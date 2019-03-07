import functools
import heapq
import random
from typing import Iterator, Tuple, Iterable

import numpy as np
from similarity.damerau import Damerau

import opcodes
import scheduler
import screen


def hamming_weight(n):
    """Compute hamming weight of 8-bit int"""
    n = (n & 0x55) + ((n & 0xAA) >> 1)
    n = (n & 0x33) + ((n & 0xCC) >> 2)
    n = (n & 0x0F) + ((n & 0xF0) >> 4)
    return n


@functools.lru_cache(None)
def edit_weight(a: int, b: int, is_odd_offset: bool):
    d = Damerau()

    a_pixels = byte_to_colour_string(a, is_odd_offset)
    b_pixels = byte_to_colour_string(b, is_odd_offset)

    return d.distance(a_pixels, b_pixels)


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
            "O",  # 0x01
            "B",  # 0x10
            "W"  # 0x11
        )
    )
    palette = palettes[b & 0x80 != 0]

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
            frame_rate: int = 30,
            screen_page: int = 1,
            opcode_scheduler: scheduler.OpcodeScheduler = None):
        self.screen_page = screen_page
        self.frame_rate = frame_rate

        # Initialize empty
        self.memory_map = screen.MemoryMap(
            self.screen_page)  # type: screen.MemoryMap

        self.scheduler = (
                opcode_scheduler or scheduler.HeuristicPageFirstScheduler())

        # Accumulates pending edit weights across frames
        self.update_priority = np.zeros((32, 256), dtype=np.int)


    def encode_frame(self, target: screen.MemoryMap) -> Iterator[
        opcodes.Opcode]:
        """Update to match content of frame within provided budget.

        """

        yield from self._index_changes(self.memory_map, target)

    def _index_changes(
            self,
            source: screen.MemoryMap,
            target: screen.MemoryMap
    ) -> Iterator[Tuple[int, int, int, int, int]]:
        """Transform encoded screen to sequence of change tuples.

        Change tuple is (update_priority, page, offset, content, run_length)
        """

        diff_weights = np.zeros((32, 256), dtype=np.uint8)

        it = np.nditer(
            source.page_offset ^ target.page_offset, flags=['multi_index'])
        while not it.finished:
            # If no diff, don't need to bother
            if not it[0]:
                it.iternext()
                continue

            diff_weights[it.multi_index] = edit_weight(
                source.page_offset[it.multi_index],
                target.page_offset[it.multi_index],
                it.multi_index[1] % 2 == 1
            )
            it.iternext()

        # Clear any update priority entries that have resolved themselves 
        # with new frame
        self.update_priority[diff_weights == 0] = 0

        self.update_priority += diff_weights

        # Iterate in descending order of update priority and emit tuples
        # encoding (page, content, [offsets])

        priorities = []
        it = np.nditer(self.update_priority, flags=['multi_index'])
        while not it.finished:
            priority = it[0]
            if not priority:
                it.iternext()
                continue

            page, offset = it.multi_index
            # Don't use deterministic order for page, offset
            nonce = random.randint(0,255)
            heapq.heappush(priorities, (-priority, nonce, page, offset))
            it.iternext()

        while True:
            priority, _, page, offset = heapq.heappop(priorities)
            priority = -priority
            if page > (56-32):
                continue
            offsets = [offset]
            content = target.page_offset[page, offset]
            #print("Priority %d: page %d offset %d content %d" % (
            #    priority, page, offset, content))

            # Clear priority for the offset we're emitting
            self.update_priority[page, offset] = 0

            # Need to find 3 more offsets to fill this opcode

            # Minimize the update_priority delta that would result from
            # emitting this offset

            # Find offsets that would have largest reduction in diff weight
            # with this content byte, then order by update priority
            deltas = {}
            for o, p in enumerate(self.update_priority[page]):
                if p == 0:
                    continue

                # If we store content at this offset, what is the new
                # edit_weight from this content byte to the target
                delta = edit_weight(
                    content,
                    target.page_offset[page, o],
                    o % 2 == 1
                )
                #print("Offset %d prio %d: %d -> %d = %d" % (
                #    o, p, content,
                #    target.page_offset[page, o],
                #    delta
                #))
                deltas.setdefault(delta, list()).append((p, o))

            for d in sorted(deltas.keys()):
                #print(d)
                po = sorted(deltas[d], reverse=True)
                #print(po)
                for p, o in po:
                    offsets.append(o)
                    # Clear priority for the offset we're emitting
                    self.update_priority[page, offset] = 0
                    if len(offsets) == 4:
                        break
                if len(offsets) == 4:
                    break

            # Pad to 4 if we didn't find anything
            for _ in range(len(offsets), 4):
                offsets.append(offsets[0])

            #print("Page %d, content %d: offsets %s" % (page+32, content,
            #                                           offsets))
            yield (page+32, content, offsets)



