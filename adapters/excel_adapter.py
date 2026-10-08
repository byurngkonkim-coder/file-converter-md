# -*- coding: utf-8 -*-
"""adapters/excel_adapter.py - Excel (.xlsx, .xlsm, .xls) 변환 어댑터.

- .xlsx: openpyxl 네이티브 파싱
- .xls / .xlsm: Excel COM 자동화 (UsedRange.Value 일괄 튜플 고속 추출)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from adapters.base import BaseAdapter, ConversionResult
from core.text_cleaner import rows_to_table, tidy

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class ExcelAdapter(BaseAdapter):
    """Excel 스프레드시트 변환기 (어휘장, 회화집 및 대규모 데이터의 콘텐츠 텍스트 평탄화 지원)."""

    def can_handle(self, ext: str) -> bool:
        return ext.lower() in {".xlsx", ".xlsm", ".xls"}

    def _format_sheet_content(self, sheetname: str, raw_rows: list[Sequence[Any]]) -> str:
        """시트의 2차원 데이터를 마크다운 콘텐츠 생성 및 활용에 최적화된 텍스트로 변환합니다."""
        if not raw_rows:
            return ""

        # 문자열 정규화 (None 제거, 줄바꿈은 공백 정리)
        str_rows = []
        for r in raw_rows:
            cleaned_row = [
                str(v).strip().replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
                if v is not None else ""
                for v in r
            ]
            if any(cleaned_row):
                str_rows.append(cleaned_row)

        if not str_rows:
            return ""

        # 1. 완전히 비어있는 열(column) 제거
        max_cols = max(len(r) for r in str_rows)
        active_cols = []
        for c_idx in range(max_cols):
            if any(c_idx < len(r) and r[c_idx] for r in str_rows):
                active_cols.append(c_idx)

        if not active_cols:
            return ""

        filtered_rows = []
        for r in str_rows:
            row_vals = [r[c_idx] if c_idx < len(r) else "" for c_idx in active_cols]
            if any(row_vals):
                filtered_rows.append(row_vals)

        cols_count = len(active_cols)
        lines = [f"### 시트: {sheetname} (총 {len(filtered_rows)}행)\n"]

        # 2. 케이스 A: 2열 단어장/표현집 (예: [영어 표현, 한국어 뜻])
        if cols_count == 2:
            for r_idx, r in enumerate(filtered_rows):
                col0, col1 = r[0].strip(), r[1].strip()
                if r_idx == 0 and any(k in col0.lower() for k in ["표현", "단어", "english", "korean", "phrase", "word"]):
                    lines.append(f"**[분류 헤더: {col0} - {col1}]**\n")
                else:
                    if col0 and col1:
                        lines.append(f"• **{col0}**: {col1}")
                    elif col0:
                        lines.append(f"• {col0}")
                    elif col1:
                        lines.append(f"  {col1}")
            return "\n".join(lines)

        # 3. 케이스 B: 3~5열 사전/예문/회화집 (헤더가 존재하고 예문/해석 중심)
        first_row_txt = " ".join(filtered_rows[0]).lower()
        has_header = any(
            k in first_row_txt
            for k in ["뜻", "의미", "예문", "해석", "meaning", "example", "keyword", "단어", "표현", "구분", "설명"]
        )

        # 셀에 30자 이상의 긴 예문이나 서술문이 포함되어 있는지 확인
        has_long_sentences = any(
            len(c) > 30 for r in filtered_rows[:20] for c in r
        )

        if has_header and has_long_sentences and len(filtered_rows) > 1:
            headers = filtered_rows[0]
            data_rows = filtered_rows[1:]

            for idx, row in enumerate(data_rows, start=1):
                main_title = row[0] if row[0] else f"항목 {idx}"
                lines.append(f"#### {idx}. {main_title}")
                for h_idx in range(1, len(headers)):
                    h_name = headers[h_idx] if h_idx < len(headers) and headers[h_idx] else f"항목 {h_idx+1}"
                    val = row[h_idx] if h_idx < len(row) else ""
                    if val:
                        lines.append(f"- **{h_name}**: {val}")
                lines.append("")
            return "\n".join(lines)

        # 4. 케이스 C: 짧은 정형 통계/코드 표 (30행 이하, 셀 길이 25자 이하)
        is_short_grid = (
            len(filtered_rows) <= 30
            and all(len(c) <= 25 for r in filtered_rows for c in r)
        )
        if is_short_grid:
            t_md = rows_to_table(filtered_rows, force_grid=True)
            if t_md:
                lines.append(t_md)
                return "\n".join(lines)

        # 5. 케이스 D: 일반 다열 데이터 (메모장 붙여넣기 스타일 탭/구분선 분리)
        for r in filtered_rows:
            non_empty = [c for c in r if c]
            if non_empty:
                lines.append("  |  ".join(non_empty))

        return "\n".join(lines)

    def _convert_xlsx_native(self, path: Path) -> tuple[str, str]:
        """openpyxl 을 활용하여 시트별 콘텐츠를 추출합니다."""
        import openpyxl

        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        sections = []
        for sheetname in wb.sheetnames:
            ws = wb[sheetname]
            rows = []
            for row in ws.iter_rows(values_only=True):
                if any(v is not None for v in row):
                    rows.append(row)
            if rows:
                s_text = self._format_sheet_content(sheetname, rows)
                if s_text:
                    sections.append(s_text)
        wb.close()
        full_text = tidy("\n\n".join(sections))
        return full_text, ""

    def _convert_via_com(self, path: Path, session: Any) -> tuple[str, str]:
        """Excel COM 자동화를 통해 UsedRange.Value 를 일괄 추출하여 콘텐츠로 변환합니다."""
        app = session.get("excel")
        abs_path = str(path.resolve())
        wb = app.Workbooks.Open(abs_path, ReadOnly=True, UpdateLinks=0, AddToMru=False)
        sections = []
        try:
            for ws in wb.Worksheets:
                used = ws.UsedRange
                values = used.Value
                if values is None:
                    continue
                rows = (
                    list(values)
                    if isinstance(values, tuple) and isinstance(values[0], tuple)
                    else ([values] if not isinstance(values, tuple) else [list(values)])
                )
                s_text = self._format_sheet_content(ws.Name, rows)
                if s_text:
                    sections.append(s_text)
        finally:
            wb.Close(False)

        full_text = tidy("\n\n".join(sections))
        return full_text, ""

    def convert(self, path: Path, session: Any = None) -> ConversionResult:
        ext = path.suffix.lower()
        method = "native"

        if ext == ".xlsx":
            try:
                body, tables = self._convert_xlsx_native(path)
            except Exception:
                if session is not None:
                    body, tables = self._convert_via_com(path, session)
                    method = "converted"
                else:
                    raise
        else:
            # .xls 또는 .xlsm
            if session is None:
                raise RuntimeError(".xls 변환을 위해서는 Excel COM 세션이 필요합니다.")
            body, tables = self._convert_via_com(path, session)
            method = "converted"

        if not body.strip():
            raise RuntimeError("스프레드시트에서 유효한 데이터를 추출하지 못했습니다 (빈 시트).")

        return ConversionResult(
            body=body,
            tables=tables,
            conversion_method=method,
            status="success",
        )
