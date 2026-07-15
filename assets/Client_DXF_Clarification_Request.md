# Client Data Clarification Request — NovoForm DXF Parsing
**To:** Nova Formworks Pvt. Ltd.  
**From:** RLAI (rightleft.ai)  
**Subject:** DXF Drawing Clarifications Required — 4 Drawing Types  
**Date:** June 2026

---

Dear Team,

We are currently integrating and testing the NovoForm BOQ automation system with the sample drawings you shared. The system successfully processes the **Monolithic drawing** (65 elements detected, BOQ generated — shared separately for your review).

However, for the following 4 drawing types, our system is unable to correctly read the DXF files. We have identified the specific reasons for each and are requesting your help to provide the correct data so we can proceed.

---

## 1. COLUMN Drawing (`COLUMN1.dxf`)

**What we see:** Our system detects 3 elements — all classified as walls:
- SW1: 3705 × 600 mm
- SW2: 3705 × 405 mm  
- SW4: 3705 × 250 mm

**What we expect:** The reference quotation shows 6 column types:
- 300×1200 mm (2 sets), 300×1000 mm (20 sets), 250×1500 mm (3 sets)
- 250×1000 mm (18 sets), 250×1200 mm (3 sets), 1125×1125 mm (2 sets)

**Root cause:** The DXF appears to show the **formwork face/elevation view** (unrolled column faces shown as strips), not the **structural column plan/section view**. Our parser needs the cross-section plan view of columns to identify them correctly.

**Request:**
> Could you please share a DXF that shows the **column layout plan** (top view / cross-section of columns with their dimensions labeled, e.g. C1 = 300×1200mm)?  
> The format we need: column label (C1, C2...) + rectangular cross-section drawn as a closed polyline with dimension annotation nearby.

---

## 2. WALL Drawing (`WALL DRAWING.dxf`)

**What we see:** 0 elements detected — the system finds no recognizable structural elements in this DXF.

**What we expect:** The quotation shows wall types at 3705mm height with various lengths (using 600mm, 500mm, 200mm... panels).

**Root cause:** The wall elements in this DXF either:
- Use non-standard entity types (not closed polylines)
- Are not labeled with standard identifiers (W1, W2, SW1...)
- OR the wall thickness dimensions fall outside our detection range

**Additional note:** The quotation also references **M.S. (Mild Steel) Haunch panels** (310mm, 460mm sizes). These are currently not in our standard Nova plastic panel catalog. Please clarify if these are to be included in the software's output.

**Request:**
> Could you please share a DXF that shows the **wall plan layout** with:
> 1. Each wall drawn as a closed polyline (rectangle showing wall length × thickness)
> 2. Each wall labeled with an identifier (W1, W2, SW1...)
> 3. Dimension annotation near each label showing length × thickness in mm
>
> Also confirm: should M.S. Haunch panels (310mm, 460mm) be part of the automated BOQ, or are they always added manually?

---

## 3. BOX CULVERT Drawing (`BOX CUVERT.dxf`)

**What we see:** 0 elements detected.

**Root cause:** Box culverts in AutoCAD are typically drawn as complex structural assemblies with many sub-components (haunch details, section cuts, reinforcement bars). Our parser looks for simple closed polylines representing the outer structural boundary, but this DXF doesn't contain one in a recognizable format.

**Request:**
> Could you please share either:
> **Option A:** A DXF with the box culvert drawn as a simple closed rectangle representing the **outer cross-section** of the culvert (length × width), labeled as `BC1` or similar, with inner dimensions annotated nearby.  
>
> **Option B:** Directly provide the key dimensions for the culvert:
> - Outer length (mm)
> - Outer width (mm)  
> - Wall thickness (mm)
> - Casting height / panel height to use (mm)
>
> The BOQ Input.csv you provided (2000×2000mm, height 2000mm) confirms we have the right dimensions — we just need the DXF in a parseable format.

---

## 4. BEAM & SLAB Drawing (`BEAM BOTTOM SIDE & SLAB 1.dxf`)

**What we see:** 40 elements detected, but all classified as Column/Wall. Our system cannot identify which are beam bottoms vs beam sides vs slab panels.

**What we expect:** The quotation has 3 separate sections:
- **Beam Bottom:** `(OC80 + 600/300/1500 + OC80) × depth` format
- **Beam Side:** Various panel heights per beam side
- **Slab Formwork:** IC100 panels (corner panels for slab soffit)

**Root cause:** Beam elements need specific labels so our system can distinguish them:
- `BB1`, `BB2`... for Beam Bottom elements
- `BS1`, `BS2`... for Beam Side elements
- The DXF currently uses generic column/wall labels (C1, SW1...) for all elements

**Request:**
> For beam drawings, could you please ensure:
> 1. Beam Bottom elements are labeled **BB1, BB2...** (or any consistent prefix for beam bottoms)
> 2. Beam Side elements are labeled **BS1, BS2...** (or any consistent prefix for beam sides)
> 3. Each label has the beam **width × depth dimensions** annotated nearby
>
> Alternatively, if the current DXF format cannot be changed, please share the **beam schedule table** (similar to column schedule) showing each beam mark with its width and depth in mm. We can then build a beam schedule parser.

---

## Summary Table

| Drawing Type | Issue | What We Need |
|---|---|---|
| Column | DXF is formwork elevation view, not plan | Plan view DXF with column cross-sections labeled C1, C2... |
| Wall | 0 elements — labels/entities not recognized | Plan view DXF with walls labeled W1, W2... as closed polylines |
| Box Culvert | Complex assembly — not a simple polyline | Simple outer cross-section DXF OR confirm 2000×2000×2000mm dimensions |
| Beam & Slab | Elements not identified as beams | Use BB1/BB2 labels for beam bottom, BS1/BS2 for beam side in DXF |

---

## What Is Working Correctly

✅ **Drawing 1–5** (all 5 project drawings) — parsed and BOQ generated successfully  
✅ **Monolithic drawing** — 65 elements detected, BOQ + Quotation generated (attached)

Please let us know if you need a call to discuss the DXF format requirements. Once we receive the corrected drawings, we can quickly validate and finalize the BOQ generation for all element types.

---

*Prepared by RLAI (rightleft.ai) | NovoForm v1.1 | June 2026*

---

## 5. Panel Catalog Confirmation (New — June 2026)

While processing all sample drawings shared, we identified panel sizes in your quotations that are **not in our current catalog**. We have already added the ones that appear in multiple project quotations:

**Already added to our catalog:**
- **Widths (16 new):** 215, 220, 225, 260, 265, 270, 280, 290, 310, 325, 345, 360, 365, 385, 390, 520 mm
- **Heights (2 new):** 3300mm, 3705mm

**Please confirm the following 4 sizes before we add them:**

| Size | Seen In | Question |
|---|---|---|
| **5850mm height** | Multi-storey Drawing 2 | Is this a standard Nova panel height for multi-storey projects, or two standard panels stacked? |
| **4200mm height** | Drawing 4 (retaining wall) | Is 4200mm a standard Nova panel height? |
| **235mm width** | Drawing 2 (single quotation) | Is 235mm a standard Nova panel width? |
| **288mm width** | Drawing 4 (single quotation) | Is 288mm a standard Nova panel width? |

**Sizes we did NOT add** (these are project-specific custom items, not standard panels):
- 5mm, 10mm, 15mm, 20mm → Shim plates / spacer adjusters
- HUNCH panels (bridge-specific), M.S. panels (steel, different product line)
- Beam side / slab soffit variable heights (230mm–2300mm range, cut-to-size per project)

*— RLAI (rightleft.ai) | NovoForm v1.1 | June 2026*
