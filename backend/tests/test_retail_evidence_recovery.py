"""
Comprehensive Test Suite for Retail Evidence Recovery and Numeric Semantic Isolation.

Tests cover:
- TEST A: Numeric Semantic Isolation (Net Quantity vs MRP amounts and nutrition zero quantities)
- TEST B: MRP Ambiguity Elimination (single visible MRP candidate is never flagged as ambiguous or competing)
- TEST C: Multi-Image Evidence Agreement (agreeing MRP prices merge as CONFIRMED_SAME without conflict)
- TEST D: Manufacturer Name Recovery on Dense Panels (entity suffixes like Pvt Ltd, LLP, Industries, Agro, etc.)
- TEST E: Manufacturer Address Isolation (address lines terminate before dates, batch numbers, consumer care)
- TEST F: Date Label Abbreviations Recovery (mfg dt, pkd dt, month/year of mfg, etc.)
- TEST G: Multi-Format Date Semantic Agreement (03/2026 vs MAR 2026)
- TEST H: Dense Back-Panel Spatial OCR Line Grouping
- TEST I: Explicit Evidence Availability States on Candidates and Evaluated Rules
- TEST J: Dispatch Validator False Ambiguity Resolution
- TEST K: Regulatory Matrix Traceability and Invariance
- TEST L: End-to-End Retail Evidence Pipeline Verification
"""

import pytest
from typing import Dict, Any

from app.core.ontology import QuantityCandidateType
from app.extraction.evidence_model import EvidenceAvailabilityState
from app.extraction.declaration_extractor import (
    extract_declarations,
    group_ocr_items_into_lines,
    _extract_date_near_keyword,
    MFG_DATE_KEYWORDS,
    PACKING_DATE_KEYWORDS,
    _values_conflict,
    merge_extracted_fields,
)
from app.rules.rule_engine import evaluate_rules
from app.rules.validators import dispatch_validator, ValidationResult


class TestRetailEvidenceRecovery:
    """Test suite validating all 7 retail evidence recovery and numeric semantic isolation requirements."""

    def test_a_numeric_semantic_isolation_quantity_vs_mrp(self):
        """TEST A: Ensure DECLARED_NET_QUANTITY does not conflict with MRP amounts or nutrition zeros."""
        raw_text = (
            "Nutritional Information per 100g:\n"
            "Total Sugars: 0 g\n"
            "Trans Fat: 0 g\n"
            "Net Qty: 200 g\n"
            "MRP Rs. 32.00 (Incl. of all taxes)\n"
            "Batch No: B1234\n"
        )
        fields = extract_declarations(raw_text)

        assert "DECLARED_NET_QUANTITY" in fields
        qty_field = fields["DECLARED_NET_QUANTITY"]
        assert qty_field.get("quantity_value") == "200"
        assert qty_field.get("quantity_unit") == "g"
        assert qty_field.get("has_conflict") is not True
        assert qty_field.get("status") != "CONFLICTING_EVIDENCE"
        assert qty_field.get("candidate_type") == QuantityCandidateType.PACKAGE_QUANTITY.value

        # Ignored nutrition zeros should be logged as irrelevant
        ignored = qty_field.get("ignored_candidates", [])
        assert any(c.get("candidate_type") == QuantityCandidateType.NUTRITIONAL_QUANTITY.value for c in ignored)

        # MRP field should be cleanly isolated
        assert "MRP" in fields
        assert "32.00" in fields["MRP"].get("value", "")
        assert fields["MRP"].get("currency_status") == "VERIFIED"

    def test_b_mrp_single_candidate_never_ambiguous_or_competing(self):
        """TEST B: MRP with a single detected candidate must validate cleanly and not say 'ambiguous or competing'."""
        evidence = {
            "value": "₹32.00",
            "amount": "32.00",
            "currency": "INR",
            "raw_text": "MRP Rs. 32.00",
            "status": "VALID",
            "confidence": 0.90,
            "has_conflict": False,
            "is_ambiguous": False,
            "competing_candidates": [{"value": "₹32.00"}],
            "evidence_state": EvidenceAvailabilityState.EVIDENCE_VERIFIED.value,
        }
        rule = {
            "rule_id": "LMPC_MRP_DECLARATION",
            "parameter": "MRP",
            "package_type": "RETAIL",
            "validation_method": "MRP_PRESENT",
            "required": True,
        }
        val_result = dispatch_validator(
            validation_method="MRP_PRESENT",
            evidence=evidence,
            rule=rule,
            all_fields={"MRP": evidence},
        )
        assert val_result.status == "PASS"
        assert "Ambiguous or competing" not in val_result.reason
        assert val_result.evidence_state == EvidenceAvailabilityState.EVIDENCE_VERIFIED.value

    def test_c_multi_image_mrp_agreement_merges_without_conflict(self):
        """TEST C: Multi-image OCR with identical price values merges as CONFIRMED_SAME without conflict."""
        image1_fields = {
            "MRP": {
                "value": "32.00",
                "currency": "INR",
                "confidence": 0.88,
                "source": "OCR",
                "source_image_index": 0,
            }
        }
        image2_fields = {
            "MRP": {
                "value": "32.00",
                "currency": "INR",
                "confidence": 0.92,
                "source": "OCR",
                "source_image_index": 1,
            }
        }
        merged = merge_extracted_fields([image1_fields, image2_fields])

        assert "MRP" in merged
        mrp_merged = merged["MRP"]
        assert mrp_merged.get("value") == "32.00"
        assert mrp_merged.get("has_conflict") is False
        assert mrp_merged.get("is_ambiguous") is False
        assert mrp_merged.get("multi_image_agreement") == "CONFIRMED_SAME"
        assert mrp_merged.get("evidence_state") == EvidenceAvailabilityState.EVIDENCE_VERIFIED.value

    def test_d_manufacturer_name_recovery_on_dense_panel(self):
        """TEST D: Detect corporate entities with diverse legal suffixes on dense text."""
        panel_text = (
            "Manufactured by:\n"
            "National Agro & Spice Mills LLP\n"
            "Plot 88, Food Park Phase 2, Sonipat, Haryana 131001\n"
            "Net Weight: 500 g\n"
            "MRP: Rs. 140.00\n"
        )
        fields = extract_declarations(panel_text)

        assert "MANUFACTURER_NAME" in fields
        mfg_name = fields["MANUFACTURER_NAME"].get("value", "")
        assert "National Agro & Spice Mills LLP" in mfg_name
        assert fields["MANUFACTURER_NAME"].get("evidence_state") == EvidenceAvailabilityState.EVIDENCE_VERIFIED.value

    def test_e_manufacturer_address_isolation_from_trailing_fields(self):
        """TEST E: Manufacturer address terminates cleanly before batch, date, and other declaration sections."""
        raw_text = (
            "Manufactured by:\n"
            "Apex Consumer Products Pvt Ltd\n"
            "Survey 42/3, Taluka Haveli, Industrial Estate, Pune, Maharashtra 411014\n"
            "Batch No: AP-909\n"
            "Mfg Dt: 02/2026\n"
            "Net Qty: 1 kg\n"
        )
        fields = extract_declarations(raw_text)

        assert "MANUFACTURER_ADDRESS" in fields
        mfg_addr = fields["MANUFACTURER_ADDRESS"].get("value", "")
        assert "Pune, Maharashtra 411014" in mfg_addr
        # Crucial: Batch, Mfg Dt, and Net Qty must NOT be absorbed into address
        assert "Batch" not in mfg_addr
        assert "AP-909" not in mfg_addr
        assert "Mfg Dt" not in mfg_addr
        assert "Net Qty" not in mfg_addr

    def test_f_date_abbreviations_recovery(self):
        """TEST F: Recognize date abbreviations such as 'mfg dt', 'pkd dt', 'month/year of mfg'."""
        text_mfg = "Crispy Snacks\nMfg Dt: 04/2026\nMRP Rs 20"
        fields_mfg = extract_declarations(text_mfg)
        assert "MONTH_YEAR_MANUFACTURE" in fields_mfg or "MANUFACTURE_DATE" in fields_mfg
        mfg_val = (fields_mfg.get("MONTH_YEAR_MANUFACTURE") or fields_mfg.get("MANUFACTURE_DATE", {})).get("value")
        assert "04/2026" in str(mfg_val)

        text_pkd = "Organic Pulses\nPkd Dt.: 12/2025\nNet Qty: 1 kg"
        fields_pkd = extract_declarations(text_pkd)
        assert "PACKING_DATE" in fields_pkd
        pkd_val = fields_pkd["PACKING_DATE"].get("value")
        assert "12/2025" in str(pkd_val)

    def test_g_multi_format_date_semantic_agreement(self):
        """TEST G: Date normalization ensures agreeing representations (03/2026 vs MAR 2026) do not conflict."""
        lines = [
            "Mfg Date: 03/2026",
            "Mfg Date: MAR 2026",
        ]
        extracted = _extract_date_near_keyword("", MFG_DATE_KEYWORDS, lines=lines)
        assert extracted is not None
        assert "2026" in extracted

        # Conflict check should report false for identical normalized dates
        c1 = {"value": "03/2026", "normalized_value": "2026-03"}
        c2 = {"value": "MAR 2026", "normalized_value": "2026-03"}
        assert not _values_conflict("MANUFACTURE_DATE", c1, c2)

    def test_h_dense_back_panel_spatial_line_grouping(self):
        """TEST H: Group word-level OCR bounding boxes into structured lines."""
        ocr_items = [
            {"text": "Net", "bbox": [100, 200, 150, 220], "confidence": 0.95},
            {"text": "Qty:", "bbox": [155, 201, 190, 221], "confidence": 0.95},
            {"text": "100", "bbox": [195, 202, 230, 220], "confidence": 0.96},
            {"text": "g", "bbox": [235, 200, 250, 221], "confidence": 0.97},
            {"text": "MRP", "bbox": [100, 250, 140, 270], "confidence": 0.94},
            {"text": "Rs.", "bbox": [145, 249, 170, 270], "confidence": 0.94},
            {"text": "50.00", "bbox": [175, 250, 220, 271], "confidence": 0.95},
        ]
        grouped_lines = group_ocr_items_into_lines(ocr_items)
        assert len(grouped_lines) == 2
        assert "Net Qty: 100 g" in grouped_lines[0]
        assert "MRP Rs. 50.00" in grouped_lines[1]

        # Ensure declarations extract directly from these spatial items
        fields = extract_declarations("", ocr_items=ocr_items)
        assert "DECLARED_NET_QUANTITY" in fields
        assert fields["DECLARED_NET_QUANTITY"]["quantity_value"] == "100"
        assert fields["DECLARED_NET_QUANTITY"]["quantity_unit"] == "g"
        assert "MRP" in fields
        assert "50.00" in fields["MRP"]["value"]

    def test_i_explicit_evidence_availability_states(self):
        """TEST I: Verification of all 5 explicit evidence availability states."""
        # 1. EVIDENCE_VERIFIED
        res_v = ValidationResult(
            status="PASS",
            binary=1,
            reason="Verified compliant",
            evidence={"value": "500 g", "evidence_state": EvidenceAvailabilityState.EVIDENCE_VERIFIED.value},
            evidence_state=EvidenceAvailabilityState.EVIDENCE_VERIFIED.value,
        )
        assert res_v.to_dict()["evidence_state"] == "EVIDENCE_VERIFIED"

        # 2. EVIDENCE_NOT_DETECTED
        res_nd = ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason="Not found",
            evidence=None,
            evidence_state=EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value,
        )
        assert res_nd.to_dict()["evidence_state"] == "EVIDENCE_NOT_DETECTED"

        # 3. EVIDENCE_CONFLICTING
        res_c = ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason="Conflict between 100g and 200g",
            evidence_state=EvidenceAvailabilityState.EVIDENCE_CONFLICTING.value,
        )
        assert res_c.to_dict()["evidence_state"] == "EVIDENCE_CONFLICTING"

        # 4. EVIDENCE_LOW_CONFIDENCE
        res_lc = ValidationResult(
            status="NOT_VERIFIABLE",
            binary=0,
            reason="Confidence 0.45",
            evidence_state=EvidenceAvailabilityState.EVIDENCE_LOW_CONFIDENCE.value,
        )
        assert res_lc.to_dict()["evidence_state"] == "EVIDENCE_LOW_CONFIDENCE"

        # 5. EVIDENCE_DETECTED_UNASSOCIATED
        res_ua = ValidationResult(
            status="PASS",
            binary=1,
            reason="Unassociated standalone quantity detected",
            evidence_state=EvidenceAvailabilityState.EVIDENCE_DETECTED_UNASSOCIATED.value,
        )
        assert res_ua.to_dict()["evidence_state"] == "EVIDENCE_DETECTED_UNASSOCIATED"

    def test_j_rule_engine_preserves_evidence_state(self):
        """TEST J: evaluate_rules exposes evidence_state on rule result item and in validation_result."""
        applicable_rules = [
            {
                "rule_id": "LMPC_NET_QTY_PRESENT",
                "parameter": "DECLARED_NET_QUANTITY",
                "package_type": "RETAIL",
                "validation_method": "QUANTITY_UNIT_PAIR",
                "required": True,
            },
            {
                "rule_id": "LMPC_CONSUMER_CARE",
                "parameter": "CONSUMER_CARE",
                "package_type": "RETAIL",
                "validation_method": "CONSUMER_CARE_CONTACT",
                "required": True,
            },
        ]
        extracted_fields = {
            "DECLARED_NET_QUANTITY": {
                "value": "500 g",
                "quantity_value": "500",
                "quantity_unit": "g",
                "quantity_present": True,
                "unit_present": True,
                "quantity_unit_valid": True,
                "confidence": 0.90,
                "evidence_state": EvidenceAvailabilityState.EVIDENCE_VERIFIED.value,
            },
            # CONSUMER_CARE missing
        }
        results, overall = evaluate_rules(applicable_rules, extracted_fields)

        qty_rule_res = next(r for r in results if r["parameter"] == "DECLARED_NET_QUANTITY")
        assert qty_rule_res["evidence_state"] == EvidenceAvailabilityState.EVIDENCE_VERIFIED.value
        assert qty_rule_res["validation_result"]["evidence_state"] == EvidenceAvailabilityState.EVIDENCE_VERIFIED.value

        cc_rule_res = next(r for r in results if r["parameter"] == "CONSUMER_CARE")
        assert cc_rule_res["evidence_state"] == EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value
        assert cc_rule_res["validation_result"]["evidence_state"] == EvidenceAvailabilityState.EVIDENCE_NOT_DETECTED.value

    def test_k_regulatory_matrix_traceability_unbroken(self):
        """TEST K: Verify regulatory matrix file rule_matrix.json exists, is valid, and is untouched."""
        import json
        import os

        matrix_path = "data/rule_matrix.json"
        assert os.path.exists(matrix_path), "rule_matrix.json must exist"

        with open(matrix_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        rules = data.get("rules", [])
        assert len(rules) >= 20, "Regulatory rule matrix must contain rules"
        for r in rules:
            assert "rule_id" in r
            assert "parameter" in r
            assert "regulatory_source" in r
            assert "rule_reference" in r

    def test_l_end_to_end_retail_package_inspection(self):
        """TEST L: Full pipeline integration test on dense retail back-panel OCR text."""
        retail_ocr = (
            "NUTRITIONAL FACTS (Approx per 100g):\n"
            "Energy 450 kcal, Protein 7 g, Carbohydrate 65 g, Total Sugars 0 g, Trans Fat 0 g\n"
            "Manufactured by:\n"
            "Heritage Organic Foods Pvt Ltd\n"
            "Plot No. 12, Agro Industrial Park, Phase 1, G.T. Road, Karnal, Haryana 132001\n"
            "Net Quantity: 400 g\n"
            "Mfg Dt: 02/2026\n"
            "Batch No: HR-092\n"
            "MRP Rs. 85.00 (Incl. of all taxes)\n"
            "For Consumer Complaints Call: 1800-111-2222 or email customercare@heritagefoods.com\n"
        )
        fields = extract_declarations(retail_ocr)

        # 1. Product & Net quantity
        assert fields["DECLARED_NET_QUANTITY"]["quantity_value"] == "400"
        assert fields["DECLARED_NET_QUANTITY"]["quantity_unit"] == "g"
        assert fields["DECLARED_NET_QUANTITY"]["candidate_type"] == QuantityCandidateType.PACKAGE_QUANTITY.value

        # 2. MRP isolated
        assert "85.00" in fields["MRP"]["value"]
        assert fields["MRP"].get("currency_status") == "VERIFIED"

        # 3. Manufacturer & Address separated
        assert "Heritage Organic Foods Pvt Ltd" in fields["MANUFACTURER_NAME"]["value"]
        assert "Karnal, Haryana 132001" in fields["MANUFACTURER_ADDRESS"]["value"]
        assert "Mfg Dt" not in fields["MANUFACTURER_ADDRESS"]["value"]

        # 4. Date & Batch
        assert "02/2026" in str(fields.get("MONTH_YEAR_MANUFACTURE", {}).get("value") or fields.get("MANUFACTURE_DATE", {}).get("value"))
        assert fields["BATCH_NUMBER"]["value"] == "HR-092"

        # 5. Consumer Care
        assert "1800-111-2222" in fields["CONSUMER_CARE"]["value"]
