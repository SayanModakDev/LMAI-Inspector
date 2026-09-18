"""
Semantic Evidence Resolver orchestrating Gemini LLM resolution, deterministic grounding validation,
and hybrid merging with rule-based candidate extractions.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import get_settings
from app.llm.gemini_client import GeminiClient
from app.llm.grounding_validator import EvidenceGroundingValidator
from app.llm.schemas import (
    CandidateValue,
    LLMExtractionResult,
    PackageContext,
    ResolvedDeclaration,
    SourceEvidence,
)

logger = logging.getLogger(__name__)

CANONICAL_FIELDS_PROMPT_DOC = """
CANONICAL DECLARATIONS TO IDENTIFY AND RESOLVE:
1. PRODUCT_NAME: Commercial product title (e.g. 'Nutriva Crispy Oats Cookies', 'Lumina Glow Face Cream'). Distinct from brand or lone generic commodity name.
2. BRAND: Distinct commercial brand or trademark (e.g. 'Nutriva', 'Lumina', 'Tata', 'Nestle').
3. GENERIC_NAME: Common or generic name of the commodity (e.g. 'Cookies', 'Face Cream', 'Crystal Sugar', 'Edible Vegetable Oil').
4. DECLARED_NET_QUANTITY: Declared net weight, volume, or count with legal metric unit (e.g. '500 g', '1 kg', '750 ml', '100 N'). For multipacks (e.g. '10 x 50 g'), preserve the exact printed statement in value and source_evidence.
5. MRP: Maximum Retail Price in Indian currency inclusive of taxes (e.g. '₹ 95.00', 'Rs. 50.00', 'MRP Rs 150/- (Incl. of all taxes)').
6. MANUFACTURER_NAME: Name of the manufacturer entity (e.g. 'ABC Foods Private Limited').
7. MANUFACTURER_ADDRESS: Factory or registered premises address of the manufacturer, including town/city, state, PIN code.
8. PACKER_NAME: Name of packing entity where packaging is done by a third party.
9. PACKER_ADDRESS: Complete postal address of the packer.
10. MARKETER_NAME: Name of marketing/distribution company (e.g. 'XYZ Consumer Products Ltd'). Must NOT be collapsed into manufacturer.
11. MARKETER_ADDRESS: Postal address of the marketer.
12. IMPORTER_NAME_ADDRESS: Complete name and address of the importer for imported goods.
13. COUNTRY_OF_ORIGIN: Declared country of manufacture/origin (e.g. 'India', 'Made in Germany', 'Product of USA').
14. MONTH_YEAR_MANUFACTURE: Date or month & year of manufacturing (e.g. '05/2024', 'MAY/24', '15/01/2024').
15. PACKING_DATE: Date or month & year of packaging where distinct from manufacture date.
16. EXPIRY_DATE: Stated expiry date (e.g. '18/04/2027', 'EXP: 10/26').
17. BEST_BEFORE_USE_BY: 'Best Before' period or date (e.g. '12 months from manufacture', 'Best Before 30/08/2027') or 'Use by' date.
18. BATCH_NUMBER: Distinct batch, lot, or code number (e.g. 'B-9921', 'Lot No. 402', 'B.No. 12/A').
19. CONSUMER_CARE: Customer helpline telephone, email, and consumer care officer contact address.
20. FSSAI_LICENSE: 14-digit statutory FSSAI license number (food products).
21. INGREDIENTS_LIST: Complete list of ingredients.
22. NUTRITIONAL_INFO: Nutritional facts/information table per 100g or per serve.
"""


def _format_ocr_tokens_for_prompt(ocr_items: List[Dict[str, Any]], max_tokens: int = 400) -> str:
    """Format OCR items into a token index table for Gemini context."""
    lines = []
    for item in ocr_items[:max_tokens]:
        t_id = item.get("token_id", 0)
        img_idx = item.get("image_index", 0)
        text = str(item.get("text", "")).strip()
        conf = round(float(item.get("confidence", 1.0)), 2)
        bbox = item.get("bbox")
        lines.append(f"[{t_id}] img={img_idx} conf={conf} text={json.dumps(text)} bbox={bbox}")
    return "\n".join(lines)


def _format_deterministic_candidates_for_prompt(deterministic_fields: Dict[str, Any]) -> str:
    """Format existing deterministic candidates as baseline hints for the LLM."""
    if not deterministic_fields:
        return "None"
    lines = []
    for f_name, f_val in deterministic_fields.items():
        if isinstance(f_val, dict):
            val = f_val.get("value")
            src = f_val.get("source", "OCR")
            conf = f_val.get("confidence")
            lines.append(f"- {f_name}: value={json.dumps(str(val))} (source={src}, conf={conf})")
    return "\n".join(lines) if lines else "None"


def build_evidence_resolver_prompt(
    ocr_items: List[Dict[str, Any]],
    raw_text: str,
    num_images: int,
    deterministic_fields: Dict[str, Any],
    barcode_result: Optional[Dict[str, Any]] = None,
) -> str:
    """Build complete structured evidence resolver prompt."""
    tokens_section = _format_ocr_tokens_for_prompt(ocr_items)
    candidates_section = _format_deterministic_candidates_for_prompt(deterministic_fields)

    barcode_info = "None detected"
    if barcode_result and barcode_result.get("value"):
        barcode_info = f"Value={barcode_result.get('value')}, Type={barcode_result.get('type')}"
        if barcode_result.get("lookup"):
            barcode_info += f", Lookup={barcode_result.get('lookup')}"

    prompt = f"""EVIDENCE INTERPRETATION TASK:
Analyze the OCR tokens detected on {num_images} package panel(s).
Extract, reconstruct broken text lines, associate labels with their values, and resolve canonical packaging declarations.

{CANONICAL_FIELDS_PROMPT_DOC}

BARCODE EVIDENCE:
{barcode_info}

EXISTING RULE-BASED CANDIDATES (For reference/hints):
{candidates_section}

DETECTED OCR TOKENS:
Format: [token_id] img=image_index conf=confidence text="detected text" bbox=[x1,y1,x2,y2]
{tokens_section}

FULL RAW OCR TEXT:
\"\"\"
{raw_text[:4000]}
\"\"\"

INSTRUCTIONS FOR EVIDENCE RESOLUTION:
1. For every resolved declaration:
   - Provide the field name.
   - Provide the resolved value and normalized_value.
   - Set status strictly to:
     * 'RESOLVED' if declaration is clearly detected and grounded.
     * 'CONFLICT' if two or more genuinely conflicting declarations exist across panels and cannot be reconciled.
     * 'NOT_FOUND' if the declaration is not present in the evidence.
   - Include 'source_evidence' listing:
     * image_index (0-based)
     * token_ids (list of integer token IDs from the tokens table above)
     * raw_text (the actual text as detected in those tokens)
     * bbox ([x1, y1, x2, y2])
   - If genuine alternatives exist, add them to 'alternatives'.
   - Provide a short factual 'resolution_note'.
2. Provide 'package_context':
   - category: FOOD, COSMETIC, HOUSEHOLD, or UNKNOWN
   - product_type: specific commodity type (e.g. BISCUIT, SALT, TALCUM_POWDER, OIL)
   - package_type: RETAIL, WHOLESALE, or NOT_DETECTED
   - import_status: DOMESTIC, IMPORTED, or NOT_DETECTED
   - confidence and reasoning.
3. Every referenced token ID MUST exist in the tokens table above. Do NOT hallucinate token IDs.
"""
    return prompt


def resolve_evidence_with_gemini(
    ocr_items: List[Dict[str, Any]],
    raw_text: str,
    num_images: int,
    deterministic_fields: Dict[str, Any],
    barcode_result: Optional[Dict[str, Any]] = None,
    client: Optional[GeminiClient] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[PackageContext]]:
    """
    Main entry point for Gemini Semantic Evidence Resolution.

    Pipeline:
    1. Check if Gemini enabled; if not, return deterministic fields directly.
    2. Format prompt with OCR token IDs and baseline candidates.
    3. Call GeminiClient structured extraction (with primary/fallback model switching).
    4. Pass result through deterministic EvidenceGroundingValidator.
    5. Hybrid merge validated LLM declarations with deterministic candidates.
    6. Return merged fields, audit metadata, and inferred package context.
    """
    settings = get_settings()
    gemini_client = client or GeminiClient()

    timing_start = time.perf_counter()
    llm_metadata: Dict[str, Any] = {
        "llm_enabled": gemini_client.is_enabled(),
        "llm_model": settings.GEMINI_MODEL,
        "llm_fallback_model": settings.GEMINI_FALLBACK_MODEL,
        "llm_status": "DISABLED" if not gemini_client.is_enabled() else "PENDING",
        "llm_processing_time_ms": 0,
        "grounding_ms": 0,
        "resolver_version": "gemini_v1.0",
        "grounding_audit": None,
    }

    # If disabled or no OCR tokens, fall back gracefully
    if not gemini_client.is_enabled() or not ocr_items:
        if not ocr_items:
            llm_metadata["llm_status"] = "FALLBACK_RULE_BASED"
            llm_metadata["notes"] = "No OCR tokens detected; relying on deterministic extractor."
        else:
            llm_metadata["llm_status"] = "DISABLED"
        return deterministic_fields, llm_metadata, None

    # Step 1: Build prompt
    prompt = build_evidence_resolver_prompt(
        ocr_items=ocr_items,
        raw_text=raw_text,
        num_images=num_images,
        deterministic_fields=deterministic_fields,
        barcode_result=barcode_result,
    )

    # Step 2: Execute LLM Structured Extraction
    llm_result, client_meta = gemini_client.generate_structured_extraction(prompt)
    llm_metadata.update(client_meta)

    if not llm_result:
        logger.info("Gemini resolution unavailable (%s); using deterministic candidates.", llm_metadata["llm_status"])
        return deterministic_fields, llm_metadata, None

    # Step 3: Grounding & Hallucination Validation
    grounding_start = time.perf_counter()
    validator = EvidenceGroundingValidator(
        ocr_items=ocr_items,
        num_images=num_images,
        min_confidence=settings.GEMINI_MIN_CONFIDENCE,
    )
    validated_result, grounding_audit = validator.validate_extraction_result(llm_result)
    grounding_ms = round((time.perf_counter() - grounding_start) * 1000)
    llm_metadata["grounding_ms"] = grounding_ms
    llm_metadata["grounding_audit"] = grounding_audit

    # Step 4: Hybrid Merge into canonical extracted_fields format
    merged_fields = dict(deterministic_fields)

    for decl in validated_result.resolved_declarations:
        field_name = decl.field
        det_candidate = deterministic_fields.get(field_name)

        if decl.status == "RESOLVED" and decl.value:
            # Construct unified canonical field dictionary
            source_img_idx = decl.source_evidence[0].image_index if decl.source_evidence else 0
            unified_bbox = decl.source_evidence[0].bbox if decl.source_evidence else None
            ocr_conf = decl.source_evidence[0].ocr_confidence if decl.source_evidence else 0.9

            merged_field = {
                "value": decl.value,
                "normalized_value": decl.normalized_value or decl.value,
                "confidence": round(decl.confidence, 3),
                "source": "OCR_GEMINI_RESOLVED",
                "extraction_method": "GEMINI_SEMANTIC_RESOLVER",
                "source_image_index": source_img_idx,
                "bbox": unified_bbox,
                "ocr_confidence": ocr_conf,
                "resolution_note": decl.resolution_note,
                "source_evidence": [ev.model_dump() for ev in decl.source_evidence],
                "status": "VALID",
                "evidence_state": "EVIDENCE_VERIFIED",
                "candidates": (
                    det_candidate.get("candidates", [det_candidate])
                    if det_candidate and isinstance(det_candidate, dict)
                    else []
                ),
            }

            # Special preservation of unit/quantity attributes for DECLARED_NET_QUANTITY
            if field_name == "DECLARED_NET_QUANTITY":
                from app.core.ontology import extract_quantity_value_unit
                q_val, q_unit, _ = extract_quantity_value_unit(decl.normalized_value or decl.value)
                merged_field["quantity_value"] = q_val
                merged_field["quantity_unit"] = q_unit
                merged_field["quantity_present"] = bool(q_val)
                merged_field["unit_present"] = bool(q_unit)
                merged_field["quantity_unit_valid"] = bool(q_val and q_unit)

            merged_fields[field_name] = merged_field

        elif decl.status == "CONFLICT":
            # True conflict confirmed by LLM evidence interpretation
            merged_fields[field_name] = {
                "value": decl.value or "CONFLICTING_DECLARATIONS",
                "confidence": decl.confidence,
                "source": "OCR_GEMINI_RESOLVED",
                "status": "CONFLICTING_EVIDENCE",
                "has_conflict": True,
                "conflict_reason": decl.resolution_note or f"Conflicting declarations detected for {field_name}",
                "alternatives": [alt.model_dump() for alt in decl.alternatives],
                "source_evidence": [ev.model_dump() for ev in decl.source_evidence],
            }

        elif decl.status == "NOT_FOUND":
            # If Gemini explicitly says NOT_FOUND but deterministic found a plausible candidate,
            # retain deterministic candidate with lowered confidence for inspector review
            if det_candidate and det_candidate.get("value"):
                det_copy = dict(det_candidate)
                det_copy.setdefault("review_notes", "Deterministic candidate unconfirmed by semantic resolver")
                merged_fields[field_name] = det_copy

    total_resolver_ms = round((time.perf_counter() - timing_start) * 1000)
    llm_metadata["total_resolver_ms"] = total_resolver_ms

    logger.info(
        "Gemini evidence resolution completed in %d ms (status=%s, grounded=%d, rejected=%d)",
        total_resolver_ms,
        llm_metadata["llm_status"],
        grounding_audit.get("grounded_count", 0),
        grounding_audit.get("rejected_count", 0),
    )

    return merged_fields, llm_metadata, validated_result.package_context
