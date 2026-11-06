"""Pinned public artifact download and private, verified streaming snapshots."""

import json
import tempfile
import urllib.error
import urllib.request
from http.client import HTTPMessage
from importlib.resources import files
from pathlib import Path
from typing import BinaryIO

from incidentiq.domain.logs import DatasetManifest, LogError, verify_source


def manifest() -> DatasetManifest:
    return DatasetManifest(
        **json.loads(
            files("incidentiq").joinpath("datasets/apache_2k.json").read_text(encoding="utf-8")
        )
    )


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: BinaryIO,
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> None:
        raise LogError("source_redirect_rejected")


def fetch(directory: Path) -> Path:
    source = manifest()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{source.sha256}.log"
    try:
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
            temporary = Path(output.name)
            try:
                with urllib.request.build_opener(NoRedirect()).open(
                    source.source_url, timeout=15
                ) as response:
                    count = 0
                    while block := response.read(64 * 1024):
                        count += len(block)
                        if count > source.byte_count:
                            raise LogError("source_size_mismatch")
                        output.write(block)
            except OSError, urllib.error.URLError:
                raise LogError("source_download_failed") from None
        verify_source(temporary, source)
        notice = files("incidentiq").joinpath("datasets/LOGHUB-LICENSE.txt")
        (directory / "LOGHUB-LICENSE.txt").write_text(
            notice.read_text(encoding="utf-8"), encoding="utf-8"
        )
        temporary.replace(destination)
        return destination
    finally:
        if "temporary" in locals():
            temporary.unlink(missing_ok=True)
