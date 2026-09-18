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
import re
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
        self.dropped = []        # 아예 다른 게임 기사로 판단해 버린 것

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


def _norm(text):
    """전각/반각과 대소문자를 맞춘다.

    게임 파일은 'メガリザードンＹ' 처럼 **전각** 알파벳을 쓰는데, 기사는
    반각 'メガリザードンY' 로 적는 경우가 많다. 눈으로는 같은 글자다.
    이걸 안 맞추면 메가가 통째로 안 잡힌다.
    """
    out = []
    for ch in text or "":
        o = ord(ch)
        if 0xFF01 <= o <= 0xFF5E:        # 전각 ASCII -> 반각
            ch = chr(o - 0xFEE0)
        elif ch == "\u3000":
            ch = " "
        # 성별 표기가 사이트마다 다르다. 게임 파일은 '(オス)', 기사는 '(♂)'.
        elif ch == "\u2642":
            ch = "オス"
        elif ch == "\u2640":
            ch = "メス"
        out.append(ch)
    return "".join(out).replace(" ", "").lower()


_NORM_CACHE = {}

# 사이트마다 폼 표기가 다르다. 게임 파일은 'ロトム' 과 'ウォッシュロトム' 을 따로
# 두는데, 기사는 'ロトム(水)' 라고 쓴다. 로토무는 폼마다 타입이 달라서
# 대충 기본 폼으로 뭉개면 계산이 통째로 틀린다. 그래서 여기만 따로 잇는다.
_FORM_ALIAS = {
    "ロトム(水)": "ウォッシュロトム", "ロトム(炎)": "ヒートロトム",
    "ロトム(氷)": "フロストロトム", "ロトム(飛)": "スピンロトム",
    "ロトム(草)": "カットロトム",
}


def _strip_form(name):
    """'ギルガルド(盾)' -> 'ギルガルド'. 괄호 안 폼 표기를 떼어낸다."""
    return re.sub(r"\s*[(（][^)）]*[)）]\s*$", "", name or "").strip()


def _resolve(names, kind, value, bad=None, where=None):
    """일본어면 한국어로 바꾼다. 이미 한국어면 그대로."""
    if not value:
        return None
    table = names.get(kind) or {}
    if value in table:
        return table[value]
    key = id(table)
    idx = _NORM_CACHE.get(key)
    if idx is None:
        idx = dict((_norm(k), v) for k, v in table.items())
        _NORM_CACHE[key] = idx
    got = idx.get(_norm(value))
    if got:
        return got
    if kind != "pokemon":
        return value
    # 폼까지 맞춰 보는 표. 이름만 맞으면 폼이 날아가므로 이쪽을 먼저 본다.
    # (대쓰여너 수컷/암컷은 공격이 20이나 다르다.)
    keys = names.get("pokemonKey") or {}
    kidx = _NORM_CACHE.get(id(keys))
    if kidx is None:
        kidx = dict((_norm(k), v) for k, v in keys.items())
        _NORM_CACHE[id(keys)] = kidx
    hit = keys.get(value) or kidx.get(_norm(value))
    if hit:
        return hit
    # 폼 표기가 다른 경우. 로토무처럼 폼이 곧 다른 포켓몬인 것만 따로 잇고,
    # 나머지는 괄호를 떼어 기본 폼으로 본다. **뗐다는 사실은 보고한다.**
    alias = _FORM_ALIAS.get(_norm(value).replace(" ", ""))
    if alias:
        hit = table.get(alias) or idx.get(_norm(alias))
        if hit:
            return hit
    base = _strip_form(value)
    if base and base != value:
        hit = table.get(base) or idx.get(_norm(base))
        if hit:
            if bad is not None:
                bad.add("폼 표기를 떼고 읽음", value, where or "")
            return hit
    return value


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
    dropped = []
    for party in doc.get("parties") or []:
        where = party.get("url") or ("시즌%s" % party.get("season"))
        members = []
        missed = 0
        for m in party.get("members") or []:
            name = _resolve(names, "pokemon", m.get("name"), bad, where)
            try:
                poke = dex.find_pokemon(name)
            except LookupError:
                bad.add("포켓몬", m.get("name"), where)
                missed += 1
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
                # **배분을 읽었는가.** 안 읽은 것과 무투자는 다르다.
                # spread_class({}) 는 '-'(무투자) 를 돌려주는데, 그건
                # 실재하는 형태다. 구축기사는 배분을 이미지로 올리는 일이
                # 많아서, 못 읽은 개체를 그냥 두면 공격형이 통째로
                # 무투자로 세어진다. 맞추기에서 빼려고 표시해 둔다.
                "has_evs": bool(evs),
                "cls": forms.spread_class(
                    dict((calc.SPREAD_KEY[k], v) for k, v in evs.items()
                         if k in calc.SPREAD_KEY)),
            })
        # **다른 게임 기사를 걸러낸다.** pokesol 은 챔피언스만 다루는 곳이
        # 아니어서 SV·소드실드 구축기사도 올라온다. 그런 글은 포켓몬 절반이
        # 우리 도감(231종)에 없다 — 'ポケモンsv S20シーズン終盤' 같은 제목이
        # 시즌 20 으로 읽히는 것도 그래서였다.
        # 몇 마리 못 읽은 것과 아예 다른 게임인 것은 다르게 다뤄야 한다.
        total = len(party.get("members") or [])
        if total >= 3 and missed >= total * 0.5:
            dropped.append((party.get("title") or where, missed, total))
            continue

        if members:
            # 시즌이 제목에 없는 기사가 많다. 그때는 게시 연월로 묶는다.
            # 메타가 언제 것인지는 어떻게든 붙들고 있어야 한다.
            when = (party.get("publishedAt") or "")[:7] or None
            out.append({"source": party.get("source"),
                        "season": party.get("season"),
                        "when": when,
                        "rule": party.get("rule"),
                        "rank": party.get("rank"),
                        "publishedAt": party.get("publishedAt"),
                        "title": party.get("title"),
                        "url": party.get("url"), "members": members})
    bad.dropped = dropped
    return out, bad


# ---------------------------------------------------------------------------
# 기사마다 값어치가 다르다
# ---------------------------------------------------------------------------
#
# **이건 측정한 것이 아니라 판단이다.** 그래서 숫자를 여기 모아 두고 바꿀 수 있게 한다.
#
# 어디서 온 기사인가 —
#   champs.pokedb.tokyo 는 순위 자료와 묶여 있는 곳이고, 사용률 자료도 거기서 온다.
#   pokesol.app 은 누구나 쓰는 메모장이라 '自分用メモ', 'BW縛り' 같은 글도 섞인다.
#   실제로 모아 보니 pokesol 기사의 1/4 은 제목에 시즌도 순위도 없었다.
#   그래서 champs 쪽을 더 무겁게 본다 (사용자 판단, 2026-09-17).
#
# 순위를 밝혔는가 —
#   '最終1位' 라고 적힌 글은 래더에서 실제로 나온 결과다.
#   순위가 없는 글은 시험 삼아 짠 것일 수도 있어서 반만 친다.
#
# ! 값어치를 매기는 것과 **마진을 갈아치우는 것은 다르다.** 여기서 하는 것은
#   "어느 표본을 더 믿을까" 이지 "래더 분포가 이렇다" 가 아니다.
#   마진은 끝까지 사용률 것을 쓴다.
SOURCE_WEIGHT = {"champs": 3.0, "pokesol": 1.0}
DEFAULT_WEIGHT = 1.0
NO_RANK_WEIGHT = 0.5          # 순위를 안 밝힌 글
RANK_WEIGHT = [(50, 2.0), (500, 1.5)]      # (순위 이내, 배율)


def source_of(party):
    """어느 사이트에서 온 기사인가. 안 적혀 있으면 주소로 짐작한다."""
    got = party.get("source")
    if got:
        return got
    url = party.get("url") or ""
    if "champs.pokedb" in url:
        return "champs"
    if "pokesol" in url:
        return "pokesol"
    return None


def party_weight(party):
    """이 기사를 얼마나 무겁게 볼 것인가."""
    w = SOURCE_WEIGHT.get(source_of(party), DEFAULT_WEIGHT)
    rank = party.get("rank")
    if not rank:
        return w * NO_RANK_WEIGHT
    for upto, mult in RANK_WEIGHT:
        if rank <= upto:
            return w * mult
    return w


def members(parties, season=None, weighted=False, usable=True):
    """개체를 하나씩. weighted 면 (개체, 값어치) 로 준다.

    `usable` 이면 **아무것도 못 읽은 개체는 안 준다.** 기술도 배분도 없는
    개체는 이름과 도구밖에 없어서 셀 것이 없는데, 그냥 흘려보내면
    두 군데가 조용히 틀어진다.

      * 형태가 `'-'`(무투자) 로 잡힌다. 이건 **실재하는 형태**라서
        report 의 '형태(표본)' 칸과 combos 의 갈래 세기가 같이 오염된다.
        (한카리아스가 내구 54% 로 나왔다. 사용률은 AS 47% 다.)
      * move_pairs 의 분모에 들어가 기술 확률을 깎는다.

    champs 카드는 명단과 도구만 준다 (기사 본문에는 배분이 이미지라 없다).
    그 개체들이 여기 걸린다. **버리는 것이 아니라 세지 않는 것이다** —
    samples.json 에는 그대로 남고, report 가 몇 마리인지 밝힌다.
    """
    for p in parties:
        if season is not None and p.get("season") != season:
            continue
        w = party_weight(p) if weighted else None
        for m in p["members"]:
            if usable and not (m["moves"] or m.get("has_evs")):
                continue
            yield (m, w) if weighted else m


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

# 격자는 넉넉히 잡는다. **끝 값이 뽑히면 진짜 값은 그 바깥일 수 있다** —
# 처음에 좁게 잡았다가 셋이 한꺼번에 끝에 붙어서 넓혔다.
# 보고서가 끝 값이 뽑힌 것을 따로 표시한다.
KNOBS = {
    "form_mismatch":          [0.001, 0.005, 0.02, 0.05, 0.10, 0.15,
                               0.25, 0.40, 0.60, 1.0],
    "nature_mismatch":        [0.001, 0.005, 0.01, 0.02, 0.05, 0.10,
                               0.20, 0.40, 1.0],
    "item_tendency_strength": [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.5, 6.0, 8.0],
    "mega_stat_strength":     [0.0, 0.75, 1.5, 2.5, 4.0, 6.0, 9.0],
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
    for m, w in members(parties, season, weighted=True):
        # 배분을 못 읽은 개체는 형태를 모르는 것이지 무투자인 것이 아니다.
        # 세기 맞추기는 전부 형태를 조건으로 걸므로 여기서 뺀다.
        # (기술 조합 move_pairs 는 형태를 안 보므로 그쪽에서는 그대로 쓴다.)
        if not m.get("has_evs"):
            continue
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
                total += w * math.log(p if x["name"] in have else 1 - p)
            used += 1
        else:
            want = m["nature"] if part == "natures" else m["item"]
            if not want:
                continue
            dist = forms.pick_dist(dex, poke, part, cls)
            hit = [p for e, p in dist if e["name"] == want]
            if not hit:
                continue
            total += w * math.log(max(eps, hit[0]))
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
def move_pairs(parties, poke_name, season=None, min_count=3,
               min_expect=2.0):
    """같이 다니는 기술 쌍. (기술A, 기술B, 같이, A, B, 기대, 리프트).

    리프트 = 실제로 같이 나온 횟수 / 따로따로였다면 나왔을 횟수.
    1 보다 크면 **같이 다닌다**, 작으면 **서로 안 든다**.

    ! 리프트만 보고 줄 세우면 안 된다. 열 마리에 네 마리씩 나오는
      드문 기술 둘은 **우연히** 한 번도 안 겹칠 수 있고, 그러면 리프트가
      0.00 으로 제일 커 보인다. 처음에 그렇게 짰다가 표가 쓸모없어졌다.
      그래서 (1) 따로따로였다면 몇 번은 겹쳤어야 하는 쌍만 보고,
      (2) **기대값과 실제의 차이**로 줄 세운다.
    """
    rows = [m for m in members(parties, season)
            if m["poke"]["name"] == poke_name]
    # (기술 쌍은 세는 것이지 맞추는 것이 아니라 값어치를 안 쓴다.
    #  몇 번 같이 나왔나를 그대로 보여 주는 편이 읽기 쉽다.)
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
        if expect < min_expect:
            continue           # 따로따로여도 거의 안 겹칠 쌍은 말할 것이 없다
        lift = both / expect
        out.append((a, b, both, names[a], names[b], expect, lift))
    out.sort(key=lambda r: -abs(r[2] - r[5]))
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

    when = {}
    for p in parties:
        tag = ("시즌%s" % p["season"]) if p.get("season") else (p.get("when") or "모름")
        when[tag] = when.get(tag, 0) + 1
    L.append("  파티 %d개 · 개체 %d마리"
             % (len(parties), sum(len(p["members"]) for p in parties)))
    L.append("  언제 것인가: " + "  ".join(
        "%s %d파티" % (k, v)
        for k, v in sorted(when.items(), key=lambda x: -x[1])[:6]))
    if len(when) > 1:
        L.append("  ! 시기가 섞여 있다. 메타가 다르므로 한 덩어리로 보면 안 된다.")
        L.append("    (제목에 시즌이 없으면 게시 연월로 묶는다)")

    # 무엇이 비었는지 먼저 알린다. 개체 수만 보면 다 받은 줄 알기 쉽다.
    allm = [m for p in parties for m in p["members"]]
    if allm:
        ev = sum(1 for m in allm if m.get("has_evs"))
        mv = sum(1 for m in allm if m["moves"])
        none = sum(1 for m in allm if not (m["moves"] or m.get("has_evs")))
        L.append("  채워진 칸: 기술 %d/%d (%.0f%%) · 배분 %d/%d (%.0f%%)"
                 % (mv, len(allm), mv * 100.0 / len(allm),
                    ev, len(allm), ev * 100.0 / len(allm)))
        if none:
            L.append("  ! 기술도 배분도 없는 개체 %d마리는 **아래 수치에서 뺐다.**"
                     % none)
            L.append("    이름과 도구밖에 없어서 셀 것이 없다. champs 카드만으로")
            L.append("    만들어진 개체다 — 기사 본문은 배분을 이미지로 올린다.")
            L.append("    그냥 두면 형태가 무투자('-') 로 잡혀 아래 '형태(표본)'")
            L.append("    칸과 combos 의 갈래 세기가 같이 틀어진다.")
        rest = sum(1 for m in allm if m["moves"] and not m.get("has_evs"))
        if rest:
            L.append("  ! 기술은 있는데 배분이 없는 개체 %d마리는 **--맞추기 에서만**"
                     % rest)
            L.append("    뺀다. 세기 맞추기는 전부 형태를 조건으로 걸기 때문이다.")
            L.append("    기술 조합(--쌍) 은 형태를 안 보므로 그대로 쓴다.")

    if len(bad):
        L.append("-" * 78)
        L.append("  [못 알아들은 이름 %d건] — 버리지 않고 보고한다" % len(bad))
        for kind, rows in sorted(bad.summary().items()):
            top = sorted(rows.items(), key=lambda x: -x[1])[:8]
            L.append("    %s: %s" % (kind, ", ".join(
                "%s(%d)" % (n, c) for n, c in top)))
    if getattr(bad, "dropped", None):
        L.append("-" * 78)
        L.append("  [다른 게임 기사로 보고 버린 것 %d편]" % len(bad.dropped))
        L.append("    pokesol 은 챔피언스만 다루는 곳이 아니다. SV·소드실드")
        L.append("    구축기사는 포켓몬 절반이 우리 도감(231종)에 없다.")
        for title, missed, total in bad.dropped[:6]:
            L.append("    · %s (%d/%d 마리가 챔피언스에 없음)"
                     % (title[:44], missed, total))

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

    L.append("-" * 78)
    L.append("  [기사 값어치] — 어느 표본을 더 믿을까 (측정이 아니라 판단이다)")
    grp = {}
    for p in parties:
        src = source_of(p) or "모름"
        key = (src, "순위 있음" if p.get("rank") else "순위 없음")
        grp.setdefault(key, [0, 0.0])
        grp[key][0] += 1
        grp[key][1] += party_weight(p)
    for (src, tag), (cnt, wsum) in sorted(grp.items(), key=lambda x: -x[1][0]):
        L.append("    %-10s %-10s %3d파티   평균 값어치 %.2f"
                 % (src, tag, cnt, wsum / cnt))
    L.append("    (champs.pokedb.tokyo 기사는 %.1f배로 본다 — 순위 자료와 묶인 곳이고"
             % SOURCE_WEIGHT.get("champs", 1.0))
    L.append("     사용률도 거기서 온다. pokesol 은 메모까지 섞인다.)")
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
    edge = []
    for key in sorted(KNOBS):
        pick, rows = got[key]
        used = max((r[2] for r in rows), default=0)
        now = calc.CONFIG[key]
        grid = KNOBS[key]
        mark = ""
        if pick is not None and abs(pick - now) > 1e-9:
            mark = "   ← 바꿔야 한다"
        if pick is not None and pick in (grid[0], grid[-1]):
            mark += "  ! 격자 끝"
            edge.append(key)
        if used < 200:
            mark = "   (표본 %d마리 — 200 넘어야 대충, 800 넘어야 확실)" % used
        cells = [key, "%.2f" % now,
                 "%.2f" % pick if pick is not None else "-", str(used)]
        L.append("  " + "".join(best._pad(c, w)
                                for c, (h, w) in zip(cells, head)).rstrip() + mark)
    L.append("-" * 78)
    if edge:
        L.append("  ! 격자 끝에서 뽑힌 값이 있다 (%s)." % ", ".join(edge))
        L.append("    진짜 값은 그 바깥일 수 있다. 격자를 넓혀서 다시 재야 한다.")
        L.append("")
    L.append("  표본이 적으면 값이 튄다. 가짜 표본으로 재 보니 200마리면 대충,")
    L.append("  800마리면 확실했다 (한 편에 6마리 -> 35편 / 130편).")
    L.append("  기술 쪽은 유사가능도다 (상위 목록 밖 기술을 못 세므로).")
    L.append("")
    L.append("  ! 표본은 **랭커가 쓴 것**이다. 랭커는 형태와 기술을 더 딱 맞춰")
    L.append("    짜므로, 여기서 나온 세기는 래더 평균보다 셀 수 있다.")
    L.append("    그래도 '아예 안 가른다(독립)' 보다는 이쪽이 실제에 가깝다.")
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
            ("기대", 7), ("리프트", 9)]
    L.append("  " + "".join(best._pad(h, w) for h, w in head).rstrip())
    for a, b, both, na, nb, expect, lift in rows[:16]:
        mark = ""
        if lift >= 1.3:
            mark = "   ← 같이 든다"
        elif lift <= 0.7:
            mark = "   ← 서로 안 든다"
        cells = [a, b, str(both), str(na), str(nb),
                 "%.1f" % expect, "%.2f" % lift]
        L.append("  " + "".join(best._pad(c, w)
                                for c, (h, w) in zip(cells, head)).rstrip() + mark)
    L.append("-" * 78)
    L.append("  리프트 = 실제로 같이 나온 횟수 / 따로따로였다면 나왔을 횟수.")
    L.append("  '기대' 가 작은 쌍은 우연으로 0 이 되기 쉬워서 아예 안 보여 준다.")
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
