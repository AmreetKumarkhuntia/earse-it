"""Set the release version, build the Windows installer, and collect release assets."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text, pattern, replacement, path):
    result, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"Expected one version field in {path}; found {count}")
    return result


def update_versions(root, version):
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise ValueError(f"Expected a stable semantic version, got {version!r}")
    updates = {}
    for relative in ("package.json", "package-lock.json", "src-tauri/tauri.conf.json"):
        path = root / relative
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = version
        if relative == "package-lock.json":
            data["packages"][""]["version"] = version
        updates[path] = json.dumps(data, indent=2) + "\n"
    for relative in ("src-tauri/Cargo.toml", "worker/pyproject.toml"):
        path = root / relative
        updates[path] = replace_once(
            path.read_text(encoding="utf-8"), r'^version = "[^"]+"$',
            lambda _: f'version = "{version}"', relative,
        )
    path = root / "src-tauri/Cargo.lock"
    updates[path] = replace_once(
        path.read_text(encoding="utf-8"),
        r'(\[\[package\]\]\nname = "erase-it"\nversion = ")[^"]+("$)',
        lambda match: f"{match[1]}{version}{match[2]}", path,
    )
    path = root / "scripts/install-nvidia.ps1"
    updates[path] = replace_once(
        path.read_text(encoding="utf-8"), r'^\$AppVersion = "[^"]+"$',
        lambda _: f'$AppVersion = "{version}"', path,
    )
    path = root / "worker/erase_it/__init__.py"
    updates[path] = replace_once(
        path.read_text(encoding="utf-8"), r'^__version__ = "[^"]+"$',
        lambda _: f'__version__ = "{version}"', path,
    )
    # Validate every file before writing any of them.
    for path, text in updates.items():
        path.write_text(text, encoding="utf-8", newline="\n")


def stage_assets(root, version):
    installers = list((root / "src-tauri/target/release/bundle/nsis").glob("*.exe"))
    if len(installers) != 1 or not installers[0].name.endswith(f"_{version}_x64-setup.exe"):
        raise ValueError(f"Expected exactly one Windows x64 installer for {version}: {installers}")
    media = root / "src-tauri/resources/media"
    sources = root / "artifacts/third-party-sources"
    worker_licenses = root / "src-tauri/resources/worker/licenses"
    required = [
        installers[0], root / "LICENSE", root / "licenses/THIRD_PARTY.md",
        sources / "ffmpeg-source.tar.gz", sources / "ffmpeg-build-scripts.tar.gz",
        sources / "provenance.json", media / "manifest.json",
        media / "build-configuration.txt", worker_licenses / "python-dependencies.json",
    ]
    for path in required:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Required release file is missing or empty: {path}")
    directories = [
        (sources, "third-party-sources"),
        (root / "licenses", "licenses"),
        (media / "upstream", "media/upstream"),
        (worker_licenses, "worker/licenses"),
    ]
    for directory, _ in directories:
        if not any(path.is_file() for path in directory.rglob("*")):
            raise ValueError(f"Required release directory is empty: {directory}")
    output = root / "artifacts/release"
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True)
    installer = output / f"erase-it-{version}-windows-x64-setup.exe"
    shutil.copy2(installers[0], installer)
    archive = output / f"third-party-sources-and-notices-{version}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for directory, prefix in directories:
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    package.write(path, f"{prefix}/{path.relative_to(directory).as_posix()}")
        package.write(root / "LICENSE", "LICENSE")
        for name in ("manifest.json", "build-configuration.txt"):
            package.write(media / name, f"media/{name}")
    checksums = []
    for path in (installer, archive):
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        checksums.append(f"{digest}  {path.name}\n")
    (output / "SHA256SUMS").write_text("".join(checksums), encoding="utf-8", newline="\n")
    return output


def main():
    if os.name != "nt" or len(sys.argv) != 2:
        raise SystemExit("Run in the Windows release workflow: prepare-release.py VERSION")
    version = sys.argv[1]
    update_versions(ROOT, version)
    # Refresh editable package metadata so the frozen worker records the new version.
    commands = [
        [sys.executable, "-m", "pip", "install", "--no-deps", "--no-build-isolation", "-e", "worker"],
        [sys.executable, "scripts/package-worker.py"],
        [sys.executable, "scripts/check-frozen-worker.py"],
        [shutil.which("npm.cmd"), "run", "desktop:build"],
    ]
    for command in commands:
        subprocess.run(command, cwd=ROOT, check=True)
    print(f"Release files ready: {stage_assets(ROOT, version)}")


if __name__ == "__main__":
    main()
