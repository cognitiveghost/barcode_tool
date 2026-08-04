# Alpha Release CI — Design — 2026-08-03

Adds a build-and-publish workflow so a GitHub Release produces a downloadable
Windows build and a Linux build automatically. Separate from `ci.yml`, which
keeps running tests/lint on every push and PR unchanged.

## Decisions

| Question | Choice |
|---|---|
| Trigger | `release: types: [published]` — push a tag, create a GitHub Release marked "pre-release" |
| Windows package shape | PyInstaller `--onedir`, zipped. Not `--onefile` — onedir keeps bundled DLLs on disk next to the exe instead of behind a temp-extraction step, which matters for the WeasyPrint fix below |
| Linux package shape | PyInstaller `--onedir`, tarred. No `.deb`/AppImage for the alpha |
| Publishing artifacts | `gh release upload` with the runner's built-in `GITHUB_TOKEN` — no marketplace action |
| Gate | A `test` job reruns the existing pytest suite; both build jobs `needs: test` |

## Why this isn't just "run pyinstaller"

`template_renderer.py` renders labels through `blabel` → WeasyPrint, which
loads Pango/Cairo/GDK-Pixbuf natively via `ctypes`, not as ordinary Python
package dependencies. PyInstaller's dependency walker doesn't see these —
it's the same reason `ci.yml:23-33` has a Windows-only MSYS2 step just to
get `pytest` passing today. A frozen exe needs the equivalent fix baked in,
or label rendering fails silently on first use on a machine that isn't the
build machine.

- **Windows**: no OS-level shared-library search path exists for arbitrary
  installed DLLs. WeasyPrint's own workaround is the
  `WEASYPRINT_DLL_DIRECTORIES` env var, which it reads via
  `os.add_dll_directory()` — but only when
  `not hasattr(sys, 'frozen')` (`weasyprint/text/ffi.py:467`). A frozen
  PyInstaller build **is** `sys.frozen`, so WeasyPrint deliberately skips
  that logic in a frozen app — setting the env var would silently do
  nothing. The app must call `os.add_dll_directory()` itself at startup
  instead of relying on WeasyPrint to read the env var.
- **Linux**: `ctypes.util.find_library` resolves through the standard
  linker cache (`ldconfig`), which is why `ci.yml` needs no Pango step for
  Ubuntu at all. Nothing to bundle — just document the apt packages as a
  runtime requirement.

## Windows build

1. Install Pango/GTK via the same `pacman -S mingw-w64-x86_64-pango` step
   `ci.yml:31-33` already uses.
2. `pip install pyinstaller`; build with `--add-data` for
   `app/templates/examples` and `app/assets/fonts` (the two non-`.py` asset
   trees `template_renderer.py` reads via `EXAMPLES_ROOT`/`FONT_CSS`).
3. Copy `C:\msys64\mingw64\bin` into `dist/BarcodeTool/gtk-dlls/` next to
   the frozen exe.
4. **Code change** — [app/main.py](app/main.py): before the
   `from app.ui.main_window import MainWindow` import (which pulls in
   `template_renderer` → `blabel` → WeasyPrint at import time), add:

   ```python
   import os
   import sys
   from pathlib import Path

   if getattr(sys, "frozen", False) and hasattr(os, "add_dll_directory"):
       os.add_dll_directory(str(Path(sys.executable).parent / "gtk-dlls"))
   ```

   `hasattr(os, "add_dll_directory")` is only true on Windows, so this is
   a no-op on the Linux build even though it's frozen too. Guarded by
   `sys.frozen` so normal `python -m app.main` / `run.sh` / pytest runs
   are untouched.
5. Zip `dist/BarcodeTool/` → `BarcodeTool-windows-<tag>.zip`.

## Linux build

`pyinstaller --onedir` with the same `--add-data` flags, no DLL copy step.
Tar `dist/` → `BarcodeTool-linux-<tag>.tar.gz`. Note in the release body (or
a README section) that the target machine needs
`libpango-1.0-0 libcairo2 libgdk-pixbuf-2.0-0` from apt.

## Known ceiling

Windows bundles the entire `mingw64/bin` closure pacman installed for the
pango package tree, rather than a hand-picked minimal DLL set — bigger zip
than strictly necessary, but correct without manual dependency tracing.
Trim later if size becomes a problem.

## Out of scope for this pass

- `.deb`/AppImage packaging for Linux.
- App-internal version string / `--version` flag.
- Automated smoke test of the frozen binary (no display in CI for a GUI
  app; existing pytest suite is the gate instead).
