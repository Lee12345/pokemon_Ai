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

FAIL = []


def check(name, cond, detail=""):
    if cond:
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


def main():
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
    test_battle_hand_check(dex)

    print("\n" + "=" * 50)
    if FAIL:
        print("실패 %d건: %s" % (len(FAIL), ", ".join(FAIL)))
        sys.exit(1)
    print("전부 통과")


if __name__ == "__main__":
    main()
