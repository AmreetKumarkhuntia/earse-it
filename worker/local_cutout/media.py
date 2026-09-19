import contextlib
import json
import math
import os
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image

from .errors import CutoutError
from .jobs import Job


def binary(name: str) -> str:
    override = os.environ.get(f"LOCAL_CUTOUT_{name.upper()}")
    found = override or shutil.which(name)
    if not found or not Path(found).is_file():
        raise CutoutError("MEDIA_TOOLS_MISSING", f"{name} is unavailable. Reinstall the media tools, or set LOCAL_CUTOUT_{name.upper()} for development.")
    return found


def quiet_flags():
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def probe(source: Path, requested_fps: str | None = None) -> dict:
    if not source.is_file():
        raise CutoutError("SOURCE_MISSING", "Choose an existing local video file.")
    try:
        result = subprocess.run([binary("ffprobe"), "-v", "error", "-show_streams", "-show_format",
                                 "-of", "json", str(source)], capture_output=True, timeout=30, **quiet_flags())
        info = json.loads(result.stdout)
        video = next(s for s in info["streams"] if s["codec_type"] == "video"
                     and not s.get("disposition", {}).get("attached_pic"))
    except (ValueError, KeyError, StopIteration, subprocess.TimeoutExpired):
        raise CutoutError("INVALID_VIDEO", "FFmpeg could not read a video stream from this file.")
    if video.get("color_transfer") in ("smpte2084", "arib-std-b67"):
        raise CutoutError("HDR_UNSUPPORTED", "This is HDR footage. Export an SDR Rec.709 version from your editor before importing it.")
    if video.get("field_order", "unknown") not in ("progressive", "unknown"):
        raise CutoutError("INTERLACED_UNSUPPORTED", "Convert interlaced footage to progressive video before importing it.")
    try:
        fps = Fraction(requested_fps or video.get("r_frame_rate", "0/1"))
        if not 1 <= fps <= 120:
            fps = Fraction(video.get("avg_frame_rate", "30/1"))
        if not 1 <= fps <= 120:
            raise ValueError()
        fps = fps.limit_denominator(100_000)
        duration = float(video.get("duration") or info["format"]["duration"])
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError()
    except (ValueError, ZeroDivisionError, KeyError):
        raise CutoutError("INVALID_VIDEO", "Could not determine the duration or a usable frame rate (1–120 fps).")
    width, height = int(video["width"]), int(video["height"])
    sar = video.get("sample_aspect_ratio", "1:1")
    if sar not in ("N/A", "0:1", "1:1"):
        width = max(1, round(width * float(Fraction(sar.replace(":", "/")))))
    rotation = int(video.get("tags", {}).get("rotate", 0))
    for side in video.get("side_data_list", []):
        if "rotation" in side:
            rotation = int(side["rotation"])
    if abs(rotation) % 180 == 90:
        width, height = height, width
    if max(width, height) > 8192:
        raise CutoutError("RESOLUTION_UNSUPPORTED", "This release supports video dimensions up to 8192 pixels.")
    average = video.get("avg_frame_rate", "0/1")
    return {"width": width, "height": height, "video_stream": video["index"], "fps_num": fps.numerator, "fps_den": fps.denominator,
            "duration": duration, "frame_count": max(1, math.ceil(duration * fps)),
            "has_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
            "normalized_timing": average != str(fps), "color_space": "bt709"}


@contextlib.contextmanager
def process(args: list[str], job: Job, *, stdin=None, stdout=None):
    with tempfile.TemporaryFile() as errors:
        child = subprocess.Popen(args, stdin=stdin or subprocess.DEVNULL, stdout=stdout or subprocess.DEVNULL,
                                 stderr=errors, **quiet_flags())
        job.register(child)
        try:
            yield child
            while child.poll() is None:
                job.check()
                try:
                    child.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass
            job.check()
            if child.returncode:
                errors.seek(0)
                detail = errors.read().decode("utf-8", errors="replace")[-3000:]
                raise CutoutError("MEDIA_FAILED", f"FFmpeg could not finish this operation. {detail}")
        finally:
            if child.poll() is None:
                child.kill()
            child.wait()
            for stream in (child.stdin, child.stdout):
                if stream:
                    stream.close()
            job.unregister(child)


def fps_filter(media: dict) -> str:
    return f"fps={media['fps_num']}/{media['fps_den']}:start_time=0"


def prepare(project, job: Job):
    """One normalized frame sequence owns all preview, prompt and export indices."""
    job.check()
    media = project.data["media"]
    frames = project.frames_dir
    frames.mkdir(parents=True, exist_ok=True)
    complete = project.directory / "prepared.json"
    if complete.exists():
        try:
            cached = json.loads(complete.read_text())
        except (ValueError, OSError):
            cached = {}
        if cached.get("frame_count") == media["frame_count"] and project.frame_path(0).exists() and project.frame_path(media["frame_count"] - 1).exists():
            return
        complete.unlink(missing_ok=True)
    # A cancelled import can safely be rebuilt; there are no masks for a new project.
    for old in frames.glob("*.jpg"):
        old.unlink()
    scale = min(1, 1280 / max(media["width"], media["height"]))
    width, height = max(2, round(media["width"] * scale / 2) * 2), max(2, round(media["height"] * scale / 2) * 2)
    proxy_part = project.directory / "preview.part.webm"
    filter_graph = f"[0:{media.get('video_stream', 0)}]{fps_filter(media)},scale={width}:{height},setsar=1,split=2[frames][proxy]"
    args = [binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", project.data["source"],
            "-filter_complex", filter_graph, "-map", "[frames]", "-q:v", "2", "-start_number", "0",
            str(frames / "%08d.jpg"), "-map", "[proxy]", "-map", "0:a:0?", "-c:v", "libvpx-vp9",
            "-deadline", "realtime", "-cpu-used", "8", "-crf", "36", "-b:v", "0", "-pix_fmt", "yuv420p",
            "-c:a", "libopus", "-b:a", "96k", "-progress", "pipe:1", str(proxy_part)]
    try:
        with process(args, job, stdout=subprocess.PIPE) as child:
            for raw in child.stdout:
                job.check()
                text = raw.decode("utf-8", errors="replace").strip()
                if text.startswith("frame="):
                    job.progress("Preparing video", int(text[6:]), media["frame_count"])
        count = sum(1 for _ in frames.glob("*.jpg"))
        if not count:
            raise CutoutError("INVALID_VIDEO", "The video did not contain any decodable frames.")
        media["frame_count"] = count
        media["duration"] = count * media["fps_den"] / media["fps_num"]
        project.data["out_frame"] = min(project.data["out_frame"], count - 1)
        os.replace(proxy_part, project.directory / "preview.webm")
        from .project import atomic_json
        atomic_json(complete, {"frame_count": count})
    finally:
        proxy_part.unlink(missing_ok=True)


def read_exact(stream, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        chunk = stream.read(size - len(result))
        if not chunk:
            break
        result.extend(chunk)
    return bytes(result)


def original_frames(project, job: Job):
    media = project.data["media"]
    width, height = media["width"], media["height"]
    start, end = project.data["in_frame"], project.data["out_frame"]
    # Match import normalization before selection; seeking first can change VFR sampling.
    filters = f"{fps_filter(media)},scale={width}:{height},setsar=1,select=between(n\\,{start}\\,{end})"
    args = [binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-i", project.data["source"],
            "-map", f"0:{media.get('video_stream', 0)}", "-vf", filters, "-fps_mode", "passthrough", "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    with process(args, job, stdout=subprocess.PIPE) as child:
        for frame in range(start, end + 1):
            job.check()
            raw = read_exact(child.stdout, width * height * 3)
            if len(raw) != width * height * 3:
                job.check()
                raise CutoutError("DECODE_FAILED", f"Could not decode source frame {frame + 1}.")
            yield frame, Image.fromarray(np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3))
