"""Figures for the README and docs, built from the published results so every number traces to a file.

    python scripts/build_docs_figures.py                 # charts (SVG) from validation/results/summary.json
    python scripts/build_docs_figures.py --images        # also: optimise screenshots and build the Road speeds GIF

Charts need only the standard library. --images needs Pillow and the raw screenshots from
web/scripts/readme-shots.mjs (docs/images/raw/*.png, data/gif_frames/speeds/*.png).

Outputs: docs/images/charts/*.svg, docs/images/*.jpg|png, docs/images/speeds-day.gif.
"""
from __future__ import annotations

import argparse
import json
import statistics
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "validation" / "results" / "summary.json"
IMAGES = ROOT / "docs" / "images"
CHARTS = IMAGES / "charts"
RAW = IMAGES / "raw"
FRAMES = ROOT / "data" / "gif_frames" / "speeds"
LIVE_API = "https://13-235-147-97.sslip.io/api"

NAVY, SAFFRON, GREEN, GREY, INK, INK2, RULE = "#1A3A8F", "#E8730C", "#138808", "#A3ACB9", "#111827", "#4B5563", "#E3E5E8"
FONT = "Noto Sans, Segoe UI, Helvetica Neue, Arial, sans-serif"


def svg(width: int, height: int, body: list[str]) -> str:
    # A white card, so the charts read the same on GitHub's light and dark themes.
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'font-family="{FONT}" role="img">\n'
            f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="14" fill="#FFFFFF" stroke="{RULE}"/>\n'
            + "\n".join(body) + "\n</svg>\n")


def text(x, y, value, size=13, fill=INK, weight=400, anchor="start", extra=""):
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}" {extra}>{escape(str(value))}</text>'


def header(title: str, subtitle: str, width: int) -> list[str]:
    return [text(28, 40, title, 19, INK, 700), text(28, 64, subtitle, 13, INK2)]


def eta_methods(summary: dict) -> str:
    eta = summary["eta"]
    labels = eta["labels"]
    rows = sorted(eta["rows"], key=lambda r: r[1])
    width, top, row_h, label_w, bar_w = 820, 96, 34, 330, 330
    height = top + row_h * len(rows) + 46
    worst = max(v for _, v in rows)
    body = header("Bus arrival at a stop, 1 to 30 stops ahead",
                  f"Mean error in seconds on {eta['n']:,} held-out predictions (26 to 31 Oct 2026). Lower is better.", width)
    for i, (key, value) in enumerate(rows):
        y = top + i * row_h
        colour = NAVY if key == "naadi" else SAFFRON if key == "timetable" else GREY
        weight = 700 if key in ("naadi", "timetable") else 400
        w = bar_w * value / worst
        body.append(text(28, y + 21, labels.get(key, key), 13.5, INK, weight))
        body.append(f'<rect x="{28 + label_w}" y="{y + 7}" width="{w:.1f}" height="20" rx="4" fill="{colour}"/>')
        body.append(text(28 + label_w + w + 8, y + 22, f"{value:.1f} s", 13, INK, weight))
    best_other = min(v for k, v in rows if k != "naadi")
    lead = eta["significance"]["diff_mae_s"]
    lo, hi = eta["significance"]["ci95"]
    body.append(text(28, height - 18, f"Naadi is {-lead:.1f} s better than the next best method (95% interval {-hi:.1f} to {-lo:.1f} s); "
                     f"the published timetable is off by {dict(rows)['timetable']:.0f} s.", 12, INK2))
    del best_other
    return svg(width, height, body)


def error_by_distance(summary: dict) -> str:
    bands = summary["eta"]["by_band"]
    names = list(bands)
    width, height, left, base, plot_h = 820, 380, 80, 320, 190
    worst = max(max(b["naadi"], b["timetable"]) for b in bands.values())
    group_w = (width - left - 40) / len(names)
    body = header("The error grows with distance ahead, Naadi's half as fast",
                  "Mean error in seconds by how many stops ahead the bus is, held-out 26 to 31 Oct 2026.", width)
    body.append(f'<rect x="28" y="84" width="12" height="12" rx="2" fill="{NAVY}"/>' + text(46, 95, "Naadi (history + live)", 12.5))
    body.append(f'<rect x="214" y="84" width="12" height="12" rx="2" fill="{SAFFRON}"/>' + text(232, 95, "Published timetable", 12.5))
    for tick in range(0, int(worst) + 100, 200):
        y = base - plot_h * tick / worst
        if y < base - plot_h - 1:
            break
        body.append(f'<line x1="{left}" x2="{width - 30}" y1="{y:.1f}" y2="{y:.1f}" stroke="{RULE}"/>')
        body.append(text(left - 10, y + 4, f"{tick} s", 12, INK2, anchor="end"))
    for i, name in enumerate(names):
        x0 = left + i * group_w + group_w * 0.18
        for j, (key, colour, label) in enumerate((("naadi", NAVY, "Naadi"), ("timetable", SAFFRON, "Timetable"))):
            value = bands[name][key]
            h = plot_h * value / worst
            x = x0 + j * group_w * 0.33
            body.append(f'<rect x="{x:.1f}" y="{base - h:.1f}" width="{group_w * 0.3:.1f}" height="{h:.1f}" rx="4" fill="{colour}"/>')
            body.append(text(x + group_w * 0.15, base - h - 6, f"{value:.0f}", 12.5, INK, 700 if key == "naadi" else 400, "middle"))
        body.append(text(x0 + group_w * 0.31, base + 22, name, 13, INK, 600, "middle"))
    return svg(width, height, body)


def head_to_head(summary: dict) -> str:
    report = summary["journeys"]["report"]
    google = summary["google"]
    calc = summary["eta_calculator"]["methods"]
    panels = [
        ("Door to door", "vs a timetable planner", report["naadi_live"]["calibrated"]["mae_min"], report["timetable"]["calibrated"]["mae_min"],
         "Timetable planner", f"{report['naadi_live']['calibrated']['n']:,} journeys, 29–31 Oct"),
        ("Google Maps", "bus directions, replayed", google["naadi"]["mae_min"], google["google"]["mae_min"], "Google Maps",
         f"{google['both_replayed']} trips, 15–16 Nov"),
        ("ETA Calculator", "the organisers' service", calc["Naadi history + live"]["mae_min"], calc["ETA Calculator (Transport Stack)"]["mae_min"],
         "ETA Calculator", f"{summary['eta_calculator']['n']:,} answers, 15–16 Nov"),
    ]
    width, height, base, plot_h = 820, 410, 320, 150
    worst = max(max(p[2], p[3]) for p in panels)
    panel_w = (width - 56) / len(panels)
    body = header("Head to head on trips that really happened",
                  "Mean error in minutes, each planner's answer followed on the buses that ran. Lower is better.", width)
    for i, (title, sub, ours, theirs, their_name, sample) in enumerate(panels):
        x0 = 28 + i * panel_w
        cx = x0 + panel_w / 2
        body.append(text(cx, 104, title, 15, INK, 700, "middle"))
        body.append(text(cx, 122, sub, 12.5, INK2, anchor="middle"))
        for j, (value, colour, name) in enumerate(((ours, NAVY, "Naadi"), (theirs, SAFFRON if i == 0 else GREY, their_name))):
            h = plot_h * value / worst
            x = cx - 78 + j * 86
            body.append(f'<rect x="{x:.1f}" y="{base - h:.1f}" width="70" height="{h:.1f}" rx="5" fill="{colour}"/>')
            body.append(text(x + 35, base - h - 8, f"{value:.1f}", 16, INK, 700, "middle"))
            body.append(text(x + 35, base + 20, name, 12, INK, 600 if j == 0 else 400, "middle"))
        body.append(text(cx, base + 44, sample, 11.5, INK2, anchor="middle"))
        if i:
            body.append(f'<line x1="{x0:.1f}" x2="{x0:.1f}" y1="96" y2="{base + 50}" stroke="{RULE}"/>')
    body.append(text(28, height - 16, "Naadi's mean error is lower in all three; the Google and ETA Calculator samples cover two November days.", 12, INK2))
    return svg(width, height, body)


def speed_by_hour(cells: list[dict]) -> str:
    series = {}
    for day in ("weekday", "weekend"):
        values = []
        for hour in range(24):
            xs = [c[day][hour] for c in cells if c.get(day) and c[day][hour] is not None]
            values.append(statistics.median(xs) if xs else None)
        series[day] = values
    width, height, left, right, top, base = 820, 380, 70, 40, 100, 320
    y_max = 40
    sx = lambda h: left + (width - left - right) * h / 23
    sy = lambda v: base - (base - top) * v / y_max
    body = header("The timetable assumes 18 km/h. Real buses don't.",
                  f"Median bus speed across {len(cells):,} road cells by hour, from October 2026 GPS.", width)
    for v in range(0, y_max + 1, 10):
        body.append(f'<line x1="{left}" x2="{width - right}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" stroke="{RULE}"/>')
        body.append(text(left - 10, sy(v) + 4, f"{v}", 12, INK2, anchor="end"))
    body.append(text(left - 46, top - 14, "km/h", 12, INK2))
    for h in range(0, 24, 3):
        body.append(text(sx(h), base + 22, f"{h:02d}:00", 12, INK2, anchor="middle"))
    body.append(f'<line x1="{left}" x2="{width - right}" y1="{sy(18):.1f}" y2="{sy(18):.1f}" stroke="{SAFFRON}" stroke-width="2.5" stroke-dasharray="8 6"/>')
    body.append(text(sx(0.2), sy(18) + 20, "Timetable: 18 km/h, all day", 12.5, SAFFRON, 700))
    for day, colour in (("weekday", NAVY), ("weekend", GREEN)):
        points = " ".join(f"{sx(h):.1f},{sy(v):.1f}" for h, v in enumerate(series[day]) if v is not None)
        body.append(f'<polyline points="{points}" fill="none" stroke="{colour}" stroke-width="3" stroke-linejoin="round"/>')
    wd = series["weekday"]
    fast = max(range(24), key=lambda h: wd[h] or 0)
    slow = min(range(24), key=lambda h: wd[h] if wd[h] is not None else 99)
    for h, label in ((fast, f"{wd[fast]:.1f} km/h at {fast:02d}:00"), (slow, f"{wd[slow]:.1f} km/h at {slow:02d}:00")):
        body.append(f'<circle cx="{sx(h):.1f}" cy="{sy(wd[h]):.1f}" r="5" fill="{NAVY}"/>')
        body.append(text(sx(h) + (10 if h < 18 else -10), sy(wd[h]) + (-10 if h == fast else 20), label, 12.5, NAVY, 700, "start" if h < 18 else "end"))
    body.append(f'<rect x="{width - 230}" y="86" width="12" height="4" fill="{NAVY}"/>' + text(width - 212, 92, "Weekdays", 12.5))
    body.append(f'<rect x="{width - 130}" y="86" width="12" height="4" fill="{GREEN}"/>' + text(width - 112, 92, "Weekends", 12.5))
    return svg(width, height, body)


def fetch(url: str):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def build_images() -> None:
    from PIL import Image  # noqa: PLC0415  (only needed with --images)

    small = {"pulse-card.png", "samay-chakra.png"}
    for raw in sorted(RAW.glob("*.png")):
        image = Image.open(raw).convert("RGB")
        if raw.name.startswith("phone-"):
            image = image.resize((image.width * 2 // 3, image.height * 2 // 3), Image.LANCZOS)
        if raw.name in small:
            out = IMAGES / raw.name
            image.save(out, optimize=True)
        else:
            out = IMAGES / (raw.stem + ".jpg")
            image.save(out, quality=86, optimize=True, progressive=True)
        print(f"{out.relative_to(ROOT)}  {out.stat().st_size // 1024} KB")
    frames = sorted(FRAMES.glob("hour-*.png"))
    if frames:
        images = [Image.open(f).convert("RGB").resize((960, 600), Image.LANCZOS) for f in frames]
        palette = images[len(images) // 2].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
        quantised = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in images]
        out = IMAGES / "speeds-day.gif"
        quantised[0].save(out, save_all=True, append_images=quantised[1:], duration=[650] * (len(quantised) - 1) + [1600],
                          loop=0, optimize=True, disposal=1)
        print(f"{out.relative_to(ROOT)}  {out.stat().st_size // 1024} KB, {len(frames)} frames")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=LIVE_API, help="API for the road-speed cells (default: the live site)")
    ap.add_argument("--images", action="store_true", help="also optimise screenshots and build the GIF (needs Pillow)")
    args = ap.parse_args()
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    CHARTS.mkdir(parents=True, exist_ok=True)
    charts = {"eta-methods.svg": eta_methods(summary), "error-by-distance.svg": error_by_distance(summary),
              "head-to-head.svg": head_to_head(summary),
              "speed-by-hour.svg": speed_by_hour(fetch(args.api.rstrip("/") + "/speeds/cells")["cells"])}
    for name, body in charts.items():
        (CHARTS / name).write_text(body, encoding="utf-8")
        print(f"docs/images/charts/{name}")
    if args.images:
        build_images()


if __name__ == "__main__":
    main()
