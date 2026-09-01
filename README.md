# sanka-sdk

Python SDK for Sanka's hosted API and local migration lifecycle.

This package is generated from Sanka's OpenAPI spec using Fern, then packaged locally for `uv` and PyPI.

## Install

Python 3.9 or newer is required. CI tests every minor from Python 3.9 through Python 3.14.

```bash
uv add sanka-sdk
```

## Hosted API

```python
from sanka_sdk import SankaClient

client = SankaClient(token="YOUR_TOKEN")
response = client.public_auth.whoami()
print(response)
```

`SankaClient` calls Sanka's hosted HTTP API and requires a token. Extension
management is part of the local migration runtime described below; it is not a
hosted API resource.

## Local migration runtime

The hosted API client and local migration adapter are separate surfaces:

| Import | What runs | Authentication |
|---|---|---|
| `from sanka_sdk import SankaClient` | Sanka's hosted HTTP API | API token |
| `SankaMigrate` or `AsyncSankaMigrate` from `sanka_sdk.migrate` | A local `sanka-migrate` subprocess | None |

Install the runtime separately. Installing `sanka-sdk` does not install or
authenticate `sanka-migrate`.

```bash
uv tool install sanka-migrate
```

Use a runtime release that includes the extension marketplace commands and
the published default DRF extension dependency.

### Configure an extension, scan, and plan

Add the official marketplace and lock the extension before the first scan.
Marketplace snapshots are user-scoped; the extension lock belongs to the
project in `cwd`.

```python
from sanka_sdk.migrate import SankaMigrate

migrate = SankaMigrate(cwd="./django-app")

migrate.extensions.marketplaces.add(
    "git@github.com:sankaHQ/extensions.git",
    name="sanka",
)
migrate.extensions.add("sanka/drf-to-fastapi", marketplace="sanka")

scan = migrate.scan()
plan = migrate.plan(
    to="fastapi",
    extension_config={
        "generation": "minimal",
        "output": "./fastapi-app",
        "package_manager": "uv",
        "strategy": "native",
    },
    extension_environment=("DJANGO_SECRET_KEY",),
)
applied = migrate.apply(plan_hash=plan.data["plan_hash"])
tested = migrate.test()
verified = migrate.verify()
```

`scan.data["recommendations"]` contains the selected extension, its target,
matching evidence, and install status. When the exact default package is
already installed and has not been disabled, `sanka-migrate` can lock it on
the first scan. Otherwise, if no matching extension is enabled, the command
stops with `SANKA_EXTENSION_REQUIRED`. The error details contain the
recommendations and exact `add_command`; the SDK does not bypass the runtime's
selection and trust checks.

`extension_config` accepts JSON-compatible values and is serialized as stable,
sorted JSON. `extension_environment` accepts environment variable names, not
secret values. `sanka-migrate` forwards only those named values to the selected
extension. Both options are available on `scan()`, `plan()`, `apply()`,
`test()`, and `verify()`.

### Manage extensions and marketplaces

```python
extensions = migrate.extensions

installed = extensions.list()
extensions.add("example/demo", marketplace="partner")
extensions.remove("example/demo")

marketplaces = extensions.marketplaces
marketplaces.add(
    "https://github.com/example/sanka-extensions.git",
    name="partner",
    trust=True,
)
marketplaces.list()
marketplaces.upgrade("partner")  # Omit the name to upgrade all marketplaces.
marketplaces.remove("partner")
```

The Python methods map directly to these local commands:

| Python method | `sanka-migrate` command |
|---|---|
| `extensions.list()` | `extension list --json` |
| `extensions.add(id, marketplace=...)` | `extension add ID --marketplace NAME --json` |
| `extensions.remove(id)` | `extension remove ID --json` |
| `extensions.marketplaces.list()` | `extension marketplace list --json` |
| `extensions.marketplaces.add(source, name=..., trust=True)` | `extension marketplace add SOURCE --name NAME --trust --json` |
| `extensions.marketplaces.upgrade(name)` | `extension marketplace upgrade NAME --json` |
| `extensions.marketplaces.remove(name)` | `extension marketplace remove NAME --json` |

`trust=True` is an explicit operator decision. The SDK only passes `--trust`.
`sanka-migrate` owns source identity checks, immutable marketplace snapshots,
artifact verification, project locks, extension installation, upgrades, and
removal safety. An untrusted source fails with
`SANKA_MARKETPLACE_TRUST_REQUIRED`; the SDK does not bypass that check.

### Async adapter

Use `AsyncSankaMigrate` to run the same commands without blocking the event
loop. Its lifecycle, extension, and marketplace methods have the same arguments
and results as the synchronous adapter. Cancelling an awaited command kills and
reaps its local CLI process.

```python
import asyncio

from sanka_sdk.migrate import AsyncSankaMigrate


async def main() -> None:
    migrate = AsyncSankaMigrate(cwd="./django-app")

    scan = await migrate.scan()
    await migrate.extensions.list()
    plan = await migrate.plan(to="fastapi")
    await migrate.apply(plan_hash=plan.data["plan_hash"])
    await migrate.test()
    await migrate.verify()


asyncio.run(main())
```

Each method maps directly to the local runtime:

| Python method | Runtime command | Purpose |
|---|---|---|
| `scan()` | `sanka-migrate scan ... --json` | Inspect the source and write the scan artifact |
| `plan()` | `sanka-migrate plan ... --json` | Create a reviewable plan and plan hash |
| `apply()` | `sanka-migrate apply ... --json` | Generate only from the supplied reviewed plan hash |
| `test()` | `sanka-migrate test ... --json` | Prepare the generated target environment and run its tests |
| `verify()` | `sanka-migrate verify ... --json` | Verify integrity and configured behavior |

### Results, failures, and subprocess safety

Both adapters execute an argv list without a shell and never call Sanka's
hosted API. Arguments such as marketplace URLs, paths, and configuration values
are not interpreted as shell commands.

Every successful call returns a typed `SankaMigrateResult`. The validated
`sanka-cli/v1` fields are `schema_version`, `command`, `outcome`,
`migration_state`, `data`, `artifacts`, `limitations`, and `next_actions`.
`ScanData`, `ExtensionRecommendation`, `ExtensionEvidence`, and
`ExtensionFailure` describe the extension-specific data available to type
checkers and IDEs.

```python
from sanka_sdk.migrate import SankaMigrateError

try:
    migrate.extensions.marketplaces.add("./third-party", name="third-party")
except SankaMigrateError as error:
    print(error.command, error.exit_code)
    print(error.parsed_error)  # code, message, and optional details
    print(error.result)  # Complete validated failure envelope, when available.
```

Failures are fail-closed. The SDK rejects missing executables, malformed or
non-object JSON, a schema other than `sanka-cli/v1`, the wrong command, invalid
outcome/exit-code pairs, malformed `data.error`, and non-string artifact or
action lists. A valid CLI failure raises `SankaMigrateError` with its typed
result preserved. Exit `1` is a runtime failure, exit `2` is invalid usage, and
any other exit code is a protocol error.

Defaults, framework detection, marketplace trust, immutable snapshots,
extension subprocess execution, generated-target environments, and plan-hash
safety remain in `sanka-migrate`. The SDK is a typed local adapter, not a second
migration runtime.

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
