# 통합 문서 변환기 (파일형식변환기_MD)

다양한 형식의 문서(Office, HWP, PDF, 이미지 OCR, Text, EPUB)를 자동으로 감지하여 **YAML Front Matter가 포함된 AI 최적화 OKF(Open Knowledge Format) 호환 Markdown(.md)** 파일로 일괄 변환하는 도구입니다.

---

## 1. 주요 특징

1. **독립 패키지 구성 & Microsoft MarkItDown 통합**:
   - 기존 `OKF_지식위키`, `MyOCR`, `텍스트 정규화` 자산의 핵심 로직을 복사 및 리팩토링하여 외부 연동 없이 독립 구동.
   - [Microsoft MarkItDown](https://github.com/microsoft/markitdown) 패키지를 통합하여 고성능 하이브리드 변환 엔진 지원 (`auto` / `markitdown` / `native`).
2. **다양한 파일 형식 지원**:
   - 구버전/현대 Office: `.doc`, `.docx`, `.ppt`, `.pptx`, `.xls`, `.xlsx`, `.rtf`
   - 한글 문서: `.hwp`, `.hwpx` (백그라운드 보안 팝업 자동 승인 스레드 내장)
   - PDF & 스캔 문서: PyMuPDF / MarkItDown 텍스트 레이어 추출 및 스캔 PDF의 자동 OCR 판별
   - 이미지 문서: `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff` 등 RapidOCR(ONNX 기반 PP-OCR) 기반 한국어/영어 텍스트 인식
   - 텍스트/마크다운: `.txt` (인코딩 자동감지), `.md` (기존 Front Matter 보존 및 병합)
   - 전자책: `.epub` (spine 읽기 순서 유지 변환)
3. **가독성 정제 후처리 (`core/text_postprocessor.py`)**:
   - 단락 내 불필요 하드 줄바꿈 결합, 하이픈 분절 어절 복원, 비가시 문자 정리.
   - 페이지 구분 텍스트(`### 페이지 N` 등)를 배제하여 문맥 연결성 및 단락 흐름 극대화.
4. **엄격한 OKF YAML Front Matter 규격**:
   - 프롬프트 100% 준수 (2공백 들여쓰기, 고유 ID, 카테고리, 키워드, 개체명, OCR 신뢰도, 상태, 오류 로그).
5. **표준 Markdown 본문 템플릿 및 저장소 분리**:
   - 순수 변환 마크다운 전용 `결과_MD/`, 이력/요약 전용 `변환리포트/` 폴더 완전 분리 관리.
6. **Windows 콘솔 & 한글 인코딩 불변 원칙 준수**:
   - 배치 파일(`*.bat`) 100% 순수 ASCII 래퍼 적용으로 cmd.exe 한글 버그 원천 방지.
   - 드래그 앤 드롭 경로 정규화 및 Python 표준 출력 UTF-8 강제 적용.

---

## 2. 폴더 및 모듈 구조

```text
d:\백업\utility\파일형식변환기_MD\
├── run_converter.bat          # [ASCII] CLI 런처 (탐색기 드래그 앤 드롭 지원)
├── run_gui.bat                # [ASCII] GUI 런처
├── cli.py                     # 커맨드라인 일괄 변환기
├── gui.py                     # Tkinter 기반 직관적인 변환 GUI
├── requirements.txt           # Python 라이브러리 목록 (markitdown[pdf] 포함)
├── README.md                  # 본 매뉴얼
├── core/                      # 공통 코어 엔진
│   ├── __init__.py
│   ├── config.py              # 경로 설정 및 지원 확장자
│   ├── text_cleaner.py        # 인코딩 자동감지, 표 마크다운 변환, 텍스트 정제
│   ├── text_postprocessor.py  # 가독성 정제 (줄바꿈 결합, 어절 복원, 페이지구분 제거)
│   ├── com_session.py         # Office/HWP COM 세션 풀 & 한글 보안 팝업 자동 승인
│   ├── metadata_extractor.py  # 제목, 범주, 키워드, 개체명, 요약 자동 추출
│   ├── frontmatter_builder.py # OKF 규격 YAML Front Matter 조립 및 유효성 검증
│   ├── markdown_formatter.py  # Markdown 본문 표준 템플릿 조립기
│   ├── batch_runner.py        # 배치 실행 엔진, 중복 파일명 회피, 결과 보고서 관리
│   └── ocr_worker.py          # RapidOCR(ONNX 기반 PP-OCR) 독립 워커 프로세스
├── adapters/                  # 포맷별 독립 변환 어댑터
│   ├── __init__.py            # 어댑터 레지스트리 및 엔진 라우터 (auto, markitdown, native)
│   ├── base.py                # BaseAdapter 인터페이스 & ConversionResult
│   ├── markitdown_adapter.py  # Microsoft MarkItDown 어댑터 (.docx, .pptx, .xlsx, .pdf 등)
│   ├── docx_adapter.py        # Word (.docx, .doc, .rtf)
│   ├── hwp_adapter.py         # 한글 (.hwp, .hwpx)
│   ├── ppt_adapter.py         # PowerPoint (.pptx, .ppt)
│   ├── excel_adapter.py       # Excel (.xlsx, .xls)
│   ├── pdf_adapter.py         # PDF (PyMuPDF 텍스트 및 스캔 OCR fallback)
│   ├── ocr_adapter.py         # 이미지 OCR (.png, .jpg 등)
│   ├── text_adapter.py        # 텍스트 (.txt, .md)
│   └── epub_adapter.py        # 전자책 (.epub)
├── tests/                     # 자체 검증 및 테스트
│   ├── __init__.py
│   └── test_converter.py      # E2E 및 단위 테스트 스위트 (7개 항목 무결성 검증)
├── 결과_MD/                   # 순수 변환 결과 Markdown 파일 전용 저장소
└── 변환리포트/                 # 변환 실행 보고서 및 이력 전용 저장소
```

---

## 3. 사용 방법

### 3.1 GUI 모드 (가장 간편한 방법)
1. `run_gui.bat` 파일을 더블 클릭하여 실행합니다.
2. 변환할 파일 또는 폴더를 창으로 끌어다 놓거나(드래그 앤 드롭), **[+ 파일 추가...]** 또는 **[+ 폴더 추가...]** 버튼을 클릭합니다.
3. 변환 옵션을 설정합니다:
   - **엔진 선택**: auto (스마트 자동 기본) / markitdown / native
   - **옵션 선택**: `하위 폴더 포함`, `덮어쓰기`, `텍스트 없는 PDF/스캔 제외 (OCR 생략)`
4. 출력 폴더를 지정한 후 **[변환 시작]** 버튼을 누릅니다.
5. 변환 완료 후 **[결과 폴더 열기]** 버튼을 눌러 생성된 `.md` 파일들을 확인합니다.

### 3.2 CLI 모드 (커맨드라인 & 드래그 앤 드롭)
1. **탐색기 드래그 앤 드롭**:
   - 변환할 파일이나 폴더를 마우스로 잡고 `run_converter.bat` 아이콘 위에 끌어다 놓으면 즉시 변환됩니다.
2. **명령줄 실행**:
   ```cmd
   # 특정 폴더 일괄 변환 (스마트 자동 엔진 기본)
   python -X utf8 cli.py "D:\문서\보고서"

   # 텍스트 레이어가 없는 스캔 PDF 및 이미지 제외 (OCR 생략)
   python -X utf8 cli.py "D:\문서\보고서" --skip-scanned

   # MarkItDown 엔진 우선 지정 변환
   python -X utf8 cli.py "D:\문서\보고서" --engine markitdown

   # 결과 폴더 지정 및 기존 파일 덮어쓰기
   python -X utf8 cli.py "D:\문서\보고서" -o "D:\결과_MD" --overwrite

   # 자체 검증 테스트 실행 (전체 무결성 테스트)
   python -X utf8 cli.py --selftest
   ```

---

## 4. 생성되는 Markdown 사양

### 4.1 YAML Front Matter 스키마 예시
```yaml
---
type: "document"
id: "doc_20261007_a1b2c3d4"
title: "2026년 3분기 사업 결과 보고서"
description: "3분기 주요 사업 추진 실적 및 예산 집행 현황 보고"
source_file: "2026년_3분기_보고서.docx"
source_path: "D:/문서/2026년_3분기_보고서.docx"
source_type: "docx"
conversion_method: "native"
converted_from: ".docx"
output_file: "2026년_3분기_보고서.md"
language: "ko"
created_at: "2026-10-07T10:00:00Z"
updated_at: "2026-10-07T10:00:00Z"
doc_category: "보고서"
topics:
  - "사업추진"
  - "예산집행"
keywords:
  - "사업추진"
  - "예산집행"
  - "매출액"
  - "영업이익"
entities:
  - "한국무역정보통신"
related_documents: []
ocr_required: false
ocr_confidence: "unknown"
review_required: false
status: "success"
errors: []
---
```

---

## 5. 오류 및 예외 처리
- **암호 걸린 문서**: 변환을 중단하고 상태를 `password_protected`로 기록하며 안내 문서를 남깁니다.
- **손상된 파일**: `corrupted_file` 상태로 기록됩니다.
- **저품질 OCR**: `partial` 상태 및 `review_required: true`로 기록되어 추후 원본 대조가 가능합니다.
- 오류가 발생해도 나머지 파일의 배치는 중단 없이 계속 진행되며, 결과 폴더의 `_conversion_report.json`과 `_conversion_summary.md`에 모든 내역이 집계됩니다.

---

## 6. USB 이동식 배포 및 경로 무결성 보장 (Portable USB Deployment)

본 프로그램은 USB 메모리 또는 외장 하드 드라이브에 담겨 서로 다른 PC 환경(드라이브 문자 변경: `D:` -> `E:`, `F:`, `Z:` 등)에 배포되더라도 시스템이 깨지지 않도록 다음과 같은 전방위적 보완 조치가 적용되어 있습니다:

1. **드라이브 문자 독립적 경로 매칭 (`core/batch_runner.py`)**:
   - 기존에 변환된 마크다운의 `source_path`와 현재 대상 파일을 비교할 때, 드라이브 문자를 제외한 경로를 스마트 비교(`is_same_source`)합니다.
   - PC 이동으로 드라이브 문자가 달라져도 동일 파일로 정확히 감지되어 불필요한 `파일명 (1).md` 중복 생성을 방지하고 건너뛰기/덮어쓰기 정책을 준수합니다.
   - Front Matter에 `source_rel_path` 상대 경로를 함께 기록하여 USB 내에서 언제든 원본을 추적할 수 있습니다.

2. **포터블 환경 다중 Python 자동 감지 런처 (`run_converter.bat`, `run_gui.bat`)**:
   - 100% 순수 ASCII 래퍼 및 `pushd "%~dp0"`를 적용하여 UNC 네트워크 경로 및 cmd.exe 한글 인코딩 버그를 원천 차단했습니다.
   - 대상 PC에 Python이 PATH에 없더라도:
     - USB 내 로컬 가상환경/임베디드 파이썬 (`venv`, `.venv`, `python`, `Python3*`) 1순위 자동 탐색
     - 시스템 `python` 2순위 탐색
     - Windows Python Launcher (`py -3` / `pyw -3`) 3순위 자동 탐색
     - LocalAppData 사용자 설치 경로 4순위 자동 탐색
     - Python 미설치 시 즉시 꺼지지 않고 명확한 안내 후 대기(`pause`)합니다.

3. **다중 엔진 OCR 하이브리드 지원 및 자립형 구동 (`core/ocr_worker.py`)**:
   - 무거운 외부 라이브러리 없이도 Windows 10/11 시스템 내장 `winrt` (Windows Media OCR) 네이티브 지원으로 USB만 꽂으면 즉시 고속 한글/영문 OCR 구동 가능.
   - `RapidOCR`(ONNX) 및 `PaddleOCR`와의 멀티 호환으로 다양한 가상환경에 유연하게 대응합니다.

4. **유니코드 NFC 정규화 및 GUI 동적 폴백 (`core/batch_runner.py`, `gui.py`)**:
   - Mac/Windows 간 파일 복사 시 발생하는 한글 자모 분리 현상(NFD)을 NFC로 자동 정규화합니다.
   - 이전 PC의 드라이브 경로가 남아있더라도 접근 불가 시 현재 USB의 `APP_DIR / "결과_MD"`로 자동 안전 전환됩니다.

