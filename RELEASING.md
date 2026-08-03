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
