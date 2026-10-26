import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from dataclasses import dataclass
import subprocess
import os
import sys
import threading
import queue

# --- mapowanie rozszerzen na handlery ----------------------------------
# kazdy wpis: rozszerzenie -> (argv bez sciezki pliku, uzyc_shell, pytac_o_admina)
# To JEDYNE miejsce, w ktorym rozstrzyga sie, jak uruchomic dane rozszerzenie.
# ``handler_for_file`` zwraca wszystkie trzy decyzje naraz, a ``get_command_for_file``
# to cienki wrapper na ``handler_for_file(...).argv``, wiec komenda i wynikajace
# z niej flagi (shell, admin) nie moga sie rozjechac.
SCRIPT_HANDLERS = {
    '.ps1': (['powershell.exe', '-NoProfile', '-ExecutionPolicy',
              'Unrestricted', '-File'], False, False),
    '.vbs': (['cscript.exe'], False, True),
    '.js':  (['cscript.exe'], False, True),
    '.wsf': (['cscript.exe'], False, True),
    '.hta': (['mshta.exe'], False, True),
    '.bat': ([], True, True),
    '.cmd': ([], True, True),
}


@dataclass(frozen=True)
class ScriptCommand:
    """Komenda uruchomieniowa wraz z decyzjami, ktore z niej wynikaja.

    Trzymanie argv, wymagania shella i pytania o admina razem gwarantuje, ze
    nie rozjada sie, gdy zmieni sie rozszerzenie lub handler.
    """

    argv: list[str]
    use_shell: bool
    ask_admin: bool


def get_command_for_file(file_path: str) -> list[str]:
    """Determines the correct command to run a script based on its native Windows handler.

    Only the argv is returned here; callers that also need the shell/admin
    decisions must use :func:`handler_for_file` so both come from the same
    entry in ``SCRIPT_HANDLERS``.
    """
    return handler_for_file(file_path).argv


def handler_for_file(file_path: str) -> ScriptCommand:
    """Zwroc komende i wynikajace z niej decyzje (shell, admin) dla pliku."""
    _, extension = os.path.splitext(file_path)
    extension = extension.lower()

    if extension in SCRIPT_HANDLERS:
        prefix, use_shell, admin = SCRIPT_HANDLERS[extension]
        return ScriptCommand(list(prefix) + [file_path], use_shell, admin)
    if extension == '.py':
        return ScriptCommand([sys.executable, file_path], False, True)
    # nieznane rozszerzenie: uruchom bezposrednio, bez shella
    return ScriptCommand([file_path], False, True)

def _ps_quote(arg: str) -> str:
    """Quote a single argument for a PowerShell -Command argument list.

    Single quotes are the only metacharacter inside a PowerShell single-quoted
    string, and they are escaped by doubling them.
    """
    return "'" + arg.replace("'", "''") + "'"


def _build_elevate_command(interpreter: str, arguments: list[str]) -> str:
    """Build the PowerShell one-liner that relaunches *interpreter* elevated.

    ``powershell.exe`` gets ``-NoExit`` so the elevated console stays open and
    the user can read the script's output.
    """
    args = list(arguments)
    if os.path.basename(interpreter).lower() == 'powershell.exe':
        args.insert(0, '-NoExit')
    quoted = ", ".join(_ps_quote(arg) for arg in args)
    return (f"Start-Process -FilePath {_ps_quote(interpreter)} "
            f"-ArgumentList @({quoted}) -Verb RunAs")


def _build_output_window() -> tuple[tk.Toplevel, scrolledtext.ScrolledText]:
    """Create the black-on-white output window for a running script.

    Returns the toplevel window and its read-only text area so the caller can
    keep streaming logic separate from widget construction.
    """
    output_window = tk.Toplevel()
    output_window.title("Running Script...")
    output_window.geometry("800x600")
    text_area = scrolledtext.ScrolledText(
        output_window, wrap=tk.WORD, width=100, height=40,
        bg="black", fg="white")
    text_area.pack(expand=True, fill='both')
    text_area.configure(state='disabled')
    return output_window, text_area


def stream_script_output(command: list[str], use_shell: bool) -> None:
    """Creates a window and streams the output of a command in real-time."""

    output_window, text_area = _build_output_window()

    # set when the user closes the window; stops the update loop from touching
    # widgets that no longer exist
    closed = False
    process = None
    thread = None

    def on_close():
        nonlocal closed
        closed = True
        # the reader thread is blocked on the child's stdout; kill the child
        # first so the pipe closes and the thread (and its process handle) is
        # released instead of lingering as a zombie
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # terminate() was ignored (console script/child tree): escalate
                process.kill()
                # reap the killed child so its handle is not leaked
                try:
                    process.wait(timeout=2)
                except (subprocess.TimeoutExpired, OSError):
                    pass
            except OSError:
                pass
        # join the reader so it stops touching the closed pipe before the
        # window is destroyed
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)
        output_window.destroy()

    output_window.protocol("WM_DELETE_WINDOW", on_close)

    def reader_thread(proc, q):
        """Reads output from the process and puts it into a queue."""
        try:
            for line in iter(proc.stdout.readline, ''):
                q.put(line)
            proc.wait()
        finally:
            q.put(None) # Signal that the process is done

    def _poll_output():
        """Drain the reader queue into the text area and reschedule.

        Kept separate from the window setup so the streaming loop can be
        reasoned about (and tested) on its own; a ``None`` sentinel marks the
        end of the stream.
        """
    def update_gui():
        """Checks the queue for new output and updates the text area."""
        if closed or not output_window.winfo_exists():
            return
        try:
            while True:
                line = q.get_nowait()
                if line is None: # End of stream
                    output_window.title(f"Script Finished (Code: {process.returncode})")
                    return
                text_area.configure(state='normal')
                text_area.insert(tk.END, line)
                text_area.see(tk.END) # Auto-scroll
                text_area.configure(state='disabled')
        except queue.Empty:
            output_window.after(100, _poll_output)

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Combine stdout and stderr
            text=True,
            shell=use_shell,
            encoding='utf-8',
            errors='ignore'
        )

        q = queue.Queue()
        thread = threading.Thread(target=reader_thread, args=(process, q))
        thread.daemon = True
        thread.start()

        _poll_output()

    except FileNotFoundError:
        output_window.destroy()
        interpreter = os.path.basename(command[0])
        messagebox.showerror("Error", f"Interpreter '{interpreter}' not found.\nMake sure it is installed and in your system's PATH.")
    except Exception as e:
        output_window.destroy()
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")


def main() -> None:
    root = tk.Tk()
    root.withdraw()

    try:
        _run_launcher_ui()
    finally:
        # ukryty root musi zostac zwolniony, inaczej kolejne uruchomienia
        # zostawialyby za soba zywe interpretery Tk; TclError wystepuje gdy
        # okno zostalo juz zniszczone (np. przez zamkniecie ostatniego toplevela)
        try:
            if root.winfo_exists():
                root.destroy()
        except tk.TclError:
            pass


def _run_launcher_ui():
    """Pokaz okno wyboru pliku i uruchom wybrany skrypt."""
    file_types = [
        ("Native Windows Scripts", "*.ps1;*.bat;*.cmd;*.vbs;*.js;*.wsf;*.hta"),
        ("All files", "*.*")
    ]

    file_path = filedialog.askopenfilename(title="Select a script to run", filetypes=file_types)

    if not file_path:
        return

    # komenda, decyzja o shellu i pytanie o admina pochodza z tego samego
    # mapowania rozszerzen, wiec nie moga sie rozjechac
    handler = handler_for_file(file_path)
    command = handler.argv

    run_as_admin = (handler.ask_admin and messagebox.askyesno(
        "Run as Administrator?",
        "Do you want to run this script with administrator privileges?"))

    try:
        if run_as_admin:
            _run_elevated(command[0], command[1:])
        else:
            stream_script_output(command, handler.use_shell)

    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")


def _run_elevated(interpreter: str, arguments: list[str]) -> None:
    """Relaunch the script through a UAC prompt.

    Reports whether the interpreter is missing or the user declined elevation
    instead of failing with a generic dialog.
    """
    elevate_command = _build_elevate_command(interpreter, arguments)
    try:
        subprocess.run(['powershell', '-Command', elevate_command], check=True)
    except FileNotFoundError:
        # ``powershell`` itself may be missing from PATH, or the target
        # interpreter may be missing; report which one so the user can act
        messagebox.showerror(
            "Error",
            f"Interpreter '{os.path.basename(interpreter)}' not found.\n"
            "Make sure it is installed and in your system's PATH.")
    except subprocess.CalledProcessError as e:
        # Start-Process -Verb RunAs zwraca blad gdy uzytkownik odmowi UAC;
        # podniesienie uprawnien moglo tez nie wystartowac w ogole
        messagebox.showerror(
            "Error",
            "Nie udalo sie uruchomic z podniesionymi uprawnieniami.\n"
            "Podniesienie uprawnien zostalo anulowane lub odrzucone przez UAC."
            f"\n\n{e}")
    except OSError as e:
        messagebox.showerror(
            "Error",
            f"Nie udalo sie uruchomic polecenia podniesienia uprawnien: {e}")


if __name__ == "__main__":
    main()