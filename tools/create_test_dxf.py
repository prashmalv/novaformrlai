"""
Generate a realistic test DXF file mimicking CLIENT-1 drawing layout.
This is used to validate our DXF parser without needing AutoCAD.

Run: python3 tools/create_test_dxf.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import ezdxf
from ezdxf.enums import TextEntityAlignment


def add_column(msp, cx: float, cy: float, W: float, H: float, label: str, layer: str = "COLUMN"):
    """Add a rectangular column as closed LWPOLYLINE + text label."""
    pts = [
        (cx - W/2, cy - H/2),
        (cx + W/2, cy - H/2),
        (cx + W/2, cy + H/2),
        (cx - W/2, cy + H/2),
    ]
    pl = msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
    # Add label in center
    msp.add_text(label, dxfattribs={
        "insert": (cx, cy),
        "height": min(W, H) * 0.3,
        "layer": "ANNO",
    })


def add_wall(msp, x1: float, y1: float, length: float, thickness: float,
             label: str, layer: str = "SHEAR_WALL"):
    """Add a rectangular wall as closed LWPOLYLINE + text label."""
    pts = [
        (x1, y1),
        (x1 + length, y1),
        (x1 + length, y1 + thickness),
        (x1, y1 + thickness),
    ]
    msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
    msp.add_text(label, dxfattribs={
        "insert": (x1 + length/2, y1 + thickness/2),
        "height": thickness * 0.5,
        "layer": "ANNO",
    })


def create_test_dxf(output_path: str):
    doc = ezdxf.new("R2018")
    doc.layers.add("COLUMN", color=1)      # red
    doc.layers.add("SHEAR_WALL", color=5)  # blue
    doc.layers.add("ANNO", color=3)        # green

    msp = doc.modelspace()

    # ─── Columns (from CLIENT-1 COLUMN quotation) ───
    # Grid spacing: 5000mm apart
    cols = [
        # label, L,    W,    cx,     cy
        ("C1",   900,  600,  1000,   1000),
        ("C2",   960,  600,  7000,   1000),
        ("C3",   1150, 600,  13000,  1000),
        ("C4",   600,  1000, 19000,  1000),
        ("C5",   600,  1000, 25000,  1000),
        ("C7",   450,  450,  31000,  1000),
        ("C8",   450,  450,  37000,  1000),
        ("C9",   750,  450,  43000,  1000),
        ("C12",  900,  600,  1000,   7000),
        ("C13",  900,  600,  7000,   7000),
    ]

    for label, L, W, cx, cy in cols:
        add_column(msp, cx, cy, L, W, label)

    # ─── Shear Walls (from CLIENT-1 COLUMN quotation) ───
    walls = [
        # label, x1,    y1,    length, thickness
        ("SW1",  1000,  15000, 2400,   300),
        ("SW2",  7000,  15000, 3600,   300),
        ("SW3",  13000, 15000, 1800,   300),
        ("SW4",  19000, 15000, 2500,   300),
        ("SW5",  25000, 15000, 4500,   300),
        ("SW6",  31000, 15000, 5600,   300),
        ("SW7",  37000, 15000, 3800,   300),
        ("SW10", 1000,  22000, 9600,   300),
        ("SW11", 13000, 22000, 12000,  300),
    ]

    for label, x1, y1, length, thickness in walls:
        add_wall(msp, x1, y1, length, thickness, label)

    # ─── Add dimension annotations (TEXT entities near geometry) ───
    # These simulate the dimension text a drafter would add
    for label, L, W, cx, cy in cols[:5]:
        msp.add_text(f"{L}x{W}", dxfattribs={
            "insert": (cx, cy - W/2 - 300),
            "height": 150,
            "layer": "ANNO",
        })

    doc.saveas(output_path)
    print(f"Test DXF saved: {output_path}")
    return output_path


if __name__ == "__main__":
    out = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "tests", "test_client1.dxf"
    )
    os.makedirs(os.path.dirname(out), exist_ok=True)
    create_test_dxf(out)
    print("\nTesting parser on generated DXF...")

    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from src.parsers.dwg_parser import parse_dxf

    elements = parse_dxf(out, casting_height_mm=3200)
    print(f"\nDetected {len(elements)} elements:")
    for e in elements:
        print(f"  {e.label:6s} {e.element_type.value:12s}  "
              f"{e.length_mm:6.0f} x {e.width_mm:6.0f} mm  qty={e.quantity}")
