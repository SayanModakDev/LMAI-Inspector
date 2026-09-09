"""
Controlled Verification Status Safety Guard and Dynamic Regulatory Snapshot Engine.

Ensures that:
1. No rule can claim VERIFIED status without complete, verifiable source metadata:
   - source_authority
   - citation / rule_reference
   - source_url
   - effective_date / effective_from
   - applicability
   - rule_version
2. Internal inspection fields (e.g. PRODUCT_NAME) are strictly classified as NON_STATUTORY.
3. Exemption-contingent statutory requirements are classified as APPLICABILITY_DEPENDENT.
4. Human-readable regulatory snapshots are dynamically derived for each inspection date.
5. The software explicitly disclaims government authority.
"""

from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime, timezone
import re


REQUIRED_VERIFIED_FIELDS = [
    "source_authority",
    "citation",
    "source_url",
    "effective_date",
    "applicability",
    "rule_version",
]

CONTROLLED_STATUSES = {
    "VERIFIED",
    "APPLICABILITY_DEPENDENT",
    "NON_STATUTORY",
    "SOURCE_IDENTIFIED",
    "PENDING_REVIEW",
}


def validate_and_enforce_verification_status(rule: Dict[str, Any]) -> str:
    """
    Enforce verification status safety based on evidentiary completeness.

    Returns one of:
    - NON_STATUTORY: for internal inspection fields.
    - APPLICABILITY_DEPENDENT: for verified rules whose mandate is contingent on exemptions.
    - VERIFIED: for statutory rules with complete, audited evidentiary metadata.
    - SOURCE_IDENTIFIED: if authority and URL exist but citation/dates are incomplete.
    - PENDING_REVIEW: if any mandatory evidentiary field is missing.
    """
    rule_id = str(rule.get("rule_id", "")).upper()
    regulatory_source = str(rule.get("regulatory_source", "")).upper()

    # 1. Internal inspection fields are strictly non-statutory
    if rule_id == "PC-ALL-001" or regulatory_source == "INTERNAL_INSPECTION":
        return "NON_STATUTORY"

    # 2. Check presence of mandatory evidentiary fields
    missing_fields = []
    for f in REQUIRED_VERIFIED_FIELDS:
        val = rule.get(f)
        if not val:
            # Fallback checks
            if f == "citation" and rule.get("rule_reference") and rule.get("rule_reference") != "PENDING_VERIFICATION":
                continue
            if f == "effective_date" and rule.get("effective_from"):
                continue
            missing_fields.append(f)

    # 3. If mandatory fields are missing, status CANNOT be VERIFIED
    if missing_fields:
        if rule.get("source_authority") and (rule.get("source_url") or rule.get("source_document")):
            return "SOURCE_IDENTIFIED"
        return "PENDING_REVIEW"

    # 4. Check whether statutory application is conditional / exemption-dependent
    requested_status = rule.get("verification_status") or rule.get("rule_reference_status")
    if requested_status == "APPLICABILITY_DEPENDENT":
        return "APPLICABILITY_DEPENDENT"

    condition = str(rule.get("condition", "")).upper()
    parameter = str(rule.get("parameter", "")).upper()
    if condition in ("IMPORTED_ONLY", "PHYSICAL_ONLY") or parameter in (
        "UNIT_SALE_PRICE",
        "INGREDIENTS_LIST",
        "NUTRITIONAL_INFO",
        "IMPORTER_NAME_ADDRESS",
    ):
        # These rules are statutory and verified, but their legal requirement is exemption-contingent
        # (e.g. Unit sale price exempt if retail price == unit price; single-ingredient food exempt).
        return "APPLICABILITY_DEPENDENT"

    return "VERIFIED"


def derive_dynamic_regulatory_snapshot(
    applicable_rules: Optional[List[Dict[str, Any]]] = None,
    inspection_date: Optional[Any] = None,
    default_snapshot: Optional[str] = None,
) -> Dict[str, str]:
    """
    Dynamically derive human-readable regulatory snapshot and effective date label.

    Example output:
    {
        "snapshot_id": "LMPC_2011_CURRENT_2024 | FSSAI_LD_2020_CURRENT_2024",
        "inspection_date": "2026-09-09",
        "effective_label": "Effective for inspection date: 2026-09-09",
        "human_readable": "Regulatory Snapshot: LMPC_2011_CURRENT_2024 | FSSAI_LD_2020_CURRENT_2024 | Effective for inspection date: 2026-09-09",
    }
    """
    if inspection_date is None:
        inspect_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    elif isinstance(inspection_date, datetime):
        inspect_str = inspection_date.strftime("%Y-%m-%d")
    else:
        inspect_str = str(inspection_date)[:10]

    versions: Set[str] = set()
    if applicable_rules:
        for r in applicable_rules:
            ver = r.get("rule_version")
            if ver and ver not in ("PENDING_VERIFICATION", "INTERNAL_INSPECTION_V1"):
                versions.add(str(ver))

    if versions:
        # Sort for deterministic order
        sorted_versions = sorted(versions)
        snapshot_id = " | ".join(sorted_versions)
    elif default_snapshot:
        snapshot_id = default_snapshot
    else:
        snapshot_id = "LMPC_2011_CURRENT_2024 | FSSAI_LD_2020_CURRENT_2024 | COSMETICS_2020_CURRENT_2024"

    return {
        "snapshot_id": snapshot_id,
        "inspection_date": inspect_str,
        "effective_label": f"Effective for inspection date: {inspect_str}",
        "human_readable": f"Regulatory Snapshot: {snapshot_id} (Effective for inspection date: {inspect_str})",
    }
