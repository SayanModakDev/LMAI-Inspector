"""Regression coverage for Tata Salt accuracy fixes (offline; no Gemini calls)."""

import cv2
import numpy as np
from unittest.mock import MagicMock

from app.core.ontology import extract_contextual_emails, normalize_contextual_email
from app.extraction.declaration_extractor import extract_declarations
from app.rules.validators import (
    dispatch_validator,
    validate_address_present,
    validate_consumer_care_present,
)
from app.llm.evidence_resolver import resolve_evidence_with_gemini
from app.llm.schemas import LLMExtractionResult, ResolvedDeclaration, SourceEvidence
from app.visual_detection import aggregate_food_symbol_evidence, detect_food_symbol


def _canvas() -> np.ndarray:
    return np.full((300, 300, 3), 245, dtype=np.uint8)


def _symbol(symbol_type: str) -> np.ndarray:
    image = _canvas()
    colour = (30, 140, 30) if symbol_type == "VEGETARIAN" else (20, 45, 120)
    cv2.rectangle(image, (105, 105), (195, 195), colour, 5)
    if symbol_type == "VEGETARIAN":
        cv2.circle(image, (150, 150), 24, colour, -1)
    else:
        points = np.array([[150, 122], [126, 169], [174, 169]], dtype=np.int32)
        cv2.fillPoly(image, [points], colour)
    return image


def _address_rule():
    return {"rule_id": "PC-ALL-005", "parameter": "MANUFACTURER_ADDRESS", "required": True}


def _care_rule():
    return {"rule_id": "PC-ALL-008", "parameter": "CONSUMER_CARE", "required": True}


def test_supported_vegetarian_symbol_and_provenance():
    result = detect_food_symbol(_symbol("VEGETARIAN"))
    assert result["symbol_type"] == "VEGETARIAN"
    accepted = [candidate for candidate in result["candidates"] if candidate["accepted"]]
    assert accepted and len(accepted[0]["bbox"]) == 4


def test_supported_nonvegetarian_symbol():
    result = detect_food_symbol(_symbol("NON_VEGETARIAN"))
    assert result["detected"] is True
    assert result["symbol_type"] == "NON_VEGETARIAN"


def test_decorative_green_graphic_is_rejected_without_prescribed_square():
    image = _canvas()
    cv2.circle(image, (150, 150), 30, (30, 140, 30), -1)
    result = detect_food_symbol(image)
    assert result["detected"] is False
    assert not any(candidate["accepted"] for candidate in result.get("candidates", []))
    assert any("enclosing square" in candidate["decision_reason"] for candidate in result["candidates"])


def test_same_supported_symbol_on_multiple_panels_is_not_a_conflict():
    merged = aggregate_food_symbol_evidence([
        (detect_food_symbol(_symbol("VEGETARIAN")), 0),
        (detect_food_symbol(_symbol("VEGETARIAN")), 2),
    ])
    assert merged["status"] == "CANDIDATE"
    assert merged["symbol_type"] == "VEGETARIAN"
    assert {item["image_index"] for item in merged["supporting_candidates"]} == {0, 2}


def test_valid_symbol_plus_demonstrable_false_positive_is_not_a_conflict():
    decorative = _canvas()
    cv2.circle(decorative, (100, 100), 25, (20, 45, 120), -1)
    merged = aggregate_food_symbol_evidence([
        (detect_food_symbol(_symbol("VEGETARIAN")), 0),
        (detect_food_symbol(decorative), 1),
    ])
    assert merged["status"] == "CANDIDATE"
    assert merged["symbol_type"] == "VEGETARIAN"
    assert any(
        item["image_index"] == 1 and item["accepted"] is False
        for item in merged["candidates"]
    )


def test_two_genuinely_supported_contradictory_symbols_remain_unresolved():
    merged = aggregate_food_symbol_evidence([
        (detect_food_symbol(_symbol("VEGETARIAN")), 0),
        (detect_food_symbol(_symbol("NON_VEGETARIAN")), 1),
    ])
    assert merged["status"] == "CONFLICTING_EVIDENCE"
    assert merged["has_conflict"] is True
    assert {item["symbol_type"] for item in merged["competing_candidates"]} == {
        "VEGETARIAN", "NON_VEGETARIAN"
    }


def test_insufficient_symbol_evidence_does_not_fabricate_detection():
    merged = aggregate_food_symbol_evidence([(detect_food_symbol(_canvas()), 4)])
    assert merged["status"] == "NOT_VERIFIABLE"
    assert merged["detected"] is False


def test_isolated_state_is_partial_and_not_a_false_pass():
    evidence = {"value": "Gujarat", "confidence": 0.9, "role": "MANUFACTURER"}
    result = validate_address_present(evidence, _address_rule(), {})
    assert result.status == "NOT_VERIFIABLE"
    assert "structurally incomplete" in result.reason

    state_and_pin = {"value": "Gujarat 361345", "confidence": 0.9, "role": "MANUFACTURER"}
    assert validate_address_present(state_and_pin, _address_rule(), {}).status == "NOT_VERIFIABLE"


def test_supported_full_address_remains_eligible_for_pass():
    evidence = {
        "value": "P.O. Mithapur, District Devbhumi Dwarka, Gujarat 361345, India",
        "confidence": 0.9,
        "role": "MANUFACTURER",
    }
    assert validate_address_present(evidence, _address_rule(), {}).status == "PASS"


def test_manufacturer_and_marketer_addresses_are_not_merged():
    fields = extract_declarations(
        "Manufactured by: Pioneer Foods Pvt Ltd\n"
        "Plot 4, Industrial Area, Pune, Maharashtra 411001\n"
        "Marketed by: Global Retail Ventures Ltd\n"
        "Tower 2, Market Road, Mumbai, Maharashtra 400001"
    )
    assert "Pune" in fields["MANUFACTURER_ADDRESS"]["value"]
    assert "Mumbai" not in fields["MANUFACTURER_ADDRESS"]["value"]
    assert "Mumbai" in fields["MARKETER_ADDRESS"]["value"]

    marketer_only = extract_declarations(
        "Marketed by: Global Retail Ventures Ltd\n"
        "Tower 2, Market Road, Mumbai, Maharashtra 400001"
    )
    assert marketer_only["MANUFACTURER_ADDRESS"]["role"] == "MARKETER"
    assert validate_address_present(
        marketer_only["MANUFACTURER_ADDRESS"], _address_rule(), marketer_only
    ).status == "NOT_VERIFIABLE"


def test_incomplete_ocr_address_is_preserved_as_partial_not_invented():
    fields = extract_declarations("Manufactured by: Tata Chemicals Limited\nGujarat")
    address = fields["MANUFACTURER_ADDRESS"]
    assert address["value"] == "Gujarat"
    assert address["address_completeness"] == "PARTIAL"
    assert validate_address_present(address, _address_rule(), fields).status == "NOT_VERIFIABLE"


def test_existing_complete_address_extraction_retains_ocr_provenance():
    items = [
        {"token_id": 1, "text": "Manufactured by: Tata Chemicals Limited", "bbox": [10, 10, 260, 30], "confidence": 0.96, "image_index": 1},
        {"token_id": 2, "text": "P.O. Mithapur, District Devbhumi Dwarka", "bbox": [10, 35, 280, 55], "confidence": 0.95, "image_index": 1},
        {"token_id": 3, "text": "Gujarat 361345 India", "bbox": [10, 60, 190, 80], "confidence": 0.94, "image_index": 1},
    ]
    fields = extract_declarations("\n".join(item["text"] for item in items), ocr_items=items)
    address = fields["MANUFACTURER_ADDRESS"]
    assert address["address_completeness"] == "SUFFICIENT"
    assert address["source_image_index"] == 1
    assert {ev["token_id"] for ev in address["source_evidence"]} >= {2, 3}


def test_joined_email_label_is_removed_only_with_supporting_context():
    supported = extract_contextual_emails("Consumer Care: EMAILcare@example.com")
    assert supported[0]["value"] == "care@example.com"
    assert supported[0]["raw_value"] == "EMAILcare@example.com"
    assert normalize_contextual_email(
        "EMAILcare@example.com", "The account EMAILcare@example.com belongs to a user"
    ) == "EMAILcare@example.com"


def test_colon_space_and_hyphen_email_labels_normalize_safely():
    assert extract_contextual_emails("EMAIL:care@example.com")[0]["value"] == "care@example.com"
    assert extract_contextual_emails("EMAIL care@example.com")[0]["value"] == "care@example.com"
    assert extract_contextual_emails("Email-care@example.com")[0]["value"] == "care@example.com"


def test_consumer_care_extractor_preserves_raw_email_ocr():
    fields = extract_declarations("Consumer Care: EMAILcare@tataconsumer.com")
    care = fields["CONSUMER_CARE"]
    assert care["contact_value"] == "care@tataconsumer.com"
    assert "EMAILcare@tataconsumer.com" in care["raw_text"]
    assert validate_consumer_care_present(care, _care_rule(), fields).status == "PASS"


def test_malformed_email_is_not_accepted_merely_for_at_character():
    result = validate_consumer_care_present(
        {"value": "Email: care@@example..com", "confidence": 0.9}, _care_rule(), {}
    )
    assert result.status == "FAIL"


def test_phone_and_postal_consumer_contacts_remain_supported():
    phone = extract_declarations("Consumer Care: 1800-123-4567")["CONSUMER_CARE"]
    assert phone["contact_value"] == "1800-123-4567"
    assert validate_consumer_care_present(phone, _care_rule(), {}).status == "PASS"

    postal = {
        "value": "Consumer Care, P.O. Box 45, Mumbai 400001",
        "raw_text": "Consumer Care, P.O. Box 45, Mumbai 400001",
        "confidence": 0.9,
    }
    assert validate_consumer_care_present(postal, _care_rule(), {}).status == "PASS"


def test_semantic_contact_without_ocr_support_is_not_verifiable():
    evidence = {
        "value": "care@example.com",
        "confidence": 0.95,
        "source": "OCR_GEMINI_RESOLVED",
        "source_evidence": [],
    }
    assert validate_consumer_care_present(evidence, _care_rule(), {}).status == "NOT_VERIFIABLE"


def test_grounded_partial_llm_address_does_not_replace_full_deterministic_address():
    ocr_items = [{
        "token_id": 7, "text": "Gujarat", "image_index": 0,
        "bbox": [10, 10, 80, 30], "confidence": 0.96,
    }]
    llm_result = LLMExtractionResult(resolved_declarations=[ResolvedDeclaration(
        field="MANUFACTURER_ADDRESS",
        value="Gujarat",
        status="RESOLVED",
        confidence=0.95,
        source_evidence=[SourceEvidence(
            image_index=0, token_ids=[7], raw_text="Gujarat",
            bbox=[10, 10, 80, 30], ocr_confidence=0.96,
        )],
    )])
    client = MagicMock()
    client.is_enabled.return_value = True
    client.generate_structured_extraction.return_value = (
        llm_result, {"llm_status": "SUCCESS", "model_used": "mock"}
    )
    deterministic = {
        "MANUFACTURER_ADDRESS": {
            "value": "P.O. Mithapur, District Devbhumi Dwarka, Gujarat 361345, India",
            "confidence": 0.8,
            "role": "MANUFACTURER",
            "source": "OCR",
        }
    }
    merged, _, _ = resolve_evidence_with_gemini(
        ocr_items=ocr_items,
        raw_text="Gujarat",
        num_images=1,
        deterministic_fields=deterministic,
        client=client,
    )
    assert merged["MANUFACTURER_ADDRESS"]["value"].startswith("P.O. Mithapur")


def test_grounded_llm_contact_normalizes_label_but_keeps_raw_value():
    raw = "Consumer Care: EMAILcare@tataconsumer.com"
    ocr_items = [{
        "token_id": 9, "text": raw, "image_index": 0,
        "bbox": [10, 10, 280, 30], "confidence": 0.97,
    }]
    llm_result = LLMExtractionResult(resolved_declarations=[ResolvedDeclaration(
        field="CONSUMER_CARE",
        value="EMAILcare@tataconsumer.com",
        normalized_value="EMAILcare@tataconsumer.com",
        status="RESOLVED",
        confidence=0.96,
        source_evidence=[SourceEvidence(
            image_index=0, token_ids=[9], raw_text=raw,
            bbox=[10, 10, 280, 30], ocr_confidence=0.97,
        )],
    )])
    client = MagicMock()
    client.is_enabled.return_value = True
    client.generate_structured_extraction.return_value = (
        llm_result, {"llm_status": "SUCCESS", "model_used": "mock"}
    )
    merged, _, _ = resolve_evidence_with_gemini(
        ocr_items=ocr_items, raw_text=raw, num_images=1,
        deterministic_fields={}, client=client,
    )
    care = merged["CONSUMER_CARE"]
    assert care["value"] == "care@tataconsumer.com"
    assert care["raw_value"] == "EMAILcare@tataconsumer.com"
    assert care["source_evidence"]


def test_rule_dispatch_keeps_partial_address_uncertain_and_physical_checks_separate():
    address_result = dispatch_validator(
        "ADDRESS_PRESENT",
        {"value": "Gujarat", "confidence": 0.9, "role": "MANUFACTURER"},
        _address_rule(),
        {},
    )
    weight_result = dispatch_validator(
        "PHYSICAL_WEIGHT_CHECK", None,
        {"rule_id": "PC-ALL-012", "parameter": "ACTUAL_NET_CONTENT", "required": True},
        {},
    )
    font_result = dispatch_validator(
        "FONT_SIZE_CHECK", None,
        {"rule_id": "PC-ALL-013", "parameter": "FONT_SIZE_COMPLIANCE", "required": True},
        {},
    )
    assert address_result.status == "NOT_VERIFIABLE"
    assert weight_result.status == "NOT_VERIFIABLE"
    assert font_result.status == "NOT_VERIFIABLE"


def test_sensodyne_deterministic_behavior_does_not_regress():
    fields = extract_declarations(
        "Sensodyne Fresh Mint Toothpaste\nDENTIST RECOMMENDED BRAND\n"
        "MRP Rs 135\nNet quantity 75 g"
    )
    assert fields["PRODUCT_NAME"]["value"] == "Sensodyne Fresh Mint Toothpaste"
    assert fields["DECLARED_NET_QUANTITY"]["value"] == "75 g"
