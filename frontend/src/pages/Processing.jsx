import React, { useEffect, useState, useRef } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { CheckCircle2, Loader2, Circle, AlertOctagon, RotateCcw, ImagePlus, ArrowLeft } from 'lucide-react';
import { apiService } from '../services/api';
import ProgressStepper from '../components/ProgressStepper';
import BrandLogo from '../components/BrandLogo';
import './Processing.css';

const PIPELINE_STAGES = [
  { id: 'prep', label: 'Image Ingestion & Preprocessing', detail: 'Fidelity normalization & orientation alignment' },
  { id: 'ocr', label: 'Multi-Pass OCR Extraction', detail: 'PaddleOCR character & token detection' },
  { id: 'barcode', label: 'Barcode & Identifier Decoding', detail: 'EAN-13/UPC decoding & database lookup' },
  { id: 'association', label: 'Field & Declaration Association', detail: 'Scoping values to statutory parameters' },
  { id: 'classification', label: 'Category & Evidence Validation', detail: 'Product type & declaration corroboration' },
  { id: 'rules', label: 'Legal Metrology Rule Evaluation', detail: 'Deterministic validation against LMPC Rules, 2011' },
  { id: 'report', label: 'Report & Traceability Preparation', detail: 'Compiling findings and database record' },
];

const Processing = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { files, packageType, importStatus, previewUrls } = location.state || {};

  const [activeStageIndex, setActiveStageIndex] = useState(0);
  const [error, setError] = useState(null);
  const [uploadPercent, setUploadPercent] = useState(0);

  const hasStartedRef = useRef(false);

  useEffect(() => {
    if (!files?.length) {
      navigate('/scan');
      return;
    }

    if (hasStartedRef.current) return;
    hasStartedRef.current = true;

    // Advance stages incrementally to reflect operational phases
    const interval = setInterval(() => {
      setActiveStageIndex((curr) => {
        if (curr < PIPELINE_STAGES.length - 2) {
          return curr + 1;
        }
        return curr;
      });
    }, 1500);

    const executeInspection = async () => {
      try {
        const response = await apiService.uploadScan(
          files,
          packageType,
          importStatus,
          (progressEvent) => {
            if (progressEvent.total) {
              const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
              setUploadPercent(percent);
            }
          }
        );

        clearInterval(interval);
        setActiveStageIndex(PIPELINE_STAGES.length - 1);

        const inspectionId = response?.inspection_id ?? response?.data?.inspection_id;
        if (!inspectionId) {
          throw new Error('Inspection completed but no valid inspection ID was returned by the engine.');
        }

        // Slight pause to display completion before navigating
        setTimeout(() => {
          navigate(`/result/${inspectionId}`, { replace: true });
        }, 600);
      } catch (err) {
        clearInterval(interval);
        console.error('Inspection pipeline error:', err);
        const detail = err.response?.data?.detail || err.message || 'Pipeline analysis failed.';
        setError(detail);
      }
    };

    executeInspection();

    return () => clearInterval(interval);
  }, [files, packageType, importStatus, navigate]);

  return (
    <div className="processing-page">
      <ProgressStepper currentStep={3} />

      <div className="processing-container card">
        <div className="processing-header">
          <BrandLogo variant="mark" height={44} alt="LMAI Inspector" />
          <div className="processing-header__text">
            <h2>Inspection Screening In Progress</h2>
            <p className="text-muted text-sm">
              Analyzing {files?.length || 1} package panel{files?.length === 1 ? '' : 's'} under the Legal Metrology (Packaged Commodities) Rules, 2011
            </p>
          </div>
        </div>

        {/* Thumbnail preview strip */}
        {previewUrls?.length > 0 && (
          <div className="processing-preview-strip">
            {previewUrls.map((url, i) => (
              <div key={i} className="processing-thumbnail-box">
                <img src={url} alt={`Panel ${i + 1}`} className="processing-thumbnail" />
                <span className="thumbnail-badge">Panel {i + 1}</span>
              </div>
            ))}
          </div>
        )}

        {/* Stage-Based Progress List */}
        {!error ? (
          <div className="pipeline-stages-list">
            {PIPELINE_STAGES.map((stage, idx) => {
              const isCompleted = activeStageIndex > idx;
              const isActive = activeStageIndex === idx;
              const isPending = activeStageIndex < idx;

              return (
                <div
                  key={stage.id}
                  className={`pipeline-stage ${isCompleted ? 'pipeline-stage--completed' : ''} ${
                    isActive ? 'pipeline-stage--active' : ''
                  } ${isPending ? 'pipeline-stage--pending' : ''}`}
                >
                  <div className="stage-icon-box">
                    {isCompleted && <CheckCircle2 size={18} className="text-success" />}
                    {isActive && <Loader2 size={18} className="spinner-icon text-primary" />}
                    {isPending && <Circle size={18} className="text-dim" />}
                  </div>
                  <div className="stage-info">
                    <span className="stage-title">{stage.label}</span>
                    <span className="stage-detail">{stage.detail}</span>
                  </div>
                  <div className="stage-status-text font-mono">
                    {isCompleted ? 'COMPLETED' : isActive ? 'PROCESSING' : 'QUEUED'}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          /* Error State Recovery */
          <div className="processing-error-state">
            <div className="error-icon-box">
              <AlertOctagon size={36} className="text-danger" />
            </div>
            <h3 className="error-title">Inspection Pipeline Error</h3>
            <p className="error-message">{error}</p>
            <div className="error-guidance text-xs text-muted">
              Package images may be corrupted, unreadable, or the backend service encountered an unexpected error.
            </div>
            <div className="error-actions mt-4">
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => navigate('/scan')}
              >
                <RotateCcw size={15} /> Try Inspection Again
              </button>
              <Link to="/scan" className="btn btn-outline">
                <ImagePlus size={15} /> Select Alternative Images
              </Link>
            </div>
          </div>
        )}

        <div className="processing-footer text-xs text-muted">
          {typeof window !== 'undefined' &&
           (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') &&
           (!import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_BASE_URL.includes('localhost') || import.meta.env.VITE_API_BASE_URL.includes('127.0.0.1'))
            ? 'Analysis processed by the local inspection server.'
            : 'Analysis is processed by the configured LMAI Inspector inspection service.'}
        </div>
      </div>
    </div>
  );
};

export default Processing;
