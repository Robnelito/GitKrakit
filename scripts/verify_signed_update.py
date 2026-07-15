"""Verify that PyUpdater accepts signed metadata and rejects tampering."""
from __future__ import annotations

import argparse
import gzip
import json
import shutil
import tempfile
from pathlib import Path

from pyupdater.client import Client

from gitkrakit.client_config import ClientConfig


class _LocalDownloader:
    """Use deploy files directly while exercising PyUpdater's verification."""

    root: Path

    def __init__(self, filename, _urls, *_args, **_kwargs):
        self.filename = filename

    def download_verify_return(self):
        return (self.root / self.filename).read_bytes()


def _client(config_class, data_dir: Path, served: Path) -> Client:
    _LocalDownloader.root = served
    client = Client(
        config_class(), data_dir=str(data_dir), downloader=_LocalDownloader
    )
    client.refresh()
    return client


def verify(deploy_dir: Path) -> None:
    required = {"keys.gz", "versions.gz"}
    missing = required.difference(path.name for path in deploy_dir.iterdir())
    if missing:
        raise RuntimeError(f"Missing signed metadata: {', '.join(sorted(missing))}")

    with tempfile.TemporaryDirectory(prefix="gitkrakit-update-test-") as temp:
        root = Path(temp)
        served = root / "served"
        shutil.copytree(deploy_dir, served)

        class LocalConfig(ClientConfig):
            UPDATE_URLS = ["https://local.invalid/"]

        valid = _client(LocalConfig, root / "valid-client", served)
        if not valid.verified:
            raise RuntimeError("Valid signed update metadata was rejected")

        wrong_key = (
            ("A" if ClientConfig.PUBLIC_KEY[0] != "A" else "B")
            + ClientConfig.PUBLIC_KEY[1:]
        )

        class WrongKeyConfig(LocalConfig):
            PUBLIC_KEY = wrong_key

        mismatched = _client(
            WrongKeyConfig, root / "wrong-key-client", served
        )
        if mismatched.verified:
            raise RuntimeError("Metadata signed by a different key was accepted")

        versions_path = served / "versions.gz"
        with gzip.open(versions_path, "rt", encoding="utf-8") as stream:
            manifest = json.load(stream)
        manifest["tampered"] = True
        with gzip.open(versions_path, "wt", encoding="utf-8") as stream:
            json.dump(manifest, stream, sort_keys=True)

        tampered = _client(LocalConfig, root / "tampered-client", served)
        if tampered.verified:
            raise RuntimeError("Tampered update metadata was accepted")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "deploy_dir",
        nargs="?",
        type=Path,
        default=Path("pyu-data/deploy"),
    )
    args = parser.parse_args()
    verify(args.deploy_dir.resolve())
    print("Signed metadata verification and tamper rejection passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
