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
        if not seen and max(col) - min(col) >= 0.35:
            mark = "   ← 갈래로 갈린다"
        L.append("  " + "".join(best._pad(c, ww)
                                for c, (h, ww) in zip(cells, head)).rstrip()
                 + mark)

    L.append("-" * 78)
    L.append("  '출처' 가 표본인 줄은 **사용률 상위 10개 목록에 없는 기술**이다.")
    L.append("  전에는 확률이 0 이라 아예 안 나왔다. 사용률이 남긴 예산을")
    L.append("  표본 비율대로 나눠 줬다.")
    L.append("  섞으면 사용률 채용률이 그대로 나온다 — 최대 오차 %.2f%%p"
             % (mix_error(dex, poke) * 100))
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
    L.append(line)
    return "\n".join(L)


def main():
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
        print(report(dex, dex.find_pokemon(name), seen))


if __name__ == "__main__":
    main()
