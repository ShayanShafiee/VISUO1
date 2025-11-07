# gui/worker.py


"""Background processing worker.

Runs the heavy-lift pipeline in a separate thread so the GUI stays responsive.

Pipeline stages per animal:
1. Load / optionally register frames (global template or intra-animal sequence).
2. Crop to the user ROI (or keep full image for feature modes that need it).
3. Build overlays (WF + LUT-colored FL) for collage / animation.
4. Extract radiomics / custom features (optionally with different region modes).
5. Perform signal path analysis (temporal & phase maps) when enabled.
6. Aggregate and write Raw Results and Group Summary CSVs; emit status signals.

Signals:
progress(int) - Percent complete overall
status(str)   - Human-readable status for status bar
finished()    - Emitted on normal completion
error(str)    - Emitted on fatal error (processing stops)
featureCsvReady(str) - Path to the Raw Results CSV once written (for auto-load)

Implementation notes:
- Long loops periodically check is_running / pause state to allow cancel/pause.
- Time points are iterated from a canonical list; missing frames yield placeholders.
- Refrains from embedding UI logic; only communicates via signals.
"""

import pandas as pd
import os
import re
import csv
import numpy as np
import logging 
from PyQt6.QtCore import QObject, pyqtSignal, QRect, QThread
from tifffile import imread, imwrite
import cv2

from processing.registration import center_image_pair_with_template
from processing.timeseries_analysis import summarize_features_by_group

from processing.image_processor import (
    apply_lut, create_overlay, crop_image,
    create_placeholder_image, assemble_and_save_collage,
    add_timestamp_to_image, create_colorbar_image, 
    create_animation_from_frames, add_progress_bar_to_image, COLOR_MAP,
)

from processing.feature_extraction import calculate_pyradiomics_features
from processing.signal_path_analysis import register_animal_time_series, analyze_signal_path



class Worker(QObject):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    featureCsvReady = pyqtSignal(str)

    def __init__(self, grouped_data: dict, settings: dict, roi: QRect, output_dir: str):
        super().__init__()
        self.grouped_data = grouped_data
        self.settings = settings
        self.roi = (roi.x(), roi.y(), roi.width(), roi.height())
        self.output_dir = output_dir
        self.is_running = True
        self._paused = False
        self.features_to_extract = self.settings.get("selected_features_list", [])

    def run(self):
        """The main processing loop."""
        try:
            # --- Step 1: Setup ---
            verbose = self.settings.get("verbose_logging", False)
            radiomics_logger = logging.getLogger('radiomics')
            radiomics_logger.setLevel(logging.INFO if verbose else logging.ERROR)
            self.status.emit("Starting processing...")
            features_only = bool(self.settings.get("features_only", False))
            use_registration = self.settings.get("use_registration", False)
            template_image = None
            if use_registration:
                template_path = self.settings.get("template_path")
                if not template_path or not os.path.exists(template_path):
                    self.error.emit("Registration is enabled, but the template image was not found.")
                    return
                template_image = imread(template_path)
            watermark_size = self.settings.get("watermark_size", 20)
            watermark_color_name = self.settings.get("watermark_color", "White")
            watermark_color_bgr = COLOR_MAP.get(watermark_color_name, (255, 255, 255))
            enable_features = self.settings.get("enable_features", False)
            # Feature region selection
            feature_region_mode = str(self.settings.get("feature_region_mode", "crop")).lower()
            feature_region_roi_id = self.settings.get("feature_region_roi_id")
            roi_list = self.settings.get("roi_list", []) or []
            enabled_feature_classes = self.settings.get("enabled_feature_classes", [])
            all_feature_results = []
            enable_signal_path = self.settings.get("enable_signal_path", False)
            all_signal_path_results = []
            master_collage_data = {}
            total_animals = len(self.grouped_data)
            time_points_to_collate = sorted([f"{i:04d}" for i in range(0, 601, 30)])

            # --- Step 2: Main Processing Loop ---
            for i, (animal_key, time_data) in enumerate(self.grouped_data.items()):
                if not self.is_running:
                    self.status.emit("Processing cancelled.")
                    return
                self._maybe_wait_if_paused()
                if not self.is_running: return
                self.status.emit(f"Processing animal: {animal_key} ({i+1}/{total_animals})")

                group_name = "Uncategorized"
                try:
                    _, animal_id_part = animal_key.split('_', 1)
                    group_match = re.match(r"(.+)-[Aa]\d{1,3}", animal_id_part)
                    if group_match:
                        group_name = group_match.group(1)
                except (ValueError, IndexError):
                    print(f"Warning: Could not parse group name from key: {animal_key}")

                # Unified preparation loop: build inputs for collage/animation and signal path in one pass.
                
                collage_images = [] # For collage and animation (skipped if features_only)
                processed_time_series_data = {} # For signal path maps
                
                # First, if intra-animal registration is needed, run it ONCE for the whole animal.
                animal_specific_aligned_data = {}
                if enable_signal_path and not use_registration:
                    self.status.emit(f"Performing intra-animal registration for {animal_key}...")
                    animal_specific_aligned_data = register_animal_time_series(time_data)

                base_filename = animal_key
                for idx, time_point in enumerate(time_points_to_collate):
                    if not self.is_running:
                        self.status.emit("Processing cancelled.")
                        return
                    self._maybe_wait_if_paused()
                    final_wf, final_fl = None, None # To hold the final processed images for this timepoint

                    # Check if we have data for this time point
                    has_data = time_point in time_data and "WF" in time_data[time_point] and "FL" in time_data[time_point]
                    has_pre_aligned_data = time_point in animal_specific_aligned_data

                    if has_pre_aligned_data:
                        # Use the already aligned images from the intra-animal step
                        full_wf = animal_specific_aligned_data[time_point]['WF']
                        full_fl = animal_specific_aligned_data[time_point]['FL']
                        # These images still need to be CROPPED
                        final_wf = crop_image(full_wf, self.roi)
                        final_fl = crop_image(full_fl, self.roi)
                    
                    elif has_data:
                        # Standard processing: load, maybe do universal registration, then crop
                        try:
                            wf_image = imread(time_data[time_point]["WF"])
                            fl_image = imread(time_data[time_point]["FL"])
                            
                            # Apply universal template registration if enabled
                            centered_wf, centered_fl = (center_image_pair_with_template(wf_image, fl_image, template_image)
                                                        if use_registration and template_image is not None
                                                        else (wf_image, fl_image))
                            # Keep full-sized copies for feature extraction if needed
                            full_wf, full_fl = centered_wf, centered_fl
                            final_wf = crop_image(centered_wf, self.roi)
                            final_fl = crop_image(centered_fl, self.roi)
                        
                        except Exception as e:
                            print(f"Warning: Failed to load/process image for {animal_key} at {time_point}. Error: {e}. Skipping.")
                            collage_images.append(create_placeholder_image(self.roi[2], self.roi[3]))
                            continue
                    
                    else:
                        # No data for this time point
                        if not features_only:
                            # Create a placeholder only if we are building collages
                            collage_images.append(create_placeholder_image(self.roi[2], self.roi[3]))
                        continue

                    # If we have processed images, feed all downstream consumers (features, overlays, signal path).
                    if final_wf is not None and final_fl is not None:
                        # 1. Prepare data for Signal Path Analysis
                        if enable_signal_path and not features_only:
                            # Note: The images passed here are now *cropped*
                            processed_time_series_data[time_point] = {"WF": final_wf, "FL": final_fl}

                        # 2. Perform Pyradiomics Feature Extraction (if enabled)
                        if enable_features and enabled_feature_classes:
                            # Choose feature image + mask based on the selected region mode
                            try:
                                if 'full' in feature_region_mode:
                                    feat_img = full_fl if 'full_fl' in locals() else final_fl
                                    mask = None  # full image
                                elif 'roi' in feature_region_mode and feature_region_roi_id is not None:
                                    feat_img = full_fl if 'full_fl' in locals() else final_fl
                                    mask = self._build_roi_mask(feat_img.shape, roi_list, int(feature_region_roi_id))
                                else:
                                    # Default: cropping window
                                    feat_img = final_fl
                                    mask = None  # entire cropped area
                            except Exception:
                                feat_img = final_fl
                                mask = None
                            features = calculate_pyradiomics_features(feat_img, mask, enabled_feature_classes)
                            if features:
                                all_feature_results.append({
                                    'group_name': group_name, 'animal_key': animal_key,
                                    'time_min': int(time_point), **features
                                })
                        
                        # 3. Create the visual overlay for collage and animation
                        if not features_only:
                            fl_rgb = apply_lut(final_fl, self.settings["min_intensity"], self.settings["max_intensity"], self.settings["lut"])
                            overlay = create_overlay(final_wf, fl_rgb, self.settings["transparency"])

                            # Add the progress bar to the frame ---
                            total_time_steps = len(time_points_to_collate)
                            overlay_with_bar = add_progress_bar_to_image(overlay, idx, total_time_steps)
                            collage_images.append(overlay_with_bar)
                # --- ALL LOOPS ARE DONE, NOW PERFORM POST-PROCESSING ---

                # --- 1. Perform Signal Path Analysis and Save Maps ---
                if not self.is_running:
                    self.status.emit("Processing cancelled.")
                    return
                self._maybe_wait_if_paused()
                if enable_signal_path and processed_time_series_data and not features_only:
                    self.status.emit(f"Analyzing signal path for {animal_key}...")
                    path_threshold = self.settings.get("signal_path_threshold", 7500)
                    transparency = self.settings.get("transparency", 70)
                    phase1 = self.settings.get("phase1_index", 5)
                    phase2 = self.settings.get("phase2_index", 15)
                    time_points_int = [int(tp) for tp in time_points_to_collate]

                    footprint, final_maps, features = analyze_signal_path(
                        processed_time_series_data, path_threshold, transparency,
                        phase1, phase2, time_points_int
                    )

                    if features:
                        features['animal_key'] = animal_key
                        features['group_name'] = group_name
                        all_signal_path_results.append(features)

                    if final_maps:
                        path_output_dir = os.path.join(self.output_dir, group_name, "Signal_Path_Analysis")
                        os.makedirs(path_output_dir, exist_ok=True)
                        footprint_path = os.path.join(path_output_dir, f"{animal_key}_footprint.tif")
                        if footprint is not None and footprint.max() > 0:
                            imwrite(footprint_path, cv2.normalize(footprint.astype(np.float32), None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U))
                        for map_name, map_image in final_maps.items():
                            imwrite(os.path.join(path_output_dir, f"{animal_key}_{map_name}_map.tif"), map_image)
                
                # --- 2. Create and Save Animation ---
                if not features_only:
                    if not self.is_running:
                        self.status.emit("Processing cancelled.")
                        return
                    if collage_images:
                        anim_output_dir = os.path.join(self.output_dir, group_name, "gifs")
                        os.makedirs(anim_output_dir, exist_ok=True)
                        anim_path = os.path.join(anim_output_dir, f"{animal_key}_animation.gif")
                        self.status.emit(f"Creating animation for {animal_key}...")
                        create_animation_from_frames(collage_images, anim_path)

                    if collage_images:
                        unwatermarked_collage = np.hstack(collage_images)
                        gradient_width = 40
                        individual_colorbar = create_colorbar_image(
                            height=unwatermarked_collage.shape[0],
                            total_width=gradient_width,
                            min_val=self.settings["min_intensity"],
                            max_val=self.settings["max_intensity"],
                            cmap_name=self.settings["lut"],
                            font_size=16, # A slightly larger font for the saved image
                            font_color=watermark_color_bgr # Note: This needs to be BGR
                        )
                        collage_with_colorbar = np.hstack([unwatermarked_collage, individual_colorbar])
                        
                        output_filename = f"{base_filename}_collage.tif"
                        output_path = os.path.join(self.output_dir, group_name, output_filename)
                        assemble_and_save_collage([collage_with_colorbar], output_path)

                        if group_name not in master_collage_data:
                            master_collage_data[group_name] = []
                        master_collage_data[group_name].append(unwatermarked_collage)
                    
                    self.progress.emit(int(((i + 1) / total_animals) * 80))
            

            if not features_only:
                self.status.emit("Assembling master collages...")
                total_groups = len(master_collage_data)
                if total_groups == 0:
                    self.status.emit("No data to process for master collages.")
                for i, (group_name, collages) in enumerate(master_collage_data.items()):
                    if not self.is_running:
                        self.status.emit("Processing cancelled.")
                        return
                    self._maybe_wait_if_paused()
                    self.status.emit(f"Creating master collage for group: {group_name}")
                    if not collages: continue
                    header_row = collages[0].copy()
                    num_tiles = len(time_points_to_collate)
                    tile_width = self.roi[2]
                    for tile_index, time_point in enumerate(time_points_to_collate):
                        start_x = tile_index * tile_width
                        end_x = start_x + tile_width
                        tile_roi = header_row[:, start_x:end_x]
                        add_timestamp_to_image(tile_roi, time_point, watermark_size, watermark_color_bgr)
                    remaining_rows = collages[1:]
                    final_rows = [header_row] + remaining_rows
                    master_collage_plain = np.vstack(final_rows)
                    master_colorbar_width = 40
                    master_colorbar = create_colorbar_image(
                        height=master_collage_plain.shape[0],
                        total_width=master_colorbar_width,
                        min_val=self.settings["min_intensity"],
                        max_val=self.settings["max_intensity"],
                        cmap_name=self.settings["lut"],
                        font_size=16,
                        font_color=watermark_color_bgr # Note: This needs to be BGR
                    )
                    master_collage_with_colorbar = np.hstack([master_collage_plain, master_colorbar])
                    master_filename = f"{group_name}_MASTER_COLLAGE.tif"
                    master_output_path = os.path.join(self.output_dir, master_filename)
                    imwrite(master_output_path, master_collage_with_colorbar)
                    self.progress.emit(80 + int(((i + 1) / total_groups) * 20))

                if master_collage_data:
                    self.status.emit("Saving standalone colorbar...")
                    first_group_collages = next(iter(master_collage_data.values()))
                    if first_group_collages:
                        sample_height = first_group_collages[0].shape[0]
                        standalone_colorbar_width = 40
                        standalone_colorbar = create_colorbar_image(
                            height=sample_height, 
                            total_width=standalone_colorbar_width,
                            min_val=self.settings["min_intensity"], max_val=self.settings["max_intensity"],
                            cmap_name=self.settings["lut"], font_size=watermark_size, font_color=watermark_color_bgr
                        )
                        standalone_colorbar_filename = "_COLORBAR.tif"
                        standalone_colorbar_path = os.path.join(self.output_dir, standalone_colorbar_filename)
                        imwrite(standalone_colorbar_path, standalone_colorbar)

            if enable_features and all_feature_results:
                self.status.emit("Parsing and saving feature extraction results...")
                raw_features_df = pd.DataFrame(all_feature_results)
                id_cols = ['group_name', 'animal_key', 'time_min']
                feature_cols_to_clean = [col for col in raw_features_df.columns if col not in id_cols]
                for col in feature_cols_to_clean:
                    raw_features_df[col] = pd.to_numeric(raw_features_df[col], errors='coerce')
                # Strip leading 'original' prefixes from feature names for clarity
                # Handles variations like 'original_', 'original.', or 'original '
                try:
                    rename_map = {}
                    for col in list(raw_features_df.columns):
                        if col in id_cols:
                            continue
                        new_col = col
                        for sep in ['_', '.', ' ']:
                            prefix = f"original{sep}"
                            if new_col.startswith(prefix):
                                new_col = new_col[len(prefix):]
                                break
                        if new_col != col:
                            rename_map[col] = new_col
                    if rename_map:
                        raw_features_df.rename(columns=rename_map, inplace=True)
                except Exception:
                    pass
                try:
                    parsed_cols = raw_features_df['group_name'].str.split('-', n=3, expand=True)
                    raw_features_df['Group_Number'] = parsed_cols[0]
                    raw_features_df['Sex'] = parsed_cols[1]
                    raw_features_df['Dose'] = parsed_cols[2]
                    raw_features_df['Treatment'] = parsed_cols[3]
                    new_factor_cols = ['Group_Number', 'Sex', 'Dose', 'Treatment']
                    desired_order = ['group_name'] + new_factor_cols + ['animal_key', 'time_min']
                    remaining_cols = [c for c in raw_features_df.columns if c not in desired_order]
                    final_order = desired_order + sorted(remaining_cols)
                    raw_features_df = raw_features_df[final_order]
                except Exception as e:
                    print(f"Warning: Could not parse group names. Sticking to original format. Error: {e}")
                tag = str(self.settings.get("feature_tag") or "").strip()
                suffix = f"__{tag}" if tag else ""
                csv_filename = f"_Feature_Extraction_Raw_Results{suffix}.csv"
                csv_output_path = os.path.join(self.output_dir, csv_filename)
                raw_features_df.to_csv(csv_output_path, index=False)
                self.status.emit("Generating group summary statistics...")
                summary_df = summarize_features_by_group(raw_features_df)
                if not summary_df.empty:
                    summary_filename = f"_Feature_Extraction_Group_Summary{suffix}.csv"
                    summary_output_path = os.path.join(self.output_dir, summary_filename)
                    summary_df.to_csv(summary_output_path, index=False)
                self.featureCsvReady.emit(csv_output_path)

            # Ensure the final CSV saving for signal path is present ---
            if not self.is_running:
                self.status.emit("Processing cancelled.")
                return
            if enable_signal_path and all_signal_path_results and not features_only:
                self.status.emit("Saving signal path analysis results...")
                path_df = pd.DataFrame(all_signal_path_results)
                id_cols = ['group_name', 'animal_key']
                feature_cols = sorted([col for col in path_df.columns if col not in id_cols])
                path_df = path_df[id_cols + feature_cols]
                path_csv_filename = "_Signal_Path_Features.csv"
                path_csv_output_path = os.path.join(self.output_dir, path_csv_filename)
                path_df.to_csv(path_csv_output_path, index=False)
            
            self.status.emit("Processing complete!")
        except BaseException as e:
            import traceback
            error_str = f"An unexpected error occurred in worker: {e}\n{traceback.format_exc()}"
            self.error.emit(error_str)
        finally:
            self.finished.emit()

    def stop(self):
        self.is_running = False
        # In case paused, ensure we can exit the pause loop
        self._paused = False
    
    def pause(self):
        """Pause the worker's processing loop at safe checkpoints."""
        self._paused = True

    def resume(self):
        """Resume processing if previously paused."""
        self._paused = False

    def _maybe_wait_if_paused(self):
        """Block the worker thread in short sleeps while paused, remaining responsive to abort."""
        while self._paused and self.is_running:
            QThread.msleep(50)

    # --- Helper: build a binary mask from a serialized ROI list ---
    def _build_roi_mask(self, image_shape, roi_list: list, roi_id: int):
        try:
            import numpy as np
            import cv2
            h, w = image_shape[:2]
            mask = np.zeros((h, w), dtype=np.uint8)
            roi = None
            for r in roi_list:
                try:
                    if int(r.get('id')) == int(roi_id):
                        roi = r
                        break
                except Exception:
                    continue
            if roi is None:
                return mask
            shape = str(roi.get('shape', 'rect'))
            rect = roi.get('rect')
            pts = roi.get('points')
            if shape == 'ellipse' and rect and len(rect) == 4:
                x, y, rw, rh = [int(v) for v in rect]
                center = (int(x + rw/2), int(y + rh/2))
                axes = (int(rw/2), int(rh/2))
                cv2.ellipse(mask, center, axes, 0, 0, 360, color=255, thickness=-1)
            elif (shape in ('freehand', 'contour') and pts and len(pts) >= 3):
                poly = np.array([[int(p[0]), int(p[1])] for p in pts], dtype=np.int32)
                cv2.fillPoly(mask, [poly], color=255)
            elif rect and len(rect) == 4:
                x, y, rw, rh = [int(v) for v in rect]
                x2, y2 = x + rw, y + rh
                x, y = max(0, x), max(0, y)
                x2, y2 = min(w, x2), min(h, y2)
                if x2 > x and y2 > y:
                    mask[y:y2, x:x2] = 255
            return mask
        except Exception:
            # Robust fallback: empty mask
            return np.zeros((image_shape[0], image_shape[1]), dtype=np.uint8)
