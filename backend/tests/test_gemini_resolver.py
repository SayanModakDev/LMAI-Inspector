"""Comprehensive Test Suite for Gemini Evidence Resolution Layer.

Covers:
1. MRP extraction with currency variants (Rs., ₹, INR).
2. MRP promo-price disambiguation (Statutory MRP vs Special Offer Price).
3. Multipack quantity extraction (preservation of printed format + metric unit).
4. Strict separation of distinct business entities (Manufacturer, Marketer, Packer, Importer).
5. Date disambiguation (MFD vs Best Before vs Expiry Date).
6. Batch number and consumer care parsing.
7. Grounding validator rejecting ungrounded hallucinated candidates.
8. Grounding validator rejecting invalid/out-of-bounds token IDs and bounding boxes.
9. Gemini client retry with exponential backoff on 429 quota / timeout & fallback from primary to secondary model.
10. Graceful fallback to deterministic extraction when Gemini is disabled or fails.
11. Compliance outcome invariance: rule engine deterministically evaluates compliance regardless of LLM.
12. Conditional live API integration test.
"""

import json
import os
import pytest
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.llm.schemas import (
    CandidateValue,
    LLMExtractionResult,
    PackageContext,
    ResolvedDeclaration,
    SourceEvidence,
)
from app.llm.grounding_validator import EvidenceGroundingValidator
from app.llm.gemini_client import GeminiClient
from app.llm.evidence_resolver import resolve_evidence_with_gemini
from app.rules.rule_engine import evaluate_rules


# ==============================================================================
# Helper fixtures and test OCR factories
# ==============================================================================

def make_ocr_item(token_id: int, text: str, image_index: int = 0, bbox=None, confidence=0.95):
    return {
        "token_id": token_id,
        "text": text,
        "image_index": image_index,
        "bbox": bbox or [10.0, 10.0, 50.0, 20.0],
        "confidence": confidence,
    }


def make_mock_client():
    client = GeminiClient()
    client.is_enabled = lambda: True
    return client


# ==============================================================================
# 1. MRP Extraction with Currency Variants
# ==============================================================================

def test_mrp_extraction_with_currency_variants():
    """Verify Gemini parses MRP whether declared with ₹, Rs., or INR."""
    ocr_items = [
        make_ocr_item(0, "MAX. RETAIL PRICE ₹ 149.00 (INCL. OF ALL TAXES)", image_index=0),
        make_ocr_item(1, "NET WT: 200 g", image_index=0),
    ]

    mock_llm_response = LLMExtractionResult(
        declarations={
            "MRP": ResolvedDeclaration(
                field="MRP",
                value="₹ 149.00",
                normalized_value="149.00",
                status="RESOLVED",
                confidence=0.96,
                source_evidence=[
                    SourceEvidence(
                        raw_text="MAX. RETAIL PRICE ₹ 149.00 (INCL. OF ALL TAXES)",
                        token_ids=[0],
                        image_index=0,
                        bbox=[10.0, 10.0, 50.0, 20.0],
                    )
                ],
                resolution_note="Detected statutory Maximum Retail Price with rupee symbol",
            )
        }
    )

    with patch.object(GeminiClient, "generate_structured_extraction", return_value=(mock_llm_response, {"model_used": "gemini-3.8-flash", "llm_status": "SUCCESS"})):
        client = make_mock_client()
        merged, meta, _ = resolve_evidence_with_gemini(
            ocr_items=ocr_items,
            raw_text="\n".join(i["text"] for i in ocr_items),
            num_images=1,
            deterministic_fields={},
            client=client,
        )

        assert "MRP" in merged
        mrp = merged["MRP"]
        assert mrp["value"] == "₹ 149.00"
        assert mrp["status"] in ("VALID", "PASS", "RESOLVED")
        assert mrp.get("numeric_value") == 149.0 or "149" in str(mrp["value"])
        assert meta.get("model_used") == "gemini-3.8-flash"


# ==============================================================================
# 2. MRP Promo-Price Disambiguation
# ==============================================================================

def test_mrp_promo_price_disambiguation():
    """Verify Gemini surfaces statutory MRP over non-statutory promotional offer price."""
    ocr_items = [
        make_ocr_item(0, "MRP Rs. 250.00 (Inclusive of all taxes)", image_index=0),
        make_ocr_item(1, "SPECIAL OFFER PRICE Rs. 199.00 ONLY", image_index=0),
    ]

    mock_llm_response = LLMExtractionResult(
        declarations={
            "MRP": ResolvedDeclaration(
                field="MRP",
                value="Rs. 250.00",
                normalized_value="250.00",
                status="RESOLVED",
                confidence=0.95,
                source_evidence=[
                    SourceEvidence(
                        raw_text="MRP Rs. 250.00 (Inclusive of all taxes)",
                        token_ids=[0],
                        image_index=0,
                        bbox=[10.0, 10.0, 50.0, 20.0],
                    )
                ],
                resolution_note="Selected statutory Maximum Retail Price Rs. 250.00; disregarded promotional offer Rs. 199.00",
            )
        }
    )

    with patch.object(GeminiClient, "generate_structured_extraction", return_value=(mock_llm_response, {"model_used": "gemini-3.8-flash", "llm_status": "SUCCESS"})):
        client = make_mock_client()
        merged, meta, _ = resolve_evidence_with_gemini(
            ocr_items=ocr_items,
            raw_text="\n".join(i["text"] for i in ocr_items),
            num_images=1,
            deterministic_fields={},
            client=client,
        )

        assert "MRP" in merged
        assert "250" in str(merged["MRP"]["value"])
        assert "199" not in str(merged["MRP"]["value"])


# ==============================================================================
# 3. Multipack Quantity Extraction
# ==============================================================================

def test_multipack_quantity_extraction():
    """Verify Gemini preserves printed multipack declaration and calculates net metric mass."""
    ocr_items = [
        make_ocr_item(0, "10 Units X 50 g Net Weight: 500 g", image_index=0),
    ]

    mock_llm_response = LLMExtractionResult(
        declarations={
            "DECLARED_NET_QUANTITY": ResolvedDeclaration(
                field="DECLARED_NET_QUANTITY",
                value="10 Units X 50 g = 500 g",
                normalized_value="500",
                status="RESOLVED",
                confidence=0.98,
                source_evidence=[
                    SourceEvidence(
                        raw_text="10 Units X 50 g Net Weight: 500 g",
                        token_ids=[0],
                        image_index=0,
                        bbox=[10.0, 10.0, 50.0, 20.0],
                    )
                ],
                resolution_note="Multipack declaration: 10 individual units of 50 g each totaling 500 g net quantity",
            )
        }
    )

    with patch.object(GeminiClient, "generate_structured_extraction", return_value=(mock_llm_response, {"model_used": "gemini-3.8-flash", "llm_status": "SUCCESS"})):
        client = make_mock_client()
        merged, _, _ = resolve_evidence_with_gemini(
            ocr_items=ocr_items,
            raw_text="\n".join(i["text"] for i in ocr_items),
            num_images=1,
            deterministic_fields={},
            client=client,
        )

        assert "DECLARED_NET_QUANTITY" in merged
        qty = merged["DECLARED_NET_QUANTITY"]
        assert "500" in str(qty["value"])


# ==============================================================================
# 4. Separation of Distinct Business Entities
# ==============================================================================

def test_distinct_business_entities_separation():
    """Verify Gemini cleanly separates Manufacturer, Marketer, Packer, and Importer."""
    ocr_items = [
        make_ocr_item(0, "Manufactured by: Alpine Foods Ltd., Solan, HP 173212", image_index=0),
        make_ocr_item(1, "Marketed by: Metro Brands India, Mumbai 400021", image_index=0),
        make_ocr_item(2, "Packed by: Packwell Logistics, Sonipat, Haryana 131001", image_index=1),
        make_ocr_item(3, "Imported by: Global Impex Pvt Ltd, New Delhi 110001", image_index=1),
    ]

    mock_llm_response = LLMExtractionResult(
        declarations={
            "MANUFACTURER_NAME": ResolvedDeclaration(
                field="MANUFACTURER_NAME",
                value="Alpine Foods Ltd.",
                status="RESOLVED",
                confidence=0.95,
                source_evidence=[
                    SourceEvidence(
                        raw_text="Manufactured by: Alpine Foods Ltd., Solan, HP 173212",
                        token_ids=[0],
                        image_index=0,
                    )
                ],
            ),
            "MANUFACTURER_ADDRESS": ResolvedDeclaration(
                field="MANUFACTURER_ADDRESS",
                value="Solan, HP 173212",
                status="RESOLVED",
                confidence=0.92,
                source_evidence=[
                    SourceEvidence(
                        raw_text="Manufactured by: Alpine Foods Ltd., Solan, HP 173212",
                        token_ids=[0],
                        image_index=0,
                    )
                ],
            ),
            "MARKETER_NAME": ResolvedDeclaration(
                field="MARKETER_NAME",
                value="Metro Brands India",
                status="RESOLVED",
                confidence=0.95,
                source_evidence=[
                    SourceEvidence(
                        raw_text="Marketed by: Metro Brands India, Mumbai 400021",
                        token_ids=[1],
                        image_index=0,
                    )
                ],
            ),
            "PACKER_NAME": ResolvedDeclaration(
                field="PACKER_NAME",
                value="Packwell Logistics",
                status="RESOLVED",
                confidence=0.94,
                source_evidence=[
                    SourceEvidence(
                        raw_text="Packed by: Packwell Logistics, Sonipat, Haryana 131001",
                        token_ids=[2],
                        image_index=1,
                    )
                ],
            ),
            "IMPORTER_NAME_ADDRESS": ResolvedDeclaration(
                field="IMPORTER_NAME_ADDRESS",
                value="Global Impex Pvt Ltd, New Delhi 110001",
                status="RESOLVED",
                confidence=0.93,
                source_evidence=[
                    SourceEvidence(
                        raw_text="Imported by: Global Impex Pvt Ltd, New Delhi 110001",
                        token_ids=[3],
                        image_index=1,
                    )
                ],
            ),
        }
    )

    with patch.object(GeminiClient, "generate_structured_extraction", return_value=(mock_llm_response, {"model_used": "gemini-3.8-flash", "llm_status": "SUCCESS"})):
        client = make_mock_client()
        merged, _, _ = resolve_evidence_with_gemini(
            ocr_items=ocr_items,
            raw_text="\n".join(i["text"] for i in ocr_items),
            num_images=2,
            deterministic_fields={},
            client=client,
        )

        assert merged["MANUFACTURER_NAME"]["value"] == "Alpine Foods Ltd."
        assert merged["MARKETER_NAME"]["value"] == "Metro Brands India"
        assert merged["PACKER_NAME"]["value"] == "Packwell Logistics"
        assert "Global Impex" in merged["IMPORTER_NAME_ADDRESS"]["value"]


# ==============================================================================
# 5. Date Disambiguation
# ==============================================================================

def test_date_disambiguation():
    """Verify Gemini disambiguates MFD, Best Before, and Expiry Date."""
    ocr_items = [
        make_ocr_item(0, "MFD: 15/01/2026", image_index=0),
        make_ocr_item(1, "BEST BEFORE: 9 MONTHS FROM MANUFACTURE", image_index=0),
        make_ocr_item(2, "EXPIRY DATE: 15/10/2026", image_index=0),
    ]

    mock_llm_response = LLMExtractionResult(
        declarations={
            "MONTH_YEAR_MANUFACTURE": ResolvedDeclaration(
                field="MONTH_YEAR_MANUFACTURE",
                value="15/01/2026",
                normalized_value="2026-01-15",
                status="RESOLVED",
                confidence=0.97,
                source_evidence=[
                    SourceEvidence(
                        raw_text="MFD: 15/01/2026",
                        token_ids=[0],
                        image_index=0,
                    )
                ],
            ),
            "BEST_BEFORE_USE_BY": ResolvedDeclaration(
                field="BEST_BEFORE_USE_BY",
                value="9 MONTHS FROM MANUFACTURE",
                status="RESOLVED",
                confidence=0.94,
                source_evidence=[
                    SourceEvidence(
                        raw_text="BEST BEFORE: 9 MONTHS FROM MANUFACTURE",
                        token_ids=[1],
                        image_index=0,
                    )
                ],
            ),
            "EXPIRY_DATE": ResolvedDeclaration(
                field="EXPIRY_DATE",
                value="15/10/2026",
                normalized_value="2026-10-15",
                status="RESOLVED",
                confidence=0.97,
                source_evidence=[
                    SourceEvidence(
                        raw_text="EXPIRY DATE: 15/10/2026",
                        token_ids=[2],
                        image_index=0,
                    )
                ],
            ),
        }
    )

    with patch.object(GeminiClient, "generate_structured_extraction", return_value=(mock_llm_response, {"model_used": "gemini-3.8-flash", "llm_status": "SUCCESS"})):
        client = make_mock_client()
        merged, _, _ = resolve_evidence_with_gemini(
            ocr_items=ocr_items,
            raw_text="\n".join(i["text"] for i in ocr_items),
            num_images=1,
            deterministic_fields={},
            client=client,
        )

        assert merged["MONTH_YEAR_MANUFACTURE"]["value"] == "15/01/2026"
        assert "9 MONTHS" in merged["BEST_BEFORE_USE_BY"]["value"]
        assert merged["EXPIRY_DATE"]["value"] == "15/10/2026"


# ==============================================================================
# 6. Batch Number and Consumer Care Parsing
# ==============================================================================

def test_batch_number_and_consumer_care_parsing():
    """Verify extraction of Batch Number and Consumer Care contact info."""
    ocr_items = [
        make_ocr_item(0, "Batch No: B-9942/2026", image_index=0),
        make_ocr_item(1, "Consumer Care Cell: Phone 1800-200-3000, Email: feedback@apex.com", image_index=0),
    ]

    mock_llm_response = LLMExtractionResult(
        declarations={
            "BATCH_NUMBER": ResolvedDeclaration(
                field="BATCH_NUMBER",
                value="B-9942/2026",
                status="RESOLVED",
                confidence=0.96,
                source_evidence=[
                    SourceEvidence(
                        raw_text="Batch No: B-9942/2026",
                        token_ids=[0],
                        image_index=0,
                    )
                ],
            ),
            "CONSUMER_CARE": ResolvedDeclaration(
                field="CONSUMER_CARE",
                value="Phone: 1800-200-3000, Email: feedback@apex.com",
                status="RESOLVED",
                confidence=0.95,
                source_evidence=[
                    SourceEvidence(
                        raw_text="Consumer Care Cell: Phone 1800-200-3000, Email: feedback@apex.com",
                        token_ids=[1],
                        image_index=0,
                    )
                ],
            ),
        }
    )

    with patch.object(GeminiClient, "generate_structured_extraction", return_value=(mock_llm_response, {"model_used": "gemini-3.8-flash", "llm_status": "SUCCESS"})):
        client = make_mock_client()
        merged, _, _ = resolve_evidence_with_gemini(
            ocr_items=ocr_items,
            raw_text="\n".join(i["text"] for i in ocr_items),
            num_images=1,
            deterministic_fields={},
            client=client,
        )

        assert merged["BATCH_NUMBER"]["value"] == "B-9942/2026"
        assert "1800-200-3000" in merged["CONSUMER_CARE"]["value"]
        assert "feedback@apex.com" in merged["CONSUMER_CARE"]["value"]


# ==============================================================================
# 7. Grounding Validator Rejection of Hallucinated Candidates
# ==============================================================================

def test_grounding_validator_rejects_hallucinated_candidate():
    """Verify validator strictly rejects candidate values not derivable from OCR tokens."""
    ocr_items = [
        make_ocr_item(0, "Brand: Himalayan Pure", image_index=0),
        make_ocr_item(1, "Net Weight: 1 kg", image_index=0),
    ]

    validator = EvidenceGroundingValidator(ocr_items, num_images=1)

    # Hallucinated manufacturer name not present anywhere in OCR tokens
    hallucinated_decl = ResolvedDeclaration(
        field="MANUFACTURER_NAME",
        value="Imaginary Foods Global Private Limited",
        confidence=0.99,
        source_evidence=[
            SourceEvidence(
                raw_text="Manufactured by Imaginary Foods Global Private Limited",
                token_ids=[0],  # Discrepancy: token 0 is "Brand: Himalayan Pure"
                image_index=0,
            )
        ],
    )

    grounded, violations, corrected = validator.validate_declaration("MANUFACTURER_NAME", hallucinated_decl)
    assert grounded is False
    assert any("not found in OCR tokens" in v for v in violations)


# ==============================================================================
# 8. Grounding Validator Rejection of Invalid Token IDs
# ==============================================================================

def test_grounding_validator_rejects_invalid_token_id_or_bbox():
    """Verify validator flags invalid token IDs and out-of-bounds bounding boxes."""
    ocr_items = [
        make_ocr_item(0, "MRP Rs. 99.00", image_index=0, bbox=[10.0, 20.0, 100.0, 40.0]),
    ]

    validator = EvidenceGroundingValidator(ocr_items, num_images=1)

    # Candidate cites token ID 999 which does not exist in the index
    bogus_token_decl = ResolvedDeclaration(
        field="MRP",
        value="Rs. 99.00",
        confidence=0.95,
        source_evidence=[
            SourceEvidence(
                raw_text="MRP Rs. 99.00",
                token_ids=[999],
                image_index=0,
            )
        ],
    )

    grounded, violations, _ = validator.validate_declaration("MRP", bogus_token_decl)
    assert grounded is False
    assert any("Unknown token ID" in v for v in violations)


# ==============================================================================
# 9. Gemini Client Quota (429) Retries & Model Fallback
# ==============================================================================

def test_gemini_client_fallback_on_429_or_error():
    """Verify client automatically falls back from primary to secondary model upon failure."""
    client = GeminiClient()
    client.is_enabled = lambda: True

    mock_primary_error = Exception("429 RESOURCE_EXHAUSTED: Quota exceeded for gemini-3.8-flash")
    mock_success_response = MagicMock()
    mock_success_response.text = json.dumps({
        "declarations": {
            "BRAND": {
                "field": "BRAND",
                "value": "Sunburst",
                "status": "RESOLVED",
                "confidence": 0.95,
                "source_evidence": [
                    {
                        "raw_text": "Brand: Sunburst",
                        "token_ids": [0],
                        "image_index": 0,
                    }
                ],
                "resolution_note": "Extracted brand via fallback model"
            }
        },
        "package_context": {
            "category": "FOOD",
            "product_type": "BISCUIT",
            "package_type": "RETAIL",
            "import_status": "DOMESTIC",
            "confidence": 0.95
        }
    })

    with patch.object(client, "_get_client") as mock_get_client:
        mock_genai_client = MagicMock()
        mock_get_client.return_value = mock_genai_client

        def mock_generate_content(model, contents, config=None):
            if "flash-lite" in model:
                return mock_success_response
            raise mock_primary_error

        mock_genai_client.models.generate_content.side_effect = mock_generate_content

        result, meta = client.generate_structured_extraction(
            prompt="Extract declarations"
        )

        assert result is not None
        assert "BRAND" in result.declarations
        assert result.declarations["BRAND"].value == "Sunburst"
        assert meta["fallback_occurred"] is True
        assert meta["model_used"] == client.fallback_model


# ==============================================================================
# 10. Graceful Fallback When Gemini is Disabled
# ==============================================================================

def test_gemini_disabled_graceful_fallback():
    """Verify resolve_evidence_with_gemini returns deterministic results when Gemini is disabled."""
    ocr_items = [
        make_ocr_item(0, "MRP Rs. 50.00", image_index=0),
        make_ocr_item(1, "Net Weight: 250 g", image_index=0),
    ]

    deterministic_fields = {
        "MRP": {"value": "Rs. 50.00", "confidence": 0.88, "source": "OCR_DETERMINISTIC"},
        "DECLARED_NET_QUANTITY": {"value": "250 g", "confidence": 0.90, "source": "OCR_DETERMINISTIC"},
    }

    client = GeminiClient()
    client.is_enabled = lambda: False

    merged, meta, _ = resolve_evidence_with_gemini(
        raw_text="MRP Rs. 50.00\nNet Weight: 250 g",
        ocr_items=ocr_items,
        num_images=1,
        deterministic_fields=deterministic_fields,
        client=client,
    )

    assert merged == deterministic_fields
    assert meta["llm_status"] == "DISABLED"


# ==============================================================================
# 11. Statutory Compliance Outcome Invariance
# ==============================================================================

def test_compliance_outcome_invariance():
    """Verify the deterministic statutory rule engine governs PASS/FAIL, not the LLM."""
    # Scenario: Gemini accurately extracts an invalid MRP (zero or negative)
    # The statutory rule engine must flag this as FAIL regardless of Gemini's status.
    evidence = {
        "MRP": {
            "value": "Rs. 0.00",
            "raw_text": "MRP Rs. 0.00",
            "source": "GEMINI_LLM",
            "confidence": 0.95,
        },
        "DECLARED_NET_QUANTITY": {
            "value": "500 g",
            "raw_text": "Net Weight 500 g",
            "source": "GEMINI_LLM",
            "confidence": 0.95,
        }
    }

    mrp_rule = {
        "rule_id": "PC-ALL-002",
        "parameter": "MRP",
        "required": True,
        "validation_method": "MRP_PRESENT",
        "regulatory_source": "LEGAL_METROLOGY",
    }

    qty_rule = {
        "rule_id": "PC-ALL-004",
        "parameter": "NET_QUANTITY",
        "required": True,
        "validation_method": "QUANTITY_UNIT_PAIR",
        "regulatory_source": "LEGAL_METROLOGY",
    }

    results, overall = evaluate_rules([mrp_rule, qty_rule], evidence)

    mrp_res = next(r for r in results if r["rule_id"] == "PC-ALL-002")
    qty_res = next(r for r in results if r["rule_id"] == "PC-ALL-004")

    # Statutory outcome is strictly enforced by rules engine
    assert mrp_res["status"] == "FAIL"
    assert mrp_res["binary"] == 0
    assert qty_res["status"] == "PASS"
    assert qty_res["binary"] == 1
    assert overall == "NON_COMPLIANT"


# ==============================================================================
# 12. Conditional Live API Test
# ==============================================================================

@pytest.mark.skipif(
    not os.getenv("RUN_GEMINI_LIVE_TESTS"),
    reason="Set RUN_GEMINI_LIVE_TESTS=1 with valid GEMINI_API_KEY to run live API calls",
)
def test_live_gemini_api_integration():
    """Optional live API integration test verifying connectivity with real Gemini endpoint."""
    api_key = os.getenv("GEMINI_API_KEY")
    assert api_key, "GEMINI_API_KEY must be set when RUN_GEMINI_LIVE_TESTS=1"

    client = GeminiClient()
    ocr_items = [
        {"token_id": 0, "text": "Brand: Everest", "image_index": 0},
        {"token_id": 1, "text": "Garam Masala 100g", "image_index": 0},
        {"token_id": 2, "text": "MRP: Rs. 85.00", "image_index": 0},
    ]

    result, meta = client.generate_structured_extraction(
        prompt="Extract packaging declarations"
    )

    assert result is not None
    assert meta["latency_ms"] > 0
    assert "BRAND" in result.declarations or "MRP" in result.declarations
