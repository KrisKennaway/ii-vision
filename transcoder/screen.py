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
    """Maps y coordinate to base address on given screen page."""
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
    """Packed bitmap representation of (D)HGR screen memory.

    Maintains a page-based array whose entries contain a packed representation
    of multiple screen bytes, in a representation that supports efficiently
    determining the visual effect of storing bytes at arbitrary screen offsets.
    """

    # NOTE: See https://github.com/numpy/numpy/issues/2524 and related issues
    # for why we have to cast things explicitly to np.uint64 - type promotion
    # to uint64 is broken in numpy :(

    # Name of bitmap type
    NAME = None  # type: str

    # Size of packed representation, consisting of header + body + footer
    HEADER_BITS = None  # type: np.uint64
    BODY_BITS = None  # type: np.uint64
    FOOTER_BITS = None  # type: np.uint64

    # How many bits of packed representation are necessary to determine the
    # effect of storing a memory byte, e.g. because they influence pixel
    # colour or are influenced by other bits.
    MASKED_BITS = None  # type: np.uint64

    # How many coloured screen pixels we can extract from MASKED_BITS.  Note
    # that this does not include the last 3 dots represented by the footer,
    # since we don't have enough information to determine their colour (we
    # would fall off the end of the 4-bit sliding window)
    MASKED_DOTS = None  # type: np.uint64

    # List of bitmasks for extracting the subset of packed data corresponding
    # to bits influencing/influenced by a given byte offset.  These must be
    # a contiguous bit mask, i.e. so that after shifting they are enumerated
    # by 0..2**MASKED_BITS-1
    BYTE_MASKS = None  # type: List[np.uint64]
    BYTE_SHIFTS = None  # type: List[np.uint64]

    # NTSC clock phase at first masked bit
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

    # TODO: don't leak headers/footers across screen rows.  We should be using
    # x-y representation rather than page-offset

    @staticmethod
    def _make_header(col: IntOrArray) -> IntOrArray:
        """Extract values to use as header of next column."""
        raise NotImplementedError

    def _body(self) -> np.ndarray:
        """Pack related screen bytes into an efficient representation."""
        raise NotImplementedError

    @staticmethod
    def _make_footer(col: IntOrArray) -> IntOrArray:
        """Extract values to use as footer of previous column."""
        raise NotImplementedError

    def _pack(self) -> None:
        """Pack MemoryMap into efficient representation for diffing."""

        body = self._body()

        # Prepend last 3 bits of previous odd byte so we can correctly
        # decode the effective colours at the beginning of the body tuple
        prev_col = np.roll(body, 1, axis=1).astype(np.uint64)
        header = self._make_header(prev_col)
        # Don't leak header across page boundaries
        header[:, 0] = 0

        # Append first 3 bits of next even byte so we can correctly
        # decode the effective colours at the end of the body tuple
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
        """Update int/array to store new value at byte_offset in every entry.

        Does not patch up headers/footers of neighbouring columns.
        """
        raise NotImplementedError

    @staticmethod
    @functools.lru_cache(None)
    def byte_offset(page_offset: int, is_aux: bool) -> int:
        """Map screen offset for aux/main into offset within packed data."""
        raise NotImplementedError

    @staticmethod
    @functools.lru_cache(None)
    def _byte_offsets(is_aux: bool) -> Tuple[int, int]:
        """Return byte offsets within packed data for AUX/MAIN memory."""
        raise NotImplementedError

    @classmethod
    def to_dots(cls, masked_val: int, byte_offset: int) -> int:
        """Convert masked representation to bit sequence of display dots."""
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
        """Fix up column headers/footers when updating a (page, offset)."""

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
        """Patch up the footer of the column to the left."""

        # Mask out footer(s)
        column_left &= np.uint64(2 ** (self.HEADER_BITS + self.BODY_BITS) - 1)
        column_left ^= self._make_footer(column)

        return column_left

    def _fix_column_right(
            self,
            column_right: IntOrArray,
            column: IntOrArray
    ) -> IntOrArray:
        """Patch up the header of the column to the right."""

        # Mask out header(s)
        column_right &= np.uint64(
            (2 ** (self.BODY_BITS + self.FOOTER_BITS) - 1)) << self.HEADER_BITS
        column_right ^= self._make_header(column)

        return column_right

    # def _fix_array_neighbours(
    #         self,
    #         ary: np.ndarray,
    #         byte_offset: int
    # ) -> None:
    #     """Fix up column headers/footers for all array entries."""
    #
    #     # TODO: don't leak header/footer across page boundaries
    #
    #     # Propagate new value into neighbouring byte headers/footers if
    #     # necessary
    #     if byte_offset == 0:
    #         # Need to also update the footer of the preceding column
    #         shifted_left = np.roll(ary, -1, axis=1)
    #         self._fix_column_left(ary, shifted_left)
    #
    #     elif byte_offset == (self.SCREEN_BYTES - 1):
    #         # Need to also update the header of the next column
    #         shifted_right = np.roll(ary, 1, axis=1)
    #         self._fix_column_right(ary, shifted_right)

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
        """Masks and shifts packed data into the MASKED_BITS range."""
        res = (data & cls.BYTE_MASKS[byte_offset]) >> (
            cls.BYTE_SHIFTS[byte_offset])
        assert np.all(res <= 2 ** cls.MASKED_BITS)
        return res

    # Can't cache all possible values but this seems to give a good enough hit
    # rate without costing too much memory
    # TODO: unit tests
    @functools.lru_cache(10 ** 6)
    def byte_pair_difference(
            self,
            byte_offset: int,
            old_packed: np.uint64,
            content: np.uint8
    ) -> np.uint16:
        """Compute effect of storing a new content byte within packed data."""

        old_pixels = self.mask_and_shift_data(old_packed, byte_offset)
        new_pixels = self.mask_and_shift_data(
            self.masked_update(byte_offset, old_packed, content), byte_offset)

        pair = (old_pixels << self.MASKED_BITS) + new_pixels

        return self.edit_distances(self.palette)[byte_offset][pair]

    def diff_weights(
            self,
            source: "Bitmap",
            is_aux: bool
    ) -> np.ndarray:
        """Compute edit distance matrix from source bitmap."""

        diff = np.ndarray((32, 256), dtype=np.int)
        offsets = self._byte_offsets(is_aux)

        dists = []
        for o in offsets:
            # Pixels influenced by byte offset o
            source_pixels = self.mask_and_shift_data(source.packed, o)
            target_pixels = self.mask_and_shift_data(self.packed, o)

            # Concatenate N-bit source and target into 2N-bit values
            pair = (source_pixels << self.MASKED_BITS) + target_pixels
            dist = self.edit_distances(self.palette)[o][pair].reshape(
                pair.shape)
            dists.append(dist)

        # Interleave even/odd columns
        diff[:, 0::2] = dists[0]
        diff[:, 1::2] = dists[1]

        return diff

    def _check_consistency(self):
        """Sanity check that headers and footers are consistent."""

        headers = np.roll(self._make_header(self.packed), 1, axis=1).astype(
            np.uint64)

        footers = np.roll(self._make_footer(self.packed), -1, axis=1).astype(
            np.uint64)

        mask_hf = np.uint64(0b1110000000000000000000000000000111)

        res = (self.packed ^ headers ^ footers) & mask_hf
        nz = np.transpose(np.nonzero(res))

        ok = True
        if nz.size != 0:
            for p, o in nz.tolist():
                if o == 0 or o == 127:
                    continue
                ok = False
                print(p, o, bin(self.packed[p, o - 1]),
                      bin(headers[p, o]),
                      bin(self.packed[p, o]),
                      bin(self.packed[p, o + 1]), bin(footers[p, o]),
                      bin(res[p, o])
                      )
            assert ok

    CONTENT_RANGE = None

    # TODO: unit tests
    def compute_delta(self, is_aux: bool) -> np.ndarray:
        """Compute which content stores introduce the least additional error.

        We compute the effect of storing content at all possible offsets
        within self.packed, in terms of the new edit_distance to the target
        pixels.
        """
        # Only need to consider 0x0 .. 0x7f content stores
        diff = np.ndarray((self.CONTENT_RANGE, 32, 256), dtype=np.int)

        all_content_bytes = np.arange(
            self.CONTENT_RANGE, dtype=np.uint64).reshape(
            (self.CONTENT_RANGE, 1))

        def _target_masked(content, t, byte_offset):
            return self.masked_update(byte_offset, t, content)

        offsets = self._byte_offsets(is_aux)

        dists = []
        for o in offsets:
            compare_packed = np.apply_along_axis(
                _target_masked, 1, all_content_bytes, self.packed, o)
            # self.masked_update(o, self.packed, content)
            # self._fix_array_neighbours(compare_packed, o)

            # Pixels influenced by byte offset 0
            source_pixels = self.mask_and_shift_data(compare_packed, o)
            target_pixels = self.mask_and_shift_data(self.packed, o)

            # Concatenate N-bit source and target into 2N-bit values
            pair = (source_pixels << self.MASKED_BITS) + target_pixels
            dist = self.edit_distances(self.palette)[o][pair].reshape(
                pair.shape)
            dists.append(dist)

        # Interleave even/odd columns
        diff[:, :, 0::2] = dists[0]
        diff[:, :, 1::2] = dists[1]

        return diff


class HGRBitmap(Bitmap):
    """Packed bitmap representation of HGR screen memory.

    The HGR display is encoded in a somewhat complicated way, so we have to
    do a bit of work to turn it into a useful format.

    Each screen byte consists of a palette bit (7) and 6 data bits (0..6)

    Each non-palette bit turns on two consecutive display dots, with bit 6
    repeated a third time.  This third dot may or may not be overwritten by the
    effect of the next byte.

    Turning on the palette bit shifts that byte's dots right by one
    position.

    Given two neighbouring screen bytes Aaaaaaaa, Bbbbbbbb (at even and odd
    offsets), where capital letter indicates the position of the palette bit,
    we use the following 22-bit packed representation:

        2211111111110000000000  <-- bit position in uint22
        1098765432109876543210
        ffFbbbbbbbBAaaaaaaaHhh

    h and f are headers/footers derived from the neighbouring screen bytes.

    Since our colour artifact model (see colours.py) uses a sliding 4-bit window
    onto the dot string, we need to also include a 3-bit header and footer
    to account for the influence from/on neighbouring bytes, i.e. adjacent
    packed values.  These are just the low/high 2 data bits of the 16-bit
    body of those neighbouring columns, plus the corresponding palette bit.

    This 22-bit packed representation is sufficient to compute the effects
    (on pixel colours) of storing a byte at even or odd offsets.  From it we
    can extract the bit stream of displayed HGR dots, and the mapping to pixel
    colours follows the HGRColours bitmap, see colours.py.

    We put the two A/B palette bits next to each other so that we can
    mask a contiguous range of bits whose colours influence/are influenced by
    storing a byte at a given offset.

    We need to mask out bit subsequences of size 3+8+3=14, i.e. the 8-bits
    corresponding to the byte being stored, plus the neighbouring 3 bits that
    influence it/are influenced by it.

    Note that the masked representation has the same size for both offsets (
    14 bits), but different meaning, since the palette bit is in a different
    position.

    With this masked representation, we can precompute an edit distance for the
    pixel changes resulting from all possible HGR byte stores, see
    make_edit_distance.py.

    The edit distance matrix is encoded by concatenating the 14-bit source
    and target masked values into a 28-bit pair, which indexes into the
    edit_distance array to give the corresponding edit distance.
    """
    NAME = 'HGR'

    # Size of packed representation, consisting of header + body + footer
    HEADER_BITS = np.uint64(3)
    # 2x 8-bit screen bytes
    BODY_BITS = np.uint64(16)
    FOOTER_BITS = np.uint64(3)

    # How many bits of packed representation are necessary to determine the
    # effect of storing a memory byte, e.g. because they influence pixel
    # colour or are influenced by other bits.
    MASKED_BITS = np.uint64(14)  # 3 + 8 + 3

    # How many coloured screen pixels we can extract from MASKED_BITS.  Note
    # that this does not include the last 3 dots represented by the footer,
    # since we don't have enough information to determine their colour (we
    # would fall off the end of the 4-bit sliding window)
    #
    # From header: 3 bits (2 HGR pixels but might be shifted right by palette)
    # From body: 7 bits doubled, plus possible shift from palette bit
    MASKED_DOTS = np.uint64(18)  # 3 + 7 + 7 + 1

    # List of bitmasks for extracting the subset of packed data corresponding
    # to bits influencing/influenced by a given byte offset.  These must be
    # a contiguous bit mask, i.e. so that after shifting they are enumerated
    # by 0..2**MASKED_BITS-1
    BYTE_MASKS = [
        np.uint64(0b0000000011111111111111),
        np.uint64(0b1111111111111100000000)
    ]
    BYTE_SHIFTS = [np.uint64(0), np.uint64(8)]

    # NTSC clock phase at first masked bit
    #
    # Each HGR byte offset has the same range of uint14 possible
    # values and nominal colour pixels, but with different initial
    # phases:
    #   even: 0 (1 at start of 3-bit header)
    #   odd:  2 (3)
    PHASES = [1, 3]

    # Need to consider all 0x0 .. 0xff content stores
    CONTENT_RANGE = 256

    def __init__(self, palette: pal.Palette, main_memory: MemoryMap):
        super(HGRBitmap, self).__init__(palette, main_memory, None)

    @staticmethod
    def _make_header(col: IntOrArray) -> IntOrArray:
        """Extract values to use as header of next column.

        Header format is bits 5,6,0 of previous screen byte
        i.e. offsets 17, 18, 11 in packed representation
        """

        return (
                (col & np.uint64(0b1 << 11)) >> np.uint64(9) ^ (
                (col & np.uint64(0b11 << 17)) >> np.uint64(17))
        )

    def _body(self) -> np.ndarray:
        """Pack related screen bytes into an efficient representation.

        Body is of the form:
            bbbbbbbBAaaaaaaa

        where capital indicates the palette bit.
        """

        even = self.main_memory.page_offset[:, 0::2].astype(np.uint64)
        odd = self.main_memory.page_offset[:, 1::2].astype(np.uint64)

        return (
                (even << 3) + ((odd & 0x7f) << 12) + ((odd & 0x80) << 4)
        )

    @staticmethod
    def _make_footer(col: IntOrArray) -> IntOrArray:
        """Extract values to use as footer of previous column.

        Footer format is bits 7,0,1 of next screen byte
        i.e. offsets 10,3,4 in packed representation
        """

        return (
                       (col & np.uint64(0b1 << 10)) >> np.uint64(10) ^ (
                       (col & np.uint64(0b11 << 3)) >> np.uint64(2))
               ) << np.uint64(19)

    @staticmethod
    @functools.lru_cache(None)
    def byte_offset(page_offset: int, is_aux: bool) -> int:
        """Returns 0..1 offset in packed representation for page_offset."""

        assert not is_aux
        is_odd = page_offset % 2 == 1

        return 1 if is_odd else 0

    @staticmethod
    @functools.lru_cache(None)
    def _byte_offsets(is_aux: bool) -> Tuple[int, int]:
        """Return byte offsets within packed data for AUX/MAIN memory."""

        assert not is_aux
        return 0, 1

    @staticmethod
    @functools.lru_cache(None)
    def _double_pixels(int7: int) -> int:
        """Each bit 0..6 controls two hires dots.

        Input bit 6 is repeated 3 times in case the neighbouring byte is
        delayed (right-shifted by one dot) due to the palette bit being set,
        which means the effect of this byte is "extended" by an extra dot.

        Care needs to be taken to mask this out when overwriting.
        """
        double = (
            # Bit pos 6
                ((int7 & 0x40) << 8) + ((int7 & 0x40) << 7) + (
                (int7 & 0x40) << 6) +
                # Bit pos 5
                ((int7 & 0x20) << 6) + ((int7 & 0x20) << 5) +
                # Bit pos 4
                ((int7 & 0x10) << 5) + ((int7 & 0x10) << 4) +
                # Bit pos 3
                ((int7 & 0x08) << 4) + ((int7 & 0x08) << 3) +
                # Bit pos 2
                ((int7 & 0x04) << 3) + ((int7 & 0x04) << 2) +
                # Bit pos 1
                ((int7 & 0x02) << 2) + ((int7 & 0x02) << 1) +
                # Bit pos 0
                ((int7 & 0x01) << 1) + (int7 & 0x01)
        )

        return double

    @classmethod
    def to_dots(cls, masked_val: int, byte_offset: int) -> int:
        """Convert masked representation to bit sequence of display dots.

        Packed representation is of the form:
            ffFbbbbbbbBAaaaaaaaHhh

        where capital indicates the palette bit.

        Each non-palette bit turns on two display dots, with bit 6 repeated
        a third time.  This may or may not be overwritten by the next byte.

        Turning on the palette bit shifts that byte's dots right by one
        position.
        """

        # Assert 14-bit representation
        assert (masked_val & (2 ** 14 - 1)) == masked_val

        # Take top 3 bits from header (plus duplicated MSB) not 4, because if it
        # is palette-shifted then we don't know what is in bit 0
        h = (masked_val & 0b111) << 5
        hp = (h & 0x80) >> 7
        res = cls._double_pixels(h & 0x7f) >> (11 - hp)

        if byte_offset == 0:
            # Offset 0: bbBAaaaaaaaHhh
            b = (masked_val >> 3) & 0xff
            bp = (b & 0x80) >> 7
        else:
            # Offset 1: ffFbbbbbbbBAaa
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
    """Packed bitmap representation of DHGR screen memory.

    The DHGR display encodes 7 pixels across interleaved 4-byte sequences
    of AUX and MAIN memory, as follows:

        PBBBAAAA PDDCCCCB PFEEEEDD PGGGGFFF
        Aux N    Main N   Aux N+1  Main N+1  (N even)

    Where A..G are the pixels, and P represents the (unused) palette bit.

    This layout makes more sense when written as a (little-endian) 32-bit
    integer:

        33222222222211111111110000000000 <- bit pos in uint32
        10987654321098765432109876543210
        PGGGGFFFPFEEEEDDPDDCCCCBPBBBAAAA

    i.e. apart from the palette bits this is a linear ordering of pixels,
    when read from LSB to MSB (i.e. right-to-left).  i.e. the screen layout
    order of bits is opposite to the usual binary representation ordering.

    We can simplify things by stripping out the palette bit and packing
    down to a 28-bit integer representation:

        33222222222211111111110000000000 <- bit pos in uint32
        10987654321098765432109876543210

            GGGGFFFFEEEEDDDDCCCCBBBBAAAA <- pixel A..G
            3210321032103210321032103210 <- bit pos in A..G pixel

            3333333222222211111110000000 <- byte offset 0.3

    Since our colour artifact model (see colours.py) uses a sliding 4-bit window
    onto the dot string, we need to also include a 3-bit header and footer
    to account for the influence from/on neighbouring bytes, i.e. adjacent
    packed values.  These are just the low/high 3 bits of the 28-bit body of
    those neighbouring columns.

    This gives a 34-bit packed representation that is sufficient to compute
    the effects (on pixel colours) of storing a byte at one of the 0..3 offsets.

    Note that this representation is also 1:1 with the actual displayed
    DHGR dots.  The mapping to pixel colours follows the DHGRColours
    bitmap, see colours.py.

    Because the packed representation is contiguous, we need to mask out bit
    subsequences of size 3+7+3=13, i.e. the 7-bits corresponding to the
    byte being stored, plus the neighbouring 3 bits that influence it/are
    influenced by it.

    With this masked representation, we can precompute an edit distance for the
    pixel changes resulting from all possible DHGR byte stores, see
    make_edit_distance.py.

    The edit distance matrix is encoded by concatenating the 13-bit source
    and target masked values into a 26-bit pair, which indexes into the
    edit_distance array to give the corresponding edit distance.
    """

    NAME = 'DHGR'

    # Packed representation is 3 + 28 + 3 = 34 bits
    HEADER_BITS = np.uint64(3)
    BODY_BITS = np.uint64(28)
    FOOTER_BITS = np.uint64(3)

    # Masked representation selecting the influence of each byte offset
    MASKED_BITS = np.uint64(13)  # 7-bit body + 3-bit header + 3-bit footer

    # Masking is 1:1 with screen dots, but we can't compute the colour of the
    # last 3 dots because we fall off the end of the 4-bit sliding window
    MASKED_DOTS = np.uint64(10)

    # 3-bit header + 28-bit body + 3-bit footer
    BYTE_MASKS = [
        #           3333222222222211111111110000000000 <- bit pos in uint64
        #           3210987654321098765432109876543210
        #           tttGGGGFFFFEEEEDDDDCCCCBBBBAAAAhhh <- pixel A..G
        #              3210321032103210321032103210    <- bit pos in A..G pixel
        #
        #              3333333222222211111110000000    <- byte offset 0.3
        np.uint64(0b0000000000000000000001111111111111),  # byte 0 uint13 mask
        np.uint64(0b0000000000000011111111111110000000),  # byte 1 uint13 mask
        np.uint64(0b0000000111111111111100000000000000),  # byte 2 uint13 mask
        np.uint64(0b1111111111111000000000000000000000),  # byte 3 uint13 mask
    ]             #      XXX            XXX

    # How much to right-shift bits after masking, to bring into uint13 range
    BYTE_SHIFTS = [np.uint64(0), np.uint64(7), np.uint64(14), np.uint64(21)]

    # NTSC clock phase at first masked bit
    #
    # Each DHGR byte offset has the same range of uint13 possible
    # values and nominal colour pixels, but with different initial
    # phases:
    # AUX 0: 0 (1 at start of 3-bit header)
    # MAIN 0: 3 (0)
    # AUX 1: 2 (3)
    # MAIN 1: 1 (2)
    PHASES = [1, 0, 3, 2]

    # Only need to consider 0x0 .. 0x7f content stores
    CONTENT_RANGE = 128

    @staticmethod
    def _make_header(col: IntOrArray) -> IntOrArray:
        """Extract upper 3 bits of body for header of next column."""
        return (col & np.uint64(0b111 << 28)) >> np.uint64(28)

    def _body(self) -> np.ndarray:
        """Pack related screen bytes into an efficient representation.

        For DHGR we first strip off the (unused) palette bit to produce
        7-bit values, then interleave aux and main memory columns and pack
        these 7-bit values into 28-bits.  This sequentially encodes 7 4-bit
        DHGR pixels, which is the "repeating unit" of the DHGR screen, and
        in a form that is convenient to operate on.

        We also shift to make room for the 3-bit header.
        """

        # Palette bit is unused for DHGR so mask it out
        aux = (self.aux_memory.page_offset & 0x7f).astype(np.uint64)
        main = (self.main_memory.page_offset & 0x7f).astype(np.uint64)

        return (
                (aux[:, 0::2] << 3) +
                (main[:, 0::2] << 10) +
                (aux[:, 1::2] << 17) +
                (main[:, 1::2] << 24)
        )

    @staticmethod
    def _make_footer(col: IntOrArray) -> IntOrArray:
        """Extract lower 3 bits of body for footer of previous column."""
        return (col & np.uint64(0b111 << 3)) << np.uint64(28)

    @staticmethod
    @functools.lru_cache(None)
    def byte_offset(page_offset: int, is_aux: bool) -> int:
        """Returns 0..3 packed byte offset for a given page_offset and is_aux"""

        is_odd = page_offset % 2 == 1
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
        """Return byte offsets within packed data for AUX/MAIN memory."""

        if is_aux:
            offsets = (0, 2)
        else:
            offsets = (1, 3)

        return offsets

    @classmethod
    def to_dots(cls, masked_val: int, byte_offset: int) -> int:
        """Convert masked representation to bit sequence of display dots.

        For DHGR the 13-bit masked value is already a 13-bit dot sequence
        so no need to transform it.
        """

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
