import enum
from typing import Iterator, Tuple

import memory_map
import symbol_table


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

    # Offset of start byte in decoder opcode
    _START = None  # type: int

    # Offset of last byte in decoder opcode
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

    def __data_eq__(self, other):
        return True


class Store(Opcode):
    COMMAND = OpcodeCommand.STORE
    _CYCLES = 20

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
    _CYCLES = 15

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
    _CYCLES = 23

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

    def __init__(self, cycles: int):
        self._START -= (cycles - 15) // 2
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
    _CYCLES = 6

    def __data_eq__(self, other):
        return True


class Ack(Opcode):
    COMMAND = OpcodeCommand.ACK
    _CYCLES = 100  # XXX todo

    def __data_eq__(self, other):
        return True


def _ParseSymbolTable():
    """Read symbol table from video player debug file."""

    opcode_data = {}
    for name, data in symbol_table.SymbolTable(
            "ethernet/ethernet/ethernet.dbg").parse().items():
        if name.startswith("\"op_"):
            op_name = name[4:-1]
            start_addr = int(data["val"], 16)

            opcode_data.setdefault(op_name, {})["start"] = start_addr

        if name.startswith("\"end_"):
            op_name = name[5:-1]
            end_addr = int(data["val"], 16) - 1

            opcode_data.setdefault(op_name, {})["end"] = end_addr

    opcode_addrs = []
    for op_name, addrs in opcode_data.items():
        for op in OpcodeCommand:
            if op.name.lower() != op_name:
                continue
            opcode_addrs.append(
                (op, addrs["start"], addrs.get("end")))

    return sorted(opcode_addrs, key=lambda x: (x[1], x[2]))


def _FillOpcodeAddresses():
    """Populate _START and _END on opcodes from symbol table."""
    idx = 0
    for op, start, end in _OPCODE_ADDRS:
        cls = _OPCODE_CLASSES[op]
        cls._START = start
        cls._END = end
        idx += 1


_OPCODE_ADDRS = _ParseSymbolTable()
_OPCODE_CLASSES = {
    OpcodeCommand.STORE: Store,
    OpcodeCommand.SET_CONTENT: SetContent,
    OpcodeCommand.SET_PAGE: SetPage,
    OpcodeCommand.RLE: RLE,
    OpcodeCommand.TICK: Tick,
    OpcodeCommand.TERMINATE: Terminate,
    OpcodeCommand.NOP: Nop,
    OpcodeCommand.ACK: Ack,
}
_FillOpcodeAddresses()


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
