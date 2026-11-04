# ----------- For round up length-------------
import math
from typing import Tuple

from collections import Counter
from typing import Tuple


def _get_tie_count_and_length(
    length_mm: float,
    width_mm: float,
    inner_length: float = 0,
    inner_width: float = 0,
    left_w: float = 0,
    right_w: float = 0,
) -> Tuple[int, dict[int, int]]:
    """
    Calculate total tie-rod count and tie-rod length distribution.

    Returns:
        Tuple containing:
            - total tie-rod count
            - dictionary of {tie_length: quantity}
    """

    def _get_length_distribution(
        required_length: int,
        count: int,
    ) -> Counter:
        """Split required length into maximum 3000 mm lengths."""
        distribution = Counter()

        if count <= 0:
            return distribution

        remaining = required_length

        for _ in range(count - 1):
            distribution[3000] += 1
            remaining -= 3000

        if remaining > 0:
            distribution[remaining] += 1

        return distribution

    # ---------------------------------------------------------
    # Case 1: Box-type element with inner dimensions
    # ---------------------------------------------------------
    if inner_length and inner_width:

        base_count = 5

        inner_length_count = int((inner_length -100) // 1100)
        inner_width_count = int((inner_width - 100) // 1100)

        required_inner_right_w = int((right_w + 720 + 499) // 500) * 500
        required_inner_left_w = int((left_w + 720 + 499) // 500) * 500

        # length_distribution_right = _get_length_distribution(
        #     required_inner_right_w,
        #     inner_length_count,
        # )

        # width_distribution_left = _get_length_distribution(
        #     required_inner_left_w,
        #     inner_width_count,
        # )

        total_count = (
            base_count
            + inner_length_count
            + inner_width_count
        )

        tie_length_distribution = Counter({
            500: base_count})
        if inner_length_count:
            tie_length_distribution[required_inner_right_w] = inner_length_count
        if inner_width_count:
            tie_length_distribution[required_inner_left_w] = inner_width_count

        # tie_length_distribution.update(length_distribution_right)
        # tie_length_distribution.update(width_distribution_left)

        return total_count, dict(tie_length_distribution)
    elif length_mm and width_mm and right_w and length_mm:
        base_count = 4
        length_count = int((length_mm -100) // 1100)
        width_count = int((width_mm - 100) // 1100)
        required_inner_right_w = int((right_w + 720 + 499) // 500) * 500
        required_inner_left_w = int((left_w + 720 + 499) // 500) * 500
        total_count = base_count + length_count + width_count
        if required_inner_left_w == required_inner_right_w:
            total_len_count = length_count + width_count
            tie_length_distribution = Counter({
                500: base_count,
                required_inner_right_w:total_len_count,})
        else:
            tie_length_distribution = Counter({
                        500: base_count})
            if length_count:
                tie_length_distribution[required_inner_right_w]= length_count
            if width_count:
                tie_length_distribution[required_inner_left_w]= width_count
        return total_count, dict(tie_length_distribution)
    # ---------------------------------------------------------
    # Case 2: Width greater than 2280 mm
    # ---------------------------------------------------------
    elif length_mm > 2280:

        base_count = 4

        additional_count = int((length_mm - 100) // 1100)

        required_length = int((width_mm + 720+ 499) // 500) * 500

        # length_distribution = _get_length_distribution(
        #     required_length,
        #     additional_count,
        # )

        total_count = base_count + additional_count

        tie_length_distribution = Counter({
            500: base_count})
        if additional_count:
            tie_length_distribution[required_length] = additional_count

        #tie_length_distribution.update(length_distribution)

        return total_count, dict(tie_length_distribution)

    # ---------------------------------------------------------
    # Case 3: Standard element
    # ---------------------------------------------------------
    else:

        #base_count = 4
        l_count = max(1, int((length_mm - 1 + 1200) // 1200))
        w_count = max(1, int((width_mm - 1 + 1200) // 1200))
        #print("this is count l & w ", l_count, w_count, length_mm, width_mm)

        length_count = max(1, int((length_mm) // 1200))
        width_count = max(1, int((width_mm) // 1200))

        required_length = int((length_mm + 720 + 499) // 500) * 500
        required_width = int((width_mm + 720 + 499) // 500) * 500

        length_distribution = _get_length_distribution(required_length,length_count,)

        width_distribution = _get_length_distribution(required_width,width_count,)

        if l_count == 2 and w_count == 2:
            l_count +=1
            w_count +=1
            for k,v in length_distribution.items():
                length_distribution[k] = (v * 2) +1
            for k,v in width_distribution.items():
                width_distribution[k] = (v * 2) +1
        elif l_count ==2:
            w_count = (w_count * 2) + 1
            for k,v in length_distribution.items():
                length_distribution[k] = (v * 2)
            for k,v in width_distribution.items():
                width_distribution[k] = (v * 2) +1
        elif w_count ==2:
            l_count = (l_count * 2) + 1
            for k,v in length_distribution.items():
                length_distribution[k] = (v * 2) + 1
            for k,v in width_distribution.items():
                width_distribution[k] = (v * 2)

        else:
            l_count = l_count * 2
            for k,v in length_distribution.items():
                length_distribution[k] = v * 2

            w_count = w_count * 2
            for k,v in width_distribution.items():
                width_distribution[k]= v * 2
        
    
        
        total_count = (l_count + w_count)

        tie_length_distribution = Counter()

        tie_length_distribution.update(length_distribution)
        tie_length_distribution.update(width_distribution)

        return total_count, dict(tie_length_distribution)


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


def _per_row_count_waller(length_mm: float, width_mm: float,inner_length: float = 0, inner_width: float = 0, 
                          left_w: float =0, right_w : float=0, total_vertices: list=[],) -> int:
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
    elif total_vertices:
        reslut_list=[]
        count = 0
        for vertic in total_vertices:
            count +=1
            valu = round(vertic)
            effective_vertic = valu + 100
            count_lengthv, wallers_lenv = _get_waller_count_and_lengths(effective_vertic)
            reslut_list.append({f"vertic{count}":[valu, count_lengthv, wallers_lenv]})
        return reslut_list
    else:
        effective_length = length_mm + 560
        count_length, wallers_len1 = _get_waller_count_and_lengths(effective_length)
        effective_width = width_mm + 560
        count_width, wallers_width2 = _get_waller_count_and_lengths(effective_width)
        return [{'effective_length':[length_mm, count_length, wallers_len1]},
                {'effective_width':[width_mm, count_width, wallers_width2]}]


