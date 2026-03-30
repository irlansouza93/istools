# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - EDGV ETL Topo Algorithm
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
"""

from typing import Any, Optional
import os
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFile,
    QgsProcessingParameterEnum,
    QgsProcessingParameterString,
    QgsProcessing,
    QgsProcessingOutputString,
    QgsDataSourceUri,
    QgsApplication,
    QgsProviderRegistry,
    QgsSettings
)

from ..converter_logic import EDGVETLConverter


class EDGVETLTopoAlgorithm(QgsProcessingAlgorithm):
    """
    Algoritmo de conversão entre EDGV 3.0 e EDGV Topo 1.4.5.
    Segue o padrão oficial de algoritmos do ISTools.
    """

    # Constants used to refer to parameters and outputs.
    JSON_PATH = "JSON_PATH"
    SOURCE_CONN = "SOURCE_CONN"
    SOURCE_DB = "SOURCE_DB"
    TARGET_CONN = "TARGET_CONN"
    TARGET_DB = "TARGET_DB"
    OUTPUT_STATUS = "OUTPUT_STATUS"

    def name(self) -> str:
        return "edgv_etl_topo"

    def displayName(self) -> str:
        return self.tr("Converter EDGV 3.0 v1.1.6 para Topo v1.4.5")

    def group(self) -> str:
        return self.tr("Ferramentas EDGV")

    def groupId(self) -> str:
        return "ferramentas_edgv"

    def shortHelpString(self) -> str:
        return (
            "Conversor ETL Profissional para migração de dados entre **EDGV 3.0 v1.1.6** (PostGIS) e **EDGV Topo v1.4.5**.\n\n"
            "<b>Parâmetros:</b>\n"
            "- <b>Servidor de Origem/Destino:</b> Servidores PostgreSQL configurados via menu ISTools.\n"
            "- <b>Banco de Dados:</b> Seleção da base de dados fonte e alvo.\n"
            "- <b>Arquivo JSON:</b> Dicionário oficial de mapeamento lógico (Avançado).\n\n"
            "<b>Funcionalidades:</b>\n"
            "- Mapeamento Matricial N-to-N inteligente.\n"
            "- Auditoria geométrica (Incompatibilidade Ponto -> Linha).\n"
            "- Resgate semântico de feições anteriormente filtradas (Religiosas, Cemitérios, Canais).\n"
            "- Trava Anticlonagem definitiva baseada em PK estável.\n\n"
            "<b>Autor:</b> Irlan Souza\n"
            "<b>Email:</b> <a href=\"mailto:irlansouza193@gmail.com\">irlansouza193@gmail.com</a>\n"
            "<b>GitHub:</b> <a href=\"https://github.com/irlansouza93\">https://github.com/irlansouza93</a>\n"
            "<b>Versão:</b> 20.0\n\n"
            "<b>🌐 <a href=\"https://irlansouza93.github.io/istools-website/\">🚀VISITE NOSSO SITE OFICIAL - CLIQUE AQUI! 🚀</a></b>"
        )

    def helpUrl(self) -> str:
        return "https://irlansouza93.github.io/istools-website/"

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("Processing", string)

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):
        """
        Define os inputs e outputs do algoritmo buscando servidores e bancos no QgsSettings.
        """
        default_json = os.path.normpath(os.path.join(
            os.path.dirname(__file__), "..", "data", "edgv_30_to_topo_145.json"
        ))

        # Buscar servidores no QgsSettings
        settings = QgsSettings()
        settings.beginGroup("PostgreSQL/servers")
        servers = settings.childGroups()
        
        # Coletar todos os bancos de dados encontrados em todos os servidores
        all_databases = set()
        for s in servers:
            dbs_str = settings.value(f"{s}/databases", "")
            if dbs_str:
                for db in dbs_str.split(","):
                    all_databases.add(db)
        settings.endGroup()
        
        db_list = sorted(list(all_databases))
        if not db_list:
            db_list = ["edgv_300", "edgv_topo", "postgres"]

        if not servers:
            servers = [self.tr("Nenhum servidor configurado (Use o Menu ISTools)")]

        # 1. Servidor de Origem
        self.addParameter(
            QgsProcessingParameterEnum(
                self.SOURCE_CONN,
                self.tr("Servidor de Origem"),
                options=servers,
                defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.SOURCE_DB,
                self.tr("Banco de Dados de Origem"),
                options=db_list,
                defaultValue=0
            )
        )

        # 2. Servidor de Destino
        self.addParameter(
            QgsProcessingParameterEnum(
                self.TARGET_CONN,
                self.tr("Servidor de Destino"),
                options=servers,
                defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.TARGET_DB,
                self.tr("Banco de Dados de Destino"),
                options=db_list,
                defaultValue=0
            )
        )

        # 3. Mapeamento JSON (Avançado)
        param_json = QgsProcessingParameterFile(
            self.JSON_PATH,
            self.tr("Arquivo JSON de Mapeamento"),
            extension="json",
            defaultValue=default_json
        )
        param_json.setFlags(param_json.flags() | QgsProcessingParameterFile.Flag.FlagAdvanced)
        self.addParameter(param_json)

        self.addOutput(
            QgsProcessingOutputString(self.OUTPUT_STATUS, self.tr("Status Final"))
        )

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback
    ) -> dict[str, Any]:
        """
        Execução principal do ETL resolvendo parâmetros via QSettings.
        """
        json_path = self.parameterAsFile(parameters, self.JSON_PATH, context)
        
        # Obter índices selecionados
        source_idx = self.parameterAsEnum(parameters, self.SOURCE_CONN, context)
        target_idx = self.parameterAsEnum(parameters, self.TARGET_CONN, context)
        
        source_db_idx = self.parameterAsEnum(parameters, self.SOURCE_DB, context)
        target_db_idx = self.parameterAsEnum(parameters, self.TARGET_DB, context)

        # Lista de servidores e bancos para resolver os nomes pelos índices
        settings = QgsSettings()
        settings.beginGroup("PostgreSQL/servers")
        servers = settings.childGroups()
        
        all_databases = set()
        for s in servers:
            dbs_str = settings.value(f"{s}/databases", "")
            if dbs_str:
                for db in dbs_str.split(","):
                    all_databases.add(db)
        settings.endGroup()
        
        db_list = sorted(list(all_databases))
        if not db_list:
            db_list = ["edgv_300", "edgv_topo", "postgres"]

        if not servers:
             raise QgsProcessingException(self.tr("Nenhum servidor configurado. Use o menu ISTools > Banco de Dados > Configurar Servidores."))

        source_conn_name = servers[source_idx]
        target_conn_name = servers[target_idx]
        
        source_db_name = db_list[source_db_idx]
        target_db_name = db_list[target_db_idx]

        # Resolver parâmetros de conexão
        source_params = self._resolve_qsettings_to_params(source_conn_name, source_db_name)
        target_params = self._resolve_qsettings_to_params(target_conn_name, target_db_name)

        feedback.pushInfo(f"Conectando Origem: {source_params['host']} / {source_params['dbname']}")
        feedback.pushInfo(f"Conectando Destino: {target_params['host']} / {target_params['dbname']}")

        feedback.pushInfo(f"\n=== ISTools - Conversor ETL Geoinformação (v11.4.1) ===")
        feedback.pushInfo(f"ESPECIFICAÇÕES: EDGV 3.0 (v1.1.6) -> Topo (v1.4.5)")
        feedback.pushInfo(f"Autor: Irlan Souza")
        feedback.pushInfo(f"Email: irlansouza193@gmail.com")
        feedback.pushInfo(f"GitHub: https://github.com/irlansouza93")
        feedback.pushInfo(f"Site Oficial: https://irlansouza93.github.io/istools-website/")
        feedback.pushInfo(f"🌐 🚀 VISITE NOSSO SITE OFICIAL E DESCUBRA NOVAS FERRAMENTAS! 🚀")
        feedback.pushInfo(f"Versão: 20.0 (Proteção Anticlonagem PK)")
        feedback.pushInfo(f"==========================================================\n")

        try:
            converter = EDGVETLConverter(
                json_path, 
                source_params, 
                target_params, 
                feedback=feedback
            )
            
            # Forçar os esquemas como 'edgv'
            converter.schema_A = "edgv"
            converter.schema_B = "edgv"
            
            success = converter.run_etl()
            
            if not success:
                 raise QgsProcessingException(self.tr("A conversão falhou. Consulte os logs."))

            return {self.OUTPUT_STATUS: self.tr(f"OK: {converter.db_target_counts} feições migradas.")}

        except Exception as e:
            raise QgsProcessingException(self.tr(f"Erro Fatal: {str(e)}"))

    def _resolve_qsettings_to_params(self, conn_name: str, db_name: str) -> dict[str, Any]:
        """
        Lê os parâmetros do QgsSettings (padrão DSGTools) e injeta o banco de dados.
        """
        settings = QgsSettings()
        settings.beginGroup(f"PostgreSQL/servers/{conn_name}")
        
        host = settings.value("host")
        port = settings.value("port", "5432")
        user = settings.value("username")
        password = settings.value("password")
        settings.endGroup()

        if not host or not user:
            raise QgsProcessingException(self.tr(f"Configuração incompleta para o servidor: {conn_name}"))

        return {
            "host": host,
            "port": port,
            "dbname": db_name,
            "user": user,
            "password": password
        }
            
    def createInstance(self):
        return EDGVETLTopoAlgorithm()
