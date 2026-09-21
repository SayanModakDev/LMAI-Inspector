"""Tests for LMAI Inspector Zero-Data Dashboard Initial State.

Verifies:
1. On a fresh installation with an empty database, every inspection count is 0,
   recent inspections list is empty, and failure occurrences are empty.
2. One COMPLIANT inspection increments compliant count accurately.
3. One REVIEW_REQUIRED inspection increments review_required count accurately.
4. One NON_COMPLIANT inspection increments non_compliant count accurately.
5. Out-of-scope physical verification rules are excluded from screening PASS/FAIL/REVIEW counts
   and from common failed parameters.
6. Dashboard and Inspection History agree on stored data counts.
7. Existing historical inspections remain visible and counted without deletion or corruption.
8. No default mock records or fabricated chart points are generated.
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database.connection import Base, get_db
from app.database import models, schemas
from app.core.constants import InspectionStatus
from app.api.inspections import get_dashboard, get_history, get_canonical_screening_status
from app.main import app


@pytest.fixture
def isolated_db():
    """Create an isolated in-memory SQLite database with fresh schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client_with_db(isolated_db):
    """FastAPI TestClient with isolated database override."""
    def override_get_db():
        try:
            yield isolated_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_requirement_1_and_2_fresh_empty_database_initial_state(isolated_db, client_with_db):
    """On a fresh installation with an empty database:
    - Every inspection-related dashboard count is 0.
    - No placeholder values, mock statistics, fake recent inspections, or invented failure data.
    """
    stats = get_dashboard(isolated_db)

    assert stats.total_inspections == 0
    assert stats.compliant == 0
    assert stats.non_compliant == 0
    assert stats.review_required == 0
    assert stats.not_verifiable == 0
    assert stats.not_applicable == 0
    assert stats.food_inspections == 0
    assert stats.cosmetic_inspections == 0
    assert stats.recent_inspections == []
    assert stats.common_failed_parameters == []

    # Verify HTTP endpoint returns identical clean zero state
    response = client_with_db.get("/api/dashboard")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_inspections"] == 0
    assert payload["compliant"] == 0
    assert payload["non_compliant"] == 0
    assert payload["review_required"] == 0
    assert payload["recent_inspections"] == []
    assert payload["common_failed_parameters"] == []


def test_requirement_4_and_5_one_compliant_inspection(isolated_db, client_with_db):
    """Adding one COMPLIANT inspection updates Dashboard counts accurately."""
    inspection = models.Inspection(
        product_name="Dabur Honey 250g",
        category="FOOD",
        overall_result="COMPLIANT",
        package_type="RETAIL",
        import_status="DOMESTIC",
        created_at=datetime.now(timezone.utc),
    )
    isolated_db.add(inspection)
    isolated_db.flush()

    # Add passed rule results
    for idx, param in enumerate(["PRODUCT_NAME", "MRP", "NET_QUANTITY", "MANUFACTURER_NAME"]):
        isolated_db.add(models.RuleResult(
            inspection_id=inspection.id,
            rule_id=f"PC-RULE-{idx + 1:03d}",
            parameter=param,
            status="PASS",
            message="Compliant declaration detected.",
            evidence_data={"binary": 1},
        ))
    isolated_db.commit()

    stats = get_dashboard(isolated_db)
    assert stats.total_inspections == 1
    assert stats.compliant == 1
    assert stats.non_compliant == 0
    assert stats.review_required == 0
    assert stats.food_inspections == 1
    assert len(stats.recent_inspections) == 1
    assert stats.recent_inspections[0]["id"] == inspection.id
    assert stats.recent_inspections[0]["result"] == "COMPLIANT"
    assert stats.common_failed_parameters == []

    # API Endpoint check
    response = client_with_db.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["total_inspections"] == 1
    assert data["compliant"] == 1
    assert data["non_compliant"] == 0
    assert data["review_required"] == 0


def test_requirement_4_and_5_one_review_required_inspection(isolated_db, client_with_db):
    """Adding one REVIEW_REQUIRED inspection updates Dashboard counts accurately."""
    inspection = models.Inspection(
        product_name="Generic Packaging Tube",
        category="COSMETIC",
        overall_result="REVIEW_REQUIRED",
        package_type="RETAIL",
        import_status="DOMESTIC",
        created_at=datetime.now(timezone.utc),
    )
    isolated_db.add(inspection)
    isolated_db.flush()

    isolated_db.add(models.RuleResult(
        inspection_id=inspection.id,
        rule_id="PC-ALL-001",
        parameter="PRODUCT_NAME",
        status="PASS",
        message="Product name detected.",
        evidence_data={"binary": 1},
    ))
    isolated_db.add(models.RuleResult(
        inspection_id=inspection.id,
        rule_id="PC-ALL-006",
        parameter="CONSUMER_CARE",
        status="NOT_VERIFIABLE",
        message="Consumer care address could not be verified with high confidence.",
        evidence_data={"binary": None},
    ))
    isolated_db.commit()

    stats = get_dashboard(isolated_db)
    assert stats.total_inspections == 1
    assert stats.compliant == 0
    assert stats.non_compliant == 0
    assert stats.review_required == 1
    assert stats.cosmetic_inspections == 1
    assert len(stats.recent_inspections) == 1
    assert stats.recent_inspections[0]["result"] == "REVIEW_REQUIRED"


def test_requirement_4_and_5_one_non_compliant_inspection(isolated_db, client_with_db):
    """Adding one NON_COMPLIANT inspection updates Dashboard counts and failure telemetry."""
    inspection = models.Inspection(
        product_name="Defective Label Carton",
        category="FOOD",
        overall_result="NON_COMPLIANT",
        package_type="RETAIL",
        import_status="DOMESTIC",
        created_at=datetime.now(timezone.utc),
    )
    isolated_db.add(inspection)
    isolated_db.flush()

    isolated_db.add(models.RuleResult(
        inspection_id=inspection.id,
        rule_id="PC-ALL-002",
        parameter="DECLARED_NET_QUANTITY",
        status="FAIL",
        message="Missing standard measurement unit.",
        evidence_data={"binary": 0},
    ))
    isolated_db.commit()

    stats = get_dashboard(isolated_db)
    assert stats.total_inspections == 1
    assert stats.compliant == 0
    assert stats.non_compliant == 1
    assert stats.review_required == 0
    assert len(stats.common_failed_parameters) == 1
    assert stats.common_failed_parameters[0]["parameter"] == "DECLARED_NET_QUANTITY"
    assert stats.common_failed_parameters[0]["count"] == 1


def test_requirement_6_exclude_out_of_scope_physical_verification(isolated_db):
    """Physical verification rules must NOT inflate failure telemetry or screening fail counts."""
    inspection = models.Inspection(
        product_name="Clean Label Biscuit",
        category="FOOD",
        overall_result="COMPLIANT",
        package_type="RETAIL",
        import_status="DOMESTIC",
        created_at=datetime.now(timezone.utc),
    )
    isolated_db.add(inspection)
    isolated_db.flush()

    # Applicable image rules pass
    isolated_db.add(models.RuleResult(
        inspection_id=inspection.id,
        rule_id="PC-ALL-001",
        parameter="PRODUCT_NAME",
        status="PASS",
        message="Declaration found",
        evidence_data={"binary": 1},
    ))
    # Caliper / physical measurement rules recorded out of scope
    isolated_db.add(models.RuleResult(
        inspection_id=inspection.id,
        rule_id="PC-ALL-012",
        parameter="ACTUAL_NET_CONTENT",
        status="OUT_OF_SCOPE_PHYSICAL_VERIFICATION",
        message="Physical check required",
        evidence_data={"verification_type": "PHYSICAL_VERIFICATION_REQUIRED"},
    ))
    isolated_db.add(models.RuleResult(
        inspection_id=inspection.id,
        rule_id="PC-ALL-013",
        parameter="FONT_SIZE_COMPLIANCE",
        status="OUT_OF_SCOPE_PHYSICAL_VERIFICATION",
        message="Physical measurement required",
        evidence_data={"verification_type": "PHYSICAL_VERIFICATION_REQUIRED"},
    ))
    isolated_db.commit()

    stats = get_dashboard(isolated_db)
    assert stats.total_inspections == 1
    assert stats.compliant == 1
    assert stats.non_compliant == 0
    assert stats.review_required == 0
    # Out of scope physical rules must NOT appear in common failed parameters
    assert len(stats.common_failed_parameters) == 0


def test_requirement_8_dashboard_and_history_agreement(isolated_db):
    """Ensure Dashboard counts agree with Inspection History for all status categories."""
    # Create 3 inspections: 1 COMPLIANT, 1 REVIEW_REQUIRED, 1 NON_COMPLIANT
    insp_c = models.Inspection(
        product_name="Compliant Product",
        category="FOOD",
        overall_result="COMPLIANT",
        created_at=datetime.now(timezone.utc),
    )
    insp_r = models.Inspection(
        product_name="Review Product",
        category="COSMETIC",
        overall_result="REVIEW_REQUIRED",
        created_at=datetime.now(timezone.utc),
    )
    insp_f = models.Inspection(
        product_name="Non Compliant Product",
        category="FOOD",
        overall_result="NON_COMPLIANT",
        created_at=datetime.now(timezone.utc),
    )
    isolated_db.add_all([insp_c, insp_r, insp_f])
    isolated_db.flush()

    isolated_db.add(models.RuleResult(
        inspection_id=insp_c.id,
        rule_id="PC-001",
        parameter="PRODUCT_NAME",
        status="PASS",
    ))
    isolated_db.add(models.RuleResult(
        inspection_id=insp_r.id,
        rule_id="PC-002",
        parameter="CONSUMER_CARE",
        status="NOT_VERIFIABLE",
    ))
    isolated_db.add(models.RuleResult(
        inspection_id=insp_f.id,
        rule_id="PC-003",
        parameter="MRP",
        status="FAIL",
    ))
    isolated_db.commit()

    stats = get_dashboard(isolated_db)
    all_history = get_history(db=isolated_db)
    compliant_history = get_history(status="COMPLIANT", db=isolated_db)
    review_history = get_history(status="REVIEW_REQUIRED", db=isolated_db)
    non_compliant_history = get_history(status="NON_COMPLIANT", db=isolated_db)

    # Dashboard and history exact count match
    assert stats.total_inspections == len(all_history) == 3
    assert stats.compliant == len(compliant_history) == 1
    assert stats.review_required == len(review_history) == 1
    assert stats.non_compliant == len(non_compliant_history) == 1

    # Status value verification
    assert compliant_history[0].screening_result == "COMPLIANT"
    assert review_history[0].screening_result == "REVIEW_REQUIRED"
    assert non_compliant_history[0].screening_result == "NON_COMPLIANT"


def test_historical_inspections_remain_visible_and_counted(isolated_db):
    """Ensure existing history is preserved, visible, and correctly totaled."""
    for idx in range(10):
        isolated_db.add(models.Inspection(
            product_name=f"Historical Product #{idx + 1}",
            category="FOOD" if idx % 2 == 0 else "COSMETIC",
            overall_result="COMPLIANT" if idx % 2 == 0 else "REVIEW_REQUIRED",
            created_at=datetime.now(timezone.utc),
        ))
    isolated_db.commit()

    stats = get_dashboard(isolated_db)
    history = get_history(db=isolated_db)

    assert stats.total_inspections == 10
    assert stats.compliant == 5
    assert stats.review_required == 5
    assert len(history) == 10
    assert len(stats.recent_inspections) == 5  # Top 5 most recent
