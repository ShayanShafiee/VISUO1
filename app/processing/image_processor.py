# processing/image_processor.py

import numpy as np
import os
import cv2
from matplotlib import colormaps
from tifffile import imwrite
from typing import List, Tuple
import imageio


def apply_lut(
    gray_image: np.ndarray, 
    min_val: int, 
    max_val: int, 
    cmap_name: str = 'hot'
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

def create_colorbar_image(
    height: int,
    gradient_width: int, # Width of just the color gradient part
    min_val: int,
    max_val: int,
    cmap_name: str,
    font_size: int,
    font_color: Tuple[int, int, int]
) -> np.ndarray:
    """
    Creates a vertical colorbar with dynamically sized text area and stroked labels.
    """
    # 1. Determine required text area width
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = cv2.getFontScaleFromHeight(font, font_size, 1)
    thickness = 1 if font_size < 20 else 2
    
    max_text = str(max_val)
    min_text = str(min_val)
    
    (tw_max, _), _ = cv2.getTextSize(max_text, font, font_scale, thickness)
    (tw_min, _), _ = cv2.getTextSize(min_text, font, font_scale, thickness)
    
    margin = 10
    text_area_width = max(tw_max, tw_min) + (2 * margin)

    # 2. Create the color gradient bar
    gradient = np.linspace(1, 0, height).reshape(height, 1)
    cmap = colormaps.get_cmap(cmap_name)
    colored_gradient = cmap(gradient)
    rgb_gradient = (colored_gradient[:, :, :3] * 255).astype(np.uint8)
    gradient_bar = np.tile(rgb_gradient, (1, gradient_width, 1))

    # 3. Create the black text area
    text_area = np.zeros((height, text_area_width, 3), dtype=np.uint8)

    # 4. Add stroked text labels
    stroke_color = (0, 0, 0)
    stroke_thickness = thickness + 2

    # Max value label (top) - right-aligned
    (_, th), _ = cv2.getTextSize(max_text, font, font_scale, thickness)
    pos_max = (text_area_width - tw_max - margin, th + margin)
    cv2.putText(text_area, max_text, pos_max, font, font_scale, stroke_color, stroke_thickness, cv2.LINE_AA)
    cv2.putText(text_area, max_text, pos_max, font, font_scale, font_color, thickness, cv2.LINE_AA)

    # Min value label (bottom) - right-aligned
    pos_min = (text_area_width - tw_min - margin, height - margin)
    cv2.putText(text_area, min_text, pos_min, font, font_scale, stroke_color, stroke_thickness, cv2.LINE_AA)
    cv2.putText(text_area, min_text, pos_min, font, font_scale, font_color, thickness, cv2.LINE_AA)
    
    # 5. Combine into final image
    final_colorbar = np.hstack([gradient_bar, text_area])
    return final_colorbar

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