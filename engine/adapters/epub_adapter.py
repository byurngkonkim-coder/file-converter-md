# -*- coding: utf-8 -*-
"""adapters/epub_adapter.py - 전자책 (.epub) 문서 변환 어댑터.

EPUB (ZIP) 내부의 OPF spine(읽는 순서)대로 XHTML 을 추출하여 Markdown 으로 변환합니다.
"""
from __future__ import annotations

import posixpath
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from adapters.base import BaseAdapter, ConversionResult
from core.text_cleaner import html_to_md, tidy

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class EpubAdapter(BaseAdapter):
    """EPUB 전자책 파일 변환기."""

    def can_handle(self, ext: str) -> bool:
        return ext.lower() == ".epub"

    def convert(self, path: Path, session: Any = None) -> ConversionResult:
        with zipfile.ZipFile(path) as z:
            # 1. container.xml 에서 rootfile(.opf) 경로 파악
            tree = ET.fromstring(z.read("META-INF/container.xml"))
            ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
            rf = tree.find(".//c:rootfile", ns)
            if rf is None or not rf.attrib.get("full-path"):
                raise RuntimeError("유효한 EPUB rootfile 을 찾을 수 없습니다.")
            opf_path = rf.attrib["full-path"]
            opf_dir = posixpath.dirname(opf_path)

            # 2. opf 에서 manifest 와 spine 순서 추출
            opf = ET.fromstring(z.read(opf_path))
            pfx = opf.tag.split("}")[0] + "}" if "}" in opf.tag else ""
            manifest = {
                item.attrib["id"]: item.attrib["href"]
                for item in opf.findall(f".//{pfx}manifest/{pfx}item")
            }
            spine_ids = [
                item.attrib["idref"]
                for item in opf.findall(f".//{pfx}spine/{pfx}itemref")
            ]

            # 3. spine 순서대로 XHTML 추출 및 변환
            parts = []
            for item_id in spine_ids:
                href = manifest.get(item_id)
                if not href:
                    continue
                file_in_zip = posixpath.normpath(posixpath.join(opf_dir, href)) if opf_dir else href
                try:
                    raw_html = z.read(file_in_zip).decode("utf-8", errors="replace")
                    md_chunk = html_to_md(raw_html).strip()
                    if md_chunk:
                        parts.append(md_chunk)
                except KeyError:
                    continue

        body = tidy("\n\n---\n\n".join(parts))
        if not body.strip():
            raise RuntimeError("EPUB 에서 본문 내용을 추출하지 못했습니다.")

        return ConversionResult(
            body=body,
            conversion_method="native",
            status="success",
        )
