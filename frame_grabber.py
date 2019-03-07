import os
import threading
import queue
import subprocess
from typing import Iterable

from PIL import Image
import skvideo.io
import numpy as np

import screen


def frame_grabber(filename: str) -> Iterable[np.array]:
    """Yields a sequence of Image frames in original resolution."""
    for frame_array in skvideo.io.vreader(filename):
        yield Image.fromarray(frame_array)


def hgr140_frame_grabber(filename: str) -> Iterable[screen.MemoryMap]:
    bm_cls = screen.HGR140Bitmap
    for frame in frame_grabber(filename):
        frame = frame.resize((bm_cls.XMAX, bm_cls.YMAX))
        frame = frame.convert("1")
        frame = np.array(frame)

        yield bm_cls(frame).to_bytemap().to_memory_map(screen_page=1)


def bmp2dhr_frame_grabber(filename: str) -> Iterable[screen.MemoryMap]:
    """Encode frame to HGR using bmp2dhr"""

    frame_dir = filename.split(".")[0]
    try:
        os.mkdir(frame_dir)
    except FileExistsError:
        pass

    q = queue.Queue(maxsize=10)

    def worker():
        for idx, frame in enumerate(frame_grabber(filename)):
            outfile = "%s/%08dC.BIN" % (frame_dir, idx)
            bmpfile = "%s/%08d.bmp" % (frame_dir, idx)

            try:
                os.stat(outfile)
            except FileNotFoundError:
                frame = frame.resize((280, 192))
                frame.save(bmpfile)

                subprocess.call(
                    ["/usr/local/bin/bmp2dhr", bmpfile, "hgr", "D9"])

                os.remove(bmpfile)

            frame = np.fromfile(outfile, dtype=np.uint8)
            q.put(frame)

        q.put(None)

    t = threading.Thread(target=worker)
    t.start()

    while True:
        frame = q.get()

        if frame is None:
            break

        yield screen.FlatMemoryMap(screen_page=1, data=frame).to_memory_map()
        q.task_done()

    t.join()