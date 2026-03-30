# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Shapefile to PostGIS Algorithm
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

from ..shp_to_postgis_logic import ShpToPostGISLogic

class ShpToPostGISAlgorithm(QgsProcessingAlgorithm):
    """
    Algoritmo para converter uma pasta de Shapefiles em um novo banco PostGIS.
    """

    FOLDER_PATH = "FOLDER_PATH"
    SERVER_CONN = "SERVER_CONN"
    NEW_DB_NAME = "NEW_DB_NAME"
    APPEND_MODE = "APPEND_MODE"
    LOAD_LAYERS = "LOAD_LAYERS"

    def name(self) -> str:
        return "shp_to_postgis"

    def displayName(self) -> str:
        return self.tr("Converter banco shapefile para postgis")

    def group(self) -> str:
        return self.tr("Banco de Dados")

    def groupId(self) -> str:
        return "database"

    def shortHelpString(self) -> str:
        return (
            "<b>Converter banco shapefile para postgis</b>\n\n"
            "Importador em massa de Shapefiles para um novo banco de dados PostGIS.\n\n"
            "<b>Parâmetros:</b>\n"
            "- <b>Pasta:</b> Diretório contendo os arquivos .shp (varredura recursiva).\n"
            "- <b>Servidor PostGIS:</b> Seleção do servidor PostgreSQL configurado no QGIS.\n"
            "- <b>Nome do Banco:</b> Nome da nova base de dados que será criada.\n"
            "- <b>Carregar Camadas:</b> Adiciona automaticamente as novas tabelas ao projeto atual.\n\n"
            "<b>Funcionalidades:</b>\n"
            "- Sanitização automática de nomes (remove espaços, acentos e aspas).\n"
            "- Persistência de metadados para garantir reversibilidade (Round-Trip).\n"
            "- Criação automática de Chave Primária (id) e Índice Espacial (GiST).\n\n"
            "<b>Autor:</b> Irlan Souza\n"
            "<b>Email:</b> <a href=\"mailto:irlansouza193@gmail.com\">irlansouza193@gmail.com</a>\n"
            "<b>GitHub:</b> <a href=\"https://github.com/irlansouza93\">https://github.com/irlansouza93</a>\n\n"
            "<b>🌐 <a href=\"https://irlansouza93.github.io/istools-website/\">🚀VISITE NOSSO SITE OFICIAL - CLIQUE AQUI! 🚀</a></b>"
        )

    def helpUrl(self) -> str:
        return "https://irlansouza93.github.io/istools-website/"

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("Processing", string)

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):
        # Pasta de Origem
        self.addParameter(
            QgsProcessingParameterFile(
                self.FOLDER_PATH,
                self.tr("Pasta contendo Shapefiles"),
                behavior=QgsProcessingParameterFile.Folder
            )
        )

        # Servidor de Destino (Lê das configurações do plugin)
        settings = QgsSettings()
        settings.beginGroup("PostgreSQL/servers")
        servers = settings.childGroups()
        settings.endGroup()

        self.addParameter(
            QgsProcessingParameterEnum(
                self.SERVER_CONN,
                self.tr("Servidor PostGIS Destino"),
                options=servers,
                defaultValue=0 if servers else -1
            )
        )

        # Nome do Novo Banco
        self.addParameter(
            QgsProcessingParameterString(
                self.NEW_DB_NAME,
                self.tr("Nome do Novo Banco de Dados"),
                defaultValue="novo_banco_postgis"
            )
        )

        # Modo de anexar dados
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.APPEND_MODE,
                self.tr("Adicionar registros se o banco já existir (Modo Append)"),
                defaultValue=False
            )
        )

        # Carregar camadas convertidas
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.LOAD_LAYERS,
                self.tr("Carregar camadas convertidas no projeto"),
                defaultValue=True
            )
        )

    def processAlgorithm(self, parameters: dict[str, Any], context: QgsProcessingContext, feedback: QgsProcessingFeedback) -> dict[str, Any]:
        folder_path = self.parameterAsFile(parameters, self.FOLDER_PATH, context)
        server_idx = self.parameterAsInt(parameters, self.SERVER_CONN, context)
        new_db_name = self.parameterAsString(parameters, self.NEW_DB_NAME, context)
        load_layers = self.parameterAsBoolean(parameters, self.LOAD_LAYERS, context)
        append_mode = self.parameterAsBoolean(parameters, self.APPEND_MODE, context)

        # 1. Obter parâmetros do servidor
        settings = QgsSettings()
        settings.beginGroup("PostgreSQL/servers")
        servers = settings.childGroups()
        if server_idx < 0 or server_idx >= len(servers):
            raise QgsProcessingException("Servidor inválido ou não selecionado.")
            
        server_name = servers[server_idx]
        settings.endGroup()
        
        settings.beginGroup(f"PostgreSQL/servers/{server_name}")
        server_params = {
            "host": settings.value("host", "localhost"),
            "port": settings.value("port", "5432"),
            "user": settings.value("username", "postgres"),
            "password": settings.value("password", "")
        }
        settings.endGroup()

        # 2. Listar SHPs
        feedback.pushInfo(f"Buscando Shapefiles em: {folder_path}")
        shp_files = ShpToPostGISLogic.list_shapefiles(folder_path)
        if not shp_files:
            feedback.reportError("Nenhum arquivo .shp encontrado na pasta.")
            return {}

        feedback.pushInfo(f"Encontrados {len(shp_files)} arquivos.")

        # 3. Conferir se Banco existe e Criar se necessário
        db_exists = ShpToPostGISLogic.check_db_exists(server_params, new_db_name)
        
        if db_exists:
            if not append_mode:
                raise QgsProcessingException(
                    self.tr(f"O banco de dados '{new_db_name}' já existe. "
                            "Habilite o 'Modo Append' se deseja adicionar novas tabelas a este banco.")
                )
            else:
                feedback.pushInfo(self.tr(f"Banco '{new_db_name}' já existe. Usando modo Append (anexando dados)."))
        else:
            feedback.pushInfo(f"Criando banco '{new_db_name}' no servidor '{server_name}'...")
            ShpToPostGISLogic.create_database(server_params, new_db_name)

        # 4. Importar cada SHP
        total = len(shp_files)
        success_layers = [] # Tuplas (uri, name)
        
        for i, shp in enumerate(shp_files):
            if feedback.isCanceled():
                break
            
            feedback.setProgress(int((i / total) * 100))
            layer_name = os.path.basename(shp)
            feedback.pushInfo(f"Importando ({i+1}/{total}): {layer_name}...")
            
            # Precisamos do layer_name sanitizado para carregar depois
            original_name = os.path.splitext(os.path.basename(shp))[0]
            sanitized_name = ShpToPostGISLogic.sanitize_table_name(original_name)
            
            imported = ShpToPostGISLogic.import_shp_to_postgis(shp, server_params, new_db_name, feedback)
            if imported:
                # Criar URI para carregar depois
                from qgis.core import QgsDataSourceUri
                uri = QgsDataSourceUri()
                uri.setConnection(server_params["host"], str(server_params["port"]), new_db_name, server_params["user"], server_params["password"])
                uri.setDataSource("public", sanitized_name, "geom")
                success_layers.append((uri.uri(), original_name))

        # 5. Apenas guardar os dados para carregar no postProcess (Thread Principal)
        self.success_layers = success_layers
        self.db_name_to_load = new_db_name
        self.should_load = load_layers

        feedback.setProgress(100)
        feedback.pushInfo("🎯 Conversão concluída na Task. Organizando camadas na UI...")

        return {"RESULT": f"Banco '{new_db_name}' criado com {len(success_layers)} camadas."}

    def postProcessAlgorithm(self, context, feedback):
        """
        Executado na Thread Principal após o processAlgorithm.
        Ideal para manipulações de UI e de Árvore de Camadas (TOC).
        """
        if not hasattr(self, 'should_load') or not self.should_load or not self.success_layers:
            return {}

        from qgis.core import QgsVectorLayer, QgsWkbTypes, QgsProject, QgsApplication
        
        project = context.project()
        if not project:
            project = QgsProject.instance()

        feedback.pushInfo(self.tr("📥 Carregando camadas no projeto (Thread Principal)..."))
        
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

        # Bloquear sinais para performance e evitar refresh circular
        project.blockSignals(True)
        try:
            for uri_str, name in self.success_layers:
                layer = QgsVectorLayer(uri_str, name, "postgres")
                if layer.isValid():
                    layers_to_add.append(layer)
                    
                    geometry_type = QgsWkbTypes.geometryType(layer.wkbType())
                    target_group = groups.get(geometry_type, groups[None])
                    layer_group_map.append((layer, target_group))
                
                QgsApplication.processEvents()

            # Adicionar ao projeto (sem root automaticamente)
            project.addMapLayers(layers_to_add, False)
            
            # Mover para grupos
            for layer, group in layer_group_map:
                group.addLayer(layer)
                
        finally:
            project.blockSignals(False)

        # Limpar grupos vazios
        for group in list(groups.values()):
            if not group.children():
                main_group.removeChildNode(group)

        feedback.pushInfo("✅ Camadas organizadas com sucesso!")
        return {}

    def createInstance(self):
        return ShpToPostGISAlgorithm()
