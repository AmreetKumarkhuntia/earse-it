"""Small SAM 2 adapter: lazy frames and disk-spilled state avoid video-sized RAM use.

The upstream predictor's selection and propagation logic is retained. Only its frame
loader and tensor storage are replaced. No CUDA extension or torch.compile is required.
"""
import contextlib
import os
import shutil
from collections import OrderedDict
from collections.abc import MutableMapping
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from .errors import CutoutError
from .jobs import Job
from .masks import save_image
from .models import Models


class LazyFrames:
    def __init__(self, project, image_size: int, limit: int = 3):
        self.project = project
        self.image_size = image_size
        self.limit = limit
        self.cache = OrderedDict()

    def __len__(self):
        return self.project.data["media"]["frame_count"]

    def __getitem__(self, index):
        import torch
        if not 0 <= index < len(self):
            raise IndexError(index)
        if index not in self.cache:
            with Image.open(self.project.frame_path(index)) as source:
                # Matches upstream JPEG loader: square resize, float RGB, ImageNet normalization.
                image = source.convert("RGB").resize((self.image_size, self.image_size))
                tensor = torch.from_numpy(np.asarray(image).copy()).permute(2, 0, 1).float().div_(255)
            mean = torch.tensor([.485, .456, .406])[:, None, None]
            std = torch.tensor([.229, .224, .225])[:, None, None]
            self.cache[index] = (tensor - mean) / std
        self.cache.move_to_end(index)
        while len(self.cache) > self.limit:
            self.cache.popitem(last=False)
        return self.cache[index]


class DiskState(MutableMapping):
    """Mapping with a write-back LRU for SAM's mutable per-frame tensor records."""
    def __init__(self, directory: Path, limit: int = 8):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.limit = limit
        self.keys_present: set[int] = set()
        self.cache = OrderedDict()

    def _write(self, key, value):
        import torch
        path = self.directory / f"{key}.pt"
        temporary = path.with_suffix(".part")
        torch.save(value, temporary)
        os.replace(temporary, path)

    def _trim(self):
        while len(self.cache) > self.limit:
            key, value = self.cache.popitem(last=False)
            self._write(key, value)

    def __getitem__(self, key):
        import torch
        if key not in self.keys_present:
            raise KeyError(key)
        if key not in self.cache:
            self.cache[key] = torch.load(self.directory / f"{key}.pt", map_location="cpu", weights_only=True)
        self.cache.move_to_end(key)
        self._trim()
        return self.cache[key]

    def __setitem__(self, key, value):
        self.keys_present.add(key)
        self.cache[key] = value
        self.cache.move_to_end(key)
        self._trim()

    def __delitem__(self, key):
        if key not in self.keys_present:
            raise KeyError(key)
        self.keys_present.remove(key)
        self.cache.pop(key, None)
        (self.directory / f"{key}.pt").unlink(missing_ok=True)

    def __iter__(self):
        return iter(sorted(self.keys_present))

    def __len__(self):
        return len(self.keys_present)


class Engine:
    def __init__(self, models: Models):
        self.models = models
        self.predictor = None
        self.loaded_key = None
        self.device = "cpu"

    def unload(self):
        self.predictor = None
        self.loaded_key = None
        import gc
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except (ImportError, RuntimeError):
            pass

    def load(self, model_id: str, preference: str, job: Job):
        try:
            import torch
            from sam2.build_sam import build_sam2_video_predictor
        except ImportError:
            raise CutoutError("INFERENCE_MISSING", "Install the processing runtime. For development, run scripts/setup-worker.py.")
        self.device = "cuda" if preference != "cpu" and torch.cuda.is_available() else "cpu"
        if preference == "cuda" and self.device != "cuda":
            raise CutoutError("CUDA_UNAVAILABLE", "NVIDIA acceleration is unavailable. Choose Auto or CPU, or install the NVIDIA runtime and a compatible driver.")
        key = (model_id, self.device)
        if key != self.loaded_key:
            self.unload()
            job.progress("Loading model", device=self.device)
            checkpoint = self.models.verify(model_id, job)
            # Leave some CPU capacity for the desktop and video pipeline.
            torch.set_num_threads(max(1, min(8, (os.cpu_count() or 2) - 1)))
            self.predictor = build_sam2_video_predictor(self.models.get(model_id)["config"], str(checkpoint),
                                                       device=self.device, apply_postprocessing=False)
            self.predictor.fill_hole_area = 0  # No upstream optional CUDA connected-components extension.
            self.predictor.add_all_frames_to_correct_as_cond = True
            # Each run starts with fresh state and all corrections; clearing old state
            # is unnecessary (and the pinned upstream clear-helper has a naming bug).
            self.predictor.clear_non_cond_mem_around_input = False
            # Bound attention cost independently of how many correction frames are saved.
            self.predictor.max_cond_frames_in_attn = 4
            self.loaded_key = key

    def precision(self):
        import torch
        if self.device == "cuda":
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
            return torch.autocast("cuda", dtype=dtype)
        return contextlib.nullcontext()

    def state(self, project, directory: Path):
        frames = LazyFrames(project, self.predictor.image_size)
        # Upstream returns output masks at this size; export resizes to original dimensions.
        with Image.open(project.frame_path(0)) as first:
            width, height = first.size
        with patch("sam2.sam2_video_predictor.load_video_frames", return_value=(frames, height, width)):
            state = self.predictor.init_state(str(project.frames_dir), offload_video_to_cpu=True, offload_state_to_cpu=True)
        self.predictor._obj_id_to_idx(state, 1)
        store = state["output_dict_per_obj"][0]
        store["cond_frame_outputs"] = DiskState(directory / "conditioning")
        store["non_cond_frame_outputs"] = DiskState(directory / "tracking")
        return state

    def prompt(self, state, frame: int, prompt: dict):
        width, height = state["video_width"], state["video_height"]
        points = prompt["points"]
        box = prompt.get("box")
        return self.predictor.add_new_points_or_box(
            state, frame_idx=frame, obj_id=1,
            points=np.array([[p[0] * width, p[1] * height] for p in points], dtype=np.float32).reshape(-1, 2),
            labels=np.array([p[2] for p in points], dtype=np.int32),
            box=np.array([box[0] * width, box[1] * height, box[2] * width, box[3] * height], dtype=np.float32) if box else None,
            clear_old_points=True,
        )

    def save_prediction(self, project, frame: int, logits):
        # Segmentation logits are not calibrated alpha. Threshold, then apply explicit edge controls at render time.
        pixels = (logits[0, 0].detach().float().cpu().numpy() > 0).astype(np.uint8) * 255
        save_image(Image.fromarray(pixels), project.mask_path(frame))
        for old in (project.directory / "renders").glob(f"*-{frame:08d}.png"):
            old.unlink(missing_ok=True)

    def preview(self, project, frame: int, job: Job):
        self.load(project.data["model"], project.data["device"], job)
        job.progress("Updating selection", device=self.device)
        import torch
        prompt = project.data["prompts"].get(str(frame))
        if not prompt:
            return
        work = project.directory / "state" / job.id
        try:
            with torch.inference_mode(), self.precision():
                state = self.state(project, work)
                job.check()
                _, _, logits = self.prompt(state, frame, prompt)
                job.check()
                self.save_prediction(project, frame, logits)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def track(self, project, anchor: int, direction: str, job: Job):
        self.load(project.data["model"], project.data["device"], job)
        import torch
        start, end = project.data["in_frame"], project.data["out_frame"]
        prompts = {int(key): value for key, value in project.data["prompts"].items() if start <= int(key) <= end}
        if anchor not in prompts:
            raise CutoutError("SELECTION_REQUIRED", "Start tracking from a frame where you have drawn a selection.")
        passes = ([False, True] if direction == "both" else [direction == "backward"])
        total = (end - anchor + 1 if False in passes else 0) + (anchor - start if True in passes else 0)
        completed = 0
        for reverse in passes:
            work = project.directory / "state" / f"{job.id}-{'back' if reverse else 'forward'}"
            try:
                with torch.inference_mode(), self.precision():
                    state = self.state(project, work)
                    for frame, prompt in sorted(prompts.items()):
                        job.check()
                        self.prompt(state, frame, prompt)
                    limit = anchor - start if reverse else end - anchor
                    for frame, _, logits in self.predictor.propagate_in_video(
                            state, start_frame_idx=anchor, max_frame_num_to_track=limit, reverse=reverse):
                        job.check()
                        self.save_prediction(project, frame, logits)
                        if not reverse or frame != anchor:
                            completed += 1
                        job.progress("Tracking subject", completed, max(1, total), frame=frame, device=self.device)
            finally:
                shutil.rmtree(work, ignore_errors=True)
