# processing/image_processor.py

import numpy as np
import os
import cv2
from matplotlib import colormaps
from tifffile import imwrite
from typing import List, Tuple, Optional
import imageio


COLOR_MAP = {
    "White": (255, 255, 255),
    "Yellow": (0, 255, 255),
    "Cyan": (255, 255, 0),
    "Lime Green": (0, 255, 0)
}

def apply_lut(
    gray_image: np.ndarray, 
    min_val: int, 
    max_val: int, 
    cmap_name: str = 'nipy_spectral'
) -> np.ndarray:
    """
    Applies a matplotlib colormap to a grayscale image after normalizing it.

    Args:
        gray_image (np.ndarray): The 2D input grayscale image.
        min_val (int): The intensity value that will be mapped to the bottom of the colormap.
        max_val (int): The intensity value that will be mapped to the top of the colormap.
        cmap_name (str): The name of the matplotlib colormap to use.

    Returns:
        np.ndarray: The 3D RGB image (dtype=uint8).
    """
    # Clip the image data to the specified min/max range
    clipped_image = np.clip(gray_image, min_val, max_val)
    
    # Normalize the clipped image to the 0-1 range
    if max_val > min_val:
        normalized_image = (clipped_image - min_val) / (max_val - min_val)
    else:
        normalized_image = np.zeros_like(clipped_image, dtype=float)

    # Get the colormap from matplotlib and apply it
    cmap = colormaps.get_cmap(cmap_name)
    colored_image = cmap(normalized_image)
    
    # Convert from RGBA (0-1 float) to RGB (0-255 uint8)
    rgb_image = (colored_image[:, :, :3] * 255).astype(np.uint8)
    
    return rgb_image

# --- FINAL CORRECTED create_overlay METHOD for processing/image_processor.py ---

def create_overlay(
    wf_image: np.ndarray, 
    fl_image_rgb: np.ndarray, 
    transparency_percent: int
) -> np.ndarray:
    """
    Overlays a colored fluorescence image onto a white field image,
    robustly handling different input data types.
    """
    # 1. Check if the wf_image is already in the expected uint8 format.
    if wf_image.dtype != np.uint8:
        # 2. If it's not (e.g., it's uint16), normalize its values to the 0-255 range
        #    and then convert the data type to uint8. This is the safe way.
        wf_image_normalized = cv2.normalize(wf_image, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    else:
        # If it's already uint8, just use it.
        wf_image_normalized = wf_image
    
    # 3. Now that we have a guaranteed uint8, single-channel image, convert it to RGB.
    # This call will no longer fail.
    wf_image_rgb = cv2.cvtColor(wf_image_normalized, cv2.COLOR_GRAY2RGB)
    
    # Alpha is the weight of the second image (FL)
    alpha = transparency_percent / 100.0
    beta = 1.0 - alpha
    
    # Blend the two images
    overlay_image = cv2.addWeighted(wf_image_rgb, beta, fl_image_rgb, alpha, 0)
    
    return overlay_image

def create_gradient_image(height: int, width: int, cmap_name: str) -> np.ndarray:
    """
    Generates a simple vertical color gradient image as a NumPy array.
    """
    gradient = np.linspace(1, 0, height).reshape(height, 1)
    cmap = colormaps.get_cmap(cmap_name)
    rgb_gradient = (cmap(gradient)[:, :, :3] * 255).astype(np.uint8)
    # Tile it horizontally to get the desired width
    gradient_img = np.tile(rgb_gradient, (1, width, 1))
    return gradient_img

def create_colorbar_image(
    height: int,
    total_width: int, # Changed from gradient_width
    min_val: int,
    max_val: int,
    cmap_name: str,
    font_size: int,
    font_color: Tuple[int, int, int]
) -> np.ndarray:
    """
    Creates a single, seamless vertical color bar with text drawn directly on it.
    """
    # 1. Create the color gradient bar that fills the entire width
    gradient = np.linspace(1, 0, height).reshape(height, 1)
    cmap = colormaps.get_cmap(cmap_name)
    rgb_gradient = (cmap(gradient)[:, :, :3] * 255).astype(np.uint8)
    # The gradient now takes up the total_width
    colorbar_img = np.tile(rgb_gradient, (1, total_width, 1))

    # 2. Prepare for drawing text
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = cv2.getFontScaleFromHeight(font, font_size, 1)
    thickness = 1
    margin = 5  # Small margin from the top/bottom edges

    # 3. Draw the "Max" value text at the top
    max_text = str(max_val)
    (tw, th), _ = cv2.getTextSize(max_text, font, font_scale, thickness)
    pos_max = ((total_width - tw) // 2, th + margin) # Centered horizontally
    
    # Draw stroked text for readability: black outline, then white fill
    cv2.putText(colorbar_img, max_text, pos_max, font, font_scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(colorbar_img, max_text, pos_max, font, font_scale, font_color, thickness, cv2.LINE_AA)

    # 4. Draw the "Min" value text at the bottom
    min_text = str(min_val)
    (tw, th), _ = cv2.getTextSize(min_text, font, font_scale, thickness)
    pos_min = ((total_width - tw) // 2, height - margin) # Centered horizontally
    
    # Draw stroked text for readability
    cv2.putText(colorbar_img, min_text, pos_min, font, font_scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(colorbar_img, min_text, pos_min, font, font_scale, font_color, thickness, cv2.LINE_AA)
    
    return colorbar_img

def crop_image(image: np.ndarray, roi: Tuple[int, int, int, int]) -> np.ndarray:
    """
    Crops an image using a specified Region of Interest (ROI).

    Args:
        image (np.ndarray): The image to crop.
        roi (Tuple[int, int, int, int]): A tuple (x, y, width, height).

    Returns:
        np.ndarray: The cropped image.
    """
    x, y, w, h = roi
    return image[y:y+h, x:x+w]

def add_timestamp_to_image(image, time_point_str, font_size, font_color):
    text = f"{int(time_point_str)} min"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = cv2.getFontScaleFromHeight(font, font_size, 1)
    thickness = 1 if font_size < 20 else 2
    (text_width, text_height), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    margin = 10
    image_height, image_width, _ = image.shape
    position = (image_width - text_width - margin, text_height + margin)
    cv2.putText(image, text, position, font, font_scale, font_color, thickness, cv2.LINE_AA)
    return image

def create_placeholder_image(
    width: int, 
    height: int, 
    text: str = "X", 
    font_size: int = 40, 
    color: tuple = (255, 0, 0)
) -> np.ndarray:
    """
    Creates a black image with centered text.

    Args:
        width (int): The width of the placeholder image.
        height (int): The height of the placeholder image.
        text (str): The text to display. Defaults to "Missing".
        font_size (int): The desired height of the font in pixels.
        color (tuple): The BGR color of the text. Defaults to Red.

    Returns:
        np.ndarray: The placeholder image with centered text.
    """
    # Create a black background
    placeholder = np.zeros((height, width, 3), dtype=np.uint8)
    
    # --- Text Centering Logic ---
    font = cv2.FONT_HERSHEY_SIMPLEX
    # Calculate the font scale and thickness based on desired pixel height
    font_scale = cv2.getFontScaleFromHeight(font, font_size, 1)
    thickness = 2 if font_size > 30 else 1
    
    # Get the size of the text box to calculate the center position
    (text_width, text_height), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    
    # Calculate the X,Y coordinates for the text's bottom-left corner to be centered
    text_x = (width - text_width) // 2
    text_y = (height + text_height) // 2
    
    # Draw the text on the placeholder image
    cv2.putText(placeholder, text, (text_x, text_y), font, font_scale, color, thickness, cv2.LINE_AA)
    
    return placeholder

def assemble_and_save_collage(image_list: List[np.ndarray], output_path: str):
    """
    Horizontally stacks a list of images and saves the result as a TIFF file.

    Args:
        image_list (List[np.ndarray]): A list of images (as NumPy arrays) to be collaged.
        output_path (str): The full path, including filename, to save the collage.
    """
    if not image_list:
        print(f"Warning: Empty image list provided for collage: {output_path}")
        return
        
    # Horizontally stack the images
    collage = np.hstack(image_list)
    
    # Create the directory if it doesn't exist
    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)
    
    # Save using tifffile to preserve data integrity
    imwrite(output_path, collage)

def create_animation_from_frames(frames: List[np.ndarray], output_path: str):
    """
    Creates a GIF animation from a list of image frames.

    Args:
        frames (List[np.ndarray]): A list of RGB frames (as NumPy arrays).
        output_path (str): The full path to save the .gif file.
    """
    if not frames:
        return
    # duration=0.5 means each frame is displayed for 0.5 seconds
    imageio.mimsave(output_path, frames, duration=0.5, loop=10)

def add_progress_bar_to_image(
    image: np.ndarray, 
    current_step: int, 
    total_steps: int,
    bar_height: int = 5
) -> np.ndarray:
    """
    Draws a progress bar at the bottom of an image frame.

    Args:
        image: The image to draw on (must be a color image, e.g., RGB/BGR).
        current_step: The current frame number (0-indexed).
        total_steps: The total number of frames in the sequence.
        bar_height: The thickness of the progress bar in pixels.

    Returns:
        The image with the progress bar drawn on it.
    """
    # Make a copy to avoid modifying the original image if it's used elsewhere
    image_with_bar = image.copy()
    h, w, _ = image_with_bar.shape

    # --- Calculate the width of the filled portion of the bar ---
    # We use (current_step + 1) so the last frame (index N-1) shows a full bar
    progress_fraction = (current_step + 1) / total_steps
    filled_width = int(w * progress_fraction)

    # --- Define the bar's position and colors ---
    # Position will be at the very bottom of the image
    pt1_bg = (0, h - bar_height)
    pt2_bg = (w, h)
    
    pt1_fill = (0, h - bar_height)
    pt2_fill = (filled_width, h)
    
    bg_color = (50, 50, 50)      # Dark gray for the background/unfilled part
    fill_color = (255, 255, 0)   # Cyan/Yellow for the filled part
    outline_color = (150, 150, 150) # Light gray for the border

    # --- Draw the components ---
    # 1. Draw the dark background for the entire bar area
    cv2.rectangle(image_with_bar, pt1_bg, pt2_bg, bg_color, -1) # -1 means filled
    
    # 2. Draw the bright filled portion on top of the background
    cv2.rectangle(image_with_bar, pt1_fill, pt2_fill, fill_color, -1)
    
    # 3. Draw a thin outline around the entire bar for a clean look
    cv2.rectangle(image_with_bar, pt1_bg, pt2_bg, outline_color, 1) # 1 pixel thickness

    return image_with_bar

def create_time_colorbar(height: int, cmap_name: str, min_time: int, max_time: int) -> np.ndarray:
    """
    Creates a vertical color bar specifically for a time series.
    """
    width = 100
    margin = 10
    font_size = 20
    
    # Create the color gradient bar
    gradient = np.linspace(1, 0, height).reshape(height, 1)
    cmap = colormaps.get_cmap(cmap_name)
    rgb_gradient = (cmap(gradient)[:, :, :3] * 255).astype(np.uint8)
    gradient_bar = np.tile(rgb_gradient, (1, width // 2, 1))

    # Create the text area
    text_area = np.zeros((height, width // 2, 3), dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = cv2.getFontScaleFromHeight(font, font_size, 1)
    
    # Max time label (top)
    max_text = f"{max_time} min"
    (tw, th), _ = cv2.getTextSize(max_text, font, font_scale, 1)
    pos_max = ((width // 2 - tw) // 2, th + margin)
    cv2.putText(text_area, max_text, pos_max, font, font_scale, (255, 255, 255), 1, cv2.LINE_AA)

    # Min time label (bottom)
    min_text = f"{min_time} min"
    (tw, _), _ = cv2.getTextSize(min_text, font, font_scale, 1)
    pos_min = ((width // 2 - tw) // 2, height - margin)
    cv2.putText(text_area, min_text, pos_min, font, font_scale, (255, 255, 255), 1, cv2.LINE_AA)

    return np.hstack([gradient_bar, text_area])

def create_phase_colorbar(height: int) -> np.ndarray:
    """
    Creates a discrete color bar for the Early/Mid/Late phase map.
    """
    width = 150
    color_box_h = height // 8
    margin = 10
    font_size = 18
    
    colorbar = np.zeros((height, width, 3), dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = cv2.getFontScaleFromHeight(font, font_size, 1)

    phases = {
        "Early": (0, 0, 255),        # Red (BGR)
        "Mid": (0, 255, 0),          # Green
        "Late": (255, 0, 0),         # Blue
        "Early+Mid": (0, 255, 255),  # Yellow
        "Mid+Late": (255, 255, 0),   # Cyan
        "Early+Late": (255, 0, 255), # Magenta
        "All Phases": (255, 255, 255) # White
    }
    
    y_pos = margin + color_box_h
    for name, color in phases.items():
        # Draw color swatch
        cv2.rectangle(colorbar, (margin, y_pos - color_box_h), (margin + 30, y_pos), color, -1)
        # Draw text label
        text_pos = (margin + 40, y_pos - (color_box_h - font_size) // 2)
        cv2.putText(colorbar, name, text_pos, font, font_scale, (255, 255, 255), 1, cv2.LINE_AA)
        y_pos += color_box_h + (margin // 2)

    return colorbar

# --- Animal outline helpers (for preview and pipeline reuse) ---

def compute_animal_outline(
    image: np.ndarray,
    method: str = 'otsu',
    threshold: Optional[int] = None,
    otsu_boost_percent: int = 10
) -> Optional[np.ndarray]:
    """
    Compute the largest external contour of the animal from a single-channel image.
    - If 'threshold' is provided, apply a binary threshold (image >= threshold).
    - If no contour is found (or no threshold provided), fall back to Otsu on an 8-bit normalized image,
      then increase the threshold by ~10% to get a tighter outline.

    Returns:
        contour (Nx1x2 or Nx2) in image pixel coordinates, or None if not found.
    """
    if image is None:
        return None
    # Ensure 2D single channel
    img = image
    if img.ndim == 3:
        # Handle color or multi-frame stacks
        if img.shape[-1] in (3, 4) and img.shape[0] not in (3, 4):
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        elif img.shape[0] > 1:
            img = np.max(img, axis=0)
        else:
            img = img.squeeze()
    method = (method or 'otsu').lower()
    contours = None
    if method == 'manual':
        if threshold is None:
            return None
        try:
            # Speed-up: work at reduced resolution for very large images, then scale back
            h, w = img.shape[:2]
            scale = 1.0
            max_dim = max(h, w)
            if max_dim >= 4096:
                scale = 0.25
            elif max_dim >= 2048:
                scale = 0.5
            if scale < 1.0:
                small_size = (max(1, int(w * scale)), max(1, int(h * scale)))
                small_img = cv2.resize(img, small_size, interpolation=cv2.INTER_AREA)
                small_mask = (small_img >= threshold).astype(np.uint8) * 255
                contours, _ = cv2.findContours(small_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    best = max(contours, key=cv2.contourArea)
                    # Scale contour coordinates back to original image space
                    best = (best.astype(np.float32) / scale).astype(np.int32)
                    return best
            # Fallback or small images: full-res
            mask = (img >= threshold).astype(np.uint8) * 255
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                return max(contours, key=cv2.contourArea)
        except Exception:
            return None
        return None
    elif method == 'otsu':
        try:
            img8 = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            otsu_val, _ = cv2.threshold(img8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            boost = max(0, int(otsu_boost_percent))
            aggressive = min(255, int(otsu_val * (1.0 + (boost / 100.0))))
            _, mask2 = cv2.threshold(img8, aggressive, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(mask2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                return max(contours, key=cv2.contourArea)
        except Exception:
            return None
        return None
    else:
        # Unknown method; default to None
        return None

def draw_outline_on_image(rgb_image: np.ndarray, contour: np.ndarray, color_rgb: Tuple[int, int, int], thickness: int = 3) -> np.ndarray:
    """
    Draw a single contour on an RGB image. The color should be in (R,G, B) order.
    Returns a modified copy; original is not altered.
    """
    if rgb_image is None or contour is None:
        return rgb_image
    out = rgb_image.copy()
    # OpenCV drawContours does not care about color space; ensure we pass the tuple matching array channel order (RGB here)
    cv2.drawContours(out, [contour], -1, color_rgb, thickness)
    return out