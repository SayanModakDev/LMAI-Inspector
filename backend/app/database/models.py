"""
SQLAlchemy ORM models for all database tables.

Tables:
    - users: Inspector accounts
    - inspections: Core inspection record
    - products: Product details per inspection
    - ocr_results: Raw OCR output storage
    - extracted_fields: Parsed declarations
    - rules: Configurable rule matrix (synced from JSON)
    - rule_results: Per-rule validation outcome
    - evidence: Bounding box / visual evidence
    - reports: Generated PDF report metadata
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime,
    ForeignKey, JSON, Enum as SAEnum,
)
from sqlalchemy.orm import relationship
from app.database.connection import Base


# ---------------------------------------------------------------------------
# USERS
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(50), default="inspector")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspections = relationship("Inspection", back_populates="inspector_user")


# ---------------------------------------------------------------------------
# INSPECTIONS
# ---------------------------------------------------------------------------
class Inspection(Base):
    __tablename__ = "inspections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inspection_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    product_name = Column(String(255), nullable=True)
    brand = Column(String(255), nullable=True)
    product_type = Column(String(100), nullable=True)
    category = Column(String(50), nullable=True)  # FOOD, COSMETIC, UNKNOWN
    category_confidence = Column(Float, nullable=True)
    package_type = Column(String(50), default="RETAIL")  # RETAIL, WHOLESALE, etc.
    import_status = Column(String(50), default="DOMESTIC")  # DOMESTIC, IMPORTED
    quantity_type = Column(String(50), nullable=True)  # WEIGHT, VOLUME, COUNT, LENGTH, AREA
    overall_result = Column(String(50), nullable=True)  # COMPLIANT, NON-COMPLIANT, NOT_VERIFIABLE
    priority = Column(String(20), default="MEDIUM")  # LOW, MEDIUM, HIGH
    image_path = Column(String(500), nullable=True)
    processed_image_path = Column(String(500), nullable=True)
    inspector_name = Column(String(255), default="Default Inspector")
    inspector_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)
    regulatory_snapshot = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    inspector_user = relationship("User", back_populates="inspections")
    product = relationship("Product", back_populates="inspection", uselist=False, cascade="all, delete-orphan")
    ocr_result = relationship("OCRResult", back_populates="inspection", uselist=False, cascade="all, delete-orphan")
    extracted_fields = relationship("ExtractedField", back_populates="inspection", cascade="all, delete-orphan")
    rule_results = relationship("RuleResult", back_populates="inspection", cascade="all, delete-orphan")
    evidence_items = relationship("Evidence", back_populates="inspection", cascade="all, delete-orphan")
    report = relationship("Report", back_populates="inspection", uselist=False, cascade="all, delete-orphan")
    images = relationship("InspectionImage", back_populates="inspection", cascade="all, delete-orphan", order_by="InspectionImage.image_index")


class InspectionImage(Base):
    """One uploaded or camera-captured image belonging to an inspection."""

    __tablename__ = "inspection_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id"), nullable=False)
    image_index = Column(Integer, nullable=False)
    file_name = Column(String(500), nullable=False)
    processed_file_name = Column(String(500), nullable=True)
    source = Column(String(30), default="UPLOAD")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspection = relationship("Inspection", back_populates="images")


# ---------------------------------------------------------------------------
# PRODUCTS
# ---------------------------------------------------------------------------
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id"), nullable=False)
    product_name = Column(String(255), nullable=True)
    brand = Column(String(255), nullable=True)
    generic_name = Column(String(255), nullable=True)
    manufacturer = Column(String(500), nullable=True)
    packer = Column(String(500), nullable=True)
    importer = Column(String(500), nullable=True)
    address = Column(Text, nullable=True)
    country_of_origin = Column(String(100), nullable=True)
    declared_net_quantity_value = Column(String(50), nullable=True)
    declared_net_quantity_unit = Column(String(20), nullable=True)
    mrp = Column(String(50), nullable=True)
    manufacture_date = Column(String(100), nullable=True)
    packing_date = Column(String(100), nullable=True)
    import_date = Column(String(100), nullable=True)
    best_before = Column(String(100), nullable=True)
    use_by = Column(String(100), nullable=True)
    consumer_care = Column(Text, nullable=True)
    unit_sale_price = Column(String(50), nullable=True)
    ingredients = Column(Text, nullable=True)
    dimensions = Column(String(100), nullable=True)
    # Physical measurement fields — NEVER populated from OCR
    actual_measured_weight = Column(Float, nullable=True)
    actual_weight_unit = Column(String(20), nullable=True)
    measurement_source = Column(String(50), nullable=True)  # MANUAL_SCALE, etc.
    measurement_timestamp = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspection = relationship("Inspection", back_populates="product")


# ---------------------------------------------------------------------------
# OCR RESULTS
# ---------------------------------------------------------------------------
class OCRResult(Base):
    __tablename__ = "ocr_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id"), nullable=False)
    raw_text = Column(Text, nullable=True)
    ocr_data = Column(JSON, nullable=True)  # Full OCR output with bboxes + confidence
    ocr_engine = Column(String(50), default="PaddleOCR")
    processing_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspection = relationship("Inspection", back_populates="ocr_result")


# ---------------------------------------------------------------------------
# EXTRACTED FIELDS
# ---------------------------------------------------------------------------
class ExtractedField(Base):
    __tablename__ = "extracted_fields"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id"), nullable=False)
    field_name = Column(String(100), nullable=False)  # e.g., MRP, NET_QUANTITY
    field_value = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    source = Column(String(50), default="OCR")  # OCR, MANUAL
    extraction_method = Column(String(100), nullable=True)
    bbox = Column(JSON, nullable=True)  # [x1, y1, x2, y2]
    source_image_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspection = relationship("Inspection", back_populates="extracted_fields")


# ---------------------------------------------------------------------------
# RULES (Rule Matrix — synced from JSON config)
# ---------------------------------------------------------------------------
class Rule(Base):
    __tablename__ = "rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(String(50), unique=True, nullable=False)  # e.g., PC-F-001
    parameter = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)  # FOOD, COSMETIC, ALL
    package_type = Column(String(50), default="ALL")
    product_type = Column(String(100), default="ALL")
    regulatory_source = Column(String(100), default="LEGAL_METROLOGY")
    condition = Column(String(50), default="APPLICABLE")
    rule_reference = Column(String(255), nullable=True)
    source_document = Column(String(500), nullable=True)
    rule_version = Column(String(50), default="PENDING_VERIFICATION")
    effective_from = Column(String(20), nullable=True)
    effective_until = Column(String(20), nullable=True)
    required = Column(Boolean, default=True)
    what_to_extract = Column(String(100), nullable=True)
    validation_method = Column(String(100), nullable=True)
    verification_type = Column(String(50), nullable=True)  # IMAGE_VERIFIABLE, etc.
    result_type = Column(String(50), default="PASS_FAIL")
    severity = Column(String(20), default="HIGH")  # LOW, MEDIUM, HIGH
    exception = Column(Text, nullable=True)
    evidence_required = Column(Boolean, default=True)
    source_link = Column(String(500), nullable=True)
    detection_method = Column(String(100), nullable=True)
    visual_or_text = Column(String(30), default="TEXT")
    source_authority = Column(String(255), nullable=True)
    source_url = Column(String(500), nullable=True)
    rule_reference_status = Column(String(50), default="PENDING_VERIFICATION")
    instrument = Column(String(255), nullable=True)
    citation = Column(String(255), nullable=True)
    citation_text = Column(Text, nullable=True)
    verification_status = Column(String(50), nullable=True)
    version_date = Column(String(20), nullable=True)
    effective_date = Column(String(20), nullable=True)
    publication_date = Column(String(20), nullable=True)
    applicability = Column(String(255), nullable=True)
    screening_scope = Column(Text, nullable=True)
    physical_scope = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# RULE RESULTS
# ---------------------------------------------------------------------------
class RuleResult(Base):
    __tablename__ = "rule_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id"), nullable=False)
    rule_id = Column(String(50), nullable=False)
    parameter = Column(String(100), nullable=False)
    status = Column(String(30), nullable=False)  # PASS, FAIL, NOT_APPLICABLE, NOT_VERIFIABLE
    message = Column(Text, nullable=True)
    evidence_data = Column(JSON, nullable=True)  # Extracted evidence details
    rule_version = Column(String(50), nullable=True)
    regulatory_source = Column(String(100), nullable=True)
    rule_reference = Column(String(255), nullable=True)
    rule_reference_status = Column(String(50), nullable=True)
    citation = Column(String(255), nullable=True)
    verification_status = Column(String(50), nullable=True)
    review_required = Column(Boolean, default=False)
    inspector_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspection = relationship("Inspection", back_populates="rule_results")


# ---------------------------------------------------------------------------
# EVIDENCE
# ---------------------------------------------------------------------------
class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id"), nullable=False)
    rule_id = Column(String(50), nullable=True)
    parameter = Column(String(100), nullable=True)
    evidence_type = Column(String(50), default="OCR_TEXT")  # OCR_TEXT, BBOX, IMAGE_CROP
    text_content = Column(Text, nullable=True)
    bbox = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspection = relationship("Inspection", back_populates="evidence_items")


# ---------------------------------------------------------------------------
# REPORTS
# ---------------------------------------------------------------------------
class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inspection_id = Column(Integer, ForeignKey("inspections.id"), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=False)
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    inspection = relationship("Inspection", back_populates="report")
