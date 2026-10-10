# -*- coding: utf-8 -*-
"""텍스트 레이어 PDF 블록 → 문단 묶기(group_column_blocks_into_paragraphs) 회귀 테스트.

실측(2026-10-10, 결과_MD 표본 25권): 세로 간격만 보고 블록을 이어 붙여, 짧은 줄로 끝나는
색인·차례 항목, 표 칸, 그림 라벨, 도서 광고, 제목이 다음 블록 본문에 붙었다(의심 2,729곳 중 표본 65%가 오결합).
MyOCR text_refiner 의 줄 잇기 기준(흔한 줄 길이의 75% 이상 찬 줄만 잇기)을 블록 단위로 적용한다.
"""
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from adapters.pdf_adapter import group_column_blocks_into_paragraphs as group

FULL = "본문 줄은 단의 오른쪽 끝까지 꽉 차서 다음 줄로 넘어간다"   # 흔한 줄 길이


def _blocks(texts, gap=4):
    out, y = [], 100.0
    for t in texts:
        h = 12.0 * len(t.splitlines())
        out.append({"text": t, "y0": y, "y1": y + h, "is_table": False})
        y += h + gap
    return out


def test_full_lines_still_joined():
    paras = group(_blocks([f"{FULL}\n{FULL}", f"{FULL}\n{FULL}", f"{FULL}\n끝난다."]))
    assert len(paras) == 1


def test_heading_and_ad_not_joined_to_body():
    # 짧은 줄로 끝나는 블록(제목·도서 광고)은 다음 본문 블록에 붙이지 않는다
    body = f"{FULL}\n{FULL}\n{FULL}"
    for short in ["Lead the Field", "양장/12.000원", "목표는 완전한 이해다"]:
        paras = group(_blocks([body + ".", short, body]))
        assert short in paras and len(paras) == 3, (short, paras)


def test_index_entries_kept_apart():
    entries = ["teams, 141, 157-158", "Ten Goal Exercise, 68, 180", "Time management, 12"]
    paras = group(_blocks([f"{FULL}\n{FULL}."] + entries))
    assert all(e in paras for e in entries), paras


def test_short_line_joined_when_next_block_starts_with_ending():
    # 좁은 단 본문: '…우월적 지위' ⟨블록 경계⟩ '를 확보했다' — 한 단어가 잘린 것이라 잇는다
    paras = group(_blocks([f"{FULL}\n{FULL}\n장에서 우월적 지위", f"를 확보했다. {FULL}\n{FULL}"]))
    assert len(paras) == 1
