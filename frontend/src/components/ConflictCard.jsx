import React from 'react';
import { AlertTriangle, Layers, UserCheck } from 'lucide-react';
import './ConflictCard.css';

/**
 * ConflictCard Component
 * Displays explicit candidate comparisons across multiple panels or evidence sources.
 * Adheres strictly to LMAI Inspector data integrity:
 * Never silently chooses a candidate; explicit "Resolution: Manual Review Required".
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
          <AlertTriangle size={18} className="conflict-card__icon" />
          <span className="conflict-card__title">
            CONFLICTING EVIDENCE: {parameter?.replace(/_/g, ' ')}
          </span>
        </div>
        <span className="status-pill status-pill--review font-mono text-xs">Manual Review Required</span>
      </div>

      <p className="conflict-card__description">
        Multiple package views or evidence sources provided contradictory values. The system does not silently choose a winner or guess; manual inspector determination is required.
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
                  <span className="meta-label">Source panel:</span>
                  <span className="meta-val font-semibold">
                    {cand.source || (cand.source_image_index !== undefined ? `Panel ${cand.source_image_index + 1}` : 'Detection Source')}
                  </span>
                </div>
                {cand.confidence !== undefined && cand.confidence !== null && (
                  <div className="conflict-candidate__row">
                    <span className="meta-label">Confidence:</span>
                    <span className="meta-val font-mono">{Math.round((cand.confidence || 0) * 100)}%</span>
                  </div>
                )}
                {cand.bbox && (
                  <div className="conflict-candidate__row">
                    <span className="meta-label">Region:</span>
                    <span className="meta-val font-mono text-2xs">Spatial coordinates provided</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="conflict-card__resolution-banner">
        <div className="flex items-center gap-2">
          <UserCheck size={16} className="text-warning flex-shrink-0" />
          <div>
            <span className="resolution-label font-semibold">Resolution: </span>
            <span className="resolution-text font-bold text-amber-900">Manual Review Required</span>
            <p className="text-2xs text-muted mb-0 mt-0.5">
              Inspector must verify physical package declaration and record certified override if necessary.
            </p>
          </div>
        </div>
      </div>

      {notes && (
        <div className="conflict-card__footer">
          <span className="meta-label">Finding Guidance:</span> {notes}
        </div>
      )}
    </div>
  );
};

export default ConflictCard;
