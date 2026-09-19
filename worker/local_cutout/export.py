import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from .errors import CutoutError
from .jobs import Job
from .masks import alpha16, refine
from .media import binary, original_frames, process


def export(project, destination: Path, format: str, job: Job):
    project.check_source()
    if format not in ("prores", "mask_sequence"):
        raise CutoutError("INVALID_INPUT", "Choose ProRes 4444 or a mask sequence.")
    if destination.exists():
        raise CutoutError("FILE_EXISTS", "That output already exists. Choose a new output name.")
    if not destination.parent.is_dir():
        raise CutoutError("OUTPUT_MISSING", "Choose an existing output directory.")
    media = project.data["media"]
    start, end = project.data["in_frame"], project.data["out_frame"]
    count = end - start + 1
    if any(not project.mask_path(frame).exists() for frame in range(start, end + 1)):
        raise CutoutError("INCOMPLETE_MASKS", "Track every frame in the selected range before exporting. Use both directions from a selection frame.")
    if shutil.disk_usage(destination.parent).free < 256 * 1024 * 1024:
        raise CutoutError("DISK_FULL", "Free at least 256 MB in the output drive before exporting.")
    size = media["width"], media["height"]
    if format == "mask_sequence":
        temporary = Path(tempfile.mkdtemp(prefix=".cutout-export-", dir=destination.parent))
        try:
            for number, frame in enumerate(range(start, end + 1)):
                job.check()
                with Image.open(project.mask_path(frame)) as mask:
                    alpha = refine(mask, size, project.data["edge"], size)
                alpha16(alpha).save(temporary / f"mask_{number:08d}.png")
                job.progress("Exporting masks", number + 1, count)
            metadata = {"schema_version": 1, "fps_num": media["fps_num"], "fps_den": media["fps_den"],
                        "frame_count": count, "width": size[0], "height": size[1],
                        "source_in_frame": start, "source": project.data["source"],
                        "interpretation": "16-bit grayscale, full range; white = keep; no audio"}
            (temporary / "timing.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            job.check()
            # Reserve the destination exclusively, then move our files into it.
            destination.mkdir()
            try:
                for item in temporary.iterdir():
                    os.replace(item, destination / item.name)
            except Exception:
                shutil.rmtree(destination, ignore_errors=True)
                raise
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
    else:
        if destination.suffix.lower() != ".mov":
            raise CutoutError("INVALID_INPUT", "Transparent ProRes exports must use a .mov filename.")
        fd, name = tempfile.mkstemp(prefix=".cutout-export-", suffix=".mov", dir=destination.parent)
        os.close(fd)
        temporary = Path(name)
        fps = f"{media['fps_num']}/{media['fps_den']}"
        frame_time = media["fps_den"] / media["fps_num"]
        args = [binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{size[0]}x{size[1]}", "-r", fps, "-i", "pipe:0",
                "-ss", f"{start * frame_time:.12f}", "-i", project.data["source"],
                "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "prores_ks", "-profile:v", "4",
                "-vf", "scale=in_range=full:out_range=tv:out_color_matrix=bt709",
                "-pix_fmt", "yuva444p10le", "-alpha_bits", "16", "-qscale:v", "4",
                "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                "-c:a", "pcm_s16le", "-af", "aresample=async=1:first_pts=0,apad",
                "-t", f"{count * frame_time:.12f}", "-movflags", "+faststart", str(temporary)]
        try:
            with process(args, job, stdin=subprocess.PIPE) as encoder:
                for number, (frame, source) in enumerate(original_frames(project, job)):
                    with Image.open(project.mask_path(frame)) as mask:
                        alpha = refine(mask, size, project.data["edge"], size)
                    rgba = source.convert("RGBA")
                    # Straight/unassociated alpha: retain source RGB at the boundary.
                    rgba.putalpha(alpha)
                    encoder.stdin.write(rgba.tobytes())
                    job.progress("Exporting cutout", number + 1, count)
                encoder.stdin.close()
                encoder.stdin = None
            job.check()
            # An atomic no-replace publication on NTFS/ext4; never overwrite existing user data.
            os.link(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return {"path": str(destination), "frames": count, "format": format}
