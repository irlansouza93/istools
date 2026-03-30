# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Clip by Frame Logic
                                 A QGIS plugin
 Professional vectorization toolkit for QGIS
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
"""

import os
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    Qgis,
    QgsProject,
    QgsMapLayer,
    QgsWkbTypes,
    QgsFeature,
    QgsGeometry,
    QgsCoordinateTransform,
    QgsMessageLog
)

class ClipByFrameLogic:
    """
    Motor de processamento central para recorte por moldura.
    Contém toda a lógica avançada portada do script manual recortar-por-moldura.py.
    """

    @staticmethod
    def safe_make_valid(geom):
        if not geom or geom.isNull() or geom.isEmpty():
            return geom
        try:
            if not geom.isGeosValid():
                return geom.makeValid()
        except Exception:
            pass
        return geom

    @staticmethod
    def extract_collection_to_subclass(geom, target_layer):
        if not geom or geom.isNull() or geom.isEmpty():
            return geom

        flat = QgsWkbTypes.flatType(geom.wkbType())
        if flat != QgsWkbTypes.GeometryCollection:
            return geom

        target_geom_type = QgsWkbTypes.geometryType(target_layer.wkbType())
        g = QgsGeometry(geom)

        try:
            ok = g.convertGeometryCollectionToSubclass(target_geom_type)
            if ok and not g.isNull() and not g.isEmpty():
                return g
        except Exception:
            pass

        return g

    @staticmethod
    def force_multi_if_needed(geom, target_layer):
        if not geom or geom.isNull() or geom.isEmpty():
            return geom

        target_wkb = target_layer.wkbType()
        target_is_multi = QgsWkbTypes.isMultiType(target_wkb)

        if target_is_multi and not QgsWkbTypes.isMultiType(geom.wkbType()):
            try:
                geom.convertToMultiType()
            except Exception:
                pass

        return geom

    @staticmethod
    def geometry_family_to_wkb_candidates(target_wkb):
        geom_type = QgsWkbTypes.geometryType(target_wkb)
        is_multi = QgsWkbTypes.isMultiType(target_wkb)
        has_z = QgsWkbTypes.hasZ(target_wkb)
        has_m = QgsWkbTypes.hasM(target_wkb)

        candidates = [target_wkb]

        if geom_type == Qgis.GeometryType.Point:
            flat_single = QgsWkbTypes.Point
            flat_multi = QgsWkbTypes.MultiPoint
        elif geom_type == Qgis.GeometryType.Line:
            flat_single = QgsWkbTypes.LineString
            flat_multi = QgsWkbTypes.MultiLineString
        elif geom_type == Qgis.GeometryType.Polygon:
            flat_single = QgsWkbTypes.Polygon
            flat_multi = QgsWkbTypes.MultiPolygon
        else:
            return candidates

        preferred_flat = flat_multi if is_multi else flat_single
        other_flat = flat_single if is_multi else flat_multi

        preferred = QgsWkbTypes.addM(
            QgsWkbTypes.addZ(preferred_flat) if has_z else preferred_flat
        ) if has_m else (QgsWkbTypes.addZ(preferred_flat) if has_z else preferred_flat)

        other = QgsWkbTypes.addM(
            QgsWkbTypes.addZ(other_flat) if has_z else other_flat
        ) if has_m else (QgsWkbTypes.addZ(other_flat) if has_z else other_flat)

        for c in [preferred, other, preferred_flat, other_flat]:
            if c not in candidates:
                candidates.append(c)

        return candidates

    @staticmethod
    def is_zero_polygon_geometry(geom):
        if not geom or geom.isNull() or geom.isEmpty():
            return True

        try:
            if QgsWkbTypes.geometryType(geom.wkbType()) != Qgis.GeometryType.Polygon:
                return False
        except Exception:
            return False

        try:
            area = geom.area()
            if area is None:
                return True
            if abs(area) <= 0.0:
                return True
        except Exception:
            return True

        return False

    @staticmethod
    def clean_polygon_geometry(geom, target_layer, auto_make_valid=True):
        if not geom or geom.isNull() or geom.isEmpty():
            return None

        g = QgsGeometry(geom)
        if auto_make_valid:
            g = ClipByFrameLogic.safe_make_valid(g)
        g = ClipByFrameLogic.extract_collection_to_subclass(g, target_layer)
        if auto_make_valid:
            g = ClipByFrameLogic.safe_make_valid(g)
        g = ClipByFrameLogic.force_multi_if_needed(g, target_layer)

        if not g or g.isNull() or g.isEmpty():
            return None

        if QgsWkbTypes.geometryType(g.wkbType()) != Qgis.GeometryType.Polygon:
            return g

        if ClipByFrameLogic.is_zero_polygon_geometry(g):
            return None

        return g

    @staticmethod
    def coerce_result_to_target_type(geom, target_layer, auto_make_valid=True):
        if not geom or geom.isNull() or geom.isEmpty():
            return []

        g = QgsGeometry(geom)
        if auto_make_valid:
            g = ClipByFrameLogic.safe_make_valid(g)
        g = ClipByFrameLogic.extract_collection_to_subclass(g, target_layer)
        if auto_make_valid:
            g = ClipByFrameLogic.safe_make_valid(g)

        if g.isNull() or g.isEmpty():
            return []

        target_wkb = target_layer.wkbType()
        # target_geom_type = QgsWkbTypes.geometryType(target_wkb) # Removido para simplificar se necessário, mas mantido na lógica de comparação
        target_is_multi = QgsWkbTypes.isMultiType(target_wkb)

        for candidate_wkb in ClipByFrameLogic.geometry_family_to_wkb_candidates(target_wkb):
            try:
                coerced_list = g.coerceToType(candidate_wkb)
            except Exception:
                coerced_list = []

            valid_parts = []
            for cg in coerced_list:
                if not cg or cg.isNull() or cg.isEmpty():
                    continue

                if auto_make_valid:
                    cg = ClipByFrameLogic.safe_make_valid(cg)
                cg = ClipByFrameLogic.extract_collection_to_subclass(cg, target_layer)
                if auto_make_valid:
                    cg = ClipByFrameLogic.safe_make_valid(cg)
                cg = ClipByFrameLogic.force_multi_if_needed(cg, target_layer)

                if cg.isNull() or cg.isEmpty():
                    continue

                if not ClipByFrameLogic.geometry_matches_layer_type(cg, target_layer):
                    continue

                valid_parts.append(cg)

            if valid_parts:
                return valid_parts

        return []

    @staticmethod
    def build_mask_geometry(mask_layer, target_layer, use_selected=True, auto_make_valid=True):
        feats = list(mask_layer.selectedFeatures()) if (use_selected and mask_layer.selectedFeatureCount() > 0) else list(mask_layer.getFeatures())

        if not feats:
            raise Exception("A camada de moldura não possui feições utilizáveis.")

        transform = None
        if mask_layer.crs() != target_layer.crs():
            transform = QgsCoordinateTransform(mask_layer.crs(), target_layer.crs(), QgsProject.instance())

        geoms = []
        for f in feats:
            g = f.geometry()
            if not g or g.isNull() or g.isEmpty():
                continue

            g = QgsGeometry(g)

            if transform is not None:
                g.transform(transform)

            if auto_make_valid:
                g = ClipByFrameLogic.safe_make_valid(g)

            if not g.isNull() and not g.isEmpty():
                geoms.append(g)

        if not geoms:
            raise Exception("Nenhuma geometria válida foi obtida da moldura.")

        mask_geom = QgsGeometry.unaryUnion(geoms)

        if auto_make_valid:
            mask_geom = ClipByFrameLogic.safe_make_valid(mask_geom)

        if mask_geom.isNull() or mask_geom.isEmpty():
            raise Exception("A geometria final da moldura ficou vazia.")

        return mask_geom

    @staticmethod
    def geometry_matches_layer_type(geom, layer):
        if not geom or geom.isNull() or geom.isEmpty():
            return False

        layer_type = QgsWkbTypes.geometryType(layer.wkbType())
        geom_type = QgsWkbTypes.geometryType(geom.wkbType())

        if geom_type != layer_type:
            return False

        if QgsWkbTypes.isMultiType(layer.wkbType()) and not QgsWkbTypes.isMultiType(geom.wkbType()):
            return False

        if layer_type == Qgis.GeometryType.Polygon:
            if ClipByFrameLogic.is_zero_polygon_geometry(geom):
                return False

        return True

    @staticmethod
    def cleanup_zero_area_features(layer, processed_ids=None):
        if QgsWkbTypes.geometryType(layer.wkbType()) != Qgis.GeometryType.Polygon:
            return 0

        removed = 0
        features = layer.getFeatures()

        for f in features:
            fid = f.id()
            if processed_ids is not None and fid not in processed_ids:
                continue

            g = f.geometry()
            if not g or g.isNull() or g.isEmpty() or ClipByFrameLogic.is_zero_polygon_geometry(g):
                if layer.deleteFeature(fid):
                    removed += 1
                continue

        return removed

    @staticmethod
    def collect_problematic_features(layer):
        problematic = []
        for f in layer.getFeatures():
            if not ClipByFrameLogic.geometry_matches_layer_type(f.geometry(), layer):
                problematic.append(f.id())
        return problematic

    @staticmethod
    def process_target_layer(mask_layer, target_layer, use_selected_mask=True, auto_make_valid=True,
                               only_selected_targets=False, clean_zero_area=True, feedback=None):
        """
        Versão In-Place para o Plugin e Algoritmo de Processamento.
        """
        mask_geom = ClipByFrameLogic.build_mask_geometry(mask_layer, target_layer, use_selected_mask, auto_make_valid)
        mask_bbox = mask_geom.boundingBox()

        engine = QgsGeometry.createGeometryEngine(mask_geom.constGet())
        if engine is None: raise Exception("Falha no engine.")
        engine.prepareGeometry()

        if not target_layer.isEditable():
            if not target_layer.startEditing(): raise Exception("Erro ao abrir edição.")

        target_layer.beginEditCommand(f"Recortar {target_layer.name()}")

        feats_to_process, used_selection = (list(target_layer.selectedFeatures()), True) if (only_selected_targets and target_layer.selectedFeatureCount() > 0) else (list(target_layer.getFeatures()), False)
        total = len(feats_to_process)
        processed_ids = set()

        removed = 0
        changed = 0
        split = 0
        inside = 0

        for i, feat in enumerate(feats_to_process):
            if feedback and feedback.isCanceled(): break
            if feedback: feedback.setProgress(int((i / total) * 100))

            fid = feat.id()
            processed_ids.add(fid)
            geom = feat.geometry()

            if not geom or geom.isNull() or geom.isEmpty() or not geom.boundingBoxIntersects(mask_bbox) or not engine.intersects(geom.constGet()):
                if target_layer.deleteFeature(fid): removed += 1
                continue

            if engine.contains(geom.constGet()):
                inside += 1
                continue

            clipped = geom.intersection(mask_geom)
            if clipped.isNull() or clipped.isEmpty():
                if target_layer.deleteFeature(fid): removed += 1
                continue

            parts = ClipByFrameLogic.coerce_result_to_target_type(clipped, target_layer, auto_make_valid)

            if not parts:
                if target_layer.deleteFeature(fid): removed += 1
            elif len(parts) == 1:
                target_layer.changeGeometry(fid, parts[0])
                changed += 1
            else:
                target_layer.deleteFeature(fid)
                removed += 1
                new_feats = []
                for p in parts:
                    nf = QgsFeature(target_layer.fields())
                    nf.setAttributes(feat.attributes())
                    nf.setGeometry(p)
                    new_feats.append(nf)
                target_layer.addFeatures(new_feats)
                split += 1

        cleaned = 0
        if clean_zero_area:
            cleaned = ClipByFrameLogic.cleanup_zero_area_features(target_layer, processed_ids if used_selection else None)
            
        target_layer.endEditCommand()
        target_layer.triggerRepaint()
        
        return {
            "success": True,
            "removed": removed,
            "changed": changed,
            "split": split,
            "inside": inside,
            "cleaned": cleaned
        }
