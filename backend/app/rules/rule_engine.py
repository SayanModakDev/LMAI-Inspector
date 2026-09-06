"""Rule Engine — evaluates extracted declarations against the active rule matrix."""

import json
import logging
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.connection import SessionLocal
from app.database.models import Rule

logger = logging.getLogger(__name__)
settings = get_settings()


def sync_rules_to_db() -> None:
    """Read the rule matrix JSON and sync it to the database without duplication."""
    try:
        with open(settings.RULE_MATRIX_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        json_rules = data.get('rules', [])
        if not json_rules:
            logger.warning("No rules found in rule_matrix.json")
            return

        db: Session = SessionLocal()
        try:
            for r_data in json_rules:
                rule_id = r_data.get('rule_id')
                if not rule_id:
                    continue

                db_rule = db.query(Rule).filter(Rule.rule_id == rule_id).first()
                if not db_rule:
                    db_rule = Rule(rule_id=rule_id)
                    db.add(db_rule)

                db_rule.parameter = r_data.get('parameter', '')
                db_rule.category = r_data.get('category', 'ALL')
                db_rule.package_type = r_data.get('package_type', 'ALL')
                db_rule.product_type = r_data.get('product_type', 'ALL')
                db_rule.regulatory_source = r_data.get(
                    'regulatory_source',
                    'FSSAI_FOOD_LABELING' if str(rule_id).startswith('PC-FOOD') else ('COSMETIC_LABELING' if str(rule_id).startswith('PC-COSM') else 'LEGAL_METROLOGY'),
                )
                db_rule.condition = r_data.get('condition', 'APPLICABLE')
                db_rule.rule_reference = r_data.get('rule_reference')
                db_rule.source_document = r_data.get('source_document')
                db_rule.rule_version = r_data.get('rule_version', 'PENDING_VERIFICATION')
                db_rule.effective_from = r_data.get('effective_from')
                db_rule.effective_until = r_data.get('effective_until')
                db_rule.required = r_data.get('required', True)
                db_rule.what_to_extract = r_data.get('what_to_extract')
                db_rule.validation_method = r_data.get('validation_method')
                db_rule.verification_type = r_data.get('verification_type')
                db_rule.result_type = r_data.get('result_type', 'PASS_FAIL')
                db_rule.severity = r_data.get('severity', 'HIGH')
                db_rule.exception = r_data.get('exception')
                db_rule.evidence_required = r_data.get('evidence_required', True)
                db_rule.source_link = r_data.get('source_link')
                db_rule.detection_method = r_data.get('detection_method')
                db_rule.visual_or_text = r_data.get('visual_or_text', 'TEXT')
                db_rule.is_active = True

            db.commit()
            logger.info(f"Successfully synced {len(json_rules)} rules to database.")
        except Exception as exc:
            db.rollback()
            logger.error(f"Failed to sync rules to database: {exc}")
        finally:
            db.close()
    except Exception as exc:
        logger.error(f"Could not read rule_matrix.json: {exc}")


def evaluate_rules(applicable_rules: List[Dict[str, Any]], extracted_fields: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    """Evaluate applicable rules via deterministic validators and never treat missing OCR as an automatic legal FAIL."""
    from app.rules.validators import dispatch_validator

    results: List[Dict[str, Any]] = []
    has_fail = False
    has_not_verifiable = False

    for rule in applicable_rules:
        rule_id = rule.get('rule_id', 'UNKNOWN')
        parameter = rule.get('parameter', 'UNKNOWN')
        required = rule.get('required', True)
        severity = rule.get('severity', 'HIGH')
        verification_type = rule.get('verification_type', 'IMAGE_VERIFIABLE')

        # Resolve aliases if the primary parameter is not present in extracted fields
        field_data = extracted_fields.get(parameter)
        if not field_data and parameter == 'MONTH_YEAR_MANUFACTURE':
            field_data = extracted_fields.get('PACKING_DATE') or extracted_fields.get('MONTH_YEAR_MANUFACTURE')
        if not field_data and parameter == 'BEST_BEFORE_USE_BY':
            field_data = extracted_fields.get('USE_BEFORE_DATE') or extracted_fields.get('BEST_BEFORE_USE_BY')

        # Dispatch to deterministic validator
        validation_method = rule.get('validation_method')
        val_result = dispatch_validator(
            validation_method=validation_method,
            evidence=field_data,
            rule=rule,
            all_fields=extracted_fields,
        )

        status = val_result.status
        message = val_result.reason
        evidence_data = val_result.evidence

        if required and status == 'NOT_VERIFIABLE':
            has_not_verifiable = True

        if status == 'FAIL':
            has_fail = True

        res_item: Dict[str, Any] = {
            'rule_id': rule_id,
            'parameter': parameter,
            'status': status,
            'binary': val_result.binary,
            'message': message,
            'reason': message,
            'evidence_data': evidence_data,
            'rule_version': rule.get('rule_version'),
            'regulatory_source': rule.get('regulatory_source', 'LEGAL_METROLOGY'),
            'rule_reference': rule.get('rule_reference'),
            'review_required': status in ['FAIL', 'NOT_VERIFIABLE'],
            'severity': severity,
            'validation_result': val_result.to_dict(),
        }

        # Expose structured quantity/unit attributes directly on result if available
        if val_result.raw_value is not None:
            res_item['raw_value'] = val_result.raw_value
        if val_result.value is not None:
            res_item['value'] = val_result.value
        if val_result.unit is not None or val_result.unit_present is not None:
            res_item['unit'] = val_result.unit
        if val_result.quantity_present is not None:
            res_item['quantity_present'] = val_result.quantity_present
        if val_result.unit_present is not None:
            res_item['unit_present'] = val_result.unit_present
        if val_result.quantity_unit_valid is not None:
            res_item['quantity_unit_valid'] = val_result.quantity_unit_valid

        results.append(res_item)

    if has_fail:
        overall_result = 'NON-COMPLIANT'
    elif has_not_verifiable:
        overall_result = 'NOT_VERIFIABLE'
    else:
        overall_result = 'COMPLIANT'

    return results, overall_result


def build_inspection_findings(rule_results: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Create a concise, evidence-backed inspector summary for UI and PDF."""
    verified, review, failed = [], [], []
    for result in rule_results:
        parameter = str(result.get('parameter', '')).replace('_', ' ').title()
        if result.get('status') == 'PASS':
            verified.append(f"{parameter}: {result.get('message', 'evidence detected')}")
        elif result.get('status') == 'FAIL':
            failed.append(f"{parameter}: {result.get('message', 'not satisfied')}")
        elif result.get('status') == 'NOT_VERIFIABLE':
            review.append(f"{parameter}: {result.get('message', 'requires review')}")
    return {'verified': verified, 'needs_review': review, 'failed': failed}


def _is_usable_evidence(field_data: Dict[str, Any]) -> bool:
    """Require a non-empty value and confidence before reporting an OCR pass."""
    value = field_data.get('value')
    if value is None or not str(value).strip():
        return False
    confidence = field_data.get('confidence')
    return confidence is None or float(confidence) >= 0.6
