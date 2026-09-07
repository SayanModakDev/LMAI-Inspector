import React from 'react';
import { AlertOctagon, RotateCcw, ImagePlus, ArrowRight } from 'lucide-react';
import './ErrorState.css';

/**
 * Actionable ErrorState Component
 */
const ErrorState = ({
  title = 'Analysis could not be completed',
  message,
  reason,
  onRetry,
  onReplaceImage,
  onContinue,
  className = '',
}) => {
  return (
    <div className={`error-state ${className}`} role="alert">
      <div className="error-state__icon-box">
        <AlertOctagon size={28} className="error-state__icon" />
      </div>
      <div className="error-state__body">
        <h4 className="error-state__title">{title}</h4>
        {message && <p className="error-state__message">{message}</p>}
        {reason && (
          <div className="error-state__reason">
            <span className="error-state__reason-label">Diagnostic Detail:</span>
            <span className="error-state__reason-text">{reason}</span>
          </div>
        )}
        <div className="error-state__actions">
          {onRetry && (
            <button type="button" className="btn btn-primary btn-sm" onClick={onRetry}>
              <RotateCcw size={13} /> Try Again
            </button>
          )}
          {onReplaceImage && (
            <button type="button" className="btn btn-outline btn-sm" onClick={onReplaceImage}>
              <ImagePlus size={13} /> Replace Image
            </button>
          )}
          {onContinue && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={onContinue}>
              Continue with Available Evidence <ArrowRight size={13} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default ErrorState;
