"""
***************************************************************************
*   Conversor Shapefile para PostGIS (EDGV 3.0) via QGIS (Standalone)     *
***************************************************************************
"""

import os
import json
import csv
import math
from pathlib import Path
from typing import Any, Optional, Dict, List, Generator

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterFile,
    QgsProcessingParameterBoolean,
    QgsVectorLayer,
    NULL
)
from qgis import processing

# ============================================================================
#                               DADOS EMBUTIDOS
# ============================================================================

# O mapeamento é distribuído como JSON legível em ``data``. Mantê-lo fora do
# código evita falsos positivos de segredo e permite auditoria do conteúdo.

import json

def get_mapping_data():
    """Carrega o mapeamento EDGV distribuído com o projeto."""
    mapping_path = Path(__file__).resolve().parents[1] / "data" / "edgv_300_mapping.json"
    try:
        with mapping_path.open("r", encoding="utf-8") as mapping_file:
            return json.load(mapping_file)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Não foi possível carregar o mapeamento EDGV: {mapping_path}"
        ) from error

# ============================================================================
#                               ENTIDADES
# ============================================================================

class ShapefileRecord:
    """ Representação de uma feição lida do Shapefile usando QGIS nativo. """
    def __init__(self, wkt_geometry: str, attributes: Dict[str, Any]):
        self.wkt_geometry = wkt_geometry
        self.attributes = attributes


class PostGISRecord:
    """ Representação de uma feição mapeada para o banco PostGIS. """
    def __init__(self, table_name: str, wkt_geometry: str, attributes: Dict[str, Any]):
        self.table_name = table_name
        self.wkt_geometry = wkt_geometry
        self.attributes = attributes


# ============================================================================
#                               REGRAS E MAPPER
# ============================================================================

class MappingRules:
    def __init__(self):
        # A API Agora lê da função de Mapeamento Mestra Centralizada Embutida
        self.data = get_mapping_data()
            
        if "class_mapping" not in self.data:
            raise ValueError("O arquivo de Mapeamento Embutido é inválido e não possui a chave 'class_mapping'.")
            
        self._class_map = {
            cls["shp_class"]: cls for cls in self.data["class_mapping"]
        }

    def get_pg_table(self, shp_class_name: str) -> str:
        cls_info = self._class_map.get(shp_class_name)
        return cls_info["pg_table"] if cls_info else None

    def get_attribute_mapping(self, shp_class_name: str, shp_attr_name: str) -> dict:
        cls_info = self._class_map.get(shp_class_name)
        if not cls_info:
            return None
        for attr in cls_info["attributes"]:
            if attr["shp_attr"] == shp_attr_name:
                return attr
        return None
        
    def get_default_fields(self, shp_class_name: str) -> dict:
        cls_info = self._class_map.get(shp_class_name)
        if cls_info:
            return cls_info.get("default_fields", {})
        return {}


class GeometricAttributeMapper:
    def __init__(self, mapping_rules: MappingRules, output_dir: str):
        self.rules = mapping_rules
        self.output_dir = output_dir

    def _is_null(self, val: Any) -> bool:
        """ Verifica nulo usando tipos do Python e do QGIS sem Pandas """
        if val is None or val == NULL:
            return True
        if isinstance(val, str) and val.strip().lower() in ('', 'nan', 'null'):
            return True
        if isinstance(val, float) and math.isnan(val):
            return True
        return False

    def _transform_value(self, shp_val: any, mapping_info: dict) -> any:
        if self._is_null(shp_val):
            if mapping_info and "default_value" in mapping_info:
                return mapping_info["default_value"]
            return None
            
        if mapping_info and mapping_info.get("is_domain"):
            val_map = mapping_info.get("value_map", {})
            val_str = str(shp_val).strip()
            
            if val_str in val_map:
                return val_map[val_str]
            elif val_str.upper() in val_map:
                return val_map[val_str.upper()]
                
            return mapping_info.get("default_value")
            
        if mapping_info and mapping_info.get("pg_type") == "boolean":
            if isinstance(shp_val, bool):
                return shp_val
            if isinstance(shp_val, str):
                return shp_val.lower() in ("true", "t", "yes", "y", "1")
            if isinstance(shp_val, int):
                return shp_val == 1
                
        return shp_val

    def map_record(self, shp_class_name: str, full_shp_name: str, record: ShapefileRecord) -> Optional[PostGISRecord]:
        pg_table_base = self.rules.get_pg_table(shp_class_name)
        if not pg_table_base:
            return None
            
        suffix = full_shp_name[-2:].lower()
        if suffix in ("_a", "_l", "_p"):
            pg_table = f"{pg_table_base}{suffix}"
        else:
            pg_table = pg_table_base
            
        pg_attributes = {}
        
        for shp_attr_name, shp_value in record.attributes.items():
            if shp_attr_name.upper() == "ID":
                continue
                
            attr_mapping = self.rules.get_attribute_mapping(shp_class_name, shp_attr_name)
            
            if attr_mapping:
                pg_col_name = attr_mapping["pg_attr"]
                pg_val = self._transform_value(shp_value, attr_mapping)
                pg_attributes[pg_col_name] = pg_val
                
        default_fields = self.rules.get_default_fields(shp_class_name)
        for def_attr, def_val in default_fields.items():
            if def_attr not in pg_attributes or self._is_null(pg_attributes[def_attr]):
                pg_attributes[def_attr] = def_val

        # Auditoria
        feicao_id = record.attributes.get("ID", "SN")
        inconsistencies = []
        
        for pg_col, pg_val in pg_attributes.items():
            if pg_val in (9999, "Desconhecido"):
                raw_shp_val = "N/A"
                shp_col_name = "N/A"
                
                for shp_attr, s_val in record.attributes.items():
                    amap = self.rules.get_attribute_mapping(shp_class_name, shp_attr)
                    if amap and amap["pg_attr"] == pg_col:
                        shp_col_name = shp_attr
                        raw_shp_val = str(s_val)
                        break
                
                is_prenchido = not self._is_null(raw_shp_val) and raw_shp_val != "N/A"
                motivo = "Sem correspondência no Domínio" if is_prenchido else "Obrigatório (Vazio/Nulo/Inexistente no SHP)"
                
                inconsistencies.append([full_shp_name, feicao_id, shp_col_name, raw_shp_val, pg_col, str(pg_val), motivo])
        
        if inconsistencies:
            audit_file = os.path.join(self.output_dir, "relatorio_inconsistencias.csv")
            try:
                file_exists = os.path.exists(audit_file)
                with open(audit_file, "a", encoding="utf-8", newline='') as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow(["Classe_Shapefile", "ID_Feicao", "Coluna_SHP_Origem", "Valor_Original_SHP", "Coluna_PG", "Valor_Atribuido", "Motivo"])
                    for inc in inconsistencies:
                        writer.writerow(inc)
            except IOError:
                pass
                    
        return PostGISRecord(table_name=pg_table, 
                             wkt_geometry=record.wkt_geometry, 
                             attributes=pg_attributes)


# ============================================================================
#                        INFRAESTRUTURA: LEITURA E ESCRITA
# ============================================================================

class ShapefileReader:
    def __init__(self, directory_path: str):
        self.directory_path = directory_path

    def get_shapefiles(self) -> list:
        shapefiles = []
        for file in os.listdir(self.directory_path):
            if file.lower().endswith(".shp"):
                shapefiles.append(os.path.join(self.directory_path, file))
        return shapefiles

    def read_records(self, filepath: str) -> Generator[ShapefileRecord, None, None]:
        layer = QgsVectorLayer(filepath, "layer", "ogr")
        if not layer.isValid():
            raise RuntimeError(f"Falha ao abrir layer com QGIS OGR: {filepath}")
            
        fields = [field.name() for field in layer.fields()]
        
        for feature in layer.getFeatures():
            geom = feature.geometry()
            geom_wkt = geom.asWkt() if not geom.isNull() else None
            
            attributes = {}
            for field in fields:
                val = feature[field]
                attributes[field] = val
                
            yield ShapefileRecord(wkt_geometry=geom_wkt, attributes=attributes)


class SqlScriptWriter:
    def __init__(self, output_filepath: str, schema_name: str = "edgv"):
        self.output_filepath = output_filepath
        self.schema_name = schema_name
        with open(self.output_filepath, 'w', encoding='utf-8') as f:
            f.write(f"-- Arquivo SQL de migracao automatica de Shapefile EDGV para PostGIS\n")
            f.write(f"BEGIN;\n\n")

    def _is_null(self, val: Any) -> bool:
        if val is None or val == NULL:
            return True
        if isinstance(val, str) and val.strip().lower() in ('', 'nan', 'null'):
            return True
        if isinstance(val, float) and math.isnan(val):
            return True
        return False

    def _format_value(self, val, pg_type: str) -> str:
        if self._is_null(val):
            return "NULL"
            
        if isinstance(val, bool):
            return "TRUE" if val else "FALSE"
        
        if isinstance(val, (int, float)):
            return str(val)
        
        val_str = str(val)
        val_str = val_str.replace("'", "''")
        return f"'{val_str}'"

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + str(identifier).replace('"', '""') + '"'

    def write_inserts(self, records: List[PostGISRecord]):
        if not records:
            return

        with open(self.output_filepath, 'a', encoding='utf-8') as f:
            for record in records:
                columns = []
                values = []
                
                for col_name, val in record.attributes.items():
                    columns.append(self._quote_identifier(col_name))
                    values.append(self._format_value(val, "unknown"))
                
                if record.wkt_geometry:
                    columns.append(self._quote_identifier("geom"))
                    geometry = self._format_value(record.wkt_geometry, "text")
                    values.append("ST_GeomFromText(" + geometry + ", 4674)")
                
                cols_str = ", ".join(columns)
                vals_str = ", ".join(values)
                
                statement = (
                    "INSERT INTO "  # nosec B608
                    + self._quote_identifier(self.schema_name)
                    + "."
                    + self._quote_identifier(record.table_name)
                    + " ("
                    + cols_str
                    + ") VALUES ("
                    + vals_str
                    + ");\n"
                )
                f.write(statement)
                
    def close(self):
        with open(self.output_filepath, 'a', encoding='utf-8') as f:
            f.write(f"\nCOMMIT;\n")


# ============================================================================
#                               QGIS ALGORITHM
# ============================================================================

class ShpToPostgisAlgorithm(QgsProcessingAlgorithm):
    MERGE_OUTPUTS = "MERGE_OUTPUTS"
    OUTPUT_SQL = "OUTPUT_SQL"

    def name(self) -> str:
        return "conversor_inteligente_edgv"

    def displayName(self) -> str:
        return "Conversor Inteligente EDGV (174 Classes)"

    def group(self) -> str:
        return "Ferramentas EDGV"

    def groupId(self) -> str:
        return "ferramentas_edgv"

    def shortHelpString(self) -> str:
        return (
            "Motor de Tradução Completa de Shapefile para EDGV 3.0 (PostGIS).\n\n"
            "Este script foi concebido como um 'Canivete Suíço' Universal Standalone.\n"
            "Ele infere e lê mais de 174 classes de mapeamento (Túnel, Áreas_Edificadas, Ferrovias)\n"
            "sem exigir que o usuário digite ou importe nenhum 'mapping.json'. O cérebro está embutido.\n\n"
            "Selecione um ou MAIS diretórios completos lotados de arquivos .shp, decida o nome\n"
            "de saída do arquivo .sql e ele tratará lógicas difusas, traduções de Domínio de Atributos\n"
            "e relatórios de conversões pendentes automaticamente."
        )

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):
        # Cria 10 seletores de pastas nativos para o usuário adicionar de 1 em 1 com o mouse
        for i in range(1, 11):
            self.addParameter(
                QgsProcessingParameterFile(
                    f"INPUT_DIR_{i}",
                    f"Diretório do Banco {i}" + (" (Obrigatório)" if i == 1 else " (Opcional)"),
                    behavior=QgsProcessingParameterFile.Folder,
                    optional=(i > 1)
                )
            )
        
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.MERGE_OUTPUTS,
                "Unir TODOS os bancos em um ÚNICO arquivo SQL de saída?",
                defaultValue=True
            )
        )

        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT_SQL,
                "Arquivo SQL de Saída Gerado (Instruções INSERT)",
                "SQL Files (*.sql)"
            )
        )

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:
        
        merge_outputs = self.parameterAsBool(parameters, self.MERGE_OUTPUTS, context)
        output_sql_base = self.parameterAsString(parameters, self.OUTPUT_SQL, context)

        # Capturar todos os diretórios selecionados nas 10 caixinhas
        valid_dirs = []
        for i in range(1, 11):
            param_name = f"INPUT_DIR_{i}"
            # O get do parametro varia dependendo do QGIS, vamos usar evaluate string
            path = self.parameterAsString(parameters, param_name, context)
            if path and path.strip() != "" and os.path.exists(path):
                if path not in valid_dirs:
                    valid_dirs.append(path)

        if not valid_dirs:
            raise QgsProcessingException("Erro: Nenhuma pasta/banco foi selecionada no 'Diretório 1'. Por favor, selecione ao menos uma raiz de shapefiles.")

        feedback.pushInfo("1. Descompactando as 174 Leis Semânticas Embutidas do Conversor Central...")
        try:
            mapping_rules = MappingRules()
        except Exception as e:
            raise QgsProcessingException(str(e))

        output_dir = os.path.dirname(output_sql_base)
        mapper = GeometricAttributeMapper(mapping_rules, output_dir)
        
        total_processed_global = 0
        total_errors_global = 0
        sql_files_generated = []

        if merge_outputs:
            feedback.pushInfo(f"\n2. [Modo Unificado] Rastreando Banco de Dados nos {len(valid_dirs)} diretórios...")
            all_shapefiles = []
            
            for directory in valid_dirs:
                feedback.pushInfo(f"   + Verificando pasta: {directory}")
                reader = ShapefileReader(directory)
                shps_in_dir = reader.get_shapefiles()
                all_shapefiles.extend(shps_in_dir)
                feedback.pushInfo(f"     Encontrados {len(shps_in_dir)} shapefiles.")
            
            if not all_shapefiles:
                raise QgsProcessingException("Aviso Crítico: Zero arquivos terminados em '.shp' encontrados.")

            total_files = len(all_shapefiles)
            feedback.pushInfo(f"\n>>>> Iniciando a conversão de {total_files} shapefiles e agrupando no arquivo único.")
            
            try:
                writer = SqlScriptWriter(output_sql_base, schema_name="edgv")
            except Exception as e:
                raise QgsProcessingException(f"Falha ao criar arquivo SQL: {e}")
            
            sql_files_generated.append(output_sql_base)
            step = 100.0 / total_files if total_files > 0 else 1

            for i, shp_file in enumerate(all_shapefiles):
                if feedback.isCanceled():
                    break
                    
                filename = os.path.basename(shp_file)
                shp_class_name, _ = os.path.splitext(filename)
                
                try:
                    reader = ShapefileReader(os.path.dirname(shp_file))
                    records_lidos = reader.read_records(shp_file)
                    pg_records_lote = []
                    
                    for shape_rec in records_lidos:
                        real_class_name = shp_class_name[:-2] if shp_class_name[-2:] in ("_A", "_L", "_P", "_a", "_l", "_p") else shp_class_name
                        pg_rec = mapper.map_record(real_class_name, shp_class_name, shape_rec)
                        
                        if pg_rec:
                            pg_records_lote.append(pg_rec)
                            total_processed_global += 1
                    
                    if pg_records_lote:
                        writer.write_inserts(pg_records_lote)
                        
                except Exception as e:
                    feedback.pushInfo(f"ERRO no arquivo '{filename}': {e}")
                    total_errors_global += 1
                    
                feedback.setProgress(int((i + 1) * step))

            writer.close()
            
        else:
            feedback.pushInfo(f"\n2. [Modo Múltiplos Arquivos] Processando {len(valid_dirs)} diretórios independentemente...")
            step_dir = 100.0 / len(valid_dirs)
            
            for d_i, directory in enumerate(valid_dirs):
                if feedback.isCanceled():
                    break
                    
                dir_name = os.path.basename(os.path.normpath(directory))
                # Gerar nome base_banco.sql
                base_dir, file_name = os.path.split(output_sql_base)
                name_only, ext = os.path.splitext(file_name)
                
                dynamic_sql_path = os.path.join(base_dir, f"{name_only}_{dir_name}{ext}")
                
                feedback.pushInfo(f"\n>>>> Processando Banco: {dir_name}")
                reader = ShapefileReader(directory)
                shps_in_dir = reader.get_shapefiles()
                
                if not shps_in_dir:
                    feedback.pushInfo(f"     Nenhum .shp encontrado em {dir_name}. Pulando...")
                    continue
                    
                try:
                    writer = SqlScriptWriter(dynamic_sql_path, schema_name="edgv")
                except Exception as e:
                    feedback.pushInfo(f"   [Erro] Falha ao criar {dynamic_sql_path}: {e}")
                    continue
                
                sql_files_generated.append(dynamic_sql_path)
                
                for shp_file in shps_in_dir:
                    filename = os.path.basename(shp_file)
                    shp_class_name, _ = os.path.splitext(filename)
                    
                    try:
                        records_lidos = reader.read_records(shp_file)
                        pg_records_lote = []
                        for shape_rec in records_lidos:
                            real_class_name = shp_class_name[:-2] if shp_class_name[-2:] in ("_A", "_L", "_P", "_a", "_l", "_p") else shp_class_name
                            pg_rec = mapper.map_record(real_class_name, shp_class_name, shape_rec)
                            
                            if pg_rec:
                                pg_records_lote.append(pg_rec)
                                total_processed_global += 1
                        
                        if pg_records_lote:
                            writer.write_inserts(pg_records_lote)
                            
                    except Exception as e:
                        feedback.pushInfo(f"ERRO no arquivo '{filename}': {e}")
                        total_errors_global += 1
                
                writer.close()
                feedback.pushInfo(f"   Concluído. Salvo em: {dynamic_sql_path}")
                feedback.setProgress(int((d_i + 1) * step_dir))

        feedback.pushInfo("\n--- RESUMO DA CONVERSÃO ---")
        feedback.pushInfo(f"✅ Total de Arquivos SQL gerados: {len(sql_files_generated)}")
        for f in sql_files_generated:
            feedback.pushInfo(f"   -> {f}")
        feedback.pushInfo(f"✅ Total de registros (feições) mapeados com sucesso: {total_processed_global}")
        if total_errors_global > 0:
            feedback.pushInfo(f"⚠️ Houve erro na leitura completa ou conversão de {total_errors_global} arquivo(s) SHP.")
            
        return {self.OUTPUT_SQL: output_sql_base}

    def createInstance(self):
        return self.__class__()
