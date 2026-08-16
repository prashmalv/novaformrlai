import re


def _parse_dimension_value(text: str, default_unit: str = "mm") -> float | None:
    """
    Parse dimension text to mm.
    Handles: "3000", "3000mm", "3.0m", "10'-0\"", "10'6\""
    """
    text = text.strip().replace(',', '')

    # Feet-inches: 10'-6" or 10'6"
    fi = re.match(r"(\d+)'\s*-?\s*(\d+)\"?", text)
    if fi:
        ft, inch = int(fi.group(1)), int(fi.group(2))
        return round((ft * 12 + inch) * 25.4)

    # Feet only: 10'
    f_only = re.match(r"(\d+)'$", text)
    if f_only:
        return round(int(f_only.group(1)) * 304.8)

    # Numeric with optional unit
    m = re.match(r"(\d+(?:\.\d+)?)\s*(mm|cm|m)?$", text, re.I)
    if m:
        val = float(m.group(1))
        unit = (m.group(2) or default_unit).lower()
        if unit == 'm':
            return round(val * 1000)
        elif unit == 'cm':
            return round(val * 10)
        else:
            return round(val)

    return None




# ──────────────────────────────────────────
# Scale Detection
# ──────────────────────────────────────────

# DXF $INSUNITS code → mm conversion factor
_INSUNITS_TO_MM = {
    0:  1.0,       # Unitless (assume mm for Indian structural)
    1:  25.4,      # Inches
    2:  304.8,     # Feet
    4:  1.0,       # Millimeters  ← most common
    5:  10.0,      # Centimeters
    6:  1000.0,    # Meters
    7:  1e6,       # Kilometers
    8:  1e-3,      # Microinches
    9:  25.4e-3,   # Mils (thou)
    10: 1.0,       # Yards? (non-standard)
    13: 25.4,      # US survey inch
    14: 304.8,     # US survey foot
}


def _detect_scale(doc, msp) -> float:
    """
    Detect drawing scale (mm per drawing unit).

    Steps:
      1. Collect raw geometry sizes (polyline short sides).
      2. Try to calibrate from DIMENSION entity text vs. measured geometry.
      3. Try $INSUNITS header — but VALIDATE against geometry sizes.
      4. Fall back to geometry heuristic.

    For Indian structural CAD, typical short-side values for columns/walls
    are 150–1500mm. We use this to detect and correct scale errors.
    """
    # --- Step 1: collect geometry sizes (raw drawing units) ---
    raw_sizes = []
    for e in msp:
        try:
            if e.dxftype() != 'LWPOLYLINE' or not e.is_closed:
                continue
            pts = [(p[0], p[1]) for p in e.get_points()]
            if len(pts) < 4:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            w = max(xs) - min(xs)
            h = max(ys) - min(ys)
            if w > 5 and h > 5:
                raw_sizes.append(min(w, h))
        except Exception:
            continue

    def _scale_makes_sense(scale: float) -> bool:
        """Check if applying this scale gives sizes in the structural range.

        Indian CAD drawings often have many small annotation boxes (title blocks,
        legend, dimension lines ~45-80 raw units) that skew the median downward.
        We skip the bottom 70% and evaluate the top 30% of shape sizes, which
        represent the actual structural elements and rooms in the drawing.
        Structural range for columns/walls: 100–5000mm.
        """
        if not raw_sizes:
            return True  # can't tell, accept
        sorted_s = sorted(raw_sizes)
        # Use top 10% — Indian CAD drawings often have 85–90% of their polylines
        # as legend/annotation boxes (~80mm), so only the largest 10% contains
        # actual structural elements (columns 300–1500mm, walls 200–600mm thickness).
        top_start = int(len(sorted_s) * 0.90)
        top_slice = sorted_s[top_start:] if top_start < len(sorted_s) else sorted_s
        median_large = top_slice[len(top_slice) // 2]
        return 100 <= median_large * scale <= 5000

    # --- Step 2: calibrate from DIMENSION entities ---
    # Only use dimensions with explicit text overrides (not auto "<>" or empty).
    # Empty-text dims give ratio=1.0 tautologically and mislead the calibration.
    dim_samples = []
    for e in msp:
        try:
            if e.dxftype() != 'DIMENSION':
                continue
            meas = e.get_measurement()
            raw_text = (e.dxf.text or "").strip()
            if raw_text in ("", "<>", "< >"):
                continue  # Skip auto-measured dims — they can't calibrate scale
            parsed = _parse_dimension_value(raw_text)
            if parsed and meas and meas > 0 and parsed > 50:
                dim_samples.append(parsed / meas)
        except Exception:
            continue

    if dim_samples:
        dim_samples.sort()
        ratio = dim_samples[len(dim_samples) // 2]
        for expected in [1.0, 10.0, 100.0, 1000.0, 25.4, 304.8]:
            if abs(ratio - expected) / expected < 0.15 and _scale_makes_sense(expected):
                return expected

    # --- Step 3: $INSUNITS header (validated against geometry) ---
    try:
        insunits = doc.header.get('$INSUNITS', 0)
        if insunits != 0 and insunits in _INSUNITS_TO_MM:
            candidate = _INSUNITS_TO_MM[insunits]
            if _scale_makes_sense(candidate):
                return candidate
    except Exception:
        pass

    # --- Step 4: geometry heuristic ---
    if raw_sizes:
        raw_sizes.sort()
        median_raw = raw_sizes[len(raw_sizes) // 2]
        # Try each standard scale and pick the one whose result falls in range
        for scale in [1.0, 10.0, 1000.0, 100.0, 25.4, 304.8, 0.1]:
            if _scale_makes_sense(scale):
                return scale

    return 1.0  # default: millimetres
