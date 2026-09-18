# -*- coding: utf-8 -*-
"""
가정값 감도 — 어떤 값을 먼저 실측해야 하는가.

    python sensitivity.py
    python sensitivity.py 메가보만다 하마돈

`calc.CONFIG` 에는 **챔피언스에서 확인한 적 없는 값이 스무 개 넘게** 들어 있다.
전부 본편 값을 가져다 쓴 것이다. 그런데 스무 개를 다 실측할 수는 없다.

그래서 **하나씩 흔들어 보고, 답이 실제로 바뀌는 것만 골라낸다.**

두 가지를 따로 잰다. 둘의 답이 다르기 때문이다.

| | 뜻 |
|---|---|
| **추천이 바뀌는가** | "뭘 누를까" 의 답. 이게 안 바뀌면 지금 써도 된다 |
| **승률이 흔들리는가** | "이 판을 이기나" 의 답. 학습의 보상이 되는 값이다 |

설계 문서 4장의 *"규칙이 틀린 시뮬레이터에서 학습하면 틀린 것에 최적화된다"* 를
**말이 아니라 숫자로** 확인하는 자리다.
"""

import sys

import battle
import best
import calc
import scout

# 각 가정값을 무엇으로 바꿔 볼 것인가.
# 대부분 '본편의 다른 세대 값' 이다. 챔피언스가 어느 쪽인지 모르므로,
# 실제로 있을 법한 다른 값으로 바꿔 보고 답이 흔들리는지 본다.
# 자속(1.5)과 급소 배율(1.5)은 사용자가 확실하다고 확인해 줬으므로 뺐다.
# 감도 측정에서 답을 흔드는 것이 그 둘뿐이었는데, 확정되면서 그 구멍이 닫혔다.
ALTERNATIVES = [
    ("crit_rate", 1 / 16.0, "급소 확률 1/24 → 1/16"),
    ("burn_physical", 0.33, "화상 물리 0.5 → 0.33"),
    ("burn_chip", 8, "화상 칩 1/16 → 1/8 (2~6세대)"),
    ("poison_chip", 16, "독 칩 1/8 → 1/16 (1세대)"),
    ("toxic_chip", 8, "맹독 1/16 → 1/8 누적"),
    ("paralysis_speed", 0.25, "마비 스피드 0.5 → 0.25 (6세대 이전)"),
    ("paralysis_skip", 0.5, "마비 행동불가 25% → 50%"),
    ("sand_chip", 8, "모래 칩 1/16 → 1/8 (2세대)"),
    ("sand_rock_spdef", 1.0, "모래 바위 특방 1.5 → 없음"),
    ("terrain_boost", 1.5, "필드 강화 1.3 → 1.5"),
    ("sleep_max", 7, "잠듦 2~4턴 → 2~7턴"),
    ("freeze_thaw", 0.10, "얼음 해동 20% → 10%"),
    ("confuse_self", 0.5, "혼란 자해 1/3 → 1/2"),
    ("rock_hazard", 4, "스텔스록 1/8 → 1/4"),
]

# 기본으로 재 볼 대면들.
#
# 두 가지를 같이 챙긴다.
#   1. 접전일 것 — 한쪽이 100% 인 대면은 뭘 흔들어도 안 바뀐다
#   2. **그 가정값이 실제로 걸리는 대면일 것**
#      화상이 안 걸리는 대면에서 화상 칩댐을 흔들면 당연히 0.0%p 다.
#      그걸 '안 중요하다' 로 읽으면 안 되므로, 조건을 깨우는 대면을 넣어 둔다.
DEFAULT_PAIRS = [
    ("드닐레이브", "한카리아스"),       # 접전
    ("루카리오", "메가보만다"),         # 접전
    ("갑주무사", "따라큐"),             # 탈 · 선공기
    ("아머까오", "브리두라스"),         # 지구력 · 오래 끄는 대면
    ("고릴타", "하마돈"),               # 그래스필드 vs 모래바람 (날씨·필드)
    ("하마돈", "메가보만다"),           # 모래 칩댐 · 하품(잠듦)
    ("누리레느", "한카리아스"),         # 스텔스록 · 압정
    ("타부자고", "메가보만다"),         # 상태이상 · 회복
]

# 그 가정값이 '걸리는' 대면인지 따로 표시해 둔다.
# 0.0%p 가 나왔을 때 '안 중요' 인지 '안 나왔음' 인지 가르기 위한 것이다.
TOUCHED_BY = {
    "burn_chip": "화상", "burn_physical": "화상",
    "poison_chip": "독", "toxic_chip": "맹독",
    "paralysis_speed": "마비", "paralysis_skip": "마비",
    "sleep_max": "잠듦", "freeze_thaw": "얼음", "confuse_self": "혼란",
    "sand_chip": "모래바람", "sand_rock_spdef": "모래바람",
    "terrain_boost": "필드", "rock_hazard": "스텔스록",
}


# 형태 가정값은 위 목록에 못 넣는다. 저 목록은 **상대를 하나로 고정해 놓고**
# 재는데, 형태는 상대를 분포로 뽑을 때만 작동하기 때문이다.
# (거기 넣으면 0.0%p 가 나오는데, 그건 '안 중요' 가 아니라 '안 걸림' 이다.)
# 그래서 따로 잰다 — 아래 measure_forms.
# 세기는 구축기사 표본으로 맞춰 확정했다 (1-B). 그래서 재는 방향이 바뀌었다.
# "어느 값이 맞나" 가 아니라 **"표본으로 맞춘 것이 실제로 값을 했나"** 를 잰다.
# 내가 감으로 잡았던 값으로 되돌려 보고, 답이 달라지는지 본다.
FORM_ALTERNATIVES = [
    ("form_mismatch", 0.15, "기술↔형태: 표본 0.05 → 내 감 0.15 로 되돌림"),
    ("form_mismatch", 1.00, "기술을 형태로 안 가른다 (1-A 이전)"),
    ("nature_mismatch", 0.05, "성격↔형태: 표본 0.003 → 내 감 0.05 로 되돌림"),
    ("nature_mismatch", 1.00, "성격을 형태로 안 가른다"),
    ("item_tendency_strength", 1.0, "도구 경향: 표본 4.5 → 내 감 1.0 으로 되돌림"),
    ("item_tendency_strength", 0.0, "도구 경향을 안 쓴다 (측정은 했지만 무시)"),
    # **데이터가 받쳐 주는 범위 안에서** 흔든다. 표본 2,896마리에서 메가 세기의
    # 구별 안 되는 범위는 1.5 한 점이고, 0.75 는 6.2 · 3.0 은 8.7 만큼 나쁘다.
    # 그런 값으로 추천이 바뀌어도 "답이 흔들린다" 고 읽으면 안 된다 — 참고용이다.
    ("mega_stat_strength", 1.125, "메가 세기 1.5 → 1.125 (바로 아래 칸)"),
    ("mega_stat_strength", 0.75, "메가 세기 1.5 → 0.75 (한때 잘못 내렸던 값)"),
    ("mega_stat_strength", 0.0, "메가 종족값을 안 쓴다 (범위 밖 — 참고용)"),
]

# 형태로 기술이 크게 갈리는 상대들. forms.py 의 조사 결과에서 골랐다.
FORM_PAIRS = [
    ("메가보만다", "한카리아스"),     # 42%p 갈림
    ("루카리오", "망나뇽"),           # 54%p 갈림
    ("드닐레이브", "킬가르도"),       # 52%p 갈림
    ("하마돈", "리자몽"),             # 50%p 갈림
]


def rank_plans(dex, me, opp, plans, opp_plan, trials, seed=3):
    """계획들을 줄 세우고 1등과 그 승률을 돌려준다."""
    rows = []
    for p in plans:
        r = battle.evaluate(dex, me, opp, p, opp_plan, trials=trials, seed=seed)
        rows.append((r["winRate"], r["carry"], " → ".join(r["plan"])))
    rows.sort(key=lambda x: (-x[0], -x[1]))
    return rows[0][2], rows[0][0], [x[2] for x in rows]


def measure(dex, pairs, trials=150):
    """가정값을 하나씩 흔들어 보고 무엇이 답을 바꾸는지 잰다."""
    setups = []
    for a, b in pairs:
        try:
            me, _ = calc.popular_build(dex, dex.find_pokemon(a))
            opp, _ = calc.popular_build(dex, dex.find_pokemon(b))
        except LookupError:
            continue
        opp_plan, _, _ = battle.opponent_plan(dex, opp, me)
        plans, _ = battle.build_plans(dex, me, opp)
        if not plans:
            continue
        top, win, order = rank_plans(dex, me, opp, plans, opp_plan, trials)
        setups.append({"names": (a, b), "me": me, "opp": opp,
                       "plans": plans, "oppPlan": opp_plan,
                       "top": top, "win": win, "order": order})

    out = []
    for key, alt, why in ALTERNATIVES:
        if key not in calc.CONFIG:
            continue
        old = calc.CONFIG[key]
        calc.CONFIG[key] = alt
        flips, swing, order_moves = 0, 0.0, 0
        try:
            for st in setups:
                top, win, order = rank_plans(dex, st["me"], st["opp"],
                                             st["plans"], st["oppPlan"], trials)
                if top != st["top"]:
                    flips += 1
                if order != st["order"]:
                    order_moves += 1
                swing = max(swing, abs(win - st["win"]))
        finally:
            calc.CONFIG[key] = old
        out.append({"key": key, "why": why, "flips": flips,
                    "orderMoves": order_moves, "swing": swing,
                    "of": len(setups)})
    return out, setups


def measure_forms(dex, pairs=None, trials=200, seed=5):
    """형태 가정값(`form_mismatch`)이 답을 바꾸는가.

    이 값은 **데이터로 확인할 방법이 없다.** 사용률에 조합 정보가 없어서,
    "특수형이 지진을 들 승산을 얼마나 깎을 것인가" 는 아무도 안 알려준다.
    확인이 안 되면 최소한 **얼마나 중요한지는** 재 둬야 한다.
    """
    import forms

    pairs = pairs or FORM_PAIRS
    setups = []
    for a, b in pairs:
        try:
            me, _ = calc.popular_build(dex, dex.find_pokemon(a))
            opp_poke = dex.find_pokemon(b)
        except LookupError:
            continue
        opp, _ = calc.popular_build(dex, opp_poke)
        plans, _ = battle.build_plans(dex, me, opp)
        if not plans:
            continue
        setups.append({"names": (a, b), "me": me, "poke": opp_poke,
                       "plans": plans})

    def rank(st):
        rows = []
        for pl in st["plans"]:
            r = battle.evaluate_vs_distribution(dex, st["me"], st["poke"], pl,
                                                trials=trials, seed=seed)
            rows.append((r["winRate"], " → ".join(r["plan"])))
        rows.sort(key=lambda x: -x[0])
        return rows[0][1], rows[0][0]

    def clear():
        forms._TABLE_CACHE.clear()
        forms._PICK_CACHE.clear()
        scout._WEIGHT_CACHE.clear()

    keys = sorted(set(k for k, _, _ in FORM_ALTERNATIVES))
    saved = dict((k, calc.CONFIG[k]) for k in keys)
    base = []
    try:
        clear()
        for st in setups:
            base.append(rank(st))
        out = []
        for key, alt, why in FORM_ALTERNATIVES:
            calc.CONFIG[key] = alt
            clear()
            flips, swing = 0, 0.0
            for st, (top0, win0) in zip(setups, base):
                top, win = rank(st)
                if top != top0:
                    flips += 1
                swing = max(swing, abs(win - win0))
            calc.CONFIG[key] = saved[key]
            out.append({"why": why, "flips": flips, "swing": swing,
                        "of": len(setups)})
    finally:
        calc.CONFIG.update(saved)
        clear()
    return out, setups, base


def report_forms(rows, setups, base, trials):
    L = []
    line = "=" * 78
    L.append(line)
    L.append("  형태 가정값 감도 (1-A)   ·   대면 %d개 x %d판"
             % (len(setups), trials))
    L.append(line)
    for st, (top, win) in zip(setups, base):
        L.append("  %s vs %s — 기본 1등 '%s' (%.0f%%)"
                 % (st["names"][0], st["names"][1], top, win * 100))
    L.append("-" * 78)
    head = [("바꿔 본 값", 44), ("추천이 바뀐 대면", 18), ("승률 최대 흔들림", 18)]
    L.append("  " + "".join(best._pad(h, w) for h, w in head).rstrip())
    for r in rows:
        cells = [r["why"], "%d / %d" % (r["flips"], r["of"]),
                 "%.1f%%p" % (r["swing"] * 100)]
        mark = "   ← 추천이 바뀐다" if r["flips"] else ""
        L.append("  " + "".join(best._pad(c, w)
                                for c, (h, w) in zip(cells, head)).rstrip() + mark)
    L.append(line)
    return "\n".join(L)


def report(rows, setups, trials):
    L = []
    line = "=" * 78
    L.append(line)
    L.append("  가정값 감도 — 무엇을 먼저 실측해야 하는가   ·   대면 %d개 x %d판"
             % (len(setups), trials))
    L.append(line)
    for st in setups:
        L.append("  %s vs %s — 기본 1등 '%s' (%.0f%%)"
                 % (st["names"][0], st["names"][1], st["top"], st["win"] * 100))
    L.append("-" * 78)

    head = [("바꿔 본 값", 34), ("추천이 바뀐 대면", 18), ("승률 최대 흔들림", 18)]
    L.append("  " + "".join(best._pad(h, w) for h, w in head).rstrip())
    for r in sorted(rows, key=lambda x: (-x["flips"], -x["swing"])):
        cells = [r["why"],
                 "%d / %d" % (r["flips"], r["of"]),
                 "%.1f%%p" % (r["swing"] * 100)]
        mark = ""
        if r["flips"]:
            mark = "   ← 추천이 바뀐다"
        elif r["swing"] >= 0.15:
            mark = "   ← 승률이 크게 흔들린다"
        L.append("  " + "".join(best._pad(c, w)
                                for c, (h, w) in zip(cells, head)).rstrip() + mark)

    L.append("-" * 78)
    flipping = [r for r in rows if r["flips"]]
    swinging = [r for r in rows if not r["flips"] and r["swing"] >= 0.15]
    if flipping:
        L.append("  [먼저 실측할 것 — 추천 자체가 바뀐다]")
        for r in sorted(flipping, key=lambda x: -x["flips"]):
            L.append("    · %s" % r["why"])
    else:
        L.append("  [추천을 바꾸는 값은 없다]")
        L.append("    → \"뭘 누를까\" 는 지금 답을 믿어도 된다.")
    if swinging:
        L.append("")
        L.append("  [승률만 흔드는 것 — 학습에는 치명적, 한 턴 판단에는 덜 중요]")
        for r in sorted(swinging, key=lambda x: -x["swing"]):
            L.append("    · %-30s 최대 %.1f%%p" % (r["why"], r["swing"] * 100))
        L.append("")
        L.append("    승률은 학습의 보상이다. 이만큼 틀린 채로 학습하면")
        L.append("    틀린 것에 최적화되고, 시뮬레이터 안에서는 승률이 계속 올라")
        L.append("    틀렸다는 것을 눈치채지 못한다 (설계 문서 4장).")
    zero = [r for r in rows if not r["flips"] and r["swing"] < 0.005]
    if zero:
        L.append("")
        L.append("  [아무것도 안 바뀐 것 %d개]" % len(zero))
        L.append("    ! 0.0%p 는 '값이 안 중요하다' 가 아니라 **이 대면들에서는")
        L.append("      그 조건이 아예 안 나왔다** 는 뜻일 수 있다.")
        L.append("      (화상이 안 걸리는 대면에서는 화상 칩댐을 흔들어도 0 이다.)")
        L.append("      그 값이 걸리는 대면을 따로 넣어 다시 재 볼 것.")
    L.append(line)
    return "\n".join(L)


def main():
    args = sys.argv[1:]
    trials = 150
    rest = []
    i = 0
    while i < len(args):
        if args[i] == "--판수" and i + 1 < len(args):
            trials = int(args[i + 1]); i += 2
        else:
            rest.append(args[i]); i += 1

    dex = calc.Dex()
    if "--형태" in args:
        sys.stderr.write("  형태 가정값을 재는 중...\n")
        rows, setups, base = measure_forms(dex, trials=trials)
        print(report_forms(rows, setups, base, trials))
        return
    pairs = [(rest[0], rest[1])] if len(rest) >= 2 else DEFAULT_PAIRS
    sys.stderr.write("  대면 %d개 x 가정값 %d개를 재는 중...\n"
                     % (len(pairs), len(ALTERNATIVES)))
    rows, setups = measure(dex, pairs, trials=trials)
    print(report(rows, setups, trials))


if __name__ == "__main__":
    main()
