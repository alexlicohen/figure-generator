#!/usr/bin/env bash
# Idempotent environment setup for scidraw-agent (used by the SessionStart hook and locally).
# Installs the Graphviz `dot` binary (needed by the pipeline/study-design generator and not
# pip-installable) and the Python dependencies into a local venv.
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v dot >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    (sudo apt-get update -qq && sudo apt-get install -y -qq graphviz) \
      || apt-get install -y -qq graphviz \
      || echo "warning: could not install graphviz; the pipeline generator will be unavailable"
  fi
fi

if command -v uv >/dev/null 2>&1; then
  uv venv --python 3.11 >/dev/null 2>&1 || true
  uv pip install -e ".[dev]" >/dev/null
else
  python3 -m venv .venv
  ./.venv/bin/pip install -q -e ".[dev]"
fi

echo "scidraw-agent setup complete."
