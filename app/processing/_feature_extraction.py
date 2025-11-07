# processing/_feature_extraction.py


"""Legacy simple feature extraction helpers.

This module provides a lightweight alternative set of feature calculations for
fluorescence images when full pyradiomics extraction is not required. It
derives intensity, shape, histogram, and basic texture (GLCM) features from a
threshold-defined signal mask.

Intended usage: internal fallback or experimental feature sets. The main
pipeline currently uses `processing.feature_extraction.calculate_pyradiomics_features`.
"""

import numpy as np
from scipy.stats import kurtosis, skew
from skimage.feature import graycomatrix, graycoprops
from skimage import measure

def calculate_all_features(fl_image: np.ndarray, threshold: int, selected_features: list) -> dict:
    """
    Calculates a suite of features from a fluorescence image based on a signal mask.

    Args:
        fl_image (np.ndarray): The cropped, single-channel fluorescence image.
        threshold (int): The intensity value above which pixels are considered signal.
        selected_features (list): A list of strings of features to calculate.

    Returns:
        A dictionary containing the calculated feature values.
    """
    # 1. Create the binary signal mask
    mask = fl_image > threshold
    
    # Get the intensity values of only the signal pixels
    signal_pixels = fl_image[mask]

    if signal_pixels.size == 0:
        return {} # Return empty dict if no signal is found

    features = {}

    # --- Category 1: Intensity-Based ---
    if 'robust_mean_intensity' in selected_features:
        # Calculate mean of the top 10th percentile of signal pixels
        percentile_val = np.percentile(signal_pixels, 90)
        top_pixels = signal_pixels[signal_pixels >= percentile_val]
        features['robust_mean_intensity'] = np.mean(top_pixels) if top_pixels.size > 0 else 0

    if 'total_integrated_intensity' in selected_features:
        features['total_integrated_intensity'] = np.sum(signal_pixels)

    if 'mean_intensity' in selected_features:
        features['mean_intensity'] = np.mean(signal_pixels)

    # --- Category 2: Shape & Localization ---
    if 'area' in selected_features:
        features['area'] = signal_pixels.size

    # Use scikit-image's regionprops for centroid and shape features
    # Note: regionprops needs a "label image", where each connected component is numbered.
    label_image = measure.label(mask)
    props = measure.regionprops(label_image, intensity_image=fl_image)
    
    if props: # Ensure at least one region was found
        main_prop = props[0] # Assume the largest region is the one of interest
        
        if 'centroid_y' in selected_features or 'centroid_x' in selected_features:
            # Centroid is returned as (row, col) which corresponds to (y, x)
            features['centroid_y'] = main_prop.centroid[0]
            features['centroid_x'] = main_prop.centroid[1]
        
        if 'circularity' in selected_features:
            # Formula for circularity: (4 * pi * Area) / (Perimeter^2)
            # Robust against objects with holes
            if main_prop.perimeter > 0:
                features['circularity'] = (4 * np.pi * main_prop.area) / (main_prop.perimeter ** 2)
            else:
                features['circularity'] = 0

    # --- Category 3: Histogram-Based Dispersion ---
    if 'intensity_variance' in selected_features:
        features['intensity_variance'] = np.var(signal_pixels)
    
    if 'kurtosis' in selected_features:
        features['kurtosis'] = kurtosis(signal_pixels)
        
    if 'skewness' in selected_features:
        features['skewness'] = skew(signal_pixels)

    # --- Category 4: GLCM Texture Features ---
    glcm_features_needed = [f for f in ['glcm_contrast', 'glcm_homogeneity', 'glcm_energy'] if f in selected_features]
    if glcm_features_needed:
        # GLCM requires 8-bit integer images. We scale the signal pixels to 0-255.
        scaled_pixels = np.clip(signal_pixels, 0, 65535) # Ensure no overflow
        scaled_pixels = (scaled_pixels / 65536 * 255).astype(np.uint8)

        # Create a blank image and place the scaled signal pixels back for GLCM calculation
        glcm_image = np.zeros_like(fl_image, dtype=np.uint8)
        glcm_image[mask] = scaled_pixels
        
        # Calculate GLCM. We check pixels right next to each other (distance 1, angle 0).
        # symmetric=True averages the results for 0 and 180 degrees.
        glcm = graycomatrix(glcm_image, distances=[1], angles=[0], levels=256, symmetric=True, normed=True)
        
        if 'glcm_contrast' in selected_features:
            features['glcm_contrast'] = graycoprops(glcm, 'contrast')[0, 0]
        if 'glcm_homogeneity' in selected_features:
            features['glcm_homogeneity'] = graycoprops(glcm, 'homogeneity')[0, 0]
        if 'glcm_energy' in selected_features:
            features['glcm_energy'] = graycoprops(glcm, 'energy')[0, 0]

    return features