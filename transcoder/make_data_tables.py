import bz2
import functools
import pickle
import sys
from typing import Iterable, Type

import colormath.color_conversions
import colormath.color_diff
import colormath.color_objects
import numpy as np
import weighted_levenshtein
from etaprogress.progress import ProgressBar

import colours
import palette
import screen


PIXEL_CHARS = "0123456789ABCDEF"


def pixel_char(i: int) -> str:
    return PIXEL_CHARS[i]


@functools.lru_cache(None)
def pixel_string(pixels: Iterable[int]) -> str:
    return "".join(pixel_char(p) for p in pixels)


class EditDistanceParams:
    """Data class for parameters to Damerau-Levenshtein edit distance."""

    # Don't even consider insertions and deletions into the string, they don't
    # make sense for comparing pixel strings
    insert_costs = np.ones(128, dtype=np.float64) * 100000
    delete_costs = np.ones(128, dtype=np.float64) * 100000

    # Smallest substitution value is ~20 from palette.diff_matrices, i.e.
    # we always prefer to transpose 2 pixels rather than substituting colours.
    # TODO: is quality really better allowing transposes?
    transpose_costs = np.ones((128, 128), dtype=np.float64) * 100000  # 10

    # These will be filled in later
    substitute_costs = np.zeros((128, 128), dtype=np.float64)

    # Substitution costs to use when evaluating other potential offsets at which
    # to store a content byte.  We penalize more harshly for introducing
    # errors that alter pixel colours, since these tend to be very
    # noticeable as visual noise.
    #
    # TODO: currently unused
    error_substitute_costs = np.zeros((128, 128), dtype=np.float64)


def compute_diff_matrix(pal: Type[palette.BasePalette]):
    """Compute matrix of perceptual distance between colour pairs.

    Specifically CIE2000 delta values for this palette.
    """
    dm = np.ndarray(shape=(16, 16), dtype=np.int32)

    for colour1, a in pal.RGB.items():
        alab = colormath.color_conversions.convert_color(
            a, colormath.color_objects.LabColor)
        for colour2, b in pal.RGB.items():
            blab = colormath.color_conversions.convert_color(
                b, colormath.color_objects.LabColor)
            dm[colour1.value, colour2.value] = int(
                colormath.color_diff.delta_e_cie2000(alab, blab))
    return dm


def compute_substitute_costs(pal: Type[palette.BasePalette]):
    """Compute costs for substituting one colour pixel for another."""

    edp = EditDistanceParams()

    diff_matrix = compute_diff_matrix(pal)

    # Penalty for changing colour
    for i, c in enumerate(PIXEL_CHARS):
        for j, d in enumerate(PIXEL_CHARS):
            cost = diff_matrix[i, j]
            edp.substitute_costs[(ord(c), ord(d))] = cost
            edp.substitute_costs[(ord(d), ord(c))] = cost
            edp.error_substitute_costs[(ord(c), ord(d))] = 5 * cost
            edp.error_substitute_costs[(ord(d), ord(c))] = 5 * cost

    return edp


def edit_distance(
        edp: EditDistanceParams,
        a: str,
        b: str,
        error: bool) -> np.float64:
    """Damerau-Levenshtein edit distance between two pixel strings."""
    res = weighted_levenshtein.dam_lev(
        a, b,
        insert_costs=edp.insert_costs,
        delete_costs=edp.delete_costs,
        substitute_costs=(
            edp.error_substitute_costs if error else edp.substitute_costs),
    )

    # Make sure result can fit in a uint16
    assert (0 <= res < 2 ** 16), res
    return res


def compute_edit_distance(
        edp: EditDistanceParams,
        bitmap_cls: Type[screen.Bitmap],
        nominal_colours: Type[colours.NominalColours]
):
    """Computes edit distance matrix between all pairs of pixel strings.

    Enumerates all possible values of the masked bit representation from
    bitmap_cls (assuming it is contiguous, i.e. we enumerate all
    2**bitmap_cls.MASKED_BITS values).  These are mapped to the dot
    representation, turned into coloured pixel strings, and we compute the
    edit distance.

    The effect of this is that we precompute the effect of storing all possible
    byte values against all possible screen backgrounds (e.g. as
    influencing/influenced by neighbouring bytes).
    """

    bits = bitmap_cls.MASKED_BITS

    bitrange = np.uint64(2 ** bits)

    edit = []
    for _ in range(len(bitmap_cls.BYTE_MASKS)):
        edit.append(
            np.zeros(shape=np.uint64(bitrange * bitrange), dtype=np.uint16))

    # Matrix is symmetrical with zero diagonal so only need to compute upper
    # triangle
    bar = ProgressBar((bitrange * (bitrange - 1)) / 2, max_width=80)

    num_dots = bitmap_cls.MASKED_DOTS

    cnt = 0
    for i in range(np.uint64(bitrange)):
        for j in range(i):
            cnt += 1

            if cnt % 10000 == 0:
                bar.numerator = cnt
                print(bar, end='\r')
                sys.stdout.flush()

            pair = (np.uint64(i) << bits) + np.uint64(j)

            for o, ph in enumerate(bitmap_cls.PHASES):
                first_dots = bitmap_cls.to_dots(i, byte_offset=o)
                second_dots = bitmap_cls.to_dots(j, byte_offset=o)

                first_pixels = pixel_string(
                    colours.dots_to_nominal_colour_pixel_values(
                        num_dots, first_dots, nominal_colours,
                        init_phase=ph)
                )
                second_pixels = pixel_string(
                    colours.dots_to_nominal_colour_pixel_values(
                        num_dots, second_dots, nominal_colours,
                        init_phase=ph)
                )
                edit[o][pair] = edit_distance(
                    edp, first_pixels, second_pixels, error=False)

    return edit


def make_edit_distance(
        pal: Type[palette.BasePalette],
        edp: EditDistanceParams,
        bitmap_cls: Type[screen.Bitmap],
        nominal_colours: Type[colours.NominalColours]
):
    """Write file containing (D)HGR edit distance matrix for a palette."""

    dist = compute_edit_distance(edp, bitmap_cls, nominal_colours)
    data = "transcoder/data/%s_palette_%d_edit_distance.pickle.bz2" % (
        bitmap_cls.NAME, pal.ID.value)
    with bz2.open(data, "wb", compresslevel=9) as out:
        pickle.dump(dist, out, protocol=pickle.HIGHEST_PROTOCOL)


def main():
    for p in palette.PALETTES.values():
        print("Processing palette %s" % p)
        edp = compute_substitute_costs(p)

        # TODO: still worth using error distance matrices?

        make_edit_distance(p, edp, screen.HGRBitmap, colours.HGRColours)
        make_edit_distance(p, edp, screen.DHGRBitmap, colours.DHGRColours)


if __name__ == "__main__":
    main()
