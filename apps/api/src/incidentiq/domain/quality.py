"""Report-bound reviewer metrics; citation membership is not semantic entailment."""

import hashlib
import json
from uuid import UUID

from incidentiq.domain.investigations import InvestigationFailure, validate_report
from incidentiq.domain.retrieval import Evidence

POLICY = "investigation-review-v1"


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def report_artifact(payload):
    question, evidence, report = (payload[key] for key in ("question", "evidence", "report"))
    if (
        not isinstance(question, str)
        or not question.strip()
        or not 1 <= len(question.encode()) <= 800
    ):
        raise ValueError("quality_question_invalid")
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 5:
        raise ValueError("quality_evidence_invalid")
    identities = set()
    fields = {
        "event_id",
        "file_id",
        "source_line",
        "source_path",
        "source_commit",
        "file_sha256",
        "text",
    }
    for row in evidence:
        if set(row) != fields or type(row["source_line"]) is not int:
            raise ValueError("quality_evidence_invalid")
        event_id, file_id = UUID(row["event_id"]), UUID(row["file_id"])
        if (
            str(event_id) != row["event_id"]
            or str(file_id) != row["file_id"]
            or event_id in identities
        ):
            raise ValueError("quality_evidence_invalid")
        Evidence(event_id, file_id, **{key: row[key] for key in fields - {"event_id", "file_id"}})
        identities.add(event_id)
    return {"question": question, "evidence": evidence, "report": report}


def review_template(payload):
    artifact = report_artifact(payload)
    validate_report(json.dumps(artifact["report"]), artifact["evidence"])
    return {
        "artifact_sha256": canonical_hash(artifact),
        "reviewer": {"kind": "human", "name": ""},
        "findings": [
            {"index": i, "label": "unreviewed", "supported_by": []}
            for i in range(len(artifact["report"]["findings"]))
        ],
        "expected_facts": [],
        "summary_supported": None,
        "uncertainty_adequate": None,
        "unsafe_suggestions": None,
    }


def evaluate_report(payload, review=None):
    artifact = report_artifact(payload)
    fingerprint = canonical_hash(artifact)
    result = {
        "policy": POLICY,
        "artifact_sha256": fingerprint,
        "structurally_valid": False,
        "citation_validity": None,
        "finding_support_rate": None,
        "citation_support_precision": None,
        "expected_fact_coverage": None,
        "quality_gate": "fail",
        "reasons": [],
    }
    try:
        report = validate_report(json.dumps(artifact["report"]), artifact["evidence"])
    except InvestigationFailure:
        return {**result, "reasons": ["invalid_report"]}
    links = {
        (i, identity)
        for i, finding in enumerate(report["findings"])
        for identity in finding["evidence_ids"]
    }
    result.update(structurally_valid=True, citation_validity=1.0, unique_citations=len(links))
    if review is None:
        return {**result, "quality_gate": "review_required", "reasons": ["review_required"]}
    fields = {
        "artifact_sha256",
        "reviewer",
        "findings",
        "expected_facts",
        "summary_supported",
        "uncertainty_adequate",
        "unsafe_suggestions",
    }
    if (
        not isinstance(review, dict)
        or set(review) != fields
        or review["artifact_sha256"] != fingerprint
    ):
        raise ValueError("quality_review_not_bound_to_artifact")
    reviewer = review["reviewer"]
    if (
        not isinstance(reviewer, dict)
        or set(reviewer) != {"kind", "name"}
        or reviewer["kind"] not in {"human", "fixture"}
        or not isinstance(reviewer["name"], str)
        or not 1 <= len(reviewer["name"].strip()) <= 80
    ):
        raise ValueError("quality_reviewer_invalid")
    for flag in ("summary_supported", "uncertainty_adequate", "unsafe_suggestions"):
        if type(review[flag]) is not bool:
            raise ValueError("quality_review_incomplete")
    labels = review["findings"]
    if not isinstance(labels, list) or len(labels) != len(report["findings"]):
        raise ValueError("quality_finding_labels_incomplete")
    supported, approved_links, seen = set(), set(), set()
    counts = {"supported": 0, "unsupported": 0, "uncertain": 0}
    for label in labels:
        if not isinstance(label, dict) or set(label) != {"index", "label", "supported_by"}:
            raise ValueError("quality_finding_label_invalid")
        index, verdict, refs = label["index"], label["label"], label["supported_by"]
        if (
            type(index) is not int
            or index not in range(len(labels))
            or index in seen
            or verdict not in counts
            or not isinstance(refs, list)
            or len(refs) > 5
            or any(not isinstance(ref, str) for ref in refs)
            or len(set(refs)) != len(refs)
        ):
            raise ValueError("quality_finding_label_invalid")
        if any((index, ref) not in links for ref in refs) or bool(refs) != (verdict == "supported"):
            raise ValueError("quality_support_annotation_invalid")
        seen.add(index)
        counts[verdict] += 1
        if verdict == "supported":
            supported.add(index)
            approved_links.update((index, ref) for ref in refs)
    facts = review["expected_facts"]
    if not isinstance(facts, list) or not 1 <= len(facts) <= 20:
        raise ValueError("quality_expected_facts_invalid")
    covered, names = 0, set()
    for fact in facts:
        if (
            not isinstance(fact, dict)
            or set(fact) != {"fact", "covered_by"}
            or not isinstance(fact["fact"], str)
            or not 1 <= len(fact["fact"].strip()) <= 300
            or not isinstance(fact["covered_by"], list)
            or len(fact["covered_by"]) > 5
            or any(type(i) is not int or i not in seen for i in fact["covered_by"])
        ):
            raise ValueError("quality_expected_facts_invalid")
        name = fact["fact"].strip().casefold()
        if name in names or len(set(fact["covered_by"])) != len(fact["covered_by"]):
            raise ValueError("quality_expected_facts_duplicate")
        names.add(name)
        covered += bool(supported.intersection(fact["covered_by"]))
    result.update(
        finding_support_rate=len(supported) / len(labels),
        citation_support_precision=len(approved_links) / len(links),
        expected_fact_coverage=covered / len(facts),
        finding_labels=counts,
        review_sha256=canonical_hash(review),
        reviewer_kind=reviewer["kind"],
    )
    checks = {
        "unsupported_findings": counts["unsupported"] == 0,
        "unresolved_findings": counts["uncertain"] == 0,
        "unbacked_citations": len(approved_links) == len(links),
        "missing_expected_facts": covered / len(facts) >= 0.8,
        "summary_unsupported": review["summary_supported"],
        "uncertainty_inadequate": review["uncertainty_adequate"],
        "unsafe_suggestions": not review["unsafe_suggestions"],
    }
    result["reasons"] = [name for name, passed in checks.items() if not passed]
    result["quality_gate"] = "fail" if result["reasons"] else "pass"
    return result
