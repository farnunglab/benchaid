#!/usr/bin/env python3
"""Send ZPL to a Zebra printer via raw TCP (p910nd on port 9100).

Usage:
    python3 print_label.py --zpl "^XA^FO50,50^A0N,40,40^FDHello^FS^XZ"
    python3 print_label.py --file label.zpl
    python3 print_label.py --text "Pol II" --subtext "5.2 µM  2025-01-30" --copies 2
    python3 print_label.py --text "LF-P042" --subtext "pFastBac-RPB1" --barcode "LF-P042"
"""

import argparse
import socket
import sys
import textwrap
from datetime import datetime

PRINTER_IP = "10.119.232.22"
PRINTER_PORT = 9100
# Label: 2" x 1" (406 x 203 dots at 203 dpi)
LABEL_W = 406
LABEL_H = 203


def send_zpl(zpl: str, ip: str = PRINTER_IP, port: int = PRINTER_PORT) -> None:
    """Send raw ZPL string to the printer."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(5)
        s.connect((ip, port))
        s.sendall(zpl.encode("utf-8"))
    print(f"Sent {len(zpl)} bytes to {ip}:{port}")


def build_simple_label(text: str, subtext: str = "", barcode: str = "") -> str:
    """Build ZPL for a simple 2x1 inch label.

    Layout (2" x 1", 203 dpi = 406 x 203 dots):
      - Main text: bold, large
      - Subtext: smaller, below main text
      - Optional Code128 barcode at bottom
    """
    zpl_parts = [
        "^XA",
        f"^PW{LABEL_W}",        # print width
        f"^LL{LABEL_H}",        # label length
        "^LH0,0",               # label home
    ]

    y = 15
    # Main text — large
    zpl_parts.append(f"^FO20,{y}^A0N,45,45^FB{LABEL_W - 40},1,0,L^FD{_esc(text)}^FS")
    y += 55

    # Subtext — smaller
    if subtext:
        zpl_parts.append(f"^FO20,{y}^A0N,28,28^FB{LABEL_W - 40},2,0,L^FD{_esc(subtext)}^FS")
        y += 35

    # Barcode
    if barcode:
        # Code128 auto — height adjusted to fit remaining space
        bar_h = max(30, LABEL_H - y - 30)
        zpl_parts.append(f"^FO20,{y}^BCN,{bar_h},N,N,N^FD{_esc(barcode)}^FS")

    zpl_parts.append("^XZ")
    return "\n".join(zpl_parts)


def build_tube_label(text: str, subtext: str = "", barcode: str = "") -> str:
    """Compact tube label: rotated 90° for wrapping around 1.5 mL tubes.
    
    Prints sideways so the label wraps around the tube with text readable
    when the tube is held upright.
    """
    zpl_parts = [
        "^XA",
        f"^PW{LABEL_W}",
        f"^LL{LABEL_H}",
        "^LH0,0",
    ]

    # Rotate text 90° (^A0R)
    x = 15
    zpl_parts.append(f"^FO{x},10^A0R,36,36^FD{_esc(text)}^FS")
    x += 45

    if subtext:
        zpl_parts.append(f"^FO{x},10^A0R,24,24^FD{_esc(subtext)}^FS")
        x += 30

    if barcode:
        zpl_parts.append(f"^FO{x},10^BCR,50,N,N,N^FD{_esc(barcode)}^FS")

    zpl_parts.append("^XZ")
    return "\n".join(zpl_parts)


def _esc(s: str) -> str:
    """Escape ZPL special characters."""
    # In ZPL, ^ and ~ are control characters
    return s  # Basic text is fine; add escaping if needed


def main():
    p = argparse.ArgumentParser(description="Print labels on Zebra ZD411")
    p.add_argument("--zpl", help="Raw ZPL string to send")
    p.add_argument("--file", help="Path to .zpl file to send")
    p.add_argument("--text", help="Main label text")
    p.add_argument("--subtext", default="", help="Secondary text line")
    p.add_argument("--barcode", default="", help="Barcode data (Code128)")
    p.add_argument("--style", choices=["standard", "tube"], default="standard",
                   help="Label style: standard (flat) or tube (rotated for tubes)")
    p.add_argument("--copies", type=int, default=1, help="Number of copies")
    p.add_argument("--ip", default=PRINTER_IP, help="Printer IP")
    p.add_argument("--port", type=int, default=PRINTER_PORT, help="Printer port")
    p.add_argument("--dry-run", action="store_true", help="Print ZPL to stdout, don't send")
    args = p.parse_args()

    if args.zpl:
        zpl = args.zpl
    elif args.file:
        with open(args.file) as f:
            zpl = f.read()
    elif args.text:
        builder = build_tube_label if args.style == "tube" else build_simple_label
        zpl = builder(args.text, args.subtext, args.barcode)
    else:
        p.error("Provide --zpl, --file, or --text")

    # Handle copies via ZPL ^PQ
    if args.copies > 1:
        zpl = zpl.replace("^XZ", f"^PQ{args.copies}^XZ")

    if args.dry_run:
        print(zpl)
        return

    send_zpl(zpl, args.ip, args.port)


if __name__ == "__main__":
    main()
