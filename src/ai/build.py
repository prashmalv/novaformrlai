"""
Turn the model's findings into StructuralElements + BOQs with Nova's own logic.

Geometry always comes from the DXF digest when the model names a shape id;
the model's own numbers are used only when an element has no closed outline.
Every element gets checks: label/schedule size vs measured size, confidence.
"""
import re
from dataclasses import dataclass, field

from src.models.element import StructuralElement, ElementType
from src.engine.panel_optimizer import compute_boq, optimize_polygon_element
from src.dwg_parse.parse_nova_shear_walls import (
    _classify_polygon_corners, _compute_polygon_face_nets,
)

_SIZE_RE = re.compile(r'(\d{2,5}(?:\.\d+)?)\s*[xX×]\s*(\d{2,5}(?:\.\d+)?)')
SIZE_TOL_MM = 15.0      # label vs geometry may differ by plaster / rounding
LOW_CONFIDENCE = 0.6


@dataclass
class AIElement:
    element: StructuralElement
    boq: object
    shape_ids: list
    confidence: float
    checks: list = field(default_factory=list)   # human-readable warnings
    drawn_panels: list = field(default_factory=list)
    sources: list = field(default_factory=list)  # tiles that reported it

    @property
    def needs_review(self) -> bool:
        return bool(self.checks) or self.confidence < LOW_CONFIDENCE


def parse_size(text: str):
    """'SW 9 400x800' → (800.0, 400.0) as (long, short); None if no size."""
    m = _SIZE_RE.search(text or "")
    if not m:
        return None
    a, b = float(m.group(1)), float(m.group(2))
    return max(a, b), min(a, b)


def _norm_label(label: str) -> str:
    return re.sub(r'[\s\-_]+', '', (label or "").upper())


def _size_ok(want, got) -> bool:
    return abs(want[0] - got[0]) <= SIZE_TOL_MM and abs(want[1] - got[1]) <= SIZE_TOL_MM


def _kind_to_type(kind: str) -> ElementType:
    return ElementType.COLUMN if kind == "column" else ElementType.SHEAR_WALL


def _polygon_boq(elem: StructuralElement, pts: list, panel_h: float):
    """Same path as parse_nova_shear_walls: corner classes → face nets → DP."""
    corners = _classify_polygon_corners(pts)
    nets = _compute_polygon_face_nets(pts, corners)
    hunch = [c for c in corners if c.startswith("H")]
    elem.notes = (f"Polygon: {len(pts)} vertices, OC×{corners.count('OC80')}, "
                  f"IC×{corners.count('IC100')}" + (f", hunch×{len(hunch)}" if hunch else ""))
    return optimize_polygon_element(
        element=elem, face_nets=nets,
        oc_count=corners.count('OC80'), ic_count=corners.count('IC100'),
        product_height_mm=panel_h, hunch_list=hunch)


def build_elements(dg, findings: list, schedule: list,
                   panel_h: float, casting_h: float) -> list:
    """findings: [(tile_name, ElementFinding)], schedule: [ScheduleRow]."""
    sched = {}          # label → (first size, text); used for the mismatch check
    sched_all = {}      # label → [(size, floor)], every size the schedule gives
    for row in schedule:
        size = (max(row.length_mm, row.width_mm), min(row.length_mm, row.width_mm)) \
            if row.length_mm and row.width_mm else parse_size(row.size_text)
        for lb in row.labels:
            sched.setdefault(_norm_label(lb), (size, row.size_text))
            if size and all(not _size_ok(size, s) for s, _ in sched_all.get(_norm_label(lb), [])):
                sched_all.setdefault(_norm_label(lb), []).append((size, row.floor))

    # 1. One record per physical element. Overlapping tiles report the same
    #    shape twice -- keep the most confident report per shape id.
    by_shape = {}
    no_shape = {}
    out = []
    for tile, f in findings:
        if not _norm_label(f.label):
            # Unmarked outline: cannot be quoted or checked, so keep it out of
            # the BOQ but show it in the report.
            out.append(AIElement(element=None, boq=None, shape_ids=list(f.shape_ids),
                                 confidence=f.confidence, sources=[tile],
                                 checks=[f"no element mark: {f.reason}"]))
            continue
        ids = [s for s in f.shape_ids if dg.shape(s)]
        if ids:
            key = tuple(sorted(ids))
            if key not in by_shape or f.confidence > by_shape[key][1].confidence:
                by_shape[key] = (tile, f)
        else:
            size = (max(f.length_mm, f.width_mm), min(f.length_mm, f.width_mm)) \
                if f.length_mm and f.width_mm else parse_size(f.size_text)
            key = (_norm_label(f.label), size)
            if key not in no_shape or f.confidence > no_shape[key][1].confidence:
                no_shape[key] = (tile, f)

    # 2. Group instances of the same mark + same measured size.
    groups = {}
    for ids, (tile, f) in by_shape.items():
        shape = max((dg.shape(s) for s in ids), key=lambda s: s.length * s.width)
        key = (_norm_label(f.label) or ids[0], round(shape.length), round(shape.width), f.kind)
        groups.setdefault(key, []).append((tile, f, shape))
    for (lbl, size), (tile, f) in no_shape.items():
        key = (lbl or f"?{len(groups)}", round(size[0]) if size else 0,
               round(size[1]) if size else 0, f.kind)
        groups.setdefault(key, []).append((tile, f, None))

    for (lbl, _, _, kind), members in groups.items():
        tile, f, shape = max(members, key=lambda m: m[1].confidence)
        if f.size_variants:
            out += _variant_elements(f, members, shape, kind, panel_h, casting_h)
            continue
        checks = []

        if shape is not None:
            length, width = shape.length, shape.width
        else:
            size = (max(f.length_mm, f.width_mm), min(f.length_mm, f.width_mm)) \
                if f.length_mm and f.width_mm else parse_size(f.size_text)
            if size is None and _norm_label(f.label) in sched:
                size = sched[_norm_label(f.label)][0]
            if size is None:
                checks.append("no outline and no readable size - element skipped")
                out.append(AIElement(element=None, boq=None, shape_ids=[],
                                     confidence=f.confidence, checks=checks,
                                     sources=[m[0] for m in members]))
                continue
            length, width = size
            checks.append("size read from text, no outline in DXF")

        # Cross-check the measured outline against what the drawing says.
        claimed = parse_size(f.label) or parse_size(f.size_text)
        if claimed is None and _norm_label(f.label) in sched:
            claimed = sched[_norm_label(f.label)][0]
        if claimed and shape is not None and not _size_ok(claimed, (length, width)):
            checks.append(f"label/schedule says {claimed[0]:.0f}x{claimed[1]:.0f} "
                          f"but outline measures {length:.0f}x{width:.0f}")
        if f.confidence < LOW_CONFIDENCE:
            checks.append(f"model unsure ({f.confidence:.2f}): {f.reason}")

        elem = StructuralElement(
            element_type=_kind_to_type(kind),
            label=f.label or lbl,
            length_mm=round(length),
            width_mm=round(width),
            height_mm=casting_h,
            quantity=len(members),
            floor_label=f.floor,
            polygon_pts=list(shape.verts) if shape is not None else [],
        )
        if shape is not None:
            boq = _polygon_boq(elem, list(shape.verts), panel_h)
        else:
            boq = compute_boq(elem, panel_h)
        boq.num_sets = 1

        out.append(AIElement(
            element=elem, boq=boq,
            shape_ids=[s.id for _, _, s in members if s is not None],
            confidence=min(m[1].confidence for m in members),
            checks=checks, drawn_panels=f.drawn_panels,
            sources=sorted({m[0] for m in members})))

        # The schedule may give other sizes for this mark (floor-wise change
        # the plan outline doesn't show) -- quote those too, flagged.
        for size, floor in sched_all.get(_norm_label(f.label), []):
            if _size_ok(size, (length, width)) or (floor and floor == f.floor):
                continue
            extra = StructuralElement(
                element_type=_kind_to_type(kind), label=f.label or lbl,
                length_mm=round(size[0]), width_mm=round(size[1]),
                height_mm=casting_h, quantity=len(members), floor_label=floor,
                notes="size from schedule")
            xb = compute_boq(extra, panel_h)
            xb.num_sets = 1
            out.append(AIElement(
                element=extra, boq=xb, shape_ids=[], confidence=f.confidence,
                checks=[f"schedule gives {size[0]:.0f}x{size[1]:.0f}"
                        + (f" ({floor})" if floor else "") + " - not the drawn outline"],
                sources=sorted({m[0] for m in members})))
    out.sort(key=lambda a: (a.element is None, _label_sort_key(a.element.label if a.element else "")))
    return out


def _variant_elements(f, members, shape, kind, panel_h, casting_h) -> list:
    """One element per floor-wise size. The drawn outline is used for the
    variant it matches; other variants are rectangles from dimension text."""
    out = []
    for v in f.size_variants:
        size = (max(v.length_mm, v.width_mm), min(v.length_mm, v.width_mm))
        elem = StructuralElement(
            element_type=_kind_to_type(kind), label=f.label,
            length_mm=round(size[0]), width_mm=round(size[1]),
            height_mm=casting_h, quantity=len(members), floor_label=v.floor,
            notes=f"floor variant: {v.floor}")
        checks = []
        if shape is not None and _size_ok(size, (shape.length, shape.width)):
            elem.polygon_pts = list(shape.verts)
            boq = _polygon_boq(elem, list(shape.verts), panel_h)
        else:
            checks.append(f"{v.floor}: size from dimension text, not the drawn outline")
            boq = compute_boq(elem, panel_h)
        boq.num_sets = 1
        if f.confidence < LOW_CONFIDENCE:
            checks.append(f"model unsure ({f.confidence:.2f}): {f.reason}")
        out.append(AIElement(
            element=elem, boq=boq,
            shape_ids=[s.id for _, _, s in members if s is not None],
            confidence=min(m[1].confidence for m in members), checks=checks,
            drawn_panels=f.drawn_panels, sources=sorted({m[0] for m in members})))
    return out


def _label_sort_key(label: str):
    m = re.match(r'([A-Z\-]*?)(\d+)(.*)', label.upper())
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (label, 0, "")
