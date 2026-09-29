"""Platform startup helpers remain safe while assigning Planacity's Windows identity."""

from types import SimpleNamespace

import planacity.main as entry


class FakeSetter:
    def __init__(self) -> None:
        self.argtypes: list[object] | None = None
        self.restype: object | None = None
        self.calls: list[str] = []

    def __call__(self, app_id: str) -> int:
        self.calls.append(app_id)
        return 0


def test_windows_runtime_identity_uses_stable_app_id(monkeypatch) -> None:
    setter = FakeSetter()
    windll = SimpleNamespace(
        shell32=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=setter)
    )
    monkeypatch.setattr(entry.sys, "platform", "win32")
    monkeypatch.setattr(entry.ctypes, "windll", windll, raising=False)

    entry._set_windows_runtime_identity()

    assert setter.calls == [entry.WINDOWS_APP_ID]
    assert setter.argtypes == [entry.ctypes.c_wchar_p]
    assert setter.restype is entry.ctypes.c_long


def test_runtime_identity_is_no_op_off_windows(monkeypatch) -> None:
    setter = FakeSetter()
    windll = SimpleNamespace(
        shell32=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=setter)
    )
    monkeypatch.setattr(entry.sys, "platform", "linux")
    monkeypatch.setattr(entry.ctypes, "windll", windll, raising=False)

    entry._set_windows_runtime_identity()

    assert setter.calls == []


def test_missing_windows_shell_api_does_not_prevent_startup(monkeypatch) -> None:
    monkeypatch.setattr(entry.sys, "platform", "win32")
    monkeypatch.setattr(entry.ctypes, "windll", object(), raising=False)

    entry._set_windows_runtime_identity()
