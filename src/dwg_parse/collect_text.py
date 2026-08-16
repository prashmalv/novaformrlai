from src.dwg_parse.normalize_dxf_code import _normalize_dxf_codes



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
