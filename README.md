# Local Cutout

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
- Source-resolution ProRes 4444 MOV with straight alpha and audio, or lossless
  16-bit grayscale PNG masks with timing metadata.
- Small preview frames, a bounded frame cache, and disk-spilled tracking tensors
  instead of loading whole 4K videos into RAM.
- Automatic project snapshots; saved `.cutout` files reference original media.
- Pinned model revisions, SHA-256 verification, resumable downloads, offline processing.

This is practical object segmentation, not advanced hair/glass matting or generative
object erasure. Start with a short, continuous SDR shot. HDR and interlaced footage
are detected and require conversion in your editor first. Masked playback is a
frame-by-frame review and may run below real time; Original plays the proxy with audio.

## Windows installation

The **Verify and build Windows app** GitHub Actions workflow creates an unsigned
Windows x64 NSIS installer as the `local-cutout-windows-x64` artifact. No public
release or code-signing certificate is configured. Download the artifact from a
successful workflow run and run the enclosed installer. Python and FFmpeg are bundled.

On first use, download the 156 MB Tiny model in **Processing**. Base+ is an optional
324 MB download. Those sizes exclude the packaged inference runtime. Once downloaded,
models need no network access. CPU operation is always available; runtime and driver
compatibility determine GPU availability. AMD/Intel GPU acceleration is deferred.

The optional **Build optional NVIDIA runtime** workflow produces a separate CUDA
runtime pack. Download its ZIP, matching `.zip.sha256`, and `install-nvidia.ps1` from
the same successful build. Close the app, then run in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-nvidia.ps1 -Archive .\local-cutout-nvidia-0.1.0-windows-x64.zip
```

The script verifies checksums and installs under the current user's app data.
The NVIDIA driver must support the bundled CUDA 12.8 runtime. If unavailable, Auto
uses CPU. To remove the pack, close the app and delete only the `runtimes\nvidia`
folder under `%APPDATA%\io.github.amreetkumarkhuntia.earseit`.

## Development

Use **Windows x64, Node 22+, Python 3.12, stable Rust with the MSVC toolchain,
Microsoft C++ Build Tools, and WebView2**. No WSL or CUDA compiler is required.

```powershell
git clone git@github.com:AmreetKumarkhuntia/earse-it.git
cd earse-it
npm ci
py -3.12 scripts/setup-worker.py
py -3.12 scripts/prepare-media.py
$env:LOCAL_CUTOUT_FFMPEG = "$pwd\src-tauri\resources\media\ffmpeg.exe"
$env:LOCAL_CUTOUT_FFPROBE = "$pwd\src-tauri\resources\media\ffprobe.exe"
npm run desktop:dev
```

For GPU development, run `py -3.12 scripts/setup-worker.py --device cuda` and set
`LOCAL_CUTOUT_PYTHON` to `.venv-cuda\Scripts\python.exe` using an absolute path.
The CPU development environment remains separate.

`npm run dev` previews the interface in a browser. Processing and native file
dialogs require the desktop host. The Python worker and frontend can also be
developed/tested on Linux with system FFmpeg; Linux desktop distribution is deferred.

```powershell
npm test
npm run build
.venv/Scripts/python -m pytest worker/tests -m "not inference" -q
.venv/Scripts/python -m local_cutout --data-dir .cache/inference --download-model tiny
$env:LOCAL_CUTOUT_TEST_MODELS = "$pwd\.cache\inference"
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
MOV/PNG exports never overwrite an existing destination; choose another name.

Source timing is normalized once using the detected nominal frame rate, or your
choice in **Import options**. The same sampling is used for previews and exports;
audio is trimmed to the selected normalized range. Export preserves displayed
source dimensions and handles rotation. Only the first audio stream is included.

## Project layout

`src/` contains the React editor and typed worker bridge; `src-tauri/` owns native
dialogs, process lifetime, and scoped access to preview files; `worker/local_cutout/`
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
