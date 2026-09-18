"""
Tests for image upload hardening, validation, and security constraints.
"""

import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import get_settings


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _create_image_bytes(fmt: str = "JPEG", size=(50, 50), color="blue") -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def test_valid_jpeg_upload_accepted(client, monkeypatch):
    monkeypatch.setattr("app.api.scan.run_ocr", lambda path: {"raw_text": "Sample Text", "ocr_items": []})
    jpeg_bytes = _create_image_bytes("JPEG")
    files = [("files", ("label.jpg", jpeg_bytes, "image/jpeg"))]
    response = client.post("/api/scan", files=files, data={"package_type": "RETAIL", "import_status": "DOMESTIC"})
    assert response.status_code == 200
    data = response.json()
    assert "inspection_id" in data


def test_valid_png_upload_accepted(client, monkeypatch):
    monkeypatch.setattr("app.api.scan.run_ocr", lambda path: {"raw_text": "Sample Text", "ocr_items": []})
    png_bytes = _create_image_bytes("PNG")
    files = [("files", ("label.png", png_bytes, "image/png"))]
    response = client.post("/api/scan", files=files, data={"package_type": "RETAIL", "import_status": "DOMESTIC"})
    assert response.status_code == 200
    data = response.json()
    assert "inspection_id" in data


def test_empty_upload_rejected(client):
    files = [("files", ("empty.jpg", b"", "image/jpeg"))]
    response = client.post("/api/scan", files=files)
    assert response.status_code == 400
    assert "empty" in response.json().get("detail", "").lower()


def test_wrong_mime_type_rejected(client):
    png_bytes = _create_image_bytes("PNG")
    files = [("files", ("doc.pdf", png_bytes, "application/pdf"))]
    response = client.post("/api/scan", files=files)
    assert response.status_code == 415
    assert "unsupported media type" in response.json().get("detail", "").lower()


def test_renamed_non_image_file_rejected(client):
    fake_content = b"<html><body><h1>This is definitely not an image</h1></body></html>"
    files = [("files", ("malicious.jpg", fake_content, "image/jpeg"))]
    response = client.post("/api/scan", files=files)
    assert response.status_code == 400
    assert "not a valid image" in response.json().get("detail", "").lower()


def test_oversized_file_rejected(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_BYTES", 50)
    png_bytes = _create_image_bytes("PNG")
    assert len(png_bytes) > 50
    files = [("files", ("large.png", png_bytes, "image/png"))]
    response = client.post("/api/scan", files=files)
    assert response.status_code == 413
    assert "exceeds maximum allowed size" in response.json().get("detail", "").lower()


def test_path_traversal_filename_sanitized_and_safe(client, monkeypatch):
    monkeypatch.setattr("app.api.scan.run_ocr", lambda path: {"raw_text": "Sample Text", "ocr_items": []})
    png_bytes = _create_image_bytes("PNG")
    files = [("files", ("../../../../etc/passwd.png", png_bytes, "image/png"))]
    response = client.post("/api/scan", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["image_url"].startswith("/uploads/scan_")
    assert "passwd" not in data["image_url"]
    assert ".." not in data["image_url"]


def test_multi_image_upload_with_one_invalid_file_rejects_whole_batch(client):
    jpeg_bytes = _create_image_bytes("JPEG")
    fake_content = b"echo 'bad script'"
    files = [
        ("files", ("valid.jpg", jpeg_bytes, "image/jpeg")),
        ("files", ("disguised.jpg", fake_content, "image/jpeg")),
    ]
    response = client.post("/api/scan", files=files)
    assert response.status_code == 400
    assert "not a valid image" in response.json().get("detail", "").lower()
