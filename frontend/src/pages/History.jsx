import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Search,
  Eye,
  FileText,
  ScanLine,
  Filter,
  Download,
  Calendar,
  Layers,
  ArrowUpDown,
} from 'lucide-react';
import { apiService } from '../services/api';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import './History.css';

const History = () => {
  const [inspections, setInspections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchHistory();
  }, [filter]);

  const fetchHistory = async () => {
    try {
      setLoading(true);
      const statusParam = filter !== 'ALL' ? filter : undefined;
      const data = await apiService.getHistory(0, 100, statusParam);
      setInspections(data || []);
    } catch (err) {
      console.error('Failed to load inspection history:', err);
    } finally {
      setLoading(false);
    }
  };

  const filteredItems = inspections.filter((item) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    const idMatch = String(item.id).includes(q);
    const prodMatch = (item.product_name || '').toLowerCase().includes(q);
    const catMatch = (item.category || '').toLowerCase().includes(q);
    const dateMatch = item.created_at ? new Date(item.created_at).toLocaleDateString().includes(q) : false;
    return idMatch || prodMatch || catMatch || dateMatch;
  });

  return (
    <div className="history-page">
      {/* Header & Controls */}
      <div className="history-header">
        <div>
          <h2 className="history-title">Inspection History Registry</h2>
          <p className="history-subtitle">
            Search, audit, and retrieve past packaged commodity compliance dossiers and generated statutory reports.
          </p>
        </div>
        <Link to="/scan" className="btn btn-primary">
          <ScanLine size={15} /> New Inspection
        </Link>
      </div>

      {/* Filter & Search Bar Card */}
      <div className="card history-filter-card">
        <div className="history-filter-body">
          <div className="history-search-box">
            <Search size={15} className="search-icon" />
            <input
              type="text"
              placeholder="Search by Dossier ID, Product Name, Category or Date..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="history-search-input"
            />
          </div>

          <div className="history-filter-tabs">
            {[
              { key: 'ALL', label: 'All Dossiers' },
              { key: 'COMPLIANT', label: 'Compliant' },
              { key: 'NOT_VERIFIABLE', label: 'Requires Review' },
              { key: 'NON_COMPLIANT', label: 'Non-Compliant' },
            ].map((tab) => (
              <button
                key={tab.key}
                type="button"
                className={`history-tab-btn ${filter === tab.key ? 'history-tab-btn--active' : ''}`}
                onClick={() => setFilter(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Registry Table */}
      <div className="card history-table-card">
        <div className="card-header flex-between">
          <div className="flex items-center gap-2">
            <span>Official Screening Records</span>
            <span className="badge badge-gray">{filteredItems.length} records</span>
          </div>
        </div>

        <div className="card-body p-0">
          {loading ? (
            <div className="p-8 text-center text-muted">Loading history records...</div>
          ) : filteredItems.length === 0 ? (
            <EmptyState
              title="No inspection records found"
              description={
                searchQuery
                  ? `No dossiers match query "${searchQuery}". Try clearing search filters.`
                  : 'No inspection records match the current status filter.'
              }
              actionLabel="Start New Inspection"
              actionTo="/scan"
            />
          ) : (
            <div className="table-wrapper">
              <table className="history-table">
                <thead>
                  <tr>
                    <th>Dossier ID</th>
                    <th>Date & Time</th>
                    <th>Product Declaration</th>
                    <th>Category</th>
                    <th>Scope</th>
                    <th>Overall Status</th>
                    <th>Statutory Report</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredItems.map((item) => (
                    <tr key={item.id}>
                      <td className="font-mono font-bold text-xs rule-id-cell">
                        #{item.id}
                      </td>
                      <td className="text-xs text-muted">
                        <div className="font-medium text-main">
                          {new Date(item.created_at).toLocaleDateString()}
                        </div>
                        <div>{new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div>
                      </td>
                      <td>
                        <div className="font-semibold text-main">
                          {item.product_name || <span className="text-muted italic">Label un-named</span>}
                        </div>
                        <div className="text-xs text-muted">
                          Priority: {item.priority || 'NORMAL'}
                        </div>
                      </td>
                      <td>
                        <span className="badge badge-gray">{item.category || 'COMMODITY'}</span>
                      </td>
                      <td className="text-xs">
                        <div className="text-secondary">{item.package_type || 'RETAIL'}</div>
                        <div className="text-muted font-mono">{item.import_status || 'DOMESTIC'}</div>
                      </td>
                      <td>
                        <StatusBadge status={item.overall_result} size="sm" showBinary={true} />
                      </td>
                      <td>
                        {item.report ? (
                          <a
                            href={`/reports/${item.report.file_name}`}
                            target="_blank"
                            rel="noreferrer"
                            className="btn btn-outline btn-sm font-mono text-xs"
                          >
                            <FileText size={12} /> PDF Report
                          </a>
                        ) : (
                          <span className="text-muted text-xs">Pending Sign-off</span>
                        )}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <Link to={`/result/${item.id}`} className="btn btn-primary btn-sm">
                          <Eye size={13} /> Review Dossier
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default History;
