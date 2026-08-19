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


def _per_row_count(length_mm: float, width_mm: float) -> int:
    """
    Wallers (and tierods) needed on each horizontal row.

    Rule:
      base  = 4   (one tie-point per corner/face side)
      extra = floor(length / 1200) + floor(width / 1200)
              (+1 for every full 1200 mm span in each dimension)
    """
    extra = int(length_mm // 1200) + int(width_mm // 1200)
    return 4 + extra


# ── Public API ──────────────────────────────────────────────────────────────

def compute_column_accessories(
    length_mm: float,
    width_mm: float,
    height_mm: float,
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
    per_row = _per_row_count(length_mm, width_mm)
    positions = _waller_positions(height_mm)

    rows = [WallerRow(pos, per_row, per_row) for pos in positions]

    total_wallers = per_row * len(rows)
    return ColumnAccessoryResult(
        length_mm=length_mm,
        width_mm=width_mm,
        height_mm=height_mm,
        rows=rows,
        total_wallers=total_wallers,
        total_tierods=total_wallers,       # tierod count == waller count
        total_anchor_nuts=total_wallers * 2,
    )
