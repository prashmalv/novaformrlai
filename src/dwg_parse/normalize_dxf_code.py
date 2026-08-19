import re


def _normalize_dxf_codes(t: str) -> str:
    """Replace AutoCAD control codes with readable characters."""
    t = re.sub(r'%%[Cc]', 'Ø', t)  # diameter symbol
    t = re.sub(r'%%[Dd]', '°', t)  # degree
    t = re.sub(r'%%[Pp]', '±', t)  # plus-minus
    return t