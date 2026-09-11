"""
Final Integration Audit Tests for SIH26034.

Verifies acceptance scenarios TEST A through TEST J end-to-end:
  TEST A — Compliant label (all mandatory declarations present & valid -> COMPLIANT, binaries=1)
  TEST B — Missing quantity unit (quantity 500, unit missing -> FAIL, binary=0, never silent PASS)
  TEST C — Missing required declaration (never disappears, shows clear reason and review/fail state)
  TEST D — Uncertain OCR (low confidence -> NOT_VERIFIABLE, binary=None, never auto PASS/FAIL)
  TEST E — Cosmetic product (no food-only veg/non-veg symbol check, classified as COSMETIC)
  TEST F — Conflicting multi-image evidence (CONFLICTING_EVIDENCE, review required, no silent overwrite)
  TEST G — Date context (manufacturing date never replaced by best before/expiry; labels respected)
  TEST H — Barcode contradiction (supplementary evidence only, contradiction noted, OCR not overwritten)
  TEST I — Invalid upload (disguised non-image rejected with 400 before OCR)
  TEST J — PDF (Rule Matrix, binary results, reasons, evidence, traceability, disclaimer, PENDING_VERIFICATION)
"""

import io
import os
import re
import zlib
import base64
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.extraction.declaration_extractor import extract_declarations, merge_extracted_fields
from app.rules.rule_engine import evaluate_rules, sync_rules_to_db
from app.rules.applicability import get_applicable_rules
from app.classification.category_classifier import classify_category
from app.core.constants import InspectionStatus
from app.reports.pdf_report import generate_inspection_pdf
from app.database import models
from app.database.connection import SessionLocal
from app.api.scan import merge_product_evidence


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# TEST A — Compliant label
# ---------------------------------------------------------------------------
def test_acceptance_test_a_compliant_label(db_session):
    """
    TEST A: Compliant label.
    Valid declared quantity + unit, valid MRP, required declarations detected,
    parameter binaries mostly/all 1, overall COMPLIANT.
    """
    sync_rules_to_db()
    db_rules = db_session.query(models.Rule).filter(models.Rule.is_active == True).all()
    all_rules_dict = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in db_rules]

    # Applicable rules for a domestic retail packaged food commodity
    applicable = get_applicable_rules(
        all_rules=all_rules_dict,
        category="FOOD",
        product_type="PREPACKAGED_FOOD",
        package_type="RETAIL",
        import_status="DOMESTIC",
        has_physical_data=True,  # Providing physical measurement so all rules are verifiable
    )

    extracted_fields = {
        "PRODUCT_NAME": {"value": "Pure Refined Sugar", "confidence": 0.95, "source": "OCR"},
        "GENERIC_NAME": {"value": "Refined Sugar", "confidence": 0.95, "source": "OCR"},
        "NET_QUANTITY": {"value": "500 g", "confidence": 0.96, "source": "OCR"},
        "MRP": {"value": "₹50.00", "confidence": 0.94, "source": "OCR"},
        "MANUFACTURER_NAME": {"value": "Sweet Sugar Mills Pvt. Ltd.", "confidence": 0.93, "source": "OCR"},
        "MANUFACTURER_ADDRESS": {"value": "Plot 12, Industrial Area, Phase II, Pune, Maharashtra 411001", "confidence": 0.95, "source": "OCR"},
        "CONSUMER_CARE": {"value": "Email: care@sweetsugar.com, Ph: 1800-123-4567", "confidence": 0.91, "source": "OCR"},
        "MONTH_YEAR_MANUFACTURE": {"value": "05/2024", "confidence": 0.95, "source": "OCR"},
        "BATCH_NUMBER": {"value": "B-9921", "confidence": 0.90, "source": "OCR"},
        "BEST_BEFORE_USE_BY": {"value": "12 months from date of manufacture", "confidence": 0.95, "source": "OCR"},
        "INGREDIENTS_LIST": {"value": "Cane Sugar", "confidence": 0.93, "source": "OCR"},
        "NUTRITIONAL_INFO": {"value": "Per 100g: Energy 400 kcal, Carbohydrates 99.8g", "confidence": 0.95, "source": "OCR"},
        "FSSAI_LICENSE": {"value": "10014011002345", "confidence": 0.95, "source": "OCR"},
        "VEG_NONVEG_SYMBOL": {"value": "100% Vegetarian", "confidence": 0.95, "source": "OCR"},
        "ACTUAL_NET_CONTENT": {"value": "500 g", "confidence": 1.0, "source": "MANUAL"},
        "FONT_SIZE_COMPLIANCE": {"value": "Pass - 4mm height", "confidence": 1.0, "source": "MANUAL"},
    }

    results, overall = evaluate_rules(applicable, extracted_fields)
    assert overall == InspectionStatus.COMPLIANT
    # Verify mandatory parameters pass with binary 1
    net_qty_res = next(r for r in results if r["parameter"] in ("DECLARED_NET_QUANTITY", "NET_QUANTITY"))
    assert net_qty_res["status"] == "PASS"
    assert net_qty_res["binary"] == 1
    assert net_qty_res["quantity_present"] is True
    assert net_qty_res["unit_present"] is True
    assert net_qty_res["quantity_unit_valid"] is True

    mrp_res = next(r for r in results if r["parameter"] == "MRP")
    assert mrp_res["status"] == "PASS"
    assert mrp_res["binary"] == 1


# ---------------------------------------------------------------------------
# TEST B — Missing quantity unit
# ---------------------------------------------------------------------------
def test_acceptance_test_b_missing_quantity_unit(db_session):
    """
    TEST B: Missing quantity unit.
    Input: Net Quantity 500 (unit omitted)
    Expected:
      quantity present
      unit missing
      quantity+unit validation fails with binary 0
      never silently PASS
    """
    sync_rules_to_db()
    db_rules = db_session.query(models.Rule).filter(models.Rule.is_active == True).all()
    all_rules_dict = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in db_rules]

    applicable = get_applicable_rules(all_rules=all_rules_dict, category="FOOD")

    extracted_fields = {
        "NET_QUANTITY": {"value": "500", "confidence": 0.95, "source": "OCR"},
    }

    results, overall = evaluate_rules(applicable, extracted_fields)
    net_qty_res = next(r for r in results if r["parameter"] in ("DECLARED_NET_QUANTITY", "NET_QUANTITY"))

    assert net_qty_res["status"] == "FAIL"
    assert net_qty_res["binary"] == 0
    assert net_qty_res["quantity_present"] is True
    assert net_qty_res["unit_present"] is False
    assert net_qty_res["quantity_unit_valid"] is False
    assert "unit" in net_qty_res["reason"].lower()
    assert overall == InspectionStatus.NON_COMPLIANT


# ---------------------------------------------------------------------------
# TEST C — Missing required declaration
# ---------------------------------------------------------------------------
def test_acceptance_test_c_missing_required_declaration(db_session):
    """
    TEST C: Missing required declaration.
    Expected:
      Parameter does not silently disappear
      Clear review/fail interpretation
      Reason shown
    """
    sync_rules_to_db()
    db_rules = db_session.query(models.Rule).filter(models.Rule.is_active == True).all()
    all_rules_dict = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in db_rules]

    applicable = get_applicable_rules(all_rules=all_rules_dict, category="FOOD")

    # Supply only product name and net quantity; omit MRP, manufacturer, etc.
    extracted_fields = {
        "PRODUCT_NAME": {"value": "Wheat Flour", "confidence": 0.92, "source": "OCR"},
        "NET_QUANTITY": {"value": "1 kg", "confidence": 0.95, "source": "OCR"},
    }

    results, overall = evaluate_rules(applicable, extracted_fields)

    mrp_res = next((r for r in results if r["parameter"] == "MRP"), None)
    assert mrp_res is not None, "MRP rule must not disappear from results"
    assert mrp_res["status"] == "NOT_VERIFIABLE"
    assert mrp_res["binary"] in (0, None)
    assert mrp_res["review_required"] is True
    assert "missing" in mrp_res["reason"].lower() or "not detected" in mrp_res["reason"].lower()

    mfg_res = next((r for r in results if r["parameter"] == "MANUFACTURER_NAME"), None)
    assert mfg_res is not None
    assert mfg_res["status"] == "NOT_VERIFIABLE"
    assert overall == InspectionStatus.NOT_VERIFIABLE


# ---------------------------------------------------------------------------
# TEST D — Uncertain OCR
# ---------------------------------------------------------------------------
def test_acceptance_test_d_uncertain_ocr(db_session):
    """
    TEST D: Uncertain OCR.
    Expected:
      Low confidence OCR is evaluated as NOT_VERIFIABLE / REVIEW
      Never automatically legal FAIL
      Never automatically PASS
    """
    sync_rules_to_db()
    db_rules = db_session.query(models.Rule).filter(models.Rule.is_active == True).all()
    all_rules_dict = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in db_rules]

    applicable = get_applicable_rules(all_rules=all_rules_dict, category="FOOD")

    extracted_fields = {
        # Confidence below usable threshold (0.60)
        "MRP": {"value": "₹120.00", "confidence": 0.42, "source": "OCR"},
    }

    results, overall = evaluate_rules(applicable, extracted_fields)
    mrp_res = next(r for r in results if r["parameter"] == "MRP")

    assert mrp_res["status"] == "NOT_VERIFIABLE"
    assert mrp_res["binary"] in (0, None)
    assert mrp_res["review_required"] is True
    assert "confidence" in mrp_res["reason"].lower()
    assert overall != InspectionStatus.COMPLIANT


# ---------------------------------------------------------------------------
# TEST E — Cosmetic product
# ---------------------------------------------------------------------------
def test_acceptance_test_e_cosmetic_product(db_session):
    """
    TEST E: Cosmetic product.
    Expected:
      No food-only symbol compliance check
      Correct COSMETIC classification
      No VEG_NONVEG compliance result
    """
    text = "Glow Derm Talcum Powder. Net Wt: 100g. Mfg by: ABC Cosmetics Ltd. For external use only. Use Before: 12/2026."
    res = classify_category(text)
    assert res["category"] == "COSMETIC"

    sync_rules_to_db()
    db_rules = db_session.query(models.Rule).filter(models.Rule.is_active == True).all()
    all_rules_dict = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in db_rules]

    applicable = get_applicable_rules(all_rules=all_rules_dict, category="COSMETIC")

    parameters = [r.get("parameter") for r in applicable]
    assert "VEG_NONVEG_SYMBOL" not in parameters, "VEG_NONVEG_SYMBOL must never apply to cosmetics"
    assert "FSSAI_LICENSE" not in parameters, "FSSAI license must never apply to cosmetics"


# ---------------------------------------------------------------------------
# TEST F — Conflicting multi-image evidence
# ---------------------------------------------------------------------------
def test_acceptance_test_f_conflicting_multi_image_evidence(db_session):
    """
    TEST F: Conflicting multi-image evidence.
    Image 1: MRP = ₹120, confidence 0.82
    Image 2: MRP = ₹140, confidence 0.81
    Expected:
      CONFLICTING_EVIDENCE
      review required
      no silent overwrite
    """
    image_extractions = [
        {"MRP": {"value": "₹120.00", "confidence": 0.82, "source": "OCR", "image_index": 0, "file_name": "front.jpg"}},
        {"MRP": {"value": "₹140.00", "confidence": 0.81, "source": "OCR", "image_index": 1, "file_name": "back.jpg"}},
    ]

    merged = merge_extracted_fields(image_extractions)
    mrp_merged = merged.get("MRP")

    assert mrp_merged is not None
    assert mrp_merged.get("status") == "CONFLICTING_EVIDENCE"
    assert mrp_merged.get("has_conflict") is True
    assert len(mrp_merged.get("values", [])) == 2
    assert "₹120.00" in mrp_merged["values"]
    assert "₹140.00" in mrp_merged["values"]

    # In rule engine evaluation:
    sync_rules_to_db()
    db_rules = db_session.query(models.Rule).filter(models.Rule.is_active == True).all()
    all_rules_dict = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in db_rules]
    applicable = get_applicable_rules(all_rules=all_rules_dict, category="FOOD")

    results, overall = evaluate_rules(applicable, merged)
    mrp_rule = next(r for r in results if r["parameter"] == "MRP")
    assert mrp_rule["status"] == "NOT_VERIFIABLE"
    assert mrp_rule["review_required"] is True
    assert "conflict" in mrp_rule["reason"].lower()


# ---------------------------------------------------------------------------
# TEST G — Date context
# ---------------------------------------------------------------------------
def test_acceptance_test_g_date_context():
    """
    TEST G: Date context.
    Expected:
      Manufacturing/packing date cannot be replaced by Best Before / Use By / Expiry date.
      Manufactured by: company name never treated as date.
    """
    text = (
        "Manufactured by: Hindustan Foodworks Private Limited, Plot 44\n"
        "MFD: 04/2024\n"
        "BEST BEFORE: 04/2025\n"
        "Net Wt: 200g"
    )

    extracted = extract_declarations(text)
    mfg_date = extracted.get("MONTH_YEAR_MANUFACTURE") or extracted.get("MANUFACTURE_DATE")
    best_before = extracted.get("BEST_BEFORE_USE_BY")

    assert mfg_date is not None
    assert "04/2024" in mfg_date["value"]
    assert best_before is not None
    assert "04/2025" in best_before["value"]
    assert mfg_date["value"] != best_before["value"]

    # Confirm company name was not captured as date
    assert "Hindustan" not in mfg_date["value"]
    assert "Foodworks" not in mfg_date["value"]


# ---------------------------------------------------------------------------
# TEST H — Barcode contradiction
# ---------------------------------------------------------------------------
def test_acceptance_test_h_barcode_contradiction():
    """
    TEST H: Barcode contradiction.
    Expected:
      Barcode remains supplementary evidence.
      Contradiction is recorded.
      OCR product identity is not silently overwritten.
    """
    ocr_fields = {
        "PRODUCT_NAME": {"value": "Amul Butter 500g", "confidence": 0.94, "source": "OCR"},
        "GENERIC_NAME": {"value": "Pasteurised Butter", "confidence": 0.90, "source": "OCR"},
    }

    barcode_result = {
        "value": "8901262010014",
        "confidence": 1.0,
        "lookup": {
            "status": "FOUND",
            "product_name": "Britannia Cheese Slices",
            "brands": "Britannia",
        }
    }

    merged = merge_product_evidence(ocr_fields, "", [], barcode_result)
    pname = merged.get("PRODUCT_NAME", {})

    # OCR is NOT overwritten
    assert pname.get("ocr_value") == "Amul Butter 500g"
    assert pname.get("barcode_value") == "Britannia Cheese Slices"
    assert pname.get("status") == "CONFLICTING_EVIDENCE"
    assert pname.get("has_conflict") is True
    assert pname.get("barcode_match") == "CONFLICTS"

    rule = {"rule_id": "PC-ALL-001", "parameter": "PRODUCT_NAME", "required": True, "validation_method": "TEXT_PRESENT"}
    results, _ = evaluate_rules([rule], merged)
    assert results[0]["status"] == "NOT_VERIFIABLE"
    assert results[0]["review_required"] is True


# ---------------------------------------------------------------------------
# TEST I — Invalid upload
# ---------------------------------------------------------------------------
def test_acceptance_test_i_invalid_upload(client):
    """
    TEST I: Invalid upload.
    Expected:
      Non-image file disguised with .jpg extension is rejected before OCR (HTTP 400).
    """
    fake_jpeg = b"<html><body><h1>This is definitely not an image</h1></body></html>"
    files = [("files", ("malicious.jpg", fake_jpeg, "image/jpeg"))]

    response = client.post("/api/scan", files=files)
    assert response.status_code == 400
    assert "not a valid image" in response.json().get("detail", "").lower()


def _extract_pdf_text(file_path: str) -> str:
    """Decompress and decode all text streams from a ReportLab PDF."""
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
    """Count page objects in PDF."""
    with open(file_path, 'rb') as f:
        content = f.read().decode('latin1', errors='ignore')
    return len(re.findall(r'/Type\s*/Page\b', content))


# ---------------------------------------------------------------------------
# TEST J — PDF report content & structure
# ---------------------------------------------------------------------------
def test_acceptance_test_j_pdf_report(db_session):
    """
    TEST J: PDF report.
    Expected:
      4-page PDF with Rule Matrix, binary results, reasons, evidence,
      traceability, limitations, legal disclaimer, and no invented citations (PENDING_VERIFICATION).
    """
    sync_rules_to_db()

    # Create dummy inspection with rule results in DB
    inspection = models.Inspection(
        product_name="Sample Audit Product",
        category="FOOD",
        overall_result="NON_COMPLIANT",
        package_type="RETAIL",
        import_status="DOMESTIC",
    )
    db_session.add(inspection)
    db_session.flush()

    rule_res = models.RuleResult(
        inspection_id=inspection.id,
        rule_id="PC-ALL-002",
        parameter="NET_QUANTITY",
        status="FAIL",
        message="Declared quantity present (500) but standard measurement unit is missing.",
        rule_reference="PENDING_VERIFICATION",
        regulatory_source="LEGAL_METROLOGY",
        evidence_data={
            "binary": 0,
            "reason": "Declared quantity present (500) but standard measurement unit is missing.",
            "raw_value": "Net Wt: 500",
            "value": 500.0,
            "unit": None,
            "quantity_present": True,
            "unit_present": False,
            "quantity_unit_valid": False,
        }
    )
    db_session.add(rule_res)
    db_session.commit()

    report = generate_inspection_pdf(inspection, db_session)
    assert report is not None
    assert report.file_path is not None
    assert os.path.exists(report.file_path)

    page_count = _get_page_count(report.file_path)
    assert page_count == 4, f"Expected exactly 4 pages, got {page_count}"

    full_text = _extract_pdf_text(report.file_path)

    # Check key sections & contents
    assert "LMAI INSPECTOR" in full_text
    assert "COMPLIANCE RULE MATRIX" in full_text
    assert "INSPECTION EVIDENCE & PANEL IMAGES" in full_text
    assert "REGULATORY TRACEABILITY & STATUTORY SIGN-OFF" in full_text
    assert "disclaimer" in full_text.lower()
    assert "pending verification" in full_text.lower()
    assert "500" in full_text
    assert "NON-COMPLIANT" in full_text


def test_acceptance_test_k_health_endpoint_and_branding():
    """Verify health endpoint branding, version, and non-AI disclaimer."""
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "running"
    assert data["app"] == "LMAI Inspector"
    assert data["version"] == "1.0.0"
    assert "LMAI Inspector is an automated Legal Metrology inspection-support system" in data["disclaimer"]
    assert "deterministic rule evaluation" in data["disclaimer"]
    assert "AI-assisted" not in data["disclaimer"]
    assert "Legal Metrology Compliance Checker" not in str(data)
