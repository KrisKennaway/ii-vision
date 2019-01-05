import functools
from collections import defaultdict
from typing import Iterator, Set, Tuple

import numpy as np

import opcodes
import scheduler
import memory_map
import screen


@functools.lru_cache(None)
def hamming_weight(n: int) -> int:
    """Compute hamming weight of 8-bit int"""
    n = (n & 0x55) + ((n & 0xAA) >> 1)
    n = (n & 0x33) + ((n & 0xCC) >> 2)
    n = (n & 0x0F) + ((n & 0xF0) >> 4)
    return n


class Video:
    """Apple II screen memory map encoding a bitmapped frame."""

    def __init__(self, screen_page: int = 0,
                 opcode_scheduler: scheduler.OpcodeScheduler = None):
        self.screen_page = screen_page

        # Initialize empty
        self.screen = screen.HGRBitmap().pack()  # type: screen.Bytemap

        self.memory_map = memory_map.MemoryMap(screen_page, self.screen)

        self.cycle_counter = opcodes.CycleCounter()
        self.state = opcodes.State(self.cycle_counter, self.memory_map)

        self.scheduler = (
                opcode_scheduler or scheduler.HeuristicPageFirstScheduler())

    def update(self, frame: screen.Bitmap,
               cycle_budget: int, fullness: float) -> Iterator[int]:
        """Update to match content of frame within provided budget.

        Emits encoded byte stream for rendering the image.

        The byte stream consists of offsets against a selected page (e.g. $20xx)
        at which to write a selected content byte.  Those selections are
        controlled by special opcodes emitted to the stream

        Opcodes:
          SET_CONTENT - new byte to write to screen contents
          SET_PAGE - set new page to offset against (e.g. $20xx)
          TICK - tick the speaker
          DONE - terminate the video decoding

        In order to "make room" for these opcodes we make use of the fact that
        each page has 2 sets of 8-byte "screen holes", at page offsets
        0x78-0x7f and 0xf8-0xff.  Currently we only use the latter range as
        this allows for efficient matching in the critical path of the decoder.

        We group by offsets from page boundary (cf some other more
        optimal starting point) because STA (..),y has 1 extra cycle if
        crossing the page boundary.  Though maybe this would be worthwhile if
        it optimizes the bytestream.
        """

        self.cycle_counter.reset()
        # Target screen memory map for new frame
        target = frame.pack()

        # Estimate number of opcodes that will end up fitting in the cycle
        # budget.
        byte_cycles = opcodes.Store(0).cycles
        est_opcodes = int(cycle_budget / fullness / byte_cycles)

        # Sort by highest xor weight and take the estimated number of change
        # operations
        # TODO: changes should be a class
        changes = list(
            sorted(self.index_changes(self.screen, target), reverse=True)
        )[:est_opcodes]

        for op in self.scheduler.schedule(changes):
            yield from self.state.emit(op)

    def index_changes(self, source: screen.Bytemap,
                      target: screen.Bytemap) -> Set[
        Tuple[int, int, int, int, int]]:
        """Transform encoded screen to sequence of change tuples.

        Change tuple is (xor_weight, page, offset, content)
        """

        changes = set()
        # TODO: don't use 256 bytes if XMAX is smaller, or we may compute RLE
        # over the full page!
        memmap = defaultdict(lambda: [(0, 0, 0)] * 256)

        it = np.nditer(target.bytemap, flags=['multi_index'])
        while not it.finished:
            y, x_byte = it.multi_index

            page, offset = self.memory_map.to_page_offset(x_byte, y)

            src_content = source.bytemap[y][x_byte]
            target_content = np.asscalar(it[0])

            bits_different = hamming_weight(src_content ^ target_content)

            memmap[page][offset] = (bits_different, src_content, target_content)
            it.iternext()

        byte_cycles = opcodes.Store(0).cycles

        for page, offsets in memmap.items():
            cur_content = None
            run_length = 0
            maybe_run = []
            for offset, data in enumerate(offsets):
                bits_different, src_content, target_content = data

                # TODO: allowing odd bit errors introduces colour error
                if maybe_run and hamming_weight(
                        cur_content ^ target_content) > 2:
                    # End of run

                    # Decide if it's worth emitting as a run vs single stores

                    # Number of changes in run for which >0 bits differ
                    num_changes = len([c for c in maybe_run if c[0]])
                    run_cost = opcodes.RLE(0, run_length).cycles
                    single_cost = byte_cycles * num_changes
                    # print("Run of %d cheaper than %d singles" % (
                    #    run_length, num_changes))

                    # TODO: don't allow too much error to accumulate

                    if run_cost < single_cost:
                        # Compute median bit value over run
                        median_bits = np.median(
                            np.vstack(
                                np.unpackbits(
                                    np.array(r[3], dtype=np.uint8)
                                )
                                for r in maybe_run
                            ), axis=0
                        ) > 0.5

                        typical_content = np.asscalar(np.packbits(median_bits))

                        total_xor = sum(ch[0] for ch in maybe_run)
                        start_offset = maybe_run[0][2]

                        change = (total_xor, page, start_offset,
                                  typical_content, run_length)
                        # print("Found run of %d * %2x at %2x:%2x" % (
                        #    run_length, cur_content, page, offset - run_length)
                        #      )
                        # print(maybe_run)
                        # print("change =", change)
                        changes.add(change)
                    else:
                        changes.update(ch for ch in maybe_run if ch[0])
                    maybe_run = []
                    run_length = 0
                    cur_content = target_content

                if cur_content is None:
                    cur_content = target_content

                run_length += 1
                maybe_run.append(
                    (bits_different, page, offset, target_content, 1))

        return changes

    def done(self) -> Iterator[int]:
        """Terminate opcode stream."""

        yield from self.state.emit(opcodes.Terminate())
