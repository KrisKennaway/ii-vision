import subprocess
import sys


import apple2
import uthernet

def main():
    stream = open("out.bin", "rb").read()
    uth = uthernet.Uthernet(stream)
    a2 = apple2.AppleII(uth)

    # Read in Apple IIE ROM image
    rom = open("simulator/APPLE2E.ROM", "rb").read()

    # TODO: other slot ROMs; alternate Cx ROMs

    # Slot 6 ROM
    a2.memory.write(0xc600, rom[0x0600:0x6ff])

    # Main ROM
    a2.memory.write(0xd000, rom[0x5000:0x7fff])

    # Load video player

    # Extract ethernet.bin from disk image
    cmd = "java -jar ethernet/ethernet/make/AppleCommander.jar -g " \
          "ethernet/ethernet/ethernet.dsk ethernet " \
          "ethernet/ethernet/ethernet.bin"
    p = subprocess.run(cmd.split())
    if p.returncode:
        sys.exit(1)

    load_addr = 0x8000
    with open("ethernet/ethernet/ethernet.bin", "rb") as f:
        code = f.read()
    a2.memory.write(load_addr, code)

    # COUT vector
    a2.memory[0x36] = 0xf0
    a2.memory[0x37] = 0xfd

    a2.memory_manager.enable()

    # TODO: why does this not use the 6502 reset vector?
    a2.cpu.reset()

    a2.Run(load_addr, trace=True)

if __name__ == "__main__":
    main()
