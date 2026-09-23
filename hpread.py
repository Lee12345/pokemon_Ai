# -*- coding: utf-8 -*-
"""
대전 화면에서 상대 HP(%)를 막대 길이로 잰다.

    python hpread.py 사진.png

## 왜 막대인가

상대 HP 는 화면에 「62%」 처럼 숫자로도 나오지만, **기울어진 흰 글자가 색 막대 위에** 있어서
스위치 화면(1341x749)에서는 윈도우 글자 인식이 한 번도 못 읽었다 (2026-09-22). 아이패드 녹화
(2732x2048)에서는 읽힌다 — 그걸 정답으로 모아 막대 재기를 맞춘다 (docs/이어받기.md §10).

## 어떻게 — 위치를 박지 않는다

1. 화면 오른쪽 위에서 **분홍 이름 줄**을 찾는다: 분홍이 가장 길게 이어진 가로줄에서 시작해,
   그 길이의 절반 넘게 분홍인 줄이 위아래로 이어지는 데까지. 그 높이가 **잣대(S)** 다.
   (분홍인 줄을 전부 세면 배경의 분홍 조명까지 잡혀 높이가 442 로 나온 장면이 있었다.)
2. 이름 줄 바로 아래의 막대 줄들에서, **왼쪽 분홍(초상 칸)이 끝나는 곳이 막대 시작**이다.
   거기서부터 초록·노랑·빨강이 이어지는 길이가 '찬 길이'.
   (막대 끝은 색으로 못 찾는다 — 빈 틀과 뒤 배경이 둘 다 어둡다.)
3. HP = (찬 길이 − FILL_OFFSET·S) / (BAR_LEN·S). 두 수는 아이패드 녹화의 정답으로 맞춘 값.
"""

import colorsys
import os
import sys

import paths
import pngio

# 아이패드 녹화(이름 줄 높이 70점)에서 글자 인식 % 와 맞춰 잰 값 — 87·75·33·31·25% 에서
# 찬 길이 ≈ 5 + 319 × HP (오차 2점 안). 100% 는 「100%」 글자가 막대 위를 덮어 짧게 잡혀 뺐다.
BAR_LEN = 319 / 70.0
FILL_OFFSET = 5 / 70.0


def _hsv(px, i):
    return colorsys.rgb_to_hsv(px[i] / 255.0, px[i + 1] / 255.0, px[i + 2] / 255.0)


# 색상(0~1): 이름 칸 분홍 ≈ 0.92, HP 가 적을 때의 빨간 막대 ≈ 0.96~0.97 (아이패드 녹화 4% 장면에서 잼).
# 그래서 둘의 경계를 0.95 / 0.955 로 갈랐다. ! 처음엔 이 경계가 '13% · 4% 가 0 으로 나온' 원인이라고
# 적었는데 **틀렸다** — 되돌려 봐도 4% 가 3.5% 로 잡힌다 (차이 0.6%). 진짜 원인은 같이 바꾼
# '두 번째로 긴 줄' 쪽이었다 (두 가지를 한꺼번에 바꾸고 원인을 잘못 짚음, 2026-09-23).


def _slow_is_pink(h, s, v):
    """원래 정의 — 읽기 쉬운 쪽. 아래 빠른 판이 같은 답을 주는지 검사가 대 본다."""
    return 0.86 < h < 0.95 and s > 0.45 and v > 0.45


def _slow_is_fill(h, s, v):
    return (h < 0.45 or h >= 0.955) and s > 0.45 and v > 0.45


# 아래 둘은 위 `_slow_*` 와 **똑같은 답**을 정수 계산만으로 낸다 (검사가 1,677만 색 전부 대 본다).
# 왜: `colorsys.rgb_to_hsv` 를 사진 한 장에 수백만 번 불러서 1초 넘게 거기에 썼다 (2026-09-23 에 잼).


def is_pink(r, g, b):
    """상대 이름 칸의 분홍. h 0.86~0.95 는 **빨강이 최댓값일 때만** 나온다."""
    if r < g or r < b:
        return False
    if r < 115:                 # v = r/255 > 0.45
        return False
    mn = g if g < b else b
    d = r - mn
    if d * 20 <= r * 9:         # s = d/r > 0.45
        return False
    t = g - b                   # h = (t/d)/6 + 1 → -0.84 < t/d < -0.3
    return -84 * d < 100 * t < -30 * d


def is_fill(r, g, b):
    """HP 막대의 찬 부분 — 초록·노랑·주황·빨강 (분홍과 겹치지 않게)."""
    mx = r
    if g > mx:
        mx = g
    if b > mx:
        mx = b
    if mx < 115:                # v > 0.45
        return False
    mn = r
    if g < mn:
        mn = g
    if b < mn:
        mn = b
    d = mx - mn
    if d * 20 <= mx * 9:        # s > 0.45
        return False
    if r == mx:                 # h = (t/d)/6 (mod 1) → h < 0.45 이거나 h >= 0.955
        return 100 * (g - b) >= -27 * d
    if g == mx:                 # h = (2 + (b-r)/d)/6 → h < 0.45 이려면 (b-r)/d < 0.7
        return 10 * (b - r) < 7 * d
    return False                # 파랑이 최댓값이면 h 는 0.45~0.955 안쪽이다


def _longest(flags):
    """참이 가장 길게 이어진 (길이, 시작)."""
    best = (0, 0)
    run = start = 0
    for i, f in enumerate(flags):
        if f:
            if run == 0:
                start = i
            run += 1
            if run > best[0]:
                best = (run, start)
        else:
            run = 0
    return best


def find_strip(w, h, px):
    """분홍 이름 줄 (x0, y0, x1, y1). 없으면 None."""
    xa, ya = int(w * 0.5), int(h * 0.3)
    rows = []
    for y in range(ya):
        base = y * w * 4
        rows.append([x for x in range(xa, w) if is_pink(px[base + x * 4], px[base + x * 4 + 1], px[base + x * 4 + 2])])
    # 줄마다 **분홍 점의 개수** 로 본다. '가장 길게 이어진 분홍' 으로 보니 이름 글자(흰색)가 분홍을
    # 끊어서 글자가 있는 줄이 다 빠졌다 — 이름 줄 높이가 70 이 아니라 18 로 잡혔다.
    top = max(range(ya), key=lambda y: len(rows[y]))
    n = len(rows[top])
    if n < w * 0.05:
        return None
    y0 = y1 = top
    while y0 > 0 and len(rows[y0 - 1]) > n * 0.5:
        y0 -= 1
    while y1 + 1 < ya and len(rows[y1 + 1]) > n * 0.5:
        y1 += 1
    xs = rows[top]
    return xs[0], y0, xs[-1] + 1, y1 + 1


def strip_height(w, h, px, strip):
    """이름 줄 높이를 소수점까지 — 경계의 반쯤 분홍인 줄도 그 몫만큼 센다.
    (줄 수로 세면 같은 화면이 68·70 으로 흔들려 HP 가 3% 틀어졌다.)"""
    x0, y0, x1, y1 = strip
    ya = int(h * 0.3)
    full = None
    total = 0.0
    for y in range(max(0, y0 - 4), min(ya, y1 + 4)):
        base = y * w * 4
        n = sum(1 for x in range(x0, x1) if is_pink(px[base + x * 4], px[base + x * 4 + 1], px[base + x * 4 + 2]))
        if full is None:
            mid = (y0 + y1) // 2
            full = max(1, sum(1 for x in range(x0, x1)
                              if is_pink(px[mid * w * 4 + x * 4], px[mid * w * 4 + x * 4 + 1], px[mid * w * 4 + x * 4 + 2])))
        total += min(1.0, n / float(full))
    return total


# ★ 잣대는 **화면 너비에 비례**한다 — 이름 줄 높이 ÷ 너비: 아이패드(4:3) 70/2732 = 0.0256,
#   스위치(16:9) 34.3/1346 = 0.0255. 선출 화면 칸 높이 ÷ 너비도 0.0593 · 0.0597 로 같다.
#   이름 줄을 직접 재면 포켓몬 이름 글자 수에 따라 66.7~69.1 로 흔들려 HP 가 4% 틀어졌다.
#   폰 등 **처음 보는 비율**에서는 이 비례가 안 맞을 수 있다 → 잰 높이와 10% 넘게 다르면 잰 값을 쓰고 알린다.
STRIP_PER_WIDTH = 0.0256


def scale(w, measured):
    """(잣대, 알림 또는 None)."""
    ref = STRIP_PER_WIDTH * w
    if measured and abs(measured / ref - 1) > 0.10:
        return measured, ("이름 줄 높이(%.1f)가 화면 너비로 짐작한 값(%.1f)과 %.0f%% 달라 잰 값을 씀 — "
                          "처음 보는 화면 비율일 수 있음" % (measured, ref, abs(measured / ref - 1) * 100))
    return ref, None


def measure(w, h, px):
    """{'hp': %, 'fill': 찬 길이, 'scale': S, 'rows': 잰 줄 수} 또는 None."""
    strip = find_strip(w, h, px)
    if strip is None:
        return None
    x0, y0, x1, y1 = strip
    S = y1 - y0
    Sf, why = scale(w, strip_height(w, h, px, strip))
    gap = max(2, int(S * 0.6))           # 분홍이 끝난 뒤 막대까지의 테두리 폭 (스위치 화면에서 잰 것 약 0.45 S)
    fills = []
    lo, hi = max(0, x0 - S), min(w, x1 + S)
    for y in range(y1, min(h, y1 + int(S * 1.2))):
        base = y * w * 4
        # 먼저 찬 막대(가장 긴 초록·노랑·빨강)를 찾고, **바로 왼쪽에 분홍이 붙어 있어야** 막대로 본다.
        # (반대로 '왼쪽 분홍이 끝나는 곳' 부터 찾았더니 초상 칸의 분홍이 중간에 끊긴 곳을 잡았다.)
        n, start = _longest([is_fill(px[base + x * 4], px[base + x * 4 + 1], px[base + x * 4 + 2]) for x in range(lo, hi)])
        start += lo
        if n < 2:
            fills.append(0)
            continue
        if any(is_pink(px[base + x * 4], px[base + x * 4 + 1], px[base + x * 4 + 2]) for x in range(max(0, start - gap - 3), start)):
            fills.append(n)
        else:
            fills.append(0)
    if not fills:
        return None
    fills.sort()
    # 두 번째로 긴 줄 — 「87%」 같은 숫자가 막대 아랫줄을 덮어 찬 부분을 끊는다. 윗줄은 덜 덮인다.
    # (위쪽 사분위를 쓰니 87% 가 65% 에서 멈췄고, 13% · 4% 는 막대 줄보다 막대 아닌 줄이 많아 0 이 됐다.)
    # 가장 긴 줄 하나만 쓰면 튀는 한 줄에 흔들린다.
    fill = fills[-2] if len(fills) > 1 else fills[-1]
    # ★ 막대를 못 찾았으면 **「0%」 가 아니라 「못 읽음」** 이다 (2026-09-23 실전에서 고침).
    #   쓰러지면 상대 칸이 화면에서 사라지므로 **진짜 0% 는 화면에 안 나온다.** 그런데 0.0 을
    #   돌려주고 있었다 → 실전 903프레임에서 막대가 잡힌 240개 중 **104개(43%)가 0%** 였고
    #   전부 거짓이었다 (메뉴·선출·상태확인 화면의 분홍 띠를 막대로 본 것). 조용히 틀리는 자리였다.
    if not fill:
        return None
    hp = (fill - FILL_OFFSET * Sf) / (BAR_LEN * Sf) * 100.0
    if hp <= 0.0 or hp > 105.0:         # 말이 안 되는 값은 내놓지 않는다
        return None
    return {"hp": min(100.0, hp), "fill": fill, "scale": Sf, "rows": len(fills), "warn": why}


def main(argv):
    paths.fix_console()
    import screenread
    for p in argv:
        w, h, px = pngio.read_png(screenread.to_png(p))
        print(os.path.basename(p), find_strip(w, h, px), measure(w, h, px))


if __name__ == "__main__":
    main(sys.argv[1:])
