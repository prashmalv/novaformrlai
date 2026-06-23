"""
NovoForm — Formwork DXF Drawing Generator
==========================================
Generates an AutoCAD R2010-compatible DXF showing:
 - Plan cross-section view per column (panels on all 4 faces, OC corners)
 - Elevation view per wall (panel grid, waller lines, tierod circles)
 - Embedded BOQ table
 - Title block with project info and Nova branding

Opens directly in AutoCAD, FreeCAD, LibreCAD, or any DXF viewer.
All dimensions in mm (1 DXF unit = 1mm). Set viewport to 1:20 for A2 print.
"""
import math
from datetime import date
from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

from src.models.element import StructuralElement, ElementBOQ, ElementType, ProjectBOQ
from src.engine.panel_optimizer import find_panel_combination, OC_WIDTH
from src.engine.accessories_calc import WALLER_V_SPACING_MM, TIEROD_H_SPACING_MM
from src.output.boq_generator import aggregate_project_boq

# ── ACI Color constants ────────────────────────────────────────────────────────
_C_RED    = 1
_C_YELLOW = 2
_C_GREEN  = 3
_C_CYAN   = 4
_C_BLUE   = 5
_C_WHITE  = 7
_C_GREY   = 8
_C_LGREY  = 9
_C_ORANGE = 30

# ── Layer names ────────────────────────────────────────────────────────────────
_L_STRUCT   = 'NOVA_STRUCTURE'
_L_PANELS   = 'NOVA_PANELS'
_L_OC       = 'NOVA_OC_CORNER'
_L_TEXT     = 'NOVA_TEXT'
_L_DIM      = 'NOVA_DIMS'
_L_WALLER   = 'NOVA_WALLER'
_L_TIEROD   = 'NOVA_TIEROD'
_L_BOQ      = 'NOVA_BOQ'
_L_TITLE    = 'NOVA_TITLE'
_L_HATCH    = 'NOVA_HATCH'
_L_DIVIDER  = 'NOVA_DIVIDER'
_L_BORDER   = 'NOVA_BORDER'

# Cycling palette for panel colors (ACI)
_PANEL_PALETTE = [_C_CYAN, _C_GREEN, 41, 170, 80, 134, 52, 30]
_PCMAP: dict = {}


def _panel_aci(width_mm: int) -> int:
    if width_mm not in _PCMAP:
        _PCMAP[width_mm] = _PANEL_PALETTE[len(_PCMAP) % len(_PANEL_PALETTE)]
    return _PCMAP[width_mm]


# ── DXF Document setup ─────────────────────────────────────────────────────────

def _setup_doc() -> ezdxf.document.Drawing:
    doc = ezdxf.new('R2010', units=4)   # 4 = mm

    layer_defs = [
        (_L_STRUCT,  _C_BLUE,   35),
        (_L_PANELS,  _C_CYAN,   18),
        (_L_OC,      _C_YELLOW, 25),
        (_L_TEXT,    _C_WHITE,  18),
        (_L_DIM,     _C_GREEN,  13),
        (_L_WALLER,  _C_RED,    50),
        (_L_TIEROD,  _C_BLUE,   18),
        (_L_BOQ,     _C_WHITE,  18),
        (_L_TITLE,   _C_WHITE,  35),
        (_L_HATCH,   _C_LGREY,  13),
        (_L_DIVIDER, _C_GREY,   13),
        (_L_BORDER,  _C_WHITE,  50),
    ]
    for name, color, lw in layer_defs:
        layer = doc.layers.new(name, dxfattribs={'color': color})
        layer.dxf.lineweight = lw

    return doc


# ── Low-level drawing helpers ──────────────────────────────────────────────────

def _rect(msp, x0, y0, x1, y1, layer, lw=None):
    """Draw a closed rectangle outline."""
    attribs = {'layer': layer, 'closed': True}
    if lw is not None:
        attribs['lineweight'] = lw
    return msp.add_lwpolyline(
        [(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
        dxfattribs=attribs,
    )


def _hatch_rect(msp, x0, y0, x1, y1, color, pattern='SOLID'):
    """Add a filled hatch for a rectangle."""
    h = msp.add_hatch(color=color, dxfattribs={'layer': _L_HATCH})
    h.paths.add_polyline_path(
        [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], is_closed=True
    )
    if pattern == 'SOLID':
        h.set_pattern_fill('SOLID')
    else:
        try:
            h.set_pattern_fill(pattern, scale=300, angle=45)
        except Exception:
            h.set_pattern_fill('SOLID')
    return h


def _line(msp, x0, y0, x1, y1, layer):
    return msp.add_line((x0, y0), (x1, y1), dxfattribs={'layer': layer})


def _txt(msp, text, x, y, height=100, layer=_L_TEXT, center=False, rotation=0):
    """Add a text entity."""
    t = msp.add_text(str(text), dxfattribs={
        'height': height, 'layer': layer, 'rotation': rotation,
    })
    align = TextEntityAlignment.CENTER if center else TextEntityAlignment.LEFT
    t.set_placement((x, y), align=align)
    return t


def _dim_horiz(msp, x0, x1, y_dim, label, text_h=80):
    """Draw a horizontal dimension line with label."""
    arrow = 100
    _line(msp, x0, y_dim, x1, y_dim, _L_DIM)
    # tick marks
    _line(msp, x0, y_dim - 80, x0, y_dim + 80, _L_DIM)
    _line(msp, x1, y_dim - 80, x1, y_dim + 80, _L_DIM)
    _txt(msp, label, (x0 + x1) / 2, y_dim + 100, height=text_h,
         layer=_L_DIM, center=True)


def _dim_vert(msp, x_dim, y0, y1, label, text_h=80):
    """Draw a vertical dimension line with label."""
    _line(msp, x_dim, y0, x_dim, y1, _L_DIM)
    _line(msp, x_dim - 80, y0, x_dim + 80, y0, _L_DIM)
    _line(msp, x_dim - 80, y1, x_dim + 80, y1, _L_DIM)
    _txt(msp, label, x_dim - 100, (y0 + y1) / 2, height=text_h,
         layer=_L_DIM, center=True, rotation=90)


# Panel visual thickness in plan view (mm) — for display only, not real thickness
_PT = 80


# ── Column plan view ───────────────────────────────────────────────────────────

def _draw_column_plan(msp, element: StructuralElement, panel_height_mm: float,
                      ox: float, oy: float) -> tuple:
    """
    Draw column formwork as plan cross-section view.
    Returns (used_width_mm, used_height_mm) of the total zone.
    """
    L = element.length_mm
    W = element.width_mm
    oc = OC_WIDTH     # 80mm
    T = _PT           # panel visual thickness in plan = 80mm
    _PCMAP.clear()

    len_combo, len_sp = find_panel_combination(L)
    wid_combo, wid_sp = find_panel_combination(W)

    # ── Concrete body ─────────────────────────────────────────────────────────
    _hatch_rect(msp, ox, oy, ox + L, oy + W, color=_C_LGREY, pattern='ANSI31')
    _rect(msp, ox, oy, ox + L, oy + W, _L_STRUCT, lw=50)
    _txt(msp, f'{L:.0f}×{W:.0f}', ox + L / 2, oy + W / 2,
         height=min(80, W * 0.12), layer=_L_TEXT, center=True)

    # ── OC corners (4 squares outside concrete) ───────────────────────────────
    oc_data = [
        (ox - oc, oy - oc, ox,      oy),       # BL
        (ox + L,  oy - oc, ox + L + oc, oy),   # BR
        (ox + L,  oy + W,  ox + L + oc, oy + W + oc),  # TR
        (ox - oc, oy + W,  ox,      oy + W + oc),       # TL
    ]
    for x0, y0, x1, y1 in oc_data:
        _hatch_rect(msp, x0, y0, x1, y1, color=_C_YELLOW)
        _rect(msp, x0, y0, x1, y1, _L_OC, lw=25)
        _txt(msp, 'OC', (x0 + x1) / 2, (y0 + y1) / 2,
             height=40, layer=_L_OC, center=True)

    # ── Face 1 & 3 (South/North — panels along L) ─────────────────────────────
    x_cur = ox
    for pw in len_combo:
        col = _panel_aci(pw)
        # Face 1 (South): y from oy-T to oy
        _hatch_rect(msp, x_cur, oy - T, x_cur + pw, oy, color=col)
        _rect(msp, x_cur, oy - T, x_cur + pw, oy, _L_PANELS)
        _txt(msp, str(pw), x_cur + pw / 2, oy - T / 2,
             height=50, layer=_L_TEXT, center=True)
        # Face 3 (North): y from oy+W to oy+W+T
        _hatch_rect(msp, x_cur, oy + W, x_cur + pw, oy + W + T, color=col)
        _rect(msp, x_cur, oy + W, x_cur + pw, oy + W + T, _L_PANELS)
        _txt(msp, str(pw), x_cur + pw / 2, oy + W + T / 2,
             height=50, layer=_L_TEXT, center=True)
        x_cur += pw

    if len_sp > 0:
        _hatch_rect(msp, x_cur, oy - T, x_cur + len_sp, oy, color=_C_LGREY)
        _rect(msp, x_cur, oy - T, x_cur + len_sp, oy, _L_PANELS)
        _txt(msp, f'{len_sp:.0f}sp', x_cur + len_sp / 2, oy - T / 2,
             height=40, layer=_L_TEXT, center=True)
        _hatch_rect(msp, x_cur, oy + W, x_cur + len_sp, oy + W + T, color=_C_LGREY)
        _rect(msp, x_cur, oy + W, x_cur + len_sp, oy + W + T, _L_PANELS)
        _txt(msp, f'{len_sp:.0f}sp', x_cur + len_sp / 2, oy + W + T / 2,
             height=40, layer=_L_TEXT, center=True)

    # ── Face 2 & 4 (East/West — panels along W) ───────────────────────────────
    y_cur = oy
    for pw in wid_combo:
        col = _panel_aci(pw)
        # Face 2 (East): x from ox+L to ox+L+T
        _hatch_rect(msp, ox + L, y_cur, ox + L + T, y_cur + pw, color=col)
        _rect(msp, ox + L, y_cur, ox + L + T, y_cur + pw, _L_PANELS)
        _txt(msp, str(pw), ox + L + T / 2, y_cur + pw / 2,
             height=50, layer=_L_TEXT, center=True, rotation=90)
        # Face 4 (West): x from ox-T to ox
        _hatch_rect(msp, ox - T, y_cur, ox, y_cur + pw, color=col)
        _rect(msp, ox - T, y_cur, ox, y_cur + pw, _L_PANELS)
        _txt(msp, str(pw), ox - T / 2, y_cur + pw / 2,
             height=50, layer=_L_TEXT, center=True, rotation=90)
        y_cur += pw

    if wid_sp > 0:
        _hatch_rect(msp, ox + L, y_cur, ox + L + T, y_cur + wid_sp, color=_C_LGREY)
        _rect(msp, ox + L, y_cur, ox + L + T, y_cur + wid_sp, _L_PANELS)
        _txt(msp, f'{wid_sp:.0f}sp', ox + L + T / 2, y_cur + wid_sp / 2,
             height=40, layer=_L_TEXT, center=True, rotation=90)

    # ── Dimension lines ───────────────────────────────────────────────────────
    dim_off = oc + T + 300
    _dim_horiz(msp, ox, ox + L, oy - T - oc - 300, f'{L:.0f}mm')
    _dim_vert(msp, ox - T - oc - 300, oy, oy + W, f'{W:.0f}mm')

    # ── Element title ─────────────────────────────────────────────────────────
    title_y = oy + W + oc + T + 300
    _txt(msp, f'{element.label}  ({element.element_type.value.upper()})',
         ox + L / 2, title_y + 120, height=130, layer=_L_TEXT, center=True)
    _txt(msp,
         f'{L:.0f} x {W:.0f} mm  |  Panel H = {panel_height_mm:.0f} mm  |  Qty = {element.quantity}',
         ox + L / 2, title_y, height=80, layer=_L_TEXT, center=True)

    # ── Panel schedule below element ──────────────────────────────────────────
    sched_y = oy - T - oc - 700
    _txt(msp, 'PANEL SCHEDULE:', ox, sched_y, height=80,
         layer=_L_TEXT)
    sched_y -= 130
    _txt(msp, f'Faces 1&3 (L={L:.0f}mm):', ox, sched_y,
         height=70, layer=_L_TEXT)
    sched_y -= 110
    for pw in sorted(set(len_combo), reverse=True):
        cnt = len_combo.count(pw)
        _txt(msp, f'  {pw}x{panel_height_mm:.0f}mm  x {cnt} nos = {cnt*2} faces',
             ox, sched_y, height=65, layer=_L_TEXT)
        sched_y -= 100
    _txt(msp, f'  OC80x{panel_height_mm:.0f}mm  x 2 nos per face (corners)',
         ox, sched_y, height=65, layer=_L_OC)
    sched_y -= 110
    _txt(msp, f'Faces 2&4 (W={W:.0f}mm):', ox, sched_y,
         height=70, layer=_L_TEXT)
    sched_y -= 110
    for pw in sorted(set(wid_combo), reverse=True):
        cnt = wid_combo.count(pw)
        _txt(msp, f'  {pw}x{panel_height_mm:.0f}mm  x {cnt} nos = {cnt*2} faces',
             ox, sched_y, height=65, layer=_L_TEXT)
        sched_y -= 100

    # bounding box for layout
    total_w = L + 2 * (oc + T) + 800
    total_h = W + 2 * (oc + T) + 1200
    return total_w, total_h


# ── Wall elevation view ────────────────────────────────────────────────────────

def _draw_wall_elevation(msp, element: StructuralElement, panel_height_mm: float,
                         ox: float, oy: float) -> tuple:
    """
    Draw wall formwork as elevation (face) view.
    Shows panel grid, waller lines, and tierod positions.
    Returns (used_width_mm, used_height_mm).
    """
    L = element.length_mm
    H_cast = element.height_mm
    oc = OC_WIDTH
    ph = panel_height_mm
    rows = max(1, math.ceil(H_cast / ph))
    total_h_draw = rows * ph
    _PCMAP.clear()

    combo, spacer = find_panel_combination(L)

    total_w_draw = oc + sum(combo) + (spacer if spacer else 0) + oc

    # ── OC at left ────────────────────────────────────────────────────────────
    _hatch_rect(msp, ox, oy, ox + oc, oy + total_h_draw, color=_C_YELLOW)
    _rect(msp, ox, oy, ox + oc, oy + total_h_draw, _L_OC, lw=25)
    _txt(msp, 'OC', ox + oc / 2, oy + total_h_draw / 2,
         height=50, layer=_L_OC, center=True, rotation=90)

    # ── Flat panels ───────────────────────────────────────────────────────────
    x_cur = ox + oc
    for pw in combo:
        col = _panel_aci(pw)
        for row in range(rows):
            ry = oy + row * ph
            _hatch_rect(msp, x_cur, ry, x_cur + pw, ry + ph, color=col)
            _rect(msp, x_cur, ry, x_cur + pw, ry + ph, _L_PANELS)
            if row == 0:
                _txt(msp, str(pw), x_cur + pw / 2, oy + total_h_draw / 2,
                     height=60, layer=_L_TEXT, center=True)
        x_cur += pw

    if spacer > 0:
        for row in range(rows):
            ry = oy + row * ph
            _hatch_rect(msp, x_cur, ry, x_cur + spacer, ry + ph, color=_C_LGREY)
            _rect(msp, x_cur, ry, x_cur + spacer, ry + ph, _L_PANELS)
        _txt(msp, f'{spacer:.0f}sp', x_cur + spacer / 2, oy + total_h_draw / 2,
             height=50, layer=_L_TEXT, center=True)
        x_cur += spacer

    # ── OC at right ───────────────────────────────────────────────────────────
    _hatch_rect(msp, x_cur, oy, x_cur + oc, oy + total_h_draw, color=_C_YELLOW)
    _rect(msp, x_cur, oy, x_cur + oc, oy + total_h_draw, _L_OC, lw=25)
    _txt(msp, 'OC', x_cur + oc / 2, oy + total_h_draw / 2,
         height=50, layer=_L_OC, center=True, rotation=90)

    # ── Panel row dividers ────────────────────────────────────────────────────
    for row in range(1, rows):
        ry = oy + row * ph
        _line(msp, ox, ry, ox + total_w_draw, ry, _L_DIVIDER)

    # ── Waller lines ─────────────────────────────────────────────────────────
    w_count = math.ceil(H_cast / WALLER_V_SPACING_MM) + 1
    for i in range(w_count):
        wy = oy + i * (total_h_draw / max(w_count - 1, 1)) if w_count > 1 else oy + total_h_draw / 2
        _line(msp, ox, wy, ox + total_w_draw, wy, _L_WALLER)
        msp.add_line(
            (ox + total_w_draw, wy),
            (ox + total_w_draw + 200, wy),
            dxfattribs={'layer': _L_WALLER},
        )
        _txt(msp, f'W{i+1}', ox + total_w_draw + 220, wy,
             height=70, layer=_L_WALLER)

    # ── Tierod circles at waller × tierod-column intersections ───────────────
    tr_count = math.ceil(L / TIEROD_H_SPACING_MM)
    tr_xs = [ox + oc + (i + 0.5) * L / tr_count for i in range(tr_count)]
    w_ys = [oy + i * (total_h_draw / max(w_count - 1, 1))
            for i in range(w_count)] if w_count > 1 else [oy + total_h_draw / 2]
    for wy in w_ys:
        for tx in tr_xs:
            msp.add_circle((tx, wy), 40, dxfattribs={'layer': _L_TIEROD})

    # ── Outer border ─────────────────────────────────────────────────────────
    _rect(msp, ox, oy, ox + total_w_draw, oy + total_h_draw, _L_BORDER, lw=50)

    # ── Dimension lines ───────────────────────────────────────────────────────
    _dim_horiz(msp, ox + oc, ox + oc + L, oy - 300, f'{L:.0f}mm (wall length)')
    _dim_vert(msp, ox - 300, oy, oy + total_h_draw, f'{total_h_draw:.0f}mm')

    # ── Element title ─────────────────────────────────────────────────────────
    title_x = ox + total_w_draw / 2
    title_y = oy + total_h_draw + 200
    _txt(msp, f'{element.label}  (WALL)',
         title_x, title_y + 120, height=130, layer=_L_TEXT, center=True)
    _txt(msp,
         f'L={L:.0f}mm  |  t={element.width_mm:.0f}mm  |  H={H_cast:.0f}mm  |  '
         f'Panel H={ph:.0f}mm  |  Qty={element.quantity}  |  '
         f'{w_count} waller rows  |  {tr_count} tierod cols',
         title_x, title_y, height=70, layer=_L_TEXT, center=True)

    total_w_zone = total_w_draw + 600
    total_h_zone = total_h_draw + 600
    return total_w_zone, total_h_zone


# ── BOQ Table ─────────────────────────────────────────────────────────────────

def _draw_boq_table(msp, elements, boqs, project, panel_height_mm, ox, oy) -> tuple:
    """Draw a panel BOQ table. Returns (used_width, used_height)."""
    agg = aggregate_project_boq(project)
    col_w = [2200, 1200, 800, 800]   # column widths: item, size, qty, area
    total_w = sum(col_w)
    row_h = 160

    headers = ['PANEL SIZE', 'HEIGHT (mm)', 'QTY (nos)', 'AREA (m²)']

    # Title
    _txt(msp, 'BILL OF QUANTITIES — PANELS', ox, oy + 100,
         height=120, layer=_L_BOQ)
    _txt(msp, f'Panel Height: {panel_height_mm:.0f}mm  |  {len(elements)} element(s)',
         ox, oy, height=80, layer=_L_BOQ)

    cur_y = oy - row_h * 0.5
    # Header row
    _hatch_rect(msp, ox, cur_y - row_h, ox + total_w, cur_y, color=_C_BLUE)
    _rect(msp, ox, cur_y - row_h, ox + total_w, cur_y, _L_BOQ)
    x = ox
    for h, cw in zip(headers, col_w):
        _txt(msp, h, x + 50, cur_y - row_h * 0.65, height=80, layer=_L_TITLE)
        x += cw

    cur_y -= row_h

    # Data rows
    summary = agg.get('panels_by_size', {})
    row_toggle = False
    total_area = 0.0
    for size_key, data in sorted(summary.items()):
        row_toggle = not row_toggle
        bg = _C_LGREY if row_toggle else _C_WHITE
        _hatch_rect(msp, ox, cur_y - row_h, ox + total_w, cur_y, color=bg)
        _rect(msp, ox, cur_y - row_h, ox + total_w, cur_y, _L_BOQ)

        parts = size_key.split('*')
        size_label = f"{parts[0].strip()} × {int(float(parts[1].strip()))}mm" if len(parts) == 2 else size_key
        qty = data.get('quantity', 0)
        area = data.get('area_sqm', 0.0)
        total_area += area

        row_data = [size_label, parts[1].strip() if len(parts) == 2 else '', str(qty), f'{area:.3f}']
        x = ox
        for val, cw in zip(row_data, col_w):
            _txt(msp, val, x + 50, cur_y - row_h * 0.65, height=75, layer=_L_BOQ)
            x += cw
        cur_y -= row_h

    # Totals row
    _hatch_rect(msp, ox, cur_y - row_h, ox + total_w, cur_y, color=_C_BLUE)
    _rect(msp, ox, cur_y - row_h, ox + total_w, cur_y, _L_BOQ)
    _txt(msp, 'TOTAL', ox + 50, cur_y - row_h * 0.65, height=85, layer=_L_TITLE)
    _txt(msp, f'{total_area:.3f} m²',
         ox + sum(col_w[:3]) + 50, cur_y - row_h * 0.65, height=85, layer=_L_TITLE)
    cur_y -= row_h

    _rect(msp, ox, cur_y, ox + total_w, oy, _L_BOQ, lw=35)   # outer border

    used_h = oy - cur_y + row_h
    return total_w, used_h


# ── Title Block ────────────────────────────────────────────────────────────────

def _draw_title_block(msp, project: ProjectBOQ, panel_height_mm: float,
                      sheet_width: float, ox: float, oy: float):
    """Draw title block strip at bottom of sheet."""
    tb_h = 1500
    _hatch_rect(msp, ox, oy - tb_h, ox + sheet_width, oy, color=_C_LGREY)
    _rect(msp, ox, oy - tb_h, ox + sheet_width, oy, _L_TITLE, lw=50)

    # Vertical dividers
    div_xs = [ox + sheet_width * 0.40, ox + sheet_width * 0.70]
    for dx in div_xs:
        _line(msp, dx, oy - tb_h, dx, oy, _L_TITLE)

    # Left column — Project info
    lx = ox + 100
    ly = oy - 200
    _txt(msp, 'NOVA FORMWORKS PVT. LTD.', lx, ly, height=160, layer=_L_TITLE)
    ly -= 220
    _txt(msp, f'PROJECT: {project.project_name or "(untitled)"}',
         lx, ly, height=110, layer=_L_TITLE)
    ly -= 160
    _txt(msp, f'CLIENT:  {project.client_name or ""}',
         lx, ly, height=100, layer=_L_TITLE)
    ly -= 150
    _txt(msp, f'PANEL HT: {panel_height_mm:.0f}mm  |  SETS: {project.num_sets}',
         lx, ly, height=100, layer=_L_TITLE)

    # Middle column — Drawing info
    mx = div_xs[0] + 100
    my = oy - 200
    draw_date = date.today().strftime('%d-%b-%Y')
    _txt(msp, f'DATE: {draw_date}', mx, my, height=110, layer=_L_TITLE)
    my -= 160
    _txt(msp, f'DRAWING NO: NF-{draw_date.replace("-","")}-01',
         mx, my, height=100, layer=_L_TITLE)
    my -= 150
    _txt(msp, 'REV: 00', mx, my, height=100, layer=_L_TITLE)
    my -= 150
    _txt(msp, 'SCALE: 1:20 (recommended)', mx, my, height=90, layer=_L_TITLE)
    my -= 130
    _txt(msp, 'UNITS: mm', mx, my, height=90, layer=_L_TITLE)

    # Right column — Notes
    rx = div_xs[1] + 100
    ry = oy - 200
    notes = [
        'NOTES:',
        '1. All dimensions in mm.',
        '2. Panel layout is schematic.',
        '3. Verify all dimensions on site',
        '   before installation.',
        '4. Generated by NovoForm v1.2',
        '   (RLAI / rightleft.ai)',
    ]
    for note in notes:
        bold = note == 'NOTES:'
        _txt(msp, note, rx, ry, height=90 if not bold else 100, layer=_L_TITLE)
        ry -= 120

    # NOVA branding line top of block
    _txt(msp, 'FORMWORK LAYOUT DRAWING  —  NOVA FORMWORKS PVT. LTD.',
         ox + sheet_width / 2, oy - 80, height=130, layer=_L_TITLE, center=True)
    _txt(msp,
         'This drawing is auto-generated by NovoForm software. '
         'Verify panel sizes and accessory quantities before ordering.',
         ox + sheet_width / 2, oy + 50, height=80, layer=_L_DIM, center=True)


# ── Main public API ────────────────────────────────────────────────────────────

def generate_formwork_dxf(
    elements: list,
    boqs: list,
    project: ProjectBOQ,
    panel_height_mm: float,
    output_path: str,
) -> str:
    """
    Generate a complete formwork layout DXF drawing.

    Args:
        elements       : List of StructuralElement
        boqs           : Corresponding ElementBOQ list (same order)
        project        : ProjectBOQ (for title block)
        panel_height_mm: Panel height being used
        output_path    : .dxf file path to write

    Returns:
        output_path (str) on success.
    """
    _PCMAP.clear()

    doc = _setup_doc()
    msp = doc.modelspace()

    # Layout: elements arranged left-to-right starting at (0, 2000)
    # BOQ table to the right of elements
    # Title block at bottom

    ELEMENT_GAP = 1200   # mm gap between elements
    BASE_Y = 2000        # baseline Y for elements

    x_cursor = 0
    max_elem_h = 0

    for elem, boq in zip(elements, boqs):
        is_col = elem.element_type == ElementType.COLUMN
        if is_col:
            w, h = _draw_column_plan(msp, elem, panel_height_mm, x_cursor, BASE_Y)
        else:
            w, h = _draw_wall_elevation(msp, elem, panel_height_mm, x_cursor, BASE_Y)
        max_elem_h = max(max_elem_h, h)
        x_cursor += w + ELEMENT_GAP

    boq_x = x_cursor
    boq_y = BASE_Y + max_elem_h - 200

    # BOQ table
    try:
        boq_w, boq_h = _draw_boq_table(
            msp, elements, boqs, project, panel_height_mm,
            ox=boq_x, oy=boq_y,
        )
        x_cursor = max(x_cursor, boq_x + boq_w + 1000)
    except Exception:
        pass  # BOQ table failure is non-fatal

    sheet_width = x_cursor

    # Title block at y=0 to y=-1500
    _draw_title_block(msp, project, panel_height_mm, sheet_width, ox=0, oy=0)

    # Outer sheet border
    total_h = BASE_Y + max_elem_h + 600
    _rect(msp, -500, -1600, sheet_width + 500, total_h, _L_BORDER, lw=70)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(output_path)
    return output_path
