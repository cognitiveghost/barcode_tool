# Task 2: Release button + in-app updater (Windows only)

Date: 2026-10-28. Parent spec, approved by the owner:
`docs/superpowers/specs/2026-10-28-thermal-templates-builder-updates-design.md`, Task 2. This note
pins down what the parent left to the builder. Everything here is **(Claude's call)** unless it
is marked **(owner)**, and it all stays inside what the parent decided.

## Facts checked against the code (2026-10-28)

- Source: `cognitiveghost/shopify-fulfillment-tool` at `dc3ae8692e82ae020fe1f01e7f8f4db26756c4bf`
  (main). The updater files were last changed in `3cb6d2dd` (2026-10-16).
- `shared/updater.py` (234 lines) uses only the stdlib (urllib, no `requests`) plus
  `shared.relaunch` and `shared.i18n.N_`.
- `shared/relaunch.py` (84 lines) uses only PySide6 and copies unchanged.
- `shared/update_flow.py` (204 lines) also imports `shared.components.confirm_dialog.ConfirmDialog`
  (used only in `ask()`, which would pull in `shared.theme`) and `shared.icons.icon` (one call).
  Both are replaced (see below), so nothing else from `shared/` is needed.
- The asset name is `f"{asset_prefix}-{version}.zip"` (`updater.py:116`), so `asset_prefix` is
  `"BarcodeTool"`, not `"BarcodeTool-"`. The `.sha256` file is that name plus `.sha256`.
- The `.cmd` swap script is written by `updater.swap_script`/`arm_install`, not by `relaunch.py`.
  It runs on `QCoreApplication.aboutToQuit`, so the app must quit when the main window closes.
  It does today (one top-level window, default `quitOnLastWindowClosed`).
- `scripts/release_version.py` (60 lines, stdlib) has no repo-specific constants. With the
  `alpha-0.0.x` tags it starts from `0.0.0`, so `bump=minor` gives `0.1.0` **(owner)**.
- All the copied code passes ruff with `--target-version py311` (CI runs Python 3.11). Locally
  ruff reports `I001` (import order, fixed by `--fix` after the imports are rewritten) and
  `BLE001` at `update_flow.py:66` (the thread's catch-all, which is intended: add
  `# noqa: BLE001`).
- Fulfilment's tests use pytest-qt (`qtbot`, `qapp`), which barcode_tool does not have. Only a
  few lines need it, so the copies use plain `QApplication` instead and no new dependency is added.
- Fulfilment runs these tests on Ubuntu only. barcode_tool's CI also runs Windows.

## Vendored updater: `app/vendor/updater/`

```
app/vendor/__init__.py           empty
app/vendor/updater/__init__.py   empty
app/vendor/updater/SYNCED_FROM   provenance + list of local edits
app/vendor/updater/i18n.py       identity shim: N_ and _
app/vendor/updater/relaunch.py   verbatim (docstring/comments untouched)
app/vendor/updater/updater.py    imports rewritten only
app/vendor/updater/update_flow.py imports rewritten, ask() and the icon line replaced
```

- Imports become relative (`from . import relaunch`, `from .i18n import N_`,
  `from .updater import (...)`), so the package is self-contained.
- `i18n.py`: `N_(text)` returns `text`. `_(text, **values)` returns `text.format(**values)` if
  `values` else `text`. Same behaviour as Fulfilment in English.
- `update_flow.ask()` uses a `QMessageBox` (Question icon, a Cancel button, plus an accept button
  labelled `verb`) and returns whether the accept button was clicked. Same signature, so the
  copied tests still monkeypatch it.
- Delete the two lines `if button.icon().isNull(): button.setIcon(icon("download"))` and the
  `icon` import. The button is text-only.
- `SYNCED_FROM` file, line 1:
  `cognitiveghost/shopify-fulfillment-tool@dc3ae8692e82ae020fe1f01e7f8f4db26756c4bf shared/updater.py shared/update_flow.py shared/relaunch.py`
  and then one line per local edit (relative imports, i18n shim, `ask()` on QMessageBox, icon
  removed, `noqa: BLE001`). To resync: copy the three files again and reapply those edits.
- Tests are copied to `tests/test_updater.py`, `tests/test_update_flow.py`,
  `tests/test_relaunch.py`. Imports point at `app.vendor.updater`. `qtbot.addWidget` is dropped
  and the window is kept by the fixture. `qapp` becomes `QApplication.instance() or QApplication([])`.
  `qtbot.waitSignal` becomes a small `_wait(signal)` helper that pumps `processEvents()` for up to
  3 s. The app identity in tests becomes `AppIdentity("owner/repo", "BarcodeTool",
  "BarcodeTool.exe")`, and expected strings change to match. If a copied test fails on Windows
  CI only because it assumes POSIX, mark it `skipif(os.name == "nt", reason=...)`. Do not
  change vendored code to make it pass.

## Wiring in `MainWindow`

- `app/__init__.py`: `__version__ = "dev"`. Only the release workflow stamps it. Never edit it
  by hand.
- Window title: `f"Barcode Label Generator {__version__}"`, the same pattern as Fulfilment's
  `Fulfilment Tool {version}`. Dev builds show "dev". There is no separate About box (YAGNI).
- `UPDATE_APP = AppIdentity("cognitiveghost/barcode_tool", "BarcodeTool", "BarcodeTool.exe")`,
  a module constant in `app/ui/main_window.py`.
- The update button is a `QToolButton` placed as the menu bar's top-right corner widget
  (`menuBar().setCornerWidget(button, Qt.TopRightCorner)`). `UpdateFlow` hides it until a newer
  release exists. It then reads "Update to X". This is the parent spec's non-blocking prompt:
  nothing modal opens at startup.
- Toast: `lambda text: self.statusBar().showMessage(text, 10000)`. A status bar appears at the
  bottom of the window.
- A new **Help** menu (after View) has a single item, `Check for updates...` (ASCII dots, like
  `Settings...`), connected to `UpdateFlow.check_now`.
- `self._update_flow.start()` runs at the end of `MainWindow.__init__`. In a dev build (not
  frozen, or version "dev") it does nothing, so tests never reach the network.
- Behaviour is unchanged from Fulfilment. The startup check is silent and runs on a daemon
  thread. A manual check reports through the status bar. Clicking the button asks for
  confirmation, downloads, verifies the `.sha256`, extracts to `BarcodeTool.update/`, arms the
  `.cmd`, and closes the window. The script swaps the folders after exit and restarts the app.
  A swap that fails is reported on the next start.

## Release workflow: `.github/workflows/release.yml` (rewritten in place)

- Trigger: `workflow_dispatch` only, with input `bump` (choice patch/minor/major, default patch).
  The `release: published` trigger and the Linux build are removed **(owner)**. There is no
  `prerelease` input (YAGNI).
- Top-level `permissions: contents: read`.
- `test` (ubuntu): the existing split test run (font-swap test alone, then the rest), unchanged.
- `version` (ubuntu, `needs: test`, `if: github.ref == 'refs/heads/main'`): checks out with
  `fetch-depth: 0` and `fetch-tags: true`, runs `python scripts/release_version.py next "$BUMP"`,
  and writes the result to `$GITHUB_OUTPUT`.
- `build-windows` (`needs: version`): the existing Pango and PyInstaller steps, unchanged, plus
  `release_version.py stamp app/__init__.py $env:VERSION` before PyInstaller. GTK bundling also
  copies `C:\msys64\mingw64\etc` to `gtk-dlls\etc`, as Fulfilment does: `app/main.py` already
  looks for `gtk-dlls/etc/fonts/fonts.conf` and never finds it today. It then runs
  `Compress-Archive -Path "dist\BarcodeTool\*" -DestinationPath "BarcodeTool-$env:VERSION.zip"`
  (the exe at the zip root, which `stage()` requires) and `actions/upload-artifact@v7`
  (`compression-level: 0`).
- `release` (ubuntu, `needs: [version, build-windows]`, `contents: write`, `id-token: write`,
  `attestations: write`): runs `actions/download-artifact@v8` and
  `sha256sum BarcodeTool-$VERSION.zip > BarcodeTool-$VERSION.zip.sha256`. It then runs
  `actions/attest-build-provenance@v4` (kept from Fulfilment: four lines, and it lets someone
  check a downloaded zip by hand with `gh attestation verify`). Last comes
  `gh release create "$VERSION" <zip> <sha256> --repo "$GITHUB_REPOSITORY" --target "$GITHUB_SHA" --title "$VERSION" --generate-notes --latest`.
  The release step runs last, so a failed build leaves no tag behind.
- `ci.yml` is unchanged: Linux and Windows tests plus lint.

## `RELEASING.md` (rewritten)

It covers how to release: Actions → Release → Run workflow on `main` → pick the bump. The tag is
the version. Never create tags or releases by hand. Never edit `__version__`.

It covers the first release: `bump=minor` → `0.1.0`. PCs on `alpha-0.0.x` builds have no updater
and need **one manual install**: download `BarcodeTool-0.1.0.zip`, close the app, and replace the
old folder with the unzipped one. Settings live in `~/.barcode_tool/` and QSettings, and
templates live in the shared folder, so no user data is lost **(owner)**.

It covers updates from then on: the app checks on start. "Update to X" appears top-right, or use
Help → Check for updates....

The "Known limitation" paragraph about bundling all of `mingw64/bin` stays. The Linux section
goes.

## Non-goals

No Linux build, no BG translation (the shim is identity), no full `shared/` sync, no About
dialog, no prerelease channel, and no new dependencies.

## Left to the builder

The exact wording of the SYNCED_FROM edit lines and of the RELEASING.md prose. Any small test
adaptations needed so the copied tests pass on both CI platforms.
