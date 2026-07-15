"""Set GitKrakit's single source-of-truth release version."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "gitkrakit" / "__init__.py"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
ASSIGNMENT = re.compile(r'^__version__\s*=\s*"[^"]+"$', re.MULTILINE)


def set_version(version: str) -> None:
    if not SEMVER.fullmatch(version):
        raise ValueError("Version must use MAJOR.MINOR.PATCH, for example 1.0.1")

    source = VERSION_FILE.read_text(encoding="utf-8")
    updated, count = ASSIGNMENT.subn(f'__version__ = "{version}"', source)
    if count != 1:
        raise RuntimeError(f"Expected exactly one __version__ in {VERSION_FILE}")
    VERSION_FILE.write_text(updated, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Release version in MAJOR.MINOR.PATCH format")
    args = parser.parse_args()
    set_version(args.version)
    print(f"GitKrakit version set to {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
