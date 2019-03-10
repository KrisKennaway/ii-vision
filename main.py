import movie

MAX_OUT = 100 * 1024 * 1024
VIDEO_FPS = 30
APPLE_FPS = 30


def main():
    filename = "apple_ii_forever.m4v"

    # filename = "Computer Chronicles - 06x05 - The Apple II.mp4"
    # filename = (
    #     "Rick Astley - Never Gonna Give You Up (Official "
    #     "Music Video).mp4"
    # )

    m = movie.Movie(filename, audio_normalization=2.0)

    with open("out.bin", "wb") as out:
        for bytes_out, b in enumerate(m.emit_stream(m.encode())):
            out.write(bytearray([b]))

            if bytes_out >= MAX_OUT:
                break

        out.write(bytes(m.done()))


if __name__ == "__main__":
    main()
