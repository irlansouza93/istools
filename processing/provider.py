# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Processing Provider
                                 A QGIS plugin
 Professional vectorization toolkit for QGIS
                              -------------------
        begin                : 2026-03-20
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

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon
import os

from .edgv_etl_topo_algorithm import EDGVETLTopoAlgorithm
from .shp_to_postgis_algorithm import ShpToPostGISAlgorithm
from .postgis_to_shp_algorithm import PostGISToShpAlgorithm
from .clip_by_frame_algorithm import ClipByFrameAlgorithm


from .edgv_300_shp_to_postgis_algorithm import EDGV300ShpToPostgisAlgorithm


class ISToolsProvider(QgsProcessingProvider):

    def __init__(self):
        """
        Initialize the provider.
        """
        super().__init__()

    def loadAlgorithms(self):
        """
        Load algorithms into the provider.
        """
        self.addAlgorithm(ShpToPostGISAlgorithm())
        self.addAlgorithm(PostGISToShpAlgorithm())
        self.addAlgorithm(ClipByFrameAlgorithm())
        self.addAlgorithm(EDGVETLTopoAlgorithm())
        self.addAlgorithm(EDGV300ShpToPostgisAlgorithm())

    def id(self):
        """
        Returns the unique provider id.
        """
        return 'istools'

    def name(self):
        """
        Returns the provider name.
        """
        return 'ISTools'

    def icon(self):
        """
        Retorna o ícone do provedor.
        """
        return QIcon(':/plugins/istools/icons/icon_istools.png')

    def longName(self):
        """
        Returns the provider long name.
        """
        return self.name()
