from __future__ import annotations

import csv
import json
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

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


class LocalComputeApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Local Compute")
        self.geometry("1120x740")
        self.minsize(980, 660)

        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.workers: list[Worker] = []
        self.pages: dict[str, ttk.Frame] = {}
        self.pairing_server: PairingServer | None = None

        self.folder_var = tk.StringVar(value=str(APP_DIR / "samples" / "input"))
        self.output_var = tk.StringVar(value=str(APP_DIR / "outputs"))
        self.logs_var = tk.StringVar(value=str(APP_DIR / "logs"))
        self.job_type_var = tk.StringVar(value="샘플 테스트")
        self.command_var = tk.StringVar(value="python samples\\sample_worker.py {input_q} {output_dir_q}")
        self.advanced_visible = tk.BooleanVar(value=False)

        self._style()
        self._build()
        self._load_workers()
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
        style.configure("Card.TLabelframe", padding=10)
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
        ttk.Label(side, text="여러 PC로 파일 처리", style="SideText.TLabel").pack(anchor="w", pady=(2, 18))

        for key, label in [
            ("devices", "기기 등록"),
            ("shared", "공유폴더 관리"),
            ("process", "파일 처리"),
            ("running", "실행중인 로그"),
            ("errors", "에러 로그"),
            ("mcp", "MCP 연결방법"),
        ]:
            ttk.Button(side, text=label, style="Menu.TButton", command=lambda k=key: self._show(k)).pack(fill="x", pady=4)

        ttk.Label(side, text="처음이면 위에서부터 순서대로 누르면 됩니다.", style="SideText.TLabel", wraplength=190).pack(side="bottom", anchor="w")

        self.content = ttk.Frame(root, padding=24)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        self.pages["devices"] = self._devices_page()
        self.pages["shared"] = self._shared_page()
        self.pages["process"] = self._process_page()
        self.pages["running"] = self._running_page()
        self.pages["errors"] = self._errors_page()
        self.pages["mcp"] = self._mcp_page()

        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def _page(self, title: str, text: str) -> ttk.Frame:
        page = ttk.Frame(self.content)
        page.columnconfigure(0, weight=1)
        ttk.Label(page, text=title, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(page, text=text, style="Sub.TLabel", wraplength=780).grid(row=1, column=0, sticky="w", pady=(5, 20))
        return page

    def _devices_page(self) -> ttk.Frame:
        page = self._page("기기 등록", "작업을 나눠서 도와줄 PC를 등록합니다. 가장 쉬운 방법은 다른 PC에서 '기기 연결 허용'을 누르고, 이 PC에서 번호를 입력하는 방식입니다.")
        page.rowconfigure(4, weight=1)

        top = ttk.Frame(page)
        top.grid(row=2, column=0, sticky="ew")
        for i in range(4):
            top.columnconfigure(i, weight=1)
        ttk.Button(top, text="기기 연결 허용", style="Accent.TButton", command=self._allow_device_connection).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(top, text="번호로 기기 추가", command=self._add_by_code).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(top, text="같은 Wi-Fi에서 찾기", command=self._open_discovery).grid(row=0, column=2, sticky="ew", padx=8)
        ttk.Button(top, text="연결 테스트", command=self._test_selected).grid(row=0, column=3, sticky="ew", padx=(8, 0))

        middle = ttk.Frame(page)
        middle.grid(row=3, column=0, sticky="ew", pady=(12, 12))
        ttk.Button(middle, text="직접 추가", command=self._add_worker).pack(side="left")
        ttk.Button(middle, text="선택 삭제", command=self._delete_worker).pack(side="left", padx=(8, 0))
        ttk.Button(middle, text="저장", command=self._save_workers).pack(side="left", padx=(8, 0))

        body = ttk.Frame(page)
        body.grid(row=4, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(body, columns=("name", "host", "jobs", "status"), show="headings", selectmode="browse")
        for key, label, width in [("name", "기기 이름", 160), ("host", "주소", 180), ("jobs", "동시 처리", 90), ("status", "상태", 80)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._show_selected())

        form = ttk.LabelFrame(body, text="선택한 기기")
        form.grid(row=0, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)

        self.name_var = tk.StringVar()
        self.host_var = tk.StringVar()
        self.user_var = tk.StringVar()
        self.jobs_var = tk.StringVar(value="2")
        self.workdir_var = tk.StringVar(value="C:/work/your-repo")
        self.enabled_var = tk.BooleanVar(value=True)

        for row, (label, var) in enumerate([
            ("기기 이름", self.name_var),
            ("주소", self.host_var),
            ("윈도우 계정", self.user_var),
            ("동시 처리 수", self.jobs_var),
            ("작업 폴더", self.workdir_var),
        ]):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=7)
            ttk.Entry(form, textvariable=var).grid(row=row, column=1, sticky="ew", padx=10, pady=7)
        ttk.Checkbutton(form, text="사용", variable=self.enabled_var).grid(row=5, column=1, sticky="w", padx=10, pady=7)
        ttk.Button(form, text="선택 기기에 적용", style="Accent.TButton", command=self._apply_form).grid(row=6, column=1, sticky="ew", padx=10, pady=10)
        return page

    def _shared_page(self) -> ttk.Frame:
        page = self._page("공유폴더 관리", "A컴퓨터를 기준 저장소로 정합니다. 다른 PC는 이 폴더에서 파일을 읽고 결과도 여기에 저장합니다.")
        card = ttk.LabelFrame(page, text="A컴퓨터에 만들 공유폴더")
        card.grid(row=2, column=0, sticky="ew")
        card.columnconfigure(1, weight=1)
        ttk.Label(card, text="추천 폴더").grid(row=0, column=0, sticky="w", padx=12, pady=8)
        ttk.Label(card, text="C:\\LocalComputeShare").grid(row=0, column=1, sticky="w", padx=12, pady=8)
        ttk.Label(card, text="안에 생기는 폴더").grid(row=1, column=0, sticky="w", padx=12, pady=8)
        ttk.Label(card, text="input / outputs / logs").grid(row=1, column=1, sticky="w", padx=12, pady=8)
        ttk.Button(card, text="이 PC를 공유폴더 PC로 설정", style="Accent.TButton", command=self._run_share_setup).grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=12)

        paths = ttk.LabelFrame(page, text="현재 앱에서 사용할 폴더")
        paths.grid(row=3, column=0, sticky="ew", pady=(20, 0))
        paths.columnconfigure(1, weight=1)
        self._path_row(paths, 0, "처리할 파일 폴더", self.folder_var)
        self._path_row(paths, 1, "결과 저장 폴더", self.output_var)
        self._path_row(paths, 2, "로그 저장 폴더", self.logs_var)
        return page

    def _process_page(self) -> ttk.Frame:
        page = self._page("파일 처리", "처리할 파일이 들어있는 폴더를 고르고 시작합니다. 복잡한 명령어는 고급 설정에서만 보이게 했습니다.")
        form = ttk.LabelFrame(page, text="처리할 내용")
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        self._path_row(form, 0, "파일이 있는 폴더", self.folder_var)
        ttk.Label(form, text="작업 종류").grid(row=1, column=0, sticky="w", padx=10, pady=7)
        job_box = ttk.Combobox(form, textvariable=self.job_type_var, values=["샘플 테스트", "엑셀 검사", "고급 명령"], state="readonly")
        job_box.grid(row=1, column=1, sticky="ew", padx=10, pady=7)
        job_box.bind("<<ComboboxSelected>>", lambda _e: self._apply_job_type())
        self._path_row(form, 2, "결과 저장 폴더", self.output_var)

        self.advanced_frame = ttk.Frame(form)
        self.advanced_frame.grid(row=3, column=0, columnspan=3, sticky="ew")
        self.advanced_frame.columnconfigure(1, weight=1)
        ttk.Label(self.advanced_frame, text="파일 형식").grid(row=0, column=0, sticky="w", padx=10, pady=7)
        self.pattern_var = tk.StringVar(value="*.txt")
        ttk.Entry(self.advanced_frame, textvariable=self.pattern_var).grid(row=0, column=1, sticky="ew", padx=10, pady=7)
        ttk.Label(self.advanced_frame, text="실행 명령").grid(row=1, column=0, sticky="w", padx=10, pady=7)
        ttk.Entry(self.advanced_frame, textvariable=self.command_var).grid(row=1, column=1, sticky="ew", padx=10, pady=7)

        ttk.Checkbutton(form, text="고급 설정 보기", variable=self.advanced_visible, command=self._toggle_advanced).grid(row=4, column=1, sticky="w", padx=10, pady=6)

        actions = ttk.Frame(page)
        actions.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        actions.columnconfigure(2, weight=1)
        ttk.Button(actions, text="기기 연결 확인", command=self._test_all).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(actions, text="파일 처리 시작", style="Accent.TButton", command=self._run_jobs).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(actions, text="실패한 파일만 다시 처리", command=self._retry_failed).grid(row=0, column=2, sticky="ew", padx=(8, 0))

        self._toggle_advanced()
        return page

    def _running_page(self) -> ttk.Frame:
        page = self._page("실행중인 로그", "지금 앱이 무엇을 하고 있는지 보여줍니다.")
        page.rowconfigure(3, weight=1)
        ttk.Button(page, text="로그 지우기", command=lambda: self.log.delete("1.0", "end")).grid(row=2, column=0, sticky="e")
        self.log = tk.Text(page, height=24, wrap="word", font=("Consolas", 10))
        self.log.grid(row=3, column=0, sticky="nsew", pady=(8, 0))
        return page

    def _errors_page(self) -> ttk.Frame:
        page = self._page("에러 로그", "실패한 파일과 이유만 따로 보여줍니다.")
        page.rowconfigure(3, weight=1)
        bar = ttk.Frame(page)
        bar.grid(row=2, column=0, sticky="ew")
        ttk.Button(bar, text="새로고침", style="Accent.TButton", command=self._refresh_errors).pack(side="left")
        ttk.Button(bar, text="실패한 파일만 다시 처리", command=self._retry_failed).pack(side="left", padx=(8, 0))
        self.error_text = tk.Text(page, height=24, wrap="word", font=("Consolas", 10))
        self.error_text.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        return page

    def _mcp_page(self) -> ttk.Frame:
        page = self._page("MCP 연결방법", "Codex/Cursor 같은 도구와 연결할 때만 봅니다. 일반 사용자는 몰라도 됩니다.")
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
        ttk.Button(parent, text="찾기", command=lambda: self._browse(variable)).grid(row=row, column=2, sticky="ew", padx=10, pady=7)

    def _browse(self, variable: tk.StringVar) -> None:
        selected = filedialog.askdirectory(initialdir=variable.get() or str(APP_DIR))
        if selected:
            variable.set(selected)

    def _show(self, key: str) -> None:
        self.pages[key].tkraise()
        if key == "errors":
            self._refresh_errors()

    def _load_workers(self) -> None:
        self.workers = load_all_workers(CONFIG_PATH)
        self._refresh_tree()
        self._write("앱이 준비되었습니다. 왼쪽 메뉴를 위에서부터 차례대로 사용하세요.")

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, worker in enumerate(self.workers):
            host = "내 PC" if worker.type == "local" else worker.host
            status = "사용" if worker.enabled else "꺼짐"
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
        self._write("기기 목록을 저장했습니다.")

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

    def _add_worker(self) -> None:
        self._append_worker(f"pc-{len(self.workers) + 1}", "192.168.0.22")

    def _delete_worker(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        if self.workers[index].type == "local":
            messagebox.showinfo("삭제 불가", "내 PC는 삭제하지 않는 편이 안전합니다.")
            return
        del self.workers[index]
        self._refresh_tree()
        self._save_workers()

    def _apply_form(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("선택 필요", "먼저 기기를 선택하세요.")
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
            messagebox.showerror("입력 오류", "동시 처리 수는 숫자로 입력하세요.")
            return
        self._refresh_tree()
        self.tree.selection_set(str(index))
        self._save_workers()

    def _allow_device_connection(self) -> None:
        if not self.pairing_server:
            self.pairing_server = PairingServer()
        info = self.pairing_server.start()
        messagebox.showinfo(
            "기기 연결 허용",
            f"다른 PC에서 아래 번호를 입력하세요.\n\n번호: {info.code}\n이 PC 주소: {info.host}\n\n같은 Wi-Fi에서만 사용하세요.",
        )
        self._write(f"기기 연결 허용 중입니다. 번호: {info.code}, 주소: {info.host}")

    def _add_by_code(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("번호로 기기 추가")
        dialog.geometry("360x170")
        dialog.transient(self)
        dialog.grab_set()
        code_var = tk.StringVar()
        ttk.Label(dialog, text="다른 PC에 표시된 6자리 번호").pack(anchor="w", padx=16, pady=(16, 6))
        ttk.Entry(dialog, textvariable=code_var, font=("Segoe UI", 16)).pack(fill="x", padx=16)

        def add() -> None:
            code = code_var.get().strip()
            dialog.destroy()
            self._run_background("번호로 기기 찾기", lambda: self._pair_by_code(code))

        ttk.Button(dialog, text="기기 찾기", style="Accent.TButton", command=add).pack(fill="x", padx=16, pady=16)

    def _pair_by_code(self, code: str) -> object:
        info = find_pairing_code(code)
        if not info:
            raise ValueError("해당 번호의 PC를 찾지 못했습니다. 두 PC가 같은 Wi-Fi인지 확인하세요.")
        self.queue.put(("add_worker", (info.name, info.host)))
        return {"name": info.name, "host": info.host}

    def _open_discovery(self) -> None:
        self._run_background("같은 Wi-Fi PC 검색", discover_same_wifi)

    def _test_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("선택 필요", "테스트할 기기를 선택하세요.")
            return
        self._run_background("기기 연결 테스트", lambda: [test_worker(self.workers[index])])

    def _test_all(self) -> None:
        self._run_background("기기 전체 연결 확인", lambda: [test_worker(worker) for worker in self._enabled_workers()])

    def _enabled_workers(self) -> list[Worker]:
        self._save_workers()
        return load_workers(CONFIG_PATH)

    def _apply_job_type(self) -> None:
        job_type = self.job_type_var.get()
        if job_type == "샘플 테스트":
            self.pattern_var.set("*.txt")
            self.command_var.set("python samples\\sample_worker.py {input_q} {output_dir_q}")
        elif job_type == "엑셀 검사":
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
                raise ValueError("선택한 폴더에서 처리할 파일을 찾지 못했습니다.")
            return run_jobs(workers, jobs, self.command_var.get(), self.output_var.get(), self.logs_var.get())

        self._run_background("파일 처리", task)

    def _retry_failed(self) -> None:
        self._run_background("실패한 파일 다시 처리", lambda: retry_failed(self._enabled_workers(), self.command_var.get(), self.output_var.get(), self.logs_var.get()))

    def _run_share_setup(self) -> None:
        script = APP_DIR / "setup_shared_disk_on_A_admin.bat"
        if not script.exists():
            messagebox.showerror("파일 없음", f"공유폴더 생성 파일이 없습니다.\n{script}")
            return
        subprocess.Popen([str(script)], cwd=str(APP_DIR), shell=True)
        self._write("공유폴더 설정 창을 열었습니다. Windows 권한 확인이 뜨면 허용하세요.")

    def _refresh_errors(self) -> None:
        self.error_text.delete("1.0", "end")
        path = Path(self.logs_var.get()) / "joblog.tsv"
        if not path.exists():
            self.error_text.insert("end", "아직 에러 로그가 없습니다.")
            return
        with path.open("r", encoding="utf-8", newline="") as handle:
            failed = [row for row in csv.DictReader(handle, delimiter="\t") if row.get("status") != "success"]
        if not failed:
            self.error_text.insert("end", "실패한 파일이 없습니다.")
            return
        for row in failed:
            self.error_text.insert("end", f"파일: {row.get('input')}\n기기: {row.get('worker')}\n종료 코드: {row.get('exit_code')}\n")
            if row.get("stderr"):
                self.error_text.insert("end", row["stderr"] + "\n")
            self.error_text.insert("end", "\n")

    def _run_background(self, title: str, fn) -> None:
        self._show("running")
        self._write(f"{title} 시작")

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
                    self._write(f"기기를 추가했습니다: {name} ({host})")
                    continue

                title, value = payload
                if kind == "error":
                    self._write(f"{title} 실패: {value}")
                    messagebox.showerror(title, str(value))
                else:
                    if title == "같은 Wi-Fi PC 검색" and isinstance(value, list):
                        self._show_discovery_results(value)
                    self._write(f"{title} 완료")
                    self._write(str(value))
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _show_discovery_results(self, devices: list[NetworkDevice]) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("찾은 PC")
        dialog.geometry("560x380")
        dialog.transient(self)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=("ip", "name"), show="headings", selectmode="browse")
        tree.heading("ip", text="주소")
        tree.heading("name", text="이름")
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

        ttk.Button(frame, text="선택한 PC 추가", style="Accent.TButton", command=add).grid(row=1, column=0, sticky="ew", pady=(12, 0))

    def _write(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")


def main() -> int:
    app = LocalComputeApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
