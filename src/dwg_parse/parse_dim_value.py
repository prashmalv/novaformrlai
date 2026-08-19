import re

def _parse_dim_value(txt: str):
    """
    Parse one schedule-table cell.
    Returns: (length_mm, width_mm) | 'AS_PER_PLAN' | None (blank/dash/skip)
    """
    s = txt.strip().upper()
    if not s or set(s) <= {'-', ' ', '_'}:
        return None
    if any(kw in s for kw in ('AS PER PLAN', 'AS PER MAP', 'AS PER LAYOUT',
                               'AS PER SITE', 'AS PER DRAW', 'MAP')):
        return 'AS_PER_PLAN'
    m = re.match(r'(\d+)\s*[xX×]\s*(\d+)', s)
    if m:
        d1, d2 = int(m.group(1)), int(m.group(2))
        return (max(d1, d2), min(d1, d2))
    return None