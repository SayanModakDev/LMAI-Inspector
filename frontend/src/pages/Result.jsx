import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { FileText, CheckCircle, XCircle, AlertTriangle, Download, RefreshCw, Save } from 'lucide-react';
import { apiService } from '../services/api';
import './Result.css';

const Result = () => {
  const { inspection_id: id } = useParams();
  const navigate = useNavigate();
  const [inspection, setInspection] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Manual Input State
  const [isEditing, setIsEditing] = useState(false);
  const [manualData, setManualData] = useState({
    actual_measured_weight: '',
    actual_weight_unit: '',
    field_overrides: {}
  });
  const [savingManual, setSavingManual] = useState(false);
  
  // Report State
  const [generatingReport, setGeneratingReport] = useState(false);

  useEffect(() => {
    fetchInspection();
  }, [id]);

  const fetchInspection = async () => {
    try {
      setLoading(true);
      const data = await apiService.getInspection(id);
      setInspection(data);
      setManualData({
        actual_measured_weight: '',
        actual_weight_unit: '',
        field_overrides: {}
      });
      setError(null);
    } catch (err) {
      setError("Failed to load inspection results.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleManualSave = async () => {
    try {
      setSavingManual(true);
      
      const payload = {
        inspection_id: parseInt(id),
        actual_measured_weight: manualData.actual_measured_weight ? parseFloat(manualData.actual_measured_weight) : null,
        actual_weight_unit: manualData.actual_weight_unit || null,
        field_overrides: manualData.field_overrides,
      };
      
      await apiService.submitManualInput(payload);
      
      setIsEditing(false);
      await fetchInspection();
      
    } catch (err) {
      alert("Failed to save manual input.");
      console.error(err);
    } finally {
      setSavingManual(false);
    }
  };

  const handleGenerateReport = async () => {
    try {
      setGeneratingReport(true);
      const res = await apiService.generateReport(id);
      window.open(res.data.file_url, '_blank');
      await fetchInspection();
    } catch (err) {
      alert("Failed to generate report.");
      console.error(err);
    } finally {
      setGeneratingReport(false);
    }
  };

  if (loading) return <div className="p-8 text-center">Loading inspection data...</div>;
  if (error) return <div className="p-8 text-center text-danger">{error}</div>;
  if (!inspection) return <div className="p-8 text-center">No data found.</div>;

  const uploadedImages = inspection.images || inspection.ocr_result?.ocr_data?.images || [{ image_path: inspection.image_path }];
  const barcode = inspection.ocr_result?.ocr_data?.barcode_result;

  // Normalized overall result status handling
  const rawOverall = (inspection.overall_result || '').replace('_', '-');
  let overallRatingClass = 'card-review';
  let overallRatingBadge = null;
  let overallBadgeColor = 'badge-warning';

  if (rawOverall === 'COMPLIANT') {
    overallRatingClass = 'card-compliant';
    overallBadgeColor = 'badge-success';
    overallRatingBadge = (
      <div className="rating-badge rating-compliant">
        <CheckCircle size={20} />
        <span>1 — COMPLIANT</span>
      </div>
    );
  } else if (rawOverall === 'NON-COMPLIANT') {
    overallRatingClass = 'card-non-compliant';
    overallBadgeColor = 'badge-danger';
    overallRatingBadge = (
      <div className="rating-badge rating-non-compliant">
        <XCircle size={20} />
        <span>0 — NON-COMPLIANT</span>
      </div>
    );
  } else {
    overallRatingClass = 'card-review';
    overallBadgeColor = 'badge-warning';
    overallRatingBadge = (
      <div className="rating-badge rating-review">
        <AlertTriangle size={20} />
        <span>REVIEW — INSUFFICIENT EVIDENCE</span>
      </div>
    );
  }

  // Calculate rule summary metrics
  const ruleResults = inspection.rule_results || [];
  const passCount = ruleResults.filter(r => r.status === 'PASS').length;
  const failCount = ruleResults.filter(r => r.status === 'FAIL').length;
  const reviewCount = ruleResults.filter(r => r.status === 'NOT_VERIFIABLE' || r.status === 'MANUAL_CHECK').length;
  const naCount = ruleResults.filter(r => r.status === 'NOT_APPLICABLE').length;

  // Helper to resolve parameter readable names
  const getParameterDisplayName = (param) => {
    switch (param) {
      case 'DECLARED_NET_QUANTITY':
      case 'NET_QUANTITY':
        return 'Declared Net Quantity';
      case 'MRP':
        return 'Maximum Retail Price (MRP)';
      case 'MONTH_YEAR_MANUFACTURE':
      case 'MANUFACTURE_DATE':
        return 'Date of Manufacture';
      case 'PACKING_DATE':
        return 'Date of Packaging';
      case 'BEST_BEFORE_USE_BY':
        return 'Best Before / Use By';
      case 'USE_BEFORE_DATE':
        return 'Use Before Date';
      case 'EXPIRY_DATE':
        return 'Date of Expiry';
      case 'MANUFACTURER_NAME':
        return 'Manufacturer Name';
      case 'MANUFACTURER_ADDRESS':
        return 'Manufacturer Address';
      case 'COUNTRY_OF_ORIGIN':
        return 'Country of Origin';
      case 'CONSUMER_CARE':
        return 'Consumer Care Details';
      case 'INGREDIENTS_LIST':
        return 'Ingredients List';
      case 'VEG_NONVEG_SYMBOL':
        return 'Veg / Non-Veg Symbol';
      case 'FSSAI_LICENSE':
        return 'FSSAI License Number';
      case 'BATCH_NUMBER':
        return 'Batch / Lot Number';
      case 'GENERIC_NAME':
        return 'Generic Name';
      default:
        return (param || '').replaceAll('_', ' ');
    }
  };

  // Helper for binary rating of each rule
  const getRuleBinary = (rule) => {
    if (rule.status === 'PASS') {
      return { label: '1', badgeClass: 'binary-badge-1', title: '1 — COMPLIANT' };
    }
    if (rule.status === 'FAIL') {
      return { label: '0', badgeClass: 'binary-badge-0', title: '0 — NON-COMPLIANT' };
    }
    if (rule.status === 'NOT_VERIFIABLE' || rule.status === 'MANUAL_CHECK') {
      return { label: 'REVIEW', badgeClass: 'binary-badge-review', title: 'REVIEW — Insufficient Evidence' };
    }
    return { label: 'N/A', badgeClass: 'binary-badge-na', title: 'N/A — Not Applicable' };
  };

  // Helper for status badge
  const getRuleStatusBadge = (status) => {
    switch (status) {
      case 'PASS':
        return <span className="badge badge-success"><CheckCircle size={12} className="mr-1" /> PASS</span>;
      case 'FAIL':
        return <span className="badge badge-danger"><XCircle size={12} className="mr-1" /> FAIL</span>;
      case 'NOT_VERIFIABLE':
      case 'MANUAL_CHECK':
        return <span className="badge badge-warning"><AlertTriangle size={12} className="mr-1" /> NOT VERIFIABLE</span>;
      case 'NOT_APPLICABLE':
        return <span className="badge badge-gray">NOT APPLICABLE</span>;
      default:
        return <span className="badge badge-gray">{status}</span>;
    }
  };

  // Helper to extract and decompose Declared Net Quantity details
  const netQtyRule = ruleResults.find(r => 
    r.parameter === 'DECLARED_NET_QUANTITY' || r.parameter === 'NET_QUANTITY'
  );
  const netQtyField = inspection.extracted_fields?.find(f => 
    f.field_name === 'DECLARED_NET_QUANTITY' || f.field_name === 'NET_QUANTITY'
  );

  const getNetQtyDecomposition = (rule, field) => {
    let val = rule?.value ?? rule?.quantity_value ?? rule?.evidence_data?.quantity_value ?? rule?.evidence_data?.value ?? inspection.product?.declared_net_quantity_value ?? null;
    let unit = rule?.unit ?? rule?.quantity_unit ?? rule?.evidence_data?.quantity_unit ?? rule?.evidence_data?.unit ?? inspection.product?.declared_net_quantity_unit ?? null;
    let rawVal = rule?.raw_value ?? rule?.evidence_data?.raw_value ?? field?.field_value ?? null;

    let qtyPresent = rule?.quantity_present ?? rule?.evidence_data?.quantity_present;
    let unitPresent = rule?.unit_present ?? rule?.evidence_data?.unit_present;
    let pairValid = rule?.quantity_unit_valid ?? rule?.evidence_data?.quantity_unit_valid;

    if ((val === null || val === undefined || unit === null) && rawVal) {
      const match = String(rawVal).match(/([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)?/);
      if (match) {
        if (val === null || val === undefined) val = match[1];
        if (!unit && match[2]) unit = match[2];
      }
    }

    if (qtyPresent === undefined) {
      qtyPresent = val !== null && val !== undefined && String(val).trim() !== '' && parseFloat(val) > 0;
    }
    if (unitPresent === undefined) {
      unitPresent = Boolean(unit && String(unit).trim() !== '');
    }
    if (pairValid === undefined) {
      pairValid = Boolean(qtyPresent && unitPresent && rule?.status === 'PASS');
    }

    const qtyValid = Boolean(qtyPresent && parseFloat(val) > 0);
    const unitValid = Boolean(unitPresent);
    const combinedValid = Boolean(pairValid && qtyValid && unitValid && rule?.status === 'PASS');

    let displayValUnit = 'Not Detected';
    if (val && unit) {
      displayValUnit = `${val} ${unit}`;
    } else if (rawVal) {
      displayValUnit = rawVal;
    }

    let binaryText = 'REVIEW';
    let binaryClass = 'qty-binary-review';
    if (rule?.status === 'PASS') {
      binaryText = '1 — PASS';
      binaryClass = 'qty-binary-pass';
    } else if (rule?.status === 'FAIL') {
      binaryText = '0 — FAIL';
      binaryClass = 'qty-binary-fail';
    } else if (rule?.status === 'NOT_APPLICABLE') {
      binaryText = 'N/A';
      binaryClass = 'qty-binary-na';
    }

    let quantityType = rule?.quantity_type ?? rule?.evidence_data?.quantity_type ?? field?.quantity_type ?? field?.field_data?.quantity_type ?? null;
    if (!quantityType && unit) {
      const u = String(unit).toLowerCase();
      if (['g', 'gm', 'gms', 'kg', 'mg'].includes(u)) quantityType = 'MASS';
      else if (['ml', 'l', 'ltr', 'cl'].includes(u)) quantityType = 'VOLUME';
      else if (['pieces', 'piece', 'pcs', 'tablets', 'capsules', 'units', 'numbers'].includes(u)) quantityType = 'COUNT';
    }

    return {
      val: val || '—',
      unit: unit || '—',
      quantityType: quantityType || '—',
      rawVal,
      displayValUnit,
      qtyPresent,
      unitPresent,
      qtyValid,
      unitValid,
      pairValid: combinedValid,
      binaryText,
      binaryClass,
      reason: rule?.reason || rule?.message || 'Declared net quantity validation'
    };
  };

  const netQtyDecomposition = getNetQtyDecomposition(netQtyRule, netQtyField);

  // Helper to format reason with strict prefix rules
  const renderRuleReason = (rule) => {
    const reasonText = rule.reason || rule.message || 'Validation evaluation complete.';
    if (rule.status === 'FAIL') {
      return (
        <div className="reason-block reason-fail">
          <span className="reason-header">0 — FAIL</span>
          <span className="reason-body">Reason: {reasonText}</span>
        </div>
      );
    }
    if (rule.status === 'NOT_VERIFIABLE' || rule.status === 'MANUAL_CHECK') {
      return (
        <div className="reason-block reason-review">
          <span className="reason-header">REVIEW</span>
          <span className="reason-body">Reason: {reasonText}</span>
        </div>
      );
    }
    if (rule.status === 'PASS') {
      return (
        <div className="reason-block reason-pass">
          <span className="reason-header">1 — PASS</span>
          <span className="reason-body">{reasonText}</span>
        </div>
      );
    }
    return (
      <div className="reason-block reason-na">
        <span className="reason-header">N/A</span>
        <span className="reason-body">{reasonText}</span>
      </div>
    );
  };

  return (
    <div className="result-container">
      {/* Top Header */}
      <div className="result-header">
        <div className="title-section">
          <h1>Inspection Result #{inspection.id}</h1>
          <span className={`badge result-badge ${overallBadgeColor}`}>
            {rawOverall === 'COMPLIANT' ? '1 — COMPLIANT' : rawOverall === 'NON-COMPLIANT' ? '0 — NON-COMPLIANT' : 'REVIEW — INSUFFICIENT EVIDENCE'}
          </span>
        </div>
        <div className="action-buttons">
          {inspection.report ? (
            <a href={`/api/report/${inspection.id}/download`} target="_blank" rel="noreferrer" className="btn btn-outline">
              <Download size={16} /> Download PDF
            </a>
          ) : (
            <button className="btn btn-outline" onClick={handleGenerateReport} disabled={generatingReport}>
              <FileText size={16} /> {generatingReport ? 'Generating...' : 'Generate Report'}
            </button>
          )}
          <button className="btn btn-primary" onClick={() => navigate('/scan')}>
            New Scan
          </button>
        </div>
      </div>

      {/* COMPLIANCE RATING Inspection Summary Card */}
      <div className={`compliance-summary-card ${overallRatingClass}`}>
        <div className="compliance-summary-header">
          <div className="compliance-summary-title-row">
            <span className="summary-label">COMPLIANCE RATING</span>
            <span className="summary-subtitle">1 / 0 / REVIEW</span>
          </div>
          <div className="compliance-rating-display">
            {overallRatingBadge}
          </div>
        </div>

        <div className="compliance-disclaimer">
          <AlertTriangle size={15} className="inline mr-1" />
          <span>Inspection-support result based on available image evidence. Final legal verification remains with the authorized inspector.</span>
        </div>

        <div className="compliance-metrics-row">
          <div className="metric-pill metric-pass">
            <span className="metric-binary">1</span>
            <span className="metric-label">Pass</span>
            <span className="metric-count">{passCount} rules</span>
          </div>
          <div className="metric-pill metric-fail">
            <span className="metric-binary">0</span>
            <span className="metric-label">Fail</span>
            <span className="metric-count">{failCount} rules</span>
          </div>
          <div className="metric-pill metric-review">
            <span className="metric-binary">REVIEW</span>
            <span className="metric-label">Needs Evidence</span>
            <span className="metric-count">{reviewCount} rules</span>
          </div>
          <div className="metric-pill metric-na">
            <span className="metric-binary">N/A</span>
            <span className="metric-label">Not Applicable</span>
            <span className="metric-count">{naCount} rules</span>
          </div>
        </div>
      </div>

      {/* Declared Net Quantity Dedicated Decomposition Hero Card */}
      <div className="declared-qty-hero-card">
        <div className="card-header flex-between">
          <div className="flex items-center gap-2">
            <strong>DECLARED NET QUANTITY</strong>
            <span className="text-xs text-muted">(Legal Metrology Packaged Commodities Rules)</span>
          </div>
          <span className="badge badge-gray" style={{ fontSize: '0.75rem' }}>
            PARAMETER DECOMPOSITION
          </span>
        </div>
        <div className="declared-qty-hero-grid">
          <div className="declared-qty-val-box">
            <span className="qty-headline-label">Declared Net Quantity</span>
            <div className="qty-headline-value">{netQtyDecomposition.displayValUnit}</div>
            <div className="text-xs text-muted">Value: {netQtyDecomposition.val} | Unit: {netQtyDecomposition.unit} | Type: {netQtyDecomposition.quantityType}</div>
          </div>
          <div className="declared-qty-checks">
            <div className="qty-check-item">
              <span className="qty-check-label">Quantity validation:</span>
              <span className={`qty-check-val ${netQtyDecomposition.qtyValid ? 'valid' : (netQtyDecomposition.qtyPresent ? 'invalid' : 'missing')}`}>
                {netQtyDecomposition.qtyValid ? 'VALID' : (netQtyDecomposition.qtyPresent ? 'INVALID' : 'MISSING')}
              </span>
            </div>
            <div className="qty-check-item">
              <span className="qty-check-label">Unit validation:</span>
              <span className={`qty-check-val ${netQtyDecomposition.unitValid ? 'valid' : 'missing'}`}>
                {netQtyDecomposition.unitValid ? 'VALID' : 'MISSING'}
              </span>
            </div>
            <div className="qty-check-item">
              <span className="qty-check-label">Quantity + unit validation:</span>
              <span className={`qty-check-val ${netQtyDecomposition.pairValid ? 'valid' : 'invalid'}`}>
                {netQtyDecomposition.pairValid ? 'VALID' : 'INVALID'}
              </span>
            </div>
          </div>
          <div className="declared-qty-binary-box">
            <span className="qty-headline-label">Binary Result</span>
            <div className={`qty-binary-badge ${netQtyDecomposition.binaryClass}`}>
              {netQtyDecomposition.binaryText}
            </div>
            <div className="text-xs text-muted mt-1">{netQtyDecomposition.reason}</div>
          </div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="result-grid">
        {/* Left Column: Image and Details */}
        <div className="result-left">
          <div className="card mb-4">
            <div className="card-header">Uploaded Product Images</div>
            <div className="card-body p-0">
              {uploadedImages.map((image, index) => (
                <img
                  key={image.image_path || index}
                  src={image.image_path?.startsWith('/uploads/') ? image.image_path : `/uploads/${image.image_path}`}
                  alt={`Product label ${index + 1}`}
                  className="result-image"
                  onError={(e) => { e.target.style.display = 'none'; }}
                />
              ))}
            </div>
          </div>
          
          <div className="card mb-4">
            <div className="card-header">Inspection Details</div>
            <div className="card-body">
              <table className="detail-table">
                <tbody>
                  <tr><th>Date:</th><td>{new Date(inspection.created_at).toLocaleString()}</td></tr>
                  <tr><th>Category:</th><td>{inspection.category}</td></tr>
                  <tr><th>Product Type:</th><td>{inspection.product_type || 'UNKNOWN'}</td></tr>
                  <tr><th>Brand:</th><td>{inspection.brand || inspection.product?.brand || 'Not detected'}</td></tr>
                  <tr><th>Product Name:</th><td>{inspection.product_name || inspection.product?.product_name || 'Not detected'}</td></tr>
                  <tr>
                    <th>Package Type:</th>
                    <td>
                      {inspection.package_type || 'RETAIL'}
                      <span className="text-xs text-muted ml-1" style={{ fontSize: '0.75rem' }}>
                        {inspection.package_type === 'RETAIL' ? '(Inspector Default)' : '(Inspector Selected)'}
                      </span>
                    </td>
                  </tr>
                  <tr>
                    <th>Import Status:</th>
                    <td>
                      {inspection.import_status || 'DOMESTIC'}
                      <span className="text-xs text-muted ml-1" style={{ fontSize: '0.75rem' }}>
                        {inspection.import_status === 'DOMESTIC' ? '(Inspector Default)' : '(Inspector Selected)'}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div className="card mb-4">
            <div className="card-header">Inspection Findings</div>
            <div className="card-body">
              {inspection.findings?.verified?.map((item, index) => <p key={`verified-${index}`} className="text-success">✓ {item}</p>)}
              {inspection.findings?.needs_review?.map((item, index) => <p key={`review-${index}`} className="text-warning">⚠ {item}</p>)}
              {inspection.findings?.failed?.map((item, index) => <p key={`failed-${index}`} className="text-danger">✕ {item}</p>)}
              {(!inspection.findings || (inspection.findings.verified?.length === 0 && inspection.findings.needs_review?.length === 0 && inspection.findings.failed?.length === 0)) && (
                <p className="text-muted text-sm">Findings compiled from rule evaluation.</p>
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Product ID and Extracted Declarations */}
        <div className="result-right">
          {barcode && (
            <div className="card mb-4">
              <div className="card-header flex-between">
                <span>Barcode Lookup</span>
                <span className="badge badge-gray" style={{ fontSize: '0.7rem' }}>SUPPLEMENTARY EVIDENCE</span>
              </div>
              <div className="card-body">
                <table className="detail-table">
                  <tbody>
                    <tr><th>Code:</th><td>{barcode.value || 'Not detected'}</td></tr>
                    <tr><th>Detection:</th><td>{barcode.source === 'OCR_BARCODE_TEXT' ? 'OCR fallback' : barcode.type || 'Unknown'}</td></tr>
                    <tr><th>Product lookup:</th><td>{barcode.lookup?.status || 'Not performed'}</td></tr>
                    {barcode.lookup?.product_name && (
                      <tr>
                        <th>Product name:</th>
                        <td>
                          {barcode.lookup.product_name}
                          {inspection.extracted_fields?.find(f => f.field_name === 'PRODUCT_NAME')?.barcode_match === 'CONFLICTS' && (
                            <span className="badge badge-danger ml-2" title="Conflicts with printed OCR label">CONFLICT WITH OCR</span>
                          )}
                          {inspection.extracted_fields?.find(f => f.field_name === 'PRODUCT_NAME')?.barcode_match === 'AGREES' && (
                            <span className="badge badge-success ml-2" title="Corroborates printed OCR label">AGREES WITH OCR</span>
                          )}
                        </td>
                      </tr>
                    )}
                    {barcode.lookup?.brands && <tr><th>Brand:</th><td>{barcode.lookup.brands}</td></tr>}
                    {inspection.extracted_fields?.find(f => f.field_name === 'PRODUCT_NAME')?.barcode_match === 'CONFLICTS' && (
                      <tr>
                        <td colSpan="2" className="text-danger text-xs p-2" style={{ backgroundColor: '#fef2f2', borderRadius: '4px' }}>
                          <AlertTriangle size={14} className="inline mr-1" />
                          Notice: Barcode database name contradicts printed OCR. Database lookups cannot override legal label evidence.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="card mb-4">
            <div className="card-header">Product Identification</div>
            <div className="card-body">
              <table className="detail-table">
                <tbody>
                  <tr><th>Brand:</th><td>{inspection.brand || inspection.product?.brand || 'Not detected'}</td></tr>
                  <tr><th>Product:</th><td>{inspection.product_name || inspection.product?.product_name || 'Not detected'}</td></tr>
                  <tr><th>Generic name:</th><td>{inspection.product?.generic_name || inspection.extracted_fields?.find(f => f.field_name === 'GENERIC_NAME')?.field_value || 'Not detected'}</td></tr>
                  <tr><th>Barcode:</th><td>{barcode?.value || inspection.extracted_fields?.find(f => f.field_name === 'BARCODE')?.field_value || 'Not detected'}</td></tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Extracted Declarations Card (OCR) */}
          <div className="card mb-4">
            <div className="card-header flex-between">
              <span>Extracted Declarations (OCR)</span>
              <button 
                className="btn btn-sm btn-outline" 
                onClick={() => setIsEditing(!isEditing)}
              >
                {isEditing ? 'Cancel Edit' : 'Manual Override'}
              </button>
            </div>
            
            <div className="card-body">
              {isEditing && (
                <div className="manual-edit-banner">
                  <AlertTriangle size={16} />
                  <span>Manual overrides will trigger a re-evaluation of compliance rules.</span>
                </div>
              )}
              
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Parameter</th>
                      <th>Extracted Value</th>
                      {isEditing && <th>Manual Override</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {/* Product Name */}
                    <tr>
                      <td><strong>Product Name</strong></td>
                      <td>
                        {(() => {
                          const f = inspection.extracted_fields?.find(f => f.field_name === 'PRODUCT_NAME');
                          if (!f || !f.field_value) return 'Not Found';
                          if (f.field_value.startsWith('CONFLICT:')) {
                            return <><span className="badge badge-danger mr-1" style={{ fontSize: '0.7rem' }}>CONFLICT</span><span className="text-danger">{f.field_value}</span></>;
                          }
                          return f.field_value;
                        })()}
                      </td>
                      {isEditing && <td><input className="form-control" value={manualData.field_overrides.PRODUCT_NAME ?? ''} onChange={(e) => setManualData({...manualData, field_overrides: {...manualData.field_overrides, PRODUCT_NAME: e.target.value}})} placeholder="Correct product name" /></td>}
                    </tr>

                    {/* MRP */}
                    <tr>
                      <td><strong>MRP</strong></td>
                      <td>
                        {(() => {
                          const f = inspection.extracted_fields?.find(f => f.field_name === 'MRP');
                          if (!f || !f.field_value) return 'Not Found';
                          if (f.field_value.startsWith('CONFLICT:')) {
                            return <><span className="badge badge-danger mr-1" style={{ fontSize: '0.7rem' }}>CONFLICT</span><span className="text-danger">{f.field_value}</span></>;
                          }
                          return f.field_value;
                        })()}
                      </td>
                      {isEditing && (
                        <td>
                          <input 
                            type="text" 
                            className="form-control" 
                            value={manualData.field_overrides.MRP ?? ''}
                            onChange={(e) => setManualData({...manualData, field_overrides: {...manualData.field_overrides, MRP: e.target.value}})}
                            placeholder="Correct MRP"
                          />
                        </td>
                      )}
                    </tr>
                    
                    {/* Declared Net Quantity */}
                    <tr>
                      <td>
                        <strong>Declared Net Quantity</strong>
                        <div className="text-xs text-muted" style={{ fontSize: '0.75rem', color: '#6b7280' }}>Printed label declaration (OCR)</div>
                      </td>
                      <td>
                        <div>{netQtyDecomposition.displayValUnit}</div>
                      </td>
                      {isEditing && (
                        <td>
                          <input 
                            type="text" 
                            className="form-control" 
                            value={manualData.field_overrides.DECLARED_NET_QUANTITY ?? ''}
                            onChange={(e) => setManualData({...manualData, field_overrides: {...manualData.field_overrides, DECLARED_NET_QUANTITY: e.target.value}})}
                            placeholder="Correct declared net quantity"
                          />
                        </td>
                      )}
                    </tr>
                    
                    {/* Mfg/Pkg Date */}
                    <tr>
                      <td><strong>Mfg/Pkg Date</strong></td>
                      <td>{inspection.extracted_fields?.find(f => f.field_name === 'MONTH_YEAR_MANUFACTURE' || f.field_name === 'MANUFACTURE_DATE' || f.field_name === 'PACKING_DATE')?.field_value || 'Not Found'}</td>
                      {isEditing && (
                        <td>
                          <input 
                            type="text" 
                            className="form-control" 
                            value={manualData.field_overrides.MONTH_YEAR_MANUFACTURE ?? manualData.field_overrides.MANUFACTURE_DATE ?? manualData.field_overrides.PACKING_DATE ?? ''}
                            onChange={(e) => setManualData({...manualData, field_overrides: {...manualData.field_overrides, MONTH_YEAR_MANUFACTURE: e.target.value}})}
                            placeholder="Correct printed date"
                          />
                        </td>
                      )}
                    </tr>
                    <tr>
                      <td><strong>Generic Name</strong></td>
                      <td>{inspection.extracted_fields?.find(f => f.field_name === 'GENERIC_NAME')?.field_value || 'Not Found'}</td>
                      {isEditing && <td><input className="form-control" value={manualData.field_overrides.GENERIC_NAME ?? ''} onChange={(e) => setManualData({...manualData, field_overrides: {...manualData.field_overrides, GENERIC_NAME: e.target.value}})} placeholder="Correct generic name" /></td>}
                    </tr>
                  </tbody>
                </table>
              </div>
              <div className="mt-3">
                {inspection.extracted_fields?.filter((field) => !['PRODUCT_NAME', 'MRP', 'DECLARED_NET_QUANTITY', 'NET_QUANTITY', 'MONTH_YEAR_MANUFACTURE', 'GENERIC_NAME'].includes(field.field_name)).map((field) => (
                  <div key={field.id || field.field_name} className="text-sm mb-2"><strong>{field.field_name.replaceAll('_', ' ')}:</strong> {field.field_value || 'Not detected'}
                    {isEditing && <input className="form-control mt-1" value={manualData.field_overrides[field.field_name] ?? ''} onChange={(e) => setManualData({...manualData, field_overrides: {...manualData.field_overrides, [field.field_name]: e.target.value}})} placeholder={`Correct ${field.field_name.replaceAll('_', ' ').toLowerCase()}`} />}
                  </div>
                ))}
              </div>
              
              {isEditing && (
                <div className="mt-3 text-right">
                  <button 
                    className="btn btn-primary" 
                    onClick={handleManualSave} 
                    disabled={savingManual}
                  >
                    {savingManual ? <RefreshCw className="spinner-icon" size={16} /> : <Save size={16} />} 
                    Save & Re-evaluate
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Main Rule Matrix Table */}
      <div className="card mb-4">
        <div className="card-header flex-between">
          <div>
            <strong>Main Rule Matrix & Deterministic Validation</strong>
            <span className="text-xs text-muted ml-2">Legal Metrology Compliance Evaluation</span>
          </div>
          <span className="badge badge-gray" style={{ fontSize: '0.75rem' }}>
            {ruleResults.length} RULES EVALUATED
          </span>
        </div>
        <div className="card-body p-0">
          <div className="rule-matrix-table-wrapper">
            <table className="rule-matrix-table">
              <thead>
                <tr>
                  <th>Rule ID</th>
                  <th>Parameter</th>
                  <th>Extracted Value</th>
                  <th>Validation</th>
                  <th>Binary</th>
                  <th>Status</th>
                  <th>Evidence</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {ruleResults.map((rule, idx) => {
                  const binary = getRuleBinary(rule);
                  const isNetQty = rule.parameter === 'DECLARED_NET_QUANTITY' || rule.parameter === 'NET_QUANTITY';
                  const extractedVal = isNetQty
                    ? netQtyDecomposition.displayValUnit
                    : (rule.evidence_data?.value || rule.normalized_value || rule.raw_value || inspection.extracted_fields?.find(f => f.field_name === rule.parameter)?.field_value || '—');

                  return (
                    <tr key={idx}>
                      {/* 1. Rule ID */}
                      <td>
                        <span className="rule-id-code">{rule.rule_id}</span>
                      </td>

                      {/* 2. Parameter */}
                      <td>
                        <div className="rule-param-name">{getParameterDisplayName(rule.parameter)}</div>
                        <div className="rule-param-category">{rule.regulatory_source || 'LEGAL_METROLOGY'}</div>
                      </td>

                      {/* 3. Extracted Value */}
                      <td>
                        <div className="rule-extracted-value">
                          {(() => {
                            const classification = rule.candidate_classification || rule.evidence_data?.candidate_classification;
                            if (classification === 'TRUE_CONFLICT') {
                              return (
                                <>
                                  <span className="badge badge-danger mr-1" style={{ fontSize: '0.65rem' }}>TRUE CONFLICT</span>
                                  <span className="text-danger">{extractedVal}</span>
                                </>
                              );
                            }
                            if (classification === 'OCR_VARIATION') {
                              return (
                                <>
                                  <span className="badge badge-warning mr-1" style={{ fontSize: '0.65rem' }}>REVIEW</span>
                                  <span>{extractedVal}</span>
                                  <div className="text-xs text-muted mt-1">Likely OCR character variations across views</div>
                                </>
                              );
                            }
                            if (classification === 'MULTI_PANEL_EVIDENCE') {
                              return (
                                <>
                                  <span className="badge mr-1" style={{ fontSize: '0.65rem', background: '#3b82f6', color: '#fff' }}>MULTI-PANEL</span>
                                  <span>{extractedVal}</span>
                                  <div className="text-xs text-muted mt-1">Additional evidence from other package views</div>
                                </>
                              );
                            }
                            if (String(extractedVal).startsWith('CONFLICT:')) {
                              return (
                                <>
                                  <span className="badge badge-danger mr-1" style={{ fontSize: '0.65rem' }}>CONFLICT</span>
                                  <span className="text-danger">{extractedVal}</span>
                                </>
                              );
                            }
                            return extractedVal;
                          })()}
                        </div>
                      </td>

                      {/* 4. Validation */}
                      <td>
                        {isNetQty ? (
                          <div className="qty-validation-inline">
                            <div className="qty-inline-row">
                              <span className="qty-inline-label">Quantity:</span>
                              <span className={`qty-inline-val ${netQtyDecomposition.qtyValid ? 'valid' : (netQtyDecomposition.qtyPresent ? 'invalid' : 'missing')}`}>
                                {netQtyDecomposition.qtyValid ? 'VALID' : (netQtyDecomposition.qtyPresent ? 'INVALID' : 'MISSING')}
                              </span>
                            </div>
                            <div className="qty-inline-row">
                              <span className="qty-inline-label">Unit:</span>
                              <span className={`qty-inline-val ${netQtyDecomposition.unitValid ? 'valid' : 'missing'}`}>
                                {netQtyDecomposition.unitValid ? 'VALID' : 'MISSING'}
                              </span>
                            </div>
                            <div className="qty-inline-row">
                              <span className="qty-inline-label">Pair:</span>
                              <span className={`qty-inline-val ${netQtyDecomposition.pairValid ? 'valid' : 'invalid'}`}>
                                {netQtyDecomposition.pairValid ? 'VALID' : 'INVALID'}
                              </span>
                            </div>
                          </div>
                        ) : (
                          <span className="validation-method-badge">
                            {rule.validation_method || rule.evidence_data?.validation_method || (rule.evidence_required !== false ? 'DETERMINISTIC_CHECK' : 'PRESENCE_CHECK')}
                          </span>
                        )}
                      </td>

                      {/* 5. Binary */}
                      <td>
                        <span className={`binary-badge ${binary.badgeClass}`} title={binary.title}>
                          {binary.label}
                        </span>
                      </td>

                      {/* 6. Status */}
                      <td>
                        {getRuleStatusBadge(rule.status)}
                      </td>

                      {/* 7. Evidence */}
                      <td>
                        <div className="rule-evidence-info">
                          <div className="rule-evidence-source">
                            {rule.evidence_data?.source || rule.evidence_type || 'OCR'}
                          </div>
                          {rule.evidence_data?.confidence !== undefined && rule.evidence_data?.confidence !== null && (
                            <div>Conf: {(rule.evidence_data.confidence * 100).toFixed(0)}%</div>
                          )}
                          {rule.rule_reference && (
                            <div className="text-xs text-muted">{rule.rule_reference}</div>
                          )}
                        </div>
                      </td>

                      {/* 8. Reason */}
                      <td>
                        <div className="rule-reason-text">
                          {renderRuleReason(rule)}
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {ruleResults.length === 0 && (
                  <tr>
                    <td colSpan="8" className="text-center p-4 text-muted">
                      No rules evaluated for this commodity.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="text-center text-muted text-xs mt-3 mb-4">
        Inspection-support result based on available image evidence. Final legal verification remains with the authorized inspector.
      </div>
    </div>
  );
};

export default Result;
