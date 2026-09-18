"""
Shared utility functions used across the application.
"""

import os
import uuid
import re
from datetime import datetime, timezone
from typing import Optional


ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/x-ms-bmp",
}


def sanitize_filename(filename: str) -> str:
    """Sanitize original filename to prevent path traversal and unsafe characters.

    Strips directory paths, null bytes, and restricts to safe characters.
    """
    if not filename:
        return "unnamed_upload"
    base = os.path.basename(filename.replace('\\', '/'))
    base = base.replace('\x00', '')
    sanitized = re.sub(r'[^A-Za-z0-9._-]', '_', base)
    sanitized = sanitized.strip('. ')
    if not sanitized:
        sanitized = "unnamed_upload"
    return sanitized[:100]


def detect_image_format_from_bytes(content: bytes) -> Optional[str]:
    """Detect image format by inspecting magic bytes/signatures.

    Supported: JPEG, PNG, WEBP, BMP.
    Returns format string e.g. 'JPEG', 'PNG', 'WEBP', 'BMP', or None if unrecognized.
    """
    if not content or len(content) < 8:
        return None
    # JPEG starts with FF D8 FF
    if content[:3] == b'\xff\xd8\xff':
        return 'JPEG'
    # PNG starts with 89 50 4E 47 0D 0A 1A 0A
    if content[:8] == b'\x89PNG\r\n\x1a\n':
        return 'PNG'
    # WEBP: bytes 0-4 RIFF and bytes 8-12 WEBP
    if len(content) >= 12 and content[:4] == b'RIFF' and content[8:12] == b'WEBP':
        return 'WEBP'
    # BMP starts with BM
    if content[:2] == b'BM':
        return 'BMP'
    return None


def validate_image_content(content: bytes) -> tuple[bool, Optional[str], Optional[str]]:
    """Validate image content using magic bytes and Pillow structural verification.

    Returns (is_valid, detected_format, error_message).
    """
    if not content or len(content) == 0:
        return False, None, "File is empty (0 bytes)."

    magic_format = detect_image_format_from_bytes(content)
    if not magic_format:
        return False, None, "File content does not match any supported image signature (JPEG, PNG, WEBP, BMP)."

    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(content)) as img:
            pil_format = img.format
            if pil_format not in ("JPEG", "PNG", "WEBP", "BMP"):
                return False, pil_format, f"Unsupported image format: '{pil_format}'."
            img.verify()
            return True, pil_format, None
    except Exception as exc:
        return False, magic_format, f"Corrupted or invalid image data: {str(exc)}"


def is_allowed_mime_type(content_type: Optional[str]) -> bool:
    """Check whether declared MIME type is an allowed image format."""
    if not content_type:
        return True
    normalized = content_type.lower().strip().split(';')[0].strip()
    return normalized in ALLOWED_MIME_TYPES


def get_safe_upload_path(upload_dir: str, server_filename: str) -> str:
    """Ensure generated filename resolves strictly within upload_dir."""
    upload_dir_abs = os.path.abspath(upload_dir)
    target_path = os.path.abspath(os.path.join(upload_dir_abs, server_filename))
    if not target_path.startswith(upload_dir_abs + os.path.sep) and target_path != upload_dir_abs:
        raise ValueError(f"Path traversal detected for filename: {server_filename}")
    return target_path


def generate_filename(original_filename: str, detected_format: Optional[str] = None) -> str:
    """Generate a unique secure server-side filename with extension matching validated format."""
    format_to_ext = {
        'JPEG': '.jpg',
        'PNG': '.png',
        'WEBP': '.webp',
        'BMP': '.bmp',
    }
    if detected_format and detected_format.upper() in format_to_ext:
        ext = format_to_ext[detected_format.upper()]
    else:
        sanitized = sanitize_filename(original_filename)
        ext = os.path.splitext(sanitized)[1].lower() if sanitized else ".jpg"
        if ext not in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
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
