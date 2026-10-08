# -*- coding: utf-8 -*-
"""core/metadata_extractor.py - D:\\백업\\utility\\OKF_지식위키\\build_frontmatter.py 호환 메타데이터 자동 추출기.

OKF_지식위키 SSOT 규격:
1. 제목 정밀 추출 (인용 각주 제거, 구조 라벨/시리즈명 배제, 정규화)
2. 위키/Obsidian 표준 태그 생성 (슬러그화, 동의어 표준화, 2회 이상 반복 볼드 용어, 불용어 제거)
3. 대분류 카테고리 판별 (글로벌 어학 & 영어, 전자무역 & 비즈니스, 경영 & 전략 기획, AI & 테크놀로지, 인문·신앙 & 라이프 등)
4. 영어 학습/교재 콘텐츠 정밀 감지 (is_english_content)
5. 다단계 핵심 요약 추출 (📌 Executive Summary, 한줄 요약, 본문 첫 문장)
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── 인용 각주 마커 제거: [1], [3-5], [1, 2] 등 ─────────────────────────────
CITE = re.compile(r'\s*\[\d+(?:\s*[-,]\s*\d+)*\]')

def strip_cite(s: str) -> str:
    """인용 각주 표기를 제거하고 양 끝 구두점을 정리합니다."""
    return CITE.sub('', s or '').strip().rstrip('.').strip()

# ── 구조적 헤더/라벨 (제목으로 채택하지 않음) ──────────────────────────────
STRUCT_TITLES = {
    "문서 메타", "한줄 요약", "핵심 지식", "요약", "개요", "목차", "위키화", "확인 필요",
    "문서 제목", "본문 내용", "문서 개요", "표 및 데이터", "추출 품질 및 검토 사항", "원본 정보",
    "부록", "감사의 글", "참고 문헌", "색인", "일러두기", "머리말", "프롤로그", "에필로그",
    "rainbow series", "rainbow series no.1", "rainbow series no", "no.1", "no.2", "no.3",
}

# ── 태그 제외 불용어 목록 (구조·서식용 라벨 및 무의미한 품사) ───────────────
STOP_TAGS = {
    '목적', '배경', '구성', '명칭', '개요', '요약', '결론', '서론', '정의', '특징',
    '핵심', '내용', '방법', '절차', '흐름', '개념', '용어', '주요 개념', '핵심 문장',
    '프로젝트 문서셋 명칭', '대상 독자 및 소비 시스템', '문서셋 구성', '프로젝트 명칭',
    '대상 독자', '작성 목적', '한줄 요약', '핵심 지식', '문서 메타', '문서', '사항',
    '기준', '현황', '추진', '계획', '작성', '검토', '보고', '확인', '진행', '관리',
    '시스템', '업무', '경우', '이후', '포함', '대한', '통해', '위한', '등',
    # 임베디드 프롬프트/지시 템플릿 용어
    '블록명', '근거 문장', '위키 연결어', '우선순위', '출력 형식', '작성 지침',
    '주의', '예시', '규칙', '단계', '항목', '필드', '값',
    # 서식 라벨
    '핵심 논지', '핵심논지', '근거 및 데이터', '주요 인용', '핵심 주장', '개념용어',
    '상세 분해', '세부 분해', '주요 슬라이드', '슬라이드 목차', '실행 방안', '기대 효과',
    '검토 의견', '본문 내용', '문서 개요',
    # 무의미한 동사/형용사/조사 어절 (노이즈 방지)
    '한다', '했다', '된다', '됐다', '있다', '없다', '하는', '되는', '있는', '없는',
    '확인한다', '살핀다', '울린다', '깨운다', '나선다', '살펴본다', '탑승했다', '달랜다',
    '이용해', '시작됐다', '만들고', '확산하라', '공급하라', '짜다', '집어넣어야',
    'part', 'chapter', 'section', 'rainbow', 'series', 'driving', 'salesman', 'power', 'skill',
    'the', 'and', 'for', 'with', 'that', 'this', 'from', 'are', 'have',
}

# ── 동의어 매핑: 변형 태그 → 표준 태그 (OKF SSOT 규격) ────────────────────
SYNONYMS = {
    "노트북lm": "NotebookLM",
    "notebooklm": "NotebookLM",
    "노트북-lm": "NotebookLM",
    "로컬lc": "내국신용장",
    "로컬-lc": "내국신용장",
    "local-lc": "내국신용장",
    "로컬-l-c": "내국신용장",
    "내국-신용장": "내국신용장",
    "구매-확인서": "구매확인서",
    "mro-대행사": "MRO-대행사",
    "mro대행사": "MRO-대행사",
    "mcp": "모델-컨텍스트-프로토콜",
    "모델-컨텍스트-프로토콜": "모델-컨텍스트-프로토콜",
    "vibe-coding": "바이브-코딩",
    "바이브코딩": "바이브-코딩",
    "ktnet": "KTNET",
    "uth": "uTradeHub",
    "utradehub": "uTradeHub",
    "stl": "스마트무역원장",
    "smart-trade-ledger": "스마트무역원장",
    "llm": "LLM",
    "ocr": "OCR",
    "agent": "AI에이전트",
    "ai-agent": "AI에이전트",
    "에이전트": "AI에이전트",
    "dbr": "동아비즈니스리뷰",
    "분석의힘": "분석의-힘",
    "세일즈입문": "세일즈-입문",
}

def canonicalize(slug: str) -> str:
    """소문자 비교 기반 표준 태그 반환"""
    return SYNONYMS.get(slug.lower(), slug)

def slugify_tag(s: str) -> str:
    """괄호 주석 및 특수문자 제거 후 태그 원형 정리"""
    s = strip_cite(s).strip()
    s = re.sub(r'\(.*?\)', '', s)          # 괄호 주석 제거: MRO 대행사(...) → MRO 대행사
    s = s.replace('/', ' ').replace('·', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def slugify_final(s: str) -> str:
    """위키/Obsidian 호환 태그 슬러그: 공백→하이픈, 태그 금지문자 제거"""
    s = s.strip()
    s = re.sub(r'[\s]+', '-', s)                       # 공백 → 하이픈
    s = re.sub(r'[^0-9A-Za-z가-힣_\-]', '', s)          # 영문/숫자/한글/_/- 만 허용
    s = re.sub(r'-{2,}', '-', s).strip('-')            # 하이픈 중복/양끝 정리
    return s

# ── 어학/영어 콘텐츠 감지 패턴 ─────────────────────────────────────────────
ENGLISH_WORD_PATTERNS = [
    r'\benglish\b', r'\bspeaking\b', r'\bgrammar\b', r'\btoeic\b',
    r'\btoefl\b', r'\bopic\b', r'\bvocabulary\b', r'\bvoca\b',
    r'\bidioms?\b', r'\bphrasal\b', r'\bconversation\b'
]
ENGLISH_HANGUL_KEYWORDS = [
    "영어", "회화", "구동사", "영작", "패턴회화", "생활영어", "영문법",
    "영어교재", "english materials", "원어민", "미국인", "외국인", "쉐도잉",
    "이디엄", "숙어", "영어단어", "영어표현", "이보영", "오성식", "토마토",
    "해커스", "시나공", "능률", "넥서스", "길벗"
]
NON_ENGLISH_TECH_KEYWORDS = [
    "anthropic", "openai", "claude", "chatgpt", "gemini", "llm", "coding",
    "프롬프트", "엔지니어링", "바이브코딩", "context engineering", "software",
    "api", "agentic", "개발자", "스타트업", "boris cherny", "erp", "무역원장",
    "notebooklm", "노트북lm", "google", "구글", "sdlc"
]

def is_english_content(path: str = "", text: str = "", title: str = "") -> bool:
    """파일명, 경로, 본문 내용을 종합 분석하여 영어 학습 컨텐츠인지 정밀 감지."""
    full_path_str = (str(path) + " " + str(title)).lower()

    is_tech = any(tk in full_path_str for tk in NON_ENGLISH_TECH_KEYWORDS)
    has_explicit_study = any(hk in full_path_str for hk in ["영어회화", "영어단어", "영어문법", "패턴회화", "생활영어", "영어교재", "toeic", "toefl", "03_english materials"])
    if is_tech and not has_explicit_study:
        return False

    if any(kw in full_path_str for kw in ENGLISH_HANGUL_KEYWORDS):
        return True

    for pat in ENGLISH_WORD_PATTERNS:
        if re.search(pat, full_path_str):
            return True

    if text:
        sample = text[:3000].lower()
        if not is_tech:
            eng_study_cues = ["phrasal verb", "dialogue", "idiom", "grammar in use", "speaking drill", "pronunciation tip"]
            cue_matches = sum(1 for cue in eng_study_cues if cue in sample)
            if cue_matches >= 2:
                return True

    return False

# ── 대분류 카테고리 판별 ───────────────────────────────────────────────────
CATEGORY_RULES = [
    ("글로벌 어학 & 영어", ["영어", "회화", "english", "speaking", "grammar", "voca", "토익", "toeic", "오픽", "이디엄"]),
    ("보고서", ["보고서", "결과보고", "현황보고", "출장보고", "동향", "점검결과"]),
    ("기획서", ["기획서", "제안서", "사업계획", "추진계획", "마스터플랜"]),
    ("매뉴얼", ["매뉴얼", "가이드", "지침", "규정", "절차서", "사용설명서", "이용안내"]),
    ("회의록", ["회의록", "의사록", "간담회", "토의", "의결"]),
    ("전자무역 & 비즈니스", ["무역", "trade", "bpr", "isp", "peppol", "내국신용장", "구매확인서", "수출", "수입", "통관", "선적", "운송", "ktnet", "utradehub", "인코텀즈"]),
    ("경영 & 전략 기획", ["경영", "전략", "분석", "마케팅", "세일즈", "기획", "사업계획", "컨설팅", "dbr", "조직", "성과", "맥킨지", "리더십"]),
    ("AI & 테크놀로지", ["ai", "llm", "인공지능", "코딩", "파이썬", "개발", "아키텍처", "api", "mcp", "에이전트", "클라우드", "데이터베이스"]),
    ("인문·신앙 & 라이프", ["인문", "철학", "신앙", "성경", "교회", "명언", "인생", "자기계발", "독서", "서평", "에세이"]),
    ("기술문서", ["기술명세", "시스템설계", "규격서", "api명세", "인프라"]),
]

def detect_category(text: str, filename: str, path: str = "") -> str:
    """텍스트, 파일명, 파일경로를 기반으로 OKF 지식위키 표준 카테고리를 추론합니다."""
    if is_english_content(path=path, text=text, title=filename):
        return "글로벌 어학 & 영어"

    combined = (f"{path} {filename} {text[:3000]}").lower()
    for cat, kws in CATEGORY_RULES:
        for kw in kws:
            if kw.lower() in combined:
                return cat
    return "일반 지식 & 도구"

# ── 제목 정밀 추출 ────────────────────────────────────────────────────────
def extract_title(text: str, fallback_filename: str) -> str:
    """인용 각주 제거, 구조 라벨/시리즈명 배제, 정규화된 최적의 문서 제목 추출."""
    # 1. 파일명 기반 정제 후보 생성 (예: Sample_스캔책_분석의힘.pdf -> 분석의힘)
    stem = Path(fallback_filename).stem
    clean_stem = re.sub(r'^(?:Sample|sample|샘플)[_\s-]*', '', stem)
    clean_stem = re.sub(r'^(?:스캔책|스캔|교재|자료)[_\s-]*', '', clean_stem)
    clean_stem = re.sub(r'^\d{4,8}[-_]?', '', clean_stem)
    clean_stem = re.sub(r'[-_]v?\d+(\.\d+)*$', '', clean_stem)
    clean_stem = re.sub(r'_소스분석$', '', clean_stem)
    clean_stem = re.sub(r'_정리본$', '', clean_stem).strip()

    # 2. 본문 첫 H1 또는 유효한 첫 타이틀 라인 탐색
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        raw_line = ""
        if line.startswith("#"):
            raw_line = line.lstrip("#").strip()
        elif 2 <= len(line) <= 60 and not line.startswith(("-", "*", "|", "```", "http", ">", "[", "값")):
            raw_line = line

        if not raw_line:
            continue

        candidate = strip_cite(raw_line).strip()
        cand_lower = candidate.lower()

        # 구조 라벨 및 섹션 기호 필터링
        if any(cand_lower.startswith(st) or cand_lower == st for st in STRUCT_TITLES):
            continue
        if re.match(r'^(?:PART|CHAPTER|SECTION|제\s*\d+\s*[장절편]|부록|페이지|슬라이드|시트)\s*[\d\.\:\s]*', candidate, re.IGNORECASE):
            continue
        if len(candidate) <= 2:
            continue

        # 유효한 후보 발견 시 반환
        return candidate

    # 본문에서 유효한 제목을 찾지 못한 경우 정제된 파일명 사용
    return clean_stem if clean_stem else stem

# ── 위키/Obsidian 호환 태그 추출 ───────────────────────────────────────────
def build_tags(text: str, title: str = "", category: str = "", is_eng: bool = False, limit: int = 10) -> list[str]:
    """OKF 지식위키 SSOT 규격: 도메인 개념 중심의 정규화된 태그 목록을 생성합니다."""
    tags, seen = [], set()

    def add(t: str):
        if not t:
            return
        t = slugify_tag(t)
        if not (t and 1 < len(t) <= 25 and t not in STOP_TAGS):
            return
        # 조사나 어미로 끝나는 단어 걸러내기 (한다, 했다, 있는, 등의 불용 토큰 차단)
        if re.search(r'(한다|했다|이다|였다|있다|없다|하고|되고|하며|되며|은|는|이|가|을|를|에|의|로|으로)$', t) and len(t) <= 3:
            return
        slug = canonicalize(slugify_final(t))
        if slug and slug.lower() not in seen and slug not in STOP_TAGS:
            seen.add(slug.lower())
            tags.append(slug)

    # 영어 학습 컨텐츠인 경우 기본 도메인 태그 우선 주입
    if is_eng or category == "글로벌 어학 & 영어":
        add("영어학습")
        add("영어회화")

    # 카테고리 기반 추천 태그
    if category == "전자무역 & 비즈니스":
        add("전자무역")
    elif category == "경영 & 전략 기획":
        add("경영전략")
    elif category == "AI & 테크놀로지":
        add("AI")

    # 1순위: 본문 내 '연결 키워드' 또는 '**키워드**:' 라인 탐색
    m_sec = re.search(r'연결\s*키워드[^\n]*\n([^\n]+)', text)
    if m_sec:
        kw_line = re.sub(r'^[>\s*-]+', '', m_sec.group(1).strip()).strip('[]')
        kw_line = re.sub(r'^\*{0,2}\s*연결\s*키워드\s*\*{0,2}\s*[:：]\s*', '', kw_line)
        for kw in re.split(r'[,，、]', kw_line):
            add(kw.strip(' *`"\''))
    else:
        m_nlm_kw = re.search(r'\*\*키워드\*\*[:：]\s*([^\n]+)', text)
        if m_nlm_kw:
            for kw in re.split(r'[,，、]', m_nlm_kw.group(1)):
                add(kw.strip(' *`"\''))

    # 2순위: 본문 전체에서 2회 이상 반복되는 볼드(**용어**) 추출
    bold_terms = [slugify_tag(m) for m in re.findall(r'\*\*(.+?)\*\*', text)]
    cnt = collections.Counter(bold_terms)
    for term, c in cnt.most_common():
        if c >= 2:
            add(term)

    # 3순위: 제목의 핵심 명사 추출
    if title:
        title_tokens = re.findall(r'[가-힣A-Za-z0-9]{2,}', title)
        for tt in title_tokens:
            add(tt)

    # 4순위: 본문 고빈도 도메인 명사 폴백 (한글/영문 2~8자)
    if len(tags) < 4:
        content_tokens = re.findall(r'[가-힣A-Za-z]{2,8}', text[:4000])
        f_cnt = collections.Counter(content_tokens)
        for tok, count in f_cnt.most_common(20):
            if count >= 3:
                add(tok)
            if len(tags) >= limit:
                break

    return tags[:limit]

# ── 다단계 핵심 요약 추출 ──────────────────────────────────────────────────
def extract_summary(text: str, max_chars: int = 220) -> str:
    """OKF 지식위키 규격: Executive Summary 또는 첫 문단에서 핵심 요약 추출."""
    # 1순위: AI Executive Summary (📌 / 🎯)
    m_ai = re.search(r'>\s*(?:📌|🎯)\s*\*\*(?:핵심\s*요약|Executive\s*Summary|AI[^\*:]*요약)[^\*:]*\*\*:?\s*(.+)', text, re.IGNORECASE)
    if m_ai:
        return strip_cite(m_ai.group(1).strip())[:max_chars]

    # 2순위: '# 한줄 요약' 또는 '**한줄 요약**'
    m_hl = re.search(r'^#\s*한줄\s*요약\s*\n(.*?)(?=^#\s|\Z)', text, re.S | re.M)
    if m_hl:
        body = re.sub(r'^\s*[-*]\s*', '', m_hl.group(1).strip(), flags=re.M)
        first_l = body.split('\n')[0].strip()
        if first_l:
            return strip_cite(first_l)[:max_chars]

    m_nlm = re.search(r'\*\*한줄\s*요약\*\*\s*\n+>\s*(.+)', text)
    if m_nlm:
        return strip_cite(m_nlm.group(1).strip())[:max_chars]

    # 3순위: 일반 인용구 핵심 요약
    m_q = re.search(r'>\s*📌\s*(?:\*\*[^*]+(?::\*\*|\*\*:)\s*|\[[^\]\n]+\]:\s*)?([^\n]+)', text)
    if m_q:
        return strip_cite(m_q.group(1).strip())[:max_chars]

    # 4순위: 본문 첫 실질 서술 문장 (제목/헤더/표/목록 제외)
    lines = [
        ln.strip() for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith(("#", "-", "*", "|", "```", "http", ">", "[", "값", "ISBN"))
        and not any(ln.strip().startswith(st) for st in ["PART", "CHAPTER", "SECTION", "부록", "감사의"])
    ]
    if lines:
        first_p = " ".join(lines[:2])
        return strip_cite(first_p)[:max_chars]

    return "문서 내용 요약 정보가 없습니다."

def extract_description(text: str, max_chars: int = 220) -> str:
    """하위 호환용 description 추출 함수"""
    return extract_summary(text, max_chars)

def detect_language(text: str) -> str:
    """한글/영문 비율 분석 (ko, en, mixed)"""
    hangul_count = len(re.findall(r"[\uac00-\ud7a3]", text))
    alpha_count = len(re.findall(r"[a-zA-Z]", text))
    total = hangul_count + alpha_count
    if total == 0:
        return "ko"
    ratio = hangul_count / total
    if ratio > 0.7:
        return "ko"
    elif ratio < 0.2:
        return "en"
    return "mixed"

def extract_entities(text: str) -> list[str]:
    """조직, 시스템, 회사 등 주요 개체명 추출"""
    entities = set()
    org_patterns = [
        r"(?:주식회사\s+|㈜|\(주\))([가-힣A-Za-z0-9]+)",
        r"([가-힣A-Za-z0-9]+(?:위원회|공사|진흥원|협회|재단|연구원|은행|대학|본부|센터))",
        r"([A-Z]{2,}(?:[-_][A-Z0-9]+)*)",
    ]
    for pat in org_patterns:
        for m in re.finditer(pat, text):
            ent = m.group(1) if m.groups() else m.group(0)
            if len(ent) >= 2 and ent not in STOP_TAGS:
                entities.add(ent)
                if len(entities) >= 6:
                    break
        if len(entities) >= 6:
            break
    return sorted(list(entities))


def extract_keywords_and_topics(text: str, limit: int = 5) -> tuple[list[str], list[str]]:
    """하위 호환용 키워드 및 토픽 추출 함수 (build_tags 기반)."""
    tags = build_tags(text, limit=limit)
    keywords = tags if tags else ["문서"]
    topics = tags[:2] if len(tags) >= 2 else (keywords[:1] if keywords else ["일반"])
    return keywords, topics
