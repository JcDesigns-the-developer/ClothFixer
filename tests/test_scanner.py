import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main import parse_asset, scan_folder, apply_changes


class ScannerTests(unittest.TestCase):
    def test_parses_prefixed_and_unprefixed_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            prefixed = root / "mp_m_freemode_01^jbib_001_u.ydd"
            plain = root / "jbib_004_u.ydd"
            self.assertEqual(parse_asset(prefixed, root).number, 1)
            self.assertEqual(parse_asset(plain, root).kind, "jbib")

    def test_duplicate_slot_renumbers_second_drawable_and_sidecar(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a").mkdir()
            (root / "b").mkdir()
            first = root / "a" / "mp_m_freemode_01^jbib_001_u.ydd"
            second = root / "b" / "mp_m_freemode_01^jbib_001_u.ydd"
            sidecar = root / "b" / "mp_m_freemode_01^jbib_001_u.ytd"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            sidecar.write_bytes(b"texture")

            assets, changes = scan_folder(root)
            targets = {change.destination.name for change in changes}
            self.assertEqual(len(assets), 3)
            self.assertIn("mp_m_freemode_01^jbib_000_u.ydd", targets)
            self.assertIn("mp_m_freemode_01^jbib_000_u.ytd", targets)

            with patch("main._run_binary_rewrites", return_value=({}, "mocked embedded rewrite")):
                backup, summary = apply_changes(changes, root)
            self.assertEqual(summary, "mocked embedded rewrite")
            self.assertTrue(backup.exists())
            self.assertTrue((root / "b" / "mp_m_freemode_01^jbib_000_u.ydd").exists())
            self.assertTrue((root / "b" / "mp_m_freemode_01^jbib_000_u.ytd").exists())
            self.assertTrue((backup / "b" / second.name).exists())

    def test_binary_rewrite_failure_leaves_original_files_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a").mkdir()
            (root / "b").mkdir()
            first = root / "a" / "mp_m_freemode_01^jbib_001_u.ydd"
            second = root / "b" / "mp_m_freemode_01^jbib_001_u.ydd"
            first.write_bytes(b"first")
            second.write_bytes(b"original second")

            _, changes = scan_folder(root)
            with patch("main._run_binary_rewrites", side_effect=RuntimeError("parser failed")):
                with self.assertRaisesRegex(RuntimeError, "parser failed"):
                    apply_changes(changes, root)

            self.assertTrue(second.exists())
            self.assertEqual(second.read_bytes(), b"original second")
            self.assertFalse((root / "b" / "mp_m_freemode_01^jbib_000_u.ydd").exists())


if __name__ == "__main__":
    unittest.main()
