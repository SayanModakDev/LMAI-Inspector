import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, Camera, Image as ImageIcon, AlertCircle } from 'lucide-react';
import { apiService } from '../services/api';
import './Scan.css';

const Scan = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  
  const [files, setFiles] = useState([]);
  const [previews, setPreviews] = useState([]);
  const [packageType, setPackageType] = useState('RETAIL');
  const [importStatus, setImportStatus] = useState('DOMESTIC');
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [capturedFromCamera, setCapturedFromCamera] = useState(false);
  
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState(null);

  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setIsCameraOpen(false);
  };

  useEffect(() => () => stopCamera(), []);

  const openCamera = async () => {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Camera access is not available in this browser.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' } },
        audio: false,
      });
      streamRef.current = stream;
      setIsCameraOpen(true);
      requestAnimationFrame(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      });
    } catch (cameraError) {
      const message = cameraError.name === 'NotAllowedError'
        ? 'Camera permission was denied. Allow camera access and try again.'
        : 'Unable to open the camera on this device.';
      setError(message);
    }
  };

  const capturePhoto = () => {
    const video = videoRef.current;
    if (!video || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      setError('The camera is not ready yet. Please try again.');
      return;
    }

    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (!blob) {
        setError('Could not capture a photo. Please try again.');
        return;
      }
      const capturedFile = new File([blob], `camera_capture_${Date.now()}.jpg`, {
        type: 'image/jpeg',
      });
      setFiles((current) => [...current, capturedFile]);
      setPreviews((current) => [...current, URL.createObjectURL(capturedFile)]);
      setCapturedFromCamera(true);
      stopCamera();
      setError(null);
    }, 'image/jpeg', 0.92);
  };

  const addFiles = (selectedFiles) => {
    const selected = Array.from(selectedFiles || []);
    if (selected.some((item) => !item.type.startsWith('image/'))) {
      setError('Please select valid image files.');
      return;
    }
    setFiles((current) => [...current, ...selected]);
    setPreviews((current) => [...current, ...selected.map((item) => URL.createObjectURL(item))]);
    setCapturedFromCamera(false);
    setError(null);
  };

  const handleFileChange = (e) => {
    addFiles(e.target.files);
    e.target.value = '';
  };

  const handleDrop = (e) => {
    e.preventDefault();
    addFiles(e.dataTransfer.files);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!files.length) {
      setError('Please select at least one image.');
      return;
    }

    setIsUploading(true);
    setError(null);
    
    // Pass progress state to navigate to Processing page
    navigate('/processing', { 
      state: { files, packageType, importStatus, previewUrls: previews }
    });
  };

  return (
    <div className="scan-container">
      <div className="scan-header">
        <h1>New Inspection Scan</h1>
        <p className="text-muted">Add every useful product view, close-up, panel, or package side to one inspection.</p>
      </div>

      <div className="scan-content">
        <div className="card">
          <div className="card-header">Product Images</div>
          <div className="card-body">
            {isCameraOpen ? (
              <div className="camera-panel">
                <video ref={videoRef} autoPlay playsInline muted className="camera-preview" />
                <p className="camera-target">Capture another product image</p>
                <div className="upload-actions camera-actions">
                  <button type="button" className="btn btn-primary" onClick={capturePhoto}>
                    <Camera size={16} /> Capture Photo
                  </button>
                  <button type="button" className="btn btn-outline" onClick={stopCamera}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div
                className="upload-zone product-images-zone"
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDrop}
              >
                <div className="upload-icon">
                  <UploadCloud size={48} />
                </div>
                <h3>Add product images</h3>
                <p>Upload multiple images or capture as many camera images as needed.</p>
                <input 
                  type="file" 
                  ref={fileInputRef} 
                  onChange={handleFileChange} 
                  accept="image/*" 
                  multiple
                  className="hidden-input" 
                />
                <div className="upload-actions">
                  <button type="button" className="btn btn-primary" onClick={() => fileInputRef.current?.click()}>
                    <ImageIcon size={16} /> Add Images
                  </button>
                  <button type="button" className="btn btn-outline" onClick={openCamera}>
                    <Camera size={16} /> Camera
                  </button>
                </div>
                {previews.length > 0 && <div className="selected-images-heading">Selected Images ({previews.length})</div>}
                <div className="image-previews">
                  {previews.map((previewUrl, index) => (
                    <div className="image-preview-item" key={previewUrl}>
                      <img src={previewUrl} alt={`Product image ${index + 1}`} className="image-preview" />
                      <button type="button" className="image-remove" aria-label={`Remove image ${index + 1}`} onClick={() => {
                        setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index));
                        setPreviews((current) => current.filter((_, itemIndex) => itemIndex !== index));
                      }}>X</button>
                      <span>Image {index + 1}</span>
                    </div>
                  ))}
                </div>
                {previews.length > 0 && <button type="button" className="btn btn-outline add-more-button" onClick={() => fileInputRef.current?.click()}><ImageIcon size={16} /> Add More Images</button>}
              </div>
            )}
            
            {error && (
              <div className="error-message">
                <AlertCircle size={16} />
                <span>{error}</span>
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-header">Inspection Parameters</div>
          <div className="card-body">
            <form onSubmit={handleSubmit} className="scan-form">
              <div className="form-group">
                <label className="form-label">Package Type</label>
                <select 
                  className="form-control" 
                  value={packageType} 
                  onChange={(e) => setPackageType(e.target.value)}
                >
                  <option value="RETAIL">Retail Package (For direct consumer sale)</option>
                  <option value="WHOLESALE">Wholesale Package</option>
                  <option value="INSTITUTIONAL">Institutional / Industrial</option>
                </select>
                <small className="form-help">Determines which rules are applicable (e.g., MRP is mandatory for Retail).</small>
              </div>
              
              <div className="form-group">
                <label className="form-label">Origin Status</label>
                <select 
                  className="form-control" 
                  value={importStatus} 
                  onChange={(e) => setImportStatus(e.target.value)}
                >
                  <option value="DOMESTIC">Domestic (Manufactured in India)</option>
                  <option value="IMPORTED">Imported</option>
                </select>
                <small className="form-help">Imported products require specific importer details and Country of Origin.</small>
              </div>

              <div className="form-actions">
                <button 
                  type="submit" 
                  className="btn btn-primary btn-lg full-width"
                  disabled={!files.length || isUploading}
                >
                  {isUploading ? 'Processing...' : 'Analyze Label'}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Scan;
