# Alpha Release CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On publishing a GitHub Release, CI builds a Windows onedir zip and a
Linux onedir tarball of the app and attaches both to that release.

**Architecture:** New `.github/workflows/release.yml`, separate from the
existing `ci.yml` (which keeps testing every push/PR unchanged). Triggered by
`release: types: [published]`. A `test` job reruns pytest as a gate; two
build jobs (`build-windows`, `build-linux`) run `needs: test` in parallel,
each freezing the app with PyInstaller and uploading its own artifact via
`gh release upload`.

**Tech Stack:** PyInstaller (onedir), GitHub Actions, `gh` CLI (preinstalled
on GitHub-hosted runners — no marketplace publish action).

## Global Constraints

- Trigger is `release: types: [published]` — nothing else triggers this
  workflow.
- Windows and Linux both ship as PyInstaller `--onedir` builds (Windows
  zipped, Linux tarred) — not `--onefile`.
- Every PyInstaller invocation must include `--collect-data blabel` —
  verified below that `blabel` ships a package-data file
  (`blabel/data/print_template.html`) PyInstaller's default import-graph
  analysis does not find; without this flag the frozen app crashes on
  first import of `app.core.template_renderer`.
- The frozen-mode Windows fix must call `os.add_dll_directory()` directly
  — **not** set `WEASYPRINT_DLL_DIRECTORIES`. Verified against
  `weasyprint/text/ffi.py:467`: WeasyPrint only reads that env var when
  `not hasattr(sys, 'frozen')`, so in an actual frozen build it silently
  ignores the env var. Task 1 below reflects this.
- Every PyInstaller invocation must bundle `app/templates/examples` and
  `app/assets/fonts` via `--add-data` (the two non-`.py` asset trees
  `template_renderer.py` reads through `EXAMPLES_ROOT`/`FONT_CSS`).
- Publishing artifacts uses `gh release upload ... --clobber` with
  `GH_TOKEN: ${{ github.token }}` — the workflow needs
  `permissions: contents: write` for this to have write access.
- Python version pinned to `3.11`, matching `ci.yml`.
- The `test` job runs once, on `ubuntu-latest` only — `ci.yml` already
  matrixes push/PR across both OSes on the same commit; re-testing both
  platforms again here is redundant, it's a build gate, not a fresh QA
  pass.

## Verified before writing this plan

A real onedir build was run locally (Linux) against this exact dependency
tree. The naive command (`pyinstaller --onedir --add-data ... app/main.py`,
no `--collect-data`) froze successfully but **crashed on launch**:

```
FileNotFoundError: [Errno 2] No such file or directory:
'.../dist/BarcodeTool/_internal/blabel/data/print_template.html'
```

Adding `--collect-data blabel` fixed it — the frozen binary then launched
and reached the Qt event loop cleanly under `QT_QPA_PLATFORM=offscreen`.
The Global Constraints above reflect that fix. The Windows job cannot be
verified the same way in this environment (no Windows runner available) —
Task 3 notes where its real verification has to happen instead.

---

### Task 1: Frozen-mode WeasyPrint DLL directory guard

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_main.py` (new)

**Interfaces:**
- Produces: `configure_frozen_weasyprint_env()` in `app/main.py` — when
  `sys.frozen` is truthy *and* `os.add_dll_directory` exists (Windows
  only), calls `os.add_dll_directory(<directory containing
  sys.executable>/gtk-dlls)`; no-op otherwise (including on the Linux
  frozen build, where `os.add_dll_directory` doesn't exist at all).
  **Task 3 must place the bundled GTK DLLs at exactly that relative
  path** (`gtk-dlls/` next to the frozen exe) for this fix to take
  effect — that's the contract between these two tasks.

  This deliberately does **not** set `WEASYPRINT_DLL_DIRECTORIES` — see
  the Global Constraints note above on why that env var is a no-op in a
  frozen build.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_main.py`:

```python
import os
import sys
from pathlib import Path

import app.main as main_module


def test_configure_frozen_weasyprint_env_adds_dll_dir_when_frozen(monkeypatch):
    fake_executable = str(Path("fake_root") / "BarcodeTool" / "BarcodeTool.exe")
    calls = []
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", fake_executable, raising=False)
    monkeypatch.setattr(os, "add_dll_directory", lambda p: calls.append(p), raising=False)

    main_module.configure_frozen_weasyprint_env()

    expected = str(Path("fake_root") / "BarcodeTool" / "gtk-dlls")
    assert calls == [expected]


def test_configure_frozen_weasyprint_env_noop_when_not_frozen(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(os, "add_dll_directory", lambda p: calls.append(p), raising=False)

    main_module.configure_frozen_weasyprint_env()

    assert calls == []
```

Note: `monkeypatch.setattr(os, "add_dll_directory", ..., raising=False)`
works even on Linux, where that attribute doesn't normally exist — it
lets the test exercise the Windows-only branch's logic on any platform,
which matters since `ci.yml` runs the full suite on both `ubuntu-latest`
and `windows-latest`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_main.py -v`
Expected: FAIL — `AttributeError: module 'app.main' has no attribute
'configure_frozen_weasyprint_env'`

- [ ] **Step 3: Implement the guard**

Replace the top of `app/main.py` (currently just `import sys` followed by
the `PySide6`/`MainWindow` imports) with:

```python
import os
import sys
from pathlib import Path


def configure_frozen_weasyprint_env() -> None:
    if getattr(sys, "frozen", False) and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(Path(sys.executable).parent / "gtk-dlls"))


configure_frozen_weasyprint_env()

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

The function call must stay *before* the `MainWindow` import — that import
chain reaches `blabel` → WeasyPrint, which reads the env var at import
time.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_main.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full suite and lint to confirm no regressions**

Run: `python3 -m pytest -q && ruff check .`
Expected: all tests pass (365+ passed), ruff reports no issues. (Confirmed
locally: ruff's default rule set does not flag code appearing before these
imports — no `# noqa` needed.)

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_main.py
git commit -m "fix: point WeasyPrint at bundled GTK DLLs when frozen"
```

---

### Task 2: Release workflow skeleton — trigger, permissions, test gate

**Files:**
- Create: `.github/workflows/release.yml`

**Interfaces:**
- Produces: a `test` job named `test` that later tasks' `build-windows` /
  `build-linux` jobs reference via `needs: test`.

- [ ] **Step 1: Create the workflow file**

```yaml
name: Release

on:
  release:
    types: [published]

permissions:
  contents: write

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install Qt runtime libraries
        run: |
          sudo apt-get update
          sudo apt-get install -y libegl1 libxkbcommon0 libxcb-cursor0
      - run: pip install -r requirements.txt
      - run: pytest -v
```

- [ ] **Step 2: Validate YAML syntax**

Run: `python3 -c "import yaml; d = yaml.safe_load(open('.github/workflows/release.yml')); print(list(d['jobs']))"`
Expected: prints `['test']`, no exception.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: add release workflow skeleton with test gate"
```

---

### Task 3: Windows build job

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `configure_frozen_weasyprint_env()`'s contract from Task 1 —
  DLLs must land at `gtk-dlls/` next to `BarcodeTool.exe`.
- Consumes: `test` job name from Task 2 (`needs: test`).

**Note on verification:** this job cannot run on this machine (no Windows
runner available locally). Steps 1–2 below verify what *can* be checked
offline (YAML syntax, flag parity with the Linux job that Task 4 verifies
for real). The genuine end-to-end check happens on the first tag push used
to cut the alpha — watch that Actions run and be ready to iterate on the
DLL-copy step if WeasyPrint still can't find a library.

- [ ] **Step 1: Add the `build-windows` job**

Append to `.github/workflows/release.yml`, under `jobs:`:

```yaml
  build-windows:
    needs: test
    runs-on: windows-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install Pango/GTK runtime (MSYS2)
        shell: cmd
        run: |
          C:\msys64\usr\bin\pacman.exe -S --noconfirm --needed mingw-w64-x86_64-pango
      - run: pip install -r requirements.txt pyinstaller
      - name: Build with PyInstaller
        run: >
          pyinstaller --name BarcodeTool --onedir --noconfirm
          --add-data "app/templates/examples;app/templates/examples"
          --add-data "app/assets/fonts;app/assets/fonts"
          --collect-data blabel
          app/main.py
      - name: Bundle GTK DLLs
        shell: pwsh
        run: |
          Copy-Item -Recurse -Path "C:\msys64\mingw64\bin" -Destination "dist\BarcodeTool\gtk-dlls"
      - name: Zip artifact
        shell: pwsh
        run: |
          Compress-Archive -Path "dist\BarcodeTool\*" -DestinationPath "BarcodeTool-windows-${{ github.event.release.tag_name }}.zip"
      - name: Upload to release
        env:
          GH_TOKEN: ${{ github.token }}
        run: gh release upload "${{ github.event.release.tag_name }}" "BarcodeTool-windows-${{ github.event.release.tag_name }}.zip" --clobber
```

Note the `;` separator in `--add-data` — Windows PyInstaller uses `;`
between source and destination, Linux/macOS use `:` (Task 4 uses `:`).

- [ ] **Step 2: Add PyInstaller build artifacts to `.gitignore`**

Add to `.gitignore`:

```
build/
dist/
*.spec
```

(Anyone running this PyInstaller command locally — including you, testing
Task 4 — will otherwise get untracked `build/`, `dist/`, and
`BarcodeTool.spec` showing up in `git status`.)

- [ ] **Step 3: Validate YAML syntax**

Run: `python3 -c "import yaml; d = yaml.safe_load(open('.github/workflows/release.yml')); print(list(d['jobs']))"`
Expected: prints `['test', 'build-windows']`, no exception.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release.yml .gitignore
git commit -m "ci: add Windows release build job"
```

---

### Task 4: Linux build job + release instructions

**Files:**
- Modify: `.github/workflows/release.yml`
- Create: `RELEASING.md`

**Interfaces:**
- Consumes: `test` job name from Task 2 (`needs: test`).

- [ ] **Step 1: Add the `build-linux` job**

Append to `.github/workflows/release.yml`, under `jobs:`:

```yaml
  build-linux:
    needs: test
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt pyinstaller
      - name: Build with PyInstaller
        run: >
          pyinstaller --name BarcodeTool --onedir --noconfirm
          --add-data "app/templates/examples:app/templates/examples"
          --add-data "app/assets/fonts:app/assets/fonts"
          --collect-data blabel
          app/main.py
      - name: Tar artifact
        run: tar -czf "BarcodeTool-linux-${{ github.event.release.tag_name }}.tar.gz" -C dist BarcodeTool
      - name: Upload to release
        env:
          GH_TOKEN: ${{ github.token }}
        run: gh release upload "${{ github.event.release.tag_name }}" "BarcodeTool-linux-${{ github.event.release.tag_name }}.tar.gz" --clobber
```

- [ ] **Step 2: Actually run this build locally and smoke-test it**

This is the one platform we can fully verify here. In a scratch venv:

```bash
python3 -m venv /tmp/pyi_venv
/tmp/pyi_venv/bin/pip install -r requirements.txt pyinstaller
/tmp/pyi_venv/bin/pyinstaller --name BarcodeTool --onedir --noconfirm \
  --add-data "app/templates/examples:app/templates/examples" \
  --add-data "app/assets/fonts:app/assets/fonts" \
  --collect-data blabel \
  app/main.py
```

Then confirm the data files landed and the binary boots without crashing:

```bash
test -f dist/BarcodeTool/_internal/app/templates/examples/README.txt && echo "templates: OK"
test -f dist/BarcodeTool/_internal/app/assets/fonts/fonts.css && echo "fonts: OK"

QT_QPA_PLATFORM=offscreen ./dist/BarcodeTool/BarcodeTool &
PID=$!
sleep 3
kill -0 "$PID" && echo "ALIVE after 3s: OK" && kill "$PID"
```

Expected: `templates: OK`, `fonts: OK`, `ALIVE after 3s: OK`. (This exact
sequence was already run once while writing this plan and passed — this
step is re-confirming it against your actual working tree, since Task 1's
`app/main.py` change wasn't present during that earlier run.)

Clean up afterward: `rm -rf build dist BarcodeTool.spec` (now gitignored
by Task 3, but the scratch venv build ran before that commit in this
sequence — remove by hand once).

- [ ] **Step 3: Write `RELEASING.md`**

```markdown
# Cutting a release

1. Push a tag: `git tag v0.1.0-alpha.1 && git push origin v0.1.0-alpha.1`
2. Create a GitHub Release from that tag, check "Set as a pre-release".
3. Publishing the release triggers `.github/workflows/release.yml`, which
   runs the test suite and, if it passes, builds and attaches:
   - `BarcodeTool-windows-<tag>.zip` — unzip, run `BarcodeTool.exe`.
   - `BarcodeTool-linux-<tag>.tar.gz` — untar, run `./BarcodeTool`.

## Linux runtime requirement

The Linux build does not bundle Qt's X11 platform libraries or
Pango/Cairo/GDK-Pixbuf — both are resolved through the system linker cache
at runtime instead of being frozen in. Install on the target machine if
not already present:

    sudo apt install libegl1 libxkbcommon0 libxcb-cursor0 \
        libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0

## Known limitation

The Windows build bundles the entire MSYS2 `mingw64/bin` directory
(everything `pacman` installed for the Pango package tree) into
`gtk-dlls/`, rather than a hand-picked minimal DLL set — a bigger zip than
strictly necessary, but correct without manually tracing the dependency
graph. Revisit if artifact size becomes a problem.
```

- [ ] **Step 4: Validate YAML syntax**

Run: `python3 -c "import yaml; d = yaml.safe_load(open('.github/workflows/release.yml')); print(list(d['jobs']))"`
Expected: prints `['test', 'build-windows', 'build-linux']`, no exception.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/release.yml RELEASING.md
git commit -m "ci: add Linux release build job and release instructions"
```
