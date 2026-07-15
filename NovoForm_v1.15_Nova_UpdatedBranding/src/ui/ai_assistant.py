"""
NovoForm AI Assistant — offline rule-based BOQ Q&A engine.

Understands natural language questions about the current project BOQ
and provides intelligent answers from the live data.  No internet
connection required.  Corrections entered by the user are stored in a
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
    QPushButton, QTextEdit, QFrame, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from src.models.element import StructuralElement, ElementType, ProjectBOQ

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

        # ── Routing ────────────────────────────────────────────────────────
        if self._is_about(q, ['total', 'area', 'sqm', 'square']):
            return self._ans_total_area(q)
        if self._is_about(q, ['cost', 'price', 'amount', 'total cost', 'grand total', 'rupee', '₹']):
            return self._ans_cost(q)
        if self._is_about(q, ['how many', 'count', 'number of', 'total panels', 'kitne']):
            return self._ans_panel_count(q)
        if self._is_about(q, ['waller', 'tierod', 'tier rod', 'pin', 'wing nut', 'pvc cone', 'accessories']):
            return self._ans_accessories(q)
        if self._is_about(q, ['element', 'column', 'wall', 'shear', 'structure', 'list']):
            return self._ans_elements(q)
        if self._is_about(q, ['height', 'warning', 'high', 'exceed']):
            return self._ans_warnings(q)
        if self._is_about(q, ['largest', 'biggest', 'maximum', 'most panel', 'sabse bada']):
            return self._ans_largest_element(q)
        if self._is_about(q, ['summary', 'overview', 'report', 'saar', 'brief']):
            return self._ans_summary()
        if self._is_about(q, ['set', 'sets', 'how many sets']):
            return self._ans_sets(q)
        if self._is_about(q, ['oc', 'ic', 'corner', 'outer corner', 'inner corner']):
            return self._ans_corner_panels(q)
        if self._is_about(q, ['600', '500', '490', '440', '400', '300', '250']):
            return self._ans_specific_panel(q)
        if self._is_about(q, ['help', 'kya poochu', 'what can', 'capabilities']):
            return self._ans_help()

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
            f"This covers {len(self._elements)} structural element(s) "
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
                f"Go to Configuration tab → enter Panel Rate (₹/sqm) → re-run optimization."
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
        for boq in self._boqs:
            k = boq.element.element_type.value
            by_type[k] = by_type.get(k, 0.0) + boq.total_panel_area_sqm
        return "\n".join(f"  • {t}: {a:.3f} m²" for t, a in by_type.items())


# ── Chat Widget ────────────────────────────────────────────────────────────────

_NOVA_BLUE   = "#1a3a5c"
_NOVA_ACCENT = "#2c5f8a"
_NOVA_LIGHT  = "#dce8f5"
_BG          = "#f5f7fa"


class AIAssistantWidget(QWidget):
    """
    Chat-style AI assistant panel that answers BOQ questions.
    Embedded as a dockable widget in the main window.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine = BOQQueryEngine()
        self._setup_ui()
        _init_db()

    def update_data(self, elements, boqs, agg, acc_agg, project):
        """Call this after every optimization run to refresh the data context."""
        self._engine.update(elements, boqs, agg, acc_agg, project)

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

        badge = QLabel("OFFLINE  ●")
        badge.setStyleSheet("color:#4ade80; font-size:9px; font-weight:bold; background:transparent;")
        hdr_lay.addWidget(badge)

        root.addWidget(hdr)

        # Chat history
        self.chat_view = QTextEdit()
        self.chat_view.setReadOnly(True)
        self.chat_view.setStyleSheet(f"""
            QTextEdit {{
                background:{_BG}; border:none;
                font-size:11px; font-family: 'Helvetica Neue', Arial;
                padding: 8px;
            }}
        """)
        root.addWidget(self.chat_view, stretch=1)

        # Input row
        input_frame = QFrame()
        input_frame.setStyleSheet(f"background:#e8f0fa; border-top:1px solid #b0c4d8;")
        input_lay = QHBoxLayout(input_frame)
        input_lay.setContentsMargins(8, 6, 8, 6)
        input_lay.setSpacing(6)

        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText(
            "Ask anything about the BOQ...  e.g. 'total area', 'C1 panels', 'cost estimate'")
        self.input_box.setStyleSheet(f"""
            QLineEdit {{
                border:1px solid #b0c4d8; border-radius:4px;
                padding:7px 10px; background:white; font-size:11px;
            }}
        """)
        self.input_box.returnPressed.connect(self._send)
        input_lay.addWidget(self.input_box)

        ask_btn = QPushButton("Ask AI")
        ask_btn.setStyleSheet(f"""
            QPushButton {{
                background:{_NOVA_ACCENT}; color:white; border:none;
                border-radius:4px; padding:7px 16px; font-weight:bold;
                font-size:11px;
            }}
            QPushButton:hover {{ background:#1a4a6e; }}
        """)
        ask_btn.setFixedWidth(75)
        ask_btn.clicked.connect(self._send)
        input_lay.addWidget(ask_btn)

        root.addWidget(input_frame)

        # Suggestion chips
        chips_frame = QFrame()
        chips_frame.setStyleSheet("background:#f0f4fa; border-top:1px solid #dde3f0;")
        chips_lay = QHBoxLayout(chips_frame)
        chips_lay.setContentsMargins(6, 4, 6, 4)
        chips_lay.setSpacing(6)

        suggestions = [
            "Total area?", "Cost breakdown", "List elements",
            "Panel count", "Accessories", "Any warnings?"
        ]
        for s in suggestions:
            btn = QPushButton(s)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background:white; color:{_NOVA_BLUE};
                    border:1px solid #b0c4d8; border-radius:10px;
                    padding:3px 10px; font-size:10px;
                }}
                QPushButton:hover {{ background:{_NOVA_LIGHT}; }}
            """)
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda checked, text=s: self._ask_preset(text))
            chips_lay.addWidget(btn)
        chips_lay.addStretch()

        root.addWidget(chips_frame)

        # Welcome message
        self._append_message(
            "bot",
            "Hello! I'm the NovoForm AI Assistant. I can answer questions "
            "about your current BOQ — panel counts, area, cost, accessories, "
            "and more. Try asking: **'Give me a summary'** or click one of "
            "the quick buttons above."
        )

    def _send(self):
        q = self.input_box.text().strip()
        if not q:
            return
        self.input_box.clear()
        self._append_message("user", q)
        # Small delay for "thinking" effect
        QTimer.singleShot(300, lambda: self._respond(q))

    def _ask_preset(self, text: str):
        self._append_message("user", text)
        QTimer.singleShot(300, lambda: self._respond(text))

    def _respond(self, question: str):
        answer = self._engine.answer(question)
        self._append_message("bot", answer)

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
            # Convert **bold** markdown to HTML
            formatted = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', self._escape(text))
            # Convert newlines
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
        # Scroll to bottom
        sb = self.chat_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _escape(self, text: str) -> str:
        return (text.replace('&', '&amp;')
                    .replace('<', '&lt;')
                    .replace('>', '&gt;'))
