"""Shared pytest fixtures for the DesktopMate test suite.

The app keeps its settings in a single JSON file next to the executable
(``text_list_data.json``).  Tests must never touch the real file, so this
fixture points ``DesktopMate.DATA_PATH`` at a throwaway directory and cleans
it up afterwards.
"""

import importlib
import os
import sys

import pytest

# Qt must run headless on CI / in a terminal without a display.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def qt_app():
    """A single QApplication for the whole session (Qt allows only one)."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def desktop_mate(tmp_path, qt_app, monkeypatch):
    """Import the app module with DATA_PATH redirected into tmp_path."""
    module = importlib.import_module("DesktopMate")
    monkeypatch.setattr(module, "DATA_PATH", str(tmp_path / "text_list_data.json"))
    return module


@pytest.fixture
def app_window(desktop_mate):
    """A TextListApp instance wired to the redirected DATA_PATH."""
    window = desktop_mate.TextListApp()
    yield window
    window.close()
    window.deleteLater()
