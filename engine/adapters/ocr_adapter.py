# -*- coding: utf-8 -*-
"""adapters/ocr_adapter.py - 이미지 및 스캔 문서 OCR 변환 어댑터.

- 지원 포맷: .png, .jpg, .jpeg, .bmp, .tiff, .tif, .webp
- 독립적인 OCR Worker 프로세스를 활용하여 RapidOCR(ONNX 기반 PP-OCR) 실행
- 한글 및 영문 텍스트 인식, OCR 신뢰도 계산 및 검토 플래그 산출
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from adapters.base import BaseAdapter, ConversionResult, ScannedDocumentSkipped
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
        # 1. 현재 프로세스에서 직접 실행 가능한 경우 프로세스 생성 없이 즉시 실행 (창 팝업 원천 차단 및 고속 처리)
        try:
            from core.ocr_worker import run_ocr_on_images
            import rapidocr
            return run_ocr_on_images([str(p.resolve()) for p in image_paths], lang=lang)
        except Exception:
            pass

        # 2. 독립 프로세스 실행 (후보 Python 순차 폴백 + 창 팝업 방지 플래그 적용)
        worker_script = Path(__file__).resolve().parent.parent / "core" / "ocr_worker.py"
        from core.config import get_ocr_python_candidates, get_safe_temp_dir

        safe_temp = get_safe_temp_dir()
        temp_json_path = safe_temp / f"ocr_batch_{os.getpid()}_{id(image_paths)}.json"
        with open(temp_json_path, "w", encoding="utf-8") as f:
            json.dump([str(p.resolve()) for p in image_paths], f, ensure_ascii=False)
        json_file = str(temp_json_path)

        # 사용 가능한 후보 Python 목록 준비
        cands = [str(c.resolve()) for c in get_ocr_python_candidates() if c and c.exists()]
        if sys.executable not in cands:
            cands.append(sys.executable)

        run_kwargs: dict[str, Any] = {
            "capture_output": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": 60,
        }

        # Windows 환경에서 콘솔 창(검은색 CMD 팝업창) 완벽 차단
        if sys.platform == "win32":
            run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            run_kwargs["startupinfo"] = startupinfo

        last_error = None
        try:
            for py_exe in cands:
                cmd = [
                    py_exe,
                    "-X", "utf8",
                    str(worker_script),
                    "--json-input", json_file,
                    "--lang", lang,
                ]
                try:
                    res = subprocess.run(cmd, **run_kwargs)
                    if res.returncode != 0:
                        last_error = f"Exit code {res.returncode}: {res.stderr.strip()[:200]}"
                        continue

                    output = res.stdout.strip()
                    json_start = output.find("[")
                    json_end = output.rfind("]")
                    if json_start != -1 and json_end != -1:
                        json_str = output[json_start : json_end + 1]
                        data = json.loads(json_str)
                    else:
                        data = json.loads(output)

                    # 결과 내에 치명적 에러가 없으면 채택
                    if data and not all(d.get("error") for d in data):
                        return data
                    elif data and data[0].get("error"):
                        last_error = data[0].get("error")
                        continue
                    return data
                except Exception as e:
                    last_error = str(e)
                    continue

            return [{"error": f"OCR 처리 실패 (모든 Python 후보 시도 완료): {last_error}", "text": "", "avg_score": 0.0, "confidence": "unknown"}]
        finally:
            if Path(json_file).exists():
                try:
                    Path(json_file).unlink()
                except Exception:
                    pass

    def convert(self, path: Path, session: Any = None, skip_scanned: bool = False, **kwargs) -> ConversionResult:
        if skip_scanned:
            raise ScannedDocumentSkipped(f"스캔/이미지 문서 ({path.name}) - 변환 제외")

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
