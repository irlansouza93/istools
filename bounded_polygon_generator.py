# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Bounded Polygon Generator
                                 A QGIS plugin
 Professional vectorization toolkit for QGIS
                              -------------------
        begin                : 2025-01-15
        git sha              : $Format:%H$
        copyright            : (C) 2025 by Irlan Souza, 2? Sgt Brazilian Army
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

import time
import uuid

from qgis.PyQt.QtCore import QVariant, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsGeometry,
    QgsMessageLog,
    QgsProject,
    QgsTask,
    QgsVectorLayer,
    QgsVectorLayerFeatureSource,
    QgsVectorLayerSelectedFeatureSource,
    QgsWkbTypes,
)

from .translations.translate import translate


class BoundedPolygonGenerator:
    OUTPUT_GROUP_NAME = "istools-output"

    def __init__(self, iface):
        self.iface = iface
        self.dialog = None

    def tr(self, *string):
        return translate(string, QgsApplication.locale()[:2])

    def activate_tool(self):
        self.dialog = PolygonGeneratorDialog(self.iface)
        self.dialog.show()

    def unload(self):
        if self.dialog:
            self.dialog.close()
            self.dialog = None


def extract_polygon_parts(geometry):
    if not geometry or geometry.isNull() or geometry.isEmpty():
        return []

    parts = []
    stack = [QgsGeometry(geometry)]

    while stack:
        current = stack.pop()
        if not current or current.isNull() or current.isEmpty():
            continue

        try:
            collection_parts = current.asGeometryCollection()
        except Exception:
            collection_parts = []

        if collection_parts:
            for sub_geom in collection_parts:
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


class BoundedPolygonGenerationTask(QgsTask):
    logGenerated = pyqtSignal(str, int)

    def __init__(
        self,
        description,
        frame_source,
        frame_source_crs_authid,
        polygon_sources,
        line_sources,
        project_crs_authid,
        transform_context,
        on_finished,
    ):
        super().__init__(description, QgsTask.CanCancel)
        self.frame_source = frame_source
        self.frame_source_crs_authid = frame_source_crs_authid
        self.polygon_sources = polygon_sources
        self.line_sources = line_sources
        self.project_crs_authid = project_crs_authid
        self.transform_context = transform_context
        self._on_finished = on_finished
        self.logs = []
        self.error_message = None
        self.output_geometries = []
        self.stats = {}

    def _log(self, message, level=Qgis.Info):
        timestamp = time.strftime('%H:%M:%S')
        line = f'[{timestamp}] {message}'
        self.logs.append(line)
        QgsMessageLog.logMessage(line, 'BoundedPolygonGenerator', level)
        self.logGenerated.emit(line, int(level))

    def _timed_log(self, label, started_at, level=Qgis.Info):
        self._log(f'{label} ({time.perf_counter() - started_at:.2f}s)', level)

    def _transform_geometry(self, geometry, source_crs, target_crs):
        transformed = QgsGeometry(geometry)
        if source_crs.isValid() and target_crs.isValid() and source_crs != target_crs:
            xform = QgsCoordinateTransform(source_crs, target_crs, self.transform_context)
            transformed.transform(xform)
        return transformed

    def _target_rect_to_source_rect(self, source_crs, target_rect, target_crs):
        if target_rect is None or target_rect.isEmpty():
            return target_rect

        source_rect = target_rect
        if source_crs.isValid() and target_crs.isValid() and source_crs != target_crs:
            xform = QgsCoordinateTransform(target_crs, source_crs, self.transform_context)
            source_rect = xform.transformBoundingBox(target_rect)
        return source_rect

    def _collect_frame_geometries(self, source, source_crs, project_crs):
        geometries = []
        request = QgsFeatureRequest()
        request.setNoAttributes()
        for feature in source.getFeatures(request):
            if self.isCanceled():
                return []
            geom = feature.geometry()
            if not geom or geom.isNull() or geom.isEmpty():
                continue
            geom = self._transform_geometry(geom, source_crs, project_crs)
            if not geom.isGeosValid():
                geom = geom.makeValid()
            if geom.isEmpty():
                continue
            geometries.append(geom)
        return geometries

    def _collect_delimiter_geometries(self, sources, frame_mask_geom, frame_bbox, project_crs, polygon_mode=False, progress_start=24, progress_end=40):
        geometries = []
        engine = QgsGeometry.createGeometryEngine(frame_mask_geom.constGet())
        if engine is None:
            raise Exception('Failed to initialize geometry engine for the working frame.')
        engine.prepareGeometry()

        total_layers = max(1, len(sources))
        for layer_index, source_info in enumerate(sources, start=1):
            source = source_info['source']
            source_crs = QgsCoordinateReferenceSystem(source_info['crs'])
            source_rect = self._target_rect_to_source_rect(source_crs, frame_bbox, project_crs)
            request = self._build_source_request(source_crs, frame_bbox, project_crs)
            layer_count = 0
            seen = 0
            kept = 0
            layer_started = time.perf_counter()
            self._log(f"Scanning layer '{source_info['name']}' ({layer_index}/{total_layers}).")

            for feature in source.getFeatures(request):
                if self.isCanceled():
                    return []

                seen += 1
                if seen % 200 == 0:
                    self._log(f"Layer '{source_info['name']}': {seen} feature(s) scanned, {kept} kept so far.")

                geom = feature.geometry()
                if not geom or geom.isNull() or geom.isEmpty():
                    continue

                if polygon_mode and source_rect is not None and not source_rect.isEmpty():
                    source_bbox = geom.boundingBox()
                    if source_bbox.isEmpty() or not source_bbox.intersects(source_rect):
                        continue
                    if not source_rect.contains(source_bbox):
                        geom = geom.clipped(source_rect)
                        if geom.isEmpty():
                            continue
                        if not geom.isGeosValid():
                            geom = geom.makeValid()
                        if geom.isEmpty():
                            continue

                geom = self._transform_geometry(geom, source_crs, project_crs)
                if geom.isEmpty():
                    continue

                bbox = geom.boundingBox()
                if bbox.isEmpty() or not bbox.intersects(frame_bbox):
                    continue

                if polygon_mode:
                    if frame_bbox.contains(bbox):
                        clipped_geom = geom
                    else:
                        clipped_geom = geom.clipped(frame_bbox)
                        if clipped_geom.isEmpty():
                            continue
                        if not clipped_geom.isGeosValid():
                            clipped_geom = clipped_geom.makeValid()
                        if clipped_geom.isEmpty():
                            continue

                    parts = extract_polygon_parts(clipped_geom)
                    geometries.extend(parts)
                    added = len(parts)
                else:
                    if frame_bbox.contains(bbox):
                        clipped_geom = geom
                    else:
                        if not engine.intersects(geom.constGet()):
                            continue
                        clipped_geom = geom.intersection(frame_mask_geom)
                        if clipped_geom.isEmpty():
                            continue
                        if not clipped_geom.isGeosValid():
                            clipped_geom = clipped_geom.makeValid()
                        if clipped_geom.isEmpty():
                            continue

                    geometries.append(QgsGeometry(clipped_geom))
                    added = 1

                layer_count += added
                kept += added

            self._timed_log(
                f"Layer '{source_info['name']}' contributed {layer_count} geometry item(s) from {seen} scanned feature(s)",
                layer_started,
            )

            progress = progress_start + ((progress_end - progress_start) * layer_index / total_layers)
            self.setProgress(progress)

        return geometries

    def run(self):
        try:
            overall_started = time.perf_counter()
            project_crs = QgsCoordinateReferenceSystem(self.project_crs_authid)
            frame_crs = QgsCoordinateReferenceSystem(self.frame_source_crs_authid)
            self._log('Background processing started.')
            self.setProgress(2)

            step_started = time.perf_counter()
            frame_geometries = self._collect_frame_geometries(self.frame_source, frame_crs, project_crs)
            if not frame_geometries:
                raise Exception('No valid frame geometry was found for processing.')
            self._timed_log(f'Frame geometries collected: {len(frame_geometries)}', step_started)
            self.setProgress(12)

            step_started = time.perf_counter()
            frame_mask_geom = QgsGeometry.unaryUnion(frame_geometries)
            if frame_mask_geom.isEmpty() or not frame_mask_geom.isGeosValid():
                frame_mask_geom = frame_mask_geom.makeValid()
            if frame_mask_geom.isEmpty():
                raise Exception('The frame geometry became empty during processing.')
            frame_bbox = frame_mask_geom.boundingBox()
            self._timed_log('Working frame geometry built', step_started)
            self.setProgress(24)
            if self.isCanceled():
                return False

            step_started = time.perf_counter()
            polygon_delimiters = self._collect_delimiter_geometries(
                self.polygon_sources,
                frame_mask_geom,
                frame_bbox,
                project_crs,
                polygon_mode=True,
                progress_start=24,
                progress_end=40,
            )
            self._timed_log(f'Polygon delimiter geometries collected: {len(polygon_delimiters)}', step_started)
            self.setProgress(40)
            if self.isCanceled():
                return False

            if polygon_delimiters:
                step_started = time.perf_counter()
                polygon_mask = QgsGeometry.unaryUnion(polygon_delimiters)
                if polygon_mask and not polygon_mask.isEmpty() and not polygon_mask.isGeosValid():
                    polygon_mask = polygon_mask.makeValid()
                if polygon_mask and not polygon_mask.isEmpty():
                    frame_mask_geom = frame_mask_geom.difference(polygon_mask)
                    if frame_mask_geom and not frame_mask_geom.isEmpty() and not frame_mask_geom.isGeosValid():
                        frame_mask_geom = frame_mask_geom.makeValid()
                if not frame_mask_geom or frame_mask_geom.isEmpty():
                    raise Exception('The work area became empty after removing polygon delimiters.')
                frame_bbox = frame_mask_geom.boundingBox()
                self._timed_log('Polygon delimiters removed from the frame', step_started)
            else:
                self._log('No polygon delimiters were collected.', Qgis.Warning)
            self.setProgress(54)
            if self.isCanceled():
                return False

            step_started = time.perf_counter()
            line_delimiters = self._collect_delimiter_geometries(
                self.line_sources,
                frame_mask_geom,
                frame_bbox,
                project_crs,
                polygon_mode=False,
                progress_start=54,
                progress_end=68,
            )
            self._timed_log(f'Line delimiter geometries collected: {len(line_delimiters)}', step_started)
            self.setProgress(68)
            if self.isCanceled():
                return False

            step_started = time.perf_counter()
            if line_delimiters:
                line_geometries = [frame_mask_geom.boundary()]
                line_geometries.extend(line_delimiters)
                self._log(f'Building line network with {len(line_geometries)} geometry item(s).')
                noded_linework = QgsGeometry.unaryUnion(line_geometries)
                if noded_linework.isEmpty():
                    polygon_candidates = extract_polygon_parts(frame_mask_geom)
                    self._log('Line network was empty after union; using frame polygons directly.', Qgis.Warning)
                else:
                    polygonized = QgsGeometry.polygonize([noded_linework])
                    polygon_candidates = extract_polygon_parts(polygonized)
                    if not polygon_candidates:
                        polygon_candidates = extract_polygon_parts(frame_mask_geom)
                    self._log(f'Polygonization produced {len(polygon_candidates)} polygon part(s).')
            else:
                polygon_candidates = extract_polygon_parts(frame_mask_geom)
                self._log('No line delimiters were collected; using frame polygons directly.', Qgis.Warning)
            self._timed_log('Line network build and polygonization finished', step_started)
            self.setProgress(84)
            if self.isCanceled():
                return False

            step_started = time.perf_counter()
            normalized_output = []
            work_area_engine = QgsGeometry.createGeometryEngine(frame_mask_geom.constGet())
            if work_area_engine is None:
                raise Exception('Failed to initialize geometry engine for output filtering.')
            work_area_engine.prepareGeometry()
            for geom in polygon_candidates:
                if self.isCanceled():
                    return False
                for part_geom in extract_polygon_parts(geom):
                    if part_geom.isEmpty():
                        continue
                    if not work_area_engine.intersects(part_geom.constGet()):
                        continue
                    clipped = part_geom.intersection(frame_mask_geom)
                    if clipped.isEmpty():
                        continue
                    normalized_output.extend(extract_polygon_parts(clipped))
            self.output_geometries = [geom for geom in normalized_output if geom and not geom.isEmpty()]
            self._timed_log(f'Singlepart polygon candidates ready for output: {len(self.output_geometries)}', step_started)
            self.setProgress(96)

            self.stats = {
                'output_geometries': len(self.output_geometries),
                'elapsed': time.perf_counter() - overall_started,
            }
            self._log(f'Background processing finished in {self.stats["elapsed"]:.2f}s', Qgis.Success)
            self.setProgress(100)
            return True
        except Exception as exc:
            self.error_message = str(exc)
            self._log(f'Background processing error: {self.error_message}', Qgis.Critical)
            return False

    def finished(self, result):
        if self._on_finished:
            self._on_finished(self, result)


class PolygonGeneratorDialog(QDialog):
    OUTPUT_GROUP_NAME = "istools-output"

    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        self._current_task = None
        self.setWindowTitle(self.tr('Bounded Polygon Generator', 'Gerador de Pol?gonos Delimitados'))

        layout = QVBoxLayout()

        layout.addWidget(QLabel(self.tr('Frame Layer (Polygon):', 'Camada de Moldura (Pol?gono):')))
        self.frame_layer_combo = QComboBox()
        layout.addWidget(self.frame_layer_combo)

        layout.addWidget(QLabel(self.tr('Delimiter Layers (Line):', 'Camadas Delimitadoras (Linha):')))
        self.line_layer_list = QListWidget()
        self.line_layer_list.setSelectionMode(QListWidget.MultiSelection)
        layout.addWidget(self.line_layer_list)

        layout.addWidget(QLabel(self.tr('Delimiter Layers (Polygon):', 'Camadas Delimitadoras (Pol?gono):')))
        self.poly_layer_list = QListWidget()
        self.poly_layer_list.setSelectionMode(QListWidget.MultiSelection)
        layout.addWidget(self.poly_layer_list)

        self.status_label = QLabel(self.tr('Ready to process.', 'Pronto para processar.'))
        layout.addWidget(self.status_label)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(500)
        self.log_box.setMinimumHeight(180)
        layout.addWidget(self.log_box)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.run_button = QPushButton(self.tr('Generate Polygons', 'Gerar Pol?gonos'))
        self.run_button.clicked.connect(self.run_script)
        layout.addWidget(self.run_button)

        self.setLayout(layout)
        self.populate_layers()

    def tr(self, *string):
        return translate(string, QgsApplication.locale()[:2])

    def get_output_layer_name(self):
        return self.tr('Bounded Polygons', 'Pol?gonos Delimitados')

    def populate_layers(self):
        layers = QgsProject.instance().mapLayers().values()
        for layer in layers:
            if not isinstance(layer, QgsVectorLayer):
                continue
            name = layer.name()
            item = QListWidgetItem(name)
            item.setData(1000, layer)
            if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                self.frame_layer_combo.addItem(name, layer)
                self.poly_layer_list.addItem(item.clone())
            elif layer.geometryType() == QgsWkbTypes.LineGeometry:
                self.line_layer_list.addItem(item)

    def _set_busy(self, is_busy):
        self.run_button.setEnabled(not is_busy)
        self.frame_layer_combo.setEnabled(not is_busy)
        self.line_layer_list.setEnabled(not is_busy)
        self.poly_layer_list.setEnabled(not is_busy)

    def _append_log(self, line, level=Qgis.Info):
        self.log_box.appendPlainText(line)
        self.status_label.setText(line.split('] ', 1)[-1] if '] ' in line else line)
        if level == Qgis.Critical:
            self.status_label.setText(self.tr('Processing failed.', 'Processamento falhou.'))

    def _log_step(self, message, level=Qgis.Info):
        timestamp = time.strftime('%H:%M:%S')
        line = f'[{timestamp}] {message}'
        QgsMessageLog.logMessage(line, 'BoundedPolygonGenerator', level)
        self._append_log(line, level)

    def _probe_frame_selection(self, frame_layer):
        if frame_layer.selectedFeatureCount() > 0:
            return QgsVectorLayerSelectedFeatureSource(frame_layer)

        request = QgsFeatureRequest()
        request.setNoAttributes()
        sample = []
        for feature in frame_layer.getFeatures(request):
            sample.append(feature.id())
            if len(sample) > 1:
                raise Exception(self.tr(
                    'Select one or more frame features before running the tool.',
                    'Selecione uma ou mais fei??es da moldura antes de executar a ferramenta.',
                ))

        if not sample:
            raise Exception(self.tr('The frame layer has no features.', 'A camada de moldura n?o possui fei??es.'))

        return QgsVectorLayerFeatureSource(frame_layer)

    def _make_feature_source_info(self, layer):
        if layer.selectedFeatureCount() > 0:
            source = QgsVectorLayerSelectedFeatureSource(layer)
        else:
            source = QgsVectorLayerFeatureSource(layer)
        return {
            'name': layer.name(),
            'crs': layer.crs().authid(),
            'source': source,
        }

    def _build_output_layer(self, output_layer_name, project_crs):
        output_layer = QgsVectorLayer(f'Polygon?crs={project_crs}', output_layer_name, 'memory')
        provider = output_layer.dataProvider()
        provider.addAttributes([
            QgsField('id', QVariant.String),
            QgsField('description', QVariant.String),
            QgsField('area_otf', QVariant.Double),
        ])
        output_layer.updateFields()
        return output_layer

    def _finalize_output(self, geometries, output_layer_name, project_crs):
        output_layer = self._build_output_layer(output_layer_name, project_crs)
        provider = output_layer.dataProvider()
        metric_crs = QgsCoordinateReferenceSystem('EPSG:31985')
        transform_context = QgsProject.instance().transformContext()
        xform = QgsCoordinateTransform(output_layer.crs(), metric_crs, transform_context)
        output_features = []

        for original_geom in geometries:
            if not original_geom or original_geom.isEmpty():
                continue

            for part_geom in extract_polygon_parts(original_geom):
                area_m2 = 0.0
                try:
                    reprojected_geom = QgsGeometry(part_geom)
                    if reprojected_geom.transform(xform) == 0 and not reprojected_geom.isEmpty():
                        area_m2 = reprojected_geom.area()
                except Exception:
                    area_m2 = 0.0

                feature = QgsFeature(output_layer.fields())
                feature.setGeometry(part_geom)
                feature.setAttributes([str(uuid.uuid4()), None, area_m2])
                output_features.append(feature)

        if output_features:
            provider.addFeatures(output_features)

        output_layer.updateExtents()
        output_layer.triggerRepaint()
        self.iface.mapCanvas().refreshAllLayers()

        root = QgsProject.instance().layerTreeRoot()
        group = root.findGroup(self.OUTPUT_GROUP_NAME)
        if not group:
            group = root.insertGroup(0, self.OUTPUT_GROUP_NAME)

        QgsProject.instance().addMapLayer(output_layer, False)
        group.addLayer(output_layer)
        return output_layer, len(output_features)

    def _on_task_progress(self, progress):
        self.progress_bar.setValue(int(progress))

    def _on_task_log(self, line, level):
        self._append_log(line, level)

    def _on_task_finished(self, task, success):
        self._current_task = None
        self._set_busy(False)
        self.progress_bar.setValue(100 if success else 0)

        if not success:
            QMessageBox.critical(
                self,
                self.tr('Error', 'Erro'),
                task.error_message or self.tr('Processing canceled.', 'Processamento cancelado.'),
            )
            return

        output_layer_name = self.get_output_layer_name()
        project_crs = QgsProject.instance().crs().authid()
        self._log_step(
            self.tr(
                f'Writing {len(task.output_geometries)} polygon geometry candidate(s) to the output layer.',
                f'Gravando {len(task.output_geometries)} geometria(s) poligonal(is) candidata(s) na camada de sa?da.',
            )
        )
        _, feature_count = self._finalize_output(task.output_geometries, output_layer_name, project_crs)
        self._log_step(
            self.tr(
                f'Output polygon features added: {feature_count}',
                f'Fei??es poligonais adicionadas na sa?da: {feature_count}',
            ),
            Qgis.Success,
        )
        self.iface.messageBar().pushSuccess(
            self.tr('Success', 'Sucesso'),
            self.tr(
                f"Layer '{output_layer_name}' created successfully. {feature_count} features added.",
                f"Camada '{output_layer_name}' criada com sucesso. {feature_count} fei??es adicionadas.",
            ),
        )
        self.status_label.setText(self.tr('Processing finished.', 'Processamento conclu?do.'))

    def run_script(self):
        self._set_busy(True)
        self.progress_bar.setValue(0)
        self.log_box.clear()

        try:
            frame_layer = self.frame_layer_combo.currentData()
            if not frame_layer:
                raise Exception(self.tr('Please select a frame layer.', 'Por favor, selecione uma camada de moldura.'))

            selected_line_layers = [item.data(1000) for item in self.line_layer_list.selectedItems()]
            selected_poly_layers = [item.data(1000) for item in self.poly_layer_list.selectedItems()]
            if not selected_line_layers and not selected_poly_layers:
                raise Exception(
                    self.tr(
                        'Select at least one delimiter layer (line or polygon).',
                        'Selecione pelo menos uma camada delimitadora (linha ou pol?gono).',
                    )
                )

            self._log_step(self.tr('Validating inputs.', 'Validando entradas.'))
            frame_source = self._probe_frame_selection(frame_layer)
            polygon_sources = [self._make_feature_source_info(layer) for layer in selected_poly_layers]
            line_sources = [self._make_feature_source_info(layer) for layer in selected_line_layers]
            self._log_step(
                self.tr(
                    f'Starting background task with {len(line_sources)} line layer(s) and {len(polygon_sources)} polygon layer(s).',
                    f'Iniciando tarefa em segundo plano com {len(line_sources)} camada(s) linear(es) e {len(polygon_sources)} camada(s) poligonal(is).',
                )
            )
            if polygon_sources:
                selected_poly_summary = ', '.join(
                    info['name'] for info in polygon_sources
                )
                self._log_step(
                    self.tr(
                        f'Selected polygon layers: {selected_poly_summary}',
                        f'Camadas poligonais selecionadas: {selected_poly_summary}',
                    )
                )
            if line_sources:
                selected_line_summary = ', '.join(
                    info['name'] for info in line_sources
                )
                self._log_step(
                    self.tr(
                        f'Selected line layers: {selected_line_summary}',
                        f'Camadas lineares selecionadas: {selected_line_summary}',
                    )
                )

            self._current_task = BoundedPolygonGenerationTask(
                self.tr('Generate bounded polygons', 'Gerar pol?gonos delimitados'),
                frame_source,
                frame_layer.crs().authid(),
                polygon_sources,
                line_sources,
                QgsProject.instance().crs().authid(),
                QgsProject.instance().transformContext(),
                self._on_task_finished,
            )
            self._current_task.progressChanged.connect(self._on_task_progress)
            self._current_task.logGenerated.connect(self._on_task_log)
            QgsApplication.taskManager().addTask(self._current_task)
        except Exception as exc:
            self._set_busy(False)
            self.progress_bar.setValue(0)
            self._log_step(self.tr(f'Processing error: {str(exc)}', f'Erro de processamento: {str(exc)}'), Qgis.Critical)
            QMessageBox.critical(self, self.tr('Error', 'Erro'), str(exc))
