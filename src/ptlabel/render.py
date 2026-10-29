"""Turn images and CSV rows into black-and-white label images.

Label images are laid out the way ptouch expects: width runs along the tape,
height is the printable width of the tape in dots.
"""

import csv
from typing import IO

from PIL import Image, ImageDraw, ImageFont, ImageOps

PADDING_PX = 10
TEXT_FILL = 0.85  # fraction of the tape height the text block may use


def fit_image(img: Image.Image, height: int, rotate: str = "auto") -> Image.Image:
    """Scale to the tape height and Floyd-Steinberg dither to pure black and white.

    rotate: "auto" turns portrait images so their long side runs along the tape,
    "none" keeps them as they are, or a number of degrees counter-clockwise.
    """
    img = img.convert("RGBA")
    flat = Image.alpha_composite(Image.new("RGBA", img.size, "white"), img).convert("L")
    if rotate == "auto":
        if flat.height > flat.width:
            flat = flat.rotate(90, expand=True)
    elif rotate != "none":
        flat = flat.rotate(int(rotate), expand=True)
    width = max(1, round(flat.width * height / flat.height))
    flat = ImageOps.autocontrast(flat.resize((width, height), Image.LANCZOS))
    return flat.convert("1").convert("RGB")


def _font(path: str | None, size: int) -> ImageFont.FreeTypeFont:
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def render_text(
    text: str, height: int, font: str | None = None, min_length_px: int = 0
) -> Image.Image:
    """Render (possibly multi-line) text as large as fits the tape height."""
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    size = height
    while size > 4:
        f = _font(font, size)
        box = [round(v) for v in draw.multiline_textbbox((0, 0), text, font=f, align="center")]
        if box[3] - box[1] <= height * TEXT_FILL:
            break
        size -= 2
    width = max(box[2] - box[0] + 2 * PADDING_PX, min_length_px)
    img = Image.new("RGB", (width, height), "white")
    x = (width - box[0] - box[2]) // 2
    y = (height - box[1] - box[3]) // 2
    ImageDraw.Draw(img).multiline_text((x, y), text, font=f, fill="black", align="center")
    return img


def csv_texts(f: IO[str], template: str | None = None) -> list[str]:
    """One label text per non-blank CSV row (header row required).

    template uses {column} placeholders and a literal \\n for a line break;
    without one, the first column is used.
    """
    reader = csv.DictReader(f)
    if template is None:
        template = "{" + reader.fieldnames[0] + "}"
    template = template.replace("\\n", "\n")
    texts = []
    for row in reader:
        if not any((v or "").strip() for v in row.values()):
            continue
        texts.append(template.format_map(row))
    return texts
