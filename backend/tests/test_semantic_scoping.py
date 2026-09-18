"""
Comprehensive Regression Tests for Semantic Field Scoping, Structured MRP,
and Manufacturer Address Boundaries.

Verifies:
1. Declared Net Quantity Scoping (8 tests)
2. Structured MRP Extraction & Validation (6 tests)
3. Manufacturer Address Boundary Enforcement (6 tests)
4. End-to-End & Multi-Image Regression (4 tests)
Total: 24 tests.
"""

import pytest
from app.extraction.declaration_extractor import (
    extract_declarations,
    merge_extracted_fields,
    _extract_mrp_structured,
    _extract_net_quantity_field,
    _clean_address_text,
    _is_irrelevant_candidate,
    SECTION_DECLARED_QUANTITY,
    SECTION_NUTRITION,
    SECTION_SERVING_SIZE,
)
from app.rules.validators import validate_mrp_present, validate_value_and_unit_present
from app.rules.rule_engine import evaluate_rules


# ===========================================================================
# 1. Declared Net Quantity Scoping (8 tests)
# ===========================================================================
class TestDeclaredNetQuantityScoping:

    def test_nutrition_carbohydrate_not_net_quantity(self):
        """Text with Net Wt 20 g and Carbohydrate 53.15 g extracts 20 g and rejects 53.15 g."""
        text = (
            "SWISSYUM FOODS\n"
            "SWEET'N SOUR\n"
            "Net Wt: 20 g\n"
            "Nutritional Information per 100g:\n"
            "Energy 450 kcal\n"
            "Carbohydrate 53.15 g\n"
            "Total Sugar 12.5 g\n"
            "Protein 5.2 g\n"
            "MRP ₹10.00"
        )
        fields = extract_declarations(text)
        qty = fields.get("DECLARED_NET_QUANTITY", {})

        assert qty.get("quantity_value") == "20"
        assert qty.get("quantity_unit") == "g"
        assert qty.get("value") == "20 g"
        assert qty.get("quantity_unit_valid") is True

        # Ignored candidates must contain the rejected nutrition values
        ignored = qty.get("ignored_candidates", [])
        assert any("53.15" in str(c.get("quantity_value")) for c in ignored)
        nutrition_ignored = next((c for c in ignored if str(c.get("quantity_value")) == "53.15"), None)
        assert nutrition_ignored is not None
        assert nutrition_ignored.get("semantic_section") == SECTION_NUTRITION
        assert nutrition_ignored.get("relevance") == "rejected_as_irrelevant"

    def test_serving_size_not_net_quantity(self):
        """Serve size per 20g with Net Wt 100 g extracts 100 g and ignores 20g serving size."""
        text = (
            "Crispy Delight\n"
            "Net Wt: 100 g\n"
            "Serve size per 20g\n"
            "Servings per pack: 5\n"
            "MRP ₹50.00"
        )
        fields = extract_declarations(text)
        qty = fields.get("DECLARED_NET_QUANTITY", {})

        assert qty.get("quantity_value") == "100"
        assert qty.get("quantity_unit") == "g"
        assert qty.get("value") == "100 g"

        ignored = qty.get("ignored_candidates", [])
        serving_ignored = next((c for c in ignored if str(c.get("quantity_value")) == "20"), None)
        assert serving_ignored is not None
        assert serving_ignored.get("semantic_section") == SECTION_SERVING_SIZE
        assert serving_ignored.get("relevance") == "rejected_as_irrelevant"

    def test_only_nutrition_no_declared_net_quantity(self):
        """Crop containing only nutrition table rows must NOT populate DECLARED_NET_QUANTITY."""
        text = (
            "Nutritional Information\n"
            "Per 100g\n"
            "Energy 400 kcal\n"
            "Carbohydrate 53.15 g\n"
            "Protein 8.5 g\n"
            "Fat 14.2 g\n"
            "Sodium 350 mg"
        )
        fields = extract_declarations(text)
        assert "DECLARED_NET_QUANTITY" not in fields

    def test_explicit_net_quantity_labeled(self):
        """Explicit Net Quantity label pattern extracts with high confidence and valid status."""
        text = "Pure Desi Ghee\nNet Quantity: 500 ml\nMRP ₹350.00"
        fields = extract_declarations(text)
        qty = fields.get("DECLARED_NET_QUANTITY", {})

        assert qty.get("quantity_value") == "500"
        assert qty.get("quantity_unit") == "ml"
        assert qty.get("quantity_unit_valid") is True
        assert qty.get("semantic_section") == SECTION_DECLARED_QUANTITY
        assert qty.get("relevance_score") >= 0.85

    def test_net_quantity_missing_unit_fails_validation(self):
        """Net Qty: 500 (missing unit) has quantity_present=True, unit_present=False and fails validation."""
        text = "Pure Desi Ghee\nNet Qty: 500\nMRP ₹350.00"
        fields = extract_declarations(text)
        qty = fields.get("DECLARED_NET_QUANTITY", {})

        assert qty.get("quantity_value") == "500"
        assert qty.get("quantity_unit") is None
        assert qty.get("quantity_present") is True
        assert qty.get("unit_present") is False
        assert qty.get("quantity_unit_valid") is False

        # Rule validation must FAIL with binary 0
        rule = {"rule_id": "PC-ALL-001", "parameter": "DECLARED_NET_QUANTITY", "required": True, "validation_method": "VALUE_AND_UNIT_PRESENT"}
        res = validate_value_and_unit_present(qty, rule, fields)
        assert res.status == "FAIL"
        assert res.binary == 0
        assert "missing a legal unit" in res.reason.lower()

    def test_net_quantity_provenance_ignored_candidates(self):
        """Ignored candidates preserve audit provenance with reasons."""
        text = (
            "Net Weight: 250 g\n"
            "Nutrition Facts\n"
            "Carbohydrate 53.15 g\n"
            "Protein 10 g\n"
            "Serve size per 25g"
        )
        field = _extract_net_quantity_field(text)
        assert field is not None
        assert field["value"] == "250 g"
        assert "ignored_candidates" in field

        reasons = [c.get("rejection_reason") for c in field["ignored_candidates"]]
        assert any("nutritional table" in r.lower() for r in reasons if r)
        assert any("serving size" in r.lower() for r in reasons if r)

    def test_multi_image_nutrition_does_not_conflict_with_declared_quantity(self):
        """Image 1 (20 g) and Image 2 (53.15 g nutrition) must NOT cause TRUE_CONFLICT."""
        img1 = {
            "DECLARED_NET_QUANTITY": {
                "value": "20 g", "quantity_value": "20", "quantity_unit": "g",
                "semantic_section": SECTION_DECLARED_QUANTITY, "relevance": "high", "relevance_score": 0.95,
                "confidence": 0.9, "source": "OCR_IMAGE_1", "source_image_index": 0,
            }
        }
        img2 = {
            "DECLARED_NET_QUANTITY": {
                "value": "53.15 g", "quantity_value": "53.15", "quantity_unit": "g",
                "semantic_section": SECTION_NUTRITION, "relevance": "rejected_as_irrelevant", "relevance_score": 0.0,
                "confidence": 0.7, "source": "OCR_IMAGE_2", "source_image_index": 1,
                "source_context": "Carbohydrate 53.15 g per 100g",
            }
        }
        merged = merge_extracted_fields([img1, img2])
        qty = merged.get("DECLARED_NET_QUANTITY", {})

        assert qty.get("status") != "CONFLICTING_EVIDENCE"
        assert qty.get("has_conflict") is not True
        assert qty.get("value") == "20 g"
        assert "filtered_noise" in qty or "ignored_candidates" in qty or qty.get("value") == "20 g"

    def test_genuine_quantity_conflict_still_detected(self):
        """Genuine conflict between Net Wt 20 g and Net Wt 500 g across images is detected."""
        img1 = {
            "DECLARED_NET_QUANTITY": {
                "value": "20 g", "quantity_value": "20", "quantity_unit": "g",
                "semantic_section": SECTION_DECLARED_QUANTITY, "relevance": "high", "relevance_score": 0.95,
                "confidence": 0.9, "source": "OCR_IMAGE_1", "source_image_index": 0,
            }
        }
        img2 = {
            "DECLARED_NET_QUANTITY": {
                "value": "500 g", "quantity_value": "500", "quantity_unit": "g",
                "semantic_section": SECTION_DECLARED_QUANTITY, "relevance": "high", "relevance_score": 0.95,
                "confidence": 0.9, "source": "OCR_IMAGE_2", "source_image_index": 1,
            }
        }
        merged = merge_extracted_fields([img1, img2])
        qty = merged.get("DECLARED_NET_QUANTITY", {})

        assert qty.get("status") == "CONFLICTING_EVIDENCE"
        assert qty.get("has_conflict") is True
        assert qty.get("candidate_classification") == "TRUE_CONFLICT"


# ===========================================================================
# 2. Structured MRP Extraction & Validation (6 tests)
# ===========================================================================
class TestStructuredMRPExtractionAndValidation:

    def test_mrp_explicit_rupee_symbol(self):
        """MRP ₹120 yields currency_status=VERIFIED, status=PASS, binary=1."""
        text = "Product XYZ\nMRP ₹120.00\nNet Wt 100 g"
        fields = extract_declarations(text)
        mrp = fields.get("MRP", {})

        assert mrp.get("currency_status") == "VERIFIED"
        assert mrp.get("currency_symbol") == "₹"
        assert mrp.get("numeric_value") == 120.0
        assert mrp.get("status") == "PASS"
        assert mrp.get("binary") == 1

        rule = {"rule_id": "PC-ALL-002", "parameter": "MRP", "required": True, "validation_method": "MRP_PRESENT"}
        res = validate_mrp_present(mrp, rule, fields)
        assert res.status == "PASS"
        assert res.binary == 1
        assert res.normalized_value == "₹120.00"

    def test_mrp_rs_text(self):
        """MRP Rs. 120 yields currency_status=VERIFIED, status=PASS, binary=1."""
        text = "Product XYZ\nMRP Rs. 120\nNet Wt 100 g"
        fields = extract_declarations(text)
        mrp = fields.get("MRP", {})

        assert mrp.get("currency_status") == "VERIFIED"
        assert mrp.get("numeric_value") == 120.0
        assert mrp.get("status") == "PASS"
        assert mrp.get("binary") == 1

        rule = {"rule_id": "PC-ALL-002", "parameter": "MRP", "required": True, "validation_method": "MRP_PRESENT"}
        res = validate_mrp_present(mrp, rule, fields)
        assert res.status == "PASS"
        assert res.binary == 1

    def test_mrp_rs_bare(self):
        """Bare Rs 120 yields currency_status=VERIFIED, status=PASS, binary=1."""
        text = "Product XYZ\nRs 120\nNet Wt 100 g"
        fields = extract_declarations(text)
        mrp = fields.get("MRP", {})

        assert mrp.get("currency_status") == "VERIFIED"
        assert mrp.get("numeric_value") == 120.0
        assert mrp.get("binary") == 1

    def test_mrp_corrupted_symbol_square(self):
        """Corrupted symbol ■10.00 yields currency_status=UNKNOWN, status=REVIEW, binary=0."""
        text = "SWISSYUM FOODS\n■10.00\nNet Wt: 20 g"
        fields = extract_declarations(text)
        mrp = fields.get("MRP", {})

        assert mrp.get("currency_status") == "UNKNOWN"
        assert mrp.get("currency_symbol") is None
        assert mrp.get("numeric_value") == 10.0
        assert mrp.get("status") == "REVIEW"
        assert mrp.get("binary") == 0
        assert "■" in mrp.get("reason", "") or "corrupted" in mrp.get("reason", "").lower()

    def test_mrp_missing_currency_inferred(self):
        """MRP 120 (missing currency symbol) yields currency_status=INFERRED, status=REVIEW, binary=0."""
        text = "Product ABC\nMRP 120\nNet Wt: 100 g"
        fields = extract_declarations(text)
        mrp = fields.get("MRP", {})

        assert mrp.get("currency_status") == "INFERRED"
        assert mrp.get("currency_symbol") is None
        assert mrp.get("status") == "REVIEW"
        assert mrp.get("binary") == 0

    def test_mrp_corrupted_validator_evaluates_review(self):
        """Running validate_mrp_present on corrupted ■10.00 yields NOT_VERIFIABLE, binary=0."""
        evidence = {
            "raw_text": "■10.00",
            "value": "■10.00",
            "numeric_value": 10.0,
            "currency_status": "UNKNOWN",
            "status": "REVIEW",
            "binary": 0,
            "confidence": 0.6,
        }
        rule = {"rule_id": "PC-ALL-002", "parameter": "MRP", "required": True, "validation_method": "MRP_PRESENT"}
        res = validate_mrp_present(evidence, rule, {})

        assert res.status == "NOT_VERIFIABLE"
        assert res.binary == 0
        assert "corrupted" in res.reason.lower() or "review" in res.reason.lower()


# ===========================================================================
# 3. Manufacturer Address Boundary Enforcement (6 tests)
# ===========================================================================
class TestManufacturerAddressBoundaries:

    def test_address_stops_at_phone_contact(self):
        """Manufacturer address stops immediately before customer care / phone number."""
        text = (
            "Manufactured by: Swissyum Foods Pvt. Ltd.\n"
            "Plot 45, GIDC Industrial Estate, Vadodara, Gujarat 390010\n"
            "call us at 033 2222 3333 for feedback\n"
            "Net Wt: 20 g"
        )
        fields = extract_declarations(text)
        addr = fields.get("MANUFACTURER_ADDRESS", {}).get("value", "")

        assert "Vadodara" in addr
        assert "call us at" not in addr.lower()
        assert "033" not in addr

    def test_address_stops_at_toll_free(self):
        """Manufacturer address stops before toll free helpline."""
        text = (
            "Manufactured by: Golden Harvest Mills Ltd.\n"
            "Survey No. 12, Phase 1, Hinjewadi, Pune 411057\n"
            "Toll Free: 1800-200-3456\n"
            "Email: care@goldenharvest.test"
        )
        fields = extract_declarations(text)
        addr = fields.get("MANUFACTURER_ADDRESS", {}).get("value", "")

        assert "Hinjewadi" in addr
        assert "1800" not in addr
        assert "toll free" not in addr.lower()

    def test_address_stops_at_marketing_slogan(self):
        """Manufacturer address stops before marketing slogans like SWEET'N SOUR."""
        text = (
            "Manufactured by: Swissyum Foods Pvt. Ltd.\n"
            "Plot 45, GIDC Industrial Area, Vadodara 390010\n"
            "SWEET'N SOUR CRISPY SNACK\n"
            "Net Wt: 20 g"
        )
        fields = extract_declarations(text)
        addr = fields.get("MANUFACTURER_ADDRESS", {}).get("value", "")

        assert "Vadodara" in addr
        assert "sweet" not in addr.lower()
        assert "crispy" not in addr.lower()

    def test_address_stops_at_storage_instructions(self):
        """Manufacturer address stops before storage instructions."""
        text = (
            "Manufactured by: Organic Spices Pvt. Ltd.\n"
            "Lane 4, Spices Park, Kochi, Kerala 682001\n"
            "CONTAINER ONCE OPENED STORE IN COOL DRY PLACE\n"
            "Best Before 12 Months"
        )
        fields = extract_declarations(text)
        addr = fields.get("MANUFACTURER_ADDRESS", {}).get("value", "")

        assert "Kochi" in addr
        assert "container once opened" not in addr.lower()
        assert "cool dry place" not in addr.lower()

    def test_address_stops_at_nutrition_fragments(self):
        """Manufacturer address stops before serving size and nutrition fragments."""
        text = (
            "Manufactured by: Swissyum Foods Pvt. Ltd.\n"
            "Plot 45, GIDC, Vadodara 390010\n"
            "SERVE SIZE PER 20G\n"
            "Energy 100 kcal"
        )
        fields = extract_declarations(text)
        addr = fields.get("MANUFACTURER_ADDRESS", {}).get("value", "")

        assert "Vadodara" in addr
        assert "serve size" not in addr.lower()
        assert "kcal" not in addr.lower()

    def test_clean_address_helper(self):
        """_clean_address_text helper removes multiple noise fragments."""
        raw = "Plot 12, Industrial Area, Pune 411001, call us at 033 2222, SWEET'N SOUR, CONTAINER ONCE OPENED, SERVE SIZE PER 20G"
        cleaned = _clean_address_text(raw)
        assert "Plot 12, Industrial Area, Pune 411001" in cleaned
        assert "call us" not in cleaned.lower()
        assert "sweet" not in cleaned.lower()
        assert "container" not in cleaned.lower()
        assert "serve size" not in cleaned.lower()


# ===========================================================================
# 4. End-to-End & Multi-Image Regression (4 tests)
# ===========================================================================
class TestEndToEndAndMultiImageRegression:

    def test_real_world_multi_image_problem_case(self):
        """Simulate real-world inspection: Front panel (20 g) + Back panel (nutrition + clean address + corrupted MRP)."""
        front_text = (
            "SWISSYUM FOODS\n"
            "SWEET'N SOUR\n"
            "Net Wt: 20 g\n"
            "■10.00"
        )
        back_text = (
            "Manufactured by: Swissyum Foods Pvt. Ltd.\n"
            "Plot 45, GIDC Industrial Estate, Vadodara 390010\n"
            "call us at 033 2222 3333\n"
            "SERVE SIZE PER 20G\n"
            "Nutritional Information per 100g:\n"
            "Carbohydrate 53.15 g\n"
            "Energy 450 kcal"
        )

        front_fields = extract_declarations(front_text)
        back_fields = extract_declarations(back_text)

        merged = merge_extracted_fields([front_fields, back_fields])

        # 1. DECLARED_NET_QUANTITY must be 20 g, NO true conflict
        qty = merged.get("DECLARED_NET_QUANTITY", {})
        assert qty.get("status") != "CONFLICTING_EVIDENCE"
        assert qty.get("has_conflict") is not True
        assert qty.get("quantity_value") == "20"
        assert qty.get("quantity_unit") == "g"

        # 2. MANUFACTURER_ADDRESS must be clean without phone or slogans
        addr = merged.get("MANUFACTURER_ADDRESS", {}).get("value", "")
        assert "Vadodara" in addr
        assert "033" not in addr
        assert "call us" not in addr.lower()
        assert "serve size" not in addr.lower()

        # 3. MRP must be flagged for review due to ■
        mrp = merged.get("MRP", {})
        assert mrp.get("currency_status") == "UNKNOWN"
        assert mrp.get("status") == "REVIEW"
        assert mrp.get("binary") == 0

    def test_multi_image_identical_mrp_agreed(self):
        """Identical MRP across multiple images merges to agreed state."""
        img1 = {"MRP": {"value": "₹120.00", "numeric_value": 120.0, "currency_status": "VERIFIED", "status": "PASS", "binary": 1, "confidence": 0.9, "source": "OCR_1"}}
        img2 = {"MRP": {"value": "₹120.00", "numeric_value": 120.0, "currency_status": "VERIFIED", "status": "PASS", "binary": 1, "confidence": 0.88, "source": "OCR_2"}}
        merged = merge_extracted_fields([img1, img2])
        mrp = merged.get("MRP", {})

        assert mrp.get("status") != "CONFLICTING_EVIDENCE"
        assert mrp.get("value") == "₹120.00"

    def test_multi_image_mrp_conflict(self):
        """Different valid prices across images create TRUE_CONFLICT."""
        img1 = {"MRP": {"value": "₹120.00", "numeric_value": 120.0, "currency_status": "VERIFIED", "status": "PASS", "binary": 1, "confidence": 0.9, "source": "OCR_1"}}
        img2 = {"MRP": {"value": "₹150.00", "numeric_value": 150.0, "currency_status": "VERIFIED", "status": "PASS", "binary": 1, "confidence": 0.88, "source": "OCR_2"}}
        merged = merge_extracted_fields([img1, img2])
        mrp = merged.get("MRP", {})

        assert mrp.get("candidate_classification") == "TRUE_CONFLICT"
        assert mrp.get("status") == "CONFLICTING_EVIDENCE"
        assert mrp.get("has_conflict") is True

    def test_pipeline_end_to_end_rule_matrix_evaluation(self):
        """End-to-end evaluation with rule matrix correctly reflects status and binary ratings."""
        text = (
            "Supreme Harvest Sugar\n"
            "Net Weight: 1 kg\n"
            "MRP ₹60.00\n"
            "Manufactured by: Supreme Harvest Foods Pvt. Ltd.\n"
            "Plot 10, Sector 5, Pune 411018\n"
            "Consumer Care: 1800 123 4567\n"
            "FSSAI Lic No: 10014011002345"
        )
        fields = extract_declarations(text)

        rules = [
            {"rule_id": "PC-ALL-001", "parameter": "DECLARED_NET_QUANTITY", "required": True, "validation_method": "VALUE_AND_UNIT_PRESENT"},
            {"rule_id": "PC-ALL-002", "parameter": "MRP", "required": True, "validation_method": "MRP_PRESENT"},
            {"rule_id": "PC-ALL-003", "parameter": "MANUFACTURER_NAME", "required": True, "validation_method": "TEXT_PRESENT"},
            {"rule_id": "PC-ALL-004", "parameter": "MANUFACTURER_ADDRESS", "required": True, "validation_method": "TEXT_PRESENT"},
        ]

        results, overall = evaluate_rules(rules, fields)

        # All 4 rules should pass with binary 1
        for res in results:
            assert res["status"] == "PASS"
            assert res["binary"] == 1
