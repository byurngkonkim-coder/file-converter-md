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

# OCR 지원 가상환경 파이썬 경로 후보들 (독립 worker 실행용)
_BASE_DIR = PROJECT_ROOT
OCR_PYTHON_CANDIDATES = [
    # 1. 파일형식변환기 자체 venv
    _BASE_DIR / "venv" / "Scripts" / "pythonw.exe",
    _BASE_DIR / "venv" / "Scripts" / "python.exe",
    # 2. 동일 워크스페이스 내 MyOCR venv (존재 시)
    _BASE_DIR.parent / "MyOCR" / "venv" / "Scripts" / "pythonw.exe",
    _BASE_DIR.parent / "MyOCR" / "venv" / "Scripts" / "python.exe",
    # 3. 동일 워크스페이스 내 01_OCR 엔진 venv (존재 시)
    _BASE_DIR.parent / "01_OCR_스캔파일텍스트추출프로그램" / "04_처리엔진" / "venv" / "Scripts" / "pythonw.exe",
    _BASE_DIR.parent / "01_OCR_스캔파일텍스트추출프로그램" / "04_처리엔진" / "venv" / "Scripts" / "python.exe",
    # 4. 현재 실행 중인 Python 인터프리터 (GUI용 pythonw 우선)
    Path(sys.executable).with_name("pythonw.exe") if Path(sys.executable).with_name("pythonw.exe").exists() else Path(sys.executable),
]


def get_ocr_python() -> str:
    """사용 가능한 OCR Python 실행 파일 경로를 반환합니다."""
    for cand in OCR_PYTHON_CANDIDATES:
        if cand.exists():
            return str(cand)
    return sys.executable
