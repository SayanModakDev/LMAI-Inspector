import React from 'react';
import { AlertTriangle, Layers } from 'lucide-react';
import './ConflictCard.css';

/**
 * ConflictCard Component
 * Displays explicit candidate comparisons across multiple panels or evidence sources
 */
const ConflictCard = ({
  parameter,
  candidates = [],
  notes,
  className = '',
}) => {
  return (
    <div className={`conflict-card ${className}`} role="region" aria-label={`Conflicting evidence for ${parameter}`}>
      <div className="conflict-card__header">
        <div className="conflict-card__title-box">
          <AlertTriangle size={16} className="conflict-card__icon" />
          <span className="conflict-card__title">
            CONFLICTING EVIDENCE DETECTED: {parameter?.replace(/_/g, ' ')}
          </span>
        </div>
        <span className="status-pill status-pill--review">Requires Review</span>
      </div>

      <p className="conflict-card__description">
        Multiple package views or evidence sources provided contradictory values. The system does not silently guess; manual inspector determination is required.
      </p>

      <div className="conflict-card__grid">
        {candidates.map((cand, idx) => {
          const letter = String.fromCharCode(65 + idx); // A, B, C...
          return (
            <div key={idx} className="conflict-candidate">
              <div className="conflict-candidate__badge">Candidate {letter}</div>
              <div className="conflict-candidate__value font-mono">{cand.value || cand.field_value || '—'}</div>
              <div className="conflict-candidate__meta">
                <div className="conflict-candidate__row">
                  <span className="meta-label">Source:</span>
                  <span className="meta-val">{cand.source || (cand.source_image_index !== undefined ? `Panel ${cand.source_image_index + 1}` : 'OCR')}</span>
                </div>
                {cand.confidence !== undefined && (
                  <div className="conflict-candidate__row">
                    <span className="meta-label">Confidence:</span>
                    <span className="meta-val font-mono">{Math.round((cand.confidence || 0) * 100)}%</span>
                  </div>
                )}
                {cand.bbox && (
                  <div className="conflict-candidate__row">
                    <span className="meta-label">Region:</span>
                    <span className="meta-val font-mono">BBox Coordinates Provided</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {notes && (
        <div className="conflict-card__footer">
          <span className="meta-label">Review Guidance:</span> {notes}
        </div>
      )}
    </div>
  );
};

export default ConflictCard;
