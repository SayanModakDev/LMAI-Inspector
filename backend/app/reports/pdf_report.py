"""Readable multi-page ReportLab inspection report."""
import logging
import os
import time
import re
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage, LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from app.core.config import get_settings
from app.database import models
from app.rules.rule_engine import build_inspection_findings

settings = get_settings()
logger = logging.getLogger(__name__)


def _paragraph(value, style):
    # Stored OCR occasionally contains HTML-like remnants. Convert breaks to
    # actual ReportLab breaks and strip all other tags before escaping text.
    text = re.sub(r'<\s*br\s*/?\s*>', '\n', str(value or "—"), flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('\n', '<br/>')
    return Paragraph(text, style)


def _table(rows, widths, header=True):
    table = LongTable(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#B7C3D0')), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]
    if header:
        commands += [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#173F5F')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white)]
    table.setStyle(TableStyle(commands))
    return table


def generate_inspection_pdf(inspection: models.Inspection, db_session) -> models.Report:
    started = time.perf_counter()
    file_name = f"inspection_report_{inspection.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    file_path = os.path.join(settings.REPORT_DIR, file_name)
    doc = SimpleDocTemplate(file_path, pagesize=landscape(A4), leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('ReportTitle', parent=styles['Title'], alignment=1, textColor=colors.HexColor('#173F5F'))
    heading = ParagraphStyle('ReportHeading', parent=styles['Heading2'], textColor=colors.HexColor('#173F5F'), spaceBefore=10, spaceAfter=6)
    body = ParagraphStyle('ReportBody', parent=styles['BodyText'], fontSize=8.5, leading=11)
    small = ParagraphStyle('ReportSmall', parent=body, fontSize=7.5, leading=9)
    story = [Paragraph('Legal Metrology Compliance Report', title), Spacer(1, 5)]

    story.append(Paragraph('Inspection Summary', heading))
    summary = [[_paragraph('Inspection ID', body), _paragraph(inspection.id, body), _paragraph('Overall Result', body), _paragraph(inspection.overall_result, body)],
               [_paragraph('Product', body), _paragraph(inspection.product_name, body), _paragraph('Brand', body), _paragraph(inspection.brand, body)],
               [_paragraph('Category / Type', body), _paragraph(f'{inspection.category or "UNKNOWN"} / {inspection.product_type or "UNKNOWN"}', body), _paragraph('Package / Origin', body), _paragraph(f'{inspection.package_type} / {inspection.import_status}', body)]]
    story.append(_table(summary, [32*mm, 74*mm, 38*mm, 106*mm], header=False))
    findings = build_inspection_findings([{'parameter': r.parameter, 'status': r.status, 'message': r.message} for r in inspection.rule_results])
    story.append(Paragraph('Inspection Findings', heading))
    for label, values, colour in [('Verified', findings['verified'], '#1B5E20'), ('Needs Review', findings['needs_review'], '#8A5A00'), ('Non-compliant', findings['failed'], '#A61B1B')]:
        if values:
            story.append(Paragraph(f'<b><font color="{colour}">{label}</font></b>', body))
            for value in values:
                story.append(_paragraph(f'• {value}', body))

    story += [PageBreak(), Paragraph('Compliance Evaluation', heading)]
    results = [[_paragraph(x, small) for x in ['Parameter', 'Status', 'Regulatory Source', 'Evidence / Message', 'Confidence']]]
    for result in inspection.rule_results:
        evidence = result.evidence_data or {}
        evidence_text = evidence.get('value') if isinstance(evidence, dict) else ''
        results.append([_paragraph(result.parameter, small), _paragraph(result.status, small), _paragraph(getattr(result, 'regulatory_source', None) or 'LEGAL_METROLOGY', small), _paragraph(f'{result.message or ""}\n{evidence_text or ""}', small), _paragraph(evidence.get('confidence', '—') if isinstance(evidence, dict) else '—', small)])
    story.append(_table(results, [42*mm, 25*mm, 42*mm, 125*mm, 20*mm]))

    images = inspection.images or ([type('LegacyImage', (), {'file_name': inspection.image_path})()] if inspection.image_path else [])
    if images:
        story += [PageBreak(), Paragraph('Uploaded Product Images', heading)]
        for image in images:
            path = os.path.join(settings.UPLOAD_DIR, image.file_name)
            if not os.path.exists(path):
                continue
            from PIL import Image
            with Image.open(path) as source:
                width, height = source.size
            scale = min((235 * mm) / width, (135 * mm) / height, 1)
            story += [_paragraph(image.file_name, small), RLImage(path, width=width * scale, height=height * scale), Spacer(1, 7)]
    story += [Spacer(1, 10), Paragraph('AI-assisted screening tool. Final legal verification must be made by an authorized inspector.', styles['Italic'])]
    doc.build(story)

    existing = db_session.query(models.Report).filter(models.Report.inspection_id == inspection.id).order_by(models.Report.id.desc()).all()
    report = existing[0] if existing else models.Report(inspection_id=inspection.id)
    for duplicate in existing[1:]:
        if duplicate.file_path != file_path and os.path.exists(duplicate.file_path):
            os.remove(duplicate.file_path)
        db_session.delete(duplicate)
    report.file_path, report.file_name, report.generated_at = file_path, file_name, datetime.now()
    db_session.add(report)
    db_session.commit()
    logger.info('pdf timing inspection=%s generation_ms=%s', inspection.id, round((time.perf_counter() - started) * 1000))
    return report
