# -*- coding: utf-8 -*-
# ISTools Plugin Initialization

def classFactory(iface):
    from . import resources
    from .istools import ISTools
    return ISTools(iface)
