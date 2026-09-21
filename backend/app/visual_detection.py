"""Conservative visual evidence detectors for legally relevant symbols with bounded memory footprint."""

from typing import Any, Dict, List, Tuple
import cv2
import numpy as np
from app.utils.memory import force_garbage_collection


FOOD_SYMBOL_DETECTOR_VERSION = "fssai-symbol-v3"


def _detector_metadata() -> Dict[str, Any]:
    """Return the stable detector identity and the colour-space contract."""
    return {
        "detector_version": FOOD_SYMBOL_DETECTOR_VERSION,
        "input_colour_space": "BGR",
        "threshold_colour_space": "OpenCV HSV (H=0..179)",
        "rgb_conversion": "BGR channels explicitly reordered for reported RGB statistics",
    }


def _colour_statistics(
    image_bgr: np.ndarray,
    image_hsv: np.ndarray,
    mask: np.ndarray,
) -> Dict[str, Any]:
    """Return serializable BGR/RGB/HSV statistics for independently masked pixels."""
    selected = mask > 0
    pixel_count = int(np.count_nonzero(selected))
    if pixel_count == 0:
        return {"pixel_count": 0}

    bgr_pixels = image_bgr[selected].astype(np.float32)
    hsv_pixels = image_hsv[selected].astype(np.float32)
    bgr_mean = np.mean(bgr_pixels, axis=0)
    bgr_median = np.median(bgr_pixels, axis=0)
    hsv_mean = np.mean(hsv_pixels, axis=0)
    hsv_median = np.median(hsv_pixels, axis=0)
    return {
        "pixel_count": pixel_count,
        "bgr_mean": [round(float(v), 2) for v in bgr_mean],
        "bgr_median": [round(float(v), 2) for v in bgr_median],
        "rgb_mean": [round(float(v), 2) for v in bgr_mean[::-1]],
        "rgb_median": [round(float(v), 2) for v in bgr_median[::-1]],
        "hsv_mean": [round(float(v), 2) for v in hsv_mean],
        "hsv_median": [round(float(v), 2) for v in hsv_median],
        "hsv_min": [round(float(v), 2) for v in np.min(hsv_pixels, axis=0)],
        "hsv_max": [round(float(v), 2) for v in np.max(hsv_pixels, axis=0)],
    }


def _hue_distance(first: float, second: float) -> float:
    """Circular OpenCV-HSV hue distance (0..90)."""
    direct = abs(float(first) - float(second))
    return min(direct, 180.0 - direct)


def _frame_border_mask(shape: Tuple[int, int], bbox: List[int]) -> np.ndarray:
    """Build a bounded border mask for measuring the enclosing-square colour."""
    mask = np.zeros(shape, dtype=np.uint8)
    x1, y1, x2, y2 = [int(v) for v in bbox]
    x1 = max(0, min(shape[1], x1))
    x2 = max(0, min(shape[1], x2))
    y1 = max(0, min(shape[0], y1))
    y2 = max(0, min(shape[0], y2))
    if x2 <= x1 or y2 <= y1:
        return mask
    thickness = max(2, int(round(min(x2 - x1, y2 - y1) * 0.12)))
    cv2.rectangle(mask, (x1, y1), (x2 - 1, y2 - 1), 255, thickness)
    return mask


def _scale_bbox_to_original(bbox: List[int], scale: float) -> List[int]:
    return [int(round(coord / scale)) for coord in bbox] if scale != 1.0 else [int(v) for v in bbox]


def _bbox_iou(first: List[int], second: List[int]) -> float:
    x1 = max(first[0], second[0])
    y1 = max(first[1], second[1])
    x2 = min(first[2], second[2])
    y2 = min(first[3], second[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    first_area = max(0, first[2] - first[0]) * max(0, first[3] - first[1])
    second_area = max(0, second[2] - second[0]) * max(0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def _rect_sum(integral: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> float:
    """Return a binary-mask rectangle sum from an OpenCV integral image."""
    return float(
        integral[y2, x2]
        - integral[y1, x2]
        - integral[y2, x1]
        + integral[y1, x1]
    )


def _find_fragmented_colour_frame(
    structural_mask: np.ndarray,
    x: int,
    y: int,
    width: int,
    height: int,
) -> Tuple[bool, float, List[int], Dict[str, Any]]:
    """Find a broken same-colour square around a strong inner-shape contour.

    Package glare and perspective can fragment a thin statutory square into four
    separate HSV components.  The normal contour hierarchy cannot recover that
    frame.  This bounded fallback requires colour support on *all four* sides,
    clearance around the inner shape, and a mostly uncoloured annulus.  The last
    constraint prevents filled recycling badges and decorative colour blocks
    from masquerading as a hollow statutory frame.
    """
    mask_h, mask_w = structural_mask.shape[:2]
    integral = cv2.integral((structural_mask > 0).astype(np.uint8))
    center_x = x + width / 2.0
    center_y = y + height / 2.0
    clearance = max(2, int(min(width, height) * 0.15))
    best: Tuple[float, float, float, float, List[int]] | None = None

    # A square printed on a flexible packet is commonly projected as a
    # rectangle.  Search each axis independently far enough to recover that
    # projective distortion; the four-side support and hollow-annulus checks
    # below still have to prove that the rectangle is an outline, not artwork.
    for width_scale in np.arange(1.7, 3.71, 0.2):
        frame_w = max(width + 2 * clearance, int(round(width * width_scale)))
        for height_scale in np.arange(1.7, 3.71, 0.2):
            frame_h = max(height + 2 * clearance, int(round(height * height_scale)))
            if not (0.55 <= frame_w / max(1, frame_h) <= 1.82):
                continue

            for offset_x in (-0.30, -0.15, 0.0, 0.15, 0.30):
                for offset_y in (-0.30, -0.15, 0.0, 0.15, 0.30):
                    frame_x1 = int(round(center_x + offset_x * width - frame_w / 2.0))
                    frame_y1 = int(round(center_y + offset_y * height - frame_h / 2.0))
                    frame_x2 = frame_x1 + frame_w
                    frame_y2 = frame_y1 + frame_h

                    # The candidate circle/triangle must sit wholly inside the
                    # frame with visible spacing on every side.
                    if (
                        frame_x1 > x - clearance
                        or frame_x2 < x + width + clearance
                        or frame_y1 > y - clearance
                        or frame_y2 < y + height + clearance
                        or frame_x1 < 0
                        or frame_y1 < 0
                        or frame_x2 > mask_w
                        or frame_y2 > mask_h
                    ):
                        continue

                    thickness = max(2, int(round(min(frame_w, frame_h) * 0.10)))
                    inset = thickness
                    side_boxes = (
                        (frame_x1 + inset, frame_y1, frame_x2 - inset, frame_y1 + thickness),
                        (frame_x1 + inset, frame_y2 - thickness, frame_x2 - inset, frame_y2),
                        (frame_x1, frame_y1 + inset, frame_x1 + thickness, frame_y2 - inset),
                        (frame_x2 - thickness, frame_y1 + inset, frame_x2, frame_y2 - inset),
                    )
                    side_support: List[float] = []
                    for sx1, sy1, sx2, sy2 in side_boxes:
                        side_area = max(1, (sx2 - sx1) * (sy2 - sy1))
                        side_support.append(_rect_sum(integral, sx1, sy1, sx2, sy2) / side_area)

                    annulus_x1 = frame_x1 + thickness
                    annulus_y1 = frame_y1 + thickness
                    annulus_x2 = frame_x2 - thickness
                    annulus_y2 = frame_y2 - thickness
                    annulus_area = max(1, (annulus_x2 - annulus_x1) * (annulus_y2 - annulus_y1))
                    annulus_sum = _rect_sum(
                        integral, annulus_x1, annulus_y1, annulus_x2, annulus_y2
                    )
                    inner_x1 = max(annulus_x1, x - 1)
                    inner_y1 = max(annulus_y1, y - 1)
                    inner_x2 = min(annulus_x2, x + width + 1)
                    inner_y2 = min(annulus_y2, y + height + 1)
                    if inner_x2 > inner_x1 and inner_y2 > inner_y1:
                        annulus_sum -= _rect_sum(
                            integral, inner_x1, inner_y1, inner_x2, inner_y2
                        )
                    annulus_density = annulus_sum / annulus_area

                    average_support = float(np.mean(side_support))
                    minimum_support = float(min(side_support))
                    score = average_support - 0.60 * annulus_density
                    candidate = (
                        score,
                        average_support,
                        minimum_support,
                        annulus_density,
                        [frame_x1, frame_y1, frame_x2, frame_y2],
                    )
                    if best is None or candidate[0] > best[0]:
                        best = candidate

    if best is None:
        return False, 0.0, [x, y, x + width, y + height], {}

    score, average_support, minimum_support, annulus_density, bbox = best
    accepted = bool(
        average_support >= 0.55
        and minimum_support >= 0.30
        and annulus_density <= 0.17
        and score >= 0.45
    )
    metrics = {
        "average_side_support": round(average_support, 3),
        "minimum_side_support": round(minimum_support, 3),
        "interior_annulus_density": round(annulus_density, 3),
        "frame_score": round(score, 3),
    }
    return accepted, max(0.0, min(1.0, score)), bbox, metrics


def detect_food_symbol(image_input: Any) -> Dict[str, Any]:
    """Detect candidate prescribed food-symbol geometry (FSSAI Regulations).

    Statutory Requirements:
    - Vegetarian: Green filled circle inside a green square outline with contrasting background.
    - Non-Vegetarian: Brown filled triangle inside a brown square outline with contrasting background.

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
                "candidates": [],
                **_detector_metadata(),
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
            "candidates": [],
            **_detector_metadata(),
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
    # Printed statutory green can shift toward dark cyan under phone white
    # balance (the real regression mark is H=87..89 with G only ~1.09x B).
    # Geometry and same-colour frame checks remain mandatory, so broadening the
    # candidate colour range cannot independently verify teal artwork.
    green_hsv = cv2.inRange(hsv, (35, 40, 30), (100, 255, 255))
    green_rgb = (
        (g_ch > (r_ch.astype(np.float32) * 1.08))
        & (g_ch > (b_ch.astype(np.float32) * 1.02))
        & (g_ch > 35)
    )
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
    # Structural masks intentionally retain HSV-consistent frame pixels that
    # glare can make fail strict RGB-channel dominance.  They are never used to
    # generate an inner-shape candidate; only to verify a local four-sided frame.
    structural_masks = {
        # A low-saturation cyan cast is common on the white packet background
        # in phone photos.  It is useful for candidate discovery but would fill
        # the supposedly hollow square annulus.  Require stronger saturation
        # for the independent frame proof (the exact printed frame remains
        # supported at S>=100).
        "VEGETARIAN": cv2.inRange(hsv, (35, 100, 30), (100, 255, 255)),
        "NON_VEGETARIAN": brown_hsv,
    }
    moderate_structural_masks = {
        # Older captures have a lower-saturation printed green frame.  This
        # second mask is consulted only if the strict frame proof fails; all
        # four sides, hollowness, geometry, hue, and contrast remain required.
        "VEGETARIAN": cv2.inRange(hsv, (35, 50, 30), (100, 255, 255)),
        "NON_VEGETARIAN": brown_hsv,
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
            if not (0.50 <= aspect_ratio <= 2.00):
                continue

            circularity = 4 * 3.141592653589793 * area / (perimeter * perimeter)
            hull_area = cv2.contourArea(cv2.convexHull(contour))
            solidity = area / hull_area if hull_area > 0 else 0.0
            extent = area / max(1, width * height)
            shape_score = 0.0
            approx = cv2.approxPolyDP(contour, 0.04 * perimeter, True)
            polygon_vertices = len(approx)
            shape_name = "unknown"

            if symbol_type == "VEGETARIAN":
                # Prescribed vegetarian mark is a green filled circle
                shape_score = min(1.0, circularity / 0.80)
                # A photographed circle becomes an ellipse under perspective.
                # Require a compact convex fill rather than lowering geometry
                # support based on circularity alone.
                circle_supported = bool(
                    circularity >= 0.42
                    and solidity >= 0.75
                    and extent >= 0.42
                )
                shape_name = "circle" if circle_supported else "irregular"
            else:
                # The current prescribed non-vegetarian mark is a brown filled
                # triangle.  A circular promotional badge is not a permissive
                # fallback: if perspective/glare prevents triangle support the
                # evidence remains review-required rather than becoming non-veg.
                is_triangle = polygon_vertices == 3
                shape_score = 1.0 if is_triangle else min(1.0, circularity / 0.80)
                shape_name = "triangle" if is_triangle else (
                    "circle" if circularity >= 0.55 else "irregular"
                )

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
            frame_detection = "none"
            frame_metrics: Dict[str, Any] = {}
            frame_structural_mask = structural_masks[symbol_type]

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
                    # A photographed square on a crumpled package may be
                    # projectively rectangular.  Concentricity, hollowness,
                    # matching hue, containment, and contrast remain mandatory.
                    if 0.55 <= sq_aspect <= 1.82:
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
                            frame_detection = "connected_same_colour_contour"
                            break

            # Thin frames broken by glare/perspective have no single enclosing
            # contour.  Verify four local HSV sides and a hollow interior rather
            # than weakening the global geometry requirement.
            if not has_enclosing_square:
                (
                    has_fragmented_frame,
                    fragmented_score,
                    fragmented_bbox,
                    fragmented_metrics,
                ) = _find_fragmented_colour_frame(
                    frame_structural_mask, x, y, width, height
                )
                frame_metrics = fragmented_metrics
                if has_fragmented_frame:
                    has_enclosing_square = True
                    square_score = fragmented_score
                    outer_bbox = fragmented_bbox
                    frame_detection = "fragmented_same_colour_frame"

            if not has_enclosing_square and symbol_type == "VEGETARIAN":
                moderate_mask = moderate_structural_masks[symbol_type]
                (
                    has_fragmented_frame,
                    fragmented_score,
                    fragmented_bbox,
                    fragmented_metrics,
                ) = _find_fragmented_colour_frame(
                    moderate_mask, x, y, width, height
                )
                if has_fragmented_frame:
                    has_enclosing_square = True
                    square_score = fragmented_score
                    outer_bbox = fragmented_bbox
                    frame_metrics = fragmented_metrics
                    frame_metrics["saturation_profile"] = "moderate"
                    frame_structural_mask = moderate_mask
                    frame_detection = "fragmented_same_colour_frame"

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

            # Independently measure inner-shape and enclosing-frame colour.
            # The class masks establish the expected range, while these
            # statistics prove that the two printed components actually match.
            inner_full_mask = np.zeros((img_h, img_w), dtype=np.uint8)
            cv2.drawContours(inner_full_mask, [contour], -1, 255, -1)
            inner_colour = _colour_statistics(image, hsv, inner_full_mask)
            frame_border = _frame_border_mask((img_h, img_w), outer_bbox)
            frame_colour_mask = cv2.bitwise_and(
                frame_border, frame_structural_mask
            )
            frame_colour_mask = cv2.bitwise_and(
                frame_colour_mask, cv2.bitwise_not(inner_full_mask)
            )
            outer_colour = _colour_statistics(image, hsv, frame_colour_mask)
            inner_hue = (inner_colour.get("hsv_median") or [None])[0]
            outer_hue = (outer_colour.get("hsv_median") or [None])[0]
            hue_delta = (
                _hue_distance(inner_hue, outer_hue)
                if inner_hue is not None and outer_hue is not None
                else None
            )
            inner_colour_supported = inner_colour.get("pixel_count", 0) >= max(12, int(area * 0.35))
            outer_colour_supported = outer_colour.get("pixel_count", 0) >= 8
            matching_enclosing_colour = bool(
                has_enclosing_square
                and inner_colour_supported
                and outer_colour_supported
                and hue_delta is not None
                and hue_delta <= 18.0
            )

            ox1, oy1, ox2, oy2 = outer_bbox
            inner_center_x = x + width / 2.0
            inner_center_y = y + height / 2.0
            outer_width = max(1, ox2 - ox1)
            outer_height = max(1, oy2 - oy1)
            spatial_containment = bool(
                ox1 <= x and oy1 <= y and ox2 >= x + width and oy2 >= y + height
            )
            geometry = {
                "inner_width": int(width),
                "inner_height": int(height),
                "inner_aspect_ratio": round(float(aspect_ratio), 4),
                "outer_width": int(outer_width),
                "outer_height": int(outer_height),
                "outer_aspect_ratio": round(float(outer_width / outer_height), 4),
                "outer_to_inner_width_ratio": round(float(outer_width / max(1, width)), 4),
                "outer_to_inner_height_ratio": round(float(outer_height / max(1, height)), 4),
                "center_offset_x_ratio": round(
                    abs(inner_center_x - (ox1 + outer_width / 2.0)) / outer_width, 4
                ),
                "center_offset_y_ratio": round(
                    abs(inner_center_y - (oy1 + outer_height / 2.0)) / outer_height, 4
                ),
                "spatial_containment": spatial_containment,
            }

            # Compute composite structural confidence score
            if has_enclosing_square:
                confidence = 0.52 + 0.24 * shape_score + 0.14 * contrast_score + 0.10 * (1.0 - abs(1.0 - aspect_ratio))
            elif has_edge_boundary:
                confidence = 0.38 + 0.18 * shape_score + 0.10 * contrast_score + min(edge_ratio, 0.08)
            else:
                # Isolated colored blob without enclosing frame is capped as weak
                confidence = 0.20 + 0.15 * shape_score + 0.08 * contrast_score

            confidence = min(0.95, max(0.10, confidence))

            # A generic edge-rich crop is useful diagnostic evidence, but it is
            # not the prescribed same-colour enclosing square.  Never allow it
            # to cross the classification threshold by itself.
            acceptance_checks = {
                "appropriate_inner_geometry": (
                    (symbol_type == "VEGETARIAN" and shape_name == "circle")
                    or (symbol_type == "NON_VEGETARIAN" and shape_name == "triangle")
                ),
                "appropriate_inner_colour": inner_colour_supported,
                "same_colour_enclosing_square": matching_enclosing_colour,
                "inner_outer_spatial_containment": spatial_containment,
                "foreground_background_contrast": contrast_score >= 0.35,
            }
            accepted = all(acceptance_checks.values())
            acceptance_reasons: List[str] = []
            rejection_reasons: List[str] = []
            if accepted:
                decision_reason = (
                    "Accepted: filled prescribed inner shape inside a concentric same-colour square "
                    f"({frame_detection})."
                )
                acceptance_reasons = [
                    "Prescribed inner-shape geometry independently supported.",
                    "Inner-shape colour independently supported in BGR/HSV.",
                    "Enclosing square has matching measured hue.",
                    "Inner shape is spatially contained by the square.",
                    "Foreground/background contrast is sufficient.",
                ]
            else:
                if not acceptance_checks["appropriate_inner_geometry"]:
                    rejection_reasons.append(
                        f"Inner geometry is {shape_name}, not the prescribed "
                        f"{'circle' if symbol_type == 'VEGETARIAN' else 'triangle'}."
                    )
                if not has_enclosing_square:
                    rejection_reasons.append(
                        "No concentric same-colour enclosing square; decorative coloured shape only."
                    )
                elif not matching_enclosing_colour:
                    rejection_reasons.append(
                        "Enclosing-square colour does not independently match the inner shape."
                    )
                if not spatial_containment:
                    rejection_reasons.append("Inner shape is not spatially contained by the enclosing square.")
                if contrast_score < 0.35:
                    rejection_reasons.append(
                        "Prescribed geometry lacks sufficient foreground/background contrast."
                    )
                decision_reason = "Rejected: " + " ".join(rejection_reasons)

            candidates.append({
                "candidate_type": "PRESCRIBED_FOOD_SYMBOL",
                "symbol_type": symbol_type,
                "confidence": confidence,
                "bbox": outer_bbox,
                "inner_bbox": [x, y, x + width, y + height],
                "area": area,
                "perimeter": perimeter,
                "circularity": circularity,
                "solidity": solidity,
                "extent": extent,
                "polygon_vertices": polygon_vertices,
                "shape": shape_name,
                "has_enclosing_square": has_enclosing_square,
                "frame_detection": frame_detection,
                "frame_metrics": frame_metrics,
                "geometry": geometry,
                "inner_colour": inner_colour,
                "outer_square_colour": outer_colour,
                "hsv_hue_distance": round(float(hue_delta), 3) if hue_delta is not None else None,
                "acceptance_checks": acceptance_checks,
                "contrast_score": contrast_score,
                "edge_ratio": edge_ratio,
                "shape_score": shape_score,
                "scale": scale,
                "original_image_dimensions": {"width": orig_w, "height": orig_h},
                "accepted": accepted,
                "lifecycle_state": "CANDIDATE" if accepted else "REJECTED",
                "acceptance_reasons": acceptance_reasons,
                "rejection_reasons": rejection_reasons,
                "decision_reason": decision_reason,
                **_detector_metadata(),
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
            "candidates": [],
            **_detector_metadata(),
        }

    # Sort candidates by structural fidelity score and reject duplicate contours
    # around the same physical mark without losing the audit record.
    candidates.sort(key=lambda c: c["confidence"], reverse=True)
    supported: List[Dict[str, Any]] = []
    for candidate in candidates:
        if not candidate["accepted"]:
            continue
        duplicate = next(
            (
                existing for existing in supported
                if existing["symbol_type"] == candidate["symbol_type"]
                and _bbox_iou(existing["bbox"], candidate["bbox"]) >= 0.70
            ),
            None,
        )
        if duplicate:
            candidate["accepted"] = False
            candidate["lifecycle_state"] = "REJECTED"
            candidate["rejection_reasons"] = [
                "Duplicate contour suppressed for the same physical symbol."
            ]
            candidate["decision_reason"] = "Rejected: duplicate contour for the same physical symbol."
        else:
            candidate["lifecycle_state"] = "VERIFIED"
            supported.append(candidate)

    candidate_audit = []
    for candidate in candidates:
        audit = dict(candidate)
        audit["bbox"] = _scale_bbox_to_original(candidate["bbox"], scale)
        audit["inner_bbox"] = _scale_bbox_to_original(candidate["inner_bbox"], scale)
        audit.pop("scale", None)
        audit["confidence"] = round(float(audit["confidence"]), 3)
        candidate_audit.append(audit)

    del image, hsv, green_mask, brown_mask
    force_garbage_collection()

    supported_types = {candidate["symbol_type"] for candidate in supported}
    if len(supported_types) > 1:
        best = max(supported, key=lambda item: item["confidence"])
        return {
            "detected": False,
            "symbol_type": "UNKNOWN",
            "confidence": round(best["confidence"], 3),
            "bbox": _scale_bbox_to_original(best["bbox"], scale),
            "detection_method": "fssai_prescribed_symbol_detector",
            "status": "REVIEW",
            "is_candidate": True,
            "is_ambiguous": True,
            "has_conflict": True,
            "reason": "Genuinely supported vegetarian and non-vegetarian symbols detected in the same image.",
            "candidates": candidate_audit,
            **_detector_metadata(),
        }

    if not supported:
        best = candidates[0]
        return {
            "detected": False,
            "symbol_type": "UNKNOWN",
            "confidence": round(best["confidence"], 3),
            "bbox": _scale_bbox_to_original(best["bbox"], scale),
            "detection_method": "fssai_prescribed_symbol_detector",
            "status": "NOT_VERIFIABLE",
            "reason": "Visual evidence does not satisfy prescribed statutory food symbol geometry.",
            "candidates": candidate_audit,
            **_detector_metadata(),
        }

    best = max(supported, key=lambda item: item["confidence"])
    orig_bbox = _scale_bbox_to_original(best["bbox"], scale)

    return {
        "detected": True,
        "symbol_type": best["symbol_type"],
        "confidence": round(best["confidence"], 3),
        "bbox": orig_bbox,
        "detection_method": "fssai_prescribed_symbol_detector",
        "status": "VERIFIED",
        "candidate_status": "CONFIRMED",
        "is_candidate": False,
        "visual_confirmation": {
            "confirmed": True,
            "checks": {
                "prescribed_inner_shape": True,
                "prescribed_inner_colour": True,
                "same_colour_enclosing_square": True,
                "inner_outer_spatial_containment": True,
                "foreground_background_contrast": True,
            },
            "missing_requirements": [],
        },
        "features": {
            "has_enclosing_square": best["has_enclosing_square"],
            "circularity": round(best["circularity"], 2),
            "shape_score": round(best["shape_score"], 2),
            "shape": best["shape"],
        },
        "size_verification": "NOT_VERIFIABLE",
        "candidates": candidate_audit,
        **_detector_metadata(),
    }


def aggregate_food_symbol_evidence(panel_results: List[Tuple[Dict[str, Any], int]]) -> Dict[str, Any]:
    """Merge traceable per-panel symbol results without promoting weak candidates.

    Equivalent supported marks across panels corroborate one classification.  A
    conflict is emitted only when both classes retain prescribed geometry.
    """
    supported: List[Dict[str, Any]] = []
    audit: List[Dict[str, Any]] = []
    ambiguous_results: List[Tuple[Dict[str, Any], int]] = []

    for result, image_index in panel_results:
        panel_candidates = result.get("candidates") or []
        for raw_candidate in panel_candidates:
            candidate = dict(raw_candidate)
            candidate["image_index"] = image_index
            candidate["source_image_index"] = image_index
            audit.append(candidate)
            if (
                candidate.get("accepted")
                and candidate.get("lifecycle_state") == "VERIFIED"
                and candidate.get("symbol_type") in ("VEGETARIAN", "NON_VEGETARIAN")
            ):
                supported.append(candidate)

        # Backward-compatible support for detector results without an audit list.
        if (
            not panel_candidates
            and result.get("status") in ("CANDIDATE", "VERIFIED", "CONFIRMED")
            and result.get("detected")
        ):
            candidate = {
                "image_index": image_index,
                "source_image_index": image_index,
                "bbox": result.get("bbox"),
                "symbol_type": result.get("symbol_type"),
                "confidence": float(result.get("confidence") or 0),
                "accepted": True,
                "lifecycle_state": "VERIFIED",
                "decision_reason": "Accepted by prescribed-symbol detector.",
            }
            supported.append(candidate)
            audit.append(candidate)
        if result.get("status") == "REVIEW" or result.get("is_ambiguous"):
            ambiguous_results.append((result, image_index))

    distinct_types = {candidate["symbol_type"] for candidate in supported}
    aggregation_trace = {
        "panel_count": len(panel_results),
        "candidate_count": len(audit),
        "verified_candidate_count": len(supported),
        "rejected_candidate_count": sum(
            1 for candidate in audit if candidate.get("lifecycle_state") == "REJECTED"
        ),
        "duplicate_suppressed_count": sum(
            1
            for candidate in audit
            if "duplicate contour" in str(candidate.get("decision_reason") or "").lower()
        ),
        "supported_symbol_types": sorted(distinct_types),
    }
    if len(distinct_types) > 1:
        best = max(supported, key=lambda item: float(item.get("confidence") or 0))
        return {
            "detected": False,
            "value": "CONFLICTING_SYMBOLS",
            "symbol_type": "UNKNOWN",
            "confidence": round(float(best.get("confidence") or 0), 3),
            "bbox": best.get("bbox"),
            "source_image_index": best.get("image_index"),
            "evidence_crop_file": best.get("evidence_crop_file"),
            "evidence_crop_url": best.get("evidence_crop_url"),
            "evidence_crop_sha256": best.get("evidence_crop_sha256"),
            "status": "CONFLICTING_EVIDENCE",
            "has_conflict": True,
            "is_candidate": True,
            "reason": "Supported vegetarian and non-vegetarian statutory symbols remain across package views.",
            "candidates": audit,
            "competing_candidates": supported,
            "detection_method": "fssai_prescribed_symbol_detector",
            "aggregation_trace": aggregation_trace,
            **_detector_metadata(),
        }

    if supported:
        best = max(supported, key=lambda item: float(item.get("confidence") or 0))
        return {
            "detected": True,
            "value": best["symbol_type"],
            "symbol_type": best["symbol_type"],
            "confidence": round(float(best.get("confidence") or 0), 3),
            "bbox": best.get("bbox"),
            "source_image_index": best.get("image_index"),
            "evidence_crop_file": best.get("evidence_crop_file"),
            "evidence_crop_url": best.get("evidence_crop_url"),
            "evidence_crop_sha256": best.get("evidence_crop_sha256"),
            "status": "VERIFIED",
            "candidate_status": "CONFIRMED",
            "is_candidate": False,
            "has_conflict": False,
            "visual_confirmation": {
                "confirmed": True,
                "checks": {
                    "prescribed_inner_shape": True,
                    "prescribed_inner_colour": True,
                    "same_colour_enclosing_square": True,
                    "inner_outer_spatial_containment": True,
                    "foreground_background_contrast": True,
                    "no_supported_opposite_symbol": True,
                    "image_and_bbox_provenance": bool(
                        best.get("image_index") is not None and best.get("bbox")
                    ),
                },
                "missing_requirements": [],
            },
            "supporting_candidates": supported,
            "candidates": audit,
            "detection_method": "fssai_prescribed_symbol_detector",
            "aggregation_trace": aggregation_trace,
            **_detector_metadata(),
        }

    if ambiguous_results:
        result, image_index = max(ambiguous_results, key=lambda item: float(item[0].get("confidence") or 0))
        return {
            "detected": False,
            "value": "AMBIGUOUS",
            "symbol_type": "UNKNOWN",
            "confidence": float(result.get("confidence") or 0),
            "bbox": result.get("bbox"),
            "source_image_index": image_index,
            "evidence_crop_file": result.get("evidence_crop_file"),
            "evidence_crop_url": result.get("evidence_crop_url"),
            "evidence_crop_sha256": result.get("evidence_crop_sha256"),
            "status": "REVIEW",
            "is_candidate": True,
            "is_ambiguous": True,
            "reason": result.get("reason") or "Visual evidence remains ambiguous.",
            "candidates": audit,
            "detection_method": "fssai_prescribed_symbol_detector",
            "aggregation_trace": aggregation_trace,
            **_detector_metadata(),
        }

    best_rejected = max(audit, key=lambda item: float(item.get("confidence") or 0)) if audit else None
    rejection_reason = (
        f"No supported prescribed food symbol detected on package images. "
        f"Best visual candidate on image {best_rejected.get('image_index')} was rejected: "
        f"{best_rejected.get('decision_reason')}"
        if best_rejected
        else "No prescribed food-symbol candidate was generated from the package images."
    )
    return {
        "detected": False,
        "value": None,
        "symbol_type": "UNKNOWN",
        "confidence": round(float((best_rejected or {}).get("confidence") or 0), 3),
        "bbox": (best_rejected or {}).get("bbox"),
        "source_image_index": (best_rejected or {}).get("image_index"),
        "evidence_crop_file": (best_rejected or {}).get("evidence_crop_file"),
        "evidence_crop_url": (best_rejected or {}).get("evidence_crop_url"),
        "evidence_crop_sha256": (best_rejected or {}).get("evidence_crop_sha256"),
        "status": "NOT_VERIFIABLE",
        "reason": rejection_reason,
        "candidates": audit,
        "detection_method": "fssai_prescribed_symbol_detector",
        "aggregation_trace": aggregation_trace,
        **_detector_metadata(),
    }


# Backward-compatible alias for existing imports
detect_veg_nonveg_symbol = detect_food_symbol
