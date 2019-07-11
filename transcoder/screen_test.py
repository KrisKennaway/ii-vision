"""Tests for the screen module."""

import unittest

import numpy as np

import screen
import colours
from palette import Palette


def binary(a):
    return np.vectorize("{:032b}".format)(a)


class TestDHGRBitmap(unittest.TestCase):
    def setUp(self) -> None:
        self.aux = screen.MemoryMap(screen_page=1)
        self.main = screen.MemoryMap(screen_page=1)

    def test_make_header(self):
        """Header extracted correctly from packed representation."""

        self.assertEqual(
            0b100,
            screen.DHGRBitmap._make_header(
                np.uint64(0b0001000011111010110000111110101000))
        )

    def test_make_footer(self):
        """Footer extracted correctly from packed representation."""

        self.assertEqual(
            0b1010000000000000000000000000000000,
            screen.DHGRBitmap._make_footer(
                np.uint64(0b0001000011111010110000111110101000))
        )

    def test_pixel_packing_offset_0(self):
        """Screen byte packing happens correctly at offset 0."""

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
        """Screen byte packing happens correctly at offset 1."""

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
        """Screen byte packing happens correctly at offset 127."""

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
        """Test the byte_offset behaviour."""

        self.assertEqual(0, screen.DHGRBitmap.byte_offset(0, is_aux=True))
        self.assertEqual(1, screen.DHGRBitmap.byte_offset(0, is_aux=False))
        self.assertEqual(2, screen.DHGRBitmap.byte_offset(1, is_aux=True))
        self.assertEqual(3, screen.DHGRBitmap.byte_offset(1, is_aux=False))

    def test_byte_offsets(self):
        """Test the _byte_offsets behaviour."""

        self.assertEqual((0, 2), screen.DHGRBitmap._byte_offsets(is_aux=True))
        self.assertEqual((1, 3), screen.DHGRBitmap._byte_offsets(is_aux=False))

    def test_mask_and_shift_data(self):
        """Verify that mask_and_shift_data extracts the right bit positions."""

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
        """Verify that masked_update updates the expected bit positions."""

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
        """Test that apply() correctly updates neighbours."""

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
        """Test that _fix_array_neighbours DTRT after masked_update."""

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


class TestHGRBitmap(unittest.TestCase):
    def setUp(self) -> None:
        self.main = screen.MemoryMap(screen_page=1)

    def test_make_header(self):
        """Header extracted correctly from packed representation."""

        self.assertEqual(
            0b111,
            screen.HGRBitmap._make_header(
                np.uint64(0b0001100000100000000000))
        )

        # Now check palette bit ends up in right spot
        self.assertEqual(
            0b100,
            screen.HGRBitmap._make_header(
                np.uint64(0b0000000000100000000000))
        )

    def test_make_footer(self):
        """Footer extracted correctly from packed representation."""

        self.assertEqual(
            0b1110000000000000000000,
            screen.HGRBitmap._make_footer(
                np.uint64(0b0000000000010000011000))
        )

        # Now check palette bit ends up in right spot
        self.assertEqual(
            0b0010000000000000000000,
            screen.HGRBitmap._make_footer(
                np.uint64(0b0000000000010000000000))
        )

    def test_pixel_packing_p0_p0(self):
        """Screen byte packing happens correctly with P=0, P=0 palette bits."""

        #                               PDCCBBAA
        self.main.page_offset[0, 0] = 0b01000011
        #                               PGGFFEED
        self.main.page_offset[0, 1] = 0b01000011

        hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        want = 0b0001000011001000011000
        got = hgr.packed[0, 0]

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

    def test_pixel_packing_p0_p1(self):
        """Screen byte packing happens correctly with P=0, P=1 palette bits."""

        #                               PDCCBBAA
        self.main.page_offset[0, 0] = 0b01000011
        #                               PGGFFEED
        self.main.page_offset[0, 1] = 0b11000011

        hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        want = 0b0001000011101000011000
        got = hgr.packed[0, 0]

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

    def test_pixel_packing_p1_p0(self):
        """Screen byte packing happens correctly with P=1, P=0 palette bits."""

        #                               PDCCBBAA
        self.main.page_offset[0, 0] = 0b11000011
        #                               PGGFFEED
        self.main.page_offset[0, 1] = 0b01000011

        hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        want = 0b0001000011011000011000
        got = hgr.packed[0, 0]

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

    def test_pixel_packing_p1_p1(self):
        """Screen byte packing happens correctly with P=1, P=1 palette bits."""

        #                               PDCCBBAA
        self.main.page_offset[0, 0] = 0b11000011
        #                               PGGFFEED
        self.main.page_offset[0, 1] = 0b11000011

        hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        want = 0b1000011111000011000
        got = hgr.packed[0, 0]

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

    def test_apply(self):
        """Test that header, body and footer are placed correctly."""
        hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        hgr.apply(0, 0, False, 0b11000011)
        hgr.apply(0, 1, False, 0b11000011)

        want = 0b1000011111000011000
        got = hgr.packed[0, 0]

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        # Now check with 4 consecutive bytes, i.e. even/odd pair plus the
        # neighbouring header/footer.
        hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        hgr.apply(1, 197, False, 128)
        hgr.apply(1, 198, False, 143)
        hgr.apply(1, 199, False, 192)
        hgr.apply(1, 200, False, 128)

        want = 0b0011000000110001111100
        got = hgr.packed[1, 199 // 2]

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

    def test_double_pixels(self):
        """Verify behaviour of _double_pixels."""

        want = 0b111001100110011
        got = screen.HGRBitmap._double_pixels(0b1010101)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

    def test_to_dots_offset_0(self):
        """Verify to_dots behaviour with byte_offset=0"""

        # Header has P=0, Body has P=0
        want = 0b00000000000000000111
        got = screen.HGRBitmap.to_dots(0b00000000000011, 0)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        # Header has P=1, body has P=0 - cuts off
        want = 0b00000000000000000111
        got = screen.HGRBitmap.to_dots(0b00000000000111, 0)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        # Header has P=1, body has P=1
        want = 0b00000000000000001111
        got = screen.HGRBitmap.to_dots(0b00010000000111, 0)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        # Header has P=1, body has P=1, footer has P=0 - cuts off body
        want = 0b00010011001100111111
        got = screen.HGRBitmap.to_dots(0b00011010101111, 0)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        # Header has P=1, body has P=1, footer has P=1
        want = 0b00110011001100111111
        got = screen.HGRBitmap.to_dots(0b00111010101111, 0)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        # Header has P=1, body has P=1, footer has P=1
        want = 0b100110011001100111111
        got = screen.HGRBitmap.to_dots(0b10111010101111, 0)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        # Header has P=0, body has P=0, footer has P=1
        want = 0b100000000000000000000
        got = screen.HGRBitmap.to_dots(0b10100000000000, 0)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        # Header has P=0, body has P=0, footer has P=0
        want = 0b110000000000000000000
        got = screen.HGRBitmap.to_dots(0b10000000000000, 0)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

    def test_to_dots_offset_1(self):
        """Verify to_dots behaviour with byte_offset=1"""

        # Header has P=0, Body has P=0
        want = 0b000000000000000000111
        got = screen.HGRBitmap.to_dots(0b00000000000011, 1)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        # Header has P=1, body has P=0 - cuts off
        want = 0b000000000000000000111
        got = screen.HGRBitmap.to_dots(0b00000000000111, 1)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        # Header has P=1, body has P=1
        want = 0b000000000000000001111
        got = screen.HGRBitmap.to_dots(0b00000000001111, 1)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        # Header has P=1, body has P=1, footer has P=0 - cuts off body
        want = 0b000010011001100111111
        got = screen.HGRBitmap.to_dots(0b00010101011111, 1)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        # Header has P=1, body has P=1, footer has P=1
        want = 0b000110011001100111111
        got = screen.HGRBitmap.to_dots(0b00110101011111, 1)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        # Header has P=1, body has P=1, footer has P=1
        want = 0b100110011001100111111
        got = screen.HGRBitmap.to_dots(0b10110101011111, 1)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        # Header has P=0, body has P=0, footer has P=1
        want = 0b100000000000000000000
        got = screen.HGRBitmap.to_dots(0b10100000000000, 1)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        # Header has P=0, body has P=0, footer has P=0
        want = 0b110000000000000000000
        got = screen.HGRBitmap.to_dots(0b10000000000000, 1)

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )


class TestNominalColours(unittest.TestCase):
    """Tests that screen pixel values produce expected colour sequences."""

    def setUp(self) -> None:
        self.main = screen.MemoryMap(screen_page=1)

        self.maxDiff = None

    def test_nominal_colours(self):
        #                               PDCCBBAA
        self.main.page_offset[0, 0] = 0b01010101
        #                               PGGFFEED
        self.main.page_offset[0, 1] = 0b00101010
        #                               PDCCBBAA
        self.main.page_offset[0, 2] = 0b01010101

        self.hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        want = 0b0100101010001010101000
        got = self.hgr.packed[0, 0]

        self.assertEqual(
            want, got, "\n%s\n%s" % (binary(want), binary(got))
        )

        masked = int(screen.HGRBitmap.mask_and_shift_data(
            self.hgr.packed[0, 0], byte_offset=0))
        dots = screen.HGRBitmap.to_dots(masked, byte_offset=0)
        self.assertEqual(
            (
                colours.HGRColours.MAGENTA,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
            ),
            colours.dots_to_nominal_colour_pixels(
                18, dots, colours.HGRColours,
                init_phase=screen.HGRBitmap.PHASES[0])
        )

        # Now check byte offset 1

        masked = int(screen.HGRBitmap.mask_and_shift_data(
            self.hgr.packed[0, 0], byte_offset=1))
        dots = screen.HGRBitmap.to_dots(masked, byte_offset=1)
        self.assertEqual(
            (
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET,
            ),
            colours.dots_to_nominal_colour_pixels(
                18, dots, colours.HGRColours,
                init_phase=screen.HGRBitmap.PHASES[1])
        )

    # The following tests check for the extended/truncated behaviour across
    # byte boundaries when mismatching palette bits.   See Figure 8.15 from
    # Sather, "Understanding the Apple IIe"

    def test_nominal_colours_sather_even_1(self):
        """Extend violet into light blue."""

        #                               PDCCBBAA
        self.main.page_offset[0, 0] = 0b01000000
        #                               PGGFFEED
        self.main.page_offset[0, 1] = 0b10000000

        self.hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        masked = int(screen.HGRBitmap.mask_and_shift_data(
            self.hgr.packed[0, 0], byte_offset=0))
        dots = screen.HGRBitmap.to_dots(masked, byte_offset=0)

        self.assertEqual(
            (
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.MAGENTA,  # 1000
                colours.HGRColours.VIOLET,  # 1100
                colours.HGRColours.LIGHT_BLUE,  # 1110
                colours.HGRColours.LIGHT_BLUE,  # 1110
                colours.HGRColours.MED_BLUE,  # 0110
                #  last repeated bit from byte 0
                colours.HGRColours.DARK_GREEN,  # 0010
            ),
            colours.dots_to_nominal_colour_pixels(
                18, dots, colours.HGRColours,
                init_phase=screen.HGRBitmap.PHASES[0])
        )

    def test_nominal_colours_sather_even_2(self):
        """Cut off blue with black to produce dark blue."""

        #                               PDCCBBAA
        self.main.page_offset[0, 0] = 0b11000000
        #                               PGGFFEED
        self.main.page_offset[0, 1] = 0b00000000

        self.hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        masked = int(screen.HGRBitmap.mask_and_shift_data(
            self.hgr.packed[0, 0], byte_offset=0))
        dots = screen.HGRBitmap.to_dots(masked, byte_offset=0)

        self.assertEqual(
            (
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.DARK_BLUE,  # 0100
                colours.HGRColours.DARK_BLUE,
                colours.HGRColours.DARK_BLUE,
                colours.HGRColours.DARK_BLUE,
                colours.HGRColours.BLACK,
            ),
            colours.dots_to_nominal_colour_pixels(
                18, dots, colours.HGRColours,
                init_phase=screen.HGRBitmap.PHASES[0])
        )

    def test_nominal_colours_sather_even_3(self):
        """Cut off blue with green to produce aqua."""

        #                               PDCCBBAA
        self.main.page_offset[0, 0] = 0b11000000
        #                               PGGFFEED
        self.main.page_offset[0, 1] = 0b00000001

        self.hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        masked = int(screen.HGRBitmap.mask_and_shift_data(
            self.hgr.packed[0, 0], byte_offset=0))
        dots = screen.HGRBitmap.to_dots(masked, byte_offset=0)

        self.assertEqual(
            (
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.DARK_BLUE,
                colours.HGRColours.MED_BLUE,
                colours.HGRColours.AQUA,
                colours.HGRColours.AQUA,
                colours.HGRColours.GREEN,
            ),
            colours.dots_to_nominal_colour_pixels(
                18, dots, colours.HGRColours,
                init_phase=screen.HGRBitmap.PHASES[0])
        )

    def test_nominal_colours_sather_even_4(self):
        """Cut off white with black to produce pink."""

        #                               PDCCBBAA
        self.main.page_offset[0, 0] = 0b11100000
        #                               PGGFFEED
        self.main.page_offset[0, 1] = 0b00000000

        self.hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        masked = int(screen.HGRBitmap.mask_and_shift_data(
            self.hgr.packed[0, 0], byte_offset=0))
        dots = screen.HGRBitmap.to_dots(masked, byte_offset=0)

        self.assertEqual(
            (
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BROWN,
                colours.HGRColours.ORANGE,
                colours.HGRColours.PINK,
                colours.HGRColours.PINK,
                colours.HGRColours.VIOLET,
                colours.HGRColours.DARK_BLUE,
                colours.HGRColours.BLACK,
            ),
            colours.dots_to_nominal_colour_pixels(
                18, dots, colours.HGRColours,
                init_phase=screen.HGRBitmap.PHASES[0])
        )

    def test_nominal_colours_sather_even_5(self):
        """Cut off orange-black with green to produce bright green.

        "Bright" here is because the sequence of pixels has high intensity
        Orange-Orange-Yellow-Yellow-Green-Green."""

        #                               PDCCBBAA
        self.main.page_offset[0, 0] = 0b10100000
        #                               PGGFFEED
        self.main.page_offset[0, 1] = 0b00000001

        self.hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        masked = int(screen.HGRBitmap.mask_and_shift_data(
            self.hgr.packed[0, 0], byte_offset=0))
        dots = screen.HGRBitmap.to_dots(masked, byte_offset=0)

        self.assertEqual(
            (
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BROWN,  # 0001
                colours.HGRColours.ORANGE,  # 1001
                colours.HGRColours.ORANGE,  # 1001
                colours.HGRColours.YELLOW,  # 1011
                colours.HGRColours.YELLOW,  # 1011
                colours.HGRColours.GREEN,  # 0011
                colours.HGRColours.GREEN,  # 0011
            ),
            colours.dots_to_nominal_colour_pixels(
                18, dots, colours.HGRColours,
                init_phase=screen.HGRBitmap.PHASES[0])
        )

    def test_nominal_colours_sather_odd_1(self):
        """Extend green into light brown."""

        #                               PDCCBBAA
        self.main.page_offset[0, 1] = 0b01000000
        #                               PGGFFEED
        self.main.page_offset[0, 2] = 0b10000000

        self.hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        masked = int(screen.HGRBitmap.mask_and_shift_data(
            self.hgr.packed[0, 0], byte_offset=1))
        dots = screen.HGRBitmap.to_dots(masked, byte_offset=1)

        self.assertEqual(
            (
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.DARK_GREEN,
                colours.HGRColours.GREEN,
                colours.HGRColours.YELLOW,
                colours.HGRColours.YELLOW,
                colours.HGRColours.ORANGE,
                colours.HGRColours.MAGENTA,
            ),
            colours.dots_to_nominal_colour_pixels(
                18, dots, colours.HGRColours,
                init_phase=screen.HGRBitmap.PHASES[1])
        )

    def test_nominal_colours_sather_odd_2(self):
        """Cut off orange with black to produce dark brown."""

        #                               PDCCBBAA
        self.main.page_offset[0, 1] = 0b11000000
        #                               PGGFFEED
        self.main.page_offset[0, 2] = 0b00000000

        self.hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        masked = int(screen.HGRBitmap.mask_and_shift_data(
            self.hgr.packed[0, 0], byte_offset=1))
        dots = screen.HGRBitmap.to_dots(masked, byte_offset=1)

        self.assertEqual(
            (
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BROWN,
                colours.HGRColours.BROWN,
                colours.HGRColours.BROWN,
                colours.HGRColours.BROWN,
                colours.HGRColours.BLACK,
            ),
            colours.dots_to_nominal_colour_pixels(
                18, dots, colours.HGRColours,
                init_phase=screen.HGRBitmap.PHASES[1])
        )

    def test_nominal_colours_sather_odd_3(self):
        """Cut off orange with violet to produce pink."""

        #                               PDCCBBAA
        self.main.page_offset[0, 1] = 0b11000000
        #                               PGGFFEED
        self.main.page_offset[0, 2] = 0b00000001

        self.hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        masked = int(screen.HGRBitmap.mask_and_shift_data(
            self.hgr.packed[0, 0], byte_offset=1))
        dots = screen.HGRBitmap.to_dots(masked, byte_offset=1)

        self.assertEqual(
            (
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BROWN,
                colours.HGRColours.ORANGE,
                colours.HGRColours.PINK,
                colours.HGRColours.PINK,
                colours.HGRColours.VIOLET,
            ),
            colours.dots_to_nominal_colour_pixels(
                18, dots, colours.HGRColours,
                init_phase=screen.HGRBitmap.PHASES[1])
        )

    def test_nominal_colours_sather_odd_4(self):
        """Cut off white with black to produce aqua."""

        #                               PDCCBBAA
        self.main.page_offset[0, 1] = 0b11100000
        #                               PGGFFEED
        self.main.page_offset[0, 2] = 0b00000000

        self.hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        masked = int(screen.HGRBitmap.mask_and_shift_data(
            self.hgr.packed[0, 0], byte_offset=1))
        dots = screen.HGRBitmap.to_dots(masked, byte_offset=1)

        self.assertEqual(
            (
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.DARK_BLUE,
                colours.HGRColours.MED_BLUE,
                colours.HGRColours.AQUA,
                colours.HGRColours.AQUA,
                colours.HGRColours.GREEN,
                colours.HGRColours.BROWN,
                colours.HGRColours.BLACK,
            ),
            colours.dots_to_nominal_colour_pixels(
                18, dots, colours.HGRColours,
                init_phase=screen.HGRBitmap.PHASES[1])
        )

    def test_nominal_colours_sather_odd_5(self):
        """Cut off blue-black with violet to produce bright violet.

        "Bright" here is because the sequence of pixels has high intensity
        Blue-Blue-Light Blue-Light Blue-Violet-Violet.
        """

        #                               PDCCBBAA
        self.main.page_offset[0, 1] = 0b10100000
        #                               PGGFFEED
        self.main.page_offset[0, 2] = 0b00000001

        self.hgr = screen.HGRBitmap(main_memory=self.main, palette=Palette.NTSC)

        masked = int(screen.HGRBitmap.mask_and_shift_data(
            self.hgr.packed[0, 0], byte_offset=1))
        dots = screen.HGRBitmap.to_dots(masked, byte_offset=1)

        self.assertEqual(
            (
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.BLACK,
                colours.HGRColours.DARK_BLUE,
                colours.HGRColours.MED_BLUE,
                colours.HGRColours.MED_BLUE,
                colours.HGRColours.LIGHT_BLUE,
                colours.HGRColours.LIGHT_BLUE,
                colours.HGRColours.VIOLET,
                colours.HGRColours.VIOLET
            ),
            colours.dots_to_nominal_colour_pixels(
                18, dots, colours.HGRColours,
                init_phase=screen.HGRBitmap.PHASES[1])
        )


if __name__ == '__main__':
    unittest.main()
