# gui/interactive_roi.py


"""Interactive ROI overlay widget.

This lightweight QWidget draws and edits a rectangular region of interest on
top of the preview image. It supports:
- Moving the ROI by dragging the interior or border
- Resizing via eight handles (corners + edges)
- Optional dimming outside the ROI

Public API:
- setActive(bool): toggles edit mode (handles and dashed border)
- setOutsideOpacity(int): sets outside dimming (0–100)
- setImageRect(QRect|None): image bounds in viewport coordinates
- setRoi(QRect): programmatically set the ROI rectangle
- roiChanged(QRect): signal emitted during live changes and on release

The widget stays fully transparent outside of shaded regions so the preview
underneath remains visible.
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor

class InteractiveROI(QWidget):
    """A custom widget for a draggable and resizable ROI rectangle."""
    
    # Signal emitted when the ROI rectangle is changed by the user.
    roiChanged = pyqtSignal(QRect)

    HANDLE_SIZE = 16 # Size of the resize handles (larger for easier grabbing)
    BORDER_THICKNESS = 6 # Clickable thickness around ROI edges for moving the ROI

    def __init__(self, parent=None):
        super().__init__(parent)
        self.roi_rect = QRect(50, 50, 200, 200) # Default starting ROI
        self.handles = {}
        self._update_handles()

        self.is_moving = False
        self.is_resizing = False
        self.active_handle = None
        self.drag_start_pos = QPoint()
        self.drag_start_rect = QRect()
        # Editable/active state similar to ROI selection behavior
        self._active = False
        # Outside mask opacity (alpha 0-255). Default ~50%
        self._outside_alpha = 128
        # Image bounds in viewport coords; when None, draw nothing
        self._image_vp_rect = None

    # Make the widget transparent so the image behind it is visible
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True) # Needed for cursor changes on hover

    # --- Public API ---
    def setActive(self, active: bool):
        """Enable or disable editing mode. When active, shows dashed outline and handles.
        When inactive, shows a subtle semi-transparent rounded rectangle and ignores edits.
        """
        if self._active == active:
            return
        self._active = active
        # When inactive, stop any ongoing drag and clear state
        if not self._active:
            self.is_moving = False
            self.is_resizing = False
            self.active_handle = None
        self.update()
    
    def isActive(self) -> bool:
        return self._active

    def setOutsideOpacity(self, percent: int):
        """Set outside dimming opacity as a percentage (0-100)."""
        try:
            p = max(0, min(100, int(percent)))
        except Exception:
            p = 50
        self._outside_alpha = int(round(p * 255 / 100))
        self.update()

    def setImageRect(self, rect):
        """Define the image area in viewport coordinates. Pass None to disable drawing."""
        if rect is None:
            self._image_vp_rect = None
        else:
            self._image_vp_rect = QRect(rect)
        self.update()

    def _is_on_border(self, pos: QPoint) -> bool:
        """Return True if 'pos' lies within a BORDER_THICKNESS band along ROI edges."""
        r = QRect(self.roi_rect)
        if r.isNull() or r.width() <= 0 or r.height() <= 0:
            return False
        # Avoid treating near-handle regions as border to prioritize resizing
        for handle_rect in self.handles.values():
            # Inflate the handle area for easier detection
            hr = QRect(handle_rect).adjusted(-4, -4, 4, 4)
            if hr.contains(pos):
                return False
        inner = r.adjusted(self.BORDER_THICKNESS, self.BORDER_THICKNESS,
                           -self.BORDER_THICKNESS, -self.BORDER_THICKNESS)
        return r.contains(pos) and not inner.contains(pos)

    def setRoi(self, rect):
        """Public method to update the ROI from outside (e.g., from spinners)."""
        if rect != self.roi_rect:
            self.roi_rect = rect
            self._update_handles()
            self.update() # Trigger a repaint
            self.roiChanged.emit(self.roi_rect)

    def _update_handles(self):
        """Calculates the positions of all resize handles based on the main ROI rect."""
        s = self.HANDLE_SIZE // 2
        r = self.roi_rect
        self.handles = {
            'top-left': QRect(r.left() - s, r.top() - s, self.HANDLE_SIZE, self.HANDLE_SIZE),
            'top-right': QRect(r.right() - s, r.top() - s, self.HANDLE_SIZE, self.HANDLE_SIZE),
            'bottom-left': QRect(r.left() - s, r.bottom() - s, self.HANDLE_SIZE, self.HANDLE_SIZE),
            'bottom-right': QRect(r.right() - s, r.bottom() - s, self.HANDLE_SIZE, self.HANDLE_SIZE),
            'top': QRect(r.center().x() - s, r.top() - s, self.HANDLE_SIZE, self.HANDLE_SIZE),
            'bottom': QRect(r.center().x() - s, r.bottom() - s, self.HANDLE_SIZE, self.HANDLE_SIZE),
            'left': QRect(r.left() - s, r.center().y() - s, self.HANDLE_SIZE, self.HANDLE_SIZE),
            'right': QRect(r.right() - s, r.center().y() - s, self.HANDLE_SIZE, self.HANDLE_SIZE),
        }

    def paintEvent(self, event):
        """Draw the cropping window visualization with dimmed outside area.
        - Outside ROI: semi-transparent black wash (slightly more opaque).
        - Inside ROI: fully clear (so the image is visible) by shading only the bands outside the ROI.
        - Border: rounded corners; dashed when active; solid when inactive.
        - Handles: only when active.
        """
        # If no image bounds are known, draw nothing (hide effect)
        if self._image_vp_rect is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1) Prepare geometry
        outside_color = QColor(0, 0, 0, self._outside_alpha)  # black with adjustable opacity
        # Only consider the image area (not the entire viewport)
        img_rect = self._image_vp_rect.intersected(self.rect())
        if img_rect.isNull():
            return
        roi_in_img = self.roi_rect.intersected(img_rect)

        # 2) Shade outside bands only (top, bottom, left, right around ROI)
        # If ROI doesn't intersect image, shade the entire image area
        if roi_in_img.isNull():
            painter.fillRect(img_rect, outside_color)
        else:
            # Top band
            if roi_in_img.top() > img_rect.top():
                top_band = QRect(img_rect.left(), img_rect.top(), img_rect.width(), roi_in_img.top() - img_rect.top())
                painter.fillRect(top_band, outside_color)
            # Bottom band
            if roi_in_img.bottom() < img_rect.bottom():
                bottom_band = QRect(img_rect.left(), roi_in_img.bottom() + 1, img_rect.width(), img_rect.bottom() - roi_in_img.bottom())
                painter.fillRect(bottom_band, outside_color)
            # Left band
            if roi_in_img.left() > img_rect.left():
                left_band = QRect(img_rect.left(), roi_in_img.top(), roi_in_img.left() - img_rect.left(), roi_in_img.height())
                painter.fillRect(left_band, outside_color)
            # Right band
            if roi_in_img.right() < img_rect.right():
                right_band = QRect(roi_in_img.right() + 1, roi_in_img.top(), img_rect.right() - roi_in_img.right(), roi_in_img.height())
                painter.fillRect(right_band, outside_color)

        # 3) Draw border around the ROI
        radius = 8
        border_color = QColor(235, 235, 235, 220)
        pen = QPen(border_color)
        if self._active:
            pen.setStyle(Qt.PenStyle.DotLine)
            pen.setWidth(3)
        else:
            pen.setStyle(Qt.PenStyle.SolidLine)
            pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if not roi_in_img.isNull():
            # Clip border drawing within image bounds
            painter.setClipRect(img_rect)
            painter.drawRoundedRect(self.roi_rect, radius, radius)

        # 4) Draw the resize handles only when active
        if self._active:
            painter.setClipRect(img_rect)
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            for handle in self.handles.values():
                painter.drawRect(handle)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
            self.drag_start_rect = QRect(self.roi_rect)

            # Prioritize handles (resize)
            for handle_name, handle_rect in self.handles.items():
                # Inflate handle hit target for better responsiveness
                hr = QRect(handle_rect).adjusted(-4, -4, 4, 4)
                if hr.contains(event.pos()):
                    # If not active yet, activate and begin resize
                    if not self._active:
                        self.setActive(True)
                    self.is_resizing = True
                    self.active_handle = handle_name
                    return

            # If inside ROI (interior or border), start moving
            if self.roi_rect.contains(event.pos()):
                if not self._active:
                    self.setActive(True)
                self.is_moving = True
                return

            # Otherwise (outside ROI), deactivate and let the view handle panning/selection
            if self._active:
                self.setActive(False)
            event.ignore()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # Update cursor on hover
        cursor = Qt.CursorShape.ArrowCursor
        if self.is_moving or self.is_resizing:
            # Handle dragging and resizing
            delta = event.pos() - self.drag_start_pos
            if self.is_moving:
                cursor = Qt.CursorShape.SizeAllCursor
                self.roi_rect = self.drag_start_rect.translated(delta)
                # If user steers over a handle while moving, switch to resizing on-the-fly
                for handle_name, handle_rect in self.handles.items():
                    hr = QRect(handle_rect).adjusted(-4, -4, 4, 4)
                    if hr.contains(event.pos()):
                        self.is_moving = False
                        self.is_resizing = True
                        self.active_handle = handle_name
                        # restart drag baseline from current pos/rect for a smooth transition
                        self.drag_start_pos = event.pos()
                        self.drag_start_rect = QRect(self.roi_rect)
                        break
            elif self.is_resizing:
                temp_rect = QRect(self.drag_start_rect)
                if 'left' in self.active_handle: temp_rect.setLeft(self.drag_start_rect.left() + delta.x())
                if 'right' in self.active_handle: temp_rect.setRight(self.drag_start_rect.right() + delta.x())
                if 'top' in self.active_handle: temp_rect.setTop(self.drag_start_rect.top() + delta.y())
                if 'bottom' in self.active_handle: temp_rect.setBottom(self.drag_start_rect.bottom() + delta.y())
                
                # To prevent inverted rectangles
                if temp_rect.width() > self.HANDLE_SIZE and temp_rect.height() > self.HANDLE_SIZE:
                    self.roi_rect = temp_rect.normalized()

            self._update_handles()
            self.update() # Trigger repaint
            # Emit live updates so the canonical image-space ROI stays current
            try:
                self.roiChanged.emit(self.roi_rect)
            except Exception:
                pass
        else:
            # Check for hover over handles to change cursor
            over_handle = False
            for handle_name, handle_rect in self.handles.items():
                if handle_rect.contains(event.pos()):
                    over_handle = True
                    if handle_name in ['top-left', 'bottom-right']: cursor = Qt.CursorShape.SizeFDiagCursor
                    elif handle_name in ['top-right', 'bottom-left']: cursor = Qt.CursorShape.SizeBDiagCursor
                    elif handle_name in ['top', 'bottom']: cursor = Qt.CursorShape.SizeVerCursor
                    elif handle_name in ['left', 'right']: cursor = Qt.CursorShape.SizeHorCursor
                    break
            if not over_handle:
                # On the ROI border: indicate move (4-direction arrows)
                if self._is_on_border(event.pos()):
                    cursor = Qt.CursorShape.SizeAllCursor
                else:
                    # Anywhere else: indicate panning is available behind
                    # Show open hand normally, closed hand if dragging outside ROI
                    if event.buttons() & Qt.MouseButton.LeftButton:
                        # Let parent view handle drag for panning
                        event.ignore()
                        cursor = Qt.CursorShape.ClosedHandCursor
                    else:
                        cursor = Qt.CursorShape.OpenHandCursor
        
        self.setCursor(cursor)
        # If we ignored the event to allow panning, don't accept further processing
        if not (self.is_moving or self.is_resizing) and not over_handle and not self._is_on_border(event.pos()) and (event.buttons() & Qt.MouseButton.LeftButton):
            return

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_moving or self.is_resizing:
                self.roiChanged.emit(self.roi_rect) # Emit final position
            self.is_moving = False
            self.is_resizing = False
            self.active_handle = None
        else:
            super().mouseReleaseEvent(event)