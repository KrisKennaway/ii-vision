"""Multiplexes video and audio inputs to encoded byte stream."""

from typing import Iterable, Iterator

import audio
import machine
import opcodes
import video


class Movie:
    def __init__(
            self, filename: str,
            every_n_video_frames: int = 1,
            audio_normalization: float = None):
        self.filename = filename  # type: str
        self.every_n_video_frames = every_n_video_frames  # type: int
        self.audio = audio.Audio(
            filename, normalization=audio_normalization)  # type: audio.Audio
        self.video = video.Video(filename)  # type: video.Video

        self.stream_pos = 0  # type: int

        # TODO: don't use this as well as cycle_counter, it's a relic of when
        # I relied on variable-duration opcodes for frame timings.
        self.cycles = 0  # type: int
        self.cycle_counter = machine.CycleCounter()

        self.state = machine.Machine(
            self.cycle_counter,
            self.video.memory_map,
            self.video.update_priority
        )

    def encode(self) -> Iterator[opcodes.Opcode]:
        """

        :return:
        """
        video_frames = self.video.frames()
        video_seq = None

        for au in self.audio.audio_stream():
            self.cycles += self.audio.cycles_per_tick
            if self.video.tick(self.cycles):
                video_frame = next(video_frames)
                if ((self.video.frame_number - 1) % self.every_n_video_frames
                        == 0):
                    print("Starting frame %d" % self.video.frame_number)
                    video_seq = self.video.encode_frame(video_frame)

            # au has range -15 .. 16 (step=1)
            # Tick cycles are units of 2
            tick = au * 2  # -30 .. 32 (step=2)
            tick += 34  # 4 .. 66 (step=2)

            (page, content, offsets) = next(video_seq)

            yield opcodes.TICK_OPCODES[(tick, page)](content, offsets)

    def _emit_bytes(self, _op):
        """

        :param _op:
        :return:
        """
        for b in self.state.emit(_op):
            yield b
            self.stream_pos += 1

    def emit_stream(self, ops: Iterable[opcodes.Opcode]) -> Iterator[int]:
        """

        :param ops:
        :return:
        """
        for op in ops:
            # Keep track of where we are in TCP client socket buffer
            socket_pos = self.stream_pos % 2048
            if socket_pos >= 2044:
                # 2 dummy bytes + 2 address bytes for next opcode
                yield from self._emit_bytes(opcodes.Ack())
            yield from self._emit_bytes(op)

    def done(self) -> Iterator[int]:
        """Terminate opcode stream.

        :return:
        """
        yield from self._emit_bytes(opcodes.Terminate())
