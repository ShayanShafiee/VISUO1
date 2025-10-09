# --- CORRECTED FILE: gui/preview_panel.py ---

import os
from PyQt6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout,
                             QSizePolicy, QFileDialog, QGroupBox, QFormLayout, QSpinBox)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, pyqtSignal, QRect

from .interactive_roi import InteractiveROI


class PreviewPanel(QWidget):
    requestNewRandomImage = pyqtSignal()
    requestSpecificImage = pyqtSignal(str)
    requestPreviousImage = pyqtSignal()
    requestNextImage = pyqtSignal()
    roiChangedFromDrawing = pyqtSignal(QRect)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap_scale_factor = 1.0
        self._init_ui()

    def _init_ui(self):
        """
        Initializes the user interface for the preview panel.
        This panel is now simplified to contain only the image viewer,
        file info, and navigation buttons. ROI controls are in the SettingsPanel.
        """
        # The top-level layout for this entire panel is vertical.
        top_level_layout = QVBoxLayout(self)
        top_level_layout.setContentsMargins(0, 0, 0, 0)

        # 1. IMAGE LABEL
        # The main widget for displaying the preview image.
        self.image_label = QLabel("Select a main directory to begin.")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.image_label.setStyleSheet("border: 1px solid gray; background-color: #505050;")
        self.image_label.setMinimumSize(400, 500) 
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        top_level_layout.addWidget(self.image_label)
        
        # The interactive ROI widget is a transparent overlay on the image_label.
        self.roi_widget = InteractiveROI(self.image_label)
        self.roi_widget.roiChanged.connect(self._on_roi_drawn) # Emits the raw widget rect
        
        # 2. FILE INFO GROUP
        # This group box displays the paths of the currently previewed files.
        info_group = QGroupBox("Current Preview File")
        # info_group.setFixedHeight(100)
        info_layout = QFormLayout(info_group)
        info_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        info_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        info_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)



        self.wf_path_label = QLabel("N/A")
        self.fl_path_label = QLabel("N/A")
        for label in [self.wf_path_label, self.fl_path_label]:
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        info_layout.addRow("WF File:", self.wf_path_label)
        info_layout.addRow("FL File:", self.fl_path_label)
        top_level_layout.addWidget(info_group)
        
        # 3. NAVIGATION BUTTONS
        # A horizontal layout for the Previous, Random, Next, and Select buttons.
        button_layout = QHBoxLayout()
        self.prev_button = QPushButton("◀ Previous")
        self.random_button = QPushButton("↻ Random")
        self.next_button = QPushButton("▶ Next")
        self.select_button = QPushButton("📂 Select Specific...")

        self.prev_button.clicked.connect(self.requestPreviousImage.emit)
        self.random_button.clicked.connect(self.requestNewRandomImage.emit)
        self.next_button.clicked.connect(self.requestNextImage.emit)
        self.select_button.clicked.connect(self._select_file)
        
        button_layout.addWidget(self.prev_button)
        button_layout.addWidget(self.random_button)
        button_layout.addWidget(self.next_button)
        button_layout.addStretch(1) # Pushes the "Select" button to the far right
        button_layout.addWidget(self.select_button)
        top_level_layout.addLayout(button_layout)

    # Public method for settings panel to update the drawn ROI ---
    def update_roi_display(self, roi: QRect):
        if self.pixmap_scale_factor > 0:
            scaled_rect = QRect(
                int(roi.x() / self.pixmap_scale_factor),
                int(roi.y() / self.pixmap_scale_factor),
                int(roi.width() / self.pixmap_scale_factor),
                int(roi.height() / self.pixmap_scale_factor)
            )
            self.roi_widget.setRoi(scaled_rect)


    def get_roi(self):
        widget_rect = self.roi_widget.roi_rect
        return QRect(
            int(widget_rect.x() * self.pixmap_scale_factor),
            int(widget_rect.y() * self.pixmap_scale_factor),
            int(widget_rect.width() * self.pixmap_scale_factor),
            int(widget_rect.height() * self.pixmap_scale_factor)
        )

    def _on_roi_drawn(self, widget_rect):
        final_roi = self.get_roi()
        self.roiChangedFromDrawing.emit(final_roi)

    def _update_roi_from_spinners(self):
        if self.pixmap_scale_factor == 0: return
        scaled_rect = QRect(
            int(self.roi_x_spin.value() / self.pixmap_scale_factor),
            int(self.roi_y_spin.value() / self.pixmap_scale_factor),
            int(self.roi_w_spin.value() / self.pixmap_scale_factor),
            int(self.roi_h_spin.value() / self.pixmap_scale_factor)
        )
        self.roi_widget.setRoi(scaled_rect)

    def _update_spinners_from_roi(self, widget_rect):
        final_roi = self.get_roi()
        self.roi_x_spin.blockSignals(True)
        self.roi_y_spin.blockSignals(True)
        self.roi_w_spin.blockSignals(True)
        self.roi_h_spin.blockSignals(True)
        self.roi_x_spin.setValue(final_roi.x())
        self.roi_y_spin.setValue(final_roi.y())
        self.roi_w_spin.setValue(final_roi.width())
        self.roi_h_spin.setValue(final_roi.height())
        self.roi_x_spin.blockSignals(False)
        self.roi_y_spin.blockSignals(False)
        self.roi_w_spin.blockSignals(False)
        self.roi_h_spin.blockSignals(False)

    def update_preview(self, pixmap: QPixmap):
        self.original_pixmap = pixmap
        self._rescale_ui()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale_ui()

    def _rescale_ui(self):
        if not hasattr(self, 'original_pixmap') or self.original_pixmap.isNull():
            return
        scaled_pixmap = self.original_pixmap.scaled(
            self.image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)
        if scaled_pixmap.width() > 0:
            self.pixmap_scale_factor = self.original_pixmap.width() / scaled_pixmap.width()
        else:
            self.pixmap_scale_factor = 1.0
        self.roi_widget.setGeometry(0, 0, scaled_pixmap.width(), scaled_pixmap.height())

    def set_file_info(self, wf_path: str, fl_path: str):
        self.wf_path_label.setText(os.path.basename(wf_path))
        self.wf_path_label.setToolTip(wf_path)
        self.fl_path_label.setText(os.path.basename(fl_path))
        self.fl_path_label.setToolTip(fl_path)

    def _select_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select Image for Preview", "", "Tiff Files (*.tif *.tiff)")
        if filepath:
            self.requestSpecificImage.emit(filepath)