import math


def _dist(p1, p2) -> float:
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def _is_rectangular(entity, tolerance_ratio: float = 0.05) -> bool:
    """Check if a polyline is approximately rectangular."""
    try:
        pts = []
        if entity.dxftype() == 'LWPOLYLINE':
            pts = [(p[0], p[1]) for p in entity.get_points()]

        if len(pts) < 4:
            return False

        # For a rectangle: 4 points, all angles ~90°
        if len(pts) == 4 or (len(pts) == 5 and _dist(pts[0], pts[-1]) < 1):
            pts = pts[:4]
            angles = []
            n = len(pts)
            for i in range(n):
                p0 = pts[(i - 1) % n]
                p1 = pts[i]
                p2 = pts[(i + 1) % n]
                v1 = (p1[0] - p0[0], p1[1] - p0[1])
                v2 = (p2[0] - p1[0], p2[1] - p1[1])
                dot = v1[0]*v2[0] + v1[1]*v2[1]
                mag1 = math.sqrt(v1[0]**2 + v1[1]**2)
                mag2 = math.sqrt(v2[0]**2 + v2[1]**2)
                if mag1 * mag2 < 1e-6:
                    continue
                cos_a = max(-1, min(1, dot / (mag1 * mag2)))
                angles.append(abs(math.degrees(math.acos(cos_a))))

            return all(abs(a - 90) < 15 for a in angles if a > 1)

        return False
    except Exception:
        return False
