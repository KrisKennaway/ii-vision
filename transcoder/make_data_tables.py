import bz2
import functools
import pickle
from typing import Iterable

import numpy as np
import weighted_levenshtein

import palette

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
def pixel_string(pixels: Iterable[palette.DHGRColours]) -> str:
    return "".join(pixel_char(p.value) for p in pixels)


@functools.lru_cache(None)
def pixels_influenced_by_byte_index(
        pixels: Iterable[palette.DHGRColours],
        idx: int) -> Iterable[palette.DHGRColours]:
    """Return subset of pixels that are influenced by given byte index (0..4)"""
    start, end = {
        0: (0, 1),
        1: (1, 3),
        2: (3, 5),
        3: (5, 6)
    }[idx]

    return pixels[start:end + 1]


# Don't even consider insertions and deletions into the string, they don't
# make sense for comparing pixel strings
insert_costs = np.ones(128, dtype=np.float64) * 100000
delete_costs = np.ones(128, dtype=np.float64) * 100000

# Smallest substitution value is ~20 from palette.diff_matrix, i.e.
# we always prefer to transpose 2 pixels rather than substituting colours.
transpose_costs = np.ones((128, 128), dtype=np.float64) * 10

substitute_costs = np.zeros((128, 128), dtype=np.float64)

# Substitution costs to use when evaluating other potential offsets at which
# to store a content byte.  We penalize more harshly for introducing
# errors that alter pixel colours, since these tend to be very
# noticeable as visual noise.
error_substitute_costs = np.zeros((128, 128), dtype=np.float64)


def make_substitute_costs():
    # Penalty for changing colour
    for i, c in enumerate(PIXEL_CHARS):
        for j, d in enumerate(PIXEL_CHARS):
            cost = palette.diff_matrix[i, j]
            substitute_costs[(ord(c), ord(d))] = cost  # / 20
            substitute_costs[(ord(d), ord(c))] = cost  # / 20
            error_substitute_costs[(ord(c), ord(d))] = 5 * cost  # / 4
            error_substitute_costs[(ord(d), ord(c))] = 5 * cost  # / 4


make_substitute_costs()


@functools.lru_cache(None)
def edit_distance(a, b, error: bool):
    res = weighted_levenshtein.dam_lev(
        a, b,

        insert_costs=insert_costs,
        delete_costs=delete_costs,
        substitute_costs=error_substitute_costs if error else substitute_costs,
    )

    assert res == 0 or (1 <= res < 2 ** 16), res
    return res


@functools.lru_cache(None)
def int28_to_pixels(int28):
    return tuple(
        palette.DHGRColours(
            (int28 & (0b1111 << (4 * i))) >> (4 * i)) for i in range(7)
    )


# TODO: these duplicates byte_mask32/byte_shift from DHGRBitmap

# Map n-bit int into 32-bit masked value
def map_int8_to_mask32_0(int8):
    assert 0 <= int8 < 2 ** 8, int8
    return int8


def map_int12_to_mask32_1(int12):
    assert 0 <= int12 < 2 ** 12, int12
    return int12 << 4


def map_int12_to_mask32_2(int12):
    assert 0 <= int12 < 2 ** 12, int12
    return int12 << 12


def map_int8_to_mask32_3(int8):
    assert 0 <= int8 < 2 ** 8, int8
    return int8 << 20


def make_edit_distance():
    edit = [
        np.zeros(shape=(2 ** 16), dtype=np.int16),
        np.zeros(shape=(2 ** 24), dtype=np.int16),
        np.zeros(shape=(2 ** 24), dtype=np.int16),
        np.zeros(shape=(2 ** 16), dtype=np.int16),
    ]

    for i in range(2 ** 8):
        print(i)
        for j in range(2 ** 8):
            pair = (i << 8) + j

            first = map_int8_to_mask32_0(i)
            second = map_int8_to_mask32_0(j)

            first_pixels = pixels_influenced_by_byte_index(
                pixel_string(int28_to_pixels(first)), 0)
            second_pixels = pixels_influenced_by_byte_index(
                pixel_string(int28_to_pixels(second)), 0)

            edit[0][pair] = edit_distance(first_pixels, second_pixels,
                                          error=False)

            first = map_int8_to_mask32_3(i)
            second = map_int8_to_mask32_3(j)

            first_pixels = pixels_influenced_by_byte_index(
                pixel_string(int28_to_pixels(first)), 3)
            second_pixels = pixels_influenced_by_byte_index(
                pixel_string(int28_to_pixels(second)), 3)

            edit[3][pair] = edit_distance(first_pixels, second_pixels,
                                          error=False)

    for i in range(2 ** 12):
        print(i)
        for j in range(2 ** 12):
            pair = (i << 12) + j

            first = map_int12_to_mask32_1(i)
            second = map_int12_to_mask32_1(j)

            first_pixels = pixels_influenced_by_byte_index(
                pixel_string(int28_to_pixels(first)), 1)
            second_pixels = pixels_influenced_by_byte_index(
                pixel_string(int28_to_pixels(second)), 1)

            edit[1][pair] = edit_distance(first_pixels, second_pixels,
                                          error=False)

            first = map_int12_to_mask32_2(i)
            second = map_int12_to_mask32_2(j)

            first_pixels = pixels_influenced_by_byte_index(
                pixel_string(int28_to_pixels(first)), 2)
            second_pixels = pixels_influenced_by_byte_index(
                pixel_string(int28_to_pixels(second)), 2)

            edit[2][pair] = edit_distance(first_pixels, second_pixels,
                                          error=False)

    return edit


def main():
    edit = make_edit_distance()

    # TODO: error distance matrices

    with bz2.open(
            "transcoder/edit_distance.pickle.bz2", "wb",
            compresslevel=9) as out:
        pickle.dump(
            edit, out, protocol=pickle.HIGHEST_PROTOCOL)


if __name__ == "__main__":
    main()
