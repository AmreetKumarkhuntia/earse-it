import hashlib
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageFilter

from .errors import CutoutError


def save_image(image: Image.Image, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".part")
    try:
        image.save(temporary, format="PNG")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def refine(mask: Image.Image, size: tuple[int, int], edge: dict, source_size: tuple[int, int]) -> Image.Image:
    # Edge controls are expressed in source pixels, independent of preview zoom/resolution.
    alpha = mask.convert("L").resize(size, Image.Resampling.BILINEAR)
    scale = max(size) / max(source_size)
    grow = round(abs(edge["grow"]) * scale)
    if grow:
        alpha = alpha.filter((ImageFilter.MaxFilter if edge["grow"] > 0 else ImageFilter.MinFilter)(grow * 2 + 1))
    if edge["feather"]:
        alpha = alpha.filter(ImageFilter.GaussianBlur(edge["feather"] * scale))
    if edge["invert"]:
        alpha = ImageChops.invert(alpha)
    return alpha


def render_frame(project, frame: int, mode: str) -> dict:
    if mode not in ("overlay", "cutout", "mask", "original"):
        raise CutoutError("INVALID_INPUT", "Unknown preview mode.")
    base_path = project.frame_path(frame)
    has_mask = project.mask_path(frame).is_file()
    if mode == "original" or not has_mask:
        return {"path": str(base_path), "has_mask": has_mask, "frame": frame}
    signature = hashlib.sha256(json.dumps(project.data["edge"], sort_keys=True).encode()).hexdigest()[:12]
    path = project.directory / "renders" / f"{project.data['revision']}-{signature}-{mode}-{frame:08d}.png"
    if not path.exists():
        with Image.open(base_path) as source, Image.open(project.mask_path(frame)) as mask:
            image = source.convert("RGB")
            media = project.data["media"]
            alpha = refine(mask, image.size, project.data["edge"], (media["width"], media["height"]))
            if mode == "cutout":
                image = image.convert("RGBA")
                image.putalpha(alpha)
            elif mode == "mask":
                image = alpha
            else:
                tint = Image.new("RGB", image.size, (182, 244, 112))
                image = Image.composite(tint, image, alpha.point(lambda value: round(value * .45)))
            save_image(image, path)
    # Render cache is disposable and capped independently of clip length.
    renders = sorted(path.parent.glob("*.png"), key=lambda item: item.stat().st_mtime)
    for old in renders[:-96]:
        if old != path:
            old.unlink(missing_ok=True)
    return {"path": str(path), "has_mask": True, "frame": frame}


def alpha16(alpha: Image.Image) -> Image.Image:
    return Image.fromarray(np.asarray(alpha, dtype=np.uint16) * 257)
