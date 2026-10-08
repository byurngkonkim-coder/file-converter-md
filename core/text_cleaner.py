# -*- coding: utf-8 -*-
"""core/text_cleaner.py - 텍스트 정제, 마크다운 표 변환 및 HTML-to-MD 유틸리티."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Sequence

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def detect_encoding(raw: bytes) -> str:
    """바이트 열의 인코딩을 감지합니다."""
    # UTF-8 BOM
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    # UTF-16 LE BOM
    if raw.startswith(b"\xff\xfe"):
        return "utf-16-le"
    # UTF-16 BE BOM
    if raw.startswith(b"\xfe\xff"):
        return "utf-16-be"

    # 일반 UTF-8 시도
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    # charset_normalizer 사용 시도
    try:
        import charset_normalizer
        result = charset_normalizer.from_bytes(raw).best()
        if result and result.encoding:
            return result.encoding
    except Exception:
        pass

    # 한국어 환경 기본 fallback: cp949
    return "cp949"


def read_text(path: Path | str) -> str:
    """파일의 인코딩을 자동 감지하여 문자열로 읽어옵니다."""
    path = Path(path)
    raw = path.read_bytes()
    enc = detect_encoding(raw)
    try:
        return raw.decode(enc, errors="replace")
    except Exception:
        return raw.decode("utf-8", errors="replace")


def tidy(text: str) -> str:
    """연속 빈 줄과 불필요한 공백을 정리합니다. 코드 블록(```)은 원형을 보존합니다."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 코드 블록 보호 분할
    blocks = text.split("```")
    cleaned = []
    for i, blk in enumerate(blocks):
        if i % 2 == 1:
            # 홀수 번째는 코드 블록 안쪽: 원형 보존
            cleaned.append(blk)
        else:
            # 짝수 번째는 일반 본문: 후행 공백 제거 및 연속 3줄 이상 빈 줄 축소
            lines = [ln.rstrip() for ln in blk.split("\n")]
            part = "\n".join(lines)
            part = re.sub(r"\n{3,}", "\n\n", part)
            cleaned.append(part)
    return "```".join(cleaned).strip() + "\n"


def _clean_cell(val: Any) -> str:
    """표 셀 안의 줄바꿈과 파이프(|) 기호를 마크다운 표에 안전하게 변환합니다."""
    if val is None:
        return ""
    s = str(val).strip().replace("\r\n", " ").replace("\r", " ").replace("\n", "<br>")
    return s.replace("|", "\\|")


def rows_to_notepad_text(rows: Sequence[Sequence[Any]]) -> str:
    """표 데이터를 메모장에 붙여넣은 것처럼 표 테두리/선 서식을 없애고 순수 텍스트로 변환합니다."""
    lines = []
    for r in rows:
        if not r:
            continue
        cleaned_cells = []
        for c in r:
            if c is None:
                continue
            s = str(c).strip().replace("\r\n", " ").replace("\r", " ")
            s = re.sub(r"<br\s*/?>", " ", s)
            if s:
                cleaned_cells.append(s)
        if cleaned_cells:
            # 셀 사이는 공백과 탭으로 연결 (메모장 스타일)
            lines.append("  \t  ".join(cleaned_cells))
    return "\n".join(lines)


def rows_to_table(rows: Sequence[Sequence[Any]], force_grid: bool = False) -> str:
    """2차원 리스트 또는 튜플 데이터를 마크다운 표 또는 메모장 스타일 순수 텍스트로 변환합니다.

    셀 내에 긴 서술문(40자 이상)이나 줄바꿈이 많은 경우, 표 서식을 없애고 메모장 스타일 텍스트로 자동 전환합니다.
    """
    valid_rows = []
    max_cols = 0
    has_long_narrative = False

    for r in rows:
        if not r:
            continue
        cleaned = [_clean_cell(c) for c in r]
        if any(c for c in cleaned):
            valid_rows.append(cleaned)
            if len(cleaned) > max_cols:
                max_cols = len(cleaned)
            for c in cleaned:
                if len(c) > 40 or "<br>" in c:
                    has_long_narrative = True

    if not valid_rows or max_cols == 0:
        return ""

    # 서술문이나 기사 문장이 포함되어 있으면 표 서식을 걷어내고 메모장 스타일 텍스트로 변환
    if has_long_narrative and not force_grid:
        return rows_to_notepad_text(valid_rows)

    # 1열짜리 표도 표 서식 대신 텍스트로 변환
    if max_cols <= 1 and not force_grid:
        return rows_to_notepad_text(valid_rows)

    # 짧은 정형 데이터인 경우에만 마크다운 표로 변환
    padded = [r + [""] * (max_cols - len(r)) for r in valid_rows]
    headers = padded[0]
    if not any(headers):
        headers = [f"열 {i+1}" for i in range(max_cols)]
        padded.insert(0, headers)
    else:
        headers = [c if c else f"열 {i+1}" for i, c in enumerate(headers)]
        padded[0] = headers

    divider = ["---"] * max_cols
    lines = [
        "| " + " | ".join(padded[0]) + " |",
        "| " + " | ".join(divider) + " |",
    ]
    for r in padded[1:]:
        lines.append("| " + " | ".join(r) + " |")

    return "\n".join(lines)


def html_to_md(html: str) -> str:
    """HTML 문자열을 깔끔한 Markdown 문자열로 변환합니다."""
    import markdownify

    md = markdownify.markdownify(
        html,
        heading_style="ATX",
        bullets="-",
        strip=["script", "style"],
    )
    return tidy(md)


def unwrap_layout_tables(md_text: str) -> str:
    """마크다운 본문에서 본문 단락이 표(| ... |) 셀 안에 갇히거나

    중첩 표(| | | --- |)로 깨진 레이아웃 표를 감지하여 순수 단락으로 복원합니다.
    진짜 데이터 표는 안전하게 보존합니다.
    """
    lines = md_text.split("\n")
    out = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # 표 시작 라인 판별
        if stripped.startswith("|") and stripped.endswith("|"):
            tbl_lines = [line]
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("|") and lines[j].strip().endswith("|"):
                tbl_lines.append(lines[j])
                j += 1

            # 레이아웃 표 또는 손상된 중첩 표인지 판별
            is_layout = False

            # 1. 비정상적 길이 (>250자) 또는 중첩 표 파이프 흔적
            for tl in tbl_lines:
                if len(tl) > 250:
                    is_layout = True
                    break
                # 셀 안에 중첩 구분선 흔적
                if tl.count("---") > 0 and tl.count("|") > 12:
                    is_layout = True
                    break
                # 셀 안에 <br> 태그 다수
                if ("<br>" in tl or "<br/>" in tl or "<br />" in tl) and len(tl) > 120:
                    is_layout = True
                    break

            # 2. 셀 내용 중 긴 문장(60자 이상)이 포함된 경우
            if not is_layout:
                for tl in tbl_lines:
                    cells = [c.strip() for c in tl.split("|") if c.strip() and not re.match(r"^:?-+:?$", c.strip())]
                    if any(len(c) > 60 for c in cells):
                        is_layout = True
                        break

            if is_layout:
                # 레이아웃 표 해제 (Unwrap): 메모장에 붙여넣은 것처럼 서식을 없애고 텍스트 단락으로 복원
                unwrapped_paras = []
                for tl in tbl_lines:
                    cells = [c.strip() for c in tl.split("|") if c.strip()]
                    # 구분선 행(| --- | --- |) 건너뜀
                    if all(re.match(r"^:?-+:?$", c) for c in cells):
                        continue

                    for cell in cells:
                        if re.match(r"^:?-+:?$", cell):
                            continue
                        # HTML br 태그를 줄바꿈으로 변환
                        cell_clean = re.sub(r"<br\s*/?>", "\n", cell)
                        cell_clean = cell_clean.replace("\\|", "|")
                        cell_paras = [p.strip() for p in cell_clean.split("\n") if p.strip()]
                        for cp in cell_paras:
                            if cp:
                                unwrapped_paras.append(cp)

                out.extend(unwrapped_paras)
                out.append("")
                i = j
                continue
            else:
                out.extend(tbl_lines)
                i = j
                continue
        else:
            out.append(line)
            i += 1

    return "\n".join(out)

