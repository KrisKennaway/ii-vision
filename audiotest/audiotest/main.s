;
;  main.s
;  audiotest
;
;  Created by Kris Kennaway on 07/01/2019.
;  Copyright © 2019 Kris Kennaway. All rights reserved.
;

.include "apple2.inc"

.proc main

TICK = $c030

; some dummy addresses in order to pad cycle counts
zpdummy = $00
dummy = $ffff

; Write symbol table to object file
.DEBUGINFO

; TCP SOCKET DEMO FOR W5100/UTHERNET II
; BY D. FINNIGAN
; OCTOBER 2015
;
; UPDATED 09 JAN 2016 6*
; UPDATED 13 FEB 2017, C. TORRENCE
;  -REMOVED SEPARATE PATH FOR WRAP, ADD DEBUG PRINT

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
PTR      =   $06  ; 2 BYTES FOR APPLE BUFFER
GETSIZE  =   $08  ; 2 BYTES FOR RX_RSR
GETOFFSET =  $0A  ; 2 BYTES FOR OFFSET ADDR
GETSTARTADR = $0C ; 2 BYTES FOR PHYSICAL ADDR

hgr = $f3e2
gr = $c050
text = $c051
fullscr = $c052
tick = $c030

.segment "LOWCODE"
; RESET AND CONFIGURE W5100
    JMP   RESET

; Put code only needed at startup in the HGR page, we'll toast it when we're
; done starting up
.segment "HGR"

    LDA   #6    ; 5 RETRIES TO GET CONNECTION
    STA   PTR   ; NUMBER OF RETRIES

SRCADDR:  .byte   $C0,$A8,$01,147   ; 192.168.2.5  W5100 IP
FADDR:    .byte   $C0,$A8,$01,15   ; 192.168.2.1   FOREIGN IP
FPORT:    .byte   $4E,$20       ; 20000 FOREIGN PORT
MAC:      .byte   $00,$08,$DC,$01,$02,$03    ; W5100 MAC ADDRESS

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

; SET BUFFER ADDRESS ON APPLE
;    LDA #0 ; LOW BYTE OF BUFFER
;    STA PTR
;    LDA #$50 ; HIGH BYTE
;    STA PTR+1

; init graphics
; default content value
    LDA #$7f
    PHA
    JMP MAINLOOP

.segment "CODE"

MAINLOOP:
    JSR hgr
    STA fullscr

; CHECK FOR ANY RECEIVED DATA

CHECKRECV:
;    BIT KBD ; KEYPRESS?
;    BPL @NEXT
;    LDA KBDSTRB
;    JMP CLOSECONN ; CLOSE CONNECTION

;@NEXT:
    BIT tick ; 4

    LDA #<S0RXRSR ; 2 S0 RECEIVED SIZE REGISTER
    STA WADRL ; 4
    LDA WDATA       ; 4 HIGH BYTE OF RECEIVED SIZE
    ORA WDATA       ; 4 LOW BYTE
    BEQ NORECV      ; 2 NO DATA TO READ

    JMP RECV        ; 3 THERE IS DATA

NORECV:
    ; XXX needed?
    NOP ; LITTLE DELAY ...
    NOP
    

    JMP CHECKRECV   ; CHECK AGAIN

; THERE IS DATA TO READ - COMPUTE THE PHYSICAL ADDRESS

RECV:
    LDA #<S0RXRSR ; 2 GET RECEIVED SIZE AGAIN
    STA WADRL ; 4
    LDA WDATA ; 4

    CMP #$10 ; 2 expect at least 4k
    bcc CHECKRECV ; 2 not yet

    BIT tick ; 4 (37)

    STA GETSIZE+1 ; 4
    LDA WDATA ; 4
    STA GETSIZE ; 4 low byte XXX should be 0

    ;jsr DEBUG

; reset address pointer to socket buffer
; CALCULATE OFFSET ADDRESS USING READ POINTER AND RX MASK
    LDA #<S0RXRD ; 2
    STA WADRL ; 4

    LDA WDATA ; 4 HIGH BYTE
    AND #>RXMASK ; 2
    STA GETOFFSET+1 ; 4
    LDA WDATA ; 4 LOW BYTE
    ; why is this not 0?
    ;BEQ @L    ; XXX assert 0
    ;BRK
@L:
    BIT tick ; 4(36)
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
    ;JSR DEBUG ; UNCOMMENT FOR W5100 DEBUG INFO
    LDA GETSTARTADR+1 ; 4 HIGH BYTE FIRST

    STA WADRH ;4
    BIT tick ; 4 (40)

    LDA GETSTARTADR ; 4
    STA WADRL ; 4

    ; restore content
    PLA ; 4
    ; fall through
    LDX #$00 ; 2

;4 stores:
;- 73 cycles
;- 14364 Hz
;- 57456 stores/sec
;- 7.5 full screen frames/sec
;- 4 .. 70 opcodes = 32 opcodes/page
;- 5 bit DAC
;- 53 bytes/opcode
;- 53*32*32 = 54272 bytes.  Just enough to fit in AUX?
;- 0x800..0x1fff, 0x4000...0xffff = 55294 bytes

; XXX should fall through to op_tick_36?  Since this is the 50% duty cycle case

op_nop:
    LDY WDATA ; 4
    STY @D+2 ; 4
    LDY WDATA ; 4
    STY @D+1 ; 4
@D:
    JMP op_nop ; 3

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
.ident (.concat ("op_tick_6_page_", .string(page))):
;4+(2+4)+3+4+4+5+4+5+4+5+4+5+4+4+4+5+3

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
    ; maintain the invariant X=0 across opcode dispatch
    STA .ident(.concat ("_op_tick_6_page_", .string(page), "_jmp"))+1,x ; 5

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
.ident (.concat ("op_tick_14_page_", .string(page))):
;4+(4+4+2+4)+3+52
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    NOP ; 2
    BIT tick ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_52")) ; 3+52
.endmacro

.macro op_tick_16 page
.ident (.concat ("op_tick_16_page_", .string(page))):
; 4+(4+4+4+4)+5+2+3+43
    BIT tick ; 4
    LDA WDATA ; 4
    ; This lets us share a common opcode tail; otherwise we need a STA dummy 4-cycle opcode
    ; which doesn't leave enough to JMP with.
    ; This temporarily violates X=0 invariant required by tick_6
    LDX WDATA ; 4
    LDY WDATA ; 4
    BIT tick ; 4
    
    STA page << 8,x ; 5
    LDX #$00 ; 2 restore X=0 invariant

    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_43")) ; 3 + 43
.endmacro

.macro op_tick_18 page
.ident (.concat ("op_tick_18_page_", .string(page))):
; 4 + (4+4+4+2+4)+5+5+2+2+4+5+4+5+4+4+4+4+3
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

    ; used >3 pad cycles within tick loop; can't branch to tail
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
.ident (.concat ("op_tick_20_page_", .string(page))):
;4+(4+4+5+3+4)+3+46=73
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    STA zpdummy ; 3
    BIT tick ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_46"))
.endmacro

.macro op_tick_22 page
.ident (.concat ("op_tick_22_page_", .string(page))):
; 4+(4+4+5+4+4)+3+3+42  XXX really tick_21
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
.ident (.concat ("op_tick_24_page_", .string(page))):
;4+(4+4+5+4+3+4)+3+42
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA zpdummy ; 3
    BIT tick ; 4
    
    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_42"))
.endmacro

.macro op_tick_26 page ; repeats from op_tick_8
.ident (.concat ("op_tick_26_page_", .string(page))):
; 4+(4+4+5+4+5+4)+3+37
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

.macro op_tick_28 page ; repeats from op_tick_10
.ident (.concat ("op_tick_28_page_", .string(page))):
; 4+(4+2+4+5+4+5+4)+3+38
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

.macro op_tick_30 page ; repeats from op_tick_12
.ident (.concat ("op_tick_30_page_", .string(page))):
;4+(4+4+5+4+5+4+4)+3+3+33
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

.macro op_tick_32 page ; repeats from op_tick_14
.ident (.concat ("op_tick_32_page_", .string(page))):
;4+(4+4+5+4+5+4+2+4)+3+34
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

.macro op_tick_34 page ; repeats from op_tick_16
.ident (.concat ("op_tick_34_page_", .string(page))):
; 4+(4+4+5+4+5+4+4+4)+2+5+5+3+20
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    STA page << 8,Y ; 5
    LDY WDATA ; 4
    LDX WDATA ; 4
    BIT tick ; 4

    STA page << 8,Y ; 5
    STA page << 8,X ; 5

    LDX #$00 ; 2 restore X=0 invariant

    JMP .ident(.concat("_op_tick_page_", .string(page), "_tail_20")) ; 3+20
.endmacro

.macro op_tick_36 page ; repeats from op_tick_18
.ident (.concat ("op_tick_36_page_", .string(page))):
;4+(4+4+5+4+5+4+4+2+4)+5+5+2+2+4+4+4+4+3
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
    ; used >3 pad cycles within tick loop and restoring invariant; can't branch to tail

    LDA WDATA ; 4
    STA @D+2 ; 4
    LDA WDATA ; 4
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_38 page ; repeats from op_tick_20
.ident (.concat ("op_tick_38_page_", .string(page))):
; 4 + (4+4+5+4+5+4+5+3+4)+3+28
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

.macro op_tick_40 page ; repeats from op_tick_22 ; XXX really tick_41
.ident (.concat ("op_tick_40_page_", .string(page))):
;4+(4+4+5+4+5+4+5+4+4)+3+3+24
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

.macro op_tick_42 page ; repeats from op_tick_24
.ident (.concat ("op_tick_42_page_", .string(page))):
;4+(4+4+5+4+5+4+5+4+3+4)+3+24
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

.macro op_tick_44 page ; repeats from op_tick_26
.ident (.concat ("op_tick_44_page_", .string(page))):
; 4 + (4+4+5+4+5+4+5+4+5+4)+3+3+19
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

.macro op_tick_46 page ; repeats from op_tick_28
.ident (.concat ("op_tick_46_page_", .string(page))):
;4+(4+2+4+5+4+5+4+5+4+5+4)+3+20
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

.macro op_tick_48 page ; repeats from op_tick_30
.ident (.concat ("op_tick_48_page_", .string(page))):
;4+(4+4+5+4+5+4+5+4+5+4+4)+3+3+15
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

.macro op_tick_50 page ; repeats from op_tick_32
.ident (.concat ("op_tick_50_page_", .string(page))):
;4+(4+4+5+4+5+4+5+4+5+4+2+4)+3+16
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

.macro op_tick_52 page ; repeats from op_tick_34
.ident (.concat ("op_tick_52_page_", .string(page))):
;4+(4+4+5+4+5+4+5+4+5+4+4+4)+2+3+12
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

.macro op_tick_54 page ; repeats from op_tick_36
.ident (.concat ("op_tick_54_page_", .string(page))):
; 4 + (4+4+5+4+5+4+5+3+3+4+5+4+4)+4+4+4+3
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

    BIT TICK ; 4

    ; used >3 pad cycles within tick loop; can't branch to tail
    STA @D+2 ; 4
    LDA WDATA ; 4
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_56 page
.ident (.concat ("op_tick_56_page_", .string(page))):
; 4+(4+4+5+4+5+4+5+4+5+4+4+4+4)+2+4+4+3
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

    ; used >3 pad cycles within tick loop; can't branch to tail
    NOP ; 2

    LDA WDATA ; 4
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_58 page ; repeats from op_tick_40
.ident (.concat ("op_tick_58_page_", .string(page))):
;4+(4+4+5+4+5+4+5+4+5+4+4+3+3+4)+4+4+3
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

    ; used >3 pad cycles within tick loop; can't branch to tail
    LDA WDATA ; 4
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_60 page
.ident (.concat ("op_tick_60_page_", .string(page))):
; 4+(4+4+5+4+5+4+5+4+5+4+4+4+4+4)+2+4+3
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

    ; used >3 pad cycles within tick loop; can't branch to tail
    NOP ; 2
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_62 page
.ident (.concat ("op_tick_62_page_", .string(page))):
;4+(4+4+5+4+5+4+5+4+5+4+4+4+3+3+4)+4+3
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
    
    ; used >3 pad cycles within tick loop; can't branch to tail
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
.endmacro

.macro op_tick_64 page
.ident (.concat ("op_tick_64_page_", .string(page))):
;4+(4+4+5+4+5+4+5+4+5+4+4+4+4+4+4)+2+3
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

.macro op_tick_66 page ; repeats from op_tick_8
.ident (.concat ("op_tick_66_page_", .string(page))):
; 4+(4+4+5+4+5+4+5+4+5+4+4+4+3+4+3+4)+3
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

op_ack:
; MOVE ADDRESS POINTER 1 page further in socket buffer
;    LDX WADRH ; socket pointer
;    INX

; UPDATE REXRD TO REFLECT DATA WE JUST READ

; TODO: be careful about which registers we stomp here
; UPDATERXRD:

    BIT tick ; 4

    CLC ; 2
    LDA #>S0RXRD ; 2 NEED HIGH BYTE HERE
    STA WADRH ; 4
    LDA #<S0RXRD ; 2

    STA WADRL ; 4
    LDA WDATA ; 4
    TAY ; 2 SAVE
    LDA WDATA ; 4 LOW BYTE ; needed?  I don't think so
    BEQ @1 ; 3
    BRK
@1:

    ADC #$00 ; 2 GETSIZE ; ADD LOW BYTE OF RECEIVED SIZE

    TAX ; 2 SAVE
    TYA ; 2 GET HIGH BYTE BACK
    ADC #$08 ;2 GETSIZE+1 ; ADD HIGH BYTE OF RECEIVED SIZE
    BIT tick ; 4 (39) ; don't mess with Carry prior to ADC
    TAY ; 2 SAVE


    LDA #<S0RXRD ; 2
    STA WADRL ; 4 XXX already there?

    STY WDATA ; 4 SEND HIGH BYTE
    STX WDATA ; 4 SEND LOW BYTE


; SEND THE RECV COMMAND
    LDA #<S0CR ; 2
    STA WADRL ; 4
    LDA #SCRECV ; 2
    STA WDATA ; 4

    JMP CHECKRECV ; 3 (35 with following BIT TICK)

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

; SUPPORT SUBROUTINE: CLEANOUT
; "CLEANS UP" OUTPUT FOR THE APPLE BY
; SETTING THE HIGH BIT AND DOING SOME SUBSTITUTIONS
;CLEANOUT:
;    ORA #%10000000 ; SET HIGH BIT
;    CMP #$8A ; NEWLINE?
;    BNE @OUT
;    LDA #$8D ; CONVERT TO <CR>
;@OUT:
;    JMP COUT ; THIS WILL DO THE RTS

; DEBUG - PRINT W5100 STARTADR AND SIZE
;DEBUG:
;    LDA #$A0 ; " "
;    JSR COUT
;    LDA #$A4 ; "$"
;    JSR COUT
;    LDA GETOFFSET+1
;    LDX GETOFFSET
;    JSR PRNTAX

;    LDA #$A0 ; " "
;    JSR COUT
;    LDA #$A4 ; "$"
;    JSR COUT
;    LDA GETSTARTADR+1
;    LDX GETSTARTADR
;    JSR PRNTAX

;    LDA #$A0 ; " "
;    JSR COUT
;    LDA #$A4 ; "$"
;   JSR COUT
;LDA GETSIZE+1
;    LDX GETSIZE
;    JSR PRNTAX
;    LDA #$8D
;    JMP COUT ; THIS WILL DO THE RTS

.endproc
