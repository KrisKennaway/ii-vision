#
#  head.mk
#  Apple2BuildPipelineSample
#
#  Part of a sample build pipeline for Apple II software development
#
#  Created by Quinn Dunki on 8/15/14.
#  One Girl, One Laptop Productions
#  http://www.quinndunki.com
#  http://www.quinndunki.com/blondihacks
#

CC65_BIN=/usr/local/bin

ifneq ($(wildcard /usr/local/lib/cc65),)
    export CC65_HOME := /usr/local/lib/cc65
else
    export CC65_HOME := /usr/local/share/cc65
endif

CL65=$(CC65_BIN)/cl65
CA65=$(CC65_BIN)/ca65
CC65=$(CC65_BIN)/cc65
CO65=$(CC65_BIN)/co65

MERLIN_DIR=/usr/local
MERLIN_BIN=$(MERLIN_DIR)/bin/Merlin32
MERLIN_LIB=$(MERLIN_DIR)/lib/Merlin

AC=make/AppleCommander.jar

SRCDIRS=.

MACHINE=apple2
CPU=6502
CFLAGS=
ASMFLAGS=
LDFLAGS=
DRIVERS=
DRVDIR=drivers

XCODE_PATH=/Applications/Xcode.app
XCODE_INFO=$(XCODE_PATH)/Contents/Info.plist

CC65_PLUGIN_PATH=$(HOME)/Library/Developer/Xcode/Plug-ins/cc65.ideplugin
CC65_PLUGIN_INFO=$(CC65_PLUGIN_PATH)/Contents/Info.plist

XCODE_PLUGIN_COMPATIBILITY=DVTPlugInCompatibilityUUID


.PHONY: all gen genclean

all:
	@make gen
	@make build

