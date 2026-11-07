from pathlib import Path

import yaml


def test_ci_workflow_is_yaml_and_run_steps_are_strings():
    path = Path(__file__).resolve().parents[3] / ".github/workflows/ci.yml"
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert set(workflow["jobs"]) == {"backend", "frontend"}
    commands = [
        step["run"] for job in workflow["jobs"].values() for step in job["steps"] if "run" in step
    ]
    assert commands and all(isinstance(command, str) for command in commands)
    assert sum("--only-binary=:all:" in command for command in commands) == 2
