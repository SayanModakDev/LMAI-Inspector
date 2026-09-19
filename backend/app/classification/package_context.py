from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple


def _evidence_text(raw_text: str, extracted_fields: Dict[str, Any]) -> str:
    values = [raw_text or ""]
    values.extend(
        str(field.get("value", ""))
        for field in (extracted_fields or {}).values()
        if isinstance(field, dict)
    )
    return " ".join(values).lower()


def _match_count(text: str, patterns: Tuple[str, ...]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text, re.IGNORECASE))


def detect_package_context(raw_text: str, extracted_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Detect package type and origin from explicit, package-visible declarations.

    Ambiguous or contradictory evidence remains ``NOT_DETECTED`` rather than being
    converted into a user/default value that could change legal applicability.
    """
    text = _evidence_text(raw_text, extracted_fields or {})

    retail_signals = (
        r"(?<!\bnot\s)\bfor\s+retail\s+sale\b",
        r"\bmaximum\s+retail\s+price\b|\bm\.?\s*r\.?\s*p\.?\b",
        r"\bunit\s+sale\s+price\b",
    )
    wholesale_signals = (
        r"\bnot\s+for\s+retail\s+sale\b",
        r"\bwholesale\b|\bbulk\s+pack\b|\bbulk\s+only\b",
        r"\binstitutional\s+(?:pack|use|sale)\b|\bcommercial\s+(?:pack|use)\b",
        r"\bdistributor(?:s)?\b|\bdealer(?:s)?\b",
    )
    retail_count = _match_count(text, retail_signals)
    wholesale_count = _match_count(text, wholesale_signals)
    if retail_count and not wholesale_count:
        package_type = "RETAIL"
    elif wholesale_count and not retail_count:
        package_type = "WHOLESALE"
    else:
        package_type = "NOT_DETECTED"

    domestic_signals = (
        r"\bmade\s+in\s+india\b",
        r"\bmanufactured\s+in\s+india\b",
        r"\bproduced\s+in\s+india\b",
    )
    imported_signals = (
        r"\bimported\s+by\b|\bimporter\b",
        r"\bcountry\s+of\s+origin\b\s*[:\-]?\s*(?!india\b)[a-z]",
        r"\bmade\s+in\b\s+(?!india\b)[a-z]",
        r"\bmanufactured\s+in\b\s+(?!india\b)[a-z]",
    )
    domestic_count = _match_count(text, domestic_signals)
    imported_count = _match_count(text, imported_signals)
    if domestic_count and not imported_count:
        import_status = "DOMESTIC"
    elif imported_count and not domestic_count:
        import_status = "IMPORTED"
    else:
        import_status = "NOT_DETECTED"

    return {
        "package_type": package_type,
        "import_status": import_status,
        "evidence": {
            "retail_signals": retail_count,
            "wholesale_signals": wholesale_count,
            "domestic_signals": domestic_count,
            "imported_signals": imported_count,
        },
    }