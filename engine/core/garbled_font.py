# -*- coding: utf-8 -*-
"""core/garbled_font.py - 글자 대응표가 깨진 글꼴의 줄만 이미지로 다시 읽어 복원.

실측(2026-10-10): DBR 잡지 PDF 의 표·제목·캡션 글꼴(DongA3G)이 텍스트 레이어에 한글 일부를
구르무키·말라얄람·아랍·키릴 확장 문자로, 영문을 밀린 글자('TVA'→'57A')로 담고 있어
표 칸이 '전통੶ 회계'·'포인트\\x10ഊఔ' 처럼 깨진 채 변환됐다. 깨진 곳이 쪽마다 몇 줄뿐이라
쪽 전체를 OCR 하면 멀쩡한 본문까지 인식 오류를 떠안는다.
→ 그런 글자가 든 줄만 이미지로 다시 읽고, 원문과 글자 정렬해 깨진 구간만 바꾼다.
오탐 실측(01_입력 98권 33,682쪽): 걸린 쪽 40 — 38쪽은 같은 DBR 글꼴, 2쪽은 기호 글꼴·제어문자.
01_OCR_스캔파일텍스트추출프로그램 engine/core/pdf_text_layer.py 의 같은 복원을 이식했다.
"""
from __future__ import annotations

import difflib
import re
from typing import Any, Callable

# 한글 책에 나올 리 없는 문자: 제어문자, 키릴 확장(U+0460~ — 현대 러시아어 U+0400~045F 는 제외),
# 아르메니아·히브리·아랍·시리아·타나·NKo·사마리아, 인도계 문자, 사용자 정의 영역
_FOREIGN_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1fѠ-ࣿऀ-෿-]")
_ALNUM_RE = re.compile(r"[A-Za-z0-9]")
_WS_RE = re.compile(r"\s+")
# (배율, 흰 여백 px) — 같은 줄도 이미지 조건에 따라 OCR 이 다르게 읽어, 둘 다 읽고 원문과 더 맞는 쪽을 쓴다
_REOCR_VARIANTS = ((3, 6), (2, 0))
_REOCR_MIN_AGREEMENT = 0.5    # 원문의 멀쩡한 글자 중 OCR 과 정렬되는 비율이 이보다 낮으면 OCR 을 믿지 않는다

_ENGINE = None


def has_foreign_glyphs(text: str) -> bool:
    """한글 책에 나올 리 없는 문자(제어문자·인도계·아랍 문자 등)가 있으면 True — 깨진 글꼴의 흔적."""
    return bool(_FOREIGN_RE.search(text or ""))


def _trust_chars(s: str) -> str:
    """원문에서 믿을 만한 글자만 — 깨진 문자·영문·숫자(깨진 글꼴에선 밀려 있다)·공백 제외."""
    return _WS_RE.sub("", _FOREIGN_RE.sub("", _ALNUM_RE.sub("", s)))


def _agreement(orig: str, ocr: str) -> float | None:
    """원문의 믿을 만한 글자 중 OCR 과 정렬되는 비율. 그런 글자가 없으면 None."""
    clean = _trust_chars(orig)
    if not clean:
        return None
    sm = difflib.SequenceMatcher(None, orig, ocr, autojunk=False)
    return sum(len(_trust_chars(orig[i:i + n])) for i, _, n in sm.get_matching_blocks()) / len(clean)


def merge_reocr(orig: str, ocr: str) -> tuple[str, bool]:
    """원문 줄과 OCR 결과를 글자 정렬해 깨진 글자·영문·숫자 구간만 OCR 로 바꾼다. (결과, OCR 을 믿었나).
    OCR 을 믿지 못하면 원문에서 깨진 문자만 지운다."""
    glyphs = len(_WS_RE.sub("", orig))
    if len(_trust_chars(orig)) < 4:      # 맞춰 볼 글자가 거의 없는 짧은 줄 — 길이가 그럴듯하면 믿는다
        ok = bool(ocr) and (not glyphs or 0.5 <= len(_WS_RE.sub("", ocr)) / glyphs <= 2)
    else:
        ag = _agreement(orig, ocr)
        ok = ag is not None and ag >= _REOCR_MIN_AGREEMENT
    if not ok:
        return _FOREIGN_RE.sub("", orig), False
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, orig, ocr, autojunk=False).get_opcodes():
        a, b = orig[i1:i2], ocr[j1:j2]
        if op == "equal":
            out.append(a)
        elif _FOREIGN_RE.search(a) or _ALNUM_RE.search(a):
            out.append(b)                    # 깨진 구간 → OCR
        elif op == "insert":                 # OCR 에만 있는 글자 — 깨진 글자 옆일 때만 받는다
            out.append(b if b.strip() and _FOREIGN_RE.search(orig[max(0, i1 - 1):i1 + 1]) else "")
        else:
            out.append(a)                    # 멀쩡한 원문 유지 (OCR 이 빠뜨리거나 다르게 읽은 곳)
    return "".join(out), True


def build_fixer(lines, ocr_line: Callable[[Any, str], str]) -> tuple[Callable[[str], str], int]:
    """깨진 줄(lines: [(원문 줄, 위치)])을 ocr_line(위치, 원문)으로 다시 읽어 '원문 줄 → 고친 줄' 대응을 만든다.
    반환: (텍스트에 대응을 적용하고 남은 깨진 문자를 지우는 함수, OCR 을 믿고 고친 줄 수).
    표 칸·본문 블록처럼 같은 줄이 다른 모양으로 들어간 곳에 각각 적용할 수 있다."""
    fixes: dict[str, str] = {}
    fixed = 0
    for orig, rect in lines:
        # 앞뒤 공백은 떼고 맞춘다 — PDF 줄 정보엔 들여쓰기 공백이 붙어 있어도 표 칸 글자엔 없다
        key = orig.strip()
        if not key or key in fixes:
            continue
        new, ok = merge_reocr(key, ocr_line(rect, key))
        fixes[key] = new.strip()
        fixed += ok
    # 긴 줄부터 — 짧은 깨진 줄('전통੶ 회계')이 긴 줄('(전통੶ 회계 기준)')의 일부일 때 긴 줄이 먼저 바뀌어야 한다
    order = sorted(fixes, key=len, reverse=True)

    def fix(text: str) -> str:
        if not text or not has_foreign_glyphs(text):
            return text
        for orig in order:
            if orig in text:
                text = text.replace(orig, fixes[orig])
        return _FOREIGN_RE.sub("", text)

    return fix, fixed


def _get_engine():
    """한국어 PP-OCRv5 인식 모델(core/ocr_worker 와 같은 설정). rapidocr 가 없으면 None."""
    global _ENGINE
    if _ENGINE is None:
        try:
            from rapidocr import RapidOCR
            from rapidocr.utils.typings import LangRec, ModelType, OCRVersion
            _ENGINE = RapidOCR(params={
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Rec.lang_type": LangRec.KOREAN,
                "Rec.model_type": ModelType.MOBILE,
            })
        except Exception:
            _ENGINE = False
    return _ENGINE or None


def _reocr_line(page: Any, rect: Any, orig: str, engine: Any) -> str:
    """줄 영역을 이미지로 다시 읽는다 — 이미 한 줄이라 글자 위치 찾기(검출) 없이 인식만(줄당 약 0.1초)."""
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    import numpy as np
    from PIL import Image, ImageOps
    best = None
    for zoom, pad in _REOCR_VARIANTS:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=rect)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        if pad:
            img = ImageOps.expand(img, border=pad, fill="white")
        res = engine(np.array(img), use_det=False, use_cls=False, use_rec=True)
        txt = " ".join(str(t) for t in (getattr(res, "txts", None) or [])).strip()
        cand = (_agreement(orig, txt) or 0, len(txt), txt)
        best = cand if best is None or cand > best else best
    return best[2]


def page_fixer(page: Any) -> tuple[Callable[[str], str], int]:
    """PDF 쪽에 깨진 글꼴 흔적이 있으면 그 줄들을 다시 읽어 고치는 함수를 돌려준다.
    흔적이 없거나 rapidocr 가 없으면 아무것도 바꾸지 않는 함수. (함수, 고친 줄 수)."""
    identity = (lambda t: t), 0
    if not has_foreign_glyphs(page.get_text()):
        return identity
    engine = _get_engine()
    if engine is None:
        return identity
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            orig = "".join(s["text"] for s in l["spans"])
            if has_foreign_glyphs(orig):
                lines.append((orig, l["bbox"]))
    return build_fixer(lines, lambda rect, orig: _reocr_line(page, rect, orig, engine))
