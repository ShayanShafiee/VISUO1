# --- FINAL CORRECTED FILE: gui/analysis_panel.py ---

import os
import re
import pandas as pd
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QPushButton, 
                             QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
                             QHBoxLayout, QFileDialog, QCheckBox, QLabel, QComboBox, 
                             QFormLayout, QApplication)
from PyQt6.QtCore import pyqtSignal

class AnalysisPanel(QWidget):
    runRankingAnalysis = pyqtSignal(dict)
    runUnivariateHeatmaps = pyqtSignal(str, bool, str)
    runMultivariateHeatmap = pyqtSignal(str, bool, str)
    loadDataRequest = pyqtSignal() 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_analysis_metadata = "No analysis has been run."
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        # Keep the top gap consistent with the Preview panel so columns line up
        main_layout.setContentsMargins(0, 5, 0, 0)
        main_layout.setSpacing(6)
        
        load_group = QGroupBox("Load Data for Analysis")
        load_layout = QVBoxLayout(load_group)
        self.load_data_button = QPushButton("Load Feature CSV File...")
        self.load_data_button.setToolTip("Load a Raw or Summary CSV to enable analyses.")
        self.load_data_button.clicked.connect(self.loadDataRequest.emit)
        self.loaded_file_label = QLabel("No file loaded.")
        self.loaded_file_label.setWordWrap(True)
        load_layout.addWidget(self.load_data_button)
        load_layout.addWidget(self.loaded_file_label)
        main_layout.addWidget(load_group)

        ranking_group = QGroupBox("Feature Ranking")
        ranking_layout = QVBoxLayout(ranking_group)
        form_layout = QFormLayout()
        self.analysis_type_combo = QComboBox()
        self.analysis_type_combo.addItems([
            "Overall Ranking (Unsupervised)", 
            "Hypothesis: Interaction Effect", 
            "Hypothesis: Normalization Effect"
        ])
        self.analysis_type_combo.currentIndexChanged.connect(self._on_analysis_type_changed)
        form_layout.addRow("Analysis Type:", self.analysis_type_combo)
        ranking_layout.addLayout(form_layout)
        
        self.interaction_widget = QWidget()
        interaction_layout = QFormLayout(self.interaction_widget)
        self.factor1_combo = QComboBox()
        self.factor2_combo = QComboBox()
        interaction_layout.addRow("Factor 1:", self.factor1_combo)
        interaction_layout.addRow("Factor 2:", self.factor2_combo)
        ranking_layout.addWidget(self.interaction_widget)

        self.normalization_widget = QWidget()
        norm_layout = QFormLayout(self.normalization_widget)
        self.baseline_combo = QComboBox()
        self.affected_combo = QComboBox()
        self.treated_combo = QComboBox()
        norm_layout.addRow("Baseline Group:", self.baseline_combo)
        norm_layout.addRow("Affected Group:", self.affected_combo)
        norm_layout.addRow("Treated Group:", self.treated_combo)
        ranking_layout.addWidget(self.normalization_widget)
        
        self.run_ranking_button = QPushButton("Run Ranking Analysis")
        self.run_ranking_button.clicked.connect(self._on_run_analysis_click)
        ranking_layout.addWidget(self.run_ranking_button)
        
        results_header_layout = QHBoxLayout()
        results_header_layout.addWidget(QLabel("<b>Ranking Results</b>"))
        results_header_layout.addStretch(1)
        self.copy_button = QPushButton("📋")
        self.copy_button.setToolTip("Copy table to clipboard")
        self.copy_button.setFixedWidth(40)
        self.export_button = QPushButton("💾")
        self.export_button.setToolTip("Export table to CSV file")
        self.export_button.setFixedWidth(40)
        results_header_layout.addWidget(self.copy_button)
        results_header_layout.addWidget(self.export_button)
        ranking_layout.addLayout(results_header_layout)
        self.results_table = QTableWidget()
        self.results_table.setSortingEnabled(True)
        ranking_layout.addWidget(self.results_table)
        main_layout.addWidget(ranking_group)

        heatmap_group = QGroupBox("Heatmap Clustering")
        heatmap_layout = QVBoxLayout(heatmap_group)
        agg_layout = QHBoxLayout()
        agg_layout.addWidget(QLabel("Use curve based on:"))
        self.agg_method_combo = QComboBox()
        self.agg_method_combo.addItems(["Median", "Mean"])
        self.agg_method_combo.setToolTip("Choose the statistic for generating time-series curves.")
        agg_layout.addWidget(self.agg_method_combo)
        agg_layout.addStretch(1)
        heatmap_layout.addLayout(agg_layout)
        self.univariate_button = QPushButton("Generate Univariate Heatmaps")
        self.multivariate_button = QPushButton("Generate Multivariate Heatmap")
        self.show_plot_checkbox = QCheckBox("Show Plots After Generating")
        self.show_plot_checkbox.setChecked(True)
        heatmap_layout.addWidget(self.univariate_button)
        heatmap_layout.addWidget(self.multivariate_button)
        heatmap_layout.addWidget(self.show_plot_checkbox)
        main_layout.addWidget(heatmap_group)

        self.copy_button.clicked.connect(self.copy_table_to_clipboard)
        self.export_button.clicked.connect(self.export_table_to_csv)
        self.univariate_button.clicked.connect(self._on_univariate_click)
        self.multivariate_button.clicked.connect(self._on_multivariate_click)
        
        self.enable_buttons(raw_csv_ready=False, summary_csv_ready=False)
        self._on_analysis_type_changed(0)

    def get_settings(self) -> dict:
        """Gets the current state of the analysis panel widgets."""
        return {
            "loaded_file_path": self.loaded_file_label.toolTip(),
            "analysis_type_index": self.analysis_type_combo.currentIndex(),
            "interaction_factor1": self.factor1_combo.currentText(),
            "interaction_factor2": self.factor2_combo.currentText(),
            "norm_baseline": self.baseline_combo.currentText(),
            "norm_affected": self.affected_combo.currentText(),
            "norm_treated": self.treated_combo.currentText(),
            "heatmap_agg_method": self.agg_method_combo.currentText(),
            "heatmap_show_plots": self.show_plot_checkbox.isChecked(),
        }

    def set_settings(self, data: dict):
        """Sets the state of the analysis panel widgets from a dictionary."""
        # Don't auto-load the data, just set the label. User can click 'Load'
        file_path = data.get("loaded_file_path", "No file loaded.")
        if file_path and "No file" not in file_path:
             self.loaded_file_label.setText(f"Loaded: {os.path.basename(file_path)}")
             self.loaded_file_label.setToolTip(file_path)
        else:
             self.loaded_file_label.setText("No file loaded.")
             self.loaded_file_label.setToolTip("")

        self.analysis_type_combo.setCurrentIndex(data.get("analysis_type_index", 0))
        self.factor1_combo.setCurrentText(data.get("interaction_factor1", ""))
        self.factor2_combo.setCurrentText(data.get("interaction_factor2", ""))
        self.baseline_combo.setCurrentText(data.get("norm_baseline", ""))
        self.affected_combo.setCurrentText(data.get("norm_affected", ""))
        self.treated_combo.setCurrentText(data.get("norm_treated", ""))
        self.agg_method_combo.setCurrentText(data.get("heatmap_agg_method", "Median"))
        self.show_plot_checkbox.setChecked(data.get("heatmap_show_plots", True))

    def _on_analysis_type_changed(self, index):
        """Shows/hides the correct controls based on analysis type selection."""
        self.interaction_widget.setVisible(index == 1)
        self.normalization_widget.setVisible(index == 2)

    def _on_run_analysis_click(self):
        params = {}
        index = self.analysis_type_combo.currentIndex()
        if index == 0:
            params["type"] = "Overall"
        elif index == 1:
            params["type"] = "Interaction"
        elif index == 2:
            params["type"] = "Normalization"
            params["baseline_group"] = self.baseline_combo.currentText()
            params["affected_group"] = self.affected_combo.currentText()
            params["treated_group"] = self.treated_combo.currentText()
            if not all([params["baseline_group"], params["affected_group"], params["treated_group"]]):
                QMessageBox.warning(self, "Invalid Selection", "Please select all three groups for normalization analysis.")
                return
        self.runRankingAnalysis.emit(params)

    def set_analysis_metadata(self, header_string: str):
        self.current_analysis_metadata = header_string

    def copy_table_to_clipboard(self):
        """Copies the contents of the results table to the system clipboard."""
        clipboard = QApplication.clipboard()
        if not clipboard or self.results_table.rowCount() == 0:
            return
            
        header = self.current_analysis_metadata + "\n\n"
        
        col_headers = [self.results_table.horizontalHeaderItem(i).text() for i in range(self.results_table.columnCount())]
        table_text = header + "\t".join(col_headers) + "\n"
        
        for row in range(self.results_table.rowCount()):
            row_data = [self.results_table.item(row, col).text() for col in range(self.results_table.columnCount())]
            table_text += "\t".join(row_data) + "\n"
            
        clipboard.setText(table_text)
        
        # --- NEW: Show a confirmation message in the main window's status bar ---
        # self.window() gets a reference to the MainWindow that contains this panel.
        if self.window() and hasattr(self.window(), 'statusBar'):
            self.window().statusBar().showMessage("Results copied to clipboard.", 3000) # Message disappears after 3 seconds

    def export_table_to_csv(self):
        """
        Opens a save dialog and exports the contents of the results table
        to a CSV file, including a metadata header and a smart filename.
        """
        # 1. Check if there is anything to export
        if self.results_table.rowCount() == 0:
            QMessageBox.information(self, "No Data", "There are no results in the table to export.")
            return

        # 2. Generate a smart, descriptive default filename from the metadata
        # Use the first line of the metadata for the filename
        first_line = self.current_analysis_metadata.split('\n')[0]
        
        # Sanitize the line to make it a valid filename by removing invalid characters
        # and replacing spaces with underscores.
        safe_filename = re.sub(r'[^\w\s-]', '', first_line).strip().replace(' ', '_')
        suggested_filename = f"{safe_filename}.csv"
  
        # 3. Open the "Save File" dialog
        filepath, _ = QFileDialog.getSaveFileName(
            self, 
            "Save Feature Ranking Results", 
            suggested_filename, # Use the suggested name as the default
            "CSV Files (*.csv)"
        )
        
        # If the user cancelled the dialog, do nothing
        if not filepath:
            return

        # 4. Write the data to the selected file
        try:
            with open(filepath, 'w', newline='') as csvfile:
                # a. Write the multi-line metadata header, with each line commented out
                for line in self.current_analysis_metadata.split('\n'):
                    csvfile.write(f"# {line}\n")
                csvfile.write("\n") # Add a blank line for readability before the data
                
                # b. Write the column headers
                col_headers = [self.results_table.horizontalHeaderItem(i).text() for i in range(self.results_table.columnCount())]
                csvfile.write(",".join(col_headers) + "\n")
                
                # c. Write the table data, row by row
                for row in range(self.results_table.rowCount()):
                    row_data = [self.results_table.item(row, col).text() for col in range(self.results_table.columnCount())]
                    csvfile.write(",".join(row_data) + "\n")

            # 5. Provide feedback to the user in the status bar
            if self.window() and hasattr(self.window(), 'statusBar'):
                self.window().statusBar().showMessage(f"Results exported to {os.path.basename(filepath)}", 3000)

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Could not save the file: {e}")

    def _on_univariate_click(self):
        agg_method = self.agg_method_combo.currentText().lower()
        self.runUnivariateHeatmaps.emit("", self.show_plot_checkbox.isChecked(), agg_method)

    def _on_multivariate_click(self):
        agg_method = self.agg_method_combo.currentText().lower()
        self.runMultivariateHeatmap.emit("", self.show_plot_checkbox.isChecked(), agg_method)

    def enable_buttons(self, raw_csv_ready: bool, summary_csv_ready: bool):
        self.run_ranking_button.setEnabled(raw_csv_ready)
        self.copy_button.setEnabled(False) # Always start disabled
        self.export_button.setEnabled(False) # Always start disabled
        self.univariate_button.setEnabled(summary_csv_ready)
        self.multivariate_button.setEnabled(summary_csv_ready)

    def set_loaded_file_label(self, path: str):
        if path:
            self.loaded_file_label.setText(f"Loaded: {os.path.basename(path)}")
        else:
            self.loaded_file_label.setText("No file loaded.")

    def populate_factor_dropdowns(self, factor_names: list, group_names: list):
        """Called by MainWindow to fill all combo boxes with available data."""
        
        # --- DEBUGGING BLOCK ---
        print("\n--- DEBUG: Inside AnalysisPanel.populate_factor_dropdowns ---")
        print(f"Received Factors to add: {factor_names}")
        print(f"Received Groups to add: {group_names}")
        # --- END DEBUGGING BLOCK ---

        # Populate factor selection dropdowns
        for combo in [self.factor1_combo, self.factor2_combo]:
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(factor_names)
            combo.blockSignals(False)
        
        # Set a sensible default if possible
        if "Sex" in factor_names:
            self.factor1_combo.setCurrentText("Sex")
        if "Dose" in factor_names:
            self.factor2_combo.setCurrentText("Dose")

        # Populate group selection dropdowns
        for combo in [self.baseline_combo, self.affected_combo, self.treated_combo]:
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(group_names)
            combo.blockSignals(False)
        
        print("Finished populating dropdowns.")

    def display_ranking_results(self, df: pd.DataFrame):
        """
        Populates the single results table with feature ranking results,
        clears old results, and manages the state of the export buttons.
        """
        table = self.results_table

        # 1. Clear the table of any previous results
        table.setRowCount(0)
        table.setColumnCount(0)
        
        # 2. Determine if there are valid results to display
        has_results = (df is not None and not df.empty)
        
        # 3. Enable or disable export buttons based on whether there is data
        self.copy_button.setEnabled(has_results)
        self.export_button.setEnabled(has_results)

        # 4. If there are no results, stop here. The table is now clear.
        if not has_results:
            return

        # 5. If there are results, populate the table
        table.setRowCount(df.shape[0])
        table.setColumnCount(df.shape[1])
        table.setHorizontalHeaderLabels(df.columns)

        for row_idx, row_data in enumerate(df.values):
            for col_idx, cell_data in enumerate(row_data):
                # Ensure all data is converted to a string for the table widget
                item = QTableWidgetItem(str(cell_data))
                table.setItem(row_idx, col_idx, item)
        
        # 6. Make columns resize to fit their content
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)