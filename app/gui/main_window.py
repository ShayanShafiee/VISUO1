# --- CORRECTED FILE: gui/main_window.py ---

import os
import sys
import random
import numpy as np
import pandas as pd
import traceback
import webbrowser 
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QProgressBar, QLabel, QMessageBox,
                             QFileDialog, QStatusBar, QGroupBox, QGridLayout, QLineEdit,
                             QScrollArea)
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import QThread, QRect, pyqtSlot, pyqtSignal, QObject, Qt
from PyQt6.QtGui import QPixmap, QImage, QAction 


from tifffile import imread

from .settings_panel import SettingsPanel
from .preview_panel import PreviewPanel
from .worker import Worker
from processing.file_handler import group_files, parse_filename
from processing.image_processor import apply_lut, create_overlay, compute_animal_outline, draw_outline_on_image
from .feature_selection_panel import FeatureSelectionPanel
from .analysis_panel import AnalysisPanel
from processing.timeseries_analysis import analyze_features
from processing.timeseries_analysis import rank_features_for_hypothesis
from processing.timeseries_analysis import analyze_features, summarize_features_by_group

from processing.heatmap_generator import (create_summary_curves,
                                          calculate_univariate_dtw_matrix,
                                          calculate_multivariate_dtw_matrix,
                                          generate_clustered_heatmap)





class RankingWorker(QObject):
    finished = pyqtSignal(pd.DataFrame, dict)
    error = pyqtSignal(str)

    def __init__(self, raw_df, params, parent=None):
        super().__init__(parent)
        self.raw_df = raw_df
        self.params = params

    def run(self):
        try:
            if self.params['type'] == 'Overall':
                results_df = analyze_features(self.raw_df)
            else:
                results_df = rank_features_for_hypothesis(self.raw_df, self.params)
            self.finished.emit(results_df, self.params)
        except Exception as e:
            error_str = f"An error occurred during ranking analysis: {e}\n\n{traceback.format_exc()}"
            self.error.emit(error_str)

    def __del__(self):
        print("--- DEBUG: Worker object is being destroyed. ---")

    def __del__(self):
        print("--- DEBUG: RankingWorker object is being destroyed. ---")


class HeatmapWorker(QObject):
    finished = pyqtSignal()
    status = pyqtSignal(str)
    error = pyqtSignal(str)
    plotReady = pyqtSignal(str)

    def __init__(self, mode: str, csv_path: str, show_plot: bool, agg_method: str, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.csv_path = csv_path
        self.show_plot = show_plot
        self.agg_method = agg_method

    def run(self):
        try:
            self.status.emit(f"Loading summary data (using {self.agg_method.capitalize()})...")
            summary_df = pd.read_csv(self.csv_path)
            summary_curves = create_summary_curves(summary_df, self.agg_method)
            output_dir = os.path.join(os.path.dirname(self.csv_path), "heatmaps")
            os.makedirs(output_dir, exist_ok=True)
            if self.mode == 'univariate':
                num_features = len(summary_curves)
                if num_features == 0:
                    raise ValueError(f"No feature columns ending in '_{self.agg_method}' found.")
                self.status.emit(f"Generating {num_features} univariate heatmaps...")
                for i, (feature_name, feature_df) in enumerate(summary_curves.items()):
                    self.status.emit(f"({i+1}/{num_features}) Analyzing feature: {feature_name}")
                    dist_matrix = calculate_univariate_dtw_matrix(feature_df)
                    title = f"Univariate Clustering ({self.agg_method.capitalize()}) Based on: {feature_name}"
                    output_path = os.path.join(output_dir, f"heatmap_univariate_{self.agg_method}_{feature_name}.png")
                    generate_clustered_heatmap(dist_matrix, title, output_path)
                    if self.show_plot:
                        self.plotReady.emit(output_path)
            elif self.mode == 'multivariate':
                self.status.emit("Generating multivariate heatmap...")
                dist_matrix = calculate_multivariate_dtw_matrix(summary_curves)
                title = f"Multivariate Clustering ({self.agg_method.capitalize()}) Based on All Features"
                output_path = os.path.join(output_dir, f"heatmap_multivariate_{self.agg_method}.png")
                generate_clustered_heatmap(dist_matrix, title, output_path)
                if self.show_plot:
                    self.plotReady.emit(output_path)
            self.status.emit(f"Heatmap generation complete. Files saved in '{output_dir}'.")
        except Exception as e:
            error_str = f"An error occurred during heatmap generation: {e}\n\n{traceback.format_exc()}"
            self.error.emit(error_str)
        finally:
            self.finished.emit()

    def __del__(self):
        print("--- DEBUG: HeatmapWorker object is being destroyed. ---")



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VISUO1")
        self.setGeometry(100, 100, 1600, 900)
        
        self.main_directory = None
        self.output_directory = None
        self.grouped_files = {}
        self.image_pair_list = []
        self.current_preview_index = -1
        self.current_preview_paths = (None, None)
        self.template_image = None
        self.worker_thread = None
        self.feature_csv_path = None
        self.raw_csv_path = None
        self.summary_csv_path = None
        self.raw_features_df = None
        self.heatmap_thread = None
        self.hypothesis_thread = None
        self.raw_features_df = None 
        
        self.ranking_thread = None 
        self.heatmap_thread = None

        self.settings_file_path = None

        # Processing outcome tracking
        self._proc_error_message = None
        self._proc_aborted = False
        self._proc_stopped = False

        # Guards to avoid spurious handlers on programmatic UI updates
        self._suppress_dir_edit_handler = False
        self._suppress_out_dir_edit_handler = False

        # --- New: Feature extraction signature tracking ---
        self._last_feature_signature = None  # Tuple describing last processed feature config
        self._current_run_feature_signature = None

        self._init_ui()
        self._connect_signals()
        # Simple cache to avoid re-reading images from disk on every tiny UI change
        self._preview_cache = {
            'wf_path': None,
            'fl_path': None,
            'wf_image': None,
            'fl_image': None,
        }
        
    def _init_ui(self):

        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        save_action = QAction("&Save Settings...", self)
        save_action.triggered.connect(self._save_settings)
        file_menu.addAction(save_action)

        load_action = QAction("&Load Settings...", self)
        load_action.triggered.connect(self._load_settings)
        file_menu.addAction(load_action)

        # --- Edit Menu ---
        edit_menu = menu_bar.addMenu("&Edit")
        select_action = QAction("&Select Next ROI", self)
        select_action.triggered.connect(lambda: self.preview_panel.select_next_roi())
        copy_action = QAction("&Copy ROI", self)
        copy_action.setShortcut("Ctrl+C")
        copy_action.triggered.connect(lambda: self.preview_panel.copy_active_roi())
        cut_action = QAction("Cu&t ROI", self)
        cut_action.setShortcut("Ctrl+X")
        cut_action.triggered.connect(lambda: self.preview_panel.cut_active_roi())
        paste_action = QAction("&Paste ROI", self)
        paste_action.setShortcut("Ctrl+V")
        paste_action.triggered.connect(lambda: self.preview_panel.paste_roi())
        add_text_action = QAction("Add &Text Annotation…", self)
        add_text_action.triggered.connect(lambda: self.preview_panel.add_text_annotation())
        edit_menu.addAction(select_action)
        edit_menu.addSeparator()
        edit_menu.addAction(copy_action)
        edit_menu.addAction(cut_action)
        edit_menu.addAction(paste_action)
        edit_menu.addSeparator()
        edit_menu.addAction(add_text_action)

        # --- Settings Menu ---
        settings_menu = menu_bar.addMenu("&Settings")
        self.verbose_action = QAction("&Verbose Logging", self)
        self.verbose_action.setCheckable(True)
        self.verbose_action.setChecked(False)
        self.verbose_action.toggled.connect(self._on_verbose_toggled)
        settings_menu.addAction(self.verbose_action)

        # --- Help Menu ---
        help_menu = menu_bar.addMenu("&Help")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        # Normalize vertical spacing between the Paths group and the panels below
        main_layout.setSpacing(5)

        dir_group = QGroupBox("Paths")
        # Compact the layout and controls to save vertical space
        dir_group_layout = QVBoxLayout(dir_group)
        dir_group_layout.setContentsMargins(8, 6, 8, 6)
        dir_group_layout.setSpacing(4)

        # Row 1: Input Directory
        input_dir_layout = QHBoxLayout()
        self.dir_button = QPushButton("Select Data…")
        self.dir_button.setFixedWidth(160)
        # Tooltip + subtle styling for directory chooser
        try:
            self.dir_button.setToolTip("Choose the main data folder containing WF and FL TIFF images")
            _subtle_btn_style = (
                "\n"
                "QPushButton {\n"
                "    background-color: #2e2e2e;\n"
                "    border: 1px solid #5a5a5a;\n"
                "    border-radius: 4px;\n"
                "    padding: 6px 10px;\n"
                "    color: #e0e0e0;\n"
                "}\n"
                "QPushButton:hover {\n"
                "    background-color: #3a3a3a;\n"
                "    border-color: #6a6a6a;\n"
                "}\n"
                "QPushButton:pressed {\n"
                "    background-color: #252525;\n"
                "    border-color: #555555;\n"
                "}\n"
                "QPushButton:disabled {\n"
                "    background-color: #1f1f1f;\n"
                "    color: #777777;\n"
                "    border-color: #333333;\n"
                "}\n"
            )
            self.dir_button.setStyleSheet(_subtle_btn_style)
        except Exception:
            pass
        self.dir_label = QLineEdit("Not selected.")
        self.dir_label.setToolTip("Selected main data directory. You can also paste a path here.")
        self.dir_label.setFixedHeight(26)
        input_dir_layout.addWidget(self.dir_button)
        input_dir_layout.addWidget(self.dir_label)
        dir_group_layout.addLayout(input_dir_layout)

        # Row 2: Output Directory
        output_dir_layout = QHBoxLayout()
        self.out_dir_button = QPushButton("Select Output…")
        self.out_dir_button.setFixedWidth(160)
        try:
            self.out_dir_button.setToolTip("Choose the folder where processed outputs will be saved")
            # Reuse the same subtle style
            self.out_dir_button.setStyleSheet(_subtle_btn_style)
        except Exception:
            pass
        self.out_dir_label = QLineEdit("Not selected.")
        self.out_dir_label.setToolTip("Selected output directory. You can also paste a path here.")
        self.out_dir_label.setFixedHeight(26)
        output_dir_layout.addWidget(self.out_dir_button)
        output_dir_layout.addWidget(self.out_dir_label)
        dir_group_layout.addLayout(output_dir_layout)
        
        main_layout.addWidget(dir_group)
        
        # The core_layout section ---
        core_layout = QHBoxLayout()
        # Reduce horizontal gaps between left Settings and right Preview (and others)
        core_layout.setContentsMargins(0, 0, 0, 0)
        core_layout.setSpacing(8)
        # Settings panel wrapped in a scroll area to keep the main layout fixed height
        self.settings_panel = SettingsPanel()
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidget(self.settings_panel)
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.settings_scroll.setFrameShape(self.settings_scroll.Shape.NoFrame)
        # Make the Settings column just wide enough for its content (dynamic with a safe minimum)
        try:
            hint_w = self.settings_panel.sizeHint().width()
            # Add a small cushion for scrollbars/margins; enforce a reasonable minimum
            w = max(360, hint_w + 12)
            self.settings_scroll.setFixedWidth(w)
        except Exception:
            # Fallback width if size hint isn't available yet
            self.settings_scroll.setFixedWidth(380)
        # Wrap Settings column in a titled group to align titles across columns
        settings_group = QGroupBox("Settings")
        settings_group_layout = QVBoxLayout(settings_group)
        settings_group_layout.setContentsMargins(0, 5, 0, 0)
        settings_group_layout.addWidget(self.settings_scroll)

    # Wrap PreviewPanel in a titled QGroupBox ---
        self.preview_panel = PreviewPanel()
        preview_group = QGroupBox("Live Preview")
        preview_group_layout = QVBoxLayout(preview_group)
        # Set margins to 0 so the panel fills the group box perfectly
        preview_group_layout.setContentsMargins(0, 5, 0, 0) 
        preview_group_layout.addWidget(self.preview_panel)

        self.feature_panel = FeatureSelectionPanel()
        self.feature_panel.setFixedWidth(300)
        # Wrap Feature column in a titled group to align with Preview
        feature_group = QGroupBox("Feature Selection")
        feature_group_layout = QVBoxLayout(feature_group)
        feature_group_layout.setContentsMargins(0, 5, 0, 0)
        feature_group_layout.addWidget(self.feature_panel)

        self.analysis_panel = AnalysisPanel()
        self.analysis_panel.setFixedWidth(500)
        # Wrap Analysis column in a titled group to align with Preview
        analysis_group = QGroupBox("Analysis")
        analysis_group_layout = QVBoxLayout(analysis_group)
        analysis_group_layout.setContentsMargins(0, 5, 0, 0)
        analysis_group_layout.addWidget(self.analysis_panel)
        
        # Reduce horizontal gaps between columns further and let Preview expand
        core_layout.setSpacing(4)
        core_layout.addWidget(settings_group)
        core_layout.addWidget(preview_group, 1) # Preview gets stretch to occupy free space
        core_layout.addWidget(feature_group)
        core_layout.addWidget(analysis_group)
        
        main_layout.addLayout(core_layout)

        # --- Always-visible control bar (above the status bar) ---
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(8, 4, 8, 4)
        footer_layout.setSpacing(8)

        # Left: control buttons
        self.control_start_btn = QPushButton("Start Processing")
        self.control_start_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        try:
            self.control_start_btn.setToolTip("Begin batch processing using the current settings and ROI")
        except Exception:
            pass
        self.control_start_btn.clicked.connect(self.run_processing)

        self.control_pause_btn = QPushButton("Pause")
        self.control_pause_btn.setStyleSheet("background-color: #FFA000; color: white; font-weight: bold;")
        try:
            self.control_pause_btn.setToolTip("Pause processing; you can resume later")
        except Exception:
            pass
        self.control_pause_btn.clicked.connect(self.pause_processing)

        self.control_abort_btn = QPushButton("Abort")
        self.control_abort_btn.setStyleSheet("background-color: #E53935; color: white; font-weight: bold;")
        try:
            self.control_abort_btn.setToolTip("Abort processing immediately; partial outputs may be incomplete")
        except Exception:
            pass
        self.control_abort_btn.clicked.connect(self.request_abort_processing)

        self.control_resume_btn = QPushButton("Resume")
        self.control_resume_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        try:
            self.control_resume_btn.setToolTip("Resume processing from the paused state")
        except Exception:
            pass
        self.control_resume_btn.clicked.connect(self.resume_processing)

        self.control_stop_btn = QPushButton("Stop")
        self.control_stop_btn.setStyleSheet("background-color: #9E9E9E; color: white; font-weight: bold;")
        try:
            self.control_stop_btn.setToolTip("Stop processing gracefully after the current unit of work")
        except Exception:
            pass
        self.control_stop_btn.clicked.connect(self.stop_processing)

        footer_layout.addWidget(self.control_start_btn)
        footer_layout.addWidget(self.control_pause_btn)
        footer_layout.addWidget(self.control_abort_btn)
        footer_layout.addWidget(self.control_resume_btn)
        footer_layout.addWidget(self.control_stop_btn)

        footer_layout.addStretch(1)

        # Right: progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(16)
        footer_layout.addWidget(self.progress_bar)

        main_layout.addWidget(footer)

        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Ready.")
        # Initialize footer control visibility to idle state
        self._enter_idle_controls()

    # --- Footer control state helpers ---
    def _enter_idle_controls(self):
        if hasattr(self, 'control_start_btn'):
            self.control_start_btn.setVisible(True)
        if hasattr(self, 'control_pause_btn'):
            self.control_pause_btn.setVisible(False)
        if hasattr(self, 'control_abort_btn'):
            self.control_abort_btn.setVisible(False)
        if hasattr(self, 'control_resume_btn'):
            self.control_resume_btn.setVisible(False)
        if hasattr(self, 'control_stop_btn'):
            self.control_stop_btn.setVisible(False)

    def _enter_processing_controls(self):
        if hasattr(self, 'control_start_btn'):
            self.control_start_btn.setVisible(False)
        if hasattr(self, 'control_pause_btn'):
            self.control_pause_btn.setVisible(True)
        if hasattr(self, 'control_abort_btn'):
            self.control_abort_btn.setVisible(True)
        if hasattr(self, 'control_resume_btn'):
            self.control_resume_btn.setVisible(False)
        if hasattr(self, 'control_stop_btn'):
            self.control_stop_btn.setVisible(False)
    
    def _on_verbose_toggled(self, checked: bool):
        """Toggle verbose logging in SettingsPanel when menu item is toggled."""
        try:
            if hasattr(self, 'settings_panel') and hasattr(self.settings_panel, 'set_verbose_logging'):
                self.settings_panel.set_verbose_logging(bool(checked))
        except Exception:
            pass

    def _connect_signals(self):
        """Connects all signals from child widgets to the main window's slots."""
        # --- Directory Panel Connections ---
        try:
            self.dir_button.clicked.connect(self.select_directory)
        except Exception:
            pass
        try:
            self.out_dir_button.clicked.connect(self.select_output_directory)
        except Exception:
            pass

        try:
            self.dir_label.editingFinished.connect(self._on_main_dir_edited)
        except Exception:
            pass
        try:
            self.out_dir_label.editingFinished.connect(self._on_out_dir_edited)
        except Exception:
            pass

        # --- Settings Panel Connections ---
        try:
            self.settings_panel.settingsChanged.connect(self.update_live_preview)
            self.settings_panel.templatePathChanged.connect(self.load_template_image)
            self.settings_panel.startProcessing.connect(self.run_processing)
            # Optional processing control signals
            if hasattr(self.settings_panel, 'pauseRequested'):
                self.settings_panel.pauseRequested.connect(self.pause_processing)
            if hasattr(self.settings_panel, 'resumeRequested'):
                self.settings_panel.resumeRequested.connect(self.resume_processing)
            if hasattr(self.settings_panel, 'abortRequested'):
                self.settings_panel.abortRequested.connect(self.request_abort_processing)
            if hasattr(self.settings_panel, 'stopRequested'):
                self.settings_panel.stopRequested.connect(self.stop_processing)
        except Exception:
            pass

        # --- Preview Panel Navigation Connections ---
        try:
            # Only honor random loads when explicitly user-initiated; pass force=True via lambda
            self.preview_panel.requestNewRandomImage.connect(lambda: self.load_random_preview_image(force=True))
            self.preview_panel.requestSpecificImage.connect(self.load_specific_preview_image)
            self.preview_panel.requestPreviousImage.connect(self.load_previous_preview_image)
            self.preview_panel.requestNextImage.connect(self.load_next_preview_image)
        except Exception:
            pass

        # --- Two-Way ROI Connections between Settings and Preview Panels ---
        try:
            # When user draws/moves ROI on preview, update SettingsPanel spinners and re-extract visibility
            self.preview_panel.roiChangedFromDrawing.connect(self.settings_panel.update_spinners_from_roi)
            self.preview_panel.roiChangedFromDrawing.connect(lambda *_: self._update_reextract_visibility())
        except Exception:
            pass
        try:
            # When ROI spinboxes change in SettingsPanel (including on settings load), update preview ROI overlay
            self.settings_panel.roiChangedFromSpinners.connect(self.preview_panel.update_roi_display)
        except Exception:
            pass

        # --- Multi-ROI wiring (Annotations) ---
        self.settings_panel.addRectangleRoiRequested.connect(self.preview_panel.add_rectangle_roi)
        try:
            self.settings_panel.addCircleRoiRequested.connect(self.preview_panel.add_circle_roi)
            self.settings_panel.addAutoOtsuRoiRequested.connect(self.preview_panel.add_auto_otsu_roi)
            self.settings_panel.addThresholdRoiRequested.connect(self.preview_panel.add_threshold_roi)
            # Composite ROI wiring
            if hasattr(self.preview_panel, 'add_composite_roi'):
                self.settings_panel.addCompositeRoiRequested.connect(self.preview_panel.add_composite_roi)
            if hasattr(self.preview_panel, 'update_composite_roi_properties'):
                self.settings_panel.changeCompositePropertiesRequested.connect(self.preview_panel.update_composite_roi_properties)
            # Overlay ROI wiring
            if hasattr(self.preview_panel, 'add_overlay_roi'):
                self.settings_panel.addOverlayRoiRequested.connect(self.preview_panel.add_overlay_roi)
            if hasattr(self.preview_panel, 'update_overlay_roi_properties'):
                self.settings_panel.changeOverlayRoiPropertiesRequested.connect(self.preview_panel.update_overlay_roi_properties)
            self.settings_panel.changeRoiPropertiesRequested.connect(self.preview_panel.update_auto_roi_properties)
        except Exception:
            pass
        self.settings_panel.renameRoiRequested.connect(self.preview_panel.rename_roi)
        self.settings_panel.removeRoiRequested.connect(self.preview_panel.remove_roi)
        self.settings_panel.toggleRoiVisibilityRequested.connect(self.preview_panel.set_roi_visibility)
        self.settings_panel.changeRoiColorRequested.connect(self.preview_panel.change_roi_color)
        self.preview_panel.roiListUpdated.connect(self.settings_panel.update_roi_list)
        # Keep Feature panel's ROI dropdown in sync too
        try:
            self.preview_panel.roiListUpdated.connect(self.feature_panel.update_available_rois)
            # Seed initial ROI list if any
            if hasattr(self.preview_panel, 'roi_manager'):
                self.feature_panel.update_available_rois(self.preview_panel.roi_manager.list_summary())
        except Exception:
            pass
        self.settings_panel.selectedRoiChanged.connect(self.preview_panel.set_active_roi)
        # Keep list selection in sync when a new ROI becomes active (e.g., just added)
        try:
            self.preview_panel.activeRoiChanged.connect(self._select_roi_in_settings)
        except Exception:
            pass

        # Feature selection panel signals
        try:
            self.feature_panel.featureSettingsChanged.connect(self._update_reextract_visibility)
            self.feature_panel.reExtractOnlyRequested.connect(self.run_feature_extraction_only)
        except Exception:
            pass

        # Provide overlay preview generator to SettingsPanel (for overlay ROI dialog)
        try:
            if hasattr(self.settings_panel, 'set_overlay_preview_provider') and hasattr(self.preview_panel, 'compute_overlay_preview'):
                self.settings_panel.set_overlay_preview_provider(self.preview_panel.compute_overlay_preview)
        except Exception:
            pass

        # --- Analysis Panel Connections ---
        try:
            self.analysis_panel.loadDataRequest.connect(self.load_analysis_data)
            self.analysis_panel.runRankingAnalysis.connect(self.run_ranking_analysis)
            # --- Connections for the heatmap buttons ---
            self.analysis_panel.runUnivariateHeatmaps.connect(self.run_univariate_analysis_slot)
            self.analysis_panel.runMultivariateHeatmap.connect(self.run_multivariate_analysis_slot)
            # Result set selection
            self.analysis_panel.useResultSetRequested.connect(self._process_loaded_files)
        except Exception:
            pass

    def _select_roi_in_settings(self, roi_id: int):
        """Helper to select an ROI in the SettingsPanel list by id."""
        try:
            if hasattr(self.settings_panel, 'select_roi_by_id'):
                self.settings_panel.select_roi_by_id(roi_id)
        except Exception:
            pass

        # Note: Analysis panel signal connections are made once in _connect_signals()

    def _save_settings(self):
        """Orchestrates gathering settings from all panels and saving to a JSON file."""
        suggested_path = self.settings_file_path if self.settings_file_path else ""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Settings File", suggested_path, "JSON Files (*.json)"
        )

        if not filepath:
            return

        self.settings_file_path = filepath
        
        # Gather settings from all relevant parts of the application
        master_settings = {
            "main_window": {
                "main_directory": self.main_directory,
                "output_directory": self.output_directory,
            },
            "settings_panel": self.settings_panel.get_settings(),
            "feature_panel": self.feature_panel.get_settings(),
            "analysis_panel": self.analysis_panel.get_settings(),
            # Persist ROIs (annotations) and their configurations
            "rois": self.preview_panel.export_rois_data() if hasattr(self, 'preview_panel') else [],
        }

        try:
            import json
            with open(filepath, 'w') as f:
                json.dump(master_settings, f, indent=4)
            self.statusBar().showMessage(f"Settings successfully saved to {os.path.basename(filepath)}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save settings file: {e}")

    def _load_settings(self):
        """Orchestrates loading settings from a JSON file and distributing them to panels."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Settings File", "", "JSON Files (*.json)"
        )

        if not filepath:
            return
            
        self.settings_file_path = filepath

        try:
            import json
            with open(filepath, 'r') as f:
                master_settings = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Could not read or parse settings file: {e}")
            return

    # Distribute the loaded settings to all parts of the application
        # Use .get() to avoid errors if a key is missing in the JSON file
        
        self.settings_panel.set_settings(master_settings.get("settings_panel", {}))
        # Sync menu item with loaded verbose state
        try:
            settings_data = master_settings.get("settings_panel", {})
            self.verbose_action.setChecked(bool(settings_data.get("verbose_logging", False)))
        except Exception:
            pass
        self.feature_panel.set_settings(master_settings.get("feature_panel", {}))
        self.analysis_panel.set_settings(master_settings.get("analysis_panel", {}))

    # 2. Handle the main window settings LAST.
        main_settings = master_settings.get("main_window", {})
        
        # Load output directory (this is simple, no extra logic needed)
        output_dir = main_settings.get("output_directory")
        if output_dir and os.path.isdir(output_dir):
            self.output_directory = output_dir
            self.out_dir_label.setText(self.output_directory)
        else:
            self.output_directory = None
            self.out_dir_label.setText("Not selected.")

    # Load main data directory. This is complex and MUST trigger a full rescan.
        main_dir = main_settings.get("main_directory")
        if main_dir and os.path.isdir(main_dir):
            # Use the robust helper function we already built.
            # This correctly sets the text, scans files, updates the UI,
            # and loads the first preview image.
            self._scan_and_update_main_dir(main_dir)
        else:
            # If no valid directory is in the file, reset everything.
            self.main_directory = None
            self.dir_label.setText("Not selected.")
            self.image_pair_list = []
            self.grouped_files = {}
            # You might want to clear the preview image here as well.
        
        # 3. Restore ROIs after directory scan has loaded an initial preview image
        try:
            rois_data = master_settings.get("rois", [])
            if hasattr(self, 'preview_panel') and rois_data:
                self.preview_panel.import_rois_data(rois_data)
                # Ensure settings panel ROI list is synced
                try:
                    self.settings_panel.update_roi_list(self.preview_panel.roi_manager.list_summary())
                except Exception:
                    pass
        except Exception:
            pass

        self.statusBar().showMessage(f"Settings loaded from {os.path.basename(filepath)}", 3000)

    def select_directory(self):
        """Open a folder dialog to choose the main data directory and rescan files."""
        directory = QFileDialog.getExistingDirectory(self, "Select Data Directory")
        if directory:
            self._scan_and_update_main_dir(directory)

    def run_feature_extraction_only(self):
        """Placeholder for re-extract-only flow; currently informs user.
        TODO: Wire to feature-only worker to skip collage and reuse current settings.
        """
        try:
            QMessageBox.information(self, "Re-Extract Features", "Feature-only re-extraction will be added next. For now, run full processing.")
        except Exception:
            pass

    def _on_main_dir_edited(self):
        """Handles manual edits to the main directory path."""
        # Ignore programmatic updates or non-modified focus losses
        if getattr(self, '_suppress_dir_edit_handler', False):
            return
        try:
            if hasattr(self.dir_label, 'isModified') and not self.dir_label.isModified():
                return
        except Exception:
            pass
        path = self.dir_label.text()
        if os.path.isdir(path):
            # --- MODIFIED: Call the new helper function ---
            self._scan_and_update_main_dir(path)
            # --- END MODIFICATION ---
        elif path != self.main_directory: # Only show warning if text actually changed to something invalid
            QMessageBox.warning(self, "Invalid Path", "The entered main directory path does not exist.")
            try:
                self._suppress_dir_edit_handler = True
                self.dir_label.setText(self.main_directory if self.main_directory else "Not selected.")
                try:
                    self.dir_label.setModified(False)
                except Exception:
                    pass
            finally:
                self._suppress_dir_edit_handler = False

    def _on_out_dir_edited(self):
        """Handles manual edits to the output directory path."""
        if getattr(self, '_suppress_out_dir_edit_handler', False):
            return
        try:
            if hasattr(self.out_dir_label, 'isModified') and not self.out_dir_label.isModified():
                return
        except Exception:
            pass
        path = self.out_dir_label.text()
        if os.path.isdir(path):
            self.output_directory = path
            self.statusBar().showMessage(f"Output directory set to: {path}")
        elif path != self.output_directory:
            QMessageBox.warning(self, "Invalid Path", "The entered output directory path does not exist.")
            try:
                self._suppress_out_dir_edit_handler = True
                self.out_dir_label.setText(self.output_directory if self.output_directory else "Not selected.")
                try:
                    self.out_dir_label.setModified(False)
                except Exception:
                    pass
            finally:
                self._suppress_out_dir_edit_handler = False

    def _load_preview_by_index(self, index: int):
        """Helper function to load an image pair by its index in the list."""
        if not self.image_pair_list or not (0 <= index < len(self.image_pair_list)):
            return
        self.current_preview_index = index
        self.current_preview_paths = self.image_pair_list[self.current_preview_index]
        # This explicit call was missing, causing the delay
        self.update_live_preview()

    def load_previous_preview_image(self):
        """Loads the previous image in the list, wrapping around if necessary."""
        if not self.image_pair_list: return
        new_index = (self.current_preview_index - 1) % len(self.image_pair_list)
        self._load_preview_by_index(new_index)

    def load_next_preview_image(self):
        """Loads the next image in the list, wrapping around if necessary."""
        if not self.image_pair_list: return
        new_index = (self.current_preview_index + 1) % len(self.image_pair_list)
        self._load_preview_by_index(new_index)
        
    def load_random_preview_image(self, force: bool = False):
        """Load a random image. If force is False, ignore spurious calls after initial load.
        This prevents an unexpected first-click randomization if something emits the signal once.
        """
        if not self.image_pair_list:
            return
        # Guard: only allow randomization if explicitly forced (button click or initial load)
        if not force and getattr(self, '_did_initial_random', False):
            # Optional: small status message for diagnostics
            try:
                self.statusBar().showMessage("Ignoring non-forced random image request (guard active)", 1500)
            except Exception:
                pass
            return
        self._did_initial_random = True
        new_index = random.randint(0, len(self.image_pair_list) - 1)
        self._load_preview_by_index(new_index)
        # Optional: show which index was loaded for quick verification
        try:
            self.statusBar().showMessage(f"Loaded random preview (index {new_index})", 1500)
        except Exception:
            pass

    def load_specific_preview_image(self, filepath: str):
        parsed = parse_filename(filepath)
        if not parsed:
            QMessageBox.warning(self, "Parse Error", "Could not understand the format of the selected filename.")
            return
        animal_key = f"{parsed['date']}_{parsed['animal_id']}"
        time_point = parsed['time']
        try:
            pair_data = self.grouped_files[animal_key][time_point]
            if "WF" in pair_data and "FL" in pair_data:
                pair_to_find = (pair_data['WF'], pair_data['FL'])
                if pair_to_find in self.image_pair_list:
                    new_index = self.image_pair_list.index(pair_to_find)
                    self._load_preview_by_index(new_index)
                else:
                    QMessageBox.warning(self, "Not Found", "The image pair exists but could not be located in the preview list.")
            else:
                QMessageBox.warning(self, "Pair Incomplete", "The corresponding WF or FL image for the selected file is missing.")
        except KeyError:
            QMessageBox.warning(self, "Pair Not Found", "Could not find the corresponding animal or timepoint data.")

    def load_template_image(self, path: str):
        if path is None:
            self.template_image = None
            return
        try:
            self.template_image = imread(path)
            self.statusBar().showMessage("Reference template loaded successfully.")
            # Immediately refresh preview so registration info shows up
            try:
                self.update_live_preview()
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load template image: {e}")
            self.template_image = None

    def update_live_preview(self):
        wf_path, fl_path = self.current_preview_paths
        if not wf_path or not fl_path:
            self.preview_panel.set_file_info("N/A", "N/A")
            return
        self.preview_panel.set_file_info(wf_path, fl_path)
        try:
            # Use cache if paths unchanged
            if (self._preview_cache.get('wf_path') != wf_path) or (self._preview_cache.get('fl_path') != fl_path):
                wf_image = imread(wf_path)
                fl_image = imread(fl_path)
                self._preview_cache.update({'wf_path': wf_path, 'fl_path': fl_path, 'wf_image': wf_image, 'fl_image': fl_image})
            else:
                wf_image = self._preview_cache.get('wf_image')
                fl_image = self._preview_cache.get('fl_image')
            settings = self.settings_panel.get_settings() # We already get the settings here
            
            fl_rgb = apply_lut(fl_image, settings["min_intensity"], settings["max_intensity"], settings["lut"])
            overlay_image = create_overlay(wf_image, fl_rgb, settings["transparency"]) 

            # Update registration info overlay (dx, dy, theta)
            try:
                use_reg = bool(settings.get("use_registration", False))
                tmpl = getattr(self, 'template_image', None)
                if use_reg and tmpl is not None:
                    import cv2
                    import numpy as np
                    # Replicate registration translation computation without warping
                    wf_gray = cv2.normalize(wf_image, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                    tmpl_gray = cv2.normalize(tmpl, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                    result = cv2.matchTemplate(wf_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
                    _minVal, _maxVal, _minLoc, maxLoc = cv2.minMaxLoc(result)
                    h_img, w_img = wf_gray.shape[:2]
                    h_tmpl, w_tmpl = tmpl_gray.shape[:2]
                    match_cx = maxLoc[0] + w_tmpl / 2.0
                    match_cy = maxLoc[1] + h_tmpl / 2.0
                    frame_cx = w_img / 2.0
                    frame_cy = h_img / 2.0
                    dx = frame_cx - match_cx
                    dy = frame_cy - match_cy
                    # Estimate rotation angle using feature matching + affine model (robust to large rotations)
                    theta_deg = 0.0
                    try:
                        orb = cv2.ORB_create(nfeatures=800)
                        kf1, des1 = orb.detectAndCompute(wf_gray, None)
                        kf2, des2 = orb.detectAndCompute(tmpl_gray, None)
                        if des1 is not None and des2 is not None and len(kf1) >= 8 and len(kf2) >= 8:
                            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
                            matches = bf.knnMatch(des2, des1, k=2)  # template -> frame direction
                            good = []
                            for m, n in matches:
                                if m.distance < 0.75 * n.distance:
                                    good.append(m)
                            if len(good) >= 8:
                                src_pts = np.float32([kf2[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)  # template
                                dst_pts = np.float32([kf1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)  # frame
                                M, inliers = cv2.estimateAffinePartial2D(src_pts, dst_pts, method=cv2.RANSAC, ransacReprojThreshold=3.0)
                                if M is not None:
                                    angle_rad = np.arctan2(M[1, 0], M[0, 0])
                                    theta_deg = float(np.degrees(angle_rad))
                    except Exception:
                        theta_deg = 0.0
                    self.preview_panel.set_registration_info(dx, dy, theta_deg, enabled=True)
                else:
                    self.preview_panel.set_registration_info(0.0, 0.0, 0.0, enabled=False)
            except Exception:
                # Hide on error to avoid stale values
                try:
                    self.preview_panel.set_registration_info(0.0, 0.0, 0.0, enabled=False)
                except Exception:
                    pass

            # Draw animal outline directly on the preview image if enabled (robust to overlay widget issues)
            try:
                if bool(settings.get("show_animal_outline", False)):
                    source = str(settings.get("animal_outline_source", 'WF'))
                    method_raw = str(settings.get("animal_outline_method", 'otsu')).lower()
                    # Defensive: accept labels like 'manual threshold' as 'manual'
                    method = 'manual' if method_raw.startswith('manual') else ('otsu' if method_raw.startswith('otsu') else method_raw)
                    manual_thresh = int(settings.get("animal_outline_threshold", 5000)) if method == 'manual' else None
                    otsu_boost = int(settings.get("animal_outline_otsu_boost", 10))
                    color_val = settings.get("animal_outline_color", (0, 255, 0, 255))
                    if isinstance(color_val, (tuple, list)) and len(color_val) >= 3:
                        color_rgb = (int(color_val[0]), int(color_val[1]), int(color_val[2]))
                    elif isinstance(color_val, str) and color_val.startswith('#'):
                        from PyQt6.QtGui import QColor
                        qc = QColor(color_val)
                        color_rgb = (qc.red(), qc.green(), qc.blue())
                    else:
                        color_rgb = (0, 255, 0)
                    src_img = wf_image if source == 'WF' else fl_image
                    # Update manual-threshold control range to match data's max intensity
                    try:
                        if hasattr(self, 'settings_panel') and hasattr(self.settings_panel, 'set_outline_threshold_max') and src_img is not None:
                            # Compute maximum intensity from the source image
                            import numpy as np
                            # Use overall max across all channels/frames as an upper bound
                            max_val = int(np.max(src_img))
                            self.settings_panel.set_outline_threshold_max(max_val)
                    except Exception:
                        pass
                    contour = compute_animal_outline(src_img, method=method, threshold=manual_thresh, otsu_boost_percent=otsu_boost)
                    if contour is None and source == 'FL':  # Graceful fallback to WF if FL failed
                        contour = compute_animal_outline(wf_image, method=method, threshold=manual_thresh, otsu_boost_percent=otsu_boost)
                    if contour is not None:
                        overlay_image = draw_outline_on_image(overlay_image, contour, color_rgb, thickness=3)
            except Exception:
                # Non-fatal for preview
                pass
            
            if not overlay_image.flags['C_CONTIGUOUS']:
                overlay_image = np.ascontiguousarray(overlay_image)
            h, w, ch = overlay_image.shape
            q_image = QImage(overlay_image.data, w, h, ch * w, QImage.Format.Format_RGB888)
            
            # --- MODIFIED: Pass the 'settings' dictionary to the preview panel ---
            self.preview_panel.update_preview(QPixmap.fromImage(q_image.copy()), settings)
            # --- END MODIFICATION ---

        except Exception as e:
            self.statusBar().showMessage(f"Error updating preview: {e}")

    def _get_first_image_size(self) -> tuple[int, int]:
        """Return (width, height) of the first available WF image, or (0,0) if unavailable."""
        try:
            if self.image_pair_list:
                wf_path, _ = self.image_pair_list[0]
                img = imread(wf_path)
                if img is not None:
                    # tifffile returns arrays as HxW or HxWxC
                    h, w = img.shape[:2]
                    return (int(w), int(h))
        except Exception:
            pass
        return (0, 0)

    def run_processing(self):

        print("\n--- DEBUG: run_processing START ---")

        if not self.main_directory or not self.output_directory:
            QMessageBox.critical(self, "Input Required", "Please select both a data and an output directory.")
            return
        # Ensure we actually have files to process (user might not have scanned a valid folder)
        if not getattr(self, 'grouped_files', None) or len(self.grouped_files) == 0:
            QMessageBox.warning(self, "No Files Found", "No valid WF/FL image pairs were found in the selected data directory. Please select a folder with TIFF files via 'Select Data Directory'.")
            try:
                self.statusBar().showMessage("No files found to process.")
            except Exception:
                pass
            return
        if not getattr(self, 'image_pair_list', None) or len(self.image_pair_list) == 0:
            QMessageBox.warning(self, "No Pairs Found", "No WF/FL pairs were detected. Please verify your data directory.")
            try:
                self.statusBar().showMessage("No image pairs available for processing.")
            except Exception:
                pass
            return
        settings = self.settings_panel.get_settings()
        if settings["use_registration"] and self.template_image is None:
            QMessageBox.critical(self, "Input Required", "Registration is enabled, but no reference template has been loaded.")
            return
        # Honor Apply Crop option
        apply_crop = bool(settings.get("apply_crop", True))
        if apply_crop:
            current_roi = self.preview_panel.get_roi()
            if current_roi.isNull() or current_roi.width() <= 1 or current_roi.height() <= 1:
                QMessageBox.critical(self, "Input Required", "Please select a valid cropping region (ROI).")
                return
        else:
            # Use full-frame ROI derived from the first image
            w, h = self._get_first_image_size()
            if w <= 0 or h <= 0:
                # Fallback to current ROI if size couldn't be determined
                current_roi = self.preview_panel.get_roi()
            else:
                current_roi = QRect(0, 0, w, h)

        visual_settings = self.settings_panel.get_settings()
        feature_settings = self.feature_panel.get_feature_settings()

        # --- We need the list of specific feature names for filtering ---
        # The get_feature_settings method needs to be updated to provide this.
        # For now, let's assume it does.
        # Include ROI definitions so the worker can use ROI masks for feature extraction
        try:
            rois_data = self.preview_panel.export_rois_data()
        except Exception:
            rois_data = []
        all_settings = {**visual_settings, **feature_settings, "roi_list": rois_data}

        # --- Track signature for this run ---
        self._current_run_feature_signature = self._get_feature_signature()
        # Provide a deterministic tag for filenames
        tag = self._compute_feature_tag(self._current_run_feature_signature)
        all_settings["feature_tag"] = tag

        # Disable only configuration groups; keep control buttons responsive
        try:
            if hasattr(self.settings_panel, 'set_config_enabled'):
                self.settings_panel.set_config_enabled(False)
            else:
                self.settings_panel.setEnabled(False)
        except Exception:
            self.settings_panel.setEnabled(False)
        self.feature_panel.setEnabled(False) # Disable this panel too
        self.dir_button.setEnabled(False)
        self.out_dir_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # 1. Create the thread and worker
        print("--- DEBUG: Creating Worker and QThread ---")

        self.worker_thread = QThread()
        self.worker = Worker(self.grouped_files, all_settings, current_roi, self.output_directory)
        
        # 2. Move worker to the thread
        self.worker.moveToThread(self.worker_thread)
        
        # 3. Connect signals
        print("--- DEBUG: Connecting worker signals ---")

        self.worker_thread.started.connect(self.worker.run)
        
        self.worker.finished.connect(self.worker_thread.quit) # Tell the thread to stop when worker is done
        
        # When the thread is finished, it's safe to delete everything and clean up
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(self.on_processing_finished) # Call our cleanup/message slot LAST
        
        # Connect other signals
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.status.connect(self.statusBar().showMessage)
        self.worker.error.connect(self.on_processing_error)
        self.worker.featureCsvReady.connect(self.on_feature_csv_ready)

        # 4. Start the thread
        print("--- DEBUG: Starting worker thread ---")
        # Reset outcome flags at the start of a run
        self._proc_error_message = None
        self._proc_aborted = False
        self._proc_stopped = False

        self.worker_thread.start()
        print("--- DEBUG: run_processing END ---")
        # Switch UI to processing controls
        self._enter_processing_controls()
        # Immediate user feedback
        try:
            self.statusBar().showMessage("Processing started…")
        except Exception:
            pass

    @pyqtSlot()
    def pause_processing(self):
        if getattr(self, 'worker', None) is None:
            return
        try:
            if hasattr(self.worker, 'pause'):
                self.worker.pause()
            self.statusBar().showMessage("Processing paused.\u00A0")
            self._enter_paused_controls()
        except Exception:
            pass

    @pyqtSlot()
    def resume_processing(self):
        if getattr(self, 'worker', None) is None:
            return
        try:
            if hasattr(self.worker, 'resume'):
                self.worker.resume()
            self.statusBar().showMessage("Resuming processing…")
            self._enter_processing_controls()
        except Exception:
            pass

    @pyqtSlot()
    def request_abort_processing(self):
        if getattr(self, 'worker', None) is None:
            return
        confirm = QMessageBox.question(
            self,
            "Abort Processing",
            "Are you sure you want to abort the current processing run?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                # Mark as aborted by user for final outcome message
                self._proc_aborted = True
                if hasattr(self.worker, 'stop'):
                    self.worker.stop()
                self.statusBar().showMessage("Aborting…")
            except Exception:
                pass

    @pyqtSlot()
    def stop_processing(self):
        if getattr(self, 'worker', None) is None:
            return
        try:
            # Mark as stopped for final outcome message
            self._proc_stopped = True
            if hasattr(self.worker, 'stop'):
                self.worker.stop()
            self.statusBar().showMessage("Stopping…")
        except Exception:
            pass

    @pyqtSlot(str)
    def on_processing_error(self, error_message: str):
        """Handle errors emitted from the worker thread in a centralized way."""
        try:
            self._proc_error_message = error_message or "Unknown error"
            # Show in status bar immediately; detailed box will be shown on finish
            self.statusBar().showMessage(f"Failed: {self._proc_error_message}")
        except Exception:
            pass

    @pyqtSlot()
    def on_processing_finished(self):
        """Clean up UI and inform the user about the processing outcome."""
        try:
            # Hide progress and re-enable controls
            self.progress_bar.setVisible(False)
            try:
                if hasattr(self.settings_panel, 'set_config_enabled'):
                    self.settings_panel.set_config_enabled(True)
                else:
                    self.settings_panel.setEnabled(True)
            except Exception:
                self.settings_panel.setEnabled(True)
            try:
                self.feature_panel.setEnabled(True)
            except Exception:
                pass
            try:
                self.dir_button.setEnabled(True)
                self.out_dir_button.setEnabled(True)
            except Exception:
                pass

            # Footer controls back to idle
            self._enter_idle_controls()

            # Outcome messaging
            if self._proc_error_message:
                QMessageBox.critical(self, "Processing Error", self._proc_error_message)
                self.statusBar().showMessage(f"Failed: {self._proc_error_message}")
            elif self._proc_aborted:
                QMessageBox.information(self, "Aborted", "Processing was aborted by the user.")
                self.statusBar().showMessage("Processing aborted.")
            elif self._proc_stopped:
                QMessageBox.information(self, "Stopped", "Processing was stopped.")
                self.statusBar().showMessage("Processing stopped.")
            else:
                self.statusBar().showMessage("Processing complete!")
                # Optional success dialog for clear feedback
                QMessageBox.information(self, "Success", "Batch processing has completed successfully!")
        finally:
            # Clear worker/thread refs
            try:
                self.worker_thread = None
            except Exception:
                pass
            try:
                self.worker = None
            except Exception:
                pass

    @pyqtSlot(str)
    def on_feature_csv_ready(self, raw_path: str):
        """
        This slot now ONLY loads the data and enables the analysis UI.
        It no longer automatically triggers the next analysis step.
        """
        self.statusBar().showMessage("Feature CSVs created. Loading data for analysis panels...")
        
        # Record the signature that produced this file
        if self._current_run_feature_signature is not None:
            self._last_feature_signature = self._current_run_feature_signature
            self._current_run_feature_signature = None
        # Hide the re-extract button (we are up-to-date now)
        try:
            self.feature_panel.set_reextract_visible(False)
        except Exception:
            pass
        # Refresh available result sets in Analysis panel
        self._refresh_available_result_sets()
        
        # We still call _process_loaded_files to load the data into memory
        # and populate the dropdowns.
        self._process_loaded_files(raw_path)
        print("\n--- DEBUG: End of on_feature_csv_ready. ---")


    def load_analysis_data(self):
        """Opens a file dialog for the user to select any feature CSV."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, 
            "Load Feature CSV File", 
            "", 
            "Feature CSV Files (*_Results.csv *_Summary.csv)"
        )
        if filepath:
            self._process_loaded_files(filepath)

    def _process_loaded_files(self, filepath: str):
        """
        Central logic to handle loading either a Raw or Summary CSV.
        """
        self.raw_csv_path = None
        self.summary_csv_path = None
        self.raw_features_df = None
        
        try:
            if filepath.endswith("_Raw_Results.csv"):
                self.raw_csv_path = filepath
                self.statusBar().showMessage(f"Loading raw data from {os.path.basename(filepath)}...")
                self.raw_features_df = pd.read_csv(self.raw_csv_path)
                # Normalize feature names by stripping leading 'original' prefixes if present
                try:
                    id_cols = ['group_name', 'Group_Number', 'Sex', 'Dose', 'Treatment', 'animal_key', 'time_min']
                    rename_map = {}
                    for col in list(self.raw_features_df.columns):
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
                        self.raw_features_df.rename(columns=rename_map, inplace=True)
                except Exception:
                    pass
                
                self.statusBar().showMessage("Generating summary statistics from raw data...")
                summary_df = summarize_features_by_group(self.raw_features_df.copy())
                
                if not summary_df.empty:
                    # Persist the summary to disk so downstream heatmap generation can read it
                    self.summary_csv_path = self.raw_csv_path.replace("_Raw_Results.csv", "_Group_Summary.csv")
                    try:
                        summary_df.to_csv(self.summary_csv_path, index=False)
                    except Exception as e:
                        # Fall back to disabling heatmaps if we cannot write the file
                        self.analysis_panel.enable_buttons(raw_csv_ready=True, summary_csv_ready=False)
                        self.statusBar().showMessage(f"Summary generated but could not be saved: {e}. Heatmaps disabled.")
                    else:
                        self.analysis_panel.enable_buttons(raw_csv_ready=True, summary_csv_ready=True)
                        self.statusBar().showMessage("Raw data loaded. All analyses enabled.")
                else:
                    self.analysis_panel.enable_buttons(raw_csv_ready=True, summary_csv_ready=False)
                    self.statusBar().showMessage("Raw data loaded. Summary generation failed. Heatmaps disabled.")

                # After loading the raw data, we now have the info needed to populate the dropdowns.
                all_groups = sorted(self.raw_features_df['group_name'].unique())
                potential_factors = ['Sex', 'Dose', 'Treatment', 'Group_Number']
                available_factors = [f for f in potential_factors if f in self.raw_features_df.columns]
                
                # --- DEBUGGING BLOCK ---
                print("\n--- DEBUG: Inside MainWindow._process_loaded_files ---")
                all_groups = sorted(self.raw_features_df['group_name'].unique())
                potential_factors = ['Sex', 'Dose', 'Treatment', 'Group_Number']
                available_factors = [f for f in potential_factors if f in self.raw_features_df.columns]
                
                print(f"Found Groups: {all_groups}")
                print(f"Found Factors: {available_factors}")
                print("Calling analysis_panel.populate_factor_dropdowns...")

                # Call the function in AnalysisPanel to update its UI
                self.analysis_panel.populate_factor_dropdowns(available_factors, all_groups)

                print("--- DEBUG: Finished populate_factor_dropdowns call ---\n")       
                print("--- DEBUG: Automatically run the initial overall ranking ---\n")       

                # Automatically run the initial overall ranking
                self.run_ranking_analysis({"type": "Overall"})
                print("--- DEBUG: Done with Automatically run the initial overall ranking ---\n")       



            elif filepath.endswith("_Group_Summary.csv"):
                self.summary_csv_path = filepath
                self.statusBar().showMessage(f"Loaded summary data from {os.path.basename(filepath)}. Heatmap analysis enabled.")
                self.analysis_panel.enable_buttons(raw_csv_ready=False, summary_csv_ready=True)
                # We can't populate hypothesis dropdowns from summary data, so we clear them
                self.analysis_panel.populate_factor_dropdowns([], [])
            
            else:
                QMessageBox.warning(self, "Invalid File Type", "Please select a valid '_Raw_Results.csv' or '_Group_Summary.csv' file.")
                self.analysis_panel.enable_buttons(raw_csv_ready=False, summary_csv_ready=False)
                return

            self.analysis_panel.set_loaded_file_label(filepath)

        except Exception as e:
            error_str = f"An error occurred while loading or processing the CSV file: {e}\n\n{traceback.format_exc()}"
            QMessageBox.critical(self, "File Load Error", error_str)
            self.analysis_panel.set_loaded_file_label("")
            self.analysis_panel.enable_buttons(raw_csv_ready=False, summary_csv_ready=False)

    @pyqtSlot(dict)
    def run_ranking_analysis(self, params: dict):
        """
        Launches the RankingWorker thread. This is the slot connected to the UI.
        """
        if self.raw_features_df is None or self.raw_features_df.empty:
            QMessageBox.warning(self, "No Data", "Raw feature data is not loaded.")
            return

        # Dynamically get factor levels for Interaction analysis
        if params.get("type") == "Interaction":
            factor1 = self.analysis_panel.factor1_combo.currentText()
            factor2 = self.analysis_panel.factor2_combo.currentText()
            if not factor1 or not factor2 or factor1 == factor2:
                QMessageBox.warning(self, "Invalid Selection", "Please select two different factors.")
                return
            f1_levels = sorted(self.raw_features_df[factor1].unique().tolist())
            f2_levels = sorted(self.raw_features_df[factor2].unique().tolist())
            if len(f1_levels) < 2 or len(f2_levels) < 2:
                QMessageBox.warning(self, "Invalid Data", "Both factors must have at least 2 levels.")
                return
            params["factor1_col"], params["factor1_levels"] = factor1, f1_levels[:2]
            params["factor2_col"], params["factor2_levels"] = factor2, f2_levels[:2]
        
        self.analysis_panel.setEnabled(False)
        self.statusBar().showMessage(f"Running '{params.get('type')}' ranking analysis...")
        
        self.ranking_thread = QThread()
        self.ranking_worker = RankingWorker(self.raw_features_df, params)
        self.ranking_worker.moveToThread(self.ranking_thread)
        
        self.ranking_thread.started.connect(self.ranking_worker.run)
        self.ranking_worker.error.connect(lambda msg: QMessageBox.critical(self, "Ranking Error", msg))
        # Accept the emitted error string to match the signal signature and ensure the panel re-enables on error
        self.ranking_worker.error.connect(lambda msg: self.analysis_panel.setEnabled(True))
        self.ranking_worker.finished.connect(self.on_ranking_finished)
        self.ranking_worker.finished.connect(self.ranking_thread.quit)
        self.ranking_worker.finished.connect(self.ranking_worker.deleteLater)
        self.ranking_thread.finished.connect(self.ranking_thread.deleteLater)
        self.ranking_thread.start()

    @pyqtSlot(pd.DataFrame, dict)
    def on_ranking_finished(self, results_df, params):
        """
        This slot receives the results from the RankingWorker and updates the UI.
        """
        analysis_type = params.get("type", "Unknown")
        metadata = f"Feature Ranking Results\nAnalysis Type: {analysis_type}\n"
        if analysis_type == "Interaction":
            metadata += f"Factor 1: {params['factor1_col']} (Levels: {', '.join(params['factor1_levels'])})\n"
            metadata += f"Factor 2: {params['factor2_col']} (Levels: {', '.join(params['factor2_levels'])})"
        elif analysis_type == "Normalization":
            metadata += f"Baseline: {params['baseline_group']}\nAffected: {params['affected_group']}\nTreated: {params['treated_group']}"
        elif analysis_type == "Overall":
            if results_df is not None and not results_df.empty:
                score_columns = [col for col in results_df.columns if col != 'Feature']
                metadata += "Based on: " + " and ".join(score_columns)
        
        self.analysis_panel.set_analysis_metadata(metadata)
        self.analysis_panel.display_ranking_results(results_df)
        self.statusBar().showMessage(f"'{analysis_type}' ranking complete.")
        self.analysis_panel.setEnabled(True)

    def on_summary_csv_selected(self, path: str):
        """Slot for when user manually loads a summary CSV for heatmaps."""
        self.summary_csv_path = path
        # Enable only the heatmap buttons
        self.analysis_panel.enable_buttons(raw_csv_ready=False, summary_csv_ready=True)
        self.statusBar().showMessage(f"Loaded summary file: {os.path.basename(path)}")

    @pyqtSlot(str, bool, str)
    def run_univariate_analysis_slot(self, _, show_plot, agg_method):
        """Slot specifically for the univariate button."""
        self._launch_heatmap_worker('univariate', show_plot, agg_method)
        

    def _on_main_dir_edited(self):
        """Handles manual edits to the main directory path."""
        # Ignore programmatic updates or non-modified focus losses
        if getattr(self, '_suppress_dir_edit_handler', False):
            return
        try:
            if hasattr(self.dir_label, 'isModified') and not self.dir_label.isModified():
                return
        except Exception:
            pass
        path = self.dir_label.text()
        if os.path.isdir(path):
            # --- MODIFIED: Call the new helper function ---
            self._scan_and_update_main_dir(path)
            # --- END MODIFICATION ---
        elif path != self.main_directory: # Only show warning if text actually changed to something invalid
            QMessageBox.warning(self, "Invalid Path", "The entered main directory path does not exist.")
            try:
                self._suppress_dir_edit_handler = True
                self.dir_label.setText(self.main_directory if self.main_directory else "Not selected.")
                try:
                    self.dir_label.setModified(False)
                except Exception:
                    pass
            finally:
                self._suppress_dir_edit_handler = False

    def _on_out_dir_edited(self):
        """Handles manual edits to the output directory path."""
        if getattr(self, '_suppress_out_dir_edit_handler', False):
            return
        try:
            if hasattr(self.out_dir_label, 'isModified') and not self.out_dir_label.isModified():
                return
        except Exception:
            pass
        path = self.out_dir_label.text()
        if os.path.isdir(path):
            self.output_directory = path
            self.statusBar().showMessage(f"Output directory set to: {path}")
        elif path != self.output_directory:
            QMessageBox.warning(self, "Invalid Path", "The entered output directory path does not exist.")
            try:
                self._suppress_out_dir_edit_handler = True
                self.out_dir_label.setText(self.output_directory if self.output_directory else "Not selected.")
                try:
                    self.out_dir_label.setModified(False)
                except Exception:
                    pass
            finally:
                self._suppress_out_dir_edit_handler = False

    def _load_preview_by_index(self, index: int):
        """Helper function to load an image pair by its index in the list."""
        if not self.image_pair_list or not (0 <= index < len(self.image_pair_list)):
            return
        self.current_preview_index = index
        self.current_preview_paths = self.image_pair_list[self.current_preview_index]
        # This explicit call was missing, causing the delay
        self.update_live_preview()

    def load_previous_preview_image(self):
        """Loads the previous image in the list, wrapping around if necessary."""
        if not self.image_pair_list: return
        new_index = (self.current_preview_index - 1) % len(self.image_pair_list)
        self._load_preview_by_index(new_index)

    def load_next_preview_image(self):
        """Loads the next image in the list, wrapping around if necessary."""
        if not self.image_pair_list: return
        new_index = (self.current_preview_index + 1) % len(self.image_pair_list)
        self._load_preview_by_index(new_index)
        
    def load_random_preview_image(self, force: bool = False):
        """Load a random image. If force is False, ignore spurious calls after initial load.
        This prevents an unexpected first-click randomization if something emits the signal once.
        """
        if not self.image_pair_list:
            return
        # Guard: only allow randomization if explicitly forced (button click or initial load)
        if not force and getattr(self, '_did_initial_random', False):
            # Optional: small status message for diagnostics
            try:
                self.statusBar().showMessage("Ignoring non-forced random image request (guard active)", 1500)
            except Exception:
                pass
            return
        self._did_initial_random = True
        new_index = random.randint(0, len(self.image_pair_list) - 1)
        self._load_preview_by_index(new_index)
        # Optional: show which index was loaded for quick verification
        try:
            self.statusBar().showMessage(f"Loaded random preview (index {new_index})", 1500)
       
        except Exception:
            pass

    def load_specific_preview_image(self, filepath: str):
        parsed = parse_filename(filepath)
        if not parsed:
            QMessageBox.warning(self, "Parse Error", "Could not understand the format of the selected filename.")
            return
        animal_key = f"{parsed['date']}_{parsed['animal_id']}"
        time_point = parsed['time']
        try:
            pair_data = self.grouped_files[animal_key][time_point]
            if "WF" in pair_data and "FL" in pair_data:
                pair_to_find = (pair_data['WF'], pair_data['FL'])
                if pair_to_find in self.image_pair_list:
                    new_index = self.image_pair_list.index(pair_to_find)
                    self._load_preview_by_index(new_index)
                else:
                    QMessageBox.warning(self, "Not Found", "The image pair exists but could not be located in the preview list.")
            else:
                QMessageBox.warning(self, "Pair Incomplete", "The corresponding WF or FL image for the selected file is missing.")
        except KeyError:
            QMessageBox.warning(self, "Pair Not Found", "Could not find the corresponding animal or timepoint data.")

    def load_template_image(self, path: str):
        if path is None:
            self.template_image = None
            return
        try:
            self.template_image = imread(path)
            self.statusBar().showMessage("Reference template loaded successfully.")
            # Immediately refresh preview so registration info shows up
            try:
                self.update_live_preview()
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load template image: {e}")
            self.template_image = None

    def update_live_preview(self):
        wf_path, fl_path = self.current_preview_paths
        if not wf_path or not fl_path:
            self.preview_panel.set_file_info("N/A", "N/A")
            return
        self.preview_panel.set_file_info(wf_path, fl_path)
        try:
            # Use cache if paths unchanged
            if (self._preview_cache.get('wf_path') != wf_path) or (self._preview_cache.get('fl_path') != fl_path):
                wf_image = imread(wf_path)
                fl_image = imread(fl_path)
                self._preview_cache.update({'wf_path': wf_path, 'fl_path': fl_path, 'wf_image': wf_image, 'fl_image': fl_image})
            else:
                wf_image = self._preview_cache.get('wf_image')
                fl_image = self._preview_cache.get('fl_image')
            settings = self.settings_panel.get_settings() # We already get the settings here
            
            fl_rgb = apply_lut(fl_image, settings["min_intensity"], settings["max_intensity"], settings["lut"])
            overlay_image = create_overlay(wf_image, fl_rgb, settings["transparency"]) 

            # Update registration info overlay (dx, dy, theta)
            try:
                use_reg = bool(settings.get("use_registration", False))
                tmpl = getattr(self, 'template_image', None)
                if use_reg and tmpl is not None:
                    import cv2
                    import numpy as np
                    # Replicate registration translation computation without warping
                    wf_gray = cv2.normalize(wf_image, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                    tmpl_gray = cv2.normalize(tmpl, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                    result = cv2.matchTemplate(wf_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
                    _minVal, _maxVal, _minLoc, maxLoc = cv2.minMaxLoc(result)
                    h_img, w_img = wf_gray.shape[:2]
                    h_tmpl, w_tmpl = tmpl_gray.shape[:2]
                    match_cx = maxLoc[0] + w_tmpl / 2.0
                    match_cy = maxLoc[1] + h_tmpl / 2.0
                    frame_cx = w_img / 2.0
                    frame_cy = h_img / 2.0
                    dx = frame_cx - match_cx
                    dy = frame_cy - match_cy
                    # Estimate rotation angle using feature matching + affine model (robust to large rotations)
                    theta_deg = 0.0
                    try:
                        orb = cv2.ORB_create(nfeatures=800)
                        kf1, des1 = orb.detectAndCompute(wf_gray, None)
                        kf2, des2 = orb.detectAndCompute(tmpl_gray, None)
                        if des1 is not None and des2 is not None and len(kf1) >= 8 and len(kf2) >= 8:
                            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
                            matches = bf.knnMatch(des2, des1, k=2)  # template -> frame direction
                            good = []
                            for m, n in matches:
                                if m.distance < 0.75 * n.distance:
                                    good.append(m)
                            if len(good) >= 8:
                                src_pts = np.float32([kf2[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)  # template
                                dst_pts = np.float32([kf1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)  # frame
                                M, inliers = cv2.estimateAffinePartial2D(src_pts, dst_pts, method=cv2.RANSAC, ransacReprojThreshold=3.0)
                                if M is not None:
                                    angle_rad = np.arctan2(M[1, 0], M[0, 0])
                                    theta_deg = float(np.degrees(angle_rad))
                    except Exception:
                        theta_deg = 0.0
                    self.preview_panel.set_registration_info(dx, dy, theta_deg, enabled=True)
                else:
                    self.preview_panel.set_registration_info(0.0, 0.0, 0.0, enabled=False)
            except Exception:
                # Hide on error to avoid stale values
                try:
                    self.preview_panel.set_registration_info(0.0, 0.0, 0.0, enabled=False)
                except Exception:
                    pass

            # Draw animal outline directly on the preview image if enabled (robust to overlay widget issues)
            try:
                if bool(settings.get("show_animal_outline", False)):
                    source = str(settings.get("animal_outline_source", 'WF'))
                    method_raw = str(settings.get("animal_outline_method", 'otsu')).lower()
                    # Defensive: accept labels like 'manual threshold' as 'manual'
                    method = 'manual' if method_raw.startswith('manual') else ('otsu' if method_raw.startswith('otsu') else method_raw)
                    manual_thresh = int(settings.get("animal_outline_threshold", 5000)) if method == 'manual' else None
                    otsu_boost = int(settings.get("animal_outline_otsu_boost", 10))
                    color_val = settings.get("animal_outline_color", (0, 255, 0, 255))
                    if isinstance(color_val, (tuple, list)) and len(color_val) >= 3:
                        color_rgb = (int(color_val[0]), int(color_val[1]), int(color_val[2]))
                    elif isinstance(color_val, str) and color_val.startswith('#'):
                        from PyQt6.QtGui import QColor
                        qc = QColor(color_val)
                        color_rgb = (qc.red(), qc.green(), qc.blue())
                    else:
                        color_rgb = (0, 255, 0)
                    src_img = wf_image if source == 'WF' else fl_image
                    # Update manual-threshold control range to match data's max intensity
                    try:
                        if hasattr(self, 'settings_panel') and hasattr(self.settings_panel, 'set_outline_threshold_max') and src_img is not None:
                            # Compute maximum intensity from the source image
                            import numpy as np
                            # Use overall max across all channels/frames as an upper bound
                            max_val = int(np.max(src_img))
                            self.settings_panel.set_outline_threshold_max(max_val)
                    except Exception:
                        pass
                    contour = compute_animal_outline(src_img, method=method, threshold=manual_thresh, otsu_boost_percent=otsu_boost)
                    if contour is None and source == 'FL':  # Graceful fallback to WF if FL failed
                        contour = compute_animal_outline(wf_image, method=method, threshold=manual_thresh, otsu_boost_percent=otsu_boost)
                    if contour is not None:
                        overlay_image = draw_outline_on_image(overlay_image, contour, color_rgb, thickness=3)
            except Exception:
                # Non-fatal for preview
                pass
            
            if not overlay_image.flags['C_CONTIGUOUS']:
                overlay_image = np.ascontiguousarray(overlay_image)
            h, w, ch = overlay_image.shape
            q_image = QImage(overlay_image.data, w, h, ch * w, QImage.Format.Format_RGB888)
            
            # --- MODIFIED: Pass the 'settings' dictionary to the preview panel ---
            self.preview_panel.update_preview(QPixmap.fromImage(q_image.copy()), settings)
            # --- END MODIFICATION ---

        except Exception as e:
            self.statusBar().showMessage(f"Error updating preview: {e}")

    def _get_first_image_size(self) -> tuple[int, int]:
        """Return (width, height) of the first available WF image, or (0,0) if unavailable."""
        try:
            if self.image_pair_list:
                wf_path, _ = self.image_pair_list[0]
                img = imread(wf_path)
                if img is not None:
                    # tifffile returns arrays as HxW or HxWxC
                    h, w = img.shape[:2]
                    return (int(w), int(h))
        except Exception:
            pass
        return (0, 0)

    def run_processing(self):

        print("\n--- DEBUG: run_processing START ---")

        if not self.main_directory or not self.output_directory:
            QMessageBox.critical(self, "Input Required", "Please select both a data and an output directory.")
            return
        # Ensure we actually have files to process (user might not have scanned a valid folder)
        if not getattr(self, 'grouped_files', None) or len(self.grouped_files) == 0:
            QMessageBox.warning(self, "No Files Found", "No valid WF/FL image pairs were found in the selected data directory. Please select a folder with TIFF files via 'Select Data Directory'.")
            try:
                self.statusBar().showMessage("No files found to process.")
            except Exception:
                pass
            return
        if not getattr(self, 'image_pair_list', None) or len(self.image_pair_list) == 0:
            QMessageBox.warning(self, "No Pairs Found", "No WF/FL pairs were detected. Please verify your data directory.")
            try:
                self.statusBar().showMessage("No image pairs available for processing.")
            except Exception:
                pass
            return
        settings = self.settings_panel.get_settings()
        if settings["use_registration"] and self.template_image is None:
            QMessageBox.critical(self, "Input Required", "Registration is enabled, but no reference template has been loaded.")
            return
        # Honor Apply Crop option
        apply_crop = bool(settings.get("apply_crop", True))
        if apply_crop:
            current_roi = self.preview_panel.get_roi()
            if current_roi.isNull() or current_roi.width() <= 1 or current_roi.height() <= 1:
                QMessageBox.critical(self, "Input Required", "Please select a valid cropping region (ROI).")
                return
        else:
            # Use full-frame ROI derived from the first image
            w, h = self._get_first_image_size()
            if w <= 0 or h <= 0:
                # Fallback to current ROI if size couldn't be determined
                current_roi = self.preview_panel.get_roi()
            else:
                current_roi = QRect(0, 0, w, h)

        visual_settings = self.settings_panel.get_settings()
        feature_settings = self.feature_panel.get_feature_settings()

        # --- We need the list of specific feature names for filtering ---
        # The get_feature_settings method needs to be updated to provide this.
        # For now, let's assume it does.
        # Include ROI definitions so the worker can use ROI masks for feature extraction
        try:
            rois_data = self.preview_panel.export_rois_data()
        except Exception:
            rois_data = []
        all_settings = {**visual_settings, **feature_settings, "roi_list": rois_data}

        # --- Track signature for this run ---
        self._current_run_feature_signature = self._get_feature_signature()
        # Provide a deterministic tag for filenames
        tag = self._compute_feature_tag(self._current_run_feature_signature)
        all_settings["feature_tag"] = tag

        # Disable only configuration groups; keep control buttons responsive
        try:
            if hasattr(self.settings_panel, 'set_config_enabled'):
                self.settings_panel.set_config_enabled(False)
            else:
                self.settings_panel.setEnabled(False)
        except Exception:
            self.settings_panel.setEnabled(False)
        self.feature_panel.setEnabled(False) # Disable this panel too
        self.dir_button.setEnabled(False)
        self.out_dir_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # 1. Create the thread and worker
        print("--- DEBUG: Creating Worker and QThread ---")

        self.worker_thread = QThread()
        self.worker = Worker(self.grouped_files, all_settings, current_roi, self.output_directory)
        
        # 2. Move worker to the thread
        self.worker.moveToThread(self.worker_thread)
        
        # 3. Connect signals
        print("--- DEBUG: Connecting worker signals ---")

        self.worker_thread.started.connect(self.worker.run)
        
        self.worker.finished.connect(self.worker_thread.quit) # Tell the thread to stop when worker is done
        
        # When the thread is finished, it's safe to delete everything and clean up
        self.worker_thread.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(self.on_processing_finished) # Call our cleanup/message slot LAST
        
        # Connect other signals
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.status.connect(self.statusBar().showMessage)
        self.worker.error.connect(self.on_processing_error)
        self.worker.featureCsvReady.connect(self.on_feature_csv_ready)

        # 4. Start the thread
        print("--- DEBUG: Starting worker thread ---")
        # Reset outcome flags at the start of a run
        self._proc_error_message = None
        self._proc_aborted = False
        self._proc_stopped = False

        self.worker_thread.start()
        print("--- DEBUG: run_processing END ---")
        # Switch UI to processing controls
        self._enter_processing_controls()
        # Immediate user feedback
        try:
            self.statusBar().showMessage("Processing started…")
        except Exception:
            pass

    @pyqtSlot()
    def pause_processing(self):
        if getattr(self, 'worker', None) is None:
            return
        try:
            if hasattr(self.worker, 'pause'):
                self.worker.pause()
            self.statusBar().showMessage("Processing paused.\u00A0")
            self._enter_paused_controls()
        except Exception:
            pass

    @pyqtSlot()
    def resume_processing(self):
        if getattr(self, 'worker', None) is None:
            return
        try:
            if hasattr(self.worker, 'resume'):
                self.worker.resume()
            self.statusBar().showMessage("Resuming processing…")
            self._enter_processing_controls()
        except Exception:
            pass

    @pyqtSlot()
    def request_abort_processing(self):
        if getattr(self, 'worker', None) is None:
            return
        confirm = QMessageBox.question(
            self,
            "Abort Processing",
            "Are you sure you want to abort the current processing run?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                # Mark as aborted by user for final outcome message
                self._proc_aborted = True
                if hasattr(self.worker, 'stop'):
                    self.worker.stop()
                self.statusBar().showMessage("Aborting…")
            except Exception:
                pass

    @pyqtSlot()
    def stop_processing(self):
        if getattr(self, 'worker', None) is None:
            return
        try:
            # Mark as stopped for final outcome message
            self._proc_stopped = True
            if hasattr(self.worker, 'stop'):
                self.worker.stop()
            self.statusBar().showMessage("Stopping…")
        except Exception:
            pass

    @pyqtSlot(str)
    def on_feature_csv_ready(self, raw_path: str):
        """
        This slot now ONLY loads the data and enables the analysis UI.
        It no longer automatically triggers the next analysis step.
        """
        self.statusBar().showMessage("Feature CSVs created. Loading data for analysis panels...")
        
        # Record the signature that produced this file
        if self._current_run_feature_signature is not None:
            self._last_feature_signature = self._current_run_feature_signature
            self._current_run_feature_signature = None
        # Hide the re-extract button (we are up-to-date now)
        try:
            self.feature_panel.set_reextract_visible(False)
        except Exception:
            pass
        # Refresh available result sets in Analysis panel
        self._refresh_available_result_sets()
        
        # We still call _process_loaded_files to load the data into memory
        # and populate the dropdowns.
        self._process_loaded_files(raw_path)
        print("\n--- DEBUG: End of on_feature_csv_ready. ---")


    def load_analysis_data(self):
        """Opens a file dialog for the user to select any feature CSV."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, 
            "Load Feature CSV File", 
            "", 
            "Feature CSV Files (*_Results.csv *_Summary.csv)"
        )
        if filepath:
            self._process_loaded_files(filepath)

    def _process_loaded_files(self, filepath: str):
        """
        Central logic to handle loading either a Raw or Summary CSV.
        """
        self.raw_csv_path = None
        self.summary_csv_path = None
        self.raw_features_df = None
        
        try:
            if filepath.endswith("_Raw_Results.csv"):
                self.raw_csv_path = filepath
                self.statusBar().showMessage(f"Loading raw data from {os.path.basename(filepath)}...")
                self.raw_features_df = pd.read_csv(self.raw_csv_path)
                # Normalize feature names by stripping leading 'original' prefixes if present
                try:
                    id_cols = ['group_name', 'Group_Number', 'Sex', 'Dose', 'Treatment', 'animal_key', 'time_min']
                    rename_map = {}
                    for col in list(self.raw_features_df.columns):
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
                        self.raw_features_df.rename(columns=rename_map, inplace=True)
                except Exception:
                    pass
                
                self.statusBar().showMessage("Generating summary statistics from raw data...")
                summary_df = summarize_features_by_group(self.raw_features_df.copy())
                
                if not summary_df.empty:
                    # Persist the summary to disk so downstream heatmap generation can read it
                    self.summary_csv_path = self.raw_csv_path.replace("_Raw_Results.csv", "_Group_Summary.csv")
                    try:
                        summary_df.to_csv(self.summary_csv_path, index=False)
                    except Exception as e:
                        # Fall back to disabling heatmaps if we cannot write the file
                        self.analysis_panel.enable_buttons(raw_csv_ready=True, summary_csv_ready=False)
                        self.statusBar().showMessage(f"Summary generated but could not be saved: {e}. Heatmaps disabled.")
                    else:
                        self.analysis_panel.enable_buttons(raw_csv_ready=True, summary_csv_ready=True)
                        self.statusBar().showMessage("Raw data loaded. All analyses enabled.")
                else:
                    self.analysis_panel.enable_buttons(raw_csv_ready=True, summary_csv_ready=False)
                    self.statusBar().showMessage("Raw data loaded. Summary generation failed. Heatmaps disabled.")

                # After loading the raw data, we now have the info needed to populate the dropdowns.
                all_groups = sorted(self.raw_features_df['group_name'].unique())
                potential_factors = ['Sex', 'Dose', 'Treatment', 'Group_Number']
                available_factors = [f for f in potential_factors if f in self.raw_features_df.columns]
                
                # --- DEBUGGING BLOCK ---
                print("\n--- DEBUG: Inside MainWindow._process_loaded_files ---")
                all_groups = sorted(self.raw_features_df['group_name'].unique())
                potential_factors = ['Sex', 'Dose', 'Treatment', 'Group_Number']
                available_factors = [f for f in potential_factors if f in self.raw_features_df.columns]
                
                print(f"Found Groups: {all_groups}")
                print(f"Found Factors: {available_factors}")
                print("Calling analysis_panel.populate_factor_dropdowns...")

                # Call the function in AnalysisPanel to update its UI
                self.analysis_panel.populate_factor_dropdowns(available_factors, all_groups)

                print("--- DEBUG: Finished populate_factor_dropdowns call ---\n")       
                print("--- DEBUG: Automatically run the initial overall ranking ---\n")       

                # Automatically run the initial overall ranking
                self.run_ranking_analysis({"type": "Overall"})
                print("--- DEBUG: Done with Automatically run the initial overall ranking ---\n")       



            elif filepath.endswith("_Group_Summary.csv"):
                self.summary_csv_path = filepath
                self.statusBar().showMessage(f"Loaded summary data from {os.path.basename(filepath)}. Heatmap analysis enabled.")
                self.analysis_panel.enable_buttons(raw_csv_ready=False, summary_csv_ready=True)
                # We can't populate hypothesis dropdowns from summary data, so we clear them
                self.analysis_panel.populate_factor_dropdowns([], [])
            
            else:
                QMessageBox.warning(self, "Invalid File Type", "Please select a valid '_Raw_Results.csv' or '_Group_Summary.csv' file.")
                self.analysis_panel.enable_buttons(raw_csv_ready=False, summary_csv_ready=False)
                return

            self.analysis_panel.set_loaded_file_label(filepath)

        except Exception as e:
            error_str = f"An error occurred while loading or processing the CSV file: {e}\n\n{traceback.format_exc()}"
            QMessageBox.critical(self, "File Load Error", error_str)
            self.analysis_panel.set_loaded_file_label("")
            self.analysis_panel.enable_buttons(raw_csv_ready=False, summary_csv_ready=False)

    @pyqtSlot(dict)
    def run_ranking_analysis(self, params: dict):
        """
        Launches the RankingWorker thread. This is the slot connected to the UI.
        """
        if self.raw_features_df is None or self.raw_features_df.empty:
            QMessageBox.warning(self, "No Data", "Raw feature data is not loaded.")
            return

        # Dynamically get factor levels for Interaction analysis
        if params.get("type") == "Interaction":
            factor1 = self.analysis_panel.factor1_combo.currentText()
            factor2 = self.analysis_panel.factor2_combo.currentText()
            if not factor1 or not factor2 or factor1 == factor2:
                QMessageBox.warning(self, "Invalid Selection", "Please select two different factors.")
                return
            f1_levels = sorted(self.raw_features_df[factor1].unique().tolist())
            f2_levels = sorted(self.raw_features_df[factor2].unique().tolist())
            if len(f1_levels) < 2 or len(f2_levels) < 2:
                QMessageBox.warning(self, "Invalid Data", "Both factors must have at least 2 levels.")
                return
            params["factor1_col"], params["factor1_levels"] = factor1, f1_levels[:2]
            params["factor2_col"], params["factor2_levels"] = factor2, f2_levels[:2]
        
        self.analysis_panel.setEnabled(False)
        self.statusBar().showMessage(f"Running '{params.get('type')}' ranking analysis...")
        
        self.ranking_thread = QThread()
        self.ranking_worker = RankingWorker(self.raw_features_df, params)
        self.ranking_worker.moveToThread(self.ranking_thread)
        
        self.ranking_thread.started.connect(self.ranking_worker.run)
        self.ranking_worker.error.connect(lambda msg: QMessageBox.critical(self, "Ranking Error", msg))
        # Accept the emitted error string to match the signal signature and ensure the panel re-enables on error
        self.ranking_worker.error.connect(lambda msg: self.analysis_panel.setEnabled(True))
        self.ranking_worker.finished.connect(self.on_ranking_finished)
        self.ranking_worker.finished.connect(self.ranking_thread.quit)
        self.ranking_worker.finished.connect(self.ranking_worker.deleteLater)
        self.ranking_thread.finished.connect(self.ranking_thread.deleteLater)
        self.ranking_thread.start()

    @pyqtSlot(pd.DataFrame, dict)
    def on_ranking_finished(self, results_df, params):
        """
        This slot receives the results from the RankingWorker and updates the UI.
        """
        analysis_type = params.get("type", "Unknown")
        metadata = f"Feature Ranking Results\nAnalysis Type: {analysis_type}\n"
        if analysis_type == "Interaction":
            metadata += f"Factor 1: {params['factor1_col']} (Levels: {', '.join(params['factor1_levels'])})\n"
            metadata += f"Factor 2: {params['factor2_col']} (Levels: {', '.join(params['factor2_levels'])})"
        elif analysis_type == "Normalization":
            metadata += f"Baseline: {params['baseline_group']}\nAffected: {params['affected_group']}\nTreated: {params['treated_group']}"
        elif analysis_type == "Overall":
            if results_df is not None and not results_df.empty:
                score_columns = [col for col in results_df.columns if col != 'Feature']
                metadata += "Based on: " + " and ".join(score_columns)
        
        self.analysis_panel.set_analysis_metadata(metadata)
        self.analysis_panel.display_ranking_results(results_df)
        self.statusBar().showMessage(f"'{analysis_type}' ranking complete.")
        self.analysis_panel.setEnabled(True)

    def on_summary_csv_selected(self, path: str):
        """Slot for when user manually loads a summary CSV for heatmaps."""
        self.summary_csv_path = path
        # Enable only the heatmap buttons
        self.analysis_panel.enable_buttons(raw_csv_ready=False, summary_csv_ready=True)
        self.statusBar().showMessage(f"Loaded summary file: {os.path.basename(path)}")

    @pyqtSlot(str, bool, str)
    def run_univariate_analysis_slot(self, _, show_plot, agg_method):
        """Slot specifically for the univariate button."""
        self._launch_heatmap_worker('univariate', show_plot, agg_method)

    @pyqtSlot(str, bool, str)
    def run_multivariate_analysis_slot(self, _, show_plot, agg_method):
        """Slot specifically for the multivariate button."""
        self._launch_heatmap_worker('multivariate', show_plot, agg_method)

    def _launch_heatmap_worker(self, mode: str, show_plot: bool, agg_method: str):
        """
        A centralized helper function to create and start the heatmap worker thread.
        """
        if not self.summary_csv_path:
            QMessageBox.warning(self, "No Data", "Group Summary CSV file not found. Please load one first.")
            return

        self.analysis_panel.setEnabled(False)
        self.heatmap_thread = QThread()
        # --- MODIFIED: Pass agg_method to the worker's constructor ---
        self.heatmap_worker = HeatmapWorker(mode, self.summary_csv_path, show_plot, agg_method)
        self.heatmap_worker.moveToThread(self.heatmap_thread)
        
        # Connect signals for this specific worker instance
        self.heatmap_thread.started.connect(self.heatmap_worker.run)
        self.heatmap_worker.finished.connect(lambda: self.analysis_panel.setEnabled(True))
        self.heatmap_worker.finished.connect(self.heatmap_thread.quit)
        self.heatmap_worker.finished.connect(self.heatmap_worker.deleteLater)
        self.heatmap_thread.finished.connect(self.heatmap_thread.deleteLater)
        
        self.heatmap_worker.status.connect(self.statusBar().showMessage)
        self.heatmap_worker.error.connect(lambda msg: QMessageBox.critical(self, "Heatmap Error", msg))
        
        self.heatmap_worker.plotReady.connect(self.show_plot)
        
        self.heatmap_thread.start()

    @pyqtSlot(str)
    def show_plot(self, image_path: str):
        """Opens the generated image file using the system's default viewer."""
        try:
            # webbrowser.open is cross-platform and safe
            webbrowser.open(f'file://{os.path.realpath(image_path)}')
        except Exception as e:
            QMessageBox.warning(self, "Display Error", f"Could not open the plot image: {e}")

    @pyqtSlot(str, bool)
    def run_heatmap_analysis(self, _, show_plot):
        """Triggers the heatmap generation in a worker thread."""
        if not self.summary_csv_path:
            QMessageBox.warning(self, "No Data", "Group Summary CSV file not found.")
            return

        sender = self.sender()
        mode = 'univariate' if sender == self.analysis_panel.univariate_button else 'multivariate'

        self.analysis_panel.setEnabled(False) # Disable the whole panel during plotting
        self.heatmap_thread = QThread()
        self.heatmap_worker = HeatmapWorker(mode, self.summary_csv_path, show_plot)
        self.heatmap_worker.moveToThread(self.heatmap_thread)
        
        self.heatmap_thread.started.connect(self.heatmap_worker.run)
        self.heatmap_worker.finished.connect(lambda: self.analysis_panel.setEnabled(True))
        self.heatmap_worker.finished.connect(self.heatmap_thread.quit)
        self.heatmap_worker.finished.connect(self.heatmap_worker.deleteLater)
        self.heatmap_thread.finished.connect(self.heatmap_thread.deleteLater)
        
        self.heatmap_worker.status.connect(self.statusBar().showMessage)
        self.heatmap_worker.error.connect(lambda msg: QMessageBox.critical(self, "Heatmap Error", msg))
        
        self.heatmap_thread.start()

    @pyqtSlot(str)
    def on_csv_path_selected(self, path: str):
        """Triggers analysis when a user manually loads a CSV."""
        self.feature_csv_path = path
        self.analysis_panel.enable_analysis_button(True)
        self.run_timeseries_analysis()

    @pyqtSlot()
    def run_timeseries_analysis(self):
        """Triggers the time-series analysis in the backend."""
        if not self.feature_csv_path:
            QMessageBox.warning(self, "No Data", "Feature CSV file not found.")
            return
        self.statusBar().showMessage(f"Running analysis on {os.path.basename(self.feature_csv_path)}...")
        self.analysis_panel.enable_analysis_button(False)
        try:
            results_df = analyze_features(self.feature_csv_path)
            self.analysis_panel.display_results(results_df)
            self.statusBar().showMessage("Time-series analysis complete.")
        except Exception as e:
            QMessageBox.critical(self, "Analysis Error", f"An error occurred during analysis: {e}")
            self.statusBar().showMessage("Analysis failed.")
        self.analysis_panel.enable_analysis_button(True)

    def _auto_load_latest_feature_csv(self) -> bool:
        """Fallback: attempt to auto-load the latest Raw Results CSV in the output directory."""
        try:
            if not self.output_directory or not os.path.isdir(self.output_directory):
                return False
            candidates = []
            for name in os.listdir(self.output_directory):
                if name.endswith("_Raw_Results.csv"):
                    full_path = os.path.join(self.output_directory, name)
                    try:
                        mtime = os.path.getmtime(full_path)
                    except Exception:
                        mtime = 0
                    candidates.append((mtime, full_path))
            if not candidates:
                return False
            candidates.sort(reverse=True)
            latest = candidates[0][1]
            self._process_loaded_files(latest)
            return True
        except Exception:
            return False

    def _refresh_available_result_sets(self):
        """Scan output dir for Raw Results CSVs and push into Analysis panel combo."""
        try:
            if not self.output_directory or not os.path.isdir(self.output_directory):
                self.analysis_panel.update_available_result_sets([])
                return
            paths = []
            for name in os.listdir(self.output_directory):
                if name.endswith("_Raw_Results.csv"):
                    paths.append(os.path.join(self.output_directory, name))
            self.analysis_panel.update_available_result_sets(sorted(paths))
        except Exception:
            pass

    def _get_feature_signature(self):
        """Build a tuple uniquely describing current feature extraction config."""
        try:
            feat = self.feature_panel.get_feature_settings()
            mode = str(feat.get("feature_region_mode", "crop"))
            roi_part = None
            if mode == "roi":
                roi_part = int(feat.get("feature_region_roi_id") or -1)
            elif mode == "crop":
                r = self.preview_panel.get_roi()
                roi_part = (int(r.x()), int(r.y()), int(r.width()), int(r.height()))
            else:
                roi_part = ("full",)
            features = tuple(sorted([str(f) for f in feat.get("selected_features_list", [])]))
            # Only include feature extraction aspects in the signature
            return (mode, roi_part, features)
        except Exception:
            return None

    def _compute_feature_tag(self, signature) -> str:
        """Create a compact, deterministic tag for filenames from a signature."""
        try:
            if not signature:
                return ""
            import hashlib
            mode, roi_part, features = signature
            if mode == "roi":
                region = f"roi{roi_part}"
            elif mode == "crop" and isinstance(roi_part, tuple) and len(roi_part) == 4:
                region = f"crop{roi_part[2]}x{roi_part[3]}"
            else:
                region = "full"
            feat_str = ",".join(features)
            h = hashlib.md5(feat_str.encode("utf-8")).hexdigest()[:8]
            return f"feat-{region}-{h}"
        except Exception:
            return ""

    def _update_reextract_visibility(self):
        """Show the green re-extract button when current feature config differs from last processed."""
        try:
            # Must have some data processed/loaded to compare against
            has_data = self.raw_features_df is not None and not self.raw_features_df.empty
            feat = self.feature_panel.get_feature_settings()
            enabled = bool(feat.get("enable_features", False))
            current_sig = self._get_feature_signature()
            visible = bool(has_data and enabled and self._last_feature_signature and (current_sig != self._last_feature_signature))
            self.feature_panel.set_reextract_visible(visible)
        except Exception:
            pass

    def select_output_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.output_directory = directory
            self.out_dir_label.setText(self.output_directory)
            self.statusBar().showMessage(f"Output directory set to: {directory}")
            # Refresh available results when output dir changes
            self._refresh_available_result_sets()

    def _scan_and_update_main_dir(self, directory: str):
        """
        Scans a given directory for image files, updates the internal state and UI,
        and loads an initial preview image. This is the central logic.
        """
        self.main_directory = directory
        # Update line edit without triggering editingFinished
        try:
            self._suppress_dir_edit_handler = True
            self.dir_label.setText(self.main_directory)
            # Reset modified flag so first click doesn't fire editingFinished logic
            try:
                self.dir_label.setModified(False)
            except Exception:
                pass
        finally:
            self._suppress_dir_edit_handler = False
        self.statusBar().showMessage("Scanning files...")

        self.grouped_files = group_files(self.main_directory)
        if not self.grouped_files:
            QMessageBox.warning(self, "No Files Found", "Could not find any valid TIFF files in the selected directory.")
            self.statusBar().showMessage("Ready.")
            return

        self.image_pair_list = []
        for animal_data in self.grouped_files.values():
            for time_data in animal_data.values():
                if "WF" in time_data and "FL" in time_data:
                    self.image_pair_list.append((time_data["WF"], time_data["FL"]))
        self.image_pair_list.sort()

        # Update phase sliders with time point count
        if self.image_pair_list:
            first_animal_key = next(iter(self.grouped_files.keys()))
            num_time_points = len(self.grouped_files[first_animal_key])
            self.feature_panel.update_phase_slider_range(num_time_points)

        self.statusBar().showMessage(f"Found {len(self.grouped_files)} animals across {len(self.image_pair_list)} image pairs.")

        # Load an initial random image immediately after scanning is complete (forced once).
        self.load_random_preview_image(force=True)
        # Refresh available result sets based on current output dir
        self._refresh_available_result_sets()