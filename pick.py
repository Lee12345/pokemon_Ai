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
import time

import paths

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
    by_idx = {(i, j): named[(mine.name, theirs.name)]
              for i, mine in enumerate(my6)
              for j, theirs in enumerate(opp6)}
    # ! 이름표도 같이 돌려준다. 이게 없으면 조합마다 `evaluate` 안에서
    #   3x3 표를 새로 재고, 그게 조합당 225판이라 예산이 4배로 터진다.
    by_idx["_named"] = named
    return by_idx


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
def _one_combo(dex, my6, opp6, table, a, b, trials, seed, named):
    """조합 하나를 돌린다. 이긴 판수를 돌려준다."""
    my_lead = _lead_for(a, b, table)
    op_lead = _lead_for(b, a, table, flip=True)
    mine = _ordered(my6, a, my_lead)
    theirs = _ordered(opp6, b, op_lead)
    opp_plan, _, _ = battle.opponent_plan(dex, theirs, mine)
    plans, _ = battle.build_plans(dex, mine, theirs)
    plan = plans[0] if plans else [dex.find_move("막치기")]
    r = battle.evaluate(dex, mine, theirs, plan, opp_plan,
                        trials=trials, seed=seed, matchup=named)
    return r["winRate"] * trials


def selection_matrix(dex, my6, opp6, table, trials=20, seed=5, verbose=False,
                     acc=None, deadline=None, say=None):
    """내 20가지 x 상대 20가지의 승률. 실제로 3대3 을 돌려서 잰다.

    acc 를 주면 **판수를 쌓는다** ({(a,b): [이긴판수, 전체판수]}).
    예산이 남으면 같은 조합을 더 돌려서 오차를 줄이는 데 쓴다.
    deadline 이 지나면 그 자리에서 멈춘다 — 칸마다 판수가 달라질
    뿐이라 승률 자체는 안 치우친다.
    """
    named = table.get("_named")
    my_trios = list(itertools.combinations(range(len(my6)), PICK))
    opp_trios = list(itertools.combinations(range(len(opp6)), PICK))
    acc = acc if acc is not None else {}
    total = len(my_trios) * len(opp_trios)
    done = 0
    stopped = False
    for a in my_trios:
        for b in opp_trios:
            if deadline is not None and time.time() > deadline:
                stopped = True
                break
            cell = acc.setdefault((a, b), [0.0, 0])
            cell[0] += _one_combo(dex, my6, opp6, table, a, b, trials,
                                  seed + done, named)
            cell[1] += trials
            done += 1
            if verbose and done % 40 == 0:
                sys.stderr.write("\r  %d / %d 조합" % (done, total))
                sys.stderr.flush()
        if stopped:
            break
    if verbose:
        sys.stderr.write("\r" + " " * 30 + "\r")
    out = {k: (v[0] / v[1] if v[1] else 0.0) for k, v in acc.items()}
    return out, my_trios, opp_trios


def rank_selections(matrix, my_trios, opp_trios, only=None):
    """내 20가지를 최악 기준·평균 기준으로 줄 세운다.

    only 를 주면 그 칸들만 본다 (예산이 모자라 다 못 돌렸을 때).
    """
    rows = []
    for a in my_trios:
        foes = [b for b in opp_trios
                if only is None or (a, b) in only]
        if not foes:
            continue
        vals = [matrix[(a, b)] for b in foes]
        worst_at = min(foes, key=lambda b: matrix[(a, b)])
        rows.append({
            "trio": a,
            "worst": min(vals),            # 상대가 제일 잘 고를 때
            "mean": sum(vals) / float(len(vals)),
            "best": max(vals),
            "worstAgainst": worst_at,      # 무엇을 내면 제일 곤란한가
            "nFoes": len(foes),            # 상대 몇 가지를 보고 낸 값인가
            # **선봉도 답의 일부다.** 전에는 보고서가 "3마리" 까지만 말하고
            # 누구를 먼저 낼지는 안 알려줬다. 실전에서는 그걸 정해야
            # 다음 화면으로 넘어간다. 사용자가 되물어서 넣었다 (2026-09-19).
            "lead": None,                  # 아래 attach_leads 가 채운다
            "leadWorst": None,
        })
    return rows


# ---------------------------------------------------------------------------
# 예산 안에서 고르기 — 창·글자판이 쓰는 문
# ---------------------------------------------------------------------------
# 한 조합을 이만큼은 돌려야 숫자를 믿는다 (승률 오차 최대 ±16%p).
MIN_TRIALS = 10


def _combo_cost(dex, my6, opp6, table, seed=1):
    """조합 하나에 드는 비용을 **두 점으로 재서** 갈라놓는다.

    (고정비, 한 판당 비용). 조합마다 `opponent_plan` · `build_plans` 를
    한 번씩 부르는데 그게 판수와 상관없이 드는 값이라, 한 점만 재면
    예산이 크게 어긋난다.

    ! **첫 판으로 재지 않는다.** 처음 한 번은 캐시를 덥히느라 실제의
      수백 배가 나온다. 7단계에서 똑같은 것으로 크게 틀렸다.
    """
    a = list(range(PICK))
    b = list(range(PICK))
    named = table.get("_named")
    # 덥히기 — 버린다
    for i in range(3):
        _one_combo(dex, my6, opp6, table, a, b, 1, seed + 900 + i, named)

    def at(trials, tag):
        fastest = None
        for i in range(3):
            t0 = time.time()
            _one_combo(dex, my6, opp6, table, a, b, trials,
                       seed + tag * 100 + i, named)
            took = time.time() - t0
            fastest = took if fastest is None else min(fastest, took)
        return fastest

    lo, hi = 1, 9
    t_lo, t_hi = at(lo, 1), at(hi, 2)
    per = max(1e-6, (t_hi - t_lo) / float(hi - lo))
    fixed = max(0.0, t_lo - per * lo)
    return fixed, per


def choose(dex, my6, opp6, seconds=60.0, seed=1, say=None):
    """예산(초) 안에서 선출을 고른다.

    400 조합을 **전부** 훑는 것은 그대로 두고, 남는 시간으로 판수를
    쌓는다. 판수를 적어 돌려주므로 오차를 같이 말할 수 있다.

    돌려주는 것 —
      rows / myTrios / oppTrios / matrix / table
      trials     : 조합당 판수 (제일 적게 돌린 칸 기준)
      pairTrials : 1대1 상성표에 쓴 판수
      spent      : 실제로 쓴 초
      tight      : 최소 판수조차 다 못 돌렸으면 True
    """
    my6, opp6 = list(my6), list(opp6)
    n_combos = (len(list(itertools.combinations(range(len(my6)), PICK)))
                * len(list(itertools.combinations(range(len(opp6)), PICK))))
    n_pairs = len(my6) * len(opp6)

    t0 = time.time()
    end = t0 + seconds
    # 상성표를 먼저 챙긴다. 교체 판단이 여기서 나오므로 이게 부실하면
    # 400조합이 다 부실해진다. 그리고 조합마다 물려줘서 다시 안 잰다.
    pair_trials = 25
    if say:
        say("1대1 상성표 재는 중 (%d쌍 x %d판)" % (n_pairs, pair_trials))
    table = pairwise(dex, my6, opp6, trials=pair_trials, seed=seed)

    fixed, per = _combo_cost(dex, my6, opp6, table, seed)
    left = max(0.0, end - time.time())
    # 한 바퀴(모든 조합 1판) 에 드는 시간
    lap = n_combos * (fixed + per)
    first = max(MIN_TRIALS, int((left * 0.6 - n_combos * fixed)
                                / max(1e-9, n_combos * per)))
    if say:
        say("조합 %d가지 · 고정비 %.1fms + 판당 %.1fms → 첫 바퀴 %d판"
            % (n_combos, fixed * 1000, per * 1000, first))

    acc = {}
    matrix, my_trios, opp_trios = selection_matrix(
        dex, my6, opp6, table, trials=first, seed=seed + 4, acc=acc,
        deadline=end)
    # 남는 예산으로 판수를 더 쌓는다. 한 바퀴가 통째로 들어갈 만할 때만.
    passes = 1
    while True:
        left = end - time.time()
        add = int((left - n_combos * fixed) / max(1e-9, n_combos * per))
        if add < MIN_TRIALS or left < lap:
            break
        matrix, my_trios, opp_trios = selection_matrix(
            dex, my6, opp6, table, trials=add, seed=seed + 40 * passes,
            acc=acc, deadline=end)
        passes += 1
        if say:
            say("남는 시간으로 %d판 더 쌓았다" % add)

    done = [v[1] for v in acc.values()]
    trials = min(done) if done else 0
    # 한 바퀴를 다 못 돌았으면 칸이 비어 있다 — 그건 숨기면 안 된다.
    missing = n_combos - len(acc)
    rows = rank_selections(matrix, my_trios, opp_trios,
                           only=set(acc.keys()))
    attach_leads(rows, table, opp6)
    return {"rows": rows, "myTrios": my_trios, "oppTrios": opp_trios,
            "matrix": matrix, "table": table, "trials": trials,
            "pairTrials": pair_trials, "spent": time.time() - t0,
            "tight": trials < MIN_TRIALS or missing > 0,
            "missing": missing, "combos": n_combos,
            "fixed": fixed, "perBattle": per}


def attach_leads(rows, table, opp6):
    """조합마다 **선봉**을 정해서 붙인다.

    lead       상대 6마리 전체를 상대로 평균 승률이 제일 높은 놈 (무난한 답)
    leadWorst  제일 곤란한 상대 선출을 상대로 제일 나은 놈 (최악 기준의 답)

    ! **이건 정한 규칙이지 끝까지 돌려 본 것이 아니다.** 선봉을 바꿔
      가며 400조합을 다시 돌리면 8배가 든다. 보고서가 그렇게 밝힌다.
    """
    all_foes = list(range(len(opp6)))
    for r in rows:
        r["lead"] = _lead_for(r["trio"], all_foes, table)
        r["leadWorst"] = _lead_for(r["trio"], r["worstAgainst"], table)
    return rows


def real_names(dex, party, trio, lead):
    """**실제로 싸우는 몸의 이름**을 선봉부터 순서대로.

    ! 메가진화는 한 게임에 한 번뿐이라, 메가스톤을 둘 이상 들고 나가도
      메가가 되는 것은 **먼저 나오는 놈** 하나다. 그런데 보고서가
      `calc.popular_build` 이 만든 이름을 그대로 찍으면 '메가보만다' 라고
      적어 놓고 실제로는 '보만다' 로 싸운다. **화면과 계산이 갈라지는
      자리다** — 이 저장소가 늘 고장나는 방식이다.
      그래서 `battle._one_mega_only` 를 똑같이 태워서 이름을 받는다.
    """
    order = [lead] + [i for i in trio if i != lead]
    fixed, _note = battle._one_mega_only(dex, [party[i] for i in order])
    return [b.name for b in fixed]


def _trio_line(dex, party, r, key="lead"):
    """'선봉 A → B · C' 처럼. 선봉을 맨 앞에 놓고 화살표로 가른다."""
    lead = r.get(key)
    if lead is None:
        return _names(party, r["trio"])
    got = real_names(dex, party, r["trio"], lead)
    return "%s → %s" % (got[0], " · ".join(got[1:]))


def short_report(dex, my6, opp6, got):
    """창·글자판에 뿌릴 짧은 보고서. 폰에서도 읽히게 좁게.

    **답을 한 줄로 못 박는다.** 3마리와 **선봉**까지. 전에는 3마리까지만
    말해서 "그래서 누굴 먼저 내라는 거지?" 가 남았다.
    """
    rows = sorted(got["rows"], key=lambda x: -x["worst"])
    err = trio_error(got["trials"]) * 100
    by_worst = max(got["rows"], key=lambda x: x["worst"])
    by_mean = max(got["rows"], key=lambda x: x["mean"])

    L = []
    L.append("  " + "=" * 52)
    L.append("  [선출]  이 3마리를 이 순서로 내세요")
    L.append("  " + "=" * 52)
    L.append("")
    best = real_names(dex, my6, by_worst["trio"], by_worst["leadWorst"])
    L.append("    ▶ 선봉   %s" % best[0])
    L.append("      벤치   %s" % " · ".join(best[1:]))
    L.append("")
    L.append("      최악 기준 승률 %.0f%% ±%.0f%%p   (평균 기준 %.0f%%)"
             % (by_worst["worst"] * 100, err, by_worst["mean"] * 100))
    if by_worst["trio"] != by_mean["trio"]:
        L.append("")
        L.append("    ! 평균 기준으로는 다른 답이 나온다:")
        alt = real_names(dex, my6, by_mean["trio"], by_mean["lead"])
        L.append("      ▶ 선봉 %s / 벤치 %s   (평균 %.0f%%)"
                 % (alt[0], " · ".join(alt[1:]), by_mean["mean"] * 100))
        L.append("      크게 지지 않으려면 위, 상대가 특별히 잘 고르지")
        L.append("      않는다고 보면 아래.")
    else:
        L.append("      (최악 기준과 평균 기준이 같다. 고민할 것 없다.)")

    L.append("")
    L.append("  " + "-" * 52)
    L.append("   %-32s %7s %7s" % ("다른 후보 (선봉 → 벤치)", "최악", "평균"))
    for r in rows[:5]:
        L.append("   %-32s %6.0f%% %6.0f%%"
                 % (_trio_line(dex, my6, r, "leadWorst"), r["worst"] * 100,
                    r["mean"] * 100))
    L.append("  " + "-" * 52)
    L.append("   제일 곤란한 상대 선출: %s"
             % _names(opp6, by_worst["worstAgainst"]))
    L.append("   %d가지 조합을 %d판 이상씩 돌렸다 (%.0f초)"
             % (got["combos"] - got.get("missing", 0), got["trials"],
                got["spent"]))

    if got.get("missing"):
        L.append("   ! 시간이 모자라 %d가지 조합 중 %d가지를 못 돌렸다."
                 % (got["combos"], got["missing"]))
        L.append("     안 돌린 것이 더 나빴을 수 있다. 초를 늘리세요.")
    elif got["tight"]:
        L.append("   ! 시간이 모자라 조합당 %d판만 돌렸다 (오차 ±%.0f%%p)."
                 % (got["trials"], err))
        L.append("     이 정도 차이는 우연일 수 있다. 초를 늘리세요.")
    if abs(by_worst["worst"] - by_mean["worst"]) * 100 < err:
        L.append("   ! 1등과 2등 차이가 오차(±%.0f%%p)보다 작다 —" % err)
        L.append("     어느 쪽도 확실하지 않다.")
    L.append("   ! **선봉은 정한 규칙으로 골랐다** (상대에게 평균 승률이")
    L.append("     제일 높은 놈). 3마리처럼 끝까지 돌려 본 것이 아니다.")
    L.append("   ! 상대 배분·기술은 사용률 1위로 봤다 (아직 분포를 안 썼다).")
    if any("메가" in b.name for b in my6):
        L.append("   ! 메가는 **한 게임에 하나뿐**이라 선봉만 메가가 된다.")
        L.append("     위 이름은 실제로 싸우는 몸으로 적었다.")
    L.append("  " + "=" * 52)
    return "\n".join(L)


def trio_error(trials):
    """조합당 판수에서 오는 승률 오차(대략). 이기냐 지냐라 분산이 최대 0.25."""
    return 0.5 / (max(1, trials) ** 0.5)


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
    paths.fix_console()   # 윈도우에서 한글을 찍다 죽지 않게
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
