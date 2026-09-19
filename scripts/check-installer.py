"""Install the real release EXE and load its NVIDIA runtime on an ephemeral CI VM."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Run only on the ephemeral Windows GitHub Actions runner")
    data = Path(os.environ["APPDATA"]) / "io.github.amreetkumarkhuntia.eraseit"
    if data.exists():
        raise SystemExit("Refusing to replace existing erase-it application data")
    installers = list((ROOT / "src-tauri/target/release/bundle/nsis").glob("*.exe"))
    if len(installers) != 1:
        raise SystemExit(f"Expected one installer, found {installers}")
    metadata = json.loads((ROOT / "src-tauri/resources/setup/nvidia-download.json").read_text())
    cache = data / "runtimes/downloads" / metadata["app_version"]
    cache.mkdir(parents=True)
    # The release is still private. Seed its verified cache with exactly the files
    # about to be published; HTTP/range/error paths have separate fixture tests.
    for entry in metadata["files"]:
        source = ROOT / "artifacts/nvidia" / entry["name"]
        destination = cache / entry["name"]
        try:
            os.link(source, destination)
        except OSError:
            shutil.copy2(source, destination)
    with tempfile.TemporaryDirectory(prefix="erase-it-install-") as temporary:
        installed = Path(temporary) / "erase-it"
        try:
            subprocess.run([str(installers[0]), "/S", "/NVIDIA", f"/D={installed}"],
                           check=True, timeout=1200)
            assert (installed / "erase-it.exe").is_file(), "App was not installed"
            assert (installed / "worker/erase-it-worker.exe").is_file(), "CPU worker was not installed"
            assert not cache.exists(), "Successful setup should remove downloaded files"
            subprocess.run([sys.executable, "scripts/check-frozen-worker.py", "--device", "cuda",
                            "--bundle", str(data / "runtimes/nvidia")], cwd=ROOT, check=True)
            print("Combined Windows installer installs the app, CPU worker, and verified CUDA worker.", flush=True)
        finally:
            log = data / "nvidia-setup.log"
            if log.exists():
                print(log.read_text(encoding="utf-8-sig", errors="replace"), flush=True)
            uninstaller = installed / "uninstall.exe"
            if uninstaller.exists():
                # _?= keeps NSIS in this process so we wait for file removal.
                subprocess.run([str(uninstaller), "/S", f"_?={installed}"], check=True, timeout=120)
            shutil.rmtree(data)


if __name__ == "__main__":
    main()
