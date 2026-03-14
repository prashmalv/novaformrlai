"""
Excel BOQ Generator — matches Nova Formworks COLUMN sheet format.
"""
from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Optional

import openpyxl
from openpyxl.styles import (
    Alignment, Border, Font, PatternFill, Side
)
from openpyxl.utils import get_column_letter

from src.models.element import ElementBOQ, ProjectBOQ


# ── colour palette (matches Nova Excel look) ─────────────────────────────────
_NOVA_BLUE   = "1F4E79"   # dark header bg
_NOVA_HEADER = "BDD7EE"   # light blue column header bg
_OC_FILL     = "FFE699"   # light amber for OC/IC rows
_ALT_FILL    = "F2F2F2"   # every-other-row light grey
_BORDER_CLR  = "BFBFBF"

_thin  = Side(style="thin",   color=_BORDER_CLR)
_thick = Side(style="medium", color="000000")

def _border(t=False, b=False, l=False, r=False) -> Border:
    return Border(
        top    = _thick if t else (_thin if t is not None else None),
        bottom = _thick if b else (_thin if b is not None else None),
        left   = _thick if l else (_thin if l is not None else None),
        right  = _thick if r else (_thin if r is not None else None),
    )


# ── helpers ───────────────────────────────────────────────────────────────────

def _hdr_cell(ws, row, col, value, bold=True, bg=_NOVA_HEADER, align="center"):
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = Font(bold=bold, color="000000" if bg != _NOVA_BLUE else "FFFFFF")
    cell.fill = PatternFill("solid", fgColor=bg)
    cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=True)
    return cell


def _data_cell(ws, row, col, value, bold=False, fill=None, align="center", number_fmt=None):
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = Font(bold=bold)
    if fill:
        cell.fill = PatternFill("solid", fgColor=fill)
    cell.alignment = Alignment(horizontal=align, vertical="center")
    if number_fmt:
        cell.number_format = number_fmt
    return cell


# ── main public function ──────────────────────────────────────────────────────

def generate_excel_boq(
    project: ProjectBOQ,
    output_path: str,
    price_per_sqm: float = 0.0,
    freight_amount: float = 0.0,
    gst_rate: float = 0.18,
) -> str:
    """
    Generate Excel BOQ in Nova Formworks COLUMN sheet format.
    Returns the saved file path.
    """
    wb = openpyxl.Workbook()

    # Remove default sheet, create "COLUMN" sheet
    wb.remove(wb.active)
    ws = wb.create_sheet("COLUMN")

    row = _write_header(ws, project)
    row = _write_element_blocks(ws, row, project)
    row = _write_summary(ws, row, project, price_per_sqm, freight_amount, gst_rate)

    _set_column_widths(ws)

    wb.save(output_path)
    return output_path


# ── header section (rows 1-9) ─────────────────────────────────────────────────

def _write_header(ws, project: ProjectBOQ) -> int:
    """Write Nova Formworks company header. Returns next free row."""

    # Row 1: title
    ws.merge_cells("B1:F1")
    c = ws["B1"]
    c.value = "QUOTATION"
    c.font = Font(bold=True, size=14, color="FFFFFF")
    c.fill = PatternFill("solid", fgColor=_NOVA_BLUE)
    c.alignment = Alignment(horizontal="center", vertical="center")

    # Rows 2-5: company info
    info_lines = [
        "M/S.NOVA FORMWORKS PVT LTD",
        "Address - A-7/121-124 South Side of GT Road Indl.Area Ghaziabad (UP)",
        "Email : info@novaformworks.com",
        "Mob - +91-93 10 69 54 40",
    ]
    for i, line in enumerate(info_lines, start=2):
        ws.merge_cells(f"B{i}:F{i}")
        c = ws[f"B{i}"]
        c.value = line
        c.font = Font(bold=(i == 2))
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 18

    # Rows 6-8: client info
    date_str = project.date or datetime.date.today().strftime("%d-%m-%Y")
    ws["B6"] = f"M/S. {project.client_name}"
    ws["G6"] = f"IPO NO - {project.ipo_no or ''}"
    ws["B7"] = project.client_address or ""
    ws["G7"] = f"DATE - {date_str}"
    ws["B8"] = "India"
    ws["G8"] = f"HEIGHT - {int(project.panel_height_mm)}MM"

    for r in range(6, 9):
        ws[f"B{r}"].font = Font(bold=True)
        ws[f"G{r}"].font = Font(bold=False)

    # Row 9: big title
    ws.merge_cells("B9:F9")
    c = ws["B9"]
    c.value = "COLUMN & SHEAR WALL QUOTATION"
    c.font = Font(bold=True, size=12, color="FFFFFF")
    c.fill = PatternFill("solid", fgColor=_NOVA_BLUE)
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[9].height = 20

    # Row 10: column headers
    headers = {2: "SIZE", 3: "PANELS REQUIRED", 4: "NO OF PANELS",
               5: "NO OF SETS", 6: "HEIGHT", 7: "IMAGE"}
    for col, label in headers.items():
        _hdr_cell(ws, 10, col, label, bg=_NOVA_HEADER)
    ws.row_dimensions[10].height = 30

    return 11


# ── element blocks ─────────────────────────────────────────────────────────────

def _write_element_blocks(ws, start_row: int, project: ProjectBOQ) -> int:
    """Write one block per element BOQ. Returns next free row."""
    row = start_row

    for boq in project.element_boqs:
        el = boq.element
        size_label = f"{int(el.length_mm)}X{int(el.width_mm)}"
        ph = int(boq.panels[0].height_mm) if boq.panels else int(project.panel_height_mm)
        height_str = boq.height_note or f"{ph}MM"

        first_row = row
        sets_written = False

        for idx, panel in enumerate(boq.panels):
            is_corner = panel.is_corner or panel.is_inner_corner
            fill = _OC_FILL if is_corner else None

            if idx == 0:
                # First panel row carries the SIZE label
                _data_cell(ws, row, 2, f"{el.label}", bold=True, align="left")
                _data_cell(ws, row, 3, panel.size_label, fill=fill, bold=is_corner)
                _data_cell(ws, row, 4, panel.quantity, fill=fill)
                _data_cell(ws, row, 5, boq.num_sets)   # NO OF SETS
                _data_cell(ws, row, 6, height_str)
            else:
                _data_cell(ws, row, 2, size_label if idx == 1 else None, align="right")
                _data_cell(ws, row, 3, panel.size_label, fill=fill, bold=is_corner)
                _data_cell(ws, row, 4, panel.quantity, fill=fill)

            row += 1

        # blank separator row
        row += 1

    return row


# ── summary / BOQ table ───────────────────────────────────────────────────────

def _write_summary(
    ws,
    start_row: int,
    project: ProjectBOQ,
    price_per_sqm: float,
    freight_amount: float,
    gst_rate: float,
) -> int:
    """Write aggregated panel summary + cost table. Returns next free row."""
    row = start_row

    # "TOTAL SET" marker
    ws.merge_cells(f"B{row}:F{row}")
    c = ws[f"B{row}"]
    c.value = "TOTAL SET"
    c.font = Font(bold=True)
    c.fill = PatternFill("solid", fgColor=_NOVA_BLUE)
    c.font = Font(bold=True, color="FFFFFF")
    c.alignment = Alignment(horizontal="center")
    row += 2

    # Section header
    ws.merge_cells(f"B{row}:G{row}")
    c = ws[f"B{row}"]
    c.value = "A - Formwork BOQ Details"
    c.font = Font(bold=True, size=11)
    c.fill = PatternFill("solid", fgColor=_NOVA_HEADER)
    c.alignment = Alignment(horizontal="left")
    row += 1

    # Table column headers
    tbl_hdrs = {2: "PANEL SIZE", 3: "NOS", 4: "PER PANEL AREA (sqm)",
                5: "TOTAL AREA (sqm)", 6: "PRICE PER SQM (₹)", 7: "AMOUNT (₹)"}
    for col, label in tbl_hdrs.items():
        _hdr_cell(ws, row, col, label, bg=_NOVA_HEADER)
    ws.row_dimensions[row].height = 28
    tbl_start = row + 1
    row += 1

    # Aggregate panel counts across all element BOQs
    totals: dict[str, dict] = defaultdict(lambda: {"qty": 0, "w_mm": 0, "h_mm": 0})
    ph = int(project.panel_height_mm)

    for boq in project.element_boqs:
        for panel in boq.panels:
            key = panel.size_label
            totals[key]["qty"] += panel.quantity
            totals[key]["w_mm"] = panel.width_mm
            totals[key]["h_mm"] = panel.height_mm

    # Sort: OC/IC first, then descending width
    def _sort_key(k):
        d = totals[k]
        is_corner = k.startswith("OC") or k.startswith("IC")
        return (0 if is_corner else 1, -d["w_mm"])

    amount_rows = []
    for key in sorted(totals.keys(), key=_sort_key):
        d = totals[key]
        qty = d["qty"]
        w_m = d["w_mm"] / 1000
        h_m = d["h_mm"] / 1000
        area_each = round(w_m * h_m, 4)
        total_area = round(area_each * qty, 4)

        alt = len(amount_rows) % 2 == 1
        fill = _ALT_FILL if alt else None

        _data_cell(ws, row, 2, key,    fill=fill, align="left")
        _data_cell(ws, row, 3, qty,    fill=fill)
        ws.cell(row=row, column=4).value = area_each
        ws.cell(row=row, column=4).number_format = "0.0000"
        ws.cell(row=row, column=5).value = total_area
        ws.cell(row=row, column=5).number_format = "0.00"
        if price_per_sqm:
            ws.cell(row=row, column=6).value = price_per_sqm
            ws.cell(row=row, column=6).number_format = "₹#,##0.00"
            ws.cell(row=row, column=7).value = round(total_area * price_per_sqm, 2)
            ws.cell(row=row, column=7).number_format = "₹#,##0.00"
        else:
            ws.cell(row=row, column=6).value = 0
            ws.cell(row=row, column=7).value = 0

        amount_rows.append(row)
        row += 1

    tbl_end = row - 1

    # ── totals ────────────────────────────────────────────────────────────────
    # TOTAL AREA row
    ws.merge_cells(f"B{row}:D{row}")
    c = ws[f"B{row}"]
    c.value = "TOTAL AREA"
    c.font = Font(bold=True)
    c.alignment = Alignment(horizontal="right")
    ws.cell(row=row, column=5).value = f"=SUM(E{tbl_start}:E{tbl_end})"
    ws.cell(row=row, column=5).number_format = "0.00"
    ws.cell(row=row, column=5).font = Font(bold=True)
    if price_per_sqm:
        ws.cell(row=row, column=7).value = f"=SUM(G{tbl_start}:G{tbl_end})"
        ws.cell(row=row, column=7).number_format = "₹#,##0.00"
        ws.cell(row=row, column=7).font = Font(bold=True)
    total_row = row
    row += 1

    # Freight
    ws.merge_cells(f"B{row}:F{row}")
    ws[f"B{row}"].value = "Freight Charges As Per Applicable"
    ws[f"B{row}"].alignment = Alignment(horizontal="right")
    ws.cell(row=row, column=7).value = freight_amount or 0
    ws.cell(row=row, column=7).number_format = "₹#,##0.00"
    freight_row = row
    row += 1

    # Total Before Tax
    ws.merge_cells(f"B{row}:F{row}")
    ws[f"B{row}"].value = "Total Value Before Tax"
    ws[f"B{row}"].font = Font(bold=True)
    ws[f"B{row}"].alignment = Alignment(horizontal="right")
    ws.cell(row=row, column=7).value = f"=G{total_row}+G{freight_row}"
    ws.cell(row=row, column=7).number_format = "₹#,##0.00"
    ws.cell(row=row, column=7).font = Font(bold=True)
    before_tax_row = row
    row += 1

    # GST
    gst_pct = int(gst_rate * 100)
    ws.merge_cells(f"B{row}:F{row}")
    ws[f"B{row}"].value = f"GSTIN {gst_pct}%"
    ws[f"B{row}"].alignment = Alignment(horizontal="right")
    ws.cell(row=row, column=7).value = f"=G{before_tax_row}*{gst_rate}"
    ws.cell(row=row, column=7).number_format = "₹#,##0.00"
    gst_row = row
    row += 1

    # Grand Total
    ws.merge_cells(f"B{row}:F{row}")
    ws[f"B{row}"].value = f"GRAND TOTAL (A+B)"
    ws[f"B{row}"].font = Font(bold=True, color="FFFFFF")
    ws[f"B{row}"].fill = PatternFill("solid", fgColor=_NOVA_BLUE)
    ws[f"B{row}"].alignment = Alignment(horizontal="right")
    ws.cell(row=row, column=7).value = f"=G{before_tax_row}+G{gst_row}"
    ws.cell(row=row, column=7).number_format = "₹#,##0.00"
    ws.cell(row=row, column=7).font = Font(bold=True)
    ws.cell(row=row, column=7).fill = PatternFill("solid", fgColor="FFF2CC")
    row += 1

    return row


# ── column widths ─────────────────────────────────────────────────────────────

def _set_column_widths(ws):
    widths = {
        "A": 5,
        "B": 28,
        "C": 20,
        "D": 14,
        "E": 12,
        "F": 14,
        "G": 18,
    }
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    # Freeze pane after header
    ws.freeze_panes = "B11"
