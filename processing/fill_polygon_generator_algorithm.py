# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Fill Polygon Generator Algorithm
                                 A QGIS plugin
 Professional vectorization toolkit for QGIS
                              -------------------
        begin                : 2026-04-01
        git sha              : $Format:%H$
        copyright            : (C) 2025 by Irlan Souza, 2nd Sgt Brazilian Army
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

from qgis.PyQt.QtCore import QVariant, QCoreApplication
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsDistanceArea,
    QgsFeature,
    QgsFeatureRequest,
    QgsFeatureSink,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsMapLayer,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingMultiStepFeedback,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingParameterVectorLayer,
    QgsProcessingUtils,
    QgsProject,
    QgsSpatialIndex,
    QgsVectorLayer,
    QgsWkbTypes,
)

from qgis import processing


class FillPolygonGeneratorAlgorithm(QgsProcessingAlgorithm):
    """
    Algoritmo de Processamento para gerar polígonos de preenchimento em regiões vazias,
    usando moldura, delimitadores lineares e delimitadores poligonais já existentes.
    """

    FRAME = "FRAME"
    LINE_DELIMITERS = "LINE_DELIMITERS"
    POLYGON_DELIMITERS = "POLYGON_DELIMITERS"
    MIN_AREA = "MIN_AREA"
    ONLY_SELECTED_FRAME = "ONLY_SELECTED_FRAME"
    OUTPUT = "OUTPUT"

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("Processing", string)

    def name(self) -> str:
        return "fill_polygon_generator"

    def displayName(self) -> str:
        return "Gerar Pol\u00edgonos de Preenchimento"

    def group(self) -> str:
        return "Geoprocessamento"

    def groupId(self) -> str:
        return "geoprocessing"

    def shortHelpString(self) -> str:
        return (
            "Este algoritmo gera pol\u00edgonos de preenchimento em regi\u00f5es vazias delimitadas por uma moldura, "
            "por fei\u00e7\u00f5es lineares e por \u00e1reas j\u00e1 ocupadas.\n\n"
            "Fluxo principal:\n"
            "- prepara e corrige a moldura;\n"
            "- converte delimitadores poligonais em linhas auxiliares;\n"
            "- mescla toda a rede delimitadora;\n"
            "- poligoniza as regi\u00f5es internas;\n"
            "- filtra apenas os pol\u00edgonos v\u00e1lidos dentro da moldura e fora das \u00e1reas j\u00e1 existentes.\n\n"
            "Par\u00e2metros:\n"
            "- CAMADA DE MOLDURA: limite geral da \u00e1rea de trabalho;\n"
            "- CAMADAS DELIMITADORAS (LINHA): linhas que particionam a \u00e1rea \u00fatil;\n"
            "- CAMADAS DELIMITADORAS (POL\u00cdGONO): \u00e1reas j\u00e1 ocupadas, usadas para eliminar vazios indevidos;\n"
            "- \u00c1REA M\u00cdNIMA A MANTER: descarta pol\u00edgonos menores que o valor informado;\n"
            "- Usar apenas fei\u00e7\u00f5es selecionadas da Moldura: restringe o processamento \u00e0 sele\u00e7\u00e3o atual da moldura.\n\n"
            "Sa\u00edda:\n"
            "- camada de pol\u00edgonos de preenchimento com campos id e area_otf.\n\n"
            "<b>Autor:</b> Irlan Souza\n"
            "<b>Email:</b> <a href=\"mailto:irlansouza193@gmail.com\">irlansouza193@gmail.com</a>\n"
            "<b>GitHub:</b> <a href=\"https://github.com/irlansouza93\">https://github.com/irlansouza93</a>\n\n"
            "<b><a href=\"https://irlansouza93.github.io/istools-website/\">VISITE NOSSO SITE OFICIAL - CLIQUE AQUI!</a></b>"
        )

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.FRAME,
                "CAMADA DE MOLDURA",
                [QgsProcessing.TypeVectorPolygon],
            )
        )

        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.LINE_DELIMITERS,
                "CAMADAS DELIMITADORAS (LINHA)",
                layerType=QgsProcessing.TypeVectorLine,
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.POLYGON_DELIMITERS,
                "CAMADAS DELIMITADORAS (POL\u00cdGONO)",
                layerType=QgsProcessing.TypeVectorPolygon,
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterNumber(
                self.MIN_AREA,
                "\u00c1REA M\u00cdNIMA A MANTER",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0.0,
                minValue=0.0,
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.ONLY_SELECTED_FRAME,
                "Usar apenas fei\u00e7\u00f5es selecionadas da Moldura",
                defaultValue=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "POL\u00cdGONOS DE PREENCHIMENTO",
                QgsProcessing.TypeVectorPolygon,
            )
        )

    def processAlgorithm(
        self,
        parameters: dict[str, Any],
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict[str, Any]:
        feedback_main = QgsProcessingMultiStepFeedback(12, feedback)

        moldura_layer = self.parameterAsVectorLayer(parameters, self.FRAME, context)
        if moldura_layer is None or not moldura_layer.isValid():
            raise QgsProcessingException("N\u00e3o foi poss\u00edvel carregar a moldura como camada vetorial v\u00e1lida.")

        line_layers = self.parameterAsLayerList(parameters, self.LINE_DELIMITERS, context) or []
        area_layers = self.parameterAsLayerList(parameters, self.POLYGON_DELIMITERS, context) or []
        area_minima = self.parameterAsDouble(parameters, self.MIN_AREA, context)
        only_selected_frame = self.parameterAsBoolean(parameters, self.ONLY_SELECTED_FRAME, context)

        line_layers = [lyr for lyr in line_layers if self._is_valid_vector_layer(lyr)]
        area_layers = [lyr for lyr in area_layers if self._is_valid_vector_layer(lyr)]

        if moldura_layer.featureCount() == 0:
            raise QgsProcessingException("A moldura n\u00e3o possui fei\u00e7\u00f5es.")

        if not line_layers and not area_layers:
            raise QgsProcessingException("Informe ao menos uma camada delimitadora linear ou poligonal.")

        target_crs = moldura_layer.crs()
        if not target_crs.isValid():
            raise QgsProcessingException("O CRS da moldura \u00e9 inv\u00e1lido.")

        feedback_main.pushInfo(f"CRS de refer\u00eancia do processamento: {target_crs.authid()}")
        feedback_main.pushInfo("Preparando moldura...")

        moldura_source = self._restrict_to_selection_if_needed(moldura_layer, only_selected_frame, context, feedback_main)
        moldura_prep = self._prepare_polygon_layer(moldura_source, target_crs, context, feedback_main, "Moldura")

        feedback_main.setCurrentStep(1)
        if feedback_main.isCanceled():
            return {}

        feedback_main.pushInfo("Dissolvendo moldura...")
        moldura_diss = processing.run("native:dissolve", {"INPUT": moldura_prep, "FIELD": [], "SEPARATE_DISJOINT": False, "OUTPUT": "memory:"}, context=context, feedback=feedback_main, is_child_algorithm=True)["OUTPUT"]
        moldura_diss = self._ensure_vector_layer(moldura_diss, context, "moldura dissolvida")

        feedback_main.pushInfo("Convertendo moldura para linhas...")
        moldura_lines = processing.run("native:polygonstolines", {"INPUT": moldura_diss, "OUTPUT": "memory:"}, context=context, feedback=feedback_main, is_child_algorithm=True)["OUTPUT"]
        moldura_lines = self._ensure_vector_layer(moldura_lines, context, "linhas da moldura")

        feedback_main.setCurrentStep(2)
        if feedback_main.isCanceled():
            return {}

        prepared_area_layers = []
        area_line_layers = []
        if area_layers:
            feedback_main.pushInfo("Preparando delimitadores tipo \u00e1rea...")
            for i, lyr in enumerate(area_layers, start=1):
                if feedback_main.isCanceled():
                    return {}
                feedback_main.pushInfo(f"  - [{i}/{len(area_layers)}] {lyr.name()}")
                prep = self._prepare_polygon_layer(lyr, target_crs, context, feedback_main, lyr.name())
                prepared_area_layers.append(prep)
                as_lines = processing.run("native:polygonstolines", {"INPUT": prep, "OUTPUT": "memory:"}, context=context, feedback=feedback_main, is_child_algorithm=True)["OUTPUT"]
                as_lines = self._ensure_vector_layer(as_lines, context, "delimita\u00e7\u00e3o de \u00e1rea")
                area_line_layers.append(as_lines)

        feedback_main.setCurrentStep(3)
        if feedback_main.isCanceled():
            return {}

        prepared_line_layers = []
        if line_layers:
            feedback_main.pushInfo("Preparando delimitadores tipo linha...")
            for i, lyr in enumerate(line_layers, start=1):
                if feedback_main.isCanceled():
                    return {}
                feedback_main.pushInfo(f"  - [{i}/{len(line_layers)}] {lyr.name()}")
                prep_line = self._prepare_line_layer(lyr, target_crs, context, feedback_main, lyr.name())
                prepared_line_layers.append(prep_line)

        feedback_main.setCurrentStep(4)
        if feedback_main.isCanceled():
            return {}

        all_line_layers = [moldura_lines] + area_line_layers + prepared_line_layers
        if not all_line_layers:
            raise QgsProcessingException("Nenhum delimitador linear p\u00f4de ser montado.")

        feedback_main.pushInfo("Mesclando linhas...")
        merged_lines = processing.run("native:mergevectorlayers", {"LAYERS": all_line_layers, "CRS": target_crs, "OUTPUT": "memory:"}, context=context, feedback=feedback_main, is_child_algorithm=True)["OUTPUT"]
        feedback_main.pushInfo("Corrigindo geometrias das linhas mescladas...")
        merged_lines_fix = processing.run("native:fixgeometries", {"INPUT": merged_lines, "METHOD": 0, "OUTPUT": "memory:"}, context=context, feedback=feedback_main, is_child_algorithm=True)["OUTPUT"]
        feedback_main.pushInfo("Convertendo multipartes em partes simples...")
        merged_lines_single = processing.run("native:multiparttosingleparts", {"INPUT": merged_lines_fix, "OUTPUT": "memory:"}, context=context, feedback=feedback_main, is_child_algorithm=True)["OUTPUT"]

        feedback_main.setCurrentStep(5)
        if feedback_main.isCanceled():
            return {}

        feedback_main.pushInfo("Poligonizando...")
        polygonized = processing.run("native:polygonize", {"INPUT": merged_lines_single, "KEEP_FIELDS": False, "OUTPUT": "memory:"}, context=context, feedback=feedback_main, is_child_algorithm=True)["OUTPUT"]
        feedback_main.pushInfo("Corrigindo pol\u00edgonos gerados...")
        polygonized_fix = processing.run("native:fixgeometries", {"INPUT": polygonized, "METHOD": 1, "OUTPUT": "memory:"}, context=context, feedback=feedback_main, is_child_algorithm=True)["OUTPUT"]
        feedback_main.pushInfo("Convertendo pol\u00edgonos multipartes em partes simples...")
        polygonized_single = processing.run("native:multiparttosingleparts", {"INPUT": polygonized_fix, "OUTPUT": "memory:"}, context=context, feedback=feedback_main, is_child_algorithm=True)["OUTPUT"]
        polygonized_single = self._ensure_vector_layer(polygonized_single, context, "polygonized_single")

        feedback_main.setCurrentStep(6)
        if feedback_main.isCanceled():
            return {}

        feedback_main.pushInfo("Unificando geometria da moldura...")
        moldura_geom = self._collect_unary_union_geom(moldura_diss, feedback_main)
        if moldura_geom is None or moldura_geom.isNull() or moldura_geom.isEmpty():
            raise QgsProcessingException("N\u00e3o foi poss\u00edvel unificar a geometria da moldura.")
        moldura_engine = QgsGeometry.createGeometryEngine(moldura_geom.constGet())
        moldura_engine.prepareGeometry()

        feedback_main.setCurrentStep(7)
        if feedback_main.isCanceled():
            return {}

        area_entries = []
        if prepared_area_layers:
            feedback_main.pushInfo("Criando \u00edndices espaciais das \u00e1reas existentes...")
            area_entries = self._build_area_indexes(prepared_area_layers, feedback_main)

        fields = QgsFields()
        fields.append(QgsField("id", QVariant.Int))
        fields.append(QgsField("area_otf", QVariant.Double, len=20, prec=3))
        sink, dest_id = self.parameterAsSink(parameters, self.OUTPUT, context, fields, QgsWkbTypes.MultiPolygon, target_crs)
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        dist_area = self._create_distance_area(target_crs, context)
        feedback_main.setCurrentStep(8)
        if feedback_main.isCanceled():
            return {}

        total = max(1, polygonized_single.featureCount())
        created = processed = skipped_outside = skipped_existing = skipped_small = skipped_invalid = 0
        feedback_main.pushInfo("Filtrando pol\u00edgonos vazios v\u00e1lidos...")

        for feat in polygonized_single.getFeatures(QgsFeatureRequest().setNoAttributes()):
            if feedback_main.isCanceled():
                break
            processed += 1
            geom = feat.geometry()
            if not geom or geom.isNull() or geom.isEmpty():
                skipped_invalid += 1
                self._set_loop_progress(feedback_main, processed, total)
                continue
            if not geom.isGeosValid():
                geom = geom.makeValid()
                if not geom or geom.isNull() or geom.isEmpty():
                    skipped_invalid += 1
                    self._set_loop_progress(feedback_main, processed, total)
                    continue
            if QgsWkbTypes.geometryType(geom.wkbType()) != QgsWkbTypes.PolygonGeometry:
                skipped_invalid += 1
                self._set_loop_progress(feedback_main, processed, total)
                continue
            rep_point = geom.pointOnSurface()
            if not rep_point or rep_point.isNull() or rep_point.isEmpty():
                skipped_invalid += 1
                self._set_loop_progress(feedback_main, processed, total)
                continue
            if not moldura_engine.contains(rep_point.constGet()):
                skipped_outside += 1
                self._set_loop_progress(feedback_main, processed, total)
                continue
            if self._point_inside_any_area(rep_point, area_entries):
                skipped_existing += 1
                self._set_loop_progress(feedback_main, processed, total)
                continue
            area_value = dist_area.measureArea(geom)
            if area_value <= 0 or area_value < area_minima:
                skipped_small += 1
                self._set_loop_progress(feedback_main, processed, total)
                continue
            geom_clean = self._force_multipolygon(geom)
            if geom_clean is None or geom_clean.isNull() or geom_clean.isEmpty():
                skipped_invalid += 1
                self._set_loop_progress(feedback_main, processed, total)
                continue
            out_feat = QgsFeature(fields)
            out_feat.setGeometry(geom_clean)
            out_feat["id"] = created + 1
            out_feat["area_otf"] = float(area_value)
            sink.addFeature(out_feat, QgsFeatureSink.FastInsert)
            created += 1
            self._set_loop_progress(feedback_main, processed, total)

        feedback_main.setCurrentStep(9)
        feedback_main.pushInfo("Processamento conclu\u00eddo.")
        feedback_main.pushInfo(f"Candidatos processados: {processed}")
        feedback_main.pushInfo(f"Pol\u00edgonos gerados: {created}")
        feedback_main.pushInfo(f"Descartados fora da moldura: {skipped_outside}")
        feedback_main.pushInfo(f"Descartados dentro de \u00e1reas existentes: {skipped_existing}")
        feedback_main.pushInfo(f"Descartados por \u00e1rea nula/menor que m\u00ednima: {skipped_small}")
        feedback_main.pushInfo(f"Descartados por geometria inv\u00e1lida: {skipped_invalid}")
        return {self.OUTPUT: dest_id}

    def createInstance(self):
        return self.__class__()

    def _is_valid_vector_layer(self, layer: QgsMapLayer) -> bool:
        return isinstance(layer, QgsVectorLayer) and layer.isValid()

    def _set_loop_progress(self, feedback: QgsProcessingFeedback, current: int, total: int) -> None:
        total = max(total, 1)
        feedback.setProgress(int((current / total) * 100))

    def _restrict_to_selection_if_needed(self, layer: QgsVectorLayer, only_selected: bool, context: QgsProcessingContext, feedback: QgsProcessingFeedback) -> QgsVectorLayer:
        if not only_selected or layer.selectedFeatureCount() == 0:
            return layer
        feedback.pushInfo("Exportando sele\u00e7\u00e3o atual da moldura para processamento.")
        extracted = processing.run("native:saveselectedfeatures", {"INPUT": layer, "OUTPUT": "memory:"}, context=context, feedback=feedback, is_child_algorithm=True)["OUTPUT"]
        return self._ensure_vector_layer(extracted, context, "moldura selecionada")

    def _prepare_polygon_layer(self, layer: QgsVectorLayer, target_crs: QgsCoordinateReferenceSystem, context: QgsProcessingContext, feedback: QgsProcessingFeedback, label: str) -> QgsVectorLayer:
        current = layer
        if current.crs().isValid() and current.crs() != target_crs:
            feedback.pushInfo(f"Reprojetando camada poligonal '{label}' para {target_crs.authid()}...")
            current = processing.run("native:reprojectlayer", {"INPUT": current, "TARGET_CRS": target_crs, "OUTPUT": "memory:"}, context=context, feedback=feedback, is_child_algorithm=True)["OUTPUT"]
            current = self._ensure_vector_layer(current, context, label)
        current = processing.run("native:fixgeometries", {"INPUT": current, "METHOD": 1, "OUTPUT": "memory:"}, context=context, feedback=feedback, is_child_algorithm=True)["OUTPUT"]
        current = self._ensure_vector_layer(current, context, label)
        current = processing.run("native:multiparttosingleparts", {"INPUT": current, "OUTPUT": "memory:"}, context=context, feedback=feedback, is_child_algorithm=True)["OUTPUT"]
        return self._ensure_vector_layer(current, context, label)

    def _prepare_line_layer(self, layer: QgsVectorLayer, target_crs: QgsCoordinateReferenceSystem, context: QgsProcessingContext, feedback: QgsProcessingFeedback, label: str) -> QgsVectorLayer:
        current = layer
        if current.crs().isValid() and current.crs() != target_crs:
            feedback.pushInfo(f"Reprojetando camada linear '{label}' para {target_crs.authid()}...")
            current = processing.run("native:reprojectlayer", {"INPUT": current, "TARGET_CRS": target_crs, "OUTPUT": "memory:"}, context=context, feedback=feedback, is_child_algorithm=True)["OUTPUT"]
            current = self._ensure_vector_layer(current, context, label)
        current = processing.run("native:fixgeometries", {"INPUT": current, "METHOD": 0, "OUTPUT": "memory:"}, context=context, feedback=feedback, is_child_algorithm=True)["OUTPUT"]
        current = self._ensure_vector_layer(current, context, label)
        current = processing.run("native:multiparttosingleparts", {"INPUT": current, "OUTPUT": "memory:"}, context=context, feedback=feedback, is_child_algorithm=True)["OUTPUT"]
        return self._ensure_vector_layer(current, context, label)

    def _collect_unary_union_geom(self, layer: QgsVectorLayer, feedback: QgsProcessingFeedback) -> Optional[QgsGeometry]:
        geoms = []
        for feat in layer.getFeatures(QgsFeatureRequest().setNoAttributes()):
            if feedback.isCanceled():
                return None
            geom = feat.geometry()
            if not geom or geom.isNull() or geom.isEmpty():
                continue
            if not geom.isGeosValid():
                geom = geom.makeValid()
                if not geom or geom.isNull() or geom.isEmpty():
                    continue
            geoms.append(geom)
        if not geoms:
            return None
        union_geom = QgsGeometry.unaryUnion(geoms)
        if union_geom and not union_geom.isEmpty() and not union_geom.isGeosValid():
            union_geom = union_geom.makeValid()
        return union_geom

    def _build_area_indexes(self, area_layers: list[QgsVectorLayer], feedback: QgsProcessingFeedback) -> list[dict]:
        entries = []
        for i, layer in enumerate(area_layers, start=1):
            if feedback.isCanceled():
                break
            feedback.pushInfo(f"Montando \u00edndice espacial [{i}/{len(area_layers)}]: {layer.name()}")
            feature_map = {}
            feats = []
            for feat in layer.getFeatures(QgsFeatureRequest().setNoAttributes()):
                geom = feat.geometry()
                if not geom or geom.isNull() or geom.isEmpty():
                    continue
                if not geom.isGeosValid():
                    geom = geom.makeValid()
                    if not geom or geom.isNull() or geom.isEmpty():
                        continue
                clone = QgsFeature()
                clone.setId(feat.id())
                clone.setGeometry(geom)
                feats.append(clone)
                feature_map[feat.id()] = geom
            if not feats:
                continue
            index = QgsSpatialIndex()
            for feat in feats:
                index.addFeature(feat)
            entries.append({"index": index, "geometries": feature_map})
        return entries

    def _point_inside_any_area(self, point_geom: QgsGeometry, area_entries: list[dict]) -> bool:
        if not point_geom or point_geom.isNull() or point_geom.isEmpty():
            return False
        bbox = point_geom.boundingBox()
        for entry in area_entries:
            candidate_ids = entry["index"].intersects(bbox)
            if not candidate_ids:
                continue
            for fid in candidate_ids:
                area_geom = entry["geometries"].get(fid)
                if area_geom is not None and area_geom.contains(point_geom):
                    return True
        return False

    def _force_multipolygon(self, geom: QgsGeometry) -> Optional[QgsGeometry]:
        if geom is None or geom.isNull() or geom.isEmpty():
            return None
        g = QgsGeometry(geom)
        if QgsWkbTypes.geometryType(g.wkbType()) != QgsWkbTypes.PolygonGeometry:
            return None
        if not QgsWkbTypes.isMultiType(g.wkbType()):
            ok = g.convertToMultiType()
            if not ok:
                return None
        return g

    def _create_distance_area(self, source_crs: QgsCoordinateReferenceSystem, context: QgsProcessingContext) -> QgsDistanceArea:
        dist = QgsDistanceArea()
        dist.setSourceCrs(source_crs, context.transformContext())
        ellipsoid = QgsProject.instance().ellipsoid()
        dist.setEllipsoid(ellipsoid if ellipsoid else "WGS84")
        return dist

    def _ensure_vector_layer(self, layer_or_source, context, layer_name="camada") -> QgsVectorLayer:
        if isinstance(layer_or_source, QgsVectorLayer):
            return layer_or_source
        if isinstance(layer_or_source, str):
            lyr = QgsProcessingUtils.mapLayerFromString(layer_or_source, context)
            if lyr is None or not isinstance(lyr, QgsVectorLayer):
                raise QgsProcessingException(f"N\u00e3o foi poss\u00edvel converter '{layer_name}' para QgsVectorLayer.")
            return lyr
        raise QgsProcessingException(f"O objeto '{layer_name}' n\u00e3o \u00e9 uma camada vetorial v\u00e1lida.")
