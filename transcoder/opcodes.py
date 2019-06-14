"""Opcodes representing discrete operations of video player."""

import enum
from typing import Iterator, Tuple

import symbol_table
import video_mode
from machine import Machine


def _op_cmds():
    """Construct names of player opcodes."""

    op_cmds = [
        "HEADER",
        "TERMINATE",
        "NOP",
        "ACK",
    ]
    for tick in range(4, 68, 2):
        for page in range(32, 64):
            op_cmds.append("TICK_%d_PAGE_%d" % (tick, page))
    return op_cmds


OpcodeCommand = enum.Enum("OpcodeCommand", _op_cmds())


class Opcode:
    """Base class for opcodes."""
    COMMAND = None  # type: OpcodeCommand

    # Offset of start byte of player opcode implementation
    _START = None  # type: int

    def __repr__(self):
        return "Opcode(%s)" % self.COMMAND.name

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False

        return self.__data_eq__(other)

    def __data_eq__(self, other):
        raise NotImplementedError

    @staticmethod
    def emit_command(opcode: "Opcode") -> Iterator[int]:
        # Emit address of opcode
        yield opcode._START >> 8
        yield opcode._START & 0xff

    def emit_data(self) -> Iterator[int]:
        return

    def apply(self, state: Machine):
        # TODO: we are no longer using this, but perhaps should be - it might
        # be easier to apply machine state changes (screen/memory
        # representations) via callback instead of tracking them individually.
        pass


class Header(Opcode):
    """Video header opcode."""
    COMMAND = OpcodeCommand.HEADER

    def __init__(self, mode: video_mode.VideoMode):
        self.video_mode = mode

    def __data_eq__(self, other):
        return self.video_mode == other.video_mode

    @staticmethod
    def emit_command(opcode: "Opcode") -> Iterator[int]:
        # This is special in that it does not explicitly vector to the next
        # opcode
        return

    def emit_data(self) -> Iterator[int]:
        # Pad bytes to same size as Tick opcode, to make it easier to schedule
        # ACK opcodes.
        yield 0xff
        yield 0xff
        yield 0xff
        yield 0xff
        yield 0xff
        yield 0xff

        yield self.video_mode.value


class Nop(Opcode):
    """NOP pad opcode that does nothing except vector to the next one."""
    COMMAND = OpcodeCommand.NOP

    def __data_eq__(self, other):
        return True


class Terminate(Opcode):
    """Terminates video playback."""
    COMMAND = OpcodeCommand.TERMINATE

    def __data_eq__(self, other):
        return True


class Ack(Opcode):
    """Instructs player to perform TCP stream + buffer management."""
    COMMAND = OpcodeCommand.ACK

    def __init__(self, aux_active: bool):
        self.aux_active = aux_active

    def emit_data(self) -> Iterator[int]:
        # Flip $C054 or $C055 soft-switches to steer subsequent writes to
        # MAIN/AUX screen memory
        yield 0x55 if self.aux_active else 0x54
        # Dummy byte to pad out TCP frame
        yield 0xff

    def __data_eq__(self, other):
        return self.aux_active == other.aux_active


class BaseTick(Opcode):
    """Base class for "fat" audio + video opcode.

    Each such opcode is specialized for a particular HiRes graphics page,
    and speaker duty cycle count.  The opcode also stores the provided
    content byte at 4 offsets on this graphics page.
    """

    def __init__(self, content: int, offsets: Tuple):
        self.content = content
        if len(offsets) != 4:
            raise ValueError("Wrong number of offsets: %d != 4" % len(offsets))
        self.offsets = offsets

    def __data_eq__(self, other):
        return self.content == other.content and self.offsets == other.offsets

    def emit_data(self):
        yield self.content  # content
        yield from self.offsets


def _make_tick_opcodes():
    # Dynamically construct classes for each of the tick opcodes.
    tick_opcodes = {}

    for _tick in range(4, 68, 2):
        for _page in range(32, 64):
            tick_opcodes[(_tick, _page)] = type(
                "Tick%dPage%d" % (_tick, _page),
                (BaseTick,),
                {
                    "COMMAND": OpcodeCommand["TICK_%d_PAGE_%d" % (_tick, _page)]
                }
            )
    return tick_opcodes


TICK_OPCODES = _make_tick_opcodes()


def _parse_symbol_table():
    """Read symbol table from video player debug file."""

    opcode_data = {}
    for name, data in symbol_table.SymbolTable(
            "player/iivision.dbg").parse().items():
        if name.startswith("\"op_"):
            op_name = name[4:-1]
            start_addr = int(data["val"], 16)

            opcode_data.setdefault(op_name, {})["start"] = start_addr

    opcode_addrs = []
    for op_name, addrs in opcode_data.items():
        for op in OpcodeCommand:
            if op.name.lower() != op_name:
                continue
            opcode_addrs.append((op, addrs["start"]))

    return sorted(opcode_addrs, key=lambda x: x[1])


def _fill_opcode_addresses():
    """Populate _START on opcodes from symbol table."""

    _OPCODE_ADDRS = _parse_symbol_table()
    _OPCODE_CLASSES = {
        OpcodeCommand.HEADER: Header,
        OpcodeCommand.TERMINATE: Terminate,
        OpcodeCommand.NOP: Nop,
        OpcodeCommand.ACK: Ack,
    }

    for _tick in range(4, 68, 2):
        for _page in range(32, 64):
            _tickop = OpcodeCommand["TICK_%d_PAGE_%d" % (_tick, _page)]
            _OPCODE_CLASSES[_tickop] = TICK_OPCODES[(_tick, _page)]
    for op, start in _OPCODE_ADDRS:
        cls = _OPCODE_CLASSES[op]
        cls._START = start

    for op, cls in _OPCODE_CLASSES.items():
        if not cls._START:
            raise ValueError(
                "Unable to find opcode address for %s in player debug symbols"
                % op
            )


_fill_opcode_addresses()
