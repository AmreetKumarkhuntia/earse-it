import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    args = parser.parse_args()
    build = ROOT / ".cache" / f"package-{args.device}"
    build.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
                    "--name", "local-cutout-worker", "--distpath", str(build / "dist"),
                    "--workpath", str(build / "work"), "--specpath", str(build),
                    "--collect-all", "sam2", "--collect-all", "hydra", "--collect-all", "omegaconf",
                    "--collect-data", "local_cutout", "--copy-metadata", "local-cutout-worker",
                    str(ROOT / "worker/entrypoint.py")], check=True)
    bundle = build / "dist/local-cutout-worker"
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
    shutil.copy2(ROOT / "LICENSE", licenses / "LOCAL-CUTOUT-LICENSE")
    (licenses / "python-dependencies.json").write_text(json.dumps(inventory, indent=2))
    if args.device == "cpu":
        target = ROOT / "src-tauri/resources/worker"
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(bundle, target)
        print(f"CPU worker ready: {target}")
    else:
        version = json.loads((ROOT / "package.json").read_text())["version"]
        files = {p.relative_to(bundle).as_posix(): hashlib.file_digest(p.open("rb"), "sha256").hexdigest()
                 for p in bundle.rglob("*") if p.is_file()}
        (bundle / "runtime-manifest.json").write_text(json.dumps({"app_version": version, "platform": "windows-x64", "files": files}, indent=2))
        archive = ROOT / f"dist/local-cutout-nvidia-{version}-windows-x64"
        archive.parent.mkdir(exist_ok=True)
        result = Path(shutil.make_archive(str(archive), "zip", bundle))
        with result.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        result.with_suffix(".zip.sha256").write_text(f"{digest}  {result.name}\n")
        shutil.copy2(ROOT / "scripts/install-nvidia.ps1", result.parent)
        print(f"NVIDIA pack ready: {result}")


if __name__ == "__main__":
    main()
