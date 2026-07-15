# Proposal: NovoForm AI-Based BOQ & Estimation Software
### Prepared for: Nova Formworks Pvt. Ltd.
### Date: April 2026 | Version: 2.0

---

## 1. Project Overview

NovoForm is a purpose-built AI-enabled desktop software solution developed exclusively for Nova Formworks Pvt. Ltd. It automates the end-to-end process of reading construction drawings (CAD / DXF / DWG / PDF) and generating:

- **Bill of Quantities (BOQ)** — panel-wise, element-wise, project-wise
- **Cost Estimation** — with configurable rate cards and GST
- **Material & Accessories Calculation** — pins, wallers, tierods, wing nuts, PVC cones

The platform is built on Nova's own quotation logic, verified against actual client quotations, and is already operational with Phase 1 & Phase 2 delivered.

**Current Status as of April 2026:**
- Phase 1 (Core Engine + Desktop UI): ✅ Delivered & Tested
- Phase 2 (New Structure Types, Logo, IC Panels, Days BOQ, Multi-floor): ✅ Delivered
- Client sample BOQs verified for 6 real projects

---

## 2. Objective

| # | Objective |
|---|---|
| 1 | Automate BOQ generation directly from DWG / DXF / PDF drawings |
| 2 | Eliminate manual panel calculation errors and save sales team time |
| 3 | Generate professional Nova-branded quotations (Excel + PDF) instantly |
| 4 | Handle all Nova structure types: Columns, Walls, Shear Walls, Box Culverts, Drains, Monolithic |
| 5 | Support complex wall junctions (T / L / C shapes) with automatic IC panel assignment |
| 6 | Enable multi-user access with role-based control (Phase 3) |
| 7 | Provide real-time insights via AI assistant (Phase 3) |

---

## 3. Key Features

### A. Drawing Intelligence (Core AI Engine) ✅ Built
- Import AutoCAD DWG / DXF drawings directly
- Auto-detect structural elements: columns, walls, shear walls
- Extract dimensions using multi-source calibration:
  - DIMENSION entity annotations in drawing
  - Polyline bounding box geometry
  - Scale detection from $INSUNITS header
- **Dimension correction**: uses concrete face annotations (not stirrup cage) for accurate sizing
- Smart label detection: reads C1, SW1, W1 etc. from drawing text
- Manual review screen: user can correct any auto-detected element before BOQ

### B. BOQ & Estimation Engine ✅ Built
- **Dynamic Programming (DP)-based** panel optimizer — matches Nova's actual quotation logic
- Symmetric panel preference (e.g. 500+500 over 600+400 for 1000mm face)
- OC80 corner panels at all 4 column corners; OC80 at 4 wall end corners
- **IC100 Inner Corner panels** automatically assigned for T / L / C wall junctions
- Panel stacking for heights exceeding single panel height
- Spacer gap management (up to 50mm allowed)
- Configurable panel catalog (widths: 600, 500, 490, 440 ... 40mm; heights: 3200, 2470, 3000, 1228mm)
- Project-level panel aggregation with quantity multiplier per element set

### C. New Structure Types ✅ Phase 2
| Structure | Description | Corner Logic |
|---|---|---|
| **Column** | Rectangular, 4 faces | OC80 × 4 corners |
| **Wall / Shear Wall** | Straight, 2 faces | OC80 × 4 end corners |
| **L-Wall** | L-junction | OC80 + IC100 at 1 junction |
| **T-Wall** | T-junction | OC80 + IC100 at 2 junctions |
| **C/U-Wall** | Enclosed shape | OC80 + IC100 at 2 inner corners |
| **Box Culvert** | 4 inner faces (modular) | IC100 × 4 inner + OC80 × 4 outer |
| **Drain** | U-shape, 3 faces | IC100 × 2 bottom + OC80 × 4 top |
| **Monolithic** | Unified slab+wall+column | Handled as combined element set |

### D. Accessories Calculation ✅ Built
- **Columns (PIN system):** PIN 50mm (horizontal), PIN 80mm (vertical stack), PIN 20mm (OC corners)
- **Walls (WALLER + TIEROD system):**
  - Wallers: rows = ceil(H/500) + 1; standard lengths applied
  - Tierods: spacing ~600mm horizontal; length = wall thickness + 300mm; standard sizes
  - Wing Nuts: 2 per tierod
  - PVC Cones: 2 per tierod
- High-wall warning (>4500mm) flagged for engineer review

### E. Output Generation ✅ Built
- **PDF Quotation:** Nova-branded (blue theme), company logo, client info, per-element panel table, consolidated summary, accessories, cost breakdown with GST
- **Excel BOQ:** Matches Nova's COLUMN sheet format exactly — panel sizes, sets, heights, summary table with formulas, Grand Total
- **Days BOQ Sheet (NEW Phase 2):** Panel reuse / deployment schedule — Day-1, Day-2, Day-3 batches with balance inventory
- **Panel Layout Drawing:** Unrolled strip view (column) + elevation view (wall) with waller/tierod markers

### F. Manual Edit & Override ✅ Built
- Add / Edit / Delete any element manually
- Adjust dimensions, quantities, panel height, number of sets
- Quick text input: "5 columns 300×450 height 3000"
- All rates configurable: panel/sqm, waller/rm, tierod/rm, props/unit
- GST toggle, freight amount input
- Version history via Git (developer level)

### G. Multi-Floor Support ✅ Phase 2
- Each element carries a `Floor Label` (GF, 1F, 2F, Terrace)
- Different column sizes per floor tracked separately
- BOQ can be generated floor-wise or full-building

---

## 4. Technology Approach

| Layer | Technology | Purpose |
|---|---|---|
| **UI Framework** | PyQt6 (Python) | Native desktop app — Windows & Mac |
| **Drawing Parser** | ezdxf library + custom scale detection | DXF/DWG reading & element extraction |
| **BOQ Engine** | Dynamic Programming + Greedy algorithm | Optimal panel combination |
| **PDF Export** | ReportLab | Nova-branded professional quotation |
| **Excel Export** | openpyxl | Matches Nova's own Excel format exactly |
| **Layout Drawing** | matplotlib + ReportLab | Panel layout visualization |
| **Configuration** | JSON panel catalog | Easily updatable panel widths/heights |
| **Build/Packaging** | PyInstaller + GitHub Actions | Auto-builds Windows .exe on push |

### Phase 3 — Cloud / Online Architecture (Planned)
| Layer | Technology |
|---|---|
| **Backend API** | FastAPI (Python) |
| **Frontend** | React.js web app |
| **Database** | PostgreSQL (projects, BOQs, users) |
| **File Storage** | AWS S3 / Azure Blob (drawings) |
| **Auth** | JWT + Role-based access |
| **AI Assistant** | Claude API / OpenAI — project insights, BOQ suggestions |
| **Deployment** | Docker + AWS / Azure |

---

## 5. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   NovoForm Desktop App                   │
│                    (PyQt6 UI Layer)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │
│  │ Project  │  │Elements  │  │  Config  │  │ Export │  │
│  │  Info    │  │ Manager  │  │ & Rates  │  │  Tab   │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───┬────┘  │
│       └─────────────┴─────────────┴─────────────┘       │
│                         │                                │
│              ┌──────────▼──────────┐                    │
│              │   Core Engine Layer │                    │
│  ┌───────────┴──┐  ┌──────────────┴──┐  ┌──────────┐  │
│  │  DXF Parser  │  │ Panel Optimizer  │  │Accessory │  │
│  │ (ezdxf +     │  │ (DP Algorithm +  │  │Calculator│  │
│  │  AI scale    │  │  corner logic)   │  │          │  │
│  │  detection)  │  │                  │  │          │  │
│  └──────────────┘  └──────────────────┘  └──────────┘  │
│                         │                                │
│              ┌──────────▼──────────┐                    │
│              │   Output Layer       │                    │
│  ┌───────────┴──┐  ┌───────────────┴─┐  ┌──────────┐  │
│  │ PDF Generator│  │ Excel Generator  │  │ Layout   │  │
│  │ (ReportLab)  │  │ (openpyxl)       │  │ Drawing  │  │
│  │ Nova-branded │  │ COLUMN + DAYS BOQ│  │(matplotlib│  │
│  └──────────────┘  └─────────────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────┘
```

**Phase 3 — Cloud Architecture:**
```
Client Browser / Mobile App
        │
        ▼
   React Frontend  ──►  FastAPI Backend  ──►  PostgreSQL DB
                              │
                    ┌─────────┼──────────┐
                    ▼         ▼          ▼
              DXF Parser   BOQ Engine  AWS S3
                (same)     (same)    (drawings)
                              │
                              ▼
                        AI Assistant
                      (Claude API / LLM)
                    Project Insights & BOQ Suggestions
```

---

## 6. User Workflow

```
Step 1: NEW PROJECT
  └─► Enter client name, address, IPO no., project date

Step 2: IMPORT DRAWING
  └─► Upload DWG / DXF file
        └─► Auto-detect: elements, dimensions, labels
        └─► Review screen: confirm / correct detected elements

   OR: MANUAL ENTRY
  └─► Type elements directly (quick text or form input)

Step 3: CONFIGURE
  └─► Select panel height (3200 / 2470 / 3000 / 1228mm)
  └─► Set number of sets
  └─► Enter rates (panel/sqm, waller, tierod, props)
  └─► Enable GST, enter freight

Step 4: GENERATE BOQ
  └─► One click → Panel optimization runs
  └─► BOQ Results tab: per-element breakdown + consolidated summary
  └─► Accessories calculated automatically

Step 5: EXPORT
  └─► PDF Quotation (Nova-branded, ready to send to client)
  └─► Excel BOQ (COLUMN sheet + DAYS BOQ schedule)
  └─► Panel Layout Drawing (visual schematic)
```

---

## 7. Project Timeline

| Phase | Deliverables | Status | Timeline |
|---|---|---|---|
| **Phase 1** | Core engine, DXF parser, Column/Wall BOQ, PDF/Excel export, PyQt6 UI | ✅ Complete | Delivered |
| **Phase 2** | Logo, Box Culvert, Drain, Monolithic, IC panels, Multi-floor, Days BOQ | ✅ Complete | Delivered |
| **Phase 3A** | BOQ comparison view, custom filler panels, PDF-from-drawings (AI) | Planned | 3–4 Weeks |
| **Phase 3B** | Cloud/Online deployment, multi-user login, role-based access | Planned | 4–5 Weeks |
| **Phase 3C** | AI Assistant (project insights, BOQ suggestions, anomaly detection) | Planned | 2–3 Weeks |
| **Phase 3D** | Mobile App (Android + iOS) — view BOQs, share quotations | Optional | 4–6 Weeks |

> Total for Phase 3 (all tracks): **~10–14 Weeks** depending on scope finalized

---

## 8. Commercials (Excluding GST)

### A. Offline Desktop License (On-Premise)

| Package | Details | Cost |
|---|---|---|
| **Base License** | Up to 10 users, lifetime license, Windows desktop app | **₹6,00,000** |
| **Additional Users** | Each extra user license (beyond 10) | **₹60,000 / user** |
| **AMC** | Annual Maintenance Contract (bug fixes, minor updates, support) | **₹60,000 / year** |

> Includes: Core AI engine, BOQ engine, PDF/Excel export, DXF/DWG import, all structure types, accessories calculator, panel layout drawings.

---

### B. Online (Cloud-Based Deployment) — Optional Add-on

| Item | Cost |
|---|---|
| Cloud setup + deployment (AWS / Azure) | **₹1,00,000 – ₹2,00,000** (one-time) |
| Server / infrastructure maintenance | **₹10,000 – ₹15,000 / month** |

> Cloud option enables: web browser access from anywhere, no local installation, centralised data storage, team collaboration. Infrastructure cost borne by client.

---

### C. Mobile Application — Optional Add-on

| Platform | Cost |
|---|---|
| Android + iOS App | **₹1,00,000** (one-time development) |

> Features: View generated BOQs, share PDF quotations, project status tracking, basic input for quick estimation on the go.

---

### D. AI Assistant / Insights Bot — Optional Add-on

| Feature | Cost |
|---|---|
| AI chatbot for project insights | **₹50,000** (one-time) |

> Features: "How many 600×3200 panels do I need for this project?", automatic anomaly detection (unusually high panel count), BOQ summary in plain language, project cost comparison across clients.

---

### E. Troubleshooting / Enhancement

| Item | Cost |
|---|---|
| Any additional customization / new feature | **₹3,500 per man-day** |

---

### F. Cost Summary Table

| Scenario | One-Time Cost | Recurring |
|---|---|---|
| **Offline only (10 users)** | ₹6,00,000 | ₹60,000/year (AMC) |
| **Offline + Cloud** | ₹7,00,000–8,00,000 | ₹60,000/year AMC + ₹15,000/month server |
| **Offline + Cloud + Mobile App** | ₹8,00,000–9,00,000 | ₹60,000/year AMC + ₹15,000/month server |
| **Full Suite (all add-ons + AI)** | ₹9,00,000–10,00,000 | ₹60,000/year AMC + ₹15,000/month server |

> All prices are exclusive of GST (18% applicable). Infrastructure (cloud server) costs are borne by the client.

---

### G. Payment Terms

| Milestone | % | Amount (Base License) |
|---|---|---|
| Agreement signing + project kickoff | **40%** | ₹2,40,000 |
| Software deployment & handover | **40%** | ₹2,40,000 |
| 15 days post-deployment (after UAT) | **20%** | ₹1,20,000 |

---

## 9. Security & Compliance

| Area | Measures |
|---|---|
| **Data Security** | All drawings and BOQ data stored locally (offline mode) — no data leaves client premises |
| **Cloud Security** | HTTPS encryption, JWT authentication, AWS/Azure enterprise-grade security |
| **Access Control** | Role-based access (Admin / Engineer / Sales / View-only) |
| **Drawing Privacy** | Client DXF/DWG files processed locally — not shared with third parties |
| **Backup** | Automated daily backups of project database (cloud mode) |
| **Audit Trail** | All BOQ changes logged with user, timestamp, and version |

---

## 10. What's Already Built & Verified

| Feature | Status | Verified Against |
|---|---|---|
| DXF/DWG import + auto element detection | ✅ Working | CLIENT-1, 2, 3 DXF files |
| Dimension correction (concrete face vs stirrup cage) | ✅ Fixed | C1: 900×600 now correctly detected |
| Column BOQ (4-face + OC80) | ✅ Verified | CLIENT-1, CLIENT-2 Excel quotations |
| Wall / Shear Wall BOQ | ✅ Verified | Formwork 1.dxf — SW1, SW2, SW3 |
| Box Culvert BOQ | ✅ Built | IC100 × 4 inner, OC80 × 4 outer |
| Drain BOQ | ✅ Built | IC100 × 2 bottom, OC80 × 4 top |
| IC panel for L/T/C walls | ✅ Built | Automatic assignment |
| PDF Quotation with Nova logo | ✅ Working | All 6 client samples |
| Excel BOQ (COLUMN sheet format) | ✅ Working | Matches Nova's own Excel format |
| Days BOQ deployment schedule | ✅ Built | New Phase 2 |
| Accessories (pins, wallers, tierods) | ✅ Working | Flagged as estimated |
| Panel layout visualization | ✅ Working | Unrolled strip + plan view |
| Windows .exe auto-build | ✅ Working | GitHub Actions CI/CD |

---

## 11. Why NovoForm

- **Built specifically for Nova Formworks** — not a generic tool. Panel catalog, corner logic, quotation format all match Nova's actual practice.
- **Verified accuracy** — panel combinations cross-checked against real quotations shared by client.
- **Already working** — Phase 1 & 2 delivered and demonstrated. No vaporware.
- **Extensible** — clean architecture allows cloud, mobile, and AI features to be added without rewriting.
- **Your IP** — all source code is owned by Nova Formworks. Hosted on private GitHub repository.

---

*For queries contact: Prashant Malviya | +91-93 10 69 54 40 | prashantmalviya@example.com*

---
*Proposal valid for 30 days from date of issue.*
