#!/usr/bin/env python3
"""Regenerate the checked-in macOS icon from the existing website SVGs.

Requires Inkscape on PATH (generated with Inkscape 1.4). This is an artwork
maintenance tool, not part of the app build or its runtime dependencies.
"""
import argparse
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "doc/public/img/brand"
SVG = "http://www.w3.org/2000/svg"
# ICNS PNG representations: logical point size and display scale matter even
# where two entries happen to have the same pixel dimensions.
REPRESENTATIONS = (
    (b"icp4", 16, 1), (b"ic11", 16, 2),
    (b"icp5", 32, 1), (b"ic12", 32, 2),
    (b"ic07", 128, 1), (b"ic13", 128, 2),
    (b"ic08", 256, 1), (b"ic14", 256, 2),
    (b"ic09", 512, 1), (b"ic10", 512, 2),
)


def artwork(compact):
    """Keep the approved paths intact; add only a neutral macOS icon backing."""
    ET.register_namespace("", SVG)
    canvas = ET.Element(f"{{{SVG}}}svg", {
        "width": "1024", "height": "1024", "viewBox": "0 0 1024 1024",
    })
    ET.SubElement(canvas, f"{{{SVG}}}rect", {
        "x": "64", "y": "64", "width": "896", "height": "896",
        "rx": "200", "fill": "#ffffff",
    })
    name = "zudo-stl-fix-symbol-small-black.svg" if compact else "zudo-stl-fix-symbol-black.svg"
    symbol = ET.parse(BRAND / name).getroot()
    symbol.attrib.update({"x": "192", "y": "192", "width": "640", "height": "640"})
    canvas.append(symbol)
    return ET.tostring(canvas, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "packaging/AppIcon.icns")
    args = parser.parse_args()
    inkscape = shutil.which("inkscape")
    if not inkscape:
        parser.error("Inkscape is required only to regenerate artwork; install it and add it to PATH.")

    chunks = []
    with tempfile.TemporaryDirectory(prefix="zudo-app-icon-") as temporary:
        directory = Path(temporary)
        for compact in (False, True):
            (directory / f"{compact}.svg").write_bytes(artwork(compact))
        rendered = {}
        for kind, points, scale in REPRESENTATIONS:
            pixels = points * scale
            compact = points <= 32
            key = (compact, pixels)
            if key not in rendered:
                png = directory / f"{compact}-{pixels}.png"
                subprocess.run([
                    inkscape, str(directory / f"{compact}.svg"), "--export-area-page",
                    f"--export-width={pixels}", f"--export-height={pixels}",
                    "--export-type=png", "--export-png-color-mode=RGBA_8",
                    f"--export-filename={png}",
                ], check=True)
                data = png.read_bytes()
                if (data[:8] != b"\x89PNG\r\n\x1a\n"
                        or struct.unpack(">II", data[16:24]) != (pixels, pixels)):
                    raise ValueError(f"Unexpected PNG output for {points}pt @{scale}x")
                rendered[key] = data
            data = rendered[key]
            chunks.append(kind + struct.pack(">I", len(data) + 8) + data)

    # Each ICNS element is a four-byte type, a big-endian length including its
    # eight-byte header, and its PNG payload. The file uses the same header form.
    payload = b"".join(chunks)
    args.output.write_bytes(b"icns" + struct.pack(">I", len(payload) + 8) + payload)
    print(f"Wrote {args.output} ({len(REPRESENTATIONS)} representations, 16–1024px)")


if __name__ == "__main__":
    main()
