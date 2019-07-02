import unittest

import colours

HGRColours = colours.HGRColours


class TestColours(unittest.TestCase):

    def test_int28_to_pixels(self):
        self.assertEqual(
            (
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.DARK_BLUE,
                HGRColours.MED_BLUE,
                HGRColours.AQUA,
                HGRColours.AQUA,
                HGRColours.GREEN,
                HGRColours.BROWN,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
            ),
            colours.int34_to_nominal_colour_pixels(
                0b00000000000000000000111000000000, HGRColours
            )
        )

        self.assertEqual(
            (
                HGRColours.BLACK,
                HGRColours.MAGENTA,
                HGRColours.VIOLET,
                HGRColours.LIGHT_BLUE,
                HGRColours.WHITE,
                HGRColours.AQUA,
                HGRColours.GREEN,
                HGRColours.BROWN,
                HGRColours.BLACK,
                HGRColours.MAGENTA,
                HGRColours.VIOLET,
                HGRColours.LIGHT_BLUE,
                HGRColours.WHITE,
                HGRColours.AQUA,
                HGRColours.GREEN,
                HGRColours.BROWN,
                HGRColours.BLACK,
                HGRColours.MAGENTA,
                HGRColours.VIOLET,
                HGRColours.LIGHT_BLUE,
                HGRColours.WHITE,
                HGRColours.AQUA,
                HGRColours.GREEN,
                HGRColours.BROWN,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK,
                HGRColours.BLACK
            ),
            colours.int34_to_nominal_colour_pixels(
                0b0000111100001111000011110000, HGRColours
            )
        )


class TestRolRoR(unittest.TestCase):
    def testRolOne(self):
        self.assertEqual(0b1111, colours.rol(0b1111, 1))
        self.assertEqual(0b0001, colours.rol(0b1000, 1))
        self.assertEqual(0b1010, colours.rol(0b0101, 1))

    def testRolMany(self):
        self.assertEqual(0b1111, colours.rol(0b1111, 3))
        self.assertEqual(0b0010, colours.rol(0b1000, 2))
        self.assertEqual(0b0101, colours.rol(0b0101, 2))

    def testRorOne(self):
        self.assertEqual(0b1111, colours.ror(0b1111, 1))
        self.assertEqual(0b1000, colours.ror(0b0001, 1))
        self.assertEqual(0b0101, colours.ror(0b1010, 1))

    def testRoRMany(self):
        self.assertEqual(0b1111, colours.ror(0b1111, 3))
        self.assertEqual(0b1000, colours.ror(0b0010, 2))
        self.assertEqual(0b0101, colours.ror(0b0101, 2))


if __name__ == "__main__":
    unittest.main()
