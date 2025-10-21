# --- CORRECTED FILE: gui/preview_panel.py ---

import os
import cv2
import numpy as np
from processing.image_processor import create_gradient_image
from PyQt6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout, QApplication,
                             QSizePolicy, QFileDialog, QGroupBox, QFormLayout, QSpinBox)
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QTimer

from .interactive_roi import InteractiveROI


COLOR_MAP = {
    "White": (255, 255, 255),
    "Yellow": (0, 255, 255),
    "Cyan": (255, 255, 0),
    "Lime Green": (0, 255, 0)
}


class LiveColorBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.bar_width = 10
        self.bg_color_val = 50

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.max_label = QLabel("Max")
        self.max_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.max_label.setStyleSheet("font-size: 9pt; color: #CCCCCC;")

        self.gradient_label = QLabel()
        self.gradient_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.min_label = QLabel("Min")
        self.min_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.min_label.setStyleSheet("font-size: 9pt; color: #CCCCCC;")

        layout.addWidget(self.max_label)
        layout.addWidget(self.gradient_label, 1)
        layout.addWidget(self.min_label)

    def update_values(self, min_val: int, max_val: int, cmap_name: str):
        self.max_label.setText(str(max_val))
        self.min_label.setText(str(min_val))
        
        QApplication.processEvents()

        grad_height = self.gradient_label.height()
        grad_width = self.gradient_label.width()

        if grad_height <= 0 or grad_width <= 0: return

        gradient_np = create_gradient_image(grad_height, self.bar_width, cmap_name)
        
        background = np.full((grad_height, grad_width, 3), self.bg_color_val, dtype=np.uint8)
        x_offset = (grad_width - self.bar_width) // 2
        background[:, x_offset : x_offset + self.bar_width] = gradient_np

        final_bar_img = cv2.cvtColor(background, cv2.COLOR_BGR2RGB)
        h, w, ch = final_bar_img.shape
        q_image = QImage(final_bar_img.data, w, h, ch * w, QImage.Format.Format_RGB888)
        self.gradient_label.setPixmap(QPixmap.fromImage(q_image))


class PreviewPanel(QWidget):
    requestNewRandomImage = pyqtSignal()
    requestSpecificImage = pyqtSignal(str)
    requestPreviousImage = pyqtSignal()
    requestNextImage = pyqtSignal()
    roiChangedFromDrawing = pyqtSignal(QRect)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap_scale_factor = 1.0
        self.current_settings = {}
        # Maintain a canonical ROI in image coordinates so it doesn't drift on resizes
        self._image_roi = None
        # Guard to prevent feedback loops when programmatically updating the ROI
        self._suppress_roi_signal = False
        # Debounce timer to finalize ROI redraw after window resizing
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_settled)

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

        # Create a horizontal layout for the image and its color bar ---
        image_and_bar_layout = QHBoxLayout()
        image_and_bar_layout.setSpacing(10)

        # 1. IMAGE LABEL
        # The main widget for displaying the preview image.
        self.image_label = QLabel("Select a main directory to begin.")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.image_label.setStyleSheet("background-color: #323232; border: none;")
        self.image_label.setMinimumSize(400, 500) 
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Add the image label with a stretch factor so it takes up most of the space
        image_and_bar_layout.addWidget(self.image_label, 1)

        # 2. COLOR BAR LABEL
        self.colorbar = LiveColorBar()
        self.colorbar.setFixedWidth(60) # Wide enough for text like "20000"
        self.colorbar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        image_and_bar_layout.addWidget(self.colorbar, 0)

        # Add the horizontal layout to the main panel's vertical layout and let it take extra space
        top_level_layout.addLayout(image_and_bar_layout, 1)

        # Add a stretch to the main vertical layout 
        # This pushes the entire image_and_bar_layout content to the top.

        # The interactive ROI widget is a transparent overlay on the image_label.
        self.roi_widget = InteractiveROI(self.image_label)
        self.roi_widget.roiChanged.connect(self._on_roi_drawn) # Emits the raw widget rect
        
        # 3. FILE INFO GROUP
        info_group = QGroupBox("Current Preview File")
        info_layout = QFormLayout(info_group)
        info_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        info_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.wf_path_label = QLabel("N/A")
        self.fl_path_label = QLabel("N/A")
        for label in [self.wf_path_label, self.fl_path_label]:
            label.setWordWrap(True)
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

    def update_roi_display(self, roi: QRect):
        """Update the on-screen ROI overlay based on a given image-space ROI.
        Also stores it as the canonical ROI to keep consistent across resizes.
        """
        self._image_roi = QRect(roi) if roi is not None else None
        if self.pixmap_scale_factor > 0 and self._image_roi is not None:
            scaled_rect = QRect(
                int(self._image_roi.x() / self.pixmap_scale_factor),
                int(self._image_roi.y() / self.pixmap_scale_factor),
                int(self._image_roi.width() / self.pixmap_scale_factor),
                int(self._image_roi.height() / self.pixmap_scale_factor)
            )
            # Prevent emitting ROI-changed signals while we programmatically set it
            self._suppress_roi_signal = True
            try:
                self.roi_widget.setRoi(scaled_rect)
            finally:
                self._suppress_roi_signal = False

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
        if not self._suppress_roi_signal:
            # Update canonical image-space ROI only for genuine user edits
            self._image_roi = QRect(final_roi)
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

    def update_preview(self, pixmap: QPixmap, settings: dict):
        self.original_pixmap = pixmap
        self.current_settings = settings # Store the settings
        self._rescale_ui() # Trigger a full redraw

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale_ui()
        # Debounce: finalize ROI overlay after user stops resizing
        try:
            self._resize_timer.stop()
        except Exception:
            pass
        self._resize_timer.start(150)

    def _rescale_ui(self):
        if not hasattr(self, 'original_pixmap') or self.original_pixmap.isNull():
            return

        # Ensure we have a canonical image-space ROI stored once
        if self._image_roi is None and hasattr(self, 'roi_widget') and self.pixmap_scale_factor > 0:
            try:
                self._image_roi = self.get_roi()
            except Exception:
                self._image_roi = None
        scaled_pixmap = self.original_pixmap.scaled(
            self.image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)

        # Generate and display the color bar ---
        if self.current_settings and scaled_pixmap.height() > 0:
            # 1. Force the color bar's container to match the actual image's height
            self.colorbar.setFixedHeight(scaled_pixmap.height())
            
            # 2. Tell the color bar to update its internal contents
            self.colorbar.update_values(
                min_val=self.current_settings.get("min_intensity", 0),
                max_val=self.current_settings.get("max_intensity", 1),
                cmap_name=self.current_settings.get("lut", "nipy_spectral")
            )


        # Update scale factor and ROI overlay geometry to match new pixmap size
        if scaled_pixmap.width() > 0:
            new_scale = self.original_pixmap.width() / scaled_pixmap.width()
        else:
            new_scale = 1.0
        self.pixmap_scale_factor = new_scale

        if hasattr(self, 'roi_widget'):
            self.roi_widget.setGeometry(0, 0, scaled_pixmap.width(), scaled_pixmap.height())
            # Reapply canonical image-space ROI to new widget scale
            if self._image_roi is not None:
                self.update_roi_display(self._image_roi)

    def _on_resize_settled(self):
        """After resize ends, snap the ROI overlay exactly to settings panel values if available."""
        # Prefer explicit ROI from current settings if present
        roi_from_settings = None
        try:
            if self.current_settings and isinstance(self.current_settings.get("roi"), (list, tuple)):
                rx, ry, rw, rh = self.current_settings["roi"]
                roi_from_settings = QRect(int(rx), int(ry), int(rw), int(rh))
        except Exception:
            roi_from_settings = None

        if roi_from_settings is not None:
            self.update_roi_display(roi_from_settings)
        elif self._image_roi is not None:
            # Fall back to the canonical image-space ROI if settings are not available
            self.update_roi_display(self._image_roi)

    def set_file_info(self, wf_path: str, fl_path: str):
        self.wf_path_label.setText(os.path.basename(wf_path))
        self.wf_path_label.setToolTip(wf_path)
        self.fl_path_label.setText(os.path.basename(fl_path))
        self.fl_path_label.setToolTip(fl_path)

    def _select_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select Image for Preview", "", "Tiff Files (*.tif *.tiff)")
        if filepath:
            self.requestSpecificImage.emit(filepath)