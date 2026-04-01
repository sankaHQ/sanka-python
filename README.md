# sanka-sdk

Python SDK for the Sanka API.

This package is generated from [Sanka's OpenAPI spec](/Users/haegwan/Sites/sanka/sanka-sdks/openapi.json) using Fern, then packaged locally for `uv` and PyPI.

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

## Regenerate

```bash
./scripts/generate_sdk.sh
```

## Publish

This repo includes a GitHub Actions workflow for PyPI Trusted Publishing at [.github/workflows/publish.yml](/Users/haegwan/Sites/sanka/sanka-python/.github/workflows/publish.yml).

Configure a Trusted Publisher on PyPI for:

- owner: `sankaHQ`
- repository: `sanka-python`
- workflow: `.github/workflows/publish.yml`
- environment: `pypi`

Then publish by pushing a tag like `v0.1.0` or running the workflow manually.

