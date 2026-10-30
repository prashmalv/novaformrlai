from src.models.element import StructuralElement, ElementBOQ, ElementType,PanelEntry
from src.dwg_parse.collect_text import _collect_texts
from src.dwg_parse.collect_polylines import _collect_polylines
from src.dwg_parse.collect_label_from_nova_output import collect_labels

import math
import re
try:
    import ezdxf
    EZDXF_OK = True
except ImportError:
    EZDXF_OK = False


_NOVA_WxH_RE = re.compile(r'^(\d+)[xX](\d+)$')  # e.g. "300X2470"

def _rcol_panels_from_elev(
    lx: float, ly: float,
    texts: list[tuple[float, float, str]],
    product_height_mm: float,
    search_radius: float = 3000.0,
) -> list[PanelEntry]:
    """
    For round columns (R-COL) the plan view is a circle with no flat panels.
    The engineer labels panel sizes as WxH MTEXT in the elevation view nearby.
    Collect those WxH labels and return them as PanelEntry objects.
    """
    from collections import Counter
    wh_found: list[tuple[int, int]] = []
    for tx, ty, t in texts:
        m = _NOVA_WxH_RE.match(t.strip())
        if not m:
            continue
        d = math.hypot(tx - lx, ty - ly)
        if d <= search_radius:
            wh_found.append((int(m.group(1)), int(m.group(2))))
    if not wh_found:
        return []
    wh_counts = Counter(wh_found)
    entries: list[PanelEntry] = []
    for (w, h), qty in sorted(wh_counts.items(), key=lambda x: -x[0][0]):
        entries.append(PanelEntry(
            size_label=f"{w}X{h}",
            width_mm=float(w),
            height_mm=float(h),
            quantity=qty,
            is_corner=False,
        ))
    return entries


def _nearest_numeric_text(
    cx: float, cy: float,
    texts: list[tuple[float, float, str]],
    max_dist: float = 600.0,
) -> str | None:
    """Return the closest MTEXT/TEXT that is a plain number or WxH near (cx,cy)."""
    best_v, best_d = None, max_dist
    for tx, ty, t in texts:
        t_clean = t.strip()
        if not (re.match(r'^\d+$', t_clean) or _NOVA_WxH_RE.match(t_clean)):
            continue
        d = math.hypot(tx - cx, ty - cy)
        if d < best_d:
            best_d, best_v = d, t_clean
    return best_v

# --------------- chain start------------------------------------
import math
from collections import Counter

TEXT_CHAIN_TOL = 670.0  # max hop distance (drawing units) for the text chain

import math


def _text_chain_around_column(
    txt: tuple,
    texts: list[tuple[float, float, str]],
    tol: float = TEXT_CHAIN_TOL,
) -> list[tuple[float, float, str]]:
    """
    Build a text chain using nearest-neighbour traversal.

    1. Find the nearest text to the starting position, skipping
       texts at exactly the same coordinates.
    2. Find unused texts within tolerance of ANY point in the chain.
    3. Select the globally nearest eligible candidate.
       Break distance ties using the original list index.
    4. Repeat until no eligible candidates remain.
    5. Append the original txt if it is not already present.

    Duplicate text entries remain distinct through their list indices.
    """
    if not texts:
        return [txt]

    lx, ly = txt[0], txt[1]

    # Step 1: Find the nearest starting text.
    min_dist = float("inf")
    first_idx = None

    for idx, text_item in enumerate(texts):
        if text_item[0] == lx and text_item[1] == ly:
            continue

        d = math.hypot(
            text_item[0] - lx,
            text_item[1] - ly,
        )

        if d < min_dist:
            min_dist = d
            first_idx = idx

    if first_idx is None:
        return [txt]

    chain_idx = [first_idx]
    used = {first_idx}

    # Step 2: Search from every point already in the chain.
    while True:
        candidates = []

        for idx, (tx, ty, _) in enumerate(texts):
            if idx in used:
                continue

            # Find the minimum distance to any point in the chain.
            min_chain_dist = float("inf")

            for chain_i in chain_idx:
                cx, cy, _ = texts[chain_i]

                d = math.hypot(tx - cx, ty - cy)

                if d < min_chain_dist:
                    min_chain_dist = d

            if min_chain_dist <= tol:
                candidates.append((min_chain_dist, idx))

        if not candidates:
            break

        # Nearest candidate first; original index breaks ties.
        candidates.sort()
        _, next_idx = candidates[0]

        chain_idx.append(next_idx)
        used.add(next_idx)

    # Step 3: Return the ordered chain.
    chain = [texts[idx] for idx in chain_idx]

    if txt not in chain:
        chain.append(txt)

    return chain

# -----------------chain end -------------------------------------


def _panels_around_column(
    polylines: list[dict],
    texts: list[tuple[float, float, str]],
    casting_height_mm: float,
    product_height_mm: float,
    best_text = tuple,
) -> list[PanelEntry]:
    """
    Find all 80mm-thick rectangles adjacent to `col`, read their panel widths
    from nearby MTEXT, and return a deduplicated list of PanelEntry objects.

    casting_height_mm : actual pour height (stored on element, shown in BOQ header)
    product_height_mm : physical panel height Nova supplies (e.g. 3200 for 2470 pour)
    """


    text_chain = _text_chain_around_column(best_text, texts, TEXT_CHAIN_TOL)
    #print("this chain :", text_chain)

    oc_qty = 0
    ic_qty = 0
    H_qty =0
    flat_widths: list[int] = []

    for _, _, txt in text_chain:

        txt = txt.strip().upper()

        # Check IC
        if re.fullmatch(r'IC', txt):
            ic_qty += 1

        # Check OC
        elif re.fullmatch(r'OC', txt):
            oc_qty += 1

        # Check H1, H4, H25 etc.
        elif re.fullmatch(r'H\d{1,3}', txt):
            H_qty += 1

        # Check dimensions like 600X1237 or 80X5250
        elif m := re.fullmatch(r'(\d{2,3})X\d{4}', txt):
            flat_widths.append(int(m.group(1)))

        # Check flat widths like 90, 200, 500, 600
        elif re.fullmatch(r'\d{2,3}', txt):
            flat_widths.append(int(txt))
        else:
            continue
    from collections import Counter
    width_counts = Counter(flat_widths)

    entries: list[PanelEntry] = []
    if oc_qty:
        entries.append(PanelEntry(
            size_label=f"OC80X{int(product_height_mm)}",
            width_mm=80.0,
            height_mm=product_height_mm,
            quantity=oc_qty,
            is_corner=True,
        ))
    if ic_qty:
        entries.append(PanelEntry(
            size_label=f"IC100X{int(product_height_mm)}",
            width_mm=100.0,
            height_mm=product_height_mm,
            quantity=ic_qty,
            is_corner=True,
            is_inner_corner=True,
        ))
    for w in sorted(width_counts.keys(), reverse=True):
        entries.append(PanelEntry(
            size_label=f"{w}X{int(product_height_mm)}",
            width_mm=float(w),
            height_mm=product_height_mm,
            quantity=width_counts[w],
            is_corner=False,
        ))
    return entries
# -------------------nearest mtext start--------------

def _dist_point_to_bbox_edge(x: float, y: float, p: tuple) -> float:
    """
    Return the Euclidean distance between two points.

    If both points have the same coordinates, return 0.
    """
    px, py = p[0], p[1]

    dx = px - x
    dy = py - y

    return math.hypot(dx, dy)

output_pattern = [
    r'^\d{2,3}[Xx]\d{4}$',
    r'^\d{2,3}$',
    r'^(?:IC|OC)$',
    r'^[A-Z]\d{1,3}$']

def _nearest_mtext_to_label(
    lbl: dict,
    texts: list[tuple],
) -> tuple | None:
    """
    Return the nearest text tuple to the label position.

    Skip a text if its coordinates are identical to the label's
    coordinates.
    """
    lx, ly = lbl['x'], lbl['y']

    min_dist = float('inf')
    nearest_text = None

    for txt in texts:
        # Skip the text if its coordinates match the label.
        if txt[0] == lx and txt[1] == ly:
            continue
        
        # match only output patterm
        if not any(re.fullmatch(p, txt[2]) for p in output_pattern):
            continue     
        d = _dist_point_to_bbox_edge(lx, ly, txt)

        if d < min_dist:
            min_dist = d
            nearest_text = txt

    return nearest_text
# --------------------nearest text end -------------------

def parse_nova_drawing(
    dxf_path: str,
    casting_height_mm: float = 2470.0,
    product_height_mm: float = 3200.0,
    doc=None,
) -> tuple[list[StructuralElement], list[ElementBOQ], str | None]:
    """
    Parse Nova's new labelled-panel DXF format.

    Supports:
    • Regular columns : GF-COL:-900X1500,  FF-COL:-600X900,  COL:-1200X800
    • Round columns   : R-COL:-Ø1200X2470  (WxH labels in nearby elevation view)
    • L-shaped columns: L-COL:-(400X3000)+(400X1500)  (8-vertex outline polyline)

    Args:
        dxf_path          : Path to the DXF file.
        casting_height_mm : Pour height shown in BOQ header (e.g. 2470mm).
        product_height_mm : Physical panel height Nova supplies (e.g. 3200mm).
        doc               : Pre-loaded ezdxf document (optional). When provided,
                            the file is not re-read — avoids Windows AV double-scan.

    Returns:
        elements : list[StructuralElement]  (element.height_mm = casting_height_mm)
        boqs     : list[ElementBOQ]         (panel size_labels use product_height_mm)
        error    : error string or None
    """
    if not EZDXF_OK:
        return [], [], "ezdxf not installed — run: pip install ezdxf"

    if doc is None:
        try:
            doc = ezdxf.readfile(dxf_path)
        except Exception as e:
            return [], [], f"Cannot open DXF file: {e}"

    try:
        msp = doc.modelspace()
    except Exception as e:
        return [], [], f"Cannot read modelspace: {e}"

    texts     = _collect_texts(msp)
    polylines = _collect_polylines(msp)
    
    if not texts:
        return [], [], "No text entities found — is this a Nova labelled drawing?"

    # ── Step 1: collect all column labels ────────────────────────────────────
    col_label: list[dict] = []
    seen_pos: set[tuple[int, int]] = set()  # deduplicate duplicate TEXT entities
    col_labels = collect_labels(texts,col_label, seen_pos)

    if not col_labels:
        return [], [], (
            "No column labels found.\n"
            "Expected formats: 'COL:-LxW', 'FF-COL 600x900', "
            "'R-COL:-Ø1200X2470', 'L-COL:-(400X3000)+(400X1500)'\n"
            f"Sample texts found: {[t for _, _, t in texts[:10]]}"
        )
    # ── Step 2: for each label, find column outline and read panels ───────────
    elements: list[StructuralElement] = []
    boqs:     list[ElementBOQ] = []

    for lbl in col_labels:
        lx, ly    = lbl['x'], lbl['y']
        dim1      = lbl['dim1']
        dim2      = lbl['dim2']
        floor_str = lbl['floor']
        etype_raw = lbl['etype']
        is_lcol   = lbl.get('is_lcol_paren', False)
        tol       = 0.20  # 20 % dimensional tolerance for outline matching
        raw_text1 = lbl.get('raw_text', '').upper().strip()
        if raw_text1.startswith("C"):
            e_type = ElementType.COLUMN
        else:
            e_type = ElementType.SHEAR_WALL

        # ── Nearest mtext outline to this label ──────────────────────────
        best_text = _nearest_mtext_to_label(lbl, texts)
        if best_text is None:
            continue   # no outline near this label; skip (or log it)
        
        
        # ── Build element ─────────────────────────────────────────────────
        if etype_raw == 'RCOL':
            elem_type = ElementType.COLUMN
            notes     = "Round column"
            length_mm = float(max(dim1, dim2))
            width_mm  = float(min(dim1, dim2))
            label_str = (
                f"{floor_str + '-' if floor_str else ''}R-COL "
                f"{int(length_mm)}x{int(width_mm)}"
            )
        elif is_lcol:
            elem_type = ElementType.COLUMN
            notes     = "L-shaped column"
            leg1_w = lbl['leg1_w']; leg1_h = lbl['leg1_h']
            leg2_w = lbl['leg2_w']; leg2_h = lbl['leg2_h']
            if dim1 and dim2:
                length_mm = float(max(dim1, dim2))
                width_mm  = float(min(dim1, dim2))
            else:
                length_mm = float(max(leg1_w, leg1_h, leg2_w, leg2_h))
                width_mm  = float(min(leg1_w, leg2_w))
            label_str = (
                f"{floor_str + '-' if floor_str else ''}L-COL "
                f"({leg1_w}x{leg1_h})+({leg2_w}x{leg2_h})"
            )
        elif etype_raw == 'LCOL':
            elem_type = ElementType.COLUMN
            notes     = "L-shaped column"
            length_mm = float(max(dim1, dim2))
            width_mm  = float(min(dim1, dim2))
            label_str = (
                f"{floor_str + '-' if floor_str else ''}L-COL "
                f"{int(length_mm)}x{int(width_mm)}"
            )
        else:
            elem_type = e_type
            notes     = ""
            length_mm = float(max(dim1, dim2))
            width_mm  = float(min(dim1, dim2))
            label_str = raw_text1
            # label_str = (
            #     f"{floor_str + '-' if floor_str else ''}COL "
            #     f"{int(length_mm)}x{int(width_mm)}"
            # )

        elem = StructuralElement(
            element_type=elem_type,
            label=label_str,
            length_mm=length_mm,
            width_mm=width_mm,
            height_mm=casting_height_mm,
            quantity=1,
            notes=notes,
            floor_label=floor_str,
        )

        # ── Read panels ───────────────────────────────────────────────────
        if etype_raw == 'RCOL':
            # Round column: no 80mm plan-view panels; use WxH elevation labels
            panel_entries = _rcol_panels_from_elev(lx, ly, texts, product_height_mm)
        elif is_lcol:
            # ── Panels (and the text chain) around that outline ───────────────
            panel_entries = _panels_around_column(
                polylines, texts,
                casting_height_mm=casting_height_mm,
                product_height_mm=product_height_mm,
                best_text = best_text,
            )
        elif best_text:  
            panel_entries = _panels_around_column(
                    polylines, texts,
                    casting_height_mm=casting_height_mm,
                    product_height_mm=product_height_mm,
                    best_text = best_text,) 
            
        else:
            panel_entries = []

        if not panel_entries:
            boq = ElementBOQ(
                element=elem, panels=[],
                warnings=["No panel rectangles detected around this element"],
            )
        else:
            boq = ElementBOQ(element=elem, panels=panel_entries)

        elements.append(elem)
        boqs.append(boq)

    if not elements:
        return [], [], (
            "Labels were found but no column outlines could be matched.\n"
            "Check that the drawing has closed polylines for column cross-sections."
        )

    return elements, boqs, None

