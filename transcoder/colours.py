"""Apple II nominal display colours, represented by 4-bit dot sequences.

These are distinct from the effective colours that are actually displayed,
e.g. due to white/black coalescing and NTSC artifacting.
"""

from typing import Tuple, Type

import enum
import functools


def ror(int4: int, howmany: int) -> int:
    """Rotate-right an int4 some number of times."""
    res = int4
    for _ in range(howmany):
        res = _ror(res)

    return res


def _ror(int4: int) -> int:
    return ((int4 & 0b1110) >> 1) ^ ((int4 & 0b0001) << 3)


def rol(int4: int, howmany: int) -> int:
    """Rotate-left an int4 some number of times."""
    res = int4
    for _ in range(howmany):
        res = _rol(res)

    return res


def _rol(int4: int) -> int:
    return ((int4 & 0b0111) << 1) ^ ((int4 & 0b1000) >> 3)


class NominalColours(enum.Enum):
    pass


class HGRColours(NominalColours):
    # Value is memory bit order, which is opposite to screen order (bits
    # ordered Left to Right on screen)
    BLACK = 0b0000
    MAGENTA = 0b0001
    BROWN = 0b1000
    ORANGE = 0b1001  # HGR colour
    DARK_GREEN = 0b0100
    GREY1 = 0b0101
    GREEN = 0b1100  # HGR colour
    YELLOW = 0b1101
    DARK_BLUE = 0b0010
    VIOLET = 0b0011  # HGR colour
    GREY2 = 0b1010
    PINK = 0b1011
    MED_BLUE = 0b0110  # HGR colour
    LIGHT_BLUE = 0b0111
    AQUA = 0b1110
    WHITE = 0b1111


class DHGRColours(NominalColours):
    # DHGR 4-bit memory representation is right-rotated from the HGR video
    # representation.
    BLACK = 0b0000
    MAGENTA = 0b1000
    BROWN = 0b0100
    ORANGE = 0b1100  # HGR colour
    DARK_GREEN = 0b0010
    GREY1 = 0b1010
    GREEN = 0b0110  # HGR colour
    YELLOW = 0b1110
    DARK_BLUE = 0b0001
    VIOLET = 0b1001  # HGR colour
    GREY2 = 0b0101
    PINK = 0b1101
    MED_BLUE = 0b0011  # HGR colour
    LIGHT_BLUE = 0b1011
    AQUA = 0b0111
    WHITE = 0b1111


# @functools.lru_cache(None)
# def int28_to_nominal_colour_pixels2(int28):
#     return tuple(
#         HGRColours(
#             (int28 & (0b1111 << (4 * i))) >> (4 * i)) for i in range(7)
#     )


@functools.lru_cache(None)
def int34_to_nominal_colour_pixels(
        int34: int,
        colours: Type[NominalColours],
        init_phase: int = 1  # Such that phase = 0 at start of 28-bit body
) -> Tuple[NominalColours]:
    """Produce sequence of 31 nominal colour pixels via sliding 4-bit window.

    Includes the 3-bit header that represents the trailing 3 bits of the
    previous 28-bit tuple.  i.e. storing a byte in aux even columns will also
    influence the colours of the previous main odd column.

    This naively models the NTSC colour artifacting.

    TODO: Use a more careful colour composition model to produce effective
    pixel colours.

    TODO: DHGR vs HGR colour differences can be modeled by changing init_phase
    """
    res = []

    shifted = int34
    phase = init_phase

    # Omit trailing 3 bits which are only there to provide a trailer for
    # bits 28..31
    for i in range(31):
        colour = rol(shifted & 0b1111, phase)
        res.append(colours(colour))

        shifted >>= 1
        phase += 1
        if phase == 4:
            phase = 0

    return tuple(res)


@functools.lru_cache(None)
def int34_to_nominal_colour_pixel_values(
        int34: int,
        colours: Type[NominalColours],
        init_phase: int = 1  # Such that phase = 0 at start of 28-bit body
) -> Tuple[int]:
    return tuple(p.value for p in int34_to_nominal_colour_pixels(
        int34, colours, init_phase
    ))

