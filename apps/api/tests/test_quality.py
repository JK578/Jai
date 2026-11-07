import copy
import json

import pytest
from incidentiq.domain.quality import evaluate_report, review_template

from scripts.evaluate_investigations import BASELINE, FIXTURE, benchmark


@pytest.fixture
def cases():
    return {case["id"]: case for case in json.loads(FIXTURE.read_text())["cases"]}


def test_benchmark_has_positive_negative_and_unreviewed_cases():
    result = benchmark()
    assert result == json.loads(BASELINE.read_text())
    assert result["regression_passed"] and result["matched_expected"] == 14
    assert {row["quality_gate"] for row in result["results"]} == {"pass", "fail", "review_required"}


def test_valid_ids_do_not_establish_semantic_support(cases):
    case = cases["irrelevant_existing_citation"]
    result = evaluate_report(case["artifact"], case["review"])
    assert result["citation_validity"] == 1.0
    assert result["finding_support_rate"] == result["citation_support_precision"] == 0
    assert result["expected_fact_coverage"] == 0
    assert result["quality_gate"] == "fail"


def test_partial_citations_and_missing_facts_have_honest_denominators(cases):
    case = cases["partly_supported_citation_set"]
    result = evaluate_report(case["artifact"], case["review"])
    assert result["finding_support_rate"] == 1
    assert result["citation_support_precision"] == 0.5
    case = cases["missing_expected_fact"]
    assert evaluate_report(case["artifact"], case["review"])["expected_fact_coverage"] == 0.5
    case = cases["duplicate_references_do_not_inflate"]
    assert evaluate_report(case["artifact"], case["review"])["unique_citations"] == 1


@pytest.mark.parametrize("target", ["claim", "evidence", "question"])
def test_review_cannot_be_reused_after_artifact_changes(cases, target):
    case = copy.deepcopy(cases["supported_observation"])
    if target == "claim":
        case["artifact"]["report"]["findings"][0]["claim"] += " Changed."
    elif target == "evidence":
        case["artifact"]["evidence"][0]["text"] += " Changed."
    else:
        case["artifact"]["question"] += " Changed."
    with pytest.raises(ValueError, match="not_bound_to_artifact"):
        evaluate_report(case["artifact"], case["review"])


def test_template_does_not_silently_pass_unreviewed_fields(cases):
    artifact = cases["supported_observation"]["artifact"]
    template = review_template(artifact)
    assert template["summary_supported"] is None
    assert evaluate_report(artifact)["quality_gate"] == "review_required"
    assert evaluate_report(artifact)["finding_support_rate"] is None
    with pytest.raises(ValueError):
        evaluate_report(artifact, template)


def test_annotations_cannot_add_uncited_evidence_or_duplicate_fact_labels(cases):
    case = copy.deepcopy(cases["supported_observation"])
    case["review"]["findings"][0]["supported_by"] = [case["artifact"]["evidence"][1]["event_id"]]
    with pytest.raises(ValueError, match="support_annotation_invalid"):
        evaluate_report(case["artifact"], case["review"])
    case = copy.deepcopy(cases["supported_observation"])
    case["review"]["expected_facts"] *= 2
    with pytest.raises(ValueError, match="expected_facts_duplicate"):
        evaluate_report(case["artifact"], case["review"])


def test_unknown_citations_fail_before_semantic_scoring(cases):
    case = cases["unknown_citation"]
    result = evaluate_report(case["artifact"], case["review"])
    assert result["structurally_valid"] is False
    assert result["finding_support_rate"] is None


@pytest.mark.parametrize(
    "change", ["blank_question", "duplicate_source", "boolean_line", "bad_hash"]
)
def test_malformed_source_artifacts_are_rejected(cases, change):
    artifact = copy.deepcopy(cases["supported_observation"]["artifact"])
    if change == "blank_question":
        artifact["question"] = "   "
    elif change == "duplicate_source":
        artifact["evidence"][1] = copy.deepcopy(artifact["evidence"][0])
    elif change == "boolean_line":
        artifact["evidence"][0]["source_line"] = True
    else:
        artifact["evidence"][0]["file_sha256"] = "invalid"
    with pytest.raises(ValueError):
        evaluate_report(artifact)


def test_cli_check_fails_unreviewed_without_printing_source(cases, tmp_path, monkeypatch, capsys):
    import sys

    from scripts.evaluate_investigations import main

    artifact = cases["supported_observation"]["artifact"]
    path = tmp_path / "report.json"
    path.write_text(json.dumps(artifact))
    monkeypatch.setattr(sys, "argv", ["evaluate", "score", "--report", str(path), "--check"])
    assert main() == 1
    output = capsys.readouterr().out
    assert json.loads(output)["quality_gate"] == "review_required"
    assert artifact["question"] not in output
