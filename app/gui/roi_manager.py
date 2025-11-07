#!/usr/bin/env python3
# gui/roi_manager.py

"""ROI data model and serialization helpers.

Defines the in-memory representation of ROIs (shape, color, geometry, labels)
and provides utilities to create, update, list, and serialize/deserialize ROIs
for persistence. Used by both the preview overlay and the settings panel to keep
lists and geometry in sync.

Focus is on clear data handling; UI logic remains in overlay/panel modules.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Tuple, Optional, Literal
from PyQt6.QtCore import QRect, QPointF
from PyQt6.QtGui import QColor

ROIShape = Literal['rect', 'ellipse', 'freehand', 'contour', 'text']

_id_counter = 0

def _next_id() -> int:
    global _id_counter
    _id_counter += 1
    return _id_counter

def _set_id_counter_at_least(n: int) -> None:
    global _id_counter
    if n > _id_counter:
        _id_counter = n

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
    # Optional algorithmic ROI parameters (for auto/threshold types)
    algo: Optional[str] = None           # 'otsu' | 'threshold' | None
    channel: Optional[str] = None        # 'WF' | 'FL' | None
    threshold: Optional[int] = None      # manual threshold value
    otsu_boost: Optional[int] = None     # boost percent for otsu
    # Overlay-ROI specific parameters (acts on WF+FL overlay, separate from preview/collage)
    overlay_min: Optional[int] = None       # FL min intensity for LUT mapping
    overlay_max: Optional[int] = None       # FL max intensity for LUT mapping
    overlay_lut: Optional[str] = None       # colormap name
    overlay_alpha: Optional[int] = None     # transparency percent (0-100)
    overlay_method: Optional[str] = None    # 'threshold' | 'otsu'
    overlay_thresh: Optional[int] = None    # 0-255 threshold on 8-bit overlay
    overlay_otsu_boost: Optional[int] = None # boost percent for otsu on overlay
    # Overlay post/pre-processing options
    overlay_smooth_method: Optional[str] = None  # 'none'|'gaussian'|'median'
    overlay_smooth_ksize: Optional[int] = None   # odd kernel size
    overlay_keep_largest: Optional[bool] = None  # keep only largest connected component
    # Base image size at creation or last edit (for proportional scaling across images)
    base_w: Optional[int] = None
    base_h: Optional[int] = None
    # Composite ROI metadata (depends on other ROIs)
    composite_op: Optional[str] = None           # 'or'|'and'|'sub'|'xor'|None
    composite_sources: Optional[List[int]] = None

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
                'algo': r.algo,
                'channel': r.channel,
                'threshold': r.threshold,
                'otsu_boost': r.otsu_boost,
                # Composite summary
                'composite_op': r.composite_op,
                'composite_sources': list(r.composite_sources) if r.composite_sources else None,
                # Overlay-specific summary (to seed dialogs)
                'overlay_min': r.overlay_min,
                'overlay_max': r.overlay_max,
                'overlay_lut': r.overlay_lut,
                'overlay_alpha': r.overlay_alpha,
                'overlay_method': r.overlay_method,
                'overlay_thresh': r.overlay_thresh,
                'overlay_otsu_boost': r.overlay_otsu_boost,
                'overlay_smooth_method': r.overlay_smooth_method,
                'overlay_smooth_ksize': r.overlay_smooth_ksize,
                'overlay_keep_largest': r.overlay_keep_largest,
            }
            for r in self.rois
        ]

    # --- Serialization helpers ---
    def to_jsonable(self) -> list[dict]:
        """Serialize all ROIs to a JSON-friendly list of dicts, preserving ids and geometry."""
        data: list[dict] = []
        for r in self.rois:
            entry = {
                'id': r.id,
                'name': r.name,
                'shape': r.shape,
                'visible': bool(r.visible),
                'color': (r.color.red(), r.color.green(), r.color.blue(), r.color.alpha()),
                'rect': [int(r.rect.x()), int(r.rect.y()), int(r.rect.width()), int(r.rect.height())] if r.rect is not None else None,
                'points': [[float(p.x()), float(p.y())] for p in (r.points or [])] if r.points else None,
                'label': r.label,
                'algo': r.algo,
                'channel': r.channel,
                'threshold': r.threshold,
                'otsu_boost': r.otsu_boost,
                'base_w': r.base_w,
                'base_h': r.base_h,
                'composite_op': r.composite_op,
                'composite_sources': list(r.composite_sources) if r.composite_sources else None,
                # Overlay fields
                'overlay_min': r.overlay_min,
                'overlay_max': r.overlay_max,
                'overlay_lut': r.overlay_lut,
                'overlay_alpha': r.overlay_alpha,
                'overlay_method': r.overlay_method,
                'overlay_thresh': r.overlay_thresh,
                'overlay_otsu_boost': r.overlay_otsu_boost,
                'overlay_smooth_method': r.overlay_smooth_method,
                'overlay_smooth_ksize': r.overlay_smooth_ksize,
                'overlay_keep_largest': bool(r.overlay_keep_largest) if r.overlay_keep_largest is not None else None,
            }
            data.append(entry)
        return data

    def load_from_jsonable(self, data: list[dict]) -> None:
        """Replace current ROIs with those from a serialized list. Preserves ids and metadata."""
        self.rois = []
        max_id = 0
        for d in (data or []):
            try:
                shape = d.get('shape')
                name = d.get('name', 'ROI')
                col = d.get('color', (100, 180, 255, 255))
                color = QColor(int(col[0]), int(col[1]), int(col[2]), int(col[3]) if len(col) > 3 else 255)
                r = ROI(shape=shape, name=name, color=color)
                # id
                rid = int(d.get('id')) if d.get('id') is not None else None
                if rid is not None:
                    r.id = rid
                    max_id = max(max_id, rid)
                # visibility
                r.visible = bool(d.get('visible', True))
                # geometry
                rect = d.get('rect')
                if rect and len(rect) == 4:
                    r.rect = QRect(int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))
                pts = d.get('points')
                if pts:
                    r.points = [QPointF(float(x), float(y)) for x, y in pts]
                # text label
                r.label = d.get('label')
                # algo params
                r.algo = d.get('algo')
                r.channel = d.get('channel')
                r.threshold = d.get('threshold')
                r.otsu_boost = d.get('otsu_boost')
                # base dims
                r.base_w = d.get('base_w')
                r.base_h = d.get('base_h')
                # composite metadata
                r.composite_op = d.get('composite_op')
                srcs = d.get('composite_sources')
                r.composite_sources = list(srcs) if srcs else None
                # overlay metadata
                r.overlay_min = d.get('overlay_min')
                r.overlay_max = d.get('overlay_max')
                r.overlay_lut = d.get('overlay_lut')
                r.overlay_alpha = d.get('overlay_alpha')
                r.overlay_method = d.get('overlay_method')
                r.overlay_thresh = d.get('overlay_thresh')
                r.overlay_otsu_boost = d.get('overlay_otsu_boost')
                r.overlay_smooth_method = d.get('overlay_smooth_method')
                r.overlay_smooth_ksize = d.get('overlay_smooth_ksize')
                r.overlay_keep_largest = d.get('overlay_keep_largest')
                self.add_roi(r)
            except Exception:
                # skip malformed entries
                continue
        _set_id_counter_at_least(max_id)
