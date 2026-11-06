import hashlib
import io
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest
from incidentiq.domain.logs import LogError
from incidentiq.infrastructure.log_source import NoRedirect, fetch, manifest


def test_manifest_pins_approved_public_artifact_and_license():
    source = manifest()
    assert source.line_count == 2000 and source.byte_count == 171239
    assert source.commit in source.source_url
    assert source.license_name == "Loghub research/academic terms"
    assert source.timezone_name is None


def test_offline_download_publication_notice_and_checksum(tmp_path):
    payload = b"synthetic offline download\n"
    source = replace(
        manifest(),
        sha256=hashlib.sha256(payload).hexdigest(),
        byte_count=len(payload),
        line_count=1,
    )
    opener = MagicMock()
    opener.open.return_value = io.BytesIO(payload)
    with (
        patch("incidentiq.infrastructure.log_source.manifest", return_value=source),
        patch(
            "incidentiq.infrastructure.log_source.urllib.request.build_opener", return_value=opener
        ),
    ):
        result = fetch(tmp_path)
    assert result.read_bytes() == payload
    assert "research" in (tmp_path / "LOGHUB-LICENSE.txt").read_text(encoding="utf-8")
    assert set(p.name for p in tmp_path.iterdir()) == {result.name, "LOGHUB-LICENSE.txt"}
    opener.open.assert_called_once_with(source.source_url, timeout=15)


def test_download_failure_keeps_existing_cache_and_cleans_partial(tmp_path):
    source = manifest()
    existing = tmp_path / f"{source.sha256}.log"
    existing.write_bytes(b"existing synthetic marker")
    opener = MagicMock()
    opener.open.return_value = io.BytesIO(b"invalid synthetic download")
    with patch(
        "incidentiq.infrastructure.log_source.urllib.request.build_opener", return_value=opener
    ):
        with pytest.raises(LogError, match="source_checksum_mismatch"):
            fetch(tmp_path)
    assert existing.read_bytes() == b"existing synthetic marker"
    assert len(list(tmp_path.iterdir())) == 1


def test_redirect_to_another_source_is_rejected():
    with pytest.raises(LogError, match="source_redirect_rejected"):
        NoRedirect().redirect_request(None, None, 302, "redirect", None, "https://example.com")
