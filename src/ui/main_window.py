"""
NovoForm Phase 2 — Main Window (PyQt6)
"""
import os
import json
from datetime import date
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QFileDialog,
    QDialog, QDialogButtonBox, QFormLayout, QMessageBox,
    QGroupBox, QScrollArea, QTextEdit, QSplitter,
    QHeaderView, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon, QPixmap

from src.models.element import (
    StructuralElement, ElementType, JunctionType, ProjectBOQ, ElementBOQ
)
from src.engine.panel_optimizer import compute_boq, is_catalog_panel
from src.output.boq_generator import aggregate_project_boq
from src.output.pdf_generator import generate_pdf, generate_boq_pdf, generate_quotation_pdf
from src.output.excel_generator import generate_excel_boq
from src.parsers.dwg_parser import (
    parse_dwg, parse_dxf, get_conversion_status, dwg_to_dxf,
    parse_dxf_full, parse_dwg_full, detect_panel_height,
    is_nova_drawing, parse_nova_drawing,
)
from src.parsers.pdf_parser import (
    render_pdf_page, get_page_count, extract_title_block,
    extract_elements_ai, extract_elements_cv,
    get_api_key, save_api_key,
)
from src.engine.accessories_calc import (
    calculate_accessories, aggregate_accessories
)
from src.output.layout_drawing import (
    generate_element_layout, generate_project_layout,
    generate_element_layout_3d_figure,
)
from src.ui.drawing_viewer import DXFViewerWidget
from src.ui.ai_assistant import AIAssistantWidget
from src.ui.view_3d import Elements3DWidget
from src.output.dxf_generator import generate_formwork_dxf

# ---------- Style Constants ----------
NOVA_BLUE = "#1a3a5c"
NOVA_ACCENT = "#2c5f8a"
NOVA_LIGHT = "#dce8f5"
BG_LIGHT = "#f5f7fa"
SUCCESS_GREEN = "#27ae60"
WARN_ORANGE = "#e67e22"
ERR_RED = "#c0392b"

BTN_STYLE = f"""
    QPushButton {{
        background-color: {NOVA_ACCENT};
        color: white;
        border: none;
        border-radius: 4px;
        padding: 6px 14px;
        font-weight: bold;
        font-size: 12px;
    }}
    QPushButton:hover {{ background-color: #1a4a6e; }}
    QPushButton:pressed {{ background-color: #0f2d44; }}
    QPushButton:disabled {{ background-color: #b0b8c4; }}
"""

BTN_SECONDARY = f"""
    QPushButton {{
        background-color: white;
        color: {NOVA_ACCENT};
        border: 2px solid {NOVA_ACCENT};
        border-radius: 4px;
        padding: 5px 12px;
        font-weight: bold;
        font-size: 11px;
    }}
    QPushButton:hover {{ background-color: {NOVA_LIGHT}; }}
"""

BTN_DANGER = """
    QPushButton {
        background-color: #c0392b;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 5px 10px;
        font-weight: bold;
        font-size: 11px;
    }
    QPushButton:hover { background-color: #a93226; }
"""

HEADER_STYLE = f"""
    QLabel {{
        color: {NOVA_BLUE};
        font-size: 14px;
        font-weight: bold;
    }}
"""

GROUP_STYLE = f"""
    QGroupBox {{
        font-weight: bold;
        font-size: 11px;
        color: {NOVA_BLUE};
        border: 1.5px solid {NOVA_ACCENT};
        border-radius: 6px;
        margin-top: 12px;
        padding-top: 8px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 6px;
        background-color: white;
        left: 12px;
    }}
"""

TABLE_STYLE = f"""
    QTableWidget {{
        border: 1px solid #b0c4d8;
        border-radius: 4px;
        font-size: 11px;
        gridline-color: #dce8f5;
        background-color: white;
    }}
    QHeaderView::section {{
        background-color: {NOVA_ACCENT};
        color: white;
        padding: 5px;
        font-weight: bold;
        font-size: 11px;
        border: none;
    }}
    QTableWidget::item:selected {{
        background-color: {NOVA_LIGHT};
        color: {NOVA_BLUE};
    }}
"""


# ---------- Add Element Dialog ----------

class AddElementDialog(QDialog):
    def __init__(self, parent=None, element: StructuralElement = None):
        super().__init__(parent)
        self.setWindowTitle("Add Structural Element")
        self.setMinimumWidth(400)
        self.result_element = None

        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setSpacing(10)

        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "Column", "Wall", "Shear Wall",
            "Box Culvert", "Drain", "Monolithic",
            "Beam Bottom", "Beam Side"
        ])
        form.addRow("Element Type:", self.type_combo)

        self.junction_combo = QComboBox()
        self.junction_combo.addItems(["None", "L-Shape", "T-Shape", "C-Shape"])
        self.junction_combo.setToolTip("For complex wall junctions (T/L/C). Adds IC panels automatically.")
        form.addRow("Junction Type:", self.junction_combo)

        self.floor_edit = QLineEdit()
        self.floor_edit.setPlaceholderText("e.g. GF, 1F, 2F (optional)")
        form.addRow("Floor Label:", self.floor_edit)

        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("e.g. C1, SW1, W-A")
        form.addRow("Label:", self.label_edit)

        self.length_spin = QDoubleSpinBox()
        self.length_spin.setRange(100, 20000)
        self.length_spin.setValue(1000)
        self.length_spin.setSuffix(" mm")
        self.length_spin.setDecimals(0)
        form.addRow("Length (mm):", self.length_spin)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(100, 10000)
        self.width_spin.setValue(600)
        self.width_spin.setSuffix(" mm")
        self.width_spin.setDecimals(0)
        form.addRow("Width / Thickness (mm):", self.width_spin)

        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(100, 15000)
        self.height_spin.setValue(3000)
        self.height_spin.setSuffix(" mm")
        self.height_spin.setDecimals(0)
        form.addRow("Casting Height (mm):", self.height_spin)

        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 500)
        self.qty_spin.setValue(1)
        form.addRow("Quantity (nos):", self.qty_spin)

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Optional notes")
        form.addRow("Notes:", self.notes_edit)

        layout.addLayout(form)

        # Pre-fill if editing
        if element:
            self.type_combo.setCurrentText(element.element_type.value)
            self.label_edit.setText(element.label)
            self.length_spin.setValue(element.length_mm)
            self.width_spin.setValue(element.width_mm)
            self.height_spin.setValue(element.height_mm)
            self.qty_spin.setValue(element.quantity)
            self.notes_edit.setText(element.notes)
            jt = getattr(element, 'junction_type', JunctionType.NONE)
            self.junction_combo.setCurrentText(jt.value)
            self.floor_edit.setText(getattr(element, 'floor_label', ''))

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(BTN_STYLE)
        layout.addWidget(btns)

    def _accept(self):
        label = self.label_edit.text().strip()
        if not label:
            QMessageBox.warning(self, "Validation", "Please enter a label for the element.")
            return

        type_map = {
            "Column":      ElementType.COLUMN,
            "Wall":        ElementType.WALL,
            "Shear Wall":  ElementType.SHEAR_WALL,
            "Box Culvert": ElementType.BOX_CULVERT,
            "Drain":       ElementType.DRAIN,
            "Monolithic":  ElementType.MONOLITHIC,
            "Beam Bottom": ElementType.BEAM_BOTTOM,
            "Beam Side":   ElementType.BEAM_SIDE,
        }
        junction_map = {
            "None":    JunctionType.NONE,
            "L-Shape": JunctionType.L,
            "T-Shape": JunctionType.T,
            "C-Shape": JunctionType.C,
        }
        self.result_element = StructuralElement(
            element_type=type_map[self.type_combo.currentText()],
            label=label,
            length_mm=self.length_spin.value(),
            width_mm=self.width_spin.value(),
            height_mm=self.height_spin.value(),
            quantity=self.qty_spin.value(),
            notes=self.notes_edit.text().strip(),
            junction_type=junction_map[self.junction_combo.currentText()],
            floor_label=self.floor_edit.text().strip(),
        )
        self.accept()


# ---------- DWG Review Dialog ----------

class DWGReviewDialog(QDialog):
    """
    Shows auto-detected elements for user review before adding to project.
    User can: confirm, edit dimensions, delete false detections, change type.
    NEW: "Add Missing Element" button for elements not detected in drawing.
    """
    def __init__(self, elements: list, parent=None, casting_height_mm: float = 3200.0):
        super().__init__(parent)
        self.setWindowTitle("Review Detected Elements from Drawing")
        self.resize(860, 520)
        self._elements = list(elements)
        self._casting_height_mm = casting_height_mm

        layout = QVBoxLayout(self)

        info = QLabel(
            f"<b>{len(elements)} element(s) detected.</b>  "
            "Review dimensions — auto-detection may not be 100% accurate. "
            "Edit values, uncheck false detections, or add missing elements manually."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {NOVA_BLUE}; padding: 6px; background: {NOVA_LIGHT}; "
                           f"border-radius: 4px;")
        layout.addWidget(info)

        self.table = QTableWidget(len(elements), 7)
        self.table.setHorizontalHeaderLabels([
            "✓", "Label", "Type", "Length (mm)", "Width (mm)", "Height (mm)", "Qty"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet(TABLE_STYLE)

        type_options = ["Column", "Wall", "Shear Wall", "Beam Bottom", "Beam Side"]

        for i, e in enumerate(elements):
            chk = QTableWidgetItem()
            chk.setCheckState(Qt.CheckState.Checked)
            chk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 0, chk)
            self.table.setItem(i, 1, QTableWidgetItem(e.label))
            combo = QComboBox()
            combo.addItems(type_options)
            combo.setCurrentText(e.element_type.value)
            self.table.setCellWidget(i, 2, combo)
            self.table.setItem(i, 3, QTableWidgetItem(str(int(e.length_mm))))
            self.table.setItem(i, 4, QTableWidgetItem(str(int(e.width_mm))))
            self.table.setItem(i, 5, QTableWidgetItem(str(int(e.height_mm))))
            self.table.setItem(i, 6, QTableWidgetItem(str(e.quantity)))

        layout.addWidget(self.table)

        # ── Toolbar: Add / Remove element ─────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 4, 0, 4)

        btn_add = QPushButton("+ Add Missing Element")
        btn_add.setStyleSheet(BTN_STYLE)
        btn_add.setFixedHeight(30)
        btn_add.setToolTip("Manually add an element not detected in the drawing")
        btn_add.clicked.connect(self._add_missing_element)
        toolbar.addWidget(btn_add)

        btn_remove = QPushButton("Remove Selected Row")
        btn_remove.setStyleSheet(BTN_SECONDARY)
        btn_remove.setFixedHeight(30)
        btn_remove.setToolTip("Remove the selected row (false detection)")
        btn_remove.clicked.connect(self._remove_selected_row)
        toolbar.addWidget(btn_remove)

        toolbar.addStretch()

        count_lbl = QLabel()
        count_lbl.setStyleSheet("color:#555; font-size:11px;")
        self._count_lbl = count_lbl
        toolbar.addWidget(count_lbl)
        layout.addLayout(toolbar)
        self._update_count_label()

        note = QLabel(
            "⚠  Dimensions are auto-measured from drawing geometry. "
            "Cross-check against drawing annotations before confirming."
        )
        note.setStyleSheet("color: #e67e22; font-size: 10px; padding: 4px;")
        layout.addWidget(note)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Confirm & Add Selected")
        btns.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(BTN_STYLE)
        layout.addWidget(btns)

    def _update_count_label(self):
        if hasattr(self, '_count_lbl'):
            self._count_lbl.setText(f"{self.table.rowCount()} row(s)")

    def _add_missing_element(self):
        dlg = AddElementDialog(self)
        # Pre-fill casting height from context
        dlg.height_spin.setValue(self._casting_height_mm)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.result_element:
            return
        elem = dlg.result_element

        row = self.table.rowCount()
        self.table.insertRow(row)

        chk = QTableWidgetItem()
        chk.setCheckState(Qt.CheckState.Checked)
        chk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 0, chk)
        self.table.setItem(row, 1, QTableWidgetItem(elem.label))

        type_options = ["Column", "Wall", "Shear Wall", "Beam Bottom", "Beam Side"]
        combo = QComboBox()
        combo.addItems(type_options)
        combo.setCurrentText(elem.element_type.value)
        self.table.setCellWidget(row, 2, combo)

        self.table.setItem(row, 3, QTableWidgetItem(str(int(elem.length_mm))))
        self.table.setItem(row, 4, QTableWidgetItem(str(int(elem.width_mm))))
        self.table.setItem(row, 5, QTableWidgetItem(str(int(elem.height_mm))))
        self.table.setItem(row, 6, QTableWidgetItem(str(elem.quantity)))

        # Highlight manually-added rows
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                item.setBackground(QColor("#e8f5e9"))

        self.table.scrollToBottom()
        self._update_count_label()

    def _remove_selected_row(self):
        rows = set(idx.row() for idx in self.table.selectedIndexes())
        for row in sorted(rows, reverse=True):
            self.table.removeRow(row)
        self._update_count_label()

    def get_confirmed_elements(self) -> list:
        from src.models.element import StructuralElement, ElementType
        type_map = {
            "Column": ElementType.COLUMN,
            "Wall": ElementType.WALL,
            "Shear Wall": ElementType.SHEAR_WALL,
        }
        result = []
        for i in range(self.table.rowCount()):
            chk = self.table.item(i, 0)
            if chk.checkState() != Qt.CheckState.Checked:
                continue
            try:
                label = self.table.item(i, 1).text().strip() or f"E{i+1}"
                etype = type_map.get(self.table.cellWidget(i, 2).currentText(),
                                     ElementType.COLUMN)
                length = float(self.table.item(i, 3).text())
                width = float(self.table.item(i, 4).text())
                height = float(self.table.item(i, 5).text())
                qty = int(self.table.item(i, 6).text())
                result.append(StructuralElement(
                    element_type=etype, label=label,
                    length_mm=length, width_mm=width,
                    height_mm=height, quantity=qty
                ))
            except (ValueError, AttributeError):
                continue
        return result


# ---------- Import Settings Confirmation ----------

_PANEL_HEIGHT_OPTIONS = ["3705", "2470", "1235", "3200", "3000"]
# Standard catalog: 3705, 2470, 1235mm.  3200/3000 kept for non-standard drawings.


class DXFArrangeDialog(QDialog):
    """
    Shown before DXF export. Lets user see and reorder elements in the drawing.
    Each row shows: order index, label, type, dimensions, and origin
    (from drawing / manually added).  Up/Down buttons reorder the sequence.
    The DXF strip layout follows this order left-to-right.
    """

    def __init__(self, elements: list, boqs: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Arrange Elements for DXF Drawing")
        self.setMinimumSize(680, 420)
        self.setModal(True)

        # Work on copies so cancel doesn't affect original
        self._pairs = list(zip(elements, boqs))

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)

        # Info banner
        info = QLabel(
            "<b>DXF layout is a panel schedule — elements are drawn left to right in sequence.</b><br>"
            "Use <b>▲ Up</b> / <b>▼ Down</b> to set the drawing order. "
            "Elements added manually are shown in <span style='color:#1b5e20'>green</span>."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            f"background:{NOVA_LIGHT}; color:{NOVA_BLUE}; "
            "border-radius:4px; padding:8px; font-size:12px;"
        )
        layout.addWidget(info)

        # Table
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["#", "Label", "Type", "Dimensions", "Origin"]
        )
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(4, 140)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setStyleSheet(TABLE_STYLE)
        layout.addWidget(self.table)

        self._populate_table()

        # Up / Down buttons
        btn_row = QHBoxLayout()
        btn_up = QPushButton("▲  Move Up")
        btn_up.setStyleSheet(BTN_SECONDARY)
        btn_up.setFixedHeight(30)
        btn_up.clicked.connect(self._move_up)
        btn_row.addWidget(btn_up)

        btn_dn = QPushButton("▼  Move Down")
        btn_dn.setStyleSheet(BTN_SECONDARY)
        btn_dn.setFixedHeight(30)
        btn_dn.clicked.connect(self._move_down)
        btn_row.addWidget(btn_dn)

        btn_row.addStretch()

        self._pos_lbl = QLabel()
        self._pos_lbl.setStyleSheet("color:#555; font-size:11px;")
        btn_row.addWidget(self._pos_lbl)
        layout.addLayout(btn_row)

        note = QLabel(
            "Columns show as plan (cross-section) view.  "
            "Walls show as elevation view.  All at same scale."
        )
        note.setStyleSheet("color:#777; font-size:10px; font-style:italic;")
        layout.addWidget(note)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = btns.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Generate DXF in This Order →")
        ok.setStyleSheet(BTN_STYLE)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.table.selectionModel().selectionChanged.connect(self._on_selection)

    def _populate_table(self):
        self.table.setRowCount(0)
        for i, (elem, _boq) in enumerate(self._pairs):
            self.table.insertRow(i)
            # Order number
            num = QTableWidgetItem(str(i + 1))
            num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 0, num)
            # Label
            self.table.setItem(i, 1, QTableWidgetItem(elem.label))
            # Type
            self.table.setItem(i, 2, QTableWidgetItem(elem.element_type.value))
            # Dimensions
            dims = (
                f"{elem.length_mm:.0f}×{elem.width_mm:.0f}mm  "
                f"H={elem.height_mm:.0f}mm  Qty={elem.quantity}"
            )
            self.table.setItem(i, 3, QTableWidgetItem(dims))
            # Origin: manually added elements have no bbox
            has_bbox = bool(getattr(elem, 'bbox', None))
            origin_txt = "From drawing" if has_bbox else "Manually added"
            origin_item = QTableWidgetItem(origin_txt)
            if not has_bbox:
                origin_item.setForeground(QColor("#1b5e20"))
                origin_item.setBackground(QColor("#e8f5e9"))
                for col in range(5):
                    item = self.table.item(i, col)
                    if item:
                        item.setBackground(QColor("#e8f5e9"))
            self.table.setItem(i, 4, origin_item)

        self._update_pos_label()

    def _on_selection(self):
        self._update_pos_label()

    def _update_pos_label(self):
        if not hasattr(self, '_pos_lbl'):
            return
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self._pos_lbl.setText(f"Selected: row {rows[0].row() + 1} of {len(self._pairs)}")
        else:
            self._pos_lbl.setText(f"{len(self._pairs)} element(s)")

    def _move_up(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if row == 0:
            return
        self._pairs[row], self._pairs[row - 1] = self._pairs[row - 1], self._pairs[row]
        self._populate_table()
        self.table.selectRow(row - 1)

    def _move_down(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if row >= len(self._pairs) - 1:
            return
        self._pairs[row], self._pairs[row + 1] = self._pairs[row + 1], self._pairs[row]
        self._populate_table()
        self.table.selectRow(row + 1)

    def get_ordered_elements(self) -> list:
        return [p[0] for p in self._pairs]

    def get_ordered_boqs(self) -> list:
        return [p[1] for p in self._pairs]


class ImportSettingsDialog(QDialog):
    """
    Shown after DXF/DWG parsing completes — lets user confirm (or override)
    the panel height and casting height before reviewing detected elements.
    Shows auto-detected height as a hint if found.
    """

    def __init__(self, element_count: int, drawing_name: str,
                 current_panel_h: int, detected_panel_h,
                 current_casting_h: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Settings — Confirm Before Review")
        self.setMinimumWidth(460)
        self._panel_h   = current_panel_h
        self._casting_h = current_casting_h

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        summary = QLabel(
            f"<b>{element_count} element(s)</b> detected from "
            f"<b>{drawing_name}</b>.<br><br>"
            "Confirm the panel height before reviewing detected elements. "
            "You can also change it later from the Configuration tab."
        )
        summary.setWordWrap(True)
        summary.setStyleSheet(
            f"background:{NOVA_LIGHT}; color:{NOVA_BLUE}; "
            f"padding:10px; border-radius:4px; font-size:11px;")
        layout.addWidget(summary)

        form = QFormLayout()
        form.setSpacing(10)

        # Panel height
        self._ph_combo = QComboBox()
        self._ph_combo.addItems(_PANEL_HEIGHT_OPTIONS)
        idx = self._ph_combo.findText(str(current_panel_h))
        if idx >= 0:
            self._ph_combo.setCurrentIndex(idx)

        if detected_panel_h:
            det_lbl = QLabel(
                f"  ✓ Auto-detected: <b>{detected_panel_h} mm</b> "
                f"(from drawing annotations)")
            det_lbl.setStyleSheet(
                f"color:{SUCCESS_GREEN}; font-size:10px; padding:2px 0;")
            form.addRow("", det_lbl)
            det_idx = self._ph_combo.findText(str(detected_panel_h))
            if det_idx >= 0:
                self._ph_combo.setCurrentIndex(det_idx)
        else:
            nd_lbl = QLabel(
                "  ⓘ Height not found in drawing — using current setting")
            nd_lbl.setStyleSheet("color:#888; font-size:10px; font-style:italic;")
            form.addRow("", nd_lbl)

        form.addRow("Panel Height (mm):", self._ph_combo)

        # Casting height
        self._ch_combo = QComboBox()
        self._ch_combo.addItems(
            ["4200", "3200", "3000", "2700", "2470", "2400", "2100", "1800"])
        self._ch_combo.setEditable(True)
        ch_idx = self._ch_combo.findText(str(current_casting_h))
        if ch_idx >= 0:
            self._ch_combo.setCurrentIndex(ch_idx)
        form.addRow("Casting Height (mm):", self._ch_combo)

        hint = QLabel(
            "Panel Height = physical panel size used on site  ·  "
            "Casting Height = actual concrete pour height (drives accessories)")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#777; font-size:9px; padding:2px 0;")
        form.addRow("", hint)

        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Proceed to Review Elements →")
        btns.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(BTN_STYLE)
        layout.addWidget(btns)

    def _on_accept(self):
        try:
            self._panel_h   = int(self._ph_combo.currentText())
            self._casting_h = int(self._ch_combo.currentText())
        except ValueError:
            pass
        self.accept()

    def get_settings(self) -> tuple:
        """Returns (panel_height_mm, casting_height_mm)."""
        return self._panel_h, self._casting_h


# ---------- PDF Import Dialog ----------

class PDFImportDialog(QDialog):
    """
    Shows a rendered PDF drawing page. Auto-extracts structural elements
    using Claude Vision AI, then lets user review/edit before confirming.
    """
    def __init__(self, pdf_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import from PDF Drawing — AI Extraction")
        self.resize(1260, 720)
        self._elements: list[StructuralElement] = []
        self._pdf_path = pdf_path
        self._page_num = 0
        self._total_pages = get_page_count(pdf_path)
        self._zoom = 1.0

        root = QVBoxLayout(self)

        # ── Info bar ──────────────────────────────────────────────────────
        meta = extract_title_block(pdf_path)
        info_text = (
            f"<b>PDF:</b> {Path(pdf_path).name}"
            + (f"  |  <b>Project:</b> {meta['project_name']}" if meta['project_name'] else "")
            + (f"  |  <b>Drawing No:</b> {meta['drawing_no']}" if meta['drawing_no'] else "")
            + f"  |  <b>Pages:</b> {self._total_pages}"
        )
        info = QLabel(info_text)
        info.setWordWrap(True)
        info.setStyleSheet(
            f"background:{NOVA_LIGHT}; color:{NOVA_BLUE}; padding:6px; "
            f"border-radius:4px; font-size:11px;")
        root.addWidget(info)

        # ── Main splitter ─────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, stretch=1)

        # Left — PDF viewer
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)

        nav_row = QHBoxLayout()
        self._page_label = QLabel(f"Page 1 / {self._total_pages}")
        self._page_label.setStyleSheet("font-size:11px;")
        btn_prev = QPushButton("◀")
        btn_prev.setFixedWidth(36)
        btn_prev.setStyleSheet(BTN_SECONDARY)
        btn_prev.clicked.connect(self._prev_page)
        btn_next = QPushButton("▶")
        btn_next.setFixedWidth(36)
        btn_next.setStyleSheet(BTN_SECONDARY)
        btn_next.clicked.connect(self._next_page)
        btn_zin  = QPushButton("＋")
        btn_zin.setFixedWidth(36)
        btn_zin.setStyleSheet(BTN_SECONDARY)
        btn_zin.clicked.connect(self._zoom_in)
        btn_zout = QPushButton("－")
        btn_zout.setFixedWidth(36)
        btn_zout.setStyleSheet(BTN_SECONDARY)
        btn_zout.clicked.connect(self._zoom_out)
        btn_fit  = QPushButton("Fit")
        btn_fit.setFixedWidth(42)
        btn_fit.setStyleSheet(BTN_SECONDARY)
        btn_fit.clicked.connect(self._zoom_fit)

        nav_row.addWidget(btn_prev)
        nav_row.addWidget(self._page_label)
        nav_row.addWidget(btn_next)
        nav_row.addStretch()
        nav_row.addWidget(btn_zout)
        nav_row.addWidget(btn_zin)
        nav_row.addWidget(btn_fit)
        left_lay.addLayout(nav_row)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setStyleSheet("background:#555;")
        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setWidget(self._img_label)
        left_lay.addWidget(self._scroll)
        splitter.addWidget(left)

        # Right — AI extract + element table
        right = QWidget()
        right.setMinimumWidth(340)
        right.setMaximumWidth(440)
        right_lay = QVBoxLayout(right)

        # Extraction buttons row
        ext_row = QHBoxLayout()
        self._btn_ai = QPushButton("✨ Extract with AI")
        self._btn_ai.setStyleSheet(BTN_STYLE)
        self._btn_ai.setMinimumHeight(34)
        self._btn_ai.setToolTip("Uses Claude AI Vision — requires API key. Most accurate (~95%).")
        self._btn_ai.clicked.connect(self._auto_extract_ai)
        ext_row.addWidget(self._btn_ai)

        self._btn_cv = QPushButton("🔍 Extract Offline")
        self._btn_cv.setStyleSheet(BTN_SECONDARY)
        self._btn_cv.setMinimumHeight(34)
        self._btn_cv.setToolTip(
            "Uses OpenCV + EasyOCR — no API key needed. "
            "First run downloads ~150 MB models (once only).")
        self._btn_cv.clicked.connect(self._auto_extract_cv)
        ext_row.addWidget(self._btn_cv)
        right_lay.addLayout(ext_row)

        self._ai_status = QLabel(
            "AI: accurate, needs API key  |  Offline: free, downloads OCR models on first run")
        self._ai_status.setWordWrap(True)
        self._ai_status.setStyleSheet("font-size:10px; color:#555; padding:2px 4px;")
        right_lay.addWidget(self._ai_status)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#ccc;")
        right_lay.addWidget(sep)

        hdr = QLabel("Detected Elements  (review before confirming)")
        hdr.setStyleSheet(
            f"font-weight:bold; font-size:12px; color:{NOVA_BLUE}; padding:2px 4px;")
        right_lay.addWidget(hdr)

        self._elem_table = QTableWidget(0, 4)
        self._elem_table.setHorizontalHeaderLabels(["Label", "Type", "L×W mm", "H mm"])
        self._elem_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._elem_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._elem_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._elem_table.setAlternatingRowColors(True)
        self._elem_table.setStyleSheet(TABLE_STYLE)
        right_lay.addWidget(self._elem_table)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("＋ Add")
        btn_add.setStyleSheet(BTN_SECONDARY)
        btn_add.clicked.connect(self._add_element)
        btn_edit = QPushButton("Edit")
        btn_edit.setStyleSheet(BTN_SECONDARY)
        btn_edit.clicked.connect(self._edit_element)
        btn_del = QPushButton("Delete")
        btn_del.setStyleSheet(BTN_SECONDARY)
        btn_del.clicked.connect(self._delete_element)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_del)
        right_lay.addLayout(btn_row)

        # Casting height for all imported elements
        h_row = QHBoxLayout()
        h_row.addWidget(QLabel("Casting Height:"))
        self._height_spin = QDoubleSpinBox()
        self._height_spin.setRange(500, 15000)
        self._height_spin.setValue(3000)
        self._height_spin.setSuffix(" mm")
        self._height_spin.setDecimals(0)
        h_row.addWidget(self._height_spin)
        right_lay.addLayout(h_row)

        splitter.addWidget(right)
        splitter.setSizes([860, 380])

        # ── Bottom buttons ────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(BTN_STYLE)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Add to Project →")
        root.addWidget(btns)

        self._render_page()

    # ── Rendering ─────────────────────────────────────────────────────────

    def _render_page(self):
        try:
            png_bytes, _, _ = render_pdf_page(self._pdf_path, self._page_num, dpi=150)
        except Exception as ex:
            self._img_label.setText(f"Cannot render: {ex}")
            return
        self._base_pixmap = QPixmap()
        self._base_pixmap.loadFromData(png_bytes)
        self._page_label.setText(f"Page {self._page_num + 1} / {self._total_pages}")
        self._apply_zoom()

    def _apply_zoom(self):
        if not hasattr(self, '_base_pixmap') or self._base_pixmap.isNull():
            return
        scaled = self._base_pixmap.scaled(
            int(self._base_pixmap.width()  * self._zoom),
            int(self._base_pixmap.height() * self._zoom),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._img_label.setPixmap(scaled)
        self._img_label.resize(scaled.size())

    def _zoom_in(self):
        self._zoom = min(self._zoom * 1.3, 4.0); self._apply_zoom()

    def _zoom_out(self):
        self._zoom = max(self._zoom / 1.3, 0.2); self._apply_zoom()

    def _zoom_fit(self):
        if not hasattr(self, '_base_pixmap') or self._base_pixmap.isNull():
            return
        vp = self._scroll.viewport()
        self._zoom = min((vp.width() - 20) / self._base_pixmap.width(),
                         (vp.height() - 20) / self._base_pixmap.height())
        self._apply_zoom()

    def _prev_page(self):
        if self._page_num > 0:
            self._page_num -= 1; self._render_page()

    def _next_page(self):
        if self._page_num < self._total_pages - 1:
            self._page_num += 1; self._render_page()

    # ── Extraction ────────────────────────────────────────────────────────────

    def _auto_extract_ai(self):
        key = get_api_key()
        if not key:
            key = self._ask_api_key()
            if not key:
                return
        self._run_extraction(
            lambda: extract_elements_ai(self._pdf_path, self._page_num, api_key=key),
            busy_msg="Analysing drawing with AI… please wait (5–15 sec).",
        )

    def _auto_extract_cv(self):
        self._run_extraction(
            lambda: extract_elements_cv(self._pdf_path, self._page_num),
            busy_msg=(
                "Running offline OCR… first run downloads ~150 MB models. "
                "Please wait (30–60 sec)."),
        )

    def _run_extraction(self, fn, busy_msg: str):
        from PyQt6.QtWidgets import QApplication
        self._btn_ai.setEnabled(False)
        self._btn_cv.setEnabled(False)
        self._ai_status.setText(busy_msg)
        self._ai_status.setStyleSheet("font-size:10px; color:#1a5c1a; padding:2px 4px;")
        QApplication.processEvents()

        try:
            raw = fn()
        except Exception as ex:
            self._ai_status.setText(f"Extraction failed: {ex}")
            self._ai_status.setStyleSheet("font-size:10px; color:#c00; padding:2px 4px;")
            self._btn_ai.setEnabled(True)
            self._btn_cv.setEnabled(True)
            return

        self._btn_ai.setEnabled(True)
        self._btn_cv.setEnabled(True)

        if not raw:
            self._ai_status.setText(
                "No elements found. Try the other method or add manually below.")
            self._ai_status.setStyleSheet("font-size:10px; color:#b85c00; padding:2px 4px;")
            return

        type_map = {
            "column":     ElementType.COLUMN,
            "wall":       ElementType.WALL,
            "shear wall": ElementType.SHEAR_WALL,
            "shearwall":  ElementType.SHEAR_WALL,
        }
        casting_h = self._height_spin.value()
        added = 0
        for item in raw:
            etype  = type_map.get(item["type"].lower(), ElementType.COLUMN)
            length = item.get("length_mm") or item.get("width_mm") or 0
            width  = item.get("width_mm")  or item.get("length_mm") or 0
            if length == 0:
                continue
            self._elements.append(StructuralElement(
                element_type = etype,
                label        = item["label"],
                length_mm    = float(max(length, width)),
                width_mm     = float(min(length, width)),
                height_mm    = casting_h,
                quantity     = max(1, item.get("quantity", 1)),
            ))
            added += 1

        self._refresh_table()
        self._ai_status.setText(
            f"✓ {added} element(s) detected. "
            "Review and set correct casting height before confirming.")
        self._ai_status.setStyleSheet(
            "font-size:10px; color:#1a5c1a; font-weight:bold; padding:2px 4px;")

    def _ask_api_key(self) -> str | None:
        """Prompt user to enter Anthropic API key, save it for future use."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Anthropic API Key Required")
        dlg.setMinimumWidth(480)
        lay = QVBoxLayout(dlg)

        lay.addWidget(QLabel(
            "<b>An Anthropic API key is required for AI extraction.</b><br><br>"
            "Get your key from: <a href='https://console.anthropic.com'>console.anthropic.com</a><br>"
            "The key is saved locally in config/api_config.json for future use."
        ))
        lbl = QLabel()
        lbl.setOpenExternalLinks(True)
        lay.addWidget(lbl)

        key_edit = QLineEdit()
        key_edit.setPlaceholderText("sk-ant-api03-...")
        key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(key_edit)

        show_chk = QCheckBox("Show key")
        show_chk.toggled.connect(
            lambda v: key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if v else QLineEdit.EchoMode.Password))
        lay.addWidget(show_chk)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            key = key_edit.text().strip()
            if key:
                save_api_key(key)
                return key
        return None

    # ── Element management ────────────────────────────────────────────────

    def _refresh_table(self):
        self._elem_table.setRowCount(len(self._elements))
        for i, e in enumerate(self._elements):
            self._elem_table.setItem(i, 0, QTableWidgetItem(e.label))
            self._elem_table.setItem(i, 1, QTableWidgetItem(e.element_type.value))
            self._elem_table.setItem(i, 2, QTableWidgetItem(
                f"{int(e.length_mm)}×{int(e.width_mm)}"))
            self._elem_table.setItem(i, 3, QTableWidgetItem(str(int(e.height_mm))))

    def _add_element(self):
        dlg = AddElementDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_element:
            self._elements.append(dlg.result_element)
            self._refresh_table()

    def _edit_element(self):
        row = self._elem_table.currentRow()
        if row < 0 or row >= len(self._elements):
            return
        dlg = AddElementDialog(self, self._elements[row])
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_element:
            self._elements[row] = dlg.result_element
            self._refresh_table()

    def _delete_element(self):
        row = self._elem_table.currentRow()
        if 0 <= row < len(self._elements):
            self._elements.pop(row)
            self._refresh_table()

    def _on_ok(self):
        if not self._elements:
            QMessageBox.warning(self, "No Elements",
                                "No elements to add. Use Auto-Extract or add manually.")
            return
        self.accept()

    def get_elements(self) -> list[StructuralElement]:
        return list(self._elements)


# ---------- Background DXF parser worker ----------

class _DXFParserWorker(QThread):
    """Runs parse_dxf_full / parse_dwg_full on a background thread so the UI stays responsive."""
    finished = pyqtSignal(object)   # emits (detected, bboxes, polylines, scale, err, dxf_render_path)

    def __init__(self, path: str, panel_h: float, casting_h: float, parent=None):
        super().__init__(parent)
        self._path     = path
        self._panel_h  = panel_h
        self._casting_h = casting_h

    def run(self):
        try:
            if self._path.lower().endswith('.dxf'):
                detected, bboxes, polylines, scale = parse_dxf_full(
                    self._path, self._casting_h)
                self.finished.emit((detected, bboxes, polylines, scale, None, self._path))
            else:
                detected, bboxes, polylines, scale, err, dxf_path = parse_dwg_full(
                    self._path, self._casting_h)
                self.finished.emit((detected, bboxes, polylines, scale, err, dxf_path))
        except Exception as ex:
            self.finished.emit(([], [], [], 1.0, str(ex), ""))


# ---------- Nova Drawing v2 parser worker ----------

class _NovaDrawingWorker(QThread):
    """
    Background worker for Nova's labelled-panel DXF format.
    Returns (elements, boqs, error) — BOQs are pre-computed from drawing labels,
    so no separate optimization step is needed.
    """
    finished = pyqtSignal(object)   # emits (elements, boqs, error)

    def __init__(self, path: str, casting_h: float, product_h: float, parent=None):
        super().__init__(parent)
        self._path      = path
        self._casting_h = casting_h
        self._product_h = product_h

    def run(self):
        try:
            elements, boqs, error = parse_nova_drawing(
                self._path,
                casting_height_mm=self._casting_h,
                product_height_mm=self._product_h,
            )
            self.finished.emit((elements, boqs, error))
        except Exception as ex:
            self.finished.emit(([], [], str(ex)))


# ---------- Main Window ----------

class MainWindow(QMainWindow):

    def __init__(self, current_user: dict | None = None):
        super().__init__()
        self._user = current_user or {"username": "unknown", "full_name": "Unknown", "role": "user"}
        self.setWindowTitle(
            f"NovoForm — Formwork BOQ Generator  |  {self._user['full_name']}")
        self.resize(1200, 800)
        _icon_path = Path(__file__).parent.parent.parent / "assets" / "images" / "NovaLogo.png"
        if _icon_path.exists():
            self.setWindowIcon(QIcon(str(_icon_path)))
        self._elements: list[StructuralElement] = []
        self._boqs: list[ElementBOQ] = []
        self._acc_boqs: list = []
        self._project = ProjectBOQ()
        self._agg = None
        self._acc_agg = None
        self._element_bboxes: list = []
        self._current_dxf_path: str = ""
        # Deferred render args — set after import, consumed when user opens that tab
        self._pending_dxf_render_args: dict | None = None
        self._pending_3d_render_args:  dict | None = None

        self._setup_ui()
        self._apply_global_style()

    def _apply_global_style(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {BG_LIGHT}; font-family: Helvetica Neue, Arial; }}
            QTabWidget::pane {{ border: 1px solid #b0c4d8; border-radius: 4px; }}
            QTabBar::tab {{
                background: #c8dae8; color: {NOVA_BLUE};
                padding: 7px 18px; font-weight: bold; font-size: 11px;
                border-top-left-radius: 4px; border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{ background: {NOVA_ACCENT}; color: white; }}
            QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {{
                border: 1px solid #b0c4d8; border-radius: 3px;
                padding: 4px 6px; background: white; font-size: 11px;
            }}
            QLabel {{ font-size: 11px; }}
        """)

    # ====================================================
    # UI SETUP
    # ====================================================
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Top banner
        banner = self._make_banner()
        main_layout.addWidget(banner)

        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.tabs.addTab(self._tab_project(),         "  Project Info  ")
        self.tabs.addTab(self._tab_elements(),        "  Elements  ")
        self.tabs.addTab(self._tab_drawing_preview(), "  Drawing Preview  ")
        self.tabs.addTab(self._tab_3d_view(),         "  3D View  ")
        self.tabs.addTab(self._tab_config(),          "  Configuration  ")
        self.tabs.addTab(self._tab_boq(),             "  BOQ Results  ")
        self.tabs.addTab(self._tab_export(),          "  Export  ")
        self.tabs.addTab(self._tab_ai_assistant(),    "  AI Assistant  ")

        # Lazy rendering: Drawing Preview (2) and 3D View (3) render only on demand
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int):
        if index == 2 and self._pending_dxf_render_args is not None:
            args = self._pending_dxf_render_args
            self._pending_dxf_render_args = None
            try:
                self.drawing_viewer.load_drawing(**args)
            except Exception:
                pass
        elif index == 3 and self._pending_3d_render_args is not None:
            args = self._pending_3d_render_args
            self._pending_3d_render_args = None
            try:
                self.view_3d.load_elements(**args)
            except Exception:
                pass

    def _make_banner(self) -> QWidget:
        frame = QFrame()
        frame.setStyleSheet(f"background-color: {NOVA_BLUE}; border-radius: 6px;")
        frame.setFixedHeight(60)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(10, 4, 14, 4)

        # Nova logo
        logo_path = Path(__file__).parent.parent.parent / "assets" / "images" / "NovaLogo.png"
        if logo_path.exists():
            logo_lbl = QLabel()
            logo_lbl.setStyleSheet("background: transparent;")
            pix = QPixmap(str(logo_path))
            logo_lbl.setPixmap(
                pix.scaledToHeight(48, Qt.TransformationMode.SmoothTransformation)
            )
            logo_lbl.setFixedWidth(160)
            lay.addWidget(logo_lbl)
            sep = QLabel("|")
            sep.setStyleSheet("color: #4a7a9b; background: transparent; font-size: 18px;")
            lay.addWidget(sep)

        sub = QLabel("Formwork Analysis & BOQ Generator")
        sub.setStyleSheet("color: #a8c8e8; background: transparent; font-size: 12px; font-weight: bold;")
        lay.addWidget(sub)

        lay.addStretch()

        # Logged-in user indicator
        role_badge = "🛡 Admin" if self._user["role"] == "admin" else "👤 User"
        user_lbl = QLabel(f"{role_badge}  {self._user['full_name']}")
        user_lbl.setStyleSheet(
            "color: #a8c8e8; background: transparent; font-size: 10px;")
        lay.addWidget(user_lbl)

        lay.addSpacing(10)

        # Admin panel button (admin only)
        if self._user["role"] == "admin":
            admin_btn = QPushButton("⚙ Admin")
            admin_btn.setFixedHeight(30)
            admin_btn.setStyleSheet("""
                QPushButton {
                    background: #2c5f8a; color: white;
                    border-radius: 4px; padding: 0 12px;
                    font-weight: 700; font-size: 10px; border: none;
                }
                QPushButton:hover { background: #3a7ab0; }
            """)
            admin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            admin_btn.clicked.connect(self._open_admin_panel)
            lay.addWidget(admin_btn)
            lay.addSpacing(4)

        version = QLabel("v1.1")
        version.setStyleSheet("color: #7aabcc; background: transparent; font-size: 10px;")
        lay.addWidget(version)

        return frame

    def _open_admin_panel(self):
        from src.ui.admin_panel import AdminPanelDialog
        from src.auth.auth_manager import log_action
        log_action(self._user["username"], self._user["full_name"],
                   "ADMIN_PANEL_OPENED", "")
        dlg = AdminPanelDialog(self._user, parent=self)
        dlg.exec()

    # ====================================================
    # TAB 1: Project Info
    # ====================================================
    def _tab_project(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        lbl = QLabel("Project Information")
        lbl.setStyleSheet(HEADER_STYLE)
        lay.addWidget(lbl)

        grp = QGroupBox("Client & Project Details")
        grp.setStyleSheet(GROUP_STYLE)
        form = QFormLayout(grp)
        form.setSpacing(10)

        self.project_name_edit = QLineEdit()
        self.project_name_edit.setPlaceholderText("e.g. Commercial Complex - Sector 42")
        form.addRow("Project Name:", self.project_name_edit)

        self.client_name_edit = QLineEdit()
        self.client_name_edit.setPlaceholderText("Client company name")
        form.addRow("Client Name:", self.client_name_edit)

        self.client_addr_edit = QLineEdit()
        self.client_addr_edit.setPlaceholderText("Client address")
        form.addRow("Client Address:", self.client_addr_edit)

        self.ipo_edit = QLineEdit()
        self.ipo_edit.setPlaceholderText("IPO Number (if any)")
        form.addRow("IPO No:", self.ipo_edit)

        self.boq_number_edit = QLineEdit()
        self.boq_number_edit.setPlaceholderText("e.g. BOQ-2025-001 (auto-generated if blank)")
        form.addRow("BOQ Number:", self.boq_number_edit)

        self.qtn_number_edit = QLineEdit()
        self.qtn_number_edit.setPlaceholderText("e.g. QTN-2025-001 (auto-generated if blank)")
        form.addRow("Quotation Number:", self.qtn_number_edit)

        self.date_edit = QLineEdit()
        self.date_edit.setText(date.today().strftime("%d-%m-%Y"))
        form.addRow("Date:", self.date_edit)

        lay.addWidget(grp)
        lay.addStretch()

        return w

    # ====================================================
    # TAB 2: Elements
    # ====================================================
    def _tab_elements(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        # Header row
        h_lay = QHBoxLayout()
        lbl = QLabel("Structural Elements")
        lbl.setStyleSheet(HEADER_STYLE)
        h_lay.addWidget(lbl)
        h_lay.addStretch()

        btn_add = QPushButton("+ Add Element")
        btn_add.setStyleSheet(BTN_STYLE)
        btn_add.clicked.connect(self._add_element)
        h_lay.addWidget(btn_add)

        btn_edit = QPushButton("Edit")
        btn_edit.setStyleSheet(BTN_SECONDARY)
        btn_edit.clicked.connect(self._edit_element)
        h_lay.addWidget(btn_edit)

        btn_del = QPushButton("Delete")
        btn_del.setStyleSheet(BTN_DANGER)
        btn_del.clicked.connect(self._delete_element)
        h_lay.addWidget(btn_del)

        lay.addLayout(h_lay)

        # Elements table
        self.elem_table = QTableWidget(0, 7)
        self.elem_table.setHorizontalHeaderLabels([
            "Label", "Type", "Length (mm)", "Width (mm)",
            "Height (mm)", "Qty", "Notes"
        ])
        self.elem_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.elem_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.elem_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.elem_table.setAlternatingRowColors(True)
        self.elem_table.setStyleSheet(TABLE_STYLE)
        lay.addWidget(self.elem_table)

        # DWG/DXF Import
        grp_dwg = QGroupBox("Import from Drawing File (DWG / DXF)")
        grp_dwg.setStyleSheet(GROUP_STYLE)
        dwg_lay = QVBoxLayout(grp_dwg)

        dwg_row = QHBoxLayout()
        self.dwg_path_edit = QLineEdit()
        self.dwg_path_edit.setReadOnly(True)
        self.dwg_path_edit.setPlaceholderText("No file selected — click Browse to load DWG or DXF")
        dwg_row.addWidget(self.dwg_path_edit)

        btn_browse = QPushButton("Browse…")
        btn_browse.setStyleSheet(BTN_SECONDARY)
        btn_browse.setFixedWidth(90)
        btn_browse.clicked.connect(self._browse_dwg)
        dwg_row.addWidget(btn_browse)

        btn_import = QPushButton("Import Elements")
        btn_import.setStyleSheet(BTN_STYLE)
        btn_import.setFixedWidth(130)
        btn_import.clicked.connect(self._import_dwg)
        dwg_row.addWidget(btn_import)
        dwg_lay.addLayout(dwg_row)

        # Status row
        self.dwg_status_label = QLabel("")
        self.dwg_status_label.setStyleSheet("font-size: 10px; color: #555;")
        dwg_lay.addWidget(self.dwg_status_label)
        self._update_dwg_status()

        lay.addWidget(grp_dwg)

        # PDF Import
        grp_pdf = QGroupBox("Import from PDF Drawing")
        grp_pdf.setStyleSheet(GROUP_STYLE)
        pdf_lay = QVBoxLayout(grp_pdf)

        pdf_row = QHBoxLayout()
        self.pdf_path_edit = QLineEdit()
        self.pdf_path_edit.setReadOnly(True)
        self.pdf_path_edit.setPlaceholderText(
            "No file selected — click Browse to load a PDF structural drawing")
        pdf_row.addWidget(self.pdf_path_edit)

        btn_pdf_browse = QPushButton("Browse…")
        btn_pdf_browse.setStyleSheet(BTN_SECONDARY)
        btn_pdf_browse.setFixedWidth(90)
        btn_pdf_browse.clicked.connect(self._browse_pdf)
        pdf_row.addWidget(btn_pdf_browse)

        btn_pdf_import = QPushButton("Open & Review")
        btn_pdf_import.setStyleSheet(BTN_STYLE)
        btn_pdf_import.setFixedWidth(130)
        btn_pdf_import.clicked.connect(self._import_pdf)
        pdf_row.addWidget(btn_pdf_import)
        pdf_lay.addLayout(pdf_row)

        pdf_note = QLabel(
            "ℹ  PDF drawings are shown as a visual preview. "
            "Review the Schedule of Columns / Walls and enter elements manually.")
        pdf_note.setWordWrap(True)
        pdf_note.setStyleSheet("font-size:10px; color:#666; padding:2px 0;")
        pdf_lay.addWidget(pdf_note)

        lay.addWidget(grp_pdf)

        # Quick text input
        grp = QGroupBox("Quick Text Input (e.g. '5 columns 300x450 height 3000')")
        grp.setStyleSheet(GROUP_STYLE)
        g_lay = QVBoxLayout(grp)

        self.quick_input = QLineEdit()
        self.quick_input.setPlaceholderText(
            "e.g. '10 columns 300x450 height 3000' or 'shear wall 6000x300 height 3200'")
        g_lay.addWidget(self.quick_input)

        btn_parse = QPushButton("Parse & Add")
        btn_parse.setStyleSheet(BTN_STYLE)
        btn_parse.clicked.connect(self._parse_quick_input)
        btn_parse.setMaximumWidth(120)
        g_lay.addWidget(btn_parse)

        lay.addWidget(grp)

        return w

    # ====================================================
    # TAB 3: Drawing Preview
    # ====================================================
    def _tab_drawing_preview(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Info banner
        info = QLabel(
            "  Drawing Preview — auto-detected elements are highlighted. "
            "Click any element to select it. Double-click to edit.  "
            "Use the toolbar above the drawing to zoom & pan."
        )
        info.setStyleSheet(
            f"background:{NOVA_LIGHT}; color:{NOVA_BLUE}; "
            f"border-radius:4px; padding:6px 10px; font-size:10px;"
        )
        info.setWordWrap(True)
        lay.addWidget(info)

        # The viewer widget
        self.drawing_viewer = DXFViewerWidget()
        self.drawing_viewer.element_selected.connect(self._on_viewer_element_selected)
        self.drawing_viewer.element_double_clicked.connect(self._on_viewer_element_dblclick)
        lay.addWidget(self.drawing_viewer, stretch=1)

        # Legend row
        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(0, 0, 0, 0)
        colors_legend = [
            ("Column", "#1565C0"), ("Wall", "#1B5E20"),
            ("Shear Wall", "#B71C1C"), ("Box Culvert", "#4A148C"),
            ("Drain", "#E65100"),
        ]
        for name, color in colors_legend:
            dot = QLabel(f"● {name}")
            dot.setStyleSheet(
                f"color:{color}; font-size:10px; font-weight:bold; "
                f"margin-right:12px; background:transparent;"
            )
            legend_row.addWidget(dot)
        legend_row.addStretch()
        lay.addLayout(legend_row)

        return w

    # ====================================================
    # TAB 3: 3D View
    # ====================================================
    def _tab_3d_view(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        info = QLabel(
            "  3D Elements Overview — all detected elements shown as 3D boxes at their "
            "actual drawing positions. Heights are to scale.  "
            "Drag to rotate · Scroll to zoom.  "
        )
        info.setStyleSheet(
            f"background:{NOVA_LIGHT}; color:{NOVA_BLUE}; "
            f"border-radius:0; padding:5px 10px; font-size:10px;"
        )
        lay.addWidget(info)

        self.view_3d = Elements3DWidget()
        lay.addWidget(self.view_3d, stretch=1)
        return w

    def _on_viewer_element_selected(self, idx: int):
        """Drawing viewer click → highlight row in Elements table."""
        if 0 <= idx < self.elem_table.rowCount():
            self.elem_table.selectRow(idx)
            self.tabs.setCurrentIndex(1)  # switch to Elements tab

    def _on_viewer_element_dblclick(self, idx: int):
        """Drawing viewer double-click → open edit dialog."""
        if 0 <= idx < len(self._elements):
            self.tabs.setCurrentIndex(1)
            self.elem_table.selectRow(idx)
            self._edit_element()

    # ====================================================
    # TAB 4: Configuration
    # ====================================================
    def _tab_config(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        lbl = QLabel("Pre-Run Configuration")
        lbl.setStyleSheet(HEADER_STYLE)
        lay.addWidget(lbl)

        # Panel Settings
        grp1 = QGroupBox("Panel Settings")
        grp1.setStyleSheet(GROUP_STYLE)
        f1 = QFormLayout(grp1)
        f1.setSpacing(10)

        self.panel_height_combo = QComboBox()
        self.panel_height_combo.addItems(_PANEL_HEIGHT_OPTIONS)
        self.panel_height_combo.setCurrentText("3200")
        self.panel_height_combo.setMinimumWidth(160)
        self.panel_height_combo.currentIndexChanged.connect(
            self._regenerate_boq_if_elements_present)
        f1.addRow("Panel Height (mm):", self.panel_height_combo)

        self.casting_height_combo = QComboBox()
        self.casting_height_combo.addItems(["3200", "3000", "2700", "2470", "2400", "2100", "1800", "1500"])
        self.casting_height_combo.setCurrentText("3200")
        self.casting_height_combo.setEditable(True)
        self.casting_height_combo.setMinimumWidth(160)
        _cast_lbl = QLabel("Casting Height (mm):")
        _cast_lbl.setToolTip(
            "Actual wall/column height for the concrete pour.\n"
            "Used to compute accessories (wallers, tierods).\n"
            "Panel Height = physical panel size being used."
        )
        f1.addRow(_cast_lbl, self.casting_height_combo)

        self.num_sets_spin = QSpinBox()
        self.num_sets_spin.setRange(1, 100)
        self.num_sets_spin.setValue(1)
        f1.addRow("Number of Sets:", self.num_sets_spin)

        lay.addWidget(grp1)

        # Rate Inputs
        grp2 = QGroupBox("Rate Inputs (Optional — for cost estimate)")
        grp2.setStyleSheet(GROUP_STYLE)
        f2 = QFormLayout(grp2)
        f2.setSpacing(10)

        self.rate_panel = QDoubleSpinBox()
        self.rate_panel.setRange(0, 100000)
        self.rate_panel.setDecimals(2)
        self.rate_panel.setSuffix(" ₹/sqm")
        f2.addRow("Panel Rate:", self.rate_panel)

        self.rate_waller = QDoubleSpinBox()
        self.rate_waller.setRange(0, 10000)
        self.rate_waller.setDecimals(2)
        self.rate_waller.setSuffix(" ₹/rm")
        f2.addRow("Waller Rate:", self.rate_waller)

        self.rate_tierod = QDoubleSpinBox()
        self.rate_tierod.setRange(0, 10000)
        self.rate_tierod.setDecimals(2)
        self.rate_tierod.setSuffix(" ₹/rm")
        f2.addRow("Tierod Rate:", self.rate_tierod)

        self.rate_prop = QDoubleSpinBox()
        self.rate_prop.setRange(0, 10000)
        self.rate_prop.setDecimals(2)
        self.rate_prop.setSuffix(" ₹/unit")
        f2.addRow("Prop Rate:", self.rate_prop)

        lay.addWidget(grp2)

        # Additional
        grp3 = QGroupBox("Additional Charges")
        grp3.setStyleSheet(GROUP_STYLE)
        f3 = QFormLayout(grp3)
        f3.setSpacing(10)

        self.gst_check = QCheckBox("Include GST @ 18%")
        self.gst_check.setChecked(True)
        f3.addRow("GST:", self.gst_check)

        self.freight_spin = QDoubleSpinBox()
        self.freight_spin.setRange(0, 10000000)
        self.freight_spin.setDecimals(2)
        self.freight_spin.setSuffix(" ₹")
        f3.addRow("Freight Charges:", self.freight_spin)

        lay.addWidget(grp3)

        # Run button
        btn_run = QPushButton("  ▶  Run Optimization & Generate BOQ")
        btn_run.setStyleSheet(BTN_STYLE)
        btn_run.setMinimumHeight(40)
        btn_run.clicked.connect(self._run_optimization)
        lay.addWidget(btn_run)

        lay.addStretch()
        return w

    # ====================================================
    # TAB 4: BOQ Results
    # ====================================================
    def _tab_boq(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        hdr_row = QHBoxLayout()
        lbl = QLabel("BOQ Results")
        lbl.setStyleSheet(HEADER_STYLE)
        hdr_row.addWidget(lbl)
        hdr_row.addStretch()

        btn_view_layout = QPushButton("  View Layout")
        btn_view_layout.setStyleSheet(BTN_SECONDARY)
        btn_view_layout.setFixedHeight(30)
        btn_view_layout.setToolTip("View panel layout for selected/first element")
        btn_view_layout.clicked.connect(self._view_layout_selected)
        hdr_row.addWidget(btn_view_layout)

        lay.addLayout(hdr_row)

        # Non-standard panel warning banner (hidden until BOQ has non-catalog items)
        self.nonstandard_banner = QLabel("")
        self.nonstandard_banner.setWordWrap(True)
        self.nonstandard_banner.setVisible(False)
        self.nonstandard_banner.setStyleSheet(
            "background:#fff3e0; color:#b84800; font-size:11px; font-weight:bold; "
            "padding:10px 14px; border-left:4px solid #f57c00; border-radius:4px;")
        lay.addWidget(self.nonstandard_banner)

        self._ns_edit_btn = QPushButton("  ✏  Edit Elements to Fix")
        self._ns_edit_btn.setStyleSheet(
            "QPushButton { background:#f57c00; color:white; border:none; border-radius:4px; "
            "padding:5px 14px; font-weight:bold; font-size:11px; } "
            "QPushButton:hover { background:#e65100; }")
        self._ns_edit_btn.setVisible(False)
        self._ns_edit_btn.setFixedHeight(30)
        self._ns_edit_btn.setToolTip(
            "Open Elements tab — change panel height in Configuration or edit element dimensions")
        self._ns_edit_btn.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        lay.addWidget(self._ns_edit_btn)

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Element-wise BOQ
        top = QWidget()
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(0, 0, 0, 0)
        top_lay.addWidget(QLabel("Per-Element Panel Breakdown:"))

        self.boq_detail_table = QTableWidget(0, 6)
        self.boq_detail_table.setHorizontalHeaderLabels([
            "Element", "Panel Size", "Qty", "Area/Panel (sqm)",
            "Total Area (sqm)", "Warnings"
        ])
        self.boq_detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.boq_detail_table.setStyleSheet(TABLE_STYLE)
        self.boq_detail_table.setAlternatingRowColors(True)
        top_lay.addWidget(self.boq_detail_table)
        splitter.addWidget(top)

        # Summary
        bottom = QWidget()
        bot_lay = QVBoxLayout(bottom)
        bot_lay.setContentsMargins(0, 0, 0, 0)
        bot_lay.addWidget(QLabel("Consolidated Panel Summary:"))

        self.boq_summary_table = QTableWidget(0, 5)
        self.boq_summary_table.setHorizontalHeaderLabels([
            "Panel Size", "Unit Area (sqm)", "Total Qty", "Total Area (sqm)", "Amount (₹)"
        ])
        self.boq_summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.boq_summary_table.setStyleSheet(TABLE_STYLE)
        self.boq_summary_table.setAlternatingRowColors(True)
        bot_lay.addWidget(self.boq_summary_table)

        # Cost summary labels
        self.cost_label = QLabel("")
        self.cost_label.setStyleSheet(
            f"color: {NOVA_BLUE}; font-weight: bold; font-size: 12px; padding: 6px;")
        bot_lay.addWidget(self.cost_label)
        splitter.addWidget(bottom)

        # Accessories section
        acc_widget = QWidget()
        acc_lay = QVBoxLayout(acc_widget)
        acc_lay.setContentsMargins(0, 0, 0, 0)
        acc_lay.addWidget(QLabel("B — Accessories Summary:"))

        self.acc_table = QTableWidget(0, 4)
        self.acc_table.setHorizontalHeaderLabels([
            "Accessory", "Quantity (nos)", "Length/Unit", "Total (m)"
        ])
        self.acc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.acc_table.setStyleSheet(TABLE_STYLE)
        self.acc_table.setAlternatingRowColors(True)
        acc_lay.addWidget(self.acc_table)

        self.acc_warn_label = QLabel("")
        self.acc_warn_label.setStyleSheet("color: #c0392b; font-weight: bold; font-size: 11px; padding: 4px;")
        self.acc_warn_label.setWordWrap(True)
        acc_lay.addWidget(self.acc_warn_label)

        splitter.addWidget(acc_widget)
        lay.addWidget(splitter)

        return w

    # ====================================================
    # TAB 6: AI Assistant
    # ====================================================
    def _tab_ai_assistant(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        info = QLabel(
            "  Ask questions about your current BOQ in plain English. "
            "Works 100% offline — no internet required.  "
        )
        info.setStyleSheet(
            f"background:{NOVA_LIGHT}; color:{NOVA_BLUE}; "
            f"border-radius:0; padding:5px 10px; font-size:10px;"
        )
        lay.addWidget(info)

        self.ai_widget = AIAssistantWidget()
        lay.addWidget(self.ai_widget, stretch=1)
        return w

    # ====================================================
    # TAB 5: Export
    # ====================================================
    def _tab_export(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        lbl = QLabel("Export & Output")
        lbl.setStyleSheet(HEADER_STYLE)
        lay.addWidget(lbl)

        grp = QGroupBox("Export Options")
        grp.setStyleSheet(GROUP_STYLE)
        g = QVBoxLayout(grp)
        g.setSpacing(12)

        btn_boq_pdf = QPushButton("  Export BOQ PDF")
        btn_boq_pdf.setStyleSheet(BTN_STYLE)
        btn_boq_pdf.setMinimumHeight(38)
        btn_boq_pdf.setToolTip("Export Bill of Quantities PDF (panel schedule, accessories, summary)")
        btn_boq_pdf.clicked.connect(self._export_pdf)
        g.addWidget(btn_boq_pdf)

        btn_qtn_pdf = QPushButton("  Export Quotation PDF")
        btn_qtn_pdf.setStyleSheet(BTN_STYLE)
        btn_qtn_pdf.setMinimumHeight(38)
        btn_qtn_pdf.setToolTip("Export Quotation PDF (pricing, T&C, Prepared By)")
        btn_qtn_pdf.clicked.connect(self._export_quotation_pdf)
        g.addWidget(btn_qtn_pdf)

        btn_excel = QPushButton("  Export Excel BOQ")
        btn_excel.setStyleSheet(BTN_SECONDARY)
        btn_excel.setMinimumHeight(38)
        btn_excel.clicked.connect(self._export_excel)
        g.addWidget(btn_excel)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #b0c4d8;")
        g.addWidget(sep)

        btn_layout_view = QPushButton("  View Panel Layout (selected element)")
        btn_layout_view.setStyleSheet(BTN_SECONDARY)
        btn_layout_view.setMinimumHeight(38)
        btn_layout_view.clicked.connect(self._view_layout_selected)
        g.addWidget(btn_layout_view)

        btn_layout_all = QPushButton("  Export Layout PDF (all elements)")
        btn_layout_all.setStyleSheet(BTN_STYLE)
        btn_layout_all.setMinimumHeight(38)
        btn_layout_all.clicked.connect(self._export_layout_pdf)
        g.addWidget(btn_layout_all)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #b0c4d8;")
        g.addWidget(sep2)

        btn_dxf = QPushButton("  Export Formwork Drawing (DXF)")
        btn_dxf.setStyleSheet(
            "QPushButton { background:#1a3a5c; color:white; border:none; border-radius:5px; "
            "padding:8px 16px; font-size:13px; font-weight:bold; }"
            "QPushButton:hover { background:#2c5f8a; }"
        )
        btn_dxf.setMinimumHeight(42)
        btn_dxf.setToolTip(
            "Generate an AutoCAD-compatible DXF drawing with panel layouts, "
            "annotations, BOQ table, and title block.\n"
            "Opens in AutoCAD, FreeCAD, LibreCAD, or any DXF viewer."
        )
        btn_dxf.clicked.connect(self._export_drawing_dxf)
        g.addWidget(btn_dxf)

        dxf_note = QLabel(
            "DXF contains: panel layout per element, OC corner marks, "
            "waller & tierod positions, BOQ table, title block."
        )
        dxf_note.setWordWrap(True)
        dxf_note.setStyleSheet("color:#555; font-size:10px; padding: 2px 4px;")
        g.addWidget(dxf_note)

        lay.addWidget(grp)

        self.export_log = QTextEdit()
        self.export_log.setReadOnly(True)
        self.export_log.setMaximumHeight(120)
        self.export_log.setStyleSheet("border: 1px solid #b0c4d8; border-radius: 4px; font-size: 10px;")
        lay.addWidget(QLabel("Export Log:"))
        lay.addWidget(self.export_log)

        lay.addStretch()
        return w

    # ====================================================
    # LOGIC
    # ====================================================

    def _add_element(self):
        dlg = AddElementDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_element:
            self._elements.append(dlg.result_element)
            self._refresh_element_table()

    def _edit_element(self):
        row = self.elem_table.currentRow()
        if row < 0 or row >= len(self._elements):
            QMessageBox.information(self, "Edit", "Please select an element to edit.")
            return
        dlg = AddElementDialog(self, self._elements[row])
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_element:
            self._elements[row] = dlg.result_element
            self._refresh_element_table()

    def _delete_element(self):
        row = self.elem_table.currentRow()
        if row < 0 or row >= len(self._elements):
            QMessageBox.information(self, "Delete", "Please select an element to delete.")
            return
        elem = self._elements[row]
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete element '{elem.label}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._elements.pop(row)
            self._refresh_element_table()

    def _refresh_element_table(self):
        self.elem_table.setRowCount(len(self._elements))
        for i, e in enumerate(self._elements):
            vals = [
                e.label, e.element_type.value,
                f"{e.length_mm:.0f}", f"{e.width_mm:.0f}",
                f"{e.height_mm:.0f}", str(e.quantity), e.notes
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 0:
                    item.setFont(QFont("Helvetica Neue", 10, QFont.Weight.Bold))
                self.elem_table.setItem(i, j, item)

    def _parse_quick_input(self):
        """
        Parse quick text inputs like:
        '5 columns 300x450 height 3000'
        'shear wall 6000x300 height 3200'
        '3 walls 4500x200 h 2800'
        """
        text = self.quick_input.text().strip().lower()
        if not text:
            return

        import re

        # Detect type
        etype = ElementType.COLUMN
        if 'shear' in text or 'shear wall' in text:
            etype = ElementType.SHEAR_WALL
        elif 'wall' in text:
            etype = ElementType.WALL

        # Detect quantity
        qty = 1
        m = re.match(r'^(\d+)\s+', text)
        if m:
            qty = int(m.group(1))

        # Detect dimensions (NxM pattern)
        dims = re.findall(r'(\d+)\s*[xX×]\s*(\d+)', text)
        if not dims:
            QMessageBox.warning(self, "Parse Error",
                                "Could not find dimensions. Use format like '300x450'.")
            return
        L, W = int(dims[0][0]), int(dims[0][1])

        # Detect height
        h_match = re.search(r'h(?:eight)?\s*[=:–-]?\s*(\d+)', text)
        height = int(h_match.group(1)) if h_match else 3000

        # Auto label
        existing = [e.label for e in self._elements]
        prefix = "C" if etype == ElementType.COLUMN else "SW" if etype == ElementType.SHEAR_WALL else "W"
        n = 1
        while f"{prefix}{n}" in existing:
            n += 1
        label = f"{prefix}{n}"

        elem = StructuralElement(
            element_type=etype, label=label,
            length_mm=L, width_mm=W,
            height_mm=height, quantity=qty
        )
        self._elements.append(elem)
        self._refresh_element_table()
        self.quick_input.clear()

    def _update_dwg_status(self):
        status = get_conversion_status()
        parts = []
        if status['dwg2dxf']:
            parts.append("✓ dwg2dxf (LibreDWG)")
        else:
            parts.append("✗ dwg2dxf not found")
        if status['oda_converter']:
            parts.append("✓ ODA Converter")
        else:
            parts.append("✗ ODA Converter not found")
        parts.append("✓ DXF supported directly")
        self.dwg_status_label.setText("Conversion tools: " + "  |  ".join(parts))

    def _browse_dwg(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Drawing File", "",
            "Drawing Files (*.dwg *.dxf);;DWG Files (*.dwg);;DXF Files (*.dxf)"
        )
        if path:
            self.dwg_path_edit.setText(path)

    def _browse_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF Drawing", "",
            "PDF Files (*.pdf);;All Files (*)"
        )
        if path:
            self.pdf_path_edit.setText(path)

    def _import_pdf(self):
        path = self.pdf_path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "No File", "Please select a PDF file first.")
            return

        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            dlg = PDFImportDialog(path, self)
        except Exception as ex:
            self.unsetCursor()
            QMessageBox.critical(self, "PDF Error", f"Cannot open PDF:\n{ex}")
            return
        finally:
            self.unsetCursor()

        if dlg.exec() == QDialog.DialogCode.Accepted:
            elements = dlg.get_elements()
            added = 0
            for elem in elements:
                existing_labels = [e.label for e in self._elements]
                if elem.label in existing_labels:
                    elem.label = elem.label + "_pdf"
                self._elements.append(elem)
                added += 1
            self._refresh_element_table()
            QMessageBox.information(
                self, "Elements Added",
                f"{added} element(s) imported from PDF.\n"
                "Review them in the Elements tab, then click Compute BOQ."
            )

    def _import_dwg(self):
        path = self.dwg_path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "No File", "Please select a DWG or DXF file first.")
            return

        panel_h    = float(self.panel_height_combo.currentText())
        casting_h  = float(self.casting_height_combo.currentText()) \
                     if hasattr(self, 'casting_height_combo') else panel_h

        # Progress dialog — accurate timing hint for large drawings
        from PyQt6.QtWidgets import QProgressDialog
        progress = QProgressDialog(
            "Parsing drawing, please wait…\n\n"
            "Small drawings  (< 10 elements) :  ~30 sec\n"
            "Medium drawings (10–30 elements): 1–2 min\n"
            "Large drawings  (30+ elements)  : 3–6 min\n\n"
            "The window will stay responsive during parsing.",
            None, 0, 0, self
        )
        progress.setWindowTitle("Importing Drawing")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.show()

        def _on_parse_done(result):
            progress.close()
            detected, bboxes_raw, all_polylines, scale_used, err, dxf_render_path = result

            if err:
                QMessageBox.critical(self, "Import Error", err)
                return

            if not detected:
                QMessageBox.information(
                    self, "No Elements Found",
                    "No structural elements were detected in the drawing.\n\n"
                    "Possible reasons:\n"
                    "• Drawing uses unsupported layer naming\n"
                    "• Dimensions are in unexpected units\n"
                    "• Elements drawn as LINES instead of polylines\n\n"
                    "Try adding elements manually or check the drawing."
                )
                return

            # ── Replace / Add / Cancel when project already has elements ──────
            if self._elements:
                msg = QMessageBox(self)
                msg.setWindowTitle("Import Drawing")
                msg.setIcon(QMessageBox.Icon.Question)
                msg.setText(
                    f"<b>{len(detected)} element(s) found in the drawing.</b><br><br>"
                    f"This project currently has <b>{len(self._elements)} existing "
                    f"element(s)</b>.<br>What would you like to do?"
                )
                replace_btn = msg.addButton(
                    "Replace All  (recommended)", QMessageBox.ButtonRole.AcceptRole)
                add_btn     = msg.addButton(
                    "Add to Existing", QMessageBox.ButtonRole.AcceptRole)
                cancel_btn  = msg.addButton(
                    "Cancel", QMessageBox.ButtonRole.RejectRole)
                msg.setDefaultButton(replace_btn)
                msg.exec()

                clicked = msg.clickedButton()
                if clicked == cancel_btn:
                    return
                if clicked == replace_btn:
                    # Full reset — clean slate for the new drawing
                    self._elements.clear()
                    self._boqs.clear()
                    self._acc_boqs.clear()
                    self._project        = ProjectBOQ()
                    self._agg            = None
                    self._acc_agg        = None
                    self._pending_dxf_render_args = None
                    self._pending_3d_render_args  = None
                    self._refresh_element_table()

            # ── Auto-detect panel height from DXF text annotations ───────────
            detected_h = None
            dxf_for_detect = dxf_render_path if (
                dxf_render_path and dxf_render_path.lower().endswith('.dxf')
            ) else (path if path.lower().endswith('.dxf') else None)
            if dxf_for_detect:
                try:
                    detected_h = detect_panel_height(dxf_for_detect)
                except Exception:
                    pass

            # ── Import Settings Confirmation ──────────────────────────────────
            try:
                cur_ph = int(self.panel_height_combo.currentText())
            except ValueError:
                cur_ph = 3200
            try:
                cur_ch = int(self.casting_height_combo.currentText())
            except (ValueError, AttributeError):
                cur_ch = 3200

            settings_dlg = ImportSettingsDialog(
                element_count    = len(detected),
                drawing_name     = Path(path).name,
                current_panel_h  = cur_ph,
                detected_panel_h = detected_h,
                current_casting_h= cur_ch,
                parent           = self,
            )
            if settings_dlg.exec() != QDialog.DialogCode.Accepted:
                return
            confirmed_ph, confirmed_ch = settings_dlg.get_settings()

            # Apply confirmed heights to Configuration dropdowns
            ph_idx = self.panel_height_combo.findText(str(confirmed_ph))
            if ph_idx >= 0:
                self.panel_height_combo.setCurrentIndex(ph_idx)
            else:
                self.panel_height_combo.setCurrentText(str(confirmed_ph))
            ch_idx = self.casting_height_combo.findText(str(confirmed_ch))
            if ch_idx >= 0:
                self.casting_height_combo.setCurrentIndex(ch_idx)
            else:
                self.casting_height_combo.setCurrentText(str(confirmed_ch))

            # ── Review dialog ─────────────────────────────────────────────────
            dlg = DWGReviewDialog(detected, self,
                                  casting_height_mm=float(confirmed_ch))
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            confirmed = dlg.get_confirmed_elements()
            added = 0
            confirmed_bboxes = []
            for i, elem in enumerate(confirmed):
                existing_labels = [e.label for e in self._elements]
                if elem.label in existing_labels:
                    elem.label = elem.label + "_dwg"
                self._elements.append(elem)
                if i < len(bboxes_raw):
                    confirmed_bboxes.append(bboxes_raw[i])
                added += 1

            # ── Store drawing preview data — rendered lazily on tab click ─────
            if bboxes_raw:
                self._element_bboxes   = confirmed_bboxes
                self._current_dxf_path = path
                self._pending_dxf_render_args = dict(
                    elements  = list(self._elements[-added:]),
                    bboxes    = confirmed_bboxes,
                    polylines = all_polylines,
                    scale     = scale_used,
                    title     = path,
                    dxf_path  = dxf_render_path,
                )
                self._pending_3d_render_args = dict(
                    elements = list(self._elements[-added:]),
                    bboxes   = confirmed_bboxes,
                    scale    = scale_used,
                )

            self._refresh_element_table()
            # Switch to Elements tab so user sees results immediately
            self.tabs.setCurrentIndex(1)

            from src.auth.auth_manager import log_action as _log
            _log(self._user["username"], self._user["full_name"],
                 "DXF_IMPORT",
                 f"{added} elements from: {Path(path).name}")

            ph_used = int(self.panel_height_combo.currentText())
            QMessageBox.information(
                self, "Import Complete",
                f"✓  {added} element(s) imported from drawing.\n\n"
                f"Panel height set to: {ph_used} mm\n\n"
                f"Drawing Preview and 3D View tabs will render\n"
                f"when you click them (keeps UI fast).\n\n"
                f"Next: go to Configuration tab → Run Optimization & Generate BOQ.\n"
                f"Tip: change panel height in Configuration → BOQ updates instantly."
            )

        def _on_nova_parse_done(result):
            """Handler for Nova labelled-panel DXF — BOQs already computed from drawing."""
            progress.close()
            elements, boqs, error = result

            if error:
                QMessageBox.critical(self, "Import Error", error)
                return

            if not elements:
                QMessageBox.information(
                    self, "No Elements Found",
                    "No labelled column elements were found in this drawing.\n\n"
                    "Expected labels: 'COL:-LxW', 'FF-COL LxW', 'R-COL LxW' etc.\n\n"
                    "Try the standard import or add elements manually."
                )
                return

            # Replace existing project if user confirms
            if self._elements:
                msg = QMessageBox(self)
                msg.setWindowTitle("Nova Drawing Import")
                msg.setIcon(QMessageBox.Icon.Question)
                msg.setText(
                    f"<b>{len(elements)} element(s) found in Nova drawing.</b><br><br>"
                    f"This project currently has <b>{len(self._elements)} existing "
                    f"element(s)</b>.<br>What would you like to do?"
                )
                replace_btn = msg.addButton(
                    "Replace All  (recommended)", QMessageBox.ButtonRole.AcceptRole)
                add_btn     = msg.addButton(
                    "Add to Existing", QMessageBox.ButtonRole.AcceptRole)
                cancel_btn  = msg.addButton(
                    "Cancel", QMessageBox.ButtonRole.RejectRole)
                msg.exec()
                clicked = msg.clickedButton()
                if clicked == cancel_btn:
                    return
                if clicked == replace_btn:
                    self._elements.clear()
                    self._boqs.clear()
                    self._acc_boqs.clear()
                    self._project    = ProjectBOQ()
                    self._agg        = None
                    self._acc_agg    = None
                    self._refresh_element_table()

            # Add elements and pre-computed BOQs directly — no optimization needed
            added_nova = 0
            for elem, boq in zip(elements, boqs):
                existing_labels = [e.label for e in self._elements]
                if elem.label in existing_labels:
                    elem.label = elem.label + "_dwg"
                self._elements.append(elem)
                self._boqs.append(boq)
                added_nova += 1

            # Update project BOQ header
            self._project = ProjectBOQ(
                project_name=self.project_name_edit.text().strip(),
                client_name=self.client_name_edit.text().strip(),
                panel_height_mm=panel_h,
                element_boqs=list(self._boqs),
            )

            self._refresh_element_table()
            self.tabs.setCurrentIndex(1)  # jump to Elements tab

            from src.auth.auth_manager import log_action as _log
            _log(self._user["username"], self._user["full_name"],
                 "NOVA_DXF_IMPORT",
                 f"{added_nova} elements (BOQ from drawing) from: {Path(path).name}")

            QMessageBox.information(
                self, "Nova Drawing Import Complete",
                f"✓  {added_nova} element(s) imported.\n\n"
                f"Panel quantities read directly from the drawing — no optimization needed.\n\n"
                f"Casting height : {int(casting_h)} mm\n"
                f"Product panels : {int(panel_h)} mm\n\n"
                f"Go to Configuration tab → Generate BOQ to create the output."
            )

        # ── Detect Nova labelled-panel format and route to correct worker ────
        if path.lower().endswith('.dxf') and is_nova_drawing(path):
            self._dwg_worker = _NovaDrawingWorker(
                path, casting_h, panel_h, parent=self)
            self._dwg_worker.finished.connect(_on_nova_parse_done)
        else:
            self._dwg_worker = _DXFParserWorker(path, panel_h, casting_h, parent=self)
            self._dwg_worker.finished.connect(_on_parse_done)
        self._dwg_worker.start()

    def _run_optimization(self):
        if not self._elements:
            QMessageBox.warning(self, "No Elements",
                                "Please add at least one structural element first.")
            self.tabs.setCurrentIndex(1)  # Elements tab
            return

        panel_h = float(self.panel_height_combo.currentText())
        self._boqs = []

        for elem in self._elements:
            try:
                boq = compute_boq(elem, panel_h)
                self._boqs.append(boq)
            except Exception as ex:
                QMessageBox.critical(self, "Error",
                                     f"Error computing BOQ for {elem.label}: {ex}")
                return

        # Build project
        self._project = ProjectBOQ(
            project_name=self.project_name_edit.text().strip(),
            client_name=self.client_name_edit.text().strip(),
            client_address=self.client_addr_edit.text().strip(),
            ipo_no=self.ipo_edit.text().strip(),
            date=self.date_edit.text().strip(),
            element_boqs=self._boqs,
            panel_height_mm=panel_h,
            num_sets=self.num_sets_spin.value(),
            gst_enabled=self.gst_check.isChecked(),
            freight_amount=self.freight_spin.value(),
            panel_rate_per_sqm=self.rate_panel.value(),
        )

        self._agg = aggregate_project_boq(self._project)

        # Compute accessories
        self._acc_boqs = []
        for elem, boq in zip(self._elements, self._boqs):
            acc = calculate_accessories(elem, boq, panel_h)
            self._acc_boqs.append(acc)
        self._acc_agg = aggregate_accessories(self._acc_boqs, self.num_sets_spin.value())

        from src.auth.auth_manager import log_action as _log
        _log(self._user["username"], self._user["full_name"],
             "BOQ_COMPUTED",
             f"Project: {self._project.project_name} | "
             f"{len(self._boqs)} elements | "
             f"{self._agg.get('total_area_sqm', 0):.1f} sqm | "
             f"Panel: {panel_h:.0f}mm")

        self._refresh_boq_tables()

        # Feed latest data into AI assistant
        self.ai_widget.update_data(
            self._elements, self._boqs,
            self._agg, self._acc_agg, self._project
        )

        # Refresh 3D view with latest elements
        self.view_3d.load_elements(
            self._elements,
            bboxes=self._element_bboxes if self._element_bboxes else None,
            scale=1.0,
        )

        self.tabs.setCurrentIndex(5)  # Jump to BOQ Results tab

        n_warn = sum(1 for a in self._acc_boqs if a.high_wall_warning)
        msg = (f"BOQ generated for {len(self._elements)} element(s).\n"
               f"Total panel area: {self._agg['total_area_sqm']:.3f} sqm")
        if n_warn:
            msg += f"\n\n⚠ {n_warn} element(s) exceed 4500mm height — engineer review required!"
        QMessageBox.information(self, "Success", msg)

    def _regenerate_boq_if_elements_present(self):
        """
        Silently recomputes BOQ when panel height dropdown changes at runtime.
        Only fires if a BOQ has already been generated (self._boqs is non-empty).
        No dialogs or tab switches — tables update in place.
        """
        if not self._elements or not self._boqs:
            return
        panel_h = float(self.panel_height_combo.currentText())
        new_boqs = []
        for elem in self._elements:
            try:
                new_boqs.append(compute_boq(elem, panel_h))
            except Exception:
                return  # bail silently on any failure

        self._boqs = new_boqs
        self._project = ProjectBOQ(
            project_name      = self.project_name_edit.text().strip(),
            client_name       = self.client_name_edit.text().strip(),
            client_address    = self.client_addr_edit.text().strip(),
            ipo_no            = self.ipo_edit.text().strip(),
            date              = self.date_edit.text().strip(),
            element_boqs      = self._boqs,
            panel_height_mm   = panel_h,
            num_sets          = self.num_sets_spin.value(),
            gst_enabled       = self.gst_check.isChecked(),
            freight_amount    = self.freight_spin.value(),
            panel_rate_per_sqm= self.rate_panel.value(),
        )
        self._agg = aggregate_project_boq(self._project)
        self._acc_boqs = []
        for elem, boq in zip(self._elements, self._boqs):
            self._acc_boqs.append(calculate_accessories(elem, boq, panel_h))
        self._acc_agg = aggregate_accessories(
            self._acc_boqs, self.num_sets_spin.value())
        self._refresh_boq_tables()
        self.ai_widget.update_data(
            self._elements, self._boqs,
            self._agg, self._acc_agg, self._project)

    def _refresh_boq_tables(self):
        if not self._boqs or not self._agg:
            return

        NS_BG    = QColor("#FFF3E0")  # light orange — non-standard rows
        NS_FG    = QColor("#b84800")  # dark orange text
        OC_COLOR = QColor(NOVA_BLUE)

        # --- Detail table ---
        # Each entry: (col_values, is_nonstandard, is_oc)
        rows = []
        ns_elem_labels: list[str] = []

        for eboq in self._boqs:
            elem_lbl = (
                f"{eboq.element.label} ({eboq.element.element_type.value})\n"
                f"{eboq.element.length_mm:.0f}×{eboq.element.width_mm:.0f}mm\n"
                f"H={eboq.element.height_mm:.0f}  Qty={eboq.element.quantity}"
            )
            # Flag this element if ANY of its panels is non-standard
            if any(not is_catalog_panel(p) for p in eboq.panels):
                if eboq.element.label not in ns_elem_labels:
                    ns_elem_labels.append(eboq.element.label)

            for i, p in enumerate(eboq.panels):
                is_ns    = not is_catalog_panel(p)
                warn_txt = "; ".join(eboq.warnings) if i == 0 else ""
                if is_ns:
                    ns_note  = "⚠ Not in Nova catalog"
                    warn_txt = f"{ns_note}; {warn_txt}" if warn_txt else ns_note
                rows.append((
                    [elem_lbl if i == 0 else "",
                     p.size_label, str(p.quantity),
                     f"{p.area_sqm:.4f}", f"{p.total_area_sqm:.4f}",
                     warn_txt],
                    is_ns,
                    p.is_corner,
                ))

        self.boq_detail_table.setRowCount(len(rows))
        for r, (row, is_ns, is_oc) in enumerate(rows):
            for c, val in enumerate(row):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if is_ns:
                    item.setBackground(NS_BG)
                    if c in (1, 5):
                        item.setForeground(NS_FG)
                        item.setFont(QFont("Helvetica Neue", 10, QFont.Weight.Bold))
                else:
                    if c == 5 and val:
                        item.setForeground(QColor(WARN_ORANGE))
                        item.setFont(QFont("Helvetica Neue", 9, QFont.Weight.Bold))
                    if c == 1 and is_oc:
                        item.setForeground(OC_COLOR)
                        item.setFont(QFont("Helvetica Neue", 10, QFont.Weight.Bold))
                self.boq_detail_table.setItem(r, c, item)

        # --- Summary table ---
        from src.engine.panel_optimizer import _CATALOG_HEIGHTS_SET
        summary = self._agg['summary_panels']
        rate    = self._agg['rate_per_sqm']
        self.boq_summary_table.setRowCount(len(summary))
        for r, (key, d) in enumerate(summary.items()):
            # Detect non-standard height from label key like "Panel 600*3000"
            ns_row = False
            try:
                ns_row = int(key.split('*')[1].strip()) not in _CATALOG_HEIGHTS_SET
            except Exception:
                pass
            amount = d['area_sqm'] * rate
            vals = [
                ("⚠ " + key) if ns_row else key,
                f"{d['unit_area_sqm']:.4f}",
                str(d['quantity']),
                f"{d['area_sqm']:.4f}",
                f"₹{amount:,.2f}" if rate else "—",
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if ns_row:
                    item.setBackground(NS_BG)
                    if c == 0:
                        item.setForeground(NS_FG)
                        item.setFont(QFont("Helvetica Neue", 10, QFont.Weight.Bold))
                else:
                    if c == 0 and ('OC' in key or 'IC' in key):
                        item.setForeground(OC_COLOR)
                        item.setFont(QFont("Helvetica Neue", 10, QFont.Weight.Bold))
                self.boq_summary_table.setItem(r, c, item)

        # --- Non-standard banner ---
        total_ns = sum(1 for _, is_ns, _ in rows if is_ns)
        if total_ns:
            labels_str = ", ".join(ns_elem_labels[:5])
            if len(ns_elem_labels) > 5:
                labels_str += f" +{len(ns_elem_labels) - 5} more"
            self.nonstandard_banner.setText(
                f"⚠  {total_ns} NON-STANDARD panel size(s) found — highlighted in orange.  "
                f"Affected elements: {labels_str}\n"
                f"Standard heights are 3705 / 2470 / 1235 mm only.  "
                f"Fix: change Panel Height in Configuration tab to a standard size and Re-run BOQ.  "
                f"Or use Elements tab → Edit to adjust individual element dimensions."
            )
            self.nonstandard_banner.setVisible(True)
            self._ns_edit_btn.setVisible(True)
        else:
            self.nonstandard_banner.setVisible(False)
            self._ns_edit_btn.setVisible(False)

        # --- Cost summary ---
        agg = self._agg
        cost_txt = (
            f"  Total Area: {agg['total_area_sqm']:.3f} sqm  |  "
            f"Sets: {agg['num_sets']}  |  "
            f"Panel Cost: ₹{agg['total_panel_cost']:,.2f}  |  "
            f"GST: ₹{agg['gst_amount']:,.2f}  |  "
            f"Freight: ₹{agg['freight_amount']:,.2f}  |  "
            f"GRAND TOTAL: ₹{agg['grand_total']:,.2f}"
        )
        self.cost_label.setText(cost_txt)

        # --- Accessories table ---
        if self._acc_agg:
            self.acc_table.setRowCount(len(self._acc_agg))
            warnings = []
            for r, (key, d) in enumerate(self._acc_agg.items()):
                rm = f"{d['total_length_m']:.1f} m" if d['total_length_m'] > 0 else "—"
                lm = f"{d['length_m']:.1f} m" if d['length_m'] > 0 else "—"
                vals = [key, str(int(d['quantity'])), lm, rm]
                for c, v in enumerate(vals):
                    item = QTableWidgetItem(v)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if c == 0:
                        item.setFont(QFont("Helvetica Neue", 10, QFont.Weight.Bold))
                    self.acc_table.setItem(r, c, item)

            # Collect high-wall warnings
            for acc_boq in self._acc_boqs:
                if acc_boq.high_wall_warning:
                    warnings.append(
                        f"⚠ {acc_boq.element.label}: Height {acc_boq.element.height_mm}mm > 4500mm"
                    )
            self.acc_warn_label.setText("\n".join(warnings) if warnings else "")

    def _export_pdf(self):
        if not self._project or not self._boqs:
            QMessageBox.warning(self, "No Data",
                                "Please run optimization first (Configuration tab).")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save BOQ PDF", "", "PDF Files (*.pdf)")
        if not path:
            return

        try:
            boq_no = self.boq_number_edit.text().strip() or None
            out = generate_boq_pdf(self._project, path,
                                   acc_agg=self._acc_agg, boq_number=boq_no)
            self.export_log.append(f"✓ BOQ PDF saved: {out}")
            from src.auth.auth_manager import log_action as _log
            _log(self._user["username"], self._user["full_name"],
                 "PDF_EXPORTED", f"BOQ PDF: {Path(path).name}")
            QMessageBox.information(self, "Export Success",
                                    f"BOQ PDF saved successfully:\n{path}")
        except Exception as ex:
            self.export_log.append(f"✗ BOQ PDF error: {ex}")
            QMessageBox.critical(self, "Export Error", str(ex))

    def _export_quotation_pdf(self):
        if not self._project or not self._boqs:
            QMessageBox.warning(self, "No Data",
                                "Please run optimization first (Configuration tab).")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Quotation PDF", "", "PDF Files (*.pdf)")
        if not path:
            return

        try:
            qtn_no = self.qtn_number_edit.text().strip() or None
            out = generate_quotation_pdf(
                self._project, path,
                acc_agg=self._acc_agg,
                qtn_number=qtn_no,
                price_per_sqm=self._project.panel_rate_per_sqm,
                freight=self._project.freight_amount,
                gst_rate=0.18 if self._project.gst_enabled else 0.0,
            )
            self.export_log.append(f"✓ Quotation PDF saved: {out}")
            from src.auth.auth_manager import log_action as _log
            _log(self._user["username"], self._user["full_name"],
                 "PDF_EXPORTED", f"Quotation PDF: {Path(path).name}")
            QMessageBox.information(self, "Export Success",
                                    f"Quotation PDF saved successfully:\n{path}")
        except Exception as ex:
            self.export_log.append(f"✗ Quotation PDF error: {ex}")
            QMessageBox.critical(self, "Export Error", str(ex))

    def _export_excel(self):
        if not self._project or not self._boqs:
            QMessageBox.warning(self, "No Data",
                                "Please run optimization first (Configuration tab).")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Excel BOQ", "", "Excel Files (*.xlsx)")
        if not path:
            return

        try:
            boq_no = self.boq_number_edit.text().strip() or None
            qtn_no = self.qtn_number_edit.text().strip() or None
            out = generate_excel_boq(
                self._project,
                path,
                price_per_sqm=self._project.panel_rate_per_sqm,
                freight_amount=self._project.freight_amount,
                gst_rate=0.18 if self._project.gst_enabled else 0.0,
                acc_agg=self._acc_agg,
                boq_number=boq_no,
                qtn_number=qtn_no,
            )
            self.export_log.append(f"✓ Excel saved: {out}")
            from src.auth.auth_manager import log_action as _log
            _log(self._user["username"], self._user["full_name"],
                 "EXCEL_EXPORTED", f"Excel BOQ: {Path(path).name}")
            QMessageBox.information(self, "Export Success",
                                    f"Excel BOQ saved successfully:\n{path}")
        except Exception as ex:
            self.export_log.append(f"✗ Excel error: {ex}")
            QMessageBox.critical(self, "Export Error", str(ex))

    # -------------------------------------------------------
    # Layout Drawing
    # -------------------------------------------------------

    def _view_layout_selected(self):
        """Show 3D panel assembly dialog for the currently selected element."""
        if not self._elements or not self._boqs:
            QMessageBox.warning(self, "No BOQ",
                                "Please run optimization first (Configuration tab).")
            return

        row = self.elem_table.currentRow()
        if row < 0 or row >= len(self._elements):
            row = 0

        element = self._elements[row]
        boq     = self._boqs[row]
        panel_h = float(self.panel_height_combo.currentText())

        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            fig = generate_element_layout_3d_figure(
                element, boq, panel_h, acc_agg=self._acc_agg
            )
        except Exception as ex:
            self.unsetCursor()
            QMessageBox.critical(self, "Layout Error", str(ex))
            return
        self.unsetCursor()

        self._show_3d_layout_dialog(fig, element.label)

    def _show_3d_layout_dialog(self, fig, title: str):
        """Open a resizable dialog with the interactive 3D panel assembly figure."""
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from src.ui.mpl_toolbar import NovoToolbar as NavigationToolbar2QT
        except ImportError:
            QMessageBox.warning(self, "Unavailable",
                                "matplotlib Qt backend not available.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"3D Panel Assembly — {title}")
        dlg.resize(1200, 720)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(4, 4, 4, 4)

        canvas  = FigureCanvasQTAgg(fig)
        toolbar = NavigationToolbar2QT(canvas, dlg)
        toolbar.setStyleSheet(
            "QToolBar{background:#1a3a5c;border:none;padding:2px;spacing:4px;}"
            "QToolButton{background:#2c5f8a;color:white;border-radius:3px;"
            "padding:3px 7px;font-size:11px;}"
            "QToolButton:hover{background:#3a7ab0;}"
        )

        tip = QLabel(
            "  Drag to rotate  ·  Right-drag to pan  ·  Scroll to zoom  ·  "
            "Use toolbar to reset view"
        )
        tip.setStyleSheet(
            f"background:{NOVA_LIGHT}; color:{NOVA_BLUE}; "
            f"font-size:10px; padding:4px 10px;"
        )

        layout.addWidget(toolbar)
        layout.addWidget(canvas, stretch=1)
        layout.addWidget(tip)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        dlg.exec()

    def _show_layout_dialog(self, png_path: str, title: str):
        """Open a resizable dialog showing the layout PNG."""
        from PyQt6.QtWidgets import QScrollArea
        from PyQt6.QtGui import QPixmap

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Panel Layout — {title}")
        dlg.resize(1050, 520)

        layout = QVBoxLayout(dlg)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        img_label = QLabel()
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        px = QPixmap(png_path)
        img_label.setPixmap(px)
        scroll.setWidget(img_label)
        layout.addWidget(scroll)

        note = QLabel(
            "Schematic layout — dimensions are proportional to actual panel widths. "
            "Verify all sizes with the BOQ table before ordering."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #e67e22; font-size: 10px; padding: 4px;")
        layout.addWidget(note)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        dlg.exec()

    def _export_layout_pdf(self):
        """Export panel layout drawings for all elements as a multi-page PDF."""
        if not self._elements or not self._boqs:
            QMessageBox.warning(self, "No BOQ",
                                "Please run optimization first (Configuration tab).")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Layout PDF", "", "PDF Files (*.pdf)")
        if not path:
            return

        panel_h = float(self.panel_height_combo.currentText())

        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            out = generate_project_layout(
                self._elements, self._boqs, panel_h,
                output_path=path, acc_agg=self._acc_agg
            )
            self.unsetCursor()
            self.export_log.append(f"✓ Layout PDF saved: {out}")
            QMessageBox.information(self, "Export Success",
                                    f"Layout PDF saved:\n{path}\n\n"
                                    f"{len(self._elements)} element(s) included.")
        except Exception as ex:
            self.unsetCursor()
            self.export_log.append(f"✗ Layout PDF error: {ex}")
            QMessageBox.critical(self, "Export Error", str(ex))

    def _export_drawing_dxf(self):
        """Export a complete formwork drawing as AutoCAD DXF."""
        if not self._elements or not self._boqs:
            QMessageBox.warning(self, "No Elements",
                                "Please import a drawing and run optimization first.")
            return

        # ── Step 1: Let user arrange element order ────────────────────────────
        arrange_dlg = DXFArrangeDialog(self._elements, self._boqs, self)
        if arrange_dlg.exec() != QDialog.DialogCode.Accepted:
            return
        ordered_elements = arrange_dlg.get_ordered_elements()
        ordered_boqs = arrange_dlg.get_ordered_boqs()

        # ── Step 2: File save dialog ──────────────────────────────────────────
        proj_name = getattr(self, '_project_name_edit', None)
        proj_name_str = proj_name.text().strip() if proj_name else "Nova Project"

        default_name = f"{proj_name_str.replace(' ','_')}_Formwork.dxf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Formwork Drawing DXF", default_name,
            "AutoCAD DXF (*.dxf)"
        )
        if not path:
            return
        if not path.lower().endswith('.dxf'):
            path += '.dxf'

        panel_h = float(self.panel_height_combo.currentText())

        # Build ProjectBOQ for title block
        try:
            pname_edit = getattr(self, 'project_name_edit', None)
            cname_edit = getattr(self, 'client_name_edit', None)
            from src.models.element import ProjectBOQ as _PBOQ
            proj = _PBOQ(
                project_name=pname_edit.text().strip() if pname_edit else "Nova Project",
                client_name=cname_edit.text().strip() if cname_edit else "",
                client_address="",
                date=date.today().strftime("%d-%m-%Y"),
                element_boqs=self._boqs,
                panel_height_mm=panel_h,
                num_sets=1,
            )
        except Exception:
            from src.models.element import ProjectBOQ as _PBOQ
            proj = _PBOQ(
                project_name="Nova Project", client_name="",
                client_address="", date=date.today().strftime("%d-%m-%Y"),
                element_boqs=self._boqs, panel_height_mm=panel_h, num_sets=1,
            )

        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            out = generate_formwork_dxf(
                ordered_elements, ordered_boqs, proj, panel_h, path
            )
            self.unsetCursor()
            self.export_log.append(f"✓ Formwork DXF saved: {out}")
            msg = QMessageBox(self)
            msg.setWindowTitle("DXF Export Success")
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setText(
                f"Formwork drawing saved:\n{path}\n\n"
                f"{len(self._elements)} element(s)  |  Panel H = {panel_h:.0f}mm\n\n"
                "Open in AutoCAD, FreeCAD, or any DXF viewer.\n"
                "Recommended print scale: 1:20"
            )
            msg.exec()
        except Exception as ex:
            self.unsetCursor()
            self.export_log.append(f"✗ DXF export error: {ex}")
            QMessageBox.critical(self, "DXF Export Error",
                                 f"Could not generate DXF:\n{str(ex)}")
