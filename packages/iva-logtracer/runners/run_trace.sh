#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IVA_LOGTRACER_DIR="$(dirname "$SCRIPT_DIR")"
cd "$IVA_LOGTRACER_DIR"

if [ -f ".venv/bin/iva-logtracer" ]; then
    CLI=".venv/bin/iva-logtracer"
elif command -v iva-logtracer >/dev/null 2>&1; then
    CLI="iva-logtracer"
elif [ -f ".venv/bin/python" ]; then
    CLI=".venv/bin/python -m logtracer_extractors.cli"
elif command -v python3 >/dev/null 2>&1; then
    CLI="python3 -m logtracer_extractors.cli"
else
    CLI="python -m logtracer_extractors.cli"
fi

exec $CLI trace "$@"
