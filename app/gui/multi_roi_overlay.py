from typing import Optional
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QRect, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QCursor, QMouseEvent

from .roi_manager import ROIManager, ROI

class MultiROIOverlay(QWidget):
    """A transparent overlay that draws multiple ROIs on top of the preview viewport.
    ROIs are defined in image-space coordinates and mapped into viewport coords by
    calling mapFromScene() on the associated view.
    """
    def __init__(self, parent: QWidget, view, manager: ROIManager):
        super().__init__(parent)
        self._view = view
        self._mgr = manager
        # Start as interactive; we'll only act on the currently active ROI
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Interaction state
        self._active_roi_id: Optional[int] = None
        self._drag_mode: Optional[str] = None  # None, 'move', 'l','r','t','b','tl','tr','bl','br'
        self._press_scene_pos: Optional[QPointF] = None
        self._orig_rect: Optional[QRect] = None
        self._handle_px = 8
        self._edge_margin_px = 6
        self._crop_widget: Optional[QWidget] = None

    # Emitted when an ROI geometry changes due to interaction
    geometryChanged = pyqtSignal(int, QRect)
    # Emitted when the active ROI selection changes (None means deselected)
    activeRoiChanged = pyqtSignal(object)

    def set_manager(self, manager: ROIManager):
        self._mgr = manager
        self.update()

    def set_active_roi(self, roi_id: Optional[int]):
        if self._active_roi_id == roi_id:
            return
        self._active_roi_id = roi_id
        self.update()
        try:
            self.activeRoiChanged.emit(roi_id)
        except Exception:
            pass

    def get_active_roi_id(self) -> Optional[int]:
        return self._active_roi_id

    def set_crop_widget(self, widget: QWidget):
        """Set the Cropping Window widget to forward non-ROI interactions to it."""
        self._crop_widget = widget

    # ---- helpers ----
    def _get_active_roi(self) -> Optional[ROI]:
        if self._mgr is None or self._active_roi_id is None:
            return None
        return self._mgr.get_roi(self._active_roi_id)

    def _hit_test_roi(self, roi: ROI, pos) -> Optional[str]:
        """Return a drag mode if pos hits edges/handles of the given roi, else None.
        Modes: 'move' for edges, 'tl','tr','bl','br' for corners.
        """
        if roi is None or roi.rect is None:
            return None
        vr = self._view_rect_for_roi(roi)
        if vr is None:
            return None
        hs = self._handle_px
        # Corners
        corners = {
            'tl': QRect(vr.topLeft().x()-hs//2, vr.topLeft().y()-hs//2, hs, hs),
            'tr': QRect(vr.topRight().x()-hs//2, vr.topRight().y()-hs//2, hs, hs),
            'bl': QRect(vr.bottomLeft().x()-hs//2, vr.bottomLeft().y()-hs//2, hs, hs),
            'br': QRect(vr.bottomRight().x()-hs//2, vr.bottomRight().y()-hs//2, hs, hs),
        }
        for k, r in corners.items():
            if r.contains(pos):
                return k
        # Edges (for MOVE)
        m = self._edge_margin_px
        left = QRect(vr.left()-m, vr.top()+m, 2*m, max(1, vr.height()-2*m))
        right = QRect(vr.right()-m, vr.top()+m, 2*m, max(1, vr.height()-2*m))
        top = QRect(vr.left()+m, vr.top()-m, max(1, vr.width()-2*m), 2*m)
        bottom = QRect(vr.left()+m, vr.bottom()-m, max(1, vr.width()-2*m), 2*m)
        if left.contains(pos) or right.contains(pos) or top.contains(pos) or bottom.contains(pos):
            return 'move'
        return None

    def _hit_test_any(self, pos) -> Optional[tuple[int, str]]:
        """Return (roi_id, mode) if pos hits any ROI edge/handle, else None.
        Prefers later ROIs (assumed top-most).
        """
        if self._mgr is None:
            return None
        # Iterate in reverse order to prefer top-most drawn
        for roi in reversed(self._mgr.rois):
            if not roi.visible or roi.rect is None:
                continue
            mode = self._hit_test_roi(roi, pos)
            if mode is not None:
                return (roi.id, mode)
        return None

    def _view_rect_for_roi(self, roi: ROI) -> Optional[QRect]:
        if roi is None or roi.rect is None:
            return None
        tl = self._view.mapFromScene(QPointF(roi.rect.topLeft()))
        br = self._view.mapFromScene(QPointF(roi.rect.bottomRight()))
        return QRect(tl, br).normalized()

    def _is_on_crop_handle(self, pos) -> bool:
        """Return True if the given overlay-local pos is on a Cropping Window handle.
        This prioritizes Cropping Window resizing over ROI edits.
        """
        if self._crop_widget is None:
            return False
        try:
            # If crop widget is hidden, treat as not present
            if hasattr(self._crop_widget, 'isVisible') and not self._crop_widget.isVisible():
                return False
            # Map overlay-local pos to crop widget-local pos (siblings under the same parent)
            pos_in_parent = self.mapToParent(pos)
            pos_in_crop = self._crop_widget.mapFromParent(pos_in_parent)
            handles = getattr(self._crop_widget, 'handles', {})
            for rect in handles.values():
                if rect.contains(pos_in_crop):
                    return True
        except Exception:
            return False
        return False

    def paintEvent(self, event):
        if self._mgr is None or self._view is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for roi in self._mgr.rois:
            if not roi.visible:
                continue
            color = QColor(roi.color)
            color.setAlpha(200)
            # Active ROI: keep its color, but draw dotted and slightly thicker
            if roi.id == self._active_roi_id:
                pen = QPen(color)
                pen.setStyle(Qt.PenStyle.DotLine)
                pen.setWidth(3)
            else:
                pen = QPen(color)
                pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            if roi.shape in ('rect', 'ellipse') and roi.rect is not None:
                tl = self._view.mapFromScene(QPointF(roi.rect.topLeft()))
                br = self._view.mapFromScene(QPointF(roi.rect.bottomRight()))
                vr = QRect(tl, br)
                if roi.shape == 'rect':
                    p.drawRect(vr)
                else:
                    p.drawEllipse(vr)
                # Draw handles if active
                if roi.id == self._active_roi_id:
                    p.setBrush(QBrush(QColor(255,255,255)))
                    hs = self._handle_px
                    for pt in [vr.topLeft(), vr.topRight(), vr.bottomLeft(), vr.bottomRight()]:
                        p.drawRect(QRect(pt.x()-hs//2, pt.y()-hs//2, hs, hs))
            elif roi.shape in ('freehand', 'contour') and roi.points:
                pts = [self._view.mapFromScene(QPointF(pt)) for pt in roi.points]
                if len(pts) > 1:
                    for i in range(len(pts) - 1):
                        p.drawLine(pts[i], pts[i+1])
            elif roi.shape == 'text' and roi.rect is not None and roi.label:
                # Draw text at the rect's top-left in view coordinates
                tl = self._view.mapFromScene(QPointF(roi.rect.topLeft()))
                # Slight shadow for visibility
                p.setPen(QPen(QColor(0,0,0,160)))
                p.drawText(int(tl.x())+1, int(tl.y())+1, roi.label)
                p.setPen(QPen(color))
                p.drawText(int(tl.x()), int(tl.y()), roi.label)
        p.end()

    # ---- interaction ----
    def _hit_test(self, pos) -> Optional[str]:
        roi = self._get_active_roi()
        if roi is None or roi.rect is None:
            return None
        # If hovering on Cropping Window handle, don't intercept
        if self._is_on_crop_handle(pos):
            return None
        vr = self._view_rect_for_roi(roi)
        if vr is None:
            return None
        hs = self._handle_px
        # Corners
        corners = {
            'tl': QRect(vr.topLeft().x()-hs//2, vr.topLeft().y()-hs//2, hs, hs),
            'tr': QRect(vr.topRight().x()-hs//2, vr.topRight().y()-hs//2, hs, hs),
            'bl': QRect(vr.bottomLeft().x()-hs//2, vr.bottomLeft().y()-hs//2, hs, hs),
            'br': QRect(vr.bottomRight().x()-hs//2, vr.bottomRight().y()-hs//2, hs, hs),
        }
        for k, r in corners.items():
            if r.contains(pos):
                return k
        # Edges (use for MOVE, not resize)
        m = self._edge_margin_px
        left = QRect(vr.left()-m, vr.top()+m, 2*m, max(1, vr.height()-2*m))
        right = QRect(vr.right()-m, vr.top()+m, 2*m, max(1, vr.height()-2*m))
        top = QRect(vr.left()+m, vr.top()-m, max(1, vr.width()-2*m), 2*m)
        bottom = QRect(vr.left()+m, vr.bottom()-m, max(1, vr.width()-2*m), 2*m)
        if left.contains(pos) or right.contains(pos) or top.contains(pos) or bottom.contains(pos):
            return 'move'
        # Inside: do not intercept (let panning/underlying widgets handle)
        return None

    def _forward_mouse_event(self, ev: QMouseEvent):
        """Forward a mouse event to the cropping widget if present, else to the view's viewport.
        Coordinate systems are translated accordingly.
        """
        target = self._crop_widget if self._crop_widget is not None else self._view.viewport()
        # Map overlay-local position to target-local position
        # Start with position in viewport coordinates
        pos_in_viewport = self.mapToParent(ev.position().toPoint())
        if target is self._view.viewport():
            local_pos = pos_in_viewport
        else:
            local_pos = target.mapFromParent(pos_in_viewport)
        # Construct a new event for the target (use localPos-only overload)
        new_ev = QMouseEvent(
            ev.type(),
            QPointF(local_pos),
            ev.button(),
            ev.buttons(),
            ev.modifiers()
        )
        QApplication.sendEvent(target, new_ev)

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            # Forward other buttons to underlying (e.g., middle for pan)
            self._forward_mouse_event(ev)
            return
        # If hovering on Cropping Window handle, let it handle first
        if self._is_on_crop_handle(ev.position().toPoint()):
            self._forward_mouse_event(ev)
            return
        # Hit-test against any ROI edges/handles and select that ROI if found
        hit = self._hit_test_any(ev.position().toPoint())
        if hit is None:
            # Not on any ROI edge/handle: deselect and forward
            if self._active_roi_id is not None:
                self.set_active_roi(None)
            self._forward_mouse_event(ev)
            return
        rid, mode = hit
        # Select ROI and start interaction
        target = self._mgr.get_roi(rid) if self._mgr else None
        self.set_active_roi(rid)
        self._drag_mode = mode
        self._press_scene_pos = self._view.mapToScene(ev.position().toPoint())
        self._orig_rect = QRect(target.rect) if target and target.rect else None
        ev.accept()

    def mouseMoveEvent(self, ev):
        roi = self._get_active_roi()
        if roi is None or roi.rect is None:
            # Update cursor based on any ROI under the cursor for better affordance
            hit = self._hit_test_any(ev.position().toPoint())
            if hit is not None:
                _, mode = hit
                cursor = Qt.CursorShape.ArrowCursor
                if mode in ('tl','br'):
                    cursor = Qt.CursorShape.SizeFDiagCursor
                elif mode in ('tr','bl'):
                    cursor = Qt.CursorShape.SizeBDiagCursor
                elif mode == 'move':
                    cursor = Qt.CursorShape.SizeAllCursor
                self.setCursor(QCursor(cursor))
            # Forward to underlying for panning/hover
            self._forward_mouse_event(ev)
            return
        # Update cursor when not dragging
        if self._drag_mode is None:
            # Prefer active ROI, else any ROI for hover feedback
            mode = self._hit_test(ev.position().toPoint())
            if mode is None:
                any_hit = self._hit_test_any(ev.position().toPoint())
                mode = any_hit[1] if any_hit is not None else None
            cursor = Qt.CursorShape.ArrowCursor
            if mode in ('tl','br'):
                cursor = Qt.CursorShape.SizeFDiagCursor
            elif mode in ('tr','bl'):
                cursor = Qt.CursorShape.SizeBDiagCursor
            elif mode == 'move':
                cursor = Qt.CursorShape.SizeAllCursor
            self.setCursor(QCursor(cursor))
            # Forward move to underlying to support hover behaviors/panning
            self._forward_mouse_event(ev)
            return

        # Dragging: compute delta in scene space
        scene_pos = self._view.mapToScene(ev.position().toPoint())
        dx = int(scene_pos.x() - self._press_scene_pos.x()) if self._press_scene_pos else 0
        dy = int(scene_pos.y() - self._press_scene_pos.y()) if self._press_scene_pos else 0
        r = QRect(self._orig_rect)
        mode = self._drag_mode
        if mode == 'move':
            r.translate(dx, dy)
        else:
            if mode in ('l','tl','bl'):
                r.setLeft(r.left() + dx)
            if mode in ('r','tr','br'):
                r.setRight(r.right() + dx)
            if mode in ('t','tl','tr'):
                r.setTop(r.top() + dy)
            if mode in ('b','bl','br'):
                r.setBottom(r.bottom() + dy)
        # Normalize to avoid inverted rects
        r = r.normalized()
        roi.rect = r
        self.update()
        self.geometryChanged.emit(roi.id, QRect(roi.rect))
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_mode = None
            self._press_scene_pos = None
            self._orig_rect = None
            ev.accept()
            return
        # Forward other button releases to underlying
        self._forward_mouse_event(ev)
