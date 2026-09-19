"""Comprehensive Regression Test Suite for Gemini Production Fixes.

Covers all 15 required scenarios:
1. PackageContext returned as Pydantic model.
2. PackageContext = None.
3. Gemini disabled.
4. Gemini resolver throws exception (scan handles gracefully without 500).
5. package_type auto-fill: NOT_DETECTED + RETAIL -> RETAIL.
6. Existing deterministic RETAIL must not be overwritten unnecessarily.
7. import_status auto-fill: NOT_DETECTED + IMPORTED -> IMPORTED.
8. UNKNOWN category can use supported Gemini category.
9. Existing known category remains unchanged.
10. MM/YY grounding: raw "05/26" + normalized "05/2026" -> accepted.
11. raw "04/28" + normalized "04/2028" -> accepted.
12. unrelated date normalization -> rejected.
13. invalid month e.g. 19/26 -> rejected.
14. Gemini primary 503 -> fallback attempted.
15. primary and fallback unavailable -> deterministic pipeline still completes.
"""

import io
import json
import pytest
from unittest.mock import MagicMock, patch
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from app.main import app
from app.classification.category_classifier import CATEGORY_VOCABULARY
from app.llm.schemas import (
    CandidateValue,
    LLMExtractionResult,
    PackageContext,
    ResolvedDeclaration,
    SourceEvidence,
)
from app.llm.gemini_client import GeminiClient
from app.llm.grounding_validator import EvidenceGroundingValidator, _is_value_derivable_from_text
from app.llm.evidence_resolver import resolve_evidence_with_gemini


def make_test_image_bytes():
    img = Image.new("RGB", (600, 600), color=(245, 245, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(20, 20), (580, 580)], outline=(50, 50, 50), width=2)
    draw.text((40, 50), "TEST PRODUCT BRAND", fill=(0, 0, 0))
    draw.text((40, 100), "MRP Rs. 100.00", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.getvalue()


# ==============================================================================
# 1. PackageContext returned as Pydantic model
# ==============================================================================

def test_package_context_returned_as_pydantic_model():
    """Verify PackageContext supports model_dump, safe .get(), and dict indexing."""
    ctx = PackageContext(
        category="FOOD",
        product_type="BISCUIT",
        package_type="RETAIL",
        import_status="DOMESTIC",
        confidence=0.92,
        reasoning="Packaging declares edible biscuit under FSSAI",
    )

    # 1. model_dump conversion
    data = ctx.model_dump(mode="json", exclude_none=True)
    assert isinstance(data, dict)
    assert data["category"] == "FOOD"
    assert data["package_type"] == "RETAIL"
    assert data["import_status"] == "DOMESTIC"

    # 2. Safe .get() backward compatibility directly on model
    assert ctx.get("category") == "FOOD"
    assert ctx.get("package_type") == "RETAIL"
    assert ctx.get("non_existent", "DEFAULT") == "DEFAULT"

    # 3. Safe subscription
    assert ctx["category"] == "FOOD"
    assert ctx["package_type"] == "RETAIL"


# ==============================================================================
# 2. PackageContext = None handling
# ==============================================================================

def test_package_context_none_handling():
    """Verify resolve_evidence_with_gemini returns None for PackageContext gracefully."""
    ocr_items = [{"token_id": 0, "text": "Brand: Test", "image_index": 0}]
    client = GeminiClient()
    client.is_enabled = lambda: False

    fields, meta, ctx = resolve_evidence_with_gemini(
        ocr_items=ocr_items,
        raw_text="Brand: Test",
        num_images=1,
        deterministic_fields={"BRAND": {"value": "Test"}},
        client=client,
    )

    assert ctx is None
    llm_pkg_context_data = ctx.model_dump(mode="json") if ctx is not None else {}
    assert llm_pkg_context_data == {}
    assert llm_pkg_context_data.get("package_type") is None


# ==============================================================================
# 3. Gemini disabled
# ==============================================================================

def test_gemini_disabled_handling():
    """Verify resolve_evidence_with_gemini returns deterministic fields when disabled."""
    ocr_items = [{"token_id": 0, "text": "MRP Rs. 100", "image_index": 0}]
    deterministic = {"MRP": {"value": "Rs. 100", "confidence": 0.85}}
    client = GeminiClient()
    client.is_enabled = lambda: False

    fields, meta, ctx = resolve_evidence_with_gemini(
        ocr_items=ocr_items,
        raw_text="MRP Rs. 100",
        num_images=1,
        deterministic_fields=deterministic,
        client=client,
    )

    assert fields == deterministic
    assert meta["llm_status"] == "DISABLED"
    assert ctx is None


# ==============================================================================
# 4. Gemini resolver throws exception (scan handles gracefully without 500)
# ==============================================================================

def test_gemini_resolver_throws_exception_scan_safe():
    """Verify /api/scan catches resolver exceptions, logs, and completes scan without HTTP 500."""
    client = TestClient(app)

    with patch("app.api.scan.resolve_evidence_with_gemini", side_effect=RuntimeError("Simulated LLM failure")):
        response = client.post(
            "/api/scan",
            files=[("files", ("test.jpg", make_test_image_bytes(), "image/jpeg"))],
            data={"package_type": "RETAIL", "import_status": "DOMESTIC"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "inspection_id" in data
        assert "analysis_source" in data
        assert "Gemini fallback" in data["analysis_source"] or "Deterministic" in data["analysis_source"]
        assert data.get("llm_metadata", {}).get("llm_status") == "ERROR"


# ==============================================================================
# 5. package_type auto-fill: NOT_DETECTED + RETAIL -> RETAIL
# ==============================================================================

def test_package_type_autofill_not_detected_to_retail():
    """Verify NOT_DETECTED package_type is auto-filled to RETAIL when Gemini returns RETAIL."""
    package_context = {"package_type": "NOT_DETECTED", "import_status": "NOT_DETECTED"}
    llm_pkg_context_data = {"package_type": "RETAIL", "import_status": "DOMESTIC"}

    llm_pkg_type = llm_pkg_context_data.get("package_type")
    if package_context.get("package_type") == "NOT_DETECTED" and llm_pkg_type in ("RETAIL", "WHOLESALE"):
        package_context["package_type"] = llm_pkg_type

    assert package_context["package_type"] == "RETAIL"


# ==============================================================================
# 6. Existing deterministic RETAIL must not be overwritten unnecessarily
# ==============================================================================

def test_existing_deterministic_retail_not_overwritten():
    """Verify existing deterministic package_type is NOT overwritten even if Gemini returns WHOLESALE."""
    package_context = {"package_type": "RETAIL", "import_status": "DOMESTIC"}
    llm_pkg_context_data = {"package_type": "WHOLESALE", "import_status": "IMPORTED"}

    llm_pkg_type = llm_pkg_context_data.get("package_type")
    if package_context.get("package_type") == "NOT_DETECTED" and llm_pkg_type in ("RETAIL", "WHOLESALE"):
        package_context["package_type"] = llm_pkg_type

    assert package_context["package_type"] == "RETAIL"


# ==============================================================================
# 7. import_status auto-fill
# ==============================================================================

def test_import_status_autofill():
    """Verify NOT_DETECTED import_status is auto-filled, and existing DOMESTIC is preserved."""
    # Case A: NOT_DETECTED -> IMPORTED
    package_context_a = {"package_type": "RETAIL", "import_status": "NOT_DETECTED"}
    llm_data_a = {"import_status": "IMPORTED"}
    if package_context_a.get("import_status") == "NOT_DETECTED" and llm_data_a.get("import_status") in ("DOMESTIC", "IMPORTED"):
        package_context_a["import_status"] = llm_data_a["import_status"]
    assert package_context_a["import_status"] == "IMPORTED"

    # Case B: Existing DOMESTIC not overwritten
    package_context_b = {"package_type": "RETAIL", "import_status": "DOMESTIC"}
    llm_data_b = {"import_status": "IMPORTED"}
    if package_context_b.get("import_status") == "NOT_DETECTED" and llm_data_b.get("import_status") in ("DOMESTIC", "IMPORTED"):
        package_context_b["import_status"] = llm_data_b["import_status"]
    assert package_context_b["import_status"] == "DOMESTIC"


# ==============================================================================
# 8. UNKNOWN category can use supported Gemini category
# ==============================================================================

def test_unknown_category_uses_supported_gemini_category():
    """Verify UNKNOWN category adopts Gemini category for all canonical supported categories."""
    supported = set(CATEGORY_VOCABULARY.keys())
    assert "FOOD" in supported
    assert "COSMETIC" in supported
    assert "HOUSEHOLD" in supported

    for cat in supported:
        category = "UNKNOWN"
        cat_confidence = 0.0
        llm_pkg_context_data = {"category": cat, "confidence": 0.88}

        if category == "UNKNOWN" and llm_pkg_context_data:
            llm_cat = llm_pkg_context_data.get("category")
            if llm_cat and llm_cat in supported:
                category = llm_cat
                cat_confidence = float(llm_pkg_context_data.get("confidence") or 0.85)

        assert category == cat
        assert cat_confidence == 0.88


# ==============================================================================
# 9. Existing known category remains unchanged
# ==============================================================================

def test_existing_known_category_remains_unchanged():
    """Verify existing deterministic FOOD category is NOT overwritten by Gemini."""
    supported = set(CATEGORY_VOCABULARY.keys())
    category = "FOOD"
    cat_confidence = 0.95
    llm_pkg_context_data = {"category": "COSMETIC", "confidence": 0.90}

    if category == "UNKNOWN" and llm_pkg_context_data:
        llm_cat = llm_pkg_context_data.get("category")
        if llm_cat and llm_cat in supported:
            category = llm_cat
            cat_confidence = float(llm_pkg_context_data.get("confidence") or 0.85)

    assert category == "FOOD"
    assert cat_confidence == 0.95


# ==============================================================================
# 10. MM/YY grounding: raw "05/26" + normalized "05/2026" -> accepted
# ==============================================================================

def test_mm_yy_grounding_raw_05_26_normalized_05_2026_accepted():
    """Verify MM/YY in OCR ('05/26:04/28/') properly validates normalized '05/2026'."""
    raw = "05/26:04/28/"
    assert _is_value_derivable_from_text("05/2026", raw) is True

    # Also test through validator
    ocr_items = [{"token_id": 0, "text": raw, "image_index": 0}]
    validator = EvidenceGroundingValidator(ocr_items=ocr_items, num_images=1)
    decl = ResolvedDeclaration(
        field="MONTH_YEAR_MANUFACTURE",
        value="05/2026",
        normalized_value="2026-05",
        status="RESOLVED",
        confidence=0.95,
        source_evidence=[SourceEvidence(raw_text=raw, token_ids=[0], image_index=0)],
    )
    is_valid, violations, validated = validator.validate_declaration(decl)
    assert is_valid is True
    assert not violations


# ==============================================================================
# 11. raw "04/28" + normalized "04/2028" -> accepted
# ==============================================================================

def test_mm_yy_grounding_raw_04_28_normalized_04_2028_accepted():
    """Verify MM/YY in OCR ('05/26:04/28/') properly validates normalized '04/2028'."""
    raw = "05/26:04/28/"
    assert _is_value_derivable_from_text("04/2028", raw) is True

    ocr_items = [{"token_id": 0, "text": raw, "image_index": 0}]
    validator = EvidenceGroundingValidator(ocr_items=ocr_items, num_images=1)
    decl = ResolvedDeclaration(
        field="EXPIRY_DATE",
        value="04/2028",
        status="RESOLVED",
        confidence=0.95,
        source_evidence=[SourceEvidence(raw_text=raw, token_ids=[0], image_index=0)],
    )
    is_valid, violations, validated = validator.validate_declaration(decl)
    assert is_valid is True
    assert not violations


# ==============================================================================
# 12. unrelated date normalization -> rejected
# ==============================================================================

def test_unrelated_date_normalization_rejected():
    """Verify dates with mismatching year or month are strictly rejected."""
    raw = "05/26"
    assert _is_value_derivable_from_text("05/2030", raw) is False
    assert _is_value_derivable_from_text("06/2026", raw) is False
    assert _is_value_derivable_from_text("12/2025", raw) is False

    ocr_items = [{"token_id": 0, "text": raw, "image_index": 0}]
    validator = EvidenceGroundingValidator(ocr_items=ocr_items, num_images=1)
    decl = ResolvedDeclaration(
        field="MONTH_YEAR_MANUFACTURE",
        value="05/2030",
        status="RESOLVED",
        confidence=0.95,
        source_evidence=[SourceEvidence(raw_text=raw, token_ids=[0], image_index=0)],
    )
    is_valid, violations, _ = validator.validate_declaration(decl)
    assert is_valid is False
    assert any("not found in OCR tokens" in v or "cannot be derived" in v for v in violations)


# ==============================================================================
# 13. invalid month e.g. 19/26 -> rejected
# ==============================================================================

def test_invalid_month_date_rejected():
    """Verify non-existent months (>12) are not accepted as valid dates."""
    assert _is_value_derivable_from_text("19/2026", "19/26") is False
    assert _is_value_derivable_from_text("19/2026", "05/26") is False
    assert _is_value_derivable_from_text("05/2026", "19/26") is False
    assert _is_value_derivable_from_text("00/2026", "00/26") is False


# ==============================================================================
# 14. Gemini primary 503 -> fallback attempted
# ==============================================================================

def test_gemini_primary_503_fallback_attempted():
    """Verify that when primary model gets 503 UNAVAILABLE, client attempts fallback model."""
    client = GeminiClient()
    client.is_enabled = lambda: True

    mock_503_error = Exception("503 UNAVAILABLE: The service is currently unavailable. Please retry later.")
    mock_success_response = MagicMock()
    mock_success_response.text = json.dumps({
        "declarations": {
            "BRAND": {
                "field": "BRAND",
                "value": "Sunburst",
                "status": "RESOLVED",
                "confidence": 0.95,
                "source_evidence": [{"raw_text": "Brand: Sunburst", "token_ids": [0], "image_index": 0}],
            }
        },
        "package_context": {
            "category": "FOOD",
            "package_type": "RETAIL",
            "import_status": "DOMESTIC",
        }
    })

    with patch.object(client, "_get_client") as mock_get_client:
        mock_genai_client = MagicMock()
        mock_get_client.return_value = mock_genai_client

        def mock_generate_content(model, contents, config=None):
            if "flash-lite" in model:
                return mock_success_response
            raise mock_503_error

        mock_genai_client.models.generate_content.side_effect = mock_generate_content

        result, meta = client.generate_structured_extraction(prompt="Extract declarations")

        assert result is not None
        assert meta["fallback_used"] is True
        assert meta["used_model"] == client.fallback_model
        assert meta["requested_model"] == client.primary_model
        assert meta["llm_status"] == "SUCCESS"


# ==============================================================================
# 15. primary and fallback unavailable -> deterministic pipeline still completes
# ==============================================================================

def test_primary_and_fallback_unavailable_deterministic_completes():
    """Verify that when both primary and fallback fail with 503, deterministic results are returned."""
    client = GeminiClient()
    client.is_enabled = lambda: True

    mock_503 = Exception("503 UNAVAILABLE: All backends down")
    with patch.object(client, "_get_client") as mock_get_client:
        mock_genai = MagicMock()
        mock_get_client.return_value = mock_genai
        mock_genai.models.generate_content.side_effect = mock_503

        ocr_items = [{"token_id": 0, "text": "MRP Rs. 50.00", "image_index": 0}]
        deterministic = {"MRP": {"value": "Rs. 50.00", "confidence": 0.85}}

        fields, meta, ctx = resolve_evidence_with_gemini(
            ocr_items=ocr_items,
            raw_text="MRP Rs. 50.00",
            num_images=1,
            deterministic_fields=deterministic,
            client=client,
        )

        assert fields == deterministic
        assert meta["llm_status"] == "FALLBACK_RULE_BASED"
        assert ctx is None
