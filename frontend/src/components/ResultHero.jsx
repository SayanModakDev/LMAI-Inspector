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
} from 'lucide-react';
import StatusBadge from './StatusBadge';
import { formatISTDateTime } from '../utils/dateUtils';
import './ResultHero.css';

/**
 * ResultHero Component
 * Prominent inspection result header with dynamic counts, IST timestamps,
 * overall compliance status, and result summary bar.
 */
const ResultHero = ({
  inspection,
  ruleResults = [],
  reportUrl = null,
  generatingReport = false,
  onGenerateReport,
}) => {
  if (!inspection) return null;

  // Derive real dynamic counts from backend rule_results
  const passCount = ruleResults.filter((r) => r.status === 'PASS').length;
  const failCount = ruleResults.filter((r) => r.status === 'FAIL').length;
  const reviewCount = ruleResults.filter(
    (r) => r.status === 'NOT_VERIFIABLE' || r.status === 'MANUAL_CHECK'
  ).length;
  const naCount = ruleResults.filter((r) => r.status === 'NOT_APPLICABLE').length;

  // Canonical overall status normalization (strictly adhering to allowed 3 statuses)
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

  // Derive concise explanation from backend reason data
  const getConciseExplanation = () => {
    if (canonicalStatus === 'NON-COMPLIANT') {
      const firstFail = ruleResults.find((r) => r.status === 'FAIL');
      if (firstFail?.reason || firstFail?.message) {
        return `Non-compliance identified: ${firstFail.reason || firstFail.message}`;
      }
      if (inspection.findings?.failed?.length > 0) {
        return `Non-compliance identified: ${inspection.findings.failed[0]}`;
      }
      return 'Mandatory statutory declaration requirements were not satisfied.';
    }

    if (canonicalStatus === 'REQUIRES REVIEW') {
      // Check for conflict
      const hasConflict = (inspection.extracted_fields || []).some(
        (f) => String(f.field_value).startsWith('CONFLICT:') || f.source === 'MULTI_IMAGE_CONFLICT'
      );
      if (hasConflict) {
        return 'Conflicting declarations detected across package views. Physical/manual review required.';
      }
      // Check for physical verification rules
      const physicalRule = ruleResults.find(
        (r) =>
          (r.parameter === 'ACTUAL_NET_CONTENT' || r.parameter === 'FONT_SIZE_COMPLIANCE') &&
          r.status === 'NOT_VERIFIABLE'
      );
      if (physicalRule?.reason) {
        return physicalRule.reason;
      }
      if (inspection.findings?.needs_review?.length > 0) {
        return inspection.findings.needs_review[0];
      }
      return 'One or more declarations could not be conclusively verified.';
    }

    // COMPLIANT
    return 'All statutory declarations satisfy mandatory Legal Metrology requirements.';
  };

  const conciseExplanation = getConciseExplanation();

  // Summary fields detection (only display fields that exist in backend response)
  const productIdentity =
    inspection.product_name ||
    inspection.brand ||
    inspection.product?.product_name ||
    inspection.product?.brand ||
    null;

  const packageClassification = [inspection.package_type, inspection.category]
    .filter(Boolean)
    .join(' • ');

  const importStatus = inspection.import_status || inspection.product?.country_of_origin || null;

  const imageCount = Array.isArray(inspection.images) && inspection.images.length > 0
    ? inspection.images.length
    : (inspection.image_path ? 1 : null);

  // OCR subsystem availability
  const ocrData = inspection.ocr_result?.ocr_data;
  const ocrItemsCount = Array.isArray(ocrData?.ocr_items) ? ocrData.ocr_items.length : null;
  const ocrEngine = inspection.ocr_result?.ocr_engine || (inspection.ocr_result ? 'PaddleOCR' : null);

  // Barcode subsystem availability
  const barcodeResult = ocrData?.barcode_result;
  const barcodeValue = barcodeResult?.value || null;
  const barcodeDecoder = barcodeResult?.source || (barcodeValue ? 'Detected' : null);

  return (
    <div className="results-hero-container">
      {/* Primary Hero Header */}
      <div className={`results-hero-card results-hero-card--${bannerModifier}`}>
        <div className="results-hero-main">
          <div className="results-hero-id-row">
            <span className="results-hero-title">Inspection Result</span>
            <span className="results-hero-id font-mono">#{inspection.id}</span>
            <span className="results-hero-dot">•</span>
            <span className="results-hero-timestamp">
              {formatISTDateTime(inspection.created_at || inspection.inspection_date)}
            </span>
          </div>

          <div className="results-hero-status-row">
            <div className="results-hero-status-badge">
              <StatusBadge status={canonicalStatus} size="lg" showBinary={true} />
            </div>
            <p className="results-hero-explanation">{conciseExplanation}</p>
          </div>

          {/* Real Backend Counts Row */}
          <div className="results-hero-counts">
            <div className={`count-pill count-pill--pass ${passCount > 0 ? 'count-pill--active' : ''}`}>
              <CheckCircle2 size={13} />
              <span className="count-num font-mono">{passCount}</span>
              <span className="count-label">Passed</span>
            </div>

            <div className={`count-pill count-pill--fail ${failCount > 0 ? 'count-pill--active' : ''}`}>
              <XCircle size={13} />
              <span className="count-num font-mono">{failCount}</span>
              <span className="count-label">Failed</span>
            </div>

            <div className={`count-pill count-pill--review ${reviewCount > 0 ? 'count-pill--active' : ''}`}>
              <AlertTriangle size={13} />
              <span className="count-num font-mono">{reviewCount}</span>
              <span className="count-label">Review Required</span>
            </div>

            <div className="count-pill count-pill--na">
              <MinusCircle size={13} />
              <span className="count-num font-mono">{naCount}</span>
              <span className="count-label">Not Applicable</span>
            </div>
          </div>
        </div>

        {/* Workstation Top-Level Actions */}
        <div className="results-hero-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={onGenerateReport}
            disabled={generatingReport}
            title="Compile or view official Legal Metrology inspection PDF report"
          >
            <Printer size={15} />
            <span>
              {generatingReport
                ? 'Compiling Report...'
                : reportUrl
                ? 'View Inspection PDF'
                : 'Generate Report'}
            </span>
          </button>

          <Link to="/history" className="btn btn-outline" title="Return to past inspection records">
            <History size={15} />
            <span>History</span>
          </Link>

          <Link to="/scan" className="btn btn-outline" title="Start screening another package">
            <PlusCircle size={15} />
            <span>New Scan</span>
          </Link>
        </div>
      </div>

      {/* Result Summary Bar (Displays only fields present in backend response) */}
      <div className="result-summary-bar">
        {productIdentity && (
          <div className="summary-item">
            <Package size={14} className="summary-icon text-primary" />
            <div className="summary-content">
              <span className="summary-label">Product Identity</span>
              <span className="summary-val font-semibold">{productIdentity}</span>
            </div>
          </div>
        )}

        {packageClassification && (
          <div className="summary-item">
            <Layers size={14} className="summary-icon text-secondary" />
            <div className="summary-content">
              <span className="summary-label">Classification</span>
              <span className="summary-val">{packageClassification}</span>
            </div>
          </div>
        )}

        {importStatus && (
          <div className="summary-item">
            <Globe size={14} className="summary-icon text-secondary" />
            <div className="summary-content">
              <span className="summary-label">Origin Status</span>
              <span className="summary-val">{importStatus}</span>
            </div>
          </div>
        )}

        {imageCount !== null && (
          <div className="summary-item">
            <FileCheck size={14} className="summary-icon text-teal" />
            <div className="summary-content">
              <span className="summary-label">Package Images</span>
              <span className="summary-val font-mono">
                {imageCount} {imageCount === 1 ? 'Panel' : 'Panels'}
              </span>
            </div>
          </div>
        )}

        <div className="summary-item">
          <Cpu size={14} className="summary-icon text-primary" />
          <div className="summary-content">
            <span className="summary-label">OCR Availability</span>
            <span className="summary-val font-mono">
              {ocrEngine ? (
                ocrItemsCount !== null && ocrItemsCount > 0 ? (
                  `${ocrEngine} (${ocrItemsCount} boxes)`
                ) : (
                  `${ocrEngine} (Active)`
                )
              ) : (
                'Unavailable'
              )}
            </span>
          </div>
        </div>

        <div className="summary-item">
          <Barcode size={14} className="summary-icon text-secondary" />
          <div className="summary-content">
            <span className="summary-label">Barcode Status</span>
            <span className="summary-val font-mono">
              {barcodeValue ? (
                <span className="text-teal font-semibold">
                  {barcodeValue} {barcodeDecoder ? `(${barcodeDecoder})` : ''}
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
