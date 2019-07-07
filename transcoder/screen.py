"""Various representations of Apple II video display."""

import bz2
import functools
import pickle
from typing import Union, List, Optional, Tuple

import numpy as np

import palette as pal

# Type annotation for cases where we may process either an int or a numpy array.
IntOrArray = Union[np.uint64, np.ndarray]


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


class Bitmap:
    """Packed 28-bit bitmap representation of (D)HGR screen memory.

    XXX comments

    The memory layout is still page-oriented, not linear y-x buffer but the
    bit map is such that 20 consecutive entries linearly encode the 28*20 =
    560-bit monochrome dot positions that underlie both Mono and Colour (
    D)HGR screens.

    For Colour display the (nominal) colours are encoded as 4-bit pixels.
    """

    NAME = None  # type: str

    # Size of packed representation
    HEADER_BITS = None  # type: np.uint64
    BODY_BITS = None  # type: np.uint64
    FOOTER_BITS = None  # type: np.uint64

    BYTE_MASKS = None  # type: List[np.uint64]
    BYTE_SHIFTS = None  # type: List[np.uint64]

    # How many bits of packed representation are influenced when storing a
    # memory byte
    MASKED_BITS = None  # type: np.uint64

    # XXX
    PHASES = None  # type: List[int]

    def __init__(
            self,
            palette: pal.Palette,
            main_memory: MemoryMap,
            aux_memory: Optional[MemoryMap]
    ):
        self.palette = palette  # type: pal.Palette
        self.main_memory = main_memory  # type: MemoryMap
        self.aux_memory = aux_memory  # type: Optional[MemoryMap]

        self.PACKED_BITS = (
                self.HEADER_BITS + self.BODY_BITS + self.FOOTER_BITS
        )  # type: np.uint64

        # How many screen bytes we pack into a single scalar
        self.SCREEN_BYTES = np.uint64(len(self.BYTE_MASKS))  # type: np.uint64

        self.packed = np.empty(
            shape=(32, 128), dtype=np.uint64)  # type: np.ndarray
        self._pack()

    def _body(self) -> np.ndarray:
        raise NotImplementedError

    # TODO: don't leak headers/footers across screen rows.  We should be using
    # x-y representation rather than page-offset

    @staticmethod
    def _make_header(prev_col: IntOrArray) -> IntOrArray:
        raise NotImplementedError

    @staticmethod
    def _make_footer(next_col: IntOrArray) -> IntOrArray:
        raise NotImplementedError

    def _pack(self) -> None:
        """Pack MemoryMap into efficient representation for diffing."""

        body = self._body()

        # XXX comments
        # Prepend last 3 bits of previous main odd byte so we can correctly
        # decode the effective colours at the beginning of the 28-bit
        # tuple
        prev_col = np.roll(body, 1, axis=1).astype(np.uint64)
        header = self._make_header(prev_col)
        # Don't leak header across page boundaries
        header[:, 0] = 0

        # Append first 3 bits of next aux even byte so we can correctly
        # decode the effective colours at the end of the 28-bit tuple
        next_col = np.roll(body, -1, axis=1).astype(np.uint64)
        footer = self._make_footer(next_col)
        # Don't leak footer across page boundaries
        footer[:, -1] = 0

        self.packed = header ^ body ^ footer

    @staticmethod
    def masked_update(
            byte_offset: int,
            old_value: IntOrArray,
            new_value: np.uint8) -> IntOrArray:
        raise NotImplementedError

    @staticmethod
    @functools.lru_cache(None)
    def byte_offset(x_byte: int, is_aux: bool) -> int:
        raise NotImplementedError

    @staticmethod
    @functools.lru_cache(None)
    def _byte_offsets(is_aux: bool) -> Tuple[int, int]:
        raise NotImplementedError

    @classmethod
    def to_dots(cls, masked_val: int, byte_offset: int) -> int:
        raise NotImplementedError

    def apply(
            self,
            page: int,
            offset: int,
            is_aux: bool,
            value: np.uint8) -> None:
        """Update packed representation of changing main/aux memory."""

        byte_offset = self.byte_offset(offset, is_aux)
        packed_offset = offset // 2

        self.packed[page, packed_offset] = self.masked_update(
            byte_offset, self.packed[page, packed_offset], value)
        self._fix_scalar_neighbours(page, packed_offset, byte_offset)

    def _fix_scalar_neighbours(
            self,
            page: int,
            offset: int,
            byte_offset: int) -> None:

        if byte_offset == 0 and offset > 0:
            self.packed[page, offset - 1] = self._fix_column_left(
                self.packed[page, offset - 1],
                self.packed[page, offset]
            )
        elif byte_offset == (self.SCREEN_BYTES - 1) and offset < 127:
            # Need to also update the 3-bit header of the next column
            self.packed[page, offset + 1] = self._fix_column_right(
                self.packed[page, offset + 1],
                self.packed[page, offset]
            )

    def _fix_column_left(
            self,
            column_left: IntOrArray,
            column: IntOrArray
    ) -> IntOrArray:
        # Mask out footer(s)
        column_left &= np.uint64(2 ** (self.HEADER_BITS + self.BODY_BITS) - 1)
        column_left ^= self._make_footer(column)

        return column_left

    def _fix_column_right(
            self,
            column_right: IntOrArray,
            column: IntOrArray
    ) -> IntOrArray:
        # Mask out header(s)
        column_right &= np.uint64(
            (2 ** (self.BODY_BITS + self.FOOTER_BITS) - 1)) << self.HEADER_BITS
        column_right ^= self._make_header(column)

        return column_right

    def _fix_array_neighbours(
            self,
            ary: np.ndarray,
            byte_offset: int
    ) -> None:
        # Propagate new value into neighbouring byte headers/footers if
        # necessary
        if byte_offset == 0:
            # Need to also update the 3-bit footer of the preceding column
            shifted_left = np.roll(ary, -1, axis=1)
            self._fix_column_left(ary, shifted_left)

        elif byte_offset == 3:
            # Need to also update the 3-bit header of the next column
            shifted_right = np.roll(ary, 1, axis=1)
            self._fix_column_right(ary, shifted_right)

    @classmethod
    @functools.lru_cache(None)
    def edit_distances(cls, palette_id: pal.Palette) -> List[np.ndarray]:
        """Load edit distance matrices for masked, shifted byte values."""

        data = "transcoder/data/%s_palette_%d_edit_distance.pickle.bz2" % (
            cls.NAME,
            palette_id.value
        )
        with bz2.open(data, "rb") as ed:
            dist = pickle.load(ed)  # type: List[np.ndarray]

        # dist is an upper-triangular matrix of edit_distance(a, b)
        # encoded as dist[(a << N) + b] = edit_distance(a, b)
        # Because the distance metric is reflexive,
        #   edit_distance(b, a) = edit_distance(a, b)

        identity = np.arange(2 ** (2 * cls.MASKED_BITS), dtype=np.uint64)
        # Swap values of form a << N + b to b << N + a
        transpose = (identity >> cls.MASKED_BITS) + (
                (identity & np.uint64(2 ** cls.MASKED_BITS - 1)) <<
                cls.MASKED_BITS)

        for i in range(len(dist)):
            dist[i][transpose] += dist[i][identity]

        return dist

    @classmethod
    def mask_and_shift_data(
            cls,
            data: IntOrArray,
            byte_offset: int) -> IntOrArray:
        """Masks and shifts data into the MASKED_BITS range."""
        res = (data & cls.BYTE_MASKS[byte_offset]) >> (
            cls.BYTE_SHIFTS[byte_offset])
        assert np.all(res <= 2 ** cls.MASKED_BITS)
        return res

    # TODO: unit tests
    @functools.lru_cache(None)
    def byte_pair_difference(
            self,
            byte_offset: int,
            old_packed: np.uint64,
            content: np.uint8
    ) -> np.uint16:
        old_pixels = self.mask_and_shift_data(
            old_packed, byte_offset)
        new_pixels = self.mask_and_shift_data(
            self.masked_update(byte_offset, old_packed, content), byte_offset)

        pair = (old_pixels << self.MASKED_BITS) + new_pixels

        return self.edit_distances(self.palette)[byte_offset][pair]

    def diff_weights(
            self,
            source: "Bitmap",
            is_aux: bool
    ) -> np.ndarray:
        return self._diff_weights(source.packed, is_aux)

    def _diff_weights(
            self,
            source_packed: np.ndarray,
            is_aux: bool,
            content: np.uint8 = None
    ) -> np.ndarray:
        """Computes diff from source_packed to self.packed"""
        diff = np.ndarray((32, 256), dtype=np.int)

        offsets = self._byte_offsets(is_aux)

        dists = []
        for o in offsets:
            if content is not None:
                source_packed = self.masked_update(o, source_packed, content)
                self._fix_array_neighbours(source_packed, o)

            # Pixels influenced by byte offset o
            source_pixels = self.mask_and_shift_data(source_packed, o)
            target_pixels = self.mask_and_shift_data(self.packed, o)

            # Concatenate 13-bit source and target into 26-bit values
            pair = (source_pixels << self.MASKED_BITS) + target_pixels
            dist = self.edit_distances(self.palette)[o][pair].reshape(
                pair.shape)
            dists.append(dist)

        diff[:, 0::2] = dists[0]
        diff[:, 1::2] = dists[1]

        return diff

    # TODO: unit tests
    def compute_delta(
            self,
            content: int,
            old: np.ndarray,
            is_aux: bool
    ) -> np.ndarray:
        # TODO: use error edit distance

        diff = self._diff_weights(self.packed, is_aux, content)

        # TODO: try different weightings
        return (diff * 5) - old


class HGRBitmap(Bitmap):
    NAME = 'HGR'

    # hhhbbbbbbbpPBBBBBBBfff
    # 0000000011111111111111
    # 1111111111111100000000

    # Header:
    #    0000000010000011
    # Footer:
    #    1100000100000000

    BYTE_MASKS = [
        np.uint64(0b0000000011111111111111),
        np.uint64(0b1111111111111100000000)
    ]
    BYTE_SHIFTS = [np.uint64(0), np.uint64(8)]
    MASKED_BITS = np.uint64(14)  # 3 + 8 + 3

    HEADER_BITS = np.uint64(3)
    # 7-bits doubled, plus possible shift from palette bit
    BODY_BITS = np.uint64(15)
    FOOTER_BITS = np.uint64(3)

    PHASES = [1, 3]

    def __init__(self, palette: pal.Palette, main_memory: MemoryMap):
        super(HGRBitmap, self).__init__(palette, main_memory, None)

    @staticmethod
    def _make_header(col: IntOrArray) -> IntOrArray:
        # Header format is bits 5,6,0 of previous byte
        # i.e. offsets 16, 17, 11

        # return (col & np.uint64(0b111 << 16)) >> np.uint64(16)

        return (
                (col & np.uint64(0b1 << 11)) >> np.uint64(9) ^ (
                (col & np.uint64(0b11 << 17)) >> np.uint64(17))
        )

    def _body(self) -> np.ndarray:
        # Body is in order
        # a0 a1 a2 a3 a4 a5 a6 a7 b7 b0 b1 b2 b3 b4 b5 b6
        # so that a) the header and footer have the same order
        # across the two byte offsets, and b) so that they
        # can be extracted as contiguous bit ranges

        even = self.main_memory.page_offset[:, 0::2].astype(np.uint64)
        odd = self.main_memory.page_offset[:, 1::2].astype(np.uint64)

        return (
                (even << 3) + ((odd & 0x7f) << 12) + ((odd & 0x80) << 4)
        )

    @staticmethod
    def _make_footer(col: IntOrArray) -> IntOrArray:
        # Footer format is bits 7,0,1 of next byte
        # i.e. offsets 10,3,4

        return (
                       (col & np.uint64(0b1 << 10)) >> np.uint64(10) ^ (
                       (col & np.uint64(0b11 << 3)) >> np.uint64(2))
               ) << np.uint64(19)

    # # XXX move to make_data_tables
    # def _pack(self) -> None:
    #     """Pack main memory into (28+3)-bit uint64 array"""
    #
    #     # 00000000001111111111222222222233
    #     # 01234567890123456789012345678901
    #     # AAAABBBBCCCCDDd
    #     #  AAAABBBBCCCCDd
    #     #               DDEEEEFFFFGGGGg
    #     #               dDDEEEEFFFFGGGg
    #
    #     # Even, P0: store unshifted (0..14)
    #     # Even, P1: store shifted << 1 (1..15) (only need 1..14)
    #
    #     # Odd, P0: store shifted << 14 (14 .. 28) - set bit 14 as bit 0 of next
    #     #  byte
    #     # Odd, p1: store shifted << 15 (15 .. 29) (only need 15 .. 28) - set
    #     #  bit 13 as bit 0 of next byte
    #
    #     # Odd overflow only matters for even, P1
    #     # - bit 0 is either bit 14 if odd, P0 or bit 13 if odd, P1
    #     # - but these both come from the undoubled bit 6.
    #
    #     main = self.main_memory.page_offset.astype(np.uint64)
    #
    #     # Double 7-bit pixel data from a into 14-bit fat pixels, and extend MSB
    #     # into 15-bits tohandle case when subsequent byte has palette bit set,
    #     # i.e. is right-shifted by 1 dot.  This only matters for even bytes
    #     # with P=0 that are followed by odd bytes with P=1; in other cases
    #     # this extra bit will be overwritten.
    #     double = (
    #                  # Bit pos 6
    #                      ((main & 0x40) << 8) + ((main & 0x40) << 7) + (
    #                      (main & 0x40) << 6)) + (
    #                  # Bit pos 5
    #                      ((main & 0x20) << 6) + ((main & 0x20) << 5)) + (
    #                  # Bit pos 4
    #                      ((main & 0x10) << 5) + ((main & 0x10) << 4)) + (
    #                  # Bit pos 3
    #                      ((main & 0x08) << 4) + ((main & 0x08) << 3)) + (
    #                  # Bit pos 2
    #                      ((main & 0x04) << 3) + ((main & 0x04) << 2)) + (
    #                  # Bit pos 1
    #                      ((main & 0x02) << 2) + ((main & 0x02) << 1)) + (
    #                  # Bit pos 0
    #                      ((main & 0x01) << 1) + (main & 0x01))
    #
    #     a_even = main[:, ::2]
    #     a_odd = main[:, 1::2]
    #
    #     double_even = double[:, ::2]
    #     double_odd = double[:, 1::2]
    #
    #     # Place even offsets at bits 1..15 (P=1) or 0..14 (P=0)
    #     packed = np.where(a_even & 0x80, double_even << 1, double_even)
    #
    #     # Place off offsets at bits 15..27 (P=1) or 14..27 (P=0)
    #     packed = np.where(
    #         a_odd & 0x80,
    #         np.bitwise_xor(
    #             np.bitwise_and(packed, (2 ** 15 - 1)),
    #             double_odd << 15
    #         ),
    #         np.bitwise_xor(
    #             np.bitwise_and(packed, (2 ** 14 - 1)),
    #             double_odd << 14
    #         )
    #     )
    #
    #     # Patch up even offsets with P=1 with extended bit from previous odd
    #     # column
    #
    #     previous_odd = np.roll(a_odd, 1, axis=1).astype(np.uint64)
    #
    #     packed = np.where(
    #         a_even & 0x80,
    #         # Truncate to 28-bits and set bit 0 from bit 6 of previous byte
    #         np.bitwise_xor(
    #             np.bitwise_and(packed, (2 ** 28 - 2)),
    #             (previous_odd & (1 << 6)) >> 6
    #         ),
    #         # Truncate to 28-bits
    #         np.bitwise_and(packed, (2 ** 28 - 1))
    #     )
    #
    #     # Append first 3 bits of next even byte so we can correctly
    #     # decode the effective colours at the end of the 28-bit tuple
    #     trailing = np.roll(packed, -1, axis=1).astype(np.uint64)
    #
    #     packed = np.bitwise_xor(
    #         packed,
    #         (trailing & 0b111) << 28
    #     )
    #
    #     self.packed = packed

    @staticmethod
    @functools.lru_cache(None)
    def byte_offset(x_byte: int, is_aux: bool) -> int:
        """Returns 0..1 offset in packed representation for a given x_byte."""
        assert not is_aux

        is_odd = x_byte % 2 == 1

        return 1 if is_odd else 0

    @staticmethod
    @functools.lru_cache(None)
    def _byte_offsets(is_aux: bool) -> Tuple[int, int]:
        assert not is_aux
        return 0, 1

    @staticmethod
    @functools.lru_cache(None)
    def _double_pixels(int7: int) -> int:

        # Input bit 6 is repeated 3 times in case the neighbouring byte is
        # delayed (right-shifted by one dot) due to the palette bit being set.
        # Care needs to be taken to mask this out when overwriting.
        double = (
            # Bit pos 6
                ((int7 & 0x40) << 8) + ((int7 & 0x40) << 7) + (
                (int7 & 0x40) << 6) +
                # Bit pos 5
                ((int7 & 0x20) << 6) + ((int7 & 0x20) << 5) +
                # Bit pos 4
                ((int7 & 0x10) << 5) + ((int7 & 0x10) << 4) + (
                    # Bit pos 3
                        ((int7 & 0x08) << 4) + ((int7 & 0x08) << 3) +
                        # Bit pos 2
                        ((int7 & 0x04) << 3) + ((int7 & 0x04) << 2) +
                        # Bit pos 1
                        ((int7 & 0x02) << 2) + ((int7 & 0x02) << 1) +
                        # Bit pos 0
                        ((int7 & 0x01) << 1) + (int7 & 0x01))
        )

        return double

    @classmethod
    def to_dots(cls, masked_val: int, byte_offset: int) -> int:

        # Assert 14-bit representation
        assert (masked_val & (2 ** 14 - 1)) == masked_val

        # Unpack hhHaaaaaaaABbbbbbbbFff

        # --> hhhaaaaaaaaaaaaaabbbb (P=0, P=0, P=0)
        #     hhhaaaaaaaaaaaaaabbbb (P=1, P=0, P=0)
        #     hhhhaaaaaaaaaaaaabbbb (P=1, P=1, P=0)
        #     hhhhaaaaaaaaaaaaaabbb (P=1, P=1, P=1)

        # Take top 3 bits from header (plus duplicated MSB) not 4, because if it
        # is palette-shifted then we don't know what is in bit 0
        h = (masked_val & 0b111) << 5
        hp = (h & 0x80) >> 7
        res = cls._double_pixels(h & 0x7f) >> (11 - hp)

        if byte_offset == 0:
            # Offset 0: hhHaaaaaaaABbb
            b = (masked_val >> 3) & 0xff
            bp = (b & 0x80) >> 7
        else:
            # Offset 1: aaABbbbbbbbFff
            bp = (masked_val >> 3) & 0x01
            b = ((masked_val >> 4) & 0x7f) ^ (bp << 7)

        # Mask out current contents in case we are overwriting the extended
        # high bit from previous screen byte
        res &= ~((2 ** 14 - 1) << (3 + bp))
        res ^= cls._double_pixels(b & 0x7f) << (3 + bp)

        f = ((masked_val >> 12) & 0b11) ^ (
                (masked_val >> 11) & 0b01) << 7
        fp = (f & 0x80) >> 7

        # Mask out current contents in case we are overwriting the extended
        # high bit from previous screen byte
        res &= ~((2 ** 4 - 1) << (17 + fp))
        res ^= cls._double_pixels(f & 0x7f) << (17 + fp)
        return res & (2 ** 21 - 1)

    # XXX test
    @staticmethod
    def masked_update(
            byte_offset: int,
            old_value: IntOrArray,
            new_value: np.uint8) -> IntOrArray:
        """Update int/array to store new value at byte_offset in every entry.

        Does not patch up headers/footers of neighbouring columns.
        """

        if byte_offset == 0:
            # Mask out 8-bit value where update will go
            masked_value = old_value & (~np.uint64(0xff << 3))

            update = np.uint64(new_value) << np.uint64(3)
            return masked_value ^ update
        else:
            # Mask out 8-bit value where update will go
            masked_value = old_value & (~np.uint64(0xff << 11))

            # shift palette bit into position 0
            shifted_new_value = (
                                        (new_value & 0x7f) << 1) ^ (
                                        (new_value & 0x80) >> 7)
            update = np.uint64(shifted_new_value) << np.uint64(11)
            return masked_value ^ update


class DHGRBitmap(Bitmap):
    # NOTE: See https://github.com/numpy/numpy/issues/2524 and related issues
    # for why we have to cast things explicitly to np.uint64 - type promotion
    # to uint64 is broken in numpy :(

    NAME = 'DHGR'

    # 3-bit header + 28-bit body + 3-bit footer
    BYTE_MASKS = [
        #    3333333222222211111110000000    <- byte 0.3
        #
        #           3333222222222211111111110000000000 <- bit pos in uint64
        #           3210987654321098765432109876543210
        #           tttGGGGFFFFEEEEDDDDCCCCBBBBAAAAhhh <- pixel A..G
        #              3210321032103210321032103210    <- bit pos in A..G pixel
        np.uint64(0b0000000000000000000001111111111111),  # byte 0 int13 mask
        np.uint64(0b0000000000000011111111111110000000),  # byte 1 int13 mask
        np.uint64(0b0000000111111111111100000000000000),  # byte 2 int13 mask
        np.uint64(0b1111111111111000000000000000000000),  # byte 3 int13 mask
    ]

    # How much to right-shift bits after masking to bring into int13 range
    BYTE_SHIFTS = [np.uint64(0), np.uint64(7), np.uint64(14), np.uint64(21)]

    HEADER_BITS = np.uint64(3)
    BODY_BITS = np.uint64(28)
    FOOTER_BITS = np.uint64(3)

    MASKED_BITS = np.uint64(13)

    # NTSC clock phase at first masked bit
    # Each DHGR byte offset has the same range of int13 possible
    # values and nominal colour pixels, but with different initial
    # phases:
    # AUX 0: 0 (1 at start of 3-bit header)
    # MAIN 0: 3 (0)
    # AUX 1: 2 (3)
    # MAIN 1: 1 (2)
    PHASES = [1, 0, 3, 2]

    def _body(self) -> np.ndarray:
        # Palette bit is unused for DHGR so mask it out
        aux = (self.aux_memory.page_offset & 0x7f).astype(np.uint64)
        main = (self.main_memory.page_offset & 0x7f).astype(np.uint64)

        # XXX update
        # Interleave aux and main memory columns and pack 7-bit masked values
        # into a 28-bit value, with 3-bit header and footer.  This
        # sequentially encodes 7 4-bit DHGR pixels, together with the
        # neighbouring 3 bits that are necessary to decode artifact colours.
        #
        # See make_data_tables.py for more discussion about this representation.

        return (
                (aux[:, 0::2] << 3) +
                (main[:, 0::2] << 10) +
                (aux[:, 1::2] << 17) +
                (main[:, 1::2] << 24)
        )

    @staticmethod
    def _make_header(col: IntOrArray) -> IntOrArray:
        """Extract upper 3 bits of body for header of next column."""
        return (col & np.uint64(0b111 << 28)) >> np.uint64(28)

    @staticmethod
    def _make_footer(col: IntOrArray) -> IntOrArray:
        """Extract lower 3 bits of body for footer of previous column."""
        return (col & np.uint64(0b111 << 3)) << np.uint64(28)

    @staticmethod
    @functools.lru_cache(None)
    def byte_offset(x_byte: int, is_aux: bool) -> int:
        """Returns 0..3 packed byte offset for a given x_byte and is_aux"""
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
    @functools.lru_cache(None)
    def _byte_offsets(is_aux: bool) -> Tuple[int, int]:
        if is_aux:
            offsets = (0, 2)
        else:
            offsets = (1, 3)

        return offsets

    @classmethod
    def to_dots(cls, masked_val: int, byte_offset: int) -> int:
        # For DHGR the 13-bit masked value is already a 13-bit dot sequence
        # so no need to transform it.

        return masked_val

    @staticmethod
    def masked_update(
            byte_offset: int,
            old_value: IntOrArray,
            new_value: np.uint8) -> IntOrArray:
        """Update int/array to store new value at byte_offset in every entry.

        Does not patch up headers/footers of neighbouring columns.
        """

        # Mask out 7-bit value where update will go
        masked_value = old_value & (
            ~np.uint64(0x7f << (7 * byte_offset + 3)))

        update = (new_value & np.uint64(0x7f)) << np.uint64(
            7 * byte_offset + 3)
        return masked_value ^ update
