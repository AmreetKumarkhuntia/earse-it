import contextlib
import json
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from PIL import Image

from .errors import CutoutError
from .jobs import Job
from .masks import alpha16, refine
from .media import binary, original_frames, process, quiet_flags
from .rendering import composite, output_size, validate_render


@lru_cache(maxsize=2)
def h264_encoder(ffmpeg: str) -> str:
    result = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True,
                            text=True, timeout=15, check=True, **quiet_flags())
    encoders = {fields[1] for line in result.stdout.splitlines() if len(fields := line.split()) >= 2}
    # OpenH264 is included in our Windows LGPL bundle. x264 supports Linux development.
    for name in ("libopenh264", "libx264"):
        if name in encoders:
            return name
    raise CutoutError("MEDIA_TOOLS_MISSING", "H.264 encoding is unavailable. Reinstall the media tools or export MOV/PNG.")


def rendered_frames(project, size, settings, job):
    source_size = project.data["media"]["width"], project.data["media"]["height"]
    with contextlib.closing(original_frames(project, job)) as frames:
        for frame, source in frames:
            job.check()
            with Image.open(project.mask_path(frame)) as mask:
                alpha = refine(mask, size, project.data["edge"], source_size)
            if source.size != size:
                source = source.resize(size, Image.Resampling.LANCZOS)
            yield composite(source, alpha, settings)


def export_sequence(project, destination, size, settings, job):
    media = project.data["media"]
    source_size = media["width"], media["height"]
    start, end = project.data["in_frame"], project.data["out_frame"]
    mask_only = settings["format"] == "mask_sequence"
    temporary = Path(tempfile.mkdtemp(prefix=".cutout-export-", dir=destination.parent))
    try:
        if mask_only:
            for number, frame in enumerate(range(start, end + 1)):
                job.check()
                with Image.open(project.mask_path(frame)) as mask:
                    alpha = refine(mask, size, project.data["edge"], source_size)
                alpha16(alpha).save(temporary / f"mask_{number:08d}.png")
                job.progress("Exporting masks", number + 1, end - start + 1)
        else:
            with contextlib.closing(rendered_frames(project, size, settings, job)) as frames:
                for number, image in enumerate(frames):
                    image.save(temporary / f"frame_{number:08d}.png")
                    job.progress("Exporting PNG frames", number + 1, end - start + 1)
        interpretation = "16-bit grayscale, full range; white = keep; no audio" if mask_only else (
            "8-bit RGBA, straight alpha; no audio" if settings["background"] == "transparent" else "8-bit RGB; no audio")
        metadata = {"schema_version": 1, "fps_num": media["fps_num"], "fps_den": media["fps_den"],
                    "frame_count": end - start + 1, "width": size[0], "height": size[1],
                    "source_in_frame": start, "source": project.data["source"],
                    "render": settings, "interpretation": interpretation}
        (temporary / "timing.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        job.check()
        destination.mkdir()
        try:
            for item in temporary.iterdir():
                job.check()
                os.replace(item, destination / item.name)
        except BaseException:
            shutil.rmtree(destination, ignore_errors=True)
            raise
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def export_movie(project, destination, size, settings, job):
    media = project.data["media"]
    start, end = project.data["in_frame"], project.data["out_frame"]
    prores = settings["format"] == "prores"
    suffix = ".mov" if prores else ".mp4"
    if destination.suffix.lower() != suffix:
        raise CutoutError("INVALID_INPUT", f"This video format needs a {suffix} filename.")
    if not prores and any(dimension % 2 for dimension in size):
        raise CutoutError("INVALID_INPUT", "MP4 needs even dimensions. Choose a resolution preset, or MOV/PNG for exact native pixels.")
    ffmpeg = binary("ffmpeg")
    codec = "prores_ks" if prores else h264_encoder(ffmpeg)
    quality = settings["quality"]
    frame_time = media["fps_den"] / media["fps_num"]
    args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgba" if prores else "rgb24", "-s", f"{size[0]}x{size[1]}",
            "-r", f"{media['fps_num']}/{media['fps_den']}", "-i", "pipe:0"]
    include_audio = settings["audio"] and media["has_audio"]
    if include_audio:
        args += ["-ss", f"{start * frame_time:.12f}", "-i", project.data["source"]]
    args += ["-map", "0:v:0", "-c:v", codec,
             "-vf", "scale=in_range=full:out_range=tv:out_color_matrix=bt709,setsar=1",
             "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    if prores:
        args += ["-profile:v", "4", "-pix_fmt", "yuva444p10le", "-alpha_bits", "16",
                 "-qscale:v", str({"standard": 7, "high": 4, "maximum": 2}[quality])]
    else:
        args += ["-pix_fmt", "yuv420p", "-profile:v", "high"]
        if codec == "libopenh264":
            bitrate = round(size[0] * size[1] / frame_time * {"standard": .08, "high": .16, "maximum": .28}[quality])
            args += ["-b:v", str(max(500_000, min(200_000_000, bitrate))), "-rc_mode", "quality"]
        else:
            args += ["-preset", "medium", "-crf", str({"standard": 24, "high": 18, "maximum": 14}[quality])]
    if include_audio:
        args += ["-map", "1:a:0?", "-c:a", "pcm_s16le" if prores else "aac",
                 "-af", "aresample=async=1:first_pts=0,apad"]
        if not prores:
            args += ["-b:a", "192k"]
    else:
        args += ["-an"]
    args += ["-t", f"{(end - start + 1) * frame_time:.12f}", "-movflags", "+faststart"]
    fd, name = tempfile.mkstemp(prefix=".cutout-export-", suffix=suffix, dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        with process([*args, str(temporary)], job, stdin=subprocess.PIPE) as encoder:
            with contextlib.closing(rendered_frames(project, size, settings, job)) as frames:
                for number, image in enumerate(frames):
                    encoder.stdin.write(image.convert("RGBA" if prores else "RGB").tobytes())
                    job.progress("Exporting cutout" if settings["background"] == "transparent" else "Rendering video",
                                 number + 1, end - start + 1)
            encoder.stdin.close()
            encoder.stdin = None
            job.progress("Finalizing video")
        job.check()
        # Never replace an existing destination, including a file created mid-render.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def export(project, destination: Path, format: str, job: Job, options=None):
    job.check()
    project.check_source()
    settings = validate_render(project.data.get("render") if options is None else options)
    settings = validate_render({**settings, "format": format})
    if destination.exists():
        raise CutoutError("FILE_EXISTS", "That output already exists. Choose a new output name.")
    if not destination.parent.is_dir():
        raise CutoutError("OUTPUT_MISSING", "Choose an existing output directory.")
    media = project.data["media"]
    start, end = project.data["in_frame"], project.data["out_frame"]
    if any(not project.mask_path(frame).exists() for frame in range(start, end + 1)):
        raise CutoutError("INCOMPLETE_MASKS", "Track every frame in the selected range before exporting. Use both directions from a selection frame.")
    if shutil.disk_usage(destination.parent).free < 256 * 1024 * 1024:
        raise CutoutError("DISK_FULL", "Free at least 256 MB in the output drive before exporting.")
    size = output_size((media["width"], media["height"]), settings["resolution"])
    if format in ("mask_sequence", "png_sequence"):
        export_sequence(project, destination, size, settings, job)
    else:
        export_movie(project, destination, size, settings, job)
    return {"path": str(destination), "frames": end - start + 1, "format": format,
            "width": size[0], "height": size[1]}
