from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import Worker, load_all_workers, load_workers, save_workers
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
        self.geometry("980x680")
        self.minsize(900, 620)
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

        ttk.Label(root, text="컴퓨터 등록", font=("Segoe UI", 13, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(root, text="작업 실행", font=("Segoe UI", 13, "bold")).grid(row=0, column=1, sticky="w", padx=(16, 0))

        left = ttk.Frame(root)
        left.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        columns = ("name", "type", "host", "jobs", "status")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        for key, label, width in [
            ("name", "이름", 130),
            ("type", "방식", 70),
            ("host", "Host/IP", 150),
            ("jobs", "동시", 60),
            ("status", "상태", 90),
        ]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_selected())

        worker_buttons = ttk.Frame(left)
        worker_buttons.grid(row=1, column=0, sticky="ew", pady=(8, 12))
        for index in range(4):
            worker_buttons.columnconfigure(index, weight=1)
        ttk.Button(worker_buttons, text="추가", command=self._add_worker).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(worker_buttons, text="삭제", command=self._delete_worker).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(worker_buttons, text="저장", command=self._save_workers).grid(row=0, column=2, sticky="ew", padx=4)
        ttk.Button(worker_buttons, text="연결 테스트", command=self._test_selected).grid(row=0, column=3, sticky="ew", padx=(4, 0))

        form = ttk.LabelFrame(left, text="선택한 컴퓨터")
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
            ("이름", ttk.Entry(form, textvariable=self.name_var)),
            ("방식", ttk.Combobox(form, textvariable=self.type_var, values=["ssh", "local"], state="readonly")),
            ("Host/IP", ttk.Entry(form, textvariable=self.host_var)),
            ("User", ttk.Entry(form, textvariable=self.user_var)),
            ("Port", ttk.Entry(form, textvariable=self.port_var)),
            ("동시 작업", ttk.Entry(form, textvariable=self.jobs_var)),
            ("작업 폴더", ttk.Entry(form, textvariable=self.workdir_var)),
        ]
        for row, (label, widget) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=5)
            widget.grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        ttk.Checkbutton(form, text="사용", variable=self.enabled_var).grid(row=len(rows), column=1, sticky="w", padx=8, pady=6)
        ttk.Button(form, text="선택 항목에 반영", command=self._apply_form).grid(row=len(rows) + 1, column=1, sticky="e", padx=8, pady=(4, 10))

        right = ttk.Frame(root)
        right.grid(row=1, column=1, sticky="nsew", padx=(16, 0), pady=(8, 0))
        right.columnconfigure(1, weight=1)
        right.rowconfigure(8, weight=1)

        self.input_var = tk.StringVar(value=str(APP_DIR / "samples" / "input"))
        self.pattern_var = tk.StringVar(value="*.txt")
        self.command_var = tk.StringVar(value="python samples\\sample_worker.py {input_q} {output_dir_q}")
        self.output_var = tk.StringVar(value=str(APP_DIR / "outputs"))
        self.logs_var = tk.StringVar(value=str(APP_DIR / "logs"))

        self._path_row(right, 0, "Input 폴더", self.input_var)
        self._entry_row(right, 1, "파일 패턴", self.pattern_var)
        self._entry_row(right, 2, "실행 명령", self.command_var)
        self._path_row(right, 3, "Output 폴더", self.output_var)
        self._path_row(right, 4, "Logs 폴더", self.logs_var)

        help_text = "Host/IP는 같은 Wi-Fi의 192.168.x.x 또는 Tailscale/ZeroTier IP를 넣으면 됩니다. 먼저 연결 테스트를 누르세요."
        ttk.Label(right, text=help_text, wraplength=520, foreground="#555").grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 10))

        action_bar = ttk.Frame(right)
        action_bar.grid(row=6, column=0, columnspan=3, sticky="ew")
        action_bar.columnconfigure(0, weight=1)
        action_bar.columnconfigure(1, weight=1)
        action_bar.columnconfigure(2, weight=1)
        ttk.Button(action_bar, text="전체 연결 테스트", command=self._test_all).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(action_bar, text="작업 실행", style="Accent.TButton", command=self._run_jobs).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(action_bar, text="실패만 재시도", command=self._retry_failed).grid(row=0, column=2, sticky="ew", padx=(5, 0))

        ttk.Label(right, text="로그", font=("Segoe UI", 10, "bold")).grid(row=7, column=0, sticky="w", pady=(16, 4))
        self.log = tk.Text(right, height=16, wrap="word", font=("Consolas", 9))
        self.log.grid(row=8, column=0, columnspan=3, sticky="nsew")

    def _entry_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=5)

    def _path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=(8, 4), pady=5)
        ttk.Button(parent, text="찾기", command=lambda: self._browse_dir(variable)).grid(row=row, column=2, sticky="ew", pady=5)

    def _browse_dir(self, variable: tk.StringVar) -> None:
        selected = filedialog.askdirectory(initialdir=variable.get() or str(APP_DIR))
        if selected:
            variable.set(selected)

    def _load_workers(self) -> None:
        self.workers = load_all_workers(CONFIG_PATH)
        self._refresh_tree()
        self._write("준비됨. 먼저 '전체 연결 테스트' 또는 샘플 '작업 실행'을 눌러보세요.")

    def _save_workers(self) -> None:
        save_workers(CONFIG_PATH, self.workers)
        self._write(f"저장 완료: {CONFIG_PATH}")

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, worker in enumerate(self.workers):
            host = "this PC" if worker.type == "local" else worker.host
            status = "사용" if worker.enabled else "꺼짐"
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
        number = len(self.workers) + 1
        self.workers.append(
            Worker(
                name=f"pc-{number}",
                type="ssh",
                enabled=True,
                host="192.168.0.22",
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

    def _delete_worker(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        if self.workers[index].type == "local":
            messagebox.showinfo("삭제 불가", "local 컴퓨터는 남겨두는 편이 안전합니다.")
            return
        del self.workers[index]
        self._refresh_tree()

    def _apply_form(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("선택 필요", "먼저 왼쪽에서 컴퓨터를 선택하세요.")
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
            messagebox.showerror("입력 오류", "Port와 동시 작업은 숫자로 입력하세요.")
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
            messagebox.showinfo("선택 필요", "테스트할 컴퓨터를 선택하세요.")
            return
        self._run_background("선택 연결 테스트", lambda: [test_worker(self.workers[index])])

    def _test_all(self) -> None:
        self._run_background("전체 연결 테스트", lambda: [test_worker(worker) for worker in self._enabled_workers()])

    def _run_jobs(self) -> None:
        def task() -> object:
            workers = self._enabled_workers()
            jobs = discover_jobs(self.input_var.get(), self.pattern_var.get())
            if not jobs:
                raise ValueError("Input 폴더에서 파일을 찾지 못했습니다.")
            return run_jobs(workers, jobs, self.command_var.get(), self.output_var.get(), self.logs_var.get())

        self._run_background("작업 실행", task)

    def _retry_failed(self) -> None:
        def task() -> object:
            return retry_failed(self._enabled_workers(), self.command_var.get(), self.output_var.get(), self.logs_var.get())

        self._run_background("실패 재시도", task)

    def _run_background(self, title: str, fn) -> None:
        self._write(f"{title} 시작...")

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
                title, value = payload
                if kind == "error":
                    self._write(f"{title} 실패: {value}")
                    messagebox.showerror(title, str(value))
                else:
                    self._write(f"{title} 완료")
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
