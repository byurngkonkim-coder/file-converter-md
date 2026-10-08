# -*- coding: utf-8 -*-
"""core/ocr_worker.py - PaddleOCR 독립 실행 워커 스크립트.

MyOCR의 검증된 OCREngine 로직을 복사·내재화하여 독립적으로 동작합니다.
- PaddleOCR 3.x(predict) 및 2.x(ocr) 방어적 초기화 및 버전 호환
- 한글 파일 경로 오류 방지를 위해 PIL 로 읽어 numpy BGR 배열로 전달
- 한글/영문 텍스트 라인 및 평균 신뢰도 산출
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
    def __init__(self, lang: str = "korean"):
        self.lang = lang
        self._ocr = None

    def ensure_engine(self):
        if self._ocr is not None:
            return
        from paddleocr import PaddleOCR

        # PaddleOCR 3.x 파라미터 시도
        try:
            self._ocr = PaddleOCR(
                lang=self.lang,
                use_textline_orientation=False,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                enable_mkldnn=False,
            )
            return
        except TypeError:
            pass

        # PaddleOCR 2.x 파라미터 시도
        try:
            self._ocr = PaddleOCR(lang=self.lang, use_angle_cls=True)
            return
        except TypeError:
            pass

        # 최소 파라미터
        self._ocr = PaddleOCR(lang=self.lang)

    def run_image(self, img_path: str) -> tuple[list[tuple[str, float]], float, str]:
        """이미지 1장 OCR -> ([(text, score), ...], avg_score, confidence_level)"""
        import numpy as np
        from PIL import Image

        self.ensure_engine()

        with Image.open(img_path) as im:
            rgb = np.array(im.convert("RGB"))

        # BGR 변환
        image_bgr = np.ascontiguousarray(rgb[:, :, ::-1])

        lines: list[tuple[str, float]] = []

        # 3.x: predict()
        if hasattr(self._ocr, "predict"):
            try:
                res = self._ocr.predict(image_bgr)
                lines = self._parse_v3(res)
            except Exception:
                pass

        if not lines:
            # 2.x: ocr()
            try:
                res = self._ocr.ocr(image_bgr)
            except TypeError:
                res = self._ocr.ocr(image_bgr, cls=True)
            lines = self._parse_v2(res)

        scores = [l["score"] for l in lines if l.get("score", 0) > 0]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        conf = "high" if avg_score >= 0.85 else ("medium" if avg_score >= 0.65 else "low")
        if not lines:
            conf = "unknown"

        return lines, avg_score, conf

    @staticmethod
    def _parse_v3(result) -> list[dict]:
        lines = []
        for res in (result or []):
            texts = None
            scores = None
            boxes = None
            try:
                texts = res["rec_texts"]
            except Exception:
                texts = getattr(res, "rec_texts", None)
            try:
                scores = res["rec_scores"]
            except Exception:
                scores = getattr(res, "rec_scores", None)
            try:
                boxes = res["rec_boxes"]
            except Exception:
                boxes = getattr(res, "rec_boxes", None)
            if boxes is None:
                try:
                    boxes = res["dt_polys"]
                except Exception:
                    boxes = getattr(res, "dt_polys", None)

            if not texts:
                continue
            if not scores or len(scores) != len(texts):
                scores = [0.0] * len(texts)

            for idx, (text, score) in enumerate(zip(texts, scores)):
                if text is not None and str(text).strip():
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
                        "score": _to_float(score),
                        "box": bbox,
                    })
        return lines

    @staticmethod
    def _parse_v2(result) -> list[dict]:
        lines = []
        if not result:
            return lines
        for page in result:
            if not page:
                continue
            for item in page:
                try:
                    raw_b = item[0]
                    text, score = item[1][0], item[1][1]
                    bbox = [0.0, 0.0, 0.0, 0.0]
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
                    if text and str(text).strip():
                        lines.append({
                            "text": str(text).strip(),
                            "score": _to_float(score),
                            "box": bbox,
                        })
                except Exception:
                    continue
        return lines


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
    parser = argparse.ArgumentParser(description="OCR Worker")
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
