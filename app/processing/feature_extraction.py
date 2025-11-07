# processing/feature_extraction.py


"""Pyradiomics feature extraction helpers.

Defines a single utility function that creates a fresh RadiomicsFeatureExtractor
per call (avoids cross-run state leakage), enables only requested feature
classes, applies normalization, and returns a cleaned feature dictionary with
diagnostic keys removed.

Public API:
 - calculate_pyradiomics_features(image, mask, enabled_classes) -> dict
 - calculate_all_features (alias kept for backward compatibility)
"""

import numpy as np
import logging
from radiomics import featureextractor, setVerbosity
import SimpleITK as sitk
from typing import Dict, List, Optional

# Set the global verbosity level just once when the module is imported.
# This is better than setting it inside a function that's called repeatedly.
setVerbosity(logging.ERROR)

def calculate_pyradiomics_features(
    fl_image: np.ndarray,
    mask: Optional[np.ndarray],
    enabled_feature_classes: List[str]
) -> Dict[str, float]:
    """
    Calculates features for a single image using a locally created and configured extractor.
    """
    try:
        # 1. Define settings dictionary
        settings = {
            'setting': {
                'force2D': True,
                'label': 1,
                'normalize': True,
                'normalizeScale': 100,
                'resampledPixelSpacing': None,
            }
        }
        
        # 2. Instantiate a new, local extractor for this specific call
        extractor = featureextractor.RadiomicsFeatureExtractor(settings)

        # 3. Enable ONLY the feature classes requested for THIS run
        extractor.disableAllFeatures()
        for feature_class in enabled_feature_classes:
            extractor.enableFeatureClassByName(feature_class)

        # 4. Perform the extraction: use provided binary mask or default to all-ones
        if mask is None:
            mask_np = np.ones_like(fl_image, dtype=np.uint8)
        else:
            mask_np = (mask.astype(np.uint8) > 0).astype(np.uint8)
        if np.sum(mask_np) < 2:
            return {}
        
        image_sitk = sitk.GetImageFromArray(fl_image)
        mask_sitk = sitk.GetImageFromArray(mask_np)
        mask_sitk.CopyInformation(image_sitk)

        feature_vector = extractor.execute(image_sitk, mask_sitk, label=1)

        clean_features = {
            name: float(value) for name, value in feature_vector.items() 
            if not name.startswith('diagnostics_')
        }
        return clean_features

    except Exception as e:
        # This will catch any errors, including LinAlgError, and prevent a crash
        # print(f"Warning: Pyradiomics feature extraction failed for one image. Error: {e}")
        return {}

# Alias for backwards compatibility if needed elsewhere, though we will fix the worker's import.
calculate_all_features = calculate_pyradiomics_features