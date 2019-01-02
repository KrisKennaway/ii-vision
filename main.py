import skvideo.io
import skvideo.datasets
from PIL import Image
import numpy as np

import screen

CYCLES = 1024 * 1024
MAX_OUT = 20 * 1024
VIDEO_FPS = 30
APPLE_FPS = 10

# Old naive XOR algorithm:
#
#stores=1894, content changes=15, page changes=365
#Frame 0, 2654 bytes, similarity = 0.850856
#stores=1750, content changes=19, page changes=444
#Frame 3, 2676 bytes, similarity = 0.903088
#stores=1648, content changes=20, page changes=501
#Frame 6, 2690 bytes, similarity = 0.922024
#stores=1677, content changes=18, page changes=486
#Frame 9, 2685 bytes, similarity = 0.912723
#stores=1659, content changes=18, page changes=497
#Frame 12, 2689 bytes, similarity = 0.923438
#stores=1681, content changes=17, page changes=485
#Frame 15, 2685 bytes, similarity = 0.922656
#stores=1686, content changes=17, page changes=482
#Frame 18, 2684 bytes, similarity = 0.921912
#stores=1669, content changes=17, page changes=492

# New
#stores=2260, content changes=277, page changes=125
#Frame 0, 3064 bytes, similarity = 0.874740
#stores=2162, content changes=325, page changes=131
#Frame 3, 3074 bytes, similarity = 0.925670
#stores=2241, content changes=313, page changes=102
#Frame 6, 3071 bytes, similarity = 0.936942
#stores=2265, content changes=313, page changes=90
#Frame 9, 3071 bytes, similarity = 0.931882
#stores=2225, content changes=334, page changes=91
#Frame 12, 3075 bytes, similarity = 0.929427
#stores=2216, content changes=342, page changes=89
#Frame 15, 3078 bytes, similarity = 0.919978
#stores=2222, content changes=339, page changes=88

# Optimized new
#stores=1762, content changes=15, page changes=338
#Frame 0, 2468 bytes, similarity = 0.841034
#stores=2150, content changes=28, page changes=465
#Frame 3, 3136 bytes, similarity = 0.921987
#stores=2067, content changes=30, page changes=573
#Frame 6, 3273 bytes, similarity = 0.939583
#stores=1906, content changes=29, page changes=551
#Frame 9, 3066 bytes, similarity = 0.928237
#stores=1876, content changes=27, page changes=560
#Frame 12, 3050 bytes, similarity = 0.933705
#stores=1856, content changes=30, page changes=575
#Frame 15, 3066 bytes, similarity = 0.929539
#stores=1827, content changes=30, page changes=562

def main():
    s = screen.Screen()

    decoder = screen.Screen()

    videogen = skvideo.io.vreader("CoffeeCup-H264-75.mov")
    with open("out.bin", "wb") as out:
        bytes_out = 0

        # Estimated opcode overhead, i.e. ratio of extra cycles from opcodes
        fullness = 1.6

        for idx, frame in enumerate(videogen):
            if idx % (VIDEO_FPS // APPLE_FPS):
                continue
            im = Image.fromarray(frame)
            im = im.resize((screen.Frame.XMAX, screen.Frame.YMAX))
            im = im.convert("1")
            im = np.array(im)
            # im.show()

            f = screen.Frame(im)
            cycle_budget = int(CYCLES / APPLE_FPS)
            stream = bytes(s.update(f, cycle_budget, fullness))

            fullness *= s.cycles / cycle_budget
            print("Fullness = %f, cycles = %d/%d budget" % (
                fullness, s.cycles, cycle_budget))

            # Assert that the opcode stream reconstructs the same screen
            (num_content_stores, num_content_changes,
             num_page_changes) = decoder.from_stream(iter(stream))
            assert np.array_equal(decoder.screen, s.screen)
            print("stores=%d, content changes=%d, page changes=%d" % (
                num_content_stores, num_content_changes,
                num_page_changes))

            # print(" ".join("%02x(%02d)" % (b, b) for b in stream))
            # assert that the screen decodes to the original bitmap
            bm = s.to_bitmap()

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
                idx, len(stream), s.similarity(im,bm)))
            out.write(stream)

        out.write(bytes(s.done()))


if __name__ == "__main__":
    main()
