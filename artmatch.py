# -*- coding: utf-8 -*-
"""
선출 화면에서 상대 6마리를 그림으로 알아본다.

    python artmatch.py 선출화면.png

## 어떻게

1. **상대 칸 찾기 — 위치를 박지 않는다.** 스위치(16:9)와 아이패드(4:3)는 칸 자리가
   다르다 (사용자, 2026-09-22). 그래서 화면 오른쪽 절반에서 **상대 칸의 빨간 바탕색**을
   찾아 줄 단위로 묶는다. 높이가 비슷한 큰 띠 6개가 상대 6칸이다 (위의 얇은 띠는
   상대 이름표라 뺀다). 6개가 안 나오면 **멈추고 말한다** — 조용히 5마리로 읽지 않는다.
2. 칸의 왼쪽(그림 자리)에서 **바탕색이 아닌 점**을 모아 그림의 모양(윤곽)을 얻는다.
3. `data/art/<key>.png` (champs 96점 그림, `fetch_art.py`) 의 모양과 대 본다.
   **색보다 모양을 본다** — 이로치는 색만 다르다 (사용자: "기존 이미지로는 이로치를
   인식하지 못할까봐"). 그림에서도 같은 '바탕색 같은 점' 을 빼고 모양을 만든다
   (무장조 날개처럼 원래 빨간 부분이 화면에서 바탕에 묻히는 것을 양쪽에 똑같이).
"""

import colorsys
import json
import os
import sys

import paths
import pngio

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "data", "art")


def _slow_is_panel(r, g, b):
    """원래 정의 — 읽기 쉬운 쪽. 아래 빠른 판이 이것과 같은 답을 주는지 검사가 대 본다."""
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return (h > 0.88 or h < 0.02) and s > 0.45 and 0.25 < v < 0.9


def is_panel(r, g, b):
    """상대 칸의 바탕색(빨강~자주, 채도 있음).

    위 `_slow_is_panel` 과 **똑같은 답**을 정수 계산만으로 낸다 (검사가 대 본다).
    왜 이렇게 했나: `colorsys.rgb_to_hsv` 를 사진 한 장에 230만 번 불러서 1.2초를
    거기에 썼다 (2026-09-23 에 잼). 빨강이 최댓값일 때만 h 가 0.88~1.0 · 0.0~0.02 에
    들어가므로, 그 경우만 따져 보면 된다.
    """
    if r < g or r < b:          # 빨강이 최댓값이 아니면 그 색상대가 아니다
        return False
    if not (63 < r < 230):      # 0.25 < v < 0.9  (v = r/255)
        return False
    mn = g if g < b else b
    d = r - mn
    if d * 20 <= r * 9:         # s = d/r > 0.45
        return False
    t = g - b                   # h = (t/d)/6 (mod 1) → -0.72 < t/d < 0.12
    return -72 * d < 100 * t < 12 * d


def _runs(flags, min_len, max_gap):
    """참인 구간들 [(시작, 끝)] — 짧게 끊긴 곳(max_gap 이하)은 잇는다."""
    out, start, last = [], None, None
    for i, f in enumerate(list(flags) + [False] * (max_gap + 1)):
        if f:
            if start is None:
                start = i
            last = i
        elif start is not None and i - last > max_gap:
            if last + 1 - start >= min_len:
                out.append((start, last + 1))
            start = None
    return out


# 선출 화면인지 **싸게** 먼저 본다 — 4줄·8칸 걸러 보니 아래 화면 8장에서 (2026-09-23):
#   선출 화면 2장  66.3% · 71.4%      ← 상대 칸의 빨간 띠가 오른쪽 절반을 가로지른다
#   대전 화면 6장   4.1% ~ 34.5%      ← 분홍 이름 칸과 빨간 HP 막대뿐이다
# 그래서 45% 로 가른다 (양쪽에 10%p 넘는 여유). 이게 없으면 **대전 화면인데도** 칸을 찾느라
# 사진 한 장에 0.42초를 버린다. 걸러 보는 값이라 이 앞선 검사 자체는 0.03초면 끝난다.
PANEL_GATE = 0.45


def looks_like_panels(w, h, px):
    """선출 화면처럼 보이나 — 가장 붉은 가로줄이 오른쪽 절반의 몇 할인지."""
    x_from = w // 2
    xs = range(x_from, w, 8)
    cols = len(xs)
    if not cols:
        return 0.0
    best = 0
    for y in range(0, h, 4):
        base = y * w * 4
        n = 0
        for x in xs:
            i = base + x * 4
            if is_panel(px[i], px[i + 1], px[i + 2]):
                n += 1
        if n > best:
            best = n
    return best / float(cols)


def find_panels(w, h, px):
    """상대 6칸 [(x0, y0, x1, y1)]. 못 찾으면 ValueError."""
    share = looks_like_panels(w, h, px)
    if share < PANEL_GATE:
        raise ValueError("상대 칸의 빨간 띠가 안 보인다 (가장 붉은 줄이 %.0f%%) — 선출 화면이 아닌 듯"
                         % (share * 100))
    x_from = w // 2
    rows = []
    for y in range(h):
        base = y * w * 4
        n = 0
        for x in range(x_from, w, 2):
            i = base + x * 4
            if is_panel(px[i], px[i + 1], px[i + 2]):
                n += 1
        rows.append(n)
    cut = max(rows) * 0.35
    bands = _runs([n > cut for n in rows], min_len=max(2, h // 100), max_gap=max(1, h // 150))
    if not bands:
        raise ValueError("상대 칸의 빨간 바탕을 못 찾았다 — 선출 화면이 맞나?")
    tall = max(b - a for a, b in bands)
    bands = [(a, b) for a, b in bands if b - a >= tall * 0.6]
    if len(bands) != 6:
        raise ValueError("상대 칸이 6개가 아니라 %d개로 보인다: %s" % (len(bands), bands))
    # 가로 범위: 바탕색이 띠 높이의 절반 넘게 차는 열의 **처음부터 끝까지**.
    # (가장 긴 구간만 잡으면 그림이 바탕을 가로막아 그림 오른쪽만 칸으로 잡힌다 — 처음에 그랬다)
    # 여섯 칸은 가로 범위가 같으므로 가운데값으로 맞춘다 — 한 칸에 레이저가 걸려도 안 흔들린다.
    lefts, rights = [], []
    for a, b in bands:
        cols = []
        for x in range(x_from, w):
            n = 0
            for y in range(a, b, 2):
                i = (y * w + x) * 4
                if is_panel(px[i], px[i + 1], px[i + 2]):
                    n += 1
            cols.append(n > (b - a) / 2 * 0.5)
        runs = _runs(cols, min_len=max(2, w // 200), max_gap=w // 100)
        lefts.append(x_from + runs[0][0])
        rights.append(x_from + runs[-1][1])
    x0, x1 = sorted(lefts)[len(lefts) // 2], sorted(rights)[len(rights) // 2]
    if x1 - x0 < w * 0.05:
        raise ValueError("상대 칸의 가로 범위가 이상하다: %d-%d" % (x0, x1))
    return [(x0, a, x1, b) for a, b in bands]




# ── 그림 비교 ────────────────────────────────────────────────────────────
#
# 잰 것 (2026-09-22, 맞힌 8마리 — 아이패드 4 · 스위치 4): 칸 높이를 H 라 하면
# champs 96점 그림 한 점 = 0.0090~0.0096 H, 그림 왼쪽 위 = 칸 왼쪽 위 + (0.54~0.58 H,
# 0.04~0.08 H). **두 기기에서 같다** — 칸이 통째로 같은 비율로 커지고 작아진다.
# 그래서 후보 그림을 **이 틀에 그대로 겹쳐** 대 본다. 모양을 저마다 늘려 맞추던
# 처음 방식은 크기 정보를 버려서 12마리 중 8마리였다.
CELL = 96
FRAME_SCALE = 0.0093    # 그림 한 점 = 칸 높이의 이만큼
FRAME_X = 0.555         # 그림 왼쪽 = 칸 왼쪽 + 칸 높이의 이만큼
FRAME_Y = 0.058
GRID = 24               # 96점 그림을 24x24 칸(칸마다 4x4점)으로 줄여 비교
SHIFT = 1               # 틀이 조금 어긋나도 되게 위아래·좌우 1칸씩 밀어 본다


def _art_grid(w, h, px):
    """96점 그림 → (칸마다 차 있는 몫, 칸마다 '바탕색 같은' 몫). 바탕색 같은 곳은 화면에서
    바탕에 묻히므로 셈에서 뺀다 (한카리아스 배·무장조 날개)."""
    step = w // GRID
    occ, red = [], []
    for gy in range(GRID):
        for gx in range(GRID):
            n = r = 0
            for y in range(gy * step, (gy + 1) * step):
                for x in range(gx * step, (gx + 1) * step):
                    i = (y * w + x) * 4
                    if px[i + 3] > 128:
                        n += 1
                        if is_panel(px[i], px[i + 1], px[i + 2]):
                            r += 1
            occ.append(n / float(step * step))
            red.append(r / float(n) if n else 0.0)
    return occ, red


def _screen_grid(w, h, px, panel):
    """칸 안 그림 틀 → (GRID+2*SHIFT)² 칸마다 '바탕색이 아닌' 몫."""
    x0, y0, x1, y1 = panel
    H = float(y1 - y0)
    step = CELL / GRID * FRAME_SCALE * H          # 한 칸의 화면 너비
    left = x0 + FRAME_X * H - SHIFT * step
    top = y0 + FRAME_Y * H - SHIFT * step
    size = GRID + 2 * SHIFT
    out = []
    for gy in range(size):
        ya, yb = int(top + gy * step), int(top + (gy + 1) * step)
        for gx in range(size):
            xa, xb = int(left + gx * step), int(left + (gx + 1) * step)
            n = f = 0
            for y in range(max(ya, y0), min(max(yb, ya + 1), y1)):
                for x in range(max(xa, x0), min(max(xb, xa + 1), x1)):
                    i = (y * w + x) * 4
                    n += 1
                    if not is_panel(px[i], px[i + 1], px[i + 2]):
                        f += 1
            out.append(f / float(n) if n else 0.0)
    return out


def _score(screen, art):
    """겹친 정도 (0~1) — 밀어 본 것 중 가장 좋은 것."""
    occ, red = art
    size = GRID + 2 * SHIFT
    best = 0.0
    for dy in range(2 * SHIFT + 1):
        for dx in range(2 * SHIFT + 1):
            inter = union = 0.0
            for gy in range(GRID):
                row = (gy + dy) * size + dx
                base = gy * GRID
                for gx in range(GRID):
                    a = occ[base + gx]
                    s = screen[row + gx]
                    wgt = 1.0 - red[base + gx]
                    inter += wgt * (a if a < s else s)
                    union += wgt * (a if a > s else s)
            if union and inter / union > best:
                best = inter / union
    return best


_ART_CACHE = {}


def art_grids():
    """key → 그림 칸. 선출 화면에 안 나오는 메가 모습은 뺀다."""
    if _ART_CACHE:
        return _ART_CACHE
    with open(os.path.join(ART, "index.json"), encoding="utf-8") as f:
        index = json.load(f)["art"]
    with open(os.path.join(HERE, "data", "pokemon.json"), encoding="utf-8") as f:
        mons = json.load(f)
    mons = mons["pokemon"] if isinstance(mons, dict) else mons
    mega = {m["key"] for m in mons if m["isMega"]}
    for key in index:
        if key in mega:
            continue
        w, h, px = pngio.read_png(os.path.join(ART, key + ".png"))
        if (w, h) != (CELL, CELL):
            raise ValueError("%s 그림이 %dx%d — %d점이어야 한다" % (key, w, h, CELL))
        _ART_CACHE[key] = _art_grid(w, h, px)
    return _ART_CACHE


# ── 성별 표시 ──────────────────────────────────────────────────────────
# 칸 오른쪽 아래(칸 높이 H 기준 가로 1.55~2.1 H, 세로 0.5~0.97 H)의 동그라미:
# ♂ 파란 동그라미, ♀ 밝은 빨간 동그라미(칸 바탕보다 훨씬 밝다), 없음(메타몽 등).
# 잰 것 (12칸): ♂ 파랑 0.12~0.15 · ♀ 빨강 0.022~0.098 (스위치 화면은 압축으로 약하다) · 없음 둘 다 0.
GENDER_BOX = (1.55, 0.5, 2.1, 0.97)
GENDER_BLUE = 0.06
GENDER_RED = 0.01


def read_gender(w, h, px, panel):
    """'수컷' / '암컷' / None(표시 없음)."""
    x0, y0, x1, y1 = panel
    H = y1 - y0
    gx0, gy0, gx1, gy1 = GENDER_BOX
    blue = red = n = 0
    for y in range(int(y0 + gy0 * H), min(int(y0 + gy1 * H), y1)):
        for x in range(int(x0 + gx0 * H), min(int(x0 + gx1 * H), x1)):
            i = (y * w + x) * 4
            r, g, b = px[i], px[i + 1], px[i + 2]
            n += 1
            if b > 150 and b > r + 60:
                blue += 1
            elif r > 200 and g < 90 and b < 110:
                red += 1
    if not n:
        return None
    blue, red = blue / float(n), red / float(n)
    if blue > GENDER_BLUE and blue > red:
        return "수컷"
    if red > GENDER_RED:
        return "암컷"
    return None


def _gender_ok(form, gender):
    """모습 이름에 성별이 들어간 것(대쓰여너·냐오닉스·에써르)만 가른다."""
    if gender is None:
        return True
    other = "암컷" if gender == "수컷" else "수컷"
    return other not in (form or "")


def identify(w, h, px, top=3):
    """상대 6칸 → [(칸, 성별, [(점수, key), …])]."""
    arts = art_grids()
    with open(os.path.join(ART, "index.json"), encoding="utf-8") as f:
        forms = {k: v["form"] for k, v in json.load(f)["art"].items()}
    out = []
    for panel in find_panels(w, h, px):
        gender = read_gender(w, h, px, panel)
        screen = _screen_grid(w, h, px, panel)
        ranked = sorted(((_score(screen, a), k) for k, a in arts.items()
                         if _gender_ok(forms.get(k), gender)), reverse=True)
        out.append((panel, gender, ranked[:top]))
    return out


def main(argv):
    paths.fix_console()
    with open(os.path.join(ART, "index.json"), encoding="utf-8") as f:
        index = json.load(f)["art"]
    w, h, px = pngio.read_png(argv[0])
    for i, (panel, gender, ranked) in enumerate(identify(w, h, px), 1):
        names = ["%s %.2f" % (index[k]["name"] + ("(" + index[k]["form"] + ")" if index[k]["form"] else ""), s)
                 for s, k in ranked]
        print("%d. [%s] %s" % (i, gender or "성별 표시 없음", " · ".join(names) or "그림을 못 찾음"))


if __name__ == "__main__":
    main(sys.argv[1:])
