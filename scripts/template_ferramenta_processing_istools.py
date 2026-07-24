# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Template Processing Algorithm
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

from typing import Any, Optional

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterVectorLayer,
)


class ISToolsTemplateProcessingAlgorithm(QgsProcessingAlgorithm):
    """
    Template base para algoritmos da caixa de processamento do ISTools.

    Use este arquivo como refer?ncia para novas ferramentas que ser?o registradas
    no provider do plugin e executadas a partir do Processing Toolbox.
    """

    INPUT = "INPUT"
    USE_SELECTION = "USE_SELECTION"
    OUTPUT = "OUTPUT"

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("Processing", string)

    def name(self) -> str:
        return "template_processing_algorithm"

    def displayName(self) -> str:
        return "Template de Algoritmo de Processamento"

    def group(self) -> str:
        return "Geoprocessamento"

    def groupId(self) -> str:
        return "geoprocessing"

    def shortHelpString(self) -> str:
        return (
            "Template textual para cria??o de algoritmos de Processing no padr?o do ISTools.\n\n"
            "Estrutura recomendada:\n"
            "- declarar constantes dos par?metros;\n"
            "- implementar name/displayName/group/groupId;\n"
            "- descrever a ferramenta em shortHelpString;\n"
            "- criar par?metros em initAlgorithm;\n"
            "- executar a l?gica em processAlgorithm;\n"
            "- registrar o algoritmo no provider.\n\n"
            "<b>Autor:</b> Irlan Souza\n"
            "<b>Email:</b> <a href=\"mailto:irlansouza193@gmail.com\">irlansouza193@gmail.com</a>\n"
            "<b>GitHub:</b> <a href=\"https://github.com/irlansouza93\">https://github.com/irlansouza93</a>\n\n"
            "<b>?? <a href=\"https://irlansouza93.github.io/istools-website/\">??VISITE NOSSO SITE OFICIAL - CLIQUE AQUI! ??</a></b>"
        )

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT,
                "CAMADA DE ENTRADA",
                [QgsProcessing.TypeVectorAnyGeometry],
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.USE_SELECTION,
                "Usar apenas fei??es selecionadas",
                defaultValue=False,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "SA?DA",
                QgsProcessing.TypeVectorAnyGeometry,
            )
        )

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:
        input_layer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        use_selection = self.parameterAsBoolean(parameters, self.USE_SELECTION, context)

        if input_layer is None:
            raise QgsProcessingException("A camada de entrada ? obrigat?ria.")

        feedback.pushInfo(f"Camada de entrada: {input_layer.name()}")
        feedback.pushInfo(f"Usar sele??o: {use_selection}")
        feedback.pushInfo("Substitua este bloco pela l?gica real do algoritmo.")

        sink, dest_id = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            input_layer.fields(),
            input_layer.wkbType(),
            input_layer.crs(),
        )

        if sink is None:
            raise QgsProcessingException("N?o foi poss?vel criar a sa?da do algoritmo.")

        return {self.OUTPUT: dest_id}

    def createInstance(self):
        return ISToolsTemplateProcessingAlgorithm()
