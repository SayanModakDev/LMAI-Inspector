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
  actual_measured_weight: '', actual_weight_unit: '', field_overrides: {}
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
        actual_measured_weight: '', actual_weight_unit: '', field_overrides: {}
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
      // Refresh data
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
      
      // refresh to get report object in inspection data
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

  const resultBadgeClass = {
    'COMPLIANT': 'badge-success',
    'NON-COMPLIANT': 'badge-danger',
    'NON_COMPLIANT': 'badge-danger',
    'NEEDS_REVIEW': 'badge-warning'
  }[inspection.overall_result] || 'badge-gray';

  return (
    <div className="result-container">
      <div className="result-header">
        <div className="title-section">
          <h1>Inspection Result #{inspection.id}</h1>
          <span className={`badge result-badge ${resultBadgeClass}`}>{inspection.overall_result}</span>
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

      <div className="result-grid">
        {/* Left Column: Image and Summary */}
        <div className="result-left">
          <div className="card mb-4">
            <div className="card-header">Uploaded Product Images</div>
            <div className="card-body p-0">
              {uploadedImages.map((image, index) => (
                <img
                  key={image.image_path || index}
                  src={image.image_path?.startsWith('/uploads/') ? image.image_path : `/uploads/${image.image_path}`}
                  alt={`Product image ${index + 1}`}
                  className="result-image"
                  onError={(e) => { e.target.style.display = 'none'; }}
                />
              ))}
            </div>
          </div>
          
          <div className="card">
            <div className="card-header">Inspection Details</div>
            <div className="card-body">
              <table className="detail-table">
                <tbody>
                  <tr><th>Date:</th><td>{new Date(inspection.created_at).toLocaleString()}</td></tr>
                  <tr><th>Category:</th><td>{inspection.category}</td></tr>
                  <tr><th>Product Type:</th><td>{inspection.product_type || 'UNKNOWN'}</td></tr>
                  <tr><th>Brand:</th><td>{inspection.brand || inspection.product?.brand || 'Not detected'}</td></tr>
                  <tr><th>Product Name:</th><td>{inspection.product_name || inspection.product?.product_name || 'Not detected'}</td></tr>
                  <tr><th>Package Type:</th><td>{inspection.package_type}</td></tr>
                  <tr><th>Import Status:</th><td>{inspection.import_status}</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right Column: Extracted Data and Rules */}
        <div className="result-right">
          
          {barcode && (
            <div className="card mb-4">
              <div className="card-header">Barcode Lookup</div>
              <div className="card-body">
                <table className="detail-table">
                  <tbody>
                    <tr><th>Code:</th><td>{barcode.value || 'Not detected'}</td></tr>
                    <tr><th>Detection:</th><td>{barcode.source === 'OCR_BARCODE_TEXT' ? 'OCR fallback' : barcode.type || 'Unknown'}</td></tr>
                    <tr><th>Product lookup:</th><td>{barcode.lookup?.status || 'Not performed'}</td></tr>
                    {barcode.lookup?.product_name && <tr><th>Product name:</th><td>{barcode.lookup.product_name}</td></tr>}
                    {barcode.lookup?.brands && <tr><th>Brand:</th><td>{barcode.lookup.brands}</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="card mb-4">
            <div className="card-header">Product Identification</div>
            <div className="card-body">
              <table className="detail-table"><tbody>
                <tr><th>Brand:</th><td>{inspection.brand || inspection.product?.brand || 'Not detected'}</td></tr>
                <tr><th>Product:</th><td>{inspection.product_name || inspection.product?.product_name || 'Not detected'}</td></tr>
                <tr><th>Generic name:</th><td>{inspection.product?.generic_name || inspection.extracted_fields.find(f => f.field_name === 'GENERIC_NAME')?.field_value || 'Not detected'}</td></tr>
                <tr><th>Barcode:</th><td>{barcode?.value || inspection.extracted_fields.find(f => f.field_name === 'BARCODE')?.field_value || 'Not detected'}</td></tr>
              </tbody></table>
            </div>
          </div>

          {/* Extracted Data Card */}
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
                    {/* Product identity */}
                    <tr>
                      <td><strong>Product Name</strong></td>
                      <td>{inspection.extracted_fields.find(f => f.field_name === 'PRODUCT_NAME')?.field_value || 'Not Found'}</td>
                      {isEditing && <td><input className="form-control" value={manualData.field_overrides.PRODUCT_NAME ?? ''} onChange={(e) => setManualData({...manualData, field_overrides: {...manualData.field_overrides, PRODUCT_NAME: e.target.value}})} placeholder="Correct product name" /></td>}
                    </tr>

                    {/* MRP */}
                    <tr>
                      <td><strong>MRP</strong></td>
                      <td>{inspection.extracted_fields.find(f => f.field_name === 'MRP')?.field_value || 'Not Found'}</td>
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
                    
                    {/* Net Qty */}
                    <tr>
                      <td>
                        <strong>Declared Net Quantity</strong>
                        <div className="text-xs text-muted" style={{ fontSize: '0.75rem', color: '#6b7280' }}>Printed label declaration (OCR)</div>
                      </td>
                      <td>
                        <div>{inspection.extracted_fields.find(f => f.field_name === 'DECLARED_NET_QUANTITY')?.field_value || 'Not Found'}</div>
                      </td>
                      {isEditing && (
                        <td>
                          <input 
                            type="text" 
                            className="form-control" 
                            value={manualData.field_overrides.DECLARED_NET_QUANTITY ?? ''}
                            onChange={(e) => setManualData({...manualData, field_overrides: {...manualData.field_overrides, DECLARED_NET_QUANTITY: e.target.value}})}
                            placeholder="Correct declared quantity"
                          />
                        </td>
                      )}
                    </tr>
                    
                    {/* Mfg/Pkg Date */}
                    <tr>
                      <td><strong>Mfg/Pkg Date</strong></td>
                      <td>{inspection.extracted_fields.find(f => f.field_name === 'MONTH_YEAR_MANUFACTURE')?.field_value || 'Not Found'}</td>
                      {isEditing && (
                        <td>
                          <input 
                            type="text" 
                            className="form-control" 
                            value={manualData.field_overrides.MONTH_YEAR_MANUFACTURE ?? manualData.field_overrides.PACKING_DATE ?? ''}
                            onChange={(e) => setManualData({...manualData, field_overrides: {...manualData.field_overrides, MONTH_YEAR_MANUFACTURE: e.target.value}})}
                            placeholder="Correct printed date"
                          />
                        </td>
                      )}
                    </tr>
                    <tr>
                      <td><strong>Generic Name</strong></td>
                      <td>{inspection.extracted_fields.find(f => f.field_name === 'GENERIC_NAME')?.field_value || 'Not Found'}</td>
                      {isEditing && <td><input className="form-control" value={manualData.field_overrides.GENERIC_NAME ?? ''} onChange={(e) => setManualData({...manualData, field_overrides: {...manualData.field_overrides, GENERIC_NAME: e.target.value}})} placeholder="Correct generic name" /></td>}
                    </tr>
                  </tbody>
                </table>
              </div>
              <div className="mt-3">
                {inspection.extracted_fields.filter((field) => !['PRODUCT_NAME', 'MRP', 'DECLARED_NET_QUANTITY', 'MONTH_YEAR_MANUFACTURE', 'GENERIC_NAME'].includes(field.field_name)).map((field) => (
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

          <div className="card mb-4">
            <div className="card-header">Inspection Findings</div>
            <div className="card-body">
              {inspection.findings?.verified?.map((item, index) => <p key={`verified-${index}`} className="text-success">✓ {item}</p>)}
              {inspection.findings?.needs_review?.map((item, index) => <p key={`review-${index}`} className="text-warning">⚠ {item}</p>)}
              {inspection.findings?.failed?.map((item, index) => <p key={`failed-${index}`} className="text-danger">✕ {item}</p>)}
            </div>
          </div>

          {/* Rule Evaluation Card */}
          <div className="card">
            <div className="card-header">Compliance Rules Evaluation</div>
            <div className="card-body p-0">
              <table className="rule-table">
                <thead>
                  <tr>
                    <th>Parameter</th>
                    <th>Status</th>
                    <th>Source</th>
                    <th>Evidence</th>
                    <th>Confidence</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {inspection.rule_results.map((rule, idx) => (
                    <tr key={idx}>
                      <td className="font-medium">{rule.parameter}</td>
                      <td>
                        {rule.status === 'PASS' && <span className="badge badge-success"><CheckCircle size={12} className="mr-1"/> PASS</span>}
                        {rule.status === 'FAIL' && <span className="badge badge-danger"><XCircle size={12} className="mr-1"/> FAIL</span>}
                        {rule.status === 'MANUAL_CHECK' && <span className="badge badge-warning"><AlertTriangle size={12} className="mr-1"/> REVIEW</span>}
                        {rule.status === 'NOT_VERIFIABLE' && <span className="badge badge-warning"><AlertTriangle size={12} className="mr-1"/> NOT VERIFIABLE</span>}
                        {rule.status === 'NOT_APPLICABLE' && <span className="badge badge-gray">NOT APPLICABLE</span>}
                        {rule.binary !== undefined && rule.binary !== null && (
                          <span className="badge badge-gray ml-1" title="Binary Compliance Score" style={{ fontSize: '0.7rem', padding: '1px 5px' }}>
                            Score: {rule.binary}
                          </span>
                        )}
                      </td>
                      <td className="text-sm">{rule.regulatory_source || 'LEGAL_METROLOGY'}</td>
                      <td className="text-sm">{rule.evidence_data?.value || '—'}</td>
                      <td className="text-sm">{rule.evidence_data?.confidence ?? '—'}</td>
                      <td className="text-sm">{rule.regulatory_source ? `${rule.regulatory_source}: ` : ''}{rule.message}</td>
                    </tr>
                  ))}
                  {inspection.rule_results.length === 0 && (
                    <tr><td colSpan="6" className="text-center">No rules evaluated.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

        </div>
      </div>
      <p className="text-muted mt-3">AI-assisted screening tool. Final legal verification must be made by an authorized inspector.</p>
    </div>
  );
};

export default Result;
