"""Exercise pack splitting and the real PowerShell installer with tiny fixtures."""
import hashlib
import http.server
import importlib.util
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_worker", ROOT / "scripts/package-worker.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
# Setup invokes Windows PowerShell 5.1; use that edition on Windows too.
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


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

    def download(self):
        return subprocess.run([
            POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(ROOT / "scripts/install-nvidia.ps1"), "-Download", "-Manifest",
            str(self.root / "download.json"), "-DataDirectory", str(self.data),
        ], text=True, capture_output=True, timeout=45)

    def serve_pack(self, split=False, ranges=True):
        self.version = json.loads((ROOT / "package.json").read_text())["version"]
        self.archive = self.root / f"erase-it-nvidia-{self.version}-windows-x64.zip"
        self.pack()
        size = self.archive.stat().st_size
        digest = package.checksum(self.archive)
        parts = package.split_archive(self.archive, limit=150) if split else [self.archive]
        requests = []
        root = self.root

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(handler):
                requests.append((handler.path, handler.headers.get("Range")))
                payload = (root / handler.path.lstrip("/")).read_bytes()
                offset = int(handler.headers["Range"][6:-1]) if ranges and handler.headers.get("Range") else 0
                handler.send_response(206 if offset else 200)
                if offset:
                    handler.send_header("Content-Range", f"bytes {offset}-{len(payload)-1}/{len(payload)}")
                handler.send_header("Content-Length", str(len(payload) - offset))
                handler.end_headers()
                handler.wfile.write(payload[offset:])

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        manifest = package.download_manifest(self.version, self.archive.name, size, digest, 1024, parts)
        manifest["base_url"] = f"http://127.0.0.1:{server.server_port}/"
        (self.root / "download.json").write_text(json.dumps(manifest))
        self.cache = self.data / "runtimes/downloads" / self.version
        return parts, requests, manifest

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

    def test_downloads_and_installs_without_manual_archive_handling(self):
        self.serve_pack()
        result = self.download()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.old.read_bytes(), b"test runtime")
        self.assertFalse(self.cache.exists())

    def test_reuses_verified_part_and_resumes_interrupted_download(self):
        parts, requests, _ = self.serve_pack(split=True)
        self.cache.mkdir(parents=True)
        shutil.copy2(parts[0], self.cache / parts[0].name)
        (self.cache / (parts[1].name + ".partial")).write_bytes(parts[1].read_bytes()[:50])
        result = self.download()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.old.read_bytes(), b"test runtime")
        self.assertNotIn(("/" + parts[0].name, None), requests)
        self.assertIn(("/" + parts[1].name, "bytes=50-"), requests)

    def test_restarts_download_when_server_ignores_range(self):
        parts, requests, _ = self.serve_pack(ranges=False)
        self.cache.mkdir(parents=True)
        (self.cache / (parts[0].name + ".partial")).write_bytes(parts[0].read_bytes()[:50])
        result = self.download()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.old.read_bytes(), b"test runtime")
        self.assertIn(("/" + parts[0].name, "bytes=50-"), requests)

    def test_corrupt_download_preserves_runtime_and_can_be_retried(self):
        parts, _, _ = self.serve_pack(split=True)
        original = parts[1].read_bytes()
        parts[1].write_bytes(b"x" * len(original))
        result = self.download()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.old.read_bytes(), b"previous runtime")
        self.assertTrue((self.cache / parts[0].name).exists())
        self.assertFalse((self.cache / (parts[1].name + ".partial")).exists())
        parts[1].write_bytes(original)
        result = self.download()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.old.read_bytes(), b"test runtime")

    def test_invalid_metadata_is_rejected_before_downloading(self):
        _, requests, manifest = self.serve_pack()
        for change in (lambda m: m.update(app_version="0.0.0"),
                       lambda m: m["files"][0].update(name="../outside.zip")):
            invalid = json.loads(json.dumps(manifest))
            change(invalid)
            (self.root / "download.json").write_text(json.dumps(invalid))
            result = self.download()
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.old.read_bytes(), b"previous runtime")
            self.assertEqual(requests, [])


if __name__ == "__main__":
    unittest.main()
