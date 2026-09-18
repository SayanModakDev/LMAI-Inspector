import React from 'react';
import './ConfidenceBadge.css';

/**
 * Responsible ConfidenceBadge Component
 * Communicates machine-detection confidence while clarifying that OCR confidence
 * does not imply legal certification.
 */
const ConfidenceBadge = ({ confidence, source = 'OCR', className = '' }) => {
  if (confidence === null || confidence === undefined) {
    return (
      <span className={`confidence-badge confidence-badge--unknown ${className}`} title="Detection confidence unavailable">
        <span className="confidence-badge__score">Score: —</span>
      </span>
    );
  }

  const scorePct = Math.round(confidence * 100);
  let tier = 'low';
  if (scorePct >= 80) tier = 'high';
  else if (scorePct >= 50) tier = 'medium';

  return (
    <span
      className={`confidence-badge confidence-badge--${tier} ${className}`}
      title={`${source} detector confidence: ${scorePct}%. (Technical scoring only — does not establish statutory certainty)`}
    >
      <span className="confidence-badge__source">{source}</span>
      <span className="confidence-badge__score font-mono">{scorePct}%</span>
    </span>
  );
};

export default ConfidenceBadge;
