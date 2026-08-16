from src.dwg_parse.normalize_dxf_code import _normalize_dxf_codes
import re



try:
    import ezdxf
    EZDXF_OK = True
except ImportError:
    EZDXF_OK = False

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

