"""
Shared utility functions used across the application.
"""

import os
import uuid
import re
from datetime import datetime, timezone
from typing import Optional


def generate_filename(original_filename: str) -> str:
    """Generate a unique filename preserving the original extension."""
    ext = os.path.splitext(original_filename)[1].lower() if original_filename else ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"):
        ext = ".jpg"
    unique_id = uuid.uuid4().hex[:12]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"scan_{timestamp}_{unique_id}{ext}"


def sanitize_text(text: str) -> str:
    """Clean OCR text: collapse whitespace, strip edges."""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def safe_float(value: str) -> Optional[float]:
    """Attempt to parse a float from a string, return None on failure."""
    if not value:
        return None
    cleaned = re.sub(r'[^\d.]', '', str(value))
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def format_date_for_display(dt: Optional[datetime]) -> str:
    """Format a datetime for display in reports/UI."""
    if dt is None:
        return "N/A"
    return dt.strftime("%d %b %Y, %H:%M")


def ensure_directory(path: str) -> None:
    """Create directory if it does not exist."""
    os.makedirs(path, exist_ok=True)
