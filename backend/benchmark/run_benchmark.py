"""
CLI entry point for running the LMAI Inspector Accuracy Benchmark.

Usage:
    python -m backend.benchmark.run_benchmark --dataset benchmark_data/dataset.example.json --output benchmark_output/
    python -m backend.benchmark.run_benchmark --tag blurry --output benchmark_output/
    python -m backend.benchmark.run_benchmark --case PKG001
    python -m backend.benchmark.run_benchmark --live  # REQUIRES RUN_GEMINI_BENCHMARK=1 or --live
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Ensure project root and backend are in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.benchmark.evaluator import BenchmarkEvaluator
from backend.benchmark.loader import load_benchmark_dataset, BenchmarkDatasetError
from backend.benchmark.metrics import BenchmarkMetricsCalculator
from backend.benchmark.report import BenchmarkReportGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("benchmark_runner")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LMAI Inspector Automated Accuracy Benchmark & Evaluation Framework",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dataset", "-d",
        type=str,
        default=None,
        help="Path to benchmark dataset JSON file. Defaults to benchmark_data/dataset.json or benchmark_data/dataset.example.json",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="benchmark_output",
        help="Directory to save benchmark reports and analytical CSVs",
    )
    parser.add_argument(
        "--tag", "-t",
        action="append",
        type=str,
        help="Filter cases by tag (e.g. --tag blurry --tag food). Can be repeated or comma-separated.",
    )
    parser.add_argument(
        "--case", "-c",
        type=str,
        help="Filter by specific case ID (e.g. PKG001)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable live Gemini API calls (MODE B). Default is offline (MODE A, ZERO live API quota).",
    )
    parser.add_argument(
        "--rule-matrix",
        type=str,
        default=None,
        help="Optional custom path to rule_matrix.json",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Quiet console output",
    )
    return parser.parse_args()


def resolve_default_dataset_path() -> Path:
    """Find default dataset file in standard locations."""
    cands = [
        PROJECT_ROOT / "benchmark_data" / "dataset.json",
        PROJECT_ROOT / "benchmark_data" / "dataset.example.json",
        BACKEND_DIR / "benchmark_data" / "dataset.json",
        BACKEND_DIR / "benchmark_data" / "dataset.example.json",
    ]
    for c in cands:
        if c.exists():
            return c
    return PROJECT_ROOT / "benchmark_data" / "dataset.example.json"


def main() -> int:
    args = parse_arguments()
    if args.quiet:
        logger.setLevel(logging.WARNING)

    # 1. Resolve dataset path
    dataset_path = Path(args.dataset) if args.dataset else resolve_default_dataset_path()
    logger.info("Using dataset file: %s", dataset_path.resolve())

    # 2. Parse tags
    tags = []
    if args.tag:
        for t in args.tag:
            tags.extend([sub.strip() for sub in t.split(",") if sub.strip()])

    # 3. Load dataset
    try:
        dataset = load_benchmark_dataset(
            dataset_path_or_dict=dataset_path,
            tags=tags if tags else None,
            case_ids=[args.case] if args.case else None,
        )
    except BenchmarkDatasetError as bde:
        logger.error("Dataset loading error: %s", bde)
        return 1

    if not dataset.cases:
        logger.warning("No benchmark cases found matching the specified filters.")
        return 0

    # 4. Mode determination
    is_live = args.live or (os.getenv("RUN_GEMINI_BENCHMARK", "0").strip().lower() in ("1", "true", "yes"))
    mode_str = "MODE_B_LIVE_GEMINI" if is_live else "MODE_A_OFFLINE"

    if is_live:
        logger.warning(">>> RUNNING IN LIVE GEMINI BENCHMARK MODE (API quota will be consumed)")
    else:
        logger.info(">>> Running in OFFLINE reproducible benchmark mode (ZERO Gemini quota consumed)")

    # 5. Execute benchmark evaluations
    evaluator = BenchmarkEvaluator(
        live_gemini=is_live,
        rule_matrix_path=args.rule_matrix,
    )

    logger.info("Evaluating %d benchmark cases...", len(dataset.cases))
    case_results = []
    for idx, case in enumerate(dataset.cases, 1):
        logger.info("[%d/%d] Evaluating case: %s (%s)", idx, len(dataset.cases), case.case_id, case.product_name)
        res = evaluator.evaluate_case(case)
        case_results.append(res)

    # 6. Calculate aggregate metrics
    calculator = BenchmarkMetricsCalculator(case_results)
    all_metrics = calculator.compute_all_metrics()

    # 7. Generate output reports
    generator = BenchmarkReportGenerator(
        cases=case_results,
        metrics=all_metrics,
        mode=mode_str,
        dataset_name=dataset.dataset_name,
    )
    outputs = generator.generate_all(output_dir=args.output)

    # 8. Print Executive Summary
    dm = all_metrics.get("declaration_metrics", {})
    cm = all_metrics.get("context_metrics", {})
    rm = all_metrics.get("review_metrics", {})
    rlm = all_metrics.get("rule_metrics", {})
    gm = all_metrics.get("grounding_metrics", {})

    print("\n" + "=" * 60)
    print("  LMAI INSPECTOR BENCHMARK EVALUATION COMPLETE")
    print("=" * 60)
    print(f"Mode:                           {mode_str}")
    print(f"Cases Evaluated:                {len(case_results)}")
    print(f"Declaration Value Accuracy:     {dm.get('value_accuracy')}%")
    print(f"Declaration Presence F1:        {dm.get('presence_f1_score')}%")
    print(f"Required Field Recall:          {dm.get('required_field_recall')}%")
    print(f"Category Classification:        {cm.get('category_accuracy')}%")
    print(f"Package Type Accuracy:          {cm.get('package_type_accuracy')}%")
    print(f"Rule Status Agreement:          {rlm.get('overall_rule_agreement_rate')}%")
    print(f"Clean Automated Inspection:     {rm.get('clean_inspections_rate')}%")
    print(f"Unsafe Grounding Acceptances:   {gm.get('unsafe_grounding_acceptances')} (Target: 0)")
    print("-" * 60)
    print(f"Markdown Report: {outputs['markdown']}")
    print(f"JSON Results:    {outputs['json']}")
    print(f"CSVs:            {outputs['declaration_csv']}")
    print("=" * 60 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
