"""
DXF Drawing Viewer — PyQt6 widget that renders AutoCAD drawings
using ezdxf's full drawing engine, then overlays color-coded element boxes.
"""
import math
from pathlib import Path

try:
    import matplotlib
    matplotlib.use('QtAgg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
    import matplotlib.patches as mpatches
    MPL_OK = True
except ImportError:
    MPL_OK = False

# ezdxf full drawing renderer (renders like AutoCAD)
try:
    import ezdxf
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    EZDXF_DRAW_OK = True
except ImportError:
    EZDXF_DRAW_OK = False

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from src.models.element import StructuralElement, ElementType

# ── Color palette per element type (edge, fill, alpha) ────────────────────────
_COLORS = {
    ElementType.COLUMN:      ('#1565C0', '#42A5F5', 0.22),
    ElementType.WALL:        ('#1B5E20', '#4CAF50', 0.20),
    ElementType.SHEAR_WALL:  ('#B71C1C', '#EF5350', 0.20),
    ElementType.BOX_CULVERT: ('#4A148C', '#AB47BC', 0.20),
    ElementType.DRAIN:       ('#E65100', '#FFA726', 0.20),
    ElementType.MONOLITHIC:  ('#37474F', '#90A4AE', 0.20),
    ElementType.SLAB:        ('#F57F17', '#FFEE58', 0.15),
}

_TYPE_LABELS = {
    ElementType.COLUMN:      'Column',
    ElementType.WALL:        'Wall',
    ElementType.SHEAR_WALL:  'Shear Wall',
    ElementType.BOX_CULVERT: 'Box Culvert',
    ElementType.DRAIN:       'Drain',
    ElementType.MONOLITHIC:  'Monolithic',
    ElementType.SLAB:        'Slab',
}

# Background colors for fallback (polyline) mode
_BG        = '#0d1117'
_GRID_CLR  = '#1a2030'
_LINE_CLR  = '#2a4a6a'


class DXFViewerWidget(QWidget):
    """
    Matplotlib-based DXF viewer embedded in PyQt6.

    Two rendering modes:
      1. Full ezdxf renderer — uses AutoCAD's exact drawing data: layers,
         colors, text, dimensions, hatches. Activated when dxf_path is passed.
      2. Polyline fallback — simple geometry outlines from the polyline list.

    Signals:
        element_selected(int)         — index of element clicked
        element_double_clicked(int)   — index for opening edit dialog
    """
    element_selected       = pyqtSignal(int)
    element_double_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._elements:   list[StructuralElement] = []
        self._bboxes:     list[tuple]             = []   # raw DXF coords
        self._polylines:  list[list]              = []   # fallback geometry
        self._scale:      float                   = 1.0
        self._dxf_path:   str                     = ""   # for full renderer
        self._selected:   int                     = -1
        self._overlay_patches: list               = []
        self._overlay_texts:   list               = []
        self._loaded:     bool                    = False
        self._full_render_done: bool              = False
        self._setup_ui()

    # ── UI Setup ───────────────────────────────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        if not MPL_OK:
            err = QLabel("matplotlib not installed. Run: pip install matplotlib")
            err.setAlignment(Qt.AlignmentFlag.AlignCenter)
            root.addWidget(err)
            return

        self.fig    = Figure(figsize=(11, 9), facecolor='white', tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.ax     = self.fig.add_subplot(111)
        self._style_ax_fallback()

        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.setStyleSheet("""
            QToolBar {
                background: #1a3a5c; border: none; padding: 2px; spacing: 4px;
            }
            QToolButton {
                background: #2c5f8a; color: white; border-radius: 3px;
                padding: 3px 7px; font-size: 11px;
            }
            QToolButton:hover  { background: #3a7ab0; }
            QToolButton:checked { background: #0d2040; }
        """)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(6, 4, 6, 4)

        self._lbl_title = QLabel("Drawing Preview")
        self._lbl_title.setStyleSheet(
            "color:#1a3a5c; font-size:11px; font-weight:bold; background:transparent;")
        top_bar.addWidget(self._lbl_title)
        top_bar.addStretch()

        self._render_mode_lbl = QLabel("")
        self._render_mode_lbl.setStyleSheet(
            "color:#2c5f8a; font-size:9px; background:transparent; margin-right:8px;")
        top_bar.addWidget(self._render_mode_lbl)

        btn_fit = QPushButton("⊡  Fit All")
        btn_fit.setStyleSheet(_btn_css())
        btn_fit.setFixedWidth(80)
        btn_fit.clicked.connect(self._fit_view)
        top_bar.addWidget(btn_fit)

        top_frame = QFrame()
        top_frame.setStyleSheet("background:#e8f0fa; border-bottom:1px solid #b0c4d8;")
        top_frame.setLayout(top_bar)
        top_frame.setFixedHeight(36)

        self._status = QLabel("Load a DXF/DWG file to see the drawing preview")
        self._status.setStyleSheet(
            "background:#dce8f5; color:#1a3a5c; font-size:10px; padding:4px 8px;")
        self._status.setFixedHeight(24)

        root.addWidget(top_frame)
        root.addWidget(self.toolbar)
        root.addWidget(self.canvas, stretch=1)
        root.addWidget(self._status)

        self.canvas.mpl_connect('button_press_event', self._on_press)
        self.canvas.mpl_connect('scroll_event',       self._on_scroll)
        self._show_placeholder()

    def _style_ax_fallback(self):
        """Dark style used in polyline-fallback mode."""
        self.ax.set_facecolor(_BG)
        self.fig.set_facecolor(_BG)
        self.ax.set_aspect('equal', adjustable='datalim')
        self.ax.tick_params(colors='#3a5a7a', labelsize=6)
        for spine in self.ax.spines.values():
            spine.set_color('#1a3050')
        self.ax.grid(True, color=_GRID_CLR, linewidth=0.4, alpha=0.6)

    def _style_ax_cad(self):
        """Light style used when ezdxf full renderer is active."""
        self.ax.set_facecolor('#f8f9fa')
        self.fig.set_facecolor('white')
        self.ax.set_aspect('equal', adjustable='datalim')
        self.ax.tick_params(colors='#555', labelsize=7)
        for spine in self.ax.spines.values():
            spine.set_color('#cccccc')
        self.ax.grid(False)

    def _show_placeholder(self):
        self.ax.clear()
        self._style_ax_fallback()
        self.ax.text(
            0.5, 0.5,
            'No drawing loaded\n\n'
            'Import a DXF or DWG file to see\nthe drawing preview here.\n\n'
            'Detected elements will be highlighted\n'
            'with colour-coded overlays.\n\n'
            'Click any element to select & edit it.',
            transform=self.ax.transAxes,
            ha='center', va='center', fontsize=11, color='#4a6a8a',
            bbox=dict(boxstyle='round,pad=1', facecolor='#121c2a',
                      edgecolor='#2a4a6a', linewidth=1.5),
            linespacing=1.8,
        )
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.canvas.draw_idle()

    # ── Public API ─────────────────────────────────────────────────────────────
    def load_drawing(
        self,
        elements:  list[StructuralElement],
        bboxes:    list[tuple],
        polylines: list[list],
        scale:     float = 1.0,
        title:     str   = "",
        dxf_path:  str   = "",
    ):
        """
        Render the drawing.

        Args:
            elements:  detected StructuralElement objects
            bboxes:    (x_min, y_min, x_max, y_max) per element in raw DXF units
            polylines: list of point lists [(x,y),...] for fallback rendering
            scale:     mm per DXF unit
            title:     filename label for the toolbar
            dxf_path:  if given, uses ezdxf full renderer (AutoCAD-quality)
        """
        if not MPL_OK:
            return

        self._elements   = elements
        self._bboxes     = bboxes
        self._polylines  = polylines
        self._scale      = scale
        self._dxf_path   = dxf_path
        self._selected   = -1
        self._loaded     = True
        self._full_render_done = False

        if title:
            self._lbl_title.setText(f"Drawing: {Path(title).name}")

        self._render_full()

        n   = len(elements)
        col = sum(1 for e in elements if e.element_type == ElementType.COLUMN)
        wal = sum(1 for e in elements
                  if e.element_type in (ElementType.WALL, ElementType.SHEAR_WALL))
        self._status.setText(
            f"  {n} element(s) — {col} column(s), {wal} wall(s)   |   "
            f"Click any highlighted element to select it"
        )

    def select_element(self, idx: int):
        if not self._loaded:
            return
        self._selected = idx
        self._redraw_overlays()
        if 0 <= idx < len(self._bboxes):
            self._zoom_to_element(idx)

    def clear(self):
        self._elements  = []
        self._bboxes    = []
        self._polylines = []
        self._dxf_path  = ""
        self._selected  = -1
        self._loaded    = False
        self._full_render_done = False
        self._overlay_patches  = []
        self._overlay_texts    = []
        self._show_placeholder()
        self._status.setText("Load a DXF/DWG file to see the drawing preview")

    # ── Rendering ─────────────────────────────────────────────────────────────
    def _render_full(self):
        self.ax.clear()
        self._overlay_patches = []
        self._overlay_texts   = []

        used_full = self._draw_background()
        self._draw_overlays(light_bg=used_full)
        self._draw_legend(light_bg=used_full)
        self._fit_view()
        self.canvas.draw_idle()

    def _draw_background(self) -> bool:
        """
        Render drawing background.
        Returns True if ezdxf full renderer was used, False for polyline fallback.
        """
        if self._dxf_path and EZDXF_DRAW_OK:
            try:
                doc = ezdxf.readfile(self._dxf_path)
                self._style_ax_cad()
                ctx = RenderContext(doc)
                out = MatplotlibBackend(self.ax)
                Frontend(ctx, out).draw_layout(
                    doc.modelspace(), finalize=True
                )
                self._full_render_done = True
                self._render_mode_lbl.setText("● AutoCAD renderer")
                return True
            except Exception:
                pass

        # Fallback: render polylines manually
        self._style_ax_fallback()
        for pts in self._polylines:
            if len(pts) < 2:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if math.hypot(pts[-1][0]-pts[0][0], pts[-1][1]-pts[0][1]) > 0.1:
                xs.append(pts[0][0])
                ys.append(pts[0][1])
            self.ax.plot(xs, ys, color=_LINE_CLR, linewidth=0.55,
                         alpha=0.7, solid_capstyle='round', zorder=1)
        self._render_mode_lbl.setText("● Outline mode")
        return False

    def _draw_overlays(self, light_bg: bool = False):
        """Draw colored rectangles for every detected element."""
        for i, (elem, bbox) in enumerate(zip(self._elements, self._bboxes)):
            x0, y0, x1, y1 = bbox
            w, h = x1 - x0, y1 - y0

            ec, fc, alpha = _COLORS.get(elem.element_type, ('#888', '#aaa', 0.20))
            selected = (i == self._selected)

            # On light bg, use higher alpha so overlays are clearly visible
            eff_alpha = (alpha + 0.25) if selected else (alpha + 0.10 if light_bg else alpha)

            rect = mpatches.FancyBboxPatch(
                (x0, y0), w, h,
                boxstyle="square,pad=0",
                facecolor=fc, edgecolor=ec if not selected else 'red',
                linewidth=3.0 if selected else (1.8 if light_bg else 1.2),
                alpha=eff_alpha,
                zorder=10, picker=5,
            )
            rect._nf_idx = i
            self.ax.add_patch(rect)
            self._overlay_patches.append(rect)

            # Label
            cx, cy = x0 + w / 2, y0 + h / 2
            label_str = f"{elem.label}\n{elem.length_mm:.0f}×{elem.width_mm:.0f}"

            txt = self.ax.text(
                cx, cy, label_str,
                ha='center', va='center',
                fontsize=6.5, fontweight='bold',
                color='white' if not light_bg else '#0d1117',
                bbox=dict(
                    boxstyle='round,pad=0.25',
                    facecolor=ec, alpha=0.92,
                    edgecolor='red' if selected else ('white' if not light_bg else ec),
                    linewidth=1,
                ),
                zorder=12,
            )
            txt._nf_idx = i
            self._overlay_texts.append(txt)

    def _draw_legend(self, light_bg: bool = False):
        present = {e.element_type for e in self._elements}
        handles = [
            mpatches.Patch(
                facecolor=_COLORS[t][1],
                edgecolor=_COLORS[t][0],
                label=_TYPE_LABELS.get(t, t.value),
                linewidth=1.2,
            )
            for t in list(ElementType)
            if t in present and t in _COLORS
        ]
        if handles:
            fc = '#ffffff' if light_bg else '#101825'
            ec = '#cccccc' if light_bg else '#2a4a6a'
            lc = '#222222' if light_bg else 'white'
            self.ax.legend(
                handles=handles, loc='upper right',
                fontsize=7, framealpha=0.90,
                facecolor=fc, edgecolor=ec,
                labelcolor=lc, handlelength=1.5,
            )

    def _redraw_overlays(self):
        for p in self._overlay_patches:
            try:
                p.remove()
            except Exception:
                pass
        for t in self._overlay_texts:
            try:
                t.remove()
            except Exception:
                pass
        self._overlay_patches = []
        self._overlay_texts   = []
        self._draw_overlays(light_bg=self._full_render_done)
        self._draw_legend(light_bg=self._full_render_done)
        self.canvas.draw_idle()

    # ── View helpers ──────────────────────────────────────────────────────────
    def _fit_view(self):
        all_x, all_y = [], []
        for bbox in self._bboxes:
            all_x += [bbox[0], bbox[2]]
            all_y += [bbox[1], bbox[3]]
        for pts in self._polylines:
            all_x += [p[0] for p in pts]
            all_y += [p[1] for p in pts]
        if not all_x:
            return
        dx = max(all_x) - min(all_x)
        dy = max(all_y) - min(all_y)
        pad = max(dx, dy) * 0.08 + 200
        self.ax.set_xlim(min(all_x) - pad, max(all_x) + pad)
        self.ax.set_ylim(min(all_y) - pad, max(all_y) + pad)
        self.canvas.draw_idle()

    def _zoom_to_element(self, idx: int):
        x0, y0, x1, y1 = self._bboxes[idx]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        xl = self.ax.get_xlim()
        yl = self.ax.get_ylim()
        xspan = (xl[1] - xl[0]) / 2
        yspan = (yl[1] - yl[0]) / 2
        self.ax.set_xlim(cx - xspan, cx + xspan)
        self.ax.set_ylim(cy - yspan, cy + yspan)
        self.canvas.draw_idle()

    # ── Mouse events ──────────────────────────────────────────────────────────
    def _on_press(self, event):
        if event.inaxes != self.ax or event.xdata is None:
            return
        if event.button != 1:
            return

        x, y   = event.xdata, event.ydata
        hit_idx = -1

        for i, bbox in enumerate(self._bboxes):
            x0, y0, x1, y1 = bbox
            tol = max((x1 - x0) * 0.05, (y1 - y0) * 0.05, 10)
            if (x0 - tol) <= x <= (x1 + tol) and (y0 - tol) <= y <= (y1 + tol):
                hit_idx = i
                break

        if hit_idx != self._selected:
            self._selected = hit_idx
            self._redraw_overlays()

        if hit_idx >= 0:
            self.element_selected.emit(hit_idx)
            elem = self._elements[hit_idx]
            self._status.setText(
                f"  Selected: {elem.label} | {elem.element_type.value} | "
                f"{elem.length_mm:.0f}×{elem.width_mm:.0f} mm | "
                f"H={elem.height_mm:.0f} mm | Qty {elem.quantity}  "
                f"  (double-click to edit)"
            )
            if event.dblclick:
                self.element_double_clicked.emit(hit_idx)
        else:
            self._status.setText(
                f"  {len(self._elements)} element(s) detected  |  "
                f"Click any highlighted element to select it"
            )

    def _on_scroll(self, event):
        if event.inaxes != self.ax:
            return
        factor = 0.85 if event.button == 'up' else 1.15
        xl = self.ax.get_xlim()
        yl = self.ax.get_ylim()
        xc = event.xdata or (xl[0] + xl[1]) / 2
        yc = event.ydata or (yl[0] + yl[1]) / 2
        self.ax.set_xlim(xc - (xc - xl[0]) * factor, xc + (xl[1] - xc) * factor)
        self.ax.set_ylim(yc - (yc - yl[0]) * factor, yc + (yl[1] - yc) * factor)
        self.canvas.draw_idle()


# ── helpers ────────────────────────────────────────────────────────────────────
def _btn_css():
    return """
    QPushButton {
        background:#2c5f8a; color:white; border:none;
        border-radius:3px; padding:4px 10px;
        font-size:10px; font-weight:bold;
    }
    QPushButton:hover   { background:#3a7ab0; }
    QPushButton:pressed { background:#0d2040; }
    """
