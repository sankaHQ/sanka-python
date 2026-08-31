# sanka-sdk

Python SDK for the Sanka API.

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

Install the migration runtime separately, then use the tokenless migration
module:

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

The five methods mirror the functional arguments of `sanka-migrate scan`,
`plan`, `apply`, `test`, and `verify`. Defaults, validation, framework
detection, generated-target environments, and plan-hash safety remain owned by
the runtime. See the [Sanka developer documentation](https://sanka.com/docs/developers/)
for the CLI lifecycle.

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
