import React, { useEffect, useState } from 'react';
import {
  Scale,
  Search,
  Filter,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  ShieldCheck,
  AlertCircle,
  Clock,
  Layers,
} from 'lucide-react';
import { apiService } from '../services/api';
import './RuleMatrix.css';

const RuleMatrix = () => {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [applicabilityFilter, setApplicabilityFilter] = useState('ALL');
  const [expandedRuleIds, setExpandedRuleIds] = useState(new Set());

  useEffect(() => {
    fetchRules();
  }, []);

  const fetchRules = async () => {
    try {
      setLoading(true);
      const data = await apiService.getRules();
      setRules(data || []);
    } catch (err) {
      console.error('Failed to load rules:', err);
    } finally {
      setLoading(false);
    }
  };

  const toggleExpand = (id) => {
    setExpandedRuleIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const filteredRules = rules.filter((rule) => {
    if (categoryFilter !== 'ALL' && rule.category !== categoryFilter && rule.category !== 'ALL') {
      return false;
    }
    if (applicabilityFilter !== 'ALL' && rule.package_type !== applicabilityFilter && rule.package_type !== 'ALL') {
      return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchId = (rule.rule_id || '').toLowerCase().includes(q);
      const matchParam = (rule.parameter || '').toLowerCase().includes(q);
      const matchRef = (rule.rule_reference || '').toLowerCase().includes(q);
      const matchExtract = (rule.what_to_extract || '').toLowerCase().includes(q);
      if (!matchId && !matchParam && !matchRef && !matchExtract) return false;
    }
    return true;
  });

  return (
    <div className="rule-matrix-page">
      {/* Header */}
      <div className="rule-matrix-header">
        <div>
          <h2 className="rule-matrix-title">Legal Metrology Rule Matrix</h2>
          <p className="rule-matrix-subtitle">
            Configured compliance rule parameters used for deterministic inspection screening under the Legal Metrology (Packaged Commodities) Rules, 2011.
          </p>
        </div>
        <div className="badge badge-primary font-mono font-semibold">
          {rules.length} Screening Rules Configured
        </div>
      </div>

      {/* Filter & Search Controls */}
      <div className="card rule-matrix-filter-card">
        <div className="rule-matrix-filter-body">
          <div className="rule-search-box">
            <Search size={15} className="search-icon" />
            <input
              type="text"
              placeholder="Search by Rule ID (e.g. PC-ALL-001), parameter, or legal reference..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="rule-search-input"
            />
          </div>

          <div className="rule-filter-selectors">
            <div className="filter-select-group">
              <label className="text-xs text-muted font-medium">Category:</label>
              <select
                className="form-control form-control-sm"
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
              >
                <option value="ALL">All Categories</option>
                <option value="FOOD">Food Commodities</option>
                <option value="COSMETIC">Cosmetics</option>
              </select>
            </div>

            <div className="filter-select-group">
              <label className="text-xs text-muted font-medium">Package Type:</label>
              <select
                className="form-control form-control-sm"
                value={applicabilityFilter}
                onChange={(e) => setApplicabilityFilter(e.target.value)}
              >
                <option value="ALL">All Applicabilities</option>
                <option value="RETAIL">Retail Packages</option>
                <option value="WHOLESALE">Wholesale Packages</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Rule Matrix Table */}
      <div className="card">
        <div className="card-header flex-between">
          <span>Configured Rule Standards</span>
          <span className="badge badge-gray">{filteredRules.length} matching criteria</span>
        </div>

        <div className="card-body p-0">
          {loading ? (
            <div className="p-8 text-center text-muted">Loading rule matrix database...</div>
          ) : (
            <div className="table-wrapper">
              <table className="rule-table">
                <thead>
                  <tr>
                    <th style={{ width: '40px' }} />
                    <th>Rule ID</th>
                    <th>Parameter</th>
                    <th>Category</th>
                    <th>Package Applicability</th>
                    <th>Validation Method</th>
                    <th>Reference Status</th>
                    <th>Source Document</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRules.map((rule) => {
                    const isExpanded = expandedRuleIds.has(rule.rule_id);
                    const isPending =
                      rule.rule_reference_status === 'PENDING_VERIFICATION' ||
                      !rule.rule_reference_status;

                    return (
                      <React.Fragment key={rule.rule_id}>
                        <tr
                          className={`rule-row ${isExpanded ? 'rule-row--expanded' : ''}`}
                          onClick={() => toggleExpand(rule.rule_id)}
                        >
                          <td className="text-center">
                            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          </td>
                          <td className="font-mono font-bold text-xs rule-id-cell">
                            {rule.rule_id}
                          </td>
                          <td>
                            <div className="font-semibold text-main">
                              {rule.parameter?.replace(/_/g, ' ')}
                            </div>
                            <div className="text-xs text-muted">{rule.regulatory_source || 'LEGAL_METROLOGY'}</div>
                          </td>
                          <td>
                            <span className="badge badge-gray">{rule.category || 'ALL'}</span>
                          </td>
                          <td>
                            <span className="badge badge-primary">{rule.package_type || 'ALL'}</span>
                          </td>
                          <td>
                            <span className="font-mono text-xs text-secondary">
                              {rule.validation_method || 'PRESENCE_CHECK'}
                            </span>
                          </td>
                          <td>
                            {isPending ? (
                              <span className="badge badge-warning" title="Statutory reference pending formal gazette sync">
                                <Clock size={11} className="mr-1" /> Pending Verification
                              </span>
                            ) : rule.rule_reference_status === 'NON_STATUTORY' ? (
                              <span className="badge badge-gray" title="Internal inspection screening specification; non-statutory">
                                Non-Statutory
                              </span>
                            ) : (
                              <span className="badge badge-success">
                                <ShieldCheck size={11} className="mr-1" /> Verified
                              </span>
                            )}
                          </td>
                          <td className="text-xs text-muted">
                            {rule.source_document || 'LMPC Rules, 2011'}
                          </td>
                        </tr>

                        {isExpanded && (
                          <tr className="rule-expanded-row">
                            <td colSpan="8">
                              <div className="rule-detail-card">
                                <div className="rule-detail-grid">
                                  <div>
                                    <span className="detail-tag">Mandatory Declaration Requirement:</span>
                                    <p className="detail-text">{rule.what_to_extract || 'Verify printed mandatory declaration on package.'}</p>
                                  </div>
                                  <div>
                                    <span className="detail-tag">
                                      {rule.rule_reference_status === 'NON_STATUTORY' ? 'Internal Specification:' : 'Legal Reference Clause:'}
                                    </span>
                                    <p className="detail-text font-semibold">{rule.rule_reference || 'Rule 6 of LMPC Rules, 2011'}</p>
                                  </div>
                                  <div>
                                    <span className="detail-tag">Condition & Applicability:</span>
                                    <p className="detail-text font-mono text-xs">{rule.applicability || rule.condition || 'Universal Package Applicability'}</p>
                                  </div>
                                  <div>
                                    <span className="detail-tag">Rule Severity:</span>
                                    <span className={`badge ${rule.severity === 'MANDATORY' || rule.severity === 'HIGH' ? 'badge-danger' : 'badge-warning'}`}>
                                      {rule.severity || 'MANDATORY'}
                                    </span>
                                  </div>
                                </div>
                                {rule.citation_text && (
                                  <div className="mt-3 pt-2 text-xs text-secondary">
                                    <span className="font-semibold text-muted">Statutory Text / Citation: </span>
                                    <span className="italic">"{rule.citation_text}"</span>
                                  </div>
                                )}
                                {rule.source_url && (
                                  <div className="mt-2">
                                    <a
                                      href={rule.source_url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-xs text-primary flex items-center gap-1 hover:underline"
                                      onClick={(e) => e.stopPropagation()}
                                    >
                                      <ExternalLink size={12} /> Official Authority Reference / Gazette
                                    </a>
                                  </div>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}

                  {filteredRules.length === 0 && (
                    <tr>
                      <td colSpan="8" className="p-4 text-center text-muted">
                        No rules found matching query.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default RuleMatrix;
