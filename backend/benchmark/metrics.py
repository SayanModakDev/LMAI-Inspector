"""
Comprehensive metrics calculator for LMAI Inspector benchmark evaluation.
Computes measurable, unbundled metrics across all 10 evaluation dimensions.
"""

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple
import statistics

from .schema import CaseEvaluation


class BenchmarkMetricsCalculator:
    """Calculates comprehensive benchmark metrics across cases."""

    def __init__(self, case_evaluations: List[CaseEvaluation]):
        self.cases = case_evaluations

    def compute_all_metrics(self) -> Dict[str, Any]:
        """Compute the complete suite of benchmark metrics."""
        return {
            "dataset_summary": self.compute_dataset_summary(),
            "declaration_metrics": self.compute_declaration_metrics(),
            "context_metrics": self.compute_context_metrics(),
            "grounding_metrics": self.compute_grounding_metrics(),
            "review_metrics": self.compute_review_metrics(),
            "rule_metrics": self.compute_rule_metrics(),
            "overall_compliance_metrics": self.compute_overall_compliance_metrics(),
            "gemini_metrics": self.compute_gemini_metrics(),
            "performance_metrics": self.compute_performance_metrics(),
            "error_taxonomy": self.compute_error_taxonomy(),
            "tag_breakdown": self.compute_tag_breakdown(),
            "image_quality_metrics": self.compute_image_quality_metrics(),
        }

    # -----------------------------------------------------------------------
    # 1. Dataset Summary
    # -----------------------------------------------------------------------
    def compute_dataset_summary(self) -> Dict[str, Any]:
        total_cases = len(self.cases)
        total_images = sum(c.image_count for c in self.cases)
        tag_counts = Counter()
        for c in self.cases:
            for t in c.tags:
                tag_counts[t] += 1

        return {
            "total_packages": total_cases,
            "total_images": total_images,
            "avg_images_per_package": round(total_images / total_cases, 2) if total_cases else 0.0,
            "tag_distribution": dict(tag_counts.most_common()),
        }

    # -----------------------------------------------------------------------
    # 2. Declaration-Level Metrics
    # -----------------------------------------------------------------------
    def compute_declaration_metrics(self) -> Dict[str, Any]:
        tp = 0  # Expected present & predicted present
        fp = 0  # Not expected present & predicted present
        fn = 0  # Expected present & not predicted present
        tn = 0  # Not expected present & not predicted present

        exact_matches = 0
        normalized_matches = 0
        total_expected_present = 0

        req_expected_present = 0
        req_predicted_present = 0
        req_normalized_matches = 0

        per_field_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {
            "expected_present": 0,
            "predicted_present": 0,
            "exact_matches": 0,
            "normalized_matches": 0,
        })

        for case in self.cases:
            for fname, decl_eval in case.declaration_evaluations.items():
                stats = per_field_stats[fname]

                if decl_eval.expected_present and decl_eval.predicted_present:
                    tp += 1
                    total_expected_present += 1
                    stats["expected_present"] += 1
                    stats["predicted_present"] += 1

                    if decl_eval.required:
                        req_expected_present += 1
                        req_predicted_present += 1

                    if decl_eval.exact_match:
                        exact_matches += 1
                        stats["exact_matches"] += 1

                    if decl_eval.normalized_match:
                        normalized_matches += 1
                        stats["normalized_matches"] += 1
                        if decl_eval.required:
                            req_normalized_matches += 1

                elif not decl_eval.expected_present and decl_eval.predicted_present:
                    fp += 1
                    stats["predicted_present"] += 1
                elif decl_eval.expected_present and not decl_eval.predicted_present:
                    fn += 1
                    total_expected_present += 1
                    stats["expected_present"] += 1
                    if decl_eval.required:
                        req_expected_present += 1
                else:
                    tn += 1

        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        exact_match_acc = (exact_matches / total_expected_present) if total_expected_present > 0 else 0.0
        norm_val_acc = (normalized_matches / total_expected_present) if total_expected_present > 0 else 0.0
        req_recall = (req_predicted_present / req_expected_present) if req_expected_present > 0 else 0.0
        req_norm_acc = (req_normalized_matches / req_expected_present) if req_expected_present > 0 else 0.0

        field_breakdown = {}
        for fname, s in sorted(per_field_stats.items()):
            exp_cnt = s["expected_present"]
            norm_cnt = s["normalized_matches"]
            exact_cnt = s["exact_matches"]
            field_breakdown[fname] = {
                "expected_count": exp_cnt,
                "detected_count": s["predicted_present"],
                "exact_matches": exact_cnt,
                "normalized_matches": norm_cnt,
                "value_accuracy": round((norm_cnt / exp_cnt) * 100, 2) if exp_cnt > 0 else None,
            }

        return {
            "total_evaluated_declarations": tp + fp + fn + tn,
            "total_expected_declarations": total_expected_present,
            "presence_precision": round(precision * 100, 2),
            "presence_recall": round(recall * 100, 2),
            "presence_f1_score": round(f1 * 100, 2),
            "exact_match_accuracy": round(exact_match_acc * 100, 2),
            "value_accuracy": round(norm_val_acc * 100, 2),
            "required_field_recall": round(req_recall * 100, 2),
            "required_field_value_accuracy": round(req_norm_acc * 100, 2),
            "confusion_counts": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
            "per_field_breakdown": field_breakdown,
        }

    # -----------------------------------------------------------------------
    # 3. Context Classification Metrics
    # -----------------------------------------------------------------------
    def compute_context_metrics(self) -> Dict[str, Any]:
        total = len(self.cases)
        cat_correct = 0
        pkg_correct = 0
        imp_correct = 0

        cat_confusion = Counter()
        pkg_confusion = Counter()
        imp_confusion = Counter()

        for c in self.cases:
            ctx = c.context_evaluation
            if ctx.get("category_match"):
                cat_correct += 1
            if ctx.get("package_type_match"):
                pkg_correct += 1
            if ctx.get("import_status_match"):
                imp_correct += 1

            cat_pair = f"{ctx.get('expected_category')} -> {ctx.get('predicted_category')}"
            pkg_pair = f"{ctx.get('expected_package_type')} -> {ctx.get('predicted_package_type')}"
            imp_pair = f"{ctx.get('expected_import_status')} -> {ctx.get('predicted_import_status')}"

            cat_confusion[cat_pair] += 1
            pkg_confusion[pkg_pair] += 1
            imp_confusion[imp_pair] += 1

        return {
            "total_cases": total,
            "category_accuracy": round((cat_correct / total) * 100, 2) if total else 0.0,
            "package_type_accuracy": round((pkg_correct / total) * 100, 2) if total else 0.0,
            "import_status_accuracy": round((imp_correct / total) * 100, 2) if total else 0.0,
            "confusion_matrices": {
                "category": dict(cat_confusion),
                "package_type": dict(pkg_confusion),
                "import_status": dict(imp_confusion),
            },
        }

    # -----------------------------------------------------------------------
    # 4. Grounding Metrics
    # -----------------------------------------------------------------------
    def compute_grounding_metrics(self) -> Dict[str, Any]:
        grounded_count = 0
        rejected_count = 0
        false_rejections = 0
        unsafe_acceptances = 0

        strategy_counts = Counter()

        for case in self.cases:
            for fname, decl in case.declaration_evaluations.items():
                strat = decl.grounding_strategy
                if strat:
                    strategy_counts[strat] += 1

                if decl.grounding_status == "GROUNDED":
                    grounded_count += 1
                    # Unsafe acceptance: accepted value contradicts verified ground truth
                    if decl.expected_present and not decl.normalized_match:
                        unsafe_acceptances += 1
                elif decl.grounding_status == "REJECTED":
                    rejected_count += 1
                    # False rejection: extracted text matched ground truth, but grounding rejected it
                    if decl.expected_present and decl.normalized_match:
                        false_rejections += 1

        total_grounding_assessments = grounded_count + rejected_count
        accept_rate = (grounded_count / total_grounding_assessments * 100) if total_grounding_assessments else 0.0
        reject_rate = (rejected_count / total_grounding_assessments * 100) if total_grounding_assessments else 0.0

        return {
            "total_assessments": total_grounding_assessments,
            "grounded_declarations": grounded_count,
            "rejected_declarations": rejected_count,
            "acceptance_rate": round(accept_rate, 2),
            "rejection_rate": round(reject_rate, 2),
            "false_grounding_rejections": false_rejections,
            "unsafe_grounding_acceptances": unsafe_acceptances,
            "strategy_breakdown": dict(strategy_counts),
        }

    # -----------------------------------------------------------------------
    # 5. Conflict & Review Metrics
    # -----------------------------------------------------------------------
    def compute_review_metrics(self) -> Dict[str, Any]:
        total = len(self.cases)
        clean_inspections = sum(1 for c in self.cases if c.clean_inspection)
        requiring_review = sum(1 for c in self.cases if c.review_required)

        auto_resolved_fields = 0
        conflict_fields = 0
        not_found_fields = 0
        not_verifiable_rules = 0

        for c in self.cases:
            for decl in c.declaration_evaluations.values():
                if decl.predicted_present:
                    auto_resolved_fields += 1
                else:
                    not_found_fields += 1

            for r in c.rule_evaluations.values():
                if r.predicted_status in ("NOT_VERIFIABLE", "REVIEW", "NEEDS_REVIEW"):
                    if not r.is_physical:
                        not_verifiable_rules += 1

        return {
            "total_cases": total,
            "clean_inspections_count": clean_inspections,
            "clean_inspections_rate": round((clean_inspections / total) * 100, 2) if total else 0.0,
            "requiring_review_count": requiring_review,
            "requiring_review_rate": round((requiring_review / total) * 100, 2) if total else 0.0,
            "fields_resolved_count": auto_resolved_fields,
            "fields_not_found_count": not_found_fields,
            "blocking_not_verifiable_rules_count": not_verifiable_rules,
        }

    # -----------------------------------------------------------------------
    # 6. Rule Engine Metrics
    # -----------------------------------------------------------------------
    def compute_rule_metrics(self) -> Dict[str, Any]:
        total_eval_rules = 0
        matched_rules = 0

        status_counts = defaultdict(lambda: {"expected": 0, "predicted": 0, "matched": 0})
        mismatches: List[Dict[str, Any]] = []

        for case in self.cases:
            for rid, rule_eval in case.rule_evaluations.items():
                if not rule_eval.expected_status:
                    continue  # Unannotated rule

                total_eval_rules += 1
                exp_st = rule_eval.expected_status.upper().replace("-", "_")
                pred_st = (rule_eval.predicted_status or "NOT_APPLICABLE").upper().replace("-", "_")

                status_counts[exp_st]["expected"] += 1
                status_counts[pred_st]["predicted"] += 1

                if rule_eval.match:
                    matched_rules += 1
                    status_counts[exp_st]["matched"] += 1
                else:
                    mismatches.append({
                        "case_id": case.case_id,
                        "rule_id": rid,
                        "parameter": rule_eval.parameter,
                        "expected": rule_eval.expected_status,
                        "actual": rule_eval.predicted_status,
                        "is_physical": rule_eval.is_physical,
                        "error_category": rule_eval.error_category,
                        "reason": rule_eval.reason,
                    })

        overall_agreement = (matched_rules / total_eval_rules * 100) if total_eval_rules else 0.0

        status_agreement = {}
        for st, c in status_counts.items():
            exp_c = c["expected"]
            status_agreement[st] = {
                "expected": exp_c,
                "predicted": c["predicted"],
                "matched": c["matched"],
                "agreement_rate": round((c["matched"] / exp_c * 100), 2) if exp_c > 0 else None,
            }

        return {
            "total_evaluated_rules": total_eval_rules,
            "overall_rule_agreement_rate": round(overall_agreement, 2),
            "status_agreement": status_agreement,
            "mismatch_count": len(mismatches),
            "mismatches": mismatches,
        }

    # -----------------------------------------------------------------------
    # 7. Overall Compliance Result
    # -----------------------------------------------------------------------
    def compute_overall_compliance_metrics(self) -> Dict[str, Any]:
        cases_with_expected = [c for c in self.cases if c.expected_overall_result]
        total = len(cases_with_expected)
        matched = sum(1 for c in cases_with_expected if c.overall_result_match)
        confusion = Counter()

        for c in cases_with_expected:
            pair = f"{c.expected_overall_result} -> {c.predicted_overall_result}"
            confusion[pair] += 1

        return {
            "total_cases_evaluated": total,
            "overall_result_agreement_rate": round((matched / total * 100), 2) if total else None,
            "confusion_counts": dict(confusion),
        }

    # -----------------------------------------------------------------------
    # 8. Gemini Metrics
    # -----------------------------------------------------------------------
    def compute_gemini_metrics(self) -> Dict[str, Any]:
        total = len(self.cases)
        success_count = 0
        fallback_count = 0
        error_count = 0
        disabled_count = 0

        used_models = Counter()

        for c in self.cases:
            meta = c.llm_metadata
            status = meta.get("llm_status", "DISABLED")
            model = meta.get("model_used") or meta.get("llm_model")
            if model:
                used_models[model] += 1

            if status in ("SUCCESS", "SUCCESS_MOCK"):
                success_count += 1
            elif "FALLBACK" in status or meta.get("fallback_used"):
                fallback_count += 1
            elif status == "ERROR":
                error_count += 1
            elif status == "DISABLED":
                disabled_count += 1

        return {
            "total_cases": total,
            "success_rate": round((success_count / total * 100), 2) if total else 0.0,
            "fallback_rate": round((fallback_count / total * 100), 2) if total else 0.0,
            "error_rate": round((error_count / total * 100), 2) if total else 0.0,
            "disabled_rate": round((disabled_count / total * 100), 2) if total else 0.0,
            "models_used": dict(used_models),
        }

    # -----------------------------------------------------------------------
    # 9. Performance Metrics
    # -----------------------------------------------------------------------
    def compute_performance_metrics(self) -> Dict[str, Any]:
        total_times = [c.timings_ms.get("total_ms", 0) for c in self.cases if c.timings_ms.get("total_ms") is not None]
        ocr_times = [c.timings_ms.get("ocr_ms", 0) for c in self.cases if c.timings_ms.get("ocr_ms") is not None]
        det_times = [c.timings_ms.get("declaration_extraction_ms", 0) for c in self.cases if c.timings_ms.get("declaration_extraction_ms") is not None]
        gem_times = [c.timings_ms.get("gemini_total_ms", 0) for c in self.cases if c.timings_ms.get("gemini_total_ms") is not None]
        rule_times = [c.timings_ms.get("rule_evaluation_ms", 0) for c in self.cases if c.timings_ms.get("rule_evaluation_ms") is not None]

        def _stats(arr: List[float]) -> Dict[str, Optional[float]]:
            if not arr:
                return {"mean": None, "median": None, "min": None, "max": None, "p95": None}
            s = sorted(arr)
            p95_idx = int(len(s) * 0.95)
            p95_val = s[min(p95_idx, len(s) - 1)]
            return {
                "mean": round(statistics.mean(s), 1),
                "median": round(statistics.median(s), 1),
                "min": round(min(s), 1),
                "max": round(max(s), 1),
                "p95": round(p95_val, 1),
            }

        return {
            "total_ms": _stats(total_times),
            "ocr_ms": _stats(ocr_times),
            "declaration_extraction_ms": _stats(det_times),
            "gemini_total_ms": _stats(gem_times),
            "rule_evaluation_ms": _stats(rule_times),
        }

    # -----------------------------------------------------------------------
    # 10. Error Taxonomy & Tag Breakdown
    # -----------------------------------------------------------------------
    def compute_error_taxonomy(self) -> Dict[str, int]:
        tax_counts = Counter()
        for c in self.cases:
            for decl in c.declaration_evaluations.values():
                if decl.error_category:
                    tax_counts[decl.error_category] += 1
            for r in c.rule_evaluations.values():
                if r.error_category:
                    tax_counts[r.error_category] += 1
        return dict(tax_counts.most_common())

    def compute_tag_breakdown(self) -> Dict[str, Any]:
        tags_map: Dict[str, List[CaseEvaluation]] = defaultdict(list)
        for c in self.cases:
            for t in c.tags:
                tags_map[t].append(c)

        breakdown = {}
        for t, cases_sub in tags_map.items():
            sub_calc = BenchmarkMetricsCalculator(cases_sub)
            sub_decl = sub_calc.compute_declaration_metrics()
            sub_rules = sub_calc.compute_rule_metrics()
            breakdown[t] = {
                "case_count": len(cases_sub),
                "declaration_accuracy": sub_decl.get("value_accuracy"),
                "rule_agreement": sub_rules.get("overall_rule_agreement_rate"),
                "clean_inspection_rate": sub_calc.compute_review_metrics().get("clean_inspections_rate"),
            }
        return breakdown

    # -----------------------------------------------------------------------
    # 11. Image Quality Gate Metrics
    # -----------------------------------------------------------------------
    def compute_image_quality_metrics(self) -> Dict[str, Any]:
        """Compute automatic image quality gate metrics."""
        evaluated_cases = [c for c in self.cases if c.quality_status is not None]
        total_eval = len(evaluated_cases)

        if not total_eval:
            return {
                "gate_enabled": False,
                "total_cases_evaluated": 0,
                "quality_accept_rate": 0.0,
                "quality_warn_rate": 0.0,
                "quality_recapture_rate": 0.0,
                "status_counts": {},
                "tag_quality_breakdown": {},
                "false_recapture_count": 0,
                "false_recaptures": [],
                "missed_bad_image_count": 0,
                "missed_bad_images": [],
            }

        counts = Counter(c.quality_status for c in evaluated_cases)
        accept_count = counts.get("ACCEPT", 0)
        warn_count = counts.get("WARN", 0)
        recapture_count = counts.get("RECAPTURE_REQUIRED", 0)

        # Per-tag quality metrics
        target_tags = ["blurry", "low_light", "glare", "small_text", "cropped"]
        tag_quality: Dict[str, Dict[str, Any]] = {}
        for tag in target_tags:
            tag_cases = [c for c in evaluated_cases if tag in c.tags]
            t_total = len(tag_cases)
            if t_total > 0:
                t_counts = Counter(c.quality_status for c in tag_cases)
                tag_quality[tag] = {
                    "total_cases": t_total,
                    "accept": t_counts.get("ACCEPT", 0),
                    "warn": t_counts.get("WARN", 0),
                    "recapture_required": t_counts.get("RECAPTURE_REQUIRED", 0),
                    "accept_rate": round(t_counts.get("ACCEPT", 0) / t_total, 4),
                    "warn_rate": round(t_counts.get("WARN", 0) / t_total, 4),
                    "recapture_rate": round(t_counts.get("RECAPTURE_REQUIRED", 0) / t_total, 4),
                }

        # FALSE_RECAPTURE: A benchmark case whose declarations are correctly recoverable (expected COMPLIANT)
        # but was rejected by the gate (quality_status == RECAPTURE_REQUIRED).
        false_recaptures = [
            c.case_id for c in evaluated_cases
            if c.expected_overall_result == "COMPLIANT" and c.quality_status == "RECAPTURE_REQUIRED"
        ]

        # MISSED_BAD_IMAGE: A deliberately unusable benchmark case (tagged with severe defects)
        # accepted without warning (quality_status == ACCEPT).
        bad_tags = {"unusable", "severely_blurred", "severe_glare", "blackout", "unreadable", "bad_image"}
        missed_bad = [
            c.case_id for c in evaluated_cases
            if any(t in bad_tags for t in c.tags) and c.quality_status == "ACCEPT"
        ]

        return {
            "gate_enabled": True,
            "total_cases_evaluated": total_eval,
            "quality_accept_rate": round(accept_count / total_eval, 4),
            "quality_warn_rate": round(warn_count / total_eval, 4),
            "quality_recapture_rate": round(recapture_count / total_eval, 4),
            "status_counts": dict(counts),
            "tag_quality_breakdown": tag_quality,
            "false_recapture_count": len(false_recaptures),
            "false_recaptures": false_recaptures,
            "missed_bad_image_count": len(missed_bad),
            "missed_bad_images": missed_bad,
        }

