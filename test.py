# # # import math
# # # from typing import Tuple


# # # def _get_tie_count_and_length(
# # #     length_mm: float, width_mm: float,inner_length: float = 0, inner_width: float = 0, left_w: float =0, right_w : float=0
# # # ) -> Tuple[float, int, int | tuple[int, int]]:
# # #     """
# # #     Calculate actual dimension, tie-rod count and tie-rod length.

# # #     Rules
# # #     -----
# # #     Tie count:
# # #         - Base = 4
# # #         - If length <= 2280:
# # #             extra = floor(length / 1200) + floor(width / 1200)
# # #         - If length > 2280:
# # #             count = 4 + floor(length / 1100)
# # #     Tie length:
# # #         Effective dimension = actual dimension + 720 mm.
# # #         Standard tie-rod lengths:
# # #             1000, 1200, 1500, 1800, 2000, 2500, 3000
# # #         If effective length > 3000:
# # #             only width is used for tie length:
# # #                 outer = 500
# # #                 inner = rounded width
# # #         Otherwise:
# # #             both length and width are returned.
# # #     """
# # #     # --------------------------------------------------
# # #     # Standard tie-rod lengths
# # #     # --------------------------------------------------

# # #     standard_lengths = [1000,1200,1500,1800,2000,2500,3000]

# # #     def round_up(value: float) -> int:
# # #         for length in standard_lengths:
# # #             if value <= length:
# # #                 return length

# # #         # Greater than 3000
# # #         return math.ceil(value / 500) * 500

# # #     # --------------------------------------------------
# # #     # Calculate tie-rod count
# # #     # --------------------------------------------------
# # #     if inner_length and inner_width:
# # #         count1 = 5
# # #         count2 = (inner_length // 1100) 
# # #         leftt_w_tie_dia = round_up(left_w + 720)
# # #         count3 = (inner_width//1100)
# # #         right_w_tie_dia = round_up(right_w + 720)
# # #         total_count= count1 + count2 + count3
# # #         length_dia = {'500':count1,leftt_w_tie_dia:count2, right_w_tie_dia:count3}
# # #         return (total_count, length_dia)

# # #     elif width_mm > 2280:
# # #         count1 = 4
# # #         count2 = (length_mm // 1100)
# # #         length_tie_dia = round_up(width_mm + 720)
# # #         total_count1 = count1 + count2
# # #         tie_length_dia = {'500':count1,length_tie_dia: count2}
# # #         return (total_count1,tie_length_dia)
# # #     else:
# # #         count1 = 4
# # #         count2 =  int(length_mm // 1200)
# # #         length_tie_dia = round_up(length_mm + 720)
# # #         count3 = int(width_mm // 1200)
# # #         width_tie_dia = round_up(width_mm + 720)
# # #         total_count = count1 + count2 + count3
# # #         tie_width_dia = {'500': count1, length_tie_dia:count2, width_tie_dia:count3}
# # #         return (total_count, tie_width_dia)








# # import math
# # from typing import Tuple


# # def _get_tie_count_and_length(
# #     length_mm: float,
# #     width_mm: float,
# #     inner_length: float = 0,
# #     inner_width: float = 0,
# #     left_w: float = 0,
# #     right_w: float = 0,
# # ) -> Tuple[int, dict[int, int]]:
# #     """
# #     Calculate the total tie-rod count and tie-rod length distribution.

# #     Parameters
# #     ----------
# #     length_mm : float
# #         Outer length of the element in millimetres.

# #     width_mm : float
# #         Outer width of the element in millimetres.

# #     inner_length : float, optional
# #         Inner length of the element. Used for L-type elements.

# #     inner_width : float, optional
# #         Inner width of the element. Used for L-type elements.

# #     left_w : float, optional
# #         Left-side wall width in millimetres.

# #     right_w : float, optional
# #         Right-side wall width in millimetres.

# #     Returns
# #     -------
# #     Tuple[int, dict[int, int]]
# #         A tuple containing:

# #         - Total number of tie rods.
# #         - Dictionary mapping tie-rod length (mm) to quantity.

# #     Tie-rod count rules
# #     -------------------
# #     1. If both ``inner_length`` and ``inner_width`` are provided:
# #         - Base count = 5
# #         - Additional count = floor(inner_length / 1100)
# #         - Additional count = floor(inner_width / 1100)

# #     2. If ``width_mm > 2280``:
# #         - Base count = 4
# #         - Additional count = floor(length_mm / 1100)

# #     3. Otherwise:
# #         - Base count = 4
# #         - Additional count = floor(length_mm / 1200)
# #         - Additional count = floor(width_mm / 1200)

# #     Tie-rod length rules
# #     --------------------
# #     Effective dimension = actual dimension + 720 mm.

# #     Standard tie-rod lengths are:

# #         1000, 1200, 1500, 1800, 2000, 2500, 3000 mm

# #     If the effective dimension exceeds 3000 mm, the value is
# #     rounded up to the nearest 500 mm.
# #     """

# #     standard_lengths = [1000, 1200, 1500, 1800, 2000, 2500, 3000]

# #     def round_up_tie_length(value: float) -> int:
# #         """Round a tie-rod length up to the next standard length."""
# #         for standard_length in standard_lengths:
# #             if value <= standard_length:
# #                 return standard_length

# #         # For values greater than 3000 mm, round up to the
# #         # nearest 500 mm.
# #         return math.ceil(value / 500) * 500

# #     # ---------------------------------------------------------
# #     # Case 1: Box-type element with inner dimensions
# #     # ---------------------------------------------------------
# #     if inner_length and inner_width:
# #         base_count = 5

# #         inner_length_count = int(inner_length // 1100)
# #         inner_width_count = int(inner_width // 1100)

# #         left_tie_length = round_up_tie_length(left_w + 720)
# #         right_tie_length = round_up_tie_length(right_w + 720)

# #         total_count = (
# #             base_count
# #             + inner_length_count
# #             + inner_width_count
# #         )

# #         tie_length_distribution = {
# #             500: base_count,
# #             left_tie_length: inner_length_count,
# #             right_tie_length: inner_width_count,
# #         }

# #         return total_count, tie_length_distribution

# #     # ---------------------------------------------------------
# #     # Case 2: Width greater than 2280 mm
# #     # ---------------------------------------------------------
# #     elif width_mm > 2280:
# #         base_count = 4
# #         additional_count = int(length_mm // 1100)

# #         tie_length = round_up_tie_length(width_mm + 720)

# #         total_count = base_count + additional_count

# #         tie_length_distribution = {
# #             500: base_count,
# #             tie_length: additional_count,
# #         }

# #         return total_count, tie_length_distribution

# #     # ---------------------------------------------------------
# #     # Case 3: Standard element
# #     # ---------------------------------------------------------
# #     else:
# #         base_count = 4

# #         length_count = int(length_mm // 1200)
# #         width_count = int(width_mm // 1200)

# #         length_tie_length = round_up_tie_length(length_mm + 720)
# #         width_tie_length = round_up_tie_length(width_mm + 720)

# #         total_count = (
# #             base_count
# #             + length_count
# #             + width_count
# #         )

# #         tie_length_distribution = {
# #             500: base_count,
# #             length_tie_length: length_count,
# #             width_tie_length: width_count,
# #         }

# #         return total_count, tie_length_distribution
# # count, dime= _get_tie_count_and_length(1500, 1800)
# # print(count, dime)

# lst1= [300, 500]
# lst2 = [400, 600]
# print(min(lst1), max(lst2))

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
    Calculate the total tie-rod count and tie-rod length distribution.
    """

    standard_lengths = [1000, 1200, 1500, 1800, 2000, 2500, 3000]

    def get_tie_lengths(effective_length: float) -> list[int]:
        """
        Convert effective tie-rod length into one or more standard lengths.

        If effective length <= 3000:
            Use the next standard tie-rod length.

        If effective length > 3000:
            Round total required length UP to nearest 500 mm
            and split it into 3000 mm rods plus the remaining length.
        """

        # -----------------------------------------------------
        # Case 1: Length is within standard tie-rod range
        # -----------------------------------------------------
        if effective_length <= 3000:
            for standard_length in standard_lengths:
                if effective_length <= standard_length:
                    return [standard_length]

        # -----------------------------------------------------
        # Case 2: Length exceeds 3000 mm
        # -----------------------------------------------------

        # Round total required length UP to nearest 500
        required_length = int(
            (effective_length + 499) // 500
        ) * 500

        lengths = []
        remaining = required_length

        # Add 3000 mm rods first
        while remaining > 3000:
            lengths.append(3000)
            remaining -= 3000

        # Add remaining length
        if remaining > 0:
            lengths.append(remaining)

        return lengths

    def add_lengths_to_distribution(
        distribution: dict[int, int],
        lengths: list[int],
        count: int,
    ):
        """
        Add tie-rod lengths to the distribution for the given count.
        """
        for _ in range(count):
            for tie_length in lengths:
                distribution[tie_length] = (
                    distribution.get(tie_length, 0) + 1
                )

    # ---------------------------------------------------------
    # Case 1: Box-type element with inner dimensions
    # ---------------------------------------------------------
    if inner_length and inner_width:
        base_count = 5

        inner_length_count = int(inner_length // 1100)
        inner_width_count = int(inner_width // 1100)

        left_lengths = get_tie_lengths(left_w + 720)
        right_lengths = get_tie_lengths(right_w + 720)

        total_count = (
            base_count
            + inner_length_count
            + inner_width_count
        )

        tie_length_distribution = {
            500: base_count
        }

        add_lengths_to_distribution(
            tie_length_distribution,
            left_lengths,
            inner_length_count,
        )

        add_lengths_to_distribution(
            tie_length_distribution,
            right_lengths,
            inner_width_count,
        )

        return total_count, tie_length_distribution

    # ---------------------------------------------------------
    # Case 2: Width greater than 2280 mm
    # ---------------------------------------------------------
    elif width_mm > 2280:
        base_count = 4
        additional_count = int(length_mm // 1100)

        tie_lengths = get_tie_lengths(width_mm + 720)

        total_count = base_count + additional_count

        tie_length_distribution = {
            500: base_count
        }

        add_lengths_to_distribution(
            tie_length_distribution,
            tie_lengths,
            additional_count,
        )

        return total_count, tie_length_distribution

    # ---------------------------------------------------------
    # Case 3: Standard element
    # ---------------------------------------------------------
    else:
        base_count = 4

        length_count = int(length_mm // 1200)
        width_count = int(width_mm // 1200)

        length_tie_lengths = get_tie_lengths(length_mm + 720)
        width_tie_lengths = get_tie_lengths(width_mm + 720)

        total_count = (
            base_count
            + length_count
            + width_count
        )

        tie_length_distribution = {
            500: base_count
        }

        add_lengths_to_distribution(
            tie_length_distribution,
            length_tie_lengths,
            length_count,
        )

        add_lengths_to_distribution(
            tie_length_distribution,
            width_tie_lengths,
            width_count,
        )

        return total_count, tie_length_distribution
result = _get_tie_count_and_length(3500,70)
print(result)