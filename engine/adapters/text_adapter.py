# -*- coding: utf-8 -*-
"""adapters/text_adapter.py - 텍스트 (.txt) 및 Markdown (.md) 변환 어댑터.

- .txt: charset-normalizer 기반 인코딩 자동 감지 및 UTF-8 정규화
- .md: 기존 YAML Front Matter 보존 및 병합, 마크다운 본문 구조 유지
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from adapters.base import BaseAdapter, ConversionResult
from core.frontmatter_builder import split_frontmatter
from core.text_cleaner import read_text, tidy

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class TextAdapter(BaseAdapter):
    """일반 텍스트 및 마크다운 파일 처리기."""

    def can_handle(self, ext: str) -> bool:
        return ext.lower() in {".txt", ".md", ".markdown"}

    def convert(self, path: Path, session: Any = None) -> ConversionResult:
        ext = path.suffix.lower()
        content = read_text(path)

        if not content.strip():
            raise RuntimeError("텍스트 파일이 비어 있습니다.")

        extra_meta = {}
        body = content

        if ext in {".md", ".markdown"}:
            # 기존 Front Matter 분리 및 보존
            existing_fm, clean_body = split_frontmatter(content)
            if existing_fm:
                extra_meta = existing_fm
            body = clean_body

        return ConversionResult(
            body=tidy(body),
            conversion_method="native",
            status="success",
            extra_metadata=extra_meta,
        )
