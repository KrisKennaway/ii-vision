"""Apple II logical display colours."""

import enum


class DHGRColours(enum.Enum):
    # Value is memory bit order, which is opposite to screen order (bits
    # ordered Left to Right on screen)
    BLACK = 0b0000
    MAGENTA = 0b1000
    BROWN = 0b0100
    ORANGE = 0b1100
    DARK_GREEN = 0b0010
    GREY1 = 0b1010
    GREEN = 0b0110
    YELLOW = 0b1110
    DARK_BLUE = 0b0001
    VIOLET = 0b1001
    GREY2 = 0b0101
    PINK = 0b1101
    MED_BLUE = 0b0011
    LIGHT_BLUE = 0b1011
    AQUA = 0b0111
    WHITE = 0b1111

