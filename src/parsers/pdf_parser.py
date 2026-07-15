"""
PDF parser for Nova formwork drawings.

Extracts panel BOQ data from PDFs that already contain labelled panel
schedules (e.g. "OC80X2400", "600X1235") embedded as text in CAD-exported PDFs.

Supports the layout: BOX CULVERT PLAN / UPPER PIPE PLAN / BOTTOM PIPE PLAN
on a single sheet with right-side panel legends.
"""

import re
from collections import defaultdict

import fitz  # PyMuPDF — already in requirements

from src.models.element import (
    ElementType, PanelEntry, ElementBOQ, StructuralElement,
)

# ── Panel label pattern ───────────────────────────────────────────────────────
_PANEL_RE = re.compile(r'\b((?:OC\d+|IC\d+|\d{2,4})X\d{3,5})\b', re.I)

# ── Section header patterns ───────────────────────────────────────────────────
_SECTION_PATS: list[tuple[str, re.Pattern]] = [
    ("BOX CULVERT",  re.compile(r'BOX\s+CU[VL]+ERT\s+PLAN',  re.I)),
    ("UPPER PIPE",   re.compile(r'UPPER\s+PIPE\s+PLAN',       re.I)),
    ("BOTTOM PIPE",  re.compile(r'BOTTOM\s+PIPE\s+PLAN',      re.I)),
    ("BOTTOM PANEL", re.compile(r'BOTTOM\s+PANEL\s+PLAN',     re.I)),
    ("ACCESSORIES",  re.compile(r'ACCESSORIES\s+PLAN',        re.I)),
]

_SECTION_TYPE = {
    "BOX CULVERT":  ElementType.BOX_CULVERT,
    "UPPER PIPE":   ElementType.BOX_CULVERT,
    "BOTTOM PIPE":  ElementType.SLAB,
    "BOTTOM PANEL": ElementType.SLAB,
    "ACCESSORIES":  ElementType.SLAB,   # recognized but will have no WxH labels → skipped
}


def _extract_spans(page) -> list[dict]:
    out = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for sp in line["spans"]:
                txt = sp["text"].strip()
                if txt:
                    x0, y0, x1, y1 = sp["bbox"]
                    out.append({"text": txt, "x": (x0 + x1) / 2, "y": (y0 + y1) / 2})
    return out


def _parse_label(label: str) -> tuple[float, float, bool, bool]:
    """Return (width_mm, height_mm, is_corner, is_inner_corner)."""
    upper = label.upper()
    is_inner  = upper.startswith("IC")
    is_corner = upper.startswith("OC") or is_inner
    parts = upper.split("X")
    try:
        h_mm = float(parts[-1])
    except (ValueError, IndexError):
        h_mm = 3200.0
    raw_w = parts[0]
    if raw_w.startswith("OC"):
        raw_w = raw_w[2:]
    elif raw_w.startswith("IC"):
        raw_w = raw_w[2:]
    try:
        w_mm = float(raw_w)
    except ValueError:
        w_mm = 80.0 if is_corner else 600.0
    return w_mm, h_mm, is_corner, is_inner


def _large_dims_in_region(spans, x0, y0, x1, y1) -> list[float]:
    result = []
    for sp in spans:
        if x0 <= sp["x"] <= x1 and y0 <= sp["y"] <= y1:
            try:
                v = float(sp["text"])
                if 1000 <= v <= 15000:
                    result.append(v)
            except ValueError:
                pass
    return sorted(set(result), reverse=True)


def _build_boq(section_name, label_counts, dims):
    length_mm = float(dims[0]) if len(dims) >= 1 else 2000.0
    width_mm  = float(dims[1]) if len(dims) >= 2 else length_mm
    heights   = [_parse_label(lbl)[1] for lbl in label_counts]
    elem_h    = max(heights) if heights else 3200.0

    elem = StructuralElement(
        element_type=_SECTION_TYPE.get(section_name, ElementType.BOX_CULVERT),
        label=section_name,
        length_mm=length_mm,
        width_mm=width_mm,
        height_mm=elem_h,
        quantity=1,
        notes="Imported from Nova PDF",
    )

    def sort_key(item):
        lbl, _qty = item
        w, _h, is_corner, _ = _parse_label(lbl)
        return (0 if is_corner else 1, -w)

    panels = []
    for lbl, qty in sorted(label_counts.items(), key=sort_key):
        w_mm, h_mm, is_corner, is_inner = _parse_label(lbl)
        panels.append(PanelEntry(
            size_label      = lbl.upper(),
            width_mm        = w_mm,
            height_mm       = h_mm,
            quantity        = qty,
            is_corner       = is_corner,
            is_inner_corner = is_inner,
        ))

    return elem, ElementBOQ(element=elem, panels=panels)


def parse_nova_pdf(
    pdf_path: str,
    product_height_mm: float = 3200.0,
) -> tuple[list, list, str]:
    """
    Parse a Nova box-culvert formwork PDF.
    Returns (elements, boqs, error_str).  error_str is empty on success.
    """
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:
        return [], [], f"Cannot open PDF: {exc}"

    if doc.page_count == 0:
        return [], [], "PDF has no pages."

    page   = doc[0]
    page_w = page.rect.width
    page_h = page.rect.height
    spans  = _extract_spans(page)

    # ── 1. Find section headers ───────────────────────────────────────────────
    sections: list[dict] = []
    for sp in spans:
        for sec_name, pat in _SECTION_PATS:
            if pat.search(sp["text"]):
                if not any(s["name"] == sec_name for s in sections):
                    sections.append({"name": sec_name, "x": sp["x"], "y": sp["y"]})
                break

    if not sections:
        return [], [], (
            "No section headers found in this PDF.\n\n"
            "Expected text such as 'BOX CULVERT PLAN', 'UPPER PIPE PLAN', "
            "or 'BOTTOM PIPE PLAN' in the drawing."
        )

    # ── 2. Compute Y split from header positions ──────────────────────────────
    # Section labels sit at the BOTTOM of their drawings.
    # The top row of headers marks the end of the top drawings.
    # Use: just below the MINIMUM header Y = top of the gap between rows.
    min_header_y = min(s["y"] for s in sections)
    y_split = min_header_y + 20  # anything above this line = top drawings

    xs = sorted(s["x"] for s in sections)
    x_split = (xs[0] + xs[-1]) / 2 if len(xs) >= 2 else page_w / 2

    # ── 3. Assign panel labels to sections ───────────────────────────────────
    # Rules based on Nova standard layout:
    #  • y < y_split (above top-row headers)       → BOX CULVERT
    #  • y ≥ y_split, panel height < 1300 mm       → BOTTOM PIPE (slab panels)
    #  • y ≥ y_split, panel height ≥ 1300 mm       → UPPER PIPE (wall panels)
    sec_counts: dict[str, dict] = {s["name"]: defaultdict(int) for s in sections}

    # X boundary for splitting top-half between BOX CULVERT (left) and BOTTOM PANEL (right)
    # BOX CULVERT header is on the left, BOTTOM PANEL header is on the right.
    top_sections_by_x = sorted(
        [s for s in sections if s["y"] < y_split + 50],
        key=lambda s: s["x"]
    )
    # Mid-X between leftmost and rightmost top-row section headers
    if len(top_sections_by_x) >= 2:
        x_top_split = (top_sections_by_x[0]["x"] + top_sections_by_x[-1]["x"]) / 2
    else:
        x_top_split = page_w / 2

    for sp in spans:
        for m in _PANEL_RE.finditer(sp["text"]):
            lbl = m.group(1).upper()
            lx, ly = sp["x"], sp["y"]
            h_suffix = lbl.split("X")[-1]
            try:
                h_val = int(h_suffix)
            except ValueError:
                h_val = 3200

            if ly < y_split:
                # Top half: split left/right to separate BOX CULVERT from BOTTOM PANEL
                if lx < x_top_split and "BOX CULVERT" in sec_counts:
                    target = "BOX CULVERT"
                elif "BOTTOM PANEL" in sec_counts:
                    target = "BOTTOM PANEL"
                else:
                    target = "BOX CULVERT"
            else:
                # Bottom half: short panels → BOTTOM PIPE, tall → UPPER PIPE
                if h_val < 1300:
                    target = "BOTTOM PIPE"
                else:
                    target = "UPPER PIPE"

            if target in sec_counts:
                sec_counts[target][lbl] += 1

    # ── 4. Deduplicate legend pairs ───────────────────────────────────────────
    # Panel legends are printed twice (top + bottom of schedule table).
    # If ALL counts in a section are even and ≤ 4 → halve them.
    for sec_name, counts in sec_counts.items():
        if not counts:
            continue
        vals = list(counts.values())
        if all(v % 2 == 0 for v in vals) and max(vals) <= 4:
            for lbl in counts:
                counts[lbl] //= 2

    # ── 5. Extract element dimensions ────────────────────────────────────────
    sec_dims = {
        "BOX CULVERT":  _large_dims_in_region(spans, 0,       0,       x_split, y_split),
        "UPPER PIPE":   _large_dims_in_region(spans, 0,       y_split, x_split, page_h),
        "BOTTOM PIPE":  _large_dims_in_region(spans, 0,       y_split, x_split, page_h),
        "BOTTOM PANEL": _large_dims_in_region(spans, 0,       0,       x_split, y_split),
    }

    # ── 6. Build output ───────────────────────────────────────────────────────
    elements: list = []
    boqs:     list = []

    seen_order = [s["name"] for s in sections]
    for sec_name in seen_order:
        counts = dict(sec_counts.get(sec_name, {}))
        if not counts:
            continue
        dims = sec_dims.get(sec_name, [2000.0, 3000.0])
        elem, boq = _build_boq(sec_name, counts, dims)
        elements.append(elem)
        boqs.append(boq)

    if not elements:
        return [], [], (
            "Section headers found but no panel labels detected.\n\n"
            "Ensure the PDF contains panel labels like 'OC80X2400', '600X1235'."
        )

    return elements, boqs, ""
