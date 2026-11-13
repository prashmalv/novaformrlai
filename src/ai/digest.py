"""
Drawing digest: a format-independent summary of a DXF for the vision model.

Every closed polyline becomes a Shape with an id (S1, S2 ...) and its TRUE size
measured along its own edges, so a 400x800 wall drawn at 30 degrees is still
reported as 400x800 (an axis-aligned bounding box would say 747x893).
Every text becomes a Text with an id (T1, T2 ...).
"""
import math
from dataclasses import dataclass, field

import ezdxf
import ezdxf.path

from src.dwg_parse.normalize_dxf_code import _normalize_dxf_codes
from src.dwg_parse.collect_attributes import _collect_attribute_texts

# Drawings are assumed to be in mm. $INSUNITS is NOT trusted: CLIENT-1.dxf
# says inches but is drawn in mm. Callers pass unit_factor to override.

# A shape is an element candidate only inside this size window (mm).
# Thinner than MIN_SIDE is a panel / hatch strip / line; longer than MAX_SIDE
# is a sheet border or plan outline (real elements stop near 12 m, junk starts
# at 25 m in CLIENT DRAWING.dxf).
MIN_SIDE = 100.0
MAX_SIDE = 20000.0


@dataclass
class Shape:
    id: str
    verts: list                 # [(x, y), ...] in mm, drawing coordinates
    layer: str
    length: float               # true long side (mm), min-area rectangle
    width: float                # true short side (mm)
    angle: float                # rotation of the long side, degrees 0-180
    cx: float
    cy: float
    bbox: tuple                 # (x0, y0, x1, y1) axis-aligned, for tiling
    candidate: bool = True

    @property
    def n_verts(self) -> int:
        return len(self.verts)


@dataclass
class Text:
    id: str
    x: float
    y: float
    text: str
    height: float
    layer: str


@dataclass
class Digest:
    path: str
    unit_factor: float
    shapes: list = field(default_factory=list)
    texts: list = field(default_factory=list)

    @property
    def candidates(self) -> list:
        return [s for s in self.shapes if s.candidate]

    def shape(self, sid: str):
        return self._by_id.get(sid)

    def __post_init__(self):
        self._by_id = {}
        self.texts_by_id = {}

    def index(self):
        self._by_id = {s.id: s for s in self.shapes}
        self.texts_by_id = {t.id: t for t in self.texts}


def _min_area_rect(pts: list) -> tuple:
    """(long, short, angle_deg) of the minimum-area rectangle around pts.

    Tries each edge direction of the polygon; for a rectangle or an
    orthogonal L/T shape the best direction is one of its own edges.
    """
    best = None
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if math.hypot(x2 - x1, y2 - y1) < 1e-6:
            continue
        a = math.atan2(y2 - y1, x2 - x1)
        c, s = math.cos(-a), math.sin(-a)
        xs = [px * c - py * s for px, py in pts]
        ys = [px * s + py * c for px, py in pts]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if best is None or w * h < best[0]:
            ang = math.degrees(a) if w >= h else math.degrees(a) + 90
            best = (w * h, max(w, h), min(w, h), ang % 180)
    if best is None:
        return 0.0, 0.0, 0.0
    return best[1], best[2], best[3]


def _dedupe_verts(pts: list, tol: float = 0.5) -> list:
    """Drop repeated and closing vertices so corner counts are not inflated."""
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > tol:
            out.append(p)
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= tol:
        out.pop()
    return out


def _closed_polylines(msp):
    """Yield (verts, layer) for closed polylines in modelspace and one level of blocks."""
    def from_entity(e):
        t = e.dxftype()
        if t == "LWPOLYLINE" and e.closed:
            return [[(p[0], p[1]) for p in e.get_points("xy")]]
        if t == "POLYLINE" and e.is_closed and e.is_2d_polyline:
            return [[(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]]
        if t == "HATCH":
            # Client plans often show a column only as a hatched section,
            # with no closed polyline around it.
            try:
                return [[(v.x, v.y) for v in p.flattening(1.0)]
                        for p in ezdxf.path.from_hatch(e)]
            except Exception:
                return None
        return None

    for e in msp:
        if e.dxftype() == "INSERT":
            try:
                subs = list(e.virtual_entities())
            except Exception:
                continue
            for v in subs:
                for pts in from_entity(v) or []:
                    yield pts, v.dxf.get("layer", "")
            continue
        for pts in from_entity(e) or []:
            yield pts, e.dxf.get("layer", "")


def _texts(msp):
    """Yield (x, y, text, height, layer) for TEXT, MTEXT and block attributes."""
    for e in msp.query("TEXT"):
        try:
            yield (e.dxf.insert.x, e.dxf.insert.y,
                   _normalize_dxf_codes(e.dxf.text).strip(),
                   e.dxf.get("height", 0.0), e.dxf.get("layer", ""))
        except Exception:
            pass
    for e in msp.query("MTEXT"):
        try:
            yield (e.dxf.insert.x, e.dxf.insert.y,
                   _normalize_dxf_codes(e.plain_text()).strip(),
                   e.dxf.get("char_height", 0.0), e.dxf.get("layer", ""))
        except Exception:
            pass
    for x, y, raw in _collect_attribute_texts(msp):
        try:
            yield x, y, _normalize_dxf_codes(raw).strip(), 0.0, ""
        except Exception:
            pass


def build_digest(dxf_path: str, doc=None, unit_factor: float = 1.0) -> Digest:
    """Read a DXF and return its Digest (all coordinates in mm).

    unit_factor converts drawing units to mm (1000 for a drawing in metres).
    """
    if doc is None:
        doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    k = float(unit_factor)
    dg = Digest(path=dxf_path, unit_factor=k)

    seen = set()
    for raw, layer in _closed_polylines(msp):
        pts = _dedupe_verts([(float(x) * k, float(y) * k) for x, y in raw])
        if len(pts) < 3:
            continue
        key = tuple(sorted((round(x), round(y)) for x, y in pts))
        if key in seen:          # same outline drawn twice (common in CAD)
            continue
        seen.add(key)
        length, width, angle = _min_area_rect(pts)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        dg.shapes.append(Shape(
            id=f"S{len(dg.shapes) + 1}", verts=pts, layer=layer,
            length=round(length, 1), width=round(width, 1), angle=round(angle, 1),
            cx=sum(xs) / len(xs), cy=sum(ys) / len(ys),
            bbox=(min(xs), min(ys), max(xs), max(ys)),
            candidate=MIN_SIDE <= width and length <= MAX_SIDE,
        ))

    for x, y, txt, h, layer in _texts(msp):
        if txt:
            dg.texts.append(Text(id=f"T{len(dg.texts) + 1}", x=float(x) * k, y=float(y) * k,
                                 text=txt, height=float(h) * k, layer=layer))
    dg.index()
    return dg


def shape_line(s: Shape) -> str:
    """One compact line describing a shape for the prompt."""
    rot = "" if s.angle % 90 < 0.5 or s.angle % 90 > 89.5 else f" rot={s.angle:.0f}deg"
    return (f"{s.id}: {s.length:.0f}x{s.width:.0f}mm verts={s.n_verts}{rot}"
            f" layer={s.layer or '-'} at=({s.cx:.0f},{s.cy:.0f})")
