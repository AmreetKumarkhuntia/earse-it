import subprocess
from pathlib import Path

import pytest

from local_cutout.jobs import Job
from local_cutout.media import binary, prepare, probe
from local_cutout.project import Project


@pytest.fixture
def job():
    return Job("test-job", lambda event: None)


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "sample with spaces & symbols.mkv"
    subprocess.run([binary("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=4:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=400:sample_rate=48000:duration=2",
                    "-c:v", "ffv1", "-c:a", "pcm_s16le", "-shortest", str(path)], check=True)
    return path


@pytest.fixture
def project(tmp_path, video, job):
    project = Project.create(tmp_path / "app-data", video, probe(video))
    prepare(project, job)
    project.save()
    return project
