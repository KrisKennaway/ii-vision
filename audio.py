import random

import numpy as np
import audioread
import librosa

import opcodes
import video


class Audio:
    def __init__(
            self, filename: str, normalization: float = 1.0):
        self.filename = filename
        self.normalization = normalization

        # TODO: take into account that the available range is slightly offset
        # as fraction of total cycle count?
        self._tick_range = [4, 66]
        self.cycles_per_tick = 73

        # TODO: round to divisor of video frame rate
        self.sample_rate = 14340  # int(1024. * 1024 / self.cycles_per_tick)

    def audio_stream(self):
        with audioread.audio_open(self.filename) as f:
            for buf in f.read_data(128 * 1024):

                data = np.frombuffer(buf, dtype='int16').astype(
                    'float32').reshape((f.channels, -1), order='F')

                a = librosa.core.to_mono(data)
                a = librosa.resample(a, f.samplerate,
                                     self.sample_rate).flatten()

                a /= 16384  # normalize to -1.0 .. 1.0
                a *= self.normalization

                # Convert to -16 .. 16
                a = (a * 16).astype(np.int)
                a = np.clip(a, -15, 16)

                yield from a


def main():
    filename = "Computer Chronicles - 06x05 - The Apple II.mp4"

    s = video.Video(frame_rate=None)
    au = Audio(filename, normalization=3)

    with open("out.bin", "wb") as out:
        for b in s.emit_stream(au.encode_audio()):
            out.write(bytearray([b]))
        out.write(bytes(s.done()))


if __name__ == "__main__":
    main()
