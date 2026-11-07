import os

import pytest

from scripts.build_phase5_wheels import compiler_environment


@pytest.mark.skipif(os.name != "nt", reason="Windows compiler setup command")
def test_compiler_batch_path_with_spaces_executes_without_quote_escaping(tmp_path):
    directory = tmp_path / "Visual Studio tools"
    directory.mkdir()
    batch = directory / "vcvars64.bat"
    batch.write_bytes(b"@echo off\r\nset INCIDENTIQ_TEST_COMPILER=ready\r\n")
    environment = compiler_environment(batch)
    assert environment["INCIDENTIQ_TEST_COMPILER"] == "ready"
    assert environment["DISTUTILS_USE_SDK"] == "1"
