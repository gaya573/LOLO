from __future__ import annotations

import csv
import queue
import subprocess
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
        self.geometry("1120x740")
        self.minsize(980, 660)

        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.workers: list[Worker] = []
        self.pages: dict[str, ttk.Frame] = {}
        self.menu_buttons: dict[str, ttk.Button] = {}

        self.input_var = tk.StringVar(value=str(APP_DIR / "samples" / "input"))
        self.pattern_var = tk.StringVar(value="*.txt")
        self.command_var = tk.StringVar(value="python samples\\sample_worker.py {input_q} {output_dir_q}")
        self.output_var = tk.StringVar(value=str(APP_DIR / "outputs"))
        self.logs_var = tk.StringVar(value=str(APP_DIR / "logs"))

        self._set_style()
        self._build_shell()
        self._load_workers()
        self._show_page("devices")
        self._poll_queue()

    def _set_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Sidebar.TFrame", background="#20242b")
        style.configure("SidebarTitle.TLabel", background="#20242b", foreground="#ffffff", font=("Segoe UI", 15, "bold"))
        style.configure("SidebarNote.TLabel", background="#20242b", foreground="#b8c0cc", font=("Segoe UI", 9))
        style.configure("Menu.TButton", anchor="w", padding=(14, 10), font=("Segoe UI", 10))
        style.configure("Accent.TButton", padding=(12, 8), font=("Segoe UI", 10, "bold"))
        style.configure("PageTitle.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Hint.TLabel", foreground="#5b6470")
        style.configure("Treeview", rowheight=28)

    def _build_shell(self) -> None:
        shell = ttk.Frame(self)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(shell, style="Sidebar.TFrame", padding=(14, 16))
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)
        sidebar.configure(width=230)

        ttk.Label(sidebar, text="Local Compute", style="SidebarTitle.TLabel").pack(anchor="w")
        ttk.Label(sidebar, text="PC 여러 대로 작업 나누기", style="SidebarNote.TLabel").pack(anchor="w", pady=(2, 18))

        for key, label in [
            ("devices", "1. 기기 등록"),
            ("shared", "2. 공유폴더 관리"),
            ("jobs", "3. 작업 실행"),
            ("running", "4. 실행중 로그"),
            ("errors", "5. 에러 로그"),
            ("mcp", "6. MCP 연결방법"),
        ]:
            button = ttk.Button(sidebar, text=label, style="Menu.TButton", command=lambda page=key: self._show_page(page))
            button.pack(fill="x", pady=4)
            self.menu_buttons[key] = button

        ttk.Label(sidebar, text="초보자 흐름: 기기 등록 -> 공유폴더 -> 작업 실행", style="SidebarNote.TLabel", wraplength=190).pack(side="bottom", anchor="w")

        self.content = ttk.Frame(shell, padding=22)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        self.pages["devices"] = self._build_devices_page()
        self.pages["shared"] = self._build_shared_page()
        self.pages["jobs"] = self._build_jobs_page()
        self.pages["running"] = self._build_running_page()
        self.pages["errors"] = self._build_errors_page()
        self.pages["mcp"] = self._build_mcp_page()

        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def _page(self, title: str, hint: str) -> ttk.Frame:
        page = ttk.Frame(self.content)
        page.columnconfigure(0, weight=1)
        ttk.Label(page, text=title, style="PageTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(page, text=hint, style="Hint.TLabel", wraplength=760).grid(row=1, column=0, sticky="w", pady=(4, 18))
        return page

    def _build_devices_page(self) -> ttk.Frame:
        page = self._page("기기 등록", "같은 Wi-Fi에 있는 PC를 찾고, 작업에 사용할 컴퓨터를 등록합니다.")
        page.rowconfigure(3, weight=1)

        actions = ttk.Frame(page)
        actions.grid(row=2, column=0, sticky="ew")
        for index in range(5):
            actions.columnconfigure(index, weight=1)
        ttk.Button(actions, text="Wi-Fi PC 찾기", style="Accent.TButton", command=self._open_discovery).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(actions, text="직접 추가", command=self._add_worker).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(actions, text="선택 삭제", command=self._delete_worker).grid(row=0, column=2, sticky="ew", padx=6)
        ttk.Button(actions, text="저장", command=self._save_workers).grid(row=0, column=3, sticky="ew", padx=6)
        ttk.Button(actions, text="연결 테스트", command=self._test_selected).grid(row=0, column=4, sticky="ew", padx=(6, 0))

        body = ttk.Frame(page)
        body.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        columns = ("name", "type", "host", "jobs", "status")
        self.tree = ttk.Treeview(body, columns=columns, show="headings", selectmode="browse")
        for key, label, width in [
            ("name", "이름", 150),
            ("type", "방식", 70),
            ("host", "Host/IP", 180),
            ("jobs", "동시작업", 80),
            ("status", "상태", 80),
        ]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_selected())

        form = ttk.LabelFrame(body, text="선택한 기기")
        form.grid(row=0, column=1, sticky="nsew")
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
            ("기기 이름", ttk.Entry(form, textvariable=self.name_var)),
            ("연결 방식", ttk.Combobox(form, textvariable=self.type_var, values=["ssh", "local"], state="readonly")),
            ("Host/IP", ttk.Entry(form, textvariable=self.host_var)),
            ("윈도우 계정", ttk.Entry(form, textvariable=self.user_var)),
            ("Port", ttk.Entry(form, textvariable=self.port_var)),
            ("동시 작업 수", ttk.Entry(form, textvariable=self.jobs_var)),
            ("작업 폴더", ttk.Entry(form, textvariable=self.workdir_var)),
        ]
        for row, (label, widget) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=6)
            widget.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        ttk.Checkbutton(form, text="사용", variable=self.enabled_var).grid(row=len(rows), column=1, sticky="w", padx=10, pady=8)
        ttk.Button(form, text="선택 기기에 적용", style="Accent.TButton", command=self._apply_form).grid(row=len(rows) + 1, column=1, sticky="ew", padx=10, pady=(6, 10))
        return page

    def _build_shared_page(self) -> ttk.Frame:
        page = self._page("공유폴더 관리", "A컴퓨터를 기준 저장소로 만들고, 모든 PC가 같은 input/output/logs 폴더를 보게 합니다.")
        card = ttk.LabelFrame(page, text="A컴퓨터 공유폴더")
        card.grid(row=2, column=0, sticky="ew")
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text="추천 위치").grid(row=0, column=0, sticky="w", padx=12, pady=8)
        ttk.Label(card, text="C:\\LocalComputeShare").grid(row=0, column=1, sticky="w", padx=12, pady=8)
        ttk.Label(card, text="네트워크 주소").grid(row=1, column=0, sticky="w", padx=12, pady=8)
        ttk.Label(card, text="\\\\A컴퓨터이름\\LocalComputeShare").grid(row=1, column=1, sticky="w", padx=12, pady=8)
        ttk.Button(card, text="A컴퓨터 공유폴더 만들기", style="Accent.TButton", command=self._run_share_setup).grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 12))

        paths = ttk.LabelFrame(page, text="앱에서 사용할 폴더")
        paths.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        paths.columnconfigure(1, weight=1)
        self._path_row(paths, 0, "Input 폴더", self.input_var)
        self._path_row(paths, 1, "Output 폴더", self.output_var)
        self._path_row(paths, 2, "Logs 폴더", self.logs_var)

        hint = (
            "공유폴더를 만들면 input에 파일을 넣고, outputs에서 결과를 확인합니다. "
            "B/C 컴퓨터에서도 같은 네트워크 주소가 열려야 합니다."
        )
        ttk.Label(page, text=hint, style="Hint.TLabel", wraplength=780).grid(row=4, column=0, sticky="w", pady=(16, 0))
        return page

    def _build_jobs_page(self) -> ttk.Frame:
        page = self._page("작업 실행", "파일 패턴과 실행 명령을 정한 뒤 여러 PC에 나눠 실행합니다.")
        page.columnconfigure(0, weight=1)

        form = ttk.LabelFrame(page, text="작업 설정")
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)
        self._path_row(form, 0, "Input 폴더", self.input_var)
        self._entry_row(form, 1, "파일 패턴", self.pattern_var)
        self._entry_row(form, 2, "실행 명령", self.command_var)
        self._path_row(form, 3, "Output 폴더", self.output_var)
        self._path_row(form, 4, "Logs 폴더", self.logs_var)

        actions = ttk.Frame(page)
        actions.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        actions.columnconfigure(2, weight=1)
        ttk.Button(actions, text="전체 연결 테스트", command=self._test_all).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(actions, text="작업 실행", style="Accent.TButton", command=self._run_jobs).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(actions, text="실패만 재시도", command=self._retry_failed).grid(row=0, column=2, sticky="ew", padx=(8, 0))

        examples = (
            "명령 예시: python check_excel.py {input_q} {output_dir_q}\n"
            "Python, PowerShell, BAT/CMD, EXE, Node 등 윈도우 명령줄에서 되는 작업이면 실행할 수 있습니다."
        )
        ttk.Label(page, text=examples, style="Hint.TLabel", wraplength=780).grid(row=4, column=0, sticky="w", pady=(18, 0))
        return page

    def _build_running_page(self) -> ttk.Frame:
        page = self._page("실행중 로그", "연결 테스트, 작업 실행, 재시도 진행 상황을 한 곳에서 봅니다.")
        page.rowconfigure(2, weight=1)
        actions = ttk.Frame(page)
        actions.grid(row=2, column=0, sticky="nsew")
        actions.columnconfigure(0, weight=1)
        actions.rowconfigure(1, weight=1)
        ttk.Button(actions, text="로그 지우기", command=lambda: self.log.delete("1.0", "end")).grid(row=0, column=0, sticky="e", pady=(0, 8))
        self.log = tk.Text(actions, height=24, wrap="word", font=("Consolas", 10))
        self.log.grid(row=1, column=0, sticky="nsew")
        return page

    def _build_errors_page(self) -> ttk.Frame:
        page = self._page("에러 로그", "실패한 작업만 따로 확인합니다.")
        page.rowconfigure(3, weight=1)
        bar = ttk.Frame(page)
        bar.grid(row=2, column=0, sticky="ew")
        ttk.Button(bar, text="에러 새로고침", style="Accent.TButton", command=self._refresh_errors).pack(side="left")
        ttk.Button(bar, text="실패만 재시도", command=self._retry_failed).pack(side="left", padx=(8, 0))
        self.error_text = tk.Text(page, height=22, wrap="word", font=("Consolas", 10))
        self.error_text.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        return page

    def _build_mcp_page(self) -> ttk.Frame:
        page = self._page("MCP 연결방법", "Codex, Cursor, Claude 같은 MCP 클라이언트에서 이 앱의 엔진을 연결할 때 사용합니다.")
        page.rowconfigure(2, weight=1)
        config = {
            "mcpServers": {
                "local-compute": {
                    "command": "python",
                    "args": ["-m", "local_compute_mcp.server", "--config", str(CONFIG_PATH)],
                    "env": {"PYTHONPATH": str(APP_DIR / "src")},
                }
            }
        }
        text = tk.Text(page, height=24, wrap="none", font=("Consolas", 10))
        text.grid(row=2, column=0, sticky="nsew")
        text.insert("end", str(config).replace("'", '"'))
        text.configure(state="disabled")
        return page

    def _entry_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=7)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=10, pady=7)

    def _path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=7)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=10, pady=7)
        ttk.Button(parent, text="찾기", command=lambda: self._browse_dir(variable)).grid(row=row, column=2, sticky="ew", padx=10, pady=7)

    def _show_page(self, key: str) -> None:
        self.pages[key].tkraise()
        if key == "errors":
            self._refresh_errors()

    def _browse_dir(self, variable: tk.StringVar) -> None:
        selected = filedialog.askdirectory(initialdir=variable.get() or str(APP_DIR))
        if selected:
            variable.set(selected)

    def _load_workers(self) -> None:
        self.workers = load_all_workers(CONFIG_PATH)
        self._refresh_tree()
        self._write("앱 준비 완료. 왼쪽 메뉴에서 필요한 기능을 선택하세요.")

    def _save_workers(self) -> None:
        save_workers(CONFIG_PATH, self.workers)
        self._write(f"기기 설정 저장 완료: {CONFIG_PATH}")

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
        dialog.title("Wi-Fi PC 찾기")
        dialog.geometry("620x420")
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        ttk.Label(frame, text="같은 Wi-Fi/LAN에 있는 PC 후보를 찾습니다. 찾은 뒤 선택해서 추가하세요.", wraplength=560).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        device_tree = ttk.Treeview(frame, columns=("ip", "name", "source"), show="headings", selectmode="browse")
        for key, label, width in [("ip", "IP"), ("name", "이름"), ("source", "출처")]:
            device_tree.heading(key, text=label)
            device_tree.column(key, width=width, anchor="w")
        device_tree.grid(row=1, column=0, sticky="nsew")

        status = tk.StringVar(value="검색을 누르세요.")
        ttk.Label(frame, textvariable=status).grid(row=2, column=0, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        for index in range(3):
            buttons.columnconfigure(index, weight=1)
        devices: list[NetworkDevice] = []

        def scan() -> None:
            scan_btn.configure(state="disabled")
            status.set("검색 중... 10-30초 정도 걸릴 수 있습니다.")
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
                messagebox.showinfo("선택 필요", "추가할 PC를 먼저 선택하세요.")
                return
            device = devices[int(selected[0])]
            name = device.name.split(".")[0] if device.name else f"pc-{len(self.workers) + 1}"
            self._append_worker(name, device.ip)
            self._save_workers()
            dialog.destroy()

        scan_btn = ttk.Button(buttons, text="검색", style="Accent.TButton", command=scan)
        scan_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(buttons, text="선택한 PC 추가", command=add_selected).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(buttons, text="닫기", command=dialog.destroy).grid(row=0, column=2, sticky="ew", padx=(5, 0))

    def _delete_worker(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        if self.workers[index].type == "local":
            messagebox.showinfo("삭제 불가", "내 PC는 남겨두는 편이 안전합니다.")
            return
        del self.workers[index]
        self._refresh_tree()

    def _apply_form(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("선택 필요", "왼쪽 목록에서 기기를 먼저 선택하세요.")
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
            messagebox.showerror("입력 오류", "Port와 동시 작업 수는 숫자로 입력하세요.")
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
            messagebox.showinfo("선택 필요", "테스트할 기기를 선택하세요.")
            return
        self._run_background("연결 테스트", lambda: [test_worker(self.workers[index])])

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

    def _run_share_setup(self) -> None:
        script = APP_DIR / "setup_shared_disk_on_A_admin.bat"
        if not script.exists():
            messagebox.showerror("파일 없음", f"공유폴더 생성 파일을 찾지 못했습니다:\n{script}")
            return
        subprocess.Popen([str(script)], cwd=str(APP_DIR), shell=True)
        self._write("공유폴더 생성 창을 열었습니다. 관리자 권한 확인 창이 뜨면 허용하세요.")

    def _refresh_errors(self) -> None:
        self.error_text.configure(state="normal")
        self.error_text.delete("1.0", "end")
        path = Path(self.logs_var.get()) / "joblog.tsv"
        if not path.exists():
            self.error_text.insert("end", "아직 에러 로그가 없습니다.")
            return
        with path.open("r", encoding="utf-8", newline="") as handle:
            rows = [row for row in csv.DictReader(handle, delimiter="\t") if row.get("status") != "success"]
        if not rows:
            self.error_text.insert("end", "실패한 작업이 없습니다.")
            return
        for row in rows:
            self.error_text.insert("end", f"[{row.get('worker')}] {row.get('input')} exit={row.get('exit_code')}\n")
            if row.get("stderr"):
                self.error_text.insert("end", row["stderr"] + "\n")
            self.error_text.insert("end", "\n")

    def _run_background(self, title: str, fn) -> None:
        self._show_page("running")
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
                if kind == "discover":
                    device_tree, status, scan_btn, devices, found = payload
                    devices.clear()
                    devices.extend(found)
                    device_tree.delete(*device_tree.get_children())
                    for index, device in enumerate(devices):
                        device_tree.insert("", "end", iid=str(index), values=(device.ip, device.name, device.source))
                    status.set(f"{len(devices)}개 기기를 찾았습니다. 선택 후 추가하세요.")
                    scan_btn.configure(state="normal")
                    continue
                if kind == "discover_error":
                    status, scan_btn, exc = payload
                    status.set(f"검색 실패: {exc}")
                    scan_btn.configure(state="normal")
                    continue

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
