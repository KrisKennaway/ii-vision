"""Extracts sequence of still images from input video stream."""

import os
import queue
import subprocess
import threading
from typing import Iterator

import numpy as np
import skvideo.io
from PIL import Image

import screen
from video_mode import VideoMode


class FrameGrabber:
    def __init__(self, mode: VideoMode):
        self.video_mode = mode
        self.input_frame_rate = 30

    def frames(self) -> Iterator[screen.MemoryMap]:
        raise NotImplementedError


class FileFrameGrabber(FrameGrabber):
    def __init__(self, filename, mode: VideoMode):
        super(FileFrameGrabber, self).__init__(mode)

        self.filename = filename  # type: str
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
    def _output_dir(filename) -> str:
        return ".".join(filename.split(".")[:-1])

    def frames(self) -> Iterator[screen.MemoryMap]:
        """Encode frame to HGR using bmp2dhr.

        We do the encoding in a background thread to parallelize.
        """

        frame_dir = self._output_dir(self.filename)
        try:
            os.mkdir(frame_dir)
        except FileExistsError:
            pass

        q = queue.Queue(maxsize=10)

        def _hgr_decode(_idx, _frame):
            outfile = "%s/%08dC.BIN" % (frame_dir, _idx)
            bmpfile = "%s/%08d.bmp" % (frame_dir, _idx)

            try:
                os.stat(outfile)
            except FileNotFoundError:
                _frame = _frame.resize((280, 192), resample=Image.LANCZOS)
                _frame.save(bmpfile)

                # TODO: parametrize palette
                subprocess.call([
                    "/usr/local/bin/bmp2dhr", bmpfile, "hgr",
                    "P5",
                    # "P0",  # Kegs32 RGB Color palette(for //gs playback)
                    "D9"  # Buckels dither
                ])

                os.remove(bmpfile)

            _main = np.fromfile(outfile, dtype=np.uint8)

            return _main, None

        def _dhgr_decode(_idx, _frame):
            mainfile = "%s/%08d.BIN" % (frame_dir, _idx)
            auxfile = "%s/%08d.AUX" % (frame_dir, _idx)

            bmpfile = "%s/%08d.bmp" % (frame_dir, _idx)

            try:
                os.stat(mainfile)
                os.stat(auxfile)
            except FileNotFoundError:
                _frame = _frame.resize((280, 192), resample=Image.LANCZOS)
                _frame.save(bmpfile)

                # TODO: parametrize palette
                subprocess.call([
                    "/usr/local/bin/bmp2dhr", bmpfile, "dhgr",  # "v",
                    "P5",  # "P0",  # Kegs32 RGB Color palette (for //gs
                    # playback)
                    "A",  # Output separate .BIN and .AUX files
                    "D9"  # Buckels dither
                ])

                os.remove(bmpfile)

            _main = np.fromfile(mainfile, dtype=np.uint8)
            _aux = np.fromfile(auxfile, dtype=np.uint8)

            return _main, _aux

        def worker():
            """Invoke bmp2dhr to encode input image frames and push to queue."""
            for _idx, _frame in enumerate(self._frame_grabber()):
                if self.video_mode == VideoMode.DHGR:
                    res = _dhgr_decode(_idx, _frame)
                else:
                    res = _hgr_decode(_idx, _frame)
                q.put(res)

            q.put((None, None))

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        while True:
            main, aux = q.get()
            if main is None:
                break

            main_map = screen.FlatMemoryMap(
                screen_page=1, data=main).to_memory_map()
            if aux is None:
                aux_map = None
            else:
                aux_map = screen.FlatMemoryMap(
                    screen_page=1, data=aux).to_memory_map()
            yield (main_map, aux_map)
            q.task_done()

        t.join()
