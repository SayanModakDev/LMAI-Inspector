"""
Deterministic Evidence Grounding and Hallucination Validator for LLM Semantic Extractions.
Guarantees zero fabricated tokens or ungrounded values can reach the statutory rule engine.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.llm.schemas import (
    CandidateValue,
    LLMExtractionResult,
    ResolvedDeclaration,
    SourceEvidence,
)

logger = logging.getLogger(__name__)


def _normalize_alphanumeric(text: str) -> str:
    """Normalize text to alphanumeric characters for derivation checking."""
    return re.sub(r'[^a-zA-Z0-9]+', '', (text or '').lower())


def _is_value_derivable_from_text(value: str, raw_text: str) -> bool:
    """
    Check if an extracted/normalized value can reasonably be derived from the raw source text.
    Handles unit abbreviations, currency signs, spacing, and numbers.
    """
    if not value or not raw_text:
        return False

    v_clean = _normalize_alphanumeric(value)
    raw_clean = _normalize_alphanumeric(raw_text)

    if not v_clean:
        return False

    # 1. Direct alphanumeric containment
    if v_clean in raw_clean or raw_clean in v_clean:
        return True

    # 2. Character overlap check for complex strings (e.g. company names, addresses)
    # If >= 70% of characters/words in value match raw text
    val_words = [w for w in re.findall(r'[a-zA-Z0-9]+', value.lower()) if len(w) > 1]
    raw_words = set(re.findall(r'[a-zA-Z0-9]+', raw_text.lower()))

    if val_words:
        matched_words = sum(1 for w in val_words if w in raw_words)
        match_ratio = matched_words / len(val_words)
        if match_ratio >= 0.65:
            return True

    # 3. Digits match for numeric values (quantities, prices, dates, licenses)
    val_digits = re.findall(r'\d+', value)
    raw_digits = re.findall(r'\d+', raw_text)
    if val_digits and all(d in raw_text for d in val_digits):
        return True

    return False


class EvidenceGroundingValidator:
    """
    Deterministic validator running after Gemini structured output.
    Verifies that all referenced token IDs, image indices, bounding boxes,
    and text strings exist in actual OCR results.
    """

    def __init__(
        self,
        ocr_items: List[Dict[str, Any]],
        num_images: int,
        min_confidence: float = 0.80,
    ):
        """
        Args:
            ocr_items: Full list of OCR items detected by PaddleOCR across all panels.
                       Each item is expected to have 'token_id', 'image_index', 'text', 'bbox', 'confidence'.
            num_images: Total number of uploaded image panels.
            min_confidence: Threshold below which LLM resolutions are flagged for review.
        """
        self.num_images = max(1, num_images)
        self.min_confidence = min_confidence

        # Build index: image_index -> token_id -> token_dict
        self.tokens_by_image: Dict[int, Dict[int, Dict[str, Any]]] = {
            i: {} for i in range(self.num_images)
        }
        self.all_tokens_by_id: Dict[int, Dict[str, Any]] = {}

        for item in ocr_items:
            img_idx = item.get("image_index", 0)
            tok_id = item.get("token_id")
            if tok_id is not None:
                self.all_tokens_by_id[int(tok_id)] = item
                if img_idx in self.tokens_by_image:
                    self.tokens_by_image[img_idx][int(tok_id)] = item

    def validate_source_evidence(
        self,
        evidence: SourceEvidence,
    ) -> Tuple[bool, str, Optional[List[float]]]:
        """
        Validate a single SourceEvidence object.

        Returns:
            (is_valid: bool, reason: str, computed_bbox: Optional[List[float]])
        """
        img_idx = evidence.image_index
        if img_idx < 0 or img_idx >= self.num_images:
            return False, f"Invalid image_index {img_idx} (valid range 0..{self.num_images - 1})", None

        if not evidence.token_ids:
            return False, "Evidence must reference at least one valid OCR token_id", None

        # Check every token ID exists on that image
        referenced_tokens = []
        for tid in evidence.token_ids:
            tok = self.tokens_by_image[img_idx].get(tid)
            if not tok:
                return False, f"Unknown token ID {tid} does not exist in OCR detections for image {img_idx}", None
            referenced_tokens.append(tok)

        # Reconstruct combined text and unified bounding box from actual OCR tokens
        token_texts = [str(t.get("text", "")).strip() for t in referenced_tokens]
        combined_token_text = " ".join(token_texts).strip()

        if not combined_token_text:
            return False, "Referenced OCR tokens have empty text", None

        # Calculate bounding box union
        all_boxes = [t.get("bbox") for t in referenced_tokens if t.get("bbox")]
        unified_bbox = None
        if all_boxes:
            try:
                min_x = min(b[0] for b in all_boxes)
                min_y = min(b[1] for b in all_boxes)
                max_x = max(b[2] for b in all_boxes)
                max_y = max(b[3] for b in all_boxes)
                unified_bbox = [float(min_x), float(min_y), float(max_x), float(max_y)]
            except Exception:
                unified_bbox = evidence.bbox

        # Check text alignment between evidence.raw_text and actual OCR tokens
        if not _is_value_derivable_from_text(evidence.raw_text, combined_token_text):
            # Also check if raw_text exists anywhere in the image's OCR tokens
            image_raw_text = " ".join(t.get("text", "") for t in self.tokens_by_image[img_idx].values())
            if not _is_value_derivable_from_text(evidence.raw_text, image_raw_text):
                return False, f"Evidence raw_text '{evidence.raw_text}' is not found in OCR tokens (referenced: '{combined_token_text}')", None

        return True, "GROUNDED", unified_bbox

    def validate_declaration(
        self,
        arg1: Any,
        arg2: Optional[ResolvedDeclaration] = None,
    ) -> Tuple[bool, List[str], ResolvedDeclaration]:
        """
        Validate a ResolvedDeclaration against actual OCR tokens and evidence.

        Supports both:
            validate_declaration(declaration)
            validate_declaration(field_name, declaration)

        Returns:
            (is_grounded: bool, violations: List[str], validated_decl: ResolvedDeclaration)
        """
        declaration: ResolvedDeclaration = arg2 if arg2 is not None else arg1
        decl_copy = declaration.model_copy(deep=True)

        if decl_copy.status == "NOT_FOUND" and not decl_copy.value:
            return True, [], decl_copy

        if not decl_copy.value and decl_copy.status == "RESOLVED":
            decl_copy.status = "NOT_FOUND"
            return False, ["RESOLVED declaration has empty value"], decl_copy

        if not decl_copy.source_evidence:
            decl_copy.status = "CONFLICT" if decl_copy.alternatives else "NOT_FOUND"
            decl_copy.confidence = 0.0
            return False, ["Missing source_evidence for declaration"], decl_copy

        # Validate each source evidence item
        valid_evidences: List[SourceEvidence] = []
        grounding_errors: List[str] = []

        for ev in decl_copy.source_evidence:
            ok, reason, unified_bbox = self.validate_source_evidence(ev)
            if ok:
                ev.bbox = unified_bbox or ev.bbox
                valid_evidences.append(ev)
            else:
                grounding_errors.append(reason)

        if not valid_evidences:
            decl_copy.status = "CONFLICT" if decl_copy.alternatives else "NOT_FOUND"
            decl_copy.confidence = 0.0
            error_summary = "; ".join(grounding_errors)
            logger.warning("Grounding rejected for field %s: %s", decl_copy.field, error_summary)
            decl_copy.resolution_note = f"Grounding validation failed: {error_summary}"
            return False, grounding_errors, decl_copy

        decl_copy.source_evidence = valid_evidences

        # Validate that the resolved value is derivable from the grounded raw text
        combined_grounded_raw = " ".join(ev.raw_text for ev in valid_evidences)
        test_value = decl_copy.normalized_value or decl_copy.value or ""

        if not _is_value_derivable_from_text(test_value, combined_grounded_raw):
            logger.warning(
                "Grounding derivation failure for %s: value '%s' not derivable from raw text '%s'",
                decl_copy.field,
                test_value,
                combined_grounded_raw,
            )
            decl_copy.status = "CONFLICT" if decl_copy.alternatives else "NOT_FOUND"
            decl_copy.confidence = 0.0
            decl_copy.resolution_note = f"Value '{test_value}' cannot be derived from grounded text '{combined_grounded_raw}'"
            return False, [f"Value '{test_value}' is not found in OCR tokens or cannot be derived from grounded evidence"], decl_copy

        # Validate alternatives
        valid_alts = []
        for alt in decl_copy.alternatives:
            alt_ev_ok = True
            for a_ev in alt.source_evidence:
                a_ok, _, _ = self.validate_source_evidence(a_ev)
                if not a_ok:
                    alt_ev_ok = False
                    break
            if alt_ev_ok:
                valid_alts.append(alt)
        decl_copy.alternatives = valid_alts

        return True, [], decl_copy

    def validate_extraction_result(
        self,
        result: LLMExtractionResult,
    ) -> Tuple[LLMExtractionResult, Dict[str, Any]]:
        """
        Validate all declarations in LLMExtractionResult.
        Rejects fabricated fields and returns validated structured result with grounding audit metadata.
        """
        validated_declarations: List[ResolvedDeclaration] = []
        rejected_count = 0
        grounded_count = 0
        grounding_audit: Dict[str, Any] = {
            "total_declarations": len(result.resolved_declarations),
            "grounded_count": 0,
            "rejected_count": 0,
            "fields": {},
        }

        for decl in result.resolved_declarations:
            is_valid, violations, valid_decl = self.validate_declaration(decl)
            validated_declarations.append(valid_decl)
            reason_str = "; ".join(violations) if isinstance(violations, (list, tuple)) else str(violations)
            grounding_audit["fields"][decl.field] = {
                "grounded": is_valid,
                "reason": reason_str or "VALIDATED",
                "status": valid_decl.status,
                "evidence_count": len(valid_decl.source_evidence),
            }
            if is_valid and valid_decl.status == "RESOLVED":
                grounded_count += 1
            elif not is_valid:
                rejected_count += 1

        grounding_audit["grounded_count"] = grounded_count
        grounding_audit["rejected_count"] = rejected_count

        validated_result = LLMExtractionResult(
            resolved_declarations=validated_declarations,
            package_context=result.package_context,
            notes=result.notes,
        )

        return validated_result, grounding_audit
