from typing import Iterable

import threading
import queue

import numpy
import skvideo.io


def frame_sequence(filename: str) -> Iterable[numpy.ndarray]:
    yield from skvideo.io.vreader(filename)


# Version of the above that delegates decoding to a background thread; not
# clear that it's more efficient though
def frame_sequence2(filename: str) -> Iterable[numpy.ndarray]:
    q = queue.Queue()

    def worker():
        for f in skvideo.io.vreader(filename):
            q.put(f)
        q.put(None)

    t = threading.Thread(target=worker)
    t.start()

    while True:
        frame = q.get()
        if frame is None:
            break
        yield frame
        q.task_done()

    t.join()
