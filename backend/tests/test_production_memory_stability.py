"""Production-like multi-panel stress and memory stability test suite.

Simulates 4 high-resolution package panel uploads through the complete FastAPI /api/scan pipeline.
Measures process RSS memory across 1, 2, and 5 sequential inspections to verify memory is bounded
and does not experience runaway accumulation.
"""

import io
import os
import sys
import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from app.main import app
from app.utils.memory import get_process_rss_mb, force_garbage_collection, log_memory_checkpoint


def _create_synthetic_panel_image(text_lines, width=1600, height=1200, bg_color="white", fg_color="black"):
    """Create a high-resolution synthetic package panel with real text declarations."""
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Draw simulated boundary / label frame
    draw.rectangle([20, 20, width - 20, height - 20], outline="gray", width=4)

    # Render declaration text lines with line spacing
    y = 60
    for line in text_lines:
        draw.text((60, y), line, fill=fg_color)
        y += 70

    # Output to JPEG byte stream
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture(scope="module")
def four_panel_image_bytes():
    """Generates 4 high-resolution panels simulating a complete retail food product package."""
    panel_1 = _create_synthetic_panel_image([
        "HIMALAYAN BLEND GREEN TEA",
        "PREMIUM ORGANIC BEVERAGE",
        "Net Qty: 200 g",
        "100% PURE AND NATURAL",
    ], width=1600, height=1200)

    panel_2 = _create_synthetic_panel_image([
        "Manufactured and Packed by:",
        "Himalayan Tea Estates Pvt. Ltd.",
        "Plot 42, Tea Garden Road, Kangra, HP - 176001",
        "Consumer Care Cell:",
        "Toll Free: 1800-111-222",
        "Email: care@himalayantea.in",
    ], width=1600, height=1200)

    panel_3 = _create_synthetic_panel_image([
        "MRP Rs. 350.00 (Incl. of all taxes)",
        "USP: Rs. 1.75 / g",
        "Mfg Date: 01/2026",
        "Use By: 01/2027",
        "Batch No: HMB-2026-01",
        "Country of Origin: India",
    ], width=1600, height=1200)

    panel_4 = _create_synthetic_panel_image([
        "Ingredients: Green Tea Leaves, Tulsi, Cardamom",
        "Nutritional Facts per 100g:",
        "Energy: 320 kcal, Protein: 4g",
        "Carbohydrate: 70g, Fat: 0g",
        "FSSAI Lic. No. 10019011000123",
        "8901030885547",
    ], width=1600, height=1200)

    return [panel_1, panel_2, panel_3, panel_4]


def test_four_panel_inspection_pipeline_completes(four_panel_image_bytes):
    """Verify that a real 4-panel high-resolution scan completes successfully with full evidence."""
    client = TestClient(app)
    force_garbage_collection()
    initial_rss = get_process_rss_mb()
    log_memory_checkpoint("test_four_panel_start", f"initial_rss={initial_rss}")

    files = [
        ("files", (f"panel_{i + 1}.jpg", io.BytesIO(img_bytes), "image/jpeg"))
        for i, img_bytes in enumerate(four_panel_image_bytes)
    ]
    data = {
        "package_type": "RETAIL",
        "import_status": "DOMESTIC",
    }

    response = client.post("/api/scan", files=files, data=data)
    assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.text}"

    payload = response.json()
    assert "inspection_id" in payload
    assert payload["inspection_id"] > 0
    assert len(payload.get("images", [])) == 4
    assert payload.get("overall_result") in ["COMPLIANT", "NON-COMPLIANT", "NOT_VERIFIABLE", "NEEDS_REVIEW"]
    assert len(payload.get("rule_results", [])) > 0

    post_rss = force_garbage_collection()
    log_memory_checkpoint("test_four_panel_end", f"post_rss={post_rss}")
    print(f"\n[Test 1] 4-Panel Scan complete. RSS: {initial_rss:.2f} MB -> {post_rss:.2f} MB")


def test_sequential_inspection_memory_stability(four_panel_image_bytes):
    """Run 5 sequential 4-panel inspections in the same process to verify memory remains bounded."""
    client = TestClient(app)
    force_garbage_collection()

    rss_baseline = get_process_rss_mb()
    rss_history = []

    print(f"\n[Test 2 Memory Stability] Baseline RSS: {rss_baseline:.2f} MB")

    for iteration in range(1, 6):
        files = [
            ("files", (f"panel_{i + 1}.jpg", io.BytesIO(img_bytes), "image/jpeg"))
            for i, img_bytes in enumerate(four_panel_image_bytes)
        ]
        data = {
            "package_type": "RETAIL",
            "import_status": "DOMESTIC",
        }

        resp = client.post("/api/scan", files=files, data=data)
        assert resp.status_code == 200, f"Iteration {iteration} failed with {resp.status_code}: {resp.text}"

        post_gc_rss = force_garbage_collection()
        rss_history.append(post_gc_rss)
        print(f"  Iteration {iteration}/5 complete: RSS = {post_gc_rss:.2f} MB")

    # Verify that memory after 5 iterations does not continuously diverge
    # Compare iteration 2 and iteration 5 (after initial model warm-up in iteration 1)
    rss_growth_after_warmup = rss_history[-1] - rss_history[1]
    print(f"Memory change between iteration 2 and 5: {rss_growth_after_warmup:+.2f} MB")

    # In a stable process, the memory growth between iteration 2 and 5 should remain bounded (under 150 MB across 20 high-res image scans)
    assert rss_growth_after_warmup < 150.0, (
        f"Memory growth across sequential inspections exceeded safe threshold: {rss_growth_after_warmup:.2f} MB"
    )


def test_max_images_per_inspection_enforcement(four_panel_image_bytes):
    """Verify that uploading more images than MAX_IMAGES_PER_INSPECTION returns a controlled HTTP 400."""
    client = TestClient(app)
    # Upload 9 panels (exceeding default limit of 8)
    nine_files = [
        ("files", (f"panel_{i + 1}.jpg", io.BytesIO(four_panel_image_bytes[i % 4]), "image/jpeg"))
        for i in range(9)
    ]
    resp = client.post("/api/scan", files=nine_files, data={"package_type": "RETAIL", "import_status": "DOMESTIC"})
    assert resp.status_code == 400
    assert "Exceeded maximum allowed images" in resp.json()["detail"]
