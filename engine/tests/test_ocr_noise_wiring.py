"""OCR 경로에 01_OCR noise_rules 가 연결됐는지 — 디지털 문서 경로는 건드리지 않는다(2026-10-16)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.pdf_adapter import apply_ocr_page_rules, apply_ocr_text_rules, reconstruct_ocr_page  # noqa: E402
from core import noise_rules as nr  # noqa: E402


def _line(text, y):
    return {"text": text, "box": [100, y, 900, y + 30], "score": 0.9}


def test_garbage_rows_dropped_before_paragraphs():
    # 그림·장식을 읽은 잡음 줄('■次'系懸')이 본문 단락에 섞이지 않는다
    lines = [_line("오늘 해야 할 일을 내일로 미루지 마라.", 300),
             _line("■次'系懸", 340),
             _line("艾^ 하루에 한개 팔고 하지만 끝이다.", 380)]
    out = reconstruct_ocr_page(lines, 1000, 1400)
    assert "系懸" not in out and "艾" not in out
    assert "미루지 마라." in out and "하루에 한개 팔고" in out


def test_group_mark_becomes_paragraph_break_after_postprocess():
    from core.text_cleaner import tidy
    from core.text_postprocessor import postprocess_markdown
    text = f"앞 그룹의 마지막 문장이 여기서 이어진다(창\n{nr.GROUP_MARK}\n심장 발작을 비롯한 질병이 많다."
    out = apply_ocr_text_rules(postprocess_markdown(tidy(text)))
    assert nr.GROUP_MARK not in out and "\n\n심장 발작을" in out


def test_ordinary_pages_unchanged_by_page_rules():
    pages = ["경영자는 성과를 책임진다.\n조직은 고객을 위해 존재한다.",
             "지식 노동자는 스스로 관리한다.\n시간 관리가 출발점이다."]
    assert apply_ocr_page_rules(pages) == pages
