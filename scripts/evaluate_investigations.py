"""Offline quality benchmark and private report-bound reviewer workflow; no model calls."""

import argparse
import json
from pathlib import Path

from incidentiq.domain.quality import POLICY, canonical_hash, evaluate_report, review_template

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "apps/api/tests/fixtures/investigation_quality.json"
BASELINE = ROOT / "docs/phase8-quality-baseline.json"
PRIVATE = ROOT / ".cache/evaluations"


def read_json(path):
    if path.stat().st_size > 262144:
        raise ValueError("evaluation_file_too_large")
    return json.loads(path.read_text(encoding="utf-8"))


def benchmark():
    suite = read_json(FIXTURE)
    rows = []
    for case in suite["cases"]:
        result = evaluate_report(case["artifact"], case.get("review"))
        rows.append({"case": case["id"], "expected_gate": case["expected_gate"], **result})
    matched = sum(row["quality_gate"] == row["expected_gate"] for row in rows)
    return {
        "policy": POLICY,
        "fixture_sha256": canonical_hash(suite),
        "scope": "Annotated synthetic scorer regression; not live model accuracy.",
        "cases": len(rows),
        "matched_expected": matched,
        "regression_passed": matched == len(rows),
        "paid_model_calls": 0,
        "results": rows,
    }


def save_private(name, value):
    PRIVATE.mkdir(parents=True, exist_ok=True)
    path = PRIVATE / name
    # Preserve existing reviews/templates rather than replacing operator annotations.
    with path.open("x", encoding="utf-8") as output:
        output.write(json.dumps(value, indent=2) + "\n")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("benchmark", "template", "score"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.operation == "benchmark":
        result = benchmark()
        matches = canonical_hash(result) == canonical_hash(read_json(BASELINE))
        print(json.dumps({"baseline_matches": matches, **result}, indent=2))
        return 0 if result["regression_passed"] and matches else 1
    if args.report is None:
        parser.error("--report is required")
    payload = read_json(args.report)
    if args.operation == "template":
        template = review_template(payload)
        path = save_private(template["artifact_sha256"] + ".review.json", template)
        print(
            json.dumps(
                {
                    "review_path": str(path),
                    "status": "human_review_required",
                    "artifact_sha256": template["artifact_sha256"],
                }
            )
        )
        return 0
    result = evaluate_report(payload, read_json(args.review) if args.review else None)
    print(json.dumps(result, indent=2))
    return 1 if args.check and result["quality_gate"] != "pass" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"quality_evaluation_failed: {type(error).__name__}; input content suppressed")
        raise SystemExit(1) from None
