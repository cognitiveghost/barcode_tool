#!/usr/bin/env bash
# Creates .venv in this checkout and installs requirements.txt into it.
# .venv is gitignored, so a fresh git worktree starts without one - run
# this inside each worktree you want to test in.
set -e
cd "$(dirname "$0")"

PYTHON=python3
if ! "$PYTHON" -c "import ctypes" >/dev/null 2>&1; then
  # This machine has more than one python3.14 on PATH and the first one
  # found is missing its _ctypes build (breaks pypdfium2/WeasyPrint at
  # import time) - fall back to the system interpreter, which has it.
  PYTHON=/usr/bin/python3
fi

"$PYTHON" -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
