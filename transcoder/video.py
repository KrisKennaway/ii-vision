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
    """Encodes sequence of images into prioritized screen byte changes."""

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
        self.ticks_per_second = float(ticks_per_second)  # type: float
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
        else:
            self.pixelmap = screen.HGRBitmap(
                palette=palette,
                main_memory=self.memory_map,
            )

        # Accumulates pending edit weights across frames
        self.update_priority = np.zeros((32, 256), dtype=np.int32)
        if self.mode == mode.DHGR:
            self.aux_update_priority = np.zeros((32, 256), dtype=np.int32)

        # Indicates whether we have run out of work for the main/aux banks.
        # Key is True for aux bank and False for main bank
        self.out_of_work = {True: False, False: False}

    def tick(self, ticks: int) -> bool:
        """Keep track of when it is time for a new image frame."""

        if ticks >= (self.ticks_per_frame * self.frame_number):
            self.frame_number += 1
            return True
        return False

    def encode_frame(
            self,
            target: screen.Bitmap,
            is_aux: bool,
    ) -> Iterator[opcodes.Opcode]:
        """Converge towards target frame in priority order of edit distance."""

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
            target_pixelmap: screen.Bitmap,
            update_priority: np.array,
            is_aux: bool
    ) -> Iterator[Tuple[int, int, List[int]]]:
        """Transform encoded screen to sequence of change tuples."""

        if self.mode == VideoMode.DHGR and is_aux:
            target = target_pixelmap.aux_memory
        else:
            target = target_pixelmap.main_memory

        diff_weights = target_pixelmap.diff_weights(self.pixelmap, is_aux)
        # Don't bother storing into screen holes
        diff_weights[screen.SCREEN_HOLES] = 0

        # Clear any update priority entries that have resolved themselves
        # with new frame
        update_priority[diff_weights == 0] = 0
        update_priority += diff_weights
        assert np.all(update_priority >= 0)

        priorities = self._heapify_priorities(update_priority)

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
            self.pixelmap.apply(page, offset, is_aux, content)

            # Need to find 3 more offsets to fill this opcode
            for err, o in self._compute_error(
                    page,
                    content,
                    target_pixelmap,
                    diff_weights,
                    is_aux
            ):
                assert o != offset
                assert not screen.SCREEN_HOLES[page, o], (
                        "Attempted to store into screen hole at (%d, %d)" % (
                    page, o))

                if update_priority[page, o] == 0:
                    # Someone already resolved this diff.
                    continue

                byte_offset = target_pixelmap.byte_offset(o, is_aux)
                old_packed = target_pixelmap.packed[page, o // 2]

                p = target_pixelmap.byte_pair_difference(
                    byte_offset, old_packed, content)

                # Update priority for the offset we're emitting
                update_priority[page, o] = p

                self.pixelmap.apply(page, o, is_aux, content)
                if p:
                    # This content byte introduced an error, so put back on the
                    # heap in case we can get back to fixing it exactly
                    # during this frame.  Otherwise, we'll get to it later.
                    heapq.heappush(
                        priorities, (-p, random.getrandbits(8), page, o))

                offsets.append(o)
                if len(offsets) == 3:
                    break

            # Pad to 4 if we didn't find enough
            for _ in range(len(offsets), 4):
                offsets.append(offsets[0])
            yield page + 32, content, offsets

        self.out_of_work[is_aux] = True

        # These debugging assertions validate that when we are out of work,
        # our source and target representations should be identical.
        #
        # They only work correctly for palettes that do not have identical
        # colours (e.g. IIGS but not NTSC which has two identical greys).
        #
        # The problem is that if we have substituted one grey for the other
        # there may be no diff if they are part of an extended run of greys.
        #
        # The only difference is at the end of the run where these produce
        # different artifact colours, but this may only be visible in the
        # other bank.
        #
        # It may take several iterations of main/aux before we will notice and
        # correct all of these differences.  That means we don't have a
        # deterministic point in time when we can assert that all diffs should
        # have been resolved.
        # TODO: add flag to enable debug assertions
        # if not np.array_equal(source.page_offset, target.page_offset):
        #     diffs = np.nonzero(source.page_offset != target.page_offset)
        #     for i in range(len(diffs[0])):
        #         diff_p = diffs[0][i]
        #         diff_o = diffs[1][i]
        #
        #         # For HGR, 0x00 or 0x7f may be visually equivalent to the same
        #         # bytes with high bit set (depending on neighbours), so skip
        #         # them
        #         if (source.page_offset[diff_p, diff_o] & 0x7f) == 0 and \
        #                 (target.page_offset[diff_p, diff_o] & 0x7f) == 0:
        #             continue
        #
        #         if (source.page_offset[diff_p, diff_o] & 0x7f) == 0x7f and \
        #                 (target.page_offset[diff_p, diff_o] & 0x7f) == 0x7f:
        #             continue
        #
        #         print("Diff at (%d, %d): %d != %d" % (
        #             diff_p, diff_o, source.page_offset[diff_p, diff_o],
        #             target.page_offset[diff_p, diff_o]
        #         ))
        #         assert False
        #
        # # If we've finished both main and aux pages, there should be no residual
        # # diffs in packed representation
        # all_done = self.out_of_work[True] and self.out_of_work[False]
        # if all_done and not np.array_equal(self.pixelmap.packed,
        #                                    target_pixelmap.packed):
        #     diffs = np.nonzero(
        #         self.pixelmap.packed != target_pixelmap.packed)
        #     print("is_aux: %s" % is_aux)
        #     for i in range(len(diffs[0])):
        #         diff_p = diffs[0][i]
        #         diff_o = diffs[1][i]
        #         print("(%d, %d): got %d want %d" % (
        #             diff_p, diff_o, self.pixelmap.packed[diff_p, diff_o],
        #             target_pixelmap.packed[diff_p, diff_o]))
        #     assert False

        # If we run out of things to do, pad forever
        content = target.page_offset[0, 0]
        while True:
            yield 32, content, [0, 0, 0, 0]

    @staticmethod
    def _heapify_priorities(update_priority: np.array) -> List:
        """Build priority queue of (page, offset) ordered by update priority."""

        # Use numpy vectorization to efficiently compute the list of
        # (priority, random nonce, page, offset) tuples to be heapified.
        pages, offsets = update_priority.nonzero()
        priorities = [tuple(data) for data in np.stack((
            -update_priority[pages, offsets],
            # Don't use deterministic order for page, offset.  Otherwise,
            # we get the "venetian blind" effect when filling large blocks of
            # colour.
            np.random.randint(0, 2 ** 8, size=pages.shape[0]),
            pages,
            offsets)
        ).T.tolist()]

        heapq.heapify(priorities)
        return priorities

    _OFFSETS = np.arange(256)

    def _compute_error(
            self, page, content, target_pixelmap, diff_weights, is_aux):
        """Build priority queue of other offsets at which to store content.

        Ordered by offsets which are closest to the target content value.
        """
        delta_page = target_pixelmap.compute_delta_page(
            page, content, diff_weights[page, :], is_aux)
        cond = delta_page < 0
        candidate_offsets = self._OFFSETS[cond]
        priorities = delta_page[cond]

        # Don't use deterministic order for page, offset.  Otherwise,
        # we get the "venetian blind" effect when filling large blocks of
        # colour.
        deltas = [
            (priorities[i], random.getrandbits(8), candidate_offsets[i])
            for i in range(len(candidate_offsets))
        ]
        heapq.heapify(deltas)

        while deltas:
            pri, _, offset = heapq.heappop(deltas)
            assert pri < 0
            assert 0 <= offset <= 255

            yield -pri, offset
