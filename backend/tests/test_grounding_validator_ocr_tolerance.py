"""
Regression and compliance test suite for OCR-tolerant Evidence Grounding Validator.
Tests fuzzy entity matching, locality-anchored address matching, strict numeric validation,
token provenance verification, and audit metadata recording.
"""

import pytest
from app.llm.grounding_validator import (
    EvidenceGroundingValidator,
    evaluate_grounding_match,
    _is_value_derivable_from_text,
    classify_field_type,
)
from app.llm.schemas import (
    CandidateValue,
    LLMExtractionResult,
    PackageContext,
    ResolvedDeclaration,
    SourceEvidence,
)


def test_entity_name_fuzzy_match_pass_production_example():
    """PASS: 'Global Health Care Products' vs OCR 'belowGGlobal Heaith Care Products,134.Dapada Kharve'"""
    ocr_text = 'belowGGlobal Heaith Care Products,134.Dapada Kharve'
    llm_val = 'Global Health Care Products'
    is_grounded, reason, score = evaluate_grounding_match('MANUFACTURER_NAME', llm_val, ocr_text)
    assert is_grounded is True
    assert reason == 'OCR_FUZZY_ENTITY_MATCH'
    assert score >= 0.75


def test_entity_name_fuzzy_match_pass_direct_noisy_ocr():
    """PASS: 'Global Health Care Products' vs 'GGlobal Heaith Care Products'"""
    ocr_text = 'GGlobal Heaith Care Products'
    llm_val = 'Global Health Care Products'
    is_grounded, reason, score = evaluate_grounding_match('MANUFACTURER_NAME', llm_val, ocr_text)
    assert is_grounded is True
    assert reason == 'OCR_FUZZY_ENTITY_MATCH'
    assert score >= 0.85


def test_entity_name_fail_different_company():
    """FAIL: 'ABC Foods Pvt Ltd' vs 'XYZ Consumer Products Ltd'"""
    ocr_text = 'XYZ Consumer Products Ltd'
    llm_val = 'ABC Foods Pvt Ltd'
    is_grounded, reason, score = evaluate_grounding_match('MANUFACTURER_NAME', llm_val, ocr_text)
    assert is_grounded is False
    assert reason == 'REJECTED_UNSUPPORTED'


def test_entity_name_pass_common_ocr_substitution():
    """PASS: common OCR substitution within a company name ('Procter & Gamble' vs 'Proctor & Gambie')"""
    ocr_text = 'Proctor & Gambie Hygiene Products Ltd'
    llm_val = 'Procter & Gamble'
    is_grounded, reason, score = evaluate_grounding_match('MARKETER_NAME', llm_val, ocr_text)
    assert is_grounded is True
    assert reason == 'OCR_FUZZY_ENTITY_MATCH'
    assert score >= 0.75


def test_entity_name_pass_punctuation_and_spacing():
    """PASS: small punctuation/spacing differences"""
    ocr_text = 'Global Health Care Products India Pvt Ltd'
    llm_val = 'Global Health-Care Products (India) Pvt. Ltd.'
    is_grounded, reason, score = evaluate_grounding_match('MANUFACTURER_NAME', llm_val, ocr_text)
    assert is_grounded is True
    assert reason in ('NORMALIZED_MATCH', 'EXACT_MATCH')
    assert score == 1.0


def test_address_fuzzy_match_pass_production_example():
    """PASS: 'Village Jharmari, Baddi, District Solan, Himachal Pradesh' vs OCR with damaged spelling & abbreviations"""
    ocr_text = 'Village JharmariBartiwaa Badd Roa,Ts Badi Distt.Slan-17403 (H.P)...'
    llm_val = 'Village Jharmari, Baddi, District Solan, Himachal Pradesh'
    is_grounded, reason, score = evaluate_grounding_match('PACKER_ADDRESS', llm_val, ocr_text)
    assert is_grounded is True
    assert reason == 'OCR_FUZZY_ADDRESS_MATCH'
    assert score >= 0.65


def test_address_fuzzy_match_pass_locality_anchors():
    """PASS: 'Baddi, District Solan' vs 'Badd ... Distt.Slan'"""
    ocr_text = 'Near Badd Barrier, Tehsil Badi, Distt.Slan HP'
    llm_val = 'Baddi, District Solan'
    is_grounded, reason, score = evaluate_grounding_match('MANUFACTURER_ADDRESS', llm_val, ocr_text)
    assert is_grounded is True
    assert reason == 'OCR_FUZZY_ADDRESS_MATCH'
    assert score >= 0.65


def test_address_fail_invented_address_unsupported_by_ocr():
    """FAIL: invented address unsupported by OCR"""
    ocr_text = 'Village JharmariBartiwaa Badd Roa,Ts Badi Distt.Slan-17403 (H.P)...'
    llm_val = 'Plot 42, Okhla Industrial Area Phase III, New Delhi 110020'
    is_grounded, reason, score = evaluate_grounding_match('MANUFACTURER_ADDRESS', llm_val, ocr_text)
    assert is_grounded is False
    assert reason == 'REJECTED_UNSUPPORTED'


def test_numeric_mrp_strict_mismatch_fails():
    """FAIL: '₹250' vs OCR '₹150'"""
    ocr_text = 'MRP Rs. 150.00 (Incl. of all taxes)'
    llm_val = '₹250'
    is_grounded, reason, score = evaluate_grounding_match('MRP', llm_val, ocr_text)
    assert is_grounded is False
    assert reason == 'REJECTED_UNSUPPORTED'


def test_numeric_net_quantity_strict_mismatch_fails():
    """FAIL: '500 g' vs OCR '300 g'"""
    ocr_text = 'Net Weight: 300 g'
    llm_val = '500 g'
    is_grounded, reason, score = evaluate_grounding_match('DECLARED_NET_QUANTITY', llm_val, ocr_text)
    assert is_grounded is False
    assert reason == 'REJECTED_UNSUPPORTED'


def test_numeric_mrp_pass_when_digits_match():
    """PASS: '₹250' vs OCR 'MRP Rs. 250.00'"""
    ocr_text = 'MRP Rs. 250.00 (Incl. of all taxes)'
    llm_val = '₹250'
    is_grounded, reason, score = evaluate_grounding_match('MRP', llm_val, ocr_text)
    assert is_grounded is True
    assert reason in ('NORMALIZED_MATCH', 'EXACT_MATCH')


def test_date_grounding_pass_and_fail():
    """PASS: date normalization MM/YY -> MM/YYYY; FAIL: ungrounded date"""
    raw_text = 'MFG: 05/26 EXP: 04/28'
    ok1, reason1, _ = evaluate_grounding_match('MONTH_YEAR_MANUFACTURE', '05/2026', raw_text)
    assert ok1 is True
    assert reason1 == 'DATE_NORMALIZATION'

    ok2, reason2, _ = evaluate_grounding_match('EXPIRY_DATE', '04/2028', raw_text)
    assert ok2 is True
    assert reason2 == 'DATE_NORMALIZATION'

    ok3, reason3, _ = evaluate_grounding_match('MONTH_YEAR_MANUFACTURE', '05/2030', raw_text)
    assert ok3 is False
    assert reason3 == 'REJECTED_UNSUPPORTED'


def test_validator_with_full_ocr_tokens_production_case():
    """Test EvidenceGroundingValidator full flow with OCR token mapping for noisy entity & address."""
    ocr_items = [
        {'token_id': 1, 'image_index': 0, 'text': 'belowGGlobal Heaith Care Products,134.Dapada Kharve', 'bbox': [10, 10, 100, 30], 'confidence': 0.88},
        {'token_id': 2, 'image_index': 0, 'text': 'Village JharmariBartiwaa Badd Roa,Ts Badi Distt.Slan-17403 (H.P)', 'bbox': [10, 40, 200, 70], 'confidence': 0.82},
        {'token_id': 3, 'image_index': 0, 'text': 'MRP Rs. 250 (Incl. taxes)', 'bbox': [10, 80, 100, 100], 'confidence': 0.95},
    ]
    validator = EvidenceGroundingValidator(ocr_items, num_images=1)

    # 1. Manufacturer Name with OCR noise
    decl_mfr = ResolvedDeclaration(
        field='MANUFACTURER_NAME',
        value='Global Health Care Products',
        status='RESOLVED',
        confidence=0.92,
        source_evidence=[
            SourceEvidence(image_index=0, token_ids=[1], raw_text='belowGGlobal Heaith Care Products,134.Dapada Kharve')
        ],
    )
    is_valid, violations, validated = validator.validate_declaration(decl_mfr)
    assert is_valid is True
    assert validated.status == 'RESOLVED'
    assert getattr(validated, '_grounding_reason') == 'OCR_FUZZY_ENTITY_MATCH'

    # 2. Packer Address with OCR noise
    decl_addr = ResolvedDeclaration(
        field='PACKER_ADDRESS',
        value='Village Jharmari, Baddi, District Solan, Himachal Pradesh',
        status='RESOLVED',
        confidence=0.89,
        source_evidence=[
            SourceEvidence(image_index=0, token_ids=[2], raw_text='Village JharmariBartiwaa Badd Roa,Ts Badi Distt.Slan-17403 (H.P)')
        ],
    )
    is_valid_addr, violations_addr, validated_addr = validator.validate_declaration(decl_addr)
    assert is_valid_addr is True
    assert validated_addr.status == 'RESOLVED'
    assert getattr(validated_addr, '_grounding_reason') == 'OCR_FUZZY_ADDRESS_MATCH'

    # 3. Hallucinated Company Name -> REJECTED
    decl_hallucinated = ResolvedDeclaration(
        field='MARKETER_NAME',
        value='Unrelated Multinational MegaCorp Inc',
        status='RESOLVED',
        confidence=0.95,
        source_evidence=[
            SourceEvidence(image_index=0, token_ids=[1], raw_text='belowGGlobal Heaith Care Products,134.Dapada Kharve')
        ],
    )
    is_valid_hal, violations_hal, validated_hal = validator.validate_declaration(decl_hallucinated)
    assert is_valid_hal is False
    assert validated_hal.status in ('NOT_FOUND', 'CONFLICT')


def test_extraction_result_audit_metadata_records_reasons_and_scores():
    """Verify validate_extraction_result records exact grounding_reason and numerical scores in audit metadata."""
    ocr_items = [
        {'token_id': 10, 'image_index': 0, 'text': 'GGlobal Heaith Care Products', 'bbox': [10, 10, 100, 30], 'confidence': 0.88},
        {'token_id': 11, 'image_index': 0, 'text': 'MRP Rs. 250', 'bbox': [10, 40, 100, 60], 'confidence': 0.95},
        {'token_id': 12, 'image_index': 0, 'text': 'MFG: 05/26', 'bbox': [10, 70, 100, 90], 'confidence': 0.90},
    ]
    validator = EvidenceGroundingValidator(ocr_items, num_images=1)

    result = LLMExtractionResult(
        resolved_declarations=[
            ResolvedDeclaration(
                field='MANUFACTURER_NAME',
                value='Global Health Care Products',
                source_evidence=[SourceEvidence(image_index=0, token_ids=[10], raw_text='GGlobal Heaith Care Products')],
            ),
            ResolvedDeclaration(
                field='MRP',
                value='₹ 250.00',
                source_evidence=[SourceEvidence(image_index=0, token_ids=[11], raw_text='MRP Rs. 250')],
            ),
            ResolvedDeclaration(
                field='MONTH_YEAR_MANUFACTURE',
                value='05/2026',
                source_evidence=[SourceEvidence(image_index=0, token_ids=[12], raw_text='MFG: 05/26')],
            ),
            ResolvedDeclaration(
                field='DECLARED_NET_QUANTITY',
                value='1000 g',
                source_evidence=[SourceEvidence(image_index=0, token_ids=[11], raw_text='MRP Rs. 250')],
            ),
        ]
    )

    validated_result, audit = validator.validate_extraction_result(result)
    assert audit['grounded_count'] == 3
    assert audit['rejected_count'] == 1

    fields = audit['fields']
    assert fields['MANUFACTURER_NAME']['reason'] == 'OCR_FUZZY_ENTITY_MATCH'
    assert fields['MANUFACTURER_NAME']['score'] >= 0.75
    assert fields['MANUFACTURER_NAME']['grounded'] is True

    assert fields['MRP']['reason'] in ('NORMALIZED_MATCH', 'EXACT_MATCH')
    assert fields['MRP']['score'] == 1.0
    assert fields['MRP']['grounded'] is True

    assert fields['MONTH_YEAR_MANUFACTURE']['reason'] == 'DATE_NORMALIZATION'
    assert fields['MONTH_YEAR_MANUFACTURE']['score'] == 1.0
    assert fields['MONTH_YEAR_MANUFACTURE']['grounded'] is True

    assert fields['DECLARED_NET_QUANTITY']['reason'] == 'REJECTED_UNSUPPORTED'
    assert fields['DECLARED_NET_QUANTITY']['grounded'] is False
