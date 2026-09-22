# -*- coding: utf-8 -*-
"""
포켓몬 그림을 받아 온다 (champs.pokedb.tokyo 의 96점 그림 판).

    python fetch_art.py            # 판을 받아 우리 포켓몬만 잘라 둔다
    python fetch_art.py --목록      # 받지 않고 무엇이 몇 개인지만 찍는다

## 왜 있나

선출 화면의 상대 6마리는 **그림뿐**이다 (이름 글자가 없다). 그래서 그림을
대 보고 누구인지 알아본다 (`artmatch.py`).

## 왜 champs 인가 (2026-09-22, 사용자가 고름)

처음엔 포켓몬 위키(fandom)의 공식 일러스트를 받으려 했다. 사용자가 champs 에서
받자고 해서 바꿨다. champs 쪽이 나은 점:
- 그림 이름이 **우리 자료의 key 와 똑같다** (`0445-00` = 한카리아스, `-01` = 메가).
  이름으로 맞추다 틀릴 일이 없다. 위키는 모습 이름을 낱말로 맞춰야 했다.
- 주소가 `champs/assets` — 게임 속 그림일 가능성이 높다 (대 보고 확인할 것).
- 96점 그림을 모은 **PNG 판 9장**(합 약 4MB)이라 파이썬 기본 기능으로 읽힌다.
  한 장씩 있는 512점 그림은 WebP 라 못 읽는다.

이로치 그림은 champs 에도 위키에도 없다. 그래서 알아볼 때 **색보다 모양**을 본다.

## 무엇을 남기나

- 판 원본: `data/art_raw/` (깃허브에 안 올린다, .gitignore)
- **게임 자료(`data/pokemon.json`)에 있는 것만** 잘라서 `data/art/<key>.png` (96x96, 올린다).
  메가 모습도 자른다 (선출 화면엔 안 나오지만 대전 중 그림에 쓸 수 있다).
- 어느 판 어느 자리에서 잘랐나: `data/art/index.json`.
"""

import json
import os
import re
import sys
import urllib.request

import paths
import pngio

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "art")
RAW = os.path.join(HERE, "data", "art_raw")
CSS = "https://champs.pokedb.tokyo/css/pokemon-sprite-96.css"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
CELL = 96

# --sprite-96-04-png:url("https://…/pokemon-sprite-96-04.png?v=…")
_SHEET = re.compile(r'--sprite-96-(\d+)-png:url\("([^"]+)"\)')
# .dex-0445-00-96{background-image:var(--sprite-96-04-image-set);--poke-x:-192px;--poke-y:-576px;}
_CELL = re.compile(r"\.dex-(\d{4}-\d{2})-96\{background-image:var\(--sprite-96-(\d+)-image-set\);"
                   r"--poke-x:(-?\d+)px;--poke-y:(-?\d+)px;\}")


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Referer": "https://champs.pokedb.tokyo/"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def parse_css(text):
    """(판 번호 → 주소, key → (판 번호, x, y))."""
    sheets = {n: u for n, u in _SHEET.findall(text)}
    cells = {k: (n, -int(x), -int(y)) for k, n, x, y in _CELL.findall(text)}
    return sheets, cells


def ours():
    with open(os.path.join(HERE, "data", "pokemon.json"), encoding="utf-8") as f:
        mons = json.load(f)
    return mons["pokemon"] if isinstance(mons, dict) else mons


def main(argv):
    paths.fix_console()
    text = download(CSS).decode("utf-8")
    sheets, cells = parse_css(text)
    # 규칙에 안 걸린 칸이 있으면 조용히 빠진다 — 개수를 맞춰 본다
    listed = len(re.findall(r"\.dex-\d{4}-\d{2}-96\{", text))
    if listed != len(cells):
        raise SystemExit("그림 칸 %d개 중 %d개만 읽었다 — CSS 모양이 바뀌었다" % (listed, len(cells)))
    mons = ours()
    missing = [m["key"] + " " + m["name"] for m in mons if m["key"] not in cells]
    print("판 %d장 · 칸 %d개 · 우리 포켓몬 %d개 중 없는 것 %d개"
          % (len(sheets), len(cells), len(mons), len(missing)))
    for x in missing:
        print("   없음:", x)
    if "--목록" in argv:
        return
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(RAW, exist_ok=True)
    need = sorted({cells[m["key"]][0] for m in mons if m["key"] in cells})
    decoded = {}
    for n in need:
        path = os.path.join(RAW, "pokemon-sprite-96-%s.png" % n)
        if not os.path.exists(path):
            data = download(sheets[n])
            if not data.startswith(pngio.SIG):
                raise ValueError("PNG 가 아닌 것이 왔다: %s" % sheets[n])
            with open(path, "wb") as f:
                f.write(data)
        decoded[n] = pngio.read_png(path)
        print("  판 %s  %dx%d" % (n, decoded[n][0], decoded[n][1]))
    index = {}
    for m in mons:
        if m["key"] not in cells:
            continue
        n, x, y = cells[m["key"]]
        w, h, px = decoded[n]
        if x + CELL > w or y + CELL > h:
            raise ValueError("%s 칸이 판 밖이다" % m["key"])
        cw, ch, cut = pngio.crop(w, h, px, x, y, x + CELL, y + CELL)
        if pngio.opaque_box(cw, ch, cut) is None:
            raise ValueError("%s 칸이 비어 있다 (다 투명)" % m["key"])
        pngio.write_png(os.path.join(OUT, m["key"] + ".png"), cw, ch, cut)
        index[m["key"]] = {"name": m["name"], "form": m["formName"], "sheet": n, "x": x, "y": y}
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"source": CSS, "cell": CELL, "art": index}, f, ensure_ascii=False, indent=1)
    print("잘라 둔 그림 %d개 → %s" % (len(index), OUT))


if __name__ == "__main__":
    main(sys.argv[1:])
