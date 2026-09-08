"""Declaration extractor for packaged-commodity OCR text."""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.ontology import (
    CanonicalDeclarationField,
    QuantityType,
    LEGAL_MASS_UNITS,
    LEGAL_VOLUME_UNITS,
    LEGAL_COUNT_UNITS,
    LEGAL_LENGTH_AREA_UNITS,
    build_quantity_candidate,
    infer_quantity_type,
    normalize_unit,
    DatePrecision,
    ContactType,
    build_date_candidate,
    build_consumer_care_candidate,
    build_product_name_candidate,
)
from app.extraction.cleaner import clean_ocr_evidence, is_artifact_token
from app.extraction.evidence_model import (
    AnchorRelation,
    EvidenceCandidate,
    EvidenceMergeClassification,
    FIELD_SCOPING_REGISTRY,
    SourceType,
    ValidationState,
    SECTION_FRONT_PRODUCT,
    SECTION_IDENTITY,
    SECTION_QUANTITY,
    SECTION_DECLARED_QUANTITY,
    SECTION_PRICING,
    SECTION_MRP,
    SECTION_MANUFACTURER,
    SECTION_PACKER,
    SECTION_ADDRESS,
    SECTION_DATE,
    SECTION_BATCH,
    SECTION_NUTRITION,
    SECTION_SERVING_SIZE,
    SECTION_INGREDIENTS,
    SECTION_CONSUMER_CARE,
    SECTION_FOOD_LABELING,
    SECTION_COSMETIC_LABELING,
    SECTION_INSTRUCTIONS,
    SECTION_STORAGE,
    SECTION_MARKETING,
    SECTION_BARCODE,
    SECTION_OTHER,
    SECTION_UNKNOWN,
)
from app.extraction.association_engine import AssociatedCandidate, LabelValueAssociator
from app.extraction.label_value_association import (
    EvidenceToken,
    SemanticLabel,
    ValueCandidate,
    LabelValueRelation,
    CanonicalFieldCandidate,
    LabelValueAssociationEngine,
)

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
    'manufacturer', 'made by',
]
MARKETER_KEYWORDS = [
    'manufactured & marketed by', 'manufactured and marketed by', 'manufactured/marketed by',
    'marketed & distributed by', 'marketed and distributed by',
    'marketed by', 'marketed at', 'marketed for',
    'mkt & dist by', 'mkt by', 'mktg by', 'mkt. by',
    'marketer', 'distributed by',
]
PACKER_KEYWORDS = [
    'manufactured & packed by', 'manufactured and packed by', 'manufactured/packed by',
    'packed & marketed by', 'packed and marketed by',
    'packed by', 'packed at', 'pkd by', 'pkd at', 'pkg by', 'pkg at', 'puckea by',
    'packaged by', 'packer',
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

# Semantic section classifications
SECTION_FRONT_PRODUCT = "FRONT_PRODUCT"
SECTION_DECLARED_QUANTITY = "DECLARED_QUANTITY"
SECTION_MRP = "MRP"
SECTION_MANUFACTURER = "MANUFACTURER"
SECTION_MARKETER = "MARKETER"
SECTION_PACKER = "PACKER"
SECTION_ADDRESS = "ADDRESS"
SECTION_DATE = "DATE"
SECTION_BATCH = "BATCH"
SECTION_NUTRITION = "NUTRITION"
SECTION_INGREDIENTS = "INGREDIENTS"
SECTION_SERVING_SIZE = "SERVING_SIZE"
SECTION_FSSAI = "FSSAI"
SECTION_CONSUMER_CARE = "CONSUMER_CARE"
SECTION_BARCODE = "BARCODE"
SECTION_STORAGE = "STORAGE"
SECTION_MARKETING = "MARKETING"
SECTION_FRONT_TITLE = "FRONT_TITLE"
SECTION_INSTRUCTIONS = "INSTRUCTIONS"
SECTION_OTHER = "OTHER"

NET_QTY_POSITIVE_CONTEXT_RE = re.compile(
    r'\b(?:net\s*(?:wt\.?|weight|qty\.?|quantity|content|contents|vol\.?|volume)|declared\s+quantity|net\s*contents?|pack\s*(?:content|contents|size|qty\.?|quantity)|package\s*(?:quantity|content|contents)|pkg\s*qty)\b',
    re.IGNORECASE,
)

NUTRITION_SECTION_HEADER_RE = re.compile(
    r'\b(?:nutritional?\s*(?:information|facts|values?)|nutrition\s+table)\b',
    re.IGNORECASE,
)

NUTRITION_LINE_RE = re.compile(
    r'(?:'
    r'\b(?:energy|calories|protein|carbohydrates?|total\s+sugars?|added\s+sugars?|sugar|total\s+fat|fat|saturated\s+fat|trans\s+fat|cholesterol|sodium|dietary\s+fib(?:re|er)|calcium|iron|potassium|zinc|nutrients?)\b|'
    r'\b(?:kcal|kj)\b|'
    r'\bper\s+100\s*(?:g|ml)\b|'
    r'\bapprox(?:imate)?\s+value\b'
    r')',
    re.IGNORECASE,
)

SERVING_SIZE_RE = re.compile(
    r'\b(?:serv(?:e|ing)\s*size|per\s+(?:serve|serving)|servings?\s+per\s+(?:container|pack|package)|serve\s*size\s*per)\b',
    re.IGNORECASE,
)

INGREDIENTS_LINE_RE = re.compile(
    r'\b(?:ingredients?|composition|contains?\s*:|ingredient\s+list)\b',
    re.IGNORECASE,
)

CONSUMER_CARE_STOP_RE = re.compile(
    r'(?:'
    r'\b(?:consumer\s*care|customer\s*care|customer\s*support|helpline|toll\s*free|call\s+us\s+at|call\s+us|write\s+to|feedback|contact\s*us|reach\s*us)\b|'
    r'\b(?:1800[\s\-]?\d{3}[\s\-]?\d{3,4}|\b\d{3,5}[\s\-]\d{6,10}|\b0\d{2,4}[\s\-]?\d{6,8})\b|'
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b|'
    r'\b(?:www\.[a-z0-9\-]+|https?://[^\s]+)\b'
    r')',
    re.IGNORECASE,
)

STORAGE_STOP_RE = re.compile(
    r'(?:'
    r'\bcontainer\s+once\s+opened\b|\bstore\s+in\b|\bkeep\s+(?:in|away)\b|'
    r'\bcool\s*(?:,|&|and)?\s*dry\s+place\b|\brefrigerat\w*\b|'
    r'\bavoid\s+(?:direct\s+)?sunlight\b|\bdo\s+not\s+(?:store|keep)\b|'
    r'\bdirections?\s+for\s+use\b|\bfor\s+external\s+use\b'
    r')',
    re.IGNORECASE,
)

MARKETING_STOP_RE = re.compile(
    r'(?:'
    r"\bsweet'?n\s*sour\b|\bcrispy\s*(?:&|and)\s*crunchy\b|"
    r'\bdelicious\b|\btasty\b|\bpremium\s+quality\b|'
    r'\b(?:100|pure)\s*%\s*(?:natural|pure|vegetarian)\b|'
    r'\bno\s+added\s+(?:preservative|colour|flavor|sugar)\b|'
    r'\b(?:new|improved)\s+(?:taste|formula|recipe)\b'
    r')',
    re.IGNORECASE,
)

SECTION_BOUNDARY_RE = re.compile(
    r'(?:'
    r'\b(?:manufactured|mfg|mfd|packed|marketed|imported)\s*(?:&|and|/)?\s*(?:marketed|packed|mkt|pkd)?\s*(?:by|at|for)\b|'
    r'\bpacked\s+(?:by|at)\b|\bmarketed\s+by\b|\bimported\s+by\b|\bcountry\s+of\s+origin\b|\bmade\s+in\b|'
    r'\bnet\s*(?:wt\.?|weight|qty\.?|quantity|content|contents|vol\.?|volume)\b|\bquantity\b|'
    r'\bm\.?\s*r\.?\s*p\.?|\bmaximum\s+retail\s+price\b|'
    r'\bbatch\s*(?:no\.?|number)?\b|\bb\.?\s*no\.?\b|\blot\s+(?:no\.?|number)?\b|\blot\s*[:#]|'
    r'\buse\s*-?\s*(?:by|before)\b|\bbest\s+before\b|\bbest\s+by\b|\bconsume\s+before\b|'
    r'\bdate\s+of\s+(?:manufactur\w+|pack\w+)\b|\bmfg\s*date\b|\bmfd\s*date\b|\bpkd\s*date\b|\bpkg\s*date\b|\bpacked\s+on\b|'
    r'\bexpiry(?:\s+date)?\b|\bexp(?:\.|\s*date|:)|'
    r'\bconsumer\s+care\b|\bcustomer\s+care\b|\bcustomer\s+support\b|\bhelpline\b|\btoll\s*free\b|\bwrite\s+to\b|\bcall\s+us\s+at\b|\bcall\s+us\b|'
    r'\bingredients?\b|\bcomposition\b|\bingredient\s+list\b|'
    r'\bnutritional?\s*(?:information|facts)\b|\bserv(?:e|ing)\s*size\b|'
    r'\bcontainer\s+once\s+opened\b|\bstore\s+in\b|\bcool\s*(?:&|and)?\s*dry\s+place\b|'
    r"\bsweet'?n\s*sour\b|\bpremium\s+quality\b|"
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
        r'\b(?:manufactured\s*(?:&|and|/)?\s*(?:marketed|packed)?\s*(?:by|at|for)|mfg\s*(?:&|and|/)?\s*(?:mkt|pkd)?\s*by|mfd\s*(?:&|and|/)?\s*(?:mkt|pkd)?\s*by|manufacturer\b|made\s+by\b)',
    ],
    'marketer': [
        r'\b(?:marketed\s*(?:&|and)?\s*(?:distributed)?\s*(?:by|at|for)|mkt\s*by|mktg\s*by|mkt\.\s*by|marketer\b|distributed\s+by\b)',
    ],
    'packer': [
        r'\b(?:packed\s*(?:&|and)?\s*(?:marketed)?\s*(?:by|at|for)|packed\s+(?:by|at)|pkd\s*by|pkg\s*by|packer\b|packaged\s+by\b)',
    ],
    'importer': [
        r'\b(?:imported\s+by|importer\b)',
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
        r'\b(?:batch\s*(?:no\.?|number)?|lot\s+(?:no\.?|number)?|lot\s*[:#]|b\.?\s*no\.?)\b',
    ],
    'date': [
        r'\b(?:date\s+of\s+(?:manufactur\w+|pack\w+)|mfg\s*date|mfd\s*date|pkd\s*date|pkg\s*date|packed\s+on|mfd[:.]|mfg[:.]|pkd[:.]|best\s+before|best\s+by|use\s*-?\s*(?:by|before)|consume\s+before|expiry(?:\s+date)?|exp(?:\.|\s*date|:))\b',
    ],
    'consumer_care': [
        r'\b(?:consumer\s*care|customer\s*care|customer\s*support|helpline|toll\s*free|call\s+us\s+at|call\s+us|contact(?:\s+us)?|write\s+to|feedback)\b',
        r'\b(?:1800[\s\-]?\d{3}[\s\-]?\d{3,4}|\b\d{3,5}[\s\-]\d{6,10}|\b0\d{2,4}[\s\-]?\d{6,8})\b',
    ],
    'nutrition': [
        r'\b(?:nutritional\s+information|nutrition\s+facts|nutritional\s+facts|per\s+(?:100\s*g|serving)|energy\s*:|protein\s*:|carbohydrate\s*:)\b',
        r'\b(?:serving\s*size|serve\s*size|per\s+serve|nutrients?)\b',
    ],
    'storage': [
        r'\b(?:container\s+once\s+opened|store\s+in|keep\s+(?:in|away)|cool\s*(?:&|and)?\s*dry\s+place|refrigerat\w*|avoid\s+sunlight|do\s+not\s+store)\b',
    ],
    'marketing': [
        r"\b(?:sweet'?n\s*sour|crispy\s*(?:&|and)\s*crunchy|delicious|tasty|premium\s+quality|100\s*%\s*(?:pure|natural)|no\s+added)\b",
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


def classify_line_section(line: str, current_section: Optional[str] = None) -> str:
    """Classify an OCR text line into its semantic section."""
    cleaned = line.strip()
    if not cleaned:
        return current_section or SECTION_OTHER

    if NUTRITION_SECTION_HEADER_RE.search(cleaned):
        return SECTION_NUTRITION
    if SERVING_SIZE_RE.search(cleaned):
        return SECTION_SERVING_SIZE
    if NET_QTY_POSITIVE_CONTEXT_RE.search(cleaned):
        return SECTION_DECLARED_QUANTITY
    if INGREDIENTS_LINE_RE.search(cleaned):
        return SECTION_INGREDIENTS
    if any(re.search(rf'(?:\b|(?<=^)){re.escape(kw)}\b', cleaned, re.I) for kw in PACKER_KEYWORDS) and re.search(r'\b(?:packed|pkd|pkg|packer)\b', cleaned, re.I):
        return SECTION_PACKER
    if any(re.search(rf'(?:\b|(?<=^)){re.escape(kw)}\b', cleaned, re.I) for kw in MARKETER_KEYWORDS) and re.search(r'\b(?:marketed|mkt|mktg|marketer|distributed)\b', cleaned, re.I):
        return SECTION_MARKETER
    if any(re.search(rf'(?:\b|(?<=^)){re.escape(kw)}\b', cleaned, re.I) for kw in MANUFACTURER_KEYWORDS) or COMPANY_SUFFIX_RE.search(cleaned):
        return SECTION_MANUFACTURER
    if CONSUMER_CARE_STOP_RE.search(cleaned):
        return SECTION_CONSUMER_CARE
    if STORAGE_STOP_RE.search(cleaned):
        return SECTION_STORAGE
    if MARKETING_STOP_RE.search(cleaned):
        return SECTION_MARKETING
    if re.search(r'\b(?:m\.?\s*r\.?\s*p\.?|maximum\s+retail\s+price)\b', cleaned, re.I):
        return SECTION_MRP
    if re.search(r'\b(?:fssai|lic\.?\s*(?:no\.?|number)?)\b', cleaned, re.I):
        return SECTION_FSSAI
    if re.search(r'\b(?:batch\s*(?:no\.?|number)?|lot\s*(?:no\.?|number)?|b\.?\s*no\.?)\b', cleaned, re.I):
        return SECTION_BATCH
    if any(re.search(rf'(?:\b|(?<=^)){re.escape(kw)}\b', cleaned, re.I) for kw in ALL_DATE_LABELS):
        return SECTION_DATE
    if re.search(r'\b(?:directions?\s+for\s+use|how\s+to\s+use|instructions?)\b', cleaned, re.I):
        return SECTION_INSTRUCTIONS
    if re.search(r'\b(?:barcode|ean|upc)\b', cleaned, re.I):
        return SECTION_BARCODE

    # Section continuity
    if current_section == SECTION_NUTRITION:
        # Check if line breaks out of nutrition into a multipack expression
        if re.search(r'\b\d+\s*(?:[×xX*✕✖⨯]|\bof\b)\s*[+-]?\d+(?:\.\d+)?\s*(?:g|gm|gms|grams?|kg|kgs?|ml|millilitres?|l|litres?)\b', cleaned, re.I) and not NUTRITION_LINE_RE.search(cleaned):
            return SECTION_DECLARED_QUANTITY
        if NUTRITION_LINE_RE.search(cleaned) or re.search(r'\b\d+(?:\.\d+)?\s*(?:g|mg|kcal|kj|%)\b', cleaned, re.I):
            return SECTION_NUTRITION
        if re.fullmatch(r'[\d.,\s/%+-]+', cleaned) or len(cleaned.split()) <= 4:
            return SECTION_NUTRITION
    elif current_section in (SECTION_MANUFACTURER, SECTION_PACKER, SECTION_ADDRESS):
        if re.search(r'(?:plot|survey|sector|phase|road|street|bldg|building|floor|estate|industrial|gidc|district|dist|pin|india)', cleaned, re.I):
            return SECTION_ADDRESS

    return SECTION_OTHER


def detect_semantic_sections(lines: List[str], ocr_items: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Segment document text lines into semantic packaging sections with bounding boxes and metadata."""
    current_sec = SECTION_OTHER
    annotated: List[Dict[str, Any]] = []
    for idx, line in enumerate(lines):
        line_clean = line.strip()
        if not line_clean:
            continue
        sec = classify_line_section(line_clean, current_sec)
        current_sec = sec
        bbox = None
        conf = 0.8
        if ocr_items:
            matching_item = next(
                (item for item in ocr_items if line_clean.lower() in str(item.get('text', '')).lower()),
                None,
            )
            if matching_item:
                bbox = matching_item.get('bbox')
                conf = float(matching_item.get('confidence') or 0.8)
        annotated.append({
            'line_index': idx,
            'text': line_clean,
            'section_type': sec,
            'bbox': bbox,
            'confidence': conf,
        })
    return annotated


def _normalize_text(raw_text: str) -> str:
    text = raw_text.replace('\r', '\n')
    text = text.replace('₹', ' Rs ')
    text = text.replace('â¹', ' Rs ')
    text = text.replace('–', '-')
    # Universal OCR repairs: standard whitespace, punctuation, and legal abbreviations
    repairs = (
        (r'\bGREDIENTS\b', 'INGREDIENTS'),
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


def parse_date_with_precision(date_str: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """Parse a date string and determine its precision (FULL_DATE vs MONTH_YEAR).

    Returns:
        (is_valid, normalized_date_string, metadata_dict)
    """
    if not date_str or not _is_valid_date_token(date_str):
        return False, None, None

    token = date_str.strip()
    month_names = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }

    # Check for text month
    m_text = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*', token, re.IGNORECASE)
    if m_text:
        month_str = m_text.group(1).lower()
        month = month_names.get(month_str, 1)
        nums = [int(n) for n in re.findall(r'\d+', token)]
        if len(nums) == 1:
            year = nums[0]
            if year < 100:
                year += 2000 if year <= 50 else 1900
            if not (1990 <= year <= 2099):
                return False, None, None
            norm = f"{month:02d}/{year}"
            return True, norm, {
                "precision": DatePrecision.MONTH_YEAR.value,
                "raw_text": date_str,
                "normalized_date": norm,
                "parsed_components": {"month": month, "year": year}
            }
        elif len(nums) == 2:
            day, year = nums
            if year < 100:
                year += 2000 if year <= 50 else 1900
            if not (1 <= day <= 31 and 1990 <= year <= 2099):
                return False, None, None
            norm = f"{day:02d}/{month:02d}/{year}"
            return True, norm, {
                "precision": DatePrecision.FULL_DATE.value,
                "raw_text": date_str,
                "normalized_date": norm,
                "parsed_components": {"day": day, "month": month, "year": year}
            }
        return False, None, None

    # Numeric parts separated by /, -, or .
    parts = [p for p in re.split(r'[/.-]', token) if p != '']
    if len(parts) not in (2, 3):
        return False, None, None

    try:
        numbers = [int(p) for p in parts]
    except ValueError:
        return False, None, None

    if len(parts) == 2:
        first, second = numbers
        p1_len, p2_len = len(parts[0]), len(parts[1])
        if p1_len == 4 and (1990 <= first <= 2099) and (1 <= second <= 12):
            year, month = first, second
        elif 1 <= first <= 12:
            month = first
            year = second
            if p2_len == 2:
                year += 2000 if year <= 50 else 1900
            if not (1990 <= year <= 2099):
                return False, None, None
        else:
            return False, None, None

        norm = f"{month:02d}/{year}"
        return True, norm, {
            "precision": DatePrecision.MONTH_YEAR.value,
            "raw_text": date_str,
            "normalized_date": norm,
            "parsed_components": {"month": month, "year": year}
        }

    if len(parts) == 3:
        p1_len, p2_len, p3_len = len(parts[0]), len(parts[1]), len(parts[2])
        if p1_len == 4 and (1990 <= numbers[0] <= 2099) and (1 <= numbers[1] <= 12) and (1 <= numbers[2] <= 31):
            year, month, day = numbers[0], numbers[1], numbers[2]
        elif (1 <= numbers[0] <= 31) and (1 <= numbers[1] <= 12):
            day, month = numbers[0], numbers[1]
            year = numbers[2]
            if p3_len == 2:
                year += 2000 if year <= 50 else 1900
            if not (1990 <= year <= 2099):
                return False, None, None
        else:
            return False, None, None

        norm = f"{day:02d}/{month:02d}/{year}"
        return True, norm, {
            "precision": DatePrecision.FULL_DATE.value,
            "raw_text": date_str,
            "normalized_date": norm,
            "parsed_components": {"day": day, "month": month, "year": year}
        }

    return False, None, None


def _is_disallowed_product_name_line(line: str) -> bool:
    """Reject corporate entities, brand-only tokens, ingredient lists, botanical Latin names,
    batch IDs, licenses, addresses, and decorative slogans from becoming PRODUCT_NAME.
    """
    line_clean = line.strip()
    if not line_clean:
        return True

    lower = line_clean.lower()

    # 1. Corporate entities / Manufacturers / Packers / Marketers
    if COMPANY_SUFFIX_RE.search(line_clean) or VENDOR_PREFIX_RE.search(line_clean):
        return True
    if re.search(r'\b(?:pvt\.?\s*ltd|private\s+limited|limited\b|ltd\b|llp\b|corp\b|corporation\b|inc\b|mfg|mfd|manufactur\w*|pack\w*|market\w*|import\w*)\b', lower):
        return True

    # 2. Ingredient lists or composition headers
    if INGREDIENTS_LINE_RE.search(line_clean) or re.search(r'\b(?:ingredients?|contains?|composition)\s*[:.]', lower):
        return True

    # 3. Botanical / Latin binomial names
    # e.g., (Azadirachta indica), Camellia sinensis, Mangifera indica, Linn., etc.
    if re.search(r'\b(?:[A-Z][a-z]+\s+(?:indica|sativa|sinensis|officinalis|vulgaris|sanctum|tinctoria|zeylanica|sp\.|var\.)|\([A-Z][a-z]+\s+[a-z]+\))\b', line_clean):
        return True

    # 4. Batch IDs, FSSAI licenses, dates, pricing, net quantity
    if re.search(r'\b(?:batch\s*(?:no\.?|number)?|b\.?\s*no\.?|lot\s*(?:no\.?|number)?|fssai|lic\.?\s*(?:no\.?|number)?|regd?\s*no\.?)\b', lower):
        return True
    if re.search(r'\b(?:m\.?r\.?p\.?|₹|rs\.?|inr|exp(?:iry)?|mfd|pkd|use\s*by|best\s*before)\b', lower):
        return True
    if re.search(r'\b\d+\s*(?:g|kg|ml|l|ltr|gm|pieces?|tablets?)\b', lower):
        return True

    # 5. Addresses & Locations
    if re.search(r'\b(?:plot\s*(?:no\.?)?|survey\s*(?:no\.?)?|sector\b|phase\s+[ivx0-9]+|gidc|industrial\s*area|pin(?:code)?\s*[:.\s-]*\d{6})\b', lower):
        return True

    # 6. Decorative marketing slogans
    if any(lower == term.lower() for term in MARKETING_TERMS):
        return True
    if re.search(r'^(?:100\s*%\s*(?:pure|natural|veg(?:etarian)?)|best\s+quality|premium\s+quality|original\s+taste|fresh\s+and\s+pure|delicious\s+taste|new\s+look)$', lower):
        return True

    return False


def _extract_product_name_candidates(
    lines: List[str],
    ocr_items: Optional[List[Dict[str, Any]]] = None
) -> Tuple[Optional[str], List[Dict[str, Any]], str]:
    """Score front-label candidates and detect ambiguity when multiple plausible candidates exist.

    Returns:
        (primary_candidate, competing_candidates, status)
        where status is 'VALID' or 'AMBIGUOUS'.
    """
    scored = []
    for index, line in enumerate(lines[:25]):
        if _is_disallowed_product_name_line(line):
            continue
        words = re.findall(r"[A-Za-z][A-Za-z&'-]*", line)
        lowered = [w.lower() for w in words]
        if not words or len(words) > 8 or ':' in line:
            continue
        if any(w in MARKETING_TERMS for w in lowered) and len(words) <= 3:
            continue

        score = 1.0 + max(0, 8 - index) * 0.08
        if re.search(r'\b(?:salt|sugar|biscuit|oil|tea|soap|shampoo|cream|flour|rice|masala|juice|toothpaste|noodles)\b', line, re.I):
            score += 4.0

        if ocr_items:
            item = next((x for x in ocr_items if str(x.get('text', '')).strip().lower() == line.lower()), None)
            if item:
                score += float(item.get('confidence') or 0)
                bbox = item.get('bbox') or []
                if len(bbox) == 4:
                    all_ys = [it.get('bbox')[1] for it in ocr_items if len(it.get('bbox') or []) == 4]
                    max_y = max(all_ys) if all_ys else 1
                    min_y = min(all_ys) if all_ys else 0
                    y_range = max_y - min_y if max_y > min_y else 1
                    if (bbox[1] - min_y) / y_range < 0.6:
                        score += 0.5
        scored.append((score, line))

    if not scored:
        return None, [], "VALID"

    scored.sort(key=lambda item: item[0], reverse=True)
    top_score, top_cand = scored[0]

    competing = []
    for s, c in scored[1:4]:
        if s >= 1.0 and _product_names_conflict(top_cand, c) and (s / top_score) > 0.70:
            competing.append(c)

    if competing:
        all_competing = [top_cand] + [c for c in competing if c != top_cand]
        return top_cand, all_competing, "AMBIGUOUS"

    return top_cand, [], "VALID"


def _product_candidate(lines: List[str], ocr_items: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """Score front-label candidates; do not let a marketing adjective become a product."""
    cand, _, _ = _extract_product_name_candidates(lines, ocr_items)
    return cand


def _extract_consumer_care_structured(lines: List[str], text: str) -> Optional[Dict[str, Any]]:
    """Extract clean, structured consumer care contact channels.

    Finds toll-free phone, telephone/mobile, email, website, and postal contacts.
    Never appends arbitrary continuation lines or unrelated trailing text.
    """
    contacts: List[Dict[str, str]] = []
    seen_contacts = set()

    def _add_contact(c_type: str, c_val: str):
        key = (c_type, c_val.lower().strip())
        if key not in seen_contacts:
            seen_contacts.add(key)
            contacts.append({"contact_type": c_type, "contact_value": c_val.strip()})

    # 1. Search for toll-free numbers across lines and text
    tf_pattern = re.compile(r'\b(1800[\s\-]?\d{3}[\s\-]?\d{3,4})\b')
    for m in tf_pattern.finditer(text):
        _add_contact(ContactType.TOLL_FREE.value, m.group(1).replace(' ', '-'))

    # 2. Search for email addresses
    email_pattern = re.compile(r'\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b')
    for m in email_pattern.finditer(text):
        _add_contact(ContactType.EMAIL.value, m.group(1))

    # 3. Search for websites (avoiding generic word matching)
    web_pattern = re.compile(r'\b(https?://[^\s,;]+|www\.[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}(?:/[^\s,;]*)?)\b', re.I)
    for m in web_pattern.finditer(text):
        _add_contact(ContactType.WEBSITE.value, m.group(1))

    # 4. Search for phone / helpline numbers specifically linked to consumer care / helpline context
    phone_prefix_pattern = re.compile(
        r'(?:(?:helpline|toll\s*free|call\s*us(?:\s*at)?|ph(?:one)?|tel(?:ephone)?|contact(?:\s*no\.?)?|mobile)\s*[:.\s-]*)\s*([+]?[0-9\s\-]{8,15})',
        re.I
    )
    for m in phone_prefix_pattern.finditer(text):
        raw_num = m.group(1).strip()
        digits = re.sub(r'\D', '', raw_num)
        if 8 <= len(digits) <= 12 and not raw_num.startswith('1800'):
            _add_contact(ContactType.PHONE.value, raw_num)

    # 5. Check if any line explicitly identifies Consumer Care Cell / address
    matched_label_line = None
    for idx, line in enumerate(lines):
        lower = line.lower()
        if any(kw in lower for kw in ('consumer care', 'customer care', 'customer support', 'write to:')):
            matched_label_line = line
            after_kw = line
            for kw in ('consumer care cell', 'consumer care', 'customer care', 'customer support', 'write to'):
                if kw in lower:
                    pos = lower.find(kw) + len(kw)
                    after_kw = line[pos:].strip(' :;,-')
                    break
            if after_kw and not any(ch in after_kw for ch in ('@', 'www.', 'http')):
                clean_target = _clean_address_text(after_kw)
                if clean_target and len(clean_target) > 5:
                    _add_contact(ContactType.POSTAL.value, clean_target)
            break

    if not contacts:
        cc_match = _search_patterns(text, CONSUMER_CARE_PATTERNS)
        if cc_match:
            val_clean = cc_match.strip(' :;,-')
            if '@' in val_clean:
                _add_contact(ContactType.EMAIL.value, val_clean)
            elif re.search(r'\d{6,}', val_clean):
                _add_contact(ContactType.PHONE.value, val_clean)
            else:
                _add_contact(ContactType.CONSUMER_CARE_CELL.value, val_clean)

    if not contacts and not matched_label_line:
        return None

    type_priority = {
        ContactType.TOLL_FREE.value: 1,
        ContactType.PHONE.value: 2,
        ContactType.EMAIL.value: 3,
        ContactType.WEBSITE.value: 4,
        ContactType.POSTAL.value: 5,
        ContactType.CONSUMER_CARE_CELL.value: 6,
    }
    contacts.sort(key=lambda c: type_priority.get(c["contact_type"], 99))

    primary = contacts[0] if contacts else {"contact_type": "CONSUMER_CARE_CELL", "contact_value": matched_label_line or "Consumer Care"}
    
    val_strs = [c["contact_value"] for c in contacts[:2]]
    val_summary = None
    if matched_label_line:
        lower_lbl = matched_label_line.lower()
        for kw in ('consumer care cell', 'consumer care', 'customer care', 'customer support', 'helpline', 'toll free', 'call us', 'write to'):
            if kw in lower_lbl:
                pos = lower_lbl.find(kw) + len(kw)
                cand_after = matched_label_line[pos:].strip(' :;,-')
                cand_after = _cut_before_next_section(cand_after, 'consumer_care')
                if cand_after:
                    if any(ch in cand_after for ch in ('@', 'www.', 'http')) or re.search(r'\d{4,}', cand_after):
                        val_summary = cand_after
                    elif val_strs:
                        val_summary = f"{cand_after}, {', '.join(val_strs)}"
                    else:
                        val_summary = cand_after
                break
    if not val_summary:
        val_summary = ', '.join(val_strs) if val_strs else primary["contact_value"]

    return build_consumer_care_candidate(
        value=val_summary,
        raw_text=matched_label_line or val_summary,
        contacts=contacts,
        primary_contact_type=primary["contact_type"],
        primary_contact_value=primary["contact_value"],
        confidence=0.8,
        source='OCR',
    )


def _extract_price_number(text: str) -> Optional[float]:
    """Extract numeric price value from price string e.g. '₹120', 'Rs 140.50'."""
    if not text:
        return None
    cleaned = str(text).replace(',', '')
    match = re.search(r'(\d+(?:\.\d{1,2})?)', cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _product_names_conflict(s1: str, s2: str) -> bool:
    """Determine whether two product or brand names contradict each other."""
    c1 = re.sub(r'[^\w\s]', '', str(s1).lower()).strip()
    c2 = re.sub(r'[^\w\s]', '', str(s2).lower()).strip()
    if not c1 or not c2 or c1 == c2:
        return False
    stop_words = {'the', 'a', 'an', 'and', '&', 'net', 'pack', 'package', 'pouch', 'bottle', 'box'}
    words1 = [w for w in c1.split() if w not in stop_words]
    words2 = [w for w in c2.split() if w not in stop_words]
    if not words1 or not words2:
        return False
    set1, set2 = set(words1), set(words2)
    if set1 == set2:
        return False
    overlap = set1.intersection(set2)
    union = set1.union(set2)
    similarity = len(overlap) / len(union) if union else 1.0
    return similarity < 0.6


def _values_conflict(field_name: str, cand1: Dict[str, Any], cand2: Dict[str, Any]) -> bool:
    """Determine whether two candidate extractions for the same field represent conflicting evidence."""
    v1 = cand1.get('value')
    v2 = cand2.get('value')
    if v1 is None or v2 is None:
        return False
    s1 = str(v1).strip()
    s2 = str(v2).strip()
    if not s1 or not s2:
        return False
    if s1.lower() == s2.lower():
        return False

    # 1. Price / MRP comparison
    if field_name == 'MRP':
        p1 = _extract_price_number(s1)
        p2 = _extract_price_number(s2)
        if p1 is not None and p2 is not None:
            return abs(p1 - p2) > 0.01
        return s1.lower() != s2.lower()

    # 2. Declared Net Quantity comparison
    if field_name == 'DECLARED_NET_QUANTITY':
        is_multi1 = bool(cand1.get('is_multipack'))
        is_multi2 = bool(cand2.get('is_multipack'))

        # A. Multipack vs Multipack
        if is_multi1 and is_multi2:
            cnt1 = cand1.get('pack_count')
            cnt2 = cand2.get('pack_count')
            uq1 = cand1.get('unit_net_quantity')
            uq2 = cand2.get('unit_net_quantity')
            u1 = str(cand1.get('quantity_unit') or cand1.get('unit') or '').lower().strip()
            u2 = str(cand2.get('quantity_unit') or cand2.get('unit') or '').lower().strip()

            if cnt1 is not None and cnt2 is not None and cnt1 != cnt2:
                return True
            if uq1 is not None and uq2 is not None:
                try:
                    if abs(float(uq1) - float(uq2)) > 0.001:
                        return True
                except (ValueError, TypeError):
                    pass
            if u1 and u2 and u1 != u2:
                return True
            return False

        # B. Multipack vs Single Quantity (Packaging Hierarchy: Outer Package vs Inner Unit)
        if is_multi1 != is_multi2:
            multi_cand = cand1 if is_multi1 else cand2
            single_cand = cand2 if is_multi1 else cand1

            s_val = single_cand.get('quantity_value') or single_cand.get('numeric_value')
            s_unit = str(single_cand.get('quantity_unit') or single_cand.get('unit') or '').lower().strip()
            m_unit = str(multi_cand.get('quantity_unit') or multi_cand.get('unit') or '').lower().strip()

            if s_val is not None:
                try:
                    s_float = float(s_val)
                    m_unit_qty = float(multi_cand.get('unit_net_quantity') or 0)
                    m_total_qty = float(multi_cand.get('derived_total_quantity') or 0)

                    unit_matches = not s_unit or not m_unit or s_unit == m_unit
                    matches_unit = abs(s_float - m_unit_qty) <= 0.001
                    matches_total = abs(s_float - m_total_qty) <= 0.001

                    if unit_matches and (matches_unit or matches_total):
                        # Complementary hierarchy: outer multipack breakdown vs inner unit or derived total
                        return False
                    else:
                        # Genuine conflict between declarations
                        return True
                except (ValueError, TypeError):
                    pass

        # C. Single Quantity vs Single Quantity
        qv1 = cand1.get('quantity_value')
        qv2 = cand2.get('quantity_value')
        qu1 = str(cand1.get('quantity_unit') or '').lower().strip()
        qu2 = str(cand2.get('quantity_unit') or '').lower().strip()
        if qv1 is not None and qv2 is not None:
            try:
                if abs(float(qv1) - float(qv2)) > 0.001:
                    return True
                if qu1 and qu2 and qu1 != qu2:
                    return True
                return False
            except (ValueError, TypeError):
                pass
        p1 = _extract_price_number(s1)
        p2 = _extract_price_number(s2)
        if p1 is not None and p2 is not None and abs(p1 - p2) > 0.001:
            return True
        return s1.lower() != s2.lower()

    # 3. Dates comparison (month/year)
    if field_name in (
        'MONTH_YEAR_MANUFACTURE', 'MANUFACTURE_DATE', 'PACKING_DATE',
        'BEST_BEFORE_USE_BY', 'USE_BEFORE_DATE', 'EXPIRY_DATE'
    ):
        m1 = cand1.get('month') or cand1.get('extracted_month')
        y1 = cand1.get('year') or cand1.get('extracted_year')
        m2 = cand2.get('month') or cand2.get('extracted_month')
        y2 = cand2.get('year') or cand2.get('extracted_year')
        if m1 and m2 and y1 and y2:
            return (m1, y1) != (m2, y2)
        d1_m = re.findall(r'\b(0?[1-9]|1[0-2])[/-](\d{2,4})\b', s1)
        d2_m = re.findall(r'\b(0?[1-9]|1[0-2])[/-](\d{2,4})\b', s2)
        if d1_m and d2_m:
            return d1_m[0] != d2_m[0]
        return s1.lower() != s2.lower()

    # 4. Product Name and Brand
    if field_name in ('PRODUCT_NAME', 'BRAND'):
        return _product_names_conflict(s1, s2)

    # 5. FSSAI License Number (digits)
    if field_name == 'FSSAI_LICENSE':
        dig1 = re.findall(r'\d{14}', s1)
        dig2 = re.findall(r'\d{14}', s2)
        if dig1 and dig2:
            return dig1[0] != dig2[0]
        return s1.lower() != s2.lower()

    # Default fallback: cleaned alphanumeric comparison
    c1 = re.sub(r'[^\w\s]', '', s1.lower()).strip()
    c2 = re.sub(r'[^\w\s]', '', s2.lower()).strip()
    return c1 != c2


def merge_product_evidence(
    fields: Dict[str, Any],
    raw_text: str,
    ocr_items: Optional[List[Dict[str, Any]]],
    barcode_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge barcode lookup as supplementary evidence without silently overwriting OCR or product identity."""
    lookup = (barcode_result or {}).get('lookup') or {}
    barcode_value = (barcode_result or {}).get('value')
    if barcode_value:
        fields['BARCODE'] = {
            'value': barcode_value,
            'confidence': (barcode_result or {}).get('confidence', 0.7),
            'source': (barcode_result or {}).get('source', 'BARCODE'),
        }

    if lookup.get('status') != 'FOUND':
        return fields

    product_name = str(lookup.get('product_name') or '').strip()
    brand = str(lookup.get('brands') or '').split(',')[0].strip()

    # External database lookup is supplementary evidence, never legal proof
    fields['BARCODE_METADATA'] = {
        'product_name': product_name,
        'brand': brand,
        'source': 'BARCODE_LOOKUP',
        'evidence_type': 'SUPPLEMENTARY',
        'status': 'FOUND',
    }

    # Handle PRODUCT_NAME
    if product_name:
        current = fields.get('PRODUCT_NAME')
        if not current or not str(current.get('value', '')).strip():
            fields['PRODUCT_NAME'] = {
                'value': product_name[:200],
                'confidence': 0.85,
                'source': 'BARCODE_LOOKUP',
                'evidence_type': 'SUPPLEMENTARY',
                'is_supplementary': True,
            }
        elif current.get('value', '').lower() in MARKETING_TERMS:
            fields['PRODUCT_NAME'] = {
                'value': product_name[:200],
                'confidence': 0.85,
                'source': 'BARCODE_LOOKUP',
                'evidence_type': 'SUPPLEMENTARY',
                'is_supplementary': True,
            }
        else:
            if _values_conflict('PRODUCT_NAME', current, {'value': product_name}):
                # Barcode lookup contradicts printed OCR - surface contradiction without replacing OCR
                ocr_val = current.get('value')
                current['status'] = 'CONFLICTING_EVIDENCE'
                current['has_conflict'] = True
                current['barcode_match'] = 'CONFLICTS'
                current['values'] = [ocr_val, product_name]
                current['ocr_value'] = ocr_val
                current['barcode_value'] = product_name
                current['candidates'] = [
                    dict(current),
                    {
                        'value': product_name,
                        'source': 'BARCODE_LOOKUP',
                        'evidence_type': 'SUPPLEMENTARY',
                        'confidence': 0.75,
                    },
                ]
                current['conflict_reason'] = (
                    f"Printed OCR product name '{ocr_val}' contradicts barcode database lookup '{product_name}'."
                )
            else:
                current['barcode_match'] = 'AGREES'
                current['supplementary_evidence'] = {
                    'value': product_name,
                    'source': 'BARCODE_LOOKUP',
                    'evidence_type': 'SUPPLEMENTARY',
                }

    # Handle BRAND
    if brand:
        current = fields.get('BRAND')
        if not current or not str(current.get('value', '')).strip():
            fields['BRAND'] = {
                'value': brand[:200],
                'confidence': 0.85,
                'source': 'BARCODE_LOOKUP',
                'evidence_type': 'SUPPLEMENTARY',
                'is_supplementary': True,
            }
        elif current.get('value', '').lower() in MARKETING_TERMS:
            fields['BRAND'] = {
                'value': brand[:200],
                'confidence': 0.85,
                'source': 'BARCODE_LOOKUP',
                'evidence_type': 'SUPPLEMENTARY',
                'is_supplementary': True,
            }
        else:
            if _values_conflict('BRAND', current, {'value': brand}):
                ocr_val = current.get('value')
                current['status'] = 'CONFLICTING_EVIDENCE'
                current['has_conflict'] = True
                current['barcode_match'] = 'CONFLICTS'
                current['values'] = [ocr_val, brand]
                current['ocr_value'] = ocr_val
                current['barcode_value'] = brand
                current['candidates'] = [
                    dict(current),
                    {
                        'value': brand,
                        'source': 'BARCODE_LOOKUP',
                        'evidence_type': 'SUPPLEMENTARY',
                        'confidence': 0.75,
                    },
                ]
                current['conflict_reason'] = (
                    f"Printed OCR brand '{ocr_val}' contradicts barcode database lookup '{brand}'."
                )
            else:
                current['barcode_match'] = 'AGREES'
                current['supplementary_evidence'] = {
                    'value': brand,
                    'source': 'BARCODE_LOOKUP',
                    'evidence_type': 'SUPPLEMENTARY',
                }

    if product_name and 'GENERIC_NAME' not in fields:
        tokens = [
            token for token in re.findall(r'[A-Za-z]+', product_name)
            if token.lower() not in {word.lower() for word in brand.split()}
        ]
        if tokens:
            fields['GENERIC_NAME'] = {
                'value': tokens[-1].upper(),
                'confidence': 0.78,
                'source': 'BARCODE_LOOKUP',
                'evidence_type': 'SUPPLEMENTARY',
            }

    return fields


# ---------------------------------------------------------------------------
# Semantic context detection for candidate classification
# ---------------------------------------------------------------------------
NUTRITION_CONTEXT_RE = re.compile(
    r'(?:'
    r'\bserv(?:e|ing)\s*size\b|\bper\s+(?:\d+\s*g|serving)\b|'
    r'\bnutrition(?:al)?\s*(?:information|facts|value)?\b|'
    r'\b(?:energy|protein|carbohydrate|fat|sugar|fibre|fiber|sodium|cholesterol|calcium|iron|vitamin)\s*[:\(]|'
    r'\bkcal\b|\bkj\b|'
    r'\btotal\s+(?:sugar|fat|carbohydrate|energy)\b|'
    r'\bper\s+100\s*(?:g|ml)\b'
    r')',
    re.IGNORECASE,
)

STORAGE_CONTEXT_RE = re.compile(
    r'(?:'
    r'\bcontainer\s+once\s+opened\b|\bstore\s+in\b|\bkeep\s+(?:in|away)\b|'
    r'\bcool\s*(?:,|&|and)?\s*dry\s+place\b|\brefrigerat\w*\b|'
    r'\bavoid\s+(?:direct\s+)?sunlight\b|\bdo\s+not\s+(?:store|keep)\b'
    r')',
    re.IGNORECASE,
)

MARKETING_CONTEXT_RE = re.compile(
    r'(?:'
    r"\bsweet'?n\s*sour\b|\bcrispy\s*(?:&|and)\s*crunchy\b|"
    r'\bdelicious\b|\btasty\b|\bpremium\s+quality\b|'
    r'\b(?:100|pure)\s*%\s*(?:natural|pure|vegetarian)\b|'
    r'\bno\s+added\s+(?:preservative|colour|flavor)\b|'
    r'\b(?:new|improved)\s+(?:taste|formula|recipe)\b'
    r')',
    re.IGNORECASE,
)

CONTACT_CONTEXT_RE = re.compile(
    r'(?:'
    r'\bcall\s+us\s+at\b|\btoll\s*free\b|\b(?:phone|tel|fax)\s*[:\s]\b|'
    r'\b(?:email|e-mail)\s*[:\s]\b|\bwww\.\b|\bhttp\b|'
    r'\bconsumer\s*care\b|\bcustomer\s*care\b|\bhelpline\b|'
    r'\bwrite\s+to\b|\bfeedback\b'
    r')',
    re.IGNORECASE,
)


def _fuzzy_ocr_similar(s1: str, s2: str, threshold: float = 0.65) -> bool:
    """Detect if two strings are OCR character-error variations of the same underlying text.

    Uses character-level bigram similarity (Dice coefficient).
    E.g. 'COMPANYFOODS' vs 'COMPANY FOODS' share most bigrams.
    """
    def _bigrams(s: str) -> list:
        cleaned = re.sub(r'[^a-z0-9]', '', s.lower())
        return [cleaned[i:i+2] for i in range(len(cleaned) - 1)] if len(cleaned) >= 2 else []

    bg1 = _bigrams(s1)
    bg2 = _bigrams(s2)
    if not bg1 or not bg2:
        return False
    # Dice coefficient
    from collections import Counter
    c1, c2 = Counter(bg1), Counter(bg2)
    overlap = sum((c1 & c2).values())
    total = sum(c1.values()) + sum(c2.values())
    similarity = (2.0 * overlap) / total if total else 0.0
    return similarity >= threshold


def _is_irrelevant_candidate(field_name: str, candidate: Dict[str, Any]) -> bool:
    """Check if a candidate value is contextually irrelevant for its claimed field.

    Returns True if the candidate should be excluded from conflict evaluation.
    """
    val = str(candidate.get('value') or '').strip()
    raw = str(candidate.get('raw_text') or candidate.get('value') or '').strip()
    # Surrounding context from the source line/text
    context = str(candidate.get('source_context') or candidate.get('context') or raw)
    sec = candidate.get('semantic_section')
    rel = candidate.get('relevance')
    rel_score = candidate.get('relevance_score')

    if not val:
        return True

    if rel == 'rejected_as_irrelevant':
        return True

    if rel_score is not None and float(rel_score) <= 0.2 and field_name in ('DECLARED_NET_QUANTITY', 'NET_QUANTITY'):
        return True

    if field_name in ('DECLARED_NET_QUANTITY', 'NET_QUANTITY'):
        if sec in (SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_INGREDIENTS):
            return True
        # Reject nutrition/serving-size quantities
        if NUTRITION_CONTEXT_RE.search(context) or SERVING_SIZE_RE.search(context) or NUTRITION_LINE_RE.search(context):
            return True
        # Reject isolated single digits without units (OCR noise like "2")
        if re.fullmatch(r'\d{1,2}', val) and not re.search(r'[a-zA-Z]', val):
            return True
        # Reject if the context line is clearly a nutrition row
        if re.search(r'\b(?:sugar|protein|fat|carbohydrate|fibre|fiber|energy|cholesterol|sodium|calcium)\b', context, re.IGNORECASE):
            return True
        # Serving size indicator
        if re.search(r'\bserv(?:e|ing)\s*size\b', context, re.IGNORECASE):
            return True

    elif field_name == 'MANUFACTURER_NAME':
        if sec in (SECTION_MARKETING, SECTION_NUTRITION, SECTION_STORAGE, SECTION_CONSUMER_CARE):
            return True
        # Reject marketing slogans, nutrition rows, storage instructions
        if MARKETING_CONTEXT_RE.search(context) or NUTRITION_CONTEXT_RE.search(context):
            return True
        if STORAGE_CONTEXT_RE.search(context):
            return True
        if CONTACT_CONTEXT_RE.search(context):
            return True

    elif field_name == 'MANUFACTURER_ADDRESS':
        if sec in (SECTION_MARKETING, SECTION_NUTRITION, SECTION_STORAGE, SECTION_CONSUMER_CARE):
            return True
        # Reject storage instructions, marketing, contact lines
        if STORAGE_CONTEXT_RE.search(val) or MARKETING_CONTEXT_RE.search(val):
            return True
        if CONTACT_CONTEXT_RE.search(val):
            return True
        # Reject if it looks like a nutrition/serving line
        if NUTRITION_CONTEXT_RE.search(val) or NUTRITION_LINE_RE.search(val):
            return True

    elif field_name == 'PRODUCT_NAME':
        if sec == SECTION_NUTRITION:
            return True
        # Reject nutrition table rows
        if NUTRITION_CONTEXT_RE.search(val) or NUTRITION_LINE_RE.search(val):
            return True
        # Reject very short low-confidence fragments (likely OCR noise)
        conf = float(candidate.get('confidence') or 0)
        if len(val) <= 3 and conf < 0.7:
            return True

    elif field_name == 'MRP':
        if sec in (SECTION_NUTRITION, SECTION_CONSUMER_CARE):
            return True
        if NUTRITION_CONTEXT_RE.search(context) or NUTRITION_LINE_RE.search(context):
            return True
        digits_only = re.sub(r'\D', '', val)
        if len(digits_only) >= 10 and not re.search(r'(?:mrp|price|₹|rs)', context, re.I):
            return True

    return False


def _classify_multi_image_evidence(
    field_name: str,
    groups: List[List[Dict[str, Any]]],
    all_candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Classify multi-group evidence for a field into TRUE_CONFLICT, REVIEW, or MULTI_PANEL_EVIDENCE.

    Args:
        field_name: The declaration field being evaluated.
        groups: Groups of candidates clustered by value equivalence.
        all_candidates: All candidates (for metadata).

    Returns:
        A merged field dict with the appropriate status and classification.
    """
    distinct_values = [str(g[0].get('value')) for g in groups]
    highest_conf = max((float(c.get('confidence') or 0) for c in all_candidates), default=0.8)

    # Check if all groups are OCR variations of the same value (fuzzy match)
    # Works for 2+ groups by checking all pairs
    if len(groups) >= 2:
        all_fuzzy_similar = True
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                v_i = str(groups[i][0].get('value', ''))
                v_j = str(groups[j][0].get('value', ''))
                if not _fuzzy_ocr_similar(v_i, v_j):
                    all_fuzzy_similar = False
                    break
            if not all_fuzzy_similar:
                break

        if all_fuzzy_similar:
            # OCR character-level variations — pick the best candidate, flag for review
            all_in_groups = [c for g in groups for c in g]
            best = max(all_in_groups, key=lambda c: (float(c.get('confidence') or 0), len(str(c.get('value', '')))))
            return {
                'status': 'REVIEW',
                'has_conflict': False,
                'value': best.get('value'),
                'selected_value': best.get('value'),
                'values': distinct_values,
                'confidence': round(float(best.get('confidence') or highest_conf), 2),
                'source': best.get('source', 'OCR'),
                'source_image_index': best.get('source_image_index'),
                'candidates': all_candidates,
                'review_required': True,
                'candidate_classification': 'OCR_VARIATION',
                'evidence_merge_type': 'AMBIGUOUS',
                'reason': (
                    f"Multiple plausible evidence candidates detected across package views for '{field_name}': "
                    f"{distinct_values}. Likely OCR character variations. Manual verification recommended."
                ),
            }

    # For multi-group (3+ or non-fuzzy): check if there's one dominant, high-confidence group
    if len(groups) >= 2:
        # Check for multi-panel naming (e.g. front panel brand + side panel variant)
        from_different_images = len(set(
            c.get('source_image_index') for g in groups for c in g
            if c.get('source_image_index') is not None
        )) > 1
        if from_different_images and field_name in ('PRODUCT_NAME', 'BRAND', 'GENERIC_NAME'):
            # Product names from different panels may be complementary, not conflicting
            best_group = max(groups, key=lambda g: max(float(c.get('confidence') or 0) for c in g))
            best = max(best_group, key=lambda c: float(c.get('confidence') or 0))
            return {
                'status': 'REVIEW',
                'has_conflict': False,
                'value': best.get('value'),
                'selected_value': best.get('value'),
                'values': distinct_values,
                'confidence': round(float(best.get('confidence') or highest_conf), 2),
                'source': best.get('source', 'OCR'),
                'source_image_index': best.get('source_image_index'),
                'candidates': all_candidates,
                'review_required': True,
                'candidate_classification': 'MULTI_PANEL_EVIDENCE',
                'evidence_merge_type': 'COMPLEMENTARY',
                'reason': (
                    f"Multiple product identification candidates detected across different package views for '{field_name}': "
                    f"{distinct_values}. Manual verification recommended."
                ),
            }

    # Default: TRUE_CONFLICT — genuinely contradictory declarations
    return {
        'status': 'CONFLICTING_EVIDENCE',
        'has_conflict': True,
        'values': distinct_values,
        'value': f"CONFLICT: {' vs '.join(distinct_values)}",
        'confidence': round(highest_conf, 2),
        'source': 'MULTI_IMAGE_CONFLICT',
        'candidates': all_candidates,
        'review_required': True,
        'candidate_classification': 'TRUE_CONFLICT',
        'evidence_merge_type': 'TRUE_CONFLICT',
        'conflict_reason': f"Conflicting declarations detected across package views for '{field_name}': {distinct_values}",
        'reason': (
            f"Conflicting evidence detected across package views for '{field_name}': "
            f"{distinct_values}. Inspector review required."
        ),
    }


def merge_extracted_fields(field_sets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge extracted declarations across multiple package views with smart conflict classification.

    Distinguishes between:
    - TRUE_CONFLICT: Same semantic field & context, genuinely contradictory values.
    - COMPLEMENTARY (MULTI_PANEL_EVIDENCE): Complementary declarations from different package panels.
    - AMBIGUOUS (OCR_VARIATION): Multiple plausible candidates or OCR character variations.
    - IRRELEVANT (OCR_NOISE): Filtered out before conflict evaluation.
    - CONFIRMED_SAME: Consistent declarations agreeing across package panels.

    Never silently favors the highest-confidence candidate when values disagree.
    All candidate metadata (source, confidence, image index) is preserved.
    """
    merged: Dict[str, Any] = {}
    candidates_by_field: Dict[str, List[Dict[str, Any]]] = {}

    for field_set in field_sets:
        if not field_set or not isinstance(field_set, dict):
            continue
        for name, candidate in field_set.items():
            if not candidate or not isinstance(candidate, dict):
                continue
            val = candidate.get('value')
            if val is None or not str(val).strip():
                continue
            candidates_by_field.setdefault(name, []).append(dict(candidate))

    for name, candidates in candidates_by_field.items():
        if not candidates:
            continue

        # Phase 1: Filter out irrelevant/noise candidates
        relevant = [c for c in candidates if not _is_irrelevant_candidate(name, c)]
        noise = [c for c in candidates if _is_irrelevant_candidate(name, c)]
        for n in noise:
            n['candidate_classification'] = 'IRRELEVANT'
            n['evidence_merge_type'] = 'IRRELEVANT'

        if not relevant:
            # All candidates are noise — pick best anyway but mark as low-confidence
            if candidates:
                best = max(candidates, key=lambda c: float(c.get('confidence') or 0))
                result = dict(best)
                result['candidates'] = candidates
                result['filtered_noise'] = noise
                result['candidate_classification'] = 'IRRELEVANT'
                result['evidence_merge_type'] = 'IRRELEVANT'
                merged[name] = result
            continue

        if len(relevant) == 1:
            result = dict(relevant[0])
            result['candidates'] = candidates
            if len(candidates) > 1 and len(noise) == 0:
                result['candidate_classification'] = 'CONFIRMED_SAME'
                result['evidence_merge_type'] = 'CONFIRMED_SAME'
            else:
                result.setdefault('candidate_classification', 'SINGLE_PANEL')
                result.setdefault('evidence_merge_type', 'SINGLE_PANEL')
            if noise:
                result['filtered_noise'] = noise
            merged[name] = result
            continue

        # Phase 2: Group relevant candidates by value equivalence
        groups: List[List[Dict[str, Any]]] = []
        for cand in relevant:
            matched_group = False
            for group in groups:
                if not _values_conflict(name, cand, group[0]):
                    group.append(cand)
                    matched_group = True
                    break
            if not matched_group:
                groups.append([cand])

        if len(groups) == 1:
            # All relevant candidates agree across images
            best = max(groups[0], key=lambda c: float(c.get('confidence') or 0))
            agreed = dict(best)
            agreed['candidates'] = candidates
            agreed['candidate_classification'] = 'CONFIRMED_SAME'
            agreed['evidence_merge_type'] = 'CONFIRMED_SAME'
            if noise:
                agreed['filtered_noise'] = noise
            merged[name] = agreed
        else:
            # Multiple distinct value groups — classify the evidence type
            result = _classify_multi_image_evidence(name, groups, relevant)
            if noise:
                result['filtered_noise'] = noise
            # Preserve all original candidates (including noise) for transparency
            result['all_candidates'] = candidates
            merged[name] = result

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
                if 0 <= m.start() < earliest_pos:
                    earliest_pos = m.start()
    return text[:earliest_pos].strip(' :;,-')


def _clean_address_text(raw_addr: str) -> str:
    """Clean manufacturer address by stripping trailing consumer care, contact info, storage, marketing, and nutrition fragments."""
    if not raw_addr:
        return ""

    # Split into chunks by comma, semicolon, or newline
    parts = [p.strip() for p in re.split(r'[,;\n]+', raw_addr) if p.strip()]
    cleaned_parts = []

    for part in parts:
        part_clean = part.strip(' :;,-')
        if not part_clean:
            continue

        # Check if this part marks the beginning of another section
        if CONSUMER_CARE_STOP_RE.search(part_clean):
            break
        if STORAGE_STOP_RE.search(part_clean):
            break
        if MARKETING_STOP_RE.search(part_clean):
            break
        if SERVING_SIZE_RE.search(part_clean) or NUTRITION_LINE_RE.search(part_clean) or NUTRITION_SECTION_HEADER_RE.search(part_clean):
            break
        if INGREDIENTS_LINE_RE.search(part_clean):
            break
        if re.search(r'\b(?:m\.?\s*r\.?\s*p\.?|maximum\s+retail\s+price|fssai|lic\.?\s*(?:no\.?|number)?|batch\s*(?:no\.?|number)?|b\.?\s*no\.?|lot\s*(?:no\.?|number)?)\b', part_clean, re.I):
            break
        if re.search(r'\b(?:ph(?:one)?|tel(?:ephone)?|mob(?:ile)?|contact)\s*[:.\s-]*\+?\d', part_clean, re.I):
            break
        if re.search(r'\b(?:1800[\s\-]?\d{3}[\s\-]?\d{3,4})\b', part_clean):
            break
        if re.search(r'\b(?:email|e-mail|website|web)\s*[:.\s-]*', part_clean, re.I):
            break
        if re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', part_clean):
            break
        if re.search(r'\b(?:manufactured\s*(?:&|and|/)?\s*(?:by|at|for)|mfg\s*by|mfd\s*by|marketed\s*by|packed\s*by|imported\s*by|distributed\s*by)\b', part_clean, re.I):
            break
        if COMPANY_SUFFIX_RE.search(part_clean):
            break
        if re.search(r'\b(?:net\s*(?:wt|weight|qty|quantity)|mrp|rs\.\s*\d)\b', part_clean, re.I):
            break

        # Check for inline section cut inside the part
        cut_part = _cut_before_next_section(part_clean, 'manufacturer')
        if cut_part:
            cleaned_parts.append(cut_part)
            if cut_part != part_clean:
                # Truncated inline before the next section
                break
        else:
            # Entire part belongs to another section
            break

    result = ', '.join(cleaned_parts).strip(' :;,-')
    return result


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
    after_entity = _cut_before_next_section(after_entity, 'manufacturer')
    after_entity = _clean_address_text(after_entity)
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
        if CONSUMER_CARE_STOP_RE.search(line_clean):
            break
        if STORAGE_STOP_RE.search(line_clean):
            break
        if MARKETING_STOP_RE.search(line_clean):
            break
        if current_section != 'nutrition' and (SERVING_SIZE_RE.search(line_clean) or NUTRITION_SECTION_HEADER_RE.search(line_clean) or NUTRITION_LINE_RE.search(line_clean)):
            break
        if current_section in ('ingredients', 'nutrition') and _extract_company_entity_from_line(line_clean):
            break
        if current_section in ('manufacturer', 'marketer', 'packer'):
            if VENDOR_PREFIX_RE.search(line_clean):
                break
            if collected and (COMPANY_SUFFIX_RE.search(line_clean) or _extract_company_entity_from_line(line_clean)):
                break
            if NET_QTY_POSITIVE_CONTEXT_RE.search(line_clean) or re.search(r'\b(?:net\s*(?:wt|weight|qty|quantity)|mrp|rs\.\s*\d)\b', line_clean, re.I):
                break
        earliest_other_pos = len(line_clean)
        for sec_name, patterns in INLINE_SECTION_PATTERNS.items():
            if sec_name == current_section:
                continue
            for pat in patterns:
                for m in re.finditer(pat, line_clean, re.IGNORECASE):
                    if 0 <= m.start() < earliest_other_pos:
                        earliest_other_pos = m.start()

        if earliest_other_pos < len(line_clean):
            cut_line = line_clean[:earliest_other_pos].strip(' :;,-')
            if cut_line:
                collected.append(cut_line.strip(' ,;'))
            break
        else:
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
                address = _clean_address_text(', '.join(part for part in addr_parts if part))
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
                    address = _clean_address_text(', '.join(part for part in addr_parts if part))
                    return name, address or None

            # Fallback split
            if cont_lines:
                vendor = _split_vendor_and_address(cleaned_after) if cleaned_after else {'name': '', 'address': ''}
                if vendor['name'] and vendor['address']:
                    name = f"{label_prefix}: {vendor['name']}" if label_prefix else vendor['name']
                    address = _clean_address_text(', '.join([vendor['address']] + cont_lines))
                elif cleaned_after:
                    name = f"{label_prefix}: {cleaned_after}" if label_prefix else cleaned_after
                    address = _clean_address_text(', '.join(cont_lines))
                else:
                    name = f"{label_prefix}: {cont_lines[0]}" if label_prefix else cont_lines[0]
                    address = _clean_address_text(', '.join(cont_lines[1:])) if len(cont_lines) > 1 else None
                return name or None, address or None
            else:
                vendor = _split_vendor_and_address(cleaned_after)
                name = f"{label_prefix}: {vendor['name']}" if (vendor['name'] and label_prefix) else (vendor['name'] or cleaned_after)
                address = _clean_address_text(vendor['address']) or None
                return name or None, address

    # Step 2: Standalone company entity without "Manufactured by:" prefix
    for idx, line in enumerate(lines):
        comp_res = _extract_company_entity_from_line(line)
        if comp_res:
            comp_name, comp_addr = comp_res
            cont_lines = _collect_continuation_lines(lines, idx, 'manufacturer', max_lines=6)
            addr_parts = [comp_addr] if comp_addr else []
            addr_parts.extend(cont_lines)
            address = _clean_address_text(', '.join(part for part in addr_parts if part))
            return comp_name, address or None

    return None, None


def _extract_marketer_and_address(lines: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Extract marketer name and address cleanly when marketed by / distributed by is declared."""
    for idx, line in enumerate(lines):
        line_lower = line.lower()
        matched_kw = None
        for kw in MARKETER_KEYWORDS:
            kw_pattern = rf'(?:\b|(?<=^)){re.escape(kw)}\b'
            m_kw = re.search(kw_pattern, line_lower)
            if m_kw:
                matched_kw = kw
                start_pos = m_kw.end()
                label_prefix = line[:start_pos].strip(' :;,-')
                raw_after = line[start_pos:].strip(' :;,-')
                break

        if matched_kw:
            cleaned_after = _cut_before_next_section(raw_after, 'marketer')
            cont_lines = _collect_continuation_lines(lines, idx, 'marketer', max_lines=6)

            comp_res = _extract_company_entity_from_line(cleaned_after)
            if comp_res:
                comp_name, comp_addr = comp_res
                name = f"{label_prefix}: {comp_name}" if label_prefix else comp_name
                addr_parts = [comp_addr] if comp_addr else []
                addr_parts.extend(cont_lines)
                address = _clean_address_text(', '.join(part for part in addr_parts if part))
                return name, address or None

            if not cleaned_after and cont_lines:
                first_cont = cont_lines[0]
                comp_res_cont = _extract_company_entity_from_line(first_cont)
                if comp_res_cont:
                    comp_name, comp_addr = comp_res_cont
                    name = f"{label_prefix}: {comp_name}" if label_prefix else comp_name
                    addr_parts = [comp_addr] if comp_addr else []
                    addr_parts.extend(cont_lines[1:])
                    address = _clean_address_text(', '.join(part for part in addr_parts if part))
                    return name, address or None

            if cont_lines:
                vendor = _split_vendor_and_address(cleaned_after) if cleaned_after else {'name': '', 'address': ''}
                if vendor['name'] and vendor['address']:
                    name = f"{label_prefix}: {vendor['name']}" if label_prefix else vendor['name']
                    address = _clean_address_text(', '.join([vendor['address']] + cont_lines))
                elif cleaned_after:
                    name = f"{label_prefix}: {cleaned_after}" if label_prefix else cleaned_after
                    address = _clean_address_text(', '.join(cont_lines))
                else:
                    name = f"{label_prefix}: {cont_lines[0]}" if label_prefix else cont_lines[0]
                    address = _clean_address_text(', '.join(cont_lines[1:])) if len(cont_lines) > 1 else None
                return name or None, address or None
            else:
                vendor = _split_vendor_and_address(cleaned_after)
                name = f"{label_prefix}: {vendor['name']}" if (vendor['name'] and label_prefix) else (vendor['name'] or cleaned_after)
                address = _clean_address_text(vendor['address']) or None
                return name or None, address

    return None, None


def _split_vendor_and_address(raw_value: str) -> Dict[str, str]:
    value = raw_value.strip(' :;,-')
    if not value:
        return {'name': '', 'address': ''}

    # Check if there is a company suffix first
    m_comp = COMPANY_SUFFIX_RE.search(value)
    if m_comp:
        company_name = m_comp.group(1).strip(' ,;:')
        rest = value[m_comp.end():].strip(' ,;:')
        clean_rest = _clean_address_text(rest)
        return {'name': company_name, 'address': clean_rest}

    # Check for known address starter keywords
    addr_kw = r'(?:p\.?o\.?|plot\s*(?:no\.?)?|survey\s*(?:no\.?)?|road|street|sector|phase\s+[ivx0-9]+|gidc|industrial\s*area|village|taluka|district|state|pin(?:code)?|india)'
    if re.search(addr_kw, value, re.IGNORECASE):
        parts = re.split(rf'\s+(?={addr_kw})', value, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) == 2:
            return {'name': parts[0].strip(', '), 'address': _clean_address_text(parts[1].strip(', '))}

    if ',' in value:
        first, second = value.split(',', 1)
        if 3 < len(first) <= 200:
            return {'name': first.strip(), 'address': _clean_address_text(second.strip())}

    return {'name': value[:200], 'address': ''}


MRP_EXPLICIT_RUPEE_RE = re.compile(
    r'(?:m\.?\s*r\.?\s*p\.?|maximum\s+retail\s+price)?\s*[:.\s-]*\s*(?:₹)\s*[:.\s-]*\s*([+-]?\d+(?:[.,]\d{1,2})?)',
    re.IGNORECASE,
)
MRP_RS_INR_RE = re.compile(
    r'(?:m\.?\s*r\.?\s*p\.?|maximum\s+retail\s+price)?\s*[:.\s-]*\s*(?:rs\.?|inr)\s*[:.\s-]*\s*([+-]?\d+(?:[.,]\d{1,2})?)',
    re.IGNORECASE,
)
MRP_CORRUPTED_RE = re.compile(
    r'(?:m\.?\s*r\.?\s*p\.?|maximum\s+retail\s+price)?\s*[:.\s-]*\s*([■\?*#§¤])\s*([+-]?\d+(?:[.,]\d{1,2})?)',
    re.IGNORECASE,
)
MRP_PREFIX_ONLY_RE = re.compile(
    r'(?:m\.?\s*r\.?\s*p\.?|maximum\s+retail\s+price)\s*[:.\s-]*\s*([+-]?\d+(?:[.,]\d{1,2})?)',
    re.IGNORECASE,
)


def _extract_mrp_structured(normalized: str, raw_text: str, lines: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Extract structured Maximum Retail Price declaration, identifying currency symbols,
    corrupted symbols, and inference status without fabricating currency."""
    if not normalized and not raw_text:
        return None

    if lines is None:
        lines = [l.strip() for l in normalized.split('\n') if l.strip()]

    # First pass: line-by-line inspection
    for line in lines:
        cleaned_line = line.strip()
        if not cleaned_line:
            continue

        # 1. Corrupted currency symbol (e.g. ■10.00, MRP ■10.00)
        m_corrupt = MRP_CORRUPTED_RE.search(cleaned_line)
        if m_corrupt:
            raw_span = m_corrupt.group(0).strip()
            corrupt_char = m_corrupt.group(1)
            num_str = m_corrupt.group(2).replace(',', '')
            try:
                num_val = float(num_str)
            except ValueError:
                num_val = None
            return {
                'raw_value': raw_span,
                'raw_text': raw_span,
                'value': raw_span,
                'numeric_value': num_val,
                'currency_symbol': None,
                'currency_status': 'UNKNOWN',
                'status': 'REVIEW',
                'binary': 0,
                'reason': f"Corrupted currency symbol '{corrupt_char}' detected in MRP declaration; manual review required.",
                'confidence': 0.6,
                'source': 'OCR',
            }

        # 2. Explicit Indian Rupee symbol (e.g. MRP ₹120, ₹120)
        m_rupee = MRP_EXPLICIT_RUPEE_RE.search(cleaned_line)
        if m_rupee and ('mrp' in cleaned_line.lower() or '₹' in cleaned_line):
            raw_span = m_rupee.group(0).strip()
            num_str = m_rupee.group(1).replace(',', '')
            try:
                num_val = float(num_str)
            except ValueError:
                num_val = None
            if num_val is not None:
                display_val = f"₹{num_val:.2f}"
                return {
                    'raw_value': raw_span,
                    'raw_text': raw_span,
                    'value': display_val,
                    'numeric_value': num_val,
                    'currency_symbol': '₹',
                    'currency_status': 'VERIFIED',
                    'status': 'PASS',
                    'binary': 1,
                    'reason': f"Detected valid MRP declaration: {display_val}",
                    'confidence': 0.9,
                    'source': 'OCR',
                }

        # 3. Explicit Rs. or INR (e.g. MRP Rs. 120, Rs 120, INR 120)
        m_rs = MRP_RS_INR_RE.search(cleaned_line)
        if m_rs and ('mrp' in cleaned_line.lower() or re.search(r'\b(?:rs\.?|inr)\b', cleaned_line, re.I)):
            raw_span = m_rs.group(0).strip()
            num_str = m_rs.group(1).replace(',', '')
            try:
                num_val = float(num_str)
            except ValueError:
                num_val = None
            if num_val is not None:
                display_val = f"₹{num_val:.2f}"
                return {
                    'raw_value': raw_span,
                    'raw_text': raw_span,
                    'value': display_val,
                    'numeric_value': num_val,
                    'currency_symbol': '₹',
                    'currency_status': 'VERIFIED',
                    'status': 'PASS',
                    'binary': 1,
                    'reason': f"Detected valid MRP declaration: {display_val}",
                    'confidence': 0.88,
                    'source': 'OCR',
                }

        # 4. MRP prefix only, missing currency symbol (e.g. MRP 120, Maximum Retail Price: 120)
        m_prefix = MRP_PREFIX_ONLY_RE.search(cleaned_line)
        if m_prefix and 'mrp' in cleaned_line.lower():
            raw_span = m_prefix.group(0).strip()
            num_str = m_prefix.group(1).replace(',', '')
            try:
                num_val = float(num_str)
            except ValueError:
                num_val = None
            if num_val is not None:
                display_val = f"{num_val:.2f}"
                return {
                    'raw_value': raw_span,
                    'raw_text': raw_span,
                    'value': display_val,
                    'numeric_value': num_val,
                    'currency_symbol': None,
                    'currency_status': 'INFERRED',
                    'status': 'REVIEW',
                    'binary': 0,
                    'reason': f"Currency symbol missing; inferred from MRP prefix but requires review: '{raw_span}'.",
                    'confidence': 0.7,
                    'source': 'OCR',
                }

    # Second pass: check normalized text as a whole
    m_corrupt_full = MRP_CORRUPTED_RE.search(normalized)
    if m_corrupt_full:
        raw_span = m_corrupt_full.group(0).strip()
        corrupt_char = m_corrupt_full.group(1)
        num_str = m_corrupt_full.group(2).replace(',', '')
        try:
            num_val = float(num_str)
        except ValueError:
            num_val = None
        return {
            'raw_value': raw_span,
            'raw_text': raw_span,
            'value': raw_span,
            'numeric_value': num_val,
            'currency_symbol': None,
            'currency_status': 'UNKNOWN',
            'status': 'REVIEW',
            'binary': 0,
            'reason': f"Corrupted currency symbol '{corrupt_char}' detected in MRP declaration; manual review required.",
            'confidence': 0.6,
            'source': 'OCR',
        }

    legacy_mrp = _search_patterns(normalized, MRP_PATTERNS)
    if legacy_mrp:
        clean_num = legacy_mrp.replace(',', '')
        try:
            num_val = float(clean_num)
        except ValueError:
            num_val = None
        if num_val is not None and num_val > 0:
            return {
                'raw_value': legacy_mrp,
                'raw_text': legacy_mrp,
                'value': f"₹{clean_num}",
                'numeric_value': num_val,
                'currency_symbol': '₹',
                'currency_status': 'VERIFIED',
                'status': 'PASS',
                'binary': 1,
                'reason': f"Detected valid MRP declaration: ₹{clean_num}",
                'confidence': 0.85,
                'source': 'OCR',
            }

    return None


NET_QTY_UNITS_MAP: Dict[str, str] = {
    **LEGAL_MASS_UNITS,
    **LEGAL_VOLUME_UNITS,
    **LEGAL_COUNT_UNITS,
    **LEGAL_LENGTH_AREA_UNITS,
}

NET_QTY_LABEL_RE = re.compile(
    r'(?:(?:net|pack|package|pkg)\s*(?:wt\.?|weight|qty\.?|quantity|content|contents|size|vol\.?|volume|mass)|quantity|contents?|pack\s*size)(?:\s*[:.=]|\s+[-–](?=\s))*\s*([^\n,;]+)',
    re.IGNORECASE,
)

QUANTITY_UNITS_CHOICES = (
    r'g|gm|gms|gram|grams|kg|kgs|kilogram|kilograms|mg|milligram|milligrams|'
    r'ml|millilitre|millilitres|milliliter|milliliters|l|ltr|litre|litres|liter|liters|cl|'
    r'oz|lb|lbs|'
    r'pc|pcs|piece|pieces|tablet|tablets|tab|tabs|capsule|capsules|cap|caps|'
    r'unit|units|n|no|nos|number|numbers|wipes?|sheets?|pouches?|sachets?|rolls?|sticks?|bars?|bags?|'
    r'm|meter|meters|metre|metres|cm|centimeter|centimeters|centimetre|centimetres|mm|sq\s*m|sq\s*cm'
)

NET_QTY_UNIT_PATTERN = rf'(?:(?<=\d)|(?<=\s)|^)\s*({QUANTITY_UNITS_CHOICES})\b'

STANDALONE_QTY_RE = re.compile(
    rf'(?:\b|(?<=\s)|^)([+-]?\d+(?:\.\d+)?)\s*({QUANTITY_UNITS_CHOICES})\b',
    re.IGNORECASE,
)

MULTIPACK_COUNT_UNITS = r'(?:pk|pks|packs?|units?|nos?|pcs?|pieces?|n|pouches?|sachets?|bottles?|cans?|bars?|tins?)'
MULTIPACK_SEPARATORS = r'(?:[×xX*✕✖⨯]|\bof\b)'

MULTIPACK_QTY_RE = re.compile(
    rf'\b(?P<count>\d+)\s*(?:{MULTIPACK_COUNT_UNITS}\b\s*)?{MULTIPACK_SEPARATORS}\s*(?P<qty>[+-]?\d+(?:\.\d+)?)\s*(?P<unit>{QUANTITY_UNITS_CHOICES})\b',
    re.IGNORECASE,
)

MULTIPACK_INVERTED_RE = re.compile(
    rf'\b(?P<qty>[+-]?\d+(?:\.\d+)?)\s*(?P<unit>{QUANTITY_UNITS_CHOICES})\s*{MULTIPACK_SEPARATORS}\s*(?P<count>\d+)(?:\s*{MULTIPACK_COUNT_UNITS}\b)?',
    re.IGNORECASE,
)


def parse_quantity_expression(expr: str) -> Optional[Dict[str, Any]]:
    """
    Universal packaged-commodity quantity expression parser.
    Recognizes:
      - Standard Multipack: COUNT × UNIT QUANTITY (e.g. 10 × 50 g, 6 x 100g, 24 × 200 ml)
      - Inverted Multipack: UNIT QUANTITY × COUNT (e.g. 50 g × 10)
      - Single Quantity: QUANTITY UNIT (e.g. 250 g, 500 ml)
    Never confuses COUNT with net quantity.
    Calculates derived total quantity (source = DERIVED) without replacing declared expression.
    Returns None for invalid or incomplete expressions.
    """
    if not expr or not expr.strip():
        return None

    clean = expr.strip()

    # 1. Standard Multipack: COUNT × UNIT QUANTITY
    m_multi = MULTIPACK_QTY_RE.search(clean)
    if m_multi:
        prefix = clean[:m_multi.start()].rstrip()
        if not prefix.endswith('-'):
            try:
                count = int(m_multi.group('count'))
                raw_qty = m_multi.group('qty')
                flt_qty = float(raw_qty)
                unit_qty = int(flt_qty) if flt_qty.is_integer() else flt_qty
                raw_unit = m_multi.group('unit')
                norm_unit, qty_type = normalize_unit(raw_unit)

                if count > 0 and unit_qty > 0 and norm_unit:
                    calc_total = count * unit_qty
                    derived_total = int(calc_total) if isinstance(calc_total, float) and calc_total.is_integer() else calc_total
                    declared_expr = m_multi.group(0).strip()
                    logger.debug(
                        "Detected standard multipack: count=%s unit_qty=%s unit=%s derived_total=%s expr=%s",
                        count, unit_qty, norm_unit, derived_total, declared_expr
                    )
                    return {
                        "is_multipack": True,
                        "pack_count": count,
                        "unit_net_quantity": unit_qty,
                        "unit_quantity": unit_qty,
                        "unit": norm_unit,
                        "raw_unit": raw_unit,
                        "declared_expression": declared_expr,
                        "derived_total_quantity": derived_total,
                        "quantity_type": qty_type.value if qty_type else None,
                        "span": declared_expr,
                    }
            except (ValueError, TypeError, IndexError):
                pass

    # 2. Inverted Multipack: UNIT QUANTITY × COUNT
    m_inv = MULTIPACK_INVERTED_RE.search(clean)
    if m_inv:
        prefix = clean[:m_inv.start()].rstrip()
        if not prefix.endswith('-'):
            try:
                count = int(m_inv.group('count'))
                raw_qty = m_inv.group('qty')
                flt_qty = float(raw_qty)
                unit_qty = int(flt_qty) if flt_qty.is_integer() else flt_qty
                raw_unit = m_inv.group('unit')
                norm_unit, qty_type = normalize_unit(raw_unit)

                if count > 0 and unit_qty > 0 and norm_unit:
                    calc_total = count * unit_qty
                    derived_total = int(calc_total) if isinstance(calc_total, float) and calc_total.is_integer() else calc_total
                    declared_expr = m_inv.group(0).strip()
                    logger.debug(
                        "Detected inverted multipack: count=%s unit_qty=%s unit=%s derived_total=%s expr=%s",
                        count, unit_qty, norm_unit, derived_total, declared_expr
                    )
                    return {
                        "is_multipack": True,
                        "pack_count": count,
                        "unit_net_quantity": unit_qty,
                        "unit_quantity": unit_qty,
                        "unit": norm_unit,
                        "raw_unit": raw_unit,
                        "declared_expression": declared_expr,
                        "derived_total_quantity": derived_total,
                        "quantity_type": qty_type.value if qty_type else None,
                        "span": declared_expr,
                    }
            except (ValueError, TypeError, IndexError):
                pass

    # 3. Single standard quantity: QUANTITY UNIT
    m_single = STANDALONE_QTY_RE.search(clean)
    if m_single:
        try:
            raw_qty = m_single.group(1)
            flt_qty = float(raw_qty)
            qty_val = int(flt_qty) if flt_qty.is_integer() else flt_qty
            raw_unit = m_single.group(2)
            norm_unit, qty_type = normalize_unit(raw_unit)

            if qty_val > 0 and norm_unit:
                declared_expr = m_single.group(0).strip()
                return {
                    "is_multipack": False,
                    "pack_count": None,
                    "unit_net_quantity": None,
                    "unit_quantity": None,
                    "quantity": qty_val,
                    "unit": norm_unit,
                    "raw_unit": raw_unit,
                    "declared_expression": declared_expr,
                    "derived_total_quantity": None,
                    "quantity_type": qty_type.value if qty_type else None,
                    "span": declared_expr,
                }
        except (ValueError, TypeError, IndexError):
            pass

    return None


def _extract_net_quantity_field(text: str, lines: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Extract structured declared net quantity with semantic section scoping.
    Distinguishes declared package quantity from nutritional table values, serving sizes,
    and unrelated section numbers across mass, volume, and count units.
    Universally parses multipack expressions (COUNT × UNIT QUANTITY) without collapsing COUNT to quantity."""
    if not text:
        return None

    if lines is None:
        lines = [l.strip() for l in text.split('\n') if l.strip()]

    current_sec = SECTION_OTHER
    annotated_lines = []
    for line in lines:
        current_sec = classify_line_section(line, current_sec)
        annotated_lines.append((line, current_sec))

    valid_candidates: List[Dict[str, Any]] = []
    ignored_candidates: List[Dict[str, Any]] = []
    fallback_candidates: List[Dict[str, Any]] = []

    for line, sec in annotated_lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        # 1. Check for explicit Net Quantity label pattern on this line
        label_match = NET_QTY_LABEL_RE.search(line_clean)
        if label_match:
            raw_span = label_match.group(0).strip()
            after_label = label_match.group(1).strip()
            parsed_q = parse_quantity_expression(after_label)
            if parsed_q:
                if parsed_q["is_multipack"]:
                    cand = build_quantity_candidate(
                        qty_val=parsed_q["unit_net_quantity"],
                        raw_unit=parsed_q["raw_unit"],
                        raw_span=raw_span,
                        confidence=0.95,
                        semantic_section=SECTION_DECLARED_QUANTITY,
                        relevance="high",
                        relevance_score=0.98,
                        source_context=line_clean,
                        source="OCR",
                        is_multipack=True,
                        pack_count=parsed_q["pack_count"],
                        unit_net_quantity=parsed_q["unit_net_quantity"],
                        declared_expression=parsed_q["declared_expression"],
                        derived_total_quantity=parsed_q["derived_total_quantity"],
                    )
                else:
                    cand = build_quantity_candidate(
                        qty_val=parsed_q["quantity"],
                        raw_unit=parsed_q["raw_unit"],
                        raw_span=raw_span,
                        confidence=0.90,
                        semantic_section=SECTION_DECLARED_QUANTITY,
                        relevance="high",
                        relevance_score=0.95,
                        source_context=line_clean,
                        source="OCR",
                        is_multipack=False,
                    )
                valid_candidates.append(cand)
                continue
            else:
                num_match = re.search(r'([+-]?\d+(?:\.\d+)?)', after_label)
                unit_match = re.search(NET_QTY_UNIT_PATTERN, after_label, re.IGNORECASE)
                qty_val = num_match.group(1) if num_match else None
                raw_unit = unit_match.group(1) if unit_match else None

                if qty_val is not None or raw_unit is not None:
                    cand = build_quantity_candidate(
                        qty_val=qty_val,
                        raw_unit=raw_unit,
                        raw_span=raw_span,
                        confidence=0.85 if (qty_val and raw_unit) else 0.8,
                        semantic_section=SECTION_DECLARED_QUANTITY,
                        relevance="high",
                        relevance_score=0.90 if (qty_val and raw_unit) else 0.85,
                        source_context=line_clean,
                        source="OCR",
                    )
                    valid_candidates.append(cand)
                    continue

        # 2. Section scoping flags for standalone checks on this line
        is_nutrition = (
            sec == SECTION_NUTRITION
            or bool(NUTRITION_LINE_RE.search(line_clean))
            or bool(NUTRITION_SECTION_HEADER_RE.search(line_clean))
            or bool(re.search(r'\b(?:carbohydrate|protein|fat|sugar|energy|cholesterol|sodium)\b', line_clean, re.I))
        )
        is_serving = (
            sec == SECTION_SERVING_SIZE
            or bool(SERVING_SIZE_RE.search(line_clean))
        )
        is_other_section = (
            sec in (SECTION_CONSUMER_CARE, SECTION_STORAGE, SECTION_MARKETING, SECTION_MRP, SECTION_DATE, SECTION_INGREDIENTS, SECTION_FSSAI, SECTION_BATCH)
            or bool(CONSUMER_CARE_STOP_RE.search(line_clean))
            or bool(STORAGE_STOP_RE.search(line_clean))
            or bool(MARKETING_STOP_RE.search(line_clean))
        )

        # 3. Check for standalone multipack expression on this line
        multi_match = parse_quantity_expression(line_clean)
        if multi_match and multi_match.get("is_multipack"):
            raw_span = multi_match["declared_expression"]
            has_nutrient_words = bool(re.search(r'\b(?:carbohydrate|protein|fat|sugar|energy|cholesterol|sodium|trans|saturated|dietary|fiber|calcium|iron)\b', line_clean, re.I))
            if is_nutrition and has_nutrient_words:
                ignored_cand = build_quantity_candidate(
                    qty_val=multi_match["unit_net_quantity"],
                    raw_unit=multi_match["raw_unit"],
                    raw_span=raw_span,
                    confidence=0.7,
                    semantic_section=SECTION_NUTRITION,
                    relevance="rejected_as_irrelevant",
                    relevance_score=0.0,
                    source_context=line_clean,
                    source="OCR",
                    is_multipack=True,
                    pack_count=multi_match["pack_count"],
                    unit_net_quantity=multi_match["unit_net_quantity"],
                    declared_expression=multi_match["declared_expression"],
                    derived_total_quantity=multi_match["derived_total_quantity"],
                )
                ignored_cand['rejection_reason'] = "Value belongs to nutritional table, not declared net quantity"
                ignored_candidates.append(ignored_cand)
            elif is_serving:
                ignored_cand = build_quantity_candidate(
                    qty_val=multi_match["unit_net_quantity"],
                    raw_unit=multi_match["raw_unit"],
                    raw_span=raw_span,
                    confidence=0.7,
                    semantic_section=SECTION_SERVING_SIZE,
                    relevance="rejected_as_irrelevant",
                    relevance_score=0.0,
                    source_context=line_clean,
                    source="OCR",
                    is_multipack=True,
                    pack_count=multi_match["pack_count"],
                    unit_net_quantity=multi_match["unit_net_quantity"],
                    declared_expression=multi_match["declared_expression"],
                    derived_total_quantity=multi_match["derived_total_quantity"],
                )
                ignored_cand['rejection_reason'] = "Value is serving size, not package declared net quantity"
                ignored_candidates.append(ignored_cand)
            elif is_other_section:
                ignored_cand = build_quantity_candidate(
                    qty_val=multi_match["unit_net_quantity"],
                    raw_unit=multi_match["raw_unit"],
                    raw_span=raw_span,
                    confidence=0.5,
                    semantic_section=sec,
                    relevance="rejected_as_irrelevant",
                    relevance_score=0.0,
                    source_context=line_clean,
                    source="OCR",
                    is_multipack=True,
                    pack_count=multi_match["pack_count"],
                    unit_net_quantity=multi_match["unit_net_quantity"],
                    declared_expression=multi_match["declared_expression"],
                    derived_total_quantity=multi_match["derived_total_quantity"],
                )
                ignored_cand['rejection_reason'] = f"Value belongs to {sec} section, not declared net quantity"
                ignored_candidates.append(ignored_cand)
            else:
                cand = build_quantity_candidate(
                    qty_val=multi_match["unit_net_quantity"],
                    raw_unit=multi_match["raw_unit"],
                    raw_span=raw_span,
                    confidence=0.92,
                    semantic_section=SECTION_DECLARED_QUANTITY,
                    relevance="high",
                    relevance_score=0.95,
                    source_context=line_clean,
                    source="OCR",
                    is_multipack=True,
                    pack_count=multi_match["pack_count"],
                    unit_net_quantity=multi_match["unit_net_quantity"],
                    declared_expression=multi_match["declared_expression"],
                    derived_total_quantity=multi_match["derived_total_quantity"],
                )
                valid_candidates.append(cand)
            continue

        # 4. Check for standalone single quantity on this line
        for sm in STANDALONE_QTY_RE.finditer(line_clean):
            qty_val = sm.group(1)
            raw_unit = sm.group(2)
            raw_span = sm.group(0).strip()

            if is_nutrition:
                ignored_cand = build_quantity_candidate(
                    qty_val=qty_val,
                    raw_unit=raw_unit,
                    raw_span=raw_span,
                    confidence=0.7,
                    semantic_section=SECTION_NUTRITION,
                    relevance="rejected_as_irrelevant",
                    relevance_score=0.0,
                    source_context=line_clean,
                    source="OCR",
                )
                ignored_cand['rejection_reason'] = "Value belongs to nutritional table, not declared net quantity"
                ignored_candidates.append(ignored_cand)
            elif is_serving:
                ignored_cand = build_quantity_candidate(
                    qty_val=qty_val,
                    raw_unit=raw_unit,
                    raw_span=raw_span,
                    confidence=0.7,
                    semantic_section=SECTION_SERVING_SIZE,
                    relevance="rejected_as_irrelevant",
                    relevance_score=0.0,
                    source_context=line_clean,
                    source="OCR",
                )
                ignored_cand['rejection_reason'] = "Value is serving size, not package declared net quantity"
                ignored_candidates.append(ignored_cand)
            elif is_other_section:
                ignored_cand = build_quantity_candidate(
                    qty_val=qty_val,
                    raw_unit=raw_unit,
                    raw_span=raw_span,
                    confidence=0.5,
                    semantic_section=sec,
                    relevance="rejected_as_irrelevant",
                    relevance_score=0.0,
                    source_context=line_clean,
                    source="OCR",
                )
                ignored_cand['rejection_reason'] = f"Value belongs to {sec} section, not declared net quantity"
                ignored_candidates.append(ignored_cand)
            else:
                fallback_cand = build_quantity_candidate(
                    qty_val=qty_val,
                    raw_unit=raw_unit,
                    raw_span=raw_span,
                    confidence=0.75,
                    semantic_section=SECTION_OTHER,
                    relevance="standalone_fallback",
                    relevance_score=0.6,
                    source_context=line_clean,
                    source="OCR",
                )
                fallback_candidates.append(fallback_cand)

    # If valid positive-context candidates exist, pick the best one
    if valid_candidates:
        valid_candidates.sort(
            key=lambda c: (c.get('relevance_score', 0), 1 if c.get('quantity_unit_valid') else 0, c.get('confidence', 0)),
            reverse=True,
        )
        winner = dict(valid_candidates[0])
        all_ignored = [c for c in valid_candidates[1:]] + ignored_candidates + fallback_candidates
        if all_ignored:
            winner['ignored_candidates'] = all_ignored
        return winner

    # Fallback to normalized text-level label search if lines didn't catch it
    label_match_norm = NET_QTY_LABEL_RE.search(text)
    if label_match_norm:
        raw_span = label_match_norm.group(0).strip()
        after_label = label_match_norm.group(1).strip()
        parsed_q = parse_quantity_expression(after_label)
        if parsed_q:
            if parsed_q["is_multipack"]:
                winner = build_quantity_candidate(
                    qty_val=parsed_q["unit_net_quantity"],
                    raw_unit=parsed_q["raw_unit"],
                    raw_span=raw_span,
                    confidence=0.90,
                    semantic_section=SECTION_DECLARED_QUANTITY,
                    relevance="high",
                    relevance_score=0.95,
                    source_context=raw_span,
                    source="OCR",
                    is_multipack=True,
                    pack_count=parsed_q["pack_count"],
                    unit_net_quantity=parsed_q["unit_net_quantity"],
                    declared_expression=parsed_q["declared_expression"],
                    derived_total_quantity=parsed_q["derived_total_quantity"],
                )
            else:
                winner = build_quantity_candidate(
                    qty_val=parsed_q["quantity"],
                    raw_unit=parsed_q["raw_unit"],
                    raw_span=raw_span,
                    confidence=0.85,
                    semantic_section=SECTION_DECLARED_QUANTITY,
                    relevance="high",
                    relevance_score=0.90,
                    source_context=raw_span,
                    source="OCR",
                )
            if ignored_candidates:
                winner['ignored_candidates'] = ignored_candidates
            return winner

        num_match = re.search(r'([+-]?\d+(?:\.\d+)?)', after_label)
        unit_match = re.search(NET_QTY_UNIT_PATTERN, after_label, re.IGNORECASE)
        qty_val = num_match.group(1) if num_match else None
        raw_unit = unit_match.group(1) if unit_match else None

        winner = build_quantity_candidate(
            qty_val=qty_val,
            raw_unit=raw_unit,
            raw_span=raw_span,
            confidence=0.85,
            semantic_section=SECTION_DECLARED_QUANTITY,
            relevance="high",
            relevance_score=0.9,
            source_context=raw_span,
            source="OCR",
        )
        if ignored_candidates:
            winner['ignored_candidates'] = ignored_candidates
        return winner

    # If standalone fallback candidates exist and NO nutrition context was found on package
    if fallback_candidates and not any(c.get('semantic_section') == SECTION_NUTRITION for c in ignored_candidates):
        winner = dict(fallback_candidates[0])
        if ignored_candidates:
            winner['ignored_candidates'] = ignored_candidates
        return winner

    return None


def _extract_packer_and_address(lines: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Extract packer name and address when packed by/pkd by is declared."""
    for idx, line in enumerate(lines):
        line_lower = line.lower()
        matched_kw = None
        for kw in PACKER_KEYWORDS:
            kw_pattern = rf'(?:\b|(?<=^)){re.escape(kw)}\b'
            m_kw = re.search(kw_pattern, line_lower)
            if m_kw:
                matched_kw = kw
                start_pos = m_kw.end()
                label_prefix = line[:start_pos].strip(' :;,-')
                raw_after = line[start_pos:].strip(' :;,-')
                break

        if matched_kw:
            cleaned_after = _cut_before_next_section(raw_after, 'packer')
            cont_lines = _collect_continuation_lines(lines, idx, 'packer', max_lines=6)

            comp_res = _extract_company_entity_from_line(cleaned_after)
            if comp_res:
                comp_name, comp_addr = comp_res
                name = f"{label_prefix}: {comp_name}" if label_prefix else comp_name
                addr_parts = [comp_addr] if comp_addr else []
                addr_parts.extend(cont_lines)
                address = _clean_address_text(', '.join(part for part in addr_parts if part))
                return name, address or None

            if not cleaned_after and cont_lines:
                first_cont = cont_lines[0]
                comp_res_cont = _extract_company_entity_from_line(first_cont)
                if comp_res_cont:
                    comp_name, comp_addr = comp_res_cont
                    name = f"{label_prefix}: {comp_name}" if label_prefix else comp_name
                    addr_parts = [comp_addr] if comp_addr else []
                    addr_parts.extend(cont_lines[1:])
                    address = _clean_address_text(', '.join(part for part in addr_parts if part))
                    return name, address or None

            if cont_lines:
                vendor = _split_vendor_and_address(cleaned_after) if cleaned_after else {'name': '', 'address': ''}
                if vendor['name'] and vendor['address']:
                    name = f"{label_prefix}: {vendor['name']}" if label_prefix else vendor['name']
                    address = _clean_address_text(', '.join([vendor['address']] + cont_lines))
                elif cleaned_after:
                    name = f"{label_prefix}: {cleaned_after}" if label_prefix else cleaned_after
                    address = _clean_address_text(', '.join(cont_lines))
                else:
                    name = f"{label_prefix}: {cont_lines[0]}" if label_prefix else cont_lines[0]
                    address = _clean_address_text(', '.join(cont_lines[1:])) if len(cont_lines) > 1 else None
                return name or None, address or None
            else:
                vendor = _split_vendor_and_address(cleaned_after)
                name = f"{label_prefix}: {vendor['name']}" if (vendor['name'] and label_prefix) else (vendor['name'] or cleaned_after)
                address = _clean_address_text(vendor['address']) or None
                return name or None, address

    return None, None

BATCH_LABEL_RE = re.compile(
    r'\b(?:batch\s*(?:no\.?|number|num\.?|code)?|lot\s+(?:no\.?|number|num\.?|code)?|lot\s*[:#]|b\.?\s*no\.?|batch#)\b',
    re.IGNORECASE,
)
INVALID_BATCH_TOKENS = {
    'no', 'no.', 'number', 'num', 'num.', 'code', 'lot', 'batch', 'b', 'b.',
    'date', 'mfd', 'pkd', 'exp', 'expiry', 'mrp', 'rs', 'inr', 'none', 'n/a', 'na', 'null',
    'image', 'placeholder', '[image]', '[image 1]', 'undefined',
}


def _extract_batch_number(lines: List[str], normalized: str, ocr_items: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """Extract batch or lot number, strictly separating label tokens from the actual identifier value."""
    # 1. Search lines for explicit batch label
    for index, line in enumerate(lines):
        m = BATCH_LABEL_RE.search(line)
        if not m:
            continue

        matched_label = m.group(0).strip()
        after = line[m.end():].strip(' :;,-=#')

        # Strip any redundant label continuation words like 'No:', 'Number:'
        cleaned_after = re.sub(r'^(?:no\.?|number|num\.?|code)\b[:\s-]*', '', after, flags=re.IGNORECASE).strip(' :;,-=#')

        candidate = None
        if cleaned_after:
            tokens = cleaned_after.split()
            first_token = tokens[0].strip(' ,;:')
            if first_token.lower() not in INVALID_BATCH_TOKENS and len(re.sub(r'[^A-Za-z0-9]', '', first_token)) >= 1:
                candidate = first_token

        # If not on same line, check immediate next line (e.g. Batch No:\nB104)
        if not candidate and index + 1 < len(lines):
            next_line = lines[index + 1].strip()
            if not _is_section_boundary(next_line):
                cleaned_next = re.sub(r'^(?:no\.?|number|num\.?|code)\b[:\s-]*', '', next_line, flags=re.IGNORECASE).strip(' :;,-=#')
                next_tokens = cleaned_next.split()
                if next_tokens:
                    cand = next_tokens[0].strip(' ,;:')
                    if cand.lower() not in INVALID_BATCH_TOKENS and len(re.sub(r'[^A-Za-z0-9]', '', cand)) >= 1:
                        candidate = cand

        if candidate:
            return {
                'value': candidate[:100],
                'raw_value': f"{matched_label}: {candidate}",
                'raw_text': f"{matched_label}: {candidate}",
                'normalized_value': candidate[:100],
                'source_label': matched_label,
                'semantic_section': 'BATCH',
                'confidence': 0.85,
                'source': 'OCR',
            }

    # 2. Check OCR bounding boxes / items if available
    if ocr_items:
        for item in ocr_items:
            text = str(item.get('text', '')).strip()
            m = BATCH_LABEL_RE.search(text)
            if m:
                after = text[m.end():].strip(' :;,-=#')
                cleaned_after = re.sub(r'^(?:no\.?|number|num\.?|code)\b[:\s-]*', '', after, flags=re.IGNORECASE).strip(' :;,-=#')
                if cleaned_after:
                    tok = cleaned_after.split()[0].strip(' ,;:')
                    if tok.lower() not in INVALID_BATCH_TOKENS and len(re.sub(r'[^A-Za-z0-9]', '', tok)) >= 1:
                        return {
                            'value': tok[:100],
                            'raw_value': f"{m.group(0)}: {tok}",
                            'raw_text': f"{m.group(0)}: {tok}",
                            'normalized_value': tok[:100],
                            'source_label': m.group(0),
                            'semantic_section': 'BATCH',
                            'confidence': float(item.get('confidence') or 0.8),
                            'bbox': item.get('bbox'),
                            'source_image_index': item.get('image_index'),
                            'source': 'OCR',
                        }

    return None


def extract_declarations(raw_text: str, ocr_items: Optional[List[Dict[str, Any]]] = None, category: Optional[str] = None) -> Dict[str, Any]:
    if not raw_text:
        return {}

    # Stage 2: OCR Cleaning layer
    cleaned_text, cleaned_ocr_items, removed_artifacts = clean_ocr_evidence(raw_text, ocr_items)
    effective_text = cleaned_text or raw_text
    effective_items = cleaned_ocr_items if cleaned_ocr_items else ocr_items

    normalized = _normalize_text(effective_text)
    lines = [line.strip() for line in normalized.split('\n') if line.strip()]
    fields: Dict[str, Any] = {}

    p_cand, competing_pnames, p_status = _extract_product_name_candidates(lines, ocr_items)
    if p_cand:
        fields['PRODUCT_NAME'] = build_product_name_candidate(
            value=p_cand[:200],
            raw_text=p_cand,
            status=p_status,
            competing_candidates=competing_pnames,
            confidence=0.65 if p_status == "AMBIGUOUS" else 0.85,
            source='OCR',
        )

    # Generalized Commodity & Brand Extraction
    # Detect generic commodity descriptors across food, personal care, and household commodities.
    # Combines front-panel layout (brand line above generic product name, or brand prefix
    # on the same line before the generic commodity name) in a product-agnostic manner.
    GENERIC_COMMODITY_VOCABULARY = [
        (r'\b(?:crystal\s+sugar|granulated\s+sugar|white\s+sugar|refined\s+sugar)\b', 'CRYSTAL SUGAR', 'SUGAR'),
        (r'\b(?:sugar)\b', 'SUGAR', 'SUGAR'),
        (r'\b(?:iodized?\s+salt|rock\s+salt|sea\s+salt|black\s+salt|table\s+salt|salt)\b', 'SALT', 'SALT'),
        (r'\b(?:sunflower\s+oil|mustard\s+oil|refined\s+oil|edible\s+oil|vegetable\s+oil|coconut\s+oil|olive\s+oil|groundnut\s+oil|cooking\s+oil)\b', 'EDIBLE OIL', 'OIL'),
        (r'\b(?:green\s+tea|black\s+tea|leaf\s+tea|dust\s+tea|tea)\b', 'TEA', 'BEVERAGE'),
        (r'\b(?:instant\s+coffee|filter\s+coffee|coffee)\b', 'COFFEE', 'BEVERAGE'),
        (r'\b(?:wheat\s+flour|whole\s+wheat\s+atta|atta|maida|besan|flour)\b', 'FLOUR', 'GRAIN_PRODUCT'),
        (r'\b(?:basmati\s+rice|rice)\b', 'RICE', 'GRAIN_PRODUCT'),
        (r'\b(?:biscuits?|cookies?)\b', 'BISCUIT', 'BISCUIT'),
        (r'\b(?:garam\s+masala|turmeric\s+powder|chilli\s+powder|coriander\s+powder|cumin\s+powder|spices?|masala|pepper)\b', 'SPICE', 'SPICE'),
        (r'\b(?:talcum\s+powder|body\s+talc|soft\s+talc|face\s+powder|talc)\b', 'TALCUM POWDER', 'TALCUM_POWDER'),
        (r'\b(?:shampoo|hair\s+cleanser)\b', 'SHAMPOO', 'PERSONAL_CARE'),
        (r'\b(?:conditioner|hair\s+conditioner)\b', 'CONDITIONER', 'PERSONAL_CARE'),
        (r'\b(?:body\s+wash|shower\s+gel|toilet\s+soap|bathing\s+soap|soap)\b', 'SOAP', 'PERSONAL_CARE'),
        (r'\b(?:body\s+lotion|face\s+cream|moisturizing\s+cream|cold\s+cream|skin\s+cream|deodorant)\b', 'SKIN CARE', 'PERSONAL_CARE'),
        (r'\b(?:toothpaste|tooth\s+paste|dental\s+cream)\b', 'TOOTHPASTE', 'PERSONAL_CARE'),
        (r'\b(?:detergent\s+powder|washing\s+powder|liquid\s+detergent|detergent)\b', 'DETERGENT', 'HOUSEHOLD_CLEANING'),
        (r'\b(?:disinfectant\s+cleaner|floor\s+cleaner|toilet\s+cleaner|dishwash\s+liquid|surface\s+cleaner|cleaner)\b', 'CLEANER', 'HOUSEHOLD_CLEANING'),
    ]

    matched_generic = None
    matched_type = None

    # 1. Scan lines from top of package, skipping ingredient, nutrition, and address sections
    for idx, line in enumerate(lines[:12]):
        sec = classify_line_section(line)
        if sec in (SECTION_INGREDIENTS, SECTION_NUTRITION, SECTION_ADDRESS, SECTION_CONSUMER_CARE, SECTION_STORAGE):
            continue
        if re.search(r'\b(?:manufactured|packed|marketed|ingredients|nutrition|mrp|batch|consumer)\b', line, re.I):
            continue

        for pat, gen_name, prod_type in GENERIC_COMMODITY_VOCABULARY:
            m_gen = re.search(pat, line, re.IGNORECASE)
            if m_gen:
                matched_generic = gen_name
                matched_type = prod_type
                fields['GENERIC_NAME'] = {'value': gen_name, 'confidence': 0.85, 'source': 'OCR'}
                fields['PRODUCT_TYPE'] = {'value': prod_type, 'confidence': 0.85, 'source': 'OCR'}

                # Check if brand tokens appear before the generic match on the same line
                before_text = line[:m_gen.start()].strip()
                brand_tokens = re.findall(r'[A-Za-z][A-Za-z0-9&-]*', before_text)
                if len(brand_tokens) >= 1 and not any(t.lower() in MARKETING_TERMS for t in brand_tokens):
                    cand_brand = ' '.join(brand_tokens).title()
                    fields['BRAND'] = {'value': cand_brand, 'confidence': 0.82, 'source': 'OCR'}
                    fields['PRODUCT_NAME'] = build_product_name_candidate(
                        value=f"{cand_brand} {gen_name.title()}",
                        raw_text=f"{cand_brand} {gen_name.title()}",
                        status="VALID",
                        confidence=0.85,
                        source='OCR_LAYOUT',
                    )
                elif idx > 0 and 'BRAND' not in fields:
                    # Check preceding line for brand name
                    prev_line = lines[idx - 1].strip()
                    prev_words = re.findall(r'[A-Za-z][A-Za-z0-9&-]*', prev_line)
                    if 1 <= len(prev_words) <= 4 and not any(w.lower() in MARKETING_TERMS for w in prev_words) and not _is_section_boundary(prev_line):
                        cand_brand = ' '.join(prev_words).title()
                        fields['BRAND'] = {'value': cand_brand, 'confidence': 0.82, 'source': 'OCR_LAYOUT'}
                        fields['PRODUCT_NAME'] = build_product_name_candidate(
                            value=f"{cand_brand} {gen_name.title()}",
                            raw_text=f"{cand_brand} {gen_name.title()}",
                            status="VALID",
                            confidence=0.85,
                            source='OCR_LAYOUT',
                        )
                break
        if matched_generic:
            break

    # 2. Front panel uppercase brand above generic line layout fallback
    if 'BRAND' not in fields:
        for index, line in enumerate(lines[:-1]):
            next_line = lines[index + 1]
            brand_words = re.findall(r'[A-Za-z][A-Za-z&-]*', line)
            product_words = re.findall(r'[A-Za-z][A-Za-z&-]*', next_line)
            if (1 <= len(brand_words) <= 3 and brand_words and line.upper() == line and
                    not any(w.lower() in MARKETING_TERMS for w in brand_words) and
                    any(word.lower() in {'salt', 'sugar', 'soap', 'shampoo', 'biscuit', 'oil', 'tea', 'powder', 'cream', 'cleaner', 'flour', 'rice'} for word in product_words)):
                brand = ' '.join(word.title() for word in brand_words)
                generic = ' '.join(product_words).title()
                fields['BRAND'] = {'value': brand, 'confidence': 0.84, 'source': 'OCR_LAYOUT'}
                if 'PRODUCT_NAME' not in fields or (fields['PRODUCT_NAME'].get('confidence', 0) < 0.8 and fields['PRODUCT_NAME'].get('status') != 'AMBIGUOUS'):
                    fields['PRODUCT_NAME'] = build_product_name_candidate(
                        value=f'{brand} {generic}',
                        raw_text=f'{brand} {generic}',
                        status="VALID",
                        confidence=0.86,
                        source='OCR_LAYOUT',
                    )
                break

    # 3. If product name is still missing or low confidence, combine available brand + generic
    if 'PRODUCT_NAME' not in fields or (fields['PRODUCT_NAME'].get('confidence', 0) < 0.7 and fields['PRODUCT_NAME'].get('status') != 'AMBIGUOUS'):
        if 'BRAND' in fields and 'GENERIC_NAME' in fields:
            fields['PRODUCT_NAME'] = build_product_name_candidate(
                value=f"{fields['BRAND']['value']} {fields['GENERIC_NAME']['value'].title()}",
                raw_text=f"{fields['BRAND']['value']} {fields['GENERIC_NAME']['value'].title()}",
                status="VALID",
                confidence=0.82,
                source='OCR',
            )
        elif p_cand and 'PRODUCT_NAME' not in fields:
            fields['PRODUCT_NAME'] = build_product_name_candidate(
                value=p_cand[:200],
                raw_text=p_cand,
                status=p_status,
                competing_candidates=competing_pnames,
                confidence=0.65 if p_status == "AMBIGUOUS" else 0.85,
                source='OCR',
            )

    mrp_field = _extract_mrp_structured(normalized, raw_text, lines)
    if mrp_field:
        fields['MRP'] = mrp_field

    qty_field = _extract_net_quantity_field(normalized, lines)
    if qty_field:
        fields['DECLARED_NET_QUANTITY'] = qty_field

    mfg_name, mfg_addr = _extract_manufacturer_and_address(lines)
    mkt_name, mkt_addr = _extract_marketer_and_address(lines)
    packer_name, packer_addr = _extract_packer_and_address(lines)

    if mfg_name:
        fields['MANUFACTURER_NAME'] = {'value': mfg_name, 'confidence': 0.85, 'source': 'OCR', 'role': 'MANUFACTURER'}
    if mfg_addr:
        fields['MANUFACTURER_ADDRESS'] = {'value': mfg_addr[:500], 'confidence': 0.8, 'source': 'OCR', 'role': 'MANUFACTURER'}

    if mkt_name:
        fields['MARKETER_NAME'] = {'value': mkt_name, 'confidence': 0.85, 'source': 'OCR', 'role': 'MARKETER'}
        if 'MANUFACTURER_NAME' not in fields:
            fields['MANUFACTURER_NAME'] = {'value': mkt_name, 'confidence': 0.8, 'source': 'OCR', 'entity_type': 'MARKETER', 'role': 'MARKETER'}
    if mkt_addr:
        fields['MARKETER_ADDRESS'] = {'value': mkt_addr[:500], 'confidence': 0.8, 'source': 'OCR', 'role': 'MARKETER'}
        if 'MANUFACTURER_ADDRESS' not in fields:
            fields['MANUFACTURER_ADDRESS'] = {'value': mkt_addr[:500], 'confidence': 0.75, 'source': 'OCR', 'entity_type': 'MARKETER', 'role': 'MARKETER'}

    if packer_name:
        fields['PACKER_NAME'] = {'value': packer_name, 'confidence': 0.85, 'source': 'OCR', 'role': 'PACKER'}
        if 'MANUFACTURER_NAME' not in fields:
            fields['MANUFACTURER_NAME'] = {'value': packer_name, 'confidence': 0.78, 'source': 'OCR', 'entity_type': 'PACKER', 'role': 'PACKER'}
    if packer_addr:
        fields['PACKER_ADDRESS'] = {'value': packer_addr[:500], 'confidence': 0.8, 'source': 'OCR', 'role': 'PACKER'}
        if 'MANUFACTURER_ADDRESS' not in fields:
            fields['MANUFACTURER_ADDRESS'] = {'value': packer_addr[:500], 'confidence': 0.68, 'source': 'OCR', 'entity_type': 'PACKER', 'role': 'PACKER'}

    # Collect distinct responsible entities with structured roles without merging
    entities = []
    if mfg_name:
        entities.append({'role': 'MANUFACTURER', 'name': mfg_name, 'address': mfg_addr})
    if mkt_name and mkt_name != mfg_name:
        entities.append({'role': 'MARKETER', 'name': mkt_name, 'address': mkt_addr})
    if packer_name and packer_name not in (mfg_name, mkt_name):
        entities.append({'role': 'PACKER', 'name': packer_name, 'address': packer_addr})

    if len(entities) > 1:
        if 'MANUFACTURER_NAME' in fields:
            fields['MANUFACTURER_NAME']['entities'] = entities

        # Ambiguous address association check:
        # If multiple distinct entities exist and their address association is shared, identical, or unlinked
        addrs = [e.get('address') for e in entities if e.get('address')]
        if len(entities) >= 2 and len(set(addrs)) == 1 and addrs[0]:
            if 'MANUFACTURER_ADDRESS' in fields:
                fields['MANUFACTURER_ADDRESS']['status'] = 'AMBIGUOUS'
                fields['MANUFACTURER_ADDRESS']['is_ambiguous'] = True
                fields['MANUFACTURER_ADDRESS']['competing_candidates'] = [
                    {'entity': e['name'], 'role': e['role'], 'address': addrs[0]} for e in entities
                ]
                fields['MANUFACTURER_ADDRESS']['reason'] = (
                    f"Ambiguous address association between multiple declared entities: "
                    f"{', '.join(e['name'] for e in entities)}"
                )

    # Check for multiple standalone corporate entities without explicit manufacturer/marketer prefixes
    standalone_comps = []
    for idx, line in enumerate(lines):
        comp = _extract_company_entity_from_line(line)
        if comp and not any(kw in line.lower() for kw in MANUFACTURER_KEYWORDS + MARKETER_KEYWORDS + PACKER_KEYWORDS):
            standalone_comps.append((comp[0], idx, comp[1]))
    if len(standalone_comps) >= 2 and not mfg_name and not mkt_name:
        if 'MANUFACTURER_ADDRESS' in fields:
            fields['MANUFACTURER_ADDRESS']['status'] = 'AMBIGUOUS'
            fields['MANUFACTURER_ADDRESS']['is_ambiguous'] = True
            fields['MANUFACTURER_ADDRESS']['competing_candidates'] = [
                {'entity': sc[0], 'address': fields['MANUFACTURER_ADDRESS'].get('value')}
                for sc in standalone_comps
            ]
            fields['MANUFACTURER_ADDRESS']['reason'] = (
                f"Ambiguous address association between competing entities: "
                f"{', '.join(sc[0] for sc in standalone_comps)}"
            )

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
        is_valid, norm_date, date_meta = parse_date_with_precision(mfg_date)
        if is_valid and date_meta:
            prec = date_meta["precision"]
            parsed_comps = date_meta["parsed_components"]
            if prec == DatePrecision.FULL_DATE.value:
                fields['MANUFACTURE_DATE'] = build_date_candidate(
                    raw_date=mfg_date,
                    norm_val=norm_date,
                    precision=DatePrecision.FULL_DATE.value,
                    parsed_components=parsed_comps,
                    source_label='MFD',
                    semantic_type='MANUFACTURE_DATE',
                    confidence=0.75,
                    source='OCR',
                )
            else:
                fields['MONTH_YEAR_MANUFACTURE'] = build_date_candidate(
                    raw_date=mfg_date,
                    norm_val=norm_date,
                    precision=DatePrecision.MONTH_YEAR.value,
                    parsed_components=parsed_comps,
                    source_label='MFD',
                    semantic_type='MONTH_YEAR_MANUFACTURE',
                    confidence=0.75,
                    source='OCR',
                )
        else:
            fields['MANUFACTURE_DATE'] = {
                'value': mfg_date,
                'raw_value': mfg_date,
                'raw_date': mfg_date,
                'source_label': 'MFD',
                'semantic_type': 'MANUFACTURE_DATE',
                'confidence': 0.75,
                'source': 'OCR',
            }

    packing_date = _extract_date_near_keyword(normalized, PACKING_DATE_KEYWORDS)
    if packing_date:
        is_valid, norm_date, date_meta = parse_date_with_precision(packing_date)
        if is_valid and date_meta:
            prec = date_meta["precision"]
            parsed_comps = date_meta["parsed_components"]
            fields['PACKING_DATE'] = build_date_candidate(
                raw_date=packing_date,
                norm_val=norm_date,
                precision=prec,
                parsed_components=parsed_comps,
                source_label='PKD',
                semantic_type='PACKING_DATE',
                confidence=0.75,
                source='OCR',
            )
        else:
            fields['PACKING_DATE'] = {
                'value': packing_date,
                'raw_value': packing_date,
                'raw_date': packing_date,
                'source_label': 'PKD',
                'semantic_type': 'PACKING_DATE',
                'confidence': 0.75,
                'source': 'OCR',
            }

    best_before = _extract_date_near_keyword(normalized, BEST_BEFORE_KEYWORDS)
    if best_before:
        fields['BEST_BEFORE_USE_BY'] = {
            'value': best_before,
            'raw_value': best_before,
            'raw_date': best_before,
            'normalized_value': best_before,
            'normalized_date': best_before,
            'source_label': 'BEST_BEFORE',
            'semantic_type': 'BEST_BEFORE',
            'evidence': {'raw_text': best_before, 'label': 'BEST_BEFORE'},
            'confidence': 0.75,
            'source': 'OCR',
        }
    else:
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in BEST_BEFORE_KEYWORDS):
                dur_match = re.search(r'(\d+\s*(?:months?|days?|years?)(?:\s*(?:from|of)\s+[a-z\s]+)?)', line, re.IGNORECASE)
                if dur_match:
                    dur_val = dur_match.group(1).strip()
                    fields['BEST_BEFORE_USE_BY'] = {
                        'value': dur_val,
                        'raw_value': dur_val,
                        'raw_date': dur_val,
                        'normalized_value': dur_val,
                        'normalized_date': dur_val,
                        'source_label': 'BEST_BEFORE',
                        'semantic_type': 'BEST_BEFORE_PERIOD',
                        'evidence': {'raw_text': dur_val, 'label': 'BEST_BEFORE'},
                        'confidence': 0.75,
                        'source': 'OCR',
                    }
                    break

    use_by = _extract_date_near_keyword(normalized, USE_BY_KEYWORDS)
    if use_by:
        fields['USE_BEFORE_DATE'] = {
            'value': use_by,
            'raw_value': use_by,
            'raw_date': use_by,
            'normalized_value': use_by,
            'normalized_date': use_by,
            'source_label': 'USE_BY',
            'semantic_type': 'USE_BY',
            'evidence': {'raw_text': use_by, 'label': 'USE_BY'},
            'confidence': 0.75,
            'source': 'OCR',
        }
    elif 'BEST_BEFORE_USE_BY' not in fields:
        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in USE_BY_KEYWORDS):
                dur_match = re.search(r'(\d+\s*(?:months?|days?|years?)(?:\s*(?:from|of)\s+[a-z\s]+)?)', line, re.IGNORECASE)
                if dur_match:
                    dur_val = dur_match.group(1).strip()
                    fields['USE_BEFORE_DATE'] = {
                        'value': dur_val,
                        'raw_value': dur_val,
                        'raw_date': dur_val,
                        'normalized_value': dur_val,
                        'normalized_date': dur_val,
                        'source_label': 'USE_BY',
                        'semantic_type': 'USE_BY_PERIOD',
                        'evidence': {'raw_text': dur_val, 'label': 'USE_BY'},
                        'confidence': 0.75,
                        'source': 'OCR',
                    }
                    break

    expiry_date = _extract_date_near_keyword(normalized, EXPIRY_KEYWORDS)
    if expiry_date:
        fields['EXPIRY_DATE'] = {
            'value': expiry_date,
            'raw_value': expiry_date,
            'raw_date': expiry_date,
            'normalized_value': expiry_date,
            'normalized_date': expiry_date,
            'source_label': 'EXPIRY',
            'semantic_type': 'EXPIRY_DATE',
            'evidence': {'raw_text': expiry_date, 'label': 'EXPIRY'},
            'confidence': 0.75,
            'source': 'OCR',
        }

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

    cc_field = _extract_consumer_care_structured(lines, normalized)
    if cc_field:
        fields['CONSUMER_CARE'] = cc_field

    batch_field = _extract_batch_number(lines, normalized, ocr_items)
    if batch_field:
        fields['BATCH_NUMBER'] = batch_field

    for f_name, field_data in fields.items():
        val_str = str(field_data.get('value', ''))
        val_lower = val_str.lower()
        if effective_items and val_lower:
            matching_item = next(
                (item for item in effective_items if val_lower in str(item.get('text', '')).lower()),
                None,
            )
            if matching_item:
                field_data.setdefault('source_image_index', matching_item.get('image_index'))
                field_data.setdefault('bbox', matching_item.get('bbox'))
                field_data['confidence'] = min(float(field_data.get('confidence') or 0), float(matching_item.get('confidence') or 0))

        # Attach canonical EvidenceCandidate schema
        if 'evidence_candidate' not in field_data:
            ev_candidate = EvidenceCandidate(
                raw_text=field_data.get('raw_text', field_data.get('raw_value', val_str)),
                normalized_text=field_data.get('normalized_value', val_str),
                source_image=field_data.get('source', 'OCR'),
                source_type=SourceType.OCR.value,
                ocr_confidence=float(field_data.get('confidence') or 0.8),
                bounding_box=field_data.get('bbox'),
                line_id=field_data.get('line_index'),
                semantic_section=field_data.get('semantic_section', 'UNKNOWN'),
                anchor_label=field_data.get('source_label'),
                anchor_relation=field_data.get('anchor_relation', AnchorRelation.SAME_LINE.value if field_data.get('source_label') else AnchorRelation.UNANCHORED.value),
                candidate_field=f_name,
                relevance_score=float(field_data.get('relevance_score') or 0.85),
                validation_state=ValidationState.UNASSESSED.value,
            )
            field_data['evidence_candidate'] = ev_candidate.to_dict()

        # Attach CanonicalFieldCandidate and structured provenance
        if 'canonical_field_candidate' not in field_data:
            cfc = CanonicalFieldCandidate(
                field=f_name,
                normalized_value=field_data.get('normalized_value', field_data.get('value')),
                raw_text=field_data.get('raw_text', field_data.get('raw_value', val_str)),
                anchor_label=field_data.get('source_label'),
                semantic_section=field_data.get('semantic_section', 'UNKNOWN'),
                source_image=field_data.get('source', 'OCR'),
                bbox=field_data.get('bbox'),
                relevance_score=float(field_data.get('relevance_score') or 0.85),
                confidence=float(field_data.get('confidence') or 0.8),
                validation_state=field_data.get('status', ValidationState.UNASSESSED.value),
                rejection_reason=field_data.get('rejection_reason'),
                provenance={
                    'what': field_data.get('value'),
                    'why': f"Associated with anchor label '{field_data.get('source_label', 'UNANCHORED')}' in section '{field_data.get('semantic_section', 'UNKNOWN')}'",
                    'where': field_data.get('bbox') or {'line_index': field_data.get('line_index')},
                    'which_label': field_data.get('source_label'),
                    'which_image': field_data.get('source_image_index'),
                    'confidence': float(field_data.get('confidence') or 0.8),
                    'validation': field_data.get('status', 'UNASSESSED'),
                },
                metadata={k: v for k, v in field_data.items() if k not in ('evidence_candidate', 'canonical_field_candidate', 'provenance')},
            )
            field_data['canonical_field_candidate'] = cfc.to_dict()
            field_data.setdefault('provenance', cfc.provenance)

    logger.info(f"Extracted {len(fields)} declaration fields from OCR text")
    return fields
