#
#  tail.mk
#  Apple2BuildPipelineSample
#
#  Part of a sample build pipeline for Apple II software development
#
#  Created by Quinn Dunki on 8/15/14.
#  One Girl, One Laptop Productions
#  http://www.quinndunki.com
#  http://www.quinndunki.com/blondihacks
#

BUILD_TYPE := $(shell if echo $(MACHINE) | grep -q -- -basic; then echo basic; elif echo $(MACHINE) | grep -q -- -merlin; then echo merlin; else echo cc65; fi)

CWD=$(shell pwd)

DISKIMAGE=$(PGM).dsk

EXECCMD=

BASIC_SRCS=$(patsubst ./%, %, $(wildcard $(addsuffix /*.bas, $(SRCDIRS))))
BASIC_OBJS=$(BASIC_SRCS:.bas=.tok)

ifeq ($(BUILD_TYPE),cc65)
    export PATH := $(PATH):$(CC65_BIN)

    # By default, use the a2 drivers.  If the machine is one of the enhanced
    # targets though, use the a2e drivers.
    DRV_BASE_MACHINE=a2
    BASE_MACHINE = apple2
    ifneq ($(filter $(MACHINE), apple2enh apple2enh-dos33 apple2enh-system apple2enh-loader apple2enh-reboot),)
        DRV_BASE_MACHINE=a2e
        BASE_MACHINE = apple2enh
    endif

    CC65_VERSION := $(shell $(CC65) --version 2>&1 | grep '^cc65 V')

    ifeq ($(CC65_VERSION),cc65 V2.13.3)
        export CC65_SUPPORTS_APPLE_SINGLE=0
        CC65_CREATE_DEP_ARG=--create-dep
        CC65_LIST_ARG=-l
        CC65_DRV_DIR=$(CC65_HOME)

        MACHCONFIG= -t $(BASE_MACHINE)
        ifeq ($(filter $(MACHINE), apple2 apple2enh),)
            MACHCONFIG += -C $(MACHINE).cfg
        endif
    else
        export CC65_SUPPORTS_APPLE_SINGLE=1
        CC65_CREATE_DEP_ARG=--create-dep $(@:.o=.u)
        CC65_LIST_ARG=-l $(@:.o=.lst)
        CC65_DRV_DIR=$(CC65_HOME)/target/$(BASE_MACHINE)/drv

        MACHCONFIG= -t $(BASE_MACHINE)
        ifneq ($(filter $(MACHINE), apple2-system apple2enh-system),)
            MACHCONFIG += -C $(BASE_MACHINE)-system.cfg
        else
            ifeq ($(PROJECT_TYPE),ca65)
                MACHCONFIG += -C $(BASE_MACHINE)-asm.cfg
                LDFLAGS += -u __EXEHDR__
            else
                MACHCONFIG += -C $(BASE_MACHINE).cfg
            endif
         endif
    endif

    ifneq ($(DRIVERS),)
        SRCDIRS+=$(DRVDIR)
    endif

    C_SRCS=$(patsubst ./%, %, $(wildcard $(addsuffix /*.c, $(SRCDIRS))))
    C_OBJS=$(C_SRCS:.c=.o)
    C_DEPS=$(C_SRCS:.c=.u)

    ASM_SRCS=$(patsubst ./%, %, $(wildcard $(addsuffix /*.s, $(SRCDIRS))))
    ASM_OBJS=$(ASM_SRCS:.s=.o)
    ASM_LSTS=$(ASM_SRCS:.s=.lst)

    MAPFILE=$(PGM).map

    ifneq ($(START_ADDR),)
        # If the MACHINE is set to an option which does not support a variable
        # start address, then error.
        ifneq ($(filter $(MACHINE), apple2-system apple2enh-system),)
            $(error You cannot change start address with this machine type)
        endif
    else
        # If not set, then use the default for the config as per cc65
	# documentation
        ifneq ($(filter $(MACHINE), apple2 apple2-dos33 apple2enh apple2enh-dos33),)
            START_ADDR=803
        endif
        ifneq ($(filter $(MACHINE), apple2-system apple2enh-system),)
            START_ADDR=2000
        endif
        ifneq ($(filter $(MACHINE), apple2-loader apple2-reboot apple2enh-loader apple2enh-reboot),)
            START_ADDR=800
        endif
    endif

    LDFLAGS += --start-addr 0x$(START_ADDR)

    ifneq ($(filter $(MACHINE), apple2 apple2enh apple2-dos33 apple2enh-dos33),)
        EXECCMD=$(shell echo brun $(PGM) | tr '[a-z]' '[A-Z]')
    endif
else
    C_OBJS=
    C_DEPS=

    ASM_OBJS=
    ASM_LSTS=
endif

ifeq ($(BUILD_TYPE),merlin)
    ASM_SRCS=$(patsubst ./%, %, $(wildcard $(addsuffix /*.s, $(SRCDIRS))))
    MAPFILE=_Output.txt
    EXECCMD=$(shell echo brun $(PGM) | tr '[a-z]' '[A-Z]')
endif

ifeq ($(BUILD_TYPE),basic)
    MAPFILE=
    EXECCMD=$(shell echo run $(PGM) | tr '[a-z]' '[A-Z]')
endif

OBJS=$(C_OBJS) $(ASM_OBJS) $(BASIC_OBJS)

ALLTARGET=$(DISKIMAGE)


.PHONY: build execute clean cleandrivers xcodefix

build: $(ALLTARGET)

$(DISKIMAGE): $(PGM)
	make/createDiskImage $(AC) $(MACHINE) "$(DISKIMAGE)" "$(PGM)" "$(START_ADDR)" $(BASIC_OBJS) $(COPYDIRS)

execute: $(DISKIMAGE)
	osascript make/V2Make.scpt "$(CWD)" "$(PGM)" "$(CWD)/make/DevApple.vii" "$(EXECCMD)"

%.tok:	%.bas
	make/bt $< $(BASICFLAGS) -o $@

ifneq ($(DRIVERS),)
cleandrivers:
	rm -Rf "$(DRVDIR)"

else
cleandrivers:

endif

clean: genclean cleandrivers
	rm -f "$(PGM)" $(OBJS) $(C_DEPS) $(MAPFILE) $(ASM_LSTS) "$(DISKIMAGE)"

cleanMacCruft:
	rm -rf pkg

# Some gen phase stuff...
gen: xcodefix $(DRIVERS)

xcodefix:
	defaults write "$(CC65_PLUGIN_INFO)" $(XCODE_PLUGIN_COMPATIBILITY)s -array `defaults read "$(XCODE_INFO)" $(XCODE_PLUGIN_COMPATIBILITY)` || true


ifeq ($(BUILD_TYPE),basic)
# Build rules for BASIC projects

$(PGM): $(OBJS)
	cp $(PGM).tok $(PGM)

$(OBJS): Makefile


endif


ifeq ($(BUILD_TYPE),merlin)
# Build rules for Merlin projects

$(PGM): $(ASM_SRCS) Makefile
	$(MERLIN_BIN) -V $(MERLIN_LIB) linkscript.s
	rm -f _FileInformation.txt

endif


ifeq ($(BUILD_TYPE),cc65)
# Build rules for cc65 projects

$(PGM): $(OBJS)
	make/errorFilter.sh $(CL65) $(MACHCONFIG) --mapfile $(MAPFILE) $(LDFLAGS) -o "$(PGM)" $(OBJS)

$(OBJS): Makefile

%.o:	%.c
	make/errorFilter.sh $(CL65) $(MACHCONFIG) $(CFLAGS) $(CC65_CREATE_DEP_ARG) -c -o $@ $<
	sed -i .bak 's/\.s:/.o:/' $(@:.o=.u)
	rm -f $(@:.o=.u).bak

%.o:	%.s
	make/errorFilter.sh $(CL65) $(MACHCONFIG) --cpu $(CPU) $(ASMFLAGS) $(CC65_LIST_ARG) -c -o $@ $<


.PHONY: loresgr hiresgr auxmem joystick mouse serial
# Lores driver codegen
loresgr: $(DRVDIR)/a2_lores_drv.s $(DRVDIR)/a2_lores_drv.h

$(DRVDIR)/a2_lores_drv.s: $(CC65_DRV_DIR)/tgi/$(DRV_BASE_MACHINE).lo.tgi
	mkdir -p $(DRVDIR)
	$(CO65) --code-label _a2_lores_drv -o $@ $(CC65_DRV_DIR)/tgi/$(DRV_BASE_MACHINE).lo.tgi

$(DRVDIR)/a2_lores_drv.h:
	mkdir -p $(DRVDIR)
	echo '#include <tgi.h>' > $@
	echo 'extern char a2_lores_drv;' >> $@


# Hires driver codegen
hiresgr: $(DRVDIR)/a2_hires_drv.s $(DRVDIR)/a2_hires_drv.h

$(DRVDIR)/a2_hires_drv.s: $(CC65_DRV_DIR)/tgi/$(DRV_BASE_MACHINE).hi.tgi
	mkdir -p $(DRVDIR)
	$(CO65) --code-label _a2_hires_drv -o $@ $(CC65_DRV_DIR)/tgi/$(DRV_BASE_MACHINE).hi.tgi

$(DRVDIR)/a2_hires_drv.h:
	mkdir -p $(DRVDIR)
	echo '#include <tgi.h>' > $@
	echo 'extern char a2_hires_drv;' >> $@


# Auxmem driver codegen
auxmem: $(DRVDIR)/a2_auxmem_drv.s $(DRVDIR)/a2_auxmem_drv.h

$(DRVDIR)/a2_auxmem_drv.s: $(CC65_DRV_DIR)/emd/$(DRV_BASE_MACHINE).auxmem.emd
	mkdir -p $(DRVDIR)
	$(CO65) --code-label _a2_auxmem_drv -o $@ $(CC65_DRV_DIR)/emd/$(DRV_BASE_MACHINE).auxmem.emd

$(DRVDIR)/a2_auxmem_drv.h:
	mkdir -p $(DRVDIR)
	echo '#include <em.h>' > $@
	echo 'extern char a2_auxmem_drv;' >> $@


# Joystick driver codegen
joystick: $(DRVDIR)/a2_joystick_drv.s $(DRVDIR)/a2_joystick_drv.h

$(DRVDIR)/a2_joystick_drv.s: $(CC65_DRV_DIR)/joy/$(DRV_BASE_MACHINE).stdjoy.joy
	mkdir -p $(DRVDIR)
	$(CO65) --code-label _a2_joystick_drv -o $@ $(CC65_DRV_DIR)/joy/$(DRV_BASE_MACHINE).stdjoy.joy

$(DRVDIR)/a2_joystick_drv.h:
	mkdir -p $(DRVDIR)
	echo '#include <joystick.h>' > $@
	echo 'extern char a2_joystick_drv;' >> $@


# Mouse driver codegen
mouse: $(DRVDIR)/a2_mouse_drv.s $(DRVDIR)/a2_mouse_drv.h

$(DRVDIR)/a2_mouse_drv.s: $(CC65_DRV_DIR)/mou/$(DRV_BASE_MACHINE).stdmou.mou
	mkdir -p $(DRVDIR)
	$(CO65) --code-label _a2_mouse_drv -o $@ $(CC65_DRV_DIR)/mou/$(DRV_BASE_MACHINE).stdmou.mou

$(DRVDIR)/a2_mouse_drv.h:
	mkdir -p $(DRVDIR)
	echo '#include <mouse.h>' > $@
	echo 'extern char a2_mouse_drv;' >> $@


# Serial driver codegen
serial: $(DRVDIR)/a2_serial_drv.s $(DRVDIR)/a2_serial_drv.h

$(DRVDIR)/a2_serial_drv.s: $(CC65_DRV_DIR)/ser/$(DRV_BASE_MACHINE).ssc.ser
	mkdir -p $(DRVDIR)
	$(CO65) --code-label _a2_serial_drv -o $@ $(CC65_DRV_DIR)/ser/$(DRV_BASE_MACHINE).ssc.ser

$(DRVDIR)/a2_serial_drv.h:
	mkdir -p $(DRVDIR)
	echo '#include <serial.h>' > $@
	echo 'extern char a2_serial_drv;' >> $@

endif


-include $(C_DEPS)
