# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - PostGIS to Shapefile Logic
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
from contextlib import closing
import psycopg2
from qgis.core import (
    QgsVectorLayer,
    QgsDataSourceUri,
    QgsMessageLog,
    Qgis,
    QgsVectorLayerExporter,
    QgsVectorFileWriter,
    QgsProject
)

class PostGISToShpLogic:
    """
    Lógica de negócio para exportar tabelas de um schema PostGIS para Shapefiles.
    """

    @staticmethod
    def get_spatial_tables(server_params, schema_name):
        """
        Retorna uma lista de nomes de tabelas que possuem coluna de geometria no schema.
        """
        tables = []
        try:
            conn = psycopg2.connect(
                dbname=server_params["dbname"],
                user=server_params["user"],
                password=server_params["password"],
                host=server_params["host"],
                port=server_params["port"]
            )
            cur = conn.cursor()
            
            # Consulta as tabelas espaciais registradas no geometry_columns
            query = """
                SELECT f_table_name 
                FROM geometry_columns 
                WHERE f_table_schema = %s
            """
            cur.execute(query, (schema_name,))
            rows = cur.fetchall()
            tables = [row[0] for row in rows]
            
            cur.close()
            conn.close()
        except Exception as e:
            QgsMessageLog.logMessage(f"Erro ao listar tabelas espaciais: {str(e)}", "ISTools", Qgis.Critical)
            raise e
            
        return tables

    @staticmethod
    def get_original_name(server_params, schema_name, table_name):
        """Busca o nome original da tabela na tabela de metadados."""
        original_name = table_name
        try:
            with closing(psycopg2.connect(
                dbname=server_params["dbname"],
                user=server_params["user"],
                password=server_params["password"],
                host=server_params["host"],
                port=server_params["port"],
            )) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT original_name FROM public.istools_metadata "
                        "WHERE sanitized_name = %s",
                        (table_name,),
                    )
                    row = cur.fetchone()
                    if row:
                        original_name = row[0]
        except psycopg2.errors.UndefinedTable:
            QgsMessageLog.logMessage(
                "A tabela public.istools_metadata não existe; será mantido o "
                f"nome atual '{table_name}'.",
                "ISTools",
                Qgis.Info,
            )
        except psycopg2.Error as error:
            QgsMessageLog.logMessage(
                f"Não foi possível consultar o nome original de "
                f"'{schema_name}.{table_name}': {error}",
                "ISTools",
                Qgis.Warning,
            )
        return original_name

    @staticmethod
    def export_table_to_shp(server_params, schema_name, table_name, output_folder, feedback=None):
        """
        Exporta uma única tabela PostGIS para Shapefile, tratando colisões de nomes de campos (ex: id vs ID).
        """
        # 0. Descobrir nome original (para restaurar acentos/caixa alta)
        original_name = PostGISToShpLogic.get_original_name(server_params, schema_name, table_name)

        # 1. Configurar URI da Origem
        uri = QgsDataSourceUri()
        uri.setConnection(
            server_params["host"],
            str(server_params["port"]),
            server_params["dbname"],
            server_params["user"],
            server_params["password"]
        )
        uri.setDataSource(schema_name, table_name, "geom")
        
        # 2. Carregar Camada PostGIS
        vlayer = QgsVectorLayer(uri.uri(), original_name, "postgres")
        if not vlayer.isValid():
            if feedback: feedback.reportError(f"Falha ao carregar tabela PostGIS: {schema_name}.{table_name}")
            return False

        # 3. Tratar Colisões de Nomes de Campos (Shapefile é case-insensitive)
        # Priorizar campos originais (ex: 'ID') sobre PKs gerados (ex: 'id').
        all_fields = vlayer.fields()
        best_indices = {} # Map name_upper -> index
        
        for i in range(all_fields.count()):
            field = all_fields.at(i)
            fname = field.name()
            name_upper = fname.upper()
            
            if name_upper not in best_indices:
                best_indices[name_upper] = i
            else:
                # Se for duplicata, decidir qual manter.
                # Regra: Se o atual for 'id' (minúsculo) e o já guardado for 'ID' (maiúsculo), mantém o 'ID'.
                old_index = best_indices[name_upper]
                old_name = all_fields.at(old_index).name()
                
                # Caso clássico: id (novo) vs ID (antigo)
                if old_name == 'id' and fname == 'ID':
                    best_indices[name_upper] = i
                elif old_name == 'ID' and fname == 'id':
                    pass # Mantém o que já estava (ID)
                elif any(c.isupper() for c in fname) and not any(c.isupper() for c in old_name):
                    # Se o novo tem caixa alta e o antigo não, troca
                    best_indices[name_upper] = i

        # Coletar os índices finais na ordem original
        attribute_indices = sorted(list(best_indices.values()))

        # 4. Caminho de Destino
        shp_path = os.path.join(output_folder, f"{original_name}.shp")
        
        # 5. Exportar usando QgsVectorFileWriter (mais flexível para selecionar campos)
        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = "ESRI Shapefile"
        save_options.fileEncoding = "UTF-8"
        save_options.attributes = attribute_indices # Vetor de índices dos campos a exportar
        
        # Executa a escrita usando o padrão V3 do QGIS 3.x
        err, msg, path, new_layer_id = QgsVectorFileWriter.writeAsVectorFormatV3(
            vlayer,
            shp_path,
            QgsProject.instance().transformContext(),
            save_options
        )

        if err == QgsVectorFileWriter.NoError:
            if feedback: feedback.pushInfo(f"✅ Exportado: {original_name}")
            del vlayer
            return True
        else:
            if feedback: feedback.reportError(f"❌ Erro ao exportar {original_name}: {msg}")
            del vlayer
            return False
