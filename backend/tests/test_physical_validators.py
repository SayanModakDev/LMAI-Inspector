"""
Comprehensive unit and integration tests for Legal Metrology physical measurement validators:
- PHYSICAL_WEIGHT_CHECK (Rule PC-ALL-012: Net content verification under Rule 14 & Second Schedule MPE)
- FONT_SIZE_CHECK (Rule PC-ALL-013: Rule 7(3) Table-I/II minimum numeral and letter height)

Validates all 10 requirements:
1. Weight check with no measurement -> NOT_VERIFIABLE
2. Weight check with adequate measured quantity -> PASS
3. Weight check with proven deficiency outside tolerance -> FAIL
4. Unit conversion cases where already supported (g <-> kg, ml <-> L)
5. Font-size check with no calibration -> NOT_VERIFIABLE
6. Font-size check with valid calibrated measurement meeting threshold -> PASS
7. Font-size check with calibrated undersized measurement -> FAIL
8. Neither validator produces "Unknown validation method" warning
9. Gemini/LLM output cannot directly force either validator to PASS
10. Full RuleEngine evaluation of PC-ALL-012 and PC-ALL-013 is safe and non-blocking
"""

import logging
import pytest
from app.rules.validators import (
    calculate_maximum_permissible_error,
    dispatch_validator,
    validate_physical_weight,
    validate_font_size,
    VALIDATOR_REGISTRY,
    DEFAULT_PARAMETER_VALIDATION_METHODS,
)
from app.rules.rule_engine import evaluate_rules, derive_overall_result
from app.core.constants import InspectionStatus


# ---------------------------------------------------------------------------
# Test 1: Weight check with no measurement -> NOT_VERIFIABLE
# ---------------------------------------------------------------------------
def test_1_weight_check_with_no_measurement_returns_not_verifiable():
    rule = {
        "rule_id": "PC-ALL-012",
        "parameter": "ACTUAL_NET_CONTENT",
        "validation_method": "PHYSICAL_WEIGHT_CHECK",
        "required": False,
    }
    all_fields = {
        "DECLARED_NET_QUANTITY": {"value": "500 g", "numeric_value": 500, "unit": "g"}
    }

    # Case A: None evidence
    res_none = dispatch_validator("PHYSICAL_WEIGHT_CHECK", None, rule, all_fields)
    assert res_none.status == "NOT_VERIFIABLE"
    assert res_none.binary == 0
    assert "Physical net content verification requires direct gravimetric" in res_none.reason

    # Case B: Empty evidence dict
    res_empty = dispatch_validator("PHYSICAL_WEIGHT_CHECK", {}, rule, all_fields)
    assert res_empty.status == "NOT_VERIFIABLE"
    assert res_empty.binary == 0


# ---------------------------------------------------------------------------
# Test 2: Weight check with adequate measured quantity -> PASS
# ---------------------------------------------------------------------------
def test_2_weight_check_with_adequate_measured_quantity_passes():
    rule = {
        "rule_id": "PC-ALL-012",
        "parameter": "ACTUAL_NET_CONTENT",
        "validation_method": "PHYSICAL_WEIGHT_CHECK",
    }
    all_fields = {
        "DECLARED_NET_QUANTITY": {"value": "500 g", "numeric_value": 500, "unit": "g"}
    }

    # Case A: Measured weight exceeds declared (502g vs 500g)
    evidence_502 = {
        "measured_weight": 502,
        "measured_unit": "g",
        "source": "CALIBRATED_SCALE",
        "is_physical_measurement": True,
    }
    res_502 = dispatch_validator("PHYSICAL_WEIGHT_CHECK", evidence_502, rule, all_fields)
    assert res_502.status == "PASS"
    assert res_502.binary == 1
    assert "satisfies declared 500g" in res_502.reason
    assert res_502.evidence["applicable_tolerance_mpe"] == 15.0
    assert res_502.evidence["minimum_allowable_quantity"] == 485.0

    # Case B: Measured weight is slightly below declared but within MPE tolerance (490g vs 500g, MPE=15g, min=485g)
    evidence_490 = {
        "measured_weight": 490,
        "measured_unit": "g",
        "source": "SCALE",
        "is_physical_measurement": True,
    }
    res_490 = dispatch_validator("PHYSICAL_WEIGHT_CHECK", evidence_490, rule, all_fields)
    assert res_490.status == "PASS"
    assert res_490.binary == 1
    assert "within maximum permissible error tolerance" in res_490.reason


# ---------------------------------------------------------------------------
# Test 3: Weight check with proven deficiency outside tolerance -> FAIL
# ---------------------------------------------------------------------------
def test_3_weight_check_with_deficiency_outside_tolerance_fails():
    rule = {
        "rule_id": "PC-ALL-012",
        "parameter": "ACTUAL_NET_CONTENT",
        "validation_method": "PHYSICAL_WEIGHT_CHECK",
    }
    all_fields = {
        "DECLARED_NET_QUANTITY": {"value": "500 g", "numeric_value": 500, "unit": "g"}
    }

    # 420g is below declared 500g by 80g; MPE is 15g, min allowable is 485g
    evidence_420 = {
        "measured_weight": 420,
        "measured_unit": "g",
        "source": "CALIBRATED_SCALE",
        "is_physical_measurement": True,
    }
    res_420 = dispatch_validator("PHYSICAL_WEIGHT_CHECK", evidence_420, rule, all_fields)
    assert res_420.status == "FAIL"
    assert res_420.binary == 0
    assert "Actual weight 420g is below declared 500g" in res_420.reason
    assert "exceeding maximum permissible error of 15g" in res_420.reason
    assert res_420.evidence["deficiency"] == 80.0


# ---------------------------------------------------------------------------
# Test 4: Unit conversion cases where already supported
# ---------------------------------------------------------------------------
def test_4_unit_conversions():
    rule = {
        "rule_id": "PC-ALL-012",
        "parameter": "ACTUAL_NET_CONTENT",
        "validation_method": "PHYSICAL_WEIGHT_CHECK",
    }

    # Case A: Declared in kg (1 kg = 1000g), measured in g (995g, MPE for 1000g is 15g, min=985g -> PASS)
    all_fields_kg = {
        "DECLARED_NET_QUANTITY": {"value": "1 kg", "numeric_value": 1, "unit": "kg"}
    }
    ev_995g = {
        "measured_weight": 995,
        "measured_unit": "g",
        "is_physical_measurement": True,
    }
    res_kg_pass = dispatch_validator("PHYSICAL_WEIGHT_CHECK", ev_995g, rule, all_fields_kg)
    assert res_kg_pass.status == "PASS"
    assert res_kg_pass.binary == 1
    assert res_kg_pass.evidence["declared_base_quantity"] == 1000.0
    assert res_kg_pass.evidence["measured_base_quantity"] == 995.0

    # Case B: Declared in kg (1 kg = 1000g), measured in g (950g < 985g -> FAIL)
    ev_950g = {
        "measured_weight": 950,
        "measured_unit": "g",
        "is_physical_measurement": True,
    }
    res_kg_fail = dispatch_validator("PHYSICAL_WEIGHT_CHECK", ev_950g, rule, all_fields_kg)
    assert res_kg_fail.status == "FAIL"
    assert res_kg_fail.binary == 0
    assert "Actual weight 950g is below declared 1000g" in res_kg_fail.reason

    # Case C: Declared in g (500g), measured in kg (0.502 kg = 502g -> PASS)
    all_fields_g = {
        "DECLARED_NET_QUANTITY": {"value": "500 g", "numeric_value": 500, "unit": "g"}
    }
    ev_0502kg = {
        "measured_weight": 0.502,
        "measured_unit": "kg",
        "is_physical_measurement": True,
    }
    res_g_pass = dispatch_validator("PHYSICAL_WEIGHT_CHECK", ev_0502kg, rule, all_fields_g)
    assert res_g_pass.status == "PASS"
    assert res_g_pass.binary == 1
    assert res_g_pass.evidence["measured_base_quantity"] == 502.0

    # Case D: Volume conversion: Declared 1 L (= 1000ml), measured 990 ml -> PASS
    all_fields_vol = {
        "DECLARED_NET_QUANTITY": {"value": "1 L", "numeric_value": 1, "unit": "L"}
    }
    ev_990ml = {
        "measured_quantity": 990,
        "measured_unit": "ml",
        "is_physical_measurement": True,
    }
    res_vol_pass = dispatch_validator("PHYSICAL_WEIGHT_CHECK", ev_990ml, rule, all_fields_vol)
    assert res_vol_pass.status == "PASS"
    assert res_vol_pass.binary == 1

    # Case E: Volume conversion: Declared 1 L (= 1000ml), measured 950 ml -> FAIL
    ev_950ml = {
        "measured_quantity": 950,
        "measured_unit": "ml",
        "is_physical_measurement": True,
    }
    res_vol_fail = dispatch_validator("PHYSICAL_WEIGHT_CHECK", ev_950ml, rule, all_fields_vol)
    assert res_vol_fail.status == "FAIL"
    assert res_vol_fail.binary == 0


# ---------------------------------------------------------------------------
# Test 5: Font-size check with no calibration -> NOT_VERIFIABLE
# ---------------------------------------------------------------------------
def test_5_font_size_check_with_no_calibration_returns_not_verifiable():
    rule = {
        "rule_id": "PC-ALL-013",
        "parameter": "FONT_SIZE_COMPLIANCE",
        "validation_method": "FONT_SIZE_CHECK",
    }
    all_fields = {
        "DECLARED_NET_QUANTITY": {"value": "200 g", "numeric_value": 200, "unit": "g"}
    }

    # Case A: None evidence
    res_none = dispatch_validator("FONT_SIZE_CHECK", None, rule, all_fields)
    assert res_none.status == "NOT_VERIFIABLE"
    assert res_none.binary == 0
    assert "calibrated gauge or caliper under Rule 7 Table-I/II required" in res_none.reason

    # Case B: Raw uncalibrated OCR bounding box pixel height
    ev_bbox_pixels = {
        "pixel_height": 28,
        "bbox": [10, 20, 100, 48],
        "source": "OCR",
    }
    res_bbox = dispatch_validator("FONT_SIZE_CHECK", ev_bbox_pixels, rule, all_fields)
    assert res_bbox.status == "NOT_VERIFIABLE"
    assert res_bbox.binary == 0
    assert "Ordinary OCR bounding box pixel height cannot be interpreted as physical millimetres" in res_bbox.reason

    # Case C: Uncalibrated visual candidate
    ev_uncal = {
        "value": "2.5 mm",
        "is_calibrated": False,
        "source": "OCR",
    }
    res_uncal = dispatch_validator("FONT_SIZE_CHECK", ev_uncal, rule, all_fields)
    assert res_uncal.status == "NOT_VERIFIABLE"
    assert res_uncal.binary == 0


# ---------------------------------------------------------------------------
# Test 6: Font-size check with valid calibrated measurement meeting threshold -> PASS
# ---------------------------------------------------------------------------
def test_6_font_size_check_with_valid_calibrated_meeting_threshold_passes():
    rule = {
        "rule_id": "PC-ALL-013",
        "parameter": "FONT_SIZE_COMPLIANCE",
        "validation_method": "FONT_SIZE_CHECK",
    }
    # For declared 200g, Table-I statutory requirement is 2.0mm
    all_fields = {
        "DECLARED_NET_QUANTITY": {"value": "200 g", "numeric_value": 200, "unit": "g"}
    }

    ev_calibrated = {
        "measured_height_mm": 2.5,
        "is_calibrated": True,
        "source": "CALIPER",
    }
    res = dispatch_validator("FONT_SIZE_CHECK", ev_calibrated, rule, all_fields)
    assert res.status == "PASS"
    assert res.binary == 1
    assert "satisfies statutory minimum 2mm under Rule 7(3)" in res.reason
    assert res.evidence["measured_height_mm"] == 2.5
    assert res.evidence["required_height_mm"] == 2.0


# ---------------------------------------------------------------------------
# Test 7: Font-size check with calibrated undersized measurement -> FAIL
# ---------------------------------------------------------------------------
def test_7_font_size_check_with_calibrated_undersized_fails():
    rule = {
        "rule_id": "PC-ALL-013",
        "parameter": "FONT_SIZE_COMPLIANCE",
        "validation_method": "FONT_SIZE_CHECK",
    }
    # For declared 200g, Table-I statutory requirement is 2.0mm
    all_fields = {
        "DECLARED_NET_QUANTITY": {"value": "200 g", "numeric_value": 200, "unit": "g"}
    }

    # 1.2mm is below required 2.0mm
    ev_undersized = {
        "measured_height_mm": 1.2,
        "is_calibrated": True,
        "source": "CALIPER",
    }
    res = dispatch_validator("FONT_SIZE_CHECK", ev_undersized, rule, all_fields)
    assert res.status == "FAIL"
    assert res.binary == 0
    assert "Font height 1.2mm is below required 2mm under Rule 7(3)" in res.reason


# ---------------------------------------------------------------------------
# Test 8: Neither validator produces "Unknown validation method"
# ---------------------------------------------------------------------------
def test_8_neither_validator_produces_unknown_validation_method_warning(caplog):
    assert "PHYSICAL_WEIGHT_CHECK" in VALIDATOR_REGISTRY
    assert "FONT_SIZE_CHECK" in VALIDATOR_REGISTRY
    assert DEFAULT_PARAMETER_VALIDATION_METHODS["ACTUAL_NET_CONTENT"] == "PHYSICAL_WEIGHT_CHECK"
    assert DEFAULT_PARAMETER_VALIDATION_METHODS["FONT_SIZE_COMPLIANCE"] == "FONT_SIZE_CHECK"

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        res_weight = dispatch_validator(
            "PHYSICAL_WEIGHT_CHECK",
            None,
            {"rule_id": "PC-ALL-012", "parameter": "ACTUAL_NET_CONTENT"},
            {},
        )
        res_font = dispatch_validator(
            "FONT_SIZE_CHECK",
            None,
            {"rule_id": "PC-ALL-013", "parameter": "FONT_SIZE_COMPLIANCE"},
            {},
        )

    # Verify no "Unknown validation method" warnings in logs
    unknown_warnings = [rec.message for rec in caplog.records if "Unknown validation method" in rec.message]
    assert len(unknown_warnings) == 0, f"Expected 0 unknown validation method warnings, found: {unknown_warnings}"
    assert res_weight.status == "NOT_VERIFIABLE"
    assert res_font.status == "NOT_VERIFIABLE"


# ---------------------------------------------------------------------------
# Test 9: Gemini output cannot directly force either validator to PASS
# ---------------------------------------------------------------------------
def test_9_gemini_output_cannot_directly_force_pass():
    rule_weight = {
        "rule_id": "PC-ALL-012",
        "parameter": "ACTUAL_NET_CONTENT",
        "validation_method": "PHYSICAL_WEIGHT_CHECK",
    }
    rule_font = {
        "rule_id": "PC-ALL-013",
        "parameter": "FONT_SIZE_COMPLIANCE",
        "validation_method": "FONT_SIZE_CHECK",
    }
    all_fields = {
        "DECLARED_NET_QUANTITY": {"value": "500 g", "numeric_value": 500, "unit": "g"}
    }

    # Gemini claiming to have weighed the package
    ev_gemini_weight = {
        "measured_weight": 500,
        "measured_unit": "g",
        "source": "GEMINI",
    }
    res_gemini_w = dispatch_validator("PHYSICAL_WEIGHT_CHECK", ev_gemini_weight, rule_weight, all_fields)
    assert res_gemini_w.status == "NOT_VERIFIABLE"
    assert res_gemini_w.binary == 0
    assert "Physical weight cannot be inferred from OCR, Gemini" in res_gemini_w.reason

    # Gemini claiming font height
    ev_gemini_font = {
        "measured_height_mm": 3.0,
        "is_calibrated": True,
        "source": "GEMINI",
    }
    res_gemini_f = dispatch_validator("FONT_SIZE_CHECK", ev_gemini_font, rule_font, all_fields)
    assert res_gemini_f.status == "NOT_VERIFIABLE"
    assert res_gemini_f.binary == 0
    assert "Font size compliance cannot be determined by Gemini" in res_gemini_f.reason

    # AI hallucination via image inference flag
    ev_inferred = {
        "measured_weight": 500,
        "measured_unit": "g",
        "inferred_from_image": True,
        "source": "VISUAL_DETECTION",
    }
    res_inferred = dispatch_validator("PHYSICAL_WEIGHT_CHECK", ev_inferred, rule_weight, all_fields)
    assert res_inferred.status == "NOT_VERIFIABLE"


# ---------------------------------------------------------------------------
# Test 10: Full RuleEngine integration with PC-ALL-012 and PC-ALL-013
# ---------------------------------------------------------------------------
def test_10_rule_engine_integration_pc_all_012_and_013():
    """Verify evaluation of PC-ALL-012 and PC-ALL-013 in evaluate_rules without warnings."""
    import json
    with open("data/rule_matrix.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    all_rules = data.get("rules", [])

    extracted_fields = {
        "PRODUCT_NAME": {"value": "Organic Green Tea", "status": "VALID"},
        "DECLARED_NET_QUANTITY": {"value": "500 g", "numeric_value": 500, "unit": "g", "status": "VALID"},
        "MRP": {"value": "₹250.00", "numeric_value": 250.0, "unit": "INR", "status": "VALID"},
    }

    # Evaluate rules
    results, overall = evaluate_rules(all_rules, extracted_fields)

    by_id = {r["rule_id"]: r for r in results}
    assert "PC-ALL-012" in by_id
    assert "PC-ALL-013" in by_id

    r_012 = by_id["PC-ALL-012"]
    r_013 = by_id["PC-ALL-013"]

    # Active software-only screening records both rules in a separate scope.
    assert r_012["status"] == "OUT_OF_SCOPE_PHYSICAL_VERIFICATION"
    assert r_013["status"] == "OUT_OF_SCOPE_PHYSICAL_VERIFICATION"
    assert r_012["status"] != "NOT_APPLICABLE"
    assert r_013["status"] != "NOT_APPLICABLE"
    assert "Unknown validation method" not in r_012["message"]
    assert "Unknown validation method" not in r_013["message"]

    # In standard automated scan, physical checks do not block overall compliance
    # (they are non-blocking physical verification requirements)
    assert overall in (InspectionStatus.COMPLIANT, InspectionStatus.REVIEW_REQUIRED)

    # Now provide physical scale measurement in extracted_fields
    extracted_fields_with_scale = dict(extracted_fields)
    extracted_fields_with_scale["ACTUAL_NET_CONTENT"] = {
        "measured_weight": 502,
        "measured_unit": "g",
        "source": "CALIBRATED_SCALE",
        "is_physical_measurement": True,
    }
    results_scale, overall_scale = evaluate_rules(
        all_rules,
        extracted_fields_with_scale,
        include_physical_verification=True,
    )
    by_id_scale = {r["rule_id"]: r for r in results_scale}
    assert by_id_scale["PC-ALL-012"]["status"] == "PASS"
    assert by_id_scale["PC-ALL-012"]["binary"] == 1
    assert "satisfies declared 500g" in by_id_scale["PC-ALL-012"]["message"]
