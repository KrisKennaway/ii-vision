"""Representation of Apple II + player virtual machine state."""

from typing import Iterator


# TODO: screen memory changes should happen via Machine while emitting opcodes?

class Machine:
    """Represents Apple II and player virtual machine state."""

    def emit(self, opcode: "Opcode") -> Iterator[int]:
        """

        :param opcode:
        :return:
        """
        cmd = opcode.emit_command(opcode)
        if cmd:
            yield from cmd
        data = opcode.emit_data()
        if data:
            yield from data

        # Update changes in memory map, if any
        opcode.apply(self)
