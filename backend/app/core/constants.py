"""
Canonical Status Constants for Legal Metrology Inspections.
"""
from typing import Optional


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


def normalize_status(status: Optional[str]) -> Optional[str]:
    """Normalize any status string (including legacy hyphenated variants)
    to the canonical underscore representation.
    """
    if not status:
        return None
    cleaned = status.strip().upper().replace("-", "_")
    if cleaned in ("NEEDS_REVIEW", "NOT_VERIFIABLE", "REVIEW"):
        return InspectionStatus.NOT_VERIFIABLE
    if cleaned in ("NON_COMPLIANT", "NONCOMPLIANT"):
        return InspectionStatus.NON_COMPLIANT
    if cleaned == "COMPLIANT":
        return InspectionStatus.COMPLIANT
    if cleaned in ("NOT_APPLICABLE", "NOTAPPLICABLE", "NA"):
        return InspectionStatus.NOT_APPLICABLE
    return CanonicalStatus(cleaned)
