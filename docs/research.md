# Engine research — September 2026

The product needs prompted object selection and temporal tracking, not just automatic
portrait segmentation. Model licenses and checkpoint licenses were considered separately.

| Project | License / fit | Decision |
| --- | --- | --- |
| [SAM 2.1](https://github.com/facebookresearch/sam2) | Apache-2.0 code/checkpoints; points, boxes, corrective prompting and video propagation | Primary; Tiny and Base+ |
| [EfficientTAM](https://github.com/yformer/EfficientTAM) | Apache-2.0 code/checkpoints; efficiency-focused video segmentation | Future benchmark candidate |
| [Robust Video Matting](https://github.com/PeterL1n/RobustVideoMatting) | GPL-3.0, human-focused recurrent matting | Not the general object selector |
| [BiRefNet](https://github.com/ZhengPeng7/BiRefNet) | MIT project; image segmentation/matting | Possible future image mode |
| [MatAnyone 2](https://github.com/pq-yang/MatAnyone2/blob/main/LICENSE.txt) | S-Lab non-commercial license | Excluded |
| [SAM 3](https://github.com/facebookresearch/sam3/blob/main/LICENSE) | Custom restricted license | Excluded |
| [BRIA RMBG 2.0](https://github.com/Bria-AI/RMBG-2.0) | Commercial use requires separate terms | Excluded |

[PyTorch](https://pytorch.org/get-started/locally/) supplies Windows CPU/CUDA execution.
CPU is the compatibility baseline; NVIDIA is optional. Neither model throughput
figures nor published GPU FPS are treated as app export benchmarks.

[OpenVINO's full SAM 2 video example](https://docs.openvino.ai/2024/notebooks/segment-anything-2-video-with-output.html)
is a candidate for future Intel acceleration. An ONNX image encoder export alone
does not provide the model's memory encoder, memory attention, video state or
corrective propagation. [DirectML](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html)
supports broad Windows hardware but is in sustained engineering; broader GPU support
requires a tested full-video conversion path.

SAM 2.1 source revision and SHA-256-pinned official checkpoint URLs are recorded in
`worker/local_cutout/models.json`. Both code and checkpoint releases were verified
against upstream metadata. Downloads are not arbitrary user-supplied model code.
