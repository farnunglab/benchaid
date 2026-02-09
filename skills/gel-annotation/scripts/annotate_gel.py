#!/usr/bin/env python3
"""
SDS-PAGE gel annotation tool.

Detects lanes and bands via intensity profiling (scipy), assigns molecular
weights from known protein ladders, and outputs an SVG (vector labels over
raster gel image) or high-res PNG.

Usage:
    python3 annotate_gel.py input.png -o annotated.png
    python3 annotate_gel.py input.heic --ladder pageruler-26616 --format svg -o gel.svg
    python3 annotate_gel.py input.png --mw 250,130,100,70,55,35,25,15,10 --labels "M,1,2,3"
"""

import argparse
import base64
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

# ---------------------------------------------------------------------------
# Supported ladders
# ---------------------------------------------------------------------------
LADDERS = {
    "pageruler-26616": {
        "name": "PageRuler™ Prestained 10–180 kDa",
        "catalog": "Thermo 26616",
        "mw": [140, 115, 80, 70, 50, 40, 30, 25, 15, 10],
        "ref_bands": [70, 40, 25],
    },
    "pageruler-26619": {
        "name": "PageRuler™ Plus Prestained 10–250 kDa",
        "catalog": "Thermo 26619",
        "mw": [250, 130, 100, 70, 55, 35, 25, 15, 10],
        "ref_bands": [70, 55, 35],
    },
}

# ---------------------------------------------------------------------------
# Image loading (with HEIC conversion)
# ---------------------------------------------------------------------------

def load_image(path: str) -> str:
    """Load image, converting HEIC to PNG if needed. Returns path to a PNG/JPEG."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".heic", ".heif"):
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        subprocess.run(
            ["sips", "-s", "format", "png", path, "--out", tmp.name],
            check=True,
            capture_output=True,
        )
        return tmp.name
    return path


# ---------------------------------------------------------------------------
# Lane detection
# ---------------------------------------------------------------------------

def detect_lanes(gel_inv: np.ndarray, sigma: float = 8, min_prom: float = 3) -> list[int]:
    """
    Detect lane centres by aggregating vertical intensity votes across multiple
    horizontal slices of the gel.
    """
    h, w = gel_inv.shape
    y_start, y_end = int(h * 0.15), int(h * 0.85)

    # Vote accumulator
    votes = np.zeros(w, dtype=float)
    for y in range(y_start, y_end, 5):
        strip = np.mean(gel_inv[max(0, y - 3): y + 3, :], axis=0)
        smooth = gaussian_filter1d(strip, sigma=sigma)
        peaks, _ = find_peaks(smooth, distance=40, prominence=min_prom)
        for p in peaks:
            lo, hi = max(0, p - 15), min(w, p + 16)
            votes[lo:hi] += 1

    vote_smooth = gaussian_filter1d(votes, sigma=10)
    lane_peaks, _ = find_peaks(vote_smooth, distance=60, prominence=5)
    return sorted(lane_peaks.tolist())


# ---------------------------------------------------------------------------
# Band detection
# ---------------------------------------------------------------------------

def detect_bands(
    gel_inv: np.ndarray,
    lane_x: int,
    sigma: float = 4,
    min_prom: float = 3,
    half_width: int = 30,
) -> tuple[list[int], list[float]]:
    """Detect band Y-positions in a single lane. Returns (y_positions, prominences)."""
    h, w = gel_inv.shape
    x0 = max(0, lane_x - half_width)
    x1 = min(w, lane_x + half_width)
    profile = np.mean(gel_inv[:, x0:x1], axis=1)
    smooth = gaussian_filter1d(profile, sigma=sigma)
    peaks, props = find_peaks(smooth, distance=12, prominence=min_prom)
    return peaks.tolist(), props["prominences"].tolist()


def match_bands_to_mw(
    gel_inv: np.ndarray,
    lane_x: int,
    n_expected: int,
    sigma: float = 4,
    base_prom: float = 3,
) -> list[int]:
    """
    Iteratively adjust prominence to get exactly n_expected bands in the ladder
    lane. Returns the Y-positions of the matched bands.
    """
    best_ys = None
    best_diff = 999

    for prom_mult in [x * 0.1 for x in range(1, 80)]:
        prom = base_prom * prom_mult
        ys, _ = detect_bands(gel_inv, lane_x, sigma=sigma, min_prom=prom)
        diff = abs(len(ys) - n_expected)
        if diff < best_diff:
            best_diff = diff
            best_ys = ys
        if diff == 0:
            break

    if best_ys is None or len(best_ys) != n_expected:
        # Fallback: take the n_expected most prominent peaks
        ys_all, proms = detect_bands(gel_inv, lane_x, sigma=sigma, min_prom=0.5)
        if len(ys_all) >= n_expected:
            # Sort by prominence descending, pick top n, re-sort by y
            paired = sorted(zip(proms, ys_all), reverse=True)[:n_expected]
            best_ys = sorted([y for _, y in paired])
        else:
            best_ys = ys_all  # best effort

    return best_ys


# ---------------------------------------------------------------------------
# SVG generation
# ---------------------------------------------------------------------------

def build_svg(
    img_path: str,
    lane_xs: list[int],
    ladder_lane_idx: int,
    ladder_band_ys: list[int],
    mw_values: list[int],
    ref_bands: list[int],
    lane_labels: list[str],
    font_size: int = 16,
    show_lines: bool = True,
) -> str:
    """Build an SVG string with the gel as embedded raster and vector labels."""
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    img = Image.open(img_path)
    w, h = img.size
    ext_left = 120
    ext_top = 90
    tw = w + ext_left
    th = h + ext_top

    lines: list[str] = []
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{tw}" height="{th}" '
        f'viewBox="0 0 {tw} {th}">'
    )
    lines.append("<style>")
    lines.append(
        f"  .mw {{ font-family: Helvetica,Arial,sans-serif; font-size: {font_size}px; fill: #444; }}"
    )
    lines.append(
        f"  .mw-ref {{ font-family: Helvetica,Arial,sans-serif; font-size: {font_size + 1}px; "
        f"fill: #c00; font-weight: bold; }}"
    )
    lines.append(
        f"  .lane {{ font-family: Helvetica,Arial,sans-serif; font-size: {font_size + 1}px; "
        f"fill: #333; font-weight: 500; }}"
    )
    lines.append("</style>")
    lines.append(f'<rect width="{tw}" height="{th}" fill="white"/>')
    lines.append(
        f'<image href="data:image/png;base64,{img_b64}" '
        f'x="{ext_left}" y="{ext_top}" width="{w}" height="{h}"/>'
    )

    # MW labels + dashed lines
    ladder_x = lane_xs[ladder_lane_idx] if ladder_lane_idx < len(lane_xs) else lane_xs[0]
    for mw, y in zip(mw_values, ladder_band_ys):
        ya = y + ext_top
        is_ref = mw in ref_bands
        cls = "mw-ref" if is_ref else "mw"
        lc = "#c44" if is_ref else "#999"
        if show_lines:
            lines.append(
                f'  <line x1="{ext_left - 5}" y1="{ya}" x2="{ext_left + ladder_x + 30}" '
                f'y2="{ya}" stroke="{lc}" stroke-width="0.8" stroke-dasharray="4,3"/>'
            )
        lines.append(
            f'  <text x="{ext_left - 8}" y="{ya + 5}" text-anchor="end" class="{cls}">{mw}</text>'
        )

    # kDa label
    if ladder_band_ys:
        yt = ladder_band_ys[0] + ext_top - 18
        lines.append(
            f'  <text x="{ext_left - 8}" y="{yt}" text-anchor="end" '
            f'class="mw" font-style="italic">kDa</text>'
        )

    # Lane labels (45° rotated)
    for i, lx in enumerate(lane_xs):
        label = lane_labels[i] if i < len(lane_labels) else chr(ord("A") + i - 1)
        xa = lx + ext_left
        ya = ext_top - 10
        lines.append(
            f'  <text x="{xa}" y="{ya}" text-anchor="start" class="lane" '
            f'transform="rotate(-45 {xa} {ya})">{label}</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def svg_to_png(svg_path: str, png_path: str, scale: int = 2) -> None:
    """Render SVG to PNG via rsvg-convert."""
    subprocess.run(
        ["rsvg-convert", "-z", str(scale), svg_path, "-o", png_path],
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Annotate SDS-PAGE gel images with MW markers and lane labels."
    )
    p.add_argument("input", help="Input gel image (PNG, JPEG, HEIC)")
    p.add_argument("-o", "--output", default="annotated.png", help="Output file path")
    p.add_argument(
        "--ladder",
        default="pageruler-26616",
        choices=list(LADDERS.keys()),
        help="Preset ladder name",
    )
    p.add_argument("--mw", help="Comma-separated MW values (kDa), overrides --ladder")
    p.add_argument(
        "--ladder-lane", type=int, default=0, help="Lane index for MW ladder (0=leftmost)"
    )
    p.add_argument("--labels", help='Comma-separated lane labels (e.g. "Ladder,A,B,C")')
    p.add_argument(
        "--format", choices=["png", "svg"], default="png", help="Output format"
    )
    p.add_argument("--scale", type=int, default=2, help="PNG render scale")
    p.add_argument("--ref-bands", help="Reference bands to highlight (default from ladder)")
    p.add_argument(
        "--band-sigma", type=float, default=4, help="Gaussian sigma for band detection"
    )
    p.add_argument(
        "--lane-sigma", type=float, default=8, help="Gaussian sigma for lane detection"
    )
    p.add_argument(
        "--min-prominence", type=float, default=3, help="Min peak prominence for bands"
    )
    p.add_argument("--font-size", type=int, default=16, help="Base font size")
    p.add_argument("--no-lines", action="store_true", help="Skip dashed MW lines")

    args = p.parse_args()

    # Load image
    img_path = load_image(args.input)
    img = Image.open(img_path).convert("L")
    gel = np.array(img, dtype=float)
    gel_inv = 255.0 - gel

    # Resolve MW values
    if args.mw:
        mw_values = [int(x.strip()) for x in args.mw.split(",")]
        ref_bands = [70, 40, 25]
    else:
        ladder = LADDERS[args.ladder]
        mw_values = ladder["mw"]
        ref_bands = ladder["ref_bands"]

    if args.ref_bands:
        ref_bands = [int(x.strip()) for x in args.ref_bands.split(",")]

    # Detect lanes
    lane_xs = detect_lanes(gel_inv, sigma=args.lane_sigma, min_prom=args.min_prominence)
    print(f"Detected {len(lane_xs)} lanes at x = {lane_xs}")

    if not lane_xs:
        print("ERROR: No lanes detected. Try adjusting --lane-sigma or --min-prominence.", file=sys.stderr)
        sys.exit(1)

    # Detect ladder bands
    ladder_idx = min(args.ladder_lane, len(lane_xs) - 1)
    ladder_x = lane_xs[ladder_idx]
    ladder_ys = match_bands_to_mw(
        gel_inv, ladder_x, len(mw_values), sigma=args.band_sigma, base_prom=args.min_prominence
    )
    print(f"Ladder lane (x={ladder_x}): {len(ladder_ys)} bands at y = {ladder_ys}")

    if len(ladder_ys) != len(mw_values):
        print(
            f"WARNING: Expected {len(mw_values)} bands, detected {len(ladder_ys)}. "
            f"MW assignment may be inaccurate.",
            file=sys.stderr,
        )
        # Truncate or pad
        if len(ladder_ys) > len(mw_values):
            ladder_ys = ladder_ys[: len(mw_values)]
        else:
            mw_values = mw_values[: len(ladder_ys)]

    # Build labels
    if args.labels:
        lane_labels = [x.strip() for x in args.labels.split(",")]
    else:
        lane_labels = ["Ladder"] + [chr(ord("A") + i) for i in range(len(lane_xs) - 1)]

    # Generate SVG
    svg_content = build_svg(
        img_path=img_path,
        lane_xs=lane_xs,
        ladder_lane_idx=ladder_idx,
        ladder_band_ys=ladder_ys,
        mw_values=mw_values,
        ref_bands=ref_bands,
        lane_labels=lane_labels,
        font_size=args.font_size,
        show_lines=not args.no_lines,
    )

    if args.format == "svg":
        out = args.output if args.output.endswith(".svg") else args.output.rsplit(".", 1)[0] + ".svg"
        with open(out, "w") as f:
            f.write(svg_content)
        print(f"SVG saved: {out}")
    else:
        # Write SVG to temp, convert to PNG
        svg_tmp = tempfile.NamedTemporaryFile(suffix=".svg", delete=False)
        svg_tmp.write(svg_content.encode())
        svg_tmp.close()
        out = args.output if args.output.endswith(".png") else args.output.rsplit(".", 1)[0] + ".png"
        svg_to_png(svg_tmp.name, out, scale=args.scale)
        os.unlink(svg_tmp.name)
        print(f"PNG saved: {out} (scale={args.scale}x)")

    # Cleanup temp HEIC conversion
    if img_path != args.input and os.path.exists(img_path):
        os.unlink(img_path)


if __name__ == "__main__":
    main()
