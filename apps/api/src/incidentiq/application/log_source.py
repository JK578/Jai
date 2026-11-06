"""Private source snapshots for bounded, verified ingestion."""

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from incidentiq.domain.logs import MAX_FILE_BYTES, DatasetManifest, LogError, verify_source


@contextmanager
def verified_stream(path: Path, source: DatasetManifest) -> Iterator[BinaryIO]:
    # Private copy prevents a changed cache path from altering an already verified run.
    with tempfile.TemporaryDirectory(prefix="incidentiq-source-") as directory:
        snapshot = Path(directory) / "source.log"
        try:
            with path.open("rb") as original, snapshot.open("wb") as target:
                count = 0
                while block := original.read(64 * 1024):
                    count += len(block)
                    if count > MAX_FILE_BYTES:
                        raise LogError("source_size_mismatch")
                    target.write(block)
        except OSError:
            raise LogError("source_unavailable") from None
        verify_source(snapshot, source)
        with snapshot.open("rb") as stream:
            yield stream
