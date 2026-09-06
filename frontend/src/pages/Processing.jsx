import { useEffect, useState, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ShieldAlert, CheckCircle, Loader2 } from 'lucide-react';
import { apiService } from '../services/api';
import './Processing.css';

const Processing = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { files, packageType, importStatus, previewUrls } = location.state || {};

  const [status, setStatus] = useState('Analyzing images...');
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);

  const hasStarted = useRef(false);

  useEffect(() => {
    if (!files?.length) {
      navigate('/scan');
      return;
    }

    if (hasStarted.current) return;
    hasStarted.current = true;
    const phases = ['Analyzing images...', 'OCR...', 'Extracting declarations...', 'Checking compliance...', 'Generating result...'];
    let phase = 0;
    const phaseTimer = window.setInterval(() => {
      phase = Math.min(phase + 1, phases.length - 1);
      setStatus(phases[phase]);
      setProgress((current) => Math.max(current, Math.min(94, 15 + phase * 18)));
    }, 1800);

    const processImage = async () => {
      try {
        const response = await apiService.uploadScan(
          files,
          packageType,
          importStatus,
          (progressEvent) => {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setProgress(Math.min(percentCompleted, 90));
            if (percentCompleted >= 100) {
              setStatus('OCR...');
            }
          }
        );

        const inspectionId = response?.inspection_id ?? response?.data?.inspection_id;
        if (!inspectionId) {
          throw new Error('Scan completed but the server did not return a valid inspection ID.');
        }

        setProgress(100);
        window.clearInterval(phaseTimer);
        setStatus('Generating result...');
        navigate(`/result/${inspectionId}`, { replace: true });
      } catch (err) {
        console.error('Scan error:', err);
        window.clearInterval(phaseTimer);
        setError(err.response?.data?.detail || err.message || 'Failed to process image.');
        setStatus('Failed');
      }
    };

    processImage();
    return () => window.clearInterval(phaseTimer);
  }, [files, packageType, importStatus, navigate]);

  return (
    <div className="processing-container">
      <div className="card processing-card">
        <div className="card-body text-center">
          <h2>Analyzing Label</h2>

          <div className="preview-thumbnail-container">
            {previewUrls?.map((previewUrl) => <img key={previewUrl} src={previewUrl} alt="Label thumbnail" className="preview-thumbnail" />)}

            <div className="processing-overlay">
              {!error && progress < 100 && <Loader2 className="spinner text-primary" size={48} />}
              {!error && progress === 100 && <CheckCircle className="text-success" size={48} />}
              {error && <ShieldAlert className="text-danger" size={48} />}
            </div>
          </div>

          {!error ? (
            <div className="progress-section">
              <p className="status-text">{status}</p>
              <div className="progress-bar-container">
                <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
              </div>
              <span className="progress-percentage">{progress}%</span>
            </div>
          ) : (
            <div className="error-section">
              <p className="text-danger mb-4">{error}</p>
              <button className="btn btn-outline" onClick={() => navigate('/scan')}>
                Try Again
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Processing;
