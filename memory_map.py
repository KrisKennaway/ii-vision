import numpy as np

import screen


def y_to_base_addr(y: int, page: int = 0) -> int:
    """Maps y coordinate to base address on given screen page"""
    a = y // 64
    d = y - 64 * a
    b = d // 8
    c = d - 8 * b

    addr = 8192 * (page + 1) + 1024 * c + 128 * b + 40 * a
    return addr


class MemoryMap:
    """Memory map representing screen memory."""

    # TODO: support DHGR

    Y_TO_BASE_ADDR = [
        [y_to_base_addr(y, screen_page) for y in range(192)]
        for screen_page in (0, 1)
    ]

    # Array mapping (page, offset) to x (byte) and y coords respectively
    PAGE_OFFSET_TO_X = np.zeros((32, 256), dtype=np.uint8)
    PAGE_OFFSET_TO_Y = np.zeros((32, 256), dtype=np.uint8)

    # Mask of which (page, offset) bytes represent screen holes
    SCREEN_HOLES = np.full((32, 256), True, dtype=np.bool)

    # Dict mapping memory address to (page, y, x_byte) tuple
    ADDR_TO_COORDS = {}
    for y in range(192):
        for x in range(40):
            y_base = Y_TO_BASE_ADDR[0][y]
            page = y_base >> 8
            offset = y_base - (page << 8) + x

            PAGE_OFFSET_TO_Y[page - 32, offset] = y
            PAGE_OFFSET_TO_X[page - 32, offset] = x
            # This (page, offset) is not a screen hole
            SCREEN_HOLES[page - 32, offset] = False

            for p in range(2):
                a = Y_TO_BASE_ADDR[p][y] + x
                ADDR_TO_COORDS[a] = (p, y, x)

    def __init__(self, screen_page: int, bytemap: screen.Bytemap):
        self.screen_page = screen_page  # type: int
        self.bytemap = bytemap

    # XXX move to bytemap class?
    @classmethod
    def to_memory_map(cls, bytemap: np.ndarray):
        # Numpy magic that constructs a new array indexed by (page, offset)
        # instead of (y, x).
        mmap = bytemap[cls.PAGE_OFFSET_TO_Y, cls.PAGE_OFFSET_TO_X]
        # Reset whatever values ended up in the screen holes after this mapping
        # (which came from default 0 values in PAGE_OFFSET_TO_X)
        mmap[cls.SCREEN_HOLES] = 0
        return mmap

    def write(self, addr: int, val: int) -> None:
        """Updates screen image to set 0xaddr = val"""
        try:
            _, y, x = self.ADDR_TO_COORDS[addr]
        except KeyError:
            # TODO: filter out screen holes
            # print("Attempt to write to invalid offset %04x" % addr)
            return
        self.bytemap.bytemap[y][x] = val
