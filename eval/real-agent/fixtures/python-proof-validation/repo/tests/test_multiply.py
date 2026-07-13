import unittest


class MultiplyTests(unittest.TestCase):
    def test_multiplication(self):
        self.assertEqual(6 * 7, 42)


if __name__ == "__main__":
    unittest.main()
