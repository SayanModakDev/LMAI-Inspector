"""
Semantic Evidence Resolver orchestrating Gemini LLM resolution, deterministic grounding validation,
and hybrid merging with rule-based candidate extractions.
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import get_settings
from app.extraction.declaration_extractor import sanitize_batch_number_field
from app.core.ontology import assess_address_structure, extract_contextual_emails
from app.extraction.declaration_extractor import (
    classify_product_identity_candidate,
    is_valid_date_candidate,
    is_descriptive_product_text,
    _product_names_conflict,
    DATE_FIELDS,
    DATE_PREFIX_RE,
    parse_date_with_precision,
)
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
1. PRODUCT_NAME: Commercial product title (e.g. 'Nutriva Crispy Oats Cookies', 'Lumina Glow Face Cream'). Distinct from brand, variant/flavour-only text, a lone generic commodity name, and descriptive or promotional claims/taglines.
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


ROLE_SPECIFIC_FIELDS = {
    "MANUFACTURER_NAME": {"MANUFACTURER", "PACKER"},
    "MANUFACTURER_ADDRESS": {"MANUFACTURER", "PACKER"},
    "PACKER_NAME": {"PACKER"},
    "PACKER_ADDRESS": {"PACKER"},
    "MARKETER_NAME": {"MARKETER"},
    "MARKETER_ADDRESS": {"MARKETER"},
}


def _has_unresolved_product_identity_conflict(candidate: Optional[Dict[str, Any]]) -> bool:
    """Keep incompatible deterministic product identities under review.

    A grounded semantic selection may discard descriptive/tagline noise, but it
    must not silently choose one of multiple genuinely incompatible identities.
    """
    if not candidate or candidate.get("status") not in ("CONFLICTING_EVIDENCE", "AMBIGUOUS", "REVIEW"):
        return False

    raw_candidates = candidate.get("all_candidates") or candidate.get("candidates") or []
    if not raw_candidates:
        raw_candidates = [{"value": value} for value in candidate.get("values", [])]

    identity_values: List[str] = []
    for item in raw_candidates:
        value = item.get("value") if isinstance(item, dict) else item
        role = str(item.get("candidate_role") or item.get("role") or "").upper() if isinstance(item, dict) else ""
        if not value or (role and role != "PRODUCT_NAME") or is_descriptive_product_text(value):
            continue
        normalized = re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()
        if normalized and normalized not in {
            re.sub(r"[^a-z0-9]+", " ", existing.lower()).strip()
            for existing in identity_values
        }:
            identity_values.append(str(value).strip())

    return any(
        _product_names_conflict(identity_values[left], identity_values[right])
        for left in range(len(identity_values))
        for right in range(left + 1, len(identity_values))
    )


def _llm_has_genuine_product_identity_conflict(declaration: ResolvedDeclaration) -> bool:
    """Accept a semantic conflict only when two eligible product identities remain."""
    candidates: List[Dict[str, Any]] = []
    if declaration.value:
        candidates.append({"value": declaration.value, "confidence": declaration.confidence})
    candidates.extend(
        {
            "value": alternative.value,
            "confidence": alternative.confidence,
            "raw_text": "\n".join(ev.raw_text for ev in alternative.source_evidence if ev.raw_text),
        }
        for alternative in declaration.alternatives
        if alternative.value
    )

    identities: List[str] = []
    for candidate in candidates:
        role, _ = classify_product_identity_candidate(candidate)
        if role != "PRODUCT_NAME":
            continue
        value = str(candidate["value"]).strip()
        normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
        if normalized and normalized not in {
            re.sub(r"[^a-z0-9]+", " ", existing.lower()).strip()
            for existing in identities
        }:
            identities.append(value)

    return any(
        _product_names_conflict(identities[left], identities[right])
        for left in range(len(identities))
        for right in range(left + 1, len(identities))
    )


def _responsible_party_roles(text: str) -> set[str]:
    """Classify explicit responsible-party labels, including narrow OCR damage."""
    roles: set[str] = set()
    value = str(text or "")
    if re.search(
        r'\b(?:manufactur(?:ed|er)\b|mfg\.?\s*by|mfd\.?\s*by|made\s+by\b)',
        value,
        re.IGNORECASE,
    ):
        roles.add("MANUFACTURER")
    if re.search(
        r'\b(?:marketed\b|marketer\b|distributed\s+by\b|m(?:k|kt|ktg)\.?\s*by)',
        value,
        re.IGNORECASE,
    ):
        roles.add("MARKETER")
    if re.search(
        r'\b(?:packed\s+by\b|packaged\s+by\b|packer\b|pkd\.?\s*by\b|pkg\.?\s*by\b)',
        value,
        re.IGNORECASE,
    ):
        roles.add("PACKER")
    return roles


def _resolve_grounded_entity_role(
    source_evidence: List[SourceEvidence],
    ocr_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Resolve an entity role from cited tokens and the nearest spatial label.

    Directly cited labels take precedence.  When an address token does not cite
    its label, only a nearby label above/on the same OCR block and on the same
    image may associate the role.  This prevents text presence elsewhere on the
    package from satisfying a role-specific declaration.
    """
    by_key = {
        (int(item.get("image_index") or 0), int(item.get("token_id"))): item
        for item in ocr_items
        if item.get("token_id") is not None
    }
    direct_roles: set[str] = set()
    direct_texts: List[str] = []
    referenced: List[Dict[str, Any]] = []
    image_indexes: set[int] = set()
    for evidence in source_evidence:
        image_index = int(evidence.image_index)
        image_indexes.add(image_index)
        direct_texts.append(evidence.raw_text)
        direct_roles.update(_responsible_party_roles(evidence.raw_text))
        for token_id in evidence.token_ids:
            token = by_key.get((image_index, int(token_id)))
            if token:
                referenced.append(token)
                token_text = str(token.get("text") or "")
                direct_texts.append(token_text)
                direct_roles.update(_responsible_party_roles(token_text))

    if direct_roles:
        return {
            "roles": sorted(direct_roles),
            "association": "CITED_ROLE_LABEL",
            "source_image_indexes": sorted(image_indexes),
            "combined_label": any(
                re.search(r'manufactur\w*\s*(?:&|and|/)\s*market\w*\s+by', text, re.IGNORECASE)
                for text in direct_texts
            ),
        }

    # Build one evidence union per image. SourceEvidence bboxes are already
    # grounding-validated; referenced token boxes are used as a fallback.
    evidence_boxes: Dict[int, List[List[float]]] = {}
    for evidence in source_evidence:
        if evidence.bbox and len(evidence.bbox) == 4:
            evidence_boxes.setdefault(int(evidence.image_index), []).append(list(evidence.bbox))
    for token in referenced:
        bbox = token.get("bbox") or []
        if len(bbox) == 4:
            evidence_boxes.setdefault(int(token.get("image_index") or 0), []).append(list(bbox))

    anchors: List[Tuple[float, set[str], Dict[str, Any]]] = []
    for image_index, boxes in evidence_boxes.items():
        if not boxes:
            continue
        union = [
            min(box[0] for box in boxes),
            min(box[1] for box in boxes),
            max(box[2] for box in boxes),
            max(box[3] for box in boxes),
        ]
        evidence_height = max(1.0, union[3] - union[1])
        evidence_width = max(1.0, union[2] - union[0])
        for item in ocr_items:
            if int(item.get("image_index") or 0) != image_index:
                continue
            roles = _responsible_party_roles(str(item.get("text") or ""))
            label_box = item.get("bbox") or []
            if not roles or len(label_box) != 4:
                continue
            label_height = max(1.0, label_box[3] - label_box[1])
            vertical_gap = union[1] - label_box[3]
            if vertical_gap < -label_height or vertical_gap > max(140.0, evidence_height * 3.0):
                continue
            overlap = max(0.0, min(union[2], label_box[2]) - max(union[0], label_box[0]))
            horizontal_gap = max(0.0, max(union[0], label_box[0]) - min(union[2], label_box[2]))
            if overlap <= 0 and horizontal_gap > max(80.0, evidence_width * 0.35):
                continue
            score = max(0.0, vertical_gap) + horizontal_gap * 0.25
            anchors.append((score, roles, item))

    if anchors:
        anchors.sort(key=lambda row: row[0])
        best_score, best_roles, best_item = anchors[0]
        # Equally close contradictory labels mean the block association is not
        # deterministic; retain uncertainty instead of choosing one.
        tied_roles: set[str] = set(best_roles)
        for score, roles, _ in anchors[1:]:
            if score <= best_score + 5.0:
                tied_roles.update(roles)
        return {
            "roles": sorted(tied_roles),
            "association": "NEAREST_SPATIAL_ROLE_LABEL",
            "source_image_indexes": [int(best_item.get("image_index") or 0)],
            "label_text": str(best_item.get("text") or ""),
            "label_bbox": best_item.get("bbox"),
        }

    return {
        "roles": [],
        "association": "UNASSOCIATED",
        "source_image_indexes": sorted(image_indexes),
    }


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
4. For MANUFACTURER, PACKER, and MARKETER fields, cite the responsible-party label token
   and its associated value/address block from the same image. Never use marketer-only
   evidence for a manufacturer field. If the role label is absent, damaged beyond a
   deterministic association, or belongs to another entity block, return NOT_FOUND.
"""
    return prompt


def resolve_evidence_with_gemini(
    ocr_items: List[Dict[str, Any]],
    raw_text: str,
    num_images: Optional[int] = None,
    deterministic_fields: Optional[Dict[str, Any]] = None,
    barcode_result: Optional[Dict[str, Any]] = None,
    client: Optional[GeminiClient] = None,
    image_count: Optional[int] = None,
    **kwargs: Any,
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

    total_images = num_images if num_images is not None else (image_count if image_count is not None else 1)
    deterministic_fields = deterministic_fields or {}

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
        sanitize_batch_number_field(deterministic_fields)
        return deterministic_fields, llm_metadata, None

    # Step 1: Build prompt
    prompt = build_evidence_resolver_prompt(
        ocr_items=ocr_items,
        raw_text=raw_text,
        num_images=total_images,
        deterministic_fields=deterministic_fields,
        barcode_result=barcode_result,
    )

    # Step 2: Execute LLM Structured Extraction
    llm_result, client_meta = gemini_client.generate_structured_extraction(prompt)
    llm_metadata.update(client_meta)

    if not llm_result:
        logger.info("Gemini resolution unavailable (%s); using deterministic candidates.", llm_metadata["llm_status"])
        sanitize_batch_number_field(deterministic_fields)
        return deterministic_fields, llm_metadata, None

    # Step 3: Grounding & Hallucination Validation
    grounding_start = time.perf_counter()
    validator = EvidenceGroundingValidator(
        ocr_items=ocr_items,
        num_images=total_images,
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
            source_context = "\n".join(ev.raw_text for ev in decl.source_evidence if ev.raw_text)

            if field_name == "PRODUCT_NAME" and _has_unresolved_product_identity_conflict(det_candidate):
                retained = dict(det_candidate)
                retained["review_notes"] = (
                    "Grounded semantic evidence selected one candidate, but incompatible OCR-supported "
                    "product identities remain unresolved."
                )
                merged_fields[field_name] = retained
                llm_metadata.setdefault("identity_resolution_rejections", []).append({
                    "field": field_name,
                    "value": decl.value,
                    "reason": retained["review_notes"],
                })
                continue

            resolved_role: Optional[str] = None
            if field_name in ROLE_SPECIFIC_FIELDS:
                expected_roles = ROLE_SPECIFIC_FIELDS[field_name]
                role_audit = _resolve_grounded_entity_role(decl.source_evidence, ocr_items)
                cited_roles = set(role_audit.get("roles") or [])
                det_role = str(
                    (det_candidate or {}).get("role")
                    or (det_candidate or {}).get("entity_type")
                    or ""
                ).upper()
                has_ambiguous_role_block = bool(
                    len(cited_roles) > 1 and not role_audit.get("combined_label")
                )

                if cited_roles & expected_roles and not has_ambiguous_role_block:
                    resolved_role = sorted(cited_roles & expected_roles)[0]
                elif not cited_roles and det_role in expected_roles:
                    # A deterministic same-field candidate may already have a
                    # role-labelled block; do not discard that stronger
                    # association merely because Gemini cited only the value.
                    resolved_role = det_role
                    role_audit["association"] = "DETERMINISTIC_ROLE_ASSOCIATION"
                else:
                    rejection = {
                        "field": field_name,
                        "value": decl.value,
                        "expected_roles": sorted(expected_roles),
                        "role_audit": role_audit,
                        "reason": (
                            "Cited evidence spans competing responsible-party roles."
                            if has_ambiguous_role_block
                            else "Cited evidence is not associated with the required entity role."
                        ),
                    }
                    llm_metadata.setdefault("role_resolution_rejections", []).append(rejection)
                    # Retain an independently role-grounded deterministic value,
                    # but never let the semantic candidate overwrite it.
                    if det_candidate and det_role in expected_roles:
                        retained = dict(det_candidate)
                        retained["review_notes"] = rejection["reason"]
                        merged_fields[field_name] = retained
                    else:
                        merged_fields.pop(field_name, None)
                    continue

            # Semantic association cannot turn a marketer/customer-care address
            # into a manufacturer address merely because the text is grounded.
            address_role_conflict = False
            if field_name == "MANUFACTURER_ADDRESS":
                lowered_context = source_context.lower()
                det_role = str((det_candidate or {}).get("role") or (det_candidate or {}).get("entity_type") or "").upper()
                address_role_conflict = bool(
                    det_role == "MARKETER"
                    or (
                        any(marker in lowered_context for marker in ("marketed by", "marketer", "consumer care", "customer care"))
                        and not any(marker in lowered_context for marker in ("manufactured by", "manufacturer", "packed by", "packer"))
                    )
                )
                llm_structure = assess_address_structure(decl.value)
                det_structure = assess_address_structure(str(det_candidate.get("value") or "")) if det_candidate else {"sufficient": False}
                if (not llm_structure["sufficient"] or address_role_conflict) and det_structure["sufficient"] and det_role in ("MANUFACTURER", "PACKER"):
                    retained = dict(det_candidate)
                    retained["review_notes"] = (
                        "Retained fuller role-associated deterministic address; semantic candidate was partial or role-conflicting."
                    )
                    merged_fields[field_name] = retained
                    continue

            # Enforce date eligibility for statutory date fields
            if field_name in DATE_FIELDS:
                val_ok = is_valid_date_candidate(decl.value) or is_valid_date_candidate(decl.normalized_value)
                if not val_ok:
                    logger.info("Rejecting ineligible date candidate for %s: %r", field_name, decl.value)
                    if det_candidate and is_valid_date_candidate(det_candidate.get("value")):
                        merged_fields[field_name] = dict(det_candidate)
                    else:
                        merged_fields[field_name] = {
                            "value": None,
                            "status": "NOT_FOUND",
                            "confidence": 0.0,
                            "review_notes": f"Ineligible date phrase '{decl.value}' rejected by date validator",
                        }
                    continue

            # Construct unified canonical field dictionary
            source_img_idx = decl.source_evidence[0].image_index if decl.source_evidence else 0
            unified_bbox = decl.source_evidence[0].bbox if decl.source_evidence else None
            ocr_conf = decl.source_evidence[0].ocr_confidence if decl.source_evidence else 0.9

            resolved_value = decl.value
            normalized_value = decl.normalized_value or decl.value
            normalized_contacts: List[Dict[str, str]] = []
            if field_name == "CONSUMER_CARE":
                email_context = "\n".join(part for part in (source_context, decl.value) if part)
                for email in extract_contextual_emails(email_context):
                    if email["raw_value"] in resolved_value:
                        resolved_value = resolved_value.replace(email["raw_value"], email["value"])
                    if email["raw_value"] in normalized_value:
                        normalized_value = normalized_value.replace(email["raw_value"], email["value"])
                    normalized_contacts.append({
                        "contact_type": "EMAIL",
                        "contact_value": email["value"],
                        "raw_contact_value": email["raw_value"],
                    })

            merged_field = {
                "value": resolved_value,
                "raw_value": decl.value,
                "raw_text": source_context or decl.value,
                "normalized_value": normalized_value,
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

            if resolved_role:
                merged_field["role"] = resolved_role
                merged_field["role_evidence"] = role_audit

            if normalized_contacts:
                merged_field["contacts"] = normalized_contacts
                merged_field["contact_type"] = normalized_contacts[0]["contact_type"]
                merged_field["contact_value"] = normalized_contacts[0]["contact_value"]

            if field_name == "MANUFACTURER_ADDRESS":
                structure = assess_address_structure(resolved_value)
                merged_field["address_structure"] = structure
                merged_field["address_completeness"] = structure["completeness"]
                if not structure["sufficient"] or address_role_conflict:
                    merged_field["status"] = "PARTIAL"
                    merged_field["evidence_state"] = "EVIDENCE_DETECTED_UNASSOCIATED"
                    merged_field["role"] = "UNASSOCIATED" if address_role_conflict else "MANUFACTURER"
                    merged_field["review_notes"] = (
                        "Grounded address text belongs to a different entity role."
                        if address_role_conflict
                        else "Grounded OCR contains only partial manufacturer-address evidence."
                    )

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
            if field_name in DATE_FIELDS:
                # Filter conflict candidates to only valid date declarations
                valid_date_cands = []
                seen_vals = set()

                if decl.value and decl.value != "CONFLICTING_DECLARATIONS" and is_valid_date_candidate(decl.value):
                    clean_v = decl.value.strip()
                    if clean_v.lower() not in seen_vals:
                        seen_vals.add(clean_v.lower())
                        valid_date_cands.append({
                            "value": clean_v,
                            "confidence": decl.confidence,
                            "source_evidence": decl.source_evidence,
                            "bbox": decl.source_evidence[0].bbox if decl.source_evidence else None,
                            "source_image_index": decl.source_evidence[0].image_index if decl.source_evidence else 0,
                        })

                for alt in decl.alternatives:
                    alt_val = alt.value if hasattr(alt, "value") else alt.get("value")
                    if alt_val and is_valid_date_candidate(alt_val):
                        clean_alt = str(alt_val).strip()
                        if clean_alt.lower() not in seen_vals:
                            seen_vals.add(clean_alt.lower())
                            alt_ev = alt.source_evidence if hasattr(alt, "source_evidence") else alt.get("source_evidence", [])
                            alt_conf = alt.confidence if hasattr(alt, "confidence") else alt.get("confidence", 0.9)
                            valid_date_cands.append({
                                "value": clean_alt,
                                "confidence": alt_conf,
                                "source_evidence": alt_ev,
                                "bbox": alt_ev[0].bbox if alt_ev and hasattr(alt_ev[0], "bbox") else None,
                                "source_image_index": alt_ev[0].image_index if alt_ev and hasattr(alt_ev[0], "image_index") else 0,
                            })

                if not valid_date_cands:
                    merged_fields[field_name] = {
                        "value": None,
                        "status": "NOT_FOUND",
                        "confidence": 0.0,
                    }
                    continue
                elif len(valid_date_cands) == 1:
                    # Non-date noise eliminated; single valid date remains
                    cand = valid_date_cands[0]
                    ev_list = [
                        ev.model_dump() if hasattr(ev, "model_dump") else ev
                        for ev in cand["source_evidence"]
                    ]
                    merged_fields[field_name] = {
                        "value": cand["value"],
                        "normalized_value": cand["value"],
                        "confidence": round(float(cand["confidence"]), 3),
                        "source": "OCR_GEMINI_RESOLVED",
                        "extraction_method": "GEMINI_SEMANTIC_RESOLVER",
                        "source_image_index": cand["source_image_index"],
                        "bbox": cand["bbox"],
                        "resolution_note": f"Filtered invalid date candidates, accepting valid date '{cand['value']}'",
                        "source_evidence": ev_list,
                        "status": "VALID",
                        "evidence_state": "EVIDENCE_VERIFIED",
                    }
                    continue
                else:
                    # Check if multiple candidates represent equivalent dates (e.g. 04/28 vs 04/2028)
                    norm_dates = []
                    all_parsed = True
                    for c in valid_date_cands:
                        core = DATE_PREFIX_RE.sub("", c["value"]).strip()
                        ok, norm, _ = parse_date_with_precision(core)
                        if ok and norm:
                            norm_dates.append(norm)
                        else:
                            all_parsed = False
                            break
                    if all_parsed and len(set(norm_dates)) == 1:
                        # Equivalent dates agree
                        cand = valid_date_cands[0]
                        ev_list = [
                            ev.model_dump() if hasattr(ev, "model_dump") else ev
                            for ev in cand["source_evidence"]
                        ]
                        merged_fields[field_name] = {
                            "value": cand["value"],
                            "normalized_value": norm_dates[0],
                            "confidence": round(float(cand["confidence"]), 3),
                            "source": "OCR_GEMINI_RESOLVED",
                            "extraction_method": "GEMINI_SEMANTIC_RESOLVER",
                            "source_image_index": cand["source_image_index"],
                            "bbox": cand["bbox"],
                            "resolution_note": f"Consolidated equivalent date formats to '{norm_dates[0]}'",
                            "source_evidence": ev_list,
                            "status": "VALID",
                            "evidence_state": "EVIDENCE_VERIFIED",
                        }
                        continue

            if field_name == "PRODUCT_NAME" and not _llm_has_genuine_product_identity_conflict(decl):
                if det_candidate and det_candidate.get("value"):
                    retained = dict(det_candidate)
                    retained.setdefault(
                        "review_notes",
                        "Semantic conflict contained only generic, descriptive, packaging, or equivalent identity evidence.",
                    )
                    merged_fields[field_name] = retained
                    llm_metadata.setdefault("identity_resolution_rejections", []).append({
                        "field": field_name,
                        "reason": retained["review_notes"],
                    })
                    continue

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
                if field_name not in DATE_FIELDS or is_valid_date_candidate(det_candidate.get("value")):
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

    sanitize_batch_number_field(merged_fields)
    return merged_fields, llm_metadata, validated_result.package_context
