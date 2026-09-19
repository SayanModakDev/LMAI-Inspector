"""
Evaluation policy and decision logic for deterministic Image Quality Gate.
"""

from __future__ import annotations

from typing import List, Optional, Tuple, Any
from .schemas import (
    ImageQualityMetric,
    ImageQualityIssue,
    QualityIssueCode,
    IssueSeverity,
    ImageQualityStatus,
    ImageQualityResult,
)


class QualityPolicyConfig:
    """Configurable thresholds for image quality evaluation."""

    def __init__(
        self,
        blur_warn_threshold: float = 75.0,
        blur_reject_threshold: float = 35.0,
        min_width: int = 120,
        min_height: int = 80,
        min_pixels: int = 40000,
        min_dimension_reject: int = 75,
        dark_warn_ratio: float = 0.60,
        dark_reject_ratio: float = 0.85,
        dark_mean_threshold: float = 45.0,
        overexpose_warn_ratio: float = 0.35,
        overexpose_reject_ratio: float = 0.60,
        glare_warn_ratio: float = 0.05,
        glare_reject_ratio: float = 0.18,
        low_contrast_warn: float = 25.0,
        low_contrast_reject: float = 12.0,
    ):
        self.blur_warn_threshold = blur_warn_threshold
        self.blur_reject_threshold = blur_reject_threshold
        self.min_width = min_width
        self.min_height = min_height
        self.min_pixels = min_pixels
        self.min_dimension_reject = min_dimension_reject
        self.dark_warn_ratio = dark_warn_ratio
        self.dark_reject_ratio = dark_reject_ratio
        self.dark_mean_threshold = dark_mean_threshold
        self.overexpose_warn_ratio = overexpose_warn_ratio
        self.overexpose_reject_ratio = overexpose_reject_ratio
        self.glare_warn_ratio = glare_warn_ratio
        self.glare_reject_ratio = glare_reject_ratio
        self.low_contrast_warn = low_contrast_warn
        self.low_contrast_reject = low_contrast_reject

    @classmethod
    def from_settings(cls, settings: Any) -> "QualityPolicyConfig":
        return cls(
            blur_warn_threshold=float(getattr(settings, "IMAGE_QUALITY_BLUR_WARN_THRESHOLD", 75.0)),
            blur_reject_threshold=float(getattr(settings, "IMAGE_QUALITY_BLUR_REJECT_THRESHOLD", 35.0)),
            min_width=int(getattr(settings, "IMAGE_QUALITY_MIN_WIDTH", 120)),
            min_height=int(getattr(settings, "IMAGE_QUALITY_MIN_HEIGHT", 80)),
            min_pixels=int(getattr(settings, "IMAGE_QUALITY_MIN_PIXELS", 40000)),
            min_dimension_reject=int(getattr(settings, "IMAGE_QUALITY_MIN_DIMENSION_REJECT", 75)),
            dark_warn_ratio=float(getattr(settings, "IMAGE_QUALITY_DARK_WARN_RATIO", 0.60)),
            dark_reject_ratio=float(getattr(settings, "IMAGE_QUALITY_DARK_REJECT_RATIO", 0.85)),
            dark_mean_threshold=float(getattr(settings, "IMAGE_QUALITY_DARK_MEAN_THRESHOLD", 45.0)),
            overexpose_warn_ratio=float(getattr(settings, "IMAGE_QUALITY_OVEREXPOSE_WARN_RATIO", 0.35)),
            overexpose_reject_ratio=float(getattr(settings, "IMAGE_QUALITY_OVEREXPOSE_REJECT_RATIO", 0.60)),
            glare_warn_ratio=float(getattr(settings, "IMAGE_QUALITY_GLARE_WARN_RATIO", 0.05)),
            glare_reject_ratio=float(getattr(settings, "IMAGE_QUALITY_GLARE_REJECT_RATIO", 0.18)),
            low_contrast_warn=float(getattr(settings, "IMAGE_QUALITY_LOW_CONTRAST_WARN", 25.0)),
            low_contrast_reject=float(getattr(settings, "IMAGE_QUALITY_LOW_CONTRAST_REJECT", 12.0)),
        )


def evaluate_image_quality(
    metrics: ImageQualityMetric,
    possible_cropping: bool = False,
    config: Optional[QualityPolicyConfig] = None,
    image_index: int = 0,
) -> ImageQualityResult:
    """
    Evaluate deterministic metrics against the 3-level quality policy:
    ACCEPT, WARN, or RECAPTURE_REQUIRED.
    """
    cfg = config or QualityPolicyConfig()
    issues: List[ImageQualityIssue] = []

    # 1. Blur / Sharpness check
    if metrics.blur_score < cfg.blur_reject_threshold:
        issues.append(
            ImageQualityIssue(
                code=QualityIssueCode.IMAGE_TOO_BLURRY,
                severity=IssueSeverity.ERROR,
                message=f"Image is severely blurred (Laplacian variance {metrics.blur_score} < {cfg.blur_reject_threshold}). Text is likely unreadable.",
                measured_value=metrics.blur_score,
                threshold=cfg.blur_reject_threshold,
            )
        )
    elif metrics.blur_score < cfg.blur_warn_threshold:
        issues.append(
            ImageQualityIssue(
                code=QualityIssueCode.IMAGE_TOO_BLURRY,
                severity=IssueSeverity.WARNING,
                message=f"Image is borderline soft or mildly blurred (Laplacian variance {metrics.blur_score} < {cfg.blur_warn_threshold}). Small declarations may be degraded.",
                measured_value=metrics.blur_score,
                threshold=cfg.blur_warn_threshold,
            )
        )

    # 2. Image Resolution check
    # Hard rejection only for genuinely unreadable tiny crops (< 40,000 pixels or shortest dim < 75px)
    shortest_dim = min(metrics.width, metrics.height)
    if metrics.total_pixels < cfg.min_pixels or shortest_dim < cfg.min_dimension_reject:
        issues.append(
            ImageQualityIssue(
                code=QualityIssueCode.IMAGE_LOW_RESOLUTION,
                severity=IssueSeverity.ERROR,
                message=f"Image resolution {metrics.width}x{metrics.height} ({metrics.total_pixels} px) is below minimum useful threshold for statutory label inspection.",
                measured_value=float(metrics.total_pixels),
                threshold=float(cfg.min_pixels),
            )
        )
    elif shortest_dim < 180 or metrics.total_pixels < 100000:
        # For compact crops or close-ups, only warn if text stroke contrast is not strong
        if metrics.text_stroke_contrast < 30.0:
            issues.append(
                ImageQualityIssue(
                    code=QualityIssueCode.IMAGE_LOW_RESOLUTION,
                    severity=IssueSeverity.WARNING,
                    message=f"Image resolution {metrics.width}x{metrics.height} is relatively compact; fine print declarations may have reduced accuracy.",
                    measured_value=float(metrics.total_pixels),
                    threshold=float(cfg.min_pixels * 2),
                )
            )

    # 3. Underexposure check
    # Avoid false rejections on dark-themed packages: require BOTH high dark ratio AND low mean
    if metrics.dark_pixel_ratio >= cfg.dark_reject_ratio and metrics.brightness_mean < cfg.dark_mean_threshold:
        issues.append(
            ImageQualityIssue(
                code=QualityIssueCode.IMAGE_TOO_DARK,
                severity=IssueSeverity.ERROR,
                message=f"Image is severely underexposed (mean brightness {metrics.brightness_mean}, {round(metrics.dark_pixel_ratio * 100, 1)}% dark pixels). Packaging declarations are obscured in darkness.",
                measured_value=metrics.brightness_mean,
                threshold=cfg.dark_mean_threshold,
            )
        )
    elif metrics.dark_pixel_ratio >= cfg.dark_warn_ratio or metrics.brightness_mean < (cfg.dark_mean_threshold + 10.0):
        # Only warn if contrast is also relatively low
        if metrics.contrast_std < 40.0:
            issues.append(
                ImageQualityIssue(
                    code=QualityIssueCode.IMAGE_TOO_DARK,
                    severity=IssueSeverity.WARNING,
                    message=f"Image is moderately dark (mean brightness {metrics.brightness_mean}). Lighting could be improved.",
                    measured_value=metrics.brightness_mean,
                    threshold=cfg.dark_mean_threshold + 10.0,
                )
            )

    # 4. Overexposure check
    # Do not reject legitimate white packages simply because large background areas are white.
    # Destructive overexposure occurs when printed text and edges are washed out.
    text_is_crisp = metrics.blur_score >= 35.0 and metrics.contrast_std >= 4.0

    if metrics.bright_pixel_ratio >= cfg.overexpose_reject_ratio:
        if not text_is_crisp:
            issues.append(
                ImageQualityIssue(
                    code=QualityIssueCode.IMAGE_OVEREXPOSED,
                    severity=IssueSeverity.ERROR,
                    message=f"Severe overexposure / sensor clipping ({round(metrics.bright_pixel_ratio * 100, 1)}% clipped white pixels) destroying label legibility.",
                    measured_value=metrics.bright_pixel_ratio,
                    threshold=cfg.overexpose_reject_ratio,
                )
            )
    elif metrics.bright_pixel_ratio >= cfg.overexpose_warn_ratio:
        if not text_is_crisp:
            issues.append(
                ImageQualityIssue(
                    code=QualityIssueCode.IMAGE_OVEREXPOSED,
                    severity=IssueSeverity.WARNING,
                    message=f"Moderate overexposure ({round(metrics.bright_pixel_ratio * 100, 1)}% near-white pixels). Portions of the label may be washed out.",
                    measured_value=metrics.bright_pixel_ratio,
                    threshold=cfg.overexpose_warn_ratio,
                )
            )

    # 5. Glare / Specular Reflection check
    if metrics.glare_ratio >= cfg.glare_reject_ratio:
        issues.append(
            ImageQualityIssue(
                code=QualityIssueCode.IMAGE_GLARE,
                severity=IssueSeverity.ERROR,
                message=f"Destructive glare reflection covers {round(metrics.glare_ratio * 100, 1)}% of the package surface, obliterating critical text.",
                measured_value=metrics.glare_ratio,
                threshold=cfg.glare_reject_ratio,
            )
        )
    elif metrics.glare_ratio >= cfg.glare_warn_ratio:
        issues.append(
            ImageQualityIssue(
                code=QualityIssueCode.IMAGE_GLARE,
                severity=IssueSeverity.WARNING,
                message=f"Specular glare reflection detected on {round(metrics.glare_ratio * 100, 1)}% of the package view. Some text may be obscured.",
                measured_value=metrics.glare_ratio,
                threshold=cfg.glare_warn_ratio,
            )
        )

    # 6. Contrast & Text-Region Readability check
    # Check whether readable text stroke transitions exist despite a uniform packaging background
    # (e.g. solid white carton or solid blue label where text occupies a small percentage of area)
    has_readable_text = (
        metrics.text_stroke_contrast >= 25.0
        and metrics.text_stroke_count >= 50
        and metrics.intensity_range >= 50.0
    )

    if metrics.contrast_std <= cfg.low_contrast_reject:
        if has_readable_text:
            # Packaging has a solid or uniform background, but printed text strokes have strong local edge contrast.
            # Do NOT emit a fatal error. If stroke contrast is borderline (< 35), warn only.
            if metrics.text_stroke_contrast < 35.0:
                issues.append(
                    ImageQualityIssue(
                        code=QualityIssueCode.IMAGE_LOW_CONTRAST,
                        severity=IssueSeverity.WARNING,
                        message=f"Image background is uniform (global std {metrics.contrast_std}), but local text stroke contrast is moderate ({metrics.text_stroke_contrast}).",
                        measured_value=metrics.contrast_std,
                        threshold=cfg.low_contrast_reject,
                    )
                )
        else:
            # Genuinely washed-out, low-contrast, unreadable image
            issues.append(
                ImageQualityIssue(
                    code=QualityIssueCode.IMAGE_LOW_CONTRAST,
                    severity=IssueSeverity.ERROR,
                    message=f"Image contrast standard deviation ({metrics.contrast_std}) is critically low and no readable text strokes were detected. Declarations cannot be distinguished.",
                    measured_value=metrics.contrast_std,
                    threshold=cfg.low_contrast_reject,
                )
            )
    elif metrics.contrast_std <= cfg.low_contrast_warn:
        if not has_readable_text and metrics.blur_score < 120.0:
            issues.append(
                ImageQualityIssue(
                    code=QualityIssueCode.IMAGE_LOW_CONTRAST,
                    severity=IssueSeverity.WARNING,
                    message=f"Image contrast ({metrics.contrast_std}) is low, which may decrease OCR character confidence.",
                    measured_value=metrics.contrast_std,
                    threshold=cfg.low_contrast_warn,
                )
            )

    # 7. Cropping Risk check
    if possible_cropping:
        issues.append(
            ImageQualityIssue(
                code=QualityIssueCode.POSSIBLE_CROPPING,
                severity=IssueSeverity.WARNING,
                message="High edge density detected at the image border; package declarations may be partially cropped.",
                measured_value=1.0,
                threshold=0.0,
            )
        )

    # Determine overall status from issue severities
    has_error = any(iss.severity == IssueSeverity.ERROR for iss in issues)
    has_warning = any(iss.severity == IssueSeverity.WARNING for iss in issues)

    if has_error:
        status = ImageQualityStatus.RECAPTURE_REQUIRED
    elif has_warning:
        status = ImageQualityStatus.WARN
    else:
        status = ImageQualityStatus.ACCEPT

    # Calculate composite quality score (0.0 to 1.0)
    score = 1.0
    for iss in issues:
        if iss.severity == IssueSeverity.ERROR:
            score -= 0.40
        elif iss.severity == IssueSeverity.WARNING:
            score -= 0.15

    # Mild penalty for low sharpness if under 120
    if metrics.blur_score < 120.0:
        score -= max(0.0, (120.0 - metrics.blur_score) / 400.0)

    score = round(max(0.0, min(1.0, score)), 2)
    rejection_reasons = [iss.message for iss in issues if iss.severity == IssueSeverity.ERROR]

    return ImageQualityResult(
        image_index=image_index,
        status=status,
        quality_score=score,
        issues=issues,
        metrics=metrics,
        rejection_reasons=rejection_reasons,
    )
