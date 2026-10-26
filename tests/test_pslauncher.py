"""Tests for the script-to-command mapping in pslauncher.

These exercise the pure mapping helpers only; they never import tkinter or
start a real process, so they run headless in CI.
"""

import os
import sys

import pytest

import pslauncher


@pytest.mark.parametrize(
    "file_path, expected_argv",
    [
        (
            r"C:\scripts\hello.ps1",
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Unrestricted",
                "-File",
                r"C:\scripts\hello.ps1",
            ],
        ),
        (r"C:\scripts\job.vbs", ["cscript.exe", r"C:\scripts\job.vbs"]),
        (r"C:\scripts\job.js", ["cscript.exe", r"C:\scripts\job.js"]),
        (r"C:\scripts\job.wsf", ["cscript.exe", r"C:\scripts\job.wsf"]),
        (r"C:\scripts\app.hta", ["mshta.exe", r"C:\scripts\app.hta"]),
        (r"C:\scripts\run.bat", [r"C:\scripts\run.bat"]),
        (r"C:\scripts\run.cmd", [r"C:\scripts\run.cmd"]),
        (r"C:\scripts\tool.py", [sys.executable, r"C:\scripts\tool.py"]),
        # unknown extension runs the file directly, without an interpreter
        (r"C:\scripts\data.xyz", [r"C:\scripts\data.xyz"]),
        # no extension at all is also treated as "run directly"
        (r"C:\scripts\README", [r"C:\scripts\README"]),
    ],
)
def test_get_command_for_file_returns_expected_argv(file_path, expected_argv):
    assert pslauncher.get_command_for_file(file_path) == expected_argv


@pytest.mark.parametrize(
    "file_path",
    [r"C:\scripts\HELLO.PS1", r"C:\scripts\Job.VBS", r"C:\scripts\RUN.BAT"],
)
def test_get_command_for_file_is_case_insensitive(file_path):
    """Extensions are lower-cased before the lookup."""
    command = pslauncher.get_command_for_file(file_path)
    # the original spelling of the path is preserved in the command
    assert command[-1] == file_path


@pytest.mark.parametrize(
    "file_path, use_shell, ask_admin",
    [
        (r"C:\scripts\hello.ps1", False, False),
        (r"C:\scripts\job.vbs", False, True),
        (r"C:\scripts\run.bat", True, True),
        (r"C:\scripts\run.cmd", True, True),
        (r"C:\scripts\tool.py", False, True),
        (r"C:\scripts\data.xyz", False, True),
    ],
)
def test_handler_flags_match_command(file_path, use_shell, ask_admin):
    """The shell/admin decisions travel with the command they belong to."""
    handler = pslauncher.handler_for_file(file_path)
    assert handler.use_shell is use_shell
    assert handler.ask_admin is ask_admin
    assert handler.argv == pslauncher.get_command_for_file(file_path)


def test_bat_requires_shell():
    """`.bat` is the case where the shell requirement is not the default."""
    handler = pslauncher.handler_for_file(r"C:\scripts\run.bat")
    assert handler.use_shell is True
    assert os.path.splitext(r"C:\scripts\run.bat")[1] == ".bat"
