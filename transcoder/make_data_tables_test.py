import unittest

from colours import HGRColours
import make_data_tables


class TestMakeDataTables(unittest.TestCase):
    def test_pixel_string(self):
        pixels = (HGRColours.BLACK, HGRColours.WHITE, HGRColours.ORANGE)
        self.assertEqual("0FC", make_data_tables.pixel_string(pixels))

    def test_pixels_influenced_by_byte_index(self):
        pixels = "CB00000"
        self.assertEqual(
            "CB",
            make_data_tables.pixels_influenced_by_byte_index(pixels, 0)
        )

        pixels = "CBA9000"
        self.assertEqual(
            "BA9",
            make_data_tables.pixels_influenced_by_byte_index(pixels, 1)
        )

    def test_map_to_mask32(self):
        byte_mask32 = [
            # 33222222222211111111110000000000 <- bit pos in uint32
            # 10987654321098765432109876543210
            # 0000GGGGFFFFEEEEDDDDCCCCBBBBAAAA <- pixel A..G
            #     3210321032103210321032103210  <- bit pos in A..G pixel
            0b00000000000000000000000011111111,  # byte 0 influences A,B
            0b00000000000000001111111111110000,  # byte 1 influences B,C,D
            0b00000000111111111111000000000000,  # byte 2 influences D,E,F
            0b00001111111100000000000000000000,  # byte 3 influences F,G
        ]
        int8_max = 2 ** 8 - 1
        int12_max = 2 ** 12 - 1

        self.assertEqual(
            make_data_tables.map_int8_to_mask32_0(int8_max), byte_mask32[0])
        self.assertEqual(
            make_data_tables.map_int12_to_mask32_1(int12_max), byte_mask32[1])
        self.assertEqual(
            make_data_tables.map_int12_to_mask32_2(int12_max), byte_mask32[2])
        self.assertEqual(
            make_data_tables.map_int8_to_mask32_3(int8_max), byte_mask32[3])


if __name__ == '__main__':
    unittest.main()
