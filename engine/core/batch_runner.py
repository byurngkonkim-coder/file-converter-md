# -*- coding: utf-8 -*-
"""core/batch_runner.py - 일괄 문서 변환 배치 엔진 및 결과 리포트 생성기.

- 드래그 앤 드롭 및 경로 정규화 (따옴표, 공백, 역슬래시 정리)
- 파일명 중복 충돌 방지 및 출처 기반 증분 관리 (unique_target_path)
- 오류 상태(password_protected, corrupted_file, unsupported_format 등) 상세 기록
- 변환 요약 보고서 (_conversion_report.json, _conversion_summary.md) 생성
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Callable

from adapters import get_adapter_for_path
from adapters.base import ConversionResult, ScannedDocumentSkipped
from core.com_session import ComSession
from core.config import DEFAULT_OUT_DIR, DEFAULT_REPORT_DIR, SUPPORTED_EXTENSIONS
from core.frontmatter_builder import (
    build_frontmatter,
    generate_doc_id,
    split_frontmatter,
)
from core.markdown_formatter import format_markdown_document
from core.metadata_extractor import (
    build_tags,
    detect_category,
    detect_language,
    extract_description,
    extract_entities,
    extract_summary,
    extract_title,
    is_english_content,
)
from core.text_postprocessor import postprocess_markdown, refine_plain_content

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


import unicodedata
from core.config import APP_DIR, DEFAULT_OUT_DIR, DEFAULT_REPORT_DIR, SUPPORTED_EXTENSIONS


def normalize_path(path_str: str) -> Path:
    """윈도우 경로 문자열의 따옴표, 공백, 역슬래시 및 유니코드를 정규화하여 절대경로 Path 객체로 반환합니다.

    - 유니코드 NFC 정규화로 맥/윈도우 간 한글 자모 분리 현상 방지
    - 윈도우 8.3 축약 경로(Short path) 및 심볼릭 링크 자동 해결
    """
    clean = path_str.strip(" \t\r\n'\"")
    # 연속된 역슬래시나 윈도우 따옴표 이스케이프 정리
    clean = clean.replace('\\"', '"').strip('"')
    clean = unicodedata.normalize("NFC", clean)
    abs_str = os.path.abspath(clean)
    try:
        real_str = os.path.realpath(abs_str)
        return Path(real_str)
    except Exception:
        return Path(abs_str)


def collect_files(inputs: list[str | Path], recursive: bool = True) -> list[Path]:
    """지정된 파일 또는 디렉토리 목록에서 지원하는 모든 문서 파일 목록을 수집합니다."""
    collected = []
    seen = set()

    for item in inputs:
        p = normalize_path(str(item)) if isinstance(item, str) else item.resolve()
        if not p.exists():
            continue

        if p.is_file():
            if p.suffix.lower() in SUPPORTED_EXTENSIONS:
                if p not in seen:
                    collected.append(p)
                    seen.add(p)
        elif p.is_dir():
            for root, dirs, files in os.walk(p):
                if not recursive and root != str(p):
                    continue
                # venv, 임시 폴더 등 제외
                dirs[:] = [d for d in dirs if d not in ("venv", "__pycache__", ".git", "output_md", "결과_MD", "변환리포트", "node_modules")]
                for f in files:
                    fp = Path(root) / f
                    if fp.suffix.lower() in SUPPORTED_EXTENSIONS:
                        if fp not in seen:
                            collected.append(fp)
                            seen.add(fp)

    return sorted(collected, key=lambda f: (f.suffix.lower(), f.name.lower()))


def compute_relative_path(src: Path) -> str | None:
    """파일이 애플리케이션 또는 USB 상위 경로 내에 위치할 경우 이동식 상대 경로를 산출합니다."""
    try:
        src_resolved = src.resolve()
        # 1. APP_DIR 기준 상대경로
        try:
            return src_resolved.relative_to(APP_DIR).as_posix()
        except ValueError:
            pass
        # 2. APP_DIR 상위 기준 상대경로 (동일 USB 루트 등)
        try:
            return src_resolved.relative_to(APP_DIR.parent).as_posix()
        except ValueError:
            pass
    except Exception:
        pass
    return None


def is_same_source(fm: dict | None, src: Path) -> bool:
    """프론트매터의 출처 정보와 대상 파일이 동일한지 판별합니다. (USB 드라이브 문자 변경 대응)"""
    if not fm:
        return False

    src_posix = src.resolve().as_posix()
    fm_src_path = str(fm.get("source_path", "")).replace("\\", "/")

    # 1. 절대경로 완전 일치
    if fm_src_path.lower() == src_posix.lower():
        return True

    # 2. 상대 경로 일치 (source_rel_path)
    fm_rel = fm.get("source_rel_path")
    if fm_rel:
        curr_rel = compute_relative_path(src)
        if curr_rel and curr_rel.lower() == str(fm_rel).lower():
            return True

    # 3. 드라이브 문자만 다른 동일 경로인지 검사 (USB 마운트 드라이브 D: -> E: 대응)
    def _strip_drive(p: str) -> str:
        p = unicodedata.normalize("NFC", p).strip()
        # Windows 드라이브 문자 (예: C:, D:, E:) 제거
        p_no_drive = re.sub(r"^[a-zA-Z]:", "", p)
        return p_no_drive.strip("/\\").replace("\\", "/").lower()

    if fm_src_path and _strip_drive(fm_src_path) == _strip_drive(src_posix):
        return True

    # 4. 파일명 일치
    fm_file = fm.get("source_file") or fm.get("source")
    if fm_file and str(fm_file).lower() == src.name.lower():
        # 파일명이 같고 드라이브를 뗀 부모 디렉토리명이 일치하는 경우
        if fm_src_path and Path(fm_src_path).parent.name.lower() == src.parent.name.lower():
            return True

    return False


def unique_target_path(out_dir: Path, src: Path) -> tuple[Path, bool]:
    """출력 디렉토리 내의 중복되지 않는 고유 Markdown 파일 경로 및 기변환 여부를 반환합니다. (USB 이동식 호환)"""
    out_dir.mkdir(parents=True, exist_ok=True)

    for n in range(1, 1000):
        dst = out_dir / (f"{src.stem}.md" if n == 1 else f"{src.stem} ({n}).md")
        if not dst.exists():
            return dst, False

        # 이미 존재하는 파일의 출처 확인 (USB 드라이브 문자 변경 대응)
        try:
            with open(dst, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(2048)
            fm, _ = split_frontmatter(head)
            if fm and is_same_source(fm, src):
                return dst, True
        except Exception:
            pass

    return out_dir / f"{src.stem}_{dt.datetime.now().strftime('%H%M%S')}.md", False


def convert_one_file(
    src: Path,
    out_dir: Path,
    session: ComSession | None = None,
    overwrite: bool = False,
    engine: str = "auto",
    skip_scanned: bool = False,
) -> tuple[str, Path, dict]:
    """단일 파일을 변환하여 (상태, 결과경로, 상세메타) 를 반환합니다."""
    ext = src.suffix.lower()
    adapter = get_adapter_for_path(str(src), engine=engine)

    if not adapter:
        raise ValueError(f"unsupported_format: 지원하지 않는 형식입니다 ({ext})")

    dst, already_done = unique_target_path(out_dir, src)
    if already_done and not overwrite:
        return "skip", dst, {"source": str(src), "target": str(dst), "reason": "이미 변환됨"}

    # 스캔/이미지 확장자 사전 제외 옵션
    if skip_scanned and SUPPORTED_EXTENSIONS.get(ext) == "image":
        return "skip", dst, {"source": str(src), "target": str(dst), "reason": "스캔/이미지 문서 제외 (OCR 생략)"}

    mtime = src.stat().st_mtime
    doc_id = generate_doc_id(str(src), mtime)
    rel_path = compute_relative_path(src)

    # 1. 어댑터를 통한 변환 수행
    try:
        import inspect
        sig = inspect.signature(adapter.convert)
        if "skip_scanned" in sig.parameters:
            res: ConversionResult = adapter.convert(src, session, skip_scanned=skip_scanned)
        else:
            res: ConversionResult = adapter.convert(src, session)
    except ScannedDocumentSkipped as e:
        return "skip", dst, {"source": str(src), "target": str(dst), "reason": str(e)}
    except Exception as e:
        err_msg = str(e)
        status = "failed"
        if "password" in err_msg.lower():
            status = "password_protected"
        elif "corrupt" in err_msg.lower() or "damage" in err_msg.lower():
            status = "corrupted_file"

        # 실패한 경우에도 프롬프트 사양에 따라 실패 상태 Markdown 파일 생성
        fm_fail = build_frontmatter(
            doc_id=doc_id,
            title=src.stem,
            description="변환 실패 문서",
            source_file=src.name,
            source_path=str(src),
            source_rel_path=rel_path,
            source_type=SUPPORTED_EXTENSIONS.get(ext, ext.lstrip(".")),
            conversion_method="none",
            converted_from=ext,
            output_file=dst.name,
            status=status,
            errors=[err_msg],
        )
        body_fail = f"# {src.stem}\n\n> [!CAUTION]\n> 변환 실패: {err_msg}\n"
        dst.write_text(fm_fail + "\n" + body_fail, encoding="utf-8")
        return status, dst, {"error": err_msg, "status": status}

    # 2. 본문 텍스트 1차 정제 및 가독성 교정 (단락 내 줄바꿈 복원, 어절 끊김 연결)
    res.body = refine_plain_content(res.body)

    # 3. 메타데이터 분석 및 추출 (OKF_지식위키 SSOT 규격 연동)
    combined_content = res.body + "\n" + res.tables
    title = extract_title(res.body, src.name)
    language = detect_language(combined_content)
    is_eng = is_english_content(path=str(src), text=combined_content, title=title)
    category = detect_category(combined_content, src.name, path=str(src))
    summary = extract_summary(res.body)
    tags = build_tags(combined_content, title=title, category=category, is_eng=is_eng, limit=10)
    entities = extract_entities(combined_content)
    doc_type = "english_learning" if is_eng else "document"

    # 4. YAML Front Matter 생성 (OKF_지식위키 및 파일형식변환기 통합 규격)
    source_type = SUPPORTED_EXTENSIONS.get(ext, ext.lstrip("."))
    frontmatter_text = build_frontmatter(
        doc_id=doc_id,
        title=title,
        description=summary,
        summary=summary,
        source_file=src.name,
        source_path=str(src),
        source_rel_path=rel_path,
        source_type=source_type,
        category=category,
        doc_category=category,
        doc_type=doc_type,
        conversion_method=res.conversion_method,
        converted_from=ext,
        output_file=dst.name,
        language=language,
        tags=tags,
        topics=tags[:3] if tags else ["일반"],
        keywords=tags[:5] if tags else ["문서"],
        entities=entities,
        ocr_required=res.ocr_required,
        ocr_confidence=res.ocr_confidence,
        review_required=res.review_required,
        status=res.status,
        errors=res.errors,
        extra_fields=res.extra_metadata,
    )

    # 5. Markdown 본문 조립
    markdown_body = format_markdown_document(
        title=title,
        source_file=src.name,
        source_path=str(src),
        doc_category=category,
        topics=tags[:3] if tags else ["일반"],
        description=summary,
        body_content=res.body,
        tables_content=res.tables,
        pages_content=res.pages,
        ocr_confidence=res.ocr_confidence,
        unrecognized_areas=res.unrecognized_areas,
        structural_damage_risk=res.structural_damage_risk,
        action_items=res.action_items,
        conversion_method=res.conversion_method,
    )

    # 6. 최종 마크다운 가독성 후처리 (마크다운 구조 보존형 정제) 및 파일 기록
    raw_output = frontmatter_text.rstrip() + "\n\n" + markdown_body
    final_output = postprocess_markdown(raw_output)
    dst.write_text(final_output, encoding="utf-8")

    meta_summary = {
        "id": doc_id,
        "title": title,
        "source": str(src),
        "target": str(dst),
        "status": res.status,
        "method": res.conversion_method,
        "ocr_confidence": res.ocr_confidence,
        "errors": res.errors,
    }
    return res.status, dst, meta_summary


def convert_batch(
    file_paths: list[Path],
    out_dir: Path | None = None,
    report_dir: Path | None = None,
    overwrite: bool = False,
    engine: str = "auto",
    skip_scanned: bool = False,
    progress_callback: Callable[[int, int, str, str], None] | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> dict:
    """파일 목록을 순회하며 일괄 변환을 수행하고, 별도의 리포트 폴더에 종합 보고서를 생성합니다."""
    out_dir = out_dir or DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    report_dir = report_dir or DEFAULT_REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)

    counts = {
        "total": len(file_paths),
        "success": 0,
        "partial": 0,
        "skip": 0,
        "failed": 0,
        "password_protected": 0,
        "corrupted_file": 0,
        "unsupported_format": 0,
    }
    details = []

    def log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    # COM 세션을 준비하여 배치 전체에서 공유
    with ComSession(auto_approve_hwp=True) as session:
        for idx, src in enumerate(file_paths, start=1):
            if progress_callback:
                progress_callback(idx, len(file_paths), src.name, "변환 중...")

            try:
                status, dst, meta = convert_one_file(
                    src,
                    out_dir,
                    session=session,
                    overwrite=overwrite,
                    engine=engine,
                    skip_scanned=skip_scanned,
                )
                if status in counts:
                    counts[status] += 1
                else:
                    counts["failed"] += 1
                details.append(meta)
                if status == "skip":
                    reason_msg = f" (사유: {meta.get('reason', '')})" if meta.get("reason") else ""
                    log(f"[{idx}/{len(file_paths)}] [SKIP] {src.name} -> {dst.name}{reason_msg}")
                else:
                    log(f"[{idx}/{len(file_paths)}] [{status.upper()}] {src.name} -> {dst.name}")
            except Exception as e:
                counts["failed"] += 1
                err_detail = {"source": str(src), "error": str(e), "status": "failed"}
                details.append(err_detail)
                log(f"[{idx}/{len(file_paths)}] [FAIL] {src.name}: {e}")

    # 변환 보고서 생성 (별도의 report_dir 에 저장)
    now_dt = dt.datetime.now()
    report_data = {
        "timestamp": now_dt.isoformat(),
        "output_directory": str(out_dir),
        "report_directory": str(report_dir),
        "counts": counts,
        "details": details,
    }

    ts_str = now_dt.strftime("%Y%m%d_%H%M%S")

    # 1. 최신 리포트 JSON 및 일시별 이력 JSON 저장
    report_json = report_dir / "_conversion_report.json"
    ts_report_json = report_dir / f"conversion_report_{ts_str}.json"
    for rj in (report_json, ts_report_json):
        with open(rj, "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

    # 2. 최신 요약 Markdown 및 일시별 이력 Markdown 저장
    summary_lines = [
        "# 문서 변환 일괄 처리 보고서\n",
        f"- 실행 일시: {report_data['timestamp']}",
        f"- 결과 마크다운 폴더: {report_data['output_directory']}",
        f"- 변환 리포트 폴더: {report_data['report_directory']}",
        f"- 전체 대상: {counts['total']} 건",
        f"- 성공: {counts['success']} 건, 부분성공/검토필요: {counts['partial']} 건, 건너뜀: {counts['skip']} 건, 실패: {counts['failed'] + counts['password_protected'] + counts['corrupted_file']} 건\n",
        "## 처리 결과 통계\n",
        "| 상태 | 건수 |",
        "|---|---|",
        f"| 성공 (Success) | {counts['success']} |",
        f"| 부분성공/검토필요 (Partial) | {counts['partial']} |",
        f"| 기존 건너뜀 (Skip) | {counts['skip']} |",
        f"| 암호 문서 (Password Protected) | {counts['password_protected']} |",
        f"| 손상 파일 (Corrupted File) | {counts['corrupted_file']} |",
        f"| 일반 실패 (Failed) | {counts['failed']} |",
        "\n## 상세 처리 내역\n",
        "| 원본 파일 | 변환 상태 | 결과 파일 | 비고 |",
        "|---|---|---|---|",
    ]
    for d in details:
        src_name = Path(d.get("source", "")).name
        st = d.get("status", "unknown")
        tgt_name = Path(d.get("target", "")).name if d.get("target") else "-"
        remark = d.get("error", "") or d.get("reason", "") or d.get("ocr_confidence", "")
        summary_lines.append(f"| {src_name} | {st} | {tgt_name} | {remark} |")

    report_md_content = "\n".join(summary_lines)
    report_md = report_dir / "_conversion_summary.md"
    ts_report_md = report_dir / f"conversion_summary_{ts_str}.md"
    report_md.write_text(report_md_content, encoding="utf-8")
    ts_report_md.write_text(report_md_content, encoding="utf-8")

    log(f"\n[완료] 총 {counts['total']}건 중 성공: {counts['success']}, 부분성공: {counts['partial']}, 건너뜀: {counts['skip']}, 실패: {counts['failed']}")
    log(f"[리포트 분리 저장] 결과MD: {out_dir.name}/ | 리포트: {report_dir.name}/{report_json.name}, {report_md.name}")

    return report_data

