from src.models.element import StructuralElement
from src.parsers.dwg_parser import dwg_to_dxf, parse_dxf




def parse_dwg(dwg_path: str,
              casting_height_mm: float = 3000,
              unit_override: str = None,
              temp_dir: str = None) -> tuple[list[StructuralElement], str | None]:
    """
    Parse a DWG file: convert to DXF then extract elements.

    Returns:
        (elements_list, error_message_or_None)
    """
    dxf_path = dwg_to_dxf(dwg_path, temp_dir)
    if not dxf_path:
        return [], (
            "Could not convert DWG to DXF.\n\n"
            "Please install LibreDWG:\n"
            "  /opt/homebrew/bin/brew install libredwg\n\n"
            "Or install ODA File Converter from:\n"
            "  https://www.opendesign.com/guestfiles/oda_file_converter\n\n"
            "Alternatively, manually export DXF from AutoCAD (File → Save As → DXF)."
        )

    try:
        elements = parse_dxf(dxf_path, casting_height_mm, unit_override)
        return elements, None
    except Exception as ex:
        return [], f"DXF parsing error: {ex}"
