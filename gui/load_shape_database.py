# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Carregar Banco Shape (Interface)
                                 A QGIS plugin
 Diálogo para carga organizada de shapefiles no projeto QGIS
                               -------------------
        begin                : 2026-03-26
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
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFileDialog,
    QCheckBox, QGroupBox, QProgressBar,
    QMessageBox, QTextEdit,
)
from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtGui import QIcon, QFont
from qgis.core import QgsApplication, QgsMessageLog, Qgis

from istools import load_shape_database_logic as logic


class LoadShapeDatabaseDialog(QDialog):
    """
    Diálogo para carregar shapefiles de uma pasta no projeto QGIS.
    
    Organiza as camadas em um grupo principal (nome da pasta) com
    subgrupos Points, Lines e Polygons.
    """

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("ISTools — Carregar Banco Shape")
        self.setMinimumSize(600, 520)

        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "icons", "carregar_banco_shape.png"
        )
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._build_ui()

    # ================================================================
    #  CONSTRUÇÃO DA INTERFACE
    # ================================================================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # --- Título ---
        title = QLabel("📂 Carregar Banco Shape")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        desc = QLabel(
            "Selecione uma pasta com arquivos Shapefile (.shp). "
            "As camadas serão carregadas no projeto atual e organizadas "
            "por tipo geométrico (Points, Lines, Polygons)."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; margin-bottom: 8px;")
        layout.addWidget(desc)

        # --- Seleção de Pasta ---
        folder_group = QGroupBox("Pasta com Shapefiles")
        folder_layout = QVBoxLayout(folder_group)

        row = QHBoxLayout()
        self.edit_folder = QLineEdit()
        self.edit_folder.setPlaceholderText("Selecione a pasta...")
        self.edit_folder.setReadOnly(True)
        btn_browse = QPushButton("Procurar...")
        btn_browse.setFixedWidth(100)
        btn_browse.clicked.connect(self._browse_folder)
        row.addWidget(self.edit_folder)
        row.addWidget(btn_browse)
        folder_layout.addLayout(row)

        layout.addWidget(folder_group)

        # --- Opções ---
        options_group = QGroupBox("Opções")
        options_layout = QVBoxLayout(options_group)

        self.chk_recursive = QCheckBox("Buscar em subpastas")
        self.chk_recursive.stateChanged.connect(self._on_options_changed)
        self.chk_recursive.setToolTip(
            "Se marcado, busca shapefiles em todas as subpastas recursivamente."
        )
        options_layout.addWidget(self.chk_recursive)

        self.chk_ignore_invalid = QCheckBox("Ignorar arquivos inválidos")
        self.chk_ignore_invalid.setChecked(True)
        self.chk_ignore_invalid.setToolTip(
            "Se marcado, arquivos que não puderem ser lidos serão ignorados silenciosamente."
        )
        options_layout.addWidget(self.chk_ignore_invalid)

        self.chk_recreate = QCheckBox("Recriar grupo se já existir")
        self.chk_recreate.setToolTip(
            "Se marcado, remove o grupo existente antes de criar um novo. "
            "Se desmarcado, cria um grupo com sufixo numérico."
        )
        options_layout.addWidget(self.chk_recreate)

        layout.addWidget(options_group)

        # --- Pré-visualização ---
        preview_group = QGroupBox("Resumo da Pasta")
        preview_layout = QVBoxLayout(preview_group)

        self.lbl_preview = QLabel("Nenhuma pasta selecionada.")
        self.lbl_preview.setWordWrap(True)
        self.lbl_preview.setStyleSheet("color: #888; padding: 4px;")
        preview_layout.addWidget(self.lbl_preview)

        layout.addWidget(preview_group)

        # --- Barra de Progresso ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # --- Log de Resultado ---
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(120)
        self.txt_log.setVisible(False)
        self.txt_log.setStyleSheet(
            "QTextEdit {"
            "  background-color: #f8f9fa;"
            "  border: 1px solid #dee2e6;"
            "  border-radius: 4px;"
            "  font-family: Consolas, monospace;"
            "  font-size: 11px;"
            "}"
        )
        layout.addWidget(self.txt_log)

        # --- Botões ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_load = QPushButton("  Carregar no Projeto  ")
        self.btn_load.setEnabled(False)
        self.btn_load.setMinimumHeight(38)
        self.btn_load.setStyleSheet(
            "QPushButton {"
            "  background-color: #28a745;"
            "  color: white;"
            "  font-weight: bold;"
            "  font-size: 13px;"
            "  border-radius: 6px;"
            "  padding: 6px 20px;"
            "}"
            "QPushButton:hover { background-color: #218838; }"
            "QPushButton:disabled {"
            "  background-color: #ccc;"
            "  color: #888;"
            "}"
        )
        self.btn_load.clicked.connect(self._run_load)
        btn_row.addWidget(self.btn_load)

        btn_close = QPushButton("Fechar")
        btn_close.setMinimumHeight(38)
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

        # --- Rodapé ---
        footer = QLabel(
            '<span style="color: grey; font-size: 10px;">'
            'Desenvolvido por 2° Sgt Irlan Souza, Exército Brasileiro — '
            '<a href="https://irlansouza93.github.io/istools-website/">Site Oficial</a>'
            '</span>'
        )
        footer.setOpenExternalLinks(True)
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)

    # ================================================================
    #  SELEÇÃO DE PASTA
    # ================================================================

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Selecionar Pasta com Shapefiles"
        )
        if folder:
            self.edit_folder.setText(folder)
            self._update_preview(folder)

    def _update_preview(self, folder: str):
        """Faz um scan rápido da pasta e atualiza o resumo."""
        recursive = self.chk_recursive.isChecked()
        shp_files = logic.discover_shapefiles(folder, recursive)
        count = len(shp_files)

        folder_name = os.path.basename(folder.rstrip("/\\"))

        if count == 0:
            self.lbl_preview.setText(
                f'📁 <b>{folder_name}</b><br>'
                f'<span style="color: #dc3545;">Nenhum shapefile (.shp) encontrado.</span>'
            )
            self.btn_load.setEnabled(False)
        else:
            plural = "s" if count > 1 else ""
            self.lbl_preview.setText(
                f'📁 <b>{folder_name}</b><br>'
                f'<span style="color: #28a745;">'
                f'{count} shapefile{plural} encontrado{plural}.</span><br>'
                f'<span style="color: #6c757d;">'
                f'As camadas serão organizadas em subgrupos por tipo geométrico.</span>'
            )
            self.btn_load.setEnabled(True)

    def _on_options_changed(self):
        """Callback para quando as opções (recursivo) mudam."""
        folder = self.edit_folder.text()
        if folder:
            self._update_preview(folder)

    # ================================================================
    #  EXECUÇÃO DO CARREGAMENTO
    # ================================================================

    def _run_load(self):
        folder = self.edit_folder.text()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "Pasta Inválida", "Selecione uma pasta válida.")
            return

        # Preparar UI
        self.btn_load.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.txt_log.setVisible(True)
        self.txt_log.clear()

        self.txt_log.append("⏳ Iniciando carregamento...")

        def progress_cb(current, total):
            if total > 0:
                pct = int((current / total) * 100)
                self.progress_bar.setValue(pct)
                self.progress_bar.setFormat(f"{current}/{total} — {pct}%")
            QgsApplication.processEvents()

        # Executar
        result = logic.load_shapefiles_to_project(
            folder=folder,
            recursive=self.chk_recursive.isChecked(),
            ignore_invalid=self.chk_ignore_invalid.isChecked(),
            recreate_group=self.chk_recreate.isChecked(),
            progress_callback=progress_cb,
        )

        # Atualizar UI
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("Concluído")

        self.txt_log.append(f"\n📊 Resultado da Carga:")
        self.txt_log.append(f"   📁 Pasta: {result.folder_name}")
        self.txt_log.append(f"   🔍 Encontrados: {result.total_found}")
        if result.stopped_by_error:
            self.txt_log.append(f"   🛑 Operação interrompida por erro.")
        self.txt_log.append(f"   ✅ Carregados: {result.total_loaded}")
        if result.total_invalid > 0:
            self.txt_log.append(f"   ⚠️  Inválidos/Ignorados: {result.total_invalid}")
        self.txt_log.append(f"\n   📍 Points: {result.points}")
        self.txt_log.append(f"   📏 Lines: {result.lines}")
        self.txt_log.append(f"   📐 Polygons: {result.polygons}")
        if result.others > 0:
            self.txt_log.append(f"   ❓ Others: {result.others}")

        if result.errors:
            self.txt_log.append(f"\n⚠️  Arquivos com erro:")
            for err in result.errors:
                self.txt_log.append(f"   • {err}")

        # Mensagem final
        if result.stopped_by_error:
            QMessageBox.critical(
                self, "Carga Interrompida",
                f"A operação foi interrompida porque um arquivo inválido foi encontrado.\n\n"
                f"Camadas carregadas até o erro: {result.total_loaded}\n"
                f"Grupo criado: {result.folder_name}\n\n"
                f"Consulte o log para detalhes sobre o arquivo problemático."
            )
        elif result.total_loaded == 0:
            QMessageBox.warning(
                self, "Nenhuma Camada Carregada",
                "Nenhum shapefile válido foi encontrado na pasta selecionada."
            )
        elif result.total_invalid > 0:
            QMessageBox.information(
                self, "Carregamento Parcial",
                f"{result.total_loaded} camadas carregadas com sucesso.\n"
                f"{result.total_invalid} arquivos foram ignorados por erro.\n\n"
                f"Grupo criado: {result.folder_name}"
            )
        else:
            QMessageBox.information(
                self, "Carregamento Concluído",
                f"✅ {result.total_loaded} camadas carregadas com sucesso!\n\n"
                f"📍 Points: {result.points}   📏 Lines: {result.lines}   "
                f"📐 Polygons: {result.polygons}\n\n"
                f"Grupo criado: {result.folder_name}"
            )

        self.btn_load.setEnabled(True)
