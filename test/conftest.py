"""Pytest fixtures and hooks shared across the test suite.

QSettings is redirected at conftest import time (so zxlive's import-time
writes are sandboxed) and again per-test by an autouse fixture (so tests
that build fresh QSettings don't leak state to each other). Module-level
QSettings instances created during import keep using the session-scoped
path for their whole lifetime.

Qt's platform plugin defaults to ``offscreen`` so the suite doesn't open
real windows on the desktop. To watch a failing test interactively, clear
``QT_QPA_PLATFORM`` so Qt auto-detects the host's platform, e.g.,
``env -u QT_QPA_PLATFORM pytest test/test_mainwindow.py -k some_test``.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings  # noqa: E402


def _probe_default_path(fmt: QSettings.Format) -> str:
    """Probe Qt's default UserScope base path for ``fmt`` via a throwaway QSettings.

    Accepts three layouts and raises on anything else rather than silently
    restoring a wrong path:

    * ``<base>/<org>/<app>.ext`` (Linux, nested) -> ``<base>``
    * ``<base>/<app>.ext`` (Linux, flat) -> ``<base>``
    * ``<base>/<reverse-domain>.<app>.plist`` (macOS NativeFormat, e.g.
      ``com.org.app.plist``) -> ``<base>``
    """
    probe_org = "zxlive-conftest-probe-org"
    probe_app = "zxlive-conftest-probe-app"
    probe = QSettings(fmt, QSettings.Scope.UserScope, probe_org, probe_app)
    probe_path = Path(probe.fileName())

    if probe_path.stem == probe_app:
        if probe_path.parent.name == probe_org:
            return str(probe_path.parent.parent)
        return str(probe_path.parent)

    # macOS NativeFormat stores ``~/Library/Preferences/com.org.app.plist``,
    # where the reverse-domain stem ends with the application name and the
    # base path is simply the containing directory.
    if probe_path.stem.endswith(probe_app):
        return str(probe_path.parent)

    raise RuntimeError(
        f"Unable to derive QSettings base path for {fmt!r} from "
        f"{probe.fileName()!r}"
    )


# PySide6's ``QSettings(org, app)`` ignores ``setDefaultFormat`` and uses
# ``NativeFormat``, so redirect both formats to cover either choice.
_ORIGINAL_FORMAT = QSettings.defaultFormat()
_ORIGINAL_NATIVE_PATH = _probe_default_path(QSettings.Format.NativeFormat)
_ORIGINAL_INI_PATH = _probe_default_path(QSettings.Format.IniFormat)

_QSETTINGS_TMPDIR = tempfile.TemporaryDirectory(prefix="zxlive-test-qsettings-")


def _set_qsettings_paths(path: str) -> None:
    """Point both QSettings formats at ``path`` for UserScope."""
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope,
                      path)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      path)


QSettings.setDefaultFormat(QSettings.Format.IniFormat)
_set_qsettings_paths(_QSETTINGS_TMPDIR.name)


# On macOS, ``QSettings(org, app)`` uses ``NativeFormat`` (CFPreferences),
# which ignores both ``setDefaultFormat`` and ``setPath`` -- so the sandbox
# above never applies and tests would read and pollute the user's real
# preferences. Route the org/app and default constructors through the
# redirectable ``IniFormat`` instead, so the per-test sandbox holds on every
# platform. Subclassing (rather than swapping in a factory function) keeps
# ``isinstance`` checks, ``QSettings.Format``, and the rest of the API intact.
import PySide6.QtCore as _QtCore  # noqa: E402


class _SandboxedQSettings(QSettings):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if not args and not kwargs:
            super().__init__(QSettings.Format.IniFormat,
                             QSettings.Scope.UserScope, "zxlive", "zxlive")
        elif len(args) == 2 and all(isinstance(a, str) for a in args):
            super().__init__(QSettings.Format.IniFormat,
                             QSettings.Scope.UserScope, args[0], args[1])
        else:
            super().__init__(*args, **kwargs)


setattr(_QtCore, "QSettings", _SandboxedQSettings)


_exit_status: int = 0


@pytest.fixture(autouse=True)
def _isolated_qsettings(tmp_path: Path) -> Iterator[None]:
    """Redirect new QSettings instances to a per-test subdirectory."""
    _set_qsettings_paths(str(tmp_path))
    try:
        yield
    finally:
        _set_qsettings_paths(_QSETTINGS_TMPDIR.name)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    global _exit_status
    _exit_status = exitstatus


def pytest_unconfigure(config: pytest.Config) -> None:
    """Restore the original QSettings state, remove the temp directory,
    # then flush to exit cleanly while preserving the exit status."""
    QSettings.setDefaultFormat(_ORIGINAL_FORMAT)
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope,
                      _ORIGINAL_NATIVE_PATH)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      _ORIGINAL_INI_PATH)
    _QSETTINGS_TMPDIR.cleanup()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_status)
