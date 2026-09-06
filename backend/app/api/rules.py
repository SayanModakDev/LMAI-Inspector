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
            evidence_required=r.evidence_required
        ) for r in rules
    ]
