import pytest
from app.extraction.declaration_extractor import extract_declarations, merge_product_evidence
from app.classification.category_classifier import classify_category
from app.rules.applicability import get_applicable_rules
from app.rules.rule_engine import evaluate_rules, build_inspection_findings
from app.barcode_decoder import decode_barcodes


def test_declaration_extractor_handles_common_packaged_commmodity_labels():
    # Realistic packaging OCR text covering the main declarations we need to extract.
    ocr_text = (
        "Saffola Active Oil\n"
        "M.R.P. Rs. 199.00\n"
        "Net Wt. 500 g\n"
        "Mfd. 10/2025\n"
        "Manufactured by: Shree Foods Pvt Ltd, Plot 12, Industrial Area, Delhi 110001\n"
        "Consumer care: 1800-123-4567\n"
        "FSSAI Lic. No. 12345678901234"
    )
    fields = extract_declarations(ocr_text)

    assert fields.get('MRP', {}).get('value') == '₹199.00'
    assert fields.get('DECLARED_NET_QUANTITY', {}).get('quantity_value') == '500'
    assert fields.get('MONTH_YEAR_MANUFACTURE', {}).get('value') == '10/2025'
    assert 'Manufactured by' in (fields.get('MANUFACTURER_NAME', {}).get('value') or '')
    assert '1800' in (fields.get('CONSUMER_CARE', {}).get('value') or '')
    assert fields.get('FSSAI_LICENSE', {}).get('value') == '12345678901234'


def test_category_classifier_detects_food_from_fssai_plus_ingredients():
    text_food = "Ingredients: Sugar, Milk, Cocoa butter. FSSAI Lic No: 12345678901234"
    result = classify_category(text_food)

    assert result.get('category') == 'FOOD'
    assert result.get('confidence', 0) >= 0.6


def test_product_classifier_identifies_sugar_and_common_name():
    fields = extract_declarations('SUPREME HARVEST\nCRYSTAL SUGAR\nNET WEIGHT: 1 kg')
    result = classify_category('SUPREME HARVEST CRYSTAL SUGAR', fields)

    assert result['category'] == 'FOOD'
    assert result['product_type'] == 'SUGAR'
    assert result['common_name'] == 'CRYSTAL SUGAR'


def test_sugar_does_not_receive_other_food_ingredient_rule():
    rules = get_applicable_rules(
        [
            {'rule_id': 'ingredients', 'parameter': 'INGREDIENTS_LIST', 'category': 'FOOD', 'product_type': 'OTHER_FOOD', 'is_active': True},
            {'rule_id': 'fssai', 'parameter': 'FSSAI_LICENSE', 'category': 'FOOD', 'product_type': 'ALL', 'is_active': True},
        ],
        category='FOOD',
        product_type='SUGAR',
    )

    assert [rule['parameter'] for rule in rules] == ['FSSAI_LICENSE']


def test_rule_engine_uses_packing_and_use_by_aliases():
    rules = [
        {'rule_id': 'date', 'parameter': 'MONTH_YEAR_MANUFACTURE', 'required': True, 'verification_type': 'IMAGE_VERIFIABLE'},
        {'rule_id': 'use-by', 'parameter': 'BEST_BEFORE_USE_BY', 'required': True, 'verification_type': 'IMAGE_VERIFIABLE'},
    ]
    results, overall = evaluate_rules(rules, {
        'PACKING_DATE': {'value': '31/08/2026', 'confidence': 0.8},
        'USE_BEFORE_DATE': {'value': '30/08/2027', 'confidence': 0.8},
    })

    assert [result['status'] for result in results] == ['PASS', 'PASS']
    assert overall == 'COMPLIANT'


def test_rule_engine_missing_evidence_is_not_verifiable():
    applicable_rules = [
        {
            'rule_id': 'PC-ALL-003',
            'parameter': 'MRP',
            'category': 'ALL',
            'package_type': 'RETAIL',
            'required': True,
            'verification_type': 'IMAGE_VERIFIABLE',
            'rule_version': '1.0',
            'severity': 'HIGH',
            'is_active': True,
        }
    ]

    rule_results, overall_result = evaluate_rules(applicable_rules, {})

    assert rule_results[0]['status'] == 'NOT_VERIFIABLE'
    assert overall_result == 'NOT_VERIFIABLE'


def test_rule_engine_weak_ocr_evidence_is_not_verifiable():
    applicable_rules = [
        {
            'rule_id': 'PC-ALL-001',
            'parameter': 'PRODUCT_NAME',
            'category': 'ALL',
            'package_type': 'RETAIL',
            'required': True,
            'verification_type': 'IMAGE_VERIFIABLE',
        }
    ]

    rule_results, overall_result = evaluate_rules(
        applicable_rules,
        {'PRODUCT_NAME': {'value': 'random OCR noise', 'confidence': 0.45, 'source': 'OCR'}},
    )

    assert rule_results[0]['status'] == 'NOT_VERIFIABLE'
    assert overall_result == 'NOT_VERIFIABLE'


def test_extractor_preserves_lines_and_does_not_invent_generic_name():
    fields = extract_declarations('Marketed by: ITC\nManufacturing Value\nFSSAI Lic. No. 12345678901234')

    assert 'PRODUCT_NAME' not in fields
    assert 'GENERIC_NAME' not in fields


def test_barcode_decoder_uses_valid_ean13_from_ocr_when_image_decoder_is_unavailable():
    result = decode_barcodes('missing-image.jpg', 'Barcode 8909081007903')

    assert result['type'] == 'EAN13'
    assert result['value'] == '8909081007903'


def test_applicability():
    mock_rules = [
        {
            "rule_id": "rule_1",
            "parameter": "mrp",
            "category": "ALL",
            "package_type": "WHOLESALE",
            "required": False,
            "is_active": True
        },
        {
            "rule_id": "rule_2",
            "parameter": "mrp",
            "category": "ALL",
            "package_type": "RETAIL",
            "required": True,
            "is_active": True
        }
    ]
    rules = get_applicable_rules(all_rules=mock_rules, package_type="WHOLESALE", import_status="DOMESTIC", category="GENERAL")
    mrp_rule = next((r for r in rules if r['parameter'] == 'mrp'), None)
    if mrp_rule:
        assert mrp_rule.get('required') is False


def test_contextual_product_and_month_year_dates_are_extracted():
    fields = extract_declarations(
        'Balanced Taste\nTATA\nSalt\nVacuum Evaporated Iodised\n'
        'Date of Packaging: JUL/26\nUse By: JUN/28\nNet Wt 1 kg\nMRP Rs. 32.00'
    )
    assert fields['PRODUCT_NAME']['value'] == 'Tata Salt'
    assert fields['BRAND']['value'] == 'Tata'
    assert fields['GENERIC_NAME']['value'] == 'SALT'
    assert fields['PACKING_DATE']['value'] == 'JUL/26'
    assert fields['USE_BEFORE_DATE']['value'] == 'JUN/28'


def test_multiline_manufacturer_consumer_ingredients_nutrition_and_batch():
    fields = extract_declarations(
        'Manufactured by: Tata Chemicals Limited\nP.O. Mithapur, District Devbhumi Dwarka\nGujarat 361345 India\n'
        'Batch No: TS-26A\nIngredients: Iodised salt, potassium iodate\n'
        'Nutritional Information\nServing size 1 g\nSodium 390 mg\n'
        'Consumer Care: Tata Consumer Products\nEmail: care@example.test\nPhone: 1800 1084488\n'
        'FSSAI Lic No: 10014031001025'
    )
    assert 'Tata Chemicals Limited' in fields['MANUFACTURER_NAME']['value']
    assert 'District Devbhumi' in fields['MANUFACTURER_ADDRESS']['value']
    assert fields['BATCH_NUMBER']['value'] == 'TS-26A'
    assert 'potassium iodate' in fields['INGREDIENTS_LIST']['value'].lower()
    assert 'Sodium' in fields['NUTRITIONAL_INFO']['value']
    assert 'care@example.test' in fields['CONSUMER_CARE']['value']
    assert fields['FSSAI_LICENSE']['value'] == '10014031001025'


def test_barcode_lookup_is_merged_as_product_evidence_not_an_isolated_card():
    fields = merge_product_evidence(
        {'PRODUCT_NAME': {'value': 'Balanced', 'confidence': .45, 'source': 'OCR'}}, '', [],
        {'value': '8904043901015', 'confidence': 1.0, 'lookup': {'status': 'FOUND', 'product_name': 'Tata Salt', 'brands': 'Tata'}},
    )
    assert fields['BARCODE']['value'] == '8904043901015'
    assert fields['PRODUCT_NAME']['value'] == 'Tata Salt'
    assert fields['BRAND']['value'] == 'Tata'
    assert fields['GENERIC_NAME']['value'] == 'SALT'


def test_findings_and_explicit_failure_statuses_are_separate_from_not_verifiable():
    results, overall = evaluate_rules([
        {'rule_id': 'pass', 'parameter': 'MRP', 'required': True},
        {'rule_id': 'fail', 'parameter': 'BATCH_NUMBER', 'required': True},
        {'rule_id': 'review', 'parameter': 'FSSAI_LICENSE', 'required': True},
    ], {
        'MRP': {'value': '₹32', 'confidence': .9},
        'BATCH_NUMBER': {'value': 'illegible', 'confidence': .9, 'clearly_invalid': True, 'failure_reason': 'Label explicitly states no batch number.'},
    })
    assert [item['status'] for item in results] == ['PASS', 'FAIL', 'NOT_VERIFIABLE']
    assert overall == 'NON-COMPLIANT'
    findings = build_inspection_findings(results)
    assert findings['verified'] and findings['failed'] and findings['needs_review']


def test_cosmetic_talc_is_not_misclassified_as_beverage_or_promotional_name():
    text = 'GREAT DEAL\nJIVE\nFragrant Soft Talc\nBody Talcum Powder\nIngredients: Talc, fragrance\nNet Qty 300 g'
    fields = extract_declarations(text)
    result = classify_category(text, fields)
    assert result['category'] == 'COSMETIC'
    assert result['product_type'] == 'TALCUM_POWDER'
    assert fields['PRODUCT_NAME']['value'] != 'GREAT DEAL'
    assert fields['GENERIC_NAME']['value'] == 'TALCUM POWDER'
    assert fields['DECLARED_NET_QUANTITY']['value'] == '300 g'


def test_decimal_noise_is_never_a_manufacturing_date():
    fields = extract_declarations('MFD: 0.73\nMRP Rs 220\nUse Before: JUL/26')
    assert 'MONTH_YEAR_MANUFACTURE' not in fields
    assert fields['USE_BEFORE_DATE']['value'] == 'JUL/26'


def test_mfd_followed_by_another_unrelated_date():
    """MFD followed by another unrelated date must not capture the later date."""
    text = "MFD: 10/2025 18/04/2027\nNet Wt: 500 g"
    fields = extract_declarations(text)

    assert fields.get('MANUFACTURE_DATE', {}).get('value') == '10/2025'
    assert fields.get('MONTH_YEAR_MANUFACTURE', {}).get('value') == '10/2025'
    # Unlabelled later date must not be inferred as Best Before, Expiry, or Use By
    assert 'BEST_BEFORE_USE_BY' not in fields
    assert 'USE_BEFORE_DATE' not in fields
    assert 'EXPIRY_DATE' not in fields


def test_manufactured_by_company_name_never_treated_as_date():
    """A token following 'Manufactured by:' must never be treated as a date."""
    text = (
        "Manufactured by: Shree Foods Pvt Ltd\n"
        "Plot 12, Industrial Area, Mumbai 400001\n"
        "18/04/2027\n"
        "Net Weight: 200 g"
    )
    fields = extract_declarations(text)

    assert 'MANUFACTURE_DATE' not in fields
    assert 'MONTH_YEAR_MANUFACTURE' not in fields
    assert 'Manufactured by' in fields.get('MANUFACTURER_NAME', {}).get('value', '')

    # Evaluating rule without verified date returns NOT_VERIFIABLE rather than guessing
    rules = [{'rule_id': 'PC-ALL-009', 'parameter': 'MONTH_YEAR_MANUFACTURE', 'required': True}]
    results, overall = evaluate_rules(rules, fields)
    assert results[0]['status'] == 'NOT_VERIFIABLE'
    assert overall == 'NOT_VERIFIABLE'


def test_best_before_classified_separately():
    """'Best Before' must be classified into BEST_BEFORE_USE_BY and not manufacture/packing date."""
    text = "Best Before: 30/08/2027\nNet Wt: 1 kg"
    fields = extract_declarations(text)

    assert fields.get('BEST_BEFORE_USE_BY', {}).get('value') == '30/08/2027'
    assert 'MANUFACTURE_DATE' not in fields
    assert 'PACKING_DATE' not in fields
    assert 'MONTH_YEAR_MANUFACTURE' not in fields
    assert 'EXPIRY_DATE' not in fields


def test_use_by_classified_separately():
    """'Use By' must be classified into USE_BEFORE_DATE and not manufacture/packing date."""
    text = "Use By: 18/04/2027\nNet Wt: 500 ml"
    fields = extract_declarations(text)

    assert fields.get('USE_BEFORE_DATE', {}).get('value') == '18/04/2027'
    assert 'MANUFACTURE_DATE' not in fields
    assert 'PACKING_DATE' not in fields
    assert 'MONTH_YEAR_MANUFACTURE' not in fields
    assert 'BEST_BEFORE_USE_BY' not in fields


def test_expiry_classified_separately():
    """'Expiry Date' must be classified into EXPIRY_DATE and not manufacture/packing date."""
    text = "Expiry Date: 18/04/2027\nNet Wt: 250 g"
    fields = extract_declarations(text)

    assert fields.get('EXPIRY_DATE', {}).get('value') == '18/04/2027'
    assert 'MANUFACTURE_DATE' not in fields
    assert 'PACKING_DATE' not in fields
    assert 'MONTH_YEAR_MANUFACTURE' not in fields
    assert 'BEST_BEFORE_USE_BY' not in fields


def test_jul_26_style_month_year():
    """JUL/26 style month/year must be parsed cleanly."""
    text = "MFD: JUL/26\nEXP: JUL/28"
    fields = extract_declarations(text)

    assert fields.get('MANUFACTURE_DATE', {}).get('value') == 'JUL/26'
    assert fields.get('MONTH_YEAR_MANUFACTURE', {}).get('value') == 'JUL/26'
    assert fields.get('EXPIRY_DATE', {}).get('value') == 'JUL/28'


def test_date_appearing_near_use_before():
    """18/04/2027 appearing near Use Before must bind to USE_BEFORE_DATE."""
    text = "Use Before: 18/04/2027\nNet Wt: 100 g"
    fields = extract_declarations(text)

    assert fields.get('USE_BEFORE_DATE', {}).get('value') == '18/04/2027'
    assert 'MANUFACTURE_DATE' not in fields
    assert 'MONTH_YEAR_MANUFACTURE' not in fields


def test_decimal_0_73_rejected_as_date():
    """Decimal number 0.73 must never be captured as a date."""
    text = "MFD: 0.73\nMRP Rs 50"
    fields = extract_declarations(text)

    assert 'MANUFACTURE_DATE' not in fields
    assert 'MONTH_YEAR_MANUFACTURE' not in fields


def test_barcode_like_numeric_strings_rejected_as_date():
    """Barcode-like numeric strings must never be captured as dates."""
    text = "MFD: 8901030881234\nBarcode: 8901030881234"
    fields = extract_declarations(text)

    assert 'MANUFACTURE_DATE' not in fields
    assert 'MONTH_YEAR_MANUFACTURE' not in fields


def test_phone_numbers_rejected_as_dates():
    """Phone numbers must never be captured as dates."""
    text = "MFD: 1800-123-4567\nConsumer Care: 1800-123-4567"
    fields = extract_declarations(text)

    assert 'MANUFACTURE_DATE' not in fields
    assert 'MONTH_YEAR_MANUFACTURE' not in fields


def test_same_line_mfd_and_expiry_separated():
    """Multiple date labels on the same line must isolate their dates correctly."""
    text = "MFD: 10/2025  EXP: 18/04/2027"
    fields = extract_declarations(text)

    assert fields.get('MANUFACTURE_DATE', {}).get('value') == '10/2025'
    assert fields.get('MONTH_YEAR_MANUFACTURE', {}).get('value') == '10/2025'
    assert fields.get('EXPIRY_DATE', {}).get('value') == '18/04/2027'

