import unittest

import frame_grabber
import palette
import video_mode


class TestFileFrameGrabber(unittest.TestCase):
    def test_output_dir(self):
        self.assertEqual(
            "/foo/bar/DHGR/NTSC",
            frame_grabber.FileFrameGrabber._output_dir(
                "/foo/bar.mp4", video_mode.VideoMode.DHGR, palette.Palette.NTSC
            )
        )

        self.assertEqual(
            "/foo/bar.blee/HGR/IIGS",
            frame_grabber.FileFrameGrabber._output_dir(
                "/foo/bar.blee.mp4",
                video_mode.VideoMode.HGR,
                palette.Palette.IIGS
            )
        )

        self.assertEqual(
            "/foo/bar blee/DHGR/IIGS",
            frame_grabber.FileFrameGrabber._output_dir(
                "/foo/bar blee.mp4",
                video_mode.VideoMode.DHGR,
                palette.Palette.IIGS
            )
        )


if __name__ == '__main__':
    unittest.main()
