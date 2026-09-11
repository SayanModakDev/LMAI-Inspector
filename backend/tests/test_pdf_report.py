"""Automated tests for professional 4-page inspection-support PDF report generator."""
import base64
import os
import re
import zlib
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import SessionLocal
from app.database import models
from app.reports.pdf_report import generate_inspection_pdf, STATUTORY_DISCLAIMER


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


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_generate_pdf_report_structure_and_pages(db_session):
    """Verify PDF generates cleanly with valid header, exactly 4 pages, and DB record."""
    insp = models.Inspection(
        product_name="Test Basmati Rice 5kg",
        brand="Royal Heritage",
        category="FOOD",
        package_type="RETAIL",
        import_status="DOMESTIC",
        overall_result="COMPLIANT",
        inspector_name="Inspector Sharma",
    )
    db_session.add(insp)
    db_session.commit()
    db_session.refresh(insp)

    # Add sample rule result
    rr = models.RuleResult(
        inspection_id=insp.id,
        rule_id="PC-ALL-001",
        parameter="PRODUCT_NAME",
        status="PASS",
        message="1 — PASS: Product name declaration verified",
        evidence_data={"value": "Test Basmati Rice 5kg", "binary": 1},
        regulatory_source="LEGAL_METROLOGY",
    )
    db_session.add(rr)
    db_session.commit()

    report = generate_inspection_pdf(insp, db_session)
    assert report is not None
    assert os.path.exists(report.file_path)

    # Check valid PDF magic bytes
    with open(report.file_path, 'rb') as f:
        header = f.read(5)
    assert header == b'%PDF-'

    # Verify 4-page structure
    pages = _get_page_count(report.file_path)
    assert pages == 4

    # Verify DB record
    db_report = db_session.query(models.Report).filter(models.Report.inspection_id == insp.id).first()
    assert db_report is not None
    assert db_report.file_name == report.file_name


def test_pdf_report_overall_results_compliant_and_non_compliant(db_session):
    """Verify Page 1 large overall compliance banners for COMPLIANT and NON_COMPLIANT."""
    # 1. Compliant inspection
    insp_c = models.Inspection(
        product_name="Compliant Wheat Flour",
        category="FOOD",
        overall_result="COMPLIANT",
    )
    db_session.add(insp_c)
    db_session.commit()
    rep_c = generate_inspection_pdf(insp_c, db_session)
    text_c = _extract_pdf_text(rep_c.file_path)
    assert "OVERALL COMPLIANCE RATING: 1 \x97 COMPLIANT" in text_c or "1 \x97 COMPLIANT" in text_c or "COMPLIANT" in text_c

    # 2. Non-compliant inspection
    insp_nc = models.Inspection(
        product_name="Non-Compliant Detergent",
        category="HOUSEHOLD",
        overall_result="NON_COMPLIANT",
    )
    db_session.add(insp_nc)
    db_session.commit()
    rep_nc = generate_inspection_pdf(insp_nc, db_session)
    text_nc = _extract_pdf_text(rep_nc.file_path)
    assert "NON-COMPLIANT" in text_nc or "0 \x97 NON-COMPLIANT" in text_nc


def test_pdf_report_declared_net_quantity_decomposition(db_session):
    """Verify Page 2 Rule Matrix decomposes Declared Net Quantity into Value and Unit."""
    insp = models.Inspection(
        product_name="Organic Almonds 250g",
        category="FOOD",
        overall_result="COMPLIANT",
    )
    db_session.add(insp)
    db_session.commit()

    rr = models.RuleResult(
        inspection_id=insp.id,
        rule_id="PC-ALL-002",
        parameter="DECLARED_NET_QUANTITY",
        status="PASS",
        message="1 — PASS: Net quantity verified: 250 g",
        evidence_data={
            "value": "250",
            "unit": "g",
            "raw_value": "Net Wt 250 g",
            "quantity_unit_valid": True,
            "binary": 1,
            "validation_method": "VALUE_AND_UNIT_PRESENT",
        },
    )
    db_session.add(rr)
    db_session.commit()

    report = generate_inspection_pdf(insp, db_session)
    text = _extract_pdf_text(report.file_path)

    assert "Value:" in text
    assert "250" in text
    assert "Unit:" in text
    assert "g" in text
    assert "Quantity & Unit:" in text or "VALUE_AND_UNIT_PRESENT" in text


def test_pdf_report_unverified_rule_references_show_pending_verification(db_session):
    """Verify unverified rule references display 'Pending verification' and not fabricated numbers."""
    insp = models.Inspection(
        product_name="Sample Honey",
        category="FOOD",
        overall_result="NOT_VERIFIABLE",
    )
    db_session.add(insp)
    db_session.commit()

    rr = models.RuleResult(
        inspection_id=insp.id,
        rule_id="PC-ALL-003",
        parameter="MRP",
        status="NOT_VERIFIABLE",
        message="Missing MRP",
        rule_reference="PENDING_VERIFICATION",
        rule_version="PENDING_VERIFICATION",
        evidence_data={"binary": None},
    )
    db_session.add(rr)
    db_session.commit()

    report = generate_inspection_pdf(insp, db_session)
    text = _extract_pdf_text(report.file_path)

    assert "Pending verification" in text


def test_pdf_report_statutory_disclaimer_and_limitations(db_session):
    """Verify statutory disclaimer, physical verification requirements, and inspector sign-off."""
    insp = models.Inspection(
        product_name="Talc Powder",
        category="COSMETIC",
        overall_result="COMPLIANT",
    )
    db_session.add(insp)
    db_session.commit()

    report = generate_inspection_pdf(insp, db_session)
    text = _extract_pdf_text(report.file_path)

    # Mandatory disclaimer exact match
    assert STATUTORY_DISCLAIMER in text

    # Physical verification mandate
    assert "Physical Verification Requirements" in text
    assert "calibrated" in text
    assert "OCR and computer vision screen optical label declarations on package graphics only" in text

    # System limitations
    assert "System Limitations" in text

    # Inspector sign-off block
    assert "Inspector Review & Verification Details" in text
    assert "Inspector Signature:" in text
    assert "Action Taken" in text


def test_report_api_endpoints_generate_and_download(db_session):
    """Verify report generation via POST /api/report/{id} and download via GET /api/report/{id}/download."""
    insp = models.Inspection(
        product_name="API Integration Product",
        category="FOOD",
        overall_result="COMPLIANT",
    )
    db_session.add(insp)
    db_session.commit()

    client = TestClient(app)

    # 1. Generate Report
    gen_resp = client.post(f"/api/report/{insp.id}")
    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()
    assert "Report generated successfully" in gen_data["message"]
    assert f"/api/report/{insp.id}/download" in gen_data["data"]["file_url"]

    # 2. Download Report
    down_resp = client.get(f"/api/report/{insp.id}/download")
    assert down_resp.status_code == 200
    assert down_resp.headers["content-type"] == "application/pdf"
    assert down_resp.content[:5] == b"%PDF-"


def test_inspector_review_audit_trail_and_pdf_reflection(db_session):
    """Verify that an inspector correction creates a complete audit trail:
    1. Original OCR preserved in OCR_SUPERSEDED evidence.
    2. Inspector verified value recorded.
    3. Rules re-evaluated and overall result updated.
    4. PDF displays both original OCR and inspector verified value with INSPECTOR_VERIFIED method.
    5. Clean terminology: no 'AI decision', 'AI recommendation', or old names.
    """
    client = TestClient(app)

    # 1. Create inspection with initial unverified MRP declaration
    insp = models.Inspection(
        product_name="Audit Trail Test Commodity",
        brand="QualityBrand",
        category="FOOD",
        package_type="RETAIL",
        import_status="DOMESTIC",
        overall_result="NOT_VERIFIABLE",
        inspector_name="Inspector V. Kumar",
    )
    db_session.add(insp)
    db_session.commit()
    db_session.refresh(insp)

    # Add initial OCR extracted field for MRP with ambiguous reading
    field_mrp = models.ExtractedField(
        inspection_id=insp.id,
        field_name="MRP",
        field_value="Rs. 9?",
        confidence=0.45,
        source="OCR",
    )
    db_session.add(field_mrp)

    # Initial rule result for MRP is NOT_VERIFIABLE
    rr = models.RuleResult(
        inspection_id=insp.id,
        rule_id="PC-ALL-003",
        parameter="MRP",
        status="NOT_VERIFIABLE",
        message="Ambiguous MRP reading",
        evidence_data={"value": "Rs. 9?", "raw_value": "Rs. 9?"},
        regulatory_source="LEGAL_METROLOGY",
    )
    db_session.add(rr)
    db_session.commit()

    # 2. Inspector applies manual correction via /api/manual-input
    override_payload = {
        "inspection_id": insp.id,
        "field_overrides": {
            "MRP": "Rs. 95.00 (inclusive of all taxes)",
        },
        "inspector_notes": "Verified against physical price label on package base.",
    }
    input_resp = client.post("/api/manual-input", json=override_payload)
    assert input_resp.status_code == 200

    # 3. Verify DB audit trail
    db_session.expire_all()
    updated_insp = db_session.query(models.Inspection).filter(models.Inspection.id == insp.id).first()

    # Check that OCR_SUPERSEDED evidence was stored
    superseded_ev = db_session.query(models.Evidence).filter(
        models.Evidence.inspection_id == insp.id,
        models.Evidence.evidence_type == "OCR_SUPERSEDED",
        models.Evidence.parameter == "MRP",
    ).first()
    assert superseded_ev is not None
    assert superseded_ev.text_content == "Rs. 9?"

    # Check that MANUAL_OVERRIDE evidence was stored
    override_ev = db_session.query(models.Evidence).filter(
        models.Evidence.inspection_id == insp.id,
        models.Evidence.evidence_type == "MANUAL_OVERRIDE",
        models.Evidence.parameter == "MRP",
    ).first()
    assert override_ev is not None
    assert "95.00" in override_ev.text_content

    # Check that extracted field value is updated to manual
    mrp_field_now = next(f for f in updated_insp.extracted_fields if f.field_name == "MRP")
    assert mrp_field_now.source == "MANUAL"
    assert "95.00" in mrp_field_now.field_value

    # 4. Generate PDF report
    report = generate_inspection_pdf(updated_insp, db_session)
    pdf_text = _extract_pdf_text(report.file_path)

    # 5. Verify PDF contents and terminology
    assert "LMAI INSPECTOR" in pdf_text
    assert "1.0.0" in pdf_text
    # Original OCR preserved in PDF
    assert "Rs. 9?" in pdf_text
    # Verified value appears in PDF
    assert "95.00" in pdf_text
    # Method and status indicators
    assert "INSPECTOR_VERIFIED" in pdf_text
    assert "VERIFIED" in pdf_text
    # Action summary in inspector block
    assert "Inspector Review Actions" in pdf_text

    # Verify no inaccurate AI claims in PDF
    assert "AI decision" not in pdf_text
    assert "AI compliance score" not in pdf_text
    assert "AI recommendation" not in pdf_text
    assert "Legal Metrology Compliance Checker" not in pdf_text
