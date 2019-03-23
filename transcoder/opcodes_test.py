"""Tests for the opcodes module."""

import unittest

import opcodes


class TestOpcodes(unittest.TestCase):
    def test_equality(self):
        op1 = opcodes.Terminate()
        op2 = opcodes.Terminate()
        self.assertEqual(op1, op2)

        op1 = opcodes.Nop()
        op2 = opcodes.Nop()
        self.assertEqual(op1, op2)

        op1 = opcodes.Ack()
        op2 = opcodes.Ack()
        self.assertEqual(op1, op2)

        op1 = opcodes.Ack()
        op2 = opcodes.Nop()
        self.assertNotEqual(op1, op2)

        op1 = opcodes.TICK_OPCODES[(4, 32)](0xff, [0x01, 0x02, 0x03, 0x04])
        op2 = opcodes.TICK_OPCODES[(4, 32)](0xff, [0x01, 0x02, 0x03, 0x04])
        self.assertEqual(op1, op2)

        # op2 has same payload but different opcode
        op1 = opcodes.TICK_OPCODES[(4, 32)](0xff, [0x01, 0x02, 0x03, 0x04])
        op2 = opcodes.TICK_OPCODES[(6, 32)](0xff, [0x01, 0x02, 0x03, 0x04])
        self.assertNotEqual(op1, op2)

        # op2 has different content byte
        op1 = opcodes.TICK_OPCODES[(4, 32)](0xff, [0x01, 0x02, 0x03, 0x04])
        op2 = opcodes.TICK_OPCODES[(4, 32)](0xfe, [0x01, 0x02, 0x03, 0x04])
        self.assertNotEqual(op1, op2)

        # op2 has different offsets
        op1 = opcodes.TICK_OPCODES[(4, 32)](0xff, [0x01, 0x02, 0x03, 0x04])
        op2 = opcodes.TICK_OPCODES[(4, 32)](0xff, [0x01, 0x02, 0x03, 0x05])
        self.assertNotEqual(op1, op2)


if __name__ == '__main__':
    unittest.main()
