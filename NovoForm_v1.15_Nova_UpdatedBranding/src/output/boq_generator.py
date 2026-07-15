"""
BOQ Generator: aggregates element BOQs into project-level summary.
"""
from collections import defaultdict
from src.models.element import ProjectBOQ, ElementBOQ, PanelEntry


def aggregate_project_boq(project: ProjectBOQ) -> dict:
    """
    Aggregate all element BOQs into a project summary.

    Returns a dict with:
      - element_boqs: list of ElementBOQ (for per-element display)
      - summary_panels: {size_label: {width, height, total_qty, total_area_sqm, price}}
      - total_area_sqm: float
      - total_panel_cost: float
      - gst_amount: float
      - grand_total: float
    """
    summary: dict[str, dict] = defaultdict(lambda: {
        'width_mm': 0, 'height_mm': 0,
        'quantity': 0, 'area_sqm': 0.0,
        'unit_area_sqm': 0.0, 'is_corner': False
    })

    rate = project.panel_rate_per_sqm
    n_sets = project.num_sets

    for eboq in project.element_boqs:
        elem_qty = eboq.element.quantity * n_sets
        for panel in eboq.panels:
            key = panel.size_label
            summary[key]['width_mm'] = panel.width_mm
            summary[key]['height_mm'] = panel.height_mm
            summary[key]['unit_area_sqm'] = panel.area_sqm
            summary[key]['is_corner'] = panel.is_corner
            summary[key]['quantity'] += panel.quantity * elem_qty
            summary[key]['area_sqm'] += panel.total_area_sqm * elem_qty

    # Compute costs
    total_area = sum(v['area_sqm'] for v in summary.values())
    total_panel_cost = total_area * rate

    gst = total_panel_cost * 0.18 if project.gst_enabled else 0.0
    freight = project.freight_amount
    grand_total = total_panel_cost + gst + freight

    # Sort: OC first, then by width desc
    def sort_key(kv):
        k, v = kv
        return (0 if v['is_corner'] else 1, -v['width_mm'])

    sorted_summary = dict(sorted(summary.items(), key=sort_key))

    return {
        'element_boqs': project.element_boqs,
        'summary_panels': sorted_summary,
        'total_area_sqm': round(total_area, 4),
        'total_panel_cost': round(total_panel_cost, 2),
        'gst_amount': round(gst, 2),
        'freight_amount': round(freight, 2),
        'grand_total': round(grand_total, 2),
        'num_sets': n_sets,
        'rate_per_sqm': rate,
    }
