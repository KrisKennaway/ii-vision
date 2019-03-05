import numpy as np
import audioread
import librosa

import opcodes
import video

TICKS = {
    4: opcodes.Tick4,
    6: opcodes.Tick6,
    8: opcodes.Tick8,
    10: opcodes.Tick10,
    12: opcodes.Tick12,
    14: opcodes.Tick14,
    16: opcodes.Tick16,
    18: opcodes.Tick18,
    20: opcodes.Tick20,
    22: opcodes.Tick22,
    24: opcodes.Tick24,
    26: opcodes.Tick26,
    28: opcodes.Tick28,
    30: opcodes.Tick30,
    32: opcodes.Tick32,
    34: opcodes.Tick34,
    36: opcodes.Tick36,
    38: opcodes.Tick38,
    40: opcodes.Tick40,
    42: opcodes.Tick42,
    44: opcodes.Tick44,
    46: opcodes.Tick46,
    48: opcodes.Tick48,
    50: opcodes.Tick50,
    52: opcodes.Tick52,
    54: opcodes.Tick54,
    56: opcodes.Tick56,
    58: opcodes.Tick58,
    60: opcodes.Tick60,
    62: opcodes.Tick62,
    64: opcodes.Tick64,
    66: opcodes.Tick66,
}


class Audio:
    def encode_audio(self, audio):
        for a in audio:
            a = max(-30, min(a * 2, 32)) + 34
            yield TICKS[a]()


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
