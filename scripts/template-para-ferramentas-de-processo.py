# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Template para Ferramentas de Processamento
                                 A QGIS plugin
 Template de referência para criação de novos algoritmos de processamento
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

 ARQUIVO DE REFERÊNCIA PARA DESENVOLVIMENTO.
 NÃO é usado em runtime pelo plugin.
 Mantido no repositório GitHub como modelo para criação de novos algoritmos.
"""

import os
from typing import Any, Optional

from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFile,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterString,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFileDestination,
)


class TemplateAlgorithm(QgsProcessingAlgorithm):
    """
    Template de Algoritmo de Processamento ISTools.

    Use este arquivo como base para criar novas ferramentas.
    Copie, renomeie a classe e registre no provider.py.
    """

    # Constantes de Parâmetros
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        """ID único do algoritmo (snake_case, sem espaços)."""
        return "template_algorithm"

    def displayName(self) -> str:
        """Nome exibido na caixa de ferramentas do Processing."""
        return self.tr("Nome da Ferramenta")

    def group(self) -> str:
        """Grupo na caixa de ferramentas (ex: 'Banco de Dados', 'Ferramentas EDGV')."""
        return self.tr("Nome do Grupo")

    def groupId(self) -> str:
        """ID do grupo (snake_case)."""
        return "nome_do_grupo"

    def shortHelpString(self) -> str:
        """Texto exibido na aba de ajuda do algoritmo."""
        return (
            "<b>Nome da Ferramenta</b>\n\n"
            "Descrição concisa do que esta ferramenta faz.\n\n"
            "<b>Parâmetros:</b>\n"
            "- <b>Entrada:</b> Descrição do parâmetro de entrada.\n"
            "- <b>Saída:</b> Descrição do parâmetro de saída.\n\n"
            "<b>O que acontece em caso de erro:</b>\n"
            "Descrever comportamento em caso de falha parcial, rollback, etc.\n\n"
            "<b>Autor:</b> Irlan Souza\n"
            "<b>Email:</b> <a href=\"mailto:irlansouza193@gmail.com\">irlansouza193@gmail.com</a>\n"
            "<b>GitHub:</b> <a href=\"https://github.com/irlansouza93\">https://github.com/irlansouza93</a>\n\n"
            "<b>🌐 <a href=\"https://irlansouza93.github.io/istools-website/\">"
            "🚀VISITE NOSSO SITE OFICIAL - CLIQUE AQUI! 🚀</a></b>"
        )

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):
        """Define os parâmetros do algoritmo."""
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT,
                "Diretório de Entrada",
                behavior=QgsProcessingParameterFile.Folder
            )
        )
        # Adicione mais parâmetros conforme necessário

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:
        """Lógica principal do algoritmo."""
        input_dir = self.parameterAsFile(parameters, self.INPUT, context)

        if not os.path.exists(input_dir):
            raise QgsProcessingException(
                f"O diretório de entrada não existe: {input_dir}")

        feedback.pushInfo("Iniciando processamento...")

        # === SUA LÓGICA AQUI ===

        feedback.pushInfo("✅ Processamento concluído.")
        return {}

    def createInstance(self):
        """Retorna nova instância do algoritmo (obrigatório)."""
        return self.__class__()
