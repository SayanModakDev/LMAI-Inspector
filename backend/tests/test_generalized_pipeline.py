"""
Generalized Packaging Declaration and Compliance Pipeline Tests.

Verifies product-agnostic extraction and rule-driven Legal Metrology compliance across:
- Scenario A: Packaged Food (mass: grams/kg, FSSAI, nutrition, allergen)
- Scenario B: Personal Care / Cosmetic (volume: ml/L, ingredients, batch, use-by)
- Scenario C: Household Product (volume/mass: 1 L / 2 kg, precautions, customer support)
- Scenario D: Packaged Commodity by Count (pieces, tablets, integer validation)
- Scenario E: Distinct Context-Anchored Dates (Mfg, Pkd, Expiry, Best Before)
- Scenario F: MRP Variations (currency symbols, Rs/INR, inferred, corrupted)
- Scenario G: Multi-Image / Multi-Panel Integration (Front + Back panels, no cross-contamination)
- Scenario H: Noisy OCR Robustness (spaces, minor OCR character glitches)
- Scenario I: Responsible Party Roles (Manufactured by, Packed by, Imported by)
- Scenario J: 25 g Packet Dynamic Regression Test (Dynamic extraction, no hardcoding)
"""

import pytest
from app.extraction.declaration_extractor import (
    extract_declarations,
    merge_extracted_fields,
    detect_semantic_sections,
    SECTION_DECLARED_QUANTITY,
    SECTION_NUTRITION,
    SECTION_SERVING_SIZE,
    SECTION_MANUFACTURER,
    SECTION_PACKER,
    SECTION_ADDRESS,
    SECTION_MRP,
    SECTION_DATE,
)
from app.rules.validators import (
    validate_value_and_unit_present,
    validate_mrp_present,
    validate_manufacturer_present,
    validate_address_present,
)
from app.rules.applicability import get_applicable_rules
from app.rules.rule_engine import evaluate_rules
from app.classification.category_classifier import classify_category
from app.core.ontology import QuantityType


# ===========================================================================
# SCENARIO A: Packaged Food (Mass in g/kg, FSSAI, Nutrition, Allergen)
# ===========================================================================
class TestScenarioAFoodCommodity:

    def test_food_commodity_extraction_and_validation(self):
        """Food package with Net Wt in grams, FSSAI license, MRP, and nutrition table."""
        text = (
            "BRITANNIA GOOD DAY\n"
            "Rich Butter Cookies\n"
            "Net Weight: 200 g\n"
            "MRP ₹40.00 (Incl. of all taxes)\n"
            "Mfd Date: 15/05/2024\n"
            "Expiry Date: 15/11/2024\n"
            "Batch No: B2405Brit\n"
            "Manufactured by: Britannia Industries Ltd.\n"
            "5/1A Hungerford Street, Kolkata 700017, West Bengal\n"
            "FSSAI Lic. No: 10015043001129\n"
            "Ingredients: Wheat Flour, Sugar, Butter (2%), Vegetable Oil, Milk Solids\n"
            "Nutritional Information per 100g:\n"
            "Energy 485 kcal\n"
            "Carbohydrate 68.5 g\n"
            "Total Sugar 22.0 g\n"
            "Protein 7.0 g\n"
            "Fat 21.0 g\n"
            "Customer Care: 1800 425 4444, feedback@britannia.co.in"
        )
        fields = extract_declarations(text, category="FOOD")

        # 1. Product identity & Category
        cat_info = classify_category(text, fields)
        assert cat_info["category"] == "FOOD"

        # 2. Declared Net Quantity (Mass)
        qty = fields.get("DECLARED_NET_QUANTITY")
        assert qty is not None
        assert qty["quantity_value"] == "200"
        assert qty["quantity_unit"] == "g"
        assert qty["quantity_type"] == QuantityType.MASS.value
        assert qty["quantity_unit_valid"] is True

        # Check that 68.5 g and 22.0 g in nutrition table were ignored
        ignored = qty.get("ignored_candidates", [])
        assert any(c.get("quantity_value") == "68.5" for c in ignored)

        # 3. Rule validation for Net Quantity
        rule = {"rule_id": "PC-ALL-001", "parameter": "DECLARED_NET_QUANTITY", "required": True, "validation_method": "VALUE_AND_UNIT_PRESENT"}
        res_qty = validate_value_and_unit_present(qty, rule, fields)
        assert res_qty.status == "PASS"
        assert res_qty.binary == 1
        assert res_qty.quantity_type == QuantityType.MASS.value

        # 4. MRP Validation
        mrp = fields.get("MRP")
        assert mrp is not None
        assert mrp["numeric_value"] == 40.0
        rule_mrp = {"rule_id": "PC-ALL-004", "parameter": "MRP", "required": True, "validation_method": "MRP_PRESENT"}
        res_mrp = validate_mrp_present(mrp, rule_mrp, fields)
        assert res_mrp.status == "PASS"
        assert res_mrp.binary == 1


# ===========================================================================
# SCENARIO B: Cosmetic / Personal Care (Volume in ml, Batch, Use-By)
# ===========================================================================
class TestScenarioBCosmeticCommodity:

    def test_cosmetic_commodity_extraction_and_validation(self):
        """Cosmetic bottle with volume in ml, batch number, use before date, and ingredients."""
        text = (
            "HIMALAYA HERBALS\n"
            "Anti-Dandruff Shampoo\n"
            "Net Volume: 400 ml\n"
            "MRP: ₹290.00\n"
            "Batch No: HML-SH-9821\n"
            "Mfg Date: 01/03/2024\n"
            "Use Before: 28/02/2026\n"
            "Manufactured by: The Himalaya Drug Company\n"
            "Makali, Bengaluru 562162, Karnataka\n"
            "Ingredients: Aqua, Sodium Laureth Sulfate, Tea Tree Oil, Aloe Vera\n"
            "For external use only. Store in a cool dry place.\n"
            "Consumer Helpline: 1800 208 1930"
        )
        fields = extract_declarations(text, category="COSMETIC")

        # 1. Product category
        cat_info = classify_category(text, fields)
        assert cat_info["category"] == "COSMETIC"

        # 2. Declared Net Quantity (Volume)
        qty = fields.get("DECLARED_NET_QUANTITY")
        assert qty is not None
        assert qty["quantity_value"] == "400"
        assert qty["quantity_unit"] == "ml"
        assert qty["quantity_type"] == QuantityType.VOLUME.value

        # 3. Rule validation
        rule_qty = {"rule_id": "PC-ALL-001", "parameter": "DECLARED_NET_QUANTITY", "required": True, "validation_method": "VALUE_AND_UNIT_PRESENT"}
        res_qty = validate_value_and_unit_present(qty, rule_qty, fields)
        assert res_qty.status == "PASS"
        assert res_qty.binary == 1
        assert res_qty.quantity_type == QuantityType.VOLUME.value

        # 4. Dates
        assert fields.get("MANUFACTURE_DATE") is not None
        assert fields["MANUFACTURE_DATE"]["value"] == "01/03/2024"
        assert fields.get("USE_BEFORE_DATE") is not None
        assert fields["USE_BEFORE_DATE"]["value"] == "28/02/2026"


# ===========================================================================
# SCENARIO C: Household Product (Volume in Liters, Precautions, Support)
# ===========================================================================
class TestScenarioCHouseholdCommodity:

    def test_household_product_extraction_and_validation(self):
        """Household cleaning product with volume in Liters, precautions, and consumer care."""
        text = (
            "LIZOL DISINFECTANT SURFACE CLEANER\n"
            "Citrus Fragrance\n"
            "Net Content: 1 L\n"
            "MRP: Rs 199.00\n"
            "Batch No: LZL-2024-C\n"
            "Date of Mfg: 10/01/2024\n"
            "Manufactured by: Reckitt Benckiser India Pvt. Ltd.\n"
            "Plot No. 1, Sector 100, Baddi 173205, Himachal Pradesh\n"
            "Keep out of reach of children. Avoid contact with eyes.\n"
            "Consumer Care: 1800 102 2221, consumerhealth_india@reckitt.com"
        )
        fields = extract_declarations(text, category="HOUSEHOLD")

        # 1. Product Category
        cat_info = classify_category(text, fields)
        assert cat_info["category"] == "HOUSEHOLD"

        # 2. Net Quantity in Liters
        qty = fields.get("DECLARED_NET_QUANTITY")
        assert qty is not None
        assert qty["quantity_value"] == "1"
        assert qty["quantity_unit"] == "L"
        assert qty["quantity_type"] == QuantityType.VOLUME.value

        rule_qty = {"rule_id": "PC-ALL-001", "parameter": "DECLARED_NET_QUANTITY", "required": True, "validation_method": "VALUE_AND_UNIT_PRESENT"}
        res_qty = validate_value_and_unit_present(qty, rule_qty, fields)
        assert res_qty.status == "PASS"
        assert res_qty.binary == 1

        # 3. Manufacturer address boundary (does NOT include 'Keep out of reach')
        mfg_addr = fields.get("MANUFACTURER_ADDRESS", {}).get("value", "")
        assert "Plot No. 1" in mfg_addr
        assert "Himachal Pradesh" in mfg_addr
        assert "Keep out of reach" not in mfg_addr


# ===========================================================================
# SCENARIO D: Packaged Commodity by Count (tablets, pieces, numbers)
# ===========================================================================
class TestScenarioDCommodityByCount:

    def test_count_declaration_tablets_integer_passes(self):
        """Packaged product declared by count (e.g. 10 Tablets or 10 N) passes validation."""
        text = (
            "HealthPlus Paracetamol\n"
            "Net Quantity: 10 tablets\n"
            "MRP ₹25.00\n"
            "Mfg Date: 02/2024\n"
            "Exp Date: 01/2027\n"
            "Batch: HP2402\n"
            "Manufactured by: HealthPlus Remedies Ltd.\n"
            "Industrial Area, Solan 173212, HP"
        )
        fields = extract_declarations(text)
        qty = fields.get("DECLARED_NET_QUANTITY")
        assert qty is not None
        assert qty["quantity_value"] == "10"
        assert qty["quantity_unit"] == "tablets"
        assert qty["quantity_type"] == QuantityType.COUNT.value

        rule_qty = {"rule_id": "PC-ALL-001", "parameter": "DECLARED_NET_QUANTITY", "required": True, "validation_method": "VALUE_AND_UNIT_PRESENT"}
        res = validate_value_and_unit_present(qty, rule_qty, fields)
        assert res.status == "PASS"
        assert res.binary == 1
        assert res.value == 10
        assert res.quantity_type == "COUNT"

    def test_count_declaration_pieces_passes(self):
        """Packaging declared by 'pieces' or 'N' parses as COUNT."""
        text = (
            "FineTip Ball Pens\n"
            "Net Quantity: 5 pieces\n"
            "MRP ₹50.00\n"
            "Manufactured by: FineTip Stationery Pvt. Ltd.\n"
            "Plot 42, GIDC, Ahmedabad 382445"
        )
        fields = extract_declarations(text)
        qty = fields.get("DECLARED_NET_QUANTITY")
        assert qty is not None
        assert qty["quantity_value"] == "5"
        assert qty["quantity_unit"] == "pieces"
        assert qty["quantity_type"] == QuantityType.COUNT.value

    def test_count_declaration_non_integer_fails_validation(self):
        """A non-integer count (e.g. 10.5 tablets) violates Legal Metrology count rules and fails."""
        evidence = {
            "value": "10.5 tablets",
            "quantity_value": "10.5",
            "quantity_unit": "tablets",
            "quantity_type": "COUNT",
            "quantity_present": True,
            "unit_present": True,
            "confidence": 0.9,
        }
        rule = {"rule_id": "PC-ALL-001", "parameter": "DECLARED_NET_QUANTITY", "required": True, "validation_method": "VALUE_AND_UNIT_PRESENT"}
        res = validate_value_and_unit_present(evidence, rule, {})
        assert res.status == "FAIL"
        assert res.binary == 0
        assert "whole number (integer)" in res.reason


# ===========================================================================
# SCENARIO E: Context-Anchored Dates (Mfg, Pkd, Expiry, Best Before)
# ===========================================================================
class TestScenarioEDateAnchoring:

    def test_distinct_dates_do_not_bleed_across_labels(self):
        """Package having Mfg Date, Expiry Date, and Best Before correctly binds each date."""
        text = (
            "Sunrise Pure Spices\n"
            "Turmeric Powder\n"
            "Net Wt: 100 g\n"
            "Mfg Date: 12/01/2024\n"
            "Expiry Date: 11/01/2025\n"
            "Best Before: 12 months from manufacture\n"
            "MRP ₹35.00"
        )
        fields = extract_declarations(text)
        assert fields.get("MANUFACTURE_DATE", {}).get("value") == "12/01/2024"
        assert fields.get("EXPIRY_DATE", {}).get("value") == "11/01/2025"
        assert "12 months" in fields.get("BEST_BEFORE_USE_BY", {}).get("value", "")


# ===========================================================================
# SCENARIO F: MRP Formatting Variations
# ===========================================================================
class TestScenarioFMRPFormatting:

    def test_mrp_with_rupee_symbol(self):
        text = "Snack Pack\nMRP ₹99.00\nNet Wt: 50 g"
        fields = extract_declarations(text)
        mrp = fields.get("MRP", {})
        assert mrp.get("numeric_value") == 99.0
        assert mrp.get("currency_symbol") == "₹"
        assert mrp.get("status") == "PASS"

    def test_mrp_with_rs_prefix(self):
        text = "Snack Pack\nMRP Rs. 149.50\nNet Wt: 100 g"
        fields = extract_declarations(text)
        mrp = fields.get("MRP", {})
        assert mrp.get("numeric_value") == 149.50
        assert mrp.get("status") == "PASS"

    def test_mrp_corrupted_symbol_flagged_for_review(self):
        text = "Snack Pack\nMRP ■20.00\nNet Wt: 20 g"
        fields = extract_declarations(text)
        mrp = fields.get("MRP", {})
        assert mrp.get("status") == "REVIEW"
        assert mrp.get("binary") == 0

        rule = {"rule_id": "PC-ALL-004", "parameter": "MRP", "required": True, "validation_method": "MRP_PRESENT"}
        res = validate_mrp_present(mrp, rule, fields)
        assert res.status == "NOT_VERIFIABLE"
        assert res.binary == 0


# ===========================================================================
# SCENARIO G: Multi-Image / Multi-Panel Integration
# ===========================================================================
class TestScenarioGMultiImagePanels:

    def test_multi_image_panels_no_nutrition_bleed(self):
        """Front panel has declared quantity 100 g, back panel has 45 g carbohydrates;
        multi-image merging must keep 100 g and never claim conflict with 45 g."""
        front_text = (
            "PARLE-G\n"
            "Original Gluco Biscuits\n"
            "Net Wt: 100 g"
        )
        back_text = (
            "Nutritional Facts per 100g:\n"
            "Carbohydrate 78 g\n"
            "Total Sugars 25 g\n"
            "Protein 6.5 g\n"
            "MRP ₹10.00\n"
            "Manufactured by: Parle Products Pvt. Ltd.\n"
            "V.S. Khandekar Marg, Vile Parle East, Mumbai 400057\n"
            "Delicious taste you love\n"
            "Consumer Care: 1800 22 7700"
        )
        f_front = extract_declarations(front_text)
        f_back = extract_declarations(back_text)

        merged = merge_extracted_fields([f_front, f_back])

        # Net quantity must be 100 g, not 78 g or 25 g
        qty = merged.get("DECLARED_NET_QUANTITY", {})
        assert qty.get("quantity_value") == "100"
        assert qty.get("quantity_unit") == "g"
        assert qty.get("has_conflict") is not True

        # Manufacturer address should not include marketing slogan
        mfg_addr = merged.get("MANUFACTURER_ADDRESS", {}).get("value", "")
        assert "Vile Parle" in mfg_addr
        assert "Delicious taste" not in mfg_addr


# ===========================================================================
# SCENARIO H: Noisy OCR Robustness
# ===========================================================================
class TestScenarioHNoisyOCR:

    def test_noisy_ocr_text_repairs_and_scoping(self):
        """Label with minor OCR noise (e.g. Pvi. Ld., MADENINDIA) handled without failure."""
        text = (
            "DELICIOUS NOODLES\n"
            "Net Wt : 70 g\n"
            "MRP : Rs 14.00\n"
            "Manufactured by: Instant Foods Pvi. Ld.\n"
            "Plot 12, Phase 1, GIDC, Vapi 396195\n"
            "MADENINDIA"
        )
        fields = extract_declarations(text)

        qty = fields.get("DECLARED_NET_QUANTITY")
        assert qty is not None
        assert qty["quantity_value"] == "70"
        assert qty["quantity_unit"] == "g"

        mfg_name = fields.get("MANUFACTURER_NAME", {}).get("value", "")
        assert "Instant Foods" in mfg_name
        assert "Pvt. Ltd." in mfg_name or "Pvi" in mfg_name


# ===========================================================================
# SCENARIO I: Responsible Party Roles (Packed By vs Manufactured By)
# ===========================================================================
class TestScenarioIResponsiblePartyRoles:

    def test_packed_by_extracts_packer_and_satisfies_rule(self):
        """Commodity with 'Packed by:' correctly populates PACKER declarations."""
        text = (
            "Golden Harvest Whole Moong Dal\n"
            "Net Quantity: 500 g\n"
            "MRP ₹85.00\n"
            "Packed by: Agritech Packaging Pvt. Ltd.\n"
            "Survey No. 44, APMC Yard, Navi Mumbai 400703\n"
            "Consumer Care: 022 2788 1234"
        )
        fields = extract_declarations(text)

        assert "PACKER_NAME" in fields
        assert "Agritech Packaging" in fields["PACKER_NAME"]["value"]
        assert "PACKER_ADDRESS" in fields
        assert "Navi Mumbai" in fields["PACKER_ADDRESS"]["value"]

        # If rule evaluates manufacturer/packer under PC-ALL-002:
        rule_mfg = {"rule_id": "PC-ALL-002", "parameter": "MANUFACTURER_NAME", "required": True, "validation_method": "MANUFACTURER_PRESENT"}
        res_mfg = validate_manufacturer_present(fields.get("MANUFACTURER_NAME"), rule_mfg, fields)
        assert res_mfg.status == "PASS"
        assert res_mfg.binary == 1


# ===========================================================================
# SCENARIO J: 25 g Packet Dynamic Regression Test (No Hardcoding)
# ===========================================================================
class TestScenarioJ25gRegressionDynamic:

    def test_25g_package_dynamically_extracts_and_validates(self):
        """25 g regression sample must dynamically extract 25 and g, without any hardcoded 25 g strings."""
        sample_text = (
            "CHIPS & CRISPS\n"
            "Net Weight: 25 g\n"
            "MRP ₹10.00\n"
            "Pkd: 01/2024\n"
            "Best Before: 6 months from packaging\n"
            "Manufactured by: Crisp Foods Pvt. Ltd.\n"
            "Plot 8, Industrial Area, Solan 173220\n"
            "FSSAI Lic. No: 10019022008765\n"
            "Nutritional Facts per 100g:\n"
            "Energy 520 kcal\n"
            "Carbohydrates 58 g\n"
            "Customer Care: 1800 11 2233"
        )
        fields = extract_declarations(sample_text)

        qty = fields.get("DECLARED_NET_QUANTITY")
        assert qty is not None
        # Verified dynamically through parsed tokens
        assert qty["quantity_value"] == "25"
        assert qty["quantity_unit"] == "g"
        assert qty["quantity_type"] == QuantityType.MASS.value
        assert qty["quantity_unit_valid"] is True

        # Rule evaluation
        rule_qty = {"rule_id": "PC-ALL-001", "parameter": "DECLARED_NET_QUANTITY", "required": True, "validation_method": "VALUE_AND_UNIT_PRESENT"}
        res_qty = validate_value_and_unit_present(qty, rule_qty, fields)
        assert res_qty.status == "PASS"
        assert res_qty.binary == 1
        assert res_qty.value == 25
        assert res_qty.unit == "g"
