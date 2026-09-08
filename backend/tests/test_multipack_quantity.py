"""
Universal Multipack & Package-Quantity Semantic Tests.

Validates:
A. Single quantity declarations (Q UNIT -> qty=Q, unit=UNIT, pack_count=None)
B. Standard multipack declarations (N × Q UNIT -> pack_count=N, unit_quantity=Q, unit=UNIT)
C. Volume multipack declarations (N × Q ml -> pack_count=N, unit_quantity=Q, unit=ml)
D. Spacing and typographical variations (N x Q, N X Q, N×Q, N * Q, N packs of Q, Q UNIT × N)
E. Nutrition contamination immunity (serving / nutrition table numbers never hijack package quantity)
F. Multi-panel conflicting declarations produce structured review state
G. Incomplete / invalid expressions are rejected without fabricating false quantities
H. Single package regression continuity
I. Legal Metrology rule validation (PC-ALL-002) with binary pass/fail
J. Packaging hierarchy (outer package vs inner unit)
"""

import pytest
from typing import Dict, Any

from app.core.ontology import build_quantity_candidate
from app.extraction.declaration_extractor import (
    parse_quantity_expression,
    _extract_net_quantity_field,
    merge_extracted_fields,
    _values_conflict,
)
from app.rules.validators import validate_declared_net_quantity


# ===========================================================================
# A. Single Quantity Parsing & Extraction
# ===========================================================================
class TestSingleQuantity:

    def test_single_quantity_parsing(self):
        """Pattern 'Q UNIT' parses with quantity=Q, unit=UNIT, pack_count=None."""
        parsed = parse_quantity_expression("250 g")
        assert parsed is not None
        assert parsed["is_multipack"] is False
        assert parsed["quantity"] == 250
        assert parsed["unit"] == "g"
        assert parsed["pack_count"] is None
        assert parsed["unit_net_quantity"] is None
        assert parsed["derived_total_quantity"] is None

    def test_single_quantity_field_extraction(self):
        """Single quantity line extracts cleanly without multipack flags."""
        text = "Net Weight: 500 g"
        field = _extract_net_quantity_field(text)
        assert field is not None
        assert field["value"] == "500 g"
        assert field["quantity_value"] == "500"
        assert field["quantity_unit"] == "g"
        assert field["is_multipack"] is False
        assert field["pack_count"] is None
        assert field["unit_net_quantity"] is None


# ===========================================================================
# B. Standard Multipack Parsing & Extraction
# ===========================================================================
class TestMultipackStandard:

    @pytest.mark.parametrize("expr,expected_count,expected_qty,expected_unit,expected_derived", [
        ("12 × 25 g", 12, 25, "g", 300),
        ("6 × 100 g", 6, 100, "g", 600),
        ("4 × 500 g", 4, 500, "g", 2000),
        ("3 × 1 kg", 3, 1, "kg", 3),
        ("8 × 12.5 g", 8, 12.5, "g", 100),
    ])
    def test_standard_multipack_patterns(self, expr, expected_count, expected_qty, expected_unit, expected_derived):
        """Test generic COUNT × UNIT QUANTITY structures."""
        parsed = parse_quantity_expression(expr)
        assert parsed is not None
        assert parsed["is_multipack"] is True
        assert parsed["pack_count"] == expected_count
        assert parsed["unit_net_quantity"] == expected_qty
        assert parsed["unit_quantity"] == expected_qty
        assert parsed["unit"] == expected_unit
        assert parsed["derived_total_quantity"] == expected_derived

    def test_count_never_collapses_to_net_quantity(self):
        """CRITICAL: '12 × 25 g' must NOT map 12 to net quantity or become '12 g'."""
        text = "Net Wt: 12 × 25 g"
        field = _extract_net_quantity_field(text)
        assert field is not None
        assert field["is_multipack"] is True
        assert field["pack_count"] == 12
        assert field["unit_net_quantity"] == 25
        assert field["unit"] == "g"
        # Legacy compatibility: quantity_value is unit quantity, NEVER pack count!
        assert field["quantity_value"] == "25"
        assert field["quantity_value"] != "12"
        # Display value retains original declaration
        assert "12" in field["value"] and "25" in field["value"]
        assert field["value"] != "12 g"

    def test_derived_total_provenance(self):
        """Derived total is clearly marked as DERIVED, never replacing printed declaration."""
        text = "Net Weight: 12 × 25 g"
        field = _extract_net_quantity_field(text)
        assert field is not None
        assert field["derived_total_quantity"] == 300
        prov = field.get("derived_total_provenance")
        assert prov is not None
        assert prov["source"] == "DERIVED"
        assert "12 × 25" in prov["formula"]
        # Printed declaration source is OCR
        assert field["declared_expression_source"]["source"] == "OCR"


# ===========================================================================
# C. Volume Multipack Parsing & Extraction
# ===========================================================================
class TestMultipackVolume:

    @pytest.mark.parametrize("expr,expected_count,expected_qty,expected_unit,expected_derived", [
        ("24 × 200 ml", 24, 200, "ml", 4800),
        ("10 × 50 ml", 10, 50, "ml", 500),
        ("6 × 1 L", 6, 1, "L", 6),
        ("12 × 330 ml", 12, 330, "ml", 3960),
    ])
    def test_volume_multipack_patterns(self, expr, expected_count, expected_qty, expected_unit, expected_derived):
        """Test generic volume multipack structures."""
        parsed = parse_quantity_expression(expr)
        assert parsed is not None
        assert parsed["is_multipack"] is True
        assert parsed["pack_count"] == expected_count
        assert parsed["unit_net_quantity"] == expected_qty
        assert parsed["unit"] == expected_unit
        assert parsed["derived_total_quantity"] == expected_derived

    def test_volume_extraction_from_labeled_line(self):
        """Test volume extraction from labeled commodity line."""
        text = "Net Volume: 24 × 200 ml"
        field = _extract_net_quantity_field(text)
        assert field is not None
        assert field["is_multipack"] is True
        assert field["pack_count"] == 24
        assert field["unit_net_quantity"] == 200
        assert field["unit"] == "ml"
        assert field["quantity_value"] == "200"
        assert field["quantity_value"] != "24"


# ===========================================================================
# D. Spacing & Typographical Variations
# ===========================================================================
class TestSpacingVariations:

    @pytest.mark.parametrize("expr", [
        "12 × 25 g",    # Unicode multiplication sign with spaces
        "12 x 25 g",    # ASCII lowercase x with spaces
        "12 X 25 g",    # ASCII uppercase X with spaces
        "12×25 g",      # Unicode multiplication sign without leading space
        "12x25 g",      # ASCII x without leading space
        "12x25g",       # Compact without spaces
        "12X25 ml",     # Uppercase X compact
        "12 * 25 g",    # Asterisk
        "12 pk × 25 g", # Count descriptor pk
        "12 packs of 25 g", # Wording 'packs of'
        "12 units of 25 g", # Wording 'units of'
        "12 N × 25 g",  # Statutory count unit N
        "25 g × 12",    # Inverted order
        "25 g x 12 packs", # Inverted with packs
    ])
    def test_multipack_spacing_variations(self, expr):
        """Every spacing and character variation parses count=12, qty=25."""
        parsed = parse_quantity_expression(expr)
        assert parsed is not None, f"Failed to parse variation: {expr}"
        assert parsed["is_multipack"] is True
        assert parsed["pack_count"] == 12
        assert parsed["unit_net_quantity"] == 25
        assert parsed["unit"] in ("g", "ml")


# ===========================================================================
# E. Contextual Quantity Filtering (Nutrition Contamination Immunity)
# ===========================================================================
class TestContextualFiltering:

    def test_nutrition_table_cannot_hijack_multipack_declaration(self):
        """A document with nutritional table numbers and a multipack declaration selects the multipack."""
        doc = (
            "BRAND PREMIUM COOKIES\n"
            "Nutritional Information per 100g:\n"
            "Energy 450 kcal\n"
            "Carbohydrate 68 g\n"
            "Protein 8.5 g\n"
            "Total Fat 18 g\n"
            "Serve size: 25 g\n"
            "Net Quantity: 12 × 25 g\n"
            "MRP: Rs. 120.00"
        )
        field = _extract_net_quantity_field(doc)
        assert field is not None
        assert field["is_multipack"] is True
        assert field["pack_count"] == 12
        assert field["unit_net_quantity"] == 25
        assert field["unit"] == "g"
        assert field["quantity_value"] == "25"
        # Ensure nutrition numbers did not hijack
        assert field["quantity_value"] not in ("68", "8.5", "18", "450")
        assert "ignored_candidates" in field
        # Verify nutrition candidates were logged as ignored
        assert any(c.get("semantic_section") in ("NUTRITION", "SERVING_SIZE") for c in field["ignored_candidates"])

    def test_standalone_multipack_outside_nutrition_selected(self):
        """Standalone multipack without explicit label is selected over nutrition table."""
        doc = (
            "NUTRITIONAL FACTS\n"
            "Energy 200 kcal\n"
            "Fat 10 g\n"
            "Carb 30 g\n"
            "12 × 25 g\n"
            "Batch No: B123"
        )
        field = _extract_net_quantity_field(doc)
        assert field is not None
        assert field["is_multipack"] is True
        assert field["pack_count"] == 12
        assert field["unit_net_quantity"] == 25


# ===========================================================================
# F. Multiple Quantity Candidates & Conflict Resolution
# ===========================================================================
class TestCandidateConflicts:

    def test_multi_image_divergent_multipack_declarations_conflict(self):
        """Panel 1 declaring 12 × 25 g and Panel 2 declaring 24 × 50 ml produce conflict review."""
        panel1 = {
            "DECLARED_NET_QUANTITY": build_quantity_candidate(
                qty_val=25, raw_unit="g", raw_span="12 × 25 g",
                is_multipack=True, pack_count=12, unit_net_quantity=25,
                declared_expression="12 × 25 g", derived_total_quantity=300,
                source="OCR_IMAGE_1",
            )
        }
        panel2 = {
            "DECLARED_NET_QUANTITY": build_quantity_candidate(
                qty_val=50, raw_unit="ml", raw_span="24 × 50 ml",
                is_multipack=True, pack_count=24, unit_net_quantity=50,
                declared_expression="24 × 50 ml", derived_total_quantity=1200,
                source="OCR_IMAGE_2",
            )
        }

        merged = merge_extracted_fields([panel1, panel2])
        qty = merged.get("DECLARED_NET_QUANTITY", {})

        assert qty.get("status") == "CONFLICTING_EVIDENCE"
        assert qty.get("has_conflict") is True
        assert qty.get("review_required") is True

    def test_multi_image_identical_multipacks_agree(self):
        """Panel 1 declaring 12 × 25 g and Panel 2 declaring 12 × 25 g agree without conflict."""
        panel1 = {
            "DECLARED_NET_QUANTITY": build_quantity_candidate(
                qty_val=25, raw_unit="g", raw_span="12 × 25 g",
                is_multipack=True, pack_count=12, unit_net_quantity=25,
                declared_expression="12 × 25 g", derived_total_quantity=300,
                source="OCR_IMAGE_1",
            )
        }
        panel2 = {
            "DECLARED_NET_QUANTITY": build_quantity_candidate(
                qty_val=25, raw_unit="g", raw_span="12 × 25 g",
                is_multipack=True, pack_count=12, unit_net_quantity=25,
                declared_expression="12 × 25 g", derived_total_quantity=300,
                source="OCR_IMAGE_2",
            )
        }

        merged = merge_extracted_fields([panel1, panel2])
        qty = merged.get("DECLARED_NET_QUANTITY", {})

        assert qty.get("status") != "CONFLICTING_EVIDENCE"
        assert qty.get("has_conflict") is not True
        assert qty.get("candidate_classification") == "CONFIRMED_SAME"


# ===========================================================================
# G. Invalid / Incomplete Expressions
# ===========================================================================
class TestInvalidExpressions:

    @pytest.mark.parametrize("invalid_expr", [
        "12 x",
        "x 25 g",
        "Net Wt:",
        "12 ×",
        "× 25 g",
        "12 x 0 g",
        "0 × 25 g",
        "-5 × 25 g",
        "12 × -25 g",
        "12 x randomword",
    ])
    def test_invalid_expressions_rejected(self, invalid_expr):
        """Incomplete or invalid strings must not fabricate false quantities."""
        parsed = parse_quantity_expression(invalid_expr)
        # Must either be None or have invalid flags, never a valid multipack
        if parsed is not None:
            assert parsed.get("is_multipack") is False or parsed.get("pack_count", 0) <= 0 or parsed.get("unit_net_quantity", 0) <= 0


# ===========================================================================
# H. Single Package Regression Continuity
# ===========================================================================
class TestSinglePackageRegression:

    def test_normal_single_package_continues_to_work(self):
        """Standard 'Net Wt: 200 g' continues extracting and validating exactly as before."""
        text = "Net Wt: 200 g"
        field = _extract_net_quantity_field(text)
        assert field is not None
        assert field["value"] == "200 g"
        assert field["quantity_value"] == "200"
        assert field["quantity_unit"] == "g"
        assert field["is_multipack"] is False

        # Rule evaluation
        rule = {"parameter": "DECLARED_NET_QUANTITY", "required": True}
        res = validate_declared_net_quantity(field, rule, {"DECLARED_NET_QUANTITY": field})
        assert res.status == "PASS"
        assert res.binary == 1
        assert res.unit == "g"
        assert res.value == 200


# ===========================================================================
# I. Legal Metrology Rule PC-ALL-002 Binary Validation
# ===========================================================================
class TestRuleEngineIntegration:

    def test_valid_multipack_passes_rule_with_binary_1(self):
        """A valid multipack candidate passes statutory rule PC-ALL-002 with binary=1."""
        cand = build_quantity_candidate(
            qty_val=25, raw_unit="g", raw_span="Net Wt: 12 × 25 g",
            is_multipack=True, pack_count=12, unit_net_quantity=25,
            declared_expression="12 × 25 g", derived_total_quantity=300,
        )
        rule = {"parameter": "DECLARED_NET_QUANTITY", "required": True}
        res = validate_declared_net_quantity(cand, rule, {"DECLARED_NET_QUANTITY": cand})

        assert res.status == "PASS"
        assert res.binary == 1
        assert res.is_multipack is True
        assert res.pack_count == 12
        assert res.unit_quantity == 25
        assert res.derived_total_quantity == 300
        assert res.unit == "g"

    def test_multipack_with_illegal_unit_fails_with_binary_0(self):
        """A multipack with an illegal unit fails with binary=0."""
        cand = build_quantity_candidate(
            qty_val=25, raw_unit="xyzunit", raw_span="12 × 25 xyzunit",
            is_multipack=True, pack_count=12, unit_net_quantity=25,
            declared_expression="12 × 25 xyzunit", derived_total_quantity=300,
        )
        rule = {"parameter": "DECLARED_NET_QUANTITY", "required": True}
        res = validate_declared_net_quantity(cand, rule, {"DECLARED_NET_QUANTITY": cand})

        assert res.status == "FAIL"
        assert res.binary == 0
        assert "not a recognized legal unit" in res.reason.lower()

    def test_multipack_with_missing_count_fails_with_binary_0(self):
        """A multipack missing pack count fails with binary=0."""
        cand = build_quantity_candidate(
            qty_val=25, raw_unit="g", raw_span="25 g",
            is_multipack=True, pack_count=None, unit_net_quantity=25,
        )
        rule = {"parameter": "DECLARED_NET_QUANTITY", "required": True}
        res = validate_declared_net_quantity(cand, rule, {"DECLARED_NET_QUANTITY": cand})

        assert res.status == "FAIL"
        assert res.binary == 0


# ===========================================================================
# J. Packaging Hierarchy: Outer Package vs Inner Unit
# ===========================================================================
class TestPackagingHierarchy:

    def test_outer_multipack_and_inner_unit_do_not_conflict(self):
        """Outer package 12 × 25 g and inner unit 25 g are complementary hierarchy, not a conflict."""
        cand_outer = build_quantity_candidate(
            qty_val=25, raw_unit="g", raw_span="12 × 25 g",
            is_multipack=True, pack_count=12, unit_net_quantity=25,
            declared_expression="12 × 25 g", derived_total_quantity=300,
            packaging_level="OUTER_PACKAGE",
        )
        cand_inner = build_quantity_candidate(
            qty_val=25, raw_unit="g", raw_span="25 g",
            is_multipack=False, packaging_level="INNER_UNIT",
        )

        conflict = _values_conflict("DECLARED_NET_QUANTITY", cand_outer, cand_inner)
        assert conflict is False, "Outer multipack and inner unit must be recognized as complementary hierarchy"

    def test_outer_multipack_and_contradictory_quantity_conflict(self):
        """Outer package 12 × 25 g and contradictory single unit 100 g produce genuine conflict."""
        cand_outer = build_quantity_candidate(
            qty_val=25, raw_unit="g", raw_span="12 × 25 g",
            is_multipack=True, pack_count=12, unit_net_quantity=25,
            declared_expression="12 × 25 g", derived_total_quantity=300,
        )
        cand_divergent = build_quantity_candidate(
            qty_val=100, raw_unit="g", raw_span="100 g",
            is_multipack=False,
        )

        conflict = _values_conflict("DECLARED_NET_QUANTITY", cand_outer, cand_divergent)
        assert conflict is True, "Contradictory quantity declarations across panels must produce conflict"
