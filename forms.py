# -*- coding: utf-8 -*-
"""
1-A — 형태를 가른다. 채용률을 '따로따로' 에서 '같이' 로.

    python forms.py 한카리아스
    python forms.py                  # 상위 30마리 중 어디서 갈리는지

## 무엇이 문제였나

`scout.py` 는 기술을 **서로 독립**이라고 보고 뽑았다. 한카리아스면
지진 67% · 용성군 30% · 스텔스록 40% 를 각각 동전 던지듯 뽑는다.
그러면 **AS형인데 용성군을 든 한카리아스** 가 태연히 나온다. 그런 건 없다.

사용자가 처음부터 지적한 것이 이것이다.

> 한카리아스는 AS형태일 경우엔 드래곤테일을 드는경우가 적고
> HB형태일 경우에 스텔스록과 함께 드는편이지

## 조합 정보가 정말로 없는가 — 없지 않았다

사용률에 조합은 없다. 노력치 배분 채용률과 기술 채용률이 **따로** 있을 뿐이다.
그런데 둘을 대조해 보면 관계가 드러난다.

    포켓몬        노력치 A형 : C형      공격기 물리 : 특수
    한카리아스     47 : 36              60 : 40
    보만다        70 : 18              69 : 31
    누리레느        0 : 34              30 : 70
    하마돈          0 :  0 (전부 내구)  100 :  0

**거의 맞아떨어진다.** 즉 "공격 투자한 놈이 물리기를 든다" 는 관계가
이미 가진 데이터 안에 들어 있다. 한 판도 안 뛰고 꺼낼 수 있다.

## 어떻게 꺼내는가

1. 배분을 **때리는 능력치 기준**으로만 가른다 — 물리형 / 특수형 / 양쪽 / 내구형.
   (HB냐 HD냐는 여기서 안 따진다. 기술 선택을 가르는 건 A·C 투자 여부다.)
2. 형태와 기술이 **얼마나 안 어울리는지** 를 승산에 곱한다 (`form_mismatch`).
3. 그렇게 갈라 놓고도 **섞으면 원래 채용률이 그대로 나오도록** 승산을 역산한다.

3번이 핵심이다. 갈라 놓기만 하면 원래 데이터를 망가뜨린 것이고,
원래 채용률을 지키면서 갈라야 데이터를 **해석**한 것이 된다.
맞았는지는 `report()` 맨 아랫줄에 오차로 찍어 준다.

## 덤 — 본 기술로 형태를 좁힌다

형태별 확률이 생기면 베이즈를 거꾸로 쓸 수 있다.
용성군을 쓰는 걸 봤으면 그놈은 특수형이다. 그러면 **아직 안 본 기술의
확률까지 같이 움직인다.** 이게 `form_posterior()` 다.
"""

import math
import paths
import re
import sys

import calc

# 노력치는 한 능력치에 최대 32다. 절반 이상 부었으면 '투자했다' 로 본다.
INVEST = 16

# 형태 이름. 사용자가 쓰는 말과 같게 둔다 — "AS형", "HB형" 의 그 표기다.
#
# 처음에는 A/C 만 봤는데, 도구 경향을 재 보니 **제일 센 축이 내구 ↔ 스피드**였다.
# 먹다남은음식은 내구형과 +0.69, 구애스카프는 스피드 투자와 +0.58 이다.
# A/C 만 보면 그 축이 통째로 안 보인다. 그래서 S 를 넣었다.
CLASS_ORDER = ["AS", "A", "CS", "C", "ACS", "AC", "S", "-"]
CLASS_KO = {"AS": "AS형", "A": "A형", "CS": "CS형", "C": "C형",
            "ACS": "ACS형", "AC": "AC형", "S": "S형", "-": "내구형"}

# 자기 어느 능력치로 때리는지가 설명문에 적혀 있는 기술이 있다.
#   바디프레스 — "이 기술은 공격이 아닌 방어 수치에 따라 데미지가 결정된다."
# (사이코쇼크의 "상대의 방어를 기준으로" 는 **맞는 쪽** 얘기라 여기 안 걸린다.)
_OWN_STAT = re.compile(r"공격이 아닌 ([가-힣]+) ?(?:수치|능력치)")
_STAT_BY_KO = {"공격": "attack", "방어": "defense", "특수공격": "spAtk",
               "특수방어": "spDef", "스피드": "speed"}


def attack_stat(move):
    """이 기술이 **내** 어느 능력치로 때리는가. 변화기면 None."""
    if move.get("category") == "변화":
        return None
    got = _OWN_STAT.search(move.get("description") or "")
    if got and got.group(1) in _STAT_BY_KO:
        return _STAT_BY_KO[got.group(1)]
    return "attack" if move.get("category") == "물리" else "spAtk"


# 때리기는 하지만 **데미지가 목적이 아닌** 기술이 있다.
# 드래곤테일(위력 60)은 강제 교체가 목적이라 공격 투자와 상관없이 들고 다닌다.
# 실제로 사용자가 짚은 예시가 이것이다 —
#   "한카리아스는 AS형태일 경우엔 드래곤테일을 드는경우가 적고
#    HB형태일 경우에 스텔스록과 함께 드는편이지"
# 이런 걸 물리기라는 이유로 물리형 쪽에 몰아 주면 **거꾸로 나온다.**
# 설명문에 강제 교체가 적혀 있는 것만 뺀다 (battle.move_effects 의 phaze 와 같은 글귀).
_PHAZE = re.compile(r"랜덤한 포켓몬으로 교체시킨다")


def form_neutral(move):
    """형태로 가르면 안 되는 기술인가."""
    return bool(_PHAZE.search(move.get("description") or ""))


def spread_class(sp):
    """노력치 배분(계산기 키)을 형태로 바꾼다."""
    sp = sp or {}
    a = sp.get("attack", 0) >= INVEST
    c = sp.get("spAtk", 0) >= INVEST
    s = sp.get("speed", 0) >= INVEST
    base = "AC" if (a and c) else ("A" if a else ("C" if c else ""))
    return (base + ("S" if s else "")) or "-"


def attack_part(cls):
    """형태에서 **때리는 능력치 부분만**. 기술 선택은 이것만 본다.

    AS형과 A형은 같은 기술을 든다. 스피드 투자는 기술이 아니라
    도구·성격을 가른다.
    """
    if cls in ("-", "S"):
        return "-"
    return cls[:-1] if cls.endswith("S") else cls


def entry_class(entry):
    """사용률의 노력치 항목(H/A/B/C/D/S 표기)을 형태로 바꾼다."""
    sp = {}
    for k, v in (entry.get("spread") or {}).items():
        if k in calc.SPREAD_KEY:
            sp[calc.SPREAD_KEY[k]] = v
    return spread_class(sp)


def class_weights(dex, poke):
    """형태별 비중. {형태: 확률}. 사용률이 없으면 빈 dict."""
    u = (dex.usage.get(poke["key"])
         or dex.usage.get("%04d-00" % poke["dexNo"]))
    if not u or not u.get("evs"):
        return {}
    out = {}
    for e in u["evs"]:
        out[entry_class(e)] = out.get(entry_class(e), 0.0) + e["pct"]
    total = sum(out.values())
    if total <= 0:
        return {}
    return dict((k, v / total) for k, v in out.items())


def compat(cls, move):
    """이 형태가 이 기술을 들 **승산 배율**. 1.0 이면 안 깎는다.

    안 맞는 정도는 `calc.CONFIG["form_mismatch"]` 다. **가정값이다.**
    사용률에는 조합이 없으므로 이 값 자체는 데이터로 확인할 수 없다.
    그래서 sensitivity.py 에 넣어 두고 답이 흔들리는지 따로 잰다.
    """
    bad = calc.CONFIG["form_mismatch"]
    stat = None if form_neutral(move) else attack_stat(move)
    if stat not in ("attack", "spAtk"):
        # 변화기 · 바디프레스 · 강제 교체기는 A·C 투자로 안 갈린다
        return 1.0
    ap = attack_part(cls)
    if ap == "AC":
        return 1.0
    if ap == "-":
        # 어느 쪽도 안 부은 내구형. 물리든 특수든 어중간하다.
        return bad ** 0.5
    return 1.0 if ap == ("A" if stat == "attack" else "C") else bad


def _solve_odds(kappas, weights, target):
    """섞었을 때 target 이 나오도록 승산 t 를 찾는다.

    형태 f 의 채용 확률은 승산으로 쓰면 그냥 곱이다.
        odds(f) = kappa(f) * t      ->      p(f) = kf*t / (kf*t + 1)
    섞은 값 Σ w_f p_f 는 t 에 대해 단조증가라, 로그 이분법으로 정확히 잡힌다.
    """
    def mix(t):
        return sum(w * (k * t) / (k * t + 1.0)
                   for k, w in zip(kappas, weights))

    if target <= 0.0:
        return 0.0
    lo, hi = 1e-12, 1e12
    if mix(hi) <= target:            # 1.0 에 가까운 목표 — 끝까지 올린다
        return hi
    for _ in range(200):
        mid = (lo * hi) ** 0.5
        if mix(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo * hi) ** 0.5



def _solve_row(kappas, mults, total):
    """그 형태가 쓰는 칸수가 total 이 되도록 행 배율을 찾는다. 역시 단조다."""
    def used(sv):
        return sum((k * m * sv) / (k * m * sv + 1.0)
                   for k, m in zip(kappas, mults))

    if total <= 0:
        return 0.0
    lo, hi = 1e-12, 1e12
    if used(hi) <= total:
        return hi
    for _ in range(200):
        mid = (lo * hi) ** 0.5
        if used(mid) < total:
            lo = mid
        else:
            hi = mid
    return (lo * hi) ** 0.5


def _fit(kappa, weights, targets, rounds=60):
    """형태별 채용 확률을 두 조건에 맞춘다.

    세로 — **섞으면 원래 채용률이 나온다.**
        Σ_i 비중[i] * p[i][j] == 채용률[j]
        이건 데이터가 시키는 조건이라 반드시 맞춰야 한다.

    가로 — **어느 형태든 이 목록에서 쓰는 칸수는 같다.**
        Σ_j p[i][j] == Σ_j 채용률[j]
        누구나 기술칸이 4개라는 사실에서 온다. 이게 없으면 내구형은
        공격기를 못 드는 만큼 **칸이 그냥 빈 채로** 남는다. 실제로는
        그 자리에 변화기가 들어간다 — 스텔스록이 그것이다.

    둘을 번갈아 맞춘다. 각각 단조라 이분법으로 정확히 잡히고,
    번갈아 하면 수렴한다. 얼마나 맞았는지는 mix_error 로 따로 잰다.
    """
    n_cls, n_mv = len(kappa), len(kappa[0]) if kappa else 0
    if not n_cls or not n_mv:
        return []
    col = [1.0] * n_mv          # 기술별 승산 배율
    row = [1.0] * n_cls         # 형태별 승산 배율
    slots = sum(targets)        # 이 목록이 먹는 칸수 (보통 3칸 안팎)

    for _ in range(rounds):
        for j in range(n_mv):
            ks = [kappa[i][j] * row[i] for i in range(n_cls)]
            col[j] = _solve_odds(ks, weights, targets[j])
        for i in range(n_cls):
            mults = [kappa[i][j] * col[j] for j in range(n_mv)]
            row[i] = _solve_row([1.0] * n_mv, mults, slots)

    out = []
    for i in range(n_cls):
        o = [kappa[i][j] * col[j] * row[i] for j in range(n_mv)]
        out.append([v / (v + 1.0) for v in o])
    return out


_TABLE_CACHE = {}


def conditional_table(dex, poke):
    """형태별 기술 채용 확률. **관측은 안 넣은 사전 분포다.**

    돌려주는 것: (형태 목록, 형태 비중, 기술 목록, 표)
    표[i][j] = 형태 i 가 기술 j 를 들고 있을 확률.

    조건은 하나다 — **섞으면 원래 채용률이 나온다.**
        Σ_i 비중[i] * 표[i][j] == 원래 채용률[j]
    """
    key = (poke["key"], calc.CONFIG["form_mismatch"], INVEST)
    hit = _TABLE_CACHE.get(key)
    if hit is not None:
        return hit

    wmap = class_weights(dex, poke)
    u = (dex.usage.get(poke["key"])
         or dex.usage.get("%04d-00" % poke["dexNo"]))
    moves = []
    targets = []
    if u and u.get("moves"):
        for entry in u["moves"]:
            mv = dex.move_by_id(entry["id"])
            if mv is not None:
                moves.append(mv)
                targets.append(min(1.0, entry["pct"] / 100.0))

    classes = [c for c in CLASS_ORDER if wmap.get(c, 0.0) > 0.0]
    weights = [wmap[c] for c in classes]
    if not classes or not moves:
        out = (classes, weights, moves, [])
        _TABLE_CACHE[key] = out
        return out

    kappa = [[compat(c, mv) for mv in moves] for c in classes]
    table = _fit(kappa, weights, targets)

    out = (classes, weights, moves, table)
    _TABLE_CACHE[key] = out
    return out


def probs_for_class(dex, poke, cls):
    """그 형태일 때의 (기술, 확률) 목록. 형태를 모르면 전체 채용률."""
    classes, weights, moves, table = conditional_table(dex, poke)
    if cls in classes and table:
        row = table[classes.index(cls)]
        return list(zip(moves, row))
    # 형태를 못 가르면 섞은 값 = 원래 채용률
    if not table:
        return []
    mixed = [sum(w * table[i][j] for i, w in enumerate(weights))
             for j in range(len(moves))]
    return list(zip(moves, mixed))



# ---------------------------------------------------------------------------
# 성격 — 규칙으로 갈린다
# ---------------------------------------------------------------------------
def nature_compat(cls, nature):
    """이 성격이 이 형태와 맞는가. **이건 규칙이다.**

    성격은 한 능력치를 1.1배, 다른 하나를 0.9배로 만든다.
    **자기가 때리는 능력치를 깎는 성격은 안 쓴다.** CS형 한카리아스가
    특수공격을 깎는 성격을 들 이유가 없다. 취향이 아니라 손해다.

    반대로 **안 쓰는 쪽을 깎는 것은 정상**이다 (CS형이 공격을 깎는 것).
    그래서 '깎는다' 가 아니라 '쓰는 걸 깎는다' 만 본다.
    """
    bad = calc.CONFIG["nature_mismatch"]
    down = (nature or {}).get("down")
    if not down:
        return 1.0
    ap = attack_part(cls)
    k = 1.0
    if down == "attack" and ap in ("A", "AC"):
        k *= bad
    if down == "spAtk" and ap in ("C", "AC"):
        k *= bad
    if down == "speed" and cls.endswith("S"):
        k *= bad
    return k


# ---------------------------------------------------------------------------
# 도구 — 규칙이 없다. 그래서 **데이터에서 잰다.**
# ---------------------------------------------------------------------------
#
# 기술은 "물리기는 공격으로 때린다" 는 규칙이 방향을 줬다. 도구에는 그런 게 없다.
# 챔피언스에는 공격/특공을 확정 짓는 도구가 힘의머리띠·박식안경 둘뿐이고,
# 상위 20마리 채용률이 0.0% 다. (구애머리띠·구애안경·돌격조끼는 아예 없다.)
#
# 그래도 경향은 잴 수 있다. 한 포켓몬 안에서는 조합을 못 보지만,
# **포켓몬끼리 비교**는 된다 — 먹다남은음식을 많이 쓰는 포켓몬이 내구형
# 비중도 높은가. 263마리로 재면 이렇게 나온다.
#
#     먹다남은음식  내구형 +0.69   스피드 -0.59
#     울퉁불퉁멧    내구형 +0.62   스피드 -0.54
#     구애스카프    스피드 +0.58   내구형 -0.41
#     생명의구슬    내구형 -0.43   물리형 +0.28
#     풍선         내구형 +0.03   ← 아무 경향 없음
#
# 마지막 줄이 중요하다. 이 측정은 **아무거나 다 맞다고 해 주지 않는다.**
# 풍선은 '땅 기술 무효' 라 뭔가 경향이 있을 것 같지만, 재 보면 없다.
#
# ! 한계를 분명히 해 둔다. 이건 **포켓몬끼리의 상관**이지 한 포켓몬 안의
#   상관이 아니다. "내구형 포켓몬이 먹다남은음식을 쓴다" 는 잰 것이고,
#   "이 한카리아스가 HB 배분일 때 먹다남은음식을 쓴다" 는 **가정**이다.
#   다만 방향은 데이터가 정했고, 세기는 CONFIG 에 두고 감도를 잰다.
#   그리고 섞으면 원래 도구 채용률이 그대로 나오도록 맞추므로 피해가 갇힌다.

_MIN_POKE = 15          # 이 도구를 쓰는 포켓몬이 이만큼은 돼야 상관을 믿는다
_TENDENCY = None


def _ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def _corr(ra, rb):
    n = len(ra)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = sum((x - ma) ** 2 for x in ra) ** 0.5
    db = sum((y - mb) ** 2 for y in rb) ** 0.5
    return num / (da * db) if da and db else 0.0


def item_tendency(dex):
    """도구가 어느 형태에 쏠리는지 데이터에서 잰다. {도구: {형태: 상관}}."""
    global _TENDENCY
    if _TENDENCY is not None:
        return _TENDENCY

    rows = []
    for u in dex.usage.values():
        evs, items = u.get("evs"), u.get("items")
        tot_ev = sum(e["pct"] for e in evs or [])
        tot_it = sum(i["pct"] for i in items or [])
        if tot_ev <= 0 or tot_it <= 0:
            continue
        share = {}
        for e in evs:
            c = entry_class(e)
            share[c] = share.get(c, 0.0) + e["pct"] / tot_ev
        rows.append((share,
                     dict((i["name"], i["pct"] / tot_it) for i in items)))

    out = {}
    if len(rows) < 30:
        _TENDENCY = out
        return out

    cls_ranks = {}
    for c in CLASS_ORDER:
        col = [r[0].get(c, 0.0) for r in rows]
        if sum(1 for v in col if v > 0) >= _MIN_POKE:
            cls_ranks[c] = _ranks(col)

    names = set()
    for _, it in rows:
        names.update(it)
    for name in names:
        col = [it.get(name, 0.0) for _, it in rows]
        if sum(1 for v in col if v > 0) < _MIN_POKE:
            continue          # 표본이 적으면 상관을 안 믿는다
        rk = _ranks(col)
        out[name] = dict((c, _corr(rk, cr)) for c, cr in cls_ranks.items())
    _TENDENCY = out
    return out


def item_compat(dex, cls, item_name):
    """이 도구가 이 형태에 붙을 **승산 배율**.

    두 가지가 따로 논다.
      · 메가스톤 — **메가 폼의 종족값**이 정한다. 상관이 아니다
        (메가스톤은 한 포켓몬만 쓰므로 포켓몬끼리 비교할 수가 없다).
      · 그 밖의 도구 — 위에서 잰 상관을 쓴다.
    """
    if not item_name:
        return 1.0
    mega = dex.mega_by_item.get(item_name)
    if mega:
        b = mega.get("baseStats") or {}
        gap = (b.get("attack", 0) - b.get("spAtk", 0)) / 100.0
        ap = attack_part(cls)
        if ap == "A":
            sign = 1.0
        elif ap == "C":
            sign = -1.0
        else:
            return 1.0        # 양쪽형·내구형은 어느 메가와도 어울린다
        return math.exp(calc.CONFIG["mega_stat_strength"] * gap * sign)

    corr = item_tendency(dex).get(item_name, {}).get(cls)
    if corr is None:
        return 1.0
    return math.exp(calc.CONFIG["item_tendency_strength"] * corr)


# ---------------------------------------------------------------------------
# 하나만 고르는 것(성격·도구)을 형태별로 가른다
# ---------------------------------------------------------------------------
def _fit_categorical(kappa, weights, targets, rounds=300):
    """기술과 달리 **딱 하나만** 고르는 것들을 맞춘다.

    기술은 4칸에 독립으로 들어가므로 기술마다 승산 하나씩 풀면 됐다.
    성격·도구는 하나만 고르므로 각 형태의 확률 합이 1 이어야 한다.
    조건이 둘이라 번갈아 맞춘다 (표 맞추기).

      가로 — 각 형태에서 확률 합이 1
      세로 — 섞으면 원래 채용률이 나온다
    """
    n, m = len(kappa), len(targets)
    if not n or not m:
        return []
    q = [[max(1e-12, targets[j]) * kappa[i][j] for j in range(m)]
         for i in range(n)]
    for _ in range(rounds):
        for i in range(n):
            tot = sum(q[i]) or 1.0
            for j in range(m):
                q[i][j] /= tot
        for j in range(m):
            got = sum(weights[i] * q[i][j] for i in range(n))
            if got <= 0:
                continue
            f = targets[j] / got
            for i in range(n):
                q[i][j] *= f
    for i in range(n):
        tot = sum(q[i]) or 1.0
        for j in range(m):
            q[i][j] /= tot
    return q


_PICK_CACHE = {}


def _pick_table(dex, poke, kind):
    """형태별로 성격(또는 도구)을 고를 확률. (형태, 항목, 표)."""
    key = (poke["key"], kind, calc.CONFIG["nature_mismatch"],
           calc.CONFIG["item_tendency_strength"],
           calc.CONFIG["mega_stat_strength"])
    hit = _PICK_CACHE.get(key)
    if hit is not None:
        return hit

    u = (dex.usage.get(poke["key"])
         or dex.usage.get("%04d-00" % poke["dexNo"]))
    wmap = class_weights(dex, poke)
    entries = (u or {}).get(kind) or []
    total = sum(e["pct"] for e in entries)
    classes = [c for c in CLASS_ORDER if wmap.get(c, 0.0) > 0.0]
    if not classes or total <= 0:
        out = (classes, entries, [])
        _PICK_CACHE[key] = out
        return out

    weights = [wmap[c] for c in classes]
    targets = [e["pct"] / total for e in entries]
    if kind == "natures":
        kappa = [[nature_compat(c, e) for e in entries] for c in classes]
    else:
        kappa = [[item_compat(dex, c, e["name"]) for e in entries]
                 for c in classes]
    out = (classes, entries, _fit_categorical(kappa, weights, targets))
    _PICK_CACHE[key] = out
    return out


def nature_table(dex, poke):
    return _pick_table(dex, poke, "natures")


def item_table(dex, poke):
    return _pick_table(dex, poke, "items")


def pick_dist(dex, poke, kind, cls):
    """그 형태일 때 (항목, 확률) 목록. 형태를 모르면 원래 채용률."""
    classes, entries, table = _pick_table(dex, poke, kind)
    if not entries:
        return []
    if not table:
        total = sum(e["pct"] for e in entries) or 1.0
        return [(e, e["pct"] / total) for e in entries]
    if cls in classes:
        row = table[classes.index(cls)]
        return list(zip(entries, row))
    wmap = class_weights(dex, poke)
    mixed = [sum(wmap.get(c, 0.0) * table[i][j] for i, c in enumerate(classes))
             for j in range(len(entries))]
    return list(zip(entries, mixed))


def pick_error(dex, poke, kind):
    """섞은 값이 원래 채용률과 얼마나 어긋나는가."""
    classes, entries, table = _pick_table(dex, poke, kind)
    if not table:
        return 0.0
    wmap = class_weights(dex, poke)
    total = sum(e["pct"] for e in entries) or 1.0
    worst = 0.0
    for j, e in enumerate(entries):
        got = sum(wmap.get(c, 0.0) * table[i][j]
                  for i, c in enumerate(classes))
        worst = max(worst, abs(got - e["pct"] / total))
    return worst

def form_posterior(dex, poke, seen_moves, item=None):
    """본 것으로 형태를 좁힌다. {형태: 사후 확률}.

    용성군을 쓰는 걸 봤으면 특수형 쪽으로 확 쏠린다. 그러면 **아직 안 본
    기술의 확률까지 같이 움직인다** — 그게 이걸 만든 이유다.
    도구를 봤으면 그것도 같이 넣는다.
    """
    classes, weights, moves, table = conditional_table(dex, poke)
    if not classes:
        return {}
    post = list(weights)
    seen = set(seen_moves or ())
    if seen and table:
        for j, mv in enumerate(moves):
            if mv["name"] not in seen:
                continue
            for i in range(len(classes)):
                post[i] *= table[i][j]
    # 도구를 봤으면 그것도 증거다. 메가스톤이 특히 세다 —
    # 메가리자몽Y(특공159, 공격104)를 봤으면 그놈은 특수형이다.
    if item:
        icls, ientries, itable = _pick_table(dex, poke, "items")
        for j, e in enumerate(ientries):
            if e["name"] != item or not itable:
                continue
            for i, c in enumerate(classes):
                if c in icls:
                    post[i] *= itable[icls.index(c)][j]
    total = sum(post)
    if total <= 0:
        return dict(zip(classes, weights))
    return dict((c, p / total) for c, p in zip(classes, post))


def mix_error(dex, poke):
    """섞은 값이 원래 채용률과 얼마나 어긋나는가 (최대 오차, 0~1)."""
    classes, weights, moves, table = conditional_table(dex, poke)
    if not table:
        return 0.0
    u = (dex.usage.get(poke["key"])
         or dex.usage.get("%04d-00" % poke["dexNo"]))
    by_id = dict((e["id"], e["pct"] / 100.0) for e in u["moves"])
    worst = 0.0
    for j, mv in enumerate(moves):
        got = sum(w * table[i][j] for i, w in enumerate(weights))
        worst = max(worst, abs(got - by_id.get(mv["id"], 0.0)))
    return worst


def spread_range(dex, poke, cls):
    """그 형태에 속한 노력치 항목만. (항목, 그 안에서의 확률) 목록."""
    u = (dex.usage.get(poke["key"])
         or dex.usage.get("%04d-00" % poke["dexNo"]))
    if not u or not u.get("evs"):
        return []
    rows = [e for e in u["evs"] if entry_class(e) == cls]
    total = sum(e["pct"] for e in rows)
    if total <= 0:
        return []
    return [(e, e["pct"] / total) for e in rows]


# ---------------------------------------------------------------------------
# 보고서
# ---------------------------------------------------------------------------
def report(dex, poke, top=12, seen=None):
    import best

    seen = set(seen or ())
    classes, weights, moves, table = conditional_table(dex, poke)
    L = []
    line = "=" * 78
    L.append(line)
    L.append("  %s — 형태별로 무슨 기술을 드는가" % poke["name"])
    L.append(line)
    if not classes:
        L.append("  사용률 자료가 없다.")
        L.append(line)
        return "\n".join(L)

    post = form_posterior(dex, poke, seen)
    shown = [post.get(c, 0.0) for c in classes] if seen else list(weights)
    if seen:
        L.append("  본 것: %s" % ", ".join(sorted(seen)))
    L.append("  형태 비중   " + "   ".join(
        "%s %.0f%%" % (CLASS_KO[c], w * 100) for c, w in zip(classes, shown)))
    if seen:
        L.append("  (본 것 없을 때: " + "  ".join(
            "%s %.0f%%" % (CLASS_KO[c], w * 100)
            for c, w in zip(classes, weights)) + ")")
    if len(classes) == 1:
        L.append("  ! 형태가 하나뿐이라 갈라지지 않는다 — 전체 채용률 그대로다.")
    L.append("-" * 78)

    head = [("기술", 16), ("전체", 9)]
    if seen:
        head.append(("지금", 9))
    head += [(CLASS_KO[c], 9) for c in classes]
    L.append("  " + "".join(best._pad(h, w) for h, w in head).rstrip())

    def mixed_at(j, ws):
        return sum(ws[i] * table[i][j] for i in range(len(classes)))

    order = sorted(range(len(moves)), key=lambda j: -mixed_at(j, weights))
    for j in order[:top]:
        base = mixed_at(j, weights)
        cells = [moves[j]["name"], "%.1f%%" % (base * 100)]
        mark = ""
        if seen:
            now = 1.0 if moves[j]["name"] in seen else mixed_at(j, shown)
            cells.append("%.1f%%" % (now * 100))
            if moves[j]["name"] in seen:
                mark = "   ← 봤다"
            elif now > base + 0.03:
                mark = "   ↑"
            elif now < base - 0.03:
                mark = "   ↓"
        cells += ["%.0f%%" % (table[i][j] * 100) for i in range(len(classes))]
        col = [table[i][j] for i in range(len(classes))]
        if not seen and max(col) - min(col) >= 0.30:
            mark = "   ← 형태로 갈린다"
        L.append("  " + "".join(best._pad(c, w)
                                for c, (h, w) in zip(cells, head)).rstrip()
                 + mark)

    # 성격과 도구도 형태로 갈린다
    for kind, title in (("natures", "성격"), ("items", "도구")):
        kclasses, entries, ktable = _pick_table(dex, poke, kind)
        if not ktable:
            continue
        L.append("-" * 78)
        khead = [(title, 16), ("전체", 9)] + [(CLASS_KO[c], 9) for c in kclasses]
        L.append("  " + "".join(best._pad(h, w) for h, w in khead).rstrip())
        tot = sum(e["pct"] for e in entries) or 1.0
        for j, e in enumerate(entries[:6]):
            cells = [e["name"], "%.1f%%" % (e["pct"] / tot * 100)]
            cells += ["%.0f%%" % (ktable[i][j] * 100)
                      for i in range(len(kclasses))]
            col = [ktable[i][j] for i in range(len(kclasses))]
            hi = max(col)
            # 채용률이 아주 낮은 것은 비율이 튀므로 표시하지 않는다
            mark = ""
            if e["pct"] / tot >= 0.03 and hi > 1.6 * (sum(col) / len(col)):
                mark = "   ← %s 쪽" % CLASS_KO[kclasses[col.index(hi)]]
            L.append("  " + "".join(best._pad(c, w)
                                    for c, (h, w) in zip(cells, khead)).rstrip()
                     + mark)

    L.append("-" * 78)
    L.append("  섞으면 원래 채용률이 그대로 나온다 — 최대 오차 기술 %.2f%%p"
             " · 성격 %.2f%%p · 도구 %.2f%%p"
             % (mix_error(dex, poke) * 100,
                pick_error(dex, poke, "natures") * 100,
                pick_error(dex, poke, "items") * 100))
    L.append("  (가정값 — 기술 %.2f · 성격 %.2f · 도구 세기 %.1f · 메가 세기 %.1f)"
             % (calc.CONFIG["form_mismatch"], calc.CONFIG["nature_mismatch"],
                calc.CONFIG["item_tendency_strength"],
                calc.CONFIG["mega_stat_strength"]))
    L.append(line)
    return "\n".join(L)


def survey(dex, count=30):
    """상위 몇 마리에서 실제로 형태가 갈리는지 — 1-A 가 얼마나 벌어 줬나."""
    import best

    rows = []
    for u in sorted(dex.usage.values(), key=lambda x: x.get("rank") or 999):
        if u.get("rank") is None or u["rank"] > count:
            continue
        try:
            poke = dex.find_pokemon(u["name"])
        except LookupError:
            continue
        classes, weights, moves, table = conditional_table(dex, poke)
        if not table:
            continue
        worst = 0.0
        for j in range(len(moves)):
            col = [table[i][j] for i in range(len(classes))]
            worst = max(worst, max(col) - min(col))
        rows.append((u["rank"], u["name"], classes, weights, worst,
                     mix_error(dex, poke)))
    rows.sort(key=lambda r: -r[4])

    L = []
    line = "=" * 78
    L.append(line)
    L.append("  형태로 기술이 갈리는 포켓몬 — 상위 %d마리" % count)
    L.append(line)
    head = [("", 4), ("포켓몬", 14), ("형태", 34), ("제일 크게 갈린 기술", 20)]
    L.append("  " + "".join(best._pad(h, w) for h, w in head).rstrip())
    split = 0
    for rank, name, classes, weights, worst, err in rows:
        forms = " ".join("%s%.0f%%" % (CLASS_KO[c][:2], w * 100)
                         for c, w in zip(classes, weights))
        cells = [str(rank), name, forms, "%.0f%%p" % (worst * 100)]
        L.append("  " + "".join(best._pad(c, w)
                                for c, (h, w) in zip(cells, head)).rstrip())
        if worst >= 0.30:
            split += 1
    L.append("-" * 78)
    L.append("  %d / %d 마리가 형태로 갈린다 (제일 큰 차이 30%%p 이상 기준)"
             % (split, len(rows)))
    L.append("  섞었을 때 원래 채용률과의 최대 오차: %.2f%%p"
             % (max(r[5] for r in rows) * 100 if rows else 0.0))
    L.append(line)
    return "\n".join(L)


def main():
    paths.fix_console()   # 윈도우에서 한글을 찍다 죽지 않게
    dex = calc.Dex()
    argv = sys.argv[1:]
    names, seen = [], []
    bucket = names
    for a in argv:
        if a == "--봤다":
            bucket = seen
            continue
        bucket.append(a)
    if not names:
        print(survey(dex))
        return
    for name in names:
        print(report(dex, dex.find_pokemon(name), seen=seen))


if __name__ == "__main__":
    main()
