"""Evidence-bounded reports and explicit approval contracts; no workflow dependencies."""

import hashlib
import json
from uuid import UUID


class InvestigationFailure(Exception):
    """Fixed safe code, never provider or tool exception text."""


def validate_report(raw: str, evidence: list[dict]) -> dict:
    try:
        report = json.loads(raw)
        if set(report) != {"summary", "findings", "uncertainties", "next_steps"}:
            raise ValueError
        if not isinstance(report["summary"], str) or not 1 <= len(report["summary"]) <= 1500:
            raise ValueError
        allowed = {item["event_id"] for item in evidence}
        findings = report["findings"]
        if not isinstance(findings, list) or not 1 <= len(findings) <= 5:
            raise ValueError
        for finding in findings:
            if set(finding) != {"claim", "evidence_ids"}:
                raise ValueError
            if not isinstance(finding["claim"], str) or not 1 <= len(finding["claim"]) <= 600:
                raise ValueError
            refs = finding["evidence_ids"]
            if not isinstance(refs, list) or not 1 <= len(refs) <= 5:
                raise ValueError
            if any(str(UUID(ref)) != ref or ref not in allowed for ref in refs):
                raise ValueError
        for key in ("uncertainties", "next_steps"):
            values = report[key]
            if not isinstance(values, list) or not 1 <= len(values) <= 5:
                raise ValueError
            if any(not isinstance(value, str) or not 1 <= len(value) <= 400 for value in values):
                raise ValueError
        return report
    except ValueError, TypeError, KeyError, AttributeError:
        raise InvestigationFailure("investigation_report_invalid") from None


def artifact(state: dict) -> dict:
    return {key: state[key] for key in ("run_id", "question", "file_id", "evidence", "report")}


def report_digest(state: dict) -> str:
    return hashlib.sha256(json.dumps(artifact(state), sort_keys=True).encode()).hexdigest()


def validate_decision(decision, digest: str) -> bool:
    if (
        not isinstance(decision, dict)
        or set(decision) != {"approved", "report_sha256"}
        or type(decision["approved"]) is not bool
        or decision["report_sha256"] != digest
    ):
        raise InvestigationFailure("investigation_approval_invalid")
    return decision["approved"]
