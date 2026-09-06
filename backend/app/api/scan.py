import logging
import os
import time
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
from app.rules.rule_engine import evaluate_rules, build_inspection_findings
from app.utils.helpers import generate_filename
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
    original_paths = []
    safe_filenames = []
    for uploaded_file in uploaded_files:
        safe_filename = generate_filename(uploaded_file.filename)
        original_path = os.path.join(settings.UPLOAD_DIR, safe_filename)
        with open(original_path, "wb") as handle:
            handle.write(await uploaded_file.read())
        safe_filenames.append(safe_filename)
        original_paths.append(original_path)
    upload_ms = round((time.perf_counter() - request_started) * 1000)
    logger.info("scan timing upload_ms=%s images=%s", upload_ms, len(uploaded_files))

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
                combined_text_parts.append(f"[IMAGE {image_index + 1}]\n{raw_text}")
            combined_ocr_items.extend(ocr_items)
            # Extract while image boundaries still exist; this makes a clear
            # declaration-panel value outrank weak text from another view.
            per_image_fields.append(extract_declarations(raw_text, ocr_items))
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
                'ocr_text': raw_text,
                'ocr_items': ocr_items,
                'barcode_result': image_barcode,
                'visual_evidence': detect_food_symbol(processed_path),
            })
            timings["images"].append({"image_index": image_index, "preprocess_ms": preprocess_ms, "ocr_ms": ocr_ms, "barcode_decode_ms": barcode_ms})
            logger.info("scan timing image=%s preprocess_ms=%s ocr_ms=%s barcode_decode_ms=%s", image_index, preprocess_ms, ocr_ms, barcode_ms)

        raw_text = '\n\n'.join(combined_text_parts)
        ocr_items = combined_ocr_items
        if barcode_result:
            lookup_started = time.perf_counter()
            barcode_result['lookup'] = lookup_barcode(barcode_result.get('value'))
            timings['product_lookup_ms'] = round((time.perf_counter() - lookup_started) * 1000)

        extraction_started = time.perf_counter()
        extracted_fields = merge_extracted_fields(per_image_fields + [extract_declarations(raw_text, ocr_items)])
        extracted_fields = merge_product_evidence(extracted_fields, raw_text, ocr_items, barcode_result)
        timings['declaration_extraction_ms'] = round((time.perf_counter() - extraction_started) * 1000)
        visual_candidates = [
            (result['visual_evidence'], result['image_index'])
            for result in image_results
            if result.get('visual_evidence', {}).get('status') == 'CANDIDATE'
        ]
        if visual_candidates and 'VEG_NONVEG_SYMBOL' not in extracted_fields:
            visual_evidence, image_index = max(visual_candidates, key=lambda item: item[0].get('confidence', 0))
            extracted_fields['VEG_NONVEG_SYMBOL'] = {
                'value': visual_evidence.get('symbol_type'),
                'confidence': visual_evidence.get('confidence', 0),
                'source': 'VISUAL_DETECTION',
                'source_image_index': image_index,
                'bbox': visual_evidence.get('bbox'),
                'detection_method': visual_evidence.get('detection_method'),
            }
        classification = classify_category(raw_text, extracted_fields, settings.CATEGORY_CONFIDENCE_THRESHOLD)
        category = classification.get('category', 'UNKNOWN')
        cat_confidence = classification.get('confidence', 0.0)
        product_type = classification.get('product_type') or extracted_fields.get('PRODUCT_TYPE', {}).get('value', 'UNKNOWN')

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
                evidence_type=field_data.get('source', 'OCR'),
                text_content=str(field_data.get('value', '')),
                bbox=field_data.get('bbox'),
                confidence=field_data.get('confidence'),
            ))

        for result in rule_results:
            db.add(models.RuleResult(
                inspection_id=db_inspection.id,
                rule_id=result.get('rule_id'),
                parameter=result.get('parameter'),
                status=result.get('status'),
                message=result.get('message'),
                evidence_data=result.get('evidence_data'),
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
            overall_result=overall_result,
            priority=priority,
            evidence=[],
            review_notes=build_inspection_findings(rule_results).get('needs_review', []),
            ocr_text=raw_text,
            ocr_data=ocr_payload.get('ocr_items', []),
            image_url=f"/uploads/{safe_filenames[0]}",
            images=[
                {"id": image_id, "image_index": index, "image_path": f"/uploads/{safe_filenames[index]}"}
                for index, image_id in sorted(image_index_to_id.items())
            ],
            barcode_result=barcode_result,
        )

    except Exception as exc:
        db.rollback()
        logger.exception("Error during scan pipeline")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(exc)}")
