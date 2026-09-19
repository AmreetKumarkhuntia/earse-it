import json
import shutil
from pathlib import Path

from .errors import CutoutError
from .export import export
from .inference import Engine
from .jobs import Job
from .masks import render_frame
from .media import binary, prepare, probe
from .models import Models, capabilities
from .project import Project, integer, validate_edge, validate_prompts


class Service:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.models = Models(self.root)
        self.engine = Engine(self.models)
        self.project: Project | None = None

    def current(self) -> Project:
        if self.project is None:
            raise CutoutError("PROJECT_REQUIRED", "Import a video or open a project first.")
        return self.project

    def invalidate(self):
        project = self.current()
        project.data["revision"] += 1
        # Old masks cannot be reused after a prompt/model edit, even after reopening.
        project.save()
        shutil.rmtree(project.directory / "masks", ignore_errors=True)
        shutil.rmtree(project.directory / "renders", ignore_errors=True)

    def hello(self, params, job):
        media_ready = True
        try:
            binary("ffmpeg")
            binary("ffprobe")
        except CutoutError:
            media_ready = False
        last = None
        try:
            last = json.loads((self.root / "last-project.json").read_text())["path"]
        except (OSError, KeyError, ValueError):
            pass
        return {"protocol": 1, "version": "0.1.0", "models": self.models.list(),
                "capabilities": {**capabilities(), "media_ready": media_ready},
                "last_project": last, "data_directory": str(self.root)}

    def import_video(self, params, job):
        source = Path(params["path"]).expanduser().resolve()
        job.progress("Inspecting video")
        media = probe(source, params.get("fps"))
        project = Project.create(self.root, source, media)
        try:
            prepare(project, job)
            project.data["out_frame"] = project.data["media"]["frame_count"] - 1
            project.save()
        except Exception:
            shutil.rmtree(project.directory, ignore_errors=True)
            raise
        self.project = project
        return project.summary()

    def open_project(self, params, job):
        project = Project.load(self.root, Path(params["path"]).expanduser())
        prepare(project, job)
        project.save()
        self.project = project
        return project.summary()

    def project_info(self, params, job):
        return self.current().summary()

    def save_project(self, params, job):
        project = self.current()
        if params.get("path"):
            path = Path(params["path"]).expanduser().resolve()
            if path.suffix != ".cutout":
                raise CutoutError("INVALID_INPUT", "Use the .cutout extension for project files.")
            project.project_file = path
        project.save()
        return project.summary()

    def settings(self, params, job):
        project = self.current()
        data = project.data
        changes = {}
        if "model" in params:
            self.models.get(params["model"])
            changes["model"] = params["model"]
        if "device" in params:
            if params["device"] not in ("auto", "cpu", "cuda"):
                raise CutoutError("INVALID_INPUT", "Unknown processing device.")
            changes["device"] = params["device"]
        if "edge" in params:
            changes["edge"] = validate_edge(params["edge"])
        count = data["media"]["frame_count"]
        start = integer(params.get("in_frame", data["in_frame"]), "In frame", 0, count - 1)
        end = integer(params.get("out_frame", data["out_frame"]), "Out frame", start, count - 1)
        changes.update(in_frame=start, out_frame=end)
        invalidate = changes.get("model", data["model"]) != data["model"]
        data.update(changes)
        if invalidate:
            self.invalidate()
            self.engine.unload()
        project.save()
        return project.summary()

    def set_prompts(self, params, job):
        project = self.current()
        prompts = validate_prompts(params["prompts"], project.data["media"]["frame_count"])
        frame = integer(params["frame"], "Frame", 0, project.data["media"]["frame_count"] - 1)
        if prompts != project.data["prompts"]:
            project.data["prompts"] = prompts
            self.invalidate()
        project.save()
        if params.get("preview", True) and str(frame) in prompts:
            try:
                self.engine.preview(project, frame, job)
            except RuntimeError as error:
                if self.engine.device == "cuda":
                    self.engine.unload()
                    raise CutoutError("GPU_FAILED", "GPU processing failed. Your selection is saved. Choose CPU and redraw or track to retry. " + str(error)[:300])
                raise
        return project.summary()

    def frame(self, params, job):
        project = self.current()
        frame = integer(params["frame"], "Frame", 0, project.data["media"]["frame_count"] - 1)
        return render_frame(project, frame, params.get("mode", "overlay"))

    def track(self, params, job):
        project = self.current()
        project.check_source()
        anchor = integer(params["frame"], "Frame", project.data["in_frame"], project.data["out_frame"])
        direction = params.get("direction", "both")
        if direction not in ("both", "forward", "backward"):
            raise CutoutError("INVALID_INPUT", "Unknown tracking direction.")
        try:
            self.engine.track(project, anchor, direction, job)
        except RuntimeError as error:
            if self.engine.device == "cuda":
                self.engine.unload()
                raise CutoutError("GPU_FAILED", "GPU processing failed. Saved selections and finished masks are retained. Select CPU and track again. " + str(error)[:300])
            raise
        finally:
            project.save()
        return project.summary()

    def download_model(self, params, job):
        return self.models.download(params["model"], job)

    def export(self, params, job):
        return export(self.current(), Path(params["path"]).expanduser().resolve(), params["format"], job)

    def dispatch(self, action: str, params: dict, job: Job):
        methods = {name: getattr(self, name) for name in (
            "hello", "import_video", "open_project", "project_info", "save_project", "settings",
            "set_prompts", "frame", "track", "download_model", "export")}
        if action not in methods:
            raise CutoutError("UNKNOWN_ACTION", "Unknown worker action.")
        job.check()
        return methods[action](params, job)
