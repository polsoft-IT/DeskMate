"""Tests for the module-level helpers in ``desktop_launcher.py``.

Only the non-GUI helpers are exercised: ``load_launcher_entries``,
``launcher_entries_file``, ``_open_with_os`` and ``launch_path``.  The GUI
classes require a real Qt event loop and are not covered here.
"""

import json

import pytest

import desktop_launcher


# --------------------------------------------------------------------------
# Store location
# --------------------------------------------------------------------------

def test_entries_file_points_next_to_module(monkeypatch):
    monkeypatch.delattr(desktop_launcher.sys, "frozen", raising=False)
    path = desktop_launcher.launcher_entries_file()

    assert path.endswith("desktop_launcher_data.json")


def test_entries_file_uses_executable_dir_when_frozen(monkeypatch):
    monkeypatch.setattr(desktop_launcher.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        desktop_launcher.sys, "executable", r"C:\apps\launcher.exe", raising=False
    )

    path = desktop_launcher.launcher_entries_file()

    assert path == r"C:\apps\desktop_launcher_data.json"


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def test_load_returns_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        desktop_launcher,
        "launcher_entries_file",
        lambda: str(tmp_path / "absent.json"),
    )

    assert desktop_launcher.load_launcher_entries() == []


def test_load_normalises_entries(tmp_path, monkeypatch):
    store = tmp_path / "entries.json"
    store.write_text(
        json.dumps(
            [
                {"path": r"C:\apps\calc.exe", "name": "Kalkulator", "icon_path": "i.png"},
                {"path": r"C:\apps\notes.txt"},
                {"path": r"C:\apps\docs", "is_dir": True},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        desktop_launcher, "launcher_entries_file", lambda: str(store)
    )

    entries = desktop_launcher.load_launcher_entries()

    assert len(entries) == 3
    assert entries[0] == {
        "path": r"C:\apps\calc.exe",
        "name": "Kalkulator",
        "icon_path": "i.png",
        "is_dir": False,
    }
    # A missing name falls back to the file name.
    assert entries[1]["name"] == "notes.txt"
    assert entries[2]["is_dir"] is True


def test_load_skips_invalid_entries(tmp_path, monkeypatch):
    store = tmp_path / "entries.json"
    store.write_text(
        json.dumps(
            [
                "not a dict",
                {"name": "no path"},
                {"path": ""},
                None,
                {"path": r"C:\apps\ok.exe"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        desktop_launcher, "launcher_entries_file", lambda: str(store)
    )

    entries = desktop_launcher.load_launcher_entries()

    assert [e["path"] for e in entries] == [r"C:\apps\ok.exe"]


@pytest.mark.parametrize("payload", ["{not json", "", "null", '"text"', "42"])
def test_load_returns_empty_on_malformed_json(tmp_path, monkeypatch, payload):
    store = tmp_path / "entries.json"
    store.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(
        desktop_launcher, "launcher_entries_file", lambda: str(store)
    )

    assert desktop_launcher.load_launcher_entries() == []


def test_load_returns_empty_when_not_a_list(tmp_path, monkeypatch):
    store = tmp_path / "entries.json"
    store.write_text(json.dumps({"path": "x"}), encoding="utf-8")
    monkeypatch.setattr(
        desktop_launcher, "launcher_entries_file", lambda: str(store)
    )

    assert desktop_launcher.load_launcher_entries() == []


# --------------------------------------------------------------------------
# Launching
# --------------------------------------------------------------------------

def test_launch_path_ignores_missing_path(monkeypatch):
    called = []
    monkeypatch.setattr(desktop_launcher, "_open_with_os", called.append)

    desktop_launcher.launch_path("")
    desktop_launcher.launch_path(str(tmp_path_missing := "definitely_missing_file_xyz"))

    assert called == []


def test_launch_path_opens_existing_path(tmp_path, monkeypatch):
    target = tmp_path / "app.exe"
    target.write_text("", encoding="utf-8")

    called = []
    monkeypatch.setattr(desktop_launcher, "_open_with_os", called.append)

    desktop_launcher.launch_path(str(target))

    assert called == [str(target)]


# --------------------------------------------------------------------------
# Size formatting
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "size,expected",
    [
        (0, "0 B"),
        (1023, "1023 B"),
        (1024, "1.0 kB"),
        (1536, "1.5 kB"),
        (1024 * 1024 - 1, "1024.0 kB"),
        (1024 * 1024, "1.00 MB"),
        (5 * 1024 * 1024, "5.00 MB"),
    ],
)
def test_format_size_boundaries(size, expected):
    assert desktop_launcher._format_size(size) == expected


# --------------------------------------------------------------------------
# Properties rows
# --------------------------------------------------------------------------

def test_properties_rows_report_missing_file(tmp_path):
    missing = tmp_path / "gone.txt"
    rows = desktop_launcher._properties_info_rows(str(missing), "Gone")
    values = dict(rows)

    assert values["Nazwa:"] == "Gone"
    assert values["Typ:"] == "Nieznany"
    assert "Stan:" in values
    # No size/mtime rows for a file that does not exist.
    assert "Rozmiar:" not in values
    assert "Zmodyfikowano:" not in values


def test_properties_rows_for_existing_file(tmp_path):
    target = tmp_path / "data.txt"
    target.write_text("hello", encoding="utf-8")
    values = dict(desktop_launcher._properties_info_rows(str(target), ""))

    assert values["Typ:"] == "TXT - plik"
    assert values["Nazwa:"] == "data.txt"
    assert values["Rozmiar:"] == "5 B"
    assert "Zmodyfikowano:" in values
    assert "Stan:" not in values


def test_properties_rows_for_directory(tmp_path):
    values = dict(desktop_launcher._properties_info_rows(str(tmp_path), "Docs"))

    assert values["Typ:"] == "Katalog"
    assert values["Lokalizacja:"] == str(tmp_path)
    assert "Rozmiar:" not in values


def test_open_with_os_swallows_oserror(monkeypatch):
    def boom(path):
        raise OSError("no association")

    monkeypatch.setattr(desktop_launcher.os, "startfile", boom, raising=False)

    # Must not raise even when the OS refuses to open the file.
    desktop_launcher._open_with_os(r"C:\apps\broken.exe")


def test_open_with_os_ignores_empty_path(monkeypatch):
    called = []
    monkeypatch.setattr(
        desktop_launcher.os, "startfile", called.append, raising=False
    )

    desktop_launcher._open_with_os("")

    assert called == []
