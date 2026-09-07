import React, { useState, useRef, useMemo } from 'react';
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Search,
  Filter,
  Eye,
  Crosshair,
  ShieldCheck,
  AlertTriangle,
  XCircle,
  CheckCircle2,
  MinusCircle,
  Barcode as BarcodeIcon,
  Layers,
  ChevronRight,
  Info,
} from 'lucide-react';
import ConfidenceBadge from './ConfidenceBadge';
import StatusBadge from './StatusBadge';
import FieldDetailModal from './FieldDetailModal';
import './EvidenceViewer.css';

/**
 * Group definitions for statutory legal metrology declarations
 */
const PARAMETER_GROUPS = {
  IDENTITY: ['PRODUCT_NAME', 'BRAND', 'GENERIC_NAME'],
  COMMERCIAL: ['MRP', 'NET_QUANTITY', 'DECLARED_NET_QUANTITY', 'UNIT_SALE_PRICE'],
  MANUFACTURER: [
    'MANUFACTURER_NAME',
    'MANUFACTURER',
    'MANUFACTURER_ADDRESS',
    'ADDRESS',
    'COUNTRY_OF_ORIGIN',
    'IMPORTER',
    'PACKER',
  ],
  DATES: [
    'MONTH_YEAR_MANUFACTURE',
    'MANUFACTURE_DATE',
    'PACKING_DATE',
    'IMPORT_DATE',
    'BEST_BEFORE',
    'USE_BY',
    'DATE_EXPIRY',
  ],
  FOOD: ['FSSAI_LICENSE', 'FSSAI', 'VEG_NON_VEG', 'INGREDIENTS'],
  IDENTIFIERS: ['BARCODE', 'EAN', 'UPC', 'QR_CODE'],
};

const GROUP_LABELS = {
  IDENTITY: 'Identity & Designation',
  COMMERCIAL: 'Commercial & Pricing',
  MANUFACTURER: 'Origin & Manufacturer',
  DATES: 'Manufacturing & Expiry Dates',
  FOOD: 'Food Safety & Ingredients',
  IDENTIFIERS: 'Product Identifiers',
  OTHER: 'Additional Declarations',
};

const getGroupForParameter = (param) => {
  const norm = (param || '').toUpperCase().trim();
  for (const [group, params] of Object.entries(PARAMETER_GROUPS)) {
    if (params.includes(norm)) return group;
  }
  return 'OTHER';
};

const formatParamLabel = (param) => {
  if (!param) return 'Declaration';
  const customNames = {
    PRODUCT_NAME: 'Product Name',
    BRAND: 'Brand Identity',
    GENERIC_NAME: 'Generic / Common Name',
    MRP: 'Maximum Retail Price (MRP)',
    DECLARED_NET_QUANTITY: 'Declared Net Quantity',
    NET_QUANTITY: 'Declared Net Quantity',
    UNIT_SALE_PRICE: 'Unit Sale Price (USP)',
    MANUFACTURER_NAME: 'Manufacturer Name',
    MANUFACTURER: 'Manufacturer',
    MANUFACTURER_ADDRESS: 'Manufacturer Address',
    ADDRESS: 'Registered Address',
    COUNTRY_OF_ORIGIN: 'Country of Origin',
    MONTH_YEAR_MANUFACTURE: 'Month & Year of Manufacture',
    MANUFACTURE_DATE: 'Date of Manufacture',
    PACKING_DATE: 'Date of Packaging',
    BEST_BEFORE: 'Best Before / Use By',
    USE_BY: 'Use By Date',
    CONSUMER_CARE: 'Consumer Care Helpline',
    FSSAI_LICENSE: 'FSSAI License Number',
    VEG_NON_VEG: 'Vegetarian / Non-Vegetarian Symbol',
    INGREDIENTS: 'List of Ingredients',
    BARCODE: 'Commodity Barcode',
  };
  if (customNames[param.toUpperCase()]) return customNames[param.toUpperCase()];
  return param
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
};

/**
 * Enhanced EvidenceViewer Component (55% Image / 45% Evidence Workstation)
 */
const EvidenceViewer = ({
  images = [],
  extractedFields = [],
  ruleResults = [],
  barcodeResult = null,
  product = null,
  className = '',
}) => {
  const [selectedPanelIndex, setSelectedPanelIndex] = useState(0);
  const [activeFieldKey, setActiveFieldKey] = useState(null);
  const [hoveredFieldKey, setHoveredFieldKey] = useState(null);
  const [modalField, setModalField] = useState(null);
  const [zoomLevel, setZoomLevel] = useState(1.0);
  const [showBBoxes, setShowBBoxes] = useState(true);
  const [evidenceFilter, setEvidenceFilter] = useState('ALL'); // ALL, PASS, REVIEW, FAIL, MISSING
  const [sourceFilter, setSourceFilter] = useState('ALL'); // ALL, OCR, BARCODE, MULTI_IMAGE
  const [searchQuery, setSearchQuery] = useState('');
  const [imageDims, setImageDims] = useState({ width: 1000, height: 1000 });

  const imgRef = useRef(null);

  // Active panel image
  const activeImage = images[selectedPanelIndex] || images[0] || null;
  const imageSrc = activeImage?.image_path
    ? (activeImage.image_path.startsWith('/uploads/')
        ? activeImage.image_path
        : `/uploads/${activeImage.image_path}`)
    : (activeImage?.file_name ? `/uploads/${activeImage.file_name}` : '/placeholder.jpg');

  const handleImageLoad = (e) => {
    if (e.target.naturalWidth && e.target.naturalHeight) {
      setImageDims({
        width: e.target.naturalWidth,
        height: e.target.naturalHeight,
      });
    }
  };

  // Zoom controls
  const handleZoomIn = () => setZoomLevel((prev) => Math.min(prev + 0.25, 3.0));
  const handleZoomOut = () => setZoomLevel((prev) => Math.max(prev - 0.25, 1.0));
  const handleZoomReset = () => setZoomLevel(1.0);

  // Build structured evidence items by merging extracted_fields, product, and rule results
  const allEvidenceItems = useMemo(() => {
    const itemsMap = new Map();

    // 1. Ingest extracted_fields
    (extractedFields || []).forEach((field) => {
      const key = (field.field_name || field.parameter || '').toUpperCase();
      if (!key) return;

      const matchingRule = ruleResults.find((r) => r.parameter === key);
      const isMissing = !field.field_value || String(field.field_value).trim() === '';

      itemsMap.set(key, {
        field_name: key,
        parameter: key,
        field_value: field.field_value,
        raw_value: field.raw_value || field.field_value,
        raw_text: field.raw_text,
        confidence: field.confidence,
        source: field.source || 'OCR',
        extraction_method: field.extraction_method || field.source || 'OCR',
        bbox: field.bbox,
        source_image_id: field.source_image_id,
        source_image_index: field.source_image_index ?? (field.source_image_id ? field.source_image_id - 1 : 0),
        status: matchingRule?.status || (isMissing ? 'REVIEW' : 'PASS'),
        rule_id: matchingRule?.rule_id,
        reason: matchingRule?.reason || matchingRule?.message,
        isMissing,
      });
    });

    // 2. Ingest fields from product object if missing from extracted_fields
    if (product) {
      const productMapping = {
        PRODUCT_NAME: product.product_name,
        BRAND: product.brand,
        GENERIC_NAME: product.generic_name,
        MANUFACTURER: product.manufacturer,
        MANUFACTURER_ADDRESS: product.address,
        COUNTRY_OF_ORIGIN: product.country_of_origin,
        DECLARED_NET_QUANTITY: product.declared_net_quantity_value
          ? `${product.declared_net_quantity_value} ${product.declared_net_quantity_unit || ''}`.trim()
          : null,
        MRP: product.mrp,
        MANUFACTURE_DATE: product.manufacture_date,
        BEST_BEFORE: product.best_before,
        USE_BY: product.use_by,
        CONSUMER_CARE: product.consumer_care,
        UNIT_SALE_PRICE: product.unit_sale_price,
      };

      Object.entries(productMapping).forEach(([paramKey, val]) => {
        if (!itemsMap.has(paramKey) && val) {
          const matchingRule = ruleResults.find((r) => r.parameter === paramKey);
          itemsMap.set(paramKey, {
            field_name: paramKey,
            parameter: paramKey,
            field_value: val,
            raw_value: val,
            confidence: 0.85,
            source: 'PRODUCT_RECORD',
            extraction_method: 'STRUCTURED_RECORD',
            bbox: null,
            source_image_index: 0,
            status: matchingRule?.status || 'PASS',
            rule_id: matchingRule?.rule_id,
            reason: matchingRule?.reason || matchingRule?.message,
            isMissing: false,
          });
        }
      });
    }

    // 3. Ingest missing rule parameters from ruleResults so non-detected required fields are visible
    (ruleResults || []).forEach((rule) => {
      const key = (rule.parameter || '').toUpperCase();
      if (!key) return;

      // Skip physical verification rules in the standard 2D OCR evidence list (handled in dedicated physical section)
      if (key === 'ACTUAL_NET_CONTENT' || key === 'FONT_SIZE_COMPLIANCE') return;

      if (!itemsMap.has(key)) {
        const isNa = rule.status === 'NOT_APPLICABLE';
        itemsMap.set(key, {
          field_name: key,
          parameter: key,
          field_value: null,
          raw_value: null,
          confidence: null,
          source: 'OCR',
          extraction_method: 'OCR_VERIFICATION',
          bbox: null,
          source_image_index: 0,
          status: rule.status,
          rule_id: rule.rule_id,
          reason: rule.reason || rule.message || 'Evidence not detected in label scan',
          isMissing: !isNa,
        });
      }
    });

    // 4. Ingest Barcode if present in barcodeResult
    if (barcodeResult && barcodeResult.value) {
      const key = 'BARCODE';
      const matchingRule = ruleResults.find((r) => r.parameter === 'BARCODE');
      itemsMap.set(key, {
        field_name: 'BARCODE',
        parameter: 'BARCODE',
        field_value: barcodeResult.value,
        raw_value: barcodeResult.value,
        confidence: barcodeResult.confidence ?? 1.0,
        source: barcodeResult.source || 'BARCODE_SCANNER',
        extraction_method: barcodeResult.source === 'OCR_BARCODE_TEXT' ? 'OCR_FALLBACK' : 'PYZBAR_DECODER',
        bbox: null,
        source_image_index: 0,
        status: matchingRule?.status || 'PASS',
        rule_id: matchingRule?.rule_id,
        reason: 'Detected supplementary barcode identifier.',
        isMissing: false,
        barcodeLookup: barcodeResult.lookup,
      });
    }

    return Array.from(itemsMap.values());
  }, [extractedFields, ruleResults, product, barcodeResult]);

  // Filter evidence items
  const filteredEvidenceItems = useMemo(() => {
    return allEvidenceItems.filter((item) => {
      // Filter by status
      if (evidenceFilter === 'PASS' && item.status !== 'PASS') return false;
      if (evidenceFilter === 'FAIL' && item.status !== 'FAIL') return false;
      if (
        evidenceFilter === 'REVIEW' &&
        item.status !== 'NOT_VERIFIABLE' &&
        item.status !== 'MANUAL_CHECK' &&
        item.status !== 'REVIEW'
      )
        return false;
      if (evidenceFilter === 'MISSING' && !item.isMissing) return false;

      // Filter by source
      if (sourceFilter !== 'ALL') {
        const itemSrc = (item.source || '').toUpperCase();
        if (!itemSrc.includes(sourceFilter)) return false;
      }

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const name = (formatParamLabel(item.field_name)).toLowerCase();
        const key = item.field_name.toLowerCase();
        const val = String(item.field_value || '').toLowerCase();
        const reason = String(item.reason || '').toLowerCase();
        if (!name.includes(q) && !key.includes(q) && !val.includes(q) && !reason.includes(q)) {
          return false;
        }
      }

      return true;
    });
  }, [allEvidenceItems, evidenceFilter, sourceFilter, searchQuery]);

  // Group filtered items
  const groupedEvidence = useMemo(() => {
    const groups = {
      IDENTITY: [],
      COMMERCIAL: [],
      MANUFACTURER: [],
      DATES: [],
      FOOD: [],
      IDENTIFIERS: [],
      OTHER: [],
    };

    filteredEvidenceItems.forEach((item) => {
      const g = getGroupForParameter(item.field_name);
      if (groups[g]) groups[g].push(item);
      else groups.OTHER.push(item);
    });

    return groups;
  }, [filteredEvidenceItems]);

  // Click on evidence card
  const handleSelectField = (item) => {
    setActiveFieldKey(item.field_name === activeFieldKey ? null : item.field_name);

    // If item has known source panel, switch to that panel
    if (
      item.source_image_index !== undefined &&
      item.source_image_index >= 0 &&
      item.source_image_index < images.length
    ) {
      setSelectedPanelIndex(item.source_image_index);
    }
  };

  const handleOpenModal = (item, e) => {
    e?.stopPropagation();
    setModalField(item);
  };

  // Convert bounding box to SVG overlay coordinates
  const renderBBoxOverlay = () => {
    if (!showBBoxes) return null;

    // Collect all bounding boxes for the active panel
    const bboxesToRender = [];

    allEvidenceItems.forEach((item) => {
      if (!item.bbox) return;

      // Only render if matches active panel
      const itemPanel = item.source_image_index ?? 0;
      if (itemPanel !== selectedPanelIndex) return;

      const isSelected = activeFieldKey === item.field_name;
      const isHovered = hoveredFieldKey === item.field_name;

      bboxesToRender.push({
        item,
        bbox: item.bbox,
        isSelected,
        isHovered,
      });
    });

    if (bboxesToRender.length === 0) return null;

    return (
      <svg
        className="evidence-bbox-overlay"
        viewBox={`0 0 ${imageDims.width} ${imageDims.height}`}
        preserveAspectRatio="none"
      >
        {bboxesToRender.map(({ item, bbox, isSelected, isHovered }, idx) => {
          // 4-point polygon format: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
          if (Array.isArray(bbox) && bbox.length === 4 && Array.isArray(bbox[0])) {
            const pointsString = bbox.map((p) => `${p[0]},${p[1]}`).join(' ');
            return (
              <polygon
                key={idx}
                points={pointsString}
                className={`evidence-bbox-shape ${isSelected ? 'evidence-bbox-shape--selected' : ''} ${isHovered ? 'evidence-bbox-shape--hovered' : ''}`}
                onMouseEnter={() => setHoveredFieldKey(item.field_name)}
                onMouseLeave={() => setHoveredFieldKey(null)}
                onClick={() => {
                  setActiveFieldKey(item.field_name);
                  setModalField(item);
                }}
              >
                <title>{`${formatParamLabel(item.field_name)}: ${item.field_value || 'Detected'}`}</title>
              </polygon>
            );
          }

          // 4 numbers format: [ymin, xmin, ymax, xmax] or normalized
          if (Array.isArray(bbox) && bbox.length === 4 && typeof bbox[0] === 'number') {
            let [a, b, c, d] = bbox;
            let x, y, w, h;

            if (a <= 1.0 && b <= 1.0 && c <= 1.0 && d <= 1.0) {
              // Normalized [ymin, xmin, ymax, xmax]
              x = b * imageDims.width;
              y = a * imageDims.height;
              w = (d - b) * imageDims.width;
              h = (c - a) * imageDims.height;
            } else {
              // Pixel coordinates [ymin, xmin, ymax, xmax] or [x1, y1, x2, y2]
              const minX = Math.min(b, d);
              const minY = Math.min(a, c);
              w = Math.abs(d - b);
              h = Math.abs(c - a);
              x = minX;
              y = minY;
            }

            return (
              <rect
                key={idx}
                x={x}
                y={y}
                width={Math.max(w, 8)}
                height={Math.max(h, 8)}
                className={`evidence-bbox-shape ${isSelected ? 'evidence-bbox-shape--selected' : ''} ${isHovered ? 'evidence-bbox-shape--hovered' : ''}`}
                onMouseEnter={() => setHoveredFieldKey(item.field_name)}
                onMouseLeave={() => setHoveredFieldKey(null)}
                onClick={() => {
                  setActiveFieldKey(item.field_name);
                  setModalField(item);
                }}
              >
                <title>{`${formatParamLabel(item.field_name)}: ${item.field_value || 'Detected'}`}</title>
              </rect>
            );
          }

          return null;
        })}
      </svg>
    );
  };

  const hasAnyBBoxOnActivePanel = allEvidenceItems.some(
    (item) => item.bbox && (item.source_image_index ?? 0) === selectedPanelIndex
  );

  return (
    <div className={`evidence-workstation ${className}`}>
      {/* =========================================================================
          LEFT: IMAGE INSPECTION CANVAS (~55% width)
          ========================================================================= */}
      <div className="evidence-workstation__image-col">
        {/* Panel Header */}
        <div className="workstation-panel-header image-panel-header">
          <div className="flex items-center gap-2">
            <span className="panel-title text-white">Package Imagery</span>
            <span className="panel-badge font-mono">
              Panel {selectedPanelIndex + 1} of {Math.max(images.length, 1)}
            </span>
          </div>

          {/* Interactive Image Controls */}
          <div className="image-toolbar-controls">
            <button
              type="button"
              className="toolbar-btn"
              onClick={handleZoomIn}
              disabled={zoomLevel >= 3.0}
              title="Zoom in (+)"
            >
              <ZoomIn size={14} />
            </button>
            <span className="zoom-level-label font-mono text-xs text-muted">
              {Math.round(zoomLevel * 100)}%
            </span>
            <button
              type="button"
              className="toolbar-btn"
              onClick={handleZoomOut}
              disabled={zoomLevel <= 1.0}
              title="Zoom out (-)"
            >
              <ZoomOut size={14} />
            </button>
            <button
              type="button"
              className="toolbar-btn"
              onClick={handleZoomReset}
              title="Reset Zoom to Fit"
            >
              <RotateCcw size={13} />
            </button>
            {hasAnyBBoxOnActivePanel && (
              <button
                type="button"
                className={`toolbar-btn ${showBBoxes ? 'toolbar-btn--active' : ''}`}
                onClick={() => setShowBBoxes(!showBBoxes)}
                title={showBBoxes ? 'Hide Bounding Boxes' : 'Show Bounding Boxes'}
              >
                <Crosshair size={14} />
              </button>
            )}
          </div>
        </div>

        {/* Multi-Panel Switcher Tabs (If multiple panels exist) */}
        {images.length > 1 && (
          <div className="panel-tabs-bar" role="tablist" aria-label="Inspection image panels">
            {images.map((img, idx) => (
              <button
                key={idx}
                type="button"
                role="tab"
                aria-selected={selectedPanelIndex === idx}
                className={`panel-tab ${selectedPanelIndex === idx ? 'panel-tab--active' : ''}`}
                onClick={() => setSelectedPanelIndex(idx)}
              >
                <Layers size={12} />
                <span>Panel {idx + 1}</span>
                {img.file_name && (
                  <span className="panel-tab__file text-2xs truncate max-w-[90px]">
                    {img.file_name}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}

        {/* Image Stage Container with Pan/Zoom */}
        <div className={`image-stage-viewport ${zoomLevel > 1.0 ? 'image-stage-viewport--zoomed' : ''}`}>
          <div
            className="image-stage-content"
            style={{
              transform: `scale(${zoomLevel})`,
              transformOrigin: 'top center',
              transition: 'transform 0.15s ease-out',
            }}
          >
            <img
              ref={imgRef}
              src={imageSrc}
              alt={`Package Inspection Panel ${selectedPanelIndex + 1}`}
              className="inspection-image"
              onLoad={handleImageLoad}
              onError={(e) => {
                e.target.src = '/placeholder.jpg';
                e.target.style.opacity = '0.5';
              }}
            />
            {renderBBoxOverlay()}
          </div>
        </div>

        {/* Image Footer Info */}
        <div className="image-panel-footer">
          <div className="flex items-center gap-2 text-xs text-muted">
            <Eye size={12} />
            <span>
              {hasAnyBBoxOnActivePanel
                ? 'Hover or click bounding boxes to inspect declaration source'
                : 'No spatial coordinate boxes returned for this view'}
            </span>
          </div>
          {activeImage?.file_name && (
            <span className="text-2xs font-mono text-muted">
              {activeImage.file_name}
            </span>
          )}
        </div>
      </div>

      {/* =========================================================================
          RIGHT: DETECTED EVIDENCE PANEL (~45% width)
          ========================================================================= */}
      <div className="evidence-workstation__declarations-col">
        {/* Evidence Panel Header */}
        <div className="workstation-panel-header evidence-list-header">
          <div className="flex items-center gap-2">
            <span className="panel-title">Detected Evidence</span>
            <span className="badge badge-gray font-mono text-2xs">
              {filteredEvidenceItems.length} Declarations
            </span>
          </div>
        </div>

        {/* Search & Filter Toolbar */}
        <div className="evidence-toolbar">
          <div className="evidence-search-box">
            <Search size={13} className="evidence-search-icon" />
            <input
              type="text"
              placeholder="Search declarations (e.g. MRP, Net Quantity, Manufacturer)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="evidence-search-input"
            />
          </div>

          <div className="evidence-filter-pills">
            {[
              { id: 'ALL', label: 'All' },
              { id: 'PASS', label: 'Passed' },
              { id: 'REVIEW', label: 'Review' },
              { id: 'FAIL', label: 'Failed' },
              { id: 'MISSING', label: 'Missing' },
            ].map((f) => (
              <button
                key={f.id}
                type="button"
                className={`filter-pill ${evidenceFilter === f.id ? 'filter-pill--active' : ''}`}
                onClick={() => setEvidenceFilter(f.id)}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Grouped Declarations List */}
        <div className="evidence-groups-container">
          {Object.entries(groupedEvidence).map(([groupKey, items]) => {
            if (items.length === 0) return null;

            return (
              <div key={groupKey} className="evidence-group-section">
                <div className="evidence-group-header">
                  <span className="group-title">{GROUP_LABELS[groupKey] || groupKey}</span>
                  <span className="group-count font-mono text-2xs text-muted">
                    {items.length}
                  </span>
                </div>

                <div className="evidence-cards-list">
                  {items.map((item, idx) => {
                    const isSelected = activeFieldKey === item.field_name;
                    const isHovered = hoveredFieldKey === item.field_name;
                    const isConflict = String(item.field_value || '').startsWith('CONFLICT:');

                    return (
                      <div
                        key={idx}
                        className={`evidence-card ${isSelected ? 'evidence-card--selected' : ''} ${isHovered ? 'evidence-card--hovered' : ''} ${isConflict ? 'evidence-card--conflict' : ''} ${item.isMissing ? 'evidence-card--missing' : ''}`}
                        onClick={() => handleSelectField(item)}
                        onMouseEnter={() => setHoveredFieldKey(item.field_name)}
                        onMouseLeave={() => setHoveredFieldKey(null)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSelectField(item);
                        }}
                      >
                        <div className="evidence-card__top">
                          <div className="evidence-card__label-block">
                            <span className="evidence-card__title">
                              {formatParamLabel(item.field_name)}
                            </span>
                            <span className="evidence-card__key font-mono text-2xs text-muted">
                              {item.field_name}
                            </span>
                          </div>

                          <div className="evidence-card__badges">
                            <StatusBadge status={item.status} size="sm" showBinary={true} />
                          </div>
                        </div>

                        <div className="evidence-card__value-row">
                          <div className="evidence-card__val font-mono">
                            {item.isMissing ? (
                              <span className="text-muted italic">Evidence not detected</span>
                            ) : (
                              String(item.field_value)
                            )}
                          </div>
                        </div>

                        <div className="evidence-card__bottom">
                          <div className="flex items-center gap-2">
                            <span className="source-pill font-mono text-2xs">
                              {item.source}
                            </span>
                            {item.confidence !== null && item.confidence !== undefined && (
                              <ConfidenceBadge
                                confidence={item.confidence}
                                source={item.source || 'OCR'}
                              />
                            )}
                            {item.bbox && (
                              <span className="bbox-pill text-2xs font-mono" title="Spatial BBox detected">
                                BBox
                              </span>
                            )}
                          </div>

                          <button
                            type="button"
                            className="inspect-btn text-xs"
                            onClick={(e) => handleOpenModal(item, e)}
                            title="Inspect field attributes and statutory reason"
                          >
                            <span>Inspect</span>
                            <ChevronRight size={12} />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}

          {filteredEvidenceItems.length === 0 && (
            <div className="evidence-empty-state text-center p-6 text-muted">
              <Info size={24} className="mx-auto mb-2 text-muted" />
              <p className="font-semibold text-sm">No declarations match the selected filter</p>
              <p className="text-xs">Adjust search query or filter pills to review all evidence items.</p>
            </div>
          )}
        </div>
      </div>

      {/* Deep Inspection Detail Modal */}
      {modalField && (
        <FieldDetailModal
          field={modalField}
          onClose={() => setModalField(null)}
        />
      )}
    </div>
  );
};

export default EvidenceViewer;
