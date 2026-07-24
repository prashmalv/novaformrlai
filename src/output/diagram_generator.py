"""
Floor-plan diagram generator for BOQ reports.

Priority per element:
  0. Pre-defined shape image  — PNG from assets/images/ShearWall Images/{label}.png
     (highest fidelity: actual client drawings for every named shear wall)
  1. DXF region extraction    — rendered directly from source DXF (complex polygons)
  2. Generated polygon shape  — L / T / E / CUSTOM drawn from polygon_pts vertices
  3. Generated rectangle      — columns and simple straight walls

Each diagram shows the shape in the top portion and a compact panel-summary
table in the bottom portion.
"""
import io
import math
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import numpy as np

from src.models.element import ElementBOQ

# ── Pre-defined shape image catalog ──────────────────────────────────────────
# Drop a PNG named <label>.png (e.g. SW5.png) in this directory to override
# the generated diagram for that element label in all DXF files.
_SHAPE_IMAGES_DIR = (
    Path(__file__).parent.parent.parent / "assets" / "images" / "ShearWall Images"
)


# ── Design tokens ─────────────────────────────────────────────────────────────
_RED    = '#C0001A'
_FILL   = '#FFE8EC'
_OC_DOT = '#CC4444'
_IC_SQ  = '#1144BB'
_DIM    = '#C0001A'
_BORDER = '#888888'
_SUMFG  = '#222222'
_SUMBG  = '#F8F4F4'
_SUMBDR = '#CCAAAA'


# ══════════════════════════════════════════════════════════════════════════════
#  Shape detection
# ══════════════════════════════════════════════════════════════════════════════

def detect_shape_type(pts: list, corners: list) -> str:
    """
    Classify a polygon into one of five shape families based on vertex count
    and number of concave (IC100) corners.

    Returns one of: 'RECTANGLE', 'L_SHAPE', 'T_SHAPE', 'E_SHAPE', 'CUSTOM'
    """
    n   = len(pts)
    nic = corners.count('IC100')

    if n <= 4:
        return 'RECTANGLE'
    if n == 6 and nic == 1:         # L-shape: one concave notch cut from rectangle
        return 'L_SHAPE'
    if n == 8 and nic == 2:         # T / Z / C-shape: two notches (T-bar/stem)
        return 'T_SHAPE'
    if n >= 10:
        # Multi-fin shapes: 12-pt (2 fins), 16-pt (4 fins), etc.
        return 'E_SHAPE'
    return 'CUSTOM'


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _normalize(pts):
    """Translate+scale pts so the bounding box is (0,0)→(w_norm, h_norm)."""
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    mn_x, mn_y = min(xs), min(ys)
    raw_w = max(xs) - mn_x
    raw_h = max(ys) - mn_y
    scale = max(raw_w, raw_h, 1.0)
    nxs = [(x - mn_x) / scale for x in xs]
    nys = [(y - mn_y) / scale for y in ys]
    return nxs, nys, scale, raw_w, raw_h


def _figsize(w_norm: float, h_norm: float, max_side: float = 3.6):
    aspect = w_norm / max(h_norm, 0.01)
    if aspect >= 1:
        fw = max_side
        fh = max(1.4, max_side / aspect)
    else:
        fh = max_side
        fw = max(1.4, max_side * aspect)
    return min(fw, max_side), min(fh, max_side)


def _draw_polygon(ax, nxs, nys, corners):
    """Fill + outline the polygon; mark OC80 (dots) and IC100 (squares)."""
    ax.fill(nxs, nys, color=_FILL, zorder=1)
    cxs = nxs + [nxs[0]]
    cys = nys + [nys[0]]
    ax.plot(cxs, cys, color=_RED, linewidth=2.0, zorder=2)

    mk = min(max(nxs) - min(nxs), max(nys) - min(nys)) * 0.045
    mk = max(mk, 0.018)
    for i, (x, y) in enumerate(zip(nxs, nys)):
        ct = corners[i] if i < len(corners) else 'OC80'
        if ct == 'IC100':
            ax.add_patch(mpatches.Rectangle(
                (x - mk/2, y - mk/2), mk, mk,
                facecolor=_IC_SQ, edgecolor=_IC_SQ, linewidth=0, zorder=6))
        else:
            ax.plot(x, y, 'o', color=_OC_DOT, markersize=3.5, zorder=5)


def _dim_arrow(ax, p1, p2, text, pad=0.025, fs=5.5):
    """Double-headed dimension arrow with label at midpoint."""
    ax.annotate('', xy=p2, xytext=p1,
                arrowprops=dict(arrowstyle='<->', color=_DIM, lw=0.9))
    mx = (p1[0] + p2[0]) / 2
    my = (p1[1] + p2[1]) / 2
    # Determine text offset direction
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    if abs(dx) >= abs(dy):              # horizontal arrow → label above
        ax.text(mx, my + pad, text, ha='center', va='bottom',
                fontsize=fs, color=_DIM, fontweight='bold')
    else:                               # vertical arrow → label to the right
        ax.text(mx + pad, my, text, ha='left', va='center',
                fontsize=fs, color=_DIM, fontweight='bold', rotation=90,
                rotation_mode='anchor')


# ══════════════════════════════════════════════════════════════════════════════
#  Panel summary box
# ══════════════════════════════════════════════════════════════════════════════

def _draw_panel_summary(ax, boq: ElementBOQ):
    """
    Draw a panel-summary table in ax.
    Groups panels as: IC100 | OC80 | flat panels by width desc.
    Shows size label and quantity for every row in the BOQ.
    """
    ax.axis('off')

    # Background box
    ax.add_patch(mpatches.FancyBboxPatch(
        (0.01, 0.05), 0.98, 0.90,
        boxstyle='round,pad=0.02',
        facecolor=_SUMBG, edgecolor=_SUMBDR, linewidth=0.8,
        transform=ax.transAxes, zorder=1, clip_on=False))

    # Build rows
    rows = []
    for p in boq.panels:
        if p.is_inner_corner:
            tag = f"IC{int(p.width_mm)}"
        elif p.is_corner:
            tag = f"OC{int(p.width_mm)}"
        else:
            tag = f"{int(p.width_mm)}mm"
        rows.append((tag, str(p.quantity), 'nos'))

    if not rows:
        ax.text(0.5, 0.5, 'No panels', ha='center', va='center',
                fontsize=5.5, color=_BORDER, transform=ax.transAxes)
        return

    # Column headers
    cols     = ['Panel', 'Qty', 'UOM']
    col_x    = [0.06, 0.65, 0.83]
    hdr_y    = 0.88

    for cx, hdr in zip(col_x, cols):
        ax.text(cx, hdr_y, hdr, ha='left', va='top',
                fontsize=4.5, color='#555555', fontweight='bold',
                transform=ax.transAxes)

    # Separator line in axes-fraction coordinates
    ax.plot([0.02, 0.98], [0.82, 0.82], color=_SUMBDR,
            linewidth=0.5, transform=ax.transAxes)

    # Data rows — fit as many as space allows
    y = 0.80
    dy = 0.13
    max_rows = int(0.75 / dy)   # ~5 rows
    visible = rows[:max_rows]
    if len(rows) > max_rows:
        visible[-1] = ('…', f'+{len(rows)-max_rows+1}', '')

    for tag, qty, uom in visible:
        for cx, val in zip(col_x, [tag, qty, uom]):
            ax.text(cx, y, val, ha='left', va='top',
                    fontsize=4.5, color=_SUMFG,
                    transform=ax.transAxes)
        y -= dy


# ══════════════════════════════════════════════════════════════════════════════
#  Shape template renderers
# ══════════════════════════════════════════════════════════════════════════════

def _render_rectangle(ax, L: float, W: float):
    """
    Draw a rectangle of L × W (mm), normalised so max dimension = 1.
    L on X-axis, W on Y-axis.
    """
    scale = max(L, W)
    lx = L / scale
    wy = W / scale
    corners = ['OC80'] * 4
    pts_n   = [(0,0),(lx,0),(lx,wy),(0,wy)]
    _draw_polygon(ax, [p[0] for p in pts_n], [p[1] for p in pts_n], corners)

    pad = 0.22
    ax.set_xlim(-pad, lx + pad)
    ax.set_ylim(-pad, wy + pad)

    # Dimension arrows
    _dim_arrow(ax, (0, wy + 0.12), (lx, wy + 0.12), f'{int(L)}mm')
    _dim_arrow(ax, (lx + 0.12, 0), (lx + 0.12, wy), f'{int(W)}mm')


def _render_l_shape(ax, pts, corners, raw_w, raw_h, scale):
    """
    Draw an L-shape from normalised pts.
    Adds dimension arrows for overall L and W.
    """
    nxs, nys = [p[0] for p in pts], [p[1] for p in pts]
    _draw_polygon(ax, nxs, nys, corners)

    w_n = raw_w / scale
    h_n = raw_h / scale
    pad = 0.22

    ax.set_xlim(-pad, w_n + pad)
    ax.set_ylim(-pad, h_n + pad)

    _dim_arrow(ax, (0, h_n + 0.12), (w_n, h_n + 0.12), f'{int(raw_w)}mm')
    _dim_arrow(ax, (w_n + 0.12, 0), (w_n + 0.12, h_n), f'{int(raw_h)}mm')


def _render_generic_polygon(ax, pts, corners, raw_w, raw_h, scale):
    """
    Fallback renderer for T / E / CUSTOM shapes.
    Draws from normalised polygon vertices; adds bounding-box dimensions.
    """
    nxs = [p[0] for p in pts]
    nys = [p[1] for p in pts]
    _draw_polygon(ax, nxs, nys, corners)

    w_n = raw_w / scale
    h_n = raw_h / scale
    pad = 0.22

    ax.set_xlim(-pad, w_n + pad)
    ax.set_ylim(-pad, h_n + pad)

    _dim_arrow(ax, (0, h_n + 0.12), (w_n, h_n + 0.12), f'{int(raw_w)}mm')
    _dim_arrow(ax, (w_n + 0.12, 0), (w_n + 0.12, h_n), f'{int(raw_h)}mm')


# ══════════════════════════════════════════════════════════════════════════════
#  DXF region extraction  (highest-fidelity when source DXF is available)
# ══════════════════════════════════════════════════════════════════════════════

def extract_dxf_region_image(doc, polygon_pts: list,
                             margin_mm: float = 400, dpi: int = 110) -> Optional[bytes]:
    """
    Render the DXF modelspace cropped to the bounding box of `polygon_pts`.
    Returns PNG bytes (monochrome on white) or None on failure.
    """
    try:
        from ezdxf.addons.drawing import RenderContext, Frontend
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
        from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy
    except ImportError:
        return None

    if not polygon_pts or len(polygon_pts) < 3:
        return None

    xs = [float(p[0]) for p in polygon_pts]
    ys = [float(p[1]) for p in polygon_pts]
    min_x, max_x = min(xs) - margin_mm, max(xs) + margin_mm
    min_y, max_y = min(ys) - margin_mm, max(ys) + margin_mm
    w_mm, h_mm   = max_x - min_x, max_y - min_y
    if w_mm <= 0 or h_mm <= 0:
        return None

    aspect = w_mm / h_mm
    ms     = 4.2
    fw     = min(ms, max(1.5, ms if aspect >= 1 else ms * aspect))
    fh     = min(ms, max(1.5, ms / aspect if aspect >= 1 else ms))

    try:
        fig, ax = plt.subplots(figsize=(fw, fh), dpi=dpi)
        ax.set_xlim(min_x, max_x); ax.set_ylim(min_y, max_y)
        ax.set_aspect('equal');    ax.axis('off')
        fig.patch.set_facecolor('white'); ax.set_facecolor('white')

        cfg = Configuration(background_policy=BackgroundPolicy.WHITE,
                            color_policy=ColorPolicy.MONOCHROME_LIGHT_BG)
        Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg)\
            .draw_layout(doc.modelspace())

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        data = buf.read()
        return data if len(data) > 3000 else None
    except Exception:
        try:
            plt.close(fig)
        except Exception:
            pass
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  Public diagram builders
# ══════════════════════════════════════════════════════════════════════════════

def make_rect_diagram(length_mm: float, width_mm: float,
                      label: str = '', boq: ElementBOQ = None,
                      dpi: int = 90) -> bytes:
    """Clean rectangle diagram with dimension arrows + panel summary."""
    L = max(float(length_mm), 1.0)
    W = max(float(width_mm), 1.0)

    scale  = max(L, W)
    lx, wy = L / scale, W / scale
    fw, fh = _figsize(lx, wy)

    fig = plt.figure(figsize=(fw, fh + 0.85), dpi=dpi,
                     constrained_layout=True)
    gs  = gridspec.GridSpec(2, 1, height_ratios=[4, 1], figure=fig)
    ax  = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])

    ax.set_aspect('equal')
    ax.axis('off')

    _render_rectangle(ax, L, W)
    if label:
        ax.set_title(label, fontsize=7.5, color='#444444', pad=2)

    if boq is not None:
        _draw_panel_summary(ax2, boq)
    else:
        ax2.axis('off')

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, facecolor='white', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def make_polygon_diagram(pts: list, label: str = '',
                         boq: ElementBOQ = None, dpi: int = 90) -> bytes:
    """
    Generate a shape diagram for any polygon element.

    Detects shape type (RECTANGLE / L / T / E / CUSTOM), draws the appropriate
    template scaled to actual dimensions, adds overall L and W dimension
    arrows, and shows a panel-summary table below.
    """
    if not pts or len(pts) < 3:
        return make_rect_diagram(500, 300, label=label, boq=boq, dpi=dpi)

    # ── Classify ──────────────────────────────────────────────────────────────
    try:
        from src.parsers.dwg_parser import _classify_polygon_corners
        corners = _classify_polygon_corners(pts)
    except Exception:
        corners = ['OC80'] * len(pts)

    shape_type = detect_shape_type(pts, corners)

    # ── Normalise ─────────────────────────────────────────────────────────────
    nxs, nys, scale, raw_w, raw_h = _normalize(pts)
    n_pts = [(nxs[i], nys[i]) for i in range(len(nxs))]

    w_n, h_n = raw_w / scale, raw_h / scale
    fw, fh   = _figsize(w_n, h_n)

    fig = plt.figure(figsize=(fw, fh + 0.85), dpi=dpi,
                     constrained_layout=True)
    gs  = gridspec.GridSpec(2, 1, height_ratios=[4, 1], figure=fig)
    ax  = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])

    ax.set_aspect('equal')
    ax.axis('off')

    # ── Render shape ──────────────────────────────────────────────────────────
    if shape_type == 'L_SHAPE':
        _render_l_shape(ax, n_pts, corners, raw_w, raw_h, scale)
    else:
        # T_SHAPE, E_SHAPE, CUSTOM — all drawn faithfully from vertices
        _render_generic_polygon(ax, n_pts, corners, raw_w, raw_h, scale)

    if label:
        ax.set_title(label, fontsize=7.5, color='#444444', pad=2)

    # ── Panel summary ─────────────────────────────────────────────────────────
    if boq is not None:
        _draw_panel_summary(ax2, boq)
    else:
        ax2.axis('off')

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, facecolor='white', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
#  Main dispatcher
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
#  Pre-defined shape image helpers
# ══════════════════════════════════════════════════════════════════════════════

def _static_image_path(label: str) -> Optional[Path]:
    """
    Return the Path to the pre-defined shape PNG for `label`, or None.
    Tries exact label, then uppercase, then lowercase (e.g. SW5, sw5).
    """
    if not _SHAPE_IMAGES_DIR.exists():
        return None
    for variant in (label, label.upper(), label.lower()):
        p = _SHAPE_IMAGES_DIR / f"{variant}.png"
        if p.exists():
            return p
    return None


def _embed_static_image(img_path: Path, boq: ElementBOQ, dpi: int = 90) -> bytes:
    """
    Wrap a pre-defined shape PNG in a 2-panel figure:
      top  — the original client image (white background, as-is)
      bottom — panel summary table
    """
    el = boq.element

    # Load image to numpy array (try PIL first, fall back to matplotlib reader)
    arr = None
    img_w, img_h = 200, 200
    try:
        from PIL import Image as PILImage
        pil_img = PILImage.open(img_path).convert('RGB')
        arr = np.array(pil_img)
        img_h, img_w = arr.shape[:2]
    except Exception:
        try:
            import matplotlib.image as mpimg
            arr = mpimg.imread(str(img_path))
            img_h, img_w = arr.shape[:2]
        except Exception:
            arr = None

    fw, fh = _figsize(img_w, img_h, max_side=3.6)

    fig = plt.figure(figsize=(fw, fh + 0.85), dpi=dpi,
                     constrained_layout=True)
    gs  = gridspec.GridSpec(2, 1, height_ratios=[4, 1], figure=fig)
    ax  = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])

    ax.axis('off')
    if arr is not None:
        ax.imshow(arr, aspect='auto')
    else:
        # Fallback: just show label text if image couldn't be loaded
        ax.text(0.5, 0.5, el.label, ha='center', va='center',
                fontsize=14, color='#CC0000', transform=ax.transAxes)
    ax.set_title(el.label, fontsize=7.5, color='#444444', pad=2)

    _draw_panel_summary(ax2, boq)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, facecolor='white', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
#  Main dispatcher
# ══════════════════════════════════════════════════════════════════════════════

def make_face_panel_diagram(boq: ElementBOQ, dpi: int = 100) -> bytes:
    """
    Top-down rectangular view showing which panels go on each face.
    Face A & A' = length faces (front/back).
    Face B & B' = width faces (left/right sides).
    """
    el   = boq.element
    L_mm = max(float(el.length_mm), 1.0)
    W_mm = max(float(el.width_mm),  1.0)

    fp_map = {f['face']: f for f in (getattr(boq, 'face_panels', None) or [])}
    if not fp_map:
        return make_rect_diagram(L_mm, W_mm, label=el.label, boq=boq, dpi=dpi)

    # Normalized coordinates: element spans (0, 0) → (1.0, aspect)
    # 1 unit on both X and Y axes = L_mm in real world
    aspect  = W_mm / L_mm
    strip_n = 0.20      # strip thickness in normalized units
    pad_n   = 0.06

    x0, x1 = -strip_n - pad_n, 1.0 + strip_n + pad_n
    y0, y1 = -strip_n - pad_n, aspect + strip_n + pad_n
    span_x  = x1 - x0
    span_y  = y1 - y0

    max_side = 4.5
    if span_x >= span_y:
        fw = max_side
        fh = max(1.8, max_side * span_y / span_x)
    else:
        fh = max_side
        fw = max(1.8, max_side * span_x / span_y)

    fig, ax = plt.subplots(figsize=(fw, fh), dpi=dpi)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    fig.patch.set_facecolor('white')

    # Element rectangle
    ax.add_patch(mpatches.Rectangle(
        (0, 0), 1.0, aspect,
        facecolor='#FFE8EC', edgecolor='#C0001A', linewidth=1.5, zorder=2
    ))
    ax.text(0.5, aspect / 2,
            f'{el.label}\n{int(L_mm)}×{int(W_mm)} mm',
            ha='center', va='center', fontsize=6.5, color='#333333',
            fontweight='bold', zorder=3, ma='center')

    # Consistent color per standard panel width
    _STD_W = [600, 500, 490, 440, 400, 350, 340, 300, 275, 250,
              230, 200, 150, 125, 100, 40]
    _CLR   = ['#A8D8FF', '#B8F0C8', '#FFD6A5', '#FFADAD',
              '#C3ABFF', '#FFF1A8', '#AAF0F0', '#FFCCE8',
              '#DDFFD8', '#FFE5CC', '#CCDDFF', '#F0DDFF',
              '#FFEECC', '#CCFFEE', '#FFCCDD', '#EEFFCC']

    def _pcolor(w: int) -> str:
        try:
            return _CLR[_STD_W.index(w) % len(_CLR)]
        except ValueError:
            return _CLR[int(w) % len(_CLR)]

    def _draw_h_strips(face_key: str, y_bot: float, y_top: float, above: bool):
        """Horizontal panel strips (Face A / A') spanning the length direction."""
        fp = fp_map.get(face_key, {})
        panels_mm = fp.get('panels', [])
        spacer_mm = fp.get('spacer', 0.0)
        dim_mm    = fp.get('dim_mm', L_mm)
        x = 0.0
        for pw in panels_mm:
            pw_n = pw / L_mm
            ax.add_patch(mpatches.Rectangle(
                (x, y_bot), pw_n, y_top - y_bot,
                facecolor=_pcolor(int(pw)), edgecolor='#555555',
                linewidth=0.6, zorder=3
            ))
            fs = 4.5 if pw < 200 else 5.5
            ax.text(x + pw_n / 2, (y_bot + y_top) / 2, str(int(pw)),
                    ha='center', va='center', fontsize=fs,
                    color='#111111', fontweight='bold', zorder=4)
            x += pw_n
        if spacer_mm > 0:
            sp_n = spacer_mm / L_mm
            ax.add_patch(mpatches.Rectangle(
                (x, y_bot), sp_n, y_top - y_bot,
                facecolor='#E0E0E0', edgecolor='#AAAAAA',
                linewidth=0.4, linestyle='--', zorder=3
            ))
        # Dimension label on the strip edge
        lbl_y = y_top + pad_n * 0.25 if above else y_bot - pad_n * 0.25
        va    = 'bottom' if above else 'top'
        ax.text(0.5, lbl_y, f'{face_key} ({int(dim_mm)} mm)',
                ha='center', va=va, fontsize=5.0,
                color='#C0001A', fontweight='bold', zorder=4)

    def _draw_v_strips(face_key: str, x_left: float, x_right: float, on_right: bool):
        """Vertical panel strips (Face B / B') spanning the width direction."""
        fp = fp_map.get(face_key, {})
        panels_mm = fp.get('panels', [])
        spacer_mm = fp.get('spacer', 0.0)
        dim_mm    = fp.get('dim_mm', W_mm)
        y = 0.0
        for pw in panels_mm:
            pw_n = pw / L_mm   # same scale: 1 unit = L_mm
            ax.add_patch(mpatches.Rectangle(
                (x_left, y), x_right - x_left, pw_n,
                facecolor=_pcolor(int(pw)), edgecolor='#555555',
                linewidth=0.6, zorder=3
            ))
            fs = 4.5 if pw < 200 else 5.5
            ax.text((x_left + x_right) / 2, y + pw_n / 2, str(int(pw)),
                    ha='center', va='center', fontsize=fs,
                    color='#111111', fontweight='bold', rotation=90, zorder=4)
            y += pw_n
        if spacer_mm > 0:
            sp_n = spacer_mm / L_mm
            ax.add_patch(mpatches.Rectangle(
                (x_left, y), x_right - x_left, sp_n,
                facecolor='#E0E0E0', edgecolor='#AAAAAA',
                linewidth=0.4, linestyle='--', zorder=3
            ))
        # Dimension label beside the strip
        lbl_x = x_right + pad_n * 0.25 if on_right else x_left - pad_n * 0.25
        ha    = 'left' if on_right else 'right'
        ax.text(lbl_x, aspect / 2,
                f'{face_key}\n({int(dim_mm)} mm)',
                ha=ha, va='center', fontsize=4.5,
                color='#C0001A', fontweight='bold',
                rotation=90 if on_right else -90,
                rotation_mode='anchor', zorder=4)

    # Face A — top (length direction)
    _draw_h_strips('A',  y_bot=aspect,         y_top=aspect + strip_n, above=True)
    # Face A' — bottom (length direction, opposite)
    _draw_h_strips("A'", y_bot=-strip_n,        y_top=0.0,              above=False)
    # Face B — right (width direction)
    _draw_v_strips('B',  x_left=1.0,            x_right=1.0 + strip_n,  on_right=True)
    # Face B' — left (width direction, opposite)
    _draw_v_strips("B'", x_left=-strip_n,       x_right=0.0,            on_right=False)

    # OC80 corner dots at all 4 corners
    for cx, cy in [(0, 0), (1.0, 0), (1.0, aspect), (0, aspect)]:
        ax.plot(cx, cy, 's', color='#CC4444', markersize=6,
                markeredgecolor='#AA0000', markeredgewidth=0.5, zorder=6)

    ax.set_title(f'{el.label} — Panel Layout (Top View)',
                 fontsize=7, color='#444444', pad=3)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def make_element_diagram(boq: ElementBOQ, dxf_doc=None, dpi: int = 90) -> bytes:
    """
    Generate the best available floor-plan diagram for an element.

    Priority:
      0. Pre-defined PNG  — assets/images/ShearWall Images/{label}.png
      1. DXF region       — rendered from source DXF (complex polygon)
      2. Generated polygon — L / T / E / CUSTOM from polygon_pts
      3. Generated rect    — columns and simple walls
    """
    el       = boq.element
    poly_pts = getattr(el, 'polygon_pts', None) or []
    is_complex = len(poly_pts) > 4

    # ── 0. Pre-defined client shape image (highest priority) ──────────────────
    img_path = _static_image_path(el.label)
    if img_path is not None:
        return _embed_static_image(img_path, boq, dpi=dpi)

    # ── 1. DXF region (pixel-perfect from actual drawing) ─────────────────────
    if dxf_doc is not None and is_complex:
        img = extract_dxf_region_image(dxf_doc, poly_pts, dpi=dpi)
        if img:
            try:
                from PIL import Image as PILImage
                pil_img = PILImage.open(io.BytesIO(img)).convert('RGB')
                arr_dxf = np.array(pil_img)
                fw, fh  = _figsize(pil_img.width, pil_img.height, max_side=3.6)
                fig = plt.figure(figsize=(fw, fh + 0.85), dpi=dpi,
                                 constrained_layout=True)
                gs  = gridspec.GridSpec(2, 1, height_ratios=[4, 1], figure=fig)
                ax  = fig.add_subplot(gs[0])
                ax2 = fig.add_subplot(gs[1])
                ax.imshow(arr_dxf)
                ax.axis('off')
                ax.set_title(el.label, fontsize=7.5, color='#444444', pad=2)
                _draw_panel_summary(ax2, boq)
                buf = io.BytesIO()
                fig.savefig(buf, format='png', dpi=dpi,
                            facecolor='white', edgecolor='none')
                plt.close(fig)
                buf.seek(0)
                return buf.read()
            except Exception:
                pass

    # ── 2. Generated polygon diagram ───────────────────────────────────────────
    if is_complex:
        return make_polygon_diagram(poly_pts, label=el.label, boq=boq, dpi=dpi)

    # ── 3. Face-panel layout diagram (rectangular columns & shear walls) ───────
    if getattr(boq, 'face_panels', None):
        return make_face_panel_diagram(boq, dpi=dpi)

    # ── 4. Plain rectangle diagram ─────────────────────────────────────────────
    return make_rect_diagram(el.length_mm, el.width_mm,
                             label=el.label, boq=boq, dpi=dpi)
