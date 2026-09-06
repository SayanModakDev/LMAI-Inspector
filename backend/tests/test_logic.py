import pytest
from app.extraction.declaration_extractor import extract_declarations, merge_product_evidence, merge_extracted_fields
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


def test_multiline_manufacturer():
    """Multiline manufacturer name and continuation lines should be captured cleanly."""
    text = (
        "Manufactured & Marketed by:\n"
        "Apex Beverages Private Limited\n"
        "Plot No. 42, Sector 18, Phase IV\n"
        "Gurugram, Haryana 122015\n"
        "Net Quantity: 750 ml"
    )
    fields = extract_declarations(text)

    assert 'Apex Beverages Private Limited' in fields.get('MANUFACTURER_NAME', {}).get('value', '')
    assert 'Manufactured & Marketed by' in fields.get('MANUFACTURER_NAME', {}).get('value', '')
    assert 'Plot No. 42' in fields.get('MANUFACTURER_ADDRESS', {}).get('value', '')
    assert '122015' in fields.get('MANUFACTURER_ADDRESS', {}).get('value', '')
    assert 'Net Quantity' not in fields.get('MANUFACTURER_ADDRESS', {}).get('value', '')
    assert fields.get('DECLARED_NET_QUANTITY', {}).get('value') == '750 ml'


def test_manufacturer_address_spanning_multiple_lines():
    """Manufacturer address spanning multiple lines should stop at section boundaries."""
    text = (
        "Manufactured by: Sunrise Spice Mills Pvt. Ltd.\n"
        "Survey No. 124/1, GIDC Estate\n"
        "Behind Fire Station, Ankleshwar\n"
        "District Bharuch, Gujarat - 393002\n"
        "MRP: Rs. 140.00"
    )
    fields = extract_declarations(text)

    assert 'Sunrise Spice Mills Pvt. Ltd.' in fields.get('MANUFACTURER_NAME', {}).get('value', '')
    address = fields.get('MANUFACTURER_ADDRESS', {}).get('value', '')
    assert 'Survey No. 124/1' in address
    assert 'Ankleshwar' in address
    assert '393002' in address
    assert 'MRP' not in address
    assert fields.get('MRP', {}).get('value') == '₹140.00'


def test_manufacturer_without_manufactured_by_prefix():
    """Verifiable corporate entity (Pvt. Ltd. / Limited) should be recognized without 'Manufactured by:'."""
    text = (
        "Himalayan Pure Organic Honey\n"
        "Everest Organics India Limited\n"
        "Khasra No. 340, Village Bhowali\n"
        "Dist. Nainital, Uttarakhand - 263132\n"
        "Net Wt: 500 g\n"
        "MRP Rs 350"
    )
    fields = extract_declarations(text)

    assert fields.get('MANUFACTURER_NAME', {}).get('value') == 'Everest Organics India Limited'
    address = fields.get('MANUFACTURER_ADDRESS', {}).get('value', '')
    assert 'Khasra No. 340' in address
    assert '263132' in address
    assert 'Net Wt' not in address
    assert fields.get('DECLARED_NET_QUANTITY', {}).get('value') == '500 g'


def test_ingredients_followed_by_manufacturer_isolation():
    """Ingredients must not bleed into manufacturer and vice-versa."""
    text = (
        "Ingredients: Sugar, Liquid Glucose, Milk Solids, Cocoa Butter, Salt.\n"
        "Manufactured by: Sweet Treats Confectionery Pvt Ltd\n"
        "Industrial Estate, Pune 411028"
    )
    fields = extract_declarations(text)

    ingredients = fields.get('INGREDIENTS_LIST', {}).get('value', '')
    assert 'Sugar' in ingredients
    assert 'Cocoa Butter' in ingredients
    assert 'Manufactured by' not in ingredients
    assert 'Sweet Treats' not in ingredients

    assert 'Sweet Treats Confectionery Pvt Ltd' in fields.get('MANUFACTURER_NAME', {}).get('value', '')
    assert 'Pune 411028' in fields.get('MANUFACTURER_ADDRESS', {}).get('value', '')


def test_ingredients_and_manufacturer_on_same_line_isolation():
    """Inline ingredients followed by manufacturer on the same line must be sliced cleanly."""
    text = (
        "Ingredients: Almonds, Cashews, Pistachios. Manufactured by: Nut Delight Foods Pvt Ltd, Delhi 110006\n"
        "Net Wt: 200 g"
    )
    fields = extract_declarations(text)

    ingredients = fields.get('INGREDIENTS_LIST', {}).get('value', '')
    assert 'Almonds, Cashews, Pistachios.' in ingredients
    assert 'Manufactured by' not in ingredients

    assert 'Nut Delight Foods Pvt Ltd' in fields.get('MANUFACTURER_NAME', {}).get('value', '')
    assert 'Delhi 110006' in fields.get('MANUFACTURER_ADDRESS', {}).get('value', '')
    assert 'Net Wt' not in fields.get('MANUFACTURER_ADDRESS', {}).get('value', '')
    assert fields.get('DECLARED_NET_QUANTITY', {}).get('value') == '200 g'


def test_manufacturer_followed_by_net_quantity():
    """Manufacturer address must not contain trailing net quantity from the same or next line."""
    text = (
        "Manufactured/Packed by: Royal Tea Blends Pvt Ltd, 14 Biplabi Trailokya Maharaj Sarani, Kolkata 700001  Net Weight: 250 g\n"
        "MRP: ₹ 160.00"
    )
    fields = extract_declarations(text)

    assert 'Royal Tea Blends Pvt Ltd' in fields.get('MANUFACTURER_NAME', {}).get('value', '')
    address = fields.get('MANUFACTURER_ADDRESS', {}).get('value', '')
    assert 'Kolkata 700001' in address
    assert 'Net Weight' not in address
    assert '250 g' not in address
    assert fields.get('DECLARED_NET_QUANTITY', {}).get('value') == '250 g'
    assert fields.get('MRP', {}).get('value') == '₹160.00'


def test_ingredients_followed_by_nutrition_information():
    """Ingredients must stop when nutritional panel begins."""
    text = (
        "Ingredients: Whole Wheat Flour, Water, Yeast, Salt, Emulsifiers (INS 471, INS 481).\n"
        "Nutritional Information per 100g:\n"
        "Energy: 245 kcal\n"
        "Protein: 8.2 g\n"
        "Carbohydrate: 49.0 g\n"
        "Fat: 1.5 g\n"
        "Manufactured by: Golden Crust Bakery Pvt Ltd, Mumbai 400050"
    )
    fields = extract_declarations(text)

    ingredients = fields.get('INGREDIENTS_LIST', {}).get('value', '')
    assert 'Whole Wheat Flour' in ingredients
    assert 'INS 481' in ingredients
    assert 'Nutritional Information' not in ingredients
    assert 'Energy' not in ingredients

    nutrition = fields.get('NUTRITIONAL_INFO', {}).get('value', '')
    assert 'Energy' in nutrition
    assert 'Protein' in nutrition


def test_cosmetic_talcum_powder_comprehensive():
    """Comprehensive declaration extraction for cosmetic talcum powder."""
    text = (
        "GREAT DEAL\n"
        "JIVE\n"
        "Fragrant Soft Talc\n"
        "Body Talcum Powder\n"
        "Ingredients: Talc, Calcium Carbonate, Fragrance, Dipropylene Glycol.\n"
        "Manufactured by: Premier Personal Care Pvt Ltd\n"
        "Plot 10, Sector 5, IMT Manesar, Gurugram, Haryana - 122050\n"
        "Net Qty: 300 g\n"
        "MRP: ₹ 180.00\n"
        "Batch No: B4019\n"
        "MFD: 02/2026\n"
        "Best Before: 36 months from mfg\n"
        "Consumer Care: 1800-222-3333, feedback@premiercare.in"
    )
    fields = extract_declarations(text)

    assert fields.get('GENERIC_NAME', {}).get('value') == 'TALCUM POWDER'
    assert 'GREAT DEAL' not in fields.get('PRODUCT_NAME', {}).get('value', '')
    assert 'Talc' in fields.get('INGREDIENTS_LIST', {}).get('value', '')
    assert 'Manufactured by' not in fields.get('INGREDIENTS_LIST', {}).get('value', '')
    assert 'Premier Personal Care Pvt Ltd' in fields.get('MANUFACTURER_NAME', {}).get('value', '')
    assert 'IMT Manesar' in fields.get('MANUFACTURER_ADDRESS', {}).get('value', '')
    assert fields.get('DECLARED_NET_QUANTITY', {}).get('value') == '300 g'
    assert fields.get('MRP', {}).get('value') == '₹180.00'
    assert fields.get('BATCH_NUMBER', {}).get('value') == 'B4019'
    assert fields.get('MANUFACTURE_DATE', {}).get('value') == '02/2026'
    assert '36 months' in fields.get('BEST_BEFORE_USE_BY', {}).get('value', '')
    assert '1800-222-3333' in fields.get('CONSUMER_CARE', {}).get('value', '')


def test_food_packaged_commodity_comprehensive():
    """Comprehensive declaration extraction for food packaged commodity."""
    text = (
        "NUTRIVA\n"
        "Crispy Oats Cookies\n"
        "Ingredients: Rolled Oats, Whole Wheat Flour, Sugar, Edible Vegetable Oil, Butter, Raising Agents (INS 500ii).\n"
        "Nutritional Facts per 100g:\n"
        "Energy: 480 kcal\n"
        "Protein: 8.5 g\n"
        "Manufactured & Marketed by: Healthy Foods India Pvt Ltd\n"
        "Survey No. 88, Village Khed, Pune, Maharashtra 410501\n"
        "Net Weight: 250 g\n"
        "MRP: Rs. 95.00\n"
        "Batch: HF-2026\n"
        "Date of Manufacture: 11/2025\n"
        "Best Before Date: 10/2026\n"
        "Customer Helpline: 1800-444-5555\n"
        "FSSAI Lic No: 10019022000456"
    )
    fields = extract_declarations(text)

    assert 'Rolled Oats' in fields.get('INGREDIENTS_LIST', {}).get('value', '')
    assert 'Nutritional Facts' not in fields.get('INGREDIENTS_LIST', {}).get('value', '')
    assert 'Healthy Foods India Pvt Ltd' in fields.get('MANUFACTURER_NAME', {}).get('value', '')
    assert 'Village Khed' in fields.get('MANUFACTURER_ADDRESS', {}).get('value', '')
    assert 'Net Weight' not in fields.get('MANUFACTURER_ADDRESS', {}).get('value', '')
    assert fields.get('DECLARED_NET_QUANTITY', {}).get('value') == '250 g'
    assert fields.get('MRP', {}).get('value') == '₹95.00'
    assert fields.get('BATCH_NUMBER', {}).get('value') == 'HF-2026'
    assert fields.get('MANUFACTURE_DATE', {}).get('value') == '11/2025'
    assert fields.get('BEST_BEFORE_USE_BY', {}).get('value') == '10/2026'
    assert '1800-444-5555' in fields.get('CONSUMER_CARE', {}).get('value', '')
    assert fields.get('FSSAI_LICENSE', {}).get('value') == '10019022000456'


def test_arbitrary_nearby_text_not_treated_as_manufacturer():
    """Arbitrary descriptive or marketing text must never be treated as manufacturer."""
    text = (
        "Best Quality Premium Salt\n"
        "Vacuum Evaporated\n"
        "Net Wt: 1 kg\n"
        "MRP Rs 28"
    )
    fields = extract_declarations(text)

    assert 'MANUFACTURER_NAME' not in fields
    assert 'MANUFACTURER_ADDRESS' not in fields


def test_food_package_can_evaluate_food_specific_rule():
    """Food packages must be eligible for food-specific rules (PC-FOOD-001..005) and evaluate them."""
    import json
    with open('data/rule_matrix.json', 'r', encoding='utf-8') as f:
        all_rules = json.load(f)['rules']

    food_text = (
        "NUTRIVA CRISPY OATS COOKIES\n"
        "Ingredients: Rolled Oats, Whole Wheat Flour, Sugar, Edible Vegetable Oil.\n"
        "Nutritional Facts per 100g: Energy 480 kcal, Protein 8.5g\n"
        "Net Weight: 250 g\n"
        "MRP: Rs. 95.00\n"
        "FSSAI Lic No: 10019022000456\n"
        "Date of Manufacture: 11/2025\n"
        "Best Before Date: 10/2026\n"
        "Manufactured by: Healthy Foods India Pvt Ltd\n"
        "Consumer Helpline: 1800-444-5555"
    )
    fields = extract_declarations(food_text)
    classification = classify_category(food_text, fields)
    assert classification['category'] == 'FOOD'

    app_rules = get_applicable_rules(all_rules, category=classification['category'], product_type=classification['product_type'])
    app_rule_ids = {r['rule_id'] for r in app_rules}

    # Food-specific rules must be present
    assert 'PC-FOOD-001' in app_rule_ids  # BEST_BEFORE_USE_BY
    assert 'PC-FOOD-002' in app_rule_ids  # INGREDIENTS_LIST
    assert 'PC-FOOD-003' in app_rule_ids  # NUTRITIONAL_INFO
    assert 'PC-FOOD-004' in app_rule_ids  # FSSAI_LICENSE
    assert 'PC-FOOD-005' in app_rule_ids  # VEG_NONVEG_SYMBOL

    # Cosmetic rules must NOT be present
    assert 'PC-COSM-001' not in app_rule_ids
    assert 'PC-COSM-002' not in app_rule_ids
    assert 'PC-COSM-003' not in app_rule_ids

    # Evaluate rules
    results, overall = evaluate_rules(app_rules, fields)
    fssai_res = next(r for r in results if r['rule_id'] == 'PC-FOOD-004')
    assert fssai_res['status'] == 'PASS'
    assert fssai_res['binary'] == 1


def test_cosmetic_package_does_not_receive_veg_nonveg_symbol():
    """Cosmetic packages must NOT receive VEG_NONVEG_SYMBOL evidence or food rules."""
    import json
    with open('data/rule_matrix.json', 'r', encoding='utf-8') as f:
        all_rules = json.load(f)['rules']

    cosmetic_text = (
        "LUMINA GLOW\n"
        "Hydrating Face Cream\n"
        "Personal Care Cosmetic Formulation\n"
        "Ingredients: Aqua, Glycerin, Cetyl Alcohol, Fragrance.\n"
        "Net Wt: 100 g\n"
        "MRP: Rs. 250.00\n"
        "Batch No: LG-402\n"
        "Use before: 12/2026\n"
        "Manufactured by: Lumina Personal Care Pvt Ltd, Mumbai 400001\n"
        "Customer Care: 1800-111-2222"
    )
    # Even if text mentioned 'vegetarian' in a cosmetic marketing context:
    text_with_veg_mention = cosmetic_text + "\n100% Vegetarian herbal extracts"
    fields = extract_declarations(text_with_veg_mention, category='COSMETIC')
    assert 'VEG_NONVEG_SYMBOL' not in fields

    classification = classify_category(text_with_veg_mention, fields)
    assert classification['category'] == 'COSMETIC'

    app_rules = get_applicable_rules(all_rules, category=classification['category'], product_type=classification['product_type'])
    app_rule_ids = {r['rule_id'] for r in app_rules}

    # Food-specific rules must NOT apply to cosmetic
    assert 'PC-FOOD-005' not in app_rule_ids
    assert 'PC-FOOD-004' not in app_rule_ids
    assert 'PC-FOOD-001' not in app_rule_ids

    # Cosmetic rules must apply
    assert 'PC-COSM-001' in app_rule_ids
    assert 'PC-COSM-002' in app_rule_ids
    assert 'PC-COSM-003' in app_rule_ids


def test_cosmetic_talc_remains_cosmetic_talcum_powder():
    """Cosmetic talc package remains firmly COSMETIC / TALCUM_POWDER with zero food rule applicability."""
    import json
    with open('data/rule_matrix.json', 'r', encoding='utf-8') as f:
        all_rules = json.load(f)['rules']

    talc_text = (
        "GREAT DEAL\n"
        "JIVE\n"
        "Fragrant Soft Talc\n"
        "Body Talcum Powder\n"
        "Ingredients: Talc, Calcium Carbonate, Fragrance, Dipropylene Glycol.\n"
        "Manufactured by: Premier Personal Care Pvt Ltd\n"
        "Plot 10, Sector 5, IMT Manesar, Gurugram, Haryana - 122050\n"
        "Net Qty: 300 g\n"
        "MRP: ₹ 180.00\n"
        "Batch No: B4019\n"
        "MFD: 02/2026\n"
        "Best Before: 36 months from mfg\n"
        "Consumer Care: 1800-222-3333, feedback@premiercare.in"
    )
    fields = extract_declarations(talc_text)
    cls = classify_category(talc_text, fields)

    assert cls['category'] == 'COSMETIC'
    assert cls['product_type'] == 'TALCUM_POWDER'
    assert cls['confidence'] >= 0.8

    app_rules = get_applicable_rules(all_rules, category=cls['category'], product_type=cls['product_type'])
    app_rule_ids = {r['rule_id'] for r in app_rules}

    assert 'PC-FOOD-005' not in app_rule_ids
    assert 'PC-COSM-001' in app_rule_ids  # BATCH_NUMBER
    assert 'PC-COSM-002' in app_rule_ids  # INGREDIENTS_LIST


def test_non_food_packages_do_not_receive_food_only_checks():
    """HOUSEHOLD, ELECTRONICS, and unconfident categories do not run food symbol checks or receive PC-FOOD-* rules."""
    import json
    with open('data/rule_matrix.json', 'r', encoding='utf-8') as f:
        all_rules = json.load(f)['rules']

    # 1. Household surface cleaner
    hh_text = (
        "SPARKLE CLEAN\n"
        "Floor Cleaner & Surface Disinfectant\n"
        "Keep out of reach of children\n"
        "Net Volume: 1 L\n"
        "MRP: Rs. 165.00\n"
        "Manufactured by: Sparkle Hygiene Products Ltd, Hyderabad 500032\n"
        "Consumer Support: 1800-555-6666"
    )
    hh_fields = extract_declarations(hh_text)
    hh_cls = classify_category(hh_text, hh_fields)
    assert hh_cls['category'] == 'HOUSEHOLD'

    hh_rules = get_applicable_rules(all_rules, category=hh_cls['category'], product_type=hh_cls['product_type'])
    hh_rule_ids = {r['rule_id'] for r in hh_rules}
    assert 'PC-FOOD-005' not in hh_rule_ids
    assert not any(rid.startswith('PC-FOOD') for rid in hh_rule_ids)

    # 2. Electronics
    elec_text = (
        "VOLTMAX\n"
        "Fast USB-C Charger Adapter\n"
        "Input: 100-240V, Output: 65W\n"
        "Serial Number: SN-998822\n"
        "MRP: Rs. 1499.00\n"
        "Manufactured by: Voltmax Technologies Pvt Ltd, Bengaluru 560001"
    )
    elec_fields = extract_declarations(elec_text)
    elec_cls = classify_category(elec_text, elec_fields)
    assert elec_cls['category'] == 'ELECTRONICS'

    elec_rules = get_applicable_rules(all_rules, category=elec_cls['category'], product_type=elec_cls['product_type'])
    elec_rule_ids = {r['rule_id'] for r in elec_rules}
    assert 'PC-FOOD-005' not in elec_rule_ids
    assert not any(rid.startswith('PC-FOOD') for rid in elec_rule_ids)

    # 3. Unknown / unconfident category
    unk_rules = get_applicable_rules(all_rules, category='UNKNOWN', product_type='UNKNOWN')
    unk_rule_ids = {r['rule_id'] for r in unk_rules}
    assert not any(rid.startswith('PC-FOOD') for rid in unk_rule_ids)
    assert not any(rid.startswith('PC-COSM') for rid in unk_rule_ids)


def test_visual_candidate_alone_never_becomes_legal_pass():
    """Distinguish detector candidate vs verified evidence vs compliance result.
    A visual detector candidate alone must NEVER evaluate to PASS.
    """
    from app.rules.validators import validate_veg_nonveg_present

    rule = {"rule_id": "PC-FOOD-005", "parameter": "VEG_NONVEG_SYMBOL", "required": True}

    # Case 1: Detector candidate from OpenCV
    candidate_evidence = {
        "value": "VEGETARIAN",
        "symbol_type": "VEGETARIAN",
        "source": "VISUAL_DETECTION",
        "status": "CANDIDATE",
        "is_candidate": True,
        "confidence": 0.72,
        "detection_method": "opencv_colored_dot_contour_with_boundary",
    }
    candidate_result = validate_veg_nonveg_present(candidate_evidence, rule, {})
    assert candidate_result.status == "NOT_VERIFIABLE"
    assert candidate_result.binary == 0
    assert "candidate detected" in candidate_result.reason.lower()

    # Case 2: Verified text evidence (OCR declaration)
    verified_evidence = {
        "value": "Vegetarian",
        "source": "OCR",
        "status": "VERIFIED",
        "confidence": 0.85,
    }
    verified_result = validate_veg_nonveg_present(verified_evidence, rule, {})
    assert verified_result.status == "PASS"
    assert verified_result.binary == 1

    # Case 3: Missing evidence
    missing_result = validate_veg_nonveg_present(None, rule, {})
    assert missing_result.status == "NOT_VERIFIABLE"
    assert missing_result.binary == 0


def test_conflicting_mrp_multi_image():
    """Conflicting MRP values across images must NOT silently choose one;
    must produce status=CONFLICTING_EVIDENCE, list distinct values, preserve candidate metadata,
    and rule evaluation must require review (NOT_VERIFIABLE, binary 0).
    """
    img1_fields = {
        'MRP': {'value': '₹120', 'confidence': 0.82, 'source': 'OCR_IMAGE_1', 'source_image_index': 0}
    }
    img2_fields = {
        'MRP': {'value': '₹140', 'confidence': 0.81, 'source': 'OCR_IMAGE_2', 'source_image_index': 1}
    }
    merged = merge_extracted_fields([img1_fields, img2_fields])
    mrp = merged.get('MRP', {})
    assert mrp.get('status') == 'CONFLICTING_EVIDENCE'
    assert mrp.get('has_conflict') is True
    assert set(mrp.get('values', [])) == {'₹120', '₹140'}
    assert len(mrp.get('candidates', [])) == 2
    assert mrp['candidates'][0]['source_image_index'] == 0
    assert mrp['candidates'][1]['source_image_index'] == 1

    # Rule evaluation must require review and never silently PASS
    rule = {'rule_id': 'PC-ALL-002', 'parameter': 'MRP', 'required': True, 'validation_method': 'MRP_PRESENT'}
    results, overall = evaluate_rules([rule], merged)
    assert results[0]['status'] == 'NOT_VERIFIABLE'
    assert results[0]['binary'] == 0
    assert results[0]['review_required'] is True
    assert overall == 'NOT_VERIFIABLE'
    findings = build_inspection_findings(results)
    assert len(findings['needs_review']) == 1


def test_conflicting_product_name_multi_image():
    """Conflicting product names across package views must be flagged as CONFLICTING_EVIDENCE
    and require human review.
    """
    img1_fields = {
        'PRODUCT_NAME': {'value': 'Tata Salt', 'confidence': 0.88, 'source': 'OCR_IMAGE_1', 'source_image_index': 0}
    }
    img2_fields = {
        'PRODUCT_NAME': {'value': 'Aashirvaad Atta', 'confidence': 0.85, 'source': 'OCR_IMAGE_2', 'source_image_index': 1}
    }
    merged = merge_extracted_fields([img1_fields, img2_fields])
    pname = merged.get('PRODUCT_NAME', {})
    assert pname.get('status') == 'CONFLICTING_EVIDENCE'
    assert pname.get('has_conflict') is True
    assert set(pname.get('values', [])) == {'Tata Salt', 'Aashirvaad Atta'}
    assert len(pname.get('candidates', [])) == 2

    rule = {'rule_id': 'PC-ALL-001', 'parameter': 'PRODUCT_NAME', 'required': True, 'validation_method': 'TEXT_PRESENT'}
    results, overall = evaluate_rules([rule], merged)
    assert results[0]['status'] == 'NOT_VERIFIABLE'
    assert results[0]['binary'] == 0
    assert results[0]['review_required'] is True
    assert overall == 'NOT_VERIFIABLE'
    findings = build_inspection_findings(results)
    assert len(findings['needs_review']) == 1


def test_barcode_agrees_with_ocr():
    """When barcode lookup corroborates OCR product name, OCR source is preserved,
    barcode metadata is attached as supplementary evidence, and barcode_match is AGREES.
    """
    ocr_fields = {
        'PRODUCT_NAME': {'value': 'Tata Salt', 'confidence': 0.90, 'source': 'OCR'}
    }
    barcode_result = {
        'value': '8904043901015',
        'confidence': 1.0,
        'lookup': {
            'status': 'FOUND',
            'product_name': 'Tata Salt',
            'brands': 'Tata',
        }
    }
    merged = merge_product_evidence(ocr_fields, '', [], barcode_result)
    pname = merged.get('PRODUCT_NAME', {})
    assert pname.get('value') == 'Tata Salt'
    assert pname.get('source') == 'OCR'
    assert pname.get('barcode_match') == 'AGREES'
    assert pname.get('supplementary_evidence', {}).get('source') == 'BARCODE_LOOKUP'
    assert pname.get('supplementary_evidence', {}).get('evidence_type') == 'SUPPLEMENTARY'
    assert merged.get('BARCODE_METADATA', {}).get('evidence_type') == 'SUPPLEMENTARY'


def test_barcode_conflicts_with_ocr():
    """When barcode lookup contradicts printed OCR, OCR is NOT overwritten;
    the contradiction is exposed as CONFLICTING_EVIDENCE with barcode_match=CONFLICTS,
    and rule evaluation requires review.
    """
    ocr_fields = {
        'PRODUCT_NAME': {'value': 'Aashirvaad Atta', 'confidence': 0.90, 'source': 'OCR'}
    }
    barcode_result = {
        'value': '8904043901015',
        'confidence': 1.0,
        'lookup': {
            'status': 'FOUND',
            'product_name': 'Tata Salt',
            'brands': 'Tata',
        }
    }
    merged = merge_product_evidence(ocr_fields, '', [], barcode_result)
    pname = merged.get('PRODUCT_NAME', {})
    assert pname.get('status') == 'CONFLICTING_EVIDENCE'
    assert pname.get('has_conflict') is True
    assert pname.get('barcode_match') == 'CONFLICTS'
    assert pname.get('ocr_value') == 'Aashirvaad Atta'
    assert pname.get('barcode_value') == 'Tata Salt'
    assert set(pname.get('values', [])) == {'Aashirvaad Atta', 'Tata Salt'}

    rule = {'rule_id': 'PC-ALL-001', 'parameter': 'PRODUCT_NAME', 'required': True, 'validation_method': 'TEXT_PRESENT'}
    results, _ = evaluate_rules([rule], merged)
    assert results[0]['status'] == 'NOT_VERIFIABLE'
    assert results[0]['binary'] == 0
    assert results[0]['review_required'] is True


def test_barcode_lookup_unavailable():
    """When barcode lookup is UNAVAILABLE or NOT_FOUND, the scan proceeds with OCR evidence
    without crashing or raising false conflicts.
    """
    ocr_fields = {
        'PRODUCT_NAME': {'value': 'Britannia Good Day', 'confidence': 0.88, 'source': 'OCR'}
    }
    barcode_result = {
        'value': '8901030383424',
        'confidence': 1.0,
        'lookup': {
            'status': 'UNAVAILABLE',
            'source': 'Open Food Facts',
        }
    }
    merged = merge_product_evidence(ocr_fields, '', [], barcode_result)
    pname = merged.get('PRODUCT_NAME', {})
    assert pname.get('value') == 'Britannia Good Day'
    assert pname.get('source') == 'OCR'
    assert pname.get('status') != 'CONFLICTING_EVIDENCE'
    assert pname.get('has_conflict') is not True


def test_multi_image_higher_confidence_vs_lower_confidence_conflict():
    """A higher-confidence candidate (.92) must NOT silently overwrite or discard a
    differing lower-confidence candidate (.65). Both must be captured as CONFLICTING_EVIDENCE.
    """
    img1_fields = {
        'MRP': {'value': '₹250', 'confidence': 0.92, 'source': 'OCR_IMAGE_1', 'source_image_index': 0}
    }
    img2_fields = {
        'MRP': {'value': '₹280', 'confidence': 0.65, 'source': 'OCR_IMAGE_2', 'source_image_index': 1}
    }
    merged = merge_extracted_fields([img1_fields, img2_fields])
    mrp = merged.get('MRP', {})
    assert mrp.get('status') == 'CONFLICTING_EVIDENCE'
    assert mrp.get('has_conflict') is True
    assert mrp.get('value') != '₹250'
    assert set(mrp.get('values', [])) == {'₹250', '₹280'}
    assert len(mrp.get('candidates', [])) == 2

    rule = {'rule_id': 'PC-ALL-002', 'parameter': 'MRP', 'required': True, 'validation_method': 'MRP_PRESENT'}
    results, _ = evaluate_rules([rule], merged)
    assert results[0]['status'] == 'NOT_VERIFIABLE'
    assert results[0]['binary'] == 0
    assert results[0]['review_required'] is True


def test_history_filter_supports_both_hyphen_and_underscore_status():
    """Verify backend get_history accepts both 'NON-COMPLIANT' and 'NON_COMPLIANT',
    as well as 'NOT_VERIFIABLE' and 'NEEDS_REVIEW'.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database.connection import SessionLocal
    from app.database import models

    client = TestClient(app)
    db = SessionLocal()
    try:
        insp = models.Inspection(
            product_name="Test Product Status Mismatch",
            category="FOOD",
            overall_result="NON-COMPLIANT"
        )
        db.add(insp)
        db.commit()
        db.refresh(insp)

        # Test querying with NON_COMPLIANT
        resp1 = client.get("/api/history?status=NON_COMPLIANT")
        assert resp1.status_code == 200
        ids1 = [item["id"] for item in resp1.json()]
        assert insp.id in ids1

        # Test querying with NON-COMPLIANT
        resp2 = client.get("/api/history?status=NON-COMPLIANT")
        assert resp2.status_code == 200
        ids2 = [item["id"] for item in resp2.json()]
        assert insp.id in ids2
    finally:
        db.close()


def test_inspection_detail_serializes_binary_and_quantity_fields():
    """Verify get_inspection_detail enriches rule results with binary,
    quantity_present, unit_present, and quantity_unit_valid.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database.connection import SessionLocal
    from app.database import models

    client = TestClient(app)
    db = SessionLocal()
    try:
        insp = models.Inspection(
            product_name="Test Detail Inspection",
            category="FOOD",
            overall_result="COMPLIANT"
        )
        db.add(insp)
        db.commit()
        db.refresh(insp)

        rr = models.RuleResult(
            inspection_id=insp.id,
            rule_id="PC-G-001",
            parameter="DECLARED_NET_QUANTITY",
            status="PASS",
            message="Valid quantity (500) and unit (g)",
            evidence_data={
                "value": "500",
                "unit": "g",
                "quantity_present": True,
                "unit_present": True,
                "quantity_unit_valid": True,
                "binary": 1
            }
        )
        db.add(rr)
        db.commit()

        resp = client.get(f"/api/inspection/{insp.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "rule_results" in data
        assert len(data["rule_results"]) > 0
        rule_res = data["rule_results"][0]
        assert rule_res["binary"] == 1
        assert rule_res["value"] == "500"
        assert rule_res["unit"] == "g"
        assert rule_res["quantity_present"] is True
        assert rule_res["unit_present"] is True
        assert rule_res["quantity_unit_valid"] is True
    finally:
        db.close()


def test_history_filter_and_counts_each_status():
    """Verify get_history filters each status (COMPLIANT, NON_COMPLIANT, NOT_VERIFIABLE,
    NOT_APPLICABLE) and returns package_type and import_status matching actual record.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database.connection import SessionLocal
    from app.database import models

    client = TestClient(app)
    db = SessionLocal()
    try:
        # Create records across all canonical and legacy states
        i_comp = models.Inspection(
            product_name="Product Compliant",
            category="FOOD",
            package_type="RETAIL",
            import_status="DOMESTIC",
            overall_result="COMPLIANT"
        )
        i_non_comp1 = models.Inspection(
            product_name="Product Non-Compliant Underscore",
            category="FOOD",
            package_type="WHOLESALE",
            import_status="IMPORTED",
            overall_result="NON_COMPLIANT"
        )
        i_non_comp2 = models.Inspection(
            product_name="Product Non-Compliant Hyphen",
            category="COSMETIC",
            package_type="INSTITUTIONAL",
            import_status="DOMESTIC",
            overall_result="NON-COMPLIANT"
        )
        i_review = models.Inspection(
            product_name="Product Review",
            category="FOOD",
            package_type="RETAIL",
            import_status="DOMESTIC",
            overall_result="NOT_VERIFIABLE"
        )
        i_na = models.Inspection(
            product_name="Product NA",
            category="COSMETIC",
            package_type="RETAIL",
            import_status="DOMESTIC",
            overall_result="NOT_APPLICABLE"
        )
        db.add_all([i_comp, i_non_comp1, i_non_comp2, i_review, i_na])
        db.commit()
        for rec in [i_comp, i_non_comp1, i_non_comp2, i_review, i_na]:
            db.refresh(rec)

        # 1. Filter COMPLIANT
        resp = client.get("/api/history?status=COMPLIANT")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert i_comp.id in ids
        assert i_non_comp1.id not in ids

        # 2. Filter NON_COMPLIANT (must match BOTH canonical NON_COMPLIANT and legacy NON-COMPLIANT)
        resp = client.get("/api/history?status=NON_COMPLIANT")
        assert resp.status_code == 200
        items = resp.json()
        ids = [item["id"] for item in items]
        assert i_non_comp1.id in ids
        assert i_non_comp2.id in ids
        assert i_comp.id not in ids
        # Verify package_type and import_status match actual record
        item_non1 = next(item for item in items if item["id"] == i_non_comp1.id)
        assert item_non1["package_type"] == "WHOLESALE"
        assert item_non1["import_status"] == "IMPORTED"
        assert item_non1["overall_result"] == "NON_COMPLIANT"

        # 3. Filter NOT_VERIFIABLE
        resp = client.get("/api/history?status=NOT_VERIFIABLE")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert i_review.id in ids
        assert i_comp.id not in ids

        # 4. Filter NOT_APPLICABLE
        resp = client.get("/api/history?status=NOT_APPLICABLE")
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert i_na.id in ids

        # 5. Verify Dashboard Counts
        dash_resp = client.get("/api/dashboard")
        assert dash_resp.status_code == 200
        stats = dash_resp.json()
        assert stats["total_inspections"] >= 5
        assert stats["compliant"] >= 1
        assert stats["non_compliant"] >= 2  # Counts both NON_COMPLIANT and NON-COMPLIANT
        assert stats["not_verifiable"] >= 1
        assert stats["not_applicable"] >= 1

        # Verify recent_inspections structure
        assert len(stats["recent_inspections"]) > 0
        recent_first = stats["recent_inspections"][0]
        assert "package_type" in recent_first
        assert "import_status" in recent_first
        assert "result" in recent_first
    finally:
        db.close()

