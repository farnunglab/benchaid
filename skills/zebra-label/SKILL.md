---
name: zebra-label
description: Print labels on the lab's Zebra ZD411 printer (2"x1" labels). Use when asked to print labels, tube labels, box labels, sample labels, or anything involving the Zebra/label printer. Supports text labels, barcodes, and raw ZPL.
---

# Zebra Label Printing

## Printer

- **Model:** Zebra ZD411, 203 dpi
- **Labels:** 2" × 1" (406 × 203 dots)
- **Connection:** Raw ZPL via TCP — `10.119.232.22:9100` (p910nd)

## Quick Use

```bash
cd skills/zebra-label

# Simple text label
python3 scripts/print_label.py --text "Pol II" --subtext "5.2 µM  2025-01-30"

# With barcode
python3 scripts/print_label.py --text "LF-P042" --subtext "pFastBac-RPB1" --barcode "LF-P042"

# Tube label (rotated for wrapping)
python3 scripts/print_label.py --text "Pol II" --subtext "5 µM" --style tube

# Multiple copies
python3 scripts/print_label.py --text "Buffer A" --copies 5

# Raw ZPL
python3 scripts/print_label.py --zpl "^XA^FO50,50^A0N,40,40^FDHello^FS^XZ"

# From file
python3 scripts/print_label.py --file label.zpl

# Dry run (preview ZPL without printing)
python3 scripts/print_label.py --text "Test" --dry-run
```

## Label Styles

| Style | Flag | Use case |
|-------|------|----------|
| `standard` | default | Flat surfaces: boxes, plates, notebooks |
| `tube` | `--style tube` | 1.5 mL tubes — text rotated 90° |

## Custom ZPL

For complex layouts, build ZPL directly. Key coordinates:
- Print area: 406 × 203 dots (203 dpi)
- `^FO x,y` — field origin
- `^A0N,h,w` — scalable font, Normal rotation, height, width
- `^BCN,h` — Code 128 barcode
- `^PQ n` — print quantity

Always use `--dry-run` first when building custom ZPL to verify layout.

## Common Lab Patterns

**Protein aliquot:** `--text "Pol II" --subtext "5.2 µM  50 µL  2025-01-30" --style tube`

**Plasmid tube:** `--text "LF-P042" --subtext "pFastBac-RPB1  150 ng/µL" --barcode "LF-P042" --style tube`

**Storage box:** `--text "Histones" --subtext "Rack 3, Shelf 2  -80°C"`

**Buffer bottle:** `--text "HEPES Buffer" --subtext "25 mM HEPES pH 7.5, 150 mM NaCl" --copies 2`
