from src.dwg_parse.parse_nova_schedule_table import parse_nova_schedule_table
from src.dwg_parse.clean_text import _clean_mtext_full
from src.dwg_parse.get_schedule_region import _get_schedule_regions
from src.models.element import StructuralElement, ElementType
from src.dwg_parse.parse_nova_shear_walls import parse_nova_shear_walls

import re

try:
    import ezdxf
    EZDXF_OK = True
except ImportError:
    EZDXF_OK = False

# ─────────────────────────────────────────────────────────────────────────────
# Unified Nova Parser  (schedule table + polygon geometry)
# ─────────────────────────────────────────────────────────────────────────────

def parse_nova_full(
    dxf_path: str,
    product_height_mm: float = 3705.0,
    casting_height_mm: float = 3705.0,
    doc=None,
) -> tuple:
    """
    Primary Nova DXF parser.  Combines two sources:

    1. COLUMN / SHEAR WALL SCHEDULE table  → authoritative dimensions
    2. Closed LWPOLYLINE geometry           → instance count (qty) &
                                              geometry for AS_PER_PLAN elements

    Priority rules:
    * Explicit schedule dimension (e.g. "600x900") → use it; compute BOQ with
      compute_boq() treating the element as a simple rectangle.
    * "AS PER PLAN" in schedule (or label absent from schedule) → use polygon
      geometry BOQ from optimize_polygon_element().
    * Elements in schedule but not found in drawing → add with qty=1 so the
      user can review and adjust.

    Returns: (elements, boqs, error_or_None)
    """
    if not EZDXF_OK:
        return [], [], "ezdxf not installed"

    if doc is None:
        try:
            doc = ezdxf.readfile(dxf_path)
        except Exception as e:
            return [], [], f"Cannot open DXF: {e}"

    # ── Step 1: schedule table (authoritative dimensions) ─────────────────
    schedule = parse_nova_schedule_table(doc)

    # ── Step 1b: count plan-area label occurrences for schedule-only elements ─
    # For elements in the schedule that the polygon parser did not find in the
    # drawing, we count how many times their label TEXT appears in the plan area
    # (excluding the schedule table region).  This is the authoritative qty.
    try:
        _msp_pnf = doc.modelspace()
    except Exception:
        _msp_pnf = None

    _pnf_raw_texts: list = []
    if _msp_pnf is not None:
        for _ent in _msp_pnf:
            try:
                if _ent.dxftype() == 'TEXT':
                    _raw = _ent.dxf.text
                    _pos = _ent.dxf.insert
                elif _ent.dxftype() == 'MTEXT':
                    try:
                        _raw = _ent.plain_text()
                    except Exception:
                        _raw = _ent.text
                    _pos = _ent.dxf.insert
                else:
                    continue
                _cleaned = _clean_mtext_full(_raw)
                if _cleaned:
                    _pnf_raw_texts.append((_pos.x, _pos.y, _cleaned))
            except Exception:
                continue

    _pnf_sched_regions = _get_schedule_regions(_pnf_raw_texts)

    def _pnf_in_table(lx: float, ly: float) -> bool:
        return any(rx0 <= lx <= rx1 and ry0 <= ly <= ry1
                   for rx0, rx1, ry0, ry1 in _pnf_sched_regions)

    from collections import Counter as _PNFCtr
    _pnf_cnt = _PNFCtr()
    for _lx, _ly, _lt in _pnf_raw_texts:
        _lt_u = _lt.strip().upper()
        # if re.match(r'^[A-Z]{1,3}\d+[A-Z]?$', _lt_u) and not _pnf_in_table(_lx, _ly):     regex is updated
        if re.match(r'^(?!H-?\d)[A-Z]{1,3}-?\d+[A-Z]?$', _lt_u) and not _pnf_in_table(_lx, _ly):
            _pnf_cnt[_lt_u] += 1
    _pnf_label_cnt: dict = dict(_pnf_cnt)

    # ── Step 2: polygon geometry (qty counts + AS_PER_PLAN shapes) ─────────
    poly_elements, poly_boqs, _ = parse_nova_shear_walls(
        dxf_path, product_height_mm=product_height_mm, doc=doc)

    poly_lookup: dict = {e.label: (e, b)
                         for e, b in zip(poly_elements, poly_boqs)}

    # ── Step 3: merge ──────────────────────────────────────────────────────
    from src.engine.panel_optimizer import compute_boq as _compute_boq

    _COLUMN_PREFIX = re.compile(r'^C\d', re.I)

    elements: list = []
    boqs:     list = []
    seen:     set  = set()

    def _elem_type(label: str) -> 'ElementType':
        return ElementType.COLUMN if _COLUMN_PREFIX.match(label) else ElementType.SHEAR_WALL

    # Process elements that the polygon parser found in the drawing
    for label_up, (poly_elem, poly_boq) in sorted(poly_lookup.items()):
        seen.add(label_up)
        sched_val = schedule.get(label_up)

        if sched_val is not None and sched_val != 'AS_PER_PLAN':
            # Authoritative schedule dimension → override polygon geometry
            length_mm, width_mm = sched_val
            elem = StructuralElement(
                element_type=_elem_type(label_up),
                label=label_up,
                length_mm=length_mm,
                width_mm=width_mm,
                height_mm=casting_height_mm,
                quantity=poly_elem.quantity,
                notes=f"Schedule: {length_mm}×{width_mm}mm",
                polygon_pts=poly_elem.polygon_pts,  # keep shape for floor-plan diagram
            )
            try:
                boq = _compute_boq(elem, panel_height_mm=product_height_mm)
            except Exception:
                boq = poly_boq  # fallback if optimizer can't handle this type
        else:
            # AS_PER_PLAN or not in schedule → polygon geometry is authoritative
            elem = poly_elem
            boq  = poly_boq

        elements.append(elem)
        boqs.append(boq)

    # Elements in schedule but NOT found in drawing geometry → add with qty=1
    for label_up, sched_val in sorted(schedule.items()):
        if label_up in seen:
            continue
        if sched_val is None or sched_val == 'AS_PER_PLAN':
            # AS_PER_PLAN with no matching polygon → include as placeholder with warning
            elem = StructuralElement(
                element_type=_elem_type(label_up),
                label=label_up,
                length_mm=0,
                width_mm=0,
                height_mm=casting_height_mm,
                quantity=_pnf_label_cnt.get(label_up, 0) or 1,
                notes=f"AS_PER_PLAN — polygon shape not found in DXF",
            )
            from src.models.element import ElementBOQ as _BOQ
            boq = _BOQ(
                element=elem,
                panels=[],
                spacer_mm=0.0,
                height_note="",
                price_per_set=0.0,
                num_sets=1,
                grand_total=0.0,
                warnings=[
                    f"{label_up}: Shape polygon not found in DXF. "
                    "Enter dimensions manually to generate BOQ."
                ],
            )
            elements.append(elem)
            boqs.append(boq)
            continue
        length_mm, width_mm = sched_val
        # Count actual instances in the drawing by dimension matching
        qty = _pnf_label_cnt.get(label_up, 0) or 1
        elem = StructuralElement(
            element_type=_elem_type(label_up),
            label=label_up,
            length_mm=length_mm,
            width_mm=width_mm,
            height_mm=casting_height_mm,
            quantity=qty,
            notes=f"Schedule: {length_mm}×{width_mm}mm",
        )
        try:
            boq = _compute_boq(elem, panel_height_mm=product_height_mm)
            elements.append(elem)
            boqs.append(boq)
        except Exception:
            pass

    if not elements:
        return [], [], (
            "No elements found.  The drawing may not have a COLUMN / SHEAR WALL"
            " SCHEDULE table, and no labelled structural polylines were detected."
        )

    return elements, boqs, None
