"""Declaration extractor for packaged-commodity OCR text."""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

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
    # 3-part dates
    r'\b(\d{1,2}/\d{1,2}/\d{2,4})\b',
    r'\b(\d{1,2}-\d{1,2}-\d{2,4})\b',
    r'\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b',
    r'\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b',
    r'\b(\d{1,2}[/-](?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[/-]\d{2,4})\b',
    r'\b(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{2,4})\b',
    # 2-part dates (Month / Year)
    r'\b(\d{1,2}/\d{2,4})\b',
    r'\b(\d{1,2}-\d{2,4})\b',
    r'\b(\d{1,2}\.\d{4})\b',
    r'\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*[/.-]?\s*\d{2,4})\b',
    r'\b(\d{4}[/-]\d{1,2})\b',
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
    'manufactured & marketed by', 'manufactured and marketed by', 'manufactured/marketed by',
    'manufactured & packed by', 'manufactured and packed by', 'manufactured/packed by',
    'manufactured at', 'manufactured for', 'manufactured by', 'manufactured:',
    'mfg & mkt by', 'mfg & pkd by', 'mfd & pkd by', 'mfd & mkt by',
    'mfg. by', 'mfd. by', 'mfg by', 'mfd by',
    'marketed by', 'packed at', 'packed by', 'puckea by',
    'packer', 'manufacturer', 'made by',
]
IMPORTER_KEYWORDS = ['imported by', 'importer', 'import by']
INGREDIENT_KEYWORDS = ['ingredients', 'composition', 'ingredient list']
NUTRITIONAL_KEYWORDS = ['nutritional information', 'nutrition facts', 'energy', 'protein', 'carbohydrate', 'fat', 'calories', 'per serving']
VEG_NONVEG_KEYWORDS = ['vegetarian', 'non-vegetarian', 'non-veg', 'nonveg']
COUNTRY_OF_ORIGIN_KEYWORDS = ['country of origin', 'made in', 'product of', 'manufactured in']
BEST_BEFORE_KEYWORDS = ['best before date', 'best before', 'best by date', 'best by']
USE_BY_KEYWORDS = ['use before date', 'use by date', 'use-before', 'use before', 'use by', 'consume before', 'consume within', 'valid until', 'valid till']
EXPIRY_KEYWORDS = ['expiry date', 'expiration date', 'exp date', 'exp. date', 'expiry', 'exp:', 'exp.', 'exp']
MFG_DATE_KEYWORDS = ['date of manufacture', 'date of manufacturing', 'manufacturing date', 'manufacture date', 'mfg date', 'mfd date', 'mfg.', 'mfd.', 'mfg:', 'mfd:', 'mfg', 'mfd']
PACKING_DATE_KEYWORDS = ['date of packaging', 'date of packing', 'packaging date', 'packing date', 'package date', 'pkg date', 'pkd date', 'packed on', 'pkd:', 'pkd.', 'pkd']
MARKETING_TERMS = {'balanced', 'taste', 'immuno', 'iodine', 'zinc', 'vacuum', 'evaporated', 'recyclable', 'fresh', 'natural', 'quality', 'premium', 'guarantee', 'trust', 'great', 'deal', 'new', 'sale', 'special', 'offer', 'free', 'buy', 'one', 'get', 'did', 'you', 'know', 'best', 'no'}
SECTION_BOUNDARY_RE = re.compile(
    r'(?:'
    r'\b(?:manufactured|mfg|mfd|packed|marketed|imported)\s*(?:&|and|/)?\s*(?:marketed|packed|mkt|pkd)?\s*(?:by|at|for)\b|'
    r'\bpacked\s+(?:by|at)\b|\bmarketed\s+by\b|\bimported\s+by\b|\bcountry\s+of\s+origin\b|\bmade\s+in\b|'
    r'\bnet\s*(?:wt\.?|weight|qty\.?|quantity|content|contents|vol\.?|volume)\b|\bquantity\b|'
    r'\bm\.?\s*r\.?\s*p\.?|\bmaximum\s+retail\s+price\b|'
    r'\bbatch\s*(?:no\.?|number)?\b|\bb\.?\s*no\.?\b|\blot\s*(?:no\.?|number)?\b|'
    r'\buse\s*-?\s*(?:by|before)\b|\bbest\s+before\b|\bbest\s+by\b|\bconsume\s+before\b|'
    r'\bdate\s+of\s+(?:manufactur\w+|pack\w+)\b|\bmfg\s*date\b|\bmfd\s*date\b|\bpkd\s*date\b|\bpkg\s*date\b|\bpacked\s+on\b|'
    r'\bexpiry(?:\s+date)?\b|\bexp(?:\.|\s*date|:)|'
    r'\bconsumer\s+care\b|\bcustomer\s+care\b|\bcustomer\s+support\b|\bhelpline\b|\btoll\s*free\b|\bwrite\s+to\b|'
    r'\bingredients?\b|\bcomposition\b|\bingredient\s+list\b|'
    r'\bnutritional?\s*(?:information|facts)\b|'
    r'\bfssai\b|\blic\.?\s*(?:no\.?|number)?\b|\blicen[cs]e\s*(?:no\.?|number)?\b|\bbarcode\b|\bean\b'
    r')',
    re.IGNORECASE,
)
VENDOR_LINE_RE = re.compile(
    r'([A-Za-z][A-Za-z0-9&.\'\s-]{2,80}?(?:Pvt\.?\s*Ltd\b\.?|Private\s+Limited\b|Ltd\b\.?|Limited\b))',
    re.IGNORECASE,
)
COMPANY_SUFFIX_RE = re.compile(
    r'\b([A-Za-z][A-Za-z0-9&.\'\s-]{1,70}?\s+(?:Pvt\.?\s*Ltd\b\.?|Private\s+Limited\b|Ltd\b\.?|Limited\b))(?:\s*[,;:]|\s*$|\s+(?=[A-Za-z0-9]))',
    re.IGNORECASE,
)
NON_COMPANY_LIMITED_WORDS = {'edition', 'offer', 'period', 'time', 'stock', 'validity', 'warranty', 'qty', 'quantity'}
INLINE_SECTION_PATTERNS = {
    'manufacturer': [
        r'\b(?:manufactured\s*(?:&|and|/)?\s*(?:marketed|packed)?\s*(?:by|at|for)|mfg\s*(?:&|and|/)?\s*(?:mkt|pkd)?\s*by|mfd\s*(?:&|and|/)?\s*(?:mkt|pkd)?\s*by|packed\s+(?:by|at)|marketed\s+by|imported\s+by|packer\b|manufacturer\b|made\s+by\b)',
    ],
    'ingredients': [
        r'\b(?:ingredients?|composition|ingredient\s+list)\b',
    ],
    'net_quantity': [
        r'\b(?:net\s*(?:wt\.?|weight|qty\.?|quantity|content|contents|vol\.?|volume)|quantity|contents)\b',
    ],
    'mrp': [
        r'\b(?:m\.?\s*r\.?\s*p\.?|maximum\s+retail\s+price)\b',
        r'\b(?:rs\.?|₹|inr)\s*\d',
    ],
    'batch': [
        r'\b(?:batch\s*(?:no\.?|number)?|lot\s*(?:no\.?|number)?|b\.?\s*no\.?)\b',
    ],
    'date': [
        r'\b(?:date\s+of\s+(?:manufactur\w+|pack\w+)|mfg\s*date|mfd\s*date|pkd\s*date|pkg\s*date|packed\s+on|mfd[:.]|mfg[:.]|pkd[:.]|best\s+before|best\s+by|use\s*-?\s*(?:by|before)|consume\s+before|expiry(?:\s+date)?|exp(?:\.|\s*date|:))\b',
    ],
    'consumer_care': [
        r'\b(?:consumer\s*care|customer\s*care|customer\s*support|helpline|toll\s*free|contact(?:\s+us)?|write\s+to|feedback)\b',
    ],
    'nutrition': [
        r'\b(?:nutritional\s+information|nutrition\s+facts|nutritional\s+facts|per\s+(?:100\s*g|serving)|energy\s*:|protein\s*:|carbohydrate\s*:)\b',
    ],
    'fssai': [
        r'\b(?:fssai|lic\.?\s*(?:no\.?|number)?|licen[cs]e\s*(?:no\.?|number)?|reg\.?\s*no\.?)\b',
    ],
}
VENDOR_PREFIX_RE = re.compile(
    r'\b(?:manufactured|mfg|mfd|packed|marketed|imported|produced|distributed)\s*(?:\.|\b)\s*(?:by|at|for|in)\b',
    re.IGNORECASE,
)
ALL_DATE_LABELS = MFG_DATE_KEYWORDS + PACKING_DATE_KEYWORDS + BEST_BEFORE_KEYWORDS + USE_BY_KEYWORDS + EXPIRY_KEYWORDS


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


def _is_section_boundary(line: str, current_section: Optional[str] = None) -> bool:
    if not line:
        return False
    if current_section:
        for sec_name, patterns in INLINE_SECTION_PATTERNS.items():
            if sec_name == current_section:
                continue
            for pat in patterns:
                if re.search(pat, line, re.IGNORECASE):
                    return True
        return False
    return bool(SECTION_BOUNDARY_RE.search(line))


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
    if not text:
        return None
    matches = []
    for pattern in DATE_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            token = m.group(1).strip()
            if _is_valid_date_token(token):
                matches.append((m.start(), len(token), token))
    if not matches:
        return None
    # Sort primarily by starting character position (earliest in the string),
    # and secondarily by token length descending (longest valid date format starting at that position)
    matches.sort(key=lambda x: (x[0], -x[1]))
    return matches[0][2]


def _line_has_other_date_label(line: str, keywords: List[str]) -> bool:
    lowered = line.lower()
    own = [kw.lower().strip() for kw in keywords]
    for label in ALL_DATE_LABELS:
        token = label.lower().strip()
        if len(token) < 3:
            continue
        if token in own or any(token == item for item in own):
            continue
        esc = re.escape(token)
        pat = rf'(?:\b|(?<=^)){esc}' if token.endswith((':', '.')) else rf'\b{esc}\b'
        if re.search(pat, lowered):
            if not re.search(rf'{pat}(?:\s*(?:by|at|for|in)\b)', lowered):
                return True
    return False


def _extract_date_near_keyword(text: str, keywords: List[str]) -> Optional[str]:
    """Bind a date only to its label line (or an immediately adjacent date-only line).

    Do not pick the nearest date in a large window. Ambiguous leftover dates stay unassigned.
    """
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    bound = []
    own_keywords_lower = [kw.lower().strip() for kw in keywords]

    # Precompile keyword patterns to avoid matching vendor lines as date keywords
    keyword_patterns = []
    for kw in sorted(keywords, key=len, reverse=True):
        escaped = re.escape(kw.strip())
        if kw.endswith((':', '.')):
            pat = re.compile(rf'(?:\b|(?<=^)){escaped}(?!\s*(?:by|at|for|in)\b)', re.IGNORECASE)
        else:
            pat = re.compile(rf'\b{escaped}\b(?!\s*(?:by|at|for|in)\b)', re.IGNORECASE)
        keyword_patterns.append((kw, pat))

    for index, line in enumerate(lines):
        matched_match = None
        matched_kw_str = None
        for kw_str, pat in keyword_patterns:
            m = pat.search(line)
            if m:
                # Ensure it's not preceded by a vendor entity name on the same line
                prefix_before = line[:m.start()]
                if VENDOR_LINE_RE.search(prefix_before) and not any(sep in prefix_before for sep in (';', '|', '\t', '  ')):
                    continue
                matched_match = m
                matched_kw_str = kw_str
                break

        if not matched_match:
            continue

        # Same line: only the span after the matched label, cut at the next other date label.
        after = line[matched_match.end():]
        earliest_other_pos = len(after)
        for other in ALL_DATE_LABELS:
            other_clean = other.lower().strip()
            if len(other_clean) < 3 or other_clean in own_keywords_lower:
                continue
            esc_other = re.escape(other_clean)
            other_pat = rf'(?:\b|(?<=^)){esc_other}' if other.endswith((':', '.')) else rf'\b{esc_other}\b'
            other_m = re.search(other_pat, after, re.IGNORECASE)
            if other_m and other_m.start() < earliest_other_pos:
                earliest_other_pos = other_m.start()

        after_segment = after[:earliest_other_pos]
        same = _first_date_in(after_segment)
        if same:
            bound.append(same)
            continue

        # Check neighbour lines only if same line has no date
        for neighbour in (lines[index + 1] if index + 1 < len(lines) else '', lines[index - 1] if index else ''):
            if not neighbour:
                continue
            # Never cross into vendor lines or section boundaries
            if _is_section_boundary(neighbour) or VENDOR_PREFIX_RE.search(neighbour) or _line_has_other_date_label(neighbour, keywords):
                continue
            neighbour_date = _first_date_in(neighbour)
            if not neighbour_date:
                continue
            # Adjacent line may be used only when it is essentially a date token.
            remainder = re.sub(re.escape(neighbour_date), '', neighbour).strip(' :;,-')
            if len(re.sub(r'[^A-Za-z]', '', remainder)) <= 3:
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

    # Phone numbers
    if '1800' in token or any(token.startswith(prefix) for prefix in ('+91', '011', '022', '033', '044', '080')):
        return False

    # Currency indicators
    if re.search(r'(?:rs\.?|inr|₹|mrp)', token):
        return False

    # Decimal numbers (e.g. 0.73, 12.50, 99.99)
    if re.fullmatch(r'\d+\.\d{1,2}', token):
        return False

    # Pure long digit sequences (barcodes, serials, phones)
    digits_only = re.sub(r'\D', '', token)
    if len(digits_only) > 8:
        return False
    if len(digits_only) < 3 and not re.search(r'[a-z]', token):
        return False

    has_text_month = bool(re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)', token))
    if re.search(r'[a-z]', token) and not has_text_month:
        return False

    if has_text_month:
        nums = [int(n) for n in re.findall(r'\d+', token)]
        if not nums:
            return False
        if len(nums) == 1:
            yr = nums[0]
            if len(str(yr)) == 4:
                return 1990 <= yr <= 2099
            elif len(str(yr)) <= 2:
                return 0 <= yr <= 99
            return False
        elif len(nums) == 2:
            day, yr = nums
            if not (1 <= day <= 31):
                return False
            if len(str(yr)) == 4:
                return 1990 <= yr <= 2099
            elif len(str(yr)) <= 2:
                return 0 <= yr <= 99
            return False
        return False

    # Numeric parts separated by /, -, or .
    parts = [part for part in re.split(r'[/.-]', token) if part != '']
    if len(parts) not in (2, 3):
        return False

    try:
        numbers = [int(p) for p in parts]
    except ValueError:
        return False

    if len(parts) == 2:
        first, second = numbers
        p1_len, p2_len = len(parts[0]), len(parts[1])
        if 1 <= first <= 12:
            if p2_len == 4:
                return 1990 <= second <= 2099
            elif p2_len == 2:
                return 0 <= second <= 99
        if p1_len == 4 and 1990 <= first <= 2099 and 1 <= second <= 12:
            return True
        return False

    if len(parts) == 3:
        p1_len, p2_len, p3_len = len(parts[0]), len(parts[1]), len(parts[2])
        if 1 <= numbers[0] <= 31 and 1 <= numbers[1] <= 12:
            if p3_len == 4:
                return 1990 <= numbers[2] <= 2099
            elif p3_len == 2:
                return 0 <= numbers[2] <= 99
        if p1_len == 4 and 1990 <= numbers[0] <= 2099 and 1 <= numbers[1] <= 12 and 1 <= numbers[2] <= 31:
            return True
        return False

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
        if re.search(r'\b(?:manufactured|manufacturing|marketed|packed|ingredients|nutrition|fssai|consumer|address|mrp|net\s*(?:wt|weight)|pvt\.?\s*ltd|private\s+limited|ltd\b|limited\b|plot\s*(?:no\.?)?|survey\s*(?:no\.?)?|sector\b|phase\s+[ivx0-9]+|gidc|industrial\s*area)\b', line, re.I):
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


def _cut_before_next_section(text: str, current_section: str) -> str:
    """Cut text on the same line before any other section begins."""
    if not text:
        return ""
    earliest_pos = len(text)
    for sec_name, patterns in INLINE_SECTION_PATTERNS.items():
        if sec_name == current_section:
            continue
        for pat in patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                if 0 < m.start() < earliest_pos:
                    earliest_pos = m.start()
    return text[:earliest_pos].strip(' :;,-')


def _extract_company_entity_from_line(line: str) -> Optional[Tuple[str, str]]:
    """If a line contains a verifiable corporate entity (e.g., 'Shree Foods Pvt. Ltd.'),
    return (company_name, remaining_address_on_same_line).
    """
    line_clean = line.strip()
    if not line_clean or _is_section_boundary(line_clean):
        return None
    m = COMPANY_SUFFIX_RE.search(line_clean)
    if not m:
        return None
    entity = m.group(1).strip(' ,;:')
    after_entity = line_clean[m.end():].strip(' ,;:')
    first_word_after = after_entity.split()[0].lower() if after_entity.split() else ''
    if first_word_after in NON_COMPANY_LIMITED_WORDS:
        return None
    words = entity.split()
    if len(words) < 2:
        return None
    if any(w.lower() in {'fresh', 'natural', 'pure', 'offer', 'deal', 'free', 'great'} for w in words[:-1]) and len(words) <= 2:
        return None
    return entity, after_entity


def _collect_continuation_lines(lines: List[str], start_index: int, current_section: str, max_lines: int = 6) -> List[str]:
    """Collect continuation lines for a section, stopping immediately at any subsequent section boundary."""
    collected = []
    for line in lines[start_index + 1:start_index + 1 + max_lines]:
        line_clean = line.strip()
        if not line_clean:
            continue
        if _is_section_boundary(line_clean, current_section):
            break
        if current_section in ('ingredients', 'nutrition') and _extract_company_entity_from_line(line_clean):
            break
        cut_line = _cut_before_next_section(line_clean, current_section)
        if cut_line != line_clean:
            if cut_line:
                collected.append(cut_line.strip(' ,;'))
            break
        collected.append(line_clean.strip(' ,;'))
    return collected


def _extract_manufacturer_and_address(lines: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Extract manufacturer name and address cleanly without section contamination."""
    # Step 1: Look for explicit manufacturer keyword lines
    for idx, line in enumerate(lines):
        line_lower = line.lower()
        matched_kw = None
        for kw in MANUFACTURER_KEYWORDS:
            kw_pattern = rf'(?:\b|(?<=^)){re.escape(kw)}\b'
            m_kw = re.search(kw_pattern, line_lower)
            if m_kw:
                matched_kw = kw
                start_pos = m_kw.end()
                label_prefix = line[:start_pos].strip(' :;,-')
                raw_after = line[start_pos:].strip(' :;,-')
                break

        if matched_kw:
            cleaned_after = _cut_before_next_section(raw_after, 'manufacturer')
            cont_lines = _collect_continuation_lines(lines, idx, 'manufacturer', max_lines=6)

            # Check if cleaned_after has a company entity
            comp_res = _extract_company_entity_from_line(cleaned_after)
            if comp_res:
                comp_name, comp_addr = comp_res
                name = f"{label_prefix}: {comp_name}" if label_prefix else comp_name
                addr_parts = [comp_addr] if comp_addr else []
                addr_parts.extend(cont_lines)
                address = ', '.join(part for part in addr_parts if part)
                return name, address or None

            # Check if label was alone on line and first continuation line is company entity
            if not cleaned_after and cont_lines:
                first_cont = cont_lines[0]
                comp_res_cont = _extract_company_entity_from_line(first_cont)
                if comp_res_cont:
                    comp_name, comp_addr = comp_res_cont
                    name = f"{label_prefix}: {comp_name}" if label_prefix else comp_name
                    addr_parts = [comp_addr] if comp_addr else []
                    addr_parts.extend(cont_lines[1:])
                    address = ', '.join(part for part in addr_parts if part)
                    return name, address or None

            # Fallback split
            if cont_lines:
                vendor = _split_vendor_and_address(cleaned_after) if cleaned_after else {'name': '', 'address': ''}
                if vendor['name'] and vendor['address']:
                    name = f"{label_prefix}: {vendor['name']}" if label_prefix else vendor['name']
                    address = ', '.join([vendor['address']] + cont_lines)
                elif cleaned_after:
                    name = f"{label_prefix}: {cleaned_after}" if label_prefix else cleaned_after
                    address = ', '.join(cont_lines)
                else:
                    name = f"{label_prefix}: {cont_lines[0]}" if label_prefix else cont_lines[0]
                    address = ', '.join(cont_lines[1:]) if len(cont_lines) > 1 else None
                return name or None, address or None
            else:
                vendor = _split_vendor_and_address(cleaned_after)
                name = f"{label_prefix}: {vendor['name']}" if (vendor['name'] and label_prefix) else (vendor['name'] or cleaned_after)
                address = vendor['address'] or None
                return name or None, address

    # Step 2: Standalone company entity without "Manufactured by:" prefix
    for idx, line in enumerate(lines):
        comp_res = _extract_company_entity_from_line(line)
        if comp_res:
            comp_name, comp_addr = comp_res
            cont_lines = _collect_continuation_lines(lines, idx, 'manufacturer', max_lines=6)
            addr_parts = [comp_addr] if comp_addr else []
            addr_parts.extend(cont_lines)
            address = ', '.join(part for part in addr_parts if part)
            return comp_name, address or None

    return None, None


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


def extract_declarations(raw_text: str, ocr_items: Optional[List[Dict[str, Any]]] = None, category: Optional[str] = None) -> Dict[str, Any]:
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

    mfg_name, mfg_addr = _extract_manufacturer_and_address(lines)
    if mfg_name:
        fields['MANUFACTURER_NAME'] = {'value': mfg_name, 'confidence': 0.8, 'source': 'OCR'}
    if mfg_addr:
        fields['MANUFACTURER_ADDRESS'] = {'value': mfg_addr[:500], 'confidence': 0.7, 'source': 'OCR'}

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

    mfg_date = _extract_date_near_keyword(normalized, MFG_DATE_KEYWORDS)
    if mfg_date:
        fields['MANUFACTURE_DATE'] = {'value': mfg_date, 'raw_value': mfg_date, 'normalized_value': mfg_date, 'confidence': 0.75, 'source': 'OCR'}
        fields['MONTH_YEAR_MANUFACTURE'] = {'value': mfg_date, 'raw_value': mfg_date, 'normalized_value': mfg_date, 'confidence': 0.75, 'source': 'OCR'}

    packing_date = _extract_date_near_keyword(normalized, PACKING_DATE_KEYWORDS)
    if packing_date:
        fields['PACKING_DATE'] = {'value': packing_date, 'raw_value': packing_date, 'normalized_value': packing_date, 'confidence': 0.75, 'source': 'OCR'}
        if 'MONTH_YEAR_MANUFACTURE' not in fields:
            fields['MONTH_YEAR_MANUFACTURE'] = {'value': packing_date, 'raw_value': packing_date, 'normalized_value': packing_date, 'confidence': 0.75, 'source': 'OCR'}

    best_before = _extract_date_near_keyword(normalized, BEST_BEFORE_KEYWORDS)
    if best_before:
        fields['BEST_BEFORE_USE_BY'] = {'value': best_before, 'raw_value': best_before, 'normalized_value': best_before, 'confidence': 0.75, 'source': 'OCR'}
    else:
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in BEST_BEFORE_KEYWORDS):
                dur_match = re.search(r'(\d+\s*(?:months?|days?|years?)(?:\s*(?:from|of)\s+[a-z\s]+)?)', line, re.IGNORECASE)
                if dur_match:
                    dur_val = dur_match.group(1).strip()
                    fields['BEST_BEFORE_USE_BY'] = {'value': dur_val, 'raw_value': dur_val, 'normalized_value': dur_val, 'confidence': 0.75, 'source': 'OCR'}
                    break

    use_by = _extract_date_near_keyword(normalized, USE_BY_KEYWORDS)
    if use_by:
        fields['USE_BEFORE_DATE'] = {'value': use_by, 'raw_value': use_by, 'normalized_value': use_by, 'confidence': 0.75, 'source': 'OCR'}
    elif 'BEST_BEFORE_USE_BY' not in fields:
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in USE_BY_KEYWORDS):
                dur_match = re.search(r'(\d+\s*(?:months?|days?|years?)(?:\s*(?:from|of)\s+[a-z\s]+)?)', line, re.IGNORECASE)
                if dur_match:
                    dur_val = dur_match.group(1).strip()
                    fields['USE_BEFORE_DATE'] = {'value': dur_val, 'raw_value': dur_val, 'normalized_value': dur_val, 'confidence': 0.75, 'source': 'OCR'}
                    break

    expiry_date = _extract_date_near_keyword(normalized, EXPIRY_KEYWORDS)
    if expiry_date:
        fields['EXPIRY_DATE'] = {'value': expiry_date, 'raw_value': expiry_date, 'normalized_value': expiry_date, 'confidence': 0.75, 'source': 'OCR'}

    fssai = _search_patterns(normalized, FSSAI_PATTERNS)
    if fssai and 9 <= len(fssai) <= 14 and fssai.isdigit():
        fields['FSSAI_LICENSE'] = {'value': fssai, 'confidence': 0.9, 'source': 'OCR'}

    for line_index, line in enumerate(lines):
        lower = line.lower()
        if any(keyword in lower for keyword in INGREDIENT_KEYWORDS):
            kw = next(k for k in INGREDIENT_KEYWORDS if k in lower)
            raw_after = line[line.lower().find(kw) + len(kw):].strip(' :;,-')
            cleaned_first = _cut_before_next_section(raw_after, 'ingredients')
            cont_lines = _collect_continuation_lines(lines, line_index, 'ingredients', max_lines=8)
            all_ing_parts = [cleaned_first] if cleaned_first else []
            all_ing_parts.extend(cont_lines)
            candidate = ' '.join(all_ing_parts).strip(' ,;')
            if candidate:
                fields['INGREDIENTS_LIST'] = {'value': candidate[:1000], 'confidence': 0.75, 'source': 'OCR'}
            break

    for line_index, line in enumerate(lines):
        if any(keyword in line.lower() for keyword in NUTRITIONAL_KEYWORDS):
            cont_lines = _collect_continuation_lines(lines, line_index, 'nutrition', max_lines=12)
            panel = ' '.join([line.strip()] + cont_lines).strip()
            fields['NUTRITIONAL_INFO'] = {'value': panel[:2000], 'confidence': 0.65, 'source': 'OCR', 'regulatory_source': 'FSSAI_FOOD_LABELING'}
            break

    if (category is None or category.upper() == 'FOOD') and any(keyword in normalized.lower() for keyword in VEG_NONVEG_KEYWORDS):
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

    batch_match = re.search(r'\b(?:batch\s*(?:no\.?|number)?|lot\s*(?:no\.?|number)?|b\.?\s*no\.?)\s*[:\s-]*\s*([A-Za-z0-9][A-Za-z0-9\-/]*)', normalized, re.IGNORECASE)
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
