"""PaddleOCR wrapper service with multiple-preprocessing fallbacks."""

import os
import time
import logging
from typing import List, Dict, Any, Optional

from app.ocr.preprocessing import build_ocr_variants

logger = logging.getLogger(__name__)
_ocr_instance = None


def _get_ocr():
    """Lazy-initialize PaddleOCR (downloads models on first run)."""
    global _ocr_instance
    if _ocr_instance is None:
        from paddleocr import PaddleOCR
        _ocr_instance = PaddleOCR(use_angle_cls=True, lang="en", show_log=False, use_gpu=False)
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
            if text:
                items.append({"text": text, "confidence": round(confidence, 4), "bbox": bbox})
        except (IndexError, TypeError, ValueError, KeyError):
            continue
    return items


def run_ocr(image_path: str) -> Dict[str, Any]:
    """Run one high-quality first pass and retry only when it is insufficient."""
    start_time = time.time()
    # `image_path` is already orientation-corrected, contrast enhanced and
    # sharpened by preprocess_image.  Avoid creating/reading six copies unless
    # a first pass has too little usable evidence.
    variant_paths = [image_path]

    best_payload: Dict[str, Any] = {
        "raw_text": "",
        "ocr_items": [],
        "processing_time_ms": 0,
        "total_detections": 0,
        "engine": "PaddleOCR",
        "error": None,
    }
    last_error = None

    try:
        ocr = _get_ocr()
        for path in variant_paths:
            try:
                results = ocr.ocr(path, cls=True)
            except Exception as exc:
                last_error = exc
                logger.warning(f"OCR failed on variant {path}: {exc}")
                continue

            items = _collect_ocr_items(results)
            text_parts = [item.get("text", "") for item in items if item.get("text")]
            candidate_text = _normalize_ocr_text(text_parts)
            candidate_count = len(items)
            if candidate_count > best_payload["total_detections"] or (candidate_count == best_payload["total_detections"] and len(candidate_text) > len(best_payload["raw_text"])):
                best_payload = {
                    "raw_text": candidate_text,
                    "ocr_items": items,
                    "processing_time_ms": int((time.time() - start_time) * 1000),
                    "total_detections": candidate_count,
                    "engine": "PaddleOCR",
                    "error": None,
                }

        # Retry with only two complementary renderings when the first pass is
        # genuinely weak.  The OCR instance remains process-global and is never
        # recreated per image.
        if best_payload["total_detections"] < 8 or len(best_payload["raw_text"]) < 80:
            try:
                variant_dir = os.path.join(os.path.dirname(image_path), "ocr_variants")
                retry_paths = build_ocr_variants(image_path, variant_dir, include_all=True)
                retry_paths = [p for p in retry_paths if "ocr_threshold_" in p or "ocr_gray_sharp_" in p]
                for path in retry_paths:
                    results = ocr.ocr(path, cls=True)
                    items = _collect_ocr_items(results)
                    text = _normalize_ocr_text([item.get("text", "") for item in items])
                    if len(items) > best_payload["total_detections"] or (len(items) == best_payload["total_detections"] and len(text) > len(best_payload["raw_text"])):
                        best_payload.update(raw_text=text, ocr_items=items, total_detections=len(items))
            except Exception as exc:
                logger.warning("Targeted OCR retry failed: %s", exc)

        if best_payload["total_detections"] == 0:
            raise RuntimeError(last_error or "No text detected by PaddleOCR")
    except Exception as exc:
        logger.error(f"OCR engine failed: {exc}")
        return {
            "raw_text": "",
            "ocr_items": [],
            "processing_time_ms": int((time.time() - start_time) * 1000),
            "total_detections": 0,
            "engine": "PaddleOCR",
            "error": str(exc),
        }

    best_payload["processing_time_ms"] = int((time.time() - start_time) * 1000)
    return best_payload


def get_text_with_bbox_for_field(ocr_items: List[Dict[str, Any]], search_text: str) -> Optional[Dict[str, Any]]:
    """Find the first OCR item whose text contains the given search text."""
    search_lower = search_text.lower()
    for item in ocr_items:
        if search_lower in str(item.get("text", "")).lower():
            return item
    return None
