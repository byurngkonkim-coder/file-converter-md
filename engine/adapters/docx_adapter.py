# -*- coding: utf-8 -*-
"""adapters/docx_adapter.py - Word (.docx, .doc, .rtf) 변환 어댑터.

- .docx: mammoth (HTML) -> markdownify (Office 없이도 고품질 변환)
- .doc, .rtf: Word COM으로 .docx 임시 저장 후 위와 동일 처리
"""
from __future__ import annotations

import sys
from pathlib import Path

from adapters.base import BaseAdapter, ConversionResult
from core.text_cleaner import html_to_md, tidy

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class DocxAdapter(BaseAdapter):
    """Word 및 RTF 문서 변환기 (중첩 표 및 레이아웃 표 완벽 언롤링 지원)."""

    def can_handle(self, ext: str) -> bool:
        return ext.lower() in {".docx", ".doc", ".rtf"}

    def _is_layout_table(self, t_obj) -> bool:
        """표가 2차원 데이터 표가 아니라 본문 레이아웃 또는 텍스트 박스형 표인지 지능적으로 판별합니다."""
        if not t_obj.rows:
            return True
        num_rows = len(t_obj.rows)
        max_cols = max(len(row.cells) for row in t_obj.rows) if t_obj.rows else 0

        # 1. 1x1 표 또는 1열 표는 레이아웃 텍스트 박스
        if num_rows == 1 and max_cols == 1:
            return True
        if max_cols <= 1:
            return True

        # 2. 셀 내부에 중첩 테이블이 존재하는 경우
        for row in t_obj.rows:
            for cell in row.cells:
                if len(cell.tables) > 0:
                    return True

        # 3. 셀 내부 텍스트가 여러 문단이거나 본문 서술문(평균 50자 이상)인 경우
        total_cells = sum(len(row.cells) for row in t_obj.rows)
        total_paras = sum(len(cell.paragraphs) for row in t_obj.rows for cell in row.cells)
        total_chars = sum(len(cell.text.strip()) for row in t_obj.rows for cell in row.cells)

        if total_cells > 0:
            if total_paras > total_cells:  # 셀당 1문단 초과
                return True
            if (total_chars / total_cells) > 50:  # 셀당 평균 50자 이상 본문 서술문
                return True

        return False

    def _convert_docx_flow(self, path: Path) -> str:
        """python-docx XML 트리를 순회하여 단락과 표를 자연스러운 문서 순서대로 추출합니다.

        레이아웃용 표 및 중첩 표는 온전한 본문 단락으로 평탄화(Unroll)하여 텍스트 누락을 원천 방지합니다.
        """
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph
        from core.text_cleaner import rows_to_table

        doc = docx.Document(path)
        parts: list[str] = []

        def _process_element(elem, parent_doc):
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "p":
                p_obj = Paragraph(elem, parent_doc)
                text = p_obj.text.strip()
                if not text:
                    return
                style_name = (p_obj.style.name.lower() if p_obj.style else "")
                if "heading 1" in style_name:
                    parts.append(f"# {text}")
                elif "heading 2" in style_name:
                    parts.append(f"## {text}")
                elif "heading 3" in style_name or "heading" in style_name:
                    parts.append(f"### {text}")
                else:
                    parts.append(text)
            elif tag == "tbl":
                t_obj = Table(elem, parent_doc)
                _process_table(t_obj, parent_doc)

        def _process_table(t_obj, parent_doc):
            if self._is_layout_table(t_obj):
                # 레이아웃 표: 셀 내부의 모든 단락과 중첩 표를 순서대로 재귀 언롤링
                for row in t_obj.rows:
                    for cell in row.cells:
                        for child in cell._tc:
                            _process_element(child, parent_doc)
            else:
                # 진짜 데이터 표: 마크다운 2차원 표로 변환
                rows_data = []
                for row in t_obj.rows:
                    row_cells = [cell.text.strip() for cell in row.cells]
                    rows_data.append(row_cells)
                t_md = rows_to_table(rows_data)
                if t_md:
                    parts.append(t_md)

        for child in doc._body._element:
            _process_element(child, doc)

        return tidy("\n\n".join(parts))

    def _convert_docx_mammoth(self, path: Path) -> str:
        """mammoth 를 활용한 HTML -> Markdown fallback 변환."""
        import mammoth

        with open(path, "rb") as f:
            res = mammoth.convert_to_html(
                f,
                convert_image=mammoth.images.img_element(lambda _i: {"src": ""}),
            )
            html = res.value
        return html_to_md(html)

    def convert(self, path: Path, session: Any = None) -> ConversionResult:
        ext = path.suffix.lower()
        method = "native"

        if ext == ".docx":
            try:
                md_text = self._convert_docx_flow(path)
            except Exception:
                md_text = self._convert_docx_mammoth(path)
        else:
            # .doc 또는 .rtf: Word COM 필요
            if session is None:
                raise RuntimeError("구버전 Word(.doc, .rtf) 변환에는 COM 세션이 필요합니다.")
            method = "converted"
            app = session.get("word")
            doc = app.Documents.Open(
                str(path.resolve()),
                ReadOnly=True,
                AddToRecentFiles=False,
                ConfirmConversions=False,
                Visible=False,
            )
            try:
                tmp_docx = session.scratch(path.stem + ".docx")
                doc.SaveAs2(str(tmp_docx.resolve()), FileFormat=16)  # wdFormatDocumentDefault
            finally:
                doc.Close(0)  # wdDoNotSaveChanges

            try:
                md_text = self._convert_docx_flow(tmp_docx)
            except Exception:
                md_text = self._convert_docx_mammoth(tmp_docx)

        if not md_text.strip():
            raise RuntimeError("Word 문서에서 내용을 추출하지 못했습니다 (빈 문서).")

        return ConversionResult(
            body=md_text,
            conversion_method=method,
            status="success",
        )
