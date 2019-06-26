;
;  ][Vision
;
;  Created by Kris Kennaway on 07/01/2019.
;  Copyright © 2019 Kris Kennaway. All rights reserved.
;
;  W5100/Uthernet II code based on "TCP SOCKET DEMO FOR W5100/UTHERNET II" by D. Finnigan.
;
;  Multiplexed audio/video decoder for 64K, 1MHz Apple II systems with Uthernet II,
;  supporting:
;  - 5 bit DAC audio at ~14KHz
;  - 56 KB/sec video update bandwidth
;
;  This is sufficient for ~7.5 full page redraws of the hires screen per second, although the
;  effective frame rate is typically higher, when there are only partial changes between
;  frames.
;
;  Fitting this in 64K together with ProDOS is pretty tight.  We make use of 3 memory
;  segments:
;
;  LOWCODE (0x800 - 0x1fff)
;  HGR (0x2000 - 0x3fff): code needed only at startup, which will be erased as soon as we start playing a video
;  CODE (0x4000 - 0xbaff): rest of main memory unused by ProDOS

.include "apple2.inc"

; Write symbol table to .dbg file, so that we can read opcode offsets in the video
; transcoder.
.DEBUGINFO

.proc main

.segment "HGR"

; TODO: make these configurable
SRCADDR:  .byte   10,0,65,02                 ; 10.0.65.02     W5100 IP
FADDR:    .byte   10,0,0,1                   ; 10.0.0.1       FOREIGN IP
FPORT:    .byte   $07,$b9                    ; 1977           FOREIGN PORT
MAC:      .byte   $00,$08,$DC,$01,$02,$03    ; W5100 MAC ADDRESS

; SLOT 1 I/O ADDRESSES FOR THE W5100
; Change this to support the Uthernet II in another slot
;
; TODO: make slot I/O addresses customizable at runtime - would probably require somehow
; compiling a list of all of the binary offsets at which we reference $C09x and patching
; them in memory or on-disk.
WMODE = $C094
WADRH = $C095
WADRL = $C096
WDATA = $C097

;;;

headerlen = $07 ; video header length

; some dummy addresses in order to pad cycle counts
zpdummy = $08
dummy = $ffff

ptr = $06  ; TODO: we only use this for connection retry count

; soft-switches
KBD         = $C000
STORE80ON   = $C001
COL80ON     = $C00D
KBDSTRB     = $C010
TICK        = $C030 ; where the magic happens
TEXTOFF     = $C050
FULLSCR     = $C052
PAGE2OFF    = $C054
PAGE2ON     = $C055
HIRESON     = $C057
DHIRESON    = $C05E

; MONITOR SUBROUTINES
HGR         = $F3E2
HGR0        = $F3EA ; internal entry point within HGR that doesn't set soft-switches
COUT        = $FDED
PRBYTE      = $FDDA
PRNTAX      = $F941

PRODOS      = $BF00 ; ProDOS MLI entry point
RESET_VECTOR = $3F2 ; Reset vector

; W5100 LOCATIONS
MACADDR  =   $0009    ; MAC ADDRESS
SRCIP    =   $000F    ; SOURCE IP ADDRESS
RMSR     =   $001A    ; RECEIVE BUFFER SIZE

; SOCKET 0 LOCATIONS
S0MR = $0400  ; SOCKET 0 MODE REGISTER
S0CR = $0401  ; COMMAND REGISTER
S0SR = $0403  ; STATUS REGISTER
S0LOCALPORT = $0404   ; LOCAL PORT
S0FORADDR =  $040C    ; FOREIGN ADDRESS
S0FORPORT =  $0410    ; FOREIGN PORT
S0TXRR   =   $0422    ; TX READ POINTER REGISTER
S0TXWR   =   $0424    ; TX WRITE POINTER REGISTER
S0RXRSR  =   $0426    ; RX RECEIVED SIZE REGISTER
S0RXRD   =   $0428    ; RX READ POINTER REGISTER

; SOCKET 0 PARAMETERS
RXBASE =  $6000       ; SOCKET 0 RX BASE ADDR
RXMASK =  $1FFF       ; SOCKET 0 8KB ADDRESS MASK
TXBASE  =   $4000     ; SOCKET 0 TX BASE ADDR
TXMASK  =   RXMASK    ; SOCKET 0 TX MASK

; SOCKET COMMANDS
SCOPEN   =   $01  ; OPEN
SCCONNECT =  $04  ; CONNECT
SCDISCON =   $08  ; DISCONNECT
SCSEND   =   $20  ; SEND
SCRECV   =   $40  ; RECV

; SOCKET STATUS
STINIT   =   $13
STESTABLISHED = $17

; this is the main binary entrypoint (it will be linked at 0x800)
.segment "LOWCODE"
    JMP bootstrap

; Put code only needed at startup in the HGR page, we'll toast it when we're
; done starting up
.segment "HGR"

; RESET AND CONFIGURE W5100
bootstrap:
    ; install reset handler
    LDA #<exit
    STA RESET_VECTOR
    LDA #>exit
    STA RESET_VECTOR+1
    EOR #$A5
    STA RESET_VECTOR+2 ; checksum to ensure warm-start reset

    LDA   #6    ; 5 RETRIES TO GET CONNECTION
    STA   ptr   ; NUMBER OF RETRIES

reset_w5100:
    LDA #$80    ; reset
    STA WMODE
    LDA #3  ; CONFIGURE WITH AUTO-INCREMENT
    STA WMODE

; ASSIGN MAC ADDRESS
    LDA #>MACADDR
    STA WADRH
    LDA #<MACADDR
    STA WADRL
    LDX #0
@L1:
    LDA MAC,X
    STA WDATA ; USING AUTO-INCREMENT
    INX
    CPX #6  ;COMPLETED?
    BNE @L1

; ASSIGN A SOURCE IP ADDRESS
    LDA #<SRCIP
    STA WADRL
    LDX #0
@L2:
    LDA SRCADDR,X
    STA WDATA
    INX
    CPX #4
    BNE @L2

;CONFIGURE BUFFER SIZES

    LDA #<RMSR
    STA WADRL
    LDA #3 ; 8KB TO SOCKET 0
    STA WDATA ; SET RECEIVE BUFFER
    STA WDATA ; SET TRANSMIT BUFFER

; CONFIGRE SOCKET 0 FOR TCP

    LDA #>S0MR
    STA WADRH
    LDA #<S0MR
    STA WADRL
    LDA #$21 ; TCP MODE | !DELAYED_ACK
    STA WDATA

; SET LOCAL PORT NUMBER

    LDA #<S0LOCALPORT
    STA WADRL
    LDA #$C0 ; HIGH BYTE OF LOCAL PORT
    STA WDATA
    LDA #0 ; LOW BYTE
    STA WDATA

; SET FOREIGN ADDRESS
    LDA #<S0FORADDR
    STA WADRL
    LDX #0
@L3:
    LDA FADDR,X
    STA WDATA
    INX
    CPX #4
    BNE @L3

; SET FOREIGN PORT
    LDA FPORT   ; HIGH BYTE OF FOREIGN PORT
    STA WDATA   ; ADDR PTR IS AT FOREIGN PORT
    LDA FPORT+1  ; LOW BYTE OF PORT
    STA WDATA

; OPEN SOCKET
    LDA #<S0CR
    STA WADRL
    LDA #SCOPEN ;OPEN COMMAND
    STA WDATA

; CHECK STATUS REGISTER TO SEE IF SUCCEEDED
    LDA #<S0SR
    STA WADRL
    LDA WDATA
    CMP #STINIT ; IS IT SOCK_INIT?
    BEQ OPENED
    LDY #0
@L4:
    LDA @SOCKERR,Y
    BEQ @LDONE
    JSR COUT
    INY
    BNE @L4
@LDONE: BRK
@SOCKERR: .byte $d5,$d4,$c8,$c5,$d2,$ce,$c5,$d4,$a0,$c9,$c9,$ba,$a0,$c3,$cf,$d5,$cc,$c4,$a0,$ce,$cf,$d4,$a0,$cf,$d0,$c5,$ce,$a0,$d3,$cf,$c3,$cb,$c5,$d4,$a1
; "UTHERNET II: COULD NOT OPEN SOCKET!"
    .byte $8D,$00 ; cr+null

; TCP SOCKET WAITING FOR NEXT COMMAND
OPENED:
    LDA #<S0CR
    STA WADRL
    LDA #SCCONNECT
    STA WDATA

; WAIT FOR TCP TO CONNECT AND BECOME ESTABLISHED

CHECKTEST:
    LDA #<S0SR
    STA WADRL
    LDA WDATA ; GET SOCKET STATUS
    BEQ FAILED ; 0 = SOCKET CLOSED, ERROR
    CMP #STESTABLISHED
    BEQ wait_read_header ; SUCCESS
    BNE CHECKTEST

FAILED:
    DEC ptr
    BEQ ERRDONE ; TOO MANY FAILURES
    LDA #$AE    ; "."
    JSR COUT
    JMP reset_w5100 ; TRY AGAIN

ERRDONE:
    LDY #0
@L:
    LDA ERRMSG,Y
    BEQ @DONE
    JSR COUT
    INY
    BNE @L
@DONE: BRK

ERRMSG: .byte $d3,$cf,$c3,$cb,$c5,$d4,$a0,$c3,$cf,$d5,$cc,$c4,$a0,$ce,$cf,$d4,$a0,$c3,$cf,$ce,$ce,$c5,$c3,$d4,$a0,$ad,$a0,$c3,$c8,$c5,$c3,$cb,$a0,$d2,$c5,$cd,$cf,$d4,$c5,$a0,$c8,$cf,$d3,$d4
; "SOCKET COULD NOT CONNECT - CHECK REMOTE HOST"
    .byte $8D,$00

wait_read_header:
    LDA #<S0RXRSR   ; Socket 0 Received Size register
    STA WADRL       ;
    LDA WDATA       ; High byte of received size
    CMP #$01        ; expect at least 256 bytes
    BCS op_header   ; There is enough data...we don't care exactly how much

    ; TODO: Not sure whether this delay is needed?
    NOP ; Little delay ...
    NOP
    JMP wait_read_header   ; Check again

op_header:
    ; Point to socket 0 buffer
    LDA #>RXBASE
    STA WADRH
    LDA #<RXBASE
    STA WADRL
    
    ; read video header
    
    ; consume 6 padding bytes from HEADER opcode.
    ; TODO: implement version header so we won't try to play a video for an incompatible
    ; player version.
    LDA WDATA
    LDA WDATA
    LDA WDATA
    LDA WDATA
    LDA WDATA
    LDA WDATA

    JMP _op_header_hgr

.segment "CODE"

; Initialize (D)HGR in the CODE segment so we don't accidentally toast ourselves when
; erasing HGR
_op_header_hgr:
    LDA WDATA ; Video mode
    BEQ @1 ; 0 = HGR mode

    ; TODO: clear screen before displaying it to look cleaner
    
    ; DHGR mode

    STA TEXTOFF
    STA HIRESON
    STA DHIRESON
    STA COL80ON
    STA STORE80ON

    ; Clear aux screen
    STA PAGE2ON ; AUX memory active
    ; Co-opt HGR internals to clear AUX for us.
    LDA #$20
    JSR HGR0

    STA PAGE2OFF ; MAIN memory active

@1:
    JSR HGR ; nukes the startup code we placed in HGR segment
    STA FULLSCR

    ; establish invariants expected by decode loop
    LDY #>RXBASE ; High byte of socket 0 receive buffer
    LDX #headerlen ; End of header
    
    LDA #>S0RXRSR
    STA WADRH
    ; fall through

; This is the main audio/video decode loop.
;
; The outer loop waits for the socket buffer to contain >2K of pending data before
; dispatching to the inner loop.
;
; The inner loop is structured in terms of "player opcodes", which receive any parameters
; from the TCP stream, and conclude with 2 bytes that are used as JMP address to the next
; opcode.
;
; Everything here has the following invariants:
; - opcodes are expected to take 73 cycles
;   - (though the NOP and TERMINATE opcodes don't do this but they're only used at the start/
;     end of the stream).
; - opcodes must maintain X=0 upon completion.
;   - this is assumed in some of the tick opcodes as a trick to get an extra cycle
;     via STA foo,X (5 cycles) instead of STA foo (4 cycles)
;
; During the ACK opcode and subsequent outer loop transit, we keep ticking the speaker
; every 36/37 cycles to maintain a multiple of 73 cycles.  Because we guarantee that the ACK
; appears every 2048 bytes, this lets us simplify the accounting for the W5100 socket buffer
; management (moving the address pointer etc).

; Somewhat magically, the cycle timings all align on multiples of 73 (with tick intervals
; alternating 36 and 37 cycles, as in the "neutral" (i.e. 50% speaker duty cycle)
; op_tick_36_* opcodes), without much work needed to optimize this.
;
; With a 73 cycle fundamental opcode (speaker) period and 1MHz clock speed, this gives a
; 14364 Hz "carrier" for the audio DAC, which is slightly audible (at least to my ageing
; ears) but quite acceptable.
;
; i.e. we get about 14364 player opcodes/second, with the op_ack + checkrecv + op_nop
; "slow path" costing 2 opcodes.  Each of the "fat" audio/video opcodes results in storing
; 4 video bytes, so we store about 56KB of video data per second.
;
; With 192x40 = 7680 visible bytes on the hires screen, this means we can do about 7.5 full
; page redraws/sec; but the effective frame rate will usually be much higher than this
; since we only prioritize the parts of the screen that are changing between frames.

; Wait until we have enough received data, and
;
; Notice that this has the only conditional opcodes in the entire decode loop ;-)
;
; Calling invariants:
; X = 0
; Y register has the high byte of the W5100 address pointer in the RX socket code, so we
; can't trash this until we are ready to point back there.
checkrecv:
    BIT TICK        ; 4

    LDA #<S0RXRSR   ; 2 Socket 0 Received Size register
    STA WADRL       ; 4
    LDA WDATA       ; 4 High byte of received size
    CMP #$08        ; 2 expect at least 2k
    ; TODO: check this doesn't cross a page bdy or it will add a cycle
    BCS recv        ; 3 There is data...we don't care exactly how much because it's at least 2K

    ; TODO: Not sure whether this delay is needed?
    NOP ; Little delay ...
    NOP
    JMP checkrecv   ; Check again

; There is data to read - restore W5100 address pointer where we last found it
;
; It turns out that the W5100 automatically wraps the address pointer at the end of the 8K RX/TX buffers
; Since we're using an 8K socket, that means we don't have to do any work to manage the read pointer!
recv: ; 15 cycles so far

    ; point W5100 back into the RX buffer where we left off in op_ack
    STY WADRH  ; 4
    STX WADRL  ; 4 normally X=0 here from op_ack except during first frame when we have just read the header.

    ; Check for keypress and pause the video
@0: BIT KBD ; 4
    ; TODO: check this doesn't cross a page bdy or it will add a cycle
    BPL @2 ; 3 nope

    ; Wait for second keypress to resume
    BIT KBDSTRB ; clear strobe
@1: BIT KBD
    BPL @1
    BIT KBDSTRB ; clear strobe

    ; fall through - tick timings don't matter

; pad cycles to keep ticking on 36/37 cycle cadence
; TODO: what can we do with the luxury of 14 unused cycles?!
@2: ; 30 so far
    ; X will usually already be 0 from op_ack except during first frame when reading
    ; header but reset it unconditionally
    LDX #$00 ; 2
    BIT TICK ; 4 ; 36

    NOP ; 2
    STA dummy ; 4
    STA dummy ; 4
    STA dummy ; 4

op_nop:
    LDY WDATA ; 4
    STY @D+2 ; 4
    LDY WDATA ; 4
    STY @D+1 ; 4
@D:
    JMP op_nop ; 3 ; 23 with following tick (37 in fallthrough case)

; Build macros for "fat" opcodes that do the following:
; - tick twice, N cycles apart (N = 4 .. 66 in steps of 2)
; - read a content byte from the stream
; - have an opcode-specific page offset configured (e.g. STA $2000,Y)
; - read 4 page offsets from the stream
; - store the content byte at these offsets
; - read 2 bytes from the stream as address of next opcode
;
; Each opcode has 6 cycles of padding, which is necessary to support reordering things to
; get the second "BIT TICK" at the right cycle offset.
;
; Where possible we share code by JMPing to a common tail instruction sequence in one of the
; earlier opcodes.  This is critical for reducing code size enough to fit.

.macro ticklabel page, cycles_left
    .concat ("_op_tick_page_", .string(page), "_tail_", .string(cycles_left))
.endmacro

.macro tickident page, cycles_left
    .ident (.concat ("_op_tick_page_", .string(page), "_tail_", .string(cycles_left))):
.endmacro

.macro op_tick_4 page
;4+(4)+2+4+4+4+5+4+5+4+5+4+5+4+4+4+4+3=73
.ident (.concat ("op_tick_4_page_", .string(page))):
    BIT TICK ; 4
    BIT TICK ; 4

    STA zpdummy ; 3
    STA zpdummy ; 3

    ; load content byte
tickident page, 59
    LDA WDATA ; 4

    ; 4 x offset stores
tickident page, 55
    LDY WDATA ; 4
tickident page, 51
    STA page << 8,Y ; 5
tickident page, 46
    LDY WDATA ; 4
tickident page, 42
    STA page << 8,Y ; 5
tickident page, 37
    LDY WDATA ; 4
tickident page, 33
    STA page << 8,Y ; 5
tickident page, 28
    LDY WDATA ; 4
tickident page, 24
    STA page << 8,Y ; 5

    ; vector to next opcode
tickident page, 19
    LDA WDATA ; 4
tickident page, 15
    STA .ident(.concat ("_op_tick_4_page_", .string(page), "_jmp"))+2 ; 4
tickident page, 11
    LDA WDATA ; 4
tickident page, 7
    STA .ident(.concat ("_op_tick_4_page_", .string(page), "_jmp"))+1 ; 4
.ident(.concat ("_op_tick_4_page_", .string(page), "_jmp")):
    JMP op_nop ; 3
.endmacro

.macro op_tick_6 page
;4+(2+4)+3+4+4+5+4+5+4+5+4+5+4+4+4+5+3
.ident (.concat ("op_tick_6_page_", .string(page))):
    BIT TICK ; 4
    NOP ; 2
    BIT TICK ; 4

    STA zpdummy ; 3

tickident page, 60
    LDA WDATA ; 4

tickident page, 56
    LDY WDATA ; 4
tickident page, 52
    STA page << 8,Y ; 5
tickident page, 47
    LDY WDATA ; 4
tickident page, 43
    STA page << 8,Y ; 5
tickident page, 38
    LDY WDATA ; 4
tickident page, 34
    STA page << 8,Y ; 5
tickident page, 29
    LDY WDATA ; 4
tickident page, 25
    STA page << 8,Y ; 5

tickident page, 20
    LDA WDATA ; 4
tickident page, 16
    STA .ident(.concat ("_op_tick_6_page_", .string(page), "_jmp"))+2 ; 4
tickident page, 12
    LDA WDATA ; 4
tickident page, 8
    ; NB: we use ,X indexing here to get an extra cycle.  This requires us to
    ; maintain the invariant X=0 across opcode dispatch.  Surprisingly this doesn't turn
    ; out to be a big deal.
    STA .ident(.concat ("_op_tick_6_page_", .string(page), "_jmp"))+1,X ; 5

.ident (.concat ("_op_tick_6_page_", .string(page), "_jmp")):
    JMP op_nop ; 3
.endmacro

.macro op_tick_8 page
;4+(4+4)+3+3+55
.ident (.concat ("op_tick_8_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    BIT TICK ; 4

    STA zpdummy ; 3
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_55")) ; 3 + 55
.endmacro

.macro op_tick_10 page
;4+(4+2+4)+3+56
.ident (.concat ("op_tick_10_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    NOP ; 2
    BIT TICK ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_56")) ; 3 + 56
.endmacro

.macro op_tick_12 page
;4+(4+4+4)+3+3+51
.ident (.concat ("op_tick_12_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    BIT TICK ; 4

    STA zpdummy ; 3
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_51")) ; 3 + 51
.endmacro

.macro op_tick_14 page
;4+(4+4+2+4)+3+52
.ident (.concat ("op_tick_14_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    NOP ; 2
    BIT TICK ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_52")) ; 3+52
.endmacro

.macro op_tick_16 page
; 4+(4+4+4+4)+5+2+3+43
.ident (.concat ("op_tick_16_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    ; This temporarily violates X=0 invariant required by tick_6, but lets us share a
    ; common opcode tail; otherwise we need a dummy 4-cycle opcode between the ticks, which
    ; doesn't leave enough to JMP with.
    LDX WDATA ; 4
    LDY WDATA ; 4
    BIT TICK ; 4
    
    STA page << 8,x ; 5
    LDX #$00 ; 2 restore X=0 invariant

    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_43")) ; 3 + 43
.endmacro

.macro op_tick_18 page
; 4 + (4+4+4+2+4)+5+5+2+2+4+5+4+5+4+4+4+4+3
.ident (.concat ("op_tick_18_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    ; lets us reorder the 5-cycle STA page << 8,y outside of tick loop.
    ; This temporarily violates X=0 invariant required by tick_6
    LDX WDATA ; 4
    NOP ; 2
    BIT TICK ; 4

    STA page << 8,Y ; 5
    STA page << 8,X ; 5

    LDX #$00 ; 2 restore X=0 invariant

    ; used >3 pad cycles already; can't branch to tail
    NOP ; 2
    
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5

    ; vector to next opcode
    LDA WDATA ; 4
    STA @D+2 ; 4
    LDA WDATA ; 4
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_20 page
;4+(4+4+5+3+4)+3+46=73
.ident (.concat ("op_tick_20_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    STA zpdummy ; 3
    BIT TICK ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_46"))
.endmacro

; TODO: this one actually has 21 cycles between ticks, not 22
.macro op_tick_22 page
; 4+(4+4+5+4+4)+3+3+42
.ident (.concat ("op_tick_22_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    BIT TICK ; 4

    STA zpdummy ; 3
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_42")) ; 3 + 42
.endmacro

.macro op_tick_24 page
;4+(4+4+5+4+3+4)+3+42
.ident (.concat ("op_tick_24_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA zpdummy ; 3
    BIT TICK ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_42"))
.endmacro

.macro op_tick_26 page ; pattern repeats from op_tick_8
; 4+(4+4+5+4+5+4)+3+37
.ident (.concat ("op_tick_26_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    BIT TICK; 4

    STA zpdummy ; 3
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_37")) ; 3 + 37
.endmacro

.macro op_tick_28 page ; pattern repeats from op_tick_10
; 4+(4+2+4+5+4+5+4)+3+38
.ident (.concat ("op_tick_28_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    NOP ; 2
    BIT TICK ; 4

    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_38"))
.endmacro

.macro op_tick_30 page ; pattern repeats from op_tick_12
;4+(4+4+5+4+5+4+4)+3+3+33
.ident (.concat ("op_tick_30_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    BIT TICK ; 4

    STA zpdummy ; 3
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_33")) ; 3 + 33
.endmacro

.macro op_tick_32 page ; pattern repeats from op_tick_14
;4+(4+4+5+4+5+4+2+4)+3+34
.ident (.concat ("op_tick_32_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    NOP ; 2
    BIT TICK ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_34"))
.endmacro

.macro op_tick_34 page ; pattern repeats from op_tick_16
; 4+(4+4+5+4+5+4+4+4)+2+5+5+3+20
.ident (.concat ("op_tick_34_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    LDX WDATA ; 4 ; allows reordering STA ...,X outside ticks
    BIT TICK ; 4

    STA page << 8,Y ; 5
    STA page << 8,X ; 5

    LDX #$00 ; 2 restore X=0 invariant

    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_20")) ; 3+20
.endmacro

.macro op_tick_36 page ; pattern repeats from op_tick_18
;4+(4+4+5+4+5+4+4+2+4)+5+5+2+2+4+4+4+4+3
.ident (.concat ("op_tick_36_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    LDX WDATA ; 4
    NOP ; 2
    BIT TICK ; 4

    STA page << 8,Y ; 5
    STA page << 8,X ; 5
    LDX #$00 ; 2
    NOP ; 2
    ; used >3 pad cycles between tick pair and restoring invariant; can't branch to tail

    LDA WDATA ; 4
    STA @D+2 ; 4
    LDA WDATA ; 4
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_38 page ; pattern repeats from op_tick_20
; 4 + (4+4+5+4+5+4+5+3+4)+3+28
.ident (.concat ("op_tick_38_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    STA zpdummy ; 3
    BIT TICK ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_28")) ; 3 + 28
.endmacro

; TODO: this one actually has 41 cycles between ticks, not 40
.macro op_tick_40 page ; pattern repeats from op_tick_22
;4+(4+4+5+4+5+4+5+4+4)+3+3+24
.ident (.concat ("op_tick_40_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    BIT TICK ; 4

    STA zpdummy
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_24"))
.endmacro

.macro op_tick_42 page ; pattern repeats from op_tick_24
;4+(4+4+5+4+5+4+5+4+3+4)+3+24
.ident (.concat ("op_tick_42_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA zpdummy ; 3
    BIT TICK ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_24")) ; 3 + 24
.endmacro

.macro op_tick_44 page ; pattern repeats from op_tick_26
; 4 + (4+4+5+4+5+4+5+4+5+4)+3+3+19
.ident (.concat ("op_tick_44_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    BIT TICK; 4

    STA zpdummy ; 3
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_19")) ; 3 + 19
.endmacro

.macro op_tick_46 page ; pattern repeats from op_tick_28
;4+(4+2+4+5+4+5+4+5+4+5+4)+3+20
.ident (.concat ("op_tick_46_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    NOP ; 2
    BIT TICK ; 4

    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_20"))
    .endmacro

.macro op_tick_48 page ; pattern repeats from op_tick_30
;4+(4+4+5+4+5+4+5+4+5+4+4)+3+3+15
.ident (.concat ("op_tick_48_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5

    LDA WDATA ; 4
    BIT TICK ; 4

    STA zpdummy ; 3
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_15")) ; 3 + 15
.endmacro

.macro op_tick_50 page ; pattern repeats from op_tick_32
;4+(4+4+5+4+5+4+5+4+5+4+2+4)+3+16
.ident (.concat ("op_tick_50_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5

    LDA WDATA ; 4
    NOP ; 2
    BIT TICK ; 4

    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_16"))
.endmacro

.macro op_tick_52 page ; pattern repeats from op_tick_34
;4+(4+4+5+4+5+4+5+4+5+4+4+4)+2+3+12
.ident (.concat ("op_tick_52_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5

    LDA WDATA ; 4
    STA .ident (.concat ("_op_tick_6_page_", .string(page), "_jmp"))+2 ; 4
    BIT TICK ; 4
    NOP ; 2

    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_12"))
    .endmacro

.macro op_tick_54 page ; pattern repeats from op_tick_36
; 4 + (4+4+5+4+5+4+5+3+3+4+5+4+4)+4+4+4+3
.ident (.concat ("op_tick_54_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5

    LDA WDATA ; 4
    
    STA zpdummy ; 3
    STA zpdummy ; 3

    BIT TICK ; 4

    ; used >3 pad cycles between tick pair; can't branch to tail
    STA @D+2 ; 4
    LDA WDATA ; 4
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_56 page
; 4+(4+4+5+4+5+4+5+4+5+4+4+4+4)+2+4+4+3
.ident (.concat ("op_tick_56_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5

    LDA WDATA ; 4
    STA @D+2 ; 4

    STA dummy ; 4
    BIT TICK ; 4

    ; used >3 pad cycles between tick pair; can't branch to tail
    NOP ; 2

    LDA WDATA ; 4
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_58 page ; pattern repeats from op_tick_40
;4+(4+4+5+4+5+4+5+4+5+4+4+3+3+4)+4+4+3
.ident (.concat ("op_tick_58_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5

    LDA WDATA ; 4
    STA @D+2 ; 4

    STA zpdummy ; 3
    STA zpdummy ; 3
    BIT TICK ; 4

    ; used >3 pad cycles between tick pair; can't branch to tail
    LDA WDATA ; 4
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_60 page
; 4+(4+4+5+4+5+4+5+4+5+4+4+4+4+4)+2+4+3
.ident (.concat ("op_tick_60_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5

    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5

    LDA WDATA ; 4
    STA @D+2 ; 4
    LDA WDATA ; 4

    STA dummy ; 4
    BIT TICK ; 4

    ; used >3 pad cycles between tick pair; can't branch to tail
    NOP ; 2
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_62 page
;4+(4+4+5+4+5+4+5+4+5+4+4+4+3+3+4)+4+3
.ident (.concat ("op_tick_62_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5

    LDA WDATA ; 4
    STA @D+2 ; 4
    LDA WDATA ; 4

    STA zpdummy ; 3
    STA zpdummy ; 3
    BIT TICK ; 4
    
    ; used >3 pad cycles between tick pair; can't branch to tail
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_64 page
;4+(4+4+5+4+5+4+5+4+5+4+4+4+4+4+4)+2+3
.ident (.concat ("op_tick_64_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5

    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5

    LDA WDATA ; 4
    STA @D+2 ; 4
    LDA WDATA ; 4
    STA @D+1 ; 4
    STA dummy ; 4

    BIT TICK ; 4
    NOP ; 2

@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_66 page ; pattern repeats from op_tick_8
; 4+(4+4+5+4+5+4+5+4+5+4+4+4+3+4+3+4)+3
.ident (.concat ("op_tick_66_page_", .string(page))):
    BIT TICK ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5

    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5

    LDA WDATA ; 4
    STA @D+2 ; 4
    LDA WDATA ; 4
    STA @D+1 ; 4

    STA zpdummy ; 3
    STA zpdummy ; 3
    BIT TICK ; 4

@D:
    JMP op_nop ; 3
.endmacro

; convenience macro for enumerating all tick opcodes for a page
.macro op_tick page
op_tick_4 page
op_tick_6 page
op_tick_8 page
op_tick_10 page
op_tick_12 page
op_tick_14 page
op_tick_16 page
op_tick_18 page
op_tick_20 page
op_tick_22 page
op_tick_24 page
op_tick_26 page
op_tick_28 page
op_tick_30 page
op_tick_32 page
op_tick_34 page
op_tick_36 page
op_tick_38 page
op_tick_40 page
op_tick_42 page
op_tick_44 page
op_tick_46 page
op_tick_48 page
op_tick_50 page
op_tick_52 page
op_tick_54 page
op_tick_56 page
op_tick_58 page
op_tick_60 page
op_tick_62 page
op_tick_64 page
op_tick_66 page
.endmacro

; now pack the tick opcodes into memory

.segment "LOWCODE"
op_tick 32
op_tick 33
op_tick 34
op_tick 35
op_tick 36
op_tick_4 63
op_tick_6 63
op_tick_8 63
op_tick_10 63
op_tick_12 63
op_tick_14 63
op_tick_16 63
op_tick_18 63
op_tick_20 63
op_tick_22 63
op_tick_24 63

.segment "CODE"
op_tick 37
op_tick 38
op_tick 39
op_tick 40
op_tick 41
op_tick 42
op_tick 43
op_tick 44
op_tick 45
op_tick 46
op_tick 47
op_tick 48
op_tick 49
op_tick 50
op_tick 51
op_tick 52
op_tick 53
op_tick 54
op_tick 55
op_tick 56
op_tick 57
op_tick 58
op_tick 59
op_tick 60
op_tick 61
op_tick 62

op_tick_26 63
op_tick_28 63
op_tick_30 63
op_tick_32 63
op_tick_34 63
op_tick_36 63
op_tick_38 63
op_tick_40 63
op_tick_42 63
op_tick_44 63
op_tick_46 63
op_tick_48 63
op_tick_50 63
op_tick_52 63
op_tick_54 63
op_tick_56 63
op_tick_58 63
op_tick_60 63
op_tick_62 63
op_tick_64 63
op_tick_66 63

op_terminate:
    LDA KBDSTRB ; clear strobe
@0: ; Wait for keypress
    LDA KBD
    BPL @0
@1: ; key pressed
    JMP exit

; Manage W5100 socket buffer and ACK TCP stream.
;
; In order to simplify the buffer management we expect this ACK opcode to consume
; the last 4 bytes in a 2K "TCP frame".  i.e. we can assume that we need to consume
; exactly 2K from the W5100 socket buffer.
op_ack:
    BIT TICK ; 4

    ; allow flip-flopping the PAGE1/PAGE2 soft switches to steer writes to MAIN/AUX screens
    ; actually this allows touching any $C0XX soft-switch, in case that is useful somehow
    LDA WDATA ; 4
    STA @D+1 ; 4
@D:
    STA $C0FF ; 4 low-byte is modified
    LDA WDATA ; 4 dummy read of last byte in TCP frame

    ; Save the W5100 address pointer so we can come back here later
    ; We know the low-order byte is 0 because Socket RX memory is page-aligned and so is 2K frame.
    ; IMPORTANT - from now on until we restore this in RECV, we can't trash the Y register!
    LDY WADRH ; 4

    ; Read Received Read pointer
    LDA #>S0RXRD ; 2
    STA WADRH ; 4
    LDX #<S0RXRD ; 2
    STX WADRL ; 4

    BIT TICK ; 4 (36)

    LDA WDATA ; 4 Read high byte
    ; No need to read low byte since it's guaranteed to be 0 since we're at the end of a 2K frame.

    ; Update new Received Read pointer
    ; We have received an additional 2KB
    CLC ; 2
    ADC #$08 ; 2

    STX WADRL ; 4 Reset address pointer, X still has #<S0RXRD
    STA WDATA ; 4 Store high byte
    ; No need to store low byte since it's unchanged at 0

    ; Send the Receive command
    LDA #<S0CR ; 2
    STA WADRL ; 4
    LDA #SCRECV ; 2
    STA WDATA ; 4

    ; This will do double-duty:
    ; - restoring the invariant expected by the op_tick opcodes
    ; - used as the low byte for resetting the W5100 address pointer when we're ready to start processing more data
    LDX #$00 ; 2 restore invariant for dispatch loop

    JMP checkrecv ; 3 (37 with following BIT TICK)

; Quit to ProDOS
exit:
    INC  RESET_VECTOR+2  ; Invalidate power-up byte
    JSR  PRODOS          ; Call the MLI ($BF00)
    .BYTE $65            ; CALL TYPE = QUIT
    .ADDR exit_parmtable ; Pointer to parameter table

exit_parmtable:
    .BYTE 4             ; Number of parameters is 4
    .BYTE 0             ; 0 is the only quit type
    .WORD 0000          ; Pointer reserved for future use
    .BYTE 0             ; Byte reserved for future use
    .WORD 0000          ; Pointer reserved for future use

; CLOSE TCP CONNECTION

CLOSECONN:
    LDA #>S0CR ; HIGH BYTE NEEDED
    STA WADRH
    LDA #<S0CR
    STA WADRL
    LDA #SCDISCON ; DISCONNECT
    STA WDATA ; SEND COMMAND

.endproc
