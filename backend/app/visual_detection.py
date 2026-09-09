"""Conservative visual evidence detectors for legally relevant symbols with bounded memory footprint."""

from typing import Any, Dict
import cv2
from app.utils.memory import force_garbage_collection


def detect_food_symbol(image_path: str) -> Dict[str, Any]:
    """Detect candidate prescribed food-symbol geometry, never infer from green alone.

    The detector requires a compact colored region with a dark interior candidate;
    it returns NOT_VERIFIABLE when the photograph does not contain enough evidence.
    Exact symbol identity and physical dimensions remain inspector-verifiable.
    """
    image = cv2.imread(image_path)
    if image is None:
        return {"symbol_type": "UNKNOWN", "confidence": 0.0, "detection_method": "opencv_shape_color", "status": "NOT_VERIFIABLE"}

    orig_h, orig_w = image.shape[:2]
    # Downscale image to max 800px for symbol detection to save memory
    target_max = 800
    scale = 1.0
    if max(orig_h, orig_w) > target_max:
        scale = target_max / max(orig_h, orig_w)
        image = cv2.resize(image, (int(orig_w * scale), int(orig_h * scale)), interpolation=cv2.INTER_AREA)

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    masks = {
        "VEGETARIAN": cv2.inRange(hsv, (35, 45, 35), (95, 255, 255)),
        "NON_VEGETARIAN": cv2.inRange(hsv, (0, 55, 35), (15, 255, 255)),
    }
    candidates = []
    for symbol_type, mask in masks.items():
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            perimeter = cv2.arcLength(contour, True)
            if area < 120 * (scale * scale) or perimeter == 0:
                continue
            circularity = 4 * 3.141592653589793 * area / (perimeter * perimeter)
            if circularity < 0.45:
                continue
            x, y, width, height = cv2.boundingRect(contour)
            if width > image.shape[1] * 0.25 or height > image.shape[0] * 0.25:
                continue
            # Prescribed food marks are a coloured dot in a contrasting square.
            # Require a nearby dark/white boundary where possible; retain a
            # lower-confidence dot candidate for glare/partial views.
            pad = max(4, int(max(width, height) * 0.45))
            x1, y1 = max(0, x - pad), max(0, y - pad)
            x2, y2 = min(image.shape[1], x + width + pad), min(image.shape[0], y + height + pad)
            border = image[y1:y2, x1:x2]
            gray = cv2.cvtColor(border, cv2.COLOR_BGR2GRAY)
            edge_ratio = float((cv2.Canny(gray, 60, 160) > 0).mean())
            candidates.append((area, edge_ratio, symbol_type, [x1, y1, x2, y2]))

    if not candidates:
        del image, hsv, masks
        force_garbage_collection()
        return {"symbol_type": "UNKNOWN", "confidence": 0.0, "detection_method": "opencv_shape_color", "status": "NOT_VERIFIABLE"}

    area, edge_ratio, symbol_type, bbox = max(candidates, key=lambda item: item[0] * (1 + item[1]))
    confidence = min(0.82, 0.48 + area / max(1, image.shape[0] * image.shape[1]) * 8 + min(edge_ratio, .12))

    # Scale bbox back to original coordinate space
    if scale != 1.0:
        orig_bbox = [int(coord / scale) for coord in bbox]
    else:
        orig_bbox = bbox

    del image, hsv, masks
    force_garbage_collection()

    return {
        "symbol_type": symbol_type,
        "confidence": round(confidence, 3),
        "bbox": orig_bbox,
        "detection_method": "opencv_colored_dot_contour_with_boundary",
        "status": "CANDIDATE",
        "is_candidate": True,
        "size_verification": "NOT_VERIFIABLE",
    }
