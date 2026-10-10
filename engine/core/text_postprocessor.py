# -*- coding: utf-8 -*-
"""core/text_postprocessor.py - 텍스트 정규화 및 가독성 교정 후처리기.

출처 및 기반: D:\\백업\\utility\\텍스트 정규화\\
  - 04_통합텍스트정규화/core/cleaner.py (join_broken_lines, remove_ocr_artifacts)
  - 01_OCR_스캔파일텍스트추출프로그램/core/char_normalizer.py (Unicode, 하이픈 어절 복원)
  - 01_OCR_스캔파일텍스트추출프로그램/core/postprocessor.py (단락 복원 및 공백 정규화)

마크다운 구조(YAML Front Matter, 코드 블록, 표, 헤더, 리스트)를 100% 안전하게 보존하면서,
PDF/HWP/OCR 변환 시 발생하는 불필요한 줄바꿈, 어절 끊김, 조사 분리, 특수문자 노이즈를 교정합니다.
"""
from __future__ import annotations

import re
import sys
import unicodedata

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 문장 종결 부호 (이 문자로 끝나면 문장이 완료된 것으로 봄)
_SENT_END = re.compile(r'[.!?。！？…\:\;]\s*$')

# 새 단락/새 구조 시작 패턴 (헤더, 목록, 불릿, 인용 등)
_BLOCK_START = re.compile(
    r"^(\s*#{1,6}\s|"          # 헤더 (#, ## 등)
    r"\s*[-*+•◦▪▫※▶▷]\s|"     # 불릿 목록 (- , * , + , • 등)
    r"\s*\d+[\.)]\s|"          # 번호 목록 (1. , 1) 등)
    r"\s*>\s|"                 # 인용문 (>)
    r"\s*\||"                  # 표 (|)
    r"\s*```|"                 # 코드 블록 (```)
    r"\s*[-*_]{3,}\s*$)"       # 수평선 (---, *** 등)
)

# 비가시 유니코드 문자 (BOM, ZWSP, ZWNJ, ZWJ, WORD JOINER 등)
_INVISIBLE_CHARS = re.compile(r"[\ufeff\u200b\u200c\u200d\u2060]")

# OCR 가운뎃점/파이프 노이즈
_OCR_ARTIFACTS = re.compile(r"\s*ᆞ+\s*")

# Unicode 합자 분해 (01_OCR_스캔파일텍스트추출프로그램 L1 규칙)
_LIGATURES: dict[str, str] = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
    "ﬅ": "st", "æ": "ae", "œ": "oe",
}

# 특수기호·단위·약어 치환
# 문자열을 통째로 바꾸므로 단어 속까지 바뀌는 항목은 뺐다 (2026-10-10, 결과_MD 98권 실측):
#   '(c)'·'(r)' — 목록 번호 '(a) (b) (c)' 를 ©·® 로 바꿈 / 'oC'·'m2'·'km2' — 'videoClip'·'item2' 속까지 바꿈
#   'No,'→'No.' — 'No, there is…' 의 뜻이 바뀜 / 'e,g,'·'i,e,'·'etc,' — 문장 속 쉼표를 마침표로 바꿈
_SYMBOL_MAP: dict[str, str] = {
    "(tm)": "™", "(TM)": "™",
    "+-": "±", "->": "→", "<-": "←", ">=": "≥", "<=": "≤", "!=": "≠",
    "deg C": "℃",
}

# 한글 조사 및 어미 목록 (줄바꿈으로 분리되어 있으면 결합 대상)
_PARTICLES_PATTERN = (
    r"(?:은|는|이|가|을|를|에|의|로|으로|와|과|도|만|서|에서|에게|고|며|면|으며|어|아|지|거나|어서|아서|는데|지만|면서|도록|으면|습니다|입니다|합니다)"
)


def normalize_unicode_and_invisible(text: str) -> str:
    """유니코드 NFKC 정규화, 비가시 문자 정리, 합자 분해, 기호 정규화."""
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE_CHARS.sub("", text)
    # NBSP(non-breaking space)는 일반 공백으로 변환 (어절 붙음 방지)
    text = text.replace("\xa0", " ")
    for lig, rep in _LIGATURES.items():
        text = text.replace(lig, rep)
    for src, dst in _SYMBOL_MAP.items():
        text = text.replace(src, dst)
    return text


def fix_english_confusion(text: str) -> str:
    """영문 세리프/숫자 혼동 교정 (01_OCR char_normalizer 규칙)."""
    # 숫자 사이 I->1, l->1, S->5, B->8, G->6, O->0
    confusion = {"I": "1", "l": "1", "S": "5", "B": "8", "G": "6"}
    for wrong, correct in confusion.items():
        text = re.sub(rf"(?<=[0-9]){re.escape(wrong)}(?=[0-9])", correct, text)
    text = re.sub(r"(?<=[0-9])O(?=[0-9])", "0", text)
    # 소문자 단어 내부 I/1 -> l (양쪽이 소문자일 때: "shouId" -> "should")
    text = re.sub(r"(?<=[a-z])[I1](?=[a-z])", "l", text)
    return text


def fix_hyphenated_words(text: str) -> str:
    """행 끝 하이픈으로 쪼개진 한글/영문 어절을 복원합니다."""
    # 한글 하이픈 분절 연결: 예) "효율적-\n으로" -> "효율적으로"
    text = re.sub(r"([가-힣])-\n\s*([가-힣])", r"\1\2", text)
    # 영문 하이픈 분절 연결: 예) "infor-\nmation" -> "information"
    text = re.sub(r"([a-zA-Z])-\n\s*([a-zA-Z])", r"\1\2", text)
    return text


def clean_ocr_artifacts(text: str) -> str:
    """가운뎃점 클러스터 및 제어문자 등 OCR/변환 잡음을 정제합니다."""
    text = _OCR_ARTIFACTS.sub(" ", text)
    # 제어문자 제거 (줄바꿈 \n, 탭 \t 제외)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text


def strip_scan_margin_noise(line: str) -> str:
    """스캔 도서 특화 줄 앞뒤 마진 노이즈 및 스캔 기호 제거 (01_OCR postprocessor 규칙)."""
    if not line.strip():
        return ""
    # 마크다운 블록 요소(헤더 #, 불릿 -, 인용 > 등)는 원형 보존
    if _BLOCK_START.match(line):
        return line

    # 선두 노이즈 토큰(의미문자 없는 기호/숫자 2개 이상) 필터링
    tokens = line.split(" ")
    n = 0
    for tok in tokens:
        t = tok.strip()
        if not t:
            n += 1
        elif re.search(r"[가-힣A-Za-z]", t) is None and len(t) <= 3:
            n += 1
        else:
            break
    if n >= 2:
        tokens = tokens[n:]
    proc = " ".join(tokens).strip()

    # 본문 첫 글자에 붙은 선두 잡음 기호 제거 (마크다운 헤더 #, 따옴표·괄호·목록 기호는 보존)
    proc = re.sub(r"^[\s*|~^@、。]+", "", proc)
    # 줄 뒤 스캔 잡음 제거 (정상 구두점 . , ! ? : 는 보존)
    proc = re.sub(r"[\sᆞ~_|@#^*、。]+$", "", proc)
    # 줄 내부 가운뎃점 클러스터 치환
    proc = re.sub(r"\s*ᆞ+\s*", " ", proc)
    return proc.strip()


def remove_noise_lines(text: str) -> str:
    """스캔 잔여물 등 의미 있는 문자(한글·영문·숫자)가 2자 미만인 순수 잡음 줄 제거."""
    lines = text.splitlines()
    result = []
    for line in lines:
        if not line.strip():
            result.append(line)
            continue
        meaningful = re.sub(r"[^\w가-힣]", "", line)
        if len(meaningful) >= 2:
            result.append(line)
    return "\n".join(result)


def remove_page_number_artifacts(text: str) -> str:
    """본문 중간에 단독으로 끼어든 쪽번호/페이지 라벨(예: '### 페이지 1', '2페이지', '12', '- 3 -') 노이즈를 제거합니다."""
    # '### 페이지 1' 형태 제거
    text = re.sub(r"(?m)^\s*#{1,6}\s*페이지\s*\d+\s*$\n?", "", text)
    # '[페이지 1]' 형태 제거
    text = re.sub(r"(?m)^\s*\[페이지\s*\d+\]\s*$\n?", "", text)
    # '2페이지' 단독 줄 제거
    text = re.sub(r"(?m)^\s*\d+\s*페이지\s*$\n?", "", text)
    # '- 12 -' 단독 쪽번호 줄 제거
    text = re.sub(r"(?m)^\s*-\s*\d+\s*-\s*$\n?", "", text)
    # 3줄 이상 연속 개행 정리
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def fix_punctuation_spacing(text: str) -> str:
    """구두점 앞뒤 공백 및 괄호 공백을 한국어 어법에 맞게 정규화합니다."""
    # 쉼표, 마침표, 물음표, 느낌표 앞의 불필요한 공백 제거
    # (줄바꿈은 먹지 않는다 — 다음 줄 첫머리 구두점을 앞 줄에 붙이지 않게)
    text = re.sub(r"[ \t]+([.,!?。！？、])", r"\1", text)
    # 구두점 뒤에 공백이 없는 경우 한 칸 띄움 — 한글 앞에서만. 영문 앞까지 띄우면 'www. naver. com'·
    # 'OCR. pdf' 가 된다(결과_MD 978곳). 영문 머리글자 뒤 마침표('U.S.의')도 띄우지 않는다
    text = re.sub(r"(?<![A-Za-z])([.])([가-힣])|([,!?。！？])([가-힣])",
                  lambda m: f"{m.group(1) or m.group(3)} {m.group(2) or m.group(4)}", text)
    # 괄호 안쪽 불필요한 공백 제거: "( 텍스트 )" -> "(텍스트)"
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"\[\s+", "[", text)
    text = re.sub(r"\s+\]", "]", text)
    # 말줄임표 표준화 (... 또는 …)
    text = re.sub(r"…{2,}", "...", text)
    text = text.replace("…", "...")
    return text


def join_split_particles(text: str) -> str:
    """줄바꿈이나 빈 줄로 인해 어절 중간 또는 조사가 끊긴 경우를 결합합니다.

    예: '맞을 수\\n\\n도 있고' -> '맞을 수도 있고'
        '직접 읽\\n\\n거나 고치지는' -> '직접 읽거나 고치지는'
    """
    # 1. 단어 중간 분절 결합: 어미/조사로 시작하는 행 ('\n\n도 있고' -> ' 도 있고')
    pattern = rf"([가-힣A-Za-z0-9])\n{{1,2}}\s*({_PARTICLES_PATTERN}(?:\s|[.,!?]|$))"
    text = re.sub(pattern, r"\1 \2", text)

    # 2. 어절 분절 결합: 어미 자체 (예: '읽\n\n거나' -> '읽거나')
    # 앞 글자가 받침 있는 글자이고 뒷 단어가 어미(거나, 으며 등)인 경우 공백 없이 결합
    verb_endings = r"(?:거나|으며|어서|아서|는데|지만|면서|도록|으면)"
    pattern_verb = rf"([가-힣])\n{{1,2}}\s*({verb_endings}(?:\s|[.,!?]|$))"
    text = re.sub(pattern_verb, r"\1\2", text)

    return text


def _should_join_lines(prev_line: str, next_line: str) -> bool:
    """두 줄이 한 문장 내에서 불필요하게 끊긴 줄바꿈인지 판별합니다."""
    prev = prev_line.strip()
    nxt = next_line.strip()

    if not prev or not nxt:
        return False

    # 윗줄이 너무 짧으면 제목·소제목·목차 항목일 가능성이 높으므로 다음 줄과 합치지 않음
    # 단, 한국어 조사나 접속어, 쉼표 등으로 끝나는 경우는 문장 중간이므로 결합 허용
    particles = ("은", "는", "이", "가", "을", "를", "에", "의", "로", "으로", "와", "과", "도", "만", "고", "며", "면", "서", "등", ",")
    if len(prev) < 10 and not any(prev.endswith(p) for p in particles):
        return False

    # 아랫줄이 새 챕터·장절·목차·부록 기호로 시작하면 합치지 않음
    if re.match(r"^(?:PART|CHAPTER|SECTION|제\s*\d+\s*[장절편]|부록|감사의\s*글|\d+[.．]\s|\|)", nxt, re.IGNORECASE):
        return False

    # 윗줄이나 아랫줄이 마크다운 블록(헤더, 리스트, 표, 코드, 수평선)인 경우 결합하지 않음
    if _BLOCK_START.match(prev_line) or _BLOCK_START.match(next_line):
        return False

    # 윗줄이 문장 종결 부호(., !, ?, :, ;)로 끝나는 경우 결합하지 않음
    # 단, 따옴표나 괄호가 열린 상태에서 줄바꿈된 경우는 결합해야 함
    if _SENT_END.search(prev) and not (prev.startswith(("“", "\"", "‘", "'")) and not prev.endswith(("”", "\"", "’", "'"))):
        return False

    # 아랫줄이 들여쓰기(2공백 이상 또는 탭)로 시작하면 의도된 들여쓰기 문단으로 유지
    if next_line.startswith(("  ", "\t", "　")):
        return False

    return True


def join_broken_paragraphs(text: str) -> str:
    """단락 내에서 어절이나 문장 중간에 발생한 불필요한 줄바꿈을 자연스럽게 이어붙입니다."""
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        cur = lines[i]

        # 빈 줄은 단락 구분자로 유지
        if not cur.strip():
            out.append(cur)
            i += 1
            continue

        # 마크다운 블록 요소는 개별 유지
        if _BLOCK_START.match(cur):
            out.append(cur)
            i += 1
            continue

        # 다음 줄들과 연결 가능한지 확인
        while i + 1 < len(lines):
            nxt = lines[i + 1]
            if not nxt.strip():
                break

            if _should_join_lines(cur, nxt):
                # 윗줄 끝과 아랫줄 시작을 단일 공백으로 이어붙임
                cur = cur.rstrip() + " " + nxt.lstrip()
                i += 1
            else:
                break

        out.append(cur)
        i += 1

    return "\n".join(out)


def rejoin_page_boundary_paragraphs(prev_text: str, next_text: str) -> str:
    """D-13 규칙 기반 페이지 경계 단락 재결합.

    앞 페이지 마지막 단락이 문장 종결 부호(., !, ?, …) 없이 한글이나 쉼표로 끝나고,
    뒷 페이지 첫 단락이 한글이나 소문자로 시작하면 한 문장으로 부드럽게 결합합니다.
    어절 자체가 쪼개진 경우(예: '성' + '찰의' 또는 '가' + '는')는 공백 없이 직결하고,
    그렇지 않으면 한 칸 공백으로 이어붙입니다.
    """
    prev = prev_text.rstrip()
    nxt = next_text.lstrip()
    if not prev:
        return nxt
    if not nxt:
        return prev

    prev_lines = [l for l in prev.splitlines() if l.strip()]
    next_lines = [l for l in nxt.splitlines() if l.strip()]
    if not prev_lines or not next_lines:
        return prev + "\n\n" + nxt

    last_line = prev_lines[-1].strip()
    first_line = next_lines[0].strip()

    # 앞 페이지 끝이 마크다운 헤더, 목록, 표, 코드블록인 경우 결합 금지
    if _BLOCK_START.match(last_line) or _BLOCK_START.match(first_line):
        return prev + "\n\n" + nxt

    last_char = last_line[-1]
    first_char = first_line[0]

    # 종결부호로 끝난 단락은 온전한 문장이므로 결합하지 않고 단락 분리(\n\n) 유지
    if last_char in (".", "!", "?", "…", ":", ";") or last_line.endswith(('."', '!"', '?"', ".'", "!'", "?'")):
        return prev + "\n\n" + nxt

    # 앞 페이지 끝이 한글이나 쉼표이고, 뒷 페이지 시작이 한글인 경우 병합 대상
    if ("가" <= last_char <= "힣" or last_char == ",") and ("가" <= first_char <= "힣" or first_char.islower()):
        last_token = last_line.split()[-1]
        first_token = first_line.split()[0]

        direct_join = False
        try:
            from core.korean_spacing_corrector import _D11_BOUND_FRAGMENTS, _COMMON_SPLIT_PAIRS
            if (first_token in _D11_BOUND_FRAGMENTS) or ((last_token, first_token) in _COMMON_SPLIT_PAIRS):
                direct_join = True
            elif len(last_token) <= 2 and len(first_token) <= 2:
                direct_join = True
        except ImportError:
            pass

        sep = "" if direct_join else " "
        return prev + sep + nxt

    return prev + "\n\n" + nxt


def refine_plain_content(content: str) -> str:
    """일반 텍스트 단락에 대해 정제 규칙들을 순차적으로 적용합니다."""
    content = normalize_unicode_and_invisible(content)
    content = fix_hyphenated_words(content)
    content = clean_ocr_artifacts(content)
    content = remove_page_number_artifacts(content)
    # 각 행별 스캔 마진 노이즈 정제
    content = "\n".join(strip_scan_margin_noise(l) for l in content.splitlines())
    content = remove_noise_lines(content)
    content = join_split_particles(content)
    content = join_broken_paragraphs(content)

    # AI Agent 없는 오프라인 고속 한국어 띄어쓰기 및 맞춤법 교정기 연동
    try:
        from core.korean_spacing_corrector import refine_korean_text
        content = refine_korean_text(content)
    except Exception:
        pass

    content = fix_punctuation_spacing(content)
    # 연속 공백(2칸 이상)은 단일 공백으로 (단, 줄 시작 공백 제외)
    content = re.sub(r"(?<=\S) {2,}", " ", content)
    return content


def postprocess_markdown(md_text: str) -> str:
    """마크다운 문서 전체를 대상으로 구조를 보존하면서 가독성 정제를 수행합니다."""
    if not md_text:
        return ""

    # 1. YAML Front Matter 분리
    fm_part = ""
    body_part = md_text

    if md_text.startswith("---"):
        m = re.match(r"^---\s*\n.*?\n---\s*\n", md_text, re.DOTALL)
        if m:
            fm_part = m.group(0)
            body_part = md_text[m.end():]

    # 2. 코드 블록(```) 분리
    code_blocks = body_part.split("```")
    cleaned_chunks = []

    for idx, chunk in enumerate(code_blocks):
        if idx % 2 == 1:
            # 홀수 번째: 코드 블록 내부 (원형 100% 보존)
            cleaned_chunks.append(chunk)
        else:
            # 짝수 번째: 일반 마크다운 본문
            # 먼저 표 셀에 갇힌 레이아웃 표나 중첩 표를 본문 단락으로 안전하게 해제
            from core.text_cleaner import unwrap_layout_tables
            unwrapped_chunk = unwrap_layout_tables(chunk)

            # 진짜 데이터 표(Table) 영역 보호를 위해 줄 단위 순회
            lines = unwrapped_chunk.split("\n")
            sub_chunks = []
            curr_lines = []
            in_table = False

            for line in lines:
                is_tbl_line = bool(line.strip().startswith("|") and line.strip().endswith("|"))
                if is_tbl_line:
                    if not in_table and curr_lines:
                        sub_chunks.append(refine_plain_content("\n".join(curr_lines)))
                        curr_lines = []
                    in_table = True
                    sub_chunks.append(line)
                else:
                    in_table = False
                    curr_lines.append(line)

            if curr_lines:
                sub_chunks.append(refine_plain_content("\n".join(curr_lines)))

            cleaned_chunk = "\n".join(sub_chunks)
            # 연속 3줄 이상 빈 줄을 2줄로 정리
            cleaned_chunk = re.sub(r"\n{3,}", "\n\n", cleaned_chunk)
            cleaned_chunks.append(cleaned_chunk)

    restored_body = "```".join(cleaned_chunks).strip() + "\n"
    return (fm_part + restored_body) if fm_part else restored_body
