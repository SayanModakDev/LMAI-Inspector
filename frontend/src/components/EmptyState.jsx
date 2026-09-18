import React from 'react';
import { Link } from 'react-router-dom';
import { PackageSearch } from 'lucide-react';
import './EmptyState.css';

/**
 * Contextual EmptyState Component
 */
const EmptyState = ({
  icon: Icon = PackageSearch,
  title = 'No records found',
  description = 'No inspection records match the current criteria.',
  actionLabel = 'New Inspection',
  actionTo = '/scan',
  onAction,
  className = '',
}) => {
  return (
    <div className={`empty-state ${className}`}>
      <div className="empty-state__icon-wrapper">
        <Icon size={32} strokeWidth={1.5} className="empty-state__icon" />
      </div>
      <h3 className="empty-state__title">{title}</h3>
      <p className="empty-state__description">{description}</p>
      {(actionTo || onAction) && (
        <div className="empty-state__action">
          {actionTo ? (
            <Link to={actionTo} className="btn btn-primary">
              {actionLabel}
            </Link>
          ) : (
            <button type="button" className="btn btn-primary" onClick={onAction}>
              {actionLabel}
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default EmptyState;
