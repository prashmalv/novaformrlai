"""
Share wall accessories calculator — waller / tierod / anchor-nut system.
Nova Formworks field practice rules (column-specific).

Waller row placement (height-based):
  First row at 300 mm from base.
  Each next row +600 mm from previous.
  Stop when (height - last_row_pos) <= 750 mm.

Per-row count (when wallers == tierods):
  base  = 4  (one per face corner)
  extra = floor(length / 1200) + floor(width / 1200)
  per_row = base + extra

Anchor nuts = 2 × total_wallers

This module has NO imports from the rest of the project so it can be
tested or updated independently.
"""

from dataclasses import dataclass, field
from src.engine.lenght_count_tie_waller import _get_tie_count_and_length, _per_row_count_waller

@dataclass
class WallerRow:
    position_mm: int   # height from base (mm)
    wallers: int
    tierods: int


@dataclass
class SharewallAccessoryResult:
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

# calculate horizontal and verticle length

import math


def _get_polygon_lengths(polygon_pts, tolerance=1e-6):
    """
    Calculate the lengths of horizontal, vertical, and diagonal edges of a polygon.

    Parameters
    ----------
    polygon_pts : list[tuple[float, float]]
        Polygon vertices represented as (x, y) coordinates.
    tolerance : float, optional
        Tolerance used to identify horizontal and vertical edges.

    Returns
    -------
    tuple( vertical_len,  horizontal_len, diagonal_len 
        Each list contains dictionaries with:
            - length: edge length
            - start: starting point
            - end: ending point
        vertical_len.append({                      # when we need starting and end point
                        "length": abs(dy),
                        "start": (x1, y1),
                        "end": (x2, y2),
                    })
    """

    vertical_len = []
    horizontal_len = []
    diagonal_len = []

    point_count = len(polygon_pts)

    if point_count < 2:
        return vertical_len, horizontal_len, diagonal_len

    for i in range(point_count):
        x1, y1 = polygon_pts[i]
        x2, y2 = polygon_pts[(i + 1) % point_count]

        dx = x2 - x1
        dy = y2 - y1

        # Horizontal edge
        if abs(dy) <= tolerance:
            horizontal_len.append(round(abs(dx)))

        # Vertical edge
        elif abs(dx) <= tolerance:
            vertical_len.append(round(abs(dy)))

        # Diagonal edge
        else:
            length = math.hypot(dx, dy)

            diagonal_len.append(round(length))

    return vertical_len, horizontal_len, diagonal_len


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


# ── Public API ──────────────────────────────────────────────────────────────

def _get_total_waller_count(waller_list) -> int:
    """Return total waller count from waller calculation result."""

    return sum(
        values[1]
        for item in waller_list
        for values in item.values()
    )

def compute_sharewall_accessories(
    length_mm: float,
    width_mm: float,
    height_mm: float,
    label: str,
    polygon_pts: list[(float,float),],
) -> SharewallAccessoryResult:
    """
    Compute waller, tierod, and anchor-nut quantities for one column element.

    Arguments:
        length_mm   — longer plan dimension (mm)
        width_mm    — shorter plan dimension (mm)
        height_mm   — pour height / panel height (mm)

    Returns a ColumnAccessoryResult with per-row breakdown and totals.
    The caller should multiply totals by element.quantity for the project BOQ.
    """
    # get all vertices length
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

    else: 
        # len(hori_length) >=4 and len(verti_length) >=4
        total_vertices = hori_length + verti_length + diago_length
        tierod_count_per_row, per_row_tie_dimension = _get_tie_count_and_length(length_mm,width_mm)
        positions = _waller_positions(height_mm)
        wallers_count_length_list = _per_row_count_waller(length_mm,width_mm, total_vertices=total_vertices)
        # find total waller count
        total_waller_lw = _get_total_waller_count(wallers_count_length_list)
        total_waller_row  = total_waller_lw
        rows = [WallerRow(pos, tierod_count_per_row, total_waller_row) for pos in positions]
        total_tie_rod = tierod_count_per_row * len(rows)
        total_waller = total_waller_row * len(rows)
        highlight_status = True
  
            
    
    return SharewallAccessoryResult(
        length_mm=length_mm,
        width_mm=width_mm,
        height_mm=height_mm,
        rows=rows,
        total_wallers= total_waller,
        total_tierods=total_tie_rod,       # tierod count == waller count
        total_anchor_nuts=total_tie_rod * 2,
    ), highlight_status