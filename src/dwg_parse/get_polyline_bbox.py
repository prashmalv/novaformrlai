
# ──────────────────────────────────────────
# DXF Geometry Analysis
# ──────────────────────────────────────────

def _get_polyline_bbox(entity) -> tuple[float, float, float, float] | None:
    """Get bounding box of a closed polyline. Returns (x_min, y_min, x_max, y_max)."""
    try:
        pts = []
        if entity.dxftype() == 'LWPOLYLINE':
            pts = [(p[0], p[1]) for p in entity.get_points()]
        elif entity.dxftype() == 'POLYLINE':
            pts = [(v.dxf.location.x, v.dxf.location.y)
                   for v in entity.vertices]
        elif entity.dxftype() in ('RECTANGLE', 'SOLID'):
            pts = [(entity.dxf.vtx0.x, entity.dxf.vtx0.y),
                   (entity.dxf.vtx1.x, entity.dxf.vtx1.y),
                   (entity.dxf.vtx2.x, entity.dxf.vtx2.y),
                   (entity.dxf.vtx3.x, entity.dxf.vtx3.y)]

        if len(pts) < 3:
            return None

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)
    except Exception:
        return None

