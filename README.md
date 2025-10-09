# VISUO1: A Platform for SWIR Time-Series Image Analysis

VISUO1 is a powerful and comprehensive desktop application built with Python and PyQt6, designed to automate the entire workflow for analyzing time-series data from preclinical short-wave infrared (SWIR) imaging studies.

The application intelligently handles everything from initial file discovery and image registration to advanced statistical analysis and data visualization, ensuring consistency, reproducibility, and the discovery of meaningful biological insights from complex imaging datasets.

## Application Preview

VISUO1 Application
<img width="1726" height="1094" alt="Screenshot 2025-10-08 at 7 48 31 PM" src="https://github.com/user-attachments/assets/8263fa6a-f6f4-44a0-bb75-5bae672a6ab2" />


## ✨ Core Features

*   **Automated File Discovery:** Scans directories to automatically parse and group time-series image pairs based on filename metadata.
*   **Live Interactive Preview:** A real-time preview panel for configuring all processing parameters (overlay, intensity, LUT) before batch processing.
*   **Advanced Registration:**
    *   **Universal Template-Based:** Aligns the entire dataset to a common reference template for inter-animal consistency.
    *   **Intra-Animal Time-Series:** Aligns all frames for a single animal to its first time point to correct for movement over long sessions.
*   **Quantitative Feature Extraction:** Utilizes the powerful `pyradiomics` library to extract a wide range of quantitative features (First Order, GLCM, GLSZM) from defined signal regions.
*   **Spatiotemporal Signal Path Analysis:** Generates advanced visualizations to track signal dynamics over time, including:
    *   **Animated GIFs:** Creates a dynamic movie of the signal progression for each animal, complete with a time-progression bar.
    *   **Time-Coded Contour & Phase Maps:** Visualizes the signal's spatial boundaries and persistence over time, overlaid on the animal's anatomy.
*   **Sophisticated Data Analysis:**
    *   **Feature Ranking:** Employs statistical models (DTW, LME) to rank features based on unsupervised clustering or specific scientific hypotheses.
    *   **Heatmap Clustering:** Generates univariate and multivariate heatmaps to visualize similarities between experimental groups based on their time-series profiles.
*   **Reproducibility:** Save and load the entire application state, including all UI settings and file paths, to a JSON file for perfectly reproducible analysis.

##  Workflow Overview

The application is organized into two main stages: Processing and Analysis.

### 1. Image Processing Pipeline
This stage transforms raw, inconsistently positioned images into standardized, quantitative data and visualizations.

![20250716_G11-M-12Gy-SHOV-A02_animation](https://github.com/user-attachments/assets/810d940a-a7d1-43ae-9123-68608a4b643d)  ![20250711_G07-F-00Gy-DIZE-A03_animation](https://github.com/user-attachments/assets/868445ef-c2f8-4ffe-ba61-c5951fe8f0e8)



*   **Data Input:** The user selects a main data directory and an output directory. The app automatically finds and groups all `_WF_` (widefield) and `_FL_` (fluorescence) image pairs.
*   **Configuration:** Using the live preview, the user configures global settings like intensity normalization, LUT colormaps, registration templates, and the final cropping ROI.
*   **Batch Processing:** In a background thread, the app processes every animal to generate:
    *   Individual and Master Time-Series Collages.
    *   Animated GIFs with a time-progression bar.
    *   Advanced Signal Path Analysis maps (Contour, Phase).
    *   Two primary data files:
        *   `_Raw_Results.csv`: Contains every calculated feature for each animal at every time point.
        *   `_Group_Summary.csv`: Contains aggregated statistics (mean, median, std) for each experimental group.
          
![G05-F-12Gy-DIZE_MASTER_COLLAGE](https://github.com/user-attachments/assets/16660de4-378b-48ff-93b5-498396065dc9)

### 2. Data Analysis Pipeline
This stage provides tools to interpret the data generated during processing.



*   **Feature Ranking:** Load the `_Raw_Results.csv` to identify the most significant features using three methods:
    *   **Overall Ranking (Unsupervised):** Finds features that best separate groups based on Dynamic Time Warping (DTW) distance.
    *   **Interaction Effect (Hypothesis-Driven):** Uses a Linear Mixed-Effects model to test for interactions between factors (e.g., Time & Dose).
    *   **Normalization Effect (Hypothesis-Driven):** Ranks features on their ability to show a return-to-baseline effect for a treated group.
*   **Heatmap Clustering:** Load the `_Group_Summary.csv` to generate clustered heatmaps that visualize the similarity between experimental groups, either for a single feature or averaged across all features.
<img width="4156" height="4294" alt="multivariate_clustered_heatmap" src="https://github.com/user-attachments/assets/41a27b4a-0683-4984-a179-1530aea7cc0b" />

## 🔧 Technology Stack

*   **GUI Framework:** PyQt6
*   **Core Numerical & Array Operations:** NumPy
*   **Image Processing & Analysis:** OpenCV, Scikit-image, Tifffile
*   **Statistical Feature Extraction:** Pyradiomics
*   **Data Handling & Analysis:** Pandas, Statsmodels
*   **Plotting & Visualization:** Matplotlib, Seaborn
*   **Animation:** Imageio

## 🚀 Getting Started

### Prerequisites

*   Python 3.8 or newer
*   An environment manager like `venv` or `conda` is recommended.

### Installation & Running

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/VISUO1.git
    cd VISUO1
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the application:**
    ```bash
    python main.py
    ```

## 📁 Project Architecture

The project uses a modular architecture that separates the user interface from the backend processing logic.
