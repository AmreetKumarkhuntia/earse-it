"""Run with Python 3.12. Installs the selected runtime into a project-local venv."""
import argparse
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Use Python 3.12: py -3.12 scripts/setup-worker.py")
    environment = ROOT / (".venv" if args.device == "cpu" else ".venv-cuda")
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    env = {**os.environ, "SAM2_BUILD_CUDA": "0", "PIP_CACHE_DIR": str(ROOT / ".cache/pip")}
    def install(*packages):
        subprocess.run([str(python), "-m", "pip", "install", *packages], env=env, check=True, cwd=ROOT)
    install("pip==25.2", "setuptools==80.9.0", "wheel==0.45.1")
    index = "https://download.pytorch.org/whl/" + ("cpu" if args.device == "cpu" else "cu128")
    install("torch==2.7.1", "torchvision==0.22.1", "--index-url", index)
    install("hydra-core==1.3.2", "iopath==0.1.10", "tqdm==4.67.1")
    manifest = json.loads((ROOT / "worker/local_cutout/models.json").read_text())
    install("--no-deps", "--no-build-isolation", f"https://github.com/facebookresearch/sam2/archive/{manifest['sam2_revision']}.zip")
    install("-e", str(ROOT / "worker") + "[test,build]")
    for folder in ("worker", "media"):
        (ROOT / "src-tauri/resources" / folder).mkdir(parents=True, exist_ok=True)
    print(f"Ready: {python}")
    if args.device == "cuda":
        print("For desktop development, set LOCAL_CUTOUT_PYTHON to this Python executable.")


if __name__ == "__main__":
    main()
