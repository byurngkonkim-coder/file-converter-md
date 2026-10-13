# -*- coding: utf-8 -*-
"""OCR 워커는 RapidOCR 한글 v5 하나만 쓴다 (core/ocr_worker) 회귀 테스트.

배경(2026-10-13): 워커가 rapidocr_onnxruntime(구버전)을 모델 지정 없이 1순위로 시도해, 그 패키지가
깔린 PC에서는 중국어+영어 기본 모델로 한글을 읽게 돼 있었다. 한글 모델 설정 실패 시에도 기본
모델로 조용히 바꿔 띄웠고, Windows 내장 OCR·PaddleOCR 예비 경로도 있었다.
엔진을 준비하지 못해도 변환은 멈추지 않는다 — 이미지마다 오류를 기록하고 다음으로 넘어간다.
"""
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

import rapidocr
from core import ocr_worker


def test_only_rapidocr_path_in_worker():
    src = (ENGINE / "core" / "ocr_worker.py").read_text(encoding="utf-8").lower()
    for gone in ("rapidocr_onnxruntime", "winrt", "paddleocr"):
        assert gone not in src, gone


def test_korean_uses_ppocrv5_korean_model(monkeypatch):
    seen = {}
    monkeypatch.setattr(rapidocr, "RapidOCR", lambda params=None: seen.setdefault("params", params) or object())
    ocr_worker.OcrEngineWorker(lang="korean").ensure_engine()
    from rapidocr.utils.typings import LangRec, OCRVersion
    assert seen["params"]["Rec.lang_type"] == LangRec.KOREAN
    assert seen["params"]["Rec.ocr_version"] == OCRVersion.PPOCRV5


def test_engine_failure_does_not_stop_batch(monkeypatch):
    def boom(params=None):
        raise OSError("모델 파일 손상")
    monkeypatch.setattr(rapidocr, "RapidOCR", boom)
    res = ocr_worker.run_ocr_on_images(["a.png", "b.png"], lang="korean")
    assert [r["path"] for r in res] == ["a.png", "b.png"]          # 두 장 모두 결과 항목이 있다
    assert all("RapidOCR" in r["error"] and "모델 파일 손상" in r["error"] for r in res)
