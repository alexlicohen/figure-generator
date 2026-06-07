#!/usr/bin/env bash
# Idempotent environment setup for scidraw-agent (used by the SessionStart hook and locally).
# Installs the Graphviz `dot` binary (needed by the pipeline/study-design generator and not
# pip-installable) and the Python dependencies into a local venv.
set -euo pipefail

cd "$(dirname "$0")/.."

# System deps: Graphviz `dot` (pipeline/study-design generator) + cairo (raster export via
# cairosvg). Neither is pip-installable. apt on Linux; Homebrew on macOS.
if command -v apt-get >/dev/null 2>&1; then
  if ! command -v dot >/dev/null 2>&1; then
    (sudo apt-get update -qq && sudo apt-get install -y -qq graphviz libcairo2) \
      || apt-get install -y -qq graphviz libcairo2 \
      || echo "warning: could not install graphviz/cairo; pipeline + raster export may be unavailable"
  fi
elif command -v brew >/dev/null 2>&1; then
  # graphviz provides `dot`; cairo provides libcairo for cairosvg PNG/PDF export.
  for formula in graphviz cairo; do
    brew list --versions "$formula" >/dev/null 2>&1 || brew install "$formula" \
      || echo "warning: could not brew install $formula"
  done
else
  echo "warning: no apt-get or brew found; install graphviz + cairo manually for full functionality"
fi

if command -v uv >/dev/null 2>&1; then
  uv venv --python 3.11 >/dev/null 2>&1 || true
  uv pip install -e ".[dev]" >/dev/null
else
  python3 -m venv .venv
  ./.venv/bin/pip install -q -e ".[dev]"
fi

echo "scidraw-agent setup complete."
