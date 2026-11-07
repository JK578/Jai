import json
import sqlite3
from contextlib import contextmanager
from unittest.mock import Mock
from uuid import UUID

import pytest
from incidentiq.application.investigations import build_investigation
from incidentiq.application.model_gateway import ModelPricing
from incidentiq.domain.investigations import InvestigationFailure, report_digest, validate_report
from incidentiq.infrastructure.investigation_checkpoint import CallJournal, publish_local, run_lock
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from scripts.investigate import MockReportProvider, mock_retrieve

FILE = str(UUID(int=100))
CONFIG = {"configurable": {"thread_id": "test-run"}, "recursion_limit": 20}


def initial(budget=20000):
    return {
        "run_id": "test-run",
        "question": "Investigate initialization",
        "file_id": FILE,
        "mode": "mock",
        "configuration": "test-v1",
        "budget": budget,
        "remaining": budget,
        "attempt": 0,
        "status": "running",
    }


def valid(request):
    return MockReportProvider().generate(request).text


@contextmanager
def workflow(path, retrieve=None, generate=None, publish=None):
    with sqlite3.connect(path / "checkpoint.sqlite", check_same_thread=False) as connection:
        graph = build_investigation(
            retrieve or mock_retrieve,
            generate or valid,
            CallJournal(path / "calls.sqlite"),
            publish or Mock(),
            SqliteSaver(connection),
            ModelPricing(1, 2),
        )
        yield graph


def test_pauses_with_evidence_and_exact_report_hash(tmp_path):
    publisher = Mock()
    with workflow(tmp_path, publish=publisher) as graph:
        result = graph.invoke(initial(), CONFIG)
        state = graph.get_state(CONFIG)
        assert result["__interrupt__"]
        assert state.values["status"] == "awaiting_approval"
        assert state.values["report_sha256"] == report_digest(state.values)
        assert state.values["remaining"] < 20000
        publisher.assert_not_called()


@pytest.mark.parametrize("approved", [True, False])
def test_reopen_checkpoint_then_decide_without_repeating_calls(tmp_path, approved):
    retrieve, generate, publisher = Mock(side_effect=mock_retrieve), Mock(side_effect=valid), Mock()
    with workflow(tmp_path, retrieve, generate, publisher) as graph:
        graph.invoke(initial(), CONFIG)
        digest = graph.get_state(CONFIG).values["report_sha256"]
    with workflow(tmp_path, retrieve, generate, publisher) as graph:
        result = graph.invoke(
            Command(resume={"approved": approved, "report_sha256": digest}), CONFIG
        )
        assert result["status"] == ("completed" if approved else "rejected")
        assert retrieve.call_count == generate.call_count == 1
        assert publisher.call_count == int(approved)


@pytest.mark.parametrize(
    "decision",
    [
        True,
        {"approved": "true", "report_sha256": "x"},
        {"approved": True, "report_sha256": "wrong"},
        {"approved": True},
    ],
)
def test_approval_cannot_be_forged_or_coerced(tmp_path, decision):
    publisher = Mock()
    with workflow(tmp_path, publish=publisher) as graph:
        graph.invoke(initial(), CONFIG)
        with pytest.raises(InvestigationFailure, match="approval_invalid"):
            graph.invoke(Command(resume=decision), CONFIG)
        publisher.assert_not_called()


def test_failure_is_safe_and_explicit_retry_preserves_retrieved_evidence(tmp_path):
    retrieve = Mock(side_effect=mock_retrieve)
    generate = Mock(side_effect=RuntimeError("private key and error body"))
    with workflow(tmp_path, retrieve=retrieve, generate=generate) as graph:
        result = graph.invoke(initial(), CONFIG)
        assert result["status"] == "failed" and result["failed_stage"] == "draft"
        assert "private" not in result["error_code"]
        spent = result["remaining"]
    generate.side_effect = valid
    with workflow(tmp_path, retrieve=retrieve, generate=generate) as graph:
        result = graph.invoke(
            Command(update={"attempt": 1, "status": "running"}, goto="reserve_model"), CONFIG
        )
        assert result["status"] == "awaiting_approval"
        assert retrieve.call_count == 1 and generate.call_count == 2
        assert result["remaining"] < spent


def test_no_evidence_skips_generation_and_approval(tmp_path):
    generate, publisher = Mock(), Mock()
    with workflow(tmp_path, retrieve=lambda *_: [], generate=generate, publish=publisher) as graph:
        result = graph.invoke(initial(), CONFIG)
        assert result["status"] == "no_evidence"
        generate.assert_not_called()
        publisher.assert_not_called()


def test_budget_prevents_paid_work(tmp_path):
    retrieve, generate = Mock(), Mock()
    with workflow(tmp_path, retrieve=retrieve, generate=generate) as graph:
        result = graph.invoke(initial(budget=1), CONFIG)
        assert result["error_code"] == "investigation_budget_exceeded"
        retrieve.assert_not_called()
        generate.assert_not_called()


def test_uncertain_call_is_not_repeated_after_process_loss(tmp_path):
    journal = CallJournal(tmp_path / "calls.sqlite")
    with sqlite3.connect(journal.path) as connection:
        connection.execute("INSERT INTO calls VALUES ('retrieve', 0, 'pending', NULL)")
    retrieve = Mock()
    with workflow(tmp_path, retrieve=retrieve) as graph:
        result = graph.invoke(initial(), CONFIG)
        assert result["error_code"] == "investigation_call_uncertain"
        retrieve.assert_not_called()


def test_completed_journal_result_reused_and_failures_redacted(tmp_path):
    journal = CallJournal(tmp_path / "calls.sqlite")
    call = Mock(return_value=["safe result"])
    assert journal.call("retrieve", 0, call) == ["safe result"]
    assert journal.call("retrieve", 0, call) == ["safe result"]
    assert call.call_count == 1
    with pytest.raises(InvestigationFailure, match="^investigation_draft_failed$"):
        journal.call("draft", 0, Mock(side_effect=RuntimeError("secret")))


@pytest.mark.parametrize(
    "alter",
    [
        lambda r: r.update(action="restart_service"),
        lambda r: r["findings"][0].update(evidence_ids=[str(UUID(int=999))]),
        lambda r: r.update(uncertainties=[]),
        lambda r: r.update(findings=[]),
        lambda r: r.update(summary="x" * 1501),
    ],
)
def test_invalid_reports_and_unknown_tools_never_reach_approval(tmp_path, alter):
    def invalid(request):
        report = json.loads(valid(request))
        alter(report)
        return json.dumps(report)

    publisher = Mock()
    with workflow(tmp_path, generate=invalid, publish=publisher) as graph:
        result = graph.invoke(initial(), CONFIG)
        assert (
            result["status"] == "failed" and result["error_code"] == "investigation_report_invalid"
        )
        publisher.assert_not_called()


def test_wrong_file_evidence_rejected(tmp_path):
    def retrieve(*args):
        evidence = mock_retrieve(*args)
        evidence[0]["file_id"] = str(UUID(int=101))
        return evidence

    with workflow(tmp_path, retrieve=retrieve) as graph:
        result = graph.invoke(initial(), CONFIG)
        assert result["error_code"] == "investigation_evidence_invalid"


def test_publication_idempotent_and_conflicting_report_not_overwritten(tmp_path):
    report = {"report_sha256": "a", "report": {"summary": "approved"}}
    publish_local(tmp_path, report)
    publish_local(tmp_path, report)
    with pytest.raises(InvestigationFailure, match="report_conflict"):
        publish_local(tmp_path, {**report, "report_sha256": "different"})
    assert json.loads((tmp_path / "approved-report.json").read_text()) == report


def test_concurrent_run_lock_rejected_and_released(tmp_path):
    with run_lock(tmp_path):
        with pytest.raises(InvestigationFailure, match="run_busy"), run_lock(tmp_path):
            pass
    with run_lock(tmp_path):
        pass


def test_context_changes_invalidate_approval_digest():
    state = {**initial(), "evidence": [], "report": {"summary": "first"}}
    first = report_digest(state)
    assert report_digest({**state, "question": "changed"}) != first
    with pytest.raises(InvestigationFailure):
        validate_report("not JSON", [])


def test_resume_after_publication_acknowledgement_loss_is_idempotent(tmp_path):
    retrieve, generate = Mock(side_effect=mock_retrieve), Mock(side_effect=valid)

    def publish_then_fail(report):
        publish_local(tmp_path, report)
        raise RuntimeError("sensitive disk failure")

    with workflow(tmp_path, retrieve, generate, publish_then_fail) as graph:
        graph.invoke(initial(), CONFIG)
        digest = graph.get_state(CONFIG).values["report_sha256"]
        with pytest.raises(
            InvestigationFailure, match="investigation_publication_failed"
        ) as failure:
            graph.invoke(Command(resume={"approved": True, "report_sha256": digest}), CONFIG)
        assert failure.value.args == ("investigation_publication_failed",)
    with workflow(
        tmp_path, retrieve, generate, lambda report: publish_local(tmp_path, report)
    ) as graph:
        result = graph.invoke(None, CONFIG)
        assert result["status"] == "completed"
        assert retrieve.call_count == generate.call_count == 1
        assert (
            json.loads((tmp_path / "approved-report.json").read_text())["report_sha256"] == digest
        )
