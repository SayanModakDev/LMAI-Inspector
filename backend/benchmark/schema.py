"""
Strict Pydantic schemas for the LMAI Inspector Accuracy Benchmark & Evaluation Framework.
Defines ground-truth structures, per-case evaluations, and aggregated metric reports.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Ground Truth Dataset Schemas
# ---------------------------------------------------------------------------

class ExpectedDeclaration(BaseModel):
    """Ground truth specification for a single package declaration parameter."""
    value: Optional[str] = Field(
        default=None,
        description="Verified printed text value on the package (or None if not declared)",
    )
    required: bool = Field(
        default=True,
        description="Whether this declaration is legally required for this commodity case",
    )
    normalized_value: Optional[str] = Field(
        default=None,
        description="Optional explicitly provided canonical normalized form",
    )
    aliases: Optional[List[str]] = Field(
        default=None,
        description="Alternative acceptable ground-truth surface variations",
    )
    unit: Optional[str] = Field(
        default=None,
        description="Expected unit of measurement where applicable (e.g. g, ml, kg)",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Factual annotation or physical inspection context",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_from_primitive(cls, data: Any) -> Any:
        """Allow shorthand syntax where a string value or dict is provided."""
        if isinstance(data, str):
            return {"value": data, "required": True}
        return data


class ExpectedContext(BaseModel):
    """Ground truth expected regulatory classification context."""
    category: str = Field(
        default="UNKNOWN",
        description="Expected canonical commodity category: FOOD, COSMETIC, HOUSEHOLD, etc.",
    )
    product_type: Optional[str] = Field(
        default="UNKNOWN",
        description="Expected specific product subtype: e.g. BISCUIT, SALT, LOTION",
    )
    package_type: str = Field(
        default="NOT_DETECTED",
        description="Expected package context: RETAIL, WHOLESALE, or NOT_DETECTED",
    )
    import_status: str = Field(
        default="NOT_DETECTED",
        description="Expected origin status: DOMESTIC, IMPORTED, or NOT_DETECTED",
    )


class BenchmarkCase(BaseModel):
    """A single benchmark test package containing verified ground truth."""
    case_id: str = Field(
        description="Unique benchmark identifier, e.g. 'PKG001'",
    )
    product_name: str = Field(
        description="Display name of the benchmark commodity",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of package characteristics and panel condition",
    )
    images: List[str] = Field(
        default_factory=list,
        description="Paths to package panel images relative to benchmark_data or project root",
    )
    expected_context: ExpectedContext = Field(
        default_factory=ExpectedContext,
        description="Verified ground truth regulatory context",
    )
    expected_declarations: Dict[str, ExpectedDeclaration] = Field(
        default_factory=dict,
        description="Map of canonical declaration parameter name to expected declaration",
    )
    expected_rules: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of Rule ID to verified expected rule status (PASS, FAIL, NOT_VERIFIABLE, NOT_APPLICABLE)",
    )
    expected_overall_result: Optional[str] = Field(
        default=None,
        description="Expected overall inspection result: COMPLIANT, NON_COMPLIANT, or NOT_VERIFIABLE",
    )
    notes: List[str] = Field(
        default_factory=list,
        description="Annotator notes regarding physical inspection or ambiguous features",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Difficulty and condition tags (e.g. clean, blurry, multipack, food, cosmetic)",
    )
    mock_ocr_result: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional recorded/synthetic OCR items and raw_text for reproducible offline testing",
    )
    mock_gemini_response: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional recorded/synthetic Gemini structured extraction for reproducible offline testing",
    )


class BenchmarkDataset(BaseModel):
    """Container for benchmark suite evaluation cases."""
    version: str = Field(default="1.0.0", description="Dataset schema version")
    dataset_name: str = Field(default="LMAI Benchmark Dataset", description="Dataset name")
    description: Optional[str] = Field(default=None, description="Dataset overview")
    cases: List[BenchmarkCase] = Field(
        default_factory=list,
        description="List of packaged commodity benchmark cases",
    )


# ---------------------------------------------------------------------------
# Evaluation Output Schemas
# ---------------------------------------------------------------------------

class DeclarationEvaluation(BaseModel):
    """Result of evaluating a single declaration field."""
    field: str
    expected_value: Optional[str] = None
    expected_normalized: Optional[str] = None
    predicted_value: Optional[str] = None
    predicted_normalized: Optional[str] = None
    expected_present: bool = False
    predicted_present: bool = False
    required: bool = True
    exact_match: bool = False
    normalized_match: bool = False
    grounding_status: Optional[str] = None
    grounding_strategy: Optional[str] = None
    grounding_score: float = 0.0
    error_category: Optional[str] = None
    resolution_source: Optional[str] = None
    notes: Optional[str] = None


class RuleEvaluation(BaseModel):
    """Result of evaluating a single rule status."""
    rule_id: str
    parameter: Optional[str] = None
    expected_status: Optional[str] = None
    predicted_status: Optional[str] = None
    match: bool = False
    is_physical: bool = False
    is_blocking: bool = False
    error_category: Optional[str] = None
    reason: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None


class CaseEvaluation(BaseModel):
    """Complete evaluation results for a single benchmark case."""
    case_id: str
    product_name: str
    tags: List[str] = Field(default_factory=list)
    image_count: int = 0
    context_evaluation: Dict[str, Any] = Field(default_factory=dict)
    declaration_evaluations: Dict[str, DeclarationEvaluation] = Field(default_factory=dict)
    rule_evaluations: Dict[str, RuleEvaluation] = Field(default_factory=dict)
    expected_overall_result: Optional[str] = None
    predicted_overall_result: Optional[str] = None
    overall_result_match: Optional[bool] = None
    timings_ms: Dict[str, Any] = Field(default_factory=dict)
    llm_metadata: Dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    clean_inspection: bool = False
    errors: List[Dict[str, Any]] = Field(default_factory=list)
