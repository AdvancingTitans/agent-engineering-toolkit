import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/growth"))

from verify_social_preview import verify


class SocialPreviewTests(unittest.TestCase):
    def test_current_preview_passes(self) -> None:
        self.assertEqual(verify(ROOT / "site/assets/social-preview.png"), [])

    def test_rejects_corrupt_and_wrong_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corrupt = Path(directory) / "corrupt.png"
            corrupt.write_bytes(b"not png")
            self.assertTrue(any("readable PNG" in item for item in verify(corrupt)))

            wrong = Path(directory) / "wrong.png"
            data = bytearray((ROOT / "site/assets/social-preview.png").read_bytes())
            data[16:24] = struct.pack(">II", 640, 320)
            wrong.write_bytes(data)
            self.assertTrue(any("expected 1280x640" in item for item in verify(wrong)))

    def test_rejects_alpha_color_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "alpha.png"
            data = bytearray((ROOT / "site/assets/social-preview.png").read_bytes())
            data[25] = 6
            path.write_bytes(data)
            self.assertTrue(any("alpha channel" in item for item in verify(path)))
