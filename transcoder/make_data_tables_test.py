import unittest

from colours import HGRColours
import make_data_tables


class TestMakeDataTables(unittest.TestCase):
    def test_pixel_string(self):
        pixels = (HGRColours.BLACK, HGRColours.WHITE, HGRColours.ORANGE)
        self.assertEqual("0FC", make_data_tables.pixel_string(pixels))


if __name__ == '__main__':
    unittest.main()
