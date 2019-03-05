import enum
import numpy as np
from typing import Iterator, Tuple

import screen
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
                 memmap: screen.MemoryMap, update_priority: np.array):
        self.page = 0x20
        self.content = 0x7f

        self.memmap = memmap
        self.cycle_counter = cycle_counter
        self.update_priority = update_priority

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
    TICK_4 = 4
    TICK_6 = 6
    TICK_8 = 8
    TICK_10 = 10
    TICK_12 = 12
    TICK_14 = 14
    TICK_16 = 16
    TICK_18 = 18
    TICK_20 = 20
    TICK_22 = 22
    TICK_24 = 24
    TICK_26 = 26
    TICK_28 = 28
    TICK_30 = 30
    TICK_32 = 32
    TICK_34 = 34
    TICK_36 = 36
    TICK_38 = 38
    TICK_40 = 40
    TICK_42 = 42
    TICK_44 = 44
    TICK_46 = 46
    TICK_48 = 48
    TICK_50 = 50
    TICK_52 = 52
    TICK_54 = 54
    TICK_56 = 56
    TICK_58 = 58
    TICK_60 = 60
    TICK_62 = 62
    TICK_64 = 64
    TICK_66 = 66



class Opcode:
    COMMAND = None  # type: OpcodeCommand
    _CYCLES = None  # type: int

    # Offset of start byte in decoder opcode
    _START = None  # type: int

    # Offset of last byte in decoder opcode
    _END = None  # type: int

    # Opcode uses relative addressing to branch to next opcode
    _RELATIVE_BRANCH = False

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
        if last_opcode._RELATIVE_BRANCH:
            offset = (opcode._START - last_opcode._END - 1) & 0xff

            # print("%s -> %s = %02x" % (last_opcode, opcode, offset))
            #yield offset
        else:
            yield opcode._START >> 8
            yield opcode._START & 0xff

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

    _RELATIVE_BRANCH = True

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
        state.memmap.write(state.page, self.offset, state.content)
        # TODO: screen page
        state.update_priority[state.page - 32, self.offset] = 0


class SetContent(Opcode):
    COMMAND = OpcodeCommand.SET_CONTENT
    _CYCLES = 15

    _RELATIVE_BRANCH = True

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

    _RELATIVE_BRANCH = True

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

    _RELATIVE_BRANCH = True

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
        yield self.run_length - 1

    @property
    def cycles(self):
        return 22 + 10 * self.run_length

    def apply(self, state):
        for i in range(self.run_length):
            offset = (self.start_offset + i) & 0xff
            state.memmap.write(state.page, offset, state.content)
            # TODO: screen page
            state.update_priority[state.page - 32, offset] = 0


class Tick(Opcode):
    COMMAND = OpcodeCommand.TICK

    _RELATIVE_BRANCH = True

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


class BaseTick(Opcode):
    _CYCLES = 73

    def __data_eq__(self, other):
        return True

    def emit_data(self):
        yield 0xff  # content
        yield 0x00  # offset 1
        yield 0x00  # offset 1
        yield 0x00  # offset 1
        yield 0x00  # offset 1


class Tick4(BaseTick):
    COMMAND = OpcodeCommand.TICK_4


class Tick6(BaseTick):
    COMMAND = OpcodeCommand.TICK_6


class Tick8(BaseTick):
    COMMAND = OpcodeCommand.TICK_8


class Tick10(BaseTick):
    COMMAND = OpcodeCommand.TICK_10


class Tick12(BaseTick):
    COMMAND = OpcodeCommand.TICK_12


class Tick14(BaseTick):
    COMMAND = OpcodeCommand.TICK_14


class Tick16(BaseTick):
    COMMAND = OpcodeCommand.TICK_16


class Tick18(BaseTick):
    COMMAND = OpcodeCommand.TICK_18


class Tick20(BaseTick):
    COMMAND = OpcodeCommand.TICK_20


class Tick22(BaseTick):
    COMMAND = OpcodeCommand.TICK_22


class Tick24(BaseTick):
    COMMAND = OpcodeCommand.TICK_24


class Tick26(BaseTick):
    COMMAND = OpcodeCommand.TICK_26


class Tick28(BaseTick):
    COMMAND = OpcodeCommand.TICK_28


class Tick30(BaseTick):
    COMMAND = OpcodeCommand.TICK_30


class Tick32(BaseTick):
    COMMAND = OpcodeCommand.TICK_32


class Tick34(BaseTick):
    COMMAND = OpcodeCommand.TICK_34


class Tick36(BaseTick):
    COMMAND = OpcodeCommand.TICK_36


class Tick38(BaseTick):
    COMMAND = OpcodeCommand.TICK_38


class Tick40(BaseTick):
    COMMAND = OpcodeCommand.TICK_40


class Tick42(BaseTick):
    COMMAND = OpcodeCommand.TICK_42


class Tick44(BaseTick):
    COMMAND = OpcodeCommand.TICK_44


class Tick46(BaseTick):
    COMMAND = OpcodeCommand.TICK_46


class Tick48(BaseTick):
    COMMAND = OpcodeCommand.TICK_48


class Tick50(BaseTick):
    COMMAND = OpcodeCommand.TICK_50


class Tick52(BaseTick):
    COMMAND = OpcodeCommand.TICK_52


class Tick54(BaseTick):
    COMMAND = OpcodeCommand.TICK_54


class Tick56(BaseTick):
    COMMAND = OpcodeCommand.TICK_56


class Tick58(BaseTick):
    COMMAND = OpcodeCommand.TICK_58


class Tick60(BaseTick):
    COMMAND = OpcodeCommand.TICK_60


class Tick62(BaseTick):
    COMMAND = OpcodeCommand.TICK_62


class Tick64(BaseTick):
    COMMAND = OpcodeCommand.TICK_64


class Tick66(BaseTick):
    COMMAND = OpcodeCommand.TICK_66




def _ParseSymbolTable():
    """Read symbol table from video player debug file."""

    opcode_data = {}
    for name, data in symbol_table.SymbolTable(
            "audiotest/audiotest/audiotest.dbg").parse().items():
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
#    OpcodeCommand.STORE: Store,
#    OpcodeCommand.SET_CONTENT: SetContent,
#    OpcodeCommand.SET_PAGE: SetPage,
#    OpcodeCommand.RLE: RLE,
#    OpcodeCommand.TICK: Tick,
#    OpcodeCommand.TERMINATE: Terminate,
    OpcodeCommand.NOP: Nop,
    OpcodeCommand.ACK: Ack,
    OpcodeCommand.TICK_4: Tick4,
    OpcodeCommand.TICK_6: Tick6,
    OpcodeCommand.TICK_8: Tick8,
    OpcodeCommand.TICK_10: Tick10,
    OpcodeCommand.TICK_12: Tick12,
    OpcodeCommand.TICK_14: Tick14,
    OpcodeCommand.TICK_16: Tick16,
    OpcodeCommand.TICK_18: Tick18,
    OpcodeCommand.TICK_20: Tick20,
    OpcodeCommand.TICK_22: Tick22,
    OpcodeCommand.TICK_24: Tick24,
    OpcodeCommand.TICK_26: Tick26,
    OpcodeCommand.TICK_28: Tick28,
    OpcodeCommand.TICK_30: Tick30,
    OpcodeCommand.TICK_32: Tick32,
    OpcodeCommand.TICK_34: Tick34,
    OpcodeCommand.TICK_36: Tick36,
    OpcodeCommand.TICK_38: Tick38,
    OpcodeCommand.TICK_40: Tick40,
    OpcodeCommand.TICK_42: Tick42,
    OpcodeCommand.TICK_44: Tick44,
    OpcodeCommand.TICK_46: Tick46,
    OpcodeCommand.TICK_48: Tick48,
    OpcodeCommand.TICK_50: Tick50,
    OpcodeCommand.TICK_52: Tick52,
    OpcodeCommand.TICK_54: Tick54,
    OpcodeCommand.TICK_56: Tick56,
    OpcodeCommand.TICK_58: Tick58,
    OpcodeCommand.TICK_60: Tick60,
    OpcodeCommand.TICK_62: Tick62,
    OpcodeCommand.TICK_64: Tick64,
    OpcodeCommand.TICK_66: Tick66,
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
