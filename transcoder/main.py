"""Transcodes an input video file to ][-Vision format."""

import argparse

import movie
import palette
import video_mode

parser = argparse.ArgumentParser(
    description='Transcode videos to ][-Vision format.')
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
parser.add_argument(
    '--audio_bitrate', type=int, default=14700,
    help='Select output audio bitrate (Hz), controls video speed (Default: '
         '14700; try 22500 for //gs 2.8MHz mode)'
)
parser.add_argument(
    '--every_n_video_frames', type=int, default=2,
    help='Allows skipping frames of input video to lower effective output '
         'frame rate, which may give better quality for some videos.'
)
parser.add_argument(
    '--video_mode', type=str, choices=video_mode.VideoMode.__members__.keys(),
    default=video_mode.VideoMode.DHGR.name,
    help='Video display mode to encode for (HGR/DHGR)'
)
parser.add_argument(
    '--palette', type=str, choices=palette.Palette.__members__.keys(),
    default=palette.Palette.NTSC.name,
    help='Video palette to encode for (default=NTSC)'
)


def main(args):
    filename = args.input
    m = movie.Movie(
        filename,
        every_n_video_frames=args.every_n_video_frames,
        audio_bitrate=args.audio_bitrate,
        audio_normalization=args.audio_normalization,
        max_bytes_out=1024. * 1024 * args.max_output_mb,
        video_mode=video_mode.VideoMode[args.video_mode],
        palette=palette.Palette[args.palette],
    )

    print("Palette %s" % args.palette)

    print("Input frame rate = %f" % m.frame_grabber.input_frame_rate)

    if args.output:
        out_filename = args.output
    else:
        # Replace suffix with .a2m
        out_filename = ".".join(filename.split(".")[:-1] + ["a2m"])

    with open(out_filename, "wb") as out:
        for bytes_out, b in enumerate(m.emit_stream(m.encode())):
            out.write(bytearray([b]))


if __name__ == "__main__":
    main(parser.parse_args())
