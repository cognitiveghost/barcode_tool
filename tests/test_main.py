import os
import sys
from pathlib import Path

import app.main as main_module


def test_configure_windows_fontconfig_env_noop_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("FONTCONFIG_PATH", raising=False)

    main_module.configure_windows_fontconfig_env()

    assert "FONTCONFIG_PATH" not in os.environ


def test_configure_windows_fontconfig_env_noop_when_already_set(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("FONTCONFIG_PATH", "/already/set")

    main_module.configure_windows_fontconfig_env()

    assert os.environ["FONTCONFIG_PATH"] == "/already/set"


def test_configure_windows_fontconfig_env_noop_when_no_candidate_exists(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("FONTCONFIG_PATH", raising=False)
    monkeypatch.setattr(main_module, "_WINDOWS_GTK3_FONTCONFIG_CANDIDATES", (r"Z:\nowhere\etc\fonts",))

    main_module.configure_windows_fontconfig_env()

    assert "FONTCONFIG_PATH" not in os.environ


def test_configure_windows_fontconfig_env_uses_first_candidate_with_a_real_fonts_conf(
    monkeypatch, tmp_path
):
    fonts_dir = tmp_path / "etc" / "fonts"
    fonts_dir.mkdir(parents=True)
    (fonts_dir / "fonts.conf").write_text("<fontconfig/>")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("FONTCONFIG_PATH", raising=False)
    monkeypatch.setattr(
        main_module,
        "_WINDOWS_GTK3_FONTCONFIG_CANDIDATES",
        (r"Z:\nowhere\etc\fonts", str(fonts_dir)),
    )

    main_module.configure_windows_fontconfig_env()

    assert os.environ["FONTCONFIG_PATH"] == str(fonts_dir)


def test_configure_windows_fontconfig_env_checks_frozen_gtk_dlls_dir_first(monkeypatch, tmp_path):
    fake_executable = tmp_path / "BarcodeTool" / "BarcodeTool.exe"
    fake_executable.parent.mkdir(parents=True)
    bundled_fonts = fake_executable.parent / "gtk-dlls" / "etc" / "fonts"
    bundled_fonts.mkdir(parents=True)
    (bundled_fonts / "fonts.conf").write_text("<fontconfig/>")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_executable))
    monkeypatch.delenv("FONTCONFIG_PATH", raising=False)
    monkeypatch.setattr(main_module, "_WINDOWS_GTK3_FONTCONFIG_CANDIDATES", ())

    main_module.configure_windows_fontconfig_env()

    assert os.environ["FONTCONFIG_PATH"] == str(bundled_fonts)


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
