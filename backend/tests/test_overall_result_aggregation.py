"""
Test suite for inspection overall result aggregation and physical verification separation.
Verifies the priority logic:
1. Deterministic FAIL -> NON_COMPLIANT
2. Unresolved critical conflict or missing mandatory declaration -> NOT_VERIFIABLE (REQUIRES REVIEW)
3. All image-verifiable requirements pass and remaining unresolved items are physical verification
   or non-blocking visual candidates -> COMPLIANT
"""

import pytest
from app.core.constants import InspectionStatus
from app.rules.rule_engine import (
    derive_overall_result,
    calculate_rule_summary,
    _is_physical_verification_rule,
    _is_uncontradicted_visual_candidate,
    _is_blocking_for_automated_screening,
)


def _build_rule_result(
    rule_id: str,
    parameter: str,
    status: str,
    required: bool = True,
    verification_type: str = "IMAGE_VERIFIABLE",
    evidence_data: dict = None,
    message: str = "",
) -> dict:
    """Helper to construct realistic rule evaluation result dict."""
    return {
        "rule_id": rule_id,
        "parameter": parameter,
        "status": status,
        "required": required,
        "verification_type": verification_type,
        "evidence_data": evidence_data or {},
        "message": message or f"Evaluation outcome for {parameter}: {status}",
        "binary": 1 if status == "PASS" else (0 if status == "FAIL" else 0),
    }


class TestOverallResultAggregation:
    """Test suite covering the 12-case regression matrix for overall screening result aggregation."""

    def test_case_1_all_image_pass_physical_not_verifiable_yields_compliant(self):
        """Case 1: All image-verifiable declarations PASS, physical checks remain NOT_VERIFIABLE.

        Must yield COMPLIANT overall screening result.
        """
        rules = [
            _build_rule_result("PC-ALL-001", "PRODUCT_NAME", "PASS"),
            _build_rule_result("PC-ALL-002", "DECLARED_NET_QUANTITY", "PASS"),
            _build_rule_result("PC-ALL-003", "MRP", "PASS"),
            _build_rule_result("PC-ALL-004", "MANUFACTURER_NAME", "PASS"),
            _build_rule_result("PC-ALL-005", "MANUFACTURER_ADDRESS", "PASS"),
            _build_rule_result("PC-ALL-006", "CONSUMER_CARE", "PASS"),
            _build_rule_result("PC-ALL-007", "MONTH_YEAR_MANUFACTURE", "PASS"),
            _build_rule_result("PC-ALL-008", "COUNTRY_OF_ORIGIN", "PASS"),
            # Physical verification checks:
            _build_rule_result(
                "PC-ALL-012",
                "ACTUAL_NET_CONTENT",
                "NOT_VERIFIABLE",
                verification_type="PHYSICAL_VERIFICATION_REQUIRED",
                message="Physical verification required: actual weight measurement not supplied.",
            ),
            _build_rule_result(
                "PC-ALL-013",
                "FONT_SIZE_COMPLIANCE",
                "NOT_VERIFIABLE",
                verification_type="PHYSICAL_VERIFICATION_REQUIRED",
                message="Physical measurement using calibrated caliper required.",
            ),
        ]

        overall = derive_overall_result(rules)
        assert overall == InspectionStatus.COMPLIANT

        # Verify summary counters still preserve exact count of review items
        summary = calculate_rule_summary(rules)
        assert summary["passed_count"] == 8
        assert summary["review_count"] == 2
        assert summary["failed_count"] == 0
        assert summary["total_rules"] == 10

    def test_case_2_deterministic_fail_yields_non_compliant(self):
        """Case 2: Deterministic FAIL on mandatory declaration (e.g. Missing legal unit)."""
        rules = [
            _build_rule_result("PC-ALL-001", "PRODUCT_NAME", "PASS"),
            _build_rule_result("PC-ALL-002", "DECLARED_NET_QUANTITY", "FAIL", message="Missing unit of measure"),
            _build_rule_result("PC-ALL-003", "MRP", "PASS"),
            _build_rule_result("PC-ALL-012", "ACTUAL_NET_CONTENT", "NOT_VERIFIABLE", verification_type="PHYSICAL_VERIFICATION_REQUIRED"),
            _build_rule_result("PC-ALL-013", "FONT_SIZE_COMPLIANCE", "NOT_VERIFIABLE", verification_type="PHYSICAL_VERIFICATION_REQUIRED"),
        ]

        overall = derive_overall_result(rules)
        assert overall == InspectionStatus.NON_COMPLIANT

    def test_case_3_missing_mandatory_image_declaration_yields_not_verifiable(self):
        """Case 3: Mandatory image-verifiable declaration not detected (e.g., MRP)."""
        rules = [
            _build_rule_result("PC-ALL-001", "PRODUCT_NAME", "PASS"),
            _build_rule_result("PC-ALL-002", "DECLARED_NET_QUANTITY", "PASS"),
            _build_rule_result("PC-ALL-003", "MRP", "NOT_VERIFIABLE", message="Required declaration MRP was not detected"),
            _build_rule_result("PC-ALL-012", "ACTUAL_NET_CONTENT", "NOT_VERIFIABLE", verification_type="PHYSICAL_VERIFICATION_REQUIRED"),
            _build_rule_result("PC-ALL-013", "FONT_SIZE_COMPLIANCE", "NOT_VERIFIABLE", verification_type="PHYSICAL_VERIFICATION_REQUIRED"),
        ]

        overall = derive_overall_result(rules)
        assert overall == InspectionStatus.NOT_VERIFIABLE

    def test_case_4_multi_view_conflict_yields_not_verifiable(self):
        """Case 4: Multi-view conflict on MRP (e.g. Rs 50 vs Rs 55)."""
        rules = [
            _build_rule_result("PC-ALL-001", "PRODUCT_NAME", "PASS"),
            _build_rule_result("PC-ALL-002", "DECLARED_NET_QUANTITY", "PASS"),
            _build_rule_result(
                "PC-ALL-003",
                "MRP",
                "NOT_VERIFIABLE",
                evidence_data={"status": "CONFLICTING_EVIDENCE", "has_conflict": True, "values": ["50", "55"]},
                message="Conflicting evidence detected across package views",
            ),
            _build_rule_result("PC-ALL-012", "ACTUAL_NET_CONTENT", "NOT_VERIFIABLE", verification_type="PHYSICAL_VERIFICATION_REQUIRED"),
        ]

        overall = derive_overall_result(rules)
        assert overall == InspectionStatus.NOT_VERIFIABLE

    def test_case_5_edible_food_with_visual_candidate_veg_yields_compliant(self):
        """Case 5: Edible food package with visual candidate VEG (no conflict) and physical checks.

        Overall screening result must be COMPLIANT.
        """
        rules = [
            _build_rule_result("PC-ALL-001", "PRODUCT_NAME", "PASS"),
            _build_rule_result("PC-ALL-002", "DECLARED_NET_QUANTITY", "PASS"),
            _build_rule_result("PC-ALL-003", "MRP", "PASS"),
            _build_rule_result("PC-FOOD-001", "FSSAI_LICENSE", "PASS"),
            _build_rule_result("PC-FOOD-002", "INGREDIENTS_LIST", "PASS"),
            _build_rule_result("PC-FOOD-003", "NUTRITIONAL_INFO", "PASS"),
            # Veg symbol detected visually as candidate
            _build_rule_result(
                "PC-FOOD-005",
                "VEG_NONVEG_SYMBOL",
                "NOT_VERIFIABLE",
                evidence_data={
                    "value": "VEG",
                    "symbol_type": "VEGETARIAN",
                    "status": "CANDIDATE",
                    "is_candidate": True,
                    "has_conflict": False,
                    "source": "VISUAL_DETECTION",
                },
                message="Visual candidate detected: VEGETARIAN",
            ),
            _build_rule_result("PC-ALL-012", "ACTUAL_NET_CONTENT", "NOT_VERIFIABLE", verification_type="PHYSICAL_VERIFICATION_REQUIRED"),
            _build_rule_result("PC-ALL-013", "FONT_SIZE_COMPLIANCE", "NOT_VERIFIABLE", verification_type="PHYSICAL_VERIFICATION_REQUIRED"),
        ]

        overall = derive_overall_result(rules)
        assert overall == InspectionStatus.COMPLIANT

    def test_case_6_edible_food_with_conflicting_symbols_yields_not_verifiable(self):
        """Case 6: Food package with conflicting visual symbols (VEG on panel 1, NON_VEG on panel 2)."""
        rules = [
            _build_rule_result("PC-ALL-001", "PRODUCT_NAME", "PASS"),
            _build_rule_result("PC-FOOD-001", "FSSAI_LICENSE", "PASS"),
            _build_rule_result(
                "PC-FOOD-005",
                "VEG_NONVEG_SYMBOL",
                "NOT_VERIFIABLE",
                evidence_data={
                    "status": "CONFLICTING_EVIDENCE",
                    "has_conflict": True,
                    "symbol_type": "CONFLICTING_SYMBOLS",
                    "values": ["VEGETARIAN", "NON_VEGETARIAN"],
                },
                message="Contradictory food symbols detected across views",
            ),
        ]

        overall = derive_overall_result(rules)
        assert overall == InspectionStatus.NOT_VERIFIABLE

    def test_case_7_food_package_with_missing_mandatory_veg_symbol_yields_not_verifiable(self):
        """Case 7: Food package where mandatory VEG_NONVEG_SYMBOL was not detected at all."""
        rules = [
            _build_rule_result("PC-ALL-001", "PRODUCT_NAME", "PASS"),
            _build_rule_result("PC-ALL-002", "DECLARED_NET_QUANTITY", "PASS"),
            _build_rule_result("PC-FOOD-001", "FSSAI_LICENSE", "PASS"),
            _build_rule_result(
                "PC-FOOD-005",
                "VEG_NONVEG_SYMBOL",
                "NOT_VERIFIABLE",
                evidence_data=None,
                message="Symbol or indicator for Vegetarian/Non-Vegetarian not detected.",
            ),
        ]

        overall = derive_overall_result(rules)
        assert overall == InspectionStatus.NOT_VERIFIABLE

    def test_case_8_non_food_package_veg_not_applicable_yields_compliant(self):
        """Case 8: Non-food commodity (e.g. Soap / Detergent) where VEG_NONVEG_SYMBOL is NOT_APPLICABLE."""
        rules = [
            _build_rule_result("PC-ALL-001", "PRODUCT_NAME", "PASS"),
            _build_rule_result("PC-ALL-002", "DECLARED_NET_QUANTITY", "PASS"),
            _build_rule_result("PC-ALL-003", "MRP", "PASS"),
            _build_rule_result("PC-ALL-004", "MANUFACTURER_NAME", "PASS"),
            _build_rule_result("PC-FOOD-005", "VEG_NONVEG_SYMBOL", "NOT_APPLICABLE", required=False),
            _build_rule_result("PC-ALL-012", "ACTUAL_NET_CONTENT", "NOT_VERIFIABLE", verification_type="PHYSICAL_VERIFICATION_REQUIRED"),
            _build_rule_result("PC-ALL-013", "FONT_SIZE_COMPLIANCE", "NOT_VERIFIABLE", verification_type="PHYSICAL_VERIFICATION_REQUIRED"),
        ]

        overall = derive_overall_result(rules)
        assert overall == InspectionStatus.COMPLIANT

    def test_case_9_physical_weight_supplied_and_passes_yields_compliant(self):
        """Case 9: Inspector supplies physical weight measurement and it satisfies declared quantity."""
        rules = [
            _build_rule_result("PC-ALL-001", "PRODUCT_NAME", "PASS"),
            _build_rule_result("PC-ALL-002", "DECLARED_NET_QUANTITY", "PASS"),
            _build_rule_result("PC-ALL-012", "ACTUAL_NET_CONTENT", "PASS", message="Actual weight 502g satisfies declared 500g"),
            _build_rule_result("PC-ALL-013", "FONT_SIZE_COMPLIANCE", "NOT_VERIFIABLE", verification_type="PHYSICAL_VERIFICATION_REQUIRED"),
        ]

        overall = derive_overall_result(rules)
        assert overall == InspectionStatus.COMPLIANT

    def test_case_10_physical_weight_supplied_and_fails_yields_non_compliant(self):
        """Case 10: Inspector supplies physical weight measurement and it FAILS (underweight package)."""
        rules = [
            _build_rule_result("PC-ALL-001", "PRODUCT_NAME", "PASS"),
            _build_rule_result("PC-ALL-002", "DECLARED_NET_QUANTITY", "PASS"),
            _build_rule_result("PC-ALL-012", "ACTUAL_NET_CONTENT", "FAIL", message="Actual weight 420g is below declared 500g"),
            _build_rule_result("PC-ALL-013", "FONT_SIZE_COMPLIANCE", "NOT_VERIFIABLE", verification_type="PHYSICAL_VERIFICATION_REQUIRED"),
        ]

        overall = derive_overall_result(rules)
        assert overall == InspectionStatus.NON_COMPLIANT

    def test_case_11_physical_font_size_supplied_and_fails_yields_non_compliant(self):
        """Case 11: Inspector supplies caliper font measurement and it fails statutory minimum height."""
        rules = [
            _build_rule_result("PC-ALL-001", "PRODUCT_NAME", "PASS"),
            _build_rule_result("PC-ALL-002", "DECLARED_NET_QUANTITY", "PASS"),
            _build_rule_result("PC-ALL-012", "ACTUAL_NET_CONTENT", "NOT_VERIFIABLE", verification_type="PHYSICAL_VERIFICATION_REQUIRED"),
            _build_rule_result("PC-ALL-013", "FONT_SIZE_COMPLIANCE", "FAIL", message="Font height 1.2mm is below required 2.0mm"),
        ]

        overall = derive_overall_result(rules)
        assert overall == InspectionStatus.NON_COMPLIANT

    def test_case_12_low_ocr_confidence_yields_not_verifiable(self):
        """Case 12: Mandatory declaration has low OCR confidence below threshold."""
        rules = [
            _build_rule_result("PC-ALL-001", "PRODUCT_NAME", "PASS"),
            _build_rule_result("PC-ALL-002", "DECLARED_NET_QUANTITY", "NOT_VERIFIABLE", message="Low OCR confidence (0.42)"),
            _build_rule_result("PC-ALL-003", "MRP", "PASS"),
            _build_rule_result("PC-ALL-012", "ACTUAL_NET_CONTENT", "NOT_VERIFIABLE", verification_type="PHYSICAL_VERIFICATION_REQUIRED"),
        ]

        overall = derive_overall_result(rules)
        assert overall == InspectionStatus.NOT_VERIFIABLE

    def test_rule_summary_always_sums_to_total(self):
        """Verify calculate_rule_summary preserves exact count equality."""
        rules = [
            _build_rule_result("R1", "P1", "PASS"),
            _build_rule_result("R2", "P2", "PASS"),
            _build_rule_result("R3", "P3", "FAIL"),
            _build_rule_result("R4", "P4", "NOT_VERIFIABLE"),
            _build_rule_result("R5", "P5", "NOT_VERIFIABLE"),
            _build_rule_result("R6", "P6", "NOT_APPLICABLE"),
        ]

        summary = calculate_rule_summary(rules)
        assert summary["passed_count"] == 2
        assert summary["failed_count"] == 1
        assert summary["review_count"] == 2
        assert summary["not_applicable_count"] == 1
        assert summary["total_rules"] == 6
        assert (
            summary["passed_count"]
            + summary["failed_count"]
            + summary["review_count"]
            + summary["not_applicable_count"]
            == summary["total_rules"]
        )
