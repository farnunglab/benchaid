---
name: gel-annotation
description: Annotate SDS-PAGE gel images with molecular weight markers and lane labels. Use when asked to label, annotate, or analyze gel photos. Detects lanes and bands automatically via intensity profiling (scikit-image), assigns MW from known protein ladders, and outputs SVG-quality annotated images.
---

# Gel Annotation

Automated SDS-PAGE gel annotation: band detection, MW assignment, lane labeling.

## Quick Start

```bash
# Basic annotation with PageRuler 26616 ladder (default)
python3 scripts/annotate_gel.py input.png -o annotated.png

# Specify ladder and ladder lane
python3 scripts/annotate_gel.py input.png --ladder pageruler-26616 --ladder-lane 0

# Custom MW values
python3 scripts/annotate_gel.py input.png --mw 140,115,80,70,50,40,30,25,15,10

# Custom lane labels (comma-separated; use "Ladder" for the marker lane)
python3 scripts/annotate_gel.py input.png --labels "Ladder,Input,FT,Wash,Elution"

# Output SVG (vector labels, raster gel)
python3 scripts/annotate_gel.py input.png --format svg -o annotated.svg

# High-res PNG from SVG (2x default)
python3 scripts/annotate_gel.py input.png --format png --scale 2 -o annotated_hires.png
```

## CLI Reference

Located at `skills/gel-annotation/scripts/annotate_gel.py`.

| Flag | Default | Description |
|------|---------|-------------|
| `input` | (required) | Input gel image (PNG, JPEG, HEIC via sips conversion) |
| `-o, --output` | `annotated.png` | Output file path |
| `--ladder` | `pageruler-26616` | Preset ladder name |
| `--mw` | (from ladder) | Comma-separated MW values (kDa), overrides ladder |
| `--ladder-lane` | `0` | Lane index for the MW ladder (0 = leftmost) |
| `--labels` | auto (Ladder,A,B,...) | Comma-separated lane labels |
| `--format` | `png` | Output format: `png`, `svg` |
| `--scale` | `2` | PNG render scale (via rsvg-convert) |
| `--ref-bands` | `70,40,25` | Reference bands to highlight in red |
| `--band-sigma` | `4` | Gaussian sigma for band detection smoothing |
| `--lane-sigma` | `8` | Gaussian sigma for lane detection smoothing |
| `--min-prominence` | `3` | Minimum peak prominence for band detection |
| `--font-size` | `16` | Base font size for labels |
| `--no-lines` | false | Skip dashed MW indicator lines |

## Supported Ladders

| Name | Bands (kDa) | Catalog |
|------|-------------|---------|
| `pageruler-26616` | 140, 115, 80, 70, 50, 40, 30, 25, 15, 10 | Thermo 26616 |
| `pageruler-26619` | 250, 130, 100, 70, 55, 35, 25, 15, 10 | Thermo 26619 |

Add new ladders in the `LADDERS` dict in the script.

## Pipeline

1. **Convert** HEIC → PNG via `sips` (macOS) if needed
2. **Detect lanes** — vertical intensity profile aggregated across gel height, peak detection
3. **Detect bands** — per-lane horizontal intensity profile, Gaussian-smoothed peak detection
4. **Assign MW** — match detected bands in ladder lane to known MW values (count must match)
5. **Render SVG** — gel as embedded raster `<image>`, all labels as vector `<text>` elements
6. **Export** — SVG direct or PNG via `rsvg-convert` at specified scale

## Tuning

If band detection misses bands or picks up noise:
- Adjust `--band-sigma` (higher = smoother, fewer peaks)
- Adjust `--min-prominence` (higher = only strong bands)
- For overloaded lanes, increase prominence threshold

If lane detection fails:
- Adjust `--lane-sigma`
- Manually specify lane count or positions (future flag)

## Dependencies

- Python 3: `numpy`, `scipy`, `scikit-image`, `Pillow`
- `rsvg-convert` (for PNG export from SVG; install via `brew install librsvg`)
- `sips` (macOS built-in, for HEIC conversion)
