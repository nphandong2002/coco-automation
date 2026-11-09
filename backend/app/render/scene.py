"""Image preparation with Pillow.

* normalise backgrounds / character images to the render size
* seamless (vertically tileable) particle textures for rain / snow effects
* procedural backgrounds — original artwork generated from a palette + seed, so the
  system works out of the box without third-party images (licence: owned/generated)
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

BACKGROUND_STYLES = {
    "gradient": "Dải màu mềm",
    "bokeh": "Bokeh ánh đèn",
    "night_sky": "Bầu trời đêm",
    "sunset": "Hoàng hôn & đồi núi",
    "rainy_window": "Cửa sổ mưa đêm",
}

DEFAULT_PALETTES = {
    "gradient": ["#F6D5C3", "#C9B6E4", "#8FA3D9"],
    "bokeh": ["#2B2340", "#E3A86B", "#F6D5C3", "#8FA3D9"],
    "night_sky": ["#0B1026", "#1C2A5A", "#F5E6B8"],
    "sunset": ["#FDB98B", "#E76F51", "#6D3B6E", "#2A1F3D"],
    "rainy_window": ["#141C2B", "#2E4057", "#F2C14E", "#7FB7BE"],
}


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _palette(style: str, palette: list[str] | None) -> list[tuple[int, int, int]]:
    cols = [c for c in (palette or []) if isinstance(c, str) and len(c.lstrip("#")) == 6]
    base = DEFAULT_PALETTES.get(style, DEFAULT_PALETTES["gradient"])
    merged = cols + base[len(cols):] if len(cols) < len(base) else cols
    return [_rgb(c) for c in merged]


# ------------------------------------------------------------------ normalisation
def cover(img: Image.Image, width: int, height: int) -> Image.Image:
    return ImageOps.fit(img, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def prepare_background(src: Path, out: Path, width: int, height: int) -> Path:
    with Image.open(src) as im:
        img = cover(im.convert("RGB"), width, height)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", compress_level=1)
    return out


def prepare_character(src: Path, out: Path, target_height: int) -> tuple[Path, int, int]:
    """Resize keeping aspect ratio. Returns (path, width, height)."""
    with Image.open(src) as im:
        img = im.convert("RGBA")
    ratio = target_height / img.height
    w = max(2, int(round(img.width * ratio / 2) * 2))
    h = max(2, int(round(target_height / 2) * 2))
    img = img.resize((w, h), Image.Resampling.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", compress_level=1)
    return out, w, h


def has_transparency(src: Path) -> bool:
    with Image.open(src) as im:
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            alpha = im.convert("RGBA").getchannel("A")
            return alpha.getextrema()[0] < 250
    return False


# ------------------------------------------------------------------ particle textures
def rain_texture(out: Path, width: int, height: int, seed: int = 7, density: float = 1.0) -> Path:
    """Transparent, vertically tileable rain streak layer."""
    rnd = random.Random(seed)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    count = int(width * height / 9000 * density)
    for _ in range(count):
        x = rnd.uniform(0, width)
        y = rnd.uniform(0, height)
        length = rnd.uniform(18, 55)
        slant = length * 0.12
        alpha = rnd.randint(55, 140)
        w = 1 if rnd.random() < 0.8 else 2
        for dy in (0, -height, height):  # wrap → seamless vertical tiling
            draw.line([(x, y + dy), (x - slant, y + length + dy)], fill=(210, 225, 255, alpha), width=w)
    layer = layer.filter(ImageFilter.GaussianBlur(0.6))
    out.parent.mkdir(parents=True, exist_ok=True)
    layer.save(out, "PNG")
    return out


def snow_texture(out: Path, width: int, height: int, seed: int = 11, density: float = 1.0) -> Path:
    rnd = random.Random(seed)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    count = int(width * height / 14000 * density)
    for _ in range(count):
        x, y = rnd.uniform(0, width), rnd.uniform(0, height)
        r = rnd.choice((1.2, 1.6, 2.2, 3.0, 3.8))
        alpha = rnd.randint(120, 230)
        for dy in (0, -height, height):
            draw.ellipse([x - r, y + dy - r, x + r, y + dy + r], fill=(255, 255, 255, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(0.8))
    out.parent.mkdir(parents=True, exist_ok=True)
    layer.save(out, "PNG")
    return out


# ------------------------------------------------------------------ procedural backgrounds
def _vertical_gradient(width: int, height: int, stops: list[tuple[int, int, int]]) -> Image.Image:
    strip = Image.new("RGB", (1, 256))
    n = len(stops) - 1
    for y in range(256):
        pos = y / 255 * n
        i = min(int(pos), n - 1)
        f = pos - i
        a, b = stops[i], stops[i + 1]
        strip.putpixel((0, y), tuple(int(a[k] + (b[k] - a[k]) * f) for k in range(3)))
    return strip.resize((width, height), Image.Resampling.BICUBIC)


def _glow(size: tuple[int, int], center: tuple[float, float], radius: float,
          color: tuple[int, int, int], strength: int) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(*color, strength))
    return layer.filter(ImageFilter.GaussianBlur(radius * 0.6))


def _grain(img: Image.Image, amount: int = 10) -> Image.Image:
    noise = Image.effect_noise(img.size, 40).convert("RGB")
    return Image.blend(img, noise, amount / 255)


def generate_background(out: Path, width: int, height: int, style: str = "bokeh",
                        palette: list[str] | None = None, seed: int = 1) -> Path:
    if style not in BACKGROUND_STYLES:
        raise ValueError(f"style phải là một trong {sorted(BACKGROUND_STYLES)}")
    rnd = random.Random(seed)
    cols = _palette(style, palette)
    out_size = (width, height)
    # paint at half resolution (blurry art anyway, ~4x faster), upscale at the end
    width, height = max(64, width // 2), max(36, height // 2)
    size = (width, height)

    if style == "gradient":
        img = _vertical_gradient(width, height, cols[:3]).convert("RGBA")
        for _ in range(3):
            c = rnd.choice(cols)
            img = Image.alpha_composite(img, _glow(size, (rnd.uniform(0, width), rnd.uniform(0, height)),
                                                   rnd.uniform(0.2, 0.4) * width, c, 90))
    elif style == "bokeh":
        img = _vertical_gradient(width, height, [cols[0], tuple(int(v * 0.6) for v in cols[0])]).convert("RGBA")
        for i in range(70):
            c = cols[1 + i % (len(cols) - 1)]
            r = rnd.uniform(0.012, 0.06) * width
            layer = Image.new("RGBA", size, (0, 0, 0, 0))
            x, y = rnd.uniform(0, width), rnd.uniform(0.05, 0.95) * height
            ImageDraw.Draw(layer).ellipse([x - r, y - r, x + r, y + r], fill=(*c, rnd.randint(40, 120)))
            img = Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(r * rnd.uniform(0.15, 0.5))))
    elif style == "night_sky":
        img = _vertical_gradient(width, height, [cols[0], cols[1]]).convert("RGBA")
        stars = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(stars)
        for _ in range(int(width * height / 3500)):
            x, y = rnd.uniform(0, width), rnd.uniform(0, height * 0.85)
            r = rnd.choice((0.6, 0.8, 1.0, 1.4))
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 240, rnd.randint(90, 255)))
        img = Image.alpha_composite(img, stars.filter(ImageFilter.GaussianBlur(0.4)))
        mx, my = width * rnd.uniform(0.65, 0.85), height * rnd.uniform(0.15, 0.3)
        img = Image.alpha_composite(img, _glow(size, (mx, my), height * 0.18, cols[2], 70))
        moon = Image.new("RGBA", size, (0, 0, 0, 0))
        mr = height * 0.06
        ImageDraw.Draw(moon).ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=(*cols[2], 255))
        img = Image.alpha_composite(img, moon.filter(ImageFilter.GaussianBlur(1.2)))
    elif style == "sunset":
        img = _vertical_gradient(width, height, cols[:3]).convert("RGBA")
        sx, sy = width * rnd.uniform(0.3, 0.7), height * 0.55
        img = Image.alpha_composite(img, _glow(size, (sx, sy), height * 0.3, (255, 220, 160), 120))
        for layer_i, base_y in enumerate((0.62, 0.72, 0.82)):
            hills = Image.new("RGBA", size, (0, 0, 0, 0))
            shade = cols[min(2 + layer_i, len(cols) - 1)]
            shade = tuple(int(v * (0.85 - layer_i * 0.15)) for v in shade)
            phase, amp = rnd.uniform(0, math.tau), height * rnd.uniform(0.03, 0.07)
            freq, freq2 = rnd.uniform(0.8, 1.6), rnd.uniform(2.5, 4.0)
            pts = [(x, base_y * height + amp * math.sin(x / width * math.tau * freq + phase)
                    + amp * 0.3 * math.sin(x / width * math.tau * freq2 + phase * 2))
                   for x in range(0, width + 8, 8)]
            ImageDraw.Draw(hills).polygon([(0, height), *pts, (width, height)], fill=(*shade, 255))
            img = Image.alpha_composite(img, hills.filter(ImageFilter.GaussianBlur(1.5)))
    else:  # rainy_window
        img = _vertical_gradient(width, height, [cols[0], cols[1]]).convert("RGBA")
        for _ in range(55):
            c = rnd.choice(cols[2:])
            r = rnd.uniform(0.01, 0.035) * width
            x, y = rnd.uniform(0, width), rnd.uniform(0.35, 0.95) * height
            layer = Image.new("RGBA", size, (0, 0, 0, 0))
            ImageDraw.Draw(layer).ellipse([x - r, y - r, x + r, y + r], fill=(*c, rnd.randint(50, 130)))
            img = Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(r * 0.5)))
        img = Image.alpha_composite(img, Image.new("RGBA", size, (*cols[1], 40)).filter(ImageFilter.GaussianBlur(4)))
        frame = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(frame)
        fc = tuple(int(v * 0.35) for v in cols[0])
        bar = int(width * 0.018)
        d.rectangle([0, 0, width, bar * 2], fill=(*fc, 255))
        d.rectangle([0, height - bar * 3, width, height], fill=(*fc, 255))
        d.rectangle([0, 0, bar * 2, height], fill=(*fc, 255))
        d.rectangle([width - bar * 2, 0, width, height], fill=(*fc, 255))
        d.rectangle([width // 2 - bar // 2, 0, width // 2 + bar // 2, height], fill=(*fc, 255))
        d.rectangle([0, int(height * 0.45), width, int(height * 0.45) + bar], fill=(*fc, 255))
        img = Image.alpha_composite(img, frame)

    result = _grain(img.convert("RGB").resize(out_size, Image.Resampling.LANCZOS), 8)
    out.parent.mkdir(parents=True, exist_ok=True)
    result.save(out, "PNG", optimize=True)
    return out
