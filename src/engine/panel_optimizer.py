"""
Panel Optimization Engine.

Logic derived from actual Nova Formworks quotations:
- Each face of a structural element is covered by panels placed side-by-side
- For columns: 4 faces (2 × length, 2 × width), OC80 at each corner
- For walls: 2 faces (both sides), OC80 at each end corner
- Panel widths must sum to the face dimension (exact preferred)
- If exact match impossible, allow small spacer gap
"""
import json
import os
from typing import Optional
from src.models.element import (
    StructuralElement, ElementType, PanelEntry, ElementBOQ
)

# Load config
_cfg_path = os.path.join(os.path.dirname(__file__), '../../config/panel_config.json')
with open(_cfg_path) as f:
    _CFG = json.load(f)

STANDARD_WIDTHS: list[int] = _CFG['panel_system']['standard_widths_mm']
OC_WIDTH: int = _CFG['panel_system']['oc_width_mm']
IC_WIDTH: int = _CFG['panel_system']['ic_width_mm']
MAX_SPACER: int = _CFG['panel_system']['max_spacer_mm']


def find_panel_combination(
    target_mm: float,
    available_widths: list[int] = None,
    max_panels: int = 10,
) -> tuple[list[int], float]:
    """
    Find optimal panel widths combination for a given face dimension.

    Returns:
        (list of panel widths used, spacer_mm)
        spacer_mm > 0 means panels don't fully cover target (gap = spacer)
        spacer_mm < 0 means panels overshoot by abs(spacer_mm)
    """
    if available_widths is None:
        available_widths = STANDARD_WIDTHS

    # Sort descending for greedy preference
    widths = sorted(available_widths, reverse=True)
    target = int(round(target_mm))

    # Try exact match using DP (subset sum with repetition allowed)
    result = _dp_exact(target, widths, max_panels)
    if result is not None:
        return result, 0.0

    # Try with spacer: find combo that covers (target - spacer) exactly
    for spacer in range(1, MAX_SPACER + 1):
        reduced = target - spacer
        if reduced <= 0:
            break
        result = _dp_exact(reduced, widths, max_panels)
        if result is not None:
            return result, float(spacer)

    # Fallback: greedy (may overshoot slightly)
    combo, overshoot = _greedy_fit(target, widths)
    return combo, -float(overshoot)  # negative = overshoot


def _combo_score(combo: list[int]) -> tuple:
    """
    Score a panel combination — lower tuple value is BETTER.

    Priority derived from actual Nova Formworks quotations:
      1. Avoid highly unbalanced splits where the smallest panel is
         less than 1/3 of the largest (e.g. [350,100] for 450mm is bad).
      2. Fewest total panels (fewer handling pieces on site).
      3. Largest minimum panel (more balanced / symmetric distribution).
         This picks [500,500] over [600,400] for 1000mm,
         and [250,200] over [300,150] for 450mm.
    """
    max_p = max(combo)
    min_p = min(combo)
    ugly  = 1 if min_p * 3 < max_p else 0  # 1 = unbalanced split
    return (ugly, len(combo), -min_p)


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

    # Determine stacking: how many rows of panels needed for height
    # height_mm may need to be covered by stacked panels
    h = element.height_mm
    rows = max(1, int(h / panel_h))
    if rows * panel_h < h:
        remaining_h = h - rows * panel_h
        # Allow slight overshoot or flag warning
        warnings.append(
            f"Height {h}mm not evenly divisible by panel height {panel_h}mm. "
            f"Using {rows} rows ({rows * panel_h}mm). Gap = {h - rows * panel_h}mm."
        )

    achieved_height = rows * panel_h
    boq.height_note = f"{achieved_height}MM"

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
    oc_key = f"OC{OC_WIDTH}X{panel_h}"
    panel_counts[oc_key] = {
        'width': OC_WIDTH, 'height': panel_h,
        'qty': 4 * rows, 'is_corner': True
    }

    # Build PanelEntry list (OC first, then flat panels sorted by width desc)
    oc_entry = PanelEntry(
        size_label=oc_key,
        width_mm=OC_WIDTH, height_mm=panel_h,
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

    boq.spacer_mm = max(len_spacer, wid_spacer)
    boq.warnings = warnings
    return boq


def optimize_wall(element: StructuralElement, panel_height_mm: float) -> ElementBOQ:
    """
    Compute formwork BOQ for a rectangular wall.

    Wall has 2 main faces (front and back), each length_mm wide.
    OC at 4 end corners.
    Tie rods go through the wall thickness.
    """
    boq = ElementBOQ(element=element)
    warnings = []

    panel_h = int(round(panel_height_mm))

    # Height stacking
    h = element.height_mm
    rows = max(1, int(h / panel_h))
    if rows * panel_h < h:
        warnings.append(
            f"Height {h}mm: {rows} rows give {rows * panel_h}mm. "
            f"Difference {h - rows * panel_h}mm."
        )

    achieved_height = rows * panel_h
    boq.height_note = f"{achieved_height}MM"

    # Main faces (2 faces × length_mm wide)
    combo, spacer = find_panel_combination(element.length_mm)
    if spacer > 0:
        warnings.append(f"Wall face {element.length_mm}mm: spacer {spacer}mm.")
    elif spacer < 0:
        warnings.append(f"Wall face {element.length_mm}mm: overshoot {-spacer}mm.")

    panel_counts: dict[str, dict] = {}

    counts = _count_panels(combo)
    for width, cnt in counts.items():
        key = f"{width}X{panel_h}"
        total_qty = cnt * 2 * rows  # 2 faces
        panel_counts[key] = {
            'width': width, 'height': panel_h,
            'qty': total_qty, 'is_corner': False
        }

    # OC at 4 end corners × rows
    oc_key = f"OC{OC_WIDTH}X{panel_h}"
    panel_counts[oc_key] = {
        'width': OC_WIDTH, 'height': panel_h,
        'qty': 4 * rows, 'is_corner': True
    }

    oc_entry = PanelEntry(
        size_label=oc_key,
        width_mm=OC_WIDTH, height_mm=panel_h,
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

    boq.spacer_mm = max(spacer, 0)
    boq.warnings = warnings
    return boq


def compute_boq(element: StructuralElement, panel_height_mm: float = 3200) -> ElementBOQ:
    """Main entry: compute BOQ for any element type."""
    if element.is_column:
        return optimize_column(element, panel_height_mm)
    elif element.is_wall:
        return optimize_wall(element, panel_height_mm)
    else:
        raise NotImplementedError(f"Element type {element.element_type} not yet supported.")
