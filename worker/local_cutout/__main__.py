import argparse
import contextlib
import json
import os
import re
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .errors import CutoutError
from .jobs import Job
from .service import Service


def serve(root: Path, input_stream=None, output_stream=None):
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    service = Service(root)
    output_lock, active_lock = threading.Lock(), threading.Lock()
    active: dict[str, Job] = {}

    def emit(message):
        with output_lock:
            output_stream.write(json.dumps(message, allow_nan=False) + "\n")
            output_stream.flush()

    def perform(request, job):
        try:
            result = service.dispatch(request["action"], request.get("params", {}), job)
            response = {"v": 1, "id": request["id"], "result": result}
        except CutoutError as error:
            response = {"v": 1, "id": request["id"], "error": {"code": error.code, "message": str(error)}}
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            if job.cancelled.is_set():
                code, message = "CANCELLED", "Operation cancelled. Your saved selections are retained."
            elif isinstance(error, OSError) and error.errno == 28:
                code, message = "DISK_FULL", "The disk is full. Free space and retry; your selections are saved."
            else:
                code, message = "PROCESSING_FAILED", str(error)[:1000] or "Processing failed. See the worker log for details."
            response = {"v": 1, "id": request["id"], "error": {"code": code, "message": message}}
        finally:
            with active_lock:
                active.pop(job.id, None)
        emit(response)

    # Keep package logging off stdout, which is exclusively the JSON protocol.
    with contextlib.redirect_stdout(sys.stderr), ThreadPoolExecutor(max_workers=1) as executor:
        for line in input_stream:
            request_id = None
            try:
                if len(line) > 1024 * 1024:
                    raise CutoutError("INVALID_REQUEST", "Request exceeds the 1 MB limit.")
                request = json.loads(line)
                request_id = request.get("id")
                if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id):
                    raise CutoutError("INVALID_REQUEST", "Invalid request identifier.")
                if request.get("v") != 1 or not isinstance(request.get("params", {}), dict):
                    raise CutoutError("INVALID_REQUEST", "Unsupported protocol version or malformed parameters.")
                if request.get("action") == "cancel":
                    with active_lock:
                        target = active.get(request.get("params", {}).get("job_id"))
                        if target:
                            target.cancel()
                    emit({"v": 1, "id": request_id, "result": {"cancelled": target is not None}})
                    continue
                with active_lock:
                    if active:
                        raise CutoutError("BUSY", "Wait for the current operation or cancel it first.")
                    job = Job(request_id, emit)
                    active[request_id] = job
                executor.submit(perform, request, job)
            except (ValueError, AttributeError):
                emit({"v": 1, "id": request_id, "error": {"code": "INVALID_REQUEST", "message": "Invalid JSON request."}})
            except CutoutError as error:
                emit({"v": 1, "id": request_id, "error": {"code": error.code, "message": str(error)}})
        # Parent exit or broken input must not leave inference/FFmpeg running.
        with active_lock:
            for job in active.values():
                job.cancel()


def main():
    parser = argparse.ArgumentParser(description="Local Cutout JSON worker")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--download-model", choices=["tiny", "base_plus"])
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        from sam2.build_sam import build_sam2_video_predictor
        model = build_sam2_video_predictor("configs/sam2.1/sam2.1_hiera_t.yaml", device="cpu", apply_postprocessing=False)
        assert model.image_size == 1024
        print(json.dumps({"ok": True, "model": "SAM 2.1 Tiny", "checkpoint_loaded": False}))
    elif args.download_model:
        from .models import Models
        model = Models(args.data_dir)
        model.download(args.download_model, Job("download", lambda value: print(json.dumps(value), file=sys.stderr)))
        print(model.path(args.download_model))
    else:
        serve(args.data_dir)


if __name__ == "__main__":
    main()
