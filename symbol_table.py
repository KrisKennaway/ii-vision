from typing import Dict


class SymbolTable:
    """Parse cc65 debug file to extract symbol table."""

    def __init__(self, debugfile: str = None):
        self.debugfile = debugfile

    def parse(self, iostream=None) -> Dict:
        syms = {}

        if not iostream:
            iostream = open(self.debugfile, "r")

        with iostream as f:
            for line in f.read().split("\n"):
                if not line.startswith("sym"):
                    continue

                sym = {}
                data = line.split()[1].split(",")
                for kv in data:
                    k, v = kv.split("=")
                    sym[k] = v

                name = sym["name"]

                syms[name] = sym

        return syms
