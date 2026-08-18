"""
Nova Formwork Drawing Parser
src/parsers/nova_drawing_parser.py

Reads Nova team's own annotated formwork detail drawings (col.dxf, new block.dxf,
FORMWORK DRAWING PLAN 1.dxf, etc.) and builds a BOQ by reading panel annotation
numbers DIRECTLY from the DXF — no panel optimization is run.

Nova Drawing Format
-------------------
TEXT labels (element headers):
    [FLOOR-][SHAPE-]TYPE:-DIM1xDIM2
    Examples:
        GF-COL:-900X1500         → Ground Floor Column, 900×1500mm
        FF-COL:-600X900          → First Floor Column, 600×900mm
        L-COL:-(400X3000)+(400X1500) → L-shaped Column
        R-COL:-%%C1200X2470      → Round column, ⌀1200mm
        COL:-1050X1250           → Column (no floor specified)
        SW:-3000X200             → Shear Wall
        WALL:-5000X230           → Wall

MTEXT panel annotations (numeric, placed next to each face):
    "600"        → 600mm-wide panel (height from app config)
    "300X2470"   → 300mm wide × 2470mm tall panel

Panel strips (LWPOLYLINE, 80mm deep):
    Drawn around each element face; MTEXT numbers label each strip.
    The 80mm dimension is the OC corner marker or panel depth — not the panel width.

Public API
----------
parse_nova_formwork_drawing(dxf_path, panel_height_mm=3200)
    → (elements: list[StructuralElement], boqs: list[ElementBOQ], error: str | None)
"""

import math
import re
from collections import defaultdict

# ── Label-parsing constants ───────────────────────────────────────────────────

# Matches optional floor prefix (GF, FF, SF, 1F, 2F …),
# optional shape code prefix (L, T, U, R), the element type, then dimensions.
_NOVA_LABEL_RE = re.compile(
    r'^'
    r'(?:([0-9]*[A-Z]+F?|B)-)?'       # group 1: floor prefix  (GF, FF, SF, 1F, B, …)
    r'(?:(L|T|U|R|C)-)?'              # group 2: shape prefix  (L-shaped, T, Round, C)
    r'(COL|WALL|SW|LIFT|PIER)'        # group 3: element type
    r':-'
    r'(.+)$',                          # group 4: raw dimension string
    re.IGNORECASE,
)

# Matches one "WxH" pair inside the dimension string
_DIM_PAIR_RE = re.compile(r'(\d+)\s*[xX×]\s*(\d+)')

# %%C = AutoCAD diameter symbol (used for round/circular columns)
_AUTOCAD_SPECIAL = re.compile(r'%%[A-Z]', re.IGNORECASE)

# MTEXT values: pure number "600" or "300X2470" (width × height)
_PANEL_VAL_RE = re.compile(r'^(\d{2,4})(?:[xX](\d{2,4}))?$')

# ── Known floor-code set (guards against shape codes being misread as floors) ─
_FLOOR_CODES = {
    'GF', 'FF', 'SF', 'TF', 'BF', 'B',
    '1F', '2F', '3F', '4F', '5F', '6F', '7F', '8F', '9F',
    'G', 'P', 'RF',
}

# Panel strip width drawn in Nova drawings (mm) — used as search gap when
# looking for MTEXT numbers outside the element bounding box.
_STRIP_DEPTH_MM = 80
_FACE_OUTER_MM  = 200   # max distance outside element edge to search for labels
_FACE_INNER_MM  = 20    # tolerance inward — panels are OUTSIDE the element


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_nova_label(raw: str):
    """
    Parse a Nova formwork TEXT label into its components.

    Returns a dict with keys:
        floor:      str | None   — floor code (GF, FF, …)
        shape:      str | None   — shape code (L, T, R, …)
        elem_type:  str          — 'COL', 'WALL', 'SW', 'LIFT'
        dims:       list[(int,int)] — dimension pairs [(L1,W1), (L2,W2), …]
        label_clean: str         — human-friendly label (e.g. "GF-COL-900×1500")
        is_round:   bool         — True if %%C (circular) prefix found
    or None if the text doesn't match the Nova label pattern.
    """
    raw = raw.strip()
    m = _NOVA_LABEL_RE.match(raw)
    if not m:
        return None

    floor_raw, shape_raw, elem_type, dims_raw = m.groups()
    floor_raw  = (floor_raw  or '').upper().strip('-')
    shape_raw  = (shape_raw  or '').upper().strip('-')
    elem_type  = elem_type.upper()

    # Resolve ambiguity: if floor_raw looks like a shape code (L/T/R/U)
    # and shape_raw is empty, move it to shape.
    if floor_raw in ('L', 'T', 'R', 'U', 'C') and not shape_raw:
        shape_raw  = floor_raw
        floor_raw  = ''
    elif floor_raw and floor_raw not in _FLOOR_CODES:
        # Unknown prefix — treat as part of the label but don't use as floor
        floor_raw = ''

    is_round   = bool(re.search(r'%%[Cc]', dims_raw))
    dims_clean = _AUTOCAD_SPECIAL.sub('', dims_raw)
    dims       = [(int(a), int(b)) for a, b in _DIM_PAIR_RE.findall(dims_clean)]

    if not dims:
        return None

    # Build clean label
    parts = [p for p in [floor_raw, shape_raw, elem_type] if p]
    dim_str = '+'.join(f'{a}×{b}' for a, b in dims)
    label_clean = '-'.join(parts) + '-' + dim_str

    return {
        'floor':       floor_raw  or None,
        'shape':       shape_raw  or None,
        'elem_type':   elem_type,
        'dims':        dims,
        'label_clean': label_clean,
        'is_round':    is_round,
        'raw':         raw,
    }


def _find_polygon_for_label(lx: float, ly: float, length_mm: float, width_mm: float,
                             all_polys: list, tol_pct: float = 0.10) -> dict | None:
    """
    Find the closest CLOSED LWPOLYLINE whose bounding box matches
    (length_mm × width_mm) within tol_pct, within 15000mm of the label.
    Returns the polygon dict or None.
    """
    best, best_d = None, 15000.0
    for poly in all_polys:
        pw, ph = poly['w'], poly['h']
        # Check both orientations (L×W or W×L)
        for el, ew in [(length_mm, width_mm), (width_mm, length_mm)]:
            if el == 0 or ew == 0:
                continue
            if (abs(pw - el) / el <= tol_pct and
                    abs(ph - ew) / ew <= tol_pct):
                d = math.hypot(poly['cx'] - lx, poly['cy'] - ly)
                if d < best_d:
                    best_d = d
                    best   = poly
                break
    return best


def _collect_face_panels(poly: dict, all_mtext: list) -> dict:  # noqa: C901
    """
    For a rectangular element polygon, identify which MTEXT panel-width numbers
    belong to each of the 4 faces (A, A', B, B').

    MTEXT numbers sit INSIDE the 80mm panel-strip rectangles drawn just outside
    the element outline.  We detect them by their position relative to the bbox:

        Face A  (left  / -X side): x slightly outside x_min, y within [y_min,y_max]
        Face A' (right / +X side): x slightly outside x_max, y within [y_min,y_max]
        Face B  (bot   / -Y side): y slightly outside y_min, x within [x_min,x_max]
        Face B' (top   / +Y side): y slightly outside y_max, x within [x_min,x_max]

    Returns:
        {
          'A':  [(panel_width_mm, panel_height_mm_or_None), …],
          "A'": […], 'B': […], "B'": […],
        }
    """
    x1 = poly['cx'] - poly['w'] / 2
    x2 = poly['cx'] + poly['w'] / 2
    y1 = poly['cy'] - poly['h'] / 2
    y2 = poly['cy'] + poly['h'] / 2

    # Panel MTEXT sits inside the 80mm-deep strip drawn just outside each face.
    # Outer search limit: strip depth + generous tolerance.
    # Inner tolerance: very small — panels are drawn OUTSIDE the element boundary,
    # not inside it.  A large inner value steals panels from adjacent elements.
    outer = _FACE_OUTER_MM   # 200mm: covers 80mm strip + label offset
    inner = _FACE_INNER_MM   # 20mm: only tiny tolerance inward

    faces: dict = {'A': [], "A'": [], 'B': [], "B'": []}

    for pw, ph, mx, my in all_mtext:
        in_y = y1 - inner <= my <= y2 + inner
        in_x = x1 - inner <= mx <= x2 + inner
        # Face A (LEFT)
        if x1 - outer < mx < x1 + inner and in_y:
            faces['A'].append((my, pw, ph))
        # Face A' (RIGHT)
        elif x2 - inner < mx < x2 + outer and in_y:
            faces["A'"].append((my, pw, ph))
        # Face B (BOTTOM)
        elif y1 - outer < my < y1 + inner and in_x:
            faces['B'].append((mx, pw, ph))
        # Face B' (TOP)
        elif y2 - inner < my < y2 + outer and in_x:
            faces["B'"].append((mx, pw, ph))

    # Sort along face direction; return just (pw, ph) tuples ordered by position
    result = {}
    for k, items in faces.items():
        result[k] = [(pw, ph) for _, pw, ph in sorted(items)]
    return result


def _build_boq(element, face_data: dict, panel_height_mm: float, poly: dict = None):
    """
    Build ElementBOQ from face_data read directly out of the Nova drawing.

    face_data: {face_key: [(panel_width_mm, panel_height_mm_or_None), …]}
    Panel heights from the drawing override panel_height_mm where specified.
    """
    from src.models.element import ElementBOQ, PanelEntry, ElementType

    boq = ElementBOQ(element=element)

    # Collect all panels across all faces → aggregate by (width, height) for quantity
    from collections import Counter as _Ctr
    panel_counter: dict = _Ctr()
    face_panel_lists: dict = {}   # face_key → [width_mm, …] for diagram

    for face_key, panels in face_data.items():
        widths = []
        for pw, ph in panels:
            effective_h = ph if ph else panel_height_mm
            panel_counter[(int(pw), int(effective_h))] += 1
            widths.append(int(pw))
        face_panel_lists[face_key] = widths

    # 4 OC corners (always present for a rectangular column / shear wall)
    oc_qty = 4
    oc_h   = int(panel_height_mm)
    boq.panels.append(PanelEntry(
        size_label=f"OC80X{oc_h}",
        width_mm=80,
        height_mm=oc_h,
        quantity=oc_qty,
        is_corner=True,
    ))

    # Flat panels — sorted by width descending
    for (pw, ph), qty in sorted(panel_counter.items(), key=lambda x: -x[0][0]):
        boq.panels.append(PanelEntry(
            size_label=f"{pw}X{ph}",
            width_mm=pw,
            height_mm=ph,
            quantity=qty,
        ))

    # face_panels structure for diagram rendering (same as optimize_column output).
    # Face A/A' are the LEFT/RIGHT (vertical) faces — they cover the polygon Y span.
    # Face B/B' are the BOTTOM/TOP (horizontal) faces — they cover the polygon X span.
    # Use the polygon's actual extents to get the right dimension label per face.
    if poly:
        face_a_dim = poly['h']   # vertical faces cover Y extent
        face_b_dim = poly['w']   # horizontal faces cover X extent
    else:
        # Fallback when polygon not found: use element dims
        face_a_dim = element.length_mm
        face_b_dim = element.width_mm

    def _face_entry(key, dim_mm):
        widths = face_panel_lists.get(key, [])
        return {
            'face':   key,
            'label':  f"{key} — {int(dim_mm)}mm",
            'dim_mm': dim_mm,
            'panels': sorted(widths, reverse=True),
            'spacer': 0.0,
        }

    boq.face_panels = [
        _face_entry('A',  face_a_dim),
        _face_entry('B',  face_b_dim),
        _face_entry("A'", face_a_dim),
        _face_entry("B'", face_b_dim),
    ]

    # Warn if face panel sums deviate more than 10% from face dimension
    for face_key, widths in face_panel_lists.items():
        if not widths:
            continue
        s = sum(widths)
        expected = face_a_dim if face_key in ('A', "A'") else face_b_dim
        if abs(s - expected) > max(50.0, expected * 0.10):
            boq.warnings.append(
                f"Face {face_key}: panels sum to {s}mm "
                f"(face dimension {int(expected)}mm) — verify against drawing."
            )

    return boq


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def parse_nova_formwork_drawing(dxf_path: str, panel_height_mm: float = 3200):
    """
    Parse a Nova formwork detail drawing (col.dxf, new block.dxf, etc.).

    Returns
    -------
    (elements, boqs, error)
        elements : list[StructuralElement]
        boqs     : list[ElementBOQ]   — parallel to elements
        error    : str | None          — human-readable error, or None on success
    """
    try:
        import ezdxf
    except ImportError:
        return [], [], "ezdxf not installed — run: pip install ezdxf"

    try:
        doc = ezdxf.readfile(dxf_path)
    except Exception as exc:
        return [], [], f"Cannot open DXF: {exc}"

    try:
        msp = doc.modelspace()
    except Exception as exc:
        return [], [], f"Cannot read modelspace: {exc}"

    from src.models.element import StructuralElement, ElementType, ElementBOQ

    # ── 1. Collect all TEXT labels ────────────────────────────────────────────
    text_labels: list = []   # [(parsed_dict, x, y)]
    for ent in msp:
        if ent.dxftype() not in ('TEXT', 'MTEXT'):
            continue
        try:
            if ent.dxftype() == 'TEXT':
                raw = ent.dxf.text
            else:
                try:
                    raw = ent.plain_text()
                except Exception:
                    raw = ent.text
            raw = (raw or '').strip()
            if not raw:
                continue
            parsed = _parse_nova_label(raw)
            if parsed:
                pos = ent.dxf.insert
                text_labels.append((parsed, pos.x, pos.y))
        except Exception:
            continue

    if not text_labels:
        return [], [], (
            "No Nova formwork labels found in this drawing.\n\n"
            "Expected labels like  GF-COL:-900X1500  or  FF-COL:-600X900.\n"
            "This file may be a client structural drawing — use 'Import Client Drawing' instead."
        )

    # ── 2. Collect all significant closed LWPOLYLINES ────────────────────────
    all_polys: list = []
    for ent in msp:
        if ent.dxftype() != 'LWPOLYLINE':
            continue
        try:
            if not ent.is_closed:
                continue
            pts = [(p[0], p[1]) for p in ent.get_points()]
            if len(pts) < 4:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            w  = max(xs) - min(xs)
            h  = max(ys) - min(ys)
            if w < 100 or h < 100:
                continue
            all_polys.append({
                'pts': pts,
                'cx':  (max(xs) + min(xs)) / 2,
                'cy':  (max(ys) + min(ys)) / 2,
                'w':   w, 'h': h,
                'npts': len(pts),
            })
        except Exception:
            continue

    # ── 3. Collect all numeric MTEXT values ──────────────────────────────────
    #  (panel_width_mm, panel_height_mm_or_None, x, y)
    all_mtext: list = []
    for ent in msp:
        if ent.dxftype() != 'MTEXT':
            continue
        try:
            try:
                txt = ent.plain_text().strip()
            except Exception:
                txt = (ent.text or '').strip()
            m = _PANEL_VAL_RE.match(txt)
            if not m:
                continue
            pw = int(m.group(1))
            ph = int(m.group(2)) if m.group(2) else None
            # Sanity: valid panel widths are 40–3000mm; heights 1000–6000mm
            if not (40 <= pw <= 3000):
                continue
            if ph is not None and not (1000 <= ph <= 6000):
                ph = None
            pos = ent.dxf.insert
            all_mtext.append((pw, ph, pos.x, pos.y))
        except Exception:
            continue

    # ── 4. For each label → find polygon → collect face panels → build BOQ ───
    elements: list = []
    boqs:     list = []
    seen_labels: set = set()

    for parsed, lx, ly in text_labels:
        dims      = parsed['dims']
        elem_type = parsed['elem_type']
        shape     = parsed['shape']
        floor_pfx = parsed['floor']

        # Use primary dimension pair for polygon matching
        d1, d2 = dims[0]
        length_mm = float(max(d1, d2))
        width_mm  = float(min(d1, d2))

        label = parsed['label_clean']
        # De-duplicate: same label type already processed
        if label in seen_labels:
            continue
        seen_labels.add(label)

        # Find matching polygon
        poly = _find_polygon_for_label(lx, ly, length_mm, width_mm, all_polys)

        # Classify element type
        if elem_type in ('SW', 'LIFT', 'WALL'):
            etype = ElementType.SHEAR_WALL if elem_type in ('SW', 'LIFT') else ElementType.WALL
        else:
            etype = ElementType.COLUMN

        notes_parts = []
        if floor_pfx:
            notes_parts.append(f"Floor: {floor_pfx}")
        if shape:
            shape_names = {'L': 'L-shaped', 'T': 'T-shaped', 'R': 'Round',
                           'U': 'U-shaped', 'C': 'C-shaped'}
            notes_parts.append(shape_names.get(shape, f'{shape}-shaped'))
        if parsed['is_round']:
            notes_parts.append('Circular section')
        if len(dims) > 1:
            extra = ' + '.join(f"{a}×{b}" for a, b in dims[1:])
            notes_parts.append(f"Additional arm(s): {extra}")
        if poly is None:
            notes_parts.append("⚠ No matching polygon found in drawing")

        element = StructuralElement(
            element_type=etype,
            label=label,
            length_mm=length_mm,
            width_mm=width_mm,
            height_mm=panel_height_mm,
            quantity=1,
            notes=', '.join(notes_parts),
            floor_label=floor_pfx or '',
            polygon_pts=list(poly['pts']) if poly else [],
        )

        if poly:
            face_data = _collect_face_panels(
                poly,
                [(pw, ph, mx, my) for pw, ph, mx, my in all_mtext],
            )
            boq = _build_boq(element, face_data, panel_height_mm, poly=poly)
        else:
            # No polygon found — build a minimal BOQ with a warning
            from src.engine.panel_optimizer import compute_boq
            boq = compute_boq(element, panel_height_mm)
            boq.warnings.insert(
                0,
                f"Polygon not found in drawing for {label} "
                f"({int(length_mm)}×{int(width_mm)}mm). "
                "BOQ estimated by optimizer — verify against drawing."
            )

        elements.append(element)
        boqs.append(boq)

    if not elements:
        return [], [], (
            "Labels were found but no BOQ could be built.\n"
            "Check that element labels follow the format  TYPE:-LxW  "
            "(e.g. COL:-900X1500)."
        )

    # Sort by label
    pairs = sorted(zip(elements, boqs), key=lambda x: x[0].label)
    elements, boqs = zip(*pairs) if pairs else ([], [])

    return list(elements), list(boqs), None
