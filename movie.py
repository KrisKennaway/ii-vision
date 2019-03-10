"""Multiplexes video and audio inputs to encoded byte stream."""

from typing import Iterable, Iterator

import audio
import opcodes
import video


class Movie:
    def __init__(self, filename: str, audio_normalization: float = 1.0):
        self.filename = filename  # type: str
        self.audio = audio.Audio(
            filename, normalization=audio_normalization)  # type: audio.Audio
        self.video = video.Video(filename)  # type: video.Video

        self.cycles = 0

        self.stream_pos = 0  # type: int

        self.cycle_counter = opcodes.CycleCounter()

        self.state = opcodes.State(
            self.cycle_counter,
            self.video.memory_map,
            self.video.update_priority
        )

        self._last_op = opcodes.Nop()

    def encode(self) -> Iterator[opcodes.Opcode]:
        video_frames = self.video.frames()
        video_seq = None

        for au in self.audio.audio_stream():
            self.cycles += self.audio.cycles_per_tick
            if self.video.tick(self.cycles):
                print("Starting frame %d" % self.video.frame_number)
                video_frame = next(video_frames)
                video_seq = self.video.encode_frame(video_frame)

            # au has range -15 .. 16 (step=1)
            # Tick cycles are units of 2
            tick = au * 2  # -30 .. 32 (step=2)
            tick += 34  # 4 .. 66 (step=2)

            (page, content, offsets) = next(video_seq)

            yield opcodes.TICK_OPCODES[(tick, page)](content, offsets)

    def _emit_bytes(self, _op):
        # print("%04X:" % self.stream_pos)
        for b in self.state.emit(self._last_op, _op):
            yield b
            self.stream_pos += 1
        self._last_op = _op

    def emit_stream(self, ops: Iterable[opcodes.Opcode]) -> Iterator[int]:
        for op in ops:
            # Keep track of where we are in TCP client socket buffer
            socket_pos = self.stream_pos % 2048
            if socket_pos >= 2044:
                # Pad out to last byte in frame
                nops = (2047 - socket_pos) // 2
                # print("At position %04x, padding with %d nops" % (
                #    socket_pos, nops))
                for _ in range(nops):
                    yield from self._emit_bytes(opcodes.Nop())
                yield from self._emit_bytes(opcodes.Ack())
                # Ack falls through to nop
                self._last_op = opcodes.Nop()
            yield from self._emit_bytes(op)

    def done(self) -> Iterator[int]:
        """Terminate opcode stream."""
        yield from self._emit_bytes(opcodes.Terminate())
