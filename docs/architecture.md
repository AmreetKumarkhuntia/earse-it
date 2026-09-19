# Architecture

```text
React editor → Tauri commands → Rust worker host → Python JSON worker
                                      │                 ├─ SAM 2.1 / PyTorch
                                      │                 ├─ FFmpeg / ffprobe
                                      │                 └─ projects, models, disk caches
                                      └─ app-data-only preview asset access
```

The webview has no shell or general filesystem permission and loads no remote UI.
The host starts a bundled worker in release builds and a project-local venv in dev.
Communication uses newline-delimited JSON on stdio; stderr goes to a local log.
No HTTP server, account service, database server, or cloud inference is involved.

## Protocol v1

Request: `{"v":1,"id":"unique-id","action":"frame","params":{"frame":42,"mode":"overlay"}}`

Response: `{"v":1,"id":"unique-id","result":{...}}`, or
`{"v":1,"id":"unique-id","error":{"code":"INCOMPLETE_MASKS","message":"..."}}`.

Progress: `{"v":1,"event":"progress","job_id":"unique-id","stage":"Tracking subject","current":10,"total":100,"elapsed":1.2}`.

| Action | Parameters | Result |
| --- | --- | --- |
| `hello` | none | runtime capabilities, model list, last project |
| `import_video` | `path`, optional rational `fps` | project summary |
| `open_project` | `path` | project summary |
| `project_info` | none | current summary and completed mask ranges |
| `save_project` | optional `path` | project summary |
| `settings` | optional `model`, `device`, `edge`, `render`, `in_frame`, `out_frame` | project summary |
| `set_prompts` | complete `prompts` mapping, `frame`, optional `preview` | updated summary |
| `frame` | `frame`, `mode`: overlay/cutout/render/mask/original | app-owned image path and mask availability |
| `track` | selection `frame`, `direction`: both/forward/backward | completed summary |
| `cancel` | `job_id` | whether an active job was cancelled |
| `download_model` | `model`: tiny/base_plus | updated model list |
| `export` | `path`, `format`: prores/mp4/png_sequence/mask_sequence, optional `options` | output path, frame count, width, height |

Commands are serialized in the client. The worker rejects overlapping jobs and
handles cancellation on its input thread while processing runs on a worker thread.
Cancellation kills registered FFmpeg children to unblock pipe reads/writes. Inference
checks cancellation between model operations. Requests and IDs have size/shape limits.

Prompt keys are zero-based frame numbers. Points are `[normalizedX, normalizedY, label]`,
where label 1 keeps and 0 excludes. A box is `[left, top, right, bottom]` in normalized
coordinates. Limits are 128 points per frame and 256 correction frames. The editor
accounts for letterboxing; export never includes selection overlays.

## Timing and bounded storage

Import generates a normalized JPEG sequence and VP9/Opus review proxy. A rational
frame rate and zero-based index are used consistently across selection, tracking,
mask storage and original-resolution decoding. Masks are segmentation masks, not
calibrated opacity; alpha feather/grow/invert is an explicit final rendering step.

SAM's loader is replaced by an LRU holding three normalized model input tensors.
Tracking output dictionaries spill to disk using an eight-entry write-back LRU.
At most four conditioning frames are attended per prediction. Corrections remain
available on disk. Full-resolution source images are decoded only during export.
Display renders are capped at 96 files. Temporary model state is removed after runs.

Project writes use temporary files and atomic replacement. Prompt/model changes
increase a revision and invalidate masks, preventing old results from being exported.
Completed mask files are published atomically. Exports are prepared under temporary
names; a MOV is published with no replacement, and PNG destinations are reserved
exclusively. Existing destinations are never overwritten.

Rendering preferences are a validated `render` object: `format`, `background`
(transparent/green/blue/black/white/custom), `color` (#RRGGBB), `resolution`
(native/720p/1080p/1440p/2k/4k), `quality` (standard/high/maximum), and boolean
`audio`. Missing preferences in old projects default to native transparent ProRes
with high quality and audio. The optional export `options` object overrides saved
preferences for that export. Rendering changes do not invalidate tracked masks.

The render preview and export share background compositing and edge refinement.
Preset dimensions fit the original aspect ratio, rotate bounds for portrait video,
and round to even pixels. Native keeps exact dimensions; odd-sized native MP4 is
rejected with guidance to use a preset or MOV/PNG. Frames are decoded from the
original source and resized with Lanczos, then composed against the refined mask.
Exports stream one frame at a time. MP4 uses the bundled OpenH264 encoder on
Windows (x264 is also accepted for Linux development) and optional AAC audio.
MOV retains ProRes 4444 and PCM audio. PNG sequences include rational timing and
rendering metadata. Audio and video retain the project's normalized in/out range.

The pinned upstream SAM 2 implementation has a broken optional memory-clear helper;
it remains disabled. Every tracking direction begins from clean state with all saved
prompts, so the helper is unnecessary. Optional CUDA extension postprocessing and
torch.compile are also disabled for native Windows portability.
