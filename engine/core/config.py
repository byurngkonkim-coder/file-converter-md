# -*- coding: utf-8 -*-
"""core/config.py - 기본 설정, 경로 및 지원 확장자 정의.

Windows 환경에서 한글 인코딩 및 안전한 파일 경로를 보장합니다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Python 표준 출력/에러 인코딩 설정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 애플리케이션 및 프로젝트 루트 기본 경로
_curr = Path(__file__).resolve().parent.parent
if _curr.name.lower() in ("engine", "src", "_internal", "04_처리엔진", "04_엔진"):
    PROJECT_ROOT = _curr.parent
    APP_DIR = _curr
else:
    PROJECT_ROOT = _curr
    APP_DIR = _curr

DEFAULT_OUT_DIR = PROJECT_ROOT / "결과_MD"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "변환리포트"

# 지원 파일 확장자 분류
SUPPORTED_EXTENSIONS = {
    # 워드 문서
    ".docx": "docx",
    ".doc": "doc",
    ".rtf": "rtf",
    # 프리젠테이션
    ".pptx": "pptx",
    ".ppt": "ppt",
    # 스프레드시트
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".xls": "xls",
    # 한글 문서
    ".hwp": "hwp",
    ".hwpx": "hwpx",
    # PDF
    ".pdf": "pdf",
    # 전자책
    ".epub": "epub",
    # 텍스트 및 마크다운
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
    # 이미지 (OCR 대상)
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".bmp": "image",
    ".tiff": "image",
    ".tif": "image",
    ".webp": "image",
}

# 포터블 배포 및 로컬 실행 환경을 위한 OCR 및 보조 Python 실행 파일 경로 동적 탐색
def get_ocr_python_candidates() -> list[Path]:
    """USB 및 다양한 실행 환경에 유연하게 대응하는 Python 실행 파일 후보 목록을 반환합니다."""
    candidates: list[Path] = []

    # 1. 현재 실행 중인 파이썬 인터프리터 (GUI용 pythonw 우선)
    if sys.executable:
        pyw = Path(sys.executable).with_name("pythonw.exe")
        if pyw.exists():
            candidates.append(pyw)
        candidates.append(Path(sys.executable))

    # 2. 환경 변수 지정
    env_py = os.environ.get("OCR_PYTHON") or os.environ.get("PORTABLE_PYTHON")
    if env_py:
        candidates.append(Path(env_py.strip(' \t\r\n\'"')))

    # 3. 로컬 및 엔진 폴더 내부의 가상환경
    candidates.extend([
        APP_DIR / "venv" / "Scripts" / "pythonw.exe",
        APP_DIR / "venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / "venv" / "Scripts" / "pythonw.exe",
        PROJECT_ROOT / "venv" / "Scripts" / "python.exe",
        APP_DIR / ".venv" / "Scripts" / "python.exe",
        APP_DIR / "python" / "python.exe",
        APP_DIR / "Python311" / "python.exe",
        APP_DIR / "Python312" / "python.exe",
        APP_DIR / "Python310" / "python.exe",
    ])

    # 4. 인접 폴더 내 MyOCR 및 01_OCR 가상환경 (상대 경로 탐색)
    candidates.extend([
        PROJECT_ROOT.parent / "MyOCR" / "engine" / "venv" / "Scripts" / "pythonw.exe",
        PROJECT_ROOT.parent / "MyOCR" / "engine" / "venv" / "Scripts" / "python.exe",
        PROJECT_ROOT.parent / "MyOCR" / "venv" / "Scripts" / "pythonw.exe",
        PROJECT_ROOT.parent / "MyOCR" / "venv" / "Scripts" / "python.exe",
        PROJECT_ROOT.parent / "01_OCR_스캔파일텍스트추출프로그램" / "engine" / "venv" / "Scripts" / "pythonw.exe",
        PROJECT_ROOT.parent / "01_OCR_스캔파일텍스트추출프로그램" / "engine" / "venv" / "Scripts" / "python.exe",
        PROJECT_ROOT.parent / "01_OCR_스캔파일텍스트추출프로그램" / "04_처리엔진" / "venv" / "Scripts" / "pythonw.exe",
        PROJECT_ROOT.parent / "01_OCR_스캔파일텍스트추출프로그램" / "04_처리엔진" / "venv" / "Scripts" / "python.exe",
    ])

    # 5. 현재 실행 중인 드라이브 루트 기준 백업 유틸리티 경로 탐색 (USB 마운트 대응)
    drive = APP_DIR.drive
    if drive:
        candidates.append(Path(f"{drive}\\백업\\utility\\MyOCR\\venv\\Scripts\\python.exe"))

    # 6. 시스템 PATH 상의 python
    import shutil
    which_py = shutil.which("python")
    if which_py:
        candidates.append(Path(which_py))

    return candidates


def get_ocr_python() -> str:
    """사용 가능한 OCR Python 실행 파일 경로를 반환합니다. (USB 이동 시에도 동적 탐색)"""
    for cand in get_ocr_python_candidates():
        try:
            if cand and cand.exists() and cand.is_file():
                return str(cand.resolve())
        except Exception:
            continue
    return sys.executable


def get_safe_temp_dir() -> Path:
    """시스템 임시 디렉토리 쓰기 권한이 제한된 폐쇄망/공용 PC 환경을 대비한 안전 임시 폴더를 반환합니다."""
    import tempfile
    try:
        sys_temp = Path(tempfile.gettempdir())
        test_file = sys_temp / f".test_perm_{os.getpid()}.tmp"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        return sys_temp
    except Exception:
        # 시스템 temp 접근 실패 시 로컬 scratch 폴더로 폴백
        local_scratch = APP_DIR / "scratch" / "temp"
        local_scratch.mkdir(parents=True, exist_ok=True)
        return local_scratch
