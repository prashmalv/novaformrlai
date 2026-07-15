"""
3D Elements Overview Widget — shows all structural elements as interactive
3D boxes at their drawing positions (or grid if no DXF loaded).
Uses mpl_toolkits.mplot3d embedded in PyQt6 via FigureCanvasQTAgg.
"""
import math
from pathlib import Path

try:
    import matplotlib
    matplotlib.use('QtAgg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from src.ui.mpl_toolbar import NovoToolbar as NavigationToolbar2QT
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 — registers '3d' projection
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    import matplotlib.patches as mpatches
    MPL3D_OK = True
except ImportError:
    MPL3D_OK = False

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PyQt6.QtCore import Qt

from src.models.element import StructuralElement, ElementType

# ── Color palette (edge, face) ─────────────────────────────────────────────────
_COLORS = {
    ElementType.COLUMN:      ('#1565C0', '#5B9BD5'),
    ElementType.WALL:        ('#1B5E20', '#57A85A'),
    ElementType.SHEAR_WALL:  ('#B71C1C', '#E05555'),
    ElementType.BOX_CULVERT: ('#4A148C', '#9C4FC5'),
    ElementType.DRAIN:       ('#E65100', '#F4883A'),
    ElementType.MONOLITHIC:  ('#37474F', '#78909C'),
    ElementType.SLAB:        ('#F57F17', '#FFCA28'),
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

_BG = '#0d1117'


class Elements3DWidget(QWidget):
    """
    Interactive 3D overview of all structural elements.
    Elements shown as boxes at their real DXF coordinates (or a grid).
    Mouse-drag to rotate, scroll to zoom.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._elements: list[StructuralElement] = []
        self._bboxes:   list[tuple]             = []
        self._scale:    float                   = 1.0
        self._setup_ui()

    # ── UI ─────────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        if not MPL3D_OK:
            lbl = QLabel("matplotlib / mpl_toolkits not available.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            root.addWidget(lbl)
            return

        self.fig    = Figure(figsize=(10, 8), facecolor=_BG)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.ax     = self.fig.add_subplot(111, projection='3d')
        self._style_ax()

        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.toolbar.setStyleSheet("""
            QToolBar { background:#1a3a5c; border:none; padding:2px; spacing:4px; }
            QToolButton { background:#2c5f8a; color:white; border-radius:3px;
                          padding:3px 7px; font-size:11px; }
            QToolButton:hover   { background:#3a7ab0; }
            QToolButton:checked { background:#0d2040; }
        """)

        top = QHBoxLayout()
        top.setContentsMargins(8, 4, 8, 4)
        self._title = QLabel("3D Elements Overview")
        self._title.setStyleSheet(
            "color:#7aabcc; font-size:11px; font-weight:bold; background:transparent;")
        top.addWidget(self._title)
        top.addStretch()
        tip = QLabel("Drag to rotate  ·  Scroll to zoom")
        tip.setStyleSheet("color:#4a6a8a; font-size:10px; background:transparent;")
        top.addWidget(tip)

        top_frame = QFrame()
        top_frame.setStyleSheet(f"background:{_BG};")
        top_frame.setLayout(top)
        top_frame.setFixedHeight(34)

        self._status = QLabel("Run optimization or import a drawing to see the 3D view")
        self._status.setStyleSheet(
            f"background:#0d1a2a; color:#6a8aaa; font-size:10px; padding:4px 8px;")
        self._status.setFixedHeight(24)

        root.addWidget(top_frame)
        root.addWidget(self.toolbar)
        root.addWidget(self.canvas, stretch=1)
        root.addWidget(self._status)

        self._show_placeholder()

    def _style_ax(self):
        self.ax.set_facecolor(_BG)
        self.fig.set_facecolor(_BG)
        self.ax.tick_params(colors='#3a5a7a', labelsize=7)
        self.ax.xaxis.pane.fill = False
        self.ax.yaxis.pane.fill = False
        self.ax.zaxis.pane.fill = False
        self.ax.xaxis.pane.set_edgecolor('#1a3050')
        self.ax.yaxis.pane.set_edgecolor('#1a3050')
        self.ax.zaxis.pane.set_edgecolor('#1a3050')
        self.ax.grid(True, color='#1a3050', linewidth=0.4, alpha=0.5)

    def _show_placeholder(self):
        self.ax.clear()
        self._style_ax()
        self.ax.text2D(
            0.5, 0.5,
            'No elements loaded\n\n'
            'Import a DXF file or add elements manually,\n'
            'then run optimization to see the 3D view.',
            transform=self.ax.transAxes,
            ha='center', va='center', fontsize=10, color='#4a6a8a',
            bbox=dict(boxstyle='round,pad=0.8', facecolor='#121c2a',
                      edgecolor='#2a4a6a', linewidth=1.5),
        )
        self.canvas.draw_idle()

    # ── Public API ─────────────────────────────────────────────────────────────
    def load_elements(
        self,
        elements: list[StructuralElement],
        bboxes:   list[tuple] = None,
        scale:    float       = 1.0,
    ):
        """
        Render elements in 3D.
        bboxes: DXF bboxes (raw units) — used for real XY positioning.
        scale:  mm per DXF unit — converts bbox coords to mm.
        """
        self._elements = elements or []
        self._bboxes   = bboxes   or []
        self._scale    = scale
        self._render()

    # ── Rendering ─────────────────────────────────────────────────────────────
    def _render(self):
        if not MPL3D_OK:
            return
        self.ax.clear()
        self._style_ax()

        if not self._elements:
            self._show_placeholder()
            return

        positions = self._compute_positions()
        legend_handles = {}

        for elem, (cx, cy) in zip(self._elements, positions):
            L = elem.length_mm / 1000
            W = elem.width_mm  / 1000
            H = elem.height_mm / 1000

            ec, fc = _COLORS.get(elem.element_type, ('#888', '#aaa'))

            x0, y0 = cx - L / 2, cy - W / 2
            self._draw_box(x0, y0, 0, L, W, H, fc, ec)

            # Label above box
            self.ax.text(
                cx, cy, H + H * 0.06,
                f"{elem.label}",
                ha='center', va='bottom', fontsize=7, fontweight='bold',
                color='white', zorder=20,
            )
            # Dimension annotation on front face
            dim_text = f"{elem.length_mm:.0f}×{elem.width_mm:.0f}"
            self.ax.text(
                cx, y0, H / 2,
                dim_text,
                ha='center', va='center', fontsize=6,
                color='#c8dae8', zorder=20,
            )

            if elem.element_type not in legend_handles:
                legend_handles[elem.element_type] = mpatches.Patch(
                    facecolor=fc, edgecolor=ec,
                    label=_TYPE_LABELS.get(elem.element_type, elem.element_type.value),
                    linewidth=1,
                )

        # Axes labels
        self.ax.set_xlabel('X (m)', color='#4a6a8a', fontsize=8, labelpad=6)
        self.ax.set_ylabel('Y (m)', color='#4a6a8a', fontsize=8, labelpad=6)
        self.ax.set_zlabel('Height (m)', color='#4a6a8a', fontsize=8, labelpad=6)

        # Legend
        if legend_handles:
            self.ax.legend(
                handles=list(legend_handles.values()),
                loc='upper left', fontsize=7,
                framealpha=0.85, facecolor='#101825',
                edgecolor='#2a4a6a', labelcolor='white',
            )

        # Stats box
        n_col = sum(1 for e in self._elements if e.element_type == ElementType.COLUMN)
        n_wal = sum(1 for e in self._elements
                    if e.element_type in (ElementType.WALL, ElementType.SHEAR_WALL))
        self._status.setText(
            f"  {len(self._elements)} element(s)  —  "
            f"Columns: {n_col}   Walls/SW: {n_wal}  |  "
            f"Drag to rotate  ·  Scroll to zoom"
        )

        # Nice viewing angle
        self.ax.view_init(elev=28, azim=225)
        self.canvas.draw_idle()

    def _draw_box(self, x, y, z, dx, dy, dz, fc, ec):
        """Draw a solid 3D box using Poly3DCollection."""
        faces = [
            # bottom
            [(x,y,z),(x+dx,y,z),(x+dx,y+dy,z),(x,y+dy,z)],
            # top
            [(x,y,z+dz),(x+dx,y,z+dz),(x+dx,y+dy,z+dz),(x,y+dy,z+dz)],
            # front (y=y)
            [(x,y,z),(x+dx,y,z),(x+dx,y,z+dz),(x,y,z+dz)],
            # back (y=y+dy)
            [(x,y+dy,z),(x+dx,y+dy,z),(x+dx,y+dy,z+dz),(x,y+dy,z+dz)],
            # left (x=x)
            [(x,y,z),(x,y+dy,z),(x,y+dy,z+dz),(x,y,z+dz)],
            # right (x=x+dx)
            [(x+dx,y,z),(x+dx,y+dy,z),(x+dx,y+dy,z+dz),(x+dx,y,z+dz)],
        ]
        poly = Poly3DCollection(faces, zsort='min')
        poly.set_facecolor(fc)
        poly.set_edgecolor(ec)
        poly.set_linewidth(0.6)
        poly.set_alpha(0.72)
        self.ax.add_collection3d(poly)

    def _compute_positions(self) -> list[tuple]:
        """Return (cx, cy) in metres for each element."""
        if self._bboxes and len(self._bboxes) == len(self._elements):
            # Use actual DXF coordinates → convert to mm → then metres
            scale_to_mm = self._scale         # DXF unit → mm
            scale_to_m  = scale_to_mm / 1000  # mm → m
            return [
                (
                    (b[0] + b[2]) / 2 * scale_to_m,
                    (b[1] + b[3]) / 2 * scale_to_m,
                )
                for b in self._bboxes
            ]

        # Grid layout (no DXF positions)
        n    = len(self._elements)
        cols = max(1, math.ceil(math.sqrt(n)))
        # Spacing: max element size + 1m gap
        max_dim = max(
            max(e.length_mm, e.width_mm) / 1000
            for e in self._elements
        ) + 1.0

        positions = []
        for i, elem in enumerate(self._elements):
            col = i % cols
            row = i // cols
            cx  = col * max_dim
            cy  = row * max_dim
            positions.append((cx, cy))
        return positions
