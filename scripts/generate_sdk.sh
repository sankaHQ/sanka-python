#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FERN_DIR="$ROOT/fern"
TMP_DIR="$(mktemp -d "$ROOT/.tmp-fern.XXXXXX")"
OUTPUT_DIR="$ROOT/src/sanka_sdk"
GENERATOR_IMAGE="fernapi/fern-python-sdk:4.34.0"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

ensure_colima() {
  if docker context ls >/dev/null 2>&1 && docker version >/dev/null 2>&1; then
    return
  fi

  if [ -x /opt/homebrew/bin/colima ]; then
    PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin /opt/homebrew/bin/colima start
  elif command -v colima >/dev/null 2>&1; then
    colima start
  fi
}

ensure_docker_host() {
  if [ -n "${DOCKER_HOST:-}" ] && docker version >/dev/null 2>&1; then
    return
  fi

  for sock in \
    "$HOME/.colima/default/docker.sock" \
    "/var/run/docker.sock" \
    "$HOME/.docker/run/docker.sock"
  do
    if [ -S "$sock" ] && DOCKER_HOST="unix://$sock" docker version >/dev/null 2>&1; then
      export DOCKER_HOST="unix://$sock"
      return
    fi
  done

  echo "No working Docker daemon found." >&2
  exit 1
}

ensure_colima
ensure_docker_host
export DOCKER_CONFIG="$TMP_DIR/docker-config"
mkdir -p "$DOCKER_CONFIG" "$OUTPUT_DIR"
printf '{}\n' > "$DOCKER_CONFIG/config.json"

(cd "$FERN_DIR" && npx --yes fern-api check >/dev/null)
(cd "$FERN_DIR" && npx --yes fern-api ir "$TMP_DIR/ir.json" >/dev/null)

cat > "$TMP_DIR/config.manual.json" <<'EOF'
{
  "dry_run": false,
  "dryRun": false,
  "ir_filepath": "/workspace/ir.json",
  "irFilepath": "/workspace/ir.json",
  "output": {
    "path": "/fern/output",
    "mode": {
      "type": "downloadFiles"
    }
  },
  "workspace_name": "api",
  "workspaceName": "api",
  "organization": "sanka",
  "environment": {
    "_type": "local"
  },
  "whitelabel": false,
  "write_unit_tests": false,
  "writeUnitTests": false,
  "generate_oauth_clients": true,
  "generateOauthClients": true,
  "custom_config": {
    "package_name": "sanka_sdk",
    "client": {
      "class_name": "SankaClient",
      "filename": "client.py",
      "exported_filename": "client.py"
    },
    "exclude_types_from_init_exports": true,
    "pydantic_config": {
      "skip_validation": true
    }
  }
}
EOF

find "$OUTPUT_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true

docker pull "$GENERATOR_IMAGE" >/dev/null
docker run --rm \
  -v "$TMP_DIR:/workspace" \
  -v "$OUTPUT_DIR:/fern/output" \
  "$GENERATOR_IMAGE" \
  /workspace/config.manual.json >/dev/null

touch "$OUTPUT_DIR/py.typed"
python3 -m compileall "$OUTPUT_DIR" >/dev/null

echo "Generated SDK into $OUTPUT_DIR"
