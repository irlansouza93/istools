# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, 
    QPushButton, QHBoxLayout, QMessageBox
)
from qgis.PyQt.QtCore import Qt

class ServerEditDialog(QDialog):
    def __init__(self, parent=None, server_data=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar Servidor PostGIS")
        self.setMinimumWidth(350)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.name_edit = QLineEdit()
        self.host_edit = QLineEdit()
        self.port_edit = QLineEdit()
        self.port_edit.setText("5432")
        self.user_edit = QLineEdit()
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.Password)
        
        form.addRow("Nome do Servidor:", self.name_edit)
        form.addRow("Endereço (Host):", self.host_edit)
        form.addRow("Porta:", self.port_edit)
        form.addRow("Usuário:", self.user_edit)
        form.addRow("Senha:", self.pass_edit)
        
        layout.addLayout(form)
        
        # Botões
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("Salvar")
        self.cancel_btn = QPushButton("Cancelar")
        
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)
        
        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        
        if server_data:
            self.name_edit.setText(server_data.get('name', ''))
            self.host_edit.setText(server_data.get('host', ''))
            self.port_edit.setText(server_data.get('port', '5432'))
            self.user_edit.setText(server_data.get('user', ''))
            self.pass_edit.setText(server_data.get('password', ''))
            # Nome não pode ser editado se for edição para não quebrar a chave do QSettings
            self.name_edit.setEnabled(False)

    def get_data(self):
        return {
            "name": self.name_edit.text().strip(),
            "host": self.host_edit.text().strip(),
            "port": self.port_edit.text().strip(),
            "user": self.user_edit.text().strip(),
            "password": self.pass_edit.text().strip()
        }

    def validate(self):
        data = self.get_data()
        if not data["name"] or not data["host"] or not data["user"]:
            QMessageBox.warning(self, "Aviso", "Preencha os campos obrigatórios (Nome, Host, Usuário).")
            return False
        if "_" in data["name"]:
            QMessageBox.warning(self, "Aviso", 'O nome do servidor não pode conter o caractere "_".')
            return False
        return True

    def accept(self):
        if self.validate():
            super().accept()
