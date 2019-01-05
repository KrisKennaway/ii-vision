import skvideo.io
import skvideo.datasets
from PIL import Image
import numpy as np

import opcodes
import screen
import video

CYCLES = 1024 * 1024
MAX_OUT = 20 * 1024
VIDEO_FPS = 30
APPLE_FPS = 10


# Old naive XOR algorithm:
#
# stores=1894, content changes=15, page changes=365
# Frame 0, 2654 bytes, similarity = 0.850856
# stores=1750, content changes=19, page changes=444
# Frame 3, 2676 bytes, similarity = 0.903088
# stores=1648, content changes=20, page changes=501
# Frame 6, 2690 bytes, similarity = 0.922024
# stores=1677, content changes=18, page changes=486
# Frame 9, 2685 bytes, similarity = 0.912723
# stores=1659, content changes=18, page changes=497
# Frame 12, 2689 bytes, similarity = 0.923438
# stores=1681, content changes=17, page changes=485
# Frame 15, 2685 bytes, similarity = 0.922656
# stores=1686, content changes=17, page changes=482
# Frame 18, 2684 bytes, similarity = 0.921912
# stores=1669, content changes=17, page changes=492

# New
# stores=2260, content changes=277, page changes=125
# Frame 0, 3064 bytes, similarity = 0.874740
# stores=2162, content changes=325, page changes=131
# Frame 3, 3074 bytes, similarity = 0.925670
# stores=2241, content changes=313, page changes=102
# Frame 6, 3071 bytes, similarity = 0.936942
# stores=2265, content changes=313, page changes=90
# Frame 9, 3071 bytes, similarity = 0.931882
# stores=2225, content changes=334, page changes=91
# Frame 12, 3075 bytes, similarity = 0.929427
# stores=2216, content changes=342, page changes=89
# Frame 15, 3078 bytes, similarity = 0.919978
# stores=2222, content changes=339, page changes=88

# Optimized new
# Fullness = 1.384560, cycle_counter = 90738/104857 budget
# stores=1872, content changes=15, page changes=352
# Frame 0, 2606 bytes, similarity = 0.849219
# Fullness = 1.452588, cycle_counter = 110009/104857 budget
# stores=2163, content changes=28, page changes=472
# Frame 3, 3163 bytes, similarity = 0.924256
# Fullness = 1.577072, cycle_counter = 113843/104857 budget
# stores=2062, content changes=30, page changes=577
# Frame 6, 3276 bytes, similarity = 0.939918
# Fullness = 1.597466, cycle_counter = 106213/104857 budget
# stores=1899, content changes=29, page changes=550
# Frame 9, 3057 bytes, similarity = 0.928274
# Fullness = 1.615001, cycle_counter = 106008/104857 budget
# stores=1875, content changes=27, page changes=561
# Frame 12, 3051 bytes, similarity = 0.933854
# Fullness = 1.639691, cycle_counter = 106460/104857 budget
# stores=1855, content changes=30, page changes=575
# Frame 15, 3065 bytes, similarity = 0.929725
# Fullness = 1.635406, cycle_counter = 104583/104857 budget
# stores=1827, content changes=30, page changes=562

# TSP solver
# Fullness = 1.336189, cycle_counter = 87568/104857 budget
# stores=1872, content changes=320, page changes=32
# Frame 0, 2576 bytes, similarity = 0.849219
# Fullness = 1.386065, cycle_counter = 108771/104857 budget
# stores=2242, content changes=452, page changes=33
# Frame 3, 3212 bytes, similarity = 0.927604
# Fullness = 1.482284, cycle_counter = 112136/104857 budget
# stores=2161, content changes=552, page changes=33
# Frame 6, 3331 bytes, similarity = 0.943415
# Fullness = 1.501014, cycle_counter = 106182/104857 budget
# stores=2021, content changes=535, page changes=33
# Frame 9, 3157 bytes, similarity = 0.934263
# Fullness = 1.523818, cycle_counter = 106450/104857 budget
# stores=1995, content changes=554, page changes=33
# Frame 12, 3169 bytes, similarity = 0.939844
# Fullness = 1.543029, cycle_counter = 106179/104857 budget
# stores=1966, content changes=566, page changes=33
# Frame 15, 3164 bytes, similarity = 0.935231
# Fullness = 1.538659, cycle_counter = 104560/104857 budget
# stores=1941, content changes=554, page changes=33

# page first
# Fullness = 1.366463, cycle_counter = 89552/104857 budget
# stores=1872, content changes=352, page changes=32
# Frame 0, 2640 bytes, similarity = 0.849219
# Fullness = 1.413155, cycle_counter = 108440/104857 budget
# stores=2192, content changes=476, page changes=32
# Frame 3, 3208 bytes, similarity = 0.925744
# Fullness = 1.516888, cycle_counter = 112554/104857 budget
# stores=2120, content changes=583, page changes=32
# Frame 6, 3350 bytes, similarity = 0.942187
# Fullness = 1.535086, cycle_counter = 106115/104857 budget
# stores=1975, content changes=561, page changes=32
# Frame 9, 3161 bytes, similarity = 0.932106
# Fullness = 1.553913, cycle_counter = 106143/104857 budget
# stores=1951, content changes=575, page changes=32
# Frame 12, 3165 bytes, similarity = 0.937835
# Fullness = 1.571548, cycle_counter = 106047/104857 budget
# stores=1927, content changes=587, page changes=32
# Frame 15, 3165 bytes, similarity = 0.933259
# Fullness = 1.572792, cycle_counter = 104940/104857 budget
# stores=1906, content changes=581, page changes=32

def main():
    s = video.Video()

    videogen = skvideo.io.vreader("CoffeeCup-H264-75.mov")
    with open("out.bin", "wb") as out:
        bytes_out = 0

        # Estimated opcode overhead, i.e. ratio of extra cycle_counter from
        # opcodes
        fullness = 1.6

        screen_cls = screen.HGRBitmap

        # Assert that the opcode stream reconstructs the same screen
        ds = video.Video()
        decoder = opcodes.Decoder(ds.state)

        for idx, frame in enumerate(videogen):
            if idx % (VIDEO_FPS // APPLE_FPS):
                continue

            im = Image.fromarray(frame)
            im = im.resize((screen_cls.XMAX, screen_cls.YMAX))
            im = im.convert("1")
            im = np.array(im)
            # im.show()

            f = screen_cls(im)

            cycle_budget = int(CYCLES / APPLE_FPS)
            stream = bytes(s.update(f, cycle_budget, fullness))

            #print(" ".join("%02x(%02d)" % (b, b) for b in stream))

            fullness *= s.cycle_counter.cycles / cycle_budget
            print("Fullness = %f, cycle_counter = %d/%d budget" % (
                fullness, s.cycle_counter.cycles, cycle_budget))

            (num_content_stores, num_content_changes,
             num_page_changes, num_rle_bytes) = decoder.decode_stream(
                iter(stream))
            assert np.array_equal(ds.screen.bytemap, s.screen.bytemap), (
                    ds.screen.bytemap ^ s.screen.bytemap)
            print("stores=%d, content changes=%d, page changes=%d, "
                  "rle_bytes=%d" % (
                      num_content_stores, num_content_changes,
                      num_page_changes, num_rle_bytes))

            # assert that the screen decodes to the original bitmap
            bm = screen_cls.from_bytemap(s.screen).bitmap

            #           print(np.array(im)[0:5,0:5])
            #            print(bm[0:5,0:5])

            # print("Comparing bitmaps")
            # print(np.array(im))
            # print(bm)
            # print(s.screen)
            # assert np.array_equal(bm, im), np.ma.masked_array(
            #    bm, np.logical_not(np.logical_xor(bm, im)))

            # d = Image.fromarray(s.screen)
            # d.show()

            bytes_out += len(stream)
            if bytes_out > MAX_OUT:
                break

            print("Frame %d, %d bytes, similarity = %f" % (
                idx, len(stream), screen.bitmap_similarity(im, bm)))
            out.write(stream)

        out.write(bytes(s.done()))


if __name__ == "__main__":
    main()
