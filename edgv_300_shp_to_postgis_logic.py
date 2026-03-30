# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Intelligent EDGV 3.0 v1.1.6 ETL Logic
                                 A QGIS plugin
 Professional vectorization toolkit for QGIS
                               -------------------
        begin                : 2026-03-22
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
"""

import os
import json
import csv
import math
from typing import Any, Optional, Dict, List, Generator

from qgis.core import (
    QgsVectorLayer,
    NULL
)

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
        self.data = self._get_mapping_data()
            
        if "class_mapping" not in self.data:
            raise ValueError("O arquivo de Mapeamento é inválido e não possui a chave 'class_mapping'.")
            
        self._class_map = {
            cls["shp_class"]: cls for cls in self.data["class_mapping"]
        }

    def _get_mapping_data(self):
        """ Carrega o mapeamento do diretório data do plugin. """
        json_path = os.path.join(os.path.dirname(__file__), "data", "edgv_300_mapping.json")
        if not os.path.exists(json_path):
            # Fallback path if used within processing subfolder
            json_path = os.path.join(os.path.dirname(__file__), "..", "data", "edgv_300_mapping.json")
            
        if not os.path.exists(json_path):
            raise RuntimeError(f"Arquivo de mapeamento não encontrado em: {json_path}")
            
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)

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
        if not os.path.exists(self.directory_path):
            return shapefiles
            
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

    def write_inserts(self, records: List[PostGISRecord]):
        if not records:
            return

        with open(self.output_filepath, 'a', encoding='utf-8') as f:
            for record in records:
                columns = []
                values = []
                
                for col_name, val in record.attributes.items():
                    columns.append(f'"{col_name}"')
                    values.append(self._format_value(val, "unknown"))
                
                if record.wkt_geometry:
                    columns.append('"geom"')
                    values.append(f"ST_GeomFromText('{record.wkt_geometry}', 4674)")
                
                cols_str = ", ".join(columns)
                vals_str = ", ".join(values)
                
                sql = f'INSERT INTO "{self.schema_name}"."{record.table_name}" ({cols_str}) VALUES ({vals_str});\n'
                f.write(sql)
                
    def close(self):
        with open(self.output_filepath, 'a', encoding='utf-8') as f:
            f.write(f"\nCOMMIT;\n")


class PostGISBatchWriter:
    """ Escritor para inserção direta no PostGIS via psycopg2. """
    def __init__(self, connection_params: dict, db_name: str, schema_name: str = "edgv"):
        import psycopg2
        self.conn_params = connection_params.copy()
        self.db_name = db_name
        self.schema_name = schema_name
        
        # Filtrar parâmetros QGIS incompatíveis com psycopg2
        for key in ("authcfg",):
            self.conn_params.pop(key, None)
            
        self.conn_params["dbname"] = db_name
        self.conn = psycopg2.connect(**self.conn_params)
        self.conn.autocommit = False # Usar transações manuais
        self.cur = self.conn.cursor()

    def _is_null(self, val: Any) -> bool:
        if val is None or val == NULL:
            return True
        if isinstance(val, str) and val.strip().lower() in ('', 'nan', 'null'):
            return True
        if isinstance(val, float) and math.isnan(val):
            return True
        return False

    def write_inserts(self, records: List[PostGISRecord]):
        if not records:
            return

        for record in records:
            columns = []
            values = []
            
            for col_name, val in record.attributes.items():
                columns.append(f'"{col_name}"')
                if self._is_null(val):
                    values.append(None)
                else:
                    values.append(val)
            
            if record.wkt_geometry:
                columns.append('"geom"')
                # Geometria via ST_GeomFromText com placeholder %s
                query_geom = f"ST_GeomFromText(%s, 4674)"
            else:
                query_geom = None

            cols_str = ", ".join(columns)
            placeholders = ["%s"] * len(values)
            if query_geom:
                placeholders.append(query_geom)
                values.append(record.wkt_geometry)
                
            placeholders_str = ", ".join(placeholders)
            
            sql = f'INSERT INTO "{self.schema_name}"."{record.table_name}" ({cols_str}) VALUES ({placeholders_str})'
            try:
                self.cur.execute(sql, tuple(values))
            except Exception as e:
                self.conn.rollback()
                raise e

    def commit(self):
        self.conn.commit()

    def close(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
