# -*- coding: utf-8 -*-
import os
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QPushButton, QHeaderView, QMessageBox,
    QApplication
)
from qgis.PyQt.QtCore import Qt, QSettings, pyqtSignal
from qgis.PyQt.QtSql import QSqlDatabase
from qgis.core import QgsMessageLog, Qgis

from .server_edit import ServerEditDialog

class ServerConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar Servidores PostGIS")
        self.setMinimumSize(700, 400)
        
        layout = QVBoxLayout(self)
        
        # Tabela de Servidores
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Nome do Servidor", "Endereço", "Porta", "Usuário", "Senha"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        layout.addWidget(self.table)
        
        # Barra de Botões
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Adicionar")
        self.remove_btn = QPushButton("Remover")
        self.edit_btn = QPushButton("Editar")
        self.test_btn = QPushButton("Teste")
        self.fetch_db_btn = QPushButton("Buscar Bancos")
        self.close_btn = QPushButton("Fechar")
        
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.test_btn)
        btn_layout.addWidget(self.fetch_db_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        
        # Eventos
        self.add_btn.clicked.connect(self.add_server)
        self.remove_btn.clicked.connect(self.remove_server)
        self.edit_btn.clicked.connect(self.edit_server)
        self.test_btn.clicked.connect(self.test_connection)
        self.fetch_db_btn.clicked.connect(self.fetch_databases)
        self.close_btn.clicked.connect(self.close)
        self.table.doubleClicked.connect(self.edit_server)
        
        self.populate_table()

    def get_servers(self):
        settings = QSettings()
        settings.beginGroup("PostgreSQL/servers")
        servers = settings.childGroups()
        settings.endGroup()
        return servers

    def get_server_info(self, name):
        settings = QSettings()
        settings.beginGroup(f"PostgreSQL/servers/{name}")
        data = {
            "name": name,
            "host": settings.value("host", ""),
            "port": settings.value("port", "5432"),
            "user": settings.value("username", ""),
            "password": settings.value("password", ""),
            "isDefault": settings.value("isDefault", False)
        }
        settings.endGroup()
        return data

    def save_server_info(self, data):
        settings = QSettings()
        settings.beginGroup(f"PostgreSQL/servers/{data['name']}")
        settings.setValue("host", data["host"])
        settings.setValue("port", data["port"])
        settings.setValue("username", data["user"])
        settings.setValue("password", data["password"])
        settings.setValue("isDefault", data.get("isDefault", False))
        settings.endGroup()

    def populate_table(self):
        self.table.setRowCount(0)
        servers = self.get_servers()
        for name in servers:
            data = self.get_server_info(name)
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(data["host"]))
            self.table.setItem(row, 2, QTableWidgetItem(data["port"]))
            self.table.setItem(row, 3, QTableWidgetItem(data["user"]))
            pass_status = "Salva" if data["password"] else "Não salva"
            self.table.setItem(row, 4, QTableWidgetItem(pass_status))

    def add_server(self):
        dlg = ServerEditDialog(self)
        if dlg.exec_():
            data = dlg.get_data()
            self.save_server_info(data)
            self.populate_table()
            # Tentar buscar bancos automaticamente após adicionar
            self._do_fetch_databases(data["name"], data, quiet=True)

    def edit_server(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um servidor para editar.")
            return
        
        name = self.table.item(row, 0).text()
        data = self.get_server_info(name)
        dlg = ServerEditDialog(self, server_data=data)
        if dlg.exec_():
            new_data = dlg.get_data()
            self.save_server_info(new_data)
            self.populate_table()
            # Tentar buscar bancos automaticamente após editar
            self._do_fetch_databases(new_data["name"], new_data, quiet=True)

    def remove_server(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um servidor para remover.")
            return
        
        name = self.table.item(row, 0).text()
        if QMessageBox.question(self, "Confirmação", f"Deseja remover o servidor '{name}'?") == QMessageBox.Yes:
            settings = QSettings()
            settings.beginGroup(f"PostgreSQL/servers/{name}")
            settings.remove("")
            settings.endGroup()
            self.populate_table()

    def test_connection(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um servidor para testar.")
            return
        
        name = self.table.item(row, 0).text()
        data = self.get_server_info(name)
        
        QApplication.setOverrideCursor(Qt.WaitCursor)
        db = QSqlDatabase.addDatabase("QPSQL", "test_conn")
        db.setHostName(data["host"])
        db.setPort(int(data["port"]))
        db.setDatabaseName("postgres") # Banco padrão para teste
        db.setUserName(data["user"])
        db.setPassword(data["password"])
        
        success = db.open()
        error = db.lastError().text()
        db.close()
        QSqlDatabase.removeDatabase("test_conn")
        QApplication.restoreOverrideCursor()
        
        if success:
            QMessageBox.information(self, "Sucesso", f"Conexão com '{name}' realizada com sucesso!")
            # Carregar bancos automaticamente após teste de sucesso
            self._do_fetch_databases(name, data, quiet=True)
        else:
            QMessageBox.critical(self, "Erro de Conexão", f"Falha ao conectar em '{name}':\n{error}")

    def fetch_databases(self):
        """Chamado pelo botão Buscar Bancos (Modo Manual/Ruidoso)"""
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um servidor para buscar os bancos.")
            return
        
        name = self.table.item(row, 0).text()
        data = self.get_server_info(name)
        self._do_fetch_databases(name, data, quiet=False)

    def _do_fetch_databases(self, name, data, quiet=False):
        """Lógica centralizada para buscar bancos de dados."""
        if not quiet:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            
        conn_id = f"fetch_db_{name}".replace(" ", "_")
        db = QSqlDatabase.addDatabase("QPSQL", conn_id)
        db.setHostName(data["host"])
        db.setPort(int(data["port"]))
        db.setDatabaseName("postgres")
        db.setUserName(data["user"])
        db.setPassword(data["password"])
        
        if not db.open():
            error = db.lastError().text()
            db.close()
            QSqlDatabase.removeDatabase(conn_id)
            if not quiet:
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(self, "Erro", f"Não foi possível buscar bancos em '{name}':\n{error}")
            return

        query = db.exec("SELECT datname FROM pg_database WHERE datistemplate = false AND datallowconn = true ORDER BY datname")
        databases = []
        while query.next():
            databases.append(query.value(0))
        
        db.close()
        QSqlDatabase.removeDatabase(conn_id)
        
        if not quiet:
            QApplication.restoreOverrideCursor()

        if databases:
            settings = QSettings()
            settings.beginGroup(f"PostgreSQL/servers/{name}")
            settings.setValue("databases", ",".join(databases))
            settings.endGroup()
            
            if not quiet:
                QMessageBox.information(self, "Sucesso", f"Encontrados {len(databases)} bancos em '{name}'.")
        elif not quiet:
            QMessageBox.warning(self, "Aviso", "Nenhum banco encontrado.")
