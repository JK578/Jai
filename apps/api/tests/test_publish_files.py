import json

from scripts import check_publish_files


def test_publish_check_reports_names_without_exposing_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(check_publish_files, "ROOT", tmp_path)
    private = tmp_path / ".cache/access"
    private.mkdir(parents=True)
    token = "S" * 48
    (private / "login.txt").write_text(token)
    files = {
        "source.py": token.encode(),
        "api.env": b"private",
        "github.txt": ("ghp_" + "a" * 40).encode(),
    }

    def git(*args):
        return (
            b"\0".join(name.encode() for name in files)
            if args[0] == "ls-files"
            else files[args[1][1:]]
        )

    monkeypatch.setattr(check_publish_files, "git", git)
    result = check_publish_files.check()
    assert {row["path"] for row in result["failures"]} == set(files)
    assert token not in json.dumps(result)
    assert "ghp_" + "a" * 40 not in json.dumps(result)


def test_publish_check_accepts_public_defaults_and_source(tmp_path, monkeypatch):
    monkeypatch.setattr(check_publish_files, "ROOT", tmp_path)
    files = {"apps/api/.env.example": b"# OPENAI_API_KEY=", "source.py": b"print('ready')"}

    def git(*args):
        return (
            b"\0".join(name.encode() for name in files)
            if args[0] == "ls-files"
            else files[args[1][1:]]
        )

    monkeypatch.setattr(check_publish_files, "git", git)
    assert check_publish_files.check() == {"indexed_files_checked": 2, "failures": []}
