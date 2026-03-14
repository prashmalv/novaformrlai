"""
PDF Generator: produces Nova Formworks-style quotation PDF.
"""
import os
from datetime import date
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from src.models.element import ProjectBOQ, ElementBOQ
from src.output.boq_generator import aggregate_project_boq

PAGE_W, PAGE_H = A4

# Colors
NOVA_BLUE = colors.HexColor('#1a3a5c')
NOVA_LIGHT = colors.HexColor('#dce8f5')
HEADER_BG = colors.HexColor('#2c5f8a')
GRAY = colors.HexColor('#e8e8e8')
WHITE = colors.white
BLACK = colors.black


def _styles():
    s = getSampleStyleSheet()
    return {
        'company': ParagraphStyle('company', fontSize=14, fontName='Helvetica-Bold',
                                  textColor=WHITE, alignment=TA_CENTER, spaceAfter=2),
        'tagline': ParagraphStyle('tagline', fontSize=8, fontName='Helvetica',
                                  textColor=WHITE, alignment=TA_CENTER),
        'title': ParagraphStyle('title', fontSize=11, fontName='Helvetica-Bold',
                                textColor=NOVA_BLUE, alignment=TA_CENTER, spaceAfter=4),
        'label': ParagraphStyle('label', fontSize=8, fontName='Helvetica-Bold',
                                textColor=BLACK),
        'normal': ParagraphStyle('normal', fontSize=8, fontName='Helvetica',
                                 textColor=BLACK),
        'small': ParagraphStyle('small', fontSize=7, fontName='Helvetica',
                                textColor=colors.grey),
        'warn': ParagraphStyle('warn', fontSize=7, fontName='Helvetica-Oblique',
                               textColor=colors.red),
        'section': ParagraphStyle('section', fontSize=9, fontName='Helvetica-Bold',
                                  textColor=NOVA_BLUE, spaceBefore=6, spaceAfter=2),
        'total': ParagraphStyle('total', fontSize=9, fontName='Helvetica-Bold',
                                textColor=BLACK),
    }


def _header_table(project: ProjectBOQ, st: dict):
    """Company header block."""
    company_info = [
        Paragraph("NOVA FORMWORKS PVT LTD", st['company']),
        Paragraph("A-7/121-124 South Side of GT Road Indl.Area Ghaziabad (UP)", st['tagline']),
        Paragraph("Email: info@novaformworks.com  |  Mob: +91-93 10 69 54 40", st['tagline']),
    ]
    header = Table(
        [[company_info]],
        colWidths=[PAGE_W - 40 * mm]
    )
    header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NOVA_BLUE),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    return header


def _client_info_table(project: ProjectBOQ, st: dict, panel_height_mm: float):
    today = project.date or date.today().strftime("%d-%m-%Y")
    data = [
        ['Client:', project.client_name or '—',
         'IPO No:', project.ipo_no or '—'],
        ['Address:', project.client_address or '—',
         'Date:', today],
        ['Project:', project.project_name or '—',
         'Height:', f"{int(panel_height_mm)}MM"],
    ]
    col_w = [20 * mm, 60 * mm, 20 * mm, 50 * mm]
    t = Table(data, colWidths=col_w)
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, GRAY),
        ('BACKGROUND', (0, 0), (0, -1), NOVA_LIGHT),
        ('BACKGROUND', (2, 0), (2, -1), NOVA_LIGHT),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def _element_boq_table(eboq: ElementBOQ, st: dict):
    """Per-element panel table."""
    elem = eboq.element
    title_text = (f"{elem.label}  |  {elem.element_type.value}  |  "
                  f"{elem.length_mm:.0f}×{elem.width_mm:.0f}mm  |  "
                  f"H = {elem.height_mm:.0f}mm  |  "
                  f"Qty = {elem.quantity}  |  Height achieved: {eboq.height_note}")
    title = Paragraph(title_text, st['label'])

    headers = ['Panel Size', 'Qty', 'Area/Panel (sqm)', 'Total Area (sqm)']
    rows = [headers]
    for p in eboq.panels:
        rows.append([
            p.size_label,
            str(p.quantity),
            f"{p.area_sqm:.4f}",
            f"{p.total_area_sqm:.4f}",
        ])

    col_w = [50 * mm, 20 * mm, 40 * mm, 40 * mm]
    t = Table(rows, colWidths=col_w)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('GRID', (0, 0), (-1, -1), 0.5, GRAY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, NOVA_LIGHT]),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))

    items = [title, Spacer(1, 2 * mm), t]

    if eboq.spacer_mm > 0:
        items.append(Paragraph(
            f"  ⚠ Spacer required: {eboq.spacer_mm:.0f}mm", st['warn']))
    for w in eboq.warnings:
        items.append(Paragraph(f"  ⚠ {w}", st['warn']))

    return items


def _summary_table(agg: dict, st: dict):
    """Aggregated panel summary table."""
    headers = ['Panel Size', 'Unit Area (sqm)', 'Total Qty', 'Total Area (sqm)', 'Rate/sqm', 'Amount']
    rows = [headers]

    rate = agg['rate_per_sqm']
    for key, d in agg['summary_panels'].items():
        amount = d['area_sqm'] * rate
        rows.append([
            key,
            f"{d['unit_area_sqm']:.4f}",
            str(d['quantity']),
            f"{d['area_sqm']:.4f}",
            f"{rate:.2f}" if rate else "—",
            f"{amount:,.2f}" if rate else "—",
        ])

    col_w = [40 * mm, 30 * mm, 20 * mm, 30 * mm, 22 * mm, 28 * mm]
    t = Table(rows, colWidths=col_w)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('GRID', (0, 0), (-1, -1), 0.5, GRAY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, NOVA_LIGHT]),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    return t


def _totals_table(agg: dict, project: ProjectBOQ, st: dict):
    """Cost summary / grand total table."""
    rate = agg['rate_per_sqm']
    rows = [
        ['TOTAL PANEL AREA', '', f"{agg['total_area_sqm']:.4f} sqm"],
        ['No. of Sets', '', str(agg['num_sets'])],
        ['Panel Rate', '', f"₹ {rate:,.2f} / sqm" if rate else "Not set"],
        ['Total Panel Cost', '', f"₹ {agg['total_panel_cost']:,.2f}"],
    ]
    if agg['freight_amount']:
        rows.append(['Freight Charges', '', f"₹ {agg['freight_amount']:,.2f}"])
    if project.gst_enabled:
        rows.append(['GST @ 18%', '', f"₹ {agg['gst_amount']:,.2f}"])
    rows.append(['GRAND TOTAL', '', f"₹ {agg['grand_total']:,.2f}"])

    col_w = [70 * mm, 30 * mm, 50 * mm]
    t = Table(rows, colWidths=col_w)
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -2), 'Helvetica'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, -1), (-1, -1), NOVA_BLUE),
        ('TEXTCOLOR', (0, -1), (-1, -1), WHITE),
        ('GRID', (0, 0), (-1, -1), 0.5, GRAY),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return t


def _accessories_table(acc_agg: dict, st: dict):
    """Accessories summary table for PDF."""
    if not acc_agg:
        return None
    headers = ['Accessory', 'Qty (nos)', 'Unit Size', 'Total (m)']
    rows = [headers]
    for key, d in acc_agg.items():
        rows.append([
            key,
            str(int(d['quantity'])),
            f"{d['length_m']:.1f}m" if d['length_m'] else "—",
            f"{d['total_length_m']:.1f}m" if d['total_length_m'] else "—",
        ])
    col_w = [70 * mm, 25 * mm, 30 * mm, 25 * mm]
    t = Table(rows, colWidths=col_w)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('GRID', (0, 0), (-1, -1), 0.5, GRAY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, NOVA_LIGHT]),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    return t


def generate_pdf(project: ProjectBOQ, panel_height_mm: float, output_path: str,
                 acc_agg: dict = None) -> str:
    """
    Generate a PDF quotation for the project.
    Returns the output file path.
    """
    agg = aggregate_project_boq(project)
    st = _styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=15 * mm, leftMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )

    story = []

    # Header
    story.append(_header_table(project, st))
    story.append(Spacer(1, 3 * mm))

    # Title
    story.append(Paragraph("COLUMN &amp; SHEAR WALL FORMWORK QUOTATION", st['title']))
    story.append(Spacer(1, 2 * mm))

    # Client info
    story.append(_client_info_table(project, st, panel_height_mm))
    story.append(Spacer(1, 4 * mm))

    # Per-element BOQs
    story.append(Paragraph("A — Per Element Formwork Details", st['section']))
    story.append(HRFlowable(width="100%", thickness=1, color=NOVA_BLUE))
    story.append(Spacer(1, 2 * mm))

    for eboq in project.element_boqs:
        items = _element_boq_table(eboq, st)
        story.extend(items)
        story.append(Spacer(1, 3 * mm))

    # Summary table
    story.append(Paragraph("B — Consolidated Panel Summary", st['section']))
    story.append(HRFlowable(width="100%", thickness=1, color=NOVA_BLUE))
    story.append(Spacer(1, 2 * mm))
    story.append(_summary_table(agg, st))
    story.append(Spacer(1, 4 * mm))

    # Accessories
    if acc_agg:
        story.append(Paragraph("B — Accessories Summary (Estimated)", st['section']))
        story.append(HRFlowable(width="100%", thickness=1, color=NOVA_BLUE))
        story.append(Spacer(1, 2 * mm))
        acc_tbl = _accessories_table(acc_agg, st)
        if acc_tbl:
            story.append(acc_tbl)
        story.append(Paragraph(
            "⚠ Accessory quantities are estimated. Verify with site engineer before ordering.",
            st['warn']
        ))
        story.append(Spacer(1, 4 * mm))

    # Totals
    story.append(Paragraph("C — Cost Summary", st['section']))
    story.append(HRFlowable(width="100%", thickness=1, color=NOVA_BLUE))
    story.append(Spacer(1, 2 * mm))
    story.append(_totals_table(agg, project, st))
    story.append(Spacer(1, 4 * mm))

    # Footer note
    story.append(Paragraph(
        "Note: This is a computer-generated quotation. All quantities are subject to "
        "field verification. Freight charges as applicable. GST extra as applicable.",
        st['small']
    ))

    doc.build(story)
    return output_path
