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
        else:
            self.pixelmap = screen.HGRBitmap(
                palette=palette,
                main_memory=self.memory_map,
            )

        # Accumulates pending edit weights across frames
        self.update_priority = np.zeros((32, 256), dtype=np.int)
        if self.mode == mode.DHGR:
            self.aux_update_priority = np.zeros((32, 256), dtype=np.int)

    def tick(self, ticks: int) -> bool:
        """Keep track of when it is time for a new image frame."""

        if ticks >= (self.ticks_per_frame * self.frame_number):
            self.frame_number += 1
            return True
        return False

    def encode_frame(
            self,
            target: screen.MemoryMap,
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
        # XXX why is this happening?  Maybe because we're not scoring <4 stores
        if np.count_nonzero(memory_map.page_offset[screen.SCREEN_HOLES]):
            print("Someone stored in screen holes")

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

        if self.mode == VideoMode.DHGR:
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
        else:
            target_pixelmap = screen.HGRBitmap(
                main_memory=target,
                palette=self.palette
            )

        diff_weights = target_pixelmap.diff_weights(self.pixelmap, is_aux)

        # Clear any update priority entries that have resolved themselves
        # with new frame
        update_priority[diff_weights == 0] = 0
        update_priority += diff_weights

        # priorities = self._heapify_priorities(update_priority)

        content_deltas = 5 * target_pixelmap.compute_delta(is_aux)
        # print(content_deltas[:, 0, 0])

        # Only want to consider deltas that are < 0
        # content_deltas[content_deltas >= update_priority] = 0

        edit_distance = content_deltas - update_priority

        # print(edit_distance[:, 0, 0])
        candidates = np.sum(edit_distance < 0)
        print("Candidates = %d" % candidates)

        # We care about finding the 4 smallest elements for each (
        # content, page), but not their order.
        smallest_idx = np.argpartition(edit_distance, 3, axis=2)[:, :, :4]
        # smallest = # np.sort(
        smallest = np.take_along_axis(edit_distance, smallest_idx,
                                          axis=2)  #, axis=2)
        while True:
            # Score should be sum of first 4 non-zero elements

            # score = np.apply_along_axis(_score, 2, smallest)

            # XXX turn into vector
            # scores = [
            #     smallest[:, :, 0],
            #     np.sum(smallest[:, :, :2], axis=2),
            #     np.sum(smallest[:, :, :3], axis=2),
            #     np.sum(smallest, axis=2)
            # ]

            score = np.sum(smallest, axis=2)

            idx = np.argmin(score, axis=None)
            #print([s.shape for s in scores])

            # print(score[:, 0])
            # print(score.shape)
            # idx = np.array((
            #     np.argmin(scores[0], axis=None),
            #     np.argmin(scores[1], axis=None),
            #     np.argmin(scores[2], axis=None),
            #     np.argmin(scores[3], axis=None)
            # ))
            # contents, pages = np.unravel_index(idx, scores[0].shape)
            # #print(contents, pages)
            # best_scores = np.array([scores[i][contents[i], pages[i]] for i in
            #                         range(4)])
            # idx_argmin = np.argmin(best_scores)
            # #print(best_scores)
            # #print(idx_argmin)
            # num_offsets = idx_argmin + 1
            #
            # sc = best_scores[idx_argmin]
            # # print(sc)
            # content, page = contents[idx_argmin], pages[idx_argmin]
            #print(score.shape)
            # print("Taking %d args" % num_offsets)
            # TODO: also consider what happens if we only store 1, 2 or 3
            #  offsets e.g. might only be a single pixel to fix up, as in
            #  AppleVision video.

            content, page = np.unravel_index(idx, score.shape)
            #print(content, page)
            sc = score[content, page]
            # print([s[content, page] for s in scores])
            # print(sc, content, page)
            if sc == 0:
                break
            assert sc < 0

            # May not have 4 valid offsets so have to recompute explicitly
            # i.e. can't just use smallest_idx[content, page]
            nonzero_offsets = smallest[content, page] < 0
            offsets = smallest_idx[
                content, page, nonzero_offsets].tolist()  # [:num_offsets]

            # print(sc, content, page, offsets)

            # TODO: uncomment once we are saving residual diff
            if any(diff_weights[page, o] == 0 for o in offsets):
                print("someone else got here first")
                continue

            for o in offsets:
                # TODO: uncomment once we are saving residual diff
                assert edit_distance[content, page, o]

                # TODO: move these all outside the loop & vectorize

                # TODO: temporal error diffusion - push residual error into
                # next frame
                update_priority[page, o] = 0  # += content_deltas[content,
                # page, o]
                # assert update_priority[page, o] >= 0
                diff_weights[page, o] = 0

                content_deltas[:, page, o] = 0

                edit_distance[:, page, o] = 0

                # Update memory maps
                source.page_offset[page, o] = content
                self.pixelmap.apply(page, o, is_aux, np.uint8(content))

                # Pad to 4 if we didn't find enough
            for _ in range(len(offsets), 4):
                offsets.append(offsets[0])

            self._repartition(edit_distance, smallest_idx, smallest, page,
                              offsets)

            yield (page + 32, content, offsets)

        print("Done")

        # If we run out of things to do, pad forever
        content = target.page_offset[0, 0]
        while True:
            yield (32, content, [0, 0, 0, 0])

    def _repartition(
            self,
            edit_distance: np.ndarray,
            smallest_idx: np.ndarray,
            smallest: np.ndarray,
            page: int,
            offsets: int
    ):
        sip = smallest_idx[:, page, :]
        contents, _ = (
                (sip == offsets[0]) |
                (sip == offsets[1]) |
                (sip == offsets[2]) |
                (sip == offsets[3])
        ).nonzero()
        # print("Repartitioning %d" % len(contents))
        for content in contents:
            partition = np.argpartition(
                edit_distance[content, page], 3)[:4]
            smallest_idx[content, page] = partition
            smallest[content, page] = np.take(
                edit_distance[content, page], partition)

        return

    def _compute_delta(
            self,
            target: screen.DHGRBitmap,
            old,
            is_aux: bool
    ):
        # Only need to consider 0x0 .. 0x7f content stores
        diff = np.ndarray((128, 32, 256), dtype=np.int)

        all_content_bytes = np.arange(128).reshape((128, 1))

        # TODO: use error edit distance

        # def _shift8(s0, t0):
        #     return (s0 << 8) + t0
        #
        # def _shift12(s0, t0):
        #     return (s0 << 12) + t0

        def _target_masked(content, t, byte_offset):
            return target.masked_update(byte_offset, t, content)

        if is_aux:
            # Pixels influenced by byte offset 0
            source_pixels0 = target.mask_and_shift_data(
                np.apply_along_axis(
                    _target_masked, 1, all_content_bytes, target.packed,
                    0), 0)
            target_pixels0 = target.mask_and_shift_data(target.packed,0)

            # Concatenate 8-bit source and target into 16-bit values
            pair0 = (source_pixels0 << 8) + target_pixels0
            dist0 = target.edit_distances(self.palette)[0][
                pair0].reshape(
                pair0.shape)

            # Pixels influenced by byte offset 2
            source_pixels2 = target.mask_and_shift_data(
                np.apply_along_axis(
                    _target_masked, 1, all_content_bytes, target.packed,
                    2), 2)
            target_pixels2 = target.mask_and_shift_data(target.packed,
                                                        2)
            # Concatenate 12-bit source and target into 24-bit values
            pair2 = (source_pixels2 << 12) + target_pixels2
            dist2 = target.edit_distances(self.palette)[2][
                pair2].reshape(
                pair2.shape)

            diff[:, :, 0::2] = dist0
            diff[:, :, 1::2] = dist2

        else:
            # Pixels influenced by byte offset 1
            source_pixels1 = target.mask_and_shift_data(
                np.apply_along_axis(
                    _target_masked, 1, all_content_bytes, target.packed,
                    1), 1)
            target_pixels1 = target.mask_and_shift_data(target.packed,
                                                        1)
            pair1 = (source_pixels1 << 12) + target_pixels1
            dist1 = target.edit_distances(self.palette)[1][
                pair1].reshape(
                pair1.shape)

            # Pixels influenced by byte offset 3
            source_pixels3 = target.mask_and_shift_data(
                np.apply_along_axis(
                    _target_masked, 1, all_content_bytes, target.packed,
                    3), 3)
            target_pixels3 = target.mask_and_shift_data(target.packed,
                                                        3)
            pair3 = (source_pixels3 << 8) + target_pixels3
            dist3 = target.edit_distances(self.palette)[3][
                pair3].reshape(
                pair3.shape)

            diff[:, :, 0::2] = dist1
            diff[:, :, 1::2] = dist3
        # TODO: try different weightings
        # 66% of the time this found enough to fill at 3 offsets
        # 18693 0
        # 14758 1
        # 12629 2
        # / 136804
        # and only 13% of the time found no candidates
        return diff
    #
    #     diff_weights = target_pixelmap.diff_weights(self.pixelmap, is_aux)
    #     # Don't bother storing into screen holes
    #     diff_weights[screen.SCREEN_HOLES] = 0
    #
    #     # Clear any update priority entries that have resolved themselves
    #     # with new frame
    #     update_priority[diff_weights == 0] = 0
    #     update_priority += diff_weights
    #
    #     priorities = self._heapify_priorities(update_priority)
    #
    #     content_deltas = {}
    #
    #     while priorities:
    #         pri, _, page, offset = heapq.heappop(priorities)
    #
    #         assert not screen.SCREEN_HOLES[page, offset], (
    #                 "Attempted to store into screen hole at (%d, %d)" % (
    #             page, offset))
    #
    #         # Check whether we've already cleared this diff while processing
    #         # an earlier opcode
    #         if update_priority[page, offset] == 0:
    #             continue
    #
    #         offsets = [offset]
    #         content = target.page_offset[page, offset]
    #         if self.mode == VideoMode.DHGR:
    #             # DHGR palette bit not expected to be set
    #             assert content < 0x80
    #
    #         # Clear priority for the offset we're emitting
    #         update_priority[page, offset] = 0
    #         diff_weights[page, offset] = 0
    #
    #         # Update memory maps
    #         source.page_offset[page, offset] = content
    #         self.pixelmap.apply(page, offset, is_aux, content)
    #
    #         # Make sure we don't emit this offset as a side-effect of some
    #         # other offset later.
    #         for cd in content_deltas.values():
    #             cd[page, offset] = 0
    #             # TODO: what if we add another content_deltas entry later?
    #             #  We might clobber it again
    #
    #         # Need to find 3 more offsets to fill this opcode
    #         for err, o in self._compute_error(
    #                 page,
    #                 content,
    #                 target_pixelmap,
    #                 diff_weights,
    #                 content_deltas,
    #                 is_aux
    #         ):
    #             assert o != offset
    #             assert not screen.SCREEN_HOLES[page, o], (
    #                     "Attempted to store into screen hole at (%d, %d)" % (
    #                 page, o))
    #
    #             if update_priority[page, o] == 0:
    #                 # Someone already resolved this diff.
    #                 continue
    #
    #             # Make sure we don't end up considering this (page, offset)
    #             # again until the next image frame.  Even if a better match
    #             # comes along, it's probably better to fix up some other byte.
    #             # TODO: or should we recompute it with new error?
    #             for cd in content_deltas.values():
    #                 cd[page, o] = 0
    #
    #             byte_offset = target_pixelmap.byte_offset(o, is_aux)
    #             old_packed = target_pixelmap.packed[page, o // 2]
    #
    #             p = target_pixelmap.byte_pair_difference(
    #                 byte_offset, old_packed, content)
    #
    #             # Update priority for the offset we're emitting
    #             update_priority[page, o] = p
    #
    #             source.page_offset[page, o] = content
    #             self.pixelmap.apply(page, o, is_aux, content)
    #
    #             if p:
    #                 # This content byte introduced an error, so put back on the
    #                 # heap in case we can get back to fixing it exactly
    #                 # during this frame.  Otherwise we'll get to it later.
    #                 heapq.heappush(
    #                     priorities, (-p, random.getrandbits(8), page, o))
    #
    #             offsets.append(o)
    #             if len(offsets) == 3:
    #                 break
    #
    #         # Pad to 4 if we didn't find enough
    #         for _ in range(len(offsets), 4):
    #             offsets.append(offsets[0])
    #         yield (page + 32, content, offsets)
    #
    #     # # TODO: there is still a bug causing residual diffs when we have
    #     # # apparently run out of work to do
    #     if not np.array_equal(source.page_offset, target.page_offset):
    #         diffs = np.nonzero(source.page_offset != target.page_offset)
    #         for i in range(len(diffs[0])):
    #             diff_p = diffs[0][i]
    #             diff_o = diffs[1][i]
    #
    #             # For HGR, 0x00 or 0x7f may be visually equivalent to the same
    #             # bytes with high bit set (depending on neighbours), so skip
    #             # them
    #             if (source.page_offset[diff_p, diff_o] & 0x7f) == 0 and \
    #                     (target.page_offset[diff_p, diff_o] & 0x7f) == 0:
    #                 continue
    #
    #             if (source.page_offset[diff_p, diff_o] & 0x7f) == 0x7f and \
    #                     (target.page_offset[diff_p, diff_o] & 0x7f) == 0x7f:
    #                 continue
    #
    #             print("Diff at (%d, %d): %d != %d" % (
    #                 diff_p, diff_o, source.page_offset[diff_p, diff_o],
    #                 target.page_offset[diff_p, diff_o]
    #             ))
    #             # assert False
    #
    #     # If we run out of things to do, pad forever
    #     content = target.page_offset[0, 0]
    #     while True:
    #         yield (32, content, [0, 0, 0, 0])
    #
    # @staticmethod
    # def _heapify_priorities(update_priority: np.array) -> List:
    #     """Build priority queue of (page, offset) ordered by update priority."""
    #
    #     # Use numpy vectorization to efficiently compute the list of
    #     # (priority, random nonce, page, offset) tuples to be heapified.
    #     pages, offsets = update_priority.nonzero()
    #     priorities = [tuple(data) for data in np.stack((
    #         -update_priority[pages, offsets],
    #         # Don't use deterministic order for page, offset
    #         np.random.randint(0, 2 ** 8, size=pages.shape[0]),
    #         pages,
    #         offsets)
    #     ).T.tolist()]
    #
    #     heapq.heapify(priorities)
    #     return priorities
    #
    # _OFFSETS = np.arange(256)
    #
    # def _compute_error(self, page, content, target_pixelmap, diff_weights,
    #                    content_deltas, is_aux):
    #     """Build priority queue of other offsets at which to store content.
    #
    #     Ordered by offsets which are closest to the target content value.
    #     """
    #     # TODO: move this up into parent
    #     delta_screen = content_deltas.get(content)
    #     if delta_screen is None:
    #         delta_screen = target_pixelmap.compute_delta(
    #             content, diff_weights, is_aux)
    #         content_deltas[content] = delta_screen
    #
    #     delta_page = delta_screen[page]
    #     cond = delta_page < 0
    #     candidate_offsets = self._OFFSETS[cond]
    #     priorities = delta_page[cond]
    #
    #     deltas = [
    #         (priorities[i], random.getrandbits(8), candidate_offsets[i])
    #         for i in range(len(candidate_offsets))
    #     ]
    #     heapq.heapify(deltas)
    #
    #     while deltas:
    #         pri, _, o = heapq.heappop(deltas)
    #         assert pri < 0
    #         assert o <= 255
    #
    #         yield -pri, o
