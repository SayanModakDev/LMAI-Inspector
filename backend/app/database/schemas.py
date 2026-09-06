"""
Pydantic schemas for API request/response validation.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


# ---------------------------------------------------------------------------
# Scan / Inspection Schemas
# ---------------------------------------------------------------------------
class ScanResponse(BaseModel):
    """Response from POST /api/scan."""
    inspection_id: int
    category: Optional[str] = None
    category_confidence: Optional[float] = None
    package_type: str = "RETAIL"
    import_status: str = "DOMESTIC"
    product_name: Optional[str] = None
    brand: Optional[str] = None
    product_type: Optional[str] = None
    brand: Optional[str] = None
    product_type: Optional[str] = None
    extracted_fields: dict = {}
    rule_results: List[dict] = []
    overall_result: Optional[str] = None
    priority: str = "MEDIUM"
    evidence: List[dict] = []
    review_notes: List[str] = []
    ocr_text: Optional[str] = None
    ocr_data: Optional[List[dict]] = None
    image_url: Optional[str] = None
    images: List[dict] = []
    barcode_result: Optional[dict] = None


class InspectionDetail(BaseModel):
    """Full inspection detail for GET /api/inspection/{id}."""
    id: int
    inspection_date: Optional[datetime] = None
    product_name: Optional[str] = None
    category: Optional[str] = None
    category_confidence: Optional[float] = None
    package_type: str = "RETAIL"
    import_status: str = "DOMESTIC"
    quantity_type: Optional[str] = None
    overall_result: Optional[str] = None
    priority: str = "MEDIUM"
    image_path: Optional[str] = None
    inspector_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    product: Optional[dict] = None
    images: List[dict] = []
    ocr_result: Optional[dict] = None
    extracted_fields: List[dict] = []
    rule_results: List[dict] = []
    evidence: List[dict] = []
    report: Optional[dict] = None

    class Config:
        from_attributes = True


class InspectionSummary(BaseModel):
    """Summary for history list."""
    id: int
    inspection_date: Optional[datetime] = None
    product_name: Optional[str] = None
    category: Optional[str] = None
    package_type: Optional[str] = "RETAIL"
    import_status: Optional[str] = "DOMESTIC"
    overall_result: Optional[str] = None
    priority: str = "MEDIUM"
    inspector_name: Optional[str] = None
    created_at: Optional[datetime] = None
    report: Optional[dict] = None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Manual Input
# ---------------------------------------------------------------------------
class ManualInputRequest(BaseModel):
    """POST /api/manual-input body."""
    inspection_id: int
    actual_measured_weight: Optional[float] = None
    actual_weight_unit: Optional[str] = None
    measurement_source: Optional[str] = "MANUAL_SCALE"
    inspector_notes: Optional[str] = None
    # Category-aware declaration corrections. Values are stored as MANUAL
    # evidence while earlier OCR evidence remains traceable in evidence_items.
    field_overrides: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
class DashboardStats(BaseModel):
    """Dashboard summary statistics."""
    total_inspections: int = 0
    compliant: int = 0
    non_compliant: int = 0
    not_verifiable: int = 0
    not_applicable: int = 0
    food_inspections: int = 0
    cosmetic_inspections: int = 0
    recent_inspections: List[dict] = []
    common_failed_parameters: List[dict] = []


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
class RuleSchema(BaseModel):
    """Schema for a single rule from the Rule Matrix."""
    rule_id: str
    parameter: str
    category: str
    package_type: str = "ALL"
    condition: str = "APPLICABLE"
    rule_reference: Optional[str] = None
    source_document: Optional[str] = None
    rule_version: str = "PENDING_VERIFICATION"
    effective_from: Optional[str] = None
    effective_until: Optional[str] = None
    required: bool = True
    what_to_extract: Optional[str] = None
    validation_method: Optional[str] = None
    verification_type: Optional[str] = None
    result_type: str = "PASS_FAIL"
    severity: str = "HIGH"
    exception: Optional[str] = None
    evidence_required: bool = True
    source_authority: Optional[str] = None
    source_url: Optional[str] = None
    source_link: Optional[str] = None
    rule_reference_status: str = "PENDING_VERIFICATION"
    regulatory_source: Optional[str] = "LEGAL_METROLOGY"


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------
class CategoryInfo(BaseModel):
    """Category information."""
    name: str
    display_name: str
    description: str
    supported: bool = True


# ---------------------------------------------------------------------------
# Generic Responses
# ---------------------------------------------------------------------------
class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    success: bool = True
    data: Optional[Any] = None
