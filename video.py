import heapq
import random
import os
import threading
import queue
import subprocess

from typing import List, Iterator, Tuple

from PIL import Image
import numpy as np
import skvideo.io

import edit_distance
import opcodes
import screen


class Video:
    """Apple II screen memory map encoding a bitmapped frame."""

    CLOCK_SPEED = 1024 * 1024  # type: int

    def __init__(self, filename: str):
        self.filename = filename  # type: str

        self._reader = skvideo.io.FFmpegReader(filename)

        # Compute frame rate from input video
        # TODO: possible to compute time offset for each frame instead?
        data = skvideo.io.ffprobe(self.filename)['video']
        rate_data = data['@r_frame_rate'].split("/")  # e.g. 12000/1001
        self._input_frame_rate = float(
            rate_data[0]) / float(rate_data[1])  # type: float

        self.cycles_per_frame = (
                1024. * 1024 / self._input_frame_rate)  # type: float
        self.frame_number = 0  # type: int

        # Initialize empty screen
        self.memory_map = screen.MemoryMap(
            screen_page=1)  # type: screen.MemoryMap

        # Accumulates pending edit weights across frames
        self.update_priority = np.zeros((32, 256), dtype=np.int64)

    def tick(self, cycles: int) -> bool:
        if cycles > (self.cycles_per_frame * self.frame_number):
            self.frame_number += 1
            return True
        return False

    def _frame_grabber(self) -> Iterator[Image]:
        for frame_array in self._reader.nextFrame():
            yield Image.fromarray(frame_array)

    def frames(self) -> Iterator[screen.MemoryMap]:
        """Encode frame to HGR using bmp2dhr.

        We do the encoding in a background thread to parallelize.
        """

        frame_dir = self.filename.split(".")[0]
        try:
            os.mkdir(frame_dir)
        except FileExistsError:
            pass

        q = queue.Queue(maxsize=10)

        def worker():
            """Invoke bmp2dhr to encode input image frames and push to queue."""
            for _idx, _frame in enumerate(self._frame_grabber()):
                outfile = "%s/%08dC.BIN" % (frame_dir, _idx)
                bmpfile = "%s/%08d.bmp" % (frame_dir, _idx)

                try:
                    os.stat(outfile)
                except FileNotFoundError:
                    _frame = _frame.resize((280, 192))
                    _frame.save(bmpfile)

                    subprocess.call(
                        ["/usr/local/bin/bmp2dhr", bmpfile, "hgr", "D9"])

                    os.remove(bmpfile)

                _frame = np.fromfile(outfile, dtype=np.uint8)
                q.put(_frame)

            q.put(None)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        while True:
            frame = q.get()
            if frame is None:
                break

            yield screen.FlatMemoryMap(
                screen_page=1, data=frame).to_memory_map()
            q.task_done()

        t.join()

    def encode_frame(
            self, target: screen.MemoryMap
    ) -> Iterator[opcodes.Opcode]:
        """Update to match content of frame within provided budget."""

        print("Similarity %f" % (self.update_priority.mean()))
        yield from self._index_changes(self.memory_map, target)

    def _index_changes(
            self,
            source: screen.MemoryMap,
            target: screen.MemoryMap
    ) -> Iterator[Tuple[int, int, List[int]]]:
        """Transform encoded screen to sequence of change tuples."""

        diff_weights = self._diff_weights(source, target)

        # Clear any update priority entries that have resolved themselves
        # with new frame
        self.update_priority[diff_weights == 0] = 0

        # Halve existing weights to increase bias to new diffs.
        # In particular this means that existing updates with diff 1 will
        # become diff 0, i.e. will only be prioritized if they are still
        # diffs in the new frame.
        # self.update_priority >>= 1
        self.update_priority += diff_weights

        priorities = self._heapify_priorities()

        content_deltas = {}

        while priorities:
            _, _, page, offset = heapq.heappop(priorities)
            # Check whether we've already cleared this diff while processing
            # an earlier opcode
            if self.update_priority[page, offset] == 0:
                continue

            offsets = [offset]
            content = target.page_offset[page, offset]

            # Clear priority for the offset we're emitting
            self.update_priority[page, offset] = 0
            self.memory_map.page_offset[page, offset] = content

            # Need to find 3 more offsets to fill this opcode
            for o in self._compute_error(
                    page,
                    content,
                    target,
                    diff_weights,
                    content_deltas
            ):
                offsets.append(o)
                # Clear priority for the offset we're emitting
                self.update_priority[page, o] = 0
                self.memory_map.page_offset[page, o] = content

            # Pad to 4 if we didn't find enough
            for _ in range(len(offsets), 4):
                offsets.append(offsets[0])

            yield (page + 32, content, offsets)

        # If we run out of things to do, pad forever
        content = target.page_offset[(0, 0)]
        while True:
            yield (32, content, [0, 0, 0, 0])

    @staticmethod
    def _diff_weights(
            source: screen.MemoryMap,
            target: screen.MemoryMap
    ):
        return edit_distance.array_edit_weight(
            source.page_offset, target.page_offset)

    def _heapify_priorities(self) -> List:
        priorities = []
        it = np.nditer(self.update_priority, flags=['multi_index'])
        while not it.finished:
            priority = it[0]
            if not priority:
                it.iternext()
                continue

            page, offset = it.multi_index

            # Don't use deterministic order for page, offset
            nonce = random.random()
            priorities.append((-priority, nonce, page, offset))
            it.iternext()

        heapq.heapify(priorities)
        return priorities

    @staticmethod
    def _compute_delta(content, target, old):
        """
        This function is the critical path for the video encoding.
        """
        return edit_distance.content_edit_weight(content, target) - old

    _OFFSETS = np.arange(256)

    def _compute_error(self, page, content, target, old_error, content_deltas):
        offsets = []

        delta_screen = content_deltas.get(content)
        if delta_screen is None:
            delta_screen = self._compute_delta(
                content, target.page_offset, old_error)
            content_deltas[content] = delta_screen

        delta_page = delta_screen[page]
        cond = delta_page < 0
        candidate_offsets = self._OFFSETS[cond]
        priorities = self.update_priority[page][cond]

        l = [
            (-priorities[i], random.random(), candidate_offsets[i])
            for i in range(len(candidate_offsets))
        ]
        heapq.heapify(l)

        while l:
            _, _, o = heapq.heappop(l)
            offsets.append(o)
            if len(offsets) == 3:
                break

        return offsets
