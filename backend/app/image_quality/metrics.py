"""
Deterministic Computer Vision metric implementations using OpenCV, NumPy, and Pillow.
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageOps
from typing import Tuple, Dict, Any


def load_and_orient_analysis_image(
    image_path_or_bytes: Any,
    max_analysis_dim: int = 1920,
) -> Tuple[Image.Image, np.ndarray, np.ndarray, int, int]:
    """
    Safely load an image, correct EXIF rotation, extract original dimensions,
    and create a bounded-dimension NumPy array for fast, memory-safe CV metric calculation.

    Uses high-fidelity Lanczos resampling up to 1920px to prevent downsampling blur
    on panoramic package labels and fine statutory text print.

    Returns:
        (oriented_pil, rgb_array, gray_array, orig_width, orig_height)
    """
    if isinstance(image_path_or_bytes, (str, bytes)) and isinstance(image_path_or_bytes, str):
        pil_img = Image.open(image_path_or_bytes)
    else:
        import io
        if isinstance(image_path_or_bytes, bytes):
            pil_img = Image.open(io.BytesIO(image_path_or_bytes))
        else:
            pil_img = Image.open(image_path_or_bytes)

    # Correct EXIF orientation
    pil_img = ImageOps.exif_transpose(pil_img)

    orig_width, orig_height = pil_img.size

    # Create bounded copy for analysis
    analysis_img = pil_img.copy()
    max_dim = max(orig_width, orig_height)
    if max_dim > max_analysis_dim:
        scale = max_analysis_dim / max_dim
        new_w = max(1, int(orig_width * scale))
        new_h = max(1, int(orig_height * scale))
        analysis_img = analysis_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    if analysis_img.mode not in ("RGB", "L"):
        analysis_img = analysis_img.convert("RGB")

    rgb_array = np.array(analysis_img)
    if len(rgb_array.shape) == 2:
        gray_array = rgb_array
        rgb_array = cv2.cvtColor(gray_array, cv2.COLOR_GRAY2RGB)
    else:
        gray_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2GRAY)

    return pil_img, rgb_array, gray_array, orig_width, orig_height


def calculate_sharpness(gray: np.ndarray) -> float:
    """
    Calculate image sharpness using the variance of the Laplacian.
    Higher values indicate sharp edges and crisp text; low values indicate blur.
    """
    if gray is None or gray.size == 0:
        return 0.0
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    variance = float(laplacian.var())
    del laplacian
    return round(variance, 2)


def calculate_exposure_stats(
    gray: np.ndarray,
    dark_threshold: int = 35,
    bright_threshold: int = 248,
) -> Tuple[float, float, float]:
    """
    Calculate luminance distribution metrics:
    - mean brightness: [0, 255]
    - dark pixel ratio: fraction of pixels <= dark_threshold
    - bright pixel ratio: fraction of pixels >= bright_threshold
    """
    if gray is None or gray.size == 0:
        return 0.0, 1.0, 0.0

    mean_val = float(np.mean(gray))
    total_pixels = gray.size
    dark_count = int(np.sum(gray <= dark_threshold))
    bright_count = int(np.sum(gray >= bright_threshold))

    dark_ratio = round(dark_count / total_pixels, 4)
    bright_ratio = round(bright_count / total_pixels, 4)

    return round(mean_val, 2), dark_ratio, bright_ratio


def calculate_contrast(gray: np.ndarray) -> float:
    """
    Calculate global image contrast using the standard deviation of grayscale intensity.
    """
    if gray is None or gray.size == 0:
        return 0.0
    std_val = float(np.std(gray))
    return round(std_val, 2)


def calculate_glare_ratio(
    rgb: np.ndarray,
    gray: np.ndarray,
    luminance_threshold: int = 252,
    min_glare_area: int = 250,
) -> float:
    """
    Conservative deterministic glare detection.
    Detects contiguous, saturated highlight patches (specular reflections)
    where camera sensor is blown out and text/gradients are obliterated.
    Distinguishes shiny specular glare from legitimate white packaging labels with sharp text.
    """
    if gray is None or gray.size == 0:
        return 0.0

    # 1. Glare occurs at sensor saturation (>= 252)
    sat_mask = (gray >= luminance_threshold).astype(np.uint8) * 255
    sat_count = np.count_nonzero(sat_mask)
    total_pixels = gray.size
    if sat_count == 0:
        return 0.0

    # If almost the entire frame is uniformly near-white (>60%), this is background exposure, not a localized glare reflection
    if (sat_count / total_pixels) > 0.60:
        return 0.0

    # 2. Check saturation if RGB available (specular reflection has low saturation)
    if len(rgb.shape) == 3 and rgb.shape[2] == 3:
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        sat = hsv[:, :, 1]
        sat_low = (sat <= 45).astype(np.uint8) * 255
        sat_mask = cv2.bitwise_and(sat_mask, sat_low)

    # 3. Glare has low local texture/gradient (washed out highlight without readable text)
    grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    low_texture = (grad <= 10).astype(np.uint8) * 255

    candidate = cv2.bitwise_and(sat_mask, low_texture)

    # 4. Morphological opening to filter fine text margins and antialiasing
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    cleaned = cv2.morphologyEx(candidate, cv2.MORPH_OPEN, kernel)

    # 5. Connected components: ignore tiny pinprick highlights (< min_glare_area)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(cleaned, connectivity=8)
    total_glare_pixels = 0

    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if min_glare_area <= area < int(total_pixels * 0.60):
            total_glare_pixels += area

    ratio = round(total_glare_pixels / total_pixels, 4)
    return ratio


def calculate_text_region_metrics(
    gray: np.ndarray,
    min_gradient_threshold: int = 20,
) -> Tuple[float, int, float]:
    """
    Calculate image-detail and local contrast metrics over likely text / foreground regions.
    Prevents large uniform package backgrounds (e.g. solid white carton, solid blue label)
    from dominating the contrast decision when printed text is sharp and readable.

    Returns:
        (text_stroke_contrast, text_stroke_count, intensity_range)
    """
    if gray is None or gray.size == 0:
        return 0.0, 0, 0.0

    # Dynamic intensity range (peak-to-peak) robust against sensor hot pixels
    p_high = float(np.percentile(gray, 99.8))
    p_low = float(np.percentile(gray, 0.2))
    intensity_range = round(max(0.0, p_high - p_low), 2)

    # Detect edge transitions typical of printed characters using morphological gradient (3x3)
    kernel_grad = np.ones((3, 3), np.uint8)
    gradient = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, kernel_grad)

    stroke_mask = gradient >= min_gradient_threshold
    stroke_count = int(np.count_nonzero(stroke_mask))

    if stroke_count < 25:
        # Negligible stroke edge content
        return 0.0, stroke_count, intensity_range

    # Measure local peak-to-peak contrast across text strokes in a 5x5 neighbourhood
    kernel_local = np.ones((5, 5), np.uint8)
    dilated = cv2.dilate(gray, kernel_local)
    eroded = cv2.erode(gray, kernel_local)
    local_contrast = dilated.astype(np.float32) - eroded.astype(np.float32)

    # Average local step height on stroke pixels
    stroke_contrast = float(np.mean(local_contrast[stroke_mask]))
    return round(stroke_contrast, 2), stroke_count, intensity_range


def check_possible_cropping(
    gray: np.ndarray,
    border_fraction: float = 0.02,
    edge_density_threshold: float = 0.35,
) -> bool:
    """
    Conservative cropping detection.
    Checks whether significant edge energy (text / packaging boundary) is abruptly truncated
    at the very outer borders of the image frame.
    """
    if gray is None or gray.size == 0:
        return False

    h, w = gray.shape[:2]
    border_w = max(2, int(w * border_fraction))
    border_h = max(2, int(h * border_fraction))

    # Sobel or Canny edge detection
    edges = cv2.Canny(gray, 50, 150)

    # Extract border bands
    top_band = edges[:border_h, :]
    bot_band = edges[h - border_h:, :]
    left_band = edges[:, :border_w]
    right_band = edges[:, w - border_w:]

    for band in (top_band, bot_band, left_band, right_band):
        if band.size > 0:
            density = float(np.count_nonzero(band)) / band.size
            if density >= edge_density_threshold:
                return True

    return False
