# NovoForm — Visit Verification Checklist
**Prepared for:** Prashant Malviya (RLAI)  
**For visit to:** Nova Formworks Pvt. Ltd. (Yukti Arora's team)  
**Version:** v1.2 | June 2026

---

## Part A — What TO VERIFY Live with Yukti's Team

### A1. Panel Height Selection — Core Verification
**Goal:** Show that the software uses the correct panel heights from the drawing.

**Demo steps:**
1. Open the app → Project Info tab → fill project name
2. Import Drawing 5 (D5) DXF → new Import Settings dialog will appear
3. Show the panel height auto-detected (or manually select `3000mm`)
4. Run BOQ → go to BOQ Results tab
5. Open D5's client quotation (Quotation 5.xlsx → COLUMN FORMWORK QUOTATION)
6. Compare: our BOQ says `Outer Corner 80*3000`, client says `OC80X3000` ✓

**What matches:**
| Our Output | Client Quotation |
|-----------|-----------------|
| `Outer Corner 80*3000` | `OC80X3000` |
| `Panel 230*3000` | `230X3000` |
| C13 (230×230): OC80×4 + 230×4 per set | Exact match ✓ |

---

### A2. Runtime Height Change — New Feature Demo
**Goal:** Show that changing panel height re-generates BOQ instantly, no re-upload needed.

**Demo steps:**
1. Import any DXF (e.g. D5)
2. Run BOQ with `3000mm` → note the panel codes in BOQ Results tab
3. Go to Configuration tab → change Panel Height to `2470mm`
4. Watch BOQ Results table update automatically (no button click needed)
5. Change back to `3000mm` → watch it revert

**Key message for team:** "Agar site pe 2 alag heights ke panels use ho rahe hain to ek hi drawing ke liye alag BOQ bana sakte hain bina file dubara upload kiye."

---

### A3. Import Confirmation Screen — New Feature Demo
**Goal:** Show the new screen that appears after parsing, before reviewing elements.

**Demo steps:**
1. Browse and import any DXF
2. After parsing completes → new "Import Settings" dialog shows
3. It shows: elements count, auto-detected height (if found), dropdown to override
4. User clicks "Proceed to Review Elements" → then reviews the element table

---

### A4. Verify One Element Panel Logic (Manual Cross-Check)
Pick D5, element C13 (230×230 column):

**Our output:**
- OC80×3000 = 4 (one at each corner)
- Panel 230×3000 = 4 (one per face)

**Client quotation (Quotation 5):**
- OC80X3000 = 32 total ÷ 8 sets = 4 per set ✓
- 230X3000 = 32 total ÷ 8 sets = 4 per set ✓

**Exact match — show this side-by-side.**

---

### A5. Aggregation Difference — Explain, Don't Match Numbers
**Pre-empt the "total doesn't match" concern:**

| Our Total Area | Client Quotation Total |
|---------------|----------------------|
| All elements × all sets = USAGE area | 1 supply kit (panels reused) |
| D2: ~2237 sqm | D2: ~661 sqm |
| Both are CORRECT — different purpose | |

**Script:** "Hamare app ka total area batata hai ki project mein kitni baar panels lagenge. Client quotation batata hai ki site pe kitne physical panels bhejne hain (kyunki same panels bar bar use hote hain). Dono numbers sahi hain — alag kaam ke liye hain."

---

### A6. Excel Export Cross-Check
1. Export BOQ Excel from app
2. Open → FORMWORK BOQ sheet
3. Check panel code column → should show `600*2470` format (not `600*3200`)
4. If Yukti's team has a specific drawing, import it and export immediately for live demo

---

## Part B — Dependencies on Nova Formworks Side

These items NEED Nova Formworks to confirm before we can finalize the app:

### B1. Panel Catalog Confirmation (CRITICAL)
We need Nova team to confirm which sizes are in their actual catalog.

**Pending confirmation:**

| Item | What We Have | Client Needs to Confirm |
|------|-------------|------------------------|
| Height: 5850mm | In pending list | ✓ Used for multi-storey? |
| Height: 4200mm | In pending list | ✓ Used for retaining walls? |
| Width: 235mm | In pending list | ✓ Standard or custom? |
| Width: 288mm | In pending list | ✓ Standard or custom? |
| Height: 1235mm | Now in catalog (was 1228) | ✓ Confirm correct height |

**Action:** Ask Yukti to share the complete Nova panel catalog sheet OR show us the physical panel list.

---

### B2. DXF File Format Requirement
**What we need from them:**

1. All future DXF drawings should be exported from AutoCAD as **DXF 2013 or 2018** format
2. Element labels (C1, SW1, W1) should be in TEXT entities close to the shapes
3. Avoid blocks/references for structural elements — use plain LWPOLYLINE
4. If they use DWG format, they need ODA File Converter installed on their machine

**Action:** Share our DXF Export Guide (AutoCAD → Save As → DXF R2013/R2018).

---

### B3. Multi-Height Drawings (e.g. D4)
D4 has both Shear Walls (2470mm panels) and Retaining Walls (4200mm panels) in same drawing.

**Current limitation:** App uses one panel height per import.  
**Workaround:** Import D4 twice — once with 2470mm for shear walls, once with 4200mm for retaining walls.

**Action:** Ask Nova team: "D4 jaise mixed drawings kitni baar aate hain? If frequent, we can build per-element height override."

---

### B4. Rate Card / Pricing
BOQ currently shows ₹0 for all rates (prices not entered).

**What Nova team needs to provide:**
- Panel rate per sqm (₹)
- Waller rate per rm (₹)
- Tierod rate per rm (₹)
- OC / IC unit prices

**Action:** Ask Yukti: "Pricing enter karna POC scope mein tha ya alag phase mein aayega?"

---

### B5. Accessories Quantities — Field Validation
Our accessories calculator gives ESTIMATED quantities.

**Nova team needs to verify:**
- Is `Waller spacing = 800mm` correct for their standard practice?
- Is `Tierod horizontal spacing = 600mm` correct?
- Tierod length formula = `wall_thickness + 300mm` (for cone + nut) — is 300mm correct?
- Waller rows = `ceil(height/500) + 1` — does this match their field practice?

**Action:** Show the Accessories section in BOQ output to any site engineer present. Get verbal confirmation or correction.

---

### B6. Client's Standard Configuration Template
Nova shared a `BOQ Input Sample.csv` with standard panel arrangements (e.g., 750×825 column → specific panel list). We've loaded this into our catalog.

**Action:** Ask Yukti: "Kya aur koi standard configurations hain jo frequently use hote hain? Hum unhe catalog mein add kar denge taki DP optimizer unhe prefer kare."

---

## Part C — Quick Live Test Script (15 minutes)

**Step 1 (2 min):** Import D5.dxf → confirm Import Settings screen shows → select 3000mm → proceed  
**Step 2 (3 min):** Review element table → confirm C13 (230×230) is present → confirm elements  
**Step 3 (2 min):** Run BOQ → go to BOQ Results → show OC80*3000 + 230*3000  
**Step 4 (2 min):** Open Quotation 5.xlsx → COLUMN FORMWORK QUOTATION → compare C13 row ✓  
**Step 5 (2 min):** Change Panel Height to 2470mm → watch BOQ update live → change back  
**Step 6 (2 min):** Export Excel → open → FORMWORK BOQ sheet → panel codes correct  
**Step 7 (2 min):** Discuss dependencies (catalog, pricing, mixed drawings)

---

## Part D — Questions to Ask Yukti's Team

1. "Panel catalog mein 5850mm aur 4200mm heights confirm kar sakte hain?"
2. "235mm aur 288mm widths standard hain ya special order?"
3. "1235mm height confirm hai — 1228mm nahi?"
4. "D4 jaise drawings jahan shear wall aur retaining wall dono hain — kitne projects mein aate hain?"
5. "Accessories quantities (waller, tierod) site engineer se verify ho sakta hai?"
6. "Pricing phase kab start karna hai — kya is demo mein rates enter karke dikhana chahiye?"
7. "Future drawings DXF format mein milenge ya DWG? ODA Converter install hai unke machine pe?"

---

## Summary: Who Does What Before Go-Live

| Item | Owner | Status |
|------|-------|--------|
| Panel heights 5850/4200 confirmation | Nova Formworks (Yukti) | Pending |
| Panel widths 235/288 confirmation | Nova Formworks (Yukti) | Pending |
| Rate card / pricing | Nova Formworks | Pending |
| Accessories field validation | Nova site engineer | Pending |
| DXF export guide for their team | RLAI (Prashant) | Ready to share |
| Per-element height override (D4 type) | RLAI | Optional — on request |
| Beam element support | RLAI | v1.3 / next phase |

---

*NovoForm v1.2 | RLAI (rightleft.ai) | June 2026*
