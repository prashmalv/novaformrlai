def _collect_polylines(msp) -> list[dict]:
    """Return list of polyline dicts with bbox info."""
    out = []
    for e in msp.query("LWPOLYLINE"):
        try:
            pts = list(e.get_points())
            if not pts:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            x0, x1 = min(xs), max(xs)
            y0, y1 = min(ys), max(ys)
            w, h = x1 - x0, y1 - y0
            if w < 1 or h < 1:
                continue
            out.append({
                'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1,
                'w': w, 'h': h,
                'cx': (x0 + x1) / 2,
                'cy': (y0 + y1) / 2,
                'closed': e.is_closed,
                'verts': len(pts),   # vertex count: 4=rect, 6/8=L-shape
            })
        except Exception:
            pass
    return out
