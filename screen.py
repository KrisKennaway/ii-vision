"""Screen module represents Apple II video display."""

from collections import defaultdict
import functools
import enum
from typing import Set, Iterator, Union, Tuple

from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2

import numpy as np


@functools.lru_cache(None)
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

    def update(self, frame: Frame,
               cycle_budget: int, fullness: float) -> Iterator[int]:
        """Update to match content of frame within provided budget.

        Emits encoded byte stream for rendering the image.

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

        self.cycles = 0
        # Target screen memory map for new frame
        target = self._encode(frame.bitmap)

        # Compute difference from current frame
        delta = np.bitwise_xor(self.screen, target)
        delta = np.ma.masked_array(delta, np.logical_not(delta))

        # Estimate number of opcodes that will end up fitting in the cycle
        # budget.
        est_opcodes = int(cycle_budget / fullness / self.CYCLES[0])

        # Sort by highest xor weight and take the estimated number of change
        # operations
        changes = list(
            sorted(self.index_changes(delta, target), reverse=True)
        )[:est_opcodes]

        for b in self._heuristic_opcode_scheduler(changes):
            yield b

    def _tsp_opcode_scheduler(self, changes):
        # Build distance matrix for pairs of changes based on number of
        # opcodes it would cost for opcodes to emit target change given source

        dist = np.zeros(shape=(len(changes), len(changes)), dtype=np.int)
        for i1, ch1 in enumerate(changes):
            _, page1, _, content1 = ch1
            for i2, ch2 in enumerate(changes):
                if ch1 == ch2:
                    continue
                _, page2, _, content2 = ch2

                cost = self.CYCLES[0]  # Emit the target content byte
                if page1 != page2:
                    cost += self.CYCLES[Opcode.SET_PAGE]
                if content1 != content2:
                    cost += self.CYCLES[Opcode.SET_CONTENT]

                dist[i1][i2] = cost
                dist[i2][i1] = cost

        def create_distance_callback(dist_matrix):
            # Create a callback to calculate distances between cities.

            def distance_callback(from_node, to_node):
                return int(dist_matrix[from_node][to_node])

            return distance_callback

        routing = pywrapcp.RoutingModel(len(changes), 1, 0)
        search_parameters = pywrapcp.RoutingModel.DefaultSearchParameters()
        # Create the distance callback.
        dist_callback = create_distance_callback(dist)
        routing.SetArcCostEvaluatorOfAllVehicles(dist_callback)

        assignment = routing.SolveWithParameters(search_parameters)
        if assignment:
            # Solution distance.
            print("Total cycles: " + str(assignment.ObjectiveValue()))
            # Display the solution.
            # Only one route here; otherwise iterate from 0 to routing.vehicles() - 1
            route_number = 0
            index = routing.Start(route_number)  # Index of the variable for the starting node.
            page = 0x20
            content = 0x7f
            # TODO: I think this will end by visiting the origin node which
            #  is not what we want
            while not routing.IsEnd(index):
                _, new_page, offset, new_content = changes[index]

                if new_page != page:
                    page = new_page
                    yield self._emit(Opcode.SET_PAGE)
                    yield page

                if new_content != content:
                    content = new_content
                    yield self._emit(Opcode.SET_CONTENT)
                    yield content

                self._write(page << 8 | offset, content)
                yield self._emit(offset)

                index = assignment.Value(routing.NextVar(index))
        else:
            raise ValueError('No solution found.')

    def _heuristic_opcode_scheduler(self, changes):
        # Heuristic: group by content byte first then page
        data = {}
        for ch in changes:
            xor_weight, page, offset, content = ch
            data.setdefault(content, {}).setdefault(page, set()).add(offset)

        for content, page_offsets in data.items():
            yield self._emit(Opcode.SET_CONTENT)
            yield content
            for page, offsets in page_offsets.items():
                yield self._emit(Opcode.SET_PAGE)
                yield page

                for offset in offsets:
                    self._write(page << 8 | offset, content)
                    yield self._emit(offset)

    def _heuristic_page_first_opcode_scheduler(self, changes):
        # Heuristic: group by page first then content byte
        data = {}
        for ch in changes:
            xor_weight, page, offset, content = ch
            data.setdefault(page, {}).setdefault(content, set()).add(offset)

        for page, content_offsets in data.items():
            yield self._emit(Opcode.SET_PAGE)
            yield page
            for content, offsets in content_offsets.items():
                yield self._emit(Opcode.SET_CONTENT)
                yield content

                for offset in offsets:
                    self._write(page << 8 | offset, content)
                    yield self._emit(offset)

    def index_changes(self, deltas: np.array,
                      memmap: np.array) -> Set[Tuple[int, int, int, int]]:
        """Transform encoded screen to sequence of change tuples.

        Change tuple is (xor_weight, page, offset, content)
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

            # print("y=%d -> page=%02x" % (y, page))
            xor_weight = hamming_weight(xor)
            offset = y_base - (page << 8) + x_byte

            changes.add((xor_weight, page, offset, np.asscalar(it[0])))
            it.iternext()

        return changes

    def _emit(self, opcode: Union[Opcode, int]) -> int:
        self.cycles += self.CYCLES[opcode]
        return opcode.value if opcode in Opcode else opcode

    @staticmethod
    def similarity(a1: np.array, a2: np.array) -> float:
        """Measure bitwise % similarity between two arrays"""
        bits_different = np.asscalar(np.sum(np.logical_xor(a1, a2)))

        return 1 - (bits_different / (np.shape(a1)[0] * np.shape(a1)[1]))

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

    def from_stream(self, stream: Iterator[int]) -> Tuple[int, int, int]:
        """Replay an opcode stream to build a screen image."""
        page = 0x20
        content = 0x7f
        num_content_changes = 0
        num_page_changes = 0
        num_content_stores = 0
        for b in stream:
            if b == Opcode.SET_CONTENT.value:
                content = next(stream)
                num_content_changes += 1
                continue
            elif b == Opcode.SET_PAGE.value:
                page = next(stream)
                num_page_changes += 1
                continue
            elif b == Opcode.TICK.value:
                continue
            elif b == Opcode.END_FRAME.value:
                break

            num_content_stores += 1
            self._write(page << 8 | b, content)

        return num_content_stores, num_content_changes, num_page_changes
