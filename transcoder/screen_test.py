"""Tests for the screen module."""

import unittest

import numpy as np

import screen


class TestDHGRBitmap(unittest.TestCase):
    def setUp(self) -> None:
        self.aux = screen.MemoryMap(screen_page=1)
        self.main = screen.MemoryMap(screen_page=1)

    def test_pixel_packing(self):
        #                              PBBBAAAA
        self.aux.page_offset[0, 0] = 0b11110101
        #                               PDDCCCCB
        self.main.page_offset[0, 0] = 0b01000011
        #                              PFEEEEDD
        self.aux.page_offset[0, 1] = 0b11110101
        #                               PGGGGFFF
        self.main.page_offset[0, 1] = 0b01000011

        dhgr = screen.DHGRBitmap(
            main_memory=self.main, aux_memory=self.aux)

        self.assertEqual(
            0b1000011111010110000111110101,
            dhgr.packed[0, 0]
        )

    def test_interleaved_byte_offset(self):
        self.assertEqual(
            0,
            screen.DHGRBitmap.interleaved_byte_offset(0, is_aux=True)
        )
        self.assertEqual(
            1,
            screen.DHGRBitmap.interleaved_byte_offset(0, is_aux=False)
        )
        self.assertEqual(
            2,
            screen.DHGRBitmap.interleaved_byte_offset(1, is_aux=True)
        )
        self.assertEqual(
            3,
            screen.DHGRBitmap.interleaved_byte_offset(1, is_aux=False)
        )

    def test_mask_and_shift_data(self):
        int8_max = 2 ** 8 - 1
        int12_max = 2 ** 12 - 1
        int32_max = 2 ** 32 - 1

        dhgr = screen.DHGRBitmap(
            main_memory=self.main, aux_memory=self.aux)

        self.assertEqual(
            int8_max,
            dhgr.mask_and_shift_data(
                screen.DHGRBitmap.BYTE_MASK32[0], 0
            )
        )
        self.assertEqual(
            int12_max,
            dhgr.mask_and_shift_data(
                screen.DHGRBitmap.BYTE_MASK32[1], 1
            )
        )
        self.assertEqual(
            int12_max,
            dhgr.mask_and_shift_data(
                screen.DHGRBitmap.BYTE_MASK32[2], 2
            )
        )
        self.assertEqual(
            int8_max,
            dhgr.mask_and_shift_data(
                screen.DHGRBitmap.BYTE_MASK32[3], 3
            )
        )

        # Now check complement, i.e. no bits taken from outside expected range

        self.assertEqual(
            0,
            dhgr.mask_and_shift_data(
                ~screen.DHGRBitmap.BYTE_MASK32[0] & int32_max, 0
            )
        )
        self.assertEqual(
            0,
            dhgr.mask_and_shift_data(
                ~screen.DHGRBitmap.BYTE_MASK32[1] & int32_max, 1
            )
        )
        self.assertEqual(
            0,
            dhgr.mask_and_shift_data(
                ~screen.DHGRBitmap.BYTE_MASK32[2] & int32_max, 2
            )
        )
        self.assertEqual(
            0,
            dhgr.mask_and_shift_data(
                ~screen.DHGRBitmap.BYTE_MASK32[3] & int32_max, 3
            )
        )

    def test_masked_update(self):
        self.assertEqual(
            0b0000000000000000000001111111,
            screen.DHGRBitmap.masked_update(0, 0x00000000, 0xff)
        )
        self.assertEqual(
            0b0000000000000011111110000000,
            screen.DHGRBitmap.masked_update(1, 0x00000000, 0xff)
        )
        self.assertEqual(
            0b0000000111111100000000000000,
            screen.DHGRBitmap.masked_update(2, 0x00000000, 0xff)
        )
        self.assertEqual(
            0b1111111000000000000000000000,
            screen.DHGRBitmap.masked_update(3, 0x00000000, 0xff)
        )

        # Now test masking out existing values

        int28_max = 2 ** 28 - 1

        self.assertEqual(
            0b1111111111111111111110000000,
            screen.DHGRBitmap.masked_update(0, int28_max, 0x00)
        )
        self.assertEqual(
            0b1111111111111100000001111111,
            screen.DHGRBitmap.masked_update(1, int28_max, 0x00)
        )
        self.assertEqual(
            0b1111111000000011111111111111,
            screen.DHGRBitmap.masked_update(2, int28_max, 0x00)
        )
        self.assertEqual(
            0b0000000111111111111111111111,
            screen.DHGRBitmap.masked_update(3, int28_max, 0x00)
        )

        # Test that masked_update can broadcast to numpy arrays
        ary = np.zeros((2, 2), dtype=np.uint32)
        self.assertTrue(np.array_equal(
            np.array([[0x7f, 0x7f], [0x7f, 0x7f]], dtype=np.uint32),
            screen.DHGRBitmap.masked_update(0, ary, 0xff)
        ))

    def test_apply(self):
        dhgr = screen.DHGRBitmap(
            main_memory=self.main, aux_memory=self.aux)

        dhgr.apply(page=0, offset=0, is_aux=True, value=0xff)
        self.assertEqual(0x0000007f, dhgr.packed[0, 0])

        dhgr.apply(page=12, offset=36, is_aux=True, value=0xff)
        self.assertEqual(0x0000007f, dhgr.packed[12, 18])

        # Now update the next aux offset in same uint32
        dhgr.apply(page=12, offset=37, is_aux=True, value=0xff)
        self.assertEqual(
            0b0000000111111100000001111111,
            dhgr.packed[12, 18]
        )

        dhgr.apply(page=12, offset=37, is_aux=False, value=0b1010101)
        self.assertEqual(
            0b1010101111111100000001111111,
            dhgr.packed[12, 18]
        )

        dhgr.apply(page=12, offset=36, is_aux=False, value=0b0001101)
        self.assertEqual(
            0b1010101111111100011011111111,
            dhgr.packed[12, 18]
        )


if __name__ == '__main__':
    unittest.main()
