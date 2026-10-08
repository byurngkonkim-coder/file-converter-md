# -*- coding: utf-8 -*-
"""core/ocr_worker.py - RapidOCR(ONNX 기반 PP-OCR) 독립 실행 워커 스크립트.

- ONNX Runtime 기반 고성능 PP-OCR 경량 모델 단일화
- 복잡하고 무거운 PaddlePaddle/PaddleOCR 종속성 완전 배제
- 한글/영문 텍스트 라인 인식 및 신뢰도 점수 산출
"""
from __future__ import annotations

import argparse
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _to_float(v) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


class OcrEngineWorker:
    """ONNX Runtime 기반 RapidOCR 전용 실행 워커."""

    def __init__(self, lang: str = "korean"):
        self.lang = lang
        self._ocr = None

    def ensure_engine(self):
        if self._ocr is not None:
            return

        try:
            from rapidocr import RapidOCR
            self._ocr = RapidOCR()
        except Exception as e:
            raise RuntimeError(f"RapidOCR 엔진 초기화 실패 (rapidocr 및 onnxruntime 필요): {e}")

    def run_image(self, img_path: str) -> tuple[list[dict], float, str]:
        """이미지 1장 OCR -> (lines, avg_score, confidence_level)"""
        self.ensure_engine()
        lines: list[dict] = []

        out = self._ocr(img_path)
        if out is not None and getattr(out, "txts", None):
            txts = out.txts or ()
            scores = out.scores or ()
            boxes = getattr(out, "boxes", None)
            for idx, text in enumerate(txts):
                if not text or not str(text).strip():
                    continue
                score = _to_float(scores[idx]) if idx < len(scores) else 0.0
                bbox = [0.0, 0.0, 0.0, 0.0]
                if boxes is not None and idx < len(boxes):
                    raw_b = boxes[idx]
                    if hasattr(raw_b, "tolist"):
                        raw_b = raw_b.tolist()
                    if isinstance(raw_b, (list, tuple)) and len(raw_b) >= 4 and isinstance(raw_b[0], (list, tuple)):
                        x0 = min(pt[0] for pt in raw_b)
                        y0 = min(pt[1] for pt in raw_b)
                        x1 = max(pt[0] for pt in raw_b)
                        y1 = max(pt[1] for pt in raw_b)
                        bbox = [round(float(x0), 1), round(float(y0), 1), round(float(x1), 1), round(float(y1), 1)]
                    elif isinstance(raw_b, (list, tuple)) and len(raw_b) >= 4:
                        bbox = [round(float(v), 1) for v in raw_b[:4]]
                lines.append({
                    "text": str(text).strip(),
                    "score": score,
                    "box": bbox,
                })

        scores = [l["score"] for l in lines if l.get("score", 0) > 0]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        conf = "high" if avg_score >= 0.85 else ("medium" if avg_score >= 0.65 else "low")
        if not lines:
            conf = "unknown"

        return lines, avg_score, conf


def run_ocr_on_images(image_paths: list[str], lang: str = "korean") -> list[dict]:
    results = []
    worker = None
    try:
        worker = OcrEngineWorker(lang=lang)
    except Exception as e:
        return [{"error": f"OCR 엔진 초기화 실패: {e}", "lines": [], "confidence": "unknown"}]

    for img_path in image_paths:
        try:
            lines, avg_score, conf = worker.run_image(img_path)
            results.append({
                "path": img_path,
                "text": "\n".join([l["text"] for l in lines]),
                "lines": lines,
                "avg_score": round(avg_score, 4),
                "confidence": conf,
                "line_count": len(lines),
                "error": None,
            })
        except Exception as e:
            results.append({
                "path": img_path,
                "text": "",
                "avg_score": 0.0,
                "confidence": "unknown",
                "line_count": 0,
                "error": str(e),
            })

    return results


def main():
    parser = argparse.ArgumentParser(description="RapidOCR Worker")
    parser.add_argument("--json-input", help="이미지 경로 JSON 파일")
    parser.add_argument("--lang", default="korean", help="OCR 언어")
    args = parser.parse_args()

    paths = []
    if args.json_input:
        if os.path.exists(args.json_input):
            with open(args.json_input, "r", encoding="utf-8") as f:
                paths = json.load(f)
        else:
            paths = json.loads(args.json_input)

    res = run_ocr_on_images(paths, lang=args.lang)
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
