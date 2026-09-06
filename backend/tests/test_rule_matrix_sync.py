"""Automated tests for rule matrix structure, metadata fidelity, and database synchronization."""
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database.connection import SessionLocal, init_db
from app.database import models
from app.rules.rule_engine import sync_rules_to_db
from app.rules.applicability import get_applicable_rules


@pytest.fixture
def rule_matrix_data():
    with open('data/rule_matrix.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def test_rule_matrix_loads_and_contains_standardized_metadata(rule_matrix_data):
    """Verify data/rule_matrix.json loads and all rules contain required metadata fields."""
    rules = rule_matrix_data.get('rules', [])
    assert len(rules) >= 20

    required_fields = [
        'rule_id',
        'parameter',
        'category',
        'package_type',
        'condition',
        'regulatory_source',
        'source_authority',
        'source_document',
        'source_url',
        'rule_reference',
        'rule_reference_status',
        'rule_version',
        'effective_from',
        'required',
        'validation_method',
    ]

    for rule in rules:
        for field in required_fields:
            assert field in rule, f"Rule {rule.get('rule_id')} missing required field '{field}'"
            assert rule[field] is not None, f"Rule {rule.get('rule_id')} has null '{field}'"


def test_unverified_rule_references_are_explicitly_pending_verification(rule_matrix_data):
    """Verify unverified rules remain explicitly marked PENDING_VERIFICATION without invented citations."""
    rules = rule_matrix_data.get('rules', [])
    for rule in rules:
        assert rule['rule_reference_status'] == 'PENDING_VERIFICATION', (
            f"Rule {rule['rule_id']} should have rule_reference_status='PENDING_VERIFICATION'"
        )
        assert rule['rule_reference'] == 'PENDING_VERIFICATION', (
            f"Rule {rule['rule_id']} should not manufacture an unverified rule number"
        )


def test_legal_metrology_commencement_date_is_accurate(rule_matrix_data):
    """Verify Legal Metrology rules use official 1 April 2011 commencement date, not invented 2011-01-01."""
    rules = rule_matrix_data.get('rules', [])
    lm_rules = [r for r in rules if r['regulatory_source'] == 'LEGAL_METROLOGY']
    assert len(lm_rules) >= 12

    for rule in lm_rules:
        assert rule['effective_from'] == '2011-04-01', (
            f"Rule {rule['rule_id']} should have effective_from='2011-04-01', got '{rule['effective_from']}'"
        )


def test_regulatory_sources_and_authorities_are_correctly_classified(rule_matrix_data):
    """Verify proper classification between Legal Metrology, FSSAI, and Cosmetics sources."""
    rules = rule_matrix_data.get('rules', [])

    for rule in rules:
        rule_id = rule['rule_id']
        if rule_id.startswith('PC-ALL'):
            assert rule['regulatory_source'] == 'LEGAL_METROLOGY'
            assert 'Consumer Affairs' in rule['source_authority']
            assert 'Legal Metrology' in rule['source_document']
        elif rule_id.startswith('PC-FOOD'):
            assert rule['regulatory_source'] == 'FSSAI_FOOD_LABELING'
            assert 'Food Safety and Standards Authority of India' in rule['source_authority']
            assert 'Food Safety and Standards' in rule['source_document']
        elif rule_id.startswith('PC-COSM'):
            assert rule['regulatory_source'] == 'COSMETIC_LABELING'
            assert 'Cosmetics' in rule['source_authority'] or 'Drugs' in rule['source_authority'] or 'Health' in rule['source_authority']
            assert 'Cosmetics Rules, 2020' in rule['source_document']


def test_product_name_kept_separate_from_statutory_generic_name(rule_matrix_data):
    """Verify PRODUCT_NAME does not falsely claim to be a statutory Rule 6 heading."""
    rules = rule_matrix_data.get('rules', [])
    product_name_rule = next((r for r in rules if r['rule_id'] == 'PC-ALL-001'), None)
    generic_name_rule = next((r for r in rules if r['rule_id'] == 'PC-ALL-010'), None)

    assert product_name_rule is not None
    assert generic_name_rule is not None
    assert product_name_rule['parameter'] == 'PRODUCT_NAME'
    assert generic_name_rule['parameter'] == 'GENERIC_NAME'

    # Verify exception/note clarifies commercial identification vs statutory generic name
    assert 'Rule 6(1)(b)' in product_name_rule['exception'] or 'generic' in product_name_rule['exception'].lower()
    assert 'generic' in generic_name_rule['exception'].lower() or 'common' in generic_name_rule['exception'].lower()


def test_sync_rules_to_db_preserves_new_metadata():
    """Verify database synchronization populates and updates all new metadata columns."""
    init_db()
    sync_rules_to_db()

    db = SessionLocal()
    try:
        db_rules = db.query(models.Rule).all()
        assert len(db_rules) >= 20

        rule_001 = db.query(models.Rule).filter(models.Rule.rule_id == 'PC-ALL-001').first()
        assert rule_001 is not None
        assert rule_001.source_authority == "Department of Consumer Affairs, Ministry of Consumer Affairs, Food and Public Distribution"
        assert rule_001.effective_from == "2011-04-01"
        assert rule_001.rule_reference_status == "PENDING_VERIFICATION"
        assert rule_001.regulatory_source == "LEGAL_METROLOGY"
        assert rule_001.source_url is not None

        food_rule = db.query(models.Rule).filter(models.Rule.rule_id == 'PC-FOOD-001').first()
        assert food_rule is not None
        assert food_rule.regulatory_source == "FSSAI_FOOD_LABELING"
        assert food_rule.source_authority == "Food Safety and Standards Authority of India (FSSAI)"
        assert "Labelling and Display" in food_rule.source_document

        cosm_rule = db.query(models.Rule).filter(models.Rule.rule_id == 'PC-COSM-001').first()
        assert cosm_rule is not None
        assert cosm_rule.regulatory_source == "COSMETIC_LABELING"
        assert "Cosmetics Rules, 2020" in cosm_rule.source_document
    finally:
        db.close()


def test_physical_verification_rules_visible_in_applicability_without_physical_data(rule_matrix_data):
    """Verify physical verification rules (PC-ALL-012, PC-ALL-013) remain visible in applicability."""
    all_rules = rule_matrix_data.get('rules', [])
    applicable = get_applicable_rules(
        all_rules=all_rules,
        category='FOOD',
        package_type='RETAIL',
        import_status='DOMESTIC',
        product_type='OTHER_FOOD',
        has_physical_data=False,  # Image-only scan
    )
    app_ids = {r['rule_id'] for r in applicable}

    # Physical verification rules must remain visible in applicability
    assert 'PC-ALL-012' in app_ids
    assert 'PC-ALL-013' in app_ids


def test_rules_api_endpoint_exposes_standardized_metadata():
    """Verify GET /api/rules endpoint returns all standardized metadata fields."""
    client = TestClient(app)
    resp = client.get("/api/rules")
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) >= 20

    first_rule = next(r for r in rules if r['rule_id'] == 'PC-ALL-001')
    assert first_rule['source_authority'] is not None
    assert first_rule['source_url'] is not None
    assert first_rule['rule_reference_status'] == 'PENDING_VERIFICATION'
    assert first_rule['effective_from'] == '2011-04-01'
    assert first_rule['regulatory_source'] == 'LEGAL_METROLOGY'
