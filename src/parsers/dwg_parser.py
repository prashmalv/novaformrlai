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
from src.dwg_parse.build_dimension_lookup import _build_dimension_lookup
from src.dwg_parse.detect_scale import _detect_scale
from src.dwg_parse.extract_text_entities import _extract_text_entities
from src.dwg_parse.get_polyline_bbox import _get_polyline_bbox


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
    doc=None,
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

    if doc is None:
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


