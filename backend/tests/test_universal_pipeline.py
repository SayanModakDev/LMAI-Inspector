"""
Comprehensive Test Suite for Universal OCR / Evidence / Result Quality Pipeline.

Verifies:
1. Canonical EvidenceCandidate Object & Lifecycle
2. OCR Cleaning Layer (artifact rejection vs legitimate token preservation)
3. Universal Label-Value Association Engine (same-line, below, spatial right)
4. Field-Specific Semantic Scoping (Quantity, Date, Identity, Batch, MRP, Address)
5. Multi-Image Evidence Merging (CONFIRMED_SAME, COMPLEMENTARY, TRUE_CONFLICT, AMBIGUOUS, IRRELEVANT)
6. Deterministic Rule Matrix Evaluation & Overall Compliance
7. Anti-Hardcoding Codebase Audit
"""

import glob
import os
import re
import pytest

from app.extraction.evidence_model import (
    AnchorRelation,
    EvidenceCandidate,
    EvidenceMergeClassification,
    FIELD_SCOPING_REGISTRY,
    SourceType,
    ValidationState,
    SECTION_DECLARED_QUANTITY,
    SECTION_NUTRITION,
    SECTION_SERVING_SIZE,
    SECTION_MRP,
    SECTION_BATCH,
    SECTION_DATE,
    SECTION_MANUFACTURER,
    SECTION_ADDRESS,
    SECTION_CONSUMER_CARE,
)
from app.extraction.cleaner import clean_ocr_evidence, is_artifact_token, is_isolated_punctuation
from app.extraction.association_engine import LabelValueAssociator, AssociatedCandidate
from app.extraction.label_value_association import (
    EvidenceToken,
    SemanticLabel,
    ValueCandidate,
    LabelValueRelation,
    CanonicalFieldCandidate,
    LabelValueAssociationEngine,
)
from app.extraction.declaration_extractor import (
    extract_declarations,
    merge_extracted_fields,
    _extract_batch_number,
    _extract_mrp_structured,
    _extract_net_quantity_field,
    _clean_address_text,
)
from app.rules.rule_engine import evaluate_rules
from app.rules.validators import (
    validate_batch_number_present,
    validate_mrp_present,
    validate_value_and_unit_present,
)


# ===========================================================================
# 1. Canonical EvidenceCandidate Object & Lifecycle
# ===========================================================================
class TestEvidenceCandidateLifecycle:

    def test_evidence_candidate_creation_and_dict_serialization(self):
        """EvidenceCandidate properly stores all required fields and serializes cleanly."""
        cand = EvidenceCandidate(
            raw_text="Net Wt: 500 g",
            normalized_text="500 g",
            source_image="OCR_IMAGE_1",
            source_type=SourceType.OCR.value,
            ocr_confidence=0.92,
            bounding_box={"x": 50, "y": 100, "w": 200, "h": 30},
            line_id=3,
            region_id=1,
            semantic_section=SECTION_DECLARED_QUANTITY,
            anchor_label="Net Wt",
            anchor_relation=AnchorRelation.SAME_LINE.value,
            candidate_field="DECLARED_NET_QUANTITY",
            relevance_score=0.95,
            validation_state=ValidationState.UNASSESSED.value,
        )

        d = cand.to_dict()
        assert d["raw_text"] == "Net Wt: 500 g"
        assert d["normalized_text"] == "500 g"
        assert d["source_image"] == "OCR_IMAGE_1"
        assert d["source_type"] == "OCR"
        assert d["ocr_confidence"] == 0.92
        assert d["bounding_box"] == {"x": 50, "y": 100, "w": 200, "h": 30}
        assert d["line_id"] == 3
        assert d["semantic_section"] == "DECLARED_QUANTITY"
        assert d["anchor_label"] == "Net Wt"
        assert d["anchor_relation"] == "SAME_LINE"
        assert d["candidate_field"] == "DECLARED_NET_QUANTITY"
        assert d["relevance_score"] == 0.95
        assert d["validation_state"] == "UNASSESSED"

        # Roundtrip reconstruction
        reconstructed = EvidenceCandidate.from_dict(d)
        assert reconstructed.raw_text == cand.raw_text
        assert reconstructed.normalized_text == cand.normalized_text
        assert reconstructed.anchor_relation == cand.anchor_relation

    def test_field_scoping_registry_covers_statutory_fields(self):
        """Scoping registry defines rules for all 23+ canonical statutory declarations."""
        required_fields = [
            "PRODUCT_NAME", "BRAND", "GENERIC_NAME", "PRODUCT_TYPE",
            "DECLARED_NET_QUANTITY", "MRP", "MANUFACTURER_NAME", "MANUFACTURER_ADDRESS",
            "PACKER_NAME", "PACKER_ADDRESS", "IMPORTER_NAME", "IMPORTER_ADDRESS",
            "MANUFACTURE_DATE", "PACKING_DATE", "BEST_BEFORE_DATE", "USE_BY_DATE",
            "EXPIRY_DATE", "BATCH_NUMBER", "CONSUMER_CARE", "FSSAI_LICENSE",
            "VEG_NONVEG_SYMBOL", "INGREDIENTS", "NUTRITIONAL_INFO", "SERVING_SIZE",
        ]
        for f in required_fields:
            assert f in FIELD_SCOPING_REGISTRY, f"Missing field in scoping registry: {f}"
            rule = FIELD_SCOPING_REGISTRY[f]
            assert len(rule.allowed_sections) > 0
            assert rule.expected_value_type in (
                "TEXT", "NUMBER", "CURRENCY", "DATE", "UNIT_MEASUREMENT", "IDENTIFIER", "ADDRESS"
            )


# ===========================================================================
# 2. OCR Cleaning Layer
# ===========================================================================
class TestOCRCleaningLayer:

    def test_cleaner_strips_image_placeholders(self):
        """Image placeholder tokens like [IMAGE 1], <image>, __IMAGE__ are removed."""
        raw = (
            "[IMAGE 1]\n"
            "ACME HEALTHCARE\n"
            "<image 2>\n"
            "Net Qty: 60 tablets\n"
            "__IMAGE__\n"
            "MRP: Rs. 250.00"
        )
        cleaned, items, removed = clean_ocr_evidence(raw)
        assert "[IMAGE 1]" not in cleaned
        assert "<image 2>" not in cleaned
        assert "__IMAGE__" not in cleaned
        assert "ACME HEALTHCARE" in cleaned
        assert "Net Qty: 60 tablets" in cleaned
        assert "MRP: Rs. 250.00" in cleaned
        assert len(removed) >= 3

    def test_cleaner_strips_repeated_noise_and_isolated_punctuation(self):
        """Repeated dashes, dots, and isolated punctuation are stripped while valid text is kept."""
        raw = (
            "------------------\n"
            "Brand: Sunburst\n"
            ".......\n"
            ",\n"
            ":\n"
            "Net Weight: 1 kg\n"
            "|||||||||\n"
            "MRP ₹120.00"
        )
        cleaned, items, removed = clean_ocr_evidence(raw)
        assert "------------------" not in cleaned
        assert "......." not in cleaned
        assert "\n,\n" not in cleaned
        assert "Sunburst" in cleaned
        assert "Net Weight: 1 kg" in cleaned
        assert "MRP ₹120.00" in cleaned

    def test_cleaner_preserves_short_legitimate_tokens(self):
        """Legitimate short measurement units (g, ml, L) and currency symbols (₹, Rs) are preserved."""
        assert not is_artifact_token("g")[0]
        assert not is_artifact_token("ml")[0]
        assert not is_artifact_token("kg")[0]
        assert not is_artifact_token("L")[0]
        assert not is_artifact_token("Rs")[0]
        assert not is_artifact_token("₹")[0]
        assert not is_artifact_token("10")[0]
        assert not is_isolated_punctuation("₹")
        assert not is_isolated_punctuation("Rs.")


# ===========================================================================
# 3. Universal Label-Value Association Engine
# ===========================================================================
class TestUniversalLabelValueAssociation:

    def test_same_line_association(self):
        """Label and value on the same line are associated with SAME_LINE relation."""
        lines = [
            "SUPER HERBALS",
            "Net Weight: 250 g",
            "Batch No: BN-9941",
            "MRP: Rs. 85.00",
        ]
        candidates = LabelValueAssociator.find_associations(
            lines=lines,
            label_pattern=r'net\s*(?:wt\.?|weight|qty\.?|quantity)',
            value_pattern=r'(\d+(?:\.\d+)?\s*(?:g|kg|ml|l|pcs))',
        )
        assert len(candidates) >= 1
        cand = candidates[0]
        assert cand.value_text == "250 g"
        assert cand.relation == AnchorRelation.SAME_LINE.value
        assert cand.line_index == 1

    def test_next_line_below_association(self):
        """Label on one line and value on the immediate next line are associated with BELOW relation."""
        lines = [
            "PURE HARVEST",
            "Net Quantity:",
            "500 ml",
            "Best Before:",
            "12/2026",
        ]
        candidates = LabelValueAssociator.find_associations(
            lines=lines,
            label_pattern=r'net\s*(?:wt\.?|weight|qty\.?|quantity)',
            value_pattern=r'(\d+(?:\.\d+)?\s*(?:g|kg|ml|l|pcs))',
        )
        assert len(candidates) >= 1
        cand = candidates[0]
        assert cand.value_text == "500 ml"
        assert cand.relation == AnchorRelation.BELOW.value
        assert cand.line_index == 1
        assert cand.value_line_index == 2

    def test_spatial_right_association_via_bounding_boxes(self):
        """Items aligned horizontally on the same band with value to the right are associated with RIGHT relation."""
        ocr_items = [
            {"text": "Net Wt:", "bbox": [100, 200, 180, 230], "confidence": 0.95},
            {"text": "750 g", "bbox": [190, 200, 260, 230], "confidence": 0.93},
        ]
        candidates = LabelValueAssociator.find_associations(
            lines=["Net Wt:", "750 g"],
            label_pattern=r'net\s*wt',
            value_pattern=r'(\d+\s*g)',
            ocr_items=ocr_items,
        )
        # Should have spatial association
        spatial_cand = next((c for c in candidates if c.relation == AnchorRelation.RIGHT.value), None)
        assert spatial_cand is not None
        assert spatial_cand.value_text == "750 g"


# ===========================================================================
# 4. Field-Specific Semantic Scoping
# ===========================================================================
class TestFieldSpecificSemanticScoping:

    def test_nutrition_and_serving_size_never_become_declared_net_quantity(self):
        """Nutritional carbs (62.4 g) and serving size (30 g) are rejected in favor of declared 400 g."""
        text = (
            "GLACIER OATS\n"
            "Net Qty: 400 g\n"
            "Serving Size: 30 g\n"
            "Nutrition Information per 100g:\n"
            "Energy 380 kcal\n"
            "Carbohydrate 62.4 g\n"
            "Protein 11.2 g\n"
            "Fat 7.5 g\n"
            "MRP Rs. 160.00"
        )
        fields = extract_declarations(text)
        qty = fields.get("DECLARED_NET_QUANTITY", {})

        assert qty.get("quantity_value") == "400"
        assert qty.get("quantity_unit") == "g"
        assert qty.get("value") == "400 g"

        # Verify rejected candidates are archived for auditability
        ignored = qty.get("ignored_candidates", [])
        assert any("62.4" in str(c.get("quantity_value")) for c in ignored)
        assert any("30" in str(c.get("quantity_value")) for c in ignored)

    def test_company_name_never_becomes_product_name(self):
        """Manufacturer company name (XYZ Organics Pvt. Ltd.) must not become product name."""
        text = (
            "ORGANIC HONEY\n"
            "Net Weight: 500 g\n"
            "Manufactured by: XYZ Organics Private Limited\n"
            "Works: Plot 12, Industrial Area, Sector 5, Haridwar, PIN 249401, India\n"
            "MRP ₹350.00"
        )
        fields = extract_declarations(text)
        pname = str(fields.get("PRODUCT_NAME", {}).get("value", ""))
        assert "private limited" not in pname.lower()
        assert "pvt" not in pname.lower()
        assert "XYZ Organics" in fields.get("MANUFACTURER_NAME", {}).get("value", "")

    def test_address_truncates_cleanly_at_section_boundaries(self):
        """Manufacturer address truncates before customer care and MRP."""
        text = (
            "Manufactured by: Sunrise Agro Foods Ltd.\n"
            "Factory: Survey 45, Phase II, GIDC Estate, Ahmedabad 382445, Gujarat, India\n"
            "Customer Care: Call 1800-200-4000 or email support@sunriseagro.com\n"
            "MRP: Rs. 99.00\n"
            "Net Qty: 1 kg"
        )
        fields = extract_declarations(text)
        addr = str(fields.get("MANUFACTURER_ADDRESS", {}).get("value", ""))
        assert "Ahmedabad" in addr
        assert "1800" not in addr
        assert "support@sunriseagro.com" not in addr
        assert "mrp" not in addr.lower()
        assert "Call 1800-200-4000" in str(fields.get("CONSUMER_CARE", {}).get("value", ""))

    def test_batch_number_separates_labels_and_rejects_placeholders(self):
        """Batch extraction isolates identifier and validator rejects lone label tokens and placeholders."""
        # Legitimate batch
        fields = extract_declarations("Batch No: BN-2024-X\nMRP ₹50.00\nNet Wt: 100 g")
        assert fields.get("BATCH_NUMBER", {}).get("value") == "BN-2024-X"

        # Rejection of lone tokens
        res_no = validate_batch_number_present({"value": "Batch No: NO"}, {}, {})
        assert res_no.binary == 0
        assert res_no.status == "FAIL"

        res_num = validate_batch_number_present({"value": "Batch Number: NUMBER"}, {}, {})
        assert res_num.binary == 0
        assert res_num.status == "FAIL"

        res_img = validate_batch_number_present({"value": "Batch No: [IMAGE 1]"}, {}, {})
        assert res_img.binary == 0
        assert res_img.status == "FAIL"

    def test_date_semantics_do_not_bleed_across_labels(self):
        """Manufacture date, Expiry date, and Best Before date are mapped to their respective fields."""
        text = (
            "MFD: 10/2024\n"
            "PKD: 11/2024\n"
            "Best Before: 10/2025\n"
            "EXP: 11/2025"
        )
        fields = extract_declarations(text)
        assert (fields.get("MONTH_YEAR_MANUFACTURE") or fields.get("MANUFACTURE_DATE", {})).get("value") == "10/2024"
        assert fields.get("PACKING_DATE", {}).get("value") == "11/2024"
        assert fields.get("BEST_BEFORE_USE_BY", {}).get("value") == "10/2025"
        assert fields.get("EXPIRY_DATE", {}).get("value") == "11/2025"


# ===========================================================================
# 5. Multi-Image Evidence Merging & Classification
# ===========================================================================
class TestMultiImageEvidenceMerging:

    def test_confirmed_same_classification(self):
        """Identical declarations across different package views are classified as CONFIRMED_SAME."""
        img1 = {"DECLARED_NET_QUANTITY": {"value": "500 g", "confidence": 0.90, "source": "OCR_IMAGE_1"}}
        img2 = {"DECLARED_NET_QUANTITY": {"value": "500 g", "confidence": 0.88, "source": "OCR_IMAGE_2"}}
        merged = merge_extracted_fields([img1, img2])
        qty = merged.get("DECLARED_NET_QUANTITY", {})
        assert qty.get("value") == "500 g"
        assert qty.get("candidate_classification") == "CONFIRMED_SAME"

    def test_complementary_multi_panel_evidence(self):
        """Front panel brand and back panel product variant are classified as COMPLEMENTARY (MULTI_PANEL_EVIDENCE)."""
        img1 = {"PRODUCT_NAME": {"value": "Herbal Glow Face Wash", "confidence": 0.92, "source": "OCR_IMAGE_1", "source_image_index": 0}}
        img2 = {"PRODUCT_NAME": {"value": "Herbal Glow Gentle Cleanser", "confidence": 0.85, "source": "OCR_IMAGE_2", "source_image_index": 1}}
        merged = merge_extracted_fields([img1, img2])
        pname = merged.get("PRODUCT_NAME", {})
        assert pname.get("candidate_classification") in ("MULTI_PANEL_EVIDENCE", "COMPLEMENTARY")
        assert pname.get("has_conflict") is False

    def test_true_conflict_flagged_for_inspector_review(self):
        """Contradictory values for the same semantic declaration are classified as TRUE_CONFLICT."""
        img1 = {"MRP": {"value": "₹150.00", "confidence": 0.90, "source": "OCR_IMAGE_1"}}
        img2 = {"MRP": {"value": "₹190.00", "confidence": 0.88, "source": "OCR_IMAGE_2"}}
        merged = merge_extracted_fields([img1, img2])
        mrp = merged.get("MRP", {})
        assert mrp.get("candidate_classification") == "TRUE_CONFLICT"
        assert mrp.get("has_conflict") is True
        assert mrp.get("status") == "CONFLICTING_EVIDENCE"

    def test_nutrition_carbs_do_not_create_conflict_with_net_quantity(self):
        """Front panel 250 g and back panel nutritional carbs 65 g do not produce a false conflict."""
        front_text = "Golden Flakes\nNet Weight: 250 g\nMRP ₹90.00"
        back_text = "Nutrition per 100g:\nCarbohydrate 65 g\nProtein 8 g"

        fields_front = extract_declarations(front_text)
        fields_back = extract_declarations(back_text)

        merged = merge_extracted_fields([fields_front, fields_back])
        qty = merged.get("DECLARED_NET_QUANTITY", {})
        assert qty.get("value") == "250 g"
        assert qty.get("has_conflict") is not True
        assert qty.get("candidate_classification") != "TRUE_CONFLICT"


# ===========================================================================
# 6. Deterministic Rule Matrix Evaluation & Overall Compliance
# ===========================================================================
class TestRuleEvaluationAndCompliance:

    def test_compliant_declarations_produce_binary_one_and_compliant_overall(self):
        """Complete, valid statutory declarations evaluate to binary 1 (PASS) and COMPLIANT."""
        fields = {
            "PRODUCT_NAME": {"value": "Pure Coconut Oil", "confidence": 0.9},
            "DECLARED_NET_QUANTITY": {
                "value": "500 ml",
                "quantity_value": "500",
                "quantity_unit": "ml",
                "quantity_present": True,
                "unit_present": True,
                "quantity_unit_valid": True,
                "confidence": 0.92,
            },
            "MRP": {"value": "₹125.00", "numeric_mrp": 125.0, "confidence": 0.9},
            "MANUFACTURER_NAME": {"value": "Kerala Oils Ltd.", "confidence": 0.88},
            "MANUFACTURER_ADDRESS": {"value": "Kochi, Kerala 682001, India", "confidence": 0.85},
            "MONTH_YEAR_MANUFACTURE": {"value": "11/2024", "confidence": 0.85},
            "BATCH_NUMBER": {"value": "B-902", "confidence": 0.88},
            "CONSUMER_CARE": {"value": "1800-425-1000", "confidence": 0.85},
        }
        rules = [
            {"rule_id": "PC-ALL-001", "parameter": "DECLARED_NET_QUANTITY", "required": True, "validation_method": "VALUE_AND_UNIT_PRESENT"},
            {"rule_id": "PC-ALL-002", "parameter": "MRP", "required": True, "validation_method": "MRP_PRESENT"},
            {"rule_id": "PC-ALL-003", "parameter": "MANUFACTURER_NAME", "required": True, "validation_method": "MANUFACTURER_PRESENT"},
            {"rule_id": "PC-ALL-004", "parameter": "MONTH_YEAR_MANUFACTURE", "required": True, "validation_method": "DATE_PRESENT"},
            {"rule_id": "PC-ALL-005", "parameter": "BATCH_NUMBER", "required": True, "validation_method": "BATCH_NUMBER_PRESENT"},
            {"rule_id": "PC-ALL-006", "parameter": "CONSUMER_CARE", "required": True, "validation_method": "CONSUMER_CARE_PRESENT"},
        ]
        results, overall = evaluate_rules(rules, fields)
        for r in results:
            assert r["binary"] == 1
            assert r["status"] == "PASS"
        assert overall == "COMPLIANT"

    def test_missing_mandatory_declaration_requires_review(self):
        """Missing mandatory MRP evaluates to binary 0 and NOT_VERIFIABLE (requires review)."""
        fields = {
            "DECLARED_NET_QUANTITY": {
                "value": "200 g",
                "quantity_value": "200",
                "quantity_unit": "g",
                "quantity_present": True,
                "unit_present": True,
                "quantity_unit_valid": True,
            },
        }
        rule = {"rule_id": "PC-ALL-002", "parameter": "MRP", "required": True, "validation_method": "MRP_PRESENT"}
        results, overall = evaluate_rules([rule], fields)
        assert results[0]["binary"] == 0
        assert results[0]["status"] == "NOT_VERIFIABLE"
        assert overall == "NOT_VERIFIABLE"

    def test_invalid_declaration_fails_rule_and_marks_non_compliant(self):
        """Invalid fractional count declaration (10.5 tablets) evaluates to binary 0, FAIL, and NON_COMPLIANT."""
        fields = {
            "DECLARED_NET_QUANTITY": {
                "value": "10.5 tablets",
                "quantity_value": "10.5",
                "quantity_unit": "tablets",
                "quantity_present": True,
                "unit_present": True,
                "quantity_type": "COUNT",
            },
        }
        rule = {"rule_id": "PC-ALL-001", "parameter": "DECLARED_NET_QUANTITY", "required": True, "validation_method": "VALUE_AND_UNIT_PRESENT"}
        results, overall = evaluate_rules([rule], fields)
        assert results[0]["binary"] == 0
        assert results[0]["status"] == "FAIL"
        assert overall == "NON_COMPLIANT"


# ===========================================================================
# 7. Anti-Hardcoding Codebase Audit
# ===========================================================================
class TestAntiHardcodingAudit:

    def test_production_backend_code_has_no_product_specific_hardcoding(self):
        """Audit production backend codebase (backend/app/) for forbidden product-specific keywords."""
        backend_app_dir = os.path.join(os.path.dirname(__file__), "..", "app")
        python_files = glob.glob(os.path.join(backend_app_dir, "**", "*.py"), recursive=True)

        forbidden_patterns = [
            (r'\bsupreme\b', "Sample brand 'supreme'"),
            (r'\bcrystal_sugar\b', "Sample commodity constant 'crystal_sugar'"),
            (r'\b25\s*g\b', "Sample quantity '25 g'"),
            (r'\bchissyum\b', "Sample brand 'chissyum'"),
            (r'\bdody\s+talcum\b', "Sample OCR correction 'dody talcum'"),
        ]

        violations = []
        for file_path in python_files:
            rel_path = os.path.relpath(file_path, backend_app_dir)
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                for pat, label in forbidden_patterns:
                    matches = list(re.finditer(pat, content, flags=re.IGNORECASE))
                    if matches:
                        for m in matches:
                            line_num = content[:m.start()].count('\n') + 1
                            violations.append(f"{rel_path}:{line_num} contains forbidden pattern: {label}")

        assert len(violations) == 0, f"Found anti-hardcoding violations in production code:\n" + "\n".join(violations)


# ===========================================================================
# 8. Canonical Evidence Model & Association Engine Integration
# ===========================================================================
class TestCanonicalEvidenceModelAndAssociationEngine:

    def test_canonical_models_instantiation_and_conversion(self):
        """EvidenceToken, SemanticLabel, ValueCandidate, LabelValueRelation, and CanonicalFieldCandidate operate properly."""
        tok = EvidenceToken(
            raw_text="Net Qty: 500 g",
            normalized_text="net qty: 500 g",
            bbox={"x": 10, "y": 20, "w": 100, "h": 25},
            line_id=1,
        )
        assert tok.raw_text == "Net Qty: 500 g"
        assert tok.to_dict()["line_id"] == 1

        lbl = SemanticLabel(
            label_text="Net Qty:",
            normalized_label="net qty:",
            semantic_type="NET_QUANTITY",
            line_id=1,
        )
        val = ValueCandidate(
            raw_text="500 g",
            parsed_value=500,
            unit="g",
            line_id=1,
            value_type="QUANTITY",
            semantic_section="DECLARED_QUANTITY",
        )
        rel = LabelValueRelation(
            label=lbl,
            candidate=val,
            spatial_relation="SAME_LINE",
            distance=0.02,
            same_line=True,
            aligned=True,
            semantic_compatibility=1.0,
            section_compatibility=1.0,
            relation_score=0.96,
        )
        assert rel.relation_score == 0.96
        assert rel.to_dict()["spatial_relation"] == "SAME_LINE"

        cfc = CanonicalFieldCandidate(
            field="DECLARED_NET_QUANTITY",
            normalized_value=500,
            raw_text="500 g",
            anchor_label="Net Qty:",
            semantic_section="DECLARED_QUANTITY",
            relevance_score=0.96,
            confidence=0.92,
            validation_state="ACCEPTED",
            provenance={"what": 500, "why": "Anchored by Net Qty: on same line"},
        )
        assert cfc.validation_state == "ACCEPTED"
        ev = cfc.to_evidence_candidate()
        assert ev.candidate_field == "DECLARED_NET_QUANTITY"
        assert ev.anchor_label == "Net Qty:"

    def test_normalized_spatial_computation_independence(self):
        """Normalized spatial distance operates smoothly without fixed pixel thresholds across scale sizes."""
        # Small image box (e.g. 200x200)
        rel_s, dist_s, same_s, align_s = LabelValueAssociationEngine.calculate_normalized_spatial_relation(
            {"x": 10, "y": 10, "w": 40, "h": 15},
            {"x": 55, "y": 10, "w": 30, "h": 15},
            image_dimensions=(200, 200),
        )
        assert rel_s in ("SAME_LINE", "RIGHT")
        assert dist_s < 0.35
        assert same_s is True

        # High-res image box (e.g. 3000x3000)
        rel_l, dist_l, same_l, align_l = LabelValueAssociationEngine.calculate_normalized_spatial_relation(
            {"x": 150, "y": 150, "w": 600, "h": 225},
            {"x": 825, "y": 150, "w": 450, "h": 225},
            image_dimensions=(3000, 3000),
        )
        assert rel_l in ("SAME_LINE", "RIGHT")
        assert dist_l < 0.35
        assert same_l is True

    def test_rejection_of_nutrition_from_net_quantity_with_reason(self):
        """Candidates in NUTRITION section are rejected with explicit audit reason."""
        lbl = SemanticLabel(label_text="Net Qty:", normalized_label="net qty:", semantic_type="NET_QUANTITY")
        val = ValueCandidate(raw_text="45 g", parsed_value=45, unit="g", value_type="QUANTITY")
        
        sem_compat, sec_compat, reason = LabelValueAssociationEngine.evaluate_semantic_and_section_compatibility(
            "DECLARED_NET_QUANTITY", lbl, val, "NUTRITION"
        )
        assert sec_compat == 0.0
        assert reason is not None
        assert "NUTRITION" in reason

    def test_rejection_of_invalid_batch_label_tokens(self):
        """Batch extraction rejects 'NO', 'NUMBER', and placeholders."""
        lbl = SemanticLabel(label_text="Batch No:", normalized_label="batch no:", semantic_type="BATCH_NUMBER")
        val_no = ValueCandidate(raw_text="NO", parsed_value="NO", value_type="IDENTIFIER")
        val_img = ValueCandidate(raw_text="[IMAGE 1]", parsed_value="[IMAGE 1]", value_type="IDENTIFIER")

        sem_no, sec_no, r_no = LabelValueAssociationEngine.evaluate_semantic_and_section_compatibility(
            "BATCH_NUMBER", lbl, val_no, "BATCH"
        )
        assert sem_no == 0.0
        assert r_no is not None

        sem_img, sec_img, r_img = LabelValueAssociationEngine.evaluate_semantic_and_section_compatibility(
            "BATCH_NUMBER", lbl, val_img, "BATCH"
        )
        assert sem_img == 0.0
        assert r_img is not None


# ===========================================================================
# 9. Universal Multi-Product Synthetic Acceptance Test Matrix
# ===========================================================================
class TestUniversalMultiProductAcceptanceMatrix:

    def test_food_mass_packaged_product(self):
        """Food mass product (750 g) extracts cleanly and attaches canonical evidence candidate."""
        text = (
            "HERITAGE HARVEST\n"
            "ROLLED OATS\n"
            "Net Weight: 750 g\n"
            "Batch No: OAT-774\n"
            "MFD: 04/2024\n"
            "EXP: 04/2025\n"
            "MRP ₹185.00\n"
            "Manufactured by: Northern Grains Ltd.\n"
            "Works: Plot 54, Industrial Estate, Mohali, Punjab 160055, India\n"
            "Customer Care: 1800-123-9999"
        )
        fields = extract_declarations(text)
        qty = fields.get("DECLARED_NET_QUANTITY", {})
        assert qty.get("quantity_value") == "750"
        assert qty.get("quantity_unit") == "g"
        assert qty.get("value") == "750 g"
        assert "evidence_candidate" in qty
        assert "canonical_field_candidate" in qty
        assert qty["canonical_field_candidate"]["field"] == "DECLARED_NET_QUANTITY"

        mrp = fields.get("MRP", {})
        assert mrp.get("numeric_value") == 185.0
        assert "evidence_candidate" in mrp

        batch = fields.get("BATCH_NUMBER", {})
        assert batch.get("value") == "OAT-774"

    def test_beverage_volume_packaged_product(self):
        """Beverage volume product (1.5 L) extracts cleanly."""
        text = (
            "MOUNTAIN SPRING\n"
            "NATURAL MINERAL WATER\n"
            "Net Volume: 1.5 L\n"
            "Batch No: MSW-108\n"
            "PKD: 02/2024\n"
            "Best Before: 02/2026\n"
            "MRP: Rs. 45.00\n"
            "Packed by: Alpine Waters Pvt. Ltd.\n"
            "Plot 18, Phase 2, Solan, Himachal Pradesh 173212, India"
        )
        fields = extract_declarations(text)
        qty = fields.get("DECLARED_NET_QUANTITY", {})
        assert qty.get("quantity_value") == "1.5"
        assert qty.get("quantity_unit") == "L"
        assert qty.get("value") == "1.5 L"

        mrp = fields.get("MRP", {})
        assert mrp.get("numeric_value") == 45.0

    def test_pharmaceutical_supplement_count_packaged_product(self):
        """Dietary supplement count product (60 capsules) extracts count correctly."""
        text = (
            "VITAL LIFE\n"
            "MULTIVITAMIN & MINERALS\n"
            "Net Qty: 60 capsules\n"
            "Batch No: B-CAP-402\n"
            "MFD: 01/2024\n"
            "EXP: 12/2025\n"
            "MRP ₹399.00\n"
            "Manufactured by: BioCare Remedies Ltd.\n"
            "Survey 12, Baddi, HP 173205, India"
        )
        fields = extract_declarations(text)
        qty = fields.get("DECLARED_NET_QUANTITY", {})
        assert qty.get("quantity_value") == "60"
        assert qty.get("quantity_unit") == "capsules"
        assert qty.get("quantity_type") == "COUNT"

    def test_household_cleaner_packaged_product(self):
        """Household disinfectant cleaner extracts volume and manufacturer address."""
        text = (
            "KLEENEX PRO\n"
            "SURFACE DISINFECTANT CLEANER\n"
            "Net Contents: 500 ml\n"
            "Batch No: KLP-99\n"
            "MFD: 06/2024\n"
            "MRP ₹120.00\n"
            "Manufactured by: CleanHome Chemical Industries\n"
            "Plot 9, Sector 4, Vapi, Gujarat 396195, India"
        )
        fields = extract_declarations(text)
        qty = fields.get("DECLARED_NET_QUANTITY", {})
        assert qty.get("quantity_value") == "500"
        assert qty.get("quantity_unit") == "ml"
        assert fields.get("MRP", {}).get("numeric_value") == 120.0
        assert "CleanHome Chemical" in fields.get("MANUFACTURER_NAME", {}).get("value", "")

    def test_cosmetic_lotion_packaged_product(self):
        """Cosmetic body lotion product extracts volume and handles multiple panel merges."""
        front_text = (
            "VELVET TOUCH\n"
            "HYDRATING BODY LOTION\n"
            "Net Qty: 200 ml\n"
            "MRP ₹245.00"
        )
        back_text = (
            "Manufactured by: Velvet Touch Cosmetics Pvt. Ltd.\n"
            "Factory: Plot 22, MIDC, Andheri East, Mumbai 400093, India\n"
            "Batch No: VT-2024-L\n"
            "MFD: 08/2024\n"
            "Use By: 08/2026\n"
            "Consumer Care: call 1800-888-7777"
        )
        fields_front = extract_declarations(front_text)
        fields_back = extract_declarations(back_text)

        merged = merge_extracted_fields([fields_front, fields_back])
        assert merged.get("DECLARED_NET_QUANTITY", {}).get("value") == "200 ml"
        assert merged.get("MRP", {}).get("numeric_value") == 245.0
        assert merged.get("BATCH_NUMBER", {}).get("value") == "VT-2024-L"
        assert "Velvet Touch" in merged.get("MANUFACTURER_NAME", {}).get("value", "")
        assert merged.get("DECLARED_NET_QUANTITY", {}).get("candidate_classification") in ("CONFIRMED_SAME", "COMPLEMENTARY", "MULTI_PANEL_EVIDENCE", "UNIQUE_PANEL", "SINGLE_PANEL")

    def test_noisy_ocr_and_missing_values_handled_gracefully(self):
        """Noisy OCR with missing MRP does not crash and produces NOT_VERIFIABLE for missing MRP rule."""
        noisy_text = (
            "--- !!! ---\n"
            "BRANDXYZ PREMIUM\n"
            "Net Wt: 350 g\n"
            "Batch: B-998\n"
            "Mfg Date: 09/2024\n"
            "......."
        )
        fields = extract_declarations(noisy_text)
        assert fields.get("DECLARED_NET_QUANTITY", {}).get("value") == "350 g"
        assert "MRP" not in fields or fields["MRP"].get("numeric_value") is None

        # Rule evaluation handles missing MRP gracefully
        rule = {"rule_id": "PC-ALL-002", "parameter": "MRP", "required": True, "validation_method": "MRP_PRESENT"}
        results, overall = evaluate_rules([rule], fields)
        assert results[0]["status"] == "NOT_VERIFIABLE"
        assert results[0]["binary"] == 0
