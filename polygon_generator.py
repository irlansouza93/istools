# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Polygon Generator
                                 A QGIS plugin
 Professional vectorization toolkit for QGIS
                              -------------------
        begin                : 2025-01-15
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
import uuid
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsField, QgsMessageLog, Qgis, QgsApplication,
    QgsWkbTypes, QgsPointXY, QgsSymbol, QgsSingleSymbolRenderer,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform
)
from qgis.gui import QgsMapToolEmitPoint, QgsVertexMarker
from .translations.translate import translate
import processing


class QgisPolygonGenerator:
    """
    A QGIS tool for generating polygons by clicking on the map canvas.
    
    This class provides functionality to create polygons from existing line and polygon
    layers in the project by using the polygonize algorithm and selecting the polygon
    that contains the clicked point.
    """
    
    # Nome do grupo de saída
    OUTPUT_GROUP_NAME = "istools-output"
    
    def get_output_layer_name(self):
        """Get translated output layer name."""
        return self.tr("Generated Polygons", "Polígonos Gerados")
    
    def tr(self, *string):
        """
        Traduz strings usando o novo sistema de tradução bilíngue.
        
        Args:
            *string: (inglês, português) ou string única
            
        Returns:
            str: String traduzida conforme o locale do QGIS
        """
        return translate(string, QgsApplication.locale()[:2])
    
    def __init__(self, iface):
        """
        Initialize the polygon generator tool.
        
        Args:
            iface: QGIS interface object
        """
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.map_tool = QgsMapToolEmitPoint(self.canvas)
        self.marker = None
    
    def activate_tool(self):
        """
        Activate the polygon generation tool.
        
        Checks for valid layers and sets up the map tool for capturing clicks.
        """
        valid_layers = self._get_valid_layers()
        if not valid_layers:
            QMessageBox.information(
                None,
                'PolygonGenerator',
                self.tr('No visible layers found in the project.', 'Nenhuma camada visível encontrada no projeto.')
            )
            return
        
        self.map_tool.canvasClicked.connect(self.capture_and_create)
        self.canvas.setMapTool(self.map_tool)
        QMessageBox.information(
            None,
            'PolygonGenerator',
            self.tr('Click to define the center. Right-click to cancel.', 'Clique para definir o centro. Botão direito cancela.')
        )
    
    def _get_valid_layers(self):
        """
        Get all visible line and polygon layers from the project.
        
        Returns:
            list: List of valid QgsVectorLayer objects
        """
        root = QgsProject.instance().layerTreeRoot()
        valid_layers = []
        
        for layer in QgsProject.instance().mapLayers().values():
            if not isinstance(layer, QgsVectorLayer):
                continue
                
            node = root.findLayer(layer.id())
            if node is None or not node.isVisible():
                continue
                
            geometry_type = QgsWkbTypes.geometryType(layer.wkbType())
            if geometry_type in [QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry]:
                valid_layers.append(layer)
                
        return valid_layers
    
    def capture_and_create(self, point, button):
        """
        Handle canvas click events for polygon creation.
        
        Args:
            point: QgsPointXY representing the clicked point
            button: Mouse button pressed (1=left, 2=right)
        """
        # Right-click cancels the operation
        if button == 2:
            self._clear_marker()
            self.canvas.unsetMapTool(self.map_tool)
            self.iface.messageBar().pushInfo('PolygonGenerator', self.tr('Operation cancelled.', 'Operação cancelada.'))
            return
            
        # Clear existing marker and create new one
        if self.marker:
            self.marker.hide()
            self.marker = None
            
        self._create_marker(point)
        self.process_polygon(point)
    
    def _create_marker(self, point):
        """
        Create a visual marker at the clicked point.
        
        Args:
            point: QgsPointXY where to place the marker
        """
        self.marker = QgsVertexMarker(self.canvas)
        self.marker.setCenter(point)
        self.marker.setColor(QColor(255, 0, 0))
        self.marker.setFillColor(QColor(255, 0, 0, 100))
        self.marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
        self.marker.setIconSize(12)
        self.marker.setPenWidth(3)
    
    def process_polygon(self, point):
        """
        Process the polygon generation at the specified point.
        
        Args:
            point: QgsPointXY representing the center point
        """
        pt = QgsPointXY(point)
        center_geometry = QgsGeometry.fromPointXY(pt)
        temp_layer = self._create_temp_layer()
        features = self._collect_valid_features()
        
        if not features:
            self.iface.messageBar().pushWarning('PolygonGenerator', self.tr('No valid geometry found.', 'Nenhuma geometria válida encontrada.'))
            self._clear_marker()
            return
            
        # Add features to temporary layer
        temp_layer.dataProvider().addFeatures(features)
        temp_layer.updateExtents()
        
        # Execute polygonize algorithm
        polygon_layer = self._execute_polygonize(temp_layer)
        if not polygon_layer:
            return
        
        # Find polygon containing the clicked point
        selected_polygon = self._find_containing_polygon(polygon_layer, center_geometry)
        if not selected_polygon:
            self.iface.messageBar().pushWarning('PolygonGenerator', self.tr('No valid polygon found.', 'Nenhum polígono válido encontrado.'))
            self._clear_marker()
            return
        
        # Add polygon to output layer
        self._add_polygon_to_output_layer(selected_polygon)
    
    def _create_temp_layer(self):
        """
        Create a temporary memory layer for processing.
        
        Returns:
            QgsVectorLayer: Temporary line layer
        """
        crs_authid = self.canvas.mapSettings().destinationCrs().authid()
        return QgsVectorLayer(
            f"LineString?crs={crs_authid}",
            "_temp_lines",
            "memory"
        )
    
    def _collect_valid_features(self):
        """
        Collect all valid features from visible layers.
        
        Returns:
            list: List of QgsFeature objects ready for polygonization
        """
        features = []
        root = QgsProject.instance().layerTreeRoot()
        
        for layer in QgsProject.instance().mapLayers().values():
            if not isinstance(layer, QgsVectorLayer):
                continue
                
            node = root.findLayer(layer.id())
            if node is None or not node.isVisible():
                continue
            
            geometry_type = QgsWkbTypes.geometryType(layer.wkbType())
            if geometry_type not in [QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry]:
                continue
            
            for feature in layer.getFeatures():
                geometry = feature.geometry()
                if not geometry.isGeosValid() or geometry.isEmpty():
                    continue
                
                new_feature = QgsFeature()
                
                # Convert polygon boundaries to lines
                if geometry_type == QgsWkbTypes.PolygonGeometry:
                    boundaries = geometry.convertToType(QgsWkbTypes.LineGeometry, True)
                    if boundaries and not boundaries.isEmpty():
                        new_feature.setGeometry(boundaries)
                        features.append(new_feature)
                else:
                    new_feature.setGeometry(geometry)
                    features.append(new_feature)
        
        return features
    
    def _execute_polygonize(self, temp_layer):
        """
        Execute the QGIS polygonize algorithm.
        
        Args:
            temp_layer: QgsVectorLayer containing line geometries
            
        Returns:
            QgsVectorLayer or None: Resulting polygon layer or None if failed
        """
        try:
            result = processing.run(
                'qgis:polygonize',
                {'INPUT': temp_layer, 'KEEP_FIELDS': False, 'OUTPUT': 'memory:'}
            )
            return result['OUTPUT']
        except Exception as e:
            QMessageBox.critical(
                None, 
                self.tr("Error", "Erro"), 
                self.tr(f'Error executing polygonize: {str(e)}', f'Erro ao executar poligonização: {str(e)}')
            )
            self._clear_marker()
            return None
    
    def _find_containing_polygon(self, polygon_layer, center_geometry):
        """
        Find the polygon that contains the center point.
        
        Args:
            polygon_layer: QgsVectorLayer containing polygons
            center_geometry: QgsGeometry of the center point
            
        Returns:
            QgsGeometry or None: The containing polygon geometry
        """
        for feature in polygon_layer.getFeatures():
            geometry = feature.geometry()
            if geometry.contains(center_geometry) and geometry.isGeosValid():
                return geometry
        return None
    
    def _add_polygon_to_output_layer(self, polygon_geometry):
        """
        Add the generated polygon to the output layer.
        
        Args:
            polygon_geometry: QgsGeometry of the polygon to add
        """
        output_layer = self._get_or_create_output_layer()
        
        # Start editing if not already in edit mode
        if not output_layer.isEditable():
            output_layer.startEditing()
        
        # Check if polygon already exists
        if self._polygon_exists(output_layer, polygon_geometry):
            self.iface.messageBar().pushInfo('PolygonGenerator', self.tr('Polygon already exists.', 'Polígono já existe.'))
            self._clear_marker()
            return
        
        # Create and add the feature
        feature = self._create_polygon_feature(output_layer, polygon_geometry)
        if not output_layer.addFeature(feature):
            QMessageBox.critical(
                None, 
                self.tr("Error", "Erro"), 
                self.tr('Error adding feature.', 'Erro ao adicionar feição.')
            )
            self._clear_marker()
            return
        
        # Update layer display
        output_layer.updateExtents()
        output_layer.triggerRepaint()
        self.canvas.refreshAllLayers()
        
        # Log success message
        feature_id = feature.attribute('id')
        QgsMessageLog.logMessage(
            self.tr(f'Feature added with ID {feature_id}. Total: {output_layer.featureCount()}', f'Feição adicionada com ID {feature_id}. Total: {output_layer.featureCount()}'),
            'PolygonGenerator',
            Qgis.Info
        )
        self.iface.messageBar().pushInfo(
            'PolygonGenerator',
            self.tr(f'Polygon added with ID {feature_id}. Layer in edit mode.', f'Polígono adicionado com ID {feature_id}. Camada em modo de edição.')
        )
        
        self._clear_marker()
    
    class PolygonGenerator:
        """
        A QGIS tool for generating polygons from point collections.
        
        This class provides functionality to create polygon geometries from
        selected point features using various generation methods.
        """
        
        # Nome da camada de saída com tradução
        def get_output_layer_name(self):
            """Get translated output layer name."""
            return self.tr("Generated Polygons", "Polígonos Gerados")
        
        # Nome do grupo de saída
        OUTPUT_GROUP_NAME = "istools-output"
    
    def _get_or_create_output_layer(self):
        """
        Get existing output layer or create a new one.
        
        Returns:
            QgsVectorLayer: The output layer for generated polygons
        """
        output_layer_name = self.get_output_layer_name()
        
        # Check if output layer already exists
        for layer in QgsProject.instance().mapLayers().values():
            if (layer.name() == output_layer_name and
                isinstance(layer, QgsVectorLayer)):
                return layer
        
        # Create new output layer
        crs_authid = self.canvas.mapSettings().destinationCrs().authid()
        output_layer = QgsVectorLayer(
            f"Polygon?crs={crs_authid}",
            output_layer_name,
            "memory"
        )
        
        # Add fields to the layer
        provider = output_layer.dataProvider()
        provider.addAttributes([
            QgsField('id', QVariant.String),
            QgsField('description', QVariant.String),
            QgsField('area_otf', QVariant.Double)
        ])
        output_layer.updateFields()
        
        # Set layer symbology
        symbol = QgsSymbol.defaultSymbol(output_layer.geometryType())
        symbol.setColor(QColor(255, 0, 0, 100))
        renderer = QgsSingleSymbolRenderer(symbol)
        output_layer.setRenderer(renderer)
        
        # Create or get the istools-output group
        root = QgsProject.instance().layerTreeRoot()
        group = root.findGroup(self.OUTPUT_GROUP_NAME)
        if not group:
            group = root.insertGroup(0, self.OUTPUT_GROUP_NAME)
        
        # Add layer to project and move to group
        QgsProject.instance().addMapLayer(output_layer, False)
        group.addLayer(output_layer)
        
        return output_layer
    
    def _polygon_exists(self, layer, geometry):
        """
        Check if a polygon with the same geometry already exists.
        
        Args:
            layer: QgsVectorLayer to check
            geometry: QgsGeometry to compare
            
        Returns:
            bool: True if polygon exists, False otherwise
        """
        for feature in layer.getFeatures():
            if feature.geometry().equals(geometry):
                return True
        return False
    
    def _create_polygon_feature(self, layer, geometry):
        """
        Create a new polygon feature with calculated attributes.
        
        Args:
            layer: QgsVectorLayer where the feature will be added
            geometry: QgsGeometry of the polygon
            
        Returns:
            QgsFeature: The created feature with attributes
        """
        feature = QgsFeature(layer.fields())
        feature.setGeometry(geometry)
        
        # Generate unique ID
        feature_id = str(uuid.uuid4()).replace('{', '').replace('}', '')
        
        # Initialize attributes array
        attributes = [None] * layer.fields().count()
        attributes[layer.fields().indexFromName('id')] = feature_id
        attributes[layer.fields().indexFromName('description')] = None
        
        # Calculate area in target CRS (EPSG:31985)
        try:
            source_crs = self.canvas.mapSettings().destinationCrs()
            target_crs = QgsCoordinateReferenceSystem('EPSG:31985')
            
            if not target_crs.isValid():
                QgsMessageLog.logMessage(
                    "Target CRS (EPSG:31985) invalid.",
                    'PolygonGenerator',
                    Qgis.Critical
                )
                attributes[layer.fields().indexFromName('area_otf')] = 0.0
                feature.setAttributes(attributes)
                return feature
            
            # Transform geometry to target CRS
            transform_context = QgsProject.instance().transformContext()
            xform = QgsCoordinateTransform(source_crs, target_crs, transform_context)
            
            geom_transformed = QgsGeometry(geometry)
            transform_result = geom_transformed.transform(xform)
            
            if transform_result != 0:
                QgsMessageLog.logMessage(
                    f"Coordinate transformation error: {transform_result}",
                    'PolygonGenerator',
                    Qgis.Warning
                )
                attributes[layer.fields().indexFromName('area_otf')] = 0.0
            elif geom_transformed.isEmpty() or not geom_transformed.isGeosValid():
                QgsMessageLog.logMessage(
                    "Empty or invalid geometry after transformation.",
                    'PolygonGenerator',
                    Qgis.Warning
                )
                attributes[layer.fields().indexFromName('area_otf')] = 0.0
            else:
                area_m2 = geom_transformed.area()
                attributes[layer.fields().indexFromName('area_otf')] = area_m2
                QgsMessageLog.logMessage(
                    f"Calculated area: {area_m2} m²",
                    'PolygonGenerator',
                    Qgis.Info
                )
                
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error calculating area: {str(e)}",
                'PolygonGenerator',
                Qgis.Critical
            )
            attributes[layer.fields().indexFromName('area_otf')] = 0.0
        
        feature.setAttributes(attributes)
        return feature
    
    def _clear_marker(self):
        """
        Clear the visual marker from the canvas.
        """
        if self.marker:
            self.marker.hide()
            self.marker = None
    
    def unload(self):
        """
        Clean up when the tool is unloaded.
        """
        self.canvas.unsetMapTool(self.map_tool)
        self._clear_marker()
