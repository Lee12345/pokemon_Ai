# -*- coding: utf-8 -*-
"""
6단계 — 선출. 6마리 중 어떤 3마리를 낼 것인가.

(파일 이름이 select.py 가 아니라 pick.py 인 이유: select 는 파이썬 표준 모듈
 이름이라, 그렇게 두면 표준 select 를 가려 버린다. 실제로 한 번 물렸다.)

    python pick.py 내1,내2,내3,내4,내5,내6 상대1,상대2,상대3,상대4,상대5,상대6

챔피언스 기본 룰이 **6마리 파티에서 3마리 선출**이다.
서로의 6마리를 보고 **동시에** 3마리를 고른다. 대전이 시작되기 전에
이미 한 번 가위바위보를 하는 셈이다 (설계 문서 3-4(1)).

다만 대전 중보다 훨씬 작다.

    내가 고를 수 있는 조합   6C3 = 20
    상대도                  20
    합쳐서                  400   <- 전부 훑어볼 수 있는 크기다

그래서 **근사하지 않고 실제로 돌린다.** 400 조합을 `battle.py` 로 시뮬레이션한다.
(3대3 한 판이 5ms 쯤이라 다 돌려도 1분 안쪽이다.)

## 무엇을 답으로 삼을 것인가

상대가 무엇을 낼지 모르므로 답이 하나가 아니다. 두 가지로 낸다.

| | 뜻 | 언제 쓰나 |
|---|---|---|
| **최악 기준** | 상대가 제일 아픈 3마리를 낸다고 보고, 그중 제일 나은 선택 | 크게 지지 않고 싶을 때 |
| **평균 기준** | 상대의 20가지를 다 평균 | 상대가 특별히 잘 고르지 않을 때 |

5장의 구분이 여기서 그대로 나온다 — 최악 기준이 균형 전략, 평균 기준이 착취 쪽이다.
"""

import itertools
import random
import sys

import battle
import best
import calc

PICK = 3            # 몇 마리를 내는가


# ---------------------------------------------------------------------------
# 1대1 상성표 — 누가 누구에게 강한가
# ---------------------------------------------------------------------------
def pairwise(dex, my6, opp6, trials=40, seed=1):
    """내 6마리 x 상대 6마리의 1대1 승률.

    선출을 정하는 데도 쓰지만, 사람이 보기에는 이게 제일 쓸모 있다.
    "내 어떤 놈이 상대 어떤 놈을 잡는가" 가 한눈에 보인다.

    battle.matchup_table 과 같은 것을 재므로 그걸 그대로 쓴다.
    (거기서 캐시까지 해 주므로 뒤에서 교체 판단에 다시 쓸 때 공짜다.)
    """
    named = battle.matchup_table(dex, my6, opp6, trials=trials, seed=seed)
    return {(i, j): named[(mine.name, theirs.name)]
            for i, mine in enumerate(my6)
            for j, theirs in enumerate(opp6)}


def _lead_for(trio_idx, foe_trio_idx, table, flip=False):
    """이 셋 중 누구를 먼저 낼 것인가.

    상대 셋을 상대로 평균 승률이 제일 높은 놈을 낸다.
    (누구를 먼저 내는지도 하나의 결정이지만, 여기서는 이 규칙으로 고정한다.)
    """
    def score(i):
        vals = []
        for j in foe_trio_idx:
            v = table[(j, i)] if flip else table[(i, j)]
            vals.append(v if not flip else 1.0 - v)
        return sum(vals) / float(len(vals))
    return max(trio_idx, key=score)


def _ordered(party, trio_idx, lead):
    """리드를 맨 앞으로 놓은 파티."""
    rest = [i for i in trio_idx if i != lead]
    return [party[lead]] + [party[i] for i in rest]


# ---------------------------------------------------------------------------
# 400 조합 전부 돌리기
# ---------------------------------------------------------------------------
def selection_matrix(dex, my6, opp6, table, trials=20, seed=5, verbose=False):
    """내 20가지 x 상대 20가지의 승률. 실제로 3대3 을 돌려서 잰다."""
    my_trios = list(itertools.combinations(range(len(my6)), PICK))
    opp_trios = list(itertools.combinations(range(len(opp6)), PICK))
    out = {}
    total = len(my_trios) * len(opp_trios)
    done = 0
    for a in my_trios:
        for b in opp_trios:
            my_lead = _lead_for(a, b, table)
            op_lead = _lead_for(b, a, table, flip=True)
            mine = _ordered(my6, a, my_lead)
            theirs = _ordered(opp6, b, op_lead)
            opp_plan, _, _ = battle.opponent_plan(dex, theirs, mine)
            plans, _ = battle.build_plans(dex, mine, theirs)
            plan = plans[0] if plans else [dex.find_move("막치기")]
            r = battle.evaluate(dex, mine, theirs, plan, opp_plan,
                                trials=trials, seed=seed + done)
            out[(a, b)] = r["winRate"]
            done += 1
            if verbose and done % 40 == 0:
                sys.stderr.write("\r  %d / %d 조합" % (done, total))
                sys.stderr.flush()
    if verbose:
        sys.stderr.write("\r" + " " * 30 + "\r")
    return out, my_trios, opp_trios


def rank_selections(matrix, my_trios, opp_trios):
    """내 20가지를 최악 기준·평균 기준으로 줄 세운다."""
    rows = []
    for a in my_trios:
        vals = [matrix[(a, b)] for b in opp_trios]
        worst_at = min(opp_trios, key=lambda b: matrix[(a, b)])
        rows.append({
            "trio": a,
            "worst": min(vals),            # 상대가 제일 잘 고를 때
            "mean": sum(vals) / float(len(vals)),
            "best": max(vals),
            "worstAgainst": worst_at,      # 무엇을 내면 제일 곤란한가
        })
    return rows


# ---------------------------------------------------------------------------
# 보고서
# ---------------------------------------------------------------------------
def _names(party, idx):
    return " · ".join(party[i].name for i in idx)


def report(my6, opp6, table, rows, my_trios, opp_trios, matrix, trials):
    L = []
    line = "=" * 78
    L.append(line)
    L.append("  6단계  선출 — 6마리 중 3마리   ·   400 조합을 실제로 돌렸다"
             " (조합당 %d판)" % trials)
    L.append(line)
    L.append("  나   " + ", ".join(b.name for b in my6))
    L.append("  상대 " + ", ".join(b.name for b in opp6))
    L.append("-" * 78)

    # 1대1 상성표
    L.append("[1대1 상성표]  내 세로 / 상대 가로 — 내가 이길 확률")
    head = "    " + best._pad("", 16) + "".join(
        best._pad(b.name[:8], 10) for b in opp6)
    L.append(head.rstrip())
    for i, mine in enumerate(my6):
        cells = []
        for j in range(len(opp6)):
            v = table[(i, j)]
            mark = "O" if v >= 0.65 else ("X" if v <= 0.35 else " ")
            cells.append(best._pad("%3.0f%%%s" % (v * 100, mark), 10))
        L.append("    " + best._pad(mine.name[:14], 16) + "".join(cells).rstrip())
    L.append("      O = 65% 이상으로 이김 / X = 35% 이하")

    # 선출 순위
    L.append("-" * 78)
    L.append("[어떤 3마리를 낼까]")
    L.append("    최악 기준 = 상대가 제일 아픈 3마리를 낸다고 볼 때의 승률")
    L.append("    평균 기준 = 상대의 20가지를 다 평균한 승률")
    L.append("")
    head = [("3마리", 34), ("최악", 8), ("평균", 8), ("최고", 8),
            ("제일 곤란한 상대 선출", 30)]
    L.append("  " + "".join(best._pad(h, w) for h, w in head).rstrip())
    for r in sorted(rows, key=lambda x: -x["worst"])[:6]:
        cells = [_names(my6, r["trio"]),
                 "%.0f%%" % (r["worst"] * 100),
                 "%.0f%%" % (r["mean"] * 100),
                 "%.0f%%" % (r["best"] * 100),
                 _names(opp6, r["worstAgainst"])]
        L.append("  " + "".join(best._pad(c, w)
                                for c, (h, w) in zip(cells, head)).rstrip())

    by_worst = max(rows, key=lambda x: x["worst"])
    by_mean = max(rows, key=lambda x: x["mean"])
    L.append("-" * 78)
    L.append("  최악 기준 추천   %s   (최악 %.0f%% / 평균 %.0f%%)"
             % (_names(my6, by_worst["trio"]), by_worst["worst"] * 100,
                by_worst["mean"] * 100))
    L.append("  평균 기준 추천   %s   (최악 %.0f%% / 평균 %.0f%%)"
             % (_names(my6, by_mean["trio"]), by_mean["worst"] * 100,
                by_mean["mean"] * 100))
    if by_worst["trio"] == by_mean["trio"]:
        L.append("  → 둘이 같다. 고민할 것 없다.")
    else:
        L.append("  → 둘이 다르다. 크게 지지 않으려면 위쪽,")
        L.append("     상대가 특별히 잘 고르지 않는다고 보면 아래쪽.")

    L.append("")
    L.append("  ! 여기서 정한 것은 '어떤 3마리' 까지다. 누구를 먼저 낼지는")
    L.append("    '상대 셋에게 평균 승률이 제일 높은 놈' 으로 고정했다.")
    L.append("    그것도 하나의 결정이라 따로 볼 자리다.")
    L.append("  ! 상대 배분·기술은 사용률 1위로 봤다. --분포 는 아직 여기 안 붙였다.")
    L.append(line)
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 명령줄
# ---------------------------------------------------------------------------
USAGE = """사용법: python pick.py <내 6마리> <상대 6마리>

  포켓몬은 쉼표로 적는다. 6마리가 아니어도 된다 (3마리 이상이면 됨).

  --판수 30      조합 하나당 몇 판을 돌릴지 (기본 20)
  --쌍판수 60    1대1 상성표에 쓸 판수 (기본 40)

  예 : python pick.py 메가보만다,한카리아스,고릴타,아머까오,따라큐,킬가르도 \\
                        하마돈,브리두라스,누리레느,갑주무사,루카리오,드닐레이브
"""


def main():
    args = sys.argv[1:]
    trials, pair_trials = 20, 40
    rest = []
    i = 0
    while i < len(args):
        if args[i] == "--판수" and i + 1 < len(args):
            trials = int(args[i + 1]); i += 2
        elif args[i] == "--쌍판수" and i + 1 < len(args):
            pair_trials = int(args[i + 1]); i += 2
        else:
            rest.append(args[i]); i += 1

    if len(rest) < 2:
        print(USAGE)
        return

    dex = calc.Dex()
    try:
        my6 = [calc.popular_build(dex, dex.find_pokemon(n))[0]
               for n in rest[0].split(",") if n.strip()]
        opp6 = [calc.popular_build(dex, dex.find_pokemon(n))[0]
                for n in rest[1].split(",") if n.strip()]
    except LookupError as e:
        print("! %s" % e)
        return
    if len(my6) < PICK or len(opp6) < PICK:
        print("! 양쪽 다 %d마리 이상이어야 합니다." % PICK)
        return

    sys.stderr.write("  1대1 상성표 재는 중 (%d쌍)...\n" % (len(my6) * len(opp6)))
    table = pairwise(dex, my6, opp6, trials=pair_trials)
    sys.stderr.write("  선출 조합 돌리는 중...\n")
    matrix, my_trios, opp_trios = selection_matrix(
        dex, my6, opp6, table, trials=trials, verbose=True)
    rows = rank_selections(matrix, my_trios, opp_trios)
    print(report(my6, opp6, table, rows, my_trios, opp_trios, matrix, trials))


if __name__ == "__main__":
    main()
