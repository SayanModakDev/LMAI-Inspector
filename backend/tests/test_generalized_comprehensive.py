"""Comprehensive synthetic unit and integration tests for Generalized Packaged-Product Inspection Pipeline.

Tests Categories A through I:
A. Quantity Context Scoping
B. Mass, Volume, and Count Handling
C. Labels and Wording Variants
D. Date Semantics and Provenance
E. Responsible Parties and Address Boundaries
F. MRP Extraction and Normalization
G. Multi-Image Evidence Merging
H. Category Applicability and Rule Isolation
I. Dynamic Report Generation (diverse synthetic payloads)
"""
import base64
import os
import re
import zlib
import pytest

from app.core.ontology import CanonicalDeclarationField, QuantityType
from app.extraction.declaration_extractor import (
    extract_declarations,
    _extract_batch_number,
    _extract_mrp_structured,
    _extract_net_quantity_field,
)
from app.classification.category_classifier import classify_category
from app.rules.applicability import get_applicable_rules
from app.rules.validators import (
    validate_value_and_unit_present,
    validate_mrp_present,
    validate_batch_number_present,
    validate_date_present,
)
from app.reports.pdf_report import generate_inspection_pdf, STATUTORY_DISCLAIMER
from app.database import models
from app.database.connection import SessionLocal


def _extract_pdf_text(file_path: str) -> str:
    """Decompress and decode text streams from a ReportLab PDF."""
    with open(file_path, 'rb') as f:
        raw = f.read()

    pos = 0
    all_text = []
    while True:
        pos = raw.find(b'stream\n', pos)
        if pos == -1:
            break
        end = raw.find(b'endstream', pos)
        data = raw[pos + 7:end].strip()
        try:
            raw_dec = base64.a85decode(data, adobe=True)
            dec = zlib.decompress(raw_dec).decode('latin1', errors='ignore')
            all_text.append(dec)
        except Exception:
            try:
                dec = zlib.decompress(data).decode('latin1', errors='ignore')
                all_text.append(dec)
            except Exception:
                pass
        pos = end + 9
    return "\n".join(all_text)


def _get_page_count(file_path: str) -> int:
    with open(file_path, 'rb') as f:
        content = f.read().decode('latin1', errors='ignore')
    return len(re.findall(r'/Type\s*/Page\b', content))


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# CATEGORY A: QUANTITY CONTEXT SCOPING
# =============================================================================
class TestCategoryAQuantityContext:
    def test_declared_quantity_preferred_over_nutrition_and_serving(self):
        """Ensure package declaration (750 g) is picked, not serving size or nutrition."""
        text = (
            "ORGANIC HARVEST\n"
            "Rolled Oats\n"
            "NET WEIGHT: 750 g\n"
            "Serving Size: 30 g\n"
            "Servings per container: 25\n"
            "Nutritional Facts per 100g:\n"
            "Carbohydrates: 68.5 g\n"
            "Dietary Fiber: 10.2 g\n"
            "Protein: 13.5 g\n"
            "Total Sugar: 1.2 g\n"
            "Ingredients: 100% Whole Grain Rolled Oats (contains 5g added bran)\n"
            "MRP: ₹340.00"
        )
        fields = extract_declarations(text, category="FOOD")
        assert 'DECLARED_NET_QUANTITY' in fields
        qty = fields['DECLARED_NET_QUANTITY']
        assert float(qty['numeric_value']) == 750.0
        assert qty['unit'] == 'g'
        assert qty['quantity_type'] == QuantityType.MASS

        # Verify nutrition was not selected
        assert float(qty['numeric_value']) not in (30.0, 68.5, 10.2, 13.5, 1.2, 5.0)

    def test_only_nutrition_no_declared_quantity(self):
        """When only nutrition values appear without net quantity label, declared net quantity is absent."""
        text = (
            "Nutritional Information (per 100g):\n"
            "Energy: 450 kcal\n"
            "Carbohydrate: 55.4 g\n"
            "Fat: 18.2 g\n"
            "Protein: 7.8 g"
        )
        fields = extract_declarations(text, category="FOOD")
        assert 'DECLARED_NET_QUANTITY' not in fields


# =============================================================================
# CATEGORY B: MASS, VOLUME, AND COUNT HANDLING
# =============================================================================
class TestCategoryBMassVolumeCount:
    def test_mass_unit_kilograms(self):
        text = "WHEAT FLOUR\nNet Wt: 5 kg\nMRP: ₹250.00"
        fields = extract_declarations(text, category="FOOD")
        qty = fields['DECLARED_NET_QUANTITY']
        assert float(qty['numeric_value']) == 5.0
        assert qty['unit'] == 'kg'
        assert qty['quantity_type'] == QuantityType.MASS

        res = validate_value_and_unit_present(qty, {}, fields)
        assert res.status == "PASS"
        assert res.binary == 1

    def test_volume_unit_litres(self):
        text = "SUNFLOWER EDIBLE OIL\nNet Volume: 1 L\nMRP: ₹165.00"
        fields = extract_declarations(text, category="FOOD")
        qty = fields['DECLARED_NET_QUANTITY']
        assert float(qty['numeric_value']) == 1.0
        assert qty['unit'] in ('l', 'L')
        assert qty['quantity_type'] == QuantityType.VOLUME

        res = validate_value_and_unit_present(qty, {}, fields)
        assert res.status == "PASS"
        assert res.binary == 1

    def test_count_unit_tablets_integer_passes(self):
        text = "ANTACID TABLETS\nNet Quantity: 30 tablets\nMRP: ₹90.00"
        fields = extract_declarations(text, category="OTHER")
        qty = fields['DECLARED_NET_QUANTITY']
        assert float(qty['numeric_value']) == 30.0
        assert qty['quantity_type'] == QuantityType.COUNT

        res = validate_value_and_unit_present(qty, {}, fields)
        assert res.status == "PASS"
        assert res.binary == 1

    def test_count_unit_fractional_fails_integer_check(self):
        """Statutory count units must be positive integers."""
        candidate = {
            "value": "12.5 tablets",
            "raw_value": "12.5 tablets",
            "numeric_value": 12.5,
            "quantity_value": "12.5",
            "unit": "tablets",
            "quantity_type": "COUNT",
            "quantity_present": True,
            "unit_present": True,
            "quantity_unit_valid": True,
        }
        res = validate_value_and_unit_present(candidate, {}, {})
        assert res.status == "FAIL"
        assert res.binary == 0
        assert "integer" in res.reason.lower()


# =============================================================================
# CATEGORY C: LABELS AND WORDING VARIANTS
# =============================================================================
class TestCategoryCLabelsAndWording:
    @pytest.mark.parametrize("label_str, expected_val, expected_unit", [
        ("Net Wt.: 500g", 500.0, "g"),
        ("Net Weight = 250 g", 250.0, "g"),
        ("NET QTY : 1 kg", 1.0, "kg"),
        ("Net Contents - 200 ml", 200.0, "ml"),
        ("Net Volume: 500 ml", 500.0, "ml"),
        ("Quantity: 100 g", 100.0, "g"),
    ])
    def test_label_variations_extracted_accurately(self, label_str, expected_val, expected_unit):
        text = f"PRODUCT SAMPLE\n{label_str}\nMRP: ₹99.00"
        fields = extract_declarations(text)
        assert 'DECLARED_NET_QUANTITY' in fields
        qty = fields['DECLARED_NET_QUANTITY']
        assert float(qty['numeric_value']) == expected_val
        assert qty['unit'] == expected_unit


# =============================================================================
# CATEGORY D: DATE SEMANTICS AND PROVENANCE
# =============================================================================
class TestCategoryDDatesAndProvenance:
    def test_dates_inherit_semantics_from_labels(self):
        """Date semantics are determined strictly by context labels, not date string format."""
        text = (
            "BISCUITS\n"
            "Mfg Date: 15/01/2024\n"
            "Packing Date: 18/01/2024\n"
            "Best Before: 6 months from packaging\n"
            "Use By: 15/07/2024\n"
            "Expiry Date: 20/07/2024\n"
            "Net Wt: 200 g"
        )
        fields = extract_declarations(text, category="FOOD")
        assert 'MANUFACTURE_DATE' in fields
        assert fields['MANUFACTURE_DATE']['value'] == "15/01/2024"
        assert fields['MANUFACTURE_DATE']['semantic_type'] == "MANUFACTURE_DATE"
        assert fields['MANUFACTURE_DATE']['raw_date'] == "15/01/2024"

        assert 'PACKING_DATE' in fields
        assert fields['PACKING_DATE']['value'] == "18/01/2024"
        assert fields['PACKING_DATE']['semantic_type'] == "PACKING_DATE"

        assert 'BEST_BEFORE_USE_BY' in fields
        assert "6 months" in fields['BEST_BEFORE_USE_BY']['value'].lower()

        assert 'USE_BEFORE_DATE' in fields
        assert fields['USE_BEFORE_DATE']['value'] == "15/07/2024"

        assert 'EXPIRY_DATE' in fields
        assert fields['EXPIRY_DATE']['value'] == "20/07/2024"

    def test_batch_number_separates_label_from_identifier(self):
        """Batch extraction extracts only the alphanumeric value and rejects 'NO' or 'NUMBER'."""
        text1 = "Batch No: B9021\nMfg Date: 01/2024"
        fields1 = extract_declarations(text1)
        assert 'BATCH_NUMBER' in fields1
        assert fields1['BATCH_NUMBER']['value'] == "B9021"

        # Multiline batch label
        text2 = "Batch Number:\nLOT-2024-X\nMfg Date: 01/2024"
        fields2 = extract_declarations(text2)
        assert 'BATCH_NUMBER' in fields2
        assert fields2['BATCH_NUMBER']['value'] == "LOT-2024-X"

    def test_batch_validator_rejects_lone_label_word(self):
        """Validator rejects values like 'NO' or 'NUMBER' as batch identifiers."""
        res = validate_batch_number_present({"value": "NO"}, {}, {})
        assert res.status == "FAIL"
        assert res.binary == 0

        res2 = validate_batch_number_present({"value": "NUMBER"}, {}, {})
        assert res2.status == "FAIL"
        assert res2.binary == 0

        res3 = validate_batch_number_present({"value": "B-4421"}, {}, {})
        assert res3.status == "PASS"
        assert res3.binary == 1


# =============================================================================
# CATEGORY E: RESPONSIBLE PARTIES AND ADDRESS BOUNDARIES
# =============================================================================
class TestCategoryEResponsibleParties:
    def test_address_boundary_truncation_before_noise(self):
        """Address extraction stops before contact phones, slogans, or nutrition info."""
        text = (
            "Manufactured by: CleanHome Solutions Pvt Ltd\n"
            "Plot No. 42, Industrial Area Phase II, Mohali 160055, Punjab\n"
            "Customer Care: 1800-111-222\n"
            "Keep in a cool dry place\n"
            "Makes your floor shine like diamond!"
        )
        fields = extract_declarations(text, category="HOUSEHOLD")
        assert 'MANUFACTURER_NAME' in fields
        assert "CleanHome Solutions" in fields['MANUFACTURER_NAME']['value']
        assert 'MANUFACTURER_ADDRESS' in fields
        addr = fields['MANUFACTURER_ADDRESS']['value']
        assert "Mohali" in addr
        assert "1800" not in addr
        assert "diamond" not in addr.lower()


# =============================================================================
# CATEGORY F: MRP EXTRACTION AND NORMALIZATION
# =============================================================================
class TestCategoryFMRPExtraction:
    def test_valid_rupee_symbol_passes(self):
        text = "NET WT: 100 g\nMRP: ₹149.00 (incl. of all taxes)"
        fields = extract_declarations(text)
        assert 'MRP' in fields
        assert fields['MRP']['currency_status'] == "VERIFIED"
        res = validate_mrp_present(fields['MRP'], {}, fields)
        assert res.status == "PASS"
        assert res.binary == 1

    def test_corrupted_symbol_flagged_for_review(self):
        """Unmapped glyph ■ flags currency as UNKNOWN and returns REVIEW / binary 0."""
        text = "NET WT: 100 g\nMRP: ■10.00"
        fields = extract_declarations(text)
        assert 'MRP' in fields
        mrp = fields['MRP']
        assert mrp.get('status') == "REVIEW" or mrp.get('currency_status') == "UNKNOWN"
        res = validate_mrp_present(mrp, {}, fields)
        assert res.status == "NOT_VERIFIABLE"
        assert res.binary == 0


# =============================================================================
# CATEGORY G: MULTI-IMAGE EVIDENCE MERGING
# =============================================================================
class TestCategoryGMultiImageEvidence:
    def test_complementary_panels_merged(self):
        """Panel 1 provides front identity & quantity, Panel 2 provides pricing & manufacturer."""
        text_panel1 = (
            "HERBAL SHAMPOO\n"
            "Net Volume: 250 ml"
        )
        text_panel2 = (
            "MRP: ₹195.00\n"
            "Batch No: B-991\n"
            "Manufactured by: Herbal Care Ltd\n"
            "Dehradun, Uttarakhand"
        )
        f1 = extract_declarations(text_panel1, category="COSMETIC")
        f2 = extract_declarations(text_panel2, category="COSMETIC")

        merged = {**f1, **f2}
        assert 'DECLARED_NET_QUANTITY' in merged
        assert float(merged['DECLARED_NET_QUANTITY']['numeric_value']) == 250.0
        assert 'MRP' in merged
        assert 'MANUFACTURER_NAME' in merged


# =============================================================================
# CATEGORY H: CATEGORY APPLICABILITY AND RULE ISOLATION
# =============================================================================
class TestCategoryHApplicability:
    def test_food_rules_do_not_leak_into_cosmetics(self, db_session):
        """Food-only rules (FSSAI license, Veg/Non-Veg) must not apply to COSMETIC products."""
        all_rules = [r.__dict__ for r in db_session.query(models.Rule).all()]
        food_rules = get_applicable_rules(all_rules, category="FOOD", package_type="RETAIL", import_status="DOMESTIC")
        cosmetic_rules = get_applicable_rules(all_rules, category="COSMETIC", package_type="RETAIL", import_status="DOMESTIC")

        food_params = {r.get('parameter') for r in food_rules}
        cosmetic_params = {r.get('parameter') for r in cosmetic_rules}

        assert "FSSAI_LICENSE" in food_params
        assert "VEG_NONVEG_SYMBOL" in food_params

        assert "FSSAI_LICENSE" not in cosmetic_params
        assert "VEG_NONVEG_SYMBOL" not in cosmetic_params


# =============================================================================
# CATEGORY I: DYNAMIC REPORT GENERATION ACROSS DIVERSE PAYLOADS
# =============================================================================
class TestCategoryIDynamicReportGeneration:
    def test_cosmetic_payload_generates_dynamic_pdf(self, db_session):
        """Inspect dynamic generation for synthetic cosmetic product."""
        insp = models.Inspection(
            product_name="Glow Skin Deep Moisture Cream",
            brand="Lumina Glow",
            category="COSMETIC",
            product_type="FACE_CREAM",
            package_type="RETAIL",
            import_status="DOMESTIC",
            overall_result="COMPLIANT",
            inspector_name="Inspector Ananya Rao",
        )
        db_session.add(insp)
        db_session.commit()
        db_session.refresh(insp)

        rr1 = models.RuleResult(
            inspection_id=insp.id,
            rule_id="PC-ALL-001",
            parameter="PRODUCT_NAME",
            status="PASS",
            message="1 — PASS: Product name declaration verified",
            evidence_data={"value": "Glow Skin Deep Moisture Cream", "binary": 1},
            regulatory_source="LEGAL_METROLOGY",
        )
        rr2 = models.RuleResult(
            inspection_id=insp.id,
            rule_id="PC-ALL-002",
            parameter="DECLARED_NET_QUANTITY",
            status="PASS",
            message="1 — PASS: Net content declared with valid unit",
            evidence_data={"value": "100", "unit": "g", "quantity_unit_valid": True, "binary": 1},
            regulatory_source="LEGAL_METROLOGY",
        )
        db_session.add_all([rr1, rr2])
        db_session.commit()

        report = generate_inspection_pdf(insp, db_session)
        assert report is not None
        assert os.path.exists(report.file_path)
        assert _get_page_count(report.file_path) == 4

        pdf_text = _extract_pdf_text(report.file_path)
        assert "Lumina Glow" in pdf_text
        assert "Glow Skin Deep Moisture Cream" in pdf_text
        assert "COSMETIC" in pdf_text
        assert STATUTORY_DISCLAIMER in pdf_text

    def test_household_payload_generates_dynamic_pdf(self, db_session):
        """Inspect dynamic generation for synthetic household cleaner product."""
        insp = models.Inspection(
            product_name="Sparkle Dishwash Liquid Lemon 500ml",
            brand="Sparkle Clean",
            category="HOUSEHOLD",
            product_type="CLEANER",
            package_type="RETAIL",
            import_status="DOMESTIC",
            overall_result="COMPLIANT",
            inspector_name="Inspector Vikram Sen",
        )
        db_session.add(insp)
        db_session.commit()
        db_session.refresh(insp)

        rr = models.RuleResult(
            inspection_id=insp.id,
            rule_id="PC-ALL-002",
            parameter="DECLARED_NET_QUANTITY",
            status="PASS",
            message="1 — PASS: Net content declared with valid unit",
            evidence_data={"value": "500", "unit": "ml", "quantity_unit_valid": True, "binary": 1},
            regulatory_source="LEGAL_METROLOGY",
        )
        db_session.add(rr)
        db_session.commit()

        report = generate_inspection_pdf(insp, db_session)
        assert report is not None
        assert os.path.exists(report.file_path)
        assert _get_page_count(report.file_path) == 4

        pdf_text = _extract_pdf_text(report.file_path)
        assert "Sparkle Clean" in pdf_text
        assert "HOUSEHOLD" in pdf_text
