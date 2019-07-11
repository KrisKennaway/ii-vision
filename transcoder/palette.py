"""RGB palette values for rendering NominalColour pixels."""

import enum
from typing import Dict, Type

import colormath.color_objects

from colours import HGRColours

# Type annotation
RGB = colormath.color_objects.sRGBColor


def rgb(r, g, b):
    return RGB(r, g, b, is_upscaled=True)


class Palette(enum.Enum):
    """BMP2DHR palette numbers."""

    UNKNOWN = -1
    IIGS = 0
    NTSC = 5


class BasePalette:
    ID = Palette.UNKNOWN  # type: Palette

    # Palette RGB map
    RGB = {}  # type: Dict[HGRColours: RGB]


class NTSCPalette(BasePalette):
    ID = Palette.NTSC

    # Palette RGB values taken from BMP2DHGR's default NTSC palette
    RGB = {
        HGRColours.BLACK: rgb(0, 0, 0),
        HGRColours.MAGENTA: rgb(148, 12, 125),
        HGRColours.BROWN: rgb(99, 77, 0),
        HGRColours.ORANGE: rgb(249, 86, 29),
        HGRColours.DARK_GREEN: rgb(51, 111, 0),
        HGRColours.GREY1: rgb(126, 126, 126),
        HGRColours.GREEN: rgb(67, 200, 0),
        HGRColours.YELLOW: rgb(221, 206, 23),
        HGRColours.DARK_BLUE: rgb(32, 54, 212),
        HGRColours.VIOLET: rgb(188, 55, 255),
        HGRColours.GREY2: rgb(126, 126, 126),
        HGRColours.PINK: rgb(255, 129, 236),
        HGRColours.MED_BLUE: rgb(7, 168, 225),
        HGRColours.LIGHT_BLUE: rgb(158, 172, 255),
        HGRColours.AQUA: rgb(93, 248, 133),
        HGRColours.WHITE: rgb(255, 255, 255)
    }


class IIGSPalette(BasePalette):
    ID = Palette.IIGS

    # Palette RGB values taken from BMP2DHGR's KEGS32 palette
    RGB = {
        HGRColours.BLACK: rgb(0, 0, 0),
        HGRColours.MAGENTA: rgb(221, 0, 51),
        HGRColours.BROWN: rgb(136, 85, 34),
        HGRColours.ORANGE: rgb(255, 102, 0),
        HGRColours.DARK_GREEN: rgb(0, 119, 0),
        HGRColours.GREY1: rgb(85, 85, 85),
        HGRColours.GREEN: rgb(0, 221, 0),
        HGRColours.YELLOW: rgb(255, 255, 0),
        HGRColours.DARK_BLUE: rgb(0, 0, 153),
        HGRColours.VIOLET: rgb(221, 0, 221),
        HGRColours.GREY2: rgb(170, 170, 170),
        HGRColours.PINK: rgb(255, 153, 136),
        HGRColours.MED_BLUE: rgb(34, 34, 255),
        HGRColours.LIGHT_BLUE: rgb(102, 170, 255),
        HGRColours.AQUA: rgb(0, 255, 153),
        HGRColours.WHITE: rgb(255, 255, 255)
    }


PALETTES = {
    Palette.IIGS: IIGSPalette,
    Palette.NTSC: NTSCPalette
}  # type: Dict[Palette, Type[BasePalette]]
