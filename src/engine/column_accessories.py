"""
Column accessories calculator — waller / tierod / anchor-nut system.
Nova Formworks field practice rules (column-specific).

Waller row placement (height-based):
  First row at 300 mm from base.
  Each next row +600 mm from previous.
  Stop when (height - last_row_pos) <= 750 mm.

Per-row count (wallers == tierods):
  base  = 4  (one per face corner)
  extra = floor(length / 1200) + floor(width / 1200)
  per_row = base + extra

Anchor nuts = 2 × total_wallers

This module has NO imports from the rest of the project so it can be
tested or updated independently.
"""

from dataclasses import dataclass, field
from src.engine.lenght_count_tie_waller import _per_row_count_waller, _get_tie_count_and_length
from src.engine.sharewall_accessories import _get_polygon_lengths

@dataclass
class WallerRow:
    position_mm: int   # height from base (mm)
    wallers: int
    tierods: int


@dataclass
class ColumnAccessoryResult:
    length_mm: float
    width_mm: float
    height_mm: float
    rows: list = field(default_factory=list)   # list[WallerRow]
    total_wallers: int = 0
    total_tierods: int = 0
    total_anchor_nuts: int = 0

    @property
    def num_rows(self):
        return len(self.rows)

    @property
    def positions_str(self):
        """Human-readable list of waller heights, e.g. '300, 900, 1500 mm'"""
        return ", ".join(str(r.position_mm) for r in self.rows) + " mm"



# ── Core calculation helpers ────────────────────────────────────────────────

def _waller_positions(height_mm: float) -> list:
    """
    Return list of waller heights (mm from base).

    Rule:
      - First waller at 300 mm from base.
      - Add +600 mm each step while (height - current_pos) > 750 mm.
      - Once remaining gap <= 750 mm, stop — no waller near top edge.
    """
    positions = [300]
    while height_mm - positions[-1] > 750:
        positions.append(positions[-1] + 600)
    return positions


import re
L_COL_RE = re.compile(
    r'\(\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*\)'
    r'\s*\+\s*'
    r'\(\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*\)',
    re.IGNORECASE
)
# ── Public API ──────────────────────────────────────────────────────────────

def _get_total_waller_count(waller_list) -> int:
    """Return total waller count from waller calculation result."""

    return sum(
        values[1]
        for item in waller_list
        for values in item.values()
    )

def compute_column_accessories(
    length_mm: float,
    width_mm: float,
    height_mm: float,
    label: str,
    polygon_pts: list[(float,float),],
) -> ColumnAccessoryResult:
    """
    Compute waller, tierod, and anchor-nut quantities for one column element.

    Arguments:
        length_mm   — longer plan dimension (mm)
        width_mm    — shorter plan dimension (mm)
        height_mm   — pour height / panel height (mm)

    Returns a ColumnAccessoryResult with per-row breakdown and totals.
    The caller should multiply totals by element.quantity for the project BOQ.
    """
    #print("C- label & pnts :", label, polygon_pts)
    match = L_COL_RE.search(label)
    if match:
        l_w, l_h, r_w, r_h = map(float, match.groups())
        left_w, left_h, = min(l_w,l_h), max(l_w, l_h)
        right_w, right_h = min(r_h,r_w), max(r_w,r_h)
        positions = _waller_positions(height_mm)
        inner_lenght = abs(left_h - right_w)
        inner_width = abs(right_h - left_w)
        waller_count_leghts_list = _per_row_count_waller(left_h, right_h,inner_width, inner_lenght, left_w, right_w)
        # calculate total waller
        total_waller_row = _get_total_waller_count(waller_count_leghts_list)
        per_row_tie,per_row_tie_dimension = _get_tie_count_and_length(length_mm, width_mm,inner_lenght, inner_width, left_w, right_w)
        rows = [WallerRow(pos, per_row_tie, total_waller_row) for pos in positions]
        total_tie_rod = per_row_tie * len(rows)
        total_waller = total_waller_row * len(rows)
        highlight_status = False

    elif polygon_pts:
        hori_length, verti_length, diago_length = _get_polygon_lengths(polygon_pts)
        if len(hori_length) == 2 and len(verti_length) ==2:
            lengths_lst = hori_length + verti_length
            length1, width1 = max(lengths_lst), min(lengths_lst)
            positions = _waller_positions(height_mm)
            waller_count_leghts_list = _per_row_count_waller(length1, width1)
            total_waller_lw = _get_total_waller_count(waller_count_leghts_list)
            total_waller_row  = total_waller_lw + total_waller_lw
            # get tie rod lengths and count
            per_row_tie,per_row_tie_dimension = _get_tie_count_and_length(length1, width1)
            rows = [WallerRow(pos, per_row_tie, total_waller_row) for pos in positions]
            total_tie_rod = per_row_tie * len(rows)
            total_waller = total_waller_row * len(rows)
            highlight_status = False
        elif len(hori_length) ==3 and len(verti_length) == 3:
            lengths_lst1 = hori_length + verti_length
            hori_length_s, verti_length_s = sorted(hori_length), sorted(verti_length)
            left_length = hori_length_s[-1]
            inner_lenght = hori_length_s[-2]
            left_w = hori_length_s[-3]
            right_width = verti_length_s[-1]
            inner_width = verti_length_s[-2]
            right_w = verti_length_s[-3]
            positions = _waller_positions(height_mm)
            waller_count_leghts_list = _per_row_count_waller(left_length, right_width, inner_lenght, inner_width, left_w, right_w)
            # calculate total waller
            total_waller_lw = _get_total_waller_count(waller_count_leghts_list)
            per_row_tie,per_row_tie_dimension = _get_tie_count_and_length(left_length,right_width,inner_lenght, inner_width, left_w, right_w)
            #total_waller_row  = total_waller_lw * 2
            rows = [WallerRow(pos, per_row_tie, total_waller_lw) for pos in positions]
            total_tie_rod = per_row_tie * len(rows)
            total_waller = total_waller_lw * len(rows)
            highlight_status = False
    
        else:  # len(hori_length) >=4 and len(verti_length) >=4: 
            total_vertices = hori_length + verti_length + diago_length
            tierod_count_per_row, per_row_tie_dimension = _get_tie_count_and_length(length_mm,width_mm)
            positions = _waller_positions(height_mm)
            wallers_count_length_list = _per_row_count_waller(length_mm,width_mm, total_vertices)
            # find total waller count
            total_waller_lw = _get_total_waller_count(wallers_count_length_list)
            total_waller_row  = total_waller_lw
            rows = [WallerRow(pos, tierod_count_per_row, total_waller_row) for pos in positions]
            total_tie_rod = tierod_count_per_row * len(rows)
            total_waller = total_waller_row * len(rows)
            highlight_status = True

    else:
        tierod_count_per_row, per_row_tie_dimension = _get_tie_count_and_length(length_mm,width_mm)
        positions = _waller_positions(height_mm)
        wallers_count_length_list = _per_row_count_waller(length_mm,width_mm)
        # find total waller count
        total_waller_lw = _get_total_waller_count(wallers_count_length_list)
        total_waller_row  = total_waller_lw * 2
        rows = [WallerRow(pos, tierod_count_per_row, total_waller_row) for pos in positions]
        total_tie_rod = tierod_count_per_row * len(rows)
        total_waller = total_waller_row * len(rows)
        highlight_status = False
    
    return ColumnAccessoryResult(
        length_mm=length_mm,
        width_mm=width_mm,
        height_mm=height_mm,
        rows=rows,
        total_wallers= total_waller,
        total_tierods=total_tie_rod,       # tierod count == waller count
        total_anchor_nuts=total_tie_rod * 2,
    ),highlight_status
