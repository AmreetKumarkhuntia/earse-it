import json
import math
import os
import re
import tempfile
import uuid
from pathlib import Path

from .errors import CutoutError
from .rendering import validate_render


def atomic_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".cutout-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def integer(value, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise CutoutError("INVALID_INPUT", f"{name} must be an integer from {minimum} to {maximum}.")
    return value


def number(value, name: str, minimum: float, maximum: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise CutoutError("INVALID_INPUT", f"{name} must be between {minimum} and {maximum}.")
    return float(value)


def validate_prompts(value, frame_count: int) -> dict:
    if not isinstance(value, dict) or len(value) > 256:
        raise CutoutError("INVALID_INPUT", "Use at most 256 correction frames per project.")
    cleaned = {}
    for key, prompt in value.items():
        if not isinstance(key, str) or not key.isdecimal() or str(int(key)) != key:
            raise CutoutError("INVALID_INPUT", "Invalid correction frame.")
        integer(int(key), "Frame", 0, frame_count - 1)
        if not isinstance(prompt, dict):
            raise CutoutError("INVALID_INPUT", "Invalid selection.")
        points = prompt.get("points", [])
        if not isinstance(points, list) or len(points) > 128:
            raise CutoutError("INVALID_INPUT", "Use at most 128 selection points per frame.")
        parsed_points = []
        for point in points:
            if not isinstance(point, list) or len(point) != 3:
                raise CutoutError("INVALID_INPUT", "Invalid stroke point.")
            parsed_points.append([number(point[0], "X", 0, 1), number(point[1], "Y", 0, 1),
                                  integer(point[2], "Point label", 0, 1)])
        box = prompt.get("box")
        if box is not None:
            if not isinstance(box, list) or len(box) != 4:
                raise CutoutError("INVALID_INPUT", "Invalid selection box.")
            box = [number(v, "Box coordinate", 0, 1) for v in box]
            if box[0] >= box[2] or box[1] >= box[3]:
                raise CutoutError("INVALID_INPUT", "Draw a box with a nonzero width and height.")
        if parsed_points or box:
            cleaned[key] = {"points": parsed_points, "box": box}
    return cleaned


def validate_edge(value: dict) -> dict:
    if not isinstance(value, dict) or type(value.get("invert", False)) is not bool:
        raise CutoutError("INVALID_INPUT", "Invalid edge settings.")
    return {"feather": number(value.get("feather", 1), "Feather", 0, 20),
            "grow": integer(value.get("grow", 0), "Grow/shrink", -20, 20),
            "invert": value.get("invert", False)}


def ranges(frames) -> list[list[int]]:
    result: list[list[int]] = []
    for frame in sorted(set(frames)):
        if result and result[-1][1] + 1 == frame:
            result[-1][1] = frame
        else:
            result.append([frame, frame])
    return result


class Project:
    def __init__(self, root: Path, data: dict, project_file: Path | None = None):
        self.root = root
        self.data = data
        self.project_file = project_file
        if not re.fullmatch(r"[0-9a-f]{32}", data.get("id", "")):
            raise CutoutError("INVALID_PROJECT", "Invalid project identifier.")
        self.directory = root / "projects" / data["id"]

    @classmethod
    def create(cls, root: Path, source: Path, media: dict):
        stat = source.stat()
        return cls(root, {
            "schema_version": 1, "id": uuid.uuid4().hex, "name": source.stem,
            "source": str(source), "source_size": stat.st_size, "source_mtime_ns": stat.st_mtime_ns,
            "media": media, "in_frame": 0, "out_frame": max(0, media["frame_count"] - 1),
            "model": "tiny", "device": "auto", "edge": {"feather": 1.0, "grow": 0, "invert": False},
            "render": validate_render(),
            "prompts": {}, "revision": 0,
        })

    @classmethod
    def load(cls, root: Path, path: Path):
        try:
            if path.stat().st_size > 4 * 1024 * 1024:
                raise CutoutError("INVALID_PROJECT", "Project file is too large.")
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("schema_version") != 1:
                raise CutoutError("INVALID_PROJECT", "This project version is not supported.")
            project = cls(root, data, path.resolve())
            source = Path(data["source"])
            stat = source.stat()
            if stat.st_size != data["source_size"] or stat.st_mtime_ns != data["source_mtime_ns"]:
                raise CutoutError("SOURCE_CHANGED", "The source video changed. Import it as a new project to avoid misaligned masks.")
            count = integer(data["media"]["frame_count"], "Frame count", 1, 10_000_000)
            integer(data["media"]["width"], "Width", 1, 16384)
            integer(data["media"]["height"], "Height", 1, 16384)
            integer(data["media"]["fps_num"], "Frame rate numerator", 1, 1_000_000)
            integer(data["media"]["fps_den"], "Frame rate denominator", 1, 1_000_000)
            data["prompts"] = validate_prompts(data["prompts"], count)
            data["edge"] = validate_edge(data["edge"])
            data["render"] = validate_render(data.get("render"))
            integer(data["in_frame"], "In frame", 0, count - 1)
            integer(data["out_frame"], "Out frame", data["in_frame"], count - 1)
            integer(data["revision"], "Revision", 0, 1_000_000)
            if data["model"] not in ("tiny", "base_plus") or data["device"] not in ("auto", "cpu", "cuda"):
                raise CutoutError("INVALID_PROJECT", "Unsupported processing settings.")
            return project
        except CutoutError:
            raise
        except FileNotFoundError:
            raise CutoutError("SOURCE_MISSING", "The project or its original video cannot be found. Restore it to its original location.")
        except (KeyError, TypeError, ValueError):
            raise CutoutError("INVALID_PROJECT", "This is not a valid erase-it project.")

    @property
    def frames_dir(self):
        return self.directory / "frames"

    @property
    def masks_dir(self):
        return self.directory / "masks" / str(self.data["revision"])

    def frame_path(self, frame: int):
        return self.frames_dir / f"{frame:08d}.jpg"

    def check_source(self):
        try:
            stat = Path(self.data["source"]).stat()
        except FileNotFoundError:
            raise CutoutError("SOURCE_MISSING", "The original video is missing. Restore it to its original location.")
        if stat.st_size != self.data["source_size"] or stat.st_mtime_ns != self.data["source_mtime_ns"]:
            raise CutoutError("SOURCE_CHANGED", "The source video changed. Import it as a new project to avoid misaligned masks.")

    def mask_path(self, frame: int):
        return self.masks_dir / f"{frame:08d}.png"

    def save(self):
        canonical = self.directory / "project.cutout"
        atomic_json(canonical, self.data)
        if self.project_file and self.project_file != canonical:
            atomic_json(self.project_file, self.data)
        atomic_json(self.root / "last-project.json", {"path": str(self.project_file or canonical)})

    def summary(self):
        frames = [int(p.stem) for p in self.masks_dir.glob("*.png") if p.stem.isdecimal()]
        return {**self.data, "project_file": str(self.project_file) if self.project_file else None,
                "tracked_ranges": ranges(frames), "directory": str(self.directory),
                "proxy": str(self.directory / "preview.webm")}
