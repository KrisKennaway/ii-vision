"""Screen module represents Apple II video display."""

from collections import defaultdict, Counter
import enum
import functools
from typing import Dict, Set, Iterator, Union, Tuple

import numpy as np


def hamming_weight(n: int) -> int:
    """Compute hamming weight of 8-bit int"""
    n = (n & 0x55) + ((n & 0xAA) >> 1)
    n = (n & 0x33) + ((n & 0xCC) >> 2)
    n = (n & 0x0F) + ((n & 0xF0) >> 4)
    return n


def y_to_base_addr(y: int, page: int = 0) -> int:
    """Maps y coordinate to base address on given screen page"""
    a = y // 64
    d = y - 64 * a
    b = d // 8
    c = d - 8 * b

    addr = 8192 * (page + 1) + 1024 * c + 128 * b + 40 * a
    return addr


# TODO: fill out other byte opcodes
class Opcode(enum.Enum):
    SET_CONTENT = 0xfc  # set new data byte to write
    SET_PAGE = 0xfd
    TICK = 0xfe  # tick speaker
    END_FRAME = 0xff


class Frame:
    """Bitmapped screen frame."""

    XMAX = 140  # double-wide pixels to not worry about colour effects
    YMAX = 192

    def __init__(self, bitmap: np.array = None):
        if bitmap is None:
            self.bitmap = np.zeros((self.YMAX, self.XMAX), dtype=bool)
        else:
            self.bitmap = bitmap

    def randomize(self):
        self.bitmap = np.random.randint(
            2, size=(self.YMAX, self.XMAX), dtype=bool)


class Screen:
    """Apple II screen memory map encoding a bitmapped frame."""

    Y_TO_BASE_ADDR = [
        [y_to_base_addr(y, page) for y in range(192)] for page in (0, 1)
    ]

    ADDR_TO_COORDS = {}
    for p in range(2):
        for y in range(192):
            for x in range(40):
                a = Y_TO_BASE_ADDR[p][y] + x
                ADDR_TO_COORDS[a] = (p, y, x)

    CYCLES = defaultdict(lambda: 35)  # fast-path cycle count
    CYCLES.update({
        Opcode.SET_CONTENT: 62,
        Opcode.SET_PAGE: 69,
        Opcode.TICK: 50,
        Opcode.END_FRAME: 50
    })

    def __init__(self, page: int = 0):
        self.screen = self._encode(Frame().bitmap)  # initialize empty
        self.page = page
        self.cycles = 0

    @staticmethod
    def _encode(bitmap: np.array) -> np.array:
        """Encode bitmapped screen as apple II memory map.

        Rows are y-coordinates, Columns are byte-packed x-values
        """

        # Double each pixel horizontally
        pixels = np.repeat(bitmap, 2, axis=1)

        # Insert zero column after every 7
        for i in range(pixels.shape[1] // 7 - 1, -1, -1):
            pixels = np.insert(pixels, (i + 1) * 7, False, axis=1)

        # packbits is big-endian so we flip the array before and after to
        # invert this
        return np.flip(np.packbits(np.flip(pixels, axis=1), axis=1), axis=1)

    def update(self, frame: Frame, cycle_budget: int) -> Iterator[int]:
        """Update to match content of frame within provided budget."""

        self.cycles = 0
        # Target screen memory map for new frame
        target = self._encode(frame.bitmap)

        # Compute difference from current frame
        delta = np.bitwise_xor(self.screen, target)
        delta = np.ma.masked_array(delta, np.logical_not(delta))

        for b in self.encoded_byte_stream(delta, target):
            yield b
            if (self.cycles >= cycle_budget and
                    not any(o.value == b for o in Opcode)):
                return

    def index_by_bytes(self, deltas: np.array,
                       memmap: np.array) -> Set[Tuple[int, int, int, int]]:
        """Transform encoded screen to map of byte --> addr.

        XXX
        """

        changes = set()
        it = np.nditer(memmap, flags=['multi_index'])
        while not it.finished:
            y, x_byte = it.multi_index

            # Skip masked values, i.e. unchanged in new frame
            xor = deltas[y][x_byte]
            if xor is np.ma.masked:
                it.iternext()
                continue

            y_base = self.Y_TO_BASE_ADDR[self.page][y]
            page = y_base >> 8

            #print("y=%d -> page=%02x" % (y, page))
            xor_weight = hamming_weight(xor)

            changes.add(
                (
                    page, y_base - (page << 8) + x_byte,
                    np.asscalar(it[0]), xor_weight
                )
            )
            it.iternext()

        return changes

    def _emit(self, opcode: Union[Opcode, int]) -> int:
        self.cycles += self.CYCLES[opcode]
        return opcode.value if opcode in Opcode else opcode

    @functools.lru_cache(None)
    def _score(self, diff_page: bool,
               diff_content: bool,
               xor_weight: int) -> float:
        """Computes score of how many pixels/cycle it would cost to emit"""
        cycles = 0
        if diff_page:
            cycles += self.CYCLES[Opcode.SET_PAGE]
        if diff_content:
            cycles += self.CYCLES[Opcode.SET_CONTENT]

        # Placeholder content since all content bytes have same cost
        cycles += self.CYCLES[0]

        cycles_per_pixel = cycles / xor_weight
        return cycles_per_pixel

    def encoded_byte_stream(self, deltas: np.array,
                            target: np.array) -> Iterator[int]:
        """Emit encoded byte stream for rendering the image.

        The byte stream consists of offsets against a selected page (e.g. $20xx)
        at which to write a selected content byte.  Those selections are
        controlled by special opcodes emitted to the stream

        Opcodes:
          SET_CONTENT - new byte to write to screen contents
          SET_PAGE - set new page to offset against (e.g. $20xx)
          TICK - tick the speaker
          DONE - terminate the video decoding

        In order to "make room" for these opcodes we make use of the fact that
        each page has 2 sets of 8-byte "screen holes", at page offsets
        0x78-0x7f and 0xf8-0xff.  Currently we only use the latter range as
        this allows for efficient matching in the critical path of the decoder.

        We group by offsets from page boundary (cf some other more
        optimal starting point) because STA (..),y has 1 extra cycle if
        crossing the page boundary.  Though maybe this would be worthwhile if
        it optimizes the bytestream.
        """

        # Construct map of byte to addr that contain it
        changes = self.index_by_bytes(deltas, target)

        ctr = Counter()
        page = 0x20
        content = 0x7f

        scores = []
        while changes:
            if not scores:
                scores = sorted((
                    (
                        self._score(page != ch[0], content != ch[2], ch[3]),
                        ctr,
                        ch
                    ) for ch in changes))

            best = scores.pop()
            best_change = best[2]
            changes.remove(best_change)
            #print(best_change)

            (new_page, offset, new_content, xor_weight) = best_change
            #print("Score=%f" % best[0])

            if new_page != page:
                #print("changing page %02x -> %02x" % (page, new_page))
                page = new_page
                yield self._emit(Opcode.SET_PAGE)
                yield page

                # Invalidate scores
                # TODO: we don't need to invalidate all of them, just those
                #  for the current page
                scores = []

            if new_content != content:
                content = new_content
                yield self._emit(Opcode.SET_CONTENT)
                yield content

                # Invalidate scores
                # TODO: we don't need to invalidate all of them, just those
                #  for the current page
                scores = []

            self._write(page << 8 | offset, content)
            yield self._emit(offset)

    def done(self) -> Iterator[int]:
        """Terminate opcode stream."""

        yield self._emit(Opcode.END_FRAME)

    def _write(self, addr: int, val: int) -> None:
        """Updates screen image to set 0xaddr ^= val"""
        _, y, x = self.ADDR_TO_COORDS[addr]
        self.screen[y][x] = val

    def to_bitmap(self) -> np.array:
        """Convert packed screen representation to bitmap."""
        bm = np.unpackbits(self.screen, axis=1)
        bm = np.delete(bm, np.arange(0, bm.shape[1], 8), axis=1)

        # Need to flip each 7-bit sequence
        reorder_cols = []
        for i in range(bm.shape[1] // 7):
            for j in range((i + 1) * 7 - 1, i * 7 - 1, -1):
                reorder_cols.append(j)
        bm = bm[:, reorder_cols]

        # Undouble pixels
        return np.array(np.delete(bm, np.arange(0, bm.shape[1], 2), axis=1),
                        dtype=np.bool)

    def from_stream(self, stream: Iterator[int]) -> None:
        """Replay an opcode stream to build a screen image."""
        page = 0x20
        content = 0x7f
        for b in stream:
            if b == Opcode.SET_CONTENT.value:
                content = next(stream)
                continue
            elif b == Opcode.SET_PAGE.value:
                page = next(stream)
                continue
            elif b == Opcode.TICK.value:
                continue
            elif b == Opcode.END_FRAME.value:
                return

            self._write(page << 8 | b, content)
