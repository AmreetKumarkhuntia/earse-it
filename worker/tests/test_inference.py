import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from local_cutout.inference import DiskState, Engine, LazyFrames
from local_cutout.models import Models
from local_cutout.project import Project


def test_spilled_state_retains_in_place_mutations(tmp_path):
    torch = pytest.importorskip("torch")
    state = DiskState(tmp_path, limit=1)
    state[0] = {"tensor": torch.tensor([1.0])}
    state[0]["tensor"] += 2
    state[1] = {"tensor": torch.tensor([9.0])}
    assert state[0]["tensor"].item() == 3
    assert len(state.cache) == 1
    del state[0]
    assert 0 not in state and not (tmp_path / "0.pt").exists()


@pytest.mark.inference
def test_real_sam2_cpu_selection_and_bidirectional_tracking(tmp_path, job):
    pytest.importorskip("sam2")
    models = Models(Path(os.environ.get("LOCAL_CUTOUT_TEST_MODELS", ".cache/inference")))
    if not models.path("tiny").exists():
        pytest.skip("Download Tiny and set LOCAL_CUTOUT_TEST_MODELS for the real inference test")
    source = tmp_path / "source.placeholder"
    source.write_bytes(b"test frames generated below")
    project = Project.create(tmp_path, source, {"width": 256, "height": 160, "fps_num": 3, "fps_den": 1,
                                             "frame_count": 3, "duration": 1, "has_audio": False})
    project.frames_dir.mkdir(parents=True)
    for index in range(3):
        image = Image.new("RGB", (256, 160), (30, 45, 60))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((75+index*3, 35, 180+index*3, 135), radius=20, fill=(215, 160, 40))
        image.save(project.frame_path(index))
    project.data["prompts"] = {"1": {"points": [[.5, .5, 1]], "box": [.28, .20, .76, .87]}}
    project.data["device"] = "cpu"
    engine = Engine(models)
    engine.preview(project, 1, job)
    engine.track(project, 1, "both", job)
    assert project.summary()["tracked_ranges"] == [[0, 2]]
    for index in range(3):
        with Image.open(project.mask_path(index)) as mask:
            area = np.count_nonzero(np.asarray(mask)) / (256 * 160)
            assert .05 < area < .85
    frames = LazyFrames(project, 1024, limit=1)
    frames[0]; frames[1]
    assert len(frames.cache) == 1
