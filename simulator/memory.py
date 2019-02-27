from collections import defaultdict

from py65 import memory


class WriteProtectedException(Exception):
    def __init__(self, name, addr, value):
        self.name = name
        self.addr = addr
        self.value = value

    def __str__(self):
        return 'Write denied to %s ($%04X): $%02X' % (
            self.name, self.addr, self.value)


class UndefinedEntryPointException(Exception):
    def __init__(self, region, prev_addr, addr):
        self.region = region
        self.prev_addr = prev_addr
        self.addr = addr

    def __str__(self):
        return 'Entered region %s via undefined entry point: $%04X --> $%04X' % (
            self.region.name, self.prev_addr, self.addr)


class MemoryRegion:
    def __init__(
            self, name, start, end, read_interceptor=None,
            write_interceptor=None, entrypoints=None,
            writable=True):
        self.name = name
        self.start = start
        self.end = end

        self.read_interceptor = read_interceptor
        self.write_interceptor = write_interceptor

        self.writable = writable

        # Maps PC to handler
        self.entrypoints = entrypoints or {}


class MemoryManager:
    def __init__(self, memory_map):
        self.entrypoints = defaultdict(list)

        default_region = MemoryRegion('default', 0x0, 0xffff)

        def _default_region():
            return default_region

        self.regions = defaultdict(_default_region)

        self.memory = memory.ObservableMemory()

        self._memory_map = memory_map

    def enable(self):
        for region in self._memory_map:
            self.RegisterRegion(region)

    def MaybeInterceptExecution(self, cpu, old_pc):
        pc = cpu.pc
        if pc in self.entrypoints:
            handlers = self.entrypoints[pc]
        else:
            handlers = []

        if self.regions[old_pc] != self.regions[pc]:
            print("Entering region %s" % self.regions[pc].name)
            if not handlers:
                raise UndefinedEntryPointException(self.regions[pc], old_pc, pc)

        for handler in handlers:
            handler(cpu)

    def RegisterRegion(self, region):
        addr_range = range(region.start, region.end + 1)

        if region.read_interceptor:
            self.memory.subscribe_to_read(addr_range, region.read_interceptor)

        if region.write_interceptor:
            self.memory.subscribe_to_write(addr_range, region.write_interceptor)

        if not region.writable:
            self.memory.subscribe_to_write(addr_range,
                                           self.DenyWritesToRegion(region))

        for addr in addr_range:
            self.regions[addr] = region

        for addr, handler in region.entrypoints.items():
            self.entrypoints[addr].append(handler)

        # TODO: should trap by default

    @staticmethod
    def DenyWritesToRegion(region):
        def _DenyWritesInterceptor(addr, value):
            raise WriteProtectedException(region.name, addr, value)

        return _DenyWritesInterceptor
