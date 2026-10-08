# -*- coding: utf-8 -*-
"""adapters/markitdown_adapter.py - Microsoft MarkItDown 기반 문서 변환 어댑터.

출처: https://github.com/microsoft/markitdown
Office 미설치 환경에서도 PDF, Word(.docx), PowerPoint(.pptx), Excel(.xlsx), HTML 등을
고품질 Markdown 으로 변환합니다.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from adapters.base import BaseAdapter, ConversionResult
from core.text_cleaner import tidy

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def is_markitdown_available() -> bool:
    """markitdown 라이브러리가 설치되어 임포트 가능한지 확인합니다."""
    try:
        import markitdown
        return True
    except ImportError:
        return False


class MarkItDownAdapter(BaseAdapter):
    """Microsoft MarkItDown 변환 어댑터."""

    SUPPORTED_EXTS = {
        ".docx",
        ".pptx",
        ".xlsx",
        ".pdf",
        ".html",
        ".htm",
        ".csv",
        ".json",
        ".xml",
        ".txt",
    }

    def __init__(self):
        self._engine = None

    def _ensure_engine(self):
        if self._engine is None:
            from markitdown import MarkItDown
            self._engine = MarkItDown()
        return self._engine

    def can_handle(self, ext: str) -> bool:
        if not is_markitdown_available():
            return False
        return ext.lower() in self.SUPPORTED_EXTS

    def convert(self, path: Path, session: Any = None) -> ConversionResult:
        engine = self._ensure_engine()
        abs_path = str(path.resolve())

        try:
            result = engine.convert(abs_path)
            raw_text = getattr(result, "text_content", "") or ""
            md_text = tidy(raw_text)
        except Exception as e:
            raise RuntimeError(f"MarkItDown 변환 실패: {e}")

        if not md_text.strip():
            raise RuntimeError("MarkItDown 변환 결과 본문이 비어 있습니다.")

        return ConversionResult(
            body=md_text,
            conversion_method="markitdown",
            status="success",
        )
