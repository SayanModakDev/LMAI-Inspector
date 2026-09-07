"""Comprehensive test suite for OCR and barcode decoder robustness, resilience, and error handling."""

import os
import io
import pytest
from PIL import Image, ImageDraw
from typing import Dict, Any

from app.barcode_decoder import decode_barcodes, is_pyzbar_available
from app.ocr.ocr_service import run_ocr
from app.ocr.preprocessing import validate_image_file, preprocess_image


@pytest.fixture
def blank_image(tmp_path):
    """Generate a clean synthetic blank image with zero text."""
    img_path = tmp_path / "blank_test.jpg"
    img = Image.new("RGB", (300, 300), color=(255, 255, 255))
    img.save(str(img_path))
    return str(img_path)


@pytest.fixture
def text_image(tmp_path):
    """Generate a synthetic test image with standard declarations."""
    img_path = tmp_path / "text_test.jpg"
    img = Image.new("RGB", (600, 250), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 30), "NET QUANTITY: 500 g", fill=(0, 0, 0))
    draw.text((20, 80), "MAXIMUM RETAIL PRICE Rs. 150.00", fill=(0, 0, 0))
    draw.text((20, 130), "DATE OF PKG: 01/2025", fill=(0, 0, 0))
    img.save(str(img_path))
    return str(img_path)


# =========================================================================
# BARCODE ROBUSTNESS TESTS
# =========================================================================

def test_pyzbar_availability_check():
    """Verify is_pyzbar_available reports boolean capability without throwing."""
    avail = is_pyzbar_available()
    assert isinstance(avail, bool)


def test_barcode_decode_with_no_barcode(blank_image):
    """When an image contains no barcode and no OCR text, return NOT_DETECTED without error."""
    result = decode_barcodes(blank_image, raw_text="")
    assert result is not None
    assert result.get("value") is None
    assert result.get("confidence") == 0.0
    assert result.get("type") in ("NOT_DETECTED", "CAPABILITY_UNAVAILABLE")


def test_barcode_decode_fallback_to_valid_ocr_ean13(blank_image):
    """When pyzbar finds nothing (or is unavailable), valid 13-digit EAN in OCR text is recovered."""
    raw_text = "Batch: B101\nBarcode: 8909081007903\nNet Qty: 100g"
    result = decode_barcodes(blank_image, raw_text=raw_text)
    assert result is not None
    assert result.get("value") == "8909081007903"
    assert result.get("type") == "EAN13"
    assert result.get("source") == "OCR_BARCODE_TEXT"


def test_barcode_decode_when_pyzbar_unavailable(monkeypatch, blank_image):
    """When pyzbar is not installed, return structured CAPABILITY_UNAVAILABLE without crashing."""
    import app.barcode_decoder as bc_module
    monkeypatch.setattr(bc_module, "is_pyzbar_available", lambda: False)
    monkeypatch.setattr(bc_module, "_PYZBAR_ERROR", "Simulated missing pyzbar")

    result = decode_barcodes(blank_image, raw_text="")
    assert result is not None
    assert result.get("type") == "CAPABILITY_UNAVAILABLE"
    assert result.get("status") == "UNAVAILABLE"
    assert result.get("value") is None


def test_barcode_decode_on_corrupt_file(tmp_path):
    """A corrupted/non-image file returns structured failure and does not raise an unhandled exception."""
    corrupt_file = tmp_path / "corrupt.jpg"
    corrupt_file.write_bytes(b"not a valid image")

    result = decode_barcodes(str(corrupt_file), raw_text="")
    assert result is not None
    assert result.get("value") is None
    assert result.get("status") in ("FAILED", "UNAVAILABLE")


# =========================================================================
# OCR ROBUSTNESS TESTS
# =========================================================================

def test_ocr_success_with_text(text_image):
    """Valid text image returns SUCCESS_WITH_TEXT and non-empty items."""
    result = run_ocr(text_image)
    assert result is not None
    assert result["ocr_status"] == "SUCCESS_WITH_TEXT"
    assert result["total_detections"] > 0
    assert result["error"] is None
    assert len(result["ocr_items"]) > 0
    assert "NET" in result["raw_text"] or "QUANTITY" in result["raw_text"] or "150" in result["raw_text"]


def test_ocr_zero_detections_returns_no_text_detected(blank_image):
    """Blank image returns NO_TEXT_DETECTED state without raising an exception or setting error."""
    result = run_ocr(blank_image)
    assert result is not None
    assert result["ocr_status"] == "NO_TEXT_DETECTED"
    assert result["total_detections"] == 0
    assert result["error"] is None
    assert result["engine_error"] is None
    assert result["raw_text"] == ""
    assert result["ocr_items"] == []
    assert result["attempt_count"] >= 1
    assert result["successful_attempt_count"] >= 1


def test_ocr_invalid_image_handling(tmp_path):
    """Non-existent or zero-byte file returns INVALID_IMAGE."""
    empty_file = tmp_path / "empty.jpg"
    empty_file.write_bytes(b"")

    res_missing = run_ocr("non_existent_path.jpg")
    assert res_missing["ocr_status"] == "INVALID_IMAGE"
    assert res_missing["total_detections"] == 0
    assert res_missing["error"] is not None

    res_empty = run_ocr(str(empty_file))
    assert res_empty["ocr_status"] == "INVALID_IMAGE"
    assert res_empty["total_detections"] == 0


def test_ocr_engine_exception_handling(monkeypatch, text_image):
    """When the underlying engine raises an exception, return OCR_ENGINE_ERROR gracefully."""
    import app.ocr.ocr_service as ocr_module

    class BrokenOCR:
        def ocr(self, *args, **kwargs):
            raise RuntimeError("Simulated PaddleOCR CUDA Out of Memory")

    monkeypatch.setattr(ocr_module, "_get_ocr", lambda: BrokenOCR())

    result = run_ocr(text_image)
    assert result is not None
    assert result["ocr_status"] == "OCR_ENGINE_ERROR"
    assert result["total_detections"] == 0
    assert "Simulated PaddleOCR" in str(result["error"])
    assert "Simulated PaddleOCR" in str(result["engine_error"])


# =========================================================================
# SCAN PIPELINE MULTI-IMAGE RESILIENCE TESTS
# =========================================================================

def test_scan_pipeline_multi_image_partial_ocr_success(tmp_path, monkeypatch):
    """In a multi-image inspection where one image has no text and one has text,
    the pipeline processes valid text from the second image without 500 error."""
    from fastapi.testclient import TestClient
    from app.main import app

    # Create two synthetic images
    img1 = Image.new("RGB", (200, 200), color=(255, 255, 255))
    buf1 = io.BytesIO()
    img1.save(buf1, format="JPEG")
    buf1.seek(0)

    img2 = Image.new("RGB", (600, 200), color=(255, 255, 255))
    buf2 = io.BytesIO()
    img2.save(buf2, format="JPEG")
    buf2.seek(0)

    # Mock run_ocr so img1 returns NO_TEXT_DETECTED and img2 returns valid declarations
    def mock_run_ocr(path: str) -> Dict[str, Any]:
        if "processed_0" in path:
            return {
                "ocr_status": "NO_TEXT_DETECTED",
                "raw_text": "",
                "ocr_items": [],
                "processing_time_ms": 50,
                "total_detections": 0,
                "engine": "PaddleOCR",
                "error": None,
            }
        return {
            "ocr_status": "SUCCESS_WITH_TEXT",
            "raw_text": "MRP Rs. 100.00\nNet Weight: 500 g\nBrand: TestCo\nProduct: Test Flakes",
            "ocr_items": [
                {"text": "MRP Rs. 100.00", "confidence": 0.95, "bbox": [10, 10, 100, 30]},
                {"text": "Net Weight: 500 g", "confidence": 0.95, "bbox": [10, 40, 100, 60]},
                {"text": "Brand: TestCo", "confidence": 0.90, "bbox": [10, 70, 80, 90]},
                {"text": "Product: Test Flakes", "confidence": 0.90, "bbox": [10, 100, 120, 120]},
            ],
            "processing_time_ms": 120,
            "total_detections": 4,
            "engine": "PaddleOCR",
            "error": None,
        }

    monkeypatch.setattr("app.api.scan.run_ocr", mock_run_ocr)

    client = TestClient(app)
    response = client.post(
        "/api/scan",
        files=[
            ("files", ("image_blank.jpg", buf1.getvalue(), "image/jpeg")),
            ("files", ("image_text.jpg", buf2.getvalue(), "image/jpeg")),
        ],
        data={"package_type": "RETAIL", "import_status": "DOMESTIC"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert "inspection_id" in data
    # Extracted fields should contain declarations from the second image
    extracted = data.get("extracted_fields", {})
    assert "MRP" in extracted or "DECLARED_NET_QUANTITY" in extracted


def test_scan_pipeline_all_images_no_text_detected(tmp_path, monkeypatch):
    """When all uploaded images have zero text detections, the pipeline must:
    1. Complete with HTTP 200 (not 500).
    2. Not hallucinate or fabricate text.
    3. Evaluate rules deterministically (missing mandatory fields -> NON-COMPLIANT / NOT_VERIFIABLE).
    """
    from fastapi.testclient import TestClient
    from app.main import app

    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)

    def mock_run_ocr_zero(path: str) -> Dict[str, Any]:
        return {
            "ocr_status": "NO_TEXT_DETECTED",
            "raw_text": "",
            "ocr_items": [],
            "processing_time_ms": 45,
            "total_detections": 0,
            "engine": "PaddleOCR",
            "error": None,
        }

    monkeypatch.setattr("app.api.scan.run_ocr", mock_run_ocr_zero)

    client = TestClient(app)
    response = client.post(
        "/api/scan",
        files=[
            ("files", ("blank.jpg", buf.getvalue(), "image/jpeg")),
        ],
        data={"package_type": "RETAIL", "import_status": "DOMESTIC"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert "inspection_id" in data
    assert data.get("overall_result") in ("NON-COMPLIANT", "NOT_VERIFIABLE", "REQUIRES_REVIEW")
