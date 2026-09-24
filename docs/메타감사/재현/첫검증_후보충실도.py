# -*- coding: utf-8 -*-
"""첫 검증 — '후보로 올린 수를 시뮬레이션이 실제로 두는가'.

    python3 docs/메타감사/재현/첫검증_후보충실도.py [저장소 경로]

탐색(7단계)의 점수는 "이번 턴에 이 수를 두면" 의 결과여야 한다. 그 전제가
깨지면 다른 모든 정확도는 의미가 없다. 그래서 세 가지를 센다.

  P1  1턴에 내 쪽이 둔 수 == 후보 수            (기대: 100%)
  P2  내 포켓몬이 쓴 기술 ⊆ 그 포켓몬에게 적어 준 기술 (기대: 위반 0)
  P3  서로 다른 후보가 서로 다른 판을 만든다        (기대: 기록 해시가 후보 수만큼)

나와 있는 놈을 0번(대조군)과 1번(시험군) 둘 다로 돈다.
씨앗은 고정이다. 로그 문장을 읽지 않고 Policy.act 가 돌려준 값을 직접 센다.
"""
import hashlib
import os
import random
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
sys.path.insert(0, ROOT)
import battle  # noqa: E402
import calc    # noqa: E402

dex = calc.Dex()
P = dex.find_pokemon
M = dex.find_move

# 이 저장소의 사고 사례 그대로 (CLAUDE.md §8) — 이름은 dex 로 확인된다.
GARCH = calc.Build(dex, P("한카리아스"), sp={"attack": 32, "speed": 32, "hp": 2})
CORV = calc.Build(dex, P("아머까오"), sp={"hp": 32, "defense": 32, "spDef": 2})
HIPPO = calc.Build(dex, P("하마돈"), sp={"hp": 32, "defense": 32})
PARTY = [GARCH, CORV]
DECLARED = {"한카리아스": ["지진", "역린", "스톤에지", "칼춤"],
            "아머까오": ["바디프레스", "철벽", "날개쉬기", "도발"]}
OPP_PLAN = [M("지진")]
SEEDS = range(20)

calls = []
_orig_act = battle.Policy.act


def _spy(self, party, turn_index, b=None):
    got = _orig_act(self, party, turn_index, b)
    calls.append((party is (b.me_party if b else None), turn_index,
                  party.active.name, got))
    return got


battle.Policy.act = _spy


def _move_name(action):
    if isinstance(action, tuple):
        if action[0] == "메가":
            return action[1]["name"]
        return None                       # 교체
    return action["name"]


total_bad = 0
for active in (0, 1):
    me = PARTY[active]
    my_moves = [M(x) for x in DECLARED[me.name]]
    cands = [m for m in my_moves] + [("교체", i) for i in range(len(PARTY))
                                      if i != active]
    p1_ok = p1_all = 0
    p2_bad = {}
    hashes = set()
    for cand in cands:
        plan = [cand] if not isinstance(cand, tuple) else [cand]
        sig = []
        for s in SEEDS:
            del calls[:]
            r = battle.run_once(dex, PARTY, HIPPO, plan, OPP_PLAN,
                                random.Random(s), log=True, my_moves=my_moves,
                                state={"my_active": active})
            sig.append("\n".join(r["log"] or []))
            mine = [c for c in calls if c[0]]
            if mine:
                p1_all += 1
                first = mine[0][3]
                p1_ok += (first == cand)
            for _me, _t, who, act in mine:
                mv = _move_name(act)
                if mv and mv not in DECLARED.get(who, []):
                    p2_bad[(who, mv)] = p2_bad.get((who, mv), 0) + 1
        hashes.add(hashlib.md5("".join(sig).encode("utf-8")).hexdigest())
    bad = (p1_ok != p1_all) + bool(p2_bad) + (len(hashes) != len(cands))
    total_bad += bad
    print("나와 있는 놈 = %d번 (%s)" % (active, me.name))
    print("  P1 1턴에 후보를 그대로 둠 : %d / %d" % (p1_ok, p1_all))
    print("  P2 적어 준 기술 밖 사용   : %s" % (p2_bad or "없음"))
    print("  P3 서로 다른 판의 수      : %d / 후보 %d" % (len(hashes), len(cands)))

print("\n결과: %s" % ("통과" if total_bad == 0 else "실패 (%d개 조건)" % total_bad))
sys.exit(1 if total_bad else 0)
