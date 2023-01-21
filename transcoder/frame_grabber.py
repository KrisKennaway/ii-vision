"""Extracts sequence of still images from input video stream."""

import os
import subprocess
import multiprocessing
from typing import Iterator, Optional

import numpy as np
import skvideo.io
from PIL import Image, ImageEnhance

import colour
import screen
from palette import Palette
from video_mode import VideoMode
import convert.palette
import convert.dither_dhr
import convert.dither_pattern
import convert.image
import convert.screen


class FrameGrabber:
    def __init__(self, mode: VideoMode):
        self.video_mode = mode
        self.input_frame_rate = 30

    def frames(self) -> Iterator[screen.MemoryMap]:
        raise NotImplementedError


class FileFrameGrabber(FrameGrabber):
    def __init__(self, filename, mode: VideoMode, palette: Palette):
        super(FileFrameGrabber, self).__init__(mode)

        self.filename = filename  # type: str
        self.palette = palette  # type: Palette
        self._reader = skvideo.io.FFmpegReader(filename)

        # Compute frame rate from input video
        # TODO: possible to compute time offset for each frame instead?
        data = skvideo.io.ffprobe(self.filename)['video']
        rate_data = data['@r_frame_rate'].split("/")  # e.g. 12000/1001
        self.input_frame_rate = float(
            rate_data[0]) / float(rate_data[1])  # type: float

    def _frame_grabber(self) -> Iterator[Image.Image]:
        for frame_array in self._reader.nextFrame():
            yield Image.fromarray(frame_array)

    @staticmethod
    def _output_dir(filename, video_mode, palette) -> str:
        return "%s/%s/%s" % (
            ".".join(filename.split(".")[:-1]),
            video_mode.name,
            palette.name)

    def _frame_extractor(self, frame_dir):
        for _idx, _frame in enumerate(self._frame_grabber()):
            bmpfile = "%s/%08d.bmp" % (frame_dir, _idx)

            try:
                os.stat(bmpfile)
            except FileNotFoundError:
                # XXX HGR dimensions
                image = _frame.resize((560, 192), resample=Image.LANCZOS)
                # XXX gamma?
                img_filter = ImageEnhance.Brightness(image)
                image = img_filter.enhance(1.5)
                image.save(bmpfile)

            yield _idx

    def frames(self) -> Iterator[screen.MemoryMap]:
        """Encode frame sequence to (D)HGR memory images.

        We do the encoding in a worker pool to parallelize.
        """

        frame_dir = self._output_dir(
            self.filename, self.video_mode, self.palette)
        os.makedirs(frame_dir, exist_ok=True)

        global _converter
        if self.video_mode == VideoMode.DHGR_MONO:
            _converter = DHGRMonoFrameConverter(frame_dir)
        elif self.video_mode == VideoMode.DHGR:
            # XXX support palette
            _converter = DHGRFrameConverter(frame_dir=frame_dir)
        elif self.video_mode == VideoMode.HGR:
            _converter = HGRFrameConverter(
                frame_dir=frame_dir, palette_value=self.palette.value)

        pool = multiprocessing.Pool(10)
        for main, aux in pool.imap(_converter.convert, self._frame_extractor(
                frame_dir), chunksize=1):
            main_map = screen.FlatMemoryMap(
                screen_page=1, data=main).to_memory_map()
            aux_map = screen.FlatMemoryMap(
                screen_page=1, data=aux).to_memory_map() if aux else None

            yield main_map, aux_map


# Used in worker pool to receive global state
_converter = None  # type:Optional[FrameConverter]


class FrameConverter:
    def __init__(self, frame_dir):
        self.frame_dir = frame_dir

    @staticmethod
    def convert(idx):
        raise NotImplementedError


class HGRFrameConverter(FrameConverter):
    def __init__(self, frame_dir, palette_value):
        super(HGRFrameConverter, self).__init__(frame_dir)
        self.palette_arg = "P%d" % palette_value

    @staticmethod
    def convert(idx):
        outfile = "%s/%08dC.BIN" % (_converter.frame_dir, idx)
        bmpfile = "%s/%08d.bmp" % (_converter.frame_dir, idx)

        try:
            os.stat(outfile)
        except FileNotFoundError:
            subprocess.call([
                "/usr/local/bin/bmp2dhr", bmpfile, "hgr",
                _converter.palette_arg,
                "D9"  # Buckels dither
            ])

            os.remove(bmpfile)

        _main = np.fromfile(outfile, dtype=np.uint8)
        return _main, None


class DHGRFrameConverter(FrameConverter):
    def __init__(self, frame_dir):
        super(DHGRFrameConverter, self).__init__(frame_dir)

        self.rgb_to_cam16 = np.load(
            "transcoder/convert/data/rgb24_to_cam16ucs.npy")
        self.dither = convert.dither_pattern.PATTERNS[
            convert.dither_pattern.DEFAULT_PATTERN]()
        self.convert_palette = convert.palette.PALETTES['ntsc']()

    @staticmethod
    def convert(idx):
        print("Encoding %d" % idx)

        bmpfile = "%s/%08d.bmp" % (_converter.frame_dir, idx)

        mainfile = "%s/%08d.BIN" % (_converter.frame_dir, idx)
        auxfile = "%s/%08d.AUX" % (_converter.frame_dir, idx)

        try:
            os.stat(mainfile)
            os.stat(auxfile)
        except FileNotFoundError:
            convert_screen = convert.screen.DHGRScreen(
                _converter.convert_palette)
            # Open and resize source image
            image = convert.image.open(bmpfile)

            image = np.array(
                convert.image.resize(image, convert_screen.X_RES,
                                     convert_screen.Y_RES,
                                     gamma=2.4)).astype(np.float32) / 255

            bitmap = convert.dither_dhr.dither_image(
                convert_screen, image, _converter.dither, 6,
                False, _converter.rgb_to_cam16)

            output_screen = convert.screen.DHGRScreen(
                _converter.convert_palette)
            output_srgb = output_screen.bitmap_to_image_ntsc(bitmap)
            out_image = convert.image.resize(
                Image.fromarray(output_srgb), convert_screen.X_RES,
                convert_screen.Y_RES * 2, srgb_output=True)
            outfile = os.path.join(
                os.path.splitext(bmpfile)[0] + "-preview.png")
            out_image.save(outfile, "PNG")
            # out_image.show()

            convert_screen.pack(bitmap)
            with open(mainfile, "wb") as f:
                f.write(bytes(convert_screen.main))
            with open(auxfile, "wb") as f:
                f.write(bytes(convert_screen.aux))

        _main = np.fromfile(mainfile, dtype=np.uint8)
        _aux = np.fromfile(auxfile, dtype=np.uint8)

        return _main, _aux


class DHGRMonoFrameConverter(FrameConverter):
    @staticmethod
    def convert(_idx):
        bmpfile = "%s/%08d.bmp" % (_converter.frame_dir, _idx)
        dhrfile = "%s/%08d.dhr" % (_converter.frame_dir, _idx)

        try:
            os.stat(dhrfile)
        except FileNotFoundError:
            subprocess.call([
                "python", "convert.py", "dhr_mono", bmpfile, dhrfile
            ])
            # os.remove(bmpfile)

        dhr = np.fromfile(dhrfile, dtype=np.uint8)
        aux = dhr[:8192]
        main = dhr[8192:]
        return aux, main

#
