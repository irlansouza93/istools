"""
Ferramenta QGIS - Gerar polígonos em regiões vazias
Compatível com QGIS 3.40.x
Estrutura no padrão QgsProcessingAlgorithm / template ISTools
"""

from typing import Any, Optional


from qgis.PyQt.QtCore import QVariant
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
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber,
    QgsProcessingUtils,
    QgsProject,
    QgsSpatialIndex,
    QgsVectorLayer,
    QgsWkbTypes,
)

from qgis import processing


class GerarPoligonosBuracosAlgorithm(QgsProcessingAlgorithm):

    INPUT_MOLDURA = "INPUT_MOLDURA"
    INPUT_LINHAS = "INPUT_LINHAS"
    INPUT_AREAS = "INPUT_AREAS"
    INPUT_AREA_MINIMA = "INPUT_AREA_MINIMA"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "gerarpoligonosburacos"

    def displayName(self) -> str:
        return "Gerar polígonos em regiões vazias"

    def group(self) -> str:
        return "ISTools"

    def groupId(self) -> str:
        return "istools"

    def shortHelpString(self) -> str:
        return (
            "Gera polígonos temporários nas regiões vazias delimitadas por moldura, "
            "linhas e áreas existentes.\n\n"
            "Saída com campos:\n"
            "- id\n"
            "- area_otf"
        )

    def initAlgorithm(self, config: Optional[dict[str, Any]] = None):
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUT_MOLDURA,
                "Limite geográfico (moldura)",
                [QgsProcessing.SourceType.TypeVectorPolygon],
            )
        )

        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT_LINHAS,
                "Delimitadores tipo linha",
                layerType=QgsProcessing.TypeVectorLine,
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.INPUT_AREAS,
                "Delimitadores tipo área",
                layerType=QgsProcessing.TypeVectorPolygon,
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterNumber(
                self.INPUT_AREA_MINIMA,
                "Área mínima a manter",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0.0,
                minValue=0.0,
                optional=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Polígonos vazios gerados",
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

        # ------------------------------------------------------------------
        # 1) ENTRADAS
        # ------------------------------------------------------------------
        moldura_layer = self.parameterAsVectorLayer(parameters, self.INPUT_MOLDURA, context)
        if moldura_layer is None or not moldura_layer.isValid():
            raise QgsProcessingException(
                "Não foi possível carregar a moldura como camada vetorial válida."
            )

        line_layers = self.parameterAsLayerList(parameters, self.INPUT_LINHAS, context) or []
        area_layers = self.parameterAsLayerList(parameters, self.INPUT_AREAS, context) or []
        area_minima = self.parameterAsDouble(parameters, self.INPUT_AREA_MINIMA, context)

        line_layers = [lyr for lyr in line_layers if self._is_valid_vector_layer(lyr)]
        area_layers = [lyr for lyr in area_layers if self._is_valid_vector_layer(lyr)]

        if moldura_layer.featureCount() == 0:
            raise QgsProcessingException("A moldura não possui feições.")

        target_crs = moldura_layer.crs()
        if not target_crs.isValid():
            raise QgsProcessingException("O CRS da moldura é inválido.")

        feedback_main.pushInfo(f"CRS de referência do processamento: {target_crs.authid()}")

        # ------------------------------------------------------------------
        # 2) PREPARAR MOLDURA
        # ------------------------------------------------------------------
        feedback_main.pushInfo("Preparando moldura...")
        moldura_prep = self._prepare_polygon_layer(
            moldura_layer,
            target_crs,
            context,
            feedback_main,
            "Moldura"
        )

        feedback_main.setCurrentStep(1)
        if feedback_main.isCanceled():
            return {}

        feedback_main.pushInfo("Dissolvendo moldura...")
        moldura_diss = processing.run(
            "native:dissolve",
            {
                "INPUT": moldura_prep,
                "FIELD": [],
                "SEPARATE_DISJOINT": False,
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback_main,
            is_child_algorithm=True,
        )["OUTPUT"]
        moldura_diss = self._ensure_vector_layer(moldura_diss, context, "moldura dissolvida")

        feedback_main.pushInfo("Convertendo moldura para linhas...")
        moldura_lines = processing.run(
            "native:polygonstolines",
            {
                "INPUT": moldura_diss,
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback_main,
            is_child_algorithm=True,
        )["OUTPUT"]
        moldura_lines = self._ensure_vector_layer(moldura_lines, context, "linhas da moldura")

        # ------------------------------------------------------------------
        # 3) PREPARAR ÁREAS DELIMITADORAS
        # ------------------------------------------------------------------
        feedback_main.setCurrentStep(2)
        if feedback_main.isCanceled():
            return {}

        prepared_area_layers = []
        area_line_layers = []

        if area_layers:
            feedback_main.pushInfo("Preparando delimitadores tipo área...")
            for i, lyr in enumerate(area_layers, start=1):
                if feedback_main.isCanceled():
                    return {}

                feedback_main.pushInfo(f"  - [{i}/{len(area_layers)}] {lyr.name()}")
                prep = self._prepare_polygon_layer(
                    lyr,
                    target_crs,
                    context,
                    feedback_main,
                    lyr.name()
                )
                prepared_area_layers.append(prep)

                as_lines = processing.run(
                    "native:polygonstolines",
                    {
                        "INPUT": prep,
                        "OUTPUT": "memory:",
                    },
                    context=context,
                    feedback=feedback_main,
                    is_child_algorithm=True,
                )["OUTPUT"]
                as_lines = self._ensure_vector_layer(as_lines, context, "delimitação de área")
                area_line_layers.append(as_lines)

        # ------------------------------------------------------------------
        # 4) PREPARAR LINHAS DELIMITADORAS
        # ------------------------------------------------------------------
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
                prep_line = self._prepare_line_layer(
                    lyr,
                    target_crs,
                    context,
                    feedback_main,
                    lyr.name()
                )
                prepared_line_layers.append(prep_line)

        # ------------------------------------------------------------------
        # 5) MESCLAR TODAS AS LINHAS
        # ------------------------------------------------------------------
        feedback_main.setCurrentStep(4)
        if feedback_main.isCanceled():
            return {}

        all_line_layers = [moldura_lines] + area_line_layers + prepared_line_layers
        if not all_line_layers:
            raise QgsProcessingException("Nenhum delimitador linear pôde ser montado.")

        feedback_main.pushInfo("Mesclando linhas...")
        merged_lines = processing.run(
            "native:mergevectorlayers",
            {
                "LAYERS": all_line_layers,
                "CRS": target_crs,
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback_main,
            is_child_algorithm=True,
        )["OUTPUT"]

        feedback_main.pushInfo("Corrigindo geometrias das linhas mescladas...")
        merged_lines_fix = processing.run(
            "native:fixgeometries",
            {
                "INPUT": merged_lines,
                "METHOD": 0,
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback_main,
            is_child_algorithm=True,
        )["OUTPUT"]

        feedback_main.pushInfo("Convertendo multipartes em partes simples...")
        merged_lines_single = processing.run(
            "native:multiparttosingleparts",
            {
                "INPUT": merged_lines_fix,
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback_main,
            is_child_algorithm=True,
        )["OUTPUT"]

        # ------------------------------------------------------------------
        # 6) POLIGONIZAR
        # ------------------------------------------------------------------
        feedback_main.setCurrentStep(5)
        if feedback_main.isCanceled():
            return {}

        feedback_main.pushInfo("Poligonizando...")
        polygonized = processing.run(
            "native:polygonize",
            {
                "INPUT": merged_lines_single,
                "KEEP_FIELDS": False,
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback_main,
            is_child_algorithm=True,
        )["OUTPUT"]

        feedback_main.pushInfo("Corrigindo polígonos gerados...")
        polygonized_fix = processing.run(
            "native:fixgeometries",
            {
                "INPUT": polygonized,
                "METHOD": 1,
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback_main,
            is_child_algorithm=True,
        )["OUTPUT"]

        feedback_main.pushInfo("Convertendo polígonos multipartes em partes simples...")
        polygonized_single = processing.run(
            "native:multiparttosingleparts",
            {
                "INPUT": polygonized_fix,
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback_main,
            is_child_algorithm=True,
        )["OUTPUT"]
        polygonized_single = self._ensure_vector_layer(polygonized_single, context, "polygonized_single")

        # ------------------------------------------------------------------
        # 7) GEOMETRIA UNIFICADA DA MOLDURA
        # ------------------------------------------------------------------
        feedback_main.setCurrentStep(6)
        if feedback_main.isCanceled():
            return {}

        feedback_main.pushInfo("Unificando geometria da moldura...")
        moldura_diss = self._ensure_vector_layer(moldura_diss, context, "moldura dissolvida")
        moldura_geom = self._collect_unary_union_geom(moldura_diss, feedback_main)
        if moldura_geom is None or moldura_geom.isNull() or moldura_geom.isEmpty():
            raise QgsProcessingException("Não foi possível unificar a geometria da moldura.")

        moldura_engine = QgsGeometry.createGeometryEngine(moldura_geom.constGet())
        moldura_engine.prepareGeometry()

        # ------------------------------------------------------------------
        # 8) DISSOLVER ÁREAS EXISTENTES E INDEXAR
        # ------------------------------------------------------------------
        feedback_main.setCurrentStep(7)
        if feedback_main.isCanceled():
            return {}

        area_entries = []
        if prepared_area_layers:
            feedback_main.pushInfo("Criando índices espaciais das áreas existentes...")
            area_entries = self._build_area_indexes(prepared_area_layers, feedback_main)

        # ------------------------------------------------------------------
        # 9) SAÍDA
        # ------------------------------------------------------------------
        fields = QgsFields()
        fields.append(QgsField("id", QVariant.Int))
        fields.append(QgsField("area_otf", QVariant.Double, len=20, prec=3))

        sink, dest_id = self.parameterAsSink(
            parameters,
            self.OUTPUT,
            context,
            fields,
            QgsWkbTypes.MultiPolygon,
            target_crs,
        )
        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.OUTPUT))

        dist_area = self._create_distance_area(target_crs, context)

        # ------------------------------------------------------------------
        # 10) FILTRAGEM DOS BURACOS
        # ------------------------------------------------------------------
        feedback_main.setCurrentStep(8)
        if feedback_main.isCanceled():
            return {}

        total = max(1, polygonized_single.featureCount())
        created = 0
        processed = 0
        skipped_outside = 0
        skipped_existing = 0
        skipped_small = 0
        skipped_invalid = 0

        feedback_main.pushInfo("Filtrando polígonos vazios válidos...")

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

        # ------------------------------------------------------------------
        # 11) RESUMO
        # ------------------------------------------------------------------
        feedback_main.setCurrentStep(9)
        feedback_main.pushInfo("Processamento concluído.")
        feedback_main.pushInfo(f"Candidatos processados: {processed}")
        feedback_main.pushInfo(f"Polígonos gerados: {created}")
        feedback_main.pushInfo(f"Descartados fora da moldura: {skipped_outside}")
        feedback_main.pushInfo(f"Descartados dentro de áreas existentes: {skipped_existing}")
        feedback_main.pushInfo(f"Descartados por área nula/menor que mínima: {skipped_small}")
        feedback_main.pushInfo(f"Descartados por geometria inválida: {skipped_invalid}")

        return {self.OUTPUT: dest_id}

    def createInstance(self):
        return self.__class__()

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _is_valid_vector_layer(self, layer: QgsMapLayer) -> bool:
        return isinstance(layer, QgsVectorLayer) and layer.isValid()

    def _set_loop_progress(self, feedback: QgsProcessingFeedback, current: int, total: int) -> None:
        total = max(total, 1)
        feedback.setProgress(int((current / total) * 100))

    def _prepare_polygon_layer(
        self,
        layer: QgsVectorLayer,
        target_crs: QgsCoordinateReferenceSystem,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
        label: str,
    ) -> QgsVectorLayer:
        current = layer

        if current.crs().isValid() and current.crs() != target_crs:
            feedback.pushInfo(f"Reprojetando camada poligonal '{label}' para {target_crs.authid()}...")
            current = processing.run(
                "native:reprojectlayer",
                {
                    "INPUT": current,
                    "TARGET_CRS": target_crs,
                    "OUTPUT": "memory:",
                },
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )["OUTPUT"]
            current = self._ensure_vector_layer(current, context, label)

        current = processing.run(
            "native:fixgeometries",
            {
                "INPUT": current,
                "METHOD": 1,
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )["OUTPUT"]
        current = self._ensure_vector_layer(current, context, label)

        current = processing.run(
            "native:multiparttosingleparts",
            {
                "INPUT": current,
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )["OUTPUT"]
        current = self._ensure_vector_layer(current, context, label)

        return current

    def _prepare_line_layer(
        self,
        layer: QgsVectorLayer,
        target_crs: QgsCoordinateReferenceSystem,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
        label: str,
    ) -> QgsVectorLayer:
        current = layer

        if current.crs().isValid() and current.crs() != target_crs:
            feedback.pushInfo(f"Reprojetando camada linear '{label}' para {target_crs.authid()}...")
            current = processing.run(
                "native:reprojectlayer",
                {
                    "INPUT": current,
                    "TARGET_CRS": target_crs,
                    "OUTPUT": "memory:",
                },
                context=context,
                feedback=feedback,
                is_child_algorithm=True,
            )["OUTPUT"]
            current = self._ensure_vector_layer(current, context, label)

        current = processing.run(
            "native:fixgeometries",
            {
                "INPUT": current,
                "METHOD": 0,
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )["OUTPUT"]
        current = self._ensure_vector_layer(current, context, label)

        current = processing.run(
            "native:multiparttosingleparts",
            {
                "INPUT": current,
                "OUTPUT": "memory:",
            },
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )["OUTPUT"]
        current = self._ensure_vector_layer(current, context, label)

        return current

    def _collect_unary_union_geom(
        self,
        layer: QgsVectorLayer,
        feedback: QgsProcessingFeedback,
    ) -> Optional[QgsGeometry]:
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

    def _build_area_indexes(
        self,
        area_layers: list[QgsVectorLayer],
        feedback: QgsProcessingFeedback,
    ) -> list[dict]:
        entries = []

        for i, layer in enumerate(area_layers, start=1):
            if feedback.isCanceled():
                break

            feedback.pushInfo(f"Montando índice espacial [{i}/{len(area_layers)}]: {layer.name()}")

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
            for f in feats:
                index.addFeature(f)
            entries.append(
                {
                    "index": index,
                    "geometries": feature_map,
                }
            )

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
                if area_geom is None:
                    continue

                if area_geom.contains(point_geom):
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

    def _create_distance_area(
        self,
        source_crs: QgsCoordinateReferenceSystem,
        context: QgsProcessingContext,
    ) -> QgsDistanceArea:
        dist = QgsDistanceArea()
        dist.setSourceCrs(source_crs, context.transformContext())

        ellipsoid = QgsProject.instance().ellipsoid()
        dist.setEllipsoid(ellipsoid if ellipsoid else "WGS84")
        return dist
    
    def _ensure_vector_layer(self, layer_or_source, context, layer_name="camada"):
        if isinstance(layer_or_source, QgsVectorLayer):
            return layer_or_source

        if isinstance(layer_or_source, str):
            lyr = QgsProcessingUtils.mapLayerFromString(layer_or_source, context)
            if lyr is None or not isinstance(lyr, QgsVectorLayer):
                raise QgsProcessingException(
                    f"Não foi possível converter '{layer_name}' para QgsVectorLayer."
                )
            return lyr

        raise QgsProcessingException(
            f"O objeto '{layer_name}' não é uma camada vetorial válida."
        )