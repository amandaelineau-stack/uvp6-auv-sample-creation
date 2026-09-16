from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Protocol, Sequence

class Prompter(Protocol):
    def choose_directory(self, title: str, initial: Optional[Path] = None) -> Optional[Path]: ...
    def choose_option(self, title: str, message: str, 
                      options: Sequence[str], default: str) -> Optional[str]: ...
    def confirm(self, title: str, message: str, default: bool = False) -> bool:...


class NullPrompter:
    def choose_directory(self, title, initial=None):
        raise RuntimeError(f"{title}: no interactive prompt available, please pass the value explicitly")

    def choose_option(self, title, message, options, default):
        raise RuntimeError(f"{title}: no interactive prompt available, please pass the value explicitly")

    def confirm(self, title, message, default=False):
        raise RuntimeError(f"{title}: no interactive prompt available, rerun with assume_yes=True")


class ConsolePrompter:
    def choose_directory(self, title, initial=None):
        raw = input(f"{title}: ".strip().strip('"'))
        return Path(raw) if raw else None

    def choose_option(self, title, message, options, default):
        return input(f"{message} ").strip() or default

    def confirm(self, title, message, default=False):
        answer = input(f"{message} ").strip().lower()
        return default if not answer else answer.startswith("y")


class TkPrompter:
    def __init__(self):
        self._root = None

    def _ready(self):
        if self._root is None:
            import tkinter as tk
            self._root = tk.Tk()
            self._root.withdraw()
        self._root.attributes("-topmost", True)
        self._root.update()
        return self._root

    def choose_directory(self, title, initial=None):
        from tkinter import filedialog
        root = self._ready()
        chosen = filedialog.askdirectory(
            title=title, mustexist=True, parent=root,
            initialdir=str(initial) if initial else None)
        return Path(chosen) if chosen else None

    def choose_option(self, title, message, options, default):
        from tkinter import simpledialog
        root = self._ready()
        answer = simpledialog.askstring(
            title, f"{message}\n\n({'/'.join(options)})", initialvalue=default, parent=root)
        return None if answer is None else (answer.strip() or default)

    def confirm(self, title, message, default=False):
        from tkinter import messagebox
        root = self._ready()
        return bool(messagebox.askyesno(
            title, message, parent=root, default="yes" if default else "no"))
        
    def close(self):
        if self._root is not None:
            self._root.destroy()
            self._root = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

def get_prompter(mode: str = "auto") -> Prompter:
    if mode == "none":
        return NullPrompter()
    if mode == "console":
        return ConsolePrompter()
    if mode in ("gui", "auto"):
        try:
            import tkinter  # noqa: F401
            return TkPrompter()
        except Exception:
            if mode == "gui":
                raise
    if sys.stdin is not None and sys.stdin.isatty():
        return ConsolePrompter()
    return NullPrompter()

