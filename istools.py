# -*- coding: utf-8 -*-
"""
/***************************************************************************
 ISTools - Main Plugin Class
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
from qgis.PyQt.QtCore import QCoreApplication, QSettings, QTranslator, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu
from qgis.core import QgsApplication, QgsProcessingRegistry
from .extend_lines import ExtendLines
from .polygon_generator import QgisPolygonGenerator
from .bounded_polygon_generator import BoundedPolygonGenerator
from .point_on_surface_generator import PointOnSurfaceGenerator
from .intersection_line import IntersectionLineTool
from .smooth_simplifier import SmoothSimplifier
from .translations.translate import translate
from .processing.provider import ISToolsProvider


class ISTools:
    """
    Main plugin class for ISTools - Professional vectorization toolkit for QGIS.
    
    This class manages the initialization, GUI setup, and cleanup of all ISTools
    components including extend lines, polygon generators, and point generators.
    """
    
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
        Initialize the ISTools plugin.
        
        Args:
            iface: QGIS interface object
        """
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.translator = None  # Initialize translator attribute
        
        # In v1.4.1 we didn't import resources.py, which protected against pyrcc5 compilation bugs.
        # We rely strictly on the file system paths exactly like 1.4.1 did.
        
        # Create ISTools top-level menu
        self.menu = QMenu(self.tr("ISTools", "ISTools"))
        
        # Helper for icons
        def get_icon(path):
            return QIcon(f":/plugins/istools/icons/{path}")
            
        # Create ISTools submenus
        self.vector_tools_menu = QMenu(self.tr("Ferramentas de Vetorização", "Ferramentas de Vetorização"))
        self.vector_tools_menu.setIcon(get_icon("ferramentas_de_vetorizacao.png"))
        
        self.processing_tools_menu = QMenu(self.tr("Ferramentas de Processamento", "Ferramentas de Processamento"))
        self.processing_tools_menu.setIcon(get_icon("ferramentas_de_geoprocessamento.png"))

        self.db_tools_menu = QMenu(self.tr("Ferramentas de Banco de Dados", "Ferramentas de Banco de Dados"))
        self.db_tools_menu.setIcon(QIcon(":/plugins/istools/icons/icon_db_tools_menu.png"))

        self.external_tools_menu = QMenu(self.tr("External Tools", "Ferramentas Externas"))
        self.external_tools_menu.setIcon(
            QIcon(os.path.join(self.plugin_dir, "icons", "icon_tifftools.png"))
        )
        
        self.menu.addMenu(self.vector_tools_menu)
        self.menu.addMenu(self.processing_tools_menu)
        self.menu.addSeparator()
        self.menu.addMenu(self.db_tools_menu)
        self.menu.addSeparator()
        self.menu.addMenu(self.external_tools_menu)
        
        # Create ISTools toolbar
        self.toolbar = self.iface.addToolBar("ISTools")
        self.toolbar.setObjectName("ISToolsToolbar")
        
        self.actions = []
        
        # Initialize tool instances
        self.extend_lines = None
        self.polygon_generator = None
        self.bounded_polygon_generator = None
        self.point_on_surface_generator = None
        self.intersection_line_tool = None
        self.smooth_simplifier = None
        self.provider = None

    def _initialize_translation(self):
        """
        Inicializa sistema de tradução com pt_BR como idioma padrão.
        Prioriza português brasileiro para melhor experiência do usuário.
        """
        # Detecção inteligente de locale com prioridade para pt_BR
        system_locale = QSettings().value('locale/userLocale', '')
        
        # Se o sistema estiver em qualquer variante de português, força pt_BR
        if system_locale.startswith('pt'):
            locale = 'pt_BR'
        else:
            # Para outros idiomas, usa detecção normal mas com pt_BR como fallback
            locale = system_locale[:2] if system_locale and len(system_locale) >= 2 else 'pt_BR'
        
        # Lista de prioridade de idiomas para tentar
        locales_to_try = [locale, 'pt_BR', 'pt', 'en']
        # Remove duplicatas mantendo ordem
        locales_to_try = list(dict.fromkeys(locales_to_try))
        
        for try_locale in locales_to_try:
            locale_path = os.path.join(self.plugin_dir, 'i18n', f'istools_{try_locale}.qm')
            
            if os.path.exists(locale_path):
                self.translator = QTranslator()
                if self.translator.load(locale_path):
                    if QCoreApplication.installTranslator(self.translator):
                        print(f"Tradução {try_locale} carregada com sucesso!")
                        return
                    else:
                        print(f"Falha ao instalar tradutor para {try_locale}")
                else:
                    print(f"Falha ao carregar: {locale_path}")
        
        print("Nenhuma tradução pôde ser carregada")
        self.translator = None

    def initGui(self):
        """
        Initialize the plugin GUI by creating menu items and toolbar actions.
        """
        self._initialize_translation()
        
        # Setup tools
        self._setup_extend_lines_tool()
        self._setup_polygon_generator_tool()
        self._setup_bounded_polygon_generator_tool()
        self._setup_point_on_surface_generator_tool()
        self._setup_intersection_line_tool()
        self._setup_smooth_simplifier_tool()
        self._setup_processing_tools()
        self._setup_load_shape_database_tool()
        self._setup_server_config_tool()
        self._setup_database_manager_tool()
        self._setup_edgv300_etl_tool()
        self._setup_external_tools()

        # Add top-level menu to QGIS
        menu_bar = self.iface.mainWindow().menuBar()
        # Inserir antes do menu Ajuda (Geralmente o último)
        help_menu = self.iface.helpMenu().menuAction()
        menu_bar.insertMenu(help_menu, self.menu)

        # Initialize and register processing provider
        self.provider = ISToolsProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def get_icon(self, path):
        """
        Retorna um QIcon de forma híbrida (recurso ou arquivo direto).
        """
        # Limpa o caminho de ícones para pegar apenas o nome do arquivo se necessário
        filename = os.path.basename(path)
        return QIcon(f":/plugins/istools/icons/{filename}")

    def _setup_extend_lines_tool(self):
        """
        Setup the Extend Lines tool with its action, icon, and menu entry.
        """
        self.extend_lines = ExtendLines(self.iface)
        
        extend_action = QAction(
            self.get_icon("icon_extend_lines.png"),
            self.tr("Extend Lines", "Estender Linhas"),
            self.iface.mainWindow()
        )
        extend_action.setToolTip(self.tr("Extends loose lines until they touch other lines", "Estende linhas soltas até tocarem outras linhas"))
        extend_action.triggered.connect(self.extend_lines.run)
        
        self._add_action_to_interface(extend_action, target_menu=self.vector_tools_menu)

    def _setup_polygon_generator_tool(self):
        """
        Setup the Polygon Generator tool with its action, icon, and menu entry.
        """
        self.polygon_generator = QgisPolygonGenerator(self.iface)
        
        polygon_action = QAction(
            self.get_icon("icon_polygon_generator.png"),
            self.tr("Polygon Generator", "Gerador de Polígonos"),
            self.iface.mainWindow()
        )
        polygon_action.setToolTip(self.tr("Generates polygons from lines or areas around a point", "Gera polígonos a partir de linhas ou áreas ao redor de um ponto"))
        polygon_action.triggered.connect(self.polygon_generator.activate_tool)
        
        self._add_action_to_interface(polygon_action, target_menu=self.vector_tools_menu)

    def _setup_bounded_polygon_generator_tool(self):
        """
        Setup the Bounded Polygon Generator tool with its action, icon, and menu entry.
        """
        self.bounded_polygon_generator = BoundedPolygonGenerator(self.iface)
        
        bounded_polygon_action = QAction(
            self.get_icon("icon_bounded_polygon_generator.png"),
            self.tr("Bounded Polygon Generator", "Gerador de Polígonos Limitados"),
            self.iface.mainWindow()
        )
        bounded_polygon_action.setToolTip(
            self.tr("Generates bounded polygons from a frame and line or polygon layers", "Gera polígonos limitados a partir de um quadro e camadas de linhas ou polígonos")
        )
        bounded_polygon_action.triggered.connect(
            self.bounded_polygon_generator.activate_tool
        )
        
        self._add_action_to_interface(bounded_polygon_action, target_menu=self.vector_tools_menu)

    def _setup_point_on_surface_generator_tool(self):
        """
        Setup the Point on Surface Generator tool with its action, icon, and menu entry.
        """
        self.point_on_surface_generator = PointOnSurfaceGenerator(self.iface)
        
        point_action = QAction(
            self.get_icon("icon_point_on_surface_generator.png"),
            self.tr("Point on Surface Generator", "Gerador de Pontos na Superfície"),
            self.iface.mainWindow()
        )
        point_action.setToolTip(self.tr("Generates points inside selected polygons", "Gera pontos dentro de polígonos selecionados"))
        point_action.triggered.connect(self.point_on_surface_generator.run)
        
        self._add_action_to_interface(point_action, target_menu=self.vector_tools_menu)

    def _setup_intersection_line_tool(self):
        """
        Setup the Intersection Line tool with its action, icon, and menu entry.
        """
        self.intersection_line_tool = IntersectionLineTool(self.iface)
        
        intersection_action = QAction(
            self.get_icon("icon_intersection_line.png"),
            self.tr("Intersection Line", "Interseção de Linhas"),
            self.iface.mainWindow()
        )
        intersection_action.setToolTip(self.tr("Insert shared vertices at line intersections within a selected area", "Insere vértices compartilhados nas interseções de linhas dentro de uma área selecionada"))
        intersection_action.triggered.connect(self.intersection_line_tool.activate)
        
        self._add_action_to_interface(intersection_action, target_menu=self.vector_tools_menu)

    def _setup_smooth_simplifier_tool(self):
        """Configura a simplificação suave de linhas selecionadas."""
        self.smooth_simplifier = SmoothSimplifier(self.iface)

        simplifier_action = QAction(
            QIcon(os.path.join(self.plugin_dir, "icons", "icon_smooth_simplifier.png")),
            self.tr("Smooth Simplifier", "Simplificador Suave"),
            self.iface.mainWindow()
        )
        simplifier_action.setToolTip(self.tr(
            "Simplifies selected lines with a fine, undoable tolerance",
            "Simplifica linhas selecionadas com tolerância fina e reversível"
        ))
        simplifier_action.triggered.connect(self.smooth_simplifier.run)

        self._add_action_to_interface(simplifier_action, target_menu=self.vector_tools_menu)

    def _setup_processing_tools(self):
        """Setup processing tools menu items."""
        icon_path = os.path.join(self.plugin_dir, "icons", "recortar_por_moldura.png")
        action = QAction(
            QIcon(icon_path),
            self.tr("Recortar por Moldura", "Recortar por Moldura (Multicamadas)"),
            self.iface.mainWindow()
        )
        action.setToolTip(self.tr("Filtra e recorta múltiplas camadas alvo usando uma moldura", "Filtra e recorta múltiplas camadas alvo usando uma moldura"))
        action.triggered.connect(self.show_clip_to_frame_dialog)
        
        self.actions.append(action)
        self.processing_tools_menu.addAction(action)

    def show_clip_to_frame_dialog(self):
        """Displays the Clip by Frame dialog."""
        from .gui.processing_tools import ClipToFrameDialog
        dlg = ClipToFrameDialog(self.iface)
        dlg.exec_()

    def _setup_load_shape_database_tool(self):
        """Setup para o botão de carregar banco shape."""
        action = QAction(
            self.get_icon("carregar_banco_shape.png"),
            self.tr("Carregar Banco Shape", "Carregar Banco Shape"),
            self.iface.mainWindow()
        )
        action.setToolTip(self.tr(
            "Carrega shapefiles de uma pasta e organiza no projeto atual",
            "Carrega shapefiles de uma pasta e organiza no projeto atual"
        ))
        action.triggered.connect(self.show_load_shape_database)

        self.actions.append(action)
        self.db_tools_menu.addAction(action)

    def show_load_shape_database(self):
        """
        Exibe o diálogo de Carregar Banco Shape.
        """
        from .gui.load_shape_database import LoadShapeDatabaseDialog
        dlg = LoadShapeDatabaseDialog(self.iface)
        dlg.exec_()

    def _setup_server_config_tool(self):
        """Configuração de servidores PostGIS."""
        action = QAction(
            self.get_icon("icon_server_config.png"),
            self.tr("Configurar Servidores", "Configurar Servidores"),
            self.iface.mainWindow()
        )
        action.setToolTip(self.tr("Gerenciar conexões com servidores PostGIS", "Gerenciar conexões com servidores PostGIS"))
        action.triggered.connect(self.show_server_config)
        
        self.actions.append(action)
        self.db_tools_menu.addAction(action)

    def _setup_database_manager_tool(self):
        """Gerenciamento de banco (Merge/Reset)."""
        action = QAction(
            self.get_icon("icon_db_manager.png"),
            self.tr("Gerenciador de Banco de Dados", "Gerenciador de Banco de Dados"),
            self.iface.mainWindow()
        )
        action.setToolTip(self.tr("Resetar, Backup, Restaurar e Criar bancos PostGIS", "Resetar, Backup, Restaurar e Criar bancos PostGIS"))
        action.triggered.connect(self.show_database_manager)
        
        self.actions.append(action)
        self.db_tools_menu.addAction(action)

    def show_database_manager(self):
        """
        Exibe o diálogo do Gerenciador de Banco de Dados.
        """
        from .gui.database_manager import DatabaseManagerDialog
        dlg = DatabaseManagerDialog(self.iface)
        dlg.exec_()

    def show_server_config(self):
        """
        Exibe o diálogo de configuração de servidores.
        """
        from .gui.server_config import ServerConfigDialog
        dlg = ServerConfigDialog(self.iface.mainWindow())
        dlg.exec_()

    def _setup_edgv300_etl_tool(self):
        """ETL EDGV 3.0."""
        action = QAction(
            self.get_icon("icon_etl_edgv300.png"),
            self.tr("Conversor SHP -> PostGIS (EDGV 3.0 v1.1.6)", "Conversor SHP -> PostGIS (EDGV 3.0 v1.1.6)"),
            self.iface.mainWindow()
        )
        action.setToolTip(self.tr("Importação inteligente de Shapefiles para o padrão EDGV 3.0", "Importação inteligente de Shapefiles para o padrão EDGV 3.0"))
        action.triggered.connect(self.show_edgv300_etl)
        
        self.actions.append(action)
        self.db_tools_menu.addAction(action)

    def show_edgv300_etl(self):
        """
        Executa o algoritmo de ETL EDGV 3.0 via caixa de diálogo do Processing.
        """
        import processing
        processing.execAlgorithmDialog("istools:shp_to_postgis_edgv300")

    def _setup_external_tools(self):
        """Adiciona atalhos para aplicativos distribuídos fora do plugin."""
        action = QAction(
            QIcon(os.path.join(self.plugin_dir, "icons", "icon_tifftools.png")),
            self.tr(
                "TiffTools Pro — download and user guide",
                "TiffTools Pro — baixar e consultar manual",
            ),
            self.iface.mainWindow(),
        )
        action.setToolTip(self.tr(
            "Opens the official page for the standalone TIFF compression and reprojection application",
            "Abre a página oficial do aplicativo externo para compressão e reprojeção de TIFF",
        ))
        action.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(
                "https://irlansouza93.github.io/istools-website/tifftools/"
            ))
        )

        self.actions.append(action)
        self.external_tools_menu.addAction(action)

    def _add_action_to_interface(self, action, target_menu=None):
        """
        Add an action to the plugin menu and toolbar.
        
        Args:
            action: QAction object to be added to the interface
            target_menu: Optional QMenu to add the action to. If None, adds to self.menu.
        """
        self.actions.append(action)
        if target_menu:
            target_menu.addAction(action)
        else:
            self.menu.addAction(action)
        self.toolbar.addAction(action)

    def unload(self):
        """
        Clean up the plugin by removing all actions and unloading tools.
        
        This method is called when the plugin is unloaded and ensures
        proper cleanup of all GUI elements and tool instances.
        """
        # Unregister processing provider
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

        # Remove actions from toolbar and menu
        for action in self.actions:
            self.iface.removeToolBarIcon(action)
            self.toolbar.removeAction(action)
            self.menu.removeAction(action)
            
        # Remove ISTools menu from menu bar
        menu_bar = self.iface.mainWindow().menuBar()
        menu_bar.removeAction(self.menu.menuAction())
        
        # Remove ISTools toolbar
        if self.toolbar:
            del self.toolbar
            self.toolbar = None
            
        # Unload all tools
        self._unload_tools()
        
        # Remove translator if it exists
        if hasattr(self, 'translator'):
            QCoreApplication.removeTranslator(self.translator)
        
        # Clear actions list
        self.actions = []

    def _unload_tools(self):
        """
        Unload all individual tools and clean up their resources.
        """
        if self.extend_lines:
            self.extend_lines.unload()
            self.extend_lines = None
            
        if self.polygon_generator:
            self.polygon_generator.unload()
            self.polygon_generator = None
            
        if self.bounded_polygon_generator:
            self.bounded_polygon_generator.unload()
            self.bounded_polygon_generator = None
            
        if self.point_on_surface_generator:
            self.point_on_surface_generator.unload()
            self.point_on_surface_generator = None
            
        if self.intersection_line_tool:
            self.intersection_line_tool.deactivate()
            self.intersection_line_tool = None

        if self.smooth_simplifier:
            self.smooth_simplifier.unload()
            self.smooth_simplifier = None
