import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  UploadCloud,
  Camera,
  Image as ImageIcon,
  AlertCircle,
  Trash2,
  CheckCircle2,
  FileText,
  Info,
  Layers,
  ArrowRight,
} from 'lucide-react';
import ProgressStepper from '../components/ProgressStepper';
import './Scan.css';

const PACKAGE_TYPE_GUIDANCE = {
  RETAIL: 'Retail-package declaration set applies.',
  WHOLESALE: 'Wholesale-package declaration set applies; retail-only declarations may be not applicable.',
  INSTITUTIONAL: 'Retail packaged-commodity screening requirements are excluded where applicable.',
};

const Scan = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const fileInputRef = useRef(null);
  const videoRef = useRef(null);
  const streamRef = useRef(null);

  const [files, setFiles] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [packageType, setPackageType] = useState('RETAIL');
  const [importStatus, setImportStatus] = useState('DOMESTIC');
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [error, setError] = useState(null);

  // Stop camera stream utility
  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setIsCameraOpen(false);
  };

  useEffect(() => {
    return () => stopCamera();
  }, []);

  // Check URL query parameters for auto-opening camera
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    if (params.get('camera') === 'true') {
      openCamera();
    }
  }, [location.search]);

  const openCamera = async () => {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Camera access is not supported in this browser.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      });
      streamRef.current = stream;
      setIsCameraOpen(true);
      requestAnimationFrame(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      });
    } catch (err) {
      setError(
        err.name === 'NotAllowedError'
          ? 'Camera permission denied. Please grant browser camera permissions.'
          : 'Unable to initialize device camera.'
      );
    }
  };

  const capturePhoto = () => {
    const video = videoRef.current;
    if (!video || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      setError('Camera stream not ready yet. Please try again.');
      return;
    }

    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 720;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(
      (blob) => {
        if (!blob) {
          setError('Failed to capture frame from camera.');
          return;
        }
        const file = new File([blob], `package_panel_${Date.now()}.jpg`, { type: 'image/jpeg' });
        setFiles((curr) => [...curr, file]);
        setPreviews((curr) => [...curr, URL.createObjectURL(file)]);
        stopCamera();
        setError(null);
      },
      'image/jpeg',
      0.95
    );
  };

  const addFiles = (selectedFiles) => {
    const valid = Array.from(selectedFiles || []).filter((f) => f.type.startsWith('image/'));
    if (valid.length === 0) {
      setError('Please upload standard image formats (JPEG, PNG, WebP).');
      return;
    }

    setFiles((curr) => [...curr, ...valid]);
    setPreviews((curr) => [...curr, ...valid.map((f) => URL.createObjectURL(f))]);
    setError(null);
  };

  const removeFile = (index) => {
    setFiles((curr) => curr.filter((_, i) => i !== index));
    setPreviews((curr) => curr.filter((_, i) => i !== index));
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files?.length) {
      addFiles(e.dataTransfer.files);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (files.length === 0) {
      setError('Please provide at least one package image to proceed.');
      return;
    }

    navigate('/processing', {
      state: {
        files,
        packageType,
        importStatus,
        previewUrls: previews,
      },
    });
  };

  return (
    <div className="scan-page">
      {/* 5-Step Workflow Stepper */}
      <ProgressStepper currentStep={files.length > 0 ? 2 : 1} />

      <div className="scan-header-bar">
        <div>
          <h2 className="scan-title">Capture & Package Ingestion</h2>
          <p className="scan-subtitle">
            Upload package panels, label close-ups, or mandatory declaration areas for Legal Metrology (Packaged Commodities) Rules, 2011 screening.
          </p>
        </div>
        <div className="scan-badge-counter">
          <span className="badge badge-primary font-mono">{files.length} Panel{files.length === 1 ? '' : 's'} Staged</span>
        </div>
      </div>

      {error && (
        <div className="scan-error-alert" role="alert">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      <div className="scan-workstation-grid">
        {/* Left: Image Ingestion Station */}
        <div className="scan-capture-col">
          {/* Camera Viewfinder Modal / Panel */}
          {isCameraOpen ? (
            <div className="card camera-card">
              <div className="card-header">
                <span>Live Camera Viewfinder</span>
                <span className="badge badge-warning">Active Capture</span>
              </div>
              <div className="card-body p-0 camera-viewport">
                <video ref={videoRef} autoPlay playsInline muted className="camera-feed" />
                <div className="camera-overlay-crosshairs" />
              </div>
              <div className="card-footer flex justify-between">
                <button type="button" className="btn btn-outline" onClick={stopCamera}>
                  Cancel
                </button>
                <button type="button" className="btn btn-primary" onClick={capturePhoto}>
                  <Camera size={16} /> Capture Frame
                </button>
              </div>
            </div>
          ) : (
            /* Standard Drag & Drop Ingestion Zone */
            <div
              className="upload-dropzone"
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
            >
              <div className="upload-dropzone__icon">
                <UploadCloud size={44} strokeWidth={1.5} />
              </div>
              <h3 className="upload-dropzone__title">Add Package Images</h3>
              <p className="upload-dropzone__subtitle">
                Drag and drop image panels here, or browse local files. Multi-angle captures recommended for complete rule coverage.
              </p>

              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/jpeg,image/png,image/webp"
                style={{ display: 'none' }}
                onChange={(e) => {
                  if (e.target.files) addFiles(e.target.files);
                  e.target.value = '';
                }}
              />

              <div className="upload-dropzone__buttons">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <ImageIcon size={15} /> Select Images
                </button>
                <button type="button" className="btn btn-outline" onClick={openCamera}>
                  <Camera size={15} /> Open Camera
                </button>
              </div>

              <div className="upload-dropzone__formats text-xs text-muted mt-3">
                Accepted: JPEG, PNG, WebP • High resolution recommended (≥1000px)
              </div>
            </div>
          )}

          {/* Staged Image Panels List */}
          {files.length > 0 && (
            <div className="staged-panels-container mt-4">
              <div className="staged-panels-header">
                <span className="font-semibold text-sm">Staged Package Panels ({files.length})</span>
                <span className="text-xs text-muted">All panels will be scoped jointly</span>
              </div>

              <div className="panels-grid">
                {files.map((file, idx) => (
                  <div key={idx} className="panel-card">
                    <div className="panel-card__preview">
                      <img src={previews[idx]} alt={`Panel ${idx + 1}`} className="panel-thumbnail" />
                      <span className="panel-badge">Panel {idx + 1}</span>
                      <button
                        type="button"
                        className="panel-remove-btn"
                        onClick={() => removeFile(idx)}
                        title="Remove panel"
                        aria-label={`Remove panel ${idx + 1}`}
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                    <div className="panel-card__meta">
                      <span className="panel-filename" title={file.name}>{file.name}</span>
                      <div className="panel-submeta">
                        <span className="font-mono">{(file.size / 1024).toFixed(0)} KB</span>
                        <span className="panel-status-pill">
                          <CheckCircle2 size={11} className="text-success" /> Ready
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right: Inspection Scope Parameters */}
        <div className="scan-params-col">
          <div className="card">
            <div className="card-header flex-between">
              <div className="flex items-center gap-2">
                <Layers size={16} className="text-primary" />
                <span>Inspection Scope Parameters</span>
              </div>
              <span className="badge badge-gray font-mono">User Configured</span>
            </div>

            <div className="card-body">
              <form onSubmit={handleSubmit}>
                <div className="scope-input-section">
                  <div className="text-xs text-muted leading-relaxed">
                    <span className="font-semibold text-main">Scope Scaffolding:</span> These parameters reflect operational context specified by the user to configure applicable rule sets. Declarations (MRP, Net Qty, Dates) will be detected automatically by the OCR engine.
                  </div>

                  <div className="form-group mb-0">
                    <label className="form-label flex-between items-center mb-1">
                      <span className="font-semibold">Package Classification</span>
                      <span className="scope-badge">Inspection Scope • User supplied</span>
                    </label>
                    <select
                      className="form-control"
                      value={packageType}
                      onChange={(e) => setPackageType(e.target.value)}
                    >
                      <option value="RETAIL">Retail Package (Direct Consumer Sale)</option>
                      <option value="WHOLESALE">Wholesale Package (Commercial Distribution)</option>
                      <option value="INSTITUTIONAL">Institutional / Industrial Consumption</option>
                    </select>
                    <span className="form-help">
                      {PACKAGE_TYPE_GUIDANCE[packageType] || PACKAGE_TYPE_GUIDANCE.RETAIL}
                    </span>
                  </div>

                  <div className="form-group mb-0">
                    <label className="form-label flex-between items-center mb-1">
                      <span className="font-semibold">Import Status</span>
                      <span className="scope-badge">Inspection Scope • User supplied</span>
                    </label>
                    <select
                      className="form-control"
                      value={importStatus}
                      onChange={(e) => setImportStatus(e.target.value)}
                    >
                      <option value="DOMESTIC">Domestic Commodity</option>
                      <option value="IMPORTED">Imported Commodity (Overseas Manufacturing)</option>
                    </select>
                    <span className="form-help">
                      For inspection scoping only; origin/manufacturing declarations are evaluated from package evidence.
                    </span>
                  </div>
                </div>

                <div className="statutory-notice-box mb-4">
                  <Info size={16} className="notice-icon" />
                  <div className="notice-text text-xs">
                    <strong>Operational Notice:</strong> All staged images will be evaluated simultaneously. Multi-panel evidence is merged to prevent false non-compliances when declarations appear on different faces.
                  </div>
                </div>

                <button
                  type="submit"
                  className="btn btn-primary btn-lg full-width"
                  disabled={files.length === 0}
                >
                  Proceed to Analysis ({files.length} Panel{files.length === 1 ? '' : 's'}) <ArrowRight size={16} />
                </button>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Scan;
