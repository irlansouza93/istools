# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Fill Polygon Generator Logic
                                 A QGIS plugin
 Professional vectorization toolkit for QGIS
                              -------------------
        begin                : 2026-04-01
        copyright            : (C) 2025 by Irlan Souza, 2? Sgt Brazilian Army
        email                : irlansouza193@gmail.com
 ***************************************************************************/
"""

from typing import List, Optional
import uuid

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsProcessingException,
    QgsProject,
    QgsRectangle,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant


class FillPolygonGeneratorLogic:
    @staticmethod
    def extract_polygon_parts(geometry: QgsGeometry) -> List[QgsGeometry]:
        if not geometry or geometry.isNull() or geometry.isEmpty():
            return []

        parts = []
        stack = [QgsGeometry(geometry)]
        while stack:
            current = stack.pop()
            if not current or current.isNull() or current.isEmpty():
                continue

            try:
                collection = current.asGeometryCollection()
            except Exception:
                collection = []

            if collection:
                for sub_geom in collection:
                    stack.append(QgsGeometry(sub_geom))
                continue

            if QgsWkbTypes.geometryType(current.wkbType()) != QgsWkbTypes.PolygonGeometry:
                continue

            try:
                iter_parts = list(current.parts())
            except Exception:
                iter_parts = []

            if iter_parts and len(iter_parts) > 1:
                for part in iter_parts:
                    part_geom = QgsGeometry(part.clone())
                    if part_geom and not part_geom.isEmpty():
                        parts.append(part_geom)
            else:
                parts.append(QgsGeometry(current))

        return parts

    @staticmethod
    def transform_geometry(geometry: QgsGeometry, source_crs: QgsCoordinateReferenceSystem, target_crs: QgsCoordinateReferenceSystem, transform_context) -> QgsGeometry:
        transformed = QgsGeometry(geometry)
        if source_crs.isValid() and target_crs.isValid() and source_crs != target_crs:
            xform = QgsCoordinateTransform(source_crs, target_crs, transform_context)
            transformed.transform(xform)
        return transformed

    @staticmethod
    def build_request(layer, target_rect: Optional[QgsRectangle], target_crs: QgsCoordinateReferenceSystem):
        request = QgsFeatureRequest()
        request.setNoAttributes()
        if target_rect is None or target_rect.isEmpty():
            return request

        source_rect = target_rect
        source_crs = layer.crs()
        if source_crs.isValid() and target_crs.isValid() and source_crs != target_crs:
            xform = QgsCoordinateTransform(target_crs, source_crs, QgsProject.instance().transformContext())
            source_rect = xform.transformBoundingBox(target_rect)

        request.setFilterRect(source_rect)
        return request

    @staticmethod
    def iter_layer_features(layer, request, only_selected: bool):
        if only_selected and layer.selectedFeatureCount() > 0:
            selected_request = QgsFeatureRequest().setFilterFids(layer.selectedFeatureIds())
            selected_request.setNoAttributes()
            return layer.getFeatures(selected_request)
        return layer.getFeatures(request)

    @classmethod
    def build_frame_mask(cls, frame_layer, only_selected_frame: bool, work_crs: QgsCoordinateReferenceSystem, feedback) -> QgsGeometry:
        request = QgsFeatureRequest()
        request.setNoAttributes()
        features = cls.iter_layer_features(frame_layer, request, only_selected_frame)
        geoms = []
        for feature in features:
            if feedback and feedback.isCanceled():
                return QgsGeometry()
            geom = feature.geometry()
            if not geom or geom.isNull() or geom.isEmpty():
                continue
            geom = cls.transform_geometry(geom, frame_layer.crs(), work_crs, QgsProject.instance().transformContext())
            if not geom.isGeosValid():
                geom = geom.makeValid()
            if not geom.isEmpty():
                geoms.append(geom)

        if not geoms:
            raise QgsProcessingException('Nenhuma geometria v?lida de moldura foi encontrada.')

        frame_mask = QgsGeometry.unaryUnion(geoms)
        if frame_mask.isEmpty() or not frame_mask.isGeosValid():
            frame_mask = frame_mask.makeValid()
        if frame_mask.isEmpty():
            raise QgsProcessingException('A geometria da moldura ficou vazia durante o processamento.')
        return frame_mask

    @classmethod
    def collect_geometries(cls, layers, frame_mask_geom: QgsGeometry, work_crs: QgsCoordinateReferenceSystem, only_selected: bool, feedback, polygon_mode: bool = False) -> List[QgsGeometry]:
        geometries = []
        frame_bbox = frame_mask_geom.boundingBox()
        engine = QgsGeometry.createGeometryEngine(frame_mask_geom.constGet())
        if engine is None:
            raise QgsProcessingException('Falha ao criar o motor geom?trico da ?rea de trabalho.')
        engine.prepareGeometry()

        total_layers = max(1, len(layers))
        for index, layer in enumerate(layers, start=1):
            if feedback:
                feedback.pushInfo(f"Coletando geometrias da camada {index}/{total_layers}: {layer.name()}")
            request = cls.build_request(layer, frame_bbox, work_crs)
            for feature in cls.iter_layer_features(layer, request, only_selected):
                if feedback and feedback.isCanceled():
                    return []
                geom = feature.geometry()
                if not geom or geom.isNull() or geom.isEmpty():
                    continue
                geom = cls.transform_geometry(geom, layer.crs(), work_crs, QgsProject.instance().transformContext())
                if geom.isEmpty():
                    continue
                bbox = geom.boundingBox()
                if bbox.isEmpty() or not bbox.intersects(frame_bbox):
                    continue
                if polygon_mode:
                    clipped = geom if frame_bbox.contains(bbox) else geom.clipped(frame_bbox)
                else:
                    if frame_bbox.contains(bbox):
                        clipped = geom
                    else:
                        if not engine.intersects(geom.constGet()):
                            continue
                        clipped = geom.intersection(frame_mask_geom)
                if clipped.isEmpty():
                    continue
                if not clipped.isGeosValid():
                    clipped = clipped.makeValid()
                if clipped.isEmpty():
                    continue
                if polygon_mode:
                    geometries.extend(cls.extract_polygon_parts(clipped))
                else:
                    geometries.append(QgsGeometry(clipped))
        return geometries

    @classmethod
    def generate_fill_polygons(
        cls,
        frame_layer,
        line_layers,
        polygon_layers,
        only_selected_frame: bool,
        only_selected_delimiters: bool,
        feedback,
    ):
        work_crs = frame_layer.crs() if frame_layer.crs().isValid() else QgsProject.instance().crs()
        frame_mask = cls.build_frame_mask(frame_layer, only_selected_frame, work_crs, feedback)
        if feedback:
            feedback.pushInfo('Moldura de trabalho preparada.')

        polygon_delimiters = cls.collect_geometries(
            polygon_layers,
            frame_mask,
            work_crs,
            only_selected_delimiters,
            feedback,
            polygon_mode=True,
        ) if polygon_layers else []

        if polygon_delimiters:
            polygon_mask = QgsGeometry.unaryUnion(polygon_delimiters)
            if polygon_mask and not polygon_mask.isEmpty() and not polygon_mask.isGeosValid():
                polygon_mask = polygon_mask.makeValid()
            if polygon_mask and not polygon_mask.isEmpty():
                frame_mask = frame_mask.difference(polygon_mask)
                if frame_mask and not frame_mask.isEmpty() and not frame_mask.isGeosValid():
                    frame_mask = frame_mask.makeValid()
            if not frame_mask or frame_mask.isEmpty():
                raise QgsProcessingException('A ?rea ?til ficou vazia ap?s remover os delimitadores poligonais.')
            if feedback:
                feedback.pushInfo(f'{len(polygon_delimiters)} geometria(s) poligonais delimitadoras aplicadas.')

        line_delimiters = cls.collect_geometries(
            line_layers,
            frame_mask,
            work_crs,
            only_selected_delimiters,
            feedback,
            polygon_mode=False,
        ) if line_layers else []

        if line_delimiters:
            linework = [frame_mask.boundary()]
            linework.extend(line_delimiters)
            noded = QgsGeometry.unaryUnion(linework)
            if noded.isEmpty():
                polygon_candidates = cls.extract_polygon_parts(frame_mask)
            else:
                polygonized = QgsGeometry.polygonize([noded])
                polygon_candidates = cls.extract_polygon_parts(polygonized)
                if not polygon_candidates:
                    polygon_candidates = cls.extract_polygon_parts(frame_mask)
            if feedback:
                feedback.pushInfo(f'Polygoniza??o gerou {len(polygon_candidates)} candidato(s).')
        else:
            polygon_candidates = cls.extract_polygon_parts(frame_mask)
            if feedback:
                feedback.pushWarning('Nenhum delimitador linear foi informado ap?s a coleta. A moldura ?til foi usada diretamente.')

        final_geometries = []
        work_engine = QgsGeometry.createGeometryEngine(frame_mask.constGet())
        if work_engine is None:
            raise QgsProcessingException('Falha ao criar o motor geom?trico da ?rea ?til final.')
        work_engine.prepareGeometry()

        for geom in polygon_candidates:
            if feedback and feedback.isCanceled():
                return work_crs, []
            for part in cls.extract_polygon_parts(geom):
                if part.isEmpty():
                    continue
                if not work_engine.intersects(part.constGet()):
                    continue
                clipped = part.intersection(frame_mask)
                if clipped.isEmpty():
                    continue
                for clipped_part in cls.extract_polygon_parts(clipped):
                    if clipped_part and not clipped_part.isEmpty():
                        final_geometries.append(clipped_part)

        return work_crs, final_geometries

    @classmethod
    def make_output_features(cls, geometries: List[QgsGeometry], work_crs: QgsCoordinateReferenceSystem):
        fields = QgsFields()
        fields.append(QgsField('id', QVariant.String))
        fields.append(QgsField('description', QVariant.String))
        fields.append(QgsField('area_otf', QVariant.Double))
        metric_crs = QgsCoordinateReferenceSystem('EPSG:31985')
        transform_context = QgsProject.instance().transformContext()
        xform = QgsCoordinateTransform(work_crs, metric_crs, transform_context)

        output_features = []
        for geom in geometries:
            for part in cls.extract_polygon_parts(geom):
                area_m2 = 0.0
                try:
                    metric_geom = QgsGeometry(part)
                    if metric_geom.transform(xform) == 0 and not metric_geom.isEmpty():
                        area_m2 = metric_geom.area()
                except Exception:
                    area_m2 = 0.0

                feature = QgsFeature(fields)
                feature.setGeometry(part)
                feature.setAttributes([str(uuid.uuid4()), None, area_m2])
                output_features.append(feature)
        return fields, output_features
