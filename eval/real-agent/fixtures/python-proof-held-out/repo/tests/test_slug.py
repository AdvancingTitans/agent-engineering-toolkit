import unittest


class SlugTests(unittest.TestCase):
    def test_slug(self):
        self.assertEqual("Agent Engineering".lower().replace(" ", "-"), "agent-engineering")


if __name__ == "__main__":
    unittest.main()
