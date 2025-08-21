import os
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu
from .extend_lines import ExtendLines
from .polygon_generator import QgisPolygonGenerator

class ISTools:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.menu = QMenu("ISTools", self.iface.mainWindow().menuBar())
        self.actions = []

    def initGui(self):
        # Inicializa ExtendLines
        self.extend_lines = ExtendLines(self.iface)
        extend_icon_path = os.path.join(self.plugin_dir, "icon_extend_lines.png")
        extend_action = QAction(
            QIcon(extend_icon_path),
            "Extend Lines",
            self.iface.mainWindow()
        )
        extend_action.setToolTip("Estende linhas soltas até tocar outras linhas")
        extend_action.triggered.connect(self.extend_lines.run)
        self.actions.append(extend_action)
        self.menu.addAction(extend_action)
        self.iface.addToolBarIcon(extend_action)

        # Inicializa QgisPolygonGenerator
        self.polygon_generator = QgisPolygonGenerator(self.iface)
        polygon_icon_path = os.path.join(self.plugin_dir, "icon_polygon_generator.png")
        polygon_action = QAction(
            QIcon(polygon_icon_path),
            "Polygon Generator",
            self.iface.mainWindow()
        )
        polygon_action.setToolTip("Gera polígonos a partir de linhas ou áreas ao redor de um ponto")
        polygon_action.triggered.connect(self.polygon_generator.activate_tool)
        self.actions.append(polygon_action)
        self.menu.addAction(polygon_action)
        self.iface.addToolBarIcon(polygon_action)

        # Adiciona o menu ISTools ao menu Plugins do QGIS
        plugin_menu = self.iface.pluginMenu()
        plugin_menu.addMenu(self.menu)

    def unload(self):
        # Remove as ações da toolbar e do menu
        for action in self.actions:
            self.iface.removeToolBarIcon(action)
            self.menu.removeAction(action)
        # Remove o menu ISTools do menu Plugins
        plugin_menu = self.iface.pluginMenu()
        if self.menu.menuAction() in plugin_menu.actions():
            plugin_menu.removeAction(self.menu.menuAction())
        # Descarrega as ferramentas
        self.extend_lines.unload()
        self.polygon_generator.unload()
        # Limpa a lista de ações
        self.actions = []