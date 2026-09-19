import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download_manifest(version, archive_name, archive_size, archive_hash, unpacked_size, parts):
    return {
        "app_version": version, "platform": "windows-x64",
        "base_url": f"https://github.com/AmreetKumarkhuntia/earse-it/releases/download/v{version}/",
        "archive": {"name": archive_name, "size": archive_size, "sha256": archive_hash},
        "unpacked_size": unpacked_size,
        "files": [{"name": part.name, "size": part.stat().st_size, "sha256": checksum(part)} for part in parts],
    }


def split_archive(archive, limit=1900 * 1024 * 1024):
    """Keep each GitHub Release asset below 2 GiB; checksum covers the joined ZIP."""
    if archive.stat().st_size <= limit:
        return [archive]
    parts = []
    with archive.open("rb") as source:
        remaining = archive.stat().st_size
        while remaining:
            part = archive.with_name(f"{archive.name}.{len(parts) + 1:03d}")
            with part.open("wb") as target:
                size = min(remaining, limit)
                while size:
                    chunk = source.read(min(size, 8 * 1024 * 1024))
                    if not chunk:
                        raise OSError("Unexpected end of NVIDIA archive")
                    target.write(chunk)
                    size -= len(chunk)
                    remaining -= len(chunk)
            parts.append(part)
    archive.unlink()
    return parts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    args = parser.parse_args()
    build = ROOT / ".cache" / f"package-{args.device}"
    build.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
                    "--name", "erase-it-worker", "--distpath", str(build / "dist"),
                    "--workpath", str(build / "work"), "--specpath", str(build),
                    "--collect-all", "sam2", "--collect-all", "hydra", "--collect-all", "omegaconf",
                    "--collect-data", "erase_it", "--copy-metadata", "erase-it-worker",
                    str(ROOT / "worker/entrypoint.py")], check=True)
    bundle = build / "dist/erase-it-worker"
    licenses = bundle / "licenses"
    licenses.mkdir(exist_ok=True)
    inventory = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        inventory.append({"name": name, "version": distribution.version})
        for file in distribution.files or []:
            if any(word in file.name.lower() for word in ("license", "copying", "notice")):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    destination = licenses / name / str(file).replace("..", "_")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
    shutil.copy2(ROOT / "licenses/SAM2-LICENSE", licenses / "SAM2-LICENSE")
    shutil.copy2(ROOT / "LICENSE", licenses / "ERASE-IT-LICENSE")
    (licenses / "python-dependencies.json").write_text(json.dumps(inventory, indent=2))
    if args.device == "cpu":
        target = ROOT / "src-tauri/resources/worker"
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(bundle, target)
        print(f"CPU worker ready: {target}")
    else:
        version = json.loads((ROOT / "package.json").read_text())["version"]
        files = {p.relative_to(bundle).as_posix(): checksum(p)
                 for p in bundle.rglob("*") if p.is_file()}
        (bundle / "runtime-manifest.json").write_text(json.dumps({"app_version": version, "platform": "windows-x64", "files": files}, indent=2))
        output = ROOT / "artifacts/nvidia"
        shutil.rmtree(output, ignore_errors=True)
        output.mkdir(parents=True)
        archive = output / f"erase-it-nvidia-{version}-windows-x64"
        result = Path(shutil.make_archive(str(archive), "zip", bundle))
        digest = checksum(result)
        archive_size = result.stat().st_size
        result.with_suffix(".zip.sha256").write_text(f"{digest}  {result.name}\n")
        parts = split_archive(result)
        manifest = download_manifest(version, result.name, archive_size, digest,
                                     sum(p.stat().st_size for p in bundle.rglob("*") if p.is_file()), parts)
        setup = ROOT / "src-tauri/resources/setup"
        setup.mkdir(parents=True, exist_ok=True)
        (setup / "nvidia-download.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"NVIDIA pack ready: {parts}")


if __name__ == "__main__":
    main()
