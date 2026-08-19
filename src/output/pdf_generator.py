"""
PDF Generator — Nova Formworks BOQ and Quotation documents.
Updated to match 2025 brand guidelines and new templates.
"""
import io
import re
from datetime import date, timedelta
from pathlib import Path
from collections import defaultdict, OrderedDict

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable, Image, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from src.models.element import ProjectBOQ, ElementBOQ

_LOGO_PATH = Path(__file__).parent.parent.parent / "assets" / "images" / "NovaLogo.png"
PAGE_W, PAGE_H = A4
MARGIN = 15 * mm
CW = PAGE_W - 2 * MARGIN          # usable content width (~180mm)

# ── Brand Colors (2025 guidelines) ────────────────────────────────────────────
NOVA_PURPLE = colors.HexColor('#7d2354')
NOVA_NAVY   = colors.HexColor('#3a516f')
NOVA_NIGHT  = colors.HexColor('#232323')
NOVA_SMOKE  = colors.HexColor('#F4F4F4')
NOVA_WHITE  = colors.white
NOVA_LIGHT  = colors.HexColor('#f5e8ef')   # very light purple, alternating rows

# ── Nova contact info (matches templates) ─────────────────────────────────────
_NOVA_ADDR     = "A-7/121-124 South Side of GT Road Indl. Area, Ghaziabad (UP)"
_NOVA_BOQ_EMAIL  = "rawatkaran7412@gmail.com"
_NOVA_BOQ_PHONE  = "7819998963"
_NOVA_QTN_EMAIL  = "hiren.jadav@novaformworks.com"
_NOVA_QTN_PHONE  = "9211377073"

_TC_POINTS = [
    "Freight Charges: Freight charges are in the client's scope.",
    "Accessories: Accessories (props) will be charged extra as per requirement.",
    "Payment Terms: 50% advance along with the Purchase Order and the remaining 50% before dispatch.",
    "Delayed Payments: Simple interest @ 24% per annum will be charged from the due date for any delayed payments.",
    "Dispatch Timeline: Dispatch within 7-10 days from date of drawing approval and advance receipt.",
    "Loading & Unloading: Loading is in the supplier's scope; unloading charges are in the buyer's scope.",
    "Site Engineering Charges: Training, travel, and accommodation charges are in the buyer's scope.",
    "Replacement of Old/Used Materials: 1 new panel against 4 old panels. Freight for replacement in buyer's scope.",
    "Documentation for Replacement: Buyer must issue Delivery Challan and/or Tax Invoice with E-Way bill.",
    "Taxes: GST and other applicable government taxes will be charged extra.",
    "Billing Details: Please verify HSN/SAC codes and billing details to avoid changes in final tax invoice.",
    "Jurisdiction: Any disputes shall be subject to Delhi jurisdiction only.",
    "Validity: The quotation is valid for 7 days from the date of issue.",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _styles() -> dict:
    return {
        'title':   ParagraphStyle('title',   fontSize=14, fontName='Helvetica-Bold',
                                  textColor=NOVA_NIGHT,   alignment=TA_CENTER),
        'sub':     ParagraphStyle('sub',     fontSize=9,  fontName='Helvetica',
                                  textColor=NOVA_NIGHT,   alignment=TA_CENTER),
        'label':   ParagraphStyle('label',   fontSize=8,  fontName='Helvetica-Bold',
                                  textColor=NOVA_NIGHT),
        'normal':  ParagraphStyle('normal',  fontSize=8,  fontName='Helvetica',
                                  textColor=NOVA_NIGHT),
        'small':   ParagraphStyle('small',   fontSize=7,  fontName='Helvetica',
                                  textColor=colors.grey),
        'section': ParagraphStyle('section', fontSize=9,  fontName='Helvetica-Bold',
                                  textColor=NOVA_NIGHT,   spaceBefore=5, spaceAfter=2),
        'warn':    ParagraphStyle('warn',    fontSize=7,  fontName='Helvetica-Oblique',
                                  textColor=colors.red),
        'tc':      ParagraphStyle('tc',      fontSize=7.5, fontName='Helvetica',
                                  textColor=NOVA_NIGHT,   leading=11),
        'prepared':ParagraphStyle('prep',    fontSize=8,  fontName='Helvetica-Bold',
                                  textColor=NOVA_NIGHT),
    }


def _fmt_panel(size_label: str) -> str:
    """Convert 'OC80X3200' → 'Outer Corner 80*3200', '600X3200' → 'Panel 600*3200'."""
    if size_label.startswith('(OC+'):
        m = re.match(r'\(OC\+(\d+)\+OC\)X(\d+)', size_label)
        return f"Beam Bottom (OC+{m.group(1)}+OC)*{m.group(2)}" if m else size_label
    if size_label.startswith('OC'):
        m = re.match(r'OC(\d+)X(\d+)', size_label)
        return f"Outer Corner {m.group(1)}*{m.group(2)}" if m else size_label
    if size_label.startswith('IC'):
        m = re.match(r'IC(\d+)X(\d+)', size_label)
        return f"Inner Corner {m.group(1)}*{m.group(2)}" if m else size_label
    m = re.match(r'(\d+)X(\d+)', size_label)
    return f"Panel {m.group(1)}*{m.group(2)}" if m else size_label


def _fmt_acc(size_label: str) -> tuple[str, str]:
    """
    Convert 'WALLER 1.2M' → ('accessories - waller - 1.2', 'nos')
    Convert 'TIE ROD 16MM (1.5M)' → ('accessories - tie_rod - 1.5 (16 MM)', 'nos')
    Returns (display_name, uom).
    """
    sl = size_label.upper()
    if 'WALLER' in sl:
        m = re.search(r'(\d+\.?\d*)\s*M', sl)
        size = m.group(1) if m else '?'
        return f"accessories - waller - {size}", "nos"
    if 'TIE ROD' in sl or 'TIEROD' in sl:
        m = re.search(r'\((\d+\.?\d*)M\)', sl) or re.search(r'(\d+\.?\d*)M', sl)
        size = m.group(1) if m else '?'
        return f"accessories - tie_rod - {size} (16 MM)", "nos"
    if 'WING NUT' in sl or 'WINGNUT' in sl:
        return "accessories - wing_nut", "nos"
    if 'PVC CONE' in sl or 'CONE' in sl:
        return "accessories - pvc_cone", "nos"
    if 'ANCHOR' in sl or 'NUT' in sl:
        return "accessories - anchor_nut - 100", "nos"
    if 'PIN' in sl:
        m = re.search(r'(\d+)', sl)
        size = m.group(1) if m else '?'
        return f"accessories - pin_{size}mm", "nos"
    return f"accessories - {size_label.lower()}", "nos"


def _natural_key(label: str) -> list:
    """Natural sort key: 'C10' sorts after 'C9', not after 'C1'."""
    import re as _re
    return [int(p) if p.isdigit() else p.upper() for p in _re.split(r'(\d+)', label)]


def _group_boqs(element_boqs: list) -> list[dict]:
    """One entry per element, sorted by natural label order (C1, C2 … C10, SW1 …)."""
    sorted_boqs = sorted(element_boqs, key=lambda b: _natural_key(b.element.label))
    return [
        {
            'boq':       boq,
            'count':     max(1, boq.element.quantity),
            'labels':    [boq.element.label],
            'height_mm': boq.element.height_mm,
        }
        for boq in sorted_boqs
    ]


def _ts(cmds):
    return TableStyle(cmds)


# ── Shared header block ───────────────────────────────────────────────────────

def _logo_title_block(doc_title: str, number_label: str, number_val: str,
                      date_str: str, valid_until: str = "") -> list:
    """Returns story items for the top of any Nova document."""
    story = []
    logo_w, logo_h = 38 * mm, 12 * mm

    if _LOGO_PATH.exists():
        logo = Image(str(_LOGO_PATH), width=logo_w, height=logo_h)
    else:
        logo = Paragraph("<b>NOVA</b>", ParagraphStyle('nl', fontSize=16,
                         fontName='Helvetica-Bold', textColor=NOVA_PURPLE))

    title_para = Paragraph(f"<b>{doc_title}</b>",
                            ParagraphStyle('dt', fontSize=14, fontName='Helvetica-Bold',
                                           textColor=NOVA_NIGHT, alignment=TA_CENTER))

    num_line = f"<b>{number_label}:</b> {number_val}&nbsp;&nbsp;&nbsp;<b>Date:</b> {date_str}"
    if valid_until:
        num_line += f"&nbsp;&nbsp;&nbsp;<b>Valid Until:</b> {valid_until}"
    num_para = Paragraph(num_line, ParagraphStyle('nl2', fontSize=8, fontName='Helvetica',
                                                  alignment=TA_CENTER))

    hdr = Table(
        [[logo, [title_para, Spacer(1, 1*mm), num_para]]],
        colWidths=[logo_w + 4*mm, CW - logo_w - 4*mm],
    )
    hdr.setStyle(_ts([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',  (0, 0), (0, 0),   'LEFT'),
        ('ALIGN',  (1, 0), (1, 0),   'CENTER'),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 3*mm))
    return story


def _from_to_block(project: ProjectBOQ, email: str, phone: str, st: dict,
                   show_valid_until: str = "") -> Table:
    """Two-column From/To address block."""
    st8  = ParagraphStyle('a8',  fontSize=8,  fontName='Helvetica',  textColor=NOVA_NIGHT)
    st8b = ParagraphStyle('a8b', fontSize=8,  fontName='Helvetica-Bold', textColor=NOVA_NIGHT)
    st7  = ParagraphStyle('a7',  fontSize=7.5, fontName='Helvetica', textColor=NOVA_NIGHT)

    from_lines = [
        Paragraph("<b>From:</b>", st8b),
        Paragraph("<b>NOVA FORMWORKS PVT LTD</b>", st8b),
        Paragraph(_NOVA_ADDR, st7),
        Paragraph(f"Email: {email}", st7),
        Paragraph(f"Phone: {phone}", st7),
    ]

    to_name = project.client_name or "—"
    to_addr = project.client_address or "—"
    to_email = getattr(project, 'client_email', None) or "-"
    to_phone = getattr(project, 'client_phone', None) or "-"

    to_lines = [
        Paragraph("<b>To:</b>", st8b),
        Paragraph(f"<b>{to_name}</b>", st8b),
        Paragraph(to_addr, st7),
        Paragraph(f"Email: {to_email}", st7),
        Paragraph(f"Phone: {to_phone}", st7),
    ]

    t = Table([[from_lines, to_lines]], colWidths=[CW / 2, CW / 2])
    t.setStyle(_ts([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
    ]))
    return t


# ══════════════════════════════════════════════════════════════════════════════
# BOQ PDF
# ══════════════════════════════════════════════════════════════════════════════

def _make_diagram_image(boq: ElementBOQ, width_mm: float = 52, height_mm: float = 60,
                        dxf_doc=None):
    """Generate a diagram Image flowable for the given BOQ element. Returns None on error."""
    try:
        from src.output.diagram_generator import make_element_diagram
        png_bytes = make_element_diagram(boq, dxf_doc=dxf_doc, dpi=100)
        buf = io.BytesIO(png_bytes)
        return Image(buf, width=width_mm * mm, height=height_mm * mm)
    except Exception:
        return None


def _boq_element_table(group: dict, num_sets: int = 1, dxf_doc=None) -> list:
    """
    Build the per-element-group BOQ table matching the new template exactly.
    Columns: PRODUCT | Qty | UOM | No of Set | Total Qty | Unit Area (SqM) | Total Area (SqM)
    Right side: floor-plan diagram of the element.
    """
    boq       = group['boq']
    el        = boq.element
    height_mm = group['height_mm']
    no_sets   = max(1, el.quantity) * max(1, num_sets)

    req_type = el.element_type.value.lower()
    dim_str  = f"{int(el.length_mm)}X{int(el.width_mm)}"
    h_str    = f"{int(height_mm)}MM"

    # Client Requirement header row — label prominent, qty from drawing
    req_text = (f"{el.label}  |  {req_type}  |  Dimension: {dim_str}  |  "
                f"Height: {h_str}  |  No. in Drawing: {el.quantity}")

    # BOQ table takes left portion; diagram column takes right portion
    DIAG_W   = 52 * mm   # diagram column width
    TABLE_W  = CW - DIAG_W
    cw = [TABLE_W * f for f in [0.36, 0.08, 0.08, 0.11, 0.11, 0.13, 0.13]]

    header_row = [req_text, '', '', '', '', '', '']
    col_hdr    = ['PRODUCT', 'Qty', 'UOM', 'No of Set', 'Total Qty',
                  'Unit Area\n(SqM)', 'Total Area\n(SqM)']

    data = [header_row, col_hdr]
    total_area = 0.0
    first_panel_row = True
    filler_row_indices = []   # track rows that are fill plates (for grey styling)

    for panel in boq.panels:
        is_filler = getattr(panel, 'is_filler', False)
        if is_filler:
            plabel    = f"Fill Plate {int(panel.width_mm)}mm (spacer)"
            unit_area = 0.0
            row_area  = 0.0
            qty       = panel.quantity
            total_qty = qty * no_sets
            row = [plabel, f"{qty:.2f}", "nos", "", f"{total_qty:.2f}", "—", "—"]
            filler_row_indices.append(len(data))
        else:
            plabel     = _fmt_panel(panel.size_label)
            qty        = panel.quantity
            unit_area  = round((panel.width_mm * panel.height_mm) / 1_000_000, 2)
            total_qty  = qty * no_sets
            row_area   = round(unit_area * total_qty, 2)
            total_area += row_area
            row = [
                plabel,
                f"{qty:.2f}",
                "nos",
                str(no_sets) if first_panel_row else "",
                f"{total_qty:.2f}",
                f"{unit_area:.2f}",
                f"{row_area:.2f}",
            ]
        data.append(row)
        if not is_filler:
            first_panel_row = False

    # Total Area row
    data.append(['', '', '', '', '', 'Total Area (in SqM)', f"{total_area:.2f}"])

    t = Table(data, colWidths=cw, repeatRows=2)
    n = len(data)
    cmds = [
        # Requirement header row
        ('SPAN',        (0, 0), (-1, 0)),
        ('BACKGROUND',  (0, 0), (-1, 0), NOVA_SMOKE),
        ('FONTNAME',    (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',    (0, 0), (-1, 0), 8),
        ('ALIGN',       (0, 0), (-1, 0), 'LEFT'),
        ('TOPPADDING',  (0, 0), (-1, 0), 3),
        ('BOTTOMPADDING',(0, 0), (-1, 0), 3),
        # Column header row
        ('BACKGROUND',  (0, 1), (-1, 1), NOVA_PURPLE),
        ('TEXTCOLOR',   (0, 1), (-1, 1), NOVA_WHITE),
        ('FONTNAME',    (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE',    (0, 1), (-1, 1), 7),
        ('ALIGN',       (0, 1), (-1, 1), 'CENTER'),
        ('VALIGN',      (0, 1), (-1, 1), 'MIDDLE'),
        ('TOPPADDING',  (0, 1), (-1, 1), 3),
        ('BOTTOMPADDING',(0, 1), (-1, 1), 3),
        # Data rows
        ('FONTNAME',    (0, 2), (-1, n-2), 'Helvetica'),
        ('FONTSIZE',    (0, 2), (-1, n-2), 7.5),
        ('ALIGN',       (1, 2), (-1, n-2), 'CENTER'),
        ('ALIGN',       (0, 2), (0, n-2),  'LEFT'),
        ('TOPPADDING',  (0, 2), (-1, n-2), 2),
        ('BOTTOMPADDING',(0, 2), (-1, n-2), 2),
        # Total row
        ('SPAN',        (0, n-1), (4, n-1)),
        ('FONTNAME',    (0, n-1), (-1, n-1), 'Helvetica-Bold'),
        ('FONTSIZE',    (0, n-1), (-1, n-1), 7.5),
        ('ALIGN',       (5, n-1), (5, n-1),  'RIGHT'),
        ('ALIGN',       (6, n-1), (6, n-1),  'CENTER'),
        ('TOPPADDING',  (0, n-1), (-1, n-1), 2),
        ('BOTTOMPADDING',(0, n-1), (-1, n-1), 2),
        # Grid
        ('GRID',        (0, 1), (-1, n-1), 0.4, colors.HexColor('#cccccc')),
    ]
    # Alternating fill for data rows
    for i in range(2, n - 1):
        if i % 2 == 1:
            cmds.append(('BACKGROUND', (0, i), (-1, i), NOVA_SMOKE))

    # Fill plate rows: light grey text to visually distinguish from regular panels
    _FILLER_GREY = colors.HexColor('#999999')
    for fi in filler_row_indices:
        cmds.append(('TEXTCOLOR',  (0, fi), (-1, fi), _FILLER_GREY))
        cmds.append(('FONTNAME',   (0, fi), (-1, fi), 'Helvetica-Oblique'))

    t.setStyle(_ts(cmds))

    # ── Diagram image ─────────────────────────────────────────────────────────
    diag_h_mm = 58
    diag_img  = _make_diagram_image(boq, width_mm=DIAG_W / mm, height_mm=diag_h_mm,
                                    dxf_doc=dxf_doc)

    if diag_img is not None:
        diag_header = Paragraph(
            "Floor Plan",
            ParagraphStyle('dh', fontSize=6.5, fontName='Helvetica-Bold',
                           textColor=NOVA_NIGHT, alignment=TA_CENTER),
        )
        wrapper = Table(
            [[t, [diag_header, Spacer(1, 1*mm), diag_img]]],
            colWidths=[TABLE_W, DIAG_W],
        )
        wrapper.setStyle(_ts([
            ('VALIGN',  (0, 0), (-1, -1), 'TOP'),
            ('ALIGN',   (1, 0), (1,  0),  'CENTER'),
            ('TOPPADDING',    (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING',   (0, 0), (-1, -1), 0),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
            ('BOX',     (1, 0), (1, 0), 0.5, colors.HexColor('#cccccc')),
        ]))
        items = [wrapper]
    else:
        items = [t]

    for w in boq.warnings:
        items.append(Paragraph(f"  ⚠ {w}", _styles()['warn']))

    # ── Column accessories mini-table ─────────────────────────────────────────
    if el.is_column:
        from src.engine.column_accessories import compute_column_accessories
        acc = compute_column_accessories(el.length_mm, el.width_mm, height_mm)
        items.append(_col_accessories_table(acc, no_sets))

    items.append(Spacer(1, 3*mm))
    return items


def _col_accessories_table(acc, no_sets: int) -> Table:
    """
    Compact accessories table appended below each column element's panel table.
    Shows waller rows, per-element totals, and total-for-all-sets quantities.
    """
    _ACC_PURPLE = colors.HexColor('#5a1a3e')   # slightly darker for sub-section
    _ACC_BG     = colors.HexColor('#fdf5fa')

    rows_str = f"Waller rows: {acc.num_rows}  |  heights: {acc.positions_str}  |  " \
               f"per row: {acc.rows[0].wallers if acc.rows else 0} wallers + {acc.rows[0].tierods if acc.rows else 0} tierods"

    hdr_note = [
        Paragraph(f"COLUMN ACCESSORIES  — {rows_str}",
                  ParagraphStyle('ah', fontSize=7, fontName='Helvetica-BoldOblique',
                                 textColor=colors.white)),
        '', '', '', ''
    ]
    col_hdr = ['PRODUCT', 'Qty / element', 'UOM', f'No. of elements\n(× {no_sets})', 'Total Qty']

    rows = [
        hdr_note, col_hdr,
        ['Waller',      acc.total_wallers,       'nos', no_sets, acc.total_wallers * no_sets],
        ['Tie Rod',     acc.total_tierods,        'nos', '',      acc.total_tierods * no_sets],
        ['Anchor Nut',  acc.total_anchor_nuts,    'nos', '',      acc.total_anchor_nuts * no_sets],
    ]

    cw = [CW * 0.36, CW * 0.16, CW * 0.12, CW * 0.18, CW * 0.18]
    t = Table(rows, colWidths=cw)
    n = len(rows)
    t.setStyle(_ts([
        # Header note spanning full width
        ('SPAN',         (0, 0), (-1, 0)),
        ('BACKGROUND',   (0, 0), (-1, 0), _ACC_PURPLE),
        ('TOPPADDING',   (0, 0), (-1, 0), 3),
        ('BOTTOMPADDING',(0, 0), (-1, 0), 3),
        ('LEFTPADDING',  (0, 0), (-1, 0), 4),
        # Column header row
        ('BACKGROUND',   (0, 1), (-1, 1), NOVA_NAVY),
        ('TEXTCOLOR',    (0, 1), (-1, 1), NOVA_WHITE),
        ('FONTNAME',     (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 1), (-1, 1), 7),
        ('ALIGN',        (0, 1), (-1, 1), 'CENTER'),
        ('VALIGN',       (0, 1), (-1, 1), 'MIDDLE'),
        ('TOPPADDING',   (0, 1), (-1, 1), 2),
        ('BOTTOMPADDING',(0, 1), (-1, 1), 2),
        # Data rows
        ('BACKGROUND',   (0, 2), (-1, n-1), _ACC_BG),
        ('FONTNAME',     (0, 2), (-1, n-1), 'Helvetica'),
        ('FONTSIZE',     (0, 2), (-1, n-1), 7.5),
        ('ALIGN',        (1, 2), (-1, n-1), 'CENTER'),
        ('ALIGN',        (0, 2), (0,  n-1), 'LEFT'),
        ('TOPPADDING',   (0, 2), (-1, n-1), 2),
        ('BOTTOMPADDING',(0, 2), (-1, n-1), 2),
        # "No. of elements" only on first data row (Waller row)
        ('SPAN',         (3, 2), (3, n-1)),
        ('VALIGN',       (3, 2), (3, n-1), 'MIDDLE'),
        # Grid
        ('GRID',         (0, 1), (-1, n-1), 0.4, colors.HexColor('#cccccc')),
    ]))
    return t


def _boq_accessories_section(acc_agg: dict, st: dict) -> list:
    """ACCESSORIES table matching the new template format."""
    if not acc_agg:
        return []

    story = [
        Spacer(1, 2*mm),
        Paragraph("ACCESSORIES:", st['section']),
    ]

    cw = [CW * 0.65, CW * 0.18, CW * 0.17]
    rows = [['PRODUCT', 'Qty', 'UOM']]
    for size_label, d in acc_agg.items():
        display_name, uom = _fmt_acc(size_label)
        rows.append([display_name, f"{d['quantity']:.2f}", uom])

    t = Table(rows, colWidths=cw)
    t.setStyle(_ts([
        ('BACKGROUND',   (0, 0), (-1, 0), NOVA_PURPLE),
        ('TEXTCOLOR',    (0, 0), (-1, 0), NOVA_WHITE),
        ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, -1), 7.5),
        ('FONTNAME',     (0, 1), (-1, -1), 'Helvetica'),
        ('ALIGN',        (1, 0), (-1, -1), 'CENTER'),
        ('ALIGN',        (0, 0), (0, -1),  'LEFT'),
        ('GRID',         (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
        ('TOPPADDING',   (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 2),
    ]))
    story.append(t)
    story.append(Spacer(1, 3*mm))
    return story


def _boq_summary_section(element_boqs: list, st: dict, num_sets: int = 1) -> list:
    """SUMMARY table — aggregated across all elements."""
    totals: dict[str, dict] = defaultdict(lambda: {'qty': 0, 'w': 0, 'h': 0})
    for boq in element_boqs:
        n = max(1, boq.element.quantity) * max(1, num_sets)
        for p in boq.panels:
            if getattr(p, 'is_filler', False):
                continue   # fill plates excluded from project-level summary
            k = p.size_label
            totals[k]['qty'] += p.quantity * n
            totals[k]['w']    = p.width_mm
            totals[k]['h']    = p.height_mm

    def _sort(kv):
        k = kv[0]
        return (0 if k.startswith('OC') or k.startswith('IC') else 1,
                -totals[k]['w'])

    cw = [CW * 0.35, CW * 0.16, CW * 0.10, CW * 0.20, CW * 0.19]
    rows = [['PRODUCT', 'Total Quantity', 'UOM', 'Unit Area (SqM)', 'Total Area (SqM)']]
    grand_area = 0.0
    for k, d in sorted(totals.items(), key=_sort):
        unit_a = round(d['w'] * d['h'] / 1_000_000, 2)
        tot_a  = round(unit_a * d['qty'], 2)
        grand_area += tot_a
        rows.append([_fmt_panel(k), f"{d['qty']:.2f}", "nos",
                     f"{unit_a:.2f}", f"{tot_a:.2f}"])

    rows.append(['', '', '', 'Total Area', f"{grand_area:.2f}"])
    n = len(rows)

    t = Table(rows, colWidths=cw)
    cmds = [
        ('BACKGROUND',   (0, 0), (-1, 0), NOVA_PURPLE),
        ('TEXTCOLOR',    (0, 0), (-1, 0), NOVA_WHITE),
        ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, -1), 7.5),
        ('FONTNAME',     (0, 1), (-1, -1), 'Helvetica'),
        ('ALIGN',        (1, 0), (-1, -1), 'CENTER'),
        ('ALIGN',        (0, 0), (0, -1),  'LEFT'),
        ('GRID',         (0, 0), (-1, n-2), 0.4, colors.HexColor('#cccccc')),
        ('FONTNAME',     (0, n-1), (-1, n-1), 'Helvetica-Bold'),
        ('ALIGN',        (3, n-1), (3, n-1),  'RIGHT'),
        ('TOPPADDING',   (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 2),
    ]
    for i in range(1, n - 1):
        if i % 2 == 0:
            cmds.append(('BACKGROUND', (0, i), (-1, i), NOVA_SMOKE))
    t.setStyle(_ts(cmds))

    story = [
        Paragraph("SUMMARY:", st['section']),
        t,
    ]
    return story


def generate_boq_pdf(project: ProjectBOQ, output_path: str,
                     acc_agg: dict = None, boq_number: str = None) -> str:
    """
    Generate FORMWORK BOQ PDF matching the updated Nova template.
    Sections: grouped element tables → ACCESSORIES → SUMMARY
    """
    boq_num  = boq_number or f"OP-ID-{abs(hash(project.project_name)) % 10000:04d}"
    date_str = project.date or date.today().strftime("%d/%m/%Y")
    st = _styles()

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        rightMargin=MARGIN, leftMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )
    story = []

    # Header
    story += _logo_title_block("FORMWORK BOQ", "BOQ Number", boq_num, date_str)
    story.append(_from_to_block(project, _NOVA_BOQ_EMAIL, _NOVA_BOQ_PHONE, st))
    story.append(Spacer(1, 4*mm))

    # BOQ DETAILS
    story.append(Paragraph("BOQ DETAILS:", st['section']))
    story.append(HRFlowable(width="100%", thickness=0.5, color=NOVA_NAVY))
    story.append(Spacer(1, 2*mm))

    # Load DXF doc once (for diagram region extraction), if source path is set
    _dxf_doc = None
    _dxf_path = getattr(project, 'source_dxf_path', '') or ''
    if _dxf_path:
        try:
            import ezdxf as _ezdxf
            _dxf_doc = _ezdxf.readfile(_dxf_path)
        except Exception:
            pass

    groups = _group_boqs(project.element_boqs)
    n_sets = max(1, getattr(project, 'num_sets', 1))
    for group in groups:
        block = _boq_element_table(group, num_sets=n_sets, dxf_doc=_dxf_doc)
        story.append(KeepTogether(block[:3]))   # try to keep table together
        story += block[3:]

    # Accessories
    if acc_agg:
        story += _boq_accessories_section(acc_agg, st)

    # Summary
    story.append(HRFlowable(width="100%", thickness=0.5, color=NOVA_NAVY))
    story.append(Spacer(1, 2*mm))
    story += _boq_summary_section(project.element_boqs, st, num_sets=n_sets)

    doc.build(story)
    return output_path


# ══════════════════════════════════════════════════════════════════════════════
# QUOTATION PDF
# ══════════════════════════════════════════════════════════════════════════════

def _qtn_details_table(element_boqs: list, price_per_sqm: float) -> Table:
    """QUOTATION DETAILS table — one row per element, total area + pricing."""
    cw = [CW * 0.35, CW * 0.22, CW * 0.215, CW * 0.215]
    rows = [['CLIENT REQUIREMENT', 'Total Area (in SqM)', 'Unit Price', 'Total Price']]

    for boq in element_boqs:
        el = boq.element
        n  = max(1, el.quantity)
        area = round(boq.total_panel_area_sqm * n, 2)
        price = round(area * price_per_sqm, 2) if price_per_sqm else 0.0
        rows.append([
            f"{el.label}  ({el.element_type.value.lower()}  {int(el.length_mm)}×{int(el.width_mm)}mm  ×{el.quantity})",
            f"{area:.2f}",
            f"{price_per_sqm:.2f}" if price_per_sqm else "0.00",
            f"{price:.2f}",
        ])

    t = Table(rows, colWidths=cw)
    n = len(rows)
    t.setStyle(_ts([
        ('BACKGROUND',   (0, 0), (-1, 0), NOVA_PURPLE),
        ('TEXTCOLOR',    (0, 0), (-1, 0), NOVA_WHITE),
        ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, -1), 7.5),
        ('FONTNAME',     (0, 1), (-1, -1), 'Helvetica'),
        ('ALIGN',        (1, 0), (-1, -1), 'CENTER'),
        ('ALIGN',        (0, 0), (0, -1),  'LEFT'),
        ('GRID',         (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
        ('TOPPADDING',   (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 3),
    ]))
    for i in range(1, n):
        if i % 2 == 0:
            t.setStyle(_ts([('BACKGROUND', (0, i), (-1, i), NOVA_SMOKE)]))
    return t


def _qtn_accessories_table(acc_agg: dict, acc_price: float = 0.0) -> list:
    """Accessories Quotation section with pricing (UOM = mtr for wallers/rods, nos for rest)."""
    if not acc_agg:
        return []

    cw = [CW * 0.42, CW * 0.16, CW * 0.12, CW * 0.15, CW * 0.15]
    rows = [['Product', 'Quantity', 'UOM', 'Unit Price', 'Total Price']]

    for size_label, d in acc_agg.items():
        display_name, _ = _fmt_acc(size_label)
        # For quotation: wallers + tierods in mtr (total length), rest in nos
        sl = size_label.upper()
        if 'WALLER' in sl or 'TIE ROD' in sl or 'TIEROD' in sl:
            qty = d['total_length_m'] or d['quantity']
            uom = "mtr"
        else:
            qty = d['quantity']
            uom = "nos"

        rows.append([display_name, f"{qty:.2f}", uom, "0.00", "0.00"])

    t = Table(rows, colWidths=cw)
    t.setStyle(_ts([
        ('BACKGROUND',   (0, 0), (-1, 0), NOVA_PURPLE),
        ('TEXTCOLOR',    (0, 0), (-1, 0), NOVA_WHITE),
        ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, -1), 7.5),
        ('FONTNAME',     (0, 1), (-1, -1), 'Helvetica'),
        ('ALIGN',        (1, 0), (-1, -1), 'CENTER'),
        ('ALIGN',        (0, 0), (0, -1),  'LEFT'),
        ('GRID',         (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
        ('TOPPADDING',   (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 2),
    ]))
    return [
        Paragraph("2. Accessories Quotation",
                  ParagraphStyle('ah', fontSize=8, fontName='Helvetica-Bold',
                                 textColor=NOVA_NIGHT, spaceBefore=4)),
        t,
    ]


def _qtn_financials_table(subtotal: float, freight: float, gst_rate: float) -> Table:
    """Financial summary: Subtotal → Freight → Before Tax → GST → Grand Total."""
    gst    = round(subtotal * gst_rate, 2)
    before = round(subtotal + freight, 2)
    grand  = round(before + gst, 2)

    rows = [
        ['', 'Subtotal',                    f"{subtotal:.2f}"],
        ['', 'Freight',                     f"{freight:.2f}"],
        ['', 'Total Amount (Before Tax)',   f"{before:.2f}"],
        ['', f'GST ({gst_rate*100:.2f}%)',  f"{gst:.2f}"],
        ['', 'Grand Total',                 f"{grand:.2f}"],
    ]
    cw = [CW * 0.55, CW * 0.25, CW * 0.20]
    t = Table(rows, colWidths=cw)
    t.setStyle(_ts([
        ('FONTNAME',     (0, 0), (-1, -2), 'Helvetica'),
        ('FONTNAME',     (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, -1), 8),
        ('BACKGROUND',   (0, -1), (-1, -1), NOVA_NAVY),
        ('TEXTCOLOR',    (0, -1), (-1, -1), NOVA_WHITE),
        ('ALIGN',        (1, 0), (1, -1),   'RIGHT'),
        ('ALIGN',        (2, 0), (2, -1),   'RIGHT'),
        ('LINEABOVE',    (0, -1), (-1, -1), 1.0, NOVA_PURPLE),
        ('TOPPADDING',   (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 3),
    ]))
    return t


def _qtn_tc_block(st: dict) -> list:
    """Terms & Conditions bullet list."""
    story = [
        Spacer(1, 4*mm),
        Paragraph("<b>TERMS AND CONDITIONS:</b>", st['section']),
        HRFlowable(width="100%", thickness=0.5, color=NOVA_NAVY),
        Spacer(1, 2*mm),
    ]
    for pt in _TC_POINTS:
        story.append(Paragraph(f"• {pt}", st['tc']))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("<b>Prepared By:</b>", st['prepared']))
    story.append(Paragraph("Hiren Jadav", st['normal']))
    return story


def generate_quotation_pdf(project: ProjectBOQ, output_path: str,
                           acc_agg: dict = None, qtn_number: str = None,
                           price_per_sqm: float = 0.0,
                           freight: float = 0.0,
                           gst_rate: float = 0.18,
                           valid_days: int = 7) -> str:
    """
    Generate FORMWORK QUOTATION PDF matching the updated Nova template.
    Sections: per-element areas → Accessories → Financials → T&C
    """
    qtn_num  = qtn_number or f"QTN-{abs(hash(project.project_name)) % 100000:05d}"
    today    = date.today()
    date_str = project.date or today.strftime("%d/%m/%Y")
    valid_str = (today + timedelta(days=valid_days)).strftime("%d/%m/%Y")
    st = _styles()

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        rightMargin=MARGIN, leftMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )
    story = []

    story += _logo_title_block("FORMWORK QUOTATION", "Quotation Number",
                               qtn_num, date_str, valid_str)
    story.append(_from_to_block(project, _NOVA_QTN_EMAIL, _NOVA_QTN_PHONE, st))
    story.append(Spacer(1, 4*mm))

    story.append(Paragraph("QUOTATION DETAILS:", st['section']))
    story.append(HRFlowable(width="100%", thickness=0.5, color=NOVA_NAVY))
    story.append(Spacer(1, 2*mm))
    story.append(_qtn_details_table(project.element_boqs, price_per_sqm))
    story.append(Spacer(1, 3*mm))

    if acc_agg:
        story += _qtn_accessories_table(acc_agg)
        story.append(Spacer(1, 3*mm))

    # Compute subtotal from panel areas × price
    from src.output.boq_generator import aggregate_project_boq
    agg = aggregate_project_boq(project)
    subtotal = round(agg['total_area_sqm'] * price_per_sqm, 2)
    story.append(_qtn_financials_table(subtotal, freight or project.freight_amount, gst_rate))

    story += _qtn_tc_block(st)

    doc.build(story)
    return output_path


# ── Backward-compatible wrapper ───────────────────────────────────────────────

def generate_pdf(project: ProjectBOQ, panel_height_mm: float, output_path: str,
                 acc_agg: dict = None) -> str:
    """Legacy wrapper — generates BOQ PDF (matches old signature)."""
    return generate_boq_pdf(project, output_path, acc_agg=acc_agg)
