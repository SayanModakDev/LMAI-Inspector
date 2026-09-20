"""Focused regressions for OCR-grounded product identity roles."""

from unittest.mock import MagicMock

from app.extraction.declaration_extractor import extract_declarations, merge_extracted_fields
from app.llm.evidence_resolver import resolve_evidence_with_gemini
from app.llm.schemas import CandidateValue, LLMExtractionResult, ResolvedDeclaration, SourceEvidence
from app.llm.evidence_resolver import _llm_has_genuine_product_identity_conflict
from app.rules.rule_engine import evaluate_rules


PRODUCT_NAME_RULE = {
    "rule_id": "PC-ALL-001",
    "parameter": "PRODUCT_NAME",
    "required": True,
    "validation_method": "TEXT_PRESENT",
    "verification_type": "IMAGE_VERIFIABLE",
}


def _extract_panel(image_index, lines):
    raw_text = "\n".join(text for text, _, _ in lines)
    ocr_items = [
        {
            "text": text,
            "confidence": confidence,
            "bbox": bbox,
            "image_index": image_index,
            "token_id": token_id,
        }
        for token_id, (text, confidence, bbox) in enumerate(lines)
    ]
    fields = extract_declarations(raw_text, ocr_items, category="PERSONAL_CARE")
    for candidate in fields.values():
        if isinstance(candidate, dict) and candidate.get("source_image_index") is None:
            candidate["source_image_index"] = image_index
    return fields


def test_original_three_image_sensodyne_fixture_rejects_benefit_tagline():
    back_panel = _extract_panel(0, [
        ("SENSODYNE FRESH MINT TOOTHPASTE:", 0.9464, [19, 6, 220, 27]),
        ("FOAMING FLUORIDATED TOOTHPASTE", 0.9753, [18, 25, 219, 41]),
        ("INGREDIENTS:", 0.9798, [20, 45, 123, 58]),
        ("Aqua, Hydrated Silica, Sorbitol, Potassium Nitrate", 0.7852, [20, 61, 239, 75]),
        ("Net wt.", 0.9444, [686, 189, 745, 204]),
        ("75g", 0.9194, [764, 186, 803, 205]),
    ])
    front_panel = _extract_panel(1, [
        ("DENTIST RECOMMENDED BRAND", 0.9659, [168, 39, 466, 58]),
        ("SENSODYNE", 0.9978, [54, 81, 578, 136]),
        ("Fresh Mint", 0.9564, [776, 80, 965, 114]),
        ("Triple cleaning action", 0.9749, [788, 138, 957, 154]),
        ("Daily Sensitivity Protection+Strong Teeth&Healthy Gums", 0.9726, [70, 157, 561, 177]),
        ("Net wt.", 0.9855, [23, 190, 84, 209]),
        ("75g", 0.9940, [107, 186, 148, 213]),
    ])
    stamp_panel = _extract_panel(2, [
        ("135.00", 0.9755, [51, 62, 244, 117]),
        ("BGM260315", 0.9935, [54, 170, 304, 217]),
        ("05/26:04/28/", 0.9047, [47, 222, 363, 273]),
    ])

    assert front_panel.get("PRODUCT_NAME") is None

    merged = merge_extracted_fields([back_panel, front_panel, stamp_panel])
    product = merged["PRODUCT_NAME"]
    assert product["value"].upper() == "SENSODYNE FRESH MINT TOOTHPASTE"
    assert product["has_conflict"] is False
    assert product["source_image_index"] == 0
    assert product["bbox"] == [19, 6, 220, 27]
    assert "Daily Sensitivity Protection" not in product["value"]
    assert all(
        "Daily Sensitivity Protection" not in str(candidate.get("value"))
        for candidate in product.get("candidates", [])
    )

    results, overall = evaluate_rules([PRODUCT_NAME_RULE], merged)
    assert results[0]["status"] == "PASS"
    assert overall == "COMPLIANT"


def test_same_product_with_different_taglines_has_no_identity_conflict():
    first = _extract_panel(0, [
        ("ACME FRESH MINT TOOTHPASTE", 0.96, [20, 20, 300, 55]),
        ("Daily Sensitivity Protection", 0.94, [20, 70, 290, 90]),
    ])
    second = _extract_panel(1, [
        ("ACME FRESH MINT TOOTHPASTE", 0.95, [18, 18, 298, 52]),
        ("Strong Teeth & Healthy Gums", 0.93, [18, 65, 285, 88]),
    ])

    merged = merge_extracted_fields([first, second])
    product = merged["PRODUCT_NAME"]
    assert product["has_conflict"] is False
    assert product["candidate_classification"] == "CONFIRMED_SAME"
    assert product["value"].upper() == "ACME FRESH MINT TOOTHPASTE"


def test_back_panel_claims_ingredients_and_directions_do_not_become_product_name():
    front = _extract_panel(0, [
        ("NUTRIVA HERBAL TOOTHPASTE", 0.96, [25, 20, 320, 58]),
    ])
    back = _extract_panel(1, [
        ("INGREDIENTS: Sorbitol, Silica, Sodium Fluoride", 0.94, [20, 20, 500, 45]),
        ("Brush twice a day", 0.95, [20, 60, 230, 82]),
        ("Helps protect against cavities", 0.93, [20, 95, 330, 118]),
    ])

    assert back.get("PRODUCT_NAME") is None
    merged = merge_extracted_fields([front, back])
    assert merged["PRODUCT_NAME"]["value"].upper() == "NUTRIVA HERBAL TOOTHPASTE"
    assert merged["PRODUCT_NAME"]["has_conflict"] is False


def test_genuine_product_name_conflict_survives_grounded_gemini_selection():
    deterministic = merge_extracted_fields([
        {"PRODUCT_NAME": {
            "value": "Tata Salt", "confidence": 0.94,
            "source": "OCR_IMAGE_1", "source_image_index": 0,
        }},
        {"PRODUCT_NAME": {
            "value": "Aashirvaad Atta", "confidence": 0.93,
            "source": "OCR_IMAGE_2", "source_image_index": 1,
        }},
    ])
    llm_result = LLMExtractionResult(resolved_declarations=[ResolvedDeclaration(
        field="PRODUCT_NAME",
        value="Tata Salt",
        normalized_value="Tata Salt",
        status="RESOLVED",
        confidence=0.97,
        source_evidence=[SourceEvidence(
            image_index=0,
            token_ids=[0],
            raw_text="Tata Salt",
            bbox=[10, 10, 200, 40],
            ocr_confidence=0.98,
        )],
    )])
    client = MagicMock()
    client.is_enabled.return_value = True
    client.generate_structured_extraction.return_value = (
        llm_result, {"llm_status": "SUCCESS", "model_used": "mock"},
    )

    merged, metadata, _ = resolve_evidence_with_gemini(
        ocr_items=[
            {"text": "Tata Salt", "confidence": 0.98, "bbox": [10, 10, 200, 40], "image_index": 0, "token_id": 0},
            {"text": "Aashirvaad Atta", "confidence": 0.97, "bbox": [10, 10, 240, 40], "image_index": 1, "token_id": 1},
        ],
        raw_text="Tata Salt\nAashirvaad Atta",
        num_images=2,
        deterministic_fields=deterministic,
        client=client,
    )

    product = merged["PRODUCT_NAME"]
    assert product["status"] == "REVIEW"
    assert product["review_required"] is True
    assert set(product["values"]) == {"Tata Salt", "Aashirvaad Atta"}
    assert metadata["grounding_audit"]["fields"]["PRODUCT_NAME"]["grounded"] is True
    assert metadata["identity_resolution_rejections"]

    results, overall = evaluate_rules([PRODUCT_NAME_RULE], merged)
    assert results[0]["status"] == "NOT_VERIFIABLE"
    assert overall == "REVIEW_REQUIRED"


def test_damaged_unsupported_identity_never_passes():
    fields = {
        "PRODUCT_NAME": {
            "value": "SENS0",
            "confidence": 0.35,
            "source": "OCR_IMAGE_1",
            "source_image_index": 0,
            "bbox": [10, 10, 80, 30],
        }
    }
    results, overall = evaluate_rules([PRODUCT_NAME_RULE], fields)
    assert results[0]["status"] == "NOT_VERIFIABLE"
    assert overall == "REVIEW_REQUIRED"


def test_tata_salt_generic_equivalent_and_recycling_candidates_reconcile():
    raw_candidates = [
        ("Salt", "OCR", 0, [20, 20, 100, 45]),
        ("Tata Salt", "OCR_LAYOUT", 1, [30, 30, 220, 70]),
        ("TATA Salt", "OCR_LAYOUT", 2, [35, 35, 225, 75]),
        ("Tata Salt's Recyclablepack", "OCR", 3, [40, 300, 310, 335]),
        ("KEEP otasvlenehaminat is Recycle Sd Salt", "OCR_LAYOUT", 4, [15, 400, 390, 440]),
    ]
    panels = [
        {
            "PRODUCT_NAME": {
                "value": value,
                "raw_text": value,
                "confidence": 0.85,
                "source": source,
                "source_image_index": image_index,
                "bbox": bbox,
            },
            "GENERIC_NAME": {
                "value": "SALT",
                "confidence": 0.85,
                "source": "OCR",
                "source_image_index": image_index,
            },
        }
        for value, source, image_index, bbox in raw_candidates
    ]

    product = merge_extracted_fields(panels)["PRODUCT_NAME"]

    assert product["value"].lower() == "tata salt"
    assert product["status"] == "VALID"
    assert product["has_conflict"] is False
    assert product["candidate_classification"] == "CONFIRMED_SAME"
    assert len(product["candidates"]) == 5
    assert {
        candidate["candidate_role"] for candidate in product["filtered_noise"]
    } == {"GENERIC_NAME_PRODUCT_TYPE", "PACKAGING_RECYCLING_DISPOSAL"}
    assert all(candidate.get("source_image_index") is not None for candidate in product["filtered_noise"])
    assert all(candidate.get("bbox") for candidate in product["filtered_noise"] if candidate["value"] != "Salt")
    assert all(candidate.get("rejection_reason") for candidate in product["filtered_noise"])

    results, overall = evaluate_rules([PRODUCT_NAME_RULE], {"PRODUCT_NAME": product})
    assert results[0]["status"] == "PASS"
    assert overall == "COMPLIANT"


def test_semantic_conflict_requires_two_eligible_product_identities():
    false_conflict = ResolvedDeclaration(
        field="PRODUCT_NAME",
        status="CONFLICT",
        confidence=0.9,
        alternatives=[
            CandidateValue(value="Salt", confidence=0.95),
            CandidateValue(value="Tata Salt", confidence=0.92),
            CandidateValue(value="Tata Salt's Recyclablepack", confidence=0.9),
        ],
    )
    genuine_conflict = ResolvedDeclaration(
        field="PRODUCT_NAME",
        status="CONFLICT",
        confidence=0.9,
        alternatives=[
            CandidateValue(value="Tata Salt", confidence=0.95),
            CandidateValue(value="Aashirvaad Atta", confidence=0.94),
        ],
    )

    assert _llm_has_genuine_product_identity_conflict(false_conflict) is False
    assert _llm_has_genuine_product_identity_conflict(genuine_conflict) is True
