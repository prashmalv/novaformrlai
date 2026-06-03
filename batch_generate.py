"""
Batch BOQ generator — processes all sample DXF drawings and produces
a BOQ PDF + Excel file for each, saved under data/team_verification/.

Usage:
    source venv/bin/activate
    python batch_generate.py
"""
import os, sys
from pathlib import Path
from datetime import date

# ── drawing configs ──────────────────────────────────────────────────────────
BASE = Path("assets/NewBrandingAssets/OneDrive_1_14-05-2026")

DRAWINGS = [
    {
        "id": 1,
        "dxf": BASE / "Drawing 1" / "Drawing 1.dxf",
        "panel_height_mm":   3200,   # Panel physical size
        "casting_height_mm": 3200,   # Actual wall/column casting height → used for accessories
        "project_name": "Drawing 1 — Column & Wall Formwork",
        "client_name":  "Nova Formworks Pvt. Ltd.",
        "note": "Large residential complex — columns + walls",
    },
    {
        "id": 2,
        "dxf": BASE / "Drawing 2" / "Drawing 2.dxf",
        "panel_height_mm":   2470,   # Client uses 2470mm panels (Quotation 2 REV-01)
        "casting_height_mm": 3200,   # Standard floor height — drives accessory quantities
        "project_name": "Drawing 2 — Column Formwork (Panel=2470mm, Cast=3200mm)",
        "client_name":  "Nova Formworks Pvt. Ltd.",
        "note": "Panel=2470mm per Quotation 2; casting height=3200mm for accessories",
    },
    {
        "id": 3,
        "dxf": BASE / "Drawing 3" / "Drawing 3.dxf",
        "panel_height_mm":   3200,
        "casting_height_mm": 3200,
        "project_name": "Drawing 3 — Column & Wall Formwork",
        "client_name":  "Nova Formworks Pvt. Ltd.",
        "note": "3 element types detected (R0, C1, SW1)",
    },
    {
        "id": 4,
        "dxf": BASE / "Drawing 4" / "Drawing 4.dxf",
        "panel_height_mm":   3200,
        "casting_height_mm": 3200,
        "project_name": "Drawing 4 — Shear Wall & Column Formwork",
        "client_name":  "Nova Formworks Pvt. Ltd.",
        "note": "Large mixed structure — shear walls + columns",
    },
    {
        "id": 5,
        "dxf": BASE / "Drawing 5" / "Drawing 5.dxf",
        "panel_height_mm":   3000,   # Quotation 5 uses 3000mm panels
        "casting_height_mm": 3200,   # Standard casting height
        "project_name": "Drawing 5 — Column Formwork (Beam elements excluded)",
        "client_name":  "Nova Formworks Pvt. Ltd.",
        "note": "Columns only (Beam Bottom + Beam Side pending implementation)",
    },
]

# ─────────────────────────────────────────────────────────────────────────────

from src.parsers.dwg_parser import parse_dxf
from src.engine.panel_optimizer import compute_boq
from src.engine.accessories_calc import calculate_accessories, aggregate_accessories
from src.output.boq_generator import aggregate_project_boq
from src.output.pdf_generator import generate_boq_pdf
from src.output.excel_generator import generate_excel_boq
from src.models.element import ProjectBOQ

OUT_ROOT = Path("data/team_verification")


def process_drawing(cfg: dict) -> None:
    did  = cfg["id"]
    dxf  = cfg["dxf"]
    ph   = cfg["panel_height_mm"]
    cast = cfg.get("casting_height_mm", 3200)   # element height for accessories
    out_d = OUT_ROOT / f"Drawing_{did}"
    out_d.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Drawing {did} — {cfg['note']}")
    print(f"  DXF: {dxf}")
    print(f"  Panel height: {ph}mm  |  Casting height: {cast}mm")

    # 1. Parse — casting_height sets element.height_mm (drives accessory quantities)
    print("  Parsing DXF...", end=" ", flush=True)
    try:
        elements = parse_dxf(str(dxf), casting_height_mm=cast)
    except Exception as ex:
        print(f"FAILED: {ex}")
        return
    print(f"{len(elements)} element type(s) detected")

    if not elements:
        print("  No elements — skipping output generation.")
        return

    # Print element summary
    for e in elements:
        floor_str = f" floor={e.floor_label}" if e.floor_label else ""
        print(f"    {e.label:8s} | {e.element_type.value:12s} | "
              f"{e.length_mm:.0f}x{e.width_mm:.0f}mm | qty={e.quantity}{floor_str}")

    # 2. BOQ + Accessories
    print("  Computing BOQ...", end=" ", flush=True)
    boqs, acc_boqs = [], []
    for elem in elements:
        try:
            boq = compute_boq(elem, ph)
            boqs.append(boq)
            acc_boqs.append(calculate_accessories(elem, boq, ph))
        except Exception as ex:
            print(f"\n  WARNING: BOQ failed for {elem.label}: {ex}")

    acc_agg = aggregate_accessories(acc_boqs, num_sets=1)

    project = ProjectBOQ(
        project_name    = cfg["project_name"],
        client_name     = cfg["client_name"],
        client_address  = "",
        date            = date.today().strftime("%d-%m-%Y"),
        element_boqs    = boqs,
        panel_height_mm = ph,
        num_sets        = 1,
        gst_enabled     = True,
        freight_amount  = 0.0,
        panel_rate_per_sqm = 0.0,
    )
    agg = aggregate_project_boq(project)
    print(f"OK — total area {agg['total_area_sqm']:.2f} sqm")

    # 3. BOQ PDF
    boq_pdf  = str(out_d / f"Drawing_{did}_BOQ.pdf")
    qtn_pdf  = str(out_d / f"Drawing_{did}_Quotation.pdf")
    boq_xlsx = str(out_d / f"Drawing_{did}_BOQ.xlsx")

    print("  Generating BOQ PDF...", end=" ", flush=True)
    try:
        generate_boq_pdf(project, boq_pdf,
                         acc_agg=acc_agg,
                         boq_number=f"BOQ-2026-D{did:02d}")
        print(f"saved → {boq_pdf}")
    except Exception as ex:
        print(f"FAILED: {ex}")

    # 4. Quotation PDF (no pricing — rates TBD by team)
    print("  Generating Quotation PDF...", end=" ", flush=True)
    try:
        from src.output.pdf_generator import generate_quotation_pdf
        generate_quotation_pdf(project, qtn_pdf,
                               acc_agg=acc_agg,
                               qtn_number=f"QTN-2026-D{did:02d}",
                               price_per_sqm=0.0,
                               freight=0.0,
                               gst_rate=0.18,
                               valid_days=7)
        print(f"saved → {qtn_pdf}")
    except Exception as ex:
        print(f"FAILED: {ex}")

    # 5. Excel
    print("  Generating Excel BOQ...", end=" ", flush=True)
    try:
        generate_excel_boq(
            project, boq_xlsx,
            price_per_sqm=0.0,
            freight_amount=0.0,
            gst_rate=0.18,
            acc_agg=acc_agg,
            boq_number=f"BOQ-2026-D{did:02d}",
            qtn_number=f"QTN-2026-D{did:02d}",
        )
        print(f"saved → {boq_xlsx}")
    except Exception as ex:
        print(f"FAILED: {ex}")

    # 6. Write element summary CSV for easy team review
    csv_path = out_d / f"Drawing_{did}_Elements.csv"
    with open(csv_path, "w") as f:
        f.write("Label,Type,Length_mm,Width_mm,Height_mm,Qty,Floor\n")
        for e in elements:
            f.write(f"{e.label},{e.element_type.value},{e.length_mm:.0f},"
                    f"{e.width_mm:.0f},{e.height_mm:.0f},{e.quantity},{e.floor_label}\n")
    print(f"  Element CSV → {csv_path}")


def main():
    print(f"NovoForm — Batch BOQ Generator")
    print(f"Output root: {OUT_ROOT.resolve()}")
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    for cfg in DRAWINGS:
        process_drawing(cfg)

    print(f"\n{'='*60}")
    print("Batch complete. Files saved under:")
    print(f"  {OUT_ROOT.resolve()}/")
    for cfg in DRAWINGS:
        d = OUT_ROOT / f"Drawing_{cfg['id']}"
        files = list(d.glob("*")) if d.exists() else []
        print(f"  Drawing {cfg['id']}: {len(files)} file(s)")


if __name__ == "__main__":
    main()
