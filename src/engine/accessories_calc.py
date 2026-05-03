"""
Accessories Calculator.

Rules derived from Nova Formworks Excel quotations (Client 1, 2, 3).

FOR COLUMNS (pin-connection system):
  - PIN 50MM: connects panels horizontally (side by side)
  - PIN 20MM: at OC corners
  - PIN 80MM: at stacking joints (when panel rows stacked)

FOR WALLS / SHEAR WALLS (waller + tierod system):
  - WALLERS: horizontal stiffeners on each face, one per ~500mm height
  - TIERODS: through wall, at each waller × column position (~600mm spacing)
  - WING NUTS: tierod_count × 2
  - PVC CONES: tierod_count × 2 (one per tierod end)
  - Pins for panel-to-panel connections
"""
import math
from dataclasses import dataclass, field
from src.models.element import StructuralElement, ElementType, ElementBOQ


# Standard waller sizes (m)
STANDARD_WALLER_LENGTHS = [3.0, 2.8, 2.5, 2.2, 2.0, 1.8, 1.5, 1.2, 1.0, 0.8, 0.6, 0.5, 0.35]

# Standard tierod lengths (m)
STANDARD_TIEROD_LENGTHS = [3.0, 2.7, 2.2, 2.0, 1.5, 1.2, 1.0, 0.8, 0.6, 0.5]

WALLER_WIDTH_MM = 40       # waller section width
TIEROD_EXTRA_MM = 150      # extra length per side for cone + wingnut
WALLER_V_SPACING_MM = 500  # vertical spacing between waller rows
TIEROD_H_SPACING_MM = 600  # horizontal spacing between tierods
PINS_PER_JOINT = 4         # pins per panel-to-panel joint


@dataclass
class AccessoryItem:
    name: str
    size_label: str   # e.g. "WALLER 3.0M", "TIEROD 0.5M", "PIN 50MM"
    quantity: float
    unit: str         # "nos", "rm" (running meters)
    length_m: float = 0.0
    total_length_m: float = 0.0
    rate: float = 0.0
    amount: float = 0.0
    is_estimated: bool = False


@dataclass
class AccessoriesBOQ:
    element: StructuralElement
    items: list[AccessoryItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    high_wall_warning: bool = False  # extra check when height > 4500mm


def _nearest_standard_length(required_m: float, options: list[float]) -> float:
    """Find the smallest standard size that is >= required length."""
    for size in sorted(options):
        if size >= required_m - 0.02:  # 20mm tolerance
            return size
    return max(options)


def _count_panel_joints(panels_per_face_combo: list[int]) -> int:
    """Number of side-by-side joints in one row of panels on one face."""
    return max(0, len(panels_per_face_combo) - 1)


def calculate_accessories_column(
    element: StructuralElement,
    boq: ElementBOQ,
    panel_height_mm: float,
) -> AccessoriesBOQ:
    """
    Column accessories: pins at panel joints.
    """
    acc_boq = AccessoriesBOQ(element=element)
    h = element.height_mm
    rows = max(1, math.ceil(h / panel_height_mm))

    # Count total panels (excluding OC)
    total_flat_panels = sum(
        p.quantity for p in boq.panels if not p.is_corner
    )
    total_oc = sum(p.quantity for p in boq.panels if p.is_corner)

    # Horizontal joints (between panels side by side)
    # Each face in each row has joints = (panels_in_face - 1)
    # Total face panels = total_flat_panels / (rows × 4 faces) per face per row
    # Approximate: joints_per_row_per_face ≈ panels_per_face - 1
    if total_flat_panels > 0:
        panels_per_face_per_row = total_flat_panels / (4 * rows)
        joints_h = max(0, panels_per_face_per_row - 1) * 4 * rows
    else:
        joints_h = 0

    # Vertical stacking joints (between rows)
    stacking_joints = total_flat_panels / rows * (rows - 1) if rows > 1 else 0

    # OC corner joints
    oc_joints = total_oc

    # Pins
    pin_50 = round(joints_h * PINS_PER_JOINT)
    pin_80 = round(stacking_joints * 2)
    pin_20 = round(oc_joints * 2)

    if pin_50 > 0:
        acc_boq.items.append(AccessoryItem(
            name="Connecting Pin", size_label="PIN 50MM",
            quantity=pin_50, unit="nos", rate=0
        ))
    if pin_80 > 0:
        acc_boq.items.append(AccessoryItem(
            name="Connecting Pin", size_label="PIN 80MM",
            quantity=pin_80, unit="nos", rate=0
        ))
    if pin_20 > 0:
        acc_boq.items.append(AccessoryItem(
            name="Connecting Pin", size_label="PIN 20MM",
            quantity=pin_20, unit="nos", rate=0
        ))

    acc_boq.notes.append(f"Rows: {rows}  |  Flat panels: {total_flat_panels}  |  OC: {total_oc}")

    if h > 4500:
        acc_boq.high_wall_warning = True
        acc_boq.notes.append(
            f"⚠  HEIGHT {h:.0f}mm > 4500mm: Engineer review required for panel loading."
        )
    return acc_boq


def calculate_accessories_wall(
    element: StructuralElement,
    boq: ElementBOQ,
    panel_height_mm: float,
) -> AccessoriesBOQ:
    """
    Wall/Shear Wall accessories: wallers, tierods, wing nuts, PVC cones, pins.
    """
    acc_boq = AccessoriesBOQ(element=element)
    h = element.height_mm
    L = element.length_mm   # wall length (face dimension)
    T = element.width_mm    # wall thickness

    rows = max(1, math.ceil(h / panel_height_mm))

    # ── Wallers ──
    # Standard waller length = face length (L)
    waller_len_m = L / 1000
    std_waller = _nearest_standard_length(waller_len_m, STANDARD_WALLER_LENGTHS)

    # Waller rows = ceil(height / WALLER_V_SPACING) + 1
    waller_rows = math.ceil(h / WALLER_V_SPACING_MM) + 1
    # Both faces × waller_rows
    waller_count = waller_rows * 2
    total_waller_rm = round(waller_count * std_waller, 2)

    acc_boq.items.append(AccessoryItem(
        name="Waller", size_label=f"WALLER {std_waller:.1f}M",
        quantity=waller_count, unit="nos",
        length_m=std_waller, total_length_m=total_waller_rm, rate=0
    ))

    # ── Tierods ──
    # Length = thickness + 2 × extra (cone + wingnut threading)
    tierod_len_m = (T + 2 * TIEROD_EXTRA_MM) / 1000
    std_tierod = _nearest_standard_length(tierod_len_m, STANDARD_TIEROD_LENGTHS)

    # Horizontal positions of tierods = ceil(L / TIEROD_H_SPACING)
    tierod_positions_h = math.ceil(L / TIEROD_H_SPACING_MM)

    # Tierod rows = waller_rows (one set of tierods per waller row)
    # But not at every waller row — alternate, or at every other row
    # Conservative: tierod at every waller row
    tierod_count = waller_rows * tierod_positions_h
    total_tierod_rm = round(tierod_count * std_tierod, 2)

    acc_boq.items.append(AccessoryItem(
        name="Tierod", size_label=f"TIE ROD 16MM ({std_tierod:.1f}M)",
        quantity=tierod_count, unit="nos",
        length_m=std_tierod, total_length_m=total_tierod_rm, rate=0
    ))

    # ── Wing Nuts & PVC Cones ──
    wing_nut_count = tierod_count * 2
    pvc_cone_count = tierod_count * 2

    acc_boq.items.append(AccessoryItem(
        name="Wing Nut", size_label="WING NUT",
        quantity=wing_nut_count, unit="nos", rate=0
    ))
    acc_boq.items.append(AccessoryItem(
        name="PVC Cone", size_label="PVC CONE",
        quantity=pvc_cone_count, unit="nos", rate=0
    ))

    # ── Pins ──
    total_flat_panels = sum(p.quantity for p in boq.panels if not p.is_corner)
    if total_flat_panels > 0:
        panels_per_row = total_flat_panels / (2 * rows)  # 2 faces
        joints_h = max(0, panels_per_row - 1) * 2 * rows
        pin_50 = round(joints_h * PINS_PER_JOINT)
        if pin_50 > 0:
            acc_boq.items.append(AccessoryItem(
                name="Connecting Pin", size_label="PIN 50MM",
                quantity=pin_50, unit="nos", rate=0
            ))

    acc_boq.notes.append(
        f"Wallers: {waller_rows} rows × {std_waller}m  |  "
        f"Tierods: {waller_rows} rows × {tierod_positions_h} positions × {std_tierod}m  |  "
        f"Wall T={T}mm"
    )

    if h > 4500:
        acc_boq.high_wall_warning = True
        acc_boq.notes.append(
            f"⚠  HEIGHT {h:.0f}mm > 4500mm: Increase tierod frequency. Engineer review MANDATORY."
        )

    return acc_boq


def calculate_accessories(
    element: StructuralElement,
    boq: ElementBOQ,
    panel_height_mm: float = 3200,
) -> AccessoriesBOQ:
    """Main entry: compute accessories for any element."""
    if element.is_column:
        return calculate_accessories_column(element, boq, panel_height_mm)
    else:
        return calculate_accessories_wall(element, boq, panel_height_mm)


def aggregate_accessories(acc_boqs: list[AccessoriesBOQ], num_sets: int = 1) -> dict:
    """
    Aggregate all element accessories into project summary.
    Returns: { size_label: { quantity, unit, length_m, total_length_m } }
    """
    from collections import defaultdict
    summary = defaultdict(lambda: {
        'name': '', 'unit': 'nos', 'quantity': 0,
        'length_m': 0, 'total_length_m': 0.0, 'rate': 0, 'amount': 0
    })

    for acc_boq in acc_boqs:
        elem_qty = acc_boq.element.quantity * num_sets
        for item in acc_boq.items:
            key = item.size_label
            summary[key]['name'] = item.name
            summary[key]['unit'] = item.unit
            summary[key]['length_m'] = item.length_m
            summary[key]['quantity'] += item.quantity * elem_qty
            summary[key]['total_length_m'] += item.total_length_m * elem_qty
            summary[key]['rate'] = item.rate

    # Sort: Wallers → Tierods → Wing Nuts → PVC Cones → Pins
    order = ['WALLER', 'TIE ROD', 'WING NUT', 'PVC CONE', 'PIN']

    def sort_key(kv):
        key = kv[0]
        for i, o in enumerate(order):
            if o in key:
                return i
        return 99

    return dict(sorted(summary.items(), key=sort_key))
