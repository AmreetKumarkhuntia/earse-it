import json
import subprocess

import numpy as np
import pytest
from PIL import Image

from erase_it.errors import Cancelled, CutoutError
from erase_it.export import export
from erase_it.masks import refine, save_image
from erase_it.media import binary, original_frames, prepare
from erase_it.media import probe
from erase_it.project import Project


def fill_masks(project):
    mask = Image.new("L", (96, 64), 0)
    mask.paste(255, (0, 0, 48, 64))
    for index in range(project.data["media"]["frame_count"]):
        save_image(mask, project.mask_path(index))
    project.data["edge"] = {"grow": 0, "feather": 0, "invert": False}


def test_import_and_export_use_identical_frame_indices(project, job):
    assert project.data["media"]["frame_count"] == 8
    assert len(list(project.frames_dir.glob("*.jpg"))) == 8
    project.data.update(in_frame=2, out_frame=5)
    decoded = list(original_frames(project, job))
    assert [index for index, image in decoded] == [2, 3, 4, 5]
    assert all(image.size == (96, 64) for _, image in decoded)


def test_feather_grow_and_invert_are_applied_to_alpha_only():
    mask = Image.new("L", (20, 20), 0)
    mask.paste(255, (5, 5, 15, 15))
    expanded = np.asarray(refine(mask, (20, 20), {"grow": 2, "feather": 0, "invert": False}, (20, 20)))
    assert np.count_nonzero(expanded) == 196
    inverted = np.asarray(refine(mask, (20, 20), {"grow": 0, "feather": 0, "invert": True}, (20, 20)))
    assert inverted[0, 0] == 255 and inverted[10, 10] == 0
    feathered = np.asarray(refine(mask, (20, 20), {"grow": 0, "feather": 2, "invert": False}, (20, 20)))
    assert np.any((feathered > 0) & (feathered < 255))


def test_alpha_movie_round_trip_preserves_audio_duration_and_dimensions(project, tmp_path, job):
    fill_masks(project)
    project.data.update(in_frame=2, out_frame=5)
    target = tmp_path / "cutout.mov"
    export(project, target, "prores", job)
    info = json.loads(subprocess.check_output([binary("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(target)]))
    video, audio = info["streams"]
    assert video["codec_name"] == "prores" and "4444" in video["profile"]
    assert (video["width"], video["height"], int(video["nb_frames"])) == (96, 64, 4)
    assert audio["codec_name"] == "pcm_s16le"
    assert abs(float(info["format"]["duration"]) - 1) < .25
    raw = subprocess.check_output([binary("ffmpeg"), "-v", "error", "-i", str(target), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "pipe:1"])
    alpha = np.frombuffer(raw, np.uint8).reshape(64, 96, 4)[:, :, 3]
    assert alpha[:, :40].min() >= 254
    assert alpha[:, 55:].max() <= 1
    with pytest.raises(CutoutError, match="already exists"):
        export(project, target, "prores", job)


def test_png_sequence_is_lossless_and_includes_timing(project, tmp_path, job):
    fill_masks(project)
    project.data.update(in_frame=1, out_frame=3)
    target = tmp_path / "masks"
    export(project, target, "mask_sequence", job)
    assert len(list(target.glob("*.png"))) == 3
    with Image.open(target / "mask_00000000.png") as image:
        alpha = np.asarray(image)
        assert alpha.max() == 65535 and alpha.min() == 0
    timing = json.loads((target / "timing.json").read_text())
    assert timing["fps_num"] == 4 and timing["source_in_frame"] == 1


def test_export_refuses_missing_masks_and_cancellation_keeps_no_final_file(project, tmp_path, job):
    with pytest.raises(CutoutError, match="every frame"):
        export(project, tmp_path / "out.mov", "prores", job)
    fill_masks(project)
    job.cancel()
    with pytest.raises(Cancelled):
        export(project, tmp_path / "out.mov", "prores", job)
    assert not (tmp_path / "out.mov").exists()
    assert not list(tmp_path.glob(".cutout-export-*"))


def test_cancelled_preparation_does_not_mark_cache_complete(project, job):
    (project.directory / "prepared.json").unlink()
    job.cancel()
    with pytest.raises(Cancelled):
        prepare(project, job)
    assert not (project.directory / "prepared.json").exists()


def test_4k_export_preserves_original_resolution(tmp_path, job):
    source = tmp_path / "4k.mkv"
    subprocess.run([binary("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=3840x2160:r=1:d=1",
                    "-c:v", "ffv1", str(source)], check=True)
    project = Project.create(tmp_path / "data", source, probe(source))
    fill_masks(project)
    target = tmp_path / "4k-cutout.mov"
    export(project, target, "prores", job)
    info = json.loads(subprocess.check_output([binary("ffprobe"), "-v", "error", "-show_streams", "-of", "json", str(target)]))
    assert (info["streams"][0]["width"], info["streams"][0]["height"]) == (3840, 2160)


def test_changed_source_is_rejected_before_export(project, tmp_path, job):
    fill_masks(project)
    with open(project.data["source"], "ab") as stream:
        stream.write(b"changed")
    with pytest.raises(CutoutError, match="source video changed"):
        export(project, tmp_path / "out.mov", "prores", job)
