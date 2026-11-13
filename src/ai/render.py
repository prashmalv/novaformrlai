"""
Render a DXF into PNG tiles for the vision model.

The drawing is drawn once with ezdxf's matplotlib backend; each tile is the
same figure zoomed to one window. Candidate shapes get their digest id
(S12, S13 ...) printed on them in red, so the model can answer in ids and
the exact geometry is then looked up in the digest ("set-of-marks").
"""
import io
import math
from dataclasses import dataclass, field

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon, Rectangle

from ezdxf import bbox
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing.config import (
    Configuration, BackgroundPolicy, ColorPolicy, HatchPolicy,
)

from src.ai.digest import Digest

TILE_PX = 1568          # long edge sent to the model
TEXT_PX = 14            # target on-screen size of a median text
OVERLAP = 0.15          # fraction of a tile shared with its neighbour
MAX_TILES = 40


@dataclass
class Tile:
    name: str                   # "R1C2"
    bounds: tuple               # (x0, y0, x1, y1) in mm
    png: bytes = b""
    shape_ids: list = field(default_factory=list)
    text_ids: list = field(default_factory=list)


def _extents(dg: Digest) -> tuple:
    """Bounds of the drawing content, ignoring the 0.5 % most distant stray points."""
    xs = [s.cx for s in dg.shapes] + [t.x for t in dg.texts]
    ys = [s.cy for s in dg.shapes] + [t.y for t in dg.texts]
    xs.sort()
    ys.sort()
    cut = int(len(xs) * 0.005)
    lo, hi = cut, len(xs) - 1 - cut
    pad = 0.02 * max(xs[hi] - xs[lo], ys[hi] - ys[lo], 1.0)
    return xs[lo] - pad, ys[lo] - pad, xs[hi] + pad, ys[hi] + pad


def _tile_size(dg: Digest, ext: tuple) -> float:
    """Tile edge in mm so a median-height text renders at about TEXT_PX pixels."""
    hs = sorted(t.height for t in dg.texts if t.height > 0)
    text_h = hs[len(hs) // 2] if hs else 150.0
    size = TILE_PX * text_h / TEXT_PX
    w, h = ext[2] - ext[0], ext[3] - ext[1]
    # Never more tiles than MAX_TILES: grow the tile until the grid fits.
    while _grid_count(w, h, size) > MAX_TILES:
        size *= 1.25
    return min(size, max(w, h))


def _grid_count(w: float, h: float, size: float) -> int:
    step = size * (1 - OVERLAP)
    return math.ceil(max(w - size, 0) / step + 1) * math.ceil(max(h - size, 0) / step + 1)


def _grid(ext: tuple, size: float) -> list:
    x0, y0, x1, y1 = ext
    step = size * (1 - OVERLAP)
    nx = math.ceil(max(x1 - x0 - size, 0) / step + 1)
    ny = math.ceil(max(y1 - y0 - size, 0) / step + 1)
    tiles = []
    for r in range(ny):             # row 1 = top of the drawing
        ty1 = y1 - r * step
        for c in range(nx):
            tx0 = x0 + c * step
            tiles.append(Tile(name=f"R{r + 1}C{c + 1}",
                              bounds=(tx0, ty1 - size, tx0 + size, ty1)))
    return tiles


def _inside(b: tuple, x: float, y: float) -> bool:
    return b[0] <= x <= b[2] and b[1] <= y <= b[3]


def _png(fig, px: int) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=px / fig.get_figwidth())
    return buf.getvalue()


def _new_axes():
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_aspect("equal")
    return fig, ax


def _entity_boxes(msp) -> list:
    """[(entity, (x0, y0, x1, y1))] in drawing units, computed once."""
    cache = bbox.Cache()
    out = []
    for e in msp:
        try:
            ext = bbox.extents([e], fast=True, cache=cache)
        except Exception:
            continue
        if ext.has_data:
            out.append((e, (ext.extmin.x, ext.extmin.y, ext.extmax.x, ext.extmax.y)))
    return out


def _draw(ax, ctx, entities):
    Frontend(ctx, MatplotlibBackend(ax), config=_CFG).draw_entities(entities)


# Hatch patterns (concrete dots) were most of the render time and add nothing
# the model needs; their outline still shows the section.
_CFG = Configuration(background_policy=BackgroundPolicy.WHITE,
                     color_policy=ColorPolicy.MONOCHROME_LIGHT_BG,
                     hatch_policy=HatchPolicy.SHOW_OUTLINE)


def render_tiles(dg: Digest, doc) -> tuple:
    """Return (overview_png, tiles). Empty tiles are dropped.

    Each tile draws only the DXF entities that overlap it, so a heavy drawing
    costs about one full render in total instead of one per tile.
    """
    # Geometry is drawn in DXF units; marks are placed in mm, so scale back.
    k = dg.unit_factor
    ctx = RenderContext(doc)
    boxes = _entity_boxes(doc.modelspace())

    ext = _extents(dg)
    size = _tile_size(dg, ext)
    tiles = _grid(ext, size)

    # Overview: whole drawing (hatches skipped -- slow and unreadable at this
    # scale) with the tile grid numbered, no shape marks.
    fig, ax = _new_axes()
    _draw(ax, ctx, (e for e, _ in boxes if e.dxftype() != "HATCH"))
    grid_artists = []
    for t in tiles:
        b = t.bounds
        grid_artists.append(ax.add_patch(Rectangle(
            (b[0] / k, b[1] / k), (b[2] - b[0]) / k, (b[3] - b[1]) / k,
            fill=False, ec="blue", lw=0.6, alpha=0.6)))
        grid_artists.append(ax.text((b[0] + b[2]) / 2 / k, (b[1] + b[3]) / 2 / k, t.name,
                                    color="blue", fontsize=9, ha="center", va="center", alpha=0.8))
    ax.set_xlim(ext[0] / k, ext[2] / k)
    ax.set_ylim(ext[1] / k, ext[3] / k)
    overview = _png(fig, TILE_PX)
    plt.close(fig)

    kept = []
    for t in tiles:
        b = t.bounds
        t.shape_ids = [s.id for s in dg.candidates if _inside(b, s.cx, s.cy)]
        t.text_ids = [x.id for x in dg.texts if _inside(b, x.x, x.y)]
        if not t.shape_ids and not t.text_ids:
            continue
        bu = (b[0] / k, b[1] / k, b[2] / k, b[3] / k)
        fig, ax = _new_axes()
        _draw(ax, ctx, (e for e, eb in boxes
                        if eb[0] <= bu[2] and eb[2] >= bu[0] and eb[1] <= bu[3] and eb[3] >= bu[1]))
        marks = []
        fs = 8
        for sid in t.shape_ids:
            s = dg.shape(sid)
            marks.append(ax.add_patch(MplPolygon(
                [(x / k, y / k) for x, y in s.verts], closed=True,
                fill=False, ec="red", lw=0.8)))
            marks.append(ax.text(s.cx / k, s.cy / k, sid, color="red", fontsize=fs,
                                 ha="center", va="center", fontweight="bold",
                                 bbox=dict(boxstyle="round,pad=0.1", fc="white",
                                           ec="red", lw=0.4, alpha=0.85)))
        ax.set_xlim(bu[0], bu[2])
        ax.set_ylim(bu[1], bu[3])
        t.png = _png(fig, TILE_PX)
        plt.close(fig)
        kept.append(t)

    return overview, kept
