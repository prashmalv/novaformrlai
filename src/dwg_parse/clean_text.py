import re

_MTEXT_STRIP_RE = re.compile(
    r'Fromans\|c\d+;'           # AutoCAD colour tag (CLIENT-1.dxf style)
    r'|\\[A-Za-z][^;]*;'        # standard MTEXT format codes: \f...; \H...; etc.
    r'|[{}\\]'                  # braces and backslashes
)

def _clean_mtext_full(txt: str) -> str:
    """Strip all AutoCAD MTEXT formatting codes and Fromans colour tags."""
    txt = _MTEXT_STRIP_RE.sub('', txt)
    txt = txt.replace('|', ' ')
    return txt.strip()
