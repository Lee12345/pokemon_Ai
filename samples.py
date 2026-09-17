# -*- coding: utf-8 -*-
"""
1-B — 구축기사 표본. 사용률이 못 주는 **조합**을 여기서 받는다.

    python samples.py                 # 무엇이 들어왔나
    python samples.py --맞추기        # 가정값 4개의 세기를 표본으로 맞춘다
    python samples.py --쌍 한카리아스  # 어떤 기술끼리 같이 다니는가

## 왜 필요한가

사용률은 **마진**이다. "지진 67%, 스텔스록 40%" 는 알려 주지만
"둘을 같이 드는가" 는 안 알려 준다. 1-A 에서 노력치 마진과 기술 마진을
교차시켜 상당 부분을 복원했지만, 두 가지가 끝내 안 됐다.

  1. **세기.** 방향은 게임 규칙이 정했는데 얼마나 센지는 확인이 안 된다.
     `form_mismatch` 0.15 냐 0.40 이냐로 추천이 바뀐다 (4개 중 1개).
  2. **기술끼리의 조합.** 스텔스록과 드래곤테일을 같이 드는지는
     마진 두 개를 아무리 교차시켜도 안 나온다.

구축기사 한 편에는 **6마리의 완전한 구성**이 적혀 있다. 기술 4개 · 배분 ·
성격 · 도구가 한 덩어리로 온다. 그게 바로 위 둘을 메우는 표본이다.
한 판 뛰는 것보다 정보 밀도가 훨씬 높다 — 대전 한 판은 상대 3마리의
**일부** 기술만 보여 준다.

## 한계 — 사용자가 먼저 짚은 것

> 시즌이 바뀌면서 메타가 바뀌니 어디까지나 참고용.

그래서 시즌을 반드시 같이 받고, 보고서에서 시즌별로 나눠 보여 준다.
사용률(현재 시즌)과 표본(여러 시즌)을 섞어서 하나로 뭉개지 않는다.

또 하나. 구축기사는 **랭커가 쓴 것**이라 래더 전체 분포와 다르다.
잘 나가는 구성 쪽으로 치우쳐 있다. 그래서 표본으로 **마진을 갈아치우지
않는다.** 마진은 사용률 것을 그대로 쓰고, 표본은 **조합만** 고치는 데 쓴다.

## 표본이 몇 개나 필요한가 — 직접 재 봤다

정답을 아는 가짜 표본을 만들어 놓고 맞추기가 그 값을 되찾는지 셌다.

    개체  48마리  ->  0.02 / 0.05 / 0.10   (세 번 재면 세 번 다르다)
    개체 200마리  ->  0.05 / 0.10 / 0.05   (대충 맞는다)
    개체 800마리  ->  0.05 / 0.05 / 0.05   (확실하다)

한 편에 6마리이므로 **35편이면 대충, 130편이면 확실**하다.
기술 쌍은 포켓몬별로 세므로 **그 포켓몬이 30마리는 나와야** 볼 만하다.

## 넣는 형식 — data/samples.json

    {"parties": [
      {"season": 6, "rank": 12, "url": "...",
       "members": [
         {"name": "ガブリアス",            <- 일본어/한국어 아무거나
          "item": "こだわりスカーフ",
          "ability": "さめはだ",
          "nature": "いじっぱり",
          "evs": {"A": 32, "S": 32},      <- 챔피언스 표기 (한 칸 최대 32)
          "moves": ["じしん", "げきりん", "スケイルショット", "ドラゴンテール"]},
         ...
       ]}
    ]}

이름은 일본어로 넣어도 된다 (`build_names.py` 가 만든 이름표로 잇는다).
못 알아들은 이름은 **조용히 버리지 않고 전부 보고한다.**
"""

import itertools
import json
import os
import sys

import calc
import forms

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "data", "samples.json")
NAMES = os.path.join(HERE, "data", "names_ja.json")

# 노력치 표기 (사용률 자료와 같은 키)
EV_KEYS = ("H", "A", "B", "C", "D", "S")


def load_names():
    if not os.path.exists(NAMES):
        return {}
    with open(NAMES, encoding="utf-8") as f:
        return json.load(f)


class Unresolved(object):
    """못 알아들은 이름을 모아 둔다. 조용히 넘어가지 않기 위한 것이다."""

    def __init__(self):
        self.rows = []

    def add(self, kind, name, where):
        self.rows.append((kind, name, where))

    def __len__(self):
        return len(self.rows)

    def summary(self):
        by = {}
        for kind, name, _ in self.rows:
            by.setdefault(kind, {}).setdefault(name, 0)
            by[kind][name] += 1
        return by


def _resolve(names, kind, value):
    """일본어면 한국어로 바꾼다. 이미 한국어면 그대로."""
    if not value:
        return None
    table = names.get(kind) or {}
    return table.get(value, value)


def parse_evs(raw):
    """노력치를 dict 로. {"A":32,"S":32} 도 되고 "A32 S32" 도 된다."""
    if isinstance(raw, dict):
        return dict((k, int(v)) for k, v in raw.items()
                    if k in EV_KEYS and int(v) > 0)
    out = {}
    if not raw:
        return out
    token = ""
    for ch in str(raw).replace("/", " ").replace(",", " "):
        token += ch
    cur = None
    num = ""
    for ch in token:
        if ch in EV_KEYS:
            if cur and num:
                out[cur] = int(num)
            cur, num = ch, ""
        elif ch.isdigit():
            num += ch
        else:
            if cur and num:
                out[cur] = int(num)
            cur, num = None, ""
    if cur and num:
        out[cur] = int(num)
    return dict((k, v) for k, v in out.items() if v > 0)


def load(dex, path=None, bad=None):
    """표본을 읽어서 (파티 목록, 못 알아들은 것) 을 돌려준다."""
    path = path or SAMPLES
    bad = bad if bad is not None else Unresolved()
    if not os.path.exists(path):
        return [], bad
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    names = load_names()

    out = []
    for party in doc.get("parties") or []:
        where = party.get("url") or ("시즌%s" % party.get("season"))
        members = []
        for m in party.get("members") or []:
            name = _resolve(names, "pokemon", m.get("name"))
            try:
                poke = dex.find_pokemon(name)
            except LookupError:
                bad.add("포켓몬", m.get("name"), where)
                continue
            moves = []
            for mv in m.get("moves") or []:
                kname = _resolve(names, "moves", mv)
                try:
                    moves.append(dex.find_move(kname))
                except LookupError:
                    bad.add("기술", mv, where)
            item = _resolve(names, "items", m.get("item"))
            nature = _resolve(names, "natures", m.get("nature"))
            ability = _resolve(names, "abilities", m.get("ability"))
            evs = parse_evs(m.get("evs"))
            members.append({
                "poke": poke, "moves": moves, "item": item,
                "nature": nature, "ability": ability, "evs": evs,
                "cls": forms.spread_class(
                    dict((calc.SPREAD_KEY[k], v) for k, v in evs.items()
                         if k in calc.SPREAD_KEY)),
            })
        if members:
            out.append({"season": party.get("season"),
                        "rank": party.get("rank"),
                        "url": party.get("url"), "members": members})
    return out, bad


def members(parties, season=None):
    for p in parties:
        if season is not None and p.get("season") != season:
            continue
        for m in p["members"]:
            yield m


def by_pokemon(parties, season=None):
    out = {}
    for m in members(parties, season):
        out.setdefault(m["poke"]["name"], []).append(m)
    return out


# ---------------------------------------------------------------------------
# 가정값 세기 맞추기
# ---------------------------------------------------------------------------
# 표본 하나하나가 **형태와 기술이 같이 적힌 한 덩어리**다. 그러니
# "이 세기였다면 이 표본이 나올 법했나" 를 물을 수 있다. 제일 그럴듯한
# 세기를 고른다 (최대가능도).
#
# ! 기술 쪽은 정확한 가능도가 아니라 **유사가능도**를 쓴다. 기술 4칸 중
#   사용률 상위 목록에 없는 기술이 섞여 있어 정확한 집합 확률을 못 매긴다.
#   목록에 있는 기술 하나하나를 독립 동전으로 보고 더한다. 세기 하나를
#   고르는 데는 이걸로 충분하다.

import math

KNOBS = {
    "form_mismatch":          [0.02, 0.05, 0.10, 0.15, 0.25, 0.40, 0.60, 1.0],
    "nature_mismatch":        [0.01, 0.02, 0.05, 0.10, 0.20, 0.40, 1.0],
    "item_tendency_strength": [0.0, 0.5, 1.0, 1.5, 2.0, 3.0],
    "mega_stat_strength":     [0.0, 0.75, 1.5, 2.5, 4.0],
}
# 그 세기가 어느 부분의 가능도에 걸리는가
KNOB_PART = {"form_mismatch": "moves", "nature_mismatch": "natures",
             "item_tendency_strength": "items",
             "mega_stat_strength": "items"}


def _clear():
    forms._TABLE_CACHE.clear()
    forms._PICK_CACHE.clear()


def loglik(dex, parties, part, season=None):
    """표본이 지금 설정에서 얼마나 그럴듯한가. (로그가능도, 쓴 표본 수)."""
    total, used = 0.0, 0
    eps = 1e-9
    for m in members(parties, season):
        poke, cls = m["poke"], m["cls"]
        if part == "moves":
            classes, weights, mv, table = forms.conditional_table(dex, poke)
            if not table or cls not in classes:
                continue
            row = table[classes.index(cls)]
            have = set(x["name"] for x in m["moves"])
            if not have:
                continue
            for j, x in enumerate(mv):
                p = min(1 - eps, max(eps, row[j]))
                total += math.log(p if x["name"] in have else 1 - p)
            used += 1
        else:
            want = m["nature"] if part == "natures" else m["item"]
            if not want:
                continue
            dist = forms.pick_dist(dex, poke, part, cls)
            hit = [p for e, p in dist if e["name"] == want]
            if not hit:
                continue
            total += math.log(max(eps, hit[0]))
            used += 1
    return total, used


def fit(dex, parties, season=None):
    """가정값 4개를 표본으로 맞춘다. {값이름: (제일 그럴듯한 값, 표)}."""
    out = {}
    saved = dict((k, calc.CONFIG[k]) for k in KNOBS)
    try:
        for key, grid in sorted(KNOBS.items()):
            part = KNOB_PART[key]
            rows = []
            for v in grid:
                calc.CONFIG[key] = v
                _clear()
                ll, used = loglik(dex, parties, part, season)
                rows.append((v, ll, used))
            calc.CONFIG[key] = saved[key]
            _clear()
            best = max(rows, key=lambda r: r[1]) if rows else None
            out[key] = (best[0] if best else None, rows)
    finally:
        calc.CONFIG.update(saved)
        _clear()
    return out


# ---------------------------------------------------------------------------
# 기술끼리의 조합 — 마진으로는 절대 안 나오는 것
# ---------------------------------------------------------------------------
def move_pairs(parties, poke_name, season=None, min_count=3):
    """같이 다니는 기술 쌍. (기술A, 기술B, 같이, A만, B만, 리프트).

    리프트 = 실제로 같이 나온 비율 / 따로따로였다면 나왔을 비율.
    1 보다 크면 **같이 다닌다**, 작으면 **서로 안 든다**.
    """
    rows = [m for m in members(parties, season)
            if m["poke"]["name"] == poke_name]
    n = len(rows)
    if n < min_count:
        return [], n
    have = [set(x["name"] for x in m["moves"]) for m in rows]
    names = {}
    for h in have:
        for x in h:
            names[x] = names.get(x, 0) + 1
    out = []
    for a, b in itertools.combinations(sorted(names), 2):
        if names[a] < min_count or names[b] < min_count:
            continue
        both = sum(1 for h in have if a in h and b in h)
        pa, pb = names[a] / float(n), names[b] / float(n)
        expect = pa * pb * n
        lift = (both / expect) if expect > 0 else 0.0
        out.append((a, b, both, names[a], names[b], lift))
    out.sort(key=lambda r: -abs(math.log(r[5]) if r[5] > 0 else 9))
    return out, n


# ---------------------------------------------------------------------------
# 보고서
# ---------------------------------------------------------------------------
def report(dex, parties, bad):
    import best

    L = []
    line = "=" * 78
    L.append(line)
    L.append("  구축기사 표본 (1-B)")
    L.append(line)
    if not parties:
        L.append("  data/samples.json 이 없거나 비어 있다.")
        L.append("  형식은 samples.py 맨 위 설명을 볼 것.")
        L.append(line)
        return "\n".join(L)

    seasons = {}
    for p in parties:
        seasons.setdefault(p.get("season"), 0)
        seasons[p.get("season")] += 1
    L.append("  파티 %d개 · 개체 %d마리"
             % (len(parties), sum(len(p["members"]) for p in parties)))
    L.append("  시즌별: " + "  ".join(
        "시즌%s %d파티" % (s, c) for s, c in sorted(
            seasons.items(), key=lambda x: (x[0] is None, x[0]))))
    if len(seasons) > 1:
        L.append("  ! 시즌이 섞여 있다. 메타가 다르므로 한 덩어리로 보면 안 된다.")

    if len(bad):
        L.append("-" * 78)
        L.append("  [못 알아들은 이름 %d건] — 버리지 않고 보고한다" % len(bad))
        for kind, rows in sorted(bad.summary().items()):
            top = sorted(rows.items(), key=lambda x: -x[1])[:8]
            L.append("    %s: %s" % (kind, ", ".join(
                "%s(%d)" % (n, c) for n, c in top)))

    L.append("-" * 78)
    L.append("  [표본에 많이 나온 포켓몬]")
    counts = by_pokemon(parties)
    head = [("포켓몬", 14), ("표본", 7), ("형태 (표본)", 26), ("형태 (사용률)", 26)]
    L.append("  " + "".join(best._pad(h, w) for h, w in head).rstrip())
    for name, rows in sorted(counts.items(), key=lambda x: -len(x[1]))[:12]:
        got = {}
        for m in rows:
            got[m["cls"]] = got.get(m["cls"], 0) + 1
        n = float(len(rows))
        mine = " ".join("%s%.0f%%" % (forms.CLASS_KO[c][:2], v / n * 100)
                        for c, v in sorted(got.items(), key=lambda x: -x[1])[:3])
        try:
            w = forms.class_weights(dex, dex.find_pokemon(name))
        except LookupError:
            w = {}
        theirs = " ".join("%s%.0f%%" % (forms.CLASS_KO[c][:2], v * 100)
                          for c, v in sorted(w.items(), key=lambda x: -x[1])[:3])
        cells = [name, str(len(rows)), mine, theirs]
        L.append("  " + "".join(best._pad(c, wd)
                                for c, (h, wd) in zip(cells, head)).rstrip())
    L.append("")
    L.append("  ! 표본은 **랭커가 쓴 것**이라 래더 전체와 다르다. 위 두 칸이")
    L.append("    다른 것은 오류가 아니다. 그래서 표본으로 마진을 갈아치우지 않고,")
    L.append("    **조합만** 고치는 데 쓴다.")
    L.append(line)
    return "\n".join(L)


def report_fit(dex, parties, season=None):
    import best

    L = []
    line = "=" * 78
    L.append(line)
    L.append("  가정값 세기를 표본으로 맞춘다" +
             (" (시즌%s)" % season if season is not None else ""))
    L.append(line)
    got = fit(dex, parties, season)
    head = [("가정값", 26), ("지금", 8), ("표본이 고른 값", 16), ("표본 수", 9)]
    L.append("  " + "".join(best._pad(h, w) for h, w in head).rstrip())
    for key in sorted(KNOBS):
        pick, rows = got[key]
        used = max((r[2] for r in rows), default=0)
        now = calc.CONFIG[key]
        mark = ""
        if pick is not None and abs(pick - now) > 1e-9:
            mark = "   ← 바꿔야 한다"
        if used < 200:
            mark = "   (표본 %d마리 — 200 넘어야 대충, 800 넘어야 확실)" % used
        cells = [key, "%.2f" % now,
                 "%.2f" % pick if pick is not None else "-", str(used)]
        L.append("  " + "".join(best._pad(c, w)
                                for c, (h, w) in zip(cells, head)).rstrip() + mark)
    L.append("-" * 78)
    L.append("  표본이 적으면 값이 튄다. 가짜 표본으로 재 보니 200마리면 대충,")
    L.append("  800마리면 확실했다 (한 편에 6마리 -> 35편 / 130편).")
    L.append("  기술 쪽은 유사가능도다 (상위 목록 밖 기술을 못 세므로).")
    L.append(line)
    return "\n".join(L)


def report_pairs(dex, parties, name, season=None):
    import best

    L = []
    line = "=" * 78
    L.append(line)
    L.append("  %s — 어떤 기술끼리 같이 다니는가" % name)
    L.append(line)
    rows, n = move_pairs(parties, name, season)
    if not rows:
        L.append("  표본이 부족하다 (%d마리)." % n)
        L.append(line)
        return "\n".join(L)
    L.append("  표본 %d마리" % n)
    L.append("-" * 78)
    head = [("기술 A", 15), ("기술 B", 15), ("같이", 7), ("A", 6), ("B", 6),
            ("리프트", 9)]
    L.append("  " + "".join(best._pad(h, w) for h, w in head).rstrip())
    for a, b, both, na, nb, lift in rows[:14]:
        mark = ""
        if lift >= 1.3:
            mark = "   ← 같이 든다"
        elif lift <= 0.7:
            mark = "   ← 서로 안 든다"
        cells = [a, b, str(both), str(na), str(nb), "%.2f" % lift]
        L.append("  " + "".join(best._pad(c, w)
                                for c, (h, w) in zip(cells, head)).rstrip() + mark)
    L.append("-" * 78)
    L.append("  리프트 = 실제로 같이 나온 비율 / 따로따로였다면 나왔을 비율.")
    L.append("  **이건 사용률 마진으로는 절대 안 나오는 정보다.**")
    L.append(line)
    return "\n".join(L)


def main():
    dex = calc.Dex()
    argv = sys.argv[1:]
    season = None
    if "--시즌" in argv:
        i = argv.index("--시즌")
        season = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    path = None
    if "--파일" in argv:
        i = argv.index("--파일")
        path = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]

    parties, bad = load(dex, path)
    if "--맞추기" in argv:
        print(report_fit(dex, parties, season))
    elif "--쌍" in argv:
        i = argv.index("--쌍")
        print(report_pairs(dex, parties, argv[i + 1], season))
    else:
        print(report(dex, parties, bad))


if __name__ == "__main__":
    main()
