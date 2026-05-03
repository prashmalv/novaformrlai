"""
DXF Drawing Viewer — PyQt6 widget that renders AutoCAD drawings
with color-coded element overlays. Click any element to select/edit it.
"""
import math
from pathlib import Path

try:
    import matplotlib
    matplotlib.use('QtAgg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
    import matplotlib.patches as mpatches
    import matplotlib.patheffects as pe
    MPL_OK = True
except ImportError:
    MPL_OK = False

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from src.models.element import StructuralElement, ElementType

# ── Color palette per element type (edge, fill, alpha) ────────────────────────
_COLORS = {
    ElementType.COLUMN:      ('#1565C0', '#42A5F5', 0.30),
    ElementType.WALL:        ('#1B5E20', '#4CAF50', 0.28),
    ElementType.SHEAR_WALL:  ('#B71C1C', '#EF5350', 0.28),
    ElementType.BOX_CULVERT: ('#4A148C', '#AB47BC', 0.28),
    ElementType.DRAIN:       ('#E65100', '#FFA726', 0.28),
    ElementType.MONOLITHIC:  ('#37474F', '#90A4AE', 0.28),
    ElementType.SLAB:        ('#F57F17', '#FFEE58', 0.20),
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

_BG        = '#0d1117'
_GRID_CLR  = '#1a2030'
_LINE_CLR  = '#2a4a6a'
_LINE2_CLR = '#1a3050'


class DXFViewerWidget(QWidget):
    """
    Matplotlib-based DXF viewer embedded in PyQt6.

    Signals:
        element_selected(int)         — index of element clicked
        element_double_clicked(int)   — index for opening edit dialog
    """
    element_selected       = pyqtSignal(int)
    element_double_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._elements: list[StructuralElement] = []
        self._bboxes:   list[tuple]             = []   # raw DXF coords
        self._polylines: list[list]             = []   # background geometry
        self._scale:    float                   = 1.0
        self._selected: int                     = -1
        self._overlay_patches: list             = []
        self._overlay_texts:   list             = []
        self._loaded = False
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

        # ── Matplotlib canvas ──────────────────────────────────────────────
        self.fig    = Figure(figsize=(11, 9), facecolor=_BG, tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.ax     = self.fig.add_subplot(111)
        self._style_ax()

        # ── Navigation toolbar (zoom/pan) ──────────────────────────────────
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.setStyleSheet("""
            QToolBar {
                background: #1a3a5c; border: none; padding: 2px;
                spacing: 4px;
            }
            QToolButton {
                background: #2c5f8a; color: white; border-radius: 3px;
                padding: 3px 7px; font-size: 11px;
            }
            QToolButton:hover { background: #3a7ab0; }
            QToolButton:checked { background: #0d2040; }
        """)

        # ── Top toolbar: custom buttons ────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(6, 4, 6, 4)

        self._lbl_title = QLabel("Drawing Preview")
        self._lbl_title.setStyleSheet(
            "color:#7aabcc; font-size:11px; font-weight:bold; background:transparent;")
        top_bar.addWidget(self._lbl_title)
        top_bar.addStretch()

        btn_fit = QPushButton("⊡  Fit All")
        btn_fit.setStyleSheet(_btn_css())
        btn_fit.setFixedWidth(80)
        btn_fit.clicked.connect(self._fit_view)
        top_bar.addWidget(btn_fit)

        top_frame = QFrame()
        top_frame.setStyleSheet(f"background:{_BG};")
        top_frame.setLayout(top_bar)

        # ── Status bar ─────────────────────────────────────────────────────
        self._status = QLabel("Load a DXF/DWG file to see the drawing preview")
        self._status.setStyleSheet(
            f"background:#0d1a2a; color:#6a8aaa; font-size:10px; padding:4px 8px;")
        self._status.setFixedHeight(24)

        root.addWidget(top_frame)
        root.addWidget(self.toolbar)
        root.addWidget(self.canvas, stretch=1)
        root.addWidget(self._status)

        # ── Event connections ──────────────────────────────────────────────
        self.canvas.mpl_connect('button_press_event',   self._on_press)
        self.canvas.mpl_connect('scroll_event',         self._on_scroll)
        self._show_placeholder()

    def _style_ax(self):
        self.ax.set_facecolor(_BG)
        self.ax.set_aspect('equal', adjustable='datalim')
        self.ax.tick_params(colors='#3a5a7a', labelsize=6)
        for spine in self.ax.spines.values():
            spine.set_color('#1a3050')
        self.ax.grid(True, color=_GRID_CLR, linewidth=0.4, alpha=0.6)

    def _show_placeholder(self):
        self.ax.clear()
        self._style_ax()
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
    ):
        """
        Render the drawing.

        Args:
            elements:  detected StructuralElement objects
            bboxes:    (x_min, y_min, x_max, y_max) per element in raw DXF units
            polylines: list of point lists [(x,y),...] for background geometry
            scale:     mm per DXF unit
            title:     filename label for the toolbar
        """
        if not MPL_OK:
            return

        self._elements  = elements
        self._bboxes    = bboxes
        self._polylines = polylines
        self._scale     = scale
        self._selected  = -1
        self._loaded    = True

        if title:
            self._lbl_title.setText(f"Drawing: {Path(title).name}")

        self._render_full()

        n = len(elements)
        col = sum(1 for e in elements if e.element_type == ElementType.COLUMN)
        wal = sum(1 for e in elements if e.element_type in (ElementType.WALL, ElementType.SHEAR_WALL))
        self._status.setText(
            f"  {n} element(s) detected — {col} column(s), {wal} wall(s)   |   "
            f"Click any highlighted element to select it"
        )

    def select_element(self, idx: int):
        """Programmatically highlight an element (called from table selection)."""
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
        self._selected  = -1
        self._loaded    = False
        self._overlay_patches = []
        self._overlay_texts   = []
        self._show_placeholder()
        self._status.setText("Load a DXF/DWG file to see the drawing preview")

    # ── Rendering ─────────────────────────────────────────────────────────────
    def _render_full(self):
        """Full redraw: background + overlays + legend."""
        self.ax.clear()
        self._style_ax()
        self._overlay_patches = []
        self._overlay_texts   = []

        self._draw_background()
        self._draw_overlays()
        self._draw_legend()
        self._fit_view()
        self.canvas.draw_idle()

    def _draw_background(self):
        """Render all drawing polylines as dim lines."""
        for pts in self._polylines:
            if len(pts) < 2:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            # Close polyline if not already closed
            if math.hypot(pts[-1][0]-pts[0][0], pts[-1][1]-pts[0][1]) > 0.1:
                xs.append(pts[0][0])
                ys.append(pts[0][1])
            self.ax.plot(xs, ys, color=_LINE_CLR, linewidth=0.55,
                         alpha=0.7, solid_capstyle='round', zorder=1)

    def _draw_overlays(self):
        """Draw colored rectangles for every detected element."""
        for i, (elem, bbox) in enumerate(zip(self._elements, self._bboxes)):
            x0, y0, x1, y1 = bbox
            w, h = x1 - x0, y1 - y0

            ec, fc, alpha = _COLORS.get(elem.element_type, ('#888', '#aaa', 0.25))
            selected = (i == self._selected)

            rect = mpatches.FancyBboxPatch(
                (x0, y0), w, h,
                boxstyle="square,pad=0",
                facecolor=fc, edgecolor='white' if selected else ec,
                linewidth=2.5 if selected else 1.2,
                alpha=(alpha + 0.2) if selected else alpha,
                zorder=4, picker=5,
            )
            rect._nf_idx = i
            self.ax.add_patch(rect)
            self._overlay_patches.append(rect)

            # Label
            cx, cy = x0 + w / 2, y0 + h / 2
            dim_str = f"{elem.length_mm:.0f}×{elem.width_mm:.0f}"
            label_str = f"{elem.label}\n{dim_str}"

            txt = self.ax.text(
                cx, cy, label_str,
                ha='center', va='center',
                fontsize=6.5, fontweight='bold',
                color='white',
                bbox=dict(
                    boxstyle='round,pad=0.25',
                    facecolor=ec, alpha=0.88,
                    edgecolor='white' if selected else 'none',
                    linewidth=1,
                ),
                zorder=6,
            )
            txt._nf_idx = i
            self._overlay_texts.append(txt)

    def _draw_legend(self):
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
            self.ax.legend(
                handles=handles, loc='upper right',
                fontsize=7, framealpha=0.85,
                facecolor='#101825', edgecolor='#2a4a6a',
                labelcolor='white', handlelength=1.5,
            )

    def _redraw_overlays(self):
        """Update only overlay patches/texts without re-rendering background."""
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
        self._draw_overlays()
        self._draw_legend()
        self.canvas.draw_idle()

    # ── View helpers ──────────────────────────────────────────────────────────
    def _fit_view(self):
        if not self._bboxes and not self._polylines:
            return
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
        """Pan/zoom so the selected element is visible."""
        x0, y0, x1, y1 = self._bboxes[idx]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        # Get current view span
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

        x, y = event.xdata, event.ydata
        hit_idx = -1

        for i, bbox in enumerate(self._bboxes):
            x0, y0, x1, y1 = bbox
            # Add small tolerance
            tol = max((x1 - x0) * 0.05, (y1 - y0) * 0.05, 10)
            if (x0 - tol) <= x <= (x1 + tol) and (y0 - tol) <= y <= (y1 + tol):
                hit_idx = i
                break  # first match (smallest bounding box preferred)

        if hit_idx != self._selected:
            self._selected = hit_idx
            self._redraw_overlays()

        if hit_idx >= 0:
            self.element_selected.emit(hit_idx)
            elem = self._elements[hit_idx]
            ec, _, _ = _COLORS.get(elem.element_type, ('#888', '#aaa', 0.25))
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
def _btn_css(primary=False):
    bg = '#2c5f8a' if not primary else '#1a3a5c'
    return f"""
    QPushButton {{
        background:{bg}; color:white; border:none;
        border-radius:3px; padding:4px 10px;
        font-size:10px; font-weight:bold;
    }}
    QPushButton:hover {{ background:#3a7ab0; }}
    QPushButton:pressed {{ background:#0d2040; }}
    """
