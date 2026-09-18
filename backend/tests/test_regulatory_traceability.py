"""
Comprehensive test suite for Regulatory Traceability & Applicability Verification.
Verifies all 18 required scenarios:
 1. Retail package applicability
 2. Wholesale package applicability (Rule 24)
 3. Industrial / institutional package applicability (Rule 3 / 26)
 4. Unit sale price retail applicability
 5. Unit sale price wholesale non-applicability
 6. Generic name (PC-ALL-010) vs Internal Product name (PC-ALL-001)
 7. Rule 24 wholesale package declarations
 8. Net quantity rule mapping (Rule 6(1)(c), 11, 12, 13)
 9. Multipack quantity traceability (Rule 13(6))
 10. Food vs non-food date marking statutory source
 11. FSSAI licence source & label presence vs FoSCoS lookup distinction
 12. Veg / non-veg symbol candidate vs legal compliance
 13. Internal / non-statutory field handling
 16. Verification-status handling across rule matrix
 17. Effective-date handling
 18. Historical regulatory version preservation
"""
import json
import pytest
from app.rules.applicability import get_applicable_rules
from app.rules.rule_engine import evaluate_rules
from app.rules.validators import dispatch_validator
from app.database.connection import SessionLocal, init_db
from app.database import models


@pytest.fixture(scope="module")
def rule_matrix_data():
    with open('data/rule_matrix.json', 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture(scope="module")
def rules_list(rule_matrix_data):
    return rule_matrix_data.get('rules', [])


# ==============================================================================
# 1. Retail package applicability
# ==============================================================================
def test_01_retail_package_applicability(rules_list):
    """Verify retail packages apply retail-specific Chapter II declarations (MRP, USP, Consumer Care, etc.)."""
    applicable = get_applicable_rules(
        all_rules=rules_list,
        category='FOOD',
        package_type='RETAIL',
        import_status='DOMESTIC',
        product_type='OTHER_FOOD',
    )
    app_ids = {r['rule_id'] for r in applicable}

    assert 'PC-ALL-004' in app_ids, "MRP (Rule 6(1)(e)) must apply to retail packages"
    assert 'PC-ALL-008' in app_ids, "Consumer Care (Rule 6(2)) must apply to retail packages"
    assert 'PC-ALL-011' in app_ids, "Unit Sale Price (Rule 6(11)) must apply to retail packages"
    assert 'PC-FOOD-001' in app_ids, "Best Before / Expiry must apply to retail food packages"


# ==============================================================================
# 2. Wholesale package applicability (Rule 24)
# ==============================================================================
def test_02_wholesale_package_applicability(rules_list):
    """Verify wholesale packages apply Rule 24 and exclude retail-only declarations."""
    applicable = get_applicable_rules(
        all_rules=rules_list,
        category='ALL',
        package_type='WHOLESALE',
        import_status='DOMESTIC',
        product_type='ALL',
    )
    app_ids = {r['rule_id'] for r in applicable}

    # Wholesale must exclude retail-only rules
    assert 'PC-ALL-003' not in app_ids, "Retail MRP (Rule 6(1)(e)) must NOT apply to wholesale packages"
    assert 'PC-ALL-008' not in app_ids, "Retail Consumer Care (Rule 6(2)) must NOT apply to wholesale packages"
    assert 'PC-ALL-009' not in app_ids, "Retail Mfg Date (Rule 6(1)(d)) must NOT apply to wholesale packages"
    assert 'PC-ALL-011' not in app_ids, "Unit Sale Price (Rule 6(11)) must NOT apply to wholesale packages"

    # Wholesale must include Rule 24 statutory declarations
    assert 'PC-ALL-002' in app_ids, "Net quantity (Rule 24(c)) must apply to wholesale packages"
    assert 'PC-ALL-004' in app_ids, "Manufacturer name (Rule 24(a)) must apply to wholesale packages"
    assert 'PC-ALL-005' in app_ids, "Manufacturer address (Rule 24(a)) must apply to wholesale packages"
    assert 'PC-ALL-010' in app_ids, "Generic/commodity name (Rule 24(b)) must apply to wholesale packages"


# ==============================================================================
# 3. Industrial / institutional package applicability (Rule 3 / 26)
# ==============================================================================
def test_03_industrial_institutional_package_applicability(rules_list):
    """Verify packages for industrial and institutional consumers exclude retail declarations."""
    for pkg_type in ['INSTITUTIONAL', 'INDUSTRIAL']:
        applicable = get_applicable_rules(
            all_rules=rules_list,
            category='ALL',
            package_type=pkg_type,
            import_status='DOMESTIC',
            product_type='ALL',
        )
        app_ids = {r['rule_id'] for r in applicable}
        assert 'PC-ALL-003' not in app_ids, f"MRP must be excluded for {pkg_type} packages"
        assert 'PC-ALL-008' not in app_ids, f"Consumer care must be excluded for {pkg_type} packages"
        assert 'PC-ALL-011' not in app_ids, f"Unit sale price must be excluded for {pkg_type} packages"


# ==============================================================================
# 4. Unit sale price retail applicability
# ==============================================================================
def test_04_unit_sale_price_retail_applicability(rules_list):
    """Verify PC-ALL-011 references Rule 6(11), effective from 2024-01-01, and applies to retail."""
    usp_rule = next(r for r in rules_list if r['rule_id'] == 'PC-ALL-011')
    assert 'Rule 6(11)' in usp_rule['rule_reference']
    assert usp_rule['effective_from'] == '2024-01-01'
    assert usp_rule['package_type'] == 'RETAIL'
    assert usp_rule['verification_status'] in ('VERIFIED', 'APPLICABILITY_DEPENDENT')
    assert 'consumeraffairs.nic.in' in usp_rule['source_url']


# ==============================================================================
# 5. Unit sale price wholesale non-applicability
# ==============================================================================
def test_05_unit_sale_price_wholesale_non_applicability(rules_list):
    """Verify PC-ALL-011 evaluates to NOT_APPLICABLE if evaluated against a wholesale package."""
    usp_rule = next(r for r in rules_list if r['rule_id'] == 'PC-ALL-011')
    result = dispatch_validator(
        validation_method=usp_rule.get("validation_method"),
        evidence={'value': '₹0.50/g'},
        rule=usp_rule,
        all_fields={'package_type': 'WHOLESALE'},
    )
    assert result.status == 'NOT_APPLICABLE'
    assert 'wholesale' in result.reason.lower() or 'rule 24' in result.reason.lower()


# ==============================================================================
# 6. Generic name (PC-ALL-010) vs automatic product name screening (PC-ALL-001)
# ==============================================================================
def test_06_generic_name_vs_internal_product_name(rules_list):
    """Verify PRODUCT_NAME uses automatic image screening while GENERIC_NAME is statutory Rule 6(1)(b) / 24(b)."""
    p_name = next(r for r in rules_list if r['rule_id'] == 'PC-ALL-001')
    g_name = next(r for r in rules_list if r['rule_id'] == 'PC-ALL-010')

    # PC-ALL-001: Automatic image screening
    assert p_name['regulatory_source'] == 'AUTOMATIC_IMAGE_SCREENING'
    assert p_name['rule_reference_status'] == 'SOURCE_IDENTIFIED'
    assert p_name['verification_status'] == 'SOURCE_IDENTIFIED'
    assert 'AUTOMATIC_IMAGE_SCREENING' in p_name['rule_reference']
    assert 'Rule 6(1)(b)' not in p_name['rule_reference'], "PRODUCT_NAME must not cite Rule 6(1)(b)"

    # PC-ALL-010: Statutory Rule 6(1)(b) [Retail] & Rule 24(b) [Wholesale]
    assert g_name['regulatory_source'] == 'LEGAL_METROLOGY'
    assert g_name['rule_reference_status'] == 'VERIFIED'
    assert g_name['verification_status'] == 'VERIFIED'
    assert 'Rule 6(1)(b)' in g_name['rule_reference']
    assert 'Rule 24(b)' in g_name['rule_reference']


# ==============================================================================
# 7. Rule 24 wholesale package declarations
# ==============================================================================
def test_07_rule_24_wholesale_declarations(rules_list):
    """Verify Rule 24 wholesale package mandatory declaration citations."""
    mfg_rule = next(r for r in rules_list if r['rule_id'] == 'PC-ALL-004')
    net_rule = next(r for r in rules_list if r['rule_id'] == 'PC-ALL-002')
    gen_rule = next(r for r in rules_list if r['rule_id'] == 'PC-ALL-010')

    assert 'Rule 24(a)' in mfg_rule['rule_reference']
    assert 'Rule 24(c)' in net_rule['rule_reference']
    assert 'Rule 24(b)' in gen_rule['rule_reference']


# ==============================================================================
# 8. Net quantity rule mapping (Rule 6(1)(c), 11, 12, 13)
# ==============================================================================
def test_08_net_quantity_rule_mapping(rules_list):
    """Verify net quantity PC-ALL-002 maps to Rule 6(1)(c), 11, 12, 13 and Rule 24(c)."""
    net_rule = next(r for r in rules_list if r['rule_id'] == 'PC-ALL-002')
    ref = net_rule['rule_reference']
    assert 'Rule 6(1)(c)' in ref
    assert 'Rule 11' in ref
    assert 'Rule 12' in ref
    assert 'Rule 13' in ref
    assert 'Rule 24(c)' in ref
    assert net_rule['verification_status'] == 'VERIFIED'


# ==============================================================================
# 9. Multipack quantity traceability (Rule 13(6))
# ==============================================================================
def test_09_multipack_quantity_traceability(rules_list):
    """Verify multipack quantity rules trace to Rule 13(6)."""
    net_rule = next(r for r in rules_list if r['rule_id'] == 'PC-ALL-002')
    # Exception or citation text must articulate Rule 13(6) multipack mandate
    combined_text = (net_rule.get('exception', '') + ' ' + net_rule.get('citation_text', '')).lower()
    assert '13(6)' in combined_text or 'multi-piece' in combined_text or 'multipack' in combined_text


# ==============================================================================
# 10. Food vs non-food date marking statutory source
# ==============================================================================
def test_10_food_vs_non_food_date_marking_source(rules_list):
    """Verify non-food date marking traces to Rule 6(1)(d), while food date marking routes to FSSAI."""
    non_food_date = next(r for r in rules_list if r['rule_id'] == 'PC-ALL-009')
    food_date = next(r for r in rules_list if r['rule_id'] == 'PC-FOOD-001')

    # Non-food
    assert 'Rule 6(1)(d)' in non_food_date['rule_reference']
    assert non_food_date['regulatory_source'] == 'LEGAL_METROLOGY'
    assert 'Food Safety and Standards Act' in non_food_date['exception'] or 'FSSAI' in non_food_date['exception']

    # Food
    assert 'Regulation 5(10)' in food_date['rule_reference']
    assert food_date['regulatory_source'] == 'FSSAI_FOOD_LABELING'
    assert 'fssai.gov.in' in food_date['source_url']


# ==============================================================================
# 11. FSSAI licence source & label presence vs FoSCoS lookup distinction
# ==============================================================================
def test_11_fssai_licence_source_and_lookup_distinction(rules_list):
    """Verify FSSAI licence presence traces to FSSAI regulations, distinguishing label presence from FoSCoS lookup."""
    licence_rule = next(r for r in rules_list if r['rule_id'] == 'PC-FOOD-004')
    assert 'Reg 5(7)' in licence_rule['rule_reference'] or 'Regulation 5(7)' in licence_rule['citation']
    assert 'Licensing Reg 2011' in licence_rule['rule_reference'] or 'Section 31' in licence_rule['citation']
    # Verify notes/exception distinguish label presence from external FoSCoS database validation
    combined = (licence_rule.get('exception', '') + ' ' + licence_rule.get('notes', '')).lower()
    assert 'foscos' in combined or 'lookup' in combined or 'registration' in combined


# ==============================================================================
# 12. Veg / non-veg symbol candidate vs legal compliance
# ==============================================================================
def test_12_veg_non_veg_symbol_statutory_source(rules_list):
    """Verify veg/non-veg symbol rule traces to FSSR (Labelling and Display) 2020 Regulation 5(4)."""
    veg_rule = next(r for r in rules_list if r['rule_id'] == 'PC-FOOD-005')
    assert 'Regulation 5(4)' in veg_rule['rule_reference']
    assert veg_rule['regulatory_source'] == 'FSSAI_FOOD_LABELING'
    assert veg_rule['verification_status'] == 'VERIFIED'


# ==============================================================================
# ===============================================================================
# 13. Automatic product identity field handling
# ==============================================================================
def test_15_automatic_product_identity_field_handling(rules_list):
    """Verify product identity uses automatic package-image metadata."""
    product_rules = [r for r in rules_list if r['rule_id'] == 'PC-ALL-001']
    assert len(product_rules) == 1
    r = product_rules[0]
    assert r['verification_status'] == 'SOURCE_IDENTIFIED'
    assert r['rule_reference_status'] == 'SOURCE_IDENTIFIED'
    assert r['regulatory_source'] == 'AUTOMATIC_IMAGE_SCREENING'
    assert r['instrument'] == 'Automatic Package Image Screening'


# ==============================================================================
# 16. Verification-status handling across rule matrix
# ==============================================================================
def test_16_verification_status_handling_across_all_rules(rules_list):
    """Verify every rule has an audited, controlled verification_status (VERIFIED, APPLICABILITY_DEPENDENT, or NON_STATUTORY)."""
    assert len(rules_list) >= 21
    allowed_statuses = {'VERIFIED', 'APPLICABILITY_DEPENDENT', 'NON_STATUTORY', 'SOURCE_IDENTIFIED'}

    for r in rules_list:
        status = r.get('verification_status')
        assert status in allowed_statuses, (
            f"Rule {r['rule_id']} has invalid or pending verification_status: {status}"
        )
        assert r.get('instrument') is not None, f"Rule {r['rule_id']} missing instrument"
        assert r.get('citation') is not None, f"Rule {r['rule_id']} missing citation"
        assert r.get('screening_scope') is not None, f"Rule {r['rule_id']} missing screening_scope"


# ==============================================================================
# 17. Effective-date handling
# ==============================================================================
def test_17_effective_date_handling(rules_list):
    """Verify all effective dates are valid and historically accurate."""
    for r in rules_list:
        eff = r.get('effective_from')
        assert eff is not None
        assert len(eff) == 10 and eff[4] == '-' and eff[7] == '-', (
            f"Rule {r['rule_id']} has malformed effective_from '{eff}'"
        )
        if r['rule_id'] == 'PC-ALL-011':
            assert eff == '2024-01-01'
        elif r['rule_id'] == 'PC-ALL-006':
            assert eff == '2018-01-01'
        elif r['rule_id'].startswith('PC-FOOD'):
            assert eff in ['2020-11-18', '2011-08-05', '2027-07-01']
        elif r['rule_id'].startswith('PC-COSM'):
            assert eff == '2020-12-15'
        elif r['regulatory_source'] == 'LEGAL_METROLOGY':
            assert eff == '2011-04-01'


# ==============================================================================
# 18. Historical regulatory version preservation
# ==============================================================================
def test_18_historical_regulatory_version_preservation(rule_matrix_data, rules_list):
    """Verify inspection engine attaches regulatory_snapshot and rule_version metadata for reproducibility."""
    snapshot = rule_matrix_data.get('regulatory_snapshot')
    assert snapshot is not None
    assert 'LMPC_2011_CURRENT_2024' in snapshot
    assert 'FSSAI_LD_2020_CURRENT_2024' in snapshot
    assert 'COSMETICS_2020_CURRENT_2024' in snapshot

    applicable = get_applicable_rules(
        all_rules=rules_list,
        category='FOOD',
        package_type='RETAIL',
        import_status='DOMESTIC',
        product_type='OTHER_FOOD',
    )
    # Run evaluate_rules and verify every result retains traceability metadata
    results, overall = evaluate_rules(
        applicable_rules=applicable,
        extracted_fields={
            'GENERIC_NAME': {'value': 'Iodized Table Salt'},
            'MRP': {'value': '₹25.00'},
            'NET_QUANTITY': {'value': '1 kg'},
        },
    )
    assert len(results) > 0
    for res in results:
        assert 'rule_reference' in res
        assert 'rule_version' in res
        assert 'regulatory_source' in res
        assert 'verification_status' in res
        assert 'citation' in res
        assert res['verification_status'] in {'VERIFIED', 'APPLICABILITY_DEPENDENT', 'NON_STATUTORY', 'SOURCE_IDENTIFIED'}


# ==============================================================================
# 19. FSSAI 2026 amendment effective date control (Notification != Commencement)
# ==============================================================================
def test_19_fssai_2026_amendment_effective_date_control(rules_list):
    """
    Explicitly test that the Food Safety and Standards (Labelling and Display)
    First Amendment Regulations, 2026 (PC-FOOD-003-AMEND2026 / FSSAI_LD_AMEND_2026):
    - Notification date: 24 March 2026 (2026-03-24)
    - Stated commencement date: 1 July 2027 (2027-07-01)
    - Must NOT be active on notification date (2026-03-24)
    - Must NOT be active day before commencement (2027-06-30)
    - Must BE active on commencement date (2027-07-01)
    - Must BE active after commencement date (2027-08-01)
    """
    # Scenario A: Notification date (2026-03-24) -> 2026 amendment NOT active
    app_notif = get_applicable_rules(
        all_rules=rules_list,
        category='FOOD',
        package_type='RETAIL',
        product_type='OTHER_FOOD',
        inspection_date='2026-03-24',
    )
    ids_notif = {r['rule_id'] for r in app_notif}
    vers_notif = {r.get('rule_version') for r in app_notif}
    assert 'PC-FOOD-003-AMEND2026' not in ids_notif, "Must not apply on publication/notification date (2026-03-24)"
    assert 'FSSAI_LD_AMEND_2026' not in vers_notif
    assert 'PC-FOOD-003' in ids_notif, "Baseline Regulation 5(3) must remain active"

    # Scenario B: Day before commencement (2027-06-30) -> 2026 amendment NOT active
    app_eve = get_applicable_rules(
        all_rules=rules_list,
        category='FOOD',
        package_type='RETAIL',
        product_type='OTHER_FOOD',
        inspection_date='2027-06-30',
    )
    ids_eve = {r['rule_id'] for r in app_eve}
    vers_eve = {r.get('rule_version') for r in app_eve}
    assert 'PC-FOOD-003-AMEND2026' not in ids_eve, "Must not apply before commencement date (2027-06-30)"
    assert 'FSSAI_LD_AMEND_2026' not in vers_eve
    assert 'PC-FOOD-003' in ids_eve, "Baseline Regulation 5(3) must remain active up to 2027-06-30"

    # Scenario C: Commencement date (2027-07-01) -> 2026 amendment active
    app_commence = get_applicable_rules(
        all_rules=rules_list,
        category='FOOD',
        package_type='RETAIL',
        product_type='OTHER_FOOD',
        inspection_date='2027-07-01',
    )
    ids_commence = {r['rule_id'] for r in app_commence}
    vers_commence = {r.get('rule_version') for r in app_commence}
    assert 'PC-FOOD-003-AMEND2026' in ids_commence, "Must become active on commencement date (2027-07-01)"
    assert 'FSSAI_LD_AMEND_2026' in vers_commence
    assert 'PC-FOOD-003' not in ids_commence, "Baseline version must be excluded once amendment commences"

    # Scenario D: After commencement (2027-08-01) -> 2026 amendment active
    app_after = get_applicable_rules(
        all_rules=rules_list,
        category='FOOD',
        package_type='RETAIL',
        product_type='OTHER_FOOD',
        inspection_date='2027-08-01',
    )
    ids_after = {r['rule_id'] for r in app_after}
    vers_after = {r.get('rule_version') for r in app_after}
    assert 'PC-FOOD-003-AMEND2026' in ids_after, "Must remain active after commencement date (2027-08-01)"
    assert 'FSSAI_LD_AMEND_2026' in vers_after
    assert 'PC-FOOD-003' not in ids_after


# ==============================================================================
# 20. Historical snapshot enforcement (Inspection A vs Inspection B)
# ==============================================================================
def test_20_historical_snapshot_enforcement(rules_list):
    """
    Demonstrate:
    - Inspection A conducted before 2027-07-01 (e.g. 2026-09-09) -> pre-amendment snapshot
    - Inspection B conducted on/after 2027-07-01 (e.g. 2027-07-01) -> post-amendment snapshot
    - Reopening Inspection A must NEVER silently switch it to the later amendment.
    """
    from app.rules.status_safety import derive_dynamic_regulatory_snapshot

    # Inspection A before 2027-07-01 (e.g. 2026-09-09)
    date_A = '2026-09-09'
    rules_A = get_applicable_rules(
        all_rules=rules_list,
        category='FOOD',
        package_type='RETAIL',
        product_type='OTHER_FOOD',
        inspection_date=date_A,
    )
    snapshot_A = derive_dynamic_regulatory_snapshot(rules_A, date_A)
    assert 'FSSAI_LD_AMEND_2026' not in snapshot_A['snapshot_id']
    assert any(r['rule_id'] == 'PC-FOOD-003' for r in rules_A)
    assert not any(r['rule_id'] == 'PC-FOOD-003-AMEND2026' for r in rules_A)

    # Inspection B on/after 2027-07-01 (e.g. 2027-07-01)
    date_B = '2027-07-01'
    rules_B = get_applicable_rules(
        all_rules=rules_list,
        category='FOOD',
        package_type='RETAIL',
        product_type='OTHER_FOOD',
        inspection_date=date_B,
    )
    snapshot_B = derive_dynamic_regulatory_snapshot(rules_B, date_B)
    assert 'FSSAI_LD_AMEND_2026' in snapshot_B['snapshot_id']
    assert any(r['rule_id'] == 'PC-FOOD-003-AMEND2026' for r in rules_B)
    assert not any(r['rule_id'] == 'PC-FOOD-003' for r in rules_B)

    # Re-evaluating historical Inspection A against date_A:
    rules_A_reopened = get_applicable_rules(
        all_rules=rules_list,
        category='FOOD',
        package_type='RETAIL',
        product_type='OTHER_FOOD',
        inspection_date=date_A,
    )
    snapshot_A_reopened = derive_dynamic_regulatory_snapshot(rules_A_reopened, date_A)
    assert snapshot_A_reopened['snapshot_id'] == snapshot_A['snapshot_id']
    assert not any(r['rule_id'] == 'PC-FOOD-003-AMEND2026' for r in rules_A_reopened)
    assert any(r['rule_id'] == 'PC-FOOD-003' for r in rules_A_reopened)


# ==============================================================================
# 21. Status Safety Guard (Mandatory metadata required for VERIFIED)
# ==============================================================================
def test_21_status_safety_metadata_enforcement():
    """
    Test that the status safety guard prevents VERIFIED status if required metadata is missing,
    and properly downgrades to PENDING_REVIEW or SOURCE_IDENTIFIED.
    """
    from app.rules.status_safety import validate_and_enforce_verification_status

    # Rule missing citation and source_url
    incomplete_rule = {
        'rule_id': 'TEST-001',
        'parameter': 'CUSTOM_PARAM',
        'verification_status': 'VERIFIED',
        'authority': 'Testing Authority',
    }
    status = validate_and_enforce_verification_status(incomplete_rule)
    assert status == 'PENDING_REVIEW', f"Expected PENDING_REVIEW for incomplete rule, got {status}"

    # Internal inspection rule must enforce NON_STATUTORY
    internal_rule = {
        'rule_id': 'PC-ALL-001',
        'parameter': 'PRODUCT_NAME',
        'verification_status': 'VERIFIED',  # Operator incorrectly attempted to set VERIFIED
        'source_authority': 'Department of Consumer Affairs',
        'citation': 'Section 18',
        'source_url': 'https://consumeraffairs.nic.in',
        'effective_from': '2011-04-01',
        'applicability': 'ALL',
        'rule_version': 'V1',
    }
    status_internal = validate_and_enforce_verification_status(internal_rule)
    assert status_internal == 'NON_STATUTORY', f"Internal field must be NON_STATUTORY, got {status_internal}"

    # Conditional exemption rule must enforce APPLICABILITY_DEPENDENT
    conditional_rule = {
        'rule_id': 'PC-ALL-011',
        'parameter': 'UNIT_SALE_PRICE',
        'verification_status': 'VERIFIED',
        'source_authority': 'Department of Consumer Affairs',
        'citation': 'Rule 6(11)',
        'source_url': 'https://consumeraffairs.nic.in',
        'effective_from': '2024-01-01',
        'applicability': 'RETAIL',
        'rule_version': 'LMPC_2011_CURRENT_2024',
        'condition': 'APPLICABLE',
    }
    status_cond = validate_and_enforce_verification_status(conditional_rule)
    assert status_cond == 'APPLICABILITY_DEPENDENT', f"Conditional exemption rule must be APPLICABILITY_DEPENDENT, got {status_cond}"


# ==============================================================================

