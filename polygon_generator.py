import os
import uuid
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsField, QgsFeatureRequest, QgsMessageLog, Qgis,
    QgsWkbTypes, QgsPointXY, QgsPoint, QgsSymbol, QgsSingleSymbolRenderer
)
from qgis.gui import QgsMapToolEmitPoint, QgsVertexMarker
import processing

class QgisPolygonGenerator:
    CAMADA_SAIDA = "POLIGONOS_CRIADOS"

    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.tool = QgsMapToolEmitPoint(self.canvas)
        self.marker = None

    def activate_tool(self):
        valid_layers = [
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer) and
            QgsWkbTypes.geometryType(lyr.wkbType()) in [QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry]
        ]
        if not valid_layers:
            self.iface.messageBar().pushWarning('PolygonGenerator', 'Nenhuma camada de linha ou área encontrada no projeto. Adicione uma camada válida.')
            return
        self.tool.canvasClicked.connect(self.capture_and_create)
        self.canvas.setMapTool(self.tool)
        self.iface.messageBar().pushInfo('PolygonGenerator', 'Clique no mapa para definir o centro. Clique com o botão direito para cancelar.')

    def capture_and_create(self, point, button):
        if button == 2:  # Botão direito
            self._cleanup_marker()
            self.canvas.unsetMapTool(self.tool)
            self.iface.messageBar().pushInfo('PolygonGenerator', 'Operação cancelada. Clique no botão novamente para reativar.')
            return
        if self.marker:
            self.marker.hide()
            self.marker = None
        self.marker = QgsVertexMarker(self.canvas)
        self.marker.setCenter(point)
        self.marker.setColor(QColor(255, 0, 0))
        self.marker.setFillColor(QColor(255, 0, 0, 100))
        self.marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
        self.marker.setIconSize(12)
        self.marker.setPenWidth(3)
        self.process_polygon(point)

    def process_polygon(self, point):
        pt = QgsPointXY(point)
        cgeom = QgsGeometry.fromPointXY(pt)

        tmp = QgsVectorLayer(
            f"LineString?crs={self.canvas.mapSettings().destinationCrs().authid()}",
            "_tmp_lines", "memory"
        )
        dp = tmp.dataProvider()
        feats = []

        for lyr in QgsProject.instance().mapLayers().values():
            if not isinstance(lyr, QgsVectorLayer):
                continue
            geom_type = QgsWkbTypes.geometryType(lyr.wkbType())
            if geom_type not in [QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry]:
                continue
            for feat in lyr.getFeatures():
                geom = feat.geometry()
                if not geom.isGeosValid() or geom.isEmpty():
                    continue
                if geom_type == QgsWkbTypes.PolygonGeometry:
                    if geom.wkbType() in [QgsWkbTypes.Polygon, QgsWkbTypes.PolygonZ, QgsWkbTypes.PolygonM]:
                        rings = geom.asPolygon()
                        if rings:
                            points = [QgsPoint(pt.x(), pt.y()) for pt in rings[0]]
                            boundary = QgsGeometry.fromPolyline(points)
                            if not boundary.isEmpty():
                                f = QgsFeature()
                                f.setGeometry(boundary)
                                feats.append(f)
                    elif geom.wkbType() in [QgsWkbTypes.MultiPolygon, QgsWkbTypes.MultiPolygonZ, QgsWkbTypes.MultiPolygonM]:
                        polygons = geom.asMultiPolygon()
                        for poly in polygons:
                            if poly:
                                points = [QgsPoint(pt.x(), pt.y()) for pt in poly[0]]
                                boundary = QgsGeometry.fromPolyline(points)
                                if not boundary.isEmpty():
                                    f = QgsFeature()
                                    f.setGeometry(boundary)
                                    feats.append(f)
                else:
                    f = QgsFeature()
                    f.setGeometry(geom)
                    feats.append(f)

        if not feats:
            self.iface.messageBar().pushWarning('PolygonGenerator', 'Nenhuma linha ou área delimitadora válida encontrada no projeto.')
            self._cleanup_marker()
            return

        dp.addFeatures(feats)
        tmp.updateExtents()

        try:
            res = processing.run(
                'qgis:polygonize',
                {'INPUT': tmp, 'KEEP_FIELDS': False, 'OUTPUT': 'memory:'}
            )
            poly = res['OUTPUT']
        except Exception as e:
            self.iface.messageBar().pushCritical('PolygonGenerator', f'Erro ao executar polygonize: {str(e)}')
            self._cleanup_marker()
            return

        sel = None
        for f in poly.getFeatures():
            if f.geometry().contains(cgeom):
                sel = f.geometry()
                break

        if not sel:
            self.iface.messageBar().pushWarning('PolygonGenerator', 'Nenhum polígono delimitado encontrado. A área pode estar vazada.')
            self._cleanup_marker()
            return

        if not sel.isGeosValid():
            self.iface.messageBar().pushWarning('PolygonGenerator', 'Geometria inválida. A área pode estar vazada e necessita de ajustes.')
            self._cleanup_marker()
            return

        out = None
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == self.CAMADA_SAIDA and isinstance(lyr, QgsVectorLayer):
                out = lyr
                break

        if not out:
            out = QgsVectorLayer(
                f"Polygon?crs={self.canvas.mapSettings().destinationCrs().authid()}",
                self.CAMADA_SAIDA, "memory"
            )
            prov = out.dataProvider()
            prov.addAttributes([QgsField('id', QVariant.String)])
            out.updateFields()
            symbol = QgsSymbol.defaultSymbol(out.geometryType())
            symbol.setColor(QColor(255, 0, 0, 100))
            renderer = QgsSingleSymbolRenderer(symbol)
            out.setRenderer(renderer)
            QgsProject.instance().addMapLayer(out)
        else:
            prov = out.dataProvider()

        if not out.isEditable():
            out.startEditing()

        for ex in out.getFeatures():
            if ex.geometry().equals(sel):
                self.iface.messageBar().pushInfo('PolygonGenerator', 'Polígono já existe na camada.')
                self._cleanup_marker()
                return

        feat = QgsFeature(out.fields())
        feat.setGeometry(sel)
        feat_id = str(uuid.uuid4())
        attributes = [None] * out.fields().count()
        id_index = out.fields().indexFromName('id')
        if id_index == -1:
            self.iface.messageBar().pushCritical('PolygonGenerator', 'Campo "id" não encontrado na camada.')
            self._cleanup_marker()
            return
        attributes[id_index] = feat_id
        feat.setAttributes(attributes)

        if not out.addFeature(feat):
            self.iface.messageBar().pushCritical('PolygonGenerator', 'Erro ao adicionar feição à camada.')
            self._cleanup_marker()
            return

        out.updateExtents()
        out.triggerRepaint()
        self.canvas.refreshAllLayers()

        QgsMessageLog.logMessage(f'Feição adicionada com ID {feat_id}. Total de feições: {out.featureCount()}', 'PolygonGenerator', Qgis.Info)
        self.iface.messageBar().pushInfo(
            'PolygonGenerator',
            f'Polígono adicionado com ID {feat_id}. A camada está em modo de edição. Use "Desfazer" (Ctrl+Z) para reverter ou clique em "Salvar Alterações" para confirmar.'
        )

        self._cleanup_marker()

    def _cleanup_marker(self):
        if self.marker:
            self.marker.hide()
            self.marker = None

    def unload(self):
        try:
            self.tool.canvasClicked.disconnect(self.capture_and_create)
        except Exception:
            pass
        self._cleanup_marker()
        self.canvas.unsetMapTool(self.tool)