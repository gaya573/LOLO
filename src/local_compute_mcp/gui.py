from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import Worker, load_all_workers, load_workers, save_workers
from .discovery import NetworkDevice, discover_same_wifi
from .runner import discover_jobs, retry_failed, run_jobs, test_worker


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


APP_DIR = app_dir()
CONFIG_PATH = APP_DIR / "workers.yaml"


class LocalComputeApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Local Compute MCP")
        self.geometry("1040x720")
        self.minsize(940, 640)
        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.workers: list[Worker] = []

        self._set_style()
        self._build()
        self._load_workers()
        self._poll_queue()

    def _set_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", padding=(10, 6))
        style.configure("Accent.TButton", padding=(12, 7), font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", rowheight=28)

    def _build(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=2)
        root.columnconfigure(1, weight=3)
        root.rowconfigure(1, weight=1)

        ttk.Label(root, text="Computers", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="Run Jobs", font=("Segoe UI", 13, "bold")).grid(row=0, column=1, sticky="w", padx=(16, 0))

        left = ttk.Frame(root)
        left.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        columns = ("name", "type", "host", "jobs", "status")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        for key, label, width in [
            ("name", "Name", 130),
            ("type", "Type", 70),
            ("host", "Host/IP", 160),
            ("jobs", "Jobs", 60),
            ("status", "Status", 90),
        ]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_selected())

        worker_buttons = ttk.Frame(left)
        worker_buttons.grid(row=1, column=0, sticky="ew", pady=(8, 12))
        for index in range(5):
            worker_buttons.columnconfigure(index, weight=1)
        ttk.Button(worker_buttons, text="Add", command=self._add_worker).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(worker_buttons, text="Find Wi-Fi PCs", command=self._open_discovery).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(worker_buttons, text="Delete", command=self._delete_worker).grid(row=0, column=2, sticky="ew", padx=4)
        ttk.Button(worker_buttons, text="Save", command=self._save_workers).grid(row=0, column=3, sticky="ew", padx=4)
        ttk.Button(worker_buttons, text="Test SSH", command=self._test_selected).grid(row=0, column=4, sticky="ew", padx=(4, 0))

        form = ttk.LabelFrame(left, text="Selected Computer")
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        self.name_var = tk.StringVar()
        self.type_var = tk.StringVar(value="ssh")
        self.host_var = tk.StringVar()
        self.user_var = tk.StringVar()
        self.port_var = tk.StringVar(value="22")
        self.jobs_var = tk.StringVar(value="2")
        self.workdir_var = tk.StringVar(value="C:/work/your-repo")
        self.enabled_var = tk.BooleanVar(value=True)

        rows = [
            ("Name", ttk.Entry(form, textvariable=self.name_var)),
            ("Type", ttk.Combobox(form, textvariable=self.type_var, values=["ssh", "local"], state="readonly")),
            ("Host/IP", ttk.Entry(form, textvariable=self.host_var)),
            ("User", ttk.Entry(form, textvariable=self.user_var)),
            ("Port", ttk.Entry(form, textvariable=self.port_var)),
            ("Parallel jobs", ttk.Entry(form, textvariable=self.jobs_var)),
            ("Work folder", ttk.Entry(form, textvariable=self.workdir_var)),
        ]
        for row, (label, widget) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=5)
            widget.grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        ttk.Checkbutton(form, text="Enabled", variable=self.enabled_var).grid(row=len(rows), column=1, sticky="w", padx=8, pady=6)
        ttk.Button(form, text="Apply to Selected", command=self._apply_form).grid(row=len(rows) + 1, column=1, sticky="e", padx=8, pady=(4, 10))

        right = ttk.Frame(root)
        right.grid(row=1, column=1, sticky="nsew", padx=(16, 0), pady=(8, 0))
        right.columnconfigure(1, weight=1)
        right.rowconfigure(9, weight=1)

        self.input_var = tk.StringVar(value=str(APP_DIR / "samples" / "input"))
        self.pattern_var = tk.StringVar(value="*.txt")
        self.command_var = tk.StringVar(value="python samples\\sample_worker.py {input_q} {output_dir_q}")
        self.output_var = tk.StringVar(value=str(APP_DIR / "outputs"))
        self.logs_var = tk.StringVar(value=str(APP_DIR / "logs"))

        self._path_row(right, 0, "Input folder", self.input_var)
        self._entry_row(right, 1, "File pattern", self.pattern_var)
        self._entry_row(right, 2, "Command", self.command_var)
        self._path_row(right, 3, "Output folder", self.output_var)
        self._path_row(right, 4, "Logs folder", self.logs_var)

        help_text = (
            "Beginner flow: 1) Find Wi-Fi PCs  2) enter Windows user  3) Test SSH  "
            "4) use a shared disk path like \\\\A-PC\\LocalComputeShare\\input  5) Run Jobs."
        )
        ttk.Label(right, text=help_text, wraplength=570, foreground="#555").grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 6))
        command_help = (
            "Command can run Python, PowerShell, .bat, .cmd, .exe, Node, or any installed CLI. "
            "Remote PCs must have the same program installed."
        )
        ttk.Label(right, text=command_help, wraplength=570, foreground="#555").grid(row=6, column=0, columnspan=3, sticky="ew", pady=(0, 10))

        action_bar = ttk.Frame(right)
        action_bar.grid(row=7, column=0, columnspan=3, sticky="ew")
        action_bar.columnconfigure(0, weight=1)
        action_bar.columnconfigure(1, weight=1)
        action_bar.columnconfigure(2, weight=1)
        ttk.Button(action_bar, text="Test All", command=self._test_all).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(action_bar, text="Run Jobs", style="Accent.TButton", command=self._run_jobs).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(action_bar, text="Retry Failed", command=self._retry_failed).grid(row=0, column=2, sticky="ew", padx=(5, 0))

        ttk.Label(right, text="Log", font=("Segoe UI", 10, "bold")).grid(row=8, column=0, sticky="w", pady=(16, 4))
        self.log = tk.Text(right, height=16, wrap="word", font=("Consolas", 9))
        self.log.grid(row=9, column=0, columnspan=3, sticky="nsew")

    def _entry_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=5)

    def _path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=(8, 4), pady=5)
        ttk.Button(parent, text="Browse", command=lambda: self._browse_dir(variable)).grid(row=row, column=2, sticky="ew", pady=5)

    def _browse_dir(self, variable: tk.StringVar) -> None:
        selected = filedialog.askdirectory(initialdir=variable.get() or str(APP_DIR))
        if selected:
            variable.set(selected)

    def _load_workers(self) -> None:
        self.workers = load_all_workers(CONFIG_PATH)
        self._refresh_tree()
        self._write("Ready. Click 'Find Wi-Fi PCs' or run the sample job.")

    def _save_workers(self) -> None:
        save_workers(CONFIG_PATH, self.workers)
        self._write(f"Saved: {CONFIG_PATH}")

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, worker in enumerate(self.workers):
            host = "this PC" if worker.type == "local" else worker.host
            status = "enabled" if worker.enabled else "off"
            self.tree.insert("", "end", iid=str(index), values=(worker.name, worker.type, host, worker.max_jobs, status))

    def _selected_index(self) -> int | None:
        selected = self.tree.selection()
        return int(selected[0]) if selected else None

    def _show_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        worker = self.workers[index]
        self.name_var.set(worker.name)
        self.type_var.set(worker.type)
        self.host_var.set(worker.host)
        self.user_var.set(worker.user)
        self.port_var.set(str(worker.port))
        self.jobs_var.set(str(worker.max_jobs))
        self.workdir_var.set(worker.workdir)
        self.enabled_var.set(worker.enabled)

    def _add_worker(self) -> None:
        self._append_worker(f"pc-{len(self.workers) + 1}", "192.168.0.22")

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

    def _open_discovery(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Find PCs on Same Wi-Fi")
        dialog.geometry("620x420")
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        info = "Scans the current Wi-Fi/LAN. Tailscale/ZeroTier devices may not appear; add their IP manually."
        ttk.Label(frame, text=info, wraplength=560).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        columns = ("ip", "name", "source")
        device_tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        for key, label, width in [("ip", "IP"), ("name", "Name"), ("source", "Source")]:
            device_tree.heading(key, text=label)
            device_tree.column(key, width=width, anchor="w")
        device_tree.grid(row=1, column=0, sticky="nsew")

        status = tk.StringVar(value="Press Scan.")
        ttk.Label(frame, textvariable=status).grid(row=2, column=0, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        for index in range(3):
            buttons.columnconfigure(index, weight=1)

        devices: list[NetworkDevice] = []

        def scan() -> None:
            scan_btn.configure(state="disabled")
            status.set("Scanning... this can take 10-30 seconds.")
            device_tree.delete(*device_tree.get_children())

            def work() -> None:
                try:
                    found = discover_same_wifi()
                    self.queue.put(("discover", (device_tree, status, scan_btn, devices, found)))
                except Exception as exc:
                    self.queue.put(("discover_error", (status, scan_btn, exc)))

            threading.Thread(target=work, daemon=True).start()

        def add_selected() -> None:
            selected = device_tree.selection()
            if not selected:
                messagebox.showinfo("Select device", "Select a device first.")
                return
            device = devices[int(selected[0])]
            name = device.name.split(".")[0] if device.name else f"pc-{len(self.workers) + 1}"
            self._append_worker(name, device.ip)
            self._save_workers()
            dialog.destroy()

        scan_btn = ttk.Button(buttons, text="Scan", command=scan)
        scan_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(buttons, text="Add Selected", style="Accent.TButton", command=add_selected).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(buttons, text="Close", command=dialog.destroy).grid(row=0, column=2, sticky="ew", padx=(5, 0))

    def _delete_worker(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        if self.workers[index].type == "local":
            messagebox.showinfo("Cannot delete", "Keep the local computer enabled.")
            return
        del self.workers[index]
        self._refresh_tree()

    def _apply_form(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("Select first", "Select a computer on the left first.")
            return
        try:
            worker = Worker(
                name=self.name_var.get().strip() or "worker",
                type=self.type_var.get(),
                enabled=self.enabled_var.get(),
                max_jobs=max(1, int(self.jobs_var.get())),
                workdir=self.workdir_var.get().strip() or ".",
                host=self.host_var.get().strip(),
                user=self.user_var.get().strip(),
                port=int(self.port_var.get()),
                ssh_options=["BatchMode=yes", "ConnectTimeout=8"],
            )
        except ValueError:
            messagebox.showerror("Input error", "Port and parallel jobs must be numbers.")
            return
        self.workers[index] = worker
        self._refresh_tree()
        self.tree.selection_set(str(index))
        self._save_workers()

    def _enabled_workers(self) -> list[Worker]:
        self._save_workers()
        return load_workers(CONFIG_PATH)

    def _test_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("Select first", "Select a computer to test.")
            return
        self._run_background("Test SSH", lambda: [test_worker(self.workers[index])])

    def _test_all(self) -> None:
        self._run_background("Test All", lambda: [test_worker(worker) for worker in self._enabled_workers()])

    def _run_jobs(self) -> None:
        def task() -> object:
            workers = self._enabled_workers()
            jobs = discover_jobs(self.input_var.get(), self.pattern_var.get())
            if not jobs:
                raise ValueError("No files found in the input folder.")
            return run_jobs(workers, jobs, self.command_var.get(), self.output_var.get(), self.logs_var.get())

        self._run_background("Run Jobs", task)

    def _retry_failed(self) -> None:
        def task() -> object:
            return retry_failed(self._enabled_workers(), self.command_var.get(), self.output_var.get(), self.logs_var.get())

        self._run_background("Retry Failed", task)

    def _run_background(self, title: str, fn) -> None:
        self._write(f"{title} started...")

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
                if kind == "discover":
                    device_tree, status, scan_btn, devices, found = payload
                    devices.clear()
                    devices.extend(found)
                    device_tree.delete(*device_tree.get_children())
                    for index, device in enumerate(devices):
                        device_tree.insert("", "end", iid=str(index), values=(device.ip, device.name, device.source))
                    status.set(f"Found {len(devices)} device(s). Select one and click Add Selected.")
                    scan_btn.configure(state="normal")
                    continue
                if kind == "discover_error":
                    status, scan_btn, exc = payload
                    status.set(f"Scan failed: {exc}")
                    scan_btn.configure(state="normal")
                    continue

                title, value = payload
                if kind == "error":
                    self._write(f"{title} failed: {value}")
                    messagebox.showerror(title, str(value))
                else:
                    self._write(f"{title} complete")
                    self._write(str(value))
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _write(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")


def main() -> int:
    app = LocalComputeApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
