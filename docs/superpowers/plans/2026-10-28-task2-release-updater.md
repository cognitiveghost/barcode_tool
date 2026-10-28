# Task 2: Release button + in-app updater Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A one-click `workflow_dispatch` release that builds a versioned Windows zip and `.sha256`, plus an in-app updater, vendored from Fulfilment, that finds, verifies and installs it.

**Architecture:** `scripts/release_version.py` picks the next tag and stamps `app/__init__.py`. Fulfilment's three updater modules are vendored into `app/vendor/updater/` with relative imports, an identity i18n shim, and `ask()` on `QMessageBox`. `MainWindow` owns one `UpdateFlow`, a corner `QToolButton`, a status-bar toast and a Help → "Check for updates..." action.

**Tech Stack:** Python 3.11 (CI), PySide6, stdlib urllib, pytest (no pytest-qt), GitHub Actions, PyInstaller `--onedir`, `gh`.

**Spec:** `docs/superpowers/specs/2026-10-28-task2-release-updater-design.md`. Read it first. Parent: `docs/superpowers/specs/2026-10-28-thermal-templates-builder-updates-design.md`, Task 2.

**Source repo (read-only):** `/home/gloopy/Desktop/Projects/shopify-fulfillment-tool`, written `$F` below. Copy files from it with `cp`; never edit it.

## Global Constraints

- Run every command from the worktree `/home/gloopy/Desktop/Projects/barcode_tool/.claude/worktrees/dr-40` with `QT_QPA_PLATFORM=offscreen` and `.venv/bin/` tools.
- Never run the whole suite in one pytest process (WeasyPrint/Pango segfaults at ~94%). Run the named test files, or the split used by CI:
  `.venv/bin/pytest -q -k test_shipped_default_actually_applies_the_bundled_font` and then `.venv/bin/pytest -q -k "not test_shipped_default_actually_applies_the_bundled_font"`.
- Lint gate: `.venv/bin/ruff check .` must be clean.
- No new dependencies. `requirements.txt` stays unchanged, and that includes pytest-qt.
- App identity, exactly: `AppIdentity("cognitiveghost/barcode_tool", "BarcodeTool", "BarcodeTool.exe")`. The asset prefix has **no** trailing dash, because `updater.py` appends `-{version}.zip` itself.
- Release assets, exactly: `BarcodeTool-<version>.zip` (with `BarcodeTool.exe` at the zip root) and `BarcodeTool-<version>.zip.sha256`.
- `app/__init__.py` holds exactly one line `__version__ = "dev"`. Only the release workflow stamps it.
- Vendored files: change only what the spec's "Vendored updater" section lists. Every such edit is listed in `app/vendor/updater/SYNCED_FROM`.
- UI strings use ASCII `...`, not `…`, in new barcode_tool code (`Check for updates...`). Strings inside the vendored files stay as they are.
- Commit after each task, using the attribution lines the session gives you.

## Review Focus

1. **Asset name versus updater lookup.** A release named the old way (`BarcodeTool-windows-0.2.0.zip`) must not be offered. One named `BarcodeTool-0.2.0.zip` + `.sha256` must be. Test with `MainWindow`'s real `UPDATE_APP` (Task 3, `test_update_identity_matches_release_assets`).
2. **First release from alpha tags.** Tags `alpha-0.0.10 … alpha-0.0.5` plus `bump=minor` must give `0.1.0`, not an error or `alpha-…` (Task 1, `test_alpha_tags_are_ignored_so_first_minor_is_0_1_0`).
3. **Dev and test runs never touch the network.** Building `MainWindow` in tests or from `run.sh` must not start a check. A manual check in dev says so in the status bar (Task 3, `test_check_for_updates_in_dev_explains_in_status_bar`).
4. **Exactly one stampable version line.** A second `__version__` line, or a missing one, makes the stamp step fail mid-release (Task 1, `test_app_package_has_one_dev_version_line`).
5. **Copied tests on Windows CI.** Fulfilment runs them on Ubuntu only. A POSIX-only assumption must be marked `skipif(os.name == "nt", reason=...)`, not patched in the vendored code (Task 2, Step 6, checked on the PR's Windows CI run).

---

### Task 1: Version stamp + `release_version.py`

**Files:**
- Modify: `app/__init__.py` (empty today)
- Create: `scripts/release_version.py` (copy of `$F/scripts/release_version.py`)
- Create: `tests/test_release_version.py` (copy of `$F/tests/test_release_version.py`, adapted)

**Interfaces:**
- Produces: `app.__version__: str` (`"dev"` in source). The CLI is `python scripts/release_version.py next <patch|minor|major>`, which prints the version, and `python scripts/release_version.py stamp <file> <version>`. The importable functions are `next_version(tags: list[str], bump: str) -> str` and `stamp(path, version) -> None`.

- [ ] **Step 1: Copy the test and adapt it**

`cp $F/tests/test_release_version.py tests/`. The import stays `from scripts.release_version import ...`: the root `conftest.py` puts the repo on `sys.path`, and `scripts/` works as a namespace package, so add no `__init__.py`. Set `PACKAGE_INIT = ROOT / "app" / "__init__.py"`, and rename `test_the_package_ships_as_dev` to `test_app_package_has_one_dev_version_line`. Add:

```python
def test_alpha_tags_are_ignored_so_first_minor_is_0_1_0():
    tags = ["alpha-0.0.10", "alpha-0.0.9", "alpha-0.0.5"]
    assert next_version(tags, "minor") == "0.1.0"
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_release_version.py`
Expected: an error collecting `scripts.release_version` (ModuleNotFoundError).

- [ ] **Step 3: Copy the script and add the version line**

`mkdir -p scripts && cp $F/scripts/release_version.py scripts/`. Change only its docstring's example path to `app/__init__.py`. Write `app/__init__.py` as exactly `__version__ = "dev"` plus a newline.

- [ ] **Step 4: Run it and confirm it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_release_version.py && .venv/bin/ruff check scripts tests/test_release_version.py`
Expected: all pass, ruff clean. Also run `python scripts/release_version.py next minor`, which should print `0.1.0`.

- [ ] **Step 5: Commit**

`git add app/__init__.py scripts/release_version.py tests/test_release_version.py && git commit -m "Add __version__ and release_version.py from Fulfilment"`

---

### Task 2: Vendor the updater into `app/vendor/updater/`

**Files:**
- Create: `app/vendor/__init__.py`, `app/vendor/updater/__init__.py` (both empty)
- Create: `app/vendor/updater/i18n.py`, `app/vendor/updater/SYNCED_FROM`
- Create (copied): `app/vendor/updater/updater.py`, `app/vendor/updater/update_flow.py`, `app/vendor/updater/relaunch.py` from `$F/shared/`
- Create (copied, adapted): `tests/test_updater.py`, `tests/test_update_flow.py`, `tests/test_relaunch.py` from `$F/tests/`

**Interfaces:**
- Produces (unchanged from Fulfilment):
  - `app.vendor.updater.updater`: `AppIdentity(repo, asset_prefix, exe_name)`, `Release`, `newer_release(app, current, fetch=fetch_json) -> Release | None`, `NOT_CHECKED`.
  - `app.vendor.updater.update_flow`: `UpdateFlow(window, button: QToolButton, toast: Callable[[str], None], app: AppIdentity, version: str, app_dir=None, frozen=None, updater=None)` with `.start()` and `.check_now()`, plus `ask(window, *, title, body, verb) -> bool`.
  - `app.vendor.updater.relaunch`: `_reset()` (for tests only).

- [ ] **Step 1: Copy the tests and point them at the vendored package**

Copy the three test files. In each one, `from shared import X` becomes `from app.vendor.updater import X`, and `from shared.updater import ...` becomes `from app.vendor.updater.updater import ...`. Replace pytest-qt:
- `qtbot.addWidget(window)`: delete the line. Each test or fixture already holds `window` in a local, which keeps it alive. Call `_app()` first.
- The `qapp` fixture argument: remove it and call `_app()` in the body.
- `with qtbot.waitSignal(sig, timeout=3000) as blocker: X` and then `blocker.args`: becomes `args = _wait(sig, lambda: X)`, then assert on `args`.

Add these helpers to the top of `tests/test_update_flow.py`. Put only `_app` in `tests/test_updater.py`.

```python
def _app():
    return QApplication.instance() or QApplication([])


def _wait(signal, action, timeout_s=3.0):
    got = []
    signal.connect(lambda *args: got.append(list(args)))
    action()
    deadline = time.monotonic() + timeout_s
    while not got and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert got, "signal not emitted"
    return got[0]
```

Fulfilment's `conftest.py` resets `relaunch` after every test (autouse). Add the same to `tests/test_updater.py` and `tests/test_update_flow.py`:

```python
@pytest.fixture(autouse=True)
def _reset_relaunch():
    yield
    relaunch._reset()
```

Swap the test identity for barcode_tool's names: `AppIdentity("owner/repo", "BarcodeTool", "BarcodeTool.exe")`. Then fix every test string and path derived from `FulfilmentTool` (zip names, exe names, `app_dir` folder names) to match.

- [ ] **Step 2: Run them and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_updater.py tests/test_update_flow.py tests/test_relaunch.py`
Expected: collection errors, `No module named 'app.vendor'`.

- [ ] **Step 3: Copy the modules and apply the listed edits only**

`mkdir -p app/vendor/updater`, create the two empty `__init__.py`, then `cp $F/shared/{updater,update_flow,relaunch}.py app/vendor/updater/`. The edits:
- `updater.py`: `from shared import relaunch` → `from . import relaunch`. `from shared.i18n import N_` → `from .i18n import N_`.
- `update_flow.py`: `from shared.i18n import _` → `from .i18n import _`. `from shared.updater import (...)` → `from .updater import (...)`. Delete the `ConfirmDialog` and `icon` imports. Delete the two lines `if button.icon().isNull(): ...` / `button.setIcon(icon("download"))`. Replace the body of `ask()` with a `QMessageBox`: `QMessageBox.Question` icon, `title`, `body`, a `QMessageBox.Cancel` button, and `box.addButton(verb, QMessageBox.AcceptRole)`. Return `box.exec()` then `box.clickedButton() is accept_button`. Drop `QDialog` from the imports if nothing else uses it. Add `# noqa: BLE001` to `except Exception as exc:  # a thread must report, not die`.
- `relaunch.py`: no change.
- `i18n.py` (new):

```python
"""Identity stand-in for Fulfilment's shared/i18n.py: English only, no catalogue."""


def N_(text: str) -> str:
    return text


def _(text: str, **values) -> str:
    return text.format(**values) if values else text
```

- `SYNCED_FROM` (new, plain text). Line 1, exactly:
  `cognitiveghost/shopify-fulfillment-tool@dc3ae8692e82ae020fe1f01e7f8f4db26756c4bf shared/updater.py shared/update_flow.py shared/relaunch.py`
  Then a blank line and one `- ` line per edit above (relative imports, the i18n shim, `ask()` on QMessageBox, the icon removed, `noqa: BLE001`). End with one line saying how to resync: copy the three files again and reapply these edits.

- [ ] **Step 4: Run the tests and lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_updater.py tests/test_update_flow.py tests/test_relaunch.py && .venv/bin/ruff check --fix app/vendor tests/test_updater.py tests/test_update_flow.py tests/test_relaunch.py && .venv/bin/ruff check .`
Expected: all pass, ruff clean. `--fix` only reorders imports.

- [ ] **Step 5: Show the vendored diff is only the listed edits**

Run: `for f in updater update_flow relaunch; do diff $F/shared/$f.py app/vendor/updater/$f.py; done`
Expected: only import lines, the `ask()` body, the two removed icon lines and the `noqa` comment. `relaunch.py` should show no diff.

- [ ] **Step 6: Windows-only failures (on the PR)**

If the PR's `windows-latest` CI job fails a copied test because the test assumes POSIX paths or permissions, add `@pytest.mark.skipif(os.name == "nt", reason="<why>")` to that test. Never edit `app/vendor/updater/*.py` to make it pass. A failure that points at a real Windows bug in the vendored code is a stop: report it.

- [ ] **Step 7: Commit**

`git add app/vendor tests/test_updater.py tests/test_update_flow.py tests/test_relaunch.py && git commit -m "Vendor Fulfilment's updater into app/vendor/updater"`

---

### Task 3: Wire the updater into `MainWindow`

**Files:**
- Modify: `app/ui/main_window.py` (`MainWindow.__init__`, around lines 57-127)
- Test: `tests/test_main_window.py` (it already has the autouse `_isolated_settings_dir` fixture and `_app()`)

**Interfaces:**
- Consumes: `app.__version__` (Task 1). `AppIdentity`, `UpdateFlow`, `newer_release` and `NOT_CHECKED` (Task 2).
- Produces: the module constant `app.ui.main_window.UPDATE_APP`, and the attributes `MainWindow._update_flow: UpdateFlow` and `MainWindow._update_button: QToolButton`.

- [ ] **Step 1: Write the failing tests in `tests/test_main_window.py`**

```python
from app import __version__
from app.vendor.updater.updater import NOT_CHECKED, newer_release


def test_title_shows_the_version():
    _app()
    window = MainWindow()
    assert window.windowTitle() == f"Barcode Label Generator {__version__}"


def test_update_button_sits_hidden_in_the_menu_bar_corner():
    _app()
    window = MainWindow()
    assert window.menuBar().cornerWidget() is window._update_button
    assert window._update_button.isHidden()


def test_check_for_updates_in_dev_explains_in_status_bar():
    _app()
    window = MainWindow()
    help_menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "Help")
    action = next(a for a in help_menu.actions() if a.text() == "Check for updates...")
    action.trigger()
    assert window.statusBar().currentMessage() == NOT_CHECKED


def test_update_identity_matches_release_assets():
    payload = {"tag_name": "0.2.0", "html_url": "page", "assets": [
        {"name": "BarcodeTool-0.2.0.zip", "browser_download_url": "z"},
        {"name": "BarcodeTool-0.2.0.zip.sha256", "browser_download_url": "s"},
    ]}
    release = newer_release(main_window_module.UPDATE_APP, "0.1.0", fetch=lambda url: payload)
    assert (release.zip_url, release.sha_url) == ("z", "s")
    old_style = {**payload, "assets": [
        {"name": "BarcodeTool-windows-0.2.0.zip", "browser_download_url": "z"}]}
    assert newer_release(main_window_module.UPDATE_APP, "0.1.0", fetch=lambda url: old_style) is None
    assert main_window_module.UPDATE_APP.repo == "cognitiveghost/barcode_tool"
    assert main_window_module.UPDATE_APP.exe_name == "BarcodeTool.exe"
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_main_window.py`
Expected: the four new tests fail (wrong title, no corner widget, no Help menu, no `UPDATE_APP`). The existing tests still pass.

- [ ] **Step 3: Implement in `app/ui/main_window.py`**

- Add the module constant `UPDATE_APP = AppIdentity("cognitiveghost/barcode_tool", "BarcodeTool", "BarcodeTool.exe")`.
- Set the title to `f"Barcode Label Generator {__version__}"`.
- After the View menu is built: create `self._update_button = QToolButton()` and `self.menuBar().setCornerWidget(self._update_button, Qt.Corner.TopRightCorner)`. Then create `self._update_flow = UpdateFlow(self, self._update_button, lambda text: self.statusBar().showMessage(text, 10000), UPDATE_APP, __version__)`.
- Add `help_menu = self.menuBar().addMenu("Help")` with `QAction("Check for updates...", self)` wired to `self._update_flow.check_now`.
- Make `self._update_flow.start()` the last line of `__init__`.

- [ ] **Step 4: Run the tests and lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_main_window.py tests/test_main.py && .venv/bin/ruff check .`
Expected: all pass, ruff clean.

- [ ] **Step 5: Run the full split suite**

Run both commands from Global Constraints.
Expected: both pass with 0 failures.

- [ ] **Step 6: Commit**

`git add app/ui/main_window.py tests/test_main_window.py && git commit -m "Show version, update button and Check for updates in MainWindow"`

---

### Task 4: Release workflow + `RELEASING.md`

**Files:**
- Rewrite: `.github/workflows/release.yml`
- Rewrite: `RELEASING.md`
- Reference (read only): `$F/.github/workflows/build_release.yml`, lines 60-224

**Interfaces:**
- Consumes: the `release_version.py` CLI (Task 1) and the asset names in Global Constraints.

- [ ] **Step 1: Rewrite `release.yml` to match the spec's "Release workflow" section**

The structure, in order:
- `name: Release`.
- `on: workflow_dispatch` with input `bump` (`type: choice`, options `patch`/`minor`/`major`, default `patch`).
- Top-level `permissions: contents: read`.
- Job `test`: keep today's job as is.
- Job `version`: `needs: test`, `if: github.ref == 'refs/heads/main'`, `outputs.version`. It checks out with `fetch-depth: 0` and `fetch-tags: true`, sets up Python 3.11, and has a step with `id: next` and `env: BUMP: ${{ inputs.bump }}` that runs `version=$(python scripts/release_version.py next "$BUMP")` and then `echo "version=$version" >> "$GITHUB_OUTPUT"`.
- Job `build-windows`: `needs: version`, `env: VERSION: ${{ needs.version.outputs.version }}`. Keep today's checkout, Python, Pango and pip steps. Add a step `python scripts/release_version.py stamp app/__init__.py $env:VERSION` before PyInstaller. Keep the PyInstaller command byte for byte. In "Bundle GTK DLLs", add `Copy-Item -Recurse -Path "C:\msys64\mingw64\etc" -Destination "dist\BarcodeTool\gtk-dlls\etc"` after the `bin` copy. Zip with `Compress-Archive -Path "dist\BarcodeTool\*" -DestinationPath "BarcodeTool-$env:VERSION.zip"`. Upload with `actions/upload-artifact@v7` (`name: bundle`, `path: BarcodeTool-*.zip`, `compression-level: 0`).
- Job `release`: `needs: [version, build-windows]`, ubuntu, `permissions` `contents: write`, `id-token: write`, `attestations: write`, and `env VERSION`. Steps: `actions/download-artifact@v8` (`name: bundle`), then `sha256sum "BarcodeTool-$VERSION.zip" > "BarcodeTool-$VERSION.zip.sha256"`, then `actions/attest-build-provenance@v4` with `subject-path: BarcodeTool-${{ needs.version.outputs.version }}.zip`, then `gh release create "$VERSION" "BarcodeTool-$VERSION.zip" "BarcodeTool-$VERSION.zip.sha256" --repo "$GITHUB_REPOSITORY" --target "$GITHUB_SHA" --title "$VERSION" --generate-notes --latest` with `GH_TOKEN: ${{ github.token }}`.
- Delete `build-linux` and every `github.event.release` reference.
- Keep one short comment on each non-obvious step, copied or adapted from Fulfilment's: why the release step runs last, and why there is no zip re-compression.

- [ ] **Step 2: Check the workflow parses and has the right shape**

Run:
```bash
python3 -c "
import yaml; w = yaml.safe_load(open('.github/workflows/release.yml'))
on = w[True]; assert list(on) == ['workflow_dispatch'], on
assert on['workflow_dispatch']['inputs']['bump']['options'] == ['patch', 'minor', 'major']
assert list(w['jobs']) == ['test', 'version', 'build-windows', 'release'], list(w['jobs'])
assert w['jobs']['version']['if'] == \"github.ref == 'refs/heads/main'\"
t = open('.github/workflows/release.yml').read()
assert 'build-linux' not in t and 'tar.gz' not in t
assert 'github.event.release' not in t and 'stamp app/__init__.py' in t
print('ok')"
```
Expected: `ok`.

- [ ] **Step 3: Rewrite `RELEASING.md` to match the spec's "`RELEASING.md` (rewritten)" section**

The sections are: "Cutting a release" (the button path, what the tag and `__version__` mean, and never make tags or releases by hand), "First release and alpha PCs" (`bump=minor` → `0.1.0`, the one manual install, and no user data lost), "Updates", and "Known limitation" (keep today's paragraph word for word). Also mention `gh attestation verify BarcodeTool-<ver>.zip -R cognitiveghost/barcode_tool`. Delete the Linux runtime section.

- [ ] **Step 4: Commit**

`git add .github/workflows/release.yml RELEASING.md && git commit -m "Release button: workflow_dispatch release, Windows only"`

The workflow itself first runs when the owner presses the button after the merge. Stage C cannot run it from a feature branch (the `version` job is main-only). The PR description must say so.
