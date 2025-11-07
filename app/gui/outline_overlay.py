#!/usr/bin/env python3
# gui/outline_overlay.py

"""Outline overlay widget.

Draws an animal outline (largest contour) over the image preview without
interfering with mouse interaction. Contour extraction is threshold-based with
fallback heuristics (Otsu-based boost) when the initial threshold yields no
result. Viewport mapping keeps the outline aligned during zoom/pan.

No change-log commentary; comments explain purpose and steps.
"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QPen, QColor, QPainterPath
import numpy as np
import cv2
try:
    from tifffile import imread as tiff_imread
except Exception:
    tiff_imread = None


class OutlineOverlay(QWidget):
    """Passive animal outline overlay.

    Computes a contour in image coordinates, caches it, and builds a QPainterPath
    mapped to viewport coordinates so the outline tracks zoom/pan smoothly.
    Mouse events pass through to underlying widgets.
    """
    def __init__(self, parent=None, image_view=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._image_view = image_view
        self._visible = False
        self._color = QColor(0, 255, 0)
        self._thresh = 5000
        self._source = 'WF'  # 'WF' or 'FL'
        self._wf_path = None
        self._fl_path = None
        self._img_cache = {}  # path -> np.ndarray
        self._contours_img_coords = None  # list of contours (Nx2 arrays) in image coordinates
        self._path_viewport = None  # QPainterPath mapped to viewport coords

    # ---- Public API ----
    def set_image_paths(self, wf_path: str, fl_path: str):
        changed = (wf_path != self._wf_path) or (fl_path != self._fl_path)
        self._wf_path = wf_path
        self._fl_path = fl_path
        if changed:
            # Clear cache for paths that changed
            for p in list(self._img_cache.keys()):
                if p not in (self._wf_path, self._fl_path):
                    self._img_cache.pop(p, None)
            self._contours_img_coords = None
            self._path_viewport = None

    def set_params(self, visible: bool = None, color: QColor = None, threshold: int = None, source: str = None):
        updated = False
        if visible is not None and bool(visible) != self._visible:
            self._visible = bool(visible)
            updated = True
        if color is not None and color != self._color:
            self._color = QColor(color)
            updated = True
        if threshold is not None and int(threshold) != self._thresh:
            self._thresh = int(threshold)
            # threshold change requires recomputation
            self._contours_img_coords = None
            updated = True
        if source is not None and source in ('WF', 'FL') and source != self._source:
            self._source = source
            # source change requires recomputation
            self._contours_img_coords = None
            updated = True
        if updated:
            self.update_outline(force_recompute=False)

    def update_outline(self, force_recompute: bool = False):
        if not self._visible:
            self._path_viewport = None
            self.update()
            return
        # Ensure contours in image coordinates exist
        if force_recompute or self._contours_img_coords is None:
            img = self._load_source_image()
            if img is None:
                self._contours_img_coords = None
                self._path_viewport = None
                self.update()
                return
            mask = self._threshold_to_mask(img, self._thresh)
            contours = self._find_largest_contour(mask)
            self._contours_img_coords = contours
        # Map to viewport painter path
        self._path_viewport = self._make_viewport_path(self._contours_img_coords)
        self.update()

    def remap_to_viewport(self):
        """Call this on zoom/pan/resize to rebuild the viewport path without recomputing contours."""
        if not self._visible:
            return
        if self._contours_img_coords is None:
            # No data yet; try computing
            self.update_outline(force_recompute=True)
            return
        self._path_viewport = self._make_viewport_path(self._contours_img_coords)
        self.update()

    # ---- Internals ----
    def _load_source_image(self):
        path = self._wf_path if self._source == 'WF' else self._fl_path
        if not path:
            return None
        if path in self._img_cache:
            return self._img_cache[path]
        img = None
        try:
            if tiff_imread is not None and (path.lower().endswith('.tif') or path.lower().endswith('.tiff')):
                img = tiff_imread(path)
            else:
                img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        except Exception:
            img = None
        if img is None:
            return None
        # Convert to a single 2D grayscale frame if needed
        if img.ndim == 3:
            # Case A: color image (H,W,3|4)
            if img.shape[-1] in (3, 4) and img.shape[0] != 3 and img.shape[0] != 4:
                try:
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                except Exception:
                    img = img.mean(axis=-1)
            # Case B: multi-frame stack (N,H,W) -> use max projection along frames
            elif img.shape[0] > 1 and img.ndim == 3:
                try:
                    img = np.max(img, axis=0)
                except Exception:
                    img = img.squeeze()
            else:
                img = img.squeeze()
        img = np.asarray(img)
        self._img_cache[path] = img
        return img

    def _threshold_to_mask(self, img: np.ndarray, thresh: int) -> np.ndarray:
        # Handle integer images of various bit depths; make boolean mask then uint8
        try:
            mask = (img >= thresh).astype(np.uint8) * 255
        except Exception:
            # Fallback: normalize to 0..255 first
            imin, imax = float(np.min(img)), float(np.max(img))
            val = 0 if imax <= imin else int(255 * (thresh - imin) / (imax - imin))
            _, mask = cv2.threshold(img.astype(np.uint8), val, 255, cv2.THRESH_BINARY)
        return mask

    def _find_largest_contour(self, mask: np.ndarray):
        try:
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        except ValueError:
            # Older OpenCV returns 3 values
            _, contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        # Pick largest external contour by area
        cnt = max(contours, key=cv2.contourArea)
        # Flatten to Nx2 (x,y)
        pts = cnt.reshape(-1, 2)
        return pts

    def _make_viewport_path(self, pts_img):
        if pts_img is None or self._image_view is None:
            return None
        path = QPainterPath()
        # Subsample for performance if too many points
        step = 1
        n = len(pts_img)
        if n > 4000:
            step = max(1, n // 2000)  # keep ~2k points
        first = True
        for i in range(0, n, step):
            x, y = float(pts_img[i][0]), float(pts_img[i][1])
            # Map from scene (image) space to viewport widget coordinates
            from PyQt6.QtCore import QPointF
            pv = self._image_view.mapFromScene(QPointF(x, y))
            if first:
                path.moveTo(pv)
                first = False
            else:
                path.lineTo(pv)
        # Close the contour
        if not first:
            path.closeSubpath()
        return path

    def paintEvent(self, event):
        if not self._visible or self._path_viewport is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._color)
        pen.setWidth(3)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(self._path_viewport)
        p.end()

    # --- Enhanced outline robustness: try Otsu fallback for WF if manual threshold finds nothing ---
    def _try_auto_wf_contour(self, img: np.ndarray):
        try:
            # Normalize to 8-bit for Otsu and compute a slightly aggressive threshold
            img8 = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            otsu_thresh, _ = cv2.threshold(img8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            aggressive = min(255, int(otsu_thresh * 1.1))
            _, mask = cv2.threshold(img8, aggressive, 255, cv2.THRESH_BINARY)
            return self._find_largest_contour(mask)
        except Exception:
            return None

    def update_outline(self, force_recompute: bool = False):
        if not self._visible:
            self._path_viewport = None
            self.update()
            return
        # Ensure contours in image coordinates exist
        if force_recompute or self._contours_img_coords is None:
            img = self._load_source_image()
            if img is None:
                self._contours_img_coords = None
                self._path_viewport = None
                self.update()
                return
            mask = self._threshold_to_mask(img, self._thresh)
            contours = self._find_largest_contour(mask)
            # If no contour found, try sensible fallbacks
            if contours is None:
                if self._source == 'WF':
                    contours = self._try_auto_wf_contour(img)
                elif self._source == 'FL' and self._wf_path:
                    # Try WF-based auto outline if FL failed
                    wf_img = None
                    try:
                        if self._wf_path in self._img_cache:
                            wf_img = self._img_cache[self._wf_path]
                        else:
                            if tiff_imread is not None and (self._wf_path.lower().endswith('.tif') or self._wf_path.lower().endswith('.tiff')):
                                wf_img = tiff_imread(self._wf_path)
                            else:
                                wf_img = cv2.imread(self._wf_path, cv2.IMREAD_UNCHANGED)
                        if wf_img is not None and wf_img.ndim == 3:
                            # Handle color or stack similarly as above
                            if wf_img.shape[-1] in (3,4) and wf_img.shape[0] not in (3,4):
                                try:
                                    wf_img = cv2.cvtColor(wf_img, cv2.COLOR_BGR2GRAY)
                                except Exception:
                                    wf_img = wf_img.mean(axis=-1)
                            elif wf_img.shape[0] > 1:
                                wf_img = np.max(wf_img, axis=0)
                            else:
                                wf_img = wf_img.squeeze()
                    except Exception:
                        wf_img = None
                    if wf_img is not None:
                        contours = self._try_auto_wf_contour(wf_img)
            self._contours_img_coords = contours
        # Map to viewport painter path
        self._path_viewport = self._make_viewport_path(self._contours_img_coords)
        self.update()
