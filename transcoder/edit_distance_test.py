"""Tests for the edit_distance module."""

import unittest

import edit_distance


class TestByteToNominalColourString(unittest.TestCase):
    def testEncoding(self):
        self.assertEqual(
            "KKK0",
            edit_distance.byte_to_nominal_colour_string(
                0, is_odd_offset=False))
        self.assertEqual(
            "0KKK",
            edit_distance.byte_to_nominal_colour_string(
                0, is_odd_offset=True))

        self.assertEqual(
            "WWW1", edit_distance.byte_to_nominal_colour_string(
                0xff, is_odd_offset=False))
        self.assertEqual(
            "1WWW", edit_distance.byte_to_nominal_colour_string(
                0xff, is_odd_offset=True))

        self.assertEqual(
            "GGG0", edit_distance.byte_to_nominal_colour_string(
                0x2a, is_odd_offset=False))
        self.assertEqual(
            "1GGG", edit_distance.byte_to_nominal_colour_string(
                0x55, is_odd_offset=True))

        self.assertEqual(
            "OOO0", edit_distance.byte_to_nominal_colour_string(
                0xaa, is_odd_offset=False))
        self.assertEqual(
            "1OOO", edit_distance.byte_to_nominal_colour_string(
                0xd5, is_odd_offset=True))


class TestEditWeight(unittest.TestCase):
    def testTransposition(self):
        self.assertEqual("WKK0", edit_distance.byte_to_nominal_colour_string(
            0b00000011, is_odd_offset=False))
        self.assertEqual("KWK0", edit_distance.byte_to_nominal_colour_string(
            0b00001100, is_odd_offset=False))
        self.assertEqual(
            1, edit_distance.edit_weight(0b00000011, 0b00001100,
                                         is_odd_offset=False)
        )

        self.assertEqual("OWK1", edit_distance.byte_to_nominal_colour_string(
            0b11001110, is_odd_offset=False))
        self.assertEqual("OKW1", edit_distance.byte_to_nominal_colour_string(
            0b11110010, is_odd_offset=False))
        self.assertEqual(
            1, edit_distance.edit_weight(
                0b11001110, 0b11110010, is_odd_offset=False)
        )

    def testSubstitution(self):
        # Black has cost 5
        self.assertEqual("WKK0", edit_distance.byte_to_nominal_colour_string(
            0b00000011, is_odd_offset=False))
        self.assertEqual("KKK0", edit_distance.byte_to_nominal_colour_string(
            0b00000000, is_odd_offset=False))
        self.assertEqual(
            5, edit_distance.edit_weight(
                0b00000011, 0b00000000, is_odd_offset=False)
        )
        self.assertEqual(
            5, edit_distance.edit_weight(
                0b00000000, 0b00000011, is_odd_offset=False)
        )

        # Other colour has cost 1
        self.assertEqual(
            1, edit_distance.edit_weight(
                0b00000010, 0b00000011, is_odd_offset=False)
        )
        self.assertEqual(
            1, edit_distance.edit_weight(
                0b00000011, 0b00000010, is_odd_offset=False)
        )


if __name__ == '__main__':
    unittest.main()
