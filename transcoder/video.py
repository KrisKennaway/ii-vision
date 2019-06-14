"""Encode a sequence of images as an optimized stream of screen changes."""

import functools
import heapq
import random
from typing import List, Iterator, Tuple

import numpy as np

import opcodes
import screen
from frame_grabber import FrameGrabber
from video_mode import VideoMode


class Video:
    """Apple II screen memory map encoding a bitmapped frame."""

    CLOCK_SPEED = 1024 * 1024  # type: int

    def __init__(
            self,
            frame_grabber: FrameGrabber,
            mode: VideoMode = VideoMode.HGR
    ):
        self.mode = mode  # type: VideoMode
        self.frame_grabber = frame_grabber  # type: FrameGrabber
        self.ticks_per_frame = (
            self.ticks_per_second / self.input_frame_rate)  # type: float
        self.frame_number = 0  # type: int

        # Initialize empty screen
        self.memory_map = screen.MemoryMap(
            screen_page=1)  # type: screen.MemoryMap
        if self.mode == mode.DHGR:
            self.aux_memory_map = screen.MemoryMap(
                screen_page=1)  # type: screen.MemoryMap

        self.pixelmap = screen.DHGRBitmap(
            main_memory=self.memory_map,
            aux_memory=self.aux_memory_map
        )

        # Accumulates pending edit weights across frames
        self.update_priority = np.zeros((32, 256), dtype=np.int)
        if self.mode == mode.DHGR:
            self.aux_update_priority = np.zeros((32, 256), dtype=np.int)

    def tick(self, cycles: int) -> bool:
        if cycles > (self.cycles_per_frame * self.frame_number):
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
                aux_memory=target
            )
        else:
            target_pixelmap = screen.DHGRBitmap(
                main_memory=target,
                aux_memory=self.aux_memory_map
            )

        diff_weights = self._diff_weights(
            self.pixelmap, target_pixelmap, is_aux
        )

        # Clear any update priority entries that have resolved themselves
        # with new frame
        update_priority[diff_weights == 0] = 0
        update_priority += diff_weights

        priorities = self._heapify_priorities(update_priority)

        content_deltas = {}

        while priorities:
            pri, _, page, offset = heapq.heappop(priorities)

            # Check whether we've already cleared this diff while processing
            # an earlier opcode
            if update_priority[page, offset] == 0:
                continue

            offsets = [offset]
            content = target.page_offset[page, offset]
            assert content < 0x80  # DHGR palette bit not expected to be set

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

                if update_priority[page, o] == 0:
                    # print("Skipping page=%d, offset=%d" % (page, o))
                    continue

                # Make sure we don't end up considering this (page, offset)
                # again until the next image frame.  Even if a better match
                # comes along, it's probably better to fix up some other byte.
                # TODO: or should we recompute it with new error?
                for cd in content_deltas.values():
                    cd[page, o] = 0

                byte_offset = target_pixelmap.interleaved_byte_offset(o, is_aux)
                old_packed = target_pixelmap.packed[page, o // 2]

                p = self._byte_pair_difference(
                    target_pixelmap, byte_offset, old_packed, content)

                # Update priority for the offset we're emitting
                update_priority[page, o] = p  # 0

                source.page_offset[page, o] = content
                self.pixelmap.apply(page, o, is_aux, content)

                if p:
                    # This content byte introduced an error, so put back on the
                    # heap in case we can get back to fixing it exactly
                    # during this frame.  Otherwise we'll get to it later.
                    heapq.heappush(
                        priorities, (-p, random.randint(0, 10000), page, o))

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
            np.random.randint(0, 10000, size=pages.shape[0]),
            pages,
            offsets)
        ).T.tolist()]

        heapq.heapify(priorities)
        return priorities

    @staticmethod
    def _diff_weights(
            source: screen.DHGRBitmap,
            target: screen.DHGRBitmap,
            is_aux: bool
    ):
        diff = np.ndarray((32, 256), dtype=np.int)

        if is_aux:
            # Pixels influenced by byte offset 0
            source_pixels0 = source.mask_and_shift_data(source.packed, 0)
            target_pixels0 = target.mask_and_shift_data(target.packed, 0)

            # Concatenate 8-bit source and target into 16-bit values
            pair0 = (source_pixels0 << 8) + target_pixels0
            dist0 = source.edit_distances[0][pair0].reshape(pair0.shape)

            # Pixels influenced by byte offset 2
            source_pixels2 = source.mask_and_shift_data(source.packed, 2)
            target_pixels2 = target.mask_and_shift_data(target.packed, 2)
            # Concatenate 12-bit source and target into 24-bit values
            pair2 = (source_pixels2 << 12) + target_pixels2
            dist2 = source.edit_distances[2][pair2].reshape(pair2.shape)

            diff[:, 0::2] = dist0
            diff[:, 1::2] = dist2

        else:
            # Pixels influenced by byte offset 1
            source_pixels1 = source.mask_and_shift_data(source.packed, 1)
            target_pixels1 = target.mask_and_shift_data(target.packed, 1)
            pair1 = (source_pixels1 << 12) + target_pixels1
            dist1 = source.edit_distances[1][pair1].reshape(pair1.shape)

            # Pixels influenced by byte offset 3
            source_pixels3 = source.mask_and_shift_data(source.packed, 3)
            target_pixels3 = target.mask_and_shift_data(target.packed, 3)
            pair3 = (source_pixels3 << 8) + target_pixels3
            dist3 = source.edit_distances[3][pair3].reshape(pair3.shape)

            diff[:, 0::2] = dist1
            diff[:, 1::2] = dist3

        return diff

    @functools.lru_cache(None)
    def _byte_pair_difference(
            self,
            target_pixelmap,
            byte_offset,
            old_packed,
            content
    ):

        old_pixels = target_pixelmap.mask_and_shift_data(
            old_packed, byte_offset)
        new_pixels = target_pixelmap.mask_and_shift_data(
            target_pixelmap.masked_update(
                byte_offset, old_packed, content), byte_offset)

        if byte_offset == 0 or byte_offset == 3:
            pair = (old_pixels << 8) + new_pixels
        else:
            pair = (old_pixels << 12) + new_pixels

        p = target_pixelmap.edit_distances[byte_offset][pair]

        return p

    @staticmethod
    def _compute_delta(
            content: int,
            target: screen.DHGRBitmap,
            old,
            is_aux: bool
    ):
        diff = np.ndarray((32, 256), dtype=np.int)

        # TODO: use error edit distance

        if is_aux:
            # Pixels influenced by byte offset 0
            source_pixels0 = target.mask_and_shift_data(
                target.masked_update(0, target.packed, content), 0)
            target_pixels0 = target.mask_and_shift_data(target.packed, 0)

            # Concatenate 8-bit source and target into 16-bit values
            pair0 = (source_pixels0 << 8) + target_pixels0
            dist0 = target.edit_distances[0][pair0].reshape(pair0.shape)

            # Pixels influenced by byte offset 2
            source_pixels2 = target.mask_and_shift_data(
                target.masked_update(2, target.packed, content), 2)
            target_pixels2 = target.mask_and_shift_data(target.packed, 2)
            # Concatenate 12-bit source and target into 24-bit values
            pair2 = (source_pixels2 << 12) + target_pixels2
            dist2 = target.edit_distances[2][pair2].reshape(pair2.shape)

            diff[:, 0::2] = dist0
            diff[:, 1::2] = dist2

        else:
            # Pixels influenced by byte offset 1
            source_pixels1 = target.mask_and_shift_data(
                target.masked_update(1, target.packed, content), 1)
            target_pixels1 = target.mask_and_shift_data(target.packed, 1)
            pair1 = (source_pixels1 << 12) + target_pixels1
            dist1 = target.edit_distances[1][pair1].reshape(pair1.shape)

            # Pixels influenced by byte offset 3
            source_pixels3 = target.mask_and_shift_data(
                target.masked_update(3, target.packed, content), 3)
            target_pixels3 = target.mask_and_shift_data(target.packed, 3)
            pair3 = (source_pixels3 << 8) + target_pixels3
            dist3 = target.edit_distances[3][pair3].reshape(pair3.shape)

            diff[:, 0::2] = dist1
            diff[:, 1::2] = dist3

        # TODO: try different weightings
        return (diff * 5) - old

    _OFFSETS = np.arange(256)

    def _compute_error(self, page, content, target_pixelmap, old_error,
                       content_deltas, is_aux):
        # TODO: move this up into parent
        delta_screen = content_deltas.get(content)
        if delta_screen is None:
            delta_screen = self._compute_delta(
                content, target_pixelmap, old_error, is_aux)
            content_deltas[content] = delta_screen

        delta_page = delta_screen[page]
        cond = delta_page < 0
        candidate_offsets = self._OFFSETS[cond]
        priorities = delta_page[cond]

        # TODO: vectorize this with numpy
        deltas = [
            (priorities[i], random.randint(0, 10000), candidate_offsets[i])
            for i in range(len(candidate_offsets))
        ]
        heapq.heapify(deltas)

        while deltas:
            pri, _, o = heapq.heappop(deltas)
            assert pri < 0
            assert o < 255

            yield -pri, o
