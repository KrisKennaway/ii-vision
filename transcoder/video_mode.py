"""Enum representing video encoding mode."""

import enum


class VideoMode(enum.Enum):
    HGR = 0  # Hi-Res
    DHGR = 1  # Double Hi-Res (Colour)
    DHGR_MONO = 2  # Double Hi-Res (Mono)
