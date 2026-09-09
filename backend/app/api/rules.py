from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database import models, schemas

router = APIRouter()

@router.get("/rules", response_model=List[schemas.RuleSchema])
def get_rules(db: Session = Depends(get_db)):
    """Get the active rule matrix used for evaluations."""
    rules = db.query(models.Rule).filter(models.Rule.is_active == True).all()
    
    return [
        schemas.RuleSchema(
            rule_id=r.rule_id,
            parameter=r.parameter,
            category=r.category,
            package_type=r.package_type,
            condition=r.condition,
            rule_reference=r.rule_reference,
            source_document=r.source_document,
            rule_version=r.rule_version,
            effective_from=r.effective_from,
            effective_until=r.effective_until,
            required=r.required,
            what_to_extract=r.what_to_extract,
            validation_method=r.validation_method,
            verification_type=r.verification_type,
            result_type=r.result_type,
            severity=r.severity,
            exception=r.exception,
            evidence_required=r.evidence_required,
            source_authority=getattr(r, 'source_authority', None),
            source_url=getattr(r, 'source_url', None) or getattr(r, 'source_link', None),
            source_link=getattr(r, 'source_link', None) or getattr(r, 'source_url', None),
            rule_reference_status=getattr(r, 'rule_reference_status', 'PENDING_VERIFICATION') or 'PENDING_VERIFICATION',
            regulatory_source=r.regulatory_source,
            instrument=getattr(r, 'instrument', None) or r.source_document,
            citation=getattr(r, 'citation', None) or r.rule_reference,
            citation_text=getattr(r, 'citation_text', None),
            verification_status=getattr(r, 'verification_status', None) or getattr(r, 'rule_reference_status', None),
            version_date=getattr(r, 'version_date', None),
            effective_date=getattr(r, 'effective_date', None) or r.effective_from,
            applicability=getattr(r, 'applicability', None),
            screening_scope=getattr(r, 'screening_scope', None),
            physical_scope=getattr(r, 'physical_scope', None),
            notes=getattr(r, 'notes', None) or r.exception,
        ) for r in rules
    ]
