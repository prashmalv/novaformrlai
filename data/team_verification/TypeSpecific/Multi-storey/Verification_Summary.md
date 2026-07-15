# Multi-storey Drawings — Verification Summary
**Date:** June 2026 | **Prepared by:** RLAI (rightleft.ai)

---

## Drawing-1 (`DWG-1.dxf`) — CANNOT GENERATE

**Status:** ❌ 0 elements detected — wrong DXF type provided

**Root cause:** The DXF is a **formwork panel layout drawing** (shows which panels are
placed where, with individual panel widths like 400, 600, 600 labelled on each panel).
Our system needs a **structural plan DXF** (column/shear-wall cross-sections with labels
C1, SW1... and dimensions). A formwork layout drawing is the *output*, not the *input*.

**What to ask client:**
> "DWG-1.dxf appears to be the formwork panel arrangement drawing, not the structural
> column plan. Please share the structural plan DXF showing column/shear-wall
> cross-sections labelled C1, SW1... with dimensions."

**No output files generated for Drawing-1.**

---

## Drawing-2 (`DWG-2.dxf`) — GENERATED (with known differences)

**Status:** ⚠️ 39 elements detected and BOQ generated — but two catalog mismatches

### Output files (in this folder)
| File | Notes |
|---|---|
| `Drawing2_BOQ.pdf` | BOQ report — 3200mm panels, standard widths |
| `Drawing2_Quotation.pdf` | Quotation at ₹5,950/sqm |
| `Drawing2_BOQ.xlsx` | Excel: 3 sheets |
| `Drawing2_Elements.csv` | All 39 detected elements |

### Panel-level comparison vs client quotation

| Metric | Our System | Client Quotation |
|---|---|---|
| Panel height | **3200mm** (standard catalog) | **5850mm** (custom / multi-storey) |
| Total area | **4,767 sqm** | **1,140 sqm** |
| Area ratio | +318% more than client | — |
| Panel widths matched | **0 out of 48** panel sizes | — |

**Every single panel shows "ONLY OURS" or "ONLY CLIENT"** — no overlap at all.
This is because the height suffix differs (3200 vs 5850) so `600X3200 ≠ 600X5850`.

### Breakdown of differences

**Issue 1 — Panel height 5850mm not in catalog**
Our catalog: `[3200, 3000, 2470, 1228]mm`
Client uses: `5850mm` throughout.
5850mm ≈ 2 × 2925mm — likely a **two-floor combined panel height** (floor height ~2.92m × 2).
If 5850mm is added to the panel catalog, every panel size column would shift from
`{w}X3200` → `{w}X5850`, and the area per panel would be 5850/3200 = 1.83× larger.

**Issue 2 — Non-standard panel widths in client quotation**
Client uses: `215, 220, 225, 260, 265, 275, 280, 310, 325, 340, 345, 360, 365, 385, 390mm`
Our catalog: `[600,500,490,440,400,350,340,300,275,250,240,230,200,150,125,100,40]mm`
Only **275mm and 340mm** overlap. All others are project-specific sizes.

**Issue 3 — Possible scope difference**
Our parser detected 39 element types from the full DXF (all floors combined, qty totals
across floors). The client quotation (1,140 sqm, dated 01/06/2026) may cover **one floor
only**. If the building has ~4 floors: 1140 sqm × (3200/5850) correction × 4 floors ≈
2,490 sqm — closer to our 4,767 sqm but still higher, suggesting quantity differences too.

### Questions for client

1. **Is 5850mm a Nova standard panel height for multi-storey projects?**
   If yes → we add it to `panel_config.json` and regenerate.

2. **Are the non-standard widths (215, 220, 225, 265, 280...mm) in Nova's catalog?**
   If yes → we add them to `panel_config.json`.

3. **Does the quotation cover one floor or all floors?**
   Confirm so we can match the scope correctly.

---

## What Needs to Happen Next

| Action | Owner |
|---|---|
| Confirm 5850mm panel height (standard or custom?) | Nova team |
| Share list of all Nova panel widths for multi-storey | Nova team |
| Share structural plan DXF for Drawing-1 (not the panel layout) | Nova / Client |
| Add confirmed panel sizes to `panel_config.json` and regenerate | RLAI |

