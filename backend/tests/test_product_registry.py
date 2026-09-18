"""Tests for Part A — Reference Product Registry & 5-tier Product Familiarity Matcher.

Verifies:
1. Exact barcode / GTIN match (Tier 1)
2. Barcode + Brand / Generic Name match (Tier 2)
3. Brand + Generic Name + Quantity match (Tier 3)
4. Product-name similarity + supporting fields (Tier 4)
5. No reliable match (Tier 5)
6. Conflicting OCR candidates ranking improvement
7. CRITICAL: Reference match DOES NOT affect statutory PASS/FAIL compliance decisions.
"""

import pytest
from app.registry.product_registry import (
    ProductRegistry,
    ReferenceProduct,
    get_product_registry,
)
from app.registry.matcher import (
    match_product,
    improve_candidate_ranking,
    RegistryMatchResult,
)
from app.rules.rule_engine import evaluate_rules


@pytest.fixture
def sample_registry():
    """Build isolated registry with known packaged products."""
    reg = ProductRegistry(data_file="__nonexistent_path__")
    reg.register(
        ReferenceProduct(
            gtin="8901030383701",
            product_name="Tata Salt Vacuum Evaporated Iodised Salt",
            brand="Tata Salt",
            generic_name="Iodised Salt",
            category="FOOD",
            product_type="SALT",
            declared_net_quantity="1 kg",
            net_quantity_value=1.0,
            net_quantity_unit="kg",
            standard_mrp="28.00",
            manufacturer_name="Tata Consumer Products Limited",
            source="NATIONAL_PRODUCT_REGISTRY",
        )
    )
    reg.register(
        ReferenceProduct(
            gtin="8901262010057",
            product_name="Amul Pasteurised Butter",
            brand="Amul",
            generic_name="Pasteurised Butter",
            category="FOOD",
            product_type="DAIRY",
            declared_net_quantity="500 g",
            net_quantity_value=500.0,
            net_quantity_unit="g",
            standard_mrp="275.00",
            manufacturer_name="Gujarat Cooperative Milk Marketing Federation Ltd.",
            source="NATIONAL_PRODUCT_REGISTRY",
        )
    )
    return reg


class TestProductRegistryMatching:
    """Verify 5-tier matching priority."""

    def test_tier1_exact_barcode_match(self, sample_registry):
        """Tier 1: Exact barcode matches, but brand/generic name absent on label."""
        result = match_product(
            barcode="8901030383701",
            brand=None,
            generic_name=None,
            product_name=None,
            registry=sample_registry,
        )
        assert result.matched is True
        assert result.tier == 1
        assert result.tier_name == "EXACT_BARCODE"
        assert result.matched_by == "Exact Barcode / GTIN"
        assert result.confidence >= 0.90
        assert result.suggestion_label == "Known product match"
        assert result.reference_product["brand"] == "Tata Salt"

    def test_tier2_barcode_plus_brand_and_generic(self, sample_registry):
        """Tier 2: Barcode + Brand + Generic Name all match."""
        result = match_product(
            barcode="8901030383701",
            brand="Tata Salt",
            generic_name="Iodised Salt",
            product_name="Tata Salt Iodised",
            registry=sample_registry,
        )
        assert result.matched is True
        assert result.tier == 2
        assert result.tier_name == "BARCODE_BRAND_GENERIC_NAME"
        assert result.matched_by == "Barcode + Brand + Generic Name"
        assert result.confidence_percent == 94
        assert result.suggestion_label == "Known product match"
        assert result.reference_product["gtin"] == "8901030383701"

    def test_tier3_brand_generic_quantity_without_barcode(self, sample_registry):
        """Tier 3: No barcode, but brand + generic name + quantity match known product."""
        result = match_product(
            barcode=None,
            brand="Amul",
            generic_name="Pasteurised Butter",
            quantity="500 g",
            registry=sample_registry,
        )
        assert result.matched is True
        assert result.tier == 3
        assert result.tier_name == "BRAND_GENERIC_QUANTITY"
        assert result.matched_by == "Brand + Generic Name + Quantity"
        assert result.confidence >= 0.85
        assert result.reference_product["product_name"] == "Amul Pasteurised Butter"

    def test_tier4_product_name_similarity(self, sample_registry):
        """Tier 4: Product name text similarity with supporting category and brand."""
        result = match_product(
            barcode=None,
            product_name="Tata Salt Vacuum Evaporated Salt",
            brand="Tata",
            category="FOOD",
            registry=sample_registry,
        )
        assert result.matched is True
        assert result.tier == 4
        assert result.tier_name == "PRODUCT_NAME_SIMILARITY"
        assert "Product Name Similarity" in result.matched_by
        assert result.confidence >= 0.70

    def test_tier5_no_reliable_match(self, sample_registry):
        """Tier 5: Completely unknown product or barcode."""
        result = match_product(
            barcode="9999999999999",
            brand="UnknownBrandXYZ",
            product_name="Random Unregistered Gadget",
            registry=sample_registry,
        )
        assert result.matched is False
        assert result.tier == 5
        assert result.tier_name == "NO_MATCH"
        assert result.confidence == 0.0
        assert result.matched_by == "No reliable match"
        assert result.reference_product is None


class TestCandidateRankingEnhancement:
    """Verify supporting evidence candidate ranking without data corruption."""

    def test_improve_candidate_ranking_elevates_matching_candidate(self, sample_registry):
        """Conflicting OCR tokens: matching candidate is ranked first without altering text."""
        ref_prod = sample_registry.get_by_gtin("8901030383701").to_dict()
        competing_candidates = [
            {"value": "Tata Tea Gold 250g", "confidence": 0.80, "source": "OCR_PANEL_1"},
            {"value": "Tata Salt Vacuum Evaporated Iodised Salt", "confidence": 0.78, "source": "OCR_PANEL_2"},
            {"value": "Tata Sampann Dal", "confidence": 0.65, "source": "OCR_PANEL_3"},
        ]

        ranked = improve_candidate_ranking("PRODUCT_NAME", competing_candidates, ref_prod)
        assert len(ranked) == 3
        # Matching candidate is elevated to index 0
        assert ranked[0]["value"] == "Tata Salt Vacuum Evaporated Iodised Salt"
        assert ranked[0]["is_reference_match"] is True
        # Original candidates are preserved
        assert any(c["value"] == "Tata Tea Gold 250g" for c in ranked)


class TestStatutoryPassFailIndependence:
    """CRITICAL: Reference match MUST NOT automatically produce PASS or alter compliance."""

    def test_reference_match_does_not_pass_missing_mandatory_declaration(self, sample_registry):
        """Even with 94% reference match, if package label lacks required MRP, rule FAILS."""
        # Simulated extracted fields from package image where MRP is completely missing
        extracted_fields = {
            "PRODUCT_NAME": {"value": "Tata Salt Vacuum Evaporated Iodised Salt", "confidence": 0.90},
            "BRAND": {"value": "Tata Salt", "confidence": 0.90},
            "GENERIC_NAME": {"value": "Iodised Salt", "confidence": 0.90},
            "DECLARED_NET_QUANTITY": {"value": "1 kg", "quantity_value": 1.0, "quantity_unit": "kg", "confidence": 0.90},
            # Note: MRP is missing!
        }

        # Check registry match produces known product match
        match = match_product(
            barcode="8901030383701",
            brand="Tata Salt",
            generic_name="Iodised Salt",
            registry=sample_registry,
        )
        assert match.matched is True
        assert match.confidence_percent == 94

        # Applicable rule: MRP must be declared
        applicable_rules = [
            {
                "rule_id": "PC-ALL-002",
                "parameter": "MRP",
                "validation_method": "PRESENCE_CHECK",
                "required": True,
                "severity": "MANDATORY",
            }
        ]

        # Evaluate rules deterministically
        results, overall = evaluate_rules(applicable_rules, extracted_fields)
        mrp_result = next(r for r in results if r["rule_id"] == "PC-ALL-002")

        # The rule MUST FAIL or be NOT_VERIFIABLE because MRP was not on the package
        assert mrp_result["status"] in ("FAIL", "NOT_VERIFIABLE")
        assert overall != "COMPLIANT"
        # Proof: The reference match did NOT automatically pass or declare legal compliance!
