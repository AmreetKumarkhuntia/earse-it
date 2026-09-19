"""Generate the app's simple geometric icon; no network or external artwork."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1] / "src-tauri/icons"
root.mkdir(parents=True, exist_ok=True)
image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((0, 0, 255, 255), radius=58, fill="#d0ef9a")
draw.rounded_rectangle((58, 54, 198, 199), radius=22, fill="#25371c")
draw.polygon([(160, 54), (198, 54), (198, 97)], fill="#d0ef9a")
draw.line([(69, 180), (176, 71)], fill="#d0ef9a", width=16)
for size, name in [(32, "32x32.png"), (128, "128x128.png"), (256, "icon.png")]:
    image.resize((size, size), Image.Resampling.LANCZOS).save(root / name)
image.save(root / "icon.ico", sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
