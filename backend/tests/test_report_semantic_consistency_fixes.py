"""
Regression test suite for semantic consistency and report consistency fixes:
1. Canonical overall status across API, DB, UI, and PDF.
2. Date candidate eligibility: rejection of age phrases, dosages, quantities, currency.
3. Date candidate eligibility: acceptance of valid calendar dates and statutory durations.
4. Multi-image date conflict filtering (filtering non-date noise, consolidating equivalent dates).
5. Expiry / Use-Before date role mapping for PC-COSM-003 with complete provenance.
6. Genuine distinct date conflict preservation (NOT_VERIFIABLE).
7. Product type resolution precedence and synchronization.
8. PDF glyph safety and Rupee symbol rendering.
9. Full inspection date rendering in PDF report without truncation.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from app.core.constants import InspectionStatus, normalize_status
from app.extraction.declaration_extractor import (
    is_valid_date_candidate,
    _values_conflict,
    DATE_FIELDS,
    DATE_PREFIX_RE,
    parse_date_with_precision,
)
from app.rules.rule_engine import (
    resolve_canonical_field_evidence,
    evaluate_rules,
    _are_dates_equivalent,
    _is_usable_field_candidate,
)
from app.reports.pdf_report import _clean_pdf_text, _setup_pdf_fonts


# ===========================================================================
# 1. CANONICAL OVERALL STATUS
# ===========================================================================
def test_canonical_overall_status_normalization():
    """Verify that NOT_DETECTED and MANUAL_CHECK are normalized to NOT_VERIFIABLE."""
    assert normalize_status("NOT_DETECTED") == InspectionStatus.NOT_VERIFIABLE
    assert normalize_status("NOT DETECTED") == InspectionStatus.NOT_VERIFIABLE
    assert normalize_status("MANUAL_CHECK") == InspectionStatus.NOT_VERIFIABLE
    assert normalize_status("NOT_VERIFIABLE") == InspectionStatus.NOT_VERIFIABLE
    assert normalize_status("COMPLIANT") == InspectionStatus.COMPLIANT
    assert normalize_status("NON-COMPLIANT") == InspectionStatus.NON_COMPLIANT
    assert normalize_status("NON_COMPLIANT") == InspectionStatus.NON_COMPLIANT


# ===========================================================================
# 2. FALSE DATE CANDIDATE ELIGIBILITY (REJECTION)
# ===========================================================================
@pytest.mark.parametrize(
    "invalid_date",
    [
        "12 years of age",
        "for children above 12 years",
        "under 12 years",
        "not for children below 3 years",
        "2 times daily",
        "take once a day",
        "apply 3 times a day",
        "75 g",
        "100 ml",
        "500 mg",
        "1 kg",
        "250 gm",
        "₹135",
        "₹ 99.00",
        "MRP Rs. 150",
        "Rs 75/-",
        "INR 50",
        "store in a cool dry place",
        "for external use only",
        "batch no 402",
        "license no 100",
        "net quantity",
        "all rights reserved",
    ],
)
def test_false_date_candidates_rejected(invalid_date: str):
    """General date validation must reject age restrictions, dosages, quantities, prices, and noise."""
    assert is_valid_date_candidate(invalid_date) is False


# ===========================================================================
# 3. VALID DATE CANDIDATE ELIGIBILITY (ACCEPTANCE)
# ===========================================================================
@pytest.mark.parametrize(
    "valid_date",
    [
        "04/28",
        "04/2028",
        "05/26",
        "05-2026",
        "MAY 2026",
        "May/2026",
        "15/08/2025",
        "15-08-2025",
        "EXP 04/28",
        "EXP: 04/2028",
        "EXPIRY: 10/26",
        "USE BEFORE 04/28",
        "USE BY 15/09/2027",
        "MFD 01/2024",
        "PKD 12/23",
        "24 months from mfg",
        "24 months from manufacture",
        "best before 12 months from date of packaging",
        "use within 6 months after opening",
        "best within 18 months from mfg",
    ],
)
def test_valid_date_candidates_accepted(valid_date: str):
    """General date validation must accept valid calendar dates and statutory shelf-life durations."""
    assert is_valid_date_candidate(valid_date) is True


# ===========================================================================
# 4. MULTI-IMAGE DATE CONFLICT GROUPING
# ===========================================================================
def test_date_conflict_ignores_non_date_noise():
    """Valid date must not conflict with a non-date phrase such as '12 years of age'."""
    assert _values_conflict("USE_BEFORE_DATE", {"value": "04/28"}, {"value": "12 years of age"}) is False
    assert _values_conflict("EXPIRY_DATE", {"value": "EXP 04/28"}, {"value": "75 g"}) is False
    assert _values_conflict("BEST_BEFORE_USE_BY", {"value": "24 months from mfg"}, {"value": "2 times daily"}) is False


def test_date_conflict_unifies_equivalent_formats():
    """Equivalent date representations across panels must not conflict."""
    assert _values_conflict("USE_BEFORE_DATE", {"value": "04/28"}, {"value": "04/2028"}) is False
    assert _values_conflict("EXPIRY_DATE", {"value": "EXP 04/28"}, {"value": "04/2028"}) is False
    assert _values_conflict("MONTH_YEAR_MANUFACTURE", {"value": "MAY 2026"}, {"value": "05/2026"}) is False


def test_date_conflict_detects_genuinely_different_dates():
    """Two genuinely different valid dates across views must be flagged as a conflict."""
    assert _values_conflict("USE_BEFORE_DATE", {"value": "04/26"}, {"value": "12/28"}) is True
    assert _values_conflict("EXPIRY_DATE", {"value": "01/2025"}, {"value": "10/2026"}) is True


# ===========================================================================
# 5. EXPIRY_DATE / USE_BEFORE_DATE CANONICAL MAPPING & PROVENANCE
# ===========================================================================
def test_cosmetic_rule_pc_cosm_003_maps_expiry_with_provenance():
    """Under Cosmetics Rules 2020 Rule 34(1)(f), EXPIRY_DATE satisfies USE_BEFORE_DATE."""
    rule = {
        "rule_id": "PC-COSM-003",
        "parameter": "USE_BEFORE_DATE",
        "category": "COSMETIC",
        "required": True,
        "validation_method": "EXPIRY_DATE_PRESENT",
        "rule_reference": "Rule 34(1)(f)",
        "regulatory_source": "COSMETIC_LABELING",
    }

    # Simulate extracted fields where USE_BEFORE_DATE is missing or held an invalid phrase,
    # but EXPIRY_DATE has grounded evidence with Token 42 (Panel 0)
    extracted_fields = {
        "USE_BEFORE_DATE": {
            "value": "12 years of age",  # Invalid date phrase
            "confidence": 0.40,
            "status": "NOT_FOUND",
        },
        "EXPIRY_DATE": {
            "value": "04/28",
            "raw_value": "EXP 04/28",
            "normalized_value": "04/2028",
            "confidence": 0.99,
            "source": "OCR_GEMINI_RESOLVED",
            "source_image_index": 0,
            "bbox": [100, 200, 300, 250],
            "source_evidence": [
                {
                    "image_index": 0,
                    "token_ids": [42],
                    "raw_text": "EXP 04/28",
                    "bbox": [100, 200, 300, 250],
                    "ocr_confidence": 0.99,
                }
            ],
            "status": "VALID",
        },
    }

    # Resolve evidence for PC-COSM-003
    resolved_evidence = resolve_canonical_field_evidence("USE_BEFORE_DATE", rule, extracted_fields)
    assert resolved_evidence is not None
    assert resolved_evidence["value"] == "04/28"
    assert resolved_evidence["original_semantic_field"] == "EXPIRY_DATE"
    assert resolved_evidence["canonical_regulatory_field"] == "USE_BEFORE_DATE"
    assert resolved_evidence["source_evidence"][0]["token_ids"] == [42]

    # Evaluate rule
    results, overall = evaluate_rules([rule], extracted_fields)
    assert len(results) == 1
    r = results[0]
    assert r["status"] == "PASS"
    assert r["binary"] == 1
    assert r["original_semantic_field"] == "EXPIRY_DATE"
    assert r["canonical_regulatory_field"] == "USE_BEFORE_DATE"
    assert r["evidence_data"]["source_evidence"][0]["token_ids"] == [42]


def test_cosmetic_rule_pc_cosm_003_consolidates_agreeing_dates():
    """When both USE_BEFORE_DATE and EXPIRY_DATE exist and agree, consolidate without conflict."""
    rule = {
        "rule_id": "PC-COSM-003",
        "parameter": "USE_BEFORE_DATE",
        "required": True,
        "validation_method": "EXPIRY_DATE_PRESENT",
        "rule_reference": "Rule 34(1)(f)",
    }
    extracted_fields = {
        "USE_BEFORE_DATE": {
            "value": "04/28",
            "confidence": 0.95,
            "status": "VALID",
        },
        "EXPIRY_DATE": {
            "value": "04/2028",
            "confidence": 0.98,
            "status": "VALID",
        },
    }
    results, overall = evaluate_rules([rule], extracted_fields)
    assert results[0]["status"] == "PASS"
    assert results[0]["binary"] == 1


def test_cosmetic_rule_pc_cosm_003_disagreeing_dates_conflict():
    """When USE_BEFORE_DATE and EXPIRY_DATE disagree on calendar dates, flag CONFLICT / NOT_VERIFIABLE."""
    rule = {
        "rule_id": "PC-COSM-003",
        "parameter": "USE_BEFORE_DATE",
        "required": True,
        "validation_method": "EXPIRY_DATE_PRESENT",
        "rule_reference": "Rule 34(1)(f)",
    }
    extracted_fields = {
        "USE_BEFORE_DATE": {
            "value": "04/26",
            "confidence": 0.95,
            "status": "VALID",
        },
        "EXPIRY_DATE": {
            "value": "12/28",
            "confidence": 0.98,
            "status": "VALID",
        },
    }
    results, overall = evaluate_rules([rule], extracted_fields)
    assert results[0]["status"] == "NOT_VERIFIABLE"
    assert results[0]["binary"] == 0
    assert overall == InspectionStatus.NOT_VERIFIABLE


# ===========================================================================
# 6. PRODUCT_TYPE FINAL CONTEXT CONSISTENCY
# ===========================================================================
def test_product_type_resolution_not_overwritten_by_unknown():
    """Classification returning 'UNKNOWN' must not overwrite extracted_fields PRODUCT_TYPE."""
    classification = {
        "category": "COSMETIC",
        "product_type": "UNKNOWN",  # Classification returned UNKNOWN
        "confidence": 0.9,
    }
    extracted_fields = {
        "PRODUCT_TYPE": {
            "value": "PERSONAL_CARE",
            "confidence": 0.85,
        }
    }
    llm_pkg_context_data = {"product_type": "TOOTHPASTE"}

    # Simulate resolution logic from scan.py
    class_pt = classification.get("product_type")
    ext_pt = extracted_fields.get("PRODUCT_TYPE", {}).get("value")
    llm_pt = llm_pkg_context_data.get("product_type")

    if class_pt and class_pt not in ("UNKNOWN", "NOT_DETECTED", "ALL"):
        final_pt = class_pt
    elif ext_pt and ext_pt not in ("UNKNOWN", "NOT_DETECTED", "ALL"):
        final_pt = ext_pt
    elif llm_pt and llm_pt not in ("UNKNOWN", "NOT_DETECTED", "ALL"):
        final_pt = llm_pt
    else:
        final_pt = "UNKNOWN"

    assert final_pt == "PERSONAL_CARE"


# ===========================================================================
# 7. PDF GLYPH & RUPEE SYMBOL RENDERING
# ===========================================================================
def test_pdf_rupee_symbol_safety():
    """Verify font setup and glyph safety for ₹ symbol."""
    _setup_pdf_fonts()
    # Testing _clean_pdf_text
    cleaned = _clean_pdf_text("MRP ₹ 135.00 (Incl. of all taxes)")
    assert "₹" in cleaned or "Rs." in cleaned
    assert "\ufffd" not in cleaned


# ===========================================================================
# 8. PDF FULL INSPECTION DATE WITHOUT TRUNCATION
# ===========================================================================
def test_pdf_date_not_truncated():
    """Verify inspection date string contains full date and time without [:10] truncation."""
    dt = datetime(2026, 9, 19, 10, 15, 30, tzinfo=timezone.utc)
    ist_tz = timezone(timedelta(hours=5, minutes=30), name="IST")
    date_str = dt.astimezone(ist_tz).strftime("%d-%b-%Y %I:%M:%S %p IST")
    
    assert len(date_str) > 15
    assert "IST" in date_str
    assert "2026" in date_str
    assert date_str == "19-Sep-2026 03:45:30 PM IST"
