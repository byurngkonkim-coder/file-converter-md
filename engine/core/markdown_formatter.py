# -*- coding: utf-8 -*-
"""core/markdown_formatter.py - 프롬프트 규격 표준 Markdown 본문 템플릿 조립기."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from core.text_cleaner import tidy

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def format_markdown_document(
    *,
    title: str,
    source_file: str,
    source_path: str,
    doc_category: str,
    topics: list[str],
    description: str,
    body_content: str,
    tables_content: str = "",
    pages_content: list[tuple[int, str]] | None = None,
    ocr_confidence: str = "unknown",
    unrecognized_areas: str = "없음",
    structural_damage_risk: str = "낮음",
    action_items: str = "없음",
    conversion_method: str = "native",
    created_at_str: str | None = None,
) -> str:
    """프롬프트 표준에 맞춘 Markdown 전체 본문을 구성합니다."""
    date_now = created_at_str or dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sections = []

    # 1. 문서 제목
    sections.append(f"# {title}\n")

    # 2. 문서 개요
    topics_str = ", ".join(topics) if topics else "일반"
    overview = [
        "## 문서 개요\n",
        f"- 원본 파일명: {source_file}",
        f"- 문서 유형: {doc_category}",
        f"- 작성·시행일자: {date_now}",
        f"- 주요 주제: {topics_str}",
        f"- 핵심 요약: {description}\n",
    ]
    sections.append("\n".join(overview))

    # 3. 본문 내용 (기존 본문에서 첫 번째 h1 타이틀이 중복되지 않도록 정리)
    cleaned_body = body_content.strip()
    if cleaned_body:
        # 첫 번째 라인이 # {title} 형태이면 제거하여 중복 방지
        lines = cleaned_body.splitlines()
        if lines and lines[0].strip().startswith("# ") and title in lines[0]:
            cleaned_body = "\n".join(lines[1:]).strip()

        sections.append("## 본문 내용\n\n" + cleaned_body + "\n")

    # 4. 표 및 데이터
    if tables_content.strip():
        sections.append("## 표 및 데이터\n\n" + tables_content.strip() + "\n")

    # 5. 추출 품질 및 검토 사항
    quality = [
        "## 추출 품질 및 검토 사항\n",
        f"- OCR 신뢰도: {ocr_confidence}",
        f"- 인식 불명확 구간: {unrecognized_areas}",
        f"- 원본 구조 손상 가능성: {structural_damage_risk}",
        f"- 추가 확인 필요 사항: {action_items}\n",
    ]
    sections.append("\n".join(quality))

    # 7. 원본 정보
    origin_info = [
        "## 원본 정보\n",
        f"- 원본 파일: {source_file}",
        f"- 원본 경로: {Path(source_path).as_posix()}",
        f"- 변환 방식: {conversion_method}",
        f"- 생성일시: {date_now}\n",
    ]
    sections.append("\n".join(origin_info))

    raw_doc = "\n\n".join(sections)
    return tidy(raw_doc)
