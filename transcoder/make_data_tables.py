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

# The DHGR display encodes 7 pixels across interleaved 4-byte sequences
# of AUX and MAIN memory, as follows:
#
#     PBBBAAAA PDDCCCCB PFEEEEDD PGGGGFFF
#     Aux N    Main N   Aux N+1  Main N+1  (N even)
#
# Where A..G are the pixels, and P represents the (unused) palette bit.
#
# This layout makes more sense when written as a (little-endian) 32-bit integer:
#
#     33222222222211111111110000000000 <- bit pos in uint32
#     10987654321098765432109876543210
#     PGGGGFFFPFEEEEDDPDDCCCCBPBBBAAAA
#
# i.e. apart from the palette bits this is a linear ordering of pixels,
# when read from LSB to MSB (i.e. right-to-left).  i.e. the screen layout order
# of bits is opposite to the usual binary representation ordering.
#
# If we now look at the effect of storing a byte in each of the 4
# byte-offset positions within this uint32,
#
#     PGGGGFFFPFEEEEDDPDDCCCCBPBBBAAAA
#     33333333222222221111111100000000
#
# We see that these byte offsets cause changes to the following pixels:
#
# 0: A B
# 1: B C D
# 2: D E F
# 3: F G
#
# i.e. DHGR byte stores to offsets 0 and 3 result in changing one 8-bit value
# (2 DHGR pixels) into another; offsets 1 and 3 result in changing one 12-bit
# value (3 DHGR pixels).
#
# We can simplify things by stripping out the palette bit and packing
# down to a 28-bit integer representation:
#
#     33222222222211111111110000000000 <- bit pos in uint32
#     10987654321098765432109876543210
#
#     0000GGGGFFFFEEEEDDDDCCCCBBBBAAAA <- pixel A..G
#         3210321032103210321032103210 <- bit pos in A..G pixel
#
#         3333333222222211111110000000 <- byte offset 0.3
#
# With this representation, we can precompute an edit distance for the
# pixel changes resulting from all possible DHGR byte stores.
#
# We further encode these (source, target) -> distance mappings by
# concatenating source and target into 16- or 24-bit values.  This is
# efficient to work with in the video transcoder.
#
# Since we are enumerating all such 16- or 24-bit values, these can be packed
# contiguously into an array whose index is the (source, target) pair and
# the value is the edit distance.

PIXEL_CHARS = "0123456789ABCDEF"


def pixel_char(i: int) -> str:
    return PIXEL_CHARS[i]


@functools.lru_cache(None)
def pixel_string(pixels: Iterable[int]) -> str:
    return "".join(pixel_char(p) for p in pixels)


class EditDistanceParams:
    # Don't even consider insertions and deletions into the string, they don't
    # make sense for comparing pixel strings
    insert_costs = np.ones(128, dtype=np.float64) * 100000
    delete_costs = np.ones(128, dtype=np.float64) * 100000

    # Smallest substitution value is ~20 from palette.diff_matrices, i.e.
    # we always prefer to transpose 2 pixels rather than substituting colours.
    transpose_costs = np.ones((128, 128), dtype=np.float64) * 10

    substitute_costs = np.zeros((128, 128), dtype=np.float64)

    # Substitution costs to use when evaluating other potential offsets at which
    # to store a content byte.  We penalize more harshly for introducing
    # errors that alter pixel colours, since these tend to be very
    # noticeable as visual noise.
    error_substitute_costs = np.zeros((128, 128), dtype=np.float64)


def compute_diff_matrix(pal: Type[palette.BasePalette]):
    # Compute matrix of CIE2000 delta values for this pal, representing
    # perceptual distance between colours.
    dm = np.ndarray(shape=(16, 16), dtype=np.int)

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
    edp = EditDistanceParams()

    diff_matrix = compute_diff_matrix(pal)

    # Penalty for changing colour
    for i, c in enumerate(PIXEL_CHARS):
        for j, d in enumerate(PIXEL_CHARS):
            cost = diff_matrix[i, j]
            edp.substitute_costs[(ord(c), ord(d))] = cost  # / 20
            edp.substitute_costs[(ord(d), ord(c))] = cost  # / 20
            edp.error_substitute_costs[(ord(c), ord(d))] = 5 * cost  # / 4
            edp.error_substitute_costs[(ord(d), ord(c))] = 5 * cost  # / 4

    return edp


def edit_distance(
        edp: EditDistanceParams,
        a: str,
        b: str,
        error: bool) -> np.float64:
    res = weighted_levenshtein.dam_lev(
        a, b,
        insert_costs=edp.insert_costs,
        delete_costs=edp.delete_costs,
        substitute_costs=(
            edp.error_substitute_costs if error else edp.substitute_costs),
    )

    assert res == 0 or (1 <= res < 2 ** 16), res
    return res


def compute_edit_distance(
        edp: EditDistanceParams,
        bitmap_cls: Type[screen.Bitmap],
        nominal_colours: Type[colours.NominalColours]
):
    bits = bitmap_cls.MASKED_BITS

    bitrange = np.uint64(2 ** bits)

    edit = []
    for _ in range(len(bitmap_cls.BYTE_MASKS)):
        edit.append(
            np.zeros(shape=np.uint64(bitrange * bitrange), dtype=np.uint16))

    # Matrix is symmetrical with zero diagonal so only need to compute upper
    # triangle
    bar = ProgressBar((bitrange * (bitrange - 1)) / 2, max_width=80)

    num_dots = bitmap_cls.HEADER_BITS + bitmap_cls.BODY_BITS

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
    dist = compute_edit_distance(edp, bitmap_cls, nominal_colours)
    data = "transcoder/data/%s_palette_%d_edit_distance.pickle.bz2" % (
        bitmap_cls.NAME, pal.ID.value)
    with bz2.open(data, "wb", compresslevel=9) as out:
        pickle.dump(dist, out, protocol=pickle.HIGHEST_PROTOCOL)


def main():
    for p in palette.PALETTES.values():
        print("Processing palette %s" % p)
        edp = compute_substitute_costs(p)

        # TODO: error distance matrices

        make_edit_distance(p, edp, screen.HGRBitmap, colours.HGRColours)
        make_edit_distance(p, edp, screen.DHGRBitmap, colours.DHGRColours)


if __name__ == "__main__":
    main()
