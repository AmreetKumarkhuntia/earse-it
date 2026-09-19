import hashlib
import importlib.util
import json
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__
from .errors import CutoutError
from .jobs import Job

MANIFEST = json.loads(Path(__file__).with_name("models.json").read_text())


class Models:
    def __init__(self, root: Path):
        self.directory = root / "models"
        self.directory.mkdir(parents=True, exist_ok=True)

    def get(self, model_id: str) -> dict:
        for model in MANIFEST["models"]:
            if model["id"] == model_id:
                return model
        raise CutoutError("INVALID_INPUT", "Unknown model.")

    def path(self, model_id: str) -> Path:
        return self.directory / self.get(model_id)["filename"]

    def list(self):
        return [{**model, "installed": self.path(model["id"]).is_file()} for model in MANIFEST["models"]]

    def verify(self, model_id: str, job: Job) -> Path:
        model = self.get(model_id)
        path = self.path(model_id)
        if not path.is_file():
            raise CutoutError("MODEL_MISSING", "Download the selected model in Processing before making a selection.")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                job.check()
                digest.update(chunk)
        if path.stat().st_size != model["size"] or digest.hexdigest() != model["sha256"]:
            raise CutoutError("MODEL_CORRUPT", "The model checksum does not match. Download the model again.")
        return path

    def download(self, model_id: str, job: Job):
        model = self.get(model_id)
        if self.path(model_id).exists():
            try:
                self.verify(model_id, job)
                return self.list()
            except CutoutError as error:
                if error.code != "MODEL_CORRUPT":
                    raise
        if shutil.disk_usage(self.directory).free < model["size"] + 64 * 1024 * 1024:
            raise CutoutError("DISK_FULL", "There is not enough free disk space to download this model.")
        partial = self.path(model_id).with_suffix(".part")
        offset = partial.stat().st_size if partial.exists() else 0
        if offset >= model["size"]:
            partial.unlink()
            offset = 0
        headers = {"User-Agent": f"erase-it/{__version__}"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            request = urllib.request.Request(model["url"], headers=headers)
            with urllib.request.urlopen(request, timeout=20) as response:
                if offset and (response.status != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-")):
                    offset = 0
                mode = "ab" if offset else "wb"
                with partial.open(mode) as stream:
                    while chunk := response.read(1024 * 1024):
                        job.check()
                        stream.write(chunk)
                        offset += len(chunk)
                        if offset > model["size"]:
                            raise CutoutError("MODEL_CORRUPT", "The model download had an unexpected size.")
                        job.progress("Downloading model", offset, model["size"])
            digest = hashlib.sha256()
            with partial.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    job.check()
                    digest.update(chunk)
            if offset != model["size"] or digest.hexdigest() != model["sha256"]:
                partial.unlink(missing_ok=True)
                raise CutoutError("MODEL_CORRUPT", "Model verification failed. Retry the download.")
            os.replace(partial, self.path(model_id))
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            raise CutoutError("DOWNLOAD_FAILED", f"Download interrupted; retry to resume. {error}")
        return self.list()


def capabilities():
    ready = all(importlib.util.find_spec(name) is not None for name in ("torch", "sam2"))
    cuda, device, runtime, detail = False, None, None, None
    status = "runtime_missing"
    if ready:
        try:
            import torch
            runtime = torch.version.cuda
            status = "cpu_only" if runtime is None else "cuda_unavailable"
            cuda = torch.cuda.is_available()
            if cuda:
                device = torch.cuda.get_device_name(0)
                status = "available"
        except Exception as error:
            # Keep the help/diagnostics screen usable when a runtime cannot load.
            cuda, device, ready = False, None, False
            status, detail = "runtime_error", str(error)
    return {"inference_ready": ready, "cuda_available": cuda, "cuda_device": device,
            "cpu_available": ready, "gpu_status": status, "cuda_runtime": runtime,
            "runtime_error": detail, "sam2_revision": MANIFEST["sam2_revision"]}
