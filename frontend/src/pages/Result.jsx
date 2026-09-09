import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  FileText,
  Download,
  Scale,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RotateCcw,
  Save,
  ChevronDown,
  ChevronRight,
  ShieldCheck,
  Search,
  Eye,
  Layers,
  Printer,
  ExternalLink,
  History,
  PlusCircle,
  Barcode,
  Info,
} from 'lucide-react';
import { apiService } from '../services/api';
import ProgressStepper from '../components/ProgressStepper';
import StatusBadge from '../components/StatusBadge';
import EvidenceViewer from '../components/EvidenceViewer';
import ResultHero from '../components/ResultHero';
import ErrorState from '../components/ErrorState';
import { formatISTDateTime, formatISTDate } from '../utils/dateUtils';
import './Result.css';

const Result = () => {
  const { inspection_id: id } = useParams();

  const [inspection, setInspection] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Active Workstation Tab: 'evidence' (default primary showcase) | 'matrix' | 'physical' | 'report'
  const [activeTab, setActiveTab] = useState('evidence');

  // Rule Matrix Filter & Search
  const [ruleFilter, setRuleFilter] = useState('ALL');
  const [ruleSearch, setRuleSearch] = useState('');
  const [expandedRuleIds, setExpandedRuleIds] = useState(new Set());
  const [evidenceCount, setEvidenceCount] = useState(null);

  // Physical Verification & Manual Input State
  const [manualData, setManualData] = useState({
    actual_measured_weight: '',
    actual_weight_unit: 'g',
    measurement_source: 'CERTIFIED_DIGITAL_SCALE',
    inspector_notes: '',
    field_overrides: {},
  });
  const [savingManual, setSavingManual] = useState(false);
  const [manualSuccessMsg, setManualSuccessMsg] = useState(null);

  // Report Generation State
  const [generatingReport, setGeneratingReport] = useState(false);
  const [reportUrl, setReportUrl] = useState(null);

  // Inspector / User profile from localStorage
  const [profile] = useState(() => {
    try {
      const saved = localStorage.getItem('lmai_inspector_profile');
      if (saved) return JSON.parse(saved);
    } catch (_) {}
    return { name: 'Workspace User', badge: 'Not configured', station: 'Demo / Local Workspace' };
  });

  useEffect(() => {
    fetchInspection();
  }, [id]);

  const fetchInspection = async () => {
    try {
      setLoading(true);
      const data = await apiService.getInspection(id);
      setInspection(data);

      if (data.product?.actual_measured_weight) {
        setManualData((prev) => ({
          ...prev,
          actual_measured_weight: data.product.actual_measured_weight,
          actual_weight_unit: data.product.actual_weight_unit || 'g',
          measurement_source: data.product.measurement_source || 'CERTIFIED_DIGITAL_SCALE',
        }));
      }

      if (data.report?.file_name) {
        setReportUrl(`/reports/${data.report.file_name}`);
      }

      setError(null);
    } catch (err) {
      console.error('Failed to load inspection data:', err);
      setError('Unable to fetch inspection data for record #' + id);
    } finally {
      setLoading(false);
    }
  };

  const handleManualSave = async (e) => {
    e?.preventDefault();
    try {
      setSavingManual(true);
      setManualSuccessMsg(null);

      const payload = {
        inspection_id: parseInt(id),
        actual_measured_weight: manualData.actual_measured_weight
          ? parseFloat(manualData.actual_measured_weight)
          : null,
        actual_weight_unit: manualData.actual_weight_unit || null,
        measurement_source: manualData.measurement_source || null,
        inspector_notes: manualData.inspector_notes || null,
        field_overrides: manualData.field_overrides,
      };

      await apiService.submitManualInput(payload);
      setManualSuccessMsg('Measurements saved. Compliance rules re-evaluated successfully.');
      await fetchInspection();
    } catch (err) {
      console.error('Manual input submission error:', err);
      alert('Failed to save manual input: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSavingManual(false);
    }
  };

  const handleGenerateReport = async () => {
    try {
      setGeneratingReport(true);
      const res = await apiService.generateReport(id);
      const url = res.data?.file_url || `/reports/${res.data?.file_name}`;
      setReportUrl(url);
      window.open(url, '_blank');
      await fetchInspection();
    } catch (err) {
      console.error('Report generation error:', err);
      alert('Report generation failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setGeneratingReport(false);
    }
  };

  const toggleRuleExpand = (ruleId) => {
    setExpandedRuleIds((prev) => {
      const next = new Set(prev);
      if (next.has(ruleId)) next.delete(ruleId);
      else next.add(ruleId);
      return next;
    });
  };

  const handleScrollToConflict = () => {
    setActiveTab('evidence');
    setTimeout(() => {
      const el = document.getElementById('product-conflict-section');
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }, 100);
  };

  if (loading) {
    return (
      <div className="result-loading card p-8 text-center">
        <div className="spinner-icon mx-auto mb-3" style={{ width: 32, height: 32 }} />
        <h3 className="font-semibold">Loading Inspection & Evidence Workstation...</h3>
        <p className="text-muted text-xs">
          Retrieving package imagery, OCR tokens, spatial coordinates, and statutory rule evaluations.
        </p>
      </div>
    );
  }

  if (error || !inspection) {
    return (
      <div className="result-error">
        <ErrorState
          title="Inspection Record Not Found"
          message={error || 'Could not find inspection record #' + id}
          onRetry={fetchInspection}
        />
      </div>
    );
  }

  const ruleResults = inspection.rule_results || [];

  // Strict backend single source of truth for counts
  const summary = inspection.summary || {};
  const passCount =
    summary.passed_count ??
    summary.passed ??
    ruleResults.filter((r) => r.status === 'PASS').length;

  const failCount =
    summary.failed_count ??
    summary.failed ??
    ruleResults.filter((r) => r.status === 'FAIL').length;

  const reviewCount =
    summary.review_count ??
    summary.review ??
    ruleResults.filter(
      (r) =>
        r.status === 'NOT_VERIFIABLE' ||
        r.status === 'MANUAL_CHECK' ||
        r.status === 'REVIEW' ||
        r.status === 'NEEDS_REVIEW'
    ).length;

  const naCount =
    summary.not_applicable_count ??
    summary.na_count ??
    summary.not_applicable ??
    ruleResults.filter((r) => r.status === 'NOT_APPLICABLE').length;

  const rawOverall = (inspection.overall_result || '').toUpperCase().replace(/-/g, '_');
  const isReviewRequired =
    rawOverall === 'NOT_VERIFIABLE' ||
    rawOverall === 'NEEDS_REVIEW' ||
    rawOverall === 'REQUIRES_REVIEW' ||
    reviewCount > 0;

  // Filtered Rules for Matrix Table
  const filteredRules = ruleResults.filter((r) => {
    if (ruleFilter === 'FAIL' && r.status !== 'FAIL') return false;
    if (ruleFilter === 'PASS' && r.status !== 'PASS') return false;
    if (
      ruleFilter === 'REVIEW' &&
      r.status !== 'NOT_VERIFIABLE' &&
      r.status !== 'MANUAL_CHECK' &&
      r.status !== 'REVIEW' &&
      r.status !== 'NEEDS_REVIEW'
    )
      return false;
    if (ruleFilter === 'NA' && r.status !== 'NOT_APPLICABLE') return false;

    if (ruleSearch.trim()) {
      const q = ruleSearch.toLowerCase();
      const matchId = (r.rule_id || '').toLowerCase().includes(q);
      const matchParam = (r.parameter || '').toLowerCase().includes(q);
      const matchReason = (r.reason || r.message || '').toLowerCase().includes(q);
      if (!matchId && !matchParam && !matchReason) return false;
    }
    return true;
  });

  // Extract conflicting fields if any
  const conflictFields = (inspection.extracted_fields || []).filter(
    (f) =>
      String(f.field_value).startsWith('CONFLICT:') ||
      f.source === 'MULTI_IMAGE_CONFLICT' ||
      f.extraction_method === 'MULTI_IMAGE_CONFLICT' ||
      f.candidate_classification === 'TRUE_CONFLICT' ||
      f.status === 'AMBIGUOUS' ||
      f.is_ambiguous
  );

  // Identify review reasons breakdown
  const missingRules = ruleResults.filter(
    (r) =>
      r.status === 'NOT_VERIFIABLE' &&
      (r.reason || r.message || '').toLowerCase().includes('not detected')
  );

  const physicalRules = ruleResults.filter(
    (r) =>
      r.status === 'NOT_VERIFIABLE' &&
      (r.parameter === 'ACTUAL_NET_CONTENT' ||
        r.parameter === 'FONT_SIZE_COMPLIANCE' ||
        (r.reason || r.message || '').toLowerCase().includes('physical verification'))
  );

  // Sub-renderer for the Compliance Rule Matrix (Section 15 strictly)
  const renderComplianceMatrix = () => (
    <div className="card compliance-matrix-card" id="compliance-rule-matrix">
      <div className="card-header flex-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Layers size={16} className="text-primary" />
          <span className="font-semibold text-sm">Deterministic Statutory Rule Screening</span>
          <span className="badge badge-gray font-mono text-xs">
            {filteredRules.length} of {ruleResults.length} rules
          </span>
        </div>

        {/* Filter & Search controls */}
        <div className="matrix-toolbar">
          <div className="matrix-search">
            <Search size={13} className="matrix-search-icon" />
            <input
              type="text"
              placeholder="Search rule ID or requirement..."
              value={ruleSearch}
              onChange={(e) => setRuleSearch(e.target.value)}
              className="matrix-search-input"
            />
          </div>

          <div className="matrix-filter-buttons">
            {[
              { id: 'ALL', label: 'All', count: ruleResults.length },
              { id: 'FAIL', label: 'Fail', count: failCount },
              { id: 'REVIEW', label: 'Review', count: reviewCount },
              { id: 'PASS', label: 'Pass', count: passCount },
              { id: 'NA', label: 'N/A', count: naCount },
            ].map((f) => (
              <button
                key={f.id}
                type="button"
                className={`filter-btn ${ruleFilter === f.id ? 'filter-btn--active' : ''}`}
                onClick={() => setRuleFilter(f.id)}
              >
                {f.label} ({f.count})
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="card-body p-0">
        <div className="table-wrapper">
          <table className="compliance-matrix-table">
            <thead>
              <tr>
                <th style={{ width: '36px' }} />
                <th>Rule ID</th>
                <th>Requirement</th>
                <th>Extracted Declaration</th>
                <th>Validation Method</th>
                <th>Screening Result</th>
                <th>Evidence Source</th>
              </tr>
            </thead>
            <tbody>
              {filteredRules.map((rule, idx) => {
                const isExpanded = expandedRuleIds.has(rule.rule_id);
                const extractedVal =
                  rule.evidence_data?.value ||
                  rule.normalized_value ||
                  rule.raw_value ||
                  inspection.extracted_fields?.find((f) => f.field_name === rule.parameter)
                    ?.field_value ||
                  '—';

                return (
                  <React.Fragment key={idx}>
                    <tr
                      className={`matrix-row ${
                        isExpanded ? 'matrix-row--expanded' : ''
                      } matrix-row--${(rule.status || '').toLowerCase()}`}
                      onClick={() => toggleRuleExpand(rule.rule_id)}
                    >
                      <td className="expand-cell text-center">
                        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </td>
                      <td className="font-mono text-xs font-semibold rule-id-cell">
                        {rule.rule_id}
                      </td>
                      <td>
                        <div className="font-semibold text-main text-xs">
                          {rule.parameter?.replace(/_/g, ' ')}
                        </div>
                        <div className="text-2xs text-muted">
                          {rule.regulatory_source || 'LMPC Rules 2011'}
                        </div>
                      </td>
                      <td className="font-mono text-xs text-secondary">
                        {String(extractedVal).startsWith('CONFLICT:') ? (
                          <span className="text-danger font-semibold">{extractedVal}</span>
                        ) : extractedVal === '—' ? (
                          <span className="text-muted italic">Evidence not detected</span>
                        ) : (
                          extractedVal
                        )}
                      </td>
                      <td className="text-xs text-muted">
                        <span className="validation-method-pill font-mono text-2xs">
                          {rule.validation_method ||
                            rule.evidence_data?.validation_method ||
                            'PRESENCE_CHECK'}
                        </span>
                      </td>
                      <td>
                        <StatusBadge status={rule.status} size="sm" showBinary={true} />
                      </td>
                      <td className="text-xs text-muted font-mono">
                        {rule.evidence_data?.source || rule.evidence_type || 'OCR'}
                      </td>
                    </tr>

                    {/* Expanded Row Dossier */}
                    {isExpanded && (
                      <tr className="matrix-expanded-row">
                        <td colSpan="7">
                          <div className="rule-expanded-dossier">
                            <div className="expanded-grid">
                              <div>
                                <span className="dossier-label">
                                  {rule.rule_reference_status === 'NON_STATUTORY'
                                    ? 'Internal Inspection Specification:'
                                    : 'Statutory Legal Reference:'}
                                </span>
                                <div className="dossier-val font-semibold text-xs">
                                  {rule.rule_reference ||
                                    (rule.rule_reference_status === 'NON_STATUTORY'
                                      ? 'INTERNAL / NON-STATUTORY'
                                      : 'Legal Metrology (Packaged Commodities) Rules, 2011')}
                                </div>
                              </div>
                              <div>
                                <span className="dossier-label">Validation Finding Reason:</span>
                                <div className="dossier-val text-secondary text-xs">
                                  {rule.reason ||
                                    rule.message ||
                                    'Evaluated against statutory requirement matrix.'}
                                </div>
                              </div>
                              <div>
                                <span className="dossier-label">Reference Status:</span>
                                <div className="dossier-val font-mono text-xs">
                                  {rule.rule_reference_status === 'VERIFIED' ? (
                                    <span className="badge badge-success" style={{ fontSize: '10px', padding: '2px 6px' }}>Verified</span>
                                  ) : rule.rule_reference_status === 'NON_STATUTORY' ? (
                                    <span className="badge badge-gray" style={{ fontSize: '10px', padding: '2px 6px' }}>Non-Statutory</span>
                                  ) : (
                                    <span className="badge badge-warning" style={{ fontSize: '10px', padding: '2px 6px' }}>Pending verification</span>
                                  )}
                                </div>
                              </div>
                              <div>
                                <span className="dossier-label">Inspector Action Guidance:</span>
                                <div className="dossier-val text-muted text-xs">
                                  {rule.action_guidance ||
                                    (rule.status === 'FAIL'
                                      ? 'Review non-compliant declaration against applicable rules.'
                                      : rule.status === 'NOT_VERIFIABLE' || rule.status === 'REVIEW'
                                      ? 'Image-based screening cannot confirm this requirement. Physical verification is required according to the inspection configuration.'
                                      : 'Declaration satisfies verified rule criteria.')}
                                </div>
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}

              {filteredRules.length === 0 && (
                <tr>
                  <td colSpan="7" className="p-4 text-center text-muted">
                    No rules match the selected filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );

  // Sub-renderer for Physical Verification Section (Section 18 strictly)
  const renderPhysicalVerification = () => (
    <div className="card physical-verification-card" id="physical-verification-section">
      <div className="card-header flex-between">
        <div className="flex items-center gap-2">
          <Scale size={18} className="text-primary" />
          <span className="font-semibold text-sm">PHYSICAL VERIFICATION REQUIRED</span>
        </div>
        <span className="badge badge-warning font-mono text-xs">Direct Physical Inspection</span>
      </div>

      <div className="card-body">
        <div className="physical-intro-alert mb-4">
          <ShieldCheck size={22} className="text-teal flex-shrink-0" />
          <div className="text-xs leading-relaxed">
            <strong>Physical Verification Notice:</strong> Image-based screening cannot confirm this requirement. Physical verification is required according to the inspection configuration.
          </div>
        </div>

        {manualSuccessMsg && (
          <div className="badge badge-success mb-4 p-2 full-width flex items-center gap-1.5">
            <CheckCircle2 size={14} /> {manualSuccessMsg}
          </div>
        )}

        <form onSubmit={handleManualSave} className="physical-form-grid">
          <div className="physical-form-left">
            <h4 className="font-semibold text-sm mb-3">Physical Scale Measurement</h4>

            <div className="form-group mb-3">
              <label className="form-label">
                <span>Actual Measured Weight</span>
                <span className="text-xs text-muted">Physical Scale Reading</span>
              </label>
              <div className="flex gap-2">
                <input
                  type="number"
                  step="0.01"
                  className="form-control font-mono text-sm"
                  placeholder="e.g. 298.50"
                  value={manualData.actual_measured_weight}
                  onChange={(e) =>
                    setManualData({ ...manualData, actual_measured_weight: e.target.value })
                  }
                />
                <select
                  className="form-control"
                  style={{ width: '90px' }}
                  value={manualData.actual_weight_unit}
                  onChange={(e) =>
                    setManualData({ ...manualData, actual_weight_unit: e.target.value })
                  }
                >
                  <option value="g">g</option>
                  <option value="kg">kg</option>
                  <option value="ml">ml</option>
                  <option value="L">L</option>
                </select>
              </div>
              <span className="form-help text-xs text-muted mt-1 block">
                Declared net quantity: {inspection.product?.declared_net_quantity_value || '—'}{' '}
                {inspection.product?.declared_net_quantity_unit || ''}
              </span>
            </div>

            <div className="form-group mb-3">
              <label className="form-label">
                <span>Measurement Instrument</span>
                <span className="text-xs text-muted">Calibration Traceability</span>
              </label>
              <select
                className="form-control text-sm"
                value={manualData.measurement_source}
                onChange={(e) =>
                  setManualData({ ...manualData, measurement_source: e.target.value })
                }
              >
                <option value="CERTIFIED_DIGITAL_SCALE">
                  Certified Inspector Digital Scale (Class II/III)
                </option>
                <option value="STAMPED_LEGAL_METROLOGY_BALANCE">
                  Stamped Standard Metrological Balance
                </option>
                <option value="VERNIER_CALIPER_NUMERAL">
                  Vernier Caliper (Numeral Height Check)
                </option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">
                <span>Inspector Verification Notes</span>
              </label>
              <textarea
                rows={3}
                className="form-control text-sm"
                placeholder="Enter physical findings, tamper-seal status, font height inspection details..."
                value={manualData.inspector_notes}
                onChange={(e) =>
                  setManualData({ ...manualData, inspector_notes: e.target.value })
                }
              />
            </div>
          </div>

          <div className="physical-form-right">
            <h4 className="font-semibold text-sm mb-3">Declaration Overrides (If Misread)</h4>
            <div className="declaration-override-list">
              {['PRODUCT_NAME', 'MRP', 'DECLARED_NET_QUANTITY', 'MANUFACTURER_NAME'].map(
                (param) => (
                  <div key={param} className="form-group mb-2">
                    <label className="form-label text-xs">
                      <span>{param.replace(/_/g, ' ')}</span>
                    </label>
                    <input
                      type="text"
                      className="form-control text-xs font-mono"
                      placeholder={`Correct ${param.replace(/_/g, ' ').toLowerCase()} if misread`}
                      value={manualData.field_overrides[param] || ''}
                      onChange={(e) =>
                        setManualData({
                          ...manualData,
                          field_overrides: {
                            ...manualData.field_overrides,
                            [param]: e.target.value,
                          },
                        })
                      }
                    />
                  </div>
                )
              )}
            </div>

            <div className="mt-4 text-right">
              <button type="submit" className="btn btn-primary btn-sm" disabled={savingManual}>
                <Save size={14} />{' '}
                {savingManual ? 'Re-evaluating...' : 'Record Measurements & Re-Evaluate'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );

  // Sub-renderer for Inspection Report Dossier
  const renderReportDossier = () => (
    <div className="card report-workstation-card">
      <div className="card-header flex-between">
        <div className="flex items-center gap-2">
          <FileText size={18} className="text-primary" />
          <span className="font-semibold text-sm">Inspection Report Dossier & PDF Export</span>
        </div>
        {reportUrl && (
          <a
            href={reportUrl}
            target="_blank"
            rel="noreferrer"
            className="btn btn-outline btn-sm"
          >
            <Download size={14} /> Download PDF
          </a>
        )}
      </div>

      <div className="card-body">
        <div className="report-summary-dossier">
          <div className="report-summary-header">
            <div className="report-title-block">
              <h3 className="font-bold text-base">LEGAL METROLOGY COMPLIANCE INSPECTION REPORT</h3>
              <span className="text-xs text-muted">
                Official Screening Dossier • Legal Metrology (Packaged Commodities) Rules, 2011
              </span>
            </div>
            <div className="report-status-badge">
              <StatusBadge status={rawOverall} size="md" showBinary={true} />
            </div>
          </div>

          <div className="report-metadata-grid">
            <div>
              <span className="meta-lbl">Inspection ID:</span>
              <span className="meta-val font-mono">#{inspection.id}</span>
            </div>
            <div>
              <span className="meta-lbl">Inspection Date & Time:</span>
              <span className="meta-val">{formatISTDateTime(inspection.created_at)}</span>
            </div>
            <div>
              <span className="meta-lbl">Product Identity:</span>
              <span className="meta-val font-semibold">
                {inspection.product_name || 'Unspecified'}
              </span>
            </div>
            <div>
              <span className="meta-lbl">Manufacturer / Packer:</span>
              <span className="meta-val">
                {inspection.product?.manufacturer || 'Evidence not detected'}
              </span>
            </div>
            <div>
              <span className="meta-lbl">Declared Net Quantity:</span>
              <span className="meta-val font-mono">
                {inspection.product?.declared_net_quantity_value || '—'}{' '}
                {inspection.product?.declared_net_quantity_unit || ''}
              </span>
            </div>
            <div>
              <span className="meta-lbl">Maximum Retail Price (MRP):</span>
              <span className="meta-val font-mono">{inspection.product?.mrp || '—'}</span>
            </div>
          </div>

          <div className="report-findings-box mt-4">
            <h5 className="font-semibold text-xs text-muted uppercase mb-2">
              Compliance Findings Summary
            </h5>
            <ul className="report-findings-list">
              {inspection.findings?.failed?.map((f, idx) => (
                <li key={idx} className="finding-item finding-item--fail">
                  <XCircle size={14} /> {f}
                </li>
              ))}
              {inspection.findings?.needs_review?.map((r, idx) => (
                <li key={idx} className="finding-item finding-item--review">
                  <AlertTriangle size={14} /> {r}
                </li>
              ))}
              {inspection.findings?.verified?.map((v, idx) => (
                <li key={idx} className="finding-item finding-item--pass">
                  <CheckCircle2 size={14} /> {v}
                </li>
              ))}
            </ul>
          </div>

          <div className="report-signature-block mt-4">
            <div className="signature-box">
              <div className="signature-line" />
              <span className="signature-title">Reviewing Operator / Inspector</span>
              <span className="signature-sub">
                {profile.name || 'Workspace User'}{' '}
                {profile.badge && profile.badge !== 'Not configured'
                  ? `(${profile.badge})`
                  : ''}
              </span>
            </div>
            <div className="signature-box">
              <div className="signature-line" />
              <span className="signature-title">Workstation / Facility</span>
              <span className="signature-sub">
                {profile.station || 'Local Workstation'} • {formatISTDate(new Date())}
              </span>
            </div>
          </div>

          <div className="report-actions-row mt-4">
            <button
              type="button"
              className="btn btn-primary btn-md"
              onClick={handleGenerateReport}
              disabled={generatingReport}
            >
              <Printer size={16} />{' '}
              {generatingReport ? 'Compiling Dossier...' : 'Generate Official PDF Report'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="result-page">
      {/* 5-Step Workflow Stepper on Step 4 */}
      <ProgressStepper currentStep={reportUrl ? 5 : 4} />

      {/* Result Hero Header & Summary Bar */}
      <ResultHero
        inspection={inspection}
        ruleResults={ruleResults}
        reportUrl={reportUrl}
        generatingReport={generatingReport}
        onGenerateReport={handleGenerateReport}
        onViewConflict={handleScrollToConflict}
      />



      {/* Workstation View Tabs */}
      <div className="workstation-tab-bar" role="tablist" aria-label="Inspection workstation views">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'evidence'}
          className={`workstation-tab ${activeTab === 'evidence' ? 'workstation-tab--active' : ''}`}
          onClick={() => setActiveTab('evidence')}
        >
          <Eye size={15} />
          <span>Evidence Workstation</span>
          <span className="tab-badge">{evidenceCount ?? (inspection.extracted_fields?.length || ruleResults.length)}</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'matrix'}
          className={`workstation-tab ${activeTab === 'matrix' ? 'workstation-tab--active' : ''}`}
          onClick={() => setActiveTab('matrix')}
        >
          <Layers size={15} />
          <span>Compliance Rule Matrix</span>
          <span className="tab-badge">{ruleResults.length}</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'physical'}
          className={`workstation-tab ${activeTab === 'physical' ? 'workstation-tab--active' : ''}`}
          onClick={() => setActiveTab('physical')}
        >
          <Scale size={15} />
          <span>Physical Verification & Scale</span>
          {physicalRules.length > 0 && (
            <span className="tab-badge tab-badge--review">{physicalRules.length}</span>
          )}
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'report'}
          className={`workstation-tab ${activeTab === 'report' ? 'workstation-tab--active' : ''}`}
          onClick={() => setActiveTab('report')}
        >
          <FileText size={15} />
          <span>Inspection Report & Dossier</span>
        </button>
      </div>

      {/* Main Evidence Workstation Tab (Centerpiece + Rule Matrix beneath) */}
      {activeTab === 'evidence' && (
        <div className="workstation-combined-flow flex flex-col gap-6">
          <EvidenceViewer
            images={inspection.images || []}
            extractedFields={inspection.extracted_fields || []}
            ruleResults={ruleResults}
            barcodeResult={inspection.ocr_result?.ocr_data?.barcode_result}
            product={inspection.product}
            onCountChange={setEvidenceCount}
          />

          {/* Compliance Rule Matrix Section beneath Evidence Workstation (Section 15) */}
          <div className="compliance-matrix-container">
            {renderComplianceMatrix()}
          </div>
        </div>
      )}

      {/* Dedicated Matrix Tab */}
      {activeTab === 'matrix' && renderComplianceMatrix()}

      {/* Dedicated Physical Verification Tab */}
      {activeTab === 'physical' && renderPhysicalVerification()}

      {/* Dedicated Report Tab */}
      {activeTab === 'report' && renderReportDossier()}
    </div>
  );
};

export default Result;
