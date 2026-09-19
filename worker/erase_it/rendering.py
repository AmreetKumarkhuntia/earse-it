"""Validated render settings shared by project saves, previews, and exports."""
import re
from fractions import Fraction

from PIL import Image

from .errors import CutoutError

DEFAULT_RENDER = {
    "format": "prores", "background": "transparent", "color": "#00ff00",
    "resolution": "native", "quality": "high", "audio": True,
}
RESOLUTIONS = {
    "720p": (1280, 720), "1080p": (1920, 1080), "1440p": (2560, 1440),
    "2k": (2048, 1080), "4k": (3840, 2160),
}
COLORS = {"green": "#00ff00", "blue": "#0000ff", "black": "#000000", "white": "#ffffff"}


def validate_render(value=None) -> dict:
    if value is None:
        value = {}
    if not isinstance(value, dict) or value.keys() - DEFAULT_RENDER.keys():
        raise CutoutError("INVALID_INPUT", "Invalid rendering settings.")
    result = {**DEFAULT_RENDER, **value}
    choices = {
        "format": ("prores", "mp4", "png_sequence", "mask_sequence"),
        "background": ("transparent", *COLORS, "custom"),
        "resolution": ("native", *RESOLUTIONS),
        "quality": ("standard", "high", "maximum"),
    }
    for name, allowed in choices.items():
        if result[name] not in allowed:
            raise CutoutError("INVALID_INPUT", f"Unknown render {name}.")
    if not isinstance(result["color"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", result["color"]):
        raise CutoutError("INVALID_INPUT", "Choose a background color in #RRGGBB format.")
    if type(result["audio"]) is not bool:
        raise CutoutError("INVALID_INPUT", "Include audio must be on or off.")
    if result["format"] == "mp4" and result["background"] == "transparent":
        raise CutoutError("INVALID_INPUT", "MP4 needs a background color. Use MOV or PNG for transparency.")
    result["color"] = result["color"].lower()
    return result


def output_size(source_size: tuple[int, int], resolution: str) -> tuple[int, int]:
    if resolution == "native":
        return source_size
    width, height = source_size
    bound_width, bound_height = RESOLUTIONS[resolution]
    if height > width:
        bound_width, bound_height = bound_height, bound_width
    scale = min(Fraction(bound_width, width), Fraction(bound_height, height))
    # Keep the whole picture and use even dimensions for common video encoders.
    return max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)


def composite(source: Image.Image, alpha: Image.Image, settings: dict) -> Image.Image:
    image = source.convert("RGB")
    if settings["background"] == "transparent":
        image = image.convert("RGBA")
        # Preserve straight/unassociated RGB at the transparent boundary.
        image.putalpha(alpha)
        return image
    color = settings["color"] if settings["background"] == "custom" else COLORS[settings["background"]]
    return Image.composite(image, Image.new("RGB", image.size, color), alpha)
