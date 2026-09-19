"""Exercise pack splitting and the real PowerShell installer with tiny fixtures."""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_worker", ROOT / "scripts/package-worker.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


class PackTests(unittest.TestCase):
    def test_split_preserves_exact_archive_and_limits_each_asset(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "runtime.zip"
            content = bytes(range(256)) * 3
            archive.write_bytes(content)
            parts = package.split_archive(archive, limit=100)
            self.assertFalse(archive.exists())
            self.assertEqual(b"".join(p.read_bytes() for p in parts), content)
            self.assertTrue(all(p.stat().st_size <= 100 for p in parts))
            self.assertEqual(parts[-1].suffix, ".008")

    def test_small_archive_does_not_require_parts(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "runtime.zip"
            archive.write_bytes(b"small")
            self.assertEqual(package.split_archive(archive, limit=100), [archive])
            self.assertEqual(archive.read_bytes(), b"small")


@unittest.skipUnless(POWERSHELL, "Requires PowerShell; exercised in Windows CI")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / "runtime.zip"
        self.data = self.root / "app-data"
        self.old = self.data / "runtimes/nvidia/erase-it-worker.exe"
        self.old.parent.mkdir(parents=True)
        self.old.write_bytes(b"previous runtime")

    def pack(self, version=None, tamper=False):
        version = version or json.loads((ROOT / "package.json").read_text())["version"]
        content = b"test runtime"
        manifest = {"app_version": version, "platform": "windows-x64", "files": {
            "erase-it-worker.exe": hashlib.sha256(content).hexdigest(),
        }}
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("erase-it-worker.exe", b"tampered" if tamper else content)
            archive.writestr("runtime-manifest.json", json.dumps(manifest))
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.archive.with_suffix(".zip.sha256").write_text(f"{digest}  {self.archive.name}\n")

    def install(self):
        return subprocess.run([
            POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(ROOT / "scripts/install-nvidia.ps1"), "-Archive", str(self.archive),
            "-DataDirectory", str(self.data),
        ], text=True, capture_output=True, timeout=30)

    def assert_clean(self):
        self.assertEqual([p.name for p in (self.data / "runtimes").iterdir()], ["nvidia"])

    def test_installs_whole_and_split_archives(self):
        for split in (False, True):
            with self.subTest(split=split):
                self.pack()
                if split:
                    package.split_archive(self.archive, limit=150)
                result = self.install()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.old.read_bytes(), b"test runtime")
                self.assert_clean()

    def test_rejects_wrong_version_and_tampered_files_without_replacing_runtime(self):
        for options in ({"version": "0.0.0"}, {"tamper": True}):
            with self.subTest(options=options):
                self.pack(**options)
                result = self.install()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.old.read_bytes(), b"previous runtime")
                self.assert_clean()

    def test_rejects_missing_part_without_replacing_runtime(self):
        self.pack()
        parts = package.split_archive(self.archive, limit=150)
        parts[1].unlink()
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.old.read_bytes(), b"previous runtime")
        self.assert_clean()

    def test_rejects_wrong_archive_checksum(self):
        self.pack()
        self.archive.write_bytes(self.archive.read_bytes() + b"corrupt")
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.old.read_bytes(), b"previous runtime")
        self.assert_clean()


if __name__ == "__main__":
    unittest.main()
