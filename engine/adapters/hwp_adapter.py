# -*- coding: utf-8 -*-
"""adapters/hwp_adapter.py - 한글 (.hwp, .hwpx) 문서 변환 어댑터.

- 한글 COM 자동화를 통해 HTML 변환 후 markdownify 로 Markdown 생성.
- .hwpx 의 경우 COM 없이도 내부 XML 파싱을 통한 Fallback 추출 지원.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from adapters.base import BaseAdapter, ConversionResult
from core.text_cleaner import html_to_md, read_text, tidy

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class HwpAdapter(BaseAdapter):
    """한글 문서(.hwp, .hwpx) 변환기."""

    def can_handle(self, ext: str) -> bool:
        return ext.lower() in {".hwp", ".hwpx"}

    def _convert_hwpx_native(self, path: Path) -> str:
        """한글 오피스 없이 .hwpx(ZIP/XML 구조) 내부 섹션을 직접 파싱합니다."""
        parts = []
        with zipfile.ZipFile(path, "r") as z:
            # Contents/section0.xml 등 섹션 파일 탐색
            section_files = sorted(
                [n for n in z.namelist() if n.startswith("Contents/section") and n.endswith(".xml")]
            )
            for sname in section_files:
                xml_data = z.read(sname)
                root = ET.fromstring(xml_data)
                # <hp:t> 태그(텍스트) 추출
                lines = []
                for p_elem in root.iter():
                    if p_elem.tag.endswith("}p"):
                        p_texts = [t.text for t in p_elem.iter() if t.tag.endswith("}t") and t.text]
                        if p_texts:
                            lines.append("".join(p_texts))
                if lines:
                    parts.append("\n\n".join(lines))

        return tidy("\n\n".join(parts))

    def _convert_via_com(self, path: Path, session: Any) -> str:
        """한글 COM 자동화를 통해 HTML 로 저장한 후 변환합니다."""
        hwp = session.get("hwp")
        tmp_html = session.scratch(path.stem + ".html")

        # 절대경로 필수
        abs_path = str(path.resolve())
        # 포맷 "" 로 두어야 한글 3.0 ~ 2024 등 자동 감지
        if hwp.Open(abs_path, "", "") is False:
            raise RuntimeError(f"한글 파일 열기 실패: {path.name}")

        try:
            hwp.SaveAs(str(tmp_html.resolve()), "HTML", "")
        finally:
            hwp.Clear(1)  # 변경사항 저장 묻지 않고 닫기

        html_content = read_text(tmp_html)
        return html_to_md(html_content)

    def convert(self, path: Path, session: Any = None) -> ConversionResult:
        ext = path.suffix.lower()
        method = "converted"

        # 1. HWP COM 시도
        if session is not None:
            try:
                md_text = self._convert_via_com(path, session)
                return ConversionResult(body=md_text, conversion_method=method, status="success")
            except Exception as e:
                # hwpx이고 COM 실패 시 네이티브 XML 파싱 시도
                if ext == ".hwpx":
                    pass
                else:
                    raise RuntimeError(f"한글 COM 변환 실패: {e}")

        # 2. hwpx 네이티브 fallback
        if ext == ".hwpx":
            md_text = self._convert_hwpx_native(path)
            method = "native"
            return ConversionResult(body=md_text, conversion_method=method, status="success")

        raise RuntimeError("HWP 변환을 위해서는 한글 프로그램(COM)이 필요합니다.")
