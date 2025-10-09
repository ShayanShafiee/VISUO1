# processing/registration.py

import cv2
import numpy as np
from typing import Tuple

def center_image_pair_with_template(
    wf_image: np.ndarray, 
    fl_image: np.ndarray, 
    template_image: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Aligns a WF image to the center of the frame based on a template,
    and applies the exact same translation to its corresponding FL image.

    Args:
        wf_image (np.ndarray): The white-field image to perform template matching on.
        fl_image (np.ndarray): The fluorescence image to be transformed.
        template_image (np.ndarray): A small, cropped image of the feature to find.

    Returns:
        A tuple containing the (centered_wf_image, centered_fl_image).
    """
    if wf_image is None or fl_image is None or template_image is None:
        raise ValueError("Input images cannot be None.")

    # Ensure images are in a compatible format for OpenCV (e.g., grayscale 8-bit or 32-bit float)
    wf_gray = cv2.normalize(wf_image, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    template_gray = cv2.normalize(template_image, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    
    # Perform template matching
    # TM_CCOEFF_NORMED is a robust method for this
    result = cv2.matchTemplate(wf_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    _, _, _, max_loc = cv2.minMaxLoc(result)
    
    # Get dimensions
    h_img, w_img = wf_image.shape[:2]
    h_tmpl, w_tmpl = template_image.shape[:2]
    
    # Calculate the center of the found template region
    match_center_x = max_loc[0] + w_tmpl / 2
    match_center_y = max_loc[1] + h_tmpl / 2
    
    # Calculate the center of the main image
    frame_center_x = w_img / 2
    frame_center_y = h_img / 2
    
    # Calculate the shift required to move the match center to the frame center
    delta_x = frame_center_x - match_center_x
    delta_y = frame_center_y - match_center_y
    
    # Create the transformation matrix for translation
    translation_matrix = np.float32([[1, 0, delta_x], [0, 1, delta_y]])
    
    # Apply the affine transformation (translation) to both images
    centered_wf = cv2.warpAffine(wf_image, translation_matrix, (w_img, h_img), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    centered_fl = cv2.warpAffine(fl_image, translation_matrix, (w_img, h_img), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    
    return centered_wf, centered_fl