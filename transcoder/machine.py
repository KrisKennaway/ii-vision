"""Representation of Apple II + player virtual machine state."""

from typing import Iterator

import numpy as np

import screen


class CycleCounter:
    """Counts clock cycles."""

    def __init__(self):
        self.cycles = 0  # type:int

    def tick(self, cycles: int) -> None:
        """Advance cycle counter by some number of clock ticks.

        :param cycles: How many clock cycles to advance
        """
        self.cycles += cycles

    def reset(self) -> None:
        """Reset cycle counter to 0."""

        self.cycles = 0


class Machine:
    """Represents Apple II and player virtual machine state."""

    def __init__(self, cycle_counter: CycleCounter,
                 memmap: screen.MemoryMap, update_priority: np.array):
        self.page = 0x20  # type: int
        self.content = 0x7f  # type: int

        self.memmap = memmap  # type: screen.MemoryMap
        self.cycle_counter = cycle_counter  # type: CycleCounter
        self.update_priority = update_priority  # type: np.array

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