"""
Unit tests for the deterministic validator-dispatch architecture in backend/app/rules/validators.py.
"""

import pytest
from app.rules.validators import (
    dispatch_validator,
    validate_text_present,
    validate_value_and_unit_present,
    validate_mrp_present,
    validate_manufacturer_present,
    validate_address_present,
    validate_importer_present,
    validate_date_present,
    validate_best_before_present,
    validate_expiry_date_present,
    validate_consumer_care_present,
    validate_fssai_number_present,
    validate_batch_number_present,
    validate_ingredients_present,
    validate_physical_weight_check,
    validate_font_size_check,
    validate_veg_nonveg_present,
    ValidationResult,
)
from app.rules.rule_engine import evaluate_rules


# ---------------------------------------------------------------------------
# TEXT_PRESENT
# ---------------------------------------------------------------------------
def test_text_present_valid():
    rule = {"rule_id": "PC-ALL-001", "parameter": "PRODUCT_NAME", "required": True}
    evidence = {"value": "Tata Salt Vacuum Evaporated", "confidence": 0.85}
    res = validate_text_present(evidence, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1
    assert "Tata Salt" in res.reason
    assert res.normalized_value == "Tata Salt Vacuum Evaporated"


def test_text_present_placeholder_fails():
    rule = {"rule_id": "PC-ALL-001", "parameter": "PRODUCT_NAME", "required": True}
    evidence = {"value": "N/A", "confidence": 0.9}
    res = validate_text_present(evidence, rule, {})

    assert res.status == "FAIL"
    assert res.binary == 0
    assert "placeholder" in res.reason.lower()


def test_text_present_missing_is_not_verifiable():
    rule = {"rule_id": "PC-ALL-001", "parameter": "PRODUCT_NAME", "required": True}
    res = validate_text_present(None, rule, {})

    assert res.status == "NOT_VERIFIABLE"
    assert res.binary == 0


def test_text_present_optional_missing_is_not_applicable():
    rule = {"rule_id": "PC-ALL-010", "parameter": "GENERIC_NAME", "required": False}
    res = validate_text_present(None, rule, {})

    assert res.status == "NOT_APPLICABLE"
    assert res.binary is None


# ---------------------------------------------------------------------------
# VALUE_AND_UNIT_PRESENT
# ---------------------------------------------------------------------------
def test_value_and_unit_present_valid_grams():
    rule = {"rule_id": "PC-ALL-002", "parameter": "DECLARED_NET_QUANTITY", "required": True}
    evidence = {
        "value": "500 g",
        "quantity_value": "500",
        "quantity_unit": "g",
        "confidence": 0.88,
    }
    res = validate_value_and_unit_present(evidence, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1
    assert res.normalized_value == "500 g"


def test_value_and_unit_present_extracts_from_raw_string():
    rule = {"rule_id": "PC-ALL-002", "parameter": "DECLARED_NET_QUANTITY", "required": True}
    evidence = {"value": "Net Wt. 1.5 kg", "confidence": 0.85}
    res = validate_value_and_unit_present(evidence, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1
    assert res.normalized_value == "1.5 kg"


def test_value_and_unit_present_missing_unit_fails():
    rule = {"rule_id": "PC-ALL-002", "parameter": "DECLARED_NET_QUANTITY", "required": True}
    evidence = {"value": "500", "confidence": 0.9}
    res = validate_value_and_unit_present(evidence, rule, {})

    assert res.status == "FAIL"
    assert res.binary == 0
    assert "unit" in res.reason.lower()


def test_value_and_unit_present_negative_or_zero_fails():
    rule = {"rule_id": "PC-ALL-002", "parameter": "DECLARED_NET_QUANTITY", "required": True}
    evidence = {"value": "0 g", "quantity_value": "0", "quantity_unit": "g", "confidence": 0.9}
    res = validate_value_and_unit_present(evidence, rule, {})

    assert res.status == "FAIL"
    assert res.binary == 0
    assert "positive" in res.reason.lower()


def test_value_and_unit_present_unrecognized_unit_fails():
    rule = {"rule_id": "PC-ALL-002", "parameter": "DECLARED_NET_QUANTITY", "required": True}
    evidence = {"value": "100 bushels", "quantity_value": "100", "quantity_unit": "bushels", "confidence": 0.9}
    res = validate_value_and_unit_present(evidence, rule, {})

    assert res.status == "FAIL"
    assert res.binary == 0
    assert "not a recognized legal unit" in res.reason.lower()


# ---------------------------------------------------------------------------
# MRP_PRESENT
# ---------------------------------------------------------------------------
def test_mrp_present_valid():
    rule = {"rule_id": "PC-ALL-003", "parameter": "MRP", "required": True}
    evidence = {"value": "₹199.00", "confidence": 0.92}
    res = validate_mrp_present(evidence, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1
    assert res.normalized_value == "₹199.00"


def test_mrp_present_zero_fails():
    rule = {"rule_id": "PC-ALL-003", "parameter": "MRP", "required": True}
    evidence = {"value": "Rs. 0.00", "confidence": 0.9}
    res = validate_mrp_present(evidence, rule, {})

    assert res.status == "FAIL"
    assert res.binary == 0
    assert "positive" in res.reason.lower()


def test_mrp_present_non_numeric_fails():
    rule = {"rule_id": "PC-ALL-003", "parameter": "MRP", "required": True}
    evidence = {"value": "MRP: Free Sample", "confidence": 0.9}
    res = validate_mrp_present(evidence, rule, {})

    assert res.status == "FAIL"
    assert res.binary == 0


# ---------------------------------------------------------------------------
# MANUFACTURER_PRESENT & ADDRESS_PRESENT
# ---------------------------------------------------------------------------
def test_manufacturer_present_valid():
    rule = {"rule_id": "PC-ALL-004", "parameter": "MANUFACTURER_NAME", "required": True}
    evidence = {"value": "Manufactured by: Shree Foods Pvt Ltd", "confidence": 0.8}
    res = validate_manufacturer_present(evidence, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1
    assert res.normalized_value == "Shree Foods Pvt Ltd"


def test_manufacturer_present_empty_name_fails():
    rule = {"rule_id": "PC-ALL-004", "parameter": "MANUFACTURER_NAME", "required": True}
    evidence = {"value": "Manufactured by:", "confidence": 0.8}
    res = validate_manufacturer_present(evidence, rule, {})

    assert res.status == "FAIL"
    assert res.binary == 0
    assert "lacks a valid manufacturer" in res.reason.lower()


def test_address_present_valid():
    rule = {"rule_id": "PC-ALL-005", "parameter": "MANUFACTURER_ADDRESS", "required": True}
    evidence = {"value": "Plot 12, Industrial Area, Delhi 110001", "confidence": 0.8}
    res = validate_address_present(evidence, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1


def test_address_present_too_short_fails():
    rule = {"rule_id": "PC-ALL-005", "parameter": "MANUFACTURER_ADDRESS", "required": True}
    evidence = {"value": "ND", "confidence": 0.8}
    res = validate_address_present(evidence, rule, {})

    assert res.status == "FAIL"
    assert res.binary == 0


# ---------------------------------------------------------------------------
# IMPORTER_PRESENT
# ---------------------------------------------------------------------------
def test_importer_present_valid():
    rule = {"rule_id": "PC-ALL-007", "parameter": "IMPORTER_NAME_ADDRESS", "required": True}
    evidence = {"value": "Imported by: Global Imports Ltd, Mumbai 400001", "confidence": 0.8}
    res = validate_importer_present(evidence, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1


# ---------------------------------------------------------------------------
# DATE-RELATED VALIDATION
# ---------------------------------------------------------------------------
def test_date_present_valid_numeric_mm_yyyy():
    rule = {"rule_id": "PC-ALL-009", "parameter": "MONTH_YEAR_MANUFACTURE", "required": True}
    evidence = {"value": "10/2025", "confidence": 0.85}
    res = validate_date_present(evidence, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1
    assert res.normalized_value == "10/2025"


def test_date_present_valid_month_name():
    rule = {"rule_id": "PC-ALL-009", "parameter": "MONTH_YEAR_MANUFACTURE", "required": True}
    evidence = {"value": "JUL/26", "confidence": 0.85}
    res = validate_date_present(evidence, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1
    assert res.normalized_value == "JUL/26"


def test_date_present_decimal_noise_fails():
    rule = {"rule_id": "PC-ALL-009", "parameter": "MONTH_YEAR_MANUFACTURE", "required": True}
    evidence = {"value": "0.73", "confidence": 0.9}
    res = validate_date_present(evidence, rule, {})

    assert res.status == "FAIL"
    assert res.binary == 0
    assert "not a valid date" in res.reason.lower()


def test_date_present_invalid_month_fails():
    rule = {"rule_id": "PC-ALL-009", "parameter": "MONTH_YEAR_MANUFACTURE", "required": True}
    evidence = {"value": "15/2025", "confidence": 0.9}
    res = validate_date_present(evidence, rule, {})

    assert res.status == "FAIL"
    assert res.binary == 0


def test_best_before_valid_date_and_duration():
    rule = {"rule_id": "PC-FOOD-001", "parameter": "BEST_BEFORE_USE_BY", "required": True}

    res_date = validate_best_before_present({"value": "30/08/2027", "confidence": 0.8}, rule, {})
    assert res_date.status == "PASS"

    res_duration = validate_best_before_present({"value": "24 months from mfg", "confidence": 0.8}, rule, {})
    assert res_duration.status == "PASS"


def test_expiry_date_valid():
    rule = {"rule_id": "PC-COSM-003", "parameter": "USE_BEFORE_DATE", "required": True}
    res = validate_expiry_date_present({"value": "JUN/28", "confidence": 0.8}, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1


# ---------------------------------------------------------------------------
# CONSUMER_CARE_PRESENT
# ---------------------------------------------------------------------------
def test_consumer_care_with_phone_passes():
    rule = {"rule_id": "PC-ALL-008", "parameter": "CONSUMER_CARE", "required": True}
    evidence = {"value": "Toll Free Helpline: 1800-123-4567", "confidence": 0.85}
    res = validate_consumer_care_present(evidence, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1
    assert "toll-free" in res.reason.lower()


def test_consumer_care_with_email_passes():
    rule = {"rule_id": "PC-ALL-008", "parameter": "CONSUMER_CARE", "required": True}
    evidence = {"value": "Write to consumer support at care@company.com", "confidence": 0.85}
    res = validate_consumer_care_present(evidence, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1
    assert "email" in res.reason.lower()


def test_consumer_care_lacking_contact_channel_fails():
    rule = {"rule_id": "PC-ALL-008", "parameter": "CONSUMER_CARE", "required": True}
    evidence = {"value": "For complaints please contact customer care department", "confidence": 0.85}
    res = validate_consumer_care_present(evidence, rule, {})

    assert res.status == "FAIL"
    assert res.binary == 0
    assert "lacks a valid contact channel" in res.reason.lower()


# ---------------------------------------------------------------------------
# FSSAI_NUMBER_PRESENT
# ---------------------------------------------------------------------------
def test_fssai_number_valid_14_digits():
    rule = {"rule_id": "PC-FOOD-004", "parameter": "FSSAI_LICENSE", "required": True}
    evidence = {"value": "12345678901234", "confidence": 0.9}
    res = validate_fssai_number_present(evidence, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1
    assert res.normalized_value == "12345678901234"


def test_fssai_number_invalid_length_fails():
    rule = {"rule_id": "PC-FOOD-004", "parameter": "FSSAI_LICENSE", "required": True}
    evidence = {"value": "12345", "confidence": 0.9}
    res = validate_fssai_number_present(evidence, rule, {})

    assert res.status == "FAIL"
    assert res.binary == 0
    assert "10-14 digits" in res.reason.lower()


# ---------------------------------------------------------------------------
# BATCH_NUMBER_PRESENT & INGREDIENTS_PRESENT
# ---------------------------------------------------------------------------
def test_batch_number_valid():
    rule = {"rule_id": "PC-COSM-001", "parameter": "BATCH_NUMBER", "required": True}
    res = validate_batch_number_present({"value": "TS-26A", "confidence": 0.8}, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1


def test_ingredients_present_valid():
    rule = {"rule_id": "PC-FOOD-002", "parameter": "INGREDIENTS_LIST", "required": True}
    res = validate_ingredients_present({"value": "Ingredients: Wheat flour, sugar, edible oil", "confidence": 0.8}, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1


# ---------------------------------------------------------------------------
# PHYSICAL VERIFICATION HANDLING
# ---------------------------------------------------------------------------
def test_physical_weight_check_without_physical_data_is_not_verifiable():
    rule = {"rule_id": "PC-ALL-012", "parameter": "ACTUAL_NET_CONTENT", "required": True}
    res = validate_physical_weight_check(None, rule, {})

    assert res.status == "NOT_VERIFIABLE"
    assert res.binary == 0
    assert "physical measurement data has not been provided" in res.reason.lower()


def test_physical_weight_check_with_physical_data_evaluates_against_declared():
    rule = {"rule_id": "PC-ALL-012", "parameter": "ACTUAL_NET_CONTENT", "required": True}
    all_fields = {
        "DECLARED_NET_QUANTITY": {"quantity_value": "500", "quantity_unit": "g"},
    }

    # Pass case (502g actual >= 500g declared)
    res_pass = validate_physical_weight_check(
        {"value": "502 g", "source": "PHYSICAL_MEASUREMENT"},
        rule,
        all_fields,
    )
    assert res_pass.status == "PASS"
    assert res_pass.binary == 1

    # Fail case (450g actual < 500g declared beyond permissible error)
    res_fail = validate_physical_weight_check(
        {"value": "450 g", "source": "PHYSICAL_MEASUREMENT"},
        rule,
        all_fields,
    )
    assert res_fail.status == "FAIL"
    assert res_fail.binary == 0


def test_font_size_check_without_data_is_not_verifiable():
    rule = {"rule_id": "PC-ALL-013", "parameter": "FONT_SIZE_COMPLIANCE", "required": True}
    res = validate_font_size_check(None, rule, {})

    assert res.status == "NOT_VERIFIABLE"
    assert res.binary == 0


def test_font_size_check_with_data_passes_or_fails():
    rule = {"rule_id": "PC-ALL-013", "parameter": "FONT_SIZE_COMPLIANCE", "min_font_height_mm": 2.0}

    res_pass = validate_font_size_check({"value": "2.5 mm", "source": "MANUAL_MEASUREMENT"}, rule, {})
    assert res_pass.status == "PASS"

    res_fail = validate_font_size_check({"value": "1.2 mm", "source": "MANUAL_MEASUREMENT"}, rule, {})
    assert res_fail.status == "FAIL"


# ---------------------------------------------------------------------------
# VEG_NONVEG_PRESENT
# ---------------------------------------------------------------------------
def test_veg_nonveg_present_detected():
    rule = {"rule_id": "PC-FOOD-005", "parameter": "VEG_NONVEG_SYMBOL", "required": True}
    res = validate_veg_nonveg_present({"value": "Vegetarian logo detected", "confidence": 0.75}, rule, {})

    assert res.status == "PASS"
    assert res.binary == 1
    assert res.normalized_value == "VEG"


# ---------------------------------------------------------------------------
# DISPATCHER & SAFETY CHECKS
# ---------------------------------------------------------------------------
def test_unknown_validation_method_fails_safely_as_not_verifiable():
    rule = {
        "rule_id": "CUSTOM-001",
        "parameter": "CUSTOM_FIELD",
        "validation_method": "NON_EXISTENT_VALIDATION_METHOD",
        "required": True,
    }
    evidence = {"value": "Some text", "confidence": 0.9}

    res = dispatch_validator("NON_EXISTENT_VALIDATION_METHOD", evidence, rule, {})

    assert res.status == "NOT_VERIFIABLE"
    assert res.binary == 0
    assert "unknown validation method" in res.reason.lower()
    assert res.status != "PASS"  # NEVER silently passes


def test_clearly_invalid_flag_produces_fail():
    rule = {"rule_id": "PC-ALL-003", "parameter": "MRP", "required": True}
    evidence = {
        "value": "₹50",
        "confidence": 0.9,
        "clearly_invalid": True,
        "failure_reason": "Price tag was tampered with",
    }
    res = dispatch_validator("MRP_PRESENT", evidence, rule, {})

    assert res.status == "FAIL"
    assert res.binary == 0
    assert "tampered" in res.reason.lower()


def test_weak_ocr_confidence_is_not_verifiable():
    rule = {"rule_id": "PC-ALL-001", "parameter": "PRODUCT_NAME", "required": True}
    evidence = {"value": "Tata Tea", "confidence": 0.4}
    res = dispatch_validator("TEXT_PRESENT", evidence, rule, {})

    assert res.status == "NOT_VERIFIABLE"
    assert res.binary == 0
    assert "confidence" in res.reason.lower()


# ---------------------------------------------------------------------------
# INTEGRATION: evaluate_rules with structured results
# ---------------------------------------------------------------------------
def test_evaluate_rules_returns_structured_validation_result():
    applicable_rules = [
        {
            "rule_id": "PC-ALL-002",
            "parameter": "DECLARED_NET_QUANTITY",
            "validation_method": "VALUE_AND_UNIT_PRESENT",
            "required": True,
        },
        {
            "rule_id": "PC-ALL-003",
            "parameter": "MRP",
            "validation_method": "MRP_PRESENT",
            "required": True,
        },
    ]
    extracted_fields = {
        "DECLARED_NET_QUANTITY": {"value": "1 kg", "quantity_value": "1", "quantity_unit": "kg", "confidence": 0.9},
        "MRP": {"value": "₹0.00", "confidence": 0.9},  # Invalid MRP (zero)
    }

    results, overall = evaluate_rules(applicable_rules, extracted_fields)

    assert overall == "NON-COMPLIANT"
    assert results[0]["status"] == "PASS"
    assert results[1]["status"] == "FAIL"

    # Verify structured validation_result attachment
    assert "validation_result" in results[0]
    assert results[0]["validation_result"]["status"] == "PASS"
    assert results[0]["validation_result"]["binary"] == 1
    assert results[0]["validation_result"]["normalized_value"] == "1 kg"

    assert "validation_result" in results[1]
    assert results[1]["validation_result"]["status"] == "FAIL"
    assert results[1]["validation_result"]["binary"] == 0
