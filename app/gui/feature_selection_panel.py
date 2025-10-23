# gui/feature_selection_panel.py ---

import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QFormLayout, 
                             QPushButton, QSpinBox, QCheckBox, 
                             QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QHBoxLayout)
from PyQt6.QtCore import Qt, pyqtSignal

class FeatureSelectionPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.feature_hierarchy = {
            "First Order Statistics": {
                "Energy": "original_firstorder_Energy", "Total Energy": "original_firstorder_TotalEnergy",
                "Entropy": "original_firstorder_Entropy", "Minimum": "original_firstorder_Minimum",
                "10th Percentile": "original_firstorder_10Percentile", "90th Percentile": "original_firstorder_90Percentile",
                "Maximum": "original_firstorder_Maximum", "Mean": "original_firstorder_Mean",
                "Median": "original_firstorder_Median", "Standard Deviation": "original_firstorder_StandardDeviation",
                "Skewness": "original_firstorder_Skewness", "Kurtosis": "original_firstorder_Kurtosis",
            },
            "GLCM (Texture)": {
                "Contrast": "original_glcm_Contrast", "Homogeneity": "original_glcm_Homogeneity1",
                "Energy": "original_glcm_Energy", "Correlation": "original_glcm_Correlation",
                "Difference Entropy": "original_glcm_DifferenceEntropy",
            },
            "GLSZM (Zone Size)": {
                "Short Zone Emphasis (SZE)": "original_glszm_ShortZoneEmphasis",
                "Long Zone Emphasis (LZE)": "original_glszm_LongZoneEmphasis",
                "Gray Level Non-Uniformity (GLN)": "original_glszm_GrayLevelNonUniformity",
                "Size Zone Non-Uniformity (SZN)": "original_glszm_SizeZoneNonUniformity",
                "Zone Percentage": "original_glszm_ZonePercentage",
            },
        }
        
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        # Match top gap with Preview panel so all columns align
        main_layout.setContentsMargins(0, 5, 0, 0)
        main_layout.setSpacing(6)
        
        feature_group = QGroupBox("Feature Extraction")
        feature_layout = QVBoxLayout(feature_group)
        
        self.feature_checkbox = QCheckBox("Enable Feature Extraction")
        self.feature_checkbox.toggled.connect(self.toggle_feature_widgets)
        feature_layout.addWidget(self.feature_checkbox)
        
        self.feature_widgets_container = QWidget()
        feature_form_layout = QFormLayout(self.feature_widgets_container)
        
        self.feature_threshold_spinbox = QSpinBox()
        self.feature_threshold_spinbox.setRange(0, 65535)
        self.feature_threshold_spinbox.setValue(5000)
        feature_form_layout.addRow("Signal Threshold:", self.feature_threshold_spinbox)
        
        self.feature_tree = QTreeWidget()
        self.feature_tree.setHeaderHidden(True)
        
        for category, features in self.feature_hierarchy.items():
            category_item = QTreeWidgetItem(self.feature_tree)
            category_item.setText(0, category)
            # We still use this flag, but we manage the state manually now
            category_item.setFlags(category_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
            category_item.setCheckState(0, Qt.CheckState.Unchecked)
            
            for display_name, internal_name in features.items():
                feature_item = QTreeWidgetItem(category_item)
                feature_item.setText(0, display_name)
                feature_item.setFlags(feature_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                feature_item.setCheckState(0, Qt.CheckState.Unchecked)
                feature_item.setData(0, Qt.ItemDataRole.UserRole, internal_name)
        

        self.feature_tree.itemClicked.connect(self._on_item_clicked)
        
        feature_form_layout.addRow(self.feature_tree)
        feature_layout.addWidget(self.feature_widgets_container)
        main_layout.addWidget(feature_group)
        
        path_group = QGroupBox("Signal Path Analysis")
        path_layout = QFormLayout(path_group)
        
        self.path_checkbox = QCheckBox("Enable Signal Path Analysis")
        # Let's start with it checked by default, which is more intuitive
        self.path_checkbox.setChecked(True) 
        
        self.path_threshold_spinbox = QSpinBox()
        self.path_threshold_spinbox.setRange(0, 65535)
        self.path_threshold_spinbox.setValue(7500)
        self.path_threshold_spinbox.setToolTip("Set the intensity threshold for signal path.")
        
        path_layout.addRow(self.path_checkbox)
        path_layout.addRow("Signal Threshold:", self.path_threshold_spinbox)

        self.phase1_spinbox = QSpinBox()
        self.phase1_spinbox.setToolTip("The time point where the 'Early' phase ends and 'Mid' phase begins.")
        self.phase2_spinbox = QSpinBox()
        self.phase2_spinbox.setToolTip("The time point where the 'Mid' phase ends and 'Late' phase begins.")

        path_layout.addRow("Early/Mid Cutoff (Time):", self.phase1_spinbox)
        path_layout.addRow("Mid/Late Cutoff (Time):", self.phase2_spinbox)

        # Use a container for the group layout
        container_widget = QWidget()
        container_widget.setLayout(path_layout)
        main_layout.addWidget(container_widget)

        self.path_checkbox.toggled.connect(self._toggle_path_widgets)
        
        # Manually call the function once to set the correct initial state.
        self._toggle_path_widgets(self.path_checkbox.isChecked())

        # Logic to prevent spinboxes from crossing over (unchanged)
        def update_phase_ranges():
            self.phase2_spinbox.setMinimum(self.phase1_spinbox.value())
            self.phase1_spinbox.setMaximum(self.phase2_spinbox.value())

        self.phase1_spinbox.valueChanged.connect(update_phase_ranges)
        self.phase2_spinbox.valueChanged.connect(update_phase_ranges)

    def _toggle_path_widgets(self, checked: bool):
        """Enables or disables all child widgets for signal path analysis."""
        self.path_threshold_spinbox.setEnabled(checked)
        self.phase1_spinbox.setEnabled(checked)
        self.phase2_spinbox.setEnabled(checked)

    def get_settings(self) -> dict:
        """
        Gathers the complete state of all controls in this panel, including
        Pyradiomics features, Signal Path settings, and Phase cutoffs.
        """
        # 1. Gather Pyradiomics Feature Settings
        enabled_feature_classes = set()
        selected_features_list = []
        checked_pyradiomics_features = []

        root = self.feature_tree.invisibleRootItem()
        for i in range(root.childCount()):
            category_item = root.child(i)
            has_checked_child = False
            for j in range(category_item.childCount()):
                feature_item = category_item.child(j)
                if feature_item.checkState(0) == Qt.CheckState.Checked:
                    has_checked_child = True
                    internal_name = feature_item.data(0, Qt.ItemDataRole.UserRole)
                    selected_features_list.append(internal_name)
                    checked_pyradiomics_features.append(internal_name)
            
            if has_checked_child:
                sample_feature = category_item.child(0).data(0, Qt.ItemDataRole.UserRole)
                class_name = sample_feature.split('_')[1]
                enabled_feature_classes.add(class_name)

        # 2. Combine all settings into a single dictionary
        all_settings = {
            "enable_features": self.feature_checkbox.isChecked(),
            "feature_threshold": self.feature_threshold_spinbox.value(),
            "enabled_feature_classes": list(enabled_feature_classes),
            "selected_features_list": selected_features_list,
            "checked_pyradiomics_features": checked_pyradiomics_features,

            "enable_signal_path": self.path_checkbox.isChecked(),
            "signal_path_threshold": self.path_threshold_spinbox.value(),

            "phase1_index": self.phase1_spinbox.value(),
            "phase2_index": self.phase2_spinbox.value(),
        }
        
        return all_settings

    def set_settings(self, data: dict):
        """
        Sets the complete state of all controls in this panel from a loaded dictionary.
        """
        # --- 1. Block signals to prevent unintended triggers ---
        self.feature_checkbox.blockSignals(True)
        self.feature_threshold_spinbox.blockSignals(True)
        self.path_checkbox.blockSignals(True)
        self.path_threshold_spinbox.blockSignals(True)
        self.phase1_spinbox.blockSignals(True)
        self.phase2_spinbox.blockSignals(True)
        self.feature_tree.blockSignals(True)

        # --- 2. Set widget states using .get() for safety ---
        self.feature_checkbox.setChecked(data.get("enable_features", False))
        self.feature_threshold_spinbox.setValue(data.get("feature_threshold", 5000))
        
        self.path_checkbox.setChecked(data.get("enable_signal_path", False))
        self.path_threshold_spinbox.setValue(data.get("signal_path_threshold", 7500))
        self.phase1_spinbox.setValue(data.get("phase1_index", 5))
        self.phase2_spinbox.setValue(data.get("phase2_index", 15))

        # --- 3. Restore the state of the feature tree ---
        checked_list = data.get("checked_pyradiomics_features", [])
        
        # First, set the state of all individual feature items (children)
        iterator = QTreeWidgetItemIterator(self.feature_tree)
        while iterator.value():
            item = iterator.value()
            if item.childCount() == 0: # This is a feature, not a category
                internal_name = item.data(0, Qt.ItemDataRole.UserRole)
                if internal_name in checked_list:
                    item.setCheckState(0, Qt.CheckState.Checked)
                else:
                    item.setCheckState(0, Qt.CheckState.Unchecked)
            iterator += 1
            
        # Second, update the state of the category items (parents) based on their children
        root = self.feature_tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            child_states = [parent.child(j).checkState(0) for j in range(parent.childCount())]
            
            if all(s == Qt.CheckState.Checked for s in child_states):
                parent.setCheckState(0, Qt.CheckState.Checked)
            elif all(s == Qt.CheckState.Unchecked for s in child_states):
                parent.setCheckState(0, Qt.CheckState.Unchecked)
            else:
                parent.setCheckState(0, Qt.CheckState.PartiallyChecked)

        # --- 4. Unblock all signals ---
        self.feature_checkbox.blockSignals(False)
        self.feature_threshold_spinbox.blockSignals(False)
        self.path_checkbox.blockSignals(False)
        self.path_threshold_spinbox.blockSignals(False)
        self.phase1_spinbox.blockSignals(False)
        self.phase2_spinbox.blockSignals(False)
        self.feature_tree.blockSignals(False)

        # After loading a settings file, manually synchronize the UI state again.
        self._toggle_path_widgets(self.path_checkbox.isChecked())

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """
        Handles the logic for parent/child checkbox interactions using the clicked signal.
        This is a robust, loop-free method.
        """
        # Determine the item's state *after* the click has toggled it
        new_state = item.checkState(column)

        # Block signals to prevent any potential re-triggering while we make changes
        self.feature_tree.blockSignals(True)

        # Case 1: A parent item (category) was clicked
        if item.childCount() > 0:
            # Propagate the parent's new state to all its children
            for i in range(item.childCount()):
                item.child(i).setCheckState(column, new_state)
        
        # Case 2: A child item (feature) was clicked
        else:
            parent = item.parent()
            if parent:
                # Check the state of all siblings
                child_states = [parent.child(i).checkState(column) for i in range(parent.childCount())]
                
                # Determine the new state for the parent
                if all(s == Qt.CheckState.Checked for s in child_states):
                    parent.setCheckState(column, Qt.CheckState.Checked)
                elif all(s == Qt.CheckState.Unchecked for s in child_states):
                    parent.setCheckState(column, Qt.CheckState.Unchecked)
                else:
                    parent.setCheckState(column, Qt.CheckState.PartiallyChecked)

        # Re-enable signals after we are done making all our changes
        self.feature_tree.blockSignals(False)

    def toggle_feature_widgets(self, checked):
        self.feature_widgets_container.setEnabled(checked)

    def update_phase_slider_range(self, num_time_points: int):
        """
        Called by MainWindow to dynamically set the valid range of the phase
        cutoff spinboxes based on the number of time points in the dataset.
        """
        if num_time_points > 1:
            # The range should be from the first time point (index 0) to the
            # last time point (index num_time_points - 1).
            max_val = num_time_points - 1
            
            self.phase1_spinbox.setRange(0, max_val)
            self.phase2_spinbox.setRange(0, max_val)

            # Set sensible defaults (approximately 1/3 and 2/3 of the way through)
            # Use // for integer division
            default_phase1 = max_val // 3
            default_phase2 = (max_val * 2) // 3

            self.phase1_spinbox.setValue(default_phase1)
            self.phase2_spinbox.setValue(default_phase2)
        else:
            # If there are not enough time points, disable and set to 0.
            self.phase1_spinbox.setRange(0, 0)
            self.phase2_spinbox.setRange(0, 0)

    def get_feature_settings(self) -> dict:
        """
        Gathers all settings from both the Pyradiomics and Signal Path panels
        and returns them as a single dictionary.
        """
        enabled_feature_classes = set()
        selected_features_list = []
        
        root = self.feature_tree.invisibleRootItem()
        for i in range(root.childCount()):
            category_item = root.child(i)
            has_checked_child = False
            for j in range(category_item.childCount()):
                feature_item = category_item.child(j)
                if feature_item.checkState(0) == Qt.CheckState.Checked:
                    has_checked_child = True
                    internal_name = feature_item.data(0, Qt.ItemDataRole.UserRole)
                    selected_features_list.append(internal_name)
            
            if has_checked_child:
                # This logic correctly extracts the feature class name (e.g., 'glcm')
                sample_feature = category_item.child(0).data(0, Qt.ItemDataRole.UserRole)
                class_name = sample_feature.split('_')[1]
                enabled_feature_classes.add(class_name)
        
        # Store the pyradiomics settings in a dictionary
        pyradiomics_settings = {
            "enable_features": self.feature_checkbox.isChecked(),
            "feature_threshold": self.feature_threshold_spinbox.value(),
            "enabled_feature_classes": list(enabled_feature_classes),
            "selected_features_list": selected_features_list
        }

        # Gather settings from the Signal Path Analysis panel ---
        signal_path_settings = {
            "enable_signal_path": self.path_checkbox.isChecked(),
            "signal_path_threshold": self.path_threshold_spinbox.value()
        }

        # --- Combine both dictionaries into one and return it ---
        # The ** operator unpacks and merges the dictionaries.
        all_settings = {**pyradiomics_settings, **signal_path_settings}
        
        return all_settings