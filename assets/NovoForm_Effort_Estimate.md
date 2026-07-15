# NovoForm — Software Effort Estimate

**Project:** NovoForm Formwork Analysis & BOQ Automation
**Client:** Nova Formworks Pvt. Ltd.
**Prepared:** 2026-05-12
**Updated:** 2026-05-15
**Team:** 2 Resources
**Unit:** Person-Days (PD) | 1 PD = 8 hours

---

## Resource Roles

| Resource | Role | Responsibility |
|---|---|---|
| R1 | Lead Developer | Architecture, core engine, complex UI, integrations |
| R2 | Developer / QA | Feature development, testing, documentation, UAT support |

---

## Phase 1 — Core Desktop Application ✅ COMPLETE

| # | Module | R1 (PD) | R2 (PD) | Total | Status |
|---|---|---|---|---|---|
| 1.1 | Requirements & Analysis | 2 | 1 | 3 | Done |
| 1.2 | Project Setup (PyQt6, venv, config) | 1 | 0.5 | 1.5 | Done |
| 1.3 | Data Models (StructuralElement, ElementType) | 1 | 0 | 1 | Done |
| 1.4 | Panel Optimizer (DP algorithm) | 3 | 1 | 4 | Done |
| 1.5 | Accessories Calculator | 2 | 1 | 3 | Done |
| 1.6 | BOQ Generator (project aggregation) | 2 | 0.5 | 2.5 | Done |
| 1.7 | PDF Export (ReportLab) | 2 | 1 | 3 | Done |
| 1.8 | Excel Export (openpyxl, Nova format) | 2 | 1 | 3 | Done |
| 1.9 | DXF Parser (ezdxf, element detection) | 3 | 1 | 4 | Done |
| 1.10 | DWG Support (ODA converter bridge) | 2 | 0.5 | 2.5 | Done |
| 1.11 | PyQt6 Main Window (8 tabs) | 3 | 1 | 4 | Done |
| 1.12 | Drawing Preview (AutoCAD renderer) | 2 | 0.5 | 2.5 | Done |
| 1.13 | 3D Elements Overview (mplot3d) | 2 | 0.5 | 2.5 | Done |
| 1.14 | 3D Panel Assembly Dialog | 2 | 0.5 | 2.5 | Done |
| 1.15 | AI Assistant (offline NLP + SQLite) | 3 | 1 | 4 | Done |
| 1.16 | Edit Element Support + Pricing Panel | 1 | 0.5 | 1.5 | Done |
| 1.17 | Logo Integration + RLAI Footer | 0.5 | 0 | 0.5 | Done |
| 1.18 | Windows Installer (BAT + VBScript) | 1 | 0.5 | 1.5 | Done |
| **Phase 1 Total** | | **34.5** | **11.5** | **46** | ✅ Done |

---

## Phase 2 — Advanced Structure Types & BOQ Sheets ✅ COMPLETE

| # | Module | R1 (PD) | R2 (PD) | Total | Status |
|---|---|---|---|---|---|
| 2.1 | Box Culvert / Drain / Monolithic detection | 2 | 1 | 3 | Done |
| 2.2 | IC Panels (inner corner logic) | 2 | 0.5 | 2.5 | Done |
| 2.3 | Days BOQ Sheet (floor cycle logic) | 2 | 1 | 3 | Done |
| 2.4 | Shear Wall + IC-100 panel placement | 1.5 | 0.5 | 2 | Done |
| 2.5 | Unit testing — Phase 2 modules | 1 | 2 | 3 | Done |
| **Phase 2 Total** | | **8.5** | **5** | **13.5** | ✅ Done |

---

## Phase 3A — Web Application (Streamlit) ✅ COMPLETE

| # | Module | R1 (PD) | R2 (PD) | Total | Status |
|---|---|---|---|---|---|
| 3A.1 | Streamlit app layout & navigation | 2 | 0.5 | 2.5 | Done |
| 3A.2 | DXF upload + element detection flow | 2 | 0.5 | 2.5 | Done |
| 3A.3 | BOQ display + download (PDF/Excel) | 1.5 | 0.5 | 2 | Done |
| 3A.4 | Manual element entry in web | 1 | 0.5 | 1.5 | Done |
| 3A.5 | Deployment config (requirements, Procfile) | 0.5 | 0.5 | 1 | Done |
| **Phase 3A Total** | | **7** | **2.5** | **9.5** | ✅ Done |

---

## Phase 3C — Brand Refresh & Output Template Update ✅ COMPLETE

> **Trigger:** Client (Nova Formworks) provided updated brand guidelines, new NOVA logo, revised BOQ template, and revised Quotation template (2025). All output files and the UI have been updated to match exactly.

| # | Module | R1 (PD) | R2 (PD) | Total | Status |
|---|---|---|---|---|---|
| 3C.1 | Brand guidelines analysis (colors, fonts, logo assets) | 0.5 | 0.5 | 1 | Done |
| 3C.2 | PDF BOQ rewrite — Nova 2025 format (No of Set column, grouped by dimension, Accessories + Summary sections, purple gradient header) | 2 | 0.5 | 2.5 | Done |
| 3C.3 | PDF Quotation rewrite — per-SqM pricing, Accessories with mtr UOM, Valid Until, T&C block, Prepared By: Hiren Jadav | 1.5 | 0.5 | 2 | Done |
| 3C.4 | Excel rewrite — 3 sheets (FORMWORK BOQ, FORMWORK QUOTATION, DAYS BOQ), new column layout (No of Set, Total Qty, Unit Area, Total Area), Accessories section, purple theme | 2 | 0.5 | 2.5 | Done |
| 3C.5 | DXF parser upgrade — multi-floor label detection (CC1/F1 format), dimension-from-text fallback ("750x375" text), expanded label patterns (CC1, WW2 etc.) | 1 | 0.5 | 1.5 | Done |
| 3C.6 | Main window UI update — separate Export BOQ PDF + Export Quotation PDF buttons, BOQ Number & Quotation Number fields in Project Info tab | 0.5 | 0.5 | 1 | Done |
| **Phase 3C Total** | | **7.5** | **3** | **10.5** | ✅ Done |

---

## Phase 3B — Advanced Junction Types 🔶 PENDING

> **Dependency:** Client must provide sample DXF files with L-Wall, T-Wall, and C/U-Wall elements before this phase can begin.

| # | Module | R1 (PD) | R2 (PD) | Total | Status |
|---|---|---|---|---|---|
| 3B.1 | Requirements + sample DXF collection from client | 0.5 | 1 | 1.5 | Not Started |
| 3B.2 | L-Wall junction detection + IC placement | 3 | 1 | 4 | Not Started |
| 3B.3 | T-Wall junction detection (3-way) | 3 | 1 | 4 | Not Started |
| 3B.4 | C/U-Wall detection (connected wall loop) | 3 | 1 | 4 | Not Started |
| 3B.5 | Panel layout drawing for junction types | 2 | 0.5 | 2.5 | Not Started |
| 3B.6 | Testing with real client DXF samples | 1 | 3 | 4 | Not Started |
| **Phase 3B Total** | | **12.5** | **7.5** | **20** | 🔶 Pending |

---

## Phase 4 — Multi-Floor Support 🔶 PENDING

> **Dependency:** Client must provide a multi-floor DXF sample (even with dummy data) with floor-tagged element labels or separate DXF layers per floor.
> **Note:** Parser groundwork done in Phase 3C (floor_label field + CC1/F1 label parsing). Full per-floor BOQ grouping + UI is still pending.

| # | Module | R1 (PD) | R2 (PD) | Total | Status |
|---|---|---|---|---|---|
| 4.1 | Floor label detection (DXF layer/label prefix) | 2 | 0.5 | 2.5 | Partial (label parsing done in 3C.5) |
| 4.2 | Per-floor BOQ grouping + summary sheet | 2 | 1 | 3 | Not Started |
| 4.3 | Floor-wise Excel sheet tabs | 1 | 0.5 | 1.5 | Not Started |
| 4.4 | Floor-wise 3D view (separate or combined) | 1.5 | 0.5 | 2 | Not Started |
| 4.5 | UAT with multi-floor client DXF | 0.5 | 2 | 2.5 | Not Started |
| **Phase 4 Total** | | **7** | **4.5** | **11.5** | 🔶 Pending |

---

## Phase 5 — AutoCAD DXF Panel Layout Export 🔶 PENDING

| # | Module | R1 (PD) | R2 (PD) | Total | Status |
|---|---|---|---|---|---|
| 5.1 | DXF output design (layers, annotation style) | 1 | 0.5 | 1.5 | Not Started |
| 5.2 | ezdxf write: panel strips as DXF entities | 3 | 0.5 | 3.5 | Not Started |
| 5.3 | Dimension annotations + labels in DXF | 1.5 | 0.5 | 2 | Not Started |
| 5.4 | Validation: open output in AutoCAD/DraftSight | 0.5 | 1 | 1.5 | Not Started |
| **Phase 5 Total** | | **6** | **2.5** | **8.5** | 🔶 Pending |

---

## Phase 6 — Testing & QA

| # | Activity | R1 (PD) | R2 (PD) | Total | Status |
|---|---|---|---|---|---|
| 6.1 | Unit tests — engine modules | 1 | 3 | 4 | Partial |
| 6.2 | Integration tests — DXF → BOQ → Export | 0.5 | 2 | 2.5 | Partial |
| 6.3 | UAT — Phase 1 & 2 with Nova team | 0.5 | 2 | 2.5 | Not Started |
| 6.4 | Regression testing — Phase 3B + 4 | 0.5 | 2 | 2.5 | Not Started |
| 6.5 | Cross-platform testing (Windows primary) | 0.5 | 1.5 | 2 | Not Started |
| 6.6 | Bug fixes from UAT rounds | 2 | 1 | 3 | Not Started |
| **Phase 6 Total** | | **5** | **11.5** | **16.5** | 🔶 Ongoing |

---

## Phase 7 — Documentation & Delivery 🔶 PENDING

| # | Activity | R1 (PD) | R2 (PD) | Total | Status |
|---|---|---|---|---|---|
| 7.1 | User Manual (feature walkthrough) | 0.5 | 2 | 2.5 | Not Started |
| 7.2 | Technical / deployment guide | 0.5 | 1 | 1.5 | Not Started |
| 7.3 | Client onboarding session | 0.5 | 0.5 | 1 | Not Started |
| 7.4 | Final handover + source code delivery | 0.5 | 0.5 | 1 | Not Started |
| **Phase 7 Total** | | **2** | **4** | **6** | 🔶 Pending |

---

## Overall Summary

| Phase | Description | Total PD | Status |
|---|---|---|---|
| Phase 1 | Core Desktop Application | 46.0 | ✅ Complete |
| Phase 2 | Advanced Structures + BOQ Sheets | 13.5 | ✅ Complete |
| Phase 3A | Streamlit Web App | 9.5 | ✅ Complete |
| Phase 3C | Brand Refresh & Output Templates | 10.5 | ✅ Complete |
| Phase 3B | Junction Types (L/T/C-U Wall) | 20.0 | 🔶 Pending (client DXF needed) |
| Phase 4 | Multi-Floor Support | 11.5 | 🔶 Pending (client DXF needed) |
| Phase 5 | DXF Panel Layout Export | 8.5 | 🔶 Pending |
| Phase 6 | Testing & QA | 16.5 | 🔶 Ongoing |
| Phase 7 | Documentation & Delivery | 6.0 | 🔶 Pending |
| **TOTAL** | | **142.0 PD** | |
| **Completed** | | **79.5 PD (56%)** | |
| **Remaining** | | **62.5 PD (44%)** | |

---

## Timeline Estimate (Remaining Work Only)

Assumptions:
- 2 resources working in parallel
- ~8 effective person-days/week combined (accounts for meetings, reviews, client dependency delays)
- Phase 3B and Phase 4 cannot start until client provides sample DXF files

| Phase | Parallel Duration | Calendar Weeks | Notes |
|---|---|---|---|
| Phase 3B | R1 + R2 parallel | ~3 weeks | Blocked on client DXF samples |
| Phase 4 | R1 + R2 parallel | ~2 weeks | Blocked on multi-floor DXF sample |
| Phase 5 | R1 leads (parallel with Phase 4) | ~1.5 weeks | Can overlap with Phase 4 |
| Phase 6 UAT + fixes | R2 leads, R1 fixes | ~2 weeks | After 3B + 4 complete |
| Phase 7 Docs + handover | R2 leads | ~1 week | Final sprint |
| **Total Remaining** | | **~9–10 weeks** | Subject to client dependency resolution |

---

## Key Dependencies & Blockers

| # | Dependency | Owned By | Blocks |
|---|---|---|---|
| D1 | Client provides L/T/C-U Wall DXF samples | Nova Formworks | Phase 3B cannot start |
| D2 | Client provides multi-floor project DXF sample | Nova Formworks | Phase 4 cannot start |
| D3 | Nova confirms Days BOQ rental pricing logic | Nova Formworks | Phase 2 Days BOQ UAT sign-off |
| D4 | Nova confirms current Excel COLUMN sheet template | Nova Formworks | Phase 6 UAT sign-off |
| D5 | ODA File Converter installed on client machine | Nova Formworks / IT | DWG direct import in production |

> **Action Required:** Dependencies D1–D5 should be requested from the client immediately to avoid sprint delays. Phases 3B and 4 together represent 31.5 PD of pending work and cannot be estimated precisely without the sample files.

---

## What Can Be Demonstrated Today

The following features are fully built and ready for client demo at any time:

- DXF drawing import with AutoCAD-quality preview
- Automatic detection of Columns, Walls, Shear Walls, Box Culverts, Drains, Monolithic elements
- Multi-floor label detection from DXF (CC1/F1, W3/GF format — floor stored per element)
- Panel optimization (DP algorithm, exact combinations, OC/IC corners)
- Accessories calculation (Pins, Wallers, Tierods, Wing Nuts, PVC Cones)
- High-wall warning (>4500mm) flagged in UI and output
- **BOQ PDF export** — updated Nova 2025 template (No of Set, grouped by dimension, purple gradient brand, Accessories + Summary)
- **Quotation PDF export** — separate document with per-SqM pricing, T&C, Valid Until, Prepared By: Hiren Jadav
- **Excel export** — 3 sheets: FORMWORK BOQ, FORMWORK QUOTATION, DAYS BOQ (Nova 2025 format)
- Days BOQ sheet (floor cycle planning)
- Interactive 3D element overview
- 3D panel assembly visualization (rotatable)
- Offline AI Assistant for BOQ queries
- Streamlit web app (online access, no installation required)

---

## Change Log

| Date | Change | Phase |
|---|---|---|
| 2026-05-12 | Initial estimate created | All |
| 2026-05-15 | Phase 3C added — Brand Refresh & Output Template Update (10.5 PD, complete) | 3C |
| 2026-05-15 | Phase 4 note updated — floor_label parsing groundwork done in 3C.5 | 4 |
| 2026-05-15 | Overall summary updated — 79.5 PD completed (56%) | All |

---

*Document prepared by development team — NovoForm v1.0 | Updated 2026-05-15*
