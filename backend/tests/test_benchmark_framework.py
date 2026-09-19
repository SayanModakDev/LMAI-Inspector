"""
Unit and integration tests for the LMAI Inspector Accuracy Benchmark & Evaluation Framework.
Tests all 10 metric dimensions, normalizers, loader filters, and safety guarantees with ZERO live API calls.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
import pytest

from backend.benchmark.loader import BenchmarkDatasetError, load_benchmark_dataset
from backend.benchmark.metrics import BenchmarkMetricsCalculator
from backend.benchmark.normalizer import (
    compare_declaration_values,
    normalize_address,
    normalize_date,
    normalize_declaration_value,
    normalize_entity_name,
    normalize_mrp,
    normalize_net_quantity,
    normalize_strict_numeric,
)
from backend.benchmark.report import BenchmarkReportGenerator
from backend.benchmark.schema import (
    BenchmarkCase,
    BenchmarkDataset,
    CaseEvaluation,
    DeclarationEvaluation,
    ExpectedContext,
    ExpectedDeclaration,
    RuleEvaluation,
)
from backend.benchmark.evaluator import BenchmarkEvaluator


# ---------------------------------------------------------------------------
# 1. Dataset Parsing & Schema Validation
# ---------------------------------------------------------------------------

def test_dataset_parsing():
    """Verify clean dataset JSON parses into BenchmarkDataset model."""
    sample = {
        "version": "1.0.0",
        "dataset_name": "Test Suite",
        "cases": [
            {
                "case_id": "TC001",
                "product_name": "Sample Biscuit",
                "expected_context": {"category": "FOOD", "package_type": "RETAIL"},
                "expected_declarations": {
                    "MRP": {"value": "₹50.00", "required": True},
                    "DECLARED_NET_QUANTITY": "500 g",
                },
                "expected_rules": {"PC-ALL-001": "PASS"},
                "tags": ["clean", "food"],
            }
        ],
    }
    dataset = load_benchmark_dataset(sample)
    assert dataset.dataset_name == "Test Suite"
    assert len(dataset.cases) == 1
    case = dataset.cases[0]
    assert case.case_id == "TC001"
    assert case.expected_context.category == "FOOD"
    assert case.expected_declarations["MRP"].value == "₹50.00"
    # Shorthand string coercion test
    assert case.expected_declarations["DECLARED_NET_QUANTITY"].value == "500 g"
    assert case.expected_declarations["DECLARED_NET_QUANTITY"].required is True


def test_malformed_dataset_validation_error():
    """Verify malformed dataset triggers informative BenchmarkDatasetError."""
    # Missing required case_id
    malformed = {
        "version": "1.0.0",
        "cases": [
            {
                "product_name": "No Case ID Item"
            }
        ]
    }
    with pytest.raises(BenchmarkDatasetError) as exc_info:
        load_benchmark_dataset(malformed)
    assert "schema validation failed" in str(exc_info.value).lower()
    assert "case_id" in str(exc_info.value).lower()


def test_missing_image_path_handling():
    """Verify missing image paths are resolved cleanly without crashing loader."""
    sample = {
        "version": "1.0.0",
        "cases": [
            {
                "case_id": "IMG_MISSING",
                "product_name": "Ghost Package",
                "images": ["non_existent_folder/missing.jpg"],
                "expected_declarations": {"MRP": "₹10.00"},
            }
        ]
    }
    dataset = load_benchmark_dataset(sample)
    assert len(dataset.cases) == 1
    evaluator = BenchmarkEvaluator(live_gemini=False)
    # Evaluation should record error in case.errors rather than unhandled exception
    res = evaluator.evaluate_case(dataset.cases[0])
    assert any("not found" in e.get("detail", "").lower() for e in res.errors)


# ---------------------------------------------------------------------------
# 2. Normalization Rules (Deterministic)
# ---------------------------------------------------------------------------

def test_exact_declaration_match():
    """Exact identical strings return exact_match=True and normalized_match=True."""
    exact, norm, _, _ = compare_declaration_values("PRODUCT_NAME", "NutriOats", "NutriOats")
    assert exact is True
    assert norm is True


def test_normalized_currency_mrp_match():
    """Verify diverse Indian currency representations match canonically."""
    # ₹ 50.00 vs Rs 50 vs 50.0 vs Rs. 50/-
    assert normalize_mrp("₹ 50.00") == "50.00"
    assert normalize_mrp("Rs 50") == "50.00"
    assert normalize_mrp("50.0") == "50.00"
    assert normalize_mrp("MRP Rs. 50/- (Incl. of all taxes)") == "50.00"

    exact, norm, exp_n, pred_n = compare_declaration_values("MRP", "₹50.00", "Rs. 50.00")
    assert exact is False
    assert norm is True
    assert exp_n == "50.00"
    assert pred_n == "50.00"


def test_net_quantity_normalization():
    """Verify quantity and unit spacing & canonicalization."""
    assert normalize_net_quantity("500g") == "500 g"
    assert normalize_net_quantity("500 gm") == "500 g"
    assert normalize_net_quantity("500 GMS") == "500 g"
    assert normalize_net_quantity("1.5 kg") == "1.5 kg"
    assert normalize_net_quantity("10 x 50 g") == "10 x 50 g"
    assert normalize_net_quantity("10N x 50g") == "10 x 50 g"

    exact, norm, _, _ = compare_declaration_values("DECLARED_NET_QUANTITY", "500 g", "Net Weight: 500gm")
    assert norm is True


def test_date_normalization_mmyy():
    """Verify MM/YY deterministic expansion to MM/YYYY."""
    assert normalize_date("04/24") == "04/2024"
    assert normalize_date("04-2024") == "04/2024"
    assert normalize_date("4/2024") == "04/2024"
    assert normalize_date("Mfg Date: May 2024") == "05/2024"

    exact, norm, exp_n, pred_n = compare_declaration_values("MONTH_YEAR_MANUFACTURE", "04/2024", "04/24")
    assert exact is False
    assert norm is True
    assert exp_n == "04/2024"
    assert pred_n == "04/2024"


def test_entity_name_and_address_normalization():
    """Verify company entity type abbreviation and address whitespace tolerance."""
    assert normalize_entity_name("NutriBake Foods Private Limited") == "nutribake foods pvt ltd"
    assert normalize_entity_name("NutriBake Foods Pvt. Ltd.") == "nutribake foods pvt ltd"

    exact, norm, _, _ = compare_declaration_values(
        "MANUFACTURER_NAME",
        "NutriBake Foods Pvt Ltd",
        "Manufactured by: NutriBake Foods Private Limited",
    )
    assert norm is True

    addr1 = "Plot 42, Sector 5, Pune 411018"
    addr2 = "Plot 42, Sector 5, Pune - 411018"
    assert normalize_address(addr1) == normalize_address(addr2)


def test_wrong_numeric_value_rejected():
    """Verify wrong numbers, different prices, and different license numbers are rejected."""
    # MRP discrepancy
    _, norm_mrp, _, _ = compare_declaration_values("MRP", "₹50.00", "₹55.00")
    assert norm_mrp is False

    # Quantity discrepancy
    _, norm_qty, _, _ = compare_declaration_values("DECLARED_NET_QUANTITY", "500 g", "250 g")
    assert norm_qty is False

    # FSSAI license discrepancy
    _, norm_fssai, _, _ = compare_declaration_values("FSSAI_LICENSE", "10014011005544", "10014011005599")
    assert norm_fssai is False


# ---------------------------------------------------------------------------
# 3. Metrics Calculator Tests
# ---------------------------------------------------------------------------

def test_field_presence_precision_recall_f1():
    """Verify declaration precision, recall, and F1 calculation formulas."""
    case = CaseEvaluation(
        case_id="M_TEST",
        product_name="Test Prod",
        declaration_evaluations={
            # TP
            "MRP": DeclarationEvaluation(field="MRP", expected_present=True, predicted_present=True, normalized_match=True),
            # TP
            "NET_QUANTITY": DeclarationEvaluation(field="NET_QUANTITY", expected_present=True, predicted_present=True, normalized_match=True),
            # FN (Expected present, predicted absent)
            "BATCH_NUMBER": DeclarationEvaluation(field="BATCH_NUMBER", expected_present=True, predicted_present=False),
            # FP (Not expected present, predicted present)
            "EXTRA_FIELD": DeclarationEvaluation(field="EXTRA_FIELD", expected_present=False, predicted_present=True),
        }
    )
    calc = BenchmarkMetricsCalculator([case])
    dm = calc.compute_declaration_metrics()
    # TP=2, FP=1, FN=1 -> Precision = 2/3 = 66.67%, Recall = 2/3 = 66.67%, F1 = 66.67%
    assert dm["presence_precision"] == 66.67
    assert dm["presence_recall"] == 66.67
    assert dm["presence_f1_score"] == 66.67


def test_context_accuracy_and_confusion():
    """Verify category and package context accuracy and confusion counts."""
    c1 = CaseEvaluation(
        case_id="C1",
        product_name="Food Item",
        context_evaluation={
            "expected_category": "FOOD",
            "predicted_category": "FOOD",
            "category_match": True,
            "expected_package_type": "RETAIL",
            "predicted_package_type": "RETAIL",
            "package_type_match": True,
            "expected_import_status": "DOMESTIC",
            "predicted_import_status": "DOMESTIC",
            "import_status_match": True,
        }
    )
    c2 = CaseEvaluation(
        case_id="C2",
        product_name="Cosmetic Item",
        context_evaluation={
            "expected_category": "COSMETIC",
            "predicted_category": "UNKNOWN",
            "category_match": False,
            "expected_package_type": "RETAIL",
            "predicted_package_type": "WHOLESALE",
            "package_type_match": False,
            "expected_import_status": "IMPORTED",
            "predicted_import_status": "IMPORTED",
            "import_status_match": True,
        }
    )
    calc = BenchmarkMetricsCalculator([c1, c2])
    cm = calc.compute_context_metrics()
    assert cm["category_accuracy"] == 50.0
    assert cm["package_type_accuracy"] == 50.0
    assert cm["import_status_accuracy"] == 100.0
    assert cm["confusion_matrices"]["category"]["COSMETIC -> UNKNOWN"] == 1


def test_rule_status_comparison_and_mismatches():
    """Verify rule engine agreement rate and mismatch logging."""
    case = CaseEvaluation(
        case_id="R_TEST",
        product_name="Rule Test",
        rule_evaluations={
            "PC-ALL-001": RuleEvaluation(rule_id="PC-ALL-001", expected_status="PASS", predicted_status="PASS", match=True),
            "PC-ALL-002": RuleEvaluation(
                rule_id="PC-ALL-002",
                expected_status="PASS",
                predicted_status="FAIL",
                match=False,
                reason="Quantity unit missing",
            ),
        }
    )
    calc = BenchmarkMetricsCalculator([case])
    rlm = calc.compute_rule_metrics()
    assert rlm["total_evaluated_rules"] == 2
    assert rlm["overall_rule_agreement_rate"] == 50.0
    assert len(rlm["mismatches"]) == 1
    assert rlm["mismatches"][0]["rule_id"] == "PC-ALL-002"
    assert rlm["mismatches"][0]["expected"] == "PASS"
    assert rlm["mismatches"][0]["actual"] == "FAIL"


def test_review_rate_calculation():
    """Verify clean inspection rate vs review required rate."""
    c1 = CaseEvaluation(case_id="C1", product_name="Clean", clean_inspection=True, review_required=False)
    c2 = CaseEvaluation(case_id="C2", product_name="Review", clean_inspection=False, review_required=True)

    calc = BenchmarkMetricsCalculator([c1, c2])
    rm = calc.compute_review_metrics()
    assert rm["clean_inspections_rate"] == 50.0
    assert rm["requiring_review_rate"] == 50.0


def test_grounding_false_rejection_and_unsafe_acceptance():
    """Verify detection of false grounding rejections and unsafe grounding acceptances."""
    case = CaseEvaluation(
        case_id="G_TEST",
        product_name="Grounding Test",
        declaration_evaluations={
            # Grounding accepted value that disagrees with ground truth -> UNSAFE ACCEPTANCE
            "MRP": DeclarationEvaluation(
                field="MRP",
                expected_present=True,
                predicted_present=True,
                normalized_match=False,
                grounding_status="GROUNDED",
                grounding_strategy="EXACT_MATCH",
            ),
            # Ground truth was present & normalized matched, but grounding rejected it -> FALSE REJECTION
            "GENERIC_NAME": DeclarationEvaluation(
                field="GENERIC_NAME",
                expected_present=True,
                predicted_present=True,
                normalized_match=True,
                grounding_status="REJECTED",
                grounding_strategy="REJECTED_UNSUPPORTED",
            ),
        }
    )
    calc = BenchmarkMetricsCalculator([case])
    gm = calc.compute_grounding_metrics()
    assert gm["unsafe_grounding_acceptances"] == 1
    assert gm["false_grounding_rejections"] == 1
    assert gm["grounded_declarations"] == 1
    assert gm["rejected_declarations"] == 1


def test_performance_aggregation():
    """Verify latency stats calculation: mean, median, min, max, p95."""
    c1 = CaseEvaluation(case_id="C1", product_name="1", timings_ms={"total_ms": 100})
    c2 = CaseEvaluation(case_id="C2", product_name="2", timings_ms={"total_ms": 200})
    c3 = CaseEvaluation(case_id="C3", product_name="3", timings_ms={"total_ms": 300})
    calc = BenchmarkMetricsCalculator([c1, c2, c3])
    pm = calc.compute_performance_metrics()
    tot = pm["total_ms"]
    assert tot["mean"] == 200.0
    assert tot["median"] == 200.0
    assert tot["min"] == 100.0
    assert tot["max"] == 300.0


def test_tag_and_case_filtering():
    """Verify loader tag and case filtering."""
    dataset_dict = {
        "version": "1.0.0",
        "cases": [
            {"case_id": "PKG001", "product_name": "A", "tags": ["clean", "food"]},
            {"case_id": "PKG002", "product_name": "B", "tags": ["blurry", "food"]},
            {"case_id": "PKG003", "product_name": "C", "tags": ["clean", "cosmetic"]},
        ]
    }
    # Filter by single tag
    d_blurry = load_benchmark_dataset(dataset_dict, tags=["blurry"])
    assert len(d_blurry.cases) == 1
    assert d_blurry.cases[0].case_id == "PKG002"

    # Filter by multiple tags (union: matches any tag)
    d_clean_or_blurry = load_benchmark_dataset(dataset_dict, tags="cosmetic,blurry")
    assert len(d_clean_or_blurry.cases) == 2

    # Filter by specific case_id
    d_case = load_benchmark_dataset(dataset_dict, case_ids="PKG003")
    assert len(d_case.cases) == 1
    assert d_case.cases[0].case_id == "PKG003"


def test_live_gemini_disabled_by_default(monkeypatch):
    """Ensure live Gemini is strictly disabled by default."""
    monkeypatch.delenv("RUN_GEMINI_BENCHMARK", raising=False)
    evaluator = BenchmarkEvaluator(live_gemini=False)
    assert evaluator.live_gemini is False
    assert evaluator.mode == "MODE_A_OFFLINE"


# ---------------------------------------------------------------------------
# 4. End-to-End Evaluation & Report Generation
# ---------------------------------------------------------------------------

def test_end_to_end_mock_evaluation_and_report_generation(tmp_path):
    """
    Run end-to-end evaluation using dataset.example.json in offline mode.
    Verifies JSON, Markdown, and CSV files are correctly created and populated.
    """
    example_path = Path(__file__).resolve().parent.parent.parent / "benchmark_data" / "dataset.example.json"
    assert example_path.exists(), f"dataset.example.json missing at {example_path}"

    dataset = load_benchmark_dataset(example_path)
    assert len(dataset.cases) >= 4

    evaluator = BenchmarkEvaluator(live_gemini=False)
    case_results = evaluator.evaluate_dataset(dataset.cases)
    assert len(case_results) == len(dataset.cases)

    calculator = BenchmarkMetricsCalculator(case_results)
    all_metrics = calculator.compute_all_metrics()

    assert all_metrics["declaration_metrics"]["value_accuracy"] > 0
    assert all_metrics["context_metrics"]["category_accuracy"] > 0
    assert all_metrics["rule_metrics"]["overall_rule_agreement_rate"] > 0

    # Generate reports
    generator = BenchmarkReportGenerator(
        cases=case_results,
        metrics=all_metrics,
        mode="MODE_A_OFFLINE",
        dataset_name=dataset.dataset_name,
    )
    outputs = generator.generate_all(output_dir=str(tmp_path))

    # Verify report files exist and contain expected sections
    assert os.path.exists(outputs["json"])
    assert os.path.exists(outputs["markdown"])
    assert os.path.exists(outputs["declaration_csv"])
    assert os.path.exists(outputs["rule_csv"])
    assert os.path.exists(outputs["case_csv"])

    with open(outputs["markdown"], "r", encoding="utf-8") as f:
        md_text = f.read()
    assert "# LMAI Inspector Accuracy Benchmark Report" in md_text
    assert "MODE_A_OFFLINE" in md_text
    assert "Executive Metric Summary" in md_text
    assert "Declaration-Level Extraction Accuracy" in md_text
    assert "Evidence Grounding" in md_text
    assert "Deterministic Rule Engine Agreement" in md_text
