"""Screen module represents Apple II video display."""

# from ortools.constraint_solver import pywrapcp
# from ortools.constraint_solver import routing_enums_pb2

import numpy as np


def bitmap_similarity(a1: np.array, a2: np.array) -> float:
    """Measure bitwise % similarity between two bitmap arrays"""
    bits_different = np.sum(np.logical_xor(a1, a2)).item()

    return 1. - (bits_different / (np.shape(a1)[0] * np.shape(a1)[1]))


class Bytemap:
    """Bitmap array with horizontal pixels packed into bytes."""

    def __init__(self, bitmap: np.array):
        self.ymax = bitmap.shape[0]  # type: int
        self.xmax = bitmap.shape[1]  # type: int
        if self.xmax % 7 != 0:
            raise ValueError(
                "Bitmap x dimension not divisible by 7: %d" % self.xmax)

        self._unpacked_bitmap = bitmap

        self.bytemap = self._pack()  # type: np.array

    def _pack(self) -> np.array:
        pixels = self._unpacked_bitmap

        # Insert zero column after every 7
        for i in range(pixels.shape[1] // 7 - 1, -1, -1):
            pixels = np.insert(pixels, (i + 1) * 7, False, axis=1)

        # packbits is big-endian so we flip the array before and after to
        # invert this
        return np.flip(np.packbits(np.flip(pixels, axis=1), axis=1), axis=1)

    def unpack(self) -> np.array:
        """Convert packed screen representation to bitmap."""
        bm = np.unpackbits(self.bytemap, axis=1)
        bm = np.delete(bm, np.arange(0, bm.shape[1], 8), axis=1)

        # Need to flip each 7-bit sequence
        reorder_cols = []
        for i in range(bm.shape[1] // 7):
            for j in range((i + 1) * 7 - 1, i * 7 - 1, -1):
                reorder_cols.append(j)
        bm = bm[:, reorder_cols]

        return np.array(bm, dtype=np.bool)


class Bitmap:
    XMAX = None  # type: int
    YMAX = None  # type: int

    def __init__(self, bitmap: np.array = None):
        if bitmap is None:
            self.bitmap = np.zeros((self.YMAX, self.XMAX), dtype=bool)
        else:
            self.bitmap = bitmap

    def randomize(self) -> None:
        self.bitmap = np.random.randint(
            2, size=(self.YMAX, self.XMAX), dtype=bool)

    def pack(self):
        return Bytemap(self.bitmap)

    @classmethod
    def from_bytemap(cls, bytemap: Bytemap):
        return cls(bytemap.unpack())


class HGR140Bitmap(Bitmap):
    XMAX = 140  # double-wide pixels to not worry about colour effects
    YMAX = 192

    def pack(self):
        # Double each pixel horizontally
        return Bytemap(np.repeat(self.bitmap, 2, axis=1))

    @classmethod
    def from_bytemap(cls, bytemap: Bytemap):
        # Undouble pixels
        bm = bytemap.unpack()
        return cls(
            np.array(
                np.delete(bm, np.arange(0, bm.shape[1], 2), axis=1),
                dtype=np.bool
            ))


class HGRBitmap(Bitmap):
    XMAX = 280
    YMAX = 192


class DHGRBitmap(Bitmap):
    XMAX = 560
    YMAX = 192
