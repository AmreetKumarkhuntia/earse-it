# Validation

Automated checks cover prompt validation and coordinate transforms, project round
trips, source modification detection, frame indexing, alpha postprocessing, FFmpeg
ProRes alpha/audio round trips, lossless 16-bit mask export, cancellation cleanup,
and disk-spilled inference state. A separate real-model test exercises CPU selection
and bidirectional tracking with the checksum-verified Tiny checkpoint.

The Windows workflow tests the worker, packages it with PyInstaller, verifies that
the frozen runtime imports PyTorch/SAM 2, checks Rust formatting, and builds an NSIS
installer. The optional NVIDIA runtime workflow builds the CUDA pack separately.

Release tests verify that only a pushed `chore:` HEAD on `main` requests publishing,
that earlier features/breaking changes determine the version bump, and that the
generated `[skip ci]` commit cannot trigger a release loop. Temporary packaging
fixtures check version consistency, source/notice coverage, installer selection,
and SHA-256 checksums. A release is built after versioning, then semantic-release
pushes the version commit and tag and uploads its assets. These local tests do not
exercise GitHub authentication, repository rules, or installation on Windows.

During initial implementation, the Linux environment passed real SAM 2.1 Tiny CPU
selection and bidirectional tracking, an actual 4K alpha export, frontend type/build
checks, the Rust host type check, and frozen-runtime construction of the Tiny model.
The browser integration test uses the real worker while substituting only native
dialogs/event transport; it covers import, selection, tracking, correction, undo,
project save and transparent export. This is not a Windows UI or NVIDIA hardware test.

Before calling a release production-ready, perform the following hardware/editor checks:

- Install on a clean Windows x64 machine without Python or developer tools.
- Test CPU-only and NVIDIA machines, driver incompatibility and GPU memory exhaustion.
- Import/export representative SDR 4K car, person and animal footage; include occlusion,
  fast motion, subject reappearance and rotated phone footage.
- Check the MOV in DaVinci Resolve over black, white and saturated backgrounds; verify
  straight-alpha interpretation, color appearance, audio sync and frame boundaries.
- Exercise actual disk-full and worker-crash recovery and re-open saved projects.
- Measure total import/selection/tracking/export time, peak RAM/VRAM and cache size.

Automated CPU/synthetic-media checks do not establish real-world segmentation quality
or NVIDIA performance. No real-time speed or Resolve-quality equivalence is claimed.
