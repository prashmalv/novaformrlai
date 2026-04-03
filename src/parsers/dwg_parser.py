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

from src.models.element import StructuralElement, ElementType


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


def _find_nearby_label(cx: float, cy: float, texts: list[dict],
                        radius: float = 2000) -> str | None:
    """Find nearest text label within radius of center point."""
    best, best_d = None, float('inf')
    for t in texts:
        d = math.sqrt((t['x'] - cx)**2 + (t['y'] - cy)**2)
        if d < radius and d < best_d:
            # Check if it looks like an element label (C1, SW1, W1 etc.)
            content = t['content'].strip()
            if re.match(r'^(C|SW|W|B|S|P)\d+[A-Z]?$', content, re.I):
                best, best_d = content.upper(), d
    return best


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

        length_mm = round(annotated_len if annotated_len else length_mm_raw)
        width_mm  = round(annotated_wid  if annotated_wid  else width_mm_raw)

        # Re-classify with refined dimensions
        elem_type = _classify_element(length_mm, width_mm, layer) or elem_type

        # --- Find nearby label ---
        label = _find_nearby_label(cx, cy, texts)
        if label is None:
            prefix = "C" if elem_type == ElementType.COLUMN else "SW"
            label = _next_label(prefix)

        if label in seen_labels:
            for e in elements:
                if e.label == label:
                    e.quantity += 1
                    break
            continue

        # Also check if an unlabeled auto-generated element with same type+dims exists
        # (same position in the drawing = genuinely repeated element without label)
        matched = False
        if not re.match(r'^(C|SW|W|B|S|P)\d+[A-Z]?$', label, re.I):
            # Auto-generated label — look for existing element with same dims
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
