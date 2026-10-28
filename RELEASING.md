# Cutting a release

Actions > **Release** > Run workflow, on `main`. Pick `bump` (patch, minor or
major). It runs the tests, picks the next version from the existing tags,
stamps it into `app/__init__.py` (`__version__`, shown in the window title),
builds the Windows bundle and publishes a GitHub Release tagged with that
version (no `v` prefix). It attaches:

- `BarcodeTool-<ver>.zip`: unzip, run `BarcodeTool.exe`.
- `BarcodeTool-<ver>.zip.sha256`: checked by the in-app updater.

Never create tags or releases by hand: the workflow derives the next version
from the tags it made, and the build only runs from the button. The workflow
cannot run from a feature branch (the `version` job is main-only).

Verify provenance of a download:
`gh attestation verify BarcodeTool-<ver>.zip -R cognitiveghost/barcode_tool`.

## First release and alpha PCs

Old `alpha-*` tags are ignored when picking the version, so the first run
with `bump=minor` gives `0.1.0`. PCs on an alpha build need one manual
install of that zip (the alpha has no updater). User data lives outside the
install folder, so nothing is lost.

## Updates

Release builds check GitHub for a newer release at startup, and Help >
Check for updates... does it on demand. The updater only offers
`BarcodeTool-<ver>.zip` with a matching `.sha256`; it verifies the checksum,
swaps the install folder and relaunches. Dev runs (`__version__ == "dev"`)
never check at startup.

## Known limitation

The Windows build bundles the entire MSYS2 `mingw64/bin` directory
(everything `pacman` installed for the Pango package tree) into
`gtk-dlls/`, rather than a hand-picked minimal DLL set — a bigger zip than
strictly necessary, but correct without manually tracing the dependency
graph. `mingw64/etc` is copied to `gtk-dlls/etc` too (`app/main.py` points
fontconfig at `gtk-dlls/etc/fonts`). Revisit if artifact size becomes a problem.
