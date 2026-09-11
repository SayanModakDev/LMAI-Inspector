"""Barcode detection wrapper that gracefully handles missing libraries."""

import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _is_valid_ean13(value: str) -> bool:
    if not re.fullmatch(r'\d{13}', value):
        return False
    checksum = sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(value[:12]))
    return (10 - checksum % 10) % 10 == int(value[-1])


def _barcode_from_ocr(raw_text: str) -> Optional[str]:
    for candidate in re.findall(r'(?<!\d)\d{13}(?!\d)', raw_text or ''):
        if _is_valid_ean13(candidate):
            return candidate
    return None


_PYZBAR_INITIALIZED = False
_PYZBAR_AVAILABLE = False
_PYZBAR_ERROR: Optional[str] = None


def is_pyzbar_available() -> bool:
    """Check whether pyzbar is installed and operable, caching the result to prevent log spam."""
    global _PYZBAR_INITIALIZED, _PYZBAR_AVAILABLE, _PYZBAR_ERROR
    if not _PYZBAR_INITIALIZED:
        try:
            from pyzbar.pyzbar import decode  # noqa: F401
            _PYZBAR_AVAILABLE = True
            _PYZBAR_ERROR = None
            logger.info("Barcode decoder initialized successfully: pyzbar is available")
        except Exception as exc:
            _PYZBAR_AVAILABLE = False
            _PYZBAR_ERROR = str(exc)
            logger.info("Barcode decoding unavailable in environment: %s. Proceeding with OCR fallback.", exc)
        _PYZBAR_INITIALIZED = True
    return _PYZBAR_AVAILABLE


def decode_barcodes(image_path: str, raw_text: str = '') -> Optional[Dict[str, Any]]:
    """Attempt to detect an EAN/UPC barcode using pyzbar when available.

    This is intentionally modular and non-fatal: if pyzbar is not installed or
    the image has no barcode, the scan proceeds with OCR and rule evaluation
    without crashing or emitting repetitive warning spam.
    """
    if not is_pyzbar_available():
        ocr_value = _barcode_from_ocr(raw_text)
        if ocr_value:
            logger.info("Barcode detected via OCR text fallback: %s", ocr_value)
            return {"type": "EAN13", "value": ocr_value, "confidence": 0.7, "source": "OCR_BARCODE_TEXT", "status": "DETECTED"}
        return {
            "type": "CAPABILITY_UNAVAILABLE",
            "value": None,
            "confidence": 0.0,
            "status": "UNAVAILABLE",
            "message": _PYZBAR_ERROR or "pyzbar is not available",
        }

    try:
        from pyzbar.pyzbar import decode
        from PIL import Image
        from app.utils.memory import force_garbage_collection

        try:
            with Image.open(image_path) as pil_img:
                w, h = pil_img.size
                if max(w, h) > 1536:
                    scale = 1536 / max(w, h)
                    pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)
                decoded = decode(pil_img)
        except Exception as img_err:
            logger.debug("Barcode decoder could not open image %s: %s", image_path, img_err)
            ocr_value = _barcode_from_ocr(raw_text)
            if ocr_value:
                return {"type": "EAN13", "value": ocr_value, "confidence": 0.7, "source": "OCR_BARCODE_TEXT", "status": "DETECTED"}
            return {"type": "INVALID_IMAGE", "value": None, "confidence": 0.0, "status": "FAILED", "message": str(img_err)}

        if not decoded:
            ocr_value = _barcode_from_ocr(raw_text)
            if ocr_value:
                logger.info("Barcode detected via OCR text fallback: %s", ocr_value)
                return {"type": "EAN13", "value": ocr_value, "confidence": 0.7, "source": "OCR_BARCODE_TEXT", "status": "DETECTED"}
            logger.debug("No barcode detected by pyzbar in %s", image_path)
            return {"type": "NOT_DETECTED", "value": None, "confidence": 0.0, "status": "NOT_DETECTED"}

        first = decoded[0]
        barcode_value = first.data.decode('utf-8', errors='ignore')
        logger.info("Barcode decode succeeded: %s (%s)", barcode_value, first.type)
        del decoded
        force_garbage_collection()
        return {
            "type": first.type,
            "value": barcode_value,
            "confidence": 1.0,
            "status": "DETECTED",
        }
    except Exception as exc:
        logger.debug("Barcode decode failed on %s: %s", image_path, exc)
        ocr_value = _barcode_from_ocr(raw_text)
        if ocr_value:
            return {"type": "EAN13", "value": ocr_value, "confidence": 0.7, "source": "OCR_BARCODE_TEXT", "status": "DETECTED"}
        return {"type": "DECODE_FAILED", "value": None, "confidence": 0.0, "status": "FAILED", "message": str(exc)}
    finally:
        from app.utils.memory import force_garbage_collection
        force_garbage_collection()


def lookup_barcode(barcode_value: Optional[str]) -> Dict[str, Any]:
    """Look up a decoded product code without treating an external miss as a scan failure."""
    if not barcode_value:
        return {"status": "NOT_DETECTED", "source": "Open Food Facts"}

    # 1. Consult Reference Product Registry first (authoritative known product dataset)
    try:
        from app.registry.product_registry import get_product_registry
        reg = get_product_registry()
        known = reg.get_by_gtin(barcode_value)
        if known:
            logger.info("Barcode %s resolved via Reference Product Registry: %s", barcode_value, known.product_name)
            return {
                "status": "FOUND",
                "source": "Reference Product Registry",
                "barcode": barcode_value,
                "product_name": known.product_name,
                "brands": known.brand,
                "generic_name": known.generic_name,
                "quantity": known.declared_net_quantity,
                "categories": known.category,
                "manufacturer": known.manufacturer_name,
                "address": known.manufacturer_address,
                "standard_mrp": known.standard_mrp,
                "is_registry_reference": True,
            }
    except Exception as reg_exc:
        logger.warning("Reference Product Registry barcode lookup error: %s", reg_exc)

    try:
        import httpx

        response = httpx.get(
            f"https://world.openfoodfacts.org/api/v2/product/{barcode_value}.json",
            headers={"User-Agent": "LMAI-Inspector/1.0"},
            timeout=8.0,
        )
        if response.status_code == 404:
            return {"status": "NOT_FOUND", "source": "Open Food Facts", "barcode": barcode_value}
        if response.status_code != 200:
            return {"status": "UNAVAILABLE", "source": "Open Food Facts", "http_status": response.status_code}
        payload = response.json()
        if payload.get("status") != 1 or not payload.get("product"):
            return {"status": "NOT_FOUND", "source": "Open Food Facts", "barcode": barcode_value}

        product = payload["product"]
        return {
            "status": "FOUND",
            "source": "Open Food Facts",
            "barcode": barcode_value,
            "product_name": product.get("product_name") or product.get("product_name_en"),
            "brands": product.get("brands"),
            "quantity": product.get("quantity"),
            "categories": product.get("categories"),
            "countries": product.get("countries"),
            "ingredients": product.get("ingredients_text") or product.get("ingredients_text_en"),
        }
    except Exception as exc:
        logger.warning("Barcode product lookup failed: %s", exc)
        return {"status": "UNAVAILABLE", "source": "Open Food Facts", "barcode": barcode_value, "message": str(exc)}
