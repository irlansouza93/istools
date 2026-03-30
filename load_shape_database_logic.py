# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Carregar Banco Shape (Lógica)
                                 A QGIS plugin
 Carrega shapefiles de uma pasta e organiza no projeto QGIS
                               -------------------
        begin                : 2026-03-26
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
from dataclasses import dataclass, field

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
    QgsMessageLog,
    Qgis,
)


# ---------------------------------------------------------------------------
#  Estrutura de Resultado
# ---------------------------------------------------------------------------

@dataclass
class LoadResult:
    """Resultado da operação de carga de shapefiles."""
    folder_name: str = ""
    total_found: int = 0
    total_loaded: int = 0
    total_invalid: int = 0
    points: int = 0
    lines: int = 0
    polygons: int = 0
    others: int = 0
    stopped_by_error: bool = False
    errors: list = field(default_factory=list)


# ---------------------------------------------------------------------------
#  Descoberta de Shapefiles
# ---------------------------------------------------------------------------

def discover_shapefiles(folder: str, recursive: bool = False) -> list[str]:
    """
    Localiza todos os arquivos .shp dentro de uma pasta.

    Args:
        folder: Caminho da pasta raiz.
        recursive: Se True, busca em subpastas recursivamente.

    Returns:
        Lista de caminhos absolutos ordenados alfabeticamente.
    """
    shp_files = []
    if recursive:
        for root, _dirs, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(".shp"):
                    shp_files.append(os.path.join(root, f))
    else:
        for f in os.listdir(folder):
            if f.lower().endswith(".shp"):
                shp_files.append(os.path.join(folder, f))

    shp_files.sort(key=lambda p: os.path.basename(p).lower())
    return shp_files


# ---------------------------------------------------------------------------
#  Classificação Geométrica
# ---------------------------------------------------------------------------

_GEOM_GROUPS = {
    QgsWkbTypes.PointGeometry:   "Points",
    QgsWkbTypes.LineGeometry:    "Lines",
    QgsWkbTypes.PolygonGeometry: "Polygons",
}


def classify_layer(layer: QgsVectorLayer) -> str:
    """Retorna o grupo geométrico da camada ('Points', 'Lines', 'Polygons' ou 'Others')."""
    return _GEOM_GROUPS.get(layer.geometryType(), "Others")


# ---------------------------------------------------------------------------
#  Resolução de Nome de Grupo
# ---------------------------------------------------------------------------

def _resolve_group_name(root, base_name: str, recreate: bool) -> "QgsLayerTreeGroup":
    """
    Cria ou recria um grupo na árvore de camadas.

    Se `recreate` for True e o grupo existir, remove-o antes de criar novo.
    Se `recreate` for False e o grupo existir, cria com sufixo (2), (3)...
    """
    existing = root.findGroup(base_name)

    if existing:
        if recreate:
            root.removeChildNode(existing)
            return root.addGroup(base_name)
        else:
            # Encontrar sufixo disponível
            counter = 2
            while root.findGroup(f"{base_name} ({counter})"):
                counter += 1
            return root.addGroup(f"{base_name} ({counter})")
    else:
        return root.addGroup(base_name)


# ---------------------------------------------------------------------------
#  Motor Principal de Carga
# ---------------------------------------------------------------------------

def load_shapefiles_to_project(
    folder: str,
    recursive: bool = False,
    ignore_invalid: bool = True,
    recreate_group: bool = False,
    progress_callback=None
) -> LoadResult:
    """
    Carrega shapefiles de uma pasta e organiza no projeto QGIS.

    Cria um grupo principal com o nome da pasta e subgrupos por
    tipo geométrico (Points, Lines, Polygons).

    Args:
        folder: Caminho da pasta com shapefiles.
        recursive: Se True, busca em subpastas.
        ignore_invalid: Se True, ignora camadas inválidas silenciosamente.
        recreate_group: Se True, apaga grupo existente com mesmo nome.
        progress_callback: Callable(current, total) para progresso.

    Returns:
        LoadResult com estatísticas da operação.
    """
    result = LoadResult()
    result.folder_name = os.path.basename(folder.rstrip("/\\"))

    # 1. Descoberta
    shp_files = discover_shapefiles(folder, recursive)
    result.total_found = len(shp_files)

    if not shp_files:
        return result

    # 2. Validação e Classificação
    classified = {
        "Points": [],
        "Lines": [],
        "Polygons": [],
        "Others": [],
    }

    valid_layers = []
    for i, shp_path in enumerate(shp_files):
        if progress_callback:
            progress_callback(i, len(shp_files))

        layer_name = os.path.splitext(os.path.basename(shp_path))[0]
        layer = QgsVectorLayer(shp_path, layer_name, "ogr")

        if not layer.isValid():
            result.total_invalid += 1
            msg = f"Camada inválida: {os.path.basename(shp_path)}"
            result.errors.append(msg)
            QgsMessageLog.logMessage(msg, "ISTools", Qgis.Warning)
            if not ignore_invalid:
                # Interrompe o processo se o usuário não quiser ignorar erros
                result.stopped_by_error = True
                break
            else:
                continue

        group_name = classify_layer(layer)
        classified[group_name].append(layer)
        valid_layers.append(layer)

    # 3. Contagem
    result.points = len(classified["Points"])
    result.lines = len(classified["Lines"])
    result.polygons = len(classified["Polygons"])
    result.others = len(classified["Others"])
    result.total_loaded = len(valid_layers)

    if not valid_layers:
        return result

    # 4. Criação da Árvore de Camadas
    project = QgsProject.instance()
    root = project.layerTreeRoot()

    main_group = _resolve_group_name(root, result.folder_name, recreate_group)
    # Atualiza o nome no resultado com o nome real do grupo (pode ter ganho sufixo)
    result.folder_name = main_group.name()

    # Criar subgrupos somente se houver camadas daquele tipo
    subgroups = {}
    # Manter ordem consistente: Points, Lines, Polygons, Others
    for gname in ["Points", "Lines", "Polygons", "Others"]:
        if classified[gname]:
            subgroups[gname] = main_group.addGroup(gname)

    # 5. Inserção das Camadas
    for gname, layers_list in classified.items():
        if not layers_list:
            continue
        target_group = subgroups[gname]
        for layer in sorted(layers_list, key=lambda l: l.name().lower()):
            project.addMapLayer(layer, False)
            target_group.addLayer(layer)

    if progress_callback:
        progress_callback(len(shp_files), len(shp_files))

    QgsMessageLog.logMessage(
        f"Carregar Banco Shape: {result.total_loaded} camadas carregadas "
        f"de '{result.folder_name}' (P:{result.points} L:{result.lines} "
        f"A:{result.polygons} O:{result.others})",
        "ISTools", Qgis.Info
    )

    return result
