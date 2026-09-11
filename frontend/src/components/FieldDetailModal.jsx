import React, { useEffect, useState } from 'react';
import {
  X,
  FileText,
  Image,
  Crosshair,
  Shield,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Code2,
} from 'lucide-react';
import StatusBadge from './StatusBadge';
import ConfidenceBadge from './ConfidenceBadge';
import './FieldDetailModal.css';

/**
 * FieldDetailModal Component
 * Deep inspection modal for a selected package declaration:
 * - Canonical / Normalized Value
 * - Raw OCR text
 * - Confidence & Source
 * - Associated Rule ID & Statutory Reason
 * - Collapsible "Evidence details" for technical metadata (BBox, provenance, candidate metadata)
 * - Clear confidence disclaimer
 */
const FieldDetailModal = ({ field, onClose }) => {
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!field) return null;

  const formatParamName = (param) => {
    if (!param) return 'Declaration';
    return param
      .replace(/_/g, ' ')
      .toLowerCase()
      .replace(/\b\w/g, (c) => c.toUpperCase());
  };

  const formatBBoxString = (bbox) => {
    if (!bbox) return null;
    if (Array.isArray(bbox)) {
      if (bbox.length === 4 && typeof bbox[0] === 'number') {
        return `[${bbox.map((v) => (typeof v === 'number' ? v.toFixed(1) : v)).join(', ')}]`;
      }
      if (Array.isArray(bbox[0])) {
        return `Polygon (${bbox.length} vertices): ${bbox.map((pt) => `[${pt.join(',')}]`).join(' ')}`;
      }
      return JSON.stringify(bbox);
    }
    return String(bbox);
  };

  const bboxString = formatBBoxString(field.bbox);
  const rawText = field.raw_text || field.raw_value || field.text_content || field.field_value;
  const isMissing = !field.field_value && !field.raw_value;

  // Additional technical metadata
  const technicalMeta = {
    parameter: field.field_name || field.parameter,
    compliance_status: field.status,
    candidate_classification: field.candidate_classification,
    evidence_state: field.evidence_state,
    semantic_section: field.semantic_section,
    source_context: field.source_context,
    extraction_method: field.extraction_method || field.source || 'OCR Rule Parser',
    source_panel: `Panel ${(field.source_image_index || 0) + 1}`,
    confidence_raw: field.confidence,
    rule_id: field.rule_id,
    role: field.role,
    conflict_reason: field.conflict_reason,
    spatial_bbox: field.bbox,
    is_multipack: field.is_multipack,
    pack_count: field.pack_count,
    unit_quantity: field.unit_quantity || field.unit_net_quantity,
    derived_total: field.derived_total_quantity,
    competing_candidates: field.candidates || field.competing_candidates,
  };

  const cleanedTechnicalMeta = Object.fromEntries(
    Object.entries(technicalMeta).filter(
      ([_, v]) => v !== undefined && v !== null && (!Array.isArray(v) || v.length > 0)
    )
  );

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="field-detail-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="field-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="field-detail-modal__header">
          <div className="flex items-center gap-2">
            <Shield size={18} className="text-teal" />
            <div>
              <h3 id="field-modal-title" className="field-detail-modal__title">
                {formatParamName(field.field_name || field.parameter)}
              </h3>
              <span className="field-detail-modal__key font-mono text-xs text-muted">
                Parameter: {field.field_name || field.parameter || 'UNSPECIFIED'}
              </span>
            </div>
          </div>
          <button
            type="button"
            className="field-detail-modal__close-btn"
            onClick={onClose}
            aria-label="Close field details"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="field-detail-modal__body">
          {/* Status & Confidence Banner */}
          <div className="field-detail-status-row">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted font-semibold uppercase">Compliance Validation:</span>
              <StatusBadge status={field.status || 'REVIEW'} size="sm" showBinary={true} />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted font-semibold uppercase">Detector Confidence:</span>
              <ConfidenceBadge confidence={field.confidence} source={field.source || 'OCR'} />
            </div>
          </div>

          {/* Value Comparison Grid */}
          <div className="field-detail-values-grid">
            <div className="detail-value-box">
              <div className="detail-value-box__label">
                <span>Normalized Declaration</span>
                <span className="badge badge-gray text-2xs">Structured</span>
              </div>
              <div className="detail-value-box__content font-mono">
                {isMissing ? (
                  <span className="text-muted italic">Evidence not detected</span>
                ) : (
                  String(field.field_value || field.value || '—')
                )}
              </div>
            </div>

            <div className="detail-value-box">
              <div className="detail-value-box__label">
                <span>Raw Extracted Text</span>
                <span className="badge badge-gray text-2xs">OCR Capture</span>
              </div>
              <div className="detail-value-box__content font-mono text-secondary">
                {isMissing ? (
                  <span className="text-muted italic">No matching tokens found in scan</span>
                ) : (
                  String(rawText || '—')
                )}
              </div>
            </div>
          </div>

          {/* Primary Metadata Table */}
          <div className="field-detail-meta-table">
            <div className="meta-row">
              <span className="meta-row__label">
                <Image size={13} className="text-muted" /> Source Panel:
              </span>
              <span className="meta-row__value font-medium">
                {field.source_image_name
                  ? `${field.source_image_name} (Panel ${(field.source_image_index || 0) + 1})`
                  : `Panel ${(field.source_image_index || 0) + 1}`}
              </span>
            </div>

            <div className="meta-row">
              <span className="meta-row__label">
                <FileText size={13} className="text-muted" /> Extraction Subsystem:
              </span>
              <span className="meta-row__value font-mono">
                {field.extraction_method || field.source || 'OCR Rule Parser'}
              </span>
            </div>

            {field.rule_id && (
              <div className="meta-row">
                <span className="meta-row__label">
                  <Shield size={13} className="text-muted" /> Associated Rule ID:
                </span>
                <span className="meta-row__value font-mono font-semibold text-primary">
                  {field.rule_id}
                </span>
              </div>
            )}

            {field.role && (
              <div className="meta-row">
                <span className="meta-row__label">
                  <FileText size={13} className="text-muted" /> Declared Role:
                </span>
                <span className="meta-row__value font-mono font-semibold text-teal">
                  {field.role}
                </span>
              </div>
            )}
          </div>

          {/* Statutory Finding Notice */}
          {field.reason && (
            <div className="field-detail-reason-card">
              <div className="field-detail-reason-card__title">
                <AlertTriangle size={14} className="text-warning flex-shrink-0" />
                <span>Statutory Screening Finding</span>
              </div>
              <p className="field-detail-reason-card__text">{field.reason}</p>
            </div>
          )}

          {/* Collapsible Technical Metadata Section (Section 13) */}
          <div className="technical-metadata-section">
            <button
              type="button"
              className="technical-metadata-toggle"
              onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
              aria-expanded={showTechnicalDetails}
            >
              <div className="flex items-center gap-1.5 font-semibold text-xs text-secondary">
                <Code2 size={13} />
                <span>Evidence Technical Details</span>
              </div>
              {showTechnicalDetails ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>

            {showTechnicalDetails && (
              <div className="technical-metadata-body">
                {bboxString && (
                  <div className="meta-row">
                    <span className="meta-row__label">
                      <Crosshair size={13} className="text-muted" /> Spatial BBox:
                    </span>
                    <span className="meta-row__value font-mono text-2xs">
                      {bboxString}
                    </span>
                  </div>
                )}
                <pre className="technical-json-block font-mono text-2xs">
                  {JSON.stringify(cleanedTechnicalMeta, null, 2)}
                </pre>
              </div>
            )}
          </div>

          {/* Legal Metrology Notice (Section 14) */}
          <div className="field-detail-disclaimer">
            <p className="text-2xs text-muted leading-relaxed m-0">
              Confidence reflects the extraction/detection subsystem; it is not a legal compliance probability.
            </p>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="field-detail-modal__footer">
          <button type="button" className="btn btn-outline btn-sm" onClick={onClose}>
            Close Inspector Details
          </button>
        </div>
      </div>
    </div>
  );
};

export default FieldDetailModal;
