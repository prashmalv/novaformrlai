import math
import re
from src.dwg_parse.clean_text import _clean_mtext_full
from src.dwg_parse.get_schedule_region import _get_schedule_regions
from src.dwg_parse.parse_nova_schedule_table import parse_nova_schedule_table
from src.models.element import StructuralElement, ElementType

try:
    import ezdxf
    EZDXF_OK = True
except ImportError:
    EZDXF_OK = False


# Label pattern for structural elements: SW6, C1, W2, etc.
# _SW_LABEL_RE = re.compile(r'^[A-Za-z]{1,3}\d+[A-Za-z]?$')
_SW_LABEL_RE = re.compile(r'^(?!H-?\d)[A-Za-z]{1,3}-?\d+[A-Za-z]?$')


def _classify_polygon_corners(pts: list) -> list:
    """
    Classify each polygon vertex as 'OC80' (convex) or 'IC100' (concave).

    Cross-product of consecutive edges determines convex vs concave.  The sign
    convention depends on whether the polygon is wound CCW (positive signed
    area) or CW (negative).  We detect the winding direction first and flip
    the cross-product interpretation for CW polygons so both orientations
    produce correct OC/IC labels.

    Verified against SW6 (OC×5, IC×1) and SW11 (OC×10, IC×6).
    """
    n = len(pts)
    # Shoelace signed area — positive = CCW, negative = CW
    signed_area = sum(
        pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
        for i in range(n)
    )
    is_ccw = signed_area > 0

    corners = []
    for i in range(n):
        prev = pts[(i - 1) % n]
        curr = pts[i]
        nxt  = pts[(i + 1) % n]
        e_in  = (curr[0] - prev[0], curr[1] - prev[1])
        e_out = (nxt[0]  - curr[0], nxt[1]  - curr[1])
        cross = e_in[0] * e_out[1] - e_in[1] * e_out[0]
        if is_ccw:
            corners.append('IC100' if cross < 0 else 'OC80')
        else:
            # CW polygon: cross-product signs are flipped relative to CCW
            corners.append('OC80' if cross < 0 else 'IC100')
    return corners



def _compute_polygon_face_nets(pts: list, corners: list) -> list:
    """
    Net flat-panel coverage length for each face of a polygon.

    Rule (verified against CLIENT-1 QUOTATION.xlsx for SW6, SW11, SW13):
      * IC100 at a corner deducts 100 mm from each of the two adjacent faces.
      * OC80 at a corner deducts nothing from the face lengths.
    """
    n = len(pts)
    nets = []
    for i in range(n):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        face_len = math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)
        deduct = (100 if corners[i] == 'IC100' else 0) + \
                 (100 if corners[(i + 1) % n] == 'IC100' else 0)
        nets.append(max(0, round(face_len) - deduct))
    return nets




def parse_nova_shear_walls(
    dxf_path: str,
    product_height_mm: float = 3705.0,
    doc=None,
) -> tuple:
    """
    Parse shear walls and other polygon-shaped elements from a Nova DXF drawing.

    For each MTEXT/TEXT label matching 'SW6', 'W3', 'C1', etc.:
      1. Find the closest closed LWPOLYLINE of structural size.
      2. Classify polygon corners (OC80 / IC100) using cross-product.
      3. Compute per-face net lengths (IC deducts 100 mm each side).
      4. Fill each face with standard panels (DP optimiser).

    Matches each plan label occurrence to a unique polygon using global
    minimum label-to-polygon-edge distance.

    Returns:
        elements : list[StructuralElement]
        boqs     : list[ElementBOQ]
        error    : str | None
    """
    if not EZDXF_OK:
        return [], [], "ezdxf not installed"

    if doc is None:
        try:
            doc = ezdxf.readfile(dxf_path)
        except Exception as e:
            return [], [], f"Cannot open DXF: {e}"

    try:
        msp = doc.modelspace()
    except Exception as e:
        return [], [], f"Cannot read modelspace: {e}"

    # ── Collect all MTEXT/TEXT labels ──────────────────────────────────────
    label_positions: list = []   # (x, y, cleaned_text)
    text_set: set={}
    for ent in msp:
        try:
            if ent.dxftype() == 'TEXT':
                raw = ent.dxf.text
                pos = ent.dxf.insert
            elif ent.dxftype() == 'MTEXT':
                try:
                    raw = ent.plain_text()
                except Exception:
                    raw = ent.text
                pos = ent.dxf.insert
            else:
                continue
            #print("Raw text :", raw)
            cleaned = _clean_mtext_full(raw)
            if cleaned:
                label_positions.append((pos.x, pos.y, cleaned))
        except Exception:
            continue
    
    # ── Count plan-area label occurrences (exclude schedule table area) ───────
    # Used as authoritative qty: how many times each label TEXT appears in
    # the plan/drawing area.  Schedule table labels (COLUMN SCHEDULE rows) are
    # excluded so they don't inflate the count.
    _sched_regions = _get_schedule_regions(label_positions)

    def _in_schedule_table(lx: float, ly: float) -> bool:
        return any(rx0 <= lx <= rx1 and ry0 <= ly <= ry1
                   for rx0, rx1, ry0, ry1 in _sched_regions)

    from collections import Counter as _LblCounter
    _plan_label_cnt: dict = {}
    _raw_cnt = _LblCounter()
    for _lx, _ly, _ltxt in label_positions:
        if _SW_LABEL_RE.match(_ltxt) and not _in_schedule_table(_lx, _ly):
            _raw_cnt[_ltxt.upper()] += 1
    _plan_label_cnt = dict(_raw_cnt)

    # ── Collect all significant closed polylines ───────────────────────────

    sig_polys: list = []  # dict with points, bounding-box metadata, and vertex count
    for ent in msp:
        if ent.dxftype() != 'LWPOLYLINE':
            continue
        try:
            pts = [(p[0], p[1]) for p in ent.get_points()]
            if len(pts) < 4:
                continue
            is_closed = ent.is_closed
            #print("text poly :", pts)
            if not is_closed:
                # Some DXF authoring tools close a loop by repeating the first
                # vertex as the last point instead of setting the LWPOLYLINE
                # "closed" flag. Treat that as closed too -- otherwise a real
                # wall/column drawn this way is silently invisible to every
                # downstream matching step (it never becomes a candidate at
                # all, regardless of label logic).
                _dx = pts[0][0] - pts[-1][0]
                _dy = pts[0][1] - pts[-1][1]
                if (_dx * _dx + _dy * _dy) ** 0.5 < 155.0:
                    is_closed = True
                    pts = pts[:-1]  # drop the duplicated closing vertex
            if not is_closed:
                continue
            if len(pts) < 4:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            w = max(xs) - min(xs)
            h = max(ys) - min(ys)
            if w < 150 or h < 150:
                continue  # skip annotation boxes / dimension lines
            sig_polys.append({
                'pts': pts,
                'w': w,
                'h': h,
                'npts': len(pts),
                'min_x': min(xs),
                'max_x': max(xs),
                'min_y': min(ys),
                'max_y': max(ys),
            })
        except Exception:
            continue
    #print("All sig polygon :", len(sig_polys))
    # Deduplicate identical polygons (same npts + center within 50mm + same size within 50mm).
    # DXF authoring artifacts can place the exact same LWPOLYLINE twice at identical coordinates.
    _seen_poly_keys: set = set()
    _deduped_polys: list = []
    for _p in sig_polys:
        _key = (
            _p['npts'],
            round(_p['min_x'] / 50),
            round(_p['max_x'] / 50),
            round(_p['min_y'] / 50),
            round(_p['max_y'] / 50),
        )
        if _key not in _seen_poly_keys:
            _seen_poly_keys.add(_key)
            _deduped_polys.append(_p)
    sig_polys = _deduped_polys

    if not sig_polys:
        return [], [], "No structural polylines found (all shapes smaller than 150mm)"
    #print("all unique polygon :", len(sig_polys))
    # Build schedule label set to filter out stray non-element text (grid refs,
    # dimension callouts, etc.) that happens to match the label pattern.
    _sched_labels: set = set()
    _sched_tbl_local: dict = {}
    if doc is not None:
        try:
            _sched_tbl_local = parse_nova_schedule_table(doc)
            _sched_labels = set(_sched_tbl_local.keys())
            #print("Label from schedule table :", _sched_labels)
        except Exception:
            pass
    # A label can legitimately appear in the plan view with NO row in the
    # schedule table at all (e.g. the schedule only defines "SW5 TO SW11" but
    # the plan also has a genuinely-drawn SW14). Excluding such labels here
    # would make their own text invisible to every matching phase below,
    # so their rightful polygon silently gets absorbed by the nearest label
    # that IS in the schedule instead (e.g. SW14's wall reported as SW9).
    # Any label found in the plan area (already schedule-region-filtered via
    # _plan_label_cnt) is therefore also treated as eligible, exactly like an
    # AS_PER_PLAN schedule entry: its own polygon geometry is authoritative.
    _sched_labels |= (set(_plan_label_cnt.keys()) - _sched_labels)

    def _point_to_segment_distance(px, py, x1, y1, x2, y2):
        dx = x2 - x1
        dy = y2 - y1
        seg_len_sq = dx * dx + dy * dy

        if seg_len_sq <= 1e-12:
            return math.hypot(px - x1, py - y1)

        t = ((px - x1) * dx + (py - y1) * dy) / seg_len_sq
        t = max(0.0, min(1.0, t))

        closest_x = x1 + t * dx
        closest_y = y1 + t * dy

        return math.hypot(px - closest_x, py - closest_y)

    def _label_to_polygon_edge_distance(lx, ly, poly):
        pts = poly['pts']
        n = len(pts)
        best_dist = float('inf')

        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]

            d = _point_to_segment_distance(
                lx, ly,
                x1, y1,
                x2, y2,
            )

            if d < best_dist:
                best_dist = d

        return best_dist

    # ── Multi-entity merged-shape detection ─────────────────────────────────
    # Some Nova drawings represent one complex/stepped wall (e.g. SW10, a
    # multi-segment Z/step-shaped run) as TWO OR MORE separate OPEN
    # LWPOLYLINE entities whose endpoints connect end-to-end into one closed
    # loop, rather than a single LWPOLYLINE. Such a wall is invisible to the
    # whole-polygon matching above (which only looks at genuine LWPOLYLINE
    # entities), so it never becomes a candidate at all.
    #
    # Detect such chains and, only where the WHOLE merged loop is a label's
    # best available match (strictly closer than any ordinary candidate
    # polygon already in sig_polys), add the complete merged loop as a
    # normal candidate polygon. It then goes through the exact same
    # corner-classification / face-net / panel-optimizer pipeline as any
    # other multi-vertex AS_PER_PLAN wall (e.g. SW5-SW7, SW9, SW11) -- no
    # edges are discarded, so the full shape (and its full panel
    # distribution) is preserved, not just one face of it.
    #
    # The "only if strictly better" guard is what keeps this safe: a label
    # that already has a correct, closer whole-polygon match elsewhere
    # (e.g. SW8, which merely sits incidentally near this same merged loop)
    # is never redirected here.
    def _pt_eq(p1, p2):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1]) < 1.0

    _open_ents: list = []
    for ent in msp:
        if ent.dxftype() != 'LWPOLYLINE' or ent.is_closed:
            continue
        _layer_up = ent.dxf.layer.upper()
        if 'DIM' in _layer_up or 'GRID' in _layer_up:
            continue  # dimension/grid lines are never structural wall outlines
        try:
            _pts = [(p[0], p[1]) for p in ent.get_points()]
            if len(_pts) < 2 or _pt_eq(_pts[0], _pts[-1]):
                continue  # too short, or self-closing (handled earlier already)
            _open_ents.append({'pts': _pts, 'layer': ent.dxf.layer})
        except Exception:
            continue

    _used_open: set = set()
    _merged_loops: list = []
    for _i, _o in enumerate(_open_ents):
        if _i in _used_open:
            continue
        _chain = [_o]
        _chain_idx = {_i}
        _cur_end = _o['pts'][-1]
        _start_pt = _o['pts'][0]
        _guard = 0
        while not _pt_eq(_cur_end, _start_pt) and _guard < 10:
            _guard += 1
            _found = None
            for _j, _o2 in enumerate(_open_ents):
                if _j in _chain_idx or _j in _used_open or _o2['layer'] != _o['layer']:
                    continue
                if _pt_eq(_o2['pts'][0], _cur_end):
                    _found = _o2['pts']
                    break
                if _pt_eq(_o2['pts'][-1], _cur_end):
                    _found = list(reversed(_o2['pts']))
                    break
                _j = None
            if _found is None:
                break
            _chain.append({'pts': _found})
            _chain_idx.add(_j)
            _cur_end = _found[-1]
        if _pt_eq(_cur_end, _start_pt) and len(_chain) >= 2:
            _merged_pts = list(_chain[0]['pts'])
            for _c in _chain[1:]:
                _merged_pts.extend(_c['pts'][1:])
            _merged_pts = _merged_pts[:-1]  # drop final point (== first point)
            _mxs = [p[0] for p in _merged_pts]; _mys = [p[1] for p in _merged_pts]
            if (max(_mxs) - min(_mxs)) >= 150 and (max(_mys) - min(_mys)) >= 150:
                _merged_loops.append(_merged_pts)
            _used_open |= _chain_idx

    for _mpts in _merged_loops:
        _n = len(_mpts)
        _mxs = [p[0] for p in _mpts]
        _mys = [p[1] for p in _mpts]

        def _merged_edge_distance(lx, ly):
            best = float('inf')

            for _i in range(_n):
                _x1, _y1 = _mpts[_i]
                _x2, _y2 = _mpts[(_i + 1) % _n]

                _d = _point_to_segment_distance(
                    lx, ly,
                    _x1, _y1,
                    _x2, _y2,
                )

                if _d < best:
                    best = _d

            return best

        _near_labels = [
            (lx, ly, lt.upper())
            for lx, ly, lt in label_positions
            if _SW_LABEL_RE.match(lt)
            and (not _sched_labels or lt.upper() in _sched_labels)
        ]

        if not _near_labels:
            continue

        _lx, _ly, _ = min(
            _near_labels,
            key=lambda t: _merged_edge_distance(t[0], t[1])
        )
        _loop_d = _merged_edge_distance(_lx, _ly)

        _best_normal_d = float('inf')
        for _poly in sig_polys:
            _dd = _label_to_polygon_edge_distance(_lx, _ly, _poly)
            if _dd < _best_normal_d:
                _best_normal_d = _dd

        if _loop_d >= _best_normal_d:
            continue

        sig_polys.append({
            'pts': _mpts,
            'w': max(_mxs) - min(_mxs),
            'h': max(_mys) - min(_mys),
            'npts': _n,
            'min_x': min(_mxs),
            'max_x': max(_mxs),
            'min_y': min(_mys),
            'max_y': max(_mys),
        })
    #print("After merge all open polygon ;",len(sig_polys))

    # ── Global label-to-polygon matching ───────────────────────────────────
    # Match each plan label occurrence to one unique polygon using global
    # minimum distance from the label point to the actual polygon boundary.
    # No centroid is used for label matching.

    label_occurrences = []

    for lx, ly, ltxt in label_positions:
        if not _SW_LABEL_RE.match(ltxt):
            continue

        lbl_up = ltxt.upper()

        if _sched_labels and lbl_up not in _sched_labels:
            continue

        label_occurrences.append({
            'x': lx,
            'y': ly,
            'label': lbl_up,
        })

    distance_matrix = []

    for label_item in label_occurrences:
        lx = label_item['x']
        ly = label_item['y']

        distance_matrix.append([
            _label_to_polygon_edge_distance(lx, ly, poly)
            for poly in sig_polys
        ])

    from scipy.optimize import linear_sum_assignment

    rows, cols = linear_sum_assignment(distance_matrix)

    poly_label = {}
    poly_dist = {}

    for row, col in zip(rows, cols):
        poly_label[int(col)] = label_occurrences[row]['label']
        poly_dist[int(col)] = distance_matrix[row][col]

    print("poly labels :", poly_label)

    # ── Group polylines by label and build BOQ ─────────────────────────────
    from collections import defaultdict as _dd
    label_polys: dict = _dd(list)
    for pi, label in poly_label.items():
        label_polys[label].append(sig_polys[pi])

    elements: list = []
    boqs:     list = []

    from src.engine.panel_optimizer import optimize_polygon_element

    for label, group in sorted(label_polys.items()):
        # Pick the most structurally significant polyline as representative:
        # prefer highest vertex count (L/T-shapes beat rectangles), then largest
        # bounding-box area.  Remaining group members contribute to quantity.
        rep = max(group, key=lambda p: (p['npts'], p['w'] * p['h']))
        # Use plan-area label text count as authoritative qty.
        # Falls back to polygon count only if the label had no text in the plan
        # (e.g. drawing only has the schedule table, no plan-view labels).
        qty = _plan_label_cnt.get(label, 0) or len(group)

        pts     = rep['pts']
        corners = _classify_polygon_corners(pts)
        f_nets  = _compute_polygon_face_nets(pts, corners)
        oc_cnt  = corners.count('OC80')
        ic_cnt  = corners.count('IC100')

        # Classify element type from bounding box
        long_mm  = max(rep['w'], rep['h'])
        short_mm = min(rep['w'], rep['h'])
        if long_mm / max(short_mm, 1) <= 4.0 and short_mm <= 1500:
            elem_type = ElementType.COLUMN
        else:
            elem_type = ElementType.SHEAR_WALL

        elem = StructuralElement(
            element_type=elem_type,
            label=label,
            length_mm=round(long_mm),
            width_mm=round(short_mm),
            height_mm=product_height_mm,
            quantity=qty,
            notes=f"Polygon: {len(pts)} vertices, OC×{oc_cnt}, IC×{ic_cnt}",
            polygon_pts=list(pts),
        )

        boq = optimize_polygon_element(
            element=elem,
            face_nets=f_nets,
            oc_count=oc_cnt,
            ic_count=ic_cnt,
            product_height_mm=product_height_mm,
        )

        elements.append(elem)
        boqs.append(boq)

    if not elements:
        return [], [], "Labels matched but no BOQ could be computed"

    return elements, boqs, None

