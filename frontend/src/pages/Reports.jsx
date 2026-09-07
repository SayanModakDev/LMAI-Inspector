import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FileText, Download, Eye, ExternalLink, Printer, Search, CheckCircle2, AlertTriangle, XCircle, ShieldCheck } from 'lucide-react';
import { apiService } from '../services/api';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import { formatISTDateTime } from '../utils/dateUtils';
import './Reports.css';

const Reports = () => {
  const [inspections, setInspections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const data = await apiService.getHistory(0, 100);
      setInspections(data || []);
    } catch (err) {
      console.error('Failed to load reports:', err);
    } finally {
      setLoading(false);
    }
  };

  const filtered = inspections.filter((item) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      String(item.id).includes(q) ||
      (item.product_name || '').toLowerCase().includes(q) ||
      (item.category || '').toLowerCase().includes(q)
    );
  });

  return (
    <div className="reports-page">
      {/* Header */}
      <div className="reports-header">
        <div>
          <h2 className="reports-title">Inspection Reports & Summaries</h2>
          <p className="reports-subtitle">
            Inspection reports, evidence summaries, and inspection-support documentation.
          </p>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="card reports-filter-card">
        <div className="reports-filter-body">
          <div className="reports-search-box">
            <Search size={15} className="search-icon" />
            <input
              type="text"
              placeholder="Search reports by ID, commodity name, or category..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="reports-search-input"
            />
          </div>
          <span className="badge badge-gray font-mono">{filtered.length} Reports Listed</span>
        </div>
      </div>

      {/* Reports Grid / Cards */}
      <div className="reports-grid">
        {loading ? (
          <div className="p-8 text-center text-muted">Loading reports registry...</div>
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No reports found"
            description="Complete an inspection to compile and archive compliance screening reports."
            actionLabel="Start New Inspection"
            actionTo="/scan"
          />
        ) : (
          filtered.map((item) => {
            const hasReport = Boolean(item.report?.file_name);
            const reportUrl = hasReport ? `/reports/${item.report.file_name}` : null;

            return (
              <div key={item.id} className="report-card card">
                <div className="report-card__header">
                  <div className="flex items-center gap-2">
                    <FileText size={18} className="text-primary" />
                    <span className="font-mono font-bold text-sm">Report #{item.id}</span>
                  </div>
                  <StatusBadge status={item.overall_result} size="sm" showBinary={true} />
                </div>

                <div className="report-card__body">
                  <h4 className="report-product-name">{item.product_name || 'Packaged Commodity'}</h4>
                  <div className="report-meta-rows">
                    <div className="report-meta-row">
                      <span className="meta-k">Date & Time:</span>
                      <span className="meta-v">{formatISTDateTime(item.created_at)}</span>
                    </div>
                    <div className="report-meta-row">
                      <span className="meta-k">Category:</span>
                      <span className="meta-v">{item.category || 'COMMODITY'}</span>
                    </div>
                    <div className="report-meta-row">
                      <span className="meta-k">Status:</span>
                      <span className="meta-v">
                        {hasReport ? (
                          <span className="text-success font-semibold flex items-center gap-1">
                            <CheckCircle2 size={12} /> PDF Compiled
                          </span>
                        ) : (
                          <span className="text-muted italic">Report Not Compiled</span>
                        )}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="report-card__footer">
                  {hasReport ? (
                    <div className="flex gap-2 full-width">
                      <a
                        href={reportUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="btn btn-outline btn-sm flex-1"
                      >
                        <Eye size={13} /> View Report
                      </a>
                      <a
                        href={reportUrl}
                        download
                        className="btn btn-primary btn-sm flex-1"
                      >
                        <Download size={13} /> Download
                      </a>
                    </div>
                  ) : (
                    <Link to={`/result/${item.id}`} className="btn btn-primary btn-sm full-width">
                      <Printer size={13} /> Review & Generate PDF
                    </Link>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default Reports;
