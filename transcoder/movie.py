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
            audio_normalization: float = None,
            max_bytes_out: int = None
    ):
        self.filename = filename  # type: str
        self.every_n_video_frames = every_n_video_frames  # type: int
        self.max_bytes_out = max_bytes_out  # type: int

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

        self.aux_memory_bank = False

    def encode(self) -> Iterator[opcodes.Opcode]:
        """

        :return:
        """
        video_frames = self.video.frames()
        video_seq = None

        for au in self.audio.audio_stream():
            self.cycles += self.audio.cycles_per_tick
            if self.video.tick(self.cycles):
                main, aux = next(video_frames)
                if ((self.video.frame_number - 1) % self.every_n_video_frames
                        == 0):
                    print("Starting frame %d" % self.video.frame_number)
                    main_seq = self.video.encode_frame(
                        main, self.video.memory_map, self.video.update_priority)
                    aux_seq = self.video.encode_frame(
                        aux, self.video.aux_memory_map,
                        self.video.aux_update_priority)

            # au has range -15 .. 16 (step=1)
            # Tick cycles are units of 2
            tick = au * 2  # -30 .. 32 (step=2)
            tick += 34  # 4 .. 66 (step=2)

            (page, content, offsets) = next(
                        aux_seq if self.aux_memory_bank else main_seq)

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
            if self.max_bytes_out and self.stream_pos >= self.max_bytes_out:
                yield from self.done()
                return
            # Keep track of where we are in TCP client socket buffer
            socket_pos = self.stream_pos % 2048
            if socket_pos >= 2044:
                # 2 dummy bytes + 2 address bytes for next opcode
                yield from self._emit_bytes(opcodes.Ack(self.aux_memory_bank))
                # Flip-flop between MAIN and AUX banks
                self.aux_memory_bank = not self.aux_memory_bank
            yield from self._emit_bytes(op)

        yield from self.done()

    def done(self) -> Iterator[int]:
        """Terminate opcode stream.

        :return:
        """
        yield from self._emit_bytes(opcodes.Terminate())

        # Player expects to fill 2K TCP buffer so pad it out
        for _ in range(2048 - (self.stream_pos % 2048)):
            yield 0x00
