"""Transcodes an input video file to Apple II format."""

import sys

import movie

MAX_OUT = 100 * 1024 * 1024


# TODO: flags
# - max out

def main(argv):
    filename = argv[1]
    m = movie.Movie(filename)

    if len(argv) >= 3:
        out_filename = argv[2]
    else:
        out_filename = ".".join(filename.split(".")[:-1] + ["a2m"])

    with open(out_filename, "wb") as out:
        for bytes_out, b in enumerate(m.emit_stream(m.encode())):
            out.write(bytearray([b]))

            if bytes_out >= MAX_OUT:
                break

        out.write(bytes(m.done()))


if __name__ == "__main__":
    main(sys.argv)
