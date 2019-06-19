"""Encode a sequence of images as an optimized stream of screen changes."""

import enum
import heapq
import os
import queue
import random
import subprocess
import threading
from typing import List, Iterator, Tuple

# import hitherdither
import numpy as np
import skvideo.io
from PIL import Image

import edit_distance
import opcodes
import screen


class Mode(enum.Enum):
    HGR = 0
    DHGR = 1


class Video:
    """Apple II screen memory map encoding a bitmapped frame."""

    CLOCK_SPEED = 1024 * 1024  # type: int

    def __init__(
            self,
            filename: str,
            ticks_per_second: float,
            mode: Mode = Mode.HGR,
    ):
        self.filename = filename  # type: str
        self.mode = mode  # type: Mode
        self.ticks_per_second = ticks_per_second  # type: float

        self._reader = skvideo.io.FFmpegReader(filename)

        # Compute frame rate from input video
        # TODO: possible to compute time offset for each frame instead?
        data = skvideo.io.ffprobe(self.filename)['video']
        rate_data = data['@r_frame_rate'].split("/")  # e.g. 12000/1001
        self.input_frame_rate = float(
            rate_data[0]) / float(rate_data[1])  # type: float

        self.ticks_per_frame = (
            self.ticks_per_second / self.input_frame_rate)  # type: float
        self.frame_number = 0  # type: int

        # Initialize empty screen
        self.memory_map = screen.MemoryMap(
            screen_page=1)  # type: screen.MemoryMap
        if self.mode == mode.DHGR:
            self.aux_memory_map = screen.MemoryMap(
                screen_page=1)  # type: screen.MemoryMap

        # Accumulates pending edit weights across frames
        self.update_priority = np.zeros((32, 256), dtype=np.int64)
        if self.mode == mode.DHGR:
            self.aux_update_priority = np.zeros((32, 256), dtype=np.int64)

    def tick(self, ticks: int) -> bool:
        if ticks >= (self.ticks_per_frame * self.frame_number):
            self.frame_number += 1
            return True
        return False

    def _frame_grabber(self) -> Iterator[Image.Image]:
        for frame_array in self._reader.nextFrame():
            yield Image.fromarray(frame_array)

    @staticmethod
    def _rgb(r, g, b):
        return (r << 16) + (g << 8) + b

    # def dither_framesframes(self) -> Iterator[screen.MemoryMap]:
    #     palette = hitherdither.palette.Palette(
    #         [
    #             self._rgb(0,0,0),           # black */
    #             self._rgb(148,12,125),  # red - hgr 0*/
    #             self._rgb(32,54,212),   # dk blue - hgr 0 */
    #             self._rgb(188,55,255),  # purple - default HGR overlay color */
    #             self._rgb(51,111,0),    # dk green - hgr 0 */
    #             self._rgb(126,126,126), # gray - hgr 0 */
    #             self._rgb(7,168,225),   # med blue - alternate HGR overlay
    #             # color */
    #             self._rgb(158,172,255), # lt blue - hgr 0 */
    #             self._rgb(99,77,0),     # brown - hgr 0 */
    #             self._rgb(249,86,29),   # orange */
    #             self._rgb(126,126,126), # grey - hgr 0 */
    #             self._rgb(255,129,236), # pink - hgr 0 */
    #             self._rgb(67,200,0),    # lt green */
    #             self._rgb(221,206,23),  # yellow - hgr 0 */
    #             self._rgb(93,248,133),  # aqua - hgr 0 */
    #             self._rgb(255,255,255)  # white
    #         ]
    #     )
    #     for _idx, _frame in enumerate(self._frame_grabber()):
    #         if _idx % 60 == 0:
    #             img_dithered = hitherdither.ordered.yliluoma.yliluomas_1_ordered_dithering(
    #                 _frame.resize((280,192), resample=Image.NEAREST),
    #                 palette, order=8)
    #
    #             yield img_dithered

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
                    "P0",  # Kegs32 RGB Color palette(for //gs playback)
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
                    "/usr/local/bin/bmp2dhr", bmpfile, "dhgr",
                    "P0",  # Kegs32 RGB Color palette (for //gs playback)
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
                if self.mode == Mode.DHGR:
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

    def encode_frame(
            self, target: screen.MemoryMap,
            memory_map: screen.MemoryMap,
            update_priority: np.array,
    ) -> Iterator[opcodes.Opcode]:
        """Update to match content of frame within provided budget."""

        print("Similarity %f" % (update_priority.mean()))
        yield from self._index_changes(memory_map, target, update_priority)

    def _index_changes(
            self,
            source: screen.MemoryMap,
            target: screen.MemoryMap,
            update_priority: np.array
    ) -> Iterator[Tuple[int, int, List[int]]]:
        """Transform encoded screen to sequence of change tuples."""

        diff_weights = self._diff_weights(source, target)

        # Clear any update priority entries that have resolved themselves
        # with new frame
        update_priority[diff_weights == 0] = 0

        # Halve existing weights to increase bias to new diffs.
        # In particular this means that existing updates with diff 1 will
        # become diff 0, i.e. will only be prioritized if they are still
        # diffs in the new frame.
        # self.update_priority >>= 1
        update_priority += diff_weights

        priorities = self._heapify_priorities(update_priority)

        content_deltas = {}

        while priorities:
            _, _, page, offset = heapq.heappop(priorities)
            # Check whether we've already cleared this diff while processing
            # an earlier opcode
            if update_priority[page, offset] == 0:
                continue

            offsets = [offset]
            content = target.page_offset[page, offset]

            # Clear priority for the offset we're emitting
            update_priority[page, offset] = 0
            source.page_offset[page, offset] = content
            diff_weights[page, offset] = 0

            # Make sure we don't emit this offset as a side-effect of some
            # other offset later.
            for cd in content_deltas.values():
                cd[page, offset] = 0

            # Need to find 3 more offsets to fill this opcode
            for o in self._compute_error(
                    page,
                    content,
                    target,
                    diff_weights,
                    content_deltas
            ):
                offsets.append(o)

                # Compute new edit distance between new content and target
                # byte, so we can reinsert with this value
                p = edit_distance.edit_weight(
                    content, target.page_offset[page, o], o % 2 == 1,
                    error=False)

                # Update priority for the offset we're emitting
                update_priority[page, o] = p  # 0

                source.page_offset[page, o] = content

                if p:
                    # This content byte introduced an error, so put back on the
                    # heap in case we can get back to fixing it exactly
                    # during this frame.  Otherwise we'll get to it later.
                    heapq.heappush(
                        priorities, (-p, random.random(), page, offset))

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
        return edit_distance.screen_edit_distance(
            source.page_offset, target.page_offset)

    def _heapify_priorities(self, update_priority: np.array) -> List:
        priorities = []
        it = np.nditer(update_priority, flags=['multi_index'])
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
        return edit_distance.byte_screen_error_distance(content, target) - old

    _OFFSETS = np.arange(256)

    def _compute_error(self, page, content, target, old_error, content_deltas):
        offsets = []

        # TODO: move this up into parent
        delta_screen = content_deltas.get(content)
        if delta_screen is None:
            delta_screen = self._compute_delta(
                content, target.page_offset, old_error)
            content_deltas[content] = delta_screen

        delta_page = delta_screen[page]
        cond = delta_page < 0
        candidate_offsets = self._OFFSETS[cond]
        priorities = delta_page[cond]

        l = [
            (priorities[i], random.random(), candidate_offsets[i])
            for i in range(len(candidate_offsets))
        ]
        heapq.heapify(l)

        while l:
            _, _, o = heapq.heappop(l)
            offsets.append(o)

            # Make sure we don't end up considering this (page, offset) again
            # until the next image frame.  Even if a better match comes along,
            # it's probably better to fix up some other byte.
            for cd in content_deltas.values():
                cd[page, o] = 0

            if len(offsets) == 3:
                break

        return offsets
