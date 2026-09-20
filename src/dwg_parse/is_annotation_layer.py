"""
Tell annotation layers apart from structural ones.

AutoCAD layer names follow the AIA convention, where the second field states
what the layer holds: A-COLS is columns, A-WALL is walls, and anything under
A-ANNO is annotation — dimension strings, leaders, and the little bubbles
that carry element identifiers.

Annotation shapes are not formwork.  "Misty Land Developers Private
Limited.dxf" draws 47 label bubbles of 262x195mm on
C0_COL_GROUND$0$A-ANNO-IDEN, one per column, and they were being detected as
structural elements: one leaked into the BOQ as a 262x195 "column", and once
the drawing's label placeholders are filled in, every label would bind to the
bubble sitting around it rather than to the column it names.

Xrefs prefix the layer with the reference name ("C0_COL_GROUND$0$A-ANNO-IDEN"),
so the test is a substring match rather than a prefix match.
"""

_ANNOTATION_MARKERS = ('ANNO', 'DIMS', 'TEXT', 'HATCH')


def is_annotation_layer(layer_name: str) -> bool:
    """True if `layer_name` holds annotation rather than structural geometry."""
    if not layer_name:
        return False
    upper = str(layer_name).upper()
    return any(marker in upper for marker in _ANNOTATION_MARKERS)
