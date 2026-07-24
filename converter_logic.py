# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - EDGV ETL Converter Logic
                                 A QGIS plugin
 Professional vectorization toolkit for QGIS
                              -------------------
        begin                : 2026-03-20
        git sha              : $Format:%H$
        copyright            : (C) 2025 by Irlan Souza, 2° Sgt Brazilian Army
        email                : irlansouza193@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/

Conversor ETL Inteligente: EDGV 3.0 -> EDGV Topo 1.4.5
Desenvolvido via PyQGIS para aplicar rigorosamente as regras do JSON validado.
"""

import json
import datetime
import psycopg2
from qgis.core import (
    QgsDataSourceUri,
    QgsVectorLayer,
    QgsFeature,
    QgsWkbTypes,
    QgsFeatureRequest,
    QgsMessageLog,
    Qgis
)


class EDGVETLConverter:
    """
    Orquestrador do ETL do EDGV, consumindo o Mapeamento JSON Oficial.
    Realiza a migração de dados entre modelos EDGV 3.0 e EDGV Topo.
    """

    def __init__(self, json_path, db_params_source, db_params_target, feedback=None):
        """
        Inicializa o conversor com os parâmetros de mapeamento e banco.
        
        Args:
            json_path (str): Caminho para o arquivo JSON de mapeamento.
            db_params_source (dict): Dicionário com host, port, dbname, user, password ou authcfg.
            db_params_target (dict): Dicionário com host, port, dbname, user, password ou authcfg.
            feedback (QgsProcessingFeedback): Feedback para progresso (opcional).
        """
        self.json_path = json_path
        self.feedback = feedback
        
        with open(self.json_path, 'r', encoding='utf-8-sig') as f:
            self.mapping_rules = json.load(f)
            
        self.global_attr_mappings = self.mapping_rules.get("mapeamento_atributos", [])
        self.schema_A = self.mapping_rules.get("schema_A", "edgv")
        self.schema_B = self.mapping_rules.get("schema_B", "edgv")
        
        self.db_params_source = db_params_source
        self.db_params_target = db_params_target
        
        self.suffix_geom_A = self.mapping_rules.get("afixo_geom_A", {"POINT": "_p", "LINESTRING": "_l", "POLYGON": "_a"})
        if isinstance(self.suffix_geom_A, dict) and "POINT" not in self.suffix_geom_A:
             # Handle possible different structure in JSON
             pass

        self.suffix_geom_B = self.mapping_rules.get("afixo_geom_B", {"POINT": "_p", "LINESTRING": "_l", "POLYGON": "_a"})
        
        self.global_default_attributes_B = self.mapping_rules.get("atributos_default_B", [])
        self.global_attribute_mappings = self.mapping_rules.get("mapeamento_atributos", [])
        self.global_extensions = self.mapping_rules.get("mapeamento_extensoes", [])
        
        self.inserted_features_registry = set()
        self.db_source_counts = {}
        self.missing_tables_log = []
        
        # Novas métricas de transparência (V10/V12)
        self.total_source = 0           
        self.total_filtered = 0         
        self.total_processed = 0        
        self.total_inserted = 0         
        self.total_failed_commit = 0    
        self.failed_tables = set()      
        
        # Detalhamento V12/V13 (Quais e Por Que)
        self.ignored_by_filter_detail = {} # class_A -> count
        self.failed_commit_detail = {}     # table_target -> {count: X, error_msg: Y, class_source: Z}
        self.total_no_target_table = 0     # Feições sem tabela destino válida no banco
        self.no_target_table_detail = {}   # class_A -> count
        self.total_duplicates = 0          # Feições ignoradas por já terem sido inseridas (assinatura id+geom)
        self.duplicate_detail = {}         # class_A -> count
        self.total_geom_mismatch = 0       # Feições cuja geometria não bate com a tabela destino (ex: Ponto p/ Linha)
        self.geom_mismatch_detail = {}     # class_A -> count
        self.missing_table_detail = set()
        
        # Registros de Unicidade V21 (Fidelidade Absoluta)
        self.registry_source_unique = set()   # (tabela_A, id_A) -> Tudo que existe fisicamente
        self.registry_rescued_unique = set()  # (tabela_A, id_A) -> Tudo que chegou a ALGUM destino (pelo menos 1)
        self.registry_lost_unique = set()     # (tabela_A, id_A) -> O que realmente sumiu do banco final
        
        # Registros Detalhados V22 (Nominal)
        self.registry_no_target_fids = {}     # tabela_origem -> set(id_A)
        self.registry_filtered_fids = {}      # tabela_origem -> set(id_A)
        self.registry_geom_mismatch_fids = {} # tabela_origem -> set(id_A)

    def log(self, msg, level=Qgis.Info):
        """Redireciona logs para o QgsMessageLog e feedback se disponível."""
        if self.feedback:
            if level == Qgis.Critical:
                self.feedback.reportError(str(msg))
            else:
                self.feedback.pushInfo(str(msg))
        
        QgsMessageLog.logMessage(str(msg), "ISTools-ETL", level)

    def _build_pg_uri(self, params, schema, table_name, geom_column="geom"):
        """Gera URI formatada do PyQGIS nativa para o PostGIS."""
        uri = QgsDataSourceUri()
        if 'authcfg' in params and params['authcfg']:
            uri.setConnection(params['host'], str(params['port']), params['dbname'], params['authcfg'])
        else:
            uri.setConnection(params['host'], str(params['port']), params['dbname'], params['user'], params['password'])
        
        uri.setDataSource(schema, table_name, geom_column)
        return uri.uri(False)

    def _parse_logical_filter(self, filtro_json):
        """Transforma blocos JSON em expressões SQL/QGIS."""
        if not filtro_json:
            return ""
            
        if "$not" in filtro_json:
            sub = self._parse_logical_filter(filtro_json["$not"])
            return f"NOT ({sub})"

        if "$or" in filtro_json:
            sub_expressions = [self._parse_logical_filter(f) for f in filtro_json["$or"]]
            return f"({' OR '.join(sub_expressions)})"
            
        if "$and" in filtro_json:
            sub_expressions = [self._parse_logical_filter(f) for f in filtro_json["$and"]]
            return f"({' AND '.join(sub_expressions)})"
        
        if "nome_atributo" in filtro_json and "valor" in filtro_json:
            attr = filtro_json["nome_atributo"]
            val = filtro_json["valor"]
            
            if attr == "$GEOM_TYPE":
                # Mapear sintaxe do JSON (WKT) para retorno da função QGIS geometry_type()
                geom_map = {"LINESTRING": "Line", "POLYGON": "Polygon", "POINT": "Point"}
                val_qgis = geom_map.get(str(val).upper(), str(val))
                return f"geometry_type($geometry) = '{val_qgis}'"
                
            if isinstance(val, (int, float, bool)):
                return f"\"{attr}\" = {val}"
            else:
                return f"\"{attr}\" = '{val}'"
        
        keys = list(filtro_json.keys())
        if len(keys) == 1 and not keys[0].startswith("$"):
            attr = keys[0]
            val = filtro_json[attr]
            if isinstance(val, (int, float, bool)):
                return f"\"{attr}\" = {val}"
            else:
                return f"\"{attr}\" = '{val}'"
                
        return ""

    def _apply_domains_and_translations(self, feature_A, target_attributes, class_mapping):
        """Aplica traduções 1:1 e de domínios."""
        mapeamentos = self.global_attr_mappings + class_mapping.get('mapeamento_atributos', [])
        
        for maq in mapeamentos:
            from_attr = maq.get("attr_A")
            to_attr = maq.get("attr_B")
            
            if not from_attr or not to_attr: 
                continue
            
            if from_attr in feature_A.fields().names():
                val_A = feature_A[from_attr]
                if val_A is not None:
                    found_translation = False
                    if "traducao" in maq:
                        def _safe_str(v):
                            s = str(v)
                            return s[:-2] if s.endswith('.0') else s
                        
                        for t in maq["traducao"]:
                            sentido = t.get("sentido", "ambos")
                            if sentido == "B=>A": continue
                            if _safe_str(val_A) == _safe_str(t.get("valor_A")):
                                target_attributes[to_attr] = t.get("valor_B")
                                found_translation = True
                                break
                    
                    if not found_translation:
                        target_attributes[to_attr] = val_A

    def _apply_defaults(self, target_attributes, default_rules):
        """Injeta valores fixos no output."""
        for rule in default_rules:
            nome_attr = rule.get("nome_atributo", "") if "nome_atributo" in rule else ""
            if nome_attr in ["operador_criacao", "data_criacao", "operador_atualizacao", "data_atualizacao"]:
                continue
                
            if "nome_atributo" in rule:
                attr_name = rule["nome_atributo"]
                attr_val = rule.get("valor")
                if attr_name not in target_attributes or target_attributes[attr_name] is None:
                    if isinstance(attr_val, str) and attr_val.upper() in ["CURRENT_TIMESTAMP", "NOW()"]:
                        attr_val = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    target_attributes[attr_name] = attr_val
            else:
                for attr, val in rule.items():
                    if attr in ["operador_criacao", "data_criacao", "operador_atualizacao", "data_atualizacao"]:
                        continue
                    if attr not in target_attributes or target_attributes[attr] is None:
                        if isinstance(val, str) and val.upper() in ["CURRENT_TIMESTAMP", "NOW()"]:
                            val = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        target_attributes[attr] = val

    def _resolve_multiple_mappings(self, feature_A, target_attributes, class_mapping):
        """Motor Matricial N-to-N."""
        mapeamentos_multiplos = class_mapping.get('mapeamento_multiplo', [])
        
        for regra_n in mapeamentos_multiplos:
            sentido = regra_n.get("sentido", "ambos")
            if sentido == "B=>A":
                continue
                
            tupla_a = regra_n.get('tupla_A', [])
            tupla_b = regra_n.get('tupla_B', [])
            
            match_completo = True
            for condicao_a in tupla_a:
                attr_a = condicao_a.get('nome_atributo')
                val_esperado_a = condicao_a.get('valor')
                
                if attr_a not in feature_A.fields().names():
                    match_completo = False
                    break
                    
                val_feature = feature_A[attr_a]
                
                if isinstance(val_esperado_a, bool):
                    feat_bool = str(val_feature).lower() in ['true', '1', 't', 'y', 'yes']
                    if feat_bool != val_esperado_a:
                        match_completo = False
                        break
                elif str(val_feature) != str(val_esperado_a):
                    match_completo = False
                    break
            
            if match_completo and tupla_b:
                for transporte_b in tupla_b:
                    attr_b = transporte_b.get('nome_atributo')
                    val_b = transporte_b.get('valor')
                    target_attributes[attr_b] = val_b

    def process_class_mapping(self, mapping_block):
        """Processa o mapeamento para uma única classe."""
        classe_A = mapping_block.get('classe_A')
        classe_B = mapping_block.get('classe_B')
        
        if not classe_A or not classe_B:
            return
            
        self.log(f"Processando: {classe_A} -> {classe_B}")
        
        suffixes_map = {
            "POINT": self.suffix_geom_A.get("POINT", "_p"),
            "LINESTRING": self.suffix_geom_A.get("LINESTRING", "_l"),
            "POLYGON": self.suffix_geom_A.get("POLYGON", "_a")
        }
        
        for geom_tipo, sufixo_a in suffixes_map.items():
            nome_tabela_origem = f"{classe_A}{sufixo_a}"
            uri_a = self._build_pg_uri(self.db_params_source, self.schema_A, nome_tabela_origem)
            layer_a = QgsVectorLayer(uri_a, nome_tabela_origem, "postgres")
            
            if not layer_a.isValid():
                self.missing_tables_log.append(nome_tabela_origem)
                self.missing_table_detail.add(nome_tabela_origem)
                continue
                
            layer_count = layer_a.featureCount()
            self.db_source_counts[nome_tabela_origem] = layer_count
            
            # Auditoria Unicidade V21: Registra existência física (Ignora se regra duplicar leitura)
            for f_fisica in layer_a.getFeatures(QgsFeatureRequest().setNoAttributes().setSubsetOfAttributes([])):
                self.registry_source_unique.add((nome_tabela_origem, f_fisica.id()))

            self.total_source += layer_count
            
            filtro_a = mapping_block.get('filtro_A', {})
            req = QgsFeatureRequest()
            expression_str = self._parse_logical_filter(filtro_a)
            if expression_str:
                req.setFilterExpression(expression_str)
            
            feat_iterator = layer_a.getFeatures(req)
            features_this_layer_after_filter = 0
            fids_passed_filter = set()
            
            layers_destino = {}
            features_to_insert = {}
            
            for feature_A in feat_iterator:
                if self.feedback and self.feedback.isCanceled():
                    return

                feature_id_A = feature_A.id()
                fids_passed_filter.add(feature_id_A)
                
                features_this_layer_after_filter += 1
                self.total_processed += 1
                target_attributes = {}
                for f in feature_A.fields():
                    fname = f.name()
                    if fname not in ["id", "geom", "pk"]:
                        target_attributes[fname] = feature_A[fname]
                        
                for ext in self.global_extensions:
                    self._apply_defaults(target_attributes, ext.get("atributos_default_B", []))
                
                self._apply_domains_and_translations(feature_A, target_attributes, mapping_block)
                self._apply_defaults(target_attributes, self.global_default_attributes_B)
                self._apply_defaults(target_attributes, mapping_block.get('atributos_default_B', []))
                self._resolve_multiple_mappings(feature_A, target_attributes, mapping_block)
                
                geom = feature_A.geometry()
                geom_type = geom.type()
                
                sufixo_b = ""
                if geom_type == QgsWkbTypes.PointGeometry:
                    sufixo_b = self.suffix_geom_B.get("POINT", "_p")
                elif geom_type == QgsWkbTypes.LineGeometry:
                    sufixo_b = self.suffix_geom_B.get("LINESTRING", "_l")
                elif geom_type == QgsWkbTypes.PolygonGeometry:
                    sufixo_b = self.suffix_geom_B.get("POLYGON", "_a")
                    
                nome_tabela_destino = f"{classe_B}{sufixo_b}"
                
                if nome_tabela_destino not in layers_destino:
                    uri_b = self._build_pg_uri(self.db_params_target, self.schema_B, nome_tabela_destino)
                    layer_b = QgsVectorLayer(uri_b, nome_tabela_destino, "postgres")
                    
                    if not layer_b.isValid():
                        self.log(f"Tabela Destino inexistente: {self.schema_B}.{nome_tabela_destino}", Qgis.Warning)
                        layers_destino[nome_tabela_destino] = None
                    else:
                        layers_destino[nome_tabela_destino] = layer_b
                        features_to_insert[nome_tabela_destino] = []
                        
                layer_b = layers_destino[nome_tabela_destino]
                if not layer_b:
                    # Checar se é incompatibilidade geométrica (ex: _p indo para classe 'infra_elemento_viario' que é linha)
                    if (nome_tabela_origem.endswith('_p') or nome_tabela_origem.endswith('_a')) and classe_B == "infra_elemento_viario":
                         self.total_geom_mismatch += 1
                         self.geom_mismatch_detail[nome_tabela_origem] = self.geom_mismatch_detail.get(nome_tabela_origem, 0) + 1
                         if nome_tabela_origem not in self.registry_geom_mismatch_fids: self.registry_geom_mismatch_fids[nome_tabela_origem] = set()
                         self.registry_geom_mismatch_fids[nome_tabela_origem].add(feature_id_A)
                    else:
                         # Ausência real de Tabela Destino
                         self.total_no_target_table += 1
                         self.no_target_table_detail[nome_tabela_origem] = self.no_target_table_detail.get(nome_tabela_origem, 0) + 1
                         if nome_tabela_origem not in self.registry_no_target_fids: self.registry_no_target_fids[nome_tabela_origem] = set()
                         self.registry_no_target_fids[nome_tabela_origem].add(feature_id_A)
                    continue
                    
                # Injetar lógica semântica e check de SKIP (V18/V20)
                self._inject_semantic_context(nome_tabela_origem, nome_tabela_destino, target_attributes)
                if target_attributes.get("__SKIP__"):
                    continue
                    
                nova_feature = QgsFeature(layer_b.fields())
                nova_feature.setGeometry(geom)
                
                for field in layer_b.fields():
                    name = field.name()
                    val = target_attributes.get(name, None)
                    is_empty = (val is None or val == "" or str(val) == "NULL")
                    if is_empty and name.lower() not in ["id", "geom", "pk"]:
                        type_name = field.typeName().lower()
                        is_domain_int = ("int2" in type_name or "smallint" in type_name) or ("int" in type_name and name.lower() not in ["ordem_simbologia", "altitude", "largura", "comprimento", "profundidade", "cota"])
                        if is_domain_int:
                            if name.lower() == "revestimento":
                                val = 0
                            elif name.lower() in ["justificativa_txt", "exibir_linha_rotulo", "visivel"]:
                                val = 9999
                            else:
                                val = 9999
                        elif "date" in type_name or "time" in type_name:
                            val = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            val = None
                            
                    nova_feature.setAttribute(name, val)
                        
                # Trava anticlonagem definitiva (V20)
                # Usa a PK real do banco (se existir) em vez do FID volátil do QGIS, e ignora o WKT (para evitar bugs de float)
                feat_pk = str(feature_A["id"]) if "id" in feature_A.fields().names() else str(feature_A.id())
                signature = f"{nome_tabela_origem}_{feat_pk}_TO_{nome_tabela_destino}"
                
                if signature not in self.inserted_features_registry:
                    self.inserted_features_registry.add(signature)
                    features_to_insert[nome_tabela_destino].append(nova_feature)
                    # Registra que esta feição de origem CONSEGUIU ser enviada a pelo menos 1 destino
                    self.registry_rescued_unique.add((nome_tabela_origem, feature_A.id()))
                else:
                    self.total_duplicates += 1
                    self.duplicate_detail[nome_tabela_origem] = self.duplicate_detail.get(nome_tabela_origem, 0) + 1
                
            # Auditoria V22: Quais IDs foram filtrados nesta regra específica?
            # Filtro = (Todos IDs da camada de origem) - (IDs que passaram pelo iterador SQL da regra)
            fids_this_layer = {fid for (tbl, fid) in self.registry_source_unique if tbl == nome_tabela_origem}
            filtered_ids_this_rule = fids_this_layer - fids_passed_filter
            if filtered_ids_this_rule:
                if nome_tabela_origem not in self.registry_filtered_fids: self.registry_filtered_fids[nome_tabela_origem] = set()
                self.registry_filtered_fids[nome_tabela_origem].update(filtered_ids_this_rule)

            # Contabilizar filtrados (quem não passou no filtro SQL) - Mantido para compatibilidade técnica
            filtered_this_map = (layer_count - features_this_layer_after_filter)
            self.total_filtered += filtered_this_map
            if filtered_this_map > 0:
                self.ignored_by_filter_detail[nome_tabela_origem] = self.ignored_by_filter_detail.get(nome_tabela_origem, 0) + filtered_this_map

            for tabela_alvo, array_features in features_to_insert.items():
                if array_features: 
                    layer_alvo = layers_destino[tabela_alvo]
                    layer_alvo.startEditing()
                    layer_alvo.addFeatures(array_features)
                    sucesso_commit = layer_alvo.commitChanges()
                    
                    if not sucesso_commit:
                        msg_erro = "\n".join(layer_alvo.commitErrors())
                        self.log(f"ERRO CRÍTICO no commit {tabela_alvo} (Origem: {nome_tabela_origem}): {msg_erro}", Qgis.Critical)
                        self.total_failed_commit += len(array_features)
                        self.failed_tables.add(tabela_alvo)
                        
                        # Detalhamento V12
                        self.failed_commit_detail[tabela_alvo] = {
                            "count": len(array_features),
                            "error": msg_erro,
                            "source": nome_tabela_origem
                        }
                    else:
                        self.total_inserted += len(array_features)

    def _inject_semantic_context(self, classe_A, classe_B, target_attributes):
        """Injeta lógica semântica hardcoded para refinamento de classes."""
        tipo_atual = target_attributes.get("tipo")
        
        # Fallback V12: Tratamento inteligente para códigos não traduzidos no EDGV 3.0
        tipo_str = str(tipo_atual)
        if tipo_str == "23":
            if "comerc" in classe_A.lower():
                target_attributes["tipo"] = 904 # Supermercado
                self.log(f"Mapping Fallback: 23 -> 904 (Comercial) na classe {classe_A}", Qgis.Info)
            elif "ensino" in classe_A.lower():
                target_attributes["tipo"] = 523 # Outro Ensino (V12)
                self.log(f"Mapping Fallback: 23 -> 523 (Ensino) na classe {classe_A}", Qgis.Info)
        elif tipo_str == "24":
             if "ensino" in classe_A.lower():
                target_attributes["tipo"] = 524 # Outro Ensino (V12)
                self.log(f"Mapping Fallback: 24 -> 524 (Ensino) na classe {classe_A}", Qgis.Info)

        # Especialização Religiosa (V18)
        if "religiosa" in classe_A.lower() and classe_B == "constr_edificacao":
            ter = target_attributes.get("tipoedifrelig")
            if ter:
                # 1=Igreja, 2=Templo, 3=Mesquita, 4=Terreiro, 5=Sinagoga
                rel_map = {1: 601, 2: 602, 3: 606, 4: 609, 5: 603, 6: 604, 7: 605}
                target_attributes["tipo"] = rel_map.get(ter, 698) # Default 698 (Outros)
                self.log(f"Semantic Rescue: Religiosa {ter} -> {target_attributes['tipo']}", Qgis.Info)

        # Especialização Cemitério (V18)
        if "cemiterio" in classe_A.lower() and classe_B == "constr_ocupacao_solo":
            tc = target_attributes.get("tipocemiterio")
            da = target_attributes.get("denominacaoassociada", 0) # Religião
            # Se for vertical (5) ou se tiver denominação específica, poderíamos refinar...
            # Para o Topo 1:45k: 101=Cemitério, 102=Crematório, 103=Animal
            cem_map = {1: 101, 2: 102, 3: 103, 0: 104, 4: 104, 5: 105}
            target_attributes["tipo"] = cem_map.get(tc, 104)
            self.log(f"Semantic Rescue: Cemitério {tc} -> {target_attributes['tipo']}", Qgis.Info)

        # Especialização Canais (V18)
        if "hid_canal" in classe_A.lower() and classe_B == "elemnat_trecho_drenagem":
            sf = target_attributes.get("situacaofisica", 1)
             # 1=Construído, 2=Abandonado/N op -> Topo 2=Normal, 5=N Op
            target_attributes["tipo"] = 5 if sf == 2 else 2
            self.log(f"Semantic Rescue: Canal Situacao {sf} -> {target_attributes['tipo']}", Qgis.Info)

        # Especialização Pistas (V18/V24)
        if "pista_competicao" in classe_A.lower() and "tipopistacomp" in target_attributes:
            tp = target_attributes.get("tipopistacomp")
            # Deixar o JSON decidir ou usar 301 se for genérico (Pista)
            if str(target_attributes.get("tipo")) in ["None", "0", "9999"]:
                target_attributes["tipo"] = 301
                self.log(f"Semantic Rescue: Pista {tp} -> 301", Qgis.Info)

        # Blindagem de Integridade para Infraestrutura Pontual (V29)
        if classe_B == "infra_elemento_infraestrutura" and "_p" in src.lower():
            t_tipo = target_attributes.get("tipo")
            # Alguns bancos rejeitam 609 (Faixa de pedestres) em tabelas de ponto
            if t_tipo == 609:
                target_attributes["tipo"] = 1495 # Outro elemento de infraestrutura (V29)
                self.log(f"Integrity Shield: infra_p 609 -> 1495", Qgis.Info)

        # Dual Mapping: Fisiografia (V18/V24)
        if "elemento_fisiografico_natural" in classe_A.lower():
            # A Dicionário converteu tipoelemnat para tipo
            ten = target_attributes.get("tipoelemnat", target_attributes.get("tipo"))
            
            # Fisico(3,4,12,5) -> elemnat_elemento_fisiografico
            # Serra(1), Morro(2) -> elemnat_toponimo_fisiografico_natural
            phys_types = [3, 4, 12, 5, 13, 14, 18] # Escarpa, Talude, Falha, etc.
            topon_types = [1, 2] # Serra, Morro
            
            if "elemnat_elemento_fisiografico" in classe_B and ten in topon_types:
                target_attributes["__SKIP__"] = True
            elif classe_B == "elemnat_toponimo_fisiografico_natural" and ten in phys_types:
                target_attributes["__SKIP__"] = True
            elif target_attributes.get("tipo") is None:
                pass


        # Atualizar valor para verificação posterior
        # Atualizar valor para verificação posterior
        tipo_atual = target_attributes.get("tipo")

        if "constr_edificacao" in classe_B:
            feat_name = str(target_attributes.get("nome", "")).upper()
            found_semantic = False
            src = classe_A.lower()
            words = feat_name.split()
            is_generic = src.startswith("edf_edificacao") or src == "edf_edificacao"
            
            generics_allowed = ["None", "0", "9999", "NULL", "null", "", "2028", "525", "1398", "1798", "3098", "898", "601", "405", "1198", "798", "1098", "801", "401"]
            
            if str(tipo_atual) in generics_allowed and feat_name and feat_name not in ["NULL", "NONE"]:
                # SEGURANÇA E POLÍCIA (pode estar em seguranca, policia, civil, ou militar)
                if not found_semantic and (is_generic or any(x in src for x in ["seg", "polic", "civil", "militar"])):
                    if "DELEGACIA" in feat_name or "POLICIA CIVIL" in feat_name or "POLÍCIA CIVIL" in feat_name: target_attributes["tipo"] = 3001; found_semantic = True
                    elif "POSTO POLICIAL" in feat_name: target_attributes["tipo"] = 3002; found_semantic = True
                    elif "GUARDA MUNICIPAL" in feat_name: target_attributes["tipo"] = 3003; found_semantic = True
                    elif "RODOVIARIA" in feat_name or "PRF" in words: target_attributes["tipo"] = 3004; found_semantic = True
                    elif any(x in feat_name for x in ["POLICIA MILITAR", "POLÍCIA MILITAR", "RONDAS TATICAS", "RONDAS TÁTICAS", "BOPE"]) or "BPM" in words: target_attributes["tipo"] = 3005; found_semantic = True
                    elif any(x in feat_name for x in ["PRESIDIO", "PENITENCIARIA", "PENITENCIÁRIA", "CADEIA", "INTERNACAO", "PROVISORIA"]): target_attributes["tipo"] = 3006; found_semantic = True
                    elif "BOMBEIRO" in feat_name: target_attributes["tipo"] = 3007; found_semantic = True

                # SAÚDE
                if not found_semantic and (is_generic or "saude" in src):
                    if any(x in feat_name for x in ["HOSPITAL", "MATERNIDADE", "SANTA CASA", "HEMOCENTRO", "BIOCOR"]): target_attributes["tipo"] = 2025; found_semantic = True
                    elif any(x in feat_name for x in ["PRONTO SOCORRO", "UPA", "PRONTO ATENDIMENTO"]): target_attributes["tipo"] = 2027; found_semantic = True
                    elif any(x in feat_name for x in ["POSTO DE SAUDE", "CLINICA", "CLÍNICA", "CENTRO DE SAUDE", "CENTRO DE SAÚDE"]) or "UBS" in words: target_attributes["tipo"] = 2028; found_semantic = True
                    elif "REABILITACAO" in feat_name: target_attributes["tipo"] = 2030; found_semantic = True
                    elif any(x in feat_name for x in ["VETERINARIA", "VETERINÁRIA", "ZOONOSES"]): target_attributes["tipo"] = 2031; found_semantic = True

                # ENSINO (Reordenado: Específicos antes de Escola Genérica)
                if not found_semantic and (is_generic or "ensino" in src):
                    if any(x in feat_name for x in ["FACULDADE", "UNIVERSIDADE", "CAMPUS"]): target_attributes["tipo"] = 520; found_semantic = True
                    elif any(x in feat_name for x in ["IFES", "SENAI", "ETEC", "FATEC", "INSTITUTO FEDERAL", "PROFISSIONALIZANTE"]) or "IF" in words: target_attributes["tipo"] = 524; found_semantic = True
                    elif any(x in feat_name for x in ["ENSINO MEDIO", "ENSINO MÉDIO"]): target_attributes["tipo"] = 519; found_semantic = True
                    elif any(x in feat_name for x in ["ENSINO FUNDAMENTAL"]): target_attributes["tipo"] = 518; found_semantic = True
                    elif "CRECHE" in feat_name: target_attributes["tipo"] = 516; found_semantic = True
                    elif any(x in feat_name for x in ["PRE-ESCOLA", "JARDIM DE INFANCIA"]): target_attributes["tipo"] = 517; found_semantic = True
                    elif any(x in feat_name for x in ["ESCOLA", "COLEGIO", "COLÉGIO"]): target_attributes["tipo"] = 518; found_semantic = True

                # PÚBLICO CIVIL
                if not found_semantic and (is_generic or "civil" in src):
                    if any(x in feat_name for x in ["CARTORIO", "CARTÓRIO"]): target_attributes["tipo"] = 1303; found_semantic = True
                    elif "PREVIDENCIA" in feat_name or "PREVIDÊNCIA" in feat_name or "INSS" in words: target_attributes["tipo"] = 1307; found_semantic = True
                    elif "CAMARA MUNICIPAL" in feat_name or "CÂMARA MUNICIPAL" in feat_name: target_attributes["tipo"] = 1308; found_semantic = True
                    elif "ASSEMBLEIA" in feat_name: target_attributes["tipo"] = 1309; found_semantic = True
                    elif any(x in feat_name for x in ["FORUM", "FÓRUM", "TRIBUNAL", "JUIZADO", "JUSTICA", "JUSTIÇA", "DEFENSORIA"]): target_attributes["tipo"] = 1313; found_semantic = True
                    elif any(x in feat_name for x in ["FUNDACAO", "FUNDAÇÃO"]): target_attributes["tipo"] = 1314; found_semantic = True
                    elif any(x in feat_name for x in ["PROCURADORIA", "MINISTERIO PUBLICO", "MINISTÉRIO PÚBLICO", "ADVOCACIA GERAL"]): target_attributes["tipo"] = 1315; found_semantic = True
                    elif any(x in feat_name for x in ["SECRETARIA", "DEPARTAMENTO", "CONSELHO", "COORDENADORIA", "DIRETORIA", "ALMOXARIFADO"]): target_attributes["tipo"] = 1316; found_semantic = True
                    elif any(x in feat_name for x in ["PREFEITURA", "PAÇO MUNICIPAL", "ADMINISTRACAO REGIONAL"]): target_attributes["tipo"] = 1322; found_semantic = True
                    elif any(x in feat_name for x in ["CORREIOS", "ARQUIVO PUBLICO", "ARQUIVO PÚBLICO", "CONSULADO", "EMBAIXADA"]): target_attributes["tipo"] = 1316; found_semantic = True

                # MILITAR (Aquartelamento, etc)
                if not found_semantic and (is_generic or "militar" in src):
                    if any(x in feat_name for x in ["QUARTEL", "TIRO DE GUERRA", "BASE AEREA", "BASE NAVAL", "BATALHAO", "BATALHÃO", "REGIMENTO", "COMANDO", "COMPANHIA", "PELOTAO", "PELOTÃO", "EXERCITO", "EXÉRCITO"]) or "TG" in words: target_attributes["tipo"] = 1712; found_semantic = True
                    elif "CAPITANIA" in feat_name: target_attributes["tipo"] = 1724; found_semantic = True
                    elif "JUNTA MILITAR" in feat_name: target_attributes["tipo"] = 1718; found_semantic = True

                # AGROPECUARIA
                if not found_semantic and (is_generic or "agro" in src):
                    if "FAZENDA" in feat_name or "SITIO" in feat_name or "SÍTIO" in feat_name or "CHACARA" in feat_name or "CHÁCARA" in feat_name: target_attributes["tipo"] = 1007; found_semantic = True
                    elif "ESTUFA" in feat_name: target_attributes["tipo"] = 1004; found_semantic = True
                    
                # ENERGIA
                if not found_semantic and (is_generic or "energia" in src):
                    if "SUBESTACAO" in feat_name or "SUBESTAÇÃO" in feat_name: target_attributes["tipo"] = 898; found_semantic = True
            
            # Se a mineração textual não descobriu (ou o nome estava ausente), usamos a camada como Dica genérica APENAS se estiver com erro na origem
            novo_tipo = target_attributes.get("tipo")
            if not found_semantic and str(novo_tipo) in ["None", "0", "9999", "NULL", "null", ""]:
                if "policia" in src or "seguranca" in src: target_attributes["tipo"] = 3098
                elif "saude" in src: target_attributes["tipo"] = 2025
                elif "ensino" in src: target_attributes["tipo"] = 525 # Outras de ensino
                elif "pub_civil" in src: target_attributes["tipo"] = 1398
                elif "pub_militar" in src: target_attributes["tipo"] = 1798
                elif "relig" in src: target_attributes["tipo"] = 601
                elif "industrial" in src: target_attributes["tipo"] = 405
                elif "energia" in src: target_attributes["tipo"] = 898
                elif "turist" in src: target_attributes["tipo"] = 1198
                elif "comerc_serv" in src: target_attributes["tipo"] = 798
                elif "agropec" in src: target_attributes["tipo"] = 1098
                elif "abast" in src: target_attributes["tipo"] = 801
                elif "ext_mineral" in src: target_attributes["tipo"] = 401
            elif found_semantic and str(novo_tipo) != str(tipo_atual):
                # Se mudou do DB para algo específico por conta do Nome, logamos!
                self.log(f"Contextual Semantic Rescue: {feat_name} ({classe_A}) -> {target_attributes['tipo']} (Resgatado via Contexto Semântico Override)", Qgis.Info)
                
        # Resgate Semântico Complementar para Depósitos (Atributo 'finalidade')
        if any(substring in classe_B for substring in ["constr_deposito", "constr_ocupacao_solo"]):
            fnd = target_attributes.get("finalidade")
            if str(fnd) in ["None", "0", "9999", "NULL", "null", ""]:
                f_name = str(target_attributes.get("nome", "")).upper()
                if "TRATAMENTO" in f_name: target_attributes["finalidade"] = 2
                elif "ARMAZEN" in f_name: target_attributes["finalidade"] = 1
                elif "DISTRIB" in f_name: target_attributes["finalidade"] = 4
                elif "CAPTACAO" in f_name or "CAPTAÇÃO" in f_name: target_attributes["finalidade"] = 3

    def run_etl(self):
        """Orquestra o processo de ETL."""
        self.log("Iniciando Conversão EDGV 3.0 (v1.1.6) -> Topo (v1.4.5)...")
        self.db_target_counts = 0
        self.db_filtered_counts = 0
        self.inserted_features_registry = set()
        
        mappings = self.mapping_rules.get("mapeamento_classes", [])
        total = len(mappings)
        
        for i, mapping in enumerate(mappings):
            if self.feedback and self.feedback.isCanceled():
                self.log("Operação cancelada pelo usuário.", Qgis.Warning)
                return False
            
            if self.feedback:
                self.feedback.setProgress(int((i / total) * 100))
                
            try:
                self.process_class_mapping(mapping)
            except Exception as e:
                self.log(f"Erro crítico processando mapeamento {mapping.get('classe_A', '???')}: {str(e)}", Qgis.Critical)
                if self.feedback:
                    self.feedback.reportError(f"Erro fatal: {str(e)}")
                return False
        
        self.log_summary()
        return True

    def log_summary(self):
        """Resumo Consolidado V22 (Fidelidade Total - Detalhamento Nominal de Perdas)."""
        real_total_source = len(self.registry_source_unique)
        real_total_rescued = len(self.registry_rescued_unique)
        real_total_lost = real_total_source - real_total_rescued
        
        # O conjunto de feições ficas que REALMENTE não chegaram a nenhum destino
        lost_features = self.registry_source_unique - self.registry_rescued_unique
        
        self.log("\n" + "═"*60)
        self.log("       RELATÓRIO DE CONVERSÃO ETL - RESUMO EXECUTIVO (V22)")
        self.log("═"*60)
        
        self.log(f"1. BALANÇO FÍSICO (ITENS ÚNICOS REAIS)")
        self.log(f"   ├── (+) Total Identificado na Origem ║ {real_total_source}")
        self.log(f"   ├── (+) Total Integrado no Destino    ║ {real_total_rescued}")
        self.log(f"   └── (─) Total Não Processado (PERDA)  ║ {real_total_lost}")
        
        self.log("\n2. RASTREABILIDADE TÉCNICA (EVENTOS)")
        self.log(f"   ├── Processamento Concluído (Matches) ║ {self.total_inserted}")
        self.log(f"   ├── Duplicatas Omitidas (Redundância) ║ {self.total_duplicates}")
        self.log(f"   ├── Sem Tabela de Destino (Ignorado)  ║ {self.total_no_target_table}")
        self.log(f"   ├── Incompatibilidade Geométrica      ║ {self.total_geom_mismatch}")
        self.log(f"   └── Regras de Filtro Aplicadas (JSON) ║ {self.total_filtered}")
        self.log("─"*60)

        # V22 Nominal: Detalhamento exato de POR QUE as feições físicas se perderam
        if lost_features:
            self.log(f"\n[!] DETALHE NOMINAL DAS {real_total_lost} FEIÇÕES PERDIDAS")
            
            # Categorização das perdas reais
            loss_by_reason = {
                "Sem Tabela de Destino": {},
                "Incompatibilidade Geométrica": {},
                "Bloqueadas por Filtro do JSON (Filtro_A)": {}
            }
            
            for tbl_origem, fid in lost_features:
                reason = "Bloqueadas por Filtro do JSON (Filtro_A)" # Causa padrão se não caiu nas outras
                
                # Prioridade 1: Sem Tabela
                if tbl_origem in self.registry_no_target_fids and fid in self.registry_no_target_fids[tbl_origem]:
                    reason = "Sem Tabela de Destino"
                # Prioridade 2: Geometria
                elif tbl_origem in self.registry_geom_mismatch_fids and fid in self.registry_geom_mismatch_fids[tbl_origem]:
                    reason = "Incompatibilidade Geométrica"
                
                if tbl_origem not in loss_by_reason[reason]: loss_by_reason[reason][tbl_origem] = 0
                loss_by_reason[reason][tbl_origem] += 1
            
            # Exibição do detalhamento nominal
            for reason, details in loss_by_reason.items():
                if details:
                    self.log(f"\n• MOTIVO: {reason}")
                    for tbl, count in sorted(details.items()):
                        self.log(f"  - {tbl}: {count} feições")

        if self.failed_commit_detail:
            self.log("\n[X] CRÍTICO: FALHAS DE COMMIT NO POSTGIS")
            for tbl, info in sorted(self.failed_commit_detail.items()):
                self.log(f"  • {tbl}: {info['count']} feições PERDIDAS (Erro: {info['error'].strip()[:50]}...)")

        self.log("\n" + "═"*60)
        if real_total_lost == 0:
            self.log(f" BALANÇO FINAL: 100% DE INTEGRIDADE ALCANÇADA! [OK]")
        else:
            self.log(f" BALANÇO FINAL: {real_total_rescued}/{real_total_source} FEIÇÕES MIGRADAS.")
            
        self.log("🌐 Obrigado por usar o ISTools! Visite nosso site:")
        self.log("🚀 https://irlansouza93.github.io/istools-website/")
        self.log("═"*60 + "\n")
