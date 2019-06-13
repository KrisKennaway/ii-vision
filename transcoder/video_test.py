"""Tests for the video module."""

import unittest

import screen
import video


class TestVideo(unittest.TestCase):
    def test_diff_weights(self):
        fs = video.FrameSequencer(mode=video.Mode.DHGR)
        v = video.Video(fs, mode=video.Mode.DHGR)

        frame = screen.MemoryMap(screen_page=1)
        frame.page_offset[0, 0] = 0b1111111
        frame.page_offset[0, 1] = 0b1010101

        target_pixelmap = screen.DHGRBitmap(
            main_memory=v.memory_map,
            aux_memory=frame
        )
        self.assertEqual(
            0b0000000101010100000001111111,
            target_pixelmap.packed[0, 0])

        diff = v._diff_weights(v.pixelmap, target_pixelmap, is_aux=True)

        # Expect byte 0 to map to 0b00000000 01111111
        expect0 = target_pixelmap.edit_distances[0][0b0000000001111111]

        # Expect byte 2 to map to 0b000000000000 000101010100
        expect2 = target_pixelmap.edit_distances[2][0b000101010100]

        self.assertEqual(expect0, diff[0, 0])
        self.assertEqual(expect2, diff[0, 1])

        # Update aux frame
        v.aux_memory_map.page_offset = frame.page_offset
        v.pixelmap._pack()
        self.assertEqual(
            0b0000000101010100000001111111,
            v.pixelmap.packed[0, 0]
        )

        # Encode new aux frame
        frame = screen.MemoryMap(screen_page=1)
        frame.page_offset[0, 0] = 0b1101101
        frame.page_offset[0, 1] = 0b0110110

        target_pixelmap = screen.DHGRBitmap(
            main_memory=v.memory_map,
            aux_memory=frame
        )
        self.assertEqual(
            0b0000000011011000000001101101,
            target_pixelmap.packed[0, 0]
        )

        diff = v._diff_weights(v.pixelmap, target_pixelmap, is_aux=True)

        # Expect byte 0 to map to 0b01111111 01101101
        expect0 = target_pixelmap.edit_distances[0][0b0111111101101101]

        # Expect byte 2 to map to 0b000101010100 000011011000
        expect2 = target_pixelmap.edit_distances[2][0b0000101010100000011011000]

        self.assertEqual(expect0, diff[0, 0])
        self.assertEqual(expect2, diff[0, 1])


if __name__ == '__main__':
    unittest.main()
