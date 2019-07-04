"""Tests for the screen module."""

import unittest

import numpy as np
from etaprogress.progress import ProgressBar

import colours
from palette import Palette, PALETTES
import screen
import sys


class TestDHGRBitmap(unittest.TestCase):
    def setUp(self) -> None:
        self.aux = screen.MemoryMap(screen_page=1)
        self.main = screen.MemoryMap(screen_page=1)

    def test_edit_distances(self):
        for p in PALETTES:
            ed = screen._edit_distances("DHGR", p)
            print(p)

            bar = ProgressBar((2 ** 13 * (2 ** 13 - 1)) / 2, max_width=80)

            cnt = 0
            for i in range(2 ** 13):
                # Assert that self-distances are zero

                self.assertEqual(0, ed[0][(i << 13) + i])
                self.assertEqual(0, ed[1][(i << 13) + i])
                self.assertEqual(0, ed[2][(i << 13) + i])
                self.assertEqual(0, ed[3][(i << 13) + i])

                # Assert that matrix is triangular

                for j in range(i):

                    cnt += 1

                    if cnt % 10000 == 0:
                        bar.numerator = cnt
                        print(bar, end='\r')
                        sys.stdout.flush()

                    self.assertEqual(
                        ed[0][(i << 13) + j],
                        ed[0][(j << 13) + i],
                    )
                    self.assertEqual(
                        ed[1][(i << 13) + j],
                        ed[1][(j << 13) + i],
                    )
                    self.assertEqual(
                        ed[2][(i << 13) + j],
                        ed[2][(j << 13) + i],
                    )
                    self.assertEqual(
                        ed[3][(i << 13) + j],
                        ed[3][(j << 13) + i],
                    )

    def test_make_header(self):
        self.assertEqual(
            0b100,
            screen.DHGRBitmap._make_header(
                np.uint64(0b0001000011111010110000111110101000))
        )

    def test_make_footer(self):
        self.assertEqual(
            0b1010000000000000000000000000000000,
            screen.DHGRBitmap._make_footer(
                np.uint64(0b0001000011111010110000111110101000))
        )

    def test_pixel_packing_offset_0(self):
        #                              PBBBAAAA
        self.aux.page_offset[0, 0] = 0b11110101
        #                               PDDCCCCB
        self.main.page_offset[0, 0] = 0b01000011
        #                              PFEEEEDD
        self.aux.page_offset[0, 1] = 0b11110101
        #                               PGGGGFFF
        self.main.page_offset[0, 1] = 0b01000011

        dhgr = screen.DHGRBitmap(
            main_memory=self.main, aux_memory=self.aux, palette=Palette.NTSC)

        self.assertEqual(
            0b0001000011111010110000111110101000,
            dhgr.packed[0, 0]
        )

        # Check header on neighbouring byte
        self.assertEqual(
            0b0000000000000000000000000000000100,
            dhgr.packed[0, 1]
        )

        # No other entries should be set, in particular no footer since we
        # are at packed offset 0
        self.assertEqual(2, np.count_nonzero(dhgr.packed))

    def test_pixel_packing_offset_1(self):
        #                              PBBBAAAA
        self.aux.page_offset[0, 2] = 0b11110101
        #                               PDDCCCCB
        self.main.page_offset[0, 2] = 0b01000011
        #                              PFEEEEDD
        self.aux.page_offset[0, 3] = 0b11110101
        #                               PGGGGFFF
        self.main.page_offset[0, 3] = 0b01000011

        dhgr = screen.DHGRBitmap(
            main_memory=self.main, aux_memory=self.aux, palette=Palette.NTSC)

        self.assertEqual(
            0b0001000011111010110000111110101000,
            dhgr.packed[0, 1]
        )

        # Check footer on neighbouring byte
        self.assertEqual(
            0b1010000000000000000000000000000000,
            dhgr.packed[0, 0]
        )

        # Check header on neighbouring byte
        self.assertEqual(
            0b0000000000000000000000000000000100,
            dhgr.packed[0, 2]
        )

        # No other entries should be set
        self.assertEqual(3, np.count_nonzero(dhgr.packed))

    def test_pixel_packing_offset_127(self):
        #                              PBBBAAAA
        self.aux.page_offset[0, 254] = 0b11110101
        #                               PDDCCCCB
        self.main.page_offset[0, 254] = 0b01000011
        #                              PFEEEEDD
        self.aux.page_offset[0, 255] = 0b11110101
        #                               PGGGGFFF
        self.main.page_offset[0, 255] = 0b01000011

        dhgr = screen.DHGRBitmap(
            main_memory=self.main, aux_memory=self.aux, palette=Palette.NTSC)

        self.assertEqual(
            0b0001000011111010110000111110101000,
            dhgr.packed[0, 127]
        )

        # Check footer on neighbouring byte
        self.assertEqual(
            0b1010000000000000000000000000000000,
            dhgr.packed[0, 126]
        )

        # No other entries should be set, in particular header should not
        # propagate to next row
        self.assertEqual(2, np.count_nonzero(dhgr.packed))

    def test_byte_offset(self):
        self.assertEqual(0, screen.DHGRBitmap.byte_offset(0, is_aux=True))
        self.assertEqual(1, screen.DHGRBitmap.byte_offset(0, is_aux=False))
        self.assertEqual(2, screen.DHGRBitmap.byte_offset(1, is_aux=True))
        self.assertEqual(3, screen.DHGRBitmap.byte_offset(1, is_aux=False))

    def test_byte_offsets(self):
        self.assertEqual((0, 2), screen.DHGRBitmap._byte_offsets(is_aux=True))
        self.assertEqual((1, 3), screen.DHGRBitmap._byte_offsets(is_aux=False))

    def test_mask_and_shift_data(self):
        int13_max = np.uint64(2 ** 13 - 1)
        int34_max = np.uint64(2 ** 34 - 1)

        dhgr = screen.DHGRBitmap(
            main_memory=self.main, aux_memory=self.aux, palette=Palette.NTSC)

        for o in range(3):
            self.assertEqual(
                int13_max,
                dhgr.mask_and_shift_data(
                    screen.DHGRBitmap.BYTE_MASKS[o], o
                )
            )

            # Now check complement, i.e. no bits taken from outside expected
            # range
            self.assertEqual(
                0,
                dhgr.mask_and_shift_data(
                    ~screen.DHGRBitmap.BYTE_MASKS[o] & int34_max, o
                )
            )

    def test_masked_update(self):
        self.assertEqual(
            0b0000000000000000000000001111111000,
            screen.DHGRBitmap.masked_update(
                0, np.uint64(0), np.uint8(0xff))
        )
        self.assertEqual(
            0b0000000000000000011111110000000000,
            screen.DHGRBitmap.masked_update(
                1, np.uint64(0), np.uint8(0xff))
        )
        self.assertEqual(
            0b0000000000111111100000000000000000,
            screen.DHGRBitmap.masked_update(
                2, np.uint64(0), np.uint8(0xff))
        )
        self.assertEqual(
            0b0001111111000000000000000000000000,
            screen.DHGRBitmap.masked_update(
                3, np.uint64(0), np.uint8(0xff))
        )

        # Now test masking out existing values

        int34_max = np.uint64(2 ** 34 - 1)

        self.assertEqual(
            0b1111111111111111111111110000000111,
            screen.DHGRBitmap.masked_update(0, int34_max, np.uint8(0x00))
        )
        self.assertEqual(
            0b1111111111111111100000001111111111,
            screen.DHGRBitmap.masked_update(1, int34_max, np.uint8(0x00))
        )
        self.assertEqual(
            0b1111111111000000011111111111111111,
            screen.DHGRBitmap.masked_update(2, int34_max, np.uint8(0x00))
        )
        self.assertEqual(
            0b1110000000111111111111111111111111,
            screen.DHGRBitmap.masked_update(3, int34_max, np.uint8(0x00))
        )

        # Test that masked_update can broadcast to numpy arrays
        ary = np.zeros((2, 2), dtype=np.uint64)

        elt = np.uint64(0b1111111000)
        self.assertTrue(np.array_equal(
            np.array([[elt, elt], [elt, elt]], dtype=np.uint64),
            screen.DHGRBitmap.masked_update(0, ary, np.uint8(0xff))
        ))

    def test_apply(self):
        dhgr = screen.DHGRBitmap(
            main_memory=self.main, aux_memory=self.aux, palette=Palette.NTSC)

        dhgr.apply(page=0, offset=0, is_aux=True, value=np.uint8(0xff))
        self.assertEqual(0b1111111000, dhgr.packed[0, 0])

        dhgr.apply(page=12, offset=36, is_aux=True, value=np.uint8(0xff))
        # Neighbouring header
        self.assertEqual(
            0,
            dhgr.packed[12, 19])
        # Body
        self.assertEqual(
            0b1111111000,
            dhgr.packed[12, 18])
        # Neighbouring footer
        self.assertEqual(
            0b1110000000000000000000000000000000,
            dhgr.packed[12, 17])

        # Now update the next aux offset in same uint64
        dhgr.apply(page=12, offset=37, is_aux=True, value=np.uint8(0xff))
        # Neighbouring header
        self.assertEqual(
            0,
            dhgr.packed[12, 19])
        # Body
        self.assertEqual(
            0b0000000111111100000001111111000,
            dhgr.packed[12, 18]
        )
        # Neighbouring footer
        self.assertEqual(
            0b1110000000000000000000000000000000,
            dhgr.packed[12, 17])

        # Update offset 3, should propagate to next header
        dhgr.apply(page=12, offset=37, is_aux=False, value=np.uint8(0b1010101))
        self.assertEqual(
            0b101,
            dhgr.packed[12, 19])
        self.assertEqual(
            0b1010101111111100000001111111000,
            dhgr.packed[12, 18]
        )
        self.assertEqual(
            0b1110000000000000000000000000000000,
            dhgr.packed[12, 17])

        dhgr.apply(page=12, offset=36, is_aux=False, value=np.uint8(0b0001101))
        self.assertEqual(
            0b101,
            dhgr.packed[12, 19])
        self.assertEqual(
            0b1010101111111100011011111111000,
            dhgr.packed[12, 18]
        )
        self.assertEqual(
            0b1110000000000000000000000000000000,
            dhgr.packed[12, 17])

        # Change offset 0, should propagate to neighbouring footer
        dhgr.apply(page=12, offset=36, is_aux=True, value=np.uint8(0b0001101))
        # Neighbouring header
        self.assertEqual(
            0b101,
            dhgr.packed[12, 19])
        self.assertEqual(
            0b1010101111111100011010001101000,
            dhgr.packed[12, 18]
        )
        # Neighbouring footer
        self.assertEqual(
            0b1010000000000000000000000000000000,
            dhgr.packed[12, 17])

        # Now propagate new header from neighbour onto (12, 18)
        dhgr.apply(page=12, offset=35, is_aux=False, value=np.uint8(0b1010101))
        self.assertEqual(
            0b1010101111111100011010001101101,
            dhgr.packed[12, 18]
        )
        # Neighbouring footer
        self.assertEqual(
            0b1011010101000000000000000000000000,
            dhgr.packed[12, 17])

    def test_fix_array_neighbours(self):
        dhgr = screen.DHGRBitmap(
            main_memory=self.main, aux_memory=self.aux, palette=Palette.NTSC)

        packed = dhgr.masked_update(0, dhgr.packed, np.uint8(0x7f))
        dhgr._fix_array_neighbours(packed, 0)

        # Should propagate to all footers
        self.assertEqual(
            0, np.count_nonzero(
                packed[packed != 0b1110000000000000000000001111111000]
            )
        )

        # Should not change headers/footers
        packed = dhgr.masked_update(1, packed, np.uint8(0b1010101))
        dhgr._fix_array_neighbours(packed, 1)

        self.assertEqual(
            0, np.count_nonzero(
                packed[packed != 0b1110000000000000010101011111111000]
            )
        )

        # Should propagate to all headers
        packed = dhgr.masked_update(3, packed, np.uint8(0b0110110))
        dhgr._fix_array_neighbours(packed, 3)

        self.assertEqual(
            0, np.count_nonzero(
                packed[packed != 0b1110110110000000010101011111111011]
            )
        )


def binary(a):
    return np.vectorize("{:032b}".format)(a)


# class TestHGRBitmap:  # unittest.TestCase):
#     def setUp(self) -> None:
#         self.main = screen.MemoryMap(screen_page=1)
#
#     def test_pixel_packing_p0_p0(self):
#         #                               PDCCBBAA
#         self.main.page_offset[0, 0] = 0b01000011
#         #                               PGGFFEED
#         self.main.page_offset[0, 1] = 0b01000011
#
#         hgr = screen.HGRBitmap(
#             main_memory=self.main)
#
#         want = 0b1100000000111111000000001111
#         got = hgr.packed[0, 0]
#
#         self.assertEqual(
#             want, got, "\n%s\n%s" % (binary(want), binary(got))
#         )
#
#     def test_pixel_packing_p0_p1(self):
#         #                               PDCCBBAA
#         self.main.page_offset[0, 0] = 0b01000011
#         #                               PGGFFEED
#         self.main.page_offset[0, 1] = 0b11000011
#
#         hgr = screen.HGRBitmap(
#             main_memory=self.main)
#
#         want = 0b1000000001111111000000001111
#         got = hgr.packed[0, 0]
#
#         self.assertEqual(
#             want, got, "\n%s\n%s" % (binary(want), binary(got))
#         )
#
#     def test_pixel_packing_p1_p0(self):
#         #                               PDCCBBAA
#         self.main.page_offset[0, 0] = 0b11000011
#         #                               PGGFFEED
#         self.main.page_offset[0, 1] = 0b01000011
#
#         hgr = screen.HGRBitmap(
#             main_memory=self.main)
#
#         want = 0b1100000000111110000000011110
#         got = hgr.packed[0, 0]
#
#         self.assertEqual(
#             want, got, "\n%s\n%s" % (binary(want), binary(got))
#         )
#
#     def test_pixel_packing_p1_p1(self):
#         #                               PDCCBBAA
#         self.main.page_offset[0, 0] = 0b11000011
#         #                               PGGFFEED
#         self.main.page_offset[0, 1] = 0b11000011
#
#         hgr = screen.HGRBitmap(
#             main_memory=self.main)
#
#         want = 0b1000000001111110000000011110
#         got = hgr.packed[0, 0]
#
#         self.assertEqual(
#             want, got, "\n%s\n%s" % (binary(want), binary(got))
#         )
#
#     def test_pixel_packing_p1_promote_p0(self):
#         #                               PDCCBBAA
#         self.main.page_offset[0, 0] = 0b00000000
#         #                               PGGFFEED
#         self.main.page_offset[0, 1] = 0b01000000
#
#         #                               PDCCBBAA
#         self.main.page_offset[0, 2] = 0b10000000
#
#         hgr = screen.HGRBitmap(
#             main_memory=self.main)
#
#         want = 0b0000000000000000000000000001
#         got = hgr.packed[0, 1]
#
#         self.assertEqual(
#             want, got, "\n%s\n%s" % (binary(want), binary(got))
#         )
#
#     def test_pixel_packing_p1_promote_p1(self):
#         #                               PDCCBBAA
#         self.main.page_offset[0, 0] = 0b00000000
#         #                               PGGFFEED
#         self.main.page_offset[0, 1] = 0b11000000
#
#         #                               PDCCBBAA
#         self.main.page_offset[0, 2] = 0b10000000
#
#         hgr = screen.HGRBitmap(
#             main_memory=self.main)
#
#         want = 0b0000000000000000000000000001
#         got = hgr.packed[0, 1]
#
#         self.assertEqual(
#             want, got, "\n%s\n%s" % (binary(want), binary(got))
#         )
#
#     def test_nominal_colours(self):
#         #                               PDCCBBAA
#         self.main.page_offset[0, 0] = 0b01010101
#         #                               PGGFFEED
#         self.main.page_offset[0, 1] = 0b00101010
#         #                               PDCCBBAA
#         self.main.page_offset[0, 2] = 0b01010101
#
#         hgr = screen.HGRBitmap(
#             main_memory=self.main)
#
#         want = 0b000110011001100110011001100110011
#         got = hgr.packed[0, 0]
#
#         self.assertEqual(
#             want, got, "\n%s\n%s" % (binary(want), binary(got))
#         )
#
#         self.assertEqual(
#             (
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.VIOLET,
#             ),
#             colours.int34_to_nominal_colour_pixels(hgr.packed[0, 0],
#                                                    colours.HGRColours)
#         )
#
#     # See Figure 8.15 from Sather, "Understanding the Apple IIe"
#
#     def test_nominal_colours_sather1(self):
#         # Extend violet into light blue
#
#         #                               PDCCBBAA
#         self.main.page_offset[0, 0] = 0b01000000
#         #                               PGGFFEED
#         self.main.page_offset[0, 1] = 0b10000000
#
#         hgr = screen.HGRBitmap(
#             main_memory=self.main)
#
#         self.assertEqual(
#             (
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.LIGHT_BLUE,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#             ),
#             colours.int28_to_nominal_colour_pixels(hgr.packed[0, 0],
#                                                    colours.HGRColours)
#         )
#
#     def test_nominal_colours_sather2(self):
#         # Cut off blue with black to produce dark blue
#
#         #                               PDCCBBAA
#         self.main.page_offset[0, 0] = 0b11000000
#         #                               PGGFFEED
#         self.main.page_offset[0, 1] = 0b00000000
#
#         hgr = screen.HGRBitmap(
#             main_memory=self.main)
#
#         self.assertEqual(
#             (
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.DARK_BLUE,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#             ),
#             colours.int28_to_nominal_colour_pixels(hgr.packed[0, 0],
#                                                    colours.HGRColours)
#         )
#
#     def test_nominal_colours_sather3(self):
#         # Cut off blue with green to produce aqua
#
#         #                               PDCCBBAA
#         self.main.page_offset[0, 0] = 0b11000000
#         #                               PGGFFEED
#         self.main.page_offset[0, 1] = 0b00000001
#
#         hgr = screen.HGRBitmap(
#             main_memory=self.main)
#
#         self.assertEqual(
#             (
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.AQUA,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#             ),
#             colours.int28_to_nominal_colour_pixels(hgr.packed[0, 0],
#                                                    colours.HGRColours)
#         )
#
#     def test_nominal_colours_sather4(self):
#         # Cut off white with black to produce pink
#
#         #                               PDCCBBAA
#         self.main.page_offset[0, 0] = 0b11100000
#         #                               PGGFFEED
#         self.main.page_offset[0, 1] = 0b00000000
#
#         hgr = screen.HGRBitmap(
#             main_memory=self.main)
#
#         want = 0b0000000000000011100000000000
#         got = hgr.packed[0, 0]
#
#         self.assertEqual(
#             want, got, "\n%s\n%s" % (binary(want), binary(got))
#         )
#
#         # TODO: BROWN(0001)/VIOLET(1100) should reframe to PINK (1011)
#         self.assertEqual(
#             (
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BROWN,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#             ),
#             colours.int28_to_nominal_colour_pixels(hgr.packed[0, 0],
#                                                    colours.HGRColours)
#         )
#
#     def test_nominal_colours_sather5(self):
#         # Extend green into light brown
#
#         #                               PDCCBBAA
#         self.main.page_offset[0, 0] = 0b01000000
#         #                               PGGFFEED
#         self.main.page_offset[0, 1] = 0b10000000
#
#         hgr = screen.HGRBitmap(
#             main_memory=self.main)
#
#         want = 0b0000000000000111000000000000
#         got = hgr.packed[0, 0]
#
#         self.assertEqual(
#             want, got, "\n%s\n%s" % (binary(want), binary(got))
#         )
#
#         # TODO: LIGHT_BLUE should reframe to PINK (1011)
#         self.assertEqual(
#             (
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.LIGHT_BLUE,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#             ),
#             colours.int28_to_nominal_colour_pixels(hgr.packed[0, 0],
#                                                    colours.HGRColours)
#         )
#
#     def test_nominal_colours_sather6(self):
#         # Cut off orange with black to produce dark brown
#
#         #                               PDCCBBAA
#         self.main.page_offset[0, 0] = 0b11000000
#         #                               PGGFFEED
#         self.main.page_offset[0, 1] = 0b00000000
#
#         hgr = screen.HGRBitmap(
#             main_memory=self.main)
#
#         want = 0b00000000000000010000000000000
#         got = hgr.packed[0, 0]
#
#         self.assertEqual(
#             want, got, "\n%s\n%s" % (binary(want), binary(got))
#         )
#
#         # TODO: DARK_BLUE should reframe to DARK_BROWN
#         self.assertEqual(
#             (
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.DARK_BLUE,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#             ),
#             colours.int28_to_nominal_colour_pixels(hgr.packed[0, 0],
#                                                    colours.HGRColours)
#         )
#
#     def test_nominal_colours_sather7(self):
#         # Cut off orange with violet to produce pink
#
#         #                               PDCCBBAA
#         self.main.page_offset[0, 0] = 0b11000000
#         #                               PGGFFEED
#         self.main.page_offset[0, 1] = 0b00000001
#
#         hgr = screen.HGRBitmap(
#             main_memory=self.main)
#
#         want = 0b00000000000001110000000000000
#         got = hgr.packed[0, 0]
#
#         self.assertEqual(
#             want, got, "\n%s\n%s" % (binary(want), binary(got))
#         )
#
#         # TODO: AQUA should reframe to PINK
#         self.assertEqual(
#             (
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.AQUA,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#             ),
#             colours.int28_to_nominal_colour_pixels(hgr.packed[0, 0],
#                                                    colours.HGRColours)
#         )
#
#     def test_nominal_colours_sather8(self):
#         # Cut off white with black to produce aqua
#
#         #                               PDCCBBAA
#         self.main.page_offset[0, 0] = 0b11100000
#         #                               PGGFFEED
#         self.main.page_offset[0, 1] = 0b00000000
#
#         hgr = screen.HGRBitmap(
#             main_memory=self.main)
#
#         want = 0b00000000000000011100000000000
#         got = hgr.packed[0, 0]
#
#         self.assertEqual(
#             want, got, "\n%s\n%s" % (binary(want), binary(got))
#         )
#
#         # TODO: BROWN/VIOLET should reframe to AQUA
#         self.assertEqual(
#             (
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BROWN,
#                 colours.HGRColours.VIOLET,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#                 colours.HGRColours.BLACK,
#             ),
#             colours.int28_to_nominal_colour_pixels(
#                 hgr.packed[0, 0], colours.HGRColours)
#         )


if __name__ == '__main__':
    unittest.main()
