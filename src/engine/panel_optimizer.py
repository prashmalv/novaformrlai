"""
Panel Optimization Engine  — Phase 2.

Supported element types:
  Column      : 4 faces, OC80 at 4 corners
  Wall        : 2 faces, OC80 at 4 end corners
  Shear Wall  : same as Wall
  Box Culvert : 4 inner faces (L × H × 2  +  W × H × 2), IC100 at all 4 inner corners
  Drain       : 3 inner faces (L × H × 2  +  W × H × 1 base), IC100 at 2 bottom corners
  Monolithic  : treated as column for each column stub; walls handled separately

Complex wall junctions (T / L / C):
  L-shape : 1 extra IC100 at junction per row
  T-shape : 2 extra IC100 at junction per row
  C-shape : 2 extra IC100 at junction per row (enclosed ends use OC)
"""
import json
import os
from typing import Optional
from src.models.element import (
    StructuralElement, ElementType, JunctionType, PanelEntry, ElementBOQ
)
from src.engine import panel_catalog as _catalog

# Load config (still used for STANDARD_HEIGHTS, MAX_SPACER — not in catalog Excel)
_cfg_path = os.path.join(os.path.dirname(__file__), '../../config/panel_config.json')
with open(_cfg_path) as f:
    _CFG = json.load(f)

STANDARD_HEIGHTS: list[int] = _CFG['panel_system']['standard_heights_mm']
MAX_SPACER: int = _CFG['panel_system']['max_spacer_mm']

# Dynamic accessors — always read from active catalog (central → local → default JSON).
# Use these instead of the old module-level constants wherever widths are needed.
def _std_widths() -> list:
    return _catalog.get_flat_widths()

def _oc() -> int:
    return _catalog.get_oc_width()

def _ic() -> int:
    return _catalog.get_ic_width()

def _panel_widths() -> list:
    return _catalog.get_usable_widths(min_width=100)

# Backward-compat module-level names — NOTE: these are snapshots taken at import time.
# They are kept only so external code that reads them (e.g. tests) doesn't break.
# Internal optimizer functions call _std_widths()/_oc()/_ic() dynamically.
STANDARD_WIDTHS: list[int] = _catalog.get_flat_widths()
OC_WIDTH:   int = _catalog.get_oc_width()
IC_WIDTH:   int = _catalog.get_ic_width()
PANEL_WIDTHS: list[int] = _catalog.get_usable_widths(min_width=100)

_CATALOG_HEIGHTS_SET: frozenset = frozenset(STANDARD_HEIGHTS)

def _catalog_widths_set() -> frozenset:
    return frozenset(_std_widths())


def is_catalog_panel(panel) -> bool:
    """
    Return True if this PanelEntry exists in Nova's standard product catalog.
    Rules:
    - Height must be a catalog standard height (1235 / 2470 / 3705mm).
    - OC and IC at any standard height are always catalog items.
    - Flat panels must have a catalog width AND a catalog height.
    """
    h = int(round(panel.height_mm))
    w = int(round(panel.width_mm))
    if h not in _CATALOG_HEIGHTS_SET:
        return False
    if panel.is_corner or panel.is_inner_corner:
        return True        # OC80 / IC100 at any standard height ✓
    return w in _catalog_widths_set()


def _combo_score(combo: list[int]) -> tuple:
    """
    Score a panel combination — lower tuple value is BETTER.

    Priority (Nova site practice):
      1. Fewest panels — fewer pieces = less handling on site.
      2. Largest maximum panel used — maximise use of 600mm / 500mm panels.
    """
    if not combo:
        return (0, 0)
    return (len(combo), -max(combo))


def find_panel_combination(
    target_mm: float,
    available_widths: list[int] = None,
    max_panels: int = None,
) -> tuple[list[int], float]:
    """
    Find the best panel-width combination for a given face net length.

    Strategy:
      * Try every allowed site gap (0 … MAX_SPACER mm) so a 3-panel + gap
        solution beats a 4-panel exact solution.
      * Score by: fewest panels, then largest max panel.
      * No panel smaller than 100 mm is ever used; 40 mm is a gap only.

    Returns:
        (widths_list, spacer_mm)
        spacer_mm > 0 → gap left between last panel and wall end
        spacer_mm < 0 → panels overshoot (rare fallback)
    """
    if available_widths is None:
        available_widths = _panel_widths()  # live from active catalog; min 100mm

    widths = sorted(available_widths, reverse=True)
    target = int(round(target_mm))

    # Face shorter than minimum panel → pure gap, no panels needed
    if target <= 0:
        return [], 0.0
    if target <= MAX_SPACER:
        return [], float(target)

    # Max panels: enough to cover target with smallest panels, plus headroom.
    # This must be large enough for big faces like 8160mm (≈ 14×600).
    if max_panels is None:
        max_panels = max(10, (target // min(widths)) + 2)

    # Always prefer a gapless solution — try gap=0 first
    no_gap = _dp_exact(target, widths, max_panels)
    if no_gap is not None:
        return no_gap, 0.0

    # No exact fit — fall back to smallest gap that yields any solution
    best_combo: list | None = None
    best_spacer = 0

    for gap in range(1, MAX_SPACER + 1):
        reduced = target - gap
        if reduced <= 0:
            break
        result = _dp_exact(reduced, widths, max_panels)
        if result is not None:
            if best_combo is None or _combo_score(result) < _combo_score(best_combo):
                best_combo = result
                best_spacer = gap

    if best_combo is not None:
        return best_combo, float(best_spacer)

    # Fallback: greedy largest-first (may overshoot by up to min_panel-1 mm)
    combo, overshoot = _greedy_fit(target, widths)
    return combo, -float(overshoot)


def _dp_exact(target: int, widths: list[int], max_panels: int) -> Optional[list[int]]:
    """
    DP to find panel combination summing exactly to target.
    Scoring: see _combo_score — prefer balanced splits, then fewer panels.
    """
    if target <= 0:
        return []

    dp = [None] * (target + 1)
    dp[0] = []

    for s in range(1, target + 1):
        best = None
        for w in widths:
            if w > s:
                continue
            prev = dp[s - w]
            if prev is None:
                continue
            candidate = prev + [w]
            if len(candidate) > max_panels:
                continue
            if best is None or _combo_score(candidate) < _combo_score(best):
                best = candidate
        dp[s] = best

    return dp[target]


def _greedy_fit(target: int, widths: list[int]) -> tuple[list[int], int]:
    """Greedy: keep adding panels until target covered. May overshoot."""
    combo = []
    remaining = target
    while remaining > 0:
        placed = False
        for w in widths:
            if w <= remaining:
                combo.append(w)
                remaining -= w
                placed = True
                break
        if not placed:
            # Must overshoot with smallest available panel
            smallest = min(widths)
            combo.append(smallest)
            remaining -= smallest
    overshoot = -remaining if remaining < 0 else 0
    return combo, overshoot


def _count_panels(combo: list[int]) -> dict[int, int]:
    """Count panel widths → {width: count}"""
    counts: dict[int, int] = {}
    for w in combo:
        counts[w] = counts.get(w, 0) + 1
    return counts


def _make_filler_entry(spacer_mm: float, panel_h: int, face_count: int) -> 'PanelEntry':
    """Create a fill-plate PanelEntry for a gap so that panel widths sum to the full face length."""
    w = int(round(spacer_mm))
    return PanelEntry(
        size_label=f"FP{w}X{panel_h}",
        width_mm=w, height_mm=panel_h,
        quantity=face_count,
        is_filler=True,
    )


def optimize_column(element: StructuralElement, panel_height_mm: float) -> ElementBOQ:
    """
    Compute formwork BOQ for a rectangular column.

    Column has 4 faces:
      - 2 faces of length_mm (front/back)
      - 2 faces of width_mm (sides)
    OC80 panels at all 4 corners.
    """
    boq = ElementBOQ(element=element)
    warnings = []

    panel_h = int(round(panel_height_mm))

    # Panel height is used for area calculation (size label & sqm) only.
    # Quantity is always for 1 row — stacking is never auto-applied.
    rows = 1
    boq.height_note = f"{panel_h}MM"

    # --- LENGTH faces (2 faces, each length_mm wide) ---
    len_combo, len_spacer = find_panel_combination(element.length_mm)
    if len_spacer > 0:
        warnings.append(f"Length face {element.length_mm}mm: spacer of {len_spacer}mm needed.")
    elif len_spacer < 0:
        warnings.append(f"Length face {element.length_mm}mm: overshoot of {-len_spacer}mm.")

    # --- WIDTH faces (2 faces, each width_mm wide) ---
    wid_combo, wid_spacer = find_panel_combination(element.width_mm)
    if wid_spacer > 0:
        warnings.append(f"Width face {element.width_mm}mm: spacer of {wid_spacer}mm needed.")
    elif wid_spacer < 0:
        warnings.append(f"Width face {element.width_mm}mm: overshoot of {-wid_spacer}mm.")

    # Collect all panels
    panel_counts: dict[str, dict] = {}

    def _add_panels(combo: list[int], face_count: int, label_prefix=""):
        # face_count = number of identical faces (2 for columns)
        # rows = vertical stacking rows
        total_multiplier = face_count * rows
        counts = _count_panels(combo)
        for width, cnt in counts.items():
            key = f"{width}X{panel_h}"
            total_qty = cnt * total_multiplier
            if key in panel_counts:
                panel_counts[key]['qty'] += total_qty
            else:
                panel_counts[key] = {
                    'width': width, 'height': panel_h,
                    'qty': total_qty, 'is_corner': False
                }

    _add_panels(len_combo, face_count=2)
    _add_panels(wid_combo, face_count=2)

    # OC (Outer Corner): 4 corners × rows
    oc_key = f"OC{_oc()}X{panel_h}"
    panel_counts[oc_key] = {
        'width': _oc(), 'height': panel_h,
        'qty': 4 * rows, 'is_corner': True
    }

    # Build PanelEntry list (OC first, then flat panels sorted by width desc)
    oc_entry = PanelEntry(
        size_label=oc_key,
        width_mm=_oc(), height_mm=panel_h,
        quantity=panel_counts[oc_key]['qty'],
        is_corner=True
    )
    boq.panels = [oc_entry]

    flat_keys = sorted(
        [k for k in panel_counts if k != oc_key],
        key=lambda k: panel_counts[k]['width'],
        reverse=True
    )
    for k in flat_keys:
        d = panel_counts[k]
        boq.panels.append(PanelEntry(
            size_label=k,
            width_mm=d['width'], height_mm=d['height'],
            quantity=d['qty']
        ))

    # Fill plates ensure: sum(panels) + fill = face_length so the math checks out.
    if len_spacer > 0:
        boq.panels.append(_make_filler_entry(len_spacer, panel_h, face_count=2))
    if wid_spacer > 0:
        boq.panels.append(_make_filler_entry(wid_spacer, panel_h, face_count=2))

    boq.spacer_mm = max(len_spacer, wid_spacer)
    boq.warnings = warnings

    # Per-face breakdown for the top-down panel layout diagram (largest panel first)
    _len_sorted = sorted(len_combo, reverse=True)
    _wid_sorted = sorted(wid_combo, reverse=True)
    boq.face_panels = [
        {'face': 'A',  'label': f'A — {int(element.length_mm)}mm',
         'dim_mm': element.length_mm, 'panels': _len_sorted, 'spacer': len_spacer},
        {'face': 'B',  'label': f'B — {int(element.width_mm)}mm',
         'dim_mm': element.width_mm,  'panels': _wid_sorted, 'spacer': wid_spacer},
        {'face': "A'", 'label': f"A' — {int(element.length_mm)}mm",
         'dim_mm': element.length_mm, 'panels': _len_sorted, 'spacer': len_spacer},
        {'face': "B'", 'label': f"B' — {int(element.width_mm)}mm",
         'dim_mm': element.width_mm,  'panels': _wid_sorted, 'spacer': wid_spacer},
    ]

    return boq


def optimize_wall(element: StructuralElement, panel_height_mm: float) -> ElementBOQ:
    """
    Compute formwork BOQ for a straight or junction wall.

    Straight wall : 2 faces × length_mm, OC80 at 4 end corners.
    L-junction    : add 1 IC100 per row at the inner corner.
    T-junction    : add 2 IC100 per row at both inner corners.
    C-junction    : add 2 IC100 per row; enclosed end uses OC like a column end.
    """
    boq = ElementBOQ(element=element)
    warnings = []
    panel_h = int(round(panel_height_mm))

    rows = 1  # height is for area calculation only; never auto-stack
    boq.height_note = f"{panel_h}MM"

    combo, spacer = find_panel_combination(element.length_mm)
    if spacer > 0:
        warnings.append(f"Wall face {element.length_mm}mm: spacer {spacer}mm.")
    elif spacer < 0:
        warnings.append(f"Wall face {element.length_mm}mm: overshoot {-spacer}mm.")

    panel_counts: dict[str, dict] = {}

    # Flat panels — 2 main faces
    counts = _count_panels(combo)
    for width, cnt in counts.items():
        key = f"{width}X{panel_h}"
        total_qty = cnt * 2 * rows
        panel_counts[key] = {'width': width, 'height': panel_h,
                              'qty': total_qty, 'is_corner': False}

    # --- OC corners at straight ends ---
    jt = getattr(element, 'junction_type', JunctionType.NONE)

    # Straight wall: 4 OC (2 ends × 2 faces)
    # C-shape: only 2 OC at the open end; enclosed end gets OC too = 4 total
    oc_qty = 4 * rows
    oc_key = f"OC{_oc()}X{panel_h}"
    panel_counts[oc_key] = {'width': _oc(), 'height': panel_h,
                             'qty': oc_qty, 'is_corner': True}

    # --- IC corners at junctions ---
    ic_qty = 0
    if jt == JunctionType.L:
        ic_qty = 2 * rows        # 1 junction × 2 faces
        warnings.append("L-shaped junction: IC100 panels added at inner corner.")
    elif jt == JunctionType.T:
        ic_qty = 4 * rows        # 2 junctions × 2 faces
        warnings.append("T-shaped junction: IC100 panels added at both inner corners.")
    elif jt == JunctionType.C:
        ic_qty = 4 * rows        # 2 inner corners of C-shape
        warnings.append("C/U-shaped wall: IC100 panels added at both inner corners.")

    ic_key = f"IC{_ic()}X{panel_h}"
    if ic_qty > 0:
        panel_counts[ic_key] = {'width': _ic(), 'height': panel_h,
                                 'qty': ic_qty, 'is_corner': True,
                                 'is_inner': True}

    # Build PanelEntry list: IC first, then OC, then flat panels
    boq.panels = []
    if ic_key in panel_counts:
        d = panel_counts[ic_key]
        boq.panels.append(PanelEntry(
            size_label=ic_key, width_mm=_ic(), height_mm=panel_h,
            quantity=d['qty'], is_corner=True, is_inner_corner=True
        ))

    boq.panels.append(PanelEntry(
        size_label=oc_key, width_mm=_oc(), height_mm=panel_h,
        quantity=panel_counts[oc_key]['qty'], is_corner=True
    ))

    flat_keys = sorted(
        [k for k in panel_counts if k not in (oc_key, ic_key)],
        key=lambda k: panel_counts[k]['width'], reverse=True
    )
    for k in flat_keys:
        d = panel_counts[k]
        boq.panels.append(PanelEntry(
            size_label=k, width_mm=d['width'], height_mm=d['height'], quantity=d['qty']
        ))

    if spacer > 0:
        boq.panels.append(_make_filler_entry(spacer, panel_h, face_count=2))

    boq.spacer_mm = max(spacer, 0)
    boq.warnings = warnings
    return boq


def optimize_box_culvert(element: StructuralElement, panel_height_mm: float) -> ElementBOQ:
    """
    Box Culvert formwork BOQ.

    A box culvert is a rectangular tunnel/conduit. The formwork covers:
      - 2 side walls  : each length_mm × height_mm
      - 1 soffit slab : length_mm wide (top inner face, if cast in-situ)
      - 2 end walls   : each width_mm × height_mm
    Inner corners between walls and soffit use IC100 panels.
    Outer corners use OC80.

    element.length_mm = inner clear length (span)
    element.width_mm  = inner clear width (span)
    element.height_mm = wall height / casting height
    """
    boq = ElementBOQ(element=element)
    warnings = []
    panel_h = int(round(panel_height_mm))

    rows = 1  # height is for area calculation only
    boq.height_note = f"{panel_h}MM"

    panel_counts: dict[str, dict] = {}

    def _add(combo, face_count):
        for width, cnt in _count_panels(combo).items():
            key = f"{width}X{panel_h}"
            qty = cnt * face_count * rows
            if key in panel_counts:
                panel_counts[key]['qty'] += qty
            else:
                panel_counts[key] = {'width': width, 'height': panel_h,
                                     'qty': qty, 'is_corner': False}

    # Side walls × 2 (left & right inner faces — length direction)
    l_combo, l_sp = find_panel_combination(element.length_mm)
    if l_sp > 0: warnings.append(f"Culvert length {element.length_mm}mm: spacer {l_sp}mm.")
    _add(l_combo, 2)

    # End walls × 2 (width direction inner faces)
    w_combo, w_sp = find_panel_combination(element.width_mm)
    if w_sp > 0: warnings.append(f"Culvert width {element.width_mm}mm: spacer {w_sp}mm.")
    _add(w_combo, 2)

    # IC100 at all 4 inner vertical corners × rows
    ic_key = f"IC{_ic()}X{panel_h}"
    panel_counts[ic_key] = {'width': _ic(), 'height': panel_h,
                             'qty': 4 * rows, 'is_corner': True, 'is_inner': True}

    # OC80 at outer top corners (where walls meet soffit) × 2 per end × rows
    oc_key = f"OC{_oc()}X{panel_h}"
    panel_counts[oc_key] = {'width': _oc(), 'height': panel_h,
                             'qty': 4 * rows, 'is_corner': True}

    # Build panel list: IC → OC → flat
    boq.panels = []
    boq.panels.append(PanelEntry(
        size_label=ic_key, width_mm=_ic(), height_mm=panel_h,
        quantity=panel_counts[ic_key]['qty'], is_corner=True, is_inner_corner=True
    ))
    boq.panels.append(PanelEntry(
        size_label=oc_key, width_mm=_oc(), height_mm=panel_h,
        quantity=panel_counts[oc_key]['qty'], is_corner=True
    ))
    for k in sorted([k for k in panel_counts if k not in (oc_key, ic_key)],
                    key=lambda k: panel_counts[k]['width'], reverse=True):
        d = panel_counts[k]
        boq.panels.append(PanelEntry(
            size_label=k, width_mm=d['width'], height_mm=d['height'], quantity=d['qty']
        ))

    if l_sp > 0:
        boq.panels.append(_make_filler_entry(l_sp, panel_h, face_count=2))
    if w_sp > 0:
        boq.panels.append(_make_filler_entry(w_sp, panel_h, face_count=2))

    boq.spacer_mm = max(l_sp, w_sp, 0)
    boq.warnings = warnings
    warnings.append("Box Culvert: verify soffit (top slab) formwork with engineer.")
    return boq


def optimize_drain(element: StructuralElement, panel_height_mm: float) -> ElementBOQ:
    """
    U-shaped Drain (open-top) formwork BOQ.

    3 inner faces:
      - 2 side walls : length_mm × height_mm each
      - 1 base       : width_mm × height_mm (bottom inner face, if used)
    IC100 at 2 bottom inner corners.
    OC80 at 4 top outer corners.

    element.length_mm = drain length
    element.width_mm  = inner clear width
    element.height_mm = drain wall height
    """
    boq = ElementBOQ(element=element)
    warnings = []
    panel_h = int(round(panel_height_mm))

    rows = 1  # height is for area calculation only
    boq.height_note = f"{panel_h}MM"

    panel_counts: dict[str, dict] = {}

    def _add(combo, face_count):
        for width, cnt in _count_panels(combo).items():
            key = f"{width}X{panel_h}"
            qty = cnt * face_count * rows
            if key in panel_counts:
                panel_counts[key]['qty'] += qty
            else:
                panel_counts[key] = {'width': width, 'height': panel_h,
                                     'qty': qty, 'is_corner': False}

    l_combo, l_sp = find_panel_combination(element.length_mm)
    if l_sp > 0: warnings.append(f"Drain length {element.length_mm}mm: spacer {l_sp}mm.")
    _add(l_combo, 2)   # 2 side walls

    w_combo, w_sp = find_panel_combination(element.width_mm)
    if w_sp > 0: warnings.append(f"Drain width {element.width_mm}mm: spacer {w_sp}mm.")
    _add(w_combo, 1)   # 1 base (bottom inner face)

    # IC100 at 2 bottom inner corners × rows
    ic_key = f"IC{_ic()}X{panel_h}"
    panel_counts[ic_key] = {'width': _ic(), 'height': panel_h,
                             'qty': 2 * rows, 'is_corner': True, 'is_inner': True}

    # OC80 at 4 top outer corners × rows
    oc_key = f"OC{_oc()}X{panel_h}"
    panel_counts[oc_key] = {'width': _oc(), 'height': panel_h,
                             'qty': 4 * rows, 'is_corner': True}

    boq.panels = []
    boq.panels.append(PanelEntry(
        size_label=ic_key, width_mm=_ic(), height_mm=panel_h,
        quantity=panel_counts[ic_key]['qty'], is_corner=True, is_inner_corner=True
    ))
    boq.panels.append(PanelEntry(
        size_label=oc_key, width_mm=_oc(), height_mm=panel_h,
        quantity=panel_counts[oc_key]['qty'], is_corner=True
    ))
    for k in sorted([k for k in panel_counts if k not in (oc_key, ic_key)],
                    key=lambda k: panel_counts[k]['width'], reverse=True):
        d = panel_counts[k]
        boq.panels.append(PanelEntry(
            size_label=k, width_mm=d['width'], height_mm=d['height'], quantity=d['qty']
        ))

    if l_sp > 0:
        boq.panels.append(_make_filler_entry(l_sp, panel_h, face_count=2))
    if w_sp > 0:
        boq.panels.append(_make_filler_entry(w_sp, panel_h, face_count=1))

    boq.spacer_mm = max(l_sp, w_sp, 0)
    boq.warnings = warnings
    warnings.append("Drain: confirm whether base slab formwork is required on site.")
    return boq


IC_75_WIDTH: int = 75   # supplementary inner-corner panel used in beam-slab junctions


def optimize_beam_bottom(element: StructuralElement, panel_height_mm: float) -> ElementBOQ:
    """
    Beam Bottom formwork BOQ.

    The bottom shutter sits beneath the beam and consists of:
      - 1 flat panel whose width ≥ beam internal clear width (element.width_mm)
      - 2 OC80 panels locking the sides (one each end of the flat panel)
    This assembly is expressed as: (OC+{flat_w}+OC)X{height_mm}

    element.width_mm  = beam internal clear width  (selects flat panel size)
    element.height_mm = beam depth / shuttering height  (= assembly height)
    element.length_mm = beam span (informational; not used for panel count)
    element.quantity  = number of beam bottom sets
    """
    boq = ElementBOQ(element=element)
    warnings: list[str] = []

    depth = int(round(element.height_mm))   # beam depth = panel height for this assembly
    beam_w = element.width_mm               # internal clear width

    # Find the nearest standard flat panel width ≥ beam_w
    flat_w = next((w for w in sorted(_std_widths()) if w >= beam_w), max(_std_widths()))
    if flat_w > beam_w:
        warnings.append(
            f"Beam width {beam_w:.0f}mm: using nearest standard panel {flat_w}mm "
            f"(overshoot {flat_w - beam_w:.0f}mm)."
        )

    # Panel label format: (OC+{flat_w}+OC)X{depth}
    label = f"(OC+{flat_w}+OC)X{depth}"

    # area = (OC_width + flat_w + OC_width) × depth
    total_w_mm = _oc() + flat_w + _oc()
    area_sqm = round(total_w_mm * depth / 1_000_000, 6)

    boq.panels = [
        PanelEntry(
            size_label=label,
            width_mm=total_w_mm,
            height_mm=depth,
            quantity=element.quantity,
            area_sqm=area_sqm,
        )
    ]
    boq.height_note = f"{depth}MM"
    boq.warnings = warnings
    return boq


def optimize_beam_side(element: StructuralElement, panel_height_mm: float) -> ElementBOQ:
    """
    Beam Side & Slab formwork BOQ.

    Covers the two vertical side faces of a beam plus the slab soffit panels at
    the beam-slab junction.

    element.height_mm = beam side height (depth of the beam side face)
    element.length_mm = beam span (determines how many panels along the side)
    element.width_mm  = beam wall thickness (used for accessories; not for panel count)
    element.quantity  = number of beam side sets

    Panels per side:
      - IC100 × 1 at each end of the beam side (beam-slab junction corner)
      - Flat panels covering (length_mm − 2×IC100_width) span
    Both sides (× 2).
    """
    boq = ElementBOQ(element=element)
    warnings: list[str] = []

    beam_h  = int(round(element.height_mm))   # beam side height
    beam_L  = element.length_mm               # beam span

    # IC100 occupies _ic() mm at each end of both sides
    ic_used = _ic() * 2
    flat_span = max(0.0, beam_L - ic_used)

    # Flat panel combination for the remaining span
    if flat_span > 0:
        combo, spacer = find_panel_combination(flat_span)
        if spacer > 0:
            warnings.append(f"Beam side span {flat_span:.0f}mm: spacer {spacer:.0f}mm needed.")
    else:
        combo, spacer = [], 0.0

    panel_counts: dict[str, dict] = {}

    # IC100 at 2 ends × 2 sides
    ic_key = f"IC{_ic()}X{beam_h}"
    panel_counts[ic_key] = {
        'width': _ic(), 'height': beam_h,
        'qty': 4 * element.quantity, 'is_corner': True, 'is_inner': True
    }

    # Flat panels × 2 sides
    for w, cnt in _count_panels(combo).items():
        key = f"{w}X{beam_h}"
        qty = cnt * 2 * element.quantity
        if key in panel_counts:
            panel_counts[key]['qty'] += qty
        else:
            panel_counts[key] = {'width': w, 'height': beam_h,
                                  'qty': qty, 'is_corner': False}

    boq.panels = []
    boq.panels.append(PanelEntry(
        size_label=ic_key, width_mm=_ic(), height_mm=beam_h,
        quantity=panel_counts[ic_key]['qty'], is_corner=True, is_inner_corner=True
    ))
    for k in sorted([k for k in panel_counts if k != ic_key],
                    key=lambda k: panel_counts[k]['width'], reverse=True):
        d = panel_counts[k]
        boq.panels.append(PanelEntry(
            size_label=k, width_mm=d['width'], height_mm=d['height'], quantity=d['qty']
        ))

    boq.height_note = f"{beam_h}MM"
    boq.spacer_mm = spacer
    boq.warnings = warnings
    warnings.append(
        f"Beam Side: IC100 at 2 ends per side. "
        f"Flat panels cover {flat_span:.0f}mm span × 2 sides."
    )
    return boq


def optimize_polygon_element(
    element: StructuralElement,
    face_nets: list,
    oc_count: int,
    ic_count: int,
    product_height_mm: float,
) -> 'ElementBOQ':
    """
    Generate BOQ for any polygon-shaped element (L-wall, T-wall, I-beam, etc.)
    from pre-computed face net lengths and corner counts.

    face_nets    : net panel-coverage length per face after IC deductions (mm)
    oc_count     : number of convex (OC80) corners in the polygon
    ic_count     : number of concave (IC100) corners in the polygon
    """
    boq = ElementBOQ(element=element)
    panel_h = int(round(product_height_mm))
    panel_counts: dict = {}

    # OC80 corner panels
    oc_key = f"OC{_oc()}X{panel_h}"
    panel_counts[oc_key] = {'width': _oc(), 'height': panel_h,
                             'qty': oc_count, 'is_corner': True, 'is_inner': False}

    # IC100 corner panels
    ic_key = f"IC{_ic()}X{panel_h}"
    if ic_count > 0:
        panel_counts[ic_key] = {'width': _ic(), 'height': panel_h,
                                 'qty': ic_count, 'is_corner': True, 'is_inner': True}

    # Flat panels — fill each face individually using DP
    for net in face_nets:
        if net <= 0:
            continue
        combo, _spacer = find_panel_combination(net)
        for w, cnt in _count_panels(combo).items():
            key = f"{w}X{panel_h}"
            if key in panel_counts:
                panel_counts[key]['qty'] += cnt
            else:
                panel_counts[key] = {'width': w, 'height': panel_h,
                                      'qty': cnt, 'is_corner': False, 'is_inner': False}

    # Build PanelEntry list: IC first, then OC, then flat panels sorted width desc
    boq.panels = []
    if ic_count > 0 and ic_key in panel_counts:
        d = panel_counts[ic_key]
        boq.panels.append(PanelEntry(
            size_label=ic_key, width_mm=_ic(), height_mm=panel_h,
            quantity=d['qty'], is_corner=True, is_inner_corner=True,
        ))
    if oc_key in panel_counts:
        d = panel_counts[oc_key]
        boq.panels.append(PanelEntry(
            size_label=oc_key, width_mm=_oc(), height_mm=panel_h,
            quantity=d['qty'], is_corner=True,
        ))
    flat_keys = sorted(
        [k for k in panel_counts if not panel_counts[k].get('is_corner')],
        key=lambda k: panel_counts[k]['width'], reverse=True,
    )
    for k in flat_keys:
        d = panel_counts[k]
        boq.panels.append(PanelEntry(
            size_label=k, width_mm=d['width'], height_mm=d['height'], quantity=d['qty'],
        ))

    boq.height_note = f"{panel_h}MM"
    return boq


def _compute_polygon_sw_boq(element: StructuralElement, panel_height_mm: float) -> ElementBOQ:
    """
    BOQ for a complex polygon-shaped shear wall.

    Uses the actual polygon vertices stored in element.polygon_pts to enumerate
    every face (edge) of the cross-section and compute net flat-panel lengths after
    IC corner deductions.  OC and IC panel counts come from the vertex classification.
    """
    poly_pts = element.polygon_pts or []

    # Lazy import to avoid circular dependency (dwg_parser ← models ← panel_optimizer)
    try:
        from src.parsers.dwg_parser import (
            _classify_polygon_corners as _cpg_c,
            _compute_polygon_face_nets  as _cpg_fn,
        )
        corners  = _cpg_c(poly_pts)
        face_nets = _cpg_fn(poly_pts, corners)
    except Exception:
        # Fallback: treat as plain rectangular element
        return optimize_column(element, panel_height_mm)

    oc_count = corners.count('OC80')
    ic_count = corners.count('IC100')

    boq = optimize_polygon_element(element, face_nets, oc_count, ic_count, panel_height_mm)
    return boq


def compute_boq(element: StructuralElement, panel_height_mm: float = 3200) -> ElementBOQ:
    """Main entry: compute BOQ for any element type."""
    if element.is_column or element.is_monolithic:
        return optimize_column(element, panel_height_mm)
    elif element.element_type == ElementType.SHEAR_WALL:
        poly = getattr(element, 'polygon_pts', None) or []
        if len(poly) > 4:
            return _compute_polygon_sw_boq(element, panel_height_mm)
        return optimize_column(element, panel_height_mm)  # rect SW → 4-face treatment
    elif element.is_wall:
        return optimize_wall(element, panel_height_mm)
    elif element.is_box_culvert:
        return optimize_box_culvert(element, panel_height_mm)
    elif element.is_drain:
        return optimize_drain(element, panel_height_mm)
    elif element.is_beam_bottom:
        return optimize_beam_bottom(element, panel_height_mm)
    elif element.is_beam_side:
        return optimize_beam_side(element, panel_height_mm)
    else:
        raise NotImplementedError(f"Element type {element.element_type} not yet supported.")
