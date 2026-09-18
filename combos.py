# -*- coding: utf-8 -*-
"""
1-C — 표본으로 기술 구성을 고친다. 두 가지를 고친다.

    python combos.py 한카리아스
    python combos.py                 # 표본이 충분한 포켓몬 목록

## 고치는 것 1 — 사용률 목록 밖의 기술

사용률 자료에는 포켓몬마다 **기술 상위 10개**만 있다. 그런데 표본을 세 보니
한카리아스가 실제로 쓴 기술 456회 중 **목록 안이 323회(71%)** 뿐이었다.

    목록 밖인데 많이 쓰인 것: 칼춤 25 · 압정뿌리기 22 · 불꽃엄니 17 · 독찌르기 15

즉 지금 모델에서 **칼춤 한카리아스는 확률이 0 이다.** 나올 수가 없다.
실제로는 랭커 표본의 22% 가 들고 있다.

그러면 목록 밖 기술에 확률을 얼마나 줘야 하나. **사용률이 답을 알고 있다.**
한카리아스 상위 10개의 채용률 합이 298% 이고 기술칸은 4개(400%)다.
차이인 **102% 가 목록 밖 기술들의 몫**이다. 얼마인지는 사용률이 알려 주고,
**누구에게 줄지는 표본이 알려 준다.**

    한카리아스 표본의 목록 밖 비율 117%  vs  사용률이 남긴 예산 102%
    -> 15% 안에서 맞는다. 랭커 쪽이 조금 더 많이 쓰는 셈이다.

## 고치는 것 2 — 기술끼리의 조합

1-A 는 형태를 가른 뒤 기술을 **서로 독립**으로 뽑았다. 그런데 표본을 재 보니
독립이 아니었다.

    드래곤테일 + 스텔스록   리프트 1.81   같이 든다
    드래곤테일 + 역린       리프트 0.10   서로 안 든다

둘 다 물리 드래곤 기술인데 114마리 중 한 번만 같이 나왔다. 형태로는 안
갈리는 것이 **다른 기술과의 관계로는 갈린다.**

쌍을 하나하나 넣는 대신 **원형(原型)** 으로 본다. 실제 구성은 두세 갈래로
뭉쳐 있기 때문이다.

    유틸형   드래곤테일 + 스텔스록 + 압정뿌리기
    공격형   스케일샷 + 칼춤 + 역린

표본에서 그 갈래를 찾아낸다 (베르누이 혼합, EM). 갈래 개수는 BIC 로 고른다.

## 1-A 와 같은 원칙을 지킨다

**구조는 표본에서, 수준은 사용률에서.**

EM 이 알려 주는 것은 "어느 기술이 어느 갈래에 뭉치나" 라는 **구조**다.
그 구조를 승산비로 뽑아내고, **섞으면 사용률 채용률이 그대로 나오도록**
다시 맞춘다 (1-A 에서 쓴 것과 같은 표 맞추기).

이유는 1-B 와 같다 — 표본은 랭커가 쓴 것이라 래더 전체가 아니다.
조합은 표본을 믿고, 비율은 사용률을 믿는다.
"""

import math
import random
import sys

import calc
import forms
import samples

SLOTS = 4
MIN_SAMPLES = 25        # 이만큼은 있어야 갈래를 찾는 의미가 있다
MIN_SEEN = 3            # 목록 밖 기술은 이만큼은 나와야 넣는다
MAX_K = 3               # 갈래는 최대 세 개까지만 (표본이 그 이상을 못 받친다)


# ---------------------------------------------------------------------------
# 어휘 — 무엇을 후보로 볼 것인가
# ---------------------------------------------------------------------------
def vocabulary(dex, poke, rows):
    """(기술, 목표 채용률, 출처) 목록.

    목록 안은 사용률 그대로. 목록 밖은 **사용률이 남긴 예산**을
    표본 비율대로 나눠 준다.
    """
    u = (dex.usage.get(poke["key"])
         or dex.usage.get("%04d-00" % poke["dexNo"]))
    if not u or not u.get("moves"):
        return []

    inside = []
    seen_ids = set()
    for e in u["moves"]:
        mv = dex.move_by_id(e["id"])
        if mv is None:
            continue
        inside.append((mv, min(1.0, e["pct"] / 100.0), "사용률"))
        seen_ids.add(mv["id"])

    budget = SLOTS - sum(p for _, p, _ in inside)
    if budget <= 0.01 or not rows:
        return inside

    # 표본에서 목록 밖 기술을 센다
    out = {}
    for m in rows:
        for x in m["moves"]:
            if x["id"] in seen_ids:
                continue
            out.setdefault(x["id"], [x, 0])
            out[x["id"]][1] += 1
    out = dict((k, v) for k, v in out.items() if v[1] >= MIN_SEEN)
    total = sum(v[1] for v in out.values())
    if not total:
        return inside

    extra = []
    for mv, cnt in out.values():
        extra.append((mv, budget * cnt / float(total), "표본"))
    extra.sort(key=lambda r: -r[1])
    return inside + extra


# ---------------------------------------------------------------------------
# 갈래 찾기 — 베르누이 혼합 (EM)
# ---------------------------------------------------------------------------
def _vectors(rows, moves):
    idx = dict((mv["id"], j) for j, mv in enumerate(moves))
    out = []
    for m in rows:
        v = [0] * len(moves)
        for x in m["moves"]:
            j = idx.get(x["id"])
            if j is not None:
                v[j] = 1
        if any(v):
            out.append(v)
    return out


def fit_mixture(vectors, k, rounds=250, seed=1):
    """베르누이 혼합을 EM 으로 맞춘다. (갈래 비중, 갈래별 기술 확률).

    초기값을 난수로 두면 돌릴 때마 답이 바뀐다. **제일 멀리 떨어진 표본들**
    을 씨앗으로 써서 같은 답이 나오게 한다.
    """
    n, m = len(vectors), len(vectors[0])
    if k <= 1:
        p = [[sum(v[j] for v in vectors) / float(n) for j in range(m)]]
        return [1.0], p

    # 씨앗: 첫 하나는 아무거나, 다음은 이미 고른 것들과 제일 다른 것
    rng = random.Random(seed)
    seeds = [max(range(n), key=lambda i: sum(vectors[i]))]
    while len(seeds) < k:
        def far(i):
            return min(sum(a != b for a, b in zip(vectors[i], vectors[s]))
                       for s in seeds)
        seeds.append(max(range(n), key=far))

    eps = 1e-6
    p = [[min(1 - eps, max(eps, float(vectors[s][j]))) for j in range(m)]
         for s in seeds]
    w = [1.0 / k] * k
    prev = None
    for _ in range(rounds):
        # E
        resp = []
        for v in vectors:
            lg = []
            for i in range(k):
                s = math.log(max(eps, w[i]))
                for j in range(m):
                    s += (math.log(p[i][j]) if v[j]
                          else math.log(1.0 - p[i][j]))
                lg.append(s)
            top = max(lg)
            ex = [math.exp(x - top) for x in lg]
            tot = sum(ex) or 1.0
            resp.append([x / tot for x in ex])
        # M
        for i in range(k):
            mass = sum(r[i] for r in resp) or eps
            w[i] = mass / n
            for j in range(m):
                num = sum(r[i] * v[j] for r, v in zip(resp, vectors))
                p[i][j] = min(1 - eps, max(eps, num / mass))
        ll = sum(math.log(max(eps, sum(
            w[i] * math.exp(sum((math.log(p[i][j]) if v[j]
                                 else math.log(1.0 - p[i][j]))
                                for j in range(m)))
            for i in range(k)))) for v in vectors)
        if prev is not None and abs(ll - prev) < 1e-7:
            break
        prev = ll
    return w, p


def _loglik(vectors, w, p):
    eps = 1e-12
    total = 0.0
    for v in vectors:
        s = 0.0
        for i in range(len(w)):
            t = w[i]
            for j in range(len(v)):
                t *= p[i][j] if v[j] else (1.0 - p[i][j])
            s += t
        total += math.log(max(eps, s))
    return total


def pick_k(vectors, max_k=MAX_K):
    """갈래를 몇 개로 볼 것인가. BIC 로 고른다 — 많을수록 잘 맞지만 벌점이 있다."""
    n, m = len(vectors), len(vectors[0])
    best = None
    for k in range(1, max_k + 1):
        if n < k * 12:            # 갈래당 열두 마리는 있어야 한다
            break
        w, p = fit_mixture(vectors, k)
        params = k * m + (k - 1)
        bic = -2 * _loglik(vectors, w, p) + params * math.log(n)
        if best is None or bic < best[0]:
            best = (bic, k, w, p)
    if best is None:
        w, p = fit_mixture(vectors, 1)
        return 1, w, p
    return best[1], best[2], best[3]


# ---------------------------------------------------------------------------
# 구조는 표본에서, 수준은 사용률에서
# ---------------------------------------------------------------------------
_CACHE = {}
_PARTIES = None


def loaded(dex):
    global _PARTIES
    if _PARTIES is None:
        _PARTIES, _ = samples.load(dex)
    return _PARTIES


def archetypes(dex, poke):
    """(기술 목록, 갈래 비중, 표, 출처 목록). 표본이 모자라면 None.

    표[i][j] = 갈래 i 가 기술 j 를 들고 있을 확률.
    **섞으면 사용률 채용률이 그대로 나온다** — 그게 이 함수의 조건이다.
    """
    key = (poke["key"], calc.CONFIG["form_mismatch"])
    if key in _CACHE:
        return _CACHE[key]

    rows = samples.by_pokemon(loaded(dex)).get(poke["name"]) or []
    if len(rows) < MIN_SAMPLES:
        _CACHE[key] = None
        return None
    vocab = vocabulary(dex, poke, rows)
    if not vocab:
        _CACHE[key] = None
        return None

    moves = [mv for mv, _, _ in vocab]
    targets = [t for _, t, _ in vocab]
    where = [w for _, _, w in vocab]
    vectors = _vectors(rows, moves)
    if len(vectors) < MIN_SAMPLES:
        _CACHE[key] = None
        return None

    k, w, p = pick_k(vectors)

    # EM 이 준 것은 **구조**다. 그 구조를 승산비로 뽑아내고,
    # 섞으면 사용률이 나오도록 다시 맞춘다 (1-A 와 같은 방식).
    eps = 1e-6
    mixed = [sum(w[i] * p[i][j] for i in range(k)) for j in range(len(moves))]
    kappa = []
    for i in range(k):
        row = []
        for j in range(len(moves)):
            a = min(1 - eps, max(eps, p[i][j]))
            b = min(1 - eps, max(eps, mixed[j]))
            row.append((a / (1 - a)) / (b / (1 - b)))
        kappa.append(row)
    table = forms._fit(kappa, w, targets)

    out = (moves, w, table, where)
    _CACHE[key] = out
    return out


def probs_for_archetype(dex, poke, which):
    """그 갈래일 때의 (기술, 확률) 목록."""
    got = archetypes(dex, poke)
    if not got:
        return []
    moves, w, table, _ = got
    if which is None or not (0 <= which < len(table)):
        mixed = [sum(w[i] * table[i][j] for i in range(len(w)))
                 for j in range(len(moves))]
        return list(zip(moves, mixed))
    return list(zip(moves, table[which]))


def mix_error(dex, poke):
    """섞은 값이 사용률과 얼마나 어긋나는가."""
    got = archetypes(dex, poke)
    if not got:
        return 0.0
    moves, w, table, _ = got
    rows = samples.by_pokemon(loaded(dex)).get(poke["name"]) or []
    targets = dict((mv["id"], t) for mv, t, _ in vocabulary(dex, poke, rows))
    worst = 0.0
    for j, mv in enumerate(moves):
        got_p = sum(w[i] * table[i][j] for i in range(len(w)))
        worst = max(worst, abs(got_p - targets.get(mv["id"], 0.0)))
    return worst


def archetype_posterior(dex, poke, seen_moves):
    """본 기술로 갈래를 좁힌다. [갈래별 사후확률]."""
    got = archetypes(dex, poke)
    if not got:
        return []
    moves, w, table, _ = got
    seen = set(seen_moves or ())
    post = list(w)
    if seen:
        for j, mv in enumerate(moves):
            if mv["name"] not in seen:
                continue
            for i in range(len(post)):
                post[i] *= table[i][j]
    tot = sum(post)
    return [x / tot for x in post] if tot > 0 else list(w)


# ---------------------------------------------------------------------------
# "이 기술이 갈래를 가르는가" 를 재는 자
# ---------------------------------------------------------------------------
#
# **한 번 잘못 잰 자다. 기록으로 남긴다.**
#
# 처음에는 `max - min`(제일 높은 갈래와 제일 낮은 갈래의 차이) 를 썼다.
# 이건 두 가지를 한 숫자에 뭉개 놓은 것이었다 —
#     (ㄱ) 그 기술을 **실제로 쓰는가**            (채용률이 높은가)
#     (ㄴ) 다른 갈래는 **안 쓰는가**              (갈래끼리 갈라지는가)
# 한카리아스 지진은 [0.75, 0.68, 0.00] 이다. 폭은 0.75 로 크지만 1등과
# 2등이 사실상 같다 — 갈래를 안 가른다. 역린은 [0.43, 0.02, 0.00] 으로
# 폭이 0.43 밖에 안 되지만 1등만 쓴다. 폭으로 재면 지진이 역린보다
# "갈래를 잘 가르는" 기술이 된다. 뒤집혀 있었다.
#
# 다음으로 `max / 2등` 을 생각했는데, 이것도 재 보니 못 쓴다.
# 표본 362칸 중 **140칸(39%)에서 2등이 0** 이라 배수가 무한이 된다.
# 블래키 배턴터치는 [0.07, 0.00, 0.00] 이라 배수가 186만이지만,
# 제일 센 갈래에서조차 7% 밖에 안 쓰는 기술이다. 배수만 보면
# "완벽하게 갈린다" 고 나온다. 이번엔 (ㄱ)을 통째로 버린 것이다.
#
# 그래서 **2등에 바닥을 깔았다.**
#
#     갈래도 = max / (2등 + 0.05)
#
# 0.05 는 "이 아래 채용률은 표본으로 0 과 구별이 안 된다" 는 바닥이다.
# 이 바닥이 두 가지를 동시에 해 준다 —
#   · 2등이 0 이어도 무한이 안 된다. 값이 max/0.05 = max×20 에서 멈춘다.
#     그래서 채용률 3% 짜리 기술은 아무리 갈려도 0.6 을 못 넘는다. (ㄱ) 회복.
#   · 2등이 1등만큼 크면 값이 1 근처로 떨어진다. (ㄴ) 유지.
#
# 재 본 결과 (표본 3,936마리 · 29종 · 362칸):
#     한카리아스 지진   0.75 / 0.68 -> 1.0    안 가름  (맞다)
#     한카리아스 역린   0.43 / 0.02 -> 6.0    가름     (맞다)
#     블래키  배턴터치  0.07 / 0.00 -> 1.4    안 가름  (맞다)
#     한카리아스 스텔스록 0.97 / 0.11 -> 6.1   가름     (맞다)
# 그리고 **갈래가 두 개 이상 잡힌 29종 전부**에서 제일 높은 기술의
# 갈래도가 5.2 이상이었다 (제일 낮은 게 하마돈 방어 5.2). 그러니
# 문턱 3 은 29종 어디에도 여유가 있다 — 한 마리에 맞춘 값이 아니다.
SPLIT_FLOOR = 0.05      # 2등에 까는 바닥
SPLIT_MIN = 3.0         # 이만하면 "갈래를 가른다" 고 본다


def split_score(column):
    """한 기술의 갈래별 채용률 목록 -> 갈래도.

    column 은 [갈래1 채용률, 갈래2 채용률, ...] 이다.
    """
    col = sorted(column, reverse=True)
    if len(col) < 2:
        return 0.0
    return col[0] / (col[1] + SPLIT_FLOOR)


def split_moves(dex, poke, least=SPLIT_MIN):
    """갈래를 가르는 기술들. [(기술이름, 갈래도, 제일 센 갈래)] 내림차순."""
    got = archetypes(dex, poke)
    if not got:
        return []
    moves, w, table, _ = got
    if len(w) < 2:
        return []
    out = []
    for j, mv in enumerate(moves):
        col = [table[i][j] for i in range(len(w))]
        s = split_score(col)
        if s >= least:
            out.append((mv["name"], s, col.index(max(col))))
    out.sort(key=lambda x: -x[1])
    return out


def label(dex, poke, which, top=3):
    """갈래에 이름 대신 대표 기술을 붙여 준다."""
    got = archetypes(dex, poke)
    if not got:
        return ""
    moves, w, table, _ = got
    mixed = [sum(w[i] * table[i][j] for i in range(len(w)))
             for j in range(len(moves))]
    # 전체보다 유난히 높은 기술이 그 갈래의 특징이다
    order = sorted(range(len(moves)),
                   key=lambda j: -(table[which][j] - mixed[j]))
    return " + ".join(moves[j]["name"] for j in order[:top])



# ---------------------------------------------------------------------------
# 형태와 갈래를 일관되게 잇는다
# ---------------------------------------------------------------------------
#
# 형태(노력치)와 갈래(기술 구성)는 따로 뽑으면 안 된다. 2번 갈래는 특수기만
# 드는데 AS 배분이 붙으면 말이 안 되는 놈이 나온다.
#
# 그런데 그냥 표본의 (형태, 갈래) 비율을 쓰면 **마진이 망가진다.**
# 표본은 랭커 것이라 내구형 한카리아스가 사용률의 2.4배다 (41% vs 17%).
#
# 그래서 1-A·1-B 에서 쓴 것과 같은 방법을 쓴다.
#   가로 — 각 형태에서 갈래 확률의 합이 1
#   세로 — 섞으면 갈래 비중(사용률에 맞춘 값)이 나온다
#   그 사이의 쏠림 = 표본에서 잰 것
# 형태 비중은 사용률, 갈래 비중도 사용률, **둘의 관계만 표본**이다.

_BY_FORM = {}


def archetype_by_form(dex, poke):
    """(형태 목록, 표). 표[형태][갈래] = 그 형태일 때 그 갈래일 확률."""
    key = (poke["key"], calc.CONFIG["form_mismatch"])
    if key in _BY_FORM:
        return _BY_FORM[key]

    got = archetypes(dex, poke)
    wmap = forms.class_weights(dex, poke)
    if not got or not wmap:
        _BY_FORM[key] = None
        return None
    moves, w, table, _ = got
    rows = samples.by_pokemon(loaded(dex)).get(poke["name"]) or []
    classes = [c for c in forms.CLASS_ORDER if wmap.get(c, 0.0) > 0.0]
    if not classes:
        _BY_FORM[key] = None
        return None

    # 표본에서 (형태, 갈래) 를 센다. 갈래는 그 개체의 기술로 사후확률을 매긴다.
    count = [[0.0] * len(w) for _ in classes]
    for m in rows:
        if m["cls"] not in classes:
            continue
        i = classes.index(m["cls"])
        post = archetype_posterior(dex, poke,
                                   set(x["name"] for x in m["moves"]))
        for a, v in enumerate(post):
            count[i][a] += v
    total = sum(sum(r) for r in count)
    if total <= 0:
        _BY_FORM[key] = None
        return None

    # 쏠림을 표본 횟수만으로 잡으면 안 된다. 한카리아스 CS형 표본이 20마리뿐인데
    # 거기서 (형태, 갈래) 아홉 칸을 추정하면 얇아서 튄다. 실제로 튀었다 —
    # **역린을 봤는데 CS형이 42% 로 나왔다** (1-A 혼자 할 때는 4% 였다).
    # 역린은 물리 드래곤 기술이니 특수형이 들 리가 없다. 1-A 가 더 맞았다.
    #
    # 그래서 **1-A 를 사전분포로 깐다.** 1-A 의 형태별 기술 확률은 게임 규칙
    # ("물리기는 공격으로 때린다") 에서 나온 것이라 표본 수와 무관하게 믿을 만하다.
    # 갈래의 기술 profile 이 그 형태의 profile 아래에서 얼마나 그럴듯한지를
    # 교차엔트로피로 재서 사전 쏠림으로 쓰고, 표본은 **칸이 두꺼운 만큼만**
    # 그 위에 얹는다 (수축).
    fclasses, fweights, fmoves, ftable = forms.conditional_table(dex, poke)
    fidx = dict((mv["id"], j) for j, mv in enumerate(fmoves))
    eps = 1e-6

    prior = []
    for c in classes:
        line = []
        fi = fclasses.index(c) if c in fclasses else None
        for a in range(len(w)):
            if fi is None:
                line.append(0.0)
                continue
            score = 0.0
            for j, mv in enumerate(moves):
                fj = fidx.get(mv["id"])
                if fj is None:
                    continue          # 사용률 목록 밖 기술은 1-A 가 모른다
                t = min(1 - eps, max(eps, ftable[fi][fj]))
                q = table[a][j]
                score += q * math.log(t) + (1 - q) * math.log(1 - t)
            line.append(score)
        prior.append(line)
    # 점수를 형태별로 견줘서 승산 배율로 바꾼다
    for i in range(len(classes)):
        top = max(prior[i]) if prior[i] else 0.0
        prior[i] = [math.exp(min(20.0, v - top)) for v in prior[i]]

    # 표본: 칸이 두꺼울수록 표본을 믿는다 (수축). PRIOR_N 마리쯤 모이면 반반.
    PRIOR_N = 15.0
    row_tot = [sum(r) or 1e-9 for r in count]
    col_tot = [sum(count[i][a] for i in range(len(classes))) or 1e-9
               for a in range(len(w))]
    kappa = []
    for i in range(len(classes)):
        line = []
        for a in range(len(w)):
            expect = row_tot[i] * col_tot[a] / total
            obs = (count[i][a] / expect) if expect > 0 else 1.0
            obs = max(0.02, obs)
            trust = row_tot[i] / (row_tot[i] + PRIOR_N)
            base = max(1e-6, prior[i][a])
            line.append((obs ** trust) * (base ** (1.0 - trust)))
        kappa.append(line)

    # ! 갈래 비중에는 **맞출 마진이 없다.** 갈래는 관측된 값이 아니라 표본에서
    #   찾아낸 잠재 변수다. 그런데 처음에 "섞으면 갈래 비중이 나오도록" 맞췄더니
    #   1번(공격형) 비중 54% 가 AS형 47% 보다 커서 **남는 몫이 CS형으로 밀렸고**,
    #   특수형인데 역린·칼춤을 든 한카리아스가 나왔다.
    #
    #   맞춰야 하는 마진은 두 개뿐이다 — **노력치(사용률)와 기술(사용률).**
    #   노력치는 각 형태에서 갈래 확률의 합이 1 이면 저절로 지켜지고,
    #   기술은 full_table 에서 승산으로 맞춘다. 그래서 여기서는 줄만 맞춘다.
    table = []
    for i in range(len(classes)):
        tot = sum(kappa[i]) or 1.0
        table.append([v / tot for v in kappa[i]])
    out = (classes, table)
    _BY_FORM[key] = out
    return out


# ---------------------------------------------------------------------------
# 두 신호를 곱해서 하나로 — (형태 x 갈래) 표
# ---------------------------------------------------------------------------
#
# 갈래만 쓰면 1-A 를 **대체**해 버린다. 갈래 1번에 역린과 화염방사가 같이
# 들어 있으므로, 역린을 봐도 "1번" 까지만 알게 되고 AS/CS 구분이 흐려진다.
# 실제로 역린을 봤을 때 CS형이 1-A 혼자일 때 4% 인데 33% 로 올라갔다.
#
# 둘은 **서로 다른 것을 아는 신호**다.
#   1-A   물리기는 공격으로 때린다        <- 게임 규칙. 표본 수와 무관하게 맞다
#   1-C   실제 구성은 몇 갈래로 뭉친다     <- 표본에서만 알 수 있다
#
# 그래서 대체하지 않고 **승산에서 곱한다.** 칸을 (형태 x 갈래) 로 펴고,
# 섞으면 사용률 채용률이 나오도록 한 번에 맞춘다.
#
#   승산(형태 f, 갈래 a, 기술 m) = κ_1A(f,m) x κ_갈래(a,m) x t_m
#   Σ_f Σ_a P(f)P(a|f) p(f,a,m) = 사용률(m)  <- t_m 을 이걸로 역산

_FULL = {}


def full_table(dex, poke):
    """(형태 목록, 갈래 수, 칸 목록, 칸 비중, 기술 목록, 표, 출처).

    칸 = (형태 번호, 갈래 번호). 표[칸][기술] = 그 칸에서 그 기술을 들 확률.
    """
    key = (poke["key"], calc.CONFIG["form_mismatch"])
    if key in _FULL:
        return _FULL[key]

    got = archetypes(dex, poke)
    byf = archetype_by_form(dex, poke)
    wmap = forms.class_weights(dex, poke)
    if not got or not byf or not wmap:
        _FULL[key] = None
        return None
    moves, w, arch, where = got
    classes, cond = byf
    rows = samples.by_pokemon(loaded(dex)).get(poke["name"]) or []
    targets = [t for _, t, _ in vocabulary(dex, poke, rows)]

    eps = 1e-6
    mixed = [sum(w[a] * arch[a][j] for a in range(len(w)))
             for j in range(len(moves))]

    def odds(x):
        x = min(1 - eps, max(eps, x))
        return x / (1 - x)

    k_arch = [[odds(arch[a][j]) / odds(mixed[j]) for j in range(len(moves))]
              for a in range(len(w))]
    k_form = [[forms.compat(c, mv) for mv in moves] for c in classes]

    cells, weights, kappa = [], [], []
    for i, c in enumerate(classes):
        for a in range(len(w)):
            cells.append((i, a))
            weights.append(wmap[c] * cond[i][a])
            kappa.append([k_form[i][j] * k_arch[a][j]
                          for j in range(len(moves))])
    table = forms._fit(kappa, weights, targets)
    out = (classes, len(w), cells, weights, moves, table, where)
    _FULL[key] = out
    return out


def cell_index(dex, poke, cls, arch):
    """(형태, 갈래) -> 칸 번호."""
    got = full_table(dex, poke)
    if not got:
        return None
    classes, k, cells, _w, _m, _t, _s = got
    if cls not in classes or arch is None or not (0 <= arch < k):
        return None
    i = classes.index(cls)
    return cells.index((i, arch))


def probs_for(dex, poke, cls=None, arch=None):
    """그 (형태, 갈래) 일 때의 (기술, 확률) 목록. 모르면 섞은 값."""
    got = full_table(dex, poke)
    if not got:
        return []
    classes, k, cells, weights, moves, table, _s = got
    idx = cell_index(dex, poke, cls, arch)
    if idx is not None:
        return list(zip(moves, table[idx]))
    # 형태만 아는 경우 — 그 형태의 갈래들만 섞는다
    pick = [n for n, (i, a) in enumerate(cells)
            if cls is None or classes[i] == cls]
    tot = sum(weights[n] for n in pick) or 1.0
    mixed = [sum(weights[n] * table[n][j] for n in pick) / tot
             for j in range(len(moves))]
    return list(zip(moves, mixed))


def mix_error_full(dex, poke):
    """섞은 값이 사용률과 얼마나 어긋나는가 ((형태 x 갈래) 표 기준)."""
    got = full_table(dex, poke)
    if not got:
        return 0.0
    _c, _k, _cells, weights, moves, table, _s = got
    rows = samples.by_pokemon(loaded(dex)).get(poke["name"]) or []
    targets = [t for _, t, _ in vocabulary(dex, poke, rows)]
    worst = 0.0
    for j in range(len(moves)):
        mix = sum(weights[n] * table[n][j] for n in range(len(table)))
        worst = max(worst, abs(mix - targets[j]))
    return worst


def joint_posterior(dex, poke, seen_moves, item=None):
    """본 것으로 (형태, 갈래) 를 같이 좁힌다. 칸별 사후확률.

    기술은 이 표가 직접 받고, 도구는 1-A 의 도구 표를 거쳐 형태 쪽에 걸린다
    (메가스톤이 특히 세다 — forms.item_compat 참고).
    """
    got = full_table(dex, poke)
    if not got:
        return []
    classes, _k, cells, weights, moves, table, _s = got
    seen = set(seen_moves or ())
    post = list(weights)
    for j, mv in enumerate(moves):
        if mv["name"] not in seen:
            continue
        for n in range(len(post)):
            post[n] *= table[n][j]
    if item:
        icls, ientries, itable = forms._pick_table(dex, poke, "items")
        for j, e in enumerate(ientries):
            if e["name"] != item or not itable:
                continue
            for n, (i, _a) in enumerate(cells):
                c = classes[i]
                if c in icls:
                    post[n] *= itable[icls.index(c)][j]
    tot = sum(post)
    return [x / tot for x in post] if tot > 0 else list(weights)


def form_posterior(dex, poke, seen_moves, item=None):
    """본 기술로 **형태**를 좁힌다 — 갈래를 거쳐서. {형태: 사후확률}.

    1-A 의 `forms.form_posterior` 보다 이쪽이 세다. 1-A 는 기술을 물리/특수로만
    가르므로 **스텔스록을 봐도 형태가 안 움직인다** (변화기는 형태 중립).
    그런데 표본을 보면 스텔스록은 3번 갈래에 94% 몰려 있고, 3번 갈래는
    내구형이 99% 다. 즉 **스텔스록 하나로 HB 형이라는 것을 거의 알 수 있다.**

        P(형태 | 본 것) ∝ P(형태) x Σ_갈래 P(갈래|형태) x Π P(본 기술|갈래)
    """
    got = full_table(dex, poke)
    if not got:
        return {}
    classes, _k, cells, _w, _m, _t, _s = got
    post = joint_posterior(dex, poke, seen_moves, item)
    out = {}
    for n, (i, _a) in enumerate(cells):
        out[classes[i]] = out.get(classes[i], 0.0) + post[n]
    return out


def archetype_dist(dex, poke, cls):
    """그 형태일 때 갈래별 확률. 형태를 모르면 갈래 비중 그대로."""
    got = archetype_by_form(dex, poke)
    if not got:
        base = archetypes(dex, poke)
        return list(base[1]) if base else []
    classes, table = got
    if cls in classes:
        return list(table[classes.index(cls)])
    wmap = forms.class_weights(dex, poke)
    return [sum(wmap.get(c, 0.0) * table[i][a] for i, c in enumerate(classes))
            for a in range(len(table[0]))]

# ---------------------------------------------------------------------------
# "구조는 표본에서, 수준은 사용률에서" 가 깨지는 자리
# ---------------------------------------------------------------------------
#
# 이 프로젝트의 원칙은 **구조(어떤 기술들이 뭉치는가)는 구축기사 표본에서,
# 수준(각 기술을 얼마나 쓰는가)은 사다리 사용률에서** 가져오는 것이다.
# 둘이 같은 시기를 가리키는 한 잘 맞는다. 그런데 **그 형태가 이번에 막
# 생긴 것이면** 깨진다. 사용률은 지금 것이라 그 형태를 크게 잡는데,
# 표본은 그 형태가 없던 시절 것이라 배울 구조가 없다.
#
# 실제로 겪은 것 (2026-09 기준) —
#   한카리아스Z(한카리아스나이트Z) 가 이번에 추가됐다. 사용률에서는
#   도구 채용률 35.3%, CS 배분 28.3% 로 거의 같은 숫자다. 즉 **CS형
#   한카리아스는 사실상 Z 전용 형태**다. 그런데 표본 222마리에서 CS는
#   9마리(4%)뿐이고, 그 9마리는 **전부 2026-09** 것이다. 시즌5(M-5)
#   표본 11마리에는 CS가 한 마리도 없다.
#
#   그래서 지금 모델은 인구의 36% 를 차지한다는 형태를 **9마리로**
#   설명하고 있다. 지금은 결과가 멀쩡하다 — CS 갈래가 용성군 80% /
#   화염방사 73% / 대지의힘 70% 로 잡히고 역린·칼춤이 안 섞인다.
#   하지만 9마리짜리 근거다. 표본이 조금만 흔들려도 같이 흔들린다.
#
# 이건 버그가 아니라 **자료가 못 따라온 자리**다. 고치는 방법은 하나뿐:
#   시즌이 돌아서 새 형태가 들어간 구축기사가 쌓이면 저절로 낫는다.
# 대신 **조용히 틀어지지는 않게** 경고를 띄운다.
# 세는 법 — **한 번 잘못 짰다가 고쳤다.**
#
#   처음엔 마리 수로 셌다("표본 15마리 미만이면 경고"). 표본이 30마리
#   뿐인 포켓몬은 어느 형태든 다 적으니 40종 중 26종이 걸렸다. 쓸모없다.
#   다음엔 이항분포로 셌다(n·q 에서 3시그마). 이번엔 22건이 걸렸다 —
#   개굴닌자 CS형이 "사용률 99%, 표본 94.5%" 인데 걸렸다. 사용률이
#   99% 면 표준편차가 0.7마리라 3마리만 어긋나도 3시그마를 넘는다.
#   **이항분포는 틀린 잡음 모형이다.** 여기서 어긋나는 것은 뽑기
#   운이 아니라, 사용률 쪽 배분 이름표와 우리 spread_class 의 경계가
#   조금씩 다른 데서 오는 **체계적인 차이**이기 때문이다.
#
#   그래서 **배수**로 잰다. 잡아야 하는 것은 몇 마리 어긋난 것이 아니라
#   **자릿수가 어긋난 것**이다. 한카리아스 CS형은 36% vs 4% 로 9배,
#   대검귀 C형은 88% vs 0% 다. 그 정도만 경고한다.
THIN_FORM_USAGE = 0.15   # 사용률이 이만큼은 돼야 따진다
THIN_FORM_FOLD = 3.0     # 몇 배 어긋나야 경고인가


def thin_forms(dex, poke):
    """사용률과 표본이 자릿수로 어긋난 형태를 찾는다. [설명 문장].

    한쪽으로만 보지 않는다 —
      표본 << 사용률 : 새로 생긴 형태. 배울 구조가 없다.
      표본 >> 사용률 : 지고 있는 형태. 표본이 옛날 것이다.
    어느 쪽이든 **구조는 옛 메타, 수준은 지금 메타** 라는 뜻이라
    그 형태의 기술 구성은 덜 믿어야 한다.
    """
    rows = samples.by_pokemon(loaded(dex)).get(poke["name"]) or []
    rows = [r for r in rows if r.get("has_evs")]
    n = len(rows)
    if n < MIN_SAMPLES:
        return []
    try:
        wmap = forms.class_weights(dex, poke)
    except Exception:
        return []
    seen = {}
    for r in rows:
        seen[r["cls"]] = seen.get(r["cls"], 0) + 1
    out = []
    for cls, q in sorted(wmap.items(), key=lambda kv: -kv[1]):
        if q < THIN_FORM_USAGE:
            continue
        k = seen.get(cls, 0)
        got = float(k) / n
        if got * THIN_FORM_FOLD >= q and got <= q * THIN_FORM_FOLD:
            continue
        why = ("새로 생긴 형태일 수 있다" if got < q
               else "지고 있는 형태일 수 있다")
        out.append("%s: 사용률은 %.0f%% 라는데 표본 %d마리 중 %d마리"
                   "(%.0f%%)뿐이다 — %s. 그 형태의 기술 구성은 덜 믿어야 "
                   "한다." % (forms.CLASS_KO.get(cls, cls), q * 100,
                             n, k, got * 100, why))
    return out


# ---------------------------------------------------------------------------
# 보고서
# ---------------------------------------------------------------------------
def report(dex, poke, seen=None):
    import best

    L = []
    line = "=" * 78
    L.append(line)
    L.append("  %s — 기술 구성이 몇 갈래인가 (1-C)" % poke["name"])
    L.append(line)
    rows = samples.by_pokemon(loaded(dex)).get(poke["name"]) or []
    got = archetypes(dex, poke)
    if not got:
        L.append("  표본 %d마리 — %d마리는 있어야 갈래를 찾는다."
                 % (len(rows), MIN_SAMPLES))
        L.append(line)
        return "\n".join(L)

    moves, w, table, where = got
    seen = set(seen or ())
    post = archetype_posterior(dex, poke, seen)
    L.append("  표본 %d마리 · 갈래 %d개" % (len(rows), len(w)))
    for i in range(len(w)):
        now = ("  ->  지금 %.0f%%" % (post[i] * 100)) if seen else ""
        L.append("    %d번 (%.0f%%)  %s%s"
                 % (i + 1, w[i] * 100, label(dex, poke, i), now))
    if seen:
        L.append("  본 것: %s" % ", ".join(sorted(seen)))
    L.append("-" * 78)

    head = [("기술", 16), ("출처", 7), ("전체", 8)]
    if seen:
        head.append(("지금", 8))
    head += [("%d번" % (i + 1), 7) for i in range(len(w))]
    L.append("  " + "".join(best._pad(h, ww) for h, ww in head).rstrip())

    mixed = [sum(w[i] * table[i][j] for i in range(len(w)))
             for j in range(len(moves))]
    order = sorted(range(len(moves)), key=lambda j: -mixed[j])
    for j in order[:14]:
        cells = [moves[j]["name"], where[j], "%.1f%%" % (mixed[j] * 100)]
        mark = ""
        if seen:
            nowp = (1.0 if moves[j]["name"] in seen
                    else sum(post[i] * table[i][j] for i in range(len(w))))
            cells.append("%.1f%%" % (nowp * 100))
            if moves[j]["name"] in seen:
                mark = "   ← 봤다"
            elif nowp > mixed[j] + 0.05:
                mark = "   ↑"
            elif nowp < mixed[j] - 0.05:
                mark = "   ↓"
        cells += ["%.0f%%" % (table[i][j] * 100) for i in range(len(w))]
        col = [table[i][j] for i in range(len(w))]
        if not seen and split_score(col) >= SPLIT_MIN:
            mark = "   ← 갈래로 갈린다 (%.0f배)" % split_score(col)
        L.append("  " + "".join(best._pad(c, ww)
                                for c, (h, ww) in zip(cells, head)).rstrip()
                 + mark)

    L.append("-" * 78)
    L.append("  '출처' 가 표본인 줄은 **사용률 상위 10개 목록에 없는 기술**이다.")
    L.append("  전에는 확률이 0 이라 아예 안 나왔다. 사용률이 남긴 예산을")
    L.append("  표본 비율대로 나눠 줬다.")
    L.append("  섞으면 사용률 채용률이 그대로 나온다 — 최대 오차 %.2f%%p"
             % (mix_error(dex, poke) * 100))
    for warn in thin_forms(dex, poke):
        L.append("  ! " + warn)
    L.append(line)
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 덮개 — 사용률 순서로 본다. **단, 룰을 맞춰 놓고 본다.**
# ---------------------------------------------------------------------------
#
# `survey()` 는 표본이 많은 순서로 줄을 세운다. 그것만 보면 표본이 제일
# 많은 한 마리(한카리아스)를 계속 들여다보게 된다. 이 표는 반대로
# 사용률 순서로 세워서 **어디에 갈래 모델이 안 붙었는지**를 본다.
#
# **여기서 한 번 크게 틀렸다. 기록으로 남긴다.**
#
#   처음 만들었을 때 "상위 30종 중 7종에 표본이 없다 — 구멍이다" 라고
#   보고했다. 틀렸다. 사용률은 **M-6** 것이고 구축기사는 대부분
#   **M-5** 것인데 그걸 나란히 놓고 센 것이다. 룰이 바뀌면 쓸 수 있는
#   포켓몬이 바뀐다. 그 7종(갑주무사·드닐레이브·고릴타·에이스번·
#   빠르모트·에써르 등)은 **M-6 에 새로 들어온 포켓몬**이었다.
#   M-5 기사에 없는 게 당연하다. 없는 것을 찾고 있었던 것이다.
#
#   자료에는 룰 이름표가 처음부터 들어 있었다(`party["rule"]`).
#   안 보고 셌다.
#
#   교훈: **세기 전에 두 자료가 같은 룰인지부터 맞춘다.**
#
# 그리고 표본이 없다는 것 자체는 사고가 아니다. 표본은 경향성을
# 확인하려고 모으는 것이고, 없으면 그 종은 기술을 서로 독립으로 뽑는다.
# 채용률은 사용률에서 그대로 오므로 **덜 정교할 뿐 틀리지 않는다.**
# 그래서 이 표는 '구멍' 이라고 부르지 않고 무엇 때문인지를 나눠서 적는다.
def coverage(dex, top=30, rule=None):
    """사용률 상위 종에 갈래 모델이 붙었나.

    [(순위, 이름, 전체표본, 지금룰표본, 표본순위, 왜)].

    `지금룰표본` 이 0 이면 **그 룰에 새로 들어온 종**일 수 있다.
    그건 모으기를 빼먹은 게 아니라 기사가 아직 없는 것이다.
    """
    import json
    import os

    rule = rule or samples.CURRENT_RULE
    parties = loaded(dex)
    prev = samples.previous_rule(parties, rule)
    byp = samples.by_pokemon(parties)
    now = samples.by_pokemon(samples.by_rule(parties, rule))
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "usage_single.json")
    try:
        with open(path, encoding="utf-8") as f:
            listed = json.load(f)["pokemon"]
    except (IOError, OSError, ValueError, KeyError):
        return []
    order = sorted(byp.items(), key=lambda kv: -len(kv[1]))
    srank = dict((nm, i + 1) for i, (nm, _v) in enumerate(order))
    fresh = samples.newcomers(parties, rule)

    rows = []
    for e in sorted(listed, key=lambda x: x.get("rank") or 10 ** 6):
        rank = e.get("rank")
        if not rank or rank > top:
            continue
        nm = e["name"]
        n = len(byp.get(nm) or [])
        n_now = len(now.get(nm) or [])
        try:
            pk = dex.find_pokemon(nm)
        except LookupError:
            rows.append((rank, nm, n, n_now, srank.get(nm), "도감에 없음"))
            continue
        got = archetypes(dex, pk)
        k = len(got[1]) if got else 0
        if nm in fresh:
            # **먼저 본다.** 이걸 뒤에 두면 신규종이 '표본 부족' 으로
            # 잡혀서 구멍처럼 보인다. 한 번 그렇게 틀렸다.
            why = "%s 신규로 보인다 (직전 %s 기사에 없음)" % (rule, prev)
        elif n >= MIN_SAMPLES:
            why = "형태가 사용률과 자릿수로 어긋남" if thin_forms(dex, pk) else ""
        else:
            why = "표본 %d마리 — 기술을 서로 독립으로 뽑는다" % n
        rows.append((rank, nm, n, n_now, srank.get(nm), why, k))
    return [r if len(r) == 7 else r + (0,) for r in rows]


def coverage_report(dex, top=30, rule=None):
    import best

    rule = rule or samples.CURRENT_RULE
    parties = loaded(dex)
    rows = coverage(dex, top, rule)
    L = []
    line = "=" * 78
    L.append(line)
    L.append("  사용률 상위 %d종에 갈래 모델이 붙었나" % top)
    L.append(line)
    n_rule, share, say = samples.rule_gap(parties, rule)
    L.append("  사용률은 지금 룰(%s) 것이다. 표본은 —" % rule)
    for x in say:
        L.append("    " + x)
    L.append("-" * 78)
    if not rows:
        L.append("  사용률 자료를 못 읽었다.")
        L.append(line)
        return "\n".join(L)
    head = [("사용률", 7), ("이름", 14), ("표본", 7), ("%s만" % rule, 8),
            ("갈래", 6)]
    L.append("  " + "".join(best._pad(h, w) for h, w in head).rstrip())
    thin = indep = fresh = 0
    for rank, nm, n, n_now, sr, why, k in rows:
        cells = [str(rank), nm, str(n), str(n_now), ("%d개" % k) if k else "-"]
        mark = ("   <-- " + why) if why else ""
        if "신규로 보인다" in why:
            fresh += 1
        elif "독립" in why:
            indep += 1
        elif why:
            thin += 1
        L.append("  " + "".join(best._pad(c, w)
                                for c, (h, w) in zip(cells, head)).rstrip()
                 + mark)
    L.append("-" * 78)
    L.append("  상위 %d종 중 — 갈래 모델 붙음 %d · 표본이 얇아 독립으로 뽑음 %d"
             % (len(rows), len(rows) - thin - indep - fresh, indep))
    L.append("                형태가 어긋남 %d · %s 신규로 보임 %d"
             % (thin, rule, fresh))
    L.append("")
    L.append("  ! 표본이 없는 것은 사고가 아니다. 채용률은 사용률에서")
    L.append("    그대로 오므로 틀리지 않는다 — 기술을 서로 묶어 주지")
    L.append("    못할 뿐이다. 표본은 경향성을 확인하는 데 쓴다.")
    L.append("  ! '%s 만' 칸이 0 인 종을 구멍으로 세지 마라. 룰이 바뀌면" % rule)
    L.append("    쓸 수 있는 포켓몬이 바뀐다. 실제로 그렇게 한 번 틀렸다.")
    L.append(line)
    return "\n".join(L)


def survey(dex):
    import best

    parties = loaded(dex)
    byp = samples.by_pokemon(parties)
    L = []
    line = "=" * 78
    L.append(line)
    L.append("  표본으로 갈래를 찾을 수 있는 포켓몬 (1-C)")
    L.append(line)
    head = [("포켓몬", 14), ("표본", 7), ("갈래", 7), ("목록 밖 기술", 14),
            ("섞음 오차", 11)]
    L.append("  " + "".join(best._pad(h, w) for h, w in head).rstrip())
    done = 0
    for name, rows in sorted(byp.items(), key=lambda x: -len(x[1])):
        if len(rows) < MIN_SAMPLES:
            continue
        try:
            poke = dex.find_pokemon(name)
        except LookupError:
            continue
        got = archetypes(dex, poke)
        if not got:
            continue
        moves, w, table, where = got
        extra = sum(1 for x in where if x == "표본")
        cells = [name, str(len(rows)), "%d개" % len(w), "%d개" % extra,
                 "%.2f%%p" % (mix_error(dex, poke) * 100)]
        L.append("  " + "".join(best._pad(c, ww)
                                for c, (h, ww) in zip(cells, head)).rstrip())
        done += 1
    L.append("-" * 78)
    L.append("  %d종에 갈래 모델이 붙었다. 나머지는 표본 %d마리를 못 넘겼다."
             % (done, MIN_SAMPLES))
    L.append("  (표본이 늘면 저절로 늘어난다 — python fetch_pokesol.py --목록 N)")
    L.append("  ! 이 표는 표본이 많은 순서다 — **우리가 가진 것**을 본다.")
    L.append("    **못 가진 것**은 python combos.py --덮개 로 본다.")
    L.append(line)
    return "\n".join(L)


def main():
    dex = calc.Dex()
    argv = sys.argv[1:]
    if "--덮개" in argv:
        print(coverage_report(dex))
        return
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
        print(report(dex, dex.find_pokemon(name), seen))


if __name__ == "__main__":
    main()
