# -*- coding: utf-8 -*-
"""core/frontmatter_builder.py - OKF_지식위키(build_frontmatter.py) 규격 100% 호환 YAML Front Matter 빌더 및 검증기.

특징:
1. OKF_지식위키 & Obsidian 표준 호환:
   - title, category, type, summary, source, source_path, created, converted, status, decision_status, tags, aliases
2. 기존 파일변환기 프롬프트 스키마 및 셀프 테스트 무결성 유지:
   - id, source_file, source_type, conversion_method, converted_from, output_file, language, created_at, updated_at, doc_category, topics, keywords, entities, ocr_required, ocr_confidence, review_required, status, errors
3. 2공백 들여쓰기 및 유니코드 안전 인코딩
4. split_frontmatter / yaml.safe_load 양방향 완전 검증
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def generate_doc_id(source_path: str, mtime: float | None = None) -> str:
    """고유하고 재현 가능한 문서 고유 ID를 생성합니다."""
    key = f"{source_path}:{mtime or ''}"
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
    date_str = dt.datetime.now().strftime("%Y%m%d")
    return f"doc_{date_str}_{h}"


def format_iso_now() -> str:
    """현재 시각을 ISO 8601 UTC(Z) 형식으로 반환합니다."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def split_frontmatter(content: str) -> tuple[dict[str, Any] | None, str]:
    """텍스트에서 YAML Front Matter와 순수 본문을 분리합니다."""
    if not content.startswith("---"):
        return None, content

    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not m:
        return None, content

    yaml_raw = m.group(1)
    body = m.group(2)
    try:
        data = yaml.safe_load(yaml_raw)
        if isinstance(data, dict):
            return data, body
    except Exception:
        pass
    return None, content


def build_frontmatter(
    *,
    doc_id: str,
    title: str,
    description: str = "",
    summary: str | None = None,
    source_file: str,
    source_path: str,
    source_rel_path: str | None = None,
    source_type: str,
    category: str | None = None,
    doc_category: str = "일반 지식 & 도구",
    doc_type: str = "document",
    conversion_method: str = "native",
    converted_from: str = "",
    output_file: str = "",
    language: str = "ko",
    created_at: str | None = None,
    updated_at: str | None = None,
    created_date: str | None = None,
    converted_date: str | None = None,
    topic: str | None = None,
    topics: list[str] | None = None,
    keywords: list[str] | None = None,
    tags: list[str] | None = None,
    entities: list[str] | None = None,
    related_documents: list[str] | None = None,
    aliases: list[str] | None = None,
    ocr_required: bool = False,
    ocr_confidence: str = "unknown",
    review_required: bool = False,
    status: str = "success",
    decision_status: str = "accepted",
    errors: list[str] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> str:
    """OKF_지식위키 규격과 파일형식변환기 스키마를 동시 충족하는 표준 Front Matter를 생성합니다."""
    now_iso = format_iso_now()
    c_time = created_at or now_iso
    u_time = updated_at or now_iso

    # 날짜 필드 정규화 (YYYY-MM-DD)
    c_date = created_date or c_time[:10]
    conv_date = converted_date or u_time[:10]

    # 요약 필드 통일 (summary / description)
    final_summary = (summary or description or "문서 내용 요약 정보가 없습니다.").strip()

    # 카테고리 필드 통일
    final_category = (category or doc_category or "일반 지식 & 도구").strip()

    # 태그 필드 통일
    final_tags = tags or keywords or topics or []
    # 중복 제거 및 슬러그 정규화 유지
    seen_tags = set()
    cleaned_tags = []
    for t in final_tags:
        t_clean = re.sub(r'[\s]+', '-', str(t).strip()).strip('-')
        if t_clean and t_clean.lower() not in seen_tags:
            seen_tags.add(t_clean.lower())
            cleaned_tags.append(t_clean)

    # 기본 토픽
    primary_topic = topic or (topics[0] if topics else (cleaned_tags[0] if cleaned_tags else ""))

    src_posix = Path(source_path).as_posix()

    lines = ["---"]
    # ── [1. OKF_지식위키 & Obsidian 핵심 표준 필드] ──
    lines.append(f'title: {json.dumps(title, ensure_ascii=False)}')
    lines.append(f'category: {json.dumps(final_category, ensure_ascii=False)}')
    lines.append(f'type: "{doc_type}"')
    if primary_topic:
        lines.append(f'topic: {json.dumps(primary_topic, ensure_ascii=False)}')
    lines.append(f'summary: {json.dumps(final_summary, ensure_ascii=False)}')
    lines.append(f'source: {json.dumps(source_file, ensure_ascii=False)}')
    lines.append(f'source_path: {json.dumps(src_posix, ensure_ascii=False)}')
    if source_rel_path:
        lines.append(f'source_rel_path: {json.dumps(Path(source_rel_path).as_posix(), ensure_ascii=False)}')
    lines.append(f'source_type: "{source_type}"')
    lines.append(f'created: {c_date}')
    lines.append(f'converted: {conv_date}')
    lines.append(f'status: "{status}"')
    lines.append(f'decision_status: "{decision_status}"')

    # tags 배열
    if cleaned_tags:
        lines.append('tags:')
        for t in cleaned_tags:
            lines.append(f'  - {t}')
    else:
        lines.append('tags: []')

    # aliases 배열
    if aliases:
        lines.append('aliases:')
        for a in aliases:
            lines.append(f'  - {json.dumps(a, ensure_ascii=False)}')
    else:
        lines.append('aliases: []')

    # ── [2. 시스템 연동 및 상세 스키마 필드 (하위 호환)] ──
    lines.append(f'id: "{doc_id}"')
    lines.append(f'description: {json.dumps(final_summary, ensure_ascii=False)}')
    lines.append(f'source_file: {json.dumps(source_file, ensure_ascii=False)}')
    lines.append(f'conversion_method: "{conversion_method}"')
    lines.append(f'converted_from: "{converted_from}"')
    lines.append(f'output_file: {json.dumps(output_file, ensure_ascii=False)}')
    lines.append(f'language: "{language}"')
    lines.append(f'created_at: "{c_time}"')
    lines.append(f'updated_at: "{u_time}"')
    lines.append(f'doc_category: {json.dumps(final_category, ensure_ascii=False)}')

    # topics (하위 호환)
    lines.append("topics:")
    if topics:
        for t in topics:
            lines.append(f"  - {json.dumps(t, ensure_ascii=False)}")
    elif cleaned_tags:
        for t in cleaned_tags[:3]:
            lines.append(f"  - {json.dumps(t, ensure_ascii=False)}")
    else:
        lines[-1] = "topics: []"

    # keywords (하위 호환)
    lines.append("keywords:")
    if keywords:
        for k in keywords:
            lines.append(f"  - {json.dumps(k, ensure_ascii=False)}")
    elif cleaned_tags:
        for t in cleaned_tags[:5]:
            lines.append(f"  - {json.dumps(t, ensure_ascii=False)}")
    else:
        lines[-1] = "keywords: []"

    # entities
    lines.append("entities:")
    if entities:
        for e in entities:
            lines.append(f"  - {json.dumps(e, ensure_ascii=False)}")
    else:
        lines[-1] = "entities: []"

    # related_documents
    lines.append("related_documents:")
    if related_documents:
        for r in related_documents:
            lines.append(f"  - {json.dumps(r, ensure_ascii=False)}")
    else:
        lines[-1] = "related_documents: []"

    lines.append(f'ocr_required: {"true" if ocr_required else "false"}')
    lines.append(f'ocr_confidence: "{ocr_confidence}"')
    lines.append(f'review_required: {"true" if review_required else "false"}')

    # errors
    lines.append("errors:")
    if errors:
        for err in errors:
            lines.append(f"  - {json.dumps(err, ensure_ascii=False)}")
    else:
        lines[-1] = "errors: []"

    # 추가 사용자 정의 필드
    if extra_fields:
        for k, v in extra_fields.items():
            if k not in ["id", "title", "source", "tags", "category", "summary"]:
                lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")

    lines.append("---\n")
    yaml_text = "\n".join(lines)

    # 무결성 검증 (오류 발생 시 예외)
    parsed = yaml.safe_load(yaml_text.replace("---", ""))
    assert parsed["id"] == doc_id, "YAML Front Matter 무결성 검증 실패: doc_id 불일치"
    assert "title" in parsed and "tags" in parsed and "source" in parsed, "OKF 필수 키 누락"

    return yaml_text
