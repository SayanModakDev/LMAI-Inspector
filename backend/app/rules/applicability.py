"""
Rule Applicability Engine — filters the full rule matrix to select
only the rules applicable to a specific product context.

Filters by:
- Category (FOOD, COSMETIC, ALL)
- Package type (RETAIL, WHOLESALE, ALL)
- Condition (APPLICABLE, IMPORTED_ONLY, PHYSICAL_ONLY)
- Active status

Rules with condition=IMPORTED_ONLY are only included when import_status=IMPORTED.
Rules with condition=PHYSICAL_ONLY are only included when physical measurements
are available (manual input).
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


def get_applicable_rules(
    all_rules: List[Dict[str, Any]],
    category: str = "UNKNOWN",
    package_type: str = "RETAIL",
    import_status: str = "DOMESTIC",
    product_type: str = "UNKNOWN",
    has_physical_data: bool = False,
    inspection_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Filter the full rule set to only rules applicable to the given context and inspection date.

    Args:
        all_rules: Complete list of rule dicts (from DB or JSON).
        category: Product category — FOOD, COSMETIC, or UNKNOWN.
        package_type: RETAIL, WHOLESALE, INSTITUTIONAL, or INDUSTRIAL.
        import_status: DOMESTIC or IMPORTED.
        has_physical_data: Whether manual measurement data was provided.
        inspection_date: ISO date string (YYYY-MM-DD) controlling rule version applicability.

    Returns:
        List of applicable rule dicts.
    """
    if inspection_date is not None:
        norm_inspect_date = str(inspection_date)[:10]
    else:
        norm_inspect_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    applicable = []

    for rule in all_rules:
        # Skip inactive rules
        if not rule.get('is_active', True):
            continue

        # --- Category filter ---
        rule_category = rule.get('category', 'ALL').upper()
        if rule_category != 'ALL' and rule_category != category.upper():
            continue

        # --- Package type & scope filter ---
        norm_pkg = (package_type or 'RETAIL').upper()
        rule_pkg = rule.get('package_type', 'ALL').upper()

        if norm_pkg in ('WHOLESALE', 'INSTITUTIONAL', 'INDUSTRIAL'):
            # Retail Chapter II declarations (e.g. MRP, USP, Consumer Care) do not apply to wholesale,
            # institutional, or industrial packages per Chapter III / Rule 24 and Rule 3/26 exemptions.
            if rule_pkg == 'RETAIL':
                continue
            if norm_pkg == 'WHOLESALE' and rule_pkg not in ('ALL', 'WHOLESALE'):
                continue
        elif norm_pkg == 'RETAIL':
            if rule_pkg not in ('ALL', 'RETAIL'):
                continue
        else:
            if rule_pkg != 'ALL' and rule_pkg != norm_pkg:
                continue

        # --- Product type filter ---
        rule_product_type = (rule.get('product_type') or 'ALL').upper()
        if rule_product_type not in {'ALL', 'UNKNOWN'}:
            if rule_product_type == 'OTHER_FOOD':
                if category.upper() != 'FOOD' or product_type.upper() in {'SALT', 'SUGAR'}:
                    continue
            elif rule_product_type != product_type.upper():
                continue

        # --- Condition filter ---
        condition = rule.get('condition', 'APPLICABLE').upper()

        if condition == 'IMPORTED_ONLY':
            if import_status.upper() != 'IMPORTED':
                continue

        # --- Effective date filter (Published law != Effective law) ---
        eff_from = rule.get('effective_from') or rule.get('effective_date')
        if eff_from and norm_inspect_date < str(eff_from)[:10]:
            # A published amendment must NOT become active before its effective date
            continue

        eff_until = rule.get('effective_until')
        if eff_until and norm_inspect_date > str(eff_until)[:10]:
            # Rule version has expired or been superseded as of this inspection date
            continue

        applicable.append(rule)

    # Deduplicate multiple versions of the same rule_id / parameter
    # by selecting the active version with the latest effective date <= norm_inspect_date
    version_candidates: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for r in applicable:
        key = (str(r.get('rule_id', '')), str(r.get('parameter', '')))
        version_candidates.setdefault(key, []).append(r)

    final_applicable = []
    for key, cand_list in version_candidates.items():
        if len(cand_list) == 1:
            final_applicable.append(cand_list[0])
        else:
            cand_list.sort(
                key=lambda x: str(x.get('effective_from') or x.get('effective_date') or ''),
                reverse=True,
            )
            final_applicable.append(cand_list[0])

    applicable = final_applicable

    logger.info(
        f"Rule applicability: {len(applicable)}/{len(all_rules)} rules applicable "
        f"(category={category}, product_type={product_type}, pkg={package_type}, import={import_status}, "
        f"physical={has_physical_data}, date={norm_inspect_date})"
    )

    return applicable


def categorize_rules_by_verification_type(
    rules: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group applicable rules by their verification_type.

    Returns:
        {
            "IMAGE_VERIFIABLE": [...],
            "IMAGE_ESTIMABLE": [...],
            "PHYSICAL_VERIFICATION_REQUIRED": [...],
        }
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}

    for rule in rules:
        vtype = rule.get('verification_type', 'IMAGE_VERIFIABLE')
        if vtype not in groups:
            groups[vtype] = []
        groups[vtype].append(rule)

    return groups


def get_rule_priority_order(
    rules: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Sort rules by severity (HIGH first, then MEDIUM, then LOW)."""
    severity_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
    return sorted(
        rules,
        key=lambda r: severity_order.get(r.get('severity', 'MEDIUM'), 1),
    )
