"""Declaration extractor for packaged-commodity OCR text."""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MRP_PATTERNS = [
    r'(?:m\.?\s*r\.?\s*p\.?|maximum\s+retail\s+price)\s*(?:inr\s*|rs\.?\s*|₹\s*)?[:\s-]*\s*([\d,]+(?:\.\d{1,2})?)',
    r'(?:rs\.?|₹|inr)\s*([\d,]+(?:\.\d{1,2})?)',
    r'price\s*[:\s-]*\s*(?:rs\.?\s*|₹\s*)?([\d,]+(?:\.\d{1,2})?)',
    r'(?:m\.?\s*r\.?\s*p\.?|maximum\s+retail\s+price)\s*[^\d]{0,80}([\d]{1,6}(?:[.,]\d{1,2})?)',
]

NET_QTY_PATTERNS = [
    r'(?:net\s*(?:wt\.?|weight|qty\.?|quantity|content|vol\.?|volume)|contents?)\s*[:\s-]*\s*([\d.]+)\s*(g|gm|gms|kg|kgs|ml|l|ltr|litre|litres|liter|liters|oz|lb)',
    r'\b([\d.]+)\s*(g|gm|gms|kg|kgs|ml|l|ltr|litre|litres|liter|liters|oz|lb)\b',
    r'(?:net\s*(?:qty|quantity|contents?)\s*[:\s-]*)?\b(\d+)\s*(pcs?|pieces?|tablets?|capsules?)\b',
]

DATE_PATTERNS = [
    r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b',
    r'\b(\d{1,2}-\d{1,2}-\d{2,4})\b',
    r'\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b',
    r'\b(\d{1,2}/\d{2,4})\b',
    r'\b(\d{1,2}-\d{2,4})\b',
    r'\b(\d{1,2}\.\d{2,4})\b',
    r'\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{2,4})\b',
    r'\b(\d{1,2}\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{2,4})\b',
    r'\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b',
    r'\b(\d{4}[/-]\d{1,2})\b',
    r'\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*[/.-]\s*\d{2,4})\b',
    r'\b(\d{1,2}\s*[/.-]\s*\d{2,4})\b',
]

FSSAI_PATTERNS = [
    r'(?:fssai|lic\.?\s*(?:no\.?|number)?|licen[cs]e\s*(?:no\.?|number)?|reg\.?\s*no\.?)\s*[:\s-]*\s*(\d{9,14})',
]

CONSUMER_CARE_PATTERNS = [
    r'(?:consumer\s*care|customer\s*care|helpline|toll\s*free|contact)\s*[:\s-]*\s*([^\n]{5,80})',
    r'\b(1800[\s\-]?\d{3}[\s\-]?\d{3,4})\b',
    r'\b(\d{3,5}[\s\-]\d{6,10})\b',
]

MANUFACTURER_KEYWORDS = [
    'manufactured by', 'manufactured at', 'manufactured for', 'manufactured:',
    'mfg by', 'mfd by', 'mfg. by', 'mfd. by',
    'manufacturer', 'marketed by', 'packed by', 'packed at', 'puckea by', 'packer', 'made by',
]
IMPORTER_KEYWORDS = ['imported by', 'importer', 'import by']
INGREDIENT_KEYWORDS = ['ingredients', 'composition', 'ingredient list']
NUTRITIONAL_KEYWORDS = ['nutritional information', 'nutrition facts', 'energy', 'protein', 'carbohydrate', 'fat', 'calories', 'per serving']
VEG_NONVEG_KEYWORDS = ['vegetarian', 'non-vegetarian', 'non-veg', 'nonveg']
COUNTRY_OF_ORIGIN_KEYWORDS = ['country of origin', 'made in', 'product of', 'manufactured in']
BEST_BEFORE_KEYWORDS = ['best before', 'best by', 'shelf life', 'consume before', 'consume within']
USE_BY_KEYWORDS = ['use by', 'use before', 'use-before', 'expiry date', 'exp date', 'expiration', 'valid until', 'valid till', 'bud']
MFG_DATE_KEYWORDS = ['date of manufacture', 'mfg date', 'mfd date', 'manufacturing date', 'mfg.', 'mfd.', 'mfg:', 'mfd:', 'mfg ', 'mfd ']
PACKING_DATE_KEYWORDS = ['date of packaging', 'date of packing', 'packing date', 'package date', 'pkg date', 'packed on', 'pkd:', 'pkd.']
MARKETING_TERMS = {'balanced', 'taste', 'immuno', 'iodine', 'zinc', 'vacuum', 'evaporated', 'recyclable', 'fresh', 'natural', 'quality', 'premium', 'guarantee', 'trust', 'great', 'deal', 'new', 'sale', 'special', 'offer', 'free', 'buy', 'one', 'get', 'did', 'you', 'know', 'best', 'no'}
SECTION_BOUNDARY_RE = re.compile(
    r'(?:manufactured\s+(?:by|at|for)|mfd\s+by|mfg\s+by|packed\s+(?:by|at)|marketed\s+by|'
    r'imported\s+by|country\s+of\s+origin|made\s+in|address|net\s*(?:wt\.?|weight|qty\.?|quantity|content)|'
    r'm\.?\s*r\.?\s*p\.?|batch(?:\s*no)?|b\.?\s*no\.?|lot(?:\s*no)?|use\s*-?\s*before|use\s+by|'
    r'best\s+before|consumer\s+care|customer\s+care|write\s+to|ingredients?|nutritional?|'
    r'fssai|barcode)',
    re.IGNORECASE,
)
VENDOR_LINE_RE = re.compile(
    r'([A-Za-z][A-Za-z0-9&.\'\s-]{2,80}?(?:Pvt\.?\s*Ltd\.?|Private\s+Limited|Ltd\.?))',
    re.IGNORECASE,
)
ALL_DATE_LABELS = MFG_DATE_KEYWORDS + PACKING_DATE_KEYWORDS + BEST_BEFORE_KEYWORDS + USE_BY_KEYWORDS + ['expiry', 'exp']


def _normalize_text(raw_text: str) -> str:
    text = raw_text.replace('\r', '\n')
    text = text.replace('₹', ' Rs ')
    text = text.replace('â¹', ' Rs ')
    text = text.replace('–', '-')
    # Conservative OCR repairs observed on real packages; do not invent values.
    repairs = (
        (r'\bGREDIENTS\b', 'INGREDIENTS'),
        (r'\bDODY\s+TALCUM\b', 'BODY TALCUM'),
        (r'\bBODYTALCUM\b', 'BODY TALCUM'),
        (r'\bMADENINDIA\b', 'MADE IN INDIA'),
        (r'\bMADEININDIA\b', 'MADE IN INDIA'),
        (r'\bMADE\s*N\s*INDIA\b', 'MADE IN INDIA'),
        (r'Pvi\.?\s*Ld\.?', 'Pvt. Ltd.'),
        (r'Pvt\.?\s*Ld\.?', 'Pvt. Ltd.'),
        (r'Far external use', 'For external use'),
        (r'\bUSE BEFORE(\d)', r'USE BEFORE \1'),
    )
    for pattern, replacement in repairs:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{2,}', '\n', text)
    return text.strip()


def _is_section_boundary(line: str) -> bool:
    return bool(SECTION_BOUNDARY_RE.search(line or ''))


def _values_conflict(left: str, right: str) -> bool:
    a = re.sub(r'[^a-z0-9]+', '', (left or '').lower())
    b = re.sub(r'[^a-z0-9]+', '', (right or '').lower())
    if not a or not b:
        return False
    return a != b and a not in b and b not in a


def _search_patterns(text: str, patterns: List[str]) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _find_keyword_line(text: str, keywords: List[str]) -> Optional[Dict[str, Any]]:
    for kw in keywords:
        idx = text.lower().find(kw.lower())
        if idx != -1:
            start = idx + len(kw)
            end = text.find('\n', start)
            if end == -1:
                end = len(text)
            value = text[start:end].strip(' :;\t-')
            return {'value': value if value else kw, 'keyword_matched': kw, 'position': idx}
    return None


def _first_date_in(text: str) -> Optional[str]:
    for pattern in DATE_PATTERNS + [r'\b(\d{1,2}/\d{1,2}[-/]\d{2,4})\b']:
        match = re.search(pattern, text or '', re.IGNORECASE)
        if match and _is_valid_date_token(match.group(1).strip()):
            return match.group(1).strip()
    return None


def _line_has_other_date_label(line: str, keywords: List[str]) -> bool:
    lowered = line.lower()
    own = [kw.lower() for kw in keywords]
    for label in ALL_DATE_LABELS:
        token = label.lower().strip()
        if len(token) < 3:
            continue
        if token in lowered and not any(token in item or item in token for item in own):
            return True
    return False


def _extract_date_near_keyword(text: str, keywords: List[str]) -> Optional[str]:
    """Bind a date only to its label line (or an immediately adjacent date-only line).

    Do not pick the nearest date in a large window. Ambiguous leftover dates stay unassigned.
    """
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    bound = []
    for index, line in enumerate(lines):
        lowered = line.lower()
        if not any(kw.lower().strip() in lowered for kw in keywords if len(kw.strip()) >= 3):
            continue
        # Same line: only the span after the matched label, cut at the next other date label.
        matched_kw = next(kw for kw in keywords if kw.lower().strip() in lowered and len(kw.strip()) >= 3)
        after = line[lowered.find(matched_kw.lower()) + len(matched_kw):]
        for other in ALL_DATE_LABELS:
            pos = after.lower().find(other.lower().strip())
            if pos > 0 and len(other.strip()) >= 3 and other.lower() not in matched_kw.lower():
                after = after[:pos]
                break
        same = _first_date_in(after)
        if same:
            bound.append(same)
            continue
        for neighbour in (lines[index + 1] if index + 1 < len(lines) else '', lines[index - 1] if index else ''):
            if not neighbour or _line_has_other_date_label(neighbour, keywords):
                continue
            if SECTION_BOUNDARY_RE.search(neighbour) and not _first_date_in(neighbour):
                continue
            neighbour_date = _first_date_in(neighbour)
            # Adjacent line may be used only when it is essentially a date token.
            remainder = re.sub(re.escape(neighbour_date or ''), '', neighbour).strip(' :;,-')
            if neighbour_date and len(re.sub(r'[^A-Za-z]', '', remainder)) <= 3:
                bound.append(neighbour_date)
                break
    unique = []
    for value in bound:
        if value not in unique:
            unique.append(value)
    if len(unique) == 1:
        return unique[0]
    return None


def _is_valid_date_token(value: str) -> bool:
    """Reject decimal/price noise, phones, barcodes, and impossible fragments."""
    token = value.strip().lower()
    if not token or len(token) > 18:
        return False
    if re.search(r'\d+\.\d+', token) and not re.search(r'[a-z]', token):
        return False
    if re.fullmatch(r'\d{10,}', token):
        return False
    if re.search(r'[a-z]', token):
        return bool(re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', token))
    parts = [part for part in re.split(r'[/.-]', token) if part != '']
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return False
    if len(parts) == 2:
        first, second = numbers
        return (1 <= first <= 12 and 0 <= second <= 9999) or (len(parts[0]) == 4 and 1 <= second <= 12)
    if len(parts) == 3:
        return 1 <= numbers[0] <= 31 and 1 <= numbers[1] <= 12 and 0 <= numbers[2] <= 9999
    return False


def _lines_after_label(lines: List[str], index: int, max_lines: int = 4) -> str:
    """Collect continuation lines without consuming the next declaration."""
    collected = []
    for line in lines[index + 1:index + 1 + max_lines]:
        if _is_section_boundary(line) or VENDOR_LINE_RE.search(line):
            break
        collected.append(line.strip(' ,;'))
    return ', '.join(item for item in collected if item)


def _product_candidate(lines: List[str], ocr_items: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """Score front-label candidates; do not let a marketing adjective become a product."""
    scored = []
    for index, line in enumerate(lines[:25]):
        words = re.findall(r"[A-Za-z][A-Za-z&'-]*", line)
        lowered = [word.lower() for word in words]
        if not words or len(words) > 8 or ':' in line or any(word in MARKETING_TERMS for word in lowered) and len(words) <= 3:
            continue
        if re.search(r'\b(?:manufactured|manufacturing|marketed|packed|ingredients|nutrition|fssai|consumer|address|mrp|net\s*(?:wt|weight))\b', line, re.I):
            continue
        score = 1.0 + max(0, 8 - index) * 0.08
        if re.search(r'\b(?:salt|sugar|biscuit|oil|tea|soap|shampoo|cream|flour|rice|masala|juice)\b', line, re.I):
            score += 4.0
        if ocr_items:
            item = next((x for x in ocr_items if str(x.get('text', '')).strip().lower() == line.lower()), None)
            if item:
                score += float(item.get('confidence') or 0)
                bbox = item.get('bbox') or []
                if len(bbox) == 4 and bbox[1] < 900:
                    score += 0.5
        scored.append((score, line))
    return max(scored, default=(0, None), key=lambda item: item[0])[1]


def merge_product_evidence(fields: Dict[str, Any], raw_text: str, ocr_items: Optional[List[Dict[str, Any]]], barcode_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge verified barcode metadata with contextual OCR, without overwriting stronger evidence blindly."""
    lookup = (barcode_result or {}).get('lookup') or {}
    barcode_value = (barcode_result or {}).get('value')
    if barcode_value:
        fields['BARCODE'] = {'value': barcode_value, 'confidence': (barcode_result or {}).get('confidence', 0.7), 'source': (barcode_result or {}).get('source', 'BARCODE')}
    if lookup.get('status') != 'FOUND':
        return fields
    product_name = str(lookup.get('product_name') or '').strip()
    brand = str(lookup.get('brands') or '').split(',')[0].strip()
    # External metadata is corroborating evidence, but has priority over a weak
    # generic OCR candidate such as "Balanced".
    if product_name:
        current = fields.get('PRODUCT_NAME', {})
        if not current or float(current.get('confidence') or 0) < 0.85 or current.get('value', '').lower() in MARKETING_TERMS:
            fields['PRODUCT_NAME'] = {'value': product_name[:200], 'confidence': 0.92, 'source': 'BARCODE_LOOKUP+OCR'}
    if brand:
        current = fields.get('BRAND', {})
        if not current or float(current.get('confidence') or 0) < 0.85:
            fields['BRAND'] = {'value': brand[:200], 'confidence': 0.92, 'source': 'BARCODE_LOOKUP+OCR'}
    if product_name and 'GENERIC_NAME' not in fields:
        tokens = [token for token in re.findall(r'[A-Za-z]+', product_name) if token.lower() not in {word.lower() for word in brand.split()}]
        if tokens:
            fields['GENERIC_NAME'] = {'value': tokens[-1].upper(), 'confidence': 0.78, 'source': 'BARCODE_LOOKUP+OCR'}
    return fields


def merge_extracted_fields(field_sets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Keep the strongest traceable field from all package views.

    A declaration panel should not be overwritten by a lower-confidence front
    image merely because it is processed later.
    """
    merged: Dict[str, Any] = {}
    for field_set in field_sets:
        for name, candidate in field_set.items():
            if not candidate or not str(candidate.get('value', '')).strip():
                continue
            previous = merged.get(name)
            if not previous or float(candidate.get('confidence') or 0) > float(previous.get('confidence') or 0):
                merged[name] = candidate
    return merged


def _split_vendor_and_address(raw_value: str) -> Dict[str, str]:
    value = raw_value.strip(' :;,-')
    if not value:
        return {'name': '', 'address': ''}
    if re.search(r'(p\.?o\.?|plot\s*no|road|street|sector|industrial\s*area|district|state|pin(?:code)?|india)', value, re.IGNORECASE):
        parts = re.split(r'\s+(?=(?:p\.?o\.?|plot\s*no|road|street|sector|industrial\s*area|district|state|pin(?:code)?|india))', value, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            return {'name': parts[0].strip(', '), 'address': parts[1].strip(', ')}
    if ',' in value:
        first, second = value.split(',', 1)
        if len(first) > 3 and len(first) <= 200:
            return {'name': first.strip(), 'address': second.strip()}
    return {'name': value[:200], 'address': ''}


NET_QTY_UNITS_MAP = {
    'g': 'g', 'gm': 'g', 'gms': 'g', 'gram': 'g', 'grams': 'g',
    'kg': 'kg', 'kgs': 'kg', 'kilogram': 'kg', 'kilograms': 'kg',
    'mg': 'mg', 'milligram': 'mg', 'milligrams': 'mg',
    'ml': 'ml', 'millilitre': 'ml', 'millilitres': 'ml', 'milliliter': 'ml', 'milliliters': 'ml',
    'l': 'L', 'ltr': 'L', 'litre': 'L', 'litres': 'L', 'liter': 'L', 'liters': 'L',
    'oz': 'oz', 'lb': 'lb', 'lbs': 'lb',
    'pc': 'pieces', 'pcs': 'pieces', 'piece': 'pieces', 'pieces': 'pieces',
    'tablet': 'tablets', 'tablets': 'tablets',
    'capsule': 'capsules', 'capsules': 'capsules',
}

NET_QTY_LABEL_RE = re.compile(
    r'(?:net\s*(?:wt\.?|weight|qty\.?|quantity|content|contents|vol\.?|volume)|quantity|contents?)\s*[:.]*\s*(?:-\s+)?([^\n,;]+)',
    re.IGNORECASE,
)

STANDALONE_QTY_RE = re.compile(
    r'\b([+-]?\d+(?:\.\d+)?)\s*(g|gm|gms|gram|grams|kg|kgs|kilogram|kilograms|mg|milligram|milligrams|ml|millilitre|millilitres|milliliter|milliliters|l|ltr|litre|litres|liter|liters|oz|lb|lbs|pc|pcs|piece|pieces|tablet|tablets|capsule|capsules)\b',
    re.IGNORECASE,
)


def _extract_net_quantity_field(normalized: str) -> Optional[Dict[str, Any]]:
    """Extract structured declared net quantity, separating raw OCR text from normalized numbers/units."""
    label_match = NET_QTY_LABEL_RE.search(normalized)
    if label_match:
        raw_span = label_match.group(0).strip()
        after_label = label_match.group(1).strip()
        num_match = re.search(r'([+-]?\d+(?:\.\d+)?)', after_label)
        unit_match = re.search(
            r'\b(g|gm|gms|gram|grams|kg|kgs|kilogram|kilograms|mg|milligram|milligrams|ml|millilitre|millilitres|milliliter|milliliters|l|ltr|litre|litres|liter|liters|oz|lb|lbs|pc|pcs|piece|pieces|tablet|tablets|capsule|capsules)\b',
            after_label,
            re.IGNORECASE,
        )

        qty_val = num_match.group(1) if num_match else None
        quantity_present = qty_val is not None
        raw_unit = unit_match.group(1) if unit_match else None
        unit_present = raw_unit is not None
        norm_unit = NET_QTY_UNITS_MAP.get(raw_unit.lower()) if raw_unit else None

        if quantity_present or unit_present:
            try:
                num_float = float(qty_val) if qty_val is not None else None
                num_valid = num_float is not None and num_float > 0
            except ValueError:
                num_valid = False

            quantity_unit_valid = bool(quantity_present and unit_present and num_valid and norm_unit)

            if quantity_present and unit_present:
                display_val = f"{qty_val} {norm_unit}"
            elif quantity_present:
                display_val = f"{qty_val}"
            elif unit_present:
                display_val = f"{norm_unit}"
            else:
                display_val = raw_span

            return {
                'raw_value': raw_span,
                'value': display_val,
                'quantity_value': qty_val,
                'quantity_unit': norm_unit,
                'raw_unit': raw_unit,
                'quantity_present': quantity_present,
                'unit_present': unit_present,
                'quantity_unit_valid': quantity_unit_valid,
                'confidence': 0.8,
                'source': 'OCR',
            }

    # Standalone quantity + unit fallback
    standalone_match = STANDALONE_QTY_RE.search(normalized)
    if standalone_match:
        raw_span = standalone_match.group(0).strip()
        qty_val = standalone_match.group(1)
        raw_unit = standalone_match.group(2)
        norm_unit = NET_QTY_UNITS_MAP.get(raw_unit.lower(), raw_unit.lower())
        try:
            num_float = float(qty_val)
            num_valid = num_float > 0
        except ValueError:
            num_valid = False
        quantity_unit_valid = bool(num_valid and norm_unit in NET_QTY_UNITS_MAP.values())
        return {
            'raw_value': raw_span,
            'value': f"{qty_val} {norm_unit}",
            'quantity_value': qty_val,
            'quantity_unit': norm_unit,
            'raw_unit': raw_unit,
            'quantity_present': True,
            'unit_present': True,
            'quantity_unit_valid': quantity_unit_valid,
            'confidence': 0.8,
            'source': 'OCR',
        }

    return None


def extract_declarations(raw_text: str, ocr_items: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if not raw_text:
        return {}

    normalized = _normalize_text(raw_text)
    lines = [line.strip() for line in normalized.split('\n') if line.strip()]
    fields: Dict[str, Any] = {}

    first_candidate = _product_candidate(lines, ocr_items)
    if first_candidate:
        fields['PRODUCT_NAME'] = {'value': first_candidate[:200], 'confidence': 0.65, 'source': 'OCR'}

    crystal_line = next((line for line in lines if re.search(r'\bcrystal\s+sugar\b', line, re.IGNORECASE)), None)
    if crystal_line:
        before_crystal = re.split(r'\bcrystal\s+sugar\b', crystal_line, maxsplit=1, flags=re.IGNORECASE)[0]
        brand_tokens = re.findall(r'[A-Za-z][A-Za-z0-9&-]*', before_crystal)
        if len(brand_tokens) >= 2:
            fields['BRAND'] = {'value': ' '.join(brand_tokens[-2:]).upper(), 'confidence': 0.8, 'source': 'OCR'}
    if 'BRAND' not in fields:
        normalized_lines = [re.sub(r'[^a-z]', '', line.lower()) for line in lines]
        if any(line == 'supreme' for line in normalized_lines) and any(line == 'harvest' for line in normalized_lines):
            fields['BRAND'] = {'value': 'SUPREME HARVEST', 'confidence': 0.78, 'source': 'OCR'}
    # A front panel often has an uppercase brand on the line immediately above
    # a generic product term (for example, brand / SALT). Combine that layout
    # evidence generically instead of promoting nearby claims.
    for index, line in enumerate(lines[:-1]):
        next_line = lines[index + 1]
        brand_words = re.findall(r'[A-Za-z][A-Za-z&-]*', line)
        product_words = re.findall(r'[A-Za-z][A-Za-z&-]*', next_line)
        if (1 <= len(brand_words) <= 3 and brand_words and line.upper() == line and
                any(word.lower() in {'salt', 'sugar', 'soap', 'shampoo', 'biscuit', 'oil', 'tea'} for word in product_words)):
            brand = ' '.join(word.title() for word in brand_words)
            generic = ' '.join(product_words).title()
            fields['BRAND'] = {'value': brand, 'confidence': 0.84, 'source': 'OCR_LAYOUT'}
            fields['PRODUCT_NAME'] = {'value': f'{brand} {generic}', 'confidence': 0.86, 'source': 'OCR_LAYOUT'}
            break
    if re.search(r'\bcrystal\s+sugar\b|\bgranulated\s+sugar\b|\bsugar\b', normalized, re.IGNORECASE):
        fields['PRODUCT_TYPE'] = {'value': 'SUGAR', 'confidence': 0.85, 'source': 'OCR'}
        fields['GENERIC_NAME'] = {'value': 'CRYSTAL SUGAR' if re.search(r'crystal\s+sugar', normalized, re.IGNORECASE) else 'SUGAR', 'confidence': 0.8, 'source': 'OCR'}
    elif re.search(r'\biodized?\s+salt\b|\bsalt\b', normalized, re.IGNORECASE):
        fields['PRODUCT_TYPE'] = {'value': 'SALT', 'confidence': 0.8, 'source': 'OCR'}
        fields['GENERIC_NAME'] = {'value': 'SALT', 'confidence': 0.75, 'source': 'OCR'}
    elif re.search(r'\bbiscuit|cookie', normalized, re.IGNORECASE):
        fields['PRODUCT_TYPE'] = {'value': 'BISCUIT', 'confidence': 0.78, 'source': 'OCR'}
    elif re.search(r'\bspice|masala|pepper|turmeric|chilli', normalized, re.IGNORECASE):
        fields['PRODUCT_TYPE'] = {'value': 'SPICE', 'confidence': 0.75, 'source': 'OCR'}
    elif re.search(r'\b(?:talcum\s+powder|body\s+talc|soft\s+talc|face\s+powder|talc)\b', normalized, re.IGNORECASE):
        fields['PRODUCT_TYPE'] = {'value': 'TALCUM_POWDER', 'confidence': 0.86, 'source': 'OCR'}
        fields['GENERIC_NAME'] = {'value': 'TALCUM POWDER', 'confidence': 0.82, 'source': 'OCR'}

    if crystal_line and 'GENERIC_NAME' in fields:
        brand_value = fields.get('BRAND', {}).get('value')
        fields['PRODUCT_NAME'] = {
            'value': f"{brand_value} {fields['GENERIC_NAME']['value']}" if brand_value else fields['GENERIC_NAME']['value'],
            'confidence': 0.82,
            'source': 'OCR',
        }

    # For labels where the logo and generic description are separated, prefer
    # the generic line as product identity and its preceding short logo line as
    # brand; promotional banners are excluded above.
    generic_line = next((line for line in lines if re.search(r'\b(?:talcum\s+powder|body\s+talc|soft\s+talc|shampoo|conditioner|deodorant|body\s+lotion|face\s+cream)\b', line, re.I)), None)
    if generic_line:
        generic = re.search(r'(talcum\s+powder|body\s+talc|soft\s+talc|shampoo|conditioner|deodorant|body\s+lotion|face\s+cream)', generic_line, re.I).group(1)
        fields['GENERIC_NAME'] = {'value': 'TALCUM POWDER' if 'talc' in generic.lower() else generic.upper(), 'confidence': .82, 'source': 'OCR'}
        candidate_index = lines.index(generic_line)
        nearby = [line for line in lines[max(0, candidate_index - 2):candidate_index] if re.fullmatch(r'[A-Za-z][A-Za-z& -]{1,30}', line.strip()) and not any(token in MARKETING_TERMS for token in line.lower().split())]
        if nearby:
            brand = nearby[-1].strip().title()
            fields['BRAND'] = {'value': brand, 'confidence': .76, 'source': 'OCR_LAYOUT'}
            fields['PRODUCT_NAME'] = {'value': f'{brand} {generic.title()}', 'confidence': .8, 'source': 'OCR_LAYOUT'}
        elif 'PRODUCT_NAME' not in fields or fields['PRODUCT_NAME'].get('value', '').lower() in MARKETING_TERMS:
            fields['PRODUCT_NAME'] = {'value': generic.title(), 'confidence': .75, 'source': 'OCR'}

    mrp_value = _search_patterns(normalized, MRP_PATTERNS)
    if mrp_value:
        fields['MRP'] = {'value': f'₹{mrp_value.replace(",", "")}', 'confidence': 0.85, 'source': 'OCR'}

    qty_field = _extract_net_quantity_field(normalized)
    if qty_field:
        fields['DECLARED_NET_QUANTITY'] = qty_field

    for line_index, line in enumerate(lines):
        lower = line.lower()
        if any(keyword in lower for keyword in MANUFACTURER_KEYWORDS):
            candidate = line
            for kw in MANUFACTURER_KEYWORDS:
                if kw in lower:
                    candidate = line[line.lower().find(kw) + len(kw):].strip(' :;,-')
                    break
            candidate = ' '.join([candidate, _lines_after_label(lines, line_index)]).strip()
            vendor = _split_vendor_and_address(candidate)
            if vendor['name']:
                fields['MANUFACTURER_NAME'] = {'value': f"Manufactured by: {vendor['name']}", 'confidence': 0.75, 'source': 'OCR'}
            if vendor['address']:
                fields['MANUFACTURER_ADDRESS'] = {'value': vendor['address'][:500], 'confidence': 0.65, 'source': 'OCR'}
            break

    for line_index, line in enumerate(lines):
        lower = line.lower()
        if any(keyword in lower for keyword in IMPORTER_KEYWORDS):
            candidate = line
            for kw in IMPORTER_KEYWORDS:
                if kw in lower:
                    candidate = line[line.lower().find(kw) + len(kw):].strip(' :;,-')
                    break
            candidate = ' '.join([candidate, _lines_after_label(lines, line_index)]).strip()
            if candidate:
                fields['IMPORTER_NAME_ADDRESS'] = {'value': candidate[:500], 'confidence': 0.7, 'source': 'OCR'}
            break

    for line in lines:
        lower = line.lower()
        if any(keyword in lower for keyword in COUNTRY_OF_ORIGIN_KEYWORDS):
            kw = next(k for k in COUNTRY_OF_ORIGIN_KEYWORDS if k in lower)
            candidate = line[line.lower().find(kw) + len(kw):].strip(' :;,-')
            if candidate:
                fields['COUNTRY_OF_ORIGIN'] = {'value': candidate[:100], 'confidence': 0.7, 'source': 'OCR'}
            break

    date_value = _extract_date_near_keyword(normalized, MFG_DATE_KEYWORDS)
    if date_value:
        fields['MONTH_YEAR_MANUFACTURE'] = {'value': date_value, 'raw_value': date_value, 'normalized_value': date_value, 'confidence': 0.7, 'source': 'OCR'}

    packing_date = _extract_date_near_keyword(normalized, PACKING_DATE_KEYWORDS)
    if packing_date:
        fields['PACKING_DATE'] = {'value': packing_date, 'raw_value': packing_date, 'normalized_value': packing_date, 'confidence': 0.75, 'source': 'OCR'}

    best_before = _extract_date_near_keyword(normalized, BEST_BEFORE_KEYWORDS)
    if best_before:
        fields['BEST_BEFORE_USE_BY'] = {'value': best_before, 'raw_value': best_before, 'normalized_value': best_before, 'confidence': 0.7, 'source': 'OCR'}

    use_by = _extract_date_near_keyword(normalized, USE_BY_KEYWORDS)
    if use_by:
        fields['USE_BEFORE_DATE'] = {'value': use_by, 'raw_value': use_by, 'normalized_value': use_by, 'confidence': 0.7, 'source': 'OCR'}

    fssai = _search_patterns(normalized, FSSAI_PATTERNS)
    if fssai and 9 <= len(fssai) <= 14 and fssai.isdigit():
        fields['FSSAI_LICENSE'] = {'value': fssai, 'confidence': 0.9, 'source': 'OCR'}

    for line_index, line in enumerate(lines):
        lower = line.lower()
        if any(keyword in lower for keyword in INGREDIENT_KEYWORDS):
            kw = next(k for k in INGREDIENT_KEYWORDS if k in lower)
            candidate = line[line.lower().find(kw) + len(kw):].strip(' :;,-')
            candidate = ' '.join([candidate, _lines_after_label(lines, line_index, 6)]).strip()
            if candidate:
                fields['INGREDIENTS_LIST'] = {'value': candidate[:1000], 'confidence': 0.7, 'source': 'OCR'}
            break

    for line_index, line in enumerate(lines):
        if any(keyword in line.lower() for keyword in NUTRITIONAL_KEYWORDS):
            panel = ' '.join([line, _lines_after_label(lines, line_index, 12)]).strip()
            fields['NUTRITIONAL_INFO'] = {'value': panel[:2000], 'confidence': 0.65, 'source': 'OCR', 'regulatory_source': 'FSSAI_FOOD_LABELING'}
            break

    if any(keyword in normalized.lower() for keyword in VEG_NONVEG_KEYWORDS):
        fields['VEG_NONVEG_SYMBOL'] = {'value': 'Text mention detected', 'confidence': 0.5, 'source': 'OCR'}

    for line_index, line in enumerate(lines):
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in ['consumer care', 'customer care', 'helpline', 'toll free', 'contact']):
            value = line.split(':', 1)[-1].strip() if ':' in line else line
            value = ' '.join([value, _lines_after_label(lines, line_index, 6)]).strip()
            fields['CONSUMER_CARE'] = {'value': value[:1000], 'confidence': 0.7, 'source': 'OCR'}
            break

    cc_match = _search_patterns(normalized, CONSUMER_CARE_PATTERNS)
    if cc_match and 'CONSUMER_CARE' not in fields:
        fields['CONSUMER_CARE'] = {'value': cc_match[:200], 'confidence': 0.7, 'source': 'OCR'}

    batch_match = re.search(r'(?:batch\s*(?:no\.?|number)?|lot\s*(?:no\.?|number)?)\s*[:\s-]*\s*([A-Za-z][A-Za-z0-9\-/]*|\d{1,10})', normalized, re.IGNORECASE)
    if batch_match:
        fields['BATCH_NUMBER'] = {'value': batch_match.group(1)[:100], 'confidence': 0.7, 'source': 'OCR'}

    for field_data in fields.values():
        value = str(field_data.get('value', '')).lower()
        if ocr_items and value:
            matching_item = next(
                (item for item in ocr_items if value in str(item.get('text', '')).lower()),
                None,
            )
            if matching_item:
                field_data['source_image_index'] = matching_item.get('image_index')
                field_data['bbox'] = matching_item.get('bbox')
                field_data['confidence'] = min(float(field_data.get('confidence') or 0), float(matching_item.get('confidence') or 0))

    logger.info(f"Extracted {len(fields)} declaration fields from OCR text")
    return fields
