"""
Panel Layout Drawing Generator.

Generates visual panel layout drawings using matplotlib:
- Column: unrolled 4-face strip view + plan cross-section
- Wall: front-face elevation with waller and tierod markers
"""
import math
import os
import tempfile

import matplotlib
matplotlib.use('Agg')   # Non-interactive backend (no display needed)
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

from src.models.element import StructuralElement, ElementBOQ, ElementType
from src.engine.panel_optimizer import find_panel_combination, OC_WIDTH

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
NOVA_BLUE   = '#1a3a5c'
NOVA_ACCENT = '#2c5f8a'

OC_COLOR    = '#f39c12'        # Orange for OC corners
SPACER_CLR  = '#ecf0f1'        # Light grey for spacer
WALLER_CLR  = '#c0392b'        # Red for waller lines
TIEROD_CLR  = '#2980b9'        # Blue for tierod markers
FACE_EDGE   = '#34495e'        # Dark edge color

# Cycling palette for flat panels (by width bucket)
_PANEL_PALETTE = [
    '#3498db', '#2ecc71', '#9b59b6', '#1abc9c',
    '#e67e22', '#16a085', '#8e44ad', '#27ae60',
]


def _panel_color(width_mm: int, color_map: dict) -> str:
    """Assign a consistent color to each unique panel width."""
    if width_mm not in color_map:
        idx = len(color_map) % len(_PANEL_PALETTE)
        color_map[width_mm] = _PANEL_PALETTE[idx]
    return color_map[width_mm]


# ---------------------------------------------------------------------------
# Column layout
# ---------------------------------------------------------------------------

def _draw_column_layout(
    element: StructuralElement,
    panel_height_mm: float,
    ax_strip: plt.Axes,
    ax_plan: plt.Axes,
):
    """
    Draw column formwork layout.

    ax_strip : "Unrolled" strip view — 4 faces laid flat side by side
    ax_plan  : Plan (top) cross-section view
    """
    L = element.length_mm   # length face dimension
    W = element.width_mm    # width face dimension
    H = element.height_mm
    rows = max(1, math.ceil(H / panel_height_mm))
    ph   = panel_height_mm

    len_combo, len_spacer = find_panel_combination(L)
    wid_combo, wid_spacer = find_panel_combination(W)

    color_map: dict[int, str] = {}
    legend_patches = []
    seen_labels: set = set()

    # ----------------------------------------------------------------
    # STRIP VIEW: 4 faces unrolled horizontally
    # ----------------------------------------------------------------
    #  [OC] [Face1=Length panels] [OC] [Face2=Width panels]
    #  [OC] [Face3=Length panels] [OC] [Face4=Width panels]
    # ----------------------------------------------------------------
    ax_strip.set_xlim(0, 1)
    ax_strip.set_ylim(0, 1)

    face_seqs = [
        ('L1', L, len_combo, len_spacer),
        ('W1', W, wid_combo, wid_spacer),
        ('L2', L, len_combo, len_spacer),
        ('W2', W, wid_combo, wid_spacer),
    ]

    # Total drawn width (actual mm, will normalize)
    total_w_mm = 4 * OC_WIDTH + 2 * sum(len_combo) + 2 * sum(wid_combo)
    total_h_mm = rows * ph

    scale_x = 1.0 / total_w_mm
    scale_y = 1.0 / total_h_mm

    cursor_x = 0

    for face_name, face_dim, combo, spacer in face_seqs:
        # OC corner at start of each face
        oc_x = cursor_x
        for row in range(rows):
            ry = row * ph
            rect = Rectangle(
                (oc_x * scale_x, ry * scale_y),
                OC_WIDTH * scale_x, ph * scale_y,
                facecolor=OC_COLOR, edgecolor=FACE_EDGE, linewidth=0.5, zorder=3
            )
            ax_strip.add_patch(rect)
            if row == 0:
                ax_strip.text(
                    (oc_x + OC_WIDTH / 2) * scale_x,
                    (ry + ph / 2) * scale_y,
                    f'OC\n{OC_WIDTH}',
                    ha='center', va='center', fontsize=5, color='white',
                    fontweight='bold', zorder=4
                )
        cursor_x += OC_WIDTH

        if 'OC corner' not in seen_labels:
            legend_patches.append(mpatches.Patch(color=OC_COLOR, label=f'OC{OC_WIDTH} Corner'))
            seen_labels.add('OC corner')

        # Flat panels
        for pw in combo:
            col = _panel_color(pw, color_map)
            for row in range(rows):
                ry = row * ph
                rect = Rectangle(
                    (cursor_x * scale_x, ry * scale_y),
                    pw * scale_x, ph * scale_y,
                    facecolor=col, edgecolor=FACE_EDGE, linewidth=0.5, zorder=3,
                    alpha=0.88
                )
                ax_strip.add_patch(rect)
                if row == 0:
                    ax_strip.text(
                        (cursor_x + pw / 2) * scale_x,
                        (ry + ph / 2) * scale_y,
                        str(pw),
                        ha='center', va='center', fontsize=5.5,
                        color='white', fontweight='bold', zorder=4
                    )
            lbl = f'{pw}mm panel'
            if lbl not in seen_labels:
                legend_patches.append(mpatches.Patch(color=col, label=lbl))
                seen_labels.add(lbl)
            cursor_x += pw

        # Spacer (if any)
        if spacer > 0:
            for row in range(rows):
                ry = row * ph
                srect = Rectangle(
                    (cursor_x * scale_x, ry * scale_y),
                    spacer * scale_x, ph * scale_y,
                    facecolor=SPACER_CLR, edgecolor='#bdc3c7', linewidth=0.5,
                    linestyle='--', zorder=3
                )
                ax_strip.add_patch(srect)
                if row == 0:
                    ax_strip.text(
                        (cursor_x + spacer / 2) * scale_x,
                        (ry + ph / 2) * scale_y,
                        f'{spacer:.0f}\nsp',
                        ha='center', va='center', fontsize=4.5, color='#7f8c8d', zorder=4
                    )
            if 'Spacer' not in seen_labels:
                legend_patches.append(mpatches.Patch(
                    facecolor=SPACER_CLR, edgecolor='#bdc3c7', linestyle='--', label='Spacer gap'))
                seen_labels.add('Spacer')
            cursor_x += spacer

        # Face label
        ax_strip.text(
            ((oc_x + OC_WIDTH + sum(combo) / 2) * scale_x),
            1.01,
            face_name,
            ha='center', va='bottom', fontsize=7, color=NOVA_BLUE, fontweight='bold',
            transform=ax_strip.transData
        )

    # Row dividers (horizontal lines between stacked rows)
    for row in range(1, rows):
        y = row * ph * scale_y
        ax_strip.axhline(y=y, color='#2c3e50', linewidth=0.8, linestyle='--', zorder=5)

    # Y-axis labels (row heights)
    for row in range(rows):
        y_mid = (row + 0.5) * ph * scale_y
        ax_strip.text(-0.01, y_mid, f'Row {row+1}\n{ph:.0f}mm',
                      ha='right', va='center', fontsize=6, color=NOVA_BLUE,
                      transform=ax_strip.transData)

    ax_strip.set_xlim(-0.05, 1.02)
    ax_strip.set_ylim(-0.05, 1.1)
    ax_strip.axis('off')
    ax_strip.set_title(
        f'Unrolled Face View  |  4 faces  |  {rows} row(s) × {ph:.0f}mm',
        fontsize=8, color=NOVA_BLUE, pad=4, fontweight='bold'
    )

    # Legend
    ax_strip.legend(handles=legend_patches, loc='lower center',
                    fontsize=6, ncol=min(6, len(legend_patches)),
                    bbox_to_anchor=(0.5, -0.08), framealpha=0.9)

    # ----------------------------------------------------------------
    # PLAN VIEW: Cross-section from above
    # ----------------------------------------------------------------
    margin = max(L, W) * 0.25
    ax_plan.set_xlim(-margin, L + margin)
    ax_plan.set_ylim(-margin, W + margin)
    ax_plan.set_aspect('equal')

    # Column body
    col_rect = Rectangle((0, 0), L, W,
                          facecolor='#bdc3c7', edgecolor=NOVA_BLUE,
                          linewidth=2, zorder=2)
    ax_plan.add_patch(col_rect)
    ax_plan.text(L / 2, W / 2, f'{L:.0f}×{W:.0f}',
                 ha='center', va='center', fontsize=9,
                 color=NOVA_BLUE, fontweight='bold', zorder=3)

    # OC corners
    oc_size = OC_WIDTH
    corners = [
        (-oc_size, -oc_size),
        (L, -oc_size),
        (L, W),
        (-oc_size, W),
    ]
    for cx, cy in corners:
        ax_plan.add_patch(Rectangle(
            (cx, cy), oc_size, oc_size,
            facecolor=OC_COLOR, edgecolor=FACE_EDGE, linewidth=1, zorder=4
        ))
        ax_plan.text(cx + oc_size / 2, cy + oc_size / 2, 'OC',
                     ha='center', va='center', fontsize=6, color='white',
                     fontweight='bold', zorder=5)

    # Dimension arrows
    ax_plan.annotate('', xy=(L, -margin * 0.55), xytext=(0, -margin * 0.55),
                     arrowprops=dict(arrowstyle='<->', color=NOVA_ACCENT, lw=1.2))
    ax_plan.text(L / 2, -margin * 0.65, f'{L:.0f}mm',
                 ha='center', va='top', fontsize=7, color=NOVA_ACCENT)

    ax_plan.annotate('', xy=(-margin * 0.55, W), xytext=(-margin * 0.55, 0),
                     arrowprops=dict(arrowstyle='<->', color=NOVA_ACCENT, lw=1.2))
    ax_plan.text(-margin * 0.65, W / 2, f'{W:.0f}mm',
                 ha='right', va='center', fontsize=7, color=NOVA_ACCENT, rotation=90)

    ax_plan.axis('off')
    ax_plan.set_title('Plan View (Cross-Section)', fontsize=8,
                       color=NOVA_BLUE, pad=4, fontweight='bold')


# ---------------------------------------------------------------------------
# Wall layout
# ---------------------------------------------------------------------------

def _draw_wall_layout(
    element: StructuralElement,
    panel_height_mm: float,
    acc_data: dict,      # accessories summary dict (may be None)
    ax_elev: plt.Axes,
):
    """
    Draw wall formwork elevation (front face view).
    Shows panel grid, waller lines, tierod positions.
    """
    L = element.length_mm   # wall length
    W = element.width_mm    # wall thickness (for tierod length display)
    H = element.height_mm
    rows = max(1, math.ceil(H / panel_height_mm))
    ph   = panel_height_mm

    combo, spacer = find_panel_combination(L)

    # Accessories info from accessories_calc module constants
    from src.engine.accessories_calc import WALLER_V_SPACING_MM, TIEROD_H_SPACING_MM

    color_map: dict[int, str] = {}
    legend_items = []
    seen_labels: set = set()

    scale = 1.0 / max(L, rows * ph)
    x_off = 0.0  # OC at start

    total_w_mm = OC_WIDTH + sum(combo) + (spacer if spacer > 0 else 0) + OC_WIDTH

    # Draw elevation: X = along length, Y = height
    ax_elev.set_aspect('auto')

    # OC at left end
    for row in range(rows):
        ry = row * ph
        ax_elev.add_patch(Rectangle(
            (0, ry), OC_WIDTH, ph,
            facecolor=OC_COLOR, edgecolor=FACE_EDGE, linewidth=0.6, zorder=3
        ))
        if row == 0:
            ax_elev.text(OC_WIDTH / 2, ry + ph / 2, f'OC\n{OC_WIDTH}',
                         ha='center', va='center', fontsize=5.5, color='white',
                         fontweight='bold', zorder=4)
    cursor_x = OC_WIDTH

    # Flat panels
    for pw in combo:
        col = _panel_color(pw, color_map)
        for row in range(rows):
            ry = row * ph
            ax_elev.add_patch(Rectangle(
                (cursor_x, ry), pw, ph,
                facecolor=col, edgecolor=FACE_EDGE, linewidth=0.5,
                alpha=0.85, zorder=3
            ))
            ax_elev.text(cursor_x + pw / 2, ry + ph / 2, str(pw),
                         ha='center', va='center', fontsize=5.5, color='white',
                         fontweight='bold', zorder=4)
        lbl = f'{pw}mm panel'
        if lbl not in seen_labels:
            legend_items.append(mpatches.Patch(color=col, label=lbl))
            seen_labels.add(lbl)
        cursor_x += pw

    # Spacer
    if spacer > 0:
        for row in range(rows):
            ry = row * ph
            ax_elev.add_patch(Rectangle(
                (cursor_x, ry), spacer, ph,
                facecolor=SPACER_CLR, edgecolor='#bdc3c7', linewidth=0.5,
                linestyle='--', zorder=3
            ))
            if row == 0:
                ax_elev.text(cursor_x + spacer / 2, ry + ph / 2,
                             f'{spacer:.0f}\nsp',
                             ha='center', va='center', fontsize=4.5,
                             color='#7f8c8d', zorder=4)
        if 'Spacer' not in seen_labels:
            legend_items.append(mpatches.Patch(
                facecolor=SPACER_CLR, edgecolor='#bdc3c7', linestyle='--', label='Spacer gap'))
            seen_labels.add('Spacer')
        cursor_x += spacer

    # OC at right end
    for row in range(rows):
        ry = row * ph
        ax_elev.add_patch(Rectangle(
            (cursor_x, ry), OC_WIDTH, ph,
            facecolor=OC_COLOR, edgecolor=FACE_EDGE, linewidth=0.6, zorder=3
        ))
        if row == 0:
            ax_elev.text(cursor_x + OC_WIDTH / 2, ry + ph / 2, f'OC\n{OC_WIDTH}',
                         ha='center', va='center', fontsize=5.5, color='white',
                         fontweight='bold', zorder=4)
    if 'OC corner' not in seen_labels:
        legend_items.append(mpatches.Patch(color=OC_COLOR, label=f'OC{OC_WIDTH} Corner'))
        seen_labels.add('OC corner')

    total_drawn_w = cursor_x + OC_WIDTH
    total_drawn_h = rows * ph

    # Panel row horizontal dividers
    for row in range(1, rows):
        ax_elev.axhline(y=row * ph, xmin=0, xmax=1,
                        color='#2c3e50', linewidth=1.0, linestyle='--', zorder=5)

    # ── Waller lines ──
    # One waller every WALLER_V_SPACING_MM, starting from bottom
    waller_rows_count = math.ceil(H / WALLER_V_SPACING_MM) + 1
    waller_y_positions = [
        (i / (waller_rows_count - 1)) * (rows * ph)
        if waller_rows_count > 1 else rows * ph / 2
        for i in range(waller_rows_count)
    ]
    for wy in waller_y_positions:
        ax_elev.axhline(y=wy, color=WALLER_CLR, linewidth=2.0,
                        linestyle='-', zorder=6, alpha=0.85)
        ax_elev.text(total_drawn_w + 50, wy, 'W',
                     va='center', ha='left', fontsize=6, color=WALLER_CLR,
                     fontweight='bold', zorder=7)

    if 'Waller' not in seen_labels:
        legend_items.append(Line2D([0], [0], color=WALLER_CLR, linewidth=2.5,
                                   linestyle='-', label='Waller position'))
        seen_labels.add('Waller')

    # ── Tierod markers ──
    tierod_x_count = math.ceil(L / TIEROD_H_SPACING_MM)
    tierod_x_positions = [
        OC_WIDTH + (i + 0.5) * (L / tierod_x_count)
        for i in range(tierod_x_count)
    ]
    for wy in waller_y_positions:
        for tx in tierod_x_positions:
            ax_elev.plot(tx, wy, 'o', color=TIEROD_CLR,
                         markersize=5, markeredgecolor='white',
                         markeredgewidth=0.5, zorder=8)

    if 'Tierod' not in seen_labels:
        legend_items.append(Line2D([0], [0], marker='o', color='w',
                                   markerfacecolor=TIEROD_CLR, markersize=7,
                                   label='Tierod position'))
        seen_labels.add('Tierod')

    # Axes formatting
    ax_elev.set_xlim(-100, total_drawn_w + 250)
    ax_elev.set_ylim(-ph * 0.15, total_drawn_h + ph * 0.15)

    # Dimension annotations
    ax_elev.annotate('', xy=(total_drawn_w, -ph * 0.08),
                     xytext=(0, -ph * 0.08),
                     arrowprops=dict(arrowstyle='<->', color=NOVA_ACCENT, lw=1.2))
    ax_elev.text(total_drawn_w / 2, -ph * 0.12,
                 f'{L:.0f}mm (wall length)',
                 ha='center', va='top', fontsize=7, color=NOVA_ACCENT)

    ax_elev.annotate('', xy=(-80, total_drawn_h),
                     xytext=(-80, 0),
                     arrowprops=dict(arrowstyle='<->', color=NOVA_ACCENT, lw=1.2))
    ax_elev.text(-90, total_drawn_h / 2,
                 f'{rows * ph:.0f}mm',
                 ha='right', va='center', fontsize=7, color=NOVA_ACCENT, rotation=90)

    ax_elev.axis('off')
    ax_elev.set_title(
        f'Wall Face Elevation  |  {rows} row(s) × {ph:.0f}mm  |  '
        f'{waller_rows_count} waller rows  |  {tierod_x_count} tierod cols',
        fontsize=8, color=NOVA_BLUE, pad=4, fontweight='bold'
    )

    ax_elev.legend(handles=legend_items, loc='lower center',
                   fontsize=6, ncol=min(6, len(legend_items)),
                   bbox_to_anchor=(0.5, -0.1), framealpha=0.9)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_element_layout(
    element: StructuralElement,
    boq: ElementBOQ,
    panel_height_mm: float,
    output_path: str = None,
    acc_agg: dict = None,
) -> str:
    """
    Generate a panel layout drawing for one element.

    Args:
        element      : The structural element
        boq          : Its computed BOQ
        panel_height_mm : Panel height in use
        output_path  : Where to save PNG (if None, a temp file is created)
        acc_agg      : Optional accessories aggregate (for waller/tierod data)

    Returns:
        Path to saved PNG file.
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix='.png', prefix='layout_')
        os.close(fd)

    is_col = element.is_column

    if is_col:
        fig = plt.figure(figsize=(14, 6), facecolor='white')
        # Left 2/3 = strip, right 1/3 = plan
        ax_strip = fig.add_axes([0.02, 0.12, 0.62, 0.72])
        ax_plan  = fig.add_axes([0.68, 0.12, 0.28, 0.72])
    else:
        fig = plt.figure(figsize=(14, 6), facecolor='white')
        ax_elev = fig.add_axes([0.04, 0.15, 0.90, 0.68])

    # Master title
    h_achieved = int(math.ceil(element.height_mm / panel_height_mm)) * panel_height_mm
    etype_str = element.element_type.value.upper()
    fig.suptitle(
        f'{etype_str}  {element.label}   |   '
        f'{element.length_mm:.0f} × {element.width_mm:.0f} mm   |   '
        f'H = {element.height_mm:.0f} mm  →  achieved {h_achieved:.0f} mm   |   '
        f'Qty = {element.quantity}',
        fontsize=10, fontweight='bold', color=NOVA_BLUE, y=0.97
    )

    # Footer
    fig.text(0.5, 0.02,
             'Panel layout is schematic. Verify all dimensions on site before installation.  '
             '|  Nova Formworks Pvt. Ltd.',
             ha='center', fontsize=6.5, color='#7f8c8d', style='italic')

    if is_col:
        _draw_column_layout(element, panel_height_mm, ax_strip, ax_plan)
    else:
        _draw_wall_layout(element, panel_height_mm, acc_agg, ax_elev)

    plt.savefig(output_path, dpi=130, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    return output_path


# ---------------------------------------------------------------------------
# 3D Panel Assembly — interactive Figure for dialog embedding
# ---------------------------------------------------------------------------

def generate_element_layout_3d_figure(
    element: StructuralElement,
    boq: ElementBOQ,
    panel_height_mm: float,
    acc_agg: dict = None,
):
    """
    Build an interactive 3D panel-assembly figure.

    Returns a matplotlib Figure (NOT saved to disk).
    Embed in FigureCanvasQTAgg → user can rotate with mouse.

    Layout:
      Left  — 3D isometric view of assembled formwork panels
      Right — panel schedule (by face + summary)
    """
    from mpl_toolkits.mplot3d import Axes3D              # noqa
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    L_mm  = element.length_mm
    W_mm  = element.width_mm
    H_mm  = element.height_mm
    ph_mm = panel_height_mm

    L  = L_mm  / 1000   # metres
    W  = W_mm  / 1000
    H  = H_mm  / 1000
    oc = OC_WIDTH / 1000

    rows  = max(1, math.ceil(H_mm / ph_mm))
    row_h = H / rows

    combo_L, spacer_L = find_panel_combination(L_mm)
    combo_W, spacer_W = find_panel_combination(W_mm)

    # ── Figure setup ──────────────────────────────────────────────────────
    fig = plt.figure(figsize=(15, 9), facecolor='white')

    # 3D subplot (left 60%)
    ax3d = fig.add_axes([0.02, 0.08, 0.58, 0.84], projection='3d')
    ax3d.set_facecolor('#f0f4f8')

    # Info subplot (right 38%)
    ax_info = fig.add_axes([0.63, 0.08, 0.35, 0.84])
    ax_info.axis('off')

    # ── Color helpers ─────────────────────────────────────────────────────
    _palette  = ['#3498db','#2ecc71','#9b59b6','#e74c3c',
                 '#1abc9c','#16a085','#8e44ad','#d35400']
    _cmap: dict = {}

    def _pcol(w_mm: int) -> str:
        if w_mm not in _cmap:
            _cmap[w_mm] = _palette[len(_cmap) % len(_palette)]
        return _cmap[w_mm]

    OC_CLR  = '#f39c12'
    EDG_CLR = 'white'

    def _quad(p1, p2, p3, p4, color, alpha=0.90, lw=0.5):
        poly = Poly3DCollection([[p1, p2, p3, p4]])
        poly.set_facecolor(color)
        poly.set_edgecolor(EDG_CLR)
        poly.set_linewidth(lw)
        poly.set_alpha(alpha)
        ax3d.add_collection3d(poly)

    # ── Draw panels on each face ───────────────────────────────────────────
    is_col = element.is_column

    if is_col:
        for row in range(rows):
            z0 = row * row_h
            z1 = z0 + row_h

            # Face 1 — front (y=0): panels along x
            x = 0.0
            for w in combo_L:
                pw = w / 1000
                _quad((x,0,z0),(x+pw,0,z0),(x+pw,0,z1),(x,0,z1), _pcol(w))
                x += pw

            # Face 2 — right (x=L): panels along y
            y = 0.0
            for w in combo_W:
                pw = w / 1000
                _quad((L,y,z0),(L,y+pw,z0),(L,y+pw,z1),(L,y,z1), _pcol(w))
                y += pw

            # Face 3 — back (y=W): panels along x reversed
            x = L
            for w in combo_L:
                pw = w / 1000
                _quad((x,W,z0),(x-pw,W,z0),(x-pw,W,z1),(x,W,z1), _pcol(w))
                x -= pw

            # Face 4 — left (x=0): panels along y reversed
            y = W
            for w in combo_W:
                pw = w / 1000
                _quad((0,y,z0),(0,y-pw,z0),(0,y-pw,z1),(0,y,z1), _pcol(w))
                y -= pw

        # OC corner strips — orange vertical sliver on each corner edge
        for row in range(rows):
            z0 = row * row_h
            z1 = z0 + row_h
            for (cx, cy) in [(0, 0), (L, 0), (L, W), (0, W)]:
                # Thin orange strip on the front-face side of each corner
                strip_w = min(oc, 0.12)
                if cx == 0:
                    _quad((cx, cy, z0),(cx+strip_w, cy, z0),
                          (cx+strip_w, cy, z1),(cx, cy, z1), OC_CLR, 0.95)
                else:
                    _quad((cx-strip_w, cy, z0),(cx, cy, z0),
                          (cx, cy, z1),(cx-strip_w, cy, z1), OC_CLR, 0.95)

        # Semi-transparent inner concrete box
        _box_faces = [
            [(0,0,0),(L,0,0),(L,W,0),(0,W,0)],  # bottom
            [(0,0,H),(L,0,H),(L,W,H),(0,W,H)],  # top
        ]
        inner = Poly3DCollection(_box_faces)
        inner.set_facecolor('#bdc3c7')
        inner.set_edgecolor('#7f8c8d')
        inner.set_linewidth(0.5)
        inner.set_alpha(0.25)
        ax3d.add_collection3d(inner)

    else:
        # WALL — show 2 faces with waller lines
        for row in range(rows):
            z0 = row * row_h
            z1 = z0 + row_h
            # Front face (y=0)
            x = 0.0
            for w in combo_L:
                pw = w / 1000
                _quad((x,0,z0),(x+pw,0,z0),(x+pw,0,z1),(x,0,z1), _pcol(w))
                x += pw
            # Back face (y=W)
            x = 0.0
            for w in combo_L:
                pw = w / 1000
                _quad((x,W,z0),(x+pw,W,z0),(x+pw,W,z1),(x+pw,W,z1), _pcol(w))
                x += pw

        # Waller lines on front face
        from src.engine.accessories_calc import WALLER_V_SPACING_MM
        w_rows = math.ceil(H_mm / WALLER_V_SPACING_MM) + 1
        for i in range(w_rows):
            wz = i * (H / max(w_rows - 1, 1))
            ax3d.plot([0, L], [0, 0], [wz, wz],
                      color='#c0392b', linewidth=2.0, alpha=0.8, zorder=10)

    # ── Axis styling ──────────────────────────────────────────────────────
    span = max(L, W) * 1.1
    ax3d.set_xlim(0, span)
    ax3d.set_ylim(0, span)
    ax3d.set_zlim(0, H * 1.05)
    ax3d.set_xlabel('Length (m)', color=NOVA_BLUE, fontsize=8, labelpad=8)
    ax3d.set_ylabel('Width (m)',  color=NOVA_BLUE, fontsize=8, labelpad=8)
    ax3d.set_zlabel('Height (m)', color=NOVA_BLUE, fontsize=8, labelpad=8)
    ax3d.tick_params(axis='both', labelsize=7, colors='#555')
    ax3d.view_init(elev=22, azim=225)
    ax3d.set_title(
        f'{element.label}  —  Panel Assembly  (drag to rotate)',
        fontsize=10, color=NOVA_BLUE, fontweight='bold', pad=12
    )

    # ── Panel schedule (right panel) ─────────────────────────────────────
    y_cur = 0.97
    line_h = 0.045

    def _write(text, y, bold=False, color=NOVA_BLUE, size=9):
        ax_info.text(0.02, y, text, transform=ax_info.transAxes,
                     fontsize=size, color=color,
                     fontweight='bold' if bold else 'normal', va='top')

    _write(f"Panel Schedule — {element.label}", y_cur, bold=True, size=10)
    y_cur -= line_h * 1.4

    etype = element.element_type.value
    _write(f"Type: {etype}  |  {L_mm:.0f} × {W_mm:.0f} mm  |  H = {H_mm:.0f} mm",
           y_cur, color='#555', size=8)
    y_cur -= line_h * 1.2

    _write(f"Panel height: {ph_mm:.0f} mm  |  Rows: {rows}  |  Sets: 1",
           y_cur, color='#555', size=8)
    y_cur -= line_h * 1.5

    # Separator line
    ax_info.plot([0.02, 0.98], [y_cur + line_h * 0.3] * 2,
                 color='#b0c4d8', linewidth=0.8, transform=ax_info.transAxes)
    y_cur -= line_h * 0.5

    if is_col:
        for face_label, combo, face_dim in [
            ('Face 1 & 3  (Length)', combo_L, L_mm),
            ('Face 2 & 4  (Width)',  combo_W, W_mm),
        ]:
            _write(face_label, y_cur, bold=True, color=NOVA_ACCENT, size=8.5)
            y_cur -= line_h

            total_w = sum(combo)
            for w in sorted(set(combo), reverse=True):
                cnt = combo.count(w)
                sq  = cnt * (w / 1000) * (ph_mm / 1000) * rows
                col = _pcol(w)
                # Color swatch
                ax_info.add_patch(mpatches.Rectangle(
                    (0.02, y_cur - 0.018), 0.04, 0.032,
                    transform=ax_info.transAxes,
                    facecolor=col, edgecolor='#555', linewidth=0.5,
                ))
                _write(f"     {w}×{ph_mm:.0f}mm  ×  {cnt} nos  ({sq:.3f} m²)",
                       y_cur, color='#222', size=8)
                y_cur -= line_h

            _write(f"  OC80×{ph_mm:.0f}mm  ×  2 nos  (corners)",
                   y_cur, color='#e67e22', size=8)
            ax_info.add_patch(mpatches.Rectangle(
                (0.02, y_cur - 0.018), 0.04, 0.032,
                transform=ax_info.transAxes,
                facecolor=OC_CLR, edgecolor='#555', linewidth=0.5,
            ))
            y_cur -= line_h * 1.4
    else:
        _write('Face 1 & 2  (Both wall faces)', y_cur, bold=True, color=NOVA_ACCENT, size=8.5)
        y_cur -= line_h
        for w in sorted(set(combo_L), reverse=True):
            cnt = combo_L.count(w)
            sq  = cnt * 2 * (w / 1000) * (ph_mm / 1000) * rows
            col = _pcol(w)
            ax_info.add_patch(mpatches.Rectangle(
                (0.02, y_cur - 0.018), 0.04, 0.032,
                transform=ax_info.transAxes,
                facecolor=col, edgecolor='#555', linewidth=0.5,
            ))
            _write(f"     {w}×{ph_mm:.0f}mm  ×  {cnt*2} nos  ({sq:.3f} m²)",
                   y_cur, color='#222', size=8)
            y_cur -= line_h
        y_cur -= line_h * 0.4

    # BOQ summary from actual boq object
    y_cur -= line_h * 0.2
    ax_info.plot([0.02, 0.98], [y_cur + line_h * 0.5] * 2,
                 color='#b0c4d8', linewidth=0.8, transform=ax_info.transAxes)
    y_cur -= line_h * 0.3

    _write('BOQ Summary', y_cur, bold=True, size=9)
    y_cur -= line_h
    for p in boq.panels:
        _write(f"  {p.size_label:22s}  {p.quantity:>4} nos  |  {p.total_area_sqm:.3f} m²",
               y_cur, color='#1a3a5c' if p.is_corner else '#222', size=7.5)
        y_cur -= line_h * 0.9

    y_cur -= line_h * 0.3
    _write(f"Total formwork area: {boq.total_panel_area_sqm:.3f} m²",
           y_cur, bold=True, color=NOVA_ACCENT, size=9)

    # Main title
    fig.suptitle(
        f'3D Panel Assembly  —  {element.label}  |  '
        f'{L_mm:.0f}×{W_mm:.0f}mm  |  H={H_mm:.0f}mm  |  Qty {element.quantity}',
        fontsize=11, fontweight='bold', color=NOVA_BLUE, y=0.99,
    )
    fig.text(
        0.5, 0.005,
        'Schematic — verify panel sizes with BOQ table before ordering.  '
        '|  Nova Formworks Pvt. Ltd.',
        ha='center', fontsize=6.5, color='#7f8c8d', style='italic',
    )

    return fig


def generate_project_layout(
    elements: list,
    boqs: list,
    panel_height_mm: float,
    output_path: str = None,
    acc_agg: dict = None,
) -> str:
    """
    Generate a multi-page layout PDF for all elements in the project.

    Each element gets one page. Returns path to saved PDF.
    """
    from matplotlib.backends.backend_pdf import PdfPages

    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix='.pdf', prefix='layout_project_')
        os.close(fd)

    with PdfPages(output_path) as pdf:
        for element, boq in zip(elements, boqs):
            is_col = element.is_column
            if is_col:
                fig = plt.figure(figsize=(14, 7), facecolor='white')
                ax_strip = fig.add_axes([0.02, 0.12, 0.62, 0.72])
                ax_plan  = fig.add_axes([0.68, 0.12, 0.28, 0.72])
            else:
                fig = plt.figure(figsize=(14, 7), facecolor='white')
                ax_elev = fig.add_axes([0.04, 0.15, 0.90, 0.68])

            h_achieved = int(math.ceil(element.height_mm / panel_height_mm)) * panel_height_mm
            etype_str = element.element_type.value.upper()
            fig.suptitle(
                f'{etype_str}  {element.label}   |   '
                f'{element.length_mm:.0f} × {element.width_mm:.0f} mm   |   '
                f'H = {element.height_mm:.0f} mm  →  {h_achieved:.0f} mm   |   '
                f'Qty = {element.quantity}',
                fontsize=10, fontweight='bold', color=NOVA_BLUE, y=0.97
            )
            fig.text(0.5, 0.01,
                     'Schematic only. Verify all dimensions on site.  '
                     '|  Nova Formworks Pvt. Ltd.',
                     ha='center', fontsize=6.5, color='#7f8c8d', style='italic')

            if is_col:
                _draw_column_layout(element, panel_height_mm, ax_strip, ax_plan)
            else:
                _draw_wall_layout(element, panel_height_mm, acc_agg, ax_elev)

            pdf.savefig(fig, bbox_inches='tight', facecolor='white')
            plt.close(fig)

    return output_path
