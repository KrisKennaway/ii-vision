import numpy as np
import librosa
import soundfile as sf

import opcodes
import video


class Audio:
    def encode_audio(self, audio):
        for a in audio:
            yield opcodes.Tick(a)
            yield opcodes.Tick(50-a)

def main():
    filename = librosa.util.example_audio_file()

    data, samplerate = sf.read(filename, dtype='float32')
    data = data.T
    a = librosa.resample(data, samplerate, 20000).flatten()

    a = librosa.util.normalize(a)
    a = (a * 10 + 25).astype(np.int)

    s = video.Video(frame_rate=None)
    au = Audio()

    with open("out.bin", "wb") as out:
        out.write(bytes(s.emit_stream(au.encode_audio(a))))
        out.write(bytes(s.done()))


if __name__ == "__main__":
    main()