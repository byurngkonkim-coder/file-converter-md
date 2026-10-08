# -*- coding: utf-8 -*-
"""adapters/base.py - 문서 변환 어댑터 기본 인터페이스 및 반환 데이터 구조."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class ConversionResult:
    """단일 파일 변환 결과 데이터 객체."""
    body: str = ""
    tables: str = ""
    pages: list[tuple[int, str]] = field(default_factory=list)
    conversion_method: str = "native"  # native | converted | ocr
    ocr_required: bool = False
    ocr_confidence: str = "unknown"     # high | medium | low | unknown
    review_required: bool = False
    status: str = "success"             # success | partial | failed
    errors: list[str] = field(default_factory=list)
    unrecognized_areas: str = "없음"
    structural_damage_risk: str = "낮음"
    action_items: str = "없음"
    extra_metadata: dict[str, Any] = field(default_factory=dict)


class ScannedDocumentSkipped(Exception):
    """텍스트 레이어가 없는 스캔 PDF 또는 이미지 문서 변환 제외 시 발생하는 예외."""
    pass


class BaseAdapter:
    """모든 형식 변환 어댑터의 기반 클래스."""

    def can_handle(self, ext: str) -> bool:
        """해당 확장자를 처리할 수 있는지 여부를 반환합니다."""
        raise NotImplementedError

    def convert(self, path: Path, session: Any = None, **kwargs) -> ConversionResult:
        """파일을 변환하여 ConversionResult 를 반환합니다."""
        raise NotImplementedError
