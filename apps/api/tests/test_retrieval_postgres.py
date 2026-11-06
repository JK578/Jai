import hashlib
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from incidentiq.domain.retrieval import Evidence, RetrievalFailure
from incidentiq.infrastructure.retrieval_postgres import (
    SEARCH,
    PostgresRetrievalIndex,
    safe_retrieval,
)
from sqlalchemy.exc import SQLAlchemyError

FILE = UUID(int=100)
ITEM = Evidence(UUID(int=1), FILE, 1, "synthetic.log", "a" * 40, "b" * 64, "restart server")
VECTOR = (1.0,) + (0.0,) * 511


def row():
    return {
        "event_id": ITEM.event_id,
        "file_id": FILE,
        "source_line": 1,
        "expected_line_count": 1,
        "source_path": ITEM.source_path,
        "source_commit": ITEM.source_commit,
        "file_sha256": ITEM.file_sha256,
        "content": ITEM.text,
        "source_content": ITEM.text,
        "content_sha256": hashlib.sha256(ITEM.text.encode()).hexdigest(),
        "model": "fixture-512",
        "dimensions": 512,
        "keyword_rank": 1,
        "vector_rank": 1,
    }


def setup(write=False):
    factory = MagicMock()
    session = (
        factory.begin.return_value.__enter__.return_value
        if write
        else factory.return_value.__enter__.return_value
    )
    session.scalar.return_value = 10000000
    session.execute.return_value.mappings.return_value.all.return_value = [row()]
    return PostgresRetrievalIndex(factory), factory, session


def test_publish_is_transactional_and_binds_vectors():
    index, factory, session = setup(write=True)
    index.replace_file(FILE, [ITEM], [VECTOR], "fixture-512", 512)
    factory.begin.return_value.__exit__.assert_called_once_with(None, None, None)
    calls = session.execute.call_args_list
    statements = [str(call.args[0]) for call in calls]
    assert any("FOR UPDATE" in sql for sql in statements)
    assert any("FOR SHARE" in sql for sql in statements)
    assert any("pg_advisory_xact_lock" in sql for sql in statements)
    assert sum("DELETE FROM" in sql for sql in statements) == 1
    insert = next(call for call in calls if "INSERT INTO" in str(call.args[0]))
    assert "extensions.vector(512)" in str(insert.args[0])
    assert ITEM.text not in str(insert.args[0])
    assert insert.args[1][0]["digest"] == hashlib.sha256(ITEM.text.encode()).hexdigest()
    assert not any("DELETE FROM incidentiq.log_" in sql for sql in statements)


def test_source_change_rejected_before_delete():
    index, factory, session = setup(write=True)
    session.execute.return_value.mappings.return_value.all.return_value = []
    with pytest.raises(RetrievalFailure, match="retrieval_source_changed"):
        index.replace_file(FILE, [ITEM], [VECTOR], "fixture-512", 512)
    assert not any("DELETE FROM" in str(call.args[0]) for call in session.execute.call_args_list)
    assert factory.begin.return_value.__exit__.call_args.args[0] is RetrievalFailure


def test_storage_headroom_prevents_mutation():
    index, _, session = setup(write=True)
    session.scalar.return_value = 401 * 1024**2
    with pytest.raises(RetrievalFailure, match="retrieval_storage_budget_exceeded"):
        index.replace_file(FILE, [ITEM], [VECTOR], "fixture-512", 512)
    assert not any("DELETE FROM" in str(call.args[0]) for call in session.execute.call_args_list)


def test_insert_failure_rolls_back_whole_replacement():
    index, factory, session = setup(write=True)
    result = session.execute.return_value

    def execute(statement, *args):
        if "INSERT INTO" in str(statement):
            raise SQLAlchemyError("secret SQL credentials")
        return result

    session.execute.side_effect = execute
    with pytest.raises(RetrievalFailure, match="^retrieval_storage_unavailable$"):
        index.replace_file(FILE, [ITEM], [VECTOR], "fixture-512", 512)
    assert factory.begin.return_value.__exit__.call_args.args[0] is SQLAlchemyError


def test_search_candidates_single_snapshot_parameterized_and_cited():
    index, _, session = setup()
    hits = index.search(FILE, "restart' OR 1=1 --", VECTOR, "fixture-512", 512, 5)
    assert hits[0].evidence == ITEM
    assert hits[0].keyword_rank == 1 and hits[0].vector_rank == 1
    statement, values = session.execute.call_args.args
    assert "OR 1=1" not in str(statement)
    assert values["file_id"] == FILE
    assert "MATERIALIZED" in SEARCH
    assert "plainto_tsquery('simple', :query)" in SEARCH
    assert "OPERATOR(extensions.<=>)" in SEARCH
    assert SEARCH.count("LIMIT 50") == 2


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("model", "other", "embedding_model_mismatch"),
        ("dimensions", 3, "embedding_model_mismatch"),
        ("source_content", "edited", "retrieval_source_changed"),
        ("content_sha256", "0" * 64, "retrieval_source_changed"),
    ],
)
def test_stale_or_mismatched_search_rejected(field, value, code):
    index, _, session = setup()
    invalid = row()
    invalid[field] = value
    session.execute.return_value.mappings.return_value.all.return_value = [invalid]
    with pytest.raises(RetrievalFailure, match=code):
        index.search(FILE, "restart", VECTOR, "fixture-512", 512, 5)


def test_scoped_index_deletion_only():
    index, _, session = setup(write=True)
    session.execute.return_value.rowcount = 1
    assert index.delete_file(FILE) == 1
    statement, values = session.execute.call_args.args
    assert str(statement) == "DELETE FROM incidentiq.retrieval_documents WHERE file_id=:file_id"
    assert values == {"file_id": FILE}


def test_load_file_provenance_and_missing_source():
    index, _, session = setup()
    assert index.load_file(FILE) == [ITEM]
    session.execute.return_value.mappings.return_value.all.return_value = []
    with pytest.raises(RetrievalFailure, match="retrieval_source_unavailable"):
        index.load_file(FILE)


def test_incomplete_source_is_not_indexed():
    index, _, session = setup()
    incomplete = {**row(), "expected_line_count": 2}
    session.execute.return_value.mappings.return_value.all.return_value = [incomplete]
    with pytest.raises(RetrievalFailure, match="retrieval_source_incomplete"):
        index.load_file(FILE)


@pytest.mark.parametrize("dimensions,limit", [(3, 5), (512, 0), (512, 21)])
def test_adapter_bounds(dimensions, limit):
    index, _, session = setup()
    with pytest.raises(ValueError):
        index.search(FILE, "restart", VECTOR, "fixture-512", dimensions, limit)
    session.execute.assert_not_called()


def test_database_failures_sanitized():
    @safe_retrieval
    def fail():
        raise SQLAlchemyError("private SQL")

    with pytest.raises(RetrievalFailure, match="^retrieval_storage_unavailable$"):
        fail()
