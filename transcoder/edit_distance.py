"""Computes visual differences between screen image data.

This is the core of the video encoding, for three reasons:

- The edit distance between old and new frames is used to prioritize which
  screen bytes to send

- When deciding which other offset bytes to send along with a chosen screen
byte, we minimize the error introduced by sending this (probably non-optimal)
byte instead of the actual target screen byte.  This needs to account for the
colour artifacts introduced by this byte as well as weighting perceived
errors introduced (e.g. long runs of colour)

- The byte_screen_error_distance function is on the critical path of the encoding.
"""

import functools

import numpy as np
import weighted_levenshtein


@functools.lru_cache(None)
def byte_to_nominal_colour_string(b: int, is_odd_offset: bool) -> str:
    """Compute nominal pixel colours for a byte.

    This ignores any fringing/colour combining effects, as well as
    half-ignoring what happens to the colour pixel that crosses the byte
    boundary.

    A better implementation of this might be to consider neighbouring (even,
    odd) column bytes together since this will allow correctly colouring the
    split pixel in the middle.

    There are also even weirder colour artifacts that happen when
    neighbouring bytes have mismatched colour palettes, which also cross the
    odd/even boundary.  But these may not be worth worrying about.

    :param b: byte to encode
    :param is_odd_offset: whether byte is at an odd screen column
    :return: string encoding nominal colour of pixels in the byte, with "0"
      or "1" for the "hanging" bit that spans the neighbouring byte.
    """
    pixels = []

    idx = 0
    if is_odd_offset:
        pixels.append("01"[b & 0x01])
        idx += 1

    # K = black
    # G = green
    # V = violet
    # W = white
    palettes = (
        (
            "K",  # 0x00
            "V",  # 0x01
            "G",  # 0x10
            "W"  # 0x11
        ), (
            "K",  # 0x00
            "B",  # 0x01
            "O",  # 0x10
            "W"  # 0x11
        )
    )
    palette = palettes[(b & 0x80) != 0]

    for _ in range(3):
        pixel = palette[(b >> idx) & 0b11]
        pixels.append(pixel)
        idx += 2

    if not is_odd_offset:
        pixels.append("01"[(b & 0x40) != 0])
        idx += 1

    return "".join(pixels)


@functools.lru_cache(None)
def byte_to_colour_string_with_white_coalescing(
        b: int, is_odd_offset: bool) -> str:
    """Model the combining of neighbouring 1 bits to produce white.

    The output is a string of length 7 representing the 7 display dots that now
    have colour.

    Attempt to model the colour artifacting that consecutive runs of
    1 bits are coerced to white.  This isn't quite correct since:

    a) it doesn't operate across byte boundaries (see note on
    byte_to_nominal_colour_string)

    b) a sequence like WVV appears more like WWWVVV or WWVVVV rather than WWWKVV
    (at least on the //gs)

    It also ignores other colour fringing e.g. from NTSC artifacts.

    TODO: this needs more work.

    :param b:
    :param is_odd_offset:
    :return:
    """

    pixels = []

    fringing = {
        "1V": "WWK",  # 110
        "1W": "WWW",  # 111

        "1B": "WWB",  # 110

        "WV": "WWWK",  # 1110
        "WB": "WWWK",  # 1110

        "GV": "KWWK",  # 0110
        "OB": "KWWK",  # 0110

        "GW": "KWWW",  # 0111
        "OW": "KWWW",  # 0111

        "W1": "WWW",  # 111
        "G1": "KWW",  # 011
        "O1": "KWW",  # 011
    }

    nominal = byte_to_nominal_colour_string(b, is_odd_offset)
    for idx in range(3):
        pair = nominal[idx:idx + 2]
        effective = fringing.get(pair)
        if not effective:
            e = []
            if pair[0] in {"0", "1"}:
                e.append(pair[0])
            else:
                e.extend([pair[0], pair[0]])
            if pair[1] in {"0", "1"}:
                e.append(pair[1])
            else:
                e.extend([pair[1], pair[1]])
            effective = "".join(e)

        if pixels:
            pixels.append(effective[2:])
        else:
            pixels.append(effective)

    return "".join(pixels)


substitute_costs = np.ones((128, 128), dtype=np.float64)

# Substitution costs to use when evaluating other potential offsets at which
# to store a content byte.  We penalize more harshly for introducing
# errors that alter pixel colours, since these tend to be very
# noticeable as visual noise.
error_substitute_costs = np.ones((128, 128), dtype=np.float64)

# Penalty for turning on/off a black bit
for c in "01GVWOB":
    substitute_costs[(ord('K'), ord(c))] = 1
    substitute_costs[(ord(c), ord('K'))] = 1
    error_substitute_costs[(ord('K'), ord(c))] = 5
    error_substitute_costs[(ord(c), ord('K'))] = 5

# Penalty for changing colour
for c in "01GVWOB":
    for d in "01GVWOB":
        substitute_costs[(ord(c), ord(d))] = 1
        substitute_costs[(ord(d), ord(c))] = 1
        error_substitute_costs[(ord(c), ord(d))] = 5
        error_substitute_costs[(ord(d), ord(c))] = 5

insert_costs = np.ones(128, dtype=np.float64) * 1000
delete_costs = np.ones(128, dtype=np.float64) * 1000


def _edit_weight(a: int, b: int, is_odd_offset: bool, error: bool):
    """

    :param a:
    :param b:
    :param is_odd_offset:
    :param error:
    :return:
    """
    a_pixels = byte_to_colour_string_with_white_coalescing(a, is_odd_offset)
    b_pixels = byte_to_colour_string_with_white_coalescing(b, is_odd_offset)

    dist = weighted_levenshtein.dam_lev(
        a_pixels, b_pixels,
        insert_costs=insert_costs,
        delete_costs=delete_costs,
        substitute_costs=error_substitute_costs if error else substitute_costs,
    )
    return np.int64(dist)


@functools.lru_cache(None)
def _edit_weight_matrices(error: bool) -> np.array:
    """

    :param error:
    :return:
    """
    ewm = np.zeros(shape=(256, 256, 2), dtype=np.int64)
    for a in range(256):
        for b in range(256):
            for is_odd_offset in (False, True):
                ewm[a, b, int(is_odd_offset)] = _edit_weight(
                    a, b, is_odd_offset, error)

    return ewm


@functools.lru_cache(None)
def edit_weight(a: int, b: int, is_odd_offset: bool, error: bool):
    """

    :param a: first content value
    :param b: second content value
    :param is_odd_offset: whether this content byte is at an odd screen
        byte offset
    :param error: whether to compute error distance or edit distance
    :return: the corresponding distance value
    """
    return _edit_weight_matrices(error)[a, b, int(is_odd_offset)]


_even_ewm = {}
_odd_ewm = {}
_even_error_ewm = {}
_odd_error_ewm = {}
for a in range(256):
    for b in range(256):
        _even_ewm[(a << 8) + b] = edit_weight(a, b, False, False)
        _odd_ewm[(a << 8) + b] = edit_weight(a, b, True, False)

        _even_error_ewm[(a << 8) + b] = edit_weight(a, b, False, True)
        _odd_error_ewm[(a << 8) + b] = edit_weight(a, b, True, True)


@functools.lru_cache(None)
def _constant_array(content: int, shape) -> np.array:
    """

    :param content:
    :param shape:
    :return:
    """
    return np.ones(shape, dtype=np.uint16) * content


def byte_screen_error_distance(content: int, b: np.array) -> np.array:
    """

    :param content: byte for which to compute error distance
    :param b: np.array of size (32, 256) representing existing screen memory.
    :return: np.array of size (32, 256) representing error distance from
        content byte to each byte of b
    """
    assert b.shape == (32, 256), b.shape

    # Extract even and off column offsets (128,)
    even_b = b[:, ::2]
    odd_b = b[:, 1::2]

    a = _constant_array(content << 8, even_b.shape)

    even = a + even_b
    odd = a + odd_b

    even_weights = np.vectorize(_even_error_ewm.__getitem__)(even)
    odd_weights = np.vectorize(_odd_error_ewm.__getitem__)(odd)

    res = np.ndarray(shape=b.shape, dtype=np.int64)
    res[:, ::2] = even_weights
    res[:, 1::2] = odd_weights

    return res


def screen_edit_distance(a: np.array, b: np.array) -> np.array:
    """

    :param a:
    :param b:
    :return:
    """
    # Extract even and off column offsets (32, 128)
    even_a = a[:, ::2]
    odd_a = a[:, 1::2]

    even_b = b[:, ::2]
    odd_b = b[:, 1::2]

    even = (even_a.astype(np.uint16) << 8) + even_b
    odd = (odd_a.astype(np.uint16) << 8) + odd_b

    even_weights = np.vectorize(_even_ewm.__getitem__)(even)
    odd_weights = np.vectorize(_odd_ewm.__getitem__)(odd)

    res = np.ndarray(shape=a.shape, dtype=np.int64)
    res[:, ::2] = even_weights
    res[:, 1::2] = odd_weights

    return res
