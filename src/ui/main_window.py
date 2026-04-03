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
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon, QPixmap

from src.models.element import (
    StructuralElement, ElementType, JunctionType, ProjectBOQ, ElementBOQ
)
from src.engine.panel_optimizer import compute_boq
from src.output.boq_generator import aggregate_project_boq
from src.output.pdf_generator import generate_pdf
from src.output.excel_generator import generate_excel_boq
from src.parsers.dwg_parser import (
    parse_dwg, parse_dxf, get_conversion_status, dwg_to_dxf
)
from src.engine.accessories_calc import (
    calculate_accessories, aggregate_accessories
)
from src.output.layout_drawing import generate_element_layout, generate_project_layout

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
            "Box Culvert", "Drain", "Monolithic"
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
    """
    def __init__(self, elements: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review Detected Elements from Drawing")
        self.resize(800, 500)
        self._elements = list(elements)

        layout = QVBoxLayout(self)

        info = QLabel(
            f"<b>{len(elements)} element(s) detected.</b>  "
            "Please review dimensions — auto-detection may not be 100% accurate. "
            "Edit any incorrect values before confirming."
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

        type_options = ["Column", "Wall", "Shear Wall"]

        for i, e in enumerate(elements):
            # Checkbox column
            chk = QTableWidgetItem()
            chk.setCheckState(Qt.CheckState.Checked)
            chk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(i, 0, chk)

            # Label (editable)
            self.table.setItem(i, 1, QTableWidgetItem(e.label))

            # Type (combo)
            combo = QComboBox()
            combo.addItems(type_options)
            combo.setCurrentText(e.element_type.value)
            self.table.setCellWidget(i, 2, combo)

            # Dimensions (editable)
            self.table.setItem(i, 3, QTableWidgetItem(str(int(e.length_mm))))
            self.table.setItem(i, 4, QTableWidgetItem(str(int(e.width_mm))))
            self.table.setItem(i, 5, QTableWidgetItem(str(int(e.height_mm))))
            self.table.setItem(i, 6, QTableWidgetItem(str(e.quantity)))

        layout.addWidget(self.table)

        note = QLabel(
            "⚠  Dimensions shown are auto-measured from drawing geometry. "
            "Always cross-check against drawing annotations."
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


# ---------- Main Window ----------

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NovoForm — Formwork Analysis & BOQ Generator")
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

        self.tabs.addTab(self._tab_project(), "  Project Info  ")
        self.tabs.addTab(self._tab_elements(), "  Elements  ")
        self.tabs.addTab(self._tab_config(), "  Configuration  ")
        self.tabs.addTab(self._tab_boq(), "  BOQ Results  ")
        self.tabs.addTab(self._tab_export(), "  Export  ")

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

        version = QLabel("Phase 2  v2.0")
        version.setStyleSheet("color: #7aabcc; background: transparent; font-size: 10px;")
        lay.addWidget(version)

        return frame

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
    # TAB 3: Configuration
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
        self.panel_height_combo.addItems(["3200", "2470", "1228", "900", "600"])
        self.panel_height_combo.setCurrentText("3200")
        f1.addRow("Panel Height (mm):", self.panel_height_combo)

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
        acc_lay.addWidget(QLabel("B — Accessories Summary (Estimated — verify with engineer):"))

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

        btn_pdf = QPushButton("  Export PDF Quotation")
        btn_pdf.setStyleSheet(BTN_STYLE)
        btn_pdf.setMinimumHeight(38)
        btn_pdf.clicked.connect(self._export_pdf)
        g.addWidget(btn_pdf)

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

    def _import_dwg(self):
        path = self.dwg_path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "No File", "Please select a DWG or DXF file first.")
            return

        # Get casting height from config tab
        panel_h = float(self.panel_height_combo.currentText())

        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            if path.lower().endswith('.dxf'):
                from src.parsers.dwg_parser import parse_dxf
                detected = parse_dxf(path, panel_h)
                err = None
            else:
                detected, err = parse_dwg(path, panel_h)
        except Exception as ex:
            detected, err = [], str(ex)
        finally:
            self.unsetCursor()

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

        # Show review dialog
        dlg = DWGReviewDialog(detected, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            confirmed = dlg.get_confirmed_elements()
            added = 0
            for elem in confirmed:
                # Check for duplicate labels
                existing_labels = [e.label for e in self._elements]
                if elem.label in existing_labels:
                    elem.label = elem.label + "_dwg"
                self._elements.append(elem)
                added += 1
            self._refresh_element_table()
            QMessageBox.information(
                self, "Import Complete",
                f"{added} element(s) imported from drawing.\n"
                f"Please review dimensions before running optimization."
            )

    def _run_optimization(self):
        if not self._elements:
            QMessageBox.warning(self, "No Elements",
                                "Please add at least one structural element first.")
            self.tabs.setCurrentIndex(1)
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

        self._refresh_boq_tables()
        self.tabs.setCurrentIndex(3)  # Jump to BOQ tab

        n_warn = sum(1 for a in self._acc_boqs if a.high_wall_warning)
        msg = (f"BOQ generated for {len(self._elements)} element(s).\n"
               f"Total panel area: {self._agg['total_area_sqm']:.3f} sqm")
        if n_warn:
            msg += f"\n\n⚠ {n_warn} element(s) exceed 4500mm height — engineer review required!"
        QMessageBox.information(self, "Success", msg)

    def _refresh_boq_tables(self):
        if not self._boqs or not self._agg:
            return

        # --- Detail table ---
        rows = []
        for eboq in self._boqs:
            elem_lbl = f"{eboq.element.label} ({eboq.element.element_type.value})\n" \
                       f"{eboq.element.length_mm:.0f}×{eboq.element.width_mm:.0f}mm\n" \
                       f"H={eboq.element.height_mm:.0f}  Qty={eboq.element.quantity}"
            for i, p in enumerate(eboq.panels):
                warn_txt = "; ".join(eboq.warnings) if i == 0 else ""
                rows.append([
                    elem_lbl if i == 0 else "",
                    p.size_label,
                    str(p.quantity),
                    f"{p.area_sqm:.4f}",
                    f"{p.total_area_sqm:.4f}",
                    warn_txt,
                ])

        self.boq_detail_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 5 and val:  # warning col
                    item.setForeground(QColor(WARN_ORANGE))
                    item.setFont(QFont("Helvetica Neue", 9, QFont.Weight.Bold))
                if c == 1 and 'OC' in val:
                    item.setForeground(QColor(NOVA_BLUE))
                    item.setFont(QFont("Helvetica Neue", 10, QFont.Weight.Bold))
                self.boq_detail_table.setItem(r, c, item)

        # --- Summary table ---
        summary = self._agg['summary_panels']
        rate = self._agg['rate_per_sqm']
        self.boq_summary_table.setRowCount(len(summary))
        for r, (key, d) in enumerate(summary.items()):
            amount = d['area_sqm'] * rate
            vals = [
                key,
                f"{d['unit_area_sqm']:.4f}",
                str(d['quantity']),
                f"{d['area_sqm']:.4f}",
                f"₹{amount:,.2f}" if rate else "—",
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 0 and ('OC' in key or 'IC' in key):
                    item.setForeground(QColor(NOVA_BLUE))
                    item.setFont(QFont("Helvetica Neue", 10, QFont.Weight.Bold))
                self.boq_summary_table.setItem(r, c, item)

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
            self, "Save PDF Quotation", "", "PDF Files (*.pdf)")
        if not path:
            return

        try:
            panel_h = float(self.panel_height_combo.currentText())
            out = generate_pdf(self._project, panel_h, path, acc_agg=self._acc_agg)
            self.export_log.append(f"✓ PDF saved: {out}")
            QMessageBox.information(self, "Export Success",
                                    f"PDF saved successfully:\n{path}")
        except Exception as ex:
            self.export_log.append(f"✗ PDF error: {ex}")
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
            out = generate_excel_boq(
                self._project,
                path,
                price_per_sqm=self._project.panel_rate_per_sqm,
                freight_amount=self._project.freight_amount,
                gst_rate=0.18 if self._project.gst_enabled else 0.0,
            )
            self.export_log.append(f"✓ Excel saved: {out}")
            QMessageBox.information(self, "Export Success",
                                    f"Excel BOQ saved successfully:\n{path}")
        except Exception as ex:
            self.export_log.append(f"✗ Excel error: {ex}")
            QMessageBox.critical(self, "Export Error", str(ex))

    # -------------------------------------------------------
    # Layout Drawing
    # -------------------------------------------------------

    def _view_layout_selected(self):
        """Show panel layout drawing for the currently selected element (or first)."""
        if not self._elements or not self._boqs:
            QMessageBox.warning(self, "No BOQ",
                                "Please run optimization first (Configuration tab).")
            return

        # Prefer the element selected in elem_table; fall back to first
        row = self.elem_table.currentRow()
        if row < 0 or row >= len(self._elements):
            row = 0

        element = self._elements[row]
        boq = self._boqs[row]
        panel_h = float(self.panel_height_combo.currentText())

        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            png_path = generate_element_layout(
                element, boq, panel_h, acc_agg=self._acc_agg
            )
        except Exception as ex:
            self.unsetCursor()
            QMessageBox.critical(self, "Layout Error", str(ex))
            return
        self.unsetCursor()

        self._show_layout_dialog(png_path, element.label)

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
