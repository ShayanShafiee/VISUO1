# gui/interactive_roi.py ---

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor

class InteractiveROI(QWidget):
    """A custom widget for a draggable and resizable ROI rectangle."""
    
    # Signal emitted when the ROI rectangle is changed by the user.
    roiChanged = pyqtSignal(QRect)

    HANDLE_SIZE = 10 # Size of the resize handles
    BORDER_THICKNESS = 8 # Clickable thickness around ROI edges for moving the ROI

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

    # Make the widget transparent so the image behind it is visible
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True) # Needed for cursor changes on hover

    def _is_on_border(self, pos: QPoint) -> bool:
        """Return True if 'pos' lies within a BORDER_THICKNESS band along ROI edges."""
        r = QRect(self.roi_rect)
        if r.isNull() or r.width() <= 0 or r.height() <= 0:
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
        """Draws the ROI rectangle and its handles."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw the main ROI rectangle
        pen = QPen(QColor(0, 255, 0, 200), 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawRect(self.roi_rect)

        # Draw the resize handles
        painter.setBrush(QBrush(QColor(0, 255, 0, 200)))
        for handle in self.handles.values():
            painter.drawRect(handle)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = event.pos()
            self.drag_start_rect = QRect(self.roi_rect)

            # Prioritize handles (resize)
            for handle_name, handle_rect in self.handles.items():
                if handle_rect.contains(event.pos()):
                    self.is_resizing = True
                    self.active_handle = handle_name
                    return

            # Move only when grabbing the ROI border lines (not the interior)
            if self._is_on_border(event.pos()):
                self.is_moving = True
                return

            # Otherwise, let the underlying view handle (e.g., for panning)
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