"""Professional 4-page inspection-support ReportLab PDF report generator."""
import logging
import os
import time
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
    Image as RLImage,
    HRFlowable,
)
from reportlab.pdfgen import canvas

from app.core.config import get_settings
from app.core.constants import InspectionStatus, normalize_status
from app.database import models
from app.rules.rule_engine import build_inspection_findings

settings = get_settings()
logger = logging.getLogger(__name__)

# Mandatory statutory disclaimer
STATUTORY_DISCLAIMER = (
    "This is an inspection-support tool and final legal verification must be made by an authorized inspector."
)


class NumberedCanvas(canvas.Canvas):
    """Canvas supporting total page count in running headers and footers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[Dict[str, Any]] = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages: int):
        self.saveState()
        width, height = self._pagesize

        # Running header (pages 2 and higher)
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#173F5F"))
            self.drawString(12 * mm, height - 10 * mm, "LMAI INSPECTOR")
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawString(42 * mm, height - 10 * mm, "— Statutory Label Compliance Screening Report")
            self.drawRightString(width - 12 * mm, height - 10 * mm, f"Page {self._pageNumber} of {total_pages}")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(12 * mm, height - 11.5 * mm, width - 12 * mm, height - 11.5 * mm)

        # Running footer (all pages)
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(12 * mm, 12 * mm, width - 12 * mm, 12 * mm)

        self.setFont("Helvetica-Oblique", 7.5)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(12 * mm, 8 * mm, STATUTORY_DISCLAIMER)

        self.setFont("Helvetica", 7.5)
        self.drawRightString(width - 12 * mm, 8 * mm, f"Page {self._pageNumber} of {total_pages}")

        self.restoreState()


def _paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    """Safely escape text for ReportLab Paragraphs and preserve breaks."""
    if value is None:
        text = "—"
    else:
        text = str(value)
    # Convert existing break tags to \n, strip stray tags, then xml escape
    text = re.sub(r'<\s*br\s*/?\s*>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('\n', '<br/>')
    )
    if not text.strip():
        text = "—"
    return Paragraph(text, style)


def _safe_html_p(html_text: str, style: ParagraphStyle) -> Paragraph:
    """Render paragraph containing approved inline markup."""
    return Paragraph(html_text, style)


def _clean_ref(value: Optional[str]) -> str:
    """Display 'Pending verification' instead of fabricating a rule number."""
    if not value or str(value).strip().upper() in (
        "PENDING_VERIFICATION", "PENDING", "UNKNOWN", "NONE", "NULL", "UNVERIFIED"
    ):
        return "Pending verification"
    return str(value).strip()


def _table(rows: List[List[Any]], widths: List[float], header: bool = True, custom_style: Optional[List] = None) -> Table:
    """Create a standardized table with border and padding defaults."""
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]
    if header:
        commands += [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#173F5F')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
            ('TOPPADDING', (0, 0), (-1, 0), 5),
        ]
    if custom_style:
        commands += custom_style
    table.setStyle(TableStyle(commands))
    return table


def generate_inspection_pdf(inspection: models.Inspection, db_session) -> models.Report:
    """Generate a 4-page professional inspection-support PDF report centered around the Rule Matrix."""
    started = time.perf_counter()
    file_name = f"inspection_report_{inspection.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    file_path = os.path.join(settings.REPORT_DIR, file_name)

    # Landscape A4: width = 297mm, height = 210mm. Usable width = 273mm (margins 12mm each)
    doc = SimpleDocTemplate(
        file_path,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    styles = getSampleStyleSheet()

    # Custom typography styles
    title_style = ParagraphStyle(
        'DocTitle',
        fontName='Helvetica-Bold',
        fontSize=17,
        leading=21,
        textColor=colors.HexColor('#173F5F'),
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#475569'),
    )
    heading_style = ParagraphStyle(
        'SectionHeading',
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#173F5F'),
        spaceBefore=6,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        'TableBody',
        fontName='Helvetica',
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor('#1E293B'),
    )
    body_bold = ParagraphStyle(
        'TableBodyBold',
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor('#1E293B'),
    )
    small_style = ParagraphStyle(
        'TableSmall',
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#334155'),
    )
    small_bold = ParagraphStyle(
        'TableSmallBold',
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#0F172A'),
    )
    th_style = ParagraphStyle(
        'TableHeader',
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white,
    )

    story = []

    # Map rule definitions from DB for rich metadata lookup
    rules_map: Dict[str, models.Rule] = {}
    if db_session:
        try:
            db_rules = db_session.query(models.Rule).all()
            for r in db_rules:
                rules_map[r.rule_id] = r
        except Exception as e:
            logger.warning("Failed to load rules from db: %s", e)

    # Determine canonical overall result
    canonical_result = normalize_status(inspection.overall_result) or InspectionStatus.NOT_VERIFIABLE
    if canonical_result == InspectionStatus.COMPLIANT:
        overall_label = "1 — COMPLIANT"
        overall_bg = colors.HexColor('#E8F5E9')
        overall_border = colors.HexColor('#2E7D32')
        overall_color = '#1B5E20'
        overall_desc = "All applicable statutory declarations under Legal Metrology Rules passed deterministic verification."
    elif canonical_result == InspectionStatus.NON_COMPLIANT:
        overall_label = "0 — NON-COMPLIANT"
        overall_bg = colors.HexColor('#FFEBEE')
        overall_border = colors.HexColor('#C62828')
        overall_color = '#B71C1C'
        overall_desc = "One or more mandatory statutory declarations failed deterministic validation requirements."
    else:
        overall_label = "REQUIRES REVIEW"
        overall_bg = colors.HexColor('#FFF8E1')
        overall_border = colors.HexColor('#F57F17')
        overall_color = '#B45309'
        overall_desc = "One or more declarations have unverified or conflicting evidence. Manual inspector review is required."

    # Compute summary counters
    results_list = inspection.rule_results or []
    passed_count = sum(1 for r in results_list if r.status == 'PASS')
    failed_count = sum(1 for r in results_list if r.status == 'FAIL')
    review_count = sum(1 for r in results_list if r.status in ('NOT_VERIFIABLE', 'NEEDS_REVIEW'))
    na_count = sum(1 for r in results_list if r.status == 'NOT_APPLICABLE')

    # Package Type & Import Status with Inspector Default indicators
    pkg_type_str = inspection.package_type or "RETAIL"
    pkg_tag = " (Inspector Default)" if pkg_type_str == "RETAIL" else " (Inspector Selected)"
    pkg_display = f"{pkg_type_str}{pkg_tag}"

    import_status_str = inspection.import_status or "DOMESTIC"
    import_tag = " (Inspector Default)" if import_status_str == "DOMESTIC" else " (Inspector Selected)"
    import_display = f"{import_status_str}{import_tag}"

    date_str = (
        inspection.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        if inspection.created_at else datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    )

    # =========================================================================
    # PAGE 1: LMAI INSPECTOR — INSPECTION OVERVIEW & SUMMARY
    # =========================================================================

    # 1. Header Banner
    header_table = Table(
        [
            [
                _safe_html_p("<b>LMAI INSPECTOR</b>", title_style),
                _safe_html_p(
                    f"<b>Inspection Record #{inspection.id}</b><br/>"
                    f"<font color='#64748B'>Date: {date_str}</font>",
                    ParagraphStyle('RightHdr', parent=subtitle_style, alignment=2),
                ),
            ],
            [
                _safe_html_p(
                    "Legal Metrology AI Inspector — Packaging Compliance Screening System<br/>"
                    "<font color='#64748B'>Standards of Weights and Measures (Packaged Commodities) Rules, 2011</font>",
                    subtitle_style,
                ),
                _safe_html_p(
                    f"<b>Inspector:</b> {inspection.inspector_name or 'Default Inspector'}<br/>"
                    f"<b>Priority:</b> {inspection.priority or 'MEDIUM'}",
                    ParagraphStyle('RightHdr2', parent=subtitle_style, alignment=2),
                ),
            ],
        ],
        colWidths=[180 * mm, 93 * mm],
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 3 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#173F5F"), spaceBefore=1, spaceAfter=4))

    # 2. Inspection Metadata Grid
    story.append(Paragraph("Inspection Overview & Product Profile", heading_style))
    meta_rows = [
        [
            _paragraph("Inspection ID", body_bold),
            _paragraph(f"#{inspection.id}", body_style),
            _paragraph("Date / Time", body_bold),
            _paragraph(date_str, body_style),
        ],
        [
            _paragraph("Product Name", body_bold),
            _paragraph(inspection.product_name or (inspection.product and inspection.product.product_name) or "Not detected", body_style),
            _paragraph("Brand", body_bold),
            _paragraph(inspection.brand or (inspection.product and inspection.product.brand) or "Not detected", body_style),
        ],
        [
            _paragraph("Category", body_bold),
            _paragraph(f"{inspection.category or 'UNKNOWN'} (Conf: {int((inspection.category_confidence or 1.0) * 100)}%)", body_style),
            _paragraph("Product Type", body_bold),
            _paragraph(inspection.product_type or "UNKNOWN", body_style),
        ],
        [
            _paragraph("Package Type", body_bold),
            _paragraph(pkg_display, body_style),
            _paragraph("Import Status", body_bold),
            _paragraph(import_display, body_style),
        ],
    ]
    meta_table = _table(meta_rows, [35 * mm, 101 * mm, 35 * mm, 102 * mm], header=False, custom_style=[
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F1F5F9')),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#F1F5F9')),
    ])
    story.append(meta_table)
    story.append(Spacer(1, 4 * mm))

    # 3. Large Overall Compliance Result Banner
    banner_content = [
        [
            _safe_html_p(
                f"<font size='15' color='{overall_color}'><b>OVERALL COMPLIANCE RATING: {overall_label}</b></font><br/>"
                f"<font size='8.5' color='#334155'>{overall_desc}</font>",
                ParagraphStyle('BannerP', parent=body_style, alignment=1),
            )
        ]
    ]
    banner_table = Table(banner_content, colWidths=[273 * mm])
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), overall_bg),
        ('BOX', (0, 0), (-1, -1), 2, overall_border),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 4 * mm))

    # 4. Summary Metrics Cards (Passed, Failed, Require Review, Not Applicable)
    summary_cards = [
        [
            _safe_html_p(f"<font size='13' color='#1B5E20'><b>{passed_count}</b></font><br/><font size='7.5' color='#1B5E20'><b>1 — PASSED</b></font>", ParagraphStyle('Card1', parent=body_style, alignment=1)),
            _safe_html_p(f"<font size='13' color='#B71C1C'><b>{failed_count}</b></font><br/><font size='7.5' color='#B71C1C'><b>0 — FAILED</b></font>", ParagraphStyle('Card2', parent=body_style, alignment=1)),
            _safe_html_p(f"<font size='13' color='#B45309'><b>{review_count}</b></font><br/><font size='7.5' color='#B45309'><b>REVIEW REQUIRED</b></font>", ParagraphStyle('Card3', parent=body_style, alignment=1)),
            _safe_html_p(f"<font size='13' color='#475569'><b>{na_count}</b></font><br/><font size='7.5' color='#475569'><b>NOT APPLICABLE</b></font>", ParagraphStyle('Card4', parent=body_style, alignment=1)),
        ]
    ]
    summary_table = Table(summary_cards, colWidths=[68.25 * mm, 68.25 * mm, 68.25 * mm, 68.25 * mm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#E8F5E9')),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#FFEBEE')),
        ('BACKGROUND', (2, 0), (2, 0), colors.HexColor('#FFF8E1')),
        ('BACKGROUND', (3, 0), (3, 0), colors.HexColor('#F1F5F9')),
        ('BOX', (0, 0), (0, 0), 1, colors.HexColor('#2E7D32')),
        ('BOX', (1, 0), (1, 0), 1, colors.HexColor('#C62828')),
        ('BOX', (2, 0), (2, 0), 1, colors.HexColor('#F57F17')),
        ('BOX', (3, 0), (3, 0), 1, colors.HexColor('#94A3B8')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 4 * mm))

    # 5. Key Findings Breakdown & Inspector Notes
    story.append(Paragraph("Inspection Findings & Field Observations", heading_style))
    findings = build_inspection_findings([
        {'parameter': r.parameter, 'status': r.status, 'message': r.message}
        for r in results_list
    ])
    findings_rows = []
    if findings['failed']:
        findings_rows.append([
            _safe_html_p("<b><font color='#B71C1C'>Critical Violations (0):</font></b>", small_bold),
            _safe_html_p(", ".join(findings['failed']), small_style),
        ])
    if findings['needs_review']:
        findings_rows.append([
            _safe_html_p("<b><font color='#B45309'>Requires Review:</font></b>", small_bold),
            _safe_html_p(", ".join(findings['needs_review']), small_style),
        ])
    if findings['verified']:
        findings_rows.append([
            _safe_html_p("<b><font color='#1B5E20'>Verified Declarations (1):</font></b>", small_bold),
            _safe_html_p(", ".join(findings['verified']), small_style),
        ])
    if not findings_rows:
        findings_rows.append([_paragraph("No specific finding categories available.", small_style), _paragraph("—", small_style)])

    findings_table = _table(findings_rows, [55 * mm, 218 * mm], header=False)
    story.append(findings_table)

    if inspection.notes:
        story.append(Spacer(1, 2 * mm))
        notes_table = Table(
            [[_safe_html_p(f"<b>Inspector Notes:</b> {inspection.notes}", small_style)]],
            colWidths=[273 * mm],
        )
        notes_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(notes_table)

    # =========================================================================
    # PAGE 2: COMPLIANCE RULE MATRIX TABLE
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("COMPLIANCE RULE MATRIX", heading_style))
    story.append(Paragraph(
        "Deterministic statutory evaluation of statutory declarations under Legal Metrology (Packaged Commodities) Rules, 2011.",
        subtitle_style,
    ))
    story.append(Spacer(1, 2 * mm))

    # Table columns:
    # 1. Rule ID (23mm)
    # 2. Parameter (36mm)
    # 3. Extracted Value (44mm) -> Declared Net Qty separates value/unit
    # 4. Validation (36mm)
    # 5. Binary (16mm)
    # 6. Status (26mm)
    # 7. Reason (58mm)
    # 8. Regulatory Source (28mm)
    # Total = 267mm (fit within 273mm printable area)

    matrix_headers = [
        _paragraph("Rule ID", th_style),
        _paragraph("Parameter", th_style),
        _paragraph("Extracted Value", th_style),
        _paragraph("Validation", th_style),
        _paragraph("Binary", th_style),
        _paragraph("Status", th_style),
        _paragraph("Reason", th_style),
        _paragraph("Regulatory Source", th_style),
    ]
    matrix_rows = [matrix_headers]

    for idx, r in enumerate(results_list):
        ed = r.evidence_data if isinstance(r.evidence_data, dict) else {}
        param_name = r.parameter or "UNKNOWN"
        rule_def = rules_map.get(r.rule_id)

        # 1. Extracted Value handling (special net quantity decomposition)
        if param_name in ("DECLARED_NET_QUANTITY", "NET_QUANTITY") or r.rule_id == "PC-ALL-002":
            val = ed.get("value") or getattr(r, "value", None)
            unit = ed.get("unit") or getattr(r, "unit", None)
            raw = ed.get("raw_value") or getattr(r, "raw_value", None) or ed.get("value_text")
            val_display = (
                f"<b>Value:</b> {val or '—'}<br/>"
                f"<b>Unit:</b> {unit or '—'}<br/>"
                f"<font color='#64748B'>Raw: \"{raw or '—'}\"</font>"
            )
            extracted_val_p = _safe_html_p(val_display, small_style)
        else:
            extracted_text = ed.get("value") or ed.get("raw_value") or r.message or "—"
            if isinstance(extracted_text, list):
                extracted_text = ", ".join(str(v) for v in extracted_text)
            extracted_val_p = _paragraph(extracted_text, small_style)

        # 2. Validation method
        val_method = ed.get("validation_method") or (rule_def.validation_method if rule_def else "STATUTORY_CHECK")
        val_display = f"<b>Method:</b> {val_method}"
        if param_name in ("DECLARED_NET_QUANTITY", "NET_QUANTITY") or r.rule_id == "PC-ALL-002":
            q_valid = ed.get("quantity_unit_valid")
            if q_valid is not None:
                val_display += f"<br/><b>Quantity & Unit:</b> {'VALID' if q_valid else 'INVALID'}"
        val_p = _safe_html_p(val_display, small_style)

        # 3. Binary Badge
        binary_val = ed.get("binary")
        if binary_val is None:
            if r.status == "PASS":
                binary_val = 1
            elif r.status == "FAIL":
                binary_val = 0
            else:
                binary_val = None

        if binary_val == 1 or r.status == "PASS":
            binary_p = _safe_html_p("<b><font color='#1B5E20'>1</font></b>", small_bold)
        elif binary_val == 0 or r.status == "FAIL":
            binary_p = _safe_html_p("<b><font color='#B71C1C'>0</font></b>", small_bold)
        elif r.status in ("NOT_VERIFIABLE", "NEEDS_REVIEW"):
            binary_p = _safe_html_p("<b><font color='#B45309'>REVIEW</font></b>", small_bold)
        else:
            binary_p = _safe_html_p("<b><font color='#64748B'>N/A</font></b>", small_bold)

        # 4. Status Badge
        if r.status == "PASS":
            status_p = _safe_html_p("<b><font color='#1B5E20'>PASS</font></b>", small_bold)
        elif r.status == "FAIL":
            status_p = _safe_html_p("<b><font color='#B71C1C'>FAIL</font></b>", small_bold)
        elif r.status in ("NOT_VERIFIABLE", "NEEDS_REVIEW"):
            status_p = _safe_html_p("<b><font color='#B45309'>NOT_VERIFIABLE</font></b>", small_bold)
        else:
            status_p = _safe_html_p("<b><font color='#64748B'>NOT_APPLICABLE</font></b>", small_bold)

        # 5. Reason & Regulatory Source
        reason_text = ed.get("reason") or r.message or "—"
        source_text = r.regulatory_source or (rule_def.regulatory_source if rule_def else "LEGAL_METROLOGY")

        row = [
            _paragraph(r.rule_id, small_bold),
            _paragraph(param_name, small_style),
            extracted_val_p,
            val_p,
            binary_p,
            status_p,
            _paragraph(reason_text, small_style),
            _paragraph(source_text, small_style),
        ]
        matrix_rows.append(row)

    # Alternate background shading for matrix rows
    matrix_styles = []
    for r_idx in range(1, len(matrix_rows)):
        if r_idx % 2 == 0:
            matrix_styles.append(('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor('#F8FAFC')))

    matrix_table = _table(
        matrix_rows,
        [23 * mm, 36 * mm, 44 * mm, 36 * mm, 16 * mm, 26 * mm, 58 * mm, 28 * mm],
        header=True,
        custom_style=matrix_styles,
    )
    story.append(matrix_table)

    # =========================================================================
    # PAGE 3: EVIDENCE & PACKAGING PANEL IMAGES
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("INSPECTION EVIDENCE & PANEL IMAGES", heading_style))
    story.append(Paragraph(
        "Packaging images and raw OCR evidence bounding boxes captured during label screening.",
        subtitle_style,
    ))
    story.append(Spacer(1, 2 * mm))

    images_list = inspection.images or []
    if not images_list and inspection.image_path:
        images_list = [
            type('LegacyImage', (), {
                'file_name': inspection.image_path,
                'source': 'UPLOAD',
                'image_index': 0,
            })()
        ]

    # Present up to 4 images in a compact 2-up grid without blowing out pages
    image_cells = []
    for idx, img in enumerate(images_list[:4]):
        path = os.path.join(settings.UPLOAD_DIR, img.file_name)
        if not os.path.exists(path):
            continue
        try:
            from PIL import Image as PILImage
            with PILImage.open(path) as source:
                w, h = source.size
            # Restrict image to 120mm wide x 75mm high
            scale = min((120 * mm) / w, (75 * mm) / h, 1.0)
            target_w = w * scale
            target_h = h * scale
            caption = f"<b>Panel #{idx + 1}</b>: {img.file_name}<br/><font color='#64748B'>Source: {getattr(img, 'source', 'UPLOAD')}</font>"
            cell_flowables = [
                RLImage(path, width=target_w, height=target_h),
                Spacer(1, 1 * mm),
                _safe_html_p(caption, small_style),
            ]
            image_cells.append(cell_flowables)
        except Exception as e:
            logger.warning("Failed to render image %s in PDF: %s", img.file_name, e)

    if image_cells:
        grid_rows = []
        for i in range(0, len(image_cells), 2):
            if i + 1 < len(image_cells):
                grid_rows.append([image_cells[i], image_cells[i + 1]])
            else:
                grid_rows.append([image_cells[i], ""])
        grid_table = Table(grid_rows, colWidths=[136 * mm, 137 * mm])
        grid_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(grid_table)
    else:
        no_img_box = Table(
            [[_paragraph("No packaging image files are available on disk for this inspection record.", small_style)]],
            colWidths=[273 * mm],
        )
        no_img_box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(no_img_box)

    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Extracted Declaration Field Audit", heading_style))

    extracted_headers = [
        _paragraph("Statutory Field", th_style),
        _paragraph("Extracted Text Content", th_style),
        _paragraph("Source", th_style),
        _paragraph("Confidence", th_style),
    ]
    extracted_rows = [extracted_headers]
    for field in (inspection.extracted_fields or []):
        conf_str = f"{int(field.confidence * 100)}%" if field.confidence is not None else "—"
        extracted_rows.append([
            _paragraph(field.field_name, small_bold),
            _paragraph(field.field_value or "—", small_style),
            _paragraph(field.source or "OCR", small_style),
            _paragraph(conf_str, small_style),
        ])

    if len(extracted_rows) == 1:
        extracted_rows.append([_paragraph("No fields extracted.", small_style), _paragraph("—", small_style), _paragraph("—", small_style), _paragraph("—", small_style)])

    extracted_table = _table(extracted_rows, [45 * mm, 160 * mm, 34 * mm, 28 * mm], header=True)
    story.append(extracted_table)

    # =========================================================================
    # PAGE 4: REGULATORY TRACEABILITY, LIMITATIONS & SIGN-OFF
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("REGULATORY TRACEABILITY & STATUTORY SIGN-OFF", heading_style))
    story.append(Paragraph(
        "Legal framework references, system operating limitations, and mandatory authorized officer sign-off.",
        subtitle_style,
    ))
    story.append(Spacer(1, 2 * mm))

    trace_headers = [
        _paragraph("Rule ID", th_style),
        _paragraph("Parameter", th_style),
        _paragraph("Regulatory Source", th_style),
        _paragraph("Rule Reference", th_style),
        _paragraph("Rule Version", th_style),
        _paragraph("Applicability", th_style),
        _paragraph("Source URL / Gazette", th_style),
    ]
    trace_rows = [trace_headers]

    for r in results_list:
        rule_def = rules_map.get(r.rule_id)
        ref = _clean_ref(getattr(r, 'rule_reference', None) or (rule_def.rule_reference if rule_def else None))
        ver = _clean_ref(getattr(r, 'rule_version', None) or (rule_def.rule_version if rule_def else None))
        source_doc = (
            rule_def.source_link if rule_def and rule_def.source_link
            else ("Pending verification" if ref == "Pending verification" else "Official Gazette")
        )
        cat_pkg = f"{getattr(rule_def, 'category', 'ALL')} / {getattr(rule_def, 'package_type', 'ALL')}" if rule_def else "ALL"

        trace_rows.append([
            _paragraph(r.rule_id, small_bold),
            _paragraph(r.parameter, small_style),
            _paragraph(r.regulatory_source or "LEGAL_METROLOGY", small_style),
            _paragraph(ref, small_style),
            _paragraph(ver, small_style),
            _paragraph(cat_pkg, small_style),
            _paragraph(source_doc, small_style),
        ])

    trace_table = _table(trace_rows, [23 * mm, 38 * mm, 33 * mm, 46 * mm, 31 * mm, 35 * mm, 61 * mm], header=True)
    story.append(trace_table)
    story.append(Spacer(1, 3 * mm))

    # Physical Verification & System Limitations callout
    limitations_text = (
        "<b>Physical Verification Requirements (Rule 12 & Rule 24 Statutory Mandate):</b><br/>"
        "The Legal Metrology (Packaged Commodities) Rules, 2011 explicitly require physical verification of net content "
        "using calibrated, certified standard weights and balances at the time of inspection. Principal display panel dimensions, "
        "font heights, and container volumes require direct measurement using certified calipers, gauges, and laboratory apparatus. "
        "OCR and computer vision screen optical label declarations on package graphics only; automated screening does not and cannot "
        "measure actual physical commodity weight, density, gravimetric net fill, or physical font height in millimeters.<br/><br/>"
        "<b>System Limitations:</b> Visual screening is subject to camera sensor resolution, specular packaging reflection, "
        "cylindrical/curved surface warping, creasing, and optical character error rates. Ambiguous or conflicting declarations "
        "require direct physical inspection before any statutory enforcement action is initiated."
    )
    limitations_box = Table(
        [[_safe_html_p(limitations_text, small_style)]],
        colWidths=[273 * mm],
    )
    limitations_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(limitations_box)
    story.append(Spacer(1, 3 * mm))

    # Inspector Review & Sign-Off Block
    inspector_block = [
        [
            _safe_html_p(
                "<b>Inspector Review & Verification Details:</b><br/>"
                f"<b>Name:</b> {inspection.inspector_name or '___________________________'}<br/>"
                "<b>Designation:</b> Legal Metrology Inspector<br/>"
                "<b>Jurisdiction / Zone:</b> ___________________________<br/>"
                f"<b>Inspection Date:</b> {date_str[:10]}",
                small_style,
            ),
            _safe_html_p(
                "<b>Action Taken / Disposition:</b><br/>"
                "[  ] Notice Issued under Section 39 / Rule 32<br/>"
                "[  ] Product Seized / Detained<br/>"
                "[  ] Verified Compliant on Label & Physical Check<br/>"
                "[  ] Sample Sent for Physical / Laboratory Analysis<br/><br/>"
                "<b>Inspector Signature:</b> ___________________________",
                small_style,
            ),
        ]
    ]
    inspector_table = Table(inspector_block, colWidths=[136 * mm, 137 * mm])
    inspector_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FFFFFF')),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(inspector_table)
    story.append(Spacer(1, 2 * mm))

    # Statutory Disclaimer Box
    disclaimer_box = Table(
        [[_safe_html_p(
            f"<b>Statutory Disclaimer:</b> {STATUTORY_DISCLAIMER}",
            ParagraphStyle('DiscP', parent=small_style, alignment=1, textColor=colors.HexColor('#64748B')),
        )]],
        colWidths=[273 * mm],
    )
    disclaimer_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F1F5F9')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#94A3B8')),
        ('PADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(disclaimer_box)

    # Build the document using NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)

    # Manage duplicate reports in database
    existing = (
        db_session.query(models.Report)
        .filter(models.Report.inspection_id == inspection.id)
        .order_by(models.Report.id.desc())
        .all()
    ) if db_session else []

    report = existing[0] if existing else models.Report(inspection_id=inspection.id)
    if existing:
        for duplicate in existing[1:]:
            if duplicate.file_path != file_path and os.path.exists(duplicate.file_path):
                try:
                    os.remove(duplicate.file_path)
                except OSError:
                    pass
            db_session.delete(duplicate)

    report.file_path = file_path
    report.file_name = file_name
    report.generated_at = datetime.now()

    if db_session:
        db_session.add(report)
        db_session.commit()

    logger.info(
        'pdf timing inspection=%s generation_ms=%s file=%s',
        inspection.id,
        round((time.perf_counter() - started) * 1000),
        file_path,
    )
    return report
