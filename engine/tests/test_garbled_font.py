# -*- coding: utf-8 -*-
"""글자 대응표가 깨진 글꼴의 줄만 이미지로 다시 읽기 (core/garbled_font) 회귀 테스트.

실측: DBR 잡지 PDF(현대카드 Case Study 등)의 표·제목·캡션 글꼴(DongA3G)이 한글 일부를 구르무키·
말라얄람·아랍 문자 등으로, 영문을 밀린 글자('TVA'→'57A')로 내보내 표 칸이 '전통੶ 회계'·
'포인트\\x10ഊఔ' 처럼 깨진 채 변환됐다. 01_OCR 의 같은 복원(pdf_text_layer)을 이식한 것.
"""
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from core import garbled_font as gf


def test_foreign_script_detected_only_in_garbled_text():
    assert gf.has_foreign_glyphs("전통੶ 회계")
    assert gf.has_foreign_glyphs("포인트\x10ഊఔ")
    assert gf.has_foreign_glyphs("ҳ주의 거울")
    assert not gf.has_foreign_glyphs("전통적 회계 TVA(Total View Accounting) 1,234원 • ① “인용” Толстой")


def test_merge_replaces_only_garbled_parts():
    new, ok = gf.merge_reocr("전통੶ ߏ식의 회계৪ 57A ߏ식의 ମ이", "전통적 방식의 회계와 TVA 방식의 차이")
    assert ok and new == "전통적 방식의 회계와 TVA 방식의 차이"
    new, ok = gf.merge_reocr("߃기ର 교수는 서울대 경영대학", "박기찬 교수는 서울대 경엉대학")
    assert ok and new == "박기찬 교수는 서울대 경영대학"      # OCR 이 멀쩡한 글자를 틀린 곳은 원문 유지


def test_merge_distrusts_unrelated_ocr():
    new, ok = gf.merge_reocr("회계를 ࢚܀게 ࠈঞѵ다는 아이디어는 어ڊ게 나ৱ나.", "룸를 콩저 그을 극이의")
    assert not ok and not gf.has_foreign_glyphs(new) and "아이디어는" in new


def test_fixer_applies_to_table_cells_and_blocks_longest_first():
    # 짧은 깨진 줄('전통੶ 회계')이 긴 깨진 줄의 일부여도 긴 줄이 먼저 바뀌어야 둘 다 고쳐진다
    lines = [("전통੶ 회계", "R1"), ("(전통੶ 회계 기઱)", "R2"), ("개ಜ യ", "R3")]
    fake = {"R1": "전통적 회계", "R2": "(전통적 회계 기준)", "R3": "개편후"}
    fix, n = gf.build_fixer(lines, lambda rect, orig: fake[rect])
    assert n == 3
    # 표 칸: 고칠 줄 목록에 없는 부분('57A੶ ੻Ӓ')은 깨진 문자만 지움(겹 공백은 후처리가 정리)
    assert fix("57A੶ ੻Ӓ (전통੶ 회계 기઱)") == "57A  (전통적 회계 기준)"
    assert fix("전통੶ 회계") == "전통적 회계"
    assert fix("개ಜ യ 결과") == "개편후 결과"


def test_fixer_matches_cell_text_without_pdf_indent():
    # PDF 줄 정보엔 들여쓰기 공백이 붙어 있어도 표 칸 글자엔 없다 — 공백을 떼고 맞춘다
    fix, n = gf.build_fixer([("        57A੶ ੻Ӓ ", "R")], lambda rect, orig: "TVA적 접근")
    assert n == 1 and fix("57A੶ ੻Ӓ (전통적 회계 기준)") == "TVA적 접근 (전통적 회계 기준)"


def test_fixer_identity_without_garbled_lines():
    fix, n = gf.build_fixer([], lambda rect, orig: "")
    assert n == 0 and fix("멀쩡한 본문") == "멀쩡한 본문"
