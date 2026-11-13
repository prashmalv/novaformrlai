"""
Structured outputs the vision model must return (Pydantic → JSON schema).
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Stage 1: overview ─────────────────────────────────────────────────────────

TileRole = Literal[
    "plan",            # plan view with elements to count
    "schedule",        # column / shear-wall schedule table
    "nova_output",     # Nova formwork drawing (panels drawn around elements)
    "elevation",       # elevation / section / detail -- never counted
    "duplicate_plan",  # repeat of a plan already chosen (other floor copy, enlarged detail)
    "title_or_notes",  # title block, legends, general notes
    "empty",
]


class TilePlan(BaseModel):
    tile: str = Field(description="Tile name, e.g. R2C3")
    role: TileRole
    sheet: str = Field(description="Short name of the sheet/view this tile belongs to, e.g. 'client GA plan', 'OUT PUT-1'")


class OverviewResult(BaseModel):
    drawing_kind: Literal["client_drawing", "nova_output", "mixed", "unknown"]
    count_from: str = Field(description="Which sheet(s) the element list should be taken from, and why")
    tiles: list[TilePlan]
    floor_or_casting_height_mm: Optional[int] = Field(
        None, description="Casting / floor height if written anywhere on the drawing")
    notes: str = ""


# ── Stage 2: tile extraction ──────────────────────────────────────────────────

ElementKind = Literal["column", "shear_wall", "wall"]


class SizeVariant(BaseModel):
    floor: str = Field(description="e.g. 'UPTO 2ND FLOOR', 'ABOVE 2ND FLOOR'")
    length_mm: float
    width_mm: float


class ElementFinding(BaseModel):
    label: str = Field(description="Element mark as written, e.g. C1, SW12, P101. Empty if unlabelled")
    kind: ElementKind
    shape_ids: list[str] = Field(
        description="Red S-ids of the closed outline(s) that ARE this element's concrete section. "
                    "Empty if the outline has no red id.")
    size_text: str = Field("", description="Size as written in the label/dimensions, e.g. '900x600', 'AS PER PLAN'")
    length_mm: Optional[float] = Field(None, description="Long side read from text/dimensions (only if no shape id)")
    width_mm: Optional[float] = Field(None, description="Short side read from text/dimensions (only if no shape id)")
    floor: str = ""
    size_variants: list[SizeVariant] = Field(
        default_factory=list,
        description="Only when the drawing gives different sizes for different floors "
                    "(dimension text like 'UPTO 2ND FLOOR 600 / ABOVE 2ND FLOOR 450'): one entry per size")
    drawn_panels: list[str] = Field(
        default_factory=list,
        description="Only on Nova output sheets: panel widths written around this element, "
                    "e.g. ['OC80','600','600','300','OC80', ...] in order round the outline")
    confidence: float = Field(description="0-1")
    reason: str = Field(description="One short sentence: why this is the element and this label")


class ScheduleRow(BaseModel):
    labels: list[str]
    kind: ElementKind
    size_text: str
    length_mm: Optional[float] = None
    width_mm: Optional[float] = None
    floor: str = ""


class TileResult(BaseModel):
    elements: list[ElementFinding]
    schedule_rows: list[ScheduleRow] = Field(default_factory=list)
    notes: str = ""
