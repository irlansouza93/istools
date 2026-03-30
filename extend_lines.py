# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Extend Lines
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

from qgis.gui import QgsMapToolIdentifyFeature
from qgis.core import (
    QgsProject, QgsGeometry, QgsPointXY, QgsLineString, 
    QgsSpatialIndex, QgsFeature, QgsWkbTypes, QgsPoint, QgsApplication
)
from qgis.PyQt.QtWidgets import QInputDialog, QMessageBox
from qgis.utils import iface
from .translations.translate import translate
import math


class ExtendLines:
    """
    A QGIS tool for extending line features to touch other line features.
    
    This tool allows users to extend selected line features until they intersect
    with other line features in the project. The extension is performed in the
    direction of the line's bearing at each endpoint.
    """
    
    # Nome do grupo de saída (não usado nesta ferramenta, mas mantido para consistência)
    OUTPUT_GROUP_NAME = "istools-output"

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
        Initialize the ExtendLines tool.
        
        Args:
            iface: QGIS interface object providing access to the map canvas,
                  layers, and other QGIS functionality.
        """
        self.iface = iface

    def run(self):
        """
        Execute the line extension process.
        
        This method performs the following steps:
        1. Validates the active layer is a line layer
        2. Checks for selected features
        3. Prompts user to select target layer
        4. Extends selected lines to intersect with target layer features
        5. Updates geometries and adds topological points
        """
        # Validate active layer
        source_layer = self.iface.activeLayer()
        if not source_layer or source_layer.geometryType() != QgsWkbTypes.LineGeometry:
            QMessageBox.warning(None, self.tr("Error", "Erro"), self.tr("Activate a line layer as source before executing.", "Ative uma camada de linha como origem antes de executar."))
            return
        
        # Start editing session
        source_layer.startEditing()
        
        # Check for selected features
        selected_features = source_layer.selectedFeatures()
        if not selected_features:
            QMessageBox.information(None, self.tr("Selection", "Seleção"), self.tr("No lines selected. Activating selection tool.", "Nenhuma linha selecionada. Ativando ferramenta de seleção."))
            self.iface.actionSelectRectangle().trigger()
            print(self.tr("Select lines using the activated tool and run the script again to proceed.", "Selecione linhas usando a ferramenta ativada e execute o script novamente para prosseguir."))
            return
        
        print(self.tr("{} line(s) selected found. Proceeding.", "{} linha(s) selecionada(s) encontrada(s). Prosseguindo.").format(len(selected_features)))
        
        # Get available line layers for target selection
        line_layers = [layer.name() for layer in QgsProject.instance().mapLayers().values() 
                       if layer.type() == 0 and layer.geometryType() == QgsWkbTypes.LineGeometry]
        if not line_layers:
            QMessageBox.warning(None, self.tr("Error", "Erro"), self.tr("No line layers found in the project.", "Nenhuma camada de linha encontrada no projeto."))
            return
        
        # Prompt user to select target layer
        target_name, ok = QInputDialog.getItem(
            None, self.tr("Target Layer", "Camada de Destino"), self.tr("Select the target layer (to be touched):", "Selecione a camada de destino (a ser tocada):"), 
            line_layers, 0, False
        )
        if not ok:
            print(self.tr("Operation cancelled.", "Operação cancelada."))
            return
        
        # Get target layer and start editing
        target_layer = QgsProject.instance().mapLayersByName(target_name)[0]
        target_layer.startEditing()
        
        # Build spatial index for target layer features
        selected_ids = [f.id() for f in selected_features]
        index_target = QgsSpatialIndex()
        for feat in target_layer.getFeatures():
            # Skip selected features if target is same as source layer
            if target_layer == source_layer and feat.id() in selected_ids:
                continue
            index_target.insertFeature(feat)
        
        # Get current canvas extent for visibility checks
        canvas_extent = self.iface.mapCanvas().extent()
        extensions_performed = False
        
        # Process each selected feature
        for selected_feature in selected_features:
            geom = selected_feature.geometry()
            
            # Check if feature is visible in current canvas extent
            if not geom.boundingBox().intersects(canvas_extent):
                QMessageBox.warning(
                    None, self.tr("Warning", "Aviso"), 
                    self.tr(f"Selected feature is outside canvas view for ID {selected_feature.id()}. Skipping.", f"Feição selecionada está fora da visualização do canvas para ID {selected_feature.id()}. Pulando.")
                )
                print(self.tr("Feature ID {} outside canvas view. Skipping.", "ID da feição {} fora da visualização do canvas. Pulando.").format(selected_feature.id()))
                continue
            
            # Extract line points from geometry
            if geom.isMultipart():
                line_points = geom.asMultiPolyline()[0]
            else:
                line_points = geom.asPolyline()
            
            # Validate line has at least 2 points
            if len(line_points) < 2:
                print(self.tr("Feature ID {} invalid (less than 2 points). Skipping.", "ID da feição {} inválido (menos de 2 pontos). Pulando.").format(selected_feature.id()))
                continue
            
            # Check if endpoints already intersect with target features
            start_vertex_geom = QgsGeometry.fromPointXY(line_points[0])
            end_vertex_geom = QgsGeometry.fromPointXY(line_points[-1])
            ignore_start = False
            ignore_end = False
            
            # Check start vertex intersection
            candidates = index_target.intersects(start_vertex_geom.boundingBox())
            for fid in candidates:
                feat = target_layer.getFeature(fid)
                if start_vertex_geom.intersects(feat.geometry()):
                    ignore_start = True
                    break
            
            # Check end vertex intersection
            candidates = index_target.intersects(end_vertex_geom.boundingBox())
            for fid in candidates:
                feat = target_layer.getFeature(fid)
                if end_vertex_geom.intersects(feat.geometry()):
                    ignore_end = True
                    break
            
            # Skip if both endpoints already intersect
            if ignore_start and ignore_end:
                print(self.tr("Both endpoints of feature ID {} already intersect. Skipping.", "Ambos os pontos finais da feição ID {} já se intersectam. Pulando.").format(selected_feature.id()))
                continue
            
            # Calculate bearing for start point extension
            start_point = line_points[0]
            start_p1 = line_points[1]
            start_dx = start_point.x() - start_p1.x()
            start_dy = start_point.y() - start_p1.y()
            start_bearing = math.atan2(start_dy, start_dx)
            
            # Calculate bearing for end point extension
            end_point = line_points[-1]
            end_p0 = line_points[-2]
            end_dx = end_point.x() - end_p0.x()
            end_dy = end_point.y() - end_p0.y()
            end_bearing = math.atan2(end_dy, end_dx)
            
            # Set extension length (large value to ensure intersection)
            extension_length = 10000
            
            # Find closest intersection for start point
            start_point_inter = None
            start_dist = float('inf')
            start_target_id = None
            if not ignore_start:
                start_ext_x = start_point.x() + extension_length * math.cos(start_bearing)
                start_ext_y = start_point.y() + extension_length * math.sin(start_bearing)
                start_ext_final = QgsPointXY(start_ext_x, start_ext_y)
                start_ext_line = QgsGeometry.fromPolylineXY([start_point, start_ext_final])
                start_point_inter, start_dist, start_target_id = self.find_closest_intersection(
                    start_ext_line, start_point, start_dx, start_dy, index_target, target_layer
                )
            
            # Find closest intersection for end point
            end_point_inter = None
            end_dist = float('inf')
            end_target_id = None
            if not ignore_end:
                end_ext_x = end_point.x() + extension_length * math.cos(end_bearing)
                end_ext_y = end_point.y() + extension_length * math.sin(end_bearing)
                end_ext_final = QgsPointXY(end_ext_x, end_ext_y)
                end_ext_line = QgsGeometry.fromPolylineXY([end_point, end_ext_final])
                end_point_inter, end_dist, end_target_id = self.find_closest_intersection(
                    end_ext_line, end_point, end_dx, end_dy, index_target, target_layer
                )
            
            # Determine which endpoint to extend based on closest intersection
            if start_dist == float('inf') and end_dist == float('inf'):
                QMessageBox.warning(
                    None, self.tr("Warning", "Aviso"), 
                    self.tr(f"No available lines for interaction with feature ID {selected_feature.id()}. Skipping.", f"Nenhuma linha disponível para interação com a feição ID {selected_feature.id()}. Pulando.")
                )
                continue
            elif start_dist < end_dist:
                chosen_point = start_point_inter
                chosen_target_id = start_target_id
                is_start = True
                print(self.tr("Extending start (touches first) for feature ID {}.", "Estendendo início (toca primeiro) para feição ID {}.").format(selected_feature.id()))
            else:
                chosen_point = end_point_inter
                chosen_target_id = end_target_id
                is_start = False
                print(self.tr("Extending end (touches first) for feature ID {}.", "Estendendo fim (toca primeiro) para feição ID {}.").format(selected_feature.id()))
            
            # Check if intersection point is visible in canvas
            chosen_point_geom = QgsGeometry.fromPointXY(chosen_point)
            if not chosen_point_geom.boundingBox().intersects(canvas_extent):
                QMessageBox.warning(
                    None, self.tr("Warning", "Aviso"), 
                    self.tr(f"No visible interactions in canvas for feature ID {selected_feature.id()}. Skipping.", f"Nenhuma interação visível no canvas para feição ID {selected_feature.id()}. Pulando.")
                )
                continue
            
            # Create new line geometry with extended point
            new_line_points = list(line_points)
            if is_start:
                new_line_points.insert(0, chosen_point)
            else:
                new_line_points.append(chosen_point)
            
            # Update source feature geometry
            new_geom = (
                QgsGeometry.fromPolylineXY(new_line_points) if not geom.isMultipart() 
                else QgsGeometry.fromMultiPolylineXY([new_line_points])
            )
            source_layer.changeGeometry(selected_feature.id(), new_geom)
            
            # Add topological point to target feature if intersection occurred
            if chosen_target_id is not None:
                target_feat = target_layer.getFeature(chosen_target_id)
                target_geom = QgsGeometry(target_feat.geometry())
                new_target_geom, added = self.add_vertex_to_line(target_geom, chosen_point)
                if added:
                    target_layer.changeGeometry(chosen_target_id, new_target_geom)
                    print(self.tr("Shared vertex added to target layer for feature ID {}.", "Vértice compartilhado adicionado à camada de destino para feição ID {}.").format(selected_feature.id()))
                else:
                    print(self.tr("Failed to add vertex (already exists?) for feature ID {}.", "Falha ao adicionar vértice (já existe?) para feição ID {}.").format(selected_feature.id()))
            
            extensions_performed = True
        
        # Show completion message
        if extensions_performed:
            self.iface.messageBar().pushInfo(
                self.tr("Completed", "Concluído"), 
                self.tr("Extension complete.", "Extensão concluída.")
            )
        else:
            QMessageBox.information(None, self.tr("Completed", "Concluído"), self.tr("No extension performed.", "Nenhuma extensão realizada."))
        
        # Activate pan tool
        self.iface.actionPan().trigger()

    def find_closest_intersection(self, ext_line, extend_point, dx, dy, index_target, target_layer):
        """
        Find the closest intersection point between an extension line and target features.
        
        Args:
            ext_line (QgsGeometry): Extended line geometry for intersection testing
            extend_point (QgsPointXY): Original endpoint being extended
            dx (float): X component of extension direction vector
            dy (float): Y component of extension direction vector
            index_target (QgsSpatialIndex): Spatial index of target layer features
            target_layer (QgsVectorLayer): Target layer containing features to intersect
            
        Returns:
            tuple: (closest_point, closest_distance, target_feature_id)
                - closest_point (QgsPointXY): Coordinates of closest intersection
                - closest_distance (float): Distance to closest intersection
                - target_feature_id (int): ID of target feature containing intersection
        """
        closest_dist = float('inf')
        closest_point = None
        target_id = None
        
        # Get candidate features that intersect with extension line bounding box
        candidates = index_target.intersects(ext_line.boundingBox())
        
        for fid in candidates:
            feat = target_layer.getFeature(fid)
            intersect_geom = ext_line.intersection(feat.geometry())
            
            # Process intersection if it exists and is a point geometry
            if not intersect_geom.isEmpty() and intersect_geom.type() == QgsWkbTypes.PointGeometry:
                # Handle both single and multi-point intersections
                points = (
                    intersect_geom.asMultiPoint() if intersect_geom.isMultipart() 
                    else [intersect_geom.asPoint()]
                )
                
                for ip in points:
                    ip_xy = QgsPointXY(ip.x(), ip.y())
                    
                    # Check if intersection is in the correct direction
                    vec_x = ip_xy.x() - extend_point.x()
                    vec_y = ip_xy.y() - extend_point.y()
                    dot = vec_x * dx + vec_y * dy
                    
                    # Only consider intersections in the extension direction
                    if dot > 0:
                        dist = extend_point.distance(ip_xy)
                        if 0 < dist < closest_dist:
                            closest_dist = dist
                            closest_point = ip_xy
                            target_id = fid
        
        return closest_point, closest_dist, target_id

    def add_vertex_to_line(self, geometry, point_to_add):
        """
        Adiciona um vértice a uma geometria de linha no ponto mais próximo.
        
        Args:
            geometry (QgsGeometry): Geometria da linha onde o vértice será adicionado
            point_to_add (QgsPointXY): Ponto a ser adicionado como vértice
            
        Returns:
            QgsGeometry: Nova geometria com o vértice adicionado
            bool: True se o ponto foi adicionado, False caso contrário
        """
        if geometry.isMultipart():
            lines = geometry.asMultiPolyline()
        else:
            lines = [geometry.asPolyline()]
        
        # Supondo que a geometria é uma linha simples (não multipart para simplificar)
        # Se precisar de multipart, itere sobre todas as lines e aplique a lógica
        line = lines[0]  # Pegamos a primeira linha (ajuste se precisar suportar multipart)
        new_line = []
        point_added = False
        
        # Converter o ponto a ser adicionado para QgsPointXY (já é, mas confirmando)
        new_point = QgsPointXY(point_to_add.x(), point_to_add.y())
        
        # Iterar pelos segmentos da linha
        for i in range(len(line) - 1):
            start = line[i]
            end = line[i + 1]
            
            # Criar uma geometria de segmento
            segment = QgsGeometry.fromPolylineXY([start, end])
            
            # Verificar se o ponto está próximo do segmento (distância < tolerância)
            if segment.distance(QgsGeometry.fromPointXY(point_to_add)) < 1e-8:  # Tolerância pequena
                # Adicionar os pontos do segmento e o novo ponto
                new_line.append(start)
                new_line.append(new_point)
                point_added = True
            else:
                new_line.append(start)
        
        # Adicionar o último ponto
        new_line.append(line[-1])
        
        # Criar nova geometria
        new_geometry = (
            QgsGeometry.fromMultiPolylineXY([new_line]) if geometry.isMultipart()
            else QgsGeometry.fromPolylineXY(new_line)
        )
        
        return new_geometry, point_added

    def unload(self):
        """
        Clean up resources when the tool is unloaded.
        
        This method is called when the plugin is disabled or QGIS is closed.
        Currently no cleanup is required for this tool.
        """
        pass
