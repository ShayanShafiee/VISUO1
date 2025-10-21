# --- CORRECTED FILE: gui/settings_panel.py ---

import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QFormLayout, 
                             QSlider, QComboBox, QPushButton, QSpinBox, QLabel,
                             QSizePolicy, QFileDialog, QHBoxLayout, QCheckBox, 
                             QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt, pyqtSignal, QRect

class SettingsPanel(QWidget):
    settingsChanged = pyqtSignal()
    startProcessing = pyqtSignal()
    templatePathChanged = pyqtSignal(str)
    roiChangedFromSpinners = pyqtSignal(QRect)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.template_path = None
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
        # Add standard and quantized colormaps
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

        # --- Timestamp Watermark Group ---
        watermark_group = QGroupBox("Timestamp Watermark")
        watermark_layout = QFormLayout(watermark_group)
        self.watermark_size_spinbox = QSpinBox()
        self.watermark_size_spinbox.setRange(10, 50)
        self.watermark_size_spinbox.setValue(20)
        self.watermark_size_spinbox.setSuffix(" px")
        self.watermark_size_spinbox.setToolTip("Set the font size of the timestamp label.")
        watermark_layout.addRow("Font Size:", self.watermark_size_spinbox)
        self.watermark_color_combo = QComboBox()
        self.watermark_color_combo.addItems(["White", "Yellow", "Cyan", "Lime Green"])
        self.watermark_color_combo.setToolTip("Set the color of the timestamp label.")
        watermark_layout.addRow("Font Color:", self.watermark_color_combo)
        main_layout.addWidget(watermark_group)
        
        # --- Region of Interest Group ---
        roi_group = QGroupBox("Region of Interest (ROI)")
        form_layout_roi = QFormLayout(roi_group)
        form_layout_roi.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form_layout_roi.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        
        self.roi_x_spin = QSpinBox()
        self.roi_y_spin = QSpinBox()
        self.roi_w_spin = QSpinBox()
        self.roi_h_spin = QSpinBox()
        for spinbox in [self.roi_x_spin, self.roi_y_spin, self.roi_w_spin, self.roi_h_spin]:
            spinbox.setRange(0, 8192)
        form_layout_roi.addRow("X:", self.roi_x_spin)
        form_layout_roi.addRow("Y:", self.roi_y_spin)
        form_layout_roi.addRow("Width:", self.roi_w_spin)
        form_layout_roi.addRow("Height:", self.roi_h_spin)
        
        self.roi_x_spin.valueChanged.connect(self._update_roi_from_spinners)
        self.roi_y_spin.valueChanged.connect(self._update_roi_from_spinners)
        self.roi_w_spin.valueChanged.connect(self._update_roi_from_spinners)
        self.roi_h_spin.valueChanged.connect(self._update_roi_from_spinners)
        main_layout.addWidget(roi_group)


        main_layout.addStretch(1) # This pushes the next items to the bottom

        # --- Advanced Settings Group ---
        advanced_group = QGroupBox("Advanced Settings")
        advanced_layout = QVBoxLayout(advanced_group)
        
        self.verbose_logging_checkbox = QCheckBox("Enable Verbose Logging")
        self.verbose_logging_checkbox.setToolTip("If checked, shows detailed log messages from libraries in the terminal.")
        self.verbose_logging_checkbox.setChecked(False) # Default to off
        advanced_layout.addWidget(self.verbose_logging_checkbox)
        
        main_layout.addWidget(advanced_group)




        # --- Final UI Elements ---
        main_layout.addStretch(1)
        self.start_button = QPushButton("Start Processing")
        self.start_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.start_button.clicked.connect(self.startProcessing.emit)
        main_layout.addWidget(self.start_button)
        
        # --- Set Initial States ---
        self.toggle_registration_widgets(False)

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
        roi = self.roiChangedFromSpinners.emit # This is not correct
        # Let's get it from the spinboxes directly
        roi_rect = QRect(self.roi_x_spin.value(), self.roi_y_spin.value(),
                         self.roi_w_spin.value(), self.roi_h_spin.value())
        
        return {
            "transparency": self.transparency_slider.value(),
            "lut": self.lut_combo.currentText(),
            "min_intensity": self.min_intensity_spinbox.value(),
            "max_intensity": self.max_intensity_spinbox.value(),
            "use_registration": self.reg_checkbox.isChecked(),
            "template_path": self.template_path,
            "watermark_size": self.watermark_size_spinbox.value(),
            "watermark_color": self.watermark_color_combo.currentText(),
            "verbose_logging": self.verbose_logging_checkbox.isChecked(),
            "roi": [roi_rect.x(), roi_rect.y(), roi_rect.width(), roi_rect.height()],

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

        self.watermark_size_spinbox.setValue(data.get("watermark_size", 20))
        self.watermark_color_combo.setCurrentText(data.get("watermark_color", "White"))
        self.verbose_logging_checkbox.setChecked(data.get("verbose_logging", False))
        
        roi_coords = data.get("roi", [0, 0, 0, 0])
        if len(roi_coords) == 4:
            self.roi_x_spin.setValue(roi_coords[0])
            self.roi_y_spin.setValue(roi_coords[1])
            self.roi_w_spin.setValue(roi_coords[2])
            self.roi_h_spin.setValue(roi_coords[3])
            # This will automatically emit the signal to update the preview
            self._update_roi_from_spinners()