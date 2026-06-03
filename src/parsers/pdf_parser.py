"""
PDF drawing parser.
- render_pdf_page : renders page to PNG for visual preview
- extract_elements_ai : uses Claude Vision to auto-detect structural elements
"""
import base64
import json
import os
import re
from pathlib import Path

import fitz  # pymupdf

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "api_config.json"


# ── API key management ────────────────────────────────────────────────────────

def get_api_key() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    if _CONFIG_PATH.exists():
        try:
            data = json.loads(_CONFIG_PATH.read_text())
            return data.get("anthropic_api_key", "").strip() or None
        except Exception:
            pass
    return None


def save_api_key(key: str) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if _CONFIG_PATH.exists():
        try:
            existing = json.loads(_CONFIG_PATH.read_text())
        except Exception:
            pass
    existing["anthropic_api_key"] = key.strip()
    _CONFIG_PATH.write_text(json.dumps(existing, indent=2))


# ── PDF rendering ─────────────────────────────────────────────────────────────

def render_pdf_page(pdf_path: str, page_num: int = 0, dpi: int = 150) -> tuple[bytes, int, int]:
    """Render a PDF page to PNG bytes. Returns (png_bytes, width, height)."""
    doc = fitz.open(pdf_path)
    page_num = min(page_num, len(doc) - 1)
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png"), pix.width, pix.height


def get_page_count(pdf_path: str) -> int:
    return len(fitz.open(pdf_path))


def extract_title_block(pdf_path: str) -> dict:
    """Extract whatever text is available from vector layers (title block, notes)."""
    doc = fitz.open(pdf_path)
    page = doc[0]
    text = page.get_text("text")
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    result = {"project_name": "", "drawing_title": "", "drawing_no": "", "client": ""}
    for i, line in enumerate(lines):
        lu = line.upper()
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if "PROJECT:" in lu:
            result["project_name"] = nxt
        elif "DRAWING TITLE:" in lu:
            result["drawing_title"] = nxt
        elif "DRAWING NO:" in lu:
            result["drawing_no"] = nxt
        elif "CLIENT:" in lu:
            result["client"] = nxt
    return result


# ── Offline CV extraction (cv2 + easyocr) ────────────────────────────────────

_LABEL_RE  = re.compile(r'^(SW|SH|WW|CC|[CWRB])\d{1,3}[a-zA-Z]?$', re.I)
_DIM_RE    = re.compile(r'(\d{2,4})\s*[xX×]\s*(\d{2,4})')
_SINGLE_RE = re.compile(r'^(\d{3,5})$')

_easyocr_reader = None   # cached so model loads only once per session


def _get_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr
        _easyocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    return _easyocr_reader


def _bbox_center(bbox):
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return sum(xs) / 4, sum(ys) / 4


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def extract_elements_cv(pdf_path: str, page_num: int = 0) -> list[dict]:
    """
    Extract structural elements using OpenCV + EasyOCR — no API key required.
    First run downloads ~150 MB OCR models (once only, then works offline).
    """
    import cv2
    import numpy as np

    # 1. Render page at 200 DPI for good OCR resolution
    png_bytes, _, _ = render_pdf_page(pdf_path, page_num, dpi=200)
    nparr = np.frombuffer(png_bytes, np.uint8)
    img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Invert if dark background (AutoCAD dark theme export)
    if np.mean(gray) < 128:
        gray = cv2.bitwise_not(gray)

    # 3. Adaptive threshold + light denoise for cleaner OCR
    gray = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 15, 8)
    gray = cv2.medianBlur(gray, 3)

    # 4. OCR
    reader  = _get_reader()
    results = reader.readtext(gray, detail=1, paragraph=False,
                              min_size=10, text_threshold=0.5)

    # 5. Build text list with centres, skip low-confidence
    texts = []
    for bbox, text, conf in results:
        t = text.strip()
        if conf < 0.3 or not t:
            continue
        cx, cy = _bbox_center(bbox)
        texts.append({'t': t, 'cx': cx, 'cy': cy})

    # 6. Identify element labels
    labels = [x for x in texts if _LABEL_RE.match(x['t'])]

    # 7. For each label find nearest dimension text (within 400 px at 200 DPI)
    MAX_PX   = 400
    seen     = set()
    elements = []

    for lbl in labels:
        key = lbl['t'].upper()
        if key in seen:
            continue
        seen.add(key)

        cx, cy = lbl['cx'], lbl['cy']
        best_dim, best_d = None, MAX_PX

        for t in texts:
            m = _DIM_RE.search(t['t'])
            if m:
                d = _dist((cx, cy), (t['cx'], t['cy']))
                if d < best_d:
                    best_d   = d
                    best_dim = (int(m.group(1)), int(m.group(2)))

        # Fallback: single integer nearby (e.g. wall thickness "300")
        if best_dim is None:
            for t in texts:
                ms = _SINGLE_RE.match(t['t'])
                if ms:
                    val = int(ms.group(1))
                    if 100 <= val <= 15000:
                        d = _dist((cx, cy), (t['cx'], t['cy']))
                        if d < best_d:
                            best_d   = d
                            best_dim = (val, val)

        if best_dim is None:
            continue

        l = max(best_dim)
        w = min(best_dim)

        ku = key
        if ku.startswith('SW') or ku.startswith('SH'):
            etype = 'Shear Wall'
        elif ku.startswith(('W', 'WW')):
            etype = 'Wall'
        else:
            etype = 'Column'

        elements.append({
            'label':     lbl['t'],
            'type':      etype,
            'length_mm': l,
            'width_mm':  w,
            'quantity':  1,
        })

    return elements


# ── AI extraction ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a structural engineering drawing analyst. "
    "You extract every structural element from construction drawings. "
    "Always respond with valid JSON only — no markdown, no explanation, no extra text."
)

_USER_PROMPT = (
    "This is a structural/civil engineering drawing. "
    "Extract EVERY structural element visible — be exhaustive, do not skip any.\n\n"
    "Step 1 — Look for schedule tables:\n"
    "  - SCHEDULE OF COLUMNS: read each row (column mark + size e.g. C1: 300x300)\n"
    "  - SCHEDULE OF WALLS or WALL SCHEDULE: read wall mark + thickness + length\n\n"
    "Step 2 — Scan the ENTIRE plan view:\n"
    "  - Find every label: C1, C2, W1, W2, W3, W4, W5, SW1, SW2, WW1, R0 etc.\n"
    "  - For each label find the nearest dimension annotation\n"
    "  - Dimension strings: LENGTHxTHICKNESS or THICKNESSxLENGTH or single number\n"
    "  - Count how many times each label appears in the plan (= quantity)\n\n"
    "Step 3 — Rules:\n"
    "  - Wall thickness usually 200-400 mm; wall length usually 1000-15000 mm\n"
    "  - Column sizes usually 200x200 to 1200x600 mm\n"
    "  - Ignore: openings (OP1/OP2), pipes, puddle pipes, slabs, footings, beams\n"
    "  - Each unique label = one entry; do NOT merge different labels\n"
    "  - length_mm = LONGER dimension; width_mm = SHORTER dimension\n\n"
    "Return ONLY a valid JSON array:\n"
    '[\n'
    '  {"label":"C1","type":"Column","length_mm":300,"width_mm":300,"quantity":4},\n'
    '  {"label":"W1","type":"Wall","length_mm":11000,"width_mm":300,"quantity":2},\n'
    '  {"label":"W2","type":"Wall","length_mm":7150,"width_mm":300,"quantity":1}\n'
    ']\n\n'
    "Valid types: Column, Wall, Shear Wall\n"
    "If truly nothing structural is visible return: []"
)


def extract_elements_ai(pdf_path: str, page_num: int = 0,
                        api_key: str = None) -> list[dict]:
    """
    Use Claude Vision to extract structural elements from a PDF drawing page.
    Returns list of dicts: label, type, length_mm, width_mm, quantity.
    Raises ValueError if API key missing or API call fails.
    """
    key = api_key or get_api_key()
    if not key:
        raise ValueError("ANTHROPIC_API_KEY not set. Enter it when prompted.")

    # 150 DPI gives Claude enough resolution to read dimensions clearly
    png_bytes, _, _ = render_pdf_page(pdf_path, page_num, dpi=150)
    img_b64 = base64.standard_b64encode(png_bytes).decode("utf-8")

    import anthropic
    client = anthropic.Anthropic(api_key=key)

    response = client.messages.create(
        model="claude-sonnet-4-6",   # sonnet for better accuracy on dense drawings
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_b64,
                    },
                },
                {"type": "text", "text": _USER_PROMPT},
            ],
        }],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    raw = raw.strip()

    data = json.loads(raw)
    if not isinstance(data, list):
        return []

    result = []
    for item in data:
        try:
            l = int(item.get("length_mm") or 0)
            w = int(item.get("width_mm")  or 0)
            if l == 0 and w == 0:
                continue
            result.append({
                "label":     str(item.get("label", "?")).strip(),
                "type":      str(item.get("type",  "Column")).strip(),
                "length_mm": max(l, w),
                "width_mm":  min(l, w) if min(l, w) > 0 else max(l, w),
                "quantity":  max(1, int(item.get("quantity", 1))),
            })
        except (ValueError, TypeError):
            continue
    return result
