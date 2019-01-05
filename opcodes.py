import enum
from typing import Iterator, Tuple

import memory_map


class CycleCounter:
    def __init__(self):
        self.cycles = 0  # type:int

    def tick(self, cycles: int) -> None:
        self.cycles += cycles

    def reset(self) -> None:
        self.cycles = 0


class State:
    """Represents virtual machine state."""

    def __init__(self, cycle_counter: CycleCounter,
                 memmap: memory_map.MemoryMap):
        self.page = 0x20
        self.content = 0x7f

        self.memmap = memmap
        self.cycle_counter = cycle_counter

    def emit(self, opcode: "Opcode") -> Iterator[int]:
        cmd = opcode.emit_command()
        if cmd:
            yield from cmd
        data = opcode.emit_data()
        if data:
            yield from data

        # Update changes in memory map, if any
        opcode.apply(self)

        # Tick 6502 CPU
        self.cycle_counter.tick(opcode.cycles)


class OpcodeCommand(enum.Enum):
    STORE = 0x00
    SET_CONTENT = 0xfb  # set new data byte to write
    SET_PAGE = 0xfc
    RLE = 0xfd
    TICK = 0xfe  # tick speaker
    TERMINATE = 0xff


class Opcode:
    COMMAND = None  # type: OpcodeCommand
    _CYCLES = None  # type: int

    @property
    def cycles(self) -> int:
        return self._CYCLES

    def emit_command(self) -> Iterator[int]:
        yield self.COMMAND.value

    def emit_data(self) -> Iterator[int]:
        return

    def apply(self, state: State):
        pass


class Store(Opcode):
    COMMAND = OpcodeCommand.STORE
    _CYCLES = 36

    def __init__(self, offset: int):
        if offset < 0 or offset >255:
            raise ValueError("Invalid offset: %d" % offset)

        self.offset = offset

    def emit_command(self):
        return

    def emit_data(self):
        yield self.offset

    def apply(self, state):
        state.memmap.write(state.page << 8 | self.offset, state.content)


class SetPage(Opcode):
    COMMAND = OpcodeCommand.SET_PAGE
    _CYCLES = 73

    def __init__(self, page:int):
        self.page = page

    def emit_data(self):
        yield self.page

    def apply(self, state: State):
        state.page = self.page


class SetContent(Opcode):
    COMMAND = OpcodeCommand.SET_CONTENT
    _CYCLES = 62

    def __init__(self, content: int):
        self.content = content

    def emit_data(self):
        yield self.content

    def apply(self, state: State):
        state.content = self.content


class RLE(Opcode):
    COMMAND = OpcodeCommand.RLE

    def __init__(self, start_offset: int, run_length: int):
        self.start_offset = start_offset
        self.run_length = run_length

    def emit_data(self):
        yield self.start_offset
        yield self.run_length

    @property
    def cycles(self):
        return 98 + 9 * self.run_length

    def apply(self, state):
        for i in range(self.run_length):
            state.memmap.write(
                state.page << 8 | ((self.start_offset + i) & 0xff),
                state.content
            )


class Tick(Opcode):
    COMMAND = OpcodeCommand.TICK
    _CYCLES = 50


class Terminate(Opcode):
    COMMAND = OpcodeCommand.TERMINATE
    _CYCLES = 50


class Decoder:
    def __init__(self, state: State):
        self.state = state  # type: State

    def decode_stream(self, stream: Iterator[int]) -> Tuple[int, int, int, int]:
        """Replay an opcode stream to build a screen image."""
        num_content_changes = 0
        num_page_changes = 0
        num_content_stores = 0
        num_rle_bytes = 0

        terminate = False
        for b in stream:
            if b == OpcodeCommand.SET_CONTENT.value:
                content = next(stream)
                op = SetContent(content)
                num_content_changes += 1
            elif b == OpcodeCommand.SET_PAGE.value:
                page = next(stream)
                op = SetPage(page)
                num_page_changes += 1
            elif b == OpcodeCommand.RLE.value:
                offset = next(stream)
                run_length = next(stream)
                num_rle_bytes += run_length
                op = RLE(offset, run_length)
            elif b == OpcodeCommand.TICK.value:
                op = Tick()
            elif b == OpcodeCommand.TERMINATE.value:
                op = Terminate()
                terminate = True
            else:
                op = Store(b)
                num_content_stores += 1

            op.apply(self.state)
            if terminate:
                break

        return (
            num_content_stores, num_content_changes, num_page_changes,
            num_rle_bytes
        )
