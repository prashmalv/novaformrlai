from src.dwg_parse.detect_scale import _parse_dimension_value

# ──────────────────────────────────────────
# Dimension-entity annotation lookup
# ──────────────────────────────────────────

def _build_dimension_lookup(msp, scale: float) -> list[dict]:
    """
    Collect all linear DIMENSION entities with their:
      - midpoint (average of both defpoints)
      - measurement value in mm
    So we can look up annotated dimensions near an element.
    """
    dims = []
    for e in msp:
        try:
            if e.dxftype() != 'DIMENSION':
                continue
            meas_raw = e.get_measurement()
            if not meas_raw or meas_raw <= 0:
                continue
            meas_mm = meas_raw * scale

            # Text override (e.g. "3000") takes priority
            raw_text = (e.dxf.text or "").strip()
            if raw_text and raw_text not in ("<>", "< >", ""):
                parsed = _parse_dimension_value(raw_text)
                if parsed and parsed > 0:
                    meas_mm = parsed

            # Midpoint of the dimension line
            try:
                defpt1 = e.dxf.defpoint
                defpt2 = e.dxf.defpoint2 if hasattr(e.dxf, 'defpoint2') else e.dxf.defpoint
                mx = (defpt1.x + defpt2.x) / 2
                my = (defpt1.y + defpt2.y) / 2
            except Exception:
                try:
                    ins = e.dxf.text_midpoint
                    mx, my = ins.x, ins.y
                except Exception:
                    continue

            dims.append({'x': mx, 'y': my, 'mm': meas_mm})
        except Exception:
            continue
    return dims
