# -*- coding: utf-8 -*-
"""
PNG 읽기·쓰기 — 파이썬 기본 기능(zlib)만으로.

바깥 라이브러리를 안 쓰는 규칙 때문에 직접 짠다. 선출 화면의 상대 그림을
알아보려면 점(픽셀) 하나하나의 색이 필요하다 (`artmatch.py`).

- 읽기: 8비트, 색 방식 0(회색)·2(RGB)·3(팔레트, tRNS 투명 포함)·4(회색+투명)·6(RGBA).
  인터레이스 PNG 와 16비트는 **못 읽는다고 바로 멈춘다** (조용히 깨진 그림을 내지 않는다).
- 결과는 늘 RGBA: (너비, 높이, bytearray 길이 너비*높이*4).
- JPG 는 못 읽는다 — 스위치 스크린샷 같은 JPG 는 먼저 PNG 로 바꾼다.
"""

import struct
import zlib

SIG = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def _chunks(data):
    pos = 8
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        yield kind, data[pos + 8:pos + 8 + n]
        pos += 12 + n


def _unfilter(raw, w, h, bpp):
    stride = w * bpp
    out = bytearray(stride * h)
    prev = bytearray(stride)
    pos = 0
    for y in range(h):
        ft = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                if pa <= pb and pa <= pc:
                    pr = a
                elif pb <= pc:
                    pr = b
                else:
                    pr = c
                line[i] = (line[i] + pr) & 255
        elif ft != 0:
            raise ValueError("PNG 줄 거르기 방식 %d 은 없는 값" % ft)
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out


def read_png(path):
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(SIG):
        raise ValueError("PNG 가 아니다: %s" % path)
    idat, plte, trns = [], None, None
    for kind, body in _chunks(data):
        if kind == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            plte = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
    if depth != 8 or inter != 0 or ctype not in _CHANNELS:
        raise ValueError("못 읽는 PNG (비트 %d, 색 방식 %d, 인터레이스 %d): %s"
                         % (depth, ctype, inter, path))
    ch = _CHANNELS[ctype]
    px = _unfilter(zlib.decompress(b"".join(idat)), w, h, ch)
    if ctype == 6:
        return w, h, px
    out = bytearray(w * h * 4)
    if ctype == 2:
        out[0::4], out[1::4], out[2::4] = px[0::3], px[1::3], px[2::3]
        out[3::4] = b"\xff" * (w * h)
        if trns and len(trns) == 6:          # 한 색을 투명으로
            key = (trns[1], trns[3], trns[5])
            for i in range(w * h):
                if tuple(px[i * 3:i * 3 + 3]) == key:
                    out[i * 4 + 3] = 0
    elif ctype == 0:
        out[0::4] = out[1::4] = out[2::4] = px
        out[3::4] = b"\xff" * (w * h)
    elif ctype == 4:
        out[0::4] = out[1::4] = out[2::4] = px[0::2]
        out[3::4] = px[1::2]
    else:                                    # 팔레트
        pal = [tuple(plte[i:i + 3]) + (255,) for i in range(0, len(plte), 3)]
        for i, a in enumerate(trns or b""):
            pal[i] = pal[i][:3] + (a,)
        table = [bytes(p) for p in pal]
        out = bytearray(b"".join(table[v] for v in px))
    return w, h, out


def write_png(path, w, h, rgba):
    assert len(rgba) == w * h * 4
    stride = w * 4
    raw = b"".join(b"\x00" + bytes(rgba[y * stride:(y + 1) * stride]) for y in range(h))

    def chunk(kind, body):
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff))

    with open(path, "wb") as f:
        f.write(SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def crop(w, h, rgba, x0, y0, x1, y1):
    """[x0, x1) x [y0, y1) 부분."""
    out = bytearray()
    for y in range(y0, y1):
        out += rgba[(y * w + x0) * 4:(y * w + x1) * 4]
    return x1 - x0, y1 - y0, out


def dark_share(w, h, rgba, dark=24, step=7):
    """거의 까만 점의 몫 (0~1). 캡처보드가 신호를 잃으면 까만 바탕에 작은 알림창만 뜬다.

    잰 것 (2026-09-23, OBS 캡처 2448x1377) — **신호 없음 0.956**, 진짜 게임 화면 **0.006~0.131**.
    """
    n = d = 0
    for y in range(0, h, step):
        base = y * w * 4
        for x in range(0, w, step):
            i = base + x * 4
            n += 1
            if rgba[i] <= dark and rgba[i + 1] <= dark and rgba[i + 2] <= dark:
                d += 1
    return d / float(n) if n else 0.0


def trim_black(w, h, rgba, dark=10, most=0.25):
    """가장자리의 **줄 전체가 거의 까만** 줄·칸을 잘라 낸 (x0, y0, x1, y1).

    OBS 창 프로젝터는 창 비율이 영상 비율과 다르면 위아래(또는 좌우)에 까만 띠를 넣는다.
    그 띠를 그대로 두면 문구 칸 자리를 화면 비율로 찾는 것이 다 어긋난다.
    - `dark`: 이 값 이하면 까만 것으로 본다 (영상 압축으로 0 이 아니라 2~3 이 되기도 한다).
    - `most`: 한쪽에서 이만큼 넘게는 안 자른다 — **게임 화면이 진짜로 어두운 장면**일 때
      화면을 파먹으면 안 된다. 넘으면 아예 안 자르고 통째로 돌려준다.
    """
    def dark_row(y):
        base = y * w * 4
        return all(rgba[base + x * 4 + c] <= dark for x in range(0, w, 3) for c in (0, 1, 2))

    def dark_col(x):
        return all(rgba[(y * w + x) * 4 + c] <= dark for y in range(0, h, 3) for c in (0, 1, 2))

    y0, y1 = 0, h
    while y0 < y1 and dark_row(y0):
        y0 += 1
    while y1 > y0 and dark_row(y1 - 1):
        y1 -= 1
    x0, x1 = 0, w
    while x0 < x1 and dark_col(x0):
        x0 += 1
    while x1 > x0 and dark_col(x1 - 1):
        x1 -= 1
    if x1 - x0 < w * (1 - most) or y1 - y0 < h * (1 - most):
        return 0, 0, w, h
    return x0, y0, x1, y1


def opaque_box(w, h, rgba, cut=16):
    """투명하지 않은 점(알파 > cut)을 다 담는 가장 작은 네모. 다 투명하면 None."""
    xs, ys = [], []
    for y in range(h):
        row = rgba[y * w * 4 + 3:(y + 1) * w * 4:4]
        hit = [x for x, a in enumerate(row) if a > cut]
        if hit:
            ys.append(y)
            xs.append(hit[0])
            xs.append(hit[-1])
    if not ys:
        return None
    return min(xs), ys[0], max(xs) + 1, ys[-1] + 1


def shrink(w, h, rgba, size):
    """긴 쪽을 size 로 줄인다 (넓이 평균, 투명도를 무게로). 키우지는 않는다."""
    scale = max(w, h) / float(size)
    if scale <= 1:
        return w, h, bytearray(rgba)
    nw, nh = max(1, round(w / scale)), max(1, round(h / scale))
    out = bytearray(nw * nh * 4)
    for ny in range(nh):
        y0, y1 = int(ny * h / nh), max(int(ny * h / nh) + 1, int((ny + 1) * h / nh))
        for nx in range(nw):
            x0, x1 = int(nx * w / nw), max(int(nx * w / nw) + 1, int((nx + 1) * w / nw))
            r = g = b = a = n = 0
            for y in range(y0, y1):
                base = y * w * 4
                for x in range(x0, x1):
                    i = base + x * 4
                    al = rgba[i + 3]
                    r += rgba[i] * al
                    g += rgba[i + 1] * al
                    b += rgba[i + 2] * al
                    a += al
                    n += 1
            o = (ny * nw + nx) * 4
            if a:
                out[o], out[o + 1], out[o + 2] = r // a, g // a, b // a
            out[o + 3] = a // n
    return nw, nh, out
