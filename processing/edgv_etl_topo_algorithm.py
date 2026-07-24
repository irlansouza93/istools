# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - EDGV ETL Topo Algorithm
                                 A QGIS plugin
 Professional vectorization toolkit for QGIS
                              -------------------
        begin                : 2026-03-20
        git sha              : $Format:%H$
        copyright            : (C) 2025 by Irlan Souza, 2o Sgt Brazilian Army
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
import subprocess
from datetime import datetime
from typing import Any, Optional

from qgis.PyQt.QtCore import QCoreApplication, QSettings, pyqtSignal
from qgis.PyQt.QtWidgets import QComboBox, QHBoxLayout, QWidget
from qgis.core import (
    QgsMessageLog,
    Qgis,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingOutputString,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterMatrix,
)
from processing.gui.wrappers import WidgetWrapper

from ..converter_logic import EDGVETLConverter
from .. import database_manager_logic as logic


_WIDGET_SELECTION_CACHE = {}


class ServerDatabaseSelectorWidget(QWidget):
    changed = pyqtSignal()

    def __init__(self, parameter_name, parent=None):
        super().__init__(parent)
        self.parameter_name = parameter_name
        self.server_combo = QComboBox()
        self.db_combo = QComboBox()
        self.server_combo.setMinimumWidth(180)
        self.db_combo.setMinimumWidth(220)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.server_combo, 1)
        layout.addWidget(self.db_combo, 1)

        self.server_combo.currentIndexChanged.connect(self._on_server_changed)
        self.db_combo.currentIndexChanged.connect(self._on_db_changed)

        self._load_servers()
        cached = self._load_cached_value()
        if cached:
            self.set_value(cached)
        else:
            self._refresh_databases()
            self._persist_current_value()

    def _settings_key(self):
        return f"ISTools/edgv_etl_topo/{self.parameter_name}"

    def _load_servers(self):
        servers = logic.get_configured_servers()
        self.server_combo.clear()
        if servers:
            self.server_combo.addItems(servers)
        else:
            self.server_combo.addItem("Nenhum servidor configurado")

    def _refresh_databases(self, preferred_db=""):
        server_name = self.server_combo.currentText().strip()
        databases = []
        if server_name and server_name != "Nenhum servidor configurado":
            try:
                databases = logic.get_server_databases(server_name, refresh_if_missing=True)
            except Exception:
                databases = []

        current = preferred_db or self.db_combo.currentText().strip()
        self.db_combo.blockSignals(True)
        self.db_combo.clear()
        self.db_combo.addItems(databases)
        if current and current in databases:
            self.db_combo.setCurrentIndex(self.db_combo.findText(current))
        elif databases:
            self.db_combo.setCurrentIndex(0)
        self.db_combo.blockSignals(False)

    def _persist_current_value(self):
        serialized = self.serialized_value()
        _WIDGET_SELECTION_CACHE[self.parameter_name] = serialized
        QSettings().setValue(self._settings_key(), serialized)
        QgsMessageLog.logMessage(
            f"ETL widget persist [{self.parameter_name}] -> {serialized or '<vazio>'}",
            "ISTools",
            Qgis.Info,
        )

    def _load_cached_value(self):
        cached = _WIDGET_SELECTION_CACHE.get(self.parameter_name, "")
        if cached:
            return cached
        return QSettings().value(self._settings_key(), "")

    def _on_server_changed(self, *args):
        self._refresh_databases()
        self._persist_current_value()
        self.changed.emit()

    def _on_db_changed(self, *args):
        self._persist_current_value()
        self.changed.emit()

    def serialized_value(self):
        server_name = self.server_combo.currentText().strip()
        db_name = self.db_combo.currentText().strip()
        if not server_name or server_name == "Nenhum servidor configurado" or not db_name:
            return ""
        return f"{server_name}|{db_name}"

    def value(self):
        serialized = self.serialized_value()
        QgsMessageLog.logMessage(
            f"ETL widget value [{self.parameter_name}] -> {serialized or '<vazio>'}",
            "ISTools",
            Qgis.Info,
        )
        return [serialized] if serialized else []

    def set_value(self, value):
        serialized = ""
        if isinstance(value, (list, tuple)):
            serialized = str(value[0]) if value else ""
        else:
            serialized = str(value or "")

        if not serialized:
            return

        server_name = ""
        db_name = ""
        if "|" in serialized:
            server_name, db_name = serialized.split("|", 1)
        else:
            server_name = serialized

        if server_name:
            idx = self.server_combo.findText(server_name)
            if idx >= 0:
                self.server_combo.setCurrentIndex(idx)
        self._refresh_databases(preferred_db=db_name)
        self._persist_current_value()


class _ServerDatabaseWidgetWrapper(WidgetWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selector = None

    def createWidget(self):
        self.selector = ServerDatabaseSelectorWidget(self.parameterDefinition().name())
        self.selector.changed.connect(lambda: self.widgetValueHasChanged.emit(self))
        return self.selector

    def setValue(self, value):
        if self.selector is not None:
            self.selector.set_value(value)

    def value(self):
        if self.selector is None:
            return []
        return self.selector.value()


class SourceConnectionWidgetWrapper(_ServerDatabaseWidgetWrapper):
    pass


class TargetConnectionWidgetWrapper(_ServerDatabaseWidgetWrapper):
    pass


class EDGVETLTopoAlgorithm(QgsProcessingAlgorithm):
    """Algoritmo ETL entre EDGV 3.0 v1.1.6 e EDGV Topo 1.4.5."""

    JSON_PATH = "JSON_PATH"
    SOURCE_CONN = "SOURCE_CONN"
    TARGET_CONN = "TARGET_CONN"
    OUTPUT_MODE = "OUTPUT_MODE"
    OUTPUT_SQL = "OUTPUT_SQL"
    OUTPUT_STATUS = "OUTPUT_STATUS"

    MODE_EXISTING_DB = 0
    MODE_SQL_FILE = 1
    MODE_CREATE_DB = 2

    def name(self) -> str:
        return "edgv_etl_topo"

    def displayName(self) -> str:
        return self.tr("Converter EDGV 3.0 v1.1.6 para Topo v1.4.5")

    def group(self) -> str:
        return self.tr("Ferramentas EDGV")

    def groupId(self) -> str:
        return "ferramentas_edgv"

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("Processing", string)

    def shortHelpString(self) -> str:
        return (
            "Conversor ETL para migracao entre EDGV 3.0 v1.1.6 e EDGV Topo v1.4.5.\n\n"
            "Fluxos disponiveis:\n"
            "- Carregar em banco Topo existente;\n"
            "- Gerar arquivo SQL completo para restauracao posterior;\n"
            "- Criar novo banco Topo 1.4.5 a partir dos scripts oficiais e carregar os dados.\n\n"
            "Cada conexao exibe servidor e banco no mesmo controle, com atualizacao automatica da lista de bancos.\n\n"
            "Autor: Irlan Souza\n"
            "Email: irlansouza193@gmail.com\n"
            "GitHub: https://github.com/irlansouza93\n"
            "Site Oficial: https://irlansouza93.github.io/istools-website/"
        )

    def helpUrl(self) -> str:
        return "https://irlansouza93.github.io/istools-website/"

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):
        default_json = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "data", "edgv_30_to_topo_145.json")
        )

        source_default = self._default_connection_value()
        source_param = QgsProcessingParameterMatrix(
            self.SOURCE_CONN,
            self.tr("Origem (Servidor e Banco)"),
            defaultValue=[source_default] if source_default else [],
            optional=True,
        )
        source_param.setMetadata({"widget_wrapper": {"class": SourceConnectionWidgetWrapper}})
        self.addParameter(source_param)

        target_default = self._default_connection_value()
        target_param = QgsProcessingParameterMatrix(
            self.TARGET_CONN,
            self.tr("Destino (Servidor e Banco)"),
            defaultValue=[target_default] if target_default else [],
            optional=True,
        )
        target_param.setMetadata({"widget_wrapper": {"class": TargetConnectionWidgetWrapper}})
        self.addParameter(target_param)

        self.addParameter(
            QgsProcessingParameterEnum(
                self.OUTPUT_MODE,
                self.tr("Resultado Final da Conversao"),
                options=[
                    self.tr("Carregar em banco Topo existente"),
                    self.tr("Gerar arquivo SQL para restauracao"),
                    self.tr("Criar novo banco Topo 1.4.5 e carregar"),
                ],
                defaultValue=self.MODE_EXISTING_DB,
            )
        )

        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT_SQL,
                self.tr("Arquivo SQL de saida (modo Gerar SQL)"),
                fileFilter="SQL Files (*.sql)",
                optional=True,
            )
        )

        param_json = QgsProcessingParameterFile(
            self.JSON_PATH,
            self.tr("Arquivo JSON de Mapeamento"),
            extension="json",
            defaultValue=default_json,
        )
        param_json.setFlags(param_json.flags() | QgsProcessingParameterFile.Flag.FlagAdvanced)
        self.addParameter(param_json)

        self.addOutput(QgsProcessingOutputString(self.OUTPUT_STATUS, self.tr("Status Final")))

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:
        json_path = self.parameterAsFile(parameters, self.JSON_PATH, context)
        output_mode = self.parameterAsInt(parameters, self.OUTPUT_MODE, context)
        output_sql = self.parameterAsFileOutput(parameters, self.OUTPUT_SQL, context)

        source_conn_name, source_db_name = self._parse_connection_matrix(
            self.parameterAsMatrix(parameters, self.SOURCE_CONN, context),
            self.SOURCE_CONN,
        )
        target_conn_name, target_db_name = self._parse_connection_matrix(
            self.parameterAsMatrix(parameters, self.TARGET_CONN, context),
            self.TARGET_CONN,
        )

        if not source_conn_name:
            raise QgsProcessingException(self.tr("Selecione o servidor de origem."))
        if not source_db_name:
            raise QgsProcessingException(self.tr("Selecione o banco de origem."))

        feedback.pushInfo("=== ISTools - Conversor ETL Topo ===")
        feedback.pushInfo(f"Servidor de origem: {source_conn_name}")
        feedback.pushInfo(f"Banco de origem: {source_db_name}")

        source_params = logic.get_server_connection_params(source_conn_name, source_db_name)
        target_params = None
        temp_db_name = None

        try:
            if output_mode == self.MODE_EXISTING_DB:
                if not target_conn_name:
                    raise QgsProcessingException(self.tr("Selecione o servidor de destino."))
                if not target_db_name:
                    raise QgsProcessingException(self.tr("Selecione o banco Topo de destino."))
                target_params = logic.get_server_connection_params(target_conn_name, target_db_name)
                feedback.pushInfo(f"Modo: banco existente -> {target_conn_name}/{target_db_name}")

            elif output_mode == self.MODE_CREATE_DB:
                if not target_conn_name:
                    raise QgsProcessingException(self.tr("Selecione o servidor onde o novo banco sera criado."))
                if not target_db_name:
                    raise QgsProcessingException(self.tr("Informe ou selecione o nome do novo banco Topo."))
                feedback.pushInfo(f"Criando banco Topo 1.4.5: {target_conn_name}/{target_db_name}")
                target_params = logic.create_topo_database(target_conn_name, target_db_name, allow_existing=False)
                feedback.pushInfo("Estrutura Topo 1.4.5 criada com sucesso.")

            elif output_mode == self.MODE_SQL_FILE:
                if not target_conn_name:
                    raise QgsProcessingException(self.tr("Selecione o servidor temporario para gerar o SQL."))
                if not output_sql:
                    raise QgsProcessingException(self.tr("Informe o caminho do arquivo SQL de saida."))
                temp_db_name = self._generate_temp_db_name()
                feedback.pushInfo(f"Criando banco temporario para exportacao SQL: {temp_db_name}")
                target_params = logic.create_topo_database(target_conn_name, temp_db_name, allow_existing=False)
                feedback.pushInfo("Estrutura temporaria Topo 1.4.5 criada com sucesso.")

            converter = EDGVETLConverter(json_path, source_params, target_params, feedback=feedback)
            converter.schema_A = "edgv"
            converter.schema_B = "edgv"

            success = converter.run_etl()
            if not success:
                raise QgsProcessingException(self.tr("A conversao falhou. Consulte os logs do algoritmo."))

            if output_mode == self.MODE_SQL_FILE:
                feedback.pushInfo(f"Gerando arquivo SQL final: {output_sql}")
                self._dump_database_to_sql(target_params, temp_db_name, output_sql)
                feedback.pushInfo("Arquivo SQL gerado com sucesso.")
                status = self.tr(f"OK: SQL gerado em {output_sql}")
            elif output_mode == self.MODE_CREATE_DB:
                status = self.tr(f"OK: banco {target_db_name} criado e carregado com {converter.db_target_counts} feicoes.")
            else:
                status = self.tr(f"OK: {converter.db_target_counts} feicoes migradas para {target_db_name}.")

            return {self.OUTPUT_STATUS: status}

        except Exception as e:
            raise QgsProcessingException(self.tr(f"Erro Fatal: {str(e)}"))
        finally:
            if output_mode == self.MODE_SQL_FILE and temp_db_name and target_conn_name:
                try:
                    feedback.pushInfo(f"Removendo banco temporario: {temp_db_name}")
                    admin_params = logic.get_server_connection_params(target_conn_name)
                    logic.drop_database(admin_params, temp_db_name, if_exists=True)
                    logic.refresh_server_databases(target_conn_name)
                except Exception as cleanup_error:
                    feedback.reportError(self.tr(f"Aviso: nao foi possivel remover o banco temporario {temp_db_name}: {cleanup_error}"))

    def _parse_connection_matrix(self, value, param_name):
        serialized = ""
        if isinstance(value, (list, tuple)) and value:
            serialized = str(value[0]).strip()
        elif value:
            serialized = str(value).strip()

        if not serialized:
            serialized = _WIDGET_SELECTION_CACHE.get(param_name, "")
        if not serialized:
            serialized = QSettings().value(f"ISTools/edgv_etl_topo/{param_name}", "")

        if not serialized:
            return "", ""
        if "|" not in serialized:
            return serialized.strip(), ""
        server_name, db_name = serialized.split("|", 1)
        return server_name.strip(), db_name.strip()

    def _default_connection_value(self):
        servers = logic.get_configured_servers()
        if not servers:
            return ""
        server_name = servers[0]
        try:
            databases = logic.get_server_databases(server_name, refresh_if_missing=True)
        except Exception:
            databases = []
        if not databases:
            return ""
        return f"{server_name}|{databases[0]}"

    def _generate_temp_db_name(self) -> str:
        return f"istools_topo_tmp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def _get_pg_dump_executable(self) -> str:
        bin_dir = QSettings().value("ISTools/postgis_bin_path", "")
        executable = "pg_dump.exe" if os.name == "nt" else "pg_dump"
        if bin_dir:
            candidate = os.path.join(bin_dir, executable)
            if os.path.exists(candidate):
                return candidate
        return executable

    def _dump_database_to_sql(self, params, db_name, output_sql):
        env = os.environ.copy()
        if params.get("password"):
            env["PGPASSWORD"] = params["password"]
        cmd = [
            self._get_pg_dump_executable(),
            "-h", params["host"],
            "-p", str(params["port"]),
            "-U", params["user"],
            "-f", output_sql,
            db_name,
        ]
        kwargs = {
            "env": env,
            "capture_output": True,
            "text": True,
            "check": False,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(cmd, **kwargs)
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip() or "pg_dump falhou sem mensagem detalhada."
            raise QgsProcessingException(self.tr(f"Falha ao gerar SQL via pg_dump: {error}"))

    def createInstance(self):
        return EDGVETLTopoAlgorithm()
