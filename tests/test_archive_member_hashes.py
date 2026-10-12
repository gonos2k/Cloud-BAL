import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from archive_member_hashes import archive_member_hashes


class ArchiveMemberHashTests(unittest.TestCase):
    def test_duplicate_and_long_member_names_keep_order_and_individual_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "objects.a"
            member = root / "track_driver.o"
            member.write_bytes(b"first occurrence")
            subprocess.run(["ar", "qc", str(archive), str(member)], check=True)
            member.write_bytes(b"second occurrence")
            long_member = root / "module_mp_very_long_name.o"
            long_member.write_bytes(b"long member")
            subprocess.run(["ar", "q", str(archive), str(member), str(long_member)], check=True)
            expected = [("track_driver.o", b"first occurrence"),
                        ("track_driver.o", b"second occurrence"),
                        (long_member.name, b"long member")]
            self.assertEqual(archive_member_hashes(archive),
                             [(name, hashlib.sha256(body).hexdigest()) for name, body in expected])
            archive.write_bytes(archive.read_bytes()[:-2])
            with self.assertRaises(ValueError):
                archive_member_hashes(archive)


if __name__ == "__main__":
    unittest.main()
