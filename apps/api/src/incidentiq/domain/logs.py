"""Log identities and parsing. No framework, database or network imports."""

import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid5

NAMESPACE = UUID("7027a76a-b5bf-4e31-8475-ddc79a467f0b")
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_LINE_BYTES = 16 * 1024
MAX_BATCH_BYTES = 512 * 1024
MAX_ERRORS = 100
LEASE_SECONDS = 60
LEVELS = {
    "emerg": "emergency",
    "alert": "alert",
    "crit": "critical",
    "error": "error",
    "warn": "warning",
    "warning": "warning",
    "notice": "notice",
    "info": "info",
    "debug": "debug",
}
MONTHS = dict(
    zip("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), range(1, 13), strict=True)
)
ENVELOPE = re.compile(r"^\[([^\]]{1,40})\] \[([A-Za-z]{1,16})\] (.*)$")


class LogError(Exception):
    """Only fixed public error codes may be used as messages."""


class LogBusy(LogError):
    pass


class LogUnavailable(LogError):
    pass


class LogTransient(LogUnavailable):
    pass


@dataclass(frozen=True)
class DatasetManifest:
    slug: str
    name: str
    provider: str
    repository: str
    commit: str
    source_path: str
    sha256: str
    byte_count: int
    line_count: int
    parser_version: str
    retrieved_on: str
    provenance_url: str
    original_source_url: str
    license_name: str
    license_url: str
    timezone_name: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9-]{1,60}", self.slug):
            raise LogError("invalid_manifest")
        if not re.fullmatch(r"[0-9a-f]{40}", self.commit) or not re.fullmatch(
            r"[0-9a-f]{64}", self.sha256
        ):
            raise LogError("invalid_manifest")
        if (
            self.repository != "https://github.com/logpai/loghub"
            or self.source_path != "Apache/Apache_2k.log"
        ):
            raise LogError("unsupported_source")
        if not 0 < self.byte_count <= MAX_FILE_BYTES or not 0 < self.line_count <= 2000:
            raise LogError("invalid_manifest")
        if self.parser_version != "apache-error-v1" or self.timezone_name is not None:
            raise LogError("unsupported_parser")
        date.fromisoformat(self.retrieved_on)

    @property
    def dataset_id(self) -> UUID:
        return uuid5(NAMESPACE, self.slug)

    @property
    def file_id(self) -> UUID:
        return uuid5(self.dataset_id, self.sha256)

    @property
    def source_url(self) -> str:
        return f"https://raw.githubusercontent.com/logpai/loghub/{self.commit}/{self.source_path}"


@dataclass(frozen=True, slots=True)
class LogEvent:
    id: UUID
    file_id: UUID
    source_line: int
    source_time_text: str
    event_time_local: datetime
    original_level: str
    normalized_level: str
    message: str
    raw_line: str
    raw_line_sha256: bytes
    ingested_at: datetime
    event_time_utc: datetime | None = None


@dataclass(frozen=True, slots=True)
class ParsedLine:
    source_line: int
    digest: bytes
    event: LogEvent | None
    error_code: str | None = None
    size: int = 256


@dataclass
class IngestionRun:
    id: UUID
    file_id: UUID
    parser_version: str
    state: str
    processed: int
    inserted: int
    duplicates: int
    rejected: int
    last_committed_line: int
    started_at: datetime
    heartbeat_at: datetime
    lease_expires_at: datetime
    owner_token: UUID = field(repr=False)
    finished_at: datetime | None = None
    failure_code: str | None = None

    def public_state(self, now: datetime) -> str:
        return (
            "interrupted"
            if self.state == "running" and self.lease_expires_at <= now
            else self.state
        )


def require_owner(run: IngestionRun, token: UUID, now: datetime) -> None:
    if run.state != "running" or run.owner_token != token or run.lease_expires_at <= now:
        raise LogBusy("worker_lease_lost")


def advance(
    run: IngestionRun, token: UUID, batch: list[ParsedLine], inserted: int, now: datetime
) -> bool:
    """Validate before writes. False means this exact checkpoint already committed."""
    require_owner(run, token, now)
    if not batch or len(batch) > 500 or sum(item.size for item in batch) > MAX_BATCH_BYTES:
        raise LogError("invalid_batch")
    if [item.source_line for item in batch] != list(
        range(batch[0].source_line, batch[-1].source_line + 1)
    ):
        raise LogError("noncontiguous_batch")
    if batch[-1].source_line <= run.last_committed_line:
        return False
    if batch[0].source_line != run.last_committed_line + 1:
        raise LogError("checkpoint_conflict")
    rejected = sum(item.event is None for item in batch)
    if not 0 <= inserted <= len(batch) - rejected:
        raise LogError("invalid_batch_count")
    run.processed += len(batch)
    run.inserted += inserted
    run.duplicates += len(batch) - rejected - inserted
    run.rejected += rejected
    run.last_committed_line = batch[-1].source_line
    run.heartbeat_at = now
    run.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    return True


def parse_line(raw: bytes, file_id: UUID, number: int, *, oversized: bool = False) -> ParsedLine:
    digest = hashlib.sha256(raw).digest()
    if oversized or len(raw) > MAX_LINE_BYTES:
        return ParsedLine(number, digest, None, "line_too_long")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return ParsedLine(number, digest, None, "invalid_encoding")
    if "\x00" in text:
        return ParsedLine(number, digest, None, "nul_character")
    match = ENVELOPE.fullmatch(text)
    if match is None:
        return ParsedLine(number, digest, None, "invalid_envelope")
    source_time, level, message = match.groups()
    normalized = LEVELS.get(level.lower())
    if normalized is None:
        return ParsedLine(number, digest, None, "unsupported_level")
    try:
        weekday, month, day, time, year = source_time.split()
        if weekday not in "Mon Tue Wed Thu Fri Sat Sun".split():
            raise ValueError
        hour, minute, second = map(int, time.split(":"))
        local = datetime(int(year), MONTHS[month], int(day), hour, minute, second)
    except ValueError, KeyError:
        return ParsedLine(number, digest, None, "invalid_timestamp")
    event = LogEvent(
        uuid5(file_id, str(number)),
        file_id,
        number,
        source_time,
        local,
        level,
        normalized,
        message,
        text,
        digest,
        datetime.now(UTC),
    )
    return ParsedLine(number, digest, event, size=len(raw) * 2 + 512)


def records(stream: BinaryIO, file_id: UUID) -> Iterator[ParsedLine]:
    number = 0
    while chunk := stream.readline(MAX_LINE_BYTES + 2):
        number += 1
        oversized = len(chunk.removesuffix(b"\n").removesuffix(b"\r")) > MAX_LINE_BYTES
        if oversized:
            digest = hashlib.sha256(chunk)
            while not chunk.endswith(b"\n"):
                chunk = stream.readline(MAX_LINE_BYTES + 2)
                if not chunk:
                    break
                digest.update(chunk)
            yield ParsedLine(number, digest.digest(), None, "line_too_long")
        else:
            yield parse_line(chunk.removesuffix(b"\n").removesuffix(b"\r"), file_id, number)


def verify_source(path: Path, manifest: DatasetManifest) -> None:
    digest = hashlib.sha256()
    size = lines = 0
    last = b""
    try:
        with path.open("rb") as stream:
            while block := stream.read(64 * 1024):
                size += len(block)
                if size > manifest.byte_count or size > MAX_FILE_BYTES:
                    raise LogError("source_size_mismatch")
                digest.update(block)
                lines += block.count(b"\n")
                last = block[-1:]
    except OSError:
        raise LogError("source_unavailable") from None
    if last and last != b"\n":
        lines += 1
    if (
        size != manifest.byte_count
        or digest.hexdigest() != manifest.sha256
        or lines != manifest.line_count
    ):
        raise LogError("source_checksum_mismatch")
