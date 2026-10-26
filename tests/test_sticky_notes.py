"""Tests for ``StickyNotesManager`` persistence in ``sticky_notes.py``.

The GUI-heavy parts of the module are not exercised here.  Every test replaces
``StickyNotesManager._create_note`` with a lightweight in-memory fake so that
no real ``StickyNote`` window is built, and points the manager at ``tmp_path``
so the real ``sticky_notes_data.json`` is never touched.  ``conftest.py``
already provides the headless Qt environment (``QT_QPA_PLATFORM=offscreen``)
and the ``qt_app`` session fixture, which the manager needs for its
``pyqtSignal`` connections.

Covered: save/load round-trip, missing file, corrupt JSON, migration between
stores (including the failure path that must not switch ``_data_path``) and the
note bookkeeping slots ``_on_note_deleted`` / ``_on_note_closed``.
"""

import json

import pytest

from sticky_notes import StickyNotesManager


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

class FakeNote:
    """Stand-in for ``StickyNote`` with just the surface the manager uses."""

    def __init__(self, note_id, data=None):
        self.note_id = note_id
        self.data = dict(data or {})
        self.closed = False
        self.shown = False
        self.hidden = False

    def to_dict(self):
        return dict(self.data)

    def close(self):
        self.closed = True

    def show(self):
        self.shown = True

    def hide(self):
        self.hidden = True

    def update_language(self, lang):
        self.lang = lang


def make_note_data(**overrides):
    data = {
        "color": "#fff740",
        "width": 260,
        "height": 220,
        "x": 100,
        "y": 100,
        "on_top": True,
        "title": "Note 1",
    }
    data.update(overrides)
    return data


@pytest.fixture
def manager(tmp_path, qt_app, monkeypatch):
    """A ``StickyNotesManager`` whose note creation is faked and whose store
    lives in ``tmp_path``."""
    created = []

    def fake_create_note(self, note_id, data=None):
        note = FakeNote(note_id, data)
        note.shown = True
        created.append(note)
        self.notes[note.note_id] = note
        return note

    monkeypatch.setattr(StickyNotesManager, "_create_note", fake_create_note)
    mgr = StickyNotesManager(data_path=str(tmp_path / "notes.json"))
    mgr.created_notes = created
    return mgr


def read_store(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Path handling
# --------------------------------------------------------------------------

def test_set_data_path_creates_missing_folder(tmp_path, qt_app):
    nested = tmp_path / "deep" / "nested" / "notes.json"
    mgr = StickyNotesManager(data_path=str(nested))

    assert mgr.get_data_path() == str(nested)
    assert nested.parent.is_dir()


def test_set_data_path_falls_back_to_default(tmp_path, qt_app):
    mgr = StickyNotesManager(data_path=None)

    assert mgr.get_data_path().endswith("sticky_notes_data.json")


# --------------------------------------------------------------------------
# Round-trip
# --------------------------------------------------------------------------

def test_save_then_load_round_trip(manager, tmp_path):
    store = str(tmp_path / "notes.json")
    manager.notes["a"] = FakeNote("a", make_note_data(title="Alpha"))
    manager.save_notes()

    saved = read_store(store)
    assert saved["a"]["title"] == "Alpha"

    # Wipe the in-memory notes and reload from disk.
    manager.notes.clear()
    manager.load_notes()

    assert "a" in manager.notes
    assert manager.notes["a"].data["title"] == "Alpha"


def test_load_notes_ignores_missing_file(manager):
    # No store on disk yet -> no crash and no notes created.
    assert not manager.notes
    manager.load_notes()
    assert manager.notes == {}


def test_load_notes_creates_one_note_per_entry(manager, tmp_path):
    store = str(tmp_path / "notes.json")
    with open(store, "w", encoding="utf-8") as f:
        json.dump(
            {"n1": make_note_data(title="One"), "n2": make_note_data(title="Two")},
            f,
        )

    manager.load_notes()

    assert set(manager.notes) == {"n1", "n2"}


# --------------------------------------------------------------------------
# Corrupt JSON
# --------------------------------------------------------------------------

@pytest.mark.parametrize("payload", ["{not json", "", "[1, 2, 3]", "null", '"str"'])
def test_corrupt_store_does_not_crash_and_is_preserved(manager, tmp_path, payload):
    store = str(tmp_path / "notes.json")
    with open(store, "w", encoding="utf-8") as f:
        f.write(payload)

    manager.load_notes()  # must not raise

    assert manager.notes == {}
    # The corrupt file must be left untouched so the user's notes are not lost.
    with open(store, "r", encoding="utf-8") as f:
        assert f.read() == payload


def test_save_notes_over_corrupt_store_rewrites_it(manager, tmp_path):
    store = str(tmp_path / "notes.json")
    with open(store, "w", encoding="utf-8") as f:
        f.write("{not json")

    manager.notes["a"] = FakeNote("a", make_note_data(title="Fresh"))
    manager.save_notes()

    assert read_store(store)["a"]["title"] == "Fresh"


# --------------------------------------------------------------------------
# Save failures
# --------------------------------------------------------------------------

def test_save_notes_survives_write_failure(manager, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("sticky_notes.open", boom, raising=False)

    manager.notes["a"] = FakeNote("a", make_note_data())
    assert manager.save_notes() is False  # must not raise, must report failure


def test_save_notes_reports_failure_via_signal(manager, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("sticky_notes.open", boom, raising=False)

    reported = []
    manager.save_failed.connect(reported.append)

    manager.notes["a"] = FakeNote("a", make_note_data())
    manager.save_notes()

    assert len(reported) == 1
    assert "disk full" in reported[0]


def test_save_notes_returns_true_on_success(manager):
    manager.notes["a"] = FakeNote("a", make_note_data())

    assert manager.save_notes() is True


# --------------------------------------------------------------------------
# Migration between stores
# --------------------------------------------------------------------------

def test_migrate_and_reload_copies_old_data(manager, tmp_path):
    old_store = str(tmp_path / "notes.json")
    manager.notes["a"] = FakeNote("a", make_note_data(title="Carry me"))
    manager.save_notes()
    assert read_store(old_store)["a"]["title"] == "Carry me"

    new_store = str(tmp_path / "moved" / "notes.json")
    assert manager.migrate_and_reload(new_store) is True

    # The old notes were copied and reloaded from the new location.
    assert read_store(new_store)["a"]["title"] == "Carry me"
    assert manager.get_data_path() == new_store
    assert manager.notes["a"].data["title"] == "Carry me"


def test_migrate_and_reload_closes_old_notes(manager, tmp_path):
    manager.notes["a"] = FakeNote("a", make_note_data())
    old_note = manager.notes["a"]

    assert manager.migrate_and_reload(str(tmp_path / "new.json")) is True

    assert old_note.closed is True
    assert "a" not in manager.notes or manager.notes["a"] is not old_note


def test_migrate_does_not_switch_path_when_copy_fails(manager, tmp_path, monkeypatch):
    old_path = manager.get_data_path()
    manager.notes["a"] = FakeNote("a", make_note_data(title="Keep me"))
    manager.save_notes()

    def boom(path, old_data):
        return False

    monkeypatch.setattr(manager, "_write_old_data", boom)

    new_store = str(tmp_path / "moved" / "notes.json")
    assert manager.migrate_and_reload(new_store) is False

    # The store must still point at the file that holds the user's notes.
    assert manager.get_data_path() == old_path
    assert read_store(old_path)["a"]["title"] == "Keep me"


def test_migrate_with_empty_old_store_still_switches_path(manager, tmp_path):
    # No old data -> nothing to copy, migration must succeed and switch paths.
    new_store = str(tmp_path / "empty.json")
    assert manager.migrate_and_reload(new_store) is True
    assert manager.get_data_path() == new_store


def test_switch_table_path_reloads_from_new_store(manager, tmp_path):
    manager.notes["a"] = FakeNote("a", make_note_data())

    new_store = str(tmp_path / "switched.json")
    with open(new_store, "w", encoding="utf-8") as f:
        json.dump({"b": make_note_data(title="Reloaded")}, f)

    manager.switch_table_path(new_store)

    assert manager.get_data_path() == new_store
    assert set(manager.notes) == {"b"}


def test_switch_table_path_closes_existing_notes(manager, tmp_path):
    manager.notes["a"] = FakeNote("a", make_note_data())
    old_note = manager.notes["a"]

    manager.switch_table_path(str(tmp_path / "switched.json"))

    assert old_note.closed is True
    assert "a" not in manager.notes


# --------------------------------------------------------------------------
# New note placement
# --------------------------------------------------------------------------

def test_create_new_note_places_note_inside_screen(manager):
    note = manager.create_new_note()

    assert note.note_id in manager.notes
    assert note.shown is True
    assert note.data["x"] >= 0
    assert note.data["y"] >= 0
    # the cascade must keep the whole 260x220 note on the available area
    assert note.data["x"] + note.data["width"] <= 1920
    assert note.data["y"] + note.data["height"] <= 1080


def test_create_new_note_cascades_without_leaving_screen(manager):
    # enough notes to push the raw offset past the old 400/300 modulo bounds
    for _ in range(20):
        note = manager.create_new_note()
        assert note.data["x"] + note.data["width"] <= 1920
        assert note.data["y"] + note.data["height"] <= 1080


# --------------------------------------------------------------------------
# Note bookkeeping slots
# --------------------------------------------------------------------------

def test_on_note_deleted_removes_and_saves(manager, tmp_path):
    manager.notes["a"] = FakeNote("a", make_note_data(title="Doomed"))
    manager.save_notes()

    manager._on_note_deleted("a")

    assert "a" not in manager.notes
    assert "a" not in read_store(str(tmp_path / "notes.json"))


def test_on_note_deleted_ignores_unknown_id(manager):
    manager._on_note_deleted("missing")  # must not raise


def test_on_note_closed_hides_and_saves(manager):
    note = FakeNote("a", make_note_data())
    manager.notes["a"] = note

    manager._on_note_closed("a")

    assert note.hidden is True
    assert "a" in manager.notes


def test_on_note_closed_ignores_unknown_id(manager):
    manager._on_note_closed("missing")  # must not raise


# --------------------------------------------------------------------------
# Language propagation
# --------------------------------------------------------------------------

def test_set_language_propagates_to_notes(manager):
    note = FakeNote("a", make_note_data())
    manager.notes["a"] = note

    manager.set_language("pl")

    assert manager.lang == "pl"
    assert note.lang == "pl"
