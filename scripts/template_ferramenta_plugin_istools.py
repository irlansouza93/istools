# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Template Plugin Tool
                                 A QGIS plugin
 Professional vectorization toolkit for QGIS
                              -------------------
        begin                : 2026-04-02
        git sha              : $Format:%H$
        copyright            : (C) 2025 by Irlan Souza, 2? Sgt Brazilian Army
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

from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QMessageBox
from qgis.core import QgsApplication, QgsMessageLog, Qgis
from .translations.translate import translate


class ISToolsTemplateTool:
    """
    Template base para ferramentas visuais do plugin ISTools.

    Use este arquivo como ponto de partida para ferramentas acionadas por menu,
    toolbar ou di?logo pr?prio dentro do plugin.
    """

    OUTPUT_GROUP_NAME = "istools-output"

    def __init__(self, iface):
        self.iface = iface
        self.dialog = None

    def tr(self, *string):
        """
        Traduz strings usando o sistema bil?ngue do ISTools.

        Exemplos:
        - self.tr("Open Tool", "Abrir Ferramenta")
        - self.tr("Simple string")
        """
        return translate(string, QgsApplication.locale()[:2])

    def activate_tool(self):
        """
        M?todo chamado a partir da action/menu do plugin.
        """
        self.dialog = TemplateToolDialog(self.iface)
        self.dialog.show()

    def unload(self):
        """
        Limpeza opcional quando a ferramenta for descarregada.
        """
        if self.dialog:
            self.dialog.close()
            self.dialog = None


class TemplateToolDialog(QDialog):
    """
    Template base para di?logo de ferramenta do plugin.

    Estrutura recomendada:
    1. construir UI em __init__
    2. preencher combos/listas em m?todos separados
    3. deixar a l?gica pesada em m?todos auxiliares ou m?dulos externos
    4. registrar mensagens em QgsMessageLog quando necess?rio
    """

    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self.setWindowTitle("Template de Ferramenta do ISTools")

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Substitua este texto pelos par?metros da ferramenta."))

        self.run_button = QPushButton("Executar")
        self.run_button.clicked.connect(self.run_tool)
        layout.addWidget(self.run_button)

        self.setLayout(layout)

    def log_info(self, message: str):
        QgsMessageLog.logMessage(message, "ISTools", Qgis.Info)

    def run_tool(self):
        """
        Ponto de entrada da execu??o da ferramenta.

        Recomenda??es:
        - validar par?metros antes de executar
        - usar QMessageBox apenas para retorno ao usu?rio
        - mover l?gica reutiliz?vel para arquivos separados quando crescer
        - evitar l?gica pesada diretamente na UI thread quando poss?vel
        """
        try:
            self.log_info("Template de ferramenta executado.")
            QMessageBox.information(
                self,
                "ISTools",
                self.tr(
                    "Replace this block with the real tool execution.",
                    "Substitua este bloco pela execu??o real da ferramenta.",
                ),
            )
        except Exception as exc:
            QgsMessageLog.logMessage(str(exc), "ISTools", Qgis.Critical)
            QMessageBox.critical(self, "ISTools", str(exc))
