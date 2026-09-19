"""
Field-specific deterministic normalizers for benchmark ground-truth comparison.
Provides conservative, rule-based standardizations without using LLMs.
"""

import re
import unicodedata
from typing import Any, List, Optional, Tuple


def clean_text_basic(text: Optional[str]) -> str:
    """Normalize unicode, lowercase, collapse whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
    text = text.lower()
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# 1. MRP Normalization
# ---------------------------------------------------------------------------

def normalize_mrp(value: Optional[str]) -> Optional[str]:
    """
    Standardize currency string to canonical decimal format (e.g. '50.00').
    Strips currency symbols (₹, Rs, Rs., INR, /-), whitespace, and tax disclaimers.
    """
    if not value:
        return None
    cleaned = clean_text_basic(value)
    # Strip prefixes and suffixes
    cleaned = re.sub(r"\b(m\.?r\.?p\.?|incl(usive)?\.?\s+of\s+all\s+taxes|taxes)\b", "", cleaned)
    cleaned = re.sub(r"(₹|rs\.?|inr|/-|/)", " ", cleaned)
    # Extract numeric price (e.g. 50, 50.00, 199.50)
    match = re.search(r"(\d+(?:\.\d{1,2})?)", cleaned)
    if match:
        try:
            num = float(match.group(1))
            return f"{num:.2f}"
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# 2. Net Quantity Normalization
# ---------------------------------------------------------------------------

_UNIT_MAP = {
    "g": "g", "gm": "g", "gms": "g", "gram": "g", "grams": "g", "g.": "g",
    "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg", "kg.": "kg",
    "ml": "ml", "mls": "ml", "millilitre": "ml", "millilitres": "ml", "ml.": "ml",
    "l": "l", "ltr": "l", "ltrs": "l", "litre": "l", "litres": "l", "l.": "l",
    "n": "N", "u": "N", "unit": "N", "units": "N", "pcs": "N", "pieces": "N", "number": "N", "count": "N",
    "m": "m", "metre": "m", "meters": "m", "cm": "cm", "mm": "mm",
}

def normalize_net_quantity(value: Optional[str]) -> Optional[str]:
    """
    Standardize net quantity string into canonical '<number> <canonical_unit>'.
    Preserves multipack notation (e.g. '10 x 50 g').
    """
    if not value:
        return None
    cleaned = clean_text_basic(value)
    # Strip field labels
    cleaned = re.sub(r"\b(net\s+(?:wt|weight|qty|quantity|vol|volume|contents?))\b", "", cleaned).strip(" :-")

    # Check for multipack e.g. 10 x 50 g or 10N x 50g
    multi_match = re.match(
        r"^(\d+)\s*(?:n|u|units?)?\s*[\*xX]\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)$",
        cleaned,
    )
    if multi_match:
        count, sub_val, sub_unit = multi_match.groups()
        canon_unit = _UNIT_MAP.get(sub_unit.lower(), sub_unit.lower())
        sub_num = float(sub_val)
        sub_num_str = f"{int(sub_num)}" if sub_num.is_integer() else f"{sub_num}"
        return f"{count} x {sub_num_str} {canon_unit}"

    # Single quantity pattern e.g. '500 g', '500g', '1.5 kg'
    single_match = re.search(r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)", cleaned)
    if single_match:
        val_str, unit_str = single_match.groups()
        canon_unit = _UNIT_MAP.get(unit_str.lower(), unit_str.lower())
        num = float(val_str)
        num_str = f"{int(num)}" if num.is_integer() else f"{num}"
        return f"{num_str} {canon_unit}"

    return cleaned.strip()


# ---------------------------------------------------------------------------
# 3. Date Normalization
# ---------------------------------------------------------------------------

_MONTH_NAMES = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

def normalize_date(value: Optional[str]) -> Optional[str]:
    """
    Standardize dates to MM/YYYY or DD/MM/YYYY.
    Expands 2-digit years MM/YY -> MM/YYYY deterministically (e.g. 05/24 -> 05/2024).
    """
    if not value:
        return None
    cleaned = clean_text_basic(value)
    # Strip label prefixes
    cleaned = re.sub(
        r"\b(mfg\s+date|date\s+of\s+(?:mfg|mfd|packing|manufacture)|mfg|mfd|pkd|pkg|date|best\s+before|expiry|exp|use\s+by|use\s+before)\b",
        "",
        cleaned,
    ).strip(" :-")

    # Replace word months (e.g. May/2024, May 24, 15-Aug-2024)
    for m_word, m_num in _MONTH_NAMES.items():
        cleaned = re.sub(rf"\b{m_word}[a-z]*\b", m_num, cleaned)

    # 1. DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    dmy_match = re.search(r"\b([0-2]?[1-9]|3[01])[\/\-\.](0?[1-9]|1[0-2])[\/\-\.]((?:19|20)\d{2})\b", cleaned)
    if dmy_match:
        d, m, y = dmy_match.groups()
        return f"{int(d):02d}/{int(m):02d}/{y}"

    # 2. DD/MM/YY -> DD/MM/20YY
    dmy2_match = re.search(r"\b([0-2]?[1-9]|3[01])[\/\-\.](0?[1-9]|1[0-2])[\/\-\.](\d{2})\b", cleaned)
    if dmy2_match:
        d, m, y2 = dmy2_match.groups()
        y = f"20{y2}" if int(y2) <= 50 else f"19{y2}"
        return f"{int(d):02d}/{int(m):02d}/{y}"

    # 3. MM/YYYY or MM-YYYY or MM.YYYY or MM YYYY
    my_match = re.search(r"\b(0?[1-9]|1[0-2])[\/\-\.\s]((?:19|20)\d{2})\b", cleaned)
    if my_match:
        m, y = my_match.groups()
        return f"{int(m):02d}/{y}"

    # 4. MM/YY -> MM/20YY (with / - . or space)
    my2_match = re.search(r"\b(0?[1-9]|1[0-2])[\/\-\.\s](\d{2})\b", cleaned)
    if my2_match:
        m, y2 = my2_match.groups()
        y = f"20{y2}" if int(y2) <= 50 else f"19{y2}"
        return f"{int(m):02d}/{y}"

    # 5. Period duration e.g. "12 months from manufacture"
    dur_match = re.search(r"(\d+)\s*months?", cleaned)
    if dur_match:
        return f"{dur_match.group(1)} months"

    return cleaned.strip()


# ---------------------------------------------------------------------------
# 4. Names & Entity Normalization
# ---------------------------------------------------------------------------

_COMPANY_REPLACEMENTS = [
    (r"\bprivate\s+limited\b", "pvt ltd"),
    (r"\bpvt\.?\s*ltd\.?\b", "pvt ltd"),
    (r"\blimited\b", "ltd"),
    (r"\bltd\.?\b", "ltd"),
    (r"\bcorporation\b", "corp"),
    (r"\bcompany\b", "co"),
    (r"\band\b", "&"),
    (r"\bmanufactured\s+by\b", ""),
    (r"\bmfd\.?\s*by\b", ""),
    (r"\bmarketed\s+by\b", ""),
    (r"\bpacked\s+by\b", ""),
    (r"\bpkd\.?\s*by\b", ""),
    (r"\bimported\s+by\b", ""),
]

def normalize_entity_name(value: Optional[str]) -> Optional[str]:
    """
    Standardize corporate / brand names:
    - Lowercase and collapse spaces
    - Standardize company legal types (Pvt Ltd, Ltd, etc.)
    - Strip prefix labels (Manufactured by, etc.)
    """
    if not value:
        return None
    cleaned = clean_text_basic(value)
    for pattern, repl in _COMPANY_REPLACEMENTS:
        cleaned = re.sub(pattern, repl, cleaned)
    # Remove excessive punctuation
    cleaned = re.sub(r"[^\w\s&]", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


# ---------------------------------------------------------------------------
# 5. Address Normalization
# ---------------------------------------------------------------------------

def normalize_address(value: Optional[str]) -> Optional[str]:
    """
    Standardize address string:
    - Lowercase, collapse spaces
    - Normalize punctuation
    - Preserves pin code, building, locality words without falsely equating different locations.
    """
    if not value:
        return None
    cleaned = clean_text_basic(value)
    # Strip address labels
    cleaned = re.sub(r"\b(address|factory|works|registered\s+office|at:?)\b", "", cleaned)
    # Standardize abbreviations
    cleaned = re.sub(r"\bplot\s+no\.?\b", "plot", cleaned)
    cleaned = re.sub(r"\bindustrial\s+area\b", "ind area", cleaned)
    cleaned = re.sub(r"\bphase\s+([0-9ivx]+)\b", r"phase \1", cleaned)
    cleaned = re.sub(r"\bdist\.?\b", "district", cleaned)
    # Normalize punctuation to spaces
    cleaned = re.sub(r"[,;:\.\-\/]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


# ---------------------------------------------------------------------------
# 6. Strict Numeric Normalization (FSSAI, Barcode, Batch, Phone)
# ---------------------------------------------------------------------------

def normalize_strict_numeric(value: Optional[str]) -> Optional[str]:
    """
    Strict preservation of identifiers. Strips harmless delimiter punctuation only.
    """
    if not value:
        return None
    cleaned = clean_text_basic(value)
    # Strip common label prefixes
    cleaned = re.sub(r"\b(fssai\s+(?:lic\.?\s*(?:no\.?)?)?|lic(?:ence)?\s*no\.?|b\.?\s*no\.?|batch\s*no\.?|lot\s*no\.?)\b", "", cleaned)
    cleaned = cleaned.strip(" :-#")
    # For FSSAI / barcodes, remove all internal spaces/hyphens
    if re.fullmatch(r"[\d\s\-]+", cleaned):
        return re.sub(r"[\s\-]+", "", cleaned)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Master Normalizer & Value Comparator
# ---------------------------------------------------------------------------

def normalize_declaration_value(field_name: str, value: Optional[str]) -> Optional[str]:
    """
    Dispatch declaration value normalization based on canonical field type.
    """
    if value is None:
        return None
    field = (field_name or "").upper().strip()

    if field in ("MRP", "UNIT_SALE_PRICE"):
        return normalize_mrp(value)
    if field in ("DECLARED_NET_QUANTITY", "NET_QUANTITY", "SERVING_SIZE"):
        return normalize_net_quantity(value)
    if any(k in field for k in ("ADDRESS", "LOCATION", "PREMISES")):
        return normalize_address(value)
    if any(k in field for k in ("NAME", "BRAND", "PACKER", "MARKETER", "IMPORTER")):
        return normalize_entity_name(value)
    if any(k in field for k in ("DATE", "EXPIRY", "BEST_BEFORE", "USE_BEFORE", "USE_BY")) or field in (
        "MONTH_YEAR_MANUFACTURE", "MANUFACTURE_DATE", "PACKING_DATE"
    ):
        return normalize_date(value)
    if field in ("FSSAI_LICENSE", "BATCH_NUMBER", "BARCODE"):
        return normalize_strict_numeric(value)
    if field == "VEG_NONVEG_SYMBOL":
        clean_v = clean_text_basic(value)
        if "non" in clean_v:
            return "NON_VEGETARIAN"
        if "veg" in clean_v:
            return "VEGETARIAN"
        return clean_v.upper()

    return clean_text_basic(value)



def compare_declaration_values(
    field_name: str,
    expected_value: Optional[str],
    predicted_value: Optional[str],
    aliases: Optional[List[str]] = None,
) -> Tuple[bool, bool, Optional[str], Optional[str]]:
    """
    Compare expected vs predicted declaration value.

    Returns:
        (exact_match: bool, normalized_match: bool, expected_norm: Optional[str], predicted_norm: Optional[str])
    """
    if expected_value is None and predicted_value is None:
        return True, True, None, None
    if expected_value is None or predicted_value is None:
        exp_n = normalize_declaration_value(field_name, expected_value) if expected_value else None
        pred_n = normalize_declaration_value(field_name, predicted_value) if predicted_value else None
        return False, False, exp_n, pred_n

    raw_exp = str(expected_value).strip()
    raw_pred = str(predicted_value).strip()
    exact_match = (raw_exp == raw_pred)

    norm_exp = normalize_declaration_value(field_name, expected_value)
    norm_pred = normalize_declaration_value(field_name, predicted_value)

    if norm_exp and norm_pred and norm_exp == norm_pred:
        return exact_match, True, norm_exp, norm_pred

    # Check aliases if specified
    if aliases:
        for alias in aliases:
            if raw_pred == alias.strip():
                return True, True, norm_exp, norm_pred
            norm_alias = normalize_declaration_value(field_name, alias)
            if norm_alias and norm_pred and norm_alias == norm_pred:
                return exact_match, True, norm_exp, norm_pred

    return exact_match, False, norm_exp, norm_pred
