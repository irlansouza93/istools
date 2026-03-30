# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Clip by Frame Algorithm
                                 A QGIS plugin
 Professional vectorization toolkit for QGIS
                              -------------------
        begin                : 2026-03-22
        copyright            : (C) 2025 by Irlan Souza, 2° Sgt Brazilian Army
        email                : irlansouza193@gmail.com
 ***************************************************************************/
"""

from typing import Any, Optional
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterBoolean,
    QgsProcessingException,
    QgsProject,
    QgsProcessingContext,
    QgsProcessingFeedback
)
from ..clip_by_frame_logic import ClipByFrameLogic

class ClipByFrameAlgorithm(QgsProcessingAlgorithm):
    """
    Algoritmo de Processamento para recortar feições de uma camada usando uma moldura
    carregada no QGIS, mantendo as alterações em modo de edição.
    """
    INPUTS = 'INPUTS'
    FRAME = 'FRAME'
    ONLY_SELECTED_FRAME = 'ONLY_SELECTED_FRAME'
    ONLY_SELECTED_TARGETS = 'ONLY_SELECTED_TARGETS'
    MAKE_VALID = 'MAKE_VALID'
    CLEAN_ZERO_AREA = 'CLEAN_ZERO_AREA'

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("Processing", string)

    def name(self) -> str:
        return 'clip_by_frame'

    def displayName(self) -> str:
        return self.tr('Recortar por Moldura (Multicamadas)')

    def group(self) -> str:
        return self.tr('Geoprocessamento')

    def groupId(self) -> str:
        return 'geoprocessing'

    def shortHelpString(self) -> str:
        return (
            "Ferramenta de recorte geográfico 'In-Place' Multi-camadas (Modifica as camadas originais).\n\n"
            "<b>Parâmetros:</b>\n"
            "- <b>Camadas de Dados:</b> Uma ou mais camadas que serão recortadas.\n"
            "- <b>Camada de Moldura:</b> Polígono que define o limite.\n"
            "- <b>Somente Selecionadas (Moldura):</b> Usa apenas feições selecionadas da moldura.\n"
            "- <b>Somente Selecionadas (Dados):</b> Processa apenas feições selecionadas nas camadas alvo.\n"
            "- <b>Corrigir Geometrias:</b> Tenta corrigir geometrias inválidas automaticamente.\n"
            "- <b>Limpar Área Zero:</b> Remove polígonos degenerados/vazios após o recorte.\n\n"
            "<b>Autor:</b> Irlan Souza\n"
            "<b>Email:</b> <a href=\"mailto:irlansouza193@gmail.com\">irlansouza193@gmail.com</a>\n"
            "<b>GitHub:</b> <a href=\"https://github.com/irlansouza93\">https://github.com/irlansouza93</a>\n\n"
            "<b>🌐 <a href=\"https://irlansouza93.github.io/istools-website/\">🚀VISITE NOSSO SITE OFICIAL - CLIQUE AQUI! 🚀</a></b>"
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(self.FRAME, 'CAMADA DE MOLDURA', types=[QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterMultipleLayers(self.INPUTS, 'CAMADAS DE DADOS (Serão Modificadas)', layerType=QgsProcessing.TypeVectorAnyGeometry))
        self.addParameter(QgsProcessingParameterBoolean(self.ONLY_SELECTED_FRAME, 'Usar apenas feições selecionadas da Moldura', defaultValue=True))
        self.addParameter(QgsProcessingParameterBoolean(self.ONLY_SELECTED_TARGETS, 'Processar apenas feições selecionadas nas Camadas de Dados', defaultValue=False))
        self.addParameter(QgsProcessingParameterBoolean(self.MAKE_VALID, 'Corrigir geometrias inválidas automaticamente', defaultValue=True))
        self.addParameter(QgsProcessingParameterBoolean(self.CLEAN_ZERO_AREA, 'Limpar polígonos com área zero (slivers)', defaultValue=True))

    def processAlgorithm(self, parameters, context, feedback):
        target_layers = self.parameterAsLayerList(parameters, self.INPUTS, context)
        frame_layer = self.parameterAsVectorLayer(parameters, self.FRAME, context)
        only_selected_frame = self.parameterAsBoolean(parameters, self.ONLY_SELECTED_FRAME, context)
        only_selected_targets = self.parameterAsBoolean(parameters, self.ONLY_SELECTED_TARGETS, context)
        make_valid = self.parameterAsBoolean(parameters, self.MAKE_VALID, context)
        clean_zero_area = self.parameterAsBoolean(parameters, self.CLEAN_ZERO_AREA, context)

        if not target_layers or not frame_layer:
            raise QgsProcessingException("Parametros insuficientes (camadas ou moldura ausentes).")

        total_layers = len(target_layers)
        results_summary = []

        for i, target_layer in enumerate(target_layers):
            if feedback.isCanceled(): break
            
            feedback.pushInfo(f"Processando camada {i+1}/{total_layers}: {target_layer.name()}")
            
            try:
                res = ClipByFrameLogic.process_target_layer(
                    frame_layer,
                    target_layer,
                    use_selected_mask=only_selected_frame,
                    auto_make_valid=make_valid,
                    only_selected_targets=only_selected_targets,
                    clean_zero_area=clean_zero_area,
                    feedback=None # Feedback granular handled inside process_target_loop if passed, but here we manage layers
                )
                
                msg = f"{target_layer.name()}: {res['inside']} mantidas, {res['changed']} recortadas, {res['removed']} removidas."
                results_summary.append(msg)
                feedback.pushInfo(f"  -> {msg}")
                
            except Exception as e:
                err_msg = f"Erro na camada {target_layer.name()}: {str(e)}"
                results_summary.append(err_msg)
                feedback.reportError(err_msg)

        final_msg = " | ".join(results_summary)
        return {'OUTPUT': [l.id() for l in target_layers], 'MSG': final_msg}

    def createInstance(self):
        return ClipByFrameAlgorithm()
