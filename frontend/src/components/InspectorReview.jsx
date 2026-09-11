import React, { useState, useCallback } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  ClipboardCheck,
  Eye,
  ChevronDown,
  ChevronRight,
  Info,
  Zap,
  BookmarkCheck,
} from 'lucide-react';
import ConfidenceBadge from './ConfidenceBadge';
import StatusBadge from './StatusBadge';
import './InspectorReview.css';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Parameters that belong exclusively to Physical Verification, never shown here. */
const PHYSICAL_ONLY_PARAMS = new Set([
  'ACTUAL_NET_CONTENT',
  'FONT_SIZE_COMPLIANCE',
  'PHYSICAL_NET_CONTENT',
  'NET_CONTENT_MEASUREMENT',
]);

/** Rule statuses that require inspector attention. */
const REVIEW_STATUSES = new Set([
  'NOT_VERIFIABLE',
  'REVIEW',
  'NEEDS_REVIEW',
  'MANUAL_CHECK',
]);

// ---------------------------------------------------------------------------
// User-facing review language (Part B)
// Plain inspector language; technical details available in the expanded dossier.
// ---------------------------------------------------------------------------
const EVIDENCE_STATE_MESSAGES = {
  EVIDENCE_CONFLICTING: 'Conflicting information — review required.',
  EVIDENCE_NOT_DETECTED: 'Not detected.',
  EVIDENCE_LOW_CONFIDENCE: 'Low confidence — review required.',
  EVIDENCE_DETECTED_UNASSOCIATED: 'Detected, not linked.',
  PHYSICAL_VERIFICATION_REQUIRED: 'Physical verification required.',
};

function getReviewMessage(item) {
  const evState = (item.evidence_state || '').toUpperCase();
  if (evState && EVIDENCE_STATE_MESSAGES[evState]) {
    return EVIDENCE_STATE_MESSAGES[evState];
  }
  if (item.has_conflict || item.candidate_classification === 'TRUE_CONFLICT') {
    return 'Conflicting information — review required.';
  }
  const candidates = item.candidates || [];
  if (candidates.length > 1) {
    return 'Different values detected — select the verified value.';
  }
  if (!item.extracted_value) {
    return 'Not detected.';
  }
  return 'Review required.';
}

function getReferenceHint(param, refProd) {
  if (!refProd) return null;
  const p = (param || '').toUpperCase();
  if (p === 'PRODUCT_NAME' && refProd.product_name) return `Reference product: ${refProd.product_name}`;
  if (p === 'BRAND' && refProd.brand) return `Reference brand: ${refProd.brand}`;
  if (p === 'GENERIC_NAME' && refProd.generic_name) return `Reference generic name: ${refProd.generic_name}`;
  if (p === 'DECLARED_NET_QUANTITY' && refProd.declared_net_quantity) return `Reference standard quantity: ${refProd.declared_net_quantity}`;
  if (p === 'MANUFACTURER_NAME' && refProd.manufacturer_name) return `Reference manufacturer: ${refProd.manufacturer_name}`;
  if (p === 'MRP' && refProd.standard_mrp) return `Reference typical MRP: ₹${refProd.standard_mrp}`;
  return null;
}

// ---------------------------------------------------------------------------
// ProductReferenceCard — Suggestion card for known products
// ---------------------------------------------------------------------------
function ProductReferenceCard({ registryMatch, onUseAsReference, onIgnore, isReferenceActive }) {
  if (!registryMatch || !registryMatch.matched || !registryMatch.reference_product) {
    return null;
  }
  const ref = registryMatch.reference_product;
  const confPct = registryMatch.confidence_percent || Math.round((registryMatch.confidence || 0) * 100);

  return (
    <div className={`reference-product-card ${isReferenceActive ? 'reference-product-card--active' : ''}`}>
      <div className="reference-card-header">
        <div className="reference-title-block">
          <BookmarkCheck size={18} className="text-emerald-600 flex-shrink-0" />
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="reference-main-title font-bold text-sm text-emerald-950">
                Known product match
              </span>
              <span className="badge badge-success font-mono text-2xs font-semibold">
                Match confidence: {confPct}%
              </span>
            </div>
            <p className="reference-matched-by text-xs text-emerald-800 mt-0.5 mb-0">
              <strong>Matched by:</strong> {registryMatch.matched_by}
            </p>
          </div>
        </div>

        <div className="reference-actions flex items-center gap-2">
          {!isReferenceActive ? (
            <button
              type="button"
              className="btn btn-sm btn-outline-success"
              onClick={onUseAsReference}
              title="Use reference product data as supporting context for review"
            >
              Use as reference
            </button>
          ) : (
            <span className="badge badge-success text-2xs py-1 px-2 flex items-center gap-1">
              <CheckCircle2 size={11} /> Reference active
            </span>
          )}
          <button
            type="button"
            className="btn btn-sm btn-ghost text-muted"
            onClick={onIgnore}
            title="Dismiss reference suggestion"
          >
            Ignore
          </button>
        </div>
      </div>

      <div className="reference-details-grid mt-2">
        <div>
          <span className="reference-field-label text-2xs text-emerald-800">Product:</span>
          <span className="reference-field-value text-xs font-semibold text-emerald-950 ml-1">{ref.product_name}</span>
        </div>
        {ref.brand && (
          <div>
            <span className="reference-field-label text-2xs text-emerald-800">Brand:</span>
            <span className="reference-field-value text-xs text-emerald-950 ml-1">{ref.brand}</span>
          </div>
        )}
        {ref.generic_name && (
          <div>
            <span className="reference-field-label text-2xs text-emerald-800">Generic Name:</span>
            <span className="reference-field-value text-xs text-emerald-950 ml-1">{ref.generic_name}</span>
          </div>
        )}
        {ref.declared_net_quantity && (
          <div>
            <span className="reference-field-label text-2xs text-emerald-800">Standard Qty:</span>
            <span className="reference-field-value text-xs font-mono text-emerald-950 ml-1">{ref.declared_net_quantity}</span>
          </div>
        )}
        {ref.manufacturer_name && (
          <div className="col-span-full">
            <span className="reference-field-label text-2xs text-emerald-800">Manufacturer:</span>
            <span className="reference-field-value text-xs text-emerald-950 ml-1">{ref.manufacturer_name}</span>
          </div>
        )}
      </div>

      <div className="reference-disclaimer mt-2 pt-1 border-t border-emerald-200 flex items-center gap-1.5 text-2xs text-emerald-700">
        <Info size={11} className="flex-shrink-0" />
        <span>Supporting evidence only. Does not declare legal compliance or replace physical inspection.</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CandidateOption — single selectable candidate card
// ---------------------------------------------------------------------------
function CandidateOption({ candidate, paramKey, isSelected, onSelect }) {
  const value = candidate.value ?? candidate.raw_text ?? candidate.normalized_text ?? String(candidate);
  const conf = candidate.ocr_confidence ?? candidate.confidence ?? null;
  const src = candidate.source_image ?? candidate.source_type ?? candidate.source ?? '';
  const imgIdx = candidate.source_image_index ?? candidate.source_image_id ?? null;
  const isRefMatch = Boolean(candidate.is_reference_match);
  const candId = `cand_${paramKey}__${value}__${src}`;

  return (
    <label
      htmlFor={candId}
      className={`candidate-option ${isSelected ? 'candidate-option--selected' : ''} ${isRefMatch ? 'candidate-option--ref-match' : ''}`}
    >
      <input
        id={candId}
        type="radio"
        name={`review_${paramKey}`}
        value={value}
        checked={isSelected}
        onChange={() => onSelect(value)}
        className="candidate-radio"
      />
      <span className="candidate-value font-mono">
        {value || <em className="text-muted">—</em>}
      </span>
      {isRefMatch && (
        <span className="badge badge-success font-mono text-2xs" style={{ fontSize: '10px', padding: '1px 5px' }}>
          Reference match
        </span>
      )}
      {conf !== null && <ConfidenceBadge confidence={conf} size="xs" />}
      {(src || imgIdx !== null) && (
        <span className="candidate-source text-muted text-2xs">
          {src === 'MULTI_IMAGE_CONFLICT' ? 'Different values across images' : src}{imgIdx !== null ? ` · image ${Number(imgIdx) + 1}` : ''}
        </span>
      )}
    </label>
  );
}

// ---------------------------------------------------------------------------
// ReviewItemCard — one review card per flagged parameter
// ---------------------------------------------------------------------------
function ReviewItemCard({ item, verifiedValues, onVerify, onClear, isReferenceActive, referenceProduct }) {
  const param = item.parameter;
  const candidates = item.candidates || [];
  const hasExtracted = Boolean(item.extracted_value);
  const reviewMsg = getReviewMessage(item);
  const refHint = isReferenceActive && referenceProduct ? getReferenceHint(param, referenceProduct) : null;

  const [manualValue, setManualValue] = useState('');
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const isManualMode = selectedCandidate === '__MANUAL__';
  const verifiedEntry = verifiedValues[param];
  const isConflict = item.has_conflict || item.candidate_classification === 'TRUE_CONFLICT';
  const isNotDetected = !hasExtracted && candidates.length === 0;

  // The value that will be submitted
  const effectiveValue = isManualMode
    ? manualValue
    : selectedCandidate !== null && selectedCandidate !== '__MANUAL__'
      ? selectedCandidate
      : candidates.length === 0
        ? manualValue
        : '';

  const canSubmit = effectiveValue.trim().length > 0;

  const handleSelectCandidate = useCallback((val) => {
    setSelectedCandidate(val);
    setManualValue('');
  }, []);

  const handleManualMode = useCallback(() => {
    setSelectedCandidate('__MANUAL__');
  }, []);

  const handleSubmit = useCallback(() => {
    const finalVal = effectiveValue.trim();
    if (!finalVal) return;
    onVerify(param, finalVal);
  }, [effectiveValue, param, onVerify]);

  const handleClear = useCallback(() => {
    setSelectedCandidate(null);
    setManualValue('');
    onClear(param);
  }, [param, onClear]);

  return (
    <div
      className={[
        'review-item-card',
        isConflict ? 'review-item-card--conflict' : '',
        verifiedEntry ? 'review-item-card--verified' : '',
      ].filter(Boolean).join(' ')}
    >
      {/* ── Header ─────────────────────────────────────── */}
      <div className="review-item-header">
        <div className="review-item-identity">
          <span className="review-item-icon">
            {verifiedEntry ? (
              <CheckCircle2 size={16} className="text-success" />
            ) : isConflict ? (
              <AlertTriangle size={16} className="text-danger" />
            ) : isNotDetected ? (
              <HelpCircle size={16} className="text-muted" />
            ) : (
              <AlertTriangle size={16} className="text-warning" />
            )}
          </span>
          <span className="review-item-param-name">
            {param.replace(/_/g, ' ')}
          </span>
          {item.rule_id && (
            <span className="review-item-rule-id font-mono text-2xs text-muted">
              {item.rule_id}
            </span>
          )}
        </div>
        <div className="review-item-header-right">
          {verifiedEntry ? (
            <span className="badge badge-success text-xs">Verified ✓</span>
          ) : (
            <StatusBadge status={item.status} size="xs" />
          )}
          <button
            type="button"
            className="btn-icon-sm"
            onClick={() => setDetailOpen((o) => !o)}
            title="Toggle technical details"
            aria-expanded={detailOpen}
          >
            {detailOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        </div>
      </div>

      {/* ── User-facing message ─────────────────────────── */}
      <p className="review-item-message">{reviewMsg}</p>

      {/* ── Verified chip ───────────────────────────────── */}
      {verifiedEntry && (
        <div className="verified-value-chip">
          <CheckCircle2 size={12} />
          <span className="font-mono text-xs">
            Inspector verified: <strong>{verifiedEntry}</strong>
          </span>
          <button
            type="button"
            className="btn-icon-xs text-muted"
            onClick={handleClear}
            title="Clear verification"
          >
            <XCircle size={12} />
          </button>
        </div>
      )}

      {/* ── Extracted value row ─────────────────────────── */}
      {hasExtracted && !verifiedEntry && (
        <div className="extracted-value-row">
          <span className="dossier-label">Extracted:</span>
          <span className="extracted-value-pill font-mono text-xs">
            {item.extracted_value}
          </span>
          {item.confidence != null && (
            <ConfidenceBadge confidence={item.confidence} size="xs" />
          )}
          {item.source && (
            <span className="text-muted text-2xs">{item.source}</span>
          )}
        </div>
      )}

      {/* ── Candidate / option selection ─────────────────── */}
      {!verifiedEntry && (
        <div className="candidate-selection-area">
          {/* Reference product specification hint if active */}
          {refHint && (
            <div className="reference-field-hint">
              <BookmarkCheck size={12} className="text-emerald-600 flex-shrink-0" />
              <span>{refHint}</span>
            </div>
          )}

          {candidates.length > 0 && (
            <>
              <span className="dossier-label mb-1">Select verified value from detected options:</span>
              <div className="candidate-list">
                {candidates.map((cand, i) => {
                  const candVal =
                    cand.value ?? cand.raw_text ?? cand.normalized_text ?? String(cand);
                  return (
                    <CandidateOption
                      key={i}
                      candidate={cand}
                      paramKey={param}
                      isSelected={selectedCandidate === candVal}
                      onSelect={handleSelectCandidate}
                    />
                  );
                })}
                {/* Manual entry radio */}
                <label
                  htmlFor={`manual_radio_${param}`}
                  className={`candidate-option candidate-option--manual ${isManualMode ? 'candidate-option--selected' : ''
                    }`}
                >
                  <input
                    id={`manual_radio_${param}`}
                    type="radio"
                    name={`review_${param}`}
                    value="__MANUAL__"
                    checked={isManualMode}
                    onChange={handleManualMode}
                    className="candidate-radio"
                  />
                  <span className="text-xs text-secondary">Enter manually:</span>
                  {isManualMode && (
                    <input
                      type="text"
                      className="manual-inline-input font-mono"
                      placeholder={`Verified ${param.replace(/_/g, ' ').toLowerCase()}...`}
                      value={manualValue}
                      onChange={(e) => setManualValue(e.target.value)}
                      autoFocus
                    />
                  )}
                </label>
              </div>
            </>
          )}

          {/* No candidates — manual entry only */}
          {candidates.length === 0 && (
            <div className="manual-only-area">
              <span className="dossier-label">No options detected — enter verified value:</span>
              <input
                type="text"
                className="form-control text-xs font-mono mt-1"
                placeholder={`Verified ${param.replace(/_/g, ' ').toLowerCase()}...`}
                value={manualValue}
                onChange={(e) => setManualValue(e.target.value)}
              />
            </div>
          )}

          {/* Submit button appears once a value is ready */}
          {(canSubmit || (candidates.length === 0 && manualValue.trim())) && (
            <div className="review-item-actions">
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={handleSubmit}
              >
                <ClipboardCheck size={13} /> Mark as Verified
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── Technical dossier (expanded) ───────────────── */}
      {detailOpen && (
        <div className="review-item-technical">
          <div className="technical-grid">
            {item.evidence_state && (
              <div>
                <span className="dossier-label">Evidence State:</span>
                <code className="text-xs">{item.evidence_state}</code>
              </div>
            )}
            {item.candidate_classification && (
              <div>
                <span className="dossier-label">Candidate Classification:</span>
                <code className="text-xs">{item.candidate_classification}</code>
              </div>
            )}
            {item.regulatory_source && (
              <div>
                <span className="dossier-label">Regulatory Source:</span>
                <span className="text-xs">{item.regulatory_source}</span>
              </div>
            )}
            {item.rule_reference && (
              <div>
                <span className="dossier-label">Rule Reference:</span>
                <span className="text-xs">{item.rule_reference}</span>
              </div>
            )}
            <div>
              <span className="dossier-label">Technical Reason:</span>
              <p className="text-xs text-secondary mt-1">{item.reason}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main InspectorReview export
// ---------------------------------------------------------------------------
/**
 * InspectorReview panel.
 *
 * Props:
 *   reviewItems     — structured list from GET /api/inspection/{id}.review_items
 *   ruleResults     — full rule_results array (fallback)
 *   extractedFields — full extracted_fields array (fallback)
 *   onSubmitReview(fieldOverrides, notes) → Promise
 */
export default function InspectorReview({
  reviewItems = [],
  ruleResults = [],
  extractedFields = [],
  registryMatch = null,
  onSubmitReview,
}) {
  const [verifiedValues, setVerifiedValues] = useState({});
  const [inspectorNotes, setInspectorNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [successMsg, setSuccessMsg] = useState(null);
  const [submitError, setSubmitError] = useState(null);
  const [isReferenceActive, setIsReferenceActive] = useState(false);
  const [isReferenceIgnored, setIsReferenceIgnored] = useState(false);

  // Prefer server-built reviewItems; fall back to deriving from ruleResults
  const effectiveItems = React.useMemo(() => {
    if (reviewItems && reviewItems.length > 0) return reviewItems;

    const efByName = {};
    for (const ef of extractedFields) {
      if (ef.field_name) efByName[ef.field_name] = ef;
    }
    return ruleResults
      .filter(
        (r) =>
          REVIEW_STATUSES.has(r.status) && !PHYSICAL_ONLY_PARAMS.has(r.parameter)
      )
      .filter((r) => {
        const evState = r.evidence_state || r.evidence_data?.evidence_state || '';
        const hasCandidates = Boolean(
          r.competing_evidence?.length || r.evidence_data?.candidates?.length
        );
        return !(evState === 'PHYSICAL_VERIFICATION_REQUIRED' && !hasCandidates);
      })
      .map((r) => {
        const ef = efByName[r.parameter] || {};
        const ed = r.evidence_data || {};
        return {
          parameter: r.parameter,
          rule_id: r.rule_id,
          status: r.status,
          evidence_state: r.evidence_state || ed.evidence_state || '',
          reason: r.reason || r.message || '',
          extracted_value: ef.field_value || ed.value || r.raw_value,
          confidence: ef.confidence ?? ed.confidence,
          source: ef.source || ed.source,
          source_image_index: ef.source_image_id,
          candidates: r.competing_evidence || ed.candidates || [],
          candidate_classification: r.candidate_classification || ed.candidate_classification,
          has_conflict: ed.has_conflict || false,
          regulatory_source: r.regulatory_source,
          rule_reference: r.rule_reference,
        };
      });
  }, [reviewItems, ruleResults, extractedFields]);

  const handleVerify = useCallback((param, value) => {
    setVerifiedValues((prev) => ({ ...prev, [param]: value }));
    setSuccessMsg(null);
    setSubmitError(null);
  }, []);

  const handleClear = useCallback((param) => {
    setVerifiedValues((prev) => {
      const next = { ...prev };
      delete next[param];
      return next;
    });
  }, []);

  const verifiedCount = Object.keys(verifiedValues).length;
  const totalReview = effectiveItems.length;

  const handleSubmit = async () => {
    if (verifiedCount === 0) return;
    setSubmitting(true);
    setSuccessMsg(null);
    setSubmitError(null);
    try {
      await onSubmitReview(verifiedValues, inspectorNotes);
      setSuccessMsg(
        `${verifiedCount} field${verifiedCount > 1 ? 's' : ''} verified and rules re-evaluated successfully.`
      );
    } catch (err) {
      setSubmitError(
        err?.response?.data?.detail || err?.message || 'Submission failed. Please try again.'
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (totalReview === 0) {
    return (
      <div className="inspector-review-empty">
        <CheckCircle2 size={36} className="text-success" />
        <h4 className="font-semibold mt-3">No Declaration Review Required</h4>
        <p className="text-secondary text-sm mt-1">
          All image-verifiable declarations have been processed. Any physical-only
          parameters are in the Physical Verification tab.
        </p>
      </div>
    );
  }

  return (
    <div className="inspector-review-panel">
      {/* Panel header */}
      <div className="review-panel-header">
        <div className="review-panel-title-block">
          <Eye size={18} className="text-primary" />
          <div>
            <h3 className="review-panel-title">Inspector Declaration Review</h3>
            <p className="review-panel-subtitle text-muted text-xs">
              {totalReview} item{totalReview !== 1 ? 's' : ''} require review ·{' '}
              {verifiedCount} of {totalReview} verified
            </p>
          </div>
        </div>
        {/* Progress pill */}
        <div className="review-panel-progress-pill" title={`${verifiedCount} / ${totalReview} verified`}>
          <div
            className="review-progress-bar"
            style={{ width: `${totalReview > 0 ? (verifiedCount / totalReview) * 100 : 0}%` }}
          />
          <span className="review-progress-label">
            {totalReview > 0 ? Math.round((verifiedCount / totalReview) * 100) : 0}%
          </span>
        </div>
      </div>

      {/* Known Product Reference Suggestion Card */}
      {!isReferenceIgnored && registryMatch?.matched && (
        <ProductReferenceCard
          registryMatch={registryMatch}
          isReferenceActive={isReferenceActive}
          onUseAsReference={() => setIsReferenceActive(true)}
          onIgnore={() => {
            setIsReferenceActive(false);
            setIsReferenceIgnored(true);
          }}
        />
      )}

      {/* Audit notice */}
      <div className="review-notice-banner">
        <Info size={14} className="flex-shrink-0 text-primary" />
        <p className="text-xs leading-relaxed">
          Select the verified value from detected options, or enter it manually. Original
          OCR evidence is preserved as an audit trail and never overwritten. Submission
          re-runs the deterministic compliance engine — no rule can silently pass without
          a verified value.
        </p>
      </div>

      {/* Status messages */}
      {successMsg && (
        <div className="review-success-banner">
          <CheckCircle2 size={14} />
          <span className="text-xs font-semibold">{successMsg}</span>
        </div>
      )}
      {submitError && (
        <div className="review-error-banner">
          <XCircle size={14} />
          <span className="text-xs">{submitError}</span>
        </div>
      )}

      {/* Review cards */}
      <div className="review-items-list">
        {effectiveItems.map((item) => (
          <ReviewItemCard
            key={item.parameter}
            item={item}
            verifiedValues={verifiedValues}
            onVerify={handleVerify}
            onClear={handleClear}
            isReferenceActive={isReferenceActive}
            referenceProduct={registryMatch?.reference_product}
          />
        ))}
      </div>

      {/* Notes + submit */}
      <div className="review-submit-section">
        <div className="form-group">
          <label className="form-label">
            <span>Inspector Verification Notes</span>
            <span className="text-xs text-muted">Optional — appended to inspection record</span>
          </label>
          <textarea
            rows={2}
            className="form-control text-xs"
            placeholder="Enter any additional findings or verification context..."
            value={inspectorNotes}
            onChange={(e) => setInspectorNotes(e.target.value)}
          />
        </div>

        <div className="review-submit-row">
          <span className="text-xs text-muted">
            {verifiedCount > 0
              ? `${verifiedCount} override${verifiedCount > 1 ? 's' : ''} ready to submit`
              : 'Select or enter at least one verified value to submit'}
          </span>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={handleSubmit}
            disabled={verifiedCount === 0 || submitting}
          >
            <Zap size={14} />
            {submitting
              ? 'Re-evaluating…'
              : `Submit & Re-Evaluate (${verifiedCount})`}
          </button>
        </div>
      </div>
    </div>
  );
}
