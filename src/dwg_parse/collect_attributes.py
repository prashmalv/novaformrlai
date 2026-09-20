"""
Block-attribute label collection.

Some client drawings do not write element labels as TEXT/MTEXT at all — they
carry them as AutoCAD block attributes on a dedicated identification layer.
Every parser here used to query only TEXT, MTEXT and LWPOLYLINE, so those
labels were invisible and the drawing looked unlabelled.

Two entity types hold attribute text:

  ATTRIB  — a value filled in on an inserted block.  Real data; always read.
  ATTDEF  — the *definition*, whose text is the template's default value.
            Read only when it looks filled in (see below).

Unfilled placeholders
---------------------
A drawing can be set up for labelling without anyone having done the
labelling.  "Misty Land Developers Private Limited.dxf" carries 47 ATTDEFs on
layer C0_COL_GROUND$0$A-ANNO-IDEN and every single one still reads "C01", the
template default.  Treating those as labels would name 47 different columns
C01 and collapse them into one element.  So when every ATTDEF in the drawing
carries the identical value, they are taken to be unfilled and skipped; once
someone fills in real names the values differ and they are read normally.
"""


def _collect_attribute_texts(msp) -> list[tuple[float, float, str]]:
    """
    Return [(x, y, raw_text)] for block-attribute labels in modelspace.

    Text is returned raw — each caller applies its own cleaning, the same way
    it already does for TEXT/MTEXT.
    """
    attdefs: list[tuple[float, float, str]] = []
    attribs: list[tuple[float, float, str]] = []

    for ent in msp:
        try:
            dxftype = ent.dxftype()
            if dxftype == 'ATTDEF':
                txt = (ent.dxf.text or '').strip()
                if txt:
                    pos = ent.dxf.insert
                    attdefs.append((pos.x, pos.y, txt))
            elif dxftype == 'INSERT':
                for att in (ent.attribs or []):
                    try:
                        txt = (att.dxf.text or '').strip()
                        if txt:
                            pos = att.dxf.insert
                            attribs.append((pos.x, pos.y, txt))
                    except Exception:
                        continue
        except Exception:
            continue

    # All ATTDEFs identical → nobody filled the template in; ignore them.
    if len(attdefs) > 1 and len({t for _, _, t in attdefs}) == 1:
        attdefs = []

    return attribs + attdefs
