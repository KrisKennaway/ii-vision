import skvideo.io
import skvideo.datasets
from PIL import Image
import numpy as np

import screen

CYCLES = 1024 * 1024
MAX_OUT = 20 * 1024
VIDEO_FPS = 30
APPLE_FPS = 5


def main():
    s = screen.Screen()

    decoder = screen.Screen()

    videogen = skvideo.io.vreader("CoffeeCup-H264-75.mov")
    with open("out.bin", "wb") as out:
        bytes_out = 0
        for idx, frame in enumerate(videogen):
            if idx % (VIDEO_FPS // APPLE_FPS):
                continue
            im = Image.fromarray(frame)
            im = im.resize((screen.Frame.XMAX, screen.Frame.YMAX))
            im = im.convert("1")
            im = np.array(im)
            # im.show()

            f = screen.Frame(im)
            stream = bytes(s.update(f, CYCLES // APPLE_FPS))

            # Assert that the opcode stream reconstructs the same screen
            decoder.from_stream(iter(stream))
            assert np.array_equal(decoder.screen, s.screen)

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
