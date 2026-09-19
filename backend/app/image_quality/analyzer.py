"""
Main entry point for deterministic Image Quality analysis.
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, Optional

from .schemas import (
    ImageQualityMetric,
    ImageQualityResult,
    ImageQualityStatus,
    InspectionQualitySummary,
    QualityIssueCode,
    IssueSeverity,
    ImageQualityIssue,
)
from .metrics import (
    load_and_orient_analysis_image,
    calculate_sharpness,
    calculate_exposure_stats,
    calculate_contrast,
    calculate_glare_ratio,
    calculate_text_region_metrics,
    check_possible_cropping,
)
from .policy import QualityPolicyConfig, evaluate_image_quality

logger = logging.getLogger(__name__)


def analyze_image_quality(
    image_path_or_bytes: Any,
    image_index: int = 0,
    config: Optional[QualityPolicyConfig] = None,
) -> ImageQualityResult:
    """
    Perform deterministic quality analysis on a single package panel image.
    Never alters original image files on disk.
    """
    started_at = time.perf_counter()
    try:
        pil_img, rgb_array, gray_array, orig_w, orig_h = load_and_orient_analysis_image(image_path_or_bytes)

        # 1. Sharpness / Blur (Laplacian variance)
        blur_score = calculate_sharpness(gray_array)

        # 2. Exposure stats (mean, dark ratio, bright ratio)
        brightness_mean, dark_ratio, bright_ratio = calculate_exposure_stats(gray_array)

        # 3. Contrast (intensity standard deviation)
        contrast_std = calculate_contrast(gray_array)

        # 4. Glare ratio (specular low-texture washed-out reflection patches)
        glare_ratio = calculate_glare_ratio(rgb_array, gray_array)

        # 5. Cropping risk heuristic
        possible_crop = check_possible_cropping(gray_array)

        # 6. Text-Region Readability & Packaging Geometry metrics
        text_stroke_contrast, text_stroke_count, intensity_range = calculate_text_region_metrics(gray_array)
        aspect_ratio = round(max(orig_w, orig_h) / max(1, min(orig_w, orig_h)), 2)

        metrics = ImageQualityMetric(
            blur_score=blur_score,
            brightness_mean=brightness_mean,
            dark_pixel_ratio=dark_ratio,
            bright_pixel_ratio=bright_ratio,
            glare_ratio=glare_ratio,
            contrast_std=contrast_std,
            width=orig_w,
            height=orig_h,
            total_pixels=orig_w * orig_h,
            aspect_ratio=aspect_ratio,
            text_stroke_contrast=text_stroke_contrast,
            text_stroke_count=text_stroke_count,
            intensity_range=intensity_range,
        )

        res = evaluate_image_quality(
            metrics=metrics,
            possible_cropping=possible_crop,
            config=config,
            image_index=image_index,
        )
        res.processing_time_ms = round((time.perf_counter() - started_at) * 1000)

        issue_codes = [iss.code.value for iss in res.issues]
        primary_reason = (
            "; ".join(res.rejection_reasons)
            if res.rejection_reasons
            else ("; ".join(iss.message for iss in res.issues) if res.issues else "OK")
        )
        logger.info(
            "Image %d: status=%s blur_score=%.1f issues=%s reason=%s",
            image_index,
            res.status.value,
            blur_score,
            issue_codes,
            primary_reason,
        )
        return res

    except Exception as exc:
        logger.error("Failed to decode or analyze image %d: %s", image_index, exc)
        elapsed_ms = round((time.perf_counter() - started_at) * 1000)
        return ImageQualityResult(
            image_index=image_index,
            status=ImageQualityStatus.RECAPTURE_REQUIRED,
            quality_score=0.0,
            issues=[
                ImageQualityIssue(
                    code=QualityIssueCode.IMAGE_UNREADABLE,
                    severity=IssueSeverity.ERROR,
                    message=f"Image file cannot be decoded or analyzed: {str(exc)}",
                )
            ],
            rejection_reasons=[f"Image file cannot be decoded or analyzed: {str(exc)}"],
            metrics=ImageQualityMetric(
                blur_score=0.0,
                brightness_mean=0.0,
                dark_pixel_ratio=1.0,
                bright_pixel_ratio=0.0,
                glare_ratio=0.0,
                contrast_std=0.0,
                width=0,
                height=0,
                total_pixels=0,
                aspect_ratio=1.0,
                text_stroke_contrast=0.0,
                text_stroke_count=0,
                intensity_range=0.0,
            ),
            processing_time_ms=elapsed_ms,
        )


def analyze_inspection_images(
    image_paths: List[str],
    config: Optional[QualityPolicyConfig] = None,
) -> InspectionQualitySummary:
    """
    Evaluate multiple package images for an inspection.
    Determines usable panels and case-level summary.
    """
    total_start = time.perf_counter()
    quality_results: List[ImageQualityResult] = []
    accepted = 0
    warning = 0
    rejected = 0
    usable_indices: List[int] = []
    recapture_indices: List[int] = []

    for idx, path in enumerate(image_paths):
        res = analyze_image_quality(path, image_index=idx, config=config)
        quality_results.append(res)
        if res.status == ImageQualityStatus.ACCEPT:
            accepted += 1
            usable_indices.append(idx)
        elif res.status == ImageQualityStatus.WARN:
            warning += 1
            usable_indices.append(idx)
        else:
            rejected += 1
            recapture_indices.append(idx)

    # Determine overall case-level quality status
    if rejected == len(image_paths) and len(image_paths) > 0:
        overall_status = ImageQualityStatus.RECAPTURE_REQUIRED
    elif rejected > 0 or warning > 0:
        overall_status = ImageQualityStatus.WARN
    else:
        overall_status = ImageQualityStatus.ACCEPT

    total_time_ms = round((time.perf_counter() - total_start) * 1000)

    summary = InspectionQualitySummary(
        overall_quality_status=overall_status,
        total_images=len(image_paths),
        accepted_images=accepted,
        warning_images=warning,
        rejected_images=rejected,
        usable_image_indices=usable_indices,
        recapture_image_indices=recapture_indices,
        quality_results=quality_results,
        total_quality_time_ms=total_time_ms,
    )

    logger.info(
        "Inspection quality gate complete: status=%s total=%d accepted=%d warn=%d rejected=%d usable=%s time_ms=%d",
        overall_status.value,
        len(image_paths),
        accepted,
        warning,
        rejected,
        usable_indices,
        total_time_ms,
    )
    return summary
