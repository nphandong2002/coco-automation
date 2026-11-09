"""YouTube thumbnail (1280x720 JPEG, < 2 MB) composed with Pillow."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.render.fonts import find_font
from app.render.scene import cover

THUMB_W, THUMB_H = 1280, 720


def _font(size: int, font_path: Path | None) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = font_path or find_font()
    if path:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        lines[-1] = lines[-1].rstrip(".,") + "…"
    return lines


def render_thumbnail(out: Path, *, background: Path, title: str, badge: str = "",
                     character: Path | None = None, accent: str = "#E3A86B",
                     font_path: Path | None = None) -> Path:
    with Image.open(background) as im:
        base = cover(im.convert("RGB"), THUMB_W, THUMB_H).convert("RGBA")

    # darken the text side for legibility
    shade = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(shade)
    for x in range(THUMB_W):
        a = int(170 * max(0.0, 1 - x / (THUMB_W * 0.72)))
        d.line([(x, 0), (x, THUMB_H)], fill=(10, 8, 20, a))
    base = Image.alpha_composite(base, shade)

    if character is not None and character.exists():
        with Image.open(character) as cim:
            ch = cim.convert("RGBA")
        target_h = int(THUMB_H * 0.88)
        ratio = target_h / ch.height
        ch = ch.resize((max(1, int(ch.width * ratio)), target_h), Image.Resampling.LANCZOS)
        glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
        px = THUMB_W - ch.width - 30
        py = THUMB_H - ch.height
        glow.paste((255, 240, 220, 90), (px, py), ch)
        base = Image.alpha_composite(base, glow.filter(ImageFilter.GaussianBlur(18)))
        base.alpha_composite(ch, (px, py))

    draw = ImageDraw.Draw(base)
    title_font = _font(86, font_path)
    lines = _wrap(draw, title.upper(), title_font, int(THUMB_W * 0.6), 3)
    if len(lines) == 3:
        title_font = _font(72, font_path)
        lines = _wrap(draw, title.upper(), title_font, int(THUMB_W * 0.6), 3)
    y = 120
    for line in lines:
        draw.text((64, y), line, font=title_font, fill=(255, 255, 255, 255),
                  stroke_width=5, stroke_fill=(20, 14, 30, 255))
        y += int(title_font.size * 1.12) if hasattr(title_font, "size") else 90

    if badge:
        bf = _font(44, font_path)
        tw = draw.textlength(badge, font=bf)
        bx, by = 64, THUMB_H - 130
        try:
            draw.rounded_rectangle([bx, by, bx + tw + 48, by + 74], radius=18, fill=accent)
        except ValueError:
            draw.rounded_rectangle([bx, by, bx + tw + 48, by + 74], radius=18, fill="#E3A86B")
        draw.text((bx + 24, by + 12), badge, font=bf, fill=(30, 20, 15, 255))

    out.parent.mkdir(parents=True, exist_ok=True)
    rgb = base.convert("RGB")
    quality = 90
    while True:
        rgb.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
        if out.stat().st_size < 1_900_000 or quality <= 60:
            break
        quality -= 10
    return out
