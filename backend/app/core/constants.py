"""
Canonical Status Constants for Legal Metrology Inspections.
"""
from enum import Enum
from typing import Any, Optional


class CanonicalStatus(str):
    """String subclass representing canonical inspection status while maintaining
    seamless backwards compatibility with hyphenated variants (e.g. NON-COMPLIANT).
    """

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, str):
            return False
        return self.replace("-", "_") == other.replace("-", "_")

    def __hash__(self) -> int:
        return hash(self.replace("-", "_"))


class InspectionStatus:
    COMPLIANT = CanonicalStatus("COMPLIANT")
    NON_COMPLIANT = CanonicalStatus("NON_COMPLIANT")
    NOT_VERIFIABLE = CanonicalStatus("NOT_VERIFIABLE")
    NOT_APPLICABLE = CanonicalStatus("NOT_APPLICABLE")

    ALL = [COMPLIANT, NON_COMPLIANT, NOT_VERIFIABLE, NOT_APPLICABLE]


class RuleStatus(str, Enum):
    """Canonical outcomes emitted by deterministic rule evaluation."""

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_VERIFIABLE = "NOT_VERIFIABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


def normalize_rule_status(status: Any) -> RuleStatus:
    """Map rule, evidence, and legacy display statuses to a rule outcome.

    Unknown, missing, and evidence-only states are conservative: they remain
    unresolved and can never silently become a pass.
    """
    raw_status = getattr(status, "value", status)
    if raw_status is None:
        return RuleStatus.NOT_VERIFIABLE

    cleaned = str(raw_status).strip().upper().replace("-", "_").replace(" ", "_")
    if cleaned in ("PASS", "COMPLIANT"):
        return RuleStatus.PASS
    if cleaned in ("FAIL", "NON_COMPLIANT", "NONCOMPLIANT"):
        return RuleStatus.FAIL
    if cleaned in ("NOT_APPLICABLE", "NOTAPPLICABLE", "NA", "N_A"):
        return RuleStatus.NOT_APPLICABLE
    if cleaned in (
        "NOT_VERIFIABLE",
        "NEEDS_REVIEW",
        "REVIEW",
        "NOT_DETECTED",
        "EVIDENCE_NOT_DETECTED",
        "MANUAL_CHECK",
        "UNKNOWN",
        "UNASSESSED",
        "CONFLICTING_EVIDENCE",
    ):
        return RuleStatus.NOT_VERIFIABLE
    return RuleStatus.NOT_VERIFIABLE


def normalize_status(status: Optional[str]) -> Optional[str]:
    """Normalize any status string (including legacy hyphenated variants)
    to the canonical underscore representation.
    """
    if not status:
        return None
    cleaned = status.strip().upper().replace("-", "_").replace(" ", "_")
    if cleaned in ("NEEDS_REVIEW", "NOT_VERIFIABLE", "REVIEW", "NOT_DETECTED", "MANUAL_CHECK"):
        return InspectionStatus.NOT_VERIFIABLE
    if cleaned in ("NON_COMPLIANT", "NONCOMPLIANT"):
        return InspectionStatus.NON_COMPLIANT
    if cleaned == "COMPLIANT":
        return InspectionStatus.COMPLIANT
    if cleaned in ("NOT_APPLICABLE", "NOTAPPLICABLE", "NA"):
        return InspectionStatus.NOT_APPLICABLE
    return CanonicalStatus(cleaned)
