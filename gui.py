# -*- coding: utf-8 -*-
"""gui.py - 통합 문서 변환기 GUI 애플리케이션 (Tkinter 기반).

- 파일/폴더 선택 및 드래그 앤 드롭 지원 (tkinterdnd2 사용 시)
- 실시간 변환 진행률 게이지 및 로그 출력
- 백그라운드 스레드 비동기 처리로 UI 블로킹 방지
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

# Python 콘솔/출력 UTF-8 재설정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from core.batch_runner import collect_files, convert_batch, normalize_path
from core.config import DEFAULT_OUT_DIR, DEFAULT_REPORT_DIR, SUPPORTED_EXTENSIONS

# 드래그 앤 드롭 라이브러리 동적 지원 (windnd: Windows 네이티브, tkinterdnd2: Tk DND)
try:
    import windnd
    _HAS_WINDND = True
except ImportError:
    _HAS_WINDND = False

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _HAS_TKDND = True
except ImportError:
    _HAS_TKDND = False


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.files: list[Path] = []
        self.queue = queue.Queue()
        self.is_running = False

        root.title("통합 문서 -> OKF Markdown 변환기 Ver 1.0")
        root.geometry("880x640")
        root.minsize(720, 500)

        # 상단 타이틀
        top_frame = tk.Frame(root, padx=12, pady=10, bg="#2b2d42")
        top_frame.pack(fill="x")
        lbl_title = tk.Label(
            top_frame,
            text="통합 문서 → OKF Markdown 일괄 변환기",
            font=("맑은 고딕", 15, "bold"),
            fg="#edf2f4",
            bg="#2b2d42",
        )
        lbl_title.pack(side="left")
        lbl_sub = tk.Label(
            top_frame,
            text="Office / HWP / PDF / OCR / Text / EPUB",
            font=("맑은 고딕", 9),
            fg="#8d99ae",
            bg="#2b2d42",
        )
        lbl_sub.pack(side="right", padx=10)

        # 본문 프레임
        main_frame = tk.Frame(root, padx=12, pady=8)
        main_frame.pack(fill="both", expand=True)

        # 파일 목록 영역
        lbl_list = tk.Label(
            main_frame,
            text="📂 변환 대상 파일 목록 (파일 또는 폴더를 창으로 드래그 앤 드롭하세요 / 더블클릭 시 삭제)",
            font=("맑은 고딕", 9, "bold"),
            fg="#1d3557",
        )
        lbl_list.pack(anchor="w")

        list_container = tk.Frame(main_frame)
        list_container.pack(fill="both", expand=True, pady=4)

        self.listbox = tk.Listbox(
            list_container,
            selectmode="extended",
            font=("맑은 고딕", 9),
            bg="#ffffff",
            selectbackground="#3a86ff",
            selectforeground="#ffffff",
            relief="solid",
            bd=1,
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", self.remove_selected)
        self.listbox.bind("<Delete>", self.remove_selected)

        scrollbar = tk.Scrollbar(list_container, orient="vertical", command=self.listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scrollbar.set)

        # 드래그 앤 드롭 바인딩 (tkinterdnd2 최우선 등록, windnd 보조)
        self.dnd_enabled = False
        if _HAS_TKDND and hasattr(self.root, "drop_target_register"):
            try:
                for w in [self.root, self.listbox, list_container, main_frame, top_frame]:
                    try:
                        w.drop_target_register(DND_FILES)
                        w.dnd_bind("<<Drop>>", self.on_tkdnd_drop)
                    except Exception:
                        pass
                self.dnd_enabled = True
            except Exception as e:
                print(f"[알림] tkinterdnd2 바인딩 실패: {e}")

        if not self.dnd_enabled and _HAS_WINDND:
            try:
                windnd.hook_dropfiles(self.listbox, func=self.on_windnd_drop)
                windnd.hook_dropfiles(self.root, func=self.on_windnd_drop)
                self.dnd_enabled = True
            except Exception as e:
                print(f"[알림] windnd 바인딩 실패: {e}")

        # 파일 추가 버튼 바
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=4)

        btn_add_file = tk.Button(btn_frame, text="+ 파일 추가...", command=self.add_files, padx=8)
        btn_add_file.pack(side="left", padx=2)

        btn_add_folder = tk.Button(btn_frame, text="+ 폴더 추가...", command=self.add_folder, padx=8)
        btn_add_folder.pack(side="left", padx=2)

        btn_clear = tk.Button(btn_frame, text="목록 비우기", command=self.clear_files, padx=8)
        btn_clear.pack(side="left", padx=2)

        self.lbl_count = tk.Label(btn_frame, text="선택된 파일: 0개", font=("맑은 고딕", 9), fg="#2b2d42")
        self.lbl_count.pack(side="right", padx=6)

        # 설정 옵션 영역
        opt_frame = tk.LabelFrame(main_frame, text="변환 설정 및 출력 경로", padx=8, pady=6)
        opt_frame.pack(fill="x", pady=6)

        # 출력 경로
        out_subframe = tk.Frame(opt_frame)
        out_subframe.pack(fill="x", pady=2)
        tk.Label(out_subframe, text="출력 폴더:", width=10, anchor="w").pack(side="left")

        self.var_out = tk.StringVar(value=str(DEFAULT_OUT_DIR.resolve()))
        self.entry_out = tk.Entry(out_subframe, textvariable=self.var_out)
        self.entry_out.pack(side="left", fill="x", expand=True, padx=4)

        btn_browse_out = tk.Button(out_subframe, text="찾아보기...", command=self.browse_out_dir)
        btn_browse_out.pack(side="left", padx=2)

        btn_open_out = tk.Button(out_subframe, text="결과 폴더 열기", command=self.open_out_dir)
        btn_open_out.pack(side="left", padx=2)

        btn_open_rep = tk.Button(out_subframe, text="리포트 열기", command=self.open_report_dir)
        btn_open_rep.pack(side="left", padx=2)

        # 체크박스 옵션 및 엔진 선택
        chk_subframe = tk.Frame(opt_frame)
        chk_subframe.pack(fill="x", pady=2)

        self.var_recursive = tk.BooleanVar(value=True)
        chk_rec = tk.Checkbutton(chk_subframe, text="하위 폴더 포함", variable=self.var_recursive)
        chk_rec.pack(side="left", padx=4)

        self.var_overwrite = tk.BooleanVar(value=False)
        chk_ow = tk.Checkbutton(chk_subframe, text="덮어쓰기", variable=self.var_overwrite)
        chk_ow.pack(side="left", padx=4)

        self.var_skip_scanned = tk.BooleanVar(value=False)
        chk_skip_scan = tk.Checkbutton(
            chk_subframe,
            text="텍스트 없는 PDF/스캔 제외 (OCR 생략)",
            variable=self.var_skip_scanned,
        )
        chk_skip_scan.pack(side="left", padx=4)

        tk.Label(chk_subframe, text="|  엔진:").pack(side="left", padx=(8, 2))
        self.var_engine = tk.StringVar(value="auto (스마트 자동)")
        self.combo_engine = ttk.Combobox(
            chk_subframe,
            textvariable=self.var_engine,
            values=[
                "auto (스마트 자동)",
                "markitdown (MS MarkItDown 우선)",
                "native (내장 전용 어댑터)",
            ],
            state="readonly",
            width=26,
        )
        self.combo_engine.pack(side="left", padx=2)

        # 진행률 및 시작 버튼
        act_frame = tk.Frame(main_frame)
        act_frame.pack(fill="x", pady=4)

        self.prog_bar = ttk.Progressbar(act_frame, mode="determinate")
        self.prog_bar.pack(side="left", fill="x", expand=True, padx=4)

        self.btn_convert = tk.Button(
            act_frame,
            text="변환 시작",
            font=("맑은 고딕", 10, "bold"),
            bg="#2b2d42",
            fg="white",
            padx=20,
            pady=4,
            command=self.start_conversion,
        )
        self.btn_convert.pack(side="right", padx=4)

        # 실시간 로그 창
        log_frame = tk.Frame(main_frame)
        log_frame.pack(fill="both", expand=True, pady=4)

        self.txt_log = ScrolledText(log_frame, height=8, font=("Consolas", 9), bg="#f8f9fa")
        self.txt_log.pack(fill="both", expand=True)
        if self.dnd_enabled and hasattr(self.txt_log, "drop_target_register"):
            try:
                self.txt_log.drop_target_register(DND_FILES)
                self.txt_log.dnd_bind("<<Drop>>", self.on_tkdnd_drop)
            except Exception:
                pass

        self.root.after(100, self.process_queue)
        dnd_status_txt = "활성화됨 (파일/폴더 지원)" if self.dnd_enabled else "비활성화 (버튼 추가 이용)"
        self.log(f"[준비] 프로그램을 시작했습니다. (드래그 앤 드롭: {dnd_status_txt})")
        self.log("[안내] 파일이나 폴더를 창으로 직접 끌어다 놓거나(드래그 앤 드롭), 버튼을 눌러 추가하세요.")

    def log(self, text: str):
        self.txt_log.insert("end", text + "\n")
        self.txt_log.see("end")

    def process_queue(self):
        while not self.queue.empty():
            msg_type, payload = self.queue.get_nowait()
            if msg_type == "log":
                self.log(payload)
            elif msg_type == "progress":
                current, total, filename, status_txt = payload
                self.prog_bar["maximum"] = total
                self.prog_bar["value"] = current
            elif msg_type == "done":
                self.is_running = False
                self.btn_convert.config(state="normal", text="변환 시작")
                messagebox.showinfo("변환 완료", "모든 문서 변환 작업이 완료되었습니다!")
        self.root.after(100, self.process_queue)

    def on_windnd_drop(self, raw_items: list):
        """windnd 를 통한 윈도우 네이티브 드래그 앤 드롭 수신 (파일 및 폴더 지원)."""
        paths: list[str] = []
        for item in raw_items:
            if isinstance(item, bytes):
                try:
                    p = item.decode("utf-8")
                except UnicodeDecodeError:
                    p = item.decode("cp949", errors="replace")
            else:
                p = str(item)
            p = p.strip(' \t\r\n\'"')
            if p:
                paths.append(p)
        if paths:
            self.root.after(0, lambda: self._handle_dropped_paths(paths))

    def on_tkdnd_drop(self, event):
        """tkinterdnd2 를 통한 드래그 앤 드롭 수신 (파일 및 폴더 지원)."""
        data = getattr(event, "data", "") or ""
        if not data:
            return
        pattern = r'\{([^}]+)\}|(\S+)'
        matches = re.findall(pattern, data)
        paths: list[str] = []
        for m in matches:
            p = m[0] if m[0] else m[1]
            p = p.strip(' \t\r\n\'"')
            if p:
                paths.append(p)
        if paths:
            self.root.after(0, lambda: self._handle_dropped_paths(paths))

    def _handle_dropped_paths(self, paths: list[str]):
        self.log(f"[드래그 앤 드롭] {len(paths)}개 항목(파일/폴더) 감지됨")
        self.add_paths(paths)

    def add_paths(self, paths: list[str]):
        """주어진 파일 또는 폴더 경로 목록을 정규화하여 중복 없이 목록에 추가합니다."""
        found = collect_files(paths, recursive=self.var_recursive.get())
        added_count = 0
        for f in found:
            if f not in self.files:
                self.files.append(f)
                self.listbox.insert("end", f"{f.name} ({f.suffix}) - {f}")
                added_count += 1
        self.lbl_count.config(text=f"선택된 파일: {len(self.files)}개")
        if added_count > 0:
            self.log(f"[목록 추가] {added_count}개 파일이 변환 대상에 추가되었습니다. (총 {len(self.files)}개)")
        elif paths:
            self.log("[안내] 추가할 수 있는 새로운 지원 문서 형식이 없거나 이미 추가되어 있습니다.")

    def add_files(self):
        ext_filters = ";".join([f"*{ext}" for ext in SUPPORTED_EXTENSIONS.keys()])
        paths = filedialog.askopenfilenames(
            title="문서 파일 선택",
            filetypes=[("지원 문서", ext_filters), ("모든 파일", "*.*")],
        )
        if paths:
            self.add_paths(list(paths))

    def add_folder(self):
        folder = filedialog.askdirectory(title="폴더 선택")
        if folder:
            self.add_paths([folder])

    def remove_selected(self, _event=None):
        indices = list(self.listbox.curselection())
        for idx in reversed(indices):
            self.listbox.delete(idx)
            del self.files[idx]
        self.lbl_count.config(text=f"선택된 파일: {len(self.files)}개")

    def clear_files(self):
        self.listbox.delete(0, "end")
        self.files.clear()
        self.lbl_count.config(text="선택된 파일: 0개")

    def browse_out_dir(self):
        d = filedialog.askdirectory(title="출력 폴더 선택")
        if d:
            self.var_out.set(d)

    def open_out_dir(self):
        p = Path(self.var_out.get())
        p.mkdir(parents=True, exist_ok=True)
        os.startfile(str(p))

    def open_report_dir(self):
        p = DEFAULT_REPORT_DIR
        p.mkdir(parents=True, exist_ok=True)
        os.startfile(str(p))

    def start_conversion(self):
        if self.is_running:
            return
        if not self.files:
            messagebox.showwarning("파일 없음", "변환할 파일이 목록에 없습니다.")
            return

        out_dir = Path(self.var_out.get())
        overwrite = self.var_overwrite.get()
        skip_scanned = self.var_skip_scanned.get()
        targets = list(self.files)

        # 변환 엔진 모드 결정
        engine_raw = self.var_engine.get().lower()
        if "markitdown" in engine_raw:
            engine_mode = "markitdown"
        elif "native" in engine_raw:
            engine_mode = "native"
        else:
            engine_mode = "auto"

        self.is_running = True
        self.btn_convert.config(state="disabled", text="변환 중...")
        self.prog_bar["value"] = 0

        def _worker():
            def _prog(cur, tot, name, msg):
                self.queue.put(("progress", (cur, tot, name, msg)))

            def _log_cb(msg):
                self.queue.put(("log", msg))

            try:
                convert_batch(
                    targets,
                    out_dir=out_dir,
                    overwrite=overwrite,
                    engine=engine_mode,
                    skip_scanned=skip_scanned,
                    progress_callback=_prog,
                    log_callback=_log_cb,
                )
            except Exception as e:
                self.queue.put(("log", f"[오류] 작업 중 치명적 예외 발생: {e}"))
            finally:
                self.queue.put(("done", None))

        threading.Thread(target=_worker, daemon=True).start()


def main():
    root = TkinterDnD.Tk() if _HAS_TKDND else tk.Tk()
    app = App(root)
    if len(sys.argv) > 1:
        initial_paths = [p.strip(' \t\r\n\'"') for p in sys.argv[1:] if p.strip(' \t\r\n\'"')]
        if initial_paths:
            app.add_paths(initial_paths)
    root.mainloop()


if __name__ == "__main__":
    main()
