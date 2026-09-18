"""
Reusable Context-Aware OCR Cleaning Layer.

Filters out non-content artifacts (image placeholders, repeated noise, isolated punctuation,
and impossible fragments) while preserving legitimate short units, numbers, and currency symbols.
Preserves the complete original raw OCR text and items for audit provenance.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# Reusable regex patterns for non-content artifacts
IMAGE_PLACEHOLDER_RE = re.compile(
    r'^\s*(?:\[IMAGE(?:\s*\d+)?\]|<image(?:\s*\d+)?>|__IMAGE__|\[IMAGE\s*:\s*[^\]]+\])\s*$',
    re.IGNORECASE,
)

INLINE_IMAGE_TAG_RE = re.compile(
    r'\[IMAGE(?:\s*\d+)?\]|<image(?:\s*\d+)?>|__IMAGE__|\[IMAGE\s*:\s*[^\]]+\]',
    re.IGNORECASE,
)

GENERATED_PLACEHOLDER_RE = re.compile(
    r'^\s*(?:\[placeholder[^\]]*\]|undefined|null|\[none\]|\[blank\]|__placeholder__)\s*$',
    re.IGNORECASE,
)

REPEATED_NOISE_RE = re.compile(
    r'^\s*[-.=_~|*#•·—–^]{2,}\s*$',
)

# Legitimate short tokens that must NEVER be deleted during cleaning
LEGITIMATE_SHORT_TOKENS: Set[str] = {
    # Units
    'g', 'gm', 'gms', 'kg', 'kgs', 'mg', 'ml', 'l', 'lt', 'ltr', 'cl',
    'pc', 'pcs', 'tab', 'tabs', 'cap', 'caps', 'oz', 'lb', 'm', 'cm', 'mm', 'n',
    # Currencies
    'rs', 'rs.', '₹', 'inr', 'p', 'paise',
    # Common prefixes / prepositions / abbreviations
    'no', 'no.', 'nos', 'mfd', 'mfg', 'pkd', 'pkg', 'exp', 'mrp', 'lot', 'wt', 'qty',
    'by', 'at', 'for', 'in', 'of', 'on', 'to', 'co', 'is', 'as', 'we', 'us',
}


def is_isolated_punctuation(token: str) -> bool:
    """Check if token consists entirely of punctuation or symbols without alphanumeric characters."""
    stripped = token.strip()
    if not stripped:
        return True
    # If it contains any alphanumeric character or currency symbol (₹), it is not isolated punctuation
    if any(c.isalnum() or c == '₹' for c in stripped):
        return False
    return True


def is_artifact_token(token: str) -> Tuple[bool, Optional[str]]:
    """Determine if an individual OCR token is an artifact."""
    clean = token.strip()
    if not clean:
        return True, "EMPTY_TOKEN"

    lower = clean.lower()
    if lower in LEGITIMATE_SHORT_TOKENS or clean.isdigit():
        return False, None

    if IMAGE_PLACEHOLDER_RE.match(clean):
        return True, "IMAGE_PLACEHOLDER"

    if GENERATED_PLACEHOLDER_RE.match(clean):
        return True, "GENERATED_PLACEHOLDER"

    if REPEATED_NOISE_RE.match(clean):
        return True, "REPEATED_NOISE"

    if is_isolated_punctuation(clean):
        return True, "ISOLATED_PUNCTUATION"

    # Impossible OCR fragments (e.g. unprintable non-ascii control chars or pure replacement chars)
    if all(ord(c) < 32 or c == '\ufffd' for c in clean):
        return True, "IMPOSSIBLE_CONTROL_CHARS"

    return False, None


def clean_ocr_evidence(
    raw_text: str,
    ocr_items: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Clean raw OCR text and bounding-box items into sanitized lines and items.
    
    Returns:
        cleaned_text: Cleaned text string with artifact lines/tokens removed.
        cleaned_items: List of surviving OCR items.
        removed_artifacts: List of removed artifact items with reason for audit trail.
    """
    if not raw_text:
        return "", [], []

    removed_artifacts: List[Dict[str, Any]] = []
    cleaned_items: List[Dict[str, Any]] = []

    # 1. Clean individual OCR bounding-box items if present
    if ocr_items:
        for item in ocr_items:
            item_text = str(item.get("text", "")).strip()
            is_art, reason = is_artifact_token(item_text)
            if is_art:
                removed_artifacts.append({
                    "text": item_text,
                    "bbox": item.get("bbox"),
                    "confidence": item.get("confidence"),
                    "reason": reason,
                    "image_index": item.get("image_index"),
                })
            else:
                cleaned_items.append(item)

    # 2. Clean line by line
    raw_lines = raw_text.replace('\r', '\n').split('\n')
    surviving_lines: List[str] = []

    for line_idx, line in enumerate(raw_lines):
        line_clean = line.strip()
        if not line_clean:
            continue

        # Strip inline image tags if embedded inside legitimate lines
        line_stripped = INLINE_IMAGE_TAG_RE.sub('', line_clean).strip()
        if not line_stripped:
            removed_artifacts.append({
                "text": line_clean,
                "reason": "IMAGE_PLACEHOLDER_LINE",
                "line_index": line_idx,
            })
            continue

        is_art, reason = is_artifact_token(line_stripped)
        if is_art:
            removed_artifacts.append({
                "text": line_clean,
                "reason": reason,
                "line_index": line_idx,
            })
            continue

        surviving_lines.append(line_stripped)

    cleaned_text = "\n".join(surviving_lines)
    return cleaned_text, cleaned_items, removed_artifacts
