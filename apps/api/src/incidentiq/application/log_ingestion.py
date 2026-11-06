"""Synchronous bounded worker; repository transactions own checkpoints and fencing."""

from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from incidentiq.application.log_source import verified_stream
from incidentiq.domain.logs import (
    MAX_BATCH_BYTES,
    DatasetManifest,
    IngestionRun,
    LogError,
    LogTransient,
    ParsedLine,
    records,
)


class IngestionRepository(Protocol):
    def claim(self, source: DatasetManifest, token: UUID, resume: UUID | None) -> IngestionRun: ...
    def checkpoint(self, run_id: UUID, token: UUID) -> IngestionRun: ...
    def commit_batch(self, run_id: UUID, token: UUID, batch: list[ParsedLine]) -> None: ...
    def finish(self, run_id: UUID, token: UUID, expected_lines: int) -> IngestionRun: ...
    def fail(self, run_id: UUID, token: UUID) -> None: ...


def ingest(
    repository: IngestionRepository,
    path: Path,
    source: DatasetManifest,
    *,
    batch_size: int = 250,
    resume: UUID | None = None,
) -> IngestionRun:
    if not 10 <= batch_size <= 500:
        raise LogError("invalid_batch_size")
    token = uuid4()
    with verified_stream(path, source) as stream:
        run = repository.claim(source, token, resume)
        try:
            batch: list[ParsedLine] = []
            size = 0

            def flush() -> None:
                for attempt in range(3):
                    try:
                        repository.commit_batch(run.id, token, batch)
                        return
                    except LogTransient:
                        # A lost commit acknowledgement may still have committed the whole batch.
                        current = repository.checkpoint(run.id, token)
                        if current.last_committed_line >= batch[-1].source_line:
                            return
                        if attempt == 2:
                            raise

            for item in records(stream, source.file_id):
                if item.source_line <= run.last_committed_line:
                    continue
                if batch and (len(batch) >= batch_size or size + item.size > MAX_BATCH_BYTES):
                    flush()
                    batch, size = [], 0
                batch.append(item)
                size += item.size
            if batch:
                flush()
            return repository.finish(run.id, token, source.line_count)
        except LogError:
            try:
                repository.fail(run.id, token)
            except LogError:
                pass  # A stale worker must never overwrite its successor's state.
            raise
