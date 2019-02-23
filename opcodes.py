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

    def emit(self, last_opcode: "Opcode", opcode: "Opcode") -> Iterator[int]:
        cmd = opcode.emit_command(last_opcode, opcode)
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
    NOP = 0xfa
    ACK = 0xf9


class Opcode:
    COMMAND = None  # type: OpcodeCommand
    _CYCLES = None  # type: int

    # Offset of start byte in decoder
    _START = None  # type: int

    # Offset of last byte in BRA instruction in decoder
    _END = None  # type: int

    def __repr__(self):
        return "Opcode(%s)" % self.COMMAND.name

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False

        return self.__data_eq__(other)

    def __data_eq__(self, other):
        raise NotImplementedError

    @property
    def cycles(self) -> int:
        return self._CYCLES

    @staticmethod
    def emit_command(last_opcode: "Opcode",
                     opcode: "Opcode") -> Iterator[int]:
        # Compute offset from last opcode's terminating BRA instruction to
        # first instruction of this opcode.
        offset = (opcode._START - last_opcode._END - 1) & 0xff

        # print("%s -> %s = %02x" % (last_opcode, opcode, offset))
        yield offset

    def emit_data(self) -> Iterator[int]:
        return

    def apply(self, state: State):
        pass


class Nop(Opcode):
    COMMAND = OpcodeCommand.NOP
    _CYCLES = 11
    _START = 0x819b
    _END = 0x81a2

    def __data_eq__(self, other):
        return True


class Store(Opcode):
    COMMAND = OpcodeCommand.STORE
    _CYCLES = 20  # 36
    _START = 0x81a3
    _END = 0x81b0

    def __init__(self, offset: int):
        if offset < 0 or offset > 255:
            raise ValueError("Invalid offset: %d" % offset)

        self.offset = offset

    def __repr__(self):
        return "Opcode(%s, %02x)" % (
            self.COMMAND.name, self.offset)

    def __data_eq__(self, other):
        return self.offset == other.offset

    def emit_data(self):
        # print("  Store @ %02x" % self.offset)
        yield self.offset

    def apply(self, state):
        state.memmap.write(state.page << 8 | self.offset, state.content)


class SetContent(Opcode):
    COMMAND = OpcodeCommand.SET_CONTENT
    _CYCLES = 15  # 62
    _START = 0x81b1
    _END = 0x81bb

    def __init__(self, content: int):
        self.content = content

    def __repr__(self):
        return "Opcode(%s, %02x)" % (
            self.COMMAND.name, self.content)

    def __data_eq__(self, other):
        return self.content == other.content

    def emit_data(self):
        yield self.content

    def apply(self, state: State):
        # print("  Set content %02x" % self.content)
        state.content = self.content


class SetPage(Opcode):
    COMMAND = OpcodeCommand.SET_PAGE
    _CYCLES = 23  # 73
    _START = 0x81bc
    _END = 0x81cc

    def __init__(self, page: int):
        self.page = page

    def __repr__(self):
        return "Opcode(%s, %02x)" % (
            self.COMMAND.name, self.page)

    def __data_eq__(self, other):
        return self.page == other.page

    def emit_data(self):
        yield self.page

    def apply(self, state: State):
        # print("  Set page %02x" % self.page)
        state.page = self.page


class RLE(Opcode):
    COMMAND = OpcodeCommand.RLE
    _CYCLES = 22
    _START = 0x81cd
    _END = 0x81e3

    def __init__(self, start_offset: int, run_length: int):
        self.start_offset = start_offset
        self.run_length = run_length

    def __repr__(self):
        return "Opcode(%s, %02x, %02x)" % (
            self.COMMAND.name, self.start_offset, self.run_length)

    def __data_eq__(self, other):
        return (
                self.start_offset == other.start_offset and
                self.run_length == other.run_length)

    def emit_data(self):
        # print("  RLE @ %02x * %02x" % (self.start_offset, self.run_length))
        yield self.start_offset
        yield self.run_length

    @property
    def cycles(self):
        return 22 + 10 * self.run_length

    def apply(self, state):
        for i in range(self.run_length):
            state.memmap.write(
                state.page << 8 | ((self.start_offset + i) & 0xff),
                state.content
            )


class Tick(Opcode):
    COMMAND = OpcodeCommand.TICK
    _TICK_ADDR = 0x81ee
    _END = 0x81f8

    def __init__(self, cycles: int):
        self._START = self._TICK_ADDR - (cycles - 15) // 2
        self._cycles = cycles

    def __repr__(self):
        return "Opcode(%s, %02x)" % (
            self.COMMAND.name, self.cycles)

    def __data_eq__(self, other):
        return self._cycles == other._cycles

    @property
    def cycles(self):
        return self._cycles

    def emit_data(self):
        print("  Tick @ %02x" % self.cycles)


class Terminate(Opcode):
    COMMAND = OpcodeCommand.TERMINATE
    _CYCLES = 6  # 50
    _START = 0x81f9
    _END = None

    def __data_eq__(self, other):
        return True


class Ack(Opcode):
    COMMAND = OpcodeCommand.ACK
    _CYCLES = 100  # XXX todo
    _START = 0x81fa
    _END = None

    def __data_eq__(self, other):
        return True


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
                cycles = next(stream)
                op = Tick(cycles)
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
