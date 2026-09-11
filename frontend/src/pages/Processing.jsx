import React, { useEffect, useState, useRef } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { CheckCircle2, Loader2, Circle, AlertOctagon, RotateCcw, ImagePlus } from 'lucide-react';
import { apiService } from '../services/api';
import ProgressStepper from '../components/ProgressStepper';
import BrandLogo from '../components/BrandLogo';
import './Processing.css';

const PIPELINE_STAGES = [
  {
    id: 'prep',
    label: 'Image Ingestion & Preprocessing',
    detail: 'Validating payload, image normalization & panel alignment',
  },
  {
    id: 'ocr',
    label: 'OCR & Token Extraction',
    detail: 'PaddleOCR character & token detection across panels',
  },
  {
    id: 'evidence',
    label: 'Evidence & Barcode Decoding',
    detail: 'Barcode lookup & multi-panel evidence aggregation',
  },
  {
    id: 'association',
    label: 'Parameter & Semantic Association',
    detail: 'Associating candidates with statutory parameters',
  },
  {
    id: 'rules',
    label: 'Deterministic Rule Validation',
    detail: 'Evaluating LMPC Rules, 2011 compliance matrix',
  },
  {
    id: 'final',
    label: 'Inspection Finalization',
    detail: 'Compiling findings, audit provenance & report record',
  },
];

const Processing = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { files, packageType, importStatus, previewUrls } = location.state || {};

  const [activeStageIndex, setActiveStageIndex] = useState(0);
  const [error, setError] = useState(null);
  const [errorStageIndex, setErrorStageIndex] = useState(null);
  const [uploadPercent, setUploadPercent] = useState(0);

  const hasStartedRef = useRef(false);
  const isMountedRef = useRef(true);
  const stageIntervalRef = useRef(null);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (stageIntervalRef.current) clearInterval(stageIntervalRef.current);
    };
  }, []);

  useEffect(() => {
    if (!files?.length) {
      navigate('/scan');
      return;
    }

    if (hasStartedRef.current) return;
    hasStartedRef.current = true;

    // Helper to fast-forward through remaining stages before final navigation
    const fastForwardRemainingStages = async (fromIdx, inspectionId) => {
      let currentIdx = fromIdx;
      while (currentIdx < PIPELINE_STAGES.length) {
        if (!isMountedRef.current) return;
        currentIdx += 1;
        setActiveStageIndex(currentIdx);
        await new Promise((resolve) => setTimeout(resolve, 140));
      }
      if (!isMountedRef.current) return;
      setTimeout(() => {
        if (isMountedRef.current) {
          navigate(`/result/${inspectionId}`, { replace: true });
        }
      }, 350);
    };

    const executeInspection = async () => {
      let currentStage = 0;

      // Start sequential ticker once upload begins
      stageIntervalRef.current = setInterval(() => {
        if (!isMountedRef.current) return;
        setActiveStageIndex((curr) => {
          // Allow ticker to advance through stages 1 to 4 while server is crunching
          if (curr < 4) {
            currentStage = curr + 1;
            return currentStage;
          }
          return curr;
        });
      }, 550);

      try {
        const response = await apiService.uploadScan(
          files,
          packageType,
          importStatus,
          (progressEvent) => {
            if (progressEvent.total && isMountedRef.current) {
              const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
              setUploadPercent(percent);
            }
          }
        );

        if (stageIntervalRef.current) {
          clearInterval(stageIntervalRef.current);
          stageIntervalRef.current = null;
        }

        const inspectionId = response?.inspection_id ?? response?.data?.inspection_id;
        if (!inspectionId) {
          throw new Error('Inspection completed but no valid inspection ID was returned by the engine.');
        }

        // Fast-forward sequentially through the remaining stages smoothly
        setActiveStageIndex((latestStage) => {
          fastForwardRemainingStages(latestStage, inspectionId);
          return latestStage;
        });
      } catch (err) {
        if (stageIntervalRef.current) {
          clearInterval(stageIntervalRef.current);
          stageIntervalRef.current = null;
        }
        console.error('Inspection pipeline error:', err);
        const detail = err.response?.data?.detail || err.message || 'Pipeline analysis failed.';
        if (isMountedRef.current) {
          setActiveStageIndex((curr) => {
            setErrorStageIndex(curr);
            return curr;
          });
          setError(detail);
        }
      }
    };

    executeInspection();
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
          <div className="pipeline-stages-list" role="status" aria-live="polite">
            {PIPELINE_STAGES.map((stage, idx) => {
              const isCompleted = activeStageIndex > idx;
              const isActive = activeStageIndex === idx;
              const isPending = activeStageIndex < idx;

              // Display live upload progress during Stage 0 if still uploading
              let stageDetailText = stage.detail;
              if (idx === 0 && isActive && uploadPercent > 0 && uploadPercent < 100) {
                stageDetailText = `Uploading package images: ${uploadPercent}%`;
              } else if (idx === 0 && isCompleted) {
                stageDetailText = 'Package images uploaded & normalized successfully';
              }

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
                    <span className="stage-detail">{stageDetailText}</span>
                    {idx === 0 && isActive && uploadPercent > 0 && uploadPercent < 100 && (
                      <div className="upload-progress-bar-container">
                        <div
                          className="upload-progress-bar"
                          style={{ width: `${uploadPercent}%` }}
                        />
                      </div>
                    )}
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
