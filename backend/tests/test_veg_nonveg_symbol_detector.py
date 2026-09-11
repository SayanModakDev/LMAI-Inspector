"""
Test suite for FSSAI Vegetarian / Non-Vegetarian symbol visual detection.
Verifies dual-space color masking, enclosing frame geometry, fidelity scoring,
and rejection of ambiguous red packaging backgrounds / text.
"""

import numpy as np
import cv2
import pytest
from app.visual_detection import detect_veg_nonveg_symbol, detect_food_symbol


def create_blank_canvas(width: int = 400, height: int = 400, bg_color: tuple = (245, 245, 245)) -> np.ndarray:
    """Create a neutral background canvas in BGR."""
    img = np.full((height, width, 3), bg_color, dtype=np.uint8)
    return img


def draw_fssai_veg_symbol(img: np.ndarray, top_left: tuple, size: int = 60) -> np.ndarray:
    """Draw a canonical FSSAI Veg symbol: green square outline with concentric filled green circle."""
    x, y = top_left
    # Pure FSSAI green in BGR: B=30, G=140, R=30
    green_bgr = (30, 140, 30)
    thickness = max(2, size // 15)
    # Outer square
    cv2.rectangle(img, (x, y), (x + size, y + size), green_bgr, thickness)
    # Inner circle
    center = (x + size // 2, y + size // 2)
    radius = int(size * 0.28)
    cv2.circle(img, center, radius, green_bgr, -1)
    return img


def draw_fssai_nonveg_symbol(img: np.ndarray, top_left: tuple, size: int = 60) -> np.ndarray:
    """Draw a canonical FSSAI Non-Veg symbol: brown square outline with concentric filled brown triangle/circle."""
    x, y = top_left
    # Brown in BGR: B=20, G=45, R=120
    brown_bgr = (20, 45, 120)
    thickness = max(2, size // 15)
    # Outer square
    cv2.rectangle(img, (x, y), (x + size, y + size), brown_bgr, thickness)
    # Inner equilateral triangle pointing up
    cx, cy = x + size // 2, y + size // 2
    r = int(size * 0.3)
    pts = np.array([
        [cx, cy - r],
        [cx - int(r * 0.866), cy + int(r * 0.5)],
        [cx + int(r * 0.866), cy + int(r * 0.5)]
    ], dtype=np.int32)
    cv2.fillPoly(img, [pts], brown_bgr)
    return img


class TestVegNonVegVisualDetector:
    """Unit tests for visual symbol detector."""

    def test_canonical_veg_symbol_detected(self):
        """A clean green circle in green square must be detected as VEGETARIAN with high confidence."""
        canvas = create_blank_canvas(300, 300)
        draw_fssai_veg_symbol(canvas, (100, 100), size=70)
        result = detect_veg_nonveg_symbol(canvas)

        assert result['detected'] is True
        assert result['symbol_type'] == 'VEGETARIAN'
        assert result['confidence'] >= 0.70
        assert result['features']['has_enclosing_square'] is True
        assert result['features']['shape'] == 'circle'

    def test_canonical_nonveg_symbol_detected(self):
        """A clean brown triangle in brown square must be detected as NON_VEGETARIAN with high confidence."""
        canvas = create_blank_canvas(300, 300)
        draw_fssai_nonveg_symbol(canvas, (100, 100), size=70)
        result = detect_veg_nonveg_symbol(canvas)

        assert result['detected'] is True
        assert result['symbol_type'] == 'NON_VEGETARIAN'
        assert result['confidence'] >= 0.70
        assert result['features']['has_enclosing_square'] is True

    def test_large_red_graphic_with_veg_symbol_does_not_falsely_detect_nonveg(self):
        """CRITICAL: On red packaging (like Tata Salt), large red graphics/banners must NOT

        overwhelm and falsely classify a genuine green vegetarian symbol as NON_VEGETARIAN.
        """
        # Canvas with a prominent red graphic banner (representing red packaging artwork)
        canvas = create_blank_canvas(500, 500)
        red_bgr = (40, 40, 200)
        # Large red banner
        cv2.rectangle(canvas, (20, 20), (480, 200), red_bgr, -1)
        # Some white text on the red banner
        cv2.putText(canvas, "IODIZED SALT", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)

        # Actual FSSAI veg symbol on white background portion of package
        draw_fssai_veg_symbol(canvas, (200, 320), size=65)

        result = detect_veg_nonveg_symbol(canvas)

        assert result['detected'] is True
        # Must detect VEGETARIAN, NEVER NON_VEGETARIAN!
        assert result['symbol_type'] == 'VEGETARIAN'
        assert result['confidence'] >= 0.70

    def test_isolated_red_or_brown_blob_without_frame_is_not_nonveg(self):
        """An arbitrary red/brown graphic or text without an enclosing frame must NOT be classified as NON_VEGETARIAN."""
        canvas = create_blank_canvas(300, 300)
        brown_bgr = (20, 45, 120)
        # Just an irregular rectangle/blob without any enclosing square outline
        cv2.rectangle(canvas, (80, 80), (220, 160), brown_bgr, -1)

        result = detect_veg_nonveg_symbol(canvas)

        # Should either not be detected, or have low confidence / UNKNOWN, NEVER confident NON_VEGETARIAN
        if result['detected']:
            assert result['symbol_type'] != 'NON_VEGETARIAN' or result['confidence'] < 0.50

    def test_plain_package_without_symbol_returns_not_detected(self):
        """A package with only black text and white background returns detected=False."""
        canvas = create_blank_canvas(300, 300)
        cv2.putText(canvas, "NET WT: 500g", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)

        result = detect_veg_nonveg_symbol(canvas)
        assert result['detected'] is False or result['symbol_type'] == 'UNKNOWN'

    def test_none_or_empty_image_fails_safely(self):
        """Passing None or zero-size image returns safe default without crash."""
        res_none = detect_veg_nonveg_symbol(None)
        assert res_none['detected'] is False
        assert res_none['symbol_type'] == 'UNKNOWN'

        empty_img = np.zeros((0, 0, 3), dtype=np.uint8)
        res_empty = detect_veg_nonveg_symbol(empty_img)
        assert res_empty['detected'] is False
