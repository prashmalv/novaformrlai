"""
NovoForm Web Application — Streamlit
Online version of NovoForm BOQ & Estimation Software.
Reuses all engine code from src/ unchanged.
"""

import io
import os
import sys
import tempfile
from pathlib import Path
from datetime import date

import streamlit as st

# ── Path setup so src/ is importable ───────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── Page config (MUST be first Streamlit call) ──────────────────────────────────
st.set_page_config(
    page_title="NovoForm — BOQ Generator",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Imports (after path setup) ──────────────────────────────────────────────────
from src.models.element import (
    StructuralElement, ElementType, JunctionType, ProjectBOQ, ElementBOQ
)
from src.engine.panel_optimizer import compute_boq
from src.output.boq_generator import aggregate_project_boq
from src.output.pdf_generator import generate_pdf
from src.output.excel_generator import generate_excel_boq

# Optional DXF parser
try:
    from src.parsers.dwg_parser import parse_dxf
    DXF_AVAILABLE = True
except ImportError:
    DXF_AVAILABLE = False

# ── Constants ──────────────────────────────────────────────────────────────────
LOGO_PATH = ROOT / "assets" / "images" / "NovaLogo.png"
NOVA_BLUE = "#003087"
NOVA_LIGHT = "#e8f0fe"

ELEMENT_TYPES = [e.value for e in ElementType]
JUNCTION_TYPES = [j.value for j in JunctionType]
PANEL_HEIGHTS = [3200, 3000, 2470, 1228, 900, 600]

# ── CSS Styling ─────────────────────────────────────────────────────────────────
def inject_css():
    st.markdown("""
    <style>
    /* ── App background ── */
    .stApp { background: #f4f6fb; }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #001f5b 0%, #003087 100%);
    }
    section[data-testid="stSidebar"] * { color: #ffffff !important; }
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stNumberInput label,
    section[data-testid="stSidebar"] .stTextInput label { color: #c8d8f8 !important; }

    /* ── Header banner ── */
    .nova-header {
        background: linear-gradient(90deg, #001f5b 0%, #003087 60%, #0050c8 100%);
        padding: 18px 28px;
        border-radius: 12px;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        gap: 18px;
    }
    .nova-header h1 {
        color: #ffffff !important;
        font-size: 1.9rem;
        margin: 0;
        font-weight: 700;
        letter-spacing: 1px;
    }
    .nova-header p {
        color: #a0c4ff;
        margin: 2px 0 0 0;
        font-size: 0.9rem;
    }

    /* ── Cards ── */
    .nova-card {
        background: #ffffff;
        border-radius: 10px;
        padding: 18px 22px;
        box-shadow: 0 2px 8px rgba(0,48,135,0.10);
        margin-bottom: 16px;
        border-left: 4px solid #003087;
    }
    .nova-card h4 {
        color: #003087;
        font-size: 1rem;
        font-weight: 700;
        margin: 0 0 10px 0;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* ── Section titles ── */
    .section-title {
        color: #001f5b;
        font-size: 1.1rem;
        font-weight: 700;
        border-bottom: 2px solid #003087;
        padding-bottom: 6px;
        margin: 24px 0 14px 0;
    }

    /* ── BOQ table ── */
    .boq-table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
    .boq-table th {
        background: #003087;
        color: white;
        padding: 8px 10px;
        text-align: left;
    }
    .boq-table td { padding: 7px 10px; border-bottom: 1px solid #e0e0e0; }
    .boq-table tr:nth-child(even) td { background: #f0f4ff; }
    .boq-table .corner-row td { background: #fff3e0 !important; }

    /* ── Metric boxes ── */
    .metric-box {
        background: linear-gradient(135deg, #003087 0%, #0050c8 100%);
        color: white;
        padding: 16px 20px;
        border-radius: 10px;
        text-align: center;
    }
    .metric-box .val { font-size: 1.6rem; font-weight: 800; }
    .metric-box .lbl { font-size: 0.8rem; opacity: 0.85; margin-top: 2px; }

    /* ── Buttons ── */
    .stButton > button {
        background: linear-gradient(90deg, #001f5b, #003087);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 28px;
        font-weight: 600;
        font-size: 0.95rem;
        letter-spacing: 0.3px;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        background: linear-gradient(90deg, #003087, #0050c8);
        box-shadow: 0 4px 12px rgba(0,80,200,0.3);
    }

    /* ── Warning/info banners ── */
    .warn-box {
        background: #fff8e1;
        border-left: 4px solid #ff9800;
        padding: 10px 14px;
        border-radius: 6px;
        color: #7a4400;
        font-size: 0.87rem;
        margin: 6px 0;
    }

    /* ── Footer ── */
    .nova-footer {
        text-align: center;
        color: #7a8aaa;
        font-size: 0.82rem;
        margin-top: 40px;
        padding-top: 16px;
        border-top: 1px solid #dde3f0;
    }

    /* ── Element list item ── */
    .elem-item {
        background: #fff;
        border: 1px solid #dde3f0;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 6px 0;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    /* Streamlit overrides */
    div[data-testid="stExpander"] { border: 1px solid #dde3f0 !important; border-radius: 8px !important; }
    div.stTabs [data-baseweb="tab"] { font-weight: 600; }
    div.stTabs [aria-selected="true"] { border-bottom: 3px solid #003087 !important; color: #003087 !important; }
    </style>
    """, unsafe_allow_html=True)


# ── Session state init ──────────────────────────────────────────────────────────
def init_state():
    defaults = {
        "elements": [],
        "boq_result": None,
        "project": ProjectBOQ(),
        "panel_height": 3200,
        "num_sets": 1,
        "panel_rate": 0.0,
        "gst_enabled": True,
        "freight": 0.0,
        "active_tab": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── Header ─────────────────────────────────────────────────────────────────────
def render_header():
    col_logo, col_title = st.columns([1, 8])
    with col_logo:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=70)
    with col_title:
        st.markdown("""
        <div style="padding-top:6px">
            <h1 style="color:#003087;margin:0;font-size:1.8rem;font-weight:800;letter-spacing:1px;">
                NovoForm <span style="color:#0050c8;font-size:1.1rem;font-weight:400">BOQ Generator</span>
            </h1>
            <p style="color:#5a6a8a;margin:2px 0 0 0;font-size:0.87rem;">
                Nova Formworks Pvt. Ltd. &nbsp;|&nbsp; AI-Based Formwork Analysis &amp; Estimation
            </p>
        </div>
        """, unsafe_allow_html=True)
    st.divider()


# ── Sidebar: Project Info + Config ─────────────────────────────────────────────
def render_sidebar():
    st.sidebar.markdown("### 📋 Project Details")

    proj = st.session_state.project

    proj.client_name    = st.sidebar.text_input("Client Name", value=proj.client_name or "", placeholder="e.g. ABC Constructions")
    proj.project_name   = st.sidebar.text_input("Project Name", value=proj.project_name or "", placeholder="e.g. Multi-storey Building")
    proj.client_address = st.sidebar.text_area("Site Address", value=proj.client_address or "", height=80, placeholder="City, State")
    proj.ipo_no         = st.sidebar.text_input("IPO / Enquiry No.", value=proj.ipo_no or "")
    proj.date           = st.sidebar.text_input("Date", value=proj.date or str(date.today()))

    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚙️ Configuration")

    st.session_state.panel_height = st.sidebar.selectbox(
        "Panel Height (mm)", PANEL_HEIGHTS,
        index=PANEL_HEIGHTS.index(st.session_state.panel_height)
        if st.session_state.panel_height in PANEL_HEIGHTS else 0
    )
    st.session_state.num_sets = st.sidebar.number_input("No. of Sets", min_value=1, max_value=20, value=st.session_state.num_sets)
    st.session_state.panel_rate = st.sidebar.number_input("Panel Rate (₹/sqm)", min_value=0.0, value=st.session_state.panel_rate, step=100.0)
    st.session_state.gst_enabled = st.sidebar.checkbox("Include GST @ 18%", value=st.session_state.gst_enabled)
    st.session_state.freight = st.sidebar.number_input("Freight (₹)", min_value=0.0, value=st.session_state.freight, step=500.0)

    # Apply config to project
    proj.panel_height_mm    = float(st.session_state.panel_height)
    proj.num_sets           = st.session_state.num_sets
    proj.panel_rate_per_sqm = st.session_state.panel_rate
    proj.gst_enabled        = st.session_state.gst_enabled
    proj.freight_amount     = st.session_state.freight

    st.sidebar.markdown("---")
    n = len(st.session_state.elements)
    st.sidebar.markdown(f"**Elements loaded:** {n}")
    if st.session_state.boq_result:
        agg = st.session_state.boq_result
        st.sidebar.markdown(f"**Total Area:** {agg['total_area_sqm']} m²")
        if agg['grand_total'] > 0:
            st.sidebar.markdown(f"**Grand Total:** ₹{agg['grand_total']:,.0f}")

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<div style='font-size:0.78rem;color:#90a0c0;text-align:center'>"
        "NovoForm v2.0 — Phase 2<br>© Nova Formworks Pvt. Ltd.</div>",
        unsafe_allow_html=True
    )


# ── Tab 1: Import / Add Elements ───────────────────────────────────────────────
def tab_import():
    st.markdown('<div class="section-title">📁 Import DXF Drawing or Add Elements Manually</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([1.2, 1])

    with col1:
        st.markdown('<div class="nova-card"><h4>Upload DXF Drawing</h4>', unsafe_allow_html=True)
        dxf_file = st.file_uploader(
            "Drop your DXF file here",
            type=["dxf"],
            help="DWG files need to be converted to DXF first using AutoCAD or ODA File Converter"
        )

        if dxf_file and DXF_AVAILABLE:
            if st.button("🔍 Auto-Detect Elements", use_container_width=True):
                with st.spinner("Parsing DXF drawing..."):
                    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
                        tmp.write(dxf_file.getvalue())
                        tmp_path = tmp.name
                    try:
                        detected = parse_dxf(tmp_path)
                        if detected:
                            st.session_state.elements = detected
                            st.session_state.boq_result = None
                            st.success(f"✅ Detected {len(detected)} elements from drawing!")
                        else:
                            st.warning("No structural elements detected. Please add manually.")
                    except Exception as e:
                        st.error(f"Parse error: {e}")
                    finally:
                        os.unlink(tmp_path)
        elif dxf_file and not DXF_AVAILABLE:
            st.warning("DXF parser not available. Please install ezdxf.")

        if not dxf_file:
            st.info("💡 Upload a DXF file to auto-detect columns, walls, and shear walls from your AutoCAD drawing.")

        st.markdown('</div>', unsafe_allow_html=True)

        # DWG help
        with st.expander("📌 How to convert DWG → DXF?"):
            st.markdown("""
            **Option 1 — AutoCAD:**
            - Open DWG → File → Save As → Select "DXF" format → Save

            **Option 2 — ODA File Converter (Free):**
            - Download from [opendesign.com](https://www.opendesign.com/guestfiles/oda_file_converter)
            - Select input folder, output folder → Convert

            **Option 3 — Online Converter:**
            - Use any DWG-to-DXF online converter
            """)

    with col2:
        st.markdown('<div class="nova-card"><h4>Add Element Manually</h4>', unsafe_allow_html=True)
        _add_element_form()
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Elements list ────────────────────────────────────────────────────────────
    if st.session_state.elements:
        st.markdown(f'<div class="section-title">📝 Elements List ({len(st.session_state.elements)} elements)</div>', unsafe_allow_html=True)

        # Bulk clear
        col_a, col_b = st.columns([6, 1])
        with col_b:
            if st.button("🗑️ Clear All", use_container_width=True):
                st.session_state.elements = []
                st.session_state.boq_result = None
                st.rerun()

        for i, elem in enumerate(st.session_state.elements):
            col_info, col_del = st.columns([8, 1])
            with col_info:
                junction_str = f" | {elem.junction_type.value}" if elem.junction_type != JunctionType.NONE else ""
                floor_str    = f" | Floor: {elem.floor_label}" if elem.floor_label else ""
                st.markdown(
                    f"<div class='elem-item'>"
                    f"<b>{elem.label}</b> &nbsp;·&nbsp; {elem.element_type.value} "
                    f"&nbsp;·&nbsp; {elem.length_mm:.0f}×{elem.width_mm:.0f}mm "
                    f"H={elem.height_mm:.0f}mm &nbsp;·&nbsp; Qty={elem.quantity}"
                    f"{junction_str}{floor_str}"
                    f"</div>",
                    unsafe_allow_html=True
                )
            with col_del:
                if st.button("×", key=f"del_{i}", help="Remove this element"):
                    st.session_state.elements.pop(i)
                    st.session_state.boq_result = None
                    st.rerun()


def _add_element_form():
    with st.form("add_element_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            label       = st.text_input("Label", placeholder="C1 / SW1 / W1")
            elem_type   = st.selectbox("Type", ELEMENT_TYPES)
            length      = st.number_input("Length (mm)", min_value=50, max_value=50000, value=600, step=50)
            height      = st.number_input("Height (mm)", min_value=100, max_value=20000, value=3000, step=50)
        with col2:
            width       = st.number_input("Width / Thickness (mm)", min_value=50, max_value=5000, value=300, step=50)
            quantity    = st.number_input("Quantity", min_value=1, max_value=500, value=1)
            junction    = st.selectbox("Junction (walls)", JUNCTION_TYPES)
            floor_lbl   = st.text_input("Floor Label", placeholder="GF / 1F / 2F")

        submitted = st.form_submit_button("➕ Add Element", use_container_width=True)
        if submitted:
            if not label.strip():
                st.error("Label is required.")
            else:
                new_elem = StructuralElement(
                    element_type  = ElementType(elem_type),
                    label         = label.strip().upper(),
                    length_mm     = float(length),
                    width_mm      = float(width),
                    height_mm     = float(height),
                    quantity      = int(quantity),
                    junction_type = JunctionType(junction),
                    floor_label   = floor_lbl.strip(),
                )
                st.session_state.elements.append(new_elem)
                st.session_state.boq_result = None
                st.success(f"Added: {new_elem.label}")


# ── Tab 2: BOQ Results ─────────────────────────────────────────────────────────
def tab_boq():
    st.markdown('<div class="section-title">📊 Bill of Quantities</div>', unsafe_allow_html=True)

    if not st.session_state.elements:
        st.info("No elements added yet. Go to **Import / Add Elements** tab first.")
        return

    col_gen, _ = st.columns([1, 3])
    with col_gen:
        gen_btn = st.button("⚡ Generate BOQ", use_container_width=True)

    if gen_btn:
        with st.spinner("Running panel optimization..."):
            _run_boq()

    if not st.session_state.boq_result:
        st.markdown(
            "<div class='warn-box'>Click <b>Generate BOQ</b> to compute optimal panel combinations.</div>",
            unsafe_allow_html=True
        )
        return

    agg  = st.session_state.boq_result
    proj = st.session_state.project

    # ── Metrics ──────────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    metrics = [
        ("Total Panel Area", f"{agg['total_area_sqm']} m²"),
        ("Panel Cost",       f"₹{agg['total_panel_cost']:,.0f}" if agg['total_panel_cost'] > 0 else "—"),
        ("GST (18%)",        f"₹{agg['gst_amount']:,.0f}" if proj.gst_enabled else "—"),
        ("Grand Total",      f"₹{agg['grand_total']:,.0f}" if agg['grand_total'] > 0 else "—"),
    ]
    for col, (lbl, val) in zip([c1, c2, c3, c4], metrics):
        with col:
            st.markdown(
                f"<div class='metric-box'><div class='val'>{val}</div><div class='lbl'>{lbl}</div></div>",
                unsafe_allow_html=True
            )

    st.markdown("")

    # ── Per-element breakdown ────────────────────────────────────────────────────
    st.markdown("#### Element-wise Panel Details")

    for eboq in proj.element_boqs:
        elem = eboq.element
        with st.expander(
            f"**{elem.label}** — {elem.element_type.value}  "
            f"{elem.length_mm:.0f}×{elem.width_mm:.0f}mm  H={elem.height_mm:.0f}mm  (Qty {elem.quantity})",
            expanded=False
        ):
            if eboq.warnings:
                for w in eboq.warnings:
                    st.markdown(f"<div class='warn-box'>⚠️ {w}</div>", unsafe_allow_html=True)

            rows_html = ""
            for p in eboq.panels:
                row_cls = "corner-row" if p.is_corner else ""
                rows_html += (
                    f"<tr class='{row_cls}'>"
                    f"<td>{p.size_label}</td>"
                    f"<td style='text-align:right'>{p.quantity}</td>"
                    f"<td style='text-align:right'>{p.area_sqm:.4f}</td>"
                    f"<td style='text-align:right'>{p.total_area_sqm:.4f}</td>"
                    f"<td>{'Corner' if p.is_corner else 'Flat'}</td>"
                    f"</tr>"
                )

            st.markdown(f"""
            <table class='boq-table'>
              <thead><tr>
                <th>Panel Size</th><th style='text-align:right'>Qty</th>
                <th style='text-align:right'>Unit Area (m²)</th>
                <th style='text-align:right'>Total Area (m²)</th>
                <th>Type</th>
              </tr></thead>
              <tbody>{rows_html}</tbody>
            </table>
            """, unsafe_allow_html=True)

            if eboq.spacer_mm > 0:
                st.caption(f"Spacer gap used: {eboq.spacer_mm:.0f}mm")
            if eboq.height_note:
                st.caption(f"Achieved height: {eboq.height_note}")

    # ── Summary table ────────────────────────────────────────────────────────────
    st.markdown("#### Consolidated Panel Summary")

    summary = agg['summary_panels']
    rows_html = ""
    total_qty  = 0
    total_area = 0.0
    for size, d in summary.items():
        tag    = " 🔶" if d['is_corner'] else ""
        rows_html += (
            f"<tr>"
            f"<td>{size}{tag}</td>"
            f"<td style='text-align:right'>{d['quantity']}</td>"
            f"<td style='text-align:right'>{d['area_sqm']:.3f}</td>"
            f"</tr>"
        )
        total_qty  += d['quantity']
        total_area += d['area_sqm']

    rows_html += (
        f"<tr style='font-weight:700;background:#e8f0fe'>"
        f"<td>TOTAL</td>"
        f"<td style='text-align:right'>{total_qty}</td>"
        f"<td style='text-align:right'>{total_area:.3f}</td>"
        f"</tr>"
    )

    st.markdown(f"""
    <table class='boq-table'>
      <thead><tr>
        <th>Panel Size</th>
        <th style='text-align:right'>Total Qty (×Sets)</th>
        <th style='text-align:right'>Total Area (m²)</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    """, unsafe_allow_html=True)


def _run_boq():
    proj = st.session_state.project
    proj.element_boqs = []

    ph = float(st.session_state.panel_height)

    for elem in st.session_state.elements:
        eboq = compute_boq(elem, ph)
        proj.element_boqs.append(eboq)

    agg = aggregate_project_boq(proj)
    st.session_state.boq_result = agg
    st.rerun()


# ── Tab 3: Export ──────────────────────────────────────────────────────────────
def tab_export():
    st.markdown('<div class="section-title">📤 Export BOQ</div>', unsafe_allow_html=True)

    if not st.session_state.boq_result:
        st.info("Generate the BOQ first (go to **BOQ Results** tab).")
        return

    proj = st.session_state.project

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="nova-card"><h4>PDF Quotation</h4>', unsafe_allow_html=True)
        st.markdown(
            "Nova-branded PDF with client info, element-wise panel tables, "
            "accessories summary, and cost breakdown."
        )
        if st.button("📄 Download PDF", use_container_width=True, key="pdf_btn"):
            with st.spinner("Generating PDF..."):
                pdf_bytes = _generate_pdf_bytes(proj)
            fname = f"NovoForm_BOQ_{proj.client_name or 'Project'}.pdf"
            st.download_button(
                "⬇️ Click to Save PDF",
                data=pdf_bytes,
                file_name=fname,
                mime="application/pdf",
                use_container_width=True,
            )
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="nova-card"><h4>Excel BOQ</h4>', unsafe_allow_html=True)
        st.markdown(
            "Excel file in Nova's COLUMN sheet format + a **Days BOQ** tab "
            "showing Day-1 / Day-2 / Day-3 panel deployment schedule."
        )
        if st.button("📊 Download Excel", use_container_width=True, key="excel_btn"):
            with st.spinner("Generating Excel..."):
                excel_bytes = _generate_excel_bytes(proj)
            fname = f"NovoForm_BOQ_{proj.client_name or 'Project'}.xlsx"
            st.download_button(
                "⬇️ Click to Save Excel",
                data=excel_bytes,
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        st.markdown('</div>', unsafe_allow_html=True)

    # What's included notice
    st.markdown("")
    st.markdown('<div class="nova-card"><h4>What\'s Included in Export</h4>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        **PDF Quotation:**
        - Nova Formworks company header with logo
        - Client & project details
        - Per-element panel breakdown
        - Consolidated panel summary
        - Accessories estimate (pins, wallers, tierods)
        - Cost + GST + Freight breakdown
        """)
    with c2:
        st.markdown("""
        **Excel BOQ:**
        - COLUMN sheet (matches Nova's Excel format)
        - Panel sizes, quantities, area calculations
        - Summary with Grand Total formulas
        - **DAYS BOQ sheet** — Day-1/2/3 deployment batches
        - Colour-coded inventory schedule
        """)
    st.markdown('</div>', unsafe_allow_html=True)


def _generate_pdf_bytes(proj: ProjectBOQ) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        generate_pdf(proj, float(st.session_state.panel_height), tmp_path)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _generate_excel_bytes(proj: ProjectBOQ) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        generate_excel_boq(
            proj,
            tmp_path,
            price_per_sqm=proj.panel_rate_per_sqm,
            freight_amount=proj.freight_amount,
            gst_rate=0.18 if proj.gst_enabled else 0.0,
        )
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ── Tab 4: About / Help ────────────────────────────────────────────────────────
def tab_about():
    st.markdown('<div class="section-title">ℹ️ About NovoForm</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([1.5, 1])

    with col1:
        st.markdown('<div class="nova-card"><h4>Supported Structure Types</h4>', unsafe_allow_html=True)
        st.markdown("""
        | Type | Description | Corner Logic |
        |------|-------------|--------------|
        | Column | Rectangular, 4 faces | OC80 × 4 corners |
        | Wall / Shear Wall | Straight, 2 faces | OC80 × 4 end corners |
        | L-Wall | L-junction | OC80 + IC100 at 1 junction |
        | T-Wall | T-junction | OC80 + IC100 at 2 junctions |
        | C/U-Wall | Enclosed shape | OC80 + IC100 at 2 inner corners |
        | Box Culvert | 4 inner faces | IC100 × 4 inner, OC80 × 4 outer |
        | Drain | U-shape, 3 faces | IC100 × 2 bottom, OC80 × 4 top |
        | Monolithic | Unified slab+wall | Handled as combined element |
        """)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="nova-card"><h4>Panel Optimization</h4>', unsafe_allow_html=True)
        st.markdown("""
        - **Dynamic Programming (DP)** finds optimal panel widths summing to exact face dimension
        - **Symmetric preference**: 500+500 preferred over 600+400 for 1000mm face
        - **Standard widths**: 600, 500, 490, 440, 400, 350, 300, 275, 250, 240, 230, 200, 150, 125, 100, 40mm
        - **Spacer gap** up to 50mm allowed when exact fit not possible
        - Algorithm verified against real Nova Formworks quotations
        """)
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="nova-card"><h4>Quick Start</h4>', unsafe_allow_html=True)
        st.markdown("""
        1. **Fill project details** in the left sidebar
        2. **Upload DXF** drawing for auto-detection, or add elements manually
        3. **Configure** panel height, sets, rates in sidebar
        4. **Generate BOQ** — click the button in BOQ Results tab
        5. **Export** PDF quotation + Excel BOQ
        """)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="nova-card"><h4>DXF Auto-Detection</h4>', unsafe_allow_html=True)
        st.markdown("""
        The DXF parser reads your AutoCAD drawing and:
        - Detects closed polylines (columns and walls)
        - Reads dimension annotations for accurate sizing
        - Matches labels (C1, SW1, W1) from text entities
        - Classifies elements by aspect ratio

        **Note:** DWG files need to be converted to DXF first.
        See the import tab for conversion instructions.
        """)
        st.markdown('</div>', unsafe_allow_html=True)

        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=160)

    st.markdown(
        "<div class='nova-footer'>NovoForm v2.0 | © 2026 Nova Formworks Pvt. Ltd. | "
        "Developed by Prashant Malviya | +91-93 10 69 54 40</div>",
        unsafe_allow_html=True
    )


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    inject_css()
    init_state()
    render_header()
    render_sidebar()

    tab1, tab2, tab3, tab4 = st.tabs([
        "📁  Import / Add Elements",
        "📊  BOQ Results",
        "📤  Export",
        "ℹ️  About",
    ])

    with tab1:
        tab_import()

    with tab2:
        tab_boq()

    with tab3:
        tab_export()

    with tab4:
        tab_about()


if __name__ == "__main__":
    main()
