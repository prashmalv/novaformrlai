import re


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
