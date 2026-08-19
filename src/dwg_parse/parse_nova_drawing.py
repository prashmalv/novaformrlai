from src.models.element import StructuralElement, ElementBOQ, ElementType, PanelEntry
from src.dwg_parse.collect_text import _collect_texts
from src.dwg_parse.collect_polylines import _collect_polylines
import re
import math


try:
    import ezdxf
    EZDXF_OK = True
except ImportError:
    EZDXF_OK = False

_NOVA_WxH_RE = re.compile(r'^(\d+)[xX](\d+)$')  # e.g. "300X2470"

_NOVA_LABEL_RE = re.compile(
    # Floor prefix: named (GF/FF/SF/TF/RF/BF/LG/PH) OR basement B1-B9
    # OR numbered floors 1F-99F / 1A-9A — deliberately excludes bare R/L
    # to avoid consuming R-COL / L-COL type prefixes
    r'(?:(GF|FF|SF|TF|RF|BF|LG|PH|B[0-9]|[1-9][0-9]*[FA])[-\s]*)?'
    r'(R[-\s]*COL|L[-\s]*COL|COL)'             # element type
    r'[:\-\s]+'                                 # separator (colon, dash, space)
    r'[Ø\s]*'                                   # optional Ø (R-COL diameter symbol)
    r'(\d+)\s*[xX]\s*(\d+)',                    # WxD dimensions
    re.IGNORECASE,
)



_L_COL_RE = re.compile(
    r'(?:(GF|FF|SF|TF|RF|BF|LG|PH|B[0-9]|[1-9][0-9]*[FA])[-\s]*)?'
    r'L[-\s]*COL[:\-\s]*'                       # L-COL + separator
    r'\((\d+)\s*[xX]\s*(\d+)\)'               # (W1xH1)  first leg
    r'\s*\+\s*'                                # +
    r'\((\d+)\s*[xX]\s*(\d+)\)',              # (W2xH2)  second leg
    re.IGNORECASE,
)


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



def _panels_around_column(
    col: dict,
    polylines: list[dict],
    texts: list[tuple[float, float, str]],
    casting_height_mm: float,
    product_height_mm: float,
) -> list[PanelEntry]:
    """
    Find all 80mm-thick rectangles adjacent to `col`, read their panel widths
    from nearby MTEXT, and return a deduplicated list of PanelEntry objects.

    casting_height_mm : actual pour height (stored on element, shown in BOQ header)
    product_height_mm : physical panel height Nova supplies (e.g. 3200 for 2470 pour)
    """
    PT        = 95   # panel thickness tolerance (80mm nominal + 15mm wiggle)
    BUF       = PT + 25  # look this far outside column outline
    MIN_THICK = 30   # annotation/dimension lines thinner than this → skip
    MAX_WIDTH = 650  # single flat panel max width (600mm + tolerance) → skip longer

    oc_qty = 0
    ic_qty = 0
    flat_widths: list[int] = []

    for p in polylines:
        if p is col:
            continue
        pw, ph = p['w'], p['h']

        # Must be panel-thin (one dimension ≤ PT = 95mm)
        if min(pw, ph) > PT:
            continue

        # Skip annotation/dimension lines (too thin — typically 1–20mm)
        if min(pw, ph) < MIN_THICK:
            continue

        # Skip outer bounding-box frame lines (too long to be a single panel)
        if max(pw, ph) > MAX_WIDTH:
            continue

        # Must be adjacent to column outline (within BUF of its bounding box)
        pcx, pcy = p['cx'], p['cy']
        if not (col['x0'] - BUF <= pcx <= col['x1'] + BUF and
                col['y0'] - BUF <= pcy <= col['y1'] + BUF):
            continue

        # OC corner: both dimensions ≤ PT (≈ 80×80 square)
        if pw <= PT and ph <= PT:
            oc_qty += 1
            continue

        # Flat panel — read width from nearest numeric MTEXT
        lbl = _nearest_numeric_text(pcx, pcy, texts)
        if lbl:
            m = _NOVA_WxH_RE.match(lbl)
            if m:
                flat_widths.append(int(m.group(1)))  # width part of WxH label
            else:
                flat_widths.append(int(lbl))
        else:
            flat_widths.append(round(max(pw, ph)))   # fallback: measured dimension

    # IC (Inner Corner) detection — look for "IC" MTEXT inside/near the column outline
    for tx, ty, t in texts:
        if t.strip().upper() != 'IC':
            continue
        if (col['x0'] - 200 <= tx <= col['x1'] + 200 and
                col['y0'] - 200 <= ty <= col['y1'] + 200):
            ic_qty += 1
            break  # one IC per L-shaped column

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
    col_labels: list[dict] = []
    seen_pos: set[tuple[int, int]] = set()  # deduplicate duplicate TEXT entities

    for tx, ty, txt in texts:
        pos_key = (round(tx), round(ty))
        if pos_key in seen_pos:
            continue

        # Skip elevation-view labels (e.g. "COL ELEVATION: 600X300")
        # These appear in the side-view section, not the plan view
        if re.search(r'\bELEV(ATION)?\b', txt, re.IGNORECASE):
            continue

        # L-COL parentheses format first: L-COL:-(400X3000)+(400X1500)
        m2 = _L_COL_RE.search(txt)
        if m2:
            floor_str = (m2.group(1) or "").upper()
            leg1_w, leg1_h = int(m2.group(2)), int(m2.group(3))
            leg2_w, leg2_h = int(m2.group(4)), int(m2.group(5))
            seen_pos.add(pos_key)
            col_labels.append({
                'x': tx, 'y': ty, 'raw_text': txt,
                'floor': floor_str, 'etype': 'LCOL',
                'is_lcol_paren': True,
                'leg1_w': leg1_w, 'leg1_h': leg1_h,
                'leg2_w': leg2_w, 'leg2_h': leg2_h,
                'dim1': max(leg1_w, leg1_h, leg2_w, leg2_h),
                'dim2': min(leg1_w, leg2_w),
            })
            continue

        # Regular / R-COL / plain L-COL format
        m = _NOVA_LABEL_RE.search(txt)
        if not m:
            continue
        floor_str = (m.group(1) or "").upper()
        etype_raw = m.group(2).upper().replace(" ", "").replace("-", "")
        dim1 = int(m.group(3))
        dim2 = int(m.group(4))
        seen_pos.add(pos_key)
        col_labels.append({
            'x': tx, 'y': ty, 'raw_text': txt,
            'floor': floor_str, 'etype': etype_raw,
            'is_lcol_paren': False,
            'dim1': dim1, 'dim2': dim2,
        })

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

        # ── Find best matching column outline polyline ────────────────────
        best_col: dict | None = None
        best_score = float('inf')

        for p in polylines:
            if not p['closed']:
                continue
            if p['w'] < 150 or p['h'] < 150:
                continue
            if p['cy'] < ly - 500:  # outline must be above (or near) the label
                continue

            pw, ph = p['w'], p['h']
            verts  = p.get('verts', 4)
            dist   = math.hypot(p['cx'] - lx, p['cy'] - ly)

            if is_lcol:
                # L-shaped columns: strongly prefer 6+ vertex polylines
                score = dist if verts >= 6 else dist + 10000
            else:
                dim_ok = (
                    (abs(pw - dim1) / max(dim1, 1) < tol and
                     abs(ph - dim2) / max(dim2, 1) < tol) or
                    (abs(pw - dim2) / max(dim2, 1) < tol and
                     abs(ph - dim1) / max(dim1, 1) < tol)
                )
                score = dist if dim_ok else dist + 50000

            if score < best_score:
                best_score = score
                best_col = p

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
            if best_col:
                length_mm = float(max(best_col['w'], best_col['h']))
                width_mm  = float(min(best_col['w'], best_col['h']))
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
            elem_type = ElementType.COLUMN
            notes     = ""
            length_mm = float(max(dim1, dim2))
            width_mm  = float(min(dim1, dim2))
            label_str = (
                f"{floor_str + '-' if floor_str else ''}COL "
                f"{int(length_mm)}x{int(width_mm)}"
            )

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
        elif best_col is not None:
            panel_entries = _panels_around_column(
                best_col, polylines, texts,
                casting_height_mm=casting_height_mm,
                product_height_mm=product_height_mm,
            )
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

