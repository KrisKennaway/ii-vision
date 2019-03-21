"""Tests for the video module."""

import unittest

import video


class TestHammingWeight(unittest.TestCase):
    def testHammingWeight(self):
        self.assertEqual(0, video.hamming_weight(0))
        self.assertEqual(1, video.hamming_weight(0b1))
        self.assertEqual(1, video.hamming_weight(0b100))
        self.assertEqual(3, video.hamming_weight(0b101100))
        self.assertEqual(7, video.hamming_weight(0b11111110))


class TestByteToColourString(unittest.TestCase):
    def testEncoding(self):
        self.assertEqual(
            "KKK0", video.byte_to_colour_string(0, is_odd_offset=False))
        self.assertEqual(
            "0KKK", video.byte_to_colour_string(0, is_odd_offset=True))

        self.assertEqual(
            "WWW1", video.byte_to_colour_string(0xff, is_odd_offset=False))
        self.assertEqual(
            "1WWW", video.byte_to_colour_string(0xff, is_odd_offset=True))

        self.assertEqual(
            "GGG0", video.byte_to_colour_string(0x2a, is_odd_offset=False))
        self.assertEqual(
            "1GGG", video.byte_to_colour_string(0x55, is_odd_offset=True))

        self.assertEqual(
            "OOO0", video.byte_to_colour_string(0xaa, is_odd_offset=False))
        self.assertEqual(
            "1OOO", video.byte_to_colour_string(0xd5, is_odd_offset=True))


class TestEditWeight(unittest.TestCase):
    def testTransposition(self):
        self.assertEqual("WKK0", video.byte_to_colour_string(
            0b00000011, is_odd_offset=False))
        self.assertEqual("KWK0", video.byte_to_colour_string(
            0b00001100, is_odd_offset=False))
        self.assertEqual(
            1, video.edit_weight(0b00000011, 0b00001100, is_odd_offset=False)
        )

        self.assertEqual("OWK1", video.byte_to_colour_string(
            0b11001110, is_odd_offset=False))
        self.assertEqual("OKW1", video.byte_to_colour_string(
            0b11110010, is_odd_offset=False))
        self.assertEqual(
            1, video.edit_weight(0b11001110, 0b11110010, is_odd_offset=False)
        )

    def testSubstitution(self):
        # Black has cost 5
        self.assertEqual("WKK0", video.byte_to_colour_string(
            0b00000011, is_odd_offset=False))
        self.assertEqual("KKK0", video.byte_to_colour_string(
            0b00000000, is_odd_offset=False))
        self.assertEqual(
            5, video.edit_weight(0b00000011, 0b00000000, is_odd_offset=False)
        )
        self.assertEqual(
            5, video.edit_weight(0b00000000, 0b00000011, is_odd_offset=False)
        )

        # Other colour has cost 1
        self.assertEqual(
            1, video.edit_weight(0b00000010, 0b00000011, is_odd_offset=False)
        )
        self.assertEqual(
            1, video.edit_weight(0b00000011, 0b00000010, is_odd_offset=False)
        )


# class TestVideo(unittest.TestCase):
#     def testEncodeEmptyFrame(self):
#         f = screen.MemoryMap(screen_page=1)
#         v = video.Video()
#
#         self.assertEqual([], list(v.encode_frame(f)))
#
#     def testEncodeOnePixel(self):
#         f = screen.HGR140Bitmap()
#         a = np.zeros((f.YMAX, f.XMAX), dtype=bool)
#         a[0, 0] = True
#
#         f = screen.HGR140Bitmap(a).to_memory_map(screen_page=1)
#
#         v = video.Video()
#
#         want = [
#             opcodes.SetPage(0x20),
#             opcodes.SetContent(0x03),
#             opcodes.Store(0x00),
#         ]
#         got = list(v.encode_frame(f))
#         self.assertListEqual(want, got)
#
#
# class TestIndexPage(unittest.TestCase):
#     def testFullPageSameValue(self):
#         """Constant data with nonzero weights should return single run"""
#         v = video.Video()
#
#         data = np.ones((256,), dtype=np.uint8)
#
#         # total_xor_difference, start_offset, content, run_length
#         want = [(256, 0, 1, 256)]
#         got = list(v._index_page(video.hamming_weight(data), data))
#
#         self.assertEqual(want, got)
#
#     def testFullPageZeroValue(self):
#         """Zero data with 0 weights should return nothing"""
#         v = video.Video()
#
#         data = np.zeros((256,), dtype=np.uint8)
#
#         # total_xor_difference, start_offset, content, run_length
#         want = []
#         got = list(v._index_page(video.hamming_weight(data), data))
#
#         self.assertEqual(want, got)
#
#     def testFullPageZeroValueWithDiff(self):
#         """Zero data with nonzero weights should return single run"""
#         v = video.Video()
#
#         old_data = np.ones((256,), dtype=np.uint8)
#
#         data = np.zeros((256,), dtype=np.uint8)
#
#         # total_xor_difference, start_offset, content, run_length
#         want = [(256, 0, 0, 256)]
#         got = list(v._index_page(video.hamming_weight(old_data), data))
#
#         self.assertEqual(want, got)
#
#     def testSingleRun(self):
#         """Single run of nonzero data"""
#         v = video.Video()
#
#         data = np.zeros((256,), dtype=np.uint8)
#         for i in range(5):
#             data[i] = 1
#
#         # total_xor_difference, start_offset, content, run_length
#         want = [(5, 0, 1, 5)]
#         got = list(v._index_page(video.hamming_weight(data), data))
#
#         self.assertEqual(want, got)
#
#     def testTwoRuns(self):
#         """Two consecutive runs of nonzero data"""
#         v = video.Video()
#
#         data = np.zeros((256,), dtype=np.uint8)
#         for i in range(5):
#             data[i] = 1
#         for i in range(5, 10):
#             data[i] = 2
#
#         # total_xor_difference, start_offset, content, run_length
#         want = [(5, 0, 1, 5), (5, 5, 2, 5)]
#         got = list(v._index_page(video.hamming_weight(data), data))
#
#         self.assertEqual(want, got)
#
#     def testShortRun(self):
#         """Run that is too short to encode as RLE opcode"""
#         v = video.Video()
#
#         data = np.zeros((256,), dtype=np.uint8)
#         for i in range(2):
#             data[i] = 1
#
#         # total_xor_difference, start_offset, content, run_length
#         want = [(1, 0, 1, 1), (1, 1, 1, 1)]
#         got = list(v._index_page(video.hamming_weight(data), data))
#
#         self.assertEqual(want, got)
#
#
# class TestEncodeDecode(unittest.TestCase):
#     def testEncodeDecode(self):
#         for _ in range(10):
#             s = video.Video(frame_rate=1)
#             screen_cls = screen.HGR140Bitmap
#
#             im = np.random.randint(
#                 0, 2, (screen_cls.YMAX, screen_cls.XMAX), dtype=np.bool)
#             f = screen_cls(im).to_memory_map(screen_page=1)
#
#             _ = bytes(s.emit_stream(s.encode_frame(f)))
#
#             # assert that the screen decodes to the original bitmap
#             bm = screen_cls.from_bytemap(s.memory_map.to_bytemap()).bitmap
#
#             self.assertTrue(np.array_equal(bm, im))
#
#     def testEncodeDecodeTwoFrames(self):
#
#         for _ in range(10):
#             s = video.Video(frame_rate=1)
#             screen_cls = screen.HGR140Bitmap
#
#             im = np.random.randint(
#                 0, 2, (screen_cls.YMAX, screen_cls.XMAX), dtype=np.bool)
#             f = screen_cls(im).to_memory_map(screen_page=1)
#             _ = bytes(s.emit_stream(s.encode_frame(f)))
#
#             im2 = np.random.randint(
#                 0, 2, (screen_cls.YMAX, screen_cls.XMAX), dtype=np.bool)
#             f = screen_cls(im2).to_memory_map(screen_page=1)
#             _ = bytes(s.emit_stream(s.encode_frame(f)))
#
#             # assert that the screen decodes to the original bitmap
#             bm = screen_cls.from_bytemap(s.memory_map.to_bytemap()).bitmap
#
#             self.assertTrue(np.array_equal(bm, im2))


if __name__ == '__main__':
    unittest.main()
