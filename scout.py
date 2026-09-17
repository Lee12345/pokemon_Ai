# -*- coding: utf-8 -*-
"""
4-C — 상대를 하나가 아니라 분포로 본다.

지금까지는 상대를 '사용률 1위 배분에 1위 기술' 하나로 놓고 계산했다.
실제로는 상대가 무엇을 들고 있는지 모른다. 대신 **사용률이 있다.**

    한카리아스  지진 67%  스텔스록 39.6%  용성군 30.1%
                한카리아스나이트Z 35.3%  구애스카프 19%
                성격 명랑 24.2%  고집 21%

이 파일은 그 채용률로 **있을 법한 상대를 뽑아낸다.** 한 마리가 아니라 여러 마리다.

## 채용률을 그대로 확률로 써도 되는 근거

기술 채용률의 합이 포켓몬마다 **평균 376%** 다. 기술칸이 4개이므로
'각 기술이 그 4칸에 들어 있을 확률' 로 그대로 쓸 수 있다는 뜻이다.
(400%에 못 미치는 24%는 상위 10개 밖의 자잘한 기술들이다.)

    python -c "import calc;d=calc.Dex();u=d.usage['0031-00'];print(sum(m['pct'] for m in u['moves']))"

## 다만 이것이 근사인 이유

사용률에는 **조합 정보가 없다.** 기술끼리도, 기술과 배분 사이도 마찬가지다.
한카리아스는 AS형이면 드래곤테일을 잘 안 들고, HB형이면 스텔스록과 같이 든다.
여기서는 전부 **서로 독립**이라고 보고 뽑는다.
형태별 표본은 직접 뛰면서 쌓아야 하고, 생기면 이 파일만 갈아끼우면 된다.
"""

import random

import calc

# 한 포켓몬이 들 수 있는 기술 칸 수
SLOTS = 4


# ---------------------------------------------------------------------------
# 사용률 읽기
# ---------------------------------------------------------------------------
def usage_of(dex, poke):
    """메가는 사용률이 기본 폼에 잡히므로 그쪽으로 넘어간다."""
    return (dex.usage.get(poke["key"])
            or dex.usage.get("%04d-00" % poke["dexNo"]))


def _normalized(entries):
    """한 칸을 두고 경쟁하는 것들(성격·도구·특성·노력치)을 확률로 바꾼다.

    합이 100%가 아닌 경우가 있어서 그대로 쓰지 않고 나눈다.
      · 도구·성격·특성은 합이 ~100% 라 사실상 그대로다.
      · **노력치는 원본(로토덱스)부터 합이 ~162% 다.** 원인은 아직 모른다.
        같은 배분이 두 번 들어 있는 경우가 있는데 그걸 합쳐도 설명이 안 된다.
        여기서는 정규화해서 쓴다 — docs/ai-design.md 참고.
    """
    total = sum(e["pct"] for e in entries)
    if total <= 0:
        return []
    return [(e, e["pct"] / total) for e in entries]


def _weighted_pick(rng, pairs):
    """(항목, 확률) 목록에서 하나 뽑는다."""
    if not pairs:
        return None
    r = rng.random()
    acc = 0.0
    for item, p in pairs:
        acc += p
        if r <= acc:
            return item
    return pairs[-1][0]


# ---------------------------------------------------------------------------
# 관찰 — 대전이 진행되면 정보가 늘어난다
# ---------------------------------------------------------------------------
class Evidence(object):
    """대전 중에 본 것. 볼수록 상대의 범위가 좁아진다.

    설계 문서 3-4(2) 의 '관찰로 확률을 좁혀가는 것' 이 이 자리다.
    """

    def __init__(self, seen_moves=None, min_speed=None, item=None,
                 ability=None):
        # 실제로 쓰는 것을 본 기술 — 확률 100% 로 확정된다
        self.seen_moves = set(seen_moves or ())
        # 예상보다 먼저 움직였다 -> 스피드가 최소 이만큼은 된다
        self.min_speed = min_speed
        # 도구·특성이 드러난 경우
        self.item = item
        self.ability = ability

    def describe(self):
        got = []
        if self.seen_moves:
            got.append("기술 %s 확인" % ", ".join(sorted(self.seen_moves)))
        if self.min_speed:
            got.append("스피드 %d 이상" % self.min_speed)
        if self.item:
            got.append("도구 %s" % self.item)
        if self.ability:
            got.append("특성 %s" % self.ability)
        return " · ".join(got) if got else "아직 본 것 없음"

    @property
    def empty(self):
        return not (self.seen_moves or self.min_speed or self.item
                    or self.ability)


# ---------------------------------------------------------------------------
# 기술 — 4칸에 무엇이 들어 있을까
# ---------------------------------------------------------------------------
def move_probabilities(dex, poke, evidence=None):
    """기술별로 '상대가 그걸 들고 있을 확률'. (기술, 확률) 목록.

    채용률을 그대로 쓴다. 본 기술은 1.0 으로 올린다.
    """
    ev = evidence or Evidence()
    u = usage_of(dex, poke)
    out = []
    if not u or not u.get("moves"):
        return out
    for entry in u["moves"]:
        mv = dex.move_by_id(entry["id"])
        if mv is None:
            continue
        p = 1.0 if mv["name"] in ev.seen_moves else entry["pct"] / 100.0
        out.append((mv, min(1.0, p)))
    # 본 기술인데 상위 10개 밖이면 목록에 없다. 그것도 넣어 준다.
    known = {m["name"] for m, _ in out}
    for name in ev.seen_moves:
        if name in known:
            continue
        try:
            out.append((dex.find_move(name), 1.0))
        except LookupError:
            pass
    out.sort(key=lambda x: -x[1])
    return out


# --- 칸 수 제약 아래에서 채용률을 되살리기 -------------------------------
#
# 기술을 채용률 그대로 독립해서 뽑으면 4칸을 자주 넘긴다.
# 넘쳤다고 아무거나 버리면 그 기술만 손해를 보고, 채용률 높은 쪽을 남기면
# 낮은 쪽이 통째로 눌린다 (하마돈 게으름피우기 37.5% -> 17%).
#
# 그래서 '4칸 이하' 라는 조건을 걸었을 때 **원래 채용률이 그대로 나오도록**
# 가중치를 역산한다. 반복해서 맞추는 방법이고, 얼마나 맞았는지는
# check_marginals 로 직접 잴 수 있다.

def _size_dist(weights):
    """독립 동전 n개를 던졌을 때 앞면이 j개일 확률 (j=0..n)."""
    dist = [1.0]
    for w in weights:
        nxt = [0.0] * (len(dist) + 1)
        for j, v in enumerate(dist):
            nxt[j] += v * (1.0 - w)
            nxt[j + 1] += v * w
        dist = nxt
    return dist


def _suffix_dists(weights):
    """뒤쪽 i..끝 만 던졌을 때 앞면 개수의 분포. 조건부로 뽑을 때 쓴다."""
    n = len(weights)
    suf = [None] * (n + 1)
    suf[n] = [1.0]
    for i in range(n - 1, -1, -1):
        d, w = suf[i + 1], weights[i]
        nxt = [0.0] * (len(d) + 1)
        for j, v in enumerate(d):
            nxt[j] += v * (1.0 - w)
            nxt[j + 1] += v * w
        suf[i] = nxt
    return suf


def _cum(dist, upto):
    return sum(dist[:upto + 1]) if upto >= 0 else 0.0


def sample_conditional(rng, weights, slots):
    """'앞면 slots개 이하' 라는 조건 아래에서 정확히 뽑는다.

    던져 보고 넘치면 다시 던지는 방식은 못 쓴다. 하마돈처럼 채용률 합이
    398% 인 경우 **4칸 이하가 나올 확률이 0.2% 밖에 안 되기 때문**이다.
    (그렇게 하면 200번 다시 던져도 거의 다 실패해서 결국 상위 4개만 나온다.)

    대신 앞에서부터 하나씩 정하면서, 남은 칸으로 뒤쪽이 들어갈 수 있는지를
    매번 따진다. 다시 던지지 않으므로 몇 %든 정확하다.
    """
    suf = _suffix_dists(weights)
    chosen = []
    left = slots
    for i, w in enumerate(weights):
        p_yes = w * _cum(suf[i + 1], left - 1)
        p_no = (1.0 - w) * _cum(suf[i + 1], left)
        total = p_yes + p_no
        if total <= 0:
            continue
        if rng.random() < p_yes / total:
            chosen.append(i)
            left -= 1
    return chosen


def _inclusion(weights, slots):
    """'앞면이 slots개 이하' 라는 조건 아래에서 각자가 뽑힐 확률."""
    full = _size_dist(weights)
    denom = sum(full[:slots + 1])
    if denom <= 0:
        return [0.0] * len(weights)
    out = []
    for i, w in enumerate(weights):
        rest = _size_dist(weights[:i] + weights[i + 1:])
        out.append(w * sum(rest[:slots]) / denom)
    return out


def fit_weights(probs, slots=SLOTS, rounds=400, damp=0.5):
    """조건을 걸어도 목표 채용률이 나오도록 가중치를 맞춘다.

    확률을 그대로 곱해서 고치면 튄다 (하마돈처럼 채용률 합이 398% 라
    4칸 제약이 거의 꽉 찬 경우). 그래서 **승산(odds)** 위에서 고치고
    한 번에 절반씩만 움직인다.

    그래도 완전히 못 맞추는 경우가 있다. 얼마나 어긋났는지는
    check_marginals 로 직접 재서 보여 주므로 모르고 지나갈 일은 없다.
    """
    eps = 1e-9
    target = [max(eps, min(1.0 - eps, p)) for p in probs]
    t_odds = [t / (1.0 - t) for t in target]
    odds = list(t_odds)
    best, best_err = None, None
    for _ in range(rounds):
        w = [o / (1.0 + o) for o in odds]
        got = _inclusion(w, slots)
        err = max(abs(g - t) for g, t in zip(got, target))
        if best_err is None or err < best_err:
            best, best_err = list(w), err
        if err < 1e-4:
            break
        for i in range(len(odds)):
            g = max(eps, min(1.0 - eps, got[i]))
            ratio = t_odds[i] / (g / (1.0 - g))
            odds[i] *= ratio ** damp
    return best


_WEIGHT_CACHE = {}


def sample_moveset(dex, poke, rng, evidence=None):
    """상대의 기술 4칸을 한 번 뽑는다.

    채용률이 그대로 재현되도록 맞춘 가중치로 뽑고, 4칸을 넘으면 다시 뽑는다.
    """
    probs = move_probabilities(dex, poke, evidence)
    if not probs:
        return []

    key = (poke["key"], tuple(round(p, 4) for _, p in probs))
    w = _WEIGHT_CACHE.get(key)
    if w is None:
        w = fit_weights([p for _, p in probs])
        _WEIGHT_CACHE[key] = w

    idx = sample_conditional(rng, w, SLOTS)
    return [probs[i][0] for i in idx]


# ---------------------------------------------------------------------------
# 몸 — 성격·노력치·도구·특성
# ---------------------------------------------------------------------------
def sample_build(dex, poke, rng, evidence=None, speed_of=None):
    """있을 법한 상대 한 마리를 뽑는다.

    성격·노력치·도구·특성을 각각 채용률로 뽑아서 조립한다.
    넷을 서로 독립이라고 본 근사다.

    speed_of 를 주면 '예상보다 먼저 움직였다' 같은 관찰을 걸러낼 수 있다.
    """
    ev = evidence or Evidence()
    u = usage_of(dex, poke)
    if not u:
        return calc.Build(dex, poke)

    for _ in range(40):          # 관찰과 안 맞으면 다시 뽑는다
        nature = None
        if u.get("natures"):
            pick = _weighted_pick(rng, _normalized(u["natures"]))
            try:
                nature = dex.find_nature(pick["name"])
            except LookupError:
                nature = None
        sp = {}
        if u.get("evs"):
            pick = _weighted_pick(rng, _normalized(u["evs"]))
            for k, v in (pick or {}).get("spread", {}).items():
                if k in calc.SPREAD_KEY:
                    sp[calc.SPREAD_KEY[k]] = v

        item = ev.item
        if item is None and u.get("items"):
            pick = _weighted_pick(rng, _normalized(u["items"]))
            item = pick["name"] if pick else None

        # 메가스톤을 뽑았으면 실제로는 그 메가다
        real_poke = poke
        mega = dex.mega_by_item.get(item)
        if mega and not poke.get("isMega") and mega["dexNo"] == poke["dexNo"]:
            real_poke = mega

        own = [a["name"] for a in real_poke["abilities"]]
        ability = ev.ability
        if ability not in own:
            ability = None
        if ability is None:
            if len(own) == 1:
                ability = own[0]
            elif u.get("abilities"):
                cand = [(a, p) for a, p in _normalized(u["abilities"])
                        if a["name"] in own]
                if cand:
                    tot = sum(p for _, p in cand) or 1.0
                    pick = _weighted_pick(rng, [(a, p / tot) for a, p in cand])
                    ability = pick["name"]
            if ability is None:
                ability = own[0] if own else None

        build = calc.Build(dex, real_poke, sp=sp, nature=nature, item=item,
                           ability=ability)
        if ev.min_speed and speed_of and speed_of(build) < ev.min_speed:
            continue          # 관찰과 안 맞는다 — 다시
        return build
    return calc.Build(dex, poke)


def sample_opponent(dex, poke, rng, evidence=None, speed_of=None):
    """몸과 기술을 함께 뽑아 돌려준다."""
    build = sample_build(dex, poke, rng, evidence, speed_of)
    moves = sample_moveset(dex, build.poke, rng, evidence)
    if not moves:
        moves = sample_moveset(dex, poke, rng, evidence)
    return build, moves


# ---------------------------------------------------------------------------
# 얼마나 잘 뽑히는지 스스로 확인
# ---------------------------------------------------------------------------
def check_marginals(dex, poke, trials=4000, seed=1):
    """뽑아낸 결과가 원래 채용률과 얼마나 맞는지.

    4칸 제한 때문에 채용률이 높은 기술은 조금 낮게, 낮은 기술은 조금 높게 나온다.
    얼마나 어긋나는지 직접 재서 보여 준다. 근사라고만 적어 두고 넘어가지 않는다.
    """
    rng = random.Random(seed)
    got = {}
    for _ in range(trials):
        for mv in sample_moveset(dex, poke, rng):
            got[mv["name"]] = got.get(mv["name"], 0) + 1
    rows = []
    for mv, p in move_probabilities(dex, poke):
        rows.append((mv["name"], p * 100.0,
                     got.get(mv["name"], 0) * 100.0 / trials))
    return rows
