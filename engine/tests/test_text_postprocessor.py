"""text_postprocessor 회귀 테스트.

Regression (2026-10-10, 결과_MD 98권 실측): 구두점 뒤 영문까지 띄워 'www. naver. com'·'OCR. pdf'(978곳),
기호 치환표가 단어 속까지 바꾸고('item2'→'ite m²') 'No, there' 를 'No. there' 로 바꿨다.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import text_postprocessor as tp  # noqa: E402


def _norm(s):
    return tp.fix_punctuation_spacing(tp.normalize_unicode_and_invisible(s))


@pytest.mark.parametrize("text", [
    "출처: 책_OCR.pdf 참고", "www.naver.com", "U.S.의 정책", "videoClip item2 km2",
    "(a) (b) (c)", "No, there is no failure", "e,g, 예시",
])
def test_preserves(text):
    assert _norm(text) == text


@pytest.mark.parametrize("src, want", [
    ("했다.그리고", "했다. 그리고"),
    ("Apple,그리고", "Apple, 그리고"),
    ("끝났다 .", "끝났다."),
    ("( 괄호 )", "(괄호)"),
])
def test_fixes(src, want):
    assert _norm(src) == want
