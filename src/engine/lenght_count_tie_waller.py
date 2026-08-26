# ----------- For round up length-------------
import math


def _per_row_tie_count(length_mm: float, width_mm: float) -> int:
    """
    Wallers (and tierods) needed on each horizontal row.

    Rule:
      base  = 4   (one tie-point per corner/face side)
      extra = floor(length / 1200) + floor(width / 1200)
              (+1 for every full 1200 mm span in each dimension)
    """
    if length_mm > 2280:
        extra = int(4 + (length_mm//1100))
        return extra
    else:
        extra = int(length_mm // 1200) + int(width_mm // 1200)
        return (4 + extra)


def round_up_tie_length(tie_length: float, tie_width: float,) -> int | tuple[int, int]:
    """
    Examples:
    600  -> 600 + 720 = 1320 -> 1500
    400  -> 400 + 720 = 1120 -> 1200
    300  -> 300 + 720 = 1020 -> 1200
    Calculate the required tie-rod length.

    effective_len   = tie_length + 720
    effective_width = tie_width + 720

    If effective_len > 3000:
        Return only the rounded effective_width.

    If effective_len <= 3000:
        Return both rounded effective_len and effective_width.
    """

    effective_len = tie_length + 720
    effective_width = tie_width + 720

    standard_lengths = [1000,1200,1500,1800,2000,2500,3000]

    def round_up(value: float) -> int:
        for length in standard_lengths:
            if value <= length:
                return length

        # For values greater than 3000
        return math.ceil(value / 500) * 500

    if effective_len > 3000:
        # Only width is considered
        return None,round_up(effective_width)

    # Both dimensions are considered
    rounded_len = round_up(effective_len)
    rounded_width = round_up(effective_width)

    return rounded_len, rounded_width


def _per_row_count_waller(length_mm: float, width_mm: float,inner_length: float = 0, inner_width: float = 0) -> int:
    """
    Calculate wallers required per horizontal row.

    Effective length = wall length + 280 mm on each side.

    Every 3000 mm of effective length requires one additional
    waller per face.
    """
    waller_len_face = waller_width_face = inner_length_face = inner_width_face = 0
    if inner_width and inner_length:
        waller_len_face = int(max(1, (length_mm + 2999 + 280) // 3000))
        waller_width_face = int(max(1, (width_mm + 280 + 2999) // 3000))
        inner_length_face = int(max(1, (inner_length + 280 + 2999) // 3000))
        inner_width_face = int(max(1, (inner_width + 280 + 2999) // 3000))
        
    else:
        effective_length = length_mm + 560

        waller_len_face = int(max(1, (effective_length + 2999) // 3000))
        effective_width = width_mm + 560

        
        waller_width_face = int(max(1, (effective_width + 2999) // 3000))

    return waller_len_face, waller_width_face, inner_length_face, inner_width_face


def round_up_waller_length(lenght_width: float) -> int:
    """
    Effective running length (each side) = structure dimension + 80 mm (panel thickness) + 200 mm
    if effective_running_length >=3000 thnen it devide into two parts
    """
    runing_len_width = lenght_width + 560
    if runing_len_width > 3000:
        pass