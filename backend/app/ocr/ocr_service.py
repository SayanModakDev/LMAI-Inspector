"""PaddleOCR wrapper service with multi-variant fallback, structured states, and robust memory bounds."""

import os
import sys
import time
import logging
from typing import List, Dict, Any, Optional

# Memory optimization flags for PaddlePaddle C++ backend before library import
os.environ.setdefault("FLAGS_allocator_strategy", "naive_best_fit")
os.environ.setdefault("FLAGS_fraction_of_cpu_memory_to_use", "0.1")
os.environ.setdefault("FLAGS_eager_delete_tensor_gb", "0.0")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

from app.ocr.preprocessing import generate_single_variant, validate_image_file
from app.utils.memory import force_garbage_collection, log_memory_checkpoint

logger = logging.getLogger(__name__)
_ocr_instance = None


def _get_ocr():
    """Lazy-initialize a single process-level PaddleOCR instance with bounded thread pools."""
    global _ocr_instance
    if _ocr_instance is None:
        from paddleocr import PaddleOCR
        threads = int(os.getenv("PADDLE_CPU_THREADS", "1"))
        _ocr_instance = PaddleOCR(
            use_angle_cls=False,
            lang="en",
            show_log=False,
            use_gpu=False,
            cpu_threads=threads,
            enable_mkldnn=False,
            rec_batch_num=1,
            max_batch_size=1,
            det_limit_side_len=960,
        )
        logger.info(
            "PaddleOCR engine initialized successfully (lang=en, angle_cls=False, cpu_threads=%d, mkldnn=False, rec_batch=1)",
            threads,
        )
    return _ocr_instance


def _normalize_ocr_text(text_parts: List[str]) -> str:
    cleaned = []
    for item in text_parts:
        value = str(item or '').strip()
        if value:
            cleaned.append(value)
    return "\n".join(cleaned).strip()


def _collect_ocr_items(results: Any) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not results or not results[0]:
        return items
    for detection in results[0]:
        try:
            polygon = detection[0]
            text_info = detection[1]
            text = text_info[0] if isinstance(text_info, (list, tuple)) and text_info else ""
            confidence = float(text_info[1]) if isinstance(text_info, (list, tuple)) and len(text_info) > 1 else 0.0
            xs = [pt[0] for pt in polygon]
            ys = [pt[1] for pt in polygon]
            bbox = [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]
            if text and text.strip():
                items.append({
                    "text": text.strip(),
                    "confidence": round(confidence, 4),
                    "bbox": bbox
                })
        except (IndexError, TypeError, ValueError, KeyError):
            continue
    return items


def _bbox_iou(box1: List[int], box2: List[int]) -> float:
    """Calculate Intersection over Union (IoU) between two bounding boxes [x1, y1, x2, y2]."""
    xA = max(box1[0], box2[0])
    yA = max(box1[1], box2[1])
    xB = min(box1[2], box2[2])
    yB = min(box1[3], box2[3])
    inter_area = max(0, xB - xA) * max(0, yB - yA)
    if inter_area == 0:
        return 0.0
    area1 = max(0, box1[2] - box1[0]) * max(0, box1[3] - box1[1])
    area2 = max(0, box2[2] - box2[0]) * max(0, box2[3] - box2[1])
    union_area = area1 + area2 - inter_area
    return inter_area / union_area if union_area > 0 else 0.0


def _deduplicate_ocr_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate overlapping OCR detections, keeping the higher-confidence candidate."""
    unique: List[Dict[str, Any]] = []
    for item in items:
        text = item.get("text", "").strip().lower()
        bbox = item.get("bbox", [0, 0, 0, 0])
        conf = item.get("confidence", 0.0)
        duplicate_index = -1
        for idx, existing in enumerate(unique):
            existing_text = existing.get("text", "").strip().lower()
            existing_bbox = existing.get("bbox", [0, 0, 0, 0])
            iou = _bbox_iou(bbox, existing_bbox)
            if (text == existing_text and iou > 0.25) or iou > 0.75:
                duplicate_index = idx
                break

        if duplicate_index >= 0:
            if conf > unique[duplicate_index].get("confidence", 0.0):
                unique[duplicate_index] = dict(item)
        else:
            unique.append(dict(item))
    return unique


def run_ocr(image_path: str) -> Dict[str, Any]:
    """Execute OCR across sensible preprocessing variants with structured states and resilience.

    Distinguishes:
      - 'SUCCESS_WITH_TEXT': Valid image with 1 or more text detections.
      - 'NO_TEXT_DETECTED': Valid image where OCR ran cleanly but detected no text.
      - 'OCR_ENGINE_ERROR': Hardware, memory, or internal engine failure.
      - 'INVALID_IMAGE': Missing, empty, or unreadable image file.
    """
    start_time = time.time()
    base_img_name = os.path.basename(image_path)

    # 1. Validate input image
    if not validate_image_file(image_path):
        logger.info("OCR received invalid or unreadable image: %s", image_path)
        return {
            "ocr_status": "INVALID_IMAGE",
            "raw_text": "",
            "ocr_items": [],
            "processing_time_ms": int((time.time() - start_time) * 1000),
            "total_detections": 0,
            "detection_count": 0,
            "attempt_count": 0,
            "successful_attempt_count": 0,
            "source_image": image_path,
            "preprocessing_variant": "none",
            "engine": "PaddleOCR",
            "error": "Invalid or unreadable image file",
            "engine_error": None,
        }

    attempt_count = 0
    successful_attempt_count = 0
    last_engine_error: Optional[Exception] = None
    candidates: List[Dict[str, Any]] = []

    # Diagnostic RSS log before OCR
    log_memory_checkpoint("RSS before OCR", f"file={base_img_name}")

    # Attempt 1: Primary Normalized Image
    attempt_count += 1
    logger.info("OCR attempt started for %s (variant=original)", image_path)
    try:
        ocr = _get_ocr()
        results = ocr.ocr(image_path, cls=False)
        items = _collect_ocr_items(results)
        successful_attempt_count += 1
        if items:
            logger.info("OCR attempt succeeded for %s (variant=original, detections=%d)", image_path, len(items))
        else:
            logger.info("OCR returned zero detections for %s (variant=original)", image_path)

        text_parts = [it["text"] for it in items if it.get("text")]
        raw_text = _normalize_ocr_text(text_parts)
        candidates.append({
            "variant": "original",
            "items": items,
            "text": raw_text,
            "count": len(items),
        })
    except Exception as exc:
        last_engine_error = exc
        logger.error("OCR engine exception on %s (variant=original): %s", image_path, exc)
    finally:
        force_garbage_collection()

    # Targeted retry: Only generate fallback variant if primary pass yielded zero text
    primary_count = candidates[0]["count"] if candidates else 0
    if primary_count == 0:
        variant_dir = os.path.join(os.path.dirname(image_path), "ocr_variants")
        for v_name in ["contrast"]:
            attempt_count += 1
            logger.info("OCR retry attempt started for %s (variant=%s)", image_path, v_name)
            v_path = None
            try:
                # Generate single variant on demand; releases NumPy arrays immediately
                v_path = generate_single_variant(image_path, v_name, variant_dir)
                ocr = _get_ocr()
                v_results = ocr.ocr(v_path, cls=False)
                v_items = _collect_ocr_items(v_results)
                successful_attempt_count += 1
                if v_items:
                    logger.info("OCR retry succeeded for %s (variant=%s, detections=%d)", image_path, v_name, len(v_items))
                else:
                    logger.info("OCR retry returned zero detections for %s (variant=%s)", image_path, v_name)

                v_text = _normalize_ocr_text([it["text"] for it in v_items if it.get("text")])
                candidates.append({
                    "variant": v_name,
                    "items": v_items,
                    "text": v_text,
                    "count": len(v_items),
                })
            except Exception as v_exc:
                last_engine_error = v_exc
                logger.error("OCR engine exception on %s (variant=%s): %s", image_path, v_name, v_exc)
            finally:
                # Clean up temporary variant file from disk immediately to conserve resources
                if v_path and os.path.exists(v_path):
                    try:
                        os.remove(v_path)
                    except Exception:
                        pass
                force_garbage_collection()

            # Early exit if the contrast pass yielded sufficient detections
            if candidates and candidates[-1]["count"] >= 10:
                break

    # Select the best performing variant or aggregate unique detections
    best_candidate = max(candidates, key=lambda c: (c["count"], len(c["text"]))) if candidates else None

    all_items: List[Dict[str, Any]] = []
    if candidates:
        for cand in candidates:
            all_items.extend(cand["items"])
    deduped_items = _deduplicate_ocr_items(all_items) if all_items else []

    # If deduplication collected richer text, use deduped items, otherwise fallback to best candidate
    if len(deduped_items) >= (best_candidate["count"] if best_candidate else 0):
        final_items = deduped_items
        final_text = _normalize_ocr_text([it["text"] for it in final_items if it.get("text")])
        final_variant = best_candidate["variant"] if best_candidate else "original"
    else:
        final_items = best_candidate["items"] if best_candidate else []
        final_text = best_candidate["text"] if best_candidate else ""
        final_variant = best_candidate["variant"] if best_candidate else "original"

    elapsed_ms = int((time.time() - start_time) * 1000)
    detection_count = len(final_items)

    # Determine status
    if detection_count > 0:
        ocr_status = "SUCCESS_WITH_TEXT"
        error_msg = None
    elif successful_attempt_count > 0:
        ocr_status = "NO_TEXT_DETECTED"
        error_msg = None
        logger.info("OCR returned zero detections across %d attempt(s) for %s", attempt_count, image_path)
    else:
        ocr_status = "OCR_ENGINE_ERROR"
        error_msg = str(last_engine_error) if last_engine_error else "OCR engine failed"
        logger.error("OCR engine error across all attempts on %s: %s", image_path, error_msg)

    # Diagnostic RSS log after OCR
    log_memory_checkpoint("RSS after OCR", f"file={base_img_name}, detections={detection_count}")
    force_garbage_collection()

    return {
        "ocr_status": ocr_status,
        "raw_text": final_text,
        "ocr_items": final_items,
        "processing_time_ms": elapsed_ms,
        "total_detections": detection_count,
        "detection_count": detection_count,
        "attempt_count": attempt_count,
        "successful_attempt_count": successful_attempt_count,
        "source_image": image_path,
        "preprocessing_variant": final_variant,
        "engine": "PaddleOCR",
        "error": error_msg,
        "engine_error": str(last_engine_error) if ocr_status == "OCR_ENGINE_ERROR" else None,
    }


def get_text_with_bbox_for_field(ocr_items: List[Dict[str, Any]], search_text: str) -> Optional[Dict[str, Any]]:
    """Find the first OCR item whose text contains the given search text."""
    search_lower = search_text.lower()
    for item in ocr_items:
        if search_lower in str(item.get("text", "")).lower():
            return item
    return None
