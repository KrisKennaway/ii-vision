import sys
import unittest

import numpy as np
from etaprogress.progress import ProgressBar

import make_data_tables
import screen
from colours import HGRColours
from palette import PALETTES


class TestMakeDataTables(unittest.TestCase):
    def test_pixel_string(self):
        pixels = (HGRColours.BLACK, HGRColours.WHITE, HGRColours.ORANGE)
        self.assertEqual("0FC", make_data_tables.pixel_string(pixels))

    def test_edit_distances(self):
        for p in PALETTES:
            ed = screen.DHGRBitmap.edit_distances(p)
            print(p)

            bar = ProgressBar((4 * 2 ** 13 * (2 ** 13 - 1)) / 2, max_width=80)

            cnt = 0
            for ph in range(3):

                # Only zero entries should be on diagonal, i.e. of form
                # i << 13 + i
                zeros = np.arange(len(ed[ph]))[ed[ph] == 0]
                for z in zeros:
                    z1 = z & (2 ** 13 - 1)
                    z2 = (z >> 13) & (2 ** 13 - 1)
                    self.assertEqual(z1, z2)

                # Assert that matrix is symmetrical
                for i in range(2 ** 13):
                    for j in range(i):
                        cnt += 1

                        if cnt % 10000 == 0:
                            bar.numerator = cnt
                            print(bar, end='\r')
                            sys.stdout.flush()

                        self.assertEqual(
                            ed[ph][(i << 13) + j],
                            ed[ph][(j << 13) + i],
                        )

                        # Matrix is positive definite
                        self.assertGreaterEqual(ed[ph][(i << 13) + j], 0)

    def test_edit_distances_hgr(self):
        for p in PALETTES:
            ed = screen.HGRBitmap.edit_distances(p)
            print(p)

            bar = ProgressBar((4 * 2 ** 14 * (2 ** 14 - 1)) / 2, max_width=80)

            cnt = 0
            for ph in range(2):

                # Only zero entries should be on diagonal, i.e. of form
                # # i << 14 + i
                # zeros = np.arange(len(ed[ph]))[ed[ph] == 0]
                # for z in zeros:
                #     z1 = z & (2**14-1)
                #     z2 = (z >> 14) & (2**14-1)
                #     self.assertEqual(z1, z2)

                # Assert that matrix is symmetrical
                for i in range(2 ** 14):
                    for j in range(i):
                        cnt += 1

                        if cnt % 10000 == 0:
                            bar.numerator = cnt
                            print(bar, end='\r')
                            sys.stdout.flush()

                        self.assertEqual(
                            ed[ph][(i << 14) + j],
                            ed[ph][(j << 14) + i],
                        )

                        # Matrix is positive definite
                        self.assertGreaterEqual(ed[ph][(i << 14) + j], 0)


if __name__ == '__main__':
    unittest.main()
