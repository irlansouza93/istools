# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QProgressDialog, QCheckBox, QListWidget,
    QListWidgetItem, QTextEdit
)
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    Qgis,
    QgsProject,
    QgsMapLayer,
    QgsWkbTypes
)
from qgis.gui import QgsMapLayerComboBox
from ..clip_by_frame_logic import ClipByFrameLogic

class ClipToFrameDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("Filtrar/Recortar feições pela moldura")
        self.setMinimumWidth(720)
        self.setMinimumHeight(680)

        layout = QVBoxLayout(self)

        lbl_info = QLabel(
            "Selecione a camada de moldura (poligonal) e marque uma ou mais camadas alvo.\n"
            "As alterações ficarão somente em edição para auditoria."
        )
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Camada moldura:"))
        self.cmb_mask = QgsMapLayerComboBox()
        self.cmb_mask.setFilters(Qgis.LayerFilter.VectorLayer)
        row1.addWidget(self.cmb_mask)
        layout.addLayout(row1)

        layout.addWidget(QLabel("Camadas alvo:"))
        self.lst_targets = QListWidget()
        self.lst_targets.setSelectionMode(QListWidget.NoSelection)
        layout.addWidget(self.lst_targets)

        row_buttons = QHBoxLayout()
        self.btn_select_all = QPushButton("Marcar todas")
        self.btn_unselect_all = QPushButton("Desmarcar todas")
        self.btn_refresh = QPushButton("Atualizar lista")
        row_buttons.addWidget(self.btn_select_all)
        row_buttons.addWidget(self.btn_unselect_all)
        row_buttons.addWidget(self.btn_refresh)
        layout.addLayout(row_buttons)

        self.chk_use_selected_mask = QCheckBox("Usar apenas feições selecionadas da moldura (quando houver)")
        self.chk_use_selected_mask.setChecked(True)
        layout.addWidget(self.chk_use_selected_mask)

        self.chk_only_selected_targets = QCheckBox("Processar apenas feições selecionadas nas camadas alvo (quando houver)")
        self.chk_only_selected_targets.setChecked(False)
        layout.addWidget(self.chk_only_selected_targets)

        self.chk_make_valid = QCheckBox("Corrigir geometrias inválidas automaticamente quando necessário")
        self.chk_make_valid.setChecked(True)
        layout.addWidget(self.chk_make_valid)

        self.chk_select_problematic = QCheckBox("Selecionar feições problemáticas na camada alvo ao final")
        self.chk_select_problematic.setChecked(True)
        layout.addWidget(self.chk_select_problematic)

        self.chk_skip_mask_layer = QCheckBox("Ignorar automaticamente a própria camada de moldura nas camadas alvo")
        self.chk_skip_mask_layer.setChecked(True)
        layout.addWidget(self.chk_skip_mask_layer)

        layout.addWidget(QLabel("Resumo da execução:"))
        self.txt_summary = QTextEdit()
        self.txt_summary.setReadOnly(True)
        self.txt_summary.setMinimumHeight(120)
        layout.addWidget(self.txt_summary)

        btns = QHBoxLayout()
        self.btn_run = QPushButton("Executar")
        self.btn_cancel = QPushButton("Cancelar")
        btns.addWidget(self.btn_run)
        btns.addWidget(self.btn_cancel)
        layout.addLayout(btns)

        self.btn_run.clicked.connect(self.run)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_select_all.clicked.connect(self.select_all_targets)
        self.btn_unselect_all.clicked.connect(self.unselect_all_targets)
        self.btn_refresh.clicked.connect(self.populate_target_layers)
        self.cmb_mask.layerChanged.connect(self.populate_target_layers)
        self.chk_skip_mask_layer.stateChanged.connect(self.populate_target_layers)

        self.populate_target_layers()

    def populate_target_layers(self):
        self.lst_targets.clear()
        mask_layer = self.cmb_mask.currentLayer()
        skip_mask = self.chk_skip_mask_layer.isChecked()

        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsMapLayer.VectorLayer:
                if skip_mask and mask_layer and layer.id() == mask_layer.id(): continue
                
                item = QListWidgetItem(layer.name())
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                item.setData(Qt.UserRole, layer.id())
                geom_type = QgsWkbTypes.displayString(layer.wkbType())
                item.setToolTip(f"{layer.name()} ({geom_type})")
                self.lst_targets.addItem(item)

    def select_all_targets(self):
        for i in range(self.lst_targets.count()):
            self.lst_targets.item(i).setCheckState(Qt.Checked)

    def unselect_all_targets(self):
        for i in range(self.lst_targets.count()):
            self.lst_targets.item(i).setCheckState(Qt.Unchecked)

    def run(self):
        mask_layer = self.cmb_mask.currentLayer()
        if not mask_layer or QgsWkbTypes.geometryType(mask_layer.wkbType()) != Qgis.GeometryType.Polygon:
            QMessageBox.warning(self, "Aviso", "Selecione uma camada de moldura poligonal.")
            return

        selected_layers = []
        for i in range(self.lst_targets.count()):
            item = self.lst_targets.item(i)
            if item.checkState() == Qt.Checked:
                layer = QgsProject.instance().mapLayer(item.data(Qt.UserRole))
                if layer: selected_layers.append(layer)

        if not selected_layers:
            QMessageBox.warning(self, "Aviso", "Marque pelo menos uma camada alvo.")
            return

        self.txt_summary.clear()
        
        for target_layer in selected_layers:
            try:
                res = ClipByFrameLogic.process_target_layer(
                    mask_layer,
                    target_layer,
                    use_selected_mask=self.chk_use_selected_mask.isChecked(),
                    auto_make_valid=self.chk_make_valid.isChecked(),
                    only_selected_targets=self.chk_only_selected_targets.isChecked()
                )
                
                resumo = (
                    f"[OK] {target_layer.name()}\n"
                    f"  Mantidas: {res['inside']}\n"
                    f"  Removidas: {res['removed']}\n"
                    f"  Recortadas: {res['changed']}\n"
                    f"  Divididas: {res['split']}\n"
                    f"  Limpas (área zero): {res['cleaned']}\n"
                )
                self.txt_summary.append(resumo)
                
                if self.chk_select_problematic.isChecked():
                    prob = ClipByFrameLogic.collect_problematic_features(target_layer)
                    if prob: target_layer.selectByIds(prob)
                    
            except Exception as e:
                self.txt_summary.append(f"[ERRO] {target_layer.name()}: {str(e)}\n")

        QMessageBox.information(self, "Concluído", "Processamento finalizado no buffer de edição.")
        self.accept()
