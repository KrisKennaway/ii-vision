"""Abstract hardware machine with CPU and memory."""

import enum
from typing import Dict, Tuple, Callable, Optional

from py65 import memory as py65_memory


class AccessMode(enum.IntFlag):
    READ = 0x1
    WRITE = 0x2
    RW = READ | WRITE


class Event(object):
    def __init__(self, event_type, details):
        self.event_type = event_type
        self.details = details

    def __str__(self) -> str:
        return "Event(%s): %s" % (self.event_type, self.details)


def Log(region:str, message:str):
    print("%s event: %s" % (region, message))


# TODO: why?
def _Event(region:str, message:str):
    def _Event(_):
        Log(region, message)

    return _Event


class TrapException(Exception):
    def __init__(self, address:int, msg:str):
        self.address = address
        self.msg = msg

    def __str__(self) -> str:
        return "$%04X: %s" % (self.address, self.msg)


class SoftSwitch:
    def __init__(
            self, name: str, clear_addr: int, set_addr: int,
            status_addr: int, mode: AccessMode = AccessMode.WRITE,
            callback=None):
        self.name = name
        self.clear_addr = clear_addr
        self.set_addr = set_addr
        self.status_addr = status_addr

        # Whether switch is set/clear by READ/WRITE or both
        self.mode = mode  # type: AccessMode

        self.state = False  # type: bool
        self.callback = callback  # type: Callable[[bool], Optional[int]]

    def set(self) -> Optional[int]:
        self.state = True
        Log(self.name, "Setting soft switch")
        return self.callback(True)

    def clear(self) -> Optional[int]:
        self.state = False
        Log(self.name, "Clearing soft switch")
        return self.callback(False)

    def get(self) -> int:
        Log(self.name, "Reading soft switch (%s)" % (
            "on" if self.state else "off"))
        return 0x80 & self.state

    @staticmethod
    def unimplemented(_):
        raise NotImplementedError

    def register(self, io_map):
        def _clear(mode, value):
            return self.clear()

        def _set(mode, value):
            return self.set()

        def _get(mode, value):
            return self.get()

        io_map[self.clear_addr] = (
            self.mode, "%s OFF" % self.name, _clear)
        io_map[self.set_addr] = (
            self.mode, "%s ON" % self.name, _set)
        io_map[self.status_addr] = (
            AccessMode.READ, "%s READ" % self.name, _get)


class Machine:
    def __init__(self):
        self.memory_manager = None  # type: memory.MemoryManager
        self.memory = None  # type: py65_memory.ObservableMemory
        self.cpu = None

        self.io_map = {}  # type: Dict[int, Tuple[AccessMode, str, Callable]]

    @staticmethod
    def unimplemented_io_callback(mode, value):
        raise NotImplementedError

    def io_interceptor(self, address, value=None):
        access_mode = (
            AccessMode.READ if (value is None) else AccessMode.WRITE)

        try:
            (mode, name, callback) = self.io_map[address]

            if access_mode & mode:
                if access_mode & AccessMode.READ:
                    print("==== IO EVENT: READ %s" % name)
                else:
                    print("==== IO EVENT: WRITE %s -> %02x" % (name, value))
                if callback:
                    return callback(access_mode, value)
                else:
                    return
            else:
                print("**** IO EVENT with unexpected mode: %s" % access_mode)
                raise TrapException(address, access_mode)
        except KeyError:
            if value:
                raise TrapException(
                    address, 'Wrote %02X ("%s")' % (value, chr(value)))
            else:
                raise TrapException(address, 'Read')
