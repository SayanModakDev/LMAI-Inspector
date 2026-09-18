"""Evidence-weighted packaged-product category and type classifier.

This is deliberately vocabulary/data driven rather than a collection of product
exceptions: declarations such as ingredients occur in more than one category,
so category-exclusive product terminology is weighted more strongly.
"""
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CATEGORY_VOCABULARY = {
    'FOOD': {
        'strong': ['fssai', 'edible', 'food safety', 'nutrition facts', 'nutritional information', 'vegetarian', 'non-vegetarian', 'allergen', 'serving size'],
        'terms': ['salt', 'sugar', 'biscuit', 'cookie', 'spice', 'masala', 'rice', 'flour', 'tea', 'coffee', 'beverage', 'juice', 'milk', 'edible oil', 'ghee', 'cereal', 'snack'],
    },
    'COSMETIC': {
        'strong': ['cosmetic', 'for external use only', 'dermatologically', 'fragrant talc', 'body talc', 'talcum powder', 'face powder', 'personal care'],
        'terms': ['talc', 'powder', 'shampoo', 'conditioner', 'moisturizer', 'moisturiser', 'deodorant', 'perfume', 'lotion', 'face wash', 'body wash', 'sunscreen', 'lipstick', 'soap', 'hair oil', 'skin care'],
    },
    'HOUSEHOLD': {
        'strong': ['keep out of reach of children', 'surface cleaner', 'toilet cleaner'],
        'terms': ['detergent', 'dishwash', 'dish wash', 'floor cleaner', 'cleaner', 'disinfectant', 'bleach', 'laundry'],
    },
    'PHARMACEUTICAL': {
        'strong': ['schedule h', 'prescription', 'drug licence', 'dosage'],
        'terms': ['tablet', 'capsule', 'ointment', 'syrup', 'medicinal', 'pharmaceutical', 'health supplement'],
    },
    'ELECTRONICS': {
        'strong': ['serial number', 'voltage', 'wattage'],
        'terms': ['charger', 'battery', 'adapter', 'electronic', 'power rating', 'volts', 'watts'],
    },
}

PRODUCT_TYPES = {
    'SALT': ('FOOD', ['salt', 'iodised salt', 'iodized salt']),
    'SUGAR': ('FOOD', ['crystal sugar', 'granulated sugar', 'sugar']),
    'BISCUIT': ('FOOD', ['biscuit', 'cookie']),
    'SPICE': ('FOOD', ['spice', 'masala', 'turmeric', 'pepper', 'chilli']),
    'BEVERAGE': ('FOOD', ['beverage', 'juice', 'soft drink', 'tea', 'coffee']),
    'PACKAGED_GRAIN': ('FOOD', ['rice', 'flour', 'wheat', 'dal', 'grain']),
    'EDIBLE_OIL': ('FOOD', ['edible oil', 'cooking oil', 'mustard oil', 'sunflower oil']),
    'TALCUM_POWDER': ('COSMETIC', ['talcum powder', 'body talc', 'soft talc', 'face powder', 'talc']),
    'SHAMPOO': ('COSMETIC', ['shampoo']), 'CONDITIONER': ('COSMETIC', ['conditioner']),
    'SOAP': ('COSMETIC', ['soap']), 'FACE_CREAM': ('COSMETIC', ['face cream', 'moisturizer', 'moisturiser']),
    'LOTION': ('COSMETIC', ['body lotion', 'lotion']), 'DEODORANT': ('COSMETIC', ['deodorant']),
    'HAIR_OIL': ('COSMETIC', ['hair oil']), 'DETERGENT': ('HOUSEHOLD', ['detergent']),
    'CLEANER': ('HOUSEHOLD', ['floor cleaner', 'dishwash', 'cleaner']),
}


def _contains(text: str, phrase: str) -> bool:
    return re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', text) is not None


def infer_product_type(text: str) -> tuple[str, str, float]:
    text = (text or '').lower()
    matches = []
    for product_type, (category, terms) in PRODUCT_TYPES.items():
        score = sum(1 for term in terms if _contains(text, term))
        if score:
            # Specific multiword product terms are more reliable than lone words.
            score += max(len(term.split()) for term in terms if _contains(text, term)) * .6
            matches.append((score, product_type, category))
    if not matches:
        return 'UNKNOWN', 'UNKNOWN', 0.0
    score, product_type, category = max(matches)
    return product_type, category, min(.95, .58 + score * .1)


def classify_category(text: str, extracted_fields: Optional[Dict[str, Any]] = None, threshold: float = .6) -> Dict[str, Any]:
    evidence_text = ' '.join([text or ''] + [str(field.get('value', '')) for field in (extracted_fields or {}).values()]).lower()
    product_type, type_category, type_confidence = infer_product_type(evidence_text)
    scores, matches = {}, {}
    for category, vocab in CATEGORY_VOCABULARY.items():
        strong = [term for term in vocab['strong'] if _contains(evidence_text, term)]
        terms = [term for term in vocab['terms'] if _contains(evidence_text, term)]
        scores[category] = len(strong) * 4 + len(terms) * 1.5
        matches[category.lower()] = (strong + terms)[:12]
    if type_category != 'UNKNOWN':
        scores[type_category] += 5
        matches[type_category.lower()].append(f'{product_type} (product type)')
    # FSSAI is category-exclusive; generic "ingredients" intentionally is not.
    if extracted_fields and extracted_fields.get('FSSAI_LICENSE'):
        scores['FOOD'] += 5
        matches['food'].append('FSSAI license')
    best_category = max(scores, key=scores.get)
    total = sum(scores.values())
    confidence = (scores[best_category] / total) if total else 0.0
    category = best_category if scores[best_category] and (confidence >= threshold or best_category == type_category) else 'UNKNOWN'
    return {
        'category': category, 'confidence': round(min(.95, max(confidence, type_confidence if category == type_category else 0)), 3),
        'product_type': product_type, 'common_name': (extracted_fields or {}).get('GENERIC_NAME', {}).get('value'),
        'scores': {name: round(value, 2) for name, value in scores.items()}, 'matched_keywords': matches,
    }
