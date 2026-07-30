# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Intersection Line
                                 A QGIS plugin
 Professional vectorization toolkit for QGIS
                              -------------------
        begin                : 2025-01-15
        git sha              : $Format:%H$
        copyright            : (C) 2025 by Irlan Souza
        email                : irlan.souza@eb.mil.br
 ***************************************************************************/

 This program is free software; you can redistribute it and/or modify it
 under the terms of the GNU General Public License as published by
 the Free Software Foundation; either version 2 of the License, or
 (at your option) any later version.
"""
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (
    QgsProject, QgsFeatureRequest, QgsGeometry, QgsRectangle, QgsPointXY,
    QgsWkbTypes, QgsSpatialIndex, QgsCoordinateTransform, QgsCsException,
    QgsMessageLog, Qgis, QgsApplication
)
from qgis.gui import QgsMapTool, QgsRubberBand
from .translations.translate import translate


class IntersectionLineTool:
    """
    Insert shared vertices at every line-line intersection inside a user-defined rectangle.

    - Works across multiple visible line layers (only layers visible in the Layer Panel).
    - Always creates 2 vertices per intersection (one on each line), unless they already exist.
    - Keeps layers in edit mode (no commit), so the user can review/undo (Ctrl+Z) or save/discard later.
    - Finalizes selection on mouse release and avoids canvas panning jumps.
    - Messages:
        * First activation: "Selecione a região de interseção"
        * If no intersections found: "Não existem vértices na região"
        * If intersections exist but all already shared: "Ja existem vertices na interceção"
        * When vertices are created: "X números de vértices criados"
    """

    TOOL_NAME = "Intersection Line"
    
    # Nome do grupo de saída (não usado nesta ferramenta, mas mantido para consistência)
    OUTPUT_GROUP_NAME = "istools-output"

    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.project = QgsProject.instance()
        self.tctx = self.project.transformContext()
        self.map_tool = None
        self._hint_shown = False

    # -------------------- i18n --------------------
    def tr(self, *string):
        return translate(string, QgsApplication.locale()[:2])

    # -------------------- lifecycle --------------------
    def activate(self):
        """Activate the tool and set up the map tool."""
        self._setup_map_tool()
        self.canvas.setMapTool(self.map_tool)
        if not self._hint_shown:
            # Requirement: show only once per activation
            QMessageBox.information(self.iface.mainWindow(), "", self.tr("Select the intersection region",
                                                                         "Selecione a região de interseção"))
            self._hint_shown = True

    def deactivate(self):
        """Deactivate and clean up."""
        self._cleanup_map_tool()

    # -------------------- map tool --------------------
    class _RectTool(QgsMapTool):
        def __init__(self, outer):
            super().__init__(outer.canvas)
            self.outer = outer
            self.canvas = outer.canvas
            self.prev_tool = None
            self.start_pt = None
            self.rb = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
            self.rb.setStrokeColor(Qt.red)
            self.rb.setFillColor(Qt.transparent)
            self.rb.setWidth(2)

        def activate(self):
            self.prev_tool = self.canvas.mapTool()
            self.canvas.setCursor(Qt.CrossCursor)
            super().activate()

        def deactivate(self):
            self._reset()
            super().deactivate()

        def canvasPressEvent(self, e):
            if e.button() == Qt.RightButton:
                # Cancel silently and return to previous tool after the event loop tick
                self._reset()
                QTimer.singleShot(0, lambda: self.canvas.setMapTool(self.prev_tool))
                e.accept()
                return
            if e.button() == Qt.LeftButton:
                self.start_pt = self.toMapCoordinates(e.pos())
                e.accept()

        def canvasMoveEvent(self, e):
            if self.start_pt is not None:
                end_pt = self.toMapCoordinates(e.pos())
                rect = QgsRectangle(self.start_pt, end_pt)
                self.rb.setToGeometry(QgsGeometry.fromRect(rect), None)

        def canvasReleaseEvent(self, e):
            if self.start_pt is not None and e.button() == Qt.LeftButton:
                end_pt = self.toMapCoordinates(e.pos())
                rect = QgsRectangle(self.start_pt, end_pt)
                try:
                    self.outer._process_rect(rect)
                except Exception as ex:
                    # show unexpected error (do not spam logs)
                    self.outer.iface.messageBar().pushMessage("", str(ex), level=Qgis.Critical)
                self._reset()
                QTimer.singleShot(0, lambda: self.canvas.setMapTool(self.prev_tool))
                e.accept()

        def _reset(self):
            self.start_pt = None
            self.rb.reset(QgsWkbTypes.PolygonGeometry)

    def _setup_map_tool(self):
        if self.map_tool is None:
            self.map_tool = self._RectTool(self)

    def _cleanup_map_tool(self):
        if self.map_tool:
            if self.canvas.mapTool() is self.map_tool:
                self.canvas.unsetMapTool(self.map_tool)
            self.map_tool = None
        self._hint_shown = False

    # -------------------- geometry helpers --------------------
    def _map_tol(self, px=2):
        """~px pixels in map units (project CRS)."""
        return self.canvas.mapUnitsPerPixel() * px

    def _collect_points_from_intersection(self, inter_geom: QgsGeometry):
        """Return QgsPointXY list (handles Point/MultiPoint/Line overlap via boundary/Collections)."""
        pts = []
        if not inter_geom or inter_geom.isEmpty():
            return pts

        flat = QgsWkbTypes.flatType(inter_geom.wkbType())
        gtype = QgsWkbTypes.geometryType(flat)

        if flat == QgsWkbTypes.Point:
            pts.append(inter_geom.asPoint()); return pts
        if flat == QgsWkbTypes.MultiPoint:
            pts.extend(inter_geom.asMultiPoint()); return pts

        if flat in (QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString):
            b = inter_geom.boundary()
            if not b or b.isEmpty():  # nothing to add
                return pts
            bf = QgsWkbTypes.flatType(b.wkbType())
            if bf == QgsWkbTypes.Point:
                pts.append(b.asPoint())
            elif bf == QgsWkbTypes.MultiPoint:
                pts.extend(b.asMultiPoint())
            return pts

        if gtype == QgsWkbTypes.GeometryCollectionGeometry:
            try:
                for p in inter_geom.asGeometryCollection():
                    pts.extend(self._collect_points_from_intersection(p))
            except Exception as error:
                QgsMessageLog.logMessage(
                    f"Falha ao decompor uma coleção de geometrias de "
                    f"interseção: {error}",
                    "ISTools",
                    Qgis.Warning,
                )
            return pts

        return pts

    def _vertex_exists(self, geom: QgsGeometry, pt: QgsPointXY, tol_layer: float):
        """Check if a vertex exists within tol_layer (layer CRS units)."""
        if not geom or geom.isEmpty():
            return False
        lines = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
        px, py = pt.x(), pt.y()
        t2 = tol_layer * tol_layer
        for line in lines:
            for v in line:
                dx = v.x() - px
                dy = v.y() - py
                if (dx*dx + dy*dy) < t2:
                    return True
        return False

    def _insert_vertex_precisely(self, geom: QgsGeometry, pt: QgsPointXY, tol_layer: float):
        """
        Insert pt at closest segment if no existing vertex there.
        Returns new geometry or None if unchanged.
        """
        if not geom or geom.isEmpty():
            return None
        if self._vertex_exists(geom, pt, tol_layer):
            return None

        parts = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
        best = (float('inf'), None, None)  # (dist, part_idx, insert_idx)

        for p_idx, line in enumerate(parts):
            for i in range(len(line) - 1):
                seg = QgsGeometry.fromPolylineXY([line[i], line[i+1]])
                d = seg.distance(QgsGeometry.fromPointXY(pt))
                if d < best[0]:
                    best = (d, p_idx, i + 1)

        if best[1] is None:
            return None

        p_idx, insert_idx = best[1], best[2]
        parts[p_idx].insert(insert_idx, QgsPointXY(pt))
        return (QgsGeometry.fromMultiPolylineXY(parts)
                if geom.isMultipart()
                else QgsGeometry.fromPolylineXY(parts[0]))

    def _layer_transforms(self, layer):
        """Return (to_proj, from_proj) transforms for layer <-> project CRS."""
        lcrs = layer.crs()
        project_crs = self.canvas.mapSettings().destinationCrs()
        if not lcrs.isValid() or not project_crs.isValid():
            QgsMessageLog.logMessage(
                f"A camada '{layer.name()}' foi ignorada porque seu CRS ou o CRS "
                "do projeto é inválido.",
                "ISTools",
                Qgis.Warning,
            )
            return None, None

        to_proj = QgsCoordinateTransform(lcrs, project_crs, self.tctx)
        from_proj = QgsCoordinateTransform(project_crs, lcrs, self.tctx)
        if not to_proj.isValid() or not from_proj.isValid():
            QgsMessageLog.logMessage(
                f"A camada '{layer.name()}' foi ignorada porque a transformação "
                "de coordenadas não pôde ser construída.",
                "ISTools",
                Qgis.Warning,
            )
            return None, None
        return to_proj, from_proj

    @staticmethod
    def _transform_point_safely(coordinate_transform, point, layer_name):
        """Transforma um ponto ou retorna ``None`` quando a reprojeção falhar."""
        if coordinate_transform is None or not coordinate_transform.isValid():
            QgsMessageLog.logMessage(
                f"Transformação de coordenadas inválida para a camada "
                f"'{layer_name}'.",
                "ISTools",
                Qgis.Warning,
            )
            return None
        try:
            return coordinate_transform.transform(point)
        except QgsCsException as error:
            QgsMessageLog.logMessage(
                f"Falha ao reprojetar um ponto de interseção para a camada "
                f"'{layer_name}': {error}",
                "ISTools",
                Qgis.Warning,
            )
            return None

    def _tol_in_layer_units(self, from_proj: QgsCoordinateTransform, tol_proj: float, ref_pt_proj: QgsPointXY):
        """Convert project tolerance into layer CRS units near ref point."""
        try:
            p1 = from_proj.transform(ref_pt_proj)
            p2 = from_proj.transform(QgsPointXY(ref_pt_proj.x() + tol_proj, ref_pt_proj.y()))
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            d = (dx*dx + dy*dy) ** 0.5
            return d if d > 0 else tol_proj
        except QgsCsException as error:
            QgsMessageLog.logMessage(
                f"Não foi possível converter a tolerância para as unidades da "
                f"camada: {error}",
                "ISTools",
                Qgis.Warning,
            )
            return tol_proj

    def _layer_is_visible(self, layer):
        """True if layer is visible in layer tree."""
        node = self.project.layerTreeRoot().findLayer(layer.id())
        return bool(node and node.isVisible())

    def _ensure_edit_command(self, info):
        """Start editing a layer only when it is about to receive a vertex."""
        layer = info['layer']
        if not layer.isEditable() and not layer.startEditing():
            return False

        if not info['command_started']:
            layer.beginEditCommand(self.tr(
                "Insert vertices at intersections (rectangle)",
                "Inserir vértices em interseções (retângulo)"
            ))
            info['command_started'] = True
        return True

    # -------------------- core processing --------------------
    def _process_rect(self, rect_proj: QgsRectangle):
        """
        Process all intersections within the rectangle (project CRS),
        across visible line layers. Only layers that receive a vertex enter edit mode.
        Emits the required single-line messages only.
        """
        tol_proj = self._map_tol(px=2)

        # 1) Collect visible line layers + spatial indexes + transforms. Editing is
        # deferred until a vertex is actually going to be inserted in that layer.
        line_layers = []
        for lyr in self.project.mapLayers().values():
            if (getattr(lyr, 'geometryType', None)
                and lyr.geometryType() == QgsWkbTypes.LineGeometry
                and lyr.isValid()
                and self._layer_is_visible(lyr)):
                index = QgsSpatialIndex(lyr.getFeatures())
                to_proj, from_proj = self._layer_transforms(lyr)
                if to_proj is None or from_proj is None:
                    continue
                line_layers.append({
                    'layer': lyr, 'index': index,
                    'to_proj': to_proj, 'from_proj': from_proj,
                    'command_started': False
                })

        if not line_layers:
            self.iface.messageBar().pushMessage("", "Não existem vértices na região", level=Qgis.Info)
            return

        # 2) Candidate features per layer (BBOX in layer CRS) + layer tolerance
        area_proj_geom = QgsGeometry.fromRect(rect_proj)
        cx = (rect_proj.xMinimum() + rect_proj.xMaximum()) * 0.5
        cy = (rect_proj.yMinimum() + rect_proj.yMaximum()) * 0.5
        ref_pt_proj = QgsPointXY(cx, cy)

        for info in line_layers:
            lyr = info['layer']
            rect_layer = info['from_proj'].transformBoundingBox(rect_proj)
            fids = info['index'].intersects(rect_layer)
            req = QgsFeatureRequest().setFilterFids(fids)
            info['feats'] = {f.id(): f for f in lyr.getFeatures(req)
                             if f.geometry() and f.geometry().isGeosValid()}
            info['tol_layer'] = self._tol_in_layer_units(info['from_proj'], tol_proj, ref_pt_proj)

        created_count = 0
        had_any_intersection = False

        # 3) Iterate pairs of layers (including same-layer) and create shared vertices
        for i, A in enumerate(line_layers):
            lyrA, featsA, toA, fromA, tolA = A['layer'], A['feats'], A['to_proj'], A['from_proj'], A['tol_layer']
            for j in range(i, len(line_layers)):
                B = line_layers[j]
                lyrB, featsB, toB, fromB, tolB = B['layer'], B['feats'], B['to_proj'], B['from_proj'], B['tol_layer']

                for fidA in list(featsA.keys()):
                    gA_layer = lyrA.getFeature(fidA).geometry()  # always fresh
                    if not gA_layer or gA_layer.isEmpty():
                        continue
                    gA_proj = QgsGeometry(gA_layer); gA_proj.transform(toA)
                    if not gA_proj.intersects(area_proj_geom):
                        continue

                    bboxA_in_B = fromB.transformBoundingBox(gA_proj.boundingBox())
                    candB_fids = B['index'].intersects(bboxA_in_B)

                    for fidB in candB_fids:
                        if lyrA is lyrB and fidB <= fidA:
                            continue
                        if fidB not in featsB:
                            continue

                        gB_layer = lyrB.getFeature(fidB).geometry()
                        if not gB_layer or gB_layer.isEmpty():
                            continue
                        gB_proj = QgsGeometry(gB_layer); gB_proj.transform(toB)

                        if not gB_proj.intersects(area_proj_geom):
                            continue
                        if not gA_proj.intersects(gB_proj):
                            continue

                        inter = gA_proj.intersection(gB_proj)
                        if not inter or inter.isEmpty():
                            continue

                        pts_proj = self._collect_points_from_intersection(inter)
                        if not pts_proj:
                            continue

                        had_any_intersection = True

                        # deduplicate in project CRS
                        seen = set()
                        for pt in pts_proj:
                            key = (round(pt.x(), 9), round(pt.y(), 9))
                            if key in seen:
                                continue
                            seen.add(key)

                            ptA = self._transform_point_safely(
                                fromA, QgsPointXY(pt), lyrA.name()
                            )
                            ptB = self._transform_point_safely(
                                fromB, QgsPointXY(pt), lyrB.name()
                            )
                            if ptA is None or ptB is None:
                                continue

                            # As duas reprojeções precisam ser válidas para manter
                            # o vértice compartilhado nas duas camadas.
                            newA = self._insert_vertex_precisely(gA_layer, ptA, tolA)
                            if newA and self._ensure_edit_command(A) and lyrA.changeGeometry(fidA, newA):
                                gA_layer = newA
                                created_count += 1

                            newB = self._insert_vertex_precisely(gB_layer, ptB, tolB)
                            if newB and self._ensure_edit_command(B) and lyrB.changeGeometry(fidB, newB):
                                gB_layer = newB
                                created_count += 1

        # 4) Close undo steps only for layers modified by this operation.
        for info in line_layers:
            if info['command_started']:
                info['layer'].endEditCommand()

        self.canvas.refreshAllLayers()

        # 5) Required single-line messages
        if created_count == 0:
            if had_any_intersection:
                # intersections existed, but were already shared (nothing new created)
                self.iface.messageBar().pushMessage("", "Ja existem vertices na interceção", level=Qgis.Info)
            else:
                self.iface.messageBar().pushMessage("", "Não existem vértices na região", level=Qgis.Info)
        else:
            self.iface.messageBar().pushMessage("", f"{created_count} números de vértices criados", level=Qgis.Success)
