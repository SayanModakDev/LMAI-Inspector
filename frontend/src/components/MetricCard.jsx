import React from 'react';
import './MetricCard.css';

/**
 * MetricCard component for operational statistics
 * @param {string} label - Title of the metric
 * @param {number|string} value - Numerical or string value
 * @param {string} status - 'neutral' | 'pass' | 'fail' | 'review' | 'primary'
 * @param {React.ReactNode} icon - Lucide icon
 * @param {string} subtitle - Optional descriptive secondary text
 */
const MetricCard = ({ label, value, status = 'neutral', icon, subtitle, className = '' }) => {
  return (
    <div className={`metric-card metric-card--${status} ${className}`}>
      <div className="metric-card__header">
        <span className="metric-card__label">{label}</span>
        {icon && <div className="metric-card__icon">{icon}</div>}
      </div>
      <div className="metric-card__value font-mono">{value ?? 0}</div>
      {subtitle && <div className="metric-card__subtitle">{subtitle}</div>}
    </div>
  );
};

export default MetricCard;
