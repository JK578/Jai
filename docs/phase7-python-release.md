# Isolated Python release environments

Verified 2026-11-07: 61 pinned distributions installed offline into two independent
environments. The tampered candidate was rejected before execution; restoring the
baseline preserved authenticated reads, the paused checkpoint, report digest and
seeded budget reservation. Unauthorized reads and approvals remained denied.
See [the executed receipt](python-rollback-validation.json). No paid model calls or
schema changes occurred. The backend suite passes 215 offline tests.

The Python release tooling installs the exact `requirements-dev.lock.txt` pins into a
fresh virtual environment, without using the development environment's site-packages.
Installation is offline and requires a SHA256 for every wheel. The host Python 3.15
interpreter/standard library remain shared; the virtual environments stay at their
original paths and are not portable archives.

## Prepare trusted wheels

For the current reviewed lock on Windows x64/Python 3.15:

```powershell
.venv/Scripts/python.exe -m pip download --only-binary=:all: --find-links .cache/phase5-wheels --dest .cache/releases/python-wheelhouse -r apps/api/requirements-dev.lock.txt
.venv/Scripts/python.exe -m scripts.python_release seal
```

The first command downloads pinned distributions over the configured package transport;
the locally built PyYAML/zstandard wheels are reused. The second command checks each
wheel's metadata against all exact pins and writes a hashed requirements file and
manifest. Keep its printed `wheelhouse_sha256` separately as the trusted expected digest.
Hashes protect changes after staging; they do not establish upstream package authorship.
A previously sealed cache is verified rather than silently resealed after a change.

## Build offline

```powershell
.venv/Scripts/python.exe -m scripts.python_release build --wheelhouse-sha256 <trusted-digest>
```

This verifies the wheel cache, creates a new environment under ignored `.cache/releases/python/`,
installs with `--no-index --require-hashes --only-binary`, runs `pip check`, compares all
installed versions with the lock, and verifies that dependency imports resolve inside
the new environment. Pip is the bootstrap tool and is recorded separately from the
application pins. No editable application installation is needed.

The command prints the Python executable, environment path and manifest hash. Environment
files are hashed after installation; missing, changed or extra files fail verification.
Do not overwrite a known-good environment during an upgrade. Keep source, credentials,
checkpoints and the daily budget ledger outside dependency environments.

For everyday local use, the printed Python executable can run the workspace API from
the repository root using `-m uvicorn incidentiq.main:app --app-dir apps/api/src
--host 127.0.0.1 --port 8000 --no-access-log`. The existing ignored `apps/api/api.env`
continues to supply server credentials. Do not pass those credentials in shell arguments.

## Rollback drill

```powershell
.venv/Scripts/python.exe -m scripts.validate_python_rollback
```

The drill builds two separate environments from the same locked wheel set. It runs a
verified source snapshot in environment A on port 8004, deliberately alters a dependency
in B, rejects B before execution, then restarts A. It uses a separate one-hour registry
and private data directory, preserving your normal login file and running application.
The investigation stays paused for human review; the digest and a seeded daily-budget
reservation must survive restoration. Unauthorized requests and approval attempts must
remain denied. No schema changes, incident writes or paid model calls are performed.

This checks recovery from dependency-file corruption using the current dependency
versions. It does not test compatibility between different dependency versions, a host
Python/Node downgrade, database downgrade or a historical production deployment.
