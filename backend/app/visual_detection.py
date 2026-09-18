"""Conservative visual evidence detectors for legally relevant symbols with bounded memory footprint."""

from typing import Any, Dict, List, Tuple
import cv2
import numpy as np
from app.utils.memory import force_garbage_collection


def detect_food_symbol(image_input: Any) -> Dict[str, Any]:
    """Detect candidate prescribed food-symbol geometry (FSSAI Regulations).

    Statutory Requirements:
    - Vegetarian: Green filled circle inside a green square outline with contrasting background.
    - Non-Vegetarian: Brown filled triangle or circle inside a brown square outline with contrasting background.

    The detector enforces structural enclosing square outline verification, shape fidelity
    (circularity/triangularity), and color consistency. It never infers non-vegetarian from
    isolated red artwork or low-confidence noise, and returns UNKNOWN/NOT_VERIFIABLE when
    evidence is absent or ambiguous.
    """
    if isinstance(image_input, np.ndarray):
        if image_input.size == 0 or len(image_input.shape) < 2:
            return {
                "detected": False,
                "symbol_type": "UNKNOWN",
                "confidence": 0.0,
                "detection_method": "fssai_prescribed_symbol_detector",
                "status": "NOT_VERIFIABLE",
            }
        image = image_input.copy()
    elif isinstance(image_input, str):
        image = cv2.imread(image_input)
    else:
        image = None

    if image is None:
        return {
            "detected": False,
            "symbol_type": "UNKNOWN",
            "confidence": 0.0,
            "detection_method": "fssai_prescribed_symbol_detector",
            "status": "NOT_VERIFIABLE",
        }

    orig_h, orig_w = image.shape[:2]
    # Downscale image to max 900px for symbol detection to preserve memory and latency
    target_max = 900
    scale = 1.0
    if max(orig_h, orig_w) > target_max:
        scale = target_max / max(orig_h, orig_w)
        image = cv2.resize(
            image,
            (int(orig_w * scale), int(orig_h * scale)),
            interpolation=cv2.INTER_AREA,
        )

    img_h, img_w = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    b_ch, g_ch, r_ch = cv2.split(image)

    # 1. Dual-Space Color Masks: HSV range corroborated by RGB channel dominance
    # Green Vegetarian Mask
    green_hsv = cv2.inRange(hsv, (35, 45, 35), (88, 255, 255))
    green_rgb = (g_ch > (r_ch.astype(np.float32) * 1.10)) & (g_ch > (b_ch.astype(np.float32) * 1.10)) & (g_ch > 40)
    green_mask = cv2.bitwise_and(green_hsv, green_rgb.astype(np.uint8) * 255)

    # Brown / Deep-Red Non-Vegetarian Mask
    # Under FSSAI, non-veg is brown/red-brown. Saturation must be sufficient to exclude beiges/skin tones.
    brown_hsv_1 = cv2.inRange(hsv, (0, 65, 30), (14, 255, 200))
    brown_hsv_2 = cv2.inRange(hsv, (168, 65, 30), (180, 255, 200))
    brown_hsv = cv2.bitwise_or(brown_hsv_1, brown_hsv_2)
    brown_rgb = (r_ch > (g_ch.astype(np.float32) * 1.15)) & (r_ch > (b_ch.astype(np.float32) * 1.10)) & (r_ch > 40)
    brown_mask = cv2.bitwise_and(brown_hsv, brown_rgb.astype(np.uint8) * 255)

    masks = {
        "VEGETARIAN": green_mask,
        "NON_VEGETARIAN": brown_mask,
    }

    candidates: List[Dict[str, Any]] = []

    # Packaging symbol dimension bounds
    min_symbol_dim = max(10, int(12 * scale))
    max_symbol_dim = max(60, int(min(img_w, img_h) * 0.35))
    min_area = max(35, int(45 * scale * scale))
    max_area = int(img_w * img_h * 0.12)

    for symbol_type, mask in masks.items():
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area or area > max_area:
                continue

            perimeter = cv2.arcLength(contour, True)
            if perimeter == 0:
                continue

            x, y, width, height = cv2.boundingRect(contour)
            if width < min_symbol_dim or height < min_symbol_dim:
                continue
            if width > max_symbol_dim or height > max_symbol_dim:
                continue

            aspect_ratio = width / max(1, height)
            if not (0.65 <= aspect_ratio <= 1.50):
                continue

            circularity = 4 * 3.141592653589793 * area / (perimeter * perimeter)
            shape_score = 0.0

            if symbol_type == "VEGETARIAN":
                # Prescribed vegetarian mark is a green filled circle
                if circularity < 0.50:
                    continue
                shape_score = min(1.0, circularity / 0.80)
            else:
                # Prescribed non-vegetarian mark is a brown filled triangle or circle
                approx = cv2.approxPolyDP(contour, 0.04 * perimeter, True)
                is_triangle = len(approx) == 3 or (len(approx) <= 5 and 0.35 <= circularity <= 0.65)
                is_circle = circularity >= 0.55
                if not (is_triangle or is_circle):
                    continue
                shape_score = 1.0 if is_triangle else min(1.0, circularity / 0.80)

            # -------------------------------------------------------------------
            # Structural Enclosing Square Outline Verification
            # The statutory mark requires an outer square of side ~1.5x - 2.5x diameter
            # -------------------------------------------------------------------
            pad_w = int(width * 1.25)
            pad_h = int(height * 1.25)
            x1 = max(0, x - pad_w)
            y1 = max(0, y - pad_h)
            x2 = min(img_w, x + width + pad_w)
            y2 = min(img_h, y + height + pad_h)

            crop_mask = mask[y1:y2, x1:x2]
            crop_gray = cv2.cvtColor(image[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)

            has_enclosing_square = False
            square_score = 0.0
            outer_bbox = [x1, y1, x2, y2]

            # Look for outer square contour in the color mask
            crop_h, crop_w = crop_mask.shape[:2]
            crop_contours, _ = cv2.findContours(crop_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            min_frame_dim = max(24, int(28 * scale))
            for cc in crop_contours:
                cx_box, cy_box, cw, ch = cv2.boundingRect(cc)
                # Outer square must not be the image crop boundary itself
                if cx_box <= 1 and cy_box <= 1 and (cw >= crop_w - 2 or ch >= crop_h - 2):
                    continue
                if cw >= crop_w * 0.95 or ch >= crop_h * 0.95:
                    continue
                if cw < min_frame_dim or ch < min_frame_dim:
                    continue

                # Outer square must be larger than inner shape but within bounding search window
                if cw > width * 1.25 and ch > height * 1.25:
                    sq_aspect = cw / max(1, ch)
                    if 0.82 <= sq_aspect <= 1.22:
                        # Outer square outline must be a hollow frame with interior spacing, not a solid block
                        density = np.count_nonzero(crop_mask[cy_box:cy_box+ch, cx_box:cx_box+cw]) / (cw * ch)
                        if not (0.10 <= density <= 0.68):
                            continue
                        cc_perim = cv2.arcLength(cc, True)
                        cc_approx = cv2.approxPolyDP(cc, 0.03 * cc_perim, True)
                        if not (4 <= len(cc_approx) <= 6):
                            continue

                        # Check concentricity: center of inner shape must align with square
                        inner_center_x = x - x1 + width / 2
                        inner_center_y = y - y1 + height / 2
                        sq_center_x = cx_box + cw / 2
                        sq_center_y = cy_box + ch / 2
                        offset_x = abs(inner_center_x - sq_center_x) / max(1, cw)
                        offset_y = abs(inner_center_y - sq_center_y) / max(1, ch)
                        if offset_x < 0.20 and offset_y < 0.20:
                            has_enclosing_square = True
                            square_score = 1.0
                            outer_bbox = [x1 + cx_box, y1 + cy_box, x1 + cx_box + cw, y1 + cy_box + ch]
                            break

            # If contour search did not find clean outer square, check edge boundary
            has_edge_boundary = False
            edge_ratio = 0.0
            if not has_enclosing_square and crop_gray.size > 0:
                edges = cv2.Canny(crop_gray, 50, 150)
                edge_ratio = float((edges > 0).mean())
                if edge_ratio > 0.07:
                    has_edge_boundary = True

            # Contrast verification: interior surrounding background must contrast with dot
            contrast_score = 0.0
            if crop_gray.size > 0:
                inner_mask = np.zeros_like(crop_gray)
                cv2.drawContours(inner_mask, [contour - np.array([x1, y1])], -1, 255, -1)
                outer_ring_mask = cv2.bitwise_not(inner_mask)
                if cv2.countNonZero(inner_mask) > 0 and cv2.countNonZero(outer_ring_mask) > 0:
                    inner_mean = cv2.mean(crop_gray, mask=inner_mask)[0]
                    ring_mean = cv2.mean(crop_gray, mask=outer_ring_mask)[0]
                    contrast_diff = abs(ring_mean - inner_mean)
                    if contrast_diff >= 25:
                        contrast_score = min(1.0, contrast_diff / 50.0)

            # Compute composite structural confidence score
            if has_enclosing_square:
                confidence = 0.52 + 0.24 * shape_score + 0.14 * contrast_score + 0.10 * (1.0 - abs(1.0 - aspect_ratio))
            elif has_edge_boundary:
                confidence = 0.38 + 0.18 * shape_score + 0.10 * contrast_score + min(edge_ratio, 0.08)
            else:
                # Isolated colored blob without enclosing frame is capped as weak
                confidence = 0.20 + 0.15 * shape_score + 0.08 * contrast_score

            confidence = min(0.95, max(0.10, confidence))

            candidates.append({
                "symbol_type": symbol_type,
                "confidence": confidence,
                "bbox": outer_bbox,
                "area": area,
                "circularity": circularity,
                "has_enclosing_square": has_enclosing_square,
                "shape_score": shape_score,
                "scale": scale,
            })

    if not candidates:
        del image, hsv, green_mask, brown_mask
        force_garbage_collection()
        return {
            "detected": False,
            "symbol_type": "UNKNOWN",
            "confidence": 0.0,
            "detection_method": "fssai_prescribed_symbol_detector",
            "status": "NOT_VERIFIABLE",
            "reason": "No prescribed food symbol detected on package images",
        }

    # Check for genuine ambiguity between competing green and brown candidates
    best_veg = next((c for c in candidates if c["symbol_type"] == "VEGETARIAN"), None)
    best_nonveg = next((c for c in candidates if c["symbol_type"] == "NON_VEGETARIAN"), None)

    # If one candidate has an enclosing square and the other does not, select the verified square
    if best_veg and best_nonveg:
        if best_veg["has_enclosing_square"] and not best_nonveg["has_enclosing_square"]:
            candidates = [c for c in candidates if c["symbol_type"] == "VEGETARIAN"]
        elif best_nonveg["has_enclosing_square"] and not best_veg["has_enclosing_square"]:
            candidates = [c for c in candidates if c["symbol_type"] == "NON_VEGETARIAN"]

    # Sort candidates by structural fidelity score
    candidates.sort(key=lambda c: c["confidence"], reverse=True)
    best = candidates[0]

    # Check for genuine ambiguity between competing green and brown candidates
    best_veg = next((c for c in candidates if c["symbol_type"] == "VEGETARIAN"), None)
    best_nonveg = next((c for c in candidates if c["symbol_type"] == "NON_VEGETARIAN"), None)

    del image, hsv, green_mask, brown_mask
    force_garbage_collection()

    # Ambiguity check: if both green and brown candidates have enclosing squares and close scores
    if best_veg and best_nonveg:
        if (best_veg["has_enclosing_square"] and best_nonveg["has_enclosing_square"] and
                abs(best_veg["confidence"] - best_nonveg["confidence"]) < 0.12):
            orig_bbox = [int(coord / scale) for coord in best["bbox"]] if scale != 1.0 else best["bbox"]
            return {
                "detected": False,
                "symbol_type": "UNKNOWN",
                "confidence": round(best["confidence"], 3),
                "bbox": orig_bbox,
                "detection_method": "fssai_prescribed_symbol_detector",
                "status": "REVIEW",
                "is_candidate": True,
                "is_ambiguous": True,
                "reason": "Ambiguous competing vegetarian and non-vegetarian symbol candidates detected.",
            }

    # Threshold for confident candidate classification
    # If confidence is below 0.50, do NOT classify as NON_VEGETARIAN or VEGETARIAN
    if best["confidence"] < 0.50:
        orig_bbox = [int(coord / scale) for coord in best["bbox"]] if scale != 1.0 else best["bbox"]
        return {
            "detected": False,
            "symbol_type": "UNKNOWN",
            "confidence": 0.0,
            "bbox": orig_bbox,
            "detection_method": "fssai_prescribed_symbol_detector",
            "status": "NOT_VERIFIABLE",
            "reason": "Visual evidence does not satisfy prescribed statutory food symbol geometry.",
        }

    orig_bbox = [int(coord / scale) for coord in best["bbox"]] if scale != 1.0 else best["bbox"]

    return {
        "detected": True,
        "symbol_type": best["symbol_type"],
        "confidence": round(best["confidence"], 3),
        "bbox": orig_bbox,
        "detection_method": "fssai_prescribed_symbol_detector",
        "status": "CANDIDATE",
        "is_candidate": True,
        "features": {
            "has_enclosing_square": best["has_enclosing_square"],
            "circularity": round(best["circularity"], 2),
            "shape_score": round(best["shape_score"], 2),
            "shape": "circle" if best["symbol_type"] == "VEGETARIAN" else "triangle",
        },
        "size_verification": "NOT_VERIFIABLE",
    }


# Backward-compatible alias for existing imports
detect_veg_nonveg_symbol = detect_food_symbol
