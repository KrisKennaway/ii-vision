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
; This is sufficient for ~7.5 full page redraws of the hires screen per second, although the
; effective frame rate is typically higher, when there are only partial changes between
; frames.
;
; Fitting this in 64K together with ProDOS is pretty tight.  We make use of 3 memory
; segments:
;
; LOWCODE (0x800 - 0x1fff)
; HGR (0x2000 - 0x3fff): code needed only at startup, which will be erased as soon as we start playing a video
; CODE (0x4000 - 0xbaff): rest of main memory unused by ProDOS

.include "apple2.inc"

; Write symbol table to .dbg file, so that we can read opcode offsets in the video
; transcoder.
.DEBUGINFO

.proc main

hgr = $f3e2
fullscr = $c052
tick = $c030 ; where the magic happens

; some dummy addresses in order to pad cycle counts
zpdummy = $00
dummy = $ffff

; TODO: make slot I/O addresses customizable

; SLOT 1 I/O ADDRESSES FOR THE W5100
WMODE = $C094
WADRH = $C095
WADRL = $C096
WDATA = $C097

; W5100 LOCATIONS
MACADDR  =   $0009    ; MAC ADDRESS
SRCIP    =   $000F    ; SOURCE IP ADDRESS
RMSR     =   $001A    ; RECEIVE BUFFER SIZE

; SOCKET 0 LOCATIONS
S0MR = $0400  ; SOCKET 0 MODE REGISTER
S0CR = $0401  ; COMMAND REGISTER
S0IR = $0402  ; INTERRUPT REGISTER
S0SR = $0403  ; STATUS REGISTER
S0LOCALPORT = $0404   ; LOCAL PORT
S0FORADDR =  $040C    ; FOREIGN ADDRESS
S0FORPORT =  $0410    ; FOREIGN PORT
S0MSS    =   $0412    ; MAX SEGMENT SIZE
S0PROTO  =   $0414    ; IP PROTOCOL
S0TOS    =   $0415    ; DS/ECN (FORMER TOS)
S0TTL    =   $0416    ; IP TIME TO LIVE
S0TXFSR  =   $0420    ; TX FREE SIZE REGISTER
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
SCLISTEN =   $02  ; LISTEN
SCCONNECT =  $04  ; CONNECT
SCDISCON =   $08  ; DISCONNECT
SCCLOSE  =   $10  ; CLOSE
SCSEND   =   $20  ; SEND
SCSENDMAC =  $21  ; SEND MAC
SCSENDKEEP = $22  ; SEND KEEP ALIVE
SCRECV   =   $40  ; RECV

; SOCKET STATUS
STCLOSED =   $00
STINIT   =   $13
STLISTEN =   $14
STESTABLISHED = $17
STCLOSEWAIT = $1C
STUDP    =   $22
STIPRAW  =   $32
STMAXRAW =   $42
STPPOE   =   $5F

; MONITOR SUBROUTINES
KBD      =   $C000
KBDSTRB  =   $C010
COUT     =   $FDED
PRBYTE   =   $FDDA
PRNTAX   =   $F941

; ZERO-PAGE STORAGE
PTR      =   $06  ; TODO: we only use this for connection retry count
GETSIZE  =   $08  ; 2 BYTES FOR RX_RSR
GETOFFSET =  $0A  ; 2 BYTES FOR OFFSET ADDR
GETSTARTADR = $0C ; 2 BYTES FOR PHYSICAL ADDR

; this is the main binary entrypoint (it will be linked at 0x800)
.segment "LOWCODE"
    JMP bootstrap

; Put code only needed at startup in the HGR page, we'll toast it when we're
; done starting up
.segment "HGR"

; TODO: make these configurable
SRCADDR:  .byte   $C0,$A8,$01,147   ; 192.168.2.5  W5100 IP
FADDR:    .byte   $C0,$A8,$01,15   ; 192.168.2.1   FOREIGN IP
FPORT:    .byte   $4E,$20       ; 20000 FOREIGN PORT
MAC:      .byte   $00,$08,$DC,$01,$02,$03    ; W5100 MAC ADDRESS

; RESET AND CONFIGURE W5100
bootstrap:
    LDA   #6    ; 5 RETRIES TO GET CONNECTION
    STA   PTR   ; NUMBER OF RETRIES

RESET:
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
    BEQ SETUP ; SUCCESS
    BNE CHECKTEST

FAILED:
    DEC PTR
    BEQ ERRDONE ; TOO MANY FAILURES
    LDA #$AE    ; "."
    JSR COUT
    JMP RESET ; TRY AGAIN

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

SETUP:
    JMP init_mainloop

.segment "CODE"
init_mainloop:
    JSR hgr ; nukes the startup code we placed in HGR segment
    STA fullscr

    ; establish invariant expected by decode loop
    LDX #$00

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
; op_tick_36_* opcodes), without much work needed to optimize this. I'm pretty sure there's
; still "unnecessary" work being done (e.g. low address bytes that are always 0) but there's
; need to work harder since we'd end up having to pad them back anyway.
;
; With a 73 cycle fundamental opcode (speaker) period and 1MHz clock speed, this gives a
; 14364 Hz "carrier" for the audio DAC, which is slightly audible (at least to my ageing
; ears) but quite acceptable.
;
; i.e. we get about 14364 player opcodes/second, with the ACK "slow path" costing 6 opcodes.
; Each of the "fat" audio/video opcodes results in storing 4 video bytes, so we store
; about 56KB of video data per second.
;
; With 192x40 = 7680 visible bytes on the hires screen, this means we can do about 7.5 full
; page redraws/sec; but the effective frame rate will usually be much higher than this
; since we only prioritize the parts of the screen that are changing between frames.

; Check for any received data
CHECKRECV:
    BIT tick        ; 4

    LDA #<S0RXRSR   ; 2 S0 RECEIVED SIZE REGISTER
    STA WADRL       ; 4
    LDA WDATA       ; 4 HIGH BYTE OF RECEIVED SIZE
    ORA WDATA       ; 4 LOW BYTE
    BNE RECV        ; 2 THERE IS DATA

    ; Not sure whether this delay is needed?
    NOP ; Little delay ...
    NOP
    JMP CHECKRECV   ; Check again

; THERE IS DATA TO READ - COMPUTE THE PHYSICAL ADDRESS
RECV:
    LDA #<S0RXRSR ; 2 GET RECEIVED SIZE AGAIN
    STA WADRL ; 4
    LDA WDATA ; 4

    ; expect at least 2k more data present.  The decoder does not do any implicit management
    ; of the TCP socket buffer, unless instructed to by the video byte stream.  This
    ; opcode is scheduled every 2k bytes, so we'd better not fall off the end of the stream.
    CMP #$08 ; 2 expect at least 2k
    bcs @L ; 3 branch should mostly be taken, pads out the next tick to 36 cycles
    BCC CHECKRECV ; not yet

@L:
    BIT tick ; 4 (36 cycles)

    STA GETSIZE+1 ; 4
    LDA WDATA ; 4
    STA GETSIZE ; 4 low byte (this should be 0 i.e. we could optimize this away, but we dont need to bother because the cycle timings work out anyway)

; reset address pointer to socket buffer
; CALCULATE OFFSET ADDRESS USING READ POINTER AND RX MASK
    LDA #<S0RXRD ; 2
    STA WADRL ; 4

    LDA WDATA ; 4 HIGH BYTE
    AND #>RXMASK ; 2
    STA GETOFFSET+1,X ; 5 - using X=0 to get an extra cycle before next tick
    LDA WDATA ; 4 LOW BYTE

    BIT tick ; 4 (37 cycles)
    AND #<RXMASK ; 2

    STA GETOFFSET ; 4

    ; CALCULATE PHYSICAL ADDRESS WITHIN W5100 RX BUFFER
    CLC ; 2
    LDA GETOFFSET ; 4
    ADC #<RXBASE ; 2
    STA GETSTARTADR ; 4

    LDA GETOFFSET+1 ; 4
    ADC #>RXBASE ; 2
    STA GETSTARTADR+1 ; 4

    ; SET BUFFER ADDRESS ON W5100
    LDA GETSTARTADR+1 ; 4 HIGH BYTE FIRST

    BIT tick ; 4 (36)
    STA WADRH ;4

    LDA GETSTARTADR ; 4
    STA WADRL ; 4

    ; ensure invariant expected by inner loop
    ; it's probably already fine, but we have 2 cycles to spare anyway ;)
    LDX #$00 ; 2

    ; fall through to op_nop

op_nop:
    LDY WDATA ; 4
    STY @D+2 ; 4
    LDY WDATA ; 4
    STY @D+1 ; 4
@D:
    JMP op_nop ; 3 ; 37 with following tick

; Build macros for "fat" opcodes that do the following:
; - tick twice, N cycles apart (N = 4 .. 66 in steps of 2)
; - read a content byte from the stream
; - have an opcode-specific page offset configured (e.g. STA $2000,Y)
; - read 4 page offsets from the stream
; - store the content byte at these offsets
; - read 2 bytes from the stream as address of next opcode
;
; Each opcode has 6 cycles of padding, which is necessary to support reordering things to
; get the second "BIT tick" at the right cycle offset.
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
    BIT tick ; 4
    BIT tick ; 4

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
    BIT tick ; 4
    NOP ; 2
    BIT tick ; 4

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
    BIT tick ; 4
    LDA WDATA ; 4
    BIT tick ; 4

    STA zpdummy ; 3
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_55")) ; 3 + 55
.endmacro

.macro op_tick_10 page
;4+(4+2+4)+3+56
.ident (.concat ("op_tick_10_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    NOP ; 2
    BIT tick ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_56")) ; 3 + 56
.endmacro

.macro op_tick_12 page
;4+(4+4+4)+3+3+51
.ident (.concat ("op_tick_12_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    BIT tick ; 4

    STA zpdummy ; 3
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_51")) ; 3 + 51
.endmacro

.macro op_tick_14 page
;4+(4+4+2+4)+3+52
.ident (.concat ("op_tick_14_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    NOP ; 2
    BIT tick ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_52")) ; 3+52
.endmacro

.macro op_tick_16 page
; 4+(4+4+4+4)+5+2+3+43
.ident (.concat ("op_tick_16_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    ; This temporarily violates X=0 invariant required by tick_6, but lets us share a
    ; common opcode tail; otherwise we need a dummy 4-cycle opcode between the ticks, which
    ; doesn't leave enough to JMP with.
    LDX WDATA ; 4
    LDY WDATA ; 4
    BIT tick ; 4
    
    STA page << 8,x ; 5
    LDX #$00 ; 2 restore X=0 invariant

    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_43")) ; 3 + 43
.endmacro

.macro op_tick_18 page
; 4 + (4+4+4+2+4)+5+5+2+2+4+5+4+5+4+4+4+4+3
.ident (.concat ("op_tick_18_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    ; lets us reorder the 5-cycle STA page << 8,y outside of tick loop.
    ; This temporarily violates X=0 invariant required by tick_6
    LDX WDATA ; 4
    NOP ; 2
    BIT tick ; 4

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
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    STA zpdummy ; 3
    BIT tick ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_46"))
.endmacro

; TODO: this one actually has 21 cycles between ticks, not 22
.macro op_tick_22 page
; 4+(4+4+5+4+4)+3+3+42
.ident (.concat ("op_tick_22_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    BIT tick ; 4

    STA zpdummy ; 3
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_42")) ; 3 + 42
.endmacro

.macro op_tick_24 page
;4+(4+4+5+4+3+4)+3+42
.ident (.concat ("op_tick_24_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA zpdummy ; 3
    BIT tick ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_42"))
.endmacro

.macro op_tick_26 page ; pattern repeats from op_tick_8
; 4+(4+4+5+4+5+4)+3+37
.ident (.concat ("op_tick_26_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    BIT tick; 4

    STA zpdummy ; 3
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_37")) ; 3 + 37
.endmacro

.macro op_tick_28 page ; pattern repeats from op_tick_10
; 4+(4+2+4+5+4+5+4)+3+38
.ident (.concat ("op_tick_28_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    NOP ; 2
    BIT tick ; 4

    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_38"))
.endmacro

.macro op_tick_30 page ; pattern repeats from op_tick_12
;4+(4+4+5+4+5+4+4)+3+3+33
.ident (.concat ("op_tick_30_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    BIT tick ; 4

    STA zpdummy ; 3
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_33")) ; 3 + 33
.endmacro

.macro op_tick_32 page ; pattern repeats from op_tick_14
;4+(4+4+5+4+5+4+2+4)+3+34
.ident (.concat ("op_tick_32_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    NOP ; 2
    BIT tick ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_34"))
.endmacro

.macro op_tick_34 page ; pattern repeats from op_tick_16
; 4+(4+4+5+4+5+4+4+4)+2+5+5+3+20
.ident (.concat ("op_tick_34_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    LDX WDATA ; 4 ; allows reordering STA ...,X outside ticks
    BIT tick ; 4

    STA page << 8,Y ; 5
    STA page << 8,X ; 5

    LDX #$00 ; 2 restore X=0 invariant

    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_20")) ; 3+20
.endmacro

.macro op_tick_36 page ; pattern repeats from op_tick_18
;4+(4+4+5+4+5+4+4+2+4)+5+5+2+2+4+4+4+4+3
.ident (.concat ("op_tick_36_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    LDX WDATA ; 4
    NOP ; 2
    BIT tick ; 4

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
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    STA zpdummy ; 3
    BIT tick ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_28")) ; 3 + 28
.endmacro

; TODO: this one actually has 41 cycles between ticks, not 40
.macro op_tick_40 page ; pattern repeats from op_tick_22
;4+(4+4+5+4+5+4+5+4+4)+3+3+24
.ident (.concat ("op_tick_40_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    BIT tick ; 4

    STA zpdummy
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_24"))
.endmacro

.macro op_tick_42 page ; pattern repeats from op_tick_24
;4+(4+4+5+4+5+4+5+4+3+4)+3+24
.ident (.concat ("op_tick_42_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA zpdummy ; 3
    BIT tick ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_24")) ; 3 + 24
.endmacro

.macro op_tick_44 page ; pattern repeats from op_tick_26
; 4 + (4+4+5+4+5+4+5+4+5+4)+3+3+19
.ident (.concat ("op_tick_44_page_", .string(page))):
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    BIT tick; 4

    STA zpdummy ; 3
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_19")) ; 3 + 19
.endmacro

.macro op_tick_46 page ; pattern repeats from op_tick_28
;4+(4+2+4+5+4+5+4+5+4+5+4)+3+20
.ident (.concat ("op_tick_46_page_", .string(page))):
    BIT tick ; 4
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
    BIT tick ; 4

    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_20"))
    .endmacro

.macro op_tick_48 page ; pattern repeats from op_tick_30
;4+(4+4+5+4+5+4+5+4+5+4+4)+3+3+15
.ident (.concat ("op_tick_48_page_", .string(page))):
    BIT tick ; 4
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
    BIT tick ; 4

    STA zpdummy ; 3
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_15")) ; 3 + 15
.endmacro

.macro op_tick_50 page ; pattern repeats from op_tick_32
;4+(4+4+5+4+5+4+5+4+5+4+2+4)+3+16
.ident (.concat ("op_tick_50_page_", .string(page))):
    BIT tick ; 4
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
    BIT tick ; 4

    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_16"))
.endmacro

.macro op_tick_52 page ; pattern repeats from op_tick_34
;4+(4+4+5+4+5+4+5+4+5+4+4+4)+2+3+12
.ident (.concat ("op_tick_52_page_", .string(page))):
    BIT tick ; 4
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
    BIT tick ; 4
    NOP ; 2

    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_12"))
    .endmacro

.macro op_tick_54 page ; pattern repeats from op_tick_36
; 4 + (4+4+5+4+5+4+5+3+3+4+5+4+4)+4+4+4+3
.ident (.concat ("op_tick_54_page_", .string(page))):
    BIT tick ; 4
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

    BIT tick ; 4

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
    BIT tick ; 4
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
    BIT tick ; 4

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
    BIT tick ; 4
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
    BIT tick ; 4

    ; used >3 pad cycles between tick pair; can't branch to tail
    LDA WDATA ; 4
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_60 page
; 4+(4+4+5+4+5+4+5+4+5+4+4+4+4+4)+2+4+3
.ident (.concat ("op_tick_60_page_", .string(page))):
    BIT tick ; 4
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
    BIT tick ; 4

    ; used >3 pad cycles between tick pair; can't branch to tail
    NOP ; 2
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_62 page
;4+(4+4+5+4+5+4+5+4+5+4+4+4+3+3+4)+4+3
.ident (.concat ("op_tick_62_page_", .string(page))):
    BIT tick ; 4
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
    BIT tick ; 4
    
    ; used >3 pad cycles between tick pair; can't branch to tail
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_64 page
;4+(4+4+5+4+5+4+5+4+5+4+4+4+4+4+4)+2+3
.ident (.concat ("op_tick_64_page_", .string(page))):
    BIT tick ; 4
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

    BIT tick ; 4
    NOP ; 2

@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_66 page ; pattern repeats from op_tick_8
; 4+(4+4+5+4+5+4+5+4+5+4+4+4+3+4+3+4)+3
.ident (.concat ("op_tick_66_page_", .string(page))):
    BIT tick ; 4
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
    BIT tick ; 4

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

; Manage W5100 socket buffer and ACK TCP stream.
;
; In order to simplify the buffer management we expect this ACK opcode to consume
; the last 4 bytes in a 2K "TCP frame".  i.e. we can assume that we need to consume
; exactly 2K from the W5100 socket buffer.
op_ack:
    BIT tick ; 4

    LDA WDATA ; 4 dummy read of second-last byte in TCP frame
    LDA WDATA ; 4 dummy read of last byte in TCP frame

    CLC ; 2
    LDA #>S0RXRD ; 2 NEED HIGH BYTE HERE
    STA WADRH ; 4
    LDA #<S0RXRD ; 2

    STA WADRL ; 4
    LDA WDATA ; 4 HIGH BYTE
    LDX WDATA ; 4 LOW BYTE ; not sure if needed -- but we have cycles to spare so who cares!

    ADC #$08 ; 2 ADD HIGH BYTE OF RECEIVED SIZE
    BIT tick ; 4 (36)
    TAY ; 2 SAVE

    LDA #<S0RXRD ; 2
    STA WADRL ; 4 Might not be needed, but have cycles to spare

    STY WDATA ; 4 SEND HIGH BYTE
    STX WDATA ; 4 SEND LOW BYTE

; SEND THE RECV COMMAND
    LDA #<S0CR ; 2
    STA WADRL ; 4
    LDA #SCRECV ; 2
    STA WDATA ; 4

    NOP ; 2 ; see, we even have cycles left over!

    JMP CHECKRECV ; 3 (37 with following BIT tick)

; CLOSE TCP CONNECTION

CLOSECONN:
    LDA #>S0CR ; HIGH BYTE NEEDED
    STA WADRH
    LDA #<S0CR
    STA WADRL
    LDA #SCDISCON ; DISCONNECT
    STA WDATA ; SEND COMMAND

; CHECK FOR CLOSED STATUS

;CHECKCLOSED:
;    LDX #0
;@L:
;    LDA #<S0SR
;    STA WADRL
;    LDA WDATA
;    BEQ ISCLOSED
;    NOP
;    NOP
;    NOP
;    INX
;    BNE @L  ; DON'T WAIT FOREVER
;ISCLOSED:
;    RTS ; SOCKET IS CLOSED

.endproc
