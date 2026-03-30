# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Bounded Polygon Generator
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

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QComboBox, QMessageBox
)
from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsWkbTypes, QgsProcessingContext,
    QgsProcessingFeedback, QgsField, QgsFeature, QgsGeometry,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsMessageLog, Qgis, QgsApplication
)
from .translations.translate import translate
import processing


class BoundedPolygonGenerator:
    """
    A QGIS tool for generating bounded polygons using frame and delimiter layers.
    
    This class provides functionality to create polygons bounded by a frame layer
    and delimited by line or polygon layers through a dialog interface.
    """
    
    # Nome do grupo de saída
    OUTPUT_GROUP_NAME = "istools-output"
    
    def get_output_layer_name(self):
        """Get translated output layer name."""
        return self.tr("Bounded Polygons", "Polígonos Delimitados")
    
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
        Initialize the bounded polygon generator tool.
        
        Args:
            iface: QGIS interface object
        """
        self.iface = iface
        self.dialog = None

    def activate_tool(self):
        """
        Activate the bounded polygon generation tool by showing the dialog.
        """
        self.dialog = PolygonGeneratorDialog(self.iface)
        self.dialog.show()

    def unload(self):
        """
        Clean up when the tool is unloaded.
        """
        if self.dialog:
            self.dialog.close()
            self.dialog = None


class PolygonGeneratorDialog(QDialog):
    """
    Dialog for configuring and running the bounded polygon generation process.
    
    This dialog allows users to select frame layers and delimiter layers,
    then generates bounded polygons based on the selected configuration.
    """
    
    # Nome do grupo de saída
    OUTPUT_GROUP_NAME = "istools-output"
    
    def get_output_layer_name(self):
        """Get translated output layer name."""
        return self.tr("Bounded Polygons", "Polígonos Delimitados")
    
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
        Initialize the dialog interface.
        
        Args:
            iface: QGIS interface object
        """
        super().__init__()
        self.iface = iface
        self.setWindowTitle(self.tr("Bounded Polygon Generator", "Gerador de Polígonos Limitados"))
        
        # Create layout and widgets
        layout = QVBoxLayout()
        
        # Frame layer selection
        layout.addWidget(QLabel(self.tr("Frame Layer (Polygon):", "Camada de Moldura (Polígono):")))
        self.frame_layer_combo = QComboBox()
        layout.addWidget(self.frame_layer_combo)
        
        # Delimiter layers selection
        layout.addWidget(QLabel(self.tr("Delimiter Layers (Line):", "Camadas Delimitadoras (Linha):")))
        self.line_layer_list = QListWidget()
        self.line_layer_list.setSelectionMode(QListWidget.MultiSelection)
        layout.addWidget(self.line_layer_list)
        
        layout.addWidget(QLabel(self.tr("Delimiter Layers (Polygon):", "Camadas Delimitadoras (Polígono):")))
        self.poly_layer_list = QListWidget()
        self.poly_layer_list.setSelectionMode(QListWidget.MultiSelection)
        layout.addWidget(self.poly_layer_list)
        
        # Run button
        self.run_button = QPushButton(self.tr("Generate Polygons", "Gerar Polígonos"))
        self.run_button.clicked.connect(self.run_script)
        layout.addWidget(self.run_button)
        
        self.setLayout(layout)
        self.populate_layers()

    def populate_layers(self):
        """
        Populate the layer selection widgets with available layers from the project.
        """
        layers = QgsProject.instance().mapLayers().values()
        
        for layer in layers:
            if isinstance(layer, QgsVectorLayer):
                name = layer.name()
                item = QListWidgetItem(name)
                item.setData(1000, layer)
                
                if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                    # Add to frame layer combo and polygon delimiter list
                    self.frame_layer_combo.addItem(name, layer)
                    self.poly_layer_list.addItem(item.clone())
                elif layer.geometryType() == QgsWkbTypes.LineGeometry:
                    # Add to line delimiter list
                    self.line_layer_list.addItem(item)

    def run_script(self):
        """
        Execute the bounded polygon generation process.
        
        This method performs the following steps:
        1. Validate input selections
        2. Create temporary merged layer with all delimiter geometries
        3. Process geometries through dissolve, fix, and polygonize operations
        4. Clip results by frame layer
        5. Remove overlaps with delimiter polygons
        6. Calculate areas and add features to output layer
        """
        try:
            # Validate frame layer selection
            frame_layer = self.frame_layer_combo.currentData()
            if not frame_layer:
                raise Exception(self.tr("Please select a frame layer.", "Por favor, selecione uma camada de moldura."))
            
            # Get selected delimiter layers
            selected_line_layers = [
                item.data(1000) for item in self.line_layer_list.selectedItems()
            ]
            selected_poly_layers = [
                item.data(1000) for item in self.poly_layer_list.selectedItems()
            ]
            
            if not selected_line_layers and not selected_poly_layers:
                raise Exception(self.tr("Select at least one delimiter layer (line or polygon).", "Selecione pelo menos uma camada delimitadora (linha ou polígono)."))
            
            # Initialize processing context
            feedback = QgsProcessingFeedback()
            context = QgsProcessingContext()
            project_crs = QgsProject.instance().crs().authid()
            
            # Create output layer
            output_layer_name = self.get_output_layer_name()
            output_layer = QgsVectorLayer(
                f"Polygon?crs={project_crs}", 
                output_layer_name, 
                "memory"
            )
            provider = output_layer.dataProvider()
            provider.addAttributes([
                QgsField('id', QVariant.String),
                QgsField('description', QVariant.String),
                QgsField('area_otf', QVariant.Double)
            ])
            output_layer.updateFields()
            output_layer.startEditing()
            
            # Create temporary layer for merged lines
            merged = QgsVectorLayer(
                f"LineString?crs={project_crs}", 
                "merged_lines", 
                "memory"
            )
            
            # Add delimiter polygon features (converting to lines)
            for layer in selected_poly_layers:
                for feature in layer.getFeatures():
                    geom = feature.geometry()
                    if geom.isEmpty() or not geom.isGeosValid():
                        continue
                    
                    boundary_geom = geom.convertToType(QgsWkbTypes.LineGeometry, True)
                    if boundary_geom and not boundary_geom.isEmpty():
                        new_feat = QgsFeature()
                        new_feat.setGeometry(boundary_geom)
                        merged.dataProvider().addFeature(new_feat)
            
            # Add delimiter line features
            for layer in selected_line_layers:
                for feature in layer.getFeatures():
                    geom = feature.geometry()
                    if geom.isEmpty() or not geom.isGeosValid():
                        continue
                    
                    new_feat = QgsFeature()
                    new_feat.setGeometry(geom)
                    merged.dataProvider().addFeature(new_feat)
            
            # Add frame features (converting to lines)
            for feature in frame_layer.getFeatures():
                geom = feature.geometry()
                if geom.isEmpty() or not geom.isGeosValid():
                    continue
                
                boundary_geom = geom.convertToType(QgsWkbTypes.LineGeometry, True)
                if boundary_geom and not boundary_geom.isEmpty():
                    new_feat = QgsFeature()
                    new_feat.setGeometry(boundary_geom)
                    merged.dataProvider().addFeature(new_feat)
            
            merged.updateExtents()
            
            # Dissolve merged lines
            dissolved = processing.run("native:dissolve", {
                'INPUT': merged,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)['OUTPUT']
            
            # Fix geometries
            fixed = processing.run("native:fixgeometries", {
                'INPUT': dissolved,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)['OUTPUT']
            
            # Polygonize lines
            try:
                polygons = processing.run("native:linestopolygons", {
                    'INPUT': fixed,
                    'OUTPUT': 'memory:'
                }, context=context, feedback=feedback)['OUTPUT']
            except:
                polygons = processing.run("native:polygonize", {
                    'INPUT': fixed,
                    'OUTPUT': 'memory:'
                }, context=context, feedback=feedback)['OUTPUT']
            
            # Clip by frame layer
            bounded = processing.run("native:intersection", {
                'INPUT': polygons,
                'OVERLAY': frame_layer,
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)['OUTPUT']
            
            # Remove overlap with delimiter polygons
            if selected_poly_layers:
                merged_polys = processing.run("native:mergevectorlayers", {
                    'LAYERS': selected_poly_layers,
                    'CRS': project_crs,
                    'OUTPUT': 'memory:'
                }, context=context, feedback=feedback)['OUTPUT']
                
                final_result = processing.run("native:difference", {
                    'INPUT': bounded,
                    'OVERLAY': merged_polys,
                    'OUTPUT': 'memory:'
                }, context=context, feedback=feedback)['OUTPUT']
            else:
                final_result = bounded
            
            # Add 'id' field with UUID
            final_result = processing.run("qgis:fieldcalculator", {
                'INPUT': final_result,
                'FIELD_NAME': 'id',
                'FIELD_TYPE': 2,
                'FIELD_LENGTH': 40,
                'FIELD_PRECISION': 0,
                'NEW_FIELD': True,
                'FORMULA': "replace(replace(uuid(), '{', ''), '}', '')",
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)['OUTPUT']
            
            # Add 'description' field
            final_result = processing.run("qgis:fieldcalculator", {
                'INPUT': final_result,
                'FIELD_NAME': 'description',
                'FIELD_TYPE': 2,
                'FIELD_LENGTH': 255,
                'FIELD_PRECISION': 0,
                'NEW_FIELD': True,
                'FORMULA': "NULL",
                'OUTPUT': 'memory:'
            }, context=context, feedback=feedback)['OUTPUT']
            
            # Add features to output layer with area calculation
            num_features_added = 0
            metric_crs = QgsCoordinateReferenceSystem('EPSG:31985')
            transform_context = QgsProject.instance().transformContext()
            
            for feature in final_result.getFeatures():
                new_feature = QgsFeature(output_layer.fields())
                new_feature.setGeometry(feature.geometry())
                
                # Calculate area in metric CRS
                try:
                    original_geom = feature.geometry()
                    xform = QgsCoordinateTransform(
                        output_layer.crs(), 
                        metric_crs, 
                        transform_context
                    )
                    
                    reprojected_geom = QgsGeometry(original_geom)
                    transform_result = reprojected_geom.transform(xform)
                    
                    if (transform_result == 0 and 
                        reprojected_geom.isGeosValid() and 
                        not reprojected_geom.isEmpty()):
                        
                        area_m2 = reprojected_geom.area()
                        new_feature.setAttribute('area_otf', area_m2)
                        
                        QgsMessageLog.logMessage(
                            f"Calculated area: {area_m2} m² for feature with ID {feature['id']}",
                            'BoundedPolygonGenerator',
                            Qgis.Info
                        )
                    else:
                        new_feature.setAttribute('area_otf', 0.0)
                        QgsMessageLog.logMessage(
                            f"Error in coordinate transformation for area calculation for feature with ID {feature['id']}",
                            'BoundedPolygonGenerator',
                            Qgis.Warning
                        )
                        
                except Exception as e:
                    new_feature.setAttribute('area_otf', 0.0)
                    QgsMessageLog.logMessage(
                        f"Error calculating area for feature with ID {feature['id']}: {str(e)}",
                        'BoundedPolygonGenerator',
                        Qgis.Critical
                    )
                
                # Set other attributes
                new_feature.setAttribute('id', feature['id'])
                new_feature.setAttribute('description', feature['description'])
                
                if provider.addFeature(new_feature):
                    num_features_added += 1
            
            # Finalize output layer
            output_layer.updateExtents()
            output_layer.triggerRepaint()
            self.iface.mapCanvas().refreshAllLayers()
            
            # Create or get the istools-output group
            root = QgsProject.instance().layerTreeRoot()
            group = root.findGroup(self.OUTPUT_GROUP_NAME)
            if not group:
                group = root.insertGroup(0, self.OUTPUT_GROUP_NAME)
            
            # Add layer to project and move to group
            QgsProject.instance().addMapLayer(output_layer, False)
            group.addLayer(output_layer)
            
            # Close dialog and show success message
            self.close()
            self.iface.messageBar().pushSuccess(
                self.tr("Success", "Sucesso"), 
                self.tr(f"Layer '{output_layer_name}' created successfully. {num_features_added} features added.", f"Camada '{output_layer_name}' criada com sucesso. {num_features_added} feições adicionadas.")
            )
            
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error", "Erro"), str(e))
            if 'output_layer' in locals():
                QgsProject.instance().removeMapLayer(output_layer.id())
