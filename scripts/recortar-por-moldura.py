# -*- coding: utf-8 -*-
"""
Recorte por moldura em buffer de edição
Compatível com QGIS 3.40.x / 3.40.13 (PyQGIS)

NOVO:
- Permite selecionar várias camadas alvo ao mesmo tempo
- Pode processar apenas feições selecionadas nas camadas alvo
- Faz limpeza de geometrias degeneradas em polígonos (área nula/zero)
- Mantém tudo apenas no buffer de edição (não grava no banco)

O que faz:
- Solicita a camada de moldura (poligonal)
- Permite marcar múltiplas camadas alvo do projeto
- Remove feições totalmente fora da moldura
- Recorta feições que cruzam a moldura
- Normaliza o resultado geométrico para evitar erro de GeometryCollection
- Em polígonos, remove sobras degeneradas com área zero

Importante:
- As alterações ficam apenas no buffer de edição para auditoria do usuário.
- O usuário decide depois se salva ou desfaz.
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QProgressDialog, QCheckBox, QListWidget,
    QListWidgetItem, QTextEdit
)
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    Qgis,
    QgsProject,
    QgsMapLayer,
    QgsWkbTypes,
    QgsFeature,
    QgsGeometry,
    QgsCoordinateTransform
)
from qgis.gui import QgsMapLayerComboBox


class ClipToFrameDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filtrar/Recortar feições pela moldura")
        self.setMinimumWidth(720)
        self.setMinimumHeight(680)

        layout = QVBoxLayout(self)

        lbl_info = QLabel(
            "Selecione a camada de moldura (poligonal) e marque uma ou mais camadas alvo.\n"
            "As alterações ficarão somente em edição para auditoria."
        )
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Camada moldura:"))
        self.cmb_mask = QgsMapLayerComboBox()
        self.cmb_mask.setFilters(Qgis.LayerFilter.VectorLayer)
        row1.addWidget(self.cmb_mask)
        layout.addLayout(row1)

        layout.addWidget(QLabel("Camadas alvo:"))
        self.lst_targets = QListWidget()
        self.lst_targets.setSelectionMode(QListWidget.NoSelection)
        layout.addWidget(self.lst_targets)

        row_buttons = QHBoxLayout()
        self.btn_select_all = QPushButton("Marcar todas")
        self.btn_unselect_all = QPushButton("Desmarcar todas")
        self.btn_refresh = QPushButton("Atualizar lista")
        row_buttons.addWidget(self.btn_select_all)
        row_buttons.addWidget(self.btn_unselect_all)
        row_buttons.addWidget(self.btn_refresh)
        layout.addLayout(row_buttons)

        self.chk_use_selected_mask = QCheckBox(
            "Usar apenas feições selecionadas da moldura (quando houver)"
        )
        self.chk_use_selected_mask.setChecked(True)
        layout.addWidget(self.chk_use_selected_mask)

        self.chk_only_selected_targets = QCheckBox(
            "Processar apenas feições selecionadas nas camadas alvo (quando houver)"
        )
        self.chk_only_selected_targets.setChecked(False)
        layout.addWidget(self.chk_only_selected_targets)

        self.chk_make_valid = QCheckBox(
            "Corrigir geometrias inválidas automaticamente quando necessário"
        )
        self.chk_make_valid.setChecked(True)
        layout.addWidget(self.chk_make_valid)

        self.chk_select_problematic = QCheckBox(
            "Selecionar feições problemáticas na camada alvo ao final"
        )
        self.chk_select_problematic.setChecked(True)
        layout.addWidget(self.chk_select_problematic)

        self.chk_skip_mask_layer = QCheckBox(
            "Ignorar automaticamente a própria camada de moldura nas camadas alvo"
        )
        self.chk_skip_mask_layer.setChecked(True)
        layout.addWidget(self.chk_skip_mask_layer)

        layout.addWidget(QLabel("Resumo da execução:"))
        self.txt_summary = QTextEdit()
        self.txt_summary.setReadOnly(True)
        self.txt_summary.setMinimumHeight(150)
        layout.addWidget(self.txt_summary)

        btns = QHBoxLayout()
        self.btn_run = QPushButton("Executar")
        self.btn_cancel = QPushButton("Cancelar")
        btns.addWidget(self.btn_run)
        btns.addWidget(self.btn_cancel)
        layout.addLayout(btns)

        self.btn_run.clicked.connect(self.run)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_select_all.clicked.connect(self.select_all_targets)
        self.btn_unselect_all.clicked.connect(self.unselect_all_targets)
        self.btn_refresh.clicked.connect(self.populate_target_layers)
        self.cmb_mask.layerChanged.connect(self.populate_target_layers)
        self.chk_skip_mask_layer.stateChanged.connect(self.populate_target_layers)

        self.populate_target_layers()

    def _is_vector(self, layer):
        return layer and layer.type() == QgsMapLayer.VectorLayer

    def _is_polygon_layer(self, layer):
        if not self._is_vector(layer):
            return False
        return QgsWkbTypes.geometryType(layer.wkbType()) == Qgis.GeometryType.Polygon

    def _is_spatial_layer(self, layer):
        if not self._is_vector(layer):
            return False
        return QgsWkbTypes.geometryType(layer.wkbType()) != Qgis.GeometryType.Unknown

    def populate_target_layers(self):
        self.lst_targets.clear()
        mask_layer = self.cmb_mask.currentLayer()
        skip_mask = self.chk_skip_mask_layer.isChecked()

        for layer in QgsProject.instance().mapLayers().values():
            if not self._is_spatial_layer(layer):
                continue

            if skip_mask and mask_layer and layer.id() == mask_layer.id():
                continue

            item = QListWidgetItem(layer.name())
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, layer.id())
            geom_type = QgsWkbTypes.displayString(layer.wkbType())
            item.setToolTip(f"{layer.name()} ({geom_type})")
            self.lst_targets.addItem(item)

    def select_all_targets(self):
        for i in range(self.lst_targets.count()):
            self.lst_targets.item(i).setCheckState(Qt.Checked)

    def unselect_all_targets(self):
        for i in range(self.lst_targets.count()):
            self.lst_targets.item(i).setCheckState(Qt.Unchecked)

    def _get_selected_target_layers(self):
        layers = []
        project = QgsProject.instance()
        for i in range(self.lst_targets.count()):
            item = self.lst_targets.item(i)
            if item.checkState() == Qt.Checked:
                layer_id = item.data(Qt.UserRole)
                layer = project.mapLayer(layer_id)
                if layer and self._is_spatial_layer(layer):
                    layers.append(layer)
        return layers

    def _append_summary(self, text):
        current = self.txt_summary.toPlainText().strip()
        if current:
            self.txt_summary.append(text)
        else:
            self.txt_summary.setPlainText(text)

    def _safe_make_valid(self, geom):
        if not geom or geom.isNull() or geom.isEmpty():
            return geom
        try:
            if not geom.isGeosValid():
                return geom.makeValid()
        except Exception:
            pass
        return geom

    def _extract_collection_to_subclass(self, geom, target_layer):
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

    def _force_multi_if_needed(self, geom, target_layer):
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

    def _geometry_family_to_wkb_candidates(self, target_wkb):
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

    def _is_zero_polygon_geometry(self, geom):
        """
        Retorna True para geometrias poligonais nulas, vazias ou com área zero.
        """
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

    def _clean_polygon_geometry(self, geom, target_layer):
        """
        Limpa geometrias poligonais degeneradas:
        - vazias
        - nulas
        - GeometryCollection
        - área zero
        """
        if not geom or geom.isNull() or geom.isEmpty():
            return None

        g = QgsGeometry(geom)
        g = self._safe_make_valid(g)
        g = self._extract_collection_to_subclass(g, target_layer)
        g = self._safe_make_valid(g)
        g = self._force_multi_if_needed(g, target_layer)

        if not g or g.isNull() or g.isEmpty():
            return None

        if QgsWkbTypes.geometryType(g.wkbType()) != Qgis.GeometryType.Polygon:
            return g

        if self._is_zero_polygon_geometry(g):
            return None

        return g

    def _coerce_result_to_target_type(self, geom, target_layer):
        if not geom or geom.isNull() or geom.isEmpty():
            return []

        g = QgsGeometry(geom)
        g = self._safe_make_valid(g)
        g = self._extract_collection_to_subclass(g, target_layer)
        g = self._safe_make_valid(g)

        if g.isNull() or g.isEmpty():
            return []

        target_wkb = target_layer.wkbType()
        target_geom_type = QgsWkbTypes.geometryType(target_wkb)
        target_is_multi = QgsWkbTypes.isMultiType(target_wkb)

        for candidate_wkb in self._geometry_family_to_wkb_candidates(target_wkb):
            try:
                coerced_list = g.coerceToType(candidate_wkb)
            except Exception:
                coerced_list = []

            valid_parts = []
            for cg in coerced_list:
                if not cg or cg.isNull() or cg.isEmpty():
                    continue

                cg = self._safe_make_valid(cg)
                cg = self._extract_collection_to_subclass(cg, target_layer)
                cg = self._safe_make_valid(cg)
                cg = self._force_multi_if_needed(cg, target_layer)

                if cg.isNull() or cg.isEmpty():
                    continue

                flat = QgsWkbTypes.geometryType(cg.wkbType())
                if flat != target_geom_type:
                    continue

                if target_is_multi and not QgsWkbTypes.isMultiType(cg.wkbType()):
                    try:
                        cg.convertToMultiType()
                    except Exception:
                        continue

                if target_geom_type == Qgis.GeometryType.Polygon:
                    cg = self._clean_polygon_geometry(cg, target_layer)
                    if cg is None:
                        continue

                valid_parts.append(cg)

            if valid_parts:
                return valid_parts

        try:
            g2 = QgsGeometry(g)
            converted = g2.convertToType(target_geom_type, target_is_multi)
        except Exception:
            converted = None

        if converted and not converted.isNull() and not converted.isEmpty():
            converted = self._safe_make_valid(converted)
            converted = self._extract_collection_to_subclass(converted, target_layer)
            converted = self._safe_make_valid(converted)
            converted = self._force_multi_if_needed(converted, target_layer)

            if target_geom_type == Qgis.GeometryType.Polygon:
                converted = self._clean_polygon_geometry(converted, target_layer)

            if converted and not converted.isNull() and not converted.isEmpty():
                flat = QgsWkbTypes.geometryType(converted.wkbType())
                if flat == target_geom_type:
                    return [converted]

        return []

    def _build_mask_geometry(self, mask_layer, target_layer, use_selected=True, auto_make_valid=True):
        feats = list(mask_layer.selectedFeatures()) if (use_selected and mask_layer.selectedFeatureCount() > 0) else list(mask_layer.getFeatures())

        if not feats:
            raise Exception("A camada de moldura não possui feições utilizáveis.")

        transform = None
        if mask_layer.crs() != target_layer.crs():
            transform = QgsCoordinateTransform(
                mask_layer.crs(),
                target_layer.crs(),
                QgsProject.instance()
            )

        geoms = []
        for f in feats:
            g = f.geometry()
            if not g or g.isNull() or g.isEmpty():
                continue

            g = QgsGeometry(g)

            if transform is not None:
                result = g.transform(transform)
                if result != Qgis.GeometryOperationResult.Success:
                    raise Exception("Falha ao transformar a moldura para o CRS da camada alvo.")

            if auto_make_valid:
                g = self._safe_make_valid(g)

            if not g.isNull() and not g.isEmpty():
                geoms.append(g)

        if not geoms:
            raise Exception("Nenhuma geometria válida foi obtida da moldura.")

        mask_geom = QgsGeometry.unaryUnion(geoms)

        if auto_make_valid:
            mask_geom = self._safe_make_valid(mask_geom)

        if mask_geom.isNull() or mask_geom.isEmpty():
            raise Exception("A geometria final da moldura ficou vazia.")

        mask_geom = self._extract_collection_to_subclass(mask_geom, mask_layer)
        mask_geom = self._safe_make_valid(mask_geom)

        if mask_geom.isNull() or mask_geom.isEmpty():
            raise Exception("A moldura final não possui geometria poligonal utilizável.")

        return mask_geom

    def _geometry_matches_layer_type(self, geom, layer):
        if not geom or geom.isNull() or geom.isEmpty():
            return False

        layer_type = QgsWkbTypes.geometryType(layer.wkbType())
        geom_type = QgsWkbTypes.geometryType(geom.wkbType())

        if geom_type != layer_type:
            return False

        if QgsWkbTypes.isMultiType(layer.wkbType()) and not QgsWkbTypes.isMultiType(geom.wkbType()):
            return False

        flat = QgsWkbTypes.flatType(geom.wkbType())
        if flat == QgsWkbTypes.GeometryCollection:
            return False

        if layer_type == Qgis.GeometryType.Polygon:
            if self._is_zero_polygon_geometry(geom):
                return False

        return True

    def _collect_problematic_features(self, layer):
        problematic = []
        for f in layer.getFeatures():
            g = f.geometry()
            if not g or g.isNull() or g.isEmpty():
                continue
            if not self._geometry_matches_layer_type(g, layer):
                problematic.append(f.id())
        return problematic

    def _get_features_to_process(self, layer, only_selected=False):
        """
        Retorna as feições a processar:
        - se only_selected=True e houver seleção, retorna apenas as selecionadas
        - caso contrário, retorna todas
        """
        if only_selected and layer.selectedFeatureCount() > 0:
            return list(layer.selectedFeatures()), True
        return list(layer.getFeatures()), False

    def _cleanup_zero_area_features(self, layer, processed_ids=None):
        """
        Limpeza final para camadas poligonais:
        remove feições com geometria nula/vazia/área zero.
        Se processed_ids for informado, restringe a limpeza a esse conjunto.
        """
        if QgsWkbTypes.geometryType(layer.wkbType()) != Qgis.GeometryType.Polygon:
            return 0

        removed = 0
        features = layer.getFeatures()

        for f in features:
            fid = f.id()
            if processed_ids is not None and fid not in processed_ids:
                continue

            g = f.geometry()
            if not g or g.isNull() or g.isEmpty():
                if layer.deleteFeature(fid):
                    removed += 1
                continue

            g = self._clean_polygon_geometry(g, layer)
            if g is None:
                if layer.deleteFeature(fid):
                    removed += 1
                continue

            # Se a geometria mudou durante a limpeza, atualiza no buffer
            if not f.geometry().equals(g):
                try:
                    if layer.changeGeometry(fid, g, True):
                        pass
                except Exception:
                    pass

        return removed

    def _process_target_layer(self, mask_layer, target_layer, use_selected_mask, auto_make_valid,
                              select_problematic, only_selected_targets):
        mask_geom = self._build_mask_geometry(
            mask_layer,
            target_layer,
            use_selected=use_selected_mask,
            auto_make_valid=auto_make_valid
        )

        mask_bbox = mask_geom.boundingBox()

        engine = QgsGeometry.createGeometryEngine(mask_geom.constGet())
        if engine is None:
            raise Exception("Não foi possível criar o engine geométrico da moldura.")
        engine.prepareGeometry()

        was_editable = target_layer.isEditable()
        if not was_editable:
            if not target_layer.startEditing():
                raise Exception(f"Não foi possível colocar a camada '{target_layer.name()}' em modo de edição.")

        target_layer.beginEditCommand(f"Recortar feições pela moldura - {target_layer.name()}")

        features_to_process, used_selection = self._get_features_to_process(
            target_layer,
            only_selected=only_selected_targets
        )

        total = len(features_to_process)
        processed_ids = set()

        progress = QProgressDialog(
            f"Processando camada: {target_layer.name()}",
            "Cancelar",
            0,
            total if total > 0 else 1,
            self
        )
        progress.setWindowTitle("Executando")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        removed_count = 0
        changed_count = 0
        split_count = 0
        unchanged_inside_count = 0
        cleaned_zero_area_count = 0

        try:
            for i, feat in enumerate(features_to_process):
                progress.setValue(i)
                progress.setLabelText(
                    f"Camada: {target_layer.name()} | Feição {i + 1} de {total}"
                )

                if progress.wasCanceled():
                    raise Exception("Operação cancelada pelo usuário.")

                fid = feat.id()
                processed_ids.add(fid)
                geom = feat.geometry()

                if not geom or geom.isNull() or geom.isEmpty():
                    if target_layer.deleteFeature(fid):
                        removed_count += 1
                    continue

                if not geom.boundingBoxIntersects(mask_bbox):
                    if target_layer.deleteFeature(fid):
                        removed_count += 1
                    else:
                        raise Exception(f"Falha ao excluir a feição {fid}.")
                    continue

                try:
                    intersects = engine.intersects(geom.constGet())
                except Exception:
                    intersects = False

                if not intersects:
                    if target_layer.deleteFeature(fid):
                        removed_count += 1
                    else:
                        raise Exception(f"Falha ao excluir a feição {fid}.")
                    continue

                try:
                    if engine.contains(geom.constGet()):
                        if QgsWkbTypes.geometryType(target_layer.wkbType()) == Qgis.GeometryType.Polygon:
                            cleaned = self._clean_polygon_geometry(geom, target_layer)
                            if cleaned is None:
                                if target_layer.deleteFeature(fid):
                                    removed_count += 1
                                continue
                            if not geom.equals(cleaned):
                                if not target_layer.changeGeometry(fid, cleaned, True):
                                    raise Exception(f"Falha ao limpar geometria contida {fid}.")
                                changed_count += 1
                        unchanged_inside_count += 1
                        continue
                except Exception:
                    pass

                clipped = geom.intersection(mask_geom)

                if clipped.isNull() or clipped.isEmpty():
                    if not target_layer.deleteFeature(fid):
                        raise Exception(f"Falha ao excluir a feição {fid}.")
                    removed_count += 1
                    continue

                if auto_make_valid:
                    clipped = self._safe_make_valid(clipped)

                result_geoms = self._coerce_result_to_target_type(clipped, target_layer)

                if not result_geoms:
                    if not target_layer.deleteFeature(fid):
                        raise Exception(f"Falha ao excluir a feição {fid}.")
                    removed_count += 1
                    continue

                if len(result_geoms) == 1:
                    new_geom = result_geoms[0]

                    if not self._geometry_matches_layer_type(new_geom, target_layer):
                        if not target_layer.deleteFeature(fid):
                            raise Exception(f"Falha ao excluir feição incompatível {fid}.")
                        removed_count += 1
                        continue

                    if not target_layer.changeGeometry(fid, new_geom, True):
                        raise Exception(f"Falha ao alterar a geometria da feição {fid}.")

                    changed_count += 1

                else:
                    attrs = feat.attributes()

                    if not target_layer.deleteFeature(fid):
                        raise Exception(f"Falha ao excluir a feição original {fid} antes do split.")

                    removed_count += 1

                    new_features = []
                    for g in result_geoms:
                        if not self._geometry_matches_layer_type(g, target_layer):
                            continue

                        nf = QgsFeature(target_layer.fields())
                        nf.setAttributes(attrs)
                        nf.setGeometry(g)
                        new_features.append(nf)

                    if not new_features:
                        continue

                    ok, added_features = target_layer.addFeatures(new_features)
                    if not ok:
                        raise Exception(f"Falha ao adicionar as novas partes da feição {fid}.")

                    for af in added_features:
                        processed_ids.add(af.id())

                    split_count += 1

            progress.setValue(total if total > 0 else 1)

            # limpeza final de polígonos degenerados
            cleaned_zero_area_count = self._cleanup_zero_area_features(
                target_layer,
                processed_ids=processed_ids if only_selected_targets and used_selection else None
            )

            problematic_after = self._collect_problematic_features(target_layer)

            target_layer.endEditCommand()
            target_layer.triggerRepaint()

            if problematic_after and select_problematic:
                target_layer.selectByIds(problematic_after)

            return {
                "layer_name": target_layer.name(),
                "removed": removed_count,
                "changed": changed_count,
                "split": split_count,
                "inside": unchanged_inside_count,
                "cleaned_zero_area": cleaned_zero_area_count,
                "problematic": len(problematic_after),
                "used_selection": used_selection,
                "processed_total": total,
                "success": True,
                "message": None
            }

        except Exception as e:
            try:
                target_layer.destroyEditCommand()
            except Exception:
                pass
            raise e

        finally:
            try:
                progress.close()
            except Exception:
                pass

    def run(self):
        self.txt_summary.clear()

        mask_layer = self.cmb_mask.currentLayer()
        target_layers = self._get_selected_target_layers()

        if not self._is_polygon_layer(mask_layer):
            QMessageBox.warning(
                self, "Aviso",
                "A camada de moldura precisa ser vetorial do tipo polígono."
            )
            return

        if not target_layers:
            QMessageBox.warning(
                self, "Aviso",
                "Marque pelo menos uma camada alvo."
            )
            return

        use_selected_mask = self.chk_use_selected_mask.isChecked()
        only_selected_targets = self.chk_only_selected_targets.isChecked()
        auto_make_valid = self.chk_make_valid.isChecked()
        select_problematic = self.chk_select_problematic.isChecked()

        results = []
        errors = []

        for target_layer in target_layers:
            if mask_layer.id() == target_layer.id():
                results.append({
                    "layer_name": target_layer.name(),
                    "success": False,
                    "message": "A camada de moldura e a camada alvo não podem ser a mesma."
                })
                continue

            try:
                result = self._process_target_layer(
                    mask_layer,
                    target_layer,
                    use_selected_mask,
                    auto_make_valid,
                    select_problematic,
                    only_selected_targets
                )
                results.append(result)

                sel_txt = "sim" if result["used_selection"] else "não"
                resumo = (
                    f"[OK] {result['layer_name']}\n"
                    f"  Feições processadas: {result['processed_total']}\n"
                    f"  Usou seleção da camada: {sel_txt}\n"
                    f"  Removidas: {result['removed']}\n"
                    f"  Alteradas: {result['changed']}\n"
                    f"  Divididas: {result['split']}\n"
                    f"  Já contidas: {result['inside']}\n"
                    f"  Limpas por área zero/nulas: {result['cleaned_zero_area']}\n"
                    f"  Problemáticas restantes: {result['problematic']}\n"
                )
                self._append_summary(resumo)

            except Exception as e:
                msg = str(e)
                results.append({
                    "layer_name": target_layer.name(),
                    "success": False,
                    "message": msg
                })
                errors.append(f"{target_layer.name()}: {msg}")
                self._append_summary(f"[ERRO] {target_layer.name()}\n  {msg}\n")

        ok_count = sum(1 for r in results if r.get("success"))
        fail_count = sum(1 for r in results if not r.get("success"))

        final_msg = (
            "Processamento concluído no buffer de edição.\n\n"
            f"Camadas processadas com sucesso: {ok_count}\n"
            f"Camadas com erro: {fail_count}\n\n"
            "Nada foi gravado definitivamente no banco.\n"
            "O usuário ainda pode auditar e decidir salvar ou desfazer."
        )

        if errors:
            QMessageBox.warning(self, "Concluído com atenção", final_msg)
        else:
            QMessageBox.information(self, "Concluído", final_msg)

        self.accept()


def executar_recorte_por_moldura():
    dlg = ClipToFrameDialog(iface.mainWindow())
    dlg.exec()


executar_recorte_por_moldura()
