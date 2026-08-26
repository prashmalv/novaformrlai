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
from src.engine.lenght_count_tie_waller import round_up_tie_length, _per_row_tie_count, _per_row_count_waller

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

def compute_column_accessories(
    length_mm: float,
    width_mm: float,
    height_mm: float,
    label: str,
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
    match = L_COL_RE.search(label)
    if match:
        l_w, l_h, r_w, r_h = map(float, match.groups())
        left_w, left_h, = min(l_w,l_h), max(l_w, l_h)
        right_w, right_h = min(r_h,r_w), max(r_w,r_h)
        per_row_tie = _per_row_tie_count(length_mm, width_mm)
        positions = _waller_positions(height_mm)
        inner_lenght = abs(left_h - right_w)
        inner_width = abs(right_h - left_w)
        waller_len_face, waller_width_face,inner_length_face, inner_width_face = _per_row_count_waller(left_h, right_h,inner_width, inner_lenght)
        per_row_waller = (waller_len_face + waller_width_face + inner_length_face + inner_width_face + 3)
        rows = [WallerRow(pos, per_row_tie, per_row_waller) for pos in positions]
        total_tie_rod = per_row_tie * len(rows)
        total_waller = per_row_waller * len(rows)
        
    else:
        per_row_tie = _per_row_tie_count(length_mm, width_mm)
        tie_rod_len, tie_rod_width = round_up_tie_length(length_mm, width_mm)
        #print("Rounded length for column :",width_mm,'w=',tie_rod_width, length_mm,'l=',tie_rod_len)
        positions = _waller_positions(height_mm)
        waller_len_face, waller_width_face, inner_length_face, inner_width_face = _per_row_count_waller(length_mm,width_mm)
        per_row_waller = (waller_width_face + waller_len_face) * 2
        rows = [WallerRow(pos, per_row_tie, per_row_waller) for pos in positions]
        total_tie_rod = per_row_tie * len(rows)
        total_waller = per_row_waller * len(rows)

    return ColumnAccessoryResult(
        length_mm=length_mm,
        width_mm=width_mm,
        height_mm=height_mm,
        rows=rows,
        total_wallers= total_waller,
        total_tierods=total_tie_rod,       # tierod count == waller count
        total_anchor_nuts=total_tie_rod * 2,
    )
