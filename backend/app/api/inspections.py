"""Inspection history, detail, dashboard, and report endpoints.

The database rows are the audit source of truth.  Presentation code normalizes
legacy status spellings but never promotes unresolved evidence to a pass.
"""

from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.constants import InspectionStatus, normalize_status
from app.database import models, schemas
from app.database.connection import get_db
from app.reports.pdf_report import generate_inspection_pdf
from app.rules.rule_engine import (
    _is_physical_verification_rule,
    calculate_rule_summary,
    derive_screening_result,
)


router = APIRouter()


def get_canonical_screening_status(inspection: Any) -> str:
    """Return the canonical automated-screening result for one inspection."""
    rule_results = list(getattr(inspection, "rule_results", None) or [])
    if rule_results:
        return str(derive_screening_result(rule_results))
    return str(normalize_status(getattr(inspection, "overall_result", None)) or InspectionStatus.REVIEW_REQUIRED)


def _report_payload(report: Optional[models.Report]) -> Optional[Dict[str, Any]]:
    if report is None:
        return None
    return {
        "id": report.id,
        "file_name": report.file_name,
        "file_path": report.file_path,
        "file_url": f"/reports/{Path(report.file_name).name}",
        "generated_at": report.generated_at,
    }


def _image_payload(image: models.InspectionImage) -> Dict[str, Any]:
    return {
        "id": image.id,
        "image_index": image.image_index,
        "file_name": image.file_name,
        "processed_file_name": image.processed_file_name,
        "source": image.source,
        "image_url": f"/uploads/{Path(image.file_name).name}",
        "processed_image_url": (
            f"/uploads/{Path(image.processed_file_name).name}"
            if image.processed_file_name else None
        ),
        "created_at": image.created_at,
    }


def _rule_payload(result: models.RuleResult) -> Dict[str, Any]:
    evidence = dict(result.evidence_data or {})
    payload = {
        "id": result.id,
        "rule_id": result.rule_id,
        "parameter": result.parameter,
        "status": result.status,
        "message": result.message,
        "evidence_data": evidence,
        "rule_version": result.rule_version,
        "regulatory_source": result.regulatory_source,
        "rule_reference": result.rule_reference,
        "rule_reference_status": result.rule_reference_status,
        "citation": result.citation,
        "verification_status": result.verification_status,
        "review_required": bool(result.review_required),
    }
    # Preserve the established flat response contract used by the workstation.
    for key in (
        "binary", "value", "unit", "raw_value", "quantity_present",
        "unit_present", "quantity_unit_valid", "verification_type",
        "screening_scope", "reason", "bbox", "source_image_index",
        "candidate_status", "visual_confirmation", "detector_version",
        "evidence_crop_file", "evidence_crop_url", "evidence_crop_sha256",
        "aggregation_trace", "candidates",
    ):
        if key in evidence:
            payload[key] = evidence[key]
    return payload


def _field_payload(
    field: models.ExtractedField,
    rule_by_parameter: Dict[str, models.RuleResult],
) -> Dict[str, Any]:
    payload = {
        "id": field.id,
        "field_name": field.field_name,
        "field_value": field.field_value,
        "value": field.field_value,
        "confidence": field.confidence,
        "source": field.source,
        "extraction_method": field.extraction_method,
        "bbox": field.bbox,
        "source_image_id": field.source_image_id,
    }
    # The compact ExtractedField table cannot hold the full visual audit.  The
    # canonical RuleResult does, so reattach it for historical detail views.
    rule = rule_by_parameter.get(field.field_name)
    if rule and isinstance(rule.evidence_data, dict):
        for key, value in rule.evidence_data.items():
            if key not in payload or payload[key] is None:
                payload[key] = value
    return payload


def _summary_item(inspection: models.Inspection) -> schemas.InspectionSummary:
    screening = get_canonical_screening_status(inspection)
    return schemas.InspectionSummary(
        id=inspection.id,
        inspection_date=inspection.inspection_date,
        product_name=inspection.product_name,
        category=inspection.category,
        package_type=inspection.package_type or "NOT_DETECTED",
        import_status=inspection.import_status or "NOT_DETECTED",
        overall_result=screening,
        screening_result=screening,
        priority=inspection.priority or "MEDIUM",
        inspector_name=inspection.inspector_name,
        created_at=inspection.created_at,
        report=_report_payload(inspection.report),
    )


@router.get("/history", response_model=List[schemas.InspectionSummary])
def get_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    # FastAPI replaces these defaults for HTTP calls; direct service-level
    # callers (including maintenance scripts) receive the Query descriptors.
    skip = skip if isinstance(skip, int) else int(skip.default)
    limit = limit if isinstance(limit, int) else int(limit.default)
    inspections = db.query(models.Inspection).order_by(
        models.Inspection.created_at.desc(), models.Inspection.id.desc()
    ).all()
    wanted_status = normalize_status(status) if status else None
    wanted_category = category.strip().upper() if category else None
    filtered = [
        inspection for inspection in inspections
        if (not wanted_status or get_canonical_screening_status(inspection) == wanted_status)
        and (not wanted_category or (inspection.category or "").upper() == wanted_category)
    ]
    return [_summary_item(item) for item in filtered[skip:skip + limit]]


@router.get("/dashboard", response_model=schemas.DashboardStats)
def get_dashboard(db: Session = Depends(get_db)):
    inspections = db.query(models.Inspection).order_by(
        models.Inspection.created_at.desc(), models.Inspection.id.desc()
    ).all()
    statuses = [get_canonical_screening_status(item) for item in inspections]
    failed_parameters = Counter(
        row.parameter
        for item in inspections
        for row in (item.rule_results or [])
        if str(row.status).upper().replace("-", "_") == "FAIL"
        and not _is_physical_verification_rule(row)
    )
    recent = []
    for item in inspections[:5]:
        status = get_canonical_screening_status(item)
        recent.append({
            "id": item.id,
            "inspection_date": item.inspection_date,
            "product_name": item.product_name,
            "category": item.category,
            "package_type": item.package_type or "NOT_DETECTED",
            "import_status": item.import_status or "NOT_DETECTED",
            "result": status,
            "overall_result": status,
            "priority": item.priority or "MEDIUM",
            "report": _report_payload(item.report),
        })
    return schemas.DashboardStats(
        total_inspections=len(inspections),
        compliant=sum(value == InspectionStatus.COMPLIANT for value in statuses),
        non_compliant=sum(value == InspectionStatus.NON_COMPLIANT for value in statuses),
        review_required=sum(value == InspectionStatus.REVIEW_REQUIRED for value in statuses),
        not_verifiable=sum(value == InspectionStatus.REVIEW_REQUIRED for value in statuses),
        not_applicable=sum(value == InspectionStatus.NOT_APPLICABLE for value in statuses),
        food_inspections=sum((item.category or "").upper() == "FOOD" for item in inspections),
        cosmetic_inspections=sum((item.category or "").upper() == "COSMETIC" for item in inspections),
        recent_inspections=recent,
        common_failed_parameters=[
            {"parameter": parameter, "count": count}
            for parameter, count in failed_parameters.most_common(10)
        ],
    )


@router.get("/inspection/{inspection_id}", response_model=schemas.InspectionDetail)
def get_inspection_detail(inspection_id: int, db: Session = Depends(get_db)):
    inspection = db.query(models.Inspection).filter(models.Inspection.id == inspection_id).first()
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")

    rules = list(inspection.rule_results or [])
    rule_by_parameter = {row.parameter: row for row in rules}
    screening = get_canonical_screening_status(inspection)
    product = inspection.product
    product_payload = None
    if product is not None:
        product_payload = {
            column.name: getattr(product, column.name)
            for column in models.Product.__table__.columns
            if column.name not in {"inspection_id"}
        }
    ocr = inspection.ocr_result
    ocr_payload = None if ocr is None else {
        "id": ocr.id,
        "raw_text": ocr.raw_text,
        "ocr_data": ocr.ocr_data,
        "ocr_engine": ocr.ocr_engine,
        "processing_time_ms": ocr.processing_time_ms,
        "created_at": ocr.created_at,
    }
    physical = []
    for row in rules:
        if _is_physical_verification_rule(row):
            payload = _rule_payload(row)
            payload["status"] = "OUT_OF_SCOPE_PHYSICAL_VERIFICATION"
            physical.append(payload)
    review_items = [
        _rule_payload(row) for row in rules
        if str(row.status).upper().replace("-", "_") in {
            "NOT_VERIFIABLE", "NEEDS_REVIEW", "REVIEW", "MANUAL_CHECK"
        } and not _is_physical_verification_rule(row)
    ]
    return {
        "id": inspection.id,
        "inspection_date": inspection.inspection_date,
        "product_name": inspection.product_name,
        "category": inspection.category,
        "category_confidence": inspection.category_confidence,
        "package_type": inspection.package_type or "NOT_DETECTED",
        "import_status": inspection.import_status or "NOT_DETECTED",
        "quantity_type": inspection.quantity_type,
        "overall_result": screening,
        "screening_result": screening,
        "screening_scope": "AUTOMATED_LABEL_SCREENING",
        "physical_verification": physical,
        "priority": inspection.priority or "MEDIUM",
        "image_path": inspection.image_path,
        "inspector_name": inspection.inspector_name,
        "notes": inspection.notes,
        "regulatory_snapshot": inspection.regulatory_snapshot,
        "created_at": inspection.created_at,
        "product": product_payload,
        "images": [_image_payload(item) for item in (inspection.images or [])],
        "ocr_result": ocr_payload,
        "extracted_fields": [
            _field_payload(field, rule_by_parameter)
            for field in (inspection.extracted_fields or [])
            if field.field_name != "BARCODE_METADATA"
        ],
        "rule_results": [_rule_payload(row) for row in rules],
        "summary": calculate_rule_summary(rules),
        "evidence": [{
            "id": item.id,
            "rule_id": item.rule_id,
            "parameter": item.parameter,
            "evidence_type": item.evidence_type,
            "text_content": item.text_content,
            "bbox": item.bbox,
            "confidence": item.confidence,
        } for item in (inspection.evidence_items or [])],
        "report": _report_payload(inspection.report),
        "review_items": review_items,
    }


@router.post("/report/{inspection_id}")
def generate_report(inspection_id: int, db: Session = Depends(get_db)):
    inspection = db.query(models.Inspection).filter(models.Inspection.id == inspection_id).first()
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    canonical = get_canonical_screening_status(inspection)
    if inspection.rule_results and inspection.overall_result != canonical:
        inspection.overall_result = canonical
        db.commit()
        db.refresh(inspection)
    report = generate_inspection_pdf(inspection, db)
    payload = _report_payload(report) or {}
    payload["file_url"] = f"/api/report/{inspection_id}/download"
    return {
        "message": "Report generated successfully",
        "success": True,
        "data": payload,
    }


@router.get("/report/{inspection_id}/download")
def download_report(inspection_id: int, db: Session = Depends(get_db)):
    inspection = db.query(models.Inspection).filter(models.Inspection.id == inspection_id).first()
    if inspection is None or inspection.report is None:
        raise HTTPException(status_code=404, detail="Inspection report not found")
    report_path = Path(inspection.report.file_path).resolve()
    if not report_path.is_file():
        raise HTTPException(status_code=404, detail="Inspection report file not found")
    return FileResponse(
        str(report_path),
        media_type="application/pdf",
        filename=inspection.report.file_name,
    )
