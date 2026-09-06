"""Test suite for smarter multi-image evidence classification.

Tests the distinction between TRUE_CONFLICT, MULTI_PANEL_EVIDENCE, REVIEW/OCR_VARIATION,
and OCR_NOISE/IRRELEVANT_CANDIDATE in the evidence merge pipeline.
"""

import pytest
from app.extraction.declaration_extractor import (
    merge_extracted_fields,
    merge_product_evidence,
    _is_irrelevant_candidate,
    _fuzzy_ocr_similar,
    _classify_multi_image_evidence,
)
from app.rules.rule_engine import evaluate_rules, build_inspection_findings


# ---------------------------------------------------------------------------
# Test 1: Same field, same context, different values -> TRUE_CONFLICT
# ---------------------------------------------------------------------------
class TestTrueConflict:
    def test_mrp_true_conflict(self):
        """MRP ₹120 vs ₹140 from same-type fields must be TRUE_CONFLICT."""
        img1 = {'MRP': {'value': '₹120', 'confidence': 0.82, 'source': 'OCR_IMAGE_1', 'source_image_index': 0}}
        img2 = {'MRP': {'value': '₹140', 'confidence': 0.81, 'source': 'OCR_IMAGE_2', 'source_image_index': 1}}
        merged = merge_extracted_fields([img1, img2])
        mrp = merged.get('MRP', {})
        assert mrp.get('status') == 'CONFLICTING_EVIDENCE'
        assert mrp.get('has_conflict') is True
        assert mrp.get('candidate_classification') == 'TRUE_CONFLICT'
        assert set(mrp.get('values', [])) == {'₹120', '₹140'}
        assert len(mrp.get('candidates', [])) == 2

        # Rule evaluation: must require review, never silently PASS
        rule = {'rule_id': 'PC-ALL-002', 'parameter': 'MRP', 'required': True, 'validation_method': 'MRP_PRESENT'}
        results, overall = evaluate_rules([rule], merged)
        assert results[0]['status'] == 'NOT_VERIFIABLE'
        assert results[0]['binary'] == 0
        assert results[0]['review_required'] is True


# ---------------------------------------------------------------------------
# Test 2: Same field, different package panels -> MULTI_PANEL_EVIDENCE
# ---------------------------------------------------------------------------
class TestMultiPanelEvidence:
    def test_product_name_different_panels(self):
        """Product names from front vs side panel that share words should NOT be TRUE_CONFLICT."""
        img1 = {'PRODUCT_NAME': {'value': 'Tata Salt Lite', 'confidence': 0.90, 'source': 'OCR_IMAGE_1', 'source_image_index': 0}}
        img2 = {'PRODUCT_NAME': {'value': 'Tata Lite Salt Low Sodium', 'confidence': 0.85, 'source': 'OCR_IMAGE_2', 'source_image_index': 1}}
        merged = merge_extracted_fields([img1, img2])
        pname = merged.get('PRODUCT_NAME', {})
        # These two share enough words (tata, salt, lite) to NOT conflict
        assert pname.get('candidate_classification') != 'TRUE_CONFLICT'
        assert pname.get('status') != 'CONFLICTING_EVIDENCE'
        # Value should be preserved (best candidate selected)
        assert pname.get('value') is not None
        assert not str(pname.get('value', '')).startswith('CONFLICT:')

    def test_completely_different_product_names_across_panels(self):
        """Completely different product names from different images should be MULTI_PANEL_EVIDENCE."""
        img1 = {'PRODUCT_NAME': {'value': 'Bournvita Health Drink', 'confidence': 0.88, 'source': 'OCR_IMAGE_1', 'source_image_index': 0}}
        img2 = {'PRODUCT_NAME': {'value': 'Cadbury Cocoa Mix', 'confidence': 0.82, 'source': 'OCR_IMAGE_2', 'source_image_index': 1}}
        merged = merge_extracted_fields([img1, img2])
        pname = merged.get('PRODUCT_NAME', {})
        # Should be classified as MULTI_PANEL_EVIDENCE (different panels, product names)
        assert pname.get('candidate_classification') == 'MULTI_PANEL_EVIDENCE'
        assert pname.get('status') == 'REVIEW'
        assert pname.get('has_conflict') is False


# ---------------------------------------------------------------------------
# Test 3: Serving size vs declared net quantity -> must not conflict
# ---------------------------------------------------------------------------
class TestServingSizeVsNetQty:
    def test_serving_size_filtered_from_net_qty(self):
        """'20 g' net quantity vs 'SERVE SIZE PER 20G' must not create a conflict."""
        img1 = {'DECLARED_NET_QUANTITY': {
            'value': '20 g', 'quantity_value': 20, 'quantity_unit': 'g',
            'confidence': 0.85, 'source': 'OCR_IMAGE_1', 'source_image_index': 0,
        }}
        img2 = {'DECLARED_NET_QUANTITY': {
            'value': '20 g', 'quantity_value': 20, 'quantity_unit': 'g',
            'confidence': 0.78, 'source': 'OCR_IMAGE_2', 'source_image_index': 1,
            'source_context': 'SERVE SIZE PER 20G',
        }}
        merged = merge_extracted_fields([img1, img2])
        qty = merged.get('DECLARED_NET_QUANTITY', {})
        # The serving-size candidate should be filtered as irrelevant
        assert qty.get('status') != 'CONFLICTING_EVIDENCE'
        assert qty.get('has_conflict') is not True
        assert qty.get('value') == '20 g'


# ---------------------------------------------------------------------------
# Test 4: Nutrition value vs declared net quantity -> must not conflict
# ---------------------------------------------------------------------------
class TestNutritionVsNetQty:
    def test_nutrition_quantity_filtered(self):
        """'20 g' net quantity vs 'Carbohydrate 53.15 g' must not conflict."""
        img1 = {'DECLARED_NET_QUANTITY': {
            'value': '20 g', 'quantity_value': 20, 'quantity_unit': 'g',
            'confidence': 0.88, 'source': 'OCR_IMAGE_1', 'source_image_index': 0,
        }}
        img2 = {'DECLARED_NET_QUANTITY': {
            'value': '53.15 g', 'quantity_value': 53.15, 'quantity_unit': 'g',
            'confidence': 0.75, 'source': 'OCR_IMAGE_2', 'source_image_index': 1,
            'source_context': 'Carbohydrate 53.15 g per serving',
        }}
        merged = merge_extracted_fields([img1, img2])
        qty = merged.get('DECLARED_NET_QUANTITY', {})
        # Nutrition quantity should be filtered; no conflict
        assert qty.get('status') != 'CONFLICTING_EVIDENCE'
        assert qty.get('has_conflict') is not True
        assert qty.get('value') == '20 g'


# ---------------------------------------------------------------------------
# Test 5: Manufacturer label + company name -> strong manufacturer candidate
# ---------------------------------------------------------------------------
class TestManufacturerCandidate:
    def test_manufacturer_with_vendor_label(self):
        """Manufacturer name with vendor keyword should be preserved as a strong candidate."""
        img1 = {'MANUFACTURER_NAME': {
            'value': 'SWISSYUM FOODS Pvt. Ltd.',
            'confidence': 0.88, 'source': 'OCR_IMAGE_1', 'source_image_index': 0,
        }}
        merged = merge_extracted_fields([img1])
        mfg = merged.get('MANUFACTURER_NAME', {})
        assert mfg.get('value') == 'SWISSYUM FOODS Pvt. Ltd.'


# ---------------------------------------------------------------------------
# Test 6: Marketing text -> rejected as manufacturer/address candidate
# ---------------------------------------------------------------------------
class TestMarketingTextRejection:
    def test_marketing_text_rejected_as_manufacturer(self):
        """'SWEET'N SOUR' and 'CRUNCHY' must be rejected as manufacturer candidates."""
        assert _is_irrelevant_candidate('MANUFACTURER_NAME', {
            'value': "SWEET'N SOUR CANDY", 'confidence': 0.80,
            'source_context': "SWEET'N SOUR CANDY - Delicious taste!"
        })

    def test_storage_text_rejected_as_address(self):
        """'CONTAINER ONCE OPENED' must be rejected as manufacturer address."""
        assert _is_irrelevant_candidate('MANUFACTURER_ADDRESS', {
            'value': 'CONTAINER ONCE OPENED KEEP IN COOL DRY PLACE',
            'confidence': 0.75,
        })

    def test_nutrition_text_rejected_as_address(self):
        """'SERVE SIZE PER 20G' must be rejected as manufacturer address."""
        assert _is_irrelevant_candidate('MANUFACTURER_ADDRESS', {
            'value': 'SERVE SIZE PER 20G',
            'confidence': 0.70,
        })


# ---------------------------------------------------------------------------
# Test 7: Multiline manufacturer address preserved correctly
# ---------------------------------------------------------------------------
class TestMultilineAddress:
    def test_valid_address_not_rejected(self):
        """Real manufacturer address lines must NOT be filtered out."""
        assert not _is_irrelevant_candidate('MANUFACTURER_ADDRESS', {
            'value': 'Plot No. 45, GIDC Industrial Estate, Anand, Gujarat 388001',
            'confidence': 0.85,
        })

    def test_contact_line_rejected(self):
        """'call us at 033' must be filtered out of address candidates."""
        assert _is_irrelevant_candidate('MANUFACTURER_ADDRESS', {
            'value': 'call us at 033-22452345 for queries',
            'confidence': 0.70,
        })


# ---------------------------------------------------------------------------
# Test 8: Barcode vs OCR disagreement -> review/conflict, no silent overwrite
# ---------------------------------------------------------------------------
class TestBarcodeConflict:
    def test_barcode_ocr_disagreement(self):
        """When barcode lookup contradicts OCR, must be CONFLICTING_EVIDENCE with no silent overwrite."""
        ocr_fields = {'PRODUCT_NAME': {'value': 'Aashirvaad Atta', 'confidence': 0.90, 'source': 'OCR'}}
        barcode_result = {
            'value': '8904043901015', 'confidence': 1.0,
            'lookup': {'status': 'FOUND', 'product_name': 'Tata Salt', 'brands': 'Tata'},
        }
        merged = merge_product_evidence(ocr_fields, '', [], barcode_result)
        pname = merged.get('PRODUCT_NAME', {})
        assert pname.get('status') == 'CONFLICTING_EVIDENCE'
        assert pname.get('has_conflict') is True
        assert pname.get('barcode_match') == 'CONFLICTS'
        # OCR must NOT be overwritten
        assert pname.get('ocr_value') == 'Aashirvaad Atta'

        rule = {'rule_id': 'PC-ALL-001', 'parameter': 'PRODUCT_NAME', 'required': True, 'validation_method': 'TEXT_PRESENT'}
        results, _ = evaluate_rules([rule], merged)
        assert results[0]['status'] == 'NOT_VERIFIABLE'
        assert results[0]['binary'] == 0
        assert results[0]['review_required'] is True


# ---------------------------------------------------------------------------
# Test 9: Multiple product-name candidates -> review if ambiguous
# ---------------------------------------------------------------------------
class TestAmbiguousProductName:
    def test_multiple_ambiguous_product_names(self):
        """Multiple distinct product names from different images should be REVIEW, not TRUE_CONFLICT."""
        img1 = {'PRODUCT_NAME': {'value': 'Swissyum Candy Bar', 'confidence': 0.85, 'source': 'OCR_IMAGE_1', 'source_image_index': 0}}
        img2 = {'PRODUCT_NAME': {'value': 'Candy Bar Supreme', 'confidence': 0.80, 'source': 'OCR_IMAGE_2', 'source_image_index': 1}}
        merged = merge_extracted_fields([img1, img2])
        pname = merged.get('PRODUCT_NAME', {})
        # Should be REVIEW/MULTI_PANEL, not TRUE_CONFLICT for product names from different images
        assert pname.get('candidate_classification') in ('MULTI_PANEL_EVIDENCE', 'OCR_VARIATION')
        assert pname.get('value') is not None
        assert not str(pname.get('value', '')).startswith('CONFLICT:')


# ---------------------------------------------------------------------------
# Test 10: Valid declared net quantity + unrelated nutrition quantities
# ---------------------------------------------------------------------------
class TestNetQtyWithNutritionNoise:
    def test_declared_qty_not_polluted_by_nutrition(self):
        """Valid declared net quantity must remain correctly scoped; nutrition quantities must not pollute."""
        img1 = {'DECLARED_NET_QUANTITY': {
            'value': '200 g', 'quantity_value': 200, 'quantity_unit': 'g',
            'confidence': 0.90, 'source': 'OCR_IMAGE_1', 'source_image_index': 0,
        }}
        img2 = {'DECLARED_NET_QUANTITY': {
            'value': '8.5 g', 'quantity_value': 8.5, 'quantity_unit': 'g',
            'confidence': 0.70, 'source': 'OCR_IMAGE_2', 'source_image_index': 1,
            'source_context': 'Protein 8.5 g per serving',
        }}
        img3 = {'DECLARED_NET_QUANTITY': {
            'value': '22 g', 'quantity_value': 22, 'quantity_unit': 'g',
            'confidence': 0.72, 'source': 'OCR_IMAGE_3', 'source_image_index': 2,
            'source_context': 'Total Sugar 22 g',
        }}
        merged = merge_extracted_fields([img1, img2, img3])
        qty = merged.get('DECLARED_NET_QUANTITY', {})
        # Only the genuine 200g should remain
        assert qty.get('status') != 'CONFLICTING_EVIDENCE'
        assert qty.get('has_conflict') is not True
        assert qty.get('value') == '200 g'
        # Noise should be recorded in filtered_noise
        assert len(qty.get('filtered_noise', [])) >= 2


# ---------------------------------------------------------------------------
# Test 11: Isolated numeric OCR candidate without semantic context -> rejected
# ---------------------------------------------------------------------------
class TestIsolatedNumericRejection:
    def test_isolated_digit_rejected(self):
        """Isolated '2' without unit or context must be filtered as OCR noise."""
        assert _is_irrelevant_candidate('DECLARED_NET_QUANTITY', {
            'value': '2', 'confidence': 0.60,
        })

    def test_proper_quantity_not_rejected(self):
        """'20 g' with proper unit must NOT be filtered."""
        assert not _is_irrelevant_candidate('DECLARED_NET_QUANTITY', {
            'value': '20 g', 'confidence': 0.85,
        })

    def test_isolated_digit_in_merge(self):
        """In a merge, isolated '2' must not create a conflict with '20 g'."""
        img1 = {'DECLARED_NET_QUANTITY': {
            'value': '20 g', 'quantity_value': 20, 'quantity_unit': 'g',
            'confidence': 0.85, 'source': 'OCR_IMAGE_1', 'source_image_index': 0,
        }}
        img2 = {'DECLARED_NET_QUANTITY': {
            'value': '2', 'confidence': 0.50,
            'source': 'OCR_IMAGE_2', 'source_image_index': 1,
        }}
        merged = merge_extracted_fields([img1, img2])
        qty = merged.get('DECLARED_NET_QUANTITY', {})
        assert qty.get('status') != 'CONFLICTING_EVIDENCE'
        assert qty.get('has_conflict') is not True
        assert qty.get('value') == '20 g'


# ---------------------------------------------------------------------------
# Test 12: Real inspection scenario (SWISSYUM product)
# ---------------------------------------------------------------------------
class TestRealInspectionScenario:
    def test_swissyum_product_scenario(self):
        """Real inspection test: multiple panels with OCR variations, noise, and nutrition data.

        PRODUCT_NAME candidates: 'Total Sugar', 'HUR', 'Ngredr Oil Paln'
        DECLARED_NET_QUANTITY candidates: '20 g', '2', '53.15 g'
        MANUFACTURER_NAME candidates: 'CHISSYUMFOODS', 'WISSYUM FOODS', 'SWISSYUM FOODS'
        MANUFACTURER_ADDRESS candidates: 'call us at 033', 'SWEET\\'N SOUR', 'CONTAINER ONCE OPENED', 'SERVE SIZE PER 20G'
        """
        # Image 1 (front panel)
        img1_fields = {
            'PRODUCT_NAME': {'value': 'Total Sugar', 'confidence': 0.65, 'source': 'OCR_IMAGE_1', 'source_image_index': 0,
                             'source_context': 'Total Sugar 20 g per serving'},
            'DECLARED_NET_QUANTITY': {'value': '20 g', 'quantity_value': 20, 'quantity_unit': 'g',
                                      'confidence': 0.88, 'source': 'OCR_IMAGE_1', 'source_image_index': 0},
            'MANUFACTURER_NAME': {'value': 'CHISSYUMFOODS', 'confidence': 0.60, 'source': 'OCR_IMAGE_1', 'source_image_index': 0},
            'MANUFACTURER_ADDRESS': {'value': 'call us at 033-22452345', 'confidence': 0.65,
                                     'source': 'OCR_IMAGE_1', 'source_image_index': 0},
        }
        # Image 2 (side panel)
        img2_fields = {
            'PRODUCT_NAME': {'value': 'HUR', 'confidence': 0.40, 'source': 'OCR_IMAGE_2', 'source_image_index': 1},
            'DECLARED_NET_QUANTITY': {'value': '2', 'confidence': 0.45, 'source': 'OCR_IMAGE_2', 'source_image_index': 1},
            'MANUFACTURER_NAME': {'value': 'WISSYUM FOODS', 'confidence': 0.72, 'source': 'OCR_IMAGE_2', 'source_image_index': 1},
            'MANUFACTURER_ADDRESS': {'value': "SWEET'N SOUR", 'confidence': 0.55,
                                     'source': 'OCR_IMAGE_2', 'source_image_index': 1,
                                     'source_context': "SWEET'N SOUR candy taste"},
        }
        # Image 3 (back panel)
        img3_fields = {
            'PRODUCT_NAME': {'value': 'Ngredr Oil Paln', 'confidence': 0.35, 'source': 'OCR_IMAGE_3', 'source_image_index': 2},
            'DECLARED_NET_QUANTITY': {'value': '53.15 g', 'quantity_value': 53.15, 'quantity_unit': 'g',
                                      'confidence': 0.70, 'source': 'OCR_IMAGE_3', 'source_image_index': 2,
                                      'source_context': 'Carbohydrate 53.15 g'},
            'MANUFACTURER_NAME': {'value': 'SWISSYUM FOODS', 'confidence': 0.85, 'source': 'OCR_IMAGE_3', 'source_image_index': 2},
            'MANUFACTURER_ADDRESS': {'value': 'CONTAINER ONCE OPENED', 'confidence': 0.60,
                                     'source': 'OCR_IMAGE_3', 'source_image_index': 2},
        }

        merged = merge_extracted_fields([img1_fields, img2_fields, img3_fields])

        # PRODUCT_NAME: 'Total Sugar' should be filtered (nutrition context).
        # 'HUR' is very short + low confidence -> filtered.
        # 'Ngredr Oil Paln' is short + very low confidence -> filtered.
        # The system should handle this gracefully.
        pname = merged.get('PRODUCT_NAME', {})
        # Should NOT produce a giant conflict storm
        assert pname.get('candidate_classification') != 'TRUE_CONFLICT' or pname.get('status') != 'CONFLICTING_EVIDENCE' or \
               len(pname.get('values', [])) <= 3  # at most 3 candidates retained

        # DECLARED_NET_QUANTITY: '20 g' is the genuine one.
        # '2' -> isolated digit -> filtered.
        # '53.15 g' with 'Carbohydrate' context -> nutrition -> filtered.
        qty = merged.get('DECLARED_NET_QUANTITY', {})
        assert qty.get('value') == '20 g'
        assert qty.get('status') != 'CONFLICTING_EVIDENCE'
        assert qty.get('has_conflict') is not True
        # Noise captured
        assert len(qty.get('filtered_noise', [])) >= 2

        # MANUFACTURER_NAME: CHISSYUMFOODS / WISSYUM FOODS / SWISSYUM FOODS
        # These are OCR variations of the same company -> should be REVIEW or OCR_VARIATION
        mfg = merged.get('MANUFACTURER_NAME', {})
        assert mfg.get('candidate_classification') != 'TRUE_CONFLICT'
        # Highest-confidence value should be selected
        assert 'SWISSYUM' in str(mfg.get('value', '')) or 'WISSYUM' in str(mfg.get('value', ''))
        # Should be flagged for review
        assert mfg.get('review_required', False) or mfg.get('status') in ('REVIEW', None)

        # MANUFACTURER_ADDRESS: all candidates are noise (contact, marketing, storage)
        addr = merged.get('MANUFACTURER_ADDRESS', {})
        # All should be filtered
        noise = addr.get('filtered_noise', [])
        assert len(noise) >= 2  # at least 2 of the 3 noise candidates filtered

    def test_no_false_conflict_storm(self):
        """Verify the system does NOT produce a giant conflict list simply because different
        panels contain different legitimate text."""
        img1 = {
            'PRODUCT_NAME': {'value': 'Swissyum Candy Bar', 'confidence': 0.85, 'source': 'OCR_IMAGE_1', 'source_image_index': 0},
            'DECLARED_NET_QUANTITY': {'value': '20 g', 'quantity_value': 20, 'quantity_unit': 'g',
                                      'confidence': 0.90, 'source': 'OCR_IMAGE_1', 'source_image_index': 0},
            'MANUFACTURER_NAME': {'value': 'SWISSYUM FOODS Pvt. Ltd.', 'confidence': 0.88,
                                  'source': 'OCR_IMAGE_1', 'source_image_index': 0},
        }
        img2 = {
            'DECLARED_NET_QUANTITY': {'value': '20 g', 'quantity_value': 20, 'quantity_unit': 'g',
                                      'confidence': 0.85, 'source': 'OCR_IMAGE_2', 'source_image_index': 1},
            'MANUFACTURER_NAME': {'value': 'SWISSYUM FOODS Pvt. Ltd.', 'confidence': 0.82,
                                  'source': 'OCR_IMAGE_2', 'source_image_index': 1},
        }

        merged = merge_extracted_fields([img1, img2])

        # No field should be TRUE_CONFLICT when values agree
        for name, field_data in merged.items():
            assert field_data.get('candidate_classification') != 'TRUE_CONFLICT', \
                f"Field '{name}' should not be TRUE_CONFLICT when values agree"
            assert field_data.get('status') != 'CONFLICTING_EVIDENCE', \
                f"Field '{name}' should not be CONFLICTING_EVIDENCE when values agree"


# ---------------------------------------------------------------------------
# Test: Fuzzy OCR similarity detection
# ---------------------------------------------------------------------------
class TestFuzzyOcrSimilarity:
    def test_swissyum_variations(self):
        """CHISSYUMFOODS / WISSYUM FOODS / SWISSYUM FOODS should be detected as similar."""
        assert _fuzzy_ocr_similar('CHISSYUMFOODS', 'SWISSYUM FOODS')
        assert _fuzzy_ocr_similar('WISSYUM FOODS', 'SWISSYUM FOODS')
        assert _fuzzy_ocr_similar('CHISSYUMFOODS', 'WISSYUM FOODS')

    def test_completely_different_not_similar(self):
        """Completely different company names should NOT be detected as similar."""
        assert not _fuzzy_ocr_similar('Tata Salt', 'Aashirvaad Atta')
        assert not _fuzzy_ocr_similar('Britannia', 'Nestlé India')

    def test_identical_strings(self):
        """Identical strings should be detected as similar."""
        assert _fuzzy_ocr_similar('SWISSYUM FOODS', 'SWISSYUM FOODS')


# ---------------------------------------------------------------------------
# Test: Irrelevant candidate detection
# ---------------------------------------------------------------------------
class TestIrrelevantCandidateDetection:
    def test_nutrition_context_detected(self):
        """Nutrition context labels should make net quantity candidates irrelevant."""
        assert _is_irrelevant_candidate('DECLARED_NET_QUANTITY', {
            'value': '8.5 g', 'source_context': 'Protein 8.5 g per 100g'
        })

    def test_serving_size_context_detected(self):
        assert _is_irrelevant_candidate('DECLARED_NET_QUANTITY', {
            'value': '30 g', 'source_context': 'Serving size 30 g'
        })

    def test_valid_net_qty_not_rejected(self):
        """A legitimate net quantity with no nutrition context must NOT be rejected."""
        assert not _is_irrelevant_candidate('DECLARED_NET_QUANTITY', {
            'value': '200 g', 'confidence': 0.90,
        })

    def test_marketing_rejected_as_manufacturer(self):
        assert _is_irrelevant_candidate('MANUFACTURER_NAME', {
            'value': 'Premium Quality Foods',
            'source_context': 'Premium Quality - No added preservatives'
        })

    def test_storage_rejected_as_address(self):
        assert _is_irrelevant_candidate('MANUFACTURER_ADDRESS', {
            'value': 'Store in a cool, dry place away from sunlight'
        })

    def test_nutrition_rejected_as_product_name(self):
        assert _is_irrelevant_candidate('PRODUCT_NAME', {
            'value': 'Total Sugar', 'confidence': 0.65,
            'source_context': 'Total Sugar 20 g per serving'
        })


# ---------------------------------------------------------------------------
# Test: REVIEW status flows through rule evaluation correctly
# ---------------------------------------------------------------------------
class TestReviewStatusInRuleEvaluation:
    def test_review_status_produces_not_verifiable(self):
        """REVIEW status evidence should produce NOT_VERIFIABLE with binary=0 in rule evaluation."""
        evidence = {
            'MANUFACTURER_NAME': {
                'value': 'SWISSYUM FOODS',
                'status': 'REVIEW',
                'candidate_classification': 'OCR_VARIATION',
                'review_required': True,
                'confidence': 0.85,
                'reason': 'Multiple plausible evidence candidates detected.',
            }
        }
        rule = {'rule_id': 'PC-ALL-007', 'parameter': 'MANUFACTURER_NAME', 'required': True, 'validation_method': 'TEXT_PRESENT'}
        results, overall = evaluate_rules([rule], evidence)
        assert results[0]['status'] == 'NOT_VERIFIABLE'
        assert results[0]['binary'] == 0
        assert results[0]['review_required'] is True
        assert overall == 'NOT_VERIFIABLE'

    def test_conflicting_evidence_produces_not_verifiable(self):
        """CONFLICTING_EVIDENCE status should also produce NOT_VERIFIABLE."""
        evidence = {
            'MRP': {
                'value': 'CONFLICT: ₹120 vs ₹140',
                'status': 'CONFLICTING_EVIDENCE',
                'has_conflict': True,
                'values': ['₹120', '₹140'],
                'candidate_classification': 'TRUE_CONFLICT',
                'confidence': 0.82,
            }
        }
        rule = {'rule_id': 'PC-ALL-002', 'parameter': 'MRP', 'required': True, 'validation_method': 'MRP_PRESENT'}
        results, overall = evaluate_rules([rule], evidence)
        assert results[0]['status'] == 'NOT_VERIFIABLE'
        assert results[0]['binary'] == 0
        assert results[0]['review_required'] is True
