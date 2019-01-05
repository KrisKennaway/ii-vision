from typing import Tuple

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

    ADDR_TO_COORDS = {}
    for p in range(2):
        for y in range(192):
            for x in range(40):
                a = Y_TO_BASE_ADDR[p][y] + x
                ADDR_TO_COORDS[a] = (p, y, x)

    def __init__(self, screen_page: int, bytemap: screen.Bytemap):
        self.screen_page = screen_page  # type: int
        self.bytemap = bytemap

    def to_page_offset(self, x_byte: int, y: int) -> Tuple[int, int]:
        y_base = self.Y_TO_BASE_ADDR[self.screen_page][y]
        page = y_base >> 8

        # print("y=%d -> page=%02x" % (y, page))
        offset = y_base - (page << 8) + x_byte
        return page, offset

    def write(self, addr: int, val: int) -> None:
        """Updates screen image to set 0xaddr ^= val"""
        try:
            _, y, x = self.ADDR_TO_COORDS[addr]
        except KeyError:
            # TODO: filter out screen holes
            # print("Attempt to write to invalid offset %04x" % addr)
            return
        self.bytemap.bytemap[y][x] = val
