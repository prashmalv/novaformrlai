"""
AI-assisted drawing reading.

A vision LLM looks at rendered tiles of a DXF and decides which closed shapes
are formwork elements (columns, shear walls, walls) and what their labels are.
Exact geometry always comes from the DXF itself, and panels are still computed
by src.engine.panel_optimizer.compute_boq -- the model never does the maths.
"""
