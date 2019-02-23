import functools
from typing import Iterator, Tuple, Iterable

import opcodes
import scheduler
import memory_map
import screen


def hamming_weight(n):
    """Compute hamming weight of 8-bit int"""
    n = (n & 0x55) + ((n & 0xAA) >> 1)
    n = (n & 0x33) + ((n & 0xCC) >> 2)
    n = (n & 0x0F) + ((n & 0xF0) >> 4)
    return n


class Video:
    """Apple II screen memory map encoding a bitmapped frame."""

    CLOCK_SPEED = 1024 * 1024

    def __init__(self, frame_rate: int = 15, screen_page: int = 0,
                 opcode_scheduler: scheduler.OpcodeScheduler = None):
        self.screen_page = screen_page

        # Initialize empty
        self.screen = screen.HGRBitmap().pack()  # type: screen.Bytemap

        self.memory_map = memory_map.MemoryMap(screen_page, self.screen)

        self.scheduler = (
                opcode_scheduler or scheduler.HeuristicPageFirstScheduler())

        self.cycle_counter = opcodes.CycleCounter()

        self.state = opcodes.State(self.cycle_counter, self.memory_map)

        self.frame_rate = frame_rate
        self.stream_pos = 0
        if self.frame_rate:
            self.cycles_per_frame = self.CLOCK_SPEED // self.frame_rate
        else:
            self.cycles_per_frame = None

        self._last_op = opcodes.Nop()

    def encode_frame(self, frame: screen.Bitmap) -> Iterator[opcodes.Opcode]:
        """Update to match content of frame within provided budget.

        Emits encoded byte stream for rendering the image.

        XXX update

        The byte stream consists of offsets against a selected page (e.g. $20xx)
        at which to write a selected content byte.  Those selections are
        controlled by special opcodes emitted to the stream

        Opcodes:
          SET_CONTENT - new byte to write to screen contents
          SET_PAGE - set new page to offset against (e.g. $20xx)
          TICK - tick the speaker
          DONE - terminate the video decoding

        We group by offsets from page boundary (cf some other more
        optimal starting point) because STA (..),y has 1 extra cycle if
        crossing the page boundary.  Though maybe this would be worthwhile if
        it optimizes the bytestream.
        """

        # Target screen memory map for new frame
        target = frame.pack()

        # Sort by highest xor weight and take the estimated number of change
        # operations
        # TODO: changes should be a class
        changes = sorted(list(self._index_changes(self.screen, target)),
                         reverse=True)

        yield from self.scheduler.schedule(changes)

    @functools.lru_cache()
    def _rle_cycles(self, run_length):
        return opcodes.RLE(0, run_length).cycles

    def _index_page(self, bits_different, target_content):
        byte_cycles = opcodes.Store(0).cycles

        cur_content = None
        run_length = 0
        run = []

        # Number of changes in run for which >0 bits differ
        num_changes_in_run = 0

        # Total weight of differences accumulated in run
        total_xor_in_run = 0

        def end_run():
            # Decide if it's worth emitting as a run vs single stores
            run_cost = self._rle_cycles(run_length)
            single_cost = byte_cycles * num_changes_in_run
            # print("Run of %d cheaper than %d singles" % (
            #     run_length, num_changes_in_run))

            if run_cost < single_cost:
                start_offset = run[0][1]

                # print("Found run of %d * %2x at %2x" % (
                #     run_length, cur_content, offset - run_length)
                #       )
                # print(run)
                yield (
                    total_xor_in_run, start_offset, cur_content, run_length)
            else:
                for ch in run:
                    if ch[0]:
                        yield ch

        for offset in range(256):
            bd = bits_different[offset]
            tc = target_content[offset]
            if run and cur_content != tc:
                # End of run

                yield from end_run()

                run = []
                run_length = 0
                num_changes_in_run = 0
                total_xor_in_run = 0
                cur_content = tc

            if cur_content is None:
                cur_content = tc

            run_length += 1
            run.append((bd, offset, tc, 1))
            if bd:
                num_changes_in_run += 1
                total_xor_in_run += bd

        if run:
            # End of run
            yield from end_run()

    def _index_changes(
            self,
            source: screen.Bytemap,
            target: screen.Bytemap) -> Iterator[Tuple[int, int, int, int, int]]:
        """Transform encoded screen to sequence of change tuples.

        Change tuple is (xor_weight, page, offset, content, run_length)
        """

        # TODO: work with memory maps directly?
        source_memmap = memory_map.MemoryMap.to_memory_map(source.bytemap)
        target_memmap = memory_map.MemoryMap.to_memory_map(target.bytemap)

        # TODO: don't use 256 bytes if XMAX is smaller, or we may compute RLE
        # (with bit errors) over the full page!
        diff_weights = hamming_weight(source_memmap ^ target_memmap)

        for page in range(32):
            for change in self._index_page(
                    diff_weights[page], target_memmap[page]):
                total_xor_in_run, start_offset, target_content, run_length = \
                    change

                # TODO: handle screen page
                yield (
                    total_xor_in_run, page + 32, start_offset,
                    target_content, run_length
                )

    def _emit_bytes(self, _op):
        # print("%04X:" % self.stream_pos)
        for b in self.state.emit(self._last_op, _op):
            yield b
            self.stream_pos += 1
        self._last_op = _op

    def emit_stream(self, ops: Iterable[opcodes.Opcode]) -> Iterator[int]:
        self.cycle_counter.reset()
        for op in ops:
            # Keep track of where we are in TCP client socket buffer
            socket_pos = self.stream_pos % 2048
            if socket_pos >= 2045:
                # May be about to emit a 3-byte opcode, pad out to last byte
                # in frame
                nops = 2047 - socket_pos
                # print("At position %04x, padding with %d nops" % (
                #    socket_pos, nops))
                for _ in range(nops):
                    yield from self._emit_bytes(opcodes.Nop())
                yield from self._emit_bytes(opcodes.Ack())
                # Ack falls through to nop
                self._last_op = opcodes.Nop()
            yield from self._emit_bytes(op)

            if self.cycles_per_frame and (
                    self.cycle_counter.cycles > self.cycles_per_frame):
                print("Out of cycle budget")
                return
        # TODO: pad to cycles_per_frame with NOPs

    def done(self) -> Iterator[int]:
        """Terminate opcode stream."""
        yield from self._emit_bytes(opcodes.Terminate())
