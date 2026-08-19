

def _get_schedule_regions(raw_texts_xy: list) -> list:
    """
    Return (x_min, x_max, y_min, y_max) bounding boxes for schedule table areas.
    Used to exclude table-area labels from plan-area label counting.
    """
    regions = []
    for kw in ('COLUMN SCHEDULE', 'SHEAR WALL SCHEDULE'):
        matches = [(x, y) for x, y, t in raw_texts_xy if kw in t.upper()]
        if not matches:
            continue
        sec_x, sec_y = max(matches, key=lambda r: r[1])
        regions.append((
            sec_x - 500,    # x_min
            sec_x + 15000,  # x_max
            sec_y - 20000,  # y_min
            sec_y + 2000,   # y_max (include header row itself)
        ))
    return regions
