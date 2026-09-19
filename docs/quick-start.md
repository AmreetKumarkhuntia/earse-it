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

The standard installer bundles **CPU PyTorch**. Choosing Automatic or setting
Windows’ graphics preference cannot add CUDA to that runtime. NVIDIA processing
requires the separate **NVIDIA runtime pack** and a compatible NVIDIA driver.
AMD and Intel GPU acceleration is not supported in this version.

GPU processing accelerates **selection and tracking**. Import, video decoding,
and export still use the CPU. CPU activity during those steps is expected.

## Install NVIDIA support

1. Check your app version in the bottom-right corner. Open that exact version on
   [GitHub Releases](https://github.com/AmreetKumarkhuntia/earse-it/releases).
2. Download `erase-it-nvidia-VERSION-windows-x64.zip`, its `.zip.sha256` file,
   and `install-nvidia.ps1` into the same folder. If the ZIP is split into
   `.zip.001`, `.zip.002`, etc., download **every part** and the `.zip.sha256` file.
   The script joins them automatically. Allow space for both the joined ZIP and
   extracted runtime. The pack builds after the installer is published; check
   the release workflow if its downloads have not appeared yet.
3. Close erase-it. Open PowerShell in that download folder and run, replacing
   `VERSION` with your installed app version:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install-nvidia.ps1 -Archive .\erase-it-nvidia-VERSION-windows-x64.zip
   ```

4. Restart erase-it, import or reopen your video, and choose **Automatic** or
   **NVIDIA GPU** under Processor. The panel should show your GPU name. Selection
   and tracking progress also show the device actually being used.

The pack includes the CUDA runtime; you do not need to install Python, PyTorch,
or the CUDA development toolkit yourself. Install the matching pack again after
updating the app. A pack from another version is ignored so the app can use its
bundled CPU runtime.

## If GPU processing is still unavailable

| Processing status | What to do |
| --- | --- |
| CPU runtime is installed | Install the NVIDIA pack for your exact app version, then restart the app. |
| CUDA runtime installed, no usable NVIDIA GPU | Confirm that your PC has an NVIDIA card and update its NVIDIA driver. Restart Windows. Run `nvidia-smi` in a terminal to check that the driver sees it. |
| CPU selected, GPU available | Change Processor to Automatic or NVIDIA GPU for that project. |
| Processing runtime unavailable | Reinstall the app or matching pack. The guide includes runtime error details when available. |
| GPU runs out of memory | Try the Tiny model or switch Processor to CPU and retry. |

If the app cannot start with a pack installed, close it and remove only
`%APPDATA%\io.github.amreetkumarkhuntia.eraseit\runtimes\nvidia`. Restart to use
the bundled CPU runtime. Your models and projects remain in place.

For troubleshooting, include your app version, GPU model, NVIDIA driver version,
and the exact message under Processing.
