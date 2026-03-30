# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - PostGIS to Shapefile Algorithm
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

from typing import Any, Optional
import os
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFile,
    QgsProcessingParameterEnum,
    QgsProcessingParameterString,
    QgsProcessingParameterBoolean,
    QgsSettings,
    QgsMessageLog,
    Qgis
)
from ..postgis_to_shp_logic import PostGISToShpLogic

class PostGISToShpAlgorithm(QgsProcessingAlgorithm):
    
    SERVER_CONN = 'SERVER_CONN'
    DB_NAME = 'DB_NAME'
    SCHEMA_NAME = 'SCHEMA_NAME'
    OUTPUT_FOLDER = 'OUTPUT_FOLDER'
    LOAD_LAYERS = 'LOAD_LAYERS'

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("Processing", string)

    def name(self):
        return 'postgis_to_shp'

    def displayName(self):
        return self.tr('Converter Banco Postgis para Shapefile')

    def group(self):
        return self.tr('Banco de Dados')

    def groupId(self):
        return 'database'

    def shortHelpString(self) -> str:
        return (
            "<b>Converter Banco Postgis para Shapefile</b>\n\n"
            "Exportador em massa de tabelas PostGIS para formato ESRI Shapefile.\n\n"
            "<b>Parâmetros:</b>\n"
            "- <b>Servidor PostGIS:</b> Seleção do servidor PostgreSQL configurado.\n"
            "- <b>Nome do Banco:</b> Nome da base de dados de origem.\n"
            "- <b>Schema:</b> Schema a ser exportado (ex: public, edgv, topo).\n"
            "- <b>Pasta de Saída:</b> Diretório de destino para os arquivos .shp.\n"
            "- <b>Carregar Camadas:</b> Adiciona automaticamente os shapes gerados ao projeto.\n\n"
            "<b>Funcionalidades:</b>\n"
            "- Recuperação automática de nomes originais (com acentos e espaços) via metadados.\n"
            "- Tratamento inteligente de colisão de nomes de campos (id vs ID).\n"
            "- Exportação em UTF-8 garantindo integridade dos atributos.\n\n"
            "<b>Autor:</b> Irlan Souza\n"
            "<b>Email:</b> <a href=\"mailto:irlansouza193@gmail.com\">irlansouza193@gmail.com</a>\n"
            "<b>GitHub:</b> <a href=\"https://github.com/irlansouza93\">https://github.com/irlansouza93</a>\n\n"
            "<b>🌐 <a href=\"https://irlansouza93.github.io/istools-website/\">🚀VISITE NOSSO SITE OFICIAL - CLIQUE AQUI! 🚀</a></b>"
        )

    def helpUrl(self) -> str:
        return "https://irlansouza93.github.io/istools-website/"

    def createInstance(self):
        return PostGISToShpAlgorithm()

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):
        # 1. Servidor de Destino (Lê das configurações do QGIS)
        settings = QgsSettings()
        settings.beginGroup("PostgreSQL/servers")
        servers = settings.childGroups()
        settings.endGroup()

        self.addParameter(
            QgsProcessingParameterEnum(
                self.SERVER_CONN,
                self.tr("Servidor PostGIS"),
                options=servers,
                defaultValue=0 if servers else -1
            )
        )

        # 2. Nome do Banco
        self.addParameter(
            QgsProcessingParameterString(
                self.DB_NAME,
                self.tr("Nome do Banco de Dados"),
                defaultValue="postgres"
            )
        )

        # 3. Schema
        self.addParameter(
            QgsProcessingParameterString(
                self.SCHEMA_NAME,
                self.tr("Schema (ex: public, edgv)"),
                defaultValue="public"
            )
        )

        # 4. Pasta de Saída
        self.addParameter(
            QgsProcessingParameterFile(
                self.OUTPUT_FOLDER,
                self.tr("Pasta de Saída"),
                behavior=QgsProcessingParameterFile.Folder
            )
        )

        # 5. Carregar camadas convertidas
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_LAYERS,
                self.tr("Carregar camadas convertidas no projeto"),
                defaultValue=True
            )
        )

    def processAlgorithm(self, parameters: dict[str, Any], context: QgsProcessingContext, feedback: QgsProcessingFeedback) -> dict[str, Any]:
        server_idx = self.parameterAsInt(parameters, self.SERVER_CONN, context)
        db_name = self.parameterAsString(parameters, self.DB_NAME, context)
        schema_name = self.parameterAsString(parameters, self.SCHEMA_NAME, context)
        output_folder = self.parameterAsFile(parameters, self.OUTPUT_FOLDER, context)
        load_layers = self.parameterAsBoolean(parameters, self.LOAD_LAYERS, context)

        # 1. Obter parâmetros do servidor
        settings = QgsSettings()
        settings.beginGroup("PostgreSQL/servers")
        servers = settings.childGroups()
        if server_idx < 0 or server_idx >= len(servers):
            raise QgsProcessingException("Servidor inválido ou não selecionado.")
            
        server_name = servers[server_idx]
        settings.endGroup()
        
        settings.beginGroup(f"PostgreSQL/servers/{server_name}")
        params_db = {
            "host": settings.value("host"),
            "port": settings.value("port", "5432"),
            "user": settings.value("username"),
            "password": settings.value("password"),
            "dbname": db_name
        }
        settings.endGroup()

        # 2. Listar tabelas espaciais
        feedback.pushInfo(f"🔍 Buscando tabelas espaciais no schema '{schema_name}'...")
        tables = PostGISToShpLogic.get_spatial_tables(params_db, schema_name)
        
        if not tables:
            feedback.pushInfo(f"⚠️ Nenhuma tabela com geometria encontrada no schema '{schema_name}'.")
            return {"RESULT": "Nenhuma tabela exportada."}

        total = len(tables)
        feedback.pushInfo(f"📦 Encontradas {total} tabelas.")
        
        success_paths = [] # Lista de (path, layer_name)

        # 3. Exportar cada tabela
        for i, table in enumerate(tables):
            if feedback.isCanceled():
                break
            
            feedback.setProgress(int((i / total) * 100))
            
            # Descobrir nome original antes de exportar
            original_name = PostGISToShpLogic.get_original_name(params_db, schema_name, table)
            feedback.pushInfo(f"⏳ Exportando {table} -> {original_name}.shp...")
            
            exported = PostGISToShpLogic.export_table_to_shp(
                params_db, 
                schema_name, 
                table, 
                output_folder, 
                feedback
            )
            
            if exported:
                shp_path = os.path.join(output_folder, f"{original_name}.shp")
                success_paths.append((shp_path, original_name))

        # 4. Apenas guardar os dados para carregar no postProcess (Thread Principal)
        self.success_paths = success_paths
        self.db_name_to_load = db_name
        self.should_load = load_layers

        feedback.setProgress(100)
        feedback.pushInfo("🎯 Exportação concluída na Task. Organizando camadas na UI...")

        return {"RESULT": f"Exportação de {len(success_paths)} tabelas concluída para {output_folder}"}

    def postProcessAlgorithm(self, context, feedback):
        """
        Executado na Thread Principal após o processAlgorithm.
        """
        if not hasattr(self, 'should_load') or not self.should_load or not self.success_paths:
            return {}

        from qgis.core import QgsVectorLayer, QgsWkbTypes, QgsProject, QgsApplication
        
        project = context.project()
        if not project:
            project = QgsProject.instance()

        feedback.pushInfo(self.tr("📥 Carregando Shapefiles no projeto (Thread Principal)..."))
        
        root = project.layerTreeRoot()
        main_group = root.addGroup(self.db_name_to_load)
        
        # Subgrupos de primitivas
        groups = {
            QgsWkbTypes.PointGeometry: main_group.addGroup(self.tr("Pontos")),
            QgsWkbTypes.LineGeometry: main_group.addGroup(self.tr("Linhas")),
            QgsWkbTypes.PolygonGeometry: main_group.addGroup(self.tr("Polígonos")),
            None: main_group.addGroup(self.tr("Outros"))
        }

        layers_to_add = []
        layer_group_map = []

        project.blockSignals(True)
        try:
            for shp_p, name in self.success_paths:
                layer = QgsVectorLayer(shp_p, name, "ogr")
                if layer.isValid():
                    layers_to_add.append(layer)
                    
                    geometry_type = QgsWkbTypes.geometryType(layer.wkbType())
                    target_group = groups.get(geometry_type, groups[None])
                    layer_group_map.append((layer, target_group))
                
                QgsApplication.processEvents()

            project.addMapLayers(layers_to_add, False)
            
            for layer, group in layer_group_map:
                group.addLayer(layer)
                
        finally:
            project.blockSignals(False)

        for group in list(groups.values()):
            if not group.children():
                main_group.removeChildNode(group)

        feedback.pushInfo("✅ Exportação organizada com sucesso!")
        return {}

    def createInstance(self):
        return PostGISToShpAlgorithm()
