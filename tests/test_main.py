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
