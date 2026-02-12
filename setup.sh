#!/usr/bin/env bash
# BenchAid setup script
# Generic tool installation for Python CLIs in scripts/ and Go CLIs in cmd/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${BIN_DIR:-$SCRIPT_DIR/bin}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "Setting up BenchAid..."
echo "Repository location: $SCRIPT_DIR"

echo ""
echo "Preparing local environment..."
if [[ ! -f "$SCRIPT_DIR/.env" && -f "$SCRIPT_DIR/.env.example" ]]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    echo "  Created .env from .env.example"
fi

echo ""
echo "Making Python scripts executable..."
if [[ -d "$SCRIPT_DIR/scripts" ]]; then
    find "$SCRIPT_DIR/scripts" -type f -name "*.py" -exec chmod +x {} +
    echo "  Updated script permissions in scripts/"
else
    echo "  scripts/ not found, skipping"
fi

echo ""
echo "Installing Python dependencies..."
if command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_VERSION="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    if "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
        "$PYTHON_BIN" -m venv "$SCRIPT_DIR/.venv"
        "$SCRIPT_DIR/.venv/bin/python" -m pip install --upgrade pip >/dev/null
        "$SCRIPT_DIR/.venv/bin/pip" install biopython primer3-py >/dev/null
        echo "  Installed Python deps in .venv (Python $PYTHON_VERSION)"
    else
        echo "  Python $PYTHON_VERSION detected; require 3.10+ for dependency install"
    fi
else
    echo "  python3 not found, skipping Python dependency install"
fi

echo ""
echo "Building Go tools from cmd/..."
if command -v go >/dev/null 2>&1; then
    mkdir -p "$BIN_DIR"
    built_any=0
    for pkg_dir in "$SCRIPT_DIR"/cmd/*; do
        if [[ -d "$pkg_dir" && -f "$pkg_dir/main.go" ]]; then
            tool_name="$(basename "$pkg_dir")"
            go build -o "$BIN_DIR/$tool_name" "./cmd/$tool_name"
            echo "  Built: $tool_name -> $BIN_DIR/$tool_name"
            built_any=1
        fi
    done
    if [[ "$built_any" -eq 0 ]]; then
        echo "  No Go cmd/*/main.go packages found"
    fi
else
    echo "  go not found, skipping Go tool build"
fi

echo ""
echo "Setup complete."
echo "Use Python tools via .venv, e.g.:"
echo "  source .venv/bin/activate && python scripts/primer_cli.py --help"
echo "Go binaries are in:"
echo "  $BIN_DIR"
echo "Add to PATH if desired:"
echo "  export PATH=\"$BIN_DIR:\$PATH\""
