import React, { useState, useRef } from 'react';
import { Layers, ZoomIn, CheckCircle, AlertTriangle, Eye, Crosshair } from 'lucide-react';
import ConfidenceBadge from './ConfidenceBadge';
import './EvidenceViewer.css';

/**
 * Professional Split Image + Evidence Workstation Viewer
 */
const EvidenceViewer = ({
  images = [],
  extractedFields = [],
  barcodeResult = null,
  findings = null,
  className = '',
}) => {
  const [selectedImageIndex, setSelectedImageIndex] = useState(0);
  const [selectedFieldKey, setSelectedFieldKey] = useState(null);
  const [imageZoom, setImageZoom] = useState(false);
  const [imageDims, setImageDims] = useState({ width: 1000, height: 1000 });

  const imgRef = useRef(null);

  const activeImage = images[selectedImageIndex] || images[0] || null;
  const imageSrc = activeImage?.image_path
    ? (activeImage.image_path.startsWith('/uploads/') ? activeImage.image_path : `/uploads/${activeImage.image_path}`)
    : '/placeholder.jpg';

  const handleImageLoad = (e) => {
    if (e.target.naturalWidth && e.target.naturalHeight) {
      setImageDims({
        width: e.target.naturalWidth,
        height: e.target.naturalHeight,
      });
    }
  };

  // Normalize fields into an array
  const fieldsArray = Array.isArray(extractedFields)
    ? extractedFields
    : Object.entries(extractedFields || {}).map(([key, val]) => ({
        field_name: key,
        field_value: typeof val === 'object' ? val?.value : val,
        confidence: typeof val === 'object' ? val?.confidence : null,
        source: typeof val === 'object' ? val?.source : 'OCR',
        bbox: typeof val === 'object' ? val?.bbox : null,
        source_image_index: typeof val === 'object' ? val?.source_image_index : 0,
      }));

  // Find currently selected field item
  const selectedField = fieldsArray.find(
    (f) => (f.field_name || f.parameter) === selectedFieldKey
  );

  const handleSelectField = (fieldName) => {
    setSelectedFieldKey(fieldName === selectedFieldKey ? null : fieldName);
    const field = fieldsArray.find((f) => (f.field_name || f.parameter) === fieldName);
    if (field && field.source_image_index !== undefined && field.source_image_index < images.length) {
      setSelectedImageIndex(field.source_image_index);
    }
  };

  // Convert bounding box to SVG overlay coordinates
  // Handles PaddleOCR 4-point polygons [[x1, y1], [x2, y2], [x3, y3], [x4, y4]] and normalized boxes
  const renderBBoxOverlay = () => {
    if (!selectedField || !selectedField.bbox) return null;

    const bbox = selectedField.bbox;

    if (Array.isArray(bbox) && bbox.length === 4 && Array.isArray(bbox[0])) {
      // 4-point polygon format: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
      const pointsString = bbox.map((p) => `${p[0]},${p[1]}`).join(' ');
      return (
        <svg
          className="evidence-bbox-overlay"
          viewBox={`0 0 ${imageDims.width} ${imageDims.height}`}
          preserveAspectRatio="none"
        >
          <polygon points={pointsString} className="evidence-polygon-highlight" />
        </svg>
      );
    }

    if (Array.isArray(bbox) && bbox.length === 4 && typeof bbox[0] === 'number') {
      const [a, b, c, d] = bbox;
      if (a <= 1 && b <= 1 && c <= 1 && d <= 1) {
        const x = b * imageDims.width;
        const y = a * imageDims.height;
        const w = (d - b) * imageDims.width;
        const h = (c - a) * imageDims.height;
        return (
          <svg
            className="evidence-bbox-overlay"
            viewBox={`0 0 ${imageDims.width} ${imageDims.height}`}
            preserveAspectRatio="none"
          >
            <rect x={x} y={y} width={w} height={h} className="evidence-polygon-highlight" />
          </svg>
        );
      }
    }

    return null;
  };

  const formatParamName = (name) => {
    return (name || '').replace(/_/g, ' ');
  };

  return (
    <div className={`evidence-workstation ${className}`}>
      {/* LEFT: Image Inspection Canvas */}
      <div className="evidence-workstation__image-col">
        <div className="workstation-panel-header">
          <div className="flex items-center gap-2">
            <span className="panel-title">Package Imagery</span>
            <span className="badge badge-gray">{images.length} Panel{images.length === 1 ? '' : 's'}</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="btn btn-outline btn-sm"
              onClick={() => setImageZoom(!imageZoom)}
              title="Toggle zoom mode"
            >
              <ZoomIn size={13} /> {imageZoom ? 'Fit' : 'Zoom'}
            </button>
          </div>
        </div>

        {/* Panel Switcher Tabs if multiple images */}
        {images.length > 1 && (
          <div className="panel-tabs" role="tablist">
            {images.map((img, idx) => (
              <button
                key={idx}
                type="button"
                role="tab"
                aria-selected={selectedImageIndex === idx}
                className={`panel-tab ${selectedImageIndex === idx ? 'panel-tab--active' : ''}`}
                onClick={() => setSelectedImageIndex(idx)}
              >
                Panel {idx + 1}
              </button>
            ))}
          </div>
        )}

        {/* Image Stage */}
        <div className={`image-stage ${imageZoom ? 'image-stage--zoomed' : ''}`}>
          <div className="image-stage__wrapper">
            <img
              ref={imgRef}
              src={imageSrc}
              alt={`Package view ${selectedImageIndex + 1}`}
              className="image-stage__img"
              onLoad={handleImageLoad}
              onError={(e) => { e.target.style.opacity = '0.3'; }}
            />
            {renderBBoxOverlay()}
          </div>
        </div>

        <div className="workstation-image-footer">
          <div className="flex items-center gap-1 text-xs text-muted">
            <Crosshair size={12} />
            <span>Click any declaration on the right to focus its evidence</span>
          </div>
          {activeImage?.source && (
            <span className="text-xs text-muted">Source: {activeImage.source}</span>
          )}
        </div>
      </div>

      {/* RIGHT: Detected Declarations List */}
      <div className="evidence-workstation__declarations-col">
        <div className="workstation-panel-header">
          <span className="panel-title">Detected Declarations & Evidence</span>
          <span className="text-xs text-muted">{fieldsArray.length} items extracted</span>
        </div>

        <div className="declarations-list">
          {fieldsArray.map((field, idx) => {
            const fieldName = field.field_name || field.parameter;
            const fieldValue = field.field_value || field.value;
            const isSelected = selectedFieldKey === fieldName;
            const isConflict = String(fieldValue).startsWith('CONFLICT:');

            return (
              <div
                key={idx}
                className={`declaration-item ${isSelected ? 'declaration-item--selected' : ''} ${isConflict ? 'declaration-item--conflict' : ''}`}
                onClick={() => handleSelectField(fieldName)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSelectField(fieldName); }}
              >
                <div className="declaration-item__header">
                  <span className="declaration-item__label">{formatParamName(fieldName)}</span>
                  <div className="flex items-center gap-1">
                    {field.confidence !== undefined && (
                      <ConfidenceBadge confidence={field.confidence} source={field.source || 'OCR'} />
                    )}
                    {field.bbox && (
                      <span className="badge badge-primary" title="Bounding box available">BBox</span>
                    )}
                  </div>
                </div>

                <div className="declaration-item__value font-mono">
                  {fieldValue || <span className="text-muted italic">Not detected on package</span>}
                </div>

                {isSelected && (
                  <div className="declaration-item__details">
                    <div className="detail-row">
                      <span className="detail-label">Source View:</span>
                      <span className="detail-val">Panel {(field.source_image_index || 0) + 1}</span>
                    </div>
                    <div className="detail-row">
                      <span className="detail-label">Extraction:</span>
                      <span className="detail-val">{field.extraction_method || field.source || 'OCR Rule Scoper'}</span>
                    </div>
                    {field.bbox && (
                      <div className="detail-row">
                        <span className="detail-label">Location:</span>
                        <span className="detail-val">Highlighted on active panel</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {/* Barcode Auxiliary Item */}
          {barcodeResult && barcodeResult.value && (
            <div className="declaration-item declaration-item--barcode">
              <div className="declaration-item__header">
                <span className="declaration-item__label">SUPPLEMENTARY BARCODE</span>
                <span className="badge badge-gray">{barcodeResult.source === 'OCR_BARCODE_TEXT' ? 'OCR Fallback' : 'PyZbar'}</span>
              </div>
              <div className="declaration-item__value font-mono">{barcodeResult.value}</div>
              {barcodeResult.lookup?.product_name && (
                <div className="text-xs text-muted mt-1">
                  Database Record: <strong>{barcodeResult.lookup.product_name}</strong>
                </div>
              )}
            </div>
          )}

          {fieldsArray.length === 0 && (
            <div className="p-4 text-center text-muted">
              No declarations detected by OCR on this package.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default EvidenceViewer;
