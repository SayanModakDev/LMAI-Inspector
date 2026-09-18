# LMAI Inspector Accuracy Benchmark Report

**Dataset:** LMAI Inspector Reference Benchmark Suite  
**Execution Mode:** `MODE_A_OFFLINE`  
**Generated At:** `2026-09-19T07:20:50.494887+00:00`  
**Total Packages Evaluated:** 4  
**Total Panel Images:** 6

> [!NOTE]
> **OFFLINE REPRODUCIBLE RUN:** Executed with Gemini API quota consumption strictly at ZERO. Uses deterministic pipelines and recorded mocks.

## 1. Executive Metric Summary

| Metric Dimension | Measured Score | Status / Target |
| :--- | :--- | :--- |
| **Declaration Value Accuracy** | 83.33% | Normalized string match |
| **Declaration Presence F1** | 85.71% | Prec: 75.0%, Rec: 100.0% |
| **Required Field Recall** | 100.0% | Statutory mandatory fields |
| **Category Classification** | 100.0% | Commodity domain accuracy |
| **Package Scope Accuracy** | 100.0% | Retail vs Wholesale |
| **Origin Status Accuracy** | 100.0% | Domestic vs Imported |
| **Overall Rule Agreement** | 89.47% | Deterministic matrix agreement |
| **Clean Automated Inspection Rate** | 0.0% | Inspections without manual review |
| **Unsafe Grounding Acceptances** | 0 | Grounded values contradicting truth |
| **False Grounding Rejections** | 0 | Correct values falsely rejected |
| **Overall Compliance Agreement** | 25.0% | End-to-end outcome agreement |

## 2. Declaration-Level Extraction Accuracy

- **Total Expected Declarations:** 36
- **Exact Match Accuracy:** 66.67%
- **Normalized Value Accuracy:** 83.33%
- **Required Field Value Accuracy:** 83.33%

### Per-Field Breakdown

| Canonical Parameter | Expected | Detected | Exact Match | Normalized Match | Value Accuracy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `BATCH_NUMBER` | 2 | 2 | 2 | 2 | 100.0% |
| `BEST_BEFORE_USE_BY` | 1 | 1 | 1 | 1 | 100.0% |
| `BRAND` | 0 | 4 | 0 | 0 | N/A |
| `CONSUMER_CARE` | 2 | 2 | 1 | 1 | 50.0% |
| `COUNTRY_OF_ORIGIN` | 0 | 4 | 0 | 0 | N/A |
| `DECLARED_NET_QUANTITY` | 4 | 4 | 4 | 4 | 100.0% |
| `EXPIRY_DATE` | 1 | 1 | 1 | 1 | 100.0% |
| `FSSAI_LICENSE` | 2 | 3 | 2 | 2 | 100.0% |
| `GENERIC_NAME` | 4 | 4 | 0 | 4 | 100.0% |
| `MANUFACTURER_ADDRESS` | 4 | 4 | 2 | 4 | 100.0% |
| `MANUFACTURER_NAME` | 4 | 4 | 4 | 4 | 100.0% |
| `MONTH_YEAR_MANUFACTURE` | 4 | 4 | 4 | 4 | 100.0% |
| `MRP` | 3 | 3 | 3 | 3 | 100.0% |
| `PRODUCT_NAME` | 4 | 4 | 0 | 0 | 0.0% |
| `PRODUCT_TYPE` | 0 | 3 | 0 | 0 | N/A |
| `VEG_NONVEG_SYMBOL` | 1 | 1 | 0 | 0 | 0.0% |

## 3. Evidence Grounding & Hallucination Prevention

- **Grounded Declarations:** 0
- **Rejected Declarations:** 0
- **Grounding Acceptance Rate:** 0.0%
- **Unsafe Grounding Acceptances:** **0** (Critical risk metric)
- **False Grounding Rejections:** 0

### Grounding Strategy Breakdown

| Derivation Strategy | Occurrences |
| :--- | :--- |

## 4. Context Classification & Regulatory Scope

- **Category Accuracy:** 100.0%
- **Package Type Accuracy:** 100.0%
- **Import Status Accuracy:** 100.0%

### Category Confusion Counts

| Expected -> Predicted | Count |
| :--- | :--- |
| FOOD -> FOOD | 3 |
| COSMETIC -> COSMETIC | 1 |

## 5. Deterministic Rule Engine Agreement

- **Total Evaluated Rules:** 19
- **Overall Rule-Status Agreement Rate:** 89.47%

| Status Dimension | Expected Count | Predicted Count | Matched | Agreement Rate |
| :--- | :--- | :--- | :--- | :--- |
| `PASS` | 15 | 13 | 13 | 86.67% |
| `NOT_VERIFIABLE` | 1 | 2 | 1 | 100.0% |
| `NOT_APPLICABLE` | 2 | 3 | 2 | 100.0% |
| `FAIL` | 1 | 1 | 1 | 100.0% |

## 6. Gemini Resolution & Fallback Behavior

- **Primary Success Rate:** 0.0%
- **Fallback Rate:** 0.0%
- **Error Rate:** 0.0%
- **Deterministic-Only Rate:** 100.0%

## 7. Performance & Latency Metrics

| Pipeline Stage | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | p95 (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `total_ms` | 45 | 43.5 | 38 | 55 | 55 |
| `ocr_ms` | 0 | 0.0 | 0 | 0 | 0 |
| `declaration_extraction_ms` | 36.8 | 36.0 | 31 | 44 | 44 |
| `gemini_total_ms` | 0 | 0.0 | 0 | 0 | 0 |
| `rule_evaluation_ms` | 2 | 1.5 | 1 | 4 | 4 |

## 8. Failure Taxonomy & Root Cause Classification

| Error Category | Occurrences | Description |
| :--- | :--- | :--- |
| `GROUNDING_FALSE_ACCEPT` | 12 | Candidate accepted that was not declared in ground truth |
| `DETERMINISTIC_EXTRACTION_ERROR` | 6 | Text present in OCR tokens but candidate association failed |
| `RULE_VALIDATION_ERROR` | 1 | Deterministic validator status differed from ground truth |
| `APPLICABILITY_ERROR` | 1 | Rule was expected applicable/inapplicable but engine diverged |

## 9. Automatic Image Quality Gate Performance

- **Total Evaluated Cases:** 4
- **Quality Accept Rate:** 100.0%
- **Quality Warning Rate:** 0.0%
- **Quality Recapture Rate:** 0.0%
- **False Recaptures (Valid Image Rejected):** 0
- **Missed Bad Images (Deliberate Defect Accepted):** 0

## 10. Per-Case Mismatch Log

| Case ID | Rule ID | Expected | Actual | Error Category | Detail |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `PKG001` | `PC-ALL-001` | `PASS` | `NOT_VERIFIABLE` | `RULE_VALIDATION_ERROR` | Conflicting evidence detected across package views for 'PRODUCT_NAME': [Digestive Biscuit, 100% Vegetarian Made in India]. Declaration not detected reliably from package images. |
| `PKG001` | `PC-ALL-006` | `PASS` | `NOT_APPLICABLE` | `APPLICABILITY_ERROR` |  |