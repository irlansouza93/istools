# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Point on Surface Generator
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

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsField,
    QgsWkbTypes,
    QgsMapLayer,
    QgsApplication
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox
from .translations.translate import translate
import uuid


class PointOnSurfaceGenerator:
    """
    A QGIS tool for generating points on the surface of selected polygons.
    
    This class provides functionality to create point features at the centroid
    or representative point of selected polygon features, ensuring points are
    within the polygon boundaries.
    """
    
    # Nome do grupo de saída
    OUTPUT_GROUP_NAME = "istools-output"
    
    def get_output_layer_name(self):
        """Get translated output layer name."""
        return self.tr("Points on Surface", "Pontos na Superfície")
    
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
        Initialize the point on surface generator tool.
        
        Args:
            iface: QGIS interface object
        """
        self.iface = iface

    def run(self):
        """
        Execute the point on surface generation process.
        
        This method performs the following steps:
        1. Validates the active layer is a polygon vector layer
        2. Checks for selected polygon features
        3. Creates or retrieves the output point layer
        4. Generates points on surface for each selected polygon
        5. Adds new point features to the output layer
        
        The method creates points that are guaranteed to be within the polygon
        boundaries and avoids creating duplicate points at the same coordinates.
        """
        # Get the active layer
        layer = self.iface.activeLayer()

        # Validate active layer exists
        if not layer:
            QMessageBox.information(
                self.iface.mainWindow(), 
                self.tr("Error", "Erro"), 
                self.tr("No active layer. Please select a polygon layer.", "Nenhuma camada ativa. Por favor, selecione uma camada de polígonos.")
            )
            return
            
        # Validate layer is a vector layer
        if layer.type() != QgsMapLayer.VectorLayer:
            QMessageBox.information(
                self.iface.mainWindow(), 
                self.tr("Error", "Erro"), 
                self.tr("The active layer is not a vector layer.", "A camada ativa não é uma camada vetorial.")
            )
            return
            
        # Validate layer contains polygon geometries
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            QMessageBox.information(
                self.iface.mainWindow(), 
                self.tr("Error", "Erro"), 
                self.tr("This is not a polygon layer.", "Esta não é uma camada de polígonos.")
            )
            return

        # Get selected features
        selected_features = layer.selectedFeatures()
        if not selected_features:
            QMessageBox.information(
                self.iface.mainWindow(), 
                self.tr("Warning", "Aviso"), 
                self.tr("No polygons selected. Please select at least one polygon.", "Nenhum polígono selecionado. Por favor, selecione pelo menos um polígono.")
            )
            return

        # Get or create the output point layer
        project = QgsProject.instance()
        point_layer = self._get_or_create_point_layer(project, layer)
        
        # Get existing coordinates to avoid duplicates
        existing_coords = self._get_existing_coordinates(point_layer)

        # Ensure layer is editable
        if not point_layer.isEditable():
            point_layer.startEditing()

        # Process selected features and create points
        features_to_add = self._create_point_features(
            selected_features, 
            point_layer, 
            existing_coords
        )

        # Add new features to the layer
        if features_to_add:
            point_layer.addFeatures(features_to_add)
            point_layer.updateExtents()
            point_layer.triggerRepaint()
            self.iface.mapCanvas().refreshAllLayers()
            
            QMessageBox.information(
                self.iface.mainWindow(), 
                self.tr("Success", "Sucesso"), 
                self.tr(f"{len(features_to_add)} point(s) created successfully.", f"{len(features_to_add)} ponto(s) criado(s) com sucesso.")
            )
        else:
            QMessageBox.information(
                self.iface.mainWindow(), 
                self.tr("Info", "Informação"), 
                self.tr("No new points were created.", "Nenhum novo ponto foi criado.")
            )

    def _get_or_create_point_layer(self, project, source_layer):
        """
        Get existing point layer or create a new one.
        
        Args:
            project: QgsProject instance
            source_layer: Source polygon layer for CRS reference
            
        Returns:
            QgsVectorLayer: The point layer for output
        """
        # Check if point layer already exists
        point_layer = None
        output_layer_name = self.get_output_layer_name()
        for layer in project.mapLayers().values():
            if layer.name() == output_layer_name:
                point_layer = layer
                break

        # Create new point layer if it doesn't exist
        if not point_layer:
            crs = source_layer.crs().authid()
            point_layer = QgsVectorLayer(
                f"Point?crs={crs}", 
                output_layer_name, 
                "memory"
            )
            
            # Add fields to the point layer
            provider = point_layer.dataProvider()
            provider.addAttributes([
                QgsField("id", QVariant.String),
                QgsField("coords", QVariant.String)
            ])
            point_layer.updateFields()
            
            # Create or get the istools-output group
            root = project.layerTreeRoot()
            group = root.findGroup(self.OUTPUT_GROUP_NAME)
            if not group:
                group = root.insertGroup(0, self.OUTPUT_GROUP_NAME)
            
            # Add layer to project and move to group
            project.addMapLayer(point_layer, False)
            group.addLayer(point_layer)
            
        return point_layer

    def _get_existing_coordinates(self, point_layer):
        """
        Get set of existing coordinate strings to avoid duplicates.
        
        Args:
            point_layer: The point layer to check for existing coordinates
            
        Returns:
            set: Set of coordinate strings in format "x.xxxxxx, y.yyyyyy"
        """
        existing_coords = set()
        for feature in point_layer.getFeatures():
            coords = feature["coords"]
            if coords:
                existing_coords.add(coords)
        return existing_coords

    def _create_point_features(self, selected_features, point_layer, existing_coords):
        """
        Create point features from selected polygon features.
        
        Args:
            selected_features: List of selected polygon features
            point_layer: Target point layer
            existing_coords: Set of existing coordinate strings
            
        Returns:
            list: List of QgsFeature objects to be added to the point layer
        """
        features_to_add = []
        
        for feature in selected_features:
            geom = feature.geometry()
            
            # Skip invalid or empty geometries
            if not geom or geom.isEmpty():
                continue
                
            # Generate point on surface
            point_geom = geom.pointOnSurface()
            pt = point_geom.asPoint()
            coords_str = f"{pt.x():.6f}, {pt.y():.6f}"

            # Skip if point already exists at these coordinates
            if coords_str in existing_coords:
                QMessageBox.information(
                    self.iface.mainWindow(), 
                    self.tr("Warning", "Aviso"), 
                    self.tr(f"A point already exists at {coords_str}. Skipping.", f"Um ponto já existe em {coords_str}. Pulando.")
                )
                continue

            # Create new point feature
            point_feature = QgsFeature(point_layer.fields())
            point_feature.setGeometry(point_geom)
            point_feature.setAttribute("id", str(uuid.uuid4()))
            point_feature.setAttribute("coords", coords_str)

            features_to_add.append(point_feature)
            existing_coords.add(coords_str)
            
        return features_to_add

    def unload(self):
        """
        Clean up when the tool is unloaded.
        
        This method is called when the plugin is unloaded and can be used
        to perform any necessary cleanup operations.
        """
        pass
