"""
Data models for structural elements.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ElementType(Enum):
    COLUMN = "Column"
    WALL = "Wall"
    SHEAR_WALL = "Shear Wall"
    SLAB = "Slab"


@dataclass
class StructuralElement:
    """Represents a structural element requiring formwork."""
    element_type: ElementType
    label: str              # e.g. "C1", "SW1"
    length_mm: float        # longer dimension (for walls: wall length)
    width_mm: float         # shorter dimension (for walls: wall thickness)
    height_mm: float        # casting height
    quantity: int = 1       # number of identical elements
    notes: str = ""

    @property
    def is_column(self) -> bool:
        return self.element_type == ElementType.COLUMN

    @property
    def is_wall(self) -> bool:
        return self.element_type in (ElementType.WALL, ElementType.SHEAR_WALL)

    def __str__(self):
        return (f"{self.label} ({self.element_type.value}) "
                f"{self.length_mm}x{self.width_mm}mm H={self.height_mm}mm "
                f"Qty={self.quantity}")


@dataclass
class PanelEntry:
    """A single panel type with quantity in a BOQ row."""
    size_label: str         # e.g. "600X3200", "OC80X3200"
    width_mm: float
    height_mm: float
    quantity: int
    is_corner: bool = False  # OC or IC type
    is_inner_corner: bool = False
    area_sqm: float = 0.0

    def __post_init__(self):
        if self.area_sqm == 0.0:
            self.area_sqm = round((self.width_mm * self.height_mm) / 1_000_000, 6)

    @property
    def total_area_sqm(self) -> float:
        return round(self.area_sqm * self.quantity, 4)


@dataclass
class ElementBOQ:
    """Complete formwork BOQ for one structural element."""
    element: StructuralElement
    panels: list[PanelEntry] = field(default_factory=list)
    spacer_mm: float = 0.0      # spacer gap used (if any)
    height_note: str = ""       # e.g. "2456MM" (panel stack height achieved)
    price_per_set: float = 0.0
    num_sets: int = 1
    grand_total: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def total_panel_area_sqm(self) -> float:
        return round(sum(p.total_area_sqm for p in self.panels), 4)


@dataclass
class ProjectBOQ:
    """Full project BOQ."""
    project_name: str = ""
    client_name: str = ""
    client_address: str = ""
    ipo_no: str = ""
    date: str = ""
    element_boqs: list[ElementBOQ] = field(default_factory=list)

    # Configuration
    panel_height_mm: float = 3200
    num_sets: int = 1
    gst_enabled: bool = True
    freight_amount: float = 0.0

    # Rates
    panel_rate_per_sqm: float = 0.0
    waller_rate_per_rm: float = 0.0
    tierod_rate_per_rm: float = 0.0
    prop_rate_per_unit: float = 0.0
    anchor_nut_rate_per_unit: float = 0.0
