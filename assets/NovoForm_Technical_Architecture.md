# NovoForm — High Level Technical Architecture

**Project:** NovoForm Formwork Analysis & BOQ Automation
**Client:** Nova Formworks Pvt. Ltd.
**Prepared by:** RLAI (rightleft.ai)
**Version:** 1.1 | May 2026

---

## 1. System Overview

NovoForm is a **desktop + web formwork BOQ automation tool** built in Python.
It has two delivery modes that share the same core engine:

```
┌─────────────────────────────────────────────────────────┐
│                    DELIVERY LAYER                        │
│                                                          │
│   Desktop App (PyQt6)          Web App (Streamlit)       │
│   main.py → src/ui/            app_web.py                │
│   Windows installer BAT        browser-based             │
└────────────────────┬────────────────────────────────────┘
                     │  both use same core
┌────────────────────▼────────────────────────────────────┐
│                    CORE ENGINE (src/)                    │
│  parsers/  →  models/  →  engine/  →  output/           │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Layer-by-Layer Breakdown

```
src/
├── parsers/          INPUT LAYER   — reads drawing files
│   ├── dwg_parser.py              DWG / DXF files (ezdxf)
│   └── pdf_parser.py              PDF drawings (pymupdf + AI/OCR)
│
├── models/           DATA LAYER    — shared data structures
│   └── element.py                 StructuralElement, ElementBOQ,
│                                  ProjectBOQ, PanelEntry
│
├── engine/           LOGIC LAYER   — core computation
│   ├── panel_optimizer.py         panel combination algorithm (DP)
│   └── accessories_calc.py        wallers, tierods, pins, cones
│
├── output/           OUTPUT LAYER  — generates reports
│   ├── boq_generator.py           aggregates project-level totals
│   ├── pdf_generator.py           BOQ PDF + Quotation PDF (ReportLab)
│   ├── excel_generator.py         3-sheet Excel (openpyxl)
│   └── layout_drawing.py          2D panel layout (matplotlib)
│
└── ui/               PRESENTATION  — desktop GUI only
    ├── main_window.py             8-tab PyQt6 main window
    ├── drawing_viewer.py          DXF drawing preview (ezdxf + mpl)
    ├── view_3d.py                 3D element overview (mplot3d)
    ├── ai_assistant.py            offline Q&A chatbot (SQLite)
    └── mpl_toolbar.py             custom matplotlib toolbar
```

---

## 3. Data Flow — End to End

```
 INPUT                PARSE              COMPUTE            OUTPUT
────────          ─────────────       ─────────────       ──────────
DXF/DWG  ──────► dwg_parser.py ──┐
                                  │
PDF      ──────► pdf_parser.py ──┤
  (AI Vision /                    │  StructuralElement[]
   EasyOCR)                       │
                                  ▼
Manual Entry       ─────► models/element.py ──► panel_optimizer.py
                                                    │ ElementBOQ[]
                                                    │
                                                    ▼
                                           accessories_calc.py
                                                    │ AccessoriesBOQ
                                                    ▼
                                           boq_generator.py
                                                    │ ProjectBOQ (aggregated)
                                         ┌──────────┴──────────┐
                                         ▼                      ▼
                                  pdf_generator         excel_generator
                                  BOQ PDF                3-sheet Excel
                                  Quotation PDF         (BOQ / QTN / DAYS)
```

---

## 4. Key Algorithms

### 4.1 Panel Optimizer — Dynamic Programming

| Step | Detail |
|---|---|
| **Input** | Element face dimension in mm (e.g. 1200mm wall face) |
| **Algorithm** | DP finds exact combination of standard widths with no gap |
| **Standard widths** | 600, 500, 490, 440, 400, 350, 340, 300, 275, 250, 240, 230, 200, 150, 125, 100, 40 mm |
| **Corner panels** | OC80 (Outer Corner 80mm) at 4 column corners; IC100 (Inner Corner) for L/T/C junctions |
| **Output** | List of `PanelEntry` objects — size label, quantity, area sqm |

### 4.2 DXF / DWG Parser

| Step | Detail |
|---|---|
| **Reads** | `LWPOLYLINE` closed entities from DXF via ezdxf |
| **Measures** | Bounding box of each polyline |
| **Classifies** | Column: aspect ratio ≤ 4:1, dims 150–1500mm; Wall: long/short ≥ 3:1 |
| **Labels** | Matched from nearby `TEXT`/`MTEXT` entities (pattern: C1, SW1, W1) |
| **Multi-floor** | `CC1/F1` label format → splits into label + `floor_label` field |
| **Fallback** | Dimension-from-text: reads `750x375` style annotations near polylines |

### 4.3 PDF Parser — Two Modes

**Mode 1 — Extract with AI (Claude Vision)**
```
PDF page → render to PNG (150 DPI) → base64 encode
→ Claude Sonnet Vision API (structured prompt)
→ JSON response: [{label, type, length_mm, width_mm, quantity}]
→ StructuralElement list
```

**Mode 2 — Extract Offline (EasyOCR + OpenCV)**
```
PDF page → render to PNG (200 DPI) → OpenCV preprocessing
  (invert dark bg → adaptive threshold → median blur)
→ EasyOCR text detection → text + bounding box positions
→ Label detection: regex [C/W/SW]\d+ patterns
→ Proximity matching: each label ↔ nearest dimension text
→ StructuralElement list
```

### 4.4 Accessories Calculator

| Element | Accessories Computed |
|---|---|
| Column | PIN 50mm, PIN 20mm per face |
| Wall | Wallers (rows = ceil(H/500)+1), Tierods (positions = ceil(L/600)), Wing Nuts, PVC Cones |
| Tierod length | wall_thickness + 300mm (cone + nut), rounded to standard sizes |

---

## 5. Technology Stack

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| Desktop UI | PyQt6 | 6.6+ | 8-tab GUI, dialogs, tables |
| Web UI | Streamlit | latest | Browser-based version |
| DXF/DWG parsing | ezdxf | 1.3+ | Read AutoCAD files |
| PDF rendering | pymupdf (fitz) | 1.23+ | Render PDF pages to images |
| AI extraction | Anthropic Claude Sonnet | claude-sonnet-4-6 | Read structural schedules from PDF |
| Offline OCR | EasyOCR | 1.7+ | Free PDF extraction without API key |
| Image processing | OpenCV (cv2) | 4.8+ | Preprocessing for OCR |
| Panel optimization | Pure Python DP | — | Exact panel combination finding |
| PDF output | ReportLab | 4.0+ | Generate BOQ + Quotation PDFs |
| Excel output | openpyxl | 3.1+ | 3-sheet formatted Excel |
| 2D/3D drawing | matplotlib | 3.8+ | Panel layouts, 3D element view |
| Config storage | JSON | — | Panel catalog, API key |
| AI chatbot | SQLite + rule engine | — | Offline BOQ Q&A |
| Packaging | BAT + VBScript | — | Windows one-click installer |

---

## 6. Data Models

```python
# Core element (input)
StructuralElement
  ├── element_type  : ElementType enum
  │     (Column, Wall, Shear Wall, Slab, Box Culvert,
  │      Drain, Monolithic, Beam Bottom, Beam Side)
  ├── label         : str         e.g. "C1", "SW3"
  ├── length_mm     : float       longer dimension
  ├── width_mm      : float       shorter dimension
  ├── height_mm     : float       casting height
  ├── quantity      : int
  ├── junction_type : JunctionType (None, L, T, C)
  └── floor_label   : str         e.g. "GF", "1F"

# BOQ result (computed)
ElementBOQ
  ├── element       : StructuralElement
  ├── panels        : list[PanelEntry]
  ├── spacer_mm     : float
  ├── height_note   : str         e.g. "3200MM achieved"
  └── warnings      : list[str]

# Panel entry
PanelEntry
  ├── size_label    : str         e.g. "600X3200", "OC80X3200"
  ├── width_mm      : float
  ├── height_mm     : float
  ├── quantity      : int
  └── area_sqm      : float

# Project level
ProjectBOQ
  ├── project_name, client_name, date, ipo_no
  ├── element_boqs  : list[ElementBOQ]
  ├── panel_height_mm, num_sets, gst_enabled
  └── rates         : panel_rate, waller_rate, tierod_rate...
```

---

## 7. Config Files

```
config/
├── panel_config.json    Panel catalog:
│                        - Standard widths: [600, 500, 490 ... 40] mm
│                        - Standard heights: [3200, 3000, 2470, 1228] mm
│                        - OC width: 80mm | IC width: 100mm
│                        - Company info: Nova Formworks Pvt. Ltd.
│                        - Default accessory counts per element type
│
└── api_config.json      Anthropic API key (for PDF AI extraction)
                         Stored locally, never shared in ZIP
```

---

## 8. Entry Points

| File | Launches | Command |
|---|---|---|
| `main.py` | Desktop app (PyQt6) | `python main.py` |
| `app_web.py` | Web app | `streamlit run app_web.py` |
| `batch_generate.py` | Batch process 5 sample drawings | `python batch_generate.py` |
| `install_windows_nova_updatedbranding.bat` | Windows installer | Double-click |

---

## 9. Output Files Generated

| Output | Format | Contents |
|---|---|---|
| BOQ PDF | PDF (ReportLab) | Panel list per element, accessories, summary — Nova 2025 branding |
| Quotation PDF | PDF (ReportLab) | Per-sqm pricing, GST, freight, T&C, Valid Until |
| Excel BOQ | .xlsx (openpyxl) | Sheet 1: FORMWORK BOQ · Sheet 2: FORMWORK QUOTATION · Sheet 3: DAYS BOQ |
| Layout Drawing | PNG/PDF (matplotlib) | 2D panel strip layout + cross-section per element |

---

## 10. Key Design Decisions

| Decision | Reason |
|---|---|
| **Models are UI-agnostic** | `src/models/` and `src/engine/` have zero PyQt6/Streamlit imports — both UIs call same engine |
| **No database** | All data lives in-memory as Python dataclasses per session; output files are the persistence |
| **Panel catalog is config-driven** | Adding a new panel width = edit `panel_config.json`, no code change needed |
| **DP for panel optimization** | Greedy fails for some combinations (e.g. 1000mm = 500+500 preferred over 600+400); DP guarantees optimal solution |
| **PDF extraction is two-tier** | AI Vision for accuracy (~95%); EasyOCR for offline/free use (~75%) |
| **Separate BOQ PDF + Quotation PDF** | BOQ = panel quantities only (shared publicly); Quotation = pricing (confidential) |
| **Floor label validation** | Regex rejects false positives like `F31` from DXF annotations; only valid floor patterns accepted |

---

## 11. Windows Distribution Package

```
NovoForm_v1.1_Nova_UpdatedBranding.zip  (228 KB)
├── main.py
├── requirements.txt
├── install_windows_nova_updatedbranding.bat   ← double-click to install
├── src/
│   ├── models/
│   ├── engine/
│   ├── output/
│   ├── parsers/
│   └── ui/
├── config/
│   └── panel_config.json
└── assets/
    └── images/
        └── NovaLogo.png
```

**Install flow (client machine):**
1. Unzip to any folder
2. Double-click `install_windows_nova_updatedbranding.bat`
3. Script: checks Python → creates venv → installs packages → creates Desktop shortcut
4. Launch via Desktop shortcut or `venv\Scripts\pythonw.exe main.py`

---

*Document prepared by RLAI (rightleft.ai) | NovoForm v1.1 | May 2026*
