import logging
import os
import time
from datetime import timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.classification.category_classifier import classify_category
from app.core.config import get_settings
from app.database import models, schemas
from app.database.connection import get_db
from app.extraction.declaration_extractor import extract_declarations, merge_product_evidence, merge_extracted_fields
from app.ocr.ocr_service import run_ocr
from app.ocr.preprocessing import preprocess_image
from app.rules.applicability import get_applicable_rules
from app.rules.rule_engine import evaluate_rules, build_inspection_findings, calculate_rule_summary
from app.utils.helpers import (
    generate_filename,
    sanitize_filename,
    validate_image_content,
    is_allowed_mime_type,
    get_safe_upload_path,
)
from app.barcode_decoder import decode_barcodes, lookup_barcode
from app.visual_detection import detect_food_symbol

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


@router.post("/scan", response_model=schemas.ScanResponse)
async def perform_scan(
    files: List[UploadFile] = File(default=None),
    file: UploadFile = File(default=None),
    package_type: str = Form("RETAIL"),
    import_status: str = Form("DOMESTIC"),
    db: Session = Depends(get_db),
):
    """Upload any number of label images and perform one combined inspection pipeline."""
    uploaded_files = [item for item in (files or []) if item and item.filename]
    if file and file.filename and not uploaded_files:
        uploaded_files = [file]
    if not uploaded_files:
        raise HTTPException(status_code=400, detail="No file uploaded")

    request_started = time.perf_counter()
    max_bytes = getattr(settings, "MAX_UPLOAD_SIZE_BYTES", settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024)

    # Validate all files before any disk writes or OCR execution
    validated_files = []
    for uploaded_file in uploaded_files:
        raw_name = uploaded_file.filename or "upload"
        sanitized_name = sanitize_filename(raw_name)

        # 1. Check declared MIME type
        content_type = uploaded_file.content_type
        if content_type and not is_allowed_mime_type(content_type):
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported media type '{content_type}' for file '{sanitized_name}'. Allowed formats: JPEG, PNG, WEBP, BMP.",
            )

        # 2. Read content into memory
        content = await uploaded_file.read()
        if not content or len(content) == 0:
            raise HTTPException(
                status_code=400,
                detail=f"Uploaded file '{sanitized_name}' is empty (0 bytes).",
            )

        # 3. Enforce maximum file size
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File '{sanitized_name}' exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB.",
            )

        # 4. Validate magic bytes and structural image integrity
        is_valid, detected_fmt, err_msg = validate_image_content(content)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail=f"File '{sanitized_name}' is not a valid image: {err_msg}",
            )

        # 5. Generate secure server-side filename and ensure upload path containment
        safe_filename = generate_filename(sanitized_name, detected_format=detected_fmt)
        try:
            dest_path = get_safe_upload_path(settings.UPLOAD_DIR, safe_filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid file path for '{sanitized_name}': {str(exc)}")

        validated_files.append({
            'safe_filename': safe_filename,
            'dest_path': dest_path,
            'content': content,
        })

    # Save validated files to disk
    original_paths = []
    safe_filenames = []
    for item in validated_files:
        with open(item['dest_path'], "wb") as handle:
            handle.write(item['content'])
        safe_filenames.append(item['safe_filename'])
        original_paths.append(item['dest_path'])

    upload_ms = round((time.perf_counter() - request_started) * 1000)
    logger.info("scan timing upload_ms=%s images=%s", upload_ms, len(validated_files))

    try:
        image_results = []
        combined_text_parts = []
        combined_ocr_items = []
        barcode_result = None
        per_image_fields = []
        total_processing_time = 0
        timings: Dict[str, Any] = {"upload_ms": upload_ms, "images": []}

        for image_index, original_path in enumerate(original_paths):
            image_started = time.perf_counter()
            try:
                processed_path, prep_info = preprocess_image(
                    input_path=original_path,
                    output_dir=settings.UPLOAD_DIR,
                    filename_prefix=f"processed_{image_index}",
                )
                preprocess_ms = round((time.perf_counter() - image_started) * 1000)
                ocr_started = time.perf_counter()
                ocr_result_data = run_ocr(processed_path)
                ocr_ms = round((time.perf_counter() - ocr_started) * 1000)
                raw_text = ocr_result_data.get('raw_text', '')
                ocr_items = ocr_result_data.get('ocr_items', [])
                for item in ocr_items:
                    item['image_index'] = image_index
                if raw_text:
                    combined_text_parts.append(raw_text)
                combined_ocr_items.extend(ocr_items)
                img_fields = extract_declarations(raw_text, ocr_items)
                for f_cand in img_fields.values():
                    if isinstance(f_cand, dict):
                        f_cand.setdefault('source_image_index', image_index)
                        f_cand.setdefault('source', f'OCR_IMAGE_{image_index + 1}')
                per_image_fields.append(img_fields)
                total_processing_time += ocr_result_data.get('processing_time_ms', 0)
                barcode_started = time.perf_counter()
                image_barcode = decode_barcodes(processed_path, raw_text)
                barcode_ms = round((time.perf_counter() - barcode_started) * 1000)
                if image_barcode and image_barcode.get('value'):
                    barcode_result = image_barcode
                image_results.append({
                    'image_index': image_index,
                    'image_path': safe_filenames[image_index],
                    'processed_image_path': os.path.basename(processed_path),
                    'processed_full_path': processed_path,
                    'ocr_status': ocr_result_data.get('ocr_status', 'SUCCESS_WITH_TEXT' if raw_text else 'NO_TEXT_DETECTED'),
                    'ocr_text': raw_text,
                    'ocr_items': ocr_items,
                    'ocr_diagnostics': {
                        'status': ocr_result_data.get('ocr_status'),
                        'attempt_count': ocr_result_data.get('attempt_count', 1),
                        'detection_count': ocr_result_data.get('detection_count', len(ocr_items)),
                        'preprocessing_variant': ocr_result_data.get('preprocessing_variant', 'original'),
                        'engine': ocr_result_data.get('engine', 'PaddleOCR'),
                        'engine_error': ocr_result_data.get('engine_error'),
                    },
                    'barcode_result': image_barcode,
                    'visual_evidence': None,
                })
                timings["images"].append({"image_index": image_index, "preprocess_ms": preprocess_ms, "ocr_ms": ocr_ms, "barcode_decode_ms": barcode_ms})
                logger.info("scan timing image=%s preprocess_ms=%s ocr_ms=%s barcode_decode_ms=%s", image_index, preprocess_ms, ocr_ms, barcode_ms)
            except Exception as img_exc:
                logger.error("Error processing scan image %s (%s): %s", image_index, original_path, img_exc)
                image_results.append({
                    'image_index': image_index,
                    'image_path': safe_filenames[image_index],
                    'processed_image_path': os.path.basename(original_path),
                    'processed_full_path': original_path,
                    'ocr_status': 'OCR_ENGINE_ERROR',
                    'ocr_text': '',
                    'ocr_items': [],
                    'ocr_diagnostics': {
                        'status': 'OCR_ENGINE_ERROR',
                        'engine_error': str(img_exc),
                    },
                    'barcode_result': {'type': 'NOT_DETECTED', 'value': None, 'confidence': 0.0},
                    'visual_evidence': None,
                })
                per_image_fields.append({})

        raw_text = '\n\n'.join(combined_text_parts)
        ocr_items = combined_ocr_items
        if barcode_result:
            lookup_started = time.perf_counter()
            barcode_result['lookup'] = lookup_barcode(barcode_result.get('value'))
            timings['product_lookup_ms'] = round((time.perf_counter() - lookup_started) * 1000)

        extraction_started = time.perf_counter()
        extracted_fields = merge_extracted_fields(per_image_fields)
        extracted_fields = merge_product_evidence(extracted_fields, raw_text, ocr_items, barcode_result)
        timings['declaration_extraction_ms'] = round((time.perf_counter() - extraction_started) * 1000)

        # Classification precedes category-specific visual checks
        classification = classify_category(raw_text, extracted_fields, settings.CATEGORY_CONFIDENCE_THRESHOLD)
        category = classification.get('category', 'UNKNOWN')
        cat_confidence = classification.get('confidence', 0.0)
        product_type = classification.get('product_type') or extracted_fields.get('PRODUCT_TYPE', {}).get('value', 'UNKNOWN')

        # Category-gated visual detection: only run food symbol detection for confident FOOD products.
        is_confident_food = (
            category == 'FOOD'
            and cat_confidence >= settings.CATEGORY_CONFIDENCE_THRESHOLD
        )

        if is_confident_food:
            visual_started = time.perf_counter()
            visual_candidates = []
            for image_res in image_results:
                proc_img_path = image_res.get('processed_full_path')
                if proc_img_path and os.path.exists(proc_img_path):
                    vis_ev = detect_food_symbol(proc_img_path)
                    image_res['visual_evidence'] = vis_ev
                    if vis_ev.get('status') == 'CANDIDATE':
                        visual_candidates.append((vis_ev, image_res['image_index']))
            timings['visual_detection_ms'] = round((time.perf_counter() - visual_started) * 1000)

            if visual_candidates and 'VEG_NONVEG_SYMBOL' not in extracted_fields:
                visual_evidence, image_index = max(visual_candidates, key=lambda item: item[0].get('confidence', 0))
                extracted_fields['VEG_NONVEG_SYMBOL'] = {
                    'value': visual_evidence.get('symbol_type'),
                    'symbol_type': visual_evidence.get('symbol_type'),
                    'confidence': visual_evidence.get('confidence', 0),
                    'source': 'VISUAL_DETECTION',
                    'source_image_index': image_index,
                    'bbox': visual_evidence.get('bbox'),
                    'detection_method': visual_evidence.get('detection_method'),
                    'status': 'CANDIDATE',
                    'is_candidate': True,
                    'candidate_status': 'CANDIDATE',
                }
        else:
            # Non-food products (COSMETIC, HOUSEHOLD, ELECTRONICS, etc.) or unconfident category:
            # Do NOT run food-symbol detection and do NOT retain VEG_NONVEG_SYMBOL evidence.
            for image_res in image_results:
                image_res['visual_evidence'] = None
            extracted_fields.pop('VEG_NONVEG_SYMBOL', None)

        db_rules = db.query(models.Rule).filter(models.Rule.is_active == True).all()
        all_rules_dict = [{c.name: getattr(rule, c.name) for c in rule.__table__.columns} for rule in db_rules]
        applicable_rules = get_applicable_rules(
            all_rules=all_rules_dict,
            category=category,
            product_type=product_type,
            package_type=package_type,
            import_status=import_status,
            has_physical_data=False,
        )

        rule_started = time.perf_counter()
        rule_results, overall_result = evaluate_rules(applicable_rules, extracted_fields)
        timings['rule_evaluation_ms'] = round((time.perf_counter() - rule_started) * 1000)
        priority = 'HIGH' if overall_result == 'NON-COMPLIANT' else 'MEDIUM'

        db_inspection = models.Inspection(
            product_name=extracted_fields.get('PRODUCT_NAME', {}).get('value', 'Unknown Product'),
            category=category,
            category_confidence=cat_confidence,
            brand=extracted_fields.get('BRAND', {}).get('value'),
            product_type=product_type,
            package_type=package_type,
            import_status=import_status,
            overall_result=overall_result,
            priority=priority,
            image_path=safe_filenames[0],
            processed_image_path=image_results[0]['processed_image_path'],
        )
        db.add(db_inspection)
        db.flush()

        image_index_to_id = {}
        for image_result in image_results:
            image_record = models.InspectionImage(
                inspection_id=db_inspection.id,
                image_index=image_result['image_index'],
                file_name=image_result['image_path'],
                processed_file_name=image_result['processed_image_path'],
                source='UPLOAD_OR_CAMERA',
            )
            db.add(image_record)
            db.flush()
            image_index_to_id[image_record.image_index] = image_record.id
            image_result['image_id'] = image_record.id

        for field_data in extracted_fields.values():
            source_index = field_data.get('source_image_index')
            if source_index in image_index_to_id:
                field_data['source_image_id'] = image_index_to_id[source_index]
            for cand in field_data.get('candidates', []):
                c_idx = cand.get('source_image_index')
                if c_idx in image_index_to_id:
                    cand['source_image_id'] = image_index_to_id[c_idx]

        db_product = models.Product(
            inspection_id=db_inspection.id,
            product_name=extracted_fields.get('PRODUCT_NAME', {}).get('value'),
            brand=extracted_fields.get('BRAND', {}).get('value'),
            manufacturer=extracted_fields.get('MANUFACTURER_NAME', {}).get('value'),
            address=extracted_fields.get('MANUFACTURER_ADDRESS', {}).get('value'),
            mrp=extracted_fields.get('MRP', {}).get('value'),
            declared_net_quantity_value=extracted_fields.get('DECLARED_NET_QUANTITY', {}).get('quantity_value'),
            declared_net_quantity_unit=extracted_fields.get('DECLARED_NET_QUANTITY', {}).get('quantity_unit'),
            country_of_origin=extracted_fields.get('COUNTRY_OF_ORIGIN', {}).get('value'),
            importer=extracted_fields.get('IMPORTER_NAME_ADDRESS', {}).get('value'),
            best_before=extracted_fields.get('BEST_BEFORE_USE_BY', {}).get('value'),
            use_by=extracted_fields.get('USE_BEFORE_DATE', {}).get('value'),
            manufacture_date=extracted_fields.get('MONTH_YEAR_MANUFACTURE', {}).get('value'),
            packing_date=extracted_fields.get('PACKING_DATE', {}).get('value'),
            ingredients=extracted_fields.get('INGREDIENTS_LIST', {}).get('value'),
            consumer_care=extracted_fields.get('CONSUMER_CARE', {}).get('value'),
            generic_name=extracted_fields.get('GENERIC_NAME', {}).get('value'),
        )
        db.add(db_product)

        ocr_payload = {
            "ocr_items": ocr_items,
            "barcode_result": barcode_result,
            "images": image_results,
        }
        db_ocr = models.OCRResult(
            inspection_id=db_inspection.id,
            raw_text=raw_text,
            ocr_data=ocr_payload,
            processing_time_ms=total_processing_time,
        )
        db.add(db_ocr)

        for field_name, field_data in extracted_fields.items():
            db.add(models.ExtractedField(
                inspection_id=db_inspection.id,
                field_name=field_name,
                field_value=field_data.get('value'),
                confidence=field_data.get('confidence'),
                source=field_data.get('source', 'OCR'),
                extraction_method=field_data.get('extraction_method', field_data.get('source', 'OCR')),
                bbox=field_data.get('bbox'),
                source_image_id=field_data.get('source_image_id'),
            ))
            db.add(models.Evidence(
                inspection_id=db_inspection.id,
                parameter=field_name,
                evidence_type=field_data.get('evidence_type', field_data.get('source', 'OCR')),
                text_content=str(field_data.get('value', '')),
                bbox=field_data.get('bbox'),
                confidence=field_data.get('confidence'),
            ))

        for result in rule_results:
            ev_data = dict(result.get('evidence_data') or {})
            ev_data['binary'] = result.get('binary')
            ev_data['reason'] = result.get('reason') or result.get('message')
            ev_data['validation_result'] = result.get('validation_result')
            ev_data['raw_value'] = result.get('raw_value')
            ev_data['value'] = result.get('value')
            ev_data['unit'] = result.get('unit')
            ev_data['quantity_present'] = result.get('quantity_present')
            ev_data['unit_present'] = result.get('unit_present')
            ev_data['quantity_unit_valid'] = result.get('quantity_unit_valid')

            db.add(models.RuleResult(
                inspection_id=db_inspection.id,
                rule_id=result.get('rule_id'),
                parameter=result.get('parameter'),
                status=result.get('status'),
                message=result.get('message'),
                evidence_data=ev_data,
                rule_version=result.get('rule_version'),
                regulatory_source=result.get('regulatory_source'),
                rule_reference=result.get('rule_reference'),
                review_required=result.get('review_required'),
            ))

        db_started = time.perf_counter()
        db.commit()
        timings['database_write_ms'] = round((time.perf_counter() - db_started) * 1000)
        timings['total_ms'] = round((time.perf_counter() - request_started) * 1000)
        # Persist timings with OCR payload after the main inspection write.
        db_ocr.ocr_data['timings'] = timings
        db.commit()
        logger.info("scan timing complete inspection=%s timings=%s", db_inspection.id, timings)

        created_dt = db_inspection.created_at
        if created_dt and created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)

        return schemas.ScanResponse(
            inspection_id=db_inspection.id,
            category=category,
            category_confidence=cat_confidence,
            package_type=package_type,
            import_status=import_status,
            product_name=db_product.product_name,
            brand=extracted_fields.get('BRAND', {}).get('value'),
            product_type=product_type,
            extracted_fields=extracted_fields,
            rule_results=rule_results,
            summary=calculate_rule_summary(rule_results),
            overall_result=overall_result,
            priority=priority,
            evidence=[],
            review_notes=build_inspection_findings(rule_results).get('needs_review', []),
            ocr_text=raw_text,
            ocr_data=ocr_payload.get('ocr_items', []),
            image_url=f"/uploads/{safe_filenames[0]}",
            images=[
                {
                    "id": image_id,
                    "image_index": index,
                    "image_path": f"/uploads/{safe_filenames[index]}",
                    "ocr_status": image_results[index].get("ocr_status"),
                    "ocr_diagnostics": image_results[index].get("ocr_diagnostics"),
                }
                for index, image_id in sorted(image_index_to_id.items())
            ],
            barcode_result=barcode_result,
            created_at=created_dt,
            inspection_date=created_dt,
        )

    except Exception as exc:
        db.rollback()
        logger.exception("Error during scan pipeline")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(exc)}")
