from __future__ import annotations

import csv
import json
import queue
import subprocess
import sys
import threading
import webbrowser
import winsound
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from .config import Worker, load_all_workers, load_workers, save_workers
from .discovery import NetworkDevice, discover_same_wifi
from .pairing import PairingServer, find_pairing_code
from .runner import discover_jobs, retry_failed, run_jobs, test_worker


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


APP_DIR = app_dir()
CONFIG_PATH = APP_DIR / "workers.yaml"
SOUND_CONFIG_PATH = APP_DIR / "sound_hub.json"


class LocalComputeApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Local Compute")
        self.geometry("1140x760")
        self.minsize(1000, 680)

        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.workers: list[Worker] = []
        self.pages: dict[str, ttk.Frame] = {}
        self.pairing_server: PairingServer | None = None

        self.folder_var = tk.StringVar(value=str(APP_DIR / "samples" / "input"))
        self.output_var = tk.StringVar(value=str(APP_DIR / "outputs"))
        self.logs_var = tk.StringVar(value=str(APP_DIR / "logs"))
        self.pattern_var = tk.StringVar(value="*.txt")
        self.command_var = tk.StringVar(value="python samples\\sample_worker.py {input_q} {output_dir_q}")
        self.job_type_var = tk.StringVar(value="Sample test")
        self.advanced_visible = tk.BooleanVar(value=False)

        self.master_volume = tk.IntVar(value=80)
        self.sound_mode = tk.StringVar(value="This PC receives audio")
        self.sound_status_var = tk.StringVar(value="Sound Hub is ready. Audio streaming tool integration is the next step.")
        self.sound_rows: dict[str, dict[str, object]] = {}

        self._style()
        self._build()
        self._load_workers()
        self._load_sound_config()
        self._show("devices")
        self._poll_queue()

    def _style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Side.TFrame", background="#222831")
        style.configure("SideTitle.TLabel", background="#222831", foreground="white", font=("Segoe UI", 16, "bold"))
        style.configure("SideText.TLabel", background="#222831", foreground="#c8d0dc", font=("Segoe UI", 9))
        style.configure("Menu.TButton", anchor="w", padding=(14, 11), font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("Sub.TLabel", foreground="#5e6875", font=("Segoe UI", 10))
        style.configure("Accent.TButton", padding=(14, 9), font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", rowheight=30)

    def _build(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        side = ttk.Frame(root, style="Side.TFrame", padding=(16, 18))
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)
        side.configure(width=230)

        ttk.Label(side, text="Local Compute", style="SideTitle.TLabel").pack(anchor="w")
        ttk.Label(side, text="Simple multi-PC tools", style="SideText.TLabel").pack(anchor="w", pady=(2, 18))

        for key, label in [
            ("devices", "Device Registration"),
            ("shared", "Shared Folders"),
            ("process", "File Processing"),
            ("sound", "Sound Hub"),
            ("running", "Running Log"),
            ("errors", "Error Log"),
            ("mcp", "MCP Connection"),
        ]:
            ttk.Button(side, text=label, style="Menu.TButton", command=lambda k=key: self._show(k)).pack(fill="x", pady=4)

        ttk.Label(side, text="Use menus from top to bottom for the easiest setup.", style="SideText.TLabel", wraplength=190).pack(side="bottom", anchor="w")

        self.content = ttk.Frame(root, padding=24)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        self.pages["devices"] = self._devices_page()
        self.pages["shared"] = self._shared_page()
        self.pages["process"] = self._process_page()
        self.pages["sound"] = self._sound_page()
        self.pages["running"] = self._running_page()
        self.pages["errors"] = self._errors_page()
        self.pages["mcp"] = self._mcp_page()

        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def _page(self, title: str, text: str) -> ttk.Frame:
        page = ttk.Frame(self.content)
        page.columnconfigure(0, weight=1)
        ttk.Label(page, text=title, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(page, text=text, style="Sub.TLabel", wraplength=820).grid(row=1, column=0, sticky="w", pady=(5, 20))
        return page

    def _devices_page(self) -> ttk.Frame:
        page = self._page("Device Registration", "Register PCs that can help with file processing or future sound sharing.")
        page.rowconfigure(4, weight=1)

        top = ttk.Frame(page)
        top.grid(row=2, column=0, sticky="ew")
        for i in range(4):
            top.columnconfigure(i, weight=1)
        ttk.Button(top, text="Allow Device Connection", style="Accent.TButton", command=self._allow_device_connection).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(top, text="Add by Number", command=self._add_by_code).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(top, text="Find Same Wi-Fi PCs", command=self._open_discovery).grid(row=0, column=2, sticky="ew", padx=8)
        ttk.Button(top, text="Test Selected", command=self._test_selected).grid(row=0, column=3, sticky="ew", padx=(8, 0))

        middle = ttk.Frame(page)
        middle.grid(row=3, column=0, sticky="ew", pady=(12, 12))
        ttk.Button(middle, text="Manual Add", command=self._add_worker).pack(side="left")
        ttk.Button(middle, text="Delete Selected", command=self._delete_worker).pack(side="left", padx=(8, 0))
        ttk.Button(middle, text="Save", command=self._save_workers).pack(side="left", padx=(8, 0))

        body = ttk.Frame(page)
        body.grid(row=4, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(body, columns=("name", "host", "jobs", "status"), show="headings", selectmode="browse")
        for key, label, width in [("name", "Device Name", 160), ("host", "Address", 180), ("jobs", "Parallel Jobs", 100), ("status", "Status", 80)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._show_selected())

        form = ttk.LabelFrame(body, text="Selected Device", padding=10)
        form.grid(row=0, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)

        self.name_var = tk.StringVar()
        self.host_var = tk.StringVar()
        self.user_var = tk.StringVar()
        self.jobs_var = tk.StringVar(value="2")
        self.workdir_var = tk.StringVar(value="C:/work/your-repo")
        self.enabled_var = tk.BooleanVar(value=True)

        for row, (label, var) in enumerate([
            ("Device name", self.name_var),
            ("Address", self.host_var),
            ("Windows account", self.user_var),
            ("Parallel jobs", self.jobs_var),
            ("Work folder", self.workdir_var),
        ]):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=7)
            ttk.Entry(form, textvariable=var).grid(row=row, column=1, sticky="ew", padx=10, pady=7)
        ttk.Checkbutton(form, text="Enabled", variable=self.enabled_var).grid(row=5, column=1, sticky="w", padx=10, pady=7)
        ttk.Button(form, text="Apply to Selected", style="Accent.TButton", command=self._apply_form).grid(row=6, column=1, sticky="ew", padx=10, pady=10)
        return page

    def _shared_page(self) -> ttk.Frame:
        page = self._page("Shared Folders", "Make PC A the shared storage PC. Other PCs read input files and write results here.")
        card = ttk.LabelFrame(page, text="Shared folder on PC A", padding=10)
        card.grid(row=2, column=0, sticky="ew")
        card.columnconfigure(1, weight=1)
        ttk.Label(card, text="Recommended folder").grid(row=0, column=0, sticky="w", padx=12, pady=8)
        ttk.Label(card, text="C:\\LocalComputeShare").grid(row=0, column=1, sticky="w", padx=12, pady=8)
        ttk.Label(card, text="Subfolders").grid(row=1, column=0, sticky="w", padx=12, pady=8)
        ttk.Label(card, text="input / outputs / logs").grid(row=1, column=1, sticky="w", padx=12, pady=8)
        ttk.Button(card, text="Make This PC Shared Storage", style="Accent.TButton", command=self._run_share_setup).grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=12)

        paths = ttk.LabelFrame(page, text="Folders used by this app", padding=10)
        paths.grid(row=3, column=0, sticky="ew", pady=(20, 0))
        paths.columnconfigure(1, weight=1)
        self._path_row(paths, 0, "Input folder", self.folder_var)
        self._path_row(paths, 1, "Output folder", self.output_var)
        self._path_row(paths, 2, "Log folder", self.logs_var)
        return page

    def _process_page(self) -> ttk.Frame:
        page = self._page("File Processing", "Choose a folder and start processing. Advanced command settings are hidden unless needed.")
        form = ttk.LabelFrame(page, text="Processing setup", padding=10)
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        self._path_row(form, 0, "Input folder", self.folder_var)
        ttk.Label(form, text="Job type").grid(row=1, column=0, sticky="w", padx=10, pady=7)
        job_box = ttk.Combobox(form, textvariable=self.job_type_var, values=["Sample test", "Excel check", "Advanced command"], state="readonly")
        job_box.grid(row=1, column=1, sticky="ew", padx=10, pady=7)
        job_box.bind("<<ComboboxSelected>>", lambda _e: self._apply_job_type())
        self._path_row(form, 2, "Output folder", self.output_var)

        self.advanced_frame = ttk.Frame(form)
        self.advanced_frame.grid(row=3, column=0, columnspan=3, sticky="ew")
        self.advanced_frame.columnconfigure(1, weight=1)
        ttk.Label(self.advanced_frame, text="File pattern").grid(row=0, column=0, sticky="w", padx=10, pady=7)
        ttk.Entry(self.advanced_frame, textvariable=self.pattern_var).grid(row=0, column=1, sticky="ew", padx=10, pady=7)
        ttk.Label(self.advanced_frame, text="Command").grid(row=1, column=0, sticky="w", padx=10, pady=7)
        ttk.Entry(self.advanced_frame, textvariable=self.command_var).grid(row=1, column=1, sticky="ew", padx=10, pady=7)

        ttk.Checkbutton(form, text="Show advanced settings", variable=self.advanced_visible, command=self._toggle_advanced).grid(row=4, column=1, sticky="w", padx=10, pady=6)

        actions = ttk.Frame(page)
        actions.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        actions.columnconfigure(2, weight=1)
        ttk.Button(actions, text="Check Device Connections", command=self._test_all).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(actions, text="Start File Processing", style="Accent.TButton", command=self._run_jobs).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(actions, text="Retry Failed Files", command=self._retry_failed).grid(row=0, column=2, sticky="ew", padx=(8, 0))

        self._toggle_advanced()
        return page

    def _sound_page(self) -> ttk.Frame:
        page = self._page("Sound Hub", "First step for listening to all PCs through one speaker. This screen manages the mixer profile and checks audio tools.")
        page.rowconfigure(5, weight=1)

        mode = ttk.LabelFrame(page, text="Mode", padding=10)
        mode.grid(row=2, column=0, sticky="ew")
        mode.columnconfigure(1, weight=1)
        ttk.Radiobutton(mode, text="This PC receives audio and plays through one speaker", variable=self.sound_mode, value="This PC receives audio").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Radiobutton(mode, text="This PC sends its audio to another PC", variable=self.sound_mode, value="This PC sends audio").grid(row=1, column=0, sticky="w", padx=8, pady=4)

        master = ttk.LabelFrame(page, text="Soundbar", padding=10)
        master.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        master.columnconfigure(1, weight=1)
        ttk.Label(master, text="Master volume").grid(row=0, column=0, sticky="w", padx=8)
        ttk.Scale(master, from_=0, to=100, variable=self.master_volume, orient="horizontal", command=lambda _v: self._save_sound_config()).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(master, text="Test Speaker Beep", command=self._test_beep).grid(row=0, column=2, padx=8)
        ttk.Button(master, text="Open Windows Volume Mixer", command=self._open_volume_mixer).grid(row=0, column=3, padx=8)

        tools = ttk.Frame(page)
        tools.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        for col in range(4):
            tools.columnconfigure(col, weight=1)
        ttk.Button(tools, text="Check Audio Tools", command=self._check_audio_tools).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(tools, text="Open VBAN", command=lambda: webbrowser.open("https://vb-audio.com/Voicemeeter/vban.htm")).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(tools, text="Open Scream", command=lambda: webbrowser.open("https://github.com/duncanthrax/scream")).grid(row=0, column=2, sticky="ew", padx=6)
        ttk.Button(tools, text="Open SonoBus", command=lambda: webbrowser.open("https://www.sonobus.net/")).grid(row=0, column=3, sticky="ew", padx=(6, 0))

        mixer = ttk.LabelFrame(page, text="Per-PC mixer profile", padding=10)
        mixer.grid(row=5, column=0, sticky="nsew", pady=(14, 0))
        mixer.columnconfigure(1, weight=1)
        self.sound_mixer_frame = mixer
        self._refresh_sound_mixer()

        ttk.Label(page, textvariable=self.sound_status_var, style="Sub.TLabel", wraplength=820).grid(row=6, column=0, sticky="w", pady=(12, 0))
        return page

    def _running_page(self) -> ttk.Frame:
        page = self._page("Running Log", "Shows what the app is doing now.")
        page.rowconfigure(3, weight=1)
        ttk.Button(page, text="Clear Log", command=lambda: self.log.delete("1.0", "end")).grid(row=2, column=0, sticky="e")
        self.log = tk.Text(page, height=24, wrap="word", font=("Consolas", 10))
        self.log.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        return page

    def _errors_page(self) -> ttk.Frame:
        page = self._page("Error Log", "Shows failed files and reasons.")
        page.rowconfigure(3, weight=1)
        bar = ttk.Frame(page)
        bar.grid(row=2, column=0, sticky="ew")
        ttk.Button(bar, text="Refresh", style="Accent.TButton", command=self._refresh_errors).pack(side="left")
        ttk.Button(bar, text="Retry Failed Files", command=self._retry_failed).pack(side="left", padx=(8, 0))
        self.error_text = tk.Text(page, height=24, wrap="word", font=("Consolas", 10))
        self.error_text.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        return page

    def _mcp_page(self) -> ttk.Frame:
        page = self._page("MCP Connection", "Only needed for Codex, Cursor, Claude, or another AI tool. Normal users can ignore this page.")
        page.rowconfigure(2, weight=1)
        text = tk.Text(page, height=24, wrap="none", font=("Consolas", 10))
        text.grid(row=2, column=0, sticky="nsew")
        config = {
            "mcpServers": {
                "local-compute": {
                    "command": "python",
                    "args": ["-m", "local_compute_mcp.server", "--config", str(CONFIG_PATH)],
                    "env": {"PYTHONPATH": str(APP_DIR / "src")},
                }
            }
        }
        text.insert("end", json.dumps(config, ensure_ascii=False, indent=2))
        text.configure(state="disabled")
        return page

    def _path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=7)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=10, pady=7)
        ttk.Button(parent, text="Browse", command=lambda: self._browse(variable)).grid(row=row, column=2, sticky="ew", padx=10, pady=7)

    def _browse(self, variable: tk.StringVar) -> None:
        selected = filedialog.askdirectory(initialdir=variable.get() or str(APP_DIR))
        if selected:
            variable.set(selected)

    def _show(self, key: str) -> None:
        if key == "sound":
            self._refresh_sound_mixer()
        self.pages[key].tkraise()
        if key == "errors":
            self._refresh_errors()

    def _load_workers(self) -> None:
        self.workers = load_all_workers(CONFIG_PATH)
        self._refresh_tree()
        self._write("App is ready. Start with Device Registration.")

    def _refresh_tree(self) -> None:
        if not hasattr(self, "tree"):
            return
        self.tree.delete(*self.tree.get_children())
        for index, worker in enumerate(self.workers):
            host = "This PC" if worker.type == "local" else worker.host
            status = "Enabled" if worker.enabled else "Off"
            self.tree.insert("", "end", iid=str(index), values=(worker.name, host, worker.max_jobs, status))

    def _selected_index(self) -> int | None:
        selected = self.tree.selection()
        return int(selected[0]) if selected else None

    def _show_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        worker = self.workers[index]
        self.name_var.set(worker.name)
        self.host_var.set(worker.host)
        self.user_var.set(worker.user)
        self.jobs_var.set(str(worker.max_jobs))
        self.workdir_var.set(worker.workdir)
        self.enabled_var.set(worker.enabled)

    def _save_workers(self) -> None:
        save_workers(CONFIG_PATH, self.workers)
        self._write("Saved device list.")
        self._refresh_sound_mixer()

    def _append_worker(self, name: str, host: str) -> None:
        self.workers.append(
            Worker(
                name=name,
                type="ssh",
                enabled=True,
                host=host,
                user="your_user",
                port=22,
                max_jobs=2,
                workdir="C:/work/your-repo",
                ssh_options=["BatchMode=yes", "ConnectTimeout=8"],
            )
        )
        self._refresh_tree()
        self.tree.selection_set(str(len(self.workers) - 1))
        self._show_selected()
        self._refresh_sound_mixer()

    def _add_worker(self) -> None:
        self._append_worker(f"pc-{len(self.workers) + 1}", "192.168.0.22")

    def _delete_worker(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        if self.workers[index].type == "local":
            messagebox.showinfo("Cannot delete", "Keep this PC in the list.")
            return
        del self.workers[index]
        self._refresh_tree()
        self._save_workers()

    def _apply_form(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("Select device", "Select a device first.")
            return
        try:
            self.workers[index] = Worker(
                name=self.name_var.get().strip() or "worker",
                type="ssh" if self.workers[index].type != "local" else "local",
                enabled=self.enabled_var.get(),
                host=self.host_var.get().strip(),
                user=self.user_var.get().strip(),
                port=22,
                max_jobs=max(1, int(self.jobs_var.get())),
                workdir=self.workdir_var.get().strip() or ".",
                ssh_options=["BatchMode=yes", "ConnectTimeout=8"],
            )
        except ValueError:
            messagebox.showerror("Input error", "Parallel jobs must be a number.")
            return
        self._refresh_tree()
        self.tree.selection_set(str(index))
        self._save_workers()

    def _allow_device_connection(self) -> None:
        if not self.pairing_server:
            self.pairing_server = PairingServer()
        info = self.pairing_server.start()
        messagebox.showinfo(
            "Allow Device Connection",
            f"On the other PC, click 'Add by Number' and enter this code.\n\nCode: {info.code}\nThis PC address: {info.host}",
        )
        self._write(f"Pairing code active: {info.code}, address: {info.host}")

    def _add_by_code(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Add by Number")
        dialog.geometry("360x170")
        dialog.transient(self)
        dialog.grab_set()
        code_var = tk.StringVar()
        ttk.Label(dialog, text="Enter the 6-digit code from the other PC").pack(anchor="w", padx=16, pady=(16, 6))
        ttk.Entry(dialog, textvariable=code_var, font=("Segoe UI", 16)).pack(fill="x", padx=16)

        def add() -> None:
            code = code_var.get().strip()
            dialog.destroy()
            self._run_background("Find device by code", lambda: self._pair_by_code(code))

        ttk.Button(dialog, text="Find Device", style="Accent.TButton", command=add).pack(fill="x", padx=16, pady=16)

    def _pair_by_code(self, code: str) -> object:
        info = find_pairing_code(code)
        if not info:
            raise ValueError("Could not find a PC with that code. Check same Wi-Fi and firewall.")
        self.queue.put(("add_worker", (info.name, info.host)))
        return {"name": info.name, "host": info.host}

    def _open_discovery(self) -> None:
        self._run_background("Find same Wi-Fi PCs", discover_same_wifi)

    def _test_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("Select device", "Select a device to test.")
            return
        self._run_background("Test selected device", lambda: [test_worker(self.workers[index])])

    def _test_all(self) -> None:
        self._run_background("Check all device connections", lambda: [test_worker(worker) for worker in self._enabled_workers()])

    def _enabled_workers(self) -> list[Worker]:
        self._save_workers()
        return load_workers(CONFIG_PATH)

    def _apply_job_type(self) -> None:
        job_type = self.job_type_var.get()
        if job_type == "Sample test":
            self.pattern_var.set("*.txt")
            self.command_var.set("python samples\\sample_worker.py {input_q} {output_dir_q}")
        elif job_type == "Excel check":
            self.pattern_var.set("*.xlsx")
            self.command_var.set("python check_excel.py {input_q} {output_dir_q}")

    def _toggle_advanced(self) -> None:
        if self.advanced_visible.get():
            self.advanced_frame.grid()
        else:
            self.advanced_frame.grid_remove()

    def _run_jobs(self) -> None:
        self._apply_job_type()

        def task() -> object:
            workers = self._enabled_workers()
            jobs = discover_jobs(self.folder_var.get(), self.pattern_var.get())
            if not jobs:
                raise ValueError("No files found in the selected folder.")
            return run_jobs(workers, jobs, self.command_var.get(), self.output_var.get(), self.logs_var.get())

        self._run_background("File processing", task)

    def _retry_failed(self) -> None:
        self._run_background("Retry failed files", lambda: retry_failed(self._enabled_workers(), self.command_var.get(), self.output_var.get(), self.logs_var.get()))

    def _run_share_setup(self) -> None:
        script = APP_DIR / "setup_shared_disk_on_A_admin.bat"
        if not script.exists():
            messagebox.showerror("File not found", f"Shared folder setup file is missing.\n{script}")
            return
        subprocess.Popen([str(script)], cwd=str(APP_DIR), shell=True)
        self._write("Opened shared folder setup. Accept the Windows permission prompt if it appears.")

    def _refresh_errors(self) -> None:
        self.error_text.delete("1.0", "end")
        path = Path(self.logs_var.get()) / "joblog.tsv"
        if not path.exists():
            self.error_text.insert("end", "No error log yet.")
            return
        with path.open("r", encoding="utf-8", newline="") as handle:
            failed = [row for row in csv.DictReader(handle, delimiter="\t") if row.get("status") != "success"]
        if not failed:
            self.error_text.insert("end", "No failed files.")
            return
        for row in failed:
            self.error_text.insert("end", f"File: {row.get('input')}\nDevice: {row.get('worker')}\nExit code: {row.get('exit_code')}\n")
            if row.get("stderr"):
                self.error_text.insert("end", row["stderr"] + "\n")
            self.error_text.insert("end", "\n")

    def _load_sound_config(self) -> None:
        if not SOUND_CONFIG_PATH.exists():
            return
        try:
            data = json.loads(SOUND_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        self.master_volume.set(int(data.get("master_volume", self.master_volume.get())))
        self.sound_mode.set(str(data.get("mode", self.sound_mode.get())))

    def _save_sound_config(self) -> None:
        data = {
            "master_volume": self.master_volume.get(),
            "mode": self.sound_mode.get(),
            "devices": {},
        }
        for name, controls in self.sound_rows.items():
            volume = controls.get("volume")
            muted = controls.get("muted")
            if isinstance(volume, tk.IntVar) and isinstance(muted, tk.BooleanVar):
                data["devices"][name] = {"volume": volume.get(), "muted": muted.get()}
        SOUND_CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _refresh_sound_mixer(self) -> None:
        if not hasattr(self, "sound_mixer_frame"):
            return
        for child in self.sound_mixer_frame.winfo_children():
            child.destroy()
        self.sound_rows = {}
        saved: dict[str, object] = {}
        if SOUND_CONFIG_PATH.exists():
            try:
                saved = json.loads(SOUND_CONFIG_PATH.read_text(encoding="utf-8")).get("devices", {})
            except Exception:
                saved = {}
        if not self.workers:
            ttk.Label(self.sound_mixer_frame, text="No devices registered yet. Add PCs in Device Registration first.").grid(row=0, column=0, sticky="w")
            return

        ttk.Label(self.sound_mixer_frame, text="Device").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Label(self.sound_mixer_frame, text="Volume").grid(row=0, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(self.sound_mixer_frame, text="Mute").grid(row=0, column=2, sticky="w", padx=8, pady=4)
        ttk.Label(self.sound_mixer_frame, text="Activity").grid(row=0, column=3, sticky="w", padx=8, pady=4)

        for row, worker in enumerate(self.workers, start=1):
            device_data = saved.get(worker.name, {}) if isinstance(saved, dict) else {}
            volume = tk.IntVar(value=int(device_data.get("volume", 80)) if isinstance(device_data, dict) else 80)
            muted = tk.BooleanVar(value=bool(device_data.get("muted", False)) if isinstance(device_data, dict) else False)
            ttk.Label(self.sound_mixer_frame, text=worker.name).grid(row=row, column=0, sticky="w", padx=8, pady=6)
            ttk.Scale(self.sound_mixer_frame, from_=0, to=100, variable=volume, orient="horizontal", command=lambda _v: self._save_sound_config()).grid(row=row, column=1, sticky="ew", padx=8, pady=6)
            ttk.Checkbutton(self.sound_mixer_frame, variable=muted, command=self._save_sound_config).grid(row=row, column=2, sticky="w", padx=8, pady=6)
            activity = ttk.Progressbar(self.sound_mixer_frame, maximum=100, value=0)
            activity.grid(row=row, column=3, sticky="ew", padx=8, pady=6)
            self.sound_rows[worker.name] = {"volume": volume, "muted": muted, "activity": activity}
        self.sound_mixer_frame.columnconfigure(1, weight=1)
        self.sound_mixer_frame.columnconfigure(3, weight=1)

    def _test_beep(self) -> None:
        volume = self.master_volume.get()
        self.sound_status_var.set(f"Speaker test beep sent. Master volume profile: {volume}%.")
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
        self._save_sound_config()

    def _open_volume_mixer(self) -> None:
        subprocess.Popen(["sndvol.exe"])
        self.sound_status_var.set("Opened Windows Volume Mixer.")

    def _check_audio_tools(self) -> None:
        checks = {
            "Voicemeeter/VBAN": ["voicemeeter.exe", "voicemeeter8.exe", "voicemeeterpro.exe"],
            "Scream Receiver": ["scream.exe"],
            "SonoBus": ["SonoBus.exe", "sonobus.exe"],
        }
        lines: list[str] = []
        for label, executables in checks.items():
            found = any(self._where(exe) for exe in executables)
            lines.append(f"{label}: {'found' if found else 'not found'}")
        lines.append("Note: this app currently saves mixer settings and opens helper tools. Real network audio requires VBAN, Scream, or SonoBus setup.")
        self.sound_status_var.set(" | ".join(lines))
        self._write("\n".join(lines))

    @staticmethod
    def _where(executable: str) -> bool:
        completed = subprocess.run(["where", executable], capture_output=True, text=True, shell=True)
        return completed.returncode == 0

    def _run_background(self, title: str, fn) -> None:
        self._show("running")
        self._write(f"{title} started")

        def wrapped() -> None:
            try:
                self.queue.put(("result", (title, fn())))
            except Exception as exc:
                self.queue.put(("error", (title, exc)))

        threading.Thread(target=wrapped, daemon=True).start()

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "add_worker":
                    name, host = payload
                    self._append_worker(name, host)
                    self._save_workers()
                    self._write(f"Added device: {name} ({host})")
                    continue

                title, value = payload
                if kind == "error":
                    self._write(f"{title} failed: {value}")
                    messagebox.showerror(title, str(value))
                else:
                    if title == "Find same Wi-Fi PCs" and isinstance(value, list):
                        self._show_discovery_results(value)
                    self._write(f"{title} complete")
                    self._write(str(value))
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _show_discovery_results(self, devices: list[NetworkDevice]) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Found PCs")
        dialog.geometry("560x380")
        dialog.transient(self)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=("ip", "name"), show="headings", selectmode="browse")
        tree.heading("ip", text="Address")
        tree.heading("name", text="Name")
        tree.grid(row=0, column=0, sticky="nsew")
        for index, device in enumerate(devices):
            tree.insert("", "end", iid=str(index), values=(device.ip, device.name))

        def add() -> None:
            selected = tree.selection()
            if not selected:
                return
            device = devices[int(selected[0])]
            self._append_worker(device.name or f"pc-{len(self.workers) + 1}", device.ip)
            self._save_workers()
            dialog.destroy()

        ttk.Button(frame, text="Add Selected PC", style="Accent.TButton", command=add).grid(row=1, column=0, sticky="ew", pady=(12, 0))

    def _write(self, text: str) -> None:
        if hasattr(self, "log"):
            self.log.insert("end", text + "\n")
            self.log.see("end")


def main() -> int:
    app = LocalComputeApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
