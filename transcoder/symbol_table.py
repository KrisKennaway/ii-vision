"""Parses the cc65 .dbg output to extract symbol addresses."""

from typing import Dict, TextIO


class SymbolTable:
    """Parse cc65 debug file to extract symbol table."""

    def __init__(self, debugfile: str = None):
        self.debugfile = debugfile  # type: str

    def parse(self, iostream: TextIO = None) -> Dict:
        """

        :param iostream:
        :return:
        """
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
