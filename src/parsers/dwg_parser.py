"""
DWG/DXF Parser — extracts structural elements from AutoCAD drawings.

Strategy:
1. Binary DWG → convert to DXF using dwg2dxf (LibreDWG) or ODA File Converter
2. Parse DXF using ezdxf
3. Identify structural elements from geometry + text labels
4. Extract dimensions from:
   a. Dimension entities (DIMENSION)
   b. TEXT/MTEXT entities near geometry
   c. Measured geometry itself

Phase 1 scope: Columns & Walls from closed polylines / rectangles.
"""
import os
import re
import subprocess
import tempfile
import math
from pathlib import Path
from collections import defaultdict

try:
    import ezdxf
    from ezdxf.math import Vec2, BoundingBox2d
    EZDXF_OK = True
except ImportError:
    EZDXF_OK = False

from src.models.element import StructuralElement, ElementType, PanelEntry, ElementBOQ


# ──────────────────────────────────────────
# DWG → DXF conversion
# ──────────────────────────────────────────

def _find_dwg2dxf() -> str | None:
    """Locate dwg2dxf binary (from LibreDWG)."""
    candidates = [
        "/opt/homebrew/bin/dwg2dxf",
        "/usr/local/bin/dwg2dxf",
        "dwg2dxf",
    ]
    for c in candidates:
        try:
            result = subprocess.run([c, "--version"],
                                    capture_output=True, timeout=5)
            return c
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def _find_oda_converter() -> str | None:
    """Locate ODA File Converter."""
    candidates = [
        "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter",
        r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def dwg_to_dxf(dwg_path: str, output_dir: str = None) -> str | None:
    """
    Convert a DWG file to DXF.
    Returns path to the generated DXF, or None if conversion failed.
    """
    dwg_path = str(dwg_path)
    if output_dir is None:
        output_dir = tempfile.mkdtemp()

    stem = Path(dwg_path).stem
    dxf_path = os.path.join(output_dir, f"{stem}.dxf")

    # Try dwg2dxf (LibreDWG)
    bin_path = _find_dwg2dxf()
    if bin_path:
        try:
            result = subprocess.run(
                [bin_path, dwg_path, "--output", dxf_path],
                capture_output=True, text=True, timeout=60
            )
            if os.path.exists(dxf_path):
                return dxf_path
        except Exception as e:
            pass

    # Try ODA File Converter
    oda = _find_oda_converter()
    if oda:
        try:
            input_dir = str(Path(dwg_path).parent)
            result = subprocess.run(
                [oda, input_dir, output_dir, "ACAD2018", "DXF", "0", "1"],
                capture_output=True, text=True, timeout=120
            )
            if os.path.exists(dxf_path):
                return dxf_path
        except Exception:
            pass

    return None


def get_conversion_status() -> dict:
    """Check what DWG conversion tools are available."""
    return {
        "dwg2dxf": _find_dwg2dxf() is not None,
        "oda_converter": _find_oda_converter() is not None,
        "ezdxf": EZDXF_OK,
    }


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


def _dist(p1, p2) -> float:
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)


def _bbox_dims(bbox: tuple) -> tuple[float, float]:
    """Returns (width, height) of a bounding box in drawing units."""
    x_min, y_min, x_max, y_max = bbox
    return abs(x_max - x_min), abs(y_max - y_min)


# ──────────────────────────────────────────
# Text / Dimension Extraction
# ──────────────────────────────────────────

DIM_PATTERN = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*(mm|cm|m|\'|"|-0")?', re.IGNORECASE)

# Matches "750x375", "750X375", "750×375" in text entities
_DIM_TEXT_RE = re.compile(r'(\d{2,4})\s*[xX×]\s*(\d{2,4})')


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


def _extract_text_entities(msp) -> list[dict]:
    """Extract all text entities with position and content."""
    texts = []
    for e in msp:
        try:
            if e.dxftype() == 'TEXT':
                texts.append({
                    'type': 'TEXT',
                    'content': e.dxf.text,
                    'x': e.dxf.insert.x,
                    'y': e.dxf.insert.y,
                    'layer': e.dxf.layer,
                })
            elif e.dxftype() == 'MTEXT':
                raw = e.text
                # Strip MTEXT formatting codes
                clean = re.sub(r'\\[A-Za-z][^;]*;', '', raw)
                clean = re.sub(r'\{[^}]*\}', '', clean)
                clean = clean.replace('\\P', ' ').strip()
                texts.append({
                    'type': 'MTEXT',
                    'content': clean,
                    'x': e.dxf.insert.x,
                    'y': e.dxf.insert.y,
                    'layer': e.dxf.layer,
                })
        except Exception:
            continue
    return texts


_FLOOR_LABEL_RE = re.compile(
    r'^(GF|RF|TF|PH|B[1-9]|[FB]\d{1,2}|\d{1,2}F)$', re.I
)


def _find_nearby_label(cx: float, cy: float, texts: list[dict],
                        radius: float = 2000) -> tuple[str | None, str]:
    """
    Find nearest element label within radius of center point.
    Returns (label, floor_label) — floor_label is '' if no valid floor suffix.
    Handles: C1, SW1, CC1, CC1/F1, W3/GF (Drawing-4 style multi-floor labels).
    Floor label validated against common patterns (GF, F1-F99, B1-B9, RF, TF, PH).
    """
    best, best_d, best_floor = None, float('inf'), ''
    for t in texts:
        d = math.sqrt((t['x'] - cx)**2 + (t['y'] - cy)**2)
        if d >= radius or d >= best_d:
            continue
        content = t['content'].strip()
        # Multi-floor format: LABEL/FLOOR  e.g. CC1/F1, W3/GF
        mf = re.match(r'^([A-Za-z]{1,3}\d+[A-Za-z]?)/([A-Za-z0-9]+)$', content, re.I)
        if mf:
            candidate_label = mf.group(1).upper()
            candidate_floor = mf.group(2).upper()
            # Only accept floor suffix if it looks like a real floor designation
            if _FLOOR_LABEL_RE.match(candidate_floor):
                best, best_d, best_floor = candidate_label, d, candidate_floor
            else:
                # Treat the whole thing as a plain label (ignore the suffix)
                best, best_d, best_floor = candidate_label, d, ''
            continue
        # Standard label: C1, SW1, CC1, WW2, etc.
        if re.match(r'^[A-Za-z]{1,3}\d+[A-Za-z]?$', content, re.I):
            best, best_d, best_floor = content.upper(), d, ''
    return best, best_floor


def _find_dims_from_text(cx: float, cy: float, texts: list[dict],
                          radius: float = 2000) -> tuple[float, float] | None:
    """
    Fallback dimension extraction from nearby text like '750x375'.
    Returns (long_mm, short_mm) or None if nothing found.
    Used when DIMENSION annotations are absent (Drawing-4 style drawings).
    """
    candidates = []
    for t in texts:
        d = math.sqrt((t['x'] - cx)**2 + (t['y'] - cy)**2)
        if d > radius:
            continue
        m = _DIM_TEXT_RE.search(t['content'])
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a >= 100 and b >= 100:  # ignore tiny annotation values
                candidates.append((d, float(max(a, b)), float(min(a, b))))
    if candidates:
        candidates.sort()
        return candidates[0][1], candidates[0][2]
    return None


def _extract_dimension_entities(msp) -> list[dict]:
    """Extract DIMENSION entities — most reliable dimension source."""
    dims = []
    for e in msp:
        try:
            if e.dxftype() == 'DIMENSION':
                text = e.dxf.text if hasattr(e.dxf, 'text') and e.dxf.text else ""
                # Measurement is stored in actual_measurement
                meas = None
                try:
                    meas = e.get_measurement()
                except Exception:
                    pass

                dims.append({
                    'text': text,
                    'measurement': meas,
                    'layer': e.dxf.layer,
                })
        except Exception:
            continue
    return dims


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


def _find_annotated_dim(cx: float, cy: float,
                         dim_lookup: list[dict],
                         radius: float = 5000,
                         target_mm: float = None) -> float | None:
    """
    Find the best DIMENSION annotation near (cx, cy) for a given raw dimension.

    Indian structural DXF drawings commonly draw only the reinforcement stirrup
    cage as the polyline — NOT the concrete face.  The concrete face dimensions
    are annotated separately and are always >= stirrup cage dimensions.

    Strategy (when target_mm given):
      1. Search within a tighter radius (max 2500 units) for values in the range
         [0.85×target, 1.55×target].  Among those, prefer the LARGEST value
         (outer concrete face ≥ inner stirrup cage).
      2. Fallback: search full radius for closest value within ±20%.
    """
    if not dim_lookup:
        return None

    if target_mm is None:
        # No target — return the closest annotation overall
        best = min(dim_lookup,
                   key=lambda d: math.sqrt((d['x']-cx)**2 + (d['y']-cy)**2),
                   default=None)
        return best['mm'] if best else None

    # --- Pass 1: prefer larger annotation (concrete face > stirrup cage) ---
    # Use a tighter radius so we don't steal a neighbour's dimension.
    tight_radius = min(radius, max(target_mm * 2.5, 2500))
    outer_candidates = []
    for d in dim_lookup:
        dist = math.sqrt((d['x'] - cx)**2 + (d['y'] - cy)**2)
        if dist <= tight_radius and 100 <= d['mm'] <= 6000:
            # Accept values in [0.85×target … 1.55×target]
            if target_mm * 0.85 <= d['mm'] <= target_mm * 1.55:
                outer_candidates.append((dist, d['mm']))

    if outer_candidates:
        # Among valid candidates, return the LARGEST value.
        # Largest = outermost (concrete face), which is what formwork needs.
        outer_candidates.sort(key=lambda x: -x[1])
        return outer_candidates[0][1]

    # --- Pass 2: fallback — closest value within ±20% (original behaviour) ---
    all_in_radius = [(math.sqrt((d['x']-cx)**2 + (d['y']-cy)**2), d['mm'])
                     for d in dim_lookup
                     if math.sqrt((d['x']-cx)**2 + (d['y']-cy)**2) <= radius]
    all_in_radius.sort(key=lambda x: x[0])
    for _, mm in all_in_radius:
        if abs(mm - target_mm) / max(target_mm, 1) < 0.20:
            return mm

    return None


# ──────────────────────────────────────────
# Main Element Extraction
# ──────────────────────────────────────────

# Layer name patterns suggesting structural elements
COLUMN_LAYER_HINTS = ['col', 'column', 'stru', 'rcc', 'struct']
WALL_LAYER_HINTS = ['wall', 'shear', 'sw', 'core', 'lift']
SLAB_LAYER_HINTS = ['slab', 'floor', 'roof']

# Typical column dimensions range (mm)
COLUMN_MIN_DIM = 150
COLUMN_MAX_DIM = 1500
# Typical wall thickness range (mm)
WALL_MIN_THICKNESS = 100
WALL_MAX_THICKNESS = 600
WALL_MIN_LENGTH = 500


def _classify_element(length_mm: float, width_mm: float,
                       layer: str = "") -> ElementType | None:
    """
    Classify element type based on dimensions (primary) and layer name (tiebreaker).

    Dimension checks come first — layer hints only break ties when the shape could
    be either a stubby column or a thick shear-wall.  This prevents large floor-plan
    outlines on a 'COLUMN' layer from being misclassified as columns.
    """
    layer_lower = layer.lower()

    short = min(length_mm, width_mm)
    long  = max(length_mm, width_mm)

    # --- Dimension-based classification (primary) ---
    is_col_dims  = (COLUMN_MIN_DIM <= short <= COLUMN_MAX_DIM and
                    COLUMN_MIN_DIM <= long  <= COLUMN_MAX_DIM and
                    long / short <= 4.0)

    is_wall_dims = (WALL_MIN_THICKNESS <= short <= WALL_MAX_THICKNESS and
                    long >= WALL_MIN_LENGTH and
                    long / short >= 3.0)

    if is_col_dims and not is_wall_dims:
        return ElementType.COLUMN

    if is_wall_dims and not is_col_dims:
        # Check layer to pick Wall vs Shear Wall
        for hint in WALL_LAYER_HINTS:
            if hint in layer_lower:
                return ElementType.SHEAR_WALL
        return ElementType.WALL

    # Ambiguous (fits both or neither) — use layer as tiebreaker
    if is_col_dims and is_wall_dims:
        for hint in COLUMN_LAYER_HINTS:
            if hint in layer_lower:
                return ElementType.COLUMN
        for hint in WALL_LAYER_HINTS:
            if hint in layer_lower:
                return ElementType.SHEAR_WALL
        return ElementType.COLUMN  # default to column for square-ish shapes

    return None


def parse_dxf(dxf_path: str,
              casting_height_mm: float = 3000,
              unit_override: str = None) -> list[StructuralElement]:
    """
    Parse a DXF file and extract structural elements.

    Improvements over v1:
    - $INSUNITS header reading for scale
    - Calibration from DIMENSION entities
    - Annotated dimension lookup to correct bounding-box readings
    - Heuristic scale check from geometry sizes

    Returns a list of StructuralElement objects for user review.
    """
    if not EZDXF_OK:
        raise RuntimeError("ezdxf not installed.")

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    # --- Scale detection (improved) ---
    if unit_override:
        scale = {'mm': 1.0, 'cm': 10.0, 'm': 1000.0,
                 'inch': 25.4, 'ft': 304.8}.get(unit_override.lower(), 1.0)
    else:
        scale = _detect_scale(doc, msp)

    # --- Build dimension annotation lookup ---
    dim_lookup = _build_dimension_lookup(msp, scale)

    # --- Extract text labels ---
    texts = _extract_text_entities(msp)

    elements: list[StructuralElement] = []
    seen_labels: set[str] = set()
    label_counters: dict[str, int] = defaultdict(int)

    def _next_label(prefix: str) -> str:
        label_counters[prefix] += 1
        return f"{prefix}{label_counters[prefix]}"

    for entity in msp:
        etype_dxf = entity.dxftype()

        # Only process closed polylines
        if etype_dxf not in ('LWPOLYLINE', 'POLYLINE'):
            continue

        try:
            is_closed = entity.is_closed if hasattr(entity, 'is_closed') else False
            if not is_closed:
                continue
        except Exception:
            continue

        bbox = _get_polyline_bbox(entity)
        if not bbox:
            continue

        w_draw, h_draw = _bbox_dims(bbox)

        # Convert to mm using detected scale
        w_mm = w_draw * scale
        h_mm = h_draw * scale

        if w_mm < 50 or h_mm < 50:
            continue  # noise / dimension lines

        # Raw geometry dimensions
        length_mm_raw = max(w_mm, h_mm)
        width_mm_raw  = min(w_mm, h_mm)

        layer = ""
        try:
            layer = entity.dxf.layer
        except Exception:
            pass

        elem_type = _classify_element(length_mm_raw, width_mm_raw, layer)
        if elem_type is None:
            continue

        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2

        # --- Try to refine dimensions from DIMENSION annotations ---
        # Annotations often more accurate than bounding-box (accounts for
        # snap tolerances, line thickness, etc.)
        annotated_len = _find_annotated_dim(cx, cy, dim_lookup,
                                            radius=max(length_mm_raw, 5000),
                                            target_mm=length_mm_raw)
        annotated_wid = _find_annotated_dim(cx, cy, dim_lookup,
                                            radius=max(width_mm_raw, 3000),
                                            target_mm=width_mm_raw)

        # --- Fallback: extract dims from nearby "NNNxNNN" text (Drawing-4 style) ---
        text_dims = None
        if not annotated_len or not annotated_wid:
            text_dims = _find_dims_from_text(
                cx, cy, texts, radius=max(length_mm_raw * 2, 2000))

        length_mm = round(annotated_len if annotated_len else
                          (text_dims[0] if text_dims else length_mm_raw))
        width_mm  = round(annotated_wid  if annotated_wid  else
                          (text_dims[1] if text_dims else width_mm_raw))

        # Re-classify with refined dimensions
        elem_type = _classify_element(length_mm, width_mm, layer) or elem_type

        # --- Find nearby label (returns label + floor_label) ---
        label, floor_label = _find_nearby_label(cx, cy, texts)
        if label is None:
            prefix = "C" if elem_type == ElementType.COLUMN else "SW"
            label = _next_label(prefix)
            floor_label = ""

        if label in seen_labels:
            for e in elements:
                if e.label == label:
                    e.quantity += 1
                    break
            continue

        # Also check if an unlabeled auto-generated element with same type+dims exists
        matched = False
        if not re.match(r'^[A-Za-z]{1,3}\d+[A-Za-z]?$', label, re.I):
            for e in elements:
                if (e.element_type == elem_type and
                        abs(e.length_mm - length_mm) <= 10 and
                        abs(e.width_mm - width_mm) <= 10):
                    e.quantity += 1
                    matched = True
                    break

        if matched:
            continue

        seen_labels.add(label)

        elements.append(StructuralElement(
            element_type=elem_type,
            label=label,
            length_mm=length_mm,
            width_mm=width_mm,
            height_mm=casting_height_mm,
            quantity=1,
            floor_label=floor_label,
            notes=f"Layer: {layer} | Scale×{scale}"
        ))

    # --- Post-process: merge elements with identical type + dimensions (±5mm) ---
    # This consolidates duplicate polylines scattered across the drawing into
    # one entry with quantity = total count, as Nova quotations expect.
    return _merge_by_dimensions(elements)


def _merge_by_dimensions(elements: list) -> list:
    """
    Group elements that have the same type and dimensions (within ±5mm tolerance)
    into a single entry, summing their quantities.  The representative entry
    keeps the label that is most 'human-readable' (shortest / lowest-numbered).
    """
    merged: list = []

    for elem in elements:
        best_match = None
        for existing in merged:
            if (existing.element_type == elem.element_type and
                    abs(existing.length_mm - elem.length_mm) <= 5 and
                    abs(existing.width_mm - elem.width_mm) <= 5):
                best_match = existing
                break

        if best_match is not None:
            best_match.quantity += elem.quantity
            # Keep the shorter / lower-numbered label as the representative
            if len(elem.label) < len(best_match.label) or (
                    len(elem.label) == len(best_match.label) and
                    elem.label < best_match.label):
                best_match.label = elem.label
        else:
            merged.append(elem)

    return merged


def parse_dxf_full(
    dxf_path: str,
    casting_height_mm: float = 3000,
    unit_override: str = None,
) -> tuple[list, list[tuple], list[list], float]:
    """
    Parse a DXF file and return rich data for the drawing viewer.

    Returns:
        elements     — list of StructuralElement (same as parse_dxf)
        bboxes_raw   — list of (x_min, y_min, x_max, y_max) in RAW DXF units
                       one entry per element (aligned with elements list)
        all_polylines — list of [(x,y),...] point lists for ALL closed polylines
                        (used to render the drawing background)
        scale        — mm per DXF unit (detected scale factor)
    """
    if not EZDXF_OK:
        raise RuntimeError("ezdxf not installed.")

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    if unit_override:
        scale = {'mm': 1.0, 'cm': 10.0, 'm': 1000.0,
                 'inch': 25.4, 'ft': 304.8}.get(unit_override.lower(), 1.0)
    else:
        scale = _detect_scale(doc, msp)

    dim_lookup = _build_dimension_lookup(msp, scale)
    texts      = _extract_text_entities(msp)

    # ── Collect ALL closed polylines for background rendering ────────────────
    all_polylines: list[list] = []
    for entity in msp:
        if entity.dxftype() == 'LWPOLYLINE':
            try:
                pts = [(p[0], p[1]) for p in entity.get_points()]
                if len(pts) >= 2:
                    all_polylines.append(pts)
            except Exception:
                pass
        elif entity.dxftype() == 'LINE':
            try:
                p1 = (entity.dxf.start.x, entity.dxf.start.y)
                p2 = (entity.dxf.end.x,   entity.dxf.end.y)
                all_polylines.append([p1, p2])
            except Exception:
                pass

    # ── Extract elements (reuse the full parse_dxf logic) ───────────────────
    elements_raw:   list = []
    bboxes_raw:     list[tuple] = []
    seen_labels:    set[str] = set()
    label_counters: dict[str, int] = defaultdict(int)

    def _next_label(prefix: str) -> str:
        label_counters[prefix] += 1
        return f"{prefix}{label_counters[prefix]}"

    for entity in msp:
        if entity.dxftype() not in ('LWPOLYLINE', 'POLYLINE'):
            continue
        try:
            if not entity.is_closed:
                continue
        except Exception:
            continue

        bbox = _get_polyline_bbox(entity)
        if not bbox:
            continue

        w_draw, h_draw = _bbox_dims(bbox)
        w_mm = w_draw * scale
        h_mm = h_draw * scale

        if w_mm < 50 or h_mm < 50:
            continue

        length_mm_raw = max(w_mm, h_mm)
        width_mm_raw  = min(w_mm, h_mm)

        layer = ""
        try:
            layer = entity.dxf.layer
        except Exception:
            pass

        elem_type = _classify_element(length_mm_raw, width_mm_raw, layer)
        if elem_type is None:
            continue

        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2

        annotated_len = _find_annotated_dim(cx, cy, dim_lookup,
                                            radius=max(length_mm_raw, 5000),
                                            target_mm=length_mm_raw)
        annotated_wid = _find_annotated_dim(cx, cy, dim_lookup,
                                            radius=max(width_mm_raw, 3000),
                                            target_mm=width_mm_raw)

        text_dims = None
        if not annotated_len or not annotated_wid:
            text_dims = _find_dims_from_text(
                cx, cy, texts, radius=max(length_mm_raw * 2, 2000))

        length_mm = round(annotated_len if annotated_len else
                          (text_dims[0] if text_dims else length_mm_raw))
        width_mm  = round(annotated_wid  if annotated_wid  else
                          (text_dims[1] if text_dims else width_mm_raw))

        elem_type = _classify_element(length_mm, width_mm, layer) or elem_type

        label, floor_label = _find_nearby_label(cx, cy, texts)
        if label is None:
            prefix = "C" if elem_type == ElementType.COLUMN else "SW"
            label  = _next_label(prefix)
            floor_label = ""

        if label in seen_labels:
            for e, b in zip(elements_raw, bboxes_raw):
                if e.label == label:
                    e.quantity += 1
                    break
            continue

        matched = False
        if not re.match(r'^[A-Za-z]{1,3}\d+[A-Za-z]?$', label, re.I):
            for e in elements_raw:
                if (e.element_type == elem_type and
                        abs(e.length_mm - length_mm) <= 10 and
                        abs(e.width_mm  - width_mm)  <= 10):
                    e.quantity += 1
                    matched = True
                    break

        if matched:
            continue

        seen_labels.add(label)
        elements_raw.append(StructuralElement(
            element_type=elem_type,
            label=label,
            length_mm=length_mm,
            width_mm=width_mm,
            height_mm=casting_height_mm,
            quantity=1,
            floor_label=floor_label,
            notes=f"Layer: {layer}",
        ))
        bboxes_raw.append(bbox)  # raw DXF coords for viewer overlay

    # Merge by dimensions (keeps bboxes aligned by tracking indices)
    merged_elements, merged_bboxes = _merge_with_bboxes(elements_raw, bboxes_raw)
    return merged_elements, merged_bboxes, all_polylines, scale


def _merge_with_bboxes(
    elements: list,
    bboxes: list[tuple],
) -> tuple[list, list[tuple]]:
    """Merge duplicate elements, keeping representative bbox for each group."""
    merged_elems:  list       = []
    merged_bboxes: list[tuple] = []

    for elem, bbox in zip(elements, bboxes):
        best_match_idx = None
        for i, existing in enumerate(merged_elems):
            if (existing.element_type == elem.element_type and
                    abs(existing.length_mm - elem.length_mm) <= 5 and
                    abs(existing.width_mm  - elem.width_mm)  <= 5):
                best_match_idx = i
                break

        if best_match_idx is not None:
            merged_elems[best_match_idx].quantity += elem.quantity
            if (len(elem.label) < len(merged_elems[best_match_idx].label) or
                    (len(elem.label) == len(merged_elems[best_match_idx].label) and
                     elem.label < merged_elems[best_match_idx].label)):
                merged_elems[best_match_idx].label = elem.label
        else:
            merged_elems.append(elem)
            merged_bboxes.append(bbox)

    return merged_elems, merged_bboxes


def parse_dwg(dwg_path: str,
              casting_height_mm: float = 3000,
              unit_override: str = None,
              temp_dir: str = None) -> tuple[list[StructuralElement], str | None]:
    """
    Parse a DWG file: convert to DXF then extract elements.

    Returns:
        (elements_list, error_message_or_None)
    """
    dxf_path = dwg_to_dxf(dwg_path, temp_dir)
    if not dxf_path:
        return [], (
            "Could not convert DWG to DXF.\n\n"
            "Please install LibreDWG:\n"
            "  /opt/homebrew/bin/brew install libredwg\n\n"
            "Or install ODA File Converter from:\n"
            "  https://www.opendesign.com/guestfiles/oda_file_converter\n\n"
            "Alternatively, manually export DXF from AutoCAD (File → Save As → DXF)."
        )

    try:
        elements = parse_dxf(dxf_path, casting_height_mm, unit_override)
        return elements, None
    except Exception as ex:
        return [], f"DXF parsing error: {ex}"


# ──────────────────────────────────────────
# Auto Panel Height Detection
# ──────────────────────────────────────────

_STANDARD_HEIGHTS_FOR_DETECT = [1235, 2470, 3000, 3200, 3300, 3705, 4200, 5850]

_HEIGHT_ANNO_RE = re.compile(
    r'\bH(?:EIGHT|T)?[-=:\s]*(\d{3,4})\s*(?:MM)?\b', re.IGNORECASE)
_PANEL_HT_RE = re.compile(
    r'\bPANEL\b.*?(\d{3,4})', re.IGNORECASE)


def detect_panel_height(dxf_path: str) -> int | None:
    """
    Scan TEXT/MTEXT entities in a DXF file for panel-height annotations.
    Matches: 'HEIGHT=2470MM', 'HT-3000', 'PANEL HT 2470', 'H=2470', etc.
    Returns the most-common matching standard height, or None if not found.
    Fast — only reads text entities, not geometry.
    """
    if not EZDXF_OK:
        return None
    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
    except Exception:
        return None

    candidates: list[int] = []
    for ent in msp:
        try:
            if ent.dxftype() == 'TEXT':
                text = ent.dxf.text
            elif ent.dxftype() == 'MTEXT':
                try:
                    text = ent.plain_text()
                except Exception:
                    text = ent.text
            else:
                continue
            text_up = text.upper()
            for m in _HEIGHT_ANNO_RE.finditer(text_up):
                h = int(m.group(1))
                if h in _STANDARD_HEIGHTS_FOR_DETECT:
                    candidates.append(h)
            for m in _PANEL_HT_RE.finditer(text_up):
                h = int(m.group(1))
                if h in _STANDARD_HEIGHTS_FOR_DETECT:
                    candidates.append(h)
        except Exception:
            continue

    if not candidates:
        return None
    return max(set(candidates), key=candidates.count)


def parse_dwg_full(
    dwg_path: str,
    casting_height_mm: float = 3000,
    unit_override: str = None,
    temp_dir: str = None,
) -> tuple[list, list[tuple], list[list], float, str | None, str]:
    """
    Parse a DWG file and return rich data for the drawing viewer.

    Converts DWG→DXF internally, then delegates to parse_dxf_full().

    Returns:
        elements        — list of StructuralElement
        bboxes_raw      — list of (x_min, y_min, x_max, y_max) per element
        all_polylines   — list of [(x,y),...] for ALL geometry (background render)
        scale           — mm per DXF unit
        error           — error string or None on success
        dxf_render_path — path to the converted DXF (for full AutoCAD renderer)
    """
    dxf_path = dwg_to_dxf(dwg_path, temp_dir)
    if not dxf_path:
        return [], [], [], 1.0, (
            "Could not convert DWG to DXF.\n\n"
            "Please install LibreDWG:\n"
            "  /opt/homebrew/bin/brew install libredwg\n\n"
            "Or install ODA File Converter from:\n"
            "  https://www.opendesign.com/guestfiles/oda_file_converter\n\n"
            "Alternatively, export DXF from AutoCAD (File → Save As → DXF)."
        ), ""

    try:
        elements, bboxes, polylines, scale = parse_dxf_full(
            dxf_path, casting_height_mm, unit_override
        )
        return elements, bboxes, polylines, scale, None, dxf_path
    except Exception as ex:
        return [], [], [], 1.0, f"DXF parsing error after DWG conversion: {ex}", ""


# ─────────────────────────────────────────────────────────────────────────────
# Nova Drawing v2 Parser  — reads panels DIRECTLY from labeled drawing
# Naming convention:
#   Regular col   : COL:-LxD  or  COL:- L X D
#   Floor prefix  : FF-COL, GF-COL, GF-Col, SF-COL …
#   Round col     : R-COL, R-Col  (elevation view; panels labeled as WxH)
#   L-shaped col  : L-COL, L-Col  (plan view; panels around L outline)
# ─────────────────────────────────────────────────────────────────────────────

# Matches: (optional-floor)(COL | RCOL | LCOL): dims WxD
def is_nova_drawing(dxf_path: str) -> bool:
    """
    Quick check — does this DXF use Nova's labelled-panel format?
    Scans only TEXT/MTEXT entities (fast). Returns True if at least one
    label like 'COL:-', 'FF-COL', 'GF-COL', 'R-COL', 'L-COL:-(...)+(...)'
    is found.
    """
    if not EZDXF_OK:
        return False
    _QUICK_RE = re.compile(
        r'(?:FF|GF|SF|B1|B2|TF|RF)?[-\s]*(?:R[-\s]*)?(?:L[-\s]*)?COL'
        r'(?:[:\-\s]+(?:Ø|%%[Cc])?\d|[:\-\s]*\()',  # digits or ( for L-COL paren
        re.IGNORECASE,
    )
    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
        for e in msp.query("TEXT"):
            try:
                t = _normalize_dxf_codes(e.dxf.text)
                if _QUICK_RE.search(t):
                    return True
            except Exception:
                pass
        for e in msp.query("MTEXT"):
            try:
                try:
                    txt = e.plain_text()
                except Exception:
                    txt = e.text
                txt = _normalize_dxf_codes(txt)
                if _QUICK_RE.search(txt):
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


_NOVA_LABEL_RE = re.compile(
    r'(?:(FF|GF|SF|B1|B2|TF|RF)[-\s]*)?'      # optional floor prefix
    r'(R[-\s]*COL|L[-\s]*COL|COL)'             # element type
    r'[:\-\s]+'                                 # separator (colon, dash, space)
    r'[Ø\s]*'                                   # optional Ø (R-COL diameter symbol)
    r'(\d+)\s*[xX]\s*(\d+)',                    # WxD dimensions
    re.IGNORECASE,
)

# L-shaped column format: L-COL:-(400X3000)+(400X1500)
_L_COL_RE = re.compile(
    r'(?:(FF|GF|SF|B1|B2|TF|RF)[-\s]*)?'      # optional floor prefix
    r'L[-\s]*COL[:\-\s]*'                       # L-COL + separator
    r'\((\d+)\s*[xX]\s*(\d+)\)'               # (W1xH1)  first leg
    r'\s*\+\s*'                                # +
    r'\((\d+)\s*[xX]\s*(\d+)\)',              # (W2xH2)  second leg
    re.IGNORECASE,
)

_NOVA_WxH_RE = re.compile(r'^(\d+)[xX](\d+)$')  # e.g. "300X2470"


def _normalize_dxf_codes(t: str) -> str:
    """Replace AutoCAD control codes with readable characters."""
    t = re.sub(r'%%[Cc]', 'Ø', t)  # diameter symbol
    t = re.sub(r'%%[Dd]', '°', t)  # degree
    t = re.sub(r'%%[Pp]', '±', t)  # plus-minus
    return t


def _collect_texts(msp) -> list[tuple[float, float, str]]:
    """Return list of (x, y, text_string) for all TEXT/MTEXT in modelspace."""
    out = []
    for e in msp.query("TEXT"):
        try:
            txt = _normalize_dxf_codes(e.dxf.text).strip()
            out.append((e.dxf.insert.x, e.dxf.insert.y, txt))
        except Exception:
            pass
    for e in msp.query("MTEXT"):
        try:
            try:
                txt = e.plain_text().strip()
            except Exception:
                try:
                    txt = e.text.strip()
                except Exception:
                    continue
            txt = _normalize_dxf_codes(txt)
            out.append((e.dxf.insert.x, e.dxf.insert.y, txt))
        except Exception:
            pass
    return out


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

    Returns:
        elements : list[StructuralElement]  (element.height_mm = casting_height_mm)
        boqs     : list[ElementBOQ]         (panel size_labels use product_height_mm)
        error    : error string or None
    """
    if not EZDXF_OK:
        return [], [], "ezdxf not installed — run: pip install ezdxf"

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
