import React from 'react';
import { CheckCircle2, XCircle, AlertTriangle, MinusCircle, Loader2 } from 'lucide-react';
import './StatusBadge.css';

/**
 * Standardized StatusBadge for LMAI Inspector
 * Supports canonical statuses:
 * - COMPLIANT / PASS (1)
 * - NON_COMPLIANT / FAIL (0)
 * - NOT_VERIFIABLE / NEEDS_REVIEW / REVIEW / MANUAL_CHECK
 * - NOT_APPLICABLE / NA
 * - PROCESSING
 */
const StatusBadge = ({ status, size = 'md', showBinary = false, className = '' }) => {
  const norm = (status || '').toUpperCase().replace(/-/g, '_').trim();

  let type = 'na';
  let label = status || 'N/A';
  let Icon = MinusCircle;

  if (norm === 'COMPLIANT' || norm === 'PASS') {
    type = 'pass';
    label = showBinary ? '1 — COMPLIANT' : (norm === 'PASS' ? 'PASS' : 'COMPLIANT');
    Icon = CheckCircle2;
  } else if (norm === 'NON_COMPLIANT' || norm === 'FAIL') {
    type = 'fail';
    label = showBinary ? '0 — NON-COMPLIANT' : (norm === 'FAIL' ? 'FAIL' : 'NON-COMPLIANT');
    Icon = XCircle;
  } else if (norm === 'NOT_VERIFIABLE' || norm === 'NEEDS_REVIEW' || norm === 'REVIEW' || norm === 'MANUAL_CHECK') {
    type = 'review';
    label = 'REVIEW REQUIRED';
    Icon = AlertTriangle;
  } else if (norm === 'NOT_APPLICABLE' || norm === 'NA') {
    type = 'na';
    label = 'NOT APPLICABLE';
    Icon = MinusCircle;
  } else if (norm === 'PROCESSING') {
    type = 'processing';
    label = 'PROCESSING';
    Icon = Loader2;
  }

  const iconSizes = { sm: 12, md: 14, lg: 18 };
  const iconSize = iconSizes[size] || 14;

  return (
    <span className={`status-badge status-badge--${type} status-badge--${size} ${className}`} role="status">
      <Icon size={iconSize} className={type === 'processing' ? 'spinner-icon' : ''} aria-hidden="true" />
      <span className="status-badge__label">{label}</span>
    </span>
  );
};

export default StatusBadge;
