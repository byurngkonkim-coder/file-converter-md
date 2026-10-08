# -*- coding: utf-8 -*-
"""core/com_session.py - Word, Excel, PowerPoint, 한글(HWP) COM 세션 관리자.

- 지연 기동(Lazy Initialization)으로 불필요한 Office 앱 구동을 방지합니다.
- HWP 실행 시 보안 팝업을 백그라운드 스레드로 자동 승인합니다.
- 세션 종료 시 모든 COM 객체와 임시 작업 디렉토리를 안전하게 정리합니다.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class ComSession:
    """Office 및 한글 COM 객체 세션 풀."""

    def __init__(self, auto_approve_hwp: bool = True):
        self._apps: dict[str, Any] = {}
        self._temp_dir: Path | None = None
        self._auto_approve_hwp = auto_approve_hwp
        self._watcher_stop = threading.Event()
        self._watcher_thread: threading.Thread | None = None

    def get(self, kind: str) -> Any:
        """kind ('word', 'excel', 'ppt', 'hwp')에 해당하는 COM 애플리케이션 인스턴스를 반환합니다."""
        kind = kind.lower()
        if kind in self._apps:
            return self._apps[kind]

        import win32com.client

        if kind == "word":
            app = win32com.client.DispatchEx("Word.Application")
            app.Visible = False
            app.DisplayAlerts = 0  # wdAlertsNone
            self._apps["word"] = app
            return app

        if kind == "excel":
            app = win32com.client.DispatchEx("Excel.Application")
            app.Visible = False
            app.DisplayAlerts = False
            app.ScreenUpdating = False
            self._apps["excel"] = app
            return app

        if kind == "ppt":
            app = win32com.client.DispatchEx("PowerPoint.Application")
            # PowerPoint는 Window가 없으면 일부 Shape 텍스트 접근이 불가하므로 최소화 상태로 띄움
            try:
                app.WindowState = 2  # ppWindowStateMinimize
            except Exception:
                pass
            self._apps["ppt"] = app
            return app

        if kind == "hwp":
            if self._auto_approve_hwp and self._watcher_thread is None:
                self._start_hwp_watcher()
            try:
                app = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
            except Exception:
                app = win32com.client.Dispatch("HWPFrame.HwpObject")
            try:
                app.RegisterModule("FilePathCheckDLL", "SecurityModule")
            except Exception:
                pass
            self._apps["hwp"] = app
            return app

        raise ValueError(f"지원하지 않는 COM 유형입니다: {kind}")

    def scratch(self, filename: str) -> Path:
        """세션 생명주기 동안 유지되는 임시 파일 경로를 생성합니다."""
        if self._temp_dir is None:
            self._temp_dir = Path(tempfile.mkdtemp(prefix="doc_conv_"))
        return self._temp_dir / filename

    def _start_hwp_watcher(self) -> None:
        """한글 보안 팝업('접근을 허용하시겠습니까?')을 주기적으로 감지하여 자동 클릭하는 감시 스레드를 시작합니다."""
        def _watch():
            try:
                import win32con
                import win32gui
            except ImportError:
                return

            while not self._watcher_stop.is_set():
                time.sleep(0.3)
                # 한글 보안 경고 다이얼로그 탐색
                for title in ("한글", "Hwp"):
                    hwnd = win32gui.FindWindow("#32770", title)
                    if not hwnd:
                        continue
                    # 텍스트 확인
                    matched = []

                    def _enum(child, _):
                        buf = win32gui.GetWindowText(child)
                        if any(k in buf for k in ("허용", "접근", "Security")):
                            matched.append(child)

                    try:
                        win32gui.EnumChildWindows(hwnd, _enum, None)
                    except Exception:
                        continue

                    if matched:
                        # [허용] 또는 기본 확인 버튼 클릭
                        btn = win32gui.FindWindowEx(hwnd, 0, "Button", "허용(&A)")
                        if not btn:
                            btn = win32gui.FindWindowEx(hwnd, 0, "Button", "허용")
                        if not btn:
                            btn = win32gui.FindWindowEx(hwnd, 0, "Button", "확인")
                        if btn:
                            win32gui.PostMessage(btn, win32con.BM_CLICK, 0, 0)
                        else:
                            # 엔터 키 전송
                            win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
                            win32gui.PostMessage(hwnd, win32con.WM_KEYUP, win32con.VK_RETURN, 0)

        self._watcher_thread = threading.Thread(target=_watch, daemon=True)
        self._watcher_thread.start()

    def close(self) -> None:
        """모든 COM 애플리케이션을 안전하게 종료하고 임시 폴더를 삭제합니다."""
        self._watcher_stop.set()

        for kind, app in list(self._apps.items()):
            try:
                if kind == "word":
                    app.Quit(0)
                elif kind == "excel":
                    app.Quit()
                elif kind == "ppt":
                    app.Quit()
                elif kind == "hwp":
                    app.Quit()
            except Exception:
                pass

        self._apps.clear()

        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def __enter__(self) -> ComSession:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
