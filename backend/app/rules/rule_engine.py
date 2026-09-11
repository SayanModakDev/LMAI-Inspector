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
                db_rule.source_link = r_data.get('source_link') or r_data.get('source_url')
                db_rule.source_url = r_data.get('source_url') or r_data.get('source_link')
                from app.rules.status_safety import validate_and_enforce_verification_status
                controlled_status = validate_and_enforce_verification_status(r_data)

                db_rule.source_authority = r_data.get('source_authority')
                db_rule.rule_reference_status = controlled_status
                db_rule.instrument = r_data.get('instrument') or r_data.get('source_document')
                db_rule.citation = r_data.get('citation') or r_data.get('rule_reference')
                db_rule.citation_text = r_data.get('citation_text')
                db_rule.verification_status = controlled_status
                db_rule.version_date = r_data.get('version_date')
                db_rule.effective_date = r_data.get('effective_date') or r_data.get('effective_from')
                db_rule.publication_date = r_data.get('publication_date')
                db_rule.applicability = r_data.get('applicability')
                db_rule.screening_scope = r_data.get('screening_scope')
                db_rule.physical_scope = r_data.get('physical_scope')
                db_rule.notes = r_data.get('notes') or r_data.get('exception')
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


def calculate_rule_summary(rule_results: List[Any]) -> Dict[str, int]:
    """Calculate canonical summary counts over final evaluated rule rows.

    Guarantees summary counters exactly match the matrix table row count:
    passed + failed + review + not_applicable == total
    """
    seen_rule_ids = set()
    deduped = []
    for r in (rule_results or []):
        rid = getattr(r, 'rule_id', None) or (r.get('rule_id') if isinstance(r, dict) else None)
        if rid and rid in seen_rule_ids:
            continue
        if rid:
            seen_rule_ids.add(rid)
        deduped.append(r)

    passed = 0
    failed = 0
    review = 0
    not_applicable = 0

    for r in deduped:
        status = getattr(r, 'status', None) or (r.get('status') if isinstance(r, dict) else None)
        if status == 'PASS':
            passed += 1
        elif status == 'FAIL':
            failed += 1
        elif status in ('NOT_VERIFIABLE', 'NEEDS_REVIEW', 'REVIEW', 'MANUAL_CHECK'):
            review += 1
        elif status == 'NOT_APPLICABLE':
            not_applicable += 1
        else:
            review += 1

    total = passed + failed + review + not_applicable
    return {
        'passed': passed,
        'failed': failed,
        'review': review,
        'not_applicable': not_applicable,
        'total': total,
        'passed_count': passed,
        'failed_count': failed,
        'review_count': review,
        'na_count': not_applicable,
        'not_applicable_count': not_applicable,
        'total_rules': total,
    }


def _is_physical_verification_rule(r: Any) -> bool:
    """Check if a rule represents physical inspection / caliper measurement rather than image-based declaration check."""
    rule_id = getattr(r, 'rule_id', None) or (r.get('rule_id') if isinstance(r, dict) else None)
    parameter = getattr(r, 'parameter', None) or (r.get('parameter') if isinstance(r, dict) else None)
    v_type = getattr(r, 'verification_type', None) or (r.get('verification_type') if isinstance(r, dict) else None)
    ev_data = getattr(r, 'evidence_data', None) or (r.get('evidence_data') if isinstance(r, dict) else None) or {}

    if rule_id in ('PC-ALL-012', 'PC-ALL-013'):
        return True
    if parameter in ('ACTUAL_NET_CONTENT', 'FONT_SIZE_COMPLIANCE'):
        return True
    if v_type in ('PHYSICAL_VERIFICATION_REQUIRED', 'PHYSICAL_INSPECTION', 'MANUAL_MEASUREMENT'):
        return True
    if isinstance(ev_data, dict):
        if ev_data.get('verification_type') in ('PHYSICAL_VERIFICATION_REQUIRED', 'PHYSICAL_INSPECTION', 'MANUAL_MEASUREMENT'):
            return True

    return False


def _is_uncontradicted_visual_candidate(r: Any) -> bool:
    """Check if a rule is a visual candidate (e.g. VEG_NONVEG_SYMBOL) that was detected without contradiction."""
    rule_id = getattr(r, 'rule_id', None) or (r.get('rule_id') if isinstance(r, dict) else None)
    parameter = getattr(r, 'parameter', None) or (r.get('parameter') if isinstance(r, dict) else None)

    if parameter != 'VEG_NONVEG_SYMBOL' and rule_id != 'PC-FOOD-005':
        return False

    ev_data = getattr(r, 'evidence_data', None) or (r.get('evidence_data') if isinstance(r, dict) else None)
    if not ev_data or not isinstance(ev_data, dict):
        return False

    # If there is a detected conflict across package views or contradictory symbols, it is NOT uncontradicted!
    if ev_data.get('has_conflict') is True or ev_data.get('status') == 'CONFLICTING_EVIDENCE':
        return False

    # Check if a visual symbol candidate was detected
    val = ev_data.get('value') or ev_data.get('symbol_type')
    is_cand = (
        ev_data.get('status') == 'CANDIDATE'
        or ev_data.get('is_candidate') is True
        or ev_data.get('source') == 'VISUAL_DETECTION'
        or bool(val)
    )
    if not is_cand or not val:
        return False

    val_lower = str(val).lower()
    if 'conflict' in val_lower or 'contradiction' in val_lower or 'unknown' in val_lower:
        return False

    return True


def _is_blocking_for_automated_screening(r: Any) -> bool:
    """Determine whether an unresolved rule blocks automated screening compliance."""
    status = getattr(r, 'status', None) or (r.get('status') if isinstance(r, dict) else None)
    if status not in ('NOT_VERIFIABLE', 'NEEDS_REVIEW', 'REVIEW', 'MANUAL_CHECK'):
        return False

    # 1. Physical-only requirements (e.g., actual gross/net weight on scale, physical font height in mm)
    # do NOT block automated image screening from reaching COMPLIANT.
    if _is_physical_verification_rule(r):
        return False

    # 2. Visual candidate detected without contradiction (e.g. FSSAI veg symbol identified on food panel)
    # is a non-blocking visual observation pending physical verification.
    if _is_uncontradicted_visual_candidate(r):
        return False

    # 3. Optional rule not required
    required = getattr(r, 'required', None)
    if required is None and isinstance(r, dict):
        required = r.get('required')
    if required is False:
        return False

    # Any missing mandatory image declaration or critical OCR conflict IS blocking
    return True


def derive_overall_result(rule_results: List[Any]) -> str:
    """Derive overall inspection result from evaluated rule results.

    Priority Logic:
    1. Deterministic FAIL -> NON_COMPLIANT
    2. Blocking unresolved critical conflict or missing mandatory declaration -> NOT_VERIFIABLE (REQUIRES REVIEW)
    3. All image-verifiable requirements pass and remaining unresolved items are physical verification
       or non-blocking visual candidates -> COMPLIANT
    """
    from app.core.constants import InspectionStatus
    seen_rule_ids = set()
    deduped = []
    for r in (rule_results or []):
        rid = getattr(r, 'rule_id', None) or (r.get('rule_id') if isinstance(r, dict) else None)
        if rid and rid in seen_rule_ids:
            continue
        if rid:
            seen_rule_ids.add(rid)
        deduped.append(r)

    has_fail = False
    has_blocking_review = False

    for r in deduped:
        status = getattr(r, 'status', None) or (r.get('status') if isinstance(r, dict) else None)
        if status == 'FAIL':
            has_fail = True
        elif _is_blocking_for_automated_screening(r):
            has_blocking_review = True

    if has_fail:
        return InspectionStatus.NON_COMPLIANT
    if has_blocking_review:
        return InspectionStatus.NOT_VERIFIABLE
    return InspectionStatus.COMPLIANT


def evaluate_rules(applicable_rules: List[Dict[str, Any]], extracted_fields: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    """Evaluate applicable rules via deterministic validators and never treat missing OCR as an automatic legal FAIL."""
    from app.rules.validators import dispatch_validator

    # Deduplicate applicable rules by rule_id preserving order
    seen_rule_ids = set()
    deduped_rules = []
    for rule in applicable_rules:
        rid = rule.get('rule_id')
        if rid and rid in seen_rule_ids:
            continue
        if rid:
            seen_rule_ids.add(rid)
        deduped_rules.append(rule)
    applicable_rules = deduped_rules

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
            field_data = extracted_fields.get('MANUFACTURE_DATE') or extracted_fields.get('PACKING_DATE')
        elif not field_data and parameter == 'MANUFACTURE_DATE':
            field_data = extracted_fields.get('MONTH_YEAR_MANUFACTURE') or extracted_fields.get('PACKING_DATE')
        elif not field_data and parameter == 'PACKING_DATE':
            field_data = extracted_fields.get('MONTH_YEAR_MANUFACTURE') or extracted_fields.get('MANUFACTURE_DATE')
        elif not field_data and parameter == 'BEST_BEFORE_USE_BY':
            field_data = extracted_fields.get('USE_BEFORE_DATE') or extracted_fields.get('EXPIRY_DATE')
        elif not field_data and parameter == 'USE_BEFORE_DATE':
            field_data = extracted_fields.get('EXPIRY_DATE') or extracted_fields.get('BEST_BEFORE_USE_BY')
        elif not field_data and parameter == 'EXPIRY_DATE':
            field_data = extracted_fields.get('USE_BEFORE_DATE') or extracted_fields.get('BEST_BEFORE_USE_BY')
        elif not field_data and parameter == 'DECLARED_NET_QUANTITY':
            field_data = extracted_fields.get('NET_QUANTITY')
        elif not field_data and parameter == 'NET_QUANTITY':
            field_data = extracted_fields.get('DECLARED_NET_QUANTITY')

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
            'rule_reference_status': rule.get('rule_reference_status') or rule.get('verification_status', 'VERIFIED'),
            'citation': rule.get('citation') or rule.get('rule_reference'),
            'citation_text': rule.get('citation_text'),
            'verification_status': rule.get('verification_status') or rule.get('rule_reference_status', 'VERIFIED'),
            'source_authority': rule.get('source_authority'),
            'source_document': rule.get('source_document'),
            'source_url': rule.get('source_url') or rule.get('source_link'),
            'screening_scope': rule.get('screening_scope'),
            'physical_scope': rule.get('physical_scope'),
            'notes': rule.get('notes') or rule.get('exception'),
            'review_required': (
                status in ['FAIL', 'NOT_VERIFIABLE']
                or bool(evidence_data and (
                    evidence_data.get('status') in ('CONFLICTING_EVIDENCE', 'REVIEW')
                    or evidence_data.get('has_conflict')
                ))
            ),
            'severity': severity,
            'evidence_state': val_result.evidence_state,
            'validation_result': val_result.to_dict(),
            'candidate_classification': (
                evidence_data.get('candidate_classification') if evidence_data else None
            ),
            'competing_evidence': (
                evidence_data.get('candidates') or evidence_data.get('competing_candidates') or evidence_data.get('values')
                if evidence_data else None
            ),
            'verification_type': verification_type,
            'required': required,
        }

        if isinstance(evidence_data, dict):
            if val_result.evidence_state is not None:
                evidence_data.setdefault('evidence_state', val_result.evidence_state)
            if verification_type:
                evidence_data.setdefault('verification_type', verification_type)

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

    overall_result = derive_overall_result(results)
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
