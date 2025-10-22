# --- CORRECTED FILE: gui/preview_panel.py ---

import os
import cv2
import numpy as np
from processing.image_processor import create_gradient_image
from PyQt6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QPushButton, QHBoxLayout, QApplication,
                             QSizePolicy, QFileDialog, QGroupBox, QFormLayout, QSpinBox,
                             QGraphicsView, QGraphicsScene, QInputDialog)
from PyQt6.QtGui import QPixmap, QImage, QMouseEvent, QPainter, QIcon, QPen, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QTimer, QPoint, QPointF, QSize

from .interactive_roi import InteractiveROI
from .roi_manager import ROIManager, ROI
from .multi_roi_overlay import MultiROIOverlay
from .outline_overlay import OutlineOverlay


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
        # Preserve current viewing state based on the viewport's top-left in scene coords
        old_total_scale = self.transform().m11()
        saved_tl_scene = None
        if preserve_center and self.has_image():
            saved_tl_scene = self.mapToScene(self.viewport().rect().topLeft())

        # Update pixmap and scene rect (keeps item at 0,0)
        self._pixmap_item.setPixmap(pixmap)
        self.scene().setSceneRect(0, 0, pixmap.width(), pixmap.height())

        # Recompute base fit scale for accurate Home behavior
        self._update_fit_scale()

        # Recalculate zoom_factor so that total scale remains exactly the same
        if self._base_fit_scale > 0:
            self._zoom_factor = max(self._min_zoom, min(self._max_zoom, old_total_scale / self._base_fit_scale))
        # Reapply transform at the same absolute scale
        self._apply_zoom()

        # Restore the viewport top-left scene point precisely to avoid drift
        if preserve_center and saved_tl_scene is not None:
            # Determine current viewport size in scene units at the applied scale
            current_scene_rect = self.mapToScene(self.viewport().rect()).boundingRect()
            target_center = saved_tl_scene + current_scene_rect.center() - current_scene_rect.topLeft()
            self.centerOn(target_center)

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
    roiListUpdated = pyqtSignal(list)  # list of dict summaries
    activeRoiChanged = pyqtSignal(int)  # id of newly active ROI

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
        # Suppress overlay/ROI sync while the view is updating to avoid jitter
        self._updating_view = False
        self._overlay_defer_timer = QTimer(self)
        self._overlay_defer_timer.setSingleShot(True)
        self._overlay_defer_timer.timeout.connect(self._sync_overlay_to_view)
        # Guard to prevent feedback loops when programmatically updating the ROI
        self._suppress_roi_signal = False
        # Debounce timer to finalize ROI redraw after window resizing
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_settled)
        # ROI clipboard for copy/paste
        self._roi_clipboard = None

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
        image_and_bar_layout.addWidget(self.image_view, 1)

        # 2. COLOR BAR LABEL
        self.colorbar = LiveColorBar()
        self.colorbar.setFixedWidth(60)  # Wide enough for text like "20000"
        self.colorbar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # Hide colorbar until an image is actually loaded
        self.colorbar.setVisible(False)
        image_and_bar_layout.addWidget(self.colorbar, 0)

        # Add the horizontal layout to the main panel's vertical layout and let it take extra space
        top_level_layout.addLayout(image_and_bar_layout, 1)

        # 2a. ZOOM CONTROLS
        zoom_layout = QHBoxLayout()
        self.zoom_out_btn = QPushButton("")
        self.zoom_home_btn = QPushButton("")
        self.zoom_in_btn = QPushButton("")
        # Use square buttons with icon-only layout
        for b in (self.zoom_out_btn, self.zoom_home_btn, self.zoom_in_btn):
            b.setFixedSize(36, 36)
            b.setIconSize(QSize(22, 22))
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        # Apply custom-drawn icons
        self.zoom_out_btn.setIcon(self._make_zoom_icon(plus=False))
        self.zoom_out_btn.setToolTip("Zoom Out")
        self.zoom_in_btn.setIcon(self._make_zoom_icon(plus=True))
        self.zoom_in_btn.setToolTip("Zoom In")
        self.zoom_home_btn.setIcon(self._make_home_icon())
        self.zoom_home_btn.setToolTip("Reset (Home)")
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_home_btn.clicked.connect(self.zoom_home)
        zoom_layout.addWidget(self.zoom_out_btn)
        zoom_layout.addWidget(self.zoom_home_btn)
        zoom_layout.addWidget(self.zoom_in_btn)
        zoom_layout.addStretch(1)
        top_level_layout.addLayout(zoom_layout)

        # Multi-ROI layer (annotations)
        self.roi_manager = ROIManager()
        self.multi_roi_overlay = MultiROIOverlay(self.image_view.viewport(), self.image_view, self.roi_manager)
        self.multi_roi_overlay.setGeometry(self.image_view.viewport().rect())
        # Keep main panel in sync when user edits ROI geometry in overlay
        self.multi_roi_overlay.geometryChanged.connect(self._on_multi_roi_geometry_changed)
        # When overlay selection changes (including deselect), update active ROI
        try:
            self.multi_roi_overlay.activeRoiChanged.connect(self._on_overlay_active_roi_changed)
        except Exception:
            pass

        # Animal Outline passive overlay (below ROI overlay, above crop shading)
        self.outline_overlay = OutlineOverlay(self.image_view.viewport(), self.image_view)
        self.outline_overlay.setGeometry(self.image_view.viewport().rect())

    # The interactive ROI widget is a transparent overlay on the graphics view's viewport.
        self.roi_widget = InteractiveROI(self.image_view.viewport())
        self.roi_widget.roiChanged.connect(self._on_roi_drawn)  # Emits the raw widget rect
        # Hide crop overlay until an image is loaded
        self.roi_widget.setVisible(False)
        # Allow ROI overlay to forward events to cropping widget when not editing ROI
        try:
            self.multi_roi_overlay.set_crop_widget(self.roi_widget)
        except Exception:
            pass
        # Keep ROI overlay in sync when panning via scrollbars (connect after ROI exists)
        self.image_view.horizontalScrollBar().valueChanged.connect(self._sync_overlay_to_view)
        self.image_view.verticalScrollBar().valueChanged.connect(self._sync_overlay_to_view)
        # Keep ROI overlay on top to allow selection-by-edge even when no ROI is active;
        # overlay forwards non-ROI interactions to the cropping widget
        # Layer order: image < roi_widget (shading) < outline_overlay < multi_roi_overlay
        try:
            self.roi_widget.lower()
            self.outline_overlay.raise_()
            self.multi_roi_overlay.raise_()
        except Exception:
            self.multi_roi_overlay.raise_()

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

        # 4. NAVIGATION BUTTONS
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
        button_layout.addStretch(1)  # Pushes the "Select" button to the far right
        button_layout.addWidget(self.select_button)
        top_level_layout.addLayout(button_layout)

    def _make_zoom_icon(self, plus: bool = True) -> QIcon:
        """Create a magnifying-glass icon with + or - drawn programmatically (no external assets)."""
        size = 64  # draw large, then scale via iconSize
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Colors
        pen = QPen(QColor(230, 230, 230))
        pen.setWidthF(size * 0.06)
        p.setPen(pen)
        # Lens
        center = QPoint(int(size * 0.42), int(size * 0.42))
        radius = int(size * 0.28)
        p.drawEllipse(center, radius, radius)
        # Handle (45 degrees)
        handle_len = int(size * 0.24)
        # Start from lens edge at 45 degrees
        from PyQt6.QtCore import QPointF
        import math
        angle = math.radians(45)
        start = QPointF(center.x() + radius / math.sqrt(2), center.y() + radius / math.sqrt(2))
        end = QPointF(start.x() + handle_len * math.cos(angle), start.y() + handle_len * math.sin(angle))
        p.drawLine(start, end)
        # Plus/Minus inside lens
        inner_w = int(radius * 1.0)
        cx, cy = center.x(), center.y()
        p.drawLine(QPoint(cx - inner_w//2, cy), QPoint(cx + inner_w//2, cy))
        if plus:
            p.drawLine(QPoint(cx, cy - inner_w//2), QPoint(cx, cy + inner_w//2))
        p.end()
        return QIcon(pm)

    def _make_home_icon(self) -> QIcon:
        """Create a simple home/house icon programmatically."""
        size = 64
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(230, 230, 230))
        pen.setWidthF(size * 0.06)
        p.setPen(pen)
        # House base
        margin = int(size * 0.18)
        base_top = int(size * 0.48)
        p.drawRect(margin, base_top, size - 2*margin, int(size * 0.30))
        # Roof (triangle)
        from PyQt6.QtCore import QPoint
        roof_apex = QPoint(size//2, int(size * 0.22))
        left_base = QPoint(margin, base_top)
        right_base = QPoint(size - margin, base_top)
        p.drawLine(left_base, roof_apex)
        p.drawLine(roof_apex, right_base)
        p.drawLine(right_base, left_base)
        p.end()
        return QIcon(pm)

        # Add a stretch to the main vertical layout (keeps content aligned to top)

    def update_roi_display(self, roi: QRect):
        """Update the on-screen ROI overlay based on a given image-space ROI.
        Uses view mapping to handle zoom and pan correctly.
        """
        if self._updating_view:
            # Defer ROI updates until the view settles to prevent visible jitter
            self._overlay_defer_timer.start(0)
            return
        # Ensure required widgets exist before mapping
        if not hasattr(self, 'image_view') or not hasattr(self, 'roi_widget'):
            self._overlay_defer_timer.start(0)
            return
        self._image_roi = QRect(roi) if roi is not None else None
        if self._image_roi is None:
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
        self._updating_view = True
        try:
            if hasattr(self, 'image_view'):
                if not self.image_view.has_image():
                    # First time: set and fit
                    self.image_view.set_pixmap(pixmap)
                    # Show colorbar now that an image exists
                    self.colorbar.setVisible(True)
                else:
                    # Subsequent updates (e.g., intensity/LUT changes): preserve zoom/center
                    self.image_view.update_pixmap(pixmap, preserve_center=True)
            # Show/hide cropping overlay based on settings and update mask opacity
            try:
                show_crop = bool(self.current_settings.get("show_crop_overlay", True))
                if hasattr(self, 'roi_widget'):
                    # Only show when an image is present
                    self.roi_widget.setVisible(show_crop and self.image_view.has_image())
                    if hasattr(self.roi_widget, 'setOutsideOpacity'):
                        opacity_pct = int(self.current_settings.get("crop_mask_opacity", 50))
                        self.roi_widget.setOutsideOpacity(opacity_pct)
            except Exception:
                pass
            # Update outline overlay (visibility/color/threshold/source) and recompute if needed
            try:
                self._apply_outline_settings()
            except Exception:
                pass
            # Update colorbar and schedule overlay sync once
            self._rescale_ui()
        finally:
            self._updating_view = False
        # After view settles, sync overlay exactly once to avoid flicker
        self._overlay_defer_timer.start(0)

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
        if not hasattr(self, 'image_view'):
            return
        # Toggle colorbar visibility based on whether an image is loaded
        has_img = self.image_view.has_image() and hasattr(self, 'original_pixmap') and not self.original_pixmap.isNull()
        if hasattr(self, 'colorbar'):
            self.colorbar.setVisible(bool(has_img))
        if not has_img:
            return


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
            # Resize overlays to match viewport
            if hasattr(self, 'multi_roi_overlay'):
                self.multi_roi_overlay.setGeometry(vp)
            self.roi_widget.setGeometry(vp)
            if hasattr(self, 'outline_overlay'):
                self.outline_overlay.setGeometry(vp)
            # Constrain crop shading to image bounds within the viewport
            self._update_crop_image_rect()
            # Reapply canonical image-space ROI to new mapping
            if self._image_roi is not None:
                self.update_roi_display(self._image_roi)
        # Remap outline to viewport coordinates after UI rescale
        try:
            if hasattr(self, 'outline_overlay'):
                self.outline_overlay.remap_to_viewport()
        except Exception:
            pass

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
        if self._updating_view:
            # Defer until the view finishes updating transforms/scrollbars
            self._overlay_defer_timer.start(0)
            return
        if not hasattr(self, 'image_view') or not hasattr(self, 'roi_widget'):
            return
        vp = self.image_view.viewport().rect()
        if hasattr(self, 'multi_roi_overlay'):
            self.multi_roi_overlay.setGeometry(vp)
            self.multi_roi_overlay.update()
        self.roi_widget.setGeometry(vp)
        if hasattr(self, 'outline_overlay'):
            self.outline_overlay.setGeometry(vp)
            try:
                self.outline_overlay.remap_to_viewport()
            except Exception:
                pass
        # Update crop shading area to align with current image position/zoom
        self._update_crop_image_rect()
        if self._image_roi is not None:
            self.update_roi_display(self._image_roi)

    def _update_crop_image_rect(self):
        """Compute the image's rectangle in viewport coordinates and pass it to the crop overlay.
        Ensures the shaded area only covers the image, not the entire viewport.
        Hides the crop overlay when no image is loaded.
        """
        try:
            if not hasattr(self, 'image_view') or not hasattr(self, 'roi_widget'):
                return
            if not self.image_view.has_image():
                # No image: disable crop mask region and hide overlay
                try:
                    self.roi_widget.setImageRect(None)
                except Exception:
                    pass
                self.roi_widget.setVisible(False)
                return
            # Map scene (0,0,w,h) to viewport to get where the image lies visually
            scene_rect = self.image_view.scene().sceneRect()
            tl = self.image_view.mapFromScene(QPointF(scene_rect.topLeft()))
            br = self.image_view.mapFromScene(QPointF(scene_rect.bottomRight()))
            img_rect = QRect(tl, br).normalized()
            # Intersect with viewport bounds for safety
            img_rect = img_rect.intersected(self.image_view.viewport().rect())
            try:
                self.roi_widget.setImageRect(img_rect)
            except Exception:
                pass
            # Respect current setting for visibility
            show_crop = bool(self.current_settings.get("show_crop_overlay", True)) if self.current_settings else True
            self.roi_widget.setVisible(show_crop)
        except Exception:
            # Fail-safe: don't crash UI on mapping errors
            pass

    def _apply_outline_settings(self):
        if not hasattr(self, 'outline_overlay'):
            return
        # Read settings with defaults
        show = bool(self.current_settings.get("show_animal_outline", False)) if self.current_settings else False
        color_val = self.current_settings.get("animal_outline_color", (0, 255, 0, 255)) if self.current_settings else (0, 255, 0, 255)
        if isinstance(color_val, (tuple, list)) and len(color_val) >= 3:
            color = QColor(int(color_val[0]), int(color_val[1]), int(color_val[2]))
        elif isinstance(color_val, str) and color_val.startswith('#'):
            color = QColor(color_val)
        else:
            color = QColor(0, 255, 0)
        thresh = int(self.current_settings.get("animal_outline_threshold", 5000)) if self.current_settings else 5000
        source = str(self.current_settings.get("animal_outline_source", 'WF')) if self.current_settings else 'WF'
        # Update image paths and params
        self.outline_overlay.set_image_paths(getattr(self, '_wf_path', None), getattr(self, '_fl_path', None))
        self.outline_overlay.set_params(visible=show, color=color, threshold=thresh, source=source)
        # Recompute/mapping
        self.outline_overlay.update_outline()

    # --- Multi-ROI Management API ---
    def add_rectangle_roi(self):
        """Add a rectangle ROI centered in the current view, with an auto name and color."""
        if not hasattr(self, 'image_view') or not self.image_view.has_image():
            return
        # Determine a default rect: 30% of image size, centered in scene
        scene_rect = self.image_view.scene().sceneRect()
        iw, ih = scene_rect.width(), scene_rect.height()
        rw, rh = int(iw * 0.3), int(ih * 0.3)
        cx, cy = scene_rect.center().x(), scene_rect.center().y()
        rect = QRect(int(cx - rw/2), int(cy - rh/2), rw, rh)
        # Choose a color from a small palette cycling
        palette = [QColor('#ff5252'), QColor('#ffb74d'), QColor('#ffd54f'), QColor('#81c784'), QColor('#64b5f6'), QColor('#9575cd')]
        idx = len(self.roi_manager.rois) % len(palette)
        name = f"ROI {len(self.roi_manager.rois)+1}"
        roi = ROI(shape='rect', name=name, color=palette[idx], rect=rect)
        self.roi_manager.add_roi(roi)
        self.multi_roi_overlay.update()
        self.roiListUpdated.emit(self.roi_manager.list_summary())
        # Make the new ROI active and bring overlay to front for immediate editing
        self.set_active_roi(roi.id)
        self.activeRoiChanged.emit(roi.id)

    def set_roi_visibility(self, roi_id: int, visible: bool):
        self.roi_manager.set_roi_visibility(roi_id, visible)
        self.multi_roi_overlay.update()
        self.roiListUpdated.emit(self.roi_manager.list_summary())

    def rename_roi(self, roi_id: int, new_name: str):
        self.roi_manager.rename_roi(roi_id, new_name)
        self.roiListUpdated.emit(self.roi_manager.list_summary())

    def remove_roi(self, roi_id: int):
        self.roi_manager.remove_roi(roi_id)
        self.multi_roi_overlay.update()
        self.roiListUpdated.emit(self.roi_manager.list_summary())

    def change_roi_color(self, roi_id: int, color: QColor):
        """Update the color of an ROI and refresh overlay + list."""
        self.roi_manager.set_roi_color(roi_id, color)
        self.multi_roi_overlay.update()
        self.roiListUpdated.emit(self.roi_manager.list_summary())

    def set_active_roi(self, roi_id: int):
        """Mark an ROI as active for interactive editing in the overlay.
        Accepts -1 or None to clear selection.
        """
        # Normalize None/-1 to None
        if roi_id is None or (isinstance(roi_id, int) and roi_id < 0):
            norm_id = None
        else:
            norm_id = roi_id
        try:
            self.multi_roi_overlay.set_active_roi(norm_id)
            # When an ROI is active, bring overlay to front; otherwise prioritize cropping window
            # Always keep overlay on top; it forwards to cropping widget when needed
            self.multi_roi_overlay.raise_()
            # Deactivate cropping window editing when an ROI is active (ROI-like behavior symmetry)
            if hasattr(self, 'roi_widget') and hasattr(self.roi_widget, 'setActive'):
                self.roi_widget.setActive(False)
        except Exception:
            pass

    def _on_overlay_active_roi_changed(self, roi_id):
        """Propagate overlay selection changes to external listeners and adjust z-order."""
        self.set_active_roi(roi_id)
        try:
            # Re-emit for MainWindow -> SettingsPanel selection sync
            self.activeRoiChanged.emit(-1 if roi_id is None else roi_id)
        except Exception:
            pass

    # --- Edit operations for ROIs ---
    def select_next_roi(self):
        if not self.roi_manager.rois:
            return
        current_id = self.multi_roi_overlay.get_active_roi_id() if hasattr(self.multi_roi_overlay, 'get_active_roi_id') else None
        ids = [r.id for r in self.roi_manager.rois]
        if current_id in ids:
            idx = ids.index(current_id)
            next_id = ids[(idx + 1) % len(ids)]
        else:
            next_id = ids[0]
        self.set_active_roi(next_id)
        try:
            self.activeRoiChanged.emit(next_id)
        except Exception:
            pass

    def copy_active_roi(self):
        rid = self.multi_roi_overlay.get_active_roi_id() if hasattr(self.multi_roi_overlay, 'get_active_roi_id') else None
        if rid is None:
            return
        roi = self.roi_manager.get_roi(rid)
        if not roi:
            return
        # Shallow snapshot (color, rect, points, shape, label, name)
        self._roi_clipboard = {
            'shape': roi.shape,
            'name': roi.name,
            'color': QColor(roi.color),
            'rect': QRect(roi.rect) if roi.rect else None,
            'points': list(roi.points) if roi.points else None,
            'label': roi.label if hasattr(roi, 'label') else None,
        }

    def cut_active_roi(self):
        rid = self.multi_roi_overlay.get_active_roi_id() if hasattr(self.multi_roi_overlay, 'get_active_roi_id') else None
        if rid is None:
            return
        self.copy_active_roi()
        self.remove_roi(rid)

    def paste_roi(self):
        if not self._roi_clipboard:
            return
        data = self._roi_clipboard
        # Offset pasted geometry a bit
        rect = QRect(data['rect']) if data.get('rect') else None
        if rect is not None:
            rect.translate(10, 10)
        new_name = f"Copy of {data['name']}" if data.get('name') else "ROI"
        new_roi = ROI(
            shape=data.get('shape', 'rect'),
            name=new_name,
            color=data.get('color', QColor('#64b5f6')),
            rect=rect,
            points=list(data['points']) if data.get('points') else None,
        )
        if hasattr(new_roi, 'label') and data.get('label'):
            new_roi.label = data['label']
        self.roi_manager.add_roi(new_roi)
        self.multi_roi_overlay.update()
        self.roiListUpdated.emit(self.roi_manager.list_summary())
        self.set_active_roi(new_roi.id)
        try:
            self.activeRoiChanged.emit(new_roi.id)
        except Exception:
            pass

    def add_text_annotation(self):
        if not hasattr(self, 'image_view') or not self.image_view.has_image():
            return
        text, ok = QInputDialog.getText(self, "Add Text Annotation", "Text:")
        if not ok or not text.strip():
            return
        # Place at center of current scene viewport
        scene_rect = self.image_view.scene().sceneRect()
        cx, cy = int(scene_rect.center().x()), int(scene_rect.center().y())
        rect = QRect(cx, cy, 1, 1)  # point-like anchor
        palette = [QColor('#ff5252'), QColor('#ffb74d'), QColor('#ffd54f'), QColor('#81c784'), QColor('#64b5f6'), QColor('#9575cd')]
        idx = len(self.roi_manager.rois) % len(palette)
        name = f"Text {len(self.roi_manager.rois)+1}"
        roi = ROI(shape='text', name=name, color=palette[idx], rect=rect)
        roi.label = text.strip()
        self.roi_manager.add_roi(roi)
        self.multi_roi_overlay.update()
        self.roiListUpdated.emit(self.roi_manager.list_summary())
        self.set_active_roi(roi.id)
        try:
            self.activeRoiChanged.emit(roi.id)
        except Exception:
            pass

    def _on_multi_roi_geometry_changed(self, roi_id: int, rect: QRect):
        """When user moves/resizes an ROI on the overlay, refresh the list for UI sync."""
        self.roiListUpdated.emit(self.roi_manager.list_summary())

    def _on_resize_settled(self):
        """After resize ends, snap the ROI overlay exactly to settings panel values if available."""
        # Use the canonical image-space ROI as the single source of truth
        if self._image_roi is not None:
            self.update_roi_display(self._image_roi)

    def set_file_info(self, wf_path: str, fl_path: str):
        self.wf_path_label.setText(os.path.basename(wf_path))
        self.wf_path_label.setToolTip(wf_path)
        self.fl_path_label.setText(os.path.basename(fl_path))
        self.fl_path_label.setToolTip(fl_path)
        # Track actual paths for overlays
        self._wf_path = wf_path if wf_path and wf_path != 'N/A' else None
        self._fl_path = fl_path if fl_path and fl_path != 'N/A' else None
        try:
            if hasattr(self, 'outline_overlay'):
                self.outline_overlay.set_image_paths(self._wf_path, self._fl_path)
                self.outline_overlay.update_outline()
        except Exception:
            pass

    def _select_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select Image for Preview", "", "Tiff Files (*.tif *.tiff)")
        if filepath:
            self.requestSpecificImage.emit(filepath)