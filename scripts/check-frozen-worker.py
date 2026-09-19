"""Smoke-test the packaged runtime without relying on site-packages or PYTHONPATH."""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
parser.add_argument("--bundle", type=Path, help="Check an installed runtime instead of the build output")
args = parser.parse_args()
bundle = args.bundle or root / (".cache/package-cuda/dist/erase-it-worker" if args.device == "cuda" else "src-tauri/resources/worker")
worker = bundle / ("erase-it-worker.exe" if os.name == "nt" else "erase-it-worker")
environment = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")}
with tempfile.TemporaryDirectory() as directory:
    subprocess.run([str(worker), "--data-dir", directory, "--self-test"], cwd=directory, env=environment, check=True, timeout=120)
    process = subprocess.Popen([str(worker), "--data-dir", directory], cwd=directory, env=environment,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        process.stdin.write(json.dumps({"v": 1, "id": "smoke", "action": "hello", "params": {}}) + "\n")
        process.stdin.flush()
        response = json.loads(process.stdout.readline())
        assert response["result"]["capabilities"]["inference_ready"], response
        if args.device == "cuda":
            assert response["result"]["capabilities"]["cuda_runtime"], response
        expected_version = json.loads((root / "package.json").read_text())["version"]
        assert response["result"]["version"] == expected_version, response
        print("Frozen runtime loads PyTorch and SAM 2 successfully.")
    finally:
        process.stdin.close()
        process.wait(timeout=30)
