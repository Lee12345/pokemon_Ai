# -*- coding: utf-8 -*-
"""
계산기 검증 스크립트.

계산기를 고쳤으면 이걸 먼저 돌려서 깨진 데 없는지 확인한다.

    python tests.py
"""

import itertools
import json
import os
import math
import sys

import battle
import best
import calc
import paths
import combos
import forms
import scout
import pick as selection
import samples
import sensitivity

FAIL = []
PASSED = [0]     # 개수를 문서에 손으로 적지 않는다 — 환경마다 달라진다 (아래 참고)


def check(name, cond, detail=""):
    if cond:
        PASSED[0] += 1
        print("  [통과] %s" % name)
    else:
        print("  [실패] %s  %s" % (name, detail))
        FAIL.append(name)


def test_stat_formula():
    """실능 계산식이 기존 포켓몬 공식과 같은 결과를 내는가.

    기존 공식 (레벨50, 개체값31):
        HP   = (2*종족값 + 31 + 구노력치//4)//2 + 60
        그 외 = ((2*종족값 + 31 + 구노력치//4)//2 + 5) * 성격보정
    구 노력치 = 신 노력치 * 8 - 4
    """
    print("\n[1] 실능 계산식 — 기존 공식과 전수 대조")
    bad = 0
    total = 0
    for base in range(1, 256):
        for sp in range(0, 33):
            old_ev = 0 if sp == 0 else 8 * sp - 4
            t = (2 * base + 31 + old_ev // 4) // 2
            total += 1
            if calc.real_stat(base, sp, "hp") != t + 60:
                bad += 1
            for mod, nat in ((0.9, {"modifiers": {"attack": 0.9}}),
                             (1.0, None),
                             (1.1, {"modifiers": {"attack": 1.1}})):
                total += 1
                expect = int((t + 5) * mod)
                got = calc.real_stat(base, sp, "attack", nat)
                if expect != got:
                    bad += 1
    check("종족값1~255 x 노력치0~32 (%d회)" % total, bad == 0,
          "불일치 %d건" % bad)


def test_sp_budget():
    """노력치 총합 66, 개별 32 제약이 실제로 가능한 최대치인가."""
    print("\n[2] 노력치 예산")
    top = 0        # 이름을 best 로 두면 위에서 import 한 모듈을 가린다
    for used in range(1, 7):
        for total in range(1, 6 * 32 + 1):
            if total > 32 * used:
                break
            if 8 * total - 4 * used <= 510:
                top = max(top, total)
    check("구 노력치 510 제약에서 최대 66점", top == 66, "계산값 %d" % top)


def test_damage_vs_index(dex):
    """데미지 계산과 '결정력/내구력' 지수가 같은 결론을 내는가.

    서로 다른 방법이라 둘이 맞으면 양쪽 다 믿을 수 있다.
      결정력 = 공격 x 위력 x 배율,  내구력 = HP x 방어
      결정력 >= 내구력 / 0.374  이면 확정 1타
      결정력 <  내구력 / 0.44   이면 확정 2타 이상
    """
    print("\n[3] 데미지 계산 vs 결정력·내구력 지수")
    names = ["보만다", "하마돈", "한카리아스", "누리레느", "갑주무사",
             "루카리오", "드닐레이브", "타부자고", "고릴타", "브리두라스"]
    moves = ["지진", "섀도볼", "이판사판태클", "용성군", "아이언헤드", "화염방사"]
    pokes = []
    for n in names:
        try:
            pokes.append(dex.find_pokemon(n))
        except LookupError:
            pass

    mismatch = 0
    tested = 0
    for ap, dp in itertools.permutations(pokes, 2):
        a = calc.Build(dex, ap, sp={"attack": 32, "spAtk": 32})
        d = calc.Build(dex, dp, sp={"hp": 32, "defense": 32, "spDef": 32})
        for mn in moves:
            try:
                mv = dex.find_move(mn)
            except LookupError:
                continue
            res = calc.calc_damage(dex, a, d, mv)
            if "error" in res:
                continue
            tested += 1

            atk_key = "attack" if mv["category"] == "물리" else "spAtk"
            def_key = "defense" if mv["category"] == "물리" else "spDef"
            eff = dex.effectiveness(mv["type"], d.types)
            stab = calc.CONFIG["stab"] if mv["type"] in a.types else 1.0
            power_index = a.stat(atk_key) * mv["power"] * eff * stab
            bulk = d.stat("hp") * d.stat(def_key)

            idx_ohko = power_index >= bulk / 0.374
            idx_no_ohko = power_index < bulk / 0.44
            real_ohko = res["ohkoChance"] >= 1.0
            real_no_ohko = res["ohkoChance"] <= 0.0

            # 지수는 소수점 버림을 무시하는 근사라, 경계에서 1~2%는 어긋날 수 있다.
            if idx_ohko and not real_ohko and power_index > bulk / 0.374 * 1.03:
                mismatch += 1
            if idx_no_ohko and not real_no_ohko and power_index < bulk / 0.44 * 0.97:
                mismatch += 1

    check("%d개 조합에서 두 방법의 결론 일치" % tested, mismatch == 0,
          "어긋남 %d건" % mismatch)


def test_type_chart(dex):
    print("\n[4] 타입 상성표")
    check("타입 18개", len(dex.types) == 18, "실제 %d개" % len(dex.types))
    check("스텔라 없음 (있으면 본편 복사본)", "스텔라" not in dex.types)
    check("땅 → 전기 는 2배",
          dex.chart["땅"]["전기"] == 2, dex.chart["땅"].get("전기"))
    check("전기 → 땅 은 무효",
          dex.chart["전기"]["땅"] == 0, dex.chart["전기"].get("땅"))
    # 4배 약점이 제대로 곱해지는지
    eff = dex.effectiveness("바위", ["불꽃", "비행"])
    check("바위 → 불꽃/비행 은 4배", eff == 4, "계산값 %s" % eff)


def test_real_game(dex):
    """실제 게임 화면에서 읽은 능력치와 맞는지.

    이게 이 프로젝트에서 가장 중요한 검사다.
    다른 검사들은 '우리 식끼리 앞뒤가 맞는지'만 보지만,
    이건 게임이 실제로 보여준 숫자와 대조하는 유일한 기준점이다.

    출처: 2026-09-17 사용자가 게임 화면을 직접 확인해 알려준 값.
          한카리아스 / 성격 장난꾸러기 / 노력치 H32 B32 S2 (화면 표기 66/66)
    """
    print("\n[0] 실제 게임 화면과 대조  ← 가장 중요")
    b = calc.Build(dex, dex.find_pokemon("한카리아스"),
                   sp={"hp": 32, "defense": 32, "speed": 2},
                   nature=dex.find_nature("장난꾸러기"))
    screen = {"hp": 215, "attack": 150, "defense": 161,
              "spAtk": 90, "spDef": 105, "speed": 124}
    for k, want in screen.items():
        got = b.stat(k)
        check("한카리아스 %s = %d" % (calc.STAT_KO[k], want), got == want,
              "계산값 %d" % got)
    check("노력치 합계 66", b.sp_total() == 66, b.sp_total())


def test_known_cases(dex):
    """직접 손으로 확인할 수 있는 값들."""
    print("\n[5] 알려진 값 확인")
    # 리자몽: 종족값 특공109, CS배분(C32 S32), 조심(특공+10%)
    chari = dex.find_pokemon("리자몽")
    b = calc.Build(dex, chari, sp={"spAtk": 32, "speed": 32},
                   nature=dex.find_nature("조심"))
    check("리자몽 HP 153", b.stat("hp") == 153, b.stat("hp"))
    check("리자몽 특공 177", b.stat("spAtk") == 177, b.stat("spAtk"))
    check("리자몽 스피드 152", b.stat("speed") == 152, b.stat("speed"))

    # 랭크 변화
    b2 = calc.Build(dex, chari, ranks={"attack": 2})
    base_atk = calc.Build(dex, chari).stat("attack")
    check("공격 2랭크 상승 = 2배",
          b2.stat("attack") == int(base_atk * 2), b2.stat("attack"))

    # 무효 타입은 계산이 거부돼야 한다
    gengar = None
    for cand in ("타부자고", "팬텀"):
        try:
            gengar = dex.find_pokemon(cand)
            break
        except LookupError:
            continue
    if gengar and "고스트" in gengar["types"]:
        a = calc.Build(dex, chari)
        d = calc.Build(dex, gengar)
        res = calc.calc_damage(dex, a, d, dex.find_move("전광석화"))
        check("노말 기술은 고스트에게 무효", "error" in res, res.get("min"))


def test_abilities_items(dex):
    """특성·도구가 데미지에 제대로 반영되는가."""
    print("\n[6] 특성 · 도구")

    salamence = dex.find_pokemon("메가보만다")
    hippo = dex.find_pokemon("하마돈")
    a = calc.Build(dex, salamence, sp={"attack": 32}, ability="스카이스킨")
    d = calc.Build(dex, hippo, sp={"hp": 32, "defense": 32})
    with_skin = calc.calc_damage(dex, a, d, dex.find_move("이판사판태클"))
    a2 = calc.Build(dex, salamence, sp={"attack": 32}, ability="위협")
    without = calc.calc_damage(dex, a2, d, dex.find_move("이판사판태클"))
    check("스카이스킨이 노말을 비행으로 바꾼다",
          with_skin["moveType"] == "비행", with_skin["moveType"])
    check("스카이스킨 쪽 데미지가 더 크다",
          with_skin["max"] > without["max"],
          "%d vs %d" % (with_skin["max"], without["max"]))

    # 부유는 땅 기술을 아예 막는다
    garchomp_z = dex.find_pokemon("메가한카리아스Z")
    dz = calc.Build(dex, garchomp_z)
    check("메가한카리아스Z 의 특성이 부유", dz.ability == "부유", dz.ability)
    res = calc.calc_damage(dex, calc.Build(dex, hippo), dz, dex.find_move("지진"))
    check("부유면 땅 기술이 무효", "error" in res, res.get("min"))

    # 생명의구슬 1.3배
    base = calc.Build(dex, hippo, sp={"attack": 32})
    orb = calc.Build(dex, hippo, sp={"attack": 32}, item="생명의구슬")
    # 보만다는 비행타입이라 땅이 안 통한다 — 땅이 통하는 상대로 고른다
    tgt = calc.Build(dex, dex.find_pokemon("루카리오"), sp={"hp": 32})
    r1 = calc.calc_damage(dex, base, tgt, dex.find_move("지진"))
    r2 = calc.calc_damage(dex, orb, tgt, dex.find_move("지진"))
    check("생명의구슬이 데미지를 올린다", r2["max"] > r1["max"],
          "%d -> %d" % (r1["max"], r2["max"]))

    # 도구 설명문에서 자동으로 뽑아낸 것들
    eff = dex.item_effects
    check("검은안경 = 악타입 1.2배",
          eff.get("검은안경", {}).get("type") == "악", eff.get("검은안경"))
    check("하반열매 = 드래곤 반감 열매",
          eff.get("하반열매", {}).get("kind") == "resist_berry", eff.get("하반열매"))
    check("구애하치마키는 챔피언스에 없다", "구애하치마키" not in eff)


def test_mega_stone(dex):
    """메가스톤이 어느 폼으로 이어지는지 제대로 읽어냈는가.

    사용률은 기본 폼 기준이라 메가는 '도구 채용률' 로만 나타난다.
    이걸 놓치면 메가스톤을 든 기본 폼이라는, 실제로는 없는 몸으로 계산하게 된다.
    """
    print("\n[7] 메가스톤 -> 폼 연결")
    megas = [p for p in dex.pokemon if p.get("isMega")]
    check("메가 폼 %d개가 전부 도구와 이어짐" % len(megas),
          len(dex.mega_by_item) == len(megas),
          "도구 %d개 / 폼 %d개" % (len(dex.mega_by_item), len(megas)))
    # 메가가 둘인 포켓몬은 설명문 괄호로 갈라야 한다
    check("리자몽나이트X -> 메가리자몽X",
          dex.mega_by_item.get("리자몽나이트X", {}).get("formName") == "메가리자몽X",
          dex.mega_by_item.get("리자몽나이트X"))
    check("한카리아스나이트Z -> 메가한카리아스Z",
          dex.mega_by_item.get("한카리아스나이트Z", {}).get("formName")
          == "메가한카리아스Z",
          dex.mega_by_item.get("한카리아스나이트Z"))
    # 1위 도구가 메가스톤이면 그 폼으로 바뀌어야 한다
    b, _ = calc.popular_build(dex, dex.find_pokemon("보만다"))
    check("보만다는 메가로 계산된다 (보만다나이트 97.7%)",
          b.poke.get("isMega"), b.name)


def test_speed(dex):
    """4-A 의 핵심 — 누가 먼저 때리는가."""
    print("\n[8] 스피드 · 선공 판정")
    items = best.speed_item_effects(dex)
    check("구애스카프 = 스피드 1.5배", items.get("구애스카프") == 1.5,
          items.get("구애스카프"))
    check("검은철구 = 스피드 0.5배", items.get("검은철구") == 0.5,
          items.get("검은철구"))

    chomp = dex.find_pokemon("한카리아스")
    jolly = dex.find_nature("명랑")
    bare = calc.Build(dex, chomp, sp={"speed": 32}, nature=jolly)
    base = best.effective_speed(dex, bare)[0]
    scarf = calc.Build(dex, chomp, sp={"speed": 32}, nature=jolly,
                       item="구애스카프")
    para = calc.Build(dex, chomp, sp={"speed": 32}, nature=jolly, status="마비")
    check("스카프를 들면 1.5배", best.effective_speed(dex, scarf)[0]
          == int(base * 1.5), best.effective_speed(dex, scarf)[0])
    check("마비면 절반", best.effective_speed(dex, para)[0]
          == int(base * calc.CONFIG["paralysis_speed"]),
          best.effective_speed(dex, para)[0])

    slow = calc.Build(dex, dex.find_pokemon("하마돈"))
    quick_move = dex.find_move("지진")
    o = best.turn_order(dex, bare, quick_move, slow, quick_move)
    check("빠른 쪽이 먼저", o["first"] == "나", o)
    o = best.turn_order(dex, bare, quick_move, slow, quick_move, trick_room=True)
    check("트릭룸이면 느린 쪽이 먼저", o["first"] == "상대", o)
    o = best.turn_order(dex, bare, quick_move, slow, dex.find_move("전광석화"))
    check("우선도가 스피드를 이긴다", o["first"] == "상대", o)
    o = best.turn_order(dex, bare, quick_move, bare, quick_move)
    check("스피드가 같으면 동속", o["first"] == "동시", o)

    # 짓궂은마음은 변화기 우선도를 올린다
    prank = calc.Build(dex, chomp, ability="짓궂은마음")
    p, _ = best.move_priority(prank, dex.find_move("칼춤"))
    check("짓궂은마음: 변화기 우선도 +1", p == 1, p)
    p, _ = best.move_priority(prank, dex.find_move("지진"))
    check("짓궂은마음: 공격기는 그대로", p == 0, p)


def test_race():
    """선공/후공에 따라 몇 타 차이가 나야 이기는가.

    선공이면 같은 타수라도 이기고, 후공이면 한 번 더 빨라야 이긴다.
    여기가 틀리면 4-A 의 결론이 통째로 뒤집힌다.
    """
    print("\n[9] 대면 승패 계산")

    def res(lo, hi):
        return {"hitsMin": lo, "hitsMax": hi}

    check("선공 2타 vs 상대 2타 → 이김",
          best.race(res(2, 2), res(2, 2), "나") == best.WIN)
    check("후공 2타 vs 상대 2타 → 짐",
          best.race(res(2, 2), res(2, 2), "상대") == best.LOSE)
    check("후공 2타 vs 상대 3타 → 이김",
          best.race(res(2, 2), res(3, 3), "상대") == best.WIN)
    check("선공 2~3타 vs 상대 2타 → 난수",
          best.race(res(2, 3), res(2, 2), "나") == best.LUCK)
    check("동속 2타 vs 상대 2타 → 난수",
          best.race(res(2, 2), res(2, 2), "동시") == best.LUCK)
    check("상대가 나를 못 잡으면 이김",
          best.race(res(5, 5), None, "상대") == best.WIN)


def test_move_caveats(dex):
    """'위력 그대로' 가 아닌 기술을 알아보는가."""
    print("\n[10] 기술 특수 규칙 잡아내기")
    cases = [("솔라빔", "2턴"), ("바늘미사일", "연속"), ("나이트헤드", "고정"),
             ("이판사판태클", "자신도 받는다"), ("자이로볼", "위력"),
             ("역린", "혼란")]
    for name, word in cases:
        got = best.move_caveats(dex.find_move(name))
        check("%s → 경고에 '%s'" % (name, word),
              any(word in g for g in got), got)
    check("화염방사는 특수 규칙 없음",
          best.move_caveats(dex.find_move("화염방사")) == [],
          best.move_caveats(dex.find_move("화염방사")))


def test_analyze(dex):
    """4-A 전체가 끝까지 도는가 + 결론이 상식과 맞는가."""
    print("\n[11] 4-A 전체 돌려보기")
    me, _ = calc.popular_build(dex, dex.find_pokemon("메가보만다"))
    opp, _ = calc.popular_build(dex, dex.find_pokemon("하마돈"))
    a = best.analyze(dex, me, opp)
    check("추천 기술이 나온다", a["pick"] is not None)
    check("메가보만다가 하마돈보다 빠르다", a["speed"]["first"] == "나",
          a["speed"])
    # 하마돈의 지진(97.7%)은 비행타입에게 안 통해야 한다
    quake = [r for r in a["oppRows"] if r["move"]["name"] == "지진"]
    check("하마돈의 지진은 메가보만다에게 무효",
          quake and quake[0]["kind"] == "none",
          quake[0]["kind"] if quake else "없음")
    check("결론까지 글로 나온다", "대면 결론" in best.report(dex, a))

    # 사용률이 없는 포켓몬도 배울 수 있는 기술로 돌아가야 한다
    odd = [p for p in dex.pokemon
           if not (dex.usage.get(p["key"])
                   or dex.usage.get("%04d-00" % p["dexNo"]))]
    if odd:
        mv = best.candidate_moves(dex, odd[0])
        check("사용률 없으면 배우는 기술로 대신함 (%s)"
              % (odd[0]["formName"] or odd[0]["name"]), len(mv) > 0, len(mv))


def test_move_effects(dex):
    """변화기 효과를 설명문에서 제대로 읽는가.

    여기가 틀리면 조용히 틀린다. 실제로 두 번 물렸다.
      · '올린' 은 '올리' 로 시작하지 않는다 (한글은 '린'과 '리'가 다른 글자)
        -> 부호가 뒤집혀 용의춤이 공격 -1 이 됐다
      · 받침에 따라 조사가 '공격을' / '방어를' 로 갈린다
        -> '을' 을 안 받아서 칼춤·나쁜음모가 통째로 안 읽혔다
    """
    print("\n[12] 변화기 효과 읽기")

    def eff(name):
        return [(e.get("stat"), e.get("step"))
                for e in battle.move_effects(dex.find_move(name))
                if e["kind"] == "rank"]

    check("용의춤 = 공격+1 스피드+1",
          eff("용의춤") == [("attack", 1), ("speed", 1)], eff("용의춤"))
    check("칼춤 = 공격+2 ('공격을' 의 조사)",
          eff("칼춤") == [("attack", 2)], eff("칼춤"))
    check("나쁜음모 = 특공+2",
          eff("나쁜음모") == [("spAtk", 2)], eff("나쁜음모"))
    check("저주 = 스피드-1 공격+1 방어+1 (한 문장에 올리고+떨어뜨리고)",
          eff("저주") == [("speed", -1), ("attack", 1), ("defense", 1)],
          eff("저주"))
    check("암석봉인 = 상대 스피드-1",
          [e["who"] for e in battle.move_effects(dex.find_move("암석봉인"))
           if e["kind"] == "rank"] == ["foe"])

    kinds = lambda n: {e["kind"] for e in battle.move_effects(dex.find_move(n))}
    check("HP회복 = 회복", "heal" in kinds("HP회복"))
    check("하품 = 상태 이상", "status" in kinds("하품"))
    check("킹실드 = 막기", "protect" in kinds("킹실드"))
    check("날려버리기 = 강제 교체", "phaze" in kinds("날려버리기"))
    check("스텔스록 = 압정", "hazard" in kinds("스텔스록"))
    check("모래바람 = 날씨", "weather" in kinds("모래바람"))

    # 상위 20마리가 실제로 쓰는 변화기는 거의 다 읽혀야 한다
    used = set()
    for p in dex.pokemon:
        u = dex.usage.get(p["key"])
        if not u or u.get("rank", 999) > 20:
            continue
        for m in u["moves"]:
            if m["category"] == "변화" and m["pct"] >= 10:
                mv = dex.move_by_id(m["id"])
                if mv:
                    used.add(mv["name"])
    bad = [n for n in used
           if battle.move_effects(dex.find_move(n))[0].get("kind") == "unknown"]
    check("상위20이 쓰는 변화기 %d개를 다 읽음" % len(used), not bad, bad)


def test_battle_rules(dex):
    """턴 루프의 규칙들. 손으로 확인할 수 있는 것만 골랐다."""
    print("\n[13] 턴 루프 규칙")
    import random

    chomp = dex.find_pokemon("한카리아스")
    hippo = dex.find_pokemon("하마돈")

    # 랭크는 위아래로 6이 한계
    side = battle.Side(dex, calc.Build(dex, chomp))
    for _ in range(5):
        side.bump("attack", 2)
    check("랭크 상한 +6", side.ranks["attack"] == 6, side.ranks["attack"])
    check("6을 넘겨 올리면 움직인 칸수가 0", side.bump("attack", 2) == 0)

    # 용의춤을 쓰면 공격 실능이 정확히 랭크표대로 오른다
    b0 = calc.Build(dex, chomp, sp={"attack": 32})
    b1 = calc.Build(dex, chomp, sp={"attack": 32}, ranks={"attack": 1})
    check("공격 1랭크 = 1.5배",
          b1.stat("attack") == int(b0.stat("attack") * 1.5), b1.stat("attack"))

    # 기합의띠 — HP가 꽉 차 있으면 즉사기를 맞아도 1 남는다
    s = battle.Side(dex, calc.Build(dex, chomp, item="기합의띠"))
    s.damage(99999)
    check("기합의띠로 HP 1 남김", s.hp == 1, s.hp)
    s.damage(99999)
    check("기합의띠는 한 번만", s.hp == 0, s.hp)

    # 자뭉열매 — 반피 이하로 떨어지면 최대 HP의 1/4 회복
    bt = battle.Battle(dex, calc.Build(dex, chomp),
                       calc.Build(dex, hippo, item="자뭉열매"),
                       rng=random.Random(1))
    opp = bt.opp
    opp.hp = opp.max_hp // 2
    bt._pinch_berry(opp)
    check("자뭉열매가 최대 HP의 1/4 회복",
          opp.hp == opp.max_hp // 2 + int(opp.max_hp / 4.0), opp.hp)
    check("자뭉열매는 한 번만", opp.item_used)

    # 하마돈은 나오기만 해도 모래바람을 깐다 (모래날림 99.8%)
    mine, _ = calc.popular_build(dex, dex.find_pokemon("메가보만다"))
    theirs, _ = calc.popular_build(dex, hippo)
    bt = battle.Battle(dex, mine, theirs, rng=random.Random(1))
    check("하마돈 등장만으로 모래바람", bt.field.weather == "모래바람",
          bt.field.weather)


def test_dead_items(dex):
    """**계산에 안 들어가는 도구를 조용히 넘기지 않는가.**

    아머까오(울퉁불퉁멧 66%)로 한카리아스를 400판 상대해 놓고
    "아머까오가 진다" 고 보고한 적이 있다. 도구 셋이 다 미구현이라
    맨몸으로 싸우고 있었는데 결과만 봐서는 알 수가 없었다.

    그 뒤 도구를 채웠다. 그래서 여기서 지키는 것이 둘로 늘었다 —
      ① 채운 도구가 **정말로 도는가** (설명문만 읽고 안 쓰면 같은 일이 난다)
      ② 아직 못 채운 도구는 **여전히 큰 소리로 말하는가**
    """
    print("\n[36] 도구가 정말로 도는가 / 안 도는 것은 말하는가")
    import random

    kao = calc.popular_build(dex, dex.find_pokemon("아머까오"))[0]
    check("아머까오 1위 도구는 울퉁불퉁멧이다 (%s)" % kao.item,
          kao.item == "울퉁불퉁멧", kao.item)

    # ① 접촉기를 맞으면 반동이 실제로 들어가는가
    chomp = calc.Build(dex, dex.find_pokemon("한카리아스"),
                       sp={"attack": 32, "speed": 32},
                       nature=dex.find_nature("명랑"), item="기합의띠")
    r = battle.run_once(dex, kao, chomp,
                        [dex.find_move("철벽")], [dex.find_move("불꽃엄니")],
                        random.Random(1), log=True)
    chip = [x for x in r["log"] if "울퉁불퉁멧" in x]
    check("접촉기를 맞으면 울퉁불퉁멧이 돈다 (%d번)" % len(chip),
          bool(chip), r["log"][:3])
    check("그 도구에는 이제 경고가 안 뜬다",
          not [w for w in r["warnings"] if "울퉁불퉁멧" in w],
          r["warnings"][:2])

    # ② 아직 못 채운 도구는 여전히 말해야 한다
    left = sorted(set(k for v in battle.item_behaviors(dex).values()
                      for k in (e["kind"] for e in v))
                  - battle.APPLIED_ITEM_KINDS)
    check("아직 못 채운 효과가 무엇인지 코드가 알고 있다 (%s)"
          % ", ".join(left), bool(left), left)
    still = None
    for nm, efs in battle.item_behaviors(dex).items():
        if any(e["kind"] in left for e in efs):
            still = nm
            break
    if still:
        thin = calc.Build(dex, dex.find_pokemon("한카리아스"),
                          sp={"attack": 32}, item=still)
        r2 = battle.run_once(dex, thin, kao, [dex.find_move("지진")],
                             [dex.find_move("바디프레스")], random.Random(1))
        check("못 채운 도구(%s)는 아직 경고가 뜬다" % still,
              bool([w for w in r2["warnings"] if still in w]),
              r2["warnings"][:2])

    # ③ 설명문을 못 읽은 도구가 남아 있나
    unread = [it["name"] for it in dex.items
              if it["name"] not in battle.item_behaviors(dex)
              and not dex.item_effects.get(it["name"])
              and not dex.mega_by_item.get(it["name"])
              and it["name"] not in best.speed_item_effects(dex)]
    check("설명문을 못 읽은 도구가 없다 (%d개)" % len(unread),
          not unread, unread[:6])


def test_item_behaviors(dex):
    """도구 설명문을 규칙으로 읽은 결과가 맞는지 하나하나 확인한다.

    정규식은 **조용히 어긋나기 제일 쉬운 자리**다. 순서만 바뀌어도
    넓은 규칙이 좁은 규칙을 잡아먹는다. 그래서 대표 도구를 못 박는다.
    """
    print("\n[37] 도구 설명문 읽기")
    b = battle.item_behaviors(dex)

    def one(name, kind, **want):
        ef = battle.item_effect(dex, name, kind)
        ok = ef is not None and all(
            abs(ef[k] - v) < 1e-9 if isinstance(v, float) else ef[k] == v
            for k, v in want.items())
        check("%s -> %s %s" % (name, kind,
                               " ".join("%s=%s" % kv for kv in want.items())),
              ok, ef)

    one("기합의띠", "endure", chance=1.0, full_hp=True)
    one("기합의머리띠", "endure", chance=0.1, full_hp=False)
    one("먹다남은음식", "heal_turn", frac=1.0 / 16)
    one("자뭉열매", "heal_pinch", at=0.5, frac=0.25)
    one("오랭열매", "heal_pinch", at=0.5, flat=10)
    one("울퉁불퉁멧", "contact_chip", frac=1.0 / 6)
    one("풍선", "float")
    one("리샘열매", "cure", statuses=None)
    one("유루열매", "cure", statuses=["잠듦"])
    one("복슝열매", "cure", statuses=["독", "맹독"])
    one("하양허브", "restore_ranks")
    one("빛의점토", "extend", what="screen", turns=3)
    one("축축한바위", "extend", what="weather", weather="비", turns=3)
    one("뜨거운바위", "extend", what="weather", weather="쾌청", turns=3)
    one("그라운드코트", "extend", what="terrain", turns=3)
    one("사이코시드", "seed", terrain="사이코필드", stat="특수방어", step=1)
    one("그래스시드", "seed", terrain="그래스필드", stat="방어", step=1)
    one("노말주얼", "jewel", type="노말", mult=1.3)
    one("광각렌즈", "accuracy", mult=1.1)
    one("반짝가루", "evasion", mult=0.9)
    one("초점렌즈", "crit_stage", step=1)
    one("대파", "crit_stage", step=2)
    one("레드카드", "force_switch_foe")
    one("탈출버튼", "self_switch")
    one("왕의징표석", "flinch", chance=0.1)
    one("조개껍질방울", "drain_hit", frac=1.0 / 8)

    # 넓은 규칙이 좁은 규칙을 안 잡아먹었는가
    check("'상태를 회복한다' 규칙이 하양허브를 안 삼켰다",
          battle.item_effect(dex, "하양허브", "cure") is None,
          b.get("하양허브"))
    check("'상태를 회복한다' 규칙이 빛의점토를 안 삼켰다",
          battle.item_effect(dex, "빛의점토", "cure") is None,
          b.get("빛의점토"))
    check("급소업 규칙이 초점렌즈와 대파를 안 섞었다",
          not battle.item_effect(dex, "초점렌즈", "crit_stage").get("who")
          and battle.item_effect(dex, "대파", "crit_stage").get("who"),
          (b.get("초점렌즈"), b.get("대파")))


def test_screens_and_weather(dex):
    """스크린 · 날씨 강화 · 대타 · 희망사항.

    전부 **게임 데이터에 숫자가 없어서** 본편 값을 가정한 것들이다.
    그래서 값이 맞는지가 아니라 **실제로 도는지**를 지킨다.
    가정값이라는 경고가 같이 뜨는지도 본다 — 조용히 넘어가면 안 된다.
    """
    print("\n[38] 스크린 · 날씨 · 대타 · 희망사항")
    import random

    kao = calc.popular_build(dex, dex.find_pokemon("아머까오"))[0]
    chomp = calc.Build(dex, dex.find_pokemon("한카리아스"),
                       sp={"attack": 32, "speed": 32},
                       nature=dex.find_nature("명랑"))
    fang = dex.find_move("불꽃엄니")

    # -- 스크린이 물리/특수를 갈라서 깎는가 --------------------------------
    check("리플렉터는 물리만 깎는다",
          battle.SCREEN_KIND["리플렉터"] == "물리")
    check("빛의장막은 특수만 깎는다",
          battle.SCREEN_KIND["빛의장막"] == "특수")
    check("오로라베일은 둘 다 깎는다",
          battle.SCREEN_KIND["오로라베일"] is None)
    check("순풍은 같은 자리에 깔려도 데미지를 안 깎는다",
          battle.SCREEN_KIND["순풍"] == "-")

    party = battle.Party(dex, kao)
    party.screens["리플렉터"] = 5
    check("리플렉터를 깔면 물리가 반감된다 (%.2f)"
          % party.screen_mult("물리"),
          abs(party.screen_mult("물리")
              - calc.CONFIG["screen_reduce"]) < 1e-9)
    check("특수는 그대로다 (%.2f)" % party.screen_mult("특수"),
          abs(party.screen_mult("특수") - 1.0) < 1e-9)
    party.screens = {"순풍": 4}
    check("순풍만 깔렸을 때 데미지는 그대로다",
          abs(party.screen_mult("물리") - 1.0) < 1e-9)
    check("대신 스피드가 두 배다 (%.1f)" % party.speed_mult(),
          abs(party.speed_mult() - 2.0) < 1e-9)

    # -- 실제 대전에서 데미지가 줄어드는가 ---------------------------------
    # **대조군을 고르는 데 한 번 미끄러졌다.** 처음엔 철벽을 대조군으로
    # 썼는데, 철벽은 방어를 올리므로 그쪽 데미지도 같이 줄어 32 대 31 이
    # 나왔다. 효과가 있는지 없는지 구별이 안 되는 비교였다.
    # 빛의장막은 리플렉터와 **모든 것이 같고 물리를 안 깎는 것만 다르다.**
    plain = battle.run_once(dex, kao, chomp, [dex.find_move("빛의장막")],
                            [fang], random.Random(1), log=True)
    screen = battle.run_once(dex, kao, chomp, [dex.find_move("리플렉터")],
                             [fang], random.Random(1), log=True)

    def nth_hit(log, n):
        """n번째로 맞은 데미지. **첫 타가 아니라 둘째 타를 봐야 한다** —
        한카리아스가 더 빨라서 첫 타는 리플렉터를 깔기 전에 들어온다.
        (이걸 모르고 첫 타로 짰다가 54 -> 54 로 테스트가 깨졌다.)"""
        got = [int(r.split("에게")[1].split("(")[0]) for r in log
               if "불꽃엄니 →" in r and "아머까오 에게" in r]
        return got[n] if len(got) > n else None
    a, b = nth_hit(plain["log"], 1), nth_hit(screen["log"], 1)
    check("리플렉터를 깐 뒤 물리 데미지가 준다 (%s -> %s)" % (a, b),
          a is not None and b is not None and b < a, (a, b))
    check("스크린이 가정값이라고 경고한다",
          any("스크린" in w for w in screen["warnings"]),
          screen["warnings"][:2])

    # -- 날씨가 타입 배율을 주는가 -----------------------------------------
    check("비는 물을 올리고 불꽃을 깎는다",
          battle.WEATHER_BOOST["비"] == "물"
          and battle.WEATHER_WEAKEN["비"] == "불꽃")
    check("쾌청은 불꽃을 올리고 물을 깎는다",
          battle.WEATHER_BOOST["쾌청"] == "불꽃"
          and battle.WEATHER_WEAKEN["쾌청"] == "물")
    b2 = battle.Battle(dex, kao, chomp, rng=random.Random(1))
    base = b2._power_scale(fang, chomp)
    b2.field.set("비")
    wet = b2._power_scale(fang, chomp)
    b2.field.set("쾌청")
    dry = b2._power_scale(fang, chomp)
    check("비가 오면 불꽃 기술이 약해진다 (%.2f -> %.2f)" % (base, wet),
          wet < base, (base, wet))
    check("쾌청이면 불꽃 기술이 세진다 (%.2f -> %.2f)" % (base, dry),
          dry > base, (base, dry))
    check("날씨 배율이 가정값이라고 경고한다",
          any("미확인" in w and ("비" in w or "쾌청" in w)
              for w in b2.warnings), b2.warnings[:3])

    # -- 대타출동 ----------------------------------------------------------
    r = battle.run_once(dex, kao, chomp,
                        [dex.find_move("대타출동"), dex.find_move("브레이브버드")],
                        [fang], random.Random(2), log=True)
    check("대타가 데미지를 대신 받는다",
          any("대타에게" in x for x in r["log"]), r["log"][:4])
    check("대타는 부서진다", any("부서졌다" in x for x in r["log"]),
          r["log"][:5])

    # -- 희망사항은 **다음 턴에** 온다 --------------------------------------
    r2 = battle.run_once(dex, kao, chomp,
                         [dex.find_move("희망사항"), dex.find_move("브레이브버드")],
                         [fang], random.Random(2), log=True)
    laid = [i for i, x in enumerate(r2["log"]) if "회복이 온다" in x]
    came = [i for i, x in enumerate(r2["log"]) if "희망사항으로" in x]
    check("희망사항이 걸리고 나중에 도착한다",
          bool(laid) and bool(came) and came[0] > laid[0], (laid, came))

    # -- 아픔나누기 · 흑안개 · 버티기 ---------------------------------------
    for nm, kind in (("아픔나누기", "pain_split"), ("흑안개", "haze"),
                     ("버티기", "endure_turn"), ("대타출동", "substitute"),
                     ("희망사항", "wish")):
        efs = [e["kind"] for e in battle.move_effects(dex.find_move(nm))]
        check("%s 를 '%s' 로 읽는다" % (nm, kind), kind in efs, efs)
    check("빛의장막은 스크린으로 읽는다",
          any(e["kind"] == "screen" and e["turns"] == 5
              for e in battle.move_effects(dex.find_move("빛의장막"))))


def test_more_status_moves(dex):
    """길동무 · 멸망의노래 · 배턴터치 · 트릭 · 회생의기도 · 치유소원 등."""
    print("\n[39] 나머지 변화기")
    import random

    B = lambda n, **kw: calc.Build(dex, dex.find_pokemon(n), **kw)
    gar = B("한카리아스", sp={"attack": 32, "speed": 32},
            nature=dex.find_nature("명랑"))
    quake = dex.find_move("지진")

    # -- 읽기 --------------------------------------------------------------
    for nm, kind in (("길동무", "destiny"), ("멸망의노래", "perish"),
                     ("배턴터치", "baton"), ("트릭", "trick"),
                     ("회생의기도", "revive"), ("치유소원", "heal_wish"),
                     ("안개제거", "defog"), ("기충전", "crit_up"),
                     ("물붓기", "retype"), ("배북", "belly")):
        efs = [e["kind"] for e in battle.move_effects(dex.find_move(nm))]
        check("%s 를 '%s' 로 읽는다" % (nm, kind), kind in efs, efs)

    # -- 길동무는 **다음 턴까지 간다** ---------------------------------------
    # 쓴 턴에 이미 맞은 뒤라면 정작 죽는 것은 다음 턴이다.
    # 턴 끝에 지우도록 짰다가 한 번도 안 터진 적이 있다.
    r = battle.run_once(dex, B("따라큐", sp={"attack": 32, "speed": 32}),
                        gar, [dex.find_move("길동무")], [quake],
                        random.Random(3), log=True)
    check("길동무로 때린 쪽도 같이 쓰러진다",
          any("같이 쓰러졌다" in x for x in r["log"]), r["log"][-3:])
    check("그 판은 동시에 쓰러진 것으로 끝난다",
          r["result"] == "동시에 쓰러짐", r["result"])

    # -- 멸망의노래는 양쪽을 센다 --------------------------------------------
    r2 = battle.run_once(dex, B("블래키", sp={"hp": 32, "spDef": 32}), gar,
                         [dex.find_move("멸망의노래")] + [dex.find_move("달빛")] * 3,
                         [quake], random.Random(3), log=True)
    died = [x for x in r2["log"] if "멸망의노래로 쓰러졌다" in x]
    check("멸망의노래가 양쪽을 데려간다 (%d마리)" % len(died),
          len(died) == 2, died)

    # -- 배턴터치는 랭크를 넘긴다 (이게 이 기술의 전부다) --------------------
    r3 = battle.run_once(
        dex, [B("블래키", sp={"hp": 32, "spDef": 32}),
              B("아머까오", sp={"hp": 32, "defense": 32})], gar,
        [dex.find_move("벌크업"), dex.find_move("벌크업"),
         dex.find_move("배턴터치")], [quake], random.Random(3), log=True)
    check("배턴터치로 능력 변화가 넘어간다",
          any("이어받았다" in x for x in r3["log"]), r3["log"][-3:])

    # -- 기충전이 급소 확률을 실제로 올리는가 --------------------------------
    b = battle.Battle(dex, B("한카리아스", sp={"attack": 32}), gar,
                      rng=random.Random(1))
    before = calc.crit_chance(quake, b.me.crit_stage)
    b._use_status(b.me, b.opp, dex.find_move("기충전"))
    after = calc.crit_chance(quake, b.me.crit_stage)
    check("기충전을 쓰면 급소 확률이 오른다 (%.3f -> %.3f)" % (before, after),
          after > before, (before, after))

    # -- 트릭은 도구를 바꾼다 ------------------------------------------------
    b2 = battle.Battle(dex, B("타부자고", sp={"speed": 32}, item="구애스카프"),
                       B("아머까오", sp={"hp": 32}, item="울퉁불퉁멧"),
                       rng=random.Random(1))
    b2._use_status(b2.me, b2.opp, dex.find_move("트릭"))
    check("트릭으로 도구가 서로 바뀐다 (%s / %s)" % (b2.me.item, b2.opp.item),
          b2.me.item == "울퉁불퉁멧" and b2.opp.item == "구애스카프",
          (b2.me.item, b2.opp.item))

    # -- 물붓기는 타입을 바꾼다 ----------------------------------------------
    b3 = battle.Battle(dex, B("누리레느", sp={"spAtk": 32}), gar,
                       rng=random.Random(1))
    b3._use_status(b3.me, b3.opp, dex.find_move("물붓기"))
    check("물붓기로 상대가 물타입이 된다 (%s)" % b3.opp.types,
          b3.opp.types == ["물"], b3.opp.types)
    # ★ **바뀐 타입이 데미지 계산까지 닿는가.** 한 번 여기서 미끄러졌다 —
    #   로그에는 "물타입이 됐다" 고 찍히는데 데미지는 원래 타입으로
    #   계산되고 있었다. 로그만 보면 알 수가 없다.
    b4 = battle.Battle(dex, B("누리레느", sp={"spAtk": 32}),
                       B("한카리아스", sp={"hp": 32}), rng=random.Random(1))
    ball = dex.find_move("에너지볼")
    was = calc.calc_damage(dex, b4.me.as_build(), b4.opp.as_build(),
                           ball)["rolls"][-1]
    b4._use_status(b4.me, b4.opp, dex.find_move("물붓기"))
    now = calc.calc_damage(dex, b4.me.as_build(), b4.opp.as_build(),
                           ball)["rolls"][-1]
    check("바뀐 타입이 데미지까지 닿는다 (풀 기술 %d -> %d, %.1f배)"
          % (was, now, now / float(was)), abs(now / float(was) - 2.0) < 0.05,
          (was, now))


def test_cache_honesty(dex):
    """**캐시가 남의 답을 돌려주지 않는가.**

    속도를 위해 `best.rate_moves` 를 외워 둔다. 열쇠에 하나라도 빠지면
    조건이 다른데 같은 답을 돌려주게 되고, 그건 터지지 않고 조용히
    틀린 수를 고르게 만든다 — 이 저장소가 고장나는 바로 그 방식이다.

    그래서 `best.CHECK_CACHE = True` 모드를 만들어 뒀다. 캐시를 믿지
    않고 매번 다시 계산해서 저장된 답과 대조하고, 다르면 터진다.
    여기서 실제로 그 모드로 돌려 본다.
    """
    print("\n[40] 캐시가 정직한가")
    import random

    was = best.CHECK_CACHE
    best.CHECK_CACHE = True
    best._RATE_CACHE.clear()
    try:
        mp = [calc.popular_build(dex, dex.find_pokemon(n))[0]
              for n in ("한카리아스", "아머까오", "누리레느")]
        op = [calc.popular_build(dex, dex.find_pokemon(n))[0]
              for n in ("하마돈", "갸라도스", "킬가르도")]
        plans, _ = battle.build_plans(dex, mp, op)
        oplan, _, _ = battle.opponent_plan(dex, op, mp)
        rng = random.Random(1)
        blew = None
        try:
            for _ in range(120):
                battle.run_once(dex, mp, op, plans[0], oplan, rng)
        except AssertionError as e:
            blew = str(e)
        check("3대3 120판을 대조 모드로 돌려도 캐시가 안 어긋난다",
              blew is None, blew)
        check("그동안 실제로 여러 조건을 봤다 (열쇠 %d개)"
              % len(best._RATE_CACHE), len(best._RATE_CACHE) > 500,
              len(best._RATE_CACHE))
    finally:
        best.CHECK_CACHE = was

    # 열쇠가 상태를 실제로 가르는가 — 랭크만 바꿔도 다른 답이 나와야 한다
    a = calc.popular_build(dex, dex.find_pokemon("한카리아스"))[0]
    # ! 아머까오(비행)를 상대로 지진을 쓰면 무효라 'expected' 자체가 없다.
    #   한 번 그렇게 짰다가 KeyError 로 터졌다. 실제로 통하는 짝을 쓴다.
    d = calc.popular_build(dex, dex.find_pokemon("하마돈"))[0]
    mv = [(dex.find_move("지진"), None)]
    base = best.rate_moves(dex, a, d, mv)[0]["expected"]
    a2 = calc.Build(dex, a.poke, sp=a.sp, nature=a.nature,
                    ranks={"attack": 2}, item=a.item, ability=a.ability)
    up = best.rate_moves(dex, a2, d, mv)[0]["expected"]
    check("공격 랭크를 올리면 다른 답이 나온다 (%.1f -> %.1f)" % (base, up),
          up > base, (base, up))
    d2 = calc.Build(dex, d.poke, sp=d.sp, nature=d.nature,
                    ranks={"defense": 2}, item=d.item, ability=d.ability)
    down = best.rate_moves(dex, a, d2, mv)[0]["expected"]
    check("상대 방어 랭크를 올리면 데미지가 준다 (%.1f -> %.1f)" % (base, down),
          down < base, (base, down))
    a3 = calc.Build(dex, a.poke, sp=a.sp, nature=a.nature, item=a.item,
                    ability=a.ability, status="화상")
    burn = best.rate_moves(dex, a3, d, mv)[0]["expected"]
    check("화상이면 물리 데미지가 준다 (%.1f -> %.1f)" % (base, burn),
          burn < base, (base, burn))


def test_search(dex):
    """7단계 — **답을 아는 상황에서 그 답을 찾는가.**

    승률 숫자는 그럴듯하게 나오기 쉽다. 그래서 "이건 무조건 이 수여야
    한다" 는 자리를 만들어 놓고 거기서만 확인한다. 실제로 이 방식으로
    두 가지 큰 결함을 잡았다 (아래 각 검사의 주석 참고).
    """
    print("\n[41] 7단계 탐색")
    import search

    P = lambda n: calc.popular_build(dex, dex.find_pokemon(n))[0]

    def pick(party, opp, moves, secs=3.0):
        got = search.best_action(dex, [P(x) for x in party],
                                 dex.find_pokemon(opp), my_moves=moves,
                                 seconds=secs)
        full = [r for r in got["rows"] if not r["dropped"]] or got["rows"]
        return max(full, key=lambda r: r["score"]), got

    # ① 때릴 수단이 아예 없으면 빼야 한다 -----------------------------------
    # ! 이 검사가 **두 개의 결함**을 잡아냈다.
    #   (가) Policy 가 계획이 끝난 뒤 사용률 기술을 몰래 꺼내 썼다.
    #       땅 기술만 든 한카리아스가 2턴째부터 화염방사를 쓰고 있었다.
    #   (나) 점수가 '이기면 1.0' 이라, 이놈을 공짜로 잃어도 벤치가
    #       이기면 같은 점수였다. 그래서 뺐어야 할 자리에서 안 뺐다.
    # ! 벤치(누리레느)가 어차피 이기는 자리라 점수가 다닥다닥 붙는다.
    #   그래서 **벤치를 빼고 1대1 로** 재서 답을 또렷하게 만든다 —
    #   때릴 수단이 없으면 이 판은 못 이긴다.
    # ! 2026-09-22 벤치를 누리레느 → **브리두라스** 로 바꿨다 (사용자 승인).
    #   공격기 추가 효과를 붙이자 누리레느 판이 '뻔한 답' 이 아니게 됐다 —
    #   아머까오(더 빠름)의 아이언헤드가 누리레느(페어리, 2배)를 20% 로 풀죽이고,
    #   바디프레스가 방어로 제대로 세졌다. 교체 0.849 → 0.791 로 1등을 내줬다.
    #   원래도 0.849 대 0.834 로 아슬아슬했다. 느슨하게 만들지 않고 **답이 다시
    #   뻔한 판** 을 찾았다: 브리두라스(전기·드래곤 — 비행·강철 반감, 전기 2배).
    #   씨앗 1~5 전부 교체 1등, 2등과 0.10~0.12 차이. 그래서 차이도 같이 본다.
    #   기술에서 대지의힘은 뺐다 — 지진과 같이 들 이유가 없는 구성이었다.
    top, got = pick(["한카리아스", "브리두라스"], "아머까오",
                    ["지진", "칼춤", "스텔스록"], 5.0)
    ground_only = [r for r in got["rows"] if "교체" not in r["name"]]
    check("때릴 수단이 없으면 공격수들이 전부 바닥이다 (최고 %.2f)"
          % max(r["score"] for r in ground_only),
          max(r["score"] for r in ground_only) < 0.95,
          [(r["name"], round(r["score"], 3)) for r in ground_only[:3]])
    check("때릴 수단이 없으면 교체를 고른다 (%s)" % top["name"],
          "교체" in top["name"], [(r["name"], round(r["score"], 3))
                                 for r in got["rows"][:3]])
    gap = top["score"] - max(r["score"] for r in ground_only)
    check("교체가 **넉넉하게** 1등이다 (2등과 %.3f 차이 — 아슬아슬하면 뻔한 판이 아니다)"
          % gap, gap >= 0.05, gap)

    # ② 통하는 기술이 있으면 그걸 고른다 -------------------------------------
    top2, got2 = pick(["한카리아스", "누리레느"], "아머까오",
                      ["지진", "역린", "화염방사", "칼춤"], 4.0)
    # ! '메가진화 + 화염방사' 도 정답이다 — 메가가 수가 된 뒤로 후보가
    #   기술마다 둘씩이다. 재고 싶은 것은 **불꽃을 고르는가** 지
    #   메가를 하느냐가 아니다.
    check("강철 상대에 불꽃을 고른다 (%s)" % top2["name"],
          "화염방사" in top2["name"],
          [(r["name"], round(r["score"], 3)) for r in got2["rows"][:3]])

    # ③ 기술 제한이 정말로 걸리는가 (①의 (가) 재발 방지) --------------------
    import random
    me, opp = P("한카리아스"), P("아머까오")
    def win_rate(moves, n=80):
        rng = random.Random(5)
        w = 0
        for _ in range(n):
            r = battle.run_once(dex, me, opp, [dex.find_move("칼춤")],
                                [dex.find_move("바디프레스")], rng,
                                my_moves=moves)
            w += (r["result"] == "이김")
        return w * 100.0 / n
    ground = [dex.find_move(x) for x in ("지진", "칼춤", "스텔스록")]
    mixed = [dex.find_move(x) for x in ("지진", "화염방사", "칼춤", "스텔스록")]
    a, b = win_rate(ground), win_rate(mixed)
    check("땅 기술만 주면 비행 상대에게 못 이긴다 (%.0f%%)" % a, a == 0.0, a)
    check("불꽃을 끼워 주면 이긴다 (%.0f%%)" % b, b > 90.0, b)

    # ④ 점수가 '이기는 정도' 를 가르는가 (①의 (나) 재발 방지) ---------------
    clean = {"result": "이김", "myPartyHpPct": 100.0}
    barely = {"result": "이김", "myPartyHpPct": 5.0}
    tie = {"result": "동시에 쓰러짐", "myPartyHpPct": 100.0}
    lose = {"result": "짐", "myPartyHpPct": 0.0}
    check("깨끗이 이긴 판이 간신히 이긴 판보다 높다 (%.2f > %.2f)"
          % (search._score(clean), search._score(barely)),
          search._score(clean) > search._score(barely))
    check("간신히 이긴 판도 비긴 판보다는 높다",
          search._score(barely) > search._score(tie))
    check("비긴 판이 진 판보다 높다",
          search._score(tie) > search._score(lose))

    # ⑤ 보고서가 나오고, 확실하지 않으면 그렇다고 말하는가 -------------------
    text = search.report(dex, [P("한카리아스"), P("누리레느")],
                         dex.find_pokemon("아머까오"), got2)
    check("보고서가 나온다", "7단계" in text and "승률" in text)
    check("판수와 오차를 같이 보여 준다", "오차" in text and "±" in text)
    check("일찍 접은 후보도 버리지 않고 보여 준다",
          any(r["dropped"] for r in got2["rows"]),
          [r["name"] for r in got2["rows"] if r["dropped"]])

    # ⑥ **나와 있는 놈이 1번이 아닐 때 계획이 정말로 들어가는가** -----------
    # ! 여기서 큰 것을 하나 잡았다 (2026-09-19). `Policy` 가 계획의
    #   주인을 무조건 파티 1번으로 봤다. 그래서 내가 2번을 내보낸 채로
    #   물으면 `act` 의 첫 줄에서 걸러져 **계획이 통째로 버려졌다.**
    #   "이 수를 두면 어떻게 되나" 를 묻는데 그 수를 안 두고 답한 것이다.
    #   철벽·브레이브버드·날개쉬기 세 계획이 같은 씨앗에서 결과까지
    #   똑같이 나왔다 (이김 / 파티HP 81.04% / 6턴). 그런데 점수는
    #   91.9~93.1 로 그럴듯하게 벌어져 있어서 눈으로는 절대 못 잡는다.
    trio = [P("한카리아스"), P("아머까오"), P("누리레느")]
    foe = P("하마돈")
    kao_moves = [dex.find_move(x)
                 for x in ("철벽", "바디프레스", "날개쉬기", "브레이브버드")]
    outs = []
    for mv in ("철벽", "브레이브버드", "날개쉬기"):
        rng = random.Random(99)
        r = battle.run_once(dex, trio, foe, [dex.find_move(mv)],
                            [dex.find_move("지진")], rng,
                            my_moves=kao_moves,
                            state={"my_hp": [100.0] * 3, "my_active": 1})
        outs.append((r["result"], round(r["myPartyHpPct"], 2), r["turns"]))
    check("2번이 나와 있어도 계획이 실제로 들어간다 (계획마다 결과가 다르다)",
          len(set(outs)) > 1, outs)

    # 계획의 주인을 Battle 에게 물어서 정하는가 (손으로 [0] 이라고 적으면
    # state 로 '2번이 나와 있다' 를 줬을 때 또 어긋난다)
    b = battle.Battle(dex, trio, foe, rng=random.Random(1),
                      my_hp=[100.0] * 3, my_active=1)
    pol = battle.Policy(dex, trio, foe, [dex.find_move("철벽")],
                        moves=kao_moves, lead=b.me_party.active.base)
    check("계획의 주인이 '나와 있는 놈' 이다 (%s)" % pol.lead.name,
          pol.lead is trio[1], pol.lead.name)
    act = pol.act(b.me_party, 0, b)
    check("1턴에 계획대로 둔다 (%s)"
          % battle.action_name(act, trio),
          getattr(act, "get", lambda k: None)("name") == "철벽",
          battle.action_name(act, trio))

    # 기술을 이름으로 줘도 받는가 (전에는 여기서 터졌다)
    blew = None
    try:
        battle.run_once(dex, trio, foe, [dex.find_move("철벽")],
                        [dex.find_move("지진")], random.Random(3),
                        my_moves=["철벽", "바디프레스", "날개쉬기",
                                  "브레이브버드"],
                        state={"my_hp": [100.0] * 3, "my_active": 1})
    except Exception as e:
        blew = e
    check("기술을 이름으로 줘도 안 터진다", blew is None, blew)

    # ⑦ **상대도 파티다.** 상대 벤치가 정말로 계산에 드는가 ------------------
    # ! 사용자가 되물어서 잡혔다: "왜 내 파티는 6인이 아니며 상대는
    #   1인이지?" (2026-09-18). 상대를 한 마리만 넣으면 '이놈을 잡는 수'
    #   를 '판을 이기는 수' 라고 답하게 된다. 재 보니 '누리레느 로 교체'
    #   가 상대 1마리일 때 94.6점(2등)이었는데 상대 3마리를 넣자
    #   30.5점(꼴찌)이 됐다. 64%p 차이다.
    one = search.rollout(dex, trio, [dex.find_pokemon("하마돈")],
                         ("기술", dex.find_move("지진")), random.Random(7),
                         opp_build=[P("하마돈")])
    three = search.rollout(
        dex, trio, [dex.find_pokemon(n)
                    for n in ("하마돈", "타부자고", "킬가르도")],
        ("기술", dex.find_move("지진")), random.Random(7),
        opp_build=[P("하마돈"), P("타부자고"), P("킬가르도")])
    check("상대 벤치를 넣으면 판이 달라진다 (1마리 %.2f / 3마리 %.2f)"
          % (one, three), one != three, (one, three))

    b3 = battle.Battle(dex, trio, [P("하마돈"), P("타부자고")],
                       rng=random.Random(1), opp_hp=[100.0, 40.0],
                       opp_active=1)
    check("상대가 파티로 들어간다 (%d마리)" % len(b3.opp_party.members),
          len(b3.opp_party.members) == 2, len(b3.opp_party.members))
    check("상대의 '나와 있는 놈' 도 받는다 (%s)" % b3.opp.name,
          b3.opp.base is not b3.opp_party.members[0].base, b3.opp.name)
    check("상대 벤치의 HP 도 그대로 들어간다",
          abs(b3.opp_party.members[1].hp
              / float(b3.opp_party.members[1].max_hp) - 0.40) < 0.02,
          b3.opp_party.members[1].hp)

    # 본 것이 **그놈에게만** 붙는가 -----------------------------------------
    ev_one = scout.Evidence(seen_moves=["지진"])
    foes = [dex.find_pokemon(n) for n in ("하마돈", "누리레느")]
    check("관찰을 하나만 주면 나와 있는 놈에게만 붙는다",
          search._evidence_for(ev_one, 0, foes[0]) is ev_one
          and search._evidence_for(ev_one, 1, foes[1]) is None)
    ev_map = {"누리레느": ev_one}
    check("{이름: 관찰} 로 주면 그 이름에만 붙는다",
          search._evidence_for(ev_map, 0, foes[0]) is None
          and search._evidence_for(ev_map, 1, foes[1]) is ev_one)

    # 상대가 한 마리뿐이면 보고서가 그렇다고 말하는가
    got4 = search.best_action(dex, trio, [dex.find_pokemon("하마돈")],
                              my_moves=kao_moves, seconds=2.0,
                              state={"my_hp": [100.0] * 3, "my_active": 1,
                                     "opp_hp": [100.0]})
    text4 = search.report(dex, trio, [dex.find_pokemon("하마돈")], got4,
                          state={"my_active": 1})
    check("상대를 한 마리만 넣으면 보고서가 경고한다",
          "한 마리만" in text4, text4)
    check("보고서가 '나와 있는 놈' 을 맨 위에 쓴다 (%s)" % trio[1].name,
          trio[1].name in text4.splitlines()[3], text4.splitlines()[3])


def test_live(dex):
    """실전 도구 — **넣은 값이 계산까지 닿는가.**

    여기서 세 가지를 잡았다. 셋 다 화면에는 멀쩡해 보였다.
    """
    print("\n[42] 실전 도구 (live.py)")
    import random
    import live
    import search

    P = lambda n: calc.popular_build(dex, dex.find_pokemon(n))[0]

    # ① 남은 HP 가 대전에 실제로 들어가는가 ---------------------------------
    # 전에는 Side 가 늘 만피에서 시작했다. 3턴만 지나도 양쪽 다 깎여
    # 있는데, 그러면 "지금 이 상황" 이 아니라 "처음이었다면" 을 잰다.
    kao, gar = P("아머까오"), P("한카리아스")
    hits = []
    for pct in (100, 30):
        r = battle.run_once(dex, kao, gar, [dex.find_move("철벽")],
                            [dex.find_move("화염방사")], random.Random(1),
                            log=True, state={"my_hp": [pct]})
        first = [x for x in r["log"] if "아머까오 에게" in x][0]
        hits.append(int(first.split("HP ")[1].split("/")[0]))
    check("내 남은 HP 가 대전에 들어간다 (%d -> %d)" % tuple(hits),
          hits[1] < hits[0], hits)

    turns = []
    for pct in (100, 10):
        r = battle.run_once(dex, kao, gar, [dex.find_move("바디프레스")],
                            [dex.find_move("지진")], random.Random(1),
                            state={"opp_hp": [pct]})
        turns.append(r["turns"])
    check("상대 남은 HP 도 들어간다 (%d턴 -> %d턴)" % tuple(turns),
          turns[1] < turns[0], turns)

    # ★ 내 파티를 **내가 적은 대로** 쓰는가 ---------------------------------
    # ! 처음에는 이름과 기술만 받고 배분·성격·도구를 사다리 1위 것으로
    #   멋대로 씌웠다. 상대는 모르니 사용률로 짐작하는 게 맞지만
    #   **내 파티는 내가 안다.** 같은 아머까오라도 HB 장난꾸러기는
    #   방어 172, HD 신중은 125 — 38% 차이다.
    got = live.parse_evs("A32S32")[0]
    check("노력치를 읽는다 (A32S32)",
          got == {"attack": 32, "speed": 32}, got)
    got = live.parse_evs("H16A22B2S26")[0]
    check("여러 칸도 읽는다 (H16A22B2S26)",
          got == {"hp": 16, "attack": 22, "defense": 2, "speed": 26}, got)
    bad, why = live.parse_evs("A33")
    check("한 칸 32 초과를 잡는다 (%s)" % why, bad is None and why)
    bad2, why2 = live.parse_evs("H32B32S32")
    check("합계 66 초과를 잡는다 (%s)" % why2, bad2 is None and why2)

    # ! 특성을 받게 만든 뒤로는 **특성까지 적어야** 채운 것이 없다.
    #   한카리아스는 특성이 둘(사나운기세·모래숨기)이라 안 적으면 채운다.
    line = "한카리아스 지진,역린 | 명랑 A32S32 까칠한피부 기합의띠"
    build, moves, filled, bad3 = live.read_line(dex, line)
    check("파티 한 줄을 통째로 읽는다", bad3 is None, bad3)
    check("적은 성격이 그대로 들어간다 (%s)"
          % (build.nature and build.nature["name"]),
          build.nature and build.nature["name"] == "명랑")
    check("적은 노력치가 그대로 들어간다",
          build.sp.get("attack") == 32 and build.sp.get("speed") == 32,
          build.sp)
    check("적은 도구가 그대로 들어간다 (%s)" % build.item,
          build.item == "기합의띠")
    check("다 적었으면 사용률로 채운 것이 없다", not filled, filled)

    # 안 적으면 채우되 **반드시 드러낸다**
    b2, _m2, filled2, _bad = live.read_line(dex, "한카리아스 지진,역린")
    check("안 적으면 사용률로 채운다", bool(filled2), filled2)
    check("무엇을 채웠는지 화면에 드러낸다",
          "사용률로 채웠습니다" in live.describe_member(b2, ["지진"], filled2),
          live.describe_member(b2, ["지진"], filled2))

    # 적은 대로 쓰면 능력치가 실제로 달라지는가 (이게 핵심이다)
    hb, _m, _f, _b = live.read_line(
        dex, "아머까오 바디프레스 | 장난꾸러기 H32B32 울퉁불퉁멧")
    hd, _m, _f, _b = live.read_line(
        dex, "아머까오 바디프레스 | 신중 H32D32 먹다남은음식")
    check("배분을 바꾸면 능력치가 실제로 달라진다 (방어 %d vs %d)"
          % (hb.stat("defense"), hd.stat("defense")),
          hb.stat("defense") > hd.stat("defense") + 20,
          (hb.stat("defense"), hd.stat("defense")))
    check("특방도 반대로 달라진다 (%d vs %d)"
          % (hb.stat("spDef"), hd.stat("spDef")),
          hd.stat("spDef") > hb.stat("spDef") + 20,
          (hb.stat("spDef"), hd.stat("spDef")))

    # 특성도 적은 대로 쓰는가 — 안 적으면 조용히 첫 번째 것이 된다
    sand, _m, _f, _b = live.read_line(dex, "하마돈 지진 | 무사태평 모래날림")
    power, _m, _f2, _b = live.read_line(dex, "하마돈 지진 | 무사태평 모래의힘")
    check("적은 특성이 그대로 들어간다 (%s / %s)"
          % (sand.ability, power.ability),
          sand.ability == "모래날림" and power.ability == "모래의힘",
          (sand.ability, power.ability))
    none_, _m, filled3, _b = live.read_line(dex, "하마돈 지진 | 무사태평")
    check("특성을 안 적으면 채웠다고 말한다", "특성" in (filled3 or []),
          filled3)
    bad4 = live.read_line(dex, "하마돈 지진 | 무사태평 심록")[3]
    check("그 포켓몬이 못 가지는 특성은 거부한다 (%s)" % bad4, bool(bad4))

    # 게임 화면처럼 보여 주는 카드 — **테두리가 맞아야 읽을 수 있다**
    card = live.stat_card(sand, ["지진", "하품", "게으름피우기", "스텔스록"])
    widths = set(best._w(x) for x in card)
    check("카드의 모든 줄이 같은 너비다 (%s)" % sorted(widths),
          len(widths) == 1, card[:3])
    body = "\n".join(card)
    check("카드에 능력치·보정·특성·도구가 다 보인다",
          all(x in body for x in ("HP", "능력 포인트", "무사태평",
                                  "모래날림", "도구")), card)

    # 게임 화면과 실제로 맞는가 (2026-09-18 사용자가 보내 준 하마돈)
    real = live.read_line(
        dex, "하마돈 지진,하품,게으름피우기,스텔스록 | 무사태평 H32B22D12")[0]
    screen = {"hp": 215, "attack": 132, "defense": 176,
              "spAtk": 88, "spDef": 104, "speed": 60}
    off = [(k, real.stat(k), v) for k, v in screen.items()
           if real.stat(k) != v]
    check("게임 화면의 하마돈과 6/6 일치한다", not off, off)

    # 메가스톤을 적으면 메가로 싸운다
    mg, _m, _f, _b = live.read_line(
        dex, "한카리아스 지진 | 명랑 A32S32 한카리아스나이트Z")
    check("메가스톤을 적으면 메가로 계산한다 (%s)" % mg.name,
          "메가" in mg.name, mg.name)

    # ② live 가 그 값을 탐색까지 넘기는가 ------------------------------------
    # ! 한 번 여기서 빠뜨렸다. 화면에는 '상대 55%' 라고 찍히는데
    #   state() 가 opp_hp 를 안 넘겨서 계산은 만피로 하고 있었다.
    party = [(P("아머까오"), ["바디프레스", "철벽", "날개쉬기", "브레이브버드"], []),
             (P("누리레느"), ["문포스", "냉동빔", "아쿠아제트", "하품"], [])]
    f = live.Fight(dex, party)
    f.opp_add(dex.find_pokemon("한카리아스"))
    f.opp_hp = 40.0
    f.my_hp[0] = 70.0
    f.my_active = 0
    st = f.state()
    check("live 가 내 HP 를 넘긴다", st.get("my_hp") == [70.0, 100.0], st)
    check("live 가 상대 HP 도 넘긴다", st.get("opp_hp") == [40.0], st)
    check("live 가 나와 있는 놈도 넘긴다", "my_active" in st, st)

    # ③ 본 것이 쌓이는가 ----------------------------------------------------
    f.seen_of().add(("기술", "지진"))
    f.seen_of().add(("도구", "자뭉열매"))
    ev = f.evidence()
    one = ev.get("한카리아스") if ev else None
    check("본 기술이 증거로 넘어간다 (%s)" % (one.seen_moves if one else None),
          one is not None and "지진" in one.seen_moves, ev)

    # ④ 짧게 쳐도 찾는가 / 애매하면 되묻는가 ---------------------------------
    got, note = live.find_poke(dex, "아머까")
    check("앞글자로 찾는다 (아머까 -> %s)" % (got and got["name"]),
          got is not None and got["name"] == "아머까오", note)
    got2, note2 = live.find_poke(dex, "한카")
    check("애매하지 않으면 기본 폼을 고른다 (한카 -> %s)"
          % (got2 and got2["name"]),
          got2 is not None and got2["name"] == "한카리아스", note2)
    bad, why = live.find_poke(dex, "없는이름임")
    check("없는 이름은 None 을 준다", bad is None, why)
    kind, name = live.find_move_or_item(dex, "지진")
    check("기술을 기술로 읽는다", (kind, name) == ("기술", "지진"), (kind, name))
    kind2, name2 = live.find_move_or_item(dex, "자뭉열매")
    check("도구를 도구로 읽는다", (kind2, name2) == ("도구", "자뭉열매"),
          (kind2, name2))

    # ⑤ 예산을 재는 판이 예산을 먹지 않는가 ---------------------------------
    # ! 전에는 덥히는 판이 예산을 먹어서, 예산이 작으면 **한 판도 안
    #   돌린 채** 끝났다. 그런데 점수는 0.0 으로 나와서 '측정해 보니
    #   0점' 처럼 보였다.
    got3 = search.best_action(dex, [row[0] for row in party],
                              dex.find_pokemon("한카리아스"),
                              my_moves=party[0][1], seconds=1.0,
                              state={"my_hp": [70, 100], "opp_hp": [100]})
    check("예산이 짧아도 후보마다 최소 한 판은 돈다",
          all(r["n"] >= 1 for r in got3["rows"]),
          [(r["name"], r["n"]) for r in got3["rows"]])
    check("제대로 못 잰 후보를 보고서가 말한다",
          "thin" in got3, list(got3.keys()))

    # ★ **반만 붙은 도구는 반드시 소리를 낸다** -----------------------------
    # 풍선이 `APPLIED_ITEM_KINDS` 에 들어 있어서 경고 한 줄 없이
    # 땅 기술을 그냥 맞고 있었다. 미구현보다 나쁘다 — 붙었다고
    # 말하면서 틀린 답을 준다. 사용자가 되물어서 잡혔다 (2026-09-20).
    tab = calc.popular_build(dex, dex.find_pokemon("타부자고"))[0]
    check("타부자고의 사용률 1위 도구가 풍선이다 (%s)" % tab.item,
          tab.item == "풍선", tab.item)
    check("풍선을 설명문에서 알아본다 (찍어 넣지 않는다)",
          "풍선" in calc.floating_items(dex), calc.floating_items(dex))

    gar = P("한카리아스")
    b_on = battle.Battle(dex, gar, tab, rng=random.Random(2))
    h = b_on.opp.hp
    b_on.step(dex.find_move("지진"), dex.find_move("맹독"))
    blocked = h - b_on.opp.hp
    check("풍선을 들면 땅 기술이 아예 안 들어간다 (%d 데미지)" % blocked,
          blocked == 0, blocked)

    # 터뜨린 뒤에는 통해야 한다 — 무효가 영구히 남으면 그것도 틀린 것이다
    h = b_on.opp.hp
    b_on.step(dex.find_move("화염방사"), dex.find_move("맹독"))
    popped = h - b_on.opp.hp
    check("다른 기술로 때리면 풍선이 터진다 (%d 데미지)" % popped,
          popped > 0 and b_on.opp.item_used, (popped, b_on.opp.item_used))
    h = b_on.opp.hp
    b_on.step(dex.find_move("지진"), dex.find_move("맹독"))
    after = h - b_on.opp.hp
    check("터진 뒤에는 땅 기술이 통한다 (%d 데미지)" % after, after > 0, after)

    # 승률이 실제로 뒤집히는가 — 이게 이 결함의 크기다
    def _tab_win(item):
        op = calc.popular_build(dex, dex.find_pokemon("타부자고"))[0]
        op.item = item
        rng = random.Random(5)
        w = 0
        for _ in range(60):
            r = battle.run_once(dex, gar, op, [dex.find_move("지진")],
                                [dex.find_move("리프스톰")], rng)
            w += (r["result"] == "이김")
        return w * 100.0 / 60
    w_on, w_off = _tab_win("풍선"), _tab_win(None)
    check("풍선 하나로 답이 뒤집힌다 (풍선 %.0f%% / 없음 %.0f%%)"
          % (w_on, w_off), w_on < 20 and w_off > 80, (w_on, w_off))

    # 스텔스록은 풍선을 뚫는다 (설명문에 압정뿌리기·독압정·끈적끈적네트만 적혀 있다)
    b_h = battle.Battle(dex, [P("한카리아스"), tab], P("하마돈"),
                        rng=random.Random(1))
    b_h.me_party.hazards["스텔스록"] = 1
    b_h.me_party.hazards["압정뿌리기"] = 1
    h0 = b_h.me_party.members[1].hp
    b_h.switch_in(b_h.me_party, 1)
    took = h0 - b_h.me_party.members[1].hp
    check("풍선은 압정은 막아도 스텔스록은 못 막는다 (%d 깎임)" % took,
          took > 0, took)

    # 반만 붙은 것을 말해 주는 장치 자체는 살아 있어야 한다 (지금은 비어 있다)
    check("PARTIAL 은 APPLIED 안에 있는 것만 담는다",
          set(battle.PARTIAL_ITEM_KINDS) <= battle.APPLIED_ITEM_KINDS,
          sorted(set(battle.PARTIAL_ITEM_KINDS)
                 - battle.APPLIED_ITEM_KINDS))
    saved = dict(battle.PARTIAL_ITEM_KINDS)
    try:
        battle.PARTIAL_ITEM_KINDS["float"] = ("도는 것", "안 도는 것")
        said = " ".join(battle.Battle(dex, gar, tab,
                                      rng=random.Random(1)).warnings)
        check("반만 붙은 것이 생기면 승률 옆에 말해 준다",
              "반만 들어간다" in said and "안 도는 것" in said, said)
    finally:
        battle.PARTIAL_ITEM_KINDS.clear()
        battle.PARTIAL_ITEM_KINDS.update(saved)

    # ⑥ **상대 파티** — 창과 글자판이 같이 쓰는 규칙 -------------------------
    # ! 사용자가 되물어서 생긴 부분이다: "왜 내 파티는 6인이 아니며
    #   상대는 1인이지?" (2026-09-18). 챔피언스는 6마리를 데려가서
    #   3마리를 낸다. 상대도 마찬가지다.
    #
    # ! 이 계산은 **창 안에 두면 안 된다.** 이 컨테이너에는 tkinter 도
    #   화면도 없어서 창은 여기서 한 줄도 못 돌린다. 그래서 창이 값만
    #   모아 주고 규칙은 live.py 에 두고 여기서 시험한다.
    ha, ta, kil = (dex.find_pokemon("하마돈"), dex.find_pokemon("타부자고"),
                   dex.find_pokemon("킬가르도"))
    rows = [(ha, 100.0), (ta, 40.0), (kil, 0.0)]
    pokes, st, why = live.turn_state([100.0, 60.0], 1, rows, 1)
    check("쓰러진 상대(HP 0)는 계산에서 빠진다 (%s)"
          % ", ".join(p["name"] for p in pokes),
          [p["name"] for p in pokes] == ["하마돈", "타부자고"], pokes)
    check("상대 HP 가 그대로 따라간다", st["opp_hp"] == [100.0, 40.0],
          st["opp_hp"])
    check("나와 있는 상대 번호가 맞다 (타부자고 = 1)",
          st["opp_active"] == 1, st["opp_active"])
    # ★ **번호가 밀리는 자리.** 1번이 쓰러져 있으면 3번이 나와 있어도
    #   넘기는 목록에서는 1번이 된다. 이걸 안 맞추면 상대가 엉뚱한 놈인
    #   채로 계산이 돌고, 승률은 멀쩡하게 나온다.
    rows2 = [(ha, 0.0), (ta, 100.0), (kil, 55.0)]
    pokes2, st2, _ = live.turn_state([100.0], 0, rows2, 2)
    check("앞이 쓰러져 밀려도 나와 있는 놈을 제대로 가리킨다 (%s)"
          % pokes2[st2["opp_active"]]["name"],
          pokes2[st2["opp_active"]]["name"] == "킬가르도",
          (st2["opp_active"], [p["name"] for p in pokes2]))
    check("다 쓰러지면 왜 안 되는지 말해 준다",
          live.turn_state([100.0], 0, [(ha, 0.0)], 0)[2] is not None)

    # -- 내 쪽: 낸 놈만, 각자의 HP 로 (live.my_turn_state) ----------------
    # 전엔 창이 채운 6자리를 전부 HP 100% 로 넘겼다 (2026-09-21).
    # 같은 대면이 6마리 약 80점 / 실제 3마리 약 40점 / 벤치 HP20% 면 0점.
    B = lambda n: calc.Build(dex, dex.find_pokemon(n))
    six = ["한카리아스", "아머까오", "하마돈", "누리레느", "고릴타", "브리두라스"]
    rows = [(B(n), ["지진"], 100.0, i in (1, 3, 4)) for i, n in enumerate(six)]
    m = live.my_turn_state(rows, 3)
    check("내 쪽은 '냈다' 켠 셋만 넘긴다 (%s)"
          % [b.poke["name"] for b, _ in m["party"]],
          [b.poke["name"] for b, _ in m["party"]]
          == ["아머까오", "누리레느", "고릴타"] and not m["why"], m)
    check("나와 있는 놈의 번호를 셋 안에서 다시 찾는다 (%s)" % m["my_active"],
          m["my_active"] == 1)
    rows[1] = (rows[1][0], rows[1][1], 0.0, True)    # 아머까오 쓰러짐
    rows[4] = (rows[4][0], rows[4][1], 35.0, True)   # 고릴타 35%
    m2 = live.my_turn_state(rows, 3)
    check("쓰러진 내 포켓몬은 빠지고 번호가 따라간다",
          [b.poke["name"] for b, _ in m2["party"]] == ["누리레느", "고릴타"]
          and m2["my_active"] == 0, m2)
    check("벤치 HP 가 그대로 간다 (%s)" % m2["my_hp"],
          m2["my_hp"] == [100.0, 35.0])
    check("쓰러진 놈을 '나와 있음' 으로 고르면 계산을 거부한다",
          live.my_turn_state(rows, 1)["why"] is not None)
    check("'냈다' 가 아닌 놈을 '나와 있음' 으로 고르면 거부한다",
          "냈다" in (live.my_turn_state(rows, 0)["why"] or ""))
    four = [(B(n), [], 100.0, True) for n in six[:4]]
    check("'냈다' 가 넷이면 거부한다 (한 판에 셋)",
          "셋" in (live.my_turn_state(four, 0)["why"] or "")
          or "3마리" in (live.my_turn_state(four, 0)["why"] or ""))
    none = [(B(n), [], 100.0, False) for n in six]
    m3 = live.my_turn_state(none, 2)
    check("하나도 안 켜면 전부로 보되 '짐작했다' 고 표시한다",
          m3["guessed"] and len(m3["party"]) == 6 and not m3["why"], m3)

    ev = live.evidence_map({"하마돈": ["지진"], "누리레느": ["문라이트"]},
                           pokes)
    check("본 기술이 그놈에게만 붙는다 (%s)" % sorted(ev),
          sorted(ev) == ["하마돈"], sorted(ev))
    check("붙은 기술이 실제로 들어 있다",
          "지진" in ev["하마돈"].seen_moves, ev["하마돈"].seen_moves)

    # Fight 도 같은 규칙을 쓰는가 (규칙이 두 군데 있으면 갈라진다)
    f = live.Fight(dex, party)
    f.opp_add(ha)
    f.opp_add(ta)
    check("상대가 쌓인다 (%d마리)" % len(f.opp_party),
          len(f.opp_party) == 2, len(f.opp_party))
    check("이미 본 놈을 다시 치면 안 늘고 그놈이 나온 것이 된다",
          f.opp_add(ha) and len(f.opp_party) == 2 and f.opp_active == 0,
          (len(f.opp_party), f.opp_active))
    f.seen_of().add(("기술", "지진"))
    live.apply_token(f, "x")                 # 나와 있는 놈이 쓰러졌다
    check("쓰러뜨리면 계산에서 빠진다 (%s)"
          % ", ".join(p["name"] for p in f.opp_pokes()),
          [p["name"] for p in f.opp_pokes()] == ["타부자고"], f.opp_pokes())
    check("쓰러진 놈의 관찰도 같이 빠진다",
          f.evidence() is None, f.evidence())
    check("상대가 최대 %d마리를 넘지 않는다" % live.MAX_PARTY,
          "꽉" in [live.apply_token(f, n["name"]) for n in
                   [dex.find_pokemon(x) for x in
                    ("누리레느", "갑주무사", "루카리오", "드닐레이브",
                     "브리두라스")]][-1],
          len(f.opp_party))


def test_windows_safe(dex):
    """**윈도우에서만 나는 고장을 여기서 잡는다.**

    리눅스·맥에서는 한글을 아무리 찍어도 멀쩡한데, 윈도우는 화면
    인코딩이 cp949/cp1252 라 UTF-8 한글을 찍는 순간 **프로그램이 죽는다.**
    글자가 깨지는 정도가 아니라 죽는다.

        UnicodeEncodeError: 'charmap' codec can't encode characters

    실제로 첫 윈도우 빌드가 tests.py 첫 줄에서 이걸로 터졌다. 방어를
    live.py 에만 넣어 뒀던 것이 원인이다. **여기서는 절대 재현이 안 되는
    고장이라, 규칙으로 잡는 수밖에 없다.**
    """
    print("\n[43] 윈도우에서 죽지 않는가")
    import io
    import os
    import re

    root = os.path.dirname(os.path.abspath(__file__))
    missing = []
    checked = []
    for name in sorted(os.listdir(root)):
        if not name.endswith(".py") or name == "paths.py":
            continue
        src = io.open(os.path.join(root, name), encoding="utf-8").read()
        # 켜서 쓰는 프로그램인가 (화면에 찍고, 직접 실행되는가)
        if "if __name__" not in src or "print(" not in src:
            continue
        if not re.search(r"^def main\(\):", src, re.M):
            continue
        checked.append(name)
        body = src[re.search(r"^def main\(\):", src, re.M).end():][:400]
        if "fix_console" not in body:
            missing.append(name)
    check("켜서 쓰는 프로그램 %d개가 모두 main 처음에 fix_console 을 부른다"
          % len(checked), not missing, missing)
    check("확인한 프로그램이 충분히 많다 (%d개)" % len(checked),
          len(checked) >= 10, checked)

    # 실제로 그 함수가 죽지 않는지 (두 번 불러도 안전해야 한다)
    blew = None
    try:
        paths.fix_console()
        paths.fix_console()
    except Exception as e:
        blew = e
    check("fix_console 은 여러 번 불러도 안전하다", blew is None, blew)

    # ! **찍는 쪽만 고치면 반쪽이다.** 화면에는 한글이 잘 나오는데
    #   사용자가 "한카리아스" 라고 친 것이 깨져 들어와 "못 찾았습니다"
    #   가 됐다. 실전에서 이름을 한 글자도 못 치게 된다.
    src = io.open(os.path.join(root, "paths.py"), encoding="utf-8").read()
    body = src[src.index("def fix_console"):]
    check("읽는 쪽(stdin)도 UTF-8 로 맞춘다", "sys.stdin" in body,
          body[:200])
    check("찍는 쪽(stdout·stderr)도 맞춘다",
          "sys.stdout" in body and "sys.stderr" in body)

    # 창 UI — **여기서는 진짜로 띄울 수가 없다** (컨테이너에 tkinter 도
    # 화면도 없다). 그래서 두 겹으로 본다:
    #   ① 여기: `faketk/` 의 가짜 tkinter 를 끼워서 **창을 통째로 돌린다**
    #   ② 윈도우 빌드: 진짜 tkinter 로 `gui.py --점검`
    # ①이 없던 동안 창 코드는 문법 말고는 한 줄도 안 돌아간 채로
    # 윈도우에 갔고, 그래서 네 번 터졌다.
    import gui
    import live
    check("창 코드가 문법적으로 멀쩡하다 (import 된다)",
          hasattr(gui, "App") and hasattr(gui, "check"))

    # ★ 가짜 tkinter 로 창을 끝까지 돌린다 ---------------------------------
    import subprocess
    fake = os.path.join(root, "faketk")
    check("가짜 tkinter 가 저장소에 있다", os.path.isdir(fake), fake)
    env = dict(os.environ)
    env["PYTHONPATH"] = fake + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([sys.executable, os.path.join(root, "gui.py"), "--점검"],
                       cwd=root, env=env, capture_output=True)
    said = (r.stdout or b"").decode("utf-8", "replace")
    check("창을 가짜 tkinter 로 끝까지 돌린다 (칸 채우기 -> 추천 -> 선출)",
          r.returncode == 0 and "창 점검 끝" in said,
          (said + (r.stderr or b"").decode("utf-8", "replace"))[-700:])
    check("그 점검이 상대 파티가 계산까지 가는지까지 본다",
          "상대 파티가 계산까지" in said, said[-300:])
    ok, why = gui.have_tk()
    check("tkinter 가 있나 없나를 말해 준다 (여기: %s)"
          % ("있음" if ok else "없음"), isinstance(ok, bool))
    if not ok:
        check("없으면 글자판을 쓰라고 안내한다",
              "live.py" in io.open(os.path.join(root, "gui.py"),
                                   encoding="utf-8").read())
    # ★ **고르는 규칙은 창이 아니라 live.py 에 있다.** 창은 못 보지만
    #   규칙은 여기서 전부 시험한다. 사용자가 "한 줄씩 적는 게 아니라
    #   칸에 검색해서 넣게 해 달라" 고 해서 만든 부분이다.
    pool = live.pickable_pokemon(dex)
    # 처음엔 '이름마다 하나뿐' 을 봤다 — 후보에 같은 글자(한카리아스·메가·메가Z)가 여럿 뜨면
    # 무엇을 고른 건지 모르기 때문이다. 그런데 그 규칙 때문에 **워시로토무 등 모습이 다른 23종을
    # 못 골랐다** (2026-09-22). 뜻(같은 글자가 두 번 안 뜬다)은 그대로 두고 기준을 이름표로 바꾼다.
    labels = [live.poke_label(p) for p in pool]
    check("후보에 같은 글자가 두 번 안 뜬다 — 이름표가 모두 다르다 (%d마리)" % len(pool),
          len(set(labels)) == len(pool), len(pool))
    usage = set(dex.usage)
    dup = {}
    for p in pool:
        dup.setdefault(p["name"], []).append(p)
    odd = [n for n, ps in dup.items() if len(ps) > 1 and not all(p["key"] in usage for p in ps)]
    check("같은 이름이 여럿이면 전부 사용률에 나오는 서로 다른 모습이다", not odd, odd)
    check("메가는 후보에 없다 (도구로 정해진다)",
          not any(p.get("isMega") for p in pool))
    hits = [p["name"] for p in live.rank_hits(pool, "한카")]
    check("'한카' 를 치면 한카리아스 하나만 뜬다 (%s)" % hits,
          hits == ["한카리아스"], hits)
    hits2 = [p["name"] for p in live.rank_hits(pool, "리자")]
    check("가운데서 맞는 것보다 앞에서 맞는 것이 먼저다 (%s)" % hits2[:2],
          hits2 and hits2[0] == "리자몽", hits2)

    hama = dex.find_pokemon("하마돈")
    moves, known = live.learnable(dex, hama)
    names = [m["name"] for m in moves]
    check("배우는 기술만 후보로 준다 (하마돈 %d개)" % len(names),
          known and "지진" in names and "역린" not in names,
          (known, len(names)))
    fake = dict(hama)
    fake["key"] = "9999-99"
    fake["dexNo"] = 9999
    all_moves, known2 = live.learnable(dex, fake)
    check("배우는 목록이 없으면 **전체를 준다** (빈 목록을 주면 안 된다)",
          not known2 and len(all_moves) > 400, (known2, len(all_moves)))

    check("특성은 그 포켓몬 것만 (%s)" % live.abilities_of(dex, hama),
          live.abilities_of(dex, hama) == ["모래날림", "모래의힘"])
    check("성격은 25개, 보정 없는 것이 먼저",
          len(live.nature_names(dex)) == 25
          and "보정 없음" in live.nature_label(dex, live.nature_names(dex)[0]),
          live.nature_names(dex)[:3])
    check("성격에 무엇이 오르내리는지 붙여 준다 (%s)"
          % live.nature_label(dex, "무사태평"),
          "방어" in live.nature_label(dex, "무사태평")
          and "스피드" in live.nature_label(dex, "무사태평"))
    check("노력치 규칙을 말로 알려 준다",
          live.ev_problem({"hp": 40}) and live.ev_problem(
              {"hp": 32, "attack": 32, "defense": 32})
          and live.ev_problem({"hp": 32, "defense": 22, "spDef": 12}) is None,
          live.ev_problem({"hp": 40}))

    gsrc = io.open(os.path.join(root, "gui.py"), encoding="utf-8").read()
    check("창이 그 규칙들을 쓴다 (스스로 다시 짜지 않는다)",
          all(x in gsrc for x in ("live.pickable_pokemon", "live.learnable",
                                  "live.abilities_of", "live.nature_names",
                                  "live.ev_problem")))
    check("창에 검색 칸(Picker)이 있다",
          "class Picker" in gsrc and "Listbox" in gsrc)
    check("점검 모드가 칸을 실제로 채워 본다",
          "slot.stat_rows" in gsrc and "app.ask()" in gsrc)
    check("창도 시작할 때 fix_console 을 부른다", "paths.fix_console" in gsrc)
    check("탐색을 다른 갈래에서 돌린다 (창이 얼면 못 쓴다)",
          "threading.Thread" in gsrc)
    check("창을 만든 갈래에서만 건드린다 (root.after)",
          "root.after" in gsrc)
    # 칸으로 받게 바뀌면서 live.read_line 은 더 안 쓴다. 대신 몸을
    # 만드는 것도 계산도 여전히 시험된 곳에 맡기는지를 본다.
    check("계산은 시험된 곳에 맡긴다 (search·live 를 쓴다)",
          "search.best_action" in gsrc and "live.build_one" in gsrc
          and "live.save_party_file" in gsrc)

    # 묶인 실행 파일에서 읽는 자리와 쓰는 자리가 갈려 있는가
    check("읽는 자리와 쓰는 자리를 따로 정한다",
          hasattr(paths, "read_root") and hasattr(paths, "write_root"))
    check("평소에는 둘이 같다",
          paths.read_root() == paths.write_root(),
          (paths.read_root(), paths.write_root()))


def test_battle_result(dex):
    """턴 루프가 '승패' 가 아니라 '끝났을 때의 상태' 를 내놓는가.

    이게 이 단계의 설계 결정이다. 승패만 내놓으면 랭크업의 값어치가
    후속 포켓몬까지 이어지는 것을 영영 못 본다.
    """
    print("\n[14] 끝났을 때의 상태가 남는가  ← 4-B 의 설계 결정")
    import random

    mine, _ = calc.popular_build(dex, dex.find_pokemon("메가보만다"))
    theirs, _ = calc.popular_build(dex, dex.find_pokemon("하마돈"))
    opp_plan, _, _ = battle.opponent_plan(dex, theirs, mine)

    dance = [dex.find_move("용의춤"), dex.find_move("용의춤"),
             dex.find_move("이판사판태클")]
    plain = [dex.find_move("이판사판태클")]

    a = battle.evaluate(dex, mine, theirs, dance, opp_plan, trials=60, seed=3)
    b = battle.evaluate(dex, mine, theirs, plain, opp_plan, trials=60, seed=3)

    check("이기고 나서 랭크가 남는다",
          a["avgRanksWhenWin"].get("attack", 0) > 1.5, a["avgRanksWhenWin"])
    check("그냥 때리면 랭크가 안 남는다",
          not b["avgRanksWhenWin"], b["avgRanksWhenWin"])
    check("랭크가 남는 쪽의 '남는 몸' 점수가 더 높다",
          a["carry"] > b["carry"], "%.0f vs %.0f" % (a["carry"], b["carry"]))
    check("하마돈은 메가보만다를 못 잡는다 (지진 무효)",
          a["winRate"] > 0.9, a["winRate"])


def test_battle_hand_check(dex):
    """손으로 검산 — 4-B 의 완료 조건.

    회복기는 '얼마나 더 버티게 만드는가' 가 값어치다. 산수로 확인한다.
    회복기가 없으면 N턴에 죽는데, 매 턴 최대 HP의 1/2 을 회복하면
    한 방에 반 이상을 못 깎는 이상 영원히 안 죽어야 한다.
    """
    print("\n[15] 손으로 검산  ← 4-B 완료 조건")
    import random

    # 한카리아스(지진)로 하마돈을 친다. 하마돈은 게으름피우기(1/2 회복)만 쓴다.
    atk, _ = calc.popular_build(dex, dex.find_pokemon("한카리아스"))
    dfn, _ = calc.popular_build(dex, dex.find_pokemon("하마돈"))
    quake = dex.find_move("지진")
    heal = dex.find_move("게으름피우기")

    res = calc.calc_damage(dex, atk, dfn, quake)
    half = dfn.stat("hp") / 2.0
    check("전제: 지진 최대 데미지(%d)가 하마돈 반피(%.0f)보다 작다"
          % (res["max"], half), res["max"] < half)

    r_heal = battle.run_once(dex, atk, dfn, [quake], [heal], random.Random(5))
    r_bare = battle.run_once(dex, atk, dfn, [quake], [dex.find_move("막치기")],
                             random.Random(5))
    check("회복만 하면 안 죽는다 (%d턴까지 안 끝남)" % battle.MAX_TURNS,
          r_heal["result"] == "안 끝남", r_heal["result"])
    check("회복을 안 하면 죽는다", r_bare["result"] == "이김", r_bare["result"])
    check("회복 쪽이 더 오래 버틴다",
          r_heal["turns"] > r_bare["turns"],
          "%d vs %d" % (r_heal["turns"], r_bare["turns"]))


def test_status(dex):
    """상태 이상 — 무엇이 걸리고 무엇이 막히는가.

    출처를 두 가지로 나눠서 본다.
      · 게임 데이터에 적혀 있는 것 — 특성 면역 9개, 기술별 타입 면역 4개
      · 게임 데이터에 없는 것 — '불꽃은 화상에 안 걸린다' 같은 타입 면역 일반 규칙.
        본편 값을 가정했고 calc.STATUS_TYPE_IMMUNE 한 곳에 모아 경고를 띄운다.
    """
    print("\n[16] 상태 이상")
    import random

    im = battle.status_immune_abilities(dex)
    check("특성 면역을 설명문에서 9개 읽음", len(im) == 9, sorted(im))
    check("유연 = 마비 면역", im.get("유연") == {"마비"}, im.get("유연"))
    check("불면 = 잠듦·졸음 면역", im.get("불면") == {"잠듦", "졸음"}, im.get("불면"))
    check("스위트베일도 잠듦·졸음 ('같은 편은' 이 앞에 붙는 문장)",
          im.get("스위트베일") == {"잠듦", "졸음"}, im.get("스위트베일"))
    check("전기자석파는 땅타입에게 안 통한다 (설명문)",
          battle.move_type_immunity(dex.find_move("전기자석파")) == ["땅"])

    def fight(a, b, seed=1):
        return battle.Battle(dex, calc.Build(dex, dex.find_pokemon(a)),
                             calc.Build(dex, dex.find_pokemon(b)),
                             rng=random.Random(seed), log=True)

    # 기술 설명문에 적힌 타입 면역
    bt = fight("썬더볼트", "한카리아스")
    bt.step(dex.find_move("전기자석파"), dex.find_move("칼춤"))
    check("땅타입은 전기자석파에 안 걸린다", bt.opp.status is None, bt.opp.status)

    # 본편 규칙을 가정한 타입 면역
    bt = fight("하마돈", "리자몽")
    bt.step(dex.find_move("도깨비불"), dex.find_move("날개쉬기"))
    check("불꽃타입은 화상에 안 걸린다", bt.opp.status is None, bt.opp.status)
    check("그때 '데이터에 없는 가정' 이라고 경고한다",
          any("본편 규칙 가정" in w for w in bt.warnings), bt.warnings)

    # 특성 면역
    bt = fight("하마돈", "리자몽")
    bt.opp.base.ability = "유연"
    bt.step(dex.find_move("전기자석파"), dex.find_move("날개쉬기"))
    check("특성 '유연' 이 마비를 막는다", bt.opp.status is None, bt.opp.status)

    # 하품 -> 졸음 -> 잠듦
    bt = fight("하마돈", "보만다")
    bt.step(dex.find_move("하품"), dex.find_move("칼춤"))
    check("하품은 바로 재우지 않고 졸음부터",
          bt.opp.status is None and bt.opp.drowsy, bt.opp.status)
    bt.step(dex.find_move("하품"), dex.find_move("칼춤"))
    check("다음 턴에 잠든다", bt.opp.status == "잠듦", bt.opp.status)
    check("잠듦 지속이 %d~%d턴 안" % (calc.CONFIG["sleep_min"],
                                     calc.CONFIG["sleep_max"]),
          calc.CONFIG["sleep_min"] - 1 <= bt.opp.status_turns
          <= calc.CONFIG["sleep_max"], bt.opp.status_turns)

    # 맹독은 턴마다 세진다
    bt = fight("한카리아스", "보만다")
    bt.step(dex.find_move("맹독"), dex.find_move("칼춤"))
    mx = bt.opp.max_hp
    first = mx - bt.opp.hp
    bt.step(dex.find_move("칼춤"), dex.find_move("칼춤"))
    second = mx - bt.opp.hp - first
    check("맹독 1턴째 = 최대HP/16", first == mx // 16, "%d vs %d" % (first, mx // 16))
    check("맹독 2턴째 = 그 두 배", second == mx * 2 // 16,
          "%d vs %d" % (second, mx * 2 // 16))

    # 잠자기는 게임 설명문대로 2턴 (본편은 3턴이라 다르다)
    eff = battle.move_effects(dex.find_move("잠자기"))
    check("잠자기 = 전체 회복 + 스스로 잠듦",
          {e["kind"] for e in eff} == {"heal", "self_status"}, eff)


def test_scout(dex):
    """4-C — 상대를 채용률대로 뽑는다.

    제일 중요한 건 '뽑은 결과가 원래 채용률과 같은가' 다.
    여기가 틀리면 승률이 통째로 어긋나는데, 숫자만 봐서는 알 수가 없다.
    """
    print("\n[17] 상대를 분포로 뽑기")
    import random

    # 기술칸이 4개라는 제약 아래에서도 채용률이 재현돼야 한다.
    # 하마돈은 채용률 합이 398% 라 4칸이 거의 꽉 찬다 — 제일 까다로운 경우.
    worst = 0.0
    for name in ("하마돈", "킬가르도", "한카리아스", "보만다"):
        for _, want, got in scout.check_marginals(dex, dex.find_pokemon(name),
                                                  trials=4000, seed=2):
            worst = max(worst, abs(got - want))
    check("채용률이 2%%p 안쪽으로 재현됨 (최대 %.1f%%p)" % worst, worst < 2.0, worst)

    # 4칸을 절대 넘지 않는다
    rng = random.Random(3)
    over = 0
    for _ in range(600):
        if len(scout.sample_moveset(dex, dex.find_pokemon("하마돈"), rng)) > 4:
            over += 1
    check("기술칸 4개를 안 넘는다", over == 0, over)

    # 조건부 뽑기가 제약을 지키는가 (다시 던지는 방식이 아니라 직접 뽑는다)
    w = [0.9] * 8
    sizes = {len(scout.sample_conditional(rng, w, 4)) for _ in range(300)}
    check("조건부 뽑기가 4칸 이하만 낸다", max(sizes) <= 4, sizes)

    # 본 기술은 확률 100%
    ev = scout.Evidence(seen_moves=["얼음엄니"])
    probs = dict((m["name"], p) for m, p in
                 scout.move_probabilities(dex, dex.find_pokemon("하마돈"), ev))
    check("본 기술은 확률 100%", probs["얼음엄니"] == 1.0, probs["얼음엄니"])
    always = all("얼음엄니" in [m["name"] for m in
                 scout.sample_moveset(dex, dex.find_pokemon("하마돈"), rng, ev)]
                 for _ in range(200))
    check("본 기술은 항상 뽑힌다", always)

    # 한 칸을 두고 경쟁하는 것들은 정규화된다 (노력치는 원본 합이 ~162%)
    u = scout.usage_of(dex, dex.find_pokemon("하마돈"))
    tot = sum(p for _, p in scout._normalized(u["evs"]))
    check("노력치 분포가 합계 1로 정규화됨", abs(tot - 1.0) < 1e-6, tot)

    # 메가스톤을 뽑으면 그 메가로 싸운다
    rng = random.Random(9)
    forms = set()
    for _ in range(80):
        b = scout.sample_build(dex, dex.find_pokemon("보만다"), rng)
        forms.add(b.poke.get("isMega", False))
    check("보만다는 대부분 메가로 뽑힌다 (보만다나이트 97.7%)", True in forms, forms)


def test_scout_narrowing(dex):
    """관찰하면 범위가 좁아지는가 — 설계 문서 3-4(2)."""
    print("\n[18] 관찰로 좁히기")
    me, _ = calc.popular_build(dex, dex.find_pokemon("메가보만다"))
    opp_poke = dex.find_pokemon("하마돈")
    plan = [dex.find_move("이판사판태클")]

    blind = battle.evaluate_vs_distribution(dex, me, opp_poke, plan,
                                            trials=150, seed=4)
    seen = battle.evaluate_vs_distribution(
        dex, me, opp_poke, plan, trials=150, seed=4,
        evidence=scout.Evidence(seen_moves=["얼음엄니"]))
    check("아무것도 모를 때는 이긴다 (하마돈 지진은 비행에 무효)",
          blind["winRate"] > 0.8, blind["winRate"])
    check("얼음엄니를 봤다면 승률이 확 떨어진다",
          seen["winRate"] < blind["winRate"] - 0.3,
          "%.2f -> %.2f" % (blind["winRate"], seen["winRate"]))
    check("졌을 때 무엇이 있었는지 센다",
          any(b["name"] == "얼음엄니" for b in blind["blame"]),
          [b["name"] for b in blind["blame"][:3]])


def test_switching(dex):
    """5단계 — 교체 · 압정 · 강제 교체기.

    제일 중요한 규칙은 **물러나면 랭크가 사라진다** 는 것이다.
    이게 있어야 '용의춤을 쌓았으면 안 빠져야 한다' 가 계산으로 나오고,
    상위권이 날려버리기를 드는 이유도 설명된다.
    """
    print("\n[19] 교체 · 압정")
    import random

    def B(name):
        return calc.popular_build(dex, dex.find_pokemon(name))[0]

    # --- 물러나면 랭크가 사라진다 ---
    bt = battle.Battle(dex, [B("메가보만다"), B("고릴타")], B("하마돈"),
                       rng=random.Random(1))
    bt.step(dex.find_move("용의춤"), dex.find_move("하품"))
    first = bt.me_party.members[0]
    check("용의춤으로 공격+1", first.ranks["attack"] == 1, first.ranks)
    bt.step(("교체", 1), dex.find_move("하품"))
    check("교체하면 나간 쪽 랭크가 사라진다",
          first.ranks["attack"] == 0, first.ranks)
    check("교체하면 나와 있는 놈이 바뀐다", bt.me.name == "고릴타", bt.me.name)

    # --- 스텔스록은 바위 상성을 탄다 ---
    # ! 전에는 [메가보만다, 한카리아스] 로 재면서 "메가한카리아스Z 는 순수
    #   드래곤이라 1배" 라고 적어 놨는데, 메가는 **대전 중에** 되는 것이라
    #   판이 시작될 때는 아무도 메가가 아니다. 검사 자체가 틀린 전제였다.
    #   이제 **두 몸을 나란히 재서** 상성을 정말 타는지 본다.
    #     보만다   드래곤/비행 -> 바위 2배   -> 1/4
    #     한카리아스 드래곤/땅   -> 바위 0.5배 -> 1/16
    for name, mult in (("보만다", 2.0), ("한카리아스", 0.5)):
        bt = battle.Battle(dex, [B("고릴타"), B(name)], B("하마돈"),
                           rng=random.Random(1), log=True)
        bt.me_party.hazards["스텔스록"] = 1
        bt.switch_in(bt.me_party, 1)
        m = bt.me_party.members[1]
        want = max(1, int(m.max_hp * mult / 8))
        check("스텔스록이 %s 에게 %.1f배로 들어간다 (%d/%d)"
              % (name, mult, m.max_hp - m.hp, m.max_hp),
              m.max_hp - m.hp == want, (m.max_hp - m.hp, want))

    # --- ★ 메가진화는 한 게임에 한 번이고, **그 자체가 수(手)다** ---
    # 사용자가 두 번에 걸쳐 못 박았다 —
    #   "메가진화는 한 게임에 한번만" (2026-09-19)
    #   "무조건 B야. 이건 선택이 아니라 필수" (2026-09-21)
    # 처음엔 셋 다 메가로 싸웠고(34.2% vs 0.0%), 그 다음엔 "선봉만 메가" 로
    # 굳혀서 **메가를 아껴 뒀다 나중에 쓰는 수를 표현조차 못 했다.**
    tri = [B("메가보만다"), B("한카리아스"), B("갑주무사")]
    check("셋 다 메가스톤을 든다 (검사 전제)",
          all(b.poke.get("isMega") for b in tri), [b.name for b in tri])
    bt3 = battle.Battle(dex, tri, B("하마돈"), rng=random.Random(1))
    check("판이 시작될 때는 **아무도 메가가 아니다**",
          not any(m.is_mega for m in bt3.me_party.members),
          [m.name for m in bt3.me_party.members])
    check("메가 전에는 기본 폼 특성을 쓴다 (갑주무사 = %s)"
          % bt3.me_party.members[2].base.ability,
          bt3.me_party.members[2].base.ability == "위기회피",
          bt3.me_party.members[2].base.ability)
    check("셋 다 메가 후보다", bt3.me_party.mega_candidates() == [0, 1, 2],
          bt3.me_party.mega_candidates())

    # ("메가", 기술) 로 그 턴에 메가가 된다
    bt3.step(("메가", dex.find_move("지진")), dex.find_move("맹독"))
    check("('메가', 기술) 을 두면 메가가 된다 (%s)" % bt3.me.name,
          bt3.me.is_mega, bt3.me.name)
    check("한 편은 한 번만 — 이제 후보가 없다",
          bt3.me_party.mega_candidates() == [],
          bt3.me_party.mega_candidates())
    check("두 번째 메가는 거부된다",
          not bt3.me_party.do_mega(bt3.me_party.members[1]),
          bt3.me_party.members[1].name)

    # ★ **메가는 기술보다 먼저 처리돼야 한다.** 늦게 하면 기본 폼 능력치로
    #   때리게 되고, 스피드도 기본 폼으로 겨루게 된다. 조용히 틀어지는 자리라
    #   '같은 씨앗에서 데미지가 달라지는가' 로 못 박는다.
    def _hit(mega):
        b = battle.Battle(dex, [B("메가보만다")], B("하마돈"),
                          rng=random.Random(7))
        mv = dex.find_move("이판사판태클")
        h = b.opp.hp
        b.step(("메가", mv) if mega else mv, dex.find_move("맹독"))
        return h - b.opp.hp
    on, off = _hit(True), _hit(False)
    check("메가가 기술보다 먼저 걸린다 (메가 %d / 기본 %d)" % (on, off),
          on != off, (on, off))
    check("메가 쪽이 더 아프다", on > off, (on, off))

    # 상대 쪽도 똑같이 걸린다
    bt4 = battle.Battle(dex, B("하마돈"), tri, rng=random.Random(1))
    check("상대도 기본 폼으로 시작한다",
          not any(m.is_mega for m in bt4.opp_party.members),
          [m.name for m in bt4.opp_party.members])
    bt4.step(dex.find_move("맹독"), ("메가", dex.find_move("이판사판태클")))
    check("상대도 메가를 쓸 수 있다 (%s)" % bt4.opp.name,
          bt4.opp.is_mega, bt4.opp.name)

    # 메가 스톤이 없으면 메가 수가 없다
    plain = battle.Battle(dex, [B("고릴타"), B("하마돈")], B("하마돈"),
                          rng=random.Random(1))
    check("스톤이 없으면 메가 후보가 없다",
          plain.me_party.mega_candidates() == [],
          plain.me_party.mega_candidates())

    # --- 압정은 떠 있으면 안 밟지만 스텔스록은 밟는다 ---
    bt = battle.Battle(dex, [B("하마돈"), B("메가보만다")], B("하마돈"),
                       rng=random.Random(1))
    bt.me_party.hazards["압정뿌리기"] = 1
    bt.switch_in(bt.me_party, 1)
    flyer = bt.me_party.members[1]
    check("비행타입은 압정을 안 밟는다", flyer.hp == flyer.max_hp,
          "%d/%d" % (flyer.hp, flyer.max_hp))

    # --- 독압정은 독타입이 걷어 간다 ---
    poison = [p for p in dex.pokemon
              if "독" in p["types"] and (dex.usage.get(p["key"]) or {}).get("rank")]
    if poison:
        bt = battle.Battle(dex, [B("하마돈"), calc.Build(dex, poison[0])],
                           B("하마돈"), rng=random.Random(1))
        bt.me_party.hazards["독압정"] = 1
        bt.switch_in(bt.me_party, 1)
        check("독타입이 나오면 독압정을 걷어 간다",
              "독압정" not in bt.me_party.hazards, bt.me_party.hazards)

    # --- 강제 교체기가 실제로 바꾼다 ---
    bt = battle.Battle(dex, [B("메가보만다"), B("고릴타")], B("하마돈"),
                       rng=random.Random(2))
    bt.step(dex.find_move("용의춤"), dex.find_move("날려버리기"))
    check("날려버리기에 밀려 강제로 바뀐다", bt.me.name == "고릴타", bt.me.name)
    check("밀려 나가면 쌓은 랭크도 같이 날아간다",
          bt.me_party.members[0].ranks["attack"] == 0,
          bt.me_party.members[0].ranks)

    # --- 흡반은 강제 교체를 막는다 ---
    bt = battle.Battle(dex, [B("메가보만다"), B("고릴타")], B("하마돈"),
                       rng=random.Random(2))
    bt.me_party.members[0].base.ability = "흡반"
    bt.step(dex.find_move("용의춤"), dex.find_move("날려버리기"))
    # ! 이름이 '메가보만다' 가 아니라 '보만다' 다 — 메가는 대전 중에 두는
    #   수라서 판이 시작될 때는 기본 폼이다. 막히는 동작 자체는 그대로다.
    check("흡반이 강제 교체를 막는다", bt.me.name == "보만다", bt.me.name)

    # --- 쓰러지면 다음이 나오고, 파티가 다 죽어야 끝난다 ---
    bt = battle.Battle(dex, [B("메가보만다"), B("고릴타")], B("하마돈"),
                       rng=random.Random(1))
    bt.me_party.members[0].hp = 0
    bt._replace_fainted()
    check("쓰러지면 다음 포켓몬이 나온다", bt.me.name == "고릴타", bt.me.name)
    check("한 마리 쓰러져도 안 끝난다", not bt.over)
    bt.me_party.members[1].hp = 0
    check("다 쓰러지면 끝난다", bt.over)


def test_intimidate(dex):
    """위협 — 1위 보만다 99.3%, 갸라도스 99.4%. 나올 때마다 상대 공격을 깎는다."""
    print("\n[20] 나올 때 터지는 특성")
    import random

    def B(name):
        return calc.popular_build(dex, dex.find_pokemon(name))[0]

    gyara = calc.Build(dex, dex.find_pokemon("갸라도스"), ability="위협")
    bt = battle.Battle(dex, gyara, B("한카리아스"), rng=random.Random(1),
                       log=True)
    check("위협이 상대 공격을 1단계 깎는다",
          bt.opp.ranks["attack"] == -1, bt.opp.ranks)
    check("로그에 남는다", any("위협" in r for r in bt.log), bt.log[:3])

    # 파수견은 위협을 막고 오히려 공격이 오른다
    target = calc.Build(dex, dex.find_pokemon("한카리아스"), ability="파수견")
    bt = battle.Battle(dex, gyara, target, rng=random.Random(1))
    check("파수견은 위협을 안 받는다", bt.opp.ranks["attack"] >= 0, bt.opp.ranks)


def test_sacrifice(dex):
    """빼는 것과 내주는 것은 값이 다르다.

      · 빼면   — 들어오는 놈이 그 턴에 한 대 맞는다
      · 내주면 — 한 마리를 잃지만 다음 놈이 공짜로 나온다 (그 턴에 안 맞는다)

    불리하다고 늘 빼는 것이 답은 아니다. 둘을 나란히 재려면
    '이길 때 몇 마리를 잃었나' 까지 세야 한다.
    """
    print("\n[21] 빼는 것 vs 내주는 것")
    import random

    def B(name):
        return calc.popular_build(dex, dex.find_pokemon(name))[0]

    quake = dex.find_move("지진")

    # (가) 직접 뺀다 — 들어오는 놈이 그 턴에 맞는다
    bt = battle.Battle(dex, [B("메가보만다"), B("한카리아스")], B("하마돈"),
                       rng=random.Random(5))
    bt.step(("교체", 1), quake)
    swapped_in = bt.me_party.members[1]
    check("빼면 들어온 놈이 그 턴에 맞는다",
          swapped_in.hp < swapped_in.max_hp,
          "%d/%d" % (swapped_in.hp, swapped_in.max_hp))

    # (나) 내준다 — 쓰러진 자리로 나오는 턴에는 안 맞는다
    bt = battle.Battle(dex, [B("메가보만다"), B("한카리아스")], B("하마돈"),
                       rng=random.Random(5))
    bt.me_party.members[0].hp = 1        # 이번 턴에 쓰러질 상태로
    bt.step(dex.find_move("이판사판태클"), quake)
    came_in = bt.me_party.members[1]
    check("쓰러진 자리로 나온 놈은 그 턴에 안 맞는다",
          came_in.hp == came_in.max_hp,
          "%d/%d" % (came_in.hp, came_in.max_hp))
    check("대신 한 마리를 잃었다",
          not bt.me_party.members[0].alive)

    # 압정은 어느 쪽으로 나오든 밟는다
    bt = battle.Battle(dex, [B("메가보만다"), B("한카리아스")], B("하마돈"),
                       rng=random.Random(5))
    bt.me_party.hazards["스텔스록"] = 1
    bt.me_party.members[0].hp = 1
    bt.step(dex.find_move("이판사판태클"), quake)
    came_in = bt.me_party.members[1]
    check("공짜로 나와도 압정은 밟는다", came_in.hp < came_in.max_hp,
          "%d/%d" % (came_in.hp, came_in.max_hp))

    # 결과에 '몇 마리 잃었나' 가 들어 있다
    me = [B("메가보만다"), B("한카리아스")]
    opp_plan, _, _ = battle.opponent_plan(dex, B("브리두라스"), me)
    r = battle.evaluate(dex, me, [B("브리두라스")], [quake], opp_plan,
                        trials=40, seed=2, my_party=me)
    check("이길 때 몇 마리를 잃었는지 센다", "lostWhenWin" in r, list(r)[:4])
    check("남는 파티 HP 도 센다", "partyHpWhenWin" in r)


def test_policy(dex):
    """교체돼 나온 놈은 자기 기술을 쓴다.

    이게 없으면 고릴타가 보만다의 이판사판태클을 쓰려 든다.
    배우지도 않은 기술이라 조용히 이상한 계산이 된다.
    """
    print("\n[22] 교체된 뒤에 무엇을 쓰는가")
    me = [calc.popular_build(dex, dex.find_pokemon("메가보만다"))[0],
          calc.popular_build(dex, dex.find_pokemon("고릴타"))[0]]
    opp = calc.popular_build(dex, dex.find_pokemon("하마돈"))[0]
    plan = [dex.find_move("이판사판태클")]
    pol = battle.Policy(dex, me, opp, plan)

    party = battle.Party(dex, me)
    # ! 메가를 들 수 있는 놈이면 계획 턴에도 메가를 같이 한다
    #   (`auto_mega`). 그래서 수가 ("메가", 기술) 로 나온다 — 그게 맞다.
    #   안 해 주면 메가 보유자가 실제보다 약해진다 (0.85 -> 0.69 로 쟀다).
    def _mv(action):
        return action[1] if isinstance(action, tuple) else action
    first = pol.act(party, 0)
    check("리드는 계획대로 쓴다",
          _mv(first)["name"] == "이판사판태클", first)
    check("계획 턴에도 메가를 같이 한다",
          isinstance(first, tuple) and first[0] == "메가", first)
    # ★ **메가스톤을 들면 Side 가 기본 폼으로 갈아 끼운다.** 그때
    #   `self.base` 가 새 객체가 되는데, Policy 는 계획의 주인을 `is` 로
    #   확인한다. 그래서 이걸 안 챙기면 **메가스톤 든 놈은 계획이 통째로
    #   버려진다** — 전에 똑같은 자리에서 크게 당했다 (§8-4).
    #   이 검사가 실제로 그 결함을 잡았다 (2026-09-21).
    check("메가스톤을 들어도 계획의 주인을 알아본다",
          pol._is_lead(party.active), (party.active.name, pol.lead.name))
    check("그래서 넘겨받은 Build 를 그대로 들고 있는다",
          party.active.origin is me[0], party.active.origin.name)
    party.active_idx = 1
    got = pol.act(party, 0)
    check("바뀐 뒤에는 그놈 기술을 쓴다",
          got["name"] != "이판사판태클", got["name"])
    learn = dex.learnsets.get(me[1].poke["key"], [])
    check("그리고 실제로 배우는 기술이다 (%s)" % got["name"],
          got["id"] in learn, got["name"])


def test_replacement_choice(dex):
    """쓰러진 자리에 누구를 낼지 — **HP 만으로는 못 정한다.**

    필요한 HP 는 상대마다 다르다. 물어야 할 것은
    "이 상대를 상대하려면 몇 대를 버텨야 하고, 지금 HP 로 그게 되는가" 다.

      · 따라큐는 탈이 살아 있으면 한 대를 통째로 막고 야습(우선도 +1)으로 때린다.
        HP 30% 여도 확실히 두 대는 넣는다.
      · 느리고 한 방에 죽는 놈은 HP 100% 여도 한 대도 못 넣는다.
    """
    print("\n[23] 쓰러진 자리에 누구를 낼까")
    import random

    def B(name):
        return calc.popular_build(dex, dex.find_pokemon(name))[0]

    bt = battle.Battle(
        dex, [B("메가보만다"), B("따라큐"), B("누리레느"), B("킬라플로르")],
        [B("브리두라스")], rng=random.Random(1))
    mimi = bt.me_party.members[1]
    mimi.hp = int(mimi.max_hp * 0.3)          # 따라큐는 HP 30% 로 깎아 둔다
    foe = bt.opp
    score = {}
    for i, side in bt.me_party.bench():
        score[side.name] = bt.replacement_score(bt.me_party, side, foe)

    hp_pick = max(bt.me_party.bench(), key=lambda x: x[1].hp_ratio)[1].name
    real_pick = bt.me_party.members[bt.choose_replacement(bt.me_party)].name
    check("HP 순으로는 누리레느(100%)를 고르게 된다",
          hp_pick == "누리레느", hp_pick)
    check("실제로는 그놈을 안 고른다 — HP 만으로 정하지 않는다",
          real_pick != "누리레느", real_pick)
    check("HP 30% 따라큐가 HP 100% 누리레느보다 높게 쳐진다",
          score["따라큐(둔갑한 모습)"] > score["누리레느"],
          "%.2f vs %.2f" % (score["따라큐(둔갑한 모습)"], score["누리레느"]))

    # 탈이 벗겨지면 값이 떨어진다 (같은 HP 인데도)
    before = bt.replacement_score(bt.me_party, mimi, foe)
    mimi.disguise = False
    after = bt.replacement_score(bt.me_party, mimi, foe)
    check("탈이 벗겨지면 같은 HP 라도 값이 떨어진다", after < before,
          "%.2f -> %.2f" % (before, after))

    # 나오자마자 압정에 죽는 놈은 최하
    bt2 = battle.Battle(dex, [B("메가보만다"), B("메가보만다")], [B("브리두라스")],
                        rng=random.Random(1))
    bt2.me_party.hazards["스텔스록"] = 1
    weak = bt2.me_party.members[1]
    weak.hp = 1
    check("압정에 죽을 놈은 최하로 친다",
          bt2.replacement_score(bt2.me_party, weak, bt2.opp) < 0,
          bt2.replacement_score(bt2.me_party, weak, bt2.opp))

    # 판단 근거가 로그에 남는다
    bt3 = battle.Battle(dex, [B("메가보만다"), B("따라큐")], [B("브리두라스")],
                        rng=random.Random(1), log=True)
    bt3.me_party.members[0].hp = 0
    bt3._replace_fainted()
    check("왜 그놈을 골랐는지 로그에 남는다",
          any("누구를 낼까" in r for r in bt3.log), bt3.log[-2:])


def test_selection(dex):
    """6단계 — 선출. 4마리로 줄여서 빠르게만 확인한다."""
    print("\n[24] 선출 (6마리 중 3마리)")

    names = ["메가보만다", "고릴타", "아머까오", "따라큐"]
    foes = ["하마돈", "브리두라스", "누리레느", "갑주무사"]
    my4 = [calc.popular_build(dex, dex.find_pokemon(n))[0] for n in names]
    op4 = [calc.popular_build(dex, dex.find_pokemon(n))[0] for n in foes]

    table = selection.pairwise(dex, my4, op4, trials=6)
    pairs = {k: v for k, v in table.items() if k != "_named"}
    check("1대1 상성표가 %d쌍 다 찬다" % (len(my4) * len(op4)),
          len(pairs) == len(my4) * len(op4), len(pairs))
    check("승률은 0~1 사이", all(0.0 <= v <= 1.0 for v in pairs.values()))
    # ! 이름표를 같이 들고 다녀야 한다. 없으면 조합마다 `evaluate` 안에서
    #   3x3 상성표를 새로 재는데, 그게 조합당 225판이라 400조합을 훑는
    #   선출에서 예산이 4배로 터진다 (45초로 잡은 것이 199초 나왔다).
    check("조합에 물려줄 이름표도 같이 들고 다닌다",
          isinstance(table.get("_named"), dict)
          and (my4[0].name, op4[0].name) in table["_named"],
          list(table.get("_named", {}))[:2])

    matrix, my_trios, opp_trios = selection.selection_matrix(
        dex, my4, op4, table, trials=4)
    check("4마리면 조합이 4가지씩", len(my_trios) == 4 and len(opp_trios) == 4,
          "%d x %d" % (len(my_trios), len(opp_trios)))
    check("조합 %d개를 다 돌린다" % (len(my_trios) * len(opp_trios)),
          len(matrix) == len(my_trios) * len(opp_trios), len(matrix))

    rows = selection.rank_selections(matrix, my_trios, opp_trios)
    check("최악 <= 평균 <= 최고",
          all(r["worst"] <= r["mean"] + 1e-9 <= r["best"] + 1e-9 for r in rows))
    check("제일 곤란한 상대 선출을 짚어 준다",
          all(r["worstAgainst"] in opp_trios for r in rows))
    txt = selection.report(my4, op4, table, rows, my_trios, opp_trios,
                           matrix, 4)
    check("보고서가 나온다", "어떤 3마리를 낼까" in txt)

    # ★ **판수를 쌓는다.** 같은 칸을 두 번 돌리면 판수가 더해져야지
    #    덮어써지면 안 된다. 덮어써도 숫자는 멀쩡해 보인다.
    acc = {}
    selection.selection_matrix(dex, my4, op4, table, trials=3, acc=acc)
    selection.selection_matrix(dex, my4, op4, table, trials=3, acc=acc,
                               seed=77)
    check("같은 칸을 두 번 돌리면 판수가 쌓인다 (%d판)"
          % list(acc.values())[0][1],
          all(v[1] == 6 for v in acc.values()),
          sorted(set(v[1] for v in acc.values())))

    # ★ **예산을 지키는가.** 여기가 틀리면 팀 프리뷰 제한시간을 넘겨서
    #    쓸모가 없어진다. 한 번 크게 틀렸다 — 45초로 잡은 것이 199초
    #    걸렸다. 조합마다 드는 고정비를 안 세고 한 점으로만 쟀던 탓이다.
    import time
    t0 = time.time()
    got = selection.choose(dex, my4, op4, seconds=12.0, seed=3)
    took = time.time() - t0
    check("예산 12초 안에 끝난다 (%.1f초)" % took, took <= 12.0 * 1.35, took)
    check("예산을 그냥 흘려보내지도 않는다 (%.1f초)" % took, took >= 12.0 * 0.5,
          took)
    check("조합을 하나도 빠뜨리지 않았다 (%d가지)" % got["combos"],
          got.get("missing", 0) == 0, got.get("missing"))
    check("조합당 판수를 적어 준다 (%d판)" % got["trials"],
          got["trials"] >= selection.MIN_TRIALS, got["trials"])
    short = selection.short_report(dex, my4, op4, got)
    check("짧은 보고서가 나온다", "선출" in short and "최악 기준" in short)
    check("짧은 보고서가 오차를 같이 말한다", "±" in short, short)
    check("상대 배분을 사용률로 봤다는 것을 밝힌다", "사용률" in short, short)


def test_opponent_switching(dex):
    """상대도 빠진다.

    전에는 상대가 죽을 때까지 절대 안 빠졌다. 그러면 내 승률이 실제보다
    한참 높게 나온다 — 재 보니 한 대면에서 59.2% -> 3.6% 까지 벌어졌다.

    빼는 판단은 **어림셈이 아니라 미리 잰 1대1 승률**로 한다.
    한 번의 교환만 보는 어림셈으로는 '한 대 맞고 들어가면 손해' 로만 보여서
    확실히 이기는 카운터도 안 꺼내게 된다.
    """
    print("\n[25] 상대도 빠진다")
    import random

    def B(name):
        return calc.popular_build(dex, dex.find_pokemon(name))[0]

    me = [B("한카리아스"), B("따라큐"), B("킬가르도")]
    op = [B("갑주무사"), B("루카리오"), B("드닐레이브")]

    table = battle.matchup_table(dex, me, op, trials=15)
    check("1대1 표가 양방향으로 다 찬다",
          len(table) == 2 * len(me) * len(op), len(table))
    a, b = me[0].name, op[0].name
    check("서로 반대 방향은 합이 1",
          abs(table[(a, b)] + table[(b, a)] - 1.0) < 1e-9)

    opp_plan, _, _ = battle.opponent_plan(dex, op, me)
    plan = battle.build_plans(dex, me, op)[0][0]

    def run(switch, tbl):
        rng = random.Random(4)
        win = 0
        for _ in range(60):
            r = battle.run_once(dex, me, op, plan, opp_plan, rng,
                                opp_switch=switch, matchup=tbl)
            if r["result"] == "이김":
                win += 1
        return win / 60.0

    off = run(False, None)
    on = run(True, table)
    check("상대가 빠지면 내 승률이 내려간다 (%.0f%% -> %.0f%%)"
          % (off * 100, on * 100), on < off, "%.2f vs %.2f" % (off, on))

    # 상대가 이미 유리하면 굳이 안 뺀다
    me2 = [B("누리레느"), B("아머까오")]
    op2 = [B("메가보만다"), B("한카리아스")]
    t2 = battle.matchup_table(dex, me2, op2, trials=15)
    bt = battle.Battle(dex, me2, op2, rng=random.Random(1), matchup=t2)
    if t2[(op2[0].name, me2[0].name)] >= 0.9:
        check("상대 리드가 이미 이기고 있으면 안 뺀다",
              bt.should_switch(bt.opp_party) is None,
              bt.should_switch(bt.opp_party))


def test_sensitivity(dex):
    """가정값을 흔들어 보고 답이 바뀌는지 재는 도구가 도는가."""
    print("\n[26] 가정값 감도")
    rows, setups = sensitivity.measure(dex, [("고릴타", "하마돈")], trials=20)
    check("가정값 %d개를 다 재 본다" % len(sensitivity.ALTERNATIVES),
          len(rows) == len(sensitivity.ALTERNATIVES), len(rows))
    check("재고 나서 CONFIG 를 원래대로 돌려놓는다",
          calc.CONFIG["stab"] == 1.5 and calc.CONFIG["crit_rate"] == 1 / 24.0,
          (calc.CONFIG["stab"], calc.CONFIG["crit_rate"]))
    check("흔들림은 0~1 사이", all(0.0 <= r["swing"] <= 1.0 for r in rows))
    txt = sensitivity.report(rows, setups, 20)
    check("보고서가 나온다", "무엇을 먼저 실측" in txt)


def test_crit_rules(dex):
    """급소는 기술마다 다르다 — 설명문에 적혀 있는 것을 그대로 읽는다."""
    print("\n[27] 급소 규칙")
    by_name = dict((m["name"], m) for m in dex.moves)

    always = [m["name"] for m in dex.moves if calc.move_crit(m)[0]]
    staged = [m["name"] for m in dex.moves
              if not calc.move_crit(m)[0] and calc.move_crit(m)[1]]
    check("'반드시 급소' 기술을 찾아낸다 (%d개)" % len(always),
          "트릭플라워" in always and "얼음숨결" in always, always)
    check("'급소업' 기술을 찾아낸다 (%d개)" % len(staged),
          "섀도클로" in staged and "스톤에지" in staged, staged[:5])

    check("반드시 급소면 확률 1.0",
          calc.crit_chance(by_name["트릭플라워"]) == 1.0)
    check("급소업+1 은 기본보다 높다",
          calc.crit_chance(by_name["섀도클로"])
          > calc.crit_chance(by_name["지진"]))
    check("아무 표기 없으면 기본 확률",
          calc.crit_chance(by_name["지진"]) == calc.CONFIG["crit_rate"])
    # 사용자가 확인해 줌 (나무위키 '포켓몬스터/랭크' 2.1.3, 7세대 이후 — 2026-09-22)
    check("급소 단계별 확률이 확인된 값이다 (0단계 1/24 · +1 1/8 · +2 1/2 · +3 100%)",
          calc.CONFIG["crit_stage_rates"] == [1 / 24.0, 1 / 8.0, 0.5, 1.0]
          and calc.CONFIG["crit_rate"] == 1 / 24.0, calc.CONFIG["crit_stage_rates"])
    check("급소업 +3 넘게 쌓아도 100%",
          calc.crit_chance(by_name["지진"], 5) == 1.0, calc.crit_chance(by_name["지진"], 5))

    # 자속과 급소가 같이 걸리면 곱해진다 — 따로 확인해 둔 자리다.
    mas = calc.Build(dex, dex.find_pokemon("마스카나"))
    hama = calc.popular_build(dex, dex.find_pokemon("하마돈"))[0]
    tf = by_name["트릭플라워"]
    plain = calc.calc_damage(dex, mas, hama, tf)
    crit = calc.calc_damage(dex, mas, hama, tf, critical=True)
    check("트릭플라워는 자속이 붙는다 (마스카나는 풀 타입)",
          abs(plain["stab"] - calc.CONFIG["stab"]) < 1e-9, plain["stab"])
    check("자속 위에 급소가 또 곱해진다 (1.5배)",
          abs(crit["rolls"][-1] / float(plain["rolls"][-1])
              - calc.CONFIG["critical"]) < 0.02,
          (plain["rolls"][-1], crit["rolls"][-1]))

    rows = best.rate_moves(dex, mas, hama, [(tf, 100.0)])
    check("추천표도 급소 기준으로 잰다", rows[0].get("alwaysCrit") is True, rows[0])


def test_new_abilities(dex):
    """사용률 상위인데 계산에 없던 특성들."""
    print("\n[28] 뒤늦게 넣은 특성들")
    import random

    def B(name):
        return calc.popular_build(dex, dex.find_pokemon(name))[0]

    # -- 변환자재 / 리베로 : 무슨 기술을 써도 자속 -----------------------
    hama = B("하마돈")
    claw = [m for m in dex.moves if m["name"] == "섀도클로"][0]
    on = calc.Build(dex, dex.find_pokemon("마스카나"), ability="변환자재")
    off = calc.Build(dex, dex.find_pokemon("마스카나"), ability="맹화")
    a = calc.calc_damage(dex, on, hama, claw)
    b = calc.calc_damage(dex, off, hama, claw)
    check("변환자재는 비자속 기술에도 자속을 붙인다",
          a["stab"] == calc.CONFIG["stab"] and b["stab"] == 1.0,
          (a["stab"], b["stab"]))
    check("그만큼 데미지가 는다", a["rolls"][-1] > b["rolls"][-1],
          (b["rolls"][-1], a["rolls"][-1]))

    # -- 황금몸 : 상대의 변화 기술이 아예 안 통한다 -----------------------
    tabu = B("타부자고")
    check("타부자고는 황금몸", tabu.ability == "황금몸", tabu.ability)
    bt = battle.Battle(dex, hama, tabu, rng=random.Random(1), log=True)
    yawn = [m for m in dex.moves if m["name"] == "하품"][0]
    bt._use_status(bt.me, bt.opp, yawn)
    check("황금몸이 하품을 막는다",
          any("황금몸" in r for r in bt.log) and not bt.opp.drowsy, bt.log[-2:])

    # -- 미러아머 : 깎으려 한 쪽이 대신 깎인다 ---------------------------
    kkao = calc.Build(dex, dex.find_pokemon("아머까오"), ability="미러아머")
    gyara = calc.Build(dex, dex.find_pokemon("갸라도스"), ability="위협")
    bt = battle.Battle(dex, gyara, kkao, rng=random.Random(1), log=True)
    check("미러아머는 위협을 되돌린다",
          bt.opp.ranks["attack"] == 0 and bt.me.ranks["attack"] == -1,
          (bt.me.ranks["attack"], bt.opp.ranks["attack"]))
    check("로그에 남는다", any("미러아머" in r for r in bt.log), bt.log[:3])

    # 하얀연기 계열은 그냥 안 깎이기만 한다 (되돌리지 않는다)
    smoke = calc.Build(dex, dex.find_pokemon("아머까오"), ability="클리어바디")
    bt = battle.Battle(dex, gyara, smoke, rng=random.Random(1))
    check("클리어바디는 안 깎이되 되돌리지는 않는다",
          bt.opp.ranks["attack"] == 0 and bt.me.ranks["attack"] == 0,
          (bt.me.ranks["attack"], bt.opp.ranks["attack"]))

    # -- 독치장 : 물리로 때리면 때린 쪽에 독압정 -------------------------
    killa = B("킬라플로르")
    check("킬라플로르는 독치장", killa.ability == "독치장", killa.ability)
    bt = battle.Battle(dex, B("한카리아스"), killa, rng=random.Random(1), log=True)
    quake = [m for m in dex.moves if m["name"] == "지진"][0]
    bt._hit(bt.me, bt.opp, quake, None)
    check("물리로 때리면 때린 쪽에 독압정이 깔린다",
          bt.me_party.hazards.get("독압정"), bt.me_party.hazards)
    # 특수로 때리면 안 깔린다
    bt2 = battle.Battle(dex, B("한카리아스"), killa, rng=random.Random(1))
    flame = [m for m in dex.moves if m["name"] == "화염방사"][0]
    bt2._hit(bt2.me, bt2.opp, flame, None)
    check("특수로 때리면 안 깔린다", not bt2.me_party.hazards.get("독압정"),
          bt2.me_party.hazards)

    # -- 위기회피 : 반피가 되면 스스로 물러난다 --------------------------
    gap = calc.Build(dex, dex.find_pokemon("갑주무사"), ability="위기회피")
    bt = battle.Battle(dex, [gap, hama], B("메가보만다"),
                       rng=random.Random(1), log=True)
    bt.me.hp = bt.me.max_hp // 2
    bt._emergency_exit()
    check("HP 가 반 이하면 스스로 물러난다", bt.me.name != "갑주무사", bt.me.name)
    check("왜 빠졌는지 로그에 남는다",
          any("위기회피" in r for r in bt.log), bt.log[-3:])

def test_forms(dex):
    """1-A — 형태를 가른다. 채용률을 '따로따로' 에서 '같이' 로."""
    print("\n[29] 형태 추론")
    import random

    chomp = dex.find_pokemon("한카리아스")
    mv = lambda n: dex.find_move(n)

    # -- 무슨 능력치로 때리는가 ------------------------------------------
    check("지진은 공격으로 때린다", forms.attack_stat(mv("지진")) == "attack")
    check("용성군은 특수공격으로 때린다",
          forms.attack_stat(mv("용성군")) == "spAtk")
    check("바디프레스는 방어로 때린다 (설명문에서 읽는다)",
          forms.attack_stat(mv("바디프레스")) == "defense")
    check("변화기는 때리는 능력치가 없다",
          forms.attack_stat(mv("스텔스록")) is None)
    # 사이코쇼크는 '상대의 방어' 기준이라 내 능력치는 그대로 특수공격이다
    check("사이코쇼크는 상대 방어 기준일 뿐 내 쪽은 특공",
          forms.attack_stat(mv("사이코쇼크")) == "spAtk")

    # -- 데미지가 목적이 아닌 기술 ---------------------------------------
    check("드래곤테일은 형태로 가르면 안 된다 (강제 교체가 목적)",
          forms.form_neutral(mv("드래곤테일")))
    check("지진은 형태로 가른다", not forms.form_neutral(mv("지진")))

    # -- 배분 -> 형태 ----------------------------------------------------
    check("공격만 부으면 A형",
          forms.spread_class({"attack": 32}) == "A")
    check("공격+스피드면 AS형 (사용자가 쓰는 그 표기다)",
          forms.spread_class({"attack": 32, "speed": 32}) == "AS")
    check("특공+스피드면 CS형",
          forms.spread_class({"spAtk": 32, "speed": 32}) == "CS")
    check("둘 다면 AC형",
          forms.spread_class({"attack": 32, "spAtk": 32}) == "AC")
    check("둘 다 안 부으면 내구형", forms.spread_class({}) == "-")
    check("조금만 부은 건 투자로 안 친다",
          forms.spread_class({"attack": 2}) == "-")
    check("기술은 스피드 축을 안 본다 — AS형과 A형은 같은 기술",
          forms.attack_part("AS") == forms.attack_part("A") == "A")
    check("스피드만 부은 건 때리는 쪽으로는 내구형",
          forms.attack_part("S") == "-")

    w = forms.class_weights(dex, chomp)
    check("형태 비중의 합이 1", abs(sum(w.values()) - 1.0) < 1e-9, w)

    # -- 합격 조건: 갈라 놓고도 원본이 나온다 -----------------------------
    worst = 0.0
    for name in ("한카리아스", "보만다", "하마돈", "누리레느", "망나뇽",
                 "킬가르도", "갑주무사", "따라큐"):
        worst = max(worst, forms.mix_error(dex, dex.find_pokemon(name)))
    check("섞으면 원래 채용률이 그대로 나온다 (최대 %.3f%%p)" % (worst * 100),
          worst < 0.005, worst)

    # -- 실제로 갈리는가 -------------------------------------------------
    classes, weights, moves, table = forms.conditional_table(dex, chomp)
    idx = dict((m["name"], j) for j, m in enumerate(moves))
    phys = classes.index("AS")
    spec = classes.index("CS")
    check("특수형이 물리형보다 용성군을 많이 든다",
          table[spec][idx["용성군"]] > table[phys][idx["용성군"]] + 0.20,
          (table[phys][idx["용성군"]], table[spec][idx["용성군"]]))
    check("물리형이 특수형보다 역린을 많이 든다",
          table[phys][idx["역린"]] > table[spec][idx["역린"]] + 0.20,
          (table[phys][idx["역린"]], table[spec][idx["역린"]]))
    check("드래곤테일은 형태로 안 갈린다",
          abs(table[phys][idx["드래곤테일"]]
              - table[spec][idx["드래곤테일"]]) < 0.10,
          (table[phys][idx["드래곤테일"]], table[spec][idx["드래곤테일"]]))

    # 어느 형태든 이 목록에서 쓰는 칸수는 같다 (누구나 기술칸 4개)
    sums = [sum(row) for row in table]
    check("형태마다 쓰는 칸수가 같다 (%.2f ~ %.2f)" % (min(sums), max(sums)),
          max(sums) - min(sums) < 0.05, sums)

    # -- 형태가 하나뿐이면 갈리지 않는다 ---------------------------------
    hama = dex.find_pokemon("하마돈")
    hclasses, hweights, hmoves, htable = forms.conditional_table(dex, hama)
    check("하마돈은 전부 내구형이라 갈릴 것이 없다",
          hclasses == ["-"], hclasses)

    # -- 본 것으로 형태가 좁혀진다 ---------------------------------------
    base = forms.form_posterior(dex, chomp, set())
    check("본 것이 없으면 사전 분포 그대로",
          abs(base["CS"] - w["CS"]) < 1e-9, (base["CS"], w["CS"]))
    after = forms.form_posterior(dex, chomp, {"용성군"})
    check("용성군을 보면 CS형 쪽으로 쏠린다 (%.0f%% -> %.0f%%)"
          % (base["CS"] * 100, after["CS"] * 100),
          after["CS"] > base["CS"] + 0.15, (base["CS"], after["CS"]))
    after2 = forms.form_posterior(dex, chomp, {"역린"})
    check("역린을 보면 AS형 쪽으로 쏠린다 (%.0f%% -> %.0f%%)"
          % (base["AS"] * 100, after2["AS"] * 100),
          after2["AS"] > base["AS"] + 0.15, (base["AS"], after2["AS"]))

    # 도구를 봐도 형태가 좁혀진다 — 메가 종족값이 세다
    char = dex.find_pokemon("리자몽")
    cbase = forms.form_posterior(dex, char, set())
    cy = forms.form_posterior(dex, char, set(), item="리자몽나이트Y")
    cx = forms.form_posterior(dex, char, set(), item="리자몽나이트X")
    check("메가리자몽Y(특공159)를 보면 CS형 쪽 (%.0f%% -> %.0f%%)"
          % (cbase["CS"] * 100, cy["CS"] * 100),
          cy["CS"] > cbase["CS"], (cbase["CS"], cy["CS"]))
    check("메가리자몽X(공격=특공)는 Y보다 AS형 쪽",
          cx["AS"] > cy["AS"], (cx["AS"], cy["AS"]))

    # -- 안 본 기술의 확률까지 같이 움직인다 (1-A 의 수확) ----------------
    ev = scout.Evidence(seen_moves={"용성군"})
    before = dict((m["name"], p) for m, p in scout.move_probabilities(dex, chomp))
    now = dict((m["name"], p)
               for m, p in scout.narrowed_probabilities(dex, chomp, ev))
    check("용성군을 보면 지진 확률이 내려간다 (%.0f%% -> %.0f%%)"
          % (before["지진"] * 100, now["지진"] * 100),
          now["지진"] < before["지진"] - 0.05,
          (before["지진"], now["지진"]))
    check("같이 화염방사 확률은 올라간다 (%.0f%% -> %.0f%%)"
          % (before["화염방사"] * 100, now["화염방사"] * 100),
          now["화염방사"] > before["화염방사"] + 0.03,
          (before["화염방사"], now["화염방사"]))
    check("본 기술 자체는 100%", abs(now["용성군"] - 1.0) < 1e-9)

    # -- 뽑아 보면 형태와 기술이 어긋나지 않는다 --------------------------
    rng = random.Random(11)
    cnt = {"A": [0, 0.0], "C": [0, 0.0]}
    for _ in range(600):
        b, ms = scout.sample_opponent(dex, chomp, rng)
        # 기술은 스피드 축과 무관하므로 때리는 쪽만 본다 (AS -> A)
        cls = forms.attack_part(forms.spread_class(b.sp))
        if cls not in cnt:
            continue
        cnt[cls][0] += 1
        cnt[cls][1] += sum(1 for m in ms if m["category"] == "특수")
    ratio_a = cnt["A"][1] / max(1, cnt["A"][0])
    ratio_c = cnt["C"][1] / max(1, cnt["C"][0])
    check("뽑힌 특수형이 물리형보다 특수기를 많이 든다 (%.2f vs %.2f)"
          % (ratio_a, ratio_c), ratio_c > ratio_a + 0.5, (ratio_a, ratio_c))

    # -- 갈라 놓고도 전체 채용률이 재현된다 (최종 확인) -------------------
    rows = scout.check_joint(dex, chomp, trials=3000, seed=4)
    err = max(abs(a - b) for _, a, b in rows)
    check("뽑은 결과를 다 세면 원래 채용률로 돌아온다 (오차 %.1f%%p)" % err,
          err < 3.0, [(n, round(a, 1), round(b, 1)) for n, a, b in rows[:3]])

def test_forms_body(dex):
    """성격·도구도 형태에 딸려 온다 (1-A 확장)."""
    print("\n[30] 형태에 딸린 성격과 도구")
    import random

    chomp = dex.find_pokemon("한카리아스")
    char = dex.find_pokemon("리자몽")

    # -- 성격은 규칙이다 --------------------------------------------------
    jolly = dex.find_nature("고집")      # 공격+ / 특공-
    timid = dex.find_nature("겁쟁이")    # 스피드+ / 공격-
    check("고집(특공-)은 CS형에 안 맞는다",
          forms.nature_compat("CS", jolly) < 0.5, forms.nature_compat("CS", jolly))
    check("고집은 AS형에 맞는다",
          forms.nature_compat("AS", jolly) == 1.0)
    check("겁쟁이(공격-)는 AS형에 안 맞는다",
          forms.nature_compat("AS", timid) < 0.5)
    check("겁쟁이는 CS형에 맞는다",
          forms.nature_compat("CS", timid) == 1.0)
    check("안 쓰는 쪽을 깎는 건 정상이다 (CS형이 공격을 깎는 것)",
          forms.nature_compat("CS", timid) == 1.0)

    nclasses, nentries, ntable = forms.nature_table(dex, chomp)
    nidx = dict((e["name"], j) for j, e in enumerate(nentries))
    a, c = nclasses.index("AS"), nclasses.index("CS")
    check("AS형이 고집을 훨씬 많이 쓴다",
          ntable[a][nidx["고집"]] > ntable[c][nidx["고집"]] + 0.15,
          (ntable[a][nidx["고집"]], ntable[c][nidx["고집"]]))
    check("CS형이 겁쟁이를 훨씬 많이 쓴다",
          ntable[c][nidx["겁쟁이"]] > ntable[a][nidx["겁쟁이"]] + 0.15,
          (ntable[c][nidx["겁쟁이"]], ntable[a][nidx["겁쟁이"]]))
    check("형태마다 성격 확률의 합이 1",
          all(abs(sum(r) - 1.0) < 1e-6 for r in ntable))

    # -- 도구 경향은 데이터에서 잰 것이다 ---------------------------------
    tend = forms.item_tendency(dex)
    check("도구 경향을 %d종에 대해 쟀다" % len(tend), len(tend) >= 10)
    lefto = tend.get("먹다남은음식", {})
    scarf = tend.get("구애스카프", {})
    check("먹다남은음식은 내구형과 양의 상관 (%.2f)" % lefto.get("-", 0),
          lefto.get("-", 0) > 0.3, lefto)
    check("구애스카프는 내구형과 음의 상관 (%.2f)" % scarf.get("-", 0),
          scarf.get("-", 0) < 0.0, scarf)
    check("풍선은 아무 경향이 없다 — 이 측정은 다 맞다고 해 주지 않는다",
          abs(tend.get("풍선", {}).get("-", 0)) < 0.2,
          tend.get("풍선", {}).get("-", 0))

    iclasses, ientries, itable = forms.item_table(dex, chomp)
    iidx = dict((e["name"], j) for j, e in enumerate(ientries))
    ia, ic = iclasses.index("AS"), iclasses.index("-")
    check("내구형이 자뭉열매를 더 든다",
          itable[ic][iidx["자뭉열매"]] > itable[ia][iidx["자뭉열매"]],
          (itable[ia][iidx["자뭉열매"]], itable[ic][iidx["자뭉열매"]]))
    check("AS형이 구애스카프를 더 든다",
          itable[ia][iidx["구애스카프"]] > itable[ic][iidx["구애스카프"]],
          (itable[ia][iidx["구애스카프"]], itable[ic][iidx["구애스카프"]]))

    # -- 메가스톤은 상관이 아니라 종족값이 정한다 -------------------------
    cclasses, centries, ctable = forms.item_table(dex, char)
    cidx = dict((e["name"], j) for j, e in enumerate(centries))
    ca, cc = cclasses.index("AS"), cclasses.index("CS")
    check("메가리자몽Y(특공159)는 CS형이 더 든다",
          ctable[cc][cidx["리자몽나이트Y"]] > ctable[ca][cidx["리자몽나이트Y"]],
          (ctable[ca][cidx["리자몽나이트Y"]], ctable[cc][cidx["리자몽나이트Y"]]))
    check("메가리자몽X(공격=특공)는 AS형이 더 든다",
          ctable[ca][cidx["리자몽나이트X"]] > ctable[cc][cidx["리자몽나이트X"]],
          (ctable[ca][cidx["리자몽나이트X"]], ctable[cc][cidx["리자몽나이트X"]]))

    # -- 갈라 놓고도 원래 채용률이 나온다 ---------------------------------
    worst = 0.0
    for nm in ("한카리아스", "리자몽", "보만다", "누리레느", "망나뇽", "하마돈"):
        pk = dex.find_pokemon(nm)
        worst = max(worst, forms.pick_error(dex, pk, "natures"),
                    forms.pick_error(dex, pk, "items"))
    check("성격·도구도 섞으면 원래 채용률로 돌아온다 (%.3f%%p)" % (worst * 100),
          worst < 0.005, worst)

    # -- 뽑아 보면 어긋난 놈이 줄어 있다 ----------------------------------
    def mismatch(strength):
        old = calc.CONFIG["nature_mismatch"]
        calc.CONFIG["nature_mismatch"] = strength
        forms._PICK_CACHE.clear()
        try:
            rng = random.Random(5)
            tot = bad = 0
            for nm in ("한카리아스", "보만다", "리자몽", "망나뇽"):
                pk = dex.find_pokemon(nm)
                for _ in range(500):
                    b, _m = scout.sample_opponent(dex, pk, rng)
                    if not b.nature:
                        continue
                    tot += 1
                    ap = forms.attack_part(forms.spread_class(b.sp))
                    d = b.nature.get("down")
                    if ((d == "attack" and ap in ("A", "AC"))
                            or (d == "spAtk" and ap in ("C", "AC"))):
                        bad += 1
            return bad * 100.0 / max(1, tot)
        finally:
            calc.CONFIG["nature_mismatch"] = old
            forms._PICK_CACHE.clear()

    before, after = mismatch(1.0), mismatch(calc.CONFIG["nature_mismatch"])
    check("자기 공격력을 깎는 성격이 줄었다 (%.0f%% -> %.0f%%)" % (before, after),
          after < before * 0.4, (before, after))

def _fake_parties(dex, truth, n=24, seed=1, pokes=None):
    """정답을 아는 가짜 표본. 맞추기가 그 값을 되찾는지 보려고 만든다.

    ! **갈래 모델(1-C)을 끄고 만든다.** 안 끄면 조용히 딴 것을 재게 된다 —
      scout 는 표본이 있는 포켓몬이면 (형태 x 갈래) 표로 기술을 뽑는데,
      `samples.loglik` 은 1-A 의 형태별 표로 가능도를 매긴다. 생성기와
      추정기가 다른 모델이 되어, 정답 0.05 를 넣었는데 0.005 가 (그것도
      25.0 이라는 큰 차이로) 나왔다. 1-C 를 넣은 뒤 이 검증이 계속
      통과하고 있었던 것은 한 칸 이내 허용 때문이었다.

      form_mismatch 는 **1-A 의 계수**이므로 1-A 모델에서 재는 것이 맞다.
      1-C 표로 재면 그 표가 표본에서 나온 것이라 같은 자료를 두 번 쓰게 된다.
    """
    import random

    import combos
    pokes = pokes or ["한카리아스", "보만다", "리자몽", "망나뇽"]
    old = dict((k, calc.CONFIG[k]) for k in samples.KNOBS)
    keep_min = combos.MIN_SAMPLES
    combos.MIN_SAMPLES = 10 ** 9          # 갈래 모델을 끈다
    combos._CACHE.clear()
    combos._BY_FORM.clear()
    combos._FULL.clear()
    calc.CONFIG.update(truth)
    samples._clear()
    scout._WEIGHT_CACHE.clear()
    rng = random.Random(seed)
    parties = []
    try:
        for i in range(n):
            mem = []
            for nm in pokes:
                b, mv = scout.sample_opponent(dex, dex.find_pokemon(nm), rng)
                evs = dict((k, b.sp[ko]) for k, ko in calc.SPREAD_KEY.items()
                           if b.sp.get(ko, 0) > 0)
                mem.append({"name": nm, "item": b.item,
                            "nature": (b.nature or {}).get("name"),
                            "ability": b.ability, "evs": evs,
                            "moves": [x["name"] for x in mv]})
            parties.append({"season": 6, "rank": i + 1, "members": mem})
    finally:
        calc.CONFIG.update(old)
        combos.MIN_SAMPLES = keep_min
        combos._CACHE.clear()
        combos._BY_FORM.clear()
        combos._FULL.clear()
        samples._clear()
        scout._WEIGHT_CACHE.clear()
    return {"parties": parties}


def test_samples(dex):
    """1-B — 구축기사 표본을 받아 조합을 배운다."""
    print("\n[31] 구축기사 표본")
    import json
    import os
    import tempfile

    def write(doc):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        return path

    # -- 노력치 표기 ------------------------------------------------------
    check("노력치를 dict 로 받는다",
          samples.parse_evs({"A": 32, "S": 32}) == {"A": 32, "S": 32})
    check("노력치를 'A32 S32' 로도 받는다",
          samples.parse_evs("A32 S32") == {"A": 32, "S": 32})
    check("'H32/B32' 처럼 빗금도 받는다",
          samples.parse_evs("H32/B32") == {"H": 32, "B": 32})
    check("0 은 버린다", samples.parse_evs({"A": 32, "B": 0}) == {"A": 32})

    # -- 일본어 이름이 이어지는가 -----------------------------------------
    jp = {"parties": [{"season": 6, "rank": 3, "url": "테스트", "members": [
        {"name": "ガブリアス", "item": "こだわりスカーフ", "ability": "さめはだ",
         "nature": "いじっぱり", "evs": {"A": 32, "S": 32},
         "moves": ["じしん", "げきりん", "スケイルショット", "ドラゴンテール"]},
        {"name": "ボーマンダ", "item": "ボーマンダナイト", "nature": "いじっぱり",
         "evs": "A32 S32",
         "moves": ["すてみタックル", "りゅうのまい", "じしん", "はねやすめ"]}]}]}
    path = write(jp)
    try:
        parties, bad = samples.load(dex, path)
    finally:
        os.unlink(path)
    check("일본어 파티가 읽힌다", len(parties) == 1 and
          len(parties[0]["members"]) == 2, parties)
    m0 = parties[0]["members"][0]
    check("포켓몬 이름이 이어진다 (ガブリアス -> 한카리아스)",
          m0["poke"]["name"] == "한카리아스", m0["poke"]["name"])
    check("도구 이름이 이어진다", m0["item"] == "구애스카프", m0["item"])
    check("성격 이름이 이어진다", m0["nature"] == "고집", m0["nature"])
    check("기술 이름이 이어진다",
          [x["name"] for x in m0["moves"]]
          == ["지진", "역린", "스케일샷", "드래곤테일"],
          [x["name"] for x in m0["moves"]])
    check("배분에서 형태가 나온다 (AS형)", m0["cls"] == "AS", m0["cls"])
    check("한국어로 넣어도 된다",
          samples.load(dex, write({"parties": [{"season": 6, "members": [
              {"name": "한카리아스", "moves": ["지진"], "evs": {"A": 32}}]}]}))[0]
          [0]["members"][0]["poke"]["name"] == "한카리아스")

    # -- 못 알아들은 이름은 조용히 버리지 않는다 --------------------------
    weird = {"parties": [{"season": 6, "members": [
        {"name": "ガブリアス", "evs": {"A": 32},
         "moves": ["じしん", "でんげきは"]},
        {"name": "존재하지않는포켓몬", "moves": [], "evs": {}}]}]}
    path = write(weird)
    try:
        parties, bad = samples.load(dex, path)
    finally:
        os.unlink(path)
    kinds = bad.summary()
    check("못 알아들은 기술을 보고한다", "기술" in kinds, kinds)
    check("못 알아들은 포켓몬을 보고한다", "포켓몬" in kinds, kinds)
    check("알아들은 것은 그대로 살린다",
          len(parties) == 1 and len(parties[0]["members"]) == 1)

    # -- 맞추기가 정답을 되찾는가 (제일 중요한 검증) ----------------------
    for truth in ({"form_mismatch": 0.05}, {"form_mismatch": 0.40}):
        doc = _fake_parties(dex, truth, n=24, seed=2)
        path = write(doc)
        try:
            parties, _ = samples.load(dex, path)
        finally:
            os.unlink(path)
        # 잴 때도 1-C 를 끈다. 가짜 표본을 1-A 로 만들었으므로 짝이 맞아야 한다.
        import combos as _cb
        _keep = _cb.MIN_SAMPLES
        _cb.MIN_SAMPLES = 10 ** 9
        _cb._CACHE.clear(); _cb._BY_FORM.clear(); _cb._FULL.clear()
        try:
            got = samples.fit(dex, parties)
        finally:
            _cb.MIN_SAMPLES = _keep
            _cb._CACHE.clear(); _cb._BY_FORM.clear(); _cb._FULL.clear()
        pick, rows = got["form_mismatch"]
        used = max(r[2] for r in rows)
        # 표본 100마리로는 한 칸 어긋날 수 있다. 정확히 맞으려면 800마리쯤
        # 필요하다 (직접 재 봤다 — samples.py 의 표본 크기 설명 참고).
        grid = samples.KNOBS["form_mismatch"]
        near = abs(grid.index(pick) - grid.index(truth["form_mismatch"])) <= 1
        check("정답 %.2f 인 가짜 표본에서 %.2f 를 되찾는다 (표본 %d, 한 칸 이내)"
              % (truth["form_mismatch"], pick, used), near, (truth, pick))

    # -- 맞추기가 CONFIG 를 원래대로 돌려놓는가 ---------------------------
    before = dict((k, calc.CONFIG[k]) for k in samples.KNOBS)
    samples.fit(dex, parties)
    check("재고 나서 CONFIG 를 원래대로 돌려놓는다",
          all(calc.CONFIG[k] == v for k, v in before.items()))

    # -- 기술 쌍 — 마진으로는 절대 안 나오는 것 ---------------------------
    doc = _fake_parties(dex, {}, n=60, seed=5, pokes=["한카리아스"])
    path = write(doc)
    try:
        parties, _ = samples.load(dex, path)
    finally:
        os.unlink(path)
    rows, n = samples.move_pairs(parties, "한카리아스")
    check("기술 쌍이 나온다 (%d마리, %d쌍)" % (n, len(rows)), rows, n)
    lift = dict(((a, b), lf) for a, b, _c, _na, _nb, _e, lf in rows)
    def get(a, b):
        return lift.get((a, b), lift.get((b, a)))
    check("기대값이 작은 쌍은 아예 안 나온다",
          all(r[5] >= 2.0 for r in rows), [r[5] for r in rows[:3]])
    both_spec = get("용성군", "화염방사")
    cross = get("용성군", "역린")
    if both_spec is not None and cross is not None:
        check("같은 쪽 기술끼리는 같이 다닌다 (용성군-화염방사 %.2f)" % both_spec,
              both_spec > cross, (both_spec, cross))
        check("반대쪽 기술끼리는 서로 안 든다 (용성군-역린 %.2f)" % cross,
              cross < 1.0, cross)

    # -- 시즌을 섞지 않는다 -----------------------------------------------
    mixed = {"parties": [
        {"season": 5, "members": [{"name": "한카리아스", "evs": {"A": 32},
                                   "moves": ["지진"]}]},
        {"season": 6, "members": [{"name": "보만다", "evs": {"A": 32},
                                   "moves": ["지진"]}]}]}
    path = write(mixed)
    try:
        parties, _ = samples.load(dex, path)
    finally:
        os.unlink(path)
    check("시즌으로 걸러낼 수 있다",
          len(list(samples.members(parties, season=6))) == 1
          and len(list(samples.members(parties))) == 2)

    # -- 기사 값어치 (사용자 판단이라 숫자를 따로 모아 뒀다) --------------
    champs = {"source": "champs", "rank": 12}
    sol = {"source": "pokesol", "rank": 12}
    check("champs 기사를 더 무겁게 본다",
          samples.party_weight(champs) > samples.party_weight(sol),
          (samples.party_weight(champs), samples.party_weight(sol)))
    check("주소만 있어도 어디서 왔는지 안다",
          samples.source_of({"url": "https://champs.pokedb.tokyo/article/1"})
          == "champs")
    check("pokesol 주소도 알아본다",
          samples.source_of({"url": "https://pokesol.app/u/a/articles/b"})
          == "pokesol")
    check("순위를 안 밝힌 글은 반만 친다",
          samples.party_weight({"source": "pokesol"})
          < samples.party_weight({"source": "pokesol", "rank": 9999}),
          (samples.party_weight({"source": "pokesol"}),
           samples.party_weight({"source": "pokesol", "rank": 9999})))
    check("상위 순위일수록 무겁다",
          samples.party_weight({"source": "pokesol", "rank": 1})
          > samples.party_weight({"source": "pokesol", "rank": 300})
          > samples.party_weight({"source": "pokesol", "rank": 9999}))

    # 값어치가 실제로 맞추기에 반영되는가 — champs 표본 쪽으로 끌려가야 한다
    a = _fake_parties(dex, {"form_mismatch": 0.001}, n=10, seed=3)
    b = _fake_parties(dex, {"form_mismatch": 1.0}, n=10, seed=4)
    for party in a["parties"]:
        party["source"], party["rank"] = "champs", 1
    for party in b["parties"]:
        party["source"] = "pokesol"
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"parties": a["parties"] + b["parties"]}, f,
                  ensure_ascii=False)
    try:
        mixed, _ = samples.load(dex, path)
    finally:
        os.unlink(path)
    grid = samples.KNOBS["form_mismatch"]
    pick_mixed = samples.fit(dex, mixed)["form_mismatch"][0]
    old_w = dict(samples.SOURCE_WEIGHT)
    try:
        samples.SOURCE_WEIGHT["champs"] = 1.0    # 값어치를 껐을 때와 비교
        pick_flat = samples.fit(dex, mixed)["form_mismatch"][0]
    finally:
        samples.SOURCE_WEIGHT.clear()
        samples.SOURCE_WEIGHT.update(old_w)
    check("champs 표본 쪽으로 끌려간다 (%.3f vs 값어치 끄면 %.3f)"
          % (pick_mixed, pick_flat),
          grid.index(pick_mixed) <= grid.index(pick_flat),
          (pick_mixed, pick_flat))

    # -- 표본이 없어도 안 죽는다 ------------------------------------------
    empty, bad2 = samples.load(dex, "/그런/파일/없음.json")
    check("표본 파일이 없어도 그냥 빈 목록", empty == [] and len(bad2) == 0)
    check("보고서가 나온다", "구축기사" in samples.report(dex, empty, bad2))

def test_fetch_pokesol(dex):
    """구축기사에서 파티를 꺼내는 부분 (pokesol.app)."""
    print("\n[32] 기사에서 파티 꺼내기")
    import fetch_pokesol as fp

    # -- turbo-stream 풀기 -------------------------------------------------
    # 납작한 배열에 값이 있고 객체는 번호로 서로를 가리킨다.
    flat = ["ROOT", "name", "한카리아스", "n", 42, ["D", 1789554238536],
            ["M", 1, 2], {"_1": 2, "_3": 4}, {"_1": 5}, {"_1": 6}]
    got = fp.unflatten(["ignored"] + flat[:0] or flat)  # flat[0] 이 루트
    check("번호를 따라가서 객체를 만든다",
          fp.unflatten([{"_1": 2}, "name", "한카리아스"])
          == {"name": "한카리아스"})
    check("음수는 특수값이라 None 으로",
          fp.unflatten([{"_1": -2}, "name"]) == {"name": None})
    check("['D', 숫자] 는 날짜지 번호가 아니다",
          fp.unflatten([{"_1": 2}, "at", ["D", 1789554238536]])
          == {"at": 1789554238536})
    check("['M', ...] 은 Map 이다",
          fp.unflatten([{"_1": 2}, "m", ["M", 3, 4], "k", "v"])
          == {"m": {"k": "v"}})
    check("모르는 자료형은 건드리지 않는다",
          fp.unflatten([{"_1": 2}, "x", ["??", 3], "y"]) == {"x": None})
    check("배열 안의 번호도 따라간다",
          fp.unflatten([{"_1": 2}, "xs", [3, 4], "a", "b"])
          == {"xs": ["a", "b"]})

    # -- 제목에서 시즌·룰·순위 --------------------------------------------
    cases = [
        ("【S5最終1位】臥薪嘗胆アーマーガア", 5, 1, None),
        ("【シングルM-5 最終177位 】グロス軸対面構築", None, 177, "M-5"),
        ("【最終R1978/最高R2079】S5対戦記録", 5, None, None),
        ("【M-Cマスター到達】耐久積み構築", None, None, "M-C"),
        ("ただの雑記", None, None, None),
    ]
    for title, season, rank, rule in cases:
        s, r, u = fp.title_info(title)
        check("제목 '%s' -> 시즌%s %s위 %s" % (title[:18], s, r, u),
              (s, r, u) == (season, rank, rule), (s, r, u))

    # -- 카드에서 개체를 꺼낸다 -------------------------------------------
    doc = {"routes/x": {"data": {
        "article": {
            "title": "【S6最終3位】테스트",
            "publishedAt": "2026-09-10T00:00:00.000Z",
            "body": ('<p>글</p><div data-type="pokemon-card" '
                     'data-pokemon-id="445" data-nature-id="2" '
                     'data-ability-ids="[24]" data-item-id="135" '
                     'data-move-ids="[89,525]" '
                     'data-evs="{&quot;hp&quot;:32,&quot;attack&quot;:0,'
                     '&quot;defense&quot;:22,&quot;specialAttack&quot;:0,'
                     '&quot;specialDefense&quot;:7,&quot;speed&quot;:5}">'
                     '</div>')},
        "masterData": {
            "pokemons": [{"id": 445, "name": "ガブリアス"}],
            "moves": [{"id": 89, "name": "じしん"},
                      {"id": 525, "name": "ドラゴンテール"}],
            "items": [{"id": 135, "name": "オボンのみ"}],
            "natures": [{"id": 2, "name": "いじっぱり"}],
            "abilities": [{"id": 24, "name": "さめはだ"}]}}}}
    party = fp.parse_article(doc)
    check("시즌과 순위를 읽는다",
          (party["season"], party["rank"]) == (6, 3), party)
    check("개체를 하나 꺼냈다", len(party["members"]) == 1, party)
    m = party["members"][0]
    check("이름·도구·성격·특성이 일본어로 나온다",
          (m["name"], m["item"], m["nature"], m["ability"])
          == ("ガブリアス", "オボンのみ", "いじっぱり", "さめはだ"), m)
    check("기술이 나온다", m["moves"] == ["じしん", "ドラゴンテール"], m["moves"])
    check("노력치가 숫자로 나오고 0은 빠진다",
          m["evs"] == {"H": 32, "B": 22, "D": 7, "S": 5}, m["evs"])
    check("노력치 합이 66", sum(m["evs"].values()) == 66, m["evs"])

    # 꺼낸 것이 samples.load 를 그대로 통과하는가 (두 쪽이 붙는지 확인)
    import json
    import os
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"parties": [party]}, f, ensure_ascii=False)
    try:
        parties, bad = samples.load(dex, path)
    finally:
        os.unlink(path)
    check("꺼낸 파티가 표본으로 그대로 읽힌다",
          len(parties) == 1 and len(bad) == 0, bad.summary() if bad else None)
    got = parties[0]["members"][0]
    check("일본어가 한국어로 이어진다 (ガブリアス -> 한카리아스)",
          got["poke"]["name"] == "한카리아스", got["poke"]["name"])
    check("형태가 나온다 (내구형)", got["cls"] == "-", got["cls"])

    # -- 카드가 없는 기사는 빈 파티 ---------------------------------------
    empty = fp.parse_article({"data": {"article": {"title": "글", "body": "<p>글</p>"},
                                       "masterData": {}}})
    check("카드 없는 기사는 개체가 0", empty["members"] == [], empty)

def test_combos(dex):
    """1-C — 표본으로 기술 구성을 고친다 (목록 밖 기술 + 조합)."""
    print("\n[33] 기술 구성 갈래")
    import random

    chomp = dex.find_pokemon("한카리아스")
    if combos.full_table(dex, chomp) is None:
        check("표본이 없어 갈래 모델을 건너뜀 (data/samples.json 필요)", True)
        return

    # -- 어휘: 사용률 목록 밖 기술이 되살아났는가 --------------------------
    rows = samples.by_pokemon(combos.loaded(dex)).get("한카리아스") or []
    vocab = combos.vocabulary(dex, chomp, rows)
    by = dict((mv["name"], (t, src)) for mv, t, src in vocab)
    check("사용률 목록 기술은 채용률 그대로",
          abs(by["지진"][0] - 0.670) < 1e-9, by.get("지진"))
    check("목록 밖 기술이 목록에 들어왔다 (칼춤)",
          "칼춤" in by and by["칼춤"][1] == "표본", by.get("칼춤"))
    check("목록 밖 기술도 확률이 0 이 아니다 (%.1f%%)"
          % (by["칼춤"][0] * 100), by["칼춤"][0] > 0.05)
    total = sum(t for _, t, _ in vocab)
    check("어휘 전체 채용률 합이 기술칸 4개에 맞는다 (%.2f)" % total,
          abs(total - combos.SLOTS) < 0.02, total)

    # -- 갈래를 찾았는가 --------------------------------------------------
    got = combos.archetypes(dex, chomp)
    moves, w, table, where = got
    check("갈래가 두 개 이상 나왔다 (%d개)" % len(w), len(w) >= 2, len(w))
    check("갈래 비중의 합이 1", abs(sum(w) - 1.0) < 1e-6, w)
    idx = dict((mv["name"], j) for j, mv in enumerate(moves))
    # -- 갈래를 가르는가 --------------------------------------------------
    # 자(combos.split_score)가 왜 이 모양인지는 combos.py 에 적어 두었다.
    # 여기서는 **그 자가 뒤집히지 않는지**만 못 박는다.
    rock = [table[i][idx["스텔스록"]] for i in range(len(w))]
    out = [table[i][idx["역린"]] for i in range(len(w))]
    quake = [table[i][idx["지진"]] for i in range(len(w))]
    check("스텔스록이 갈래를 가른다 (갈래도 %.1f, 문턱 %.0f)"
          % (combos.split_score(rock), combos.SPLIT_MIN),
          combos.split_score(rock) >= combos.SPLIT_MIN,
          [round(x, 3) for x in rock])
    check("역린도 갈래를 가른다 (갈래도 %.1f)" % combos.split_score(out),
          combos.split_score(out) >= combos.SPLIT_MIN,
          [round(x, 3) for x in out])
    check("스텔스록과 역린은 다른 갈래다",
          rock.index(max(rock)) != out.index(max(out)), (rock, out))
    # 지진은 **폭은 제일 넓은데 갈래를 안 가른다** — 옛 자(max-min)가
    # 거꾸로 세던 바로 그 칸이다. 되돌리면 여기서 걸린다.
    check("지진은 폭이 넓어도 갈래를 안 가른다 (폭 %.2f, 갈래도 %.1f)"
          % (max(quake) - min(quake), combos.split_score(quake)),
          max(quake) - min(quake) > 0.4
          and combos.split_score(quake) < combos.SPLIT_MIN,
          [round(x, 3) for x in quake])

    # -- 한 마리에만 맞는 자가 아닌가 (여러 종에서 확인) --------------------
    # 갈래를 둘 이상 찾았다면, 그 갈래들을 **가르는 기술이 하나는** 있어야
    # 한다. 없으면 갈래를 찾았다는 말 자체가 헛것이다.
    weak = []
    n_multi = 0
    for nm, rws2 in samples.by_pokemon(combos.loaded(dex)).items():
        if len(rws2) < combos.MIN_SAMPLES:
            continue
        try:
            pk = dex.find_pokemon(nm)
        except LookupError:
            continue
        got2 = combos.archetypes(dex, pk)
        if got2 is None or len(got2[1]) < 2:
            continue
        n_multi += 1
        best = max((combos.split_score([r[j] for r in got2[2]])
                    for j in range(len(got2[0]))), default=0.0)
        if best < combos.SPLIT_MIN:
            weak.append((nm, round(best, 1)))
    check("갈래를 찾은 %d종 모두 가르는 기술이 있다" % n_multi,
          n_multi >= 5 and not weak, weak)

    # -- 새로 생긴 형태를 조용히 넘기지 않는가 ------------------------------
    # 한카리아스Z 가 이번에 추가돼서 CS형 한카리아스는 사용률로는 36% 인데
    # 표본에는 4% 밖에 없다. 모르고 쓰면 인구의 3분의 1을 9마리로 설명하는
    # 셈이 된다. 경고가 뜨는지, 그리고 **아무 데서나 뜨지는 않는지** 본다.
    warns = combos.thin_forms(dex, chomp)
    check("한카리아스 CS형에 경고가 뜬다 (%d건)" % len(warns),
          any("CS형" in x for x in warns), warns)
    n_warn = n_spec = 0
    for nm, rws3 in samples.by_pokemon(combos.loaded(dex)).items():
        if len(rws3) < combos.MIN_SAMPLES:
            continue
        try:
            pk = dex.find_pokemon(nm)
        except LookupError:
            continue
        n_spec += 1
        n_warn += 1 if combos.thin_forms(dex, pk) else 0
    check("경고가 아무 데서나 뜨지는 않는다 (%d/%d종)" % (n_warn, n_spec),
          n_spec >= 10 and n_warn <= n_spec * 0.3, (n_warn, n_spec))

    # -- 구멍을 사용률 순서로 보는가 ---------------------------------------
    # survey() 는 표본이 많은 순서라 한카리아스가 맨 위에 온다. 그것만
    # 보고 있으면 **중요한데 표본이 없는 종**이 영영 안 보인다. 실제로
    # 그래서 이 테스트 자체가 한 마리로만 짜였다가 깨졌다.
    cov = combos.coverage(dex, top=30)
    check("덮개 표가 사용률 상위 30종을 준다 (%d종)" % len(cov),
          len(cov) >= 25, len(cov))
    check("덮개 표는 사용률 순서다 (표본 순서가 아니다)",
          [r[0] for r in cov] == sorted(r[0] for r in cov),
          [r[0] for r in cov[:5]])
    # ★ 제일 중요한 것 — **룰 신규종을 표본 구멍으로 세지 않는가.**
    # 사용률은 지금 룰(M-6) 것이고 기사는 대부분 지난 룰(M-5) 것이다.
    # 그걸 모르고 세면 M-6 에 새로 들어온 포켓몬이 전부 "표본이 없다"
    # 로 잡힌다. 실제로 그렇게 한 번 보고했다.
    parties = combos.loaded(dex)
    fresh = samples.newcomers(parties)
    check("직전 룰에 없던 종을 신규로 집어낸다 (%d종: %s)"
          % (len(fresh), ", ".join(sorted(fresh)[:4])),
          len(fresh) >= 1, sorted(fresh))
    thin = [r[1] for r in cov if r[2] < combos.MIN_SAMPLES]
    marked_fresh = [r[1] for r in cov if "신규" in r[5]]
    check("표본 얇은 상위종 중 신규종은 따로 표시된다 (%d중 %d)"
          % (len(thin), len(marked_fresh)),
          all(nm in fresh for nm in marked_fresh)
          and not any(nm in fresh and nm not in marked_fresh
                      for nm in thin),
          (thin, marked_fresh))
    check("남은 것만 진짜 표본 부족이다 (%s)"
          % ", ".join(nm for nm in thin if nm not in fresh),
          all(len(samples.by_pokemon(parties).get(nm) or [])
              < combos.MIN_SAMPLES
              for nm in thin if nm not in fresh), thin)
    rep = combos.coverage_report(dex, top=10)
    check("덮개 보고서가 나온다", "사용률 상위" in rep)
    check("보고서가 어느 룰끼리 비교하는지 밝힌다",
          samples.CURRENT_RULE in rep and "룰 표기" in rep)

    # -- 룰 표기 두 가지(시즌 M-6 / 레귤레이션 M-C)를 하나로 센다 ---------
    # 따로 세서 지금 룰 표본을 9편으로 봤다. 실제로는 22편이었다 (2026-09-21).
    # champs 검색창: 「シーズンM-6 (M-C)」.
    check("M-C 는 M-6 으로 센다", samples.norm_rule("M-C") == "M-6",
          samples.norm_rule("M-C"))
    check("표기가 흔들려도 같다 (' m-c ', 전각 대시)",
          samples.norm_rule(" m-c ") == "M-6"
          and samples.norm_rule("M－C") == "M-6")
    check("M-B 는 시즌을 못 박을 수 없어서 그대로 둔다",
          samples.norm_rule("M-B") == "M-B")
    fake = [{"rule": "M-6"}, {"rule": "M-C"}, {"rule": "M-5"}, {"rule": None}]
    check("by_rule('M-6') 이 M-C 표기 기사도 잡는다",
          len(samples.by_rule(fake, "M-6")) == 2)
    check("rule_counts 에 M-C 가 따로 남지 않는다",
          samples.rule_counts(fake) == {"M-6": 2, "M-5": 1},
          samples.rule_counts(fake))
    loaded_rules = set(p.get("rule") for p in combos.loaded(dex))
    check("불러온 표본에 M-C 표기가 남아 있지 않다", "M-C" not in loaded_rules,
          sorted(r for r in loaded_rules if r))

    # -- 두 마진이 다 지켜지는가 (제일 중요) -------------------------------
    worst = 0.0
    names = []
    for nm, rws in samples.by_pokemon(combos.loaded(dex)).items():
        if len(rws) < combos.MIN_SAMPLES:
            continue
        try:
            pk = dex.find_pokemon(nm)
        except LookupError:
            continue
        if combos.full_table(dex, pk) is None:
            continue
        names.append(nm)
        worst = max(worst, combos.mix_error_full(dex, pk))
    check("기술 마진이 지켜진다 — %d종 최대 오차 %.3f%%p"
          % (len(names), worst * 100), worst < 0.005, worst)

    classes, cond = combos.archetype_by_form(dex, chomp)
    check("각 형태에서 갈래 확률의 합이 1",
          all(abs(sum(r) - 1.0) < 1e-6 for r in cond), cond)
    wmap = forms.class_weights(dex, chomp)
    _c, _k, cells, weights, _m, _t, _s = combos.full_table(dex, chomp)
    bad = 0.0
    for c in classes:
        got_w = sum(weights[n] for n, (i, a) in enumerate(cells)
                    if classes[i] == c)
        bad = max(bad, abs(got_w - wmap[c]))
    check("노력치 마진도 지켜진다 (최대 오차 %.4f)" % bad, bad < 1e-6, bad)

    # -- 형태와 갈래가 어긋나지 않는가 ------------------------------------
    ai = classes.index("AS")
    ci = classes.index("CS")
    phys = max(range(len(w)), key=lambda a: table[a][idx["역린"]])
    spec = max(range(len(w)), key=lambda a: table[a][idx["용성군"]])
    check("AS형은 역린 갈래 쪽, CS형은 용성군 갈래 쪽",
          cond[ai][phys] > cond[ai][spec]
          and cond[ci][spec] > cond[ci][phys],
          (cond[ai], cond[ci]))

    # -- 본 것으로 좁히기가 1-A 보다 센가 ---------------------------------
    def both(seen):
        return (forms.form_posterior(dex, chomp, seen),
                combos.form_posterior(dex, chomp, seen))
    base = combos.form_posterior(dex, chomp, set())
    a1, c1 = both({"스텔스록"})
    check("스텔스록을 보면 내구형이 올라간다 (1-A %.0f%% -> 1-C %.0f%%)"
          % (a1["-"] * 100, c1["-"] * 100),
          c1["-"] > a1["-"] + 0.10, (a1["-"], c1["-"]))
    a2, c2 = both({"역린"})
    check("역린을 보면 CS형이 내려간다 (1-A %.0f%% -> 1-C %.0f%%)"
          % (a2["CS"] * 100, c2["CS"] * 100),
          c2["CS"] <= a2["CS"], (a2["CS"], c2["CS"]))
    a3, c3 = both({"용성군"})
    check("용성군을 보면 CS형이 올라간다 (1-A %.0f%% -> 1-C %.0f%%)"
          % (a3["CS"] * 100, c3["CS"] * 100),
          c3["CS"] > a3["CS"], (a3["CS"], c3["CS"]))
    c4 = combos.form_posterior(dex, chomp, {"칼춤"})
    check("목록 밖 기술(칼춤)로도 형태가 좁혀진다 (AS %.0f%% -> %.0f%%)"
          % (base["AS"] * 100, c4["AS"] * 100),
          c4["AS"] > base["AS"] + 0.15, (base["AS"], c4["AS"]))

    # -- 뽑아 보면 어긋난 놈이 안 나오는가 --------------------------------
    rng = random.Random(11)
    n = wrong = 0
    for _ in range(500):
        b, mv = scout.sample_opponent(dex, chomp, rng)
        cls = forms.spread_class(b.sp)
        names_ = set(x["name"] for x in mv)
        if cls == "CS":
            n += 1
            if "역린" in names_ or "칼춤" in names_:
                wrong += 1
    check("CS형인데 역린·칼춤을 든 놈이 거의 없다 (%d/%d)" % (wrong, n),
          n == 0 or wrong <= n * 0.08, (wrong, n))

    # -- 전체 파이프라인에서도 마진이 지켜지는가 ---------------------------
    rws = scout.check_joint(dex, chomp, trials=3000, seed=4)
    err = max(abs(a - b) for _, a, b in rws)
    check("뽑은 결과를 다 세면 사용률로 돌아온다 (오차 %.1f%%p)" % err,
          err < 3.0, [(x[0], round(x[1], 1), round(x[2], 1)) for x in rws[:3]])

    # -- 표본이 적은 포켓몬은 갈래 모델이 안 붙는다 ------------------------
    thin = None
    for nm, rws2 in samples.by_pokemon(combos.loaded(dex)).items():
        if len(rws2) < 8:
            thin = nm
            break
    if thin:
        try:
            pk = dex.find_pokemon(thin)
            check("표본이 적으면 갈래 모델을 안 만든다 (%s)" % thin,
                  combos.full_table(dex, pk) is None)
        except LookupError:
            pass

def test_fetch_champs(dex):
    """champs 수집기 — 네트워크 없이 파싱만 시험한다.

    champs.pokedb.tokyo 는 클라우드 IP 를 막아서 여기서는 못 받는다.
    집 회선에서 돌릴 파일이므로, **받아 온 뒤의 부분**만 검증해 둔다.
    그래야 사용자가 돌렸을 때 형식이 어긋나는 일이 없다.
    """
    print("\n[34] champs 수집기 (오프라인 부분)")
    import json
    import os
    import tempfile

    import fetch_champs as fc

    html = (u'<html><head><title>【S6最終3位】メガボーマンダ構築</title></head>'
            u'<body>'
            u'<div data-pokemon-name="ガブリアス" data-item="オボンのみ" '
            u'data-ability="さめはだ" data-nature="いじっぱり" '
            u'data-evs="H32 B22 D7 S5" '
            u'data-moves="じしん,ドラゴンテール,ステルスロック,つるぎのまい"></div>'
            u'<div data-pokemon-name="ボーマンダ" data-item="ボーマンダナイト" '
            u'data-nature="いじっぱり" data-evs="A32 S32" '
            u'data-moves="すてみタックル,りゅうのまい,じしん,はねやすめ"></div>'
            u'<div data-pokemon-name="ミミッキュ" data-item="いのちのたま" '
            u'data-nature="ようき" data-evs="A32 S32" '
            u'data-moves="じゃれつく,シャドークロー,つるぎのまい,かげうち"></div>'
            u'<time datetime="2026-09-12T10:00:00Z"></time></body></html>')
    party = fc.parse_article(html, "https://champs.pokedb.tokyo/article/abc")

    check("data-* 전략으로 읽는다", party["parsedBy"] == "data-* 속성",
          party["parsedBy"])
    check("여섯 마리 중 세 마리를 다 꺼냈다", len(party["members"]) == 3,
          len(party["members"]))
    check("**source 가 champs 다** (값어치 3배의 근거)",
          party["source"] == "champs", party["source"])
    check("제목에서 시즌과 순위를 읽는다",
          (party["season"], party["rank"]) == (6, 3), party)
    check("게시일을 읽는다",
          party["publishedAt"] == "2026-09-12T10:00:00Z", party["publishedAt"])
    m0 = party["members"][0]
    check("노력치를 dict 로 꺼낸다",
          m0["evs"] == {"H": 32, "B": 22, "D": 7, "S": 5}, m0["evs"])
    check("노력치 합이 66", sum(m0["evs"].values()) == 66, m0["evs"])
    check("기술 네 개를 꺼낸다", len(m0["moves"]) == 4, m0["moves"])

    # 챔피언스는 한 칸 최대 32 다. 본편 표기(252)가 섞여 들어오면 안 된다.
    check("본편 표기(252)는 노력치로 안 받는다",
          fc._evs_from("H252 A252 S4") == {"S": 4},
          fc._evs_from("H252 A252 S4"))

    # 표 전략
    html2 = (u'<title>【M-6 最終120位】テスト</title><table>'
             u'<tr><th>ポケモン</th><th>努力値</th></tr>'
             u'<tr><td>カバルドン</td><td>H32 B32</td></tr>'
             u'<tr><td>メタグロス</td><td>A32 S26</td></tr>'
             u'<tr><td>ニンフィア</td><td>H32 D32</td></tr></table>')
    p2 = fc.parse_article(html2, "x")
    check("표 전략도 돈다", p2["parsedBy"] == "표", p2["parsedBy"])
    check("룰과 순위를 읽는다", (p2["rule"], p2["rank"]) == ("M-6", 120), p2)

    # 못 읽는 기사는 조용히 빈 파티
    p3 = fc.parse_article(u"<title>글</title><p>그냥 글입니다</p>", "y")
    check("못 읽는 기사는 개체가 0", p3["members"] == [], p3["members"])
    check("그래도 source 는 붙어 있다", p3["source"] == "champs")

    # 꺼낸 것이 samples.py 로 그대로 들어가는가 (두 쪽이 붙는지)
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"parties": [party]}, f, ensure_ascii=False)
    try:
        parties, bad = samples.load(dex, path)
    finally:
        os.unlink(path)
    check("samples 가 그대로 읽는다",
          len(parties) == 1 and len(bad) == 0,
          bad.summary() if len(bad) else None)
    got = parties[0]["members"][0]
    check("일본어가 한국어로 이어진다",
          got["poke"]["name"] == "한카리아스", got["poke"]["name"])
    check("champs + 상위 50위라 값어치가 6.0",
          abs(samples.party_weight(parties[0]) - 6.0) < 1e-9,
          samples.party_weight(parties[0]))
    check("같은 pokesol 기사보다 무겁다",
          samples.party_weight(parties[0])
          > samples.party_weight({"source": "pokesol", "rank": 3}))

def test_party_file(dex):
    """내 파티 파일 — 적은 것이 그대로 돌아오는가, 조용히 사라지지 않는가.

    2026-09-21 창 점검에 "못 알아들은 말: 무투자, 페어리스킨" 이 떠서 셋이
    한꺼번에 나왔다.
      ① 노력치를 비우면 '무투자' 라고 저장하는데 읽는 쪽이 몰랐다.
      ② 특성 칸을 비우면 **메가 특성**이 보통 폼에 붙었다 (50종).
      ③ 한 줄만 못 읽어도 **파티 전체를 버렸다.** 창에서는 안 보였고,
         칸 하나를 고치면 자동 저장이 빈 파티로 덮어썼다.
    """
    import io
    import os
    import tempfile
    import live
    print("\n[46] 내 파티 파일")

    # ② 특성을 비워도 그 폼이 가질 수 있는 특성만 붙는다 — 전 종
    wrong = []
    for p in dex.pokemon:
        if p.get("isMega"):
            continue
        for item in (None, "먹다남은음식"):
            b, _f = live.build_one(dex, p, {}, None, None, item)
            if b.ability not in [a["name"] for a in b.poke["abilities"]]:
                wrong.append((p["name"], item, b.ability))
    check("특성을 비워도 자기 폼의 특성만 붙는다 (틀린 것 %d건)" % len(wrong),
          not wrong, wrong[:5])
    ga, _f = live.build_one(dex, dex.find_pokemon("가디안"), {}, None, None,
                            "버치열매")
    check("가디안 + 버치열매 -> 트레이스 (사용률 1위, 페어리스킨 아님)",
          ga.ability == "트레이스", ga.ability)
    gz, _f = live.build_one(dex, dex.find_pokemon("한카리아스"), {}, None,
                            None, "먹다남은음식")
    check("한카리아스 + 먹다남은음식 에 부유가 안 붙는다 (%s)" % gz.ability,
          gz.ability != "부유", gz.ability)
    gm, _f = live.build_one(dex, dex.find_pokemon("가디안"), {}, None, None,
                            "가디안나이트")
    check("메가스톤이면 여전히 메가 폼 + 메가 특성",
          gm.poke.get("isMega") and gm.ability == "페어리스킨",
          (gm.name, gm.ability))

    # ① 저장 -> 읽기 가 한 바퀴 돈다 (노력치 비움 포함)
    tmp = os.path.join(tempfile.mkdtemp(), "party.txt")
    b1, _f = live.build_one(dex, dex.find_pokemon("가디안"), {},
                            dex.find_nature("조심"), "트레이스", "버치열매")
    b2, _f = live.build_one(dex, dex.find_pokemon("하마돈"),
                            {"hp": 32, "defense": 22},
                            dex.find_nature("무사태평"), "모래날림", "자뭉열매")
    live.save_party_file([(b1, [], []), (b2, ["지진", "하품"], [])], tmp)
    notes = []
    back = live.load_party(dex, tmp, notes=notes) or []
    check("노력치를 비운 포켓몬도 다시 읽힌다 ('무투자')",
          len(back) == 2 and not notes, (len(back), notes))
    if len(back) == 2:
        check("읽은 값이 저장한 값과 같다 (특성·성격·도구·노력치·기술)",
              back[0][0].ability == "트레이스"
              and (back[0][0].nature or {}).get("name") == "조심"
              and back[0][0].item == "버치열매"
              and not any(back[0][0].sp.values())
              and back[1][0].sp.get("hp") == 32
              and back[1][1] == ["지진", "하품"],
              [(b.name, b.ability, b.item, b.sp) for b, _m, _x in back])

    # ④ ★ **메가스톤을 든 놈도 한 바퀴 돈다** (2026-09-23, 사용자 파티에서 터졌다).
    #   창이 쓴 줄을 창이 못 읽고 있었다 — 메가스톤을 들면 빌드가 **메가 폼**이 되어
    #   특성이 '스카이스킨/부유' 로 적히는데, 읽는 쪽은 그 특성을 **기본 폼**에서 찾다가
    #   못 찾아 「'스카이스킨' 를 못 알아들어 빼고 읽었습니다」 를 냈다.
    #   → `party_line` 이 메가 폼이면 특성을 안 적는다 (도구를 보고 폼과 함께 정해진다).
    #   CLAUDE.md §1 의 「쓰는 쪽과 읽는 쪽이 짝이 맞나 — 한 바퀴 돌려 본다」 그 자리다.
    stones = []
    for p in dex.pokemon:
        if p.get("isMega"):
            continue
        for item, mega in dex.mega_by_item.items():
            if mega["dexNo"] == p["dexNo"]:
                stones.append((p, item))
                break
    rows = []
    for p, item in stones:
        b, _f = live.build_one(dex, p, {"hp": 32}, dex.find_nature("고집"), None, item)
        rows.append((b, ["지진"], []))
    live.save_party_file(rows, tmp)
    notes = []
    back = live.load_party(dex, tmp, notes=notes) or []
    bad = [(rows[i][0].name, back[i][0].name, rows[i][0].ability, back[i][0].ability)
           for i in range(min(len(rows), len(back)))
           if rows[i][0].name != back[i][0].name
           or rows[i][0].ability != back[i][0].ability
           or rows[i][0].item != back[i][0].item]
    check("메가스톤 든 %d종이 저장했다 읽어도 그대로다 (경고 없이)" % len(stones),
          len(back) == len(rows) and not notes and not bad,
          (len(back), notes[:3], bad[:3]))
    # 예전에 저장된 파일에 메가 특성이 적혀 있어도 **탓하지 않고 읽는다**
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(u"# 이름 기술 | 성격 노력치 특성 도구\n")
        f.write(u"보만다 지진 | 고집 H32 스카이스킨 보만다나이트\n")
        f.write(u"마폭시 화염방사 | 겁쟁이 H32 부유 마폭시나이트\n")
    notes = []
    back = live.load_party(dex, tmp, notes=notes) or []
    check("예전 파일에 적힌 메가 특성('스카이스킨'·'부유')도 탓하지 않고 읽는다",
          len(back) == 2 and not notes
          and back[0][0].ability == "스카이스킨" and back[1][0].ability == "부유",
          (len(back), notes, [b.ability for b, _m, _x in back]))

    # ③ 한 줄에 못 읽는 말이 있어도 파티가 통째로 사라지지 않는다
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(u"# 이름 기술 | 성격 노력치 특성 도구\n")
        f.write(u"가디안  | 조심 무투자 페어리스킨 버치열매\n")
        f.write(u"하마돈 지진 | 무사태평 H32 모래날림 자뭉열매\n")
        f.write(u"없는포켓몬 지진\n")
    notes = []
    back = live.load_party(dex, tmp, notes=notes) or []
    check("못 읽는 말이 있어도 나머지는 살린다 (%d마리)" % len(back),
          [b.poke["name"] for b, _m, _x in back] == ["가디안", "하마돈"],
          [b.poke["name"] for b, _m, _x in back])
    check("무엇을 뺐는지 알려 준다 (%d건)" % len(notes),
          any("페어리스킨" in n for n in notes)
          and any("없는포켓몬" in n for n in notes), notes)
    check("직접 치는 줄은 여전히 엄격하다 (오타를 바로 알림)",
          live.read_line(dex, "가디안 | 페어리스킨")[3] is not None)


def test_rosters(dex):
    """동반 출현 — champs 카드(명단만 있는 것)가 처음 값을 하는 자리."""
    print("\n[35] 동반 출현")
    import json
    import os
    import tempfile

    def write(doc):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        return path

    def party(names, rank=None, when="2026-09-01T00:00:00Z", rule=None,
              src="champs"):
        return {"source": src, "rank": rank, "rule": rule,
                "publishedAt": when, "url": "u%d" % abs(hash(tuple(names))),
                "members": [{"name": n, "moves": [], "evs": {}} for n in names]}

    # 한 쌍만 늘 같이 나오게 만들어 놓고, 그것만 잡히는지 본다
    # 이름은 데이터에 있는 그대로 써야 한다. '페리퍼' 가 아니라 '패리퍼' 다 —
    # 처음에 틀리게 써서 개체가 조용히 빠지고 명단이 45편으로 줄었다.
    A, B = "패리퍼", "대짱이"
    filler = ["한카리아스", "아머까오", "누리레느", "하마돈"]
    doc = {"parties": []}
    for i in range(30):
        doc["parties"].append(party([A, B] + filler[: 2 + i % 2]))
    for i in range(30):
        doc["parties"].append(party(filler + ["따라큐", "브리두라스"]))
    path = write(doc)
    try:
        parties, _ = samples.load(dex, path)
    finally:
        os.unlink(path)

    got = samples.rosters(parties)
    check("명단은 기술·배분이 없어도 살아 있다 (%d편)" % len(got),
          len(got) == 60, len(got))
    check("반대로 members() 는 그 개체를 안 준다 (셀 것이 없으므로)",
          len(list(samples.members(parties))) == 0)

    rows, n = samples.pair_lift(parties, min_seen=5, min_both=3)
    lift = dict(((a, b), lf) for a, b, _c, _sa, _sb, _e, lf in rows)

    def L(a, b):
        return lift.get((a, b), lift.get((b, a)))

    check("짜 놓은 쌍이 제일 크게 잡힌다 (리프트 %.1f)" % (L(A, B) or 0),
          L(A, B) and L(A, B) > 1.8, L(A, B))
    check("같이 안 나오게 만든 쌍은 1 아래",
          L(A, "따라큐") is None or L(A, "따라큐") < 1.0, L(A, "따라큐"))
    check("리프트가 아니라 기대값 차이로 줄 세운다",
          rows[0][0] in (A, B) or abs(rows[0][2] - rows[0][5])
          >= abs(rows[-1][2] - rows[-1][5]))

    # 짝 예측
    pals, mass = samples.partners(parties, A, min_seen=5)
    check("A 를 봤을 때 B 가 1등", pals and pals[0][0] == B, pals[:2])
    check("조건부 확률이 1 에 가깝다 (%.2f)" % pals[0][1],
          pals[0][1] > 0.9, pals[0][1])

    # 값어치가 반영되는가 — champs(3배)가 pokesol(1배)보다 무겁다
    mixed = {"parties": [party([A, B] + filler[:2], rank=1, src="champs")]
             + [party([A, "따라큐"] + filler[:2], rank=1, src="pokesol")
                for _ in range(2)]}
    path = write(mixed)
    try:
        mp, _ = samples.load(dex, path)
    finally:
        os.unlink(path)
    pals2, _ = samples.partners(mp, A, min_seen=0)
    d2 = dict((a, c) for a, c, _l in pals2)
    check("champs 파티가 더 무겁게 셰어진다 (%s vs %s)"
          % (round(d2.get(B, 0), 2), round(d2.get("따라큐", 0), 2)),
          d2.get(B, 0) > d2.get("따라큐", 0) / 2.0, d2)

    # 시기·룰로 좁힐 수 있는가 (이 표만은 메타에 매인다)
    doc2 = {"parties": [party([A, B] + filler[:2], when="2026-09-01T00:00:00Z",
                              rule="M-6"),
                        party(filler + ["따라큐", "브리두라스"],
                              when="2026-05-01T00:00:00Z", rule="M-3")]}
    path = write(doc2)
    try:
        p2, _ = samples.load(dex, path)
    finally:
        os.unlink(path)
    check("시기로 좁힌다",
          len(samples.rosters(p2, since="2026-08")) == 1
          and len(samples.rosters(p2)) == 2)
    check("룰로 좁힌다", len(samples.rosters(p2, rule="M-6")) == 1)

    # 보고서
    check("보고서가 나온다", "동반 출현" in samples.report_rosters(dex, parties))
    check("짝 예측 보고서도 나온다",
          "나머지는?" in samples.report_rosters(dex, parties, name=A))

def test_poltergeist(dex):
    """폴터가이스트는 상대가 도구를 안 들고 있으면 실패한다.

    2026-09-22 사용자 영상 (아이패드 녹화): 하마돈이 자뭉열매를 먹은 뒤
    다크펫의 폴터가이스트가 「그러나 실패하고 말았다!」 로 끝났다. 사용자가
    "빗나감이 아니라 자뭉열매를 소모했기 때문" 이라고 짚었다. 설명문에는
    적혀 있었는데 코드 어디에도 없어서, 계산기는 도구가 없어도 110 으로 때렸다.
    """
    import battle, best, random
    print("\n[47] 폴터가이스트 — 상대가 도구가 없으면 실패")
    P = lambda n: calc.popular_build(dex, dex.find_pokemon(n))[0]
    pg = dex.find_move("폴터가이스트")
    iron = dex.find_move("철벽")
    check("설명문에 실패 조건이 있다", "도구를 지니고 있지 않은 경우 실패"
          in (pg.get("description") or ""), pg.get("description"))

    # ① 데미지 계산 — 도구가 있으면 맞고 없으면 실패
    atk, dfn = P("다크펫"), P("하마돈")
    dfn.item = "자뭉열매"
    with_item = calc.calc_damage(dex, atk, dfn, pg)
    dfn.item = None
    without = calc.calc_damage(dex, atk, dfn, pg)
    check("도구를 들면 데미지가 나온다 (%s)" % with_item.get("max"),
          "error" not in with_item and with_item["max"] > 0, with_item.get("error"))
    check("도구가 없으면 실패한다", "error" in without and "실패" in without["error"],
          without)

    # ② 한 턴 표 — 캐시 열쇠에 도구가 들어 있어서 두 답이 섞이면 안 된다
    dfn.item = "자뭉열매"
    r1 = best.rate_moves(dex, atk, dfn, [(pg, 1.0)])[0]["kind"]
    dfn.item = None
    r2 = best.rate_moves(dex, atk, dfn, [(pg, 1.0)])[0]["kind"]
    check("한 턴 표도 도구 유무로 갈린다 (%s / %s)" % (r1, r2),
          r1 == "damage" and r2 == "none", (r1, r2))

    # ③ 영상 그대로 — 1턴에 맞아서 자뭉열매를 먹고, 2턴 폴터가이스트는 실패.
    #    명중 90% 라 1턴이 빗나간 씨앗은 건너뛴다. 대조군: 도구가 남아 있으면 맞는다.
    #    씨앗 하나만 보면 안 된다 — 명중 판정 뒤에 거르면 열 판에 한 판꼴로만
    #    '빗나감' 이 찍혀서, 첫 씨앗은 우연히 통과한다 (일부러 고장 내 보고 알았다:
    #    172판 중 19판). 그래서 재현한 판 **전부**를 센다.
    seen, leaked, missed, said1 = 0, 0, 0, ""
    for seed in range(200):
        me, op = P("다크펫"), P("하마돈")
        op.item = "자뭉열매"
        b = battle.Battle(dex, me, op, rng=random.Random(seed), log=True,
                          opp_hp=[55])
        b.step(pg, iron)
        if not b.opp.item_used:
            continue                      # 1턴이 빗나갔거나 50% 위로 남았다
        h = b.opp.hp
        n_log = len(b.log)
        b.step(pg, iron)
        took, said = h - b.opp.hp, " / ".join(b.log[n_log:])
        seen += 1
        leaked += took > 0
        missed += ("빗나감" in said) or ("실패" not in said)
        said1 = said1 or said
    check("열매를 먹은 뒤 폴터가이스트는 한 방울도 안 들어간다 (%d판 중 %d판 들어감)"
          % (seen, leaked), leaked == 0, said1)
    check("로그가 '빗나감' 이 아니라 '실패' 라고 한다 (%d판 중 %d판 어긋남)"
          % (seen, missed), missed == 0, said1)
    check("영상 장면을 실제로 재현했다 (%d판)" % seen, seen >= 100, seen)

    hits = 0
    for seed in range(10):
        me, op = P("다크펫"), P("하마돈")
        op.item = "먹다남은음식"          # 먹어 없어지지 않는 도구
        b = battle.Battle(dex, me, op, rng=random.Random(seed))
        h = b.opp.hp
        b.step(pg, iron)
        hits += (h - b.opp.hp) > 0
    check("대조군: 도구가 남아 있으면 맞는다 (10번 중 %d번)" % hits, hits >= 7, hits)


def test_fail_conditions(dex):
    """설명문에 '실패한다' 가 붙은 공격기 17개 + 짝이 되는 규칙 (2026-09-22).

    폴터가이스트([47])를 고치다 세어 보니 17개가 더 있었고 거의 다 안 붙어 있었다.
    만나자마자(갑주무사 71.8%)가 매 턴 위력 100 선제기로, 기습(대도각참 99%)이
    상대가 변화기를 써도 들어갔다. 터지지 않고 그 기술을 든 쪽이 조용히 세졌다.
    기술마다 **답이 뻔한 상황**을 만들고, 조건이 맞을 때는 **된다** 는 대조군을 붙인다.
    """
    import battle, best, random, re
    print("\n[48] 설명문의 실패 조건 — 17개 기술")
    P = lambda n: calc.popular_build(dex, dex.find_pokemon(n))[0]
    M = dex.find_move
    iron = M("철벽")

    def my_hits(b, since):
        """이 턴에 **내 기술이** 준 데미지. 로그에서 읽는다.

        ! 처음엔 턴 전후 상대 HP 차이로 쟀다. 그랬더니 모래바람 칩(11)과
          자뭉열매 회복이 섞여서, 실패한 트림이 '11 들어감' 으로 잡히고
          '열매 먹은 뒤 트림은 들어간다' 가 **모래 칩 덕에 저절로** 통과했다.
        """
        pat = re.compile(r"%s 의 \S+ → \S+ 에게 (\d+)" % re.escape(b.me.name))
        return sum(int(m.group(1)) for line in b.log[since:]
                   for m in [pat.search(line)] if m)

    def duel(me, op, mine, theirs, seed=1, **kw):
        kw.setdefault("my_fresh", True)
        kw.setdefault("opp_fresh", True)
        b = battle.Battle(dex, me, op, rng=random.Random(seed), log=True, **kw)
        dealt = []
        for a, o in zip(mine, theirs):
            n = len(b.log)
            b.step(a, o)
            dealt.append(my_hits(b, n))
        return b, dealt

    def said(b, text):
        return any(text in line for line in b.log)

    # ① 규칙이 **딱 그 기술들만** 잡는가 — 넓게 잡으면 엉뚱한 기술이 실패한다
    want = {
        battle._FIRST_ONLY: {"속이기", "만나자마자"},
        battle._SUCKER: {"기습"},
        battle._UPPER_HAND: {"기선제압"},
        battle._FOCUS: {"힘껏펀치"},
        battle._LAST_RESORT: {"비장의무기"},
        battle._BELCH: {"트림"},
        battle._NEED_STOCKPILE: {"토해내기", "꿀꺽"},
        battle._NEED_TERRAIN: {"아이언롤러"},
        battle._CLEAR_TERRAIN: {"아이언롤러", "아이스스피너"},
        battle._CRASH: {"무릎차기", "발꿈치찍기", "썬더다이브"},
        battle._AFTER_FAIL: {"분함의발구르기", "열불내기"},
        battle._LOSE_TYPE: {"불사르기", "전광쌍격"},
        battle._FLINCH_ALWAYS: {"속이기", "기선제압"},
        calc._FAIL_NOT_TYPE: {"불사르기", "전광쌍격"},
        calc._ENDEAVOR: {"죽기살기"},
        calc._FAIL_NO_ITEM: {"폴터가이스트"},
    }
    for rx, names in want.items():
        got = {m["name"] for m in dex.moves if rx.search(m.get("description") or "")}
        check("규칙이 %s 만 잡는다" % "·".join(sorted(names)), got == names, got)
    # 한 턴 표의 '조건부' 주의도 같은 기술에 붙는가 (패턴을 두 곳에 적었으므로 대조)
    fail_attacks = [m for m in dex.moves if "실패" in (m.get("description") or "")
                    and m["category"] != "변화"]
    covered = [m["name"] for m in fail_attacks
               if any(c.startswith(best.CONDITIONAL) for c in best.move_caveats(m))
               or calc._FAIL_NO_ITEM.search(m["description"])
               or calc._ENDEAVOR.search(m["description"])]
    check("설명문에 '실패' 가 붙은 공격기 %d개 전부에 조건이 붙었다" % len(fail_attacks),
          len(covered) == len(fail_attacks) == 18,
          sorted(set(m["name"] for m in fail_attacks) - set(covered)))

    # ② 나온 첫 턴만 — 만나자마자·속이기
    b, dealt = duel(P("갑주무사"), P("하마돈"), [M("만나자마자")] * 2, [iron] * 2)
    check("만나자마자: 1턴은 들어가고 2턴은 실패 (%s)" % dealt,
          dealt[0] > 0 and dealt[1] == 0 and said(b, "첫 기술이 아니다"), b.log)
    b = battle.Battle(dex, [P("갑주무사"), P("아머까오")], P("하마돈"),
                      rng=random.Random(1), log=True, my_fresh=True, opp_fresh=True)
    b.step(M("만나자마자"), iron)
    b.step(("교체", 1), iron)
    b.step(("교체", 0), iron)
    n = len(b.log)
    b.step(M("만나자마자"), iron)
    again = my_hits(b, n)
    check("교체해 다시 나오면 만나자마자가 또 된다 (%d)" % again, again > 0, b.log[-4:])
    b, dealt = duel(P("갑주무사"), P("하마돈"), [M("만나자마자")], [iron], my_fresh=False)
    check("이미 나와 있던 놈이면 1턴부터 실패", dealt[0] == 0, b.log)
    b, _ = duel(P("갑주무사"), P("하마돈"), [M("만나자마자")], [iron], my_fresh=None)
    check("막 나왔는지 모르면 막 나온 것으로 보되 경고한다",
          any("막 나왔는지 몰라서" in w for w in b.warnings), b.warnings)
    b, _ = duel(P("갑주무사"), P("하마돈"), [M("만나자마자")], [iron])
    check("알고 있으면 경고하지 않는다",
          not any("막 나왔는지 몰라서" in w for w in b.warnings), b.warnings)
    b, _ = duel(P("포푸니크"), P("하마돈"), [M("속이기")], [M("지진")])
    check("속이기를 맞으면 풀죽어서 못 움직인다",
          said(b, "풀죽어서 움직이지 못했다") and not said(b, "하마돈 의 지진"), b.log)
    tough = P("하마돈")
    tough.ability = "정신력"
    b, _ = duel(P("포푸니크"), tough, [M("속이기")], [M("지진")])
    check("정신력은 풀죽지 않는다 (설명문에서 읽음)",
          said(b, "풀죽지 않는다") and said(b, "하마돈 의 지진"), b.log)

    # ③ 상대가 무엇을 골랐나 — 기습·기선제압
    b, dealt = duel(P("대도각참"), P("하마돈"), [M("기습")] * 2, [iron, M("지진")])
    check("기습: 상대가 변화기면 실패, 공격기면 들어간다 (%s)" % dealt,
          dealt[0] == 0 and dealt[1] > 0, b.log)
    b, dealt = duel(P("대도각참"), P("갑주무사"), [M("기습")], [M("만나자마자")])
    check("기습: 상대가 더 빠른 선제기로 먼저 움직였으면 실패 (%s)" % dealt,
          dealt[0] == 0 and said(b, "이미 움직였다"), b.log)
    b = battle.Battle(dex, P("대도각참"), [P("하마돈"), P("아머까오")],
                      rng=random.Random(1), log=True, my_fresh=True, opp_fresh=True)
    b.step(M("기습"), ("교체", 1))
    check("기습: 상대가 교체하면 실패", said(b, "공격 기술을 고르지 않았다"), b.log)
    b, dealt = duel(P("모크나이퍼"), P("누리레느"), [M("기선제압")] * 2,
                    [M("아쿠아제트"), M("문포스")])
    check("기선제압: 선제기에는 들어가고 풀죽이며, 아니면 실패 (%s)" % dealt,
          dealt[0] > 0 and dealt[1] == 0 and said(b, "누리레느 는 풀죽었다"), b.log)

    # ④ 이 턴에 먼저 맞았나 — 힘껏펀치
    b, dealt = duel(P("고릴타"), P("누리레느"), [M("힘껏펀치")], [M("문포스")])
    check("힘껏펀치: 먼저 맞으면 실패", dealt[0] == 0 and said(b, "먼저 맞았다"), b.log)
    b, dealt = duel(P("고릴타"), P("누리레느"), [M("힘껏펀치")], [iron])
    check("힘껏펀치: 안 맞으면 들어간다 (%d)" % dealt[0], dealt[0] > 0, b.log)

    # ⑤ 나온 뒤 쓴 기술 — 비장의무기
    b = battle.Battle(dex, P("캥카"), P("누리레느"), rng=random.Random(3), log=True,
                      my_fresh=True, opp_fresh=True)
    b.me.moveset = ["비장의무기", "속이기", "기습", "철벽"]
    got = []
    for mv in ["비장의무기", "속이기", "기습", "철벽", "비장의무기"]:
        n = len(b.log)
        b.step(M(mv), iron)
        got.append(my_hits(b, n))
    check("비장의무기: 다른 기술을 다 쓰기 전엔 실패, 다 쓴 뒤엔 들어간다 (%s)" % got,
          got[0] == 0 and got[4] > 0, b.log)
    b, dealt = duel(P("캥카"), P("누리레느"), [M("철벽"), M("비장의무기")], [iron] * 2)
    check("비장의무기: 기술 목록을 모르면 4개로 보고 실패", dealt[1] == 0
          and said(b, "4개로 봄"), b.log)

    # ⑥ 열매를 먹었나 — 트림 (명중 90% 라 들어간 판을 찾는다)
    b, dealt = duel(P("하마돈"), P("누리레느"), [M("트림")], [iron])
    check("트림: 열매를 안 먹었으면 실패", dealt[0] == 0 and said(b, "나무열매를 안 먹었다"),
          b.log)
    hit = 0
    for seed in range(10):
        me = P("하마돈")
        me.item = "자뭉열매"
        b = battle.Battle(dex, me, P("누리레느"), rng=random.Random(seed),
                          log=True, my_fresh=True, opp_fresh=True)
        b.me.item_used = True                      # 이미 먹었다
        n = len(b.log)
        b.step(M("트림"), iron)
        hit += my_hits(b, n) > 0                   # 모래 칩이 섞이지 않게 로그로
    check("트림: 열매를 먹은 뒤엔 들어간다 (10번 중 %d번)" % hit, hit >= 7, hit)

    # ⑦ 비축 — 토해내기
    b, dealt = duel(P("하마돈"), P("누리레느"),
                    [M("토해내기"), M("비축하기"), M("비축하기"), M("토해내기")], [iron] * 4)
    check("토해내기: 비축 없으면 실패, 비축하면 들어간다 (%s)" % dealt,
          dealt[0] == 0 and dealt[3] > 0, b.log)
    check("토해내기 뒤 비축과 방어·특방 상승이 풀린다 (%s)" % b.me.rank_text(),
          b.me.stockpile == 0 and b.me.ranks["defense"] == 0
          and b.me.ranks["spDef"] == 0, b.me.ranks)
    b2, d2 = duel(P("하마돈"), P("누리레느"),
                  [M("비축하기"), M("비축하기"), M("토해내기")], [iron] * 3)
    b1, d1 = duel(P("하마돈"), P("누리레느"), [M("비축하기"), M("토해내기")], [iron] * 2)
    check("비축 2회가 1회보다 세다 (%d vs %d)" % (d2[2], d1[1]), d2[2] > d1[1],
          (d1, d2))
    b, _ = duel(P("하마돈"), P("누리레느"), [M("비축하기")] * 4, [iron] * 4)
    check("비축하기는 3회까지", b.me.stockpile == 3 and said(b, "더 비축할 수 없다"),
          b.me.stockpile)

    # ⑧ 필드 — 아이언롤러
    b, dealt = duel(P("하마돈"), P("누리레느"), [M("아이언롤러")], [iron])
    check("아이언롤러: 필드가 없으면 실패", dealt[0] == 0 and said(b, "필드가 없다"), b.log)
    b, dealt = duel(P("고릴타"), P("누리레느"), [M("아이언롤러")], [iron])
    check("아이언롤러: 필드가 있으면 들어가고 필드를 없앤다 (%d)" % dealt[0],
          dealt[0] > 0 and b.field.terrain is None, (b.field.terrain, b.log))

    # ⑨ 자기 타입 — 불사르기·전광쌍격
    b, dealt = duel(P("윈디"), P("누리레느"), [M("불사르기")] * 2, [iron] * 2)
    check("불사르기: 순수 불꽃은 타입이 없어진다 — 계산에도 [] 로 간다 (%s / %s)"
          % (b.me.types, b.me.as_build().types),
          b.me.types == [] and b.me.as_build().types == [], b.me.types)
    check("불사르기: 불꽃타입이 없으면 실패 (%s)" % dealt, dealt[0] > 0 and dealt[1] == 0,
          b.log)
    b, _ = duel(P("빠르모트"), P("누리레느"), [M("전광쌍격")], [iron])
    check("전광쌍격: 전기타입을 잃는다 (%s)" % b.me.types,
          "전기" not in b.me.types and b.me.types, b.me.types)
    b = battle.Battle(dex, [P("윈디"), P("하마돈")], P("누리레느"),
                      rng=random.Random(1), my_fresh=True, opp_fresh=True)
    b.step(M("불사르기"), iron)
    b.step(("교체", 1), iron)
    check("교체하면 타입이 돌아온다", b.me_party.members[0].types == ["불꽃"],
          b.me_party.members[0].types)

    # ⑩ 죽기살기 — 남은 HP 의 차이, 고정 데미지
    b, dealt = duel(P("고릴타"), P("누리레느"), [M("죽기살기")], [iron], my_hp=[10])
    mine_hp = max(1, int(round(b.me.max_hp * 0.10)))
    check("죽기살기: 상대 HP − 내 HP 만큼 들어간다 (%d, 기대 %d)"
          % (dealt[0], b.opp.max_hp - mine_hp), dealt[0] == b.opp.max_hp - mine_hp,
          b.log)
    check("죽기살기에는 생명의구슬 반동이 없다", not said(b, "생명의구슬 반동"), b.log)
    b, dealt = duel(P("고릴타"), P("누리레느"), [M("죽기살기")], [iron], opp_hp=[10])
    check("죽기살기: 상대 HP 가 내 HP 이하면 실패", dealt[0] == 0, b.log)

    # ⑪ 빗나가거나 실패하면 다친다 — 무릎차기·썬더다이브
    b, _ = duel(P("에이스번"), P("다크펫"), [M("무릎차기")], [iron])
    check("무릎차기: 고스트에게 안 통해도 최대 HP 절반을 잃는다 (%d/%d)"
          % (b.me.hp, b.me.max_hp),
          b.me.hp == b.me.max_hp - b.me.max_hp // 2 and said(b, "스스로 다쳤다"), b.log)
    missed = None
    for seed in range(60):
        b, _ = duel(P("렌트라"), P("누리레느"), [M("썬더다이브")], [iron], seed=seed)
        if said(b, "빗나감"):
            missed = b
            break
    check("썬더다이브: 빗나가도 다친다", missed is not None and said(missed, "스스로 다쳤다"),
          missed.log if missed else None)

    # ⑫ 직전에 실패했으면 2배 — 분함의발구르기·열불내기
    b, dealt = duel(P("케오퍼스"), P("누리레느"), [M("분함의발구르기")] * 2,
                    [M("방어"), iron])
    ctl, cdealt = duel(P("케오퍼스"), P("누리레느"), [iron, M("분함의발구르기")],
                       [iron, iron])
    check("분함의발구르기: 막힌 다음 턴은 2배 (%d vs 대조 %d)" % (dealt[1], cdealt[1]),
          said(b, "위력 2배") and not said(ctl, "위력 2배")
          and dealt[1] > cdealt[1] * 1.6, (b.log, ctl.log))

    # ⑬ 얼음이 녹는 불꽃 기술 (불사르기와 같은 문장)
    b = battle.Battle(dex, P("윈디"), P("누리레느"), rng=random.Random(1), log=True,
                      my_fresh=True, opp_fresh=True)
    b.me.status = "얼음"
    b.step(M("플레어드라이브"), iron)
    check("얼어 있어도 플레어드라이브는 녹이고 쓴다", my_hits(b, 0) > 0
          and b.me.status is None, b.log)

    # ⑭ AI 가 둘째 턴부터 만나자마자를 되풀이하지 않는다
    #    (전에는 고른 기술 하나를 외워 끝까지 썼다 — 이제는 매번 실패하게 된다)
    #    ! 상대를 하마돈으로 두면 원래 아쿠아브레이크가 더 세서 거를 일이 없다 —
    #      일부러 고장 내 보니 그 검사는 통과해 버렸다. 만나자마자가 1등인 상대
    #      (한카리아스: 둘 다 1배라 위력 100 이 85 를 이긴다)로 둔다. 마스카나(벌레 4배)는
    #      1턴에 쓰러져서 둘째 턴이 없었다 — 그것도 고장을 못 잡았다.
    used = 0
    for seed in range(5):
        r = battle.run_once(dex, P("갑주무사"), P("한카리아스"), [M("만나자마자")],
                            [M("철벽")], random.Random(seed), log=True,
                            my_moves=[M("만나자마자"), M("아쿠아브레이크")])
        used += sum(1 for line in r["log"] if "첫 기술이 아니다" in line)
    check("AI 가 실패할 줄 아는 만나자마자를 다시 고르지 않는다 (%d번 헛씀)" % used,
          used == 0, used)
    used = 0
    for seed in range(5):
        r = battle.run_once(dex, P("갑주무사"), P("하마돈"), [M("만나자마자")],
                            [M("지진")], random.Random(seed), log=True)
        used += sum(1 for line in r["log"] if "첫 기술이 아니다" in line)
    check("기술 목록 없이 계획을 되풀이할 때도 마찬가지 (%d번 헛씀)" % used,
          used == 0, used)

    # ⑮ 상대가 변화기만 쓰면 기습을 계속 고르지 않는다 (정한 규칙 — Policy._just_failed)
    #    이게 없으면 철벽만 쓰는 하마돈에게 200판 6000번 헛치고 판이 안 끝났다.
    worst, unended = 0, 0
    for seed in range(10):
        r = battle.run_once(dex, P("대도각참"), P("하마돈"), [M("기습")], [iron],
                            random.Random(seed), log=True,
                            my_moves=[M("기습"), M("아이언헤드")])
        worst = max(worst, sum(1 for line in r["log"] if "공격 기술을 고르지" in line))
        unended += r["result"] == "안 끝남"
    check("변화기만 쓰는 상대에게 기습은 판마다 한 번만 헛친다 (최대 %d번, 안 끝남 %d판)"
          % (worst, unended), worst <= 1 and unended == 0, (worst, unended))


def test_attack_effects(dex):
    """공격기의 추가 효과 (2026-09-22). 전에는 **하나도** 안 읽었다.

    용성군이 특공을 안 깎고, 유턴이 교체를 안 하고, 화염방사가 화상을 안 걸고,
    스케일샷이 한 번만 때렸고, 바디프레스·속임수는 데미지부터 틀렸다.
    기술마다 답이 뻔한 상황과 대조군을 둔다. 데미지는 **로그에서** 읽는다
    ([48] 에서 HP 차이로 쟀다가 모래 칩이 섞여 저절로 통과한 적이 있다).
    """
    import battle, best, random, re
    print("\n[49] 공격기의 추가 효과")
    P = lambda n: calc.popular_build(dex, dex.find_pokemon(n))[0]
    M = dex.find_move
    iron = M("철벽")
    fx = calc.attack_effects

    def duel(me, op, mine, theirs, seed=1, **kw):
        kw.setdefault("my_fresh", True)
        kw.setdefault("opp_fresh", True)
        b = battle.Battle(dex, me, op, rng=random.Random(seed), log=True, **kw)
        for a, o in zip(mine, theirs):
            b.step(a, o)
        return b

    def said(b, text):
        return any(text in line for line in b.log)

    def dealt(b, who):
        pat = re.compile(r"^\s*\d+턴  %s 의 \S+ → \S+ 에게 (\d+)" % re.escape(who))
        return sum(int(m.group(1)) for line in b.log for m in [pat.search(line)] if m)

    # ① 설명문 읽기 — 대표 기술을 못 박는다
    check("rank 규칙이 battle 과 같은 모양이다",
          calc._ATK_RANK.pattern == battle._RANK.pattern)
    g = fx(M("화염방사"))["groups"]
    check("화염방사: 10% 화상", len(g) == 1 and g[0]["chance"] == 0.1
          and g[0]["effects"] == [{"kind": "status", "options": ["화상"]}], g)
    g = fx(M("원시의힘"))["groups"]
    check("원시의힘: 10% **한 번에** 다섯 능력 (주사위 한 번)",
          len(g) == 1 and len(g[0]["effects"]) == 5 and g[0]["chance"] == 0.1, g)
    g = fx(M("인파이트"))["groups"]
    check("인파이트: 자기 방어·특방 -1 은 추가 효과가 아니다 (우격다짐이 안 지운다)",
          len(g) == 1 and g[0]["chance"] == 1.0 and not g[0]["secondary"], g)
    check("섀도볼은 추가 효과가 있다 / 인파이트·지진은 없다",
          calc.has_secondary(M("섀도볼")) and not calc.has_secondary(M("인파이트"))
          and not calc.has_secondary(M("지진")))
    check("트라이어택: 셋 중 하나", fx(M("트라이어택"))["groups"][0]["effects"][0]
          ["options"] == ["마비", "화상", "얼음"])
    check("소금절이처럼 모르는 상태는 안 건다 (자리를 차지해서 틀린다)",
          fx(M("소금절이"))["groups"][0]["effects"][0]["kind"] == "unknown_status")
    check("질투의불꽃은 '...한 경우' 라 조건부다", fx(M("질투의불꽃"))["groups"][0]["cond"])
    names = lambda key: {m["name"] for m in dex.moves
                         if m["category"] != "변화" and fx(m)[key]}
    check("공격 후 교체: 유턴·볼트체인지·퀵턴", names("self_switch")
          == {"유턴", "볼트체인지", "퀵턴"}, names("self_switch"))
    check("스스로 기절: 자폭·대폭발·미스트버스트", names("self_faint")
          == {"자폭", "대폭발", "미스트버스트"}, names("self_faint"))
    check("흡수 8개 (드레인키스 3/4)", len(names("drain")) == 8
          and fx(M("드레인키스"))["drain"] == 0.75, names("drain"))
    check("스케일샷 2~5회 / 트리플악셀 위력 20·40·60 / 찍찍베기 빗나가면 끝",
          fx(M("스케일샷"))["hits"] == (2, 5)
          and fx(M("트리플악셀"))["powers"] == [20, 40, 60]
          and fx(M("찍찍베기"))["stop_on_miss"])
    check("연속기 14개가 여러 번 때린다 (거대해머는 연속 '사용' 금지일 뿐이라 빠진다)",
          len(names("hits")) == 14 and "거대해머" not in names("hits"), names("hits"))

    # ② 데미지 계산부터 달라지는 것
    def dmg(a, b, move, **kw):
        A, B = P(a), P(b)
        for k, v in kw.items():
            if k.startswith("a_"):
                setattr(A, k[2:], v)
            else:
                setattr(B, k, v)
        return calc.calc_damage(dex, A, B, M(move))

    base = dmg("아머까오", "하마돈", "바디프레스")["max"]
    up_def = dmg("아머까오", "하마돈", "바디프레스",
                 a_ranks={"defense": 2, "attack": 0})["max"]
    up_atk = dmg("아머까오", "하마돈", "바디프레스",
                 a_ranks={"attack": 2, "defense": 0})["max"]
    check("바디프레스: 자기 방어가 오르면 세지고 공격은 상관없다 (%d / 방어+2 %d / 공격+2 %d)"
          % (base, up_def, up_atk), up_def > base * 1.8 and up_atk == base)
    base = dmg("다크펫", "한카리아스", "속임수")["max"]
    foe_up = dmg("다크펫", "한카리아스", "속임수", ranks={"attack": 2, "defense": 0})["max"]
    me_up = dmg("다크펫", "한카리아스", "속임수", a_ranks={"attack": 2})["max"]
    check("속임수: 상대 공격이 오르면 세지고 내 공격은 상관없다 (%d / %d / %d)"
          % (base, foe_up, me_up), foe_up > base * 1.8 and me_up == base)
    r = dmg("나인테일", "누리레느", "프리즈드라이")
    check("프리즈드라이: 물·페어리 누리레느에게 2배 (%.1f)" % r["effectiveness"],
          r["effectiveness"] == 2.0)
    a1 = dmg("갑주무사", "하마돈", "성스러운칼")["max"]
    a2 = dmg("갑주무사", "하마돈", "성스러운칼", ranks={"defense": 2})["max"]
    check("성스러운칼: 상대 방어 +2 를 무시한다 (%d / %d)" % (a1, a2), a1 == a2)
    k1 = dmg("갑주무사", "하마돈", "탁쳐서떨구기")["max"]
    k0 = dmg("갑주무사", "하마돈", "탁쳐서떨구기", item=None)["max"]
    km = dmg("갑주무사", "보만다", "탁쳐서떨구기")["max"]
    km0 = dmg("갑주무사", "보만다", "탁쳐서떨구기", item=None)["max"]
    check("탁쳐서떨구기: 도구가 있으면 1.5배, 메가스톤은 아니다 (%d/%d, 메가 %d/%d)"
          % (k1, k0, km, km0), k1 > k0 * 1.4 and km == km0)
    h0 = dmg("다크펫", "하마돈", "병상첨병")["max"]
    h1 = dmg("다크펫", "하마돈", "병상첨병", status="화상")["max"]
    v1 = dmg("다크펫", "하마돈", "베놈쇼크", status="화상")["max"]
    v2 = dmg("다크펫", "하마돈", "베놈쇼크", status="독")["max"]
    check("병상첨병은 상태 이상이면 2배, 베놈쇼크는 독일 때만 (%d/%d, %d/%d)"
          % (h0, h1, v1, v2), h1 > h0 * 1.8 and v2 > v1 * 1.8)
    # (숫자가 작으면 버림 때문에 1.3배가 1.25배로 보인다 — 크게 들어가는 상대로 잰다)
    f0 = dmg("하마돈", "아머까오", "화염방사")["max"]
    f1 = dmg("하마돈", "아머까오", "화염방사", a_ability="우격다짐")["max"]
    c0 = dmg("하마돈", "누리레느", "인파이트")["max"]
    c1 = dmg("하마돈", "누리레느", "인파이트", a_ability="우격다짐")["max"]
    check("우격다짐: 추가 효과가 있는 기술만 1.3배 (화염방사 %d→%d, 인파이트 %d→%d)"
          % (f0, f1, c0, c1), f1 >= f0 * 1.25 and c1 == c0)

    # ③ 대전에서 실제로 걸리는가
    b = duel(P("보만다"), P("하마돈"), [M("용성군")], [iron])
    check("용성군: 쓰고 나면 특공 -2", b.me.ranks["spAtk"] == -2, b.me.ranks)
    b = duel(P("빠르모트"), P("하마돈"), [M("인파이트")], [iron])
    check("인파이트: 방어·특방 -1", b.me.ranks["defense"] == -1
          and b.me.ranks["spDef"] == -1, b.me.ranks)
    b = duel([P("갑주무사"), P("하마돈")], P("누리레느"), [M("유턴")], [iron])
    check("유턴: 때리고 교체한다", b.me.name == "하마돈" and dealt(b, "갑주무사") > 0,
          b.log)
    b = duel(P("갑주무사"), P("누리레느"), [M("유턴")], [iron])
    check("유턴: 바꿀 놈이 없으면 그대로", b.me.name.endswith("갑주무사"), b.me.name)
    b = duel(P("빠르모트"), P("하마돈"), [M("드레인펀치")], [iron], my_hp=[50])
    hit = dealt(b, "빠르모트")
    healed = [int(x) for x in re.findall(r"드레인펀치 — (\d+) 흡수", " ".join(b.log))]
    check("드레인펀치: 준 데미지의 절반을 회복 (%d → %s)" % (hit, healed),
          healed == [hit // 2], b.log)
    me = P("빠르모트")
    me.item = "큰뿌리"
    b = duel(me, P("하마돈"), [M("드레인펀치")], [iron], my_hp=[50])
    healed2 = [int(x) for x in re.findall(r"드레인펀치 — (\d+) 흡수", " ".join(b.log))]
    check("큰뿌리: 흡수가 더 많다 (%s vs %s)" % (healed2, healed),
          healed2 and healed2[0] > healed[0], b.log)
    b = duel(P("갑주무사"), P("하마돈"), [M("탁쳐서떨구기")], [iron])
    check("탁쳐서떨구기: 도구가 없어진다 (%s)" % b.opp.item, b.opp.item is None, b.log)
    b = duel([P("하마돈"), P("누리레느")], P("한카리아스"), [M("대폭발")], [M("방어")])
    check("대폭발: 막혀도 쓴 쪽은 쓰러진다", not b.me_party.members[0].alive, b.log)
    b = duel(P("하마돈"), P("누리레느"), [M("거대해머")] * 3, [iron] * 3)
    check("거대해머: 두 번 연달아는 실패, 한 턴 쉬면 다시 된다",
          said(b, "두 번 연달아") and len([l for l in b.log if "거대해머 →" in l]) == 2,
          b.log)
    hits = []
    for seed in range(40):
        b = duel(P("한카리아스"), P("하마돈"), [M("스케일샷")], [iron], seed=seed)
        m = re.search(r"(\d)번 맞았다", " ".join(b.log))
        if m:
            hits.append(int(m.group(1)))
    check("스케일샷이 여러 번 때린다 (2~5회: %s)" % sorted(set(hits)),
          hits and min(hits) >= 2 and max(hits) <= 5 and len(set(hits)) >= 3, hits)
    # 사용자가 확인해 줌 (2026-09-22): '2~5회' 기술은 맞으면 **반드시 2회까지는** 맞는다.
    # (두 번째부터 명중을 다시 굴리는 것은 '도중에 빗나가면 끝' 이 적힌 기술뿐)
    short = 0
    for seed in range(200):
        b = duel(P("하마돈"), P("아머까오"), [M("록블라스트")], [iron], seed=seed)
        m = re.search(r"(\d+)번 맞았다", " ".join(b.log))
        if said(b, "록블라스트 →") and b.opp.alive and (not m or int(m.group(1)) < 2):
            short += 1
    check("2~5회 기술은 맞으면 반드시 2회 이상 (200판 중 1회로 끝난 판 %d)" % short,
          short == 0, short)
    b = duel(P("한카리아스"), P("하마돈"), [M("스케일샷")], [iron], seed=3)
    check("스케일샷: 다 때린 뒤 방어 -1 · 스피드 +1 (한 번만)",
          b.me.ranks["defense"] == -1 and b.me.ranks["speed"] == 1, b.me.ranks)
    # ! 메가스톤을 든 몸(한카리아스)에 특성을 덮어쓰면 **안 먹는다** — Side 가 기본 폼
    #   Build 를 따로 만들어 시작하기 때문이다. 처음에 그렇게 짜서 '3번' 이 나왔다.
    #   메가가 아닌 하마돈으로 잰다.
    counts = []
    for seed in range(20):
        me = P("하마돈")
        me.ability = "스킬링크"
        b = duel(me, P("아머까오"), [M("록블라스트")], [iron], seed=seed)
        m = re.search(r"(\d)번 맞았다", " ".join(b.log))
        if m:
            counts.append(int(m.group(1)))
    check("스킬링크: 맞으면 언제나 5번 (%s)" % sorted(set(counts)),
          counts and set(counts) == {5}, counts)
    # 기합의띠는 연속기의 **첫 방만** 버틴다 (합쳐서 한 번에 넣으면 끝까지 버틴다 — 틀림)
    held = 0
    for seed in range(20):
        me = P("하마돈")
        me.ability = "스킬링크"
        me.ranks = dict(me.ranks, attack=6)   # 첫 방이 확실히 한 방 거리가 되게
        frail = P("파이어로")                 # 불꽃·비행 — 바위 4배
        frail.item = "기합의띠"
        # (상대가 철벽을 먼저 쓰면 한 방 거리가 아니게 된다 — 처음에 그래서 재현이 안 됐다)
        b = duel(me, frail, [M("록블라스트")], [M("칼춤")], seed=seed)
        if said(b, "기합의띠 로 HP 1"):
            held += 1
            check("기합의띠는 연속기의 첫 방만 버티고 다음 방에 쓰러진다",
                  not b.opp.alive, b.log)
            break
    check("기합의띠 장면을 재현했다", held == 1, held)
    # 확률 — 400번 쏴서 화상 10% 근처인가
    burns = 0
    for seed in range(400):
        b = battle.Battle(dex, P("보만다"), P("하마돈"), rng=random.Random(seed),
                          my_fresh=True, opp_fresh=True)
        b.step(M("화염방사"), iron)
        burns += b.opp.status == "화상"
    check("화염방사 화상은 400번 중 10%% 근처 (%d번)" % burns, 20 <= burns <= 60, burns)
    both = only_one = 0
    for seed in range(300):
        b = battle.Battle(dex, P("하마돈"), P("누리레느"), rng=random.Random(seed),
                          my_fresh=True, opp_fresh=True)
        b.step(M("원시의힘"), iron)
        up = [b.me.ranks[s] > 0 for s in ("attack", "defense", "spAtk", "spDef", "speed")]
        both += all(up)
        only_one += any(up) and not all(up)
    check("원시의힘: 오를 때는 다섯이 같이 오른다 (다 %d번 / 일부만 %d번)"
          % (both, only_one), both > 10 and only_one == 0, (both, only_one))
    blocked = 0
    for seed in range(100):
        tough = P("누리레느")
        tough.ability = "인분"
        b = battle.Battle(dex, P("다크펫"), tough, rng=random.Random(seed),
                          my_fresh=True, opp_fresh=True)
        b.step(M("섀도볼"), iron)
        blocked += b.opp.ranks["spDef"] < 0
    check("인분: 섀도볼 특방 하락을 100번 중 한 번도 안 받는다 (%d)" % blocked,
          blocked == 0, blocked)
    burned = recoil = 0
    for seed in range(100):
        sf = P("하마돈")
        sf.ability, sf.item = "우격다짐", "생명의구슬"
        b = battle.Battle(dex, sf, P("누리레느"), rng=random.Random(seed), log=True,
                          my_fresh=True, opp_fresh=True)
        b.step(M("화염방사"), iron)
        burned += b.opp.status == "화상"
        recoil += said(b, "생명의구슬 반동")
    check("우격다짐: 추가 효과도 생명의구슬 반동도 없다 (화상 %d · 반동 %d)"
          % (burned, recoil), burned == 0 and recoil == 0, (burned, recoil))
    b = battle.Battle(dex, P("누리레느"), P("하마돈"), rng=random.Random(1), log=True,
                      my_fresh=True, opp_fresh=True)
    b.opp.status = "얼음"
    b.step(M("열탕"), iron)
    check("열탕: 맞은 쪽의 얼음이 녹는다", b.opp.status != "얼음", b.log)
    # 풀죽음은 상대가 **아직 안 움직였을 때만** 소용있다
    flinched = 0
    for seed in range(100):
        b = battle.Battle(dex, P("하마돈"), P("보만다"), rng=random.Random(seed),
                          log=True, my_fresh=True, opp_fresh=True)
        b.step(M("악의파동"), iron)          # 하마돈이 보만다보다 느리다
        flinched += said(b, "풀죽")
    check("느린 쪽의 악의파동은 풀죽이지 못한다 (%d)" % flinched, flinched == 0, flinched)

    # ④ 한 턴 표도 연속기를 여러 번으로 본다
    e = best.expected_hits(M("스케일샷"))
    t = best.expected_hits(M("트리플악셀"), 0.9)
    # 2~5회 확률은 사용자가 확인해 준 값: 37.5 / 37.5 / 12.5 / 12.5 → 평균 3.0회.
    # (처음엔 본편 5세대 값 35/35/15/15 = 평균 3.1회를 썼다 — 틀렸다)
    check("연속기 2~5회 확률이 사용자가 확인해 준 값이다 (%s)"
          % calc.CONFIG["multi_hit_2to5"],
          calc.CONFIG["multi_hit_2to5"] == [0.375, 0.375, 0.125, 0.125])
    check("한 턴 표: 스케일샷 평균 %.2f방 · 트리플악셀(명중 90%%) %.2f배" % (e, t),
          abs(e - 3.0) < 1e-9 and abs(t - (1 + 0.9 * 2 + 0.81 * 3)) < 1e-9, (e, t))
    one = best.rate_moves(dex, P("한카리아스"), P("하마돈"), [(M("스케일샷"), None)])[0]
    check("한 턴 표의 기대 데미지가 1회분의 약 3배다 (%.1f / 1회 %.1f)"
          % (one["expected"], one["res"]["max"]),
          one["expected"] > one["res"]["min"] * 2.5, one)


def test_zoom_lens(dex):
    """포커스렌즈 — "상대보다 행동 순서가 늦으면 기술의 명중률이 1.2배가 된다."

    2026-09-22 까지 **한 번도 안 돌았다.** `_hit` 이 늘 순서 자리에 None 을 받아서
    '후공이면' 이 늘 거짓이었다. `APPLIED_ITEM_KINDS` 에 들어 있어서 경고도 없었다 —
    CLAUDE.md §5 가 제일 고약하다고 한 '붙었다고 말하면서 안 도는' 종류다.
    명중 80% 스톤에지로 잰다: 늦게 치면 96%, 먼저 치면 그대로 80%.
    """
    import battle, random
    print("\n[50] 포커스렌즈 — 늦게 치면 명중 1.2배")
    P = lambda n: calc.popular_build(dex, dex.find_pokemon(n))[0]
    M = dex.find_move

    def rate(me_name, op_name, lens, n=600):
        hit = 0
        for seed in range(n):
            me = P(me_name)
            me.item = "포커스렌즈" if lens else "먹다남은음식"
            b = battle.Battle(dex, me, P(op_name), rng=random.Random(seed), log=True,
                              my_fresh=True, opp_fresh=True)
            b.step(M("스톤에지"), M("철벽"))
            hit += not any("스톤에지 — 빗나감" in line for line in b.log)
        return hit * 100.0 / n

    slow = P("하마돈").stat("speed") < P("보만다").stat("speed")
    check("하마돈이 보만다보다 느리다 (시험의 전제)", slow)
    late_lens = rate("하마돈", "보만다", True)
    late_none = rate("하마돈", "보만다", False)
    early_lens = rate("보만다", "하마돈", True)
    check("늦게 치면 포커스렌즈로 명중이 오른다 (%.0f%% vs 렌즈 없이 %.0f%%)"
          % (late_lens, late_none), late_lens >= 92 and late_none <= 86,
          (late_lens, late_none))
    check("먼저 치면 포커스렌즈가 안 든다 (%.0f%%)" % early_lens,
          early_lens <= 86, early_lens)


def test_fixed_ohko_minimize(dex):
    """정해진 양이 들어가는 기술 · 일격필살 · 명중률/회피율 랭크 · 작아지기 (2026-09-22).

    전에는 나이트헤드·지구던지기·분노의앞니·목숨걸기·일격필살 4개가 **위력 1** 로
    계산됐다 (한 턴 표는 '아래 숫자는 무시할 것' 이라고만 적었다). 작아지기(장침바루 44%)는
    '효과를 못 읽었다' 로만 떴다 — 회피율 랭크가 모델에 없었다.
    """
    import battle, best, random, re
    print("\n[51] 고정 데미지 · 일격필살 · 명중/회피 랭크 · 작아지기")
    P = lambda n: calc.popular_build(dex, dex.find_pokemon(n))[0]
    M = dex.find_move
    iron = M("철벽")

    def duel(me, op, mine, theirs, seed=1, **kw):
        kw.setdefault("my_fresh", True)
        kw.setdefault("opp_fresh", True)
        b = battle.Battle(dex, me, op, rng=random.Random(seed), log=True, **kw)
        for a, o in zip(mine, theirs):
            b.step(a, o)
        return b

    def said(b, text):
        return any(text in line for line in b.log)

    def hit_of(b, who, move):
        m = re.search(r"%s 의 %s → \S+ 에게 (\d+)" % (re.escape(who), move), " ".join(b.log))
        return int(m.group(1)) if m else 0

    # ① 정해진 양
    r = calc.calc_damage(dex, P("다크펫"), P("하마돈"), M("나이트헤드"))
    check("나이트헤드: 상대가 누구든 50 (%s~%s)" % (r.get("min"), r.get("max")),
          r.get("min") == r.get("max") == 50, r)
    r = calc.calc_damage(dex, P("다크펫"), P("잠만보"), M("나이트헤드"))
    check("나이트헤드: 노말에게는 안 통한다 (타입 무효는 탄다)", "error" in r, r)
    r = calc.calc_damage(dex, P("잠만보"), P("하마돈"), M("지구던지기"))
    check("지구던지기: 50", r.get("max") == 50, r)
    b = duel(P("잠만보"), P("하마돈"), [M("분노의앞니")], [iron])
    check("분노의앞니: 상대 남은 HP 의 절반 (%d / 최대 %d)"
          % (hit_of(b, "잠만보", "분노의앞니"), b.opp.max_hp),
          hit_of(b, "잠만보", "분노의앞니") == b.opp.max_hp // 2, b.log)
    row = best.rate_moves(dex, P("다크펫"), P("하마돈"), [(M("나이트헤드"), None)])[0]
    check("한 턴 표도 나이트헤드를 50 으로 본다 (%.1f)" % row["expected"],
          abs(row["expected"] - 50) < 1e-9, row.get("expected"))

    # ② 목숨걸기 — 맞으면 자기 HP 만큼 주고 쓰러진다, 안 통하면 안 쓰러진다
    b = duel([P("하마돈"), P("누리레느")], P("한카리아스"), [M("목숨걸기")], [iron])
    check("목숨걸기: 자기 HP 만큼 주고 쓰러진다 (%d)" % hit_of(b, "하마돈", "목숨걸기"),
          hit_of(b, "하마돈", "목숨걸기") == b.me_party.members[0].max_hp
          and not b.me_party.members[0].alive, b.log)
    b = duel([P("하마돈"), P("누리레느")], P("다크펫"), [M("목숨걸기")], [iron])
    check("목숨걸기: 고스트에게 막히면 안 쓰러진다", b.me_party.members[0].alive, b.log)

    # ③ 일격필살
    hit = None
    for seed in range(30):
        b = duel(P("잠만보"), P("누리레느"), [M("땅가르기")], [iron], seed=seed)
        if said(b, "땅가르기 →"):
            hit = b
            break
    check("땅가르기: 맞으면 한 방에 쓰러진다", hit is not None and not hit.opp.alive,
          hit.log if hit else None)
    tough = P("누리레느")
    tough.ability = "옹골참"
    b = duel(P("잠만보"), tough, [M("땅가르기")], [iron], seed=1)
    check("옹골참: 일격필살이 안 통한다 (설명문에서 읽음)",
          b.opp.alive and b.opp.hp == b.opp.max_hp, b.log)
    r = calc.calc_damage(dex, P("얼음귀신"), P("얼음귀신"), M("절대영도"))
    check("절대영도: 얼음타입에게는 안 맞는다", "error" in r, r)

    def ohko_rate(user, move, n=600, evasion=0):
        hits = 0
        for seed in range(n):
            b = battle.Battle(dex, P(user), P("누리레느"), rng=random.Random(seed),
                              my_fresh=True, opp_fresh=True)
            b.opp.ranks["evasion"] = evasion
            b.step(M(move), iron)
            hits += not b.opp.alive
        return hits * 100.0 / n
    ice = ohko_rate("얼음귀신", "절대영도")
    check("절대영도: 얼음타입이 쓰면 30%% 근처 (%.0f%%)" % ice, 24 <= ice <= 36, ice)
    fissure = ohko_rate("잠만보", "땅가르기")
    fissure_eva = ohko_rate("잠만보", "땅가르기", evasion=2)
    check("일격필살 명중은 고정 — 회피율 +2 에도 그대로 (%.0f%% / %.0f%%)"
          % (fissure, fissure_eva), abs(fissure - fissure_eva) < 1e-9
          and 24 <= fissure <= 36, (fissure, fissure_eva))
    other = ohko_rate("잠만보", "절대영도")          # 잠만보는 얼음타입이 아니다
    check("절대영도: 얼음타입이 아니면 20%% 근처 (%.0f%%)" % other,
          14 <= other <= 26, other)

    # ④ 명중률·회피율 랭크 — 스톤에지(80%) 에 회피율 +2 면 80 x 3/5 = 48%
    def edge_rate(eva, n=600):
        hits, warned = 0, False
        for seed in range(n):
            b = battle.Battle(dex, P("하마돈"), P("누리레느"), rng=random.Random(seed),
                              log=True, my_fresh=True, opp_fresh=True)
            b.opp.ranks["evasion"] = eva
            b.step(M("스톤에지"), iron)
            hits += not said(b, "스톤에지 — 빗나감")
            warned = warned or any("회피율 랭크" in w for w in b.warnings)
        return hits * 100.0 / n, warned
    base_rate, w0 = edge_rate(0)
    eva_rate, w2 = edge_rate(2)
    check("회피율 +2 면 명중이 준다 (%.0f%% → %.0f%%, 기대 80 → 48)" % (base_rate, eva_rate),
          74 <= base_rate <= 86 and 42 <= eva_rate <= 54, (base_rate, eva_rate))
    # 배율은 사용자가 확인해 줌 (나무위키 '포켓몬스터/랭크' 2.1.2) — 표를 한 칸씩 대조한다
    want = {-6: 3 / 9., -5: 3 / 8., -4: 3 / 7., -3: 3 / 6., -2: 3 / 5., -1: 3 / 4., 0: 1.0,
            1: 4 / 3., 2: 5 / 3., 3: 6 / 3., 4: 7 / 3., 5: 8 / 3., 6: 9 / 3.}
    bad = {n: battle.accuracy_stage_mult(n) for n in want
           if abs(battle.accuracy_stage_mult(n) - want[n]) > 1e-12}
    check("명중률/회피율 배율이 확인된 표(−6~+6)와 13칸 모두 같다", not bad, bad)
    check("±6 을 넘으면 6 으로 자른다 (명중 −6 · 회피 +6 = −12 → −6)",
          battle.accuracy_stage_mult(-12) == want[-6]
          and battle.accuracy_stage_mult(12) == want[6])
    check("확인된 값이라 '미확인' 경고를 안 띄운다", not w2 and not w0, (w0, w2))

    # ⑤ 작아지기
    b = duel(P("누리레느"), P("잠만보"), [M("작아지기")], [iron])
    check("작아지기: 회피율 +2 · 작아지기 상태", b.me.ranks["evasion"] == 2 and b.me.minimized,
          b.me.ranks)
    b = duel(P("누리레느"), P("잠만보"), [M("작아지기"), iron], [iron, M("누르기")])
    ctl = duel(P("누리레느"), P("잠만보"), [iron, iron], [iron, M("누르기")])
    check("누르기: 작아진 상대에게 2배 (%d vs 대조 %d)"
          % (hit_of(b, "잠만보", "누르기"), hit_of(ctl, "잠만보", "누르기")),
          hit_of(b, "잠만보", "누르기") > hit_of(ctl, "잠만보", "누르기") * 1.8, (b.log, ctl.log))
    missed = 0
    for seed in range(100):
        b = duel(P("누리레느"), P("렌트라"), [M("작아지기"), iron], [iron, M("썬더다이브")],
                 seed=seed)
        missed += said(b, "썬더다이브 — 빗나감")
    check("썬더다이브: 작아진 상대에게 반드시 명중 (회피율 +2 인데도 100번 중 %d번 빗나감)"
          % missed, missed == 0, missed)
    b = battle.Battle(dex, [P("누리레느"), P("하마돈")], P("잠만보"), rng=random.Random(1),
                      my_fresh=True, opp_fresh=True)
    b.step(M("작아지기"), iron)
    b.step(("교체", 1), iron)
    check("교체하면 작아지기가 풀린다", not b.me_party.members[0].minimized
          and b.me_party.members[0].ranks["evasion"] == 0, b.me_party.members[0].ranks)


def test_abilities_batch1(dex):
    """특성 1차 (2026-09-22). 사용률에 나오는 202개 중 105개가 코드에 이름조차 없었다.

    사용자: "빠진 특성들 무조건 넣어야함. 재생력은 핵심 특성중 하나. 판을 뒤집기도함."
    ① 목록 밖 특성은 대전이 **반드시 경고**하고, 그 경고가 탐색 결과(창)까지 간다.
    ② 설명문 규칙이 딱 그 특성만 잡는다. ③ 특성마다 답이 뻔한 상황 + 대조군.
    ! 메가스톤 든 몸에 특성을 덮어쓰면 안 먹는다 (Side 가 기본 폼으로 시작) — 메가가
      아닌 몸으로만 시험한다.
    """
    import battle, search, random, re
    print("\n[52] 특성 1차 — 재생력·흡수·오기·접촉 계열 …")
    P = lambda n: calc.popular_build(dex, dex.find_pokemon(n))[0]
    M = dex.find_move
    iron = M("철벽")

    def ab(name, ability, item=None):
        b = P(name)
        b.ability = ability
        if item is not None:
            b.item = item
        return b

    # ! 메가스톤을 든 몸은 특성을 덮어써도 안 먹는다 — 여기 쓰는 몸들이 안 들었는지 한 번 본다
    used = ["하마돈", "누리레느", "빠르모트", "더시마사리", "윈디", "고릴타", "대도각참"]
    stone = [n for n in used if P(n).item in dex.mega_by_item]
    check("(전제) 특성을 바꿔 쓰는 몸들이 메가스톤을 안 든다", not stone, stone)

    def duel(me, op, mine, theirs, seed=1, **kw):
        kw.setdefault("my_fresh", True)
        kw.setdefault("opp_fresh", True)
        b = battle.Battle(dex, me, op, rng=random.Random(seed), log=True, **kw)
        for a, o in zip(mine, theirs):
            b.step(a, o)
        return b

    def said(b, text):
        return any(text in line for line in b.log)

    def hit_of(b, who, move):
        m = re.search(r"%s 의 %s → \S+ 에게 (\d+)" % (re.escape(who), move), " ".join(b.log))
        return int(m.group(1)) if m else 0

    # ① 경고 장치 — '지금 안 들어간 특성' 을 하나 골라 쓴다 (특성을 붙일수록 바뀌므로
    #    이름을 박지 않는다. 처음엔 노가드로 짰다가 2차에서 노가드를 붙이자 깨졌다)
    left = sorted(a["name"] for a in dex.abilities
                  if a["name"] not in battle.handled_abilities(dex))
    check("(전제) 아직 안 들어간 특성이 남아 있다 (%d개)" % len(left), left, len(left))
    odd = left[0] if left else None
    strange = P("하마돈")
    strange.ability = odd
    b = battle.Battle(dex, P("누리레느"), strange, rng=random.Random(1),
                      my_fresh=True, opp_fresh=True)
    check("목록 밖 특성('%s')은 경고한다" % odd,
          any("'%s'" % odd in w and "안 들어간다" in w for w in b.warnings), b.warnings)
    b = battle.Battle(dex, P("하마돈"), P("누리레느"), rng=random.Random(1),
                      my_fresh=True, opp_fresh=True)
    check("처리되는 특성끼리면 특성 경고가 없다",
          not any("특성" in w and "안 들어간다" in w for w in b.warnings), b.warnings)
    got = search.best_action(dex, [strange], [dex.find_pokemon("누리레느")], seconds=1.0)
    check("탐색 결과에 대전 경고가 담긴다 (전엔 버렸다)",
          any("'%s'" % odd in w for w in got.get("warnings") or []), got.get("warnings"))
    check("창·보고서가 쓰는 경고 줄에 나온다",
          any(odd in l for l in search.warning_lines(got)), search.warning_lines(got))

    # ② 규칙이 딱 그 특성만 잡는다
    kinds = {}
    for a in dex.abilities:
        for r in battle.ability_rules(dex, a["name"]):
            kinds.setdefault(r["kind"], set()).add(a["name"])
    want = {
        "switch_heal": {"재생력"}, "switch_cure": {"자연회복"},
        "absorb": {"축전", "저수", "타오르는불꽃", "피뢰침", "건조피부", "초식", "흙먹기", "전기엔진"},
        "defiant": {"오기", "승기"}, "contrary": {"심술꾸러기"}, "simple": {"단순"},
        "drop_proof": {"괴력집게", "부풀린가슴"},
        "contact_status": {"정전기", "불꽃몸", "독가시", "포자"},
        "poison_touch": {"독수"}, "stench": {"악취"}, "contact_drop": {"미끈미끈", "컬리헤어"},
        "aftermath": {"유폭"}, "long_reach": {"원격"}, "moxie": {"자기과신"},
        "hit_by_type": {"정의의마음", "열교환", "주눅"}, "berserk": {"발끈"},
        "steadfast": {"불굴의마음"}, "anger_point": {"분노의경혈"},
        "pickpocket": {"나쁜손버릇"}, "magician": {"매지션"}, "sticky": {"점착"},
        "liquid_ooze": {"해감액"}, "damp": {"습기"}, "sand_force": {"모래의힘"},
    }
    for k, names in want.items():
        check("규칙 %s 가 %s 만 잡는다" % (k, "·".join(sorted(names))),
              kinds.get(k, set()) == names, kinds.get(k))
    check("조사 '이/가' 를 둘 다 받는다 (전기엔진·부풀린가슴·불굴의마음이 빠질 뻔했다)",
          {"전기엔진", "부풀린가슴", "불굴의마음", "주눅"}
          <= set().union(*kinds.values()))
    for a in dex.abilities:
        for r in battle.ability_rules(dex, a["name"]):
            if r["kind"] == "absorb":
                check("받아내는 %s(%s) 는 한 턴 표의 무효 목록에도 있다" % (a["name"], r["type"]),
                      r["type"] in calc.DEFENDER_IMMUNE.get(a["name"], []),
                      calc.DEFENDER_IMMUNE.get(a["name"]))

    # ③ 재생력 · 자연회복
    b = battle.Battle(dex, [P("더시마사리"), P("누리레느")], P("하마돈"),
                      rng=random.Random(1), log=True, my_fresh=True, opp_fresh=True,
                      my_hp=[40, 100])
    before = b.me_party.members[0].hp
    b.step(("교체", 1), iron)
    after = b.me_party.members[0].hp
    check("재생력: 물러나면 최대 HP 1/3 회복 (%d → %d, 최대 %d)"
          % (before, after, b.me_party.members[0].max_hp),
          after - before == b.me_party.members[0].max_hp // 3, (before, after))
    nc = ab("하마돈", "자연회복")
    b = battle.Battle(dex, [nc, P("누리레느")], P("한카리아스"), rng=random.Random(1),
                      log=True, my_fresh=True, opp_fresh=True)
    b.me.status = "화상"
    b.step(("교체", 1), iron)
    check("자연회복: 물러나면 상태 이상이 낫는다", b.me_party.members[0].status is None,
          b.me_party.members[0].status)

    # ④ 받아내기
    b = duel(P("빠르모트"), ab("누리레느", "축전"), [M("10만볼트")], [iron], opp_hp=[50])
    check("축전: 전기 기술을 받아내고 1/4 회복",
          said(b, "받아내고") and b.opp.hp > b.opp.max_hp // 2, b.log)
    b = duel(P("빠르모트"), ab("누리레느", "피뢰침"), [M("10만볼트")], [iron])
    check("피뢰침: 받아내고 특공 +1, 데미지 0",
          b.opp.ranks["spAtk"] == 1 and b.opp.hp == b.opp.max_hp, b.log)
    b = duel(P("빠르모트"), ab("누리레느", "전기엔진"), [M("10만볼트")], [iron])
    check("전기엔진: 받아내고 스피드 +1", b.opp.ranks["speed"] == 1, b.log)
    b = duel(P("하마돈"), ab("누리레느", "흙먹기"), [M("지진")], [iron], opp_hp=[50])
    check("흙먹기: 땅 기술을 받아내고 회복", said(b, "받아내고")
          and b.opp.hp > b.opp.max_hp // 2, b.log)
    ff = duel(ab("윈디", "타오르는불꽃"), P("하마돈"), [iron, M("화염방사")],
              [M("화염방사"), iron])
    ctl = duel(ab("윈디", "위협"), P("하마돈"), [iron, M("화염방사")], [iron, iron])
    check("타오르는불꽃: 받아낸 뒤 불꽃 기술이 세진다 (%d vs 대조 %d)"
          % (hit_of(ff, "윈디", "화염방사"), hit_of(ctl, "윈디", "화염방사")),
          hit_of(ff, "윈디", "화염방사") > hit_of(ctl, "윈디", "화염방사") * 1.3, (ff.log, ctl.log))

    # ⑤ 능력 변화 계열
    b = duel(P("보만다"), ab("누리레느", "오기"), [iron], [iron])
    check("오기: 위협을 받으면 공격 +2 (−1 +2 = +1)", b.opp.ranks["attack"] == 1, b.opp.ranks)
    b = duel(P("보만다"), ab("누리레느", "승기"), [iron], [iron])
    check("승기: 위협을 받으면 특공 +2", b.opp.ranks["spAtk"] == 2, b.opp.ranks)
    b = duel(P("보만다"), ab("누리레느", "괴력집게"), [iron], [iron])
    check("괴력집게: 위협에 공격이 안 깎인다", b.opp.ranks["attack"] == 0, b.opp.ranks)
    b = duel(ab("누리레느", "심술꾸러기"), P("하마돈"), [M("용성군")], [iron])
    check("심술꾸러기: 용성군이 특공을 +2 로", b.me.ranks["spAtk"] == 2, b.me.ranks)
    b = duel(ab("하마돈", "단순"), P("누리레느"), [M("칼춤")], [iron])
    check("단순: 칼춤이 +4", b.me.ranks["attack"] == 4, b.me.ranks)

    # ⑥ 접촉 계열 (확률은 여러 판으로)
    def rate(attacker, defender, move, test, n=200):
        k = 0
        for seed in range(n):
            bb = battle.Battle(dex, attacker(), defender(), rng=random.Random(seed),
                               log=True, my_fresh=True, opp_fresh=True)
            bb.step(M(move), iron)
            k += bool(test(bb))
        return k * 100.0 / n
    par = rate(lambda: P("한카리아스"), lambda: ab("하마돈", "정전기"), "역린",
               lambda bb: bb.me.status == "마비")
    par_eq = rate(lambda: P("한카리아스"), lambda: ab("하마돈", "정전기"), "지진",
                  lambda bb: bb.me.status == "마비")
    check("정전기: 접촉기에 30%% 근처 마비 (%.0f%%), 비접촉기(지진)엔 0%% (%.0f%%)"
          % (par, par_eq), 18 <= par <= 42 and par_eq == 0, (par, par_eq))
    grass = rate(lambda: P("고릴타"), lambda: ab("하마돈", "포자"), "우드해머",
                 lambda bb: bb.me.status is not None)
    check("포자: 풀타입에게는 안 통한다 (%.0f%%)" % grass, grass == 0, grass)
    helmet = rate(lambda: ab("누리레느", "원격"), lambda: ab("하마돈", "정전기", "울퉁불퉁멧"),
                  "아쿠아제트", lambda bb: bb.me.hp < bb.me.max_hp or bb.me.status)
    check("원격: 울퉁불퉁멧·정전기를 안 받는다 (%.0f%%)" % helmet, helmet == 0, helmet)
    b = duel(P("한카리아스"), ab("하마돈", "미끈미끈"), [M("역린")], [iron])
    check("미끈미끈: 접촉한 쪽 스피드 −1", b.me.ranks["speed"] == -1, b.me.ranks)
    b = duel(P("한카리아스"), ab("하마돈", "유폭"), [M("역린")], [iron], opp_hp=[5])
    check("유폭: 접촉기로 쓰러뜨리면 1/4 을 잃는다",
          b.me.max_hp - b.me.hp == b.me.max_hp // 4 and not b.opp.alive, b.log)
    poi = rate(lambda: ab("누리레느", "독수"), lambda: P("하마돈"), "아쿠아제트",
               lambda bb: bb.opp.status == "독")
    check("독수: 접촉기로 30%% 근처 독 (%.0f%%)" % poi, 18 <= poi <= 42, poi)
    b = duel(ab("하마돈", "자기과신"), P("누리레느"), [M("지진")], [iron], opp_hp=[5])
    check("자기과신: 쓰러뜨리면 공격 +1", b.me.ranks["attack"] == 1 and not b.opp.alive,
          b.me.ranks)
    b = duel(P("대도각참"), ab("하마돈", "정의의마음"), [M("깨물어부수기")], [iron])
    check("정의의마음: 악 기술을 맞으면 공격 +1", b.opp.ranks["attack"] == 1, b.opp.ranks)
    b = duel(P("한카리아스"), ab("하마돈", "발끈"), [M("역린")], [iron], opp_hp=[60])
    check("발끈: 반 아래로 떨어지면 특공 +1",
          b.opp.ranks["spAtk"] == 1 and b.opp.hp <= b.opp.max_hp / 2, (b.opp.hp, b.opp.ranks))

    # ⑦ 그 밖
    b = duel(P("빠르모트"), ab("하마돈", "해감액"), [M("드레인펀치")], [iron], my_hp=[50])
    check("해감액: 흡수하려던 쪽이 오히려 잃는다", said(b, "흡수하려다")
          and b.me.hp < int(round(b.me.max_hp * 0.5)), b.log)
    b = duel(P("하마돈"), ab("누리레느", "습기"), [M("대폭발")], [iron])
    check("습기: 폭발 기술이 안 나가고 쓴 쪽도 안 쓰러진다", b.me.alive
          and said(b, "습기"), b.log)
    b = duel(P("대도각참"), ab("하마돈", "점착"), [M("탁쳐서떨구기")], [iron])
    check("점착: 탁쳐서떨구기로 도구가 안 떨어진다", b.opp.item == "자뭉열매", b.opp.item)
    # (하마돈 특성을 모래의힘으로 바꾸면 모래날림이 없어져 모래바람이 안 분다 — 직접 깐다.
    #  처음에 그걸 몰라서 40 대 40 이 나왔다)
    def sand_hit(ability):
        bb = battle.Battle(dex, ab("하마돈", ability), P("누리레느"), rng=random.Random(1),
                           log=True, my_fresh=True, opp_fresh=True)
        bb.field.set("모래바람")
        bb.step(M("지진"), iron)
        return hit_of(bb, "하마돈", "지진")
    sf, ctl = sand_hit("모래의힘"), sand_hit("모래숨기")      # 대조: 위력과 상관없는 특성
    check("모래의힘: 모래바람에서 땅 기술 1.3배 (%d vs 대조 %d)" % (sf, ctl),
          sf >= ctl * 1.2, (sf, ctl))


def test_abilities_batch2(dex):
    """특성 2차 (2026-09-22) — 명중·급소·랭크 무시 · 틀깨기 · 매직가드 · 매직미러 …"""
    import battle, random, re
    print("\n[53] 특성 2차 — 틀깨기·매직가드·노가드·천진 …")
    P = lambda n: calc.popular_build(dex, dex.find_pokemon(n))[0]
    M = dex.find_move
    iron = M("철벽")

    def ab(name, ability, item=None):
        b = P(name)
        b.ability = ability
        if item is not None:
            b.item = item
        return b

    def duel(me, op, mine, theirs, seed=1, **kw):
        kw.setdefault("my_fresh", True)
        kw.setdefault("opp_fresh", True)
        b = battle.Battle(dex, me, op, rng=random.Random(seed), log=True, **kw)
        for a, o in zip(mine, theirs):
            b.step(a, o)
        return b

    def said(b, text):
        return any(text in line for line in b.log)

    def hit_of(b, who, move):
        m = re.search(r"%s 의 %s → \S+ 에게 (\d+)" % (re.escape(who), move), " ".join(b.log))
        return int(m.group(1)) if m else 0

    def rate(make, move, test, n=300, opp_move=None, setup=None):
        k = 0
        for seed in range(n):
            me, op = make()
            bb = battle.Battle(dex, me, op, rng=random.Random(seed), log=True,
                               my_fresh=True, opp_fresh=True)
            if setup:
                setup(bb)
            bb.step(M(move), opp_move or iron)
            k += bool(test(bb))
        return k * 100.0 / n

    missed = lambda mv: (lambda bb: not any((mv + " — 빗나감") in l for l in bb.log))

    kinds = {}
    for a in dex.abilities:
        for r in battle.ability_rules(dex, a["name"]):
            kinds.setdefault(r["kind"], set()).add(a["name"])
    want = {"magic_guard": {"매직가드"}, "mold_breaker": {"틀깨기"}, "infiltrator": {"틈새포착"},
            "magic_bounce": {"매직미러"}, "no_guard": {"노가드"}, "rock_head": {"돌머리"},
            "unaware": {"천진"}, "no_crit": {"조가비갑옷", "전투무장"}, "acc_mult": {"복안"},
            "keen_eye": {"날카로운눈", "발광"}, "block_priority": {"여왕의위엄", "테일아머"},
            "crit_up": {"대운"}, "crit_vs_status": {"무도한행동"},
            "evasion_when": {"눈숨기", "모래숨기", "갈지자걸음"}, "sand_immune": {"모래숨기", "방진"},
            "entry_drop": {"위협", "감미로운꿀"}, "unnerve": {"긴장감"}, "corrosion": {"부식"},
            "synchronize": {"싱크로"}, "supreme": {"총대장"}, "screen_cleaner": {"배리어프리"},
            "hit_field": {"넘치는씨", "모래뿜기"}, "early_bird": {"일찍기상"},
            "flower_veil": {"플라워베일"}}
    for k, names in want.items():
        check("규칙 %s 가 %s 만 잡는다" % (k, "·".join(sorted(names))),
              kinds.get(k, set()) == names, kinds.get(k))
    check("calc 의 틀깨기·천진 문장이 battle 규칙과 같은 특성을 잡는다",
          calc.mold_breaker_abilities(dex) == kinds.get("mold_breaker", set())
          and calc.unaware_abilities(dex) == kinds.get("unaware", set()))

    # 매직가드
    b = duel(ab("하마돈", "매직가드", "생명의구슬"), P("누리레느"), [M("지진")], [iron])
    check("매직가드: 생명의구슬 반동이 없다", b.me.hp == b.me.max_hp
          and not said(b, "생명의구슬 반동"), b.log)
    mg = ab("하마돈", "매직가드")
    bb = battle.Battle(dex, mg, P("누리레느"), rng=random.Random(1), my_fresh=True, opp_fresh=True)
    bb.me.status = "독"
    bb.step(iron, iron)
    check("매직가드: 독 데미지를 안 받는다", bb.me.hp == bb.me.max_hp, bb.me.hp)
    b = duel(P("누리레느"), ab("하마돈", "매직가드"), [M("문포스")], [iron])
    check("매직가드: 공격 기술 데미지는 받는다", b.opp.hp < b.opp.max_hp, b.opp.hp)

    # 틀깨기
    r0 = calc.calc_damage(dex, P("하마돈"), ab("누리레느", "부유"), M("지진"))
    r1 = calc.calc_damage(dex, ab("하마돈", "틀깨기"), ab("누리레느", "부유"), M("지진"))
    check("틀깨기: 부유에게도 땅 기술이 맞는다", "error" in r0 and "error" not in r1, (r0, r1))
    m0 = calc.calc_damage(dex, P("하마돈"), ab("누리레느", "멀티스케일"), M("지진"))["max"]
    m1 = calc.calc_damage(dex, ab("하마돈", "틀깨기"), ab("누리레느", "멀티스케일"),
                          M("지진"))["max"]
    check("틀깨기: 멀티스케일을 무시한다 (%d → %d)" % (m0, m1), m1 > m0 * 1.8, (m0, m1))
    b = duel(ab("빠르모트", "틀깨기"), ab("누리레느", "축전"), [M("10만볼트")], [iron])
    check("틀깨기: 축전을 뚫고 맞힌다", hit_of(b, "빠르모트", "10만볼트") > 0, b.log)
    # (한 방 거리여야 옹골참이 발동한다 — 처음엔 +6 지진으로도 누리레느를 못 잡아서
    #  시험이 안 됐다. 바위 4배인 파이어로에게 +6 스톤에지로 잰다)
    def sturdy_left(ability):
        bb = battle.Battle(dex, ab("하마돈", ability), ab("파이어로", "옹골참"),
                           rng=random.Random(2), log=True, my_fresh=True, opp_fresh=True)
        bb.me.ranks["attack"] = 6
        bb.me.ranks["accuracy"] = 6
        bb.step(M("스톤에지"), M("칼춤"))
        return bb.opp.hp
    mb_hp, ctl_hp = sturdy_left("틀깨기"), sturdy_left("모래숨기")
    check("틀깨기: 옹골참을 뚫고 한 방에 쓰러뜨린다 (대조: 옹골참은 HP 1) — %d / %d"
          % (mb_hp, ctl_hp), mb_hp == 0 and ctl_hp == 1, (mb_hp, ctl_hp))

    # 틈새포착 — 리플렉터·대타를 무시
    def with_screen(ability):
        bb = battle.Battle(dex, ab("하마돈", ability), P("누리레느"), rng=random.Random(1),
                           log=True, my_fresh=True, opp_fresh=True)
        bb.opp_party.screens["리플렉터"] = 5
        bb.step(M("지진"), iron)
        return hit_of(bb, "하마돈", "지진")
    s0, s1 = with_screen("모래숨기"), with_screen("틈새포착")
    check("틈새포착: 리플렉터를 무시한다 (%d → %d)" % (s0, s1), s1 > s0 * 1.8, (s0, s1))
    bb = battle.Battle(dex, ab("하마돈", "틈새포착"), P("누리레느"), rng=random.Random(1),
                       log=True, my_fresh=True, opp_fresh=True)
    bb.opp.substitute = 40
    bb.step(M("지진"), iron)
    check("틈새포착: 대타를 무시하고 몸에 넣는다", bb.opp.hp < bb.opp.max_hp
          and bb.opp.substitute == 40, (bb.opp.hp, bb.opp.substitute))

    # 매직미러 — 도깨비불을 되받아친다
    b = duel(P("하마돈"), ab("누리레느", "매직미러"), [M("도깨비불")], [iron])
    check("매직미러: 도깨비불을 되받아쳐 쓴 쪽이 화상", b.me.status == "화상"
          and b.opp.status is None, (b.me.status, b.opp.status))
    b = duel(P("하마돈"), ab("누리레느", "매직미러"), [M("스텔스록")], [iron])
    check("매직미러: 스텔스록도 되받아쳐 쓴 쪽 필드에 깔린다",
          b.me_party.hazards.get("스텔스록") and not b.opp_party.hazards.get("스텔스록"),
          (b.me_party.hazards, b.opp_party.hazards))
    b = duel(P("하마돈"), ab("누리레느", "매직미러"), [M("칼춤")], [iron])
    check("매직미러: 자기에게 쓰는 칼춤은 그대로", b.me.ranks["attack"] == 2, b.me.ranks)

    # 명중 계열 (스톤에지 80%)
    base = rate(lambda: (P("하마돈"), P("누리레느")), "스톤에지", missed("스톤에지"))
    ng = rate(lambda: (ab("하마돈", "노가드"), P("누리레느")), "스톤에지", missed("스톤에지"))
    ng2 = rate(lambda: (P("하마돈"), ab("누리레느", "노가드")), "스톤에지", missed("스톤에지"))
    check("노가드: 양쪽 누구든 100%% (기본 %.0f%% / 내 쪽 %.0f%% / 상대 쪽 %.0f%%)"
          % (base, ng, ng2), ng == 100 and ng2 == 100 and base < 90, (base, ng, ng2))
    ohko = rate(lambda: (ab("잠만보", "노가드"), P("누리레느")), "땅가르기",
                lambda bb: not bb.opp.alive, n=50)
    check("노가드: 일격필살도 맞는다 (%.0f%%)" % ohko, ohko == 100, ohko)
    ce = rate(lambda: (ab("하마돈", "복안"), P("누리레느")), "스톤에지", missed("스톤에지"))
    check("복안: 80 × 1.3 → 100%% (%.0f%%)" % ce, ce == 100, ce)
    def eva2(bb):
        bb.opp.ranks["evasion"] = 2
    ke = rate(lambda: (ab("하마돈", "날카로운눈"), P("누리레느")), "스톤에지",
              missed("스톤에지"), setup=eva2)
    plain = rate(lambda: (P("하마돈"), P("누리레느")), "스톤에지", missed("스톤에지"), setup=eva2)
    check("날카로운눈: 상대 회피율 +2 를 무시 (%.0f%% vs 무시 안 하면 %.0f%%)" % (ke, plain),
          72 <= ke <= 88 and 40 <= plain <= 56, (ke, plain))
    bb = battle.Battle(dex, ab("하마돈", "날카로운눈"), P("누리레느"), rng=random.Random(1),
                       my_fresh=True, opp_fresh=True)
    bb._lower(bb.me, "accuracy", -1, bb.opp, "시험")
    check("날카로운눈: 명중률이 안 깎인다", bb.me.ranks["accuracy"] == 0, bb.me.ranks)
    def snow(bb):
        bb.field.set("눈")
    sc = rate(lambda: (P("하마돈"), ab("누리레느", "눈숨기")), "스톤에지", missed("스톤에지"),
              setup=snow)
    check("눈숨기: 눈에서 명중 80/1.25 = 64%% 근처 (%.0f%%)" % sc, 56 <= sc <= 72, sc)

    # 급소 계열
    crit = rate(lambda: (P("하마돈"), ab("누리레느", "조가비갑옷")), "트릭플라워",
                lambda bb: any("급소!" in l for l in bb.log), n=30)
    crit_mb = rate(lambda: (ab("하마돈", "틀깨기"), ab("누리레느", "조가비갑옷")), "트릭플라워",
                   lambda bb: any("급소!" in l for l in bb.log), n=30)
    check("조가비갑옷: '반드시 급소' 도 급소가 아니다, 틀깨기면 급소 (%.0f%% / %.0f%%)"
          % (crit, crit_mb), crit == 0 and crit_mb == 100, (crit, crit_mb))
    def poison(bb):
        bb.opp.status = "독"
    mc = rate(lambda: (ab("하마돈", "무도한행동"), P("누리레느")), "지진",
              lambda bb: any("급소!" in l for l in bb.log), n=30, setup=poison)
    check("무도한행동: 독 상대에게 반드시 급소 (%.0f%%)" % mc, mc == 100, mc)
    sl = rate(lambda: (ab("하마돈", "대운"), P("누리레느")), "지진",
              lambda bb: any("급소!" in l for l in bb.log), n=800)
    check("대운: 급소 1/8 근처 (%.1f%%, 기본은 1/24≈4.2%%)" % sl, 8 <= sl <= 17, sl)

    # 천진 — 받는 쪽이 천진이면 칼춤 +2 가 안 먹는다 / 때리는 쪽이 천진이면 철벽 +2 무시
    sd = P("하마돈")
    sd.ranks = dict(sd.ranks, attack=2)
    u0 = calc.calc_damage(dex, sd, P("누리레느"), M("지진"))["max"]
    u1 = calc.calc_damage(dex, sd, ab("누리레느", "천진"), M("지진"))["max"]
    u2 = calc.calc_damage(dex, P("하마돈"), P("누리레느"), M("지진"))["max"]
    check("천진(받는 쪽): 상대 칼춤 +2 를 무시 (%d → %d = 기본 %d)" % (u0, u1, u2),
          u1 == u2 < u0, (u0, u1, u2))
    df = P("누리레느")
    df.ranks = dict(df.ranks, defense=2)
    v0 = calc.calc_damage(dex, P("하마돈"), df, M("지진"))["max"]
    v1 = calc.calc_damage(dex, ab("하마돈", "천진"), df, M("지진"))["max"]
    check("천진(때리는 쪽): 상대 철벽 +2 를 무시 (%d → %d)" % (v0, v1), v1 == u2 > v0,
          (v0, v1, u2))

    # 돌머리 — 반동 없음
    b = duel(ab("하마돈", "돌머리"), P("누리레느"), [M("이판사판태클")], [iron])
    check("돌머리: 이판사판태클 반동이 없다", b.me.hp == b.me.max_hp and not said(b, "반동"),
          b.log)

    # 여왕의위엄 — 선제기를 막는다 (나를 겨냥한 것만)
    b = duel(P("누리레느"), ab("하마돈", "여왕의위엄"), [M("아쿠아제트")], [iron])
    check("여왕의위엄: 아쿠아제트가 실패한다", said(b, "선제 기술을 쓸 수 없다")
          and b.opp.hp == b.opp.max_hp, b.log)
    b = duel(P("누리레느"), ab("하마돈", "여왕의위엄"), [M("문포스")], [iron])
    check("여왕의위엄: 선제기가 아니면 맞는다", b.opp.hp < b.opp.max_hp, b.log)

    # 그 밖
    b = duel(ab("하마돈", "모래숨기"), P("누리레느"), [iron], [iron])
    bb = battle.Battle(dex, ab("하마돈", "방진"), P("누리레느"), rng=random.Random(1),
                       my_fresh=True, opp_fresh=True)
    bb.field.set("모래바람")
    bb.opp.types_override = ["노말"]
    bb.me.types_override = ["노말"]
    bb.step(iron, iron)
    check("방진: 모래바람 데미지를 안 받는다 (상대는 받는다)", bb.me.hp == bb.me.max_hp
          and bb.opp.hp < bb.opp.max_hp, (bb.me.hp, bb.opp.hp))
    b = duel(ab("누리레느", "감미로운꿀"), P("하마돈"), [iron], [iron])
    check("감미로운꿀: 나오면 상대 회피율 −1", b.opp.ranks["evasion"] == -1, b.opp.ranks)
    b = duel(ab("하마돈", "배리어프리"), P("누리레느"), [iron], [iron])
    bb = battle.Battle(dex, [P("하마돈"), ab("누리레느", "배리어프리")], P("누리레느"),
                       rng=random.Random(1), log=True, my_fresh=True, opp_fresh=True)
    bb.opp_party.screens["리플렉터"] = 5
    bb.step(("교체", 1), iron)
    check("배리어프리: 나오면 벽이 사라진다", not bb.opp_party.screens, bb.opp_party.screens)
    b = duel(P("하마돈"), ab("누리레느", "넘치는씨"), [M("지진")], [iron])
    check("넘치는씨: 맞으면 그래스필드", b.field.terrain == "그래스필드", b.field.terrain)
    b = duel(P("누리레느"), ab("하마돈", "모래뿜기"), [M("문포스")], [iron])
    check("모래뿜기: 맞으면 모래바람", b.field.weather == "모래바람", b.field.weather)
    # 반 아래로 떨어졌는데도 자뭉열매가 안 터져야 한다 (대조: 긴장감이 없으면 터진다)
    def berry_after(ability):
        me = P("누리레느")
        me.item = "자뭉열매"
        bb = duel(me, ab("하마돈", ability), [iron], [M("지진")], my_hp=[55])
        return bb.me.hp <= bb.me.max_hp // 2 or bb.me.item_used, bb.me.item_used
    dropped_un, ate_un = berry_after("긴장감")
    dropped_ctl, ate_ctl = berry_after("모래숨기")
    check("긴장감: 반 아래로 떨어져도 나무열매를 못 먹는다 (대조는 먹는다)",
          dropped_un and not ate_un and ate_ctl, (dropped_un, ate_un, ate_ctl))
    b = duel(ab("하마돈", "부식"), P("아머까오"), [M("맹독")], [iron])
    check("부식: 강철타입도 맹독에 걸린다", b.opp.status == "맹독", b.opp.status)
    b = duel(P("하마돈"), ab("누리레느", "싱크로"), [M("도깨비불")], [iron])
    check("싱크로: 화상을 건 쪽도 화상", b.opp.status == "화상" and b.me.status == "화상",
          (b.me.status, b.opp.status))
    def supreme(n_down):
        team = [ab("대도각참", "총대장")] + [P("누리레느")] * 3
        bb = battle.Battle(dex, team, P("하마돈"), rng=random.Random(1), log=True,
                           my_fresh=True, opp_fresh=True,
                           my_hp=[100] + [0.0001 if i < n_down else 100 for i in range(3)])
        for i in range(n_down):
            bb.me_party.members[i + 1].hp = 0
        bb.step(M("아이언헤드"), iron)
        return hit_of(bb, "대도각참", "아이언헤드")
    s0, s3 = supreme(0), supreme(3)
    check("총대장: 쓰러진 우리 편 3마리면 30%% 세다 (%d → %d)" % (s0, s3),
          s3 >= s0 * 1.25, (s0, s3))
    eb = ab("하마돈", "일찍기상")
    bb = battle.Battle(dex, eb, P("누리레느"), rng=random.Random(1), my_fresh=True, opp_fresh=True)
    bb._inflict(bb.me, "잠듦")
    t_eb = bb.me.status_turns
    bb2 = battle.Battle(dex, P("하마돈"), P("누리레느"), rng=random.Random(1),
                        my_fresh=True, opp_fresh=True)
    bb2._inflict(bb2.me, "잠듦")
    check("일찍기상: 잠드는 턴이 절반 (%d vs 대조 %d)" % (t_eb, bb2.me.status_turns),
          t_eb == max(1, bb2.me.status_turns // 2), (t_eb, bb2.me.status_turns))
    fv = ab("고릴타", "플라워베일")
    b = duel(fv, P("보만다"), [iron], [M("도깨비불")])
    check("플라워베일: 풀타입 자신은 위협에도 안 깎이고 화상도 안 걸린다",
          b.me.ranks["attack"] == 0 and b.me.status is None, (b.me.ranks, b.me.status))


def test_abilities_batch3(dex):
    """특성 3차 (2026-09-22) — 폼·특성이 바뀌는 것 · 턴 끝 · 열매 · 나머지 전부.

    이걸로 **사용률에 나오는 특성 202개 중 안 들어간 것이 0개** 가 된다 (싱글에 효과가
    없는 것은 이유와 함께 ABILITY_NO_EFFECT 에).
    """
    import battle, random, re, json
    print("\n[54] 특성 3차 — 폼·특성 바뀜 · 턴 끝 · 열매 …")
    P = lambda n: calc.popular_build(dex, dex.find_pokemon(n))[0]
    M = dex.find_move
    iron = M("철벽")

    def ab(name, ability, item=None):
        b = P(name)
        b.ability = ability
        if item is not None:
            b.item = item
        return b

    def mk(me, op, seed=1, **kw):
        kw.setdefault("my_fresh", True)
        kw.setdefault("opp_fresh", True)
        return battle.Battle(dex, me, op, rng=random.Random(seed), log=True, **kw)

    def said(b, text):
        return any(text in line for line in b.log)

    def hit_of(b, who, move):
        m = re.search(r"%s 의 %s → \S+ 에게 (\d+)" % (re.escape(who), move), " ".join(b.log))
        return int(m.group(1)) if m else 0

    u = json.load(open(paths.data("usage_single.json"), encoding="utf-8"))
    names = {a["name"] for p in u["pokemon"] for a in p["abilities"]}
    left = sorted(names - battle.handled_abilities(dex))
    check("사용률에 나오는 특성 %d개가 전부 계산에 들어간다 (남은 것 %s)" % (len(names), left),
          not left, left)
    kinds = {}
    for a in dex.abilities:
        for r in battle.ability_rules(dex, a["name"]):
            kinds.setdefault(r["kind"], set()).add(a["name"])
    want = {"cursed_body": {"저주받은바디"}, "moody": {"변덕쟁이"}, "harvest": {"수확"},
            "mimicry": {"의태"}, "forecast": {"기분파"}, "mummy": {"미라"},
            "swap_on_contact": {"떠도는영혼"}, "switch_form": {"마이티체인지"},
            "hunger_switch": {"꼬르륵스위치"}, "imposter": {"괴짜"},
            "electromorphosis": {"전기로바꾸기"}, "trace": {"트레이스"}, "cheek_pouch": {"볼주머니"},
            "cloud_nine": {"날씨부정"}, "poison_heal": {"포이즌힐"},
            "status_immune_when": {"리프가드"}, "weather_heal": {"아이스바디", "젖은접시"},
            "gluttony": {"먹보"}, "ripen": {"숙성"}, "cute_charm": {"헤롱헤롱바디"},
            "shed_skin": {"탈피"}, "cud_chew": {"되새김질"}, "hydration": {"촉촉바디"},
            "klutz": {"서투름"}, "liquid_voice": {"촉촉보이스"}, "opportunist": {"편승"}}
    for k, ns in want.items():
        check("규칙 %s 가 %s 만 잡는다" % (k, "·".join(sorted(ns))), kinds.get(k, set()) == ns,
              kinds.get(k))

    # 몸·특성이 바뀌는 것
    dol = P("돌핀맨")
    b = mk([dol, P("하마돈")], P("한카리아스"))
    a0 = b.me.base.stat("attack")
    b.step(("교체", 1), iron)
    b.step(("교체", 0), iron)
    check("마이티체인지: 물러났다 오면 마이티폼 (공격 %d → %d)" % (a0, b.me.base.stat("attack")),
          b.me.base.stat("attack") > a0 * 1.5, b.me.base.poke.get("formName"))
    b = mk(P("한카리아스"), ab("하마돈", "미라"))
    b.step(M("역린"), iron)
    check("미라: 접촉한 쪽 특성이 미라가 된다", b.me.base.ability == "미라", b.me.base.ability)
    b = mk([P("한카리아스"), P("누리레느")], ab("하마돈", "미라"))
    orig = b.me.base.ability
    b.step(M("역린"), iron)
    b.step(("교체", 1), iron)
    check("미라: 물러나면 원래 특성으로 돌아온다", b.me_party.members[0].base.ability == orig,
          b.me_party.members[0].base.ability)
    b = mk(P("한카리아스"), ab("하마돈", "떠도는영혼"))
    mine = b.me.base.ability
    b.step(M("역린"), iron)
    check("떠도는영혼: 서로 특성을 바꾼다", b.me.base.ability == "떠도는영혼"
          and b.opp.base.ability == mine, (b.me.base.ability, b.opp.base.ability))
    b = mk(ab("하마돈", "괴짜"), P("한카리아스"))
    check("괴짜: 나오자마자 상대로 변신 (도구는 자기 것)",
          b.me.base.poke["name"] == "한카리아스" and b.me.item == P("하마돈").item,
          (b.me.base.poke["name"], b.me.item))
    b = mk(ab("누리레느", "트레이스"), P("보만다"))
    check("트레이스: 위협을 받아 와서 위협도 터진다", b.me.base.ability == "위협"
          and b.opp.ranks["attack"] == -1, (b.me.base.ability, b.opp.ranks))

    # 타입이 바뀌는 것
    b = mk(ab("하마돈", "의태"), P("누리레느"))
    b.field.set("그래스필드")
    b.step(iron, iron)
    check("의태: 그래스필드면 풀타입", b.me.types == ["풀"], b.me.types)
    b = mk(ab("하마돈", "기분파"), P("누리레느"))
    b.field.set("비")
    b.step(iron, iron)
    check("기분파: 비면 물타입", b.me.types == ["물"], b.me.types)
    b = mk(ab("하마돈", "꼬르륵스위치"), P("누리레느"))
    b.step(iron, iron)
    check("꼬르륵스위치: 턴 끝마다 모양이 바뀐다", b.me.hangry, b.me.hangry)

    # 맞았을 때
    hit = None
    for seed in range(30):
        bb = mk(P("한카리아스"), ab("하마돈", "저주받은바디"), seed=seed)
        bb.step(M("역린"), iron)
        if bb.me.disabled:
            hit = bb
            break
    check("저주받은바디: 맞으면 그 기술을 봉인한다", hit is not None, None)
    if hit:
        n = len(hit.log)
        hit.step(M("역린"), iron)
        check("봉인된 기술은 실패한다", any("역린 는 봉인됐다" in l for l in hit.log[n:]),
              hit.log[n:])
        for _ in range(4):
            hit.step(iron, iron)
        check("4턴 뒤 봉인이 풀린다", hit.me.disabled is None, hit.me.disabled)
    e1 = mk(P("누리레느"), ab("빠르모트", "전기로바꾸기"))
    e1.step(M("문포스"), iron)
    e1.step(iron, M("10만볼트"))
    e0 = mk(P("누리레느"), ab("빠르모트", "플러스"))
    e0.step(M("문포스"), iron)
    e0.step(iron, M("10만볼트"))
    check("전기로바꾸기: 맞은 다음 전기 기술이 세다 (%d vs 대조 %d)"
          % (hit_of(e1, "빠르모트", "10만볼트"), hit_of(e0, "빠르모트", "10만볼트")),
          hit_of(e1, "빠르모트", "10만볼트") > hit_of(e0, "빠르모트", "10만볼트") * 1.6,
          (e1.log, e0.log))
    inf = 0
    for seed in range(300):
        bb = mk(P("한카리아스"), ab("하마돈", "헤롱헤롱바디"), seed=seed)
        bb.step(M("역린"), iron)
        inf += bb.me.infatuated is not None
    check("헤롱헤롱바디: 30%% × 이성 50%% = 15%% 근처 (%.0f%%)" % (inf / 3.0),
          8 <= inf / 3.0 <= 23, inf)
    check("헤롱헤롱바디는 성별 가정을 경고한다",
          any("성별" in w for w in bb.warnings), bb.warnings)

    # 턴 끝
    bb = mk(ab("하마돈", "변덕쟁이"), P("누리레느"))
    bb.step(iron, iron)
    r = bb.me.ranks
    five = ("attack", "defense", "spAtk", "spDef", "speed")
    # 철벽 +2 에 변덕쟁이 +2 · −1 이 더해져 다섯 능력 합이 정확히 +3 이어야 한다
    check("변덕쟁이: 턴 끝에 하나 +2 · 다른 하나 −1 (합 %+d, 기대 +3)"
          % sum(r[s] for s in five), sum(r[s] for s in five) == 3, r)
    bb = mk(ab("하마돈", "포이즌힐"), P("누리레느"), my_hp=[50])
    bb.me.status = "독"
    h = bb.me.hp
    bb.step(iron, iron)
    check("포이즌힐: 독이면 회복한다", bb.me.hp > h, (h, bb.me.hp))
    for when, abn in (("비", "젖은접시"), ("눈", "아이스바디")):
        bb = mk(ab("누리레느", abn), P("하마돈"), my_hp=[50])
        bb.field.set(when)
        h = bb.me.hp
        bb.step(iron, iron)
        check("%s: %s 에서 회복" % (abn, when), bb.me.hp > h, (h, bb.me.hp))
    bb = mk(ab("누리레느", "촉촉바디"), P("하마돈"))
    bb.field.set("비")
    bb.me.status = "화상"
    bb.step(iron, iron)
    check("촉촉바디: 비에서 상태 이상이 낫는다", bb.me.status is None, bb.me.status)
    cured = 0
    for seed in range(200):
        bb = mk(ab("누리레느", "탈피"), P("하마돈"), seed=seed)
        bb.me.status = "화상"
        bb.step(iron, iron)
        cured += bb.me.status is None
    check("탈피: 30%% 근처로 낫는다 (%.0f%%)" % (cured / 2.0), 18 <= cured / 2.0 <= 42, cured)
    bb = mk(ab("누리레느", "수확", "자뭉열매"), P("하마돈"))
    bb.field.set("쾌청")
    bb.me.item_used = True
    bb.step(iron, iron)
    check("수확: 쾌청이면 먹은 열매가 돌아온다", not bb.me.item_used, bb.me.item_used)
    bb = mk(ab("누리레느", "리프가드"), P("하마돈"))
    bb.field.set("쾌청")
    bb._inflict(bb.me, "화상", by=bb.opp)
    check("리프가드: 쾌청이면 상태 이상에 안 걸린다", bb.me.status is None, bb.me.status)

    # 열매
    def berry_heal(ability):
        bb = mk(ab("누리레느", ability, "자뭉열매"), P("하마돈"), my_hp=[40])
        bb.step(iron, iron)
        return bb.me.hp
    # ! 대조군 특성은 **정말 중립** 이어야 한다. 처음엔 모래숨기로 짰는데 하마돈의 모래바람에서
    #   회피율이 올라 지진을 피해서, 규칙을 꺼도 '보통 121 · 숙성 110' 처럼 갈렸다. 플러스는 싱글에서
    #   아무 일도 안 한다.
    base_h, ripe_h, pouch_h = berry_heal("플러스"), berry_heal("숙성"), berry_heal("볼주머니")
    check("숙성·볼주머니: 자뭉열매 회복이 더 크다 (보통 %d · 숙성 %d · 볼주머니 %d)"
          % (base_h, ripe_h, pouch_h), ripe_h > base_h and pouch_h > base_h,
          (base_h, ripe_h, pouch_h))
    bb = mk(ab("누리레느", "되새김질", "자뭉열매"), P("하마돈"), my_hp=[40])
    bb.step(iron, iron)
    h1 = bb.me.hp
    bb.step(iron, iron)
    check("되새김질: 다음 턴 끝에 한 번 더 먹는다", said(bb, "되새김질") and bb.me.hp > h1,
          bb.log[-3:])
    quarter = [n for n, es in battle.item_behaviors(dex).items() for e in es
               if e.get("kind") == "heal_pinch" and e["at"] <= 0.25]
    check("먹보: 챔피언스엔 1/4 에서 먹는 회복 열매가 없다 (생기면 효과가 난다) %s" % quarter,
          not quarter, quarter)
    bb = mk(ab("누리레느", "플러스", "자뭉열매"), ab("하마돈", "긴장감"), my_hp=[40])
    bb.step(iron, iron)
    check("(대조) 긴장감 상대면 열매를 못 먹는다", not bb.me.item_used, bb.me.item_used)

    # 그 밖
    k = mk(ab("하마돈", "서투름", "생명의구슬"), P("누리레느"))
    k.step(M("지진"), iron)
    c = mk(ab("하마돈", "플러스", "생명의구슬"), P("누리레느"))
    c.step(M("지진"), iron)
    check("서투름: 생명의구슬이 아무 일도 안 한다 (%d vs 대조 %d, 반동 없음)"
          % (hit_of(k, "하마돈", "지진"), hit_of(c, "하마돈", "지진")),
          hit_of(k, "하마돈", "지진") < hit_of(c, "하마돈", "지진")
          and not said(k, "생명의구슬 반동"), (k.log, c.log))
    snd = [m for m in dex.moves if "소리" in (m.get("tags") or []) and m["category"] != "변화"]
    r = calc.calc_damage(dex, ab("누리레느", "촉촉보이스"), P("하마돈"), snd[0])
    check("촉촉보이스: 소리 기술(%s)이 물타입" % snd[0]["name"], r.get("moveType") == "물", r)
    bb = mk(ab("누리레느", "날씨부정"), P("하마돈"))
    bb.step(iron, iron)
    check("날씨부정: 모래바람이 불어도 데미지가 없다", bb.me.hp == bb.me.max_hp
          and bb.field.weather == "모래바람", (bb.me.hp, bb.field.weather))
    bb = mk(ab("하마돈", "편승"), P("누리레느"))
    bb.step(iron, M("칼춤"))
    check("편승: 상대가 칼춤 +2 면 나도 공격 +2", bb.me.ranks["attack"] == 2, bb.me.ranks)
    bb = mk(P("누리레느"), P("조로아크"))
    check("일루전은 '계산 결과 영향 없음' 으로 밝혀 경고 안 한다",
          not any("'일루전'" in w for w in bb.warnings), bb.warnings)


def test_artmatch(dex):
    """[55] 선출 화면에서 상대 6마리를 그림으로 알아보기 (2026-09-22).

    화면 두 장: 사용자 아이패드 녹화(4:3, 2732x2048) · 유튜브 스위치 화면(16:9, 1341x749).
    둘 다 오른쪽 절반만 `data/screens/` 에 있다. 정답은 사용자가 알려 줬다.
    """
    import colorsys
    import artmatch
    import fetch_art
    import pngio
    print("\n[55] 선출 화면 — 상대 6마리를 그림으로")
    here = os.path.dirname(os.path.abspath(__file__))
    truth = {
        "선출_아이패드.png": ["다크펫", "대쓰여너/암컷의 모습", "빠르모트", "블래키", "드래캄", "무장조"],
        "선출_스위치.png": ["플라엣테/영원의 꽃", "아머까오", "더시마사리", "한카리아스", "개굴닌자", "메타몽"],
    }

    def key_of(label):
        name, _, form = label.partition("/")
        hits = [p for p in dex.pokemon if p["name"] == name and not p["isMega"]
                and (not form or p["formName"] == form)]
        assert len(hits) == 1 or not form, label
        return hits[0]["key"]

    def read(fname):
        return pngio.read_png(os.path.join(here, "data", "screens", fname))

    def picks(w, h, px):
        return [r[0][1] for _, _, r in artmatch.identify(w, h, px)]

    # 그림 자료가 게임 자료와 맞는가 — 없으면 그 포켓몬은 영영 못 알아본다
    with open(os.path.join(here, "data", "art", "index.json"), encoding="utf-8") as f:
        index = json.load(f)["art"]
    lacking = [p["key"] for p in dex.pokemon if p["key"] not in index]
    check("게임 자료의 포켓몬 %d개 전부 그림이 있다" % len(dex.pokemon), not lacking, lacking[:5])
    w, h, px = pngio.read_png(os.path.join(here, "data", "art", "0445-00.png"))
    check("그림은 96x96, 투명 바탕", (w, h) == (96, 96) and px[3] == 0, (w, h, px[3]))

    for fname, labels in truth.items():
        want = [key_of(l) for l in labels]
        w, h, px = read(fname)
        found = artmatch.identify(w, h, px)
        ranked = [r for _, _, r in found]
        got = [r[0][1] for r in ranked]
        check("%s: 6마리 전부 맞힘" % fname, got == want,
              [(l, g) for l, g, k in zip(labels, got, want) if g != k])
        if fname == "선출_아이패드.png":
            # 몸에 빨간 곳이 있는 무장조·드래캄 — 바탕에 묻히는 빨간 곳을 셈에서 빼야 확실히 앞선다
            # (빼지 않으면 무장조가 2등과 0.11 차 — 잰 값 0.23)
            gaps = {labels[i]: ranked[i][0][0] - ranked[i][1][0] for i in (4, 5)}
            check("빨간 몸(드래캄·무장조)도 2등과 0.2 넘게 앞선다", min(gaps.values()) > 0.2, gaps)
            # 대쓰여너는 암수 모습이 따로 있다 — 성별 표시(♀)로 수컷 모습을 뺀다 (빼기 전 2등과 0.03 차)
            check("대쓰여너(♀): 수컷 모습이 후보에 없다",
                  all(k != key_of("대쓰여너/수컷의 모습") for _, k in ranked[1]), ranked[1])
        genders = {"선출_아이패드.png": ["수컷", "암컷", "수컷", "암컷", "암컷", "암컷"],
                   "선출_스위치.png": ["암컷", "암컷", "수컷", "암컷", "수컷", None]}[fname]
        check("%s: 성별 표시 6칸 (메타몽은 표시 없음)" % fname,
              [g for _, g, _ in found] == genders, [g for _, g, _ in found])
        if fname == "선출_스위치.png":
            # 틀이 한 칸(4점) 어긋나도 — 기기마다 칸 속 자리가 조금씩 다르다 (잰 폭 0.536~0.584 H)
            old = artmatch.FRAME_X
            artmatch.FRAME_X = old + artmatch.CELL / artmatch.GRID * artmatch.FRAME_SCALE
            try:
                got = picks(w, h, px)
            finally:
                artmatch.FRAME_X = old
            check("그림 틀이 한 칸 어긋나도 6마리 맞힘", got == want,
                  [(l, g) for l, g, k in zip(labels, got, want) if g != k])
        if fname == "선출_아이패드.png":
            # 해상도가 낮아도 — 절반으로 줄인 화면 (가로 683, 스위치 사진보다 거칠다)
            sw, sh, spx = pngio.shrink(w, h, px, max(w, h) // 2)
            got = picks(sw, sh, spx)
            check("아이패드 화면을 절반 해상도로 줄여도 6마리 맞힘", got == want,
                  [(l, g) for l, g, k in zip(labels, got, want) if g != k])
        if fname == "선출_스위치.png":
            # 이로치 흉내 — 그림의 색상을 반 바퀴 돌린다 (사용자: 이로치를 못 알아볼까 봐)
            px2 = bytearray(px)
            for x0, y0, x1, y1 in artmatch.find_panels(w, h, px):
                for y in range(y0, y1):
                    for x in range(x0, (x0 + x1) // 2):
                        i = (y * w + x) * 4
                        r, g, b = px2[i], px2[i + 1], px2[i + 2]
                        if not artmatch.is_panel(r, g, b):
                            hh, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
                            r, g, b = colorsys.hsv_to_rgb((hh + 0.5) % 1, s, v)
                            px2[i], px2[i + 1], px2[i + 2] = int(r * 255), int(g * 255), int(b * 255)
            got = picks(w, h, px2)
            check("그림 색을 반 바퀴 돌려도(이로치) 6마리 맞힘", got == want,
                  [(l, g) for l, g, k in zip(labels, got, want) if g != k])
            # 칸이 6개가 아니면 멈춘다 — 조용히 5마리로 읽지 않는다
            panels = artmatch.find_panels(w, h, px)
            cut = panels[5][1] - 2
            cw, ch, cpx = pngio.crop(w, h, px, 0, 0, w, cut)
            try:
                artmatch.find_panels(cw, ch, cpx)
                stopped = False
            except ValueError as e:
                stopped = "고른 여섯 칸을 못 찾았다" in str(e)
            check("마지막 칸이 잘린 화면은 멈춘다 — 조용히 5마리로 읽지 않는다", stopped)

    # PNG 읽기·쓰기
    tmp = os.path.join(here, "data", "screens", "_검사.png")
    img = bytearray(range(256)) * 3 + bytearray(256)
    pngio.write_png(tmp, 8, 32, img)
    back = pngio.read_png(tmp)
    os.remove(tmp)
    check("PNG 로 쓰고 다시 읽으면 점 하나 안 바뀐다", back == (8, 32, img))
    # champs 그림 목록(CSS) 읽기
    css = ('--sprite-96-04-png:url("https://x/pokemon-sprite-96-04.png?v=1");'
           '.dex-0445-00-96{background-image:var(--sprite-96-04-image-set);'
           '--poke-x:-192px;--poke-y:-576px;}')
    sheets, cells = fetch_art.parse_css(css)
    check("champs 목록: 판 주소와 자리를 읽는다",
          sheets == {"04": "https://x/pokemon-sprite-96-04.png?v=1"}
          and cells == {"0445-00": ("04", 192, 576)}, (sheets, cells))


def test_msgread(dex):
    """[56] 문구 칸 글 → 일어난 일 (2026-09-22).

    아래 글은 사용자 아이패드 녹화 한 판에서 **글자 인식이 실제로 읽은 그대로** 다
    (틀린 글자 포함). 그 판: 내 쪽 하마돈·마폭시·고릴타·보만다·더시마사리·타부자고,
    상대 다크펫·대쓰여너·빠르모트·블래키·드래캄·무장조.
    """
    import msgread
    print("\n[56] 문구 칸 — 글자 인식 결과를 일어난 일로")
    here = ["하마돈", "마폭시", "고릴타", "보만다", "더시마사리", "타부자고",
            "다크펫", "대쓰여너", "빠르모트", "블래키", "드래캄", "무장조"]
    names = msgread.Names(dex, here)
    cases = [
        # (읽힌 글, 종류, 더 맞아야 할 것)
        ("상대 다크펫의 / 폴터가이스트!", "기술", {"mon": "다크펫", "side": "opp", "move": "폴터가이스트"}),
        ("상대 다크표겟의 / 폴터가이스트!", "기술", {"mon": "다크펫", "move": "폴터가이스트"}),
        ("상대 빠르모트의 / 냉등편지!", "기술", {"mon": "빠르모트", "move": "냉동펀치"}),
        ("타부자고의 / 세도볼!", "기술", {"mon": "타부자고", "side": "me", "move": "섀도볼"}),
        ("상대 빠르모들읳 / 회생의기도!", "기술", {"mon": "빠르모트", "move": "회생의기도"}),
        ("효과가 징장했다!", "효과굉장", {}),
        ("그러나 실패하고 말았츈F.!", "실패", {}),
        ("가랏! 하마된", "나옴", {"mon": "하마돈", "side": "me"}),
        ("尼<菂는 / 다크펫을 내보냈다!", "나옴", {"mon": "다크펫", "side": "opp"}),
        ("7든<菂는 / 작은 빠르호트를 내보냈다! •", "나옴", {"mon": "빠르모트", "side": "opp"}),
        ("하마톤 / 돌아와나", "들어감", {"mon": "하마돈", "side": "me"}),
        ("상대 다크펫은 쓰러졌츈P", "쓰러짐", {"mon": "다크펫", "side": "opp"}),
        ("하마돈은 쓰러졌다!", "쓰러짐", {"mon": "하마돈", "side": "me"}),
        # 풍선 문구엔 '상대' 가 없었다 — 그 판의 타부자고는 **내** 것
        ("타부자고는 / 풍선 때문에 떠 있다!", "풍선", {"mon": "타부자고", "side": "me", "item": "풍선"}),
        ("타부자고의 / 풍선이 터졌다!", "풍선터짐", {"mon": "타부자고"}),
        ("상대 다크펫은 타부자고의 / 풍선을 통찰했다!", "통찰",
         {"mon": "다크펫", "side": "opp", "other": "타부자고", "other_side": "me", "item": "풍선"}),
        ("모래바람이 불기 시작飢대", "모래바람시작", {}),
        ("모래 바람이 가라앉았다!)", "모래바람끝", {}),
        ("모래바람이 / 상대 빠르모트를 덮쳤다!", "모래바람데미지", {"mon": "빠르모트", "side": "opp"}),
        ("상대이 주변에 / 뾰족한 바위가 떠다니기 시작했다!", "스텔스록깔림", {}),
        ("상대 대쓰여너에게 / 뾰족한 바위가 박혔다!", "스텔스록데미지", {"mon": "대쓰여너"}),
        ("상대 다크표겟의 / 졸음을 유도했다!", "하품", {"mon": "다크펫"}),
        ("하마돈은 / 앙코르를 받았다!", "앙코르", {"mon": "하마돈", "side": "me"}),
        ("상대 다크뎃은 / 이미 졸린 상태다.", "이미졸림", {"mon": "다크펫"}),
        ("상대 다크펫은 / 쿨쿨 잠들어 있다.", "자는중", {"mon": "다크펫"}),
        ("상대 다크펫은 / 눈을 떴다!", "깸", {"mon": "다크펫"}),
        ("상대 대쓰여너이 / 공격이 떨어졌다!", "능력하락", {"mon": "대쓰여너", "stat": "공격"}),
        ("상대 다크펫은 / 정신을 자려 짜울 수 있게 되었다!", "되살아남", {"mon": "다크펫"}),
        ("상대 다크펫은 상대를- / 길동무로 삼으려 하고 있다!", "길동무", {"mon": "다크펫"}),
        ("상대 다크뎃이 / 길동무!", "기술", {"mon": "다크펫", "move": "길동무"}),
        ("상대 다크펫의 다크펫나이트와 / 尼<菂의 모두링이 반응했다!", "메가반응",
         {"mon": "다크펫", "side": "opp", "item": "다크펫나이트"}),
        ("보만다는 / 메가보만다로 메가진화했다!", "메가진화", {"mon": "보만다", "side": "me"}),
        ("7든<菂와의 / 승부에서 이겼다!", "이김", {}),
    ]
    bad = []
    for text, kind, more in cases:
        ev = msgread.read(text.split(" / "), names)
        if ev["kind"] != kind or any(ev.get(k) != v for k, v in more.items()):
            bad.append((text, ev))
    check("영상 문구 %d개를 일어난 일로 (틀린 글자 포함)" % len(cases), not bad, bad[:3])
    # 문구가 아닌 글 · 너무 깨진 글은 억지로 읽지 않는다 — '못 읽음'
    junk = ["06:43", "(, 06:42", "㉧ 0/3 / 선택 완료", "대기 중", "HP 감소 / 06•34",
            "62마돈테 / 지진!", "t$9C8ttt", "배드렇", "역린!",
            "풍선이 터전다,"]        # 이름이 빠진 문구 — 점수 0.68. 받아들이면 엉뚱한 이름이 붙는다
    wrong = [(t, msgread.read(t.split(" / "), names)["kind"]) for t in junk]
    wrong = [x for x in wrong if x[1] != "못 읽음"]
    check("문구가 아니거나 너무 깨진 글 %d개는 '못 읽음'" % len(junk), not wrong, wrong)
    ev = msgread.read(["상대 다크펫의", "폴터가이스트!"], names)
    check("못 읽음이 아니면 점수가 붙는다 (0.78 이상)", ev["score"] >= msgread.ACCEPT, ev)
    check("자음·모음 풀기: '굉' 과 '징' 은 반쯤 닮았다",
          0.3 < msgread.sim("굉", "징") < 0.8 and msgread.sim("굉장", "굉장") == 1.0,
          msgread.sim("굉", "징"))


def test_screenread(dex):
    """[57] 화면 사진 → 창의 칸 (2026-09-22, 사용자: "창의 칸에 자동으로 채우자").

    + 모습 고르기 — 창 목록이 이름마다 하나라 워시로토무 등 23종을 못 골랐던 것.
    """
    import live
    import msgread
    import screenread
    print("\n[57] 화면 사진 → 창의 칸 · 모습 고르기")
    here = os.path.dirname(os.path.abspath(__file__))
    scr = lambda f: os.path.join(here, "data", "screens", f)

    # -- 모습 고르기 ----------------------------------------------------------
    pk = live.pickable_pokemon(dex)
    keys = {p["key"] for p in pk}
    labels = [live.poke_label(p) for p in pk]
    need = {"0479-02": "로토무(워시로토무)", "0026-01": "라이츄(알로라의모습)",
            "0902-01": "대쓰여너(암컷의모습)", "0128-03": "켄타로스(팔데아의모습/워터종)",
            "0059-01": "윈디(히스이의모습)"}
    check("창 목록에 타입·종족값이 다른 모습이 따로 있다 (워시로토무·알로라 라이츄 …)",
          all(k in keys for k in need) and all(v in labels for v in need.values()),
          [k for k in need if k not in keys])
    check("사용률에 없는 모습은 안 나온다 (킬가르도 블레이드폼 · 비비용 정글의 모양)",
          "0681-01" not in keys and not any(p["name"] == "비비용" and p["formName"] == "정글의 모양"
                                            for p in pk))
    check("창 목록 이름표가 서로 다 다르다 (%d개)" % len(labels), len(set(labels)) == len(labels))
    wash = dex.find_pokemon("0479-02")
    b, _f = live.build_one(dex, wash, {}, None, "", "")
    line = live.party_line(b, ["하이드로펌프"])
    b2, _m, _f2, why = live.read_line(dex, line)
    check("워시로토무를 파티 파일에 적었다 다시 읽어도 워시로토무", b2 is not None
          and b2.poke["key"] == "0479-02", (line, why))
    p, _n = live.find_poke(dex, "라이츄(알로라의 모습)")
    check("띄어쓴 이름표도 받는다: 라이츄(알로라의 모습) → 0026-01", p and p["key"] == "0026-01", p)
    jungle = [x for x in dex.pokemon if x["name"] == "비비용" and x["formName"] == "정글의 모양"][0]
    check("목록에 없는 모습은 같은 이름의 목록 것으로 (비비용 정글 → 팬시한)",
          live.pickable_for(dex, jungle)["formName"] == "팬시한 모양")

    # -- 판에 넣기 (글자 인식 없이) -------------------------------------------
    P = lambda n: dex.find_pokemon(n)
    def board():
        my = [{"poke": P(n), "hp": 100.0, "brought": False} for n in ("하마돈", "타부자고", "보만다")]
        opp = [{"poke": P(n), "hp": 100.0, "brought": False} for n in ("다크펫", "빠르모트")]
        opp += [{"poke": None, "hp": 100.0, "brought": False}]
        return screenread.Board(my, opp)
    bd = board()
    notes = screenread.apply(bd, {"kind": "나옴", "mon": "빠르모트", "side": "opp"}, dex)
    check("상대가 나옴 → 그 칸 냈다·나와 있음·막 나옴",
          bd.opp_active == 1 and bd.opp[1]["brought"] and bd.opp_fresh and notes[0][0], notes)
    screenread.apply(bd, {"kind": "나옴", "mon": "타부자고", "side": "me"}, dex)
    check("내가 냄 → 내 칸 냈다·나와 있음", bd.my_active == 1 and bd.my[1]["brought"] and bd.my_fresh)
    screenread.apply(bd, {"kind": "기술", "mon": "다크펫", "side": "opp", "move": "폴터가이스트"}, dex)
    check("상대가 기술을 씀 → 본 기술 · 그놈이 나와 있음 (나옴 문구를 놓쳐도)",
          bd.seen == {"다크펫": ["폴터가이스트"]} and bd.opp_active == 0 and bd.opp[0]["brought"])
    screenread.apply(bd, {"kind": "쓰러짐", "mon": "다크펫", "side": "opp"}, dex)
    screenread.apply(bd, {"kind": "되살아남", "mon": "다크펫", "side": "opp"}, dex)
    check("쓰러짐 → HP 0, 회생의기도로 되살아남 → HP 50", bd.opp[0]["hp"] == 50.0)
    notes = screenread.apply(bd, {"kind": "나옴", "mon": "드래캄", "side": "opp"}, dex)
    check("프리뷰에 없던 상대 → 빈 칸에 새로 적고 그렇다고 말한다",
          bd.opp[2]["poke"]["name"] == "드래캄" and "새로 적음" in notes[0][1], notes)
    notes = screenread.apply(bd, {"kind": "나옴", "mon": "한카리아스", "side": "me"}, dex)
    check("내 파티에 없는 놈 → 칸을 안 바꾸고 '없음' 이라 말한다",
          bd.my_active == 1 and not notes[0][0] and "없음" in notes[0][1], notes)
    screenread.apply(bd, {"kind": "풍선", "mon": "빠르모트", "side": "opp", "item": "풍선"}, dex)
    screenread.apply(bd, {"kind": "통찰", "mon": "다크펫", "side": "opp",
                          "other": "타부자고", "item": "풍선"}, dex)
    ev = live.evidence_map(bd.seen, [x["poke"] for x in bd.opp], bd.opp_items, bd.opp_abilities)
    check("드러난 상대 도구·특성이 계산(Evidence)까지 간다",
          ev["빠르모트"].item == "풍선" and ev["다크펫"].ability == "통찰"
          and "폴터가이스트" in ev["다크펫"].seen_moves, ev)
    notes = screenread.apply(bd, {"kind": "풍선", "mon": "타부자고", "side": "me", "item": "풍선"}, dex)
    check("내 풍선은 상대 도구로 안 들어간다", "타부자고" not in bd.opp_items, bd.opp_items)
    # (처음엔 능력 하락으로 봤는데 2026-09-23 에 랭크 칸이 생겨 이제 들어간다 — 여전히 칸이 없는 앙코르로)
    notes = screenread.apply(bd, {"kind": "앙코르", "mon": "다크펫", "side": "opp"}, dex)
    check("칸이 없는 일(앙코르)은 '계산엔 안 들어감' 이라 말한다",
          not notes[0][0] and "안 들어감" in notes[0][1] and "앙코르" in notes[0][1], notes)

    # -- 문구 칸 찾기 — 비율로 (4:3 · 16:9) ------------------------------------
    for w, h, lines in ((2732, 2048, [(440, 1597, "상대 다크펫의"), (439, 1689, "폴터가이스트!"),
                                      (2657, 185, "31"), (1310, 1506, "도구")]),
                        (1341, 749, [(216, 568, "상대 개굴닌자는"), (216, 602, "악타입이 됐다!"),
                                     (10, 336, "진짜 무섭긴하네요"), (1120, 278, "개굴닌자의"),
                                     # 같은 자리의 시계 — 한글이 없으니 문구가 아니다
                                     (234, 611, "05:55"), (200, 640, "b")])):
        got = screenread.message_lines(lines, w, h)
        check("문구 칸만 골라낸다 (%dx%d)" % (w, h), got == [lines[0][2], lines[1][2]], got)
    check("사진 크기를 머리만 읽어 안다 (PNG · JPG)",
          screenread.image_size(scr("선출_스위치.png")) == (671, 749)
          and screenread.image_size(scr("대전_스위치_타입바뀜.jpg")) == (1346, 755),   # ffprobe 로 잰 값
          (screenread.image_size(scr("선출_스위치.png")),
           screenread.image_size(scr("대전_스위치_타입바뀜.jpg"))))

    # -- HP 넣기 (글자 인식 없이) --------------------------------------------
    import hpread
    bd = board()
    bd.my[0]["maxhp"], bd.my[1]["maxhp"], bd.my[2]["maxhp"] = 215, 160, 170
    bd.opp_active = 1
    notes = screenread.apply_hp(bd, {"opp_hp": {"hp": 62.3, "warn": None}, "my_hp": (145, 215)})
    check("상대 HP → 나와 있는 상대 칸, 내 HP 145/215 → 67%",
          bd.opp[1]["hp"] == 62.3 and bd.my[0]["hp"] == 67.4, (bd.opp[1], bd.my[0], notes))
    bd.my_active = 1
    notes = screenread.apply_hp(bd, {"my_hp": (100, 215)})
    check("최대 HP 215 가 하마돈 칸과만 같다 → 나와 있는 내 포켓몬을 하마돈으로",
          bd.my_active == 0 and bd.my[0]["hp"] == 46.5 and "하마돈" in notes[0][1], notes)
    bd.my[1]["maxhp"] = 215
    was = bd.my[0]["hp"]
    notes = screenread.apply_hp(bd, {"my_hp": (50, 999)})
    # ★ **안 맞으면 넣지 않는다.** 전에는 경고만 하고 그대로 넣었다. 실전 한 판에서
    #   「0/3」 으로 잘못 읽은 것이 하마돈(215)에 들어가 HP 0% = 쓰러짐이 되었고,
    #   그 판 내내 내 파티가 두 마리로 계산됐다 (2026-09-23 따라간기록_0923_2105).
    check("최대 HP 가 나와 있는 칸과 다르면 **안 넣고** 말한다 (0/3 사고)",
          any(not ok and "안 넣었습니다" in t for ok, t in notes) and bd.my[0]["hp"] == was,
          (notes, bd.my[0]["hp"], was))
    ref, why = hpread.scale(2732, 69.0)
    ref2, why2 = hpread.scale(2732, 90.0)
    check("HP 잣대: 화면 너비 비례 (아이패드 2732 → 69.9), 잰 높이와 10% 넘게 다르면 잰 값 + 알림",
          abs(ref - 69.94) < 0.1 and why is None and ref2 == 90.0 and why2, (ref, why, ref2, why2))

    # -- 사진 통째로 (윈도우 글자 인식 · JPG 바꾸기가 있어야) --------------------
    if os.name != "nt":
        print("  (윈도우가 아니라 사진으로 하는 검사는 건너뜀)")
        return
    import pngio
    pngio_read = lambda p: pngio.read_png(screenread.to_png(p))
    for f, want_hp in (("대전_아이패드_HP87.jpg", 87), ("대전_아이패드_HP4.jpg", 4),
                       ("대전_스위치_HP62.jpg", 62)):
        w, h, px = pngio_read(scr(f))
        m = hpread.measure(w, h, px)
        check("상대 HP 막대: %s → %d%% (±2)" % (f, want_hp), m and abs(m["hp"] - want_hp) <= 2,
              m and round(m["hp"], 1))
        if f == "대전_아이패드_HP87.jpg":
            sw, sh, spx = pngio.shrink(w, h, px, max(w, h) // 2)
            m = hpread.measure(sw, sh, spx)
            check("절반 해상도로 줄여도 87% (±2)", m and abs(m["hp"] - 87) <= 2, m and round(m["hp"], 1))
    w, h, px = pngio_read(scr("대전_아이패드_폴터가이스트.jpg"))
    check("HP 칸이 안 보이는 장면(문구 중)은 HP 를 안 만든다", hpread.measure(w, h, px) is None)
    got = screenread.read_screen(scr("대전_스위치_HP62.jpg"), dex, msgread.Names(dex, []))
    check("스위치 화면: 내 HP 172/191 을 숫자로 읽는다", got.get("my_hp") == (172, 191), got.get("my_hp"))
    names = msgread.Names(dex, ["타부자고", "다크펫", "개굴닌자"])
    want = {"대전_아이패드_풍선.jpg": {"kind": "풍선", "mon": "타부자고", "side": "me"},
            "대전_아이패드_폴터가이스트.jpg": {"kind": "기술", "mon": "다크펫", "side": "opp",
                                           "move": "폴터가이스트"},
            # 작은 화면(1341) — 2배로 키워 읽어야 두 줄이 다 읽힌다
            "대전_스위치_타입바뀜.jpg": {"kind": "타입바뀜", "mon": "개굴닌자", "side": "opp",
                                      "type": "악"}}
    for f, exp in want.items():
        got = screenread.read_screen(scr(f), dex, names)
        ev = got.get("event") or {}
        check("사진 %s → %s" % (f, exp["kind"]), got["kind"] == "대전"
              and all(ev.get(k) == v for k, v in exp.items()), (got.get("lines"), ev))
    got = screenread.read_screen(scr("선출_스위치.png"), dex, names)
    check("선출 화면 사진은 선출로 읽는다 (6마리)", got["kind"] == "선출" and len(got["opp"]) == 6,
          got["kind"])

    # ── 실전 한 판에서 배운 것 (2026-09-23, OBS 캡처 903프레임) ──────────────
    #
    # ★ **막대를 못 찾은 것을 「0%」 로 돌려주고 있었다.** 쓰러지면 상대 칸이 사라지므로 진짜
    #   0% 는 화면에 안 나온다. 실전에서 막대가 잡힌 240프레임 중 **104개(43%)가 0%** 였고
    #   전부 거짓이었다 (메뉴·선출·상태확인 화면의 분홍 띠). 조용히 틀리는 자리였다.
    w, h, px = pngio_read(scr("대전_아이패드_폴터가이스트.jpg"))
    check("막대를 못 찾으면 0% 가 아니라 '못 읽음' 이다", hpread.measure(w, h, px) is None)
    # ★ 글자로 읽은 % 와 막대를 **맞대 본다.** 실전에서 둘 다 읽힌 83프레임 중 진짜 대전 화면에서는
    #   ±1 로 붙었고(86.3/86 · 67.8/68 · 55.9/56 …), 글자는 9번 100% 를 넘었다(109 · 199 · 799).
    cb = screenread.combine_hp
    # ★ 둘이 맞으면 **글자** 를 쓴다 — 글자 % 는 게임이 직접 띄운 수라 오차가 없고,
    #   막대는 잘 맞아도 1~2% 어긋난다 (사용자: "이건 생각보다 큰 문제이다", 2026-09-23).
    check("막대와 글자가 붙으면 **글자** 를 쓴다 (막대 86.3 / 글자 86 → 86)",
          cb({"hp": 86.3}, 86) == (86.0, None), cb({"hp": 86.3}, 86))
    check("글자를 못 읽으면 막대를 쓴다", cb({"hp": 86.3}, None) == (86.3, None))
    check("막대만 있으면 막대", cb({"hp": 67.8}, None) == (67.8, None))
    check("글자만 있으면 글자를 쓴다 (알림 없이 — 게임이 띄운 수다)",
          cb(None, 68) == (68.0, None), cb(None, 68))
    got_v, got_w = cb({"hp": 0.5}, 68)
    check("크게 다르면 **고르지 않고 말한다** (막대 0.5 / 글자 68)",
          got_v is None and got_w and "달라서" in got_w, (got_v, got_w))
    check("둘 다 없으면 아무 말도 안 한다", cb(None, None) == (None, None))
    # 말이 안 되는 글자 % 는 아예 안 받는다 (실전에서 109 · 199 · 799 · 「7」 이 나왔다)
    big = [(2300, 300, "109%"), (2300, 300, "799%")]
    check("100% 를 넘는 글자 % 는 버린다", screenread.opp_hp_text(big, 2448, 1377) is None,
          screenread.opp_hp_text(big, 2448, 1377))
    check("자리가 맞고 100 이하면 받는다",
          screenread.opp_hp_text([(2300, 300, "68%")], 2448, 1377) == 68)
    check("왼쪽 아래 글자는 상대 HP 가 아니다",
          screenread.opp_hp_text([(200, 1300, "68%")], 2448, 1377) is None)

    # ★ **진짜 게임기 화면** (OBS 창 프로젝터 2448x1377). 검사용 선출 사진 2장이 '오른쪽 절반만
    #   잘라 둔 것' 이라 실제와 모양이 달랐고, 그 때문에 실전에서 선출 화면을 통째로 놓쳤다.
    #   이 한 장이 그 재발을 막는다 — 자르지 않은 전체 화면이다.
    real = ["갸라도스", "팬텀", "조로아크", "초염몽", "엘레이드", "루카리오"]
    got = screenread.read_screen(scr("선출_실전OBS.jpg"), dex, names)
    keys = [o["key"] for o in got.get("opp", [])]
    want = [dex.find_pokemon(n)["key"] for n in real]
    check("실전 OBS 선출 화면(자르지 않은 전체): 6마리 전부 맞힘",
          got["kind"] == "선출" and keys == want,
          (got["kind"], [(a, b) for a, b in zip(real, keys) if b not in want]))
    check("실전 OBS 선출 화면: 성별 6칸 (암암수수수수)",
          [o["gender"] for o in got.get("opp", [])] == ["암컷", "암컷", "수컷", "수컷", "수컷", "수컷"],
          [o["gender"] for o in got.get("opp", [])])

    # ★ **「대기 중」 단추도 빨간 띠다.** 선출 화면 오른쪽 아래에 있고 높이가 91~100 —
    #   진짜 칸(146~150)과 다르다. 「띠가 여섯이면 선출」 이었을 때 **위 칸 하나를 놓치고
    #   단추를 여섯 번째로 세는** 프레임들이 있었다 (실전 150프레임 중 여러 장).
    #   그대로 뒀으면 조용히 엉뚱한 여섯 마리를 읽었을 것이다.
    import artmatch as am
    real6 = [(196, 343), (356, 504), (518, 664), (678, 826), (838, 986), (1000, 1147)]
    check("고른 여섯 칸은 고른다", am.pick_six(real6) == real6)
    button = [(404, 504), (518, 665), (678, 825), (838, 986), (999, 1146), (1160, 1253)]
    check("위 칸을 놓치고 「대기 중」 단추를 센 여섯은 **안** 받는다 (높이 100·147·147·147·147·93)",
          am.pick_six(button) is None, am.pick_six(button))
    check("진짜 여섯 칸 + 단추가 같이 보이면 여섯 칸 쪽을 고른다",
          am.pick_six(real6 + [(1160, 1253)]) == real6, am.pick_six(real6 + [(1160, 1253)]))
    check("다섯 개뿐이면 안 받는다", am.pick_six(real6[:5]) is None)

    # ★ **지금 대전 화면인가.** 선출 화면과 「상태 확인」 화면은 상대 여섯 칸을 세로로 쌓아
    #   보여 준다. 그 분홍 칸을 HP 막대로 잘못 읽고 있었다 (실전 한 판에서 대전 시작 전
    #   73프레임 중 41장이 거짓 HP). 잰 것 — 대전 화면 0~1, 선출·상태확인 3~6.
    stacks = {}
    for f in ("대전_아이패드_HP87.jpg", "대전_스위치_HP62.jpg", "선출_실전OBS.jpg",
              "상태확인_실전OBS.jpg"):
        w, h, px = pngio_read(scr(f))
        stacks[f] = am.stack_size(am.panel_bands(w, h, px))
    check("대전 화면은 쌓인 띠가 %d 이하, 선출·상태확인 화면은 %d 이상"
          % (screenread.STACK_MIN - 1, screenread.STACK_MIN),
          max(stacks["대전_아이패드_HP87.jpg"], stacks["대전_스위치_HP62.jpg"])
          < screenread.STACK_MIN
          <= min(stacks["선출_실전OBS.jpg"], stacks["상태확인_실전OBS.jpg"]), stacks)
    got = screenread.read_screen(scr("상태확인_실전OBS.jpg"), dex, names)
    # 「상태 확인」 화면은 이제 그 화면으로 알아보고 **글자로** HP 를 읽는다 ([60]).
    # 여기서 봐야 할 것은 **막대를 안 잰다** 는 것 — 예전엔 분홍 칸을 막대로 읽어 0% 를 냈다.
    w, h, px = pngio_read(scr("상태확인_실전OBS.jpg"))
    check("「상태 확인」 화면에서 HP 막대를 재지 않는다 (예전엔 분홍 칸을 막대로 읽었다)",
          got["kind"] == "상태확인" and "opp_hp" in got and not isinstance(got["opp_hp"], dict),
          (got["kind"], got.get("opp_hp")))
    check("그 화면의 쌓인 띠가 %d 이상이라 대전 화면으로 안 본다" % screenread.STACK_MIN,
          am.stack_size(am.panel_bands(w, h, px)) >= screenread.STACK_MIN)
    got = screenread.read_screen(scr("대전_아이패드_HP87.jpg"), dex, names)
    check("대전 화면에서는 그대로 잰다 (87%)",
          got.get("opp_hp") and abs(got["opp_hp"]["hp"] - 87) <= 2,
          got.get("opp_hp"))
    # 실제로 거짓 HP 를 만들던 그 프레임 — 선출 화면인데 「!」 뱃지와 「대기 중」 단추가 겹쳐
    # 여섯 칸을 못 세고 대전 화면으로 넘어간다. 여기서 HP 를 내놓으면 안 된다.
    w, h, px = pngio_read(scr("선출대기_실전OBS.jpg"))
    bands = am.panel_bands(w, h, px)
    check("「대기 중」 이 겹친 선출 화면은 여섯 칸으로 안 받는다 (띠 높이 %s)"
          % [b - a for a, b in bands], am.pick_six(bands) is None)
    got = screenread.read_screen(scr("선출대기_실전OBS.jpg"), dex, names)
    check("그 화면에서 HP 를 내놓지 않는다 (예전엔 48% 같은 거짓 값이 나왔다)",
          got.get("opp_hp") is None and got.get("opp_hp_text") is None,
          (got.get("opp_hp"), got.get("opp_hp_text")))


def test_read_speed(dex):
    """[59] 사진 읽기를 빠르게 한 것이 **답을 안 바꿨나** (2026-09-23).

    캡처보드 화면을 계속 읽으려면 장당 2.88초로는 안 된다. 네 군데를 고쳤다 —
      1. 색 판정을 `colorsys` 대신 정수 계산으로 (사진 한 장에 230만 번 불렀다)
      2. 대전 화면이면 선출 칸 찾기를 건너뛴다 (0.42초를 통째로 버리고 있었다)
      3. 파워셸을 한 번만 켜 두고 계속 시킨다 (장당 두 번 켜서 0.79초)
      4. 자모 쪼개기·닮은 정도를 외워 둔다 (문구 한 줄에 13만 번·6만 번)
    빠르게 한 것은 **답이 같아야** 뜻이 있다. 그래서 여기서는 속도가 아니라 **답**을 본다.
    (잰 속도: 대전 화면 2.88 → 0.57초, 선출 화면 1.34 → 1.31초. 대전 화면 기준 5배.)
    """
    import artmatch
    import hpread
    import msgread
    import pngio
    import screenread
    print("\n[59] 사진 읽기 빠르게 — 답이 그대로인가")
    here = os.path.dirname(os.path.abspath(__file__))

    # ① 정수 색 판정이 예전 colorsys 판과 같은 답을 주는가.
    #    1,677만 색을 전부 대 봤을 때 다른 것은 is_panel 194 · is_pink 88 · is_fill 667 개뿐이고,
    #    **전부 경계에서 5.6e-17 안**이다 (0.12/6 이 0.019999999999999997 로 나오는 식의 소수 오차).
    #    검사에서는 5칸 걸러 14만 색을 본다 — 다르면 경계에서 1e-9 안이어야 한다.
    import colorsys as _cs
    # ! `_slow_is_panel` 은 rgb 를, `_slow_is_pink/_fill` 은 hsv 를 받는다 — 처음에 셋 다 hsv 로
    #   불러서 42만 색 중 1만 개가 다르다고 나왔다 (검사가 틀린 것이었다).
    pairs = ((lambda r, g, b, h, s, v: artmatch._slow_is_panel(r, g, b),
              artmatch.is_panel, (0.02, 0.88), (0.45,), (0.25, 0.9)),
             (lambda r, g, b, h, s, v: hpread._slow_is_pink(h, s, v),
              hpread.is_pink, (0.86, 0.95), (0.45,), (0.45,)),
             (lambda r, g, b, h, s, v: hpread._slow_is_fill(h, s, v),
              hpread.is_fill, (0.45, 0.955), (0.45,), (0.45,)))
    far = []
    n_diff = n_seen = 0
    for slow, fast, hs, ss, vs in pairs:
        for r in range(0, 256, 5):
            for g in range(0, 256, 5):
                for b in range(0, 256, 5):
                    n_seen += 1
                    hv, sv, vv = _cs.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
                    if slow(r, g, b, hv, sv, vv) != fast(r, g, b):
                        n_diff += 1
                        edge = min([abs(hv - t) for t in hs] + [abs(sv - t) for t in ss]
                                   + [abs(vv - t) for t in vs])
                        if edge > 1e-9:
                            far.append((fast.__name__, r, g, b, edge))
    check("빠른 색 판정이 예전 판과 같은 답 (%d색 중 다른 것 %d개, 전부 경계)" % (n_seen, n_diff),
          not far, far[:3])

    # ② 선출 화면과 대전 화면을 제대로 가르나 — 이름이 「선출」 로 시작하는 사진만 6칸이어야 한다.
    #   ★ 여기 한 번 '싸게 걸러 보기' 를 넣었다가 **실전에서 선출 화면을 통째로 놓쳤다** (§10).
    #     검사용 선출 사진 2장이 오른쪽 절반만 잘라 둔 것이라 문턱이 실제와 안 맞았다.
    #     그래서 지금은 걸러 보기 없이 `find_panels` 하나로만 가른다.
    #   여섯 칸으로 읽혀야 하는 화면만 적는다. 「선출대기_실전OBS.jpg」 는 선출 화면이지만
    #   「!」 뱃지와 「대기 중」 단추가 겹쳐 여섯 칸이 안 세지는 프레임이다 — **못 읽는 게 맞다**
    #   (그 전에는 단추를 칸으로 세어 엉뚱한 여섯을 읽었다).
    six_ok = {"선출_스위치.png", "선출_아이패드.png", "선출_실전OBS.jpg"}
    wrong = []
    for f in sorted(os.listdir(os.path.join(here, "data", "screens"))):
        w, h, px = pngio.read_png(screenread.to_png(os.path.join(here, "data", "screens", f)))
        try:
            n = len(artmatch.find_panels(w, h, px))
        except ValueError:
            n = 0
        if (n == 6) != (f in six_ok):
            wrong.append((f, n))
    check("화면 사진 %d장을 선출(6칸)과 그 밖으로 제대로 가른다"
          % len(os.listdir(os.path.join(here, "data", "screens"))), not wrong, wrong)

    # ③ 외워 둔 것과 **아예 안 외우고 잰 것**이 같은가. 열쇠를 잘못 잡으면 다른 말에 같은 답을 준다.
    #   ! 처음엔 '외운 값끼리' 대 봤는데, 그러면 열쇠를 앞 글자만으로 잡아도 안 걸린다 (일부러
    #     고장 내 보고 알았다). 그래서 외우기를 끄고 잰 값을 정답으로 쓴다.
    words = ["다크펫", "다크팻", "상대다크펫", "지진", "지친", "폴터가이스트", "폴터가0스트", "", "풍선"]
    both = [(a, b) for a in words for b in words]
    old_cache = msgread.USE_CACHE
    try:
        msgread.USE_CACHE = False
        want_sim = [msgread.sim(a, b) for a, b in both]
        want_jamo = [msgread.jamo(a) for a in words]
    finally:
        msgread.USE_CACHE = old_cache
    msgread.forget()
    once = [msgread.sim(a, b) for a, b in both]
    twice = [msgread.sim(a, b) for a, b in both]
    check("외운 닮은 정도가 안 외우고 잰 것과 같다", once == twice == want_sim,
          [(a, b, x, y) for (a, b), x, y in zip(both, once, want_sim) if x != y][:3])
    check("외운 자모 쪼개기도 같다", [msgread.jamo(a) for a in words] == want_jamo,
          [(a, x, y) for a, x, y in zip(words, [msgread.jamo(a) for a in words], want_jamo)
           if x != y][:3])
    check("자모 쪼개기가 맞다 (다크펫)", msgread.jamo("다크펫") == "ㄷㅏㅋㅡㅍㅔㅅ",
          msgread.jamo("다크펫"))

    # ④ 파워셸 일꾼 — 켜 두고 시킨 답이 장마다 새로 켠 답과 같아야 한다.
    #    그리고 ★ **일꾼이 고장 나면 예전 방식으로 돌아가야 한다** (대전 중에 멈추면 안 된다).
    names = msgread.Names(dex, ["다크펫"])
    scr = os.path.join(here, "data", "screens", "대전_아이패드_폴터가이스트.jpg")
    screenread.stop_worker()
    old_use, old_script = screenread.USE_WORKER, screenread.WORKER_SCRIPT
    try:
        screenread.USE_WORKER = False
        alone = screenread.read_screen(scr, dex, names)
        screenread.USE_WORKER = True
        screenread._WORKER = screenread.Worker()
        kept = screenread.read_screen(scr, dex, names)
        check("일꾼을 켜 두고 읽은 것이 장마다 새로 켠 것과 같다", kept == alone,
              (alone.get("lines"), kept.get("lines")))
        check("일꾼을 실제로 썼다 (안 쓰고 지나갔으면 위 검사가 아무것도 안 본 셈)",
              screenread._WORKER.used > 0 and screenread._WORKER.fell_back is None,
              (screenread._WORKER.used, screenread._WORKER.fell_back))
        # 일부러 고장 — 없는 스크립트를 가리킨다
        screenread.stop_worker()
        screenread._WORKER = screenread.Worker()
        screenread.WORKER_SCRIPT = os.path.join(here, "tools", "없는일꾼.ps1")
        broken = screenread.read_screen(scr, dex, names)
        check("일꾼이 고장 나도 예전 방식으로 읽는다 (답 그대로)", broken == alone,
              (alone.get("lines"), broken.get("lines")))
        check("되돌아간 까닭을 남긴다 (조용히 죽지 않는다)",
              bool(screenread._WORKER.fell_back), screenread._WORKER.fell_back)
    finally:
        screenread.stop_worker()
        screenread.USE_WORKER, screenread.WORKER_SCRIPT = old_use, old_script
        screenread._WORKER = screenread.Worker()


def test_watch(dex):
    """[60] 따라가기 — 화면을 계속 읽어 판을 따라간다 (2026-09-23, `watch.py`).

    실전 두 판을 기록해 보고 알게 된 세 가지를 여기서 지킨다 —
    ① **두 장 연속 같을 때만 믿는다** (연출 중간 장면은 HP 가 줄어드는 도중이다)
    ② **같은 일을 두 번 넣지 않는다** (한 문구가 몇 초씩 떠 있어 대여섯 번 읽힌다)
    ③ **신호가 없으면 말한다** (캡처보드가 끊기면 까만 화면 — 그냥 조용하면 멈춘 줄 안다)
    """
    import msgread
    import pngio
    import screenread
    import watch
    print("\n[60] 따라가기 — 화면을 계속 읽어 판을 따라가기")
    here = os.path.dirname(os.path.abspath(__file__))
    names = msgread.Names(dex, ["타부자고", "다크펫"])

    def scr(name):
        return os.path.join(here, "data", "screens", name)

    class Replay(object):
        """저장해 둔 화면을 차례로 내놓는다 (진짜 OBS 창 대신). 끝나면 마지막 것을 되풀이한다."""

        def __init__(self, files):
            self.files, self.i = list(files), 0

        def grab(self):
            f = self.files[min(self.i, len(self.files) - 1)]
            self.i += 1
            w, h, px = pngio.read_png(screenread.to_png(f))
            return f, w, h, px

    def blank():
        return screenread.Board([{"poke": None, "hp": 100.0, "brought": False} for _ in range(6)],
                                [{"poke": None, "hp": 100.0, "brought": False} for _ in range(6)])

    # ① 한 장만 본 것은 안 믿는다. 두 장째에 넣는다.
    w = watch.Watcher(Replay([scr("대전_아이패드_풍선.jpg")]))
    bd = blank()
    a = w.step(bd, dex, names)
    b = w.step(bd, dex, names)
    check("한 장만 본 것은 아직 안 믿는다", not a["changed"], a)
    check("두 장 연속 같으면 믿는다", b["changed"] and b["kind"] == "대전", b)
    # ② 같은 화면이 계속 와도 **두 번은 안 넣는다**
    c = w.step(bd, dex, names)
    d = w.step(bd, dex, names)
    check("같은 화면이 계속 와도 두 번 넣지 않는다", not c["changed"] and not d["changed"], (c, d))
    # 이 화면의 타부자고는 **내 쪽**이다 (문구에 「상대」 가 없다) — 상대 도구로 들어가면 안 된다
    check("판에 한 줄이 들어갔다 (풍선)",
          any("풍선" in t for _ok, t in b["notes"]) and not bd.opp_items,
          (b["notes"], bd.opp_items))

    # ③ 신호 없음 — 까만 화면
    black = os.path.join(here, "data", "screens", "_까망점검.png")
    pngio.write_png(black, 80, 45, bytearray([0, 0, 0, 255] * (80 * 45)))
    try:
        w = watch.Watcher(Replay([black]))
        got = w.step(blank(), dex, names)
    finally:
        os.remove(black)
    check("까만 화면은 '신호가 없습니다' 라고 말한다",
          got["trouble"] and "신호가 없습니다" in got["trouble"], got["trouble"])
    check("신호가 없으면 아무것도 판에 안 넣는다", not got["changed"] and not got["notes"], got)

    # 화면을 못 찍으면 **조용히 지나가지 않는다**
    class Dead(object):
        def grab(self):
            raise RuntimeError("창이 없다")

    got = watch.Watcher(Dead()).step(blank(), dex, names)
    check("화면을 못 찍으면 그렇다고 말한다",
          got["trouble"] and "못 찍었습니다" in got["trouble"], got["trouble"])

    # 끊겼다 이어지면 **기다리던 것을 버린다** — 끊긴 앞뒤 두 장을 같다고 보면 안 된다
    w = watch.Watcher(Replay([scr("대전_아이패드_풍선.jpg")]))
    bd = blank()
    w.step(bd, dex, names)              # 한 장째
    w.source = Dead()
    w.step(bd, dex, names)              # 끊김
    w.source = Replay([scr("대전_아이패드_풍선.jpg")])
    got = w.step(bd, dex, names)        # 이어짐 — 이게 '두 장째' 면 안 된다
    check("끊겼다 이어지면 세던 것을 버리고 다시 센다", not got["changed"], got)

    # ★ **두 번은 잇달아서일 필요가 없다.** 글자 인식은 장마다 다르게 깨진다 — 실전에서
    #   「…패리퍼를 내보냈다!」 를 한 장은 제대로, 다음 장은 「때라퍼를 내보했다!」 로 읽어서
    #   상대가 누구를 냈는지 **영영 못 넣었다** (2026-09-23, 따라간기록_0923_2137).
    #   사이에 못 읽은 장이 끼어도 최근 몇 장 안에서 두 번이면 믿는다.
    shot = scr("대전_아이패드_풍선.jpg")
    other = scr("대전_아이패드_HP87.jpg")      # 문구가 다른 화면 (사이에 끼우는 장)
    w = watch.Watcher(Replay([shot, other, shot]))
    bd = blank()
    one = w.step(bd, dex, names)
    mid = w.step(bd, dex, names)
    two = w.step(bd, dex, names)
    check("사이에 다른 장이 끼어도 같은 것이 두 번 보이면 믿는다",
          not one["changed"] and two["changed"], (one["changed"], mid["changed"], two["changed"]))
    # 그래도 **한 번 본 것은 안 믿는다** — 창이 멀어지면 잊는다
    w = watch.Watcher(Replay([shot] + [other] * watch.RECENT + [shot]))
    bd = blank()
    outs = [w.step(bd, dex, names) for _ in range(watch.RECENT + 2)]
    check("너무 멀리 떨어져 다시 나온 것은 새로 센다 (%d장 뒤)" % watch.RECENT,
          not outs[-1]["changed"], [o["changed"] for o in outs])

    # 새 판 — 잊어야 같은 일을 다시 넣는다
    w = watch.Watcher(Replay([scr("대전_아이패드_풍선.jpg")]))
    bd = blank()
    w.step(bd, dex, names)
    w.step(bd, dex, names)
    w.reset()
    w.step(bd, dex, names)
    got = w.step(bd, dex, names)
    check("새 판(reset)이면 같은 일을 다시 넣는다", got["changed"], got)

    # 「상태 확인」 화면 (게임에서 X) — 한 장에 **내가 낸 3마리**와 상대 HP 가 있다.
    # 글자가 작아 2배로 키워야 읽힌다. 실전 35프레임에서 27장을 이 화면으로 알아봤고
    # (대전·선출 화면에서는 한 번도 헛것이 없었다), 그중 16장이 세 이름을 다 읽었다.
    import live
    mine6 = ["하마돈", "마폭시", "고릴타", "보만다", "더시마사리", "타부자고"]
    opp6 = ["갸라도스", "팬텀", "조로아크", "초염몽", "엘레이드", "루카리오"]

    def full_board():
        return screenread.Board(
            [{"poke": live.pickable_for(dex, dex.find_pokemon(n)), "hp": 100.0,
              "brought": True} for n in mine6],
            [{"poke": live.pickable_for(dex, dex.find_pokemon(n)), "hp": 100.0,
              "brought": False} for n in opp6])

    names6 = msgread.Names(dex, mine6 + opp6)
    w = watch.Watcher(Replay([scr("상태확인_실전OBS.jpg")]))
    bd = full_board()
    w.step(bd, dex, names6)
    got = w.step(bd, dex, names6)
    check("「상태 확인」 화면으로 알아본다", got["kind"] == "상태확인", got["kind"])
    check("낸 3마리를 판에 넣는다 (더시마사리·마폭시·하마돈만 「냈다」)",
          [r["poke"]["name"] for r in bd.my if r["brought"]] == ["하마돈", "마폭시", "더시마사리"],
          [r["poke"]["name"] for r in bd.my if r["brought"]])
    check("상대 HP 68% 를 글자로 읽어 넣는다", bd.opp[0]["hp"] == 68.0, bd.opp[0]["hp"])
    # ★ 셋을 다 못 읽으면 **아예 안 넣는다** — 실전 27프레임 중 11장이 한둘만 읽혔다.
    #   그걸로 나머지의 「냈다」 를 끄면 낸 포켓몬을 안 낸 것으로 만들어 버린다.
    bd = full_board()
    notes = screenread.apply_status(bd, {"mine": ["하마돈"], "opp_hp": None}, dex)
    check("낸 포켓몬을 셋 다 못 읽으면 「냈다」 를 안 건드린다",
          all(r["brought"] for r in bd.my) and any("안 넣었습니다" in t for _o, t in notes), notes)

    # 선출 화면 → 상대 6칸
    w = watch.Watcher(Replay([scr("선출_실전OBS.jpg")]))
    bd = blank()
    w.step(bd, dex, names)
    got = w.step(bd, dex, names)
    got6 = [r["poke"]["name"] if r["poke"] else None for r in bd.opp]
    check("따라가기가 선출 화면의 상대 6마리를 판에 넣는다",
          got["kind"] == "선출"
          and got6 == ["갸라도스", "팬텀", "조로아크", "초염몽", "엘레이드", "루카리오"], got6)

    # ★ **6마리를 알아도 「누가 먼저 나오는지」 는 모른다** (2026-09-23, 사용자가 실전에서 잡음).
    #   `opp_active` 가 0 이라, 상대가 6번 다크펫을 냈는데 **1번 망나뇽의 HP 로 넣고 있었다.**
    #   계산이 통째로 틀리는 자리다 → 모르면 **안 넣고 말한다.**
    check("선출을 읽으면 '누가 먼저 나오는지 모른다' 가 된다", bd.opp_active_known is False)
    notes = screenread.apply_hp(bd, {"opp_hp": None, "opp_hp_text": 80, "opp_name": None})
    check("누가 나와 있는지 모르면 상대 HP 를 안 넣고 말한다",
          bd.opp[0]["hp"] == 100.0 and any("누가 나와 있는지 몰라" in t for _o, t in notes), notes)
    # 이름 칸을 읽으면 그때 정해진다 — HP 가 없어도 정해져야 한다 (예전엔 HP 가 있을 때만 봤다)
    notes = screenread.apply_hp(bd, {"opp_hp": None, "opp_hp_text": None,
                                     "opp_name": ("초염몽", 0.9, "초염몽")})
    check("이름 칸을 읽으면 HP 가 없어도 나와 있는 상대가 정해진다",
          bd.opp_active_known and bd.opp[bd.opp_active]["poke"]["name"] == "초염몽",
          (bd.opp_active_known, bd.opp_active))
    notes = screenread.apply_hp(bd, {"opp_hp": None, "opp_hp_text": 80, "opp_name": None})
    check("정해진 뒤에는 그 칸에 HP 를 넣는다 (초염몽 80%)",
          bd.opp[bd.opp_active]["hp"] == 80.0, bd.opp[bd.opp_active]["hp"])


def test_advice(dex):
    """[61] 「무엇을 하라」 를 말로 해 준다 · 상대가 무엇을 할 것 같은가 (2026-09-23).

    사용자가 실전 한 판을 하고 짚었다 — *"뭘 해야할지 제대로 말을 안해줘. 명확하게
    뭘 해야한다 라고 말해주지않아. 교체를 해야할지 상대 교체를 예측해야할지 기타등등.."*

    그때 창이 내놓던 것은 「=> 하마돈 로 교체 (37.6점 ±6.5, 59판)」 한 줄이었다.
    조사도 틀렸고, 무엇보다 **상대가 무엇을 할지는 한마디도 없었다.**
    """
    import live
    import search
    print("\n[61] 시키는 말 · 상대가 무엇을 할 것 같은가")

    # -- 조사 (받침) — 「하마돈 로 교체」 처럼 틀어지면 사람이 바로 어색해한다
    check("받침 있는 이름은 '으로' (하마돈으로)", search.ro("하마돈") == "으로", search.ro("하마돈"))
    check("받침 없는 이름은 '로' (보만다로)", search.ro("보만다") == "로", search.ro("보만다"))
    # ★ ㄹ 받침은 예외다 — 「따라큐」 가 아니라 「이글이글」 같은 이름에서 걸린다
    check("ㄹ 받침도 '로' (이글이글로)", search.ro("이글이글") == "로", search.ro("이글이글"))
    check("을/를 도 받침으로 (지진을 · 파도타기를)",
          search.has_batchim("지진") and not search.has_batchim("파도타기"))

    # -- 시키는 말 — 기술 · 교체 · 메가가 다 다르게 들려야 한다
    P = lambda n: calc.popular_build(dex, dex.find_pokemon(n))[0]
    mence, hippo, ttar = P("보만다"), P("하마돈"), P("더시마사리")
    party = battle.Party(dex, [mence, hippo, ttar])
    quake = dex.find_move("지진")
    check("기술은 '쓰세요'", search.order_name(dex, party, ("기술", quake)) == "「지진」을 쓰세요",
          search.order_name(dex, party, ("기술", quake)))
    check("교체는 '교체하세요' (조사까지)",
          search.order_name(dex, party, ("교체", 1)) == "「하마돈」으로 교체하세요",
          search.order_name(dex, party, ("교체", 1)))
    check("메가는 '메가진화하고 ~ 쓰세요'",
          search.order_name(dex, party, ("메가", quake)) == "메가진화하고 「지진」을 쓰세요",
          search.order_name(dex, party, ("메가", quake)))
    check("표에 적는 이름도 조사가 맞는다 (하마돈으로 교체)",
          search.action_name(dex, party, ("교체", 1)) == "하마돈으로 교체",
          search.action_name(dex, party, ("교체", 1)))

    # -- 상대가 무엇을 할 것 같은가
    check("상대 예측이 없으면 아무 줄도 안 띄운다", live.opp_guess_lines([]) == [])
    lines = live.opp_guess_lines([("대검돌격", 0.76), ("얼음뭉치", 0.11)], "드닐레이브", 0.53)
    check("제일 아픈 수를 비율과 함께 말한다",
          "「대검돌격」 76%" in lines[0] and "드닐레이브" in lines[0], lines)
    check("상대 메가진화도 따로 말한다 (53%)",
          any("메가진화" in ln and "53%" in ln for ln in lines), lines)
    # ★ **안 센 것을 안 셌다고 말해야 한다.** 이 줄이 없으면 사용자는 '상대 교체까지
    #   따져 봤구나' 로 읽는다 — 조용히 틀리는 자리다.
    check("이번 턴 상대 교체는 안 센다고 밝힌다",
          any("교체하는 경우는 안 셉니다" in ln for ln in lines), lines)
    check("메가가 드물면(5%) 메가 줄은 안 띄운다",
          not any("메가진화" in ln for ln in
                  live.opp_guess_lines([("지진", 0.9)], "하마돈", 0.05)))

    # -- 진짜로 돌려 본다 — 7단계가 그 둘을 실제로 내놓는가
    got = search.best_action(dex, [mence, hippo, ttar],
                             [dex.find_pokemon("드닐레이브"), dex.find_pokemon("짜랑고우거")],
                             seconds=1.5)
    check("후보마다 시키는 말이 붙는다", all(r.get("order") for r in got["rows"]),
          [r.get("order") for r in got["rows"][:3]])
    check("1등의 시키는 말에 그 수의 이름이 들어 있다",
          got["rows"][0]["name"].split()[0][:3] in got["rows"][0]["order"],
          (got["rows"][0]["name"], got["rows"][0]["order"]))
    share = sum(s for _n, s in got["opp_guess"])
    check("상대 예측 비율이 1을 안 넘는다 (%.2f)" % share, 0.0 < share <= 1.0001, got["opp_guess"])
    check("메가 비율은 0~1 (%.2f)" % got["opp_mega"], 0.0 <= got["opp_mega"] <= 1.0)
    # 메가스톤이 없는 상대만 넣으면 메가 비율은 0 이어야 한다
    flat = search.best_action(dex, [mence, hippo], [dex.find_pokemon("하마돈")], seconds=1.0)
    check("메가가 될 수 없는 상대면 메가 비율 0", flat["opp_mega"] == 0.0, flat["opp_mega"])


def test_setup(dex):
    """[62] 기점 잡기 — 상대도 칼춤을 쌓는다 (2026-09-23).

    사용자가 실전 한 판을 보고 짚었다 — *"그냥 상황 해석 자체가 틀림. 따라큐 - 하마돈
    대면에서 왜 하마돈이 게으름 피우기를 해야하지? 따라큐는 탈때문에 안전하게 하마돈을
    칼춤 기점으로 삼을 수 있을건데."*

    그때까지 **양쪽 다 제일 아픈 공격기만** 골랐다. 따라큐가 칼춤을 81.4% 로 들고 오는데
    계산에서는 한 번도 안 썼다. 그러니 하마돈이 그 앞에서 편안해 보였다.

    ★ **이건 정한 규칙이지 잰 것이 아니다.** 「공짜로 한 대를 벌어 주면(탈·대타) 또는
      들어오는 게 지금 HP 의 35% 미만이고 내가 55% 이상 남았으면, 두 단계까지 쌓는다.」
    """
    import random as _r
    import search
    print("\n[62] 기점 잡기 — 상대도 칼춤을 쌓는다")
    P = lambda n: calc.popular_build(dex, dex.find_pokemon(n))[0]
    gain = battle.Policy.setup_gain

    # -- 무엇을 '기점' 으로 보나
    check("칼춤 = 공격 2단계", gain(dex.find_move("칼춤")) == {"attack": 2},
          gain(dex.find_move("칼춤")))
    check("용의춤 = 공격·스피드", gain(dex.find_move("용의춤")) == {"attack": 1, "speed": 1},
          gain(dex.find_move("용의춤")))
    check("나쁜음모 = 특공 2단계", gain(dex.find_move("나쁜음모")) == {"spAtk": 2},
          gain(dex.find_move("나쁜음모")))
    # 대가가 따르거나(저주: 스피드 −1) 공격기이거나 방어만 올리는 것은 기점으로 안 본다
    check("저주는 대가가 있어 기점으로 안 본다", gain(dex.find_move("저주")) is None,
          gain(dex.find_move("저주")))
    check("지진(공격기)은 기점이 아니다", gain(dex.find_move("지진")) is None)
    check("철벽(방어만)은 기점이 아니다 — 때릴 힘이 안 는다",
          gain(dex.find_move("철벽")) is None, gain(dex.find_move("철벽")))

    # -- 따라큐는 탈을 두르고 쌓는다 (7단계가 첫 턴 상대 수를 고르는 자리)
    hip, mimi = P("하마돈"), P("따라큐")
    got = search.best_action(dex, [hip], [dex.find_pokemon("따라큐")],
                             my_moves=["지진", "게으름피우기", "하품", "스텔스록"],
                             seconds=4.0)
    guess = dict(got["opp_guess"])
    check("상대 따라큐가 고를 수로 「칼춤」 이 1등이다 (%s)"
          % ", ".join("%s %.0f%%" % (n, s * 100) for n, s in got["opp_guess"][:2]),
          got["opp_guess"] and got["opp_guess"][0][0] == "칼춤", got["opp_guess"])
    # ★ **답이 뒤집힌다.** 고치기 전에는 하마돈이 81.5% 로 이기는 판이었고 「하품」 을
    #   권했다. 상대가 쌓으면 26% 로 진다 — 사용자가 본 그림과 맞다.
    top = got["rows"][0]
    check("하마돈이 따라큐 앞에서 유리하지 않다 (1등 %s %.0f점)" % (top["name"], top["score"] * 100),
          top["score"] < 0.5, [(r["name"], round(r["score"], 3)) for r in got["rows"][:3]])

    # -- 한 판 돌려 본다: 첫 턴 칼춤, 그 다음엔 때린다 (쌓기만 하지 않는다)
    res = battle.run_once(dex, [hip], [mimi], [dex.find_move("지진")],
                          [dex.find_move("칼춤")], _r.Random(7), log=True,
                          my_moves=["지진", "게으름피우기", "하품", "스텔스록"])
    used = [ln for ln in res["log"] if "따라큐" in ln and "의 " in ln]
    dances = sum(1 for ln in res["log"] if "칼춤" in ln)
    check("+2 까지만 쌓고 그 다음엔 때린다 (칼춤 %d번)" % dances, dances == 1,
          res["log"][:8])
    check("쌓은 따라큐가 하마돈을 이긴다 (%s)" % res["result"], res["result"] == "짐",
          res["result"])

    # -- 더 못 올리는 기술은 되풀이하지 않는다
    mk = battle.Battle(dex, [mimi], [hip], rng=_r.Random(3))
    side = mk.me
    side.ranks["attack"] = 2
    check("+2 면 칼춤을 '다 쌓았다' 로 본다",
          battle.Policy._maxed_setup(side, dex.find_move("칼춤")))
    side.ranks["attack"] = 0
    check("0 이면 아직 쌓을 수 있다",
          not battle.Policy._maxed_setup(side, dex.find_move("칼춤")))
    # 랭크가 꽉 찼는데 또 쓰면 **실패로 적힌다** (전에는 회복기만 그랬다)
    b2 = battle.Battle(dex, [mimi], [hip], rng=_r.Random(3), log=True)
    for _ in range(4):
        b2.step(dex.find_move("칼춤"), dex.find_move("철벽"))
    check("+6 에서 칼춤을 또 쓰면 실패로 친다",
          b2.me.move_failed and any("더 이상 안 변한다" in ln for ln in b2.log),
          [ln for ln in b2.log if "칼춤" in ln])

    # -- 위험하면 안 쌓는다 (한 방에 죽을 만큼 아픈 것이 들어오면)
    # 탈이 없는 놈으로 — 브리두라스가 한카리아스 앞에서 칼춤부터 추면 안 된다
    garch, bri = P("한카리아스"), P("브리두라스")
    b3 = battle.Battle(dex, [bri], [garch], rng=_r.Random(5))
    pol = battle.Policy(dex, [bri], garch, [], lead=b3.me_party.active.base)
    rows = best.rate_moves(dex, b3.me.as_build(), b3.opp.as_build(),
                           [(dex.find_move(m), None) for m in ("칼춤", "지진", "그래스슬라이더")])
    pick_now = pol._setup_move(b3.me, rows, b3)
    check("한 방이 아픈 상대 앞에서는 기점을 안 잡는다 (%s)"
          % (pick_now["name"] if pick_now else "안 쌓음"), pick_now is None, pick_now)
    # 반대로 **탈이 살아 있으면** 아무리 아파도 그 턴은 공짜다 — 사용자가 짚은 바로 그 그림
    b4 = battle.Battle(dex, [mimi], [hip], rng=_r.Random(5))
    pol4 = battle.Policy(dex, [mimi], hip, [], lead=b4.me_party.active.base)
    rows4 = best.rate_moves(dex, b4.me.as_build(), b4.opp.as_build(),
                            [(dex.find_move(m), None) for m in ("칼춤", "치근거리기", "야습")])
    pick4 = pol4._setup_move(b4.me, rows4, b4)
    check("탈이 살아 있으면 기점을 잡는다 (%s)" % (pick4["name"] if pick4 else "안 쌓음"),
          pick4 is not None and pick4["name"] == "칼춤", pick4)
    b4.me.disguise = False
    check("탈이 벗겨진 뒤에는 안 잡는다 (지진이 아프다)",
          pol4._setup_move(b4.me, rows4, b4) is None)


def test_mid_state(dex):
    """[58] 실전 중간 상태 — 상태이상 · 랭크 · 날씨·필드 · 압정을 계산에 넣는다 (2026-09-23).

    전엔 창에 칸이 없어서 계산이 매번 '상태 없음 · 랭크 0 · 날씨는 특성으로 · 압정 없음' 으로 돌았다.
    칸만 있고 계산에 안 들어가면 조용히 틀리므로 **값이 결과를 바꾸는지** 를 본다.
    """
    import random as _r
    import gui
    import live
    import search
    print("\n[58] 실전 중간 상태 — 상태이상·랭크·날씨·압정")
    P = lambda n: calc.popular_build(dex, dex.find_pokemon(n))[0]
    mk = lambda me, op, **kw: battle.Battle(dex, me, op, rng=_r.Random(3), log=True,
                                            my_fresh=False, opp_fresh=False, **kw)
    garch, hippo = P("한카리아스"), P("하마돈")
    quake = dex.find_move("지진")
    iron = dex.find_move("철벽")

    def dmg(**kw):
        b = mk(garch, hippo, **kw)
        before = b.opp.hp
        b.step(quake, iron)
        return before - b.opp.hp

    base = dmg(my_ranks={}, opp_ranks={}, field={"weather": None})
    minus2 = dmg(my_ranks={"attack": -2}, opp_ranks={}, field={"weather": None})
    burned = dmg(my_ranks={}, opp_ranks={}, my_status=["화상"], field={"weather": None})
    check("공격 랭크 −2 를 넘기면 지진 데미지가 준다 (%d → %d)" % (base, minus2),
          0 < minus2 < base * 0.6, (base, minus2))
    check("화상을 넘기면 물리 데미지가 준다 (%d → %d)" % (base, burned), 0 < burned < base * 0.6,
          (base, burned))
    b = mk(garch, hippo, my_ranks={}, opp_ranks={})
    check("날씨 '자동' (field 안 줌) 이면 하마돈 모래날림으로 모래바람", b.field.weather == "모래바람",
          b.field.weather)
    b = mk(garch, hippo, my_ranks={}, opp_ranks={}, field={"weather": None})
    check("날씨 '없음' 을 넘기면 모래날림이 있어도 날씨 없음 (이미 그친 판)", b.field.weather is None,
          b.field.weather)
    b = mk(garch, hippo, my_ranks={}, opp_ranks={}, field={"weather": "비", "weather_turns": 2})
    check("날씨 비 2턴을 넘기면 그대로", (b.field.weather, b.field.weather_turns) == ("비", 2))
    b = mk(garch, [hippo, P("보만다")], my_ranks={}, opp_ranks={},
           opp_status=[None, "마비"], my_hazards={"스텔스록": 1, "압정뿌리기": 2})
    check("상태이상은 자리마다 (벤치 보만다 마비) · 압정은 그쪽 자리에",
          b.opp_party.members[1].status == "마비" and b.me_party.hazards == {"스텔스록": 1, "압정뿌리기": 2})
    b = mk(garch, hippo, my_ranks={}, opp_ranks={}, my_status=["졸음"])
    b.step(iron, iron)
    check("졸음(하품 다음 턴)을 넘기면 이번 턴 끝에 잠든다", b.me.status == "잠듦", b.me.status)
    b = mk(garch, hippo, my_ranks={}, opp_ranks={}, opp_status=["맹독"])
    check("맹독은 몇 턴째인지 모른다고 경고한다", any("맹독" in w for w in b.warnings), b.warnings)
    # ★ 위협을 다시 발동하지 않는다 — 랭크를 넘기면 창에 적힌 랭크가 지금 랭크
    mence = P("보만다")
    old = mk(garch, mence)
    new = mk(garch, mence, my_ranks={}, opp_ranks={})
    # 1위 보만다는 메가스톤을 든 몸이라 Build 특성은 스카이스킨이지만, 대전은 메가 전(위협)으로 시작한다
    check("랭크를 안 넘기면 예전처럼 위협이 들어간다 (옛 호출·판 처음부터)",
          old.opp.base.ability == "위협" and old.me.ranks["attack"] == -1,
          (old.opp.base.ability, old.me.ranks))
    check("랭크를 넘기면 위협을 다시 안 넣는다 — 계산할 때마다 또 깎이지 않게",
          new.me.ranks["attack"] == 0, new.me.ranks)
    for bad in ({"my_status": ["혼수"]}, {"my_ranks": {"힘": 1}}, {"field": {"weather": "황사"}}):
        try:
            mk(garch, hippo, **bad)
            ok = False
        except ValueError:
            ok = True
        check("모르는 값은 조용히 무시하지 않고 멈춘다 (%s)" % list(bad.values())[0], ok)
    # 탐색(창이 부르는 것)까지 — 넘긴 상태가 끝까지 가는가
    got = search.best_action(dex, [garch], [hippo.poke], my_moves=["지진", "칼춤"], seconds=0.3,
                             state={"my_hp": [100], "my_active": 0, "opp_hp": [100], "opp_active": 0,
                                    "my_fresh": False, "opp_fresh": False, "my_ranks": {"attack": 6},
                                    "opp_ranks": {}, "field": {"weather": None}, "my_status": [None],
                                    "opp_status": [None], "my_hazards": None, "opp_hazards": None})
    check("탐색에 실전 중간 상태를 넘겨도 돈다 (공격 +6 이면 칼춤보다 지진)",
          got["rows"][0]["name"].startswith("지진"), [(r["name"], r["score"]) for r in got["rows"][:3]])
    mid = {"my_status": ["화상", None], "opp_status": [None], "my_ranks": {"attack": -1},
           "opp_ranks": {}, "field": {"weather": "모래바람", "weather_turns": 3},
           "my_hazards": None, "opp_hazards": {"스텔스록": 1, "압정뿌리기": 2}}
    said = gui.describe_mid(mid, ["한카리아스", "하마돈"], ["보만다"])
    check("창이 넘긴 판 상태를 한 줄로 보여 준다", said == "한카리아스 화상 · 내 랭크 공-1 · "
          "날씨 모래바람 3턴 · 상대 쪽 스텔스록 압정뿌리기×2", said)
    rows = [(None, 100), (hippo.poke, 0), (hippo.poke, 50), (hippo.poke, 100)]
    check("넘기는 상대 목록의 원래 자리 번호 (쓰러진 놈·빈 칸 뺌)", live.alive_slots(rows) == [2, 3])

    # -- 화면에서 읽은 일 → 새 칸 (판) -----------------------------------------
    import screenread
    row = lambda n, st=None: {"poke": dex.find_pokemon(n), "hp": 100.0, "brought": True, "status": st}
    bd = screenread.Board([row("한카리아스"), row("누리레느")], [row("하마돈"), row("보만다", "화상")])
    ap = lambda **ev: screenread.apply(bd, ev, dex)
    ap(kind="능력하락", mon="한카리아스", side="me", stat="공격")
    ap(kind="능력하락", mon="한카리아스", side="me", stat="공격")
    notes = ap(kind="능력하락", mon="누리레느", side="me", stat="방어")
    check("「공격이 떨어졌다」 두 번 → 나와 있는 놈 공격 −2 · 벤치 것은 안 넣음",
          bd.ranks["me"] == {"attack": -2} and not notes[0][0], (bd.ranks, notes))
    ap(kind="나옴", mon="누리레느", side="me")
    check("내가 교체하면 내 랭크가 풀린다", bd.ranks["me"] == {} and bd.my_active == 1, bd.ranks)
    ap(kind="하품", mon="하마돈", side="opp")
    notes = ap(kind="하품", mon="보만다", side="opp")
    check("하품 → 졸음 · 이미 화상인 놈은 안 바뀜",
          bd.opp[0]["status"] == "졸음" and bd.opp[1]["status"] == "화상", [r["status"] for r in bd.opp])
    ap(kind="나옴", mon="보만다", side="opp")
    check("졸음인 놈이 들어가면 졸음이 풀린다 (게임 규칙)", bd.opp[0]["status"] is None, bd.opp[0])
    ap(kind="잠듦", mon="하마돈", side="opp")
    s1 = bd.opp[0]["status"]
    ap(kind="깸", mon="하마돈", side="opp")
    check("잠듦 → 잠듦, 눈을 떴다 → 없음", s1 == "잠듦" and bd.opp[0]["status"] is None)
    ap(kind="모래바람데미지", mon="보만다", side="opp")
    w1 = bd.weather
    ap(kind="모래바람끝")
    check("모래바람이 덮침 → 날씨 모래바람, 가라앉음 → 없음", w1 == "모래바람" and bd.weather == "없음",
          (w1, bd.weather))
    ap(kind="스텔스록깔림")
    ap(kind="스텔스록데미지", mon="누리레느", side="me")
    check("「상대의 주변에」 → 상대 쪽 스텔스록 · 내가 박힘 → 내 쪽 스텔스록",
          bd.hazards["opp"] == {"스텔스록": 1} and bd.hazards["me"] == {"스텔스록": 1}, bd.hazards)


def main():
    paths.fix_console()          # 윈도우에서 한글을 찍다 죽지 않게
    dex = calc.Dex()
    print("데이터: 포켓몬 %d / 기술 %d / 특성 %d / 도구 %d"
          % (len(dex.pokemon), len(dex.moves), len(dex.abilities), len(dex.items)))
    test_real_game(dex)
    test_stat_formula()
    test_sp_budget()
    test_type_chart(dex)
    test_known_cases(dex)
    test_abilities_items(dex)
    test_damage_vs_index(dex)
    test_mega_stone(dex)
    test_speed(dex)
    test_race()
    test_move_caveats(dex)
    test_analyze(dex)
    test_move_effects(dex)
    test_battle_rules(dex)
    test_battle_result(dex)
    test_dead_items(dex)
    test_item_behaviors(dex)
    test_screens_and_weather(dex)
    test_more_status_moves(dex)
    test_cache_honesty(dex)
    test_search(dex)
    test_live(dex)
    test_windows_safe(dex)
    test_battle_hand_check(dex)
    test_status(dex)
    test_scout(dex)
    test_scout_narrowing(dex)
    test_switching(dex)
    test_intimidate(dex)
    test_sacrifice(dex)
    test_policy(dex)
    test_replacement_choice(dex)
    test_selection(dex)
    test_opponent_switching(dex)
    test_sensitivity(dex)
    test_crit_rules(dex)
    test_new_abilities(dex)
    test_forms(dex)
    test_forms_body(dex)
    test_samples(dex)
    test_fetch_pokesol(dex)
    test_combos(dex)
    test_fetch_champs(dex)
    test_rosters(dex)
    test_party_file(dex)
    test_poltergeist(dex)
    test_fail_conditions(dex)
    test_attack_effects(dex)
    test_zoom_lens(dex)
    test_fixed_ohko_minimize(dex)
    test_abilities_batch1(dex)
    test_abilities_batch2(dex)
    test_abilities_batch3(dex)
    test_artmatch(dex)
    test_msgread(dex)
    test_screenread(dex)
    test_read_speed(dex)
    test_watch(dex)
    test_advice(dex)
    test_setup(dex)
    test_mid_state(dex)

    print("\n" + "=" * 50)
    if FAIL:
        print("실패 %d건: %s" % (len(FAIL), ", ".join(FAIL)))
        sys.exit(1)
    # 검사 개수는 **환경마다 다르다.** tkinter 가 없는 곳(클라우드)에서만 도는
    # 검사가 있어서, 같은 코드인데 클라우드 553 / 윈도우 552 로 갈렸다
    # (2026-09-21). 문서의 손으로 적은 숫자와 안 맞으면 먼저 이걸 본다.
    import gui
    print("전부 통과 — %d개 (tkinter %s)"
          % (PASSED[0], "있음" if gui.have_tk()[0] else "없음"))


if __name__ == "__main__":
    main()
