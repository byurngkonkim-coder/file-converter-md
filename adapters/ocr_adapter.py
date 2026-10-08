# -*- coding: utf-8 -*-
"""adapters/ocr_adapter.py - 이미지 및 스캔 문서 OCR 변환 어댑터.

- 지원 포맷: .png, .jpg, .jpeg, .bmp, .tiff, .tif, .webp
- 독립적인 OCR Worker 프로세스를 활용하여 PaddleOCR 실행
- 한글 및 영문 텍스트 인식, OCR 신뢰도 계산 및 검토 플래그 산출
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from adapters.base import BaseAdapter, ConversionResult
from core.config import get_ocr_python
from core.text_cleaner import tidy

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class OcrAdapter(BaseAdapter):
    """이미지 파일 OCR 변환기."""

    def can_handle(self, ext: str) -> bool:
        return ext.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}

    def perform_ocr_batch(self, image_paths: list[Path], lang: str = "korean") -> list[dict]:
        """이미지 경로 목록을 OCR Worker 로 넘겨 텍스트와 신뢰도를 수집합니다."""
        worker_script = Path(__file__).resolve().parent.parent / "core" / "ocr_worker.py"
        py_exe = get_ocr_python()

        # 경로 목록 임시 JSON 작성
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as f:
            json_file = f.name
            json.dump([str(p.resolve()) for p in image_paths], f, ensure_ascii=False)

        cmd = [
            py_exe,
            "-X", "utf8",
            str(worker_script),
            "--json-input", json_file,
            "--lang", lang,
        ]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            output = res.stdout.strip()
            # JSON 부분만 파싱 (앞뒤 다른 로그 메시지가 있을 수 있으므로 방어적 추출)
            json_start = output.find("[")
            json_end = output.rfind("]")
            if json_start != -1 and json_end != -1:
                json_str = output[json_start : json_end + 1]
                data = json.loads(json_str)
            else:
                data = json.loads(output)
            return data
        except Exception as e:
            err_msg = f"OCR 처리 중 오류 발생: {e}"
            return [{"error": err_msg, "text": "", "avg_score": 0.0, "confidence": "unknown"}]
        finally:
            if Path(json_file).exists():
                try:
                    Path(json_file).unlink()
                except Exception:
                    pass

    def convert(self, path: Path, session: Any = None) -> ConversionResult:
        res_list = self.perform_ocr_batch([path])
        if not res_list:
            raise RuntimeError("OCR 결과를 수신하지 못했습니다.")

        info = res_list[0]
        if info.get("error"):
            return ConversionResult(
                body=f"> [!WARNING]\n> OCR 처리 실패: {info['error']}\n",
                conversion_method="ocr",
                ocr_required=True,
                ocr_confidence="unknown",
                review_required=True,
                status="failed",
                errors=[info["error"]],
            )

        lines = info.get("lines", [])
        raw_text = info.get("text", "").strip()
        conf = info.get("confidence", "unknown")
        avg_score = info.get("avg_score", 0.0)

        if lines:
            from PIL import Image
            from adapters.pdf_adapter import reconstruct_ocr_page
            try:
                with Image.open(str(path)) as im:
                    im_w, im_h = im.size
                text = reconstruct_ocr_page(lines, im_w, im_h)
            except Exception:
                text = raw_text
        else:
            text = raw_text

        from core.text_postprocessor import postprocess_markdown
        final_body = postprocess_markdown(tidy(text if text else "인식된 텍스트가 없습니다."))

        status = "success" if text else "partial"
        review_required = (conf in ("low", "unknown")) or (not text)

        return ConversionResult(
            body=final_body,
            pages=[(1, text)],
            conversion_method="ocr",
            ocr_required=True,
            ocr_confidence=conf,
            review_required=review_required,
            status=status,
            unrecognized_areas="저신뢰도 구간 발생" if review_required else "없음",
            action_items="원문 이미지와 대조 검토 필요" if review_required else "없음",
            extra_metadata={"ocr_avg_score": avg_score},
        )
