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
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def get_applicable_rules(
    all_rules: List[Dict[str, Any]],
    category: str = "UNKNOWN",
    package_type: str = "RETAIL",
    import_status: str = "DOMESTIC",
    product_type: str = "UNKNOWN",
    has_physical_data: bool = False,
) -> List[Dict[str, Any]]:
    """
    Filter the full rule set to only rules applicable to the given context.

    Args:
        all_rules: Complete list of rule dicts (from DB or JSON).
        category: Product category — FOOD, COSMETIC, or UNKNOWN.
        package_type: RETAIL or WHOLESALE.
        import_status: DOMESTIC or IMPORTED.
        has_physical_data: Whether manual measurement data was provided.

    Returns:
        List of applicable rule dicts.
    """
    applicable = []

    for rule in all_rules:
        # Skip inactive rules
        if not rule.get('is_active', True):
            continue

        # --- Category filter ---
        rule_category = rule.get('category', 'ALL').upper()
        if rule_category != 'ALL' and rule_category != category.upper():
            continue

        # --- Package type filter ---
        rule_pkg = rule.get('package_type', 'ALL').upper()
        if rule_pkg != 'ALL' and rule_pkg != package_type.upper():
            continue

        # --- Product type filter ---
        rule_product_type = rule.get('product_type', 'ALL').upper()
        if rule_product_type not in {'ALL', 'UNKNOWN'} and rule_product_type != product_type.upper():
            continue

        # --- Condition filter ---
        condition = rule.get('condition', 'APPLICABLE').upper()

        if condition == 'IMPORTED_ONLY':
            if import_status.upper() != 'IMPORTED':
                continue

        if condition == 'PHYSICAL_ONLY':
            if not has_physical_data:
                continue

        applicable.append(rule)

    logger.info(
        f"Rule applicability: {len(applicable)}/{len(all_rules)} rules applicable "
        f"(category={category}, product_type={product_type}, pkg={package_type}, import={import_status}, "
        f"physical={has_physical_data})"
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
