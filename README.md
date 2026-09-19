# erase-it

A small, open-source Windows app for selecting a video subject, tracking it across
frames, and exporting a transparent cutout or mask for your editor. Repository:
[AmreetKumarkhuntia/earse-it](https://github.com/AmreetKumarkhuntia/earse-it).

**Import → mark → track → correct → export.** Videos stay on your computer. There
are no accounts, cloud inference, usage fees, telemetry, or watermarks.

## Features

- Positive/negative strokes and box selection for one subject per project.
- SAM 2.1 Tiny by default; optional Base+ model. CPU and optional NVIDIA CUDA.
- Forward/backward tracking, correction frames, undo/redo, in/out ranges, and cancellation.
- Overlay, checkerboard cutout, grayscale mask, and original-video previews.
- Feather, shrink/grow, and invert controls in source pixels.
- ProRes 4444 MOV, H.264 MP4, transparent/color PNG frames, and 16-bit PNG masks.
- Transparent, green-screen, blue-screen, black, white, or custom-color backgrounds,
  with a rendered-background preview before export.
- Native, 720p, 1080p, 1440p/QHD, 2K/DCI, and 4K/UHD output sizes. Aspect ratio and
  portrait orientation are preserved. Video quality and source audio are selectable.
- Small preview frames, a bounded frame cache, and disk-spilled tracking tensors
  instead of loading whole 4K videos into RAM.
- Automatic project snapshots; saved `.cutout` files reference original media.
- Pinned model revisions, SHA-256 verification, resumable downloads, offline processing.

This is practical object segmentation, not advanced hair/glass matting or generative
object erasure. Start with a short, continuous SDR shot. HDR and interlaced footage
are detected and require conversion in your editor first. Masked playback is a
frame-by-frame review and may run below real time; Original plays the proxy with audio.

## Windows installation

Download the Windows x64 `erase-it-VERSION-windows-x64-setup.exe` from
[GitHub Releases](https://github.com/AmreetKumarkhuntia/earse-it/releases/latest)
and run it. Installers are unsigned; Python and FFmpeg are bundled. Each release
also includes `SHA256SUMS` and a companion third-party source and notice ZIP.
The installer can download WebView2 if it is missing, so initial installation may
need an internet connection.

Development installers are available as the `erase-it-windows-x64` artifact
from successful **Verify and build Windows app** workflow runs. Before the first
automated release, use this artifact download.

On first use, download the 156 MB Tiny model in **Processing**. Base+ is an optional
324 MB download. Those sizes exclude the packaged inference runtime. Once downloaded,
models need no network access. CPU operation is always available; runtime and driver
compatibility determine GPU availability. AMD/Intel GPU acceleration is deferred.

**One setup EXE handles both CPU and NVIDIA installation.** When asked whether to
install NVIDIA GPU acceleration, choose **Yes**. Setup downloads the matching
runtime (about 3.2 GB), verifies it, and installs it automatically. Allow about
12 GB of free space during installation and 5 GB afterwards. The numbered GPU
files on the release page are data used by setup; you only need to download the
`setup.exe`. Choose **No** for CPU use, or rerun the same EXE to add NVIDIA later.
A failed download can be retried without downloading verified files again.

NVIDIA support includes a private Python 3.12 runtime, erase-it's processing
worker, PyTorch 2.7.1 with CUDA 12.8, TorchVision 0.22.1, SAM 2, and the CUDA,
cuDNN, cuBLAS and other libraries needed by PyTorch, plus dependencies and notices.
It does not install the graphics driver or CUDA development toolkit. Model
weights are downloaded separately in Processing. The source/notice ZIP includes
the exact Python dependency inventory for both CPU and NVIDIA workers.

An NVIDIA GPU and driver compatible with CUDA 12.8 are required. If unavailable,
Automatic uses CPU. Selection and tracking use the GPU; import, decoding, and
export use CPU. Choose NVIDIA support again when updating the app; runtimes
from other versions are ignored. See the [small Windows guide](docs/quick-start.md)
or **Quick guide** in the app for selection steps and GPU troubleshooting.
To remove GPU support, close the app and delete only `runtimes\nvidia` under
`%APPDATA%\io.github.amreetkumarkhuntia.eraseit`.

## Development

Use **Windows x64, Node 24.15+, Python 3.12, stable Rust with the MSVC toolchain,
Microsoft C++ Build Tools, and WebView2**. No WSL or CUDA compiler is required.

```powershell
git clone git@github.com:AmreetKumarkhuntia/earse-it.git
cd earse-it
npm ci
py -3.12 scripts/setup-worker.py
py -3.12 scripts/prepare-media.py
$env:ERASE_IT_FFMPEG = "$pwd\src-tauri\resources\media\ffmpeg.exe"
$env:ERASE_IT_FFPROBE = "$pwd\src-tauri\resources\media\ffprobe.exe"
npm run desktop:dev
```

For GPU development, run `py -3.12 scripts/setup-worker.py --device cuda` and set
`ERASE_IT_PYTHON` to `.venv-cuda\Scripts\python.exe` using an absolute path.
The CPU development environment remains separate.

`npm run dev` previews the interface in a browser. Processing and native file
dialogs require the desktop host. The Python worker and frontend can also be
developed/tested on Linux with system FFmpeg; Linux desktop distribution is deferred.

```powershell
npm test
npm run build
.venv/Scripts/python -m pytest worker/tests -m "not inference" -q
.venv/Scripts/python -m erase_it --data-dir .cache/inference --download-model tiny
$env:ERASE_IT_TEST_MODELS = "$pwd\.cache\inference"
.venv/Scripts/python -m pytest worker/tests -m inference -q
```

Build an installer:

```powershell
.venv/Scripts/python scripts/package-worker.py
.venv/Scripts/python scripts/check-frozen-worker.py
npm run desktop:build
```

Run `scripts/prepare-media.py` before bundling; it pins and verifies the Windows
LGPL FFmpeg build, records provenance, and downloads FFmpeg source/build archives.
Installer output is under `src-tauri/target/release/bundle/nsis/`. Publish the
companion source and notice artifact alongside any redistributed installer.

## Automated releases

Commit messages are enforced by a Git hook and CI. Only `feat`, `fix`, `docs`, and
`refactor` are allowed: `type(optional-scope): short description`. Run `npm ci` to
install the hook. See [CONTRIBUTING.md](CONTRIBUTING.md) for examples and rules.

Push a `feat` or `fix` commit to `main` to request an automatic release. Breaking
changes of any allowed type also request one. Ordinary `docs` and `refactor`
commits, pull requests, and manual runs build and test without publishing. Add
`[skip release]` to defer publishing for a particular push. Only HEAD decides
whether the push requests a release; use a matching PR title when squash merging.

After frontend tests, worker tests, real CPU inference, and Rust formatting pass,
semantic-release calculates the version from all commits since the last release:
`fix` gives a patch, `feat` a minor, and `!` or a `BREAKING CHANGE:` footer a major.
With no existing version tag, semantic-release starts at **1.0.0**.

The workflow updates the npm, Tauri, Rust, and Python versions and the optional
NVIDIA installer version, then packages and checks both frozen workers. It builds
the Windows installer with pinned download hashes and tests an actual silent
installation with NVIDIA support before publishing. It commits these versions and `CHANGELOG.md` as
`docs(release): VERSION [skip ci]`, pushes that commit and `vVERSION`, and publishes
the installer, NVIDIA data files, sources/notices ZIP, and checksums to GitHub Releases. Pull the
generated commit before your next push. Release builds run serially; if `main`
has advanced before semantic-release starts, it skips the stale run. Use another
`feat` or `fix` commit to request a release of the latest changes in that case.

Publishing uses the workflow's built-in `GITHUB_TOKEN` with `contents: write` only
for the release job. No npm publishing token or personal access token is needed.
Repository branch/tag rules must allow that job to push the release commit and
version tag. The generated commit skips CI; installer publishing happens in the
same workflow and does not depend on a second workflow triggered by the bot's tag.
Both workers and the setup EXE are built in the same release job. GitHub keeps the
release as a draft until all assets have uploaded, so setup's NVIDIA downloads
are available when the release becomes public. Hosted Windows runners verify
installation and CUDA runtime loading; they cannot test inference on physical
NVIDIA hardware. The NVIDIA files stay below GitHub's per-asset size limit and
setup joins them automatically. Development installers include CPU support only.

For unattended release installation, use `setup.exe /S /NVIDIA`; omit `/NVIDIA`
for CPU only. An unsuccessful requested NVIDIA installation exits with code 30.
The app remains installed and can use CPU processing. The setup log is at
`%APPDATA%\io.github.amreetkumarkhuntia.eraseit\nvidia-setup.log`.

If building fails, no release commit or tag is pushed. If GitHub uploading fails
after tagging, the workflow retains `erase-it-release-files` as an Actions
artifact. Create or recover a draft release for the existing tag, upload the files
from that run, and publish the draft; rerunning semantic-release will not rebuild
an already tagged version. Published versions are not overwritten.

Release logic checks (no publishing):

```sh
npm run test:release
python -m unittest discover -s scripts -p 'test_release.py' -v
```

## Editor workflow

1. Choose a frame with a visible subject. Draw inside it with **Keep**, exclude
   unwanted pixels with **Remove**, or draw a **Box** around it.
2. Click **Track both ways**. To repair drift, add a stroke on a later frame and
   track again. All correction frames within the selected range condition tracking.
3. Adjust edges and set in/out points. Every frame in that range must have a mask
   before export is enabled.
4. In DaVinci Resolve, place the transparent MOV above the new background. Set
   **Clip Attributes → Alpha Mode → Straight** if automatic interpretation differs.
   Import PNGs as an image sequence and set the frame rate from `timing.json`.

Changing a selection or model invalidates previous masks. Undo restores selections;
retracking regenerates their masks. Cancellation retains completed masks and prompts.
Exports never overwrite an existing destination; choose another name.

Source timing is normalized once using the detected nominal frame rate, or your
choice in **Import options**. The same sampling is used for previews and exports;
audio is trimmed to the selected normalized range. Native export preserves displayed
source dimensions and handles rotation. Other sizes fit the whole image within the
selected preset without cropping; the panel shows the exact dimensions. Upscaling
does not add detail. Only the first audio stream is included when audio is enabled.

### Rendering options

Choose **Render & Export** on the right. Rendering settings are saved with your
project and reuse its existing masks, so exporting a second size or background
does not require retracking.

| Output | Use |
| --- | --- |
| Editing video · MOV | ProRes 4444 with straight alpha, or a solid background; optional PCM audio. |
| Video · MP4 | H.264 with green, blue, black, white, or custom-color background; optional AAC audio. |
| Image sequence · PNG | Lossless RGB/RGBA frames with timing metadata and no audio. |
| Mask sequence · PNG | Lossless 16-bit grayscale masks with timing metadata and no audio. |

**Native** keeps the original pixels. Presets fit within 1280 × 720, 1920 × 1080,
2560 × 1440 (QHD), 2048 × 1080 (DCI 2K), or 3840 × 2160 (UHD 4K). Bounds rotate
for portrait footage; square and other aspect ratios remain intact. For example,
a 16:9 clip fits DCI 2K at 1920 × 1080; choose QHD for 2560 × 1440. MP4 requires
even dimensions: use a preset or MOV/PNG for a source with odd native dimensions.

Use **Preview background** to review the selected color. Green and blue screens
are opaque backgrounds for later chroma keying; transparent MOV or PNG keeps alpha
directly. High quality is the default for video; Maximum uses more space and
Standard creates smaller files. PNG and mask sequences remain lossless.

## Project layout

`src/` contains the React editor and typed worker bridge; `src-tauri/` owns native
dialogs, process lifetime, and scoped access to preview files; `worker/erase_it/`
owns project data, media processing, model management, and SAM 2 inference.

Project caches live in the OS application data folder. `.cutout` saves are references,
not portable video archives. Keep originals in place; changed sources are rejected
to prevent mask misalignment. Closing the app cancels active processing. After a
crash, reopen the last project and retrack any missing range. Logs stay local in
`worker.log`; no data is sent to a logging service.

See [architecture and protocol](docs/architecture.md), [model research](docs/research.md),
and [validation](docs/validation.md).

## License

Original code: [Apache-2.0](LICENSE). Models and libraries retain their respective
licenses; see [third-party notices](licenses/THIRD_PARTY.md). The optional CUDA pack
uses NVIDIA's runtime redistribution terms. The CPU path does not require it.
