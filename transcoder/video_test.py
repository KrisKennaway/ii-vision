"""Tests for the video module."""

import unittest

import frame_grabber
import palette
import screen
import video
import video_mode


class TestVideo(unittest.TestCase):
    def test_diff_weights(self):
        fs = frame_grabber.FrameGrabber(mode=video_mode.VideoMode.DHGR)
        v = video.Video(
            fs, ticks_per_second=10000.,
            mode=video_mode.VideoMode.DHGR)

        frame = screen.MemoryMap(screen_page=1)
        frame.page_offset[0, 0] = 0b1111111
        frame.page_offset[0, 1] = 0b1010101

        target_pixelmap = screen.DHGRBitmap(
            palette=palette.Palette.NTSC,
            main_memory=v.memory_map,
            aux_memory=frame
        )
        self.assertEqual(
            0b0000000000101010100000001111111000,
            target_pixelmap.packed[0, 0])

        pal = palette.NTSCPalette

        diff = target_pixelmap.diff_weights(v.pixelmap, is_aux=True)

        # Expect byte 0 to map to 0b0001111111000
        expect0 = target_pixelmap.edit_distances(pal.ID)[0][0b0001111111000]

        # Expect byte 2 to map to 0b0001010101000
        expect2 = target_pixelmap.edit_distances(pal.ID)[2][0b0001010101000]

        self.assertEqual(expect0, diff[0, 0])
        self.assertEqual(expect2, diff[0, 1])

        # Update aux frame
        v.aux_memory_map.page_offset = frame.page_offset
        v.pixelmap._pack()
        self.assertEqual(
            0b0000000000101010100000001111111000,
            v.pixelmap.packed[0, 0]
        )

        # Encode new aux frame
        frame = screen.MemoryMap(screen_page=1)
        frame.page_offset[0, 0] = 0b1101101
        frame.page_offset[0, 1] = 0b0110110

        target_pixelmap = screen.DHGRBitmap(
            main_memory=v.memory_map,
            aux_memory=frame,
            palette=pal.ID
        )
        self.assertEqual(
            0b0000000000011011000000001101101000,
            target_pixelmap.packed[0, 0]
        )

        diff = target_pixelmap.diff_weights(v.pixelmap, is_aux=True)

        # Masked offset 0 changes from 0001111111000 to 0001101101000
        expect0 = target_pixelmap.edit_distances(pal.ID)[0][
            0b00011111110000001101101000]

        # Masked offset 2 changes from 0001010101000 to 0000110110000
        expect2 = target_pixelmap.edit_distances(pal.ID)[2][
            0b00010101010000000110110000]

        self.assertEqual(expect0, diff[0, 0])
        self.assertEqual(expect2, diff[0, 1])


if __name__ == '__main__':
    unittest.main()
