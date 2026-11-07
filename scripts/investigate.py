"""Run, inspect and resume a checkpointed investigation; mock mode is offline."""

import argparse
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import UUID, uuid4

from incidentiq.application.investigations import INSTRUCTIONS, build_investigation
from incidentiq.application.model_gateway import ModelGateway, ModelPricing, ModelResult
from incidentiq.application.retrieval import RetrievalService
from incidentiq.config import load_settings
from incidentiq.domain.investigations import InvestigationFailure, validate_decision
from incidentiq.infrastructure.investigation_checkpoint import CallJournal, publish_local, run_lock
from incidentiq.infrastructure.log_source import manifest
from incidentiq.infrastructure.model_provider import OpenAIModelProvider
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import SecretStr

from scripts.retrieval_cli import open_index, provider

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / ".cache/investigations"


class MockReportProvider:
    def generate(self, request):
        evidence = json.loads(request.text)["evidence"]
        report = {
            "summary": "Mock investigation; no model inference performed.",
            "findings": [
                {
                    "claim": "A source event was retrieved; no root cause is established.",
                    "evidence_ids": [evidence[0]["event_id"]],
                }
            ],
            "uncertainties": ["Synthetic evidence does not establish a production cause."],
            "next_steps": ["Review source evidence with the incident owner."],
        }
        return ModelResult(json.dumps(report), 1, 128)


def mock_retrieve(question, file_id):
    return [
        {
            "event_id": str(UUID(int=1)),
            "file_id": file_id,
            "source_line": 1,
            "source_path": "synthetic/investigation.log",
            "source_commit": "0" * 40,
            "file_sha256": hashlib.sha256(b"Synthetic worker initialization evidence").hexdigest(),
            "text": "Synthetic worker initialization evidence",
        }
    ]


def live_retrieve(question, file_id):
    engine, index = open_index()
    try:
        retrieval = RetrievalService(provider(len(question.encode())), index)
        hits = retrieval.search(UUID(file_id), question, limit=5)
        return [
            {
                "event_id": str(h.evidence.event_id),
                "file_id": str(h.evidence.file_id),
                "source_line": h.evidence.source_line,
                "source_path": h.evidence.source_path,
                "source_commit": h.evidence.source_commit,
                "file_sha256": h.evidence.file_sha256,
                "text": h.evidence.text.encode()[:1200].decode("utf-8", errors="ignore"),
            }
            for h in hits
        ]
    finally:
        engine.dispose()


def execute(args, *, run_root=None, retrieve=None):
    # Disable automatic cloud tracing in this private, local workflow process.
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    load_settings()
    runs = run_root or RUNS
    if args.operation == "start":
        if not args.question.strip() or len(args.question.encode()) > 800:
            raise InvestigationFailure("investigation_question_invalid")
        if not 1000 <= args.budget_microusd <= 100000:
            raise InvestigationFailure("investigation_budget_invalid")
        if runs.exists() and len(list(runs.glob("*/checkpoints.sqlite"))) >= 32:
            raise InvestigationFailure("investigation_retention_review_required")
        run_id = str(uuid4())
    else:
        run_id = str(UUID(args.run_id))
        if not (runs / run_id / "checkpoints.sqlite").exists():
            raise InvestigationFailure("investigation_not_found")
    directory = runs / run_id
    with (
        run_lock(directory),
        closing(
            sqlite3.connect(directory / "checkpoints.sqlite", check_same_thread=False)
        ) as connection,
    ):
        saver = SqliteSaver(connection)
        config = {"configurable": {"thread_id": run_id}, "recursion_limit": 20, "callbacks": []}
        prior = saver.get_tuple(config)
        saved = prior.checkpoint["channel_values"] if prior else {}
        mode = args.provider if args.operation == "start" else saved["mode"]
        pricing = ModelPricing(1, 2)
        adapter = MockReportProvider()
        if mode == "openai":
            pricing = ModelPricing(
                int(os.environ["INCIDENTIQ_MODEL_INPUT_MICROUSD"]),
                int(os.environ["INCIDENTIQ_MODEL_OUTPUT_MICROUSD"]),
            )
            # Status/review do not require a network call; adapter construction never connects.
            adapter = OpenAIModelProvider(
                SecretStr(os.environ.get("OPENAI_API_KEY", "")),
                os.environ["INCIDENTIQ_MODEL"],
                reasoning_effort="none",
            )
        identity = hashlib.sha256(
            json.dumps(
                [
                    mode,
                    os.getenv("INCIDENTIQ_MODEL") if mode == "openai" else "mock",
                    pricing.input_microusd,
                    pricing.output_microusd,
                    INSTRUCTIONS,
                    1,
                ]
            ).encode()
        ).hexdigest()
        if saved and saved["configuration"] != identity:
            raise InvestigationFailure("investigation_configuration_changed")

        def generate(request):
            allowance = pricing.cost(request.input_allowance, request.max_output_tokens)
            return ModelGateway(adapter, pricing, allowance).generate(request).text

        graph = build_investigation(
            (retrieve or live_retrieve) if mode == "openai" else mock_retrieve,
            generate,
            CallJournal(directory / "calls.sqlite"),
            lambda report: publish_local(directory, report),
            saver,
            pricing,
        )
        if args.operation == "start":
            graph.invoke(
                {
                    "run_id": run_id,
                    "question": args.question,
                    "file_id": str(manifest().file_id),
                    "mode": mode,
                    "configuration": identity,
                    "budget": args.budget_microusd,
                    "remaining": args.budget_microusd,
                    "attempt": 0,
                    "status": "running",
                },
                config,
            )
        elif args.operation == "resume":
            snapshot = graph.get_state(config)
            if snapshot.values.get("status") == "awaiting_approval":
                raise InvestigationFailure("investigation_approval_required")
            if not snapshot.next:
                raise InvestigationFailure("investigation_not_resumable")
            graph.invoke(None, config)
        elif args.operation in ("approve", "reject"):
            snapshot = graph.get_state(config)
            if snapshot.values.get("status") != "awaiting_approval" or not snapshot.next:
                raise InvestigationFailure("investigation_not_awaiting_approval")
            validate_decision(
                {"approved": args.operation == "approve", "report_sha256": args.report_sha256},
                snapshot.values["report_sha256"],
            )
            graph.invoke(
                Command(
                    resume={
                        "approved": args.operation == "approve",
                        "report_sha256": args.report_sha256,
                    }
                ),
                config,
            )
        elif args.operation == "retry":
            if saved.get("status") != "failed" or saved["attempt"] >= 1:
                raise InvestigationFailure("investigation_retry_not_allowed")
            target = "reserve_retrieval" if saved["failed_stage"] == "retrieve" else "reserve_model"
            graph.invoke(
                Command(
                    update={"attempt": saved["attempt"] + 1, "status": "running", "error_code": ""},
                    goto=target,
                ),
                config,
            )
        values = graph.get_state(config).values
        return {
            "provider": mode,
            "question": values["question"],
            "attempt": values["attempt"],
            "run_id": run_id,
            "status": values["status"],
            "remaining_conservative_microusd": values["remaining"],
            "report_sha256": values.get("report_sha256"),
            "error_code": values.get("error_code"),
            "report": values.get("report"),
            "evidence": values.get("evidence", []),
            "published": (directory / "approved-report.json").exists(),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation", choices=("start", "status", "resume", "approve", "reject", "retry")
    )
    parser.add_argument("--provider", choices=("mock", "openai"), default="mock")
    parser.add_argument("--question", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--report-sha256", default="")
    parser.add_argument("--budget-microusd", type=int, default=20000)
    args = parser.parse_args()
    try:
        print(json.dumps(execute(args), indent=2))
    except InvestigationFailure as error:
        print(str(error))
        raise SystemExit(1) from None
    except Exception:
        print("investigation_unavailable; details suppressed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
