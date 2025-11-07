# processing/signal_path_analysis.py


"""Signal path / spatiotemporal analysis utilities.

Provides registration across a time series and generation of composite
spatiotemporal visualizations (temporal color progression, phase map, contour
evolution) plus basic morphology metrics of activation footprints.

High-level functions:
- register_animal_time_series: Aligns each time point to the first via ECC
    (Euclidean motion). Returns aligned WF/FL arrays for downstream analysis.
- analyze_signal_path: Builds masks above a fluorescence threshold, derives
    temporal / phase / contour overlays with color bars, and computes footprint
    metrics (area, circularity, dispersion).

Design notes:
- Threshold boosting (Otsu * 1.10) tightens background segmentation for a more
    precise outline overlay without relying on user tuning here.
- All color bar creation is delegated to helpers in image_processor for reuse.
- Returns are structured so the caller can optionally persist individual maps
    or aggregate metrics alongside feature CSVs.

Comments emphasize rationale and data flow; change-log phrasing removed.
"""

import cv2
import numpy as np
from matplotlib import colormaps
from skimage import measure
from typing import Dict, List, Tuple
from processing.image_processor import create_time_colorbar, create_phase_colorbar


def register_animal_time_series(time_data: Dict[str, Dict[str, str]]) -> Dict[str, Dict[str, np.ndarray]]:
    """
    Performs intra-animal registration for a full time-series against its first time point.
    """
    if not time_data:
        return {}

    sorted_time_points = sorted(time_data.keys())
    reference_time_point = sorted_time_points[0]

    if "WF" not in time_data[reference_time_point]:
        print(f"Warning: Cannot perform registration. Missing reference WF image for time {reference_time_point}.")
        return {}

    # Load the reference image (t=0)
    ref_wf_image = cv2.imread(time_data[reference_time_point]["WF"], cv2.IMREAD_UNCHANGED)
    ref_fl_image = cv2.imread(time_data[reference_time_point]["FL"], cv2.IMREAD_UNCHANGED)
    
    # Normalize reference to float32 for ECC
    ref_wf_float = cv2.normalize(ref_wf_image, None, 0, 1.0, cv2.NORM_MINMAX, dtype=cv2.CV_32F)
    
    aligned_images = {
        reference_time_point: {"WF": ref_wf_image, "FL": ref_fl_image}
    }

    # Define motion model and termination criteria for ECC
    motion_model = cv2.MOTION_EUCLIDEAN
    warp_matrix = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 5000, 1e-8)

    # Iterate through subsequent time points to align them
    for time_point in sorted_time_points[1:]:
        if "WF" not in time_data[time_point] or "FL" not in time_data[time_point]:
            continue

        moving_wf = cv2.imread(time_data[time_point]["WF"], cv2.IMREAD_UNCHANGED)
        moving_fl = cv2.imread(time_data[time_point]["FL"], cv2.IMREAD_UNCHANGED)
        
        moving_wf_float = cv2.normalize(moving_wf, None, 0, 1.0, cv2.NORM_MINMAX, dtype=cv2.CV_32F)

        try:
            # Calculate the transformation matrix
            (_, warp_matrix) = cv2.findTransformECC(ref_wf_float, moving_wf_float, warp_matrix, motion_model, criteria)
            
            h, w = ref_wf_image.shape
            
            # Apply the calculated transformation to both WF and FL images
            aligned_wf = cv2.warpAffine(moving_wf, warp_matrix, (w, h), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP)
            aligned_fl = cv2.warpAffine(moving_fl, warp_matrix, (w, h), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP)
            
            aligned_images[time_point] = {"WF": aligned_wf, "FL": aligned_fl}

        except cv2.error as e:
            print(f"Warning: Registration failed for time point {time_point}. Using original images. Error: {e}")
            aligned_images[time_point] = {"WF": moving_wf, "FL": moving_fl}
            
    return aligned_images


def analyze_signal_path(
    aligned_data: Dict[str, Dict[str, np.ndarray]],
    signal_threshold: int,
    transparency_percent: int,
    phase1_index: int,
    phase2_index: int,
    time_points_in_minutes: List[int], # UI-provided time points (minutes) for labeling color bars
    cmap_name: str = 'inferno'
) -> Tuple[np.ndarray, Dict[str, np.ndarray], Dict[str, float]]:
    """
    Analyzes spatiotemporal dynamics and creates multiple advanced visualization maps,
    each with an attached color bar.
    """
    if not aligned_data:
        return None, {}, {}
    

    # 1. Initial Setup and Data Preparation
    first_key = next(iter(aligned_data))
    h, w = aligned_data[first_key]['FL'].shape
    sorted_time_points = sorted(aligned_data.keys())
    num_time_points = len(sorted_time_points)

    footprint_map = np.zeros((h, w), dtype=np.uint32)
    masks_by_time = {}
    for time_point in sorted_time_points:
        mask = aligned_data[time_point]['FL'] > signal_threshold
        masks_by_time[time_point] = mask
        footprint_map[mask] += 1

    # 2. Create the Universal Anatomical Background
    wf_images = [data['WF'] for data in aligned_data.values()]
    average_wf = np.mean(np.stack(wf_images).astype(np.float32), axis=0).astype(wf_images[0].dtype)
    wf_bg_8bit = cv2.normalize(average_wf, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    
    # Find the optimal Otsu threshold first
    otsu_thresh_val, _ = cv2.threshold(wf_bg_8bit, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Increase the threshold by 10% to make it more aggressive
    aggressive_thresh_val = otsu_thresh_val * 1.10
    
    # Apply this new, higher threshold to get a tighter mask
    _, binary_mask = cv2.threshold(wf_bg_8bit, aggressive_thresh_val, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    largest_contour = max(contours, key=cv2.contourArea) if contours else None

    # 3. Generate the Individual Signal Maps (without background)
    temporal_map_raw = np.zeros((h, w, 3), dtype=np.uint8)
    cmap = colormaps.get_cmap(cmap_name)
    for i, time_point in enumerate(sorted_time_points):
        color = cmap(i / (num_time_points - 1)) if num_time_points > 1 else cmap(0.5)
        temporal_map_raw[masks_by_time[time_point]] = (np.array(color[:3]) * 255).astype(np.uint8)

    phase_map_raw = np.zeros((h, w, 3), dtype=np.uint8)
    # The indices from the UI are now used directly here
    early_mask = np.any([masks_by_time[tp] for tp in sorted_time_points[0:phase1_index]], axis=0)
    mid_mask = np.any([masks_by_time[tp] for tp in sorted_time_points[phase1_index:phase2_index]], axis=0)
    late_mask = np.any([masks_by_time[tp] for tp in sorted_time_points[phase2_index:]], axis=0)

    phase_map_raw[early_mask, 2] = 255  # Red
    phase_map_raw[mid_mask, 1] = 255    # Green
    phase_map_raw[late_mask, 0] = 255     # Blue

    contour_map_raw = np.zeros((h, w, 3), dtype=np.uint8)
    for i, time_point in enumerate(sorted_time_points):
        color = cmap(i / (num_time_points - 1)) if num_time_points > 1 else cmap(0.5)
        color_bgr = tuple(int(c * 255) for c in color[:3][::-1])
        
        contours, _ = cv2.findContours(masks_by_time[time_point].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(contour_map_raw, contours, -1, color_bgr, 1)

    # 4. Create Final Overlays and Attach Color Bars
    generated_maps = {}
    raw_maps_to_process = {
        "temporal": temporal_map_raw,
        "phase": phase_map_raw,
        "contour": contour_map_raw,
    }

    alpha = transparency_percent / 100.0
    beta = 1.0 - alpha
    wf_bg_rgb = cv2.cvtColor(wf_bg_8bit, cv2.COLOR_GRAY2RGB)
    
    # --- Generate the color bars ONCE ---
    time_bar = create_time_colorbar(h, cmap_name, min(time_points_in_minutes), max(time_points_in_minutes))
    phase_bar = create_phase_colorbar(h)

    for name, raw_map in raw_maps_to_process.items():
        # Blend the signal map with the anatomical background
        blended_image = cv2.addWeighted(wf_bg_rgb, beta, raw_map, alpha, 0)
        
        # Draw the bright white animal outline ON TOP of the blended result
        if largest_contour is not None:
            cv2.drawContours(blended_image, [largest_contour], -1, (255, 255, 255), 2)
        
        # --- Attach the correct color bar to the final blended image ---
        if name == 'phase':
            final_map_with_bar = np.hstack([blended_image, phase_bar])
        else: # 'temporal' and 'contour' maps both use the time bar
            final_map_with_bar = np.hstack([blended_image, time_bar])
            
        generated_maps[name] = final_map_with_bar
        
    # 5. Extract Morphological Features
    features = {}
    binary_footprint = footprint_map > 0
    label_image = measure.label(binary_footprint)
    props = measure.regionprops(label_image)
    if props:
        main_prop = max(props, key=lambda p: p.area)
        features['Total_Explored_Area'] = main_prop.area
        if main_prop.perimeter > 0:
            features['Footprint_Circularity'] = (4 * np.pi * main_prop.area) / (main_prop.perimeter ** 2)
        else:
            features['Footprint_Circularity'] = 0.0
        coords = main_prop.coords
        if coords.shape[0] > 1:
            std_devs = np.std(coords, axis=0)
            features['Footprint_Dispersion_Y'] = std_devs[0]
            features['Footprint_Dispersion_X'] = std_devs[1]
            features['Footprint_Dispersion_Euclidean'] = np.linalg.norm(std_devs)
        else:
            features['Footprint_Dispersion_Y'] = 0.0
            features['Footprint_Dispersion_X'] = 0.0
            features['Footprint_Dispersion_Euclidean'] = 0.0
    else: # Handle case where there is no signal at all
        features['Total_Explored_Area'] = 0.0
        features['Footprint_Circularity'] = 0.0
        features['Footprint_Dispersion_Y'] = 0.0
        features['Footprint_Dispersion_X'] = 0.0
        features['Footprint_Dispersion_Euclidean'] = 0.0

    return footprint_map, generated_maps, features