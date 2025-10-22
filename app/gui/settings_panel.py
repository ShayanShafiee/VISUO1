# --- CORRECTED FILE: gui/settings_panel.py ---

import os
from typing import Optional
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QFormLayout, 
                             QSlider, QComboBox, QPushButton, QSpinBox, QLabel,
                             QSizePolicy, QFileDialog, QHBoxLayout, QCheckBox, 
                             QListWidget, QListWidgetItem, QLineEdit, QColorDialog,
                             QToolButton, QFrame, QInputDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QSize, QTimer
from PyQt6.QtGui import QColor, QIcon

class SettingsPanel(QWidget):
    settingsChanged = pyqtSignal()
    startProcessing = pyqtSignal()
    pauseRequested = pyqtSignal()
    resumeRequested = pyqtSignal()
    abortRequested = pyqtSignal()
    stopRequested = pyqtSignal()
    templatePathChanged = pyqtSignal(str)
    roiChangedFromSpinners = pyqtSignal(QRect)
    # Multi-ROI management
    addRectangleRoiRequested = pyqtSignal()
    renameRoiRequested = pyqtSignal(int, str)
    removeRoiRequested = pyqtSignal(int)
    toggleRoiVisibilityRequested = pyqtSignal(int, bool)
    changeRoiColorRequested = pyqtSignal(int, object)  # QColor
    selectedRoiChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.template_path = None
        # Store verbose logging state (moved to Settings menu)
        self._verbose_logging_enabled = False
        # Debounce timer for high-frequency controls (e.g., manual threshold)
        self._settings_debounce_timer: Optional[QTimer] = None
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # --- Overlay Settings Group ---
        overlay_group = QGroupBox("Overlay Settings")
        overlay_layout = QFormLayout(overlay_group)
        self.transparency_slider = QSlider(Qt.Orientation.Horizontal)
        self.transparency_slider.setRange(0, 100)
        self.transparency_spinbox = QSpinBox()
        self.transparency_spinbox.setRange(0, 100)
        self.transparency_spinbox.setSuffix(" %")
        transparency_layout = QHBoxLayout()
        transparency_layout.addWidget(self.transparency_slider)
        transparency_layout.addWidget(self.transparency_spinbox)
        self.transparency_slider.setValue(80)
        self.transparency_spinbox.setValue(80)
        self.transparency_slider.valueChanged.connect(self.transparency_spinbox.setValue)
        self.transparency_spinbox.valueChanged.connect(self.transparency_slider.setValue)
        self.transparency_slider.valueChanged.connect(self.settingsChanged.emit)
        overlay_layout.addRow("FL Transparency:", transparency_layout)
        self.lut_combo = QComboBox()
        colormaps = [
            'hot', 'viridis', 'inferno', 'magma', 'cividis', 'gray', 'jet',
            'tab10', 'tab20', 'tab20b', 'tab20c', 'Pastel1', 'Pastel2',
            'Paired', 'Accent', 'Dark2', 'Set1', 'Set2', 'Set3', 'flag', 'prism', 'nipy_spectral'
        ]
        self.lut_combo.addItems(sorted(colormaps))
        self.lut_combo.setCurrentText("nipy_spectral")
        self.lut_combo.currentTextChanged.connect(self.settingsChanged.emit)
        overlay_layout.addRow("LUT (Colormap):", self.lut_combo)
        main_layout.addWidget(overlay_group)
        self.overlay_group = overlay_group

        # --- Normalization Settings Group ---
        norm_group = QGroupBox("Intensity Range (Normalization)")
        norm_layout = QFormLayout(norm_group)
        self.min_intensity_spinbox = QSpinBox()
        self.min_intensity_spinbox.setRange(0, 65535)
        self.min_intensity_spinbox.setValue(100)
        self.min_intensity_spinbox.valueChanged.connect(self.settingsChanged.emit)
        norm_layout.addRow("Min Intensity:", self.min_intensity_spinbox)
        self.max_intensity_spinbox = QSpinBox()
        self.max_intensity_spinbox.setRange(0, 65535)
        self.max_intensity_spinbox.setValue(20000)
        self.max_intensity_spinbox.valueChanged.connect(self.settingsChanged.emit)
        norm_layout.addRow("Max Intensity:", self.max_intensity_spinbox)
        main_layout.addWidget(norm_group)
        self.norm_group = norm_group

        # --- Registration Settings Group ---
        reg_group = QGroupBox("Registration")
        reg_layout = QVBoxLayout(reg_group)
        self.reg_checkbox = QCheckBox("Enable Centering / Registration")
        self.reg_checkbox.setChecked(False)
        self.reg_checkbox.toggled.connect(self.toggle_registration_widgets)
        reg_layout.addWidget(self.reg_checkbox)
        self.load_template_button = QPushButton("Load Reference Template...")
        self.load_template_button.clicked.connect(self._load_template)
        self.template_label = QLabel("No template loaded.")
        self.template_label.setWordWrap(True)
        reg_layout.addWidget(self.load_template_button)
        reg_layout.addWidget(self.template_label)
        main_layout.addWidget(reg_group)
        self.reg_group = reg_group

        # --- Timestamp Watermark Group (compact + enable toggle) ---
        watermark_group = QGroupBox("Timestamp Watermark")
        watermark_layout = QFormLayout(watermark_group)
        watermark_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        watermark_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        watermark_layout.setHorizontalSpacing(8)
        watermark_layout.setVerticalSpacing(4)

        # Checkbox to enable/disable timestamp drawing
        self.watermark_enabled_chk = QCheckBox("Include timestamp")
        self.watermark_enabled_chk.setChecked(True)
        self.watermark_enabled_chk.toggled.connect(self.settingsChanged.emit)
        self.watermark_enabled_chk.toggled.connect(self.toggle_watermark_widgets)
        watermark_layout.addRow(self.watermark_enabled_chk)

        # Compact single row for Size and Color
        roww = QWidget()
        row = QHBoxLayout(roww)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.watermark_size_spinbox = QSpinBox()
        self.watermark_size_spinbox.setRange(10, 50)
        self.watermark_size_spinbox.setValue(20)
        self.watermark_size_spinbox.setSuffix(" px")
        self.watermark_size_spinbox.setToolTip("Set the font size of the timestamp label.")
        self.watermark_size_spinbox.valueChanged.connect(self.settingsChanged.emit)

        self.watermark_color_combo = QComboBox()
        self.watermark_color_combo.addItems(["White", "Yellow", "Cyan", "Lime Green"])
        self.watermark_color_combo.setToolTip("Set the color of the timestamp label.")
        self.watermark_color_combo.currentTextChanged.connect(self.settingsChanged.emit)

        row.addWidget(QLabel("Size:"))
        row.addWidget(self.watermark_size_spinbox)
        row.addSpacing(12)
        row.addWidget(QLabel("Color:"))
        row.addWidget(self.watermark_color_combo, 1)
        row.addStretch(1)

        watermark_layout.addRow(roww)
        main_layout.addWidget(watermark_group)
        self.watermark_group = watermark_group

        # --- Cropping Window Group (compact) ---
        roi_group = QGroupBox("Cropping Window")
        form_layout_roi = QFormLayout(roi_group)
        form_layout_roi.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form_layout_roi.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout_roi.setHorizontalSpacing(8)
        form_layout_roi.setVerticalSpacing(4)

        # Visibility and apply toggles
        toggles_row_w = QWidget()
        toggles_row = QHBoxLayout(toggles_row_w)
        toggles_row.setContentsMargins(0, 0, 0, 0)
        toggles_row.setSpacing(12)
        self.show_crop_chk = QCheckBox("Show cropping overlay")
        self.show_crop_chk.setChecked(True)
        self.show_crop_chk.toggled.connect(self.settingsChanged.emit)
        self.apply_crop_chk = QCheckBox("Apply crop during processing")
        self.apply_crop_chk.setChecked(True)
        self.apply_crop_chk.toggled.connect(self.settingsChanged.emit)
        toggles_row.addWidget(self.show_crop_chk)
        toggles_row.addStretch(1)
        toggles_row.addWidget(self.apply_crop_chk)
        form_layout_roi.addRow(toggles_row_w)

        # Mask opacity control (outside-dimming strength)
        mask_row_w = QWidget()
        mask_row = QHBoxLayout(mask_row_w)
        mask_row.setContentsMargins(0, 0, 0, 0)
        mask_row.setSpacing(8)
        self.crop_mask_slider = QSlider(Qt.Orientation.Horizontal)
        self.crop_mask_slider.setRange(0, 100)
        self.crop_mask_spin = QSpinBox()
        self.crop_mask_spin.setRange(0, 100)
        self.crop_mask_spin.setSuffix(" %")
        self.crop_mask_slider.setValue(50)
        self.crop_mask_spin.setValue(50)
        self.crop_mask_slider.valueChanged.connect(self.crop_mask_spin.setValue)
        self.crop_mask_spin.valueChanged.connect(self.crop_mask_slider.setValue)
        self.crop_mask_slider.valueChanged.connect(self.settingsChanged.emit)
        mask_row.addWidget(QLabel("Mask opacity:"))
        mask_row.addWidget(self.crop_mask_slider, 1)
        mask_row.addWidget(self.crop_mask_spin)
        form_layout_roi.addRow(mask_row_w)

        self.roi_x_spin = QSpinBox()
        self.roi_y_spin = QSpinBox()
        self.roi_w_spin = QSpinBox()
        self.roi_h_spin = QSpinBox()
        for spinbox in [self.roi_x_spin, self.roi_y_spin, self.roi_w_spin, self.roi_h_spin]:
            spinbox.setRange(0, 8192)

        row1w = QWidget()
        row1 = QHBoxLayout(row1w)
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(8)
        row1.addWidget(QLabel("X:"))
        row1.addWidget(self.roi_x_spin)
        row1.addSpacing(12)
        row1.addWidget(QLabel("Y:"))
        row1.addWidget(self.roi_y_spin)
        row1.addStretch(1)

        row2w = QWidget()
        row2 = QHBoxLayout(row2w)
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(8)
        row2.addWidget(QLabel("W:"))
        row2.addWidget(self.roi_w_spin)
        row2.addSpacing(12)
        row2.addWidget(QLabel("H:"))
        row2.addWidget(self.roi_h_spin)
        row2.addStretch(1)

        form_layout_roi.addRow(row1w)
        form_layout_roi.addRow(row2w)
        self.roi_x_spin.valueChanged.connect(self._update_roi_from_spinners)
        self.roi_y_spin.valueChanged.connect(self._update_roi_from_spinners)
        self.roi_w_spin.valueChanged.connect(self._update_roi_from_spinners)
        self.roi_h_spin.valueChanged.connect(self._update_roi_from_spinners)
        main_layout.addWidget(roi_group)
        self.roi_group = roi_group

        # --- Animal Outline Settings ---
        outline_group = QGroupBox("Animal Outline")
        outline_form = QFormLayout(outline_group)
        self.outline_show_chk = QCheckBox("Show animal outline")
        self.outline_show_chk.setChecked(False)
        self.outline_show_chk.toggled.connect(self.settingsChanged.emit)
        outline_form.addRow(self.outline_show_chk)

        self.outline_method_combo = QComboBox()
        self.outline_method_combo.addItems(["Otsu", "Manual Threshold"])  
        self.outline_method_combo.setCurrentText("Otsu")
        self.outline_method_combo.currentTextChanged.connect(self.settingsChanged.emit)
        self.outline_method_combo.currentTextChanged.connect(self._update_outline_controls_visibility)
        outline_form.addRow("Method:", self.outline_method_combo)

        self.outline_source_combo = QComboBox()
        self.outline_source_combo.addItems(["WF", "FL"])
        self.outline_source_combo.currentTextChanged.connect(self.settingsChanged.emit)
        outline_form.addRow("Source:", self.outline_source_combo)

        thresh_row_w = QWidget()
        thresh_row = QHBoxLayout(thresh_row_w)
        thresh_row.setContentsMargins(0, 0, 0, 0)
        thresh_row.setSpacing(8)
        self.outline_thresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.outline_thresh_slider.setRange(0, 65535)
        self.outline_thresh_spin = QSpinBox()
        self.outline_thresh_spin.setRange(0, 65535)
        self.outline_thresh_slider.setValue(5000)
        self.outline_thresh_spin.setValue(5000)
        self.outline_thresh_slider.valueChanged.connect(self.outline_thresh_spin.setValue)
        self.outline_thresh_spin.valueChanged.connect(self.outline_thresh_slider.setValue)
        def _debounced_emit():
            try:
                if self._settings_debounce_timer is None:
                    self._settings_debounce_timer = QTimer(self)
                    self._settings_debounce_timer.setSingleShot(True)
                    self._settings_debounce_timer.setInterval(75)
                    self._settings_debounce_timer.timeout.connect(self.settingsChanged.emit)
                self._settings_debounce_timer.start()
            except Exception:
                try:
                    self.settingsChanged.emit()
                except Exception:
                    pass
        self.outline_thresh_slider.valueChanged.connect(_debounced_emit)
        self.outline_thresh_spin.valueChanged.connect(_debounced_emit)
        thresh_row.addWidget(self.outline_thresh_slider, 1)
        thresh_row.addWidget(self.outline_thresh_spin)
        self._outline_threshold_row = thresh_row_w
        outline_form.addRow("Threshold:", self._outline_threshold_row)

        otsu_row_w = QWidget()
        otsu_row = QHBoxLayout(otsu_row_w)
        otsu_row.setContentsMargins(0, 0, 0, 0)
        otsu_row.setSpacing(8)
        self.outline_otsu_boost_slider = QSlider(Qt.Orientation.Horizontal)
        self.outline_otsu_boost_slider.setRange(0, 50)
        self.outline_otsu_boost_spin = QSpinBox()
        self.outline_otsu_boost_spin.setRange(0, 50)
        self.outline_otsu_boost_spin.setSuffix(" %")
        self.outline_otsu_boost_slider.setValue(10)
        self.outline_otsu_boost_spin.setValue(10)
        self.outline_otsu_boost_slider.valueChanged.connect(self.outline_otsu_boost_spin.setValue)
        self.outline_otsu_boost_spin.valueChanged.connect(self.outline_otsu_boost_slider.setValue)
        self.outline_otsu_boost_slider.valueChanged.connect(self.settingsChanged.emit)
        otsu_row.addWidget(self.outline_otsu_boost_slider, 1)
        otsu_row.addWidget(self.outline_otsu_boost_spin)
        self._outline_otsu_row = otsu_row_w
        outline_form.addRow("Otsu boost:", self._outline_otsu_row)

        color_row_w = QWidget()
        color_row = QHBoxLayout(color_row_w)
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(8)
        self.outline_color_preview = QFrame()
        self.outline_color_preview.setFixedSize(18, 18)
        self.outline_color_preview.setStyleSheet("background-color: rgba(0,255,0,255); border: 1px solid #666; border-radius: 3px;")
        self.outline_color_btn = QPushButton("Choose…")
        def choose_outline_color():
            col = QColorDialog.getColor(parent=self)
            if col.isValid():
                self._set_outline_color(col)
                self.settingsChanged.emit()
        self.outline_color_btn.clicked.connect(choose_outline_color)
        color_row.addWidget(self.outline_color_preview)
        color_row.addWidget(self.outline_color_btn)
        color_row.addStretch(1)
        outline_form.addRow("Color:", color_row_w)
        main_layout.addWidget(outline_group)
        self.outline_group = outline_group

        # --- Annotations (Multi-ROIs) ---
        ann_group = QGroupBox("Annotations (ROIs)")
        ann_layout = QVBoxLayout(ann_group)
        header_row = QHBoxLayout()
        self.roi_show_all_chk = QCheckBox("Show all")
        self.roi_show_all_chk.setChecked(True)
        self.roi_show_all_chk.toggled.connect(self._on_toggle_all_rois_visible)
        header_row.addWidget(self.roi_show_all_chk)
        header_row.addStretch(1)
        self.add_roi_btn = QPushButton("Add Rectangle ROI")
        self.add_roi_btn.clicked.connect(self.addRectangleRoiRequested.emit)
        header_row.addWidget(self.add_roi_btn)
        ann_layout.addLayout(header_row)
        self.roi_list = QListWidget()
        self.roi_list.setSelectionMode(self.roi_list.SelectionMode.ExtendedSelection)
        self.roi_list.itemSelectionChanged.connect(self._on_roi_selection_changed)
        self.roi_list.itemDoubleClicked.connect(self._on_item_double_clicked_rename)
        try:
            self.roi_list.viewport().installEventFilter(self)
        except Exception:
            pass
        ann_layout.addWidget(self.roi_list)
        main_layout.addWidget(ann_group)
        self.ann_group = ann_group

        main_layout.addStretch(1)

        # --- Set Initial States ---
        self.toggle_registration_widgets(False)
        self._roi_id_by_row = []
        self._roi_summaries_by_id = {}
        self._update_outline_controls_visibility(self.outline_method_combo.currentText())
        self.enter_idle_state()

    def set_config_enabled(self, enabled: bool):
        """Enable/disable configuration groups while keeping control buttons active."""
        try:
            for grp in [
                getattr(self, 'overlay_group', None),
                getattr(self, 'norm_group', None),
                getattr(self, 'reg_group', None),
                getattr(self, 'watermark_group', None),
                getattr(self, 'roi_group', None),
                getattr(self, 'outline_group', None),
                getattr(self, 'ann_group', None),
            ]:
                if grp is not None:
                    grp.setEnabled(enabled)
        except Exception:
            pass

    # ---- Control state helpers ----
    def enter_idle_state(self):
        if hasattr(self, 'start_button'):
            self.start_button.setVisible(True)
        if hasattr(self, 'pause_button'):
            self.pause_button.setVisible(False)
        if hasattr(self, 'abort_button'):
            self.abort_button.setVisible(False)
        if hasattr(self, 'resume_button'):
            self.resume_button.setVisible(False)
        if hasattr(self, 'stop_button'):
            self.stop_button.setVisible(False)

    def enter_processing_state(self):
        if hasattr(self, 'start_button'):
            self.start_button.setVisible(False)
        if hasattr(self, 'pause_button'):
            self.pause_button.setVisible(True)
        if hasattr(self, 'abort_button'):
            self.abort_button.setVisible(True)
        if hasattr(self, 'resume_button'):
            self.resume_button.setVisible(False)
        if hasattr(self, 'stop_button'):
            self.stop_button.setVisible(False)

    def enter_paused_state(self):
        if hasattr(self, 'start_button'):
            self.start_button.setVisible(False)
        if hasattr(self, 'pause_button'):
            self.pause_button.setVisible(False)
        if hasattr(self, 'abort_button'):
            self.abort_button.setVisible(False)
        if hasattr(self, 'resume_button'):
            self.resume_button.setVisible(True)
        if hasattr(self, 'stop_button'):
            self.stop_button.setVisible(True)

    # --- Programmatic updates for outline controls ---
    def set_outline_threshold_max(self, max_val: int):
        """Clamp the manual threshold slider/spin range to the available image max intensity."""
        try:
            m = int(max(1, max_val))  # avoid zero-range; at least 1
            if hasattr(self, 'outline_thresh_slider'):
                cur_min = self.outline_thresh_slider.minimum()
                self.outline_thresh_slider.setRange(cur_min, m)
            if hasattr(self, 'outline_thresh_spin'):
                cur_min2 = self.outline_thresh_spin.minimum()
                self.outline_thresh_spin.setRange(cur_min2, m)
                # Clamp value if needed
                if self.outline_thresh_spin.value() > m:
                    self.outline_thresh_spin.setValue(m)
        except Exception:
            pass

    # Advanced Settings group removed to free space; verbose logging lives in the app Settings menu

    

    # ------- Multi-ROI helpers (update from PreviewPanel) -------
    def update_roi_list(self, summaries: list[dict]):
        """Called by MainWindow to refresh the ROI list from PreviewPanel."""
        self._roi_summaries_by_id = {}
        self.roi_list.blockSignals(True)
        self.roi_list.clear()
        self._roi_id_by_row = []
        for s in summaries:
            rid = s.get('id')
            name = s.get('name', 'ROI')
            r,g,b,a = s.get('color', (0,255,0,255))
            visible = bool(s.get('visible', True))

            item = QListWidgetItem()
            item.setSizeHint(QSize(10, 28))
            self.roi_list.addItem(item)
            self._roi_id_by_row.append(rid)
            if rid is not None:
                self._roi_summaries_by_id[rid] = s

            # Build per-row widget
            roww = QWidget()
            row = QHBoxLayout(roww)
            row.setContentsMargins(4, 2, 4, 2)
            row.setSpacing(6)

            # Color swatch
            swatch = QFrame()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(f"background-color: rgba({r},{g},{b},{a}); border: 1px solid #666; border-radius: 2px;")
            row.addWidget(swatch)

            # Name label
            name_label = QLabel(name)
            name_label.setToolTip("Double-click to rename")
            name_label.setStyleSheet("font-size: 10pt;")
            row.addWidget(name_label, 1)

            # Buttons: edit name, visibility, color, remove
            edit_btn = QToolButton()
            edit_btn.setIcon(self._make_edit_icon())
            edit_btn.setToolTip("Rename…")
            edit_btn.setAutoRaise(True)
            edit_btn.clicked.connect(lambda _, rid=rid: self._prompt_rename(rid))
            row.addWidget(edit_btn)

            vis_btn = QToolButton()
            vis_btn.setCheckable(True)
            vis_btn.setChecked(visible)
            vis_btn.setIcon(self._make_eye_icon(visible))
            vis_btn.setToolTip("Toggle visibility")
            vis_btn.setAutoRaise(True)
            def on_toggle(v, rid=rid, btn=vis_btn):
                btn.setIcon(self._make_eye_icon(v))
                self.toggleRoiVisibilityRequested.emit(rid, v)
            vis_btn.toggled.connect(on_toggle)
            row.addWidget(vis_btn)

            color_btn = QToolButton()
            color_btn.setIcon(self._make_palette_icon())
            color_btn.setToolTip("Change color…")
            color_btn.setAutoRaise(True)
            def on_color(_=None, rid=rid):
                color = QColorDialog.getColor(parent=self)
                if color.isValid():
                    self.changeRoiColorRequested.emit(rid, color)
            color_btn.clicked.connect(on_color)
            row.addWidget(color_btn)

            del_btn = QToolButton()
            del_btn.setIcon(self._make_trash_icon())
            del_btn.setToolTip("Remove ROI")
            del_btn.setAutoRaise(True)
            del_btn.clicked.connect(lambda _, rid=rid: self.removeRoiRequested.emit(rid))
            row.addWidget(del_btn)

            self.roi_list.setItemWidget(item, roww)
        self.roi_list.blockSignals(False)
        # After refresh, keep nothing selected until user clicks

    def _current_roi_id(self) -> Optional[int]:
        row = self.roi_list.currentRow()
        if row < 0 or row >= len(self._roi_id_by_row):
            return None
        return self._roi_id_by_row[row]

    def _on_roi_selection_changed(self):
        # Determine selected ROI ids
        selected_rows = [self.roi_list.row(i) for i in self.roi_list.selectedItems()]
        ids = []
        for row in selected_rows:
            if 0 <= row < len(self._roi_id_by_row):
                ids.append(self._roi_id_by_row[row])
        # Emit single selection id for preview panel; -1 means deselect
        if len(ids) == 1 and ids[0] is not None:
            try:
                self.selectedRoiChanged.emit(ids[0])
            except Exception:
                pass
        elif len(ids) == 0:
            try:
                self.selectedRoiChanged.emit(-1)
            except Exception:
                pass

    # Allow MainWindow to programmatically select a specific ROI in the list
    def select_roi_by_id(self, roi_id: int):
        try:
            if not hasattr(self, '_roi_id_by_row'):
                return
            for row, rid in enumerate(self._roi_id_by_row):
                if rid == roi_id:
                    # Clear and select this row (single select behavior from external events)
                    self.roi_list.blockSignals(True)
                    self.roi_list.clearSelection()
                    item = self.roi_list.item(row)
                    if item:
                        item.setSelected(True)
                    self.roi_list.blockSignals(False)
                    break
        except Exception:
            pass

    # Event filter to allow deselection by clicking empty area
    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is getattr(self.roi_list, 'viewport', lambda: None)() and event.type() == QEvent.Type.MouseButtonPress:
            # If click is not on an item, clear selection
            pos = event.pos()
            item = self.roi_list.itemAt(pos)
            if item is None:
                try:
                    self.roi_list.clearSelection()
                    self.selectedRoiChanged.emit(-1)
                except Exception:
                    pass
        return super().eventFilter(obj, event)

    def _on_remove_roi(self):
        rid = self._current_roi_id()
        if rid is not None:
            self.removeRoiRequested.emit(rid)

    def _on_rename_roi(self):
        rid = self._current_roi_id()
        if rid is not None:
            self.renameRoiRequested.emit(rid, self.roi_name_edit.text().strip())

    def _on_item_double_clicked_rename(self, item: QListWidgetItem):
        row = self.roi_list.row(item)
        if 0 <= row < len(self._roi_id_by_row):
            rid = self._roi_id_by_row[row]
            self._prompt_rename(rid)

    def _prompt_rename(self, roi_id: int):
        current = self._roi_summaries_by_id.get(roi_id, {}).get('name', '')
        text, ok = QInputDialog.getText(self, "Rename ROI", "Name:", text=current)
        if ok and text.strip():
            self.renameRoiRequested.emit(roi_id, text.strip())

    def _on_toggle_visibility(self, checked: bool):
        rid = self._current_roi_id()
        if rid is not None:
            self.toggleRoiVisibilityRequested.emit(rid, checked)

    def _on_toggle_all_rois_visible(self, checked: bool):
        # Toggle all rois via individual signals
        for rid in getattr(self, '_roi_id_by_row', []):
            if rid is not None:
                self.toggleRoiVisibilityRequested.emit(rid, checked)

    def _on_pick_color(self):
        rid = self._current_roi_id()
        if rid is None:
            return
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self.changeRoiColorRequested.emit(rid, color)

    # --- Small icon painters ---
    def _make_eye_icon(self, visible: bool) -> 'QIcon':
        from PyQt6.QtGui import QIcon, QPainter, QPen, QPixmap
        size = 64
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(230, 230, 230))
        pen.setWidthF(size * 0.06)
        p.setPen(pen)
        # Eye outline (simple oval)
        p.drawEllipse(int(size*0.18), int(size*0.35), int(size*0.64), int(size*0.30))
        # Pupil if visible, strike-through if hidden
        if visible:
            p.drawEllipse(int(size*0.42), int(size*0.45), int(size*0.16), int(size*0.16))
        else:
            p.drawLine(int(size*0.24), int(size*0.30), int(size*0.76), int(size*0.70))
        p.end()
        return QIcon(pm)

    def _make_trash_icon(self) -> 'QIcon':
        from PyQt6.QtGui import QIcon, QPainter, QPen, QPixmap
        size = 64
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(230,230,230))
        pen.setWidthF(size*0.06)
        p.setPen(pen)
        # Can body
        p.drawRect(int(size*0.28), int(size*0.30), int(size*0.44), int(size*0.44))
        # Lid
        p.drawLine(int(size*0.24), int(size*0.28), int(size*0.76), int(size*0.28))
        # Handle
        p.drawLine(int(size*0.44), int(size*0.22), int(size*0.56), int(size*0.22))
        p.end()
        return QIcon(pm)

    def _make_palette_icon(self) -> 'QIcon':
        from PyQt6.QtGui import QIcon, QPainter, QPen, QPixmap, QBrush
        size = 64
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(230,230,230))
        pen.setWidthF(size*0.06)
        p.setPen(pen)
        # Palette outline (circle-ish)
        p.drawEllipse(int(size*0.18), int(size*0.18), int(size*0.62), int(size*0.62))
        # Thumb hole
        p.drawEllipse(int(size*0.54), int(size*0.48), int(size*0.16), int(size*0.16))
        p.end()
        return QIcon(pm)

    def _make_edit_icon(self) -> 'QIcon':
        from PyQt6.QtGui import QIcon, QPainter, QPen, QPixmap
        size = 64
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(230,230,230))
        pen.setWidthF(size*0.06)
        p.setPen(pen)
        # Pencil-like shape
        p.drawLine(int(size*0.25), int(size*0.70), int(size*0.70), int(size*0.25))
        p.drawLine(int(size*0.65), int(size*0.30), int(size*0.75), int(size*0.20))
        p.end()
        return QIcon(pm)

    def update_spinners_from_roi(self, roi: QRect):
        self.roi_x_spin.blockSignals(True)
        self.roi_y_spin.blockSignals(True)
        self.roi_w_spin.blockSignals(True)
        self.roi_h_spin.blockSignals(True)
        
        self.roi_x_spin.setValue(roi.x())
        self.roi_y_spin.setValue(roi.y())
        self.roi_w_spin.setValue(roi.width())
        self.roi_h_spin.setValue(roi.height())

        self.roi_x_spin.blockSignals(False)
        self.roi_y_spin.blockSignals(False)
        self.roi_w_spin.blockSignals(False)
        self.roi_h_spin.blockSignals(False)
    
    def _update_roi_from_spinners(self):
        new_rect = QRect(self.roi_x_spin.value(), self.roi_y_spin.value(),
                         self.roi_w_spin.value(), self.roi_h_spin.value())
        self.roiChangedFromSpinners.emit(new_rect)

    def toggle_registration_widgets(self, checked):
        """Enable/disable registration widgets based on the checkbox."""
        self.load_template_button.setEnabled(checked)
        self.template_label.setEnabled(checked)
        if not checked:
            self.template_label.setText("Registration disabled.")
            if self.template_path is not None:
                self.template_path = None
                self.templatePathChanged.emit(None) # Notify main window
        else:
            self.template_label.setText("No template loaded.")

    def toggle_watermark_widgets(self, checked: bool):
        """Enable/disable timestamp widgets based on the checkbox."""
        self.watermark_size_spinbox.setEnabled(checked)
        self.watermark_color_combo.setEnabled(checked)


    def toggle_feature_widgets(self, checked):
        """Enable/disable feature widgets based on the master checkbox."""
        self.feature_widgets_container.setEnabled(checked)

    def select_all_features(self):
        """Checks all items in the feature list."""
        for i in range(self.feature_list_widget.count()):
            self.feature_list_widget.item(i).setCheckState(Qt.CheckState.Checked)

    def deselect_all_features(self):
        """Unchecks all items in the feature list."""
        for i in range(self.feature_list_widget.count()):
            self.feature_list_widget.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _load_template(self):
        """Opens a file dialog to select a template image."""
        filepath, _ = QFileDialog.getOpenFileName(self, "Select Template Image", "", "Image Files (*.tif *.tiff *.png)")
        if filepath:
            self.template_path = filepath
            self.template_label.setText(f"Loaded: {os.path.basename(filepath)}")
            # --- FIX: No longer need to manage start button state here ---
            self.templatePathChanged.emit(self.template_path)

    def _link_phase_controls(self):
        """Links the sliders and spinboxes for the phase cutoffs."""
        # Link slider to spinbox and vice-versa for the first cutoff
        self.phase1_slider.valueChanged.connect(self.phase1_spinbox.setValue)
        self.phase1_spinbox.valueChanged.connect(self.phase1_slider.setValue)

        # Link slider to spinbox and vice-versa for the second cutoff
        self.phase2_slider.valueChanged.connect(self.phase2_spinbox.setValue)
        self.phase2_spinbox.valueChanged.connect(self.phase2_slider.setValue)

        # --- Crucial Logic: Prevent sliders from crossing over ---
        def update_phase_sliders():
            phase1_val = self.phase1_slider.value()
            phase2_val = self.phase2_slider.value()
            
            # The second slider's minimum must be the first slider's value
            self.phase2_slider.setMinimum(phase1_val)
            
            # The first slider's maximum must be the second slider's value
            self.phase1_slider.setMaximum(phase2_val)

        # Connect the valueChanged signals to this update function
        self.phase1_slider.valueChanged.connect(update_phase_sliders)
        self.phase2_slider.valueChanged.connect(update_phase_sliders)
        
        # Initial call to set the ranges correctly
        update_phase_sliders()


    def get_settings(self) -> dict:
        """Returns a dictionary containing all current settings."""
        selected_features = []
        for i in range(self.feature_list_widget.count()):
            item = self.feature_list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                display_name = item.text()
                internal_name = self.available_features[display_name]
                selected_features.append(internal_name)
        
    def get_settings(self) -> dict:
        """Returns a dictionary containing all VISUAL settings."""
        # Get ROI from the spinboxes directly
        roi_rect = QRect(self.roi_x_spin.value(), self.roi_y_spin.value(),
                         self.roi_w_spin.value(), self.roi_h_spin.value())

        # Canonicalize outline method to stable keys ('otsu' | 'manual') regardless of label text
        try:
            _method_label = self.outline_method_combo.currentText() if hasattr(self, 'outline_method_combo') else 'Otsu'
            _ml = str(_method_label).strip().lower()
            _method_key = 'manual' if _ml.startswith('manual') else 'otsu'
        except Exception:
            _method_key = 'otsu'

        return {
            "transparency": self.transparency_slider.value(),
            "lut": self.lut_combo.currentText(),
            "min_intensity": self.min_intensity_spinbox.value(),
            "max_intensity": self.max_intensity_spinbox.value(),
            "use_registration": self.reg_checkbox.isChecked(),
            "template_path": self.template_path,
            "watermark_enabled": getattr(self, 'watermark_enabled_chk', None).isChecked() if hasattr(self, 'watermark_enabled_chk') else True,
            "watermark_size": self.watermark_size_spinbox.value(),
            "watermark_color": self.watermark_color_combo.currentText(),
            "verbose_logging": bool(getattr(self, '_verbose_logging_enabled', False)),
            "roi": [roi_rect.x(), roi_rect.y(), roi_rect.width(), roi_rect.height()],
            "show_crop_overlay": self.show_crop_chk.isChecked() if hasattr(self, 'show_crop_chk') else True,
            "apply_crop": self.apply_crop_chk.isChecked() if hasattr(self, 'apply_crop_chk') else True,
            "crop_mask_opacity": self.crop_mask_slider.value() if hasattr(self, 'crop_mask_slider') else 50,
            # Animal outline
            "show_animal_outline": self.outline_show_chk.isChecked() if hasattr(self, 'outline_show_chk') else False,
            "animal_outline_method": _method_key,
            "animal_outline_threshold": self.outline_thresh_spin.value() if hasattr(self, 'outline_thresh_spin') else 5000,
            "animal_outline_source": self.outline_source_combo.currentText() if hasattr(self, 'outline_source_combo') else 'WF',
            "animal_outline_color": self._get_outline_color_tuple(),
            "animal_outline_otsu_boost": self.outline_otsu_boost_spin.value() if hasattr(self, 'outline_otsu_boost_spin') else 10,
        }

    def set_settings(self, data: dict):
        """Sets all widgets in this panel based on a loaded dictionary."""
        self.transparency_slider.setValue(data.get("transparency", 70))
        self.lut_combo.setCurrentText(data.get("lut", "nipy_spectral"))
        self.min_intensity_spinbox.setValue(data.get("min_intensity", 100))
        self.max_intensity_spinbox.setValue(data.get("max_intensity", 20000))
        self.reg_checkbox.setChecked(data.get("use_registration", False))

        
        template_path = data.get("template_path")
        if template_path and os.path.exists(template_path):
            self.template_path = template_path
            self.template_label.setText(f"Loaded: {os.path.basename(template_path)}")
            self.templatePathChanged.emit(self.template_path)
        else:
            self.template_path = None
            self.template_label.setText("No template loaded.")
            self.templatePathChanged.emit(None)

        # Timestamp watermark
        if hasattr(self, 'watermark_enabled_chk'):
            self.watermark_enabled_chk.setChecked(data.get("watermark_enabled", True))
            # Ensure widgets reflect enabled state
            self.toggle_watermark_widgets(self.watermark_enabled_chk.isChecked())
        self.watermark_size_spinbox.setValue(data.get("watermark_size", 20))
        self.watermark_color_combo.setCurrentText(data.get("watermark_color", "White"))
        # Verbose logging now controlled by Settings menu; keep internal state synced
        self._verbose_logging_enabled = bool(data.get("verbose_logging", False))

        roi_coords = data.get("roi", [0, 0, 0, 0])
        if len(roi_coords) == 4:
            self.roi_x_spin.setValue(roi_coords[0])
            self.roi_y_spin.setValue(roi_coords[1])
            self.roi_w_spin.setValue(roi_coords[2])
            self.roi_h_spin.setValue(roi_coords[3])
            # This will automatically emit the signal to update the preview
            self._update_roi_from_spinners()

        # Cropping overlay and apply-crop toggles
        if hasattr(self, 'show_crop_chk'):
            self.show_crop_chk.setChecked(data.get("show_crop_overlay", True))
        if hasattr(self, 'apply_crop_chk'):
            self.apply_crop_chk.setChecked(data.get("apply_crop", True))
        if hasattr(self, 'crop_mask_slider'):
            self.crop_mask_slider.setValue(data.get("crop_mask_opacity", 50))
            self.crop_mask_spin.setValue(data.get("crop_mask_opacity", 50))

        # Animal outline settings
        if hasattr(self, 'outline_show_chk'):
            self.outline_show_chk.setChecked(data.get("show_animal_outline", False))
        if hasattr(self, 'outline_method_combo'):
            method = data.get("animal_outline_method", 'otsu')
            self.outline_method_combo.setCurrentText('Otsu' if str(method).lower() == 'otsu' else 'Manual Threshold')
        if hasattr(self, 'outline_source_combo'):
            self.outline_source_combo.setCurrentText(data.get("animal_outline_source", 'WF'))
        if hasattr(self, 'outline_thresh_slider'):
            self.outline_thresh_slider.setValue(int(data.get("animal_outline_threshold", 5000)))
            self.outline_thresh_spin.setValue(int(data.get("animal_outline_threshold", 5000)))
        if hasattr(self, 'outline_otsu_boost_slider'):
            self.outline_otsu_boost_slider.setValue(int(data.get("animal_outline_otsu_boost", 10)))
            self.outline_otsu_boost_spin.setValue(int(data.get("animal_outline_otsu_boost", 10)))
        # Refresh visibility of per-method controls
        if hasattr(self, 'outline_method_combo'):
            self._update_outline_controls_visibility(self.outline_method_combo.currentText())
        if 'animal_outline_color' in data:
            col = data.get("animal_outline_color")
            if isinstance(col, (tuple, list)) and len(col) >= 3:
                q = QColor(int(col[0]), int(col[1]), int(col[2]), int(col[3]) if len(col) > 3 else 255)
                self._set_outline_color(q)
            elif isinstance(col, str) and col.startswith('#'):
                q = QColor(col)
                if q.isValid():
                    self._set_outline_color(q)

    # External API for MainWindow to control verbose flag from menu
    def set_verbose_logging(self, enabled: bool):
        self._verbose_logging_enabled = bool(enabled)
        # Notify that settings were conceptually changed
        try:
            self.settingsChanged.emit()
        except Exception:
            pass

    # --- Helpers for outline color ---
    def _set_outline_color(self, color: QColor):
        if not color.isValid():
            return
        r, g, b, a = color.red(), color.green(), color.blue(), color.alpha()
        if hasattr(self, 'outline_color_preview'):
            self.outline_color_preview.setStyleSheet(f"background-color: rgba({r},{g},{b},{a}); border: 1px solid #666; border-radius: 3px;")
        self._outline_color = QColor(color)

    def _get_outline_color_tuple(self):
        col = getattr(self, '_outline_color', QColor(0, 255, 0))
        return (col.red(), col.green(), col.blue(), col.alpha())

    # --- Outline controls visibility ---
    def _update_outline_controls_visibility(self, method_label: str):
        method = (method_label or 'Otsu').lower()
        is_otsu = method.startswith('otsu')
        # Show threshold only for Manual; Otsu boost only for Otsu
        if hasattr(self, '_outline_threshold_row'):
            self._outline_threshold_row.setVisible(not is_otsu)
        if hasattr(self, '_outline_otsu_row'):
            self._outline_otsu_row.setVisible(is_otsu)