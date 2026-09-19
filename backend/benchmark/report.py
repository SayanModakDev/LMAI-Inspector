"""
Report generator for LMAI Inspector benchmark runs.
Outputs machine-readable JSON, human-readable Markdown, and analytical CSV files.
"""

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schema import CaseEvaluation


class BenchmarkReportGenerator:
    """Generates benchmark JSON, Markdown, and CSV reports."""

    def __init__(
        self,
        cases: List[CaseEvaluation],
        metrics: Dict[str, Any],
        mode: str = "MODE_A_OFFLINE",
        dataset_name: str = "LMAI Benchmark Dataset",
    ):
        self.cases = cases
        self.metrics = metrics
        self.mode = mode
        self.dataset_name = dataset_name
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def generate_all(self, output_dir: str) -> Dict[str, str]:
        """Generate all report formats in the specified output directory."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        json_path = out_path / "benchmark_results.json"
        md_path = out_path / "benchmark_report.md"
        decl_csv_path = out_path / "declaration_results.csv"
        rule_csv_path = out_path / "rule_results.csv"
        case_csv_path = out_path / "case_summary.csv"

        self.save_json(json_path)
        self.save_markdown(md_path)
        self.save_declaration_csv(decl_csv_path)
        self.save_rule_csv(rule_csv_path)
        self.save_case_csv(case_csv_path)

        return {
            "json": str(json_path.resolve()),
            "markdown": str(md_path.resolve()),
            "declaration_csv": str(decl_csv_path.resolve()),
            "rule_csv": str(rule_csv_path.resolve()),
            "case_csv": str(case_csv_path.resolve()),
        }

    # -----------------------------------------------------------------------
    # JSON Generation
    # -----------------------------------------------------------------------
    def save_json(self, file_path: Path) -> None:
        payload = {
            "meta": {
                "dataset_name": self.dataset_name,
                "mode": self.mode,
                "timestamp": self.timestamp,
                "total_cases": len(self.cases),
            },
            "metrics": self.metrics,
            "cases": [c.model_dump() for c in self.cases],
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    # -----------------------------------------------------------------------
    # Markdown Generation
    # -----------------------------------------------------------------------
    def save_markdown(self, file_path: Path) -> None:
        lines: List[str] = []

        ds = self.metrics.get("dataset_summary", {})
        dm = self.metrics.get("declaration_metrics", {})
        cm = self.metrics.get("context_metrics", {})
        gm = self.metrics.get("grounding_metrics", {})
        rm = self.metrics.get("review_metrics", {})
        rlm = self.metrics.get("rule_metrics", {})
        om = self.metrics.get("overall_compliance_metrics", {})
        gem = self.metrics.get("gemini_metrics", {})
        pm = self.metrics.get("performance_metrics", {})
        tax = self.metrics.get("error_taxonomy", {})

        lines.append("# LMAI Inspector Accuracy Benchmark Report\n")
        lines.append(f"**Dataset:** {self.dataset_name}  ")
        lines.append(f"**Execution Mode:** `{self.mode}`  ")
        lines.append(f"**Generated At:** `{self.timestamp}`  ")
        lines.append(f"**Total Packages Evaluated:** {ds.get('total_packages', 0)}  ")
        lines.append(f"**Total Panel Images:** {ds.get('total_images', 0)}\n")

        # Mode Safety Badge
        if "LIVE" in self.mode:
            lines.append("> [!CAUTION]\n> **LIVE GEMINI RUN:** API calls were executed against configured live endpoints. Results reflect current remote model behavior.\n")
        else:
            lines.append("> [!NOTE]\n> **OFFLINE REPRODUCIBLE RUN:** Executed with Gemini API quota consumption strictly at ZERO. Uses deterministic pipelines and recorded mocks.\n")

        # 1. Executive Summary Table
        lines.append("## 1. Executive Metric Summary\n")
        lines.append("| Metric Dimension | Measured Score | Status / Target |")
        lines.append("| :--- | :--- | :--- |")
        lines.append(f"| **Declaration Value Accuracy** | {dm.get('value_accuracy')}% | Normalized string match |")
        lines.append(f"| **Declaration Presence F1** | {dm.get('presence_f1_score')}% | Prec: {dm.get('presence_precision')}%, Rec: {dm.get('presence_recall')}% |")
        lines.append(f"| **Required Field Recall** | {dm.get('required_field_recall')}% | Statutory mandatory fields |")
        lines.append(f"| **Category Classification** | {cm.get('category_accuracy')}% | Commodity domain accuracy |")
        lines.append(f"| **Package Scope Accuracy** | {cm.get('package_type_accuracy')}% | Retail vs Wholesale |")
        lines.append(f"| **Origin Status Accuracy** | {cm.get('import_status_accuracy')}% | Domestic vs Imported |")
        lines.append(f"| **Overall Rule Agreement** | {rlm.get('overall_rule_agreement_rate')}% | Deterministic matrix agreement |")
        lines.append(f"| **Clean Automated Inspection Rate** | {rm.get('clean_inspections_rate')}% | Inspections without manual review |")
        lines.append(f"| **Unsafe Grounding Acceptances** | {gm.get('unsafe_grounding_acceptances')} | Grounded values contradicting truth |")
        lines.append(f"| **False Grounding Rejections** | {gm.get('false_grounding_rejections')} | Correct values falsely rejected |")
        if om.get("overall_result_agreement_rate") is not None:
            lines.append(f"| **Overall Compliance Agreement** | {om.get('overall_result_agreement_rate')}% | End-to-end outcome agreement |")
        lines.append("")

        # 2. Declaration Metrics Table
        lines.append("## 2. Declaration-Level Extraction Accuracy\n")
        lines.append(f"- **Total Expected Declarations:** {dm.get('total_expected_declarations', 0)}")
        lines.append(f"- **Exact Match Accuracy:** {dm.get('exact_match_accuracy', 0)}%")
        lines.append(f"- **Normalized Value Accuracy:** {dm.get('value_accuracy', 0)}%")
        lines.append(f"- **Required Field Value Accuracy:** {dm.get('required_field_value_accuracy', 0)}%\n")

        lines.append("### Per-Field Breakdown\n")
        lines.append("| Canonical Parameter | Expected | Detected | Exact Match | Normalized Match | Value Accuracy |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for fname, fstats in dm.get("per_field_breakdown", {}).items():
            acc_str = f"{fstats.get('value_accuracy')}%" if fstats.get('value_accuracy') is not None else "N/A"
            lines.append(
                f"| `{fname}` | {fstats.get('expected_count')} | {fstats.get('detected_count')} | "
                f"{fstats.get('exact_matches')} | {fstats.get('normalized_matches')} | {acc_str} |"
            )
        lines.append("")

        # 3. Grounding & Hallucination Metrics
        lines.append("## 3. Evidence Grounding & Hallucination Prevention\n")
        lines.append(f"- **Grounded Declarations:** {gm.get('grounded_declarations', 0)}")
        lines.append(f"- **Rejected Declarations:** {gm.get('rejected_declarations', 0)}")
        lines.append(f"- **Grounding Acceptance Rate:** {gm.get('acceptance_rate', 0)}%")
        lines.append(f"- **Unsafe Grounding Acceptances:** **{gm.get('unsafe_grounding_acceptances', 0)}** (Critical risk metric)")
        lines.append(f"- **False Grounding Rejections:** {gm.get('false_grounding_rejections', 0)}\n")

        lines.append("### Grounding Strategy Breakdown\n")
        lines.append("| Derivation Strategy | Occurrences |")
        lines.append("| :--- | :--- |")
        for strat, cnt in gm.get("strategy_breakdown", {}).items():
            lines.append(f"| `{strat}` | {cnt} |")
        lines.append("")

        # 4. Context Classification & Scope
        lines.append("## 4. Context Classification & Regulatory Scope\n")
        lines.append(f"- **Category Accuracy:** {cm.get('category_accuracy')}%")
        lines.append(f"- **Package Type Accuracy:** {cm.get('package_type_accuracy')}%")
        lines.append(f"- **Import Status Accuracy:** {cm.get('import_status_accuracy')}%\n")

        lines.append("### Category Confusion Counts\n")
        lines.append("| Expected -> Predicted | Count |")
        lines.append("| :--- | :--- |")
        for pair, cnt in cm.get("confusion_matrices", {}).get("category", {}).items():
            lines.append(f"| {pair} | {cnt} |")
        lines.append("")

        # 5. Rule Engine & Statutory Validation
        lines.append("## 5. Deterministic Rule Engine Agreement\n")
        lines.append(f"- **Total Evaluated Rules:** {rlm.get('total_evaluated_rules', 0)}")
        lines.append(f"- **Overall Rule-Status Agreement Rate:** {rlm.get('overall_rule_agreement_rate', 0)}%\n")

        lines.append("| Status Dimension | Expected Count | Predicted Count | Matched | Agreement Rate |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for st, st_data in rlm.get("status_agreement", {}).items():
            ag_rate = f"{st_data.get('agreement_rate')}%" if st_data.get('agreement_rate') is not None else "N/A"
            lines.append(f"| `{st}` | {st_data.get('expected')} | {st_data.get('predicted')} | {st_data.get('matched')} | {ag_rate} |")
        lines.append("")

        # 6. Gemini & Fallback Metrics
        lines.append("## 6. Gemini Resolution & Fallback Behavior\n")
        lines.append(f"- **Primary Success Rate:** {gem.get('success_rate')}%")
        lines.append(f"- **Fallback Rate:** {gem.get('fallback_rate')}%")
        lines.append(f"- **Error Rate:** {gem.get('error_rate')}%")
        lines.append(f"- **Deterministic-Only Rate:** {gem.get('disabled_rate')}%\n")

        # 7. Processing Performance
        lines.append("## 7. Performance & Latency Metrics\n")
        lines.append("| Pipeline Stage | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | p95 (ms) |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for stage, sstats in pm.items():
            lines.append(
                f"| `{stage}` | {sstats.get('mean')} | {sstats.get('median')} | "
                f"{sstats.get('min')} | {sstats.get('max')} | {sstats.get('p95')} |"
            )
        lines.append("")

        # 8. Error Taxonomy
        lines.append("## 8. Failure Taxonomy & Root Cause Classification\n")
        lines.append("| Error Category | Occurrences | Description |")
        lines.append("| :--- | :--- | :--- |")
        tax_desc = {
            "OCR_ERROR": "Expected declaration text unreadable or absent in OCR detection",
            "DETERMINISTIC_EXTRACTION_ERROR": "Text present in OCR tokens but candidate association failed",
            "LLM_RESOLUTION_ERROR": "Gemini semantic resolver generated contradictory or ungroundable value",
            "GROUNDING_REJECTION": "Candidate rejected by deterministic grounding validator",
            "GROUNDING_FALSE_ACCEPT": "Candidate accepted that was not declared in ground truth",
            "CONTEXT_CLASSIFICATION_ERROR": "Category or package scope mismatch",
            "APPLICABILITY_ERROR": "Rule was expected applicable/inapplicable but engine diverged",
            "RULE_VALIDATION_ERROR": "Deterministic validator status differed from ground truth",
            "EXPECTED_REVIEW": "Legitimate physical verification check (weight, caliper)",
            "UNKNOWN": "Uncategorized discrepancy",
        }
        for err_k, err_cnt in tax.items():
            lines.append(f"| `{err_k}` | {err_cnt} | {tax_desc.get(err_k, '')} |")
        lines.append("")

        # 9. Case-by-Case Mismatch Details
        lines.append("## 9. Per-Case Mismatch Log\n")
        mismatches = rlm.get("mismatches", [])
        if mismatches:
            lines.append("| Case ID | Rule ID | Expected | Actual | Error Category | Detail |")
            lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for m in mismatches[:50]:  # Cap at 50 for readability
                lines.append(f"| `{m.get('case_id')}` | `{m.get('rule_id')}` | `{m.get('expected')}` | `{m.get('actual')}` | `{m.get('error_category')}` | {m.get('reason') or ''} |")
        else:
            lines.append("No rule mismatches recorded across evaluated benchmark cases.\n")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    # -----------------------------------------------------------------------
    # CSV Exports
    # -----------------------------------------------------------------------
    def save_declaration_csv(self, file_path: Path) -> None:
        with open(file_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "case_id", "product_name", "field", "expected_value", "expected_normalized",
                "predicted_value", "predicted_normalized", "expected_present", "predicted_present",
                "exact_match", "normalized_match", "required", "grounding_status",
                "grounding_strategy", "grounding_score", "error_category", "resolution_source"
            ])
            for c in self.cases:
                for fname, d in c.declaration_evaluations.items():
                    writer.writerow([
                        c.case_id, c.product_name, fname, d.expected_value, d.expected_normalized,
                        d.predicted_value, d.predicted_normalized, d.expected_present, d.predicted_present,
                        d.exact_match, d.normalized_match, d.required, d.grounding_status,
                        d.grounding_strategy, d.grounding_score, d.error_category, d.resolution_source
                    ])

    def save_rule_csv(self, file_path: Path) -> None:
        with open(file_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "case_id", "rule_id", "parameter", "expected_status", "predicted_status",
                "match", "is_physical", "is_blocking", "error_category", "reason"
            ])
            for c in self.cases:
                for rid, r in c.rule_evaluations.items():
                    writer.writerow([
                        c.case_id, rid, r.parameter, r.expected_status, r.predicted_status,
                        r.match, r.is_physical, r.is_blocking, r.error_category, r.reason
                    ])

    def save_case_csv(self, file_path: Path) -> None:
        with open(file_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "case_id", "product_name", "image_count", "expected_category", "predicted_category",
                "expected_package_type", "predicted_package_type", "expected_overall", "predicted_overall",
                "overall_match", "clean_inspection", "review_required", "total_ms"
            ])
            for c in self.cases:
                ctx = c.context_evaluation
                writer.writerow([
                    c.case_id, c.product_name, c.image_count,
                    ctx.get("expected_category"), ctx.get("predicted_category"),
                    ctx.get("expected_package_type"), ctx.get("predicted_package_type"),
                    c.expected_overall_result, c.predicted_overall_result,
                    c.overall_result_match, c.clean_inspection, c.review_required,
                    c.timings_ms.get("total_ms", 0),
                ])
