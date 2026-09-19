"""Professional 4-page inspection-support ReportLab PDF report generator."""
import logging
import os
import time
import re
from datetime import datetime, timezone, timedelta
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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.core.config import get_settings
from app.core.constants import InspectionStatus, normalize_status
from app.database import models
from app.rules.rule_engine import build_inspection_findings

settings = get_settings()
logger = logging.getLogger(__name__)

# Mandatory statutory disclaimer
STATUTORY_DISCLAIMER = (
    "This software generates automatic package-image screening results. It is not itself a government authority or a statutory certificate."
)

_REGISTERED_UNICODE_FONT = False
_CANONICAL_FONT_NORMAL = "Helvetica"
_CANONICAL_FONT_BOLD = "Helvetica-Bold"
_CANONICAL_FONT_OBLIQUE = "Helvetica-Oblique"
_CANONICAL_FONT_BOLD_OBLIQUE = "Helvetica-BoldOblique"


def _setup_pdf_fonts() -> None:
    """Discover and register system TrueType fonts supporting Unicode / Indian Rupee symbol (₹).
    Falls back gracefully to Helvetica with safe text rendering when no suitable TTF is found.
    """
    global _REGISTERED_UNICODE_FONT, _CANONICAL_FONT_NORMAL, _CANONICAL_FONT_BOLD, _CANONICAL_FONT_OBLIQUE, _CANONICAL_FONT_BOLD_OBLIQUE
    if _REGISTERED_UNICODE_FONT:
        return

    candidates = [
        # Windows standard fonts with U+20B9 Rupee glyph
        {
            "family": "LMAI-Sans",
            "normal": "C:/Windows/Fonts/arial.ttf",
            "bold": "C:/Windows/Fonts/arialbd.ttf",
            "italic": "C:/Windows/Fonts/ariali.ttf",
            "boldItalic": "C:/Windows/Fonts/arialbi.ttf",
        },
        {
            "family": "LMAI-Sans",
            "normal": "C:/Windows/Fonts/segoeui.ttf",
            "bold": "C:/Windows/Fonts/segoeuib.ttf",
            "italic": "C:/Windows/Fonts/segoeuii.ttf",
            "boldItalic": "C:/Windows/Fonts/segoeuiz.ttf",
        },
        # Linux standard fonts
        {
            "family": "LMAI-Sans",
            "normal": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "italic": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
            "boldItalic": "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
        },
        {
            "family": "LMAI-Sans",
            "normal": "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "bold": "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "italic": "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
            "boldItalic": "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
        },
        {
            "family": "LMAI-Sans",
            "normal": "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "bold": "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "italic": "/usr/share/fonts/dejavu/DejaVuSans-Oblique.ttf",
            "boldItalic": "/usr/share/fonts/dejavu/DejaVuSans-BoldOblique.ttf",
        },
        {
            "family": "LMAI-Sans",
            "normal": "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "bold": "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            "italic": "/usr/share/fonts/truetype/freefont/FreeSansOblique.ttf",
            "boldItalic": "/usr/share/fonts/truetype/freefont/FreeSansBoldOblique.ttf",
        },
    ]

    for cand in candidates:
        normal_path = cand["normal"]
        if os.path.exists(normal_path):
            try:
                fam = cand["family"]
                bold_path = cand.get("bold") if cand.get("bold") and os.path.exists(cand["bold"]) else normal_path
                italic_path = cand.get("italic") if cand.get("italic") and os.path.exists(cand["italic"]) else normal_path
                bi_path = cand.get("boldItalic") if cand.get("boldItalic") and os.path.exists(cand["boldItalic"]) else bold_path

                pdfmetrics.registerFont(TTFont(fam, normal_path))
                pdfmetrics.registerFont(TTFont(f"{fam}-Bold", bold_path))
                pdfmetrics.registerFont(TTFont(f"{fam}-Italic", italic_path))
                pdfmetrics.registerFont(TTFont(f"{fam}-BoldItalic", bi_path))

                pdfmetrics.registerFontFamily(
                    fam,
                    normal=fam,
                    bold=f"{fam}-Bold",
                    italic=f"{fam}-Italic",
                    boldItalic=f"{fam}-BoldItalic",
                )
                _CANONICAL_FONT_NORMAL = fam
                _CANONICAL_FONT_BOLD = f"{fam}-Bold"
                _CANONICAL_FONT_OBLIQUE = f"{fam}-Italic"
                _CANONICAL_FONT_BOLD_OBLIQUE = f"{fam}-BoldItalic"
                _REGISTERED_UNICODE_FONT = True
                logger.info("Registered Unicode TrueType font %s from %s", fam, normal_path)
                return
            except Exception as e:
                logger.warning("Could not register font %s: %s", normal_path, e)

    _REGISTERED_UNICODE_FONT = False


_setup_pdf_fonts()


def _clean_pdf_text(text: str) -> str:
    """Ensure characters that standard fonts cannot display are safely represented."""
    if not _REGISTERED_UNICODE_FONT:
        # Fallback when running on Type 1 Helvetica without Unicode glyph U+20B9
        return text.replace("₹", "Rs. ")
    return text


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
            self.setFont(_CANONICAL_FONT_BOLD, 8)
            self.setFillColor(colors.HexColor("#173F5F"))
            self.drawString(12 * mm, height - 10 * mm, "LMAI INSPECTOR")
            self.setFont(_CANONICAL_FONT_NORMAL, 8)
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

        self.setFont(_CANONICAL_FONT_OBLIQUE, 7.5)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(12 * mm, 8 * mm, STATUTORY_DISCLAIMER)

        self.setFont(_CANONICAL_FONT_NORMAL, 7.5)
        self.drawRightString(width - 12 * mm, 8 * mm, f"Page {self._pageNumber} of {total_pages}")

        self.restoreState()


def _paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    """Safely escape text for ReportLab Paragraphs and preserve breaks."""
    if value is None:
        text = "—"
    else:
        text = str(value)
    text = _clean_pdf_text(text)
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
    return Paragraph(_clean_pdf_text(html_text), style)


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


def generate_inspection_pdf(inspection: models.Inspection, db_session: Optional[Any] = None) -> models.Report:
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
        fontName=_CANONICAL_FONT_BOLD,
        fontSize=17,
        leading=21,
        textColor=colors.HexColor('#173F5F'),
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        fontName=_CANONICAL_FONT_NORMAL,
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#475569'),
    )
    heading_style = ParagraphStyle(
        'SectionHeading',
        fontName=_CANONICAL_FONT_BOLD,
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#173F5F'),
        spaceBefore=6,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        'TableBody',
        fontName=_CANONICAL_FONT_NORMAL,
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor('#1E293B'),
    )
    body_bold = ParagraphStyle(
        'TableBodyBold',
        fontName=_CANONICAL_FONT_BOLD,
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor('#1E293B'),
    )
    small_style = ParagraphStyle(
        'TableSmall',
        fontName=_CANONICAL_FONT_NORMAL,
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#334155'),
    )
    small_bold = ParagraphStyle(
        'TableSmallBold',
        fontName=_CANONICAL_FONT_BOLD,
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#0F172A'),
    )
    th_style = ParagraphStyle(
        'TableHeader',
        fontName=_CANONICAL_FONT_BOLD,
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

    # Deduplicate rule results by rule_id preserving order (Single Source of Truth)
    seen_rule_ids = set()
    deduped_results = []
    for r in (inspection.rule_results or []):
        rid = getattr(r, 'rule_id', None) or (r.get('rule_id') if isinstance(r, dict) else None)
        if rid and rid in seen_rule_ids:
            continue
        if rid:
            seen_rule_ids.add(rid)
        deduped_results.append(r)
    results_list = deduped_results

    # Collect package-image evidence items.
    all_evidences = []
    if hasattr(inspection, 'evidence_items') and inspection.evidence_items:
        all_evidences.extend(inspection.evidence_items)
    elif hasattr(inspection, 'evidences') and inspection.evidences:
        all_evidences.extend(inspection.evidences)
    if db_session:
        try:
            db_ev = db_session.query(models.Evidence).filter(models.Evidence.inspection_id == inspection.id).all()
            for ev in db_ev:
                if ev not in all_evidences:
                    all_evidences.append(ev)
        except Exception as e:
            logger.warning("Could not query DB evidences: %s", e)

    # Compute summary counters and overall status using shared rule_engine methods
    from app.rules.rule_engine import calculate_rule_summary, derive_overall_result
    summary_counts = calculate_rule_summary(results_list)
    passed_count = summary_counts['passed']
    failed_count = summary_counts['failed']
    review_count = summary_counts['review']
    na_count = summary_counts['not_applicable']

    # Determine canonical overall result from the final rule-result collection (or inspection fallback if empty)
    if results_list:
        derived_overall = derive_overall_result(results_list)
        canonical_result = normalize_status(derived_overall) or InspectionStatus.NOT_VERIFIABLE
    else:
        canonical_result = normalize_status(inspection.overall_result) or InspectionStatus.NOT_VERIFIABLE
    if canonical_result == InspectionStatus.COMPLIANT:
        overall_label = "COMPLIANT"
        overall_bg = colors.HexColor('#E8F5E9')
        overall_border = colors.HexColor('#2E7D32')
        overall_color = '#1B5E20'
        overall_desc = "All detected package declarations passed the applicable automatic checks."
    elif canonical_result == InspectionStatus.NON_COMPLIANT:
        overall_label = "NON-COMPLIANT"
        overall_bg = colors.HexColor('#FFEBEE')
        overall_border = colors.HexColor('#C62828')
        overall_color = '#B71C1C'
        overall_desc = "One or more mandatory statutory declarations failed deterministic validation requirements."
    else:
        overall_label = "NOT_VERIFIABLE"
        overall_bg = colors.HexColor('#FFF8E1')
        overall_border = colors.HexColor('#F57F17')
        overall_color = '#B45309'
        overall_desc = "Some package details could not be read clearly or verified from the submitted images."

    # Context is detected from package evidence; unknown values remain explicit.
    pkg_display = inspection.package_type or "NOT_DETECTED"
    import_display = inspection.import_status or "NOT_DETECTED"

    ist_tz = timezone(timedelta(hours=5, minutes=30), name="IST")
    if inspection.created_at:
        dt = inspection.created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        date_str = dt.astimezone(ist_tz).strftime("%d-%b-%Y %I:%M:%S %p IST")
    else:
        date_str = datetime.now(timezone.utc).astimezone(ist_tz).strftime("%d-%b-%Y %I:%M:%S %p IST")

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
                    "LMAI Inspector — Automated Legal Metrology Inspection Screening System (v1.0.0)<br/>"
                    "<font color='#64748B'>Regulatory screening baseline reviewed against authoritative sources under LM(PC) Rules, 2011</font>",
                    subtitle_style,
                ),
                _safe_html_p(
                    "<b>Processing:</b> Automatic package-image analysis<br/>"
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

    # Derive dynamic regulatory snapshot
    inspect_dt_str = inspection.created_at.strftime('%Y-%m-%d') if inspection.created_at else datetime.now(timezone.utc).strftime('%Y-%m-%d')
    reg_snapshot = getattr(inspection, 'regulatory_snapshot', None)
    if not reg_snapshot:
        from app.rules.status_safety import derive_dynamic_regulatory_snapshot
        snapshot_meta = derive_dynamic_regulatory_snapshot(None, inspect_dt_str)
        reg_snapshot = snapshot_meta['snapshot_id']
    reg_snapshot_label = f"Effective for inspection date: {inspect_dt_str}"

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
        [
            _paragraph("Regulatory Snapshot", body_bold),
            _paragraph(reg_snapshot, small_style),
            _paragraph("Traceability Baseline", body_bold),
            _paragraph(reg_snapshot_label, small_style),
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

    # 4. Summary Metrics Cards (Passed, Failed, Not Verifiable, Not Applicable)
    summary_cards = [
        [
            _safe_html_p(f"<font size='13' color='#1B5E20'><b>{passed_count}</b></font><br/><font size='7.5' color='#1B5E20'><b>PASSED</b></font>", ParagraphStyle('Card1', parent=body_style, alignment=1)),
            _safe_html_p(f"<font size='13' color='#B71C1C'><b>{failed_count}</b></font><br/><font size='7.5' color='#B71C1C'><b>FAILED</b></font>", ParagraphStyle('Card2', parent=body_style, alignment=1)),
            _safe_html_p(f"<font size='13' color='#B45309'><b>{review_count}</b></font><br/><font size='7.5' color='#B45309'><b>NOT VERIFIABLE</b></font>", ParagraphStyle('Card3', parent=body_style, alignment=1)),
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

    # 5. Key Findings Breakdown & Automatic Observations
    story.append(Paragraph("Inspection Findings & Field Observations", heading_style))
    findings = build_inspection_findings([
        {'parameter': r.parameter, 'status': r.status, 'message': r.message}
        for r in results_list
    ])
    findings_rows = []
    if findings['failed']:
        findings_rows.append([
            _safe_html_p(f"<b><font color='#B71C1C'>Critical Violations ({len(findings['failed'])}):</font></b>", small_bold),
            _safe_html_p(", ".join(findings['failed']), small_style),
        ])
    if findings['needs_review']:
        findings_rows.append([
            _safe_html_p(f"<b><font color='#B45309'>Not Detected ({len(findings['needs_review'])}):</font></b>", small_bold),
            _safe_html_p(", ".join(findings['needs_review']), small_style),
        ])
    if findings['verified']:
        findings_rows.append([
            _safe_html_p(f"<b><font color='#1B5E20'>Verified Declarations ({len(findings['verified'])}):</font></b>", small_bold),
            _safe_html_p(", ".join(findings['verified']), small_style),
        ])
    if not findings_rows:
        findings_rows.append([_paragraph("No specific finding categories available.", small_style), _paragraph("—", small_style)])

    findings_table = _table(findings_rows, [55 * mm, 218 * mm], header=False)
    story.append(findings_table)


    # =========================================================================
    # PAGE 2: COMPLIANCE RULE MATRIX TABLE
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("COMPLIANCE RULE MATRIX", heading_style))
    story.append(Paragraph(
        "Deterministic rule-based screening against the versioned regulatory traceability baseline under Legal Metrology (Packaged Commodities) Rules, 2011 and applicable statutory instruments.",
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
            if ed.get("is_multipack") or getattr(r, "is_multipack", False):
                decl_expr = ed.get("declared_expression") or val or raw
                pack_cnt = ed.get("pack_count") or getattr(r, "pack_count", "—")
                unit_qty = ed.get("unit_quantity") or ed.get("unit_net_quantity") or getattr(r, "unit_quantity", "—")
                derived_tot = ed.get("derived_total_quantity") or getattr(r, "derived_total_quantity", "—")
                val_display = (
                    f"<b>Expression:</b> {decl_expr or '—'}<br/>"
                    f"<b>Pack Count:</b> {pack_cnt} &nbsp;|&nbsp; <b>Unit Qty:</b> {unit_qty} {unit or ''}<br/>"
                    f"<b>Derived Total:</b> {derived_tot} {unit or ''} <i>(derived)</i><br/>"
                    f"<font color='#64748B'>Raw: \"{raw or '—'}\"</font>"
                )
            else:
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

        # 1. Extracted value handling, including printed multipack decomposition.
        if param_name in ("DECLARED_NET_QUANTITY", "NET_QUANTITY") or r.rule_id == "PC-ALL-002":
            val = ed.get("value") or getattr(r, "value", None)
            unit = ed.get("unit") or getattr(r, "unit", None)
            raw = ed.get("raw_value") or getattr(r, "raw_value", None) or ed.get("value_text")
            if ed.get("is_multipack") or getattr(r, "is_multipack", False):
                decl_expr = ed.get("declared_expression") or val or raw
                pack_cnt = ed.get("pack_count") or getattr(r, "pack_count", "—")
                unit_qty = ed.get("unit_quantity") or ed.get("unit_net_quantity") or getattr(r, "unit_quantity", "—")
                derived_tot = ed.get("derived_total_quantity") or getattr(r, "derived_total_quantity", "—")
                val_display = (
                    f"<b>Expression:</b> {decl_expr or '—'}<br/>"
                    f"<b>Pack Count:</b> {pack_cnt} &nbsp;|&nbsp; <b>Unit Qty:</b> {unit_qty} {unit or ''}<br/>"
                    f"<b>Derived Total:</b> {derived_tot} {unit or ''} <i>(derived)</i><br/>"
                    f"<font color='#64748B'>Raw: \"{raw or '—'}\"</font>"
                )
            else:
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
            binary_p = _safe_html_p("<b><font color='#B45309'>NOT DETECTED</font></b>", small_bold)
        else:
            binary_p = _safe_html_p("<b><font color='#64748B'>N/A</font></b>", small_bold)

        # 4. Status Badge
        if r.status == "PASS":
            status_p = _safe_html_p("<b><font color='#1B5E20'>PASS</font></b>", small_bold)
        elif r.status == "FAIL":
            status_p = _safe_html_p("<b><font color='#B71C1C'>FAIL</font></b>", small_bold)
        elif r.status in ("NOT_VERIFIABLE", "NEEDS_REVIEW"):
            status_p = _safe_html_p("<b><font color='#B45309'>NOT DETECTED</font></b>", small_bold)
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
    story.append(Paragraph(
        "Traceable audit of declarations detected from package images.",
        subtitle_style,
    ))
    story.append(Spacer(1, 1.5 * mm))

    extracted_headers = [
        _paragraph("Statutory Declaration", th_style),
        _paragraph("Original Extracted Value (OCR)", th_style),
        _paragraph("Detected Value", th_style),
        _paragraph("Source", th_style),
        _paragraph("Audit Status", th_style),
    ]
    extracted_rows = [extracted_headers]
    for field in (inspection.extracted_fields or []):
        param = field.field_name
        orig_val = field.field_value
        verified_display = "<font color='#64748B'>As detected</font>"
        conf_pct = f"{int(field.confidence * 100)}%" if field.confidence is not None else "—"
        method_display = f"<b>{field.source or 'OCR'}</b> (Conf: {conf_pct})"
        status_display = "<font color='#334155'>IMAGE EVIDENCE</font>"

        extracted_rows.append([
            _paragraph(param, small_bold),
            _paragraph(orig_val or "—", small_style),
            _safe_html_p(verified_display, small_style),
            _safe_html_p(method_display, small_style),
            _safe_html_p(status_display, small_style),
        ])

    if len(extracted_rows) == 1:
        extracted_rows.append([
            _paragraph("No fields extracted.", small_style),
            _paragraph("—", small_style),
            _paragraph("—", small_style),
            _paragraph("—", small_style),
            _paragraph("—", small_style),
        ])

    extracted_table = _table(extracted_rows, [40 * mm, 72 * mm, 72 * mm, 47 * mm, 42 * mm], header=True)
    story.append(extracted_table)

    # =========================================================================
    # PAGE 4: REGULATORY TRACEABILITY & STATUTORY SIGN-OFF
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("REGULATORY TRACEABILITY & STATUTORY SIGN-OFF", heading_style))
    story.append(Paragraph(
        "Legal framework references, statutory sign-off, and system operating limitations.",
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
            getattr(rule_def, 'source_url', None) or getattr(rule_def, 'source_link', None)
            if rule_def and (getattr(rule_def, 'source_url', None) or getattr(rule_def, 'source_link', None))
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

    # System limitations and extraction provenance
    limitations_text = (
        "<b>System Limitations:</b> OCR and computer vision screen optical label declarations on package graphics only. "
        "Evidence extraction: PaddleOCR + Gemini-assisted semantic extraction (or deterministic fallback when offline). "
        "Compliance evaluation: Deterministic regulatory rule engine. "
        "Final statutory verification remains subject to authorised inspection where physical measurements or unresolved evidence is required. "
        "The report shows only information read from the package images. Unreadable or missing text is marked NOT DETECTED."
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

    # Automatic result summary.
    review_summary_text = ""

    automatic_result_block = [
        [
            _safe_html_p(
                "<b>Automatic inspection:</b><br/>"
                f"<b>Inspection ID:</b> #{inspection.id}<br/>"
                f"<b>Inspection Date:</b> {date_str}"
                f"{review_summary_text}",
                small_style,
            ),
            _safe_html_p(
                f"<b>Overall result:</b> {canonical_result}<br/>"
                "The result was generated automatically from the submitted package images.",
                small_style,
            ),
        ]
    ]
    automatic_result_table = Table(automatic_result_block, colWidths=[136 * mm, 137 * mm])
    automatic_result_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FFFFFF')),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(automatic_result_table)
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
