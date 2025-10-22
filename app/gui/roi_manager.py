from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Literal
from PyQt6.QtCore import QRect, QPointF
from PyQt6.QtGui import QColor

ROIShape = Literal['rect', 'ellipse', 'freehand', 'contour', 'text']

_id_counter = 0

def _next_id() -> int:
    global _id_counter
    _id_counter += 1
    return _id_counter

@dataclass
class ROI:
    shape: ROIShape
    name: str
    color: QColor
    visible: bool = True
    id: int = field(default_factory=_next_id)
    # Geometry in image-space coordinates
    rect: Optional[QRect] = None           # for rect/ellipse
    points: Optional[List[QPointF]] = None # for freehand/contour
    # Optional text content for text annotations
    label: Optional[str] = None

    def as_rect(self) -> Optional[QRect]:
        return self.rect

    def as_points(self) -> Optional[List[QPointF]]:
        return self.points or []

@dataclass
class ROIManager:
    rois: List[ROI] = field(default_factory=list)

    def add_roi(self, roi: ROI) -> ROI:
        self.rois.append(roi)
        return roi

    def remove_roi(self, roi_id: int) -> None:
        self.rois = [r for r in self.rois if r.id != roi_id]

    def get_roi(self, roi_id: int) -> Optional[ROI]:
        for r in self.rois:
            if r.id == roi_id:
                return r
        return None

    def rename_roi(self, roi_id: int, new_name: str) -> None:
        r = self.get_roi(roi_id)
        if r:
            r.name = new_name

    def set_roi_visibility(self, roi_id: int, visible: bool) -> None:
        r = self.get_roi(roi_id)
        if r:
            r.visible = visible

    def set_roi_color(self, roi_id: int, color: QColor) -> None:
        r = self.get_roi(roi_id)
        if r:
            r.color = color

    def list_summary(self) -> List[dict]:
        return [
            {
                'id': r.id,
                'name': r.name,
                'shape': r.shape,
                'color': (r.color.red(), r.color.green(), r.color.blue(), r.color.alpha()),
                'visible': r.visible,
            }
            for r in self.rois
        ]
