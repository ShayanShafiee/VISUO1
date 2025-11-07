#!/usr/bin/env python3
# gui/multi_roi_overlay.py

"""Interactive multi-ROI overlay layer.

Provides drawing, selecting, moving, resizing, and styling for multiple ROIs on
top of the image preview viewport. Geometry is stored in image coordinates so
ROIs remain consistent across zoom/pan operations. This widget mediates event
handling and forwards non-ROI interactions (e.g., for cropping) when no active
ROI consumes them.

Key responsibilities:
- Maintain ROI selection state and emit signals when geometry changes.
- Render different ROI shapes (rect, ellipse, contour, text) with handles.
- Support active ROI highlighting and color-coded display.

Comment style documents behavior and rationale instead of change history.
"""
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
        # Track when a crop drag/resize is in progress so we keep forwarding events
        self._crop_dragging = False

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
        Modes: 'move' for edges, 'tl','tr','bl','br' for corners. For contour/freehand,
        allow MOVE when pointer is inside the bounding box.
        """
        if roi is None:
            return None
        vr = self._view_rect_for_roi(roi)
        if vr is None:
            return None
        # For contour/freehand (no rect), allow move when inside bounding box
        if roi.shape in ('contour', 'freehand') and roi.rect is None:
            return 'move' if vr.contains(pos) else None
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
            if not roi.visible:
                continue
            mode = self._hit_test_roi(roi, pos)
            if mode is not None:
                return (roi.id, mode)
        return None

    def _view_rect_for_roi(self, roi: ROI) -> Optional[QRect]:
        if roi is None:
            return None
        if roi.rect is not None:
            tl = self._view.mapFromScene(QPointF(roi.rect.topLeft()))
            br = self._view.mapFromScene(QPointF(roi.rect.bottomRight()))
            return QRect(tl, br).normalized()
        # Fallback: use bounding rect of points for contour/freehand
        if roi.shape in ('contour', 'freehand') and roi.points:
            xs = [p.x() for p in roi.points]
            ys = [p.y() for p in roi.points]
            tl = self._view.mapFromScene(QPointF(min(xs), min(ys)))
            br = self._view.mapFromScene(QPointF(max(xs), max(ys)))
            return QRect(tl, br).normalized()
        return None

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

    def _is_on_crop_edge(self, pos) -> bool:
        """Return True if pos is on the crop rectangle edge band (not interior), excluding handles.
        This lets users select/drag the crop only from edges, not by clicking inside.
        """
        if self._crop_widget is None:
            return False
        try:
            if hasattr(self._crop_widget, 'isVisible') and not self._crop_widget.isVisible():
                return False
            # Map to crop widget local coords
            pos_in_parent = self.mapToParent(pos)
            pos_in_crop = self._crop_widget.mapFromParent(pos_in_parent)
            r = getattr(self._crop_widget, 'roi_rect', None)
            if r is None or r.isNull():
                return False
            # Exclude handle hit regions first (prefer resizing)
            handles = getattr(self._crop_widget, 'handles', {})
            for rect in handles.values():
                # Slightly inflate to avoid ambiguity with border clicks near handles
                hr = rect.adjusted(-4, -4, 4, 4)
                if hr.contains(pos_in_crop):
                    return False
            # Border band thickness (fallback default if attribute missing)
            bt = int(getattr(self._crop_widget, 'BORDER_THICKNESS', 6))
            # Improve responsiveness by ensuring a minimum band width
            if bt < 10:
                bt = 10
            inner = r.adjusted(bt, bt, -bt, -bt)
            return r.contains(pos_in_crop) and not inner.contains(pos_in_crop)
        except Exception:
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
                    # Close the polygon to avoid a missing side
                    p.drawLine(pts[-1], pts[0])
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

    def _forward_mouse_event(self, ev: QMouseEvent, allow_crop: bool = True):
        """Forward a mouse event to the cropping widget if present, else to the view's viewport.
        Coordinate systems are translated accordingly.
        """
        # Only forward to crop widget if allowed AND it exists AND is visible; otherwise forward to view
        use_crop = allow_crop and (self._crop_widget is not None) and getattr(self._crop_widget, 'isVisible', lambda: False)()
        target = self._crop_widget if use_crop else self._view.viewport()
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
            # Not on any ROI edge/handle: deselect and forward, but DO NOT give focus to crop unless on its handles
            self._forward_mouse_event(ev, allow_crop=False)
            return
        # If hovering on Cropping Window handle, let it handle first
        if self._is_on_crop_handle(ev.position().toPoint()):
            self._crop_dragging = True
            # Ensure crop becomes active
            try:
                if hasattr(self._crop_widget, 'setActive'):
                    self._crop_widget.setActive(True)
            except Exception:
                pass
            # Forward to crop widget to start resize
            self._forward_mouse_event(ev, allow_crop=True)
            return
        # If on crop edge (border), allow crop to handle move/drag; don't activate on interior
        if self._is_on_crop_edge(ev.position().toPoint()):
            self._crop_dragging = True
            # Ensure crop becomes active
            try:
                if hasattr(self._crop_widget, 'setActive'):
                    self._crop_widget.setActive(True)
            except Exception:
                pass
            self._forward_mouse_event(ev, allow_crop=True)
            return
        # Hit-test against any ROI edges/handles and select that ROI if found
        hit = self._hit_test_any(ev.position().toPoint())
        if hit is None:
            # Not on any ROI edge/handle: deselect and forward
            if self._active_roi_id is not None:
                self.set_active_roi(None)
            # Deactivate crop if it's currently active (clicking outside)
            try:
                if self._crop_widget is not None and hasattr(self._crop_widget, 'isActive') and self._crop_widget.isActive():
                    if hasattr(self._crop_widget, 'setActive'):
                        self._crop_widget.setActive(False)
            except Exception:
                pass
            # Do NOT focus crop for interior clicks; forward to view only
            self._forward_mouse_event(ev, allow_crop=False)
            return
        rid, mode = hit
        # Select ROI and start interaction
        target = self._mgr.get_roi(rid) if self._mgr else None
        # When selecting an ROI, deactivate crop to avoid dual-active tools
        try:
            if self._crop_widget is not None and hasattr(self._crop_widget, 'isActive') and self._crop_widget.isActive():
                if hasattr(self._crop_widget, 'setActive'):
                    self._crop_widget.setActive(False)
        except Exception:
            pass
        self.set_active_roi(rid)
        self._drag_mode = mode
        self._press_scene_pos = self._view.mapToScene(ev.position().toPoint())
        self._orig_rect = QRect(target.rect) if target and target.rect else None
        ev.accept()

    def mouseMoveEvent(self, ev):
        # If crop interaction is in progress, forward all moves to the crop widget
        if self._crop_dragging:
            self._forward_mouse_event(ev, allow_crop=True)
            return
        roi = self._get_active_roi()
        if roi is None or (roi.rect is None and not (roi.shape in ('contour','freehand') and roi.points)):
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
            self._forward_mouse_event(ev, allow_crop=False)
            return

        # Dragging: compute delta in scene space
        scene_pos = self._view.mapToScene(ev.position().toPoint())
        dx = int(scene_pos.x() - self._press_scene_pos.x()) if self._press_scene_pos else 0
        dy = int(scene_pos.y() - self._press_scene_pos.y()) if self._press_scene_pos else 0
        mode = self._drag_mode
        if roi.shape in ('contour','freehand') and roi.points and mode == 'move':
            # Translate all points
            new_pts = []
            for p in roi.points:
                new_pts.append(QPointF(p.x() + dx, p.y() + dy))
            roi.points = new_pts
            # Update an implicit rect for UI sync
            xs = [p.x() for p in roi.points]
            ys = [p.y() for p in roi.points]
            roi.rect = QRect(int(min(xs)), int(min(ys)), int(max(xs)-min(xs)), int(max(ys)-min(ys)))
        else:
            r = QRect(self._orig_rect)
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
            # Finish crop interactions first if any
            if self._crop_dragging:
                self._forward_mouse_event(ev, allow_crop=True)
                self._crop_dragging = False
                ev.accept()
                return
            self._drag_mode = None
            self._press_scene_pos = None
            self._orig_rect = None
            ev.accept()
            return
        # Forward other button releases to underlying; avoid focusing crop unless on its handles
        self._forward_mouse_event(ev, allow_crop=False)
