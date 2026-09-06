"""
Image preprocessing pipeline using OpenCV and Pillow.

Applies basic corrections to improve OCR accuracy while preserving the original
image. Multiple OCR-ready variants are generated to improve robustness on glare,
shadows, low contrast, and rotated packaging labels.
"""

import os
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ExifTags
from typing import Tuple, List

from app.utils.helpers import ensure_directory

MAX_DIMENSION = 2048
MIN_DIMENSION = 300


def fix_orientation(image: Image.Image) -> Image.Image:
    """Fix image orientation using EXIF data when the phone stores it there."""
    try:
        exif = image._getexif()
        if exif is None:
            return image

        orientation_key = None
        for key, val in ExifTags.TAGS.items():
            if val == "Orientation":
                orientation_key = key
                break

        if orientation_key is None or orientation_key not in exif:
            return image

        orientation = exif[orientation_key]
        if orientation == 3:
            image = image.rotate(180, expand=True)
        elif orientation == 6:
            image = image.rotate(270, expand=True)
        elif orientation == 8:
            image = image.rotate(90, expand=True)
    except (AttributeError, KeyError, TypeError):
        pass
    return image


def resize_image(image: np.ndarray, max_dim: int = MAX_DIMENSION) -> np.ndarray:
    """Resize image so the largest dimension does not exceed max_dim."""
    h, w = image.shape[:2]
    if max(h, w) <= max_dim:
        return image
    scale = max_dim / max(h, w)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)


def convert_to_grayscale(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def enhance_contrast(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 3:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_channel = clahe.apply(l_channel)
        enhanced = cv2.merge([l_channel, a, b])
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(image)


def denoise_image(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 3:
        return cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)
    return cv2.fastNlMeansDenoising(image, None, 10, 7, 21)


def sharpen_image(image: np.ndarray) -> np.ndarray:
    kernel = np.array([
        [0, -0.5, 0],
        [-0.5, 3, -0.5],
        [0, -0.5, 0]
    ])
    return cv2.filter2D(image, -1, kernel)


def _save_variant(output_dir: str, image_name: str, image: np.ndarray) -> str:
    ensure_directory(output_dir)
    output_path = os.path.join(output_dir, image_name)
    cv2.imwrite(output_path, image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return output_path


def build_ocr_variants(input_path: str, output_dir: str, include_all: bool = False) -> List[str]:
    """Create OCR variants.

    The normal scan path deliberately uses the processed image as its first pass.
    Extra variants are retained for a targeted retry only: running six complete
    detector/recogniser passes for every photograph made multi-image scans slow.
    """
    with Image.open(input_path) as pil_image:
        pil_image = fix_orientation(pil_image)
        if pil_image.mode not in ("RGB", "L"):
            pil_image = pil_image.convert("RGB")
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        variants = []

        cv_base = np.array(pil_image)
        if len(cv_base.shape) == 3:
            cv_base = cv2.cvtColor(cv_base, cv2.COLOR_RGB2BGR)
        cv_base = resize_image(cv_base)
        variants.append(("original", cv_base))

        if include_all:
            gray = convert_to_grayscale(cv_base)
            variants.append(("grayscale", gray))
            contrast = enhance_contrast(cv_base)
            variants.append(("contrast", contrast))
            variants.append(("sharpened", sharpen_image(contrast)))
            variants.append(("gray_sharp", sharpen_image(gray)))
            _, threshold = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            variants.append(("threshold", threshold))

    saved_paths = []
    for variant_name, variant_image in variants:
        saved_paths.append(_save_variant(output_dir, f"ocr_{variant_name}_{base_name}.jpg", variant_image))
    return saved_paths


def preprocess_image(input_path: str, output_dir: str, filename_prefix: str = "processed") -> Tuple[str, dict]:
    """Generate a single improved OCR processing image for the standard pipeline."""
    ensure_directory(output_dir)
    preprocessing_info = {"original_path": input_path, "steps_applied": [], "original_size": None, "processed_size": None}

    with Image.open(input_path) as pil_image:
        preprocessing_info["original_size"] = pil_image.size
        pil_image = fix_orientation(pil_image)
        preprocessing_info["steps_applied"].append("orientation_fix")
        if pil_image.mode not in ("RGB", "L"):
            pil_image = pil_image.convert("RGB")
            preprocessing_info["steps_applied"].append("mode_conversion")
        cv_image = np.array(pil_image)
        if len(cv_image.shape) == 3:
            cv_image = cv2.cvtColor(cv_image, cv2.COLOR_RGB2BGR)

    cv_image = resize_image(cv_image)
    preprocessing_info["steps_applied"].append("resize")
    cv_image = enhance_contrast(cv_image)
    preprocessing_info["steps_applied"].append("contrast_enhancement")
    cv_image = denoise_image(cv_image)
    preprocessing_info["steps_applied"].append("denoise")
    cv_image = sharpen_image(cv_image)
    preprocessing_info["steps_applied"].append("sharpen")

    h, w = cv_image.shape[:2]
    preprocessing_info["processed_size"] = (w, h)
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_filename = f"{filename_prefix}_{base_name}.jpg"
    output_path = os.path.join(output_dir, output_filename)
    cv2.imwrite(output_path, cv_image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    preprocessing_info["processed_path"] = output_path
    return output_path, preprocessing_info
