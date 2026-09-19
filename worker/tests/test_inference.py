import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from erase_it.inference import DiskState, Engine, LazyFrames
from erase_it.models import Models
from erase_it.project import Project


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


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_spilled_state_preserves_per_tensor_devices(tmp_path, device):
    torch = pytest.importorskip("torch")
    if device == "cuda" and not torch.cuda.is_available():
        pytest.skip("Requires an NVIDIA GPU and CUDA PyTorch")
    state = DiskState(tmp_path, limit=1)
    record = {
        "maskmem_features": torch.ones(1, 4, dtype=torch.bfloat16),
        "pred_masks": torch.zeros(1, 4),
        "obj_ptr": torch.ones(1, 4, device=device),
        "maskmem_pos_enc": [torch.arange(4, device=device).float()],
        "object_score_logits": torch.tensor([2.0], device=device),
    }
    state[0] = record
    state[1] = {"obj_ptr": torch.zeros(1, 4, device=device)}
    assert 0 not in state.cache
    restored = state[0]
    # Values, dtypes, and each tensor's device must survive disk eviction.
    torch.testing.assert_close(restored, record)
    # SAM 2 combines restored pointers with newly computed ones on the GPU.
    pointers = torch.cat([restored["obj_ptr"], torch.zeros(1, 4, device=device)])
    assert pointers.device == record["obj_ptr"].device
    assert restored["maskmem_features"].device.type == "cpu"
    assert len(state.cache) == 1


@pytest.mark.inference
@pytest.mark.parametrize("device,frame_count", [("cpu", 3), ("cuda", 25)])
def test_real_sam2_selection_and_bidirectional_tracking(tmp_path, job, device, frame_count):
    pytest.importorskip("sam2")
    torch = pytest.importorskip("torch")
    if device == "cuda" and not torch.cuda.is_available():
        pytest.skip("Requires an NVIDIA GPU and CUDA PyTorch")
    models = Models(Path(os.environ.get("ERASE_IT_TEST_MODELS", ".cache/inference")))
    if not models.path("tiny").exists():
        pytest.skip("Download Tiny and set ERASE_IT_TEST_MODELS for the real inference test")
    source = tmp_path / "source.placeholder"
    source.write_bytes(b"test frames generated below")
    anchor = frame_count // 2
    project = Project.create(tmp_path, source, {"width": 256, "height": 160, "fps_num": 3, "fps_den": 1,
                                             "frame_count": frame_count, "duration": frame_count / 3, "has_audio": False})
    project.frames_dir.mkdir(parents=True)
    for index in range(frame_count):
        image = Image.new("RGB", (256, 160), (30, 45, 60))
        draw = ImageDraw.Draw(image)
        shift = (index - anchor) * 2
        draw.rounded_rectangle((75+shift, 35, 180+shift, 135), radius=20, fill=(215, 160, 40))
        image.save(project.frame_path(index))
    project.data["prompts"] = {str(anchor): {"points": [[.5, .5, 1]], "box": [.28, .20, .76, .87]}}
    project.data["device"] = device
    engine = Engine(models)
    try:
        engine.preview(project, anchor, job)
        # CUDA uses enough frames to evict the default eight-frame cache in both
        # directions, which is where mixed CPU/CUDA state used to fail.
        engine.track(project, anchor, "both", job)
        assert engine.device == device
    finally:
        engine.unload()
    assert project.summary()["tracked_ranges"] == [[0, frame_count - 1]]
    for index in range(frame_count):
        with Image.open(project.mask_path(index)) as mask:
            area = np.count_nonzero(np.asarray(mask)) / (256 * 160)
            assert .05 < area < .85
    frames = LazyFrames(project, 1024, limit=1)
    frames[0]; frames[1]
    assert len(frames.cache) == 1
