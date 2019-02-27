import machine
import memory
import uthernet
from py65 import disassembler
from py65.devices import mpu65c02


class AppleII(machine.Machine):
    def __init__(self, uthernet: uthernet.Uthernet):
        memory_map = [
            memory.MemoryRegion("Zero page", 0x0000, 0x00ff),
            memory.MemoryRegion("Stack", 0x0100, 0x01ff),
            memory.MemoryRegion(
                "Text page 1", 0x0400, 0x7ff,
                write_interceptor=self.TextPageWriteInterceptor),

            memory.MemoryRegion("HiRes Page 1", 0x2000, 0x2fff),
            memory.MemoryRegion("HiRes Page 2", 0x4000, 0x4fff, writable=False),

            memory.MemoryRegion(
                "IO page", 0xc000, 0xc0ff,
                read_interceptor=self.io_interceptor,
                write_interceptor=self.io_interceptor),

            memory.MemoryRegion("Slot 1 ROM", 0xc100, 0xc1ff, writable=False),
            memory.MemoryRegion("Slot 2 ROM", 0xc200, 0xc2ff, writable=False),
            memory.MemoryRegion("Slot 3 ROM", 0xc300, 0xc3ff, writable=False),
            memory.MemoryRegion("Slot 4 ROM", 0xc400, 0xc4ff, writable=False),
            memory.MemoryRegion("Slot 5 ROM", 0xc500, 0xc5ff, writable=False),
            memory.MemoryRegion("Slot 6 ROM", 0xc600, 0xc6ff, writable=False),
            memory.MemoryRegion("Slot 7 ROM", 0xc700, 0xc7ff, writable=False),

            memory.MemoryRegion(
                "ROM", 0xd000, 0xffff,
                entrypoints={
                    0xfca8: self._Wait,
                    0xfded: machine._Event("ROM", "COUT"),
                    0xfe89: machine._Event("ROM", "Select the keyboard (IN#0)")
                },
                writable=False
            )
        ]

        self.memory_manager = memory.MemoryManager(memory_map)
        self.memory = self.memory_manager.memory
        self.cpu = mpu65c02.MPU(memory=self.memory)

        self.uthernet = uthernet  # type: uthernet.Uthernet

        self.disassembler = disassembler.Disassembler(self.cpu)

        def _uther_wmode(mode, value):
            if mode & machine.AccessMode.READ:
                return self.uthernet.read_mode()
            else:
                return self.uthernet.write_mode(value)

        def _uther_wadrh(mode, value):
            old = self.uthernet.ptr
            self.uthernet.ptr = (value << 8) | (self.uthernet.ptr & 0x7f)
            machine.Log("WADRH", "%04x -> %04x" % (old, self.uthernet.ptr))

        def _uther_wadrl(mode, value):
            old = self.uthernet.ptr
            self.uthernet.ptr = (self.uthernet.ptr & 0x7f00) | value
            machine.Log("WADRL", "%04x -> %04x" % (old, self.uthernet.ptr))

        def _uther_wdata(mode, value):
            if mode & machine.AccessMode.READ:
                return self.uthernet.read_data()
            else:
                return self.uthernet.write_data(value)

        # Set up interceptors for accessing various interesting parts of the
        # memory map
        self.io_map = {
            0xc094: (
                machine.AccessMode.RW, "WMODE", _uther_wmode),
            0xc095: (
                machine.AccessMode.WRITE, "WADRH", _uther_wadrh),
            0xc096: (
                machine.AccessMode.WRITE, "WADRL", _uther_wadrl),
            0xc097: (
                machine.AccessMode.RW, "WDATA", _uther_wdata),
        }

        self.soft_switches = {}
        for ss in [
            machine.SoftSwitch(
                "80Store",
                clear_addr=0xc000,
                set_addr=0xc001,
                status_addr=0xc018,
                callback=machine.SoftSwitch.unimplemented
            ),
            machine.SoftSwitch(
                "RamRd",
                clear_addr=0xc002,
                set_addr=0xc003,
                status_addr=0xc013,
                callback=machine.SoftSwitch.unimplemented
            ),
            machine.SoftSwitch(
                "RamWrt",
                clear_addr=0xc004,
                set_addr=0xc005,
                status_addr=0xc014,
                callback=machine.SoftSwitch.unimplemented
            ),
            machine.SoftSwitch(
                "IntCxROM",
                clear_addr=0xc006,
                set_addr=0xc007,
                status_addr=0xc015,
                callback=machine.SoftSwitch.unimplemented
            ),
            machine.SoftSwitch(
                "AltZP",
                clear_addr=0xc008,
                set_addr=0xc009,
                status_addr=0xc016,
                callback=machine.SoftSwitch.unimplemented
            ),
            machine.SoftSwitch(
                "SlotC3ROM",
                clear_addr=0xc00a,
                set_addr=0xc00b,
                status_addr=0xc017,
                callback=machine.SoftSwitch.unimplemented
            ),
            machine.SoftSwitch(
                "80Col",
                clear_addr=0xc00c,
                set_addr=0xc00d,
                status_addr=0xc01f
            ),
            machine.SoftSwitch(
                "AltCharSet",
                clear_addr=0xc00e,
                set_addr=0xc00f,
                status_addr=0xc01e
            ),
            machine.SoftSwitch(
                "Text",
                clear_addr=0xc050,
                set_addr=0xc051,
                status_addr=0xc01a,
                mode=machine.AccessMode.RW
            ),
            machine.SoftSwitch(
                "Mixed",
                clear_addr=0xc052, set_addr=0xc053,
                status_addr=0xc01b,
                mode=machine.AccessMode.RW
            ),
            machine.SoftSwitch(
                "Page2",
                clear_addr=0xc054, set_addr=0xc055,
                status_addr=0xc01c,
                mode=machine.AccessMode.RW
            ),
            machine.SoftSwitch(
                "Hires",
                clear_addr=0xc056, set_addr=0xc057,
                status_addr=0xc01d,
                mode=machine.AccessMode.RW
            )
        ]:
            self.soft_switches[ss.name] = ss
            ss.register(self.io_map)

    @staticmethod
    def _Wait(_):
        print("Waiting")

    # TODO: convert addresses to screen coordinates
    # See e.g. https://retrocomputing.stackexchange.com/questions/2534/what-are-the-screen-holes-in-apple-ii-graphics
    @staticmethod
    def TextPageWriteInterceptor(address, value):
        print('Wrote "%s" to text page address $%04X' % (chr(value & 0x7f),
                                                         address))

    def Run(self, pc, trace=False):
        self.cpu.pc = pc
        old_pc = self.cpu.pc
        while True:
            self.memory_manager.MaybeInterceptExecution(self.cpu, old_pc)
            old_pc = self.cpu.pc
            if trace:
                print(self.cpu)
                print("  $%04X: %s" % (
                    self.cpu.pc,
                    self.disassembler.instruction_at(self.cpu.pc)[1]))
            self.cpu.step()
            if self.cpu.pc == old_pc:
                break
