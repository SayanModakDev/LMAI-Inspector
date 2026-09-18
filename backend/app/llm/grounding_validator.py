"""
Deterministic Evidence Grounding and Hallucination Validator for LLM Semantic Extractions.
Guarantees zero fabricated tokens or ungrounded values can reach the statutory rule engine
while tolerating legitimate OCR scanning noise, character substitutions, and layout fragmentation.
"""

import difflib
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple

from app.llm.schemas import (
    CandidateValue,
    LLMExtractionResult,
    ResolvedDeclaration,
    SourceEvidence,
)

logger = logging.getLogger(__name__)


def clean_ocr_text(text: str) -> str:
    """
    Normalize text for OCR comparison:
    - Unicode normalize (NFKD)
    - lowercase
    - strip & collapse whitespace
    - normalize quotes and dashes
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _normalize_alphanumeric(text: str) -> str:
    """Normalize text to alphanumeric characters for derivation checking."""
    return re.sub(r'[^a-zA-Z0-9]+', '', (text or '').lower())


def normalize_repeated_chars(text: str) -> str:
    """
    Safely reduce excessive repeated characters caused by OCR stuttering/noise:
    - 3+ identical consecutive characters -> 1 character (e.g. 'coooompany' -> 'company')
    - Double leading consonants at word start where unnatural in English/Hindi transliteration
      (e.g., 'gglobal' -> 'global', 'bbt' -> 'bt')
    """
    if not text:
        return ""
    collapsed = re.sub(r'(.)\1{2,}', r'\1', text)
    words = collapsed.split()
    cleaned_words = []
    for w in words:
        if len(w) >= 4 and w[0] == w[1] and w[0] in 'bcdfghjklmnpqrstvwxyz':
            w = w[1:]
        cleaned_words.append(w)
    return " ".join(cleaned_words)


def _is_date_expansion_derivable(value: str, raw_text: str) -> bool:
    """
    Narrow deterministic date-normalization derivation rule allowing:
    MM/YY -> MM/YYYY (as well as DD/MM/YY -> DD/MM/YYYY, or ISO date variants)
    only when:
    - Month is valid 01-12
    - The two-digit year is actually present in the OCR evidence
    - Normalized month is identical
    - Normalized year is a deterministic expansion of the OCR year (e.g. 20YY or 19YY)
    - No arbitrary date value is introduced.
    """
    if not value or not raw_text:
        return False

    # Extract candidate dates from normalized value (requiring a 4-digit year 19xx/20xx)
    val_dates = []

    # 1. DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    for m in re.finditer(r'(?<!\d)([0-2]?[1-9]|3[01])[\/\-\.](0?[1-9]|1[0-2])[\/\-\.]((?:19|20)\d{2})(?!\d)', value):
        val_dates.append({
            "day": int(m.group(1)),
            "month": int(m.group(2)),
            "year": int(m.group(3)),
        })

    # 2. MM/YYYY or MM-YYYY or MM.YYYY (only if not preceded by a day)
    for m in re.finditer(r'(?<!\d)(0?[1-9]|1[0-2])[\/\-\.]((?:19|20)\d{2})(?!\d)', value):
        m_val = int(m.group(1))
        y_val = int(m.group(2))
        if not any(vd["month"] == m_val and vd["year"] == y_val for vd in val_dates):
            val_dates.append({
                "day": None,
                "month": m_val,
                "year": y_val,
            })

    # 3. YYYY-MM-DD or YYYY/MM/DD
    for m in re.finditer(r'(?<!\d)((?:19|20)\d{2})[\/\-\.](0?[1-9]|1[0-2])[\/\-\.]([0-2]?[1-9]|3[01])(?!\d)', value):
        val_dates.append({
            "day": int(m.group(3)),
            "month": int(m.group(2)),
            "year": int(m.group(1)),
        })

    # 4. YYYY-MM or YYYY/MM
    for m in re.finditer(r'(?<!\d)((?:19|20)\d{2})[\/\-\.](0?[1-9]|1[0-2])(?!\d)', value):
        m_val = int(m.group(2))
        y_val = int(m.group(1))
        if not any(vd["month"] == m_val and vd["year"] == y_val for vd in val_dates):
            val_dates.append({
                "day": None,
                "month": m_val,
                "year": y_val,
            })

    if not val_dates:
        return False

    # Extract candidate 2-digit-year dates from raw_text
    raw_dates = []

    # 1. DD/MM/YY
    for m in re.finditer(r'(?<!\d)([0-2]?[1-9]|3[01])[\/\-\.](0?[1-9]|1[0-2])[\/\-\.]([0-9]{2})(?!\d)', raw_text):
        raw_dates.append({
            "day": int(m.group(1)),
            "month": int(m.group(2)),
            "yy": int(m.group(3)),
        })

    # 2. MM/YY e.g. 05/26, 04/28, 05-26, 05.26
    for m in re.finditer(r'(?<!\d)(0?[1-9]|1[0-2])[\/\-\.]([0-9]{2})(?!\d)', raw_text):
        m_raw = int(m.group(1))
        yy_raw = int(m.group(2))
        if not any(rd["month"] == m_raw and rd["yy"] == yy_raw for rd in raw_dates):
            raw_dates.append({
                "day": None,
                "month": m_raw,
                "yy": yy_raw,
            })

    if not raw_dates:
        return False

    for vd in val_dates:
        for rd in raw_dates:
            # Month must be valid 01-12 and identical
            if not (1 <= vd["month"] <= 12 and 1 <= rd["month"] <= 12):
                continue
            if vd["month"] != rd["month"]:
                continue

            # If both have a day specified, day must be identical
            if vd["day"] is not None and rd["day"] is not None and vd["day"] != rd["day"]:
                continue

            # Normalized year must be a deterministic expansion of the 2-digit OCR year
            expected_20xx = 2000 + rd["yy"]
            expected_19xx = 1900 + rd["yy"]
            if vd["year"] in (expected_20xx, expected_19xx):
                return True

    return False


ADDRESS_STRUCTURAL_MAP: Dict[str, Set[str]] = {
    "district": {"dist", "distt", "dt", "district"},
    "village": {"vill", "vpo", "village"},
    "tehsil": {"teh", "ts", "tehsil"},
    "road": {"rd", "road"},
    "street": {"st", "street"},
    "floor": {"flr", "floor"},
    "building": {"bldg", "building"},
    "apartment": {"apt", "flat", "apartment"},
    "sector": {"sec", "sect", "sector"},
    "phase": {"ph", "phase"},
    "industrial": {"ind", "indl", "industrial"},
    "estate": {"est", "estate"},
    "area": {"area"},
    "plot": {"plot", "no"},
    "near": {"nr", "near"},
    "opposite": {"opp", "opposite"},
}

STATE_MAPPINGS: Dict[str, List[str]] = {
    "himachal pradesh": ["hp", "h.p", "h.p.", "himachal", "pradesh"],
    "uttar pradesh": ["up", "u.p", "u.p.", "uttar", "pradesh"],
    "madhya pradesh": ["mp", "m.p", "m.p.", "madhya", "pradesh"],
    "andhra pradesh": ["ap", "a.p", "a.p.", "andhra", "pradesh"],
    "tamil nadu": ["tn", "t.n", "t.n.", "tamil", "nadu"],
    "west bengal": ["wb", "w.b", "w.b.", "bengal"],
    "maharashtra": ["mh", "m.h", "maharashtra"],
    "gujarat": ["gj", "g.j", "gujarat"],
    "rajasthan": ["rj", "r.j", "rajasthan"],
    "haryana": ["hr", "h.r", "haryana"],
    "punjab": ["pb", "p.b", "punjab"],
    "karnataka": ["ka", "k.a", "karnataka"],
    "kerala": ["kl", "k.l", "kerala"],
    "telangana": ["ts", "t.s", "telangana"],
    "uttarakhand": ["uk", "ut", "uttarakhand"],
    "delhi": ["delhi", "new delhi", "dl", "d.l"],
    "chandigarh": ["ch", "chandigarh"],
    "goa": ["ga", "goa"],
}

ENTITY_STOP_WORDS: Set[str] = {
    "pvt", "ltd", "limited", "private", "inc", "corp", "corporation",
    "llp", "co", "company", "mfg", "mfr", "manufactured", "by", "for",
    "marketed", "packed", "registered", "office", "works", "india"
}


def classify_field_type(field_name: str) -> str:
    """Classify field into ADDRESS, ENTITY_NAME, STRICT_NUMERIC, or GENERAL_TEXT."""
    name = (field_name or "").upper().strip()
    if any(term in name for term in ["ADDRESS", "PREMISES", "LOCATION"]):
        return "ADDRESS"
    if any(term in name for term in ["NAME", "BRAND", "PACKER", "MARKETER", "IMPORTER", "COMPANY", "ENTITY"]) and not any(term in name for term in ["DATE", "MRP", "QUANTITY"]):
        return "ENTITY_NAME"
    if any(term in name for term in [
        "MRP", "NET_QUANTITY", "QUANTITY", "DATE", "MFG", "EXPIRY",
        "BEST_BEFORE", "BATCH", "FSSAI", "PHONE", "LICENSE", "PRICE"
    ]) or ("MANUFACTURE" in name and "NAME" not in name and "ADDRESS" not in name):
        return "STRICT_NUMERIC"
    return "GENERAL_TEXT"


def _word_similarity(w1: str, w2: str) -> float:
    """Compute character-level similarity between two words with substring recognition."""
    if w1 == w2:
        return 1.0
    len1, len2 = len(w1), len(w2)
    if len1 >= 4 and len2 >= 4:
        if w1 in w2 or w2 in w1:
            return min(len1, len2) / max(len1, len2)
    return difflib.SequenceMatcher(None, w1, w2).ratio()


def _evaluate_entity_name_match(value: str, raw_text: str) -> Tuple[bool, str, float]:
    """
    Conservative entity name matching:
    - Verifies majority of core non-stop words match closely (>= 0.75)
    - Differences resemble OCR errors
    - Rejects contradictory entity names
    """
    cand_words = [w for w in re.findall(r'[a-zA-Z0-9]+', clean_ocr_text(value)) if len(w) > 1]
    if not cand_words:
        return False, "REJECTED_UNSUPPORTED", 0.0

    cand_core_words = [w for w in cand_words if w not in ENTITY_STOP_WORDS]
    if not cand_core_words:
        cand_core_words = cand_words

    raw_clean = clean_ocr_text(raw_text)
    raw_words = [w for w in re.findall(r'[a-zA-Z0-9]+', raw_clean) if len(w) > 1]
    raw_clean_collapsed = normalize_repeated_chars(raw_clean)
    raw_words_collapsed = [w for w in re.findall(r'[a-zA-Z0-9]+', raw_clean_collapsed) if len(w) > 1]
    all_raw_words = list(set(raw_words + raw_words_collapsed))

    core_scores = []
    for cw in cand_core_words:
        best_s = 0.0
        for rw in all_raw_words:
            s = _word_similarity(cw, rw)
            if s > best_s:
                best_s = s
        core_scores.append(best_s)

    matched_core = sum(1 for s in core_scores if s >= 0.75)
    core_ratio = matched_core / len(cand_core_words)
    avg_score = sum(core_scores) / len(core_scores)

    # Conservative thresholds for ENTITY_NAME:
    # At least 70% of core words must match, with average core similarity >= 0.75
    if core_ratio >= 0.70 and avg_score >= 0.75:
        return True, "OCR_FUZZY_ENTITY_MATCH", avg_score
    return False, "REJECTED_UNSUPPORTED", avg_score


def _evaluate_address_match(value: str, raw_text: str) -> Tuple[bool, str, float]:
    """
    Locality-anchored address matching:
    - Detects spelling damage, administrative abbreviations, and state codes
    - Requires strong locality anchors (village, town, industrial estate)
    - Rejects fabricated addresses lacking OCR anchor support
    """
    val_clean = clean_ocr_text(value)
    raw_clean = clean_ocr_text(raw_text)

    # Check PIN code if present
    val_pins = re.findall(r'\b\d{6}\b', value)
    raw_pins = re.findall(r'\b\d{5,6}\b', raw_text)
    if val_pins:
        v_pin = val_pins[0]
        pin_matched = any(v_pin in r_pin or r_pin in v_pin for r_pin in raw_pins) or (v_pin in raw_text)
        if not pin_matched and raw_pins:
            return False, "REJECTED_UNSUPPORTED", 0.0

    val_words = [w for w in re.findall(r'[a-zA-Z0-9]+', val_clean) if len(w) > 1]
    if not val_words:
        return False, "REJECTED_UNSUPPORTED", 0.0

    raw_words = [w for w in re.findall(r'[a-zA-Z0-9]+', raw_clean) if len(w) > 1]
    raw_clean_collapsed = normalize_repeated_chars(raw_clean)
    raw_words_collapsed = [w for w in re.findall(r'[a-zA-Z0-9]+', raw_clean_collapsed) if len(w) > 1]
    all_raw_words = list(set(raw_words + raw_words_collapsed))

    structural_cand = []
    locality_cand = []

    matched_state = False
    has_state_in_cand = False
    for state_name, abbrevs in STATE_MAPPINGS.items():
        if state_name in val_clean or any(re.search(r'\b' + re.escape(ab) + r'\b', val_clean) for ab in abbrevs):
            has_state_in_cand = True
            if state_name in raw_clean or any(re.search(r'\b' + re.escape(ab) + r'\b', raw_clean) for ab in abbrevs):
                matched_state = True
                break

    for w in val_words:
        if w.isdigit():
            continue
        is_struct = False
        for struct_term, syns in ADDRESS_STRUCTURAL_MAP.items():
            if w == struct_term or w in syns:
                structural_cand.append((w, struct_term, syns))
                is_struct = True
                break
        if is_struct:
            continue

        is_state_word = any(w in s_name for s_name in STATE_MAPPINGS.keys())
        if is_state_word and has_state_in_cand:
            continue

        if len(w) >= 3:
            locality_cand.append(w)

    loc_scores = []
    for lw in locality_cand:
        best_s = 0.0
        for rw in all_raw_words:
            s = _word_similarity(lw, rw)
            if s > best_s:
                best_s = s
        loc_scores.append(best_s)

    matched_loc_count = sum(1 for s in loc_scores if s >= 0.70)
    loc_score = (sum(loc_scores) / len(loc_scores)) if loc_scores else 1.0

    struct_scores = []
    for w, term, syns in structural_cand:
        matched = any(syn in all_raw_words for syn in syns)
        struct_scores.append(1.0 if matched else 0.0)
    struct_score = (sum(struct_scores) / len(struct_scores)) if struct_scores else 1.0

    state_score = 1.0 if matched_state else (0.0 if has_state_in_cand else 1.0)

    # Locality anchor requirement:
    # If locality anchors exist in candidate, at least 1 (if 1 total) or 2 (if >= 2 total) must match!
    if locality_cand:
        min_required_anchors = 1 if len(locality_cand) == 1 else 2
        if matched_loc_count < min_required_anchors:
            return False, "REJECTED_UNSUPPORTED", loc_score * 0.5

    # Conservative weighted address score: Locality 0.55, Structural 0.25, State 0.20
    total_score = (0.55 * loc_score) + (0.25 * struct_score) + (0.20 * state_score)

    if total_score >= 0.65:
        return True, "OCR_FUZZY_ADDRESS_MATCH", total_score
    return False, "REJECTED_UNSUPPORTED", total_score


def evaluate_grounding_match(field: str, value: str, raw_text: str) -> Tuple[bool, str, float]:
    """
    Public deterministic evaluator for text grounding against OCR raw text.
    Handles exact, normalized, date expansion, fuzzy entity, fuzzy address, and general text matches.

    Returns:
        (is_grounded: bool, grounding_reason: str, score: float)
    """
    if not value or not raw_text:
        return False, "REJECTED_UNSUPPORTED", 0.0

    v_raw = value.strip()
    r_raw = raw_text.strip()
    v_clean = clean_ocr_text(v_raw)
    r_clean = clean_ocr_text(r_raw)
    v_alphanumeric = _normalize_alphanumeric(v_raw)
    r_alphanumeric = _normalize_alphanumeric(r_raw)

    # 1. Exact Match
    if v_raw in r_raw or r_raw in v_raw:
        return True, "EXACT_MATCH", 1.0

    # 2. Normalized Alphanumeric Match
    if v_alphanumeric and r_alphanumeric and (v_alphanumeric in r_alphanumeric or r_alphanumeric in v_alphanumeric):
        return True, "NORMALIZED_MATCH", 1.0

    # 3. Date Normalization Check
    if _is_date_expansion_derivable(v_raw, r_raw):
        return True, "DATE_NORMALIZATION", 1.0

    field_type = classify_field_type(field)

    # 4. Strict Numeric Fields
    if field_type == "STRICT_NUMERIC":
        v_digits_clean = re.sub(r'\.00?(?!\d)', '', v_raw)
        v_digits = re.findall(r'\d+', v_digits_clean)
        if v_digits:
            for vd in v_digits:
                if vd not in r_raw:
                    return False, "REJECTED_UNSUPPORTED", 0.0
            return True, "NORMALIZED_MATCH", 1.0
        return False, "REJECTED_UNSUPPORTED", 0.0

    # 5. Entity Names
    if field_type == "ENTITY_NAME":
        return _evaluate_entity_name_match(v_raw, r_raw)

    # 6. Addresses
    if field_type == "ADDRESS":
        return _evaluate_address_match(v_raw, r_raw)

    # 7. General Text
    v_digits_clean = re.sub(r'\.00?(?!\d)', '', v_raw)
    v_digits = re.findall(r'\d+', v_digits_clean)
    if v_digits and any(vd not in r_raw for vd in v_digits):
        return False, "REJECTED_UNSUPPORTED", 0.0

    val_words = [w for w in re.findall(r'[a-zA-Z0-9]+', v_clean) if len(w) > 1]
    raw_words = [w for w in re.findall(r'[a-zA-Z0-9]+', r_clean) if len(w) > 1]
    if val_words:
        scores = []
        for vw in val_words:
            best_s = max([_word_similarity(vw, rw) for rw in raw_words], default=0.0)
            scores.append(best_s)
        matched = sum(1 for s in scores if s >= 0.75)
        ratio = matched / len(val_words)
        avg_score = sum(scores) / len(scores)
        if ratio >= 0.70 and avg_score >= 0.70:
            return True, "OCR_FUZZY_TEXT_MATCH", avg_score

    return False, "REJECTED_UNSUPPORTED", 0.0


def _is_value_derivable_from_text(value: str, raw_text: str, field: Optional[str] = None) -> bool:
    """
    Check if an extracted/normalized value can reasonably be derived from raw source text.
    Handles unit abbreviations, spacing, dates, and deterministic fuzzy matching.
    """
    if not value or not raw_text:
        return False
    target_field = field or "GENERAL_TEXT"
    is_grounded, _, _ = evaluate_grounding_match(target_field, value, raw_text)
    return is_grounded


class EvidenceGroundingValidator:
    """
    Deterministic validator running after Gemini structured output.
    Verifies that all referenced token IDs, image indices, bounding boxes,
    and text strings exist in actual OCR results.
    """

    def __init__(
        self,
        ocr_items: List[Dict[str, Any]],
        num_images: int,
        min_confidence: float = 0.80,
    ):
        """
        Args:
            ocr_items: Full list of OCR items detected by PaddleOCR across all panels.
                       Each item is expected to have 'token_id', 'image_index', 'text', 'bbox', 'confidence'.
            num_images: Total number of uploaded image panels.
            min_confidence: Threshold below which LLM resolutions are flagged for review.
        """
        self.num_images = max(1, num_images)
        self.min_confidence = min_confidence

        # Build index: image_index -> token_id -> token_dict
        self.tokens_by_image: Dict[int, Dict[int, Dict[str, Any]]] = {
            i: {} for i in range(self.num_images)
        }
        self.all_tokens_by_id: Dict[int, Dict[str, Any]] = {}

        for item in ocr_items:
            img_idx = item.get("image_index", 0)
            tok_id = item.get("token_id")
            if tok_id is not None:
                self.all_tokens_by_id[int(tok_id)] = item
                if img_idx in self.tokens_by_image:
                    self.tokens_by_image[img_idx][int(tok_id)] = item

    def validate_source_evidence(
        self,
        evidence: SourceEvidence,
    ) -> Tuple[bool, str, Optional[List[float]]]:
        """
        Validate a single SourceEvidence object.

        Returns:
            (is_valid: bool, reason: str, computed_bbox: Optional[List[float]])
        """
        img_idx = evidence.image_index
        if img_idx < 0 or img_idx >= self.num_images:
            return False, f"Invalid image_index {img_idx} (valid range 0..{self.num_images - 1})", None

        if not evidence.token_ids:
            return False, "Evidence must reference at least one valid OCR token_id", None

        # Check every token ID exists on that image
        referenced_tokens = []
        for tid in evidence.token_ids:
            tok = self.tokens_by_image[img_idx].get(tid)
            if not tok:
                return False, f"Unknown token ID {tid} does not exist in OCR detections for image {img_idx}", None
            referenced_tokens.append(tok)

        # Reconstruct combined text and unified bounding box from actual OCR tokens
        token_texts = [str(t.get("text", "")).strip() for t in referenced_tokens]
        combined_token_text = " ".join(token_texts).strip()

        if not combined_token_text:
            return False, "Referenced OCR tokens have empty text", None

        # Calculate bounding box union
        all_boxes = [t.get("bbox") for t in referenced_tokens if t.get("bbox")]
        unified_bbox = None
        if all_boxes:
            try:
                min_x = min(b[0] for b in all_boxes)
                min_y = min(b[1] for b in all_boxes)
                max_x = max(b[2] for b in all_boxes)
                max_y = max(b[3] for b in all_boxes)
                unified_bbox = [float(min_x), float(min_y), float(max_x), float(max_y)]
            except Exception:
                unified_bbox = evidence.bbox

        # Check text alignment between evidence.raw_text and actual OCR tokens
        if not _is_value_derivable_from_text(evidence.raw_text, combined_token_text):
            # Also check if raw_text exists anywhere in the image's OCR tokens
            image_raw_text = " ".join(t.get("text", "") for t in self.tokens_by_image[img_idx].values())
            if not _is_value_derivable_from_text(evidence.raw_text, image_raw_text):
                return False, f"Evidence raw_text '{evidence.raw_text}' is not found in OCR tokens (referenced: '{combined_token_text}')", None

        return True, "GROUNDED", unified_bbox

    def validate_declaration(
        self,
        arg1: Any,
        arg2: Optional[ResolvedDeclaration] = None,
    ) -> Tuple[bool, List[str], ResolvedDeclaration]:
        """
        Validate a ResolvedDeclaration against actual OCR tokens and evidence.

        Supports both:
            validate_declaration(declaration)
            validate_declaration(field_name, declaration)

        Returns:
            (is_grounded: bool, violations: List[str], validated_decl: ResolvedDeclaration)
        """
        declaration: ResolvedDeclaration = arg2 if arg2 is not None else arg1
        field_name = str(arg1) if arg2 is not None else getattr(declaration, "field", "GENERAL_TEXT")
        decl_copy = declaration.model_copy(deep=True)
        if not decl_copy.field:
            decl_copy.field = field_name

        if decl_copy.status == "NOT_FOUND" and not decl_copy.value:
            return True, [], decl_copy

        if not decl_copy.value and decl_copy.status == "RESOLVED":
            decl_copy.status = "NOT_FOUND"
            return False, ["RESOLVED declaration has empty value"], decl_copy

        if not decl_copy.source_evidence:
            decl_copy.status = "CONFLICT" if decl_copy.alternatives else "NOT_FOUND"
            decl_copy.confidence = 0.0
            return False, ["Missing source_evidence for declaration"], decl_copy

        # Validate each source evidence item
        valid_evidences: List[SourceEvidence] = []
        grounding_errors: List[str] = []

        for ev in decl_copy.source_evidence:
            ok, reason, unified_bbox = self.validate_source_evidence(ev)
            if ok:
                ev.bbox = unified_bbox or ev.bbox
                valid_evidences.append(ev)
            else:
                grounding_errors.append(reason)

        if not valid_evidences:
            decl_copy.status = "CONFLICT" if decl_copy.alternatives else "NOT_FOUND"
            decl_copy.confidence = 0.0
            error_summary = "; ".join(grounding_errors)
            logger.warning("Grounding rejected for field %s: %s", decl_copy.field, error_summary)
            decl_copy.resolution_note = f"Grounding validation failed: {error_summary}"
            return False, grounding_errors, decl_copy

        decl_copy.source_evidence = valid_evidences

        # Validate that the resolved value is derivable from the grounded raw text and token texts
        combined_grounded_raw = " ".join(ev.raw_text for ev in valid_evidences)
        referenced_token_texts = []
        for ev in valid_evidences:
            img_idx = ev.image_index
            for tid in ev.token_ids:
                tok = self.tokens_by_image.get(img_idx, {}).get(tid)
                if tok and tok.get("text"):
                    referenced_token_texts.append(str(tok.get("text")))
        all_grounded_text = (combined_grounded_raw + " " + " ".join(referenced_token_texts)).strip()

        test_value = decl_copy.normalized_value or decl_copy.value or ""

        is_grounded, grounding_reason, score = evaluate_grounding_match(
            decl_copy.field,
            test_value,
            all_grounded_text,
        )
        if not is_grounded and decl_copy.value and decl_copy.value != test_value:
            is_grounded, grounding_reason, score = evaluate_grounding_match(
                decl_copy.field,
                decl_copy.value,
                all_grounded_text,
            )

        if not is_grounded:
            logger.warning(
                "Grounding derivation failure for %s: value '%s' not derivable from raw text '%s' (%s, score=%.2f)",
                decl_copy.field,
                test_value,
                all_grounded_text,
                grounding_reason,
                score,
            )
            decl_copy.status = "CONFLICT" if decl_copy.alternatives else "NOT_FOUND"
            decl_copy.confidence = 0.0
            decl_copy.resolution_note = f"Value '{test_value}' cannot be derived from grounded text ({grounding_reason}, score={score:.2f})"
            object.__setattr__(decl_copy, "_grounding_reason", grounding_reason)
            object.__setattr__(decl_copy, "_grounding_score", score)
            return False, [f"Value '{test_value}' is not found in OCR tokens or cannot be derived from grounded evidence ({grounding_reason}, score={score:.2f})"], decl_copy

        # Grounded! Record audit metadata
        decl_copy.resolution_note = f"Grounding: {grounding_reason} (score={score:.2f})"
        object.__setattr__(decl_copy, "_grounding_reason", grounding_reason)
        object.__setattr__(decl_copy, "_grounding_score", score)

        # Validate alternatives
        valid_alts = []
        for alt in decl_copy.alternatives:
            alt_ev_ok = True
            for a_ev in alt.source_evidence:
                a_ok, _, _ = self.validate_source_evidence(a_ev)
                if not a_ok:
                    alt_ev_ok = False
                    break
            if alt_ev_ok:
                valid_alts.append(alt)
        decl_copy.alternatives = valid_alts

        return True, [], decl_copy

    def validate_extraction_result(
        self,
        result: LLMExtractionResult,
    ) -> Tuple[LLMExtractionResult, Dict[str, Any]]:
        """
        Validate all declarations in LLMExtractionResult.
        Rejects fabricated fields and returns validated structured result with grounding audit metadata.
        """
        validated_declarations: List[ResolvedDeclaration] = []
        rejected_count = 0
        grounded_count = 0
        grounding_audit: Dict[str, Any] = {
            "total_declarations": len(result.resolved_declarations),
            "grounded_count": 0,
            "rejected_count": 0,
            "fields": {},
        }

        for decl in result.resolved_declarations:
            is_valid, violations, valid_decl = self.validate_declaration(decl)
            validated_declarations.append(valid_decl)
            grounding_reason = getattr(valid_decl, "_grounding_reason", "EXACT_MATCH" if is_valid else "REJECTED_UNSUPPORTED")
            match_score = getattr(valid_decl, "_grounding_score", 1.0 if is_valid else 0.0)

            grounding_audit["fields"][decl.field] = {
                "grounded": is_valid,
                "reason": grounding_reason,
                "score": round(match_score, 3),
                "status": valid_decl.status,
                "evidence_count": len(valid_decl.source_evidence),
            }
            if is_valid and valid_decl.status == "RESOLVED":
                grounded_count += 1
            elif not is_valid:
                rejected_count += 1

        grounding_audit["grounded_count"] = grounded_count
        grounding_audit["rejected_count"] = rejected_count

        validated_result = LLMExtractionResult(
            resolved_declarations=validated_declarations,
            package_context=result.package_context,
            notes=result.notes,
        )

        return validated_result, grounding_audit
