# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Shapefile to PostGIS Logic
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
import psycopg2
from qgis.core import (
    QgsVectorLayer,
    QgsDataSourceUri,
    QgsProject,
    QgsMessageLog,
    Qgis,
    QgsProviderRegistry,
    QgsVectorLayerExporter,
    QgsWkbTypes
)

class ShpToPostGISLogic:
    """
    Lógica de negócio para converter uma pasta de Shapefiles em um banco PostGIS.
    """
    
    @staticmethod
    def list_shapefiles(folder_path):
        """Lista todos os .shp no diretório base."""
        shp_files = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(".shp"):
                    shp_files.append(os.path.join(root, file))
        return shp_files

    @staticmethod
    def check_db_exists(server_params, db_name):
        """Verifica se um banco de dados já existe no servidor."""
        try:
            conn = psycopg2.connect(
                dbname="postgres",
                user=server_params["user"],
                password=server_params["password"],
                host=server_params["host"],
                port=server_params["port"]
            )
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(f"SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            exists = cur.fetchone() is not None
            cur.close()
            conn.close()
            return exists
        except Exception as e:
            QgsMessageLog.logMessage(f"Erro ao verificar existência do banco: {str(e)}", "ISTools", Qgis.Warning)
            return False

    @staticmethod
    def create_database(server_params, new_db_name):
        """
        Cria um novo banco de dados no servidor especificado.
        """
        try:
            # Conecta ao banco 'postgres' default para criar o novo
            conn = psycopg2.connect(
                dbname="postgres",
                user=server_params["user"],
                password=server_params["password"],
                host=server_params["host"],
                port=server_params["port"]
            )
            conn.autocommit = True
            cur = conn.cursor()
            
            # Verifica se já existe
            cur.execute(f"SELECT 1 FROM pg_database WHERE datname = %s", (new_db_name,))
            exists = cur.fetchone()
            
            if not exists:
                cur.execute(f'CREATE DATABASE "{new_db_name}"')
                QgsMessageLog.logMessage(f"Banco '{new_db_name}' criado com sucesso.", "ISTools", Qgis.Info)
            
            cur.close()
            conn.close()
            
            # Ativa PostGIS no novo banco
            ShpToPostGISLogic.enable_postgis(server_params, new_db_name)
            return True
        except Exception as e:
            QgsMessageLog.logMessage(f"Falha ao criar banco: {str(e)}", "ISTools", Qgis.Critical)
            raise e

    @staticmethod
    def enable_postgis(server_params, db_name):
        """Habilita a extensão PostGIS no banco recém criado."""
        try:
            conn = psycopg2.connect(
                dbname=db_name,
                user=server_params["user"],
                password=server_params["password"],
                host=server_params["host"],
                port=server_params["port"]
            )
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
            QgsMessageLog.logMessage(f"Extensão PostGIS habilitada em '{db_name}'.", "ISTools", Qgis.Info)
            cur.close()
            conn.close()
        except Exception as e:
            QgsMessageLog.logMessage(f"Falha ao habilitar PostGIS: {str(e)}", "ISTools", Qgis.Critical)
            raise e

    @staticmethod
    def sanitize_table_name(name):
        """Sanitiza o nome da tabela para o PostGIS (remover espaços, acentos, aspas)."""
        import unicodedata
        import re
        
        # 1. Remover acentos e normalizar
        nfkd_form = unicodedata.normalize('NFKD', name)
        name = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
        
        # 2. Remover apóstrofos e caracteres especiais chatos
        name = name.replace("'", "").replace('"', "")
        
        # 3. Trocar espaços e hífens por underscore
        name = re.sub(r'[\s\-]+', '_', name)
        
        # 4. Remover qualquer coisa que não seja alfa-numérico ou underscore
        name = re.sub(r'[^a-zA-Z0-9_]', '', name)
        
        # 5. Converter para minúsculo (Padrão Postgres)
        return name.lower()

    @staticmethod
    def register_layer_metadata(server_params, db_name, sanitized_name, original_name):
        """Registra o nome original da camada em uma tabela de metadados no PostGIS."""
        try:
            conn = psycopg2.connect(
                dbname=db_name,
                user=server_params["user"],
                password=server_params["password"],
                host=server_params["host"],
                port=server_params["port"]
            )
            conn.autocommit = True
            cur = conn.cursor()
            
            # Criar tabela de metadados se não existir
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.istools_metadata (
                    sanitized_name TEXT PRIMARY KEY,
                    original_name TEXT
                );
            """)
            
            # Inserir ou atualizar mapeamento
            cur.execute("""
                INSERT INTO public.istools_metadata (sanitized_name, original_name)
                VALUES (%s, %s)
                ON CONFLICT (sanitized_name) DO UPDATE SET original_name = EXCLUDED.original_name;
            """, (sanitized_name, original_name))
            
            cur.close()
            conn.close()
        except Exception as e:
            QgsMessageLog.logMessage(f"Erro ao registrar metadados: {str(e)}", "ISTools", Qgis.Warning)

    @staticmethod
    def import_shp_to_postgis(shp_path, server_params, db_name, feedback=None):
        """
        Importa um arquivo Shapefile para o banco PostGIS usando QgsVectorLayerExporter.
        """
        original_name = os.path.splitext(os.path.basename(shp_path))[0]
        layer_name = ShpToPostGISLogic.sanitize_table_name(original_name)
        
        # 1. Carregar Camada SHP
        vlayer = QgsVectorLayer(shp_path, layer_name, "ogr")
        if not vlayer.isValid():
            if feedback: feedback.reportError(f"Falha ao carregar SHP: {shp_path}")
            return False

        # 2. Configurar URI de Destino
        uri = QgsDataSourceUri()
        uri.setConnection(
            server_params["host"],
            str(server_params["port"]),
            db_name,
            server_params["user"],
            server_params["password"]
        )
        uri.setDataSource("public", layer_name, "geom")
        
        # 3. Importar usando QgsVectorLayerExporter
        options = {
            'OVERWRITE': True,
            'GEOMETRY_NAME': 'geom',
            'PRIMARY_KEY': 'id',
            'SCHEMA': 'public',
            'TABLENAME': layer_name,
            'SRID': int(vlayer.crs().postgisSrid()) if vlayer.crs().isValid() else 0,
            'CREATE_SPATIAL_INDEX': True
        }
        
        err, msg = QgsVectorLayerExporter.exportLayer(
            vlayer, 
            uri.uri(), 
            "postgres", 
            vlayer.crs(), 
            False,
            options
        )

        if err == QgsVectorLayerExporter.NoError:
            # 4. Registrar metadados para reversão de nome futura
            ShpToPostGISLogic.register_layer_metadata(server_params, db_name, layer_name, original_name)
            
            # 5. Verificação Pós-Importação
            dest_layer = QgsVectorLayer(uri.uri(), layer_name, "postgres")
            valid_import = False
            if dest_layer.isValid():
                dest_count = dest_layer.featureCount()
                success_msg = f"✅ Importado: {original_name} -> {layer_name} ({dest_count} feições)"
                if feedback: feedback.pushInfo(success_msg)
                valid_import = True
            else:
                if feedback: feedback.reportError(f"❌ Erro: Tabela {layer_name} criada, mas QGIS não conseguiu carregar")
            
            # Limpeza de memória
            del dest_layer
            del vlayer
            return valid_import
        else:
            if feedback: feedback.reportError(f"❌ Erro ao importar {layer_name}: {msg}")
            del vlayer
            return False
