from src.dwg_parse.clean_text import _clean_mtext_full
from src.dwg_parse.cluster_rows import _cluster_rows
from src.dwg_parse.parse_dim_value import _parse_dim_value
from src.dwg_parse.expand_label import _expand_label
import re
try:
    import ezdxf
    EZDXF_OK = True
except ImportError:
    EZDXF_OK = False


_SCHED_COL_TOL = 1800  # mm — X tolerance for table-column matching

def parse_nova_schedule_table(doc) -> dict:
    """
    Parse COLUMN SCHEDULE and SHEAR WALL SCHEDULE tables from a Nova DXF.

    Returns: {LABEL_UPPER: (length_mm, width_mm) | 'AS_PER_PLAN'}
    Only Foundation-floor dimensions are extracted.
    Elements absent from the foundation column ("-----") are omitted.
    """
    if not EZDXF_OK or doc is None:
        return {}
    try:
        msp = doc.modelspace()
    except Exception:
        return {}

    # ── Collect all text entities ──────────────────────────────────────────
    raw_texts: list = []
    for ent in msp:
        try:
            if ent.dxftype() == 'TEXT':
                raw, pos = ent.dxf.text, ent.dxf.insert
            elif ent.dxftype() == 'MTEXT':
                try:
                    raw = ent.plain_text()
                except Exception:
                    raw = ent.text
                pos = ent.dxf.insert
            else:
                continue
            cleaned = _clean_mtext_full(raw)
            if cleaned:
                raw_texts.append((pos.x, pos.y, cleaned))
        except Exception:
            continue

    if not raw_texts:
        return {}

    result: dict = {}

    # ── Process each schedule section ─────────────────────────────────────
    for section_kw in ('COLUMN SCHEDULE', 'SHEAR WALL SCHEDULE'):
        hdr_matches = [(x, y, t) for x, y, t in raw_texts
                       if section_kw in t.upper()]
        if not hdr_matches:
            continue
        # Topmost occurrence (highest Y)
        sec_x, sec_y, _ = max(hdr_matches, key=lambda r: r[1])

        # Texts belonging to this section: within 15000mm to the right,
        # and up to 20000mm below the section header.
        sec_texts = [(x, y, t) for x, y, t in raw_texts
                     if sec_x - 500 <= x <= sec_x + 15000
                     and sec_y - 20000 <= y < sec_y]

        if not sec_texts:
            continue

        # ── Find FDN column X from header rows ────────────────────────────
        hdr_zone = [(x, y, t) for x, y, t in sec_texts if y >= sec_y - 2200]
        fdn_x = None
        for x, y, t in hdr_zone:
            tu = t.upper()
            if 'FDN' in tu or 'FOUNDATION' in tu:
                fdn_x = x
                break
        if fdn_x is None:
            continue

        # ── Data rows: below header zone ──────────────────────────────────
        data_texts = [(x, y, t) for x, y, t in sec_texts if y < sec_y - 1500]
        if not data_texts:
            continue

        label_x = min(x for x, y, t in data_texts)
        row_centroids = _cluster_rows([y for x, y, t in data_texts])

        for cy in row_centroids:
            row = [(x, t) for x, y, t in data_texts if abs(y - cy) < 290]
            if not row:
                continue

            # Label: text nearest to label_x
            lbl_cands = [(x, t) for x, t in row if abs(x - label_x) < _SCHED_COL_TOL]
            if not lbl_cands:
                continue
            label_raw = min(lbl_cands, key=lambda r: abs(r[0] - label_x))[1]
            label_raw = label_raw.replace('%%U', '').strip()

            # FDN value: text nearest to fdn_x
            fdn_cands = [(x, t) for x, t in row if abs(x - fdn_x) < _SCHED_COL_TOL]
            if not fdn_cands:
                continue
            fdn_raw = min(fdn_cands, key=lambda r: abs(r[0] - fdn_x))[1]

            value = _parse_dim_value(fdn_raw)
            if value is None:
                continue  # "-----" → element doesn't exist at foundation

            for lbl in _expand_label(label_raw):
                lbl_up = lbl.upper().strip()
                # if lbl_up and re.match(r'^[A-Z]+\d', lbl_up):    # regex updated
                if lbl_up and re.match(r'^(?!H-?\d)[A-Z]+-?\d', lbl_up):
                    result[lbl_up] = value

    return result
