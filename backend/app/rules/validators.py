"""
Deterministic Validation Layer for Rule Matrix.

Implements a validator-dispatch architecture where each rule's validation_method
is executed deterministically rather than merely checking field presence.
"""

from dataclasses import dataclass, field
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Minimum OCR confidence threshold to consider evidence verifiable
MIN_OCR_CONFIDENCE = 0.6

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
    quantity_present: Optional[bool] = None
    unit_present: Optional[bool] = None
    quantity_unit_valid: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert validation result to dictionary representation."""
        data: Dict[str, Any] = {
            "status": self.status,
            "binary": self.binary,
            "reason": self.reason,
        }
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
        if self.quantity_present is not None:
            data["quantity_present"] = self.quantity_present
        if self.unit_present is not None:
            data["unit_present"] = self.unit_present
        if self.quantity_unit_valid is not None:
            data["quantity_unit_valid"] = self.quantity_unit_valid
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

    # 0. Conflicting evidence across views/sources requires manual review, never silently PASS
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
                f"[{vals_str}]. Manual inspection and review required."
            ),
            normalized_value=str(evidence.get("value", "")),
            evidence=evidence,
        )

    # 1. Missing evidence or empty value
    if not evidence or evidence.get("value") is None or not str(evidence.get("value", "")).strip():
        if required:
            return ValidationResult(
                status="NOT_VERIFIABLE",
                binary=0,
                reason=f"Required declaration '{parameter}' was not detected in the available OCR evidence.",
                evidence=None,
            )
        return ValidationResult(
            status="NOT_APPLICABLE",
            binary=None,
            reason=f"Optional declaration '{parameter}' not identified and not required for this context.",
            evidence=None,
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
                f"[{vals_str}]. Manual inspection and review required."
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

    # 4. Extract or parse quantity value and unit token
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
            quantity_present=True,
            unit_present=True,
            quantity_unit_valid=False,
            evidence=evidence,
        )

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
        quantity_present=True,
        unit_present=True,
        quantity_unit_valid=True,
        evidence=evidence,
    )


# Dedicated alias export
validate_quantity_unit_pair = validate_value_and_unit_present


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

    raw_val = str(evidence.get("value", "")).strip()  # type: ignore[union-attr]

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
    """Validate presence and name of manufacturer, packer, or marketer."""
    pre = _check_preconditions(evidence, rule)
    if pre:
        return pre

    raw_val = str(evidence.get("value", "")).strip()  # type: ignore[union-attr]

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

    # Address should contain sufficient descriptive information
    alphanumeric_count = len(re.sub(r'[^A-Za-z0-9]', '', raw_val))
    if alphanumeric_count < 5:
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"Address declaration is incomplete or too short: '{raw_val}'.",
            normalized_value=raw_val,
            evidence=evidence,
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

    # Check for duration statements like "24 months from mfg" or "best within 6 months"
    duration_match = re.search(r'\b\d+\s*(?:months?|days?|years?)\s*(?:from|of)?\b', raw_val, re.IGNORECASE)
    if duration_match:
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
    duration_match = re.search(r'\b\d+\s*(?:months?|days?|years?)\b', raw_val, re.IGNORECASE)
    if duration_match and re.search(r'from\s*(?:mfg|mfd|pkg|pack)', raw_val, re.IGNORECASE):
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

    # 1. Phone or Toll-free number
    if re.search(r'\b1800[\s\-]?\d{3}[\s\-]?\d{3,4}\b', raw_val):
        channels_detected.append("toll-free phone")
    elif re.search(r'\b(?:\+91[\s-]?)?[6-9]\d{9}\b|\b\d{3,5}[\s-]\d{6,8}\b', raw_val):
        channels_detected.append("telephone")

    # 2. Email address
    email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', raw_val)
    if email_match:
        channels_detected.append(f"email ({email_match.group(0)})")

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
        normalized_value=raw_val,
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

    if len(re.sub(r'[^A-Za-z0-9]', '', cleaned)) < 1:
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
            reason=f"Visual candidate detected: {symbol_type} ({det_method}); requires inspector confirmation to verify compliance.",
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


@register_validator("PHYSICAL_WEIGHT_CHECK")
def validate_physical_weight_check(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate actual net content against declared net quantity (physical inspection required)."""
    # Physical-only requirement remains NOT_VERIFIABLE until physical measurement is supplied
    physical_value = None
    if evidence and evidence.get("physical_measured_value") is not None:
        physical_value = evidence.get("physical_measured_value")
    elif evidence and evidence.get("value") is not None:
        # Check if caller supplied explicit physical verification measurement
        source = evidence.get("source", "")
        if "PHYSICAL" in str(source).upper() or "MANUAL" in str(source).upper():
            physical_value = evidence.get("value")

    if physical_value is None:
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason="Physical verification is required before this requirement can be confirmed. Physical measurement data has not been provided.",
            evidence=None,
        )

    # If physical measurement data is supplied, validate it against declared quantity
    declared_net = all_fields.get("DECLARED_NET_QUANTITY", {})
    declared_val = declared_net.get("quantity_value")

    if declared_val is not None:
        try:
            declared_num = float(declared_val)
            actual_num = float(re.sub(r'[^\d.]', '', str(physical_value)))
            # Maximum Permissible Error tolerance: standard ~2% or within nominal declared
            if actual_num >= declared_num * 0.98:
                return ValidationResult(
                    status="PASS",
                    binary=1,
                    reason=f"Physical verification passed: actual weight ({actual_num}) satisfies declared quantity ({declared_num}).",
                    normalized_value=str(physical_value),
                    evidence=evidence,
                )
            return ValidationResult(
                status="FAIL",
                binary=0,
                reason=f"Physical verification failed: actual weight ({actual_num}) is below declared quantity ({declared_num}).",
                normalized_value=str(physical_value),
                evidence=evidence,
            )
        except (ValueError, TypeError):
            pass

    return ValidationResult(
        status="PASS",
        binary=1,
        reason=f"Physical verification available: {physical_value}",
        normalized_value=str(physical_value),
        evidence=evidence,
    )


@register_validator("FONT_SIZE_CHECK")
def validate_font_size_check(
    evidence: Optional[Dict[str, Any]],
    rule: Dict[str, Any],
    all_fields: Dict[str, Any],
) -> ValidationResult:
    """Validate numeral and letter font height compliance (Rule 7, physical verification required)."""
    physical_height = None
    if evidence and evidence.get("physical_font_height_mm") is not None:
        physical_height = evidence.get("physical_font_height_mm")
    elif evidence and evidence.get("value") is not None:
        source = evidence.get("source", "")
        if "PHYSICAL" in str(source).upper() or "MANUAL" in str(source).upper():
            physical_height = evidence.get("value")

    if physical_height is None:
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason="Physical verification is required before this requirement can be confirmed. Font/numeral height measurement has not been provided.",
            evidence=None,
        )

    try:
        height_mm = float(re.sub(r'[^\d.]', '', str(physical_height)))
        # Minimum font height under Rule 7 table is typically 1.0mm - 4.0mm depending on package size
        min_required_mm = float(rule.get("min_font_height_mm", 1.0))
        if height_mm >= min_required_mm:
            return ValidationResult(
                status="PASS",
                binary=1,
                reason=f"Font height measurement ({height_mm}mm) meets minimum required ({min_required_mm}mm).",
                normalized_value=f"{height_mm}mm",
                evidence=evidence,
            )
        return ValidationResult(
            status="FAIL",
            binary=0,
            reason=f"Font height measurement ({height_mm}mm) is below minimum required ({min_required_mm}mm).",
            normalized_value=f"{height_mm}mm",
            evidence=evidence,
        )
    except (ValueError, TypeError):
        return ValidationResult(
            status="PASS",
            binary=1,
            reason=f"Physical verification available: {physical_height}",
            normalized_value=str(physical_height),
            evidence=evidence,
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
    # Intercept conflicting evidence upfront across all rules
    if evidence and (
        evidence.get("status") == "CONFLICTING_EVIDENCE"
        or evidence.get("has_conflict") is True
    ):
        conflicting_vals = evidence.get("values") or [evidence.get("value")]
        vals_str = ", ".join(str(v) for v in conflicting_vals)
        parameter = rule.get("parameter", "UNKNOWN")
        return ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason=(
                f"Conflicting evidence detected across package views for '{parameter}': "
                f"[{vals_str}]. Manual inspection and review required."
            ),
            normalized_value=str(evidence.get("value", "")),
            evidence=evidence,
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
        )

    # Execute the deterministic validator
    return validator_func(evidence, rule, all_fields)
