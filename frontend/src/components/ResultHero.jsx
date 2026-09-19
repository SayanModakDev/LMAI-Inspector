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
 * - Canonical image-screening status (COMPLIANT, NON-COMPLIANT, REVIEW REQUIRED)
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

  const [showDetails, setShowDetails] = React.useState(false);
  const isPhysicalRule = (r) =>
    r.status === 'OUT_OF_SCOPE_PHYSICAL_VERIFICATION' ||
    r.verification_type === 'PHYSICAL_VERIFICATION_REQUIRED' ||
    r.verification_type === 'PHYSICAL_CHECK' ||
    r.rule_id === 'PC-ALL-012' ||
    r.rule_id === 'PC-ALL-013' ||
    r.parameter === 'ACTUAL_NET_CONTENT' ||
    r.parameter === 'FONT_SIZE_COMPLIANCE';
  const imageRules = ruleResults.filter((r) => !isPhysicalRule(r));
  const physicalRules = inspection.physical_verification?.length
    ? inspection.physical_verification
    : ruleResults.filter(isPhysicalRule);

  // 1. Strict Canonical Summary Counts (directly from backend summary)
  const summary = inspection.summary || {};
  const passCount =
    summary.passed_count ??
    summary.passed ??
    imageRules.filter((r) => r.status === 'PASS').length;

  const failCount =
    summary.failed_count ??
    summary.failed ??
    imageRules.filter((r) => r.status === 'FAIL').length;

  const reviewCount =
    summary.review_count ??
    summary.review ??
    imageRules.filter(
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
    imageRules.filter((r) => r.status === 'NOT_APPLICABLE').length;

  // 2. Canonical Overall Status Normalization (strictly 3 allowed states)
  const rawStatus = (inspection.screening_result || inspection.overall_result || '').toUpperCase().replace(/-/g, '_').trim();
  let canonicalStatus = 'REVIEW_REQUIRED';
  let bannerModifier = 'review';

  if (rawStatus === 'COMPLIANT') {
    canonicalStatus = 'COMPLIANT';
    bannerModifier = 'compliant';
  } else if (rawStatus === 'NON_COMPLIANT') {
    canonicalStatus = 'NON_COMPLIANT';
    bannerModifier = 'non-compliant';
  } else {
    canonicalStatus = 'REVIEW_REQUIRED';
    bannerModifier = 'review';
  }

  // 3. Collect Review / Failure Reasons Dynamically
  const reviewRules = imageRules.filter(
    (r) =>
      r.status === 'NOT_VERIFIABLE' ||
      r.status === 'MANUAL_CHECK' ||
      r.status === 'REVIEW' ||
      r.status === 'NEEDS_REVIEW'
  );

  const failRules = imageRules.filter((r) => r.status === 'FAIL');

  // Helper to format parameter labels cleanly without legal conclusions
  const formatParamLabel = (param) => {
    if (!param) return 'Declaration';
    const names = {
      PRODUCT_NAME: 'Product Name',
      BRAND: 'Brand Name',
      GENERIC_NAME: 'Generic Name',
      DECLARED_NET_QUANTITY: 'Declared Net Quantity',
      NET_QUANTITY: 'Declared Net Quantity',
      MANUFACTURER_NAME: 'Manufacturer Name',
      MANUFACTURER_ADDRESS: 'Manufacturer Address',
      MARKETER_NAME: 'Marketer Name',
      MARKETER_ADDRESS: 'Marketer Address',
      CONSUMER_CARE: 'Consumer Care',
      MONTH_YEAR_MANUFACTURE: 'Date of Manufacture',
      BARCODE: 'Commodity Barcode',
      MRP: 'MRP',
    };
    if (names[param.toUpperCase()]) return names[param.toUpperCase()];
    return param
      .replace(/_/g, ' ')
      .toLowerCase()
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  // 4. Concise Dynamic Explanation
  const getExplanationContent = () => {
    if (canonicalStatus === 'NON_COMPLIANT') {
      return {
        secondary: `${failRules.length} declaration${failRules.length === 1 ? '' : 's'} failed validation`,
        main: 'Screening identified declarations that did not satisfy validation rules.',
        reasons: failRules.map((r) => r.reason || r.message || r.parameter?.replace(/_/g, ' ')).filter(Boolean),
      };
    }

    if (canonicalStatus === 'REVIEW_REQUIRED') {
      return {
        secondary: `${reviewCount} image-based check${reviewCount === 1 ? '' : 's'} require review`,
        main: `${passCount} checks passed. ${failCount} confirmed failures. ${reviewCount} applicable image-based checks require review.`,
        reasons: reviewRules
          .map((r) => r.reason || r.message || `${formatParamLabel(r.parameter)} is not verifiable`)
          .filter(Boolean),
      };
    }

    return {
      secondary: 'All screening criteria satisfied',
      main: 'All verified declarations satisfy applicable screening rules.',
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
  const packageType = inspection.package_type || inspection.product?.package_type || 'NOT_DETECTED';
  const importStatus = inspection.import_status || inspection.product?.import_status || 'NOT_DETECTED';

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

  // Compact review reasons list derived dynamically from backend findings
  const compactReviewReasons = React.useMemo(() => {
    if (canonicalStatus !== 'REVIEW_REQUIRED') return [];
    const list = [];
    if (isProductNameConflict) {
      list.push('Conflicting information');
    }
    const hasGenericMissing = reviewRules.some(
      (r) =>
        r.parameter === 'GENERIC_NAME' ||
        (r.reason || '').toLowerCase().includes('generic name')
    );
    if (hasGenericMissing) {
      list.push('Generic name not detected');
    }
    // Additional specific parameters that need review
    reviewRules.forEach((r) => {
      const p = r.parameter;
      if (p === 'PRODUCT_NAME' && isProductNameConflict) return;
      if (p === 'GENERIC_NAME' && hasGenericMissing) return;
      const label = formatParamLabel(p);
      const entry = `${label} requires review`;
      if (!list.includes(entry) && list.length < 5) {
        list.push(entry);
      }
    });
    return list;
  }, [canonicalStatus, isProductNameConflict, reviewRules]);

  return (
    <div className="results-hero-container">
      {/* Primary Hero Header */}
      <div className={`results-hero-card results-hero-card--${bannerModifier}`}>
        <div className="results-hero-main">
          {/* Top Identifier Row */}
          <div className="results-hero-id-row">
            <span className="results-hero-title">Automated Label Screening</span>
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
            {inspection.analysis_source && (
              <>
                <span className="results-hero-dot">•</span>
                <span
                  className="badge badge-primary text-2xs font-semibold"
                  title="Evidence extraction & resolution methodology"
                >
                  {inspection.analysis_source}
                </span>
              </>
            )}
          </div>

          {/* Primary Status + Secondary Attention Count + Compact Reasons */}
          <div className="results-hero-status-row">
            <div className="results-hero-status-badge">
              <StatusBadge status={canonicalStatus} size="lg" showBinary={true} />
            </div>
            <div className="results-hero-explanation-block">
              <div className="results-hero-secondary-line flex items-center gap-2 flex-wrap">
                <span className="results-hero-secondary-title font-bold text-sm text-main">
                  {explanation.secondary}
                </span>
                {explanation.reasons.length > 0 && (
                  <button
                    type="button"
                    className="results-hero-details-toggle text-xs font-semibold text-primary inline-flex items-center gap-1"
                    onClick={() => setShowDetails(!showDetails)}
                    aria-expanded={showDetails}
                    title="Toggle detailed rule findings"
                  >
                    <span>{showDetails ? 'Hide details' : 'View details'}</span>
                    <ChevronRight
                      size={12}
                      style={{
                        transform: showDetails ? 'rotate(90deg)' : 'none',
                        transition: 'transform 0.15s ease',
                      }}
                    />
                  </button>
                )}
              </div>

              {/* Compact list of affected reasons */}
              {compactReviewReasons.length > 0 ? (
                <div className="results-hero-compact-reasons flex items-center gap-1.5 flex-wrap mt-1">
                  {compactReviewReasons.map((reason, idx) => (
                    <span key={idx} className="compact-reason-badge">
                      <span className="compact-reason-bullet">•</span>
                      <span>{reason}</span>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="results-hero-explanation text-xs text-secondary mt-0.5 mb-0">
                  {explanation.main}
                </p>
              )}

              {/* Expandable detailed explanations */}
              {showDetails && explanation.reasons.length > 0 && (
                <div className="results-hero-expanded-dossier mt-2">
                  <div className="expanded-dossier-title text-2xs font-bold uppercase tracking-wider text-muted mb-1">
                    Specific Parameter Findings:
                  </div>
                  <ul className="expanded-reasons-list text-xs">
                    {explanation.reasons.map((r, idx) => (
                      <li key={idx} className="expanded-reason-item">
                        {r}
                      </li>
                    ))}
                  </ul>
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
              title={`${reviewCount} declarations were not detected`}
            >
              <AlertTriangle size={13} />
              <span className="count-num font-mono">{reviewCount}</span>
              <span className="count-label">NOT DETECTED</span>
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

        {/* Top-Level Workstation Actions - Recommended Hierarchy: Primary, Secondary, Tertiary */}
        <div className="results-hero-actions" role="group" aria-label="Inspection actions">
          {/* Primary Action: View Inspection Report / Generate Report */}
          <button
            type="button"
            className="btn btn-primary btn-sm action-primary"
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

          {/* Secondary Action: Download PDF */}
          {reportUrl && (
            <a
              href={reportUrl}
              download={`inspection_report_${inspection.id}.pdf`}
              className="btn btn-secondary-action btn-sm action-secondary"
              title="Download generated PDF report dossier"
            >
              <span>Download PDF</span>
            </a>
          )}

          {/* Tertiary Actions: History & New Scan */}
          <div className="tertiary-actions-group">
            <Link
              to="/history"
              className="btn btn-tertiary-action btn-sm"
              title="Return to past inspection history"
            >
              <History size={13} />
              <span>History</span>
            </Link>

            <Link
              to="/scan"
              className="btn btn-tertiary-action btn-sm"
              title="Start screening another package"
            >
              <PlusCircle size={13} />
              <span>New Scan</span>
            </Link>
          </div>
        </div>
      </div>

      {physicalRules.length > 0 && (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-slate-500/10 border-b border-slate-500/20 text-xs text-secondary">
          <MinusCircle size={14} className="shrink-0" />
          <span>
            Physical verification limitations: {physicalRules.length} check{physicalRules.length === 1 ? '' : 's'}
            {' '}({physicalRules.map((r) => r.parameter?.replace(/_/g, ' ')).filter(Boolean).join(', ')})
            {' '}are outside this software-only image screening and do not affect its result.
          </span>
        </div>
      )}

      {/* Image Quality Gate Notice */}
      {inspection.image_quality && inspection.image_quality.overall_quality_status !== 'ACCEPT' && (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-amber-500/10 border-b border-amber-500/20 text-amber-700 dark:text-amber-300 text-xs">
          <AlertTriangle size={14} className="shrink-0 text-amber-500" />
          <span>
            {inspection.image_quality.overall_quality_status === 'RECAPTURE_REQUIRED'
              ? 'Image Quality Alert: Submitted images had critical quality defects (blur, glare, or darkness). Recapture recommended.'
              : inspection.image_quality.rejected_images > 0
              ? `Image Quality Notice: Analysis proceeded with ${inspection.image_quality.accepted_images + inspection.image_quality.warning_images} usable panel(s); ${inspection.image_quality.rejected_images} panel excluded due to quality defects.`
              : 'Image Quality Notice: Minor quality warnings detected (soft focus, lighting, or glare). Verification proceeded.'}
          </span>
        </div>
      )}

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
                  title="View conflicting product options"
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

        {/* Regulatory Snapshot */}
        {inspection.regulatory_snapshot && (
          <div className="summary-item" title={inspection.regulatory_snapshot_label || inspection.regulatory_snapshot}>
            <Layers size={14} className="summary-icon text-indigo-600" />
            <div className="summary-content">
              <span className="summary-label">Regulatory Snapshot</span>
              <span className="summary-val font-mono text-2xs truncate max-w-[180px]">
                {inspection.regulatory_snapshot}
              </span>
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
