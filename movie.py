"""Multiplexes video and audio inputs to encoded byte stream."""

from typing import Iterable, Iterator

import audio
import frame_grabber
import opcodes
import video


class Movie:
    def __init__(self, filename: str, audio_normalization:float=1.0):
        self.filename = filename  # type: str
        self.audio = audio.Audio(
            filename, normalization=audio_normalization)  # type: audio.Audio
        # TODO: get from input file
        self.video = video.Video()  # type: video.Video

        self.cycles = 0
        self.ticks_per_video_frame = (
                self.audio.sample_rate /  self.video.frame_rate)

        self.stream_pos = 0  # type: int

        self.cycle_counter = opcodes.CycleCounter()

        self.state = opcodes.State(
            self.cycle_counter,
            self.video.memory_map,
            self.video.update_priority
        )

        self._last_op = opcodes.Nop()

    def frames(self):
        yield from frame_grabber.bmp2dhr_frame_grabber(self.filename)

    def encode(self) -> Iterator[opcodes.Opcode]:
        ticks = 0
        frames = 0
        video_seq = None

        video_frames = self.frames()

        for au in self.audio.audio_stream():
            if ticks % self.ticks_per_video_frame == 0:
                frames += 1
                video_seq = self.video.encode_frame(next(video_frames))

                print("Starting frame %d" % frames)
                # TODO: compute similarity

            ticks += 1
            self.cycles += self.audio.cycles_per_tick

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
