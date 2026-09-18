"""
Strict Pydantic schemas for Gemini structured JSON output in Legal Metrology Inspections.
Enforces typed declarations, provenance tokens, and package context.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class SourceEvidence(BaseModel):
    """Traceable link to OCR evidence bounding boxes and token IDs."""
    image_index: int = Field(description="Zero-based image index from uploaded package panels")
    token_ids: List[int] = Field(default_factory=list, description="IDs of OCR tokens that form this evidence")
    raw_text: str = Field(description="Exact raw text detected on the package label")
    bbox: Optional[List[float]] = Field(default=None, description="Bounding box [x1, y1, x2, y2] if available")
    ocr_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence of the source OCR tokens")


class CandidateValue(BaseModel):
    """Alternative candidate value considered for a declaration field."""
    value: str = Field(description="Candidate printed value as found on the package")
    normalized_value: Optional[str] = Field(default=None, description="Standardized form of the candidate value")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score for this candidate")
    source_evidence: List[SourceEvidence] = Field(default_factory=list, description="Evidence supporting this candidate")
    notes: Optional[str] = Field(default=None, description="Reason this candidate was considered or deprecated")


class ResolvedDeclaration(BaseModel):
    """A canonically resolved packaged-commodity declaration with strict evidence grounding."""
    field: str = Field(description="Canonical field name, e.g. NET_QUANTITY, MRP, MANUFACTURER_NAME, etc.")
    value: Optional[str] = Field(default=None, description="Resolved printed declaration value")
    normalized_value: Optional[str] = Field(default=None, description="Normalized representation (e.g. standard units or numbers)")
    status: str = Field(
        default="NOT_FOUND",
        description="Resolution status: 'RESOLVED', 'CONFLICT', or 'NOT_FOUND'",
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score of resolution (0.0 to 1.0)")
    source_evidence: List[SourceEvidence] = Field(
        default_factory=list,
        description="Traceable OCR evidence supporting this resolution",
    )
    alternatives: List[CandidateValue] = Field(
        default_factory=list,
        description="Other competing candidates found on the package",
    )
    resolution_note: Optional[str] = Field(
        default=None,
        description="Short factual note explaining the association or why conflict/not_found was declared",
    )

    @model_validator(mode="before")
    @classmethod
    def _set_default_status(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "status" not in data:
                data["status"] = "RESOLVED" if data.get("value") else "NOT_FOUND"
        return data


class PackageContext(BaseModel):
    """Automated package scope and classification inference derived from package evidence."""
    category: str = Field(default="UNKNOWN", description="Product category: FOOD, COSMETIC, HOUSEHOLD, etc.")
    product_type: str = Field(default="UNKNOWN", description="Specific commodity type: e.g. SALT, BISCUIT, SHAMPOO, OIL")
    package_type: str = Field(default="NOT_DETECTED", description="RETAIL, WHOLESALE, or NOT_DETECTED")
    import_status: str = Field(default="NOT_DETECTED", description="DOMESTIC, IMPORTED, or NOT_DETECTED")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall classification confidence")
    reasoning: Optional[str] = Field(default=None, description="Factual textual basis for inferred context")


class LLMExtractionResult(BaseModel):
    """Complete structured output from Gemini Semantic Evidence Resolver."""
    resolved_declarations: List[ResolvedDeclaration] = Field(
        default_factory=list,
        description="List of resolved declaration parameters",
    )
    package_context: PackageContext = Field(
        default_factory=PackageContext,
        description="Inferred package category, type, and scope",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Factual overview of panel analysis without legal compliance opinions",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_declarations(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "declarations" in data and not data.get("resolved_declarations"):
                decls = data.pop("declarations")
                if isinstance(decls, dict):
                    data["resolved_declarations"] = list(decls.values())
                elif isinstance(decls, list):
                    data["resolved_declarations"] = decls
        return data

    @property
    def declarations(self) -> Dict[str, ResolvedDeclaration]:
        return {d.field: d for d in self.resolved_declarations}

