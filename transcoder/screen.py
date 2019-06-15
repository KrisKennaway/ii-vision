"""Various representations of Apple II video display."""

import bz2
import functools
import pickle
from typing import Union, List

import numpy as np
import palette

# Type annotation for cases where we may process either an int or a numpy array.
IntOrArray = Union[int, np.ndarray]


def y_to_base_addr(y: int, page: int = 0) -> int:
    """Maps y coordinate to base address on given screen page"""
    a = y // 64
    d = y - 64 * a
    b = d // 8
    c = d - 8 * b

    addr = 8192 * (page + 1) + 1024 * c + 128 * b + 40 * a
    return addr


Y_TO_BASE_ADDR = [
    [y_to_base_addr(y, screen_page) for y in range(192)]
    for screen_page in (0, 1)
]

# Array mapping (page, offset) to x (byte) and y coords respectively
# TODO: is np.dtype(int) faster for these?
PAGE_OFFSET_TO_X = np.zeros((32, 256), dtype=np.uint8)
PAGE_OFFSET_TO_Y = np.zeros((32, 256), dtype=np.uint8)

# Inverse mappings
X_Y_TO_PAGE = np.zeros((192, 40), dtype=np.uint8)
X_Y_TO_OFFSET = np.zeros((192, 40), dtype=np.uint8)

# Mask of which (page, offset) bytes represent screen holes
SCREEN_HOLES = np.full((32, 256), True, dtype=np.bool)

# Dict mapping memory address to (page, y, x_byte) tuple
ADDR_TO_COORDS = {}


def _populate_mappings():
    for y in range(192):
        for x in range(40):
            y_base = Y_TO_BASE_ADDR[0][y]
            page = y_base >> 8
            offset = y_base - (page << 8) + x

            PAGE_OFFSET_TO_Y[page - 32, offset] = y
            PAGE_OFFSET_TO_X[page - 32, offset] = x

            X_Y_TO_PAGE[y, x] = page - 32
            X_Y_TO_OFFSET[y, x] = offset

            # This (page, offset) is not a screen hole
            SCREEN_HOLES[page - 32, offset] = False

            for p in range(2):
                a = Y_TO_BASE_ADDR[p][y] + x
                ADDR_TO_COORDS[a] = (p, y, x)


_populate_mappings()


class FlatMemoryMap:
    """Linear 8K representation of HGR screen memory."""

    def __init__(self, screen_page: int, data: np.array = None):
        if screen_page not in [1, 2]:
            raise ValueError("Screen page out of bounds: %d" % screen_page)
        self.screen_page = screen_page  # type: int

        self._addr_start = 8192 * self.screen_page
        self._addr_end = self._addr_start + 8191

        self.data = None  # type: np.array
        if data is not None:
            if data.shape != (8192,):
                raise ValueError("Unexpected shape: %r" % (data.shape,))
            self.data = data
        else:
            self.data = np.zeros((8192,), dtype=np.uint8)

    def to_memory_map(self):
        return MemoryMap(self.screen_page, self.data.reshape((32, 256)))

    def write(self, addr: int, val: int) -> None:
        """Updates screen image to set 0xaddr = val (including screen holes)"""
        if addr < self._addr_start or addr > self._addr_end:
            raise ValueError("Address out of range: 0x%04x" % addr)
        self.data[addr - self._addr_start] = val


class MemoryMap:
    """Page/offset-structured representation of HGR screen memory."""

    def __init__(self, screen_page: int, page_offset: np.array = None):
        if screen_page not in [1, 2]:
            raise ValueError("Screen page out of bounds: %d" % screen_page)
        self.screen_page = screen_page  # type: int

        self._page_start = 32 * screen_page

        self.page_offset = None  # type: np.array
        if page_offset is not None:
            if page_offset.shape != (32, 256):
                raise ValueError("Unexpected shape: %r" % (page_offset.shape,))
            self.page_offset = page_offset
        else:
            self.page_offset = np.zeros((32, 256), dtype=np.uint8)

    def to_flat_memory_map(self) -> FlatMemoryMap:
        return FlatMemoryMap(self.screen_page, self.page_offset.reshape(8192))

    def write(self, page: int, offset: int, val: int) -> None:
        """Updates screen image to set (page, offset)=val (inc. screen holes)"""

        self.page_offset[page - self._page_start][offset] = val


class DHGRBitmap:
    BYTE_MASK32 = [
        #     3333333222222211111110000000 <- byte 0.3
        #
        # 33222222222211111111110000000000 <- bit pos in uint32
        # 10987654321098765432109876543210
        # 0000GGGGFFFFEEEEDDDDCCCCBBBBAAAA <- pixel A..G
        #     3210321032103210321032103210  <- bit pos in A..G pixel
        0b00000000000000000000000011111111,  # byte 0 influences A,B
        0b00000000000000001111111111110000,  # byte 1 influences B,C,D
        0b00000000111111111111000000000000,  # byte 2 influences D,E,F
        0b00001111111100000000000000000000,  # byte 3 influences F,G
    ]

    # How much to right-shift bits after masking to bring into int8/int12 range
    BYTE_SHIFTS = [0, 4, 12, 20]

    @staticmethod
    @functools.lru_cache(None)
    def edit_distances(palette_id: palette.Palette) -> List[np.ndarray]:
        """Load edit distance matrices for masked, shifted byte 0..3 values."""
        data = "transcoder/data/palette_%d_edit_distance.pickle.bz2" % (
            palette_id.value
        )
        with bz2.open(data, "rb") as ed:
            return pickle.load(ed)  # type: List[np.ndarray]

    def __init__(self, main_memory: MemoryMap, aux_memory: MemoryMap):
        self.main_memory = main_memory
        self.aux_memory = aux_memory

        self.packed = np.empty(shape=(32, 128), dtype=np.uint32)
        self._pack()

    def _pack(self) -> None:
        """Interleave and pack aux and main memory into 28-bit uint32 array"""

        # Palette bit is unused for DHGR so mask it out
        aux = (self.aux_memory.page_offset & 0x7f).astype(np.uint32)
        main = (self.main_memory.page_offset & 0x7f).astype(np.uint32)

        # Interleave aux and main memory columns and pack 7-bit masked values
        # into a 28-bit value.  This sequentially encodes 7 4-bit DHGR pixels.
        # See make_data_tables.py for more discussion about this representation.
        self.packed = (
                aux[:, 0::2] +
                (main[:, 0::2] << 7) +
                (aux[:, 1::2] << 14) +
                (main[:, 1::2] << 21)
        )

    @staticmethod
    @functools.lru_cache(None)
    def interleaved_byte_offset(x_byte: int, is_aux: bool) -> int:
        """Returns 0..3 offset in ByteTuple for a given x_byte and is_aux"""
        is_odd = x_byte % 2 == 1
        if is_aux:
            if is_odd:
                return 2
            return 0
        else:  # main memory
            if is_odd:
                return 3
            else:
                return 1

    @staticmethod
    def masked_update(
            byte_offset: int,
            old_value: IntOrArray,
            new_value: int) -> IntOrArray:
        # Mask out 7-bit value where update will go
        masked_value = old_value & ~(0x7f << (7 * byte_offset))

        update = (new_value & 0x7f) << (7 * byte_offset)

        return masked_value ^ update

    def apply(self, page: int, offset: int, is_aux: bool, value: int) -> None:
        """Update packed representation of changing main/aux memory."""

        byte_offset = self.interleaved_byte_offset(offset, is_aux)
        packed_offset = offset // 2

        self.packed[page, packed_offset] = self.masked_update(
            byte_offset, self.packed[page, packed_offset], value)

    def mask_and_shift_data(
            self,
            data: IntOrArray,
            byte_offset: int) -> IntOrArray:
        """Masks and shifts data into the 8 or 12-bit range."""
        return (data & self.BYTE_MASK32[byte_offset]) >> (
            self.BYTE_SHIFTS[byte_offset])
