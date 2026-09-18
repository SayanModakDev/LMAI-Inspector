# LMAI Inspector Accuracy Benchmark Report

**Dataset:** LMAI Inspector Reference Benchmark Suite  
**Execution Mode:** `MODE_A_OFFLINE`  
**Generated At:** `2026-09-19T04:12:03.268789+00:00`  
**Total Packages Evaluated:** 1  
**Total Panel Images:** 2

> [!NOTE]
> **OFFLINE REPRODUCIBLE RUN:** Executed with Gemini API quota consumption strictly at ZERO. Uses deterministic pipelines and recorded mocks.

## 1. Executive Metric Summary

| Metric Dimension | Measured Score | Status / Target |
| :--- | :--- | :--- |
| **Declaration Value Accuracy** | 90.0% | Normalized string match |
| **Declaration Presence F1** | 90.91% | Prec: 83.33%, Rec: 100.0% |
| **Required Field Recall** | 100.0% | Statutory mandatory fields |
| **Category Classification** | 100.0% | Commodity domain accuracy |
| **Package Scope Accuracy** | 100.0% | Retail vs Wholesale |
| **Origin Status Accuracy** | 100.0% | Domestic vs Imported |
| **Overall Rule Agreement** | 100.0% | Deterministic matrix agreement |
| **Clean Automated Inspection Rate** | 0.0% | Inspections without manual review |
| **Unsafe Grounding Acceptances** | 0 | Grounded values contradicting truth |
| **False Grounding Rejections** | 0 | Correct values falsely rejected |
| **Overall Compliance Agreement** | 0.0% | End-to-end outcome agreement |

## 2. Declaration-Level Extraction Accuracy

- **Total Expected Declarations:** 10
- **Exact Match Accuracy:** 70.0%
- **Normalized Value Accuracy:** 90.0%
- **Required Field Value Accuracy:** 90.0%

### Per-Field Breakdown

| Canonical Parameter | Expected | Detected | Exact Match | Normalized Match | Value Accuracy |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `BATCH_NUMBER` | 1 | 1 | 1 | 1 | 100.0% |
| `BRAND` | 0 | 1 | 0 | 0 | N/A |
| `CONSUMER_CARE` | 1 | 1 | 1 | 1 | 100.0% |
| `COUNTRY_OF_ORIGIN` | 0 | 1 | 0 | 0 | N/A |
| `DECLARED_NET_QUANTITY` | 1 | 1 | 1 | 1 | 100.0% |
| `EXPIRY_DATE` | 1 | 1 | 1 | 1 | 100.0% |
| `GENERIC_NAME` | 1 | 1 | 0 | 1 | 100.0% |
| `MANUFACTURER_ADDRESS` | 1 | 1 | 0 | 1 | 100.0% |
| `MANUFACTURER_NAME` | 1 | 1 | 1 | 1 | 100.0% |
| `MONTH_YEAR_MANUFACTURE` | 1 | 1 | 1 | 1 | 100.0% |
| `MRP` | 1 | 1 | 1 | 1 | 100.0% |
| `PRODUCT_NAME` | 1 | 1 | 0 | 0 | 0.0% |

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
| COSMETIC -> COSMETIC | 1 |

## 5. Deterministic Rule Engine Agreement

- **Total Evaluated Rules:** 6
- **Overall Rule-Status Agreement Rate:** 100.0%

| Status Dimension | Expected Count | Predicted Count | Matched | Agreement Rate |
| :--- | :--- | :--- | :--- | :--- |
| `PASS` | 5 | 5 | 5 | 100.0% |
| `NOT_APPLICABLE` | 1 | 1 | 1 | 100.0% |

## 6. Gemini Resolution & Fallback Behavior

- **Primary Success Rate:** 0.0%
- **Fallback Rate:** 0.0%
- **Error Rate:** 0.0%
- **Deterministic-Only Rate:** 100.0%

## 7. Performance & Latency Metrics

| Pipeline Stage | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | p95 (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `total_ms` | 45 | 45 | 45 | 45 | 45 |
| `ocr_ms` | 0 | 0 | 0 | 0 | 0 |
| `declaration_extraction_ms` | 36 | 36 | 36 | 36 | 36 |
| `gemini_total_ms` | 0 | 0 | 0 | 0 | 0 |
| `rule_evaluation_ms` | 4 | 4 | 4 | 4 | 4 |

## 8. Failure Taxonomy & Root Cause Classification

| Error Category | Occurrences | Description |
| :--- | :--- | :--- |
| `GROUNDING_FALSE_ACCEPT` | 2 | Candidate accepted that was not declared in ground truth |
| `DETERMINISTIC_EXTRACTION_ERROR` | 1 | Text present in OCR tokens but candidate association failed |

## 9. Per-Case Mismatch Log

No rule mismatches recorded across evaluated benchmark cases.
