"""
Universal Packaged-Product OCR / Evidence Association Engine.

Architectural pipeline:
OCR Tokens -> Semantic Sections -> Semantic Labels & Value Candidates ->
Normalized Spatial Relations -> Semantic & Section Compatibility ->
Scored Label-Value Associations -> Canonical Field Candidates with Provenance.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
import math
import re
from typing import Any, Callable, Dict, List, Optional, Pattern, Set, Tuple, Union

from app.core.ontology import (
    LEGAL_MASS_UNITS,
    LEGAL_VOLUME_UNITS,
    LEGAL_COUNT_UNITS,
    LEGAL_LENGTH_AREA_UNITS,
    build_quantity_candidate,
    infer_quantity_type,
    normalize_unit,
)
from app.extraction.cleaner import is_artifact_token, clean_ocr_evidence
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

# ---------------------------------------------------------------------------
# Canonical Semantic Sections (16 sections required by specification)
# ---------------------------------------------------------------------------
SECTION_PRODUCT_IDENTITY = "PRODUCT_IDENTITY"

ALL_CANONICAL_SECTIONS = [
    SECTION_FRONT_PRODUCT,
    SECTION_PRODUCT_IDENTITY,
    SECTION_QUANTITY,
    SECTION_DECLARED_QUANTITY,
    SECTION_PRICING,
    SECTION_MRP,
    SECTION_MANUFACTURER,
    SECTION_ADDRESS,
    SECTION_DATE,
    SECTION_BATCH,
    SECTION_NUTRITION,
    SECTION_SERVING_SIZE,
    SECTION_INGREDIENTS,
    SECTION_FOOD_LABELING,
    SECTION_CONSUMER_CARE,
    SECTION_BARCODE,
    SECTION_INSTRUCTIONS,
    SECTION_OTHER,
    SECTION_UNKNOWN,
]

# ---------------------------------------------------------------------------
# 1. Canonical Evidence Model Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EvidenceToken:
    """Individual normalized token produced from OCR with layout coordinates."""
    raw_text: str
    normalized_text: str
    source_image: str = ""
    source_type: str = SourceType.OCR.value
    bbox: Optional[Dict[str, Any]] = None
    confidence: float = 1.0
    line_id: Optional[int] = None
    region_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SemanticLabel:
    """Detected statutory declaration label."""
    label_text: str
    normalized_label: str
    semantic_type: str  # e.g., DECLARED_NET_QUANTITY, MRP, BATCH_NUMBER, MANUFACTURE_DATE, etc.
    bbox: Optional[Dict[str, Any]] = None
    source_image: str = ""
    confidence: float = 1.0
    line_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValueCandidate:
    """Discovered value token that could fulfill a statutory declaration."""
    raw_text: str
    parsed_value: Any
    unit: Optional[str] = None
    bbox: Optional[Dict[str, Any]] = None
    source_image: str = ""
    confidence: float = 1.0
    line_id: Optional[int] = None
    value_type: str = "TEXT"  # QUANTITY, CURRENCY, DATE, IDENTIFIER, ADDRESS, CONTACT, TEXT
    semantic_section: str = SECTION_UNKNOWN
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LabelValueRelation:
    """Spatial and semantic association between a SemanticLabel and a ValueCandidate."""
    label: SemanticLabel
    candidate: ValueCandidate
    spatial_relation: str  # SAME_LINE, RIGHT, LEFT, BELOW, ABOVE, OVERLAPPING, ALIGNED, NEARBY
    distance: float  # Normalized geometric distance (0.0 to 1.0+)
    same_line: bool
    aligned: bool
    semantic_compatibility: float  # 0.0 to 1.0
    section_compatibility: float   # 0.0 to 1.0
    relation_score: float          # Combined transparent score
    rejection_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label.to_dict(),
            "candidate": self.candidate.to_dict(),
            "spatial_relation": self.spatial_relation,
            "distance": self.distance,
            "same_line": self.same_line,
            "aligned": self.aligned,
            "semantic_compatibility": self.semantic_compatibility,
            "section_compatibility": self.section_compatibility,
            "relation_score": self.relation_score,
            "rejection_reason": self.rejection_reason,
        }


@dataclass
class CanonicalFieldCandidate:
    """Canonical statutory field candidate with full provenance and lifecycle validation."""
    field: str
    normalized_value: Any
    raw_text: str
    anchor_label: Optional[str] = None
    semantic_section: str = SECTION_UNKNOWN
    source_image: str = ""
    bbox: Optional[Dict[str, Any]] = None
    relevance_score: float = 0.0
    confidence: float = 0.0
    validation_state: str = ValidationState.UNASSESSED.value  # ACCEPTED, REJECTED_IRRELEVANT, AMBIGUOUS, NOT_VERIFIABLE
    rejection_reason: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "normalized_value": self.normalized_value,
            "raw_text": self.raw_text,
            "anchor_label": self.anchor_label,
            "semantic_section": self.semantic_section,
            "source_image": self.source_image,
            "bbox": self.bbox,
            "relevance_score": self.relevance_score,
            "confidence": self.confidence,
            "validation_state": self.validation_state,
            "rejection_reason": self.rejection_reason,
            "provenance": self.provenance,
            "metadata": self.metadata,
        }

    def to_evidence_candidate(self) -> EvidenceCandidate:
        """Promote to canonical EvidenceCandidate."""
        return EvidenceCandidate(
            raw_text=self.raw_text,
            normalized_text=str(self.normalized_value) if self.normalized_value is not None else None,
            source_image=self.source_image,
            source_type=SourceType.OCR.value,
            ocr_confidence=self.confidence,
            bounding_box=self.bbox,
            line_id=self.metadata.get("line_id"),
            semantic_section=self.semantic_section,
            anchor_label=self.anchor_label,
            anchor_relation=self.metadata.get("anchor_relation", AnchorRelation.SAME_LINE.value),
            candidate_field=self.field,
            relevance_score=self.relevance_score,
            validation_state=self.validation_state,
            metadata=self.metadata,
        )


# ---------------------------------------------------------------------------
# Statutory Label Vocabulary and Section Rules
# ---------------------------------------------------------------------------

LABEL_DEFINITIONS: List[Tuple[Pattern, str, str]] = [
    # (regex_pattern, semantic_label_type, target_field)
    (re.compile(r'\b(?:net\s*(?:wt\.?|weight|qty\.?|quantity|content|contents|vol\.?|volume)|declared\s+quantity|pack\s*(?:content|contents|size|qty\.?|quantity)|package\s*(?:quantity|content|contents)|pkg\s*qty)\b', re.I), "NET_QUANTITY", "DECLARED_NET_QUANTITY"),
    (re.compile(r'\b(?:m\.?\s*r\.?\s*p\.?|maximum\s+retail\s+price)\b', re.I), "MRP", "MRP"),
    (re.compile(r'\b(?:batch\s*(?:no\.?|number)?|b\.?\s*no\.?|lot\s*(?:no\.?|number)?|lot\s*[:#]|batch\s*[:#])\b', re.I), "BATCH_NUMBER", "BATCH_NUMBER"),
    (re.compile(r'\b(?:mfg\s*date|mfd\s*date|date\s+of\s+manufacture|manufacturing\s+date|mfd\b|mfg\b)', re.I), "MANUFACTURE_DATE", "MANUFACTURE_DATE"),
    (re.compile(r'\b(?:pkd\s*date|pkg\s*date|packed\s+on|date\s+of\s+pack\w+|packing\s+date|pkd\b)', re.I), "PACKING_DATE", "PACKING_DATE"),
    (re.compile(r'\b(?:best\s+before|best\s+by|consume\s+before)\b', re.I), "BEST_BEFORE_DATE", "BEST_BEFORE_USE_BY"),
    (re.compile(r'\b(?:use\s*-?\s*by|use\s+before|consume\s+within|valid\s+till)\b', re.I), "USE_BY_DATE", "USE_BEFORE_DATE"),
    (re.compile(r'\b(?:expiry\s*date|exp\s*date|exp\.?\s*date|expiry\b|exp\b)', re.I), "EXPIRY_DATE", "EXPIRY_DATE"),
    (re.compile(r'\b(?:manufactured\s*(?:&|and|/)?\s*(?:marketed|packed|pkd)?\s*(?:by|at|for)|mfg\s*(?:&|and)?\s*pkd\s*by|mfg\s*by|mfd\s*by)\b', re.I), "MANUFACTURER_NAME", "MANUFACTURER_NAME"),
    (re.compile(r'\b(?:marketed\s*(?:&|and)?\s*distributed\s*by|marketed\s*by|mkt\s*by|mktg\s*by|marketer)\b', re.I), "MARKETER_NAME", "MARKETER_NAME"),
    (re.compile(r'\b(?:packed\s*(?:&|and)?\s*marketed\s*by|packed\s*by|pkd\s*by|packer)\b', re.I), "PACKER_NAME", "PACKER_NAME"),
    (re.compile(r'\b(?:imported\s*by|importer)\b', re.I), "IMPORTER_NAME", "IMPORTER_NAME"),
    (re.compile(r'\b(?:consumer\s*care|customer\s*care|helpline|toll\s*free|feedback|call\s*us)\b', re.I), "CONSUMER_CARE", "CONSUMER_CARE"),
    (re.compile(r'\b(?:ingredients?|composition|contains?\s*:)\b', re.I), "INGREDIENTS", "INGREDIENTS_LIST"),
    (re.compile(r'\b(?:nutritional?\s*(?:information|facts)|nutrition\s+facts)\b', re.I), "NUTRITION", "NUTRITIONAL_INFO"),
    (re.compile(r'\b(?:serv(?:e|ing)\s*size|per\s+(?:serve|serving)|servings?\s+per\s+pack)\b', re.I), "SERVING_SIZE", "SERVING_SIZE"),
    (re.compile(r'\b(?:fssai|lic\.?\s*(?:no\.?|number)?|licen[cs]e\s*(?:no\.?|number)?)\b', re.I), "FSSAI", "FSSAI_LICENSE"),
    (re.compile(r'\b(?:country\s+of\s+origin|made\s+in|product\s+of)\b', re.I), "COUNTRY_OF_ORIGIN", "COUNTRY_OF_ORIGIN"),
    (re.compile(r'\b(?:generic\s+name|name\s+of\s+commodity|commodity)\b', re.I), "GENERIC_NAME", "GENERIC_NAME"),
]

INVALID_BATCH_TOKENS = {
    'no', 'no.', 'number', 'num', 'num.', 'code', 'lot', 'batch',
    'b.no', 'b.no.', 'lot.no', 'lot.no.', 'date', 'mfg', 'mfd',
    'rs', 'rs.', 'inr', 'mrp', 'image', 'placeholder', 'undefined',
}

# ---------------------------------------------------------------------------
# 2. Label-Value Association Engine
# ---------------------------------------------------------------------------

class LabelValueAssociationEngine:
    """
    Universal Association Engine connecting statutory declaration labels to their
    semantically, geometrically, and contextually validated values.
    """

    @staticmethod
    def parse_bounding_box(box: Any) -> Optional[Tuple[float, float, float, float, float, float]]:
        """
        Parse bounding box into (x_min, y_min, x_max, y_max, center_x, center_y).
        Accepts dict with keys {x, y, w, h} / {left, top, width, height} or [x1, y1, x2, y2].
        """
        if not box:
            return None
        if isinstance(box, dict):
            x = float(box.get('x', box.get('left', 0)))
            y = float(box.get('y', box.get('top', 0)))
            w = float(box.get('w', box.get('width', 0)))
            h = float(box.get('h', box.get('height', 0)))
            return x, y, x + w, y + h, x + w / 2.0, y + h / 2.0
        elif isinstance(box, (list, tuple)) and len(box) >= 4:
            x1, y1, x2, y2 = float(box[0]), float(box[1]), float(box[2]), float(box[3])
            return x1, y1, x2, y2, (x1 + x2) / 2.0, (y1 + y2) / 2.0
        return None

    @classmethod
    def calculate_normalized_spatial_relation(
        cls,
        box_label: Any,
        box_value: Any,
        image_dimensions: Optional[Tuple[float, float]] = None,
        line_diff: int = 0,
    ) -> Tuple[str, float, bool, bool]:
        """
        Compute normalized geometric spatial relationship between label and candidate.
        Returns:
            (spatial_relation, normalized_distance, is_same_line, is_aligned)
        
        Normalized distance is scaled by image dimensions or token extent, never raw pixel bounds.
        """
        b1 = cls.parse_bounding_box(box_label)
        b2 = cls.parse_bounding_box(box_value)

        # Fallback when bounding boxes are missing (relying on line indices)
        if not b1 or not b2:
            if line_diff == 0:
                return AnchorRelation.SAME_LINE.value, 0.0, True, True
            elif line_diff > 0:
                norm_d = min(1.0, float(line_diff) * 0.15)
                return AnchorRelation.BELOW.value, norm_d, False, False
            else:
                norm_d = min(1.0, float(abs(line_diff)) * 0.15)
                return AnchorRelation.ABOVE.value, norm_d, False, False

        x1_min, y1_min, x1_max, y1_max, cx1, cy1 = b1
        x2_min, y2_min, x2_max, y2_max, cx2, cy2 = b2

        w1 = max(1.0, x1_max - x1_min)
        h1 = max(1.0, y1_max - y1_min)
        w2 = max(1.0, x2_max - x2_min)
        h2 = max(1.0, y2_max - y2_min)

        # Use passed image dimensions or estimate from coordinate envelope
        if image_dimensions and image_dimensions[0] > 0 and image_dimensions[1] > 0:
            img_w, img_h = image_dimensions
        else:
            img_w = max(100.0, max(x1_max, x2_max) * 1.2)
            img_h = max(100.0, max(y1_max, y2_max) * 1.2)

        # Normalized coordinates relative to image frame
        norm_dx = (cx2 - cx1) / img_w
        norm_dy = (cy2 - cy1) / img_h
        norm_dist = math.hypot(norm_dx, norm_dy)

        # Check vertical overlap for same horizontal text row
        overlap_y = max(0.0, min(y1_max, y2_max) - max(y1_min, y2_min))
        ref_h = min(h1, h2)
        is_same_row = (overlap_y / ref_h >= 0.35) if ref_h > 0 else (abs(norm_dy) < 0.03)

        # Left alignment check (both left edges align within 4% of image width)
        is_left_aligned = abs(x1_min - x2_min) / img_w < 0.04

        # Intersection over Union for overlapping boxes
        overlap_x = max(0.0, min(x1_max, x2_max) - max(x1_min, x2_min))
        intersection_area = overlap_x * overlap_y
        union_area = (w1 * h1) + (w2 * h2) - intersection_area
        iou = (intersection_area / union_area) if union_area > 0 else 0.0

        if iou > 0.15:
            return "OVERLAPPING", norm_dist, True, True

        if is_same_row:
            if cx2 >= cx1:
                # Value is immediately to the right of the label
                rel = AnchorRelation.SAME_LINE.value if norm_dist < 0.25 else AnchorRelation.RIGHT.value
                return rel, norm_dist, True, is_left_aligned
            else:
                return AnchorRelation.LEFT.value, norm_dist, True, is_left_aligned

        if cy2 > cy1:
            # Value is beneath the label
            return AnchorRelation.BELOW.value, norm_dist, False, is_left_aligned

        return AnchorRelation.ABOVE.value, norm_dist, False, is_left_aligned

    @classmethod
    def classify_line_semantic_section(cls, line_text: str, previous_section: str = SECTION_UNKNOWN) -> str:
        """Assign an individual OCR text line to its primary semantic section."""
        lt = line_text.strip().lower()
        if not lt:
            return previous_section

        if re.search(r'\b(?:nutritional?\s*(?:information|facts)|nutrition\s+table)\b', lt):
            return SECTION_NUTRITION
        if re.search(r'\b(?:energy|calories|protein|carbohydrate|fat|sugar|sodium|cholesterol)\b', lt) and re.search(r'\b(?:per\s+100|approx|kcal|kj|g|mg)\b', lt):
            return SECTION_NUTRITION
        if re.search(r'\b(?:serv(?:e|ing)\s*size|per\s+(?:serve|serving)|servings?\s+per)\b', lt):
            return SECTION_SERVING_SIZE
        if re.search(r'\b(?:ingredients?|composition|contains?\s*:)\b', lt):
            return SECTION_INGREDIENTS
        if re.search(r'\b(?:consumer\s*care|customer\s*care|helpline|toll\s*free|feedback|call\s*us)\b', lt):
            return SECTION_CONSUMER_CARE
        if re.search(r'\b(?:m\.?\s*r\.?\s*p\.?|maximum\s+retail\s+price)\b', lt):
            return SECTION_MRP
        if re.search(r'\b(?:net\s*(?:wt\.?|weight|qty\.?|quantity|vol\.?|volume)|declared\s+quantity)\b', lt):
            return SECTION_DECLARED_QUANTITY
        if re.search(r'\b(?:batch\s*(?:no\.?|number)?|b\.?\s*no\.?|lot\s*(?:no\.?|number)?)\b', lt):
            return SECTION_BATCH
        if re.search(r'\b(?:mfg\s*date|pkd\s*date|best\s+before|use\s*by|expiry\s*date|exp\.?\s*date)\b', lt):
            return SECTION_DATE
        if re.search(r'\b(?:manufactured\s*by|mfg\s*by|mfd\s*by|produced\s*by)\b', lt):
            return SECTION_MANUFACTURER
        if re.search(r'\b(?:packed\s*by|pkd\s*by|pkg\s*by|packer)\b', lt):
            return SECTION_PACKER
        if re.search(r'\b(?:plot|survey|industrial\s*area|road|street|dist|state|pin\s*\d{6}|india)\b', lt) and previous_section in (SECTION_MANUFACTURER, SECTION_PACKER, SECTION_ADDRESS):
            return SECTION_ADDRESS
        if re.search(r'\b(?:fssai|lic\.?\s*(?:no\.?|number)?)\b', lt):
            return SECTION_FOOD_LABELING
        if re.search(r'\b(?:store\s+in|keep\s+in|cool\s*(&|and)?\s*dry\s+place|do\s+not\s+freeze)\b', lt):
            return SECTION_INSTRUCTIONS
        if re.search(r'\b(?:barcode|ean|upc)\b', lt):
            return SECTION_BARCODE

        return previous_section if previous_section != SECTION_UNKNOWN else SECTION_OTHER

    @classmethod
    def evaluate_semantic_and_section_compatibility(
        cls,
        target_field: str,
        label: SemanticLabel,
        candidate: ValueCandidate,
        candidate_section: str,
    ) -> Tuple[float, float, Optional[str]]:
        """
        Evaluate semantic and section compatibility for a candidate under a target field.
        Returns:
            (semantic_compatibility, section_compatibility, rejection_reason)
        """
        sem_compat = 1.0
        sec_compat = 1.0
        rejection_reason = None

        # -------------------------------------------------------------------
        # 1. DECLARED_NET_QUANTITY
        # -------------------------------------------------------------------
        if target_field == "DECLARED_NET_QUANTITY":
            if candidate.value_type != "QUANTITY":
                return 0.0, 0.0, f"Rejected because candidate value type is '{candidate.value_type}', not QUANTITY."

            # Section Scoping: strictly exclude nutritional table & serving size
            if candidate_section == SECTION_NUTRITION:
                return 0.0, 0.0, "Rejected because candidate belongs to NUTRITION section, not declared net quantity."
            elif candidate_section == SECTION_SERVING_SIZE:
                return 0.0, 0.0, "Rejected because candidate belongs to SERVING_SIZE section, not declared net quantity."
            elif candidate_section in (SECTION_CONSUMER_CARE, SECTION_STORAGE, SECTION_BARCODE):
                return 0.5, 0.0, f"Rejected because candidate belongs to {candidate_section} section."
            elif candidate_section in (SECTION_DECLARED_QUANTITY, SECTION_QUANTITY, SECTION_FRONT_PRODUCT):
                sec_compat = 1.0
            else:
                sec_compat = 0.8

            # Net Quantity requires mass, volume, or count
            unit_norm = str(candidate.unit or '').lower()
            if unit_norm in LEGAL_MASS_UNITS or unit_norm in LEGAL_VOLUME_UNITS or unit_norm in LEGAL_COUNT_UNITS:
                sem_compat = 1.0
            else:
                sem_compat = 0.7

            return sem_compat, sec_compat, None

        # -------------------------------------------------------------------
        # 2. MRP (Maximum Retail Price)
        # -------------------------------------------------------------------
        if target_field == "MRP":
            if candidate_section in (SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_INGREDIENTS):
                return 0.0, 0.0, f"Rejected because candidate belongs to {candidate_section} section."
            if candidate.value_type not in ("CURRENCY", "NUMBER", "TEXT"):
                return 0.0, 0.0, f"Rejected because candidate value type '{candidate.value_type}' is incompatible with MRP."
            
            # Numeric presence required
            num_val = candidate.parsed_value
            if num_val is None or (isinstance(num_val, (int, float)) and num_val <= 0):
                return 0.0, 0.0, "Rejected because MRP candidate does not contain a valid positive price."
            
            if candidate.metadata.get("is_corrupted_currency"):
                sem_compat = 0.6
                sec_compat = 0.9
                rejection_reason = "Corrupted currency symbol detected; flagged for review."
            else:
                sem_compat = 1.0
                sec_compat = 1.0 if candidate_section in (SECTION_MRP, SECTION_PRICING) else 0.85

            return sem_compat, sec_compat, rejection_reason

        # -------------------------------------------------------------------
        # 3. BATCH_NUMBER
        # -------------------------------------------------------------------
        if target_field == "BATCH_NUMBER":
            val_clean = str(candidate.parsed_value or '').strip()
            val_lower = val_clean.lower()
            
            if is_artifact_token(val_clean):
                return 0.0, 0.0, "Rejected because candidate is a placeholder token."
            if val_lower in INVALID_BATCH_TOKENS or val_lower == label.normalized_label.lower():
                return 0.0, 0.0, f"Rejected because label text '{val_clean}' cannot be the batch value."
            if len(re.sub(r'[^A-Za-z0-9]', '', val_clean)) < 1:
                return 0.0, 0.0, "Rejected because batch candidate lacks alphanumeric characters."
            if candidate_section in (SECTION_NUTRITION, SECTION_SERVING_SIZE):
                return 0.0, 0.0, f"Rejected because candidate belongs to {candidate_section} section."

            sem_compat = 1.0
            sec_compat = 1.0 if candidate_section in (SECTION_BATCH, SECTION_DATE) else 0.8
            return sem_compat, sec_compat, None

        # -------------------------------------------------------------------
        # 4. DATES (MANUFACTURE_DATE, PACKING_DATE, BEST_BEFORE_DATE, etc.)
        # -------------------------------------------------------------------
        if target_field in ("MANUFACTURE_DATE", "PACKING_DATE", "BEST_BEFORE_USE_BY", "USE_BEFORE_DATE", "EXPIRY_DATE", "MONTH_YEAR_MANUFACTURE"):
            if candidate_section in (SECTION_NUTRITION, SECTION_SERVING_SIZE):
                return 0.0, 0.0, f"Rejected because candidate belongs to {candidate_section} section."

            # Date semantics MUST match anchor label semantics
            label_type = label.semantic_type
            if target_field == "MANUFACTURE_DATE" and label_type not in ("MANUFACTURE_DATE", "UNKNOWN"):
                return 0.0, 0.0, f"Rejected because anchor label '{label.label_text}' is {label_type}, not MANUFACTURE_DATE."
            if target_field == "PACKING_DATE" and label_type not in ("PACKING_DATE", "UNKNOWN"):
                return 0.0, 0.0, f"Rejected because anchor label '{label.label_text}' is {label_type}, not PACKING_DATE."
            if target_field == "BEST_BEFORE_USE_BY" and label_type not in ("BEST_BEFORE_DATE", "UNKNOWN"):
                return 0.0, 0.0, f"Rejected because anchor label '{label.label_text}' is {label_type}, not BEST_BEFORE."
            if target_field == "USE_BEFORE_DATE" and label_type not in ("USE_BY_DATE", "UNKNOWN"):
                return 0.0, 0.0, f"Rejected because anchor label '{label.label_text}' is {label_type}, not USE_BY."
            if target_field == "EXPIRY_DATE" and label_type not in ("EXPIRY_DATE", "UNKNOWN"):
                return 0.0, 0.0, f"Rejected because anchor label '{label.label_text}' is {label_type}, not EXPIRY."

            sem_compat = 1.0 if candidate.value_type == "DATE" else 0.7
            sec_compat = 1.0 if candidate_section in (SECTION_DATE, SECTION_BATCH) else 0.8
            return sem_compat, sec_compat, None

        # -------------------------------------------------------------------
        # 5. MANUFACTURER / PACKER / ADDRESS
        # -------------------------------------------------------------------
        if target_field in ("MANUFACTURER_NAME", "PACKER_NAME", "MARKETER_NAME", "MANUFACTURER_ADDRESS", "PACKER_ADDRESS", "MARKETER_ADDRESS"):
            if candidate_section in (SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_MRP, SECTION_DECLARED_QUANTITY):
                return 0.0, 0.0, f"Rejected because candidate belongs to {candidate_section} section."
            
            # Address candidates must not contain phone numbers, URLs, barcodes
            val_str = str(candidate.parsed_value or '')
            if target_field in ("MANUFACTURER_ADDRESS", "PACKER_ADDRESS", "MARKETER_ADDRESS"):
                if re.search(r'\b(?:1800\d+|call\s*us|helpline|toll\s*free)\b', val_str, re.I):
                    return 0.2, 0.0, "Rejected because candidate contains customer support contact details."
            
            sem_compat = 1.0
            sec_compat = 1.0 if candidate_section in (SECTION_MANUFACTURER, SECTION_PACKER, SECTION_ADDRESS) else 0.75
            return sem_compat, sec_compat, None

        # Default fallback
        return sem_compat, sec_compat, None

    @classmethod
    def calculate_candidate_score(
        cls,
        label: SemanticLabel,
        candidate: ValueCandidate,
        spatial_relation: str,
        normalized_distance: float,
        sem_compat: float,
        sec_compat: float,
    ) -> float:
        """
        Calculate transparent candidate score combining label relevance, spatial relation,
        semantic section compatibility, expected data type, and OCR confidence.
        """
        if sem_compat <= 0.0 or sec_compat <= 0.0:
            return 0.0

        # Spatial weighting factor
        if spatial_relation == AnchorRelation.SAME_LINE.value or spatial_relation == "OVERLAPPING":
            spatial_factor = 1.0
        elif spatial_relation == AnchorRelation.RIGHT.value:
            spatial_factor = max(0.70, 0.95 - (normalized_distance * 0.4))
        elif spatial_relation == AnchorRelation.BELOW.value:
            spatial_factor = max(0.60, 0.88 - (normalized_distance * 0.4))
        elif spatial_relation == "NEARBY":
            spatial_factor = max(0.50, 0.75 - (normalized_distance * 0.5))
        else:
            spatial_factor = max(0.40, 0.60 - (normalized_distance * 0.4))

        score = (
            label.confidence * 0.25 +
            spatial_factor * 0.30 +
            sem_compat * 0.20 +
            sec_compat * 0.15 +
            candidate.confidence * 0.10
        )
        return round(score, 4)

    @classmethod
    def associate_tokens_and_build_candidates(
        cls,
        raw_text: str,
        ocr_items: Optional[List[Dict[str, Any]]] = None,
        image_name: str = "",
        image_dimensions: Optional[Tuple[float, float]] = None,
    ) -> Dict[str, CanonicalFieldCandidate]:
        """
        Execute full label-value association pipeline:
        1. Tokenize & Clean
        2. Detect Semantic Sections
        3. Detect Labels & Value Candidates
        4. Calculate Spatial & Semantic Relationships
        5. Rank Candidates & Preserve Rejected Alternatives
        6. Produce CanonicalFieldCandidate Pool
        """
        cleaned_text, cleaned_items, _ = clean_ocr_evidence(raw_text, ocr_items)
        effective_text = cleaned_text or raw_text
        effective_items = cleaned_items or ocr_items or []

        lines = [l.strip() for l in effective_text.split('\n') if l.strip()]
        if not lines and not effective_items:
            return {}

        # -------------------------------------------------------------------
        # 1. Detect Semantic Sections per line
        # -------------------------------------------------------------------
        section_map: Dict[int, str] = {}
        curr_sec = SECTION_UNKNOWN
        for idx, line in enumerate(lines):
            curr_sec = cls.classify_line_semantic_section(line, curr_sec)
            section_map[idx] = curr_sec

        # -------------------------------------------------------------------
        # 2. Detect Labels
        # -------------------------------------------------------------------
        detected_labels: List[SemanticLabel] = []
        for idx, line in enumerate(lines):
            for pat, label_type, field_name in LABEL_DEFINITIONS:
                m = pat.search(line)
                if m:
                    label_text = m.group(0).strip()
                    detected_labels.append(SemanticLabel(
                        label_text=label_text,
                        normalized_label=label_text.lower(),
                        semantic_type=label_type,
                        line_id=idx,
                        source_image=image_name,
                        confidence=0.90,
                    ))

        # Check item-level labels with bounding boxes
        for item in effective_items:
            item_text = str(item.get('text', '')).strip()
            for pat, label_type, field_name in LABEL_DEFINITIONS:
                m = pat.search(item_text)
                if m and item.get('bbox'):
                    label_text = m.group(0).strip()
                    detected_labels.append(SemanticLabel(
                        label_text=label_text,
                        normalized_label=label_text.lower(),
                        semantic_type=label_type,
                        bbox=item.get('bbox'),
                        source_image=image_name,
                        confidence=float(item.get('confidence') or 0.85),
                    ))

        # -------------------------------------------------------------------
        # 3. Detect Value Candidates
        # -------------------------------------------------------------------
        detected_values: List[ValueCandidate] = []

        # Quantities
        qty_pat = re.compile(r'\b([+-]?\d+(?:\.\d+)?)\s*(g|gm|gms|kg|kgs|ml|l|ltr|litre|litres|liter|liters|pcs|pieces|tablets|capsules|units|n)\b', re.I)
        for idx, line in enumerate(lines):
            line_sec = section_map.get(idx, SECTION_UNKNOWN)

            # Check for multipack on line first
            from app.extraction.declaration_extractor import parse_quantity_expression
            multi_parsed = parse_quantity_expression(line)
            if multi_parsed and multi_parsed.get("is_multipack"):
                norm_u = multi_parsed["unit"]
                q_type = infer_quantity_type(norm_u)
                detected_values.append(ValueCandidate(
                    raw_text=multi_parsed["declared_expression"],
                    parsed_value=multi_parsed["unit_net_quantity"],
                    unit=norm_u,
                    line_id=idx,
                    source_image=image_name,
                    confidence=0.95,
                    value_type="QUANTITY",
                    semantic_section=line_sec,
                    metadata={
                        "is_multipack": True,
                        "pack_count": multi_parsed["pack_count"],
                        "unit_net_quantity": multi_parsed["unit_net_quantity"],
                        "declared_expression": multi_parsed["declared_expression"],
                        "derived_total_quantity": multi_parsed["derived_total_quantity"],
                        "quantity_type": q_type.value if q_type else "MASS",
                    },
                ))
                continue

            for m in qty_pat.finditer(line):
                val_num = float(m.group(1)) if '.' in m.group(1) else int(m.group(1))
                norm_u, _ = normalize_unit(m.group(2))
                q_type = infer_quantity_type(norm_u)
                detected_values.append(ValueCandidate(
                    raw_text=m.group(0).strip(),
                    parsed_value=val_num,
                    unit=norm_u,
                    line_id=idx,
                    source_image=image_name,
                    confidence=0.90,
                    value_type="QUANTITY",
                    semantic_section=line_sec,
                    metadata={"quantity_type": q_type.value if q_type else "MASS"},
                ))

        # MRP / Prices
        for idx, line in enumerate(lines):
            line_sec = section_map.get(idx, SECTION_UNKNOWN)
            if 'mrp' in line.lower() or '₹' in line or 'rs' in line.lower():
                # Check for corrupted currency symbol
                is_corrupted = bool(re.search(r'[■\?*#§¤]', line))
                m = re.search(r'([+-]?\d+(?:[.,]\d{1,2})?)', line)
                if m:
                    try:
                        p_val = float(m.group(1).replace(',', ''))
                        detected_values.append(ValueCandidate(
                            raw_text=line.strip(),
                            parsed_value=p_val,
                            unit="INR",
                            line_id=idx,
                            source_image=image_name,
                            confidence=0.85,
                            value_type="CURRENCY",
                            semantic_section=line_sec,
                            metadata={"is_corrupted_currency": is_corrupted},
                        ))
                    except ValueError:
                        pass

        # Dates
        date_pat = re.compile(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}|[A-Za-z]{3,9}\s+\d{4})\b')
        for idx, line in enumerate(lines):
            line_sec = section_map.get(idx, SECTION_UNKNOWN)
            for m in date_pat.finditer(line):
                detected_values.append(ValueCandidate(
                    raw_text=m.group(0).strip(),
                    parsed_value=m.group(0).strip(),
                    line_id=idx,
                    source_image=image_name,
                    confidence=0.85,
                    value_type="DATE",
                    semantic_section=line_sec,
                ))

        # Batch codes
        for idx, line in enumerate(lines):
            line_sec = section_map.get(idx, SECTION_UNKNOWN)
            if re.search(r'\b(?:batch|lot|b\.?no)\b', line, re.I):
                after_label = re.sub(r'.*?\b(?:batch|lot|b\.?no)\s*[:#.-]*\s*', '', line, flags=re.I).strip()
                tokens = after_label.split()
                if tokens:
                    first_tok = tokens[0].strip(' ,;:')
                    if first_tok.lower() not in INVALID_BATCH_TOKENS and len(re.sub(r'[^A-Za-z0-9]', '', first_tok)) >= 1:
                        detected_values.append(ValueCandidate(
                            raw_text=first_tok,
                            parsed_value=first_tok,
                            line_id=idx,
                            source_image=image_name,
                            confidence=0.85,
                            value_type="IDENTIFIER",
                            semantic_section=line_sec,
                        ))

        # -------------------------------------------------------------------
        # 4. Association & Scoring Matrix
        # -------------------------------------------------------------------
        candidates_by_field: Dict[str, List[CanonicalFieldCandidate]] = {}

        # Target fields to resolve via association
        target_fields = [
            ("DECLARED_NET_QUANTITY", "NET_QUANTITY"),
            ("MRP", "MRP"),
            ("BATCH_NUMBER", "BATCH_NUMBER"),
            ("MANUFACTURE_DATE", "MANUFACTURE_DATE"),
            ("PACKING_DATE", "PACKING_DATE"),
            ("BEST_BEFORE_USE_BY", "BEST_BEFORE_DATE"),
            ("USE_BEFORE_DATE", "USE_BY_DATE"),
            ("EXPIRY_DATE", "EXPIRY_DATE"),
        ]

        for target_field, target_label_type in target_fields:
            matching_labels = [l for l in detected_labels if l.semantic_type == target_label_type]
            if not matching_labels:
                # Create synthetic unanchored label if not explicitly found
                matching_labels = [SemanticLabel(
                    label_text="",
                    normalized_label="",
                    semantic_type=target_label_type,
                    confidence=0.5,
                )]

            field_scored: List[Tuple[float, ValueCandidate, SemanticLabel, str, Optional[str]]] = []

            for label in matching_labels:
                for val in detected_values:
                    # Spatial relationship
                    line_diff = (val.line_id - label.line_id) if (val.line_id is not None and label.line_id is not None) else 0
                    rel, norm_dist, same_line, aligned = cls.calculate_normalized_spatial_relation(
                        label.bbox, val.bbox, image_dimensions=image_dimensions, line_diff=line_diff
                    )

                    sem_compat, sec_compat, rej_reason = cls.evaluate_semantic_and_section_compatibility(
                        target_field, label, val, val.semantic_section
                    )

                    score = cls.calculate_candidate_score(
                        label, val, rel, norm_dist, sem_compat, sec_compat
                    )

                    field_scored.append((score, val, label, rel, rej_reason))

            if not field_scored:
                continue

            # Sort descending by relation score
            field_scored.sort(key=lambda item: item[0], reverse=True)

            accepted_cands = [item for item in field_scored if item[0] > 0.0 and item[4] is None]
            rejected_cands = [item for item in field_scored if item[0] == 0.0 or item[4] is not None]

            if accepted_cands:
                winner_score, winner_val, winner_lbl, winner_rel, _ = accepted_cands[0]
                
                # Check for ambiguity: multiple candidates within 0.08 score difference
                val_state = ValidationState.PASS.value if winner_score >= 0.65 else ValidationState.REVIEW.value
                rej_msg = None
                if len(accepted_cands) > 1 and (winner_score - accepted_cands[1][0]) < 0.08:
                    val_state = "AMBIGUOUS"
                    rej_msg = "Ambiguous: multiple candidates have near-identical semantic association scores."

                provenance = {
                    "what": winner_val.parsed_value,
                    "why": f"Anchored by label '{winner_lbl.label_text}' with {winner_rel} spatial relation (score: {winner_score:.2f})",
                    "where": winner_val.bbox or {"line_id": winner_val.line_id},
                    "which_label": winner_lbl.label_text,
                    "which_image": winner_val.source_image,
                    "confidence": winner_score,
                    "validation": val_state,
                }

                cfc = CanonicalFieldCandidate(
                    field=target_field,
                    normalized_value=winner_val.parsed_value,
                    raw_text=winner_val.raw_text,
                    anchor_label=winner_lbl.label_text or None,
                    semantic_section=winner_val.semantic_section,
                    source_image=winner_val.source_image,
                    bbox=winner_val.bbox,
                    relevance_score=winner_score,
                    confidence=winner_val.confidence,
                    validation_state=val_state,
                    rejection_reason=rej_msg,
                    provenance=provenance,
                    metadata={
                        "unit": winner_val.unit,
                        "value_type": winner_val.value_type,
                        "anchor_relation": winner_rel,
                        "line_id": winner_val.line_id,
                        "rejected_alternatives": [
                            {
                                "raw_text": r[1].raw_text,
                                "section": r[1].semantic_section,
                                "score": r[0],
                                "reason": r[4] or "Lower semantic score than winning candidate",
                            }
                            for r in (accepted_cands[1:] + rejected_cands)
                        ],
                    },
                )
                candidates_by_field[target_field] = [cfc]

        # Convert to dictionary format
        result_fields: Dict[str, CanonicalFieldCandidate] = {}
        for f_name, c_list in candidates_by_field.items():
            if c_list:
                result_fields[f_name] = c_list[0]

        return result_fields
