#!/usr/bin/env bash
# Creates .venv in this checkout and installs requirements.txt into it.
# .venv is gitignored, so a fresh git worktree starts without one - run
# this inside each worktree you want to test in.
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
