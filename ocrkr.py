# -*- coding: utf-8 -*-
"""한국어 글자 인식 — **PaddleOCR 모델** (RapidOCR·onnxruntime 로 돌린다).

    python ocrkr.py 사진.png

## 왜 바꿨나 (2026-09-24, 사용자 요구: "Paddle OCR로 교체하고싶어")

그전까지는 **윈도우 10 내장 글자 인식**을 썼다. 실전에서 못 읽은 40장으로 둘을 견줬다
(`내기록/못읽은화면`, 2026-09-23 한 판) —

| | 장당 | 상대 이름 칸 | 한글 이름 |
|---|---|---|---|
| 윈도우 내장 | **0.19초** | 40장 중 **0장** | 「크Ä/까자리」 · 「* 티부Ⅹ/고」 |
| 패들 모델 | 0.70~1.06초 | **읽힌다** | 「더시마사리」 · 「타부자고」 |

★ **이름을 제대로 읽는 것이 판을 가른다.** 실전에서 상대가 패리퍼로 바꿨는데 창이 23초
  동안 저승갓숭으로 알고 답을 냈다 (사용자가 잡음). 윈도우 내장은 그 40장에서 상대 이름
  칸을 **한 번도** 못 읽었다. 패들은 읽는다.
★ 대신 **장당 0.7초쯤 느려진다.** 따라가기 한 바퀴가 0.5초 → 1.2초가 된다.

## 파이썬 3.14 에서는 paddlepaddle 이 안 깔린다

`pip install paddlepaddle` → "No matching distribution". 그래서 **같은 모델(PP-OCRv5
korean)을 onnxruntime 으로 돌리는 RapidOCR** 를 쓴다. onnxruntime 은 이미 깔려 있었다.
모델은 첫 실행 때 내려받아 `site-packages/rapidocr/models` 에 놓인다 (한 번만).

## 없으면 없는 대로

`rapidocr` 가 없는 컴퓨터(개발 컨테이너·빌드 서버)에서는 `available()` 이 False 를
돌려주고, `screenread` 가 **윈도우 내장으로 되돌아간다.** 검사는 양쪽에서 다 돌아야 한다.
"""

import os
import sys

_ENGINE = None          # 만들어 둔 엔진 (한 번만 만든다 — 만드는 데 1.5초쯤)
_FAILED = None          # 못 만든 까닭 (한 번 실패하면 다시 안 해 본다)


def available():
    """이 컴퓨터에서 쓸 수 있나."""
    if _ENGINE is not None:
        return True
    if _FAILED is not None:
        return False
    try:
        import rapidocr                      # noqa: F401
    except Exception:
        return False
    return True


def why_not():
    return _FAILED


def engine():
    """엔진 하나를 만들어 두고 계속 쓴다. 못 만들면 None."""
    global _ENGINE, _FAILED
    if _ENGINE is not None or _FAILED is not None:
        return _ENGINE
    try:
        from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
        # ! 로그를 끄지 않으면 장마다 INFO 줄이 콘솔에 쏟아진다.
        # ! 한국어 모델은 **PP-OCRv5 에만** 있다 (v6 의 52개 말 목록에 한국어가 없다).
        _ENGINE = RapidOCR(params={
            "Global.log_level": "error",
            "Det.ocr_version": OCRVersion.PPOCRV5,
            "Det.model_type": ModelType.MOBILE,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.lang_type": LangRec.KOREAN,
            "Rec.model_type": ModelType.MOBILE,
        })
    except Exception as e:
        _FAILED = "%s: %s" % (type(e).__name__, e)
        _ENGINE = None
    return _ENGINE


def read(path, scale=1):
    """사진 한 장 → [(x, y, 글)] — `screenread.ocr` 과 같은 모양. 못 읽으면 None.

    `scale` 을 주면 그만큼 키워서 읽고 좌표는 **원래 사진 기준**으로 돌려준다.
    ★ **작은 화면은 키워야 한다.** 스위치 녹화(1346x755)에서 「악타입이 됐다!」 를 그대로는
      「10」 으로 읽었다 (윈도우 내장은 2배로 키워 읽어서 맞혔다). 2배로 키우니 맞는다.
    """
    eng = engine()
    if eng is None:
        return None
    try:
        src = path
        if scale != 1:
            import cv2                      # rapidocr 가 깔리면 같이 들어온다
            import numpy as np
            # ! `cv2.imread` 는 **한글이 든 경로를 못 연다** (윈도우). 조용히 None 을 돌려줘서
            #   글자 인식이 통째로 안 돌고 있었는데 아무 말도 없었다 (2026-09-24).
            #   그래서 파일을 직접 읽어서 푼다.
            img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return None
            src = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        res = eng(src)
    except Exception as e:
        # 한 장 실패는 엔진을 죽이지 않는다 (사진이 깨졌을 수도 있다)
        sys.stderr.write("글자 인식 실패: %s\n" % e)
        return None
    boxes = getattr(res, "boxes", None)
    txts = getattr(res, "txts", None)
    if not txts:
        return []
    out = []
    for i, text in enumerate(txts):
        x = y = 0
        if boxes is not None and i < len(boxes):
            # 네 꼭짓점 중 왼쪽 위 — 키워서 읽었으면 원래 사진 자리로 되돌린다
            pts = boxes[i]
            x = int(min(p[0] for p in pts) / scale)
            y = int(min(p[1] for p in pts) / scale)
        out.append((x, y, str(text)))
    out.sort(key=lambda r: (r[1], r[0]))
    return out


def main(argv):
    import paths
    paths.fix_console()
    if not argv:
        print("쓰기: python ocrkr.py 사진.png")
        return 1
    if not available():
        print("rapidocr 가 없습니다 — pip install rapidocr")
        return 1
    import time
    for f in argv:
        t = time.time()
        got = read(f)
        print("== %s  %.2f초" % (os.path.basename(f), time.time() - t))
        for x, y, text in got or []:
            print("  %5d,%5d  %s" % (x, y, text))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
