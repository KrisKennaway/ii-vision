"""Various representations of Apple II video display."""

import numpy as np


# TODO: support DHGR


def bitmap_similarity(a1: np.array, a2: np.array) -> float:
    """Measure bitwise % similarity between two bitmap arrays"""
    bits_different = np.sum(np.logical_xor(a1, a2)).item()

    return 1. - (bits_different / (np.shape(a1)[0] * np.shape(a1)[1]))


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


class Bytemap:
    """Bitmap array with horizontal pixels packed into bytes."""

    def __init__(self, bytemap: np.array = None):
        self.bytemap = None  # type: np.array
        if bytemap is not None:
            if bytemap.shape != (192, 40):
                raise ValueError("Unexpected shape: %r" % (bytemap.shape,))
            self.bytemap = bytemap
        else:
            self.bytemap = np.zeros((192, 40), dtype=np.uint8)

    def to_memory_map(self, screen_page: int) -> "MemoryMap":
        # Numpy magic that constructs a new array indexed by (page, offset)
        # instead of (y, x).
        mmap = self.bytemap[PAGE_OFFSET_TO_Y, PAGE_OFFSET_TO_X]
        # Reset whatever values ended up in the screen holes after this mapping
        # (which came from default 0 values in PAGE_OFFSET_TO_X)
        mmap[SCREEN_HOLES] = 0
        return MemoryMap(screen_page, mmap)


class Bitmap:
    XMAX = None  # type: int
    YMAX = None  # type: int

    def __init__(self, bitmap: np.array = None):
        if bitmap is None:
            self.bitmap = np.zeros((self.YMAX, self.XMAX), dtype=bool)
        else:
            if bitmap.shape != (self.YMAX, self.XMAX):
                raise ValueError("Unexpected shape: %r" % (bitmap.shape,))
            self.bitmap = bitmap

    def randomize(self) -> None:
        self.bitmap = np.random.randint(
            2, size=(self.YMAX, self.XMAX), dtype=bool)

    @staticmethod
    def _to_bytemap(bitmap) -> Bytemap:
        # Insert zero column after every 7
        pixels = bitmap.copy()
        for i in range(pixels.shape[1] // 7 - 1, -1, -1):
            pixels = np.insert(pixels, (i + 1) * 7, False, axis=1)

        # packbits is big-endian so we flip the array before and after to
        # invert this
        return Bytemap(
            np.flip(np.packbits(np.flip(pixels, axis=1), axis=1), axis=1))

    def to_bytemap(self) -> Bytemap:
        return self._to_bytemap(self.bitmap)

    def to_memory_map(self, screen_page: int) -> "MemoryMap":
        return self.to_bytemap().to_memory_map(screen_page)

    @staticmethod
    def _from_bytemap(bytemap: Bytemap) -> np.array:
        bm = np.unpackbits(bytemap.bytemap, axis=1)
        bm = np.delete(bm, np.arange(0, bm.shape[1], 8), axis=1)

        # Need to flip each 7-bit sequence
        reorder_cols = []
        for i in range(bm.shape[1] // 7):
            for j in range((i + 1) * 7 - 1, i * 7 - 1, -1):
                reorder_cols.append(j)
        bm = bm[:, reorder_cols]

        return np.array(bm, dtype=np.bool)

    @classmethod
    def from_bytemap(cls, bytemap: Bytemap) -> "Bitmap":
        return cls(cls._from_bytemap(bytemap))


class HGR140Bitmap(Bitmap):
    XMAX = 140  # double-wide pixels to not worry about colour effects
    YMAX = 192

    def to_bytemap(self) -> Bytemap:
        # Double each pixel horizontally
        return self._to_bytemap(np.repeat(self.bitmap, 2, axis=1))

    @classmethod
    def from_bytemap(cls, bytemap: Bytemap) -> "HGR140Bitmap":
        # Undouble pixels
        bitmap = cls._from_bytemap(bytemap)
        bitmap = np.array(
            np.delete(bitmap, np.arange(0, bitmap.shape[1], 2), axis=1),
            dtype=np.bool
        )

        return HGR140Bitmap(bitmap)


class HGRBitmap(Bitmap):
    XMAX = 280
    YMAX = 192


class DHGRBitmap(Bitmap):
    XMAX = 560
    YMAX = 192


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

    def to_bytemap(self) -> Bytemap:
        bytemap = self.page_offset[X_Y_TO_PAGE, X_Y_TO_OFFSET]
        return Bytemap(bytemap)

    def write(self, page: int, offset: int, val: int) -> None:
        """Updates screen image to set (page, offset)=val (inc. screen holes)"""

        self.page_offset[page - self._page_start][offset] = val
