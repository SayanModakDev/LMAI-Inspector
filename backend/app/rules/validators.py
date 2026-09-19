"""
Deterministic Validation Layer for Rule Matrix.

Implements a validator-dispatch architecture where each rule's validation_method
is executed deterministically rather than merely checking field presence.
"""

from dataclasses import dataclass, field
import logging
import math
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from app.core.ontology import (
    QuantityType,
    STRICT_EMAIL_RE,
    assess_address_structure,
    extract_contextual_emails,
    extract_quantity_value_unit,
    normalize_contextual_email,
    normalize_unit,
)
from app.extraction.cleaner import is_artifact_token
from app.extraction.evidence_model import EvidenceAvailabilityState

logger = logging.getLogger(__name__)

# Minimum OCR confidence threshold to consider evidence verifiable
MIN_OCR_CONFIDENCE = 0.6

# ---------------------------------------------------------------------------
# Cross-field contamination detection (Requirement 6 — Field-level validation hardening)
# Prevents MRP values, date strings, barcode numbers, and nutritional serving
# values from being treated as DECLARED_NET_QUANTITY or other declaration fields.
# ---------------------------------------------------------------------------

# Pattern: bare currency / MRP marker in a quantity field
_MRP_CONTAMINATION_RE = re.compile(
    r'(?:^|\s)(?:₹|rs\.?|inr|mrp|maximum\s*retail\s*price)\s*[\d]',
    re.IGNORECASE,
)
# Pattern: standalone currency amount with no quantity unit
_CURRENCY_ONLY_RE = re.compile(
    r'^(?:₹|rs\.?|inr)\s*[\d,]+(?:\.\d{1,2})?$',
    re.IGNORECASE,
)
# Pattern: date-like strings (MM/YYYY, DD/MM/YYYY, MonYYYY, etc.)
_DATE_CONTAMINATION_RE = re.compile(
    r'(?:'
    r'\b\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}\b'        # DD/MM/YYYY
    r'|\b\d{1,2}[\/\-\.]\d{4}\b'                          # MM/YYYY
    r'|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}\b'  # MonYYYY
    r'|\b\d{4}[\/\-]\d{1,2}\b'                            # YYYY/MM
    r')',
    re.IGNORECASE,
)
# Pattern: barcode / EAN / UPC — 8–14 consecutive digits with no alphabetic unit
_BARCODE_CONTAMINATION_RE = re.compile(r'^\d{8,14}$')

# Nutritional serving markers that must NOT bleed into DECLARED_NET_QUANTITY
_NUTRITION_SERVING_MARKERS = frozenset([
    'per 100g', 'per 100ml', 'per serve', 'per serving', 'serving size',
    'servings per', 'energy', 'protein', 'carbohydrate', 'fat', 'kcal',
    'calories', 'sodium', 'fibre', 'fiber', 'sugar', 'cholesterol',
])


def _is_mrp_contamination(value: str, parameter: str) -> bool:
    """Return True if a value looks like an MRP / price value landing in a non-MRP field."""
    if parameter in ('MRP', 'UNIT_SALE_PRICE'):
        return False  # currency values are expected here
    stripped = value.strip()
    return bool(_MRP_CONTAMINATION_RE.search(stripped) or _CURRENCY_ONLY_RE.match(stripped))


def _is_date_contamination(value: str, parameter: str) -> bool:
    """Return True if a date string has landed in a quantity or text identity field."""
    if parameter in (
        'MANUFACTURE_DATE', 'MONTH_YEAR_MANUFACTURE', 'PACKING_DATE',
        'BEST_BEFORE_USE_BY', 'USE_BEFORE_DATE', 'EXPIRY_DATE',
        'BEST_BEFORE', 'USE_BY_DATE', 'IMPORT_DATE',
    ):
        return False  # dates are expected here
    stripped = value.strip()
    # Only flag pure-date strings (short enough not to be a full sentence)
    if len(stripped) > 20:
        return False
    return bool(_DATE_CONTAMINATION_RE.search(stripped))


def _is_barcode_contamination(value: str, parameter: str) -> bool:
    """Return True if a barcode number (8-14 digits) has contaminated a declaration field."""
    if parameter in ('BARCODE', 'EAN', 'UPC', 'QR_CODE', 'BATCH_NUMBER', 'FSSAI_LICENSE'):
        return False  # identifiers expected here
    return bool(_BARCODE_CONTAMINATION_RE.match(value.strip()))


def _has_nutrition_marker(value: str) -> bool:
    """Return True if the value contains nutritional-serving context markers."""
    lowered = value.lower()
    return any(marker in lowered for marker in _NUTRITION_SERVING_MARKERS)

# Units recognized under Legal Metrology (Packaged Commodities) Rules
LEGAL_WEIGHT_UNITS = {
    'g': 'g', 'gm': 'g', 'gms': 'g', 'gram': 'g', 'grams': 'g',
    'kg': 'kg', 'kgs': 'kg', 'kilogram': 'kg', 'kilograms': 'kg',
    'mg': 'mg', 'milligram': 'mg', 'milligrams': 'mg',
    'oz': 'oz', 'lb': 'lb', 'lbs': 'lb',
}

LEGAL_VOLUME_UNITS = {
    'ml': 'ml', 'millilitre': 'ml', 'millilitres': 'ml', 'milliliter': 'ml', 'milliliters': 'ml',
    'l': 'L', 'ltr': 'L', 'litre': 'L', 'litres': 'L', 'liter': 'L', 'liters': 'L',
    'cl': 'cl',
}

LEGAL_COUNT_UNITS = {
    'pcs': 'pieces', 'pieces': 'pieces', 'piece': 'pieces', 'pc': 'pieces',
    'tablets': 'tablets', 'tablet': 'tablets',
    'capsules': 'capsules', 'capsule': 'capsules',
    'units': 'units', 'unit': 'units',
    'numbers': 'numbers', 'number': 'numbers', 'n': 'numbers', 'u': 'units',
}

LEGAL_LENGTH_AREA_UNITS = {
    'm': 'm', 'meter': 'm', 'meters': 'm', 'metre': 'm', 'metres': 'm',
    'cm': 'cm', 'centimeter': 'cm', 'centimeters': 'cm',
    'mm': 'mm', 'millimeter': 'mm', 'millimeters': 'mm',
    'sq m': 'sq m', 'sq cm': 'sq cm', 'sq mm': 'sq mm',
}

ALL_LEGAL_UNITS = {
    **LEGAL_WEIGHT_UNITS,
    **LEGAL_VOLUME_UNITS,
    **LEGAL_COUNT_UNITS,
    **LEGAL_LENGTH_AREA_UNITS,
}

MONTH_NAMES = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


@dataclass
class ValidationResult:
    """Structured result returned by every validator."""

    status: str  # PASS, FAIL, NOT_VERIFIABLE, NOT_APPLICABLE
    binary: Optional[int]  # 1 (pass), 0 (fail / not verifiable), None (not applicable)
    reason: str
    normalized_value: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None

    # Structured quantity & unit pair attributes
    raw_value: Optional[str] = None
    value: Optional[Any] = None
    unit: Optional[str] = None
    quantity_type: Optional[str] = None
    quantity_present: Optional[bool] = None
    unit_present: Optional[bool] = None
    quantity_unit_valid: Optional[bool] = None

    # Multipack semantic attributes
    is_multipack: Optional[bool] = None
    pack_count: Optional[int] = None
    unit_quantity: Optional[Union[int, float]] = None
    unit_net_quantity: Optional[Union[int, float]] = None
    declared_expression: Optional[str] = None
    derived_total_quantity: Optional[Union[int, float]] = None
    evidence_state: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert validation result to dictionary representation."""
        data: Dict[str, Any] = {
            "status": self.status,
            "binary": self.binary,
            "reason": self.reason,
        }
        if self.evidence_state is not None:
            data["evidence_state"] = self.evidence_state
        if self.normalized_value is not None:
            data["normalized_value"] = self.normalized_value
        if self.evidence is not None:
            data["evidence"] = self.evidence
        if self.raw_value is not None:
            data["raw_value"] = self.raw_value
        if self.value is not None:
            data["value"] = self.value
        if self.unit is not None:
            data["unit"] = self.unit
        if self.quantity_type is not None:
            data["quantity_type"] = self.quantity_type
        if self.quantity_present is not None:
            data["quantity_present"] = self.quantity_present
        if self.unit_present is not None:
            data["unit_present"] = self.unit_present
        if self.quantity_unit_valid is not None:
            data["quantity_unit_valid"] = self.quantity_unit_valid
        if self.is_multipack is not None:
            data["is_multipack"] = self.is_multipack
        if self.pack_count is not None:
            data["pack_count"] = self.pack_count
        if self.unit_quantity is not None:
            data["unit_quantity"] = self.unit_quantity
        if self.unit_net_quantity is not None:
            data["unit_net_quantity"] = self.unit_net_quantity
        if self.declared_expression is not None:
            data["declared_expression"] = self.declared_expression
        if self.derived_total_quantity is not None:
            data["derived_total_quantity"] = self.derived_total_quantity
        return data


# Type signature for validator functions
ValidatorFunc = Callable[
    [Optional[Dict[str, Any]], Dict[str, Any], Dict[str, Any]],
    ValidationResult,
]

# Registry mapping validation_method string to validator function
VALIDATOR_REGISTRY: Dict[str, ValidatorFunc] = {}


def register_validator(method_name: str) -> Callable[[ValidatorFunc], ValidatorFunc]:
    """Decorator to register a validator function in the registry."""

    def decorator(func: ValidatorFunc) -> ValidatorFunc:
        VALIDATOR_REGISTRY[method_name] = func
        return func

    return decorator


def _check_preconditions(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
) -> Optional[ValidationResult]:
    """Check common preconditions: missing evidence, clearly_invalid flag, confidence, and conflicting evidence.

    Returns a ValidationResult if a terminal state is reached, else None to continue validation.
    """
    parameter = rule.get("parameter", "UNKNOWN")
    required = rule.get("required", True)

    # Conflicting evidence across views/sources cannot be treated as a pass.
    if evidence and (
        evidence.get("status") == "CONFLICTING_EVIDENCE"
        or evidence.get("has_conflict") is True
    ):
        conflicting_vals = evidence.get("values") or [evidence.get("value")]
        vals_str = ", ".join(str(v) for v in conflicting_vals)
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=(
                f"Conflicting evidence detected across package views for '{parameter}': "
                f"[{vals_str}]. Declaration not detected reliably from package images."
            ),
            normalized_value=str(evidence.get("value", "")),
            evidence=evidence,
            evidence_state=evidence.get("evidence_state", EvidenceAvailabilityState.EVIDENCE_CONFLICTING.value),
        )

    # 0b. Ambiguous / OCR variation evidence is not detected reliably
    if evidence and evidence.get("status") == "REVIEW":
        review_reason = evidence.get("reason") or (
            f"Evidence detected for '{parameter}' is ambiguous and requires review. "
            "Declaration not detected reliably from package images."
        )
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=review_reason,
            normalized_value=str(evidence.get("value", "")),
            evidence=evidence,
            evidence_state=evidence.get("evidence_state", EvidenceAvailabilityState.EVIDENCE_DETECTED_UNASSOCIATED.value),
        )

    # 1. Missing evidence or empty value
    if not evidence or evidence.get("value") is None or not str(evidence.get("value", "")).strip():
        if required:
            return ValidationResult(
                status="NOT_VERIFIABLE",
                binary=0,
                reason=f"Required declaration '{parameter}' was not detected in the available OCR evidence.",
                evidence=None,
                evidence_state=EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value,
            )
        return ValidationResult(
            status="NOT_APPLICABLE",
            binary=None,
            reason=f"Optional declaration '{parameter}' not identified and not required for this context.",
            evidence=None,
            evidence_state=EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value,
        )

    # 2. Clearly invalid flag explicitly set on evidence
    if evidence.get("clearly_invalid"):
        failure_reason = evidence.get("failure_reason") or (
            f"Available evidence indicates this requirement is not satisfied: {parameter}."
        )
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=failure_reason,
            normalized_value=str(evidence.get("value", "")),
            evidence=evidence,
            evidence_state=evidence.get("evidence_state", EvidenceAvailabilityState.EVIDENCE_VERIFIED.value),
        )

    # 3. Weak OCR confidence
    confidence = evidence.get("confidence")
    if confidence is not None and float(confidence) < MIN_OCR_CONFIDENCE:
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=(
                f"Evidence detected for '{parameter}' has low OCR confidence ({float(confidence):.2f}) "
                f"below threshold {MIN_OCR_CONFIDENCE}; cannot confirm compliance legally."
            ),
            normalized_value=str(evidence.get("value", "")),
            evidence=evidence,
            evidence_state=EvidenceAvailabilityState.EVIDENCE_LOW_CONFIDENCE.value,
        )

    # 4. Cross-field contamination guards — prevent semantic drift
    # These run after confidence checks so that low-confidence items still route to NOT_VERIFIABLE
    # without double-flagging.
    raw_value_str = str(evidence.get("value") or "").strip()
    if raw_value_str:
        # 4a. MRP/currency value in a non-MRP field (e.g., DECLARED_NET_QUANTITY = "₹45")
        if parameter == "DECLARED_NET_QUANTITY" and _is_mrp_contamination(raw_value_str, parameter):
            return ValidationResult(
                status="NOT_VERIFIABLE",
                binary=0,
                reason=(
                    f"Suspected MRP/price value '{raw_value_str}' detected as declared net quantity. "
                    "This field requires a quantity with a legal unit (g, kg, ml, L, pcs). "
                    "Declaration not detected reliably from package images."
                ),
                normalized_value=raw_value_str,
                evidence=evidence,
                evidence_state=EvidenceAvailabilityState.EVIDENCE_DETECTED_UNASSOCIATED.value,
            )

        # 4b. Date string in DECLARED_NET_QUANTITY (e.g., "01/2025" mistaken for quantity)
        if parameter == "DECLARED_NET_QUANTITY" and _is_date_contamination(raw_value_str, parameter):
            return ValidationResult(
                status="NOT_VERIFIABLE",
                binary=0,
                reason=(
                    f"A date-like value '{raw_value_str}' was detected in the declared net quantity field. "
                    "A date cannot represent a net quantity. Declaration not detected reliably from package images."
                ),
                normalized_value=raw_value_str,
                evidence=evidence,
                evidence_state=EvidenceAvailabilityState.EVIDENCE_DETECTED_UNASSOCIATED.value,
            )

        # 4c. Barcode/EAN number contaminating a declaration text field
        if parameter not in ("BARCODE", "EAN", "UPC", "QR_CODE", "BATCH_NUMBER", "FSSAI_LICENSE") \
                and _is_barcode_contamination(raw_value_str, parameter):
            return ValidationResult(
                status="NOT_VERIFIABLE",
                binary=0,
                reason=(
                    f"A numeric code '{raw_value_str}' that resembles a barcode or identifier was detected "
                    f"as '{parameter}'. Declaration values must not be bare numeric codes. Declaration not detected reliably from package images."
                ),
                normalized_value=raw_value_str,
                evidence=evidence,
                evidence_state=EvidenceAvailabilityState.EVIDENCE_DETECTED_UNASSOCIATED.value,
            )

        # 4d. Nutritional/serving context value contaminating DECLARED_NET_QUANTITY
        if parameter == "DECLARED_NET_QUANTITY" and _has_nutrition_marker(raw_value_str):
            return ValidationResult(
                status="NOT_VERIFIABLE",
                binary=0,
                reason=(
                    f"Value '{raw_value_str}' appears to originate from a nutritional or serving-size "
                    "context, not a package net quantity declaration. Declaration not detected reliably from package images."
                ),
                normalized_value=raw_value_str,
                evidence=evidence,
                evidence_state=EvidenceAvailabilityState.EVIDENCE_DETECTED_UNASSOCIATED.value,
            )

    return None



@register_validator("TEXT_PRESENT")
def validate_text_present(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate that meaningful, legible textual content is declared."""
    pre = _check_preconditions(evidence, rule)
    if pre:
        return pre

    parameter = rule.get("parameter", "UNKNOWN")
    raw_val = str(evidence.get("value", "")).strip()  # type: ignore[union-attr]

    # Reject placeholder or meaningless content
    cleaned = re.sub(r'[^A-Za-z0-9]', '', raw_val)
    if len(cleaned) < 2 or raw_val.lower() in {'n/a', 'na', 'null', 'none', 'unknown', 'nil', '-'}:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"Declaration '{parameter}' contains invalid or placeholder content: '{raw_val}'.",
            normalized_value=raw_val,
            evidence=evidence,
        )

    return ValidationResult(
        status="PASS",
        binary=1,
        reason=f"Detected in OCR evidence: {raw_val}",
        normalized_value=raw_val,
        evidence=evidence,
    )


@register_validator("VALUE_AND_UNIT_PRESENT")
@register_validator("QUANTITY_UNIT_PAIR")
def validate_value_and_unit_present(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate declared net quantity and unit pair.
    
    Verifies that the label declaration printed on the package contains both a
    positive numeric quantity and a recognized Legal Metrology unit of measure.
    Does NOT claim that image OCR measures actual physical weight.
    """
    parameter = rule.get("parameter", "DECLARED_NET_QUANTITY")
    required = rule.get("required", True)

    # 0. Conflicting evidence check
    if evidence and (
        evidence.get("status") == "CONFLICTING_EVIDENCE"
        or evidence.get("has_conflict") is True
    ):
        conflicting_vals = evidence.get("values") or [evidence.get("value")]
        vals_str = ", ".join(str(v) for v in conflicting_vals)
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=(
                f"Conflicting evidence detected across package views for '{parameter}': "
                f"[{vals_str}]. Declaration not detected reliably from package images."
            ),
            raw_value=str(evidence.get("value", "")),
            value=None,
            unit=None,
            quantity_present=evidence.get("quantity_present", False),
            unit_present=evidence.get("unit_present", False),
            quantity_unit_valid=False,
            evidence=evidence,
        )

    # 1. Missing evidence
    if not evidence or evidence.get("value") is None or not str(evidence.get("value", "")).strip():
        if required:
            return ValidationResult(
                status="NOT_VERIFIABLE",
                binary=0,
                reason=f"Required declaration '{parameter}' was not detected in OCR evidence.",
                raw_value=None,
                value=None,
                unit=None,
                quantity_present=False,
                unit_present=False,
                quantity_unit_valid=False,
                evidence=None,
            )
        return ValidationResult(
            status="NOT_APPLICABLE",
            binary=None,
            reason=f"Optional declaration '{parameter}' not identified and not required.",
            raw_value=None,
            value=None,
            unit=None,
            quantity_present=False,
            unit_present=False,
            quantity_unit_valid=False,
            evidence=None,
        )

    raw_val = str(evidence.get("raw_value") or evidence.get("value", "")).strip()

    # 2. Clearly invalid flag explicitly set
    if evidence.get("clearly_invalid"):
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=evidence.get("failure_reason") or f"Declared net quantity is invalid: '{raw_val}'.",
            normalized_value=raw_val,
            raw_value=raw_val,
            value=None,
            unit=None,
            quantity_present=evidence.get("quantity_present", False),
            unit_present=evidence.get("unit_present", False),
            quantity_unit_valid=False,
            evidence=evidence,
        )

    # 3. Weak OCR confidence
    confidence = evidence.get("confidence")
    if confidence is not None and float(confidence) < MIN_OCR_CONFIDENCE:
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=(
                f"Evidence detected for '{parameter}' has low OCR confidence ({float(confidence):.2f}) "
                f"below threshold {MIN_OCR_CONFIDENCE}; cannot confirm compliance legally."
            ),
            normalized_value=raw_val,
            raw_value=raw_val,
            value=None,
            unit=None,
            quantity_present=evidence.get("quantity_present", False),
            unit_present=evidence.get("unit_present", False),
            quantity_unit_valid=False,
            evidence=evidence,
        )

    # 4. Check for multipack declaration
    is_multi = bool(evidence.get("is_multipack"))
    if not is_multi and raw_val:
        from app.extraction.declaration_extractor import parse_quantity_expression
        parsed_test = parse_quantity_expression(raw_val)
        if parsed_test and parsed_test.get("is_multipack"):
            is_multi = True
            evidence["is_multipack"] = True
            evidence.setdefault("pack_count", parsed_test["pack_count"])
            evidence.setdefault("unit_net_quantity", parsed_test["unit_net_quantity"])
            evidence.setdefault("unit", parsed_test["unit"])
            evidence.setdefault("declared_expression", parsed_test["declared_expression"])
            evidence.setdefault("derived_total_quantity", parsed_test["derived_total_quantity"])

    if is_multi:
        pack_cnt = evidence.get("pack_count")
        unit_qty = evidence.get("unit_net_quantity") or evidence.get("unit_quantity") or evidence.get("quantity_value")
        norm_u = evidence.get("unit") or evidence.get("quantity_unit") or evidence.get("raw_unit")
        decl_expr = evidence.get("declared_expression") or evidence.get("value") or raw_val
        derived_total = evidence.get("derived_total_quantity")

        # Validate count
        count_valid = False
        if pack_cnt is not None:
            try:
                c_int = int(pack_cnt)
                count_valid = c_int > 0
            except (ValueError, TypeError):
                count_valid = False

        # Validate unit quantity
        unit_qty_valid = False
        num_unit_qty = None
        if unit_qty is not None:
            try:
                num_unit_qty = float(unit_qty)
                unit_qty_valid = num_unit_qty > 0
                if num_unit_qty.is_integer():
                    num_unit_qty = int(num_unit_qty)
            except (ValueError, TypeError):
                unit_qty_valid = False

        # Validate unit
        norm_unit_str: Optional[str] = None
        if norm_u:
            lowered_u = str(norm_u).lower().strip()
            if lowered_u in {'g', 'gm', 'gms', 'gram', 'grams'}:
                norm_unit_str = 'g'
            elif lowered_u in {'kg', 'kgs', 'kilogram', 'kilograms'}:
                norm_unit_str = 'kg'
            elif lowered_u in {'ml', 'millilitre', 'millilitres', 'milliliter', 'milliliters'}:
                norm_unit_str = 'ml'
            elif lowered_u in {'l', 'ltr', 'litre', 'litres', 'liter', 'liters'}:
                norm_unit_str = 'L'
            else:
                norm_unit_str = ALL_LEGAL_UNITS.get(lowered_u, lowered_u)

        is_legal = bool(norm_unit_str and (norm_unit_str in ALL_LEGAL_UNITS.values() or norm_unit_str.lower() in ALL_LEGAL_UNITS.keys()))

        if not count_valid and not unit_qty_valid and not is_legal:
            return ValidationResult(
                status="NOT_VERIFIABLE",
                binary=0,
                reason=f"Multipack expression detected but components cannot be verified: '{raw_val}'.",
                normalized_value=raw_val,
                raw_value=raw_val,
                value=None,
                unit=None,
                is_multipack=True,
                quantity_present=False,
                unit_present=False,
                quantity_unit_valid=False,
                evidence=evidence,
            )

        if not count_valid:
            return ValidationResult(
                status="FAIL",
                binary=0,
                reason=f"Multipack declaration is missing a valid positive pack count: '{raw_val}'.",
                normalized_value=decl_expr,
                raw_value=raw_val,
                value=decl_expr,
                unit=norm_unit_str,
                is_multipack=True,
                pack_count=pack_cnt,
                unit_quantity=num_unit_qty,
                quantity_present=unit_qty_valid,
                unit_present=bool(norm_unit_str),
                quantity_unit_valid=False,
                evidence=evidence,
            )

        if not unit_qty_valid:
            return ValidationResult(
                status="FAIL",
                binary=0,
                reason=f"Multipack declaration is missing a valid unit net quantity: '{raw_val}'.",
                normalized_value=decl_expr,
                raw_value=raw_val,
                value=decl_expr,
                unit=norm_unit_str,
                is_multipack=True,
                pack_count=pack_cnt,
                unit_quantity=None,
                quantity_present=False,
                unit_present=bool(norm_unit_str),
                quantity_unit_valid=False,
                evidence=evidence,
            )

        if not is_legal:
            return ValidationResult(
                status="FAIL",
                binary=0,
                reason=f"Multipack unit '{norm_u}' is not a recognized legal unit under Legal Metrology Rules.",
                normalized_value=decl_expr,
                raw_value=raw_val,
                value=decl_expr,
                unit=norm_u,
                is_multipack=True,
                pack_count=pack_cnt,
                unit_quantity=num_unit_qty,
                quantity_present=True,
                unit_present=bool(norm_u),
                quantity_unit_valid=False,
                evidence=evidence,
            )

        # Valid multipack!
        return ValidationResult(
            status="PASS",
            binary=1,
            reason=f"Valid declared multipack quantity: {decl_expr}",
            normalized_value=decl_expr,
            raw_value=raw_val,
            value=decl_expr,
            unit=norm_unit_str,
            is_multipack=True,
            pack_count=pack_cnt,
            unit_quantity=num_unit_qty,
            unit_net_quantity=num_unit_qty,
            declared_expression=decl_expr,
            derived_total_quantity=derived_total,
            quantity_present=True,
            unit_present=True,
            quantity_unit_valid=True,
            evidence=evidence,
        )

    # 5. Extract or parse quantity value and unit token for single package
    qty_val = evidence.get("quantity_value")
    qty_unit = evidence.get("quantity_unit") or evidence.get("raw_unit")

    # If missing from structured evidence, parse candidate string
    if qty_val is None or qty_unit is None:
        num_match = re.search(r'([+-]?\d+(?:\.\d+)?)', raw_val)
        unit_match = re.search(
            r'\b(g|gm|gms|gram|grams|kg|kgs|kilogram|kilograms|mg|milligram|milligrams|ml|millilitre|millilitres|milliliter|milliliters|l|ltr|litre|litres|liter|liters|oz|lb|lbs|pc|pcs|piece|pieces|tablet|tablets|capsule|capsules)\b',
            raw_val,
            re.IGNORECASE,
        )
        if qty_val is None and num_match:
            qty_val = num_match.group(1)
        if qty_unit is None and unit_match:
            qty_unit = unit_match.group(1)

    # Check presence flags
    quantity_present = bool(qty_val is not None and str(qty_val).strip() != "")
    unit_present = bool(qty_unit is not None and str(qty_unit).strip() != "")

    # Normalize unit:
    # gm / g -> g
    # kg -> kg
    # ml / mL -> ml
    # l / L -> L
    normalized_unit: Optional[str] = None
    if unit_present:
        lowered_unit = str(qty_unit).lower().strip()
        if lowered_unit in {'g', 'gm', 'gms', 'gram', 'grams'}:
            normalized_unit = 'g'
        elif lowered_unit in {'kg', 'kgs', 'kilogram', 'kilograms'}:
            normalized_unit = 'kg'
        elif lowered_unit in {'ml', 'millilitre', 'millilitres', 'milliliter', 'milliliters'}:
            normalized_unit = 'ml'
        elif lowered_unit in {'l', 'ltr', 'litre', 'litres', 'liter', 'liters'}:
            normalized_unit = 'L'
        else:
            normalized_unit = ALL_LEGAL_UNITS.get(lowered_unit, lowered_unit)

    # Parse numeric quantity
    numeric_val: Optional[Any] = None
    if quantity_present:
        try:
            flt = float(qty_val)
            numeric_val = int(flt) if flt.is_integer() else flt
        except ValueError:
            quantity_present = False
            numeric_val = None

    is_legal_unit = bool(normalized_unit and (normalized_unit in ALL_LEGAL_UNITS.values() or normalized_unit.lower() in ALL_LEGAL_UNITS.keys()))

    # Infer or extract quantity type (MASS, VOLUME, COUNT, LENGTH_AREA)
    qty_type_str = evidence.get("quantity_type")
    if not qty_type_str and normalized_unit:
        lowered_u = normalized_unit.lower()
        if lowered_u in LEGAL_WEIGHT_UNITS or lowered_u in LEGAL_WEIGHT_UNITS.values():
            qty_type_str = "MASS"
        elif lowered_u in LEGAL_VOLUME_UNITS or lowered_u in LEGAL_VOLUME_UNITS.values():
            qty_type_str = "VOLUME"
        elif lowered_u in LEGAL_COUNT_UNITS or lowered_u in LEGAL_COUNT_UNITS.values():
            qty_type_str = "COUNT"
        elif lowered_u in LEGAL_LENGTH_AREA_UNITS or lowered_u in LEGAL_LENGTH_AREA_UNITS.values():
            qty_type_str = "LENGTH_AREA"

    # Determine compliance
    if not quantity_present and not unit_present:
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=f"Neither numeric quantity nor unit detected in: '{raw_val}'.",
            normalized_value=raw_val,
            raw_value=raw_val,
            value=None,
            unit=None,
            quantity_type=qty_type_str,
            quantity_present=False,
            unit_present=False,
            quantity_unit_valid=False,
            evidence=evidence,
        )

    if quantity_present and not unit_present:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"Declared quantity is missing a legal unit of measurement: '{raw_val}' (value={numeric_val}, unit=null).",
            normalized_value=str(numeric_val),
            raw_value=raw_val,
            value=numeric_val,
            unit=None,
            quantity_type=qty_type_str,
            quantity_present=True,
            unit_present=False,
            quantity_unit_valid=False,
            evidence=evidence,
        )

    if not quantity_present and unit_present:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"Unit of measurement is present ('{normalized_unit}') but numeric quantity is missing from declaration: '{raw_val}'.",
            normalized_value=normalized_unit,
            raw_value=raw_val,
            value=None,
            unit=normalized_unit,
            quantity_type=qty_type_str,
            quantity_present=False,
            unit_present=True,
            quantity_unit_valid=False,
            evidence=evidence,
        )

    # Both quantity_present and unit_present are True
    if numeric_val is not None and numeric_val <= 0:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"Invalid declared quantity: must be positive non-zero, found {numeric_val} {normalized_unit}.",
            normalized_value=f"{numeric_val} {normalized_unit}",
            raw_value=raw_val,
            value=numeric_val,
            unit=normalized_unit,
            quantity_type=qty_type_str,
            quantity_present=True,
            unit_present=True,
            quantity_unit_valid=False,
            evidence=evidence,
        )

    if not is_legal_unit:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"Net quantity unit '{qty_unit}' is not a recognized legal unit of weight, measure, or number under Legal Metrology Rules.",
            normalized_value=f"{numeric_val} {qty_unit}",
            raw_value=raw_val,
            value=numeric_val,
            unit=qty_unit,
            quantity_type=qty_type_str,
            quantity_present=True,
            unit_present=True,
            quantity_unit_valid=False,
            evidence=evidence,
        )

    # Count declarations must be whole numbers (integers)
    if qty_type_str == "COUNT" and numeric_val is not None:
        try:
            if not float(numeric_val).is_integer():
                return ValidationResult(
                    status="FAIL",
                    binary=0,
                    reason=f"Declared count quantity must be a whole number (integer), found: {numeric_val} {normalized_unit}.",
                    normalized_value=f"{numeric_val} {normalized_unit}",
                    raw_value=raw_val,
                    value=numeric_val,
                    unit=normalized_unit,
                    quantity_type=qty_type_str,
                    quantity_present=True,
                    unit_present=True,
                    quantity_unit_valid=False,
                    evidence=evidence,
                )
        except (ValueError, TypeError):
            pass

    # Valid quantity + unit declaration on package
    normalized_value = f"{numeric_val} {normalized_unit}"
    return ValidationResult(
        status="PASS",
        binary=1,
        reason="Valid declared quantity and unit",
        normalized_value=normalized_value,
        raw_value=raw_val,
        value=numeric_val,
        unit=normalized_unit,
        quantity_type=qty_type_str,
        quantity_present=True,
        unit_present=True,
        quantity_unit_valid=True,
        evidence=evidence,
    )


# Dedicated alias exports
validate_quantity_unit_pair = validate_value_and_unit_present
validate_declared_net_quantity = validate_value_and_unit_present


@register_validator("MRP_PRESENT")
def validate_mrp_present(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate Maximum Retail Price (MRP) declaration and positive numeric price."""
    pre = _check_preconditions(evidence, rule)
    if pre:
        return pre

    raw_val = str(evidence.get("raw_text") or evidence.get("raw_value") or evidence.get("value", "")).strip()

    # Check currency status and corrupted symbols
    currency_status = evidence.get("currency_status")
    if currency_status == "UNKNOWN" or "■" in raw_val or evidence.get("status") in ("REVIEW", "NOT_VERIFIABLE"):
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=evidence.get("reason") or f"MRP declaration contains corrupted or unverified currency symbol: '{raw_val}'. Declaration not detected reliably from package images.",
            normalized_value=raw_val,
            evidence=evidence,
        )

    if currency_status == "INFERRED":
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=evidence.get("reason") or f"Currency symbol is missing from MRP declaration: '{raw_val}'. Declaration not detected reliably from package images.",
            normalized_value=raw_val,
            evidence=evidence,
        )

    # Extract price amount using numeric search (avoids picking up periods from 'Rs.' or 'M.R.P.')
    price_match = re.search(r'([+-]?\d+(?:\.\d+)?)', raw_val)
    if not price_match:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"MRP declaration does not contain a numeric price amount: '{raw_val}'.",
            normalized_value=raw_val,
            evidence=evidence,
        )

    try:
        amount = float(price_match.group(1))
    except ValueError:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"MRP declaration contains invalid price format: '{raw_val}'.",
            normalized_value=raw_val,
            evidence=evidence,
        )

    if amount <= 0:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"MRP must be a positive retail price amount, found: ₹{amount:.2f}.",
            normalized_value=f"₹{amount:.2f}",
            evidence=evidence,
        )

    normalized_price = f"₹{amount:.2f}"
    return ValidationResult(
        status="PASS",
        binary=1,
        reason=f"Detected valid MRP declaration: {normalized_price}",
        normalized_value=normalized_price,
        evidence=evidence,
    )


@register_validator("MANUFACTURER_PRESENT")
def validate_manufacturer_present(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate a role-grounded manufacturer or packer name declaration."""
    pre = _check_preconditions(evidence, rule)
    if pre:
        return pre

    raw_val = str(evidence.get("value", "")).strip()  # type: ignore[union-attr]

    role = str(evidence.get("role") or evidence.get("entity_type") or "MANUFACTURER").upper()  # type: ignore[union-attr]
    if rule.get("parameter") == "MANUFACTURER_NAME" and role not in ("MANUFACTURER", "PACKER"):
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=(
                "A company name was detected, but it is not grounded as the manufacturer or "
                "packer required by this declaration."
            ),
            normalized_value=raw_val,
            evidence=evidence,
            evidence_state=EvidenceAvailabilityState.EVIDENCE_DETECTED_UNASSOCIATED.value,
        )

    # Strip prefix keywords to inspect actual entity name
    cleaned = re.sub(
        r'^(?:manufactured\s*(?:&|and|/)?\s*(?:marketed|packed)?\s*(?:by|at|for)|mfd\.?\s*by|mfg\.?\s*by|packed\s+(?:by|at)|marketed\s+by)[:\s-]*',
        '',
        raw_val,
        flags=re.IGNORECASE,
    ).strip()

    # Reject empty or trivial entity names (e.g. just label with no name)
    if len(re.sub(r'[^A-Za-z0-9]', '', cleaned)) < 3:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"Manufacturer declaration label is present but lacks a valid manufacturer/company name: '{raw_val}'.",
            normalized_value=raw_val,
            evidence=evidence,
        )

    return ValidationResult(
        status="PASS",
        binary=1,
        reason=f"Detected manufacturer declaration: {raw_val}",
        normalized_value=cleaned or raw_val,
        evidence=evidence,
    )


@register_validator("ADDRESS_PRESENT")
def validate_address_present(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate manufacturer or premises address declaration."""
    pre = _check_preconditions(evidence, rule)
    if pre:
        return pre

    raw_val = str(evidence.get("value", "")).strip()  # type: ignore[union-attr]

    # Obvious fragments can still be deterministically invalid.  Longer partial
    # OCR, however, is uncertainty rather than proof that the printed package is
    # legally incomplete.
    alphanumeric_count = len(re.sub(r'[^A-Za-z0-9]', '', raw_val))
    if alphanumeric_count < 5:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"Address declaration is incomplete or too short: '{raw_val}'.",
            normalized_value=raw_val,
            evidence=evidence,
        )

    role = str(evidence.get("role") or evidence.get("entity_type") or "MANUFACTURER").upper()  # type: ignore[union-attr]
    if rule.get("parameter") == "MANUFACTURER_ADDRESS" and role in ("MARKETER", "UNASSOCIATED"):
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=(
                "An address was detected, but it is not grounded as the manufacturer or packer "
                "address required by this declaration."
            ),
            normalized_value=raw_val,
            evidence=evidence,
            evidence_state=EvidenceAvailabilityState.EVIDENCE_DETECTED_UNASSOCIATED.value,
        )

    structure = assess_address_structure(raw_val)
    if not structure["sufficient"]:
        printed_complete = bool(
            evidence.get("printed_declaration_complete") is True  # type: ignore[union-attr]
            or evidence.get("ocr_coverage_complete") is True  # type: ignore[union-attr]
        )
        status = "FAIL" if printed_complete else "NOT_VERIFIABLE"
        return ValidationResult(
            status=status,
            binary=0,
            reason=(
                f"Detected address evidence is structurally incomplete: '{raw_val}'. "
                + (
                    "Complete image coverage confirms the printed declaration lacks sufficient postal-address components."
                    if printed_complete
                    else "The available OCR may be partial, so package non-compliance cannot be concluded."
                )
            ),
            normalized_value=raw_val,
            evidence=evidence,
            evidence_state=(
                EvidenceAvailabilityState.EVIDENCE_VERIFIED.value
                if printed_complete
                else EvidenceAvailabilityState.EVIDENCE_DETECTED_UNASSOCIATED.value
            ),
        )

    return ValidationResult(
        status="PASS",
        binary=1,
        reason=f"Detected address declaration: {raw_val}",
        normalized_value=raw_val,
        evidence=evidence,
    )


@register_validator("IMPORTER_PRESENT")
def validate_importer_present(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate importer name and address for imported commodities."""
    pre = _check_preconditions(evidence, rule)
    if pre:
        return pre

    raw_val = str(evidence.get("value", "")).strip()  # type: ignore[union-attr]
    cleaned = re.sub(r'^(?:imported\s+by|importer)[:\s-]*', '', raw_val, flags=re.IGNORECASE).strip()

    if len(re.sub(r'[^A-Za-z0-9]', '', cleaned)) < 3:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"Importer label is present but lacks a valid entity/address: '{raw_val}'.",
            normalized_value=raw_val,
            evidence=evidence,
        )

    return ValidationResult(
        status="PASS",
        binary=1,
        reason=f"Detected importer declaration: {raw_val}",
        normalized_value=cleaned or raw_val,
        evidence=evidence,
    )


def _parse_and_validate_date(date_str: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate date structure (month/year or day/month/year).

    Returns (is_valid, normalized_date_string, error_message).
    """
    token = date_str.strip().lower()

    # Reject non-date candidates (e.g. age restrictions, dosages, net quantities, prices)
    from app.extraction.declaration_extractor import is_valid_date_candidate, DATE_PREFIX_RE
    if not is_valid_date_candidate(date_str):
        if re.fullmatch(r'\d+\.\d+', token):
            return False, None, f"Numeric decimal value is not a valid date: '{date_str}'"
        return False, None, f"Value is not a valid date declaration: '{date_str}'"

    # Strip prefixes like "EXP", "MFD", "PKD", "USE BEFORE"
    core = DATE_PREFIX_RE.sub("", date_str).strip()
    token = core.lower()

    # Reject numeric noise like "0.73" or barcodes
    if re.fullmatch(r'\d+\.\d+', token):
        return False, None, f"Numeric decimal value is not a valid date: '{date_str}'"
    if '1800' in token or len(re.sub(r'\D', '', token)) > 8 or re.fullmatch(r'\d{10,}', token):
        return False, None, f"Barcode or telephone number is not a valid date: '{date_str}'"

    # Pattern: Mon/Year or Mon-Year (e.g. JUL/26, Oct 2025, Mar-24)
    month_text_match = re.search(
        r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*[/.-]?\s*(\d{2,4})\b',
        token,
    )
    if month_text_match:
        month_name = month_text_match.group(1)
        year_str = month_text_match.group(2)
        month_num = MONTH_NAMES.get(month_name, 0)
        if 1 <= month_num <= 12:
            return True, f"{month_name.upper()}/{year_str}", None

    # Pattern: Numeric tokens separated by / or - or .
    parts = [p for p in re.split(r'[/.-]', token) if p]
    if not parts or not all(p.isdigit() for p in parts):
        return False, None, f"Unrecognized date structure: '{date_str}'"

    nums = [int(p) for p in parts]

    # Case: Month and Year (e.g. 10/2025 or 10/25 or 2025/10)
    if len(nums) == 2:
        if 1 <= nums[0] <= 12 and (len(parts[1]) in (2, 4)):
            return True, f"{nums[0]:02d}/{parts[1]}", None
        if len(parts[0]) == 4 and 1 <= nums[1] <= 12:
            return True, f"{nums[1]:02d}/{parts[0]}", None
        return False, None, f"Invalid month/year values in date: '{date_str}'"

    # Case: Day, Month, Year (e.g. 31/08/2026 or 2026/08/31)
    if len(nums) == 3:
        if 1 <= nums[0] <= 31 and 1 <= nums[1] <= 12 and (len(parts[2]) in (2, 4)):
            return True, f"{nums[0]:02d}/{nums[1]:02d}/{parts[2]}", None
        if len(parts[0]) == 4 and 1 <= nums[1] <= 12 and 1 <= nums[2] <= 31:
            return True, f"{nums[2]:02d}/{nums[1]:02d}/{parts[0]}", None
        return False, None, f"Invalid day/month/year values in date: '{date_str}'"

    return False, None, f"Date does not contain 2 or 3 valid components: '{date_str}'"


@register_validator("DATE_PRESENT")
def validate_date_present(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate Month and Year of manufacture or pre-packing."""
    pre = _check_preconditions(evidence, rule)
    if pre:
        return pre

    raw_val = str(evidence.get("value", "")).strip()  # type: ignore[union-attr]
    is_valid, norm_date, err = _parse_and_validate_date(raw_val)

    if not is_valid:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=err or f"Invalid date declaration: '{raw_val}'.",
            normalized_value=raw_val,
            evidence=evidence,
        )

    return ValidationResult(
        status="PASS",
        binary=1,
        reason=f"Detected valid manufacture/packing date: {norm_date}",
        normalized_value=norm_date,
        evidence=evidence,
    )


@register_validator("BEST_BEFORE_OR_USE_BY_PRESENT")
def validate_best_before_present(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate Best Before or Use By declaration (food products)."""
    pre = _check_preconditions(evidence, rule)
    if pre:
        return pre

    raw_val = str(evidence.get("value", "")).strip()  # type: ignore[union-attr]

    # Check for duration statements like "24 months from mfg" or "best before 12 months from manufacture"
    from app.extraction.declaration_extractor import VALID_LIFECYCLE_DURATION_RE, is_valid_date_candidate
    if VALID_LIFECYCLE_DURATION_RE.search(raw_val) and is_valid_date_candidate(raw_val):
        return ValidationResult(
            status="PASS",
            binary=1,
            reason=f"Detected shelf-life duration statement: '{raw_val}'",
            normalized_value=raw_val,
            evidence=evidence,
        )

    # Check for specific date format
    is_valid, norm_date, err = _parse_and_validate_date(raw_val)
    if not is_valid:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=err or f"Invalid best before / use by date: '{raw_val}'.",
            normalized_value=raw_val,
            evidence=evidence,
        )

    return ValidationResult(
        status="PASS",
        binary=1,
        reason=f"Detected valid best before / use by date: {norm_date}",
        normalized_value=norm_date,
        evidence=evidence,
    )


@register_validator("EXPIRY_DATE_PRESENT")
def validate_expiry_date_present(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate expiry or use-before date (cosmetics / drugs)."""
    pre = _check_preconditions(evidence, rule)
    if pre:
        return pre

    raw_val = str(evidence.get("value", "")).strip()  # type: ignore[union-attr]

    # Check for duration statement
    from app.extraction.declaration_extractor import VALID_LIFECYCLE_DURATION_RE, is_valid_date_candidate
    if VALID_LIFECYCLE_DURATION_RE.search(raw_val) and is_valid_date_candidate(raw_val):
        return ValidationResult(
            status="PASS",
            binary=1,
            reason=f"Detected valid use-before duration: '{raw_val}'",
            normalized_value=raw_val,
            evidence=evidence,
        )

    is_valid, norm_date, err = _parse_and_validate_date(raw_val)
    if not is_valid:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=err or f"Invalid expiry / use-before date: '{raw_val}'.",
            normalized_value=raw_val,
            evidence=evidence,
        )

    return ValidationResult(
        status="PASS",
        binary=1,
        reason=f"Detected valid expiry / use-before date: {norm_date}",
        normalized_value=norm_date,
        evidence=evidence,
    )


@register_validator("CONSUMER_CARE_PRESENT")
def validate_consumer_care_present(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate consumer care declaration (contact phone, email, or address)."""
    pre = _check_preconditions(evidence, rule)
    if pre:
        return pre

    raw_val = str(evidence.get("value", "")).strip()  # type: ignore[union-attr]

    channels_detected: List[str] = []
    normalized_channels: List[str] = []
    raw_context = str(evidence.get("raw_text") or evidence.get("raw_value") or raw_val)  # type: ignore[union-attr]

    if str(evidence.get("source") or "").upper() == "OCR_GEMINI_RESOLVED" and not evidence.get("source_evidence"):  # type: ignore[union-attr]
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason="Consumer-care value from the semantic resolver has no OCR source evidence.",
            normalized_value=raw_val,
            evidence=evidence,
            evidence_state=EvidenceAvailabilityState.EVIDENCE_DETECTED_UNASSOCIATED.value,
        )

    structured_contacts = evidence.get("contacts") if isinstance(evidence, dict) else None
    contact_values = structured_contacts if isinstance(structured_contacts, list) else []

    # 1. Phone or Toll-free number
    phone_source = " ".join(
        str(contact.get("contact_value") or "")
        for contact in contact_values
        if isinstance(contact, dict) and str(contact.get("contact_type") or "").upper() in ("PHONE", "TOLL_FREE")
    ) or raw_val
    toll_free_match = re.search(r'\b1800[\s\-]?\d{3}[\s\-]?\d{3,4}\b', phone_source)
    phone_match = re.search(r'\b(?:\+91[\s-]?)?[6-9]\d{9}\b|\b\d{3,5}[\s-]\d{6,8}\b', phone_source)
    if toll_free_match:
        channels_detected.append("toll-free phone")
        normalized_channels.append(toll_free_match.group(0))
    elif phone_match:
        channels_detected.append("telephone")
        normalized_channels.append(phone_match.group(0))

    # 2. Email address
    normalized_emails: List[str] = []
    if contact_values:
        for contact in contact_values:
            if not isinstance(contact, dict) or str(contact.get("contact_type") or "").upper() != "EMAIL":
                continue
            contact_value = str(contact.get("contact_value") or "")
            normalized = normalize_contextual_email(contact_value, raw_context)
            if normalized and STRICT_EMAIL_RE.fullmatch(normalized):
                normalized_emails.append(normalized)
    else:
        normalized_emails = [item["value"] for item in extract_contextual_emails(raw_context)]
    if normalized_emails:
        email_value = normalized_emails[0]
        channels_detected.append(f"email ({email_value})")
        normalized_channels.append(email_value)

    # 3. Postal or customer care address with pincode / P.O. Box / helpline keyword
    if re.search(r'\b(?:p\.?o\.?\s*box|care@|helpline|toll\s*free|customer\s*care)\b', raw_val, re.I):
        if re.search(r'\d{6}|\bwrite\s+to\b|\bmanager\b', raw_val, re.I):
            channels_detected.append("postal care address")

    if not channels_detected:
        # Field exists but contains no actionable contact channel
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=(
                f"Consumer care declaration was detected but lacks a valid contact channel "
                f"(telephone, email, or postal address): '{raw_val}'."
            ),
            normalized_value=raw_val,
            evidence=evidence,
        )

    return ValidationResult(
        status="PASS",
        binary=1,
        reason=f"Detected consumer care contact details ({', '.join(channels_detected)}): {raw_val}",
        normalized_value=", ".join(normalized_channels) or raw_val,
        evidence=evidence,
    )


@register_validator("FSSAI_NUMBER_PRESENT")
def validate_fssai_number_present(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate FSSAI license number (standard 14-digit numeric format)."""
    pre = _check_preconditions(evidence, rule)
    if pre:
        return pre

    raw_val = str(evidence.get("value", "")).strip()  # type: ignore[union-attr]

    # Extract digits
    digits = re.sub(r'\D', '', raw_val)

    # Standard FSSAI license is 14 digits; registration licenses are 10-14 digits
    if not digits or len(digits) < 10 or len(digits) > 14:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"FSSAI license number must be 10-14 digits (standard 14), found: '{raw_val}'.",
            normalized_value=raw_val,
            evidence=evidence,
        )

    return ValidationResult(
        status="PASS",
        binary=1,
        reason=f"Detected valid FSSAI license number: {digits}",
        normalized_value=digits,
        evidence=evidence,
    )


@register_validator("BATCH_NUMBER_PRESENT")
def validate_batch_number_present(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate batch / lot number declaration."""
    pre = _check_preconditions(evidence, rule)
    if pre:
        return pre

    raw_val = str(evidence.get("value", "")).strip()  # type: ignore[union-attr]
    cleaned = re.sub(r'^(?:batch\s*(?:no\.?|number)?|lot\s*(?:no\.?|number)?|b\.?\s*no\.?)[:\s-]*', '', raw_val, flags=re.IGNORECASE).strip()

    invalid_batch_tokens = {"no", "number", "num", "code", "lot", "batch", "b", "none", "n/a", "n.a.", "null", "image", "placeholder", "[image]", "undefined"}
    is_art, _ = is_artifact_token(cleaned)
    if not cleaned or is_art or cleaned.lower() in invalid_batch_tokens or len(re.sub(r'[^A-Za-z0-9]', '', cleaned)) < 1:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"Batch number label present but lacks valid identifier: '{raw_val}'.",
            normalized_value=raw_val,
            evidence=evidence,
        )

    return ValidationResult(
        status="PASS",
        binary=1,
        reason=f"Detected batch/lot number: {cleaned or raw_val}",
        normalized_value=cleaned or raw_val,
        evidence=evidence,
    )


@register_validator("INGREDIENTS_PRESENT")
def validate_ingredients_present(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate list of ingredients declaration."""
    pre = _check_preconditions(evidence, rule)
    if pre:
        return pre

    raw_val = str(evidence.get("value", "")).strip()  # type: ignore[union-attr]
    cleaned = re.sub(r'^(?:ingredients?|composition)[:\s-]*', '', raw_val, flags=re.IGNORECASE).strip()

    if len(cleaned) < 3:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"Ingredients declaration label present but contains no ingredient items: '{raw_val}'.",
            normalized_value=raw_val,
            evidence=evidence,
        )

    return ValidationResult(
        status="PASS",
        binary=1,
        reason=f"Detected ingredients list: {raw_val}",
        normalized_value=cleaned or raw_val,
        evidence=evidence,
    )


@register_validator("VEG_NONVEG_PRESENT")
def validate_veg_nonveg_present(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate Vegetarian / Non-Vegetarian symbol or declaration (FSSAI)."""
    pre = _check_preconditions(evidence, rule)
    if pre:
        return pre

    raw_val = str(evidence.get("value", "")).strip()  # type: ignore[union-attr]
    lowered = raw_val.lower()

    # Distinguish detector candidate vs verified evidence
    is_candidate = bool(
        evidence.get("status") == "CANDIDATE"  # type: ignore[union-attr]
        or evidence.get("is_candidate") is True  # type: ignore[union-attr]
        or (evidence.get("source") == "VISUAL_DETECTION" and evidence.get("status") != "VERIFIED")  # type: ignore[union-attr]
    )

    if is_candidate:
        # A visual candidate alone must never become a legal PASS.
        symbol_type = evidence.get("value") or evidence.get("symbol_type") or "symbol"  # type: ignore[union-attr]
        det_method = evidence.get("detection_method", "visual detector")  # type: ignore[union-attr]
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=f"Visual candidate detected: {symbol_type} ({det_method}); declaration not detected reliably from package images.",
            normalized_value=str(symbol_type),
            evidence=evidence,
        )

    if any(k in lowered for k in ['vegetarian', 'non-vegetarian', 'non-veg', 'nonveg', 'veg symbol', 'veg']):
        status_label = "NON_VEG" if any(k in lowered for k in ['non-veg', 'nonveg', 'non-vegetarian']) else "VEG"
        return ValidationResult(
            status="PASS",
            binary=1,
            reason=f"Vegetarian/Non-Vegetarian declaration identified: {status_label} ('{raw_val}')",
            normalized_value=status_label,
            evidence=evidence,
        )

    return ValidationResult(
        status="NOT_VERIFIABLE",
        binary=0,
        reason=f"Symbol or indicator for Vegetarian/Non-Vegetarian not clearly confirmed from: '{raw_val}'.",
        normalized_value=raw_val,
        evidence=evidence,
    )


def _extract_declared_quantity_and_unit(
    all_fields: Dict[str, Any],
    evidence: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[float], Optional[str]]:
    """Deterministically retrieve declared net quantity numeric value and unit.

    Checks evidence override first, then all_fields ('DECLARED_NET_QUANTITY', 'NET_QUANTITY').
    """
    if evidence:
        for val_k, unit_k in [
            ("declared_quantity", "declared_unit"),
            ("declared_weight", "declared_unit"),
            ("declared_net_quantity", "declared_unit"),
        ]:
            if evidence.get(val_k) is not None:
                try:
                    q = float(evidence[val_k])
                    u = evidence.get(unit_k) or evidence.get("unit")
                    return q, str(u) if u else None
                except (ValueError, TypeError):
                    pass

    decl_field = (all_fields or {}).get("DECLARED_NET_QUANTITY") or (all_fields or {}).get("NET_QUANTITY")
    if decl_field is not None:
        if isinstance(decl_field, dict):
            num_val = decl_field.get("numeric_value")
            if num_val is None:
                num_val = (
                    decl_field.get("unit_net_quantity")
                    or decl_field.get("unit_quantity")
                    or decl_field.get("quantity_value")
                )
            unit_val = (
                decl_field.get("normalized_unit")
                or decl_field.get("unit")
                or decl_field.get("quantity_unit")
            )

            if num_val is not None:
                try:
                    return float(num_val), str(unit_val) if unit_val else None
                except (ValueError, TypeError):
                    pass

            text_val = decl_field.get("value") or decl_field.get("raw_value")
            if text_val:
                parsed_val, parsed_u, _ = extract_quantity_value_unit(str(text_val))
                if parsed_val is not None:
                    return parsed_val, parsed_u or (str(unit_val) if unit_val else None)
        elif isinstance(decl_field, (int, float)):
            return float(decl_field), None
        elif isinstance(decl_field, str):
            parsed_val, parsed_u, _ = extract_quantity_value_unit(decl_field)
            if parsed_val is not None:
                return parsed_val, parsed_u

    return None, None


def _extract_measured_quantity_and_unit(
    evidence: Optional[Dict[str, Any]],
) -> Tuple[Optional[float], Optional[str]]:
    """Extract physical measured quantity and unit from evidence."""
    if not evidence:
        return None, None

    for k in (
        "measured_weight",
        "measured_quantity",
        "actual_weight",
        "actual_quantity",
        "actual_net_content",
        "numeric_value",
    ):
        v = evidence.get(k)
        if v is not None:
            try:
                num = float(v)
                u = (
                    evidence.get("measured_unit")
                    or evidence.get("actual_unit")
                    or evidence.get("unit")
                    or evidence.get("quantity_unit")
                )
                return num, str(u) if u else None
            except (ValueError, TypeError):
                pass

    for k in ("value", "raw_value", "raw_text"):
        v = evidence.get(k)
        if v is not None:
            if isinstance(v, (int, float)):
                u = evidence.get("measured_unit") or evidence.get("unit")
                return float(v), str(u) if u else None
            if isinstance(v, str) and v.strip():
                parsed_val, parsed_u, _ = extract_quantity_value_unit(v)
                if parsed_val is not None:
                    u = evidence.get("measured_unit") or evidence.get("unit") or parsed_u
                    return parsed_val, str(u) if u else None

    return None, None


def _convert_to_base_units(
    declared_qty: float,
    declared_unit: Optional[str],
    measured_qty: float,
    measured_unit: Optional[str],
) -> Tuple[float, float, str, Optional[str]]:
    """Convert declared and measured quantities to their canonical base unit (g, ml, m, sq m, pieces).

    Returns:
        Tuple of (declared_base, measured_base, base_unit, error_message_if_any)
    """
    decl_u_norm, decl_type = normalize_unit(declared_unit)
    if not measured_unit:
        measured_unit = declared_unit
    meas_u_norm, meas_type = normalize_unit(measured_unit)

    if decl_type and meas_type and decl_type != meas_type:
        return (
            declared_qty,
            measured_qty,
            decl_u_norm or declared_unit or "",
            f"Measurement dimension mismatch: declared is {decl_type.value} ({declared_unit}) but measured is {meas_type.value} ({measured_unit}).",
        )

    target_type = decl_type or meas_type or QuantityType.MASS
    decl_clean = (decl_u_norm or declared_unit or "g").lower()
    meas_clean = (meas_u_norm or measured_unit or "g").lower()

    if target_type == QuantityType.MASS:
        base_u = "g"
        if decl_clean in ("kg", "kgs", "kilogram", "kilograms"):
            d_base = declared_qty * 1000.0
        elif decl_clean in ("mg", "milligram", "milligrams"):
            d_base = declared_qty / 1000.0
        else:
            d_base = declared_qty

        if meas_clean in ("kg", "kgs", "kilogram", "kilograms"):
            m_base = measured_qty * 1000.0
        elif meas_clean in ("mg", "milligram", "milligrams"):
            m_base = measured_qty / 1000.0
        else:
            m_base = measured_qty

        return d_base, m_base, base_u, None

    if target_type == QuantityType.VOLUME:
        base_u = "ml"
        if decl_clean in ("l", "ltr", "litre", "litres", "liter", "liters"):
            d_base = declared_qty * 1000.0
        elif decl_clean in ("cl",):
            d_base = declared_qty * 10.0
        else:
            d_base = declared_qty

        if meas_clean in ("l", "ltr", "litre", "litres", "liter", "liters"):
            m_base = measured_qty * 1000.0
        elif meas_clean in ("cl",):
            m_base = measured_qty * 10.0
        else:
            m_base = measured_qty

        return d_base, m_base, base_u, None

    if target_type == QuantityType.LENGTH_AREA:
        base_u = decl_u_norm or "m"
        d_base = declared_qty
        m_base = measured_qty
        if "cm" in decl_clean:
            d_base = declared_qty / 100.0
            base_u = "m"
        if "cm" in meas_clean:
            m_base = measured_qty / 100.0
        return d_base, m_base, base_u, None

    return declared_qty, measured_qty, decl_u_norm or "pieces", None


def calculate_maximum_permissible_error(
    declared_quantity: float,
    unit: str,
) -> Tuple[float, float, str, str]:
    """Calculate Maximum Permissible Error (MPE) under Rule 14 & Second Schedule of LMPC Rules, 2011.

    Args:
        declared_quantity: Declared quantity in canonical base units (e.g. g for mass, ml for volume).
        unit: Canonical unit string ('g', 'ml', etc.).

    Returns:
        Tuple of (mpe_value, min_allowable_quantity, base_unit, calculation_description).
    """
    q = float(declared_quantity)
    u = unit.lower()

    if u in ("g", "gm", "gram", "grams", "ml", "millilitre", "millilitres", "milliliter", "milliliters"):
        base_u = "g" if u in ("g", "gm", "gram", "grams") else "ml"
        if q <= 50.0:
            mpe = 0.09 * q
            desc = f"9.0% of declared quantity ({q:g}{base_u})"
        elif q <= 100.0:
            mpe = 4.5
            desc = f"4.5{base_u} (Rule 14 flat tier for 50-100{base_u})"
        elif q <= 200.0:
            mpe = 0.045 * q
            desc = f"4.5% of declared quantity ({q:g}{base_u})"
        elif q <= 300.0:
            mpe = 9.0
            desc = f"9.0{base_u} (Rule 14 flat tier for 200-300{base_u})"
        elif q <= 500.0:
            mpe = 0.03 * q
            desc = f"3.0% of declared quantity ({q:g}{base_u})"
        elif q <= 1000.0:
            mpe = 15.0
            desc = f"15.0{base_u} (Rule 14 flat tier for 500-1000{base_u})"
        elif q <= 10000.0:
            mpe = 0.015 * q
            desc = f"1.5% of declared quantity ({q:g}{base_u})"
        elif q <= 15000.0:
            mpe = 150.0
            desc = f"150.0{base_u} (Rule 14 flat tier for 10000-15000{base_u})"
        else:
            mpe = 0.01 * q
            desc = f"1.0% of declared quantity ({q:g}{base_u})"

        min_allowable = q - mpe
        return round(mpe, 4), round(min_allowable, 4), base_u, desc

    mpe = round(0.02 * q, 4)
    min_allowable = round(q - mpe, 4)
    return mpe, min_allowable, u, f"2.0% of declared quantity ({q:g}{u})"


@register_validator("PHYSICAL_WEIGHT_CHECK")
def validate_physical_weight(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate physical gravimetric/volumetric net quantity against Second Schedule MPE tolerances.

    Rule PC-ALL-012 (Legal Metrology Act Sec 18, Rule 14 & Second Schedule, Rule 19 & Third Schedule).
    Never infers physical weight from OCR, Gemini, visual detection, or package dimensions.
    Returns NOT_VERIFIABLE when trustworthy physical measurement is unavailable.
    """
    parameter = rule.get("parameter", "ACTUAL_NET_CONTENT")

    # 1. Missing evidence check
    if not evidence:
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=(
                "Physical net content verification requires direct gravimetric/volumetric measurement "
                "using calibrated apparatus under Rule 19 & Third Schedule. No physical measurement evidence provided."
            ),
            evidence=None,
            evidence_state=EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value,
        )

    # 2. Source trustworthiness check (Strict anti-hallucination & anti-visual-inference guard)
    source = str(evidence.get("source") or "").upper()
    is_physical = bool(
        evidence.get("is_physical_measurement") is True
        or evidence.get("physical_measurement") is True
        or source in (
            "PHYSICAL_MEASUREMENT",
            "SCALE",
            "CALIBRATED_SCALE",
            "GRAVIMETRIC",
            "INSPECTOR_INPUT",
            "PHYSICAL_INSPECTION",
            "MANUAL_MEASUREMENT",
        )
    )

    if (
        source in ("GEMINI", "LLM", "AI", "PROMPT", "CHAT")
        or (source in ("OCR", "VISUAL_DETECTION", "VISUAL", "IMAGE", "INFERENCE") and not is_physical)
        or evidence.get("inferred_from_image") is True
        or evidence.get("inferred_from_dimensions") is True
        or evidence.get("is_estimated") is True
    ):
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=(
                "Physical weight cannot be inferred from OCR, Gemini, visual detection, package dimensions, "
                "or product categories. Physical measurement using calibrated apparatus is required under Rule 19 & Third Schedule."
            ),
            evidence=evidence,
            evidence_state=EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value,
        )

    # 3. Extract measured physical quantity
    meas_qty, meas_unit = _extract_measured_quantity_and_unit(evidence)
    if meas_qty is None or meas_qty <= 0:
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason="No valid physical measured weight/quantity provided in measurement evidence.",
            evidence=evidence,
            evidence_state=EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value,
        )

    # 4. Retrieve declared net quantity from all_fields
    decl_qty, decl_unit = _extract_declared_quantity_and_unit(all_fields, evidence)
    if decl_qty is None or decl_qty <= 0:
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason="Cannot verify physical weight: declared net quantity declaration could not be retrieved from package evidence.",
            evidence=evidence,
            evidence_state=EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value,
        )

    # 5. Unit conversion and normalization
    d_base, m_base, base_u, err = _convert_to_base_units(
        decl_qty, decl_unit, meas_qty, meas_unit
    )
    if err:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=err,
            evidence=evidence,
            evidence_state=EvidenceAvailabilityState.EVIDENCE_CONFLICTING.value,
        )

    # 6. Statutory MPE calculation
    mpe, min_allowable, base_u, calc_desc = calculate_maximum_permissible_error(d_base, base_u)
    deficiency = round(d_base - m_base, 4)

    # 7. Compliance determination
    if m_base < min_allowable:
        status = "FAIL"
        binary = 0
        reason = (
            f"Actual weight {m_base:g}{base_u} is below declared {d_base:g}{base_u} by {deficiency:g}{base_u}, "
            f"exceeding maximum permissible error of {mpe:g}{base_u} (minimum allowable: {min_allowable:g}{base_u} "
            f"under Rule 14 & Second Schedule)."
        )
    else:
        status = "PASS"
        binary = 1
        if m_base >= d_base:
            reason = (
                f"Actual weight {m_base:g}{base_u} satisfies declared {d_base:g}{base_u} "
                f"(exceeds or meets declared quantity; within MPE tolerance of {mpe:g}{base_u})."
            )
        else:
            reason = (
                f"Actual weight {m_base:g}{base_u} satisfies declared {d_base:g}{base_u} "
                f"within maximum permissible error tolerance (deficiency {deficiency:g}{base_u} <= MPE {mpe:g}{base_u}, "
                f"minimum allowable: {min_allowable:g}{base_u} under Rule 14 & Second Schedule)."
            )

    # 8. Provenance preservation
    ev_record = dict(evidence)
    ev_record.update({
        "declared_quantity": decl_qty,
        "declared_unit": decl_unit,
        "declared_base_quantity": d_base,
        "measured_quantity": meas_qty,
        "measured_unit": meas_unit,
        "measured_base_quantity": m_base,
        "base_unit": base_u,
        "applicable_tolerance_mpe": mpe,
        "minimum_allowable_quantity": min_allowable,
        "deficiency": max(0.0, deficiency),
        "mpe_calculation": calc_desc,
        "statutory_reference": "Legal Metrology Act 2009 Sec 18; LMPC Rules 2011 Rule 14 (Sched II), Rule 19 (Sched III)",
    })

    return ValidationResult(
        status=status,
        binary=binary,
        reason=reason,
        normalized_value=f"{m_base:g} {base_u}",
        raw_value=str(evidence.get("raw_value") or evidence.get("value") or f"{meas_qty} {meas_unit or base_u}"),
        value=m_base,
        unit=base_u,
        evidence=ev_record,
        evidence_state=EvidenceAvailabilityState.EVIDENCE_VERIFIED.value,
    )


@register_validator("FONT_SIZE_CHECK")
def validate_font_size(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate font/numeral height in millimetres against Rule 7(3) Table-I / Table-II minimums.

    Rule PC-ALL-013 (Legal Metrology (Packaged Commodities) Rules, 2011 Rule 7(3)).
    Never interprets raw OCR bounding box pixel height as physical millimetres.
    Requires calibrated measurement (caliper, calibrated optical graticule, or physical measurement gauge).
    Returns NOT_VERIFIABLE when calibrated physical measurement is unavailable.
    """
    parameter = rule.get("parameter", "FONT_SIZE_COMPLIANCE")

    # 1. Missing evidence check
    if not evidence:
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=(
                "Visual screening cannot confirm physical millimetre height without calibrated optics and "
                "physical scale reference. Physical measurement of numeral and letter height in millimeters "
                "using calibrated gauge or caliper under Rule 7 Table-I/II required."
            ),
            evidence=None,
            evidence_state=EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value,
        )

    # 2. Source trustworthiness check (Strict anti-hallucination & anti-visual-inference guard)
    source = str(evidence.get("source") or "").upper()
    if source in ("GEMINI", "LLM", "AI", "PROMPT", "CHAT"):
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason="Font size compliance cannot be determined by Gemini or visual LLM estimation. Calibrated physical measurement required under Rule 7 Table-I/II.",
            evidence=evidence,
            evidence_state=EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value,
        )

    # 3. Calibration verification
    is_calibrated = bool(
        evidence.get("is_calibrated") is True
        or evidence.get("calibrated") is True
        or evidence.get("calibration_factor") is not None
        or evidence.get("calibration_reference") is not None
        or source in (
            "CALIPER",
            "VERNIER_CALIPER",
            "CALIBRATED_GAUGE",
            "CALIBRATED_OPTICS",
            "OPTICAL_GRATICULE",
            "PHYSICAL_MEASUREMENT",
            "INSPECTOR_INPUT",
        )
    )

    # Reject raw uncalibrated pixel bounding boxes
    if not is_calibrated or (evidence.get("pixel_height") is not None and not evidence.get("is_calibrated")):
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=(
                "Visual screening cannot confirm physical millimetre height without calibrated optics and "
                "physical scale reference. Ordinary OCR bounding box pixel height cannot be interpreted as physical millimetres."
            ),
            evidence=evidence,
            evidence_state=EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value,
        )

    # 4. Extract measured physical height in mm
    measured_mm: Optional[float] = None
    for k in (
        "measured_height_mm",
        "measured_font_size_mm",
        "measured_height",
        "measured_mm",
        "font_size_mm",
        "numeric_value",
        "value",
    ):
        v = evidence.get(k)
        if v is not None:
            if isinstance(v, (int, float)):
                measured_mm = float(v)
                break
            if isinstance(v, str):
                cleaned = re.sub(r"[^\d.]", "", v)
                if cleaned:
                    try:
                        measured_mm = float(cleaned)
                        break
                    except ValueError:
                        pass

    if measured_mm is None or measured_mm <= 0:
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason="No valid calibrated font height measurement in millimetres found in evidence.",
            evidence=evidence,
            evidence_state=EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value,
        )

    # 5. Determine applicable minimum font height requirement under Rule 7(3) Table-I / Table-II
    required_mm: float = 2.0  # Statutory baseline for numerals/letters
    rule_specified = rule.get("minimum_height_mm") or rule.get("required_height_mm") or rule.get("threshold_mm")
    ev_specified = evidence.get("required_height_mm") or evidence.get("minimum_height_mm") or evidence.get("threshold_mm")

    if rule_specified is not None:
        try:
            required_mm = float(rule_specified)
        except (ValueError, TypeError):
            pass
    elif ev_specified is not None:
        try:
            required_mm = float(ev_specified)
        except (ValueError, TypeError):
            pass
    else:
        decl_qty, decl_unit = _extract_declared_quantity_and_unit(all_fields, evidence)
        if decl_qty is not None and decl_qty > 0:
            norm_u, q_type = normalize_unit(decl_unit)
            if q_type == QuantityType.MASS:
                q_g = decl_qty * 1000.0 if norm_u == "kg" else (decl_qty / 1000.0 if norm_u == "mg" else decl_qty)
                if q_g <= 50.0:
                    required_mm = 1.0
                elif q_g <= 200.0:
                    required_mm = 2.0
                elif q_g <= 1000.0:
                    required_mm = 4.0
                else:
                    required_mm = 6.0
            elif q_type == QuantityType.VOLUME:
                q_ml = decl_qty * 1000.0 if norm_u == "L" else (decl_qty * 10.0 if norm_u == "cl" else decl_qty)
                if q_ml <= 50.0:
                    required_mm = 1.0
                elif q_ml <= 200.0:
                    required_mm = 2.0
                elif q_ml <= 1000.0:
                    required_mm = 4.0
                else:
                    required_mm = 6.0

    # 6. Compare measured physical height deterministically
    if measured_mm >= required_mm:
        status = "PASS"
        binary = 1
        reason = f"Measured font height {measured_mm:g}mm satisfies statutory minimum {required_mm:g}mm under Rule 7(3)."
    else:
        status = "FAIL"
        binary = 0
        reason = f"Font height {measured_mm:g}mm is below required {required_mm:g}mm under Rule 7(3)."

    # 7. Preserve evidence provenance
    ev_record = dict(evidence)
    ev_record.update({
        "measured_height_mm": measured_mm,
        "required_height_mm": required_mm,
        "is_calibrated": True,
        "statutory_reference": "Rule 7(3), Table-I & Table-II of Legal Metrology (Packaged Commodities) Rules, 2011",
    })

    return ValidationResult(
        status=status,
        binary=binary,
        reason=reason,
        normalized_value=f"{measured_mm:g} mm",
        raw_value=str(evidence.get("raw_value") or evidence.get("value") or f"{measured_mm} mm"),
        value=measured_mm,
        unit="mm",
        evidence=ev_record,
        evidence_state=EvidenceAvailabilityState.EVIDENCE_VERIFIED.value,
    )


# Fallback mapping from rule parameter to validation method if omitted in rule dict
DEFAULT_PARAMETER_VALIDATION_METHODS: Dict[str, str] = {
    "PRODUCT_NAME": "TEXT_PRESENT",
    "DECLARED_NET_QUANTITY": "VALUE_AND_UNIT_PRESENT",
    "MRP": "MRP_PRESENT",
    "MANUFACTURER_NAME": "MANUFACTURER_PRESENT",
    "MANUFACTURER_ADDRESS": "ADDRESS_PRESENT",
    "COUNTRY_OF_ORIGIN": "TEXT_PRESENT",
    "IMPORTER_NAME_ADDRESS": "IMPORTER_PRESENT",
    "CONSUMER_CARE": "CONSUMER_CARE_PRESENT",
    "MONTH_YEAR_MANUFACTURE": "DATE_PRESENT",
    "MANUFACTURE_DATE": "DATE_PRESENT",
    "PACKING_DATE": "DATE_PRESENT",
    "GENERIC_NAME": "TEXT_PRESENT",
    "UNIT_SALE_PRICE": "TEXT_PRESENT",
    "BEST_BEFORE_USE_BY": "BEST_BEFORE_OR_USE_BY_PRESENT",
    "INGREDIENTS_LIST": "INGREDIENTS_PRESENT",
    "NUTRITIONAL_INFO": "TEXT_PRESENT",
    "FSSAI_LICENSE": "FSSAI_NUMBER_PRESENT",
    "VEG_NONVEG_SYMBOL": "VEG_NONVEG_PRESENT",
    "BATCH_NUMBER": "BATCH_NUMBER_PRESENT",
    "USE_BEFORE_DATE": "EXPIRY_DATE_PRESENT",
    "ACTUAL_NET_CONTENT": "PHYSICAL_WEIGHT_CHECK",
    "FONT_SIZE_COMPLIANCE": "FONT_SIZE_CHECK",
}


def dispatch_validator(
    validation_method: Optional[str],
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Dispatch evidence to the validator corresponding to rule's validation_method.

    Fails safely as NOT_VERIFIABLE if validation_method is unknown.
    Never declares PASS merely because a field exists.
    """
    # Package-type applicability guard (Wholesale & Institutional/Industrial exemptions)
    pkg_context = str(
        (all_fields or {}).get("package_type")
        or (all_fields.get("PACKAGE_TYPE", {}).get("value") if isinstance(all_fields.get("PACKAGE_TYPE"), dict) else None)
        or rule.get("current_package_type")
        or ""
    ).upper()
    rule_pkg = str(rule.get("package_type", "ALL")).upper()
    param = rule.get("parameter", "")

    if pkg_context in ("WHOLESALE", "INSTITUTIONAL", "INDUSTRIAL") and rule_pkg == "RETAIL":
        if param == "UNIT_SALE_PRICE":
            reason = f"Unit sale price is not required on {pkg_context.lower()} packages under Rule 24 and Department of Consumer Affairs guidance."
        elif param == "MRP":
            reason = f"Retail sale price (MRP) declaration is not applicable to {pkg_context.lower()} packages under Chapter III / Rule 24."
        elif param == "CONSUMER_CARE":
            reason = f"Consumer care declaration is not mandatory on outer {pkg_context.lower()} packages under Rule 24."
        else:
            reason = f"Retail declaration '{param}' is not applicable to {pkg_context.lower()} packages under Chapter III / Rule 24 of LMPC Rules, 2011."
        return ValidationResult(
            status="NOT_APPLICABLE",
            binary=None,
            reason=reason,
            evidence=evidence,
            evidence_state=evidence.get("evidence_state", EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value) if evidence else EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value,
        )

    # Intercept conflicting or ambiguous evidence upfront across all rules
    if evidence and (
        evidence.get("status") in ("CONFLICTING_EVIDENCE", "AMBIGUOUS", "REVIEW")
        or evidence.get("has_conflict") is True
        or evidence.get("is_ambiguous") is True
    ):
        raw_candidates = evidence.get("competing_candidates") or evidence.get("values") or [evidence.get("value")]
        cand_vals = []
        for c in raw_candidates:
            if isinstance(c, dict):
                v = c.get("value") or c.get("normalized_value")
            else:
                v = c
            if v is not None and str(v).strip():
                cand_vals.append(str(v).strip())

        unique_cand_vals = list(dict.fromkeys(cand_vals))

        # Only treat as ambiguous/competing if > 1 unique candidate value exists OR explicit cross-view conflict exists
        if len(unique_cand_vals) <= 1 and not evidence.get("has_conflict"):
            # Check if there is an explicit non-competing review reason
            if evidence.get("status") in ("AMBIGUOUS", "REVIEW") and evidence.get("reason"):
                msg = evidence.get("reason")
                return ValidationResult(
                    status="NOT_VERIFIABLE",
                    binary=0,
                    reason=msg,
                    normalized_value=str(evidence.get("value", "")),
                    evidence=evidence,
                    evidence_state=evidence.get("evidence_state", EvidenceAvailabilityState.EVIDENCE_DETECTED_UNASSOCIATED.value),
                )
            # Otherwise, clear false ambiguity flag and let validator evaluate the single candidate!
            if evidence.get("status") in ("AMBIGUOUS", "REVIEW"):
                evidence["status"] = "VALID"
            evidence["is_ambiguous"] = False
        else:
            cand_str = ", ".join(unique_cand_vals) if unique_cand_vals else str(evidence.get("value", ""))
            parameter = rule.get("parameter", "UNKNOWN")
            is_amb = evidence.get("status") in ("AMBIGUOUS", "REVIEW") or evidence.get("is_ambiguous")
            msg = (
                f"Ambiguous or competing candidate declarations detected for '{parameter}': "
                f"[{cand_str}]. Declaration not detected reliably from package images."
                if is_amb
                else f"Conflicting evidence detected across package views for '{parameter}': [{cand_str}]. Declaration not detected reliably from package images."
            )
            return ValidationResult(
                status="NOT_VERIFIABLE",
                binary=0,
                reason=msg,
                normalized_value=str(evidence.get("value", "")),
                evidence=evidence,
                evidence_state=EvidenceAvailabilityState.EVIDENCE_CONFLICTING.value,
            )

    method = validation_method

    # If method is missing, fallback to default for this parameter if known
    if not method:
        parameter = rule.get("parameter", "")
        method = DEFAULT_PARAMETER_VALIDATION_METHODS.get(parameter)

    if not method:
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=f"Rule '{rule.get('rule_id')}' has no validation method specified and cannot be evaluated deterministically.",
            evidence=evidence,
            evidence_state=evidence.get("evidence_state", EvidenceAvailabilityState.EVIDENCE_DETECTED_UNASSOCIATED.value) if evidence else EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value,
        )

    validator_func = VALIDATOR_REGISTRY.get(method)
    if not validator_func:
        logger.warning(
            "Unknown validation method '%s' for rule '%s'",
            method,
            rule.get("rule_id"),
        )
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=f"Unknown validation method '{method}'. Cannot determine compliance deterministically.",
            evidence=evidence,
            evidence_state=evidence.get("evidence_state", EvidenceAvailabilityState.EVIDENCE_DETECTED_UNASSOCIATED.value) if evidence else EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value,
        )

    # Execute the deterministic validator
    res = validator_func(evidence, rule, all_fields)
    if res.evidence_state is None:
        if evidence:
            ev_st = evidence.get("evidence_state")
            if not ev_st:
                if evidence.get("status") in ("CONFLICTING_EVIDENCE", "AMBIGUOUS", "REVIEW") or evidence.get("has_conflict") or evidence.get("is_ambiguous"):
                    ev_st = EvidenceAvailabilityState.EVIDENCE_CONFLICTING.value
                elif float(evidence.get("confidence") or 0.8) < MIN_OCR_CONFIDENCE:
                    ev_st = EvidenceAvailabilityState.EVIDENCE_LOW_CONFIDENCE.value
                elif evidence.get("semantic_section") == "UNKNOWN" and evidence.get("source_label") is None:
                    ev_st = EvidenceAvailabilityState.EVIDENCE_DETECTED_UNASSOCIATED.value
                else:
                    ev_st = EvidenceAvailabilityState.EVIDENCE_VERIFIED.value
            res.evidence_state = ev_st
        else:
            res.evidence_state = EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value
    return res
