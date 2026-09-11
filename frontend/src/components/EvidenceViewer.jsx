import React, { useState, useRef, useMemo } from 'react';
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Search,
  Crosshair,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Barcode as BarcodeIcon,
  Layers,
  ChevronRight,
  Info,
  ExternalLink,
  Eye,
  Tag,
  Building2,
  Calendar,
  Utensils,
  Package,
} from 'lucide-react';
import ConfidenceBadge from './ConfidenceBadge';
import StatusBadge from './StatusBadge';
import FieldDetailModal from './FieldDetailModal';
import { resolveBackendUrl } from '../services/api';
import './EvidenceViewer.css';

/**
 * Group definitions for statutory legal metrology declarations (Strict Section 10 adherence)
 */
const PARAMETER_GROUPS = {
  IDENTITY: ['PRODUCT_NAME', 'BRAND', 'GENERIC_NAME'],
  QUANTITY: [
    'DECLARED_NET_QUANTITY',
    'NET_QUANTITY',
    'MULTIPACK_EXPRESSION',
    'PACK_COUNT',
    'UNIT_QUANTITY',
    'UNIT_NET_QUANTITY',
    'UNIT',
    'DERIVED_TOTAL',
  ],
  COMMERCIAL: ['MRP', 'UNIT_SALE_PRICE'],
  MANUFACTURER: [
    'MANUFACTURER_NAME',
    'MANUFACTURER',
    'MANUFACTURER_ADDRESS',
    'MARKETER_NAME',
    'MARKETER',
    'MARKETER_ADDRESS',
    'PACKER_NAME',
    'PACKER',
    'PACKER_ADDRESS',
    'IMPORTER_NAME',
    'IMPORTER',
    'IMPORTER_ADDRESS',
    'COUNTRY_OF_ORIGIN',
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
  IDENTIFIERS: ['BARCODE', 'BATCH_NUMBER', 'EAN', 'UPC', 'QR_CODE'],
};

const GROUP_LABELS = {
  IDENTITY: 'Identity & Designation',
  QUANTITY: 'Quantity & Content',
  COMMERCIAL: 'Commercial & Pricing',
  MANUFACTURER: 'Origin, Manufacturer & Marketer',
  DATES: 'Manufacturing & Expiry Dates',
  FOOD: 'Food Safety & Ingredients',
  IDENTIFIERS: 'Product Identifiers',
  OTHER: 'Additional Declarations',
};

const GROUP_ICONS = {
  IDENTITY: Package,
  QUANTITY: Layers,
  COMMERCIAL: Tag,
  MANUFACTURER: Building2,
  DATES: Calendar,
  FOOD: Utensils,
  IDENTIFIERS: BarcodeIcon,
  OTHER: Info,
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
    BRAND: 'Brand Name',
    GENERIC_NAME: 'Generic / Common Name',
    MRP: 'Maximum Retail Price (MRP)',
    DECLARED_NET_QUANTITY: 'Declared Net Quantity',
    NET_QUANTITY: 'Declared Net Quantity',
    MULTIPACK_EXPRESSION: 'Multipack Expression',
    UNIT_SALE_PRICE: 'Unit Sale Price (USP)',
    MANUFACTURER_NAME: 'Manufacturer Name',
    MANUFACTURER: 'Manufacturer',
    MANUFACTURER_ADDRESS: 'Manufacturer Address',
    MARKETER_NAME: 'Marketer Name',
    MARKETER: 'Marketer',
    MARKETER_ADDRESS: 'Marketer Address',
    PACKER_NAME: 'Packer Name',
    PACKER: 'Packer',
    PACKER_ADDRESS: 'Packer Address',
    IMPORTER_NAME: 'Importer Name',
    IMPORTER: 'Importer',
    IMPORTER_ADDRESS: 'Importer Address',
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
    BATCH_NUMBER: 'Batch / Lot Number',
  };
  if (customNames[param.toUpperCase()]) return customNames[param.toUpperCase()];
  return param
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
};

/**
 * Universal Multipack Parser Helper
 * Extracts or derives multipack decomposition without hardcoding
 */
const parseMultipackDetails = (item) => {
  if (!item) return null;

  // Check if item already carries structured multipack keys
  if (item.is_multipack && item.pack_count) {
    const packCount = item.pack_count;
    const unitQty = item.unit_quantity || item.unit_net_quantity;
    const unit = item.unit || 'g';
    const derivedTotal = item.derived_total_quantity || (packCount * unitQty);
    const declaredExpr = item.declared_expression || `${packCount} × ${unitQty} ${unit}`;
    return {
      isMultipack: true,
      packCount,
      unitQuantity: unitQty,
      unit,
      derivedTotal,
      declaredExpression: declaredExpr,
    };
  }

  // Check evidence_data / candidate candidate metadata
  const meta = item.metadata || item.evidence_data || {};
  if (meta.is_multipack && meta.pack_count) {
    const packCount = meta.pack_count;
    const unitQty = meta.unit_quantity || meta.unit_net_quantity;
    const unit = meta.unit || 'g';
    const derivedTotal = meta.derived_total_quantity || (packCount * unitQty);
    const declaredExpr = meta.declared_expression || `${packCount} × ${unitQty} ${unit}`;
    return {
      isMultipack: true,
      packCount,
      unitQuantity: unitQty,
      unit,
      derivedTotal,
      declaredExpression: declaredExpr,
    };
  }

  // Fallback: parse string representation (e.g. "12 X 25g" or "12 × 25 g")
  const valStr = String(item.field_value || item.raw_value || item.raw_text || '').trim();
  const multiMatch = valStr.match(/^(\d+)\s*(?:[xX×*]|packs?\s+of|units?\s+of)\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)/i);
  if (multiMatch) {
    const packCount = parseInt(multiMatch[1], 10);
    const unitQty = parseFloat(multiMatch[2]);
    const unit = multiMatch[3];
    return {
      isMultipack: true,
      packCount,
      unitQuantity: unitQty,
      unit,
      derivedTotal: packCount * unitQty,
      declaredExpression: `${packCount} × ${unitQty} ${unit}`,
    };
  }

  const invertedMatch = valStr.match(/^(\d+(?:\.\d+)?)\s*([a-zA-Z]+)\s*(?:[xX×*]|packs?\s+of)\s*(\d+)/i);
  if (invertedMatch) {
    const unitQty = parseFloat(invertedMatch[1]);
    const unit = invertedMatch[2];
    const packCount = parseInt(invertedMatch[3], 10);
    return {
      isMultipack: true,
      packCount,
      unitQuantity: unitQty,
      unit,
      derivedTotal: packCount * unitQty,
      declaredExpression: `${packCount} × ${unitQty} ${unit}`,
    };
  }

  return null;
};

/**
 * Main EvidenceViewer Workstation (55% Image / 45% Evidence)
 */
const EvidenceViewer = ({
  images = [],
  extractedFields = [],
  ruleResults = [],
  barcodeResult = null,
  product = null,
  onCountChange = null,
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
  const rawImageSrc = activeImage?.image_path
    ? (activeImage.image_path.startsWith('/uploads/') || activeImage.image_path.startsWith('http://') || activeImage.image_path.startsWith('https://')
        ? activeImage.image_path
        : `/uploads/${activeImage.image_path}`)
    : (activeImage?.file_name ? `/uploads/${activeImage.file_name}` : '/placeholder.jpg');
  const imageSrc = resolveBackendUrl(rawImageSrc);

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

  // Ingest and structure all evidence items
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
        is_multipack: field.is_multipack,
        pack_count: field.pack_count,
        unit_quantity: field.unit_quantity || field.unit_net_quantity,
        unit: field.unit,
        derived_total_quantity: field.derived_total_quantity,
        declared_expression: field.declared_expression,
        candidates: field.candidates,
        competing_candidates: field.competing_candidates,
        is_ambiguous: field.is_ambiguous || field.status === 'AMBIGUOUS',
        role: field.role,
      });
    });

    // 2. Ingest fields from product object if not already present
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

    // 3. Ingest rule results that were missing from extracted_fields so non-detected required fields are visible
    (ruleResults || []).forEach((rule) => {
      const key = (rule.parameter || '').toUpperCase();
      if (!key) return;

      // Skip physical verification parameters in the visual OCR evidence panel
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
        extraction_method:
          barcodeResult.source === 'OCR_BARCODE_TEXT' ? 'OCR_FALLBACK' : 'PYZBAR_DECODER',
        bbox: null,
        source_image_index: 0,
        status: matchingRule?.status || 'PASS',
        rule_id: matchingRule?.rule_id,
        reason: 'Detected package barcode identifier.',
        isMissing: false,
      });
    }

    return Array.from(itemsMap.values());
  }, [extractedFields, ruleResults, product, barcodeResult]);

  // Synchronize authoritative declaration count with parent tab
  React.useEffect(() => {
    if (onCountChange && allEvidenceItems.length > 0) {
      onCountChange(allEvidenceItems.length);
    }
  }, [allEvidenceItems.length, onCountChange]);

  // Product Identity Conflict Detection
  const productConflict = useMemo(() => {
    const nameItem = allEvidenceItems.find((i) => i.field_name === 'PRODUCT_NAME');
    if (!nameItem) return null;

    const valStr = String(nameItem.field_value || '');
    const isConflict =
      valStr.startsWith('CONFLICT:') ||
      nameItem.source === 'MULTI_IMAGE_CONFLICT' ||
      nameItem.extraction_method === 'MULTI_IMAGE_CONFLICT' ||
      nameItem.is_ambiguous ||
      (Array.isArray(nameItem.candidates) && nameItem.candidates.length > 1) ||
      (Array.isArray(nameItem.competing_candidates) && nameItem.competing_candidates.length > 1);

    if (!isConflict) return null;

    let candidates = [];
    if (Array.isArray(nameItem.candidates) && nameItem.candidates.length > 0) {
      candidates = nameItem.candidates.map((c, idx) => ({
        value: typeof c === 'object' ? (c.value || c.field_value || JSON.stringify(c)) : String(c),
        source: typeof c === 'object' ? (c.source || `Panel ${idx + 1}`) : `Candidate ${idx + 1}`,
        confidence: typeof c === 'object' ? c.confidence : 0.65,
        evidence_type: typeof c === 'object' ? c.evidence_type : 'OCR_TOKEN',
      }));
    } else if (Array.isArray(nameItem.competing_candidates) && nameItem.competing_candidates.length > 0) {
      candidates = nameItem.competing_candidates.map((c, idx) => ({
        value: typeof c === 'object' ? (c.entity || c.value || String(c)) : String(c),
        source: `Candidate ${idx + 1}`,
        confidence: 0.65,
        evidence_type: 'ENTITY_CANDIDATE',
      }));
    } else {
      const cleanVal = valStr.replace(/^CONFLICT:\s*/i, '');
      if (cleanVal.includes(' vs ')) {
        candidates = cleanVal.split(/\s+vs\s+/i).map((part, idx) => ({
          value: part.trim(),
          source: `Panel Observation ${idx + 1}`,
          confidence: 0.65,
          evidence_type: 'OCR_LINE',
        }));
      } else {
        candidates = [
          { value: cleanVal || 'Competing product titles', source: 'Panel View', confidence: 0.65 },
        ];
      }
    }

    return {
      parameter: 'PRODUCT_NAME',
      status: 'REQUIRES MANUAL REVIEW',
      candidates,
    };
  }, [allEvidenceItems]);

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
        item.status !== 'REVIEW' &&
        item.status !== 'NEEDS_REVIEW'
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
        const name = formatParamLabel(item.field_name).toLowerCase();
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

  // Group filtered items into canonical Section 10 categories
  const groupedEvidence = useMemo(() => {
    const groups = {
      IDENTITY: [],
      QUANTITY: [],
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

  // Select field and switch to panel if known
  const handleSelectField = (item) => {
    setActiveFieldKey(item.field_name === activeFieldKey ? null : item.field_name);

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

    const bboxesToRender = [];

    allEvidenceItems.forEach((item) => {
      if (!item.bbox) return;

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
                className={`evidence-bbox-shape ${
                  isSelected ? 'evidence-bbox-shape--selected' : ''
                } ${isHovered ? 'evidence-bbox-shape--hovered' : ''}`}
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
              x = b * imageDims.width;
              y = a * imageDims.height;
              w = (d - b) * imageDims.width;
              h = (c - a) * imageDims.height;
            } else {
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
                className={`evidence-bbox-shape ${
                  isSelected ? 'evidence-bbox-shape--selected' : ''
                } ${isHovered ? 'evidence-bbox-shape--hovered' : ''}`}
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

        {/* Image Viewport Container */}
        <div
          className={`image-stage-viewport ${
            zoomLevel > 1.0 ? 'image-stage-viewport--zoomed' : ''
          }`}
        >
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
              loading="lazy"
              onLoad={handleImageLoad}
              onError={(e) => {
                e.target.src = '/placeholder.jpg';
                e.target.style.opacity = '0.5';
              }}
            />
            {renderBBoxOverlay()}
          </div>
        </div>

        {/* Image Footer Info - Truthful conditional spatial wording */}
        <div className="image-panel-footer">
          <div className="flex items-center gap-2 text-xs text-muted">
            <Eye size={12} />
            <span>
              {hasAnyBBoxOnActivePanel
                ? 'Hover or click bounding boxes to inspect declaration source'
                : 'No spatial coordinate boxes returned for this view. Spatial evidence highlighting available when coordinates are provided.'}
            </span>
          </div>
          {activeImage?.file_name && (
            <span className="text-2xs font-mono text-muted">{activeImage.file_name}</span>
          )}
        </div>
      </div>

      {/* =========================================================================
          RIGHT: DETECTED EVIDENCE PANEL (~45% width)
          ========================================================================= */}
      <div className="evidence-workstation__declarations-col">
        {/* Evidence Panel Header - Authoritative Extracted Declarations Count */}
        <div className="workstation-panel-header evidence-list-header">
          <div className="flex items-center gap-2">
            <span className="panel-title">Detected Evidence</span>
            <span className="badge badge-gray font-mono text-2xs">
              {filteredEvidenceItems.length === allEvidenceItems.length
                ? `${allEvidenceItems.length} Extracted Declarations`
                : `${filteredEvidenceItems.length} of ${allEvidenceItems.length} Extracted Declarations`}
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

        {/* Confidence System Notice */}
        <div className="evidence-confidence-notice">
          <Info size={12} className="flex-shrink-0 text-muted" />
          <span>
            Confidence reflects the extraction/detection subsystem; it is not a legal compliance probability.
          </span>
        </div>

        {/* Grouped Declarations List */}
        <div className="evidence-groups-container">
          {/* Dedicated Product Identity Conflict Section (Section 12 strictly) */}
          {productConflict && (
            <div id="product-conflict-section" className="product-identity-conflict-box">
              <div className="conflict-box-header">
                <div className="flex items-center gap-2">
                  <AlertTriangle size={16} className="text-amber-600 flex-shrink-0" />
                  <div>
                    <span className="font-bold text-xs uppercase tracking-wide text-amber-900">
                      Product Identity Conflict
                    </span>
                    <p className="text-2xs text-amber-800 m-0">
                      Conflicting evidence: multiple package views or candidate text lines returned contradictory product identities.
                    </p>
                  </div>
                </div>
                <span className="badge badge-warning font-mono text-2xs font-bold">
                  REQUIRES MANUAL REVIEW
                </span>
              </div>

              <div className="conflict-candidates-grid">
                {productConflict.candidates.map((cand, idx) => (
                  <div key={idx} className="conflict-candidate-card">
                    <div className="conflict-candidate-card__top">
                      <span className="candidate-badge font-mono text-2xs font-bold">
                        Candidate {String.fromCharCode(65 + idx)}
                      </span>
                      {cand.confidence !== null && cand.confidence !== undefined && (
                        <span className="candidate-conf font-mono text-2xs">
                          {Math.round((cand.confidence || 0) * 100)}% conf
                        </span>
                      )}
                    </div>
                    <div className="candidate-val font-semibold text-main text-xs">
                      {cand.value}
                    </div>
                    <div className="candidate-meta text-2xs text-muted flex items-center justify-between mt-1">
                      <span>Source: {cand.source || 'Panel Observation'}</span>
                      {cand.evidence_type && <span>Type: {cand.evidence_type}</span>}
                    </div>
                  </div>
                ))}
              </div>

              <div className="conflict-resolution-note text-2xs text-amber-900 bg-amber-100 p-1.5 rounded">
                Conflicting evidence detected. The system does not select an official winner. The inspector must determine the official product identity during physical review.
              </div>
            </div>
          )}

          {/* Canonical Grouped Declarations */}
          {Object.entries(groupedEvidence).map(([groupKey, items]) => {
            if (items.length === 0) return null;
            const GroupIcon = GROUP_ICONS[groupKey] || Info;

            return (
              <div key={groupKey} className="evidence-group-section">
                <div className="evidence-group-header">
                  <div className="flex items-center gap-1.5">
                    <GroupIcon size={13} className="text-secondary" />
                    <span className="group-title">{GROUP_LABELS[groupKey] || groupKey}</span>
                  </div>
                  <span className="group-count font-mono text-2xs text-muted">
                    {items.length}
                  </span>
                </div>

                <div className="evidence-cards-list">
                  {items.map((item, idx) => {
                    const isSelected = activeFieldKey === item.field_name;
                    const isHovered = hoveredFieldKey === item.field_name;
                    const isConflict =
                      String(item.field_value || '').startsWith('CONFLICT:') || item.is_ambiguous;

                    const multipack = parseMultipackDetails(item);

                    // Barcode URL detection
                    const isBarcodeField = item.field_name === 'BARCODE';
                    const isUrlBarcode =
                      isBarcodeField &&
                      item.field_value &&
                      /^https?:\/\//i.test(String(item.field_value).trim());

                    return (
                      <div
                        key={idx}
                        className={`evidence-card ${
                          isSelected ? 'evidence-card--selected' : ''
                        } ${isHovered ? 'evidence-card--hovered' : ''} ${
                          isConflict ? 'evidence-card--conflict' : ''
                        } ${item.isMissing ? 'evidence-card--missing' : ''}`}
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
                              {(item.role || (item.field_name.startsWith('MANUFACTURER') ? 'MANUFACTURER' : item.field_name.startsWith('MARKETER') ? 'MARKETER' : null)) && (
                                <span className="entity-role-tag font-mono ml-1">
                                  [{item.role || (item.field_name.startsWith('MANUFACTURER') ? 'MANUFACTURER' : 'MARKETER')}]
                                </span>
                              )}
                            </span>
                          </div>

                          <div className="evidence-card__badges">
                            <StatusBadge status={item.status} size="sm" showBinary={true} />
                          </div>
                        </div>

                        {/* Value Row / Multipack Decomposition */}
                        <div className="evidence-card__value-row">
                          {multipack ? (
                            <div className="multipack-breakdown-box">
                              <div className="multipack-expr-line">
                                <span className="font-mono font-bold text-sm text-main">
                                  {multipack.declaredExpression}
                                </span>
                                <span className="badge badge-primary font-mono text-2xs">
                                  Multipack
                                </span>
                              </div>

                              <div className="multipack-metrics-grid">
                                <div className="multipack-submetric">
                                  <span className="submetric-label">Pack Count</span>
                                  <span className="submetric-val font-mono font-bold">
                                    {multipack.packCount}
                                  </span>
                                </div>
                                <div className="multipack-submetric">
                                  <span className="submetric-label">Unit Quantity</span>
                                  <span className="submetric-val font-mono font-bold">
                                    {multipack.unitQuantity} {multipack.unit}
                                  </span>
                                </div>
                                <div className="multipack-submetric multipack-submetric--derived">
                                  <div className="flex items-center justify-between gap-1">
                                    <span className="submetric-label">Derived Total</span>
                                    <span className="badge badge-derived font-mono text-2xs font-bold">
                                      DERIVED
                                    </span>
                                  </div>
                                  <span className="submetric-val font-mono font-bold text-teal">
                                    {multipack.derivedTotal} {multipack.unit}
                                  </span>
                                </div>
                              </div>
                              <div className="multipack-derived-caption text-2xs text-muted">
                                Derived total quantity ({multipack.packCount} × {multipack.unitQuantity} {multipack.unit}) — not printed as a single declaration.
                              </div>
                            </div>
                          ) : (
                            <div className="evidence-card__val font-mono">
                              {item.isMissing ? (
                                <span className="text-muted italic">Evidence not detected</span>
                              ) : isBarcodeField && isUrlBarcode ? (
                                <div className="barcode-url-box flex items-center justify-between gap-2">
                                  <span className="truncate max-w-[280px]" title={item.field_value}>
                                    {String(item.field_value)}
                                  </span>
                                  <a
                                    href={String(item.field_value)}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="barcode-open-link text-2xs font-semibold inline-flex items-center gap-0.5"
                                    onClick={(e) => e.stopPropagation()}
                                    title="Open barcode payload URL in a safe new tab"
                                  >
                                    <span>Open URL</span>
                                    <ExternalLink size={10} />
                                  </a>
                                </div>
                              ) : (
                                String(item.field_value)
                              )}
                            </div>
                          )}
                        </div>

                        {/* Card Bottom: Metadata & Inspect Button */}
                        <div className="evidence-card__bottom">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="source-pill font-mono text-2xs">
                              {item.source}
                            </span>
                            {item.source_image_index !== undefined && (
                              <button
                                type="button"
                                className="panel-link-btn font-mono text-2xs"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (item.source_image_index < images.length) {
                                    setSelectedPanelIndex(item.source_image_index);
                                  }
                                }}
                                title={`Jump to Panel ${item.source_image_index + 1}`}
                              >
                                Panel {item.source_image_index + 1}
                              </button>
                            )}
                            {item.confidence !== null && item.confidence !== undefined && (
                              <ConfidenceBadge
                                confidence={item.confidence}
                                source={item.source || 'OCR'}
                              />
                            )}
                            {item.bbox && (
                              <span
                                className="bbox-pill text-2xs font-mono"
                                title="Spatial coordinate box detected"
                              >
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
