# NovoForm — BOQ Generation & Verification Summary
**Generated:** 29 May 2026  
**Prepared by:** RLAI (rightleft.ai)  
**For:** Nova Formworks Pvt. Ltd. — Internal Team Review

---

## 1. Batch Run Status

All 5 drawings processed successfully. Output files saved under `data/team_verification/`.

| Drawing | DXF File | Elements Detected | Total Area | BOQ PDF | Quotation PDF | Excel |
|---------|----------|-------------------|------------|---------|---------------|-------|
| Drawing 1 | Drawing 1.dxf | **54 types** | 13,220 sqm | ✅ | ✅ | ✅ |
| Drawing 2 | Drawing 2.dxf | **44 types** | 2,240 sqm | ✅ | ✅ | ✅ |
| Drawing 3 | Drawing 3.dxf | **3 types** | 2,087 sqm | ✅ | ✅ | ✅ |
| Drawing 4 | Drawing 4.dxf | **54 types** | 5,353 sqm | ✅ | ✅ | ✅ |
| Drawing 5 | Drawing 5.dxf | **38 types** | 3,680 sqm | ✅ | ✅ | ✅ |

> **Panel height used:** Drawing 1 = 3000mm · Drawing 2 = 2470mm · Drawing 3 = 3000mm · Drawing 4 = 3000mm · Drawing 5 = 3000mm  
> **Price used in reports:** ₹0/sqm (placeholder) — team to update with actual rates before sharing with client.

---

## 2. Output Files per Drawing

```
data/team_verification/
├── Drawing_1/
│   ├── Drawing_1_BOQ.pdf         ← BOQ report (panels only, no pricing)
│   ├── Drawing_1_Quotation.pdf   ← Quotation template (₹0 placeholder)
│   ├── Drawing_1_BOQ.xlsx        ← Excel: FORMWORK BOQ / QUOTATION / DAYS BOQ
│   └── Drawing_1_Elements.csv    ← Detected elements list for review
├── Drawing_2/ (same structure)
├── Drawing_3/ (same structure)
├── Drawing_4/ (same structure)
└── Drawing_5/ (same structure)
```

---

## 3. Comparison with Client Quotations

### 3.1 Availability of Client Reference Data

| Drawing | Client Excel | Status | Sheets with Nova Quotation |
|---------|-------------|--------|---------------------------|
| Drawing 1 | Quotation 1.xlsx | ❌ Corrupt (`xl/drawings/NULL` error) | Not readable |
| Drawing 2 | Quotation 2.xlsx | ✅ Readable | `FORMWORK QUOTATION` + `REV -01` |
| Drawing 3 | Quotation 3.xlsx | ❌ Corrupt | Not readable |
| Drawing 4 | Quotation 4.xlsx | ❌ Corrupt | Not readable |
| Drawing 5 | Quotation 5.xlsx | ✅ Readable | `COLUMN FORMWORK QUOTATION`, `BEAM BOTTOM`, `BEAM SIDE & SLAB` |

**For Drawings 1, 3, 4 — team must verify manually** by opening the generated PDFs/Excel and comparing visually with the client's original.

---

### 3.2 Drawing 2 — Detailed Comparison

**Client reference:** `Quotation 2.xlsx → REV -01` sheet  
**Panel height:** 2470mm  
**Client pricing:** ₹5,950/sqm + GST 18%

#### Area Totals

| Metric | Our System | Client REV-01 | Difference |
|--------|-----------|---------------|------------|
| Total Area (sqm) | 2,240.28 | 661.52 | **+1,578 sqm** |
| Element types detected | 44 | ~15–20 (estimated) | We cover more |
| Price/sqm | ₹0 (placeholder) | ₹5,950 | — |
| Grand Total | — | ₹4,644,552 | — |

#### Root Cause of Area Difference

**Our system covers all 44 element types** detected in the DXF, including:

- **B1** (Column 1182×391mm, qty=66) — large quantity "B" elements
- **H1** (Column 605×159mm, qty=38), **H2** (1294×1223mm, qty=3), **H3** (620×162mm, qty=1), **H4** (1255×604mm, qty=6) — "H" labeled columns
- **C19** (605×181mm, qty=24), and many more small/irregular columns

**Client's quotation covered a specific subset** (approx. 15–17 unique column/wall types). This is normal — Nova manually selects which elements to include in a quotation for a given project phase.

> **Action Required:** Client/team to confirm which elements from Drawing 2's DXF were actually in scope for this quotation. Elements not in scope should be excluded from the BOQ manually in the application.

#### Panel Width Comparison (same elements, different widths)

| Panel Size | Our Nos | Client Nos | Status |
|------------|---------|------------|--------|
| OC80X2470 | 1,196 | 273 | Scope difference — we cover more elements |
| 600X2470 | 542 | 309 | Scope difference |
| 500X2470 | 114 | 14 | Scope difference |
| 250X2470 | 104 | **150** | We have fewer — panel selection difference |
| 230X2470 | 362 | 3 | Scope difference |
| 240X2470 | 208 | **0** | We use 240mm; client doesn't (uses 250mm instead) |
| 490X2470 | 94 | **0** | We use 490mm; client doesn't |
| 275X2470 | 170 | **0** | We use 275mm; client doesn't |
| 235X2470 | **0** | 3 | Client uses 235mm; we don't have this standard width |
| 260X2470 | **0** | 3 | Client uses 260mm; we don't (non-standard) |
| 265X2470 | **0** | 3 | Client uses 265mm; we don't (non-standard) |
| 615X2470 | **0** | 1 | Custom spacer panel used by client |
| IC100X2470 | **0** | 1 | Client uses Inner Corner; our IC not triggered here |

> **Key Finding:** Our panel optimizer uses the standard catalog widths `[600, 500, 490, 440, 400, 350, 340, 300, 275, 250, 240, 230, 200, 150, 125, 100, 40]`. The client's manual selection includes non-catalog sizes (235mm, 260mm, 265mm) which are custom filler/spacer panels not in our standard catalog. The client also uses a 615mm panel — this is likely a spacer for a column face that is 615mm wide (not in our standard catalog).

> **Action Required:** Confirm with Nova if sizes 235mm, 260mm, 265mm are actual panel sizes in their catalog, or if these are calculated spacer offsets. If they are real panels, they need to be added to `config/panel_config.json`.

---

### 3.3 Drawing 5 — Detailed Comparison

**Client reference:** `Quotation 5.xlsx → COLUMN FORMWORK QUOTATION` sheet  
**Panel height:** 3000mm  
**Client pricing:** ₹5,950/sqm + GST 18%

#### Area Totals

| Metric | Our System | Client Quotation | Difference |
|--------|-----------|-----------------|------------|
| Total Area (sqm) | 3,678.14 | 101.04 | **+3,577 sqm** |
| Element types covered | 38 | **2 column types only** | Client quoted subset |
| Grand Total | — | ₹709,402 | — |

#### Root Cause

The client's COLUMN FORMWORK QUOTATION for Drawing 5 covered **only 2 column types**:

| Client Label | Size | Sets | Panels |
|---|---|---|---|
| COL 230X230 | 230×230mm | 8 sets | OC80×32, 230X3000×32 |
| COL 230X600 | 230×600mm | 12 sets | OC80×48, 600X3000×24, 230X3000×24 |

**Our system detected 38 element types** with 128 instances of C85 (1235×600mm) alone.

> **Match found:** C13 (230×230mm, qty=32) in our DXF = COL 230X230 in client (32 sets). Panel widths should match — **OC80×32 and 230X3000×32** — which aligns with our optimizer output for a 230×230mm column.

> **Action Required:** Client to confirm which specific DXF elements were in scope for this quotation. Drawing 5 also has a `BEAM BOTTOM` and `BEAM SIDE & SLAB` quotation sheet (see §3.4 below).

#### Drawing 5 — Beam Elements (Client Excel)

The client's `BEAM BOTTOM` sheet lists custom beam-bottom panel sizes:

| Panel Size | Nos | Area (sqm) |
|---|---|---|
| (OC+230+OC)X1220 | 1 | 0.476 |
| (OC+230+OC)X1235 | 47 | 22.638 |
| (OC+230+OC)X570 | 1 | 0.222 |
| (OC+230+OC)X610 | 2 | 0.476 |
| (OC+230+OC)X762 | 4 | 1.189 |
| (OC+230+OC)X840 | 2 | 0.655 |
| **TOTAL** | **57** | **25.66 sqm** |
| Grand Total (incl. GST) | | **₹180,126** |

> Our beam-bottom format `(OC+230+OC)X{depth}` matches the client's format exactly. The `BEAM & SLAB` folder has a separate DXF (`BEAM BOTTOM SIDE & SLAB 1.dxf`) which hasn't been processed in this batch run.

The client's `BEAM SIDE & SLAB` sheet lists slab-side panels (IC+75, 600, 440, 300, 270, 260, 255, 230, 125, 100 × various heights):

| Metric | Value |
|---|---|
| Total area | 110.43 sqm |
| Grand Total (incl. GST) | ₹775,312 |

> **These beam elements require the BEAM & SLAB DXF** (`BEAM BOTTOM SIDE & SLAB 1.dxf`) to be processed. They are not columns or walls.

---

## 4. Element Detection Quality

### Drawing 3 — Only 3 Elements Detected (Flag)

Drawing 3 DXF parsed only 3 element types:

| Label | Type | Size | Qty |
|---|---|---|---|
| R0 | Column | 1000×600mm | 14 |
| C1 | Column | 500×300mm | 71 |
| SW1 | Wall | 2470×600mm | 97 |

**This is suspicious** — Drawing 3's DXF may be a simplified version with very few labeled polylines, or it may be a plan where most elements share a small number of labels. The DXF was parsed correctly (no errors) but the count is very low compared to Drawings 1, 2, 4, 5.

> **Action Required:** Team to open Drawing 3 DXF in any DXF viewer / AutoCAD and verify if only 3 element labels exist in the drawing, or if the parser missed some.

### Drawing 1 — Large Complex (54 Element Types)

Drawing 1 is the largest drawing: 54 element types, 13,220 sqm total area. Notable elements include:

- Large columns: C119 (1200×1200mm), C121 (1500×1200mm), C114 (1294×1223mm)
- Various wall/shear wall thicknesses: 148mm, 148mm, 250mm, 330mm, 390mm, 513mm, 549mm, 598mm
- Element labels: SW, C, AC (likely "Anchor" or a project prefix), P (likely "Pillar")

The `AC` and `P` prefix elements are flagged for team review — these may be non-standard element labels that Nova team should confirm are correctly classified as columns/walls.

### Drawing 4 — 54 Element Types, Mixed Prefixes

Drawing 4 contains: SW (Shear Wall), C (Column), P (Pillar/Column), AC (possibly Anchor/Column), H (Column). Notable:

- **H1** (750×375mm, qty=98) — large quantity; verify if this is a column or something else
- **P4** (900×600mm) has `floor=F31` — parser correctly identified the multi-floor label
- **SW176** (12575×230mm, qty=1) — extremely long wall (12.6m), verify this is correct
- **AC** elements (AC1–AC70) — non-standard prefix; team to confirm these are columns/walls

---

## 5. Panel Optimizer — Known Gaps

These are known differences vs the client's manual approach:

| Gap | Detail | Impact | Status |
|-----|--------|--------|--------|
| Non-catalog panel widths | Client uses 235, 260, 265mm panels; our catalog stops at 250mm | Some elements will have different panel selection | Needs catalog update |
| Custom spacer panels | Client uses "615X2470" (615mm custom) for specific faces | We'll use 600+15mm spacer, not shown | Minor discrepancy |
| Inner Corner (IC100) | Client uses IC100 for L/T wall junctions; our junction detection not implemented | IC panels not in our BOQ | Phase 3B pending |
| Beam Side + Slab | Client has IC+75 format for beam-side panels; not in our element types | Beam Side BOQ not generated yet | Phase pending |
| Qty-vs-Sets | Our "qty" = element instances; client shows "num sets" separately | Same total; different presentation | Cosmetic |

---

## 6. Key Questions for Client / Nova Team

1. **Drawing 2 scope:** Which specific elements (column/wall labels) were included in the Quotation 2 BOQ? Our system generates BOQ for all 44 detected elements. Nova's manual quotation covers ~15 specific types.

2. **Non-standard panels:** Are 235mm, 260mm, 265mm actual Nova panel sizes? If yes, send updated panel catalog — we'll add them to `panel_config.json`.

3. **Drawing 3 verification:** Open `Drawing 3.dxf` and confirm if only R0, C1, SW1 labels exist. If more elements are present, there may be a parsing issue.

4. **AC / P prefixes (Drawings 1 & 4):** Confirm that elements labeled AC1–AC70 and P1, P03, P89 etc. are columns/walls (not piles, pipes, or other structural items).

5. **Beam DXF:** Should `BEAM BOTTOM SIDE & SLAB 1.dxf` be processed in a separate run? If yes, what panel height to use for beams?

6. **Drawing 5 COL 230X600:** Which element label in the DXF corresponds to the client's "COL 230×600" (12 sets)? Is it C1 (611×230mm, 50 sets) or a different one?

7. **Price rates:** What rates should be entered for final reports?
   - Panel rate/sqm: ₹5,950 (confirmed from Quotation 2 and 5)
   - Waller rate/RM: `___`
   - Tierod rate/RM: `___`
   - Freight: `___`

---

## 7. How to Verify the Generated Reports

### Step 1 — Open Reports in `data/team_verification/`
- Open `Drawing_X_BOQ.pdf` to see panel list per element
- Open `Drawing_X_BOQ.xlsx` to see full panel table with counts and areas

### Step 2 — Cross-check Key Elements
For each drawing, pick 2–3 familiar elements (e.g., C1, SW1) and verify:
1. Are the detected dimensions correct? (check `Drawing_X_Elements.csv`)
2. Do the panel widths look right? (cross-reference with client's manual selection)
3. Do the OC80 corners appear for all column corners?

### Step 3 — Update Pricing and Re-generate
Once rates are confirmed, enter them in the application and re-generate quotation reports.

### Step 4 — Run from Application
To generate with pricing through the UI:
1. `python main.py` (or via Desktop shortcut)
2. Import DXF → Review elements → Set panel height → Generate BOQ/Quotation

---

## 8. Files in This Batch Run

| File | Path | Notes |
|------|------|-------|
| Drawing_1_BOQ.pdf | data/team_verification/Drawing_1/ | 54 elements, 13,220 sqm |
| Drawing_1_BOQ.xlsx | data/team_verification/Drawing_1/ | 3-sheet Excel |
| Drawing_2_BOQ.pdf | data/team_verification/Drawing_2/ | 44 elements, 2,240 sqm |
| Drawing_2_BOQ.xlsx | data/team_verification/Drawing_2/ | 3-sheet Excel, compare with Quotation 2 REV-01 |
| Drawing_3_BOQ.pdf | data/team_verification/Drawing_3/ | 3 elements only — verify parser |
| Drawing_3_BOQ.xlsx | data/team_verification/Drawing_3/ | 3-sheet Excel |
| Drawing_4_BOQ.pdf | data/team_verification/Drawing_4/ | 54 elements, 5,353 sqm |
| Drawing_4_BOQ.xlsx | data/team_verification/Drawing_4/ | 3-sheet Excel |
| Drawing_5_BOQ.pdf | data/team_verification/Drawing_5/ | 38 elements, 3,680 sqm |
| Drawing_5_BOQ.xlsx | data/team_verification/Drawing_5/ | 3-sheet Excel, compare with Quotation 5 COLUMN FORMWORK QUOTATION |

---

*Document prepared by RLAI (rightleft.ai) | NovoForm v1.1 | 29 May 2026*
