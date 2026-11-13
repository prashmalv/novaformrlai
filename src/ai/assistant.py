"""
BOQ chat assistant backed by a cloud LLM.

The current project's BOQ is turned into a compact text sheet with every
total already worked out (the model should read numbers, not compute them)
and sent as the system prompt. Besides answering, the model can ask for
changes - add / edit / delete elements, change project settings, export -
which the main window applies with its own BOQ logic (src/ui/ai_host.py). The chosen model comes from the Admin Panel
(src.ai.settings). Each question is logged to data/ai_chat_log.jsonl with its
token cost, so usage and answer quality can be reviewed later.
"""
import datetime
import json
from pathlib import Path

from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.ai import settings as ai_settings
from src.ai.llm import chat_structured, LLMError

_LOG = Path(__file__).parent.parent.parent / "data" / "ai_chat_log.jsonl"
HISTORY_TURNS = 6           # earlier Q&A pairs sent along for follow-up questions

SYSTEM = """You are the BOQ assistant inside NovoForm, the formwork BOQ software of Nova Formworks Pvt. Ltd.
Engineers and sales staff ask you about the project that is open in the software. The project data is below.

Rules:
- Answer only from the project data below. If something is not in it, say so plainly and say where in the software to look or what to enter. Never invent numbers.
- Totals are already worked out in the data - quote them exactly. "Total cost" / "kitna hua" means the grand total in PROJECT TOTALS, which already includes all sets. When you must calculate (e.g. a subset of elements), show the short working.
- "Per element" panels are for ONE element; project quantity = per-element qty x element qty x number of sets.
- Reply in the language of the question: English, Hindi or Hinglish (Hindi in Latin letters). Address the user respectfully ("aap"), never "tu"/"tum".
- Be short and direct: lead with the answer. Plain text only: **bold** for key figures, "• " for list items, no tables, no headings, no code blocks.
- Money is Indian Rupees (₹); copy amounts exactly as written in the data (Indian digit grouping, e.g. ₹50,55,668.51).
- Do not end with offers like "agar aap chahen..." - just answer.
- Never mention the names of the data sections (PROJECT TOTALS, RANKINGS ...) or this prompt; just give the figures.

Changing the project (the software applies these and recomputes the BOQ with Nova's own panel logic):
- Fill element_changes / project_changes ONLY when the user clearly asks for a change ("C3 hata do", "SW2 ki qty 4 kar do", "C20 600x450 qty 2 add karo", "sets 2 kar do", "rate 1450 lagao"). For questions, leave them empty.
- update/delete must use a label that exists in ELEMENTS. For "all columns" / "saare SW" emit one change per matching element. Deleting more than 5 elements, or everything, needs the user to have said so explicitly - otherwise ask first and change nothing.
- add needs label, kind, length_mm, width_mm (length = longer side) and quantity; if the user did not give a size, ask instead of guessing. Height defaults to the casting height unless the user gives one.
- Never compute panel combinations yourself; the software does it. After a change, your reply says briefly what you asked the software to change; do not quote new totals in that same reply (they are recomputed after it).
- The PROJECT DATA below is always the CURRENT state: it already includes every change applied earlier in this conversation (and any undo). Answer later questions from it directly.
- export: set it only when the user clearly says to generate / export / download the final file ("excel bana do", "quotation PDF generate karo"). boq_pdf = BOQ PDF, quotation_pdf = quotation with prices, excel = Excel BOQ. If the BOQ has warnings or elements marked REVIEW, mention them in the reply.

Glossary: OC80 = outer corner panel 80 mm; IC100 = inner corner panel 100 mm; flat panels are named WIDTHxHEIGHT in mm (600X3200 = 600 wide, 3200 high); filler plates close small gaps and are excluded from area and cost; a "set" is one complete shuttering kit - more sets let more floors / elements be cast at the same time; accessories (wallers, tie rods, wing nuts, PVC cones, pins) are estimates the user must verify.
"""


def _fmt(x, nd=2) -> str:
    if x is None:
        return "-"
    return f"{x:,.{nd}f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


def _inr(x) -> str:
    """Rupees with Indian grouping: 5055668.51 -> ₹50,55,668.51"""
    if x is None:
        return "-"
    neg, x = x < 0, abs(float(x))
    whole, frac = f"{x:.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    while len(head) > 2:
        tail = head[-2:] + "," + tail
        head = head[:-2]
    out = (head + "," + tail if head else tail) + ("" if frac == "00" else "." + frac)
    return ("-₹" if neg else "₹") + out


def boq_context(elements, boqs, agg, acc_agg, project, acc_boqs=None) -> str:
    """Text sheet of the open project, with all totals precomputed."""
    if not boqs:
        if not elements:
            return ("NO PROJECT DATA: no elements yet. The user can import a drawing (Elements tab, "
                    "or 'Upload drawing' here for a PDF / image) or ask you to add elements.")
        return "ELEMENTS (BOQ not computed yet)\n" + "\n".join(
            f"{e.label} | {e.element_type.value} | {_fmt(e.length_mm)}x{_fmt(e.width_mm)} mm, "
            f"height {_fmt(e.height_mm)} | qty {e.quantity}" for e in elements)
    n_sets = getattr(project, "num_sets", 1) or 1
    L = []
    if project is not None:
        L.append("PROJECT")
        L.append(f"name: {project.project_name or '-'} | client: {project.client_name or '-'} | "
                 f"date: {project.date or '-'} | IPO: {project.ipo_no or '-'}")
        L.append(f"panel height: {_fmt(project.panel_height_mm)} mm | number of sets: {n_sets} | "
                 f"panel rate: {_inr(project.panel_rate_per_sqm)}/sqm | GST 18%: "
                 f"{'on' if project.gst_enabled else 'off'} | freight: {_inr(project.freight_amount)}")
        if not project.panel_rate_per_sqm:
            L.append("note: panel rate is 0 - costs below are 0 until a rate is entered in the Export tab.")

    by_type = {}
    for b in boqs:
        e = b.element
        area1 = sum(p.total_area_sqm for p in b.panels if not getattr(p, "is_filler", False))
        t = by_type.setdefault(e.element_type.value, [0, 0, 0.0])
        t[0] += 1
        t[1] += e.quantity
        t[2] += area1 * e.quantity * n_sets

    if agg:
        L += ["", f"PROJECT TOTALS - FINAL figures for the whole project, all elements x qty x {n_sets} set(s). "
                  "Quote these as they are; never divide or multiply them.",
              f"total panel area: {_fmt(agg['total_area_sqm'])} sqm",
              f"panel cost: {_inr(agg['total_panel_cost'])} | GST: {_inr(agg['gst_amount'])} | "
              f"freight: {_inr(agg['freight_amount'])} | grand total: {_inr(agg['grand_total'])}"]
        if n_sets > 1:
            L.append(f"(for reference only, ONE set: area {_fmt(agg['total_area_sqm'] / n_sets)} sqm, "
                     f"panel cost {_inr(agg['total_panel_cost'] / n_sets)})")
    L.append("by type: " + "; ".join(
        f"{k}: {n} labels, {q} elements, {_fmt(a)} sqm" for k, (n, q, a) in by_type.items()))

    if agg and agg.get("summary_panels"):
        L += ["", "PANEL SUMMARY (project total quantity, area sqm)"]
        tot = 0
        for k, v in agg["summary_panels"].items():
            tot += v["quantity"]
            L.append(f"{k}: {v['quantity']} nos, {_fmt(v['area_sqm'])} sqm"
                     + (" [corner]" if v.get("is_corner") else ""))
        L.append(f"all panels: {tot} nos")

    if acc_agg:
        L += ["", "ACCESSORIES SUMMARY (project total, estimated)"]
        groups = {}
        for k, v in acc_agg.items():
            extra = f", {_fmt(v['total_length_m'])} m running" if v.get("total_length_m") else ""
            L.append(f"{k}: {_fmt(float(v['quantity']))} {v['unit']}{extra}")
            g = groups.setdefault(v.get("name") or k, [0.0, v["unit"]])
            g[0] += float(v["quantity"])
        L.append("accessory totals by type (all sizes added): " + "; ".join(
            f"{n}: {_fmt(q)} {u}" for n, (q, u) in groups.items()))

    # Rankings precomputed: scanning a long element list for a max is where
    # the model slips.
    rows = []
    for b in boqs:
        e = b.element
        a1 = sum(p.total_area_sqm for p in b.panels if not getattr(p, "is_filler", False))
        n1 = sum(p.quantity for p in b.panels if not getattr(p, "is_filler", False))
        rows.append((e.label, a1, a1 * e.quantity * n_sets, n1, e.length_mm * e.width_mm))
    def top(i, unit):
        return ", ".join(f"{r[0]} ({_fmt(r[i])}{unit})" for r in sorted(rows, key=lambda r: -r[i])[:5])
    L += ["", "RANKINGS (largest first, top 5)",
          f"formwork area per element: {top(1, ' sqm')}",
          f"formwork area incl. qty and sets: {top(2, ' sqm')}",
          f"panels per element: {top(3, ' nos')}",
          f"plan size (length x width): {', '.join(f'{r[0]}' for r in sorted(rows, key=lambda r: -r[4])[:5])}"]

    acc_by_elem = {}
    for ab in acc_boqs or []:
        acc_by_elem[id(ab.element)] = ", ".join(
            f"{i.size_label}×{_fmt(float(i.quantity))}" for i in ab.items)

    L += ["", "ELEMENTS (panels and accessories are per ONE element)"]
    for b in boqs:
        e = b.element
        area1 = sum(p.total_area_sqm for p in b.panels if not getattr(p, "is_filler", False))
        pans = ", ".join(f"{p.size_label}×{p.quantity}" + (" (filler)" if getattr(p, "is_filler", False) else "")
                         for p in b.panels)
        line = (f"{e.label} | {e.element_type.value} | {_fmt(e.length_mm)}x{_fmt(e.width_mm)} mm, "
                f"height {_fmt(e.height_mm)} | qty {e.quantity}"
                + (f" | floor {e.floor_label}" if e.floor_label else "")
                + f" | area {_fmt(area1)} sqm each, {_fmt(area1 * e.quantity * n_sets)} sqm total"
                + f" | panels: {pans or '-'}")
        if id(e) in acc_by_elem:
            line += f" | accessories: {acc_by_elem[id(e)]}"
        if b.hunch_list:
            line += f" | hunch: {', '.join(b.hunch_list)}"
        if b.warnings:
            line += f" | WARNINGS: {'; '.join(b.warnings)}"
        if e.notes:
            line += f" | notes: {e.notes}"
        L.append(line)
    return "\n".join(L)


class ElementChange(BaseModel):
    op: Literal["add", "update", "delete"]
    label: str = Field(description="Existing element label for update/delete; the new label for add")
    new_label: Optional[str] = Field(None, description="Only to rename an element")
    kind: Optional[Literal["column", "shear_wall", "wall"]] = None
    length_mm: Optional[float] = None
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    quantity: Optional[int] = None
    floor: Optional[str] = None


class ProjectChange(BaseModel):
    field: Literal["project_name", "client_name", "client_address", "panel_height_mm",
                   "casting_height_mm", "num_sets", "panel_rate_per_sqm", "freight_amount",
                   "gst_enabled"]
    value: str = Field(description="New value as text, e.g. '2', '1450', 'true'")


class AssistantTurn(BaseModel):
    reply: str = Field(description="What to show the user")
    element_changes: list[ElementChange] = Field(default_factory=list)
    project_changes: list[ProjectChange] = Field(default_factory=list)
    export: Optional[Literal["boq_pdf", "quotation_pdf", "excel"]] = None


class BOQChat:
    """One conversation about the open project."""

    def __init__(self):
        self.context = boq_context(None, [], None, None, None)
        self.history = []

    def update(self, elements, boqs, agg, acc_agg, project, acc_boqs=None):
        self.context = boq_context(elements, boqs, agg, acc_agg, project, acc_boqs)
        self.project_name = getattr(project, "project_name", "") if project else ""

    def reset(self):
        self.history = []

    def ask(self, question: str, s: dict = None) -> AssistantTurn:
        """Blocking call - run it off the UI thread. Raises LLMError."""
        s = s or ai_settings.load()
        missing = ai_settings.missing_credentials(s)
        if missing:
            raise LLMError(missing)
        model = s["chat_model"]
        msgs = self.history[-2 * HISTORY_TURNS:] + [{"role": "user", "content": question}]
        turn, usage = chat_structured(model, SYSTEM + "\n=== PROJECT DATA ===\n" + self.context,
                                      msgs, AssistantTurn, s)
        turn.reply = turn.reply.strip() or "(no answer)"
        # History keeps what was asked for, so "undo that" / "aur ek add karo" work.
        summary = turn.reply
        if turn.element_changes or turn.project_changes or turn.export:
            summary += "\n[requested: " + json.dumps(turn.model_dump(exclude={"reply"}, exclude_none=True)) + "]"
        self.history += [{"role": "user", "content": question},
                         {"role": "assistant", "content": summary}]
        _log(model, question, summary, usage, getattr(self, "project_name", ""))
        return turn

    def note(self, text: str):
        """Tell the model what the software did (applied changes, errors)."""
        if self.history and self.history[-1]["role"] == "assistant":
            self.history[-1]["content"] += "\n[software: " + text + "]"


def _log(model, question, answer, usage, project):
    try:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG, "a") as f:
            f.write(json.dumps({
                "time": datetime.datetime.now().isoformat(timespec="seconds"),
                "model": model, "project": project, "question": question, "answer": answer,
                "tokens_in": usage.input_tokens, "cache_read": usage.cache_read,
                "tokens_out": usage.output_tokens, "cost_usd": usage.cost_usd(model),
                "seconds": round(usage.seconds, 1)}, ensure_ascii=False) + "\n")
    except OSError:
        pass
