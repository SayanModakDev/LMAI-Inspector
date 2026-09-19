"""
Core evaluation engine for LMAI Inspector benchmark suites.
Executes packages through the analysis pipeline in reproducible offline or audited live mode.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from app.core.config import get_settings

from app.core.constants import InspectionStatus, normalize_status
from app.classification.category_classifier import classify_category, CATEGORY_VOCABULARY
from app.classification.package_context import detect_package_context
from app.extraction.declaration_extractor import extract_declarations, merge_extracted_fields, merge_product_evidence
from app.rules.applicability import get_applicable_rules
from app.rules.rule_engine import evaluate_rules, derive_overall_result
from app.llm.grounding_validator import EvidenceGroundingValidator
from app.llm.schemas import LLMExtractionResult

from .normalizer import compare_declaration_values, normalize_declaration_value
from .schema import (
    BenchmarkCase,
    CaseEvaluation,
    DeclarationEvaluation,
    ExpectedDeclaration,
    RuleEvaluation,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class BenchmarkEvaluator:
    """
    Executes benchmark cases through the LMAI pipeline and measures ground-truth agreement.
    """

    def __init__(
        self,
        live_gemini: bool = False,
        rule_matrix_path: Optional[str] = None,
    ):
        """
        Initialize the evaluator.

        Args:
            live_gemini: Whether live Gemini API calls are permitted. Gated by explicit opt-in.
            rule_matrix_path: Optional path to rule_matrix.json (defaults to settings.RULE_MATRIX_PATH).
        """
        # Mode B is enabled ONLY if live_gemini is True or RUN_GEMINI_BENCHMARK==1
        env_live = os.getenv("RUN_GEMINI_BENCHMARK", "0").strip().lower() in ("1", "true", "yes")
        self.live_gemini = live_gemini or env_live
        self.mode = "MODE_B_LIVE_GEMINI" if self.live_gemini else "MODE_A_OFFLINE"

        self.rule_matrix_path = rule_matrix_path or getattr(settings, "RULE_MATRIX_PATH", None)
        self._rules_cache: Optional[List[Dict[str, Any]]] = None

        logger.info("Initialized BenchmarkEvaluator in %s mode (live_gemini=%s)", self.mode, self.live_gemini)

    def _get_all_rules(self) -> List[Dict[str, Any]]:
        """Load and cache the canonical rule matrix without requiring a live database."""
        if self._rules_cache is not None:
            return self._rules_cache

        rules: List[Dict[str, Any]] = []
        path = self.rule_matrix_path
        if not path or not os.path.exists(path):
            # Fallback relative to project data directory
            cand = Path(__file__).resolve().parent.parent.parent / "data" / "rule_matrix.json"
            if cand.exists():
                path = str(cand)

        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                rules = data.get("rules", [])
            except Exception as exc:
                logger.error("Failed to load rule matrix from %s: %s", path, exc)

        self._rules_cache = rules
        return self._rules_cache

    def evaluate_case(self, case: BenchmarkCase) -> CaseEvaluation:
        """
        Execute a single benchmark case end-to-end and evaluate against expected ground truth.
        """
        case_started = time.perf_counter()
        timings: Dict[str, Any] = {}
        errors: List[Dict[str, Any]] = []

        # -------------------------------------------------------------------
        # Step 0: Pre-OCR Image Quality Gate
        # -------------------------------------------------------------------
        quality_started = time.perf_counter()
        quality_summary_data = None
        case_quality_status = None
        usable_image_indices = list(range(len(case.images))) if case.images else []

        quality_gate_enabled = getattr(settings, "IMAGE_QUALITY_GATE_ENABLED", True)
        if quality_gate_enabled:
            # Check real images if available on disk
            real_images = [p for p in case.images if os.path.exists(p)]
            if real_images:
                try:
                    from app.image_quality.analyzer import analyze_inspection_images
                    from app.image_quality.policy import QualityPolicyConfig

                    q_cfg = QualityPolicyConfig.from_settings(settings)
                    q_sum = analyze_inspection_images(real_images, config=q_cfg)
                    quality_summary_data = q_sum.model_dump()
                    case_quality_status = q_sum.overall_quality_status.value
                    usable_image_indices = q_sum.usable_image_indices
                except Exception as q_exc:
                    logger.error("Error evaluating image quality for benchmark case %s: %s", case.case_id, q_exc)
            elif getattr(case, "mock_quality_status", None):
                case_quality_status = case.mock_quality_status
            elif case.mock_ocr_result and case.mock_ocr_result.get("quality_status"):
                case_quality_status = case.mock_ocr_result.get("quality_status")
            elif any(t in ("severely_blurred", "severe_glare", "unusable", "blackout", "unreadable") for t in case.tags):
                case_quality_status = "RECAPTURE_REQUIRED"
                usable_image_indices = []
            elif any(t in ("blurry", "glare", "low_light", "small_text", "cropped") for t in case.tags):
                case_quality_status = "WARN"
            else:
                case_quality_status = "ACCEPT"

        timings["quality_ms"] = round((time.perf_counter() - quality_started) * 1000)

        # -------------------------------------------------------------------
        # Step 1: OCR Processing (or Synthetic/Mock OCR)
        # -------------------------------------------------------------------
        ocr_started = time.perf_counter()
        raw_text = ""
        ocr_items: List[Dict[str, Any]] = []
        image_count = len(case.images)

        # If quality gate rejected ALL images, skip OCR completely
        if quality_gate_enabled and case_quality_status == "RECAPTURE_REQUIRED" and not usable_image_indices:
            logger.info("Quality gate RECAPTURE_REQUIRED for case %s; skipping OCR.", case.case_id)
            timings["ocr_ms"] = 0
        elif case.mock_ocr_result:
            # Reproducible offline/synthetic evaluation
            raw_text = case.mock_ocr_result.get("raw_text", "")
            ocr_items = case.mock_ocr_result.get("ocr_items", [])
            image_count = max(image_count, case.mock_ocr_result.get("image_count", 1))
            timings["ocr_ms"] = round((time.perf_counter() - ocr_started) * 1000)
        elif case.images:
            # Real package images
            try:
                from app.ocr.ocr_service import run_ocr
                from app.ocr.preprocessing import preprocess_image

                combined_text_parts = []
                for idx, img_path in enumerate(case.images):
                    if not os.path.exists(img_path):
                        errors.append({"stage": "IMAGE_LOADING", "detail": f"Image file not found: {img_path}"})
                        continue
                    if quality_gate_enabled and idx not in usable_image_indices:
                        logger.info("Case %s image %d excluded from OCR due to quality gate", case.case_id, idx)
                        continue
                    prep_started = time.perf_counter()
                    proc_path, _ = preprocess_image(img_path, output_dir=settings.UPLOAD_DIR, filename_prefix=f"bm_{case.case_id}_{idx}")
                    timings[f"img_{idx}_prep_ms"] = round((time.perf_counter() - prep_started) * 1000)

                    ocr_res = run_ocr(proc_path)
                    t = ocr_res.get("raw_text", "")
                    items = ocr_res.get("ocr_items", [])
                    for itm in items:
                        itm["image_index"] = idx
                    if t:
                        combined_text_parts.append(t)
                    ocr_items.extend(items)

                raw_text = "\n\n".join(combined_text_parts)
                timings["ocr_ms"] = round((time.perf_counter() - ocr_started) * 1000)
            except Exception as exc:
                logger.exception("OCR execution error for case %s: %s", case.case_id, exc)
                errors.append({"stage": "OCR", "detail": str(exc)})
                timings["ocr_ms"] = round((time.perf_counter() - ocr_started) * 1000)
        else:
            errors.append({"stage": "INPUT", "detail": "Case contains neither images nor mock_ocr_result"})
            timings["ocr_ms"] = 0

        for idx, item in enumerate(ocr_items):
            item["token_id"] = idx

        # -------------------------------------------------------------------
        # Step 2: Deterministic Candidate Extraction
        # -------------------------------------------------------------------
        det_started = time.perf_counter()
        per_image_fields = []
        if ocr_items:
            img_indices = sorted(list({item.get("image_index", 0) for item in ocr_items}))
            for img_idx in img_indices:
                sub_items = [itm for itm in ocr_items if itm.get("image_index", 0) == img_idx]
                sub_text = "\n".join(itm.get("text", "") for itm in sub_items)
                fields = extract_declarations(sub_text, sub_items)
                for f_cand in fields.values():
                    if isinstance(f_cand, dict):
                        f_cand.setdefault("source_image_index", img_idx)
                per_image_fields.append(fields)
        else:
            per_image_fields.append(extract_declarations(raw_text, ocr_items))

        extracted_fields = merge_extracted_fields(per_image_fields)
        extracted_fields = merge_product_evidence(extracted_fields, raw_text, ocr_items, None)
        timings["declaration_extraction_ms"] = round((time.perf_counter() - det_started) * 1000)

        # -------------------------------------------------------------------
        # Step 3: Gemini Semantic Resolution & Grounding (Offline vs Live)
        # -------------------------------------------------------------------
        gemini_started = time.perf_counter()
        gemini_metadata: Dict[str, Any] = {
            "mode": self.mode,
            "llm_enabled": self.live_gemini,
            "llm_status": "DISABLED",
            "model_requested": settings.GEMINI_MODEL,
            "model_used": None,
            "fallback_used": False,
        }
        llm_pkg_context_data: Dict[str, Any] = {}

        if self.live_gemini:
            # Mode B: Live Gemini API
            try:
                from app.llm.evidence_resolver import resolve_evidence_with_gemini
                extracted_fields, live_meta, live_pkg_context = resolve_evidence_with_gemini(
                    ocr_items=ocr_items,
                    raw_text=raw_text,
                    image_count=max(1, image_count),
                    num_images=max(1, image_count),
                    deterministic_fields=extracted_fields,
                    barcode_result=None,
                )
                gemini_metadata.update(live_meta)
                if live_pkg_context:
                    llm_pkg_context_data = live_pkg_context.model_dump(mode="json") if hasattr(live_pkg_context, "model_dump") else dict(live_pkg_context)
            except Exception as gem_exc:
                logger.exception("Live Gemini resolution error: %s", gem_exc)
                gemini_metadata["llm_status"] = "ERROR"
                gemini_metadata["error"] = str(gem_exc)
                errors.append({"stage": "GEMINI_LIVE", "detail": str(gem_exc)})
        elif case.mock_gemini_response:
            # Mode A: Offline using recorded mock Gemini response
            try:
                mock_result = LLMExtractionResult.model_validate(case.mock_gemini_response)
                grounding_start = time.perf_counter()
                validator = EvidenceGroundingValidator(
                    ocr_items=ocr_items,
                    num_images=max(1, image_count),
                    min_confidence=settings.GEMINI_MIN_CONFIDENCE,
                )
                validated_result, grounding_audit = validator.validate_extraction_result(mock_result)
                gemini_metadata["grounding_ms"] = round((time.perf_counter() - grounding_start) * 1000)
                gemini_metadata["grounding_audit"] = grounding_audit
                gemini_metadata["llm_status"] = "SUCCESS_MOCK"
                gemini_metadata["model_used"] = "mock-recorded"

                # Hybrid merge validated resolutions into extracted_fields
                for decl in validated_result.resolved_declarations:
                    if decl.status == "RESOLVED" and decl.value:
                        extracted_fields[decl.field] = {
                            "value": decl.value,
                            "normalized_value": decl.normalized_value or decl.value,
                            "confidence": round(decl.confidence, 3),
                            "source": "OCR_GEMINI_RESOLVED",
                            "extraction_method": "GEMINI_SEMANTIC_RESOLVER",
                            "resolution_note": decl.resolution_note,
                            "status": "VALID",
                            "evidence_state": "EVIDENCE_VERIFIED",
                            "source_evidence": [ev.model_dump() for ev in decl.source_evidence],
                        }
                        if decl.field == "DECLARED_NET_QUANTITY":
                            from app.core.ontology import extract_quantity_value_unit
                            q_val, q_unit, _ = extract_quantity_value_unit(decl.normalized_value or decl.value)
                            extracted_fields[decl.field].update({
                                "quantity_value": q_val,
                                "quantity_unit": q_unit,
                                "quantity_present": bool(q_val),
                                "unit_present": bool(q_unit),
                                "quantity_unit_valid": bool(q_val and q_unit),
                            })
                if mock_result.package_context:
                    llm_pkg_context_data = mock_result.package_context.model_dump()
            except Exception as mock_exc:
                logger.exception("Error applying mock Gemini response: %s", mock_exc)
                gemini_metadata["llm_status"] = "ERROR_MOCK"
                gemini_metadata["error"] = str(mock_exc)
                errors.append({"stage": "GEMINI_MOCK", "detail": str(mock_exc)})
        else:
            # Mode A: Gemini explicitly disabled, deterministic extraction only
            gemini_metadata["llm_status"] = "DISABLED"

        gemini_metadata["timestamp"] = datetime.now(timezone.utc).isoformat()
        timings["gemini_total_ms"] = round((time.perf_counter() - gemini_started) * 1000)

        # -------------------------------------------------------------------
        # Step 4: Package Context & Category Classification
        # -------------------------------------------------------------------
        ctx_started = time.perf_counter()
        package_context = detect_package_context(raw_text, extracted_fields)
        if getattr(settings, "GEMINI_AUTO_SCOPE", True) and llm_pkg_context_data:
            llm_pkg_type = llm_pkg_context_data.get("package_type")
            if package_context.get("package_type") == "NOT_DETECTED" and llm_pkg_type in ("RETAIL", "WHOLESALE"):
                package_context["package_type"] = llm_pkg_type
            llm_import_status = llm_pkg_context_data.get("import_status")
            if package_context.get("import_status") == "NOT_DETECTED" and llm_import_status in ("DOMESTIC", "IMPORTED"):
                package_context["import_status"] = llm_import_status

        package_type = package_context.get("package_type", "NOT_DETECTED")
        import_status = package_context.get("import_status", "NOT_DETECTED")

        classification = classify_category(raw_text, extracted_fields, settings.CATEGORY_CONFIDENCE_THRESHOLD)
        category = classification.get("category", "UNKNOWN")
        cat_confidence = classification.get("confidence", 0.0)

        if getattr(settings, "GEMINI_AUTO_SCOPE", True) and category == "UNKNOWN" and llm_pkg_context_data:
            llm_cat = llm_pkg_context_data.get("category")
            if llm_cat and llm_cat in CATEGORY_VOCABULARY:
                category = llm_cat
                cat_confidence = float(llm_pkg_context_data.get("confidence") or 0.85)

        product_type = classification.get("product_type") or "UNKNOWN"
        timings["classification_ms"] = round((time.perf_counter() - ctx_started) * 1000)

        # -------------------------------------------------------------------
        # Step 5: Rule Applicability & Deterministic Rule Evaluation
        # -------------------------------------------------------------------
        rule_started = time.perf_counter()
        all_rules = self._get_all_rules()
        current_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        applicable_rules = get_applicable_rules(
            all_rules=all_rules,
            category=category,
            product_type=product_type,
            package_type=package_type,
            import_status=import_status,
            inspection_date=current_date_str,
        )

        rule_results, predicted_overall_result = evaluate_rules(applicable_rules, extracted_fields)
        timings["rule_evaluation_ms"] = round((time.perf_counter() - rule_started) * 1000)
        timings["total_ms"] = round((time.perf_counter() - case_started) * 1000)

        # -------------------------------------------------------------------
        # Step 6: Ground Truth Evaluation & Metric Calculation
        # -------------------------------------------------------------------

        # A. Context Evaluation
        exp_ctx = case.expected_context
        context_eval = {
            "expected_category": exp_ctx.category,
            "predicted_category": category,
            "category_match": (exp_ctx.category.upper() == category.upper()),
            "category_confidence": cat_confidence,
            "expected_package_type": exp_ctx.package_type,
            "predicted_package_type": package_type,
            "package_type_match": (exp_ctx.package_type.upper() == package_type.upper()),
            "expected_import_status": exp_ctx.import_status,
            "predicted_import_status": import_status,
            "import_status_match": (exp_ctx.import_status.upper() == import_status.upper()),
        }

        # B. Declaration Evaluation
        decl_evaluations: Dict[str, DeclarationEvaluation] = {}
        all_field_names = set(case.expected_declarations.keys()) | set(extracted_fields.keys())

        for fname in sorted(all_field_names):
            exp_decl: Optional[ExpectedDeclaration] = case.expected_declarations.get(fname)
            pred_data: Optional[Dict[str, Any]] = extracted_fields.get(fname)

            exp_val = exp_decl.value if exp_decl else None
            pred_val = pred_data.get("value") if isinstance(pred_data, dict) else (str(pred_data) if pred_data else None)

            # Skip internal/debug keys that are not declaration parameters
            if fname in ("VEG_NONVEG_SYMBOL_FEATURES",) and not exp_decl:
                continue

            exp_present = bool(exp_val and str(exp_val).strip())
            pred_present = bool(pred_val and str(pred_val).strip() and str(pred_val).strip() != "NOT_DETECTED")

            exact_m, norm_m, exp_n, pred_n = compare_declaration_values(
                field_name=fname,
                expected_value=exp_val,
                predicted_value=pred_val,
                aliases=exp_decl.aliases if exp_decl else None,
            )

            # Extract grounding metadata if available
            g_audit = (gemini_metadata.get("grounding_audit") or {}).get("declarations", {}).get(fname, {})
            g_strategy = g_audit.get("strategy")
            g_score = float(g_audit.get("score") or 0.0)
            g_status = "GROUNDED" if g_audit.get("grounded") else ("REJECTED" if g_strategy else None)

            # Error taxonomy categorization
            err_cat = None
            if exp_present and not pred_present:
                # Was the expected text visible in raw OCR?
                clean_raw = raw_text.lower()
                clean_exp = str(exp_val).lower().strip()
                if clean_exp and clean_exp in clean_raw:
                    err_cat = "DETERMINISTIC_EXTRACTION_ERROR"
                else:
                    err_cat = "OCR_ERROR"
            elif pred_present and not exp_present:
                err_cat = "GROUNDING_FALSE_ACCEPT"
            elif exp_present and pred_present and not norm_m:
                if g_status == "REJECTED":
                    err_cat = "GROUNDING_REJECTION"
                else:
                    err_cat = "LLM_RESOLUTION_ERROR" if pred_data.get("source") == "OCR_GEMINI_RESOLVED" else "DETERMINISTIC_EXTRACTION_ERROR"

            decl_evaluations[fname] = DeclarationEvaluation(
                field=fname,
                expected_value=exp_val,
                expected_normalized=exp_n,
                predicted_value=pred_val,
                predicted_normalized=pred_n,
                expected_present=exp_present,
                predicted_present=pred_present,
                required=exp_decl.required if exp_decl else True,
                exact_match=exact_m,
                normalized_match=norm_m,
                grounding_status=g_status,
                grounding_strategy=g_strategy,
                grounding_score=g_score,
                error_category=err_cat,
                resolution_source=pred_data.get("source") if isinstance(pred_data, dict) else None,
                notes=exp_decl.notes if exp_decl else None,
            )

        # C. Rule Engine Evaluation
        rule_evaluations: Dict[str, RuleEvaluation] = {}
        pred_rule_dict = {r.get("rule_id"): r for r in rule_results}

        # Rules to evaluate: intersection of expected rules and actual evaluated rules
        all_eval_rule_ids = set(case.expected_rules.keys()) | set(pred_rule_dict.keys())

        for rid in sorted(all_eval_rule_ids):
            exp_st = case.expected_rules.get(rid)
            pred_r = pred_rule_dict.get(rid)
            pred_st = pred_r.get("status") if pred_r else "NOT_APPLICABLE"

            norm_exp_st = normalize_status(exp_st)
            norm_pred_st = normalize_status(pred_st)

            r_match = (norm_exp_st == norm_pred_st) if (norm_exp_st and norm_pred_st) else False
            is_phys = bool(pred_r and pred_r.get("verification_type") == "PHYSICAL_VERIFICATION")
            is_block = bool(pred_r and pred_r.get("status") in ("NOT_VERIFIABLE", "REVIEW", "NEEDS_REVIEW") and not is_phys)

            err_cat = None
            if not r_match and exp_st:
                if rid not in pred_rule_dict:
                    err_cat = "APPLICABILITY_ERROR"
                elif is_phys:
                    err_cat = "EXPECTED_REVIEW"
                else:
                    err_cat = "RULE_VALIDATION_ERROR"

            rule_evaluations[rid] = RuleEvaluation(
                rule_id=rid,
                parameter=pred_r.get("parameter") if pred_r else None,
                expected_status=exp_st,
                predicted_status=pred_st,
                match=r_match,
                is_physical=is_phys,
                is_blocking=is_block,
                error_category=err_cat,
                reason=pred_r.get("message") if pred_r else None,
                evidence=pred_r.get("evidence_data") if pred_r else None,
            )

        # D. Overall Result Evaluation
        exp_overall = normalize_status(case.expected_overall_result) if case.expected_overall_result else None
        pred_overall = normalize_status(predicted_overall_result)
        overall_match = (exp_overall == pred_overall) if exp_overall else None

        # E. Review Metrics
        blocking_reviews = [r for r in rule_results if r.get("status") in ("NOT_VERIFIABLE", "REVIEW", "NEEDS_REVIEW") and r.get("verification_type") != "PHYSICAL_VERIFICATION"]
        conflicts = [f for f in extracted_fields.values() if isinstance(f, dict) and f.get("status") in ("CONFLICT", "CONFLICTING_EVIDENCE")]
        review_required = bool(blocking_reviews or conflicts)
        clean_inspection = not review_required and (predicted_overall_result == InspectionStatus.COMPLIANT)

        return CaseEvaluation(
            case_id=case.case_id,
            product_name=case.product_name,
            tags=case.tags,
            image_count=image_count,
            context_evaluation=context_eval,
            declaration_evaluations=decl_evaluations,
            rule_evaluations=rule_evaluations,
            expected_overall_result=case.expected_overall_result,
            predicted_overall_result=predicted_overall_result,
            overall_result_match=overall_match,
            timings_ms=timings,
            llm_metadata=gemini_metadata,
            review_required=review_required,
            clean_inspection=clean_inspection,
            errors=errors,
            quality_summary=quality_summary_data,
            quality_status=case_quality_status,
        )

    def evaluate_dataset(self, cases: List[BenchmarkCase]) -> List[CaseEvaluation]:
        """Execute and evaluate an entire list of benchmark cases."""
        results: List[CaseEvaluation] = []
        for case in cases:
            res = self.evaluate_case(case)
            results.append(res)
        return results
