"""Release checks use temporary fixtures; they never build or publish the app."""
import hashlib
import importlib.util
import json
import shutil
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("prepare_release", ROOT / "scripts/prepare-release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write(self, relative, content="fixture\n"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def versions(self):
        for relative in (
            "package.json", "package-lock.json", "src-tauri/tauri.conf.json",
            "src-tauri/Cargo.toml", "src-tauri/Cargo.lock", "worker/pyproject.toml",
            "scripts/install-nvidia.ps1", "worker/erase_it/__init__.py",
        ):
            self.write(relative, (ROOT / relative).read_text(encoding="utf-8"))

    def assets(self):
        for relative in (
            "src-tauri/target/release/bundle/nsis/erase-it_1.2.3_x64-setup.exe",
            "LICENSE", "licenses/THIRD_PARTY.md",
            "artifacts/third-party-sources/ffmpeg-source.tar.gz",
            "artifacts/third-party-sources/ffmpeg-build-scripts.tar.gz",
            "artifacts/third-party-sources/provenance.json",
            "src-tauri/resources/media/manifest.json",
            "src-tauri/resources/media/build-configuration.txt",
            "src-tauri/resources/media/upstream/LICENSE.txt",
            "src-tauri/resources/worker/licenses/python-dependencies.json",
            "src-tauri/resources/worker/licenses/SAM2-LICENSE",
        ):
            self.write(relative)

    def test_version_update_keeps_all_manifests_in_sync(self):
        self.versions()
        before = tomllib.loads((self.root / "src-tauri/Cargo.lock").read_text())["package"]
        release.update_versions(self.root, "1.2.3")
        for relative in ("package.json", "package-lock.json", "src-tauri/tauri.conf.json"):
            data = json.loads((self.root / relative).read_text())
            self.assertEqual(data["version"], "1.2.3")
        lock = json.loads((self.root / "package-lock.json").read_text())
        self.assertEqual(lock["packages"][""]["version"], "1.2.3")
        self.assertEqual(tomllib.loads((self.root / "src-tauri/Cargo.toml").read_text())["package"]["version"], "1.2.3")
        self.assertEqual(tomllib.loads((self.root / "worker/pyproject.toml").read_text())["project"]["version"], "1.2.3")
        after = tomllib.loads((self.root / "src-tauri/Cargo.lock").read_text())["package"]
        for old, new in zip(before, after, strict=True):
            self.assertEqual(new, {**old, "version": "1.2.3"} if old["name"] == "erase-it" else old)
        self.assertIn('$AppVersion = "1.2.3"', (self.root / "scripts/install-nvidia.ps1").read_text())
        self.assertIn('__version__ = "1.2.3"', (self.root / "worker/erase_it/__init__.py").read_text())

    def test_invalid_version_or_missing_field_does_not_change_files(self):
        self.versions()
        package = self.root / "package.json"
        before = package.read_bytes()
        with self.assertRaises(ValueError):
            release.update_versions(self.root, "v1.2.3")
        self.write("scripts/install-nvidia.ps1", "Missing the expected version field")
        with self.assertRaises(ValueError):
            release.update_versions(self.root, "1.2.3")
        self.assertEqual(package.read_bytes(), before)

    def test_archive_contains_sources_notices_and_matching_checksums(self):
        self.assets()
        output = release.stage_assets(self.root, "1.2.3")
        for line in (output / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ", 1)
            self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
        with zipfile.ZipFile(output / "third-party-sources-and-notices-1.2.3.zip") as archive:
            self.assertTrue({
                "LICENSE", "third-party-sources/ffmpeg-source.tar.gz",
                "third-party-sources/ffmpeg-build-scripts.tar.gz", "third-party-sources/provenance.json",
                "licenses/THIRD_PARTY.md", "media/build-configuration.txt", "media/manifest.json",
                "media/upstream/LICENSE.txt", "worker/licenses/python-dependencies.json",
                "worker/licenses/SAM2-LICENSE",
            }.issubset(archive.namelist()))

    def test_missing_sources_or_upstream_notices_block_release(self):
        self.assets()
        source = self.root / "artifacts/third-party-sources/ffmpeg-source.tar.gz"
        source.unlink()
        with self.assertRaisesRegex(ValueError, "missing or empty"):
            release.stage_assets(self.root, "1.2.3")
        self.write(str(source.relative_to(self.root)))
        shutil.rmtree(self.root / "src-tauri/resources/media/upstream")
        with self.assertRaisesRegex(ValueError, "directory is empty"):
            release.stage_assets(self.root, "1.2.3")

    def test_missing_ambiguous_or_wrong_version_installer_blocks_release(self):
        self.assets()
        with self.assertRaisesRegex(ValueError, "exactly one"):
            release.stage_assets(self.root, "1.2.4")
        extra = self.write("src-tauri/target/release/bundle/nsis/stale.exe")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            release.stage_assets(self.root, "1.2.3")
        extra.unlink()
        shutil.rmtree(self.root / "src-tauri/target/release/bundle/nsis")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            release.stage_assets(self.root, "1.2.3")


if __name__ == "__main__":
    unittest.main()
