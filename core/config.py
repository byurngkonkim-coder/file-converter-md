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

# 애플리케이션 기본 경로
APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = APP_DIR / "결과_MD"
DEFAULT_REPORT_DIR = APP_DIR / "변환리포트"

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
OCR_PYTHON_CANDIDATES = [
    Path(r"D:\백업\utility\MyOCR\venv\Scripts\python.exe"),
    Path(sys.executable),
]


def get_ocr_python() -> str:
    """사용 가능한 OCR Python 실행 파일 경로를 반환합니다."""
    for cand in OCR_PYTHON_CANDIDATES:
        if cand.exists():
            return str(cand)
    return sys.executable
