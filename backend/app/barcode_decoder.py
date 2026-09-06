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


def decode_barcodes(image_path: str, raw_text: str = '') -> Optional[Dict[str, Any]]:
    """Attempt to detect an EAN/UPC barcode using pyzbar when available.

    This is intentionally non-fatal: if the barcode library is not installed, the
    scan still proceeds with OCR and rule evaluation rather than crashing.
    """
    try:
        from pyzbar.pyzbar import decode
        from PIL import Image

        decoded = decode(Image.open(image_path))
        if not decoded:
            ocr_value = _barcode_from_ocr(raw_text)
            if ocr_value:
                return {"type": "EAN13", "value": ocr_value, "confidence": 0.7, "source": "OCR_BARCODE_TEXT"}
            return {"type": "NOT_DETECTED", "value": None, "confidence": 0.0}

        first = decoded[0]
        barcode = {
            "type": first.type,
            "value": first.data.decode('utf-8', errors='ignore'),
            "confidence": 1.0,
        }
        return barcode
    except Exception as exc:
        logger.warning("Barcode decoding unavailable or failed: %s", exc)
        ocr_value = _barcode_from_ocr(raw_text)
        if ocr_value:
            return {"type": "EAN13", "value": ocr_value, "confidence": 0.7, "source": "OCR_BARCODE_TEXT"}
        return {"type": "UNAVAILABLE", "value": None, "confidence": 0.0, "message": str(exc)}


def lookup_barcode(barcode_value: Optional[str]) -> Dict[str, Any]:
    """Look up a decoded product code without treating an external miss as a scan failure."""
    if not barcode_value:
        return {"status": "NOT_DETECTED", "source": "Open Food Facts"}

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
