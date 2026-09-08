"""
Canonical Packaging Declaration Ontology and Measurement Models.

Defines standardized fields, field groups, quantity measurement types (Mass, Volume, Count, Length/Area),
and legal unit mappings under the Legal Metrology (Packaged Commodities) Rules, 2011.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union


class CanonicalDeclarationField(str, Enum):
    """Canonical declaration fields recognized across all packaged commodities."""
    # Identity
    PRODUCT_NAME = "PRODUCT_NAME"
    BRAND = "BRAND"
    GENERIC_NAME = "GENERIC_NAME"
    PRODUCT_TYPE = "PRODUCT_TYPE"

    # Quantity & Pricing
    DECLARED_NET_QUANTITY = "DECLARED_NET_QUANTITY"
    MRP = "MRP"

    # Responsible Parties
    MANUFACTURER_NAME = "MANUFACTURER_NAME"
    MANUFACTURER_ADDRESS = "MANUFACTURER_ADDRESS"
    PACKER_NAME = "PACKER_NAME"
    PACKER_ADDRESS = "PACKER_ADDRESS"
    IMPORTER_NAME_ADDRESS = "IMPORTER_NAME_ADDRESS"
    COUNTRY_OF_ORIGIN = "COUNTRY_OF_ORIGIN"

    # Dates
    MANUFACTURE_DATE = "MANUFACTURE_DATE"
    PACKING_DATE = "PACKING_DATE"
    EXPIRY_DATE = "EXPIRY_DATE"
    BEST_BEFORE_USE_BY = "BEST_BEFORE_USE_BY"
    USE_BEFORE_DATE = "USE_BEFORE_DATE"
    MONTH_YEAR_MANUFACTURE = "MONTH_YEAR_MANUFACTURE"

    # Traceability & Consumer Care
    BATCH_NUMBER = "BATCH_NUMBER"
    CONSUMER_CARE = "CONSUMER_CARE"
    BARCODE = "BARCODE"

    # Category-Specific & Composition
    FSSAI_LICENSE = "FSSAI_LICENSE"
    INGREDIENTS_LIST = "INGREDIENTS_LIST"
    NUTRITIONAL_INFO = "NUTRITIONAL_INFO"
    VEG_NONVEG_SYMBOL = "VEG_NONVEG_SYMBOL"


class DeclarationGroup(str, Enum):
    """Functional groupings for declarations."""
    IDENTITY = "IDENTITY"
    QUANTITY = "QUANTITY"
    PRICING = "PRICING"
    RESPONSIBLE_PARTY = "RESPONSIBLE_PARTY"
    ORIGIN = "ORIGIN"
    DATES = "DATES"
    TRACEABILITY = "TRACEABILITY"
    CONSUMER_SUPPORT = "CONSUMER_SUPPORT"
    SAFETY_COMPLIANCE = "SAFETY_COMPLIANCE"
    SPECIFICATION = "SPECIFICATION"


FIELD_TO_GROUP: Dict[str, DeclarationGroup] = {
    CanonicalDeclarationField.PRODUCT_NAME: DeclarationGroup.IDENTITY,
    CanonicalDeclarationField.BRAND: DeclarationGroup.IDENTITY,
    CanonicalDeclarationField.GENERIC_NAME: DeclarationGroup.IDENTITY,
    CanonicalDeclarationField.PRODUCT_TYPE: DeclarationGroup.IDENTITY,
    CanonicalDeclarationField.DECLARED_NET_QUANTITY: DeclarationGroup.QUANTITY,
    CanonicalDeclarationField.MRP: DeclarationGroup.PRICING,
    CanonicalDeclarationField.MANUFACTURER_NAME: DeclarationGroup.RESPONSIBLE_PARTY,
    CanonicalDeclarationField.MANUFACTURER_ADDRESS: DeclarationGroup.RESPONSIBLE_PARTY,
    CanonicalDeclarationField.PACKER_NAME: DeclarationGroup.RESPONSIBLE_PARTY,
    CanonicalDeclarationField.PACKER_ADDRESS: DeclarationGroup.RESPONSIBLE_PARTY,
    CanonicalDeclarationField.IMPORTER_NAME_ADDRESS: DeclarationGroup.RESPONSIBLE_PARTY,
    CanonicalDeclarationField.COUNTRY_OF_ORIGIN: DeclarationGroup.ORIGIN,
    CanonicalDeclarationField.MANUFACTURE_DATE: DeclarationGroup.DATES,
    CanonicalDeclarationField.PACKING_DATE: DeclarationGroup.DATES,
    CanonicalDeclarationField.EXPIRY_DATE: DeclarationGroup.DATES,
    CanonicalDeclarationField.BEST_BEFORE_USE_BY: DeclarationGroup.DATES,
    CanonicalDeclarationField.USE_BEFORE_DATE: DeclarationGroup.DATES,
    CanonicalDeclarationField.MONTH_YEAR_MANUFACTURE: DeclarationGroup.DATES,
    CanonicalDeclarationField.BATCH_NUMBER: DeclarationGroup.TRACEABILITY,
    CanonicalDeclarationField.BARCODE: DeclarationGroup.TRACEABILITY,
    CanonicalDeclarationField.CONSUMER_CARE: DeclarationGroup.CONSUMER_SUPPORT,
    CanonicalDeclarationField.FSSAI_LICENSE: DeclarationGroup.SAFETY_COMPLIANCE,
    CanonicalDeclarationField.INGREDIENTS_LIST: DeclarationGroup.SPECIFICATION,
    CanonicalDeclarationField.NUTRITIONAL_INFO: DeclarationGroup.SPECIFICATION,
    CanonicalDeclarationField.VEG_NONVEG_SYMBOL: DeclarationGroup.SAFETY_COMPLIANCE,
}


class QuantityType(str, Enum):
    """Physical dimension / measurement type under Legal Metrology."""
    MASS = "MASS"
    VOLUME = "VOLUME"
    COUNT = "COUNT"
    LENGTH_AREA = "LENGTH_AREA"


# Standard Legal Metrology units mapping and normalizations
LEGAL_MASS_UNITS: Dict[str, str] = {
    'g': 'g', 'gm': 'g', 'gms': 'g', 'gram': 'g', 'grams': 'g',
    'kg': 'kg', 'kgs': 'kg', 'kilogram': 'kg', 'kilograms': 'kg',
    'mg': 'mg', 'milligram': 'mg', 'milligrams': 'mg',
}

LEGAL_VOLUME_UNITS: Dict[str, str] = {
    'ml': 'ml', 'millilitre': 'ml', 'millilitres': 'ml', 'milliliter': 'ml', 'milliliters': 'ml',
    'l': 'L', 'ltr': 'L', 'litre': 'L', 'litres': 'L', 'liter': 'L', 'liters': 'L',
    'cl': 'cl',
}

LEGAL_COUNT_UNITS: Dict[str, str] = {
    'piece': 'pieces', 'pieces': 'pieces', 'pc': 'pieces', 'pcs': 'pieces', 'units': 'pieces', 'unit': 'pieces',
    'tablet': 'tablets', 'tablets': 'tablets', 'tab': 'tablets', 'tabs': 'tablets',
    'capsule': 'capsules', 'capsules': 'capsules', 'cap': 'capsules', 'caps': 'capsules',
    'n': 'pieces', 'no': 'pieces', 'nos': 'pieces', 'numbers': 'pieces', 'number': 'pieces',
    'wipes': 'pieces', 'wipe': 'pieces', 'sheets': 'pieces', 'sheet': 'pieces',
    'sticks': 'pieces', 'stick': 'pieces', 'rolls': 'pieces', 'roll': 'pieces',
    'pouches': 'pieces', 'pouch': 'pieces', 'sachets': 'pieces', 'sachet': 'pieces',
    'bags': 'pieces', 'bag': 'pieces', 'bars': 'pieces', 'bar': 'pieces',
}

LEGAL_LENGTH_AREA_UNITS: Dict[str, str] = {
    'm': 'm', 'metre': 'm', 'metres': 'm', 'meter': 'm', 'meters': 'm',
    'cm': 'cm', 'centimetre': 'cm', 'centimetres': 'cm', 'centimeter': 'cm', 'centimeters': 'cm',
    'mm': 'mm', 'millimetre': 'mm', 'millimetres': 'mm', 'millimeter': 'mm', 'millimeters': 'mm',
    'sq m': 'sq m', 'sq. m': 'sq m', 'sq cm': 'sq cm', 'sq. cm': 'sq cm',
}

UNIT_TO_QUANTITY_TYPE: Dict[str, QuantityType] = {}
for u in LEGAL_MASS_UNITS:
    UNIT_TO_QUANTITY_TYPE[u.lower()] = QuantityType.MASS
for u in LEGAL_VOLUME_UNITS:
    UNIT_TO_QUANTITY_TYPE[u.lower()] = QuantityType.VOLUME
for u in LEGAL_COUNT_UNITS:
    UNIT_TO_QUANTITY_TYPE[u.lower()] = QuantityType.COUNT
for u in LEGAL_LENGTH_AREA_UNITS:
    UNIT_TO_QUANTITY_TYPE[u.lower()] = QuantityType.LENGTH_AREA


def infer_quantity_type(unit_str: Optional[str]) -> QuantityType:
    """Infer physical QuantityType from unit string, defaulting to MASS if unrecognized."""
    if not unit_str:
        return QuantityType.MASS
    norm_u = unit_str.strip().lower()
    return UNIT_TO_QUANTITY_TYPE.get(norm_u, QuantityType.MASS)


def normalize_unit(unit_str: Optional[str]) -> Tuple[Optional[str], Optional[QuantityType]]:
    """Normalize unit to canonical abbreviation and determine QuantityType."""
    if not unit_str:
        return None, None
    raw_clean = unit_str.strip().lower()
    if raw_clean in LEGAL_MASS_UNITS:
        return LEGAL_MASS_UNITS[raw_clean], QuantityType.MASS
    if raw_clean in LEGAL_VOLUME_UNITS:
        return LEGAL_VOLUME_UNITS[raw_clean], QuantityType.VOLUME
    if raw_clean in LEGAL_COUNT_UNITS:
        return LEGAL_COUNT_UNITS[raw_clean], QuantityType.COUNT
    if raw_clean in LEGAL_LENGTH_AREA_UNITS:
        return LEGAL_LENGTH_AREA_UNITS[raw_clean], QuantityType.LENGTH_AREA
    return raw_clean, None


def build_quantity_candidate(
    qty_val: Optional[Union[str, int, float]],
    raw_unit: Optional[str],
    raw_span: str,
    confidence: float = 0.85,
    semantic_section: str = "DECLARED_QUANTITY",
    relevance: str = "high",
    relevance_score: float = 0.9,
    source_context: str = "",
    source: str = "OCR",
    is_multipack: bool = False,
    pack_count: Optional[int] = None,
    unit_net_quantity: Optional[Union[int, float]] = None,
    declared_expression: Optional[str] = None,
    derived_total_quantity: Optional[Union[int, float]] = None,
    packaging_level: Optional[str] = None,
    candidates: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Construct a canonical quantity candidate dictionary preserving full backwards compatibility
    with existing tests while populating the complete typed quantity and multipack data model.
    """
    norm_unit, qty_type = normalize_unit(raw_unit)
    if qty_type is None and raw_unit:
        qty_type = infer_quantity_type(raw_unit)

    # Multipack handling & derivation
    derived_provenance = None
    if is_multipack:
        if unit_net_quantity is not None and (qty_val is None or str(qty_val).strip() == ""):
            qty_val = unit_net_quantity
        elif qty_val is not None and unit_net_quantity is None:
            try:
                flt_q = float(qty_val)
                unit_net_quantity = int(flt_q) if flt_q.is_integer() else flt_q
            except (ValueError, TypeError):
                pass

        if pack_count is not None:
            try:
                pack_count = int(pack_count)
            except (ValueError, TypeError):
                pass

        if declared_expression is None:
            if pack_count is not None and unit_net_quantity is not None and (norm_unit or raw_unit):
                declared_expression = f"{pack_count} × {unit_net_quantity} {raw_unit or norm_unit}"
            else:
                declared_expression = raw_span

        if derived_total_quantity is None and pack_count is not None and unit_net_quantity is not None:
            try:
                calc_total = float(pack_count) * float(unit_net_quantity)
                derived_total_quantity = int(calc_total) if calc_total.is_integer() else calc_total
            except (ValueError, TypeError):
                pass

        if pack_count is not None and unit_net_quantity is not None:
            derived_provenance = {
                "source": "DERIVED",
                "formula": f"{pack_count} × {unit_net_quantity}",
                "unit": norm_unit or raw_unit,
            }

    quantity_present = qty_val is not None and str(qty_val).strip() != ""
    unit_present = norm_unit is not None and str(norm_unit).strip() != ""

    num_float: Optional[float] = None
    num_val: Optional[Union[int, float]] = None
    num_valid = False

    if quantity_present:
        try:
            num_float = float(qty_val)
            num_val = int(num_float) if num_float.is_integer() else num_float
            num_valid = num_float > 0
            if qty_type == QuantityType.COUNT and not is_multipack:
                # Count declarations must be whole numbers under PCR rules
                num_valid = num_valid and num_float.is_integer()
        except (ValueError, TypeError):
            num_valid = False

    if is_multipack:
        count_valid = pack_count is not None and pack_count > 0
        quantity_unit_valid = bool(count_valid and unit_present and num_valid and norm_unit)
    else:
        quantity_unit_valid = bool(quantity_present and unit_present and num_valid and norm_unit)

    str_val = str(qty_val) if qty_val is not None else None
    if is_multipack:
        display_val = declared_expression or (f"{pack_count} × {str_val} {norm_unit}" if pack_count else raw_span)
    elif quantity_present and unit_present:
        display_val = f"{str_val} {norm_unit}"
    elif quantity_present:
        display_val = str_val or raw_span
    elif unit_present:
        display_val = norm_unit or raw_span
    else:
        display_val = raw_span

    result: Dict[str, Any] = {
        # Canonical & display values (preserves declared expression for multipacks and display values for single units)
        "value": display_val,
        "raw_value": raw_span,
        "raw_text": raw_span,

        # Typed quantity model
        "numeric_value": num_val,
        "normalized_value": num_val,
        "unit": norm_unit,
        "normalized_unit": norm_unit,
        "raw_unit": raw_unit,
        "quantity_type": qty_type.value if qty_type else None,

        # Legacy decomposition fields for rule engine / tests (CRITICAL: COUNT IS NEVER MAPPED TO QUANTITY_VALUE)
        "quantity_value": str_val,
        "quantity_unit": norm_unit,
        "quantity_present": quantity_present,
        "unit_present": unit_present,
        "quantity_unit_valid": quantity_unit_valid,

        # Multipack semantic fields
        "is_multipack": is_multipack,
        "pack_count": pack_count,
        "unit_net_quantity": unit_net_quantity,
        "unit_quantity": unit_net_quantity,  # standard alias
        "declared_expression": declared_expression if is_multipack else None,
        "derived_total_quantity": derived_total_quantity if is_multipack else None,
        "derived_total_provenance": derived_provenance,
        "declared_expression_source": {"source": "OCR", "raw_text": raw_span},
        "packaging_level": packaging_level or ("OUTER_PACKAGE" if is_multipack else "SINGLE_UNIT"),

        # Scoring & provenance
        "confidence": confidence,
        "source": source,
        "semantic_section": semantic_section,
        "relevance": relevance,
        "relevance_score": relevance_score,
        "source_context": source_context,
    }

    if candidates:
        result["candidates"] = candidates

    return result


class DatePrecision(str, Enum):
    FULL_DATE = "FULL_DATE"
    MONTH_YEAR = "MONTH_YEAR"


class ContactType(str, Enum):
    TOLL_FREE = "TOLL_FREE"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    WEBSITE = "WEBSITE"
    POSTAL = "POSTAL"
    CONSUMER_CARE_CELL = "CONSUMER_CARE_CELL"


def build_date_candidate(
    raw_date: str,
    normalized_date: Optional[str] = None,
    norm_val: Optional[str] = None,
    precision: str = DatePrecision.FULL_DATE.value,
    parsed_components: Optional[Dict[str, Any]] = None,
    source_label: Optional[str] = None,
    semantic_type: str = "MANUFACTURE_DATE",
    confidence: float = 0.8,
    source: str = "OCR",
    source_image_id: Optional[int] = None,
    source_image_index: Optional[int] = None,
    bbox: Optional[Any] = None,
) -> Dict[str, Any]:
    """Construct a canonical date candidate preserving raw declaration, precision, and parsed parts."""
    norm_val = normalized_date or norm_val or raw_date
    return {
        "value": raw_date,
        "raw_value": raw_date,
        "raw_date": raw_date,
        "normalized_value": norm_val,
        "normalized_date": norm_val,
        "precision": precision,
        "parsed_components": parsed_components or {},
        "source_label": source_label,
        "semantic_type": semantic_type,
        "evidence": {
            "raw_text": raw_date,
            "label": source_label,
            "precision": precision,
        },
        "confidence": confidence,
        "source": source,
        "source_image_id": source_image_id,
        "source_image_index": source_image_index,
        "bbox": bbox,
    }


def build_consumer_care_candidate(
    value: str,
    raw_text: str,
    contacts: Optional[List[Dict[str, Any]]] = None,
    primary_contact_type: Optional[str] = None,
    primary_contact_value: Optional[str] = None,
    confidence: float = 0.8,
    source: str = "OCR",
    source_image_id: Optional[int] = None,
    source_image_index: Optional[int] = None,
    bbox: Optional[Any] = None,
) -> Dict[str, Any]:
    """Construct a canonical consumer care candidate with structured contact channels."""
    contact_list = contacts or []
    c_type = primary_contact_type
    c_val = primary_contact_value
    if not c_type and contact_list:
        c_type = contact_list[0].get("contact_type")
        c_val = contact_list[0].get("contact_value")

    return {
        "value": value,
        "raw_value": raw_text,
        "raw_text": raw_text,
        "contact_type": c_type,
        "contact_value": c_val,
        "primary_contact_type": c_type,
        "primary_contact_value": c_val,
        "contacts": contact_list,
        "confidence": confidence,
        "source": source,
        "source_image_id": source_image_id,
        "source_image_index": source_image_index,
        "bbox": bbox,
    }


def build_product_name_candidate(
    value: Optional[str],
    raw_text: Optional[str] = None,
    status: str = "VALID",
    competing_candidates: Optional[List[Dict[str, Any]]] = None,
    confidence: float = 0.85,
    source: str = "OCR",
    source_image_id: Optional[int] = None,
    source_image_index: Optional[int] = None,
    bbox: Optional[Any] = None,
    reconciliation_status: Optional[str] = None,
) -> Dict[str, Any]:
    """Construct a canonical product name candidate tracking semantic association and ambiguity."""
    is_ambiguous = status in ("AMBIGUOUS", "REVIEW", "CONFLICTING_EVIDENCE")
    return {
        "value": value,
        "raw_value": raw_text or value,
        "raw_text": raw_text or value,
        "status": status,
        "reconciliation_status": reconciliation_status or ("REVIEW" if is_ambiguous else "CONFIRMED"),
        "is_ambiguous": is_ambiguous,
        "competing_candidates": competing_candidates or [],
        "confidence": confidence,
        "source": source,
        "source_image_id": source_image_id,
        "source_image_index": source_image_index,
        "bbox": bbox,
    }

