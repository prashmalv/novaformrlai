"""
Read structural elements from a PDF or image drawing with a vision model.

Unlike the DXF pipeline there is no geometry to measure, so sizes come from
what is written on the drawing (schedule tables, labels, dimensions) and
counts from the plan. Every element carries the model's confidence and where
its size came from, and is flagged for review in the software.

Per page: (1) one request with the whole page plus zoomed tiles reads the
element list and sizes (schedule); (2) each tile is then asked separately
for every element mark it shows and where, and the marks are de-duplicated
in page coordinates, so the count is done by code, not by the model.
"""
from concurrent.futures import ThreadPoolExecutor
import io
import math
from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel, Field

from src.ai.llm import chat_structured, LLMError, Usage

MAX_PAGES = 8
IMG_PX = 1568           # long edge of each image sent
RENDER_PX = 4200        # page render size before tiling
OVERLAP = 0.12
MAX_TILES = 30
# Native tile size: GPT (high detail) shrinks every image to ~768 px on the
# short side, so its tiles must be small to keep labels readable; Claude
# keeps ~1500 px.
TILE_NATIVE = {"azure": 900, "claude": 1500}


class DrawnElement(BaseModel):
    label: str = Field(description="Element mark exactly as written, e.g. C1, SW3, P12")
    kind: Literal["column", "shear_wall", "wall"]
    length_mm: float = Field(description="Longer side in mm (convert inches/feet: 1 inch = 25.4 mm)")
    width_mm: float = Field(description="Shorter side in mm")
    quantity: int = Field(description="How many of this mark with this size appear on the PLAN of this page; 0 if the page has no plan")
    floor: Optional[str] = Field(None, description="Floor / level if the drawing gives sizes per floor")
    size_source: Literal["schedule", "label_text", "dimension", "estimated"]
    confidence: float = Field(description="0-1: how sure you are of size AND count")
    note: str = Field("", description="Anything the estimator should check")


class PageResult(BaseModel):
    page_kind: Literal["plan_with_schedule", "plan", "schedule_only", "nova_output", "elevation_or_detail", "other"]
    units_seen: Literal["mm", "inch", "feet_inch", "metre", "unknown"]
    elements: list[DrawnElement]
    casting_height_mm: Optional[int] = Field(None, description="Floor-to-floor / casting height if written")
    notes: str = ""


SYSTEM = """You read construction drawings for Nova Formworks, which quotes column and shear-wall formwork (shuttering).
From the drawing page you are given, list every vertical concrete element that needs formwork: columns (C1, C2, COL-1, P1 ...) and shear walls / RCC walls (SW1, W1, LW1 ...). Ignore beams, slabs, footings, rafts, stairs, brick walls, doors, windows, furniture.

How to read it:
- Image 1 is the whole page. The following images are zoomed tiles of the same page (left-to-right, top-to-bottom, overlapping) - use them to read small text. COUNT on the whole page, and never count an element twice because it appears in two overlapping tiles.
- Sizes: take them from the column / wall schedule table if there is one, else from the label text (e.g. "C1 (300x600)"), else from dimensions. Convert to mm: 1 inch = 25.4 mm (9" = 229, 12" = 305, 18" = 457, 1'-6" = 457). length_mm is the longer side.
- Quantity: how many times each mark appears on the plan. Look at every column position on the plan, including small ones near the edges. If a size schedule exists but the plan marks are unreadable, set quantity from what you can see and lower the confidence.
- If the same mark has different sizes on different floors, return one entry per floor size with the floor filled in.
- Only if the page has no plan (just a schedule), return the schedule sizes with quantity 0.
- Be honest: confidence below 0.6 when the label or size is hard to read or the count is uncertain, and say why in note.
"""


class Mark(BaseModel):
    label: str = Field(description="Element mark as written, e.g. C1")
    x: float = Field(description="Horizontal position of the element in this image, 0 = left edge, 1 = right edge")
    y: float = Field(description="Vertical position, 0 = top edge, 1 = bottom edge")


class TileMarks(BaseModel):
    marks: list[Mark]


COUNT_SYSTEM = """You look at one zoomed piece of a construction drawing. List every column / shear-wall position on the FLOOR PLAN in this image whose element mark (C1, C4, SW2, P3 ...) you can read, with its position in this image.
- One entry per physical element on the plan (a filled or outlined section with its mark next to it).
- Do NOT list marks that are captions of schedule tables, column detail / reinforcement drawings, legends or title blocks.
- Include elements cut by the image edge if the mark is readable.
- If nothing qualifies, return an empty list."""

DEDUP_RADIUS = 0.02     # fraction of the page's long edge


@dataclass
class ReadResult:
    elements: list = field(default_factory=list)   # merged dicts, see _merge
    pages: list = field(default_factory=list)      # PageResult per page
    usage: Usage = field(default_factory=Usage)
    casting_height_mm: Optional[int] = None
    warnings: list = field(default_factory=list)


def _page_images(path: str) -> list:
    """List of PIL images, one per page (PDF) or one (image file)."""
    from PIL import Image
    if path.lower().endswith(".pdf"):
        import fitz
        doc = fitz.open(path)
        out = []
        for i, page in enumerate(doc):
            if i >= MAX_PAGES:
                break
            zoom = RENDER_PX / max(page.rect.width, page.rect.height)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            out.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        return out
    img = Image.open(path)
    img.load()
    return [img.convert("RGB")]


def _png(img, long_edge: int = IMG_PX) -> bytes:
    from PIL import Image
    w, h = img.size
    k = min(1.0, long_edge / max(w, h))
    if k < 1.0:
        img = img.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _tiles(img, tile_px: int) -> list:
    """[(png, (x0, y0, x1, y1))]: overlapping tiles of about tile_px
    (just the whole image when it is small)."""
    w, h = img.size
    parts = []
    if max(w, h) <= tile_px * 1.3:
        return [(_png(img), (0, 0, w, h))]
    nx = max(1, math.ceil(w / tile_px))
    ny = max(1, math.ceil(h / tile_px))
    while nx * ny > MAX_TILES:
        tile_px *= 1.2
        nx, ny = math.ceil(w / tile_px), math.ceil(h / tile_px)
    tw, th = w / nx, h / ny
    for r in range(ny):
        for c in range(nx):
            x0 = max(0, int(c * tw - tw * OVERLAP))
            y0 = max(0, int(r * th - th * OVERLAP))
            x1 = min(w, int((c + 1) * tw + tw * OVERLAP))
            y1 = min(h, int((r + 1) * th + th * OVERLAP))
            parts.append((_png(img.crop((x0, y0, x1, y1))), (x0, y0, x1, y1)))
    return parts


def _norm(label: str) -> str:
    return "".join(ch for ch in label.upper() if ch.isalnum())


def _count_marks(model, settings, img, tiles, usage: Usage) -> dict:
    """{normalised label: count} from per-tile mark positions."""
    def one(t):
        png, _ = t
        r, u = chat_structured(model, COUNT_SYSTEM, [{"role": "user", "content": [("image", png)]}],
                               TileMarks, settings, max_tokens=8000, effort="low")
        return r, u
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(one, tiles))
    w, h = img.size
    radius = DEDUP_RADIUS * max(w, h)
    points = {}                  # label -> [(x, y)]
    for (r, u), (_, (x0, y0, x1, y1)) in zip(results, tiles):
        usage.add(u)
        for m in r.marks:
            px = x0 + min(max(m.x, 0), 1) * (x1 - x0)
            py = y0 + min(max(m.y, 0), 1) * (y1 - y0)
            pts = points.setdefault(_norm(m.label), [])
            if all((px - qx) ** 2 + (py - qy) ** 2 > radius ** 2 for qx, qy in pts):
                pts.append((px, py))
    return {k: len(v) for k, v in points.items()}


def read_drawing(path: str, settings: dict, progress=None) -> ReadResult:
    """Blocking - run off the UI thread. Raises LLMError."""
    model = settings.get("drawing_model") or settings["chat_model"]
    pages = _page_images(path)
    if not pages:
        raise LLMError("No pages found in the file")
    res = ReadResult()
    for i, img in enumerate(pages, 1):
        if progress:
            progress(f"Reading page {i} of {len(pages)}…")
        tiles = _tiles(img, TILE_NATIVE["azure" if model.startswith("azure:") else "claude"])
        imgs = [_png(img)] + ([b for b, _ in tiles] if len(tiles) > 1 else [])
        content = [("text", f"Page {i} of {len(pages)}. Image 1 = whole page"
                            + (f", images 2-{len(imgs)} = zoomed tiles." if len(imgs) > 1 else "."))]
        content += [("image", b) for b in imgs]
        page, u = chat_structured(model, SYSTEM, [{"role": "user", "content": content}],
                                  PageResult, settings, max_tokens=16000, effort="medium")
        res.usage.add(u)
        if page.page_kind in ("plan", "plan_with_schedule"):
            if progress:
                progress(f"Counting elements on page {i} ({len(tiles)} parts)…")
            counts = _count_marks(model, settings, img, tiles, res.usage)
            _apply_counts(page, counts, res.warnings, i)
        res.pages.append(page)
        if page.casting_height_mm and not res.casting_height_mm:
            res.casting_height_mm = page.casting_height_mm
    res.elements = _merge(res.pages)
    if len(pages) > 1:
        res.warnings.append(f"{len(pages)} pages read - counts from different plan pages were added up; "
                            "check that no plan is a repeat of another.")
    return res


def _apply_counts(page: PageResult, counts: dict, warnings: list, page_no: int):
    """Replace the model's guessed quantities with the position-based counts
    where a mark has one size on this page."""
    sizes = {}
    for e in page.elements:
        sizes.setdefault(_norm(e.label), []).append(e)
    for key, elems in sizes.items():
        n = counts.get(key, 0)
        if len(elems) > 1:
            continue            # floor-wise sizes: counts can't be split by position
        e = elems[0]
        if n and n != e.quantity:
            e.note = (e.note + " " if e.note else "") + f"(overview count was {e.quantity})"
            e.quantity = n
        elif not n and e.quantity:
            e.note = (e.note + " " if e.note else "") + "no plan mark found by position count - overview count kept"
            e.confidence = min(e.confidence, 0.5)
    unknown = [k for k in counts if k not in sizes]
    if unknown:
        warnings.append(f"Page {page_no}: marks found on the plan without a size: "
                        + ", ".join(f"{k}×{counts[k]}" for k in sorted(unknown))
                        + " - add them with their size if they need formwork.")


def _merge(pages: list) -> list:
    """One entry per (label, size, floor). Counts add up over plan pages;
    a schedule-only page contributes sizes but no count."""
    out = {}
    for p in pages:
        if p.page_kind in ("elevation_or_detail", "other"):
            continue
        for e in p.elements:
            L, W = max(e.length_mm, e.width_mm), min(e.length_mm, e.width_mm)
            key = (e.label.strip().upper(), round(L), round(W), (e.floor or "").upper())
            m = out.setdefault(key, {
                "label": e.label.strip(), "kind": e.kind, "length_mm": round(L), "width_mm": round(W),
                "quantity": 0, "floor": e.floor or "", "confidence": e.confidence,
                "size_source": e.size_source, "notes": []})
            m["quantity"] += max(0, e.quantity)
            m["confidence"] = min(m["confidence"], e.confidence)
            if e.note:
                m["notes"].append(e.note)
    merged = list(out.values())
    for m in merged:
        if m["quantity"] == 0:
            m["notes"].append("count not found on a plan - quantity set to 1, please correct")
            m["quantity"] = 1
            m["confidence"] = min(m["confidence"], 0.5)
        if m["size_source"] == "estimated":
            m["notes"].append("size estimated, not written on the drawing")
    return merged
