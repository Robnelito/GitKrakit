"""Compatibility bridge for PyUpdater 4 with modern ``packaging``.

PyUpdater passes an archive name such as ``GitKrakit-win-1.0.0.zip`` to
``packaging.version.parse``. Packaging 22 removed its permissive legacy-version
parser, while current PyInstaller correctly requires packaging 22 or newer.
This shim is activated only for the ``pyupdater pkg`` process through
``PYTHONPATH`` and extracts the embedded semantic version on that legacy path.
"""
from __future__ import annotations

import re

import packaging.version
from packaging.version import InvalidVersion


_original_parse = packaging.version.parse
_archive_version = re.compile(r"(?<!\d)(\d+\.\d+\.\d+)(?!\d)")


def _parse_with_archive_fallback(value):
    try:
        return _original_parse(value)
    except InvalidVersion:
        if isinstance(value, str):
            matches = _archive_version.findall(value)
            if matches:
                return _original_parse(matches[-1])
        raise


packaging.version.parse = _parse_with_archive_fallback
