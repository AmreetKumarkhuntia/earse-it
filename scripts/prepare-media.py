"""Fetch the pinned Windows LGPL tools; retain upstream notices and source archives."""
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / "scripts/media-manifest.json").read_text())
    cache = ROOT / ".cache/media"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / "ffmpeg-windows.zip"
    if not archive.exists():
        urllib.request.urlretrieve(manifest["url"], archive.with_suffix(".part"))
        archive.with_suffix(".part").replace(archive)
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != manifest["sha256"]:
        archive.unlink()
        raise SystemExit("FFmpeg checksum mismatch; download discarded.")
    target = ROOT / "src-tauri/resources/media"
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as package:
        for item in package.infolist():
            relative = Path(*Path(item.filename).parts[1:])
            if ".." in relative.parts or relative.is_absolute():
                raise SystemExit("Invalid path in media archive")
            if item.is_dir():
                continue
            if relative.parts and relative.parts[0] == "bin":
                if relative.name not in ("ffmpeg.exe", "ffprobe.exe") and relative.suffix != ".dll":
                    continue
                destination = target / relative.name
            else:
                destination = target / "upstream" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with package.open(item) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
    if os.name == "nt":
        configuration = subprocess.check_output([str(target / "ffmpeg.exe"), "-buildconf"], stderr=subprocess.STDOUT).decode(errors="replace")
        if "--enable-gpl" in configuration or "--enable-nonfree" in configuration:
            raise SystemExit("GPL or nonfree FFmpeg builds must not be bundled by this packaging workflow.")
        (target / "build-configuration.txt").write_text(configuration)
    sources = ROOT / "dist/third-party-sources"
    sources.mkdir(parents=True, exist_ok=True)
    urls = {
        "ffmpeg-source.tar.gz": f"https://github.com/FFmpeg/FFmpeg/archive/{manifest['ffmpeg_revision']}.tar.gz",
        "ffmpeg-build-scripts.tar.gz": f"https://github.com/BtbN/FFmpeg-Builds/archive/refs/tags/{manifest['build_release']}.tar.gz",
    }
    for filename, url in urls.items():
        destination = sources / filename
        if not destination.exists():
            urllib.request.urlretrieve(url, destination)
    (sources / "provenance.json").write_text(json.dumps({**manifest, "sources": urls}, indent=2))
    shutil.copy2(ROOT / "scripts/media-manifest.json", target / "manifest.json")
    print(f"Media tools ready: {target}")


if __name__ == "__main__":
    main()
