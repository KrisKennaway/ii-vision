import colormath.color_objects
import colormath.color_diff
import colormath.color_conversions
import numpy as np

from colours import DHGRColours


def rgb(r, g, b):
    return colormath.color_objects.sRGBColor(r, g, b, is_upscaled=True)


# Palette RGB values taken from BMP2DHGR's default NTSC palette
# TODO: support other palettes as well, e.g. //gs RGB
palette = {
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


# Compute matrix of CIE2000 delta values for this palette, representing
# perceptual distance between colours.
diff_matrix = np.ndarray(shape=(16, 16), dtype=np.int)
for colour1, a in palette.items():
    alab = colormath.color_conversions.convert_color(
        a, colormath.color_objects.LabColor)
    for colour2, b in palette.items():
        blab = colormath.color_conversions.convert_color(
            b, colormath.color_objects.LabColor)
        diff_matrix[colour1.value, colour2.value] = int(
            colormath.color_diff.delta_e_cie2000(alab, blab))
