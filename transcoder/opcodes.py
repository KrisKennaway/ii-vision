"""Opcodes representing discrete operations of video player."""

import enum
from typing import Iterator, Tuple

import symbol_table
from machine import Machine

_op_cmds = [
    "TERMINATE",
    "NOP",
    "ACK",
]
for tick in range(4, 68, 2):
    for page in range(32, 64):
        _op_cmds.append("TICK_%d_PAGE_%d" % (tick, page))

OpcodeCommand = enum.Enum("OpcodeCommand", _op_cmds)


class Opcode:
    COMMAND = None  # type: OpcodeCommand

    # Offset of start byte in decoder opcode
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
        # Emit address of next opcode
        yield opcode._START >> 8
        yield opcode._START & 0xff

    def emit_data(self) -> Iterator[int]:
        return

    def apply(self, state: Machine):
        pass


class Nop(Opcode):
    COMMAND = OpcodeCommand.NOP

    def __data_eq__(self, other):
        return True


class Terminate(Opcode):
    COMMAND = OpcodeCommand.TERMINATE

    def __data_eq__(self, other):
        return True


class Ack(Opcode):
    COMMAND = OpcodeCommand.ACK

    def emit_data(self) -> Iterator[int]:
        # Dummy bytes to pad out TCP frame
        yield 0xff
        yield 0xff

    def __data_eq__(self, other):
        return True


class BaseTick(Opcode):
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


TICK_OPCODES = {}

for _tick in range(4, 68, 2):
    for _page in range(32, 64):
        _cls = type(
            "Tick%dPage%d" % (_tick, _page),
            (BaseTick,),
            {
                "COMMAND": OpcodeCommand["TICK_%d_PAGE_%d" % (_tick, _page)]
            }
        )
        TICK_OPCODES[(_tick, _page)] = _cls


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
    for op, start in _OPCODE_ADDRS:
        cls = _OPCODE_CLASSES[op]
        cls._START = start


_OPCODE_ADDRS = _parse_symbol_table()
_OPCODE_CLASSES = {
    OpcodeCommand.TERMINATE: Terminate,
    OpcodeCommand.NOP: Nop,
    OpcodeCommand.ACK: Ack,
}

for _tick in range(4, 68, 2):
    for _page in range(32, 64):
        _tickop = OpcodeCommand["TICK_%d_PAGE_%d" % (_tick, _page)]
        _OPCODE_CLASSES[_tickop] = TICK_OPCODES[(_tick, _page)]
_fill_opcode_addresses()
