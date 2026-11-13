"""
Read Nova's own quotation Excel as ground truth and score a BOQ against it.

Quotation sheets ('COLUMN', 'FORMWORK QUOTATION', '~100%' ...) list one block
per size:  B = marks ('C1,C6') + size ('900X600'),  C = panel,  D = number of
panels,  E = number of sets,  F = height. Blocks are separated by blank rows.
NO OF PANELS is the total over all sets, so panels per set = D / E.
"""
import re
from dataclasses import dataclass, field

import openpyxl
import openpyxl.reader.excel

_LABEL_RE = re.compile(r'(?<![A-Z])([A-WYZ][A-Z]{0,2}-?\d{1,3}[A-Z]?)(?![0-9X])')
_SIZE_RE = re.compile(r'(\d{2,5})\s*[xX×]\s*(\d{2,5})')
_PANEL_RE = re.compile(r'^(OC|IC)?(\d{2,4})\s*[xX]\s*(\d{3,5})$')


@dataclass
class GTBlock:
    labels: list
    size: tuple            # (long, short) mm, or None
    sets: float
    height: str
    panels: dict = field(default_factory=dict)   # 'OC80' / '600' → qty per set
    row: int = 0


def _num(v):
    try:
        return float(str(v).strip().replace("MM", "").replace("mm", ""))
    except (TypeError, ValueError):
        return None


def _panel_key(name: str):
    """'OC80X3200' → 'OC80', '600X2470' → '600' (height ignored)."""
    m = _PANEL_RE.match(str(name).strip().upper().replace(" ", ""))
    return f"{m.group(1) or ''}{m.group(2)}" if m else None


def _find_sheet(wb, name: str = None):
    if name:
        return wb[name]
    hits = []
    for ws in wb.worksheets:
        # 'SITE SEND BOQ' sheets are an older template (OC180X614 panel system).
        if ws.title.strip().upper().startswith("SITE SEND"):
            continue
        for row in ws.iter_rows(min_row=1, max_row=20, max_col=4, values_only=True):
            cells = [str(c or "").strip().upper() for c in row]
            if len(cells) > 2 and cells[1] == "SIZE" and cells[2].startswith("PANELS REQUIRED"):
                hits.append(ws)
                break
    if not hits:
        raise ValueError("No quotation sheet (SIZE | PANELS REQUIRED header) found")
    # Prefer the full quotation over partial (~30 %) or site-send sheets.
    for ws in hits:
        t = ws.title.upper()
        if "100%" in t or "COLUMN" in t or "FORMWORK" in t:
            return ws
    return hits[0]


def load_quotation(path: str, sheet: str = None) -> tuple:
    """Return (sheet title, [GTBlock])."""
    # Some Nova files reference an image that is missing from the zip; skip images.
    openpyxl.reader.excel.find_images = lambda *a, **k: ([], [])
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = _find_sheet(wb, sheet)

    rows = list(ws.iter_rows(values_only=True))
    start = next(i for i, r in enumerate(rows)
                 if len(r) > 2 and str(r[1] or "").strip().upper() == "SIZE") + 1

    # A block ends at a blank row, or when a corner panel (OC/IC) follows a
    # flat panel -- some sheets have no blank row between two sizes.
    blocks, cur, seen_flat = [], [], False
    for i in range(start, len(rows)):
        r = list(rows[i]) + [None] * 6
        if str(r[1] or "").strip().upper().startswith("TOTAL"):
            break
        if all(v in (None, "") for v in r[1:6]):
            if cur:
                blocks.append(cur)
            cur, seen_flat = [], False
            continue
        key = _panel_key(r[2] or "") or ""
        if key[:2] in ("OC", "IC") and seen_flat:
            blocks.append(cur)
            cur, seen_flat = [], False
        elif key and key[:2] not in ("OC", "IC"):
            seen_flat = True
        cur.append((i + 1, r))
    if cur:
        blocks.append(cur)

    out = []
    for blk in blocks:
        if any("EXTRA" in str(r[1] or "").upper() for _, r in blk):
            continue        # add-on panels for other elements, not a full set
        labels, size, sets, height, panels = [], None, None, "", {}
        for _, r in blk:
            b = str(r[1] or "").upper()
            if b:
                s = _SIZE_RE.search(b)
                if s and size is None:
                    size = (max(int(s.group(1)), int(s.group(2))),
                            min(int(s.group(1)), int(s.group(2))))
                if not any(w in b for w in ("FLOOR", "HUNCH", "EXTRA", "PANEL")):
                    labels += [m for m in _LABEL_RE.findall(_SIZE_RE.sub(" ", b))]
            key = _panel_key(r[2] or "")
            qty = _num(r[3])
            if key and qty:
                panels[key] = panels.get(key, 0) + qty
            if sets is None and _num(r[4]):
                sets = _num(r[4])
            if not height and r[5] not in (None, ""):
                height = str(r[5])
        if not panels:
            continue
        sets = sets or 1
        out.append(GTBlock(labels=labels, size=size, sets=sets, height=height,
                           panels={k: v / sets for k, v in panels.items()}, row=blk[0][0]))
    return ws.title, out


# ── Scoring ───────────────────────────────────────────────────────────────────

def _norm(label: str) -> str:
    return re.sub(r'[\s\-_]+', '', (label or "").upper())


def boq_panel_dict(boq) -> dict:
    """ElementBOQ → {'OC80': 4, '600': 4, ...} for ONE element (height ignored)."""
    d = {}
    for p in boq.panels:
        if getattr(p, "is_filler", False):
            continue
        k = _panel_key(p.size_label)
        if k:
            d[k] = d.get(k, 0) + p.quantity
    return d


def score(gt_blocks: list, predicted: list, tol: float = 15.0) -> dict:
    """predicted: [(label, length, width, panel_dict)]. Returns metrics + rows."""
    pred = {}
    for label, length, width, panels in predicted:
        pred.setdefault(_norm(label), []).append((length, width, panels))

    rows, n_lab, n_found, n_size, n_pan = [], 0, 0, 0, 0
    for blk in gt_blocks:
        for lb in blk.labels:
            n_lab += 1
            cands = pred.get(_norm(lb), [])
            row = {"label": lb, "gt_size": blk.size, "gt_panels": blk.panels,
                   "found": bool(cands), "size_ok": False, "panels_ok": False,
                   "pred_size": None, "pred_panels": None}
            if cands:
                n_found += 1
                # Best candidate = right size if any.
                best = cands[0]
                if blk.size:
                    for c in cands:
                        if abs(c[0] - blk.size[0]) <= tol and abs(c[1] - blk.size[1]) <= tol:
                            best = c
                            break
                row["pred_size"] = (round(best[0]), round(best[1]))
                row["pred_panels"] = best[2]
                if blk.size and abs(best[0] - blk.size[0]) <= tol and abs(best[1] - blk.size[1]) <= tol:
                    row["size_ok"] = True
                    n_size += 1
                if {k: round(v, 2) for k, v in best[2].items()} == \
                        {k: round(v, 2) for k, v in blk.panels.items()}:
                    row["panels_ok"] = True
                    n_pan += 1
            rows.append(row)

    gt_labels = {_norm(lb) for b in gt_blocks for lb in b.labels}
    extra = sorted(k for k in pred if k and k not in gt_labels)
    pct = lambda a, n: round(100.0 * a / n, 1) if n else 0.0
    n_sized = sum(len(b.labels) for b in gt_blocks if b.size)
    return {
        "gt_labels": n_lab,
        "found_pct": pct(n_found, n_lab),
        # Only labels whose quotation states a size can be size-checked.
        "size_ok_pct": pct(n_size, n_sized),
        "panels_ok_pct": pct(n_pan, n_lab),
        "extra_labels": extra,
        "rows": rows,
    }
