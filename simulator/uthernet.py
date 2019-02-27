import machine
import memory


class Uthernet(machine.Machine):
    """Uthernet/W5100 device simulator."""

    def __init__(self, stream:bytes):
        memory_map = [
            memory.MemoryRegion(
                "Registers", 0x0000, 0x002f,
                read_interceptor=self.io_interceptor,
                write_interceptor=self.io_interceptor),
            memory.MemoryRegion(
                "Socket registers", 0x0400, 0x07ff,
                read_interceptor=self.io_interceptor,
                write_interceptor=self.io_interceptor),
            memory.MemoryRegion("TX Memory", 0x4000, 0x5fff),
            memory.MemoryRegion("RX Memory", 0x6000, 0x7fff),
        ]

        self.memory_manager = memory.MemoryManager(memory_map)
        self.memory = self.memory_manager.memory

        self.memory_manager.enable()

        self._indirect_bus_mode = False  # type: bool
        self._auto_increment = False  # type: bool

        # Address read pointer
        self.ptr = 0x0000

        # Inbound data to buffer via TCP socket
        self.stream = stream

        def _mode(mode, value):
            if not (mode & machine.AccessMode.WRITE):
                return
            # 7 - reset
            # 1 - address auto-increment
            # 0 - indirect bus mode
            assert value & 0b10000011 == value, value
            self._indirect_bus_mode = bool(value & 1)
            self._auto_increment = bool(value & (1 << 1))
            machine.Log(
                "Uthernet", "Indirect bus mode: %s, Auto-incr: %s" % (
                    self._indirect_bus_mode, self._auto_increment
                ))
            if value & (1 << 7):
                self.reset()

        def _socket_mode(mode, value):
            if not (mode & machine.AccessMode.WRITE):
                return

            # 5 - delayed ACK disabled
            # 3 - 0 for TCP
            # 2 - 0 for TCP
            # 1 - 0 for TCP
            # 0 - 1 for TCP

            assert value == 0b100001, value

        def _socket_command(mode, value):
            if not (mode & machine.AccessMode.WRITE):
                return

            def _OPEN():
                # Move TCP status to SOCK_INIT
                self.memory[0x403] = 0x13
                machine.Log("Uthernet", "Opening socket 0")

            def _CONNECT():
                # Move TCP status to SOCK_ESTABLISHED
                self.memory[0x403] = 0x17

            def _RECV():
                raise NotImplementedError

            commands = {
                0x01: _OPEN,
                # 0x02: _LISTEN,
                0x04: _CONNECT,
                # 0x08: _DISCON,
                # 0x10: _CLOSE,
                # 0x20: _SEND,
                # 0x21: _SEND_MAC,
                # 0x22: _SEND_KEEP,
                0x40: _RECV,
            }
            handler = commands.get(value)
            if handler:
                handler()

        self.io_map = {
            # CONTROL REGISTERS

            0x0000: (
                machine.AccessMode.RW, "Mode", _mode),
            0x0001: (
                machine.AccessMode.RW, "Gateway Address 0", None),
            0x0002: (
                machine.AccessMode.RW, "Gateway Address 1", None),
            0x0003: (
                machine.AccessMode.RW, "Gateway Address 2", None),
            0x0004: (
                machine.AccessMode.RW, "Gateway Address 3", None),
            0x0005: (
                machine.AccessMode.RW, "Subnet Mask Address 0", None),
            0x0006: (
                machine.AccessMode.RW, "Subnet Mask Address 1", None),
            0x0007: (
                machine.AccessMode.RW, "Subnet Mask Address 2", None),
            0x0008: (
                machine.AccessMode.RW, "Subnet Mask Address 3", None),
            0x0009: (
                machine.AccessMode.RW, "Source Hardware Address 0", None),
            0x000a: (
                machine.AccessMode.RW, "Source Hardware Address 1", None),
            0x000b: (
                machine.AccessMode.RW, "Source Hardware Address 2", None),
            0x000c: (
                machine.AccessMode.RW, "Source Hardware Address 3", None),
            0x000d: (
                machine.AccessMode.RW, "Source Hardware Address 4", None),
            0x000e: (
                machine.AccessMode.RW, "Source Hardware Address 5", None),
            0x000f: (
                machine.AccessMode.RW, "Source IP Address 0", None),
            0x0010: (
                machine.AccessMode.RW, "Source IP Address 1", None),
            0x0011: (
                machine.AccessMode.RW, "Source IP Address 2", None),
            0x0012: (
                machine.AccessMode.RW, "Source IP Address 3", None),
            0x0015: (
                machine.AccessMode.RW, "Interrupt",
                self.unimplemented_io_callback),
            0x0016: (
                machine.AccessMode.RW, "Interrupt Mask",
                self.unimplemented_io_callback),
            0x0017: (
                machine.AccessMode.RW, "Retry Time 0",
                self.unimplemented_io_callback),
            0x0018: (
                machine.AccessMode.RW, "Retry Time 1",
                self.unimplemented_io_callback),
            0x0019: (
                machine.AccessMode.RW, "Retry Count",
                self.unimplemented_io_callback),
            0x001a: (
                machine.AccessMode.RW, "RX Memory Size", None),
            0x001b: (
                machine.AccessMode.RW, "TX Memory Size", None),
            0x001c: (
                machine.AccessMode.RW, "PPPoE Auth Type 0",
                self.unimplemented_io_callback),
            0x001d: (
                machine.AccessMode.RW, "PPPoE Auth Type 1",
                self.unimplemented_io_callback),
            0x0028: (
                machine.AccessMode.RW, "PPP LCP Request Timer",
                self.unimplemented_io_callback),
            0x0029: (
                machine.AccessMode.RW, "PPP LCP Magic Number",
                self.unimplemented_io_callback),
            0x002a: (
                machine.AccessMode.RW, "Unreachable IP Address 0",
                self.unimplemented_io_callback),
            0x002b: (
                machine.AccessMode.RW, "Unreachable IP Address 1",
                self.unimplemented_io_callback),
            0x002c: (
                machine.AccessMode.RW, "Unreachable IP Address 2",
                self.unimplemented_io_callback),
            0x002d: (
                machine.AccessMode.RW, "Unreachable IP Address 3",
                self.unimplemented_io_callback),
            0x002e: (
                machine.AccessMode.RW, "Unreachable Port 0",
                self.unimplemented_io_callback),
            0x002f: (
                machine.AccessMode.RW, "Unreachable Port 0",
                self.unimplemented_io_callback),

            # SOCKET 0 registers

            0x0400: (
                machine.AccessMode.RW, "Socket 0 Mode",
                _socket_mode),
            0x0401: (
                machine.AccessMode.RW, "Socket 0 Command",
                _socket_command),
            0x0402: (
                machine.AccessMode.RW, "Socket 0 Interrupt",
                self.unimplemented_io_callback),
            0x0403: (
                machine.AccessMode.RW, "Socket 0 Status", None),
            0x0404: (
                machine.AccessMode.RW, "Socket 0 Source Port 0", None),
            0x0405: (
                machine.AccessMode.RW, "Socket 0 Source Port 1", None),
            0x0406: (
                machine.AccessMode.RW, "Socket 0 Dest HW Addr 0",
                self.unimplemented_io_callback),
            0x0407: (
                machine.AccessMode.RW, "Socket 0 Dest HW Addr 1",
                self.unimplemented_io_callback),
            0x0408: (
                machine.AccessMode.RW, "Socket 0 Dest HW Addr 2",
                self.unimplemented_io_callback),
            0x0409: (
                machine.AccessMode.RW, "Socket 0 Dest HW Addr 3",
                self.unimplemented_io_callback),
            0x040a: (
                machine.AccessMode.RW, "Socket 0 Dest HW Addr 4",
                self.unimplemented_io_callback),
            0x040b: (
                machine.AccessMode.RW, "Socket 0 Dest HW Addr 5",
                self.unimplemented_io_callback),
            0x040c: (
                machine.AccessMode.RW, "Socket 0 Dest IP Addr 0", None),
            0x040d: (
                machine.AccessMode.RW, "Socket 0 Dest IP Addr 1", None),
            0x040e: (
                machine.AccessMode.RW, "Socket 0 Dest IP Addr 2", None),
            0x040f: (
                machine.AccessMode.RW, "Socket 0 Dest IP Addr 3", None),
            0x0410: (
                machine.AccessMode.RW, "Socket 0 Dest Port 0", None),
            0x0411: (
                machine.AccessMode.RW, "Socket 0 Dest Port 1", None),
            0x0412: (
                machine.AccessMode.RW, "Socket 0 MSS 0",
                self.unimplemented_io_callback),
            0x0413: (
                machine.AccessMode.RW, "Socket 0 MSS 1",
                self.unimplemented_io_callback),
            0x0414: (
                machine.AccessMode.RW, "Socket 0 Protocol",
                self.unimplemented_io_callback),
            0x0415: (
                machine.AccessMode.RW, "Socket 0 IP TOS",
                self.unimplemented_io_callback),
            0x0416: (
                machine.AccessMode.RW, "Socket 0 IP TTL",
                self.unimplemented_io_callback),
            0x0420: (
                machine.AccessMode.RW, "Socket 0 TX Free Size 0",
                self.unimplemented_io_callback),
            0x0421: (
                machine.AccessMode.RW, "Socket 0 TX Free Size 1",
                self.unimplemented_io_callback),
            0x0422: (
                machine.AccessMode.RW, "Socket 0 TX Read Ptr 0",
                self.unimplemented_io_callback),
            0x0423: (
                machine.AccessMode.RW, "Socket 0 TX Read Ptr 1",
                self.unimplemented_io_callback),
            0x0424: (
                machine.AccessMode.RW, "Socket 0 TX Write Ptr 0",
                self.unimplemented_io_callback),
            0x0425: (
                machine.AccessMode.RW, "Socket 0 TX Write Ptr 1",
                self.unimplemented_io_callback),
            0x0426: (
                machine.AccessMode.RW, "Socket 0 RX Received Size 0", None),
            0x0427: (
                machine.AccessMode.RW, "Socket 0 RX Received Size 1", None),
            0x0428: (
                machine.AccessMode.RW, "Socket 0 RX Read Ptr 0", None),
            0x0429: (
                machine.AccessMode.RW, "Socket 0 RX Read Ptr 1", None),
        }

    def read_data(self):
        val = self.memory[self.ptr]
        self.ptr = (self.ptr + 1) & 0x7fff
        return val

    def write_data(self, value):
        self.memory[self.ptr] = value
        self.ptr = (self.ptr + 1) & 0x7fff
        return

    def read_mode(self):
        return self.memory[0x0000]

    def write_mode(self, value):
        self.memory[0x0000] = value

    def reset(self):
        # TODO: what state should be reset?
        machine.Log("Uthernet", "Resetting")

    def fill_socket(self):
        # TODO: assumes 4k socket rx buffer
        print("")