#
#  Makefile
#  Apple2BuildPipelineSample
#
#  Part of a sample build pipeline for Apple II software development
#
#  Created by Quinn Dunki on 8/15/14.
#  One Girl, One Laptop Productions
#  http://www.quinndunki.com
#  http://www.quinndunki.com/blondihacks
#

include make/head.mk

# Customize this file to control what gets built, what machines to
# target, where in memory to put it, etc.

# The name of your system or binary file to build goes here:
PGM=ethernet

# Uncomment the one you want below (the first one is the default):
#    MACHINE = apple2
#    MACHINE = apple2-dos33
#    MACHINE = apple2-system
#    MACHINE = apple2-loader
#    MACHINE = apple2-reboot
    MACHINE = apple2enh
#    MACHINE = apple2enh-dos33
#    MACHINE = apple2enh-system
#    MACHINE = apple2enh-loader
#    MACHINE = apple2enh-reboot

# Uncomment the appropriate project type.  If your entry point is
# main() in a .c file, then your project type is cc65.  If your
# entry point is in an assembly file, then you project type is
# ca65:
#    PROJECT_TYPE = cc65
PROJECT_TYPE = ca65

# Uncomment and set this to your starting address in Apple II memory
# if necessary:
    START_ADDR = 8000

# Set the default CPU to assemble for.  You can change this in the
# body of a .s file using control commands like ".PC02".  Uncomment
# the one you want below (the first one is the default):
#    CPU = 6502
#    CPU = 65SC02
    CPU = 65C02
#    CPU = 65816
# Note: You can assemble for 65816 in 16-bit mode but the C compiler
# will only produce 8-bit code.

# Add any other directories where you are putting C or assembly source
# files to this list:
SRCDIRS+=

# If you have a non-standard cc65 install, you may need to change
# some of these.  Uncomment the following line and change it to the
# correct path to CC65_HOME if the default is not correct.  If you
# are using cc65 v2.13.3, the default is:
# 	/usr/local/lib/cc65
# If you are using cc65 v2.17, the default is:
# 	/usr/local/share/cc65
#    export CC65_HOME := /path/to/your/cc65/directory
# 
# If the path to the cc65 binaries is not correct, uncomment this
# line and change it:
#    CC65_BIN = /usr/local/bin

# If you want to add arguments to the compile commandline, add them
# to this variable:
#    CFLAGS += -Os

# If you want to add arguments to the assembly commandline, add them
# to this variable:
#    ASMFLAGS += -g

# If you want to add arguments to the link commandline, add them to
# this variable:
#    LDFLAGS += -v

# If you want to add arguments to the BASIC tokenizer commandline,
# add them to this valiable:
#    BASICFLAGS += --optimize

# If you want to link the lores graphics driver with your executable,
# uncomment the next line.
#    DRIVERS += loresgr
#
# To use the lores driver, add code which looks like this to your
# project:
#
# 	#include "drivers/a2_lores_drv.h"
#       int main(void)
#       {
# 	    tgi_install(&a2_lores_drv);
# 	    tgi_init();
# 	    // Use the graphics driver
# 	    tgi_uninstall();
# 	}
#
# Read the $CC65_HOME/include/tgi.h file to see what the
# driver interface provides.  Also check out
# $CC65_HOME/include/apple2.h to see the colour definitions.

# If you want to link the hires graphics driver with your executable,
# uncomment the next line.
#    DRIVERS += hiresgr
#
# To use the hires driver, add code which looks like this to your
# project:
#
# 	#include "drivers/a2_hires_drv.h"
#       int main(void)
#       {
# 	    tgi_install(&a2_hires_drv);
# 	    tgi_init();
# 	    // Use the graphics driver
# 	    tgi_uninstall();
# 	}
#
# Read the $CC65_HOME/cc65/include/tgi.h file to see what the
# driver interface provides.  Also check out
# $CC65_HOME/include/apple2.h to see the colour definitions.

# If you want to link the extended memory driver with your executable,
# uncomment the next line.
#    DRIVERS += auxmem
#
# To use the auxmem driver, add code which looks like this to your
# project:
#
# 	#include "drivers/a2_auxmem_drv.h"
#       int main(void)
#       {
# 	    em_install(&a2_auxmem_drv);
# 	    // Use the auxmem driver
# 	    em_uninstall();
# 	}
#
# Read the $CC65_HOME/include/em.h file to see what the
# driver interface provides.

# If you want to link the joystick driver with your executable,
# uncomment the next line.
#    DRIVERS += joystick
#
# To use the joystick driver, add code which looks like this to your
# project:
#
# 	#include "drivers/a2_joystick_drv.h"
#       int main(void)
#       {
# 	    joy_install(&a2_joystick_drv);
# 	    // Use the joystick driver
# 	    joy_uninstall();
# 	}
#
# Read the $CC65_HOME/include/joystick.h file to see what the
# driver interface provides.

# If you want to link the mouse driver with your executable,
# uncomment the next line.
#    DRIVERS += mouse
#
# To use the mouse driver, add code which looks like this to your
# project:
#
# 	#include "drivers/a2_mouse_drv.h"
#       int main(void)
#       {
# 	    mouse_install(&mouse_def_callbacks, &a2_mouse_drv);
# 	    // Use the mouse driver
# 	    mouse_uninstall();
# 	}
#
# Read the $CC65_HOME/include/mouse.h file to see what the
# driver interface provides.

# If you want to link the serial driver with your executable,
# uncomment the next line.
#    DRIVERS += serial
#
# To use the serial driver, add code which looks like this to your
# project:
#
# 	#include "drivers/a2_serial_drv.h"
#       int main(void)
#       {
# 	    ser_install(&a2_serial_drv);
# 	    // Use the serial driver
# 	    ser_uninstall();
# 	}
#
# Read the $CC65_HOME/include/serial.h file to see what the
# driver interface provides.

# If you have java installed in a non-standard location, you can set
# the path to it by uncommenting the following line:
#    export JAVA=/usr/bin/java

# If you want to copy one or more files or directories to the target disk
# image, add the root directory to this variable.  All files will be
# copied from the source to the target using the same path from the source.
#
# For example, if you set COPYDIRS to dir and in your project you have
# the following files:
#     dir/mySystemFile
#     dir/newDir/anotherFile
#
# Then, during the copy phase, mySystemFile will be copied into the root
# of the disk and anotherFile will be copied into a directory named
# newDir.  The newDir directory will be created if it does not already
# exist.
#
# The name of the file to copy is checked and if it ends in:
#     .as - It assumes the file is in AppleSingle format.  The .as
#           suffix is stripped from the name when copied to the
# 	    disk image.
# .<char> - If the file ends with a single character which matches
#           a DOS 3.3 file type (A, B, T, etc) it uses that value as
#           the file type of the file copied to the disk image.  The
#           single character is removed from the file name.
#  .<TLA> - If the file ends with a three letter alpha extension, it
#           uses that TLA as the file type of the file copied to the
#           disk image.  The TLA is removed from the file name.
#
# If you do not provide any type information for your filenames,
# it will be copied as a binary.
#
COPYDIRS=

# Add any rules you want to execute before any compiles or assembly
# commands are called here, if any.  You can generate .c, .s or .h
# files for example.  You can generate data files.  Whatever you
# might need.
#
# All of your commands associated with a rule _must_ start with a tab
# character.  Xcode makes it a bit tough to type a tab character by
# default.  Press option-tab within Xcode to insert a tab character.
gen:

# For any files you generated in the gen target above, you should
# add rules in genclean to remove those generated files when you
# clean your build.
genclean:

# Do not change anything else below here...
include make/tail.mk
