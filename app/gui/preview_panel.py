# --- CORRECTED FILE: gui/preview_panel.py ---

import os
import cv2
import numpy as np
from processing.image_processor import create_gradient_image
from PyQt6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout, QApplication,
                             QSizePolicy, QFileDialog, QGroupBox, QFormLayout, QSpinBox,
                             QGraphicsView, QGraphicsScene)
from PyQt6.QtGui import QPixmap, QImage, QMouseEvent, QPainter
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QTimer, QPoint, QPointF

from .interactive_roi import InteractiveROI


class ZoomableImageView(QGraphicsView):
    """A QGraphicsView-based image viewer that supports smooth zoom and pan
    without affecting the window's layout size. The scene holds a single
    pixmap item at (0,0) in scene coordinates.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self._pixmap_item = self.scene().addPixmap(QPixmap())
        self._pixmap_item.setPos(0, 0)
        self._base_fit_scale = 1.0
        self._zoom_factor = 1.0
        self._min_zoom = 0.25
        self._max_zoom = 8.0
        self._zoom_step = 1.2
        # View configuration
        self.setRenderHints(self.renderHints() | QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

    def has_image(self) -> bool:
        return not self._pixmap_item.pixmap().isNull()

    def set_pixmap(self, pixmap: QPixmap):
        self._pixmap_item.setPixmap(pixmap)
        self.scene().setSceneRect(0, 0, pixmap.width(), pixmap.height())
        # Reset view transform and fit to viewport
        self.resetTransform()
        self._update_fit_scale()
        self._zoom_factor = 1.0
        self._apply_zoom()

    def update_pixmap(self, pixmap: QPixmap, preserve_center: bool = True):
        """Replace the pixmap without resetting the current zoom/transform.
        Optionally keep the same viewport center in scene coordinates.
        """
        # Preserve current viewing state as precisely as possible
        old_total_scale = self.transform().m11()  # current applied scale (x axis)
        old_h = self.horizontalScrollBar().value()
        old_v = self.verticalScrollBar().value()
        center_scene = None
        if preserve_center and self.has_image():
            # Also keep a scene center fallback in case scrollbar ranges change
            center_scene = self.mapToScene(self.viewport().rect().center())

        # Update pixmap and scene rect (keeps item at 0,0)
        self._pixmap_item.setPixmap(pixmap)
        self.scene().setSceneRect(0, 0, pixmap.width(), pixmap.height())

        # Recompute base fit scale for accurate Home behavior
        self._update_fit_scale()

        # Recalculate zoom_factor so that total scale remains exactly the same
        # Avoid cumulative drift from floating/int rounding
        if self._base_fit_scale > 0:
            self._zoom_factor = max(self._min_zoom, min(self._max_zoom, old_total_scale / self._base_fit_scale))
        # Reapply transform at the same absolute scale
        self._apply_zoom()

        if preserve_center:
            # First, try to restore exact scroll positions (most stable for same-size updates)
            self.horizontalScrollBar().setValue(old_h)
            self.verticalScrollBar().setValue(old_v)
            # If scene size changed and scrollbars adjusted, fall back to scene center
            if center_scene is not None:
                self.centerOn(center_scene)

    def _update_fit_scale(self):
        if not self.has_image():
            self._base_fit_scale = 1.0
            return
        vw = max(1, self.viewport().width())
        vh = max(1, self.viewport().height())
        pw = max(1, self._pixmap_item.pixmap().width())
        ph = max(1, self._pixmap_item.pixmap().height())
        self._base_fit_scale = min(vw / pw, vh / ph)

    def total_scale(self) -> float:
        return self._base_fit_scale * self._zoom_factor

    def _apply_zoom(self):
        self.resetTransform()
        self.scale(self.total_scale(), self.total_scale())
        # Enable hand-drag only when zoomed beyond fit
        if self._zoom_factor > 1.0:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)

    # External API
    def zoom_in(self):
        self._zoom_factor = min(self._max_zoom, self._zoom_factor * self._zoom_step)
        self._apply_zoom()

    def zoom_out(self):
        self._zoom_factor = max(self._min_zoom, self._zoom_factor / self._zoom_step)
        self._apply_zoom()

    def zoom_home(self):
        self._zoom_factor = 1.0
        self._apply_zoom()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # When the viewport resizes, recompute base fit and reapply zoom so fit/home works
        old_scene_pos = self.mapToScene(self.viewport().rect().center()) if self.has_image() else None
        self._update_fit_scale()
        self._apply_zoom()
        # Try to keep the same center point during a resize
        if old_scene_pos is not None:
            self.centerOn(old_scene_pos)


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
        self.zoom_factor = 1.0
        self._min_zoom = 0.25
        self._max_zoom = 8.0
        self._zoom_step = 1.2
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

        # 1. ZOOMABLE IMAGE VIEW (replaces scroll area + label)
        self.image_view = ZoomableImageView()
        self.image_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Keep ROI overlay in sync when panning via scrollbars
        self.image_view.horizontalScrollBar().valueChanged.connect(self._sync_overlay_to_view)
        self.image_view.verticalScrollBar().valueChanged.connect(self._sync_overlay_to_view)
        image_and_bar_layout.addWidget(self.image_view, 1)

        # 2. COLOR BAR LABEL
        self.colorbar = LiveColorBar()
        self.colorbar.setFixedWidth(60)  # Wide enough for text like "20000"
        self.colorbar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        image_and_bar_layout.addWidget(self.colorbar, 0)

        # Add the horizontal layout to the main panel's vertical layout and let it take extra space
        top_level_layout.addLayout(image_and_bar_layout, 1)

        # 2a. ZOOM CONTROLS
        zoom_layout = QHBoxLayout()
        self.zoom_out_btn = QPushButton("-")
        self.zoom_home_btn = QPushButton("Home")
        self.zoom_in_btn = QPushButton("+")
        self.zoom_out_btn.setFixedWidth(40)
        self.zoom_in_btn.setFixedWidth(40)
        self.zoom_home_btn.setFixedWidth(70)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_home_btn.clicked.connect(self.zoom_home)
        zoom_layout.addWidget(self.zoom_out_btn)
        zoom_layout.addWidget(self.zoom_home_btn)
        zoom_layout.addWidget(self.zoom_in_btn)
        zoom_layout.addStretch(1)
        top_level_layout.addLayout(zoom_layout)

        # Add a stretch to the main vertical layout
        # This pushes the entire image_and_bar_layout content to the top.

        # The interactive ROI widget is a transparent overlay on the graphics view's viewport.
        self.roi_widget = InteractiveROI(self.image_view.viewport())
        self.roi_widget.roiChanged.connect(self._on_roi_drawn)  # Emits the raw widget rect
        
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
        Uses view mapping to handle zoom and pan correctly.
        """
        self._image_roi = QRect(roi) if roi is not None else None
        if self._image_roi is None or not hasattr(self, 'image_view'):
            return
        # Map image-space ROI to viewport widget coordinates
        tl_view = self.image_view.mapFromScene(QPointF(self._image_roi.topLeft()))
        br_view = self.image_view.mapFromScene(QPointF(self._image_roi.bottomRight()))
        widget_rect = QRect(tl_view, br_view)
        # Clip to the viewport area
        vp_rect = self.image_view.viewport().rect()
        clipped = widget_rect.intersected(vp_rect)
        self._suppress_roi_signal = True
        try:
            self.roi_widget.setRoi(clipped)
        finally:
            self._suppress_roi_signal = False

    def get_roi(self):
        """Return ROI in image-space coordinates using view mapping."""
        widget_rect = self.roi_widget.roi_rect
        if not hasattr(self, 'image_view'):
            return QRect()
        tl_scene = self.image_view.mapToScene(widget_rect.topLeft())
        br_scene = self.image_view.mapToScene(widget_rect.bottomRight())
        x = int(tl_scene.x())
        y = int(tl_scene.y())
        w = int(br_scene.x() - tl_scene.x())
        h = int(br_scene.y() - tl_scene.y())
        return QRect(x, y, w, h)

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
        self.current_settings = settings  # Store the settings
        if hasattr(self, 'image_view'):
            if not self.image_view.has_image():
                # First time: set and fit
                self.image_view.set_pixmap(pixmap)
            else:
                # Subsequent updates (e.g., intensity/LUT changes): preserve zoom/center
                self.image_view.update_pixmap(pixmap, preserve_center=True)
        self._rescale_ui()  # Trigger a UI refresh (colorbar + overlay)

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
        if not hasattr(self, 'original_pixmap') or self.original_pixmap.isNull() or not hasattr(self, 'image_view'):
            return

        # Maintain canonical ROI once
        if self._image_roi is None and hasattr(self, 'roi_widget'):
            try:
                self._image_roi = self.get_roi()
            except Exception:
                self._image_roi = None

        # Update color bar to match viewport height (visible image area)
        if self.current_settings:
            vp_h = max(1, self.image_view.viewport().height())
            self.colorbar.setFixedHeight(vp_h)
            self.colorbar.update_values(
                min_val=self.current_settings.get("min_intensity", 0),
                max_val=self.current_settings.get("max_intensity", 1),
                cmap_name=self.current_settings.get("lut", "nipy_spectral")
            )

        # Update scale factor and ROI overlay geometry to match viewport
        try:
            total_scale = self.image_view.total_scale()
            self.pixmap_scale_factor = 1.0 / total_scale if total_scale > 0 else 1.0
        except Exception:
            self.pixmap_scale_factor = 1.0

        if hasattr(self, 'roi_widget'):
            vp = self.image_view.viewport().rect()
            self.roi_widget.setGeometry(vp)
            # Reapply canonical image-space ROI to new mapping
            if self._image_roi is not None:
                self.update_roi_display(self._image_roi)

    # --- Zoom API ---
    def zoom_in(self):
        if hasattr(self, 'image_view'):
            self.image_view.zoom_in()
        self._rescale_ui()

    def zoom_out(self):
        if hasattr(self, 'image_view'):
            self.image_view.zoom_out()
        self._rescale_ui()

    def zoom_home(self):
        # Reset to default (fit-to-viewport)
        if hasattr(self, 'image_view'):
            self.image_view.zoom_home()
        self._rescale_ui()

    def _sync_overlay_to_view(self):
        """Reposition ROI overlay to match current viewport and redraw ROI rectangle."""
        if not hasattr(self, 'image_view') or not hasattr(self, 'roi_widget'):
            return
        self.roi_widget.setGeometry(self.image_view.viewport().rect())
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