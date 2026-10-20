"""Generate gitkrakit/resources/icon.ico from gitkrakit/resources/logo.svg.

Re-run after any change to the logo, then commit the resulting .ico:
    python scripts/make_icon.py
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

RESOURCES = Path(__file__).resolve().parents[1] / "gitkrakit" / "resources"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_png(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def build_ico(images: list[tuple[int, bytes]]) -> bytes:
    """ICO container holding PNG-compressed frames (supported since Vista)."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, payload = b"", b""
    for size, png in images:
        dimension = 0 if size >= 256 else size  # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(png), offset)
        payload += png
        offset += len(png)
    return header + entries + payload


def main() -> int:
    _app = QGuiApplication(sys.argv)  # noqa: F841 - Qt needs an instance to paint
    renderer = QSvgRenderer(str(RESOURCES / "logo.svg"))
    if not renderer.isValid():
        raise SystemExit("logo.svg is not a valid SVG")
    ico = build_ico([(size, render_png(renderer, size)) for size in SIZES])
    target = RESOURCES / "icon.ico"
    target.write_bytes(ico)
    print(f"{target} ({len(ico)} bytes, sizes {SIZES})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
