import functools
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

    def __init__(self, frame_rate: int = 15, screen_page: int = 1,
                 opcode_scheduler: scheduler.OpcodeScheduler = None):
        self.screen_page = screen_page

        # Initialize empty
        self.memory_map = screen.MemoryMap(
            self.screen_page)  # type: screen.MemoryMap

        self.scheduler = (
                opcode_scheduler or scheduler.HeuristicPageFirstScheduler())

        self.cycle_counter = opcodes.CycleCounter()

        # Accumulates pending edit weights across frames
        self.update_priority = np.zeros((32, 256), dtype=np.int)

        self.state = opcodes.State(
            self.cycle_counter, self.memory_map, self.update_priority)

        self.frame_rate = frame_rate
        self.stream_pos = 0
        if self.frame_rate:
            self.cycles_per_frame = self.CLOCK_SPEED // self.frame_rate
        else:
            self.cycles_per_frame = None

        self._last_op = opcodes.Nop()

    def encode_frame(self, target: screen.MemoryMap) -> Iterator[
        opcodes.Opcode]:
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

        # TODO: changes should be a class
        changes = self._index_changes(self.memory_map, target)

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
        total_update_priority_in_run = 0

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
                    total_update_priority_in_run, start_offset, cur_content,
                    run_length
                )
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
                total_update_priority_in_run = 0
                cur_content = tc

            if cur_content is None:
                cur_content = tc

            run_length += 1
            run.append((bd, offset, tc, 1))
            if bd:
                num_changes_in_run += 1
                total_update_priority_in_run += bd

        if run:
            # End of run
            yield from end_run()

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
            source.page_offset ^ target.page_offset,
            flags=['multi_index'])
        while not it.finished:
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

        for page in range(32):
            for change in self._index_page(
                    self.update_priority[page], target.page_offset[page]):
                (
                    total_priority_in_run, start_offset, target_content,
                    run_length
                ) = change

                # TODO: handle screen page
                yield (
                    total_priority_in_run, page + 32, start_offset,
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
