# -*- coding: utf-8 -*-
"""adapters/__init__.py - 파일 형식별 변환 어댑터 레지스트리 및 엔진 라우터."""
from __future__ import annotations

import os
import sys
from typing import Any

from adapters.base import BaseAdapter, ConversionResult
from adapters.docx_adapter import DocxAdapter
from adapters.epub_adapter import EpubAdapter
from adapters.excel_adapter import ExcelAdapter
from adapters.hwp_adapter import HwpAdapter
from adapters.markitdown_adapter import MarkItDownAdapter
from adapters.ocr_adapter import OcrAdapter
from adapters.pdf_adapter import PdfAdapter
from adapters.ppt_adapter import PptAdapter
from adapters.text_adapter import TextAdapter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 싱글톤 인스턴스
_MARKITDOWN_ADAPTER = MarkItDownAdapter()

NATIVE_ADAPTERS: list[BaseAdapter] = [
    DocxAdapter(),
    HwpAdapter(),
    PptAdapter(),
    ExcelAdapter(),
    PdfAdapter(),
    EpubAdapter(),
    TextAdapter(),
    OcrAdapter(),
]


def get_adapter_for_path(path_str: str, engine: str = "auto") -> BaseAdapter | None:
    """주어진 파일 확장자와 엔진 선택 모드('auto', 'markitdown', 'native')에 대응하는 어댑터를 반환합니다.

    - 'markitdown': MarkItDown 지원 포맷은 MarkItDown 어댑터 우선, 미지원(HWP, 구버전, 이미지 등)은 네이티브 어댑터 Fallback
    - 'auto': 한국어 특화(HWP/HWPX) 및 구버전 오피스는 네이티브/COM, 현대 문서(docx/pptx/xlsx/pdf)는 MarkItDown 지원
    - 'native': 기존 내장(mammoth/COM/PyMuPDF/한글) 어댑터 사용
    """
    _, ext = os.path.splitext(path_str)
    ext = ext.lower()
    engine = (engine or "auto").lower()

    if engine == "markitdown":
        if _MARKITDOWN_ADAPTER.can_handle(ext):
            return _MARKITDOWN_ADAPTER
        # MarkItDown 미지원 형식(hwp, doc, 이미지 등)은 네이티브로 자동 폴백
        for adapter in NATIVE_ADAPTERS:
            if adapter.can_handle(ext):
                return adapter
        return None

    if engine == "auto":
        # HWP, Office(Word/PPT), PDF 및 텍스트 등 콘텐츠 중심 네이티브 어댑터 우선
        if ext in {".hwp", ".hwpx", ".docx", ".doc", ".rtf", ".pptx", ".ppt", ".pdf", ".xls", ".xlsx", ".txt", ".md", ".markdown"}:
            for adapter in NATIVE_ADAPTERS:
                if adapter.can_handle(ext):
                    return adapter
        # 그 외 MarkItDown 지원 포맷 (HTML, CSV, JSON, XML 등)
        if _MARKITDOWN_ADAPTER.can_handle(ext):
            return _MARKITDOWN_ADAPTER
        for adapter in NATIVE_ADAPTERS:
            if adapter.can_handle(ext):
                return adapter
        return None

    # 'native' 모드
    for adapter in NATIVE_ADAPTERS:
        if adapter.can_handle(ext):
            return adapter

    return None
