import enum
from typing import Dict, Type

import colormath.color_objects

from colours import DHGRColours

# Type annotation
RGB = colormath.color_objects.sRGBColor


def rgb(r, g, b):
    return RGB(r, g, b, is_upscaled=True)


class Palette(enum.Enum):
    """BMP2DHR palette numbers"""
    UNKNOWN = -1
    IIGS = 0
    NTSC = 5


class BasePalette:
    ID = Palette.UNKNOWN  # type: Palette

    # Palette RGB map
    RGB = {}  # type: Dict[DHGRColours: RGB]


class NTSCPalette(BasePalette):
    ID = Palette.NTSC

    # Palette RGB values taken from BMP2DHGR's default NTSC palette
    RGB = {
        DHGRColours.BLACK: rgb(0, 0, 0),
        DHGRColours.MAGENTA: rgb(148, 12, 125),
        DHGRColours.BROWN: rgb(99, 77, 0),
        DHGRColours.ORANGE: rgb(249, 86, 29),
        DHGRColours.DARK_GREEN: rgb(51, 111, 0),
        DHGRColours.GREY1: rgb(126, 126, 126),
        DHGRColours.GREEN: rgb(67, 200, 0),
        DHGRColours.YELLOW: rgb(221, 206, 23),
        DHGRColours.DARK_BLUE: rgb(32, 54, 212),
        DHGRColours.VIOLET: rgb(188, 55, 255),
        DHGRColours.GREY2: rgb(126, 126, 126),
        DHGRColours.PINK: rgb(255, 129, 236),
        DHGRColours.MED_BLUE: rgb(7, 168, 225),
        DHGRColours.LIGHT_BLUE: rgb(158, 172, 255),
        DHGRColours.AQUA: rgb(93, 248, 133),
        DHGRColours.WHITE: rgb(255, 255, 255)
    }


class IIGSPalette(BasePalette):
    ID = Palette.IIGS

    # Palette RGB values taken from BMP2DHGR's KEGS32 palette
    RGB = {
        DHGRColours.BLACK: rgb(0, 0, 0),
        DHGRColours.MAGENTA: rgb(221, 0, 51),
        DHGRColours.BROWN: rgb(136, 85, 34),
        DHGRColours.ORANGE: rgb(255, 102, 0),
        DHGRColours.DARK_GREEN: rgb(0, 119, 0),
        DHGRColours.GREY1: rgb(85, 85, 85),
        DHGRColours.GREEN: rgb(0, 221, 0),
        DHGRColours.YELLOW: rgb(255, 255, 0),
        DHGRColours.DARK_BLUE: rgb(0, 0, 153),
        DHGRColours.VIOLET: rgb(221, 0, 221),
        DHGRColours.GREY2: rgb(170, 170, 170),
        DHGRColours.PINK: rgb(255, 153, 136),
        DHGRColours.MED_BLUE: rgb(34, 34, 255),
        DHGRColours.LIGHT_BLUE: rgb(102, 170, 255),
        DHGRColours.AQUA: rgb(0, 255, 153),
        DHGRColours.WHITE: rgb(255, 255, 255)
    }


PALETTES = {
    Palette.IIGS: IIGSPalette,
    Palette.NTSC: NTSCPalette
}  # type: Dict[Palette, Type[BasePalette]]
