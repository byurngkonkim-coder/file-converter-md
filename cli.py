# -*- coding: utf-8 -*-
"""cli.py - 통합 문서 변환기 커맨드라인 인터페이스 (CLI).

사용 예:
    python cli.py <파일또는폴더...>
    python cli.py "D:\\문서\\보고서" -o "D:\\결과_MD" --overwrite
    python cli.py --selftest
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Windows 콘솔 인코딩 불변 원칙: UTF-8 재설정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 현재 작업 디렉토리를 모듈 검색 경로에 추가
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from core.batch_runner import collect_files, convert_batch, normalize_path
from core.config import DEFAULT_OUT_DIR, DEFAULT_REPORT_DIR


def run_selftest() -> int:
    """기본 모듈 무결성 및 내장 테스트를 수행합니다."""
    print("=== 통합 문서 변환기 셀프 테스트 시작 ===")
    from tests.test_converter import run_all_tests
    return run_all_tests()


def main():
    parser = argparse.ArgumentParser(
        description="통합 문서 -> YAML Front Matter 포함 OKF Markdown 일괄 변환기"
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="변환할 파일 또는 폴더 경로 (여러 개 지정 가능, 드래그 앤 드롭 지원)",
    )
    parser.add_argument(
        "-o", "--out",
        default=str(DEFAULT_OUT_DIR),
        help=f"순수 변환 Markdown 저장 디렉토리 (기본값: {DEFAULT_OUT_DIR.name})",
    )
    parser.add_argument(
        "--report-dir",
        default=str(DEFAULT_REPORT_DIR),
        help=f"변환 리포트 및 이력 저장 디렉토리 (기본값: {DEFAULT_REPORT_DIR.name})",
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        default=True,
        help="하위 폴더를 재귀적으로 탐색 (기본값: True)",
    )
    parser.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        help="하위 폴더는 탐색하지 않음",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="이미 변환된 파일이 있어도 덮어쓰기 (기본값: 건너뛰기)",
    )
    parser.add_argument(
        "--engine",
        choices=["auto", "markitdown", "native"],
        default="auto",
        help="변환 엔진 선택 (auto: 스마트 자동, markitdown: Microsoft MarkItDown 최우선, native: 기존 내장 어댑터) [기본값: auto]",
    )
    parser.add_argument(
        "--skip-scanned",
        action="store_true",
        default=False,
        help="텍스트 레이어가 없는 스캔 PDF 및 이미지 문서 변환 제외 (OCR 생략)",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="단위 테스트 및 시스템 무결성 검증 실행",
    )

    args = parser.parse_args()

    if args.selftest:
        sys.exit(run_selftest())

    if not args.inputs:
        parser.print_help()
        print("\n[알림] 변환할 파일 또는 폴더 경로를 지정해 주십시오.")
        sys.exit(1)

    # 경로 정규화 및 파일 수집
    norm_inputs = [normalize_path(i) for i in args.inputs]
    out_dir = normalize_path(args.out)
    report_dir = normalize_path(args.report_dir)

    print(f"[*] 대상 경로 탐색 중... (입력: {len(norm_inputs)}개)")
    files = collect_files(norm_inputs, recursive=args.recursive)

    if not files:
        print("[!] 변환 가능한 지원 문서 파일을 찾지 못했습니다.")
        sys.exit(0)

    print(f"[*] 총 {len(files)}개 변환 대상 파일 발견:")
    for f in files[:10]:
        print(f"  - {f.name} ({f.suffix})")
    if len(files) > 10:
        print(f"  ... 외 {len(files) - 10}개 파일")

    print(f"[*] 결과 Markdown 디렉토리: {out_dir}")
    print(f"[*] 변환 리포트 디렉토리: {report_dir}")
    print(f"[*] 변환 엔진: {args.engine}")
    print(f"[*] 기존 파일 덮어쓰기: {'예' if args.overwrite else '건너뛰기'}")
    print(f"[*] 텍스트 없는 PDF/스캔 제외: {'예 (OCR 생략)' if args.skip_scanned else '아니오 (OCR 수행)'}")
    print("-" * 60)

    # 일괄 변환 실행
    convert_batch(
        files,
        out_dir=out_dir,
        report_dir=report_dir,
        overwrite=args.overwrite,
        engine=args.engine,
        skip_scanned=args.skip_scanned,
    )


if __name__ == "__main__":
    main()
