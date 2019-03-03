import frame_grabber
import opcodes
import screen
import video

MAX_OUT = 100 * 1024 * 1024
VIDEO_FPS = 30
APPLE_FPS = 7


def main():
    #frames = frame_grabber.hgr140_frame_grabber(
    #    "Computer Chronicles - 06x05 - The Apple II.mp4")

    frames = frame_grabber.bmp_frame_grabber("cc/CC")

    bytes_out = 0
    sims = []
    out_frames = 0

    s = video.Video(APPLE_FPS)

    # Assert that the opcode stream reconstructs the same screen
    ds = video.Video()
    decoder = opcodes.Decoder(s.state)

    with open("out.bin", "wb") as out:
        for idx, frame in enumerate(frames):
            if idx % (VIDEO_FPS // APPLE_FPS):
                continue

            stream = bytes(s.emit_stream(s.encode_frame(frame)))

            bytes_out += len(stream)
            bytes_left = MAX_OUT - bytes_out

            sim = screen.bitmap_similarity(
                screen.HGRBitmap.from_bytemap(s.memory_map.to_bytemap()).bitmap,
                screen.HGRBitmap.from_bytemap(frame.to_bytemap()).bitmap)
            sims.append(sim)
            out_frames += 1
            print("Frame %d, %d bytes, similarity = %f" % (
                idx, len(stream), sim))
            out.write(stream[:bytes_left])

            if bytes_left <= 0:
                out.write(bytes(s.done()))
                break

    print("Median similarity: %f" % sorted(sims)[out_frames//2])


if __name__ == "__main__":
    main()
