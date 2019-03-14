import functools
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
import weighted_levenshtein

import opcodes
import screen


def hamming_weight(n):
    """Compute hamming weight of 8-bit int"""
    n = (n & 0x55) + ((n & 0xAA) >> 1)
    n = (n & 0x33) + ((n & 0xCC) >> 2)
    n = (n & 0x0F) + ((n & 0xF0) >> 4)
    return n

# TODO: what about increasing transposition cost?  Might be better to have
# any pixel at the right place even if the wrong colour?

substitute_costs = np.ones((128, 128), dtype=np.float64)
error_substitute_costs = np.ones((128, 128), dtype=np.float64)

# Penalty for turning on/off a black bit
for c in "01GVWOB":
    substitute_costs[(ord('K'), ord(c))] = 1
    substitute_costs[(ord(c), ord('K'))] = 1
    error_substitute_costs[(ord('K'), ord(c))] = 5
    error_substitute_costs[(ord(c), ord('K'))] = 5

# Penalty for changing colour
for c in "01GVWOB":
    for d in "01GVWOB":
        substitute_costs[(ord(c), ord(d))] = 1
        substitute_costs[(ord(d), ord(c))] = 1
        error_substitute_costs[(ord(c), ord(d))] = 5
        error_substitute_costs[(ord(d), ord(c))] = 5

insert_costs = np.ones(128, dtype=np.float64) * 1000
delete_costs = np.ones(128, dtype=np.float64) * 1000


def _edit_weight(a: int, b: int, is_odd_offset: bool, error: bool):
    a_pixels = byte_to_colour_string(a, is_odd_offset)
    b_pixels = byte_to_colour_string(b, is_odd_offset)

    dist = weighted_levenshtein.dam_lev(
        a_pixels, b_pixels,
        insert_costs=insert_costs,
        delete_costs=delete_costs,
        substitute_costs=error_substitute_costs if error else substitute_costs,
    )
    return np.int64(dist)


def edit_weight_matrixes(error: bool) -> np.array:
    ewm = np.zeros(shape=(256, 256, 2), dtype=np.int64)
    for a in range(256):
        for b in range(256):
            for is_odd_offset in (False, True):
                ewm[a, b, int(is_odd_offset)] = _edit_weight(
                    a, b, is_odd_offset, error)

    return ewm


_ewm = edit_weight_matrixes(False)
_error_ewm = edit_weight_matrixes(True)


@functools.lru_cache(None)
def edit_weight(a: int, b: int, is_odd_offset: bool, error: bool):
    e = _error_ewm if error else _ewm
    return e[a, b, int(is_odd_offset)]


#
# @functools.lru_cache(None)
# def edit_weight_old(a: int, b: int, is_odd_offset: bool):
#     a_pixels = byte_to_colour_string(a, is_odd_offset)
#     b_pixels = byte_to_colour_string(b, is_odd_offset)
#
#     dist = weighted_levenshtein.dam_lev(
#         a_pixels, b_pixels,
#         insert_costs=insert_costs,
#         delete_costs=delete_costs,
#         substitute_costs=substitute_costs,
#     )
#     assert dist == edit_weight_new(a, b, is_odd_offset), (dist, a, b,
#                                                           is_odd_offset)
#     return np.int64(dist)

_even_ewm = {}
_odd_ewm = {}
_even_error_ewm = {}
_odd_error_ewm = {}
for a in range(256):
    for b in range(256):
        _even_ewm[(a << 8) + b] = edit_weight(a, b, False, False)
        _odd_ewm[(a << 8) + b] = edit_weight(a, b, True, False)

        _even_error_ewm[(a << 8) + b] = edit_weight(a, b, False, True)
        _odd_error_ewm[(a << 8) + b] = edit_weight(a, b, True, True)


#
# for a in range(256):
#     for b in range(256):
#         assert edit_weight(a, b, True) == edit_weight(b, a, True)
#         assert edit_weight(a, b, False) == edit_weight(b, a, False)


# def array_edit_weight2(content: int, b: np.array) -> np.array:
#     assert b.shape == (256,), b.shape
#
#     # Extract even and off column offsets (128,)
#     even_b = b[::2]
#     odd_b = b[1::2]
#
#     a = np.ones(even_b.shape, dtype=np.int64) * content
#
#     even = (a << 8) + even_b
#     odd = (a << 8) + odd_b
#
#     even_weights = npi.remap(
#         even, _ewm_keys, _even_ewm_values, missing="raise")
#     odd_weights = npi.remap(
#         odd, _ewm_keys, _odd_ewm_values, missing="raise")
#
#     res = np.ndarray(shape=(256,), dtype=np.int64)
#     res[::2] = even_weights
#     res[1::2] = odd_weights
#
#     return res


@functools.lru_cache(None)
def _content_a_array(content: int, shape) -> np.array:
    return (np.ones(shape, dtype=np.uint16) * content) << 8


def content_edit_weight(content: int, b: np.array) -> np.array:
    assert b.shape == (32, 256), b.shape

    # Extract even and off column offsets (128,)
    even_b = b[:, ::2]
    odd_b = b[:, 1::2]

    a = _content_a_array(content, even_b.shape)

    even = a + even_b
    odd = a + odd_b

    even_weights = np.vectorize(_even_error_ewm.__getitem__)(even)
    odd_weights = np.vectorize(_odd_error_ewm.__getitem__)(odd)

    res = np.ndarray(shape=b.shape, dtype=np.int64)
    res[:, ::2] = even_weights
    res[:, 1::2] = odd_weights

    return res


def array_edit_weight(a: np.array, b: np.array) -> np.array:
    # assert a.shape == b.shape == (32, 256), (a.shape, b.shape)

    # Extract even and off column offsets (32, 128)
    even_a = a[:, ::2]
    odd_a = a[:, 1::2]

    even_b = b[:, ::2]
    odd_b = b[:, 1::2]

    even = (even_a.astype(np.uint16) << 8) + even_b
    odd = (odd_a.astype(np.uint16) << 8) + odd_b
    #
    # print("XXX")
    # print(a)
    # print(b)
    # print(even_a)
    # print(even_b)
    # print(even)

    even_weights = np.vectorize(_even_ewm.__getitem__)(even)
    odd_weights = np.vectorize(_odd_ewm.__getitem__)(odd)

    #
    # print(even_weights)
    # print(odd_weights)

    res = np.ndarray(shape=a.shape, dtype=np.int64)
    res[:, ::2] = even_weights
    res[:, 1::2] = odd_weights

    return res


# _x = np.ndarray((4, 4), dtype=np.uint8)
# print(array_edit_weight(_x, _x))
# assert np.array_equal(array_edit_weight(_x, _x), np.zeros((32, 256)))

@functools.lru_cache(None)
def byte_to_colour_string(b: int, is_odd_offset: bool) -> str:
    pixels = []

    idx = 0
    if is_odd_offset:
        pixels.append("01"[b & 0x01])
        idx += 1

    # K = black
    # G = green
    # V = violet
    # W = white
    palettes = (
        (
            "K",  # 0x00
            "V",  # 0x01
            "G",  # 0x10
            "W"  # 0x11
        ), (
            "K",  # 0x00
            "B",  # 0x01
            "O",  # 0x10
            "W"  # 0x11
        )
    )
    palette = palettes[(b & 0x80) != 0]

    for _ in range(3):
        pixel = palette[(b >> idx) & 0b11]
        pixels.append(pixel)
        idx += 2

    if not is_odd_offset:
        pixels.append("01"[b & 0x40 != 0])
        idx += 1

    return "".join(pixels)


class Video:
    """Apple II screen memory map encoding a bitmapped frame."""

    CLOCK_SPEED = 1024 * 1024

    def __init__(
            self,
            filename: str):
        self.filename = filename  # type: str

        self._reader = skvideo.io.FFmpegReader(filename)

        # Compute frame rate from input video
        data = skvideo.io.ffprobe(self.filename)['video']
        rate_data = data['@r_frame_rate'].split("/")  # e.g. 12000/1001
        self._input_frame_rate = float(rate_data[0]) / float(rate_data[1])

        self.cycles_per_frame = 1024. * 1024 / self._input_frame_rate
        self.frame_number = 0

        # Initialize empty
        self.memory_map = screen.MemoryMap(
            screen_page=1)  # type: screen.MemoryMap

        # Accumulates pending edit weights across frames
        self.update_priority = np.zeros((32, 256), dtype=np.int64)

    def tick(self, cycles) -> bool:
        # print(cycles, self.cycles_per_frame, self.cycles_per_frame *
        #       self.frame_number)
        if cycles > (self.cycles_per_frame * self.frame_number):
            self.frame_number += 1
            return True
        return False

    def _frame_grabber(self):
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

        t = threading.Thread(target=worker)
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

    # def _diff_weights(
    #         self,
    #         source: screen.MemoryMap,
    #         target: screen.MemoryMap
    # ):
    #     diff_weights = np.zeros((32, 256), dtype=np.int64)
    #
    #     it = np.nditer(
    #         source.page_offset ^ target.page_offset, flags=['multi_index'])
    #     while not it.finished:
    #         # If no diff, don't need to bother
    #         if not it[0]:
    #             it.iternext()
    #             continue
    #
    #         diff_weights[it.multi_index] = edit_weight(
    #             source.page_offset[it.multi_index],
    #             target.page_offset[it.multi_index],
    #             it.multi_index[1] % 2 == 1
    #         )
    #         it.iternext()

    # aew = array_edit_weight(source.page_offset,
    #                         target.page_offset)
    # if not np.array_equal(
    #     diff_weights, aew
    # ):
    #     it = np.nditer(
    #         diff_weights - aew, flags=['multi_index'])
    #     while not it.finished:
    #         # If no diff, don't need to bother
    #         if it[0]:
    #             print(
    #                 source.page_offset[it.multi_index],
    #                 target.page_offset[it.multi_index],
    #                 diff_weights[it.multi_index],
    #                 aew[it.multi_index], it.multi_index)
    #         it.iternext()
    #     assert False

    # return diff_weights

    @staticmethod
    def _diff_weights_new(
            source: screen.MemoryMap,
            target: screen.MemoryMap
    ):
        return array_edit_weight(
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
            heapq.heappush(priorities, (-priority, nonce, page, offset))
            it.iternext()

        return priorities

    @staticmethod
    def _compute_delta(content, target, old):
        return content_edit_weight(content, target) - old

    # XXX 0WKK -> 1KKV (3)
    #     1VVV -> 1KKV (2) is closer to target but a big
    # visual difference

    # 0WKK -> 1KKV = 2 transpose + 2 flip = 12, or 3 flip = 15
    # 1VVV -> 1KKV = 2 flip = 10, delta = -2
    # @functools.lru_cache(None)
    # def _compute_delta_old(self, content, target, is_odd, old):
    #     return edit_weight(content, target, is_odd)  # - old

    _OFFSETS = np.arange(256)

    def _compute_error(self, page, content, target, old_error, content_deltas):
        offsets = []

        delta_screen = content_deltas.get(content)
        if delta_screen is None:
            delta_screen = self._compute_delta(
                content, target.page_offset, old_error)
            content_deltas[content] = delta_screen
        delta_page = delta_screen[page]

        # old_error_page = old_error[page]
        # tpo = target.page_offset[page]
        #
        # # If we store content at this offset, what is the difference
        # # between this edit distance and the ideal target edit distance?
        # delta_page = self._compute_delta(
        #     content, tpo, old_error_page)
        # # print(delta_page)
        cond = delta_page < 0

        candidate_offsets = self._OFFSETS[cond]
        priorities = self.update_priority[page][cond]
        # deltas = delta_page[cond]

        # assert len(priorities) == len(candidate_offsets) == len(deltas) ==
        # sum(cond)

        l = [
            (-priorities[i], random.random(), candidate_offsets[i])
            for i in range(len(candidate_offsets))
        ]
        # offsets = [o for _, _, o in heapq.nsmallest(3, l)]
        heapq.heapify(l)

        while l:
            _, _, o = heapq.heappop(l)
            offsets.append(o)
            if len(offsets) == 3:
                break
        #
        # page_priorities = [(-p, random.random(), o) for o, p in enumerate(
        #     self.update_priority[page]) if p]
        # heapq.heapify(page_priorities)
        #
        # # Iterate in descending priority order and take first 3 offsets with
        # # negative delta
        # while page_priorities:
        #     _, _, o = heapq.heappop(page_priorities)
        #
        #     # If we store content at this offset, what is the difference
        #     # between this edit distance and the ideal target edit distance?
        #     delta = self._compute_delta_old(
        #         content, tpo[o], o % 2 == 1, old_error_page[o])
        #
        #     # Getting further away from goal, no thanks!
        #     if delta >= 0:
        #         continue
        #     #
        #     # # print("Offset %d prio %d: %d -> %d = %d" % (
        #     # #   o, p, content,
        #     # #   target.page_offset[page, o],
        #     # #   delta
        #     # # ))
        #     offsets.append(o)
        #     if len(offsets) == 3:
        #         break

        return offsets

    def _index_changes(
            self,
            source: screen.MemoryMap,
            target: screen.MemoryMap
    ) -> Iterator[Tuple[int, int, int, int, int]]:
        """Transform encoded screen to sequence of change tuples.

        Change tuple is (update_priority, page, offset, content, run_length)
        """

        diff_weights = self._diff_weights_new(source, target)

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
            # print("Priority %d: page %d offset %d content %d" % (
            #    priority, page, offset, content))

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

            # print("Page %d, content %d: offsets %s" % (page+32, content,
            #                                           offsets))
            yield (page + 32, content, offsets)

        # If we run out of things to do, pad forever
        content = target.page_offset[(0, 0)]
        while True:
            yield (32, content, [0, 0, 0, 0])
