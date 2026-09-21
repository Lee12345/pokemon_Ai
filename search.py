# -*- coding: utf-8 -*-
"""7단계 — 여러 턴을 내다보고 이번 턴의 수를 고른다.

    python search.py 한카리아스,아머까오,누리레느 하마돈,브리두라스,갑주무사
    python search.py 한카리아스,아머까오 하마돈 --초 20 --봤다 지진,자뭉열매

## 4-B 와 무엇이 다른가

`battle.py` 는 **내가 수순을 미리 정해 주면** 그대로 돌려 본다
("역린 -> 역린 -> 역린 을 400판 돌려라"). 여기는 반대다.
**이번 턴에 둘 수 있는 모든 수를 각각 끝까지 돌려 보고 제일 나은 것을
고른다.** 기술 4개 + 벤치로 교체 2개면 수가 6개다.

## 얼마나 깊이 보나 — **되도록 끝까지 본다**

사용자가 정한 방침이다 (2026-09-18): "C로 하되 가능하면 끝까지
돌려보는게 좋아."

그래서 기본은 **끝까지**다. 판이 끝날 때까지 돌리고 이겼나 졌나로
센다. 예산(초)이 모자랄 때만 줄인다. 줄이는 순서도 정해 뒀다 —

  1. **판수를 줄인다.** 깊이는 그대로 두고 수마다 돌리는 횟수를 줄인다.
  2. **가망 없는 수를 먼저 버린다.** 전부에 똑같이 나눠 주면 뻔히 나쁜
     수에 예산의 절반을 쓰게 된다. 적은 판수로 한 바퀴 돌려 보고
     하위 절반을 떨어뜨린 뒤, 살아남은 수에 판수를 두 배로 준다.
     이걸 예산이 다할 때까지 되풀이한다. 마지막에는 후보 한두 개가
     제일 많은 판수를 받는다.
  3. **그래도 모자라면** 그때만 몇 턴에서 끊고 판세로 점수를 매긴다
     (`shallow`). 이건 마지막 수단이고, 썼으면 보고서에 적는다.

2번이 핵심이다. 같은 예산으로 **중요한 후보에 더 많은 판수**가 간다.

## 상대는 어떻게 두나

**상대도 파티다.** 챔피언스는 6마리에서 3마리를 내는 룰이라 상대도
보통 셋이다. 전에는 여기에 **한 마리만** 넣을 수 있었다. 그러면
"이 한 마리를 이기는 수" 를 고르게 되는데, 실제로 이겨야 하는 것은
**판**이다. 상대에게 벤치가 있으면 "지금 이놈을 잡는 것" 과
"판을 이기는 것" 이 자주 다른 답을 낸다.

상대 몸은 매 판 사용률대로 새로 뽑는다 (4-C, `scout.sample_opponent`).
파티면 **각자 따로** 뽑는다. 본 기술·본 도구가 있으면 그만큼 좁혀진다.
상대의 수는 그때그때 제일 아픈 수를 고르고, 불리하면 스스로 뺀다 —
`battle.Policy` 가 한다.

**본 것은 그놈에게만 붙인다.** '지진을 봤다' 는 그때 나와 있던 놈이
지진을 쓴다는 뜻이지, 벤치의 누리레느도 지진을 든다는 뜻이 아니다.
그래서 `evidence` 를 하나만 주면 **맨 앞(나와 있는 놈)** 에만 붙고,
여럿에게 붙이려면 목록이나 {이름: 관찰} 로 준다.

**상대를 '제일 잘 두는 상대' 로 보지 않는다.** 그건 최악을 가정하는
것이고, 그러면 모든 수가 나빠 보여서 아무것도 못 고른다. 대신 실제로
만날 상대들의 평균을 본다.
"""

import random
import sys
import time

import battle
import best
import calc
import paths
import scout


# 후보 하나에 최소 이만큼은 돌려야 숫자를 믿을 수 있다.
# 30판이면 승률의 표준오차가 최대 9%p 다 (0.5 x sqrt(1/30)).
MIN_ROLLOUTS = 30
# 시간을 재기 전에 캐시를 덥힌다. **횟수를 고정하면 안 된다** —
# 첫 판이 461ms, 더워진 뒤가 2.1ms 로 **220배** 차이가 났다. 3판만
# 덥히고 재면 아직 차가운 값을 잡아서, 멀쩡한 판인데 "예산이 모자라다"
# 며 얕은 모드로 떨어진다. 실제로 그래서 매 세션 첫 턴이 얕은 모드로
# 돌았고, 점수가 전부 100.00 으로 나와 그럴듯해 보였다.
WARMUP_MAX = 25          # 이만큼까지 덥힌다
WARMUP_SECONDS = 2.0     # 또는 이 시간까지
WARMUP_SETTLE = 3.0      # 제일 빠른 판의 이 배수 안에 들면 더워진 것으로 본다
PROBE = 5
# 한 바퀴 돌 때마다 판수를 이만큼 곱한다
GROW = 2.0
# 하위 몇 할을 떨어뜨리나
CUT = 0.5
# 마지막 수단으로 몇 턴에서 끊나
SHALLOW_TURNS = 6


def candidate_actions(dex, party, my_moves=None):
    # ! party.active 를 본다. 교체한 뒤에는 나와 있는 놈의 기술이어야 한다.
    """이번 턴에 둘 수 있는 수들. 기술 + 교체.

    my_moves 를 주면 **내가 실제로 들고 있는 기술**을 쓴다. 안 주면
    사용률 상위로 대신한다 — 내 파티인데 기술을 모르는 것은 이상하므로
    보고서가 그 사실을 밝힌다.
    """
    side = party.active
    if my_moves:
        moves = [dex.find_move(m) if isinstance(m, str) else m
                 for m in my_moves]
        guessed = False
    else:
        moves = [m for m, _ in battle.realistic_moveset(dex, side.base.poke)]
        guessed = True
    out = [("기술", m) for m in moves]
    # ★ **메가진화도 수다.** 한 게임에 한 번이라 "지금 쓸까, 아껴 둘까" 가
    #   진짜 판단이다. 기술마다 '메가하고 쓴다' 를 짝으로 넣는다.
    #   사용자가 못 박았다 — "무조건 B야. 이건 선택이 아니라 필수".
    #   후보가 두 배가 되지만, 예산 배분(가망 없는 수를 먼저 접는 것)이
    #   그대로 돌아가므로 나쁜 쪽은 금방 떨어진다.
    if party.can_mega():
        out += [("메가", m) for m in moves]
    for i, _ in party.bench():
        out.append(("교체", i))
    return out, guessed


def _as_plan(action):
    """후보 하나를 battle.Policy 가 받는 '계획' 으로."""
    kind, what = action
    if kind == "교체":
        return [("교체", what)]
    if kind == "메가":
        return [("메가", what)]
    return [what]


def _score(res):
    """판 하나의 값어치. 0~1.

    **이기면 무조건 1.0 으로 두면 안 된다.** 3마리 다 살려 이긴 것과
    두 마리를 내주고 간신히 이긴 것이 같은 점수가 되어 버린다. 그러면
    "지금 이놈을 공짜로 잃어도 어차피 벤치가 이기니까 괜찮다" 는 수를
    고른다. 실제로 그래서 뺐어야 할 자리에서 안 뺐다.

    그래서 이김 안에서 **남은 파티 HP** 로 갈라 준다.
      이김   0.70 ~ 1.00
      비김   0.35 ~ 0.50
      짐     0.00
    이긴 판은 어떤 비긴 판보다도 항상 위다 — 이기는 것이 먼저다.
    HP 로 가르는 폭(0.30)은 **내가 정한 값이지 잰 것이 아니다.**
    """
    hp = max(0.0, min(1.0, res["myPartyHpPct"] / 100.0))
    if res["result"] == "이김":
        return 0.70 + 0.30 * hp
    if res["result"] == "짐":
        return 0.0
    return 0.35 + 0.15 * hp


def _position_value(b):
    """판을 중간에서 끊었을 때의 판세. 0~1.

    마릿수가 먼저고, 같으면 남은 HP 로 가른다. **이건 내가 정한 기준이지
    잰 것이 아니다.** 그래서 이 값으로 고른 수는 보고서에 표시한다.
    """
    def side_value(party):
        alive = sum(1 for m in party.members if m.alive)
        hp = sum(m.hp for m in party.members)
        top = sum(m.max_hp for m in party.members)
        return alive + (hp / float(top) if top else 0.0)

    mine = side_value(b.me_party)
    theirs = side_value(b.opp_party)
    if theirs <= 0:          # 상대를 다 잡았다 — 이긴 것과 같게 센다
        top = float(len(b.me_party.members))
        return 0.70 + 0.30 * min(1.0, mine / top if top else 1.0)
    if mine <= 0:
        return 0.0
    total = mine + theirs
    # 안 끝난 판은 비긴 자리(0.35~0.50)에 놓는다. 끝까지 본 점수와
    # 자리를 맞춰야 둘을 나란히 볼 수 있다.
    return 0.35 + 0.15 * (mine / total)


def _as_list(x):
    return list(x) if isinstance(x, (list, tuple)) else [x]


def _evidence_for(evidence, index, poke):
    """상대 파티에서 i번째 놈에게 붙는 관찰.

    ! **하나 줬다고 전부에 붙이면 안 된다.** 그러면 상대 세 마리가
      전부 지진을 들고 나오는데, 승률은 멀쩡한 숫자로 나온다.
    """
    if evidence is None:
        return None
    if isinstance(evidence, dict):
        return evidence.get(poke["name"])
    if isinstance(evidence, (list, tuple)):
        return evidence[index] if index < len(evidence) else None
    return evidence if index == 0 else None


def sample_opp_party(dex, opp_pokes, rng, evidence=None, opp_build=None):
    """상대가 낸 파티를 한 판치 뽑는다. ([빌드], [[기술]]).

    opp_build 를 주면 뽑지 않고 그것을 쓴다 (몸을 아는 시험용).
    """
    if opp_build is not None:
        builds = _as_list(opp_build)
        return builds, [[m for m, _ in battle.realistic_moveset(dex, b.poke)]
                        for b in builds]
    speed_of = lambda b: best.effective_speed(dex, b)[0]
    builds, movesets = [], []
    for i, poke in enumerate(_as_list(opp_pokes)):
        b, mv = scout.sample_opponent(
            dex, poke, rng, _evidence_for(evidence, i, poke), speed_of)
        builds.append(b)
        movesets.append(mv)
    return builds, movesets


def rollout(dex, my_party, opp_pokes, action, rng, evidence=None,
            opp_build=None, turns=None, my_moves=None, state=None):
    """한 판. 이번 턴에 `action` 을 두고 나머지는 양쪽이 알아서 둔다.

    turns 를 주면 그 턴에서 끊고 판세로 점수를 매긴다 (마지막 수단).
    """
    opp_builds, opp_sets = sample_opp_party(
        dex, opp_pokes, rng, evidence, opp_build)
    st = state or {}
    # 상대의 첫 수는 **지금 나와 있는 놈끼리** 재야 한다.
    # ! 전에는 양쪽 다 [0] 으로 굳어 있었다. 2번을 내보낸 채로 물으면
    #   상대가 1번을 겨냥한 기술을 골랐다 — 조용히 틀어지는 자리다.
    ai = min(st.get("my_active", 0), len(my_party) - 1)
    oi = min(st.get("opp_active", 0), len(opp_builds) - 1)
    opp_moves = opp_sets[oi]
    rows = best.rate_moves(dex, opp_builds[oi], my_party[ai],
                           [(m, None) for m in opp_moves])
    threat = best.best_threat(rows)
    opp_plan = [threat["move"]] if threat else [
        opp_moves[0] if opp_moves else dex.find_move("막치기")]
    # 상대도 메가를 쓴다. **안 쓰게 두면 상대가 실제보다 약해진다** —
    # 그러면 내 승률이 통째로 뻥튀기된다. 상대는 '첫 기회에 바로' 로 둔다
    # (정한 규칙이지 잰 것이 아니다. `Policy._wrap_mega` 와 같은 규칙).
    if opp_builds[oi].poke.get("isMega"):
        opp_plan = [("메가", opp_plan[0])]
    opp = opp_builds if len(opp_builds) > 1 else opp_builds[0]

    if turns is None:
        # auto_mega=False — '메가하고 쓴다' 와 '그냥 쓴다' 가 서로 다른
        # 후보이므로, 계획 턴에 Policy 가 멋대로 메가를 붙이면 안 된다.
        res = battle.run_once(dex, my_party, opp, _as_plan(action),
                              opp_plan, rng, my_moves=my_moves, state=state,
                              auto_mega=False)
        return _score(res)

    # 끊어 보기 — run_once 를 못 쓰므로 직접 돈다
    b = battle.Battle(dex, my_party, opp, rng=rng, **st)
    mine = battle.Policy(dex, my_party, opp, _as_plan(action),
                         moves=my_moves, lead=b.me_party.active.base,
                         auto_mega=False)
    theirs = battle.Policy(dex, opp, my_party, opp_plan,
                           lead=b.opp_party.active.base)
    for i in range(turns):
        if b.over:
            break
        b.step(mine.act(b.me_party, i, b), theirs.act(b.opp_party, i, b))
    # ! 전에는 여기서 이기면 곧바로 1.0 을 돌려줬다. 그러면 바로 아래
    #   _position_value 가 HP 로 갈라 주는 것을 건너뛰어서, 얕은 모드의
    #   점수만 '이기면 무조건 만점' 이 된다. 끝까지 본 점수와 자리가
    #   안 맞으면 둘을 나란히 볼 수 없다. 한 군데서만 재게 한다.
    return _position_value(b)


def best_action(dex, my_party, opp_pokes, my_moves=None, evidence=None,
                seconds=10.0, seed=1, opp_build=None, state=None):
    """이번 턴의 수를 고른다.

    opp_pokes 는 **한 마리든 파티든** 받는다. 파티를 주면 상대의
    벤치까지 넣고 판을 끝까지 돌린다.

    돌려주는 것 —
      rows     : [{action, name, score, n, dropped}] 점수 내림차순
      spent    : 실제로 쓴 초 / rollouts : 전체 판수
      shallow  : 끝까지 못 보고 끊었으면 True
      guessed  : 내 기술을 사용률로 짐작했으면 True

    ! **떨어뜨린 후보도 버리지 않고 같이 돌려준다.** 보고서에 "이건
      몇 판 보고 접었다" 가 남아야 나중에 지고 나서 되짚을 수 있다.
    """
    rng = random.Random(seed)
    party = battle.Party(dex, my_party, (state or {}).get("my_hp"))
    if (state or {}).get("my_active"):
        party.active_idx = state["my_active"]
    builds = _as_list(my_party)
    opp_pokes = _as_list(opp_pokes)
    actions, guessed = candidate_actions(dex, party, my_moves)
    # 계획이 끝난 뒤에도 이 기술들 안에서만 고르게 한다
    moves = [a[1] for a in actions if a[0] == "기술"]

    # 한 판이 얼마나 걸리는지 재 본다. **예산을 짐작으로 나누지 않는다** —
    # 파티 크기와 기술에 따라 2ms 에서 20ms 까지 벌어진다.
    #
    # ! **첫 판으로 재면 안 된다.** 처음 한 판은 캐시(rate_moves·도구 규칙·
    #   형태 모델)를 덥히느라 551ms 가 나왔다. 실제 한 판은 5ms 인데
    #   110배로 잰 것이다. 그 값으로 예산을 나누니 멀쩡한 판인데도
    #   "모자라다" 며 얕은 모드로 떨어졌다. 조용히 답이 나빠지는 종류다.
    #   그래서 **덥히는 판을 먼저 버리고** 그 뒤 몇 판을 재서 평균한다.
    warm_t0 = time.time()
    fastest = None
    for i in range(WARMUP_MAX):
        one = time.time()
        rollout(dex, builds, opp_pokes, actions[0], rng, evidence,
                opp_build, None, moves, state)
        took = time.time() - one
        fastest = took if fastest is None else min(fastest, took)
        if i >= 2 and took <= fastest * WARMUP_SETTLE:
            break
        if time.time() - warm_t0 > WARMUP_SECONDS:
            break
    # **평균이 아니라 제일 빠른 판으로 잰다.** 평균은 아직 덜 더워진
    # 판에 끌려간다. 우리가 알고 싶은 것은 '앞으로 한 판에 얼마나
    # 걸리느냐' 이므로 안정된 값이 맞다.
    times = []
    for _ in range(PROBE):
        one = time.time()
        rollout(dex, builds, opp_pokes, actions[0], rng, evidence,
                opp_build, None, moves, state)
        times.append(time.time() - one)
    per = max(1e-5, min(times))
    # ! **예산 시계는 재고 나서 켠다.** 전에는 재기 전에 켰다. 그러면
    #   덥히는 판 3 + 재는 판 5 = 8판이 예산을 먹어서, 예산이 작으면
    #   **한 판도 안 돌린 채 끝났다.** 그런데도 점수는 0.0 으로 나와서
    #   "측정해 보니 0점" 처럼 보였다. 조용히 틀어지는 종류다.
    t0 = time.time()

    shallow = len(actions) * MIN_ROLLOUTS * per > seconds
    turns = SHALLOW_TURNS if shallow else None

    rows = [{"action": a, "sum": 0.0, "n": 0, "dropped": False}
            for a in actions]
    live = list(rows)
    batch = MIN_ROLLOUTS
    out_of_time = False

    # **예산이 아무리 짧아도 후보마다 최소 한 판은 돌린다.** 한 판도 안
    # 돌린 후보의 0점은 '나쁘다' 가 아니라 '모른다' 인데, 구별이 안 된다.
    for row in rows:
        row["sum"] += rollout(dex, builds, opp_pokes, row["action"], rng,
                              evidence, opp_build, turns, moves, state)
        row["n"] += 1
    while live and not out_of_time:
        for row in live:
            for _ in range(batch):
                if time.time() - t0 >= seconds:
                    out_of_time = True
                    break
                row["sum"] += rollout(dex, builds, opp_pokes, row["action"],
                                      rng, evidence, opp_build, turns,
                                      moves, state)
                row["n"] += 1
            if out_of_time:
                break
        # **1등만 남기고 끝내지 않는다.** 남은 예산으로 둘을 더 돌려서
        # 1등과 2등의 차이를 좁혀야 한다. 전에는 후보가 하나가 되면
        # 바로 끝나서 12초 예산 중 3.8초만 쓰고 멈췄다.
        if out_of_time:
            break
        if len(live) <= 2:
            while time.time() - t0 < seconds:
                for row in live:
                    if time.time() - t0 >= seconds:
                        break
                    row["sum"] += rollout(dex, builds, opp_pokes,
                                          row["action"], rng, evidence,
                                          opp_build, turns, moves, state)
                    row["n"] += 1
            break
        live.sort(key=lambda r: -(r["sum"] / max(1, r["n"])))
        keep = max(1, int(round(len(live) * CUT)))
        for row in live[keep:]:
            row["dropped"] = True
        live = live[:keep]
        batch = int(batch * GROW)

    for row in rows:
        row["score"] = row["sum"] / row["n"] if row["n"] else 0.0
        row["name"] = action_name(dex, party, row["action"])
    rows.sort(key=lambda r: (-r["score"], r["dropped"]))
    thin = [r["name"] for r in rows if r["n"] < MIN_ROLLOUTS]
    return {"rows": rows, "spent": time.time() - t0,
            "rollouts": sum(r["n"] for r in rows),
            "shallow": shallow, "guessed": guessed,
            "perRollout": per,
            # 예산이 모자라 제대로 못 잰 후보들. 보고서가 이걸 말해야 한다.
            "thin": thin}


def action_name(dex, party, action):
    kind, what = action
    if kind == "교체":
        return "%s 로 교체" % party.members[what].name
    if kind == "메가":
        return "메가진화 + %s" % what["name"]
    return what["name"]


# ---------------------------------------------------------------------------
# 보고서
# ---------------------------------------------------------------------------
_MIN = MIN_ROLLOUTS


def _err(n):
    """승률의 표본오차(대략). 이기냐 지냐라 최대 분산이 0.25 다."""
    return 0.5 / (max(1, n) ** 0.5)



def report(dex, my_party, opp_pokes, got, evidence=None, state=None):
    L = []
    line = "=" * 78
    builds = _as_list(my_party)
    foes = _as_list(opp_pokes)
    st = state or {}
    ai = min(st.get("my_active", 0), len(builds) - 1)
    oi = min(st.get("opp_active", 0), len(foes) - 1)
    L.append(line)
    L.append("  7단계  이번 턴에 무엇을 둘까")
    L.append(line)
    L.append("  나   " + builds[ai].describe())
    rest = [b.name for i, b in enumerate(builds) if i != ai]
    if rest:
        L.append("       벤치 " + ", ".join(rest))
    L.append("  상대 %s — 몸과 기술은 매 판 사용률대로 새로 뽑는다"
             % foes[oi]["name"])
    foe_rest = [p["name"] for i, p in enumerate(foes) if i != oi]
    if foe_rest:
        L.append("       벤치 " + ", ".join(foe_rest))
    else:
        L.append("       ! 상대를 한 마리만 넣었다. 상대에게 벤치가 있으면")
        L.append("         '이놈을 잡는 수' 와 '판을 이기는 수' 가 달라진다.")
    for i, poke in enumerate(foes):
        ev = _evidence_for(evidence, i, poke)
        if ev is not None and not ev.empty:
            L.append("       본 것 (%s): %s" % (poke["name"], ev.describe()))
    L.append("")
    L.append("  %s%d판 · %.1f초 (한 판 %.1fms)"
             % ("**몇 턴에서 끊고 판세로 셈** · " if got["shallow"] else
                "끝까지 돌림 · ",
                got["rollouts"], got["spent"], got["perRollout"] * 1000))
    L.append("-" * 78)
    L.append("  %-22s %8s %8s %9s" % ("수", "승률", "판수", "오차"))
    for r in got["rows"]:
        err = _err(r["n"])
        mark = "   (일찍 접음 — 덜 믿을 것)" if r["dropped"] else ""
        L.append("  %-22s %7.1f%% %8d  ±%5.1f%%p%s"
                 % (r["name"], r["score"] * 100, r["n"], err * 100, mark))
    L.append("-" * 78)

    # **끝까지 본 것들 중에서 고른다.** 일찍 접은 후보는 판수가 적어
    # 점수가 우연히 높을 수 있다. 실제로 30판짜리가 970판짜리보다
    # 위에 오는 일이 있었다.
    full = [r for r in got["rows"] if not r["dropped"]] or got["rows"]
    top = max(full, key=lambda r: r["score"])
    L.append("  => %s  (승률 %.1f%% ±%.1f%%p, %d판)"
             % (top["name"], top["score"] * 100, _err(top["n"]) * 100,
                top["n"]))
    rest = [r for r in got["rows"] if r is not top]
    close = [r for r in rest
             if r["score"] + _err(r["n"]) >= top["score"] - _err(top["n"])]
    if close:
        L.append("  ! 오차 범위가 겹치는 수가 있다 — 확실하지 않다:")
        for r in close[:3]:
            L.append("      %s %.1f%% ±%.1f%%p (%d판)%s"
                     % (r["name"], r["score"] * 100, _err(r["n"]) * 100,
                        r["n"], " — 일찍 접어서 덜 믿을 것" if r["dropped"]
                        else ""))
        L.append("    --초 를 늘리면 판수가 늘어 오차가 줄어든다.")
    if got.get("thin"):
        L.append("  ! 예산이 모자라 %d판도 못 돌린 수가 있다: %s"
                 % (_MIN, ", ".join(got["thin"][:4])))
        L.append("    이 수들의 점수는 '나쁘다' 가 아니라 '아직 모른다' 다.")
    if got["guessed"]:
        L.append("  ! 내 기술을 **사용률 상위 4개로 짐작**했다. 실제 기술을")
        L.append("    주려면 --기술 지진,역린,칼춤,스텔스록 처럼 적는다.")
    if got["shallow"]:
        L.append("  ! 예산이 모자라 %d턴에서 끊고 **판세**로 점수를 매겼다."
                 % SHALLOW_TURNS)
        L.append("    판세 점수는 내가 정한 기준이지 잰 것이 아니다.")
        L.append("    --초 를 늘리면 끝까지 돌린다.")
    L.append(line)
    return "\n".join(L)


def main():
    paths.fix_console()
    argv = sys.argv[1:]
    seconds, seen, moves, rest = 10.0, [], None, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--초" and i + 1 < len(argv):
            seconds = float(argv[i + 1]); i += 2
        elif a == "--봤다" and i + 1 < len(argv):
            seen = [x.strip() for x in argv[i + 1].split(",") if x.strip()]
            i += 2
        elif a == "--기술" and i + 1 < len(argv):
            moves = [x.strip() for x in argv[i + 1].split(",") if x.strip()]
            i += 2
        else:
            rest.append(a); i += 1
    if len(rest) < 2:
        print(__doc__)
        return
    dex = calc.Dex()
    try:
        mine = [calc.popular_build(dex, dex.find_pokemon(n))[0]
                for n in rest[0].split(",") if n.strip()]
        opp = [dex.find_pokemon(n) for n in rest[1].split(",") if n.strip()]
    except LookupError as e:
        print("! %s" % e)
        return
    # --봤다 는 **나와 있는 놈** 것이다. 벤치에까지 붙이지 않는다.
    ev = scout.Evidence(seen_moves=seen) if seen else None
    got = best_action(dex, mine, opp, my_moves=moves, evidence=ev,
                      seconds=seconds)
    print(report(dex, mine, opp, got, ev))


if __name__ == "__main__":
    main()
