import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ScanLine,
  History,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  FileCheck2,
  Camera,
  UploadCloud,
  FileText,
  Barcode,
  Layers,
  Cpu,
  ArrowRight,
} from 'lucide-react';
import { apiService } from '../services/api';
import MetricCard from '../components/MetricCard';
import StatusBadge from '../components/StatusBadge';
import EmptyState from '../components/EmptyState';
import './Dashboard.css';

const Dashboard = () => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        setLoading(true);
        const data = await apiService.getDashboardStats();
        setStats(data);
        setError(null);
      } catch (err) {
        console.error('Failed to load dashboard statistics:', err);
        setError('Unable to retrieve operational metrics from backend.');
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  if (loading) {
    return (
      <div className="dashboard-loading">
        <div className="skeleton-header" />
        <div className="skeleton-grid" />
        <div className="skeleton-card" />
      </div>
    );
  }

  return (
    <div className="dashboard-page">
      {/* Top Level Operational Header */}
      <div className="dashboard-header">
        <div className="dashboard-header__text">
          <h2 className="dashboard-title">Inspection Overview</h2>
          <p className="dashboard-subtitle">
            Review packaging declarations, evidence and compliance screening results under Legal Metrology rules.
          </p>
        </div>
        <div className="dashboard-header__actions">
          <Link to="/history" className="btn btn-outline">
            <History size={15} /> View History
          </Link>
          <Link to="/scan" className="btn btn-primary">
            <ScanLine size={15} /> New Inspection
          </Link>
        </div>
      </div>

      {/* Restrained Metric Row (Real backend values) */}
      <div className="dashboard-metrics-grid">
        <MetricCard
          label="Total Inspections"
          value={stats?.total_inspections ?? 0}
          status="primary"
          icon={<FileCheck2 size={18} />}
          subtitle="All recorded screenings"
        />
        <MetricCard
          label="Passed (Compliant)"
          value={stats?.compliant ?? 0}
          status="pass"
          icon={<CheckCircle2 size={18} />}
          subtitle="Meets all verified rules"
        />
        <MetricCard
          label="Requires Review"
          value={stats?.not_verifiable ?? 0}
          status="review"
          icon={<AlertTriangle size={18} />}
          subtitle="Insufficient / conflicting evidence"
        />
        <MetricCard
          label="Failed (Non-Compliant)"
          value={stats?.non_compliant ?? 0}
          status="fail"
          icon={<XCircle size={18} />}
          subtitle="Mandatory rule violation"
        />
      </div>

      {/* Quick Inspection Command Entry Point */}
      <div className="card quick-inspection-card">
        <div className="quick-inspection__body">
          <div className="quick-inspection__info">
            <div className="badge badge-primary mb-2">QUICK INSPECTION ENTRY</div>
            <h3 className="quick-inspection__heading">Scan a Packaged Commodity</h3>
            <p className="quick-inspection__desc">
              Upload multiple panel photographs or capture directly from camera to extract printed declarations and run rule validation.
            </p>
          </div>
          <div className="quick-inspection__actions">
            <Link to="/scan" className="btn btn-primary">
              <UploadCloud size={16} /> Upload Package Views
            </Link>
            <Link to="/scan?camera=true" className="btn btn-outline">
              <Camera size={16} /> Open Camera
            </Link>
          </div>
        </div>
      </div>

      {/* Main Operational Split: Recent Inspections & System Telemetry */}
      <div className="dashboard-split-grid">
        {/* Recent Inspections Table */}
        <div className="card recent-inspections-card">
          <div className="card-header">
            <div className="flex items-center gap-2">
              <span>Recent Screenings</span>
              <span className="badge badge-gray">{stats?.recent_inspections?.length ?? 0} Latest</span>
            </div>
            <Link to="/history" className="text-primary text-xs font-semibold flex items-center gap-1">
              Complete Registry <ArrowRight size={12} />
            </Link>
          </div>

          <div className="card-body p-0">
            {(!stats?.recent_inspections || stats.recent_inspections.length === 0) ? (
              <EmptyState
                title="No inspections recorded yet"
                description="Start your first packaged commodity screening to build operational history."
                actionLabel="Start New Inspection"
                actionTo="/scan"
              />
            ) : (
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Date</th>
                      <th>Product</th>
                      <th>Category</th>
                      <th>Result</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.recent_inspections.map((item) => (
                      <tr key={item.id}>
                        <td className="font-mono font-semibold">#{item.id}</td>
                        <td className="text-xs text-muted">
                          {item.date ? new Date(item.date).toLocaleDateString() : '—'}
                        </td>
                        <td className="font-medium text-main">
                          {item.product_name || <span className="text-muted italic">Label unscoped</span>}
                        </td>
                        <td>
                          <span className="badge badge-gray">{item.category || 'GENERAL'}</span>
                        </td>
                        <td>
                          <StatusBadge status={item.result} size="sm" showBinary={true} />
                        </td>
                        <td>
                          <Link to={`/result/${item.id}`} className="btn btn-outline btn-sm">
                            Inspect
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

        {/* System Capabilities & Non-Compliance Telemetry */}
        <div className="dashboard-side-col">
          {/* Top Non-Compliance Telemetry */}
          <div className="card mb-4">
            <div className="card-header">
              <span>Frequent Rule Failures</span>
              <span className="text-xs text-muted">LMPC Rules</span>
            </div>
            <div className="card-body p-0">
              <table className="failure-table">
                <thead>
                  <tr>
                    <th>Requirement Parameter</th>
                    <th style={{ textAlign: 'right' }}>Occurrences</th>
                  </tr>
                </thead>
                <tbody>
                  {(stats?.common_failed_parameters || []).map((fail, i) => (
                    <tr key={i}>
                      <td className="font-medium text-xs">{fail.parameter?.replace(/_/g, ' ')}</td>
                      <td style={{ textAlign: 'right' }}>
                        <span className="badge badge-danger font-mono">{fail.count}</span>
                      </td>
                    </tr>
                  ))}
                  {(!stats?.common_failed_parameters || stats.common_failed_parameters.length === 0) && (
                    <tr>
                      <td colSpan="2" className="p-3 text-center text-muted text-xs">
                        No failure occurrences recorded.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* System Capabilities (Reported as capabilities, not marketing hype) */}
          <div className="card system-capabilities-card">
            <div className="card-header">
              <span>Inspection Engine Capabilities</span>
            </div>
            <div className="card-body">
              <ul className="capabilities-list">
                <li className="capability-item">
                  <Cpu size={16} className="capability-icon text-primary" />
                  <div>
                    <div className="capability-title">Multi-Pass OCR Engine</div>
                    <div className="capability-desc">Extracts printed package text with aspect preservation and orientation normalization.</div>
                  </div>
                </li>
                <li className="capability-item">
                  <Barcode size={16} className="capability-icon text-primary" />
                  <div>
                    <div className="capability-title">Barcode Decoding & Checksum</div>
                    <div className="capability-desc">EAN-13/UPC identification with secondary database cross-referencing.</div>
                  </div>
                </li>
                <li className="capability-item">
                  <Layers size={16} className="capability-icon text-primary" />
                  <div>
                    <div className="capability-title">Deterministic Rule Matrix</div>
                    <div className="capability-desc">Evaluates 16+ statutory requirements under Legal Metrology Act and Packaged Commodities Rules.</div>
                  </div>
                </li>
                <li className="capability-item">
                  <FileText size={16} className="capability-icon text-primary" />
                  <div>
                    <div className="capability-title">Statutory Report Generation</div>
                    <div className="capability-desc">Generates tamper-evident inspection reports for field records and enforcement review.</div>
                  </div>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
