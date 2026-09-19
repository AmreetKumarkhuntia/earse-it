# Third-party components

erase-it original source is Apache-2.0. Dependencies retain their own licenses.

| Component | License | Source |
| --- | --- | --- |
| SAM 2.1 code and Tiny/Base+ checkpoints | Apache-2.0 | https://github.com/facebookresearch/sam2 |
| Tauri | MIT / Apache-2.0 | https://github.com/tauri-apps/tauri |
| React | MIT | https://github.com/facebook/react |
| Lucide | ISC | https://github.com/lucide-icons/lucide |
| PyTorch / torchvision | BSD-style | https://github.com/pytorch/pytorch |
| NumPy | BSD-3-Clause | https://github.com/numpy/numpy |
| Pillow | MIT-CMU | https://github.com/python-pillow/Pillow |
| FFmpeg | LGPL-2.1-or-later for the selected build, plus dependency notices | https://ffmpeg.org/legal.html |
| libvpx / libopus | BSD-style | https://www.webmproject.org/ / https://opus-codec.org/ |
| PyInstaller | GPL-2.0-or-later with a distribution exception for generated bundles | https://pyinstaller.org/en/stable/license.html |

Release packaging collects Python distribution license files into the worker bundle.
Media releases must include the upstream FFmpeg license, build configuration, exact
source archive and source/build links. GPL/nonfree builds are rejected by the media
packaging script. A developer's system FFmpeg is not redistributed automatically.

The optional NVIDIA pack includes CUDA runtime libraries under NVIDIA's redistribution
terms. It is optional; the CPU package is independent of CUDA. Check the runtime pack's
included notices. No SAM 3, MatAnyone, or BRIA model is included.
