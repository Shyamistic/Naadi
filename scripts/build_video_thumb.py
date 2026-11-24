"""The README's demo-video thumbnail: the video's YouTube thumbnail with a play button, saved to
docs/images/demo-video.jpg. Also checks the video can be watched without signing in (YouTube's oEmbed endpoint
answers for public and unlisted videos, not private ones).

    python scripts/build_video_thumb.py [video id]
"""
from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images" / "demo-video.jpg"
VIDEO = sys.argv[1] if len(sys.argv) > 1 else "7jEKTCY2mV0"
UA = {"User-Agent": "Mozilla/5.0"}
NAVY = (26, 58, 143)


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read()


def font(size: int):
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


meta = json.loads(get(f"https://www.youtube.com/oembed?format=json&url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3D{VIDEO}"))
print(f"watchable: yes | title: {meta.get('title')!r} | channel: {meta.get('author_name')!r}")
length = None
try:
    page = get(f"https://www.youtube.com/watch?v={VIDEO}").decode("utf-8", "replace")
    m = re.search(r'"lengthSeconds":"(\d+)"', page)
    length = int(m.group(1)) if m else None
except Exception as exc:  # noqa: BLE001
    print("length lookup failed:", exc)
print("length:", f"{length // 60}:{length % 60:02d}" if length else "unknown")

image = None
for name in ("maxresdefault", "sddefault", "hqdefault"):
    try:
        im = Image.open(io.BytesIO(get(f"https://img.youtube.com/vi/{VIDEO}/{name}.jpg"))).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        print(f"{name}: unavailable ({getattr(exc, 'code', exc)})")
        continue
    print(f"{name}: {im.size}")
    if abs(im.width / im.height - 4 / 3) < 0.01:  # 4:3 frames letterbox a 16:9 video: crop the bars
        h = round(im.width * 9 / 16)
        top = (im.height - h) // 2
        im = im.crop((0, top, im.width, top + h))
    image = im.resize((1280, 720), Image.LANCZOS) if im.width < 1280 else im
    break
if image is None:
    sys.exit("no thumbnail available")

w, h = image.size
# A small badge in the bottom-right corner, so the thumbnail's own design stays uncovered.
overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
draw = ImageDraw.Draw(overlay)
label = "Watch the demo" + (f"  ·  {length // 60}:{length % 60:02d}" if length else "")
f = font(round(h * 0.042))
box = draw.textbbox((0, 0), label, font=f)
text_w, text_h = box[2] - box[0], box[3] - box[1]
pill_h = round(h * 0.095)
icon_d = pill_h - 16
pill_w = 10 + icon_d + 16 + text_w + 26
margin = round(h * 0.04)
x0, y0 = w - margin - pill_w, h - margin - pill_h
draw.rounded_rectangle((x0, y0, x0 + pill_w, y0 + pill_h), radius=pill_h // 2, fill=(17, 24, 39, 228),
                       outline=(255, 255, 255, 210), width=2)
ix0, iy0 = x0 + 10, y0 + (pill_h - icon_d) // 2
draw.ellipse((ix0, iy0, ix0 + icon_d, iy0 + icon_d), fill=(230, 33, 23, 255))
cx, cy = ix0 + icon_d / 2, iy0 + icon_d / 2
t = icon_d * 0.24
draw.polygon([(cx - t * 0.75, cy - t), (cx - t * 0.75, cy + t), (cx + t * 1.1, cy)], fill=(255, 255, 255, 255))
draw.text((ix0 + icon_d + 16 - box[0], y0 + (pill_h - text_h) // 2 - box[1]), label, font=f, fill=(255, 255, 255, 255))
Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB").save(OUT, quality=88, optimize=True, progressive=True)
print(f"saved {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")
