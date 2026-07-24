# -*- coding: utf-8 -*-
"""Ferramenta de simplificação suave para feições lineares selecionadas."""

from qgis.core import QgsApplication, QgsMapLayer, QgsWkbTypes, Qgis

from .translations.translate import translate


class SmoothSimplifier:
    """Simplifica, de forma reversível, linhas selecionadas na camada ativa."""

    # Tolerância angular fina, adequada ao uso do plugin com dados em graus.
    TOLERANCE = 0.000001

    def __init__(self, iface):
        self.iface = iface

    def tr(self, *strings):
        return translate(strings, QgsApplication.locale()[:2])

    def run(self):
        """Simplifica as linhas selecionadas mantendo a operação no histórico de edição."""
        layer = self.iface.activeLayer()
        if not layer:
            self._message(
                "Error",
                "Erro",
                "No active layer. Select a line layer.",
                "Nenhuma camada ativa. Selecione uma camada de linhas.",
                Qgis.Critical,
            )
            return

        if layer.type() != QgsMapLayer.VectorLayer or layer.geometryType() != QgsWkbTypes.LineGeometry:
            self._message(
                "Warning",
                "Aviso",
                "The active layer must be a line vector layer.",
                "A camada ativa deve ser uma camada vetorial de linhas.",
                Qgis.Warning,
            )
            return

        features = layer.selectedFeatures()
        if not features:
            self._message(
                "Warning",
                "Aviso",
                "No line features selected.",
                "Nenhuma feição de linha selecionada.",
                Qgis.Warning,
            )
            return

        if not layer.isEditable() and not layer.startEditing():
            self._message(
                "Error",
                "Erro",
                "The layer could not be put into edit mode.",
                "Não foi possível iniciar a edição da camada.",
                Qgis.Critical,
            )
            return

        before, after, changed = 0, 0, 0
        layer.beginEditCommand(self.tr("Simplify selected lines", "Simplificar linhas selecionadas"))
        try:
            for feature in features:
                geometry = feature.geometry()
                if not geometry or geometry.isEmpty():
                    continue

                original_vertices = self._vertex_count(geometry)
                simplified = geometry.simplify(self.TOLERANCE)
                if simplified.isEmpty():
                    continue

                simplified_vertices = self._vertex_count(simplified)
                if not layer.changeGeometry(feature.id(), simplified):
                    raise RuntimeError("Unable to update feature geometry")

                before += original_vertices
                after += simplified_vertices
                changed += 1
        except Exception:
            layer.destroyEditCommand()
            self._message(
                "Error",
                "Erro",
                "Unable to simplify the selected lines. No changes were applied.",
                "Não foi possível simplificar as linhas selecionadas. Nenhuma alteração foi aplicada.",
                Qgis.Critical,
            )
            return

        layer.endEditCommand()
        layer.triggerRepaint()
        self.iface.mapCanvas().refreshAllLayers()

        reduction = 0 if not before else 100 * (1 - after / before)
        self._message(
            "Success",
            "Sucesso",
            "Simplified {changed} line(s): {reduction:.1f}% fewer vertices ({before} to {after}). Use Ctrl+Z to undo.",
            "Simplificadas {changed} linha(s): {reduction:.1f}% menos vértices ({before} para {after}). Use Ctrl+Z para desfazer.",
            Qgis.Success,
            changed=changed,
            reduction=reduction,
            before=before,
            after=after,
        )

    @staticmethod
    def _vertex_count(geometry):
        return sum(1 for _ in geometry.vertices())

    def _message(self, title_en, title_pt, text_en, text_pt, level, **values):
        title = self.tr(title_en, title_pt)
        text = self.tr(text_en, text_pt).format(**values)
        self.iface.messageBar().pushMessage(title, text, level=level, duration=7)

    def unload(self):
        """A ferramenta não mantém recursos persistentes."""
