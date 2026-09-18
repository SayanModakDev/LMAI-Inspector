# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from datetime import timezone
from typing import List, Optional, Any
from app.database.connection import get_db
from app.database import models, schemas
from app.reports.pdf_report import generate_inspection_pdf
from app.rules.rule_engine import evaluate_rules, build_inspection_findings, calculate_rule_summary, derive_overall_result
from app.rules.applicability import get_applicable_rules

from app.core.constants import InspectionStatus, normalize_status
from app.core.config import get_settings

router = APIRouter()
settings = get_settings()


def format_public_url(path: Optional[str]) -> Optional[str]:
    """Prefix path with PUBLIC_BASE_URL if configured, otherwise return relative path."""
    if not path or path.startswith("http://") or path.startswith("https://"):
        return path
    base = settings.PUBLIC_BASE_URL.strip().rstrip("/") if settings.PUBLIC_BASE_URL else ""
    clean_path = path if path.startswith("/") else f"/{path}"
    return f"{base}{clean_path}" if base else clean_path


@router.get("/history", response_model=List[schemas.InspectionSummary])
def get_history(
    skip: int = 0, 
    limit: int = 100,
    status: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get list of past inspections."""
    query = db.query(models.Inspection).order_by(desc(models.Inspection.created_at))
    
    if status:
        norm = normalize_status(status)
        if norm == InspectionStatus.NON_COMPLIANT:
            query = query.filter(models.Inspection.overall_result.in_(["NON_COMPLIANT", "NON-COMPLIANT"]))
        elif norm == InspectionStatus.NOT_VERIFIABLE:
            query = query.filter(models.Inspection.overall_result.in_(["NOT_VERIFIABLE", "NEEDS_REVIEW", "NOT-VERIFIABLE", "NEEDS-REVIEW"]))
        elif norm == InspectionStatus.COMPLIANT:
            query = query.filter(models.Inspection.overall_result == "COMPLIANT")
        elif norm == InspectionStatus.NOT_APPLICABLE:
            query = query.filter(models.Inspection.overall_result.in_(["NOT_APPLICABLE", "NOT-APPLICABLE"]))
        else:
            query = query.filter(models.Inspection.overall_result == status)
    if category:
        query = query.filter(models.Inspection.category == category)
        
    inspections: List[Any] = query.offset(skip).limit(limit).all()
    
    result_summaries = []
    for i in inspections:
        created_dt = i.created_at
        if created_dt and created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)
        ocr_payload_data = i.ocr_result.ocr_data if i.ocr_result and isinstance(i.ocr_result.ocr_data, dict) else {}
        analysis_source = ocr_payload_data.get("analysis_source")
        result_summaries.append(
            schemas.InspectionSummary(
                id=int(i.id),
                inspection_date=created_dt,
                product_name=str(i.product_name) if i.product_name is not None else None,
                category=str(i.category) if i.category is not None else None,
                package_type=str(i.package_type) if i.package_type is not None else "NOT_DETECTED",
                import_status=str(i.import_status) if i.import_status is not None else "NOT_DETECTED",
                overall_result=str(normalize_status(str(i.overall_result)) if i.overall_result is not None else None),
                priority=str(i.priority or "MEDIUM"),
                inspector_name=str(i.inspector_name) if i.inspector_name is not None else None,
                created_at=created_dt,
                report=(
                    {"id": i.report.id, "file_name": i.report.file_name}
                    if i.report else None
                ),
                analysis_source=analysis_source,
            )
        )
    return result_summaries


@router.get("/dashboard", response_model=schemas.DashboardStats)
def get_dashboard(db: Session = Depends(get_db)):
    """Get statistics for the dashboard using canonical states."""
    total = db.query(models.Inspection).count()
    compliant = db.query(models.Inspection).filter(models.Inspection.overall_result == "COMPLIANT").count()
    non_compliant = db.query(models.Inspection).filter(models.Inspection.overall_result.in_(["NON_COMPLIANT", "NON-COMPLIANT"])).count()
    not_verifiable = db.query(models.Inspection).filter(models.Inspection.overall_result.in_(["NOT_VERIFIABLE", "NEEDS_REVIEW", "NOT-VERIFIABLE", "NEEDS-REVIEW"])).count()
    not_applicable = db.query(models.Inspection).filter(models.Inspection.overall_result.in_(["NOT_APPLICABLE", "NOT-APPLICABLE"])).count()
    
    food = db.query(models.Inspection).filter(models.Inspection.category == "FOOD").count()
    cosmetic = db.query(models.Inspection).filter(models.Inspection.category == "COSMETIC").count()
    
    recent: List[Any] = db.query(models.Inspection).order_by(desc(models.Inspection.created_at)).limit(5).all()
    
    # Common failed parameters
    failed_rules = db.query(
        models.RuleResult.parameter, func.count(models.RuleResult.id).label('count')
    ).filter(models.RuleResult.status == "FAIL")\
     .group_by(models.RuleResult.parameter)\
     .order_by(desc('count'))\
     .limit(5).all()
     
    common_failed = [{"parameter": r[0], "count": r[1]} for r in failed_rules]
    
    recent_inspections = []
    for i in recent:
        created_dt = i.created_at
        if created_dt and created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)
        recent_inspections.append({
            "id": i.id,
            "product_name": i.product_name,
            "category": i.category,
            "package_type": i.package_type or "NOT_DETECTED",
            "import_status": i.import_status or "NOT_DETECTED",
            "result": str(normalize_status(str(i.overall_result) if i.overall_result is not None else None) or i.overall_result or ""),
            "date": created_dt.isoformat() if created_dt else None
        })

    return schemas.DashboardStats(
        total_inspections=total,
        compliant=compliant,
        non_compliant=non_compliant,
        not_verifiable=not_verifiable,
        not_applicable=not_applicable,
        food_inspections=food,
        cosmetic_inspections=cosmetic,
        recent_inspections=recent_inspections,
        common_failed_parameters=common_failed
    )


@router.get("/inspection/{inspection_id}")
def get_inspection_detail(inspection_id: int, db: Session = Depends(get_db)):
    """Get full details of a specific inspection."""
    inspection: Any = db.query(models.Inspection).filter(models.Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
        
    # Serialize data
    product = {c.name: getattr(inspection.product, c.name) for c in inspection.product.__table__.columns} if inspection.product else None
    ocr_result = {c.name: getattr(inspection.ocr_result, c.name) for c in inspection.ocr_result.__table__.columns} if inspection.ocr_result else None
    extracted_fields = [{c.name: getattr(f, c.name) for c in f.__table__.columns} for f in inspection.extracted_fields]
    rule_results = []
    for r in inspection.rule_results:
        item = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        ed = item.get("evidence_data") or {}
        if "binary" in ed and ed["binary"] is not None:
            item["binary"] = ed["binary"]
        else:
            if item.get("status") == "PASS":
                item["binary"] = 1
            elif item.get("status") == "FAIL":
                item["binary"] = 0
            else:
                item["binary"] = None
        item["reason"] = ed.get("reason") or item.get("message")
        if "validation_method" in ed:
            item["validation_method"] = ed["validation_method"]
        for field in ["value", "unit", "quantity_present", "unit_present", "quantity_unit_valid", "raw_value", "validation_result"]:
            if field in ed and ed[field] is not None:
                item[field] = ed[field]
        rule_results.append(item)

    # Deduplicate rule results by rule_id preserving order
    seen_rule_ids = set()
    deduped_results = []
    for r_item in rule_results:
        rid = r_item.get("rule_id")
        if rid and rid in seen_rule_ids:
            continue
        if rid:
            seen_rule_ids.add(rid)
        deduped_results.append(r_item)
    rule_results = deduped_results
    rule_summary = calculate_rule_summary(rule_results)
    derived_overall = derive_overall_result(rule_results)

    images = [
        {
            "id": image.id,
            "image_index": image.image_index,
            "file_name": image.file_name,
            "image_path": format_public_url(f"/uploads/{image.file_name}"),
            "processed_file_name": image.processed_file_name,
            "source": image.source,
        }
        for image in inspection.images
    ]
    evidence = [{c.name: getattr(e, c.name) for c in e.__table__.columns} for e in inspection.evidence_items]
    report = {c.name: getattr(inspection.report, c.name) for c in inspection.report.__table__.columns} if inspection.report else None
    if report and report.get("file_name"):
        report["file_url"] = format_public_url(f"/api/report/{inspection.id}/download")
    
    created_dt = inspection.created_at
    if created_dt and created_dt.tzinfo is None:
        created_dt = created_dt.replace(tzinfo=timezone.utc)
    inspect_str = created_dt.strftime("%Y-%m-%d") if created_dt else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    reg_snapshot = getattr(inspection, "regulatory_snapshot", None) or "LMPC_2011_CURRENT_2024 | FSSAI_LD_2020_CURRENT_2024"
    reg_snapshot_label = f"Effective for inspection date: {inspect_str}"

    # -----------------------------------------------------------------------
    # Enrich extracted_fields with candidate / evidence data from rule_results
    # so the frontend can display actual package-image candidates
    # without fabrication. No DB schema change needed — rule_results already
    # carry evidence_data.candidates / competing_evidence from the validators.
    # -----------------------------------------------------------------------
    rule_evidence_by_param: dict = {}
    for rr in rule_results:
        param = rr.get("parameter")
        if param and param not in rule_evidence_by_param:
            rule_evidence_by_param[param] = rr

    for ef in extracted_fields:
        param = ef.get("field_name")
        rr = rule_evidence_by_param.get(param)
        if rr:
            ed = rr.get("evidence_data") or {}
            # Expose candidates array (real OCR candidates, never fabricated)
            candidates = (
                ed.get("candidates")
                or rr.get("competing_evidence")
                or ed.get("competing_candidates")
                or ed.get("values")
            )
            if candidates:
                ef["candidates"] = candidates
            # Expose evidence state for automatic result context
            ev_state = rr.get("evidence_state") or ed.get("evidence_state")
            if ev_state:
                ef["evidence_state"] = ev_state
            # Expose candidate_classification
            cc = rr.get("candidate_classification") or ed.get("candidate_classification")
            if cc:
                ef["candidate_classification"] = cc
            # has_conflict flag
            if ed.get("has_conflict") is not None:
                ef["has_conflict"] = ed["has_conflict"]
            # rule status for quick lookup
            ef["rule_status"] = rr.get("status")
            ef["rule_reason"] = rr.get("reason") or rr.get("message")
            ef["rule_id"] = rr.get("rule_id")

    # -----------------------------------------------------------------------
    # Product Familiarity / Reference Product Registry
    # -----------------------------------------------------------------------
    registry_match = None
    ocr_payload_data = ocr_result.get("ocr_data") if ocr_result else {}
    analysis_source = None
    llm_metadata = None
    if isinstance(ocr_payload_data, dict):
        registry_match = ocr_payload_data.get("registry_match")
        analysis_source = ocr_payload_data.get("analysis_source")
        llm_metadata = ocr_payload_data.get("llm_metadata")

    if not registry_match:
        from app.registry.matcher import match_product
        barcode_val = None
        if isinstance(ocr_payload_data, dict):
            b_res = ocr_payload_data.get("barcode_result") or {}
            barcode_val = b_res.get("value")
        ef_dict = {f.get("field_name"): f.get("field_value") for f in extracted_fields if f.get("field_name")}
        reg_result = match_product(
            barcode=barcode_val or ef_dict.get("BARCODE"),
            brand=ef_dict.get("BRAND") or (product.get("brand") if product else None),
            generic_name=ef_dict.get("GENERIC_NAME") or (product.get("generic_name") if product else None),
            product_name=ef_dict.get("PRODUCT_NAME") or (product.get("product_name") if product else None),
            quantity=ef_dict.get("DECLARED_NET_QUANTITY") or (
                f"{product.get('declared_net_quantity_value')} {product.get('declared_net_quantity_unit')}"
                if product and product.get("declared_net_quantity_value")
                else None
            ),
            category=inspection.category,
        )
        registry_match = reg_result.to_dict()

    # Build complete dict since response_model requires handling nested objects correctly.
    # Alternatively return a dict that matches the schema
    return {
        "id": inspection.id,
        "inspection_date": created_dt,
        "product_name": inspection.product_name,
        "brand": inspection.brand,
        "product_type": inspection.product_type,
        "category": inspection.category,
        "category_confidence": inspection.category_confidence,
        "package_type": inspection.package_type,
        "import_status": inspection.import_status,
        "quantity_type": inspection.quantity_type,
        "overall_result": str(normalize_status(derived_overall) or normalize_status(str(inspection.overall_result) if inspection.overall_result is not None else None) or inspection.overall_result or ""),
        "priority": inspection.priority,
        "image_path": format_public_url(f"/uploads/{inspection.image_path}") if inspection.image_path else None,
        "inspector_name": inspection.inspector_name,
        "notes": inspection.notes,
        "regulatory_snapshot": reg_snapshot,
        "regulatory_snapshot_label": reg_snapshot_label,
        "created_at": created_dt,
        "product": product,
        "images": images,
        "ocr_result": ocr_result,
        "extracted_fields": extracted_fields,
        "rule_results": rule_results,
        "summary": rule_summary,
        "evidence": evidence,
        "report": report,
        "findings": build_inspection_findings(rule_results),
        "registry_match": registry_match,
        "analysis_source": analysis_source,
        "llm_metadata": llm_metadata,
    }

@router.post("/report/{inspection_id}", response_model=schemas.MessageResponse)
def generate_report(inspection_id: int, db: Session = Depends(get_db)):
    """Generate a PDF report for the inspection."""
    inspection: Any = db.query(models.Inspection).filter(models.Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
        
    try:
        report = generate_inspection_pdf(inspection, db)
        return schemas.MessageResponse(
            message="Report generated successfully",
            data={"report_id": report.id, "file_url": format_public_url(f"/api/report/{inspection_id}/download")}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.get("/report/{inspection_id}/download")
def download_report(inspection_id: int, db: Session = Depends(get_db)):
    """Download the generated PDF report."""
    inspection: Any = db.query(models.Inspection).filter(models.Inspection.id == inspection_id).first()
    if not inspection or not inspection.report:
        raise HTTPException(status_code=404, detail="Report not found")
        
    file_path = inspection.report.file_path
    import os
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report file not found on disk")
        
    return FileResponse(
        path=file_path, 
        filename=inspection.report.file_name, 
        media_type="application/pdf"
    )
