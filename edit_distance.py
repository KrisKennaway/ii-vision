import functools

import numpy as np
import weighted_levenshtein


@functools.lru_cache(None)
def byte_to_colour_string(b: int, is_odd_offset: bool) -> str:
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
        pixels.append("01"[b & 0x40 != 0])
        idx += 1

    return "".join(pixels)


# TODO: what about increasing transposition cost?  Might be better to have
# any pixel at the right place even if the wrong colour?

substitute_costs = np.ones((128, 128), dtype=np.float64)
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
    a_pixels = byte_to_colour_string(a, is_odd_offset)
    b_pixels = byte_to_colour_string(b, is_odd_offset)

    dist = weighted_levenshtein.dam_lev(
        a_pixels, b_pixels,
        insert_costs=insert_costs,
        delete_costs=delete_costs,
        substitute_costs=error_substitute_costs if error else substitute_costs,
    )
    return np.int64(dist)


def edit_weight_matrixes(error: bool) -> np.array:
    ewm = np.zeros(shape=(256, 256, 2), dtype=np.int64)
    for a in range(256):
        for b in range(256):
            for is_odd_offset in (False, True):
                ewm[a, b, int(is_odd_offset)] = _edit_weight(
                    a, b, is_odd_offset, error)

    return ewm


_ewm = edit_weight_matrixes(False)
_error_ewm = edit_weight_matrixes(True)


@functools.lru_cache(None)
def edit_weight(a: int, b: int, is_odd_offset: bool, error: bool):
    e = _error_ewm if error else _ewm
    return e[a, b, int(is_odd_offset)]

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
def _content_a_array(content: int, shape) -> np.array:
    return (np.ones(shape, dtype=np.uint16) * content) << 8


def content_edit_weight(content: int, b: np.array) -> np.array:
    assert b.shape == (32, 256), b.shape

    # Extract even and off column offsets (128,)
    even_b = b[:, ::2]
    odd_b = b[:, 1::2]

    a = _content_a_array(content, even_b.shape)

    even = a + even_b
    odd = a + odd_b

    even_weights = np.vectorize(_even_error_ewm.__getitem__)(even)
    odd_weights = np.vectorize(_odd_error_ewm.__getitem__)(odd)

    res = np.ndarray(shape=b.shape, dtype=np.int64)
    res[:, ::2] = even_weights
    res[:, 1::2] = odd_weights

    return res


def array_edit_weight(a: np.array, b: np.array) -> np.array:
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
