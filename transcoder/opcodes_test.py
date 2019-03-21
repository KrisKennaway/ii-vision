import unittest

import opcodes


class TestOpcodes(unittest.TestCase):
    def test_equality(self):
        op1 = opcodes.Terminate()
        op2 = opcodes.Terminate()
        self.assertEqual(op1, op2)

        op1 = opcodes.SetPage(0x20)
        op2 = opcodes.SetPage(0x20)
        self.assertEqual(op1, op2)

        op1 = opcodes.SetPage(0x20)
        op2 = opcodes.SetPage(0x21)
        self.assertNotEqual(op1, op2)

        op1 = opcodes.SetPage(0x20)
        op2 = opcodes.Terminate()
        self.assertNotEqual(op1, op2)


if __name__ == '__main__':
    unittest.main()
