"""
MainWindow side of the AI Assistant: applies what the assistant asks for
(add / edit / delete elements, project settings, export, elements read from
a PDF or image) with the window's own BOQ logic, and keeps one undo step.

Mixed into MainWindow; uses its widgets and lists (_elements, _boqs, ...).
"""
import copy
import re

from PyQt6.QtWidgets import QMessageBox

from src.models.element import StructuralElement, ElementType
from src.engine.panel_optimizer import compute_boq

_KIND = {"column": ElementType.COLUMN, "shear_wall": ElementType.SHEAR_WALL,
         "wall": ElementType.WALL}


def _norm(label: str) -> str:
    return re.sub(r'[\s\-_]+', '', (label or "").upper())


class AIHostMixin:

    # ── undo ──────────────────────────────────────────────────────────────────
    def _ai_snapshot(self):
        self._ai_undo = {
            "lists": copy.deepcopy((self._elements, self._boqs)),
            "nova": self._is_nova_drawing,
            "ph": self.panel_height_combo.currentText(),
            "ch": self.casting_height_combo.currentText(),
            "sets": self.num_sets_spin.value(),
            "rate": self.rate_panel.value(),
            "freight": self.freight_spin.value(),
            "gst": self.gst_check.isChecked(),
            "names": (self.project_name_edit.text(), self.client_name_edit.text(),
                      self.client_addr_edit.text()),
        }

    def ai_can_undo(self) -> bool:
        return bool(getattr(self, "_ai_undo", None))

    def ai_undo(self) -> str:
        u = getattr(self, "_ai_undo", None)
        if not u:
            return "Nothing to undo."
        self._ai_undo = None
        self._elements, self._boqs = u["lists"]
        self._acc_boqs = []
        self._is_nova_drawing = u["nova"]
        self._ai_set_height(self.panel_height_combo, getattr(self, "boq_ph_combo", None), u["ph"])
        self._ai_set_height(self.casting_height_combo, getattr(self, "boq_ch_combo", None), u["ch"])
        self._ai_set_value(self.num_sets_spin, u["sets"])
        self._ai_set_value(self.boq_sets_spin, u["sets"])
        self._ai_set_value(self.rate_panel, u["rate"])
        self._ai_set_value(self.freight_spin, u["freight"])
        self.gst_check.blockSignals(True)
        self.gst_check.setChecked(u["gst"])
        self.gst_check.blockSignals(False)
        for w, v in zip((self.project_name_edit, self.client_name_edit, self.client_addr_edit), u["names"]):
            w.setText(v)
        self._ai_rebuild(recompute=[])
        self._ai_log("AI_UNDO", "last AI change undone")
        return "Last AI change undone."

    # ── widget helpers ────────────────────────────────────────────────────────
    @staticmethod
    def _ai_set_value(w, v):
        w.blockSignals(True)
        w.setValue(v)
        w.blockSignals(False)

    @staticmethod
    def _ai_set_height(combo, mirror, text):
        for c in (combo, mirror):
            if c is None:
                continue
            c.blockSignals(True)
            i = c.findText(text)
            if i >= 0:
                c.setCurrentIndex(i)
            else:
                c.setCurrentText(text)
            c.blockSignals(False)

    def _ai_log(self, action, detail):
        try:
            from src.auth.auth_manager import log_action
            log_action(self._user["username"], self._user["full_name"], action, detail)
        except Exception:
            pass

    def _ai_rebuild(self, recompute: list, all_geometry: bool = False):
        """Recompute BOQs for the element indexes in `recompute` (or all, if the
        BOQ list is out of step), then re-aggregate and refresh every view."""
        self._refresh_element_table()
        if not self._elements:
            self._boqs, self._acc_boqs, self._agg, self._acc_agg = [], [], None, None
            self._refresh_boq_tables_safe()
            self.ai_widget.update_data([], [], None, None, self._project, acc_boqs=[])
            return
        panel_h = self._get_panel_height()
        if panel_h is None:
            return
        if len(self._boqs) != len(self._elements):
            self._boqs = [compute_boq(e, panel_h) for e in self._elements]
        else:
            for i in recompute:
                self._boqs[i] = compute_boq(self._elements[i], panel_h)
        if all_geometry:
            # New panel height: the window's own handler re-optimises (or, for
            # Nova drawings, re-heights the drawn panels) and re-aggregates.
            self._regenerate_boq_if_elements_present()
        else:
            # nova_mode=True: keep the BOQs above, rebuild project + aggregates.
            self._auto_run_boq_silent(nova_mode=True)
        try:
            self.view_3d.load_elements(self._elements, bboxes=None, scale=1.0)
        except Exception:
            pass

    def _refresh_boq_tables_safe(self):
        try:
            self._refresh_boq_tables()
        except Exception:
            pass

    # ── chat actions ──────────────────────────────────────────────────────────
    def ai_apply_turn(self, turn) -> list:
        """Apply an AssistantTurn's changes. Returns lines describing what was done."""
        done, problems = [], []
        if not (turn.element_changes or turn.project_changes):
            return []
        self._ai_snapshot()
        cast_h = self._get_casting_height() or self._get_panel_height() or 3000
        recompute, ph_changed = set(), False

        for c in turn.element_changes:
            idx = next((i for i, e in enumerate(self._elements) if _norm(e.label) == _norm(c.label)), None)
            if c.op == "add":
                if idx is not None:
                    problems.append(f"{c.label} already exists - not added (ask to update it instead)")
                    continue
                if not (c.length_mm and c.width_mm and c.kind):
                    problems.append(f"{c.label}: size or type missing - not added")
                    continue
                e = StructuralElement(
                    element_type=_KIND[c.kind], label=c.label.strip(),
                    length_mm=float(max(c.length_mm, c.width_mm)), width_mm=float(min(c.length_mm, c.width_mm)),
                    height_mm=float(c.height_mm or cast_h), quantity=max(1, c.quantity or 1),
                    floor_label=c.floor or "", notes="added by AI chat")
                self._elements.append(e)
                if len(self._boqs) == len(self._elements) - 1:
                    self._boqs.append(None)
                recompute.add(len(self._elements) - 1)
                done.append(f"added {e.label} {e.element_type.value} {e.length_mm:.0f}×{e.width_mm:.0f} qty {e.quantity}")
            elif idx is None:
                problems.append(f"{c.label} not found")
            elif c.op == "delete":
                e = self._elements.pop(idx)
                if idx < len(self._boqs):
                    self._boqs.pop(idx)
                recompute = {i - 1 if i > idx else i for i in recompute if i != idx}
                done.append(f"deleted {e.label}")
            else:  # update
                e = self._elements[idx]
                before = (e.element_type, e.length_mm, e.width_mm, e.height_mm)
                parts = []
                if c.kind:
                    e.element_type = _KIND[c.kind]
                if c.length_mm or c.width_mm:
                    L = c.length_mm or e.length_mm
                    W = c.width_mm or e.width_mm
                    e.length_mm, e.width_mm = float(max(L, W)), float(min(L, W))
                if c.height_mm:
                    e.height_mm = float(c.height_mm)
                if (e.element_type, e.length_mm, e.width_mm, e.height_mm) != before:
                    if e.polygon_pts:
                        parts.append("drawn outline replaced by a rectangle")
                        e.polygon_pts = []
                    recompute.add(idx)
                    parts.append(f"{e.element_type.value} {e.length_mm:.0f}×{e.width_mm:.0f} H{e.height_mm:.0f}")
                if c.quantity:
                    e.quantity = max(1, c.quantity)
                    parts.append(f"qty {e.quantity}")
                if c.floor is not None and c.floor != e.floor_label:
                    e.floor_label = c.floor
                    parts.append(f"floor {c.floor or '-'}")
                if c.new_label and c.new_label.strip() != e.label:
                    parts.append(f"renamed to {c.new_label.strip()}")
                    e.label = c.new_label.strip()
                done.append(f"{c.label}: " + (", ".join(parts) or "no change"))

        for p in turn.project_changes:
            v = (p.value or "").strip()
            try:
                if p.field in ("panel_height_mm", "casting_height_mm"):
                    h = str(int(float(v)))
                    if p.field == "panel_height_mm":
                        self._ai_set_height(self.panel_height_combo, getattr(self, "boq_ph_combo", None), h)
                        ph_changed = True
                    else:
                        self._ai_set_height(self.casting_height_combo, getattr(self, "boq_ch_combo", None), h)
                elif p.field == "num_sets":
                    n = max(1, int(float(v)))
                    self._ai_set_value(self.num_sets_spin, n)
                    self._ai_set_value(self.boq_sets_spin, n)
                elif p.field == "panel_rate_per_sqm":
                    self._ai_set_value(self.rate_panel, float(v))
                elif p.field == "freight_amount":
                    self._ai_set_value(self.freight_spin, float(v))
                elif p.field == "gst_enabled":
                    self.gst_check.setChecked(v.lower() in ("1", "true", "yes", "on", "haan"))
                else:
                    {"project_name": self.project_name_edit, "client_name": self.client_name_edit,
                     "client_address": self.client_addr_edit}[p.field].setText(v)
                done.append(f"{p.field.replace('_', ' ')} = {v}")
            except (ValueError, KeyError):
                problems.append(f"could not set {p.field} to '{v}'")

        if not done:
            self._ai_undo = None
        else:
            # A new panel height changes every element's panels.
            self._ai_rebuild(sorted(i for i in recompute if i < len(self._elements)),
                             all_geometry=ph_changed)
            self._ai_log("AI_CHAT_CHANGE", "; ".join(done)[:500])
        return [f"✓ {d}" for d in done] + [f"✗ {p}" for p in problems]

    def ai_export(self, kind: str) -> str:
        """Run the normal export (it asks where to save - the final go-ahead)."""
        if not self._boqs:
            return "No BOQ yet - add or import elements first."
        fn = {"excel": self._export_excel, "boq_pdf": self._export_pdf,
              "quotation_pdf": self._export_quotation_pdf}.get(kind)
        if fn is None:
            return f"Unknown export '{kind}'"
        fn()
        return ""

    # ── drawing import (PDF / image) ──────────────────────────────────────────
    def ai_import_drawing(self, result, source_name: str) -> list:
        """Put elements read from a PDF / image into the project."""
        if not result.elements:
            return ["No columns or walls were found in this drawing."]
        replace = True
        if self._elements:
            box = QMessageBox(self)
            box.setWindowTitle("AI drawing import")
            box.setText(f"<b>{len(result.elements)} element type(s) read from {source_name}.</b><br><br>"
                        f"The project already has {len(self._elements)} element(s). What should I do?")
            b_rep = box.addButton("Replace all", QMessageBox.ButtonRole.AcceptRole)
            b_add = box.addButton("Add to existing", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() not in (b_rep, b_add):
                return ["Import cancelled."]
            replace = box.clickedButton() is b_rep
        self._ai_snapshot()
        cast_h = self._get_casting_height() or self._get_panel_height() or 3000
        if replace:
            self._elements, self._boqs, self._acc_boqs = [], [], []
            self._is_nova_drawing = False
            self._element_bboxes = []
        taken = {_norm(e.label) for e in self._elements}
        start = len(self._elements)
        review = 0
        for m in result.elements:
            label = m["label"]
            if _norm(label) in taken:
                label += f"-{m['floor']}" if m["floor"] else "-AI"
            taken.add(_norm(label))
            flags = list(m["notes"])
            if m["confidence"] < 0.6:
                review += 1
                flags.insert(0, "REVIEW")
            self._elements.append(StructuralElement(
                element_type=_KIND.get(m["kind"], ElementType.COLUMN), label=label,
                length_mm=float(m["length_mm"]), width_mm=float(m["width_mm"]),
                height_mm=float(cast_h), quantity=int(m["quantity"]), floor_label=m["floor"],
                notes=("AI " + source_name + (": " + "; ".join(flags) if flags else ""))[:300]))
        if not replace and len(self._boqs) == start:
            self._boqs += [None] * (len(self._elements) - start)
        self._ai_rebuild(list(range(start, len(self._elements))))
        n = sum(m["quantity"] for m in result.elements)
        self._ai_log("AI_DRAWING_IMPORT",
                     f"{len(result.elements)} types / {n} elements from {source_name}")
        out = [f"✓ {len(result.elements)} element type(s), {n} element(s) in total, added from {source_name}."]
        if review:
            out.append(f"⚠ {review} marked REVIEW (low confidence) - please check them in the preview.")
        out += [f"⚠ {w}" for w in result.warnings]
        if result.casting_height_mm:
            out.append(f"Drawing mentions height {result.casting_height_mm} mm - "
                       "say 'casting height ... kar do' if it should be used.")
        return out
