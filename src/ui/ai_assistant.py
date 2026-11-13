"""
NovoForm AI Assistant — BOQ Q&A chat.

When AI is enabled in Admin Panel → AI Settings, questions go to a cloud
LLM together with the open project's BOQ (src/ai/assistant.py). The model
can also change the project (add / edit / delete elements, settings) and
start an export; a PDF or image drawing can be uploaded and read by the
vision model (src/ai/drawing_reader.py). The main window applies all of it
with its own BOQ logic (src/ui/ai_host.py) and a live preview is shown here. Otherwise,
for a project marked "AI off", or when the model can't be reached, the
offline keyword engine below (BOQQueryEngine) answers.  Corrections entered by the user are stored in a
local SQLite database and auto-applied on the next import of the same
drawing file.
"""
import re
import math
import sqlite3
import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QFrame, QScrollArea, QCheckBox,
    QSplitter, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QAbstractItemView
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QRect, QSize, QPoint
from PyQt6.QtWidgets import QLayout
from PyQt6.QtGui import QFont, QColor

from src.models.element import StructuralElement, ElementType, ProjectBOQ
from src.ai import settings as ai_settings
from src.ai.assistant import BOQChat, _inr, _log as _ai_log

# ── Persistence ────────────────────────────────────────────────────────────────
_DB_PATH = Path(__file__).parent.parent.parent / "data" / "ai_memory.db"


def _init_db():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS corrections (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            drawing     TEXT,
            label       TEXT,
            dim_key     TEXT,
            old_val     REAL,
            new_val     REAL,
            created_at  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            role       TEXT,
            message    TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_correction(drawing: str, label: str, dim_key: str,
                    old_val: float, new_val: float):
    _init_db()
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute(
        "INSERT INTO corrections (drawing, label, dim_key, old_val, new_val, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (drawing, label, dim_key, old_val, new_val,
         datetime.datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_corrections(drawing: str) -> list[dict]:
    _init_db()
    conn = sqlite3.connect(str(_DB_PATH))
    rows = conn.execute(
        "SELECT label, dim_key, old_val, new_val FROM corrections WHERE drawing=?",
        (drawing,)
    ).fetchall()
    conn.close()
    return [{"label": r[0], "dim_key": r[1], "old_val": r[2], "new_val": r[3]}
            for r in rows]


# ── Query Engine ───────────────────────────────────────────────────────────────

class BOQQueryEngine:
    """
    Rule-based natural language query engine over the current project BOQ.
    Handles a broad set of questions without any external AI service.
    """

    def __init__(self):
        self._elements: list[StructuralElement] = []
        self._boqs    = []
        self._agg:  dict = {}
        self._acc_agg: dict = {}
        self._project: ProjectBOQ = None

    def update(self, elements, boqs, agg, acc_agg, project):
        self._elements = elements or []
        self._boqs     = boqs     or []
        self._agg      = agg      or {}
        self._acc_agg  = acc_agg  or {}
        self._project  = project

    def answer(self, question: str) -> str:
        q = question.strip().lower()

        # ── Guard: no BOQ loaded ────────────────────────────────────────────
        if not self._elements:
            return (
                "No project data loaded yet. Please add elements and run "
                "optimization first, then I can answer questions about your BOQ."
            )

        # ── Routing: most specific first ───────────────────────────────────
        # A question naming an element mark ("C1 me kitne panels") is about
        # that element, not the whole project.
        labels = {e.label.upper() for e in self._elements}
        for tok in re.findall(r'[a-z]{1,4}-?\d+[a-z]?', q, re.I):
            if tok.upper() in labels:
                return self._ans_element_specific(tok.upper(), q)
        if self._is_about(q, ['help', 'kya poochu', 'what can', 'capabilities']):
            return self._ans_help()
        if self._is_about(q, ['cost', 'price', 'amount', 'grand total', 'rupee', '₹', 'gst', 'kharcha', 'rate']):
            return self._ans_cost(q)
        if self._is_about(q, ['waller', 'tierod', 'tie rod', 'tier rod', 'pin', 'wing nut', 'pvc', 'cone', 'accessor']):
            return self._ans_accessories(q)
        if self._is_about(q, ['largest', 'biggest', 'maximum', 'most panel', 'sabse bada', 'sabse bade']):
            return self._ans_largest_element(q)
        if self._is_about(q, ['warning', 'exceed', 'high wall', 'problem', 'issue']):
            return self._ans_warnings(q)
        if self._is_about(q, ['oc80', 'ic100', 'oc ', 'ic ', 'corner']) or q.strip() in ('oc', 'ic'):
            return self._ans_corner_panels(q)
        if re.search(r'\b(600|500|490|440|400|350|340|300|275|250|240|230|200|150|125|100)\b', q):
            return self._ans_specific_panel(q)
        if self._is_about(q, ['area', 'sqm', 'square', 'm²']):
            return self._ans_total_area(q)
        if self._is_about(q, ['how many sets', 'sets', 'set ']):
            return self._ans_sets(q)
        if self._is_about(q, ['how many', 'count', 'number of', 'panels', 'kitne']):
            return self._ans_panel_count(q)
        if self._is_about(q, ['summary', 'overview', 'report', 'saar', 'brief', 'total']):
            return self._ans_summary()
        if self._is_about(q, ['element', 'column', 'wall', 'shear', 'structure', 'list']):
            return self._ans_elements(q)

        # ── Element-specific questions (e.g., "C1 panels", "SW2 area") ────
        elem_match = re.search(r'\b([a-z]{1,3}\d+[a-z]?)\b', q, re.I)
        if elem_match:
            return self._ans_element_specific(elem_match.group(1).upper(), q)

        return self._ans_summary()

    # ── Individual answer methods ──────────────────────────────────────────

    def _ans_total_area(self, q: str) -> str:
        if not self._agg:
            return "BOQ has not been generated yet. Please run optimization first."
        area = self._agg.get('total_area_sqm', 0)
        n_sets = self._agg.get('num_sets', 1)
        return (
            f"**Total Formwork Area: {area:.3f} m²**\n"
            f"This covers {len(self._elements)} element label(s) "
            f"× {n_sets} set(s).\n\n"
            f"Breakdown by element type:\n"
            + self._type_area_breakdown()
        )

    def _ans_cost(self, q: str) -> str:
        if not self._agg:
            return "No BOQ data. Run optimization first."
        rate = self._agg.get('rate_per_sqm', 0)
        if rate == 0:
            area = self._agg.get('total_area_sqm', 0)
            return (
                f"Panel area is **{area:.3f} m²** but no rate has been entered.\n"
                f"Enter the Panel Rate (₹/sqm) in the Export tab, then recompute the BOQ."
            )
        agg = self._agg
        lines = [
            f"**Cost Breakdown:**",
            f"• Panel Area:      {agg['total_area_sqm']:.3f} m²",
            f"• Rate:            ₹{rate:,.0f}/m²",
            f"• Panel Cost:      ₹{agg['total_panel_cost']:,.2f}",
        ]
        if self._project and self._project.gst_enabled:
            lines.append(f"• GST (18%):       ₹{agg['gst_amount']:,.2f}")
        if agg.get('freight_amount', 0) > 0:
            lines.append(f"• Freight:         ₹{agg['freight_amount']:,.2f}")
        lines.append(f"\n**Grand Total:   ₹{agg['grand_total']:,.2f}**")
        return "\n".join(lines)

    def _ans_panel_count(self, q: str) -> str:
        if not self._agg or not self._agg.get('summary_panels'):
            return "No BOQ data. Run optimization first."
        summary = self._agg['summary_panels']

        # Check for specific size mention
        m = re.search(r'(\d{2,3})\s*[xX×]\s*(\d{3,4})', q)
        if m:
            target = f"{m.group(1)}X{m.group(2)}"
            for size, d in summary.items():
                if target in size.upper():
                    return (
                        f"**{size}:** {d['quantity']} panels\n"
                        f"Area per panel: {d['unit_area_sqm']:.4f} m²\n"
                        f"Total area: {d['area_sqm']:.3f} m²"
                    )
            return f"No panels of size {target} found in this project."

        total_qty = sum(d['quantity'] for d in summary.values())
        flat_qty  = sum(d['quantity'] for d in summary.values() if not d['is_corner'])
        oc_qty    = sum(d['quantity'] for d in summary.values() if d['is_corner'])
        lines = [
            f"**Total panels: {total_qty}**",
            f"• Flat panels:      {flat_qty}",
            f"• Corner (OC/IC):  {oc_qty}",
            f"\nTop 5 panel sizes:",
        ]
        top5 = sorted(summary.items(), key=lambda kv: -kv[1]['quantity'])[:5]
        for size, d in top5:
            lines.append(f"• {size:20s}  {d['quantity']:>4} nos  ({d['area_sqm']:.2f} m²)")
        return "\n".join(lines)

    def _ans_accessories(self, q: str) -> str:
        if not self._acc_agg:
            return "Accessories not calculated. Run optimization first."
        lines = ["**Accessories Summary:**\n"]
        for key, d in self._acc_agg.items():
            qty = int(d['quantity'])
            if d['total_length_m'] > 0:
                lines.append(f"• {key:35s}  {qty:>5} nos  ({d['total_length_m']:.1f} rm total)")
            else:
                lines.append(f"• {key:35s}  {qty:>5} nos")
        # High-wall warnings
        if hasattr(self, '_boqs'):
            hw = [b.element.label for b in self._boqs
                  if hasattr(b, 'warnings') and
                  any('4500' in w for w in b.warnings)]
            if hw:
                lines.append(f"\n⚠ High-wall elements (>4500mm): {', '.join(hw)}")
                lines.append("  Engineer review required for these elements.")
        return "\n".join(lines)

    def _ans_elements(self, q: str) -> str:
        lines = [f"**{len(self._elements)} structural elements in this project:**\n"]
        for e in self._elements:
            junc = f" ({e.junction_type.value})" if e.junction_type.value != "None" else ""
            floor = f" [{e.floor_label}]" if e.floor_label else ""
            lines.append(
                f"• {e.label:8s}  {e.element_type.value:12s}  "
                f"{e.length_mm:.0f}×{e.width_mm:.0f}mm  "
                f"H={e.height_mm:.0f}mm  Qty={e.quantity}{junc}{floor}"
            )
        return "\n".join(lines)

    def _ans_largest_element(self, q: str) -> str:
        if not self._boqs:
            return "No BOQ data available."
        largest = max(self._boqs, key=lambda b: b.total_panel_area_sqm)
        e = largest.element
        return (
            f"**Largest element by formwork area: {e.label}**\n"
            f"Type:   {e.element_type.value}\n"
            f"Dims:   {e.length_mm:.0f} × {e.width_mm:.0f} mm\n"
            f"Height: {e.height_mm:.0f} mm\n"
            f"Qty:    {e.quantity}\n"
            f"Area:   {largest.total_panel_area_sqm:.3f} m²\n"
            f"Panels: {sum(p.quantity for p in largest.panels)}"
        )

    def _ans_warnings(self, q: str) -> str:
        if not self._boqs:
            return "No BOQ data."
        warns = []
        for boq in self._boqs:
            for w in boq.warnings:
                warns.append(f"• {boq.element.label}: {w}")
        if not warns:
            return "✅ No warnings — all elements are within normal height limits."
        return "**BOQ Warnings:**\n" + "\n".join(warns)

    def _ans_summary(self) -> str:
        proj = self._project
        lines = []
        if proj:
            if proj.client_name:
                lines.append(f"**Project: {proj.project_name or 'Untitled'}**")
                lines.append(f"Client: {proj.client_name}")
            if proj.date:
                lines.append(f"Date: {proj.date}")
        lines.append(f"\nElements: {len(self._elements)}")

        type_counts = {}
        for e in self._elements:
            k = e.element_type.value
            type_counts[k] = type_counts.get(k, 0) + e.quantity
        for t, n in type_counts.items():
            lines.append(f"  • {t}: {n}")

        if self._agg:
            lines.append(f"\nTotal Panel Area: {self._agg.get('total_area_sqm', 0):.3f} m²")
            if self._agg.get('grand_total', 0) > 0:
                lines.append(f"Grand Total: ₹{self._agg['grand_total']:,.2f}")

        return "\n".join(lines) if lines else "Load a project and run optimization to get a summary."

    def _ans_sets(self, q: str) -> str:
        if not self._project:
            return "No project loaded."
        n = self._project.num_sets
        return (
            f"This project uses **{n} set(s)** of formwork.\n"
            f"All panel quantities in the BOQ are per-set figures. "
            f"Grand total accounts for all {n} set(s)."
        )

    def _ans_corner_panels(self, q: str) -> str:
        if not self._agg or not self._agg.get('summary_panels'):
            return "No BOQ data. Run optimization first."
        summary = self._agg['summary_panels']
        oc = {k: d for k, d in summary.items() if 'OC' in k}
        ic = {k: d for k, d in summary.items() if 'IC' in k}
        lines = ["**Corner Panel Summary:**\n"]
        if oc:
            lines.append("Outer Corner (OC80) panels:")
            for k, d in oc.items():
                lines.append(f"  • {k}: {d['quantity']} nos")
        if ic:
            lines.append("\nInner Corner (IC100) panels:")
            for k, d in ic.items():
                lines.append(f"  • {k}: {d['quantity']} nos")
        if not oc and not ic:
            lines.append("No corner panels found.")
        return "\n".join(lines)

    def _ans_specific_panel(self, q: str) -> str:
        if not self._agg or not self._agg.get('summary_panels'):
            return "No BOQ data."
        m = re.search(r'(\d{2,3})', q)
        if not m:
            return "Please specify the panel width (e.g., '600 panels', '500x3200')."
        width = m.group(1)
        summary = self._agg['summary_panels']
        matches = [(k, d) for k, d in summary.items() if k.startswith(width + 'X')]
        if not matches:
            return f"No panels of width {width}mm found in this project."
        lines = [f"**Panels with width {width}mm:**\n"]
        for k, d in matches:
            lines.append(f"• {k}: {d['quantity']} nos  ({d['area_sqm']:.3f} m²)")
        return "\n".join(lines)

    def _ans_element_specific(self, label: str, q: str) -> str:
        elem = next((e for e in self._elements if e.label.upper() == label), None)
        if not elem:
            return f"Element '{label}' not found in this project."
        boq = next((b for b in self._boqs if b.element.label == elem.label), None)
        if not boq:
            return f"BOQ not yet generated for {label}. Run optimization first."
        lines = [
            f"**{elem.label} — {elem.element_type.value}**",
            f"Dimensions:   {elem.length_mm:.0f} × {elem.width_mm:.0f} mm",
            f"Height:       {elem.height_mm:.0f} mm",
            f"Quantity:     {elem.quantity}",
            f"Panel area:   {boq.total_panel_area_sqm:.3f} m²",
            f"\nPanel breakdown:",
        ]
        for p in boq.panels:
            tag = " [corner]" if p.is_corner else ""
            lines.append(f"  • {p.size_label:20s} × {p.quantity}{tag}")
        if boq.warnings:
            lines.append("\n⚠ Warnings:")
            for w in boq.warnings:
                lines.append(f"  {w}")
        return "\n".join(lines)

    def _ans_help(self) -> str:
        return (
            "**I can answer questions like:**\n\n"
            "• 'What is the total formwork area?'\n"
            "• 'How many 600×3200 panels are needed?'\n"
            "• 'Show me the cost breakdown'\n"
            "• 'List all elements'\n"
            "• 'Which element needs the most panels?'\n"
            "• 'How many wallers are required?'\n"
            "• 'Tell me about C1'\n"
            "• 'Any height warnings?'\n"
            "• 'Give me a summary'\n\n"
            "I analyze the current BOQ data in real time — "
            "no internet connection required."
        )

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _is_about(self, q: str, keywords: list[str]) -> bool:
        return any(kw in q for kw in keywords)

    def _type_area_breakdown(self) -> str:
        if not self._boqs:
            return ""
        by_type: dict[str, float] = {}
        n_sets = (self._agg or {}).get('num_sets', 1) or 1
        for boq in self._boqs:
            k = boq.element.element_type.value
            area1 = sum(p.total_area_sqm for p in boq.panels if not getattr(p, 'is_filler', False))
            by_type[k] = by_type.get(k, 0.0) + area1 * boq.element.quantity * n_sets
        return "\n".join(f"  • {t}: {a:.3f} m²" for t, a in by_type.items())



# ── Chat Widget ────────────────────────────────────────────────────────────────

_NOVA_BLUE   = "#1a3a5c"
_NOVA_ACCENT = "#2c5f8a"
_NOVA_LIGHT  = "#dce8f5"
_BG          = "#f5f7fa"
_REVIEW_BG   = "#fff3cd"

_PLACEHOLDER = ("Ask or instruct in English / Hinglish…  e.g. 'C1 me kitne panels?' · "
                "'C3 ki qty 4 kar do' · 'Excel bana do'")
_DRAWING_FILTER = "Drawings (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp);;All Files (*)"


class _Worker(QThread):
    """Runs one blocking AI call off the UI thread: fn(progress_emit) -> result."""
    done = pyqtSignal(object, str)       # (result, error)
    progress = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn(self.progress.emit), "")
        except Exception as e:           # LLMError or anything unexpected
            self.done.emit(None, str(e))


class _FlowLayout(QLayout):
    """Lays widgets left to right and wraps to the next line (for chips)."""

    def __init__(self, parent=None, spacing=5):
        super().__init__(parent)
        self._items = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._place(QRect(0, 0, width, 0), dry=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._place(rect, dry=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        return size

    def _place(self, rect, dry):
        x, y, line_h, sp = rect.x(), rect.y(), 0, self.spacing()
        for it in self._items:
            hint = it.sizeHint()
            if x + hint.width() > rect.right() and line_h > 0:
                x, y, line_h = rect.x(), y + line_h + sp, 0
            if not dry:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + sp
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()


def _chip_css(kind: str) -> str:
    border, fg = ("#b0c4d8", _NOVA_BLUE) if kind == "ask" else ("#e0b252", "#7a4b00")
    return f"""
        QPushButton {{ background:white; color:{fg}; border:1px solid {border};
                       border-radius:10px; padding:3px 10px; font-size:10px; }}
        QPushButton:hover {{ background:{_NOVA_LIGHT}; }}
        QPushButton:disabled {{ color:#aaa; }}"""


class AIAssistantWidget(QWidget):
    """
    Chat panel (left) + live BOQ preview (right). `host` is the MainWindow
    (AIHostMixin); without it the panel only answers questions.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.host = None
        self._engine = BOQQueryEngine()
        self._chat = BOQChat()
        self._worker = None
        self._project_name = None
        self._elements, self._boqs, self._agg = [], [], None
        self._setup_ui()
        _init_db()
        self._rebuild_chips()
        self._refresh_badge()

    def update_data(self, elements, boqs, agg, acc_agg, project, acc_boqs=None):
        """Call this after every optimization run to refresh the data context."""
        self._engine.update(elements, boqs, agg, acc_agg, project)
        self._chat.update(elements, boqs, agg, acc_agg, project, acc_boqs)
        self._elements, self._boqs, self._agg = list(elements or []), list(boqs or []), agg
        self._project = project
        name = getattr(project, "project_name", "") if project else ""
        if name and name != self._project_name:
            # Another project: start a fresh conversation and let the user
            # decide again whether this one may go to the cloud.
            if self._project_name is not None:
                self._chat.reset()
                self.ai_off_chk.setChecked(False)
            self._project_name = name
        self._refresh_preview()
        self._rebuild_chips()

    # ── Mode ───────────────────────────────────────────────────────────────────
    def _online_settings(self):
        """Settings dict if this request may go to the AI model, else None."""
        if self.ai_off_chk.isChecked():
            return None
        s = ai_settings.load()
        if not s.get("enabled") or ai_settings.missing_credentials(s):
            return None
        return s

    def _refresh_badge(self):
        s = self._online_settings()
        if s:
            name = dict(ai_settings.CHAT_MODELS).get(s["chat_model"], s["chat_model"]).split(" — ")[0]
            self.badge.setText(f"ONLINE · {name}  ●")
            self.badge.setStyleSheet("color:#4ade80; font-size:9px; font-weight:bold; background:transparent;")
        else:
            self.badge.setText("OFFLINE  ●")
            self.badge.setStyleSheet("color:#cbd5e1; font-size:9px; font-weight:bold; background:transparent;")
        self.upload_btn.setToolTip(
            "Read columns / walls from a PDF or image drawing with AI" if s else
            "Needs AI: turn it on in Admin Panel → AI Settings (and untick 'AI off')")

    def showEvent(self, ev):
        super().showEvent(ev)
        self._refresh_badge()      # admin may have changed AI settings

    # ── UI ─────────────────────────────────────────────────────────────────────
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setStyleSheet(f"background:{_NOVA_BLUE}; border-radius:6px 6px 0 0;")
        hdr.setFixedHeight(42)
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(10, 0, 10, 0)
        ai_lbl = QLabel("🤖  AI Assistant")
        ai_lbl.setStyleSheet("color:white; font-size:13px; font-weight:bold; background:transparent;")
        hdr_lay.addWidget(ai_lbl)
        hdr_lay.addStretch()

        self.ai_off_chk = QCheckBox("AI off for this project (govt / confidential)")
        self.ai_off_chk.setToolTip(
            "Tick for government or confidential projects: questions are answered\n"
            "by the offline engine and no project data leaves this computer.")
        self.ai_off_chk.setStyleSheet("color:white; font-size:9px; background:transparent;")
        self.ai_off_chk.toggled.connect(lambda _: self._refresh_badge())
        hdr_lay.addWidget(self.ai_off_chk)
        hdr_lay.addSpacing(12)
        new_btn = QPushButton("New chat")
        new_btn.setToolTip("Forget the earlier messages in this conversation")
        new_btn.setStyleSheet("QPushButton { color:white; background:transparent; border:1px solid #6b8bb0;"
                              " border-radius:4px; padding:2px 8px; font-size:9px; }")
        new_btn.clicked.connect(self._new_chat)
        hdr_lay.addWidget(new_btn)
        hdr_lay.addSpacing(12)
        self.badge = QLabel()
        hdr_lay.addWidget(self.badge)
        root.addWidget(hdr)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._build_chat_side())
        split.addWidget(self._build_preview_side())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setChildrenCollapsible(False)
        root.addWidget(split, stretch=1)

        self._append_message(
            "bot",
            "Namaste! I work on the project open in NovoForm.\n"
            "• **Ask** anything about its BOQ — panels, area, cost, accessories, any element.\n"
            "• **Change** it by typing — e.g. 'C3 ki qty 4 kar do', 'SW2 delete karo', "
            "'C20 column 600x450 qty 2 add karo', 'sets 2 kar do'. The preview on the right "
            "updates, and **Undo** reverts the last AI change.\n"
            "• **Upload drawing** (PDF / image) to read columns and walls from it.\n"
            "• When it looks right, say **'Excel bana do'** or **'Quotation PDF generate karo'**.\n"
            "The buttons below show example questions. Please verify before sending to a client.")

    def _build_chat_side(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.chat_view = QTextEdit()
        self.chat_view.setReadOnly(True)
        self.chat_view.setStyleSheet(f"""
            QTextEdit {{ background:{_BG}; border:none; font-size:11px;
                         font-family: 'Helvetica Neue', Arial; padding: 8px; }}""")
        lay.addWidget(self.chat_view, stretch=1)

        # Example chips: blue = ask (sends), amber = change (fills the box)
        chips = QFrame()
        chips.setStyleSheet("background:#f0f4fa; border-top:1px solid #dde3f0;")
        cl = QVBoxLayout(chips)
        cl.setContentsMargins(6, 4, 6, 4)
        cl.setSpacing(3)
        self._ask_row, self._change_row = QHBoxLayout(), QHBoxLayout()
        for row, title in ((self._ask_row, "Poochiye:"), (self._change_row, "Badlaav / Export:")):
            row.setSpacing(5)
            t = QLabel(title)
            t.setStyleSheet(f"color:{_NOVA_BLUE}; font-size:9px; font-weight:bold; background:transparent;")
            t.setFixedWidth(88)
            t.setAlignment(Qt.AlignmentFlag.AlignTop)
            row.addWidget(t)
            holder = QWidget()
            holder.setStyleSheet("background:transparent;")
            _FlowLayout(holder)
            row.addWidget(holder, stretch=1)
            row.holder = holder
            cl.addLayout(row)
        lay.addWidget(chips)

        # Input row
        input_frame = QFrame()
        input_frame.setStyleSheet("background:#e8f0fa; border-top:1px solid #b0c4d8;")
        il = QHBoxLayout(input_frame)
        il.setContentsMargins(8, 6, 8, 6)
        il.setSpacing(6)
        self.upload_btn = QPushButton("📎 Upload drawing")
        self.upload_btn.setStyleSheet(f"""
            QPushButton {{ background:white; color:{_NOVA_BLUE}; border:1px solid #b0c4d8;
                           border-radius:4px; padding:7px 10px; font-size:11px; }}
            QPushButton:hover {{ background:{_NOVA_LIGHT}; }}""")
        self.upload_btn.clicked.connect(self._upload_drawing)
        il.addWidget(self.upload_btn)
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText(_PLACEHOLDER)
        self.input_box.setStyleSheet("""
            QLineEdit { border:1px solid #b0c4d8; border-radius:4px;
                        padding:7px 10px; background:white; font-size:11px; }""")
        self.input_box.returnPressed.connect(self._send)
        il.addWidget(self.input_box, stretch=1)
        self.ask_btn = QPushButton("Send")
        self.ask_btn.setStyleSheet(f"""
            QPushButton {{ background:{_NOVA_ACCENT}; color:white; border:none; border-radius:4px;
                           padding:7px 16px; font-weight:bold; font-size:11px; }}
            QPushButton:hover {{ background:#1a4a6e; }}""")
        self.ask_btn.setFixedWidth(75)
        self.ask_btn.clicked.connect(self._send)
        il.addWidget(self.ask_btn)
        lay.addWidget(input_frame)
        return w

    def _build_preview_side(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:white;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        t = QLabel("Live BOQ preview")
        t.setStyleSheet(f"color:{_NOVA_BLUE}; font-size:12px; font-weight:bold;")
        lay.addWidget(t)
        self.prev_totals = QLabel("No elements yet.")
        self.prev_totals.setWordWrap(True)
        self.prev_totals.setStyleSheet("font-size:10px; color:#333;")
        lay.addWidget(self.prev_totals)

        self.prev_table = QTableWidget(0, 6)
        self.prev_table.setHorizontalHeaderLabels(["Label", "Type", "Size (mm)", "Qty", "Area sqm", "Panels / elem"])
        self.prev_table.verticalHeader().setVisible(False)
        self.prev_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.prev_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.prev_table.setStyleSheet("font-size:10px;")
        hh = self.prev_table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.prev_table.cellDoubleClicked.connect(
            lambda r, c: self.input_box.setText(f"{self.prev_table.item(r, 0).text()} ") or self.input_box.setFocus())
        lay.addWidget(self.prev_table, stretch=1)
        hint = QLabel("Yellow rows need review. Double-click a row to talk about that element.")
        hint.setStyleSheet("font-size:9px; color:#777;")
        lay.addWidget(hint)

        btn_css = f"""
            QPushButton {{ background:white; color:{_NOVA_BLUE}; border:1px solid #b0c4d8;
                           border-radius:4px; padding:5px 8px; font-size:10px; }}
            QPushButton:hover {{ background:{_NOVA_LIGHT}; }}
            QPushButton:disabled {{ color:#aaa; }}"""
        r1, r2 = QHBoxLayout(), QHBoxLayout()
        self.undo_btn = QPushButton("↶ Undo last AI change")
        self.undo_btn.clicked.connect(self._undo)
        open_btn = QPushButton("Open full BOQ")
        open_btn.clicked.connect(lambda: self.host and self.host.tabs.setCurrentIndex(4))
        for b in (self.undo_btn, open_btn):
            b.setStyleSheet(btn_css)
            r1.addWidget(b)
        self._export_btns = []
        for text, kind in (("Excel", "excel"), ("BOQ PDF", "boq_pdf"), ("Quotation PDF", "quotation_pdf")):
            b = QPushButton(f"⬇ {text}")
            b.setStyleSheet(btn_css)
            b.clicked.connect(lambda _, k=kind: self._do_export(k))
            r2.addWidget(b)
            self._export_btns.append(b)
        lay.addLayout(r1)
        lay.addLayout(r2)
        return w

    # ── Chips ──────────────────────────────────────────────────────────────────
    def _rebuild_chips(self):
        cols = [e.label for e in self._elements if e.element_type == ElementType.COLUMN]
        walls = [e.label for e in self._elements if e.element_type != ElementType.COLUMN]
        c1 = cols[0] if cols else (walls[0] if walls else "C1")
        w1 = walls[0] if walls else (cols[-1] if cols else "SW1")
        asks = ["Total area kitna hai?", "Cost breakdown batao", f"{c1} me kitne panels lagenge?",
                "Sabse bada element kaun sa hai?", "Tie rods aur wallers kitne lagenge?",
                "OC aur IC kitne lagenge?", "Koi warning hai kya?"]
        changes = [(f"{c1} ki qty 4 kar do", False), (f"{w1} delete kar do", False),
                   ("C20 column 600x450 qty 2 add karo", False), ("Sets 2 kar do", False),
                   ("Panel rate 1450 per sqm lagao", False), ("Excel bana do", True),
                   ("Quotation PDF generate karo", True)]
        for row, items in ((self._ask_row, [(a, True) for a in asks]), (self._change_row, changes)):
            lay = row.holder.layout()
            while lay.count():
                it = lay.takeAt(0)
                if it.widget():
                    it.widget().deleteLater()
            for text, send in items:
                b = QPushButton(text)
                b.setStyleSheet(_chip_css("ask" if row is self._ask_row else "change"))
                b.setFixedHeight(24)
                if send:
                    b.clicked.connect(lambda _, t=text: self._ask_preset(t))
                else:
                    b.setToolTip("Puts this in the box - change the label / numbers, then press Enter")
                    b.clicked.connect(lambda _, t=text: (self.input_box.setText(t), self.input_box.setFocus()))
                lay.addWidget(b)

    # ── Preview ────────────────────────────────────────────────────────────────
    def _refresh_preview(self):
        els = self._elements
        boq_by_elem = {id(b.element): b for b in self._boqs if b is not None}
        n_sets = (self._agg or {}).get("num_sets", 1) or 1
        self.prev_table.setRowCount(len(els))
        for i, e in enumerate(els):
            b = boq_by_elem.get(id(e))
            area = sum(p.total_area_sqm for p in b.panels if not getattr(p, "is_filler", False)) if b else 0
            npan = sum(p.quantity for p in b.panels if not getattr(p, "is_filler", False)) if b else 0
            vals = [e.label, e.element_type.value, f"{e.length_mm:.0f}×{e.width_mm:.0f}", str(e.quantity),
                    f"{area * e.quantity * n_sets:.2f}" if b else "-", str(npan) if b else "-"]
            # Yellow only for what the AI was unsure of; BOQ notes such as
            # "spacer needed" are normal and go in the tooltip.
            review = "REVIEW" in (e.notes or "")
            tip = "\n".join(filter(None, [e.notes] + (list(b.warnings) if b else [])))
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if review:
                    it.setBackground(QColor(_REVIEW_BG))
                if tip:
                    it.setToolTip(tip)
                self.prev_table.setItem(i, j, it)
        if not els:
            self.prev_totals.setText("No elements yet - import a drawing, upload one here, or add elements by chat.")
        else:
            a = self._agg or {}
            txt = (f"<b>{len(els)}</b> labels · <b>{sum(e.quantity for e in els)}</b> elements · "
                   f"<b>{a.get('total_area_sqm', 0):,.2f} sqm</b> · sets {n_sets}")
            if a.get("grand_total"):
                txt += f" · grand total <b>{_inr(a['grand_total'])}</b>"
            n_rev = sum(1 for i in range(len(els)) if self.prev_table.item(i, 0).background().color().name() == _REVIEW_BG)
            if n_rev:
                txt += f"<br><span style='color:#a15c00'>⚠ {n_rev} row(s) need review</span>"
            self.prev_totals.setText(txt)
        has = bool(self._boqs)
        for b in self._export_btns:
            b.setEnabled(has and self.host is not None)
        self.undo_btn.setEnabled(bool(self.host and self.host.ai_can_undo()))

    # ── Actions ────────────────────────────────────────────────────────────────
    def _send(self):
        q = self.input_box.text().strip()
        if not q or self._worker is not None:
            return
        self.input_box.clear()
        self._append_message("user", q)
        self._respond(q)

    def _ask_preset(self, text: str):
        if self._worker is not None:
            return
        self._append_message("user", text)
        self._respond(text)

    def _new_chat(self):
        self._chat.reset()
        self.chat_view.clear()
        self._append_message("bot", "New conversation started.")

    def _undo(self):
        if self.host:
            msg = self.host.ai_undo()
            self._append_message("bot", msg)
            self._chat.note("user pressed Undo: the last change was reverted")
            self._refresh_preview()

    def _do_export(self, kind: str):
        if self.host:
            msg = self.host.ai_export(kind)
            if msg:
                self._append_message("bot", msg)

    def _respond(self, question: str):
        s = self._online_settings()
        self._refresh_badge()
        if s is None:
            QTimer.singleShot(200, lambda: self._append_message("bot", self._engine.answer(question)))
            return
        self._run(lambda emit: self._chat.ask(question, s),
                  lambda turn, err: self._on_answer(question, turn, err), "Thinking…")

    def _on_answer(self, question: str, turn, error: str):
        if error:
            # Never leave the user without an answer: fall back offline.
            self._append_message("bot", f"⚠ AI not available ({error}). Offline answer:\n\n"
                                        + self._engine.answer(question))
            return
        lines = []
        if self.host is not None:
            lines = self.host.ai_apply_turn(turn)
        elif turn.element_changes or turn.project_changes:
            lines = ["✗ changes can only be applied inside the main window"]
        self._append_message("bot", turn.reply + ("\n\n" + "\n".join(lines) if lines else ""))
        if lines:
            self._chat.note("; ".join(lines))
        if turn.export and self.host is not None:
            msg = self.host.ai_export(turn.export)
            self._chat.note(msg or f"{turn.export} export dialog opened")
            if msg:
                self._append_message("bot", msg)
        self._refresh_preview()

    def _upload_drawing(self):
        if self._worker is not None:
            return
        s = self._online_settings()
        if s is None:
            self._append_message("bot", "Reading a PDF / image drawing needs the AI model. Turn AI on in "
                                        "Admin Panel → AI Settings, and keep 'AI off for this project' unticked.")
            return
        if self.host is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Upload drawing (PDF / image)", "", _DRAWING_FILTER)
        if not path:
            return
        name = Path(path).name
        self._append_message("user", f"📎 {name}")
        from src.ai.drawing_reader import read_drawing
        self._run(lambda emit: read_drawing(path, s, progress=emit),
                  lambda res, err: self._on_drawing(name, s, res, err),
                  "Reading drawing… (about 1-2 min per page)")

    def _on_drawing(self, name, s, res, error):
        if error:
            self._append_message("bot", f"⚠ Could not read {name}: {error}")
            return
        lines = self.host.ai_import_drawing(res, name)
        self._append_message("bot", "\n".join(lines) + "\n\nCheck the preview; tell me what to change, "
                                    "then say 'Excel bana do' or 'Quotation PDF generate karo'.")
        self._chat.history += [{"role": "user", "content": f"[uploaded drawing {name}]"},
                               {"role": "assistant", "content": "\n".join(lines)}]
        _ai_log(s["chat_model"], f"[upload] {name}", "\n".join(lines), res.usage, self._project_name or "")
        self._refresh_preview()

    def _run(self, fn, on_done, busy_text: str):
        self._set_busy(True, busy_text)
        self._worker = _Worker(fn)
        self._worker.progress.connect(lambda m: self.input_box.setPlaceholderText(m))

        def finished(result, err):
            self._worker.wait()
            self._worker = None
            self._set_busy(False)
            on_done(result, err)
        self._worker.done.connect(finished)
        self._worker.start()

    def _set_busy(self, busy: bool, text: str = ""):
        for w in (self.input_box, self.ask_btn, self.upload_btn):
            w.setEnabled(not busy)
        for row in (self._ask_row, self._change_row):
            row.holder.setEnabled(not busy)
        self.ask_btn.setText("…" if busy else "Send")
        self.input_box.setPlaceholderText(text if busy else _PLACEHOLDER)
        if not busy:
            self.input_box.setFocus()

    def _append_message(self, role: str, text: str):
        if role == "user":
            html = (
                f'<div style="text-align:right;margin:6px 0;">'
                f'<span style="background:#003087;color:white;'
                f'border-radius:12px 12px 2px 12px;padding:7px 12px;'
                f'display:inline-block;max-width:80%;font-size:11px;">'
                f'{self._escape(text)}'
                f'</span></div>'
            )
        else:
            formatted = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', self._escape(text))
            formatted = formatted.replace('\n', '<br>')
            html = (
                f'<div style="text-align:left;margin:6px 0;">'
                f'<span style="background:#e8f0fe;color:#1a2340;'
                f'border-radius:12px 12px 12px 2px;padding:7px 12px;'
                f'display:inline-block;max-width:90%;font-size:11px;'
                f'border-left:3px solid #003087;">'
                f'<b style="color:#003087;font-size:10px;">🤖 AI</b><br>{formatted}'
                f'</span></div>'
            )
        self.chat_view.append(html)
        sb = self.chat_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _escape(self, text: str) -> str:
        return (text.replace('&', '&amp;')
                    .replace('<', '&lt;')
                    .replace('>', '&gt;'))
