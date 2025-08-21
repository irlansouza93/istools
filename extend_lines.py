from qgis.core import (
    QgsPointXY,
    QgsGeometry,
    QgsFeatureRequest,
    QgsWkbTypes,
    QgsSpatialIndex
)
import math

class ExtendLines:
    def __init__(self, iface):
        self.iface = iface

    def run(self):
        EXTENSION_DISTANCE = 0.005
        CONNECT_TOLERANCE = 1e-9
        INDEX_BUFFER = 0.0001

        layer = self.iface.activeLayer()
        if not layer or layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.iface.messageBar().pushWarning("Erro", "Selecione uma camada de linhas ativa.")
            return
        if layer.selectedFeatureCount() == 0:
            self.iface.messageBar().pushWarning("Erro", "Selecione ao menos uma feição de linha.")
            return

        if not layer.isEditable():
            layer.startEditing()

        index = QgsSpatialIndex(layer.getFeatures())

        def is_connected(pt_xy, fid):
            bbox = QgsGeometry.fromPointXY(pt_xy).buffer(CONNECT_TOLERANCE, 1).boundingBox()
            req = QgsFeatureRequest().setFilterRect(bbox)
            for f in layer.getFeatures(req):
                if f.id() == fid:
                    continue
                if f.geometry().distance(QgsGeometry.fromPointXY(pt_xy)) <= CONNECT_TOLERANCE:
                    return True
            return False

        def find_nearest_intersection(feat, p_end, p_prev):
            dx = p_end.x() - p_prev.x()
            dy = p_end.y() - p_prev.y()
            seglen = math.hypot(dx, dy)
            if seglen == 0:
                return None, None
            ux, uy = dx / seglen, dy / seglen

            p_ext = QgsPointXY(
                p_end.x() + ux * EXTENSION_DISTANCE,
                p_end.y() + uy * EXTENSION_DISTANCE
            )
            ext_line = QgsGeometry.fromPolylineXY([p_end, p_ext])

            rect = ext_line.boundingBox().buffered(INDEX_BUFFER)
            candidates = index.intersects(rect)

            nearest_feat = None
            nearest_pt = None
            min_dist = EXTENSION_DISTANCE

            for fid in candidates:
                if fid == feat.id():
                    continue
                f = layer.getFeature(fid)
                inter = ext_line.intersection(f.geometry())
                if inter.isEmpty():
                    continue
                for v in inter.vertices():
                    pt = QgsPointXY(v)
                    d = p_end.distance(pt)
                    if CONNECT_TOLERANCE < d < min_dist:
                        min_dist = d
                        nearest_pt = pt
                        nearest_feat = f

            return nearest_feat, nearest_pt

        for feat in layer.selectedFeatures():
            verts = [QgsPointXY(v) for v in feat.geometry().vertices()]

            for idx in (0, -1):
                p_end = verts[idx]
                if is_connected(p_end, feat.id()):
                    continue

                neighbor_idx = 1 if idx == 0 else len(verts) - 2
                p_prev = verts[neighbor_idx]

                target_feat, inter_pt = find_nearest_intersection(feat, p_end, p_prev)
                if not target_feat or not inter_pt:
                    continue

                new_verts = verts.copy()
                new_verts[idx] = inter_pt
                feat.setGeometry(QgsGeometry.fromPolylineXY(new_verts))
                layer.updateFeature(feat)

                tgt_geom = target_feat.geometry()
                exists = any(QgsPointXY(v).distance(inter_pt) <= CONNECT_TOLERANCE for v in tgt_geom.vertices())
                if exists:
                    continue

                seg_info = tgt_geom.closestSegmentWithContext(inter_pt)
                dist_seg = seg_info[0]
                after_idx = seg_info[2]

                if dist_seg > CONNECT_TOLERANCE:
                    continue

                tgt_geom.insertVertex(inter_pt.x(), inter_pt.y(), after_idx)
                target_feat.setGeometry(tgt_geom)
                layer.updateFeature(target_feat)

        self.iface.messageBar().pushInfo(
            "Processamento concluído",
            "Pontas soltas conectadas sem gerar vértices duplicados. Salve a camada para confirmar."
        )

    def unload(self):
        pass