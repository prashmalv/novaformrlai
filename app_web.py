"""
NovoForm Web Application — Streamlit
Online version of NovoForm BOQ & Estimation Software.
Reuses all engine code from src/ unchanged.
"""

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

# ── Engine imports (after path setup) ──────────────────────────────────────────
from src.models.element import (
    StructuralElement, ElementType, JunctionType, ProjectBOQ
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
LOGO_PATH    = ROOT / "assets" / "images" / "NovaLogo.png"
ELEMENT_TYPES  = [e.value for e in ElementType]
JUNCTION_TYPES = [j.value for j in JunctionType]
PANEL_HEIGHTS  = [3200, 3000, 2470, 1228, 900, 600]


# ══════════════════════════════════════════════════════════════════════════════
#  CSS
# ══════════════════════════════════════════════════════════════════════════════
def inject_css():
    st.markdown("""
    <style>
    .stApp { background: #f4f6fb; }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #001f5b 0%, #003087 100%);
    }
    section[data-testid="stSidebar"] * { color: #ffffff !important; }
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stNumberInput label,
    section[data-testid="stSidebar"] .stTextInput label { color: #c8d8f8 !important; }

    /* Cards */
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
        margin: 0 0 12px 0;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* Section titles */
    .section-title {
        color: #001f5b;
        font-size: 1.1rem;
        font-weight: 700;
        border-bottom: 2px solid #003087;
        padding-bottom: 6px;
        margin: 22px 0 14px 0;
    }

    /* BOQ table */
    .boq-table { width: 100%; border-collapse: collapse; font-size: 0.87rem; }
    .boq-table th {
        background: #003087; color: white;
        padding: 8px 10px; text-align: left;
    }
    .boq-table td { padding: 7px 10px; border-bottom: 1px solid #e0e0e0; }
    .boq-table tr:nth-child(even) td { background: #f0f4ff; }
    .boq-table .corner-row td { background: #fff3e0 !important; }

    /* Metric boxes */
    .metric-box {
        background: linear-gradient(135deg, #003087 0%, #0050c8 100%);
        color: white; padding: 16px 20px; border-radius: 10px; text-align: center;
    }
    .metric-box .val { font-size: 1.55rem; font-weight: 800; }
    .metric-box .lbl { font-size: 0.78rem; opacity: 0.85; margin-top: 2px; }

    /* Pricing card */
    .pricing-card {
        background: #f0f6ff;
        border-radius: 10px;
        padding: 16px 20px;
        border: 1.5px solid #b0ccf0;
        margin-bottom: 16px;
    }
    .pricing-card h4 {
        color: #003087; font-size: 0.95rem; font-weight: 700;
        margin: 0 0 10px 0; text-transform: uppercase; letter-spacing: 0.4px;
    }

    /* Element rows */
    .elem-row {
        background: #fff; border: 1px solid #dde3f0; border-radius: 8px;
        padding: 10px 14px; margin: 5px 0;
    }
    .elem-label { font-weight: 700; color: #003087; }
    .elem-meta  { color: #5a6a8a; font-size: 0.87rem; }

    /* Edit form highlight */
    .edit-active {
        background: #fff8e1; border: 2px solid #ffa000;
        border-radius: 10px; padding: 16px; margin-bottom: 14px;
    }

    /* Warn box */
    .warn-box {
        background: #fff8e1; border-left: 4px solid #ff9800;
        padding: 10px 14px; border-radius: 6px;
        color: #7a4400; font-size: 0.87rem; margin: 6px 0;
    }

    /* Buttons */
    .stButton > button {
        background: linear-gradient(90deg, #001f5b, #003087);
        color: white; border: none; border-radius: 8px;
        padding: 10px 28px; font-weight: 600;
        font-size: 0.93rem; letter-spacing: 0.3px;
    }
    .stButton > button:hover {
        background: linear-gradient(90deg, #003087, #0050c8);
        box-shadow: 0 4px 12px rgba(0,80,200,0.3);
    }

    /* Tab styling */
    div.stTabs [data-baseweb="tab"] { font-weight: 600; }
    div.stTabs [aria-selected="true"] {
        border-bottom: 3px solid #003087 !important; color: #003087 !important;
    }
    div[data-testid="stExpander"] {
        border: 1px solid #dde3f0 !important; border-radius: 8px !important;
    }

    /* Footer */
    .nova-footer {
        text-align: center; color: #7a8aaa; font-size: 0.82rem;
        margin-top: 40px; padding-top: 16px; border-top: 1px solid #dde3f0;
    }
    </style>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Session state
# ══════════════════════════════════════════════════════════════════════════════
def init_state():
    defaults = {
        "elements":    [],
        "boq_result":  None,
        "project":     ProjectBOQ(),
        "panel_height": 3200,
        "num_sets":    1,
        "panel_rate":  0.0,
        "gst_enabled": True,
        "freight":     0.0,
        "edit_idx":    None,   # index of element currently being edited
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ══════════════════════════════════════════════════════════════════════════════
#  Header
# ══════════════════════════════════════════════════════════════════════════════
def render_header():
    col_logo, col_title = st.columns([1, 9])
    with col_logo:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=72)
    with col_title:
        st.markdown("""
        <div style="padding-top:4px">
            <h1 style="color:#003087;margin:0;font-size:1.8rem;font-weight:800;letter-spacing:1px;">
                NovoForm
                <span style="color:#0050c8;font-size:1rem;font-weight:400;margin-left:8px;">
                    BOQ Generator
                </span>
            </h1>
            <p style="color:#5a6a8a;margin:2px 0 0 0;font-size:0.86rem;">
                Nova Formworks Pvt. Ltd.&nbsp;&nbsp;|&nbsp;&nbsp;
                AI-Based Formwork Analysis &amp; Estimation &nbsp;·&nbsp; v2.0
            </p>
        </div>
        """, unsafe_allow_html=True)
    st.divider()


# ══════════════════════════════════════════════════════════════════════════════
#  Sidebar — Project details + config
# ══════════════════════════════════════════════════════════════════════════════
def render_sidebar():
    proj = st.session_state.project

    st.sidebar.markdown("### 📋 Project Details")
    proj.client_name    = st.sidebar.text_input("Client Name",     value=proj.client_name    or "", placeholder="ABC Constructions")
    proj.project_name   = st.sidebar.text_input("Project Name",    value=proj.project_name   or "", placeholder="Multi-storey Building")
    proj.client_address = st.sidebar.text_area("Site Address",     value=proj.client_address or "", height=70, placeholder="City, State")
    proj.ipo_no         = st.sidebar.text_input("IPO / Enquiry No.", value=proj.ipo_no or "")
    proj.date           = st.sidebar.text_input("Date",            value=proj.date or str(date.today()))

    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚙️ Panel Configuration")

    ph_idx = PANEL_HEIGHTS.index(st.session_state.panel_height) \
             if st.session_state.panel_height in PANEL_HEIGHTS else 0
    st.session_state.panel_height = st.sidebar.selectbox(
        "Panel Height (mm)", PANEL_HEIGHTS, index=ph_idx)
    st.session_state.num_sets = st.sidebar.number_input(
        "No. of Sets", min_value=1, max_value=20, value=st.session_state.num_sets)

    # Apply to project
    proj.panel_height_mm = float(st.session_state.panel_height)
    proj.num_sets        = st.session_state.num_sets

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


# ══════════════════════════════════════════════════════════════════════════════
#  Tab 1 — Import / Add Elements
# ══════════════════════════════════════════════════════════════════════════════
def tab_import():
    st.markdown('<div class="section-title">📁 Import DXF Drawing or Add Elements Manually</div>',
                unsafe_allow_html=True)

    col_left, col_right = st.columns([1.15, 1])

    # ── DXF upload ──────────────────────────────────────────────────────────
    with col_left:
        st.markdown('<div class="nova-card"><h4>Upload DXF Drawing</h4>', unsafe_allow_html=True)
        dxf_file = st.file_uploader(
            "Drop your DXF file here",
            type=["dxf"],
            help="DWG files need conversion to DXF first (see guide below)"
        )
        if dxf_file and DXF_AVAILABLE:
            if st.button("🔍 Auto-Detect Elements from Drawing", use_container_width=True):
                with st.spinner("Parsing DXF drawing..."):
                    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
                        tmp.write(dxf_file.getvalue())
                        tmp_path = tmp.name
                    try:
                        detected = parse_dxf(tmp_path)
                        if detected:
                            st.session_state.elements   = detected
                            st.session_state.boq_result = None
                            st.session_state.edit_idx   = None
                            st.success(f"✅ Detected {len(detected)} elements from drawing!")
                        else:
                            st.warning("No structural elements detected. Try adding manually.")
                    except Exception as e:
                        st.error(f"Parse error: {e}")
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass
        elif dxf_file and not DXF_AVAILABLE:
            st.warning("ezdxf not installed — DXF parsing unavailable.")
        if not dxf_file:
            st.info("💡 Upload a DXF file to auto-detect columns, walls, and shear walls.")
        st.markdown('</div>', unsafe_allow_html=True)

        with st.expander("📌 How to convert DWG → DXF?"):
            st.markdown("""
**Option 1 — AutoCAD:**
File → Save As → format: DXF → Save

**Option 2 — ODA File Converter (Free):**
Download from opendesign.com → Select folders → Convert

**Option 3 — Online converter:**
Search "DWG to DXF online" — several free tools available.
            """)

    # ── Manual add form ────────────────────────────────────────────────────
    with col_right:
        st.markdown('<div class="nova-card"><h4>Add Element Manually</h4>', unsafe_allow_html=True)
        _add_element_form()
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Elements list with Edit / Delete ───────────────────────────────────
    _render_elements_list()


def _add_element_form():
    """New-element entry form."""
    with st.form("add_element_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            label     = st.text_input("Label *", placeholder="C1 / SW1 / W1")
            elem_type = st.selectbox("Type", ELEMENT_TYPES)
            length    = st.number_input("Length (mm)", min_value=50, max_value=50000, value=600, step=50)
            height    = st.number_input("Height (mm)", min_value=100, max_value=20000, value=3000, step=50)
        with c2:
            width     = st.number_input("Width / Thickness (mm)", min_value=50, max_value=5000, value=300, step=50)
            qty       = st.number_input("Quantity", min_value=1, max_value=500, value=1)
            junction  = st.selectbox("Junction (walls only)", JUNCTION_TYPES)
            floor_lbl = st.text_input("Floor Label", placeholder="GF / 1F / 2F")

        if st.form_submit_button("➕ Add Element", use_container_width=True):
            if not label.strip():
                st.error("Label is required.")
            else:
                st.session_state.elements.append(StructuralElement(
                    element_type  = ElementType(elem_type),
                    label         = label.strip().upper(),
                    length_mm     = float(length),
                    width_mm      = float(width),
                    height_mm     = float(height),
                    quantity      = int(qty),
                    junction_type = JunctionType(junction),
                    floor_label   = floor_lbl.strip(),
                ))
                st.session_state.boq_result = None
                st.success(f"Added: {label.strip().upper()}")


def _render_elements_list():
    """Show all elements with inline Edit and Delete buttons."""
    elements = st.session_state.elements
    if not elements:
        return

    st.markdown(
        f'<div class="section-title">📝 Elements ({len(elements)} total)</div>',
        unsafe_allow_html=True
    )

    # Clear all button
    col_hdr, col_clr = st.columns([7, 1])
    with col_clr:
        if st.button("🗑️ Clear All", use_container_width=True, key="clear_all"):
            st.session_state.elements   = []
            st.session_state.boq_result = None
            st.session_state.edit_idx   = None
            st.rerun()

    for i, elem in enumerate(elements):

        # ── Edit form (shown inline when this element is selected) ────────
        if st.session_state.edit_idx == i:
            _render_edit_form(i, elem)
            continue

        # ── Normal row display ─────────────────────────────────────────────
        junc_str  = f" · {elem.junction_type.value}" if elem.junction_type != JunctionType.NONE else ""
        floor_str = f" · Floor: {elem.floor_label}"  if elem.floor_label else ""

        col_info, col_edit, col_del = st.columns([7, 1, 1])
        with col_info:
            st.markdown(
                f"<div class='elem-row'>"
                f"<span class='elem-label'>{elem.label}</span>"
                f"&nbsp;<span class='elem-meta'>"
                f"{elem.element_type.value} &nbsp;·&nbsp; "
                f"{elem.length_mm:.0f} × {elem.width_mm:.0f} mm &nbsp;·&nbsp; "
                f"H = {elem.height_mm:.0f} mm &nbsp;·&nbsp; Qty {elem.quantity}"
                f"{junc_str}{floor_str}"
                f"</span></div>",
                unsafe_allow_html=True
            )
        with col_edit:
            if st.button("✏️", key=f"edit_{i}", help="Edit this element"):
                st.session_state.edit_idx = i
                st.rerun()
        with col_del:
            if st.button("🗑", key=f"del_{i}", help="Remove this element"):
                st.session_state.elements.pop(i)
                st.session_state.boq_result = None
                if st.session_state.edit_idx == i:
                    st.session_state.edit_idx = None
                st.rerun()


def _render_edit_form(idx: int, elem: StructuralElement):
    """Inline edit form for an existing element."""
    st.markdown('<div class="edit-active">', unsafe_allow_html=True)
    st.markdown(f"**✏️ Editing: {elem.label}**")

    with st.form(f"edit_form_{idx}"):
        c1, c2 = st.columns(2)
        with c1:
            new_label  = st.text_input("Label",   value=elem.label)
            new_type   = st.selectbox("Type",     ELEMENT_TYPES,
                                      index=ELEMENT_TYPES.index(elem.element_type.value))
            new_length = st.number_input("Length (mm)",  min_value=50,  max_value=50000,
                                         value=int(elem.length_mm),  step=50)
            new_height = st.number_input("Height (mm)",  min_value=100, max_value=20000,
                                         value=int(elem.height_mm),  step=50)
        with c2:
            new_width  = st.number_input("Width / Thickness (mm)", min_value=50, max_value=5000,
                                         value=int(elem.width_mm),  step=50)
            new_qty    = st.number_input("Quantity", min_value=1, max_value=500,
                                         value=elem.quantity)
            new_junc   = st.selectbox("Junction", JUNCTION_TYPES,
                                      index=JUNCTION_TYPES.index(elem.junction_type.value))
            new_floor  = st.text_input("Floor Label", value=elem.floor_label or "")

        col_save, col_cancel = st.columns(2)
        with col_save:
            save = st.form_submit_button("💾 Save Changes", use_container_width=True)
        with col_cancel:
            cancel = st.form_submit_button("✕ Cancel", use_container_width=True)

        if save:
            if not new_label.strip():
                st.error("Label is required.")
            else:
                st.session_state.elements[idx] = StructuralElement(
                    element_type  = ElementType(new_type),
                    label         = new_label.strip().upper(),
                    length_mm     = float(new_length),
                    width_mm      = float(new_width),
                    height_mm     = float(new_height),
                    quantity      = int(new_qty),
                    junction_type = JunctionType(new_junc),
                    floor_label   = new_floor.strip(),
                )
                st.session_state.boq_result = None
                st.session_state.edit_idx   = None
                st.rerun()

        if cancel:
            st.session_state.edit_idx = None
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Tab 2 — BOQ Results  (with pricing panel at top)
# ══════════════════════════════════════════════════════════════════════════════
def tab_boq():
    st.markdown('<div class="section-title">📊 Bill of Quantities</div>', unsafe_allow_html=True)

    if not st.session_state.elements:
        st.info("No elements added yet. Go to **Import / Add Elements** tab first.")
        return

    # ── Pricing panel ────────────────────────────────────────────────────────
    _render_pricing_panel()

    # ── Generate button ──────────────────────────────────────────────────────
    col_btn, _ = st.columns([1, 3])
    with col_btn:
        if st.button("⚡ Generate BOQ", use_container_width=True, key="gen_boq"):
            with st.spinner("Running panel optimization..."):
                _run_boq()

    if not st.session_state.boq_result:
        st.markdown(
            "<div class='warn-box'>Set your rates above then click <b>Generate BOQ</b>.</div>",
            unsafe_allow_html=True
        )
        return

    _render_boq_results()


def _render_pricing_panel():
    """Pricing inputs displayed prominently before Generate BOQ button."""
    proj = st.session_state.project

    st.markdown('<div class="pricing-card"><h4>💰 Pricing & Rates</h4>', unsafe_allow_html=True)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        new_rate = st.number_input(
            "Panel Rate (₹ / sqm)", min_value=0.0,
            value=float(st.session_state.panel_rate), step=100.0,
            key="price_rate", help="Rate charged per square metre of formwork panel area"
        )
        st.session_state.panel_rate  = new_rate
        proj.panel_rate_per_sqm      = new_rate
    with col2:
        new_freight = st.number_input(
            "Freight / Transport (₹)", min_value=0.0,
            value=float(st.session_state.freight), step=500.0,
            key="price_freight"
        )
        st.session_state.freight = new_freight
        proj.freight_amount      = new_freight
    with col3:
        new_gst = st.checkbox(
            "Include GST @ 18%", value=st.session_state.gst_enabled, key="price_gst"
        )
        st.session_state.gst_enabled = new_gst
        proj.gst_enabled             = new_gst
    with col4:
        if new_rate > 0:
            # Quick area preview from previous result
            if st.session_state.boq_result:
                area = st.session_state.boq_result['total_area_sqm']
                cost = area * new_rate
                gst  = cost * 0.18 if new_gst else 0
                st.metric("Estimated Total", f"₹{cost + gst + new_freight:,.0f}")
            else:
                st.info("Generate BOQ to see totals.")
        else:
            st.caption("Enter rate above to calculate cost.")

    st.markdown('</div>', unsafe_allow_html=True)


def _render_boq_results():
    """Show metrics and per-element breakdown after generation."""
    agg  = st.session_state.boq_result
    proj = st.session_state.project

    # Metrics
    c1, c2, c3, c4 = st.columns(4)
    has_rate = proj.panel_rate_per_sqm > 0
    for col, (lbl, val) in zip(
        [c1, c2, c3, c4],
        [
            ("Total Panel Area",  f"{agg['total_area_sqm']} m²"),
            ("Panel Cost",        f"₹{agg['total_panel_cost']:,.0f}" if has_rate else "—"),
            ("GST @ 18%",         f"₹{agg['gst_amount']:,.0f}"       if (has_rate and proj.gst_enabled) else "—"),
            ("Grand Total",       f"₹{agg['grand_total']:,.0f}"       if has_rate else "—"),
        ]
    ):
        with col:
            st.markdown(
                f"<div class='metric-box'>"
                f"<div class='val'>{val}</div>"
                f"<div class='lbl'>{lbl}</div>"
                f"</div>",
                unsafe_allow_html=True
            )

    st.markdown("")

    # Per-element breakdown
    st.markdown("#### Element-wise Panel Details")
    for eboq in proj.element_boqs:
        elem = eboq.element
        with st.expander(
            f"**{elem.label}** — {elem.element_type.value}  "
            f"{elem.length_mm:.0f}×{elem.width_mm:.0f} mm  "
            f"H={elem.height_mm:.0f} mm  (Qty {elem.quantity})",
            expanded=False
        ):
            for w in eboq.warnings:
                st.markdown(f"<div class='warn-box'>⚠️ {w}</div>", unsafe_allow_html=True)

            rows_html = "".join(
                f"<tr class='{'corner-row' if p.is_corner else ''}'>"
                f"<td>{p.size_label}</td>"
                f"<td style='text-align:right'>{p.quantity}</td>"
                f"<td style='text-align:right'>{p.area_sqm:.4f}</td>"
                f"<td style='text-align:right'>{p.total_area_sqm:.4f}</td>"
                f"<td>{'Corner (OC/IC)' if p.is_corner else 'Flat'}</td>"
                f"</tr>"
                for p in eboq.panels
            )
            st.markdown(f"""
            <table class='boq-table'>
              <thead><tr>
                <th>Panel Size</th>
                <th style='text-align:right'>Qty</th>
                <th style='text-align:right'>Unit Area m²</th>
                <th style='text-align:right'>Total Area m²</th>
                <th>Type</th>
              </tr></thead>
              <tbody>{rows_html}</tbody>
            </table>
            """, unsafe_allow_html=True)

            if eboq.spacer_mm > 0:
                st.caption(f"Spacer gap: {eboq.spacer_mm:.0f} mm")
            if eboq.height_note:
                st.caption(f"Achieved height: {eboq.height_note}")

    # Consolidated summary
    st.markdown("#### Consolidated Panel Summary")
    summary = agg['summary_panels']
    total_qty = total_area = 0
    rows_html = ""
    for size, d in summary.items():
        tag = " 🔶" if d['is_corner'] else ""
        rows_html += (
            f"<tr><td>{size}{tag}</td>"
            f"<td style='text-align:right'>{d['quantity']}</td>"
            f"<td style='text-align:right'>{d['area_sqm']:.3f}</td></tr>"
        )
        total_qty  += d['quantity']
        total_area += d['area_sqm']
    rows_html += (
        f"<tr style='font-weight:700;background:#e8f0fe'>"
        f"<td>TOTAL</td>"
        f"<td style='text-align:right'>{total_qty}</td>"
        f"<td style='text-align:right'>{total_area:.3f}</td></tr>"
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
        proj.element_boqs.append(compute_boq(elem, ph))
    st.session_state.boq_result = aggregate_project_boq(proj)
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  Tab 3 — Export
# ══════════════════════════════════════════════════════════════════════════════
def tab_export():
    st.markdown('<div class="section-title">📤 Export Quotation</div>', unsafe_allow_html=True)

    if not st.session_state.boq_result:
        st.info("Generate the BOQ first (go to **BOQ Results** tab).")
        return

    proj = st.session_state.project

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="nova-card"><h4>📄 PDF Quotation</h4>', unsafe_allow_html=True)
        st.markdown(
            "Nova-branded PDF with company logo, client info, element-wise panel tables, "
            "accessories, and cost breakdown with GST."
        )
        if st.button("Generate PDF", use_container_width=True, key="gen_pdf"):
            with st.spinner("Generating PDF..."):
                pdf_bytes = _generate_pdf_bytes(proj)
            fname = f"NovoForm_BOQ_{proj.client_name or 'Project'}.pdf"
            st.download_button(
                "⬇️ Download PDF",
                data=pdf_bytes, file_name=fname, mime="application/pdf",
                use_container_width=True, key="dl_pdf"
            )
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="nova-card"><h4>📊 Excel BOQ</h4>', unsafe_allow_html=True)
        st.markdown(
            "Excel in Nova's COLUMN sheet format (with logo in header) + "
            "a **Days BOQ** tab showing Day-1 / Day-2 / Day-3 panel deployment schedule."
        )
        if st.button("Generate Excel", use_container_width=True, key="gen_excel"):
            with st.spinner("Generating Excel..."):
                excel_bytes = _generate_excel_bytes(proj)
            fname = f"NovoForm_BOQ_{proj.client_name or 'Project'}.xlsx"
            st.download_button(
                "⬇️ Download Excel",
                data=excel_bytes, file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True, key="dl_excel"
            )
        st.markdown('</div>', unsafe_allow_html=True)

    # Summary of what's included
    st.markdown('<div class="nova-card"><h4>What\'s Included in Exports</h4>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
**PDF Quotation:**
- Nova Formworks logo in company header
- Client name, address, IPO no., date, panel height
- Per-element panel breakdown table
- Consolidated panel summary
- Accessories estimate (pins, wallers, tierods)
- Cost + GST + Freight = Grand Total
        """)
    with c2:
        st.markdown("""
**Excel BOQ:**
- Nova logo embedded in COLUMN sheet header
- Panel sizes, quantities, area per element
- Summary table with Grand Total formula
- **DAYS BOQ sheet** — Day-1 / Day-2 / Day-3 batches
- Colour-coded inventory deployment schedule
        """)
    st.markdown('</div>', unsafe_allow_html=True)


def _generate_pdf_bytes(proj: ProjectBOQ) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        generate_pdf(proj, float(st.session_state.panel_height), tmp_path)
        return open(tmp_path, "rb").read()
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
            proj, tmp_path,
            price_per_sqm  = proj.panel_rate_per_sqm,
            freight_amount = proj.freight_amount,
            gst_rate       = 0.18 if proj.gst_enabled else 0.0,
        )
        return open(tmp_path, "rb").read()
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
#  Tab 4 — About
# ══════════════════════════════════════════════════════════════════════════════
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

        st.markdown('<div class="nova-card"><h4>Panel Optimization Engine</h4>', unsafe_allow_html=True)
        st.markdown("""
- **Dynamic Programming (DP)** — finds exact panel widths summing to face dimension
- **Symmetric preference** — 500+500 over 600+400 for 1000 mm (matches Nova practice)
- **Standard widths** — 600, 500, 490, 440, 400, 350, 300, 275, 250, 240, 230, 200, 150, 125, 100, 40 mm
- **Spacer gap** up to 50 mm allowed when exact fit unavailable
- Verified against 6 real Nova Formworks client quotations
        """)
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="nova-card"><h4>Quick Start Guide</h4>', unsafe_allow_html=True)
        st.markdown("""
1. **Project details** — fill sidebar (client name, address, date)
2. **Add elements** — upload DXF or add manually
3. **Edit if needed** — ✏️ button on any element row
4. **Set pricing** — enter rate in the BOQ Results tab
5. **Generate BOQ** — one click runs panel optimization
6. **Export** — download PDF + Excel with Nova logo
        """)
        st.markdown('</div>', unsafe_allow_html=True)

        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=160)
            st.caption("Nova Formworks Pvt. Ltd.")

    st.markdown(
        "<div class='nova-footer'>"
        "NovoForm v2.0 &nbsp;|&nbsp; © 2026 Nova Formworks Pvt. Ltd. &nbsp;|&nbsp; "
        "Developed by <a href='https://rightleft.ai' target='_blank' "
        "style='color:#7a8aaa;text-decoration:underline'>RLAI</a>"
        "</div>",
        unsafe_allow_html=True
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════
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
