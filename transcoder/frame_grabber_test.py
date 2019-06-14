import unittest

import frame_grabber


class TestFileFrameGrabber(unittest.TestCase):
    def test_output_dir(self):
        self.assertEqual(
            "/foo/bar",
            frame_grabber.FileFrameGrabber._output_dir("/foo/bar.mp4")
        )

        self.assertEqual(
            "/foo/bar.blee",
            frame_grabber.FileFrameGrabber._output_dir("/foo/bar.blee.mp4")
        )

        self.assertEqual(
            "/foo/bar blee",
            frame_grabber.FileFrameGrabber._output_dir("/foo/bar blee.mp4")
        )


if __name__ == '__main__':
    unittest.main()
