"""
Pydantic schemas and enums for deterministic Image Quality evaluation.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ImageQualityStatus(str, Enum):
    """Quality status for an image panel.

    Note: We strictly do NOT use PASS / FAIL as those are reserved for regulatory compliance.
    """
    ACCEPT = "ACCEPT"
    WARN = "WARN"
    RECAPTURE_REQUIRED = "RECAPTURE_REQUIRED"


class IssueSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class QualityIssueCode(str, Enum):
    """Stable, machine-readable issue codes for quality defects."""
    IMAGE_TOO_BLURRY = "IMAGE_TOO_BLURRY"
    IMAGE_LOW_RESOLUTION = "IMAGE_LOW_RESOLUTION"
    IMAGE_TOO_DARK = "IMAGE_TOO_DARK"
    IMAGE_OVEREXPOSED = "IMAGE_OVEREXPOSED"
    IMAGE_GLARE = "IMAGE_GLARE"
    IMAGE_LOW_CONTRAST = "IMAGE_LOW_CONTRAST"
    POSSIBLE_CROPPING = "POSSIBLE_CROPPING"
    IMAGE_UNREADABLE = "IMAGE_UNREADABLE"


class ImageQualityIssue(BaseModel):
    """Structured, auditable image quality issue."""
    code: QualityIssueCode
    severity: IssueSeverity
    message: str
    measured_value: Optional[float] = None
    threshold: Optional[float] = None


class ImageQualityMetric(BaseModel):
    """Raw deterministic metrics measured on an image."""
    blur_score: float = Field(..., description="Laplacian variance sharpness metric")
    brightness_mean: float = Field(..., description="Mean grayscale intensity [0-255]")
    dark_pixel_ratio: float = Field(..., description="Fraction of pixels below dark intensity threshold")
    bright_pixel_ratio: float = Field(..., description="Fraction of pixels above bright intensity threshold")
    glare_ratio: float = Field(..., description="Fraction of pixels in high-luminance low-texture specular regions")
    contrast_std: float = Field(..., description="Standard deviation of luminance intensity")
    width: int = Field(..., description="Original image width in pixels")
    height: int = Field(..., description="Original image height in pixels")
    total_pixels: int = Field(..., description="Total pixel count (width * height)")
    aspect_ratio: float = Field(default=1.0, description="Aspect ratio (max_dim / min_dim)")
    text_stroke_contrast: float = Field(default=0.0, description="Local contrast of detected text stroke edges")
    text_stroke_count: int = Field(default=0, description="Count of detected text stroke transition pixels")
    intensity_range: float = Field(default=0.0, description="Peak-to-peak intensity dynamic range")


class ImageQualityResult(BaseModel):
    """Quality evaluation for a single package panel image."""
    image_index: int = 0
    status: ImageQualityStatus = ImageQualityStatus.ACCEPT
    quality_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Composite heuristic score [0.0 - 1.0]")
    issues: List[ImageQualityIssue] = Field(default_factory=list)
    metrics: Optional[ImageQualityMetric] = None
    rejection_reasons: List[str] = Field(default_factory=list, description="Explicit reasons if rejected")
    processing_time_ms: int = 0


class InspectionQualitySummary(BaseModel):
    """Multi-image case-level quality summary for an inspection."""
    overall_quality_status: ImageQualityStatus = ImageQualityStatus.ACCEPT
    total_images: int = 0
    accepted_images: int = 0
    warning_images: int = 0
    rejected_images: int = 0
    usable_image_indices: List[int] = Field(default_factory=list)
    recapture_image_indices: List[int] = Field(default_factory=list)
    quality_results: List[ImageQualityResult] = Field(default_factory=list)
    total_quality_time_ms: int = 0
