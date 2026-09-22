# -*- coding: utf-8 -*-
"""
계산기 검증 스크립트.

계산기를 고쳤으면 이걸 먼저 돌려서 깨진 데 없는지 확인한다.

    python tests.py
"""

import itertools
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
    top, got = pick(["한카리아스", "누리레느"], "아머까오",
                    ["지진", "대지의힘", "칼춤", "스텔스록"], 5.0)
    ground_only = [r for r in got["rows"] if "교체" not in r["name"]]
    check("때릴 수단이 없으면 공격수들이 전부 바닥이다 (최고 %.2f)"
          % max(r["score"] for r in ground_only),
          max(r["score"] for r in ground_only) < 0.95,
          [(r["name"], round(r["score"], 3)) for r in ground_only[:3]])
    check("때릴 수단이 없으면 교체를 고른다 (%s)" % top["name"],
          "교체" in top["name"], [(r["name"], round(r["score"], 3))
                                 for r in got["rows"][:3]])

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
    ground = [dex.find_move(x) for x in ("지진", "대지의힘", "칼춤", "스텔스록")]
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
    check("고를 수 있는 포켓몬이 이름마다 하나뿐이다 (%d마리)" % len(pool),
          len(set(p["name"] for p in pool)) == len(pool), len(pool))
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
