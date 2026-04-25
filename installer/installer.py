from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tkinter as tk
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_NAME = "Local Compute MCP"
EXE_NAME = "LocalCompute.exe"


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


class Installer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} Setup")
        self.geometry("680x460")
        self.resizable(False, False)

        self.install_dir = tk.StringVar(value=str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "LocalComputeMCP"))
        self.desktop_shortcut = tk.BooleanVar(value=True)
        self.start_shortcut = tk.BooleanVar(value=True)
        self.open_after = tk.BooleanVar(value=True)
        self.page = 0
        self.pages: list[ttk.Frame] = []

        self._style()
        self._build()
        self._show_page(0)

    def _style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Heading.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Accent.TButton", padding=(14, 8), font=("Segoe UI", 10, "bold"))

    def _build(self) -> None:
        self.container = ttk.Frame(self, padding=22)
        self.container.pack(fill="both", expand=True)
        self.container.rowconfigure(0, weight=1)
        self.container.columnconfigure(0, weight=1)

        self.pages = [self._welcome_page(), self._options_page(), self._install_page(), self._done_page()]
        for page in self.pages:
            page.grid(row=0, column=0, sticky="nsew")

        bottom = ttk.Frame(self, padding=(22, 0, 22, 18))
        bottom.pack(fill="x")
        self.back_btn = ttk.Button(bottom, text="Back", command=self._back)
        self.back_btn.pack(side="left")
        self.next_btn = ttk.Button(bottom, text="Next", style="Accent.TButton", command=self._next)
        self.next_btn.pack(side="right")
        self.cancel_btn = ttk.Button(bottom, text="Cancel", command=self.destroy)
        self.cancel_btn.pack(side="right", padx=(0, 8))

    def _welcome_page(self) -> ttk.Frame:
        frame = ttk.Frame(self.container)
        ttk.Label(frame, text=APP_NAME, style="Title.TLabel").pack(anchor="w", pady=(20, 12))
        ttk.Label(frame, text="Install the double-click app for registering PCs, testing SSH, and running distributed jobs.", wraplength=580).pack(anchor="w")
        ttk.Label(frame, text="Works on the same Wi-Fi, Tailscale, or ZeroTier. Use the IP shown by that network in the app.", wraplength=580).pack(anchor="w", pady=(16, 0))
        return frame

    def _options_page(self) -> ttk.Frame:
        frame = ttk.Frame(self.container)
        ttk.Label(frame, text="Install Options", style="Heading.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(20, 16))
        ttk.Label(frame, text="Install folder").grid(row=1, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.install_dir, width=62).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 14))
        ttk.Button(frame, text="Browse", command=self._browse).grid(row=2, column=2, padx=(8, 0), pady=(6, 14))
        ttk.Checkbutton(frame, text="Create desktop shortcut", variable=self.desktop_shortcut).grid(row=3, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Checkbutton(frame, text="Create Start Menu shortcut", variable=self.start_shortcut).grid(row=4, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Checkbutton(frame, text="Open app after install", variable=self.open_after).grid(row=5, column=0, columnspan=3, sticky="w", pady=4)
        frame.columnconfigure(0, weight=1)
        return frame

    def _install_page(self) -> ttk.Frame:
        frame = ttk.Frame(self.container)
        ttk.Label(frame, text="Installing", style="Heading.TLabel").pack(anchor="w", pady=(20, 12))
        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 12))
        self.status = tk.Text(frame, height=13, wrap="word", font=("Consolas", 9))
        self.status.pack(fill="both", expand=True)
        return frame

    def _done_page(self) -> ttk.Frame:
        frame = ttk.Frame(self.container)
        ttk.Label(frame, text="Installation Complete", style="Title.TLabel").pack(anchor="w", pady=(20, 12))
        ttk.Label(frame, text="You can now open Local Compute MCP from the shortcut or installed folder.", wraplength=580).pack(anchor="w")
        ttk.Label(frame, text="First create a shared disk on A/main PC if you plan to use B/C workers.", wraplength=580).pack(anchor="w", pady=(16, 0))
        return frame

    def _browse(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.install_dir.get())
        if selected:
            self.install_dir.set(selected)

    def _show_page(self, page: int) -> None:
        self.page = page
        self.pages[page].tkraise()
        self.back_btn.configure(state="normal" if page > 0 and page != 2 else "disabled")
        self.cancel_btn.configure(state="normal" if page != 3 else "disabled")
        self.next_btn.configure(text="Install" if page == 1 else "Finish" if page == 3 else "Next")

    def _back(self) -> None:
        self._show_page(max(0, self.page - 1))

    def _next(self) -> None:
        if self.page == 0:
            self._show_page(1)
        elif self.page == 1:
            self._show_page(2)
            self.after(100, self._install)
        elif self.page == 3:
            self.destroy()

    def _log(self, text: str) -> None:
        self.status.insert("end", text + "\n")
        self.status.see("end")
        self.update_idletasks()

    def _install(self) -> None:
        self.back_btn.configure(state="disabled")
        self.next_btn.configure(state="disabled")
        self.cancel_btn.configure(state="disabled")
        try:
            target = Path(self.install_dir.get()).expanduser().resolve()
            payload = resource_path("payload.zip")
            if not payload.exists():
                raise FileNotFoundError(f"Missing payload: {payload}")

            self._log(f"Installing to {target}")
            target.mkdir(parents=True, exist_ok=True)
            self.progress["value"] = 20

            with zipfile.ZipFile(payload, "r") as archive:
                archive.extractall(target)
            self.progress["value"] = 65
            self._log("Files copied.")

            exe_path = target / EXE_NAME
            if self.desktop_shortcut.get():
                self._create_shortcut(Path.home() / "Desktop" / f"{APP_NAME}.lnk", exe_path, target)
                self._log("Desktop shortcut created.")
            if self.start_shortcut.get():
                start_dir = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME
                start_dir.mkdir(parents=True, exist_ok=True)
                self._create_shortcut(start_dir / f"{APP_NAME}.lnk", exe_path, target)
                self._log("Start Menu shortcut created.")

            self.progress["value"] = 100
            if self.open_after.get() and exe_path.exists():
                subprocess.Popen([str(exe_path)], cwd=str(target))
            self._show_page(3)
            self.next_btn.configure(state="normal")
        except Exception as exc:
            messagebox.showerror("Install failed", str(exc))
            self._log(f"ERROR: {exc}")
            self.cancel_btn.configure(state="normal")

    def _create_shortcut(self, shortcut_path: Path, target_path: Path, workdir: Path) -> None:
        script = (
            "$shell=New-Object -ComObject WScript.Shell;"
            f"$s=$shell.CreateShortcut('{shortcut_path}');"
            f"$s.TargetPath='{target_path}';"
            f"$s.WorkingDirectory='{workdir}';"
            "$s.Save()"
        )
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], check=True)


def main() -> int:
    app = Installer()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
