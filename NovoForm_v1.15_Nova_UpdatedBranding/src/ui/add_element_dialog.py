"""
Add / Edit Element Dialog.
Allows users to manually add structural elements not detected in the drawing,
or edit an existing detected element's properties.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QSpinBox, QLabel,
    QPushButton, QDialogButtonBox, QGroupBox, QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from src.models.element import StructuralElement, ElementType


class AddElementDialog(QDialog):
    """
    Form to manually add a structural element (column or wall) to the project.
    Can also be used to edit an existing element.
    """

    def __init__(self, parent=None, edit_element: StructuralElement = None):
        super().__init__(parent)
        self._edit = edit_element
        mode = "Edit Element" if edit_element else "Add Missing Element"
        self.setWindowTitle(mode)
        self.setMinimumWidth(420)
        self.setModal(True)
        self._build_ui()
        if edit_element:
            self._populate(edit_element)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        hdr = QLabel("Fill in the element details below.\n"
                      "Use this for elements not detected in the drawing.")
        hdr.setWordWrap(True)
        hdr.setStyleSheet("color:#555; font-size:12px;")
        layout.addWidget(hdr)

        frame = QGroupBox("Element Properties")
        form = QFormLayout(frame)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setVerticalSpacing(8)
        layout.addWidget(frame)

        # Label
        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("e.g. C1, W2, SW3")
        self._label_edit.setMaxLength(20)
        form.addRow("Element Label *", self._label_edit)

        # Type
        self._type_combo = QComboBox()
        self._type_combo.addItem("Column", ElementType.COLUMN)
        self._type_combo.addItem("Wall", ElementType.WALL)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Element Type *", self._type_combo)

        # Length
        self._length_spin = QSpinBox()
        self._length_spin.setRange(100, 50000)
        self._length_spin.setSingleStep(50)
        self._length_spin.setSuffix(" mm")
        self._length_spin.setValue(900)
        self._length_spin.setToolTip("For column: concrete length. For wall: wall length.")
        form.addRow("Length *", self._length_spin)

        # Width / Thickness
        self._width_lbl = QLabel("Width *")
        self._width_spin = QSpinBox()
        self._width_spin.setRange(100, 5000)
        self._width_spin.setSingleStep(50)
        self._width_spin.setSuffix(" mm")
        self._width_spin.setValue(600)
        self._width_spin.setToolTip("For column: concrete width. For wall: wall thickness.")
        form.addRow(self._width_lbl, self._width_spin)

        # Height hint
        self._height_note = QLabel()
        self._height_note.setStyleSheet("color:#777; font-size:11px; font-style:italic;")
        form.addRow("", self._height_note)

        # Quantity
        self._qty_spin = QSpinBox()
        self._qty_spin.setRange(1, 500)
        self._qty_spin.setValue(1)
        self._qty_spin.setSuffix("  nos")
        form.addRow("Quantity *", self._qty_spin)

        # Floor label
        self._floor_edit = QLineEdit()
        self._floor_edit.setPlaceholderText("e.g. GF, 1st, B1 (optional)")
        self._floor_edit.setMaxLength(20)
        form.addRow("Floor / Level", self._floor_edit)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._validate_and_accept)
        btns.rejected.connect(self.reject)
        ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Add Element" if not self._edit else "Save Changes")
        ok_btn.setStyleSheet(
            "background:#1a3a5c; color:white; border-radius:4px; padding:6px 16px; font-weight:bold;"
        )
        layout.addWidget(btns)

        self._on_type_changed()

    def _on_type_changed(self):
        is_wall = self._type_combo.currentData() == ElementType.WALL
        self._width_lbl.setText("Wall Thickness *" if is_wall else "Width *")
        self._width_spin.setToolTip(
            "Wall thickness (e.g. 200, 230mm)" if is_wall
            else "Column cross-section width"
        )
        if is_wall:
            self._width_spin.setRange(100, 1000)
            if self._width_spin.value() > 500:
                self._width_spin.setValue(230)
            self._height_note.setText(
                "Height = panel height setting (set in Import / BOQ tab)"
            )
        else:
            self._width_spin.setRange(100, 5000)
            self._height_note.setText(
                "Height = casting height (set in Import screen)"
            )

    def _populate(self, elem: StructuralElement):
        self._label_edit.setText(elem.label)
        idx = 0 if elem.element_type == ElementType.COLUMN else 1
        self._type_combo.setCurrentIndex(idx)
        self._length_spin.setValue(int(elem.length_mm))
        self._width_spin.setValue(int(elem.width_mm))
        self._qty_spin.setValue(elem.quantity)
        if elem.floor_label:
            self._floor_edit.setText(elem.floor_label)

    def _validate_and_accept(self):
        label = self._label_edit.text().strip()
        if not label:
            self._label_edit.setFocus()
            self._label_edit.setStyleSheet("border:1.5px solid #c0392b;")
            return
        self.accept()

    # ── Result ────────────────────────────────────────────────────────────────

    def get_element(self, casting_height_mm: float = 3200.0) -> StructuralElement:
        """Return a StructuralElement from the form values."""
        etype = self._type_combo.currentData()
        return StructuralElement(
            label=self._label_edit.text().strip().upper(),
            element_type=etype,
            length_mm=float(self._length_spin.value()),
            width_mm=float(self._width_spin.value()),
            height_mm=casting_height_mm,
            quantity=self._qty_spin.value(),
            floor_label=self._floor_edit.text().strip() or None,
        )
