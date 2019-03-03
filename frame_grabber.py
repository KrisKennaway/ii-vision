from typing import Iterable

from PIL import Image
import skvideo.io
import numpy as np

import screen


def hgr140_frame_grabber(filename: str) -> Iterable[screen.MemoryMap]:
    bm_cls = screen.HGR140Bitmap
    for frame in skvideo.io.vreader(filename):
        im = Image.fromarray(frame)
        im = im.resize((bm_cls.XMAX, bm_cls.YMAX))
        im = im.convert("1")
        im = np.array(im)

        yield bm_cls(im).to_bytemap().to_memory_map(screen_page=1)


def bmp_frame_grabber(filename: str) -> Iterable[screen.MemoryMap]:
    idx = 0
    while True:
        fn = "%s-%08dC.BIN" % (filename, idx)
        frame = np.fromfile(fn, dtype=np.uint8)

        yield screen.FlatMemoryMap(screen_page=1, data=frame).to_memory_map()
        idx += 1
