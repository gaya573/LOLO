from __future__ import annotations

import csv
import json
import queue
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk

from .config import Worker, load_all_workers, load_workers, save_workers
from .discovery import NetworkDevice, discover_same_wifi
from .mcp_registry import McpEntry, inspect_local_mcp, inspect_workers_mcp
from .pairing import PairingServer, find_pairing_code
from .remote_assist import RemoteAssistServer, save_screenshot
from .runner import discover_jobs, retry_failed, run_jobs, test_worker
from .sound_hub import (
    SoundHubConfig,
    check_audio_tools,
    load_sound_config,
    open_windows_volume_mixer,
    save_sound_config,
    test_speaker_beep,
)


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


APP_DIR = app_dir()
CONFIG_PATH = APP_DIR / "workers.yaml"
SOUND_CONFIG_PATH = APP_DIR / "sound_hub.json"

BG = "#f6f5f2"
SURFACE = "#ffffff"
INK = "#202124"
MUTED = "#6b7280"
LINE = "#e5e7eb"
BRAND = "#ff6f0f"
BRAND_DARK = "#e85f00"
GREEN = "#1f9d55"
BLUE = "#2563eb"
RED = "#dc2626"


class LocalComputeApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Local Compute")
        self.geometry("1180x780")
        self.minsize(1040, 700)
        self.configure(bg=BG)

        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.workers: list[Worker] = []
        self.pages: dict[str, tk.Frame] = {}
        self.nav_buttons: dict[str, tk.Button] = {}
        self.pairing_server: PairingServer | None = None
        self.remote_assist_server: RemoteAssistServer | None = None

        self.folder_var = tk.StringVar(value=str(APP_DIR / "samples" / "input"))
        self.output_var = tk.StringVar(value=str(APP_DIR / "outputs"))
        self.logs_var = tk.StringVar(value=str(APP_DIR / "logs"))
        self.pattern_var = tk.StringVar(value="*.txt")
        self.command_var = tk.StringVar(value="python samples\\sample_worker.py {input_q} {output_dir_q}")
        self.job_type_var = tk.StringVar(value="Sample test")
        self.advanced_visible = tk.BooleanVar(value=False)

        self.master_volume = tk.IntVar(value=80)
        self.sound_mode = tk.StringVar(value="This PC receives audio")
        self.sound_status_var = tk.StringVar(value="아직 실제 오디오 송수신은 연결 전입니다. 먼저 오디오 도구를 확인하세요.")
        self.sound_rows: dict[str, dict[str, object]] = {}
        self.assist_status_var = tk.StringVar(value="AI 원격지원은 사용자가 허용한 동안만 스크린샷을 제공합니다.")
        self.assist_url_var = tk.StringVar(value="")

        self._style()
        self._build()
        self._load_workers()
        self._load_sound_config()
        self._show("home")
        self._poll_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", rowheight=34, background=SURFACE, fieldbackground=SURFACE, bordercolor=LINE)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#f3f4f6")
        style.configure("Horizontal.TScale", background=SURFACE)
        style.configure("TCombobox", padding=8)

    def _build(self) -> None:
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        nav = tk.Frame(shell, bg="#191f2b", width=238)
        nav.grid(row=0, column=0, sticky="ns")
        nav.grid_propagate(False)

        tk.Label(nav, text="🥕 Local", bg="#191f2b", fg="white", font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=22, pady=(24, 2))
        tk.Label(nav, text="여러 PC를 쉽게 연결", bg="#191f2b", fg="#cbd5e1", font=("Segoe UI", 10)).pack(anchor="w", padx=24, pady=(0, 22))

        for key, icon, label in [
            ("home", "🏠", "홈"),
            ("devices", "🔗", "기기등록"),
            ("shared", "📁", "공유폴더"),
            ("process", "⚡", "파일처리"),
            ("sound", "🔊", "사운드바"),
            ("running", "📋", "실행로그"),
            ("errors", "⚠️", "에러로그"),
            ("mcp", "🔌", "MCP"),
        ]:
            button = tk.Button(
                nav,
                text=f"{icon}  {label}",
                anchor="w",
                font=("Segoe UI", 12, "bold"),
                bg="#191f2b",
                fg="#e5e7eb",
                activebackground="#273244",
                activeforeground="white",
                relief="flat",
                bd=0,
                padx=22,
                pady=13,
                command=lambda name=key: self._show(name),
            )
            button.pack(fill="x", padx=10, pady=3)
            self.nav_buttons[key] = button

        button = tk.Button(
            nav,
            text="AI  AI 원격지원",
            anchor="w",
            font=("Segoe UI", 12, "bold"),
            bg="#191f2b",
            fg="#e5e7eb",
            activebackground="#273244",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=22,
            pady=13,
            command=lambda: self._show("assist"),
        )
        button.pack(fill="x", padx=10, pady=3)
        self.nav_buttons["assist"] = button

        tk.Label(
            nav,
            text="처음이면 홈에서 시작하세요.\n한 화면에 한 기능만 담았습니다.",
            bg="#191f2b",
            fg="#94a3b8",
            font=("Segoe UI", 9),
            justify="left",
        ).pack(side="bottom", anchor="w", padx=22, pady=20)

        self.content = tk.Frame(shell, bg=BG)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        self.pages = {
            "home": self._home_page(),
            "devices": self._devices_page(),
            "shared": self._shared_page(),
            "process": self._process_page(),
            "sound": self._sound_page(),
            "assist": self._assist_page(),
            "running": self._running_page(),
            "errors": self._errors_page(),
            "mcp": self._mcp_page(),
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def _page(self, title: str, subtitle: str, icon: str) -> tk.Frame:
        page = tk.Frame(self.content, bg=BG, padx=28, pady=24)
        page.columnconfigure(0, weight=1)
        header = tk.Frame(page, bg=BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        tk.Label(header, text=icon, bg=BG, fg=INK, font=("Segoe UI Emoji", 28)).pack(side="left", padx=(0, 12))
        text = tk.Frame(header, bg=BG)
        text.pack(side="left", fill="x", expand=True)
        tk.Label(text, text=title, bg=BG, fg=INK, font=("Segoe UI", 24, "bold")).pack(anchor="w")
        tk.Label(text, text=subtitle, bg=BG, fg=MUTED, font=("Segoe UI", 11)).pack(anchor="w", pady=(3, 0))
        return page

    def _card(self, parent: tk.Misc, row: int, title: str = "", column: int = 0, colspan: int = 1, pady: int = 8) -> tk.Frame:
        card = tk.Frame(parent, bg=SURFACE, highlightthickness=1, highlightbackground=LINE, padx=18, pady=16)
        card.grid(row=row, column=column, columnspan=colspan, sticky="nsew", pady=pady, padx=0)
        return card

    def _button(self, parent: tk.Misc, text: str, command, primary: bool = False, danger: bool = False) -> tk.Button:
        bg = BRAND if primary else RED if danger else "#eef2f7"
        fg = "white" if primary or danger else INK
        active = BRAND_DARK if primary else "#e2e8f0"
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active,
            activeforeground=fg,
            relief="flat",
            bd=0,
            padx=16,
            pady=11,
            font=("Segoe UI", 11, "bold"),
            cursor="hand2",
        )

    def _entry(self, parent: tk.Misc, variable: tk.StringVar) -> tk.Entry:
        return tk.Entry(parent, textvariable=variable, font=("Segoe UI", 11), relief="solid", bd=1)

    def _home_page(self) -> tk.Frame:
        page = self._page("오늘 할 일", "처음 쓰는 분도 순서대로 누르면 됩니다.", "🏠")
        page.columnconfigure(0, weight=1)
        page.columnconfigure(1, weight=1)

        steps = [
            ("🔗", "1. 기기 연결", "같은 Wi-Fi PC를 찾거나 6자리 번호로 연결합니다.", "devices"),
            ("📁", "2. 공유폴더 만들기", "A컴퓨터에 input / outputs / logs 폴더를 준비합니다.", "shared"),
            ("⚡", "3. 파일 처리", "처리할 파일을 넣고 연결된 PC들이 나눠 처리합니다.", "process"),
            ("🔊", "4. 사운드바", "여러 PC 소리를 한 스피커로 모으는 준비 화면입니다.", "sound"),
        ]
        for index, (icon, title, body, target) in enumerate(steps):
            card = self._card(page, row=1 + index // 2, column=index % 2, pady=10)
            card.grid_configure(padx=(0, 10) if index % 2 == 0 else (10, 0))
            tk.Label(card, text=icon, bg=SURFACE, font=("Segoe UI Emoji", 26)).pack(anchor="w")
            tk.Label(card, text=title, bg=SURFACE, fg=INK, font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(8, 2))
            tk.Label(card, text=body, bg=SURFACE, fg=MUTED, font=("Segoe UI", 10), wraplength=360, justify="left").pack(anchor="w")
            self._button(card, "열기", lambda key=target: self._show(key), primary=index == 0).pack(anchor="w", pady=(14, 0))
        return page

    def _devices_page(self) -> tk.Frame:
        page = self._page("기기등록", "도와줄 PC를 등록합니다. 가장 쉬운 방법은 번호 연결입니다.", "🔗")
        page.rowconfigure(3, weight=1)
        page.columnconfigure(0, weight=1)

        quick = self._card(page, 1, "빠른 연결")
        for i in range(4):
            quick.columnconfigure(i, weight=1)
        self._button(quick, "내 기기 연결 허용", self._allow_device_connection, primary=True).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._button(quick, "번호로 추가", self._add_by_code).grid(row=0, column=1, sticky="ew", padx=6)
        self._button(quick, "같은 Wi-Fi 찾기", self._open_discovery).grid(row=0, column=2, sticky="ew", padx=6)
        self._button(quick, "연결 테스트", self._test_selected).grid(row=0, column=3, sticky="ew", padx=(6, 0))

        manage = tk.Frame(page, bg=BG)
        manage.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self._button(manage, "직접 추가", self._add_worker).pack(side="left")
        self._button(manage, "저장", self._save_workers).pack(side="left", padx=8)
        self._button(manage, "선택 삭제", self._delete_worker, danger=True).pack(side="left")

        body = tk.Frame(page, bg=BG)
        body.grid(row=3, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        list_card = self._card(body, 0, "연결된 기기")
        list_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        list_card.rowconfigure(1, weight=1)
        list_card.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(list_card, columns=("name", "host", "jobs", "status"), show="headings", selectmode="browse")
        for key, label, width in [("name", "기기 이름", 160), ("host", "주소", 190), ("jobs", "동시 처리", 90), ("status", "상태", 80)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._show_selected())

        form = self._card(body, 0, "선택한 기기")
        form.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
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
            tk.Label(form, text=label, bg=SURFACE, fg=MUTED, font=("Segoe UI", 10, "bold")).grid(row=row, column=0, sticky="w", pady=7)
            self._entry(form, var).grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=7)
        tk.Checkbutton(form, text="사용", bg=SURFACE, variable=self.enabled_var, font=("Segoe UI", 10)).grid(row=5, column=1, sticky="w", pady=8)
        self._button(form, "수정 내용 반영", self._apply_form, primary=True).grid(row=6, column=1, sticky="ew", pady=(8, 0))
        return page

    def _shared_page(self) -> tk.Frame:
        page = self._page("공유폴더", "A컴퓨터를 공용 저장소로 만들고 파일 위치를 관리합니다.", "📁")
        page.columnconfigure(0, weight=1)
        card = self._card(page, 1, "A컴퓨터에 만들 폴더")
        tk.Label(card, text="C:\\LocalComputeShare", bg=SURFACE, fg=BRAND, font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(card, text="input / outputs / logs 폴더가 자동으로 준비됩니다.", bg=SURFACE, fg=MUTED, font=("Segoe UI", 11)).pack(anchor="w", pady=(6, 12))
        self._button(card, "이 PC를 공용 저장소로 만들기", self._run_share_setup, primary=True).pack(anchor="w")

        paths = self._card(page, 2, "앱에서 사용할 폴더")
        paths.columnconfigure(1, weight=1)
        self._path_row(paths, 0, "처리할 파일", self.folder_var)
        self._path_row(paths, 1, "결과 저장", self.output_var)
        self._path_row(paths, 2, "로그 저장", self.logs_var)
        return page

    def _process_page(self) -> tk.Frame:
        page = self._page("파일처리", "처리할 파일을 고르고 시작하세요. 복잡한 설정은 숨겨두었습니다.", "⚡")
        page.columnconfigure(0, weight=1)
        form = self._card(page, 1, "처리 준비")
        form.columnconfigure(1, weight=1)
        self._path_row(form, 0, "처리할 파일 폴더", self.folder_var)
        tk.Label(form, text="처리 방식", bg=SURFACE, fg=MUTED, font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=8)
        job_box = ttk.Combobox(form, textvariable=self.job_type_var, values=["Sample test", "Excel check", "Advanced command"], state="readonly")
        job_box.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=8)
        job_box.bind("<<ComboboxSelected>>", lambda _e: self._apply_job_type())
        self._path_row(form, 2, "결과 저장 폴더", self.output_var)

        self.advanced_frame = tk.Frame(form, bg=SURFACE)
        self.advanced_frame.grid(row=3, column=0, columnspan=3, sticky="ew")
        self.advanced_frame.columnconfigure(1, weight=1)
        tk.Label(self.advanced_frame, text="파일 형식", bg=SURFACE, fg=MUTED, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=8)
        self._entry(self.advanced_frame, self.pattern_var).grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=8)
        tk.Label(self.advanced_frame, text="고급 실행 방식", bg=SURFACE, fg=MUTED, font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=8)
        self._entry(self.advanced_frame, self.command_var).grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=8)
        tk.Checkbutton(form, text="고급 설정 보기", bg=SURFACE, variable=self.advanced_visible, command=self._toggle_advanced, font=("Segoe UI", 10)).grid(row=4, column=1, sticky="w", pady=8)

        actions = tk.Frame(page, bg=BG)
        actions.grid(row=2, column=0, sticky="ew", pady=12)
        for i in range(3):
            actions.columnconfigure(i, weight=1)
        self._button(actions, "기기 연결 확인", self._test_all).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._button(actions, "파일 처리 시작", self._run_jobs, primary=True).grid(row=0, column=1, sticky="ew", padx=8)
        self._button(actions, "실패 파일 재처리", self._retry_failed).grid(row=0, column=2, sticky="ew", padx=(8, 0))
        self._toggle_advanced()
        return page

    def _sound_page(self) -> tk.Frame:
        page = self._page("사운드바", "여러 PC 소리를 한 스피커로 모으기 위한 준비 화면입니다.", "🔊")
        page.rowconfigure(4, weight=1)
        page.columnconfigure(0, weight=1)

        mode = self._card(page, 1, "이 PC 역할")
        tk.Radiobutton(mode, text="이 PC가 모든 소리를 받아서 스피커로 재생", bg=SURFACE, variable=self.sound_mode, value="This PC receives audio", font=("Segoe UI", 11)).pack(anchor="w", pady=4)
        tk.Radiobutton(mode, text="이 PC 소리를 다른 PC로 보내기", bg=SURFACE, variable=self.sound_mode, value="This PC sends audio", font=("Segoe UI", 11)).pack(anchor="w", pady=4)

        bar = self._card(page, 2, "전체 사운드바")
        bar.columnconfigure(1, weight=1)
        tk.Label(bar, text="전체 볼륨", bg=SURFACE, fg=MUTED, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Scale(bar, from_=0, to=100, variable=self.master_volume, orient="horizontal", command=lambda _v: self._save_sound_config()).grid(row=0, column=1, sticky="ew", padx=12)
        self._button(bar, "스피커 테스트", self._test_beep).grid(row=0, column=2, padx=6)
        self._button(bar, "윈도우 볼륨", self._open_volume_mixer).grid(row=0, column=3, padx=(6, 0))

        tools = tk.Frame(page, bg=BG)
        tools.grid(row=3, column=0, sticky="ew", pady=(2, 8))
        for i in range(4):
            tools.columnconfigure(i, weight=1)
        self._button(tools, "오디오 도구 확인", self._check_audio_tools, primary=True).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._button(tools, "VBAN 열기", lambda: webbrowser.open("https://vb-audio.com/Voicemeeter/vban.htm")).grid(row=0, column=1, sticky="ew", padx=6)
        self._button(tools, "Scream 열기", lambda: webbrowser.open("https://github.com/duncanthrax/scream")).grid(row=0, column=2, sticky="ew", padx=6)
        self._button(tools, "SonoBus 열기", lambda: webbrowser.open("https://www.sonobus.net/")).grid(row=0, column=3, sticky="ew", padx=(6, 0))

        mixer = self._card(page, 4, "PC별 볼륨")
        mixer.grid(sticky="nsew")
        mixer.columnconfigure(1, weight=1)
        self.sound_mixer_frame = mixer
        self._refresh_sound_mixer()
        tk.Label(page, textvariable=self.sound_status_var, bg=BG, fg=MUTED, font=("Segoe UI", 10), wraplength=820, justify="left").grid(row=5, column=0, sticky="w", pady=(8, 0))
        return page

    def _assist_page(self) -> tk.Frame:
        page = self._page("AI 원격지원", "상대 PC에서 허용한 화면을 확인하고, 필요한 작업 권한을 단계별로 받을 준비 화면입니다.", "AI")
        page.rowconfigure(3, weight=1)
        page.columnconfigure(0, weight=1)

        start = self._card(page, 1, "연결 허용")
        start.columnconfigure(1, weight=1)
        tk.Label(start, text="1", bg=BRAND, fg="white", font=("Segoe UI", 16, "bold"), width=3, height=1).grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 14))
        tk.Label(start, text="이 PC 화면 확인을 허용", bg=SURFACE, fg=INK, font=("Segoe UI", 16, "bold")).grid(row=0, column=1, sticky="w")
        tk.Label(
            start,
            text="버튼을 누르면 6자리 코드와 스크린샷 주소가 만들어집니다. 코드를 아는 사람만 현재 화면 이미지를 볼 수 있습니다.",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 10),
            wraplength=760,
            justify="left",
        ).grid(row=1, column=1, sticky="w", pady=(4, 0))
        self._button(start, "AI 원격지원 허용", self._start_remote_assist, primary=True).grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 0))

        tools = self._card(page, 2, "도구")
        for i in range(4):
            tools.columnconfigure(i, weight=1)
        self._button(tools, "내 화면 스크린샷 저장", self._save_local_screenshot, primary=True).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._button(tools, "스크린샷 주소 복사", self._copy_assist_url).grid(row=0, column=1, sticky="ew", padx=6)
        self._button(tools, "처리 폴더 열기", self._open_input_folder).grid(row=0, column=2, sticky="ew", padx=6)
        self._button(tools, "엑셀 열기", self._open_excel).grid(row=0, column=3, sticky="ew", padx=(6, 0))

        status = self._card(page, 3, "상태")
        status.grid(sticky="nsew")
        status.columnconfigure(0, weight=1)
        tk.Label(status, textvariable=self.assist_status_var, bg=SURFACE, fg=INK, font=("Segoe UI", 12, "bold"), wraplength=860, justify="left").grid(row=0, column=0, sticky="w")
        url_entry = self._entry(status, self.assist_url_var)
        url_entry.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        url_entry.configure(state="readonly")
        tk.Label(
            status,
            text="현재 버전은 안전을 위해 화면 스크린샷 공유부터 제공합니다. 마우스/키보드 조종, 엑셀 파일 열기, 앱 실행은 다음 단계에서 권한별 버튼과 로그를 붙여 확장합니다.",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 10),
            wraplength=860,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(14, 0))
        return page

    def _running_page(self) -> tk.Frame:
        page = self._page("실행로그", "앱이 지금 무엇을 하는지 보여줍니다.", "📋")
        page.rowconfigure(2, weight=1)
        self._button(page, "로그 지우기", lambda: self.log.delete("1.0", "end")).grid(row=1, column=0, sticky="e")
        self.log = tk.Text(page, height=24, wrap="word", font=("Consolas", 10), bg=SURFACE, relief="flat", padx=14, pady=12)
        self.log.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        return page

    def _errors_page(self) -> tk.Frame:
        page = self._page("에러로그", "실패한 파일과 이유만 모아서 보여줍니다.", "⚠️")
        page.rowconfigure(2, weight=1)
        bar = tk.Frame(page, bg=BG)
        bar.grid(row=1, column=0, sticky="ew")
        self._button(bar, "새로고침", self._refresh_errors, primary=True).pack(side="left")
        self._button(bar, "실패 파일 재처리", self._retry_failed).pack(side="left", padx=8)
        self.error_text = tk.Text(page, height=24, wrap="word", font=("Consolas", 10), bg=SURFACE, relief="flat", padx=14, pady=12)
        self.error_text.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        return page

    def _mcp_page(self) -> tk.Frame:
        page = self._page("MCP 연결", "Codex/Cursor/Claude 연결용입니다. 일반 사용자는 몰라도 됩니다.", "🔌")
        page.rowconfigure(3, weight=1)
        text = tk.Text(page, height=11, wrap="none", font=("Consolas", 10), bg=SURFACE, relief="flat", padx=14, pady=12)
        text.grid(row=1, column=0, sticky="nsew")
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

        actions = tk.Frame(page, bg=BG)
        actions.grid(row=2, column=0, sticky="ew", pady=10)
        for index in range(3):
            actions.columnconfigure(index, weight=1)
        self._button(actions, "내 PC MCP 확인", self._inspect_local_mcp, primary=True).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._button(actions, "등록 PC MCP 확인", self._inspect_all_mcp).grid(row=0, column=1, sticky="ew", padx=6)
        self._button(actions, "MCP 목록 지우기", self._clear_mcp_inventory).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        self.mcp_inventory_text = tk.Text(page, height=13, wrap="word", font=("Consolas", 10), bg=SURFACE, relief="flat", padx=14, pady=12)
        self.mcp_inventory_text.grid(row=3, column=0, sticky="nsew")
        self.mcp_inventory_text.insert("end", "버튼을 누르면 이 PC 또는 등록된 PC의 Codex/Cursor MCP 등록 목록을 보여줍니다.\n")
        return page

    def _path_row(self, parent: tk.Misc, row: int, label: str, variable: tk.StringVar) -> None:
        tk.Label(parent, text=label, bg=SURFACE, fg=MUTED, font=("Segoe UI", 10, "bold")).grid(row=row, column=0, sticky="w", pady=8)
        self._entry(parent, variable).grid(row=row, column=1, sticky="ew", padx=(10, 8), pady=8)
        self._button(parent, "찾기", lambda: self._browse(variable)).grid(row=row, column=2, sticky="ew", pady=8)

    def _browse(self, variable: tk.StringVar) -> None:
        selected = filedialog.askdirectory(initialdir=variable.get() or str(APP_DIR))
        if selected:
            variable.set(selected)

    def _show(self, key: str) -> None:
        for name, button in self.nav_buttons.items():
            button.configure(bg=BRAND if name == key else "#191f2b", fg="white" if name == key else "#e5e7eb")
        if key == "sound":
            self._refresh_sound_mixer()
        self.pages[key].tkraise()
        if key == "errors":
            self._refresh_errors()

    def _load_workers(self) -> None:
        self.workers = load_all_workers(CONFIG_PATH)
        self._refresh_tree()
        self._write("앱이 준비됐습니다. 홈에서 순서대로 시작하세요.")

    def _refresh_tree(self) -> None:
        if not hasattr(self, "tree"):
            return
        self.tree.delete(*self.tree.get_children())
        for index, worker in enumerate(self.workers):
            host = "이 PC" if worker.type == "local" else worker.host
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
            messagebox.showinfo("삭제 불가", "이 PC는 목록에 남겨두는 것이 안전합니다.")
            return
        del self.workers[index]
        self._refresh_tree()
        self._save_workers()

    def _apply_form(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("기기 선택", "기기를 먼저 선택하세요.")
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
        messagebox.showinfo("기기 연결 허용", f"다른 PC에서 '번호로 추가'를 누르고 입력하세요.\n\n번호: {info.code}\n이 PC 주소: {info.host}")
        self._write(f"연결 번호 활성화: {info.code}, 주소: {info.host}")

    def _add_by_code(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("번호로 추가")
        dialog.geometry("380x180")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg=BG)
        code_var = tk.StringVar()
        tk.Label(dialog, text="다른 PC에 표시된 6자리 번호", bg=BG, fg=INK, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=18, pady=(18, 6))
        self._entry(dialog, code_var).pack(fill="x", padx=18)

        def add() -> None:
            code = code_var.get().strip()
            dialog.destroy()
            self._run_background("번호로 기기 찾기", lambda: self._pair_by_code(code))

        self._button(dialog, "기기 찾기", add, primary=True).pack(fill="x", padx=18, pady=16)

    def _pair_by_code(self, code: str) -> object:
        info = find_pairing_code(code)
        if not info:
            raise ValueError("해당 번호의 PC를 찾지 못했습니다. 같은 Wi-Fi와 방화벽을 확인하세요.")
        self.queue.put(("add_worker", (info.name, info.host)))
        return {"name": info.name, "host": info.host}

    def _open_discovery(self) -> None:
        self._run_background("같은 Wi-Fi PC 찾기", discover_same_wifi)

    def _test_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            messagebox.showinfo("기기 선택", "테스트할 기기를 선택하세요.")
            return
        self._run_background("선택 기기 테스트", lambda: [test_worker(self.workers[index])])

    def _test_all(self) -> None:
        self._run_background("전체 기기 연결 확인", lambda: [test_worker(worker) for worker in self._enabled_workers()])

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
                raise ValueError("선택한 폴더에서 처리할 파일을 찾지 못했습니다.")
            return run_jobs(workers, jobs, self.command_var.get(), self.output_var.get(), self.logs_var.get())

        self._run_background("파일 처리", task)

    def _retry_failed(self) -> None:
        self._run_background("실패 파일 재처리", lambda: retry_failed(self._enabled_workers(), self.command_var.get(), self.output_var.get(), self.logs_var.get()))

    def _inspect_local_mcp(self) -> None:
        self._show_mcp_inventory(inspect_local_mcp("local"))

    def _inspect_all_mcp(self) -> None:
        self._run_background("MCP 등록 확인", lambda: inspect_workers_mcp(self._enabled_workers()))

    def _clear_mcp_inventory(self) -> None:
        if hasattr(self, "mcp_inventory_text"):
            self.mcp_inventory_text.delete("1.0", "end")

    def _show_mcp_inventory(self, entries: list[McpEntry]) -> None:
        if not hasattr(self, "mcp_inventory_text"):
            return
        self.mcp_inventory_text.delete("1.0", "end")
        if not entries:
            self.mcp_inventory_text.insert("end", "등록된 MCP를 찾지 못했습니다.\n")
            return
        for entry in entries:
            self.mcp_inventory_text.insert("end", f"[{entry.pc}] {entry.app} / {entry.name}\n")
            self.mcp_inventory_text.insert("end", f"  방식: {entry.kind}\n")
            self.mcp_inventory_text.insert("end", f"  대상: {entry.target or '-'}\n")
            self.mcp_inventory_text.insert("end", f"  상태: {entry.status}\n")
            self.mcp_inventory_text.insert("end", f"  파일: {entry.source}\n\n")

    def _run_share_setup(self) -> None:
        script = APP_DIR / "setup_shared_disk_on_A_admin.bat"
        if not script.exists():
            messagebox.showerror("파일 없음", f"공유폴더 설정 파일이 없습니다.\n{script}")
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

    def _start_remote_assist(self) -> None:
        try:
            if self.remote_assist_server is None:
                self.remote_assist_server = RemoteAssistServer()
            info = self.remote_assist_server.start()
        except Exception as exc:
            messagebox.showerror("AI 원격지원", f"원격지원 서버를 시작하지 못했습니다.\n{exc}")
            return

        self.assist_url_var.set(info.screenshot_url)
        self.assist_status_var.set(
            f"허용됨: 이 PC({info.name}) 화면 확인 코드 {info.code}. 같은 Wi-Fi PC에서 아래 주소를 열면 현재 화면 스크린샷을 볼 수 있습니다."
        )
        self.clipboard_clear()
        self.clipboard_append(info.screenshot_url)
        self._write(f"AI 원격지원 허용: {info.screenshot_url}")
        messagebox.showinfo("AI 원격지원 허용", f"연결 코드: {info.code}\n\n스크린샷 주소를 클립보드에 복사했습니다.")

    def _save_local_screenshot(self) -> None:
        try:
            path = save_screenshot(Path(self.output_var.get()) / "assist-screenshot.png")
        except Exception as exc:
            messagebox.showerror("스크린샷 저장", str(exc))
            return
        self.assist_status_var.set(f"스크린샷 저장 완료: {path}")
        self._write(f"스크린샷 저장: {path}")

    def _copy_assist_url(self) -> None:
        url = self.assist_url_var.get().strip()
        if not url:
            messagebox.showinfo("AI 원격지원", "먼저 'AI 원격지원 허용'을 눌러 주소를 만들어주세요.")
            return
        self.clipboard_clear()
        self.clipboard_append(url)
        messagebox.showinfo("AI 원격지원", "스크린샷 주소를 복사했습니다.")

    def _open_input_folder(self) -> None:
        folder = Path(self.folder_var.get())
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(folder)])

    def _open_excel(self) -> None:
        try:
            subprocess.Popen(["excel.exe"])
        except OSError:
            messagebox.showerror("엑셀 열기", "Excel을 찾지 못했습니다. 이 PC에 Microsoft Excel이 설치되어 있는지 확인해주세요.")

    def _load_sound_config(self) -> None:
        config = load_sound_config(SOUND_CONFIG_PATH, self.master_volume.get(), self.sound_mode.get())
        self.master_volume.set(config.master_volume)
        self.sound_mode.set(config.mode)

    def _save_sound_config(self) -> None:
        devices: dict[str, dict[str, object]] = {}
        for name, controls in self.sound_rows.items():
            volume = controls.get("volume")
            muted = controls.get("muted")
            if isinstance(volume, tk.IntVar) and isinstance(muted, tk.BooleanVar):
                devices[name] = {"volume": volume.get(), "muted": muted.get()}
        save_sound_config(
            SOUND_CONFIG_PATH,
            SoundHubConfig(master_volume=self.master_volume.get(), mode=self.sound_mode.get(), devices=devices),
        )

    def _refresh_sound_mixer(self) -> None:
        if not hasattr(self, "sound_mixer_frame"):
            return
        for child in self.sound_mixer_frame.winfo_children():
            child.destroy()
        self.sound_rows = {}
        saved = load_sound_config(SOUND_CONFIG_PATH, self.master_volume.get(), self.sound_mode.get()).devices
        if not self.workers:
            tk.Label(self.sound_mixer_frame, text="아직 등록된 기기가 없습니다.", bg=SURFACE, fg=MUTED, font=("Segoe UI", 11)).grid(row=0, column=0, sticky="w")
            return
        for col, label in enumerate(["기기", "볼륨", "음소거", "소리 감지"]):
            tk.Label(self.sound_mixer_frame, text=label, bg=SURFACE, fg=MUTED, font=("Segoe UI", 10, "bold")).grid(row=0, column=col, sticky="w", padx=8, pady=4)
        for row, worker in enumerate(self.workers, start=1):
            device_data = saved.get(worker.name, {}) if isinstance(saved, dict) else {}
            volume = tk.IntVar(value=int(device_data.get("volume", 80)) if isinstance(device_data, dict) else 80)
            muted = tk.BooleanVar(value=bool(device_data.get("muted", False)) if isinstance(device_data, dict) else False)
            tk.Label(self.sound_mixer_frame, text=worker.name, bg=SURFACE, fg=INK, font=("Segoe UI", 11, "bold")).grid(row=row, column=0, sticky="w", padx=8, pady=7)
            ttk.Scale(self.sound_mixer_frame, from_=0, to=100, variable=volume, orient="horizontal", command=lambda _v: self._save_sound_config()).grid(row=row, column=1, sticky="ew", padx=8, pady=7)
            tk.Checkbutton(self.sound_mixer_frame, variable=muted, bg=SURFACE, command=self._save_sound_config).grid(row=row, column=2, sticky="w", padx=8, pady=7)
            ttk.Progressbar(self.sound_mixer_frame, maximum=100, value=0).grid(row=row, column=3, sticky="ew", padx=8, pady=7)
            self.sound_rows[worker.name] = {"volume": volume, "muted": muted}
        self.sound_mixer_frame.columnconfigure(1, weight=1)
        self.sound_mixer_frame.columnconfigure(3, weight=1)

    def _test_beep(self) -> None:
        volume = self.master_volume.get()
        self.sound_status_var.set(f"스피커 테스트 완료. 저장된 전체 볼륨 값: {volume}%.")
        test_speaker_beep()
        self._save_sound_config()

    def _open_volume_mixer(self) -> None:
        open_windows_volume_mixer()
        self.sound_status_var.set("Windows 볼륨 믹서를 열었습니다.")

    def _check_audio_tools(self) -> None:
        checks = check_audio_tools()
        lines: list[str] = []
        for label, found in checks.items():
            lines.append(f"{label}: {'설치됨' if found else '없음'}")
        lines.append("실제 네트워크 오디오는 VBAN, Scream, SonoBus 중 하나를 연결해야 합니다.")
        self.sound_status_var.set(" | ".join(lines))
        self._write("\n".join(lines))

    def _on_close(self) -> None:
        if self.remote_assist_server is not None:
            self.remote_assist_server.stop()
        if self.pairing_server is not None:
            self.pairing_server.stop()
        self.destroy()

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
                    if title == "같은 Wi-Fi PC 찾기" and isinstance(value, list):
                        self._show_discovery_results(value)
                    if title == "MCP 등록 확인" and isinstance(value, list):
                        self._show("mcp")
                        self._show_mcp_inventory(value)
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
        dialog.configure(bg=BG)
        frame = tk.Frame(dialog, bg=BG, padx=14, pady=14)
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

        self._button(frame, "선택한 PC 추가", add, primary=True).grid(row=1, column=0, sticky="ew", pady=(12, 0))

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
