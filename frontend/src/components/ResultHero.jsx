import React from 'react';
import { Link } from 'react-router-dom';
import {
  Printer,
  History,
  PlusCircle,
  FileCheck,
  AlertTriangle,
  XCircle,
  CheckCircle2,
  MinusCircle,
  Package,
  Layers,
  Cpu,
  Barcode,
  Globe,
  Tag,
  ChevronRight,
} from 'lucide-react';
import StatusBadge from './StatusBadge';
import { formatISTDateTime } from '../utils/dateUtils';
import './ResultHero.css';

/**
 * ResultHero Component
 * Primary inspection result header adhering strictly to backend source of truth:
 * - Summary counts derived directly from backend summary object
 * - Canonical overall status (COMPLIANT, NON-COMPLIANT, REQUIRES REVIEW)
 * - Concise dynamic explanation based on backend findings
 * - Product Identity conflict handling (never picks an arbitrary winner)
 * - Metadata summary bar
 */
const ResultHero = ({
  inspection,
  ruleResults = [],
  reportUrl = null,
  generatingReport = false,
  onGenerateReport,
  onViewConflict,
}) => {
  if (!inspection) return null;

  // 1. Strict Canonical Summary Counts (directly from backend summary)
  const summary = inspection.summary || {};
  const passCount =
    summary.passed_count ??
    summary.passed ??
    ruleResults.filter((r) => r.status === 'PASS').length;

  const failCount =
    summary.failed_count ??
    summary.failed ??
    ruleResults.filter((r) => r.status === 'FAIL').length;

  const reviewCount =
    summary.review_count ??
    summary.review ??
    ruleResults.filter(
      (r) =>
        r.status === 'NOT_VERIFIABLE' ||
        r.status === 'MANUAL_CHECK' ||
        r.status === 'REVIEW' ||
        r.status === 'NEEDS_REVIEW'
    ).length;

  const naCount =
    summary.not_applicable_count ??
    summary.na_count ??
    summary.not_applicable ??
    ruleResults.filter((r) => r.status === 'NOT_APPLICABLE').length;

  // 2. Canonical Overall Status Normalization (strictly 3 allowed states)
  const rawStatus = (inspection.overall_result || '').toUpperCase().replace(/-/g, '_').trim();
  let canonicalStatus = 'REQUIRES REVIEW';
  let bannerModifier = 'review';

  if (rawStatus === 'COMPLIANT') {
    canonicalStatus = 'COMPLIANT';
    bannerModifier = 'compliant';
  } else if (rawStatus === 'NON_COMPLIANT') {
    canonicalStatus = 'NON-COMPLIANT';
    bannerModifier = 'non-compliant';
  } else {
    canonicalStatus = 'REQUIRES REVIEW';
    bannerModifier = 'review';
  }

  // 3. Collect Review / Failure Reasons Dynamically
  const reviewRules = ruleResults.filter(
    (r) =>
      r.status === 'NOT_VERIFIABLE' ||
      r.status === 'MANUAL_CHECK' ||
      r.status === 'REVIEW' ||
      r.status === 'NEEDS_REVIEW'
  );

  const failRules = ruleResults.filter((r) => r.status === 'FAIL');

  // 4. Concise Dynamic Explanation
  const getExplanationContent = () => {
    if (canonicalStatus === 'NON-COMPLIANT') {
      const firstFail = failRules[0];
      const failReason =
        firstFail?.reason ||
        firstFail?.message ||
        (inspection.findings?.failed && inspection.findings.failed[0]) ||
        'One or more mandatory statutory declarations failed deterministic validation requirements.';
      return {
        main: 'Deterministic screening identified statutory violations under Legal Metrology Rules.',
        reasons: failRules.map((r) => r.reason || r.message || r.parameter?.replace(/_/g, ' ')).filter(Boolean),
      };
    }

    if (canonicalStatus === 'REQUIRES REVIEW') {
      return {
        main: 'Manual review is required because one or more declarations could not be conclusively verified.',
        reasons: reviewRules
          .slice(0, 3)
          .map((r) => r.reason || r.message || `${(r.parameter || '').replace(/_/g, ' ')} requires verification`)
          .filter(Boolean),
        extraCount: Math.max(0, reviewRules.length - 3),
      };
    }

    return {
      main: 'All statutory declarations satisfy mandatory Legal Metrology requirements.',
      reasons: [],
    };
  };

  const explanation = getExplanationContent();

  // 5. Product Identity Conflict Detection
  const isProductNameConflict =
    String(inspection.product_name || '').startsWith('CONFLICT:') ||
    (inspection.extracted_fields || []).some(
      (f) =>
        (f.field_name === 'PRODUCT_NAME' || f.parameter === 'PRODUCT_NAME') &&
        (String(f.field_value || '').startsWith('CONFLICT:') ||
          f.source === 'MULTI_IMAGE_CONFLICT' ||
          f.extraction_method === 'MULTI_IMAGE_CONFLICT' ||
          f.candidate_classification === 'TRUE_CONFLICT' ||
          f.status === 'AMBIGUOUS' ||
          f.is_ambiguous ||
          (Array.isArray(f.candidates) && f.candidates.length > 1))
    ) ||
    ruleResults.some(
      (r) =>
        r.parameter === 'PRODUCT_NAME' &&
        r.status === 'NOT_VERIFIABLE' &&
        (r.reason || '').toLowerCase().includes('competing')
    );

  const productIdentity = isProductNameConflict
    ? null
    : (inspection.product_name ||
       inspection.brand ||
       inspection.product?.product_name ||
       inspection.product?.brand ||
       null);

  const brandName =
    inspection.brand ||
    inspection.product?.brand ||
    inspection.extracted_fields?.find((f) => f.field_name === 'BRAND')?.field_value ||
    null;

  const categoryName = inspection.category || inspection.product?.category || null;
  const productType = inspection.product_type || inspection.product?.product_type || null;
  const packageType = inspection.package_type || inspection.product?.package_type || 'RETAIL';
  const importStatus = inspection.import_status || inspection.product?.import_status || inspection.product?.country_of_origin || 'DOMESTIC';

  const imageCount = Array.isArray(inspection.images) && inspection.images.length > 0
    ? inspection.images.length
    : (inspection.image_path ? 1 : null);

  const ocrData = inspection.ocr_result?.ocr_data;
  const ocrItemsCount = Array.isArray(ocrData?.ocr_items) ? ocrData.ocr_items.length : null;
  const ocrEngine = inspection.ocr_result?.ocr_engine || (inspection.ocr_result ? 'PaddleOCR' : null);

  const barcodeResult = ocrData?.barcode_result;
  const barcodeValue = barcodeResult?.value || null;

  const handleScrollToConflict = (e) => {
    e?.preventDefault();
    if (onViewConflict) {
      onViewConflict();
    } else {
      const el = document.getElementById('product-conflict-section');
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  };

  return (
    <div className="results-hero-container">
      {/* Primary Hero Header */}
      <div className={`results-hero-card results-hero-card--${bannerModifier}`}>
        <div className="results-hero-main">
          {/* Top Identifier Row */}
          <div className="results-hero-id-row">
            <span className="results-hero-title">Inspection Dossier</span>
            <span className="results-hero-id font-mono">#{inspection.id}</span>
            <span className="results-hero-dot">•</span>
            <span className="results-hero-timestamp">
              {formatISTDateTime(inspection.created_at || inspection.inspection_date)}
            </span>
            {categoryName && (
              <>
                <span className="results-hero-dot">•</span>
                <span className="badge badge-gray text-2xs font-semibold">{categoryName}</span>
              </>
            )}
          </div>

          {/* Overall Screening Status + Dynamic Explanation */}
          <div className="results-hero-status-row">
            <div className="results-hero-status-badge">
              <StatusBadge status={canonicalStatus} size="lg" showBinary={true} />
            </div>
            <div className="results-hero-explanation-block">
              <p className="results-hero-explanation font-medium">{explanation.main}</p>
              {explanation.reasons.length > 0 && (
                <div className="results-hero-reasons-list text-xs text-secondary mt-1">
                  {explanation.reasons.map((r, idx) => (
                    <span key={idx} className="reason-item">
                      {idx > 0 && <span className="reason-separator"> • </span>}
                      {r}
                    </span>
                  ))}
                  {explanation.extraCount > 0 && (
                    <span className="reason-item text-muted"> +{explanation.extraCount} more</span>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Backend Canonical Rule Counts Row */}
          <div className="results-hero-counts" role="region" aria-label="Screening Rule Counters">
            <div
              className={`count-pill count-pill--pass ${passCount > 0 ? 'count-pill--active' : ''}`}
              title={`${passCount} rules passed deterministic verification`}
            >
              <CheckCircle2 size={13} />
              <span className="count-num font-mono">{passCount}</span>
              <span className="count-label">PASSED</span>
            </div>

            <div
              className={`count-pill count-pill--fail ${failCount > 0 ? 'count-pill--active' : ''}`}
              title={`${failCount} rules failed statutory requirements`}
            >
              <XCircle size={13} />
              <span className="count-num font-mono">{failCount}</span>
              <span className="count-label">FAILED</span>
            </div>

            <div
              className={`count-pill count-pill--review ${reviewCount > 0 ? 'count-pill--active' : ''}`}
              title={`${reviewCount} rules require manual verification or certified measurement`}
            >
              <AlertTriangle size={13} />
              <span className="count-num font-mono">{reviewCount}</span>
              <span className="count-label">REVIEW</span>
            </div>

            <div
              className="count-pill count-pill--na"
              title={`${naCount} rules evaluated as not applicable to this package`}
            >
              <MinusCircle size={13} />
              <span className="count-num font-mono">{naCount}</span>
              <span className="count-label">N/A</span>
            </div>
          </div>
        </div>

        {/* Top-Level Workstation Actions */}
        <div className="results-hero-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={onGenerateReport}
            disabled={generatingReport}
            title="Compile or view official Legal Metrology inspection PDF report"
          >
            <Printer size={14} />
            <span>
              {generatingReport
                ? 'Compiling Report...'
                : reportUrl
                ? 'View Inspection Report'
                : 'Generate Report'}
            </span>
          </button>

          {reportUrl && (
            <a
              href={reportUrl}
              download={`inspection_report_${inspection.id}.pdf`}
              className="btn btn-outline btn-sm"
              title="Download generated PDF report dossier"
            >
              <span>Download PDF</span>
            </a>
          )}

          <Link to="/history" className="btn btn-outline btn-sm" title="Return to past inspection history">
            <History size={14} />
            <span>History</span>
          </Link>

          <Link to="/scan" className="btn btn-outline btn-sm" title="Start screening another package">
            <PlusCircle size={14} />
            <span>New Scan</span>
          </Link>
        </div>
      </div>

      {/* Metadata Summary Bar */}
      <div className="result-summary-bar" role="region" aria-label="Key Inspection Metadata">
        {/* Product Identity / Conflict */}
        {isProductNameConflict ? (
          <div className="summary-item summary-item--conflict">
            <Package size={14} className="summary-icon text-amber-600" />
            <div className="summary-content">
              <span className="summary-label">Product Identity</span>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="badge badge-warning font-mono text-2xs font-bold">
                  CONFLICT
                </span>
                <button
                  type="button"
                  onClick={handleScrollToConflict}
                  className="conflict-view-btn text-2xs font-semibold text-primary inline-flex items-center gap-0.5"
                  title="View conflicting product candidates"
                >
                  <span>View evidence</span>
                  <ChevronRight size={10} />
                </button>
              </div>
            </div>
          </div>
        ) : productIdentity ? (
          <div className="summary-item">
            <Package size={14} className="summary-icon text-primary" />
            <div className="summary-content">
              <span className="summary-label">Product Identity</span>
              <span className="summary-val font-semibold truncate max-w-[200px]" title={productIdentity}>
                {productIdentity}
              </span>
            </div>
          </div>
        ) : null}

        {/* Brand */}
        {brandName && (
          <div className="summary-item">
            <Tag size={14} className="summary-icon text-secondary" />
            <div className="summary-content">
              <span className="summary-label">Brand</span>
              <span className="summary-val font-medium">{brandName}</span>
            </div>
          </div>
        )}

        {/* Product Type / Classification */}
        {(productType || packageType) && (
          <div className="summary-item">
            <Layers size={14} className="summary-icon text-secondary" />
            <div className="summary-content">
              <span className="summary-label">Package Classification</span>
              <span className="summary-val">
                {[productType, packageType].filter(Boolean).join(' • ')}
              </span>
            </div>
          </div>
        )}

        {/* Import / Origin Status */}
        {importStatus && (
          <div className="summary-item">
            <Globe size={14} className="summary-icon text-secondary" />
            <div className="summary-content">
              <span className="summary-label">Origin Status</span>
              <span className="summary-val font-mono">{importStatus}</span>
            </div>
          </div>
        )}

        {/* Package Images / Views */}
        {imageCount !== null && (
          <div className="summary-item">
            <FileCheck size={14} className="summary-icon text-teal" />
            <div className="summary-content">
              <span className="summary-label">Package Views</span>
              <span className="summary-val font-mono">
                {imageCount} {imageCount === 1 ? 'Panel' : 'Panels'}
              </span>
            </div>
          </div>
        )}

        {/* OCR Subsystem */}
        <div className="summary-item">
          <Cpu size={14} className="summary-icon text-primary" />
          <div className="summary-content">
            <span className="summary-label">OCR Engine</span>
            <span className="summary-val font-mono">
              {ocrEngine ? (
                ocrItemsCount !== null && ocrItemsCount > 0 ? (
                  `${ocrEngine} (${ocrItemsCount} boxes)`
                ) : (
                  `${ocrEngine}`
                )
              ) : (
                'Unavailable'
              )}
            </span>
          </div>
        </div>

        {/* Barcode Subsystem */}
        <div className="summary-item">
          <Barcode size={14} className="summary-icon text-secondary" />
          <div className="summary-content">
            <span className="summary-label">Barcode Evidence</span>
            <span className="summary-val font-mono">
              {barcodeValue ? (
                <span className="text-teal font-semibold">
                  {barcodeValue.length > 22 ? `${barcodeValue.substring(0, 20)}...` : barcodeValue}
                </span>
              ) : (
                <span className="text-muted">Not Detected</span>
              )}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ResultHero;
