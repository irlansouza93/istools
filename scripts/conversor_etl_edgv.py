# -*- coding: utf-8 -*-
"""
Conversor ETL Inteligente: EDGV 3.0 -> EDGV 3.0 Topo 1:45k
Desenvolvido via PyQGIS para aplicar rigorosamente as regras do JSON validado.
"""

import sys
import os
import json
import time
import datetime
import psycopg2

# Dependências QGIS (necessidade de ambiente do OSGeo4W ou QGIS instalado no sistema)
try:
    from qgis.core import (
        QgsApplication,
        QgsDataSourceUri,
        QgsVectorLayer,
        QgsFeature,
        QgsGeometry,
        QgsProject,
        QgsWkbTypes,
        QgsExpression,
        QgsFeatureRequest,
        QgsMessageLog,
        Qgis
    )
except ImportError:
    print("ERRO: PyQGIS não encontrado. Execute este script dentro de um ambiente Python do QGIS.")
    sys.exit(1)


class EDGVConverter:
    def __init__(self, json_path, pg_host, pg_port, pg_db_source, pg_db_target, pg_user, pg_pass):
        """
        Inicia a Orquestração do ETL do EDGV, consumindo o Mapeamento JSON Oficial.
        """
        self.json_path = json_path
        
        # Carrega dicionario em memoria
        with open(self.json_path, 'r', encoding='utf-8') as f:
            self.mapping_rules = json.load(f)
            
        self.global_attr_mappings = self.mapping_rules.get("mapeamento_atributos", [])
            
        self.log(f"[*] JSON carregado: {self.mapping_rules['metadados']['modelo_A']} -> {self.mapping_rules['metadados']['modelo_B']}")
        
        # Configuracoes do Source (PostGIS)
        self.pg_db_source = pg_db_source
        self.pg_db_target = pg_db_target
        
        self.db_params = {
            'host': pg_host,
            'port': pg_port,
            'user': pg_user,
            'password': pg_pass
        }
        
        # Schemas
        self.schema_A = self.mapping_rules.get("schema_A", "edgv")
        self.schema_B = self.mapping_rules.get("schema_B", "edgv")
        
        # Geometria globals
        self.suffix_geom_A = self.mapping_rules.get("afixo_geom_A", {"POINT": "_p", "LINESTRING": "_l", "POLYGON": "_a"})
        self.suffix_geom_B = self.mapping_rules.get("afixo_geom_B", {})
        
        # Regras Globais A Extraidas (para aplicacao no iterador)
        self.global_default_attributes_B = self.mapping_rules.get("atributos_default_B", [])
        self.global_attribute_mappings = self.mapping_rules.get("mapeamento_atributos", [])
        self.global_extensions = self.mapping_rules.get("mapeamento_extensoes", [])
        
        # Variaveis de Analise e Feedback
        self.db_source_counts = {}
        self.db_target_counts = 0
        self.db_filtered_counts = 0
        self.missing_tables_log = []
        self.source_classes_in_db = set()
        self.classes_mapped_in_json = {m.get('classe_A') for m in self.mapping_rules.get("mapeamento_classes", [])}

    def log(self, msg, level=Qgis.Info):
        """Redireciona prints logicos pro MessageLog correto nativo do QGIS"""
        QgsMessageLog.logMessage(str(msg), "EDGV ETL", level)
        print(str(msg)) # Fallback seguro console externo

    def __build_pg_uri(self, db_name, schema, table_name, geom_column="geom"):
        """Gera URI formatada do PyQGIS nativa para o PostGIS"""
        uri = QgsDataSourceUri()
        uri.setConnection(
            self.db_params['host'], 
            str(self.db_params['port']), 
            db_name, 
            self.db_params['user'], 
            self.db_params['password']
        )
        uri.setDataSource(schema, table_name, geom_column)
        return uri.uri(False)
        
    def _parse_logical_filter(self, filtro_json):
        """
        Motor de Parsing Recursivo:
        Transforma os blocos `$or`, `$and`, `$not` em Expressions validas SQL/QGIS (Strings)
        """
        if not filtro_json:
            return ""
            
        # Lógica Recursiva Básica para NOT/AND/OR
        if "$not" in filtro_json:
            sub = self._parse_logical_filter(filtro_json["$not"])
            return f"NOT ({sub})"

        if "$or" in filtro_json:
            sub_expressions = [self._parse_logical_filter(f) for f in filtro_json["$or"]]
            return f"({' OR '.join(sub_expressions)})"
            
        if "$and" in filtro_json:
            sub_expressions = [self._parse_logical_filter(f) for f in filtro_json["$and"]]
            return f"({' AND '.join(sub_expressions)})"
        
        # Lógica de Raiz (Leaf Node): "nome_atributo" = "valor"
        if "nome_atributo" in filtro_json and "valor" in filtro_json:
            attr = filtro_json["nome_atributo"]
            val = filtro_json["valor"]
            if isinstance(val, (int, float, bool)):
                return f"\"{attr}\" = {val}"
            else:
                return f"\"{attr}\" = '{val}'"
        
        # Caso de dicionário raso (ex: {"tipo": 1938}) presente no Lote 2
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
        """Aplica as traduções diretas 1:1 e de domínios (mapeamento_atributos)"""
        # Aplica Globais
        for maq in self.global_attribute_mappings:
            from_attr = next(iter(maq.keys()))
            to_attr = maq[from_attr]
            if from_attr in feature_A.fields().names() and isinstance(to_attr, str):
                target_attributes[to_attr] = feature_A[from_attr]
                # Verifica traducoes diretas
                if "traducao" in maq:
                    for t in maq["traducao"]:
                        if str(feature_A[from_attr]) == str(t.get("valor_A")):
                            target_attributes[to_attr] = t.get("valor_B")
                            break
                            
    def _apply_domains_and_translations(self, feature_A, target_attributes, class_mapping):
        # Mesclar mapeamentos globais com mapeamentos da classe
        mapeamentos = self.global_attr_mappings + class_mapping.get('mapeamento_atributos', [])
        
        for maq in mapeamentos:
            from_attr = maq.get("attr_A")
            to_attr = maq.get("attr_B")
            
            if not from_attr or not to_attr: 
                continue
            
            if from_attr in feature_A.fields().names():
                val_A = feature_A[from_attr]
                if val_A is not None:
                    # 1. Tenta Tradução Específica primeiro (Prioritária)
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
                    
                    # 2. Se não tem tradução (ou o valor não está no mapa), move o valor bruto
                    if not found_translation:
                        target_attributes[to_attr] = val_A

    def _apply_defaults(self, target_attributes, default_rules):
        """Injeta dinamicamente os valores fixos no output (prevenindo nulos)"""
        for rule in default_rules:
            # Filtra mockups genéricos para que o RDBMS/Acionador PostGIS gerencie a Autoria nativamente
            nome_attr = rule.get("nome_atributo", "") if "nome_atributo" in rule else ""
            if nome_attr in ["operador_criacao", "data_criacao", "operador_atualizacao", "data_atualizacao"]:
                continue
                
            if "nome_atributo" in rule: # Novo padrão EDGV Json
                attr_name = rule["nome_atributo"]
                attr_val = rule.get("valor")
                if attr_name not in target_attributes or target_attributes[attr_name] is None:
                    if isinstance(attr_val, str) and attr_val.upper() in ["CURRENT_TIMESTAMP", "NOW()"]:
                        attr_val = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    target_attributes[attr_name] = attr_val
            else: # Antigo padrão dicionário Flat
                for attr, val in rule.items():
                    if attr in ["operador_criacao", "data_criacao", "operador_atualizacao", "data_atualizacao"]:
                        continue
                    if attr not in target_attributes or target_attributes[attr] is None:
                        if isinstance(val, str) and val.upper() in ["CURRENT_TIMESTAMP", "NOW()"]:
                            val = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        target_attributes[attr] = val

    def _resolve_multiple_mappings(self, feature_A, target_attributes, class_mapping):
        """Motor Matricial N-to-N: Verifica as tuplas_A combinadas e se TRUE aplica tuplas_B"""
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
                
                # Conversão flexível de booleanos do PostGIS/PyQGIS (t, f, 0, 1) para match com o JSON
                if isinstance(val_esperado_a, bool):
                    feat_bool = str(val_feature).lower() in ['true', '1', 't', 'y', 'yes']
                    if feat_bool != val_esperado_a:
                        match_completo = False
                        break
                elif str(val_feature) != str(val_esperado_a):
                    match_completo = False
                    break
            
            # Se a tupla de origem der match completo na feição, transportamos os valores N para a matriz destino
            if match_completo and tupla_b:
                for transporte_b in tupla_b:
                    attr_b = transporte_b.get('nome_atributo')
                    val_b = transporte_b.get('valor')
                    target_attributes[attr_b] = val_b

    def process_class_mapping(self, mapping_block):
        """
        Lê e extrai os dados baseados no Dicionário para uma Classe Única.
        """
        classe_A = mapping_block.get('classe_A')
        classe_B = mapping_block.get('classe_B')
        
        if not classe_A or not classe_B:
            return
            
        self.log(f"\n[>] Iniciando Conversão: {classe_A} ---> {classe_B}")
        
        # 1. Carregar Fonte (Schema A) tentado descobrir qual (ou quais) sufixos físicos existem
        tabelas_encontradas = 0
        
        for geom_tipo, sufixo_a in self.suffix_geom_A.items():
            nome_tabela_origem = f"{classe_A}{sufixo_a}"
            uri_a = self.__build_pg_uri(self.pg_db_source, self.schema_A, nome_tabela_origem)
            layer_a = QgsVectorLayer(uri_a, nome_tabela_origem, "postgres")
            
            if not layer_a.isValid():
                self.missing_tables_log.append(nome_tabela_origem)
                continue # Essa primitiva geometrica não existe fisicamente no banco pra essa classe. Tudo bem!
                
            tabelas_encontradas += 1
            
            # Contabilidade do Banco Fonte
            self.db_source_counts[nome_tabela_origem] = layer_a.featureCount()
            
            # 2. Aplicar Filtros Dinâmicos (Filtragem em Banco - QgsFeatureRequest)
            filtro_a = mapping_block.get('filtro_A', {})
            req = QgsFeatureRequest()
            
            expression_str = self._parse_logical_filter(filtro_a)
            if expression_str:
                self.log(f"  [-] Filtro Ativado no PostGIS para {nome_tabela_origem}: {expression_str}")
                req.setFilterExpression(expression_str)
            
            # Contagem para o Relatório Auditor (Diferença entre total e filtrado)
            total_phys_count = layer_a.featureCount()
            feat_iterator = layer_a.getFeatures(req)
            features_after_filter = 0
            feature_count = 0
            
            # Cache de conexoes e buffers de feições na memória para Bulk Insert rápido
            layers_destino = {}
            features_to_insert = {}
            
            # 3. Processamento e Transformação das Features
            for feature_A in feat_iterator:
                features_after_filter += 1
                feature_count += 1
                
                # Inicializa a matriz de atributos de destino (Topo 1:45k)
                # FME PARITY: Herança direta de atributos com nomes idênticos da origem pro destino (Preserva "nome", "sigla", etc)
                target_attributes = {}
                for f in feature_A.fields():
                    fname = f.name()
                    if fname not in ["id", "geom", "pk"]:
                        target_attributes[fname] = feature_A[fname]
                        
                for ext in self.global_extensions:
                    self._apply_defaults(target_attributes, ext.get("atributos_default_B", []))
                
                # --- ORDEM DE PRIORIDADE DO MOTOR SEMANTICO ---
                # A) Tradução de Dominios
                self._apply_domains_and_translations(feature_A, target_attributes, mapping_block)
                # B) Aplicação de Valores Padrao B
                self._apply_defaults(target_attributes, self.global_default_attributes_B)
                self._apply_defaults(target_attributes, mapping_block.get('atributos_default_B', []))
                # C) Motor Híbrido N-to-N
                self._resolve_multiple_mappings(feature_A, target_attributes, mapping_block)
                
                # C.1) Injeção de Contexto Semântico (Caso a classe generalista perca o Tipo Específico da Tabela Origem)
                # FME PARITY: Injection of hardcoded defaults based on Source Table metadata if semantic mapping is empty/null
                tipo_atual = target_attributes.get("tipo")
                if tipo_atual in [None, 0, 9999, "NULL", "null"] and classe_B == "constr_edificacao":
                    lo_name = classe_A.lower()
                    if "policia" in lo_name or "seguranca" in lo_name:
                        target_attributes["tipo"] = 3098  # Outras polícias (Segurança Pública)
                    elif "saude" in lo_name:
                        target_attributes["tipo"] = 2025  # Ponto de Saúde
                    elif "ensino" in lo_name:
                        target_attributes["tipo"] = 519   # Ensino (Educação)
                    elif "pub_civil" in lo_name:
                        target_attributes["tipo"] = 1398  # Administração Pública/Serviços
                    elif "pub_militar" in lo_name:
                        target_attributes["tipo"] = 1798  # Instalação Militar
                    elif "relig" in lo_name:
                        target_attributes["tipo"] = 601   # Templo Religioso
                    elif "industrial" in lo_name:
                        target_attributes["tipo"] = 405   # Área Industrial
                    elif "energia" in lo_name:
                        target_attributes["tipo"] = 898   # Energia/Utilidade
                    elif "turist" in lo_name:
                        target_attributes["tipo"] = 1198  # Turismo
                    elif "comerc_serv" in lo_name:
                        target_attributes["tipo"] = 798   # Comércio e Serviços
                    elif "agropec" in lo_name:
                        target_attributes["tipo"] = 1098  # Agropecuária
                    elif "abast" in lo_name:
                        target_attributes["tipo"] = 801   # Abastecimento de Água
                    elif "ext_mineral" in lo_name:
                        target_attributes["tipo"] = 401   # Extração Mineral
                        
                    # C.2) Heurística por Palavra-Chave (Refinamento de Nome)
                    # Se o tipo ainda é genérico mas o nome contém dicas óbvias, forçamos a especialização
                    feat_name = str(target_attributes.get("nome", "")).upper()
                    if feat_name:
                        if "DELEGACIA" in feat_name:
                            target_attributes["tipo"] = 3001
                        elif "POSTO POLICIAL" in feat_name or "POSTO DE POLICIA" in feat_name:
                            target_attributes["tipo"] = 3002
                        elif "BOMBEIRO" in feat_name:
                            target_attributes["tipo"] = 3007
                        elif "POSTO DE SAUDE" in feat_name or "UNIDADE BASICA" in feat_name or "UBS" in feat_name:
                            target_attributes["tipo"] = 2028
                        elif "HOSPITAL" in feat_name:
                            target_attributes["tipo"] = 2025
                        elif "CRECHE" in feat_name:
                            target_attributes["tipo"] = 516
                        elif "PREFEITURA" in feat_name:
                            target_attributes["tipo"] = 1322
                        elif "FORUM" in feat_name:
                            target_attributes["tipo"] = 1313
                        
                # D) Finalização (Tratamento de Geometria e Preparação Array - BULK)
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
                
                # 1. Carrega ou acessa do cache a tabela B para consultar seus campos nativos sem reabrir conexão!
                if nome_tabela_destino not in layers_destino:
                    uri_b = self.__build_pg_uri(self.pg_db_target, self.schema_B, nome_tabela_destino)
                    layer_b = QgsVectorLayer(uri_b, nome_tabela_destino, "postgres")
                    
                    if not layer_b.isValid():
                        self.log(f"  [!] ERRO CRITICO: Tabela Destino inexistente no Postgres: {self.schema_B}.{nome_tabela_destino}", Qgis.Critical)
                        layers_destino[nome_tabela_destino] = None # Salva nulo para skip rápido
                    else:
                        layers_destino[nome_tabela_destino] = layer_b
                        features_to_insert[nome_tabela_destino] = []
                        
                layer_b = layers_destino[nome_tabela_destino]
                if not layer_b:
                    continue # pula se já testou que não existe
                    
                # 2. Instanciar Feição Destino OGR em memoria e preencher attributes
                nova_feature = QgsFeature(layer_b.fields())
                nova_feature.setGeometry(geom)
                
                # Construção da Feição + Rotina de Resiliência Universal NOT NULL
                for field in layer_b.fields():
                    name = field.name()
                    val = target_attributes.get(name, None)
                    
                    # Tratamento de Nulos Nativos do PyQGIS (evitando que campos QVariant() ignorem o Fallback)
                    is_empty = (val is None or val == "" or str(val) == "NULL")
                    if is_empty and name.lower() not in ["id", "geom", "pk"]:
                        # Fallback agressivo EDGV para sanar regras RESTRICT do PostGIS
                        type_name = field.typeName().lower()
                        
                        # PyQGIS pode retornar 'int2' ou 'int4' para Postgres. Ignoramos inteiros opcionais como ordem_simbologia
                        is_domain_int = ("int2" in type_name or "smallint" in type_name) or ("int" in type_name and name.lower() not in ["ordem_simbologia", "altitude", "largura", "comprimento", "profundidade", "cota"])
                        
                        if is_domain_int:
                            if name.lower() == "revestimento":
                                val = 0
                            elif name.lower() in ["justificativa_txt", "exibir_linha_rotulo", "visivel"]:
                                # Nativos preechemos os textuais basicos via dicionario, caem no 9999 se nao foi herdado.
                                val = 9999
                            else:
                                val = 9999 # Valor padrao EDGV "A SER PREENCHIDO" para Dominios
                        elif "date" in type_name or "time" in type_name:
                            val = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            val = None # Garante que enviaremos nulo genuíno para campos String e Numericos Livres (integer, real) opcionais
                            
                    nova_feature.setAttribute(name, val)
                        
                # 3. Adiciona na esteira invisível RAM (evitando tráfego unitário com Postgres)
                # O motor previne duplicatas de mapeamentos (JSON com blocos sobrepostos/redundantes sem Filtros Exclusivos)
                signature = f"{nome_tabela_origem}_{nome_tabela_destino}_{feature_A.id()}"
                if signature not in self.inserted_features_registry:
                    self.inserted_features_registry.add(signature)
                    features_to_insert[nome_tabela_destino].append(nova_feature)
                
            # For do iterador da tabela A de origem finalizado. 
            # Esvaziar agora todas as coleções do Buffer com 1 comando de Transação (LOAD EFETIVO):
            for tabela_alvo, array_features in features_to_insert.items():
                if array_features: 
                    # ... (rest of bulk insert)
                    layer_alvo = layers_destino[tabela_alvo]
                    
                    # Usa o motor transacional do PyQGIS em vez do Provider direto, para pescar erros do PostgreSQL
                    layer_alvo.startEditing()
                    sucesso_add = layer_alvo.addFeatures(array_features)
                    sucesso_commit = layer_alvo.commitChanges()
                    
                    if not sucesso_commit:
                        erros_banco = layer_alvo.commitErrors()
                        msg_erro = "\n".join(erros_banco) if erros_banco else "Erro desconhecido de transação nula."
                        self.log(f"  [!] ERRO FATAL POSTGIS: Fallback na tabela {tabela_alvo}. Motivo: {msg_erro}", Qgis.Critical)
                    else:
                        self.log(f"  [OK] BULK INSERT: {len(array_features)} feições gravadas permanentemente de {nome_tabela_origem} -> {tabela_alvo}")
                        self.db_target_counts += len(array_features)
            
            # Auditoria: features que existiam mas o filtro 'Filtro_A' barrou
            self.db_filtered_counts += (total_phys_count - features_after_filter)
            
            if feature_count == 0:
                self.log(f"  [i] Sem feições correspondentes em {nome_tabela_origem}.")
                
        if tabelas_encontradas == 0:
            self.log(f"  [!] Tabela Origem base não possui ramificações validas (_p,_l,_a) no Postgres: {classe_A}", Qgis.Warning)
            
    def _analyze_source_schema(self):
        """Busca nativamente no PostGIS todas as tabelas fisicas do schema A."""
        try:
            conn = psycopg2.connect(
                host=self.db_params['host'],
                port=self.db_params['port'],
                database=self.pg_db_source,
                user=self.db_params['user'],
                password=self.db_params['password']
            )
            cur = conn.cursor()
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s",
                (self.schema_A,),
            )
            tables = cur.fetchall()
            
            for (tname,) in tables:
                base_name = tname
                for suffix in self.suffix_geom_A.values():
                    if tname.endswith(suffix):
                        base_name = tname[:len(tname)-len(suffix)]
                        break
                self.source_classes_in_db.add(base_name)
            cur.close()
            conn.close()
        except:
            self.log("[!] Nao foi possivel auditar o schema de origem dinamicamente.", Qgis.Warning)

    def run_etl(self):
        """
        Orquestra a iteração em massa de todas as regras no JSON Validado.
        """
        self.log("\n=============================================")
        self.log("  INICIANDO CONVERSÃO TOPOGRÁFICA EDGV 1:45  ")
        self.log("=============================================")
        
        # Initialize counts for this run
        self.db_source_counts = {}
        self.db_target_counts = 0
        self.db_filtered_counts = 0
        self.missing_tables_log = []
        
        # Auditoria de Schema
        self._analyze_source_schema()
        
        # Prevenção de Duplicatas Ocorridas por Blocos JSON Sobrepostos (First-Match-Wins)
        self.inserted_features_registry = set()
        
        for mapping in self.mapping_rules.get("mapeamento_classes", []):
            try:
                self.process_class_mapping(mapping)
            except Exception as e:
                self.log(f"  [ERRO] Falha fatal processando {mapping.get('classe_A')}: {str(e)}", Qgis.Critical)


# RODE DIRETAMENTE O PIPELINE AGORA (Sem inibir por __name__)
try:
    import time
    start_time = time.time()
    
    from qgis.utils import iface
    from qgis.core import Qgis
    if iface:
        iface.messageBar().pushMessage("Info", "Iniciando Conversor ETL EDGV...", level=Qgis.Info)
    
    converter = EDGVConverter(
        json_path=os.environ.get(
            "ISTOOLS_MAPPING_PATH",
            os.path.join(
                os.path.dirname(__file__),
                "conversao_pg-edgv-300_pg-edgv-300topo145.json",
            ),
        ),
        pg_host=os.environ.get("PGHOST", "localhost"),
        pg_port=int(os.environ.get("PGPORT", "5432")),
        pg_db_source=os.environ.get("ISTOOLS_SOURCE_DB", "banco-fonte"),
        pg_db_target=os.environ.get("ISTOOLS_TARGET_DB", "banco-destino"),
        pg_user=os.environ.get("PGUSER", "postgres"),
        pg_pass=os.environ.get("PGPASSWORD", ""),
    )
    # Inicia o ETL lendo todas as classes!
    converter.run_etl()
    
    end_time = time.time()
    minutos, segundos = divmod(end_time - start_time, 60)
    tempo_str = f"{int(minutos)}m {segundos:.2f}s" if minutos > 0 else f"{segundos:.2f} segundos"
    
    # ---------------------------------------------------------------------------------
    # GERAÇÃO DO SUMMARY E FEEDBACK (ORIENTAÇÃO LLM)
    # ---------------------------------------------------------------------------------
    converter.log("\n================================================================================")
    converter.log("               RESUMO EXECUTIVO DA CONVERSÃO (EDGV 3.0 -> TOPO) ")
    converter.log("================================================================================")
    
    total_source = sum(converter.db_source_counts.values())
    total_target = converter.db_target_counts
    total_ignored = total_source - total_target
    
    unmapped_classes = converter.source_classes_in_db - converter.classes_mapped_in_json
    
    converter.log("\n 1. BALANÇO GEOMÉTRICO (FEIÇÕES)")
    converter.log(f"    [+] Total lido na EDGV 3.0 (Fonte):   {total_source}")
    converter.log(f"    [+] SUCESSO! Gravados no Destino:     {total_target}")
    converter.log(f"    [-] Bloqueados ou Filtrados:          {converter.db_filtered_counts} (Feições que as regras mandaram barrar)")
    
    clone_count = total_ignored - converter.db_filtered_counts
    if clone_count > 0:
        converter.log(f"    [-] Clones Fantasmas barrados:        {clone_count} (Feições duplicadas barradas pela proteção da IA)")
    
    converter.log(f"\n 2. BALANÇO DE MAPEAMENTO DO DICIONÁRIO JSON")
    converter.log(f"    [i] Classes da Fonte contempladas com regras: {len(converter.classes_mapped_in_json)}")
    converter.log(f"    [!] Classes da Fonte SEM regras(Esquecidas):  {len(unmapped_classes)}")
    
    if unmapped_classes:
        todas_esquecidas = sorted(list(unmapped_classes))
        converter.log(f"        * QUAIS SÃO: {', '.join(todas_esquecidas)}")
        converter.log("        * MOTIVO: Normalmente estas classes são legadas da EDGV 3.0 que saíram de circulação na Topo,")
        converter.log("                  classes de apoio técnico temporário do PqRMtx, ou você pode não ter mapeado no JSON ainda.")

    missing_count = len(set(converter.missing_tables_log))
    converter.log(f"\n 3. TABELAS VAZIAS NO SEU BANCO")
    converter.log(f"    [i] O Dicionário tentou ler {missing_count} tabelas/primitivas(P/L/A) que estavam vazias ou não existem na sua Fonte.")
    converter.log("        Isso é Normal, indica apenas que esse lote não usava esses temas.")
    
    # ALERTA DE COMPORTAMENTO TOPOGRÁFICO ESPECÍFICO
    serra_count = converter.db_source_counts.get("rel_elemento_fisiografico_natural_a", 0)
    if serra_count > 0:
        converter.log("\n[!] AVISO DE CONVERSAO: TOPONIMO FISIOGRAFICO (SERRAS/MONTANHAS)")
        converter.log(f"    Foram identificados {serra_count} poligonos nativos na tabela 'rel_elemento_fisiografico_natural_a'.")
        converter.log("    A modelagem EDGV Topo descarta poligonos e exige uma ancora (Point/Linestring) para alocar o Rótulo do Toponimo.")
        converter.log("    Como nao aplicamos um extrapolador de Centroide geometrico nativamente neste script, estes poligonos")
        converter.log("    foram PROPOSITALMENTE IGNORADOS. Eh recomendado extrair o 'PointOnSurface' manual no QGIS e inserir na tabela_p.")
        
    converter.log("\n=======================================================\n")
    
    converter.log(f"[*] Processamento finalizado. Tempo Total: {tempo_str}", Qgis.Info)
    
    if iface:
        iface.messageBar().pushMessage("Sucesso", f"Script ETL terminou em {tempo_str}. Verifique os Logs!", level=Qgis.Success)
except Exception as e:
    import traceback
    erro = traceback.format_exc()
    try:
        from qgis.utils import iface
        from qgis.core import Qgis
        if iface:
            iface.messageBar().pushMessage("Falha Crítica", f"O script morreu. Erro: {str(e)}", level=Qgis.Critical)
    except:
        pass
    print("FALHA:", erro)
