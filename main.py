from PIL import Image
import numpy as np

import frame_sequence
import opcodes
import screen
import video

MAX_OUT = 1 * 1024 * 1024
VIDEO_FPS = 30
APPLE_FPS = 10


def main():
    frames = frame_sequence.frame_sequence(
        "Computer Chronicles - 06x05 - The Apple II.mp4")

    bytes_out = 0

    s = video.Video(APPLE_FPS)
    screen_cls = screen.HGR140Bitmap

    # Assert that the opcode stream reconstructs the same screen
    ds = video.Video()
    decoder = opcodes.Decoder(s.state)

    with open("out.bin", "wb") as out:
        for idx, frame in enumerate(frames):
            if idx % (VIDEO_FPS // APPLE_FPS):
                continue

            im = Image.fromarray(frame)
            im = im.resize((screen_cls.XMAX, screen_cls.YMAX))
            im = im.convert("1")
            im = np.array(im)
            # im.show()

            f = screen_cls(im)

            stream = bytes(s.emit_stream(s.encode_frame(f)))

            # assert that the screen decodes to the original bitmap
            bm = screen_cls.from_bytemap(s.screen).bitmap

            # print("Comparing bitmaps")
            # print(np.array(im))
            # print(bm)
            # print(s.screen)
            #np.set_printoptions(threshold=100000000)

            #assert np.array_equal(bm, im), np.ma.masked_array(
            #    bm, np.logical_not(np.logical_xor(bm, im)))

            # d = Image.fromarray(s.screen)
            # d.show()

            bytes_out += len(stream)
            bytes_left = MAX_OUT - bytes_out

            print("Frame %d, %d bytes, similarity = %f" % (
                idx, len(stream), screen.bitmap_similarity(im, bm)))
            out.write(stream[:bytes_left])

            if bytes_left <= 0:
                out.write(bytes(s.done()))
                break



if __name__ == "__main__":
    main()
