"""Regression coverage for Tata Salt accuracy fixes (offline; no Gemini calls)."""

from pathlib import Path

import cv2
import numpy as np
import pytest
from unittest.mock import MagicMock

from app.core.ontology import extract_contextual_emails, normalize_contextual_email
from app.extraction.declaration_extractor import extract_declarations, merge_extracted_fields
from app.rules.validators import (
    dispatch_validator,
    validate_address_present,
    validate_consumer_care_present,
    validate_manufacturer_present,
)
from app.rules.rule_engine import calculate_rule_summary, derive_screening_result
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


def test_prescribed_symbol_survives_localized_frame_glare():
    image = _symbol("VEGETARIAN")
    # A narrow highlight breaks two parts of the printed frame while leaving
    # the inner shape and the remaining local side support observable.
    cv2.rectangle(image, (146, 102), (155, 112), (255, 255, 255), -1)
    result = detect_food_symbol(image)
    assert result["detected"] is True
    assert result["status"] == "VERIFIED"
    assert result["symbol_type"] == "VEGETARIAN"


def test_prescribed_symbol_survives_mild_package_perspective():
    image = _symbol("VEGETARIAN")
    source = np.float32([[0, 0], [299, 0], [299, 299], [0, 299]])
    destination = np.float32([[12, 6], [288, 18], [296, 288], [4, 280]])
    transform = cv2.getPerspectiveTransform(source, destination)
    warped = cv2.warpPerspective(image, transform, (300, 300), borderValue=(245, 245, 245))
    result = detect_food_symbol(warped)
    assert result["detected"] is True
    assert result["status"] == "VERIFIED"
    assert result["symbol_type"] == "VEGETARIAN"


def test_same_supported_symbol_on_multiple_panels_is_not_a_conflict():
    merged = aggregate_food_symbol_evidence([
        (detect_food_symbol(_symbol("VEGETARIAN")), 0),
        (detect_food_symbol(_symbol("VEGETARIAN")), 2),
    ])
    assert merged["status"] == "VERIFIED"
    assert merged["candidate_status"] == "CONFIRMED"
    assert merged["visual_confirmation"]["confirmed"] is True
    assert merged["symbol_type"] == "VEGETARIAN"
    assert {item["image_index"] for item in merged["supporting_candidates"]} == {0, 2}


def test_valid_symbol_plus_demonstrable_false_positive_is_not_a_conflict():
    decorative = _canvas()
    cv2.circle(decorative, (100, 100), 25, (20, 45, 120), -1)
    merged = aggregate_food_symbol_evidence([
        (detect_food_symbol(_symbol("VEGETARIAN")), 0),
        (detect_food_symbol(decorative), 1),
    ])
    assert merged["status"] == "VERIFIED"
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


def test_confirmed_visual_symbol_passes_without_ocr_evidence():
    merged = aggregate_food_symbol_evidence([(detect_food_symbol(_symbol("VEGETARIAN")), 4)])
    evidence = {
        **merged,
        "source": "VISUAL_DETECTION",
        "candidate_status": "CONFIRMED",
    }
    result = dispatch_validator(
        "VEG_NONVEG_PRESENT",
        evidence,
        {"rule_id": "PC-FOOD-005", "parameter": "VEG_NONVEG_SYMBOL", "required": True},
        {},
    )
    assert result.status == "PASS"
    assert result.evidence_state == "EVIDENCE_VERIFIED"
    assert "OCR" not in result.reason


def test_high_confidence_visual_candidate_without_structural_confirmation_stays_review():
    evidence = {
        "value": "VEGETARIAN",
        "symbol_type": "VEGETARIAN",
        "confidence": 0.99,
        "source": "VISUAL_DETECTION",
        "detected": True,
        "status": "CANDIDATE",
        "candidate_status": "CANDIDATE",
        "is_candidate": True,
        "supporting_candidates": [],
    }
    result = dispatch_validator(
        "VEG_NONVEG_PRESENT",
        evidence,
        {"rule_id": "PC-FOOD-005", "parameter": "VEG_NONVEG_SYMBOL", "required": True},
        {},
    )
    assert result.status == "NOT_VERIFIABLE"
    assert "Missing confirmation requirement" in result.reason
    assert "accepted prescribed-geometry candidate" in result.reason


def test_insufficient_symbol_evidence_does_not_fabricate_detection():
    merged = aggregate_food_symbol_evidence([(detect_food_symbol(_canvas()), 4)])
    assert merged["status"] == "NOT_VERIFIABLE"
    assert merged["detected"] is False


def test_symbol_non_detection_rule_reason_describes_visual_evidence():
    reason = "No supported prescribed food symbol detected on package images."
    result = dispatch_validator(
        "VEG_NONVEG_PRESENT",
        {
            "value": "NOT_DETECTED",
            "symbol_type": "UNKNOWN",
            "source": "VISUAL_DETECTION",
            "status": "REVIEW",
            "reason": reason,
            "confidence": 0.0,
        },
        {"parameter": "VEG_NONVEG_SYMBOL", "required": True},
        {},
    )
    assert result.status == "NOT_VERIFIABLE"
    assert result.reason == reason
    assert "OCR" not in result.reason


def test_real_tata_salt_four_image_visual_regression():
    uploads = Path(__file__).resolve().parents[1] / "uploads"
    image_names = [
        "scan_20260910_190520_513508b9372c.jpg",
        "scan_20260910_190520_52c81405cfd7.jpg",
        "scan_20260910_190520_2f23e3d63d6e.jpg",
        "scan_20260910_190520_54443dd38913.jpg",
    ]
    paths = [uploads / name for name in image_names]
    if not all(path.exists() for path in paths):
        pytest.skip("Original four Tata Salt regression images are not available locally")

    panel_results = [(detect_food_symbol(str(path)), index) for index, path in enumerate(paths)]
    merged = aggregate_food_symbol_evidence(panel_results)

    assert merged["status"] == "VERIFIED"
    assert merged["symbol_type"] == "VEGETARIAN"
    assert merged["source_image_index"] == 0
    assert merged["has_conflict"] is False
    accepted = [item for item in merged["supporting_candidates"] if item["accepted"]]
    assert len(accepted) == 1
    assert accepted[0]["frame_detection"] == "fragmented_same_colour_frame"
    assert accepted[0]["frame_metrics"]["interior_annulus_density"] <= 0.16


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
    assert "MANUFACTURER_NAME" not in marketer_only
    assert "MANUFACTURER_ADDRESS" not in marketer_only
    assert marketer_only["MARKETER_NAME"]["role"] == "MARKETER"
    assert validate_manufacturer_present(
        marketer_only["MARKETER_NAME"],
        {"parameter": "MANUFACTURER_NAME", "required": True},
        marketer_only,
    ).status == "NOT_VERIFIABLE"


def test_damaged_mk_by_label_remains_marketer_evidence_only():
    items = [
        {
            "token_id": 1,
            "text": "Mk byata nr Products Limited",
            "bbox": [100, 100, 360, 120],
            "confidence": 0.74,
            "image_index": 1,
        },
        {
            "token_id": 2,
            "text": "Tata Centre, 1st Floor, 43 Jawaharlal Nehru Road",
            "bbox": [100, 124, 470, 146],
            "confidence": 0.90,
            "image_index": 1,
        },
        {
            "token_id": 3,
            "text": "Kolkata 700071",
            "bbox": [100, 150, 230, 170],
            "confidence": 0.96,
            "image_index": 1,
        },
    ]
    fields = extract_declarations("\n".join(item["text"] for item in items), ocr_items=items)

    assert "MANUFACTURER_NAME" not in fields
    assert "MANUFACTURER_ADDRESS" not in fields
    assert fields["MARKETER_NAME"]["role"] == "MARKETER"
    assert fields["MARKETER_NAME"]["source_image_index"] == 1
    assert fields["MARKETER_NAME"]["bbox"] == [100, 100, 360, 120]
    assert fields["MARKETER_NAME"]["source_evidence"][0]["raw_text"] == "Mk byata nr Products Limited"
    assert "Kolkata" in fields["MARKETER_ADDRESS"]["value"]


def test_gemini_grounding_cannot_promote_damaged_marketer_to_manufacturer():
    raw = "Mk byata nr Products Limited\nTata Centre, 1st Floor, Kolkata 700071"
    items = [
        {
            "token_id": 1,
            "text": "Mk byata nr Products Limited",
            "bbox": [100, 100, 350, 120],
            "confidence": 0.74,
            "image_index": 1,
        },
        {
            "token_id": 2,
            "text": "Tata Centre, 1st Floor, Kolkata 700071",
            "bbox": [100, 125, 400, 150],
            "confidence": 0.90,
            "image_index": 1,
        },
    ]
    deterministic = extract_declarations(raw, ocr_items=items)
    llm_result = LLMExtractionResult(resolved_declarations=[ResolvedDeclaration(
        field="MANUFACTURER_NAME",
        value="Mk byata nr Products Limited",
        status="RESOLVED",
        confidence=0.95,
        source_evidence=[SourceEvidence(
            image_index=1,
            token_ids=[1],
            raw_text="Mk byata nr Products Limited",
            bbox=[100, 100, 350, 120],
            ocr_confidence=0.74,
        )],
    )])
    client = MagicMock()
    client.is_enabled.return_value = True
    client.generate_structured_extraction.return_value = (
        llm_result,
        {"llm_status": "SUCCESS", "model_used": "mock"},
    )

    merged, metadata, _ = resolve_evidence_with_gemini(
        ocr_items=items,
        raw_text=raw,
        num_images=2,
        deterministic_fields=deterministic,
        client=client,
    )

    assert "MANUFACTURER_NAME" not in merged
    assert merged["MARKETER_NAME"]["role"] == "MARKETER"
    assert metadata["role_resolution_rejections"][0]["role_audit"]["roles"] == ["MARKETER"]


def test_tata_role_blocks_keep_original_image_and_distinct_bounding_boxes():
    items = [
        {"token_id": 10, "text": "Mkt by: Tata Consumer Products Limited", "bbox": [100, 100, 400, 120], "confidence": 0.94, "image_index": 1},
        {"token_id": 11, "text": "1st Floor, 43, Jawaharlal Nehru Road", "bbox": [100, 124, 380, 145], "confidence": 0.90, "image_index": 1},
        {"token_id": 12, "text": "Kolkata - 700 071", "bbox": [100, 148, 250, 168], "confidence": 0.95, "image_index": 1},
        {"token_id": 13, "text": "Mfg by: Tata Chemicals Limited", "bbox": [100, 180, 350, 200], "confidence": 0.92, "image_index": 1},
        {"token_id": 14, "text": "Mithapur - 361345, District-Devbhumi Dwarka", "bbox": [100, 204, 430, 226], "confidence": 0.94, "image_index": 1},
        {"token_id": 15, "text": "Gujarat", "bbox": [100, 230, 180, 250], "confidence": 0.96, "image_index": 1},
    ]
    fields = extract_declarations("\n".join(item["text"] for item in items), ocr_items=items)

    assert fields["MANUFACTURER_NAME"]["value"] == "Tata Chemicals Limited"
    assert fields["MARKETER_NAME"]["value"] == "Tata Consumer Products Limited"
    assert fields["MANUFACTURER_ADDRESS"]["source_image_index"] == 1
    assert fields["MARKETER_ADDRESS"]["source_image_index"] == 1
    assert fields["MANUFACTURER_ADDRESS"]["bbox"][1] > fields["MARKETER_ADDRESS"]["bbox"][3]
    assert "Kolkata" not in fields["MANUFACTURER_ADDRESS"]["value"]
    assert "Mithapur" not in fields["MARKETER_ADDRESS"]["value"]


def test_tata_partial_manufacturer_ocr_discards_registration_noise_without_crossing_roles():
    panel_zero = [
        {"token_id": 27, "text": "g.Mtrl.Mfd.By", "bbox": [225, 908, 335, 977], "confidence": 0.7776, "image_index": 0},
        {"token_id": 28, "text": "4037F-25", "bbox": [395, 902, 469, 926], "confidence": 0.9449, "image_index": 0},
        {"token_id": 29, "text": "Regn.No.PR", "bbox": [230, 936, 327, 996], "confidence": 0.9348, "image_index": 0},
    ]
    panel_one = [
        {"token_id": 39, "text": "Mkt byTata Consumer Products LimitedTata Centre", "bbox": [180, 576, 552, 614], "confidence": 0.7392, "image_index": 1},
        {"token_id": 40, "text": "1st Floor 43.Jawaharlal Nehru Road", "bbox": [183, 601, 529, 641], "confidence": 0.7304, "image_index": 1},
        {"token_id": 41, "text": "Kolkata-700071.", "bbox": [183, 628, 309, 662], "confidence": 0.9572, "image_index": 1},
        {"token_id": 43, "text": "Mfg byTata Chemicals LimitedP.O", "bbox": [181, 656, 465, 692], "confidence": 0.8597, "image_index": 1},
        {"token_id": 44, "text": "Gujarat.Lic.No.10012021000351", "bbox": [178, 709, 444, 741], "confidence": 0.9337, "image_index": 1},
    ]
    field_sets = []
    for items in (panel_zero, panel_one):
        field_sets.append(extract_declarations("\n".join(item["text"] for item in items), ocr_items=items))
    merged = merge_extracted_fields(field_sets)

    assert merged["MANUFACTURER_NAME"]["value"] == "Tata Chemicals Limited"
    assert merged["MANUFACTURER_NAME"]["role"] == "MANUFACTURER"
    assert "Regn.No.PR" not in [
        candidate.get("value") for candidate in merged["MANUFACTURER_NAME"].get("candidates", [])
    ]
    assert merged["MARKETER_NAME"]["role"] == "MARKETER"
    assert "Tata Consumer Products" in merged["MARKETER_NAME"]["value"]

    address = merged["MANUFACTURER_ADDRESS"]
    assert address["value"] == "P.O, Gujarat."
    assert address["address_completeness"] == "PARTIAL"
    assert address["source_image_index"] == 1
    assert {item["token_id"] for item in address["source_evidence"]} == {43, 44}
    assert validate_address_present(address, _address_rule(), merged).status == "NOT_VERIFIABLE"
    assert "Kolkata" not in address["value"]


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


def test_optional_barcode_lookup_metadata_is_not_a_declaration_badge():
    from app.api.inspections import get_inspection_detail
    from app.database import models
    from app.database.connection import SessionLocal

    db = SessionLocal()
    try:
        inspection = models.Inspection(
            product_name="Tata Salt",
            category="FOOD",
            overall_result="REVIEW_REQUIRED",
        )
        db.add(inspection)
        db.flush()
        db.add(models.OCRResult(
            inspection_id=inspection.id,
            raw_text="Tata Salt",
            ocr_data={
                "ocr_items": [],
                "images": [],
                "barcode_result": {
                    "value": "8904043901015",
                    "lookup": {"status": "UNAVAILABLE", "source": "Open Food Facts"},
                },
            },
        ))
        db.add_all([
            models.ExtractedField(
                inspection_id=inspection.id,
                field_name="BARCODE",
                field_value="8904043901015",
                confidence=1.0,
                source="BARCODE",
            ),
            # Simulate a legacy record created before supplementary lookup
            # metadata was separated from package declarations.
            models.ExtractedField(
                inspection_id=inspection.id,
                field_name="BARCODE_METADATA",
                field_value=None,
                source="BARCODE_LOOKUP",
            ),
        ])
        db.flush()

        payload = get_inspection_detail(inspection.id, db)
        fields = {item["field_name"]: item for item in payload["extracted_fields"]}
        assert "BARCODE" in fields
        assert "BARCODE_METADATA" not in fields
        assert payload["ocr_result"]["ocr_data"]["barcode_result"]["lookup"]["status"] == "UNAVAILABLE"
        assert payload["summary"]["review_count"] == 0
    finally:
        db.rollback()
        db.close()


def test_tata_status_transition_keeps_overall_review_required():
    before = [
        {"rule_id": f"PASS-{index}", "parameter": f"FIELD_{index}", "status": "PASS"}
        for index in range(8)
    ] + [
        {"rule_id": "PC-ALL-003", "parameter": "MANUFACTURER_NAME", "status": "NOT_VERIFIABLE"},
        {"rule_id": "PC-ALL-004", "parameter": "MANUFACTURER_ADDRESS", "status": "NOT_VERIFIABLE"},
        {"rule_id": "PC-FOOD-005", "parameter": "VEG_NONVEG_SYMBOL", "status": "NOT_VERIFIABLE"},
        {"rule_id": "OPTIONAL", "parameter": "UNIT_SALE_PRICE", "status": "NOT_APPLICABLE"},
    ]
    before_summary = calculate_rule_summary(before)
    assert (before_summary["passed"], before_summary["failed"], before_summary["review"], before_summary["not_applicable"]) == (8, 0, 3, 1)

    after = [dict(row) for row in before]
    for row in after:
        if row["parameter"] in ("MANUFACTURER_NAME", "VEG_NONVEG_SYMBOL"):
            row["status"] = "PASS"
    after_summary = calculate_rule_summary(after)
    assert (after_summary["passed"], after_summary["failed"], after_summary["review"], after_summary["not_applicable"]) == (10, 0, 1, 1)
    assert derive_screening_result(after) == "REVIEW_REQUIRED"
