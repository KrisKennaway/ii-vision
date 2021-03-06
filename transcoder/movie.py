"""Multiplexes video and audio inputs to encoded byte stream."""

from typing import Iterable, Iterator

import audio
import frame_grabber
import machine
import opcodes
import video
from palette import Palette
from video_mode import VideoMode


class Movie:
    def __init__(
            self, filename: str,
            every_n_video_frames: int = 1,
            audio_bitrate: int = 14700,
            audio_normalization: float = None,
            max_bytes_out: int = None,
            video_mode: VideoMode = VideoMode.HGR,
            palette: Palette = Palette.NTSC,
    ):
        self.filename = filename  # type: str
        self.every_n_video_frames = every_n_video_frames  # type: int
        self.max_bytes_out = max_bytes_out  # type: int
        self.video_mode = video_mode  # type: VideoMode
        self.palette = palette  # type: Palette

        self.audio = audio.Audio(
            filename, bitrate=audio_bitrate,
            normalization=audio_normalization)  # type: audio.Audio

        self.frame_grabber = frame_grabber.FileFrameGrabber(
            filename, mode=video_mode, palette=self.palette)
        self.video = video.Video(
            self.frame_grabber,
            ticks_per_second=self.audio.sample_rate,
            mode=video_mode,
            palette=self.palette
        )  # type: video.Video

        # Byte offset within TCP stream
        self.stream_pos = 0  # type: int

        # Current audio tick opcode count within movie stream.
        self.ticks = 0  # type: int

        # Tracks internal state of player virtual machine
        self.state = machine.Machine()

        # Currently operating on AUX memory bank?
        self.aux_memory_bank = False

    def encode(self) -> Iterator[opcodes.Opcode]:
        """

        :return:
        """
        video_frames = self.frame_grabber.frames()
        main_seq = None
        aux_seq = None

        yield opcodes.Header(mode=self.video_mode)

        for au in self.audio.audio_stream():
            self.ticks += 1
            if self.video.tick(self.ticks):
                try:
                    main, aux = next(video_frames)
                except StopIteration:
                    break

                if ((self.video.frame_number - 1) % self.every_n_video_frames
                        == 0):
                    print("Starting frame %d" % self.video.frame_number)
                    main_seq = self.video.encode_frame(main, is_aux=False)

                    if aux:
                        aux_seq = self.video.encode_frame(aux, is_aux=True)

            # au has range -15 .. 16 (step=1)
            # Tick cycles are units of 2
            tick = au * 2  # -30 .. 32 (step=2)
            tick += 34  # 4 .. 66 (step=2)

            (page, content, offsets) = next(
                aux_seq if self.aux_memory_bank else main_seq)

            yield opcodes.TICK_OPCODES[(tick, page)](content, offsets)

    def _emit_bytes(self, _op: opcodes.Opcode) -> Iterable[int]:
        """Emit compiled bytes corresponding to a player opcode.

        Also tracks byte stream position.
        """
        for b in self.state.emit(_op):
            yield b
            self.stream_pos += 1

    def emit_stream(self, ops: Iterable[opcodes.Opcode]) -> Iterator[int]:
        """Emit compiled byte stream corresponding to opcode stream.

        Inserts padding opcodes at 2KB stream boundaries, to instruct player
        to manage the TCP socket buffer.

        :param ops:
        :return:
        """
        for op in ops:
            if self.max_bytes_out and self.stream_pos >= self.max_bytes_out:
                yield from self.done()
                return

            yield from self._emit_bytes(op)

            # Keep track of where we are in TCP client socket buffer
            socket_pos = self.stream_pos % 2048
            if socket_pos >= 2044:
                # 2 op_ack address bytes + 2 payload bytes from ACK must
                # terminate 2K stream frame
                if self.video_mode == VideoMode.DHGR:
                    # Flip-flop between MAIN and AUX banks
                    self.aux_memory_bank = not self.aux_memory_bank

                yield from self._emit_bytes(opcodes.Ack(self.aux_memory_bank))
                assert self.stream_pos % 2048 == 0, self.stream_pos % 2048

        yield from self.done()

    def done(self) -> Iterator[int]:
        """Terminate byte stream by emitting terminal opcode and padding to 2KB.

        :return:
        """
        yield from self._emit_bytes(opcodes.Terminate())

        # Player expects to fill 2K TCP buffer so pad it out
        for _ in range(2048 - (self.stream_pos % 2048)):
            yield 0x00
