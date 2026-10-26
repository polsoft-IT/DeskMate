# File: sandbox_en.py
# ─────────────────────────────────────────────────────────────────────────────
# CrossTerm :: Sandbox Module
# Author : Sebastian Januchowski
# Company: polsoft.ITS™ Group
# GitHub : https://github.com/polsoft-seb07uk
# E-mail : polsoft.its@fastservice.com
# Version: 1.0.1
# ─────────────────────────────────────────────────────────────────────────────
"""
sandbox_en.py — isolated test environment for CrossTerm (English version of sandbox.py).

Purpose
─────────────
This module provides a dialog window (SandboxWindow) that allows running
commands and scripts (bat, cmd, ps1, py, vbs) in an isolated output buffer
without affecting the main terminal session.

Supported script types
──────────────────────────
  .bat / .cmd  — cmd.exe /C
  .ps1         — powershell.exe -ExecutionPolicy Bypass -File
  .py          — python.exe / python3
  .vbs         — cscript.exe //NoLogo
  .sh          — bash / sh
  .js          — node (Node.js)
  .lua         — lua / luajit (syntax test: luac -p)
  .rb          — ruby (syntax test: ruby -c)
  .pl          — perl (syntax test: perl -c)
  .php         — php (syntax test: php -l)
  .r / .R      — Rscript (syntax test: --parse-only)
  .tcl         — tclsh
  .wsf         — cscript.exe //NoLogo  (Windows only)
  .hta         — mshta.exe             (Windows only, no syntax verification)
  .reg         — regedit.exe /s        (Windows only, requires confirmation)
  .go          — go run                (syntax test: go vet)
  .java        — java (single-file, Java 11+)  (syntax test: javac)
  .cs / .csx   — dotnet-script                (verification: runtime only)
  .ts          — ts-node / deno run    (syntax test: tsc --noEmit / deno check)
  .coffee      — coffee                (syntax test: coffee -p)
  .exs         — elixir                (syntax test: elixir -e)
Structure
──────────
  SandboxWindow
  ├── _build_toolbar()       ← buttons: Run / Open / Clear / Save log
  ├── _build_console()       ← output area (scrolled Text) with color tags
  ├── _build_input()         ← command field or path to file
  ├── _run_command()         ← dispatcher: script file or built-in command
  ├── _run_script(path)      ← runs a script in the background (subprocess + threading)
  ├── _stream_output(proc)   ← reads stdout/stderr in real time
  ├── _test_script(path)     ← test mode: syntax verification before running
  └── _handle_builtin(cmd)   ← built-in commands (help, clear, version …)
"""

from __future__ import annotations
import weakref

import glob
import os
import platform
import shlex
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import simpledialog
from pathlib import Path
from tkinter import filedialog, ttk

# Import structured logger
try:
    from logger import get_logger
    _logger = get_logger()
except ImportError:
    _logger = None

try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, get_lexer_for_filename, guess_lexer, TextLexer
    from pygments.styles import get_style_by_name
    _PYGMENTS_AVAILABLE = True
except ImportError:
    _PYGMENTS_AVAILABLE = False

# ── Module metadata ──────────
__version__   = "1.0.1"
__author__    = "Sebastian Januchowski"
__company__   = "polsoft.ITS™ Group"
__module_id__ = "sandbox"

IS_WINDOWS = platform.system() == "Windows"

# Shells / interpreters recognized as the FIRST token of a command, e.g.
# "cmd.exe /c file.bat", "powershell -File script.ps1", "python -O script.py".
# This lets the sandbox behave like a real terminal, not just a "run file" box.
_SHELL_INVOCATIONS = {
    "cmd", "cmd.exe",
    "powershell", "powershell.exe", "pwsh", "pwsh.exe",
    "python", "python.exe", "python3", "py", "py.exe",
    "node", "node.exe",
    "bash", "bash.exe", "sh",
    "wscript", "wscript.exe", "cscript", "cscript.exe",
    "ruby", "perl", "php", "Rscript", "tclsh",
    "go", "java", "dotnet-script",
    "mshta", "mshta.exe",
}


def _split_commandline(text: str) -> list[str]:
    """Split input while preserving quoted Windows paths and arguments."""
    try:
        if IS_WINDOWS:
            # ``posix=False`` preserves Windows backslashes.  Popen receives
            # argv directly, so enclosing quotes must then be removed.
            return [part.strip('"') for part in shlex.split(text, posix=False)]
        return shlex.split(text)
    except ValueError:
        # Do not crash a Tk callback on an unmatched quote.
        return []

# ── UI constants ─────────────
_FONT_CONSOLE = ("Consolas", 10)
_FONT_LABEL   = ("Segoe UI", 9)
_BANNER = (
    "Type a command, a script path, or click 📂 Open.\n"
    "Supported: .bat .cmd .ps1 .py .vbs .sh .js .lua .rb .pl .php .r .tcl .wsf .hta .reg .go .java .cs .csx .ts .coffee .exs\n"
)
_LEXER_MAP = {
    ".py": "python", ".ps1": "powershell", ".bat": "batch", ".cmd": "batch",
    ".sh": "bash", ".js": "javascript", ".ts": "typescript", ".rb": "ruby", ".pl": "perl",
    ".php": "php", ".lua": "lua", ".go": "go", ".java": "java", ".cs": "csharp", ".html": "html",
}

# ── Syntax verification configuration ──
SYNTAX_CHECK_CONFIG = {
    ".bat": {"special": True, "platform": "windows", "ok_msg": "BAT/CMD file: loaded correctly"},
    ".cmd": {"special": True, "platform": "windows", "ok_msg": "BAT/CMD file: loaded correctly"},
    ".hta": {"special": True, "platform": "windows", "ok_msg": "HTA file: loaded correctly"},
    ".reg": {"special": True, "platform": "windows", "ok_msg": "REG file: header valid"},
    ".cs": {"special": True, "ok_msg": "dotnet-script found"},
    ".csx": {"special": True, "ok_msg": "dotnet-script found"},
}

# ── Runner configuration for errors ──
RUNNER_CONFIG = {
    ".bat": {"error": "cmd.exe not found"},
    ".cmd": {"error": "cmd.exe not found"},
    ".ps1": {"error": "powershell/pwsh not found"},
    ".py": {"error": "python not found"},
    ".vbs": {"error": "cscript.exe not found"},
    ".sh": {"error": "bash/sh not found"},
    ".js": {"error": "node (Node.js) not found"},
    ".lua": {"error": "lua/luac not found"},
    ".rb": {"error": "ruby not found"},
    ".pl": {"error": "perl not found"},
    ".php": {"error": "php not found"},
    ".r": {"error": "Rscript not found"},
    ".R": {"error": "Rscript not found"},
    ".tcl": {"error": "tclsh not found"},
    ".wsf": {"error": "cscript.exe not found"},
    ".hta": {"error": "mshta.exe not found"},
    ".reg": {"error": "regedit.exe not found"},
    ".go": {"error": "go not found"},
    ".java": {"error": "java/javac not found"},
    ".cs": {"error": "dotnet-script not found"},
    ".csx": {"error": "dotnet-script not found"},
    ".ts": {"error": "ts-node or deno not found"},
    ".coffee": {"error": "coffee not found"},
    ".exs": {"error": "elixir not found"},
}

# ── Extension → runner mapping ──
def _find_python() -> str:
    """Find the Python interpreter: prefer the one running this process."""
    return sys.executable or shutil.which("python") or shutil.which("python3") or "python"


def _find_shell() -> str | None:
    """Find a shell interpreter for .sh scripts (bash, falling back to sh)."""
    return shutil.which("bash") or shutil.which("sh")


def _find_node() -> str | None:
    """Find the Node.js interpreter for .js scripts."""
    found = shutil.which("node") or shutil.which("nodejs")
    if found:
        return found
    if IS_WINDOWS:
        candidates = [
            r"C:\Program Files\nodejs\node.exe",
            r"C:\Program Files (x86)\nodejs\node.exe",
            os.path.expandvars(r"%APPDATA%\nvm\current\node.exe"),
            os.path.expandvars(r"%ProgramFiles%\nodejs\node.exe"),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
    return None


def _find_lua() -> str | None:
    """Find a Lua interpreter for .lua scripts (lua, lua5.x, luajit)."""
    for name in ("lua", "lua5.4", "lua5.3", "lua5.1", "luajit"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _find_luac() -> str | None:
    """Find the Lua compiler/parser (luac) used for syntax verification."""
    for name in ("luac", "luac5.4", "luac5.3", "luac5.1"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _find_ruby() -> str | None:
    """Find the Ruby interpreter for .rb scripts."""
    found = shutil.which("ruby")
    if found:
        return found
    if IS_WINDOWS:
        candidates = [
            r"C:\Ruby34-x64\bin\ruby.exe",
            r"C:\Ruby33-x64\bin\ruby.exe",
            r"C:\Ruby32-x64\bin\ruby.exe",
            r"C:\Ruby31-x64\bin\ruby.exe",
            r"C:\Ruby30-x64\bin\ruby.exe",
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
    return None


def _find_perl() -> str | None:
    """Find the Perl interpreter for .pl scripts."""
    found = shutil.which("perl")
    if found:
        return found
    if IS_WINDOWS:
        # Strawberry Perl
        candidates = [
            r"C:\Strawberry\perl\bin\perl.exe",
            r"C:\Perl64\bin\perl.exe",
            r"C:\Perl\bin\perl.exe",
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
    return None


def _find_php() -> str | None:
    """Find the PHP interpreter for .php scripts."""
    found = shutil.which("php")
    if found:
        return found
    if IS_WINDOWS:
        candidates = [
            r"C:\php\php.exe",
            r"C:\xampp\php\php.exe",
            r"C:\wamp64\bin\php\php8.2.0\php.exe",
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
    return None


def _find_rscript() -> str | None:
    """Find the R interpreter (Rscript) for .r/.R scripts."""
    found = shutil.which("Rscript")
    if found:
        return found
    if IS_WINDOWS:
        # Typical R installation paths on Windows
        patterns = [
            r"C:\Program Files\R\R-*\bin\x64\Rscript.exe",
            r"C:\Program Files\R\R-*\bin\Rscript.exe",
        ]
        for pat in patterns:
            hits = sorted(glob.glob(pat), reverse=True)  # newest version first
            if hits:
                return hits[0]
    return None


def _find_tclsh() -> str | None:
    """Find the Tcl interpreter (tclsh) for .tcl scripts."""
    for name in ("tclsh", "tclsh9.0", "tclsh8.6", "tclsh8.5"):
        found = shutil.which(name)
        if found:
            return found
    if IS_WINDOWS:
        candidates = [
            r"C:\Tcl\bin\tclsh.exe",
            r"C:\ActiveTcl\bin\tclsh.exe",
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
    return None


def _find_go() -> str | None:
    """Find the go tool for .go scripts."""
    found = shutil.which("go")
    if found:
        return found
    if IS_WINDOWS:
        for c in [r"C:\Program Files\Go\bin\go.exe", r"C:\Go\bin\go.exe"]:
            if os.path.isfile(c):
                return c
    else:
        for c in ["/usr/local/go/bin/go", "/usr/lib/go/bin/go"]:
            if os.path.isfile(c):
                return c
    return None


def _find_java() -> tuple[str | None, str | None]:
    """Find java and javac. Returns (java, javac)."""
    java  = shutil.which("java")
    javac = shutil.which("javac")
    if IS_WINDOWS and not java:
        patterns = [
            r"C:\Program Files\Java\jdk*\bin\java.exe",
            r"C:\Program Files\Eclipse Adoptium\jdk*\bin\java.exe",
            r"C:\Program Files\Microsoft\jdk*\bin\java.exe",
        ]
        for pat in patterns:
            hits = sorted(glob.glob(pat), reverse=True)
            if hits:
                java = hits[0]
                javac = hits[0].replace("java.exe", "javac.exe") if os.path.isfile(hits[0].replace("java.exe", "javac.exe")) else None
                break
    return java, javac


def _find_dotnet_script() -> str | None:
    """Find dotnet-script or dotnet for .cs scripts."""
    ds = shutil.which("dotnet-script")
    if ds:
        return ds
    # Fallback: dotnet alone (it can run .csx via dotnet-script)
    return shutil.which("dotnet")


def _find_ts_runner() -> tuple[str | None, str]:
    """
    Find a TypeScript runner. Returns (path, mode).
    Mode: 'ts-node' | 'deno' | None
    """
    ts_node = shutil.which("ts-node")
    if ts_node:
        return ts_node, "ts-node"
    deno = shutil.which("deno")
    if deno:
        return deno, "deno"
    return None, ""


def _find_coffee() -> str | None:
    """Find the CoffeeScript interpreter (coffee) for .coffee scripts."""
    return shutil.which("coffee")


def _find_elixir() -> str | None:
    """Find the Elixir interpreter (elixir) for .exs scripts."""
    found = shutil.which("elixir")
    if found:
        return found
    if not IS_WINDOWS:
        for c in ["/usr/local/bin/elixir", "/usr/bin/elixir"]:
            if os.path.isfile(c):
                return c
    return None


def _find_mshta() -> str | None:
    """Find mshta.exe for .hta scripts (Windows only)."""
    if not IS_WINDOWS:
        return None
    found = shutil.which("mshta")
    if found:
        return found
    candidates = [
        r"C:\Windows\System32\mshta.exe",
        r"C:\Windows\SysWOW64\mshta.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


# ── Extension → runner mapping ──────────────
def _build_runner(path: Path) -> list[str] | None:
    """Returns a list of arguments for subprocess.Popen, or None if unsupported."""
    ext = path.suffix.lower()
    if ext in (".bat", ".cmd"):
        if IS_WINDOWS:
            return ["cmd.exe", "/C", str(path)]
        return None  # .bat/.cmd do not work outside Windows
    if ext == ".ps1":
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if ps:
            return [ps, "-ExecutionPolicy", "Bypass", "-File", str(path)]
        return None
    if ext == ".py":
        return [_find_python(), str(path)]
    if ext == ".vbs":
        if IS_WINDOWS:
            cs = shutil.which("cscript")
            if cs:
                return [cs, "//NoLogo", str(path)]
        return None
    if ext == ".sh":
        sh = _find_shell()
        if sh:
            return [sh, str(path)]
        return None
    if ext == ".js":
        node = _find_node()
        if node:
            return [node, str(path)]
        return None
    if ext == ".lua":
        lua = _find_lua()
        if lua:
            return [lua, str(path)]
        return None
    if ext == ".rb":
        rb = _find_ruby()
        if rb:
            return [rb, str(path)]
        return None
    if ext == ".pl":
        pl = _find_perl()
        if pl:
            return [pl, str(path)]
        return None
    if ext == ".php":
        php = _find_php()
        if php:
            return [php, str(path)]
        return None
    if ext in (".r", ".R"):
        rs = _find_rscript()
        if rs:
            return [rs, str(path)]
        return None
    if ext == ".tcl":
        tcl = _find_tclsh()
        if tcl:
            return [tcl, str(path)]
        return None
    if ext == ".wsf":
        if IS_WINDOWS:
            cs = shutil.which("cscript")
            if cs:
                return [cs, "//NoLogo", str(path)]
        return None
    if ext == ".hta":
        mshta = _find_mshta()
        if mshta:
            return [mshta, str(path)]
        return None
    if ext == ".reg":
        if IS_WINDOWS:
            regedit = shutil.which("regedit") or r"C:\Windows\regedit.exe"
            if os.path.isfile(regedit) or shutil.which("regedit"):
                return [regedit, "/s", str(path)]
        return None
    if ext == ".go":
        go = _find_go()
        if go:
            # go run supports single-file since Go 1.0; -mod=mod is needed outside a module
            return [go, "run", str(path)]
        return None
    if ext == ".java":
        java, _ = _find_java()
        if java:
            # java <file.java> works for single-file source programs since Java 11
            return [java, str(path)]
        return None
    if ext in (".cs", ".csx"):
        ds = _find_dotnet_script()
        if ds:
            name = os.path.basename(ds)
            if "dotnet-script" in name:
                # dotnet-script <file>
                return [ds, str(path)]
            # dotnet alone cannot run .cs/.csx without a project — dotnet-script required
        return None
    if ext == ".ts":
        runner_ts, mode = _find_ts_runner()
        if runner_ts:
            if mode == "deno":
                return [runner_ts, "run", "--allow-all", str(path)]
            return [runner_ts, str(path)]
        return None
    if ext == ".coffee":
        coffee = _find_coffee()
        if coffee:
            return [coffee, str(path)]
        return None
    if ext == ".exs":
        elixir = _find_elixir()
        if elixir:
            return [elixir, str(path)]
        return None
    return None


def _syntax_check(path: Path) -> tuple[bool, str]:
    """
    Syntax verification before execution.
    Returns (ok: bool, message: str).
    """
    ext = path.suffix.lower()
    config = SYNTAX_CHECK_CONFIG.get(ext)
    if not config:
        return False, f"Unsupported extension: {ext!r}"

    if ext == ".py":
        py = _find_python()
        result = subprocess.run(
            [py, "-m", "py_compile", str(path)],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True, "Python syntax: OK"
        return False, result.stderr.strip() or "Python syntax error"

    if ext == ".ps1":
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if ps:
            # PowerShell: parse the script without executing it
            result = subprocess.run(
                [ps, "-NoProfile", "-NonInteractive", "-Command",
                 f"$null = [System.Management.Automation.Language.Parser]::ParseFile('{path}', [ref]$null, [ref]$errs); $errs | ForEach-Object {{ $_.Message }}"],
                capture_output=True, text=True, timeout=10
            )
            errs = result.stdout.strip()
            if not errs:
                return True, "PowerShell syntax: OK"
            return False, errs
        return False, "powershell/pwsh not found"

    if ext in (".bat", ".cmd"):
        if not IS_WINDOWS:
            return False, ".bat/.cmd — Windows only"
        # Minimal verification: check that the file is not empty and encoding
    if config.get("special"):
        if config.get("platform") == "windows" and not IS_WINDOWS:
            return False, f"{ext.upper()} — Windows only"
        # Special handling for types without a simple checker command
        try:
            content = path.read_text(encoding="cp1250", errors="replace")
            if not content.strip():
                return False, "File is empty"
            return True, "BAT/CMD file: loaded correctly (full verification only at runtime)"
            if ext in (".bat", ".cmd", ".hta"):
                if not path.read_text(encoding="cp1250", errors="replace").strip():
                    return False, "File is empty"
            elif ext == ".reg":
                raw = path.read_bytes()
                content = raw.decode("utf-16" if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else "utf-8", errors="replace")
                first_line = content.strip().splitlines()[0] if content.strip() else ""
                if not any(first_line.startswith(h) for h in ("Windows Registry Editor Version 5.00", "REGEDIT4")):
                    return False, f"Invalid .reg header: {first_line!r}"
            elif ext in (".cs", ".csx"):
                if not _find_dotnet_script():
                    return False, "dotnet-script required: dotnet tool install -g dotnet-script"
            return True, config["ok_msg"]
        except Exception as exc:
            return False, str(exc)

    if ext == ".vbs":
        if not IS_WINDOWS:
            return False, ".vbs — Windows only"
        cs = shutil.which("cscript")
        if cs:
            # cscript //NoExecute checks the syntax
            result = subprocess.run(
                [cs, "//NoLogo", "//NoExecute", str(path)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return True, "VBScript syntax: OK"
            return False, (result.stderr or result.stdout).strip() or "VBS syntax error"
        return False, "cscript.exe not found"
    runner_path = config["runner"]() if "runner" in config else None
    if not runner_path:
        return False, config.get("err_msg", f"No interpreter available for {ext}")

    if ext == ".sh":
        sh = _find_shell()
        if sh:
            # bash/sh -n: syntax check without execution
            result = subprocess.run(
                [sh, "-n", str(path)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return True, "Shell syntax: OK"
            return False, result.stderr.strip() or "Shell syntax error"
        return False, "bash/sh not found"

    if ext == ".js":
        node = _find_node()
        if node:
            # node --check: syntax check without execution
            result = subprocess.run(
                [node, "--check", str(path)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return True, "JavaScript syntax: OK"
            return False, result.stderr.strip() or "JavaScript syntax error"
        return False, "node (Node.js) not found"

    if ext == ".lua":
        luac = _find_luac()
        if luac:
            # luac -p: parsing ("precompile") without creating an output file
            result = subprocess.run(
                [luac, "-p", str(path)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return True, "Lua syntax: OK"
            return False, (result.stderr or result.stdout).strip() or "Lua syntax error"
        if _find_lua():
            return False, "luac not found — Lua syntax verification requires luac"
        return False, "lua/luac not found"

    if ext == ".rb":
        rb = _find_ruby()
        if rb:
            # ruby -c: syntax check without execution
            result = subprocess.run(
                [rb, "-c", str(path)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return True, "Ruby syntax: OK"
            return False, result.stderr.strip() or result.stdout.strip() or "Ruby syntax error"
        return False, "ruby not found"

    if ext == ".pl":
        pl = _find_perl()
        if pl:
            # perl -c: syntax check — prints "syntax OK" on stderr even on success
            result = subprocess.run(
                [pl, "-c", str(path)],
                capture_output=True, text=True, timeout=10
            )
            out = (result.stderr + result.stdout).strip()
            if result.returncode == 0:
                return True, f"Perl syntax: {out}" if out else "Perl syntax: OK"
            return False, out or "Perl syntax error"
        return False, "perl not found"

    if ext == ".php":
        php = _find_php()
        if php:
            # php -l: lint — syntax check without execution
            result = subprocess.run(
                [php, "-l", str(path)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return True, "PHP syntax: OK"
            return False, result.stdout.strip() or result.stderr.strip() or "PHP syntax error"
        return False, "php not found"

    if ext in (".r", ".R"):
        rs = _find_rscript()
        if rs:
            # Rscript --parse-only: parsing without execution (R >= 3.6)
            result = subprocess.run(
                [rs, "--parse-only", str(path)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return True, "R syntax: OK"
            return False, result.stderr.strip() or result.stdout.strip() or "R syntax error"
        return False, "Rscript not found"

    if ext == ".tcl":
        tcl = _find_tclsh()
        if tcl:
            # tclsh has no dedicated syntax flag — verify via parse in a subinterpreter
            check_script = f'if {{[catch {{set fd [open "{str(path).replace(chr(92), "/")}" r]; set src [read $fd]; close $fd; parse $src}} err]}} {{puts stderr $err; exit 1}} else {{exit 0}}'
            result = subprocess.run(
                [tcl],
                input=check_script,
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return True, "Tcl syntax: OK (loaded)"
            # Fallback: tclsh parses the file on load — no static verification
            return False, result.stderr.strip() or "Unable to verify Tcl syntax (no parse)"
        return False, "tclsh not found"

    if ext == ".wsf":
        if not IS_WINDOWS:
            return False, ".wsf — Windows only"
        cs = shutil.which("cscript")
        if cs:
            # cscript //NoExecute checks syntax without execution
            result = subprocess.run(
                [cs, "//NoLogo", "//NoExecute", str(path)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return True, "WSF syntax: OK"
            return False, (result.stderr or result.stdout).strip() or "WSF syntax error"
        return False, "cscript.exe not found"

    if ext == ".hta":
        if not IS_WINDOWS:
            return False, ".hta — Windows only"
        mshta = _find_mshta()
        if mshta:
            # mshta has no syntax verification mode — only check that the file is readable
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                if not content.strip():
                    return False, "HTA file is empty"
                return True, "HTA file: loaded (full verification only at runtime)"
            except Exception as exc:
                return False, str(exc)
        return False, "mshta.exe not found"

    if ext == ".reg":
        if not IS_WINDOWS:
            return False, ".reg — Windows only"
        try:
            # Verification: the file must start with a Windows Registry Editor header
            raw = path.read_bytes()
            # Handle UTF-16 LE BOM (typical for .reg files from Windows)
            if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
                content = raw.decode("utf-16", errors="replace")
            else:
                content = raw.decode("utf-8", errors="replace")
            first_line = content.strip().splitlines()[0] if content.strip() else ""
            valid_headers = (
                "Windows Registry Editor Version 5.00",
                "REGEDIT4",
            )
            if not any(first_line.startswith(h) for h in valid_headers):
                return False, f"Invalid .reg header: {first_line!r}"
            return True, "REG file: header valid (execution requires confirmation)"
        except Exception as exc:
            return False, str(exc)

    if ext == ".go":
        go = _find_go()
        if go:
            # go vet: static analysis; go build -o /dev/null: compilation without an output file
            result = subprocess.run(
                [go, "vet", str(path)],
                capture_output=True, text=True, timeout=30,
                cwd=str(path.parent),
            )
            if result.returncode == 0:
                return True, "Go syntax: OK (go vet)"
            return False, (result.stderr or result.stdout).strip() or "go vet error"
        return False, "go not found"

    if ext == ".java":
        _, javac = _find_java()
        if javac:
            result = subprocess.run(
                [javac, "-proc:none", str(path)],
                capture_output=True, text=True, timeout=30,
                cwd=str(path.parent),
            )
            if result.returncode == 0:
                # Remove the generated .class from the script directory
                class_file = path.with_suffix(".class")
                if class_file.exists():
                    try:
                        class_file.unlink()
                    except OSError:
                        pass
                return True, "Java syntax: OK (javac)"
            return False, result.stderr.strip() or result.stdout.strip() or "javac error"
        java, _ = _find_java()
        if java:
            return False, "javac not found — a JDK is required (not just a JRE)"
        return False, "java/javac not found"

    if ext in (".cs", ".csx"):
        ds = _find_dotnet_script()
        if ds and "dotnet-script" in os.path.basename(ds):
            # dotnet-script --help does not compile — no dry-run mode; informational only
            return True, "dotnet-script found (C# syntax verification only at runtime)"
        dotnet = shutil.which("dotnet")
        if dotnet:
            return False, "dotnet-script required: dotnet tool install -g dotnet-script"
        return False, "dotnet-script or dotnet not found"

    # Special case for TypeScript
    if ext == ".ts":
        runner_ts, mode = _find_ts_runner()
        if runner_ts:
            if mode == "deno":
                result = subprocess.run(
                    [runner_ts, "check", str(path)],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    return True, "TypeScript syntax: OK (deno check)"
                return False, (result.stderr or result.stdout).strip() or "deno check error"
            # ts-node: check via tsc if available
        _, mode = _find_ts_runner()
        if mode == "deno":
            cmd = [runner_path, "check", str(path)]
        else:  # ts-node
            tsc = shutil.which("tsc")
            if tsc:
                result = subprocess.run(
                    [tsc, "--noEmit", "--allowJs", "--checkJs", str(path)],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(path.parent),
                )
                if result.returncode == 0:
                    return True, "TypeScript syntax: OK (tsc --noEmit)"
                return False, result.stdout.strip() or result.stderr.strip() or "tsc error"
            return True, "ts-node found (no tsc — TS syntax verification limited)"
        return False, "ts-node or deno not found"
    else:
        path_esc = str(path).replace(chr(92), "/")
        cmd = [arg.format(runner=runner_path, path=str(path), path_esc=path_esc) for arg in config["template"]]

    if ext == ".coffee":
        coffee = _find_coffee()
        if coffee:
            # coffee -p: compiles to JS on stdout without saving — syntax verification
            result = subprocess.run(
                [coffee, "-p", str(path)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return True, "CoffeeScript syntax: OK (coffee -p)"
            return False, result.stderr.strip() or result.stdout.strip() or "CoffeeScript syntax error"
        return False, "coffee not found (npm i -g coffeescript)"
    result = subprocess.run(
        cmd, input=config.get("input", "").format(path_esc=path_esc),
        capture_output=True, text=True, timeout=30, cwd=str(path.parent)
    )

    if ext == ".exs":
        elixir = _find_elixir()
        if elixir:
            # elixir --no-halt -e: compile_string checks syntax without running the script
            check_code = (
                f'try do\n'
                f'  Code.compile_file("{str(path).replace(chr(92), "/")}")\n'
                f'  IO.puts("OK")\n'
                f'rescue e ->\n'
                f'  IO.puts(:stderr, Exception.message(e))\n'
                f'  System.halt(1)\n'
                f'end'
            )
            result = subprocess.run(
                [elixir, "-e", check_code],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return True, "Elixir syntax: OK"
            return False, result.stderr.strip() or result.stdout.strip() or "Elixir syntax error"
        return False, "elixir not found"
    if result.returncode == 0:
        # Perl -c prints "syntax OK" on success, so we might want to show it
        out = (result.stderr + result.stdout).strip()
        return True, f"{config['ok_msg']}: {out}" if out and ext == ".pl" else config["ok_msg"]
    return False, (result.stderr or result.stdout).strip() or config["err_msg"]

    return False, f"Unsupported extension: {ext!r}"


# ── Encoding detection ────────────────
def _detect_encoding(path: Path) -> str:
    """
    Detect the encoding of a script file.
    Order: BOM → Windows heuristic (cp1250 for .bat/.cmd/.vbs/.wsf)
    → try UTF-8 → fallback cp1250 / latin-2.
    Requires no chardet; works 100% on stdlib.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return "utf-8"

    # BOM — unambiguous identification
    if raw[:3] == b'\xef\xbb\xbf':
        return "utf-8-sig"
    if raw[:2] == b'\xff\xfe':
        return "utf-16-le"
    if raw[:2] == b'\xfe\xff':
        return "utf-16-be"
    if raw[:4] == b'\x00\x00\xfe\xff':
        return "utf-32-be"
    if raw[:4] == b'\xff\xfe\x00\x00':
        return "utf-32-le"

    # Windows Script files — always CP1250 on a Polish system
    if IS_WINDOWS and path.suffix.lower() in (".bat", ".cmd", ".vbs", ".wsf"):
        return "cp1250"

    # Try UTF-8 (strict — no replace)
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # CP1250 heuristic — Polish characters have specific bytes in CP1250:
    # ą=0xa5 ć=0xe6 ę=0xea ł=0xb3 ń=0xf1 ó=0xf3 ś=0x9c ź=0x9f ż=0xbf
    # Ą=0xa4 Ć=0xc6 Ę=0xca Ł=0xa3 Ń=0xd1 Ó=0xd3 Ś=0x8c Ź=0x8f Ż=0xaf
    _CP1250_PL = frozenset((
        0xa5, 0xe6, 0xea, 0xb3, 0xf1, 0xf3, 0x9c, 0x9f, 0xbf,
        0xa4, 0xc6, 0xca, 0xa3, 0xd1, 0xd3, 0x8c, 0x8f, 0xaf,
    ))
    if any(b in _CP1250_PL for b in raw):
        return "cp1250"
    return "utf-8"


# ── ANSI ESC sequence parser ──────────
import re as _re

# Regex matching ESC CSI sequences: ESC [ <params> <final_byte>
_ANSI_RE = _re.compile(r'\x1b\[([\d;]*)([A-Za-z])')

# Predefined ANSI 3/4-bit colors → hex (dark background)
_ANSI_FG = {
    30: "#1e1e2e",  # black  → background (appears as dark)
    31: "#f871",  # red
    32: "#4ade80",  # green
    33: "#fbbf24",  # yellow
    34: "#60a5fa",  # blue
    35: "#c084fc",  # magenta
    36: "#34d399",  # cyan
    37: "#e2e8f0",  # white
    90: "#64748b",  # bright black (gray)
    91: "#fca5a5",  # bright red
    92: "#86efac",  # bright green
    93: "#fde68a",  # bright yellow
    94: "#93c5fd",  # bright blue
    95: "#d8b4fe",  # bright magenta
    96: "#6ee7b7",  # bright cyan
    97: "#f8fafc",  # bright white
}
_ANSI_BG = {k + 10: v for k, v in _ANSI_FG.items()}  # 40–47, 100–107

# 256-color palette (6×6×6 cube + grayscale ramp)
def _ansi_256_to_hex(n: int) -> str:
    if n < 16:
        base = [
            "#000","#800000","#008000","#808000",
            "#000080","#800080","#008080","#c0c0c0",
            "#808080","#ff0000","#00ff00","#ffff00",
            "#0000ff","#ff00ff","#00ffff","#ffffff",
        ]
        return base[n]
    if n < 232:
        n -= 16
        b = n % 6;  n //= 6
        g = n % 6;  r = n // 6
        def _c(x): return 0 if x == 0 else 55 + x * 40
        return f"#{_c(r):02x}{_c(g):02x}{_c(b):02x}"
    # grayscale ramp 232–255
    v = 8 + (n - 232) * 10
    return f"#{v:02x}{v:02x}{v:02x}"


def _ansi_to_spans(text: str, base_tag: str) -> list[tuple[str, str]]:
    """
    Parse ANSI ESC sequences in `text`.
    Returns a list of (text_fragment, tag_name) ready for insert() into tk.Text.
    Dynamic tags are created on-the-fly: 'ansi_fg_#rrggbb', 'ansi_bg_#rrggbb',
    'ansi_bold', 'ansi_ul', 'ansi_italic', base_tag (reset/default).
    Unsupported sequences (cursor move, erase etc.) are removed from the text.
    """
    spans: list[tuple[str, str]] = []
    # Current state
    fg: str | None = None
    bg: str | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False

    def _make_tag() -> str:
        """Build a unique tag name from the current state."""
        parts = [base_tag]
        if fg:   parts.append(f"fg{fg.replace('#','')}")
        if bg:   parts.append(f"bg{bg.replace('#','')}")
        if bold: parts.append("bold")
        if italic: parts.append("it")
        if underline: parts.append("ul")
        return "_".join(parts) if len(parts) > 1 else base_tag

    pos = 0
    for m in _ANSI_RE.finditer(text):
        start, end = m.span()
        # Text before the sequence
        if start > pos:
            spans.append((text[pos:start], _make_tag()))
        pos = end

        cmd = m.group(2)
        if cmd != 'm':
            # Ignore sequences other than SGR (Set Graphics Rendition)
            continue

        params_raw = m.group(1)
        params = [int(x) for x in params_raw.split(';') if x.isdigit()] if params_raw else [0]

        i = 0
        while i < len(params):
            p = params[i]
            if p == 0:
                fg = bg = None; bold = italic = underline = False
            elif p == 1:
                bold = True
            elif p == 2:
                bold = False  # faint — treat as bold reset
            elif p == 3:
                italic = True
            elif p == 4:
                underline = True
            elif p == 22:
                bold = False
            elif p == 23:
                italic = False
            elif p == 24:
                underline = False
            elif p in _ANSI_FG:
                fg = _ANSI_FG[p]
            elif p in _ANSI_BG:
                bg = _ANSI_BG[p]
            elif p == 39:
                fg = None
            elif p == 49:
                bg = None
            elif p in (38, 48):
                # 256-color: 38;5;N or truecolor: 38;2;R;G;B
                is_fg = (p == 38)
                if i + 1 < len(params) and params[i+1] == 5 and i + 2 < len(params):
                    color = _ansi_256_to_hex(params[i+2])
                    if is_fg: fg = color
                    else:     bg = color
                    i += 2
                elif i + 1 < len(params) and params[i+1] == 2 and i + 4 < len(params):
                    r, g, b = params[i+2], params[i+3], params[i+4]
                    color = f"#{r:02x}{g:02x}{b:02x}"
                    if is_fg: fg = color
                    else:     bg = color
                    i += 4
            i += 1

    # Remaining text after the last sequence
    if pos < len(text):
        spans.append((text[pos:], _make_tag()))

    return spans


# ─────────────
class SandboxWindow(tk.Toplevel):
    """Sandbox window — run and test scripts (.bat/.cmd/.ps1/.py/.vbs/.sh/.js/.lua/.rb/.pl/.php/.r/.tcl/.wsf/.hta/.reg/.go/.java/.cs/.csx/.ts/.coffee/.exs)."""
    def __init__(self, parent: tk.Widget, theme: dict, *, title: str = "🧪 Sandbox", initial_path: str | None = None) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(True, True)
        self.minsize(1280, 540)
        self.geometry("800x540")
        self.geometry("800x600")

        self._theme    = theme
        self._history: list[str] = []
        self._hist_idx: int = -1
        self._running_proc: subprocess.Popen | None = None
        self._last_script: Path | None = None
        self._pygments_tag_cache: set[str] = set()
        self._current_lexer = None
        self._main_app_ref = weakref.ref(parent) if hasattr(parent, "scripts") else None
        self._always_on_top: bool = False

        self._apply_theme()
        self._build_toolbar()
        self._build_input()
        self._build_panes()
        self._print_banner()

        self._entry.focus_set()
        if _PYGMENTS_AVAILABLE:
            self._configure_pygments_tags()
            self._editor.bind("<<Modified>>", self._on_editor_modified, add=True)

        if initial_path:
            self.after(100, lambda p=initial_path: self._load_file(p))

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _load_file(self, path_str: str):
        path = Path(path_str)
        if not path.is_file():
            return
        content, _ = _read_source(path)
        self._editor.delete("1.0", "end")
        self._editor.insert("1.0", content)
        self._update_lexer_from_path(path_str)

    # ── Theme ──────────────
    def _apply_theme(self) -> None:
        t = self._theme
        self.configure(bg=t.get("DARK", "#0f1117"))

    # ── Toolbar ────────────
    def _build_toolbar(self) -> None:
        t = self._theme
        bar = tk.Frame(self, bg=t.get("PANEL", "#181c27"), pady=4)
        bar.pack(fill=tk.X, side=tk.TOP)

        btn_kw = dict(
            bg=t.get("CARD", "#1e223"),
            fg=t.get("TEXT", "#e2e8f0"),
            activebackground=t.get("ACCENT", "#4ade80"),
            activeforeground=t.get("DARK", "#0f1117"),
            relief=tk.FLAT, padx=10, pady=2, cursor="hand2"
        )
        btn_red = {**btn_kw, "activebackground": t.get("RED", "#f871")}
        btn_yel = {**btn_kw, "activebackground": t.get("YELLOW", "#fbbf24")}

        tk.Button(bar, text="▶  Run",      command=self._run_command,   **btn_kw).pack(side=tk.LEFT, padx=(8, 2))
        tk.Button(bar, text="🔬  Test",    command=self._test_current,  **btn_yel).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="📂  Open",    command=self._browse_script, **btn_kw).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="⛔  Stop",    command=self._stop_process,  **btn_red).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="🗑  Clear",   command=self._clear,         **btn_kw).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="💾  Save log",command=self._save_log,      **btn_kw).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="📌  Always on top", command=self._toggle_always_on_top, **btn_kw).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="▶ Run", command=self._run_editor_content, **btn_kw).pack(side=tk.LEFT, padx=(8, 2))
        tk.Button(bar, text="🔬 Test", command=self._test_editor_content, **btn_yel).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="📂 Open", command=self._browse_script, **btn_kw).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="💾 Save", command=self._save_editor_content, **btn_kw).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="⛔ Stop", command=self._stop_process, **btn_red).pack(side=tk.LEFT, padx=2)
        tk.Button(bar, text="🗑 Clear", command=self._clear, **btn_kw).pack(side=tk.LEFT, padx=2)
        # Store reference to "Add to psLauncher" button for safe hiding
        self._add_to_pslauncher_btn = tk.Button(bar, text="✚ Add to psLauncher", command=self._add_to_pslauncher, **btn_kw)
        self._add_to_pslauncher_btn.pack(side=tk.LEFT, padx=2)

        self._status_lbl = tk.Label(
            bar, text="Ready.", font=(_FONT_LABEL[0], _FONT_LABEL[1]),
            bg=t.get("PANEL", "#181c27"), fg=t.get("DIM", "#64748b")
        )
        self._status_lbl.pack(side=tk.RIGHT, padx=8)
        if self._main_app_ref is None or self._main_app_ref() is None:
            if self._add_to_pslauncher_btn:
                self._add_to_pslauncher_btn.pack_forget()

    def _build_panes(self) -> None:
        t = self._theme
        panes = tk.PanedWindow(self, orient="vertical", bg=t.get("DARK", "#0f1117"), sashwidth=4, sashrelief="flat")
        panes.pack(fill="both", expand=True, padx=6, pady=6)

        # Top pane: Editor
        editor_frame = tk.Frame(panes, bg=t.get("DARK", "#0f1117"))
        self._editor = tk.Text(
            editor_frame, font=_FONT_CONSOLE, bg=t.get("DARK", "#0f1117"),
            fg=t.get("TEXT", "#e2e8f0"), insertbackground=t.get("ACCENT", "#4ade80"),
            selectbackground=t.get("ACCENT2", "#38bdf8"), relief=tk.FLAT,
            wrap="word", undo=True,
        )
        self._editor.pack(fill="both", expand=True)
        panes.add(editor_frame, minsize=100)

        # Bottom pane: Console
        console_frame = tk.Frame(panes, bg=t.get("DARK", "#0f1117"))
        self._build_console(console_frame)  # Pass the correct parent
        panes.add(console_frame, minsize=100)

    # ── Console ────────────
    def _build_console(self, parent: tk.Frame) -> None:
        t = self._theme
        sb = ttk.Scrollbar(parent, orient=tk.VERTICAL)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self._console = tk.Text(
            parent,
            font=_FONT_CONSOLE,
            bg=t.get("DARK", "#0f1117"),
            fg=t.get("TEXT", "#e2e8f0"),
            insertbackground=t.get("ACCENT", "#4ade80"),
            selectbackground=t.get("ACCENT2", "#38bdf8"),
            relief=tk.FLAT, wrap=tk.WORD, state=tk.DISABLED,
            yscrollcommand=sb.set,
        )
        self._console.pack(fill=tk.BOTH, expand=True)
        sb.config(command=self._console.yview)

        # Ctrl+C: copy selected text from the disabled widget
        self._console.bind("<Control-c>", self._copy_selection)

        # Output color tags
        self._console.tag_config("prompt",  foreground=t.get("ACCENT",  "#4ade80"))
        self._console.tag_config("output",  foreground=t.get("TEXT",    "#e2e8f0"))
        self._console.tag_config("stderr",  foreground=t.get("RED",     "#f871"))
        self._console.tag_config("error",   foreground=t.get("RED",     "#f871"))
        self._console.tag_config("info",    foreground=t.get("ACCENT2", "#38bdf8"))
        self._console.tag_config("dim",     foreground=t.get("DIM",     "#64748b"))
        self._console.tag_config("banner",  foreground=t.get("YELLOW",  "#fbbf24"))
        self._console.tag_config("ok",      foreground=t.get("ACCENT",  "#4ade80"))
        self._console.tag_config("warn",    foreground=t.get("YELLOW",  "#fbbf24"))
        self._console.tag_config("header",  foreground=t.get("ACCENT2", "#38bdf8"))

        # Fixed ANSI SGR tags (attributes)
        self._console.tag_config("ansi_bold",   font=(_FONT_CONSOLE[0], _FONT_CONSOLE[1], "bold"))
        self._console.tag_config("ansi_italic", font=(_FONT_CONSOLE[0], _FONT_CONSOLE[1], "italic"))
        self._console.tag_config("ansi_ul",     underline=True)

        # Cache of dynamic tags (fg/bg/combinations) — avoid duplicate tag_config calls
        self._ansi_tag_cache: set[str] = set()

    # ── Input field ────────
    def _build_input(self) -> None:
        t = self._theme
        frame = tk.Frame(self, bg=t.get("PANEL", "#181c27"), pady=4)
        frame.pack(fill=tk.X, side=tk.BOTTOM, padx=6, pady=4)

        tk.Label(
            frame, text="sandbox>", font=(_FONT_LABEL[0], _FONT_LABEL[1], "bold"),
            bg=t.get("PANEL", "#181c27"), fg=t.get("ACCENT", "#4ade80")
        ).pack(side=tk.LEFT, padx=(0, 6))

        self._input_var = tk.StringVar()
        self._entry = tk.Entry(
            frame, textvariable=self._input_var,
            font=_FONT_CONSOLE,
            bg=t.get("CARD", "#1e223"),
            fg=t.get("TEXT", "#e2e8f0"),
            insertbackground=t.get("ACCENT", "#4ade80"),
            relief=tk.FLAT,
        )
        self._entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._entry.bind("<Return>",    lambda _e: self._run_command())
        self._entry.bind("<Up>",        lambda _e: self._hist_prev())
        self._entry.bind("<Down>",      lambda _e: self._hist_next())
        self._entry.bind("<Control-l>", lambda _e: self._clear())

    # ── Printing ───────────
    def _print(self, text: str, tag: str = "output") -> None:
        self._console.config(state=tk.NORMAL)
        self._console.insert(tk.END, text, tag)
        self._console.see(tk.END)
        self._console.config(state=tk.DISABLED)

    def _println(self, text: str, tag: str = "output") -> None:
        self._print(text + "\n", tag)

    def _ensure_ansi_tag(self, tag_name: str) -> None:
        """
        Register a dynamic tag (ANSI color/style) if it does not exist yet.
        The tag name encodes the attributes, e.g.:
          'output_fgf871_bold'  → fg=#f871, bold
          'stderr_bg1e1e2e'     → bg=#1e1e2e
        """
        if tag_name in self._ansi_tag_cache:
            return
        self._ansi_tag_cache.add(tag_name)

        kw: dict = {}
        parts = tag_name.split("_")

        # Collect fg/bg/bold/italic/underline from the tag name
        font_bold   = "bold"   in parts
        font_italic = "it"     in parts
        has_ul      = "ul"     in parts

        for part in parts:
            if part.startswith("fg") and len(part) == 8:
                kw["foreground"] = "#" + part[2:]
            elif part.startswith("bg") and len(part) == 8:
                kw["background"] = "#" + part[2:]

        if font_bold and font_italic:
            kw["font"] = (_FONT_CONSOLE[0], _FONT_CONSOLE[1], "bold italic")
        elif font_bold:
            kw["font"] = (_FONT_CONSOLE[0], _FONT_CONSOLE[1], "bold")
        elif font_italic:
            kw["font"] = (_FONT_CONSOLE[0], _FONT_CONSOLE[1], "italic")

        if has_ul:
            kw["underline"] = True

        # If no fg in the tag — inherit color from base_tag (first part)
        if "foreground" not in kw:
            base = parts[0] if parts else "output"
            base_fg = {
                "output": self._theme.get("TEXT",    "#e2e8f0"),
                "stderr": self._theme.get("RED",     "#f871"),
                "error":  self._theme.get("RED",     "#f871"),
                "info":   self._theme.get("ACCENT2", "#38bdf8"),
                "dim":    self._theme.get("DIM",     "#64748b"),
                "ok":     self._theme.get("ACCENT",  "#4ade80"),
                "warn":   self._theme.get("YELLOW",  "#fbbf24"),
            }.get(base, self._theme.get("TEXT", "#e2e8f0"))
            kw["foreground"] = base_fg

        self._console.tag_config(tag_name, **kw)

    def _print_ansi(self, text: str, base_tag: str = "output") -> None:
        """
        Print text with ANSI ESC sequence handling to the console.
        If there are no ESC sequences — behaves identically to _println.
        """
        if '\x1b' not in text:
            self._println(text, base_tag)
            return
        self._console.config(state=tk.NORMAL)
        spans = _ansi_to_spans(text, base_tag)
        for fragment, tag_name in spans:
            self._ensure_ansi_tag(tag_name)
            self._console.insert(tk.END, fragment, tag_name)
        self._console.insert(tk.END, "\n")
        self._console.see(tk.END)
        self._console.config(state=tk.DISABLED)

    def _copy_selection(self, _event=None) -> str:
        """Copy selected text from the console to the clipboard (Ctrl+C)."""
        try:
            text = self._console.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.clipboard_clear()
            self.clipboard_append(text)
        except tk.TclError:
            pass  # No selection — ignore
        return "break"  # Block default behavior

    def _print_banner(self) -> None:
        self._print(_BANNER, "dim")

    def _print_separator(self) -> None:
        self._println("─" * 44, "dim")

    # ── Main dispatcher ────
    def _run_command(self) -> None:
        raw = self._input_var.get().strip()
        if not raw:
            return

        if not self._history or self._history[-1] != raw:
            self._history.append(raw)
        self._hist_idx = len(self._history)
        self._input_var.set("")

        ts = datetime.now().strftime("%H:%M:%S")
        self._println(f"[{ts}] sandbox> {raw}", "prompt")

        # Check if it is a path to a script
        path, extra_args = self._resolve_script_path(raw)
        if path:
            self._last_script = path
            self._run_script(path, extra_args)
            return

        # Check if it is a direct shell/interpreter invocation,
        # e.g. "cmd.exe /c file.bat" or "powershell -File script.ps1"
        argv = self._resolve_shell_invocation(raw)
        if argv:
            self._run_raw_command(argv)
            return

        self._handle_builtin(raw)

    def _resolve_shell_invocation(self, text: str) -> list[str] | None:
        """Recognize commands starting with a known shell/interpreter
        (cmd.exe, powershell, python, node, bash, ...) and return the full
        list of arguments for subprocess.Popen, or None if the first token is
        not a recognized shell."""
        parts = _split_commandline(text)
        if not parts:
            return None
        head = parts[0]
        # Extract just the file name from a possible full path, regardless
        # of the separator (\ on Windows, / elsewhere) — Path().name will not
        # split backslashes outside WindowsPath, so do it explicitly.
        head_name = head.replace("\\", "/").rsplit("/", 1)[-1]
        if head_name.lower() not in {s.lower() for s in _SHELL_INVOCATIONS}:
            return None
        return parts

    def _resolve_script_path(self, text: str) -> tuple[Path | None, list[str]]:
        """Check whether the text points to a script file; returns (path, extra_args)."""
        parts = _split_commandline(text)
        if not parts:
            return None, []
        p = Path(parts[0])
        if p.exists() and p.is_file():
            if p.suffix.lower() in (".bat", ".cmd", ".ps1", ".py", ".vbs", ".sh", ".js", ".lua",
                                    ".rb", ".pl", ".php", ".r", ".tcl",
                                    ".wsf", ".hta", ".reg",
                                    ".go", ".java", ".cs", ".csx", ".ts", ".coffee", ".exs"):
                return p, parts[1:]
        return None, []

    def _run_editor_content(self):
        """Run the editor content as a temporary script."""
        code = self._editor.get("1.0", "end-1c")
        if not code.strip():
            return

        # Guess the script type based on shebang or content
        first_line = code.splitlines()[0] if code else ""
        ext = ".txt"
        if first_line.startswith("#!/"):
            if "python" in first_line: ext = ".py"
            elif "bash" in first_line or "sh" in first_line: ext = ".sh"
            elif "node" in first_line: ext = ".js"
        elif self._current_lexer:
            ext = f".{self._current_lexer.aliases[0]}"

        # Save to a temporary file
        temp_dir = Path(os.environ.get("TEMP", "/tmp"))
        temp_file = temp_dir / f"sandbox_{os.getpid()}{ext}"
        temp_file.write_text(code, encoding="utf-8")

        self._last_script = temp_file
        self._run_script(temp_file)
        # The temporary file will be removed in _on_process_done

    # ── Running scripts ────
    def _run_script(self, path: Path, extra_args: list[str] | None = None) -> None:
        """Run the script in the background; stream stdout and stderr live."""
        if _logger:
            _logger.start_performance(f"script_execution_{path.name}")
        runner = _build_runner(path)
        ext = path.suffix.lower()
        if runner is None:
            ext = path.suffix.lower()
            if ext in (".bat", ".cmd", ".vbs") and not IS_WINDOWS:
                self._println(f"❌  {ext.upper()} — available on Windows only.", "error")
            elif ext == ".ps1":
                self._println("❌  PowerShell not found (powershell / pwsh).", "error")
            elif ext == ".sh":
                self._println("❌  Shell interpreter not found (bash / sh).", "error")
            elif ext == ".js":
                self._println("❌  Node.js interpreter not found (node).", "error")
            elif ext == ".lua":
                self._println("❌  Lua interpreter not found (lua / luajit).", "error")
            elif ext == ".rb":
                self._println("❌  Ruby interpreter not found (ruby).", "error")
            elif ext == ".pl":
                self._println("❌  Perl interpreter not found (perl).", "error")
            elif ext == ".php":
                self._println("❌  PHP interpreter not found (php).", "error")
            elif ext in (".r", ".R"):
                self._println("❌  R interpreter not found (Rscript).", "error")
            elif ext == ".tcl":
                self._println("❌  Tcl interpreter not found (tclsh).", "error")
            elif ext == ".wsf":
                if not IS_WINDOWS:
                    self._println("❌  .wsf — available on Windows only.", "error")
                else:
                    self._println("❌  cscript.exe not found.", "error")
            elif ext == ".hta":
                if not IS_WINDOWS:
                    self._println("❌  .hta — available on Windows only.", "error")
                else:
                    self._println("❌  mshta.exe not found.", "error")
            elif ext == ".reg":
                if not IS_WINDOWS:
                    self._println("❌  .reg — available on Windows only.", "error")
                else:
                    self._println("❌  regedit.exe not found.", "error")
            elif ext == ".go":
                self._println("❌  go tool not found (https://go.dev/dl/).", "error")
            elif ext == ".java":
                self._println("❌  java/javac not found (JDK 11+).", "error")
            elif ext in (".cs", ".csx"):
                self._println("❌  dotnet-script not found (run: dotnet tool install -g dotnet-script).", "error")
            elif ext == ".ts":
                self._println("❌  ts-node or deno not found (run: npm i -g ts-node).", "error")
            elif ext == ".coffee":
                self._println("❌  coffee not found (run: npm i -g coffeescript).", "error")
            elif ext == ".exs":
                self._println("❌  elixir not found (https://elixir-lang.org/install.html).", "error")
            else:
                self._println(f"❌  Unsupported extension: {ext!r}", "error")
            config = RUNNER_CONFIG.get(ext)
            error_msg = config.get("error") if config else f"❌  Unsupported extension: {ext!r}"
            self._println(error_msg, "error")
            if _logger:
                _logger.error(f"SANDBOX: {error_msg}", context={"file": str(path), "extension": ext})
            return

        # ── Special handling of .reg: mandatory confirmation ──────────────
        if path.suffix.lower() == ".reg":
            if self._running_proc and self._running_proc.poll() is None:
                self._println("⚠️  Previous process is still running. Click ⛔ Stop.", "warn")
                return
            from tkinter import messagebox as _mb
            confirmed = _mb.askyesno(
                "⚠️  Registry operation",
                f"The file '{path.name}' will modify the Windows registry.\n\n"
                "Invalid entries may damage the system.\n\n"
                "Are you sure you want to continue?",
                icon="warning",
            )
            if not confirmed:
                self._println("⛔  Cancelled — the registry has not been changed.", "warn")
                self._set_status("Cancelled.")
                return
            # regedit /s does not return stdout/stderr — run and wait for exit code
            self._println(f"▶  Importing to registry: {path.name}", "header")
            self._println(f"   Command: {' '.join(runner)}", "dim")
            self._print_separator()
            self._set_status(f"Importing: {path.name} …")

            def _run_reg() -> None:
                try:
                    proc = subprocess.run(runner, capture_output=True, timeout=30)
                    rc = proc.returncode
                    self.after(0, lambda: self._on_process_done(rc))
                    if rc == 0:
                        self.after(0, lambda: self._println("✅  Registry updated successfully.", "ok"))
                    else:
                        self.after(0, lambda: self._println(f"❌  regedit exited with code {rc}.", "error"))
                except subprocess.TimeoutExpired:
                    self.after(0, lambda: self._println("⏱  Timeout — regedit did not respond.", "warn"))
                except Exception as exc:
                    self.after(0, lambda e=exc: self._println(f"❌  Error: {e}", "error"))

            threading.Thread(target=_run_reg, daemon=True).start()
            return

        if self._running_proc and self._running_proc.poll() is None:
            self._println("⚠️  Previous process is still running. Click ⛔ Stop.", "warn")
            return

        self._println(f"▶  Running: {path.name}  [{path.suffix.upper()}]", "header")
        if extra_args:
            runner = runner + extra_args
        self._println(f"   Command: {' '.join(runner)}", "dim")
        self._print_separator()
        self._set_status(f"Running: {path.name} …")
        if _logger:
            _logger.info(f"SANDBOX: Running script {path.name}", context={"command": ' '.join(runner), "working_dir": str(path.parent)})

        def _run() -> None:
            try:
                enc = _detect_encoding(path)
                proc = subprocess.Popen(
                    runner,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding=enc,
                    errors="replace",
                    cwd=str(path.parent),
                    env=os.environ.copy(),
                )
                self._running_proc = proc
                self._stream_output(proc)
            except FileNotFoundError as exc:
                self.after(0, lambda e=exc: self._println(f"❌  Not found: {e}", "error"))
                if _logger:
                    _logger.error(f"SANDBOX: File not found: {exc}", context={"file": str(path)})
            except Exception as exc:
                self.after(0, lambda e=exc: self._println(f"❌  Launch error: {e}", "error"))
                if _logger:
                    _logger.error(f"SANDBOX: Launch error: {exc}", context={"file": str(path)})

        threading.Thread(target=_run, daemon=True).start()

    def _run_raw_command(self, argv: list[str]) -> None:
        """Run any shell command provided directly by the user
        (e.g. ['cmd.exe', '/c', 'D:\\script.bat'], ['powershell', '-File', '...']).
        Works like _run_script (live stdout/stderr streaming), but without
        interpreter detection based on extension — argv is already complete."""
        if self._running_proc and self._running_proc.poll() is None:
            self._println("⚠️  Previous process is still running. Click ⛔ Stop.", "warn")
            return

        self._println("▶  Running shell command", "header")
        self._println(f"   Command: {' '.join(argv)}", "dim")
        self._print_separator()
        self._set_status("Running shell command …")
        if _logger:
            _logger.info("SANDBOX: Running shell command", context={"command": ' '.join(argv)})

        def _run() -> None:
            try:
                proc = subprocess.Popen(
                    argv,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(Path.cwd()),
                    env=os.environ.copy(),
                )
                self._running_proc = proc
                self._stream_output(proc)
            except FileNotFoundError as exc:
                self.after(0, lambda e=exc: self._println(f"❌  Not found: {e}", "error"))
            except Exception as exc:
                self.after(0, lambda e=exc: self._println(f"❌  Launch error: {e}", "error"))

        threading.Thread(target=_run, daemon=True).start()

    def _stream_output(self, proc: subprocess.Popen) -> None:
        """Read stdout and stderr of proc in separate threads; print to the console with ANSI support."""
        lock = threading.Lock()

        def _read(stream, tag: str) -> None:
            for line in stream:
                line_s = line.rstrip("\n")
                with lock:
                    self.after(0, lambda l=line_s, t=tag: self._print_ansi(l, t))
            stream.close()

        t_out = threading.Thread(target=_read, args=(proc.stdout, "output"), daemon=True)
        t_err = threading.Thread(target=_read, args=(proc.stderr, "stderr"), daemon=True)
        t_out.start()
        t_err.start()

        def _wait() -> None:
            t_out.join()
            t_err.join()
            rc = proc.wait()
            self.after(0, lambda: self._on_process_done(rc))

        threading.Thread(target=_wait, daemon=True).start()

    def _on_process_done(self, returncode: int) -> None:
        self._print_separator()
        tag = "ok" if returncode == 0 else "error"
        icon = "✅" if returncode == 0 else "❌"
        self._println(f"{icon}  Finished. Exit code: {returncode}", tag)
        self._set_status(f"Finished (code {returncode})")
        # Delete the temporary file if it was one
        if self._last_script and self._last_script.name.startswith("sandbox_"):
            if self._last_script.exists():
                self._last_script.unlink()
        self._running_proc = None

    # ── Stop ───────────────
    def _stop_process(self) -> None:
        proc = self._running_proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    self._println("⛔  Process killed (SIGKILL).", "warn")
                    if _logger:
                        _logger.warning("SANDBOX: Process killed (SIGKILL)")
                else:
                    self._println("⛔  Process terminated.", "warn")
                    if _logger:
                        _logger.info("SANDBOX: Process terminated")
                self._set_status("Terminated.")
            except Exception as exc:
                self._println(f"⚠️  Cannot stop: {exc}", "error")
                if _logger:
                    _logger.error(f"SANDBOX: Failed to stop process: {exc}")
        else:
            self._println("ℹ️  No active process.", "dim")

    # ── Test / syntax verification ────────────
    def _test_current(self) -> None:
        """Test the script from the input field or the last one run."""
        raw = self._input_var.get().strip()
        path, _ = self._resolve_script_path(raw) if raw else (self._last_script, [])
        if not path:
            self._println("ℹ️  Enter a script path or run it first.", "dim")
            return
        self._test_script(path)

    def _test_editor_content(self) -> None:
        """Test the syntax of the editor content."""
        # Works like _run_editor_content, but calls _test_script instead of _run_script.
        # The logic is nearly identical, so it could be merged for brevity,
        # but keep it separate for clarity for now.
        code = self._editor.get("1.0", "end-1c")
        if not code.strip(): return
        first_line = code.splitlines()[0] if code else ""
        ext = ".txt"
        if first_line.startswith("#!/"):
            if "python" in first_line: ext = ".py"
            elif "bash" in first_line or "sh" in first_line: ext = ".sh"
        elif self._current_lexer:
            ext = f".{self._current_lexer.aliases[0]}"

        temp_dir = Path(os.environ.get("TEMP", "/tmp"))
        temp_file = temp_dir / f"sandbox_test_{os.getpid()}{ext}"
        temp_file.write_text(code, encoding="utf-8")

        self._test_script(temp_file)
        # The temporary file will be removed in _test_script

    def _test_script(self, path: Path) -> None:
        """Syntax verification without running."""
        if _logger:
            _logger.start_performance(f"syntax_check_{path.name}")
        self._println(f"🔬  Testing: {path.name}", "header")
        self._set_status(f"Testing: {path.name} …")

        def _run_test() -> None:
            try:
                ok, msg = _syntax_check(path)
                tag = "ok" if ok else "error"
                icon = "✅" if ok else "❌"
                self.after(0, lambda: self._println(f"   {icon}  {msg}", tag))
                self.after(0, lambda: self._set_status(f"Test: {'OK' if ok else 'ERROR'}"))
                if _logger:
                    if ok:
                        _logger.info(f"SANDBOX: Syntax check passed for {path.name}")
                    else:
                        _logger.error(f"SANDBOX: Syntax check failed for {path.name}: {msg}")
            except subprocess.TimeoutExpired:
                self.after(0, lambda: self._println("   ⏱  Syntax verification timeout.", "warn"))
                if _logger:
                    _logger.warning(f"SANDBOX: Syntax check timeout for {path.name}")
            except Exception as exc:
                self.after(0, lambda e=exc: self._println(f"   ❌  Test error: {e}", "error"))
                if _logger:
                    _logger.error(f"SANDBOX: Syntax check error for {path.name}: {exc}")
            finally:
                if _logger:
                    _logger.end_performance(f"syntax_check_{path.name}")
                if path.name.startswith("sandbox_test_"):
                    if path.exists():
                        path.unlink()

        threading.Thread(target=_run_test, daemon=True).start()

    # ── Open file via dialog ────────────
    def _browse_script(self) -> None:
        ftypes = [
            ("Scripts",           "*.bat;*.cmd;*.ps1;*.py;*.vbs;*.sh;*.js;*.lua;*.rb;*.pl;*.php;*.r;*.tcl;*.wsf;*.hta;*.reg;*.go;*.java;*.cs;*.csx;*.ts;*.coffee;*.exs"),
            ("Batch / CMD",       "*.bat;*.cmd"),
            ("PowerShell",        "*.ps1"),
            ("Python",            "*.py"),
            ("VBScript",          "*.vbs"),
            ("Shell",             "*.sh"),
            ("JavaScript",        "*.js"),
            ("Lua",               "*.lua"),
            ("Ruby",              "*.rb"),
            ("Perl",              "*.pl"),
            ("PHP",               "*.php"),
            ("R",                 "*.r;*.R"),
            ("Tcl",               "*.tcl"),
            ("Windows Script",    "*.wsf"),
            ("HTA",               "*.hta"),
            ("Registry",          "*.reg"),
            ("Go",                "*.go"),
            ("Java",              "*.java"),
            ("C# Script",         "*.cs;*.csx"),
            ("TypeScript",        "*.ts"),
            ("CoffeeScript",      "*.coffee"),
            ("Elixir",            "*.exs"),
            ("All files",         "*.*"),
        ]
        _default_dir = Path(__file__).parent.parent / "scripts"
        _default_dir.mkdir(parents=True, exist_ok=True)
        path = filedialog.askopenfilename(
            title="Select a script to run",
            filetypes=ftypes,
            initialdir=str(_default_dir.resolve()),
        )
        if path:
            p = Path(path)
            self._input_var.set(str(p))
            self._last_script = p
            content, _ = _read_source(p)
            self._editor.delete("1.0", "end")
            self._editor.insert("1.0", content)
            self._println(f"📂  Loaded: {p.name}  ({p.suffix.upper()})", "info")
            self._set_status(f"Ready: {p.name}")
            self._update_lexer_from_path(path)

    # ── Built-in commands ────────────
    def _handle_builtin(self, cmd: str) -> None:
        lower = cmd.lower().strip()

        if lower in ("help", "?", "pomoc"):
            self._println(
                "Available sandbox commands:\n"
                "  help / ?          — this list\n"
                "  clear / cls       — clear the console\n"
                "  version           — module version\n"
                "  env               — environment variables\n"
                "  runners           — show available interpreters\n"
                "  stop              — terminate the active process\n"
                "  test <file>       — check syntax without running\n"
                "  run  <file>       — run a script (.bat .cmd .ps1 .py .vbs .sh .js .lua .rb .pl .php .r .tcl .wsf .hta .reg .go .java .cs .csx .ts .coffee .exs)\n"
                "  <file>            — run by entering just the file path\n"
                "  cmd.exe /c <file> — run through a shell (also: powershell, pwsh, bash, python, node, ...)\n"
                "  Ctrl+L            — clear the console (shortcut)\n",
                "info"
            )

        elif lower in ("clear", "cls"):
            self._clear()
            return

        elif lower == "version":
            self._println(f"sandbox v{__version__}  ·  {__author__}  ·  {__company__}", "info")

        elif lower == "env":
            lines = [f"  {k}={v}" for k, v in sorted(os.environ.items())]
            self._println("Environment variables:\n" + "\n".join(lines[:40]), "dim")
            if len(lines) > 40:
                self._println(f"  … (+{len(lines)-40} more)", "dim")

        elif lower == "runners":
            self._show_runners()

        elif lower == "stop":
            self._stop_process()

        elif lower.startswith("test "):
            arg = lower[5:].strip().strip("'\"")
            path = Path(arg)
            if path.exists():
                self._test_script(path)
            else:
                self._println(f"❌  File does not exist: {arg!r}", "error")

        elif lower.startswith("run "):
            arg = cmd[4:].strip().strip("'\"")
            parts = arg.split()
            path = Path(parts[0]) if parts else Path(arg)
            extra = parts[1:] if len(parts) > 1 else []
            if path.exists():
                self._last_script = path
                self._run_script(path, extra)
            else:
                self._println(f"❌  File does not exist: {arg!r}", "error")

        else:
            self._println(f"[sandbox] Unknown command: '{cmd}'", "error")
            self._println("  Type 'help' to see available commands.", "dim")

        self._set_status(f"Last: {cmd!r}")

    def _show_runners(self) -> None:
        """Show available interpreters/runners."""
        self._println("Available interpreters:", "header")

        py = _find_python()
        self._println(f"  Python  : {py}", "info" if py else "dim")

        ps = shutil.which("powershell") or shutil.which("pwsh")
        self._println(f"  PS      : {ps or '(unavailable)'}", "info" if ps else "dim")

        if IS_WINDOWS:
            cmd_exe = shutil.which("cmd")
            cs = shutil.which("cscript")
            self._println(f"  CMD     : {cmd_exe or '(unavailable)'}", "info" if cmd_exe else "dim")
            self._println(f"  cscript : {cs or '(unavailable)'}", "info" if cs else "dim")
        else:
            self._println("  CMD/VBS : (Windows only)", "dim")

        sh = _find_shell()
        self._println(f"  Shell   : {sh or '(unavailable — bash/sh)'}", "info" if sh else "dim")

        node = _find_node()
        self._println(f"  Node    : {node or '(unavailable)'}", "info" if node else "dim")

        lua = _find_lua()
        self._println(f"  Lua     : {lua or '(unavailable)'}", "info" if lua else "dim")

        luac = _find_luac()
        self._println(
            f"  luac    : {luac or '(unavailable — Lua syntax test unavailable)'}",
            "info" if luac else "dim"
        )

        rb = _find_ruby()
        self._println(f"  Ruby    : {rb or '(unavailable)'}", "info" if rb else "dim")

        pl = _find_perl()
        self._println(f"  Perl    : {pl or '(unavailable)'}", "info" if pl else "dim")

        php = _find_php()
        self._println(f"  PHP     : {php or '(unavailable)'}", "info" if php else "dim")

        rs = _find_rscript()
        self._println(f"  Rscript : {rs or '(unavailable)'}", "info" if rs else "dim")

        tcl = _find_tclsh()
        self._println(f"  Tcl     : {tcl or '(unavailable)'}", "info" if tcl else "dim")

        if IS_WINDOWS:
            cs = shutil.which("cscript")
            self._println(f"  WSF     : {cs or '(unavailable — cscript.exe)'}", "info" if cs else "dim")
            mshta = _find_mshta()
            self._println(f"  HTA     : {mshta or '(unavailable — mshta.exe)'}", "info" if mshta else "dim")
            regedit = shutil.which("regedit") or (r"C:\Windows\regedit.exe" if os.path.isfile(r"C:\Windows\regedit.exe") else None)
            self._println(f"  REG     : {regedit or '(unavailable — regedit.exe)'}", "info" if regedit else "dim")
        else:
            self._println("  WSF/HTA/REG : (Windows only)", "dim")

        go = _find_go()
        self._println(f"  Go      : {go or '(unavailable)'}", "info" if go else "dim")

        java, javac = _find_java()
        self._println(f"  Java    : {java or '(unavailable)'}", "info" if java else "dim")
        self._println(f"  javac   : {javac or '(unavailable — Java syntax test unavailable)'}", "info" if javac else "dim")

        ds = _find_dotnet_script()
        self._println(f"  C#/CSX  : {ds or '(unavailable — dotnet-script)'}", "info" if ds else "dim")

        ts_runner, ts_mode = _find_ts_runner()
        ts_label = f"{ts_runner} [{ts_mode}]" if ts_runner else "(unavailable — ts-node / deno)"
        self._println(f"  TS      : {ts_label}", "info" if ts_runner else "dim")

        coffee = _find_coffee()
        self._println(f"  Coffee  : {coffee or '(unavailable)'}", "info" if coffee else "dim")

        elixir = _find_elixir()
        self._println(f"  Elixir  : {elixir or '(unavailable)'}", "info" if elixir else "dim")

    # ── Toolbar actions ────
    def _clear(self) -> None:
        self._console.config(state=tk.NORMAL)
        self._console.delete("1.0", tk.END)
        self._console.config(state=tk.DISABLED)
        self._set_status("Cleared.")

    def _toggle_always_on_top(self) -> None:
        """Toggle always on top window state."""
        self._always_on_top = not self._always_on_top
        self.attributes('-topmost', self._always_on_top)
        status = "enabled" if self._always_on_top else "disabled"
        self._set_status(f"Always on top: {status}")
        if _logger:
            _logger.info(f"SANDBOX: Always on top {status}")

    def _save_log(self) -> None:
        """Save the console content to a file."""
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")],
            title="Save sandbox log",
        )
        if not path:
            return
        try:
            content = self._console.get("1.0", tk.END)
            Path(path).write_text(content, encoding="utf-8")
            self._set_status(f"Log saved: {path}")
        except Exception as exc:
            self._println(f"[save error] {exc}", "error")

    def _save_editor_content(self) -> Path | None:
        """Save the editor content to a file."""
        path = filedialog.asksaveasfilename(
            filetypes=[("All files", "*.*")],
            title="Save script from sandbox",
        )
        if not path:
            return None
        try:
            content = self._editor.get("1.0", "end-1c")
            Path(path).write_text(content, encoding="utf-8")
            self._set_status(f"Script saved: {path}")
            self._update_lexer_from_path(path)
            return Path(path)
        except Exception as exc:
            self._println(f"[save error] {exc}", "error")
            return None

    # ── Command history ────
    def _hist_prev(self) -> None:
        if not self._history:
            return
        self._hist_idx = max(0, self._hist_idx - 1)
        self._input_var.set(self._history[self._hist_idx])
        self._entry.icursor(tk.END)

    def _hist_next(self) -> None:
        if not self._history:
            return
        self._hist_idx = min(len(self._history), self._hist_idx + 1)
        self._input_var.set(
            self._history[self._hist_idx] if self._hist_idx < len(self._history) else ""
        )
        self._entry.icursor(tk.END)

    def _add_to_pslauncher(self):
        """Save the script and add it to the main application."""
        app = self._main_app_ref() if self._main_app_ref else None
        if not app:
            return
        # First save the file
        saved_path = self._save_editor_content()
        if not saved_path:
            return
        # Add to psLauncher
        app._add_script_entry(str(saved_path))
        app._refresh_tree()
        app._schedule_save()
        self._set_status(f"Added to psLauncher: {saved_path.name}")

    # ── Syntax Highlighting ────
    def _configure_pygments_tags(self):
        is_dark = self._theme.get("DARK", "#0f1117").startswith("#0")
        style_name = "monokai" if is_dark else "default"
        try:
            style = get_style_by_name(style_name)
        except Exception:
            return

        for ttype, sdef in style:
            tag_name = str(ttype)
            kw = {}
            if sdef['color']: kw['foreground'] = f"#{sdef['color']}"
            if sdef['bold']: kw['font'] = (_FONT_CONSOLE[0], _FONT_CONSOLE[1], "bold")
            if sdef['italic']: kw['font'] = (_FONT_CONSOLE[0], _FONT_CONSOLE[1], "italic")
            if sdef['underline']: kw['underline'] = True
            self._editor.tag_configure(tag_name, **kw)

    def _on_editor_modified(self, event=None):
        self._editor.edit_modified(False) # reset flag
        if not _PYGMENTS_AVAILABLE or not self._current_lexer:
            return
        # Simple highlighting of the entire text on every change.
        # For large files this could be optimized to highlight only the changed line.
        code = self._editor.get("1.0", "end-1c")
        self._editor.mark_set("range_start", "1.0")
        for ttype, value in self._current_lexer.get_tokens(code):
            self._editor.mark_set("range_end", f"range_start + {len(value)}c")
            self._editor.tag_add(str(ttype), "range_start", "range_end")
            self._editor.mark_set("range_start", "range_end")

    def _update_lexer_from_path(self, path: str | Path):
        if not _PYGMENTS_AVAILABLE: return
        try:
            self._current_lexer = get_lexer_for_filename(str(path))
            self._on_editor_modified()
        except Exception:
            self._current_lexer = TextLexer()

    # ── Status ─────────────
    def _set_status(self, text: str) -> None:
        self._status_lbl.config(text=text)

    # ── Closing the window ──
    def _on_close(self) -> None:
        self._stop_process()
        self.destroy()


# ─────────────
# Public API of the module
# ─────────────

_sandbox_ref: "weakref.ref[SandboxWindow] | None" = None


def open_sandbox(parent: tk.Widget, theme: dict, initial_path: str | None = None) -> SandboxWindow:
    """Opens the sandbox window. If it already exists and is visible, restores focus."""
    global _sandbox_ref
    if _sandbox_ref is not None:
        win = _sandbox_ref()
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus_set()
            if initial_path: win._load_file(initial_path)
            return win
    win = SandboxWindow(parent, theme, initial_path=initial_path)
    win.transient(parent)
    _sandbox_ref = weakref.ref(win)
    return win
