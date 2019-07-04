"""Encode a sequence of images as an optimized stream of screen changes."""

import heapq
import random
from typing import List, Iterator, Tuple

import numpy as np

import opcodes
import screen
from frame_grabber import FrameGrabber
from palette import Palette
from video_mode import VideoMode


class Video:
    """Apple II screen memory map encoding a bitmapped frame."""

    CLOCK_SPEED = 1024 * 1024  # type: int

    def __init__(
            self,
            frame_grabber: FrameGrabber,
            ticks_per_second: float,
            mode: VideoMode = VideoMode.HGR,
            palette: Palette = Palette.NTSC
    ):
        self.mode = mode  # type: VideoMode
        self.frame_grabber = frame_grabber  # type: FrameGrabber
        self.ticks_per_second = ticks_per_second  # type: float
        self.ticks_per_frame = (
                self.ticks_per_second / frame_grabber.input_frame_rate
        )  # type: float
        self.frame_number = 0  # type: int
        self.palette = palette  # type: Palette

        # Initialize empty screen
        self.memory_map = screen.MemoryMap(
            screen_page=1)  # type: screen.MemoryMap
        if self.mode == mode.DHGR:
            self.aux_memory_map = screen.MemoryMap(
                screen_page=1)  # type: screen.MemoryMap

        self.pixelmap = screen.DHGRBitmap(
            palette=palette,
            main_memory=self.memory_map,
            aux_memory=self.aux_memory_map
        )

        # Accumulates pending edit weights across frames
        self.update_priority = np.zeros((32, 256), dtype=np.int)
        if self.mode == mode.DHGR:
            self.aux_update_priority = np.zeros((32, 256), dtype=np.int)

    def tick(self, ticks: int) -> bool:
        if ticks >= (self.ticks_per_frame * self.frame_number):
            self.frame_number += 1
            return True
        return False

    def encode_frame(
            self,
            target: screen.MemoryMap,
            is_aux: bool,
    ) -> Iterator[opcodes.Opcode]:
        """Update to match content of frame within provided budget."""
        if is_aux:
            memory_map = self.aux_memory_map
            update_priority = self.aux_update_priority
        else:
            memory_map = self.memory_map
            update_priority = self.update_priority

        # Make sure nothing is leaking into screen holes
        assert np.count_nonzero(
            memory_map.page_offset[screen.SCREEN_HOLES]) == 0

        print("Similarity %f" % (update_priority.mean()))

        yield from self._index_changes(
            memory_map, target, update_priority, is_aux)

    def _index_changes(
            self,
            source: screen.MemoryMap,
            target: screen.MemoryMap,
            update_priority: np.array,
            is_aux: True
    ) -> Iterator[Tuple[int, int, List[int]]]:
        """Transform encoded screen to sequence of change tuples."""

        if is_aux:
            target_pixelmap = screen.DHGRBitmap(
                main_memory=self.memory_map,
                aux_memory=target,
                palette=self.palette
            )
        else:
            target_pixelmap = screen.DHGRBitmap(
                main_memory=target,
                aux_memory=self.aux_memory_map,
                palette=self.palette
            )

        diff_weights = target_pixelmap.diff_weights(self.pixelmap, is_aux)

        # Don't bother storing into screen holes
        diff_weights[screen.SCREEN_HOLES] = 0

        # Clear any update priority entries that have resolved themselves
        # with new frame
        update_priority[diff_weights == 0] = 0
        update_priority += diff_weights

        assert np.count_nonzero(update_priority[screen.SCREEN_HOLES]) == 0

        priorities = self._heapify_priorities(update_priority)

        content_deltas = {}

        while priorities:
            pri, _, page, offset = heapq.heappop(priorities)

            assert not screen.SCREEN_HOLES[page, offset], (
                    "Attempted to store into screen hole at (%d, %d)" % (
                page, offset))

            # Check whether we've already cleared this diff while processing
            # an earlier opcode
            if update_priority[page, offset] == 0:
                continue

            offsets = [offset]
            content = target.page_offset[page, offset]
            if self.mode == VideoMode.DHGR:
                # DHGR palette bit not expected to be set
                assert content < 0x80

            # Clear priority for the offset we're emitting
            update_priority[page, offset] = 0
            diff_weights[page, offset] = 0

            # Update memory maps
            source.page_offset[page, offset] = content
            self.pixelmap.apply(page, offset, is_aux, content)

            # Make sure we don't emit this offset as a side-effect of some
            # other offset later.
            for cd in content_deltas.values():
                cd[page, offset] = 0
                # TODO: what if we add another content_deltas entry later?
                #  We might clobber it again

            # Need to find 3 more offsets to fill this opcode
            for err, o in self._compute_error(
                    page,
                    content,
                    target_pixelmap,
                    diff_weights,
                    content_deltas,
                    is_aux
            ):
                assert o != offset

                assert not screen.SCREEN_HOLES[page, o], (
                        "Attempted to store into screen hole at (%d, %d)" % (
                    page, o))

                if update_priority[page, o] == 0:
                    # print("Skipping page=%d, offset=%d" % (page, o))
                    continue

                # Make sure we don't end up considering this (page, offset)
                # again until the next image frame.  Even if a better match
                # comes along, it's probably better to fix up some other byte.
                # TODO: or should we recompute it with new error?
                for cd in content_deltas.values():
                    cd[page, o] = 0

                byte_offset = target_pixelmap.byte_offset(o, is_aux)
                old_packed = target_pixelmap.packed[page, o // 2]

                p = target_pixelmap.byte_pair_difference(
                    byte_offset, old_packed, content)

                # Update priority for the offset we're emitting
                update_priority[page, o] = p  # 0

                source.page_offset[page, o] = content
                self.pixelmap.apply(page, o, is_aux, content)

                if p:
                    # This content byte introduced an error, so put back on the
                    # heap in case we can get back to fixing it exactly
                    # during this frame.  Otherwise we'll get to it later.
                    heapq.heappush(
                        priorities, (-p, random.getrandbits(16), page, o))

                offsets.append(o)
                if len(offsets) == 3:
                    break

            # Pad to 4 if we didn't find enough
            for _ in range(len(offsets), 4):
                offsets.append(offsets[0])
            yield (page + 32, content, offsets)

        # TODO: there is still a bug causing residual diffs when we have
        # apparently run out of work to do
        if not np.array_equal(source.page_offset, target.page_offset):
            diffs = np.nonzero(source.page_offset != target.page_offset)
            for i in range(len(diffs[0])):
                diff_p = diffs[0][i]
                diff_o = diffs[1][i]

                print("Diff at (%d, %d): %d != %d" % (
                    diff_p, diff_o, source.page_offset[diff_p, diff_o],
                    target.page_offset[diff_p, diff_o]
                ))
            # assert False

        # If we run out of things to do, pad forever
        content = target.page_offset[0, 0]
        while True:
            yield (32, content, [0, 0, 0, 0])

    @staticmethod
    def _heapify_priorities(update_priority: np.array) -> List:
        pages, offsets = update_priority.nonzero()
        priorities = [tuple(data) for data in np.stack((
            -update_priority[pages, offsets],
            # Don't use deterministic order for page, offset
            np.random.randint(0, 2 ** 8, size=pages.shape[0]),
            pages,
            offsets)
        ).T.tolist()]

        heapq.heapify(priorities)
        return priorities

    _OFFSETS = np.arange(256)

    def _compute_error(self, page, content, target_pixelmap, old_error,
                       content_deltas, is_aux):
        # TODO: move this up into parent
        delta_screen = content_deltas.get(content)
        if delta_screen is None:
            delta_screen = target_pixelmap.compute_delta(
                content, old_error, is_aux)
            content_deltas[content] = delta_screen

        delta_page = delta_screen[page]
        cond = delta_page < 0
        candidate_offsets = self._OFFSETS[cond]
        priorities = delta_page[cond]

        deltas = [
            (priorities[i], random.getrandbits(16), candidate_offsets[i])
            for i in range(len(candidate_offsets))
        ]
        heapq.heapify(deltas)

        while deltas:
            pri, _, o = heapq.heappop(deltas)
            assert pri < 0
            assert o <= 255

            yield -pri, o
