import json

import pytest

from local_cutout.errors import CutoutError
from local_cutout.project import Project, ranges, validate_prompts


@pytest.mark.parametrize("point", [[float("nan"), .5, 1], [.5, 2, 1], [.5, .5, 3], [.5, .5, True], [0, 0, 1.0]])
def test_invalid_prompt_coordinates_are_rejected(point):
    with pytest.raises(CutoutError):
        validate_prompts({"0": {"points": [point]}}, 10)


def test_prompts_must_belong_to_existing_frames():
    with pytest.raises(CutoutError):
        validate_prompts({"10": {"points": [[.5, .5, 1]]}}, 10)


def test_empty_frames_are_removed_and_boxes_are_ordered():
    assert validate_prompts({"0": {"points": []}}, 10) == {}
    with pytest.raises(CutoutError):
        validate_prompts({"0": {"box": [.7, .2, .3, .8]}}, 10)


def test_mask_coverage_has_no_duplicates():
    assert ranges([2, 0, 1, 1, 4, 7, 8]) == [[0, 2], [4, 4], [7, 8]]


def test_save_reopen_retains_corrections_and_detects_source_changes(project, tmp_path, video):
    project.data["prompts"] = {"1": {"points": [[.4, .5, 1]], "box": None}}
    project.project_file = tmp_path / "saved.cutout"
    project.save()
    reopened = Project.load(project.root, project.project_file)
    assert reopened.data["prompts"] == project.data["prompts"]
    with video.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(CutoutError, match="source video changed"):
        Project.load(project.root, project.project_file)


def test_project_id_cannot_escape_cache_directory(project, tmp_path):
    project.data["id"] = "../../elsewhere"
    path = tmp_path / "invalid.cutout"
    path.write_text(json.dumps(project.data))
    with pytest.raises(CutoutError, match="identifier"):
        Project.load(project.root, path)
