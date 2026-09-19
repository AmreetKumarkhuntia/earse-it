import json
import subprocess

import numpy as np
import pytest
from PIL import Image

from erase_it.errors import Cancelled, CutoutError
from erase_it.export import export
from erase_it.jobs import Job
from erase_it.masks import render_frame, save_image
from erase_it.media import binary, original_frames
from erase_it.project import Project
from erase_it.rendering import DEFAULT_RENDER, output_size, validate_render
from erase_it.service import Service


def ready(project):
    mask = Image.new("L", (96, 64), 0)
    mask.paste(255, (0, 0, 48, 64))
    for frame in range(project.data["media"]["frame_count"]):
        save_image(mask, project.mask_path(frame))
    project.data.update(edge={"grow": 0, "feather": 0, "invert": False}, in_frame=2, out_frame=5)


@pytest.mark.parametrize("resolution,expected", [
    ("native", (1920, 1080)), ("720p", (1280, 720)), ("1080p", (1920, 1080)),
    ("1440p", (2560, 1440)), ("2k", (1920, 1080)), ("4k", (3840, 2160)),
])
def test_resolution_preserves_landscape_and_portrait(resolution, expected):
    assert output_size((1920, 1080), resolution) == expected
    assert output_size((1080, 1920), resolution) == expected[::-1]


def test_native_keeps_odd_pixels_and_presets_fit_non_widescreen_sources():
    assert output_size((101, 67), "native") == (101, 67)
    assert output_size((4096, 2160), "2k") == (2048, 1080)
    assert output_size((1920, 1920), "720p") == (720, 720)
    assert output_size((96, 64), "720p") == (1080, 720)


@pytest.mark.parametrize("settings", [
    {"format": "avi"}, {"format": "mp4"}, {"resolution": "8k"}, {"quality": "ultra"},
    {"color": "red"}, {"audio": "false"}, {"background": ["green"]}, {"width": 100}, [],
])
def test_invalid_render_settings_are_rejected(settings):
    with pytest.raises(CutoutError):
        validate_render(settings)


def test_render_settings_save_reopen_and_do_not_invalidate_tracking(project, job):
    ready(project)
    before = project.mask_path(2).read_bytes()
    revision = project.data["revision"]
    service = Service(project.root)
    service.project = project
    settings = validate_render({"format": "mp4", "background": "green", "resolution": "1080p", "audio": False})
    result = service.settings({"render": settings}, job)
    assert result["render"] == settings and result["revision"] == revision
    assert project.mask_path(2).read_bytes() == before
    reopened = Project.load(project.root, project.directory / "project.cutout")
    assert reopened.data["render"] == settings
    assert reopened.summary()["tracked_ranges"] == [[0, 7]]
    with pytest.raises(CutoutError):
        service.settings({"render": {"format": "mp4", "background": "transparent"}}, job)
    assert project.data["render"] == settings
    # Existing projects have no rendering field and keep the old export behavior.
    project.data.pop("render")
    project.save()
    assert Project.load(project.root, project.directory / "project.cutout").data["render"] == DEFAULT_RENDER


@pytest.mark.parametrize("background,color", [
    ("green", (0, 255, 0)), ("blue", (0, 0, 255)), ("black", (0, 0, 0)),
    ("white", (255, 255, 255)), ("custom", (171, 34, 204)),
])
def test_png_and_preview_use_the_selected_background(project, tmp_path, job, background, color):
    ready(project)
    project.data["render"] = validate_render({"format": "png_sequence", "background": background, "color": "#ab22cc"})
    preview = render_frame(project, 2, "render")
    with Image.open(preview["path"]) as image:
        assert image.getpixel((90, 30)) == color
    destination = tmp_path / "frames"
    export(project, destination, "png_sequence", job)
    with Image.open(destination / "frame_00000000.png") as image:
        assert image.mode == "RGB" and image.getpixel((90, 30)) == color
    assert len(list(destination.glob("*.png"))) == 4
    metadata = json.loads((destination / "timing.json").read_text())
    assert metadata["source_in_frame"] == 2 and metadata["fps_num"] == 4
    assert metadata["render"]["background"] == background


def test_transparent_png_sequence_preserves_original_rgb_and_alpha(project, tmp_path, job):
    ready(project)
    original = next(original_frames(project, job))[1]
    destination = tmp_path / "transparent"
    export(project, destination, "png_sequence", job)
    with Image.open(destination / "frame_00000000.png") as image:
        assert image.mode == "RGBA"
        assert image.getpixel((10, 10)) == (*original.getpixel((10, 10)), 255)
        assert image.getpixel((90, 30))[3] == 0


@pytest.mark.parametrize("resolution,expected", [("native", (96, 64)), ("1080p", (1620, 1080)),
                                                ("1440p", (2160, 1440)), ("2k", (1620, 1080)), ("4k", (3240, 2160))])
def test_mp4_renders_each_size_preset(project, tmp_path, job, resolution, expected):
    ready(project)
    project.data.update(out_frame=2)
    destination = tmp_path / "size.mp4"
    export(project, destination, "mp4", job, options={"background": "green", "resolution": resolution})
    info = json.loads(subprocess.check_output([binary("ffprobe"), "-v", "error", "-show_streams", "-of", "json", str(destination)]))
    assert (info["streams"][0]["width"], info["streams"][0]["height"]) == expected


@pytest.mark.parametrize("background,audio", [("green", True), ("blue", False), ("custom", True)])
def test_mp4_background_audio_and_trim_round_trip(project, tmp_path, job, background, audio):
    ready(project)
    settings = {"format": "mp4", "background": background, "color": "#ab22cc", "audio": audio, "resolution": "720p"}
    destination = tmp_path / "render.mp4"
    result = export(project, destination, "mp4", job, options=settings)
    info = json.loads(subprocess.check_output([binary("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(destination)]))
    video = info["streams"][0]
    assert video["codec_name"] == "h264"
    assert (video["width"], video["height"], int(video["nb_frames"])) == (1080, 720, 4)
    assert (result["width"], result["height"]) == (1080, 720)
    assert bool([s for s in info["streams"] if s["codec_type"] == "audio"]) == audio
    assert abs(float(info["format"]["duration"]) - 1) < .25
    raw = subprocess.check_output([binary("ffmpeg"), "-v", "error", "-i", str(destination), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"])
    pixels = np.frombuffer(raw, np.uint8).reshape(720, 1080, 3)
    expected = {"green": (0, 255, 0), "blue": (0, 0, 255), "custom": (171, 34, 204)}[background]
    np.testing.assert_allclose(pixels[100:500, 900:1000].mean(axis=(0, 1)), expected, atol=7)


@pytest.mark.parametrize("format", ["prores", "mp4", "png_sequence", "mask_sequence"])
def test_cancel_during_render_removes_partial_outputs(project, tmp_path, format):
    ready(project)
    job = Job("cancel-render", lambda event: job.cancel() if event["current"] == 1 else None)
    target = tmp_path / ("video.mov" if format == "prores" else "video.mp4" if format == "mp4" else "frames")
    with pytest.raises(Cancelled):
        export(project, target, format, job, options={"background": "green"})
    assert not target.exists()
    assert not list(tmp_path.glob(".cutout-export-*"))
    assert not job._processes
