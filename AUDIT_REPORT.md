# Audit Report — SIH 2026 PS 26034

**Project:** AI-assisted packaged-commodity compliance screening  
**Date of audit:** 2026-09-06  
**Scope:** Existing repository only (no rebuild)

This report documents the inspected architecture and defects. Implementation of repairs continues in the same change set.

**Architectural principle (enforced):** OCR/AI extracts evidence. The legal rule engine makes deterministic rule decisions. The system must not invent legal requirements, must not treat OCR confidence as compliance, and must leave final legal verification with an authorized inspector.

---

## 1. Current architecture

Image/camera/upload → OpenCV preprocessing → PaddleOCR → declaration extraction → category/product-type classification → rule applicability → deterministic evaluation → PASS/FAIL/NOT_VERIFIABLE/NOT_APPLICABLE → findings → SQLite/MySQL → PDF → React dashboard.

AI/OCR does **not** currently output a legal verdict independently; `evaluate_rules()` does. Several pipelines still **contaminate** that decision with guessed context, visual false positives, and overwritten multi-image evidence.

---

## 2. Backend architecture

| Area | Location |
|------|----------|
| FastAPI entry | `backend/app/main.py` |
| Scan pipeline | `backend/app/api/scan.py` |
| History / dashboard / PDF / manual input | `backend/app/api/inspections.py` |
| Categories / rules APIs | `backend/app/api/categories.py`, `rules.py` |
| OCR | `backend/app/ocr/` |
| Extraction | `backend/app/extraction/declaration_extractor.py` |
| Classification | `backend/app/classification/category_classifier.py` |
| Applicability / engine | `backend/app/rules/` |
| PDF | `backend/app/reports/pdf_report.py` |
| Barcode / visual | `backend/app/barcode_decoder.py`, `visual_detection.py` |

Database: SQLAlchemy models + `database/schema.sql`. Dev fallback: SQLite (`DATABASE_ENABLED=false`).

---

## 3. Frontend architecture

React + Vite (`frontend/src`):

- `Scan.jsx` / `Processing.jsx` — multi-image upload and camera
- `Result.jsx` — inspection result
- `Dashboard.jsx`, `History.jsx`
- `services/api.js`

Proxy to `/api`. Status badges historically mismatch backend values (`NON-COMPLIANT` vs `NON_COMPLIANT`).

---

## 4. OCR pipeline

1. `preprocess_image`: EXIF orientation, resize, CLAHE, denoise, sharpen.  
2. `run_ocr`: **process-global** PaddleOCR singleton (good). First pass on processed image; retry threshold/gray-sharp only if detections are weak.  
3. Per-image OCR concatenated with `[IMAGE n]` markers.

**Issues:** no MIME/magic-byte validation on upload; visual veg/non-veg detector runs on every image including cosmetics.

---

## 5. Extraction pipeline

Regex + keyword line collection in `declaration_extractor.py`. Per-image extract then `merge_extracted_fields` (highest confidence wins).

**Issues confirmed on Inspection #35 (Jive Soft Talc):**

| Defect | Observed |
|--------|----------|
| Date proximity | `MONTH_YEAR_MANUFACTURE = 18/04/2027` (Use Before date) |
| Use-before missed | `USE_BEFORE_DATE` not extracted |
| Manufacturer missed | `Akan Products Pvt. Ltd.` visible; `MANUFACTURER_NAME` NOT_VERIFIABLE |
| Ingredients contamination | Ingredients include manufacturer + `NET QUANTITY` + `300 g` |
| Veg symbol on cosmetic | `VEG_NONVEG_SYMBOL = NON_VEGETARIAN` from OpenCV |

Date helper searches 150 characters after `mfd`/`mfg`, so the token `USP,MFD*` captures a later Use-Before date. `manufactured` as a date keyword can collide with `Manufactured by`. Ingredient collection does not stop at manufacturer/net quantity.

---

## 6. Classification pipeline

Vocabulary-weighted FOOD / COSMETIC / HOUSEHOLD / PHARMACEUTICAL / ELECTRONICS plus product types (SALT, SUGAR, TALCUM_POWDER, …).

Jive *can* classify correctly as COSMETIC / TALCUM_POWDER from OCR. Visual veg detection still attaches a food symbol to cosmetics after classification.

Package type and import status are **form defaults** (`RETAIL` / `DOMESTIC`), not inferred from the photograph — but the UI does not state that they are inspector-declared.

---

## 7. Rule engine

`evaluate_rules()`:

- Missing required evidence → `NOT_VERIFIABLE` (not FAIL) — **correct**
- Weak OCR (`confidence < 0.6`) → `NOT_VERIFIABLE` — **correct** (confidence is not compliance)
- `clearly_invalid` → FAIL
- Physical rules skipped unless `has_physical_data`
- Overall: `COMPLIANT` / `NON-COMPLIANT` / `NOT_VERIFIABLE`

No fake percentage score in the engine. UI/docs still use “Compliant” without the inspector-facing outcome wording.

---

## 8. Rule matrix

Single file: `data/rule_matrix.json` (synced to `rules` table).

Problems:

- Most `rule_reference` values are `PENDING_VERIFICATION` even where Rule 6 headings are knowable from official PC Rules text
- Invented `effective_from: 2011-01-01` (PC Rules text examined: commencement **1 April 2011**)
- FSSAI food rules use Legal Metrology as `source_document` in places
- Cosmetic rules cite “Drugs and Cosmetics Act / Legal Metrology” instead of Cosmetics Rules, 2020 Rule 34
- Missing traceability fields (`source_authority`, `source_url`, `rule_reference_status`)
- `PC-ALL-001` PRODUCT_NAME is treated as a mandatory PC Rules heading; Rule 6(1)(b) is **generic/common name**, not brand/product name
- PHYSICAL_ONLY rules omitted from every image-only inspection, so inspectors never see “physical verification required”

---

## 9. Legal sources currently used

Informal strings only:

- Legal Metrology (Packaged Commodities) Rules, 2011
- FSSAI / Food Safety and Standards Act, 2006 (partial)
- Drugs and Cosmetics Act (partial, mis-cited for cosmetics labelling)

Not systematically versioned. Cosmetics Rules, 2020 not named. Labelling and Display Regulations, 2020 not named on several food rules.

---

## 10. Database structure

Tables: `users`, `inspections`, `inspection_images`, `products`, `ocr_results`, `extracted_fields`, `rules`, `rule_results`, `evidence`, `reports`.

Schema and models are largely aligned. Defaults `package_type=RETAIL`, `import_status=DOMESTIC` encode a guess if the inspector never chooses. `InspectionSummary` omits `package_type` while History UI reads it.

---

## 11. PDF generation

ReportLab Platypus `LongTable` in landscape. Sections: summary, findings, compliance table, images, disclaimer.

Missing required sections: extracted declarations, physical verification, regulatory sources, limitations, inspector review, rule version/reference columns. Evidence can overflow; product/declaration tables incomplete.

---

## 12. Existing tests

`backend/tests/test_logic.py` — extractor, classifier, applicability, engine, barcode, Tata Salt dates, multiline manufacturer, Jive *classification* smoke, decimal `0.73` not a date.

**Not covered:** Jive manufacturer/ingredients/use-before; conflicting multi-image evidence; cosmetic vs FSSAI; physical quantity not claimed from image; package type not guessed from OCR.

---

## 13. Existing problems

1. Context-unaware date extraction (Inspection 35 MFD).  
2. Manufacturer not recovered from `Pvt. Ltd.` lines without a clean “Manufactured by”.  
3. Ingredients over-read into the next label block.  
4. Veg/non-veg visual detector applied to cosmetics.  
5. Multi-image merge silently prefers higher confidence (no `CONFLICTING_EVIDENCE`).  
6. Barcode lookup can overwrite product identity (supplementary evidence should be labelled as such).  
7. Rule matrix invented dates / weak citations.  
8. PRODUCT_NAME treated as a statutory PC Rules heading.  
9. Physical/font-size rules hidden unless manual weight is entered.  
10. Frontend: “Net Quantity” not “Declared Net Quantity”; no “Actual Measured Quantity / physical verification required”; History filter `NON_COMPLIANT` never matches `NON-COMPLIANT`.  
11. Upload: filename extension only.  
12. PDF incomplete.  
13. `.env` contains a local DB password (gitignored; must remain uncommitted).  
14. OpenAI is **not** a runtime dependency (must stay that way).

---

## 14. Legal risks

- Reporting a Use-Before date as manufacture date.  
- Applying FSSAI veg/non-veg findings to cosmetics.  
- Treating missing OCR as legal FAIL (currently avoided — must be preserved).  
- Presenting barcode lookup or Open Food Facts as legal proof.  
- Claiming image-based net-content or millimetre font-size verification.  
- Invented rule numbers or effective dates in the matrix.  
- Inspector-facing “COMPLIANT” without the screening disclaimer.

---

## 15. Technical risks

- Multi-image last-write / silent merge.  
- Date window spanning unrelated lines.  
- Visual colour contours on pink packaging.  
- History status filter mismatch.  
- Duplicate `brand`/`product_type` fields in `ScanResponse`.

---

## 16. Recommended fixes (implemented after this report)

1. Line/label-scoped date extraction; reject decimals, prices, barcodes, phones.  
2. Manufacturer/address from manufactured/packed/marketed lines **and** `Pvt. Ltd.` entities; stop at section boundaries.  
3. Ingredients stop at manufacturer/net quantity/MRP/dates/care.  
4. Merge with conflict flags; keep stronger OCR; never silently drop disagreement.  
5. Barcode stored as `BARCODE` / `BARCODE_EVIDENCE`; lookup not legal proof.  
6. Veg detector only when category is FOOD.  
7. Rule matrix: official citations, `NEEDS_VERIFICATION` where exact gazette mapping is incomplete; no invented dates.  
8. PRODUCT_NAME screening vs GENERIC_NAME statutory.  
9. Physical rules always listed as `PHYSICAL_VERIFICATION_REQUIRED`.  
10. Outcome labels without percentages.  
11. PDF/UI/copy/tests/docs as specified in the work order.

---

## 17. Files that need modification

- `data/rule_matrix.json`
- `backend/app/extraction/declaration_extractor.py`
- `backend/app/classification/category_classifier.py`
- `backend/app/rules/applicability.py`
- `backend/app/rules/rule_engine.py`
- `backend/app/api/scan.py`
- `backend/app/api/inspections.py`
- `backend/app/reports/pdf_report.py`
- `backend/app/database/schemas.py`
- `backend/app/database/models.py` (comments/defaults only)
- `backend/app/utils/helpers.py` (upload safety)
- `backend/app/visual_detection.py` (no food claim without category gate in scan)
- `backend/tests/test_logic.py` (add tests; do not delete)
- `frontend/src/pages/Result.jsx`, `Scan.jsx`, `History.jsx`, `Dashboard.jsx`
- `frontend/src/services/api.js`
- `README.md`
- New: `docs/legal/*`

No project rebuild. No deletion of existing tests. No OpenAI dependency.
