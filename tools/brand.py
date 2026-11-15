"""Hibiscus brand renders for the OSS repo: README banners, GitHub social preview, logos.

Everything is composed from the *built* Hibiscus design-system assets synced into the frontend
(``frontend/public/pixel``: sprites and animation strips from hibiscus-assets ``dist/``) plus the
self-hosted Nunito font. No art is drawn here and nothing is copied from the hibiscus-assets
``design/`` sources. Pixel art is upscaled at an integer factor with nearest-neighbour only; the
wordmark and tagline are Nunito (readability first, as the style guide asks).

    frontend: ~/hibiscus-assets/tools/sync.sh frontend --favicon   # refresh the synced assets
    env -u PYTHONPATH uv run --no-project --with pillow python tools/brand.py

Outputs (repo root ``assets/brand/``, © Bigkatoan, see ASSETS-LICENSE):

* ``banner-light.png`` / ``banner-dark.png`` -- 1280x320 README banner (day / night garden)
* ``social-preview.png`` -- 1280x640 GitHub social preview (< 1 MB)
* ``logo.png`` (256), ``logo-512.png``, ``logo-64.png`` -- the 16x16 hibiscus mark at 16/32/4x
* ``hibi.png`` -- Hibi (robot arm holding a hibiscus) at 4x
* ``wordmark.png`` / ``wordmark-dark.png`` -- transparent lockups (mark + Nunito wordmark)
* ``favicon.svg``, ``favicon.ico``, ``apple-touch-icon.png`` -- copied from ``frontend/public``
  (synced with ``--favicon``); ``favicon-32.png`` -- the mark at 2x
"""

from __future__ import annotations

import json
import random
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "frontend" / "public"
PIXEL = PUBLIC / "pixel"
FONT = PUBLIC / "fonts" / "nunito-latin.woff2"
OUT = ROOT / "assets" / "brand"
SCALE = 4  # base canvas -> output, integer only

DAY = {
    "sky": ["#6fb7e8", "#8fcbef", "#b4def2", "#d7eef0", "#f3dfb2"],
    "text": "#3b2027",
    "word": "#d7263d",
    "shadow": "#3b2027",
}
NIGHT = {
    "sky": ["#161a2e", "#1a1f36", "#1f2540", "#222842", "#2b3253"],
    "text": "#f4ecd6",
    "word": "#f2606f",
    "shadow": "#0c0e1f",
}
TAGLINE = "LeRobot training for your lab"


def _meta() -> dict:
    return json.loads((PIXEL / "sprites.json").read_text())


def sprite(name: str) -> Image.Image:
    return Image.open(PIXEL / f"{name}.png").convert("RGBA")


def frame(name: str, i: int = 0) -> Image.Image:
    a = _meta()["anims"][name]
    strip = Image.open(PIXEL / "anim" / f"{name}.png").convert("RGBA")
    return strip.crop((i * a["w"], 0, (i + 1) * a["w"], a["h"]))


def hexrgb(h: str, a: int = 255) -> tuple[int, int, int, int]:
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), a)


def nunito(size: int, weight: int = 800) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT), size)
    f.set_variation_by_axes([weight])
    return f


def sky(w: int, h: int, theme: dict, horizon: int) -> Image.Image:
    """Flat colour bands (pixel-art sky, no gradients)."""
    img = Image.new("RGBA", (w, h), hexrgb(theme["sky"][-1]))
    d = ImageDraw.Draw(img)
    bands = theme["sky"]
    step = max(1, horizon // len(bands))
    for i, c in enumerate(bands):
        d.rectangle((0, i * step, w, (i + 1) * step - 1 if i < len(bands) - 1 else horizon), fill=hexrgb(c))
    return img


def stars(img: Image.Image, n: int, max_y: int, seed: int, avoid: tuple[int, int, int, int] | None = None) -> None:
    rng = random.Random(seed)
    for _ in range(n):
        x, y = rng.randrange(img.width), rng.randrange(max_y)
        if avoid and avoid[0] <= x <= avoid[2] and avoid[1] <= y <= avoid[3]:
            continue
        img.putpixel((x, y), hexrgb("#fff6dc" if rng.random() < 0.7 else "#ffc531"))


def garden(img: Image.Image, ground_top: int, seed: int, flowers: list[int]) -> None:
    """Grass tiles from ground_top down, swaying tufts and hibiscus along the edge."""
    tile = sprite("tile_grass")
    for x in range(0, img.width, tile.width):
        for y in range(ground_top, img.height, tile.height):
            img.alpha_composite(tile, (x, y))
    d = ImageDraw.Draw(img)
    d.line((0, ground_top, img.width, ground_top), fill=hexrgb("#3b2027"))
    tufts = frame("grass_tufts", 0)
    rng = random.Random(seed)
    for x in range(-4, img.width, 22):
        img.alpha_composite(tufts, (x + rng.randrange(6), ground_top - tufts.height + 1))
    flower = sprite("hibiscus")
    for x in flowers:
        img.alpha_composite(flower, (x, ground_top - flower.height + 2))


def up(img: Image.Image, k: int = SCALE) -> Image.Image:
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


def text(img: Image.Image, xy: tuple[int, int], s: str, font: ImageFont.FreeTypeFont, fill: str, shadow: str | None,
         off: int = 2 * SCALE) -> None:
    """Text with a hard offset shadow (whole art pixels, never blurred)."""
    d = ImageDraw.Draw(img)
    if shadow:
        d.text((xy[0] + off, xy[1] + off), s, font=font, fill=hexrgb(shadow))
    d.text(xy, s, font=font, fill=hexrgb(fill))


def banner(night: bool) -> Image.Image:
    theme = NIGHT if night else DAY
    w, h = 320, 80
    base = sky(w, h, theme, 64)
    if night:
        stars(base, 70, 56, seed=7, avoid=(88, 10, 232, 60))  # keep the lettering clean
    else:
        for cx, cy in ((92, 10), (278, 18)):  # flat pixel clouds
            d = ImageDraw.Draw(base)
            d.rectangle((cx, cy, cx + 22, cy + 3), fill=hexrgb("#fff6dc"))
            d.rectangle((cx + 4, cy - 3, cx + 14, cy), fill=hexrgb("#fff6dc"))
            d.rectangle((cx, cy + 3, cx + 22, cy + 4), fill=hexrgb("#c7d3e3"))
    garden(base, 66, seed=3, flowers=[4, 70, 296])
    base.alpha_composite(frame("hibi_wave", 2), (18, 66 - 48 + 2))
    base.alpha_composite(frame("butterfly", 0), (64, 22))
    out = up(base)
    word = nunito(132)
    tag = nunito(38, 700)
    x0 = 92 * SCALE
    text(out, (x0, 6 * SCALE), "Hibiscus", word, theme["word"], theme["shadow"])
    text(out, (x0 + 6, 45 * SCALE), TAGLINE, tag, theme["text"], None)
    return out


def social() -> Image.Image:
    theme = DAY
    w, h = 320, 160
    base = sky(w, h, theme, 120)
    garden(base, 128, seed=11, flowers=[10, 150, 230, 300])
    base.alpha_composite(frame("hibi_wave", 2), (22, 128 - 48 + 2))
    icons = ["icon_dataset", "icon_train", "icon_model", "icon_gpu", "icon_robot_arm"]
    for i, name in enumerate(icons):
        base.alpha_composite(sprite(name), (92 + i * 28, 92))
    base.alpha_composite(frame("butterfly", 1), (262, 70))
    out = up(base)
    text(out, (92 * SCALE, 10 * SCALE), "Hibiscus", nunito(150), theme["word"], theme["shadow"])
    text(out, (92 * SCALE + 6, 54 * SCALE), TAGLINE, nunito(44, 700), theme["text"], None)
    text(out, (92 * SCALE + 6, 68 * SCALE), "datasets · training · models · robot station", nunito(30, 700),
         "#6b4433", None)
    return out


def lockup(night: bool) -> Image.Image:
    theme = NIGHT if night else DAY
    mark = up(sprite("hibiscus"), 6)  # 96 px
    font = nunito(96)
    tw = int(font.getlength("Hibiscus"))
    img = Image.new("RGBA", (mark.width + 24 + tw + 16, 128), (0, 0, 0, 0))
    img.alpha_composite(mark, (0, 16))
    text(img, (mark.width + 24, 0), "Hibiscus", font, theme["word"], theme["shadow"], off=6)
    return img


def save(img: Image.Image, path: Path) -> None:
    img.save(path, optimize=True)
    print(f"{path.relative_to(ROOT)}  {img.width}x{img.height}  {path.stat().st_size // 1024} KiB")


def main() -> None:
    if not (PIXEL / "sprites.json").exists():
        raise SystemExit("frontend/public/pixel is missing: run ~/hibiscus-assets/tools/sync.sh frontend --favicon")
    OUT.mkdir(parents=True, exist_ok=True)
    save(banner(night=False), OUT / "banner-light.png")
    save(banner(night=True), OUT / "banner-dark.png")
    social_img = social()
    save(social_img, OUT / "social-preview.png")
    assert (OUT / "social-preview.png").stat().st_size < 1_000_000, "GitHub social preview must stay < 1 MB"
    save(lockup(night=False), OUT / "wordmark.png")
    save(lockup(night=True), OUT / "wordmark-dark.png")
    mark = sprite("hibiscus")
    for size, name in ((256, "logo.png"), (512, "logo-512.png"), (64, "logo-64.png"), (32, "favicon-32.png")):
        save(up(mark, size // 16), OUT / name)
    save(up(frame("hibi_idle", 0)), OUT / "hibi.png")
    for name in ("favicon.svg", "favicon.ico", "apple-touch-icon.png"):
        shutil.copy2(PUBLIC / name, OUT / name)


if __name__ == "__main__":
    main()
