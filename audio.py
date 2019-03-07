import random

import numpy as np
import audioread
import librosa

import opcodes
import video


class Audio:
    def encode_audio(self, audio):
        for a in audio:
            a = max(-30, min(a * 2, 32)) + 34
            page = random.randint(32, 56)
            content = random.randint(0,255)
            offsets = [random.randint(0, 255) for _ in range(4)]
            yield opcodes.TICK_OPCODES[(a, page)](content, offsets)


def main():
    filename = "Computer Chronicles - 06x05 - The Apple II.mp4"

    s = video.Video(frame_rate=None)
    au = Audio()

    with audioread.audio_open(filename) as f:
        with open("out.bin", "wb") as out:
            for buf in f.read_data(128 * 1024):
                print(f.channels, f.samplerate, f.duration)

                data = np.frombuffer(buf, dtype='int16').astype(
                    'float32').reshape((f.channels, -1), order='F')

                a = librosa.core.to_mono(data)
                a = librosa.resample(a, f.samplerate, 14000).flatten()

                # Normalize to 95%ile
                # norm = max(
                #    abs(np.percentile(a, 5, axis=0)),
                #    abs(np.percentile(a, 95, axis=0))
                # )
                # print(min(a),max(a))
                # print(norm)

                # XXX how to estimate normalization without reading whole file?
                norm = 12000

                a /= norm  # librosa.util.normalize(a)
                a = (a * 32).astype(np.int)

                out.write(bytes(s.emit_stream(au.encode_audio(a))))
    out.write(bytes(s.done()))


if __name__ == "__main__":
    main()
