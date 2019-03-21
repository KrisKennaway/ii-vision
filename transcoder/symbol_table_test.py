import io
import unittest

import symbol_table

DEBUG_FILE = """
version major=2,minor=0
info    csym=0,file=594,lib=1,line=420,mod=2,scope=2,seg=7,span=255,sym=151,type=5
file    id=0,name="main.s",size=10297,mtime=0x5C766D92,mod=0
file    id=1,name="/usr/local/share/cc65/asminc/apple2.inc",size=2348,mtime=0x5AA06221,mod=0
file    id=2,name="apple2/exehdr.s",size=1848,mtime=0x5AA06221,mod=1
lib     id=0,name="/usr/local/share/cc65/lib/apple2enh.lib"
line    id=0,file=1,line=60
[...]
sym     id=8,name="op_ack",addrsize=absolute,scope=1,def=195,val=0x81FA,type=lab
sym     id=10,name="op_tick",addrsize=absolute,scope=1,def=6,val=0x81EE,type=lab
sym     id=12,name="rle1",addrsize=absolute,scope=1,def=135,ref=373,val=0x81D6,type=lab
[...]
"""


class TestSymbolTable(unittest.TestCase):
    def test_parse(self):
        dbg = io.StringIO(DEBUG_FILE)
        s = symbol_table.SymbolTable()
        self.assertEqual(
            {"\"op_ack\"", "\"op_tick\"", "\"rle1\""}, s.parse(dbg).keys())


if __name__ == '__main__':
    unittest.main()
