"""Rule Engine — evaluates extracted declarations against the active rule matrix."""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.connection import SessionLocal
from app.database.models import Rule, RuleResult

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
                db_rule.notes = r_data.get('notes') or r_data.get('exception')
                db_rule.detection_method = r_data.get('detection_method')
                db_rule.visual_or_text = r_data.get('visual_or_text', 'TEXT')
                db_rule.is_active = True

            active_rule_ids = {r.get('rule_id') for r in json_rules if r.get('rule_id')}
            stale_rule_ids = {
                rule_id
                for (rule_id,) in db.query(Rule.rule_id).filter(
                    ~Rule.rule_id.in_(active_rule_ids)
                ).all()
            }
            db.query(Rule).filter(~Rule.rule_id.in_(active_rule_ids)).update(
                {Rule.is_active: False}, synchronize_session=False
            )
            if stale_rule_ids:
                db.query(RuleResult).filter(
                    RuleResult.rule_id.in_(stale_rule_ids)
                ).delete(synchronize_session=False)

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

    from app.core.constants import RuleStatus, normalize_rule_status

    for r in deduped:
        raw_status = getattr(r, 'status', None) or (r.get('status') if isinstance(r, dict) else None)
        status = normalize_rule_status(raw_status)
        if status == RuleStatus.PASS:
            passed += 1
        elif status == RuleStatus.FAIL:
            failed += 1
        elif status == RuleStatus.NOT_VERIFIABLE:
            review += 1
        elif status == RuleStatus.NOT_APPLICABLE:
            not_applicable += 1

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


def _is_physical_verification_rule(r: Any) -> bool:
    """Check if a rule result represents a physical verification requirement (caliper/scale)."""
    vtype = getattr(r, 'verification_type', None) or (r.get('verification_type') if isinstance(r, dict) else None)
    evidence_data = getattr(r, 'evidence_data', None) or (r.get('evidence_data') if isinstance(r, dict) else None)
    if not vtype and isinstance(evidence_data, dict):
        vtype = evidence_data.get('verification_type')
    rid = getattr(r, 'rule_id', None) or (r.get('rule_id') if isinstance(r, dict) else None)
    param = getattr(r, 'parameter', None) or (r.get('parameter') if isinstance(r, dict) else None)
    return (
        vtype in ('PHYSICAL_VERIFICATION_REQUIRED', 'PHYSICAL_CHECK')
        or rid in ('PC-ALL-012', 'PC-ALL-013')
        or param in ('ACTUAL_NET_CONTENT', 'FONT_SIZE_COMPLIANCE')
    )


def _is_blocking_for_automated_screening(r: Any) -> bool:
    """Determine whether an unresolved rule blocks automated screening compliance."""
    status = getattr(r, 'status', None) or (r.get('status') if isinstance(r, dict) else None)
    if status not in ('NOT_VERIFIABLE', 'NEEDS_REVIEW', 'REVIEW', 'MANUAL_CHECK'):
        return False

    # Physical verification checks (caliper measurement, physical weighing) cannot be verified
    # from package images alone and do not block automated optical screening.
    if _is_physical_verification_rule(r):
        return False

    # Visual candidate detected without contradiction (e.g. FSSAI veg symbol identified on food panel)
    # is a non-blocking visual observation pending additional image evidence.
    if _is_uncontradicted_visual_candidate(r):
        return False

    # Optional rule not required
    required = getattr(r, 'required', None)
    if required is None and isinstance(r, dict):
        required = r.get('required')
    if required is False:
        return False

    # Any missing mandatory image declaration or critical OCR conflict IS blocking
    return True


def derive_overall_result(rule_results: List[Any]) -> str:
    """Derive the complete inspection result from canonical rule outcomes.

    NOT_APPLICABLE rows are excluded. Confirmed failures take precedence over
    unresolved checks; any remaining unresolved applicable check prevents a
    complete inspection from being labelled compliant.
    """
    from app.core.constants import InspectionStatus, RuleStatus, normalize_rule_status
    seen_rule_ids = set()
    deduped = []
    for r in (rule_results or []):
        rid = getattr(r, 'rule_id', None) or (r.get('rule_id') if isinstance(r, dict) else None)
        if rid and rid in seen_rule_ids:
            continue
        if rid:
            seen_rule_ids.add(rid)
        deduped.append(r)

    applicable_statuses = []
    for r in deduped:
        raw_status = getattr(r, 'status', None) or (r.get('status') if isinstance(r, dict) else None)
        status = normalize_rule_status(raw_status)
        if status != RuleStatus.NOT_APPLICABLE:
            applicable_statuses.append(status)

    if not applicable_statuses:
        return InspectionStatus.NOT_VERIFIABLE
    if RuleStatus.FAIL in applicable_statuses:
        return InspectionStatus.NON_COMPLIANT
    if RuleStatus.NOT_VERIFIABLE in applicable_statuses:
        return InspectionStatus.NOT_VERIFIABLE
    if all(status == RuleStatus.PASS for status in applicable_statuses):
        return InspectionStatus.COMPLIANT
    return InspectionStatus.NOT_VERIFIABLE


def derive_screening_result(rule_results: List[Any]) -> str:
    """Derive the automatic image-screening result without physical checks.

    This is informational only. ``derive_overall_result`` remains the legal
    inspection outcome and includes every applicable physical requirement.
    """
    image_results = [
        result
        for result in (rule_results or [])
        if not _is_physical_verification_rule(result)
    ]
    return derive_overall_result(image_results)


def reconcile_persisted_overall_results(db: Session) -> int:
    """Repair stored inspection outcomes using their persisted rule rows.

    This makes legacy history and regenerated reports use the same canonical
    result as new scans. Inspections without evaluated rule rows are preserved.
    """
    from app.core.constants import normalize_status
    from app.database.models import Inspection

    changed = 0
    for inspection in db.query(Inspection).all():
        rule_results = list(getattr(inspection, "rule_results", None) or [])
        if not rule_results:
            continue
        canonical = str(derive_overall_result(rule_results))
        stored = normalize_status(getattr(inspection, "overall_result", None))
        if stored != canonical or getattr(inspection, "overall_result", None) != canonical:
            inspection.overall_result = canonical
            changed += 1
    if changed:
        db.commit()
        logger.warning("Reconciled %d persisted inspection overall result(s)", changed)
    return changed


def _is_usable_field_candidate(field_data: Optional[Dict[str, Any]], is_date: bool = False) -> bool:
    """Check if field evidence contains a usable, non-empty, non-conflicting candidate."""
    if not field_data or not isinstance(field_data, dict):
        return False
    val = field_data.get('value')
    if val is None or not str(val).strip():
        return False
    if field_data.get('has_conflict') is True or field_data.get('status') == 'CONFLICTING_EVIDENCE':
        return False
    if field_data.get('clearly_invalid') is True:
        return False
    if is_date:
        from app.extraction.declaration_extractor import is_valid_date_candidate
        if not is_valid_date_candidate(str(val)):
            norm = field_data.get('normalized_value')
            if not norm or not is_valid_date_candidate(str(norm)):
                return False
    return True


def _are_dates_equivalent(val1: str, val2: str) -> bool:
    """Determine whether two date expressions represent equivalent calendar dates."""
    if not val1 or not val2:
        return False
    s1 = str(val1).strip()
    s2 = str(val2).strip()
    if s1.lower() == s2.lower():
        return True
    from app.extraction.declaration_extractor import DATE_PREFIX_RE, parse_date_with_precision
    c1 = DATE_PREFIX_RE.sub('', s1).strip()
    c2 = DATE_PREFIX_RE.sub('', s2).strip()
    if c1.lower() == c2.lower():
        return True
    ok1, norm1, m1 = parse_date_with_precision(c1)
    ok2, norm2, m2 = parse_date_with_precision(c2)
    if ok1 and ok2:
        if norm1 == norm2:
            return True
        if m1 and m2:
            p1 = m1.get('parsed_components', {})
            p2 = m2.get('parsed_components', {})
            if p1.get('year') == p2.get('year') and p1.get('month') == p2.get('month'):
                if p1.get('day') is None or p2.get('day') is None or p1.get('day') == p2.get('day'):
                    return True
    return False


def resolve_canonical_field_evidence(
    parameter: str,
    rule: Dict[str, Any],
    extracted_fields: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Resolve field evidence taking statutory equivalence and date-role mapping into account.

    Maintains complete provenance:
    - original_semantic_field
    - canonical_regulatory_field
    - source_evidence, bboxes, token IDs, panel metadata
    Consolidates agreeing expressions without conflict.
    Flags genuine disagreement as a statutory conflict.
    """
    field_data = extracted_fields.get(parameter)
    rule_ref = rule.get('rule_reference', 'statutory requirements')

    # Define statutory equivalence groups
    # Cosmetics Rule 34(1)(f): permits either expiry date or use-before date
    # Food: permits best before or use by
    date_equivalents: Dict[str, List[str]] = {
        'USE_BEFORE_DATE': ['EXPIRY_DATE', 'BEST_BEFORE_USE_BY'],
        'EXPIRY_DATE': ['USE_BEFORE_DATE', 'BEST_BEFORE_USE_BY'],
        'BEST_BEFORE_USE_BY': ['USE_BEFORE_DATE', 'EXPIRY_DATE'],
        'MONTH_YEAR_MANUFACTURE': ['MANUFACTURE_DATE', 'PACKING_DATE'],
        'MANUFACTURE_DATE': ['MONTH_YEAR_MANUFACTURE', 'PACKING_DATE'],
        'PACKING_DATE': ['MONTH_YEAR_MANUFACTURE', 'MANUFACTURE_DATE'],
    }

    if parameter in date_equivalents:
        is_primary_usable = _is_usable_field_candidate(field_data, is_date=True)
        equiv_keys = date_equivalents[parameter]

        # Find usable equivalents
        usable_equivs: List[Tuple[str, Dict[str, Any]]] = []
        for eq_key in equiv_keys:
            eq_data = extracted_fields.get(eq_key)
            if _is_usable_field_candidate(eq_data, is_date=True):
                usable_equivs.append((eq_key, eq_data))

        if not is_primary_usable:
            if usable_equivs:
                # Map first usable statutory equivalent to satisfy the requirement
                source_field, source_data = usable_equivs[0]
                mapped_data = dict(source_data)
                mapped_data['original_semantic_field'] = source_field
                mapped_data['canonical_regulatory_field'] = parameter
                mapped_data['mapped_from'] = source_field
                mapped_data['role_mapping_note'] = (
                    f"Statutory date mapping: '{source_field}' satisfied '{parameter}' "
                    f"under {rule_ref}."
                )
                return mapped_data
            else:
                return field_data

        else:
            # Primary is usable. Check if equivalent declarations also exist.
            if usable_equivs:
                source_field, source_data = usable_equivs[0]
                val1 = str(field_data.get('normalized_value') or field_data.get('value', ''))
                val2 = str(source_data.get('normalized_value') or source_data.get('value', ''))
                if _are_dates_equivalent(val1, val2):
                    # They agree: consolidate without false conflict
                    consolidated = dict(field_data)
                    consolidated['consolidated_with'] = source_field
                    consolidated['consolidation_note'] = (
                        f"Statutory date declarations '{parameter}' and '{source_field}' agree ({val1})."
                    )
                    return consolidated
                else:
                    # Genuinely distinct dates: flag conflict
                    return {
                        'value': f"{val1} vs {val2}",
                        'status': 'CONFLICTING_EVIDENCE',
                        'has_conflict': True,
                        'conflict_reason': (
                            f"Conflicting statutory dates detected: {parameter} ({val1}) "
                            f"vs {source_field} ({val2})"
                        ),
                        'values': [val1, val2],
                        'candidates': [field_data, source_data],
                        'original_semantic_field': f"{parameter} & {source_field}",
                        'canonical_regulatory_field': parameter,
                    }
            return field_data

    # Quantity equivalents
    if parameter in ('DECLARED_NET_QUANTITY', 'NET_QUANTITY'):
        if not _is_usable_field_candidate(field_data):
            alt_key = 'NET_QUANTITY' if parameter == 'DECLARED_NET_QUANTITY' else 'DECLARED_NET_QUANTITY'
            alt_data = extracted_fields.get(alt_key)
            if _is_usable_field_candidate(alt_data):
                mapped_data = dict(alt_data)
                mapped_data['original_semantic_field'] = alt_key
                mapped_data['canonical_regulatory_field'] = parameter
                return mapped_data

    return field_data


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

        # Resolve field evidence with statutory date/role equivalence
        field_data = resolve_canonical_field_evidence(parameter, rule, extracted_fields)

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

        if isinstance(field_data, dict):
            if field_data.get('original_semantic_field'):
                res_item['original_semantic_field'] = field_data['original_semantic_field']
            if field_data.get('canonical_regulatory_field'):
                res_item['canonical_regulatory_field'] = field_data['canonical_regulatory_field']
            if field_data.get('role_mapping_note'):
                res_item['role_mapping_note'] = field_data['role_mapping_note']
            if field_data.get('mapped_from'):
                res_item['mapped_from'] = field_data['mapped_from']

        if isinstance(evidence_data, dict):
            if val_result.evidence_state is not None:
                evidence_data.setdefault('evidence_state', val_result.evidence_state)
            if verification_type:
                evidence_data.setdefault('verification_type', verification_type)
            if isinstance(field_data, dict):
                for k in ('original_semantic_field', 'canonical_regulatory_field', 'role_mapping_note', 'mapped_from', 'source_evidence'):
                    if k in field_data and k not in evidence_data:
                        evidence_data[k] = field_data[k]

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
    """Create a concise, evidence-backed summary for UI and PDF."""
    from app.core.constants import RuleStatus, normalize_rule_status

    verified, review, failed, physical_unverified = [], [], [], []
    for result in rule_results:
        parameter = str(result.get('parameter', '')).replace('_', ' ').title()
        status = normalize_rule_status(result.get('status'))
        if status == RuleStatus.PASS:
            verified.append(f"{parameter}: {result.get('message', 'evidence detected')}")
        elif status == RuleStatus.FAIL:
            failed.append(f"{parameter}: {result.get('message', 'not satisfied')}")
        elif status == RuleStatus.NOT_VERIFIABLE:
            finding = f"{parameter}: {result.get('message', 'not verifiable')}"
            review.append(finding)
            if _is_physical_verification_rule(result):
                physical_unverified.append(finding)
    return {
        'verified': verified,
        'needs_review': review,
        'failed': failed,
        'physical_unverified': physical_unverified,
    }


def _is_usable_evidence(field_data: Dict[str, Any]) -> bool:
    """Require a non-empty value and confidence before reporting an OCR pass."""
    value = field_data.get('value')
    if value is None or not str(value).strip():
        return False
    confidence = field_data.get('confidence')
    return confidence is None or float(confidence) >= 0.6
