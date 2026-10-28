import time
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QToolButton, QWidget

from app.vendor.updater import relaunch, update_flow, updater
from app.vendor.updater.updater import AppIdentity, Release

APP = AppIdentity("owner/repo", "BarcodeTool", "BarcodeTool.exe")


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


@pytest.fixture(autouse=True)
def _reset_relaunch():
    yield
    relaunch._reset()


R = Release("2.4.0", "https://page", "zip", "sha")


class FakeUpdater(QObject):
    available = Signal(object)
    upToDate = Signal(str)
    progress = Signal(int)
    staged = Signal(object)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self.checks, self.installs = [], []

    def check(self, manual):
        self.checks.append(manual)

    def install(self, release):
        self.installs.append(release)


@pytest.fixture
def flow(tmp_path, monkeypatch):
    _app()
    relaunch._reset()
    window = QWidget()
    button = QToolButton(window)
    toasts, asked = [], []
    monkeypatch.setattr(update_flow, "ask", lambda w, **kw: asked.append(kw) or True)
    app_dir = tmp_path / "BarcodeTool"
    app_dir.mkdir()
    fake = FakeUpdater()
    f = update_flow.UpdateFlow(window, button, toasts.append, APP, "2.3.1",
                               app_dir=app_dir, frozen=True, updater=fake)
    yield f, fake, button, toasts, asked, app_dir, window
    relaunch._reset()


def test_start_checks_silently_and_hides_the_button(flow):
    f, fake, button, _toasts, *_ = flow
    f.start()
    assert fake.checks == [False]
    assert button.isHidden()


def test_start_reports_a_failed_swap_first(flow):
    f, _fake, _button, toasts, _a, app_dir, _w = flow
    staged = updater.staging_dir(app_dir)
    staged.mkdir()
    (staged / "failed.txt").write_text("2.4.0")
    f.start()
    assert "2.4.0" in toasts[0] and "another PC" in toasts[0]


def test_dev_builds_never_check(tmp_path):
    _app()
    fake = FakeUpdater()
    window = QWidget()
    f = update_flow.UpdateFlow(window, QToolButton(window), [].append, APP, "dev",
                               app_dir=tmp_path, frozen=True, updater=fake)
    f.start()
    assert fake.checks == []
    toasts = []
    f._toast = toasts.append
    f.check_now()
    assert toasts == ["Updates are checked only in the released app."]


def test_available_shows_the_button(flow):
    f, fake, button, toasts, *_ = flow
    f.start()
    fake.available.emit(R)
    assert not button.isHidden()
    assert button.text() == "Update to 2.4.0"
    assert toasts == []


def test_manual_check_toasts_each_outcome(flow):
    f, fake, _button, toasts, *_ = flow
    f.check_now()
    assert fake.checks == [True]
    fake.upToDate.emit("2.3.1")
    fake.failed.emit("Could not reach GitHub: timed out")
    assert toasts == ["You have the latest version (2.3.1)",
                      "Couldn't check for updates: Could not reach GitHub: timed out"]


def test_a_silent_check_failure_says_nothing(flow):
    f, fake, button, toasts, *_ = flow
    f.start()
    fake.failed.emit("Could not reach GitHub: 403")
    assert toasts == [] and button.isHidden()


def test_click_confirms_then_installs_with_progress(flow):
    f, fake, button, _toasts, asked, *_ = flow
    f.start()
    fake.available.emit(R)
    button.click()
    assert asked[0]["verb"] == "Update and restart"
    assert "https://page" in asked[0]["body"]
    assert fake.installs == [R]
    assert not button.isEnabled()
    fake.progress.emit(42)
    assert button.text() == "Downloading… 42%"


def test_staged_arms_the_swap_and_closes(flow):
    f, fake, button, _toasts, _asked, app_dir, window = flow
    window.show()
    f.start()
    fake.available.emit(R)
    button.click()
    updater.staging_dir(app_dir).mkdir()
    fake.staged.emit(R)
    assert relaunch.pending().startswith("cmd /d /s /c")
    assert button.toolTip() == "Update installs when you close the app"
    assert not window.isVisible()


def test_a_vetoed_close_after_staging_toasts_the_full_text(flow, monkeypatch):
    f, fake, button, toasts, _asked, app_dir, window = flow
    monkeypatch.setattr(window, "close", lambda: False)
    f.start()
    fake.available.emit(R)
    button.click()
    updater.staging_dir(app_dir).mkdir()
    fake.staged.emit(R)
    assert toasts[-1] == "Update installs when you close the app"


def test_arming_failure_restores_the_offer(flow, monkeypatch):
    f, fake, button, toasts, _asked, app_dir, _window = flow
    def boom(*a):
        raise OSError("read-only")
    monkeypatch.setattr(update_flow, "arm_install", boom)
    f.start()
    fake.available.emit(R)
    button.click()
    updater.staging_dir(app_dir).mkdir()
    fake.staged.emit(R)
    assert toasts[-1] == "read-only"
    assert not updater.staging_dir(app_dir).exists()
    assert button.isEnabled() and button.text() == "Update to 2.4.0"
    assert relaunch.pending() is None


def test_install_failure_restores_the_button(flow):
    f, fake, button, toasts, *_ = flow
    f.start()
    fake.available.emit(R)
    button.click()
    fake.failed.emit("The download is damaged (checksum mismatch).")
    assert toasts == ["The download is damaged (checksum mismatch)."]
    assert button.isEnabled() and button.text() == "Update to 2.4.0"


def test_a_blocked_copy_offers_the_release_page(tmp_path, monkeypatch):
    _app()
    fake = FakeUpdater()
    window = QWidget()
    asked, opened = [], []
    monkeypatch.setattr(update_flow, "ask", lambda w, **kw: asked.append(kw) or True)
    monkeypatch.setattr(update_flow.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    button = QToolButton(window)
    update_flow.UpdateFlow(window, button, [].append, APP, "2.3.1",
                          app_dir=tmp_path / "x", frozen=False, updater=fake)
    fake.available.emit(R)
    button.click()
    assert asked[0]["verb"] == "Open release page"
    assert opened == ["https://page"]
    assert fake.installs == []


def test_server_copy_warns_in_the_confirm(flow, monkeypatch):
    _f, fake, button, _toasts, asked, *_ = flow
    monkeypatch.setattr(update_flow, "is_server_copy", lambda p: True)
    fake.available.emit(R)
    button.click()
    assert "close it on every PC first" in asked[0]["body"]


def test_updater_thread_reports_through_signals(monkeypatch):
    _app()
    monkeypatch.setattr(update_flow, "newer_release", lambda app, current: R)
    real = update_flow.Updater(APP, "2.3.1", Path("/nowhere"))
    args = _wait(real.available, lambda: real.check(manual=False))
    assert args == [R]


def test_updater_thread_reports_errors_translated(monkeypatch):
    _app()

    def boom(app, current):
        raise updater.UpdateError(updater.NO_CONNECTION, detail="timed out")
    monkeypatch.setattr(update_flow, "newer_release", boom)
    real = update_flow.Updater(APP, "2.3.1", Path("/nowhere"))
    args = _wait(real.failed, lambda: real.check(manual=True))
    assert args == ["Could not reach GitHub: timed out"]


@pytest.mark.parametrize("pick_verb", [True, False])
def test_ask_returns_whether_the_verb_button_was_clicked(pick_verb):
    _app()

    def click():
        box = QApplication.activeModalWidget()
        verb = next(b for b in box.buttons() if b.text() == "Update")
        (verb if pick_verb else box.button(QMessageBox.Cancel)).click()

    QTimer.singleShot(0, click)
    assert update_flow.ask(None, title="t", body="b", verb="Update") is pick_verb
