"""
Application configuration loaded from environment variables.
Uses pydantic-settings for validation and type safety.
"""

import os
from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class Settings(BaseSettings):
    """Application settings — loaded from .env file or environment variables."""

    # Application
    APP_NAME: str = "LMAI Inspector"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    PORT: int = 8000

    # Database
    DATABASE_ENABLED: bool = False
    DATABASE_URL: str = "mysql+pymysql://root:password@localhost:3306/legal_metrology_db"

    # CORS & Networking
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: str = ""
    PUBLIC_BASE_URL: str = ""

    # File paths
    UPLOAD_DIR: str = os.path.join(PROJECT_ROOT, "backend", "uploads")
    REPORT_DIR: str = os.path.join(PROJECT_ROOT, "backend", "generated_reports")

    # OCR settings
    OCR_LANG: str = "en"
    OCR_CONFIDENCE_THRESHOLD: float = 0.5

    # Category classification
    CATEGORY_CONFIDENCE_THRESHOLD: float = 0.6

    # Security
    SECRET_KEY: str = "change-this-to-a-random-secret-key"

    # Gemini LLM Semantic Evidence Resolver
    GEMINI_ENABLED: bool = True
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_FALLBACK_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_TIMEOUT_SECONDS: int = 20
    GEMINI_MIN_CONFIDENCE: float = 0.80
    GEMINI_AUTO_SCOPE: bool = True

    # Memory & Concurrency Optimization (Production Stability)
    MAX_OCR_IMAGE_DIMENSION: int = 1536
    MAX_IMAGES_PER_INSPECTION: int = 8
    OCR_CONCURRENCY: int = 1
    PADDLE_CPU_THREADS: int = 1

    # Automatic Image Quality Gate
    IMAGE_QUALITY_GATE_ENABLED: bool = True
    IMAGE_QUALITY_BLUR_WARN_THRESHOLD: float = 75.0
    IMAGE_QUALITY_BLUR_REJECT_THRESHOLD: float = 35.0
    IMAGE_QUALITY_MIN_WIDTH: int = 120
    IMAGE_QUALITY_MIN_HEIGHT: int = 80
    IMAGE_QUALITY_MIN_PIXELS: int = 40000
    IMAGE_QUALITY_MIN_DIMENSION_REJECT: int = 75
    IMAGE_QUALITY_DARK_WARN_RATIO: float = 0.60
    IMAGE_QUALITY_DARK_REJECT_RATIO: float = 0.85
    IMAGE_QUALITY_DARK_MEAN_THRESHOLD: float = 45.0
    IMAGE_QUALITY_OVEREXPOSE_WARN_RATIO: float = 0.35
    IMAGE_QUALITY_OVEREXPOSE_REJECT_RATIO: float = 0.60
    IMAGE_QUALITY_GLARE_WARN_RATIO: float = 0.05
    IMAGE_QUALITY_GLARE_REJECT_RATIO: float = 0.18
    IMAGE_QUALITY_LOW_CONTRAST_WARN: float = 25.0
    IMAGE_QUALITY_LOW_CONTRAST_REJECT: float = 12.0

    # Upload Hardening & Constraints
    MAX_UPLOAD_SIZE_MB: int = 15
    MAX_UPLOAD_SIZE_BYTES: int = 15 * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS: set = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    ALLOWED_IMAGE_MIME_TYPES: set = {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/bmp",
        "image/x-ms-bmp",
    }

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug_mode(cls, value):
        """Accept conventional deployment labels without preventing startup."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod", "off", "no"}:
                return False
            if normalized in {"development", "dev", "debug", "on", "yes"}:
                return True
        return value

    # Rule matrix path (relative to project root)
    RULE_MATRIX_PATH: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "data",
        "rule_matrix.json",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()


settings = get_settings()
