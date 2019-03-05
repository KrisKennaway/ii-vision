;
;  main.s
;  audiotest
;
;  Created by Kris Kennaway on 07/01/2019.
;  Copyright © 2019 Kris Kennaway. All rights reserved.
;

.include "apple2.inc"

.org $0800
.proc main

TICK = $c030

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

; RESET AND CONFIGURE W5100
    LDA   #6    ; 5 RETRIES TO GET CONNECTION
    STA   PTR   ; NUMBER OF RETRIES
    BPL   RESET ; ALWAYS TAKEN

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

    JSR hgr
    STA fullscr

; CHECK FOR ANY RECEIVED DATA

CHECKRECV:
;    BIT KBD ; KEYPRESS?
;    BPL @NEXT
;    LDA KBDSTRB
;    JMP CLOSECONN ; CLOSE CONNECTION

;@NEXT:
    BIT tick

    LDA #<S0RXRSR ; S0 RECEIVED SIZE REGISTER
    STA WADRL
    LDA WDATA       ; HIGH BYTE OF RECEIVED SIZE
    ORA WDATA       ; LOW BYTE
    BEQ NORECV      ; NO DATA TO READ

    JMP RECV        ; THERE IS DATA

NORECV:
    ; XXX needed?
    NOP ; LITTLE DELAY ...
    NOP
    

    JMP CHECKRECV   ; CHECK AGAIN

; THERE IS DATA TO READ - COMPUTE THE PHYSICAL ADDRESS

RECV:
    LDA #<S0RXRSR ; GET RECEIVED SIZE AGAIN
    STA WADRL
    LDA WDATA
    BIT tick
    
    CMP #$10 ; expect at least 4k
    bcc CHECKRECV ; not yet

    STA GETSIZE+1
    LDA WDATA
    STA GETSIZE ; low byte XXX should be 0



    ;jsr DEBUG

; reset address pointer to socket buffer
; CALCULATE OFFSET ADDRESS USING READ POINTER AND RX MASK
    LDA #<S0RXRD
    STA WADRL

    LDA WDATA ; HIGH BYTE
    AND #>RXMASK
    STA GETOFFSET+1
    LDA WDATA ; LOW BYTE
    ; why is this not 0?
    ;BEQ @L    ; XXX assert 0
    ;BRK
@L:
    AND #<RXMASK

    STA GETOFFSET


; CALCULATE PHYSICAL ADDRESS WITHIN W5100 RX BUFFER
    BIT tick

    CLC
    LDA GETOFFSET
    ADC #<RXBASE
    STA GETSTARTADR


    LDA GETOFFSET+1
    ADC #>RXBASE
    STA GETSTARTADR+1

    ; SET BUFFER ADDRESS ON W5100
    ;JSR DEBUG ; UNCOMMENT FOR W5100 DEBUG INFO
    LDA GETSTARTADR+1 ; HIGH BYTE FIRST
    STA WADRH

    LDA GETSTARTADR
    STA WADRL

    ; restore content
    PLA
    ; fall through
    LDX #$00
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
    LDY WDATA
    STY @D+2
    LDY WDATA
    STY @D+1
@D:
    JMP op_nop

;4+(4)+2+4+4+4+5+4+5+4+5+4+5+4+4+4+4+3=73
op_tick_4:
    BIT tick ; 4
    BIT tick ; 4

    STA zpdummy ; 3
    STA zpdummy ; 3

    ; load content byte
_op_tick_tail_59:
    LDA WDATA ; 4

    ; 4 x offset stores
_op_tick_tail_55:
    LDY WDATA ; 4
_op_tick_tail_51:
    STA $2000,Y ; 5
_op_tick_tail_46:
    LDY WDATA ; 4
_op_tick_tail_42:
    STA $2000,Y ; 5
_op_tick_tail_37:
    LDY WDATA ; 4
_op_tick_tail_33:
    STA $2000,Y ; 5
_op_tick_tail_28:
    LDY WDATA ; 4
_op_tick_tail_24:
    STA $2000,Y ; 5

    ; vector to next opcode
_op_tick_tail_19:
    LDA WDATA ; 4
_op_tick_tail_15:
    STA _op_tick_4_jmp+2 ; 4
_op_tick_tail_11:
    LDA WDATA ; 4
_op_tick_tail_7:
    STA _op_tick_4_jmp+1 ; 4
_op_tick_4_jmp:
    JMP op_nop ; 3

;4+(2+4)+3+4+4+5+4+5+4+5+4+5+4+4+4+5+3
op_tick_6:
    BIT tick ; 4
    NOP ; 2
    BIT tick ; 4

    STA zpdummy ; 3

_op_tick_tail_60:
    LDA WDATA ; 4

_op_tick_tail_56:
    LDY WDATA ; 4
_op_tick_tail_52:
    STA $2000,Y ; 5
_op_tick_tail_47:
    LDY WDATA ; 4
_op_tick_tail_43:
    STA $2000,Y ; 5
_op_tick_tail_38:
    LDY WDATA ; 4
_op_tick_tail_34:
    STA $2000,Y ; 5
_op_tick_tail_29:
    LDY WDATA ; 4
_op_tick_tail_25:
    STA $2000,Y ; 5

_op_tick_tail_20:
    LDA WDATA ; 4
_op_tick_tail_16:
    STA _op_tick_6_jmp+2 ; 4
_op_tick_tail_12:
    LDA WDATA ; 4
_op_tick_tail_8:
    ; NB: we use ,X indexing here to get an extra cycle.  This requires us to
    ; maintain the invariant X=0 across opcode dispatch
    STA _op_tick_6_jmp+1,x ; 5
_op_tick_6_jmp:
    JMP op_nop ; 3

;4+(4+4)+3+3+55
op_tick_8:
    BIT tick ; 4
    LDA WDATA ; 4
    BIT tick ; 4

    STA zpdummy ; 3
    JMP _op_tick_tail_55 ; 3 + 55

;4+(4+2+4)+3+56
op_tick_10:
    BIT tick ; 4
    LDA WDATA ; 4
    NOP ; 2
    BIT tick ; 4
    
    JMP _op_tick_tail_56 ; 3 + 56

;4+(4+4+4)+3+3+51
op_tick_12:
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    BIT tick ; 4

    STA zpdummy ; 3
    JMP _op_tick_tail_51 ; 3 + 51

;4+(4+4+2+4)+3+52
op_tick_14:
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    NOP ; 2
    BIT tick ; 4
    
    JMP _op_tick_tail_52 ; 3+52

; 4+(4+4+4+4)+5+2+3+43
op_tick_16:
    BIT tick ; 4
    LDA WDATA ; 4
    ; This lets us share a common opcode tail; otherwise we need a STA dummy 4-cycle opcode
    ; which doesn't leave enough to JMP with.
    ; This temporarily violates X=0 invariant required by tick_6
    LDX WDATA ; 4
    LDY WDATA ; 4
    BIT tick ; 4
    
    STA $2000,x ; 5
    LDX #$00 ; 2 restore X=0 invariant

    JMP _op_tick_tail_43 ; 3 + 43

; 4 + (4+4+4+2+4)+5+5+2+2+4+5+4+5+4+4+4+4+3
op_tick_18:
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    ; lets us reorder the 5-cycle STA $2000,y outside of tick loop.
    ; This temporarily violates X=0 invariant required by tick_6
    LDX WDATA ; 4
    NOP ; 2
    BIT tick ; 4

    STA $2000,Y ; 5
    STA $2000,X ; 5

    LDX #$00 ; 2 restore X=0 invariant

    ; used >3 pad cycles within tick loop; can't branch to tail
    NOP ; 2
    
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5

    ; vector to next opcode
    LDA WDATA ; 4
    STA @D+2 ; 4
    LDA WDATA ; 4
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3
    
;4+(4+4+5+3+4)+3+46=73
op_tick_20:
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    STA zpdummy ; 3
    BIT tick ; 4
    
    JMP _op_tick_tail_46

; 4+(4+4+5+4+4)+3+3+42
op_tick_22: ; XXX really tick_21
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    BIT tick ; 4

    STA zpdummy ; 3
    JMP _op_tick_tail_42 ; 3 + 42

;4+(4+4+5+4+3+4)+3+42
op_tick_24:
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA zpdummy ; 3
    BIT tick ; 4
    
    JMP _op_tick_tail_42

; 4+(4+4+5+4+5+4)+3+37
op_tick_26: ; repeats from op_tick_8
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    BIT tick; 4

    STA zpdummy ; 3
    JMP _op_tick_tail_37 ; 3 + 37

; 4+(4+2+4+5+4+5+4)+3+38
op_tick_28: ; repeats from op_tick_10
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    NOP ; 2
    BIT tick ; 4

    JMP _op_tick_tail_38

;4+(4+4+5+4+5+4+4)+3+3+33
op_tick_30: ; repeats from op_tick_12
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    BIT tick ; 4

    STA zpdummy ; 3
    JMP _op_tick_tail_33 ; 3 + 33

;4+(4+4+5+4+5+4+2+4)+3+34
op_tick_32: ; repeats from op_tick_14
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    NOP ; 2
    BIT tick ; 4
    
    JMP _op_tick_tail_34

op_tick_34: ; repeats from op_tick_16
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA dummy ; 4
    BIT tick ; 4

    ; used >3 pad cycles within tick loop; can't branch to tail
    NOP ; 2

    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5

    LDA WDATA ; 4
    STA @D+2 ; 4
    LDA WDATA ; 4
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3

;4+(4+4+5+4+5+4+4+2+4)+5+5+2+2+4+4+4+4+3
op_tick_36: ; repeats from op_tick_18
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    LDX WDATA ; 4
    NOP ; 2
    BIT tick ; 4

    STA $2000,Y ; 5
    STA $2000,X ; 5
    LDX #$00 ; 2
    NOP ; 2
    ; used >3 pad cycles within tick loop and restoring invariant; can't branch to tail

    LDA WDATA ; 4
    STA @D+2 ; 4
    LDA WDATA ; 4
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3

; 4 + (4+4+5+4+5+4+5+3+4)+3+28
op_tick_38: ; repeats from op_tick_20
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    STA zpdummy ; 3
    BIT tick ; 4
    
    JMP _op_tick_tail_28 ; 3 + 28

;4+(4+4+5+4+5+4+5+4+4)+3+3+24
op_tick_40: ; repeats from op_tick_22 ; XXX really tick_41
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    BIT tick ; 4

    STA zpdummy
    JMP _op_tick_tail_24

;4+(4+4+5+4+5+4+5+4+3+4)+3+24
op_tick_42: ; repeats from op_tick_24
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA zpdummy ; 3
    BIT tick ; 4
    
    JMP _op_tick_tail_24 ; 3 + 24
    
; 4 + (4+4+5+4+5+4+5+4+5+4)+3+3+19
op_tick_44: ; repeats from op_tick_26
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    BIT tick; 4

    STA zpdummy ; 3
    JMP _op_tick_tail_19 ; 3 + 19

;4+(4+2+4+5+4+5+4+5+4+5+4)+3+20
op_tick_46: ; repeats from op_tick_28
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    NOP ; 2
    BIT tick ; 4

    JMP _op_tick_tail_20
    
;4+(4+4+5+4+5+4+5+4+5+4+4)+3+3+15
op_tick_48: ; repeats from op_tick_30
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5

    LDA WDATA ; 4
    BIT tick ; 4

    STA zpdummy ; 3
    JMP _op_tick_tail_15 ; 3 + 15

;4+(4+4+5+4+5+4+5+4+5+4+2+4)+3+16
op_tick_50: ; repeats from op_tick_32
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5

    LDA WDATA ; 4
    NOP ; 2
    BIT tick ; 4
    
    JMP _op_tick_tail_16

;4+(4+4+5+4+5+4+5+4+5+4+4+4)+2+4+4+4+3
op_tick_52: ; repeats from op_tick_34
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5

    LDA WDATA ; 4

    STA dummy ; 4
    BIT tick ; 4

    ; used >3 pad cycles within tick loop; can't branch to tail
    NOP ;2

    STA @D+2 ; 4
    LDA WDATA ; 4
    STA @D+1 ; 4
@D:
    JMP op_nop ; 3

; 4 + (4+4+5+4+5+4+5+3+3+4+5+4+4)+4+4+4+3
op_tick_54: ; repeats from op_tick_36
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5

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

; 4+(4+4+5+4+5+4+5+4+5+4+4+4+4)+2+4+4+3
op_tick_56:
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5

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

;4+(4+4+5+4+5+4+5+4+5+4+4+3+3+4)+4+4+3
op_tick_58: ; repeats from op_tick_40
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5

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

; 4+(4+4+5+4+5+4+5+4+5+4+4+4+4+4)+2+4+3
op_tick_60:
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5

    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5

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

;4+(4+4+5+4+5+4+5+4+5+4+4+4+3+3+4)+4+3
op_tick_62:
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5

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

;4+(4+4+5+4+5+4+5+4+5+4+4+4+4+4+4)+2+3
op_tick_64:
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5

    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5

    LDA WDATA ; 4
    STA @D+2 ; 4
    LDA WDATA ; 4
    STA @D+1 ; 4
    STA dummy ; 4

    BIT tick ; 4
    NOP ; 2

@D:
    JMP op_nop ; 3

; 4+(4+4+5+4+5+4+5+4+5+4+4+4+3+4+3+4)+3
op_tick_66:
    BIT tick ; 4
    LDA WDATA ; 4
    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5

    LDY WDATA ; 4
    STA $2000,Y ; 5
    LDY WDATA ; 4
    STA $2000,Y ; 5

    LDA WDATA ; 4
    STA @D+2 ; 4
    LDA WDATA ; 4
    STA @D+1 ; 4

    STA zpdummy ; 3
    STA zpdummy ; 3
    BIT tick ; 4

@D:
    JMP op_nop ; 3

op_ack:
; MOVE ADDRESS POINTER 1 page further in socket buffer
;    LDX WADRH ; socket pointer
;    INX

; UPDATE REXRD TO REFLECT DATA WE JUST READ

; TODO: be careful about which registers we stomp here
; UPDATERXRD:

    BIT tick

    CLC
    LDA #>S0RXRD ; NEED HIGH BYTE HERE
    STA WADRH
    LDA #<S0RXRD

    STA WADRL
    LDA WDATA
    TAY ; SAVE
    LDA WDATA ; LOW BYTE ; needed?  I don't think so
    BEQ @1
    BRK
@1:

    ADC #$00 ; GETSIZE ; ADD LOW BYTE OF RECEIVED SIZE
    BIT tick

    TAX ; SAVE
    TYA ; GET HIGH BYTE BACK
    ADC #$08 ;GETSIZE+1 ; ADD HIGH BYTE OF RECEIVED SIZE
    TAY ; SAVE


    LDA #<S0RXRD
    STA WADRL ; XXX already there?

    STY WDATA ; SEND HIGH BYTE
    STX WDATA ; SEND LOW BYTE


; SEND THE RECV COMMAND
    LDA #<S0CR
    STA WADRL
    LDA #SCRECV
    STA WDATA

    JMP CHECKRECV

; CLOSE TCP CONNECTION

CLOSECONN:
    LDA #>S0CR ; HIGH BYTE NEEDED
    STA WADRH
    LDA #<S0CR
    STA WADRL
    LDA #SCDISCON ; DISCONNECT
    STA WDATA ; SEND COMMAND

; CHECK FOR CLOSED STATUS

CHECKCLOSED:
    LDX #0
@L:
    LDA #<S0SR
    STA WADRL
    LDA WDATA
    BEQ ISCLOSED
    NOP
    NOP
    NOP
    INX
    BNE @L  ; DON'T WAIT FOREVER
ISCLOSED:
    RTS ; SOCKET IS CLOSED

; SUPPORT SUBROUTINE: CLEANOUT
; "CLEANS UP" OUTPUT FOR THE APPLE BY
; SETTING THE HIGH BIT AND DOING SOME SUBSTITUTIONS
CLEANOUT:
    ORA #%10000000 ; SET HIGH BIT
    CMP #$8A ; NEWLINE?
    BNE @OUT
    LDA #$8D ; CONVERT TO <CR>
@OUT:
    JMP COUT ; THIS WILL DO THE RTS

; DEBUG - PRINT W5100 STARTADR AND SIZE
DEBUG:
    LDA #$A0 ; " "
    JSR COUT
    LDA #$A4 ; "$"
    JSR COUT
    LDA GETOFFSET+1
    LDX GETOFFSET
    JSR PRNTAX

    LDA #$A0 ; " "
    JSR COUT
    LDA #$A4 ; "$"
    JSR COUT
    LDA GETSTARTADR+1
    LDX GETSTARTADR
    JSR PRNTAX

    LDA #$A0 ; " "
    JSR COUT
    LDA #$A4 ; "$"
    JSR COUT
    LDA GETSIZE+1
    LDX GETSIZE
    JSR PRNTAX
    LDA #$8D
    JMP COUT ; THIS WILL DO THE RTS

.endproc
