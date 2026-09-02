# ----------- For round up length-------------
import math
from typing import Tuple

def _per_row_tie_count(length_mm: float, width_mm: float) -> int:
    """
    Wallers (and tierods) needed on each horizontal row.

    Rule:
      base  = 4   (one tie-point per corner/face side)
      extra = floor(length / 1200) + floor(width / 1200)
              (+1 for every full 1200 mm span in each dimension)
        720 = (80+80+100+100) x2  = 2280 : 3000-720
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
        return [{'outter_cor_dia':500},{'inner_dia':round_up(effective_width)}]

    # Both dimensions are considered
    rounded_len = round_up(effective_len)
    rounded_width = round_up(effective_width)

    return [{'lenght_dia':rounded_len},{'width_dia': rounded_width}]



def _get_waller_count_and_lengths(
    effective_length: float
) -> Tuple[int, tuple[int, ...]]:
    """
    Calculate waller count and lengths.

    effective_length is the total length that needs
    to be covered by wallers.

    Count:
        ceil(effective_length / 3000)

    Length:
        Rounded UP to nearest 500 mm.
        Maximum individual waller length = 3000 mm.
    """

    # Count of wallers
    count = int(
        max(1, (effective_length + 2999) // 3000)
    )

    # Round total required length UP to nearest 500
    required_length = int(
        (effective_length + 499) // 500
    ) * 500

    # Split into waller lengths
    lengths = []
    remaining = required_length

    for _ in range(count - 1):
        lengths.append(3000)
        remaining -= 3000

    # Remaining length
    if remaining > 0:
        lengths.append(remaining)

    return count, tuple(lengths)


def _per_row_count_waller(length_mm: float, width_mm: float,inner_length: float = 0, inner_width: float = 0, left_w: float =0, right_w : float=0) -> int:
    """
    Calculate wallers required per horizontal row.

    Effective length = wall length + 280 mm on each side.

    Every 3000 mm of effective length requires one additional
    waller per face.
    """
    waller_len_face = waller_width_face = inner_length_face = inner_width_face = 0
    if inner_width and inner_length:
        waller_len_face = int(length_mm + 50)
        count_len1, waller_dia1 = _get_waller_count_and_lengths(waller_len_face) 
        waller_width_face = int(width_mm + 50)
        count_width2, waller_dia2 = _get_waller_count_and_lengths(waller_width_face) 
        inner_length_face = int(inner_length + 50)
        count_inner_len_face3, waller_dia3 = _get_waller_count_and_lengths(inner_length_face)
        inner_width_face = int(inner_width + 50)
        count_inner_width_face4, waller_dia4 = _get_waller_count_and_lengths(inner_width_face)
        left_w_face = int(left_w + 100)
        count_left_w5, waller_dia5 = _get_waller_count_and_lengths(left_w_face)
        right_w_face = int(right_w + 100)
        count_right_w6, waller_dia6 = _get_waller_count_and_lengths(right_w_face)
        return [{'waller_len_face':[length_mm, count_len1, waller_dia1]},
                {'waller_width_face':[width_mm, count_width2, waller_dia2]},
                {'inner_length_face':[inner_length, count_inner_len_face3, waller_dia3]},
                {'inner_width_face':[inner_width, count_inner_width_face4, waller_dia4]},
                {'left_w_face':[left_w, count_left_w5, waller_dia5]},
                {'right_w_face':[right_w, count_right_w6, waller_dia6]}]
    else:
        effective_length = length_mm + 560
        count_length, wallers_len1 = _get_waller_count_and_lengths(effective_length)
        effective_width = width_mm + 560
        count_width, wallers_width2 = _get_waller_count_and_lengths(effective_width)
        return [{'effective_length':[length_mm, count_length, wallers_len1]},
                {'effective_width':[width_mm, count_width, wallers_width2]}]


