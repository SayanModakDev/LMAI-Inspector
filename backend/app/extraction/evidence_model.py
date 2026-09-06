"""
Canonical Evidence Object and Field Scoping Specification for Legal Metrology Inspections.

Every OCR-derived candidate must first exist as an EvidenceCandidate before it can
become a structured field, passing through semantic association and validation.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class SourceType(str, Enum):
    """Source modality for evidence."""
    OCR = "OCR"
    VISUAL = "VISUAL"
    BARCODE = "BARCODE"
    OTHER = "OTHER"


class AnchorRelation(str, Enum):
    """Spatial/layout relationship between an anchor label and its candidate value."""
    SAME_LINE = "SAME_LINE"
    BELOW = "BELOW"
    RIGHT = "RIGHT"
    ABOVE = "ABOVE"
    LEFT = "LEFT"
    SAME_BLOCK = "SAME_BLOCK"
    UNANCHORED = "UNANCHORED"


class ValidationState(str, Enum):
    """Lifecycle validation status of a candidate."""
    UNASSESSED = "UNASSESSED"
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    REJECTED = "REJECTED"


class EvidenceMergeClassification(str, Enum):
    """Multi-image evidence merge classification types."""
    CONFIRMED_SAME = "CONFIRMED_SAME"
    COMPLEMENTARY = "COMPLEMENTARY"
    TRUE_CONFLICT = "TRUE_CONFLICT"
    AMBIGUOUS = "AMBIGUOUS"
    IRRELEVANT = "IRRELEVANT"


@dataclass
class EvidenceCandidate:
    """
    Canonical evidence object representing an extracted declaration candidate.
    
    Guarantees strict provenance tracking, layout relation, semantic section scoping,
    and lifecycle validation state before field assignment.
    """
    raw_text: str
    normalized_text: Optional[str] = None
    source_image: str = ""
    source_type: str = SourceType.OCR.value
    ocr_confidence: float = 0.0
    bounding_box: Optional[Dict[str, Any]] = None
    line_id: Optional[int] = None
    region_id: Optional[int] = None
    semantic_section: str = "UNKNOWN"
    anchor_label: Optional[str] = None
    anchor_relation: Optional[str] = None
    candidate_field: Optional[str] = None
    relevance_score: float = 0.0
    validation_state: str = ValidationState.UNASSESSED.value
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert candidate to dictionary matching the required canonical schema."""
        d = asdict(self)
        if isinstance(d.get("source_type"), Enum):
            d["source_type"] = d["source_type"].value
        if isinstance(d.get("anchor_relation"), Enum):
            d["anchor_relation"] = d["anchor_relation"].value
        if isinstance(d.get("validation_state"), Enum):
            d["validation_state"] = d["validation_state"].value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceCandidate":
        """Reconstruct candidate from dictionary."""
        known_fields = {
            "raw_text", "normalized_text", "source_image", "source_type",
            "ocr_confidence", "bounding_box", "line_id", "region_id",
            "semantic_section", "anchor_label", "anchor_relation",
            "candidate_field", "relevance_score", "validation_state",
            "metadata"
        }
        filtered = {k: v for k, v in data.items() if k in known_fields}
        if "metadata" not in filtered:
            filtered["metadata"] = {k: v for k, v in data.items() if k not in known_fields}
        return cls(**filtered)


@dataclass
class FieldScopingRule:
    """Field-specific semantic scoping specification."""
    field_name: str
    positive_indicators: List[str]
    negative_indicators: List[str]
    expected_value_type: str  # TEXT, NUMBER, CURRENCY, DATE, UNIT_MEASUREMENT, IDENTIFIER, ADDRESS
    allowed_sections: Set[str]
    disallowed_sections: Set[str]
    proximity_expectations: str  # SAME_LINE_PREFERRED, MULTILINE_CONTINUITY, TITLE_TOP, ANY


# Semantic Section Definitions
SECTION_FRONT_PRODUCT = "FRONT_PRODUCT"
SECTION_IDENTITY = "IDENTITY"
SECTION_QUANTITY = "QUANTITY"
SECTION_DECLARED_QUANTITY = "DECLARED_QUANTITY"
SECTION_PRICING = "PRICING"
SECTION_MRP = "MRP"
SECTION_MANUFACTURER = "MANUFACTURER"
SECTION_PACKER = "PACKER"
SECTION_ADDRESS = "ADDRESS"
SECTION_DATE = "DATE"
SECTION_BATCH = "BATCH"
SECTION_NUTRITION = "NUTRITION"
SECTION_SERVING_SIZE = "SERVING_SIZE"
SECTION_INGREDIENTS = "INGREDIENTS"
SECTION_CONSUMER_CARE = "CONSUMER_CARE"
SECTION_FOOD_LABELING = "FOOD_LABELING"
SECTION_COSMETIC_LABELING = "COSMETIC_LABELING"
SECTION_INSTRUCTIONS = "INSTRUCTIONS"
SECTION_STORAGE = "STORAGE"
SECTION_MARKETING = "MARKETING"
SECTION_BARCODE = "BARCODE"
SECTION_OTHER = "OTHER"
SECTION_UNKNOWN = "UNKNOWN"

ALL_SEMANTIC_SECTIONS = {
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
}

# Universal Field Scoping Registry across 23+ Canonical Fields
FIELD_SCOPING_REGISTRY: Dict[str, FieldScopingRule] = {
    "PRODUCT_NAME": FieldScopingRule(
        field_name="PRODUCT_NAME",
        positive_indicators=["product", "name", "brand"],
        negative_indicators=["manufactured by", "packed by", "ingredients", "nutrition", "carbohydrate", "mrp"],
        expected_value_type="TEXT",
        allowed_sections={SECTION_FRONT_PRODUCT, SECTION_IDENTITY, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_INGREDIENTS, SECTION_ADDRESS, SECTION_CONSUMER_CARE},
        proximity_expectations="TITLE_TOP",
    ),
    "BRAND": FieldScopingRule(
        field_name="BRAND",
        positive_indicators=["brand", "trademark", "tm", "®"],
        negative_indicators=["manufactured by", "pvt ltd", "ingredients", "nutrition", "store in"],
        expected_value_type="TEXT",
        allowed_sections={SECTION_FRONT_PRODUCT, SECTION_IDENTITY, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_INGREDIENTS, SECTION_ADDRESS, SECTION_CONSUMER_CARE},
        proximity_expectations="TITLE_TOP",
    ),
    "GENERIC_NAME": FieldScopingRule(
        field_name="GENERIC_NAME",
        positive_indicators=["generic name", "commodity", "name of commodity", "common name"],
        negative_indicators=["delicious", "premium", "crispy", "natural", "manufactured"],
        expected_value_type="TEXT",
        allowed_sections={SECTION_FRONT_PRODUCT, SECTION_IDENTITY, SECTION_DECLARED_QUANTITY, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_INGREDIENTS, SECTION_ADDRESS},
        proximity_expectations="SAME_LINE_PREFERRED",
    ),
    "PRODUCT_TYPE": FieldScopingRule(
        field_name="PRODUCT_TYPE",
        positive_indicators=["type", "category", "class"],
        negative_indicators=["tasty", "fresh", "offer", "discount"],
        expected_value_type="TEXT",
        allowed_sections={SECTION_FRONT_PRODUCT, SECTION_IDENTITY, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_ADDRESS},
        proximity_expectations="ANY",
    ),
    "DECLARED_NET_QUANTITY": FieldScopingRule(
        field_name="DECLARED_NET_QUANTITY",
        positive_indicators=["net wt", "net weight", "net qty", "net quantity", "net content", "net vol", "net volume"],
        negative_indicators=["per 100g", "per serve", "serving size", "energy", "protein", "carbohydrate", "fat", "sugar"],
        expected_value_type="UNIT_MEASUREMENT",
        allowed_sections={SECTION_DECLARED_QUANTITY, SECTION_QUANTITY, SECTION_FRONT_PRODUCT, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_INGREDIENTS},
        proximity_expectations="SAME_LINE_PREFERRED",
    ),
    "MRP": FieldScopingRule(
        field_name="MRP",
        positive_indicators=["mrp", "maximum retail price", "incl. of all taxes", "inclusive of all taxes", "rs.", "₹", "inr"],
        negative_indicators=["serving", "kcal", "calories", "grams", "phone", "pincode"],
        expected_value_type="CURRENCY",
        allowed_sections={SECTION_MRP, SECTION_PRICING, SECTION_FRONT_PRODUCT, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_INGREDIENTS, SECTION_CONSUMER_CARE},
        proximity_expectations="SAME_LINE_PREFERRED",
    ),
    "MANUFACTURER_NAME": FieldScopingRule(
        field_name="MANUFACTURER_NAME",
        positive_indicators=["manufactured by", "mfg by", "mfd by", "made by", "producer"],
        negative_indicators=["packed by", "marketed by", "imported by", "customer care", "call us", "toll free"],
        expected_value_type="TEXT",
        allowed_sections={SECTION_MANUFACTURER, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_MRP, SECTION_DECLARED_QUANTITY},
        proximity_expectations="SAME_LINE_PREFERRED",
    ),
    "MANUFACTURER_ADDRESS": FieldScopingRule(
        field_name="MANUFACTURER_ADDRESS",
        positive_indicators=["at:", "works:", "factory:", "plot", "survey", "road", "street", "dist", "state", "pin", "india"],
        negative_indicators=["mrp", "net wt", "best before", "batch no", "call us at", "email:", "toll free"],
        expected_value_type="ADDRESS",
        allowed_sections={SECTION_MANUFACTURER, SECTION_ADDRESS, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_MRP, SECTION_DECLARED_QUANTITY, SECTION_CONSUMER_CARE},
        proximity_expectations="MULTILINE_CONTINUITY",
    ),
    "PACKER_NAME": FieldScopingRule(
        field_name="PACKER_NAME",
        positive_indicators=["packed by", "pkd by", "pkg by", "packer"],
        negative_indicators=["manufactured by", "imported by", "consumer care", "helpline"],
        expected_value_type="TEXT",
        allowed_sections={SECTION_PACKER, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_MRP},
        proximity_expectations="SAME_LINE_PREFERRED",
    ),
    "PACKER_ADDRESS": FieldScopingRule(
        field_name="PACKER_ADDRESS",
        positive_indicators=["packed at", "pkd at", "plot", "survey", "sector", "estate", "pin", "india"],
        negative_indicators=["mrp", "batch", "expiry", "consumer care", "call us"],
        expected_value_type="ADDRESS",
        allowed_sections={SECTION_PACKER, SECTION_ADDRESS, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_MRP, SECTION_CONSUMER_CARE},
        proximity_expectations="MULTILINE_CONTINUITY",
    ),
    "IMPORTER_NAME": FieldScopingRule(
        field_name="IMPORTER_NAME",
        positive_indicators=["imported by", "importer", "import by"],
        negative_indicators=["manufactured by", "packed by", "domestic"],
        expected_value_type="TEXT",
        allowed_sections={SECTION_MANUFACTURER, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE},
        proximity_expectations="SAME_LINE_PREFERRED",
    ),
    "IMPORTER_ADDRESS": FieldScopingRule(
        field_name="IMPORTER_ADDRESS",
        positive_indicators=["importer address", "imported by", "plot", "road", "city", "pin"],
        negative_indicators=["mrp", "batch", "net qty"],
        expected_value_type="ADDRESS",
        allowed_sections={SECTION_MANUFACTURER, SECTION_ADDRESS, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_MRP},
        proximity_expectations="MULTILINE_CONTINUITY",
    ),
    "MANUFACTURE_DATE": FieldScopingRule(
        field_name="MANUFACTURE_DATE",
        positive_indicators=["mfg date", "mfd date", "date of manufacture", "mfg.", "mfd.", "mfd:", "mfg:"],
        negative_indicators=["best before", "use by", "expiry", "exp:", "use-before"],
        expected_value_type="DATE",
        allowed_sections={SECTION_DATE, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_INGREDIENTS},
        proximity_expectations="SAME_LINE_PREFERRED",
    ),
    "PACKING_DATE": FieldScopingRule(
        field_name="PACKING_DATE",
        positive_indicators=["pkd date", "pkg date", "packed on", "date of packing", "pkd.", "pkd:"],
        negative_indicators=["best before", "expiry", "exp:", "use by"],
        expected_value_type="DATE",
        allowed_sections={SECTION_DATE, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_INGREDIENTS},
        proximity_expectations="SAME_LINE_PREFERRED",
    ),
    "BEST_BEFORE_DATE": FieldScopingRule(
        field_name="BEST_BEFORE_DATE",
        positive_indicators=["best before", "best by", "consume before"],
        negative_indicators=["mfg date", "mfd date", "pkd date", "date of manufacture"],
        expected_value_type="DATE",
        allowed_sections={SECTION_DATE, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE},
        proximity_expectations="SAME_LINE_PREFERRED",
    ),
    "USE_BY_DATE": FieldScopingRule(
        field_name="USE_BY_DATE",
        positive_indicators=["use by", "use before", "use-before", "consume within", "valid till"],
        negative_indicators=["mfg date", "date of manufacture", "pkd date"],
        expected_value_type="DATE",
        allowed_sections={SECTION_DATE, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE},
        proximity_expectations="SAME_LINE_PREFERRED",
    ),
    "EXPIRY_DATE": FieldScopingRule(
        field_name="EXPIRY_DATE",
        positive_indicators=["expiry date", "exp date", "exp.", "exp:", "expiration date"],
        negative_indicators=["mfg date", "pkd date", "manufactured on"],
        expected_value_type="DATE",
        allowed_sections={SECTION_DATE, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE},
        proximity_expectations="SAME_LINE_PREFERRED",
    ),
    "BATCH_NUMBER": FieldScopingRule(
        field_name="BATCH_NUMBER",
        positive_indicators=["batch no", "b.no", "batch number", "lot no", "lot number", "lot:", "batch:"],
        negative_indicators=["fssai", "lic no", "mrp", "phone", "pin", "net wt"],
        expected_value_type="IDENTIFIER",
        allowed_sections={SECTION_BATCH, SECTION_DATE, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_INGREDIENTS},
        proximity_expectations="SAME_LINE_PREFERRED",
    ),
    "CONSUMER_CARE": FieldScopingRule(
        field_name="CONSUMER_CARE",
        positive_indicators=["consumer care", "customer care", "helpline", "toll free", "feedback", "call us", "email:"],
        negative_indicators=["mrp", "net wt", "batch no", "best before"],
        expected_value_type="TEXT",
        allowed_sections={SECTION_CONSUMER_CARE, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_SERVING_SIZE, SECTION_INGREDIENTS},
        proximity_expectations="MULTILINE_CONTINUITY",
    ),
    "FSSAI_LICENSE": FieldScopingRule(
        field_name="FSSAI_LICENSE",
        positive_indicators=["fssai", "lic no", "license no", "lic. no", "licen"],
        negative_indicators=["batch", "mrp", "toll free", "pincode", "phone"],
        expected_value_type="IDENTIFIER",
        allowed_sections={SECTION_FOOD_LABELING, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_COSMETIC_LABELING},
        proximity_expectations="SAME_LINE_PREFERRED",
    ),
    "VEG_NONVEG_SYMBOL": FieldScopingRule(
        field_name="VEG_NONVEG_SYMBOL",
        positive_indicators=["vegetarian", "non-vegetarian", "veg", "green dot", "brown dot"],
        negative_indicators=["cosmetic", "detergent", "cleaner"],
        expected_value_type="IDENTIFIER",
        allowed_sections={SECTION_FOOD_LABELING, SECTION_FRONT_PRODUCT, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_COSMETIC_LABELING},
        proximity_expectations="ANY",
    ),
    "INGREDIENTS": FieldScopingRule(
        field_name="INGREDIENTS",
        positive_indicators=["ingredients", "composition", "contains", "ingredient list"],
        negative_indicators=["nutrition facts", "mrp", "manufactured by", "batch no"],
        expected_value_type="TEXT",
        allowed_sections={SECTION_INGREDIENTS, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_NUTRITION, SECTION_MRP, SECTION_ADDRESS},
        proximity_expectations="MULTILINE_CONTINUITY",
    ),
    "NUTRITIONAL_INFO": FieldScopingRule(
        field_name="NUTRITIONAL_INFO",
        positive_indicators=["nutritional information", "nutrition facts", "per 100g", "approx value", "energy", "carbohydrate"],
        negative_indicators=["net wt", "manufactured by", "batch no", "mrp"],
        expected_value_type="TEXT",
        allowed_sections={SECTION_NUTRITION, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_ADDRESS, SECTION_CONSUMER_CARE},
        proximity_expectations="MULTILINE_CONTINUITY",
    ),
    "SERVING_SIZE": FieldScopingRule(
        field_name="SERVING_SIZE",
        positive_indicators=["serving size", "serve size", "per serve", "servings per pack"],
        negative_indicators=["net wt", "net weight", "declared quantity"],
        expected_value_type="UNIT_MEASUREMENT",
        allowed_sections={SECTION_SERVING_SIZE, SECTION_NUTRITION, SECTION_OTHER, SECTION_UNKNOWN},
        disallowed_sections={SECTION_DECLARED_QUANTITY, SECTION_ADDRESS},
        proximity_expectations="SAME_LINE_PREFERRED",
    ),
}
