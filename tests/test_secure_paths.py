import os
import tempfile
import unittest
from pathlib import Path

from deep_reach.runtime.secure_paths import ensure_private_dir, tighten_file


class SecurePathsTest(unittest.TestCase):
    def test_ensure_private_dir_tightens_existing_directory(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions only")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "private"
            path.mkdir(mode=0o755)
            note = ensure_private_dir(path)
            self.assertEqual(note, "")
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)

    def test_tighten_file_skips_symlink(self):
        if os.name == "nt":
            self.skipTest("POSIX permissions only")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target.yaml"
            target.write_text("x", encoding="utf-8")
            link = Path(tmp) / "keys.yaml"
            link.symlink_to(target)
            note = tighten_file(link)
            self.assertIn("symlink", note)
            self.assertNotEqual(target.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
