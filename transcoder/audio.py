"""Encodes input audio stream into sequence of speaker duty cycle counts."""

from typing import Iterator

import audioread
import librosa
import numpy as np


class Audio:
    def __init__(
            self, filename: str, normalization: float = None):
        self.filename = filename  # type: str

        # TODO: take into account that the available range is slightly offset
        # as fraction of total cycle count?
        self._tick_range = [4, 66]

        # At 73 cycles/tick, true audio playback sample rate is
        # roughly 1024*1024/73 = 14364 Hz (ignoring ACK slow path).
        # Typical audio encoding is 44100Hz which is close to 14700*3
        # Downscaling by 3x gives better results than trying to resample
        # to a non-divisor.  So we cheat a bit and play back the video a tiny
        # bit (<2%) faster.
        self.sample_rate = 14700.  # type: float

        self.normalization = (
                normalization or self._normalization())  # type: float

    def _decode(self, f, buf) -> np.array:
        """

        :param f:
        :param buf:
        :return:
        """
        data = np.frombuffer(buf, dtype='int16').astype(
            'float32').reshape((f.channels, -1), order='F')

        a = librosa.core.to_mono(data)
        a = librosa.resample(a, f.samplerate,
                             self.sample_rate).flatten()

        return a

    def _normalization(self, read_bytes=1024 * 1024 * 10):
        """Read first read_bytes of audio stream and compute normalization.

        We compute the 2.5th and 97.5th percentiles i.e. only 2.5% of samples
        will clip.

        :param read_bytes:
        :return:
        """
        raw = bytearray()
        with audioread.audio_open(self.filename) as f:
            for buf in f.read_data():
                raw.extend(bytearray(buf))
                if len(raw) > read_bytes:
                    break
        a = self._decode(f, raw)
        norm = np.max(np.abs(np.percentile(a, [2.5, 97.5])))

        return 16384. / norm

    def audio_stream(self) -> Iterator[int]:
        """

        :return:
        """
        with audioread.audio_open(self.filename) as f:
            for buf in f.read_data(128 * 1024):
                a = self._decode(f, buf)

                a /= 16384  # normalize to -1.0 .. 1.0
                a *= self.normalization

                # Convert to -16 .. 16
                a = (a * 16).astype(np.int)
                a = np.clip(a, -15, 16)

                yield from a
