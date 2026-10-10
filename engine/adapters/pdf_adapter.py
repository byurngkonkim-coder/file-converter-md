# -*- coding: utf-8 -*-
"""adapters/pdf_adapter.py - PDF 문서 변환 어댑터.

- PyMuPDF (fitz) 기반 스마트 레이아웃 분석:
  * 수평 밴드(Horizontal Band) 및 다단(2단/3단 Column) 자동 감지/정렬
  * 머리글/바닥글/워터마크 노이즈 제거 (DBR, 잡지, 학술논문 등)
  * 표(find_tables) 추출 및 메모장 스타일 서식 평탄화
  * 불필요한 줄바꿈 제거 및 자연스러운 단락 복원
- 암호 걸린 PDF (doc.needs_pass) 감지 및 예외 처리
- 텍스트 레이어가 없는 스캔 PDF 인 경우 고해상도 렌더링 후 OCR 자동 수행 (Fallback)
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from adapters.base import BaseAdapter, ConversionResult, ScannedDocumentSkipped
from adapters.ocr_adapter import OcrAdapter
from core.text_cleaner import rows_to_table, tidy
from core.text_postprocessor import postprocess_markdown, rejoin_page_boundary_paragraphs
from core.korean_spacing_corrector import refine_korean_text

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def is_header_footer_noise(text: str, y0: float, y1: float, page_h: float) -> bool:
    """잡지/논문 머리글, 바닥글, 다운로드 워터마크 노이즈 여부 판정."""
    t = text.strip()
    if not t:
        return True

    # 1. 다운로드 워터마크 (위치 무관)
    if "Downloaded by" in t or "(PREMIUM)" in t:
        return True

    # 2. 극단적인 상단 머리글 (y0 < 55)
    if y0 < 55:
        if len(t) < 80 and (
            any(kw in t for kw in ["Dong-A Business Review", "Special Report", "DBR", "www.dongabiz.com"])
            or re.match(r"^\d{1,4}(\s+.*)?$", t)
            or len(t) <= 4
        ):
            return True

    # 3. 극단적인 하단 바닥글 (y1 > page_h - 115, 즉 A4 기준 약 725 이상)
    if y1 > (page_h - 115):
        if len(t) < 80 and (
            any(kw in t for kw in ["Dong-A Business Review", "DBR", "www.dongabiz.com"])
            or re.match(r"^\d{1,4}$", t)
            or "No." in t
        ):
            return True

    return False


# 블록 잇기 기준 — 앞 블록의 마지막 줄이 단에서 흔한 줄 길이(중앙값)의 이만큼 이상 찼을 때만 다음 블록과 잇는다.
# 실측(2026-10-10, 결과_MD 표본 25권): 세로 간격만 보고 이어 붙여 짧은 줄로 끝나는 색인·차례 항목, 표 칸,
# 그림 라벨, 도서 광고('양장/12.000원'), 제목('Lead the Field')이 다음 본문에 붙었다. MyOCR text_refiner 와 같은 비율
_FULL_LINE_RATIO = 0.75
# 단어 첫머리에 올 수 없는 어미·조사 — 다음 블록이 이걸로 시작하면 앞 줄이 짧아도 한 단어가 잘린 것이라 잇는다
# (좁은 단: '…우월적 지위' ⟨블록 경계⟩ '를 확보했다'). '이·가·서·만·도' 는 독립 단어로도 쓰여 제외
_BOUND_START = {"며", "으며", "니", "으니", "니까", "지만", "면서", "도록", "거나", "는데", "은데", "으면",
                "는", "은", "을", "를", "에", "의", "에서", "에게", "으로", "로", "께서",
                "었다", "았다", "였다", "했다", "한다", "된다", "합니다", "입니다", "습니다", "니다"}


# 색인 항목: 낱말 뒤에 쪽번호(들)로 끝나는 줄 — 'teams, 141, 157-158'·'프레더릭 테일러 518, 627'
_INDEX_ENTRY_RE = re.compile(r"[가-힣A-Za-z)]\s*,?\s+\d{1,4}(?:[-–~]\d{1,4})?(?:\s*,\s*\d{1,4}(?:[-–~]\d{1,4})?)*\s*$")


def _starts_bound(text: str) -> bool:
    m = re.match(r"[가-힣]+", text.strip())
    return bool(m) and m.group(0) in _BOUND_START


def group_column_blocks_into_paragraphs(col_blocks: list[dict]) -> list[str]:
    """컬럼 내 연속된 줄(Line) 블록들을 자연스러운 단락(Paragraph)으로 병합."""
    if not col_blocks:
        return []

    lens = sorted(len(l.strip()) for b in col_blocks if not b.get("is_table")
                  for l in b["text"].splitlines() if l.strip())
    full = lens[len(lens) // 2] * _FULL_LINE_RATIO if lens else 0

    paragraphs = []
    curr_lines = []
    prev_b = None

    for b in col_blocks:
        if b.get("is_table", False):
            if curr_lines:
                paragraphs.append(" ".join(curr_lines))
                curr_lines = []
            paragraphs.append(b["text"])
            prev_b = None
            continue

        btext = b["text"].strip()
        if not btext:
            continue

        if prev_b is None:
            curr_lines.append(btext)
            prev_b = b
            continue

        y_gap = b["y0"] - prev_b["y1"]
        prev_text = prev_b["text"].strip()

        # 새 단락 시작 조건
        is_bullet = btext.startswith(("-", "•", "▶", "※", "*", "①", "②", "③", "1.", "2.", "3.", "4.", "5."))
        prev_ended = any(prev_text.endswith(ch) for ch in (".", "!", "?", "…", ":"))

        prev_last = prev_text.splitlines()[-1].strip()
        bound = re.search(r"[가-힣]$", prev_last) is not None and _starts_bound(btext)
        short_end = len(prev_last) < full and not bound   # 짧은 줄로 끝남 = 제목·항목·표 칸·라벨
        # 앞 문단이 끝났는데(마침표 등) 이 블록이 문장부호 없이 끝나는 짧은 한 줄 = 제목·항목 — 간격이 좁아도 떼어 둔다.
        # 앞 문단이 안 끝났으면 떼지 않는다: 문단 마지막 줄이 OCR 로 마침표를 잃은 경우('…사람들이 잘' ‖ '이해하지 못한다')
        short_label = (prev_ended and "\n" not in btext and len(btext) < full and not bound
                       and not any(btext.endswith(ch) for ch in (".", "!", "?", "…", ":", "”", "\"")))

        # 색인 항목끼리('teams, 141, 157-158' ‖ 'Ten Goal Exercise, 68, 180') — 단 전체가 짧아 길이로는 못 가른다
        index_pair = bool(_INDEX_ENTRY_RE.search(prev_last) and _INDEX_ENTRY_RE.search(btext.splitlines()[0]))

        if is_bullet or (prev_ended and y_gap > 8) or y_gap > 16 or short_end or short_label or index_pair:
            paragraphs.append(" ".join(curr_lines))
            curr_lines = [btext]
        elif bound:   # 끊긴 어미·조사 — 한 단어가 잘린 것이니 공백 없이 잇는다
            curr_lines[-1] = curr_lines[-1].rstrip() + btext
        else:
            curr_lines.append(btext)

        prev_b = b

    if curr_lines:
        paragraphs.append(" ".join(curr_lines))

    return paragraphs


def sort_band_blocks(blocks: list[dict], page_w: float) -> list[str]:
    """하나의 수평 밴드 내에서 텍스트 블록들을 올바른 독서 순서(다단 인식)로 정렬."""
    if not blocks:
        return []
    if len(blocks) == 1:
        return [blocks[0]["text"]]

    min_x = min(b["x0"] for b in blocks)
    max_x = max(b["x1"] for b in blocks)
    span_w = max_x - min_x

    # 너비가 밴드 전체 폭의 60% 이상인 전폭 블록 분리
    full_blocks = [b for b in blocks if b["w"] > span_w * 0.60]
    col_blocks = [b for b in blocks if b["w"] <= span_w * 0.60]

    # 거터(Gutter, 공백 구간) 찾기
    gutters = []
    if len(col_blocks) >= 2:
        hist_len = int(span_w) + 10
        coverage = [0] * hist_len
        for b in col_blocks:
            s = max(0, int(b["x0"] - min_x))
            e = min(hist_len, int(b["x1"] - min_x))
            for x in range(s, e):
                coverage[x] += 1

        start_x = int(span_w * 0.12)
        end_x = int(span_w * 0.88)
        in_gap = False
        gap_start = 0
        for x in range(start_x, end_x):
            if coverage[x] == 0:
                if not in_gap:
                    in_gap = True
                    gap_start = x
            else:
                if in_gap:
                    in_gap = False
                    if (x - gap_start) >= 6:  # 6pt 이상 공백이면 컬럼 거터로 판정
                        gutters.append(min_x + (gap_start + x) / 2.0)
        if in_gap and (end_x - gap_start) >= 6:
            gutters.append(min_x + (gap_start + end_x) / 2.0)

    # 거터가 없으면: 일반 Y축(위->아래) 정렬 후 단락 병합
    if not gutters:
        sorted_all = sorted(blocks, key=lambda b: (b["y0"], b["x0"]))
        return group_column_blocks_into_paragraphs(sorted_all)

    # 거터가 있으면: 다단 컬럼 분할
    num_cols = len(gutters) + 1
    cols = [[] for _ in range(num_cols)]

    for b in col_blocks:
        assigned = False
        for c_idx, g_x in enumerate(gutters):
            if b["cx"] < g_x:
                cols[c_idx].append(b)
                assigned = True
                break
        if not assigned:
            cols[-1].append(b)

    top_full = []
    bot_full = []
    if full_blocks:
        min_col_y = min((min(b["y0"] for b in c) for c in cols if c), default=0)
        for b in full_blocks:
            if b["y1"] <= min_col_y + 15:
                top_full.append(b)
            else:
                bot_full.append(b)
        top_full.sort(key=lambda b: b["y0"])
        bot_full.sort(key=lambda b: b["y0"])

    res = []
    for b in top_full:
        res.append(b["text"])

    for c in cols:
        c.sort(key=lambda b: b["y0"])
        col_paras = group_column_blocks_into_paragraphs(c)
        res.extend(col_paras)

    for b in bot_full:
        res.append(b["text"])

    return res


def extract_pdf_page(page: Any) -> str:
    """PDF 한 페이지에서 표와 다단 텍스트를 최적의 독서 순서로 추출."""
    page_w = page.rect.width
    page_h = page.rect.height

    tab_rects = []
    page_elements = []
    # 글자 대응표가 깨진 글꼴(DBR 표·제목 등)의 줄은 이미지로 다시 읽어 고친다 — 표 칸·본문 블록 모두
    from core.garbled_font import page_fixer
    fix, _ = page_fixer(page)

    # 1. 표(find_tables) 감지 및 메모장 서식 평탄화
    try:
        tabs = page.find_tables()
        for tab in tabs:
            tab_rects.append(tab.bbox)
            grid = tab.extract()
            if grid:
                grid = [[fix(c) if isinstance(c, str) else c for c in row] for row in grid]
                t_str = rows_to_table(grid)
                if t_str:
                    bx0, by0, bx1, by1 = tab.bbox
                    page_elements.append({
                        "x0": bx0,
                        "y0": by0,
                        "x1": bx1,
                        "y1": by1,
                        "cx": (bx0 + bx1) / 2.0,
                        "cy": (by0 + by1) / 2.0,
                        "w": bx1 - bx0,
                        "h": by1 - by0,
                        "text": t_str,
                        "is_table": True,
                    })
    except Exception:
        tab_rects = []

    # 2. 일반 텍스트 블록 수집
    raw_blocks = page.get_text("blocks")
    for b in raw_blocks:
        if len(b) >= 7 and b[6] == 1:
            continue  # 이미지 제외
        bx0, by0, bx1, by1, btext = b[0], b[1], b[2], b[3], fix(b[4]).strip()
        if not btext:
            continue
        if is_header_footer_noise(btext, by0, by1, page_h):
            continue

        # 표 영역과 겹치는지 체크 (중심점 기준)
        bcx = (bx0 + bx1) / 2.0
        bcy = (by0 + by1) / 2.0
        in_tab = False
        for tr in tab_rects:
            if tr[0] - 5 <= bcx <= tr[2] + 5 and tr[1] - 5 <= bcy <= tr[3] + 5:
                in_tab = True
                break
        if in_tab:
            continue

        page_elements.append({
            "x0": bx0,
            "y0": by0,
            "x1": bx1,
            "y1": by1,
            "cx": bcx,
            "cy": bcy,
            "w": bx1 - bx0,
            "h": by1 - by0,
            "text": btext,
            "is_table": False,
        })

    if not page_elements:
        return ""

    min_x = min(e["x0"] for e in page_elements)
    max_x = max(e["x1"] for e in page_elements)
    content_w = max_x - min_x

    # 3. 수평 밴드 분할 (전폭 블록 기준)
    cut_ys = []
    for e in page_elements:
        if e["w"] > content_w * 0.55:
            cut_ys.append(e["y0"] - 2)
            cut_ys.append(e["y1"] + 2)

    cut_ys = sorted(list(set(cut_ys)))
    cleaned_cuts = []
    for cy in cut_ys:
        if cy <= 60 or cy >= (page_h - 120):
            continue
        if not cleaned_cuts or (cy - cleaned_cuts[-1]) >= 20:
            cleaned_cuts.append(cy)

    bands = []
    prev_y = 0.0
    for cy in cleaned_cuts:
        band_b = [e for e in page_elements if prev_y <= e["cy"] < cy]
        if band_b:
            bands.append(band_b)
        prev_y = cy
    last_band = [e for e in page_elements if e["cy"] >= prev_y]
    if last_band:
        bands.append(last_band)

    # 4. 각 밴드별 다단 정렬 및 결합
    all_texts = []
    for band in bands:
        all_texts.extend(sort_band_blocks(band, page_w))

    return "\n\n".join(all_texts)


def reconstruct_ocr_page(lines: list[dict], img_w: float, img_h: float) -> str:
    """OCR 인식 라인들과 바운딩 박스를 분석하여 스캔 도서 레이아웃을 고품질 단락으로 재구성."""
    from core.text_postprocessor import (
        clean_ocr_artifacts,
        fix_english_confusion,
        fix_hyphenated_words,
        fix_punctuation_spacing,
        join_split_particles,
        normalize_unicode_and_invisible,
        remove_noise_lines,
        strip_scan_margin_noise,
    )

    if not lines:
        return ""

    valid_lines = []
    for l in lines:
        txt = l.get("text", "").strip()
        if not txt:
            continue
        box = l.get("box", [0, 0, 0, 0])
        # 스캔 마진 잡음 1차 정제
        txt_clean = strip_scan_margin_noise(txt)
        if not txt_clean:
            continue
        meaningful = re.sub(r"[^\w가-힣]", "", txt_clean)
        if len(meaningful) < 1:
            continue

        # 상단/하단 여백(상위 12%, 하위 10%)의 러닝헤더/러닝푸터 및 쪽번호 필터링
        y0, y1 = box[1], box[3]
        if y0 < img_h * 0.12 or y1 > img_h * 0.90:
            # 1. 단독 쪽번호나 짧은 기호
            if txt_clean.isdigit() or len(meaningful) <= 2:
                continue
            # 2. "20 분석의 힘" 또는 "PART 1 ... 19" 같은 러닝헤더/푸터 패턴
            if re.search(r"^\d{1,4}\s+[\w가-힣\s]{2,20}$", txt_clean) or re.search(r"^[\w가-힣\s]{2,30}\s*\d{1,4}$", txt_clean):
                continue

        valid_lines.append({
            "text": txt_clean,
            "score": l.get("score", 0.0),
            "box": box,
            "x0": box[0], "y0": box[1], "x1": box[2], "y1": box[3],
            "cx": (box[0] + box[2]) / 2.0,
            "cy": (box[1] + box[3]) / 2.0,
            "w": box[2] - box[0],
            "h": box[3] - box[1],
        })

    if not valid_lines:
        return ""

    # Y좌표 기준 정렬
    valid_lines.sort(key=lambda item: (item["y0"], item["x0"]))

    # 같은 행에 있는 텍스트(예: 목차 제목과 우측 쪽번호) 가로 병합
    rows = []
    curr_row = []
    for item in valid_lines:
        if not curr_row:
            curr_row.append(item)
        else:
            avg_h = sum(x["h"] for x in curr_row) / len(curr_row)
            if abs(item["cy"] - curr_row[0]["cy"]) < max(12, avg_h * 0.5):
                curr_row.append(item)
            else:
                rows.append(curr_row)
                curr_row = [item]
    if curr_row:
        rows.append(curr_row)

    row_strings = []
    for row in rows:
        row.sort(key=lambda x: x["x0"])
        row_text = " ".join(x["text"] for x in row)
        row_strings.append({
            "text": row_text,
            "y0": min(x["y0"] for x in row),
            "y1": max(x["y1"] for x in row),
            "h": max(x["h"] for x in row),
        })

    # 줄 간격(y-gap) 분석을 통한 단락 그룹화
    paragraphs = []
    curr_p = []
    prev_row = None

    for r in row_strings:
        rtxt = r["text"].strip()
        if not rtxt:
            continue

        if prev_row is None:
            curr_p.append(rtxt)
            prev_row = r
            continue

        y_gap = r["y0"] - prev_row["y1"]
        prev_txt = prev_row["text"].strip()

        # 새 단락 시작 판별
        is_heading = bool(re.match(r"^(?:PART|CHAPTER|SECTION|제\s*\d+\s*[장절편]|부록|감사의\s*글|\d+[.．]\s|\||\[|\#)", rtxt, re.IGNORECASE))
        prev_is_short = len(prev_txt) < 14 and not any(prev_txt.endswith(ch) for ch in (",", "와", "과", "및", "등"))
        prev_ended = any(prev_txt.endswith(ch) for ch in (".", "!", "?", "…", ":", ";"))

        if is_heading or prev_is_short or (prev_ended and y_gap > r["h"] * 0.6) or (y_gap > r["h"] * 1.5):
            paragraphs.append(" ".join(curr_p))
            curr_p = [rtxt]
        else:
            curr_p.append(rtxt)

        prev_row = r

    if curr_p:
        paragraphs.append(" ".join(curr_p))

    raw_page_text = "\n\n".join(paragraphs)
    # 정제 규칙 파이프라인
    cleaned_page = normalize_unicode_and_invisible(raw_page_text)
    cleaned_page = fix_english_confusion(cleaned_page)
    cleaned_page = fix_hyphenated_words(cleaned_page)
    cleaned_page = clean_ocr_artifacts(cleaned_page)
    cleaned_page = remove_noise_lines(cleaned_page)
    cleaned_page = join_split_particles(cleaned_page)
    cleaned_page = refine_korean_text(cleaned_page)
    cleaned_page = fix_punctuation_spacing(cleaned_page)

    return cleaned_page


class PdfAdapter(BaseAdapter):
    """PDF 문서 변환기."""

    def can_handle(self, ext: str) -> bool:
        return ext.lower() == ".pdf"

    def convert(self, path: Path, session: Any = None, skip_scanned: bool = False, **kwargs) -> ConversionResult:
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz

        abs_path = str(path.resolve())
        doc = fitz.open(abs_path)

        if doc.needs_pass:
            doc.close()
            raise RuntimeError("password_protected: 암호가 걸린 PDF 문서입니다.")

        pages_extracted = []
        total_chars = 0

        try:
            for p_num, page in enumerate(doc, start=1):
                p_text = extract_pdf_page(page)
                total_chars += len(p_text)
                pages_extracted.append((p_num, p_text))

            page_count = len(doc)
            # 페이지당 평균 글자 수가 20자 미만이면 스캔 PDF로 간주하고 OCR 수행
            is_scan = (total_chars / max(1, page_count)) < 20

            if is_scan and skip_scanned:
                raise ScannedDocumentSkipped(
                    f"텍스트 레이어가 없는 스캔 PDF (글자 수: {total_chars}자, {page_count}페이지) - 변환 제외"
                )

            if not is_scan and total_chars > 0:
                # 텍스트 레이어 정상 추출 완료: 페이지 마커 없이 문맥 연속 결합
                merged_body_parts = []
                for p_num, p_text in pages_extracted:
                    p_text_clean = p_text.strip()
                    if not p_text_clean:
                        continue
                    if not merged_body_parts:
                        merged_body_parts.append(p_text_clean)
                    else:
                        prev = merged_body_parts[-1].rstrip()
                        if any(prev.endswith(ch) for ch in (".", "!", "?", "…", ":", ";")):
                            merged_body_parts.append("\n\n" + p_text_clean)
                        else:
                            merged_body_parts.append(" " + p_text_clean)

                body = "".join(merged_body_parts)
                final_body = postprocess_markdown(tidy(body))

                return ConversionResult(
                    body=final_body,
                    tables="",
                    pages=pages_extracted,
                    conversion_method="native",
                    ocr_required=False,
                    ocr_confidence="unknown",
                    review_required=False,
                    status="success",
                )

            # --- 스캔 PDF 처리: 고해상도 이미지 렌더링 후 OCR 실행 ---
            ocr_adapter = OcrAdapter()
            tmp_img_paths = []
            page_dims = []
            tmp_dir = Path(tempfile.mkdtemp(prefix="pdf_ocr_"))

            try:
                for p_num, page in enumerate(doc, start=1):
                    # 2.5배율 렌더링 (약 180 DPI)으로 한글 받침 및 세밀한 텍스트 인식률 향상
                    mat = fitz.Matrix(2.5, 2.5)
                    pix = page.get_pixmap(matrix=mat)
                    img_file = tmp_dir / f"page_{p_num:03d}.png"
                    pix.save(str(img_file))
                    tmp_img_paths.append(img_file)
                    page_dims.append((pix.width, pix.height))

                ocr_results = ocr_adapter.perform_ocr_batch(tmp_img_paths, lang="korean")

                ocr_pages = []
                merged_ocr_parts = []
                avg_scores = []

                for p_num, (res, (pw, ph)) in enumerate(zip(ocr_results, page_dims), start=1):
                    lines = res.get("lines", [])
                    if lines:
                        p_txt = reconstruct_ocr_page(lines, pw, ph)
                    else:
                        p_txt = res.get("text", "").strip()

                    p_txt = p_txt.strip()
                    ocr_pages.append((p_num, p_txt))
                    if p_txt:
                        if not merged_ocr_parts:
                            merged_ocr_parts.append(p_txt)
                        else:
                            # D-13 규칙 기반 페이지 경계 단락 재결합 (문장 완결 시 \n\n, 미완결 시 부드러운 연결)
                            prev_ocr = merged_ocr_parts[-1].rstrip()
                            if prev_ocr.endswith("-"):
                                merged_ocr_parts[-1] = prev_ocr[:-1] + p_txt
                            else:
                                merged_ocr_parts[-1] = rejoin_page_boundary_paragraphs(prev_ocr, p_txt)

                    if "avg_score" in res:
                        avg_scores.append(res["avg_score"])

                ocr_body = "\n\n".join(merged_ocr_parts)
                final_ocr_body = postprocess_markdown(tidy(ocr_body))

                mean_score = sum(avg_scores) / len(avg_scores) if avg_scores else 0.0
                conf = "high" if mean_score >= 0.85 else ("medium" if mean_score >= 0.65 else "low")
                if not avg_scores:
                    conf = "unknown"

                review_req = conf in ("low", "unknown") or mean_score < 0.7

                return ConversionResult(
                    body=final_ocr_body,
                    tables="",
                    pages=ocr_pages,
                    conversion_method="ocr",
                    ocr_required=True,
                    ocr_confidence=conf,
                    review_required=review_req,
                    status="partial" if review_req else "success",
                    unrecognized_areas="스캔 이미지 인식 저품질 페이지 확인 필요" if review_req else "없음",
                    action_items="OCR 결과 원본 대조 검토" if review_req else "없음",
                )
            finally:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)

        finally:
            if hasattr(doc, "is_closed"):
                if not doc.is_closed:
                    doc.close()
            else:
                try:
                    doc.close()
                except Exception:
                    pass
