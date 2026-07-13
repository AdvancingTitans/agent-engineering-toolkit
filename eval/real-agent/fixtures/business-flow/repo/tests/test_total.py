import unittest


class TotalTests(unittest.TestCase):
    def test_total(self):
        self.assertEqual(sum([19, 23]), 42)


if __name__ == "__main__":
    unittest.main()
