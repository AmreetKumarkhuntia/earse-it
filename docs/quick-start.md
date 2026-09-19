# A quick guide to erase-it on Windows

Open **Quick guide** in the app’s top bar for these steps, or choose
**GPU setup & troubleshooting** in Processing.

## Select and export a subject

1. **Import** a short video. Download the Tiny model in Processing if prompted.
2. Pause on a clear frame. Choose **Keep (1)** and click or draw a short stroke
   inside your subject. You do not need to trace the outline. **Box (B)** lets you
   drag a rectangle around it instead.
3. Choose **Remove (2)** and mark any background included by mistake. Check the
   **Cutout** preview to see what you will export.
4. Click **Track both ways**. Review the result; use **Space** to play/pause and
   **Left/Right** to step through frames. If tracking drifts, add Keep/Remove marks
   on that frame and track again. Changing marks clears the previous masks.
5. Adjust Feather and Shrink/grow if needed. Choose an in/out range, track every
   frame in it, then **Export cutout** for a transparent MOV or export PNG masks.

In DaVinci Resolve, put the MOV above your new background. If needed, set
Clip Attributes → Alpha Mode → Straight. Masked previews may play slowly;
**Original** plays the video normally. Save a `.cutout` project to resume later,
and keep your source video in its original location.

## Why Windows is using the CPU

Setup always installs **CPU PyTorch** and offers **NVIDIA GPU acceleration**.
If you skipped that option, rerun the same setup EXE and choose Yes. Choosing
Automatic or changing Windows’ graphics preference alone cannot enable CUDA.
NVIDIA processing also requires a compatible NVIDIA graphics driver.
AMD and Intel GPU acceleration is not supported in this version.

GPU processing accelerates **selection and tracking**. Import, video decoding,
and export still use the CPU. CPU activity during those steps is expected.

## Install NVIDIA support

1. Download the `erase-it-VERSION-windows-x64-setup.exe` from
   [GitHub Releases](https://github.com/AmreetKumarkhuntia/earse-it/releases/latest).
   This one EXE installs the app and its optional GPU support. You do not need
   to download ZIP parts or run commands yourself.
2. Close erase-it and run setup. Choose **Yes** when asked to install NVIDIA GPU
   acceleration. Setup downloads about **3.2 GB** and verifies the files before
   installing them. Allow about **12 GB free** during setup (**5 GB** afterwards).
   Keep an internet connection available. If downloading fails, choose **Retry**;
   setup reuses verified downloads and resumes interrupted ones where possible.
   Cancel finishes with CPU processing; rerun the EXE to try again later.
3. Open erase-it and download the Tiny model in Processing if prompted. Import or
   reopen your video and choose **Automatic** or **NVIDIA GPU** under Processor.
   The panel should show your GPU name. Selection and tracking progress also
   show the device actually being used.

Choose NVIDIA support again when installing an app update. A runtime from another
version is ignored so the app can use its bundled CPU runtime.

### What NVIDIA support contains

| Component | Purpose |
| --- | --- |
| Private Python 3.12 and erase-it worker | Runs processing without a separate Python installation. |
| PyTorch 2.7.1 + CUDA 12.8 and TorchVision 0.22.1 | GPU inference runtime. |
| SAM 2 and its Python dependencies | Subject selection and tracking. |
| CUDA, cuDNN, cuBLAS, and other PyTorch runtime DLLs | GPU computation libraries; these account for most of the download size. |
| Dependency inventory and license notices | Records the bundled software. Also included in the release's notices ZIP. |

The NVIDIA package does **not** install an NVIDIA graphics driver or the CUDA
compiler/development toolkit. Install or update the driver for your card
separately. Model weights are also separate: download Tiny (156 MB) or optional
Base+ (324 MB) in the app. FFmpeg is included with the app's CPU installation.

## If GPU processing is still unavailable

| Processing status | What to do |
| --- | --- |
| CPU runtime is installed | Rerun setup for your app version and choose NVIDIA GPU acceleration, then restart the app. |
| CUDA runtime installed, no usable NVIDIA GPU | Confirm that your PC has an NVIDIA card and update its NVIDIA driver. Restart Windows. Run `nvidia-smi` in a terminal to check that the driver sees it. |
| CPU selected, GPU available | Change Processor to Automatic or NVIDIA GPU for that project. |
| Processing runtime unavailable | Rerun setup and choose NVIDIA support again. The guide includes runtime error details when available. |
| GPU runs out of memory | Try the Tiny model or switch Processor to CPU and retry. |

If the app cannot start with a pack installed, close it and remove only
`%APPDATA%\io.github.amreetkumarkhuntia.eraseit\runtimes\nvidia`. Restart to use
the bundled CPU runtime. Your models and projects remain in place.

For troubleshooting, include your app version, GPU model, NVIDIA driver version,
and the exact message under Processing.

If setup fails, its detailed log is at
`%APPDATA%\io.github.amreetkumarkhuntia.eraseit\nvidia-setup.log`.
