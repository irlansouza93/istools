# -*- coding: utf-8 -*-
"""
database_manager.py — Interface do Gerenciador de Banco ISTools.

Toda lógica de banco (conexão, queries) é delegada a database_manager_logic.py.
Este módulo cuida exclusivamente da camada de apresentação (PyQt/QGIS).
"""
import os
import subprocess
import datetime
from istools import database_manager_logic as logic
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QComboBox, QPushButton, QFileDialog, QLineEdit,
    QProgressBar, QMessageBox, QGroupBox, QRadioButton,
    QTableWidget, QTableWidgetItem, QTextEdit, QButtonGroup,
    QListWidget, QAbstractItemView, QHeaderView
)
from qgis.PyQt.QtCore import Qt, QSettings, QThread, pyqtSignal, QCoreApplication
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsMessageLog, Qgis, QgsApplication, QgsTask


class DatabaseManagerDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("ISTools - Gerenciador de Banco de Dados")
        self.setMinimumSize(750, 600)

        self.layout = QVBoxLayout(self)
        # --- Área de Conexão Compacta ---
        self.conn_group = QGroupBox("Conexão ao PostGIS")
        conn_layout = QVBoxLayout(self.conn_group)
        conn_layout.setContentsMargins(5, 5, 5, 5)
        conn_layout.setSpacing(2)
        
        # Linha 1: Servidor
        server_row = QHBoxLayout()
        self.combo_servers = QComboBox()
        self.btn_refresh_servers = QPushButton("Atualizar")
        self.btn_config_bin = QPushButton("Configurar Ferramentas")
        self.btn_config_bin.setToolTip("Configurar pg_dump / psql")
        
        server_row.addWidget(QLabel("Servidor:"))
        server_row.addWidget(self.combo_servers, 2)
        server_row.addWidget(self.btn_refresh_servers)
        server_row.addWidget(self.btn_config_bin)
        conn_layout.addLayout(server_row)
        
        # Linha 2: Banco (Global)
        db_row = QHBoxLayout()
        self.combo_dbs = QComboBox()
        self.btn_refresh_dbs = QPushButton("Listar Bancos")
        db_row.addWidget(QLabel("Banco Principal:"))
        db_row.addWidget(self.combo_dbs, 2)
        db_row.addWidget(self.btn_refresh_dbs)
        conn_layout.addLayout(db_row)
        
        self.layout.addWidget(self.conn_group)

        # --- Abas ---
        self.tabs = QTabWidget()
        self.tab_reset = QWidget()
        self.tab_clone = QWidget()
        self.tab_merge = QWidget()
        self.tab_delete = QWidget()
        self.tab_backup = QWidget()
        self.tab_restore = QWidget()
        self.tab_create = QWidget()
        self.tab_help = QWidget()

        self.tabs.addTab(self.tab_reset, "Limpar Dados")
        self.tabs.addTab(self.tab_clone, "Clonar")
        self.tabs.addTab(self.tab_merge, "Unir Bancos")
        self.tabs.addTab(self.tab_delete, "Excluir")
        self.tabs.addTab(self.tab_backup, "Backup")
        self.tabs.addTab(self.tab_restore, "Restaurar")
        self.tabs.addTab(self.tab_create, "Criar (Script)")
        self.tabs.addTab(self.tab_help, "Ajuda")

        self.layout.addWidget(self.tabs)

        # --- Progresso ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar)

        self.btn_close = QPushButton("Fechar")
        self.layout.addWidget(self.btn_close, 0, Qt.AlignRight)

        # Inicializar abas
        self._init_tab_reset()
        self._init_tab_clone()
        self._init_tab_merge()
        self._init_tab_delete()
        self._init_tab_backup()
        self._init_tab_restore()
        self._init_tab_create()
        self._init_tab_help()

        # Conexões globais
        self.btn_refresh_servers.clicked.connect(self.populate_servers)
        self.btn_refresh_dbs.clicked.connect(self.populate_databases)
        self.btn_config_bin.clicked.connect(self.configure_bin_path)
        self.btn_close.clicked.connect(self.close)
        self.combo_dbs.currentTextChanged.connect(self.populate_reset_schemas)
        self.combo_reset_schemas.currentIndexChanged.connect(self.update_reset_preview)

        # Carga inicial
        self.populate_servers()

    # ================================================================
    #  UTILITÁRIOS GLOBAIS
    # ================================================================
    def tr(self, msg):
        return QCoreApplication.translate("DatabaseManagerDialog", msg)

    def get_bin_path(self):
        return QSettings().value("ISTools/postgis_bin_path", "")

    def configure_bin_path(self):
        curr = self.get_bin_path()
        path = QFileDialog.getExistingDirectory(
            self, "Selecionar pasta com pg_dump e psql", curr)
        if path:
            # Validar se os arquivos existem e tentar pegar a versão
            pg_dump = os.path.join(path, "pg_dump.exe") if os.name == 'nt' else os.path.join(path, "pg_dump")
            if not os.path.exists(pg_dump):
                QMessageBox.warning(self, "Aviso", 
                    f"O arquivo pg_dump não foi encontrado na pasta selecionada.\n\n"
                    "O Backup e Restauração podem não funcionar.")
            else:
                try:
                    ver = subprocess.check_output([pg_dump, "--version"], 
                        universal_newlines=True, 
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                    QSettings().setValue("ISTools/postgis_bin_path", path)
                    QMessageBox.information(self, "Sucesso", 
                        f"Configuração salva!\nVersão detectada: {ver.strip()}")
                except Exception as e:
                    QSettings().setValue("ISTools/postgis_bin_path", path)
                    QMessageBox.warning(self, "Aviso", 
                        f"Caminho salvo, mas não conseguimos validar a versão: {e}")

    def populate_servers(self):
        self.combo_servers.clear()
        settings = QSettings()
        settings.beginGroup("PostgreSQL/servers")
        self.combo_servers.addItems(settings.childGroups())
        settings.endGroup()

    def get_selected_server_params(self):
        name = self.combo_servers.currentText()
        if not name:
            return None
        settings = QSettings()
        settings.beginGroup(f"PostgreSQL/servers/{name}")
        params = {
            "host": settings.value("host", "localhost"),
            "port": settings.value("port", "5432"),
            "user": settings.value("username", "postgres"),
            "password": settings.value("password", ""),
            "authcfg": settings.value("authcfg", ""),
        }
        settings.endGroup()
        return params

    def populate_databases(self):
        """Lista bancos via módulo lógico e atualiza todas as abas."""
        params = self.get_selected_server_params()
        if not params:
            return
        self.combo_dbs.clear()
        try:
            dbs = logic.list_databases(params)
            self.combo_dbs.addItems(dbs)
        except Exception as e:
            QMessageBox.warning(self, "Erro de Conexão",
                f"Não foi possível listar os bancos de dados.\n\n"
                f"Verifique se o servidor está ativo e as credenciais estão corretas.\n\n"
                f"Detalhe técnico: {e}")
            QgsMessageLog.logMessage(f"populate_databases: {e}", "ISTools", Qgis.Warning)
        finally:
            self.populate_reset_schemas()
            self.populate_merge_list()

    # ================================================================
    #  ABA: LIMPAR DADOS (RESET)
    # ================================================================
    def populate_reset_schemas(self):
        db_name = self.combo_dbs.currentText()
        if not db_name:
            if hasattr(self, 'combo_reset_schemas'):
                self.combo_reset_schemas.clear()
            return
        params = self.get_selected_server_params()
        if not params:
            return
        try:
            schemas = logic.list_user_schemas(params, db_name)
            self.combo_reset_schemas.blockSignals(True)
            self.combo_reset_schemas.clear()
            for name in schemas:
                try:
                    is_spat = len(logic.list_spatial_tables(params, db_name, name)) > 0
                except Exception:
                    is_spat = False
                display = f"{name} (camadas espaciais)" if is_spat else name
                self.combo_reset_schemas.addItem(display, name)
            self.combo_reset_schemas.blockSignals(False)
            self.update_reset_preview()
        except Exception as e:
            self.combo_reset_schemas.clear()
            QgsMessageLog.logMessage(f"populate_reset_schemas: {e}", "ISTools", Qgis.Warning)

    def _init_tab_reset(self):
        layout = QVBoxLayout(self.tab_reset)
        info = QLabel(
            "Remove os registros (feições) das tabelas do grupo selecionado.\n"
            "A estrutura do banco (tabelas, domínios, regras) é preservada."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addWidget(QLabel("Grupo de tabelas para limpar:"))
        self.combo_reset_schemas = QComboBox()
        layout.addWidget(self.combo_reset_schemas)

        mode_group = QGroupBox("Modo de Limpeza")
        mode_layout = QVBoxLayout(mode_group)
        self.radio_reset_all = QRadioButton("Limpar todas as tabelas do grupo")
        self.radio_reset_geo = QRadioButton("Limpar apenas camadas espaciais")
        self.radio_reset_all.setChecked(True)
        mode_layout.addWidget(self.radio_reset_all)
        mode_layout.addWidget(self.radio_reset_geo)
        layout.addWidget(mode_group)

        self.radio_reset_all.toggled.connect(self.update_reset_preview)

        self.lbl_reset_preview = QLabel("Aguardando seleção...")
        self.lbl_reset_preview.setStyleSheet("color: #555; font-style: italic; padding: 4px;")
        layout.addWidget(self.lbl_reset_preview)

        self.btn_run_reset = QPushButton("LIMPAR DADOS AGORA")
        self.btn_run_reset.setStyleSheet(
            "background-color: #f44336; color: white; font-weight: bold; padding: 10px;")
        self.btn_run_reset.clicked.connect(self.run_reset)
        layout.addWidget(self.btn_run_reset)
        layout.addStretch()

    def update_reset_preview(self):
        db_name = self.combo_dbs.currentText()
        schema_name = self.combo_reset_schemas.currentData()
        if not db_name or not schema_name:
            self.lbl_reset_preview.setText("Selecione um banco e um grupo de tabelas.")
            return
        params = self.get_selected_server_params()
        mode = "all" if self.radio_reset_all.isChecked() else "spatial"
        try:
            count = logic.count_tables_for_reset(params, db_name, schema_name, mode)
            modo_txt = "todas as tabelas" if mode == "all" else "camadas espaciais"
            self.lbl_reset_preview.setText(
                f"Resumo: {count} tabelas ({modo_txt}) serão afetadas no grupo '{schema_name}'.")
        except Exception as e:
            self.lbl_reset_preview.setText(f"Não foi possível gerar o resumo: {e}")
            QgsMessageLog.logMessage(f"update_reset_preview: {e}", "ISTools", Qgis.Warning)

    def run_reset(self):
        db_name = self.combo_dbs.currentText()
        schema_name = self.combo_reset_schemas.currentData()
        if not db_name or not schema_name:
            QMessageBox.warning(self, "Aviso", "Selecione um banco e um grupo de tabelas.")
            return
        mode = "all" if self.radio_reset_all.isChecked() else "spatial"
        mode_text = "TODAS AS TABELAS" if mode == "all" else "APENAS CAMADAS ESPACIAIS"

        msg = (f"Você está prestes a APAGAR {mode_text} do grupo '{schema_name}' "
               f"no banco '{db_name}'.\n\n"
               "Os registros serão excluídos permanentemente, mas a estrutura "
               "(tabelas, domínios, regras) será mantida.\n\n"
               "Deseja continuar?")

        if QMessageBox.question(self, "Confirmação", msg,
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        params = self.get_selected_server_params()
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        task = ResetDatabaseTask(params, db_name, schema_name, mode)
        task.taskCompleted.connect(lambda: self.on_reset_finished(True, task))
        task.taskTerminated.connect(lambda: self.on_reset_finished(False, task))
        QgsApplication.taskManager().addTask(task)

    def on_reset_finished(self, success, task):
        self.progress_bar.setVisible(False)
        if success:
            QMessageBox.information(self, "Concluído",
                f"{task.count} tabelas foram limpas no grupo '{task.schema_name}'.")
            self.update_reset_preview()
        else:
            QMessageBox.critical(self, "Falha na Limpeza",
                f"Não foi possível limpar os dados.\n\nDetalhe: {task.error_msg}")

    # ================================================================
    #  ABA: CLONAR
    # ================================================================
    def _init_tab_clone(self):
        layout = QVBoxLayout(self.tab_clone)
        layout.addWidget(QLabel("O banco selecionado no topo será usado como origem."))
        layout.addWidget(QLabel("Nome para o novo clone:"))
        self.edit_clone_name = QLineEdit()
        self.edit_clone_name.setPlaceholderText("ex: banco_copia_trabalho")
        layout.addWidget(self.edit_clone_name)
        self.btn_run_clone = QPushButton("CLONAR BANCO AGORA")
        self.btn_run_clone.clicked.connect(self.run_clone)
        layout.addWidget(self.btn_run_clone)
        layout.addStretch()

    def run_clone(self):
        src_db = self.combo_dbs.currentText()
        new_db = self.edit_clone_name.text()
        if not src_db or not new_db:
            QMessageBox.warning(self, "Aviso",
                "Selecione o banco de origem e informe o nome do clone.")
            return
        params = self.get_selected_server_params()
        try:
            logic.terminate_db_sessions(params, src_db)
            conn = logic.get_db_connection(params, "postgres")
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(f'CREATE DATABASE "{new_db}" TEMPLATE "{src_db}"')
            cur.close()
            conn.close()
            QMessageBox.information(self, "Sucesso",
                f"Banco '{src_db}' clonado para '{new_db}'!")
            self.populate_databases()
        except Exception as e:
            QMessageBox.critical(self, "Erro ao Clonar",
                f"Não foi possível clonar o banco.\n\nDetalhe: {e}")

    # ================================================================
    #  ABA: UNIR BANCOS (MERGE)
    # ================================================================
    def _init_tab_merge(self):
        # Layout principal da aba
        main_layout = QVBoxLayout(self.tab_merge)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # 1. Área Superior de Seleção e Diagnóstico (Lado a Lado)
        central_layout = QHBoxLayout()
        
        # Coluna Esquerda: Seleção de Bancos
        left_panel = QVBoxLayout()
        l_header = QHBoxLayout()
        l_header.addWidget(QLabel("<b>1. Seleção:</b>"))
        btn_refresh_merge = QPushButton("Atualizar")
        btn_refresh_merge.clicked.connect(self.populate_merge_list)
        l_header.addWidget(btn_refresh_merge)
        left_panel.addLayout(l_header)
        
        self.list_dbs_merge = QListWidget()
        self.list_dbs_merge.setSelectionMode(QAbstractItemView.MultiSelection)
        self.list_dbs_merge.setMinimumWidth(180)
        left_panel.addWidget(self.list_dbs_merge)
        central_layout.addLayout(left_panel, 1) # Proporção 1
        
        # Coluna Direita: Análise e Log
        right_panel = QVBoxLayout()
        r_header = QHBoxLayout()
        r_header.addWidget(QLabel("<b>2. Diagnóstico de Estrutura:</b>"))
        btn_analyze_merge = QPushButton("Analisar")
        btn_analyze_merge.clicked.connect(self.run_merge_analysis)
        r_header.addWidget(btn_analyze_merge)
        right_panel.addLayout(r_header)
        
        self.tbl_merge_diag = QTableWidget(0, 5)
        self.tbl_merge_diag.setHorizontalHeaderLabels(["Banco", "Grupos", "Geo", "Status", "Obs"])
        self.tbl_merge_diag.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_merge_diag.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_merge_diag.setMinimumHeight(120)
        right_panel.addWidget(self.tbl_merge_diag, 2)
        
        right_panel.addWidget(QLabel("<b>Log da Operação:</b>"))
        self.txt_merge_log = QTextEdit()
        self.txt_merge_log.setReadOnly(True)
        self.txt_merge_log.setMaximumHeight(100)
        right_panel.addWidget(self.txt_merge_log, 1)
        
        central_layout.addLayout(right_panel, 3) # Proporção 3
        main_layout.addLayout(central_layout)

        # 2. Área Inferior: Regras e Execução (Mais compacta)
        footer_layout = QHBoxLayout()
        
        # Grupo Regras
        self.check_ignore_pk = QRadioButton("Criar novos IDs (EVITA CONFLITOS)")
        self.check_ignore_pk.setChecked(True)
        self.check_ignore_pk.setStyleSheet("font-weight: bold; color: #4CAF50;")
        footer_layout.addWidget(self.check_ignore_pk)
        
        footer_layout.addStretch()
        
        footer_layout.addWidget(QLabel("<b>Banco de Destino:</b>"))
        self.edit_merge_db_name = QLineEdit()
        self.edit_merge_db_name.setPlaceholderText("nome_do_banco_unificado")
        self.edit_merge_db_name.setFixedWidth(200)
        footer_layout.addWidget(self.edit_merge_db_name)
        
        main_layout.addLayout(footer_layout)

        self.btn_run_merge = QPushButton("EXECUTAR UNIÃO DOS BANCOS")
        self.btn_run_merge.setEnabled(False)
        self.btn_run_merge.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold; padding: 12px; font-size: 14px;")
        self.btn_run_merge.clicked.connect(self.run_merge)
        main_layout.addWidget(self.btn_run_merge)

    def add_merge_log(self, text, type="info"):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        prefix = {"info": "[INFO]", "error": "[ERRO]", "ok": "[ OK ]"}.get(type, "[INFO]")
        self.txt_merge_log.append(f"{now} {prefix} {text}")
        QgsApplication.processEvents()

    def populate_merge_list(self):
        self.list_dbs_merge.clear()
        params = self.get_selected_server_params()
        if not params:
            return
        try:
            dbs = logic.list_databases(params)
            self.list_dbs_merge.addItems(dbs)
        except Exception as e:
            QgsMessageLog.logMessage(
                f"populate_merge_list: {e}", "ISTools", Qgis.Warning)

    def run_merge_analysis(self):
        """Análise estrutural real dos bancos selecionados."""
        selected = [item.text() for item in self.list_dbs_merge.selectedItems()]
        if len(selected) < 2:
            QMessageBox.warning(self, "Aviso",
                "Selecione pelo menos 2 bancos para analisar.")
            return

        params = self.get_selected_server_params()
        self.tbl_merge_diag.setRowCount(0)
        self.add_merge_log(f"Analisando estrutura de {len(selected)} bancos...")

        # Coletar análises
        analyses = []
        for db_name in selected:
            self.add_merge_log(f"  Analisando '{db_name}'...")
            a = logic.analyze_database(params, db_name)
            analyses.append(a)

            row = self.tbl_merge_diag.rowCount()
            self.tbl_merge_diag.insertRow(row)
            self.tbl_merge_diag.setItem(row, 0, QTableWidgetItem(db_name))

            schemas_str = ", ".join(a["schemas"][:3])
            if len(a["schemas"]) > 3:
                schemas_str += "..."
            self.tbl_merge_diag.setItem(row, 1, QTableWidgetItem(schemas_str))
            self.tbl_merge_diag.setItem(row, 2, QTableWidgetItem(str(a["geo_count"])))

            status_map = {
                "compatible": ("Compatível", "#C8E6C9"),
                "warning":    ("Compatível com aviso", "#FFF9C4"),
                "no_geo":     ("Sem camadas espaciais", "#FFF9C4"),
                "error":      ("Erro de conexão", "#FFCDD2"),
            }
            label, color = status_map.get(a["status"], ("Desconhecido", "#E0E0E0"))
            status_item = QTableWidgetItem(label)
            status_item.setBackground(QColor(color))
            self.tbl_merge_diag.setItem(row, 3, status_item)

            obs_item = QTableWidgetItem(a.get("obs", ""))
            obs_item.setToolTip(a.get("obs", ""))
            self.tbl_merge_diag.setItem(row, 4, obs_item)

        # Comparar
        comparison = logic.compare_structures(analyses)

        for w in comparison.get("warnings", []):
            self.add_merge_log(f"  ⚠ {w}", "error")

        if comparison["compatible"]:
            self.btn_run_merge.setEnabled(True)
            compat = sum(1 for a in analyses if a["status"] in ("compatible", "warning"))
            self.add_merge_log(
                f"Análise concluída. {compat} bancos aptos para união.", "ok")
        else:
            self.btn_run_merge.setEnabled(False)
            self.add_merge_log(
                "Análise concluída. Bancos insuficientes ou incompatíveis.", "error")

    def run_merge(self):
        selected = [item.text() for item in self.list_dbs_merge.selectedItems()]
        target_db = self.edit_merge_db_name.text().strip()

        if len(selected) < 2 or not target_db:
            QMessageBox.warning(self, "Aviso",
                "Selecione pelo menos 2 bancos e informe o nome do banco resultante.")
            return

        msg = (f"Você vai unir {len(selected)} bancos em um novo banco chamado "
               f"'{target_db}'.\n\n"
               "Novos identificadores serão criados para evitar conflitos.\n"
               "Os bancos originais NÃO serão alterados.\n\n"
               "Deseja iniciar?")

        if QMessageBox.question(self, "Confirmar União", msg,
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        params = self.get_selected_server_params()
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.txt_merge_log.clear()

        task = MergeDatabaseTask(params, selected, target_db)
        task.progress_signal.connect(self.add_merge_log)
        task.taskCompleted.connect(lambda: self.on_merge_finished(True, task))
        task.taskTerminated.connect(lambda: self.on_merge_finished(False, task))
        QgsApplication.taskManager().addTask(task)

    def on_merge_finished(self, success, task):
        self.progress_bar.setVisible(False)
        mr = task.merge_result or {}
        status = mr.get("status", "error")

        if success and status == "success":
            QMessageBox.information(self, "União Concluída",
                f"✅ A união dos bancos foi concluída com sucesso.\n\n"
                f"- {mr.get('total_registros', 0)} registros inseridos.\n"
                f"- {mr.get('total_sequences', 0)} sequências ajustadas.\n"
                f"- Banco resultante: '{task.target_db}'.")
            self.populate_databases()
        elif success and status == "partial":
            warns = mr.get("warnings", [])
            warn_text = "\n".join(f"  • {w}" for w in warns[:10])
            if len(warns) > 10:
                warn_text += f"\n  ... e mais {len(warns) - 10} aviso(s)."
            QMessageBox.warning(self, "União Concluída com Alertas",
                f"⚠️ A união foi concluída, mas com {len(warns)} aviso(s).\n\n"
                f"- {mr.get('total_registros', 0)} registros inseridos.\n"
                f"- {mr.get('total_sequences', 0)} sequências ajustadas.\n"
                f"- Banco resultante: '{task.target_db}'.\n\n"
                f"Avisos:\n{warn_text}\n\n"
                "Revise o banco resultante antes de usá-lo em produção.")
            self.populate_databases()
        else:
            errs = mr.get("errors", [task.error_msg]) if mr else [task.error_msg]
            err_text = "\n".join(f"  • {e}" for e in errs[:5])
            QMessageBox.critical(self, "Falha na União",
                f"❌ Não foi possível completar a operação.\n\nErro(s):\n{err_text}")

    # ================================================================
    #  ABA: EXCLUIR
    # ================================================================
    def _init_tab_delete(self):
        layout = QVBoxLayout(self.tab_delete)
        layout.addWidget(QLabel("Selecione os bancos para EXCLUIR DEFINITIVAMENTE:"))

        self.list_dbs_delete = QListWidget()
        self.list_dbs_delete.setSelectionMode(QAbstractItemView.MultiSelection)
        self.list_dbs_delete.setStyleSheet("border: 1px solid red;")
        layout.addWidget(self.list_dbs_delete)

        btn_refresh_delete = QPushButton("Atualizar Lista")
        btn_refresh_delete.clicked.connect(self.populate_delete_list)
        layout.addWidget(btn_refresh_delete)

        self.btn_run_delete = QPushButton("EXCLUIR SELECIONADOS")
        self.btn_run_delete.setStyleSheet(
            "background-color: #d32f2f; color: white; font-weight: bold; padding: 10px;")
        self.btn_run_delete.clicked.connect(self.run_delete)
        layout.addWidget(self.btn_run_delete)
        layout.addStretch()

    def populate_delete_list(self):
        self.list_dbs_delete.clear()
        params = self.get_selected_server_params()
        if not params:
            return
        try:
            dbs = logic.list_databases(params)
            self.list_dbs_delete.addItems(dbs)
        except Exception as e:
            QgsMessageLog.logMessage(f"populate_delete_list: {e}", "ISTools", Qgis.Warning)

    def run_delete(self):
        targets = [item.text() for item in self.list_dbs_delete.selectedItems()]
        if not targets:
            QMessageBox.warning(self, "Aviso", "Selecione pelo menos um banco.")
            return

        msg = (f"Você selecionou {len(targets)} banco(s) para EXCLUSÃO PERMANENTE:\n\n"
               f"{', '.join(targets)}\n\n"
               "Esta ação NÃO PODE SER DESFEITA. Deseja continuar?")
        if QMessageBox.question(self, "CONFIRMAÇÃO CRÍTICA", msg,
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        params = self.get_selected_server_params()
        try:
            conn = logic.get_db_connection(params, "postgres")
            conn.autocommit = True
            cur = conn.cursor()
            for db in targets:
                logic.terminate_db_sessions(params, db)
                cur.execute(f'DROP DATABASE "{db}"')
                QgsMessageLog.logMessage(
                    f"Banco '{db}' excluído.", "ISTools", Qgis.Info)
            cur.close()
            conn.close()
            QMessageBox.information(self, "Sucesso",
                f"{len(targets)} banco(s) excluído(s)!")
            self.populate_databases()
            self.populate_delete_list()
        except Exception as e:
            QMessageBox.critical(self, "Erro",
                f"Falha ao excluir banco(s).\n\nDetalhe: {e}")

    # ================================================================
    #  ABA: BACKUP
    # ================================================================
    def _init_tab_backup(self):
        layout = QVBoxLayout(self.tab_backup)
        layout.addWidget(QLabel("Selecione o local para salvar o arquivo de Backup (.sql):"))
        h = QHBoxLayout()
        self.edit_backup_path = QLineEdit()
        btn_browse = QPushButton("Procurar...")
        btn_browse.clicked.connect(self.browse_backup)
        h.addWidget(self.edit_backup_path)
        h.addWidget(btn_browse)
        layout.addLayout(h)
        self.btn_run_backup = QPushButton("Gerar Backup")
        self.btn_run_backup.clicked.connect(self.run_backup)
        layout.addWidget(self.btn_run_backup)
        layout.addStretch()

    def browse_backup(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Backup", "", "SQL Files (*.sql);;All Files (*)")
        if path:
            self.edit_backup_path.setText(path)

    def run_backup(self):
        db_name = self.combo_dbs.currentText()
        out_path = self.edit_backup_path.text()
        bin_dir = self.get_bin_path()
        if not db_name or not out_path:
            QMessageBox.warning(self, "Aviso",
                "Selecione o banco e o destino do arquivo.")
            return
        pg_dump = os.path.join(bin_dir, "pg_dump.exe") if os.name == 'nt' else os.path.join(bin_dir, "pg_dump")
        if not os.path.exists(pg_dump):
            pg_dump = "pg_dump"
        params = self.get_selected_server_params()
        env = os.environ.copy()
        env["PGPASSWORD"] = params["password"]
        cmd = [pg_dump, "-h", params["host"], "-p", params["port"],
               "-U", params["user"], "-f", out_path, db_name]
        self.run_db_task("Backup", cmd, env)

    # ================================================================
    #  ABA: RESTAURAR
    # ================================================================
    def _init_tab_restore(self):
        layout = QVBoxLayout(self.tab_restore)
        layout.addWidget(QLabel("Arquivo SQL para restaurar:"))
        h1 = QHBoxLayout()
        self.edit_restore_sql = QLineEdit()
        btn_browse = QPushButton("Procurar...")
        btn_browse.clicked.connect(self.browse_restore)
        h1.addWidget(self.edit_restore_sql)
        h1.addWidget(btn_browse)
        layout.addLayout(h1)
        layout.addWidget(QLabel("Nome do Novo Banco:"))
        self.edit_new_db_name = QLineEdit()
        self.edit_new_db_name.setPlaceholderText("ex: edgv_topo_restaurado")
        layout.addWidget(self.edit_new_db_name)
        self.btn_run_restore = QPushButton("Restaurar Banco")
        self.btn_run_restore.clicked.connect(self.run_restore)
        layout.addWidget(self.btn_run_restore)
        layout.addStretch()

    def browse_restore(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar SQL", "", "SQL Files (*.sql);;All Files (*)")
        if path:
            self.edit_restore_sql.setText(path)

    def run_restore(self):
        sql_path = self.edit_restore_sql.text()
        new_db = self.edit_new_db_name.text()
        bin_dir = self.get_bin_path()
        if not sql_path or not new_db:
            QMessageBox.warning(self, "Aviso",
                "Selecione o SQL e informe o nome do novo banco.")
            return
        params = self.get_selected_server_params()
        env = os.environ.copy()
        env["PGPASSWORD"] = params["password"]
        try:
            conn = logic.get_db_connection(params, "postgres")
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(f'CREATE DATABASE "{new_db}"')
            cur.close()
            conn.close()
        except Exception as e:
            if "already exists" not in str(e).lower():
                QMessageBox.critical(self, "Erro", f"Falha ao criar banco: {e}")
                return
        psql = os.path.join(bin_dir, "psql.exe") if os.name == 'nt' else os.path.join(bin_dir, "psql")
        if not os.path.exists(psql):
            psql = "psql"
        cmd = [psql, "-h", params["host"], "-p", params["port"],
               "-U", params["user"], "-d", new_db, "-f", sql_path]
        self.run_db_task("Restauração", cmd, env)

    # ================================================================
    #  ABA: CRIAR (SCRIPT)
    # ================================================================
    def _init_tab_create(self):
        layout = QVBoxLayout(self.tab_create)
        layout.addWidget(QLabel(
            "Selecione o script de criação de estrutura (ex: EDGV Topo):"))
        h1 = QHBoxLayout()
        self.edit_create_sql = QLineEdit()
        btn_browse = QPushButton("Procurar...")
        btn_browse.clicked.connect(
            lambda: self.edit_create_sql.setText(
                QFileDialog.getOpenFileName(self, "Selecionar Script")[0]))
        h1.addWidget(self.edit_create_sql)
        h1.addWidget(btn_browse)
        layout.addLayout(h1)
        layout.addWidget(QLabel("Nome do Banco a Criar:"))
        self.edit_create_db_name = QLineEdit()
        layout.addWidget(self.edit_create_db_name)
        self.btn_run_create = QPushButton("Criar Banco e Estrutura")
        self.btn_run_create.clicked.connect(self.run_create)
        layout.addWidget(self.btn_run_create)
        layout.addStretch()

    def run_create(self):
        sql_path = self.edit_create_sql.text()
        new_db = self.edit_create_db_name.text()
        if not sql_path or not new_db:
            return
        self.edit_restore_sql.setText(sql_path)
        self.edit_new_db_name.setText(new_db)
        self.run_restore()

    # ================================================================
    #  ABA: AJUDA
    # ================================================================
    def _init_tab_help(self):
        layout = QVBoxLayout(self.tab_help)
        help_text = QTextEdit()
        help_text.setReadOnly(True)
        help_text.setHtml("""
            <h3>Guia do Gerenciador de Banco — ISTools v1.5.0</h3>
            <p>Ferramenta para administração de bancos PostGIS com foco em projetos de Geoinformação.</p>

            <hr>
            <h4>1. Configurar Ferramentas PostgreSQL
            <b>(Obrigatório para Backup/Restaurar)</b></h4>
            <p>Clique em <b>"Configurar Ferramentas"</b> no topo e selecione a pasta
            onde estão os programas <i>pg_dump</i> e <i>psql</i>
            (ex: C:\\Program Files\\PostgreSQL\\15\\bin).
            <br><i>Sem essa configuração, as abas Backup e Restaurar não funcionarão.</i></p>

            <h4>2. Limpar Dados</h4>
            <p>Remove os registros (feições) das tabelas de um grupo, mantendo toda a
            estrutura do banco (tabelas, domínios, regras). Você pode limpar
            <b>todas as tabelas</b> ou <b>apenas camadas espaciais</b>. O sistema
            detecta automaticamente os grupos disponíveis.</p>

            <h4>3. Clonar</h4>
            <p>Cria uma cópia exata do banco selecionado com um novo nome. Útil para
            trabalhar sem risco sobre o banco de produção.</p>

            <h4>4. Unir Bancos</h4>
            <p>Combina dados de múltiplos bancos em um novo banco unificado.
            <b>Antes de unir</b>, use o botão "Analisar Compatibilidade" para verificar
            se os bancos possuem estrutura compatível.</p>
            <p><b>Comportamento:</b></p>
            <ul>
              <li>Novos IDs são gerados automaticamente para evitar conflitos.</li>
              <li>Se houver erros por tabela, a operação conclui com status "parcial".</li>
              <li>Sempre revise o log detalhado antes de confiar no banco resultante.</li>
            </ul>

            <h4>5. Excluir</h4>
            <p>Remove bancos do servidor de forma permanente. Requer confirmação.</p>

            <h4>6. Backup</h4>
            <p>Gera um arquivo .sql com toda a estrutura e dados do banco. Utilize para 
            salvar o trabalho ou transferir para outro computador.
            <br><i>Requer <b>pg_dump</b> configurado (ver item 1).</i></p>

            <h4>7. Restaurar</h4>
            <p>Cria um <b>novo banco</b> a partir de um arquivo .sql existente.
            <br><i>Requer <b>psql</b> configurado (ver item 1).</i></p>

            <h4>8. Criar (Script)</h4>
            <p>Cria um banco vazio a partir de um script de definição de estrutura
            (EDGV Topo v1.4.5, etc).</p>

            <hr>
            <p style='color: grey;'>Desenvolvido por 2° Sgt Irlan Souza, Exército Brasileiro.<br>
            <a href="https://irlansouza93.github.io/istools-website/">Site Oficial</a> |
            <a href="https://github.com/irlansouza93/istools">GitHub</a></p>
        """)
        layout.addWidget(help_text)

    # ================================================================
    #  MOTOR DE TAREFAS QgsTask
    # ================================================================
    def run_db_task(self, description, cmd, env):
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        task = DatabaseOperationTask(description, cmd, env)
        task.taskCompleted.connect(
            lambda: self.on_task_finished(description, True, task))
        task.taskTerminated.connect(
            lambda: self.on_task_finished(description, False, task))
        QgsApplication.taskManager().addTask(task)

    def on_task_finished(self, desc, success, task):
        self.progress_bar.setVisible(False)
        if success:
            QgsMessageLog.logMessage(
                f"{desc} concluído.", "ISTools", Qgis.Success)
            QMessageBox.information(self, desc, f"{desc} finalizado com sucesso.")
        else:
            erro = getattr(task, 'error_msg', 'Erro desconhecido')
            QgsMessageLog.logMessage(
                f"Falha no {desc}: {erro}", "ISTools", Qgis.Critical)
            
            # Detecção de incompatibilidade de versão
            hint = ""
            if "version mismatch" in erro.lower() or "server version" in erro.lower():
                hint = ("\n\n<b>DICA:</b> Detectamos uma incompatibilidade de versão.\n"
                        "Certifique-se que o <i>pg_dump</i> local é de uma versão igual ou superior "
                        "à do servidor PostgreSQL. Atualize o caminho em 'Configurar Ferramentas'.")
            else:
                hint = "\n\nDica: Verifique se o caminho das ferramentas PostgreSQL está correto."

            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle(f"Falha no {desc}")
            msg.setText(f"Ocorreu um problema ao executar a operação de {desc}.")
            msg.setInformativeText(f"{erro}{hint}")
            msg.exec_()


# ====================================================================
#  TAREFAS ASSÍNCRONAS (QgsTask)
# ====================================================================

class DatabaseOperationTask(QgsTask):
    """Subprocesso (pg_dump/psql) sem travar UI."""
    def __init__(self, description, cmd, env):
        super().__init__(description, QgsTask.CanCancel)
        self.cmd = cmd
        self.env = env
        self.error_msg = ""

    def run(self):
        try:
            process = subprocess.Popen(
                self.cmd, env=self.env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                self.error_msg = f"Código {process.returncode}\n{stderr}"
                return False
            return True
        except Exception as e:
            self.error_msg = str(e)
            return False

    def finished(self, result):
        pass


class ResetDatabaseTask(QgsTask):
    """Reset de dados em background."""
    def __init__(self, params, db_name, schema_name, mode):
        super().__init__(
            f"Limpando '{schema_name}' em '{db_name}'", QgsTask.CanCancel)
        self.params = params
        self.db_name = db_name
        self.schema_name = schema_name
        self.mode = mode
        self.count = 0
        self.error_msg = ""

    def run(self):
        try:
            self.count = logic.reset_schema_data(
                self.params, self.db_name, self.schema_name, self.mode)
            return True
        except Exception as e:
            self.error_msg = str(e)
            return False


class MergeDatabaseTask(QgsTask):
    """União de bancos em background."""
    progress_signal = pyqtSignal(str, str)

    def __init__(self, params, source_dbs, target_db):
        super().__init__(
            f"Unindo bancos em '{target_db}'", QgsTask.CanCancel)
        self.params = params
        self.source_dbs = source_dbs
        self.target_db = target_db
        self.total_count = 0
        self.error_msg = ""
        self.merge_result = None  # dict completo

    def run(self):
        try:
            self.merge_result = logic.merge_databases(
                self.params, self.source_dbs, self.target_db,
                progress_callback=self._emit)

            status = self.merge_result.get("status", "error")
            self.total_count = self.merge_result.get("total_registros", 0)

            if status == "success":
                return True
            elif status == "partial":
                # Sucesso parcial — task completa mas com avisos
                return True
            else:
                self.error_msg = "; ".join(self.merge_result.get("errors", ["Erro desconhecido"]))
                return False
        except Exception as e:
            self.error_msg = str(e)
            return False

    def _emit(self, text, type="info"):
        self.progress_signal.emit(text, type)
