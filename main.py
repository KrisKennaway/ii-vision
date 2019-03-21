"""Transcodes an input video file to ][Vision format."""

import argparse

import movie


parser = argparse.ArgumentParser(
    description='Transcode videos to ][Vision format.')
parser.add_argument(
    'input', help='Path to input video file.')
parser.add_argument(
    '--output', default=None, help='Path to output video file.')
parser.add_argument(
    '--max_output_mb', type=float, default=0,
    help='Maximum number of MB to output (0 = Unlimited).'
)
parser.add_argument(
    '--audio_normalization', type=float, default=None,
    help='Override auto-detected multiplier for audio normalization.'
)


def main(args):
    filename = args.input
    m = movie.Movie(
        filename, audio_normalization=args.audio_normalization)

    max_bytes_out = 1024. * 1024 * args.max_output_mb

    if args.output:
        out_filename = args.output
    else:
        # Replace suffix with .a2m
        out_filename = ".".join(filename.split(".")[:-1] + ["a2m"])

    with open(out_filename, "wb") as out:
        for bytes_out, b in enumerate(m.emit_stream(m.encode())):
            out.write(bytearray([b]))

            if max_bytes_out and bytes_out >= max_bytes_out:
                break

        out.write(bytes(m.done()))


if __name__ == "__main__":
    main(parser.parse_args())
