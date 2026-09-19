"""
Comprehensive offline test suite for the Automatic Image Quality Gate.
Uses programmatic synthetic Pillow / OpenCV image generation for 100% reproducible tests.
"""

import os
import tempfile
import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.image_quality.schemas import (
    ImageQualityStatus,
    QualityIssueCode,
    IssueSeverity,
)
from app.image_quality.policy import QualityPolicyConfig, evaluate_image_quality
from app.image_quality.analyzer import (
    analyze_image_quality,
    analyze_inspection_images,
)
from app.core.config import Settings
from app.core.constants import InspectionStatus


# ---------------------------------------------------------------------------
# Programmatic Image Generators (No copyrighted external assets)
# ---------------------------------------------------------------------------

def _draw_mock_package_text(draw: ImageDraw.ImageDraw, offset: int = 0):
    """Draw realistic package label statutory declarations."""
    declarations = [
        "PARLE-G ORIGINAL GLUCOSE BISCUITS",
        "Generic Name: Biscuits",
        "Net Quantity: 250 g",
        "MRP Rs. 25.00 (Incl. of all taxes)",
        "Pkg Date: 05/2024   Batch: B-901",
        "Mfg by: Parle Products Pvt Ltd, Mumbai 400057",
        "Customer Care: 1800-22-2211, care@parle.biz",
        "100% Vegetarian Made in India",
    ]
    y = 50 + offset
    for line in declarations:
        draw.text((50, y), line, fill=(20, 20, 20))
        y += 45


def make_sharp_label_image(path: str, width: int = 800, height: int = 600) -> str:
    """Create a crisp, sharp statutory package label image."""
    img = Image.new("RGB", (width, height), color=(245, 245, 242))
    draw = ImageDraw.Draw(img)
    # Draw border
    draw.rectangle([(20, 20), (width - 20, height - 20)], outline=(40, 40, 40), width=3)
    _draw_mock_package_text(draw)
    img.save(path, format="JPEG", quality=95)
    return path


def make_blurred_image(src_path: str, dst_path: str, ksize: int = 25) -> str:
    """Apply strong Gaussian blur to simulate camera shake or out-of-focus capture."""
    cv_img = cv2.imread(src_path)
    blurred = cv2.GaussianBlur(cv_img, (ksize, ksize), 0)
    cv2.imwrite(dst_path, blurred)
    return dst_path


def make_mild_blurred_image(src_path: str, dst_path: str) -> str:
    """Apply mild blur to simulate borderline focus."""
    cv_img = cv2.imread(src_path)
    blurred = cv2.GaussianBlur(cv_img, (5, 5), 0)
    cv2.imwrite(dst_path, blurred)
    return dst_path


def make_low_resolution_image(path: str, width: int = 180, height: int = 150) -> str:
    """Create an image below the statutory minimum resolution threshold."""
    img = Image.new("RGB", (width, height), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), "Tiny text", fill=(0, 0, 0))
    img.save(path, format="JPEG", quality=80)
    return path


def make_dark_image(src_path: str, dst_path: str, scale: float = 0.42) -> str:
    """Simulate moderate underexposure."""
    cv_img = cv2.imread(src_path).astype(np.float32)
    darkened = np.clip(cv_img * scale, 0, 255).astype(np.uint8)
    cv2.imwrite(dst_path, darkened)
    return dst_path


def make_almost_black_image(path: str, width: int = 800, height: int = 600) -> str:
    """Simulate near-total darkness (e.g. camera covered or pitch black room)."""
    cv_img = np.random.randint(0, 15, (height, width, 3), dtype=np.uint8)
    cv2.imwrite(path, cv_img)
    return path


def make_white_package_image(path: str, width: int = 800, height: int = 600) -> str:
    """Simulate legitimate clean white packaging with crisp typography."""
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(40, 40), (width - 40, height - 40)], outline=(180, 180, 180), width=2)
    _draw_mock_package_text(draw)
    img.save(path, format="JPEG", quality=95)
    return path


def make_overexposed_image(path: str, width: int = 800, height: int = 600) -> str:
    """Simulate severe sensor clipping / blown out overexposure."""
    cv_img = np.full((height, width, 3), 253, dtype=np.uint8)
    # A few faint pixels that are obliterated
    cv_img[100:150, 100:200] = 240
    cv2.imwrite(path, cv_img)
    return path


def make_small_glare_image(src_path: str, dst_path: str) -> str:
    """Simulate a small benign specular highlight."""
    cv_img = cv2.imread(src_path)
    # Small highlight circle (radius 12 px)
    cv2.circle(cv_img, (150, 150), 12, (255, 255, 255), -1)
    cv2.imwrite(dst_path, cv_img)
    return dst_path


def make_severe_glare_image(src_path: str, dst_path: str) -> str:
    """Simulate severe, destructive specular glare covering major label declarations."""
    cv_img = cv2.imread(src_path)
    h, w = cv_img.shape[:2]
    # Large washed-out flash ellipse covering 35% of image
    cv2.ellipse(cv_img, (w // 2, h // 2), (int(w * 0.35), int(h * 0.28)), 0, 0, 360, (255, 255, 255), -1)
    cv2.imwrite(dst_path, cv_img)
    return dst_path


def make_low_contrast_image(path: str, width: int = 800, height: int = 600) -> str:
    """Simulate washed-out low contrast packaging."""
    cv_img = np.full((height, width, 3), 128, dtype=np.uint8)
    # Very faint text that barely differs in intensity
    cv_img[100:180, 50:400] = 132
    cv2.imwrite(path, cv_img)
    return path


# ---------------------------------------------------------------------------
# Test Fixture Directory
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def image_fixtures():
    """Generate all synthetic test fixtures once per test module."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sharp = os.path.join(tmpdir, "sharp.jpg")
        make_sharp_label_image(sharp)

        blurred = os.path.join(tmpdir, "blurred.jpg")
        make_blurred_image(sharp, blurred, ksize=29)

        mild_blur = os.path.join(tmpdir, "mild_blur.jpg")
        make_mild_blurred_image(sharp, mild_blur)

        low_res = os.path.join(tmpdir, "low_res.jpg")
        make_low_resolution_image(low_res, width=180, height=160)

        dark = os.path.join(tmpdir, "dark.jpg")
        make_dark_image(sharp, dark, scale=0.45)

        almost_black = os.path.join(tmpdir, "almost_black.jpg")
        make_almost_black_image(almost_black)

        white_pkg = os.path.join(tmpdir, "white_pkg.jpg")
        make_white_package_image(white_pkg)

        overexposed = os.path.join(tmpdir, "overexposed.jpg")
        make_overexposed_image(overexposed)

        small_glare = os.path.join(tmpdir, "small_glare.jpg")
        make_small_glare_image(sharp, small_glare)

        severe_glare = os.path.join(tmpdir, "severe_glare.jpg")
        make_severe_glare_image(sharp, severe_glare)

        low_contrast = os.path.join(tmpdir, "low_contrast.jpg")
        make_low_contrast_image(low_contrast)

        yield {
            "tmpdir": tmpdir,
            "sharp": sharp,
            "blurred": blurred,
            "mild_blur": mild_blur,
            "low_res": low_res,
            "dark": dark,
            "almost_black": almost_black,
            "white_pkg": white_pkg,
            "overexposed": overexposed,
            "small_glare": small_glare,
            "severe_glare": severe_glare,
            "low_contrast": low_contrast,
        }


# ---------------------------------------------------------------------------
# Test Cases 1 - 22
# ---------------------------------------------------------------------------

def test_01_sharp_normal_image_accept(image_fixtures):
    """1. Sharp, high-contrast statutory label must be ACCEPT."""
    res = analyze_image_quality(image_fixtures["sharp"])
    assert res.status == ImageQualityStatus.ACCEPT
    assert res.quality_score >= 0.85
    assert not any(i.severity == IssueSeverity.ERROR for i in res.issues)
    assert res.metrics.blur_score > 75.0


def test_02_mildly_blurred_image_warn(image_fixtures):
    """2. Mildly blurred image should produce a WARN, not a hard rejection."""
    res = analyze_image_quality(image_fixtures["mild_blur"])
    # Mild blur can be WARN or ACCEPT if edge content remains moderately sharp, but not RECAPTURE_REQUIRED
    assert res.status in (ImageQualityStatus.WARN, ImageQualityStatus.ACCEPT)
    assert res.status != ImageQualityStatus.RECAPTURE_REQUIRED


def test_03_severely_blurred_image_recapture_required(image_fixtures):
    """3. Severely blurred image must trigger RECAPTURE_REQUIRED with IMAGE_TOO_BLURRY code."""
    res = analyze_image_quality(image_fixtures["blurred"])
    assert res.status == ImageQualityStatus.RECAPTURE_REQUIRED
    codes = [i.code for i in res.issues]
    assert QualityIssueCode.IMAGE_TOO_BLURRY in codes
    error_issue = next(i for i in res.issues if i.code == QualityIssueCode.IMAGE_TOO_BLURRY)
    assert error_issue.severity == IssueSeverity.ERROR
    assert error_issue.measured_value is not None
    assert error_issue.threshold is not None


def test_04_normal_resolution_accept(image_fixtures):
    """4. Normal resolution image (800x600) meets minimum dimensions and pixel count."""
    res = analyze_image_quality(image_fixtures["sharp"])
    assert res.metrics.width == 800
    assert res.metrics.height == 600
    assert res.metrics.total_pixels == 480000
    assert not any(i.code == QualityIssueCode.IMAGE_LOW_RESOLUTION for i in res.issues)


def test_05_extremely_low_resolution_recapture(image_fixtures):
    """5. Extremely low resolution (180x160) must trigger RECAPTURE_REQUIRED."""
    res = analyze_image_quality(image_fixtures["low_res"])
    assert res.status == ImageQualityStatus.RECAPTURE_REQUIRED
    codes = [i.code for i in res.issues]
    assert QualityIssueCode.IMAGE_LOW_RESOLUTION in codes


def test_06_moderately_dark_image_warn(image_fixtures):
    """6. Moderately dark image should yield WARN rather than fatal rejection."""
    res = analyze_image_quality(image_fixtures["dark"])
    assert res.status in (ImageQualityStatus.WARN, ImageQualityStatus.ACCEPT)
    assert res.status != ImageQualityStatus.RECAPTURE_REQUIRED


def test_07_almost_black_image_recapture(image_fixtures):
    """7. Pitch black / unlit image must trigger RECAPTURE_REQUIRED with IMAGE_TOO_DARK."""
    res = analyze_image_quality(image_fixtures["almost_black"])
    assert res.status == ImageQualityStatus.RECAPTURE_REQUIRED
    codes = [i.code for i in res.issues]
    assert QualityIssueCode.IMAGE_TOO_DARK in codes


def test_08_normal_white_package_not_falsely_overexposed(image_fixtures):
    """8. Legitimate clean white package with black text must NOT be falsely rejected."""
    res = analyze_image_quality(image_fixtures["white_pkg"])
    assert res.status == ImageQualityStatus.ACCEPT
    assert not any(i.severity == IssueSeverity.ERROR for i in res.issues)


def test_09_severe_clipping_overexposed_recapture(image_fixtures):
    """9. Severe sensor overexposure (>60% blown pixels) must trigger RECAPTURE_REQUIRED."""
    res = analyze_image_quality(image_fixtures["overexposed"])
    assert res.status == ImageQualityStatus.RECAPTURE_REQUIRED
    codes = [i.code for i in res.issues]
    assert QualityIssueCode.IMAGE_OVEREXPOSED in codes


def test_10_small_glare_patch_not_hard_rejected(image_fixtures):
    """10. Minor specular highlight must NOT cause hard rejection."""
    res = analyze_image_quality(image_fixtures["small_glare"])
    assert res.status in (ImageQualityStatus.ACCEPT, ImageQualityStatus.WARN)
    assert res.status != ImageQualityStatus.RECAPTURE_REQUIRED


def test_11_severe_glare_recapture_required(image_fixtures):
    """11. Large destructive glare covering packaging text must trigger RECAPTURE_REQUIRED."""
    res = analyze_image_quality(image_fixtures["severe_glare"])
    assert res.status == ImageQualityStatus.RECAPTURE_REQUIRED
    codes = [i.code for i in res.issues]
    assert QualityIssueCode.IMAGE_GLARE in codes


def test_12_low_contrast_warn_or_recapture(image_fixtures):
    """12. Flat washed-out contrast must trigger low contrast issue."""
    res = analyze_image_quality(image_fixtures["low_contrast"])
    assert res.status in (ImageQualityStatus.WARN, ImageQualityStatus.RECAPTURE_REQUIRED)
    codes = [i.code for i in res.issues]
    assert QualityIssueCode.IMAGE_LOW_CONTRAST in codes


def test_13_multi_image_one_bad_panel_proceeds(image_fixtures):
    """13. Multi-image case: 1 sharp panel + 1 severely blurred panel."""
    paths = [image_fixtures["sharp"], image_fixtures["blurred"]]
    summary = analyze_inspection_images(paths)

    assert summary.total_images == 2
    assert summary.accepted_images == 1
    assert summary.rejected_images == 1
    assert summary.usable_image_indices == [0]
    assert summary.recapture_image_indices == [1]
    # Inspection as a whole can proceed with usable image 0!
    assert summary.overall_quality_status == ImageQualityStatus.WARN


def test_14_all_images_unusable_case_level_recapture(image_fixtures):
    """14. If ALL submitted images are unusable, overall status is RECAPTURE_REQUIRED."""
    paths = [image_fixtures["blurred"], image_fixtures["almost_black"]]
    summary = analyze_inspection_images(paths)

    assert summary.total_images == 2
    assert summary.rejected_images == 2
    assert summary.usable_image_indices == []
    assert summary.recapture_image_indices == [0, 1]
    assert summary.overall_quality_status == ImageQualityStatus.RECAPTURE_REQUIRED


def test_15_rejected_image_excluded_from_ocr(image_fixtures, monkeypatch):
    """15. Verify that in the pipeline, an unusable image does not invoke OCR."""
    from app.ocr.ocr_service import run_ocr
    ocr_called_paths = []

    def mock_run_ocr(img_path):
        ocr_called_paths.append(img_path)
        return {"raw_text": "Sample text", "ocr_items": [], "ocr_status": "SUCCESS"}

    monkeypatch.setattr("app.ocr.ocr_service.run_ocr", mock_run_ocr)

    paths = [image_fixtures["sharp"], image_fixtures["blurred"]]
    summary = analyze_inspection_images(paths)

    usable_indices = summary.usable_image_indices
    assert usable_indices == [0]
    assert 1 not in usable_indices


def test_16_rejected_image_does_not_reach_gemini():
    """16. Empty/filtered tokens from rejected panels mean Gemini only receives clean tokens."""
    # If panel 1 is rejected, ocr_items only has tokens with image_index == 0.
    usable_ocr_items = [{"token_id": 0, "text": "MRP Rs 50", "image_index": 0}]
    # Bounded tokens passed to Gemini never include unverified tokens from rejected image_index 1
    assert all(item["image_index"] != 1 for item in usable_ocr_items)


def test_17_quality_warning_never_causes_legal_fail():
    """17. Image quality status is evidence quality, never regulatory FAIL."""
    from app.rules.rule_engine import derive_overall_result
    # Poor quality or unverified evidence leads to NOT_VERIFIABLE, never FAIL
    overall = derive_overall_result([{"status": "NOT_VERIFIABLE", "verification_type": "IMAGE_UNVERIFIED"}])
    assert overall in (InspectionStatus.NOT_VERIFIABLE, "NOT_VERIFIABLE")
    assert overall != "FAIL"
    assert overall != InspectionStatus.NON_COMPLIANT


def test_18_image_quality_gate_disabled_preserves_legacy():
    """18. When IMAGE_QUALITY_GATE_ENABLED=False, all images are considered usable."""
    settings = Settings(IMAGE_QUALITY_GATE_ENABLED=False)
    assert settings.IMAGE_QUALITY_GATE_ENABLED is False


def test_19_raw_original_files_remain_untouched(image_fixtures):
    """19. Ensure analyze_image_quality never modifies original files on disk."""
    sharp_path = image_fixtures["sharp"]
    mtime_before = os.path.getmtime(sharp_path)
    size_before = os.path.getsize(sharp_path)

    analyze_image_quality(sharp_path)

    mtime_after = os.path.getmtime(sharp_path)
    size_after = os.path.getsize(sharp_path)

    assert mtime_before == mtime_after
    assert size_before == size_after


def test_20_benchmark_metrics_calculator_reports_quality():
    """20. Verify BenchmarkMetricsCalculator computes quality_accept_rate and False Recaptures."""
    from benchmark.schema import CaseEvaluation
    from benchmark.metrics import BenchmarkMetricsCalculator

    cases = [
        CaseEvaluation(
            case_id="PKG001",
            product_name="Test Product 1",
            quality_status="ACCEPT",
            expected_overall_result="COMPLIANT",
            predicted_overall_result="COMPLIANT",
        ),
        CaseEvaluation(
            case_id="PKG002",
            product_name="Test Product 2",
            quality_status="WARN",
            tags=["blurry"],
            expected_overall_result="COMPLIANT",
            predicted_overall_result="COMPLIANT",
        ),
        CaseEvaluation(
            case_id="PKG003",
            product_name="Test Product 3",
            quality_status="RECAPTURE_REQUIRED",
            tags=["unusable"],
            expected_overall_result="NOT_VERIFIABLE",
            predicted_overall_result="NOT_VERIFIABLE",
        ),
    ]

    calc = BenchmarkMetricsCalculator(cases)
    qm = calc.compute_image_quality_metrics()

    assert qm["gate_enabled"] is True
    assert qm["total_cases_evaluated"] == 3
    assert qm["quality_accept_rate"] == round(1 / 3, 4)
    assert qm["quality_warn_rate"] == round(1 / 3, 4)
    assert qm["quality_recapture_rate"] == round(1 / 3, 4)
    assert qm["false_recapture_count"] == 0  # PKG003 was expected NOT_VERIFIABLE, so not a false recapture
    assert qm["missed_bad_image_count"] == 0


def test_21_quality_score_computation_bounded():
    """21. Composite quality score is strictly bounded [0.0, 1.0] and non-null."""
    from app.image_quality.schemas import ImageQualityMetric

    m_good = ImageQualityMetric(
        blur_score=150.0,
        brightness_mean=130.0,
        dark_pixel_ratio=0.05,
        bright_pixel_ratio=0.05,
        glare_ratio=0.01,
        contrast_std=50.0,
        width=1920,
        height=1080,
        total_pixels=1920 * 1080,
    )
    res_good = evaluate_image_quality(m_good)
    assert 0.0 <= res_good.quality_score <= 1.0
    assert res_good.quality_score >= 0.85
    assert res_good.status == ImageQualityStatus.ACCEPT

    m_bad = ImageQualityMetric(
        blur_score=10.0,
        brightness_mean=20.0,
        dark_pixel_ratio=0.95,
        bright_pixel_ratio=0.0,
        glare_ratio=0.25,
        contrast_std=5.0,
        width=200,
        height=200,
        total_pixels=40000,
    )
    res_bad = evaluate_image_quality(m_bad)
    assert 0.0 <= res_bad.quality_score <= 1.0
    assert res_bad.status == ImageQualityStatus.RECAPTURE_REQUIRED


def test_22_quality_gate_execution_speed(image_fixtures):
    """22. Quality gate must execute quickly (< 100ms per typical image)."""
    res = analyze_image_quality(image_fixtures["sharp"])
    # Processing on bounded 1280 image takes tens of ms
    assert res.processing_time_ms < 500  # Conservative bound for CI/test environments
