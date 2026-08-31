# sanka-sdk

Python SDK for Sanka's hosted API and local migration lifecycle.

This package is generated from Sanka's OpenAPI spec using Fern, then packaged locally for `uv` and PyPI.

## Install

```bash
uv add sanka-sdk
```

## Usage

```python
from sanka_sdk import SankaClient

client = SankaClient(token="YOUR_TOKEN")
response = client.public_auth.whoami()
print(response)
```

## Local migration

The hosted API client and local migration adapter are separate surfaces:

| Import | What runs | Authentication |
|---|---|---|
| `from sanka_sdk import SankaClient` | Sanka's hosted HTTP API | API token |
| `from sanka_sdk.migrate import SankaMigrate` | A local `sanka-migrate` subprocess | None |

Install the migration runtime separately, then use the tokenless adapter:

```bash
uv tool install sanka-migrate
```

```python
from sanka_sdk.migrate import SankaMigrate

migrate = SankaMigrate(cwd="./django-app")

scan = migrate.scan()
plan = migrate.plan(
    to="fastapi",
    generation="full",
    strategy="native",
    package_manager="uv",
)
applied = migrate.apply(plan_hash=plan.data["plan_hash"])
tested = migrate.test()
verified = migrate.verify()
```

Each method maps directly to the local runtime:

| Python method | Runtime command | Purpose |
|---|---|---|
| `scan()` | `sanka-migrate scan ... --json` | Inspect the source and write the scan artifact |
| `plan()` | `sanka-migrate plan ... --json` | Create a reviewable plan and plan hash |
| `apply()` | `sanka-migrate apply ... --json` | Generate only from the supplied reviewed plan hash |
| `test()` | `sanka-migrate test ... --json` | Prepare the generated target environment and run its tests |
| `verify()` | `sanka-migrate verify ... --json` | Verify integrity and configured behavior |

The adapter invokes an argument vector without a shell and never calls Sanka's
hosted API. It forwards only parameters you provide; defaults, validation,
framework detection, generated-target environments, and plan-hash safety remain
owned by `sanka-migrate`. Every call returns a typed `SankaMigrateResult` with
the `sanka-cli/v1` fields `data`, `artifacts`, `limitations`, and
`next_actions`.

Failures raise `SankaMigrateError`. Its `command`, `exit_code`, `parsed_error`,
and `stderr` attributes distinguish a migration failure (exit `1`), invalid
usage (exit `2`), a missing executable, and an invalid protocol response. The
public classes and methods include docstrings for IDE hover and `help()`.

See the [CLI execution model](https://github.com/sankaHQ/sanka/blob/main/docs/django-to-fastapi.md#cli-and-sdk-execution-model)
and [Sanka developer documentation](https://sanka.com/docs/developers/).

## Regenerate

```bash
./scripts/generate_sdk.sh
```

## Publish

This repo includes a GitHub Actions workflow for PyPI Trusted Publishing at [.github/workflows/publish.yml](.github/workflows/publish.yml).

Configure a Trusted Publisher on PyPI for:

- owner: `sankaHQ`
- repository: `sanka-python`
- workflow: `.github/workflows/publish.yml`
- environment: `pypi`

Then publish by pushing a tag like `vX.Y.Z` or running the workflow manually.
