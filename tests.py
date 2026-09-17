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
import forms
import scout
import pick as selection
import samples
import sensitivity

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
    bt = battle.Battle(dex, [B("메가보만다"), B("한카리아스")], B("하마돈"),
                       rng=random.Random(1), log=True)
    bt.me_party.hazards["스텔스록"] = 1
    bt.switch_in(bt.me_party, 1)
    chomp = bt.me_party.members[1]
    # 메가한카리아스Z 는 순수 드래곤 -> 바위는 보통(x1) -> 1/8
    check("스텔스록 데미지가 상성을 탄다",
          chomp.max_hp - chomp.hp == max(1, int(chomp.max_hp * 1.0 / 8)),
          chomp.max_hp - chomp.hp)

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
    check("흡반이 강제 교체를 막는다", bt.me.name == "메가보만다", bt.me.name)

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
    check("리드는 계획대로 쓴다",
          pol.act(party, 0)["name"] == "이판사판태클", pol.act(party, 0))
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
    check("1대1 상성표가 %d쌍 다 찬다" % (len(my4) * len(op4)),
          len(table) == len(my4) * len(op4), len(table))
    check("승률은 0~1 사이", all(0.0 <= v <= 1.0 for v in table.values()))

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
    """정답을 아는 가짜 표본. 맞추기가 그 값을 되찾는지 보려고 만든다."""
    import random
    pokes = pokes or ["한카리아스", "보만다", "리자몽", "망나뇽"]
    old = dict((k, calc.CONFIG[k]) for k in samples.KNOBS)
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
        got = samples.fit(dex, parties)
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
    lift = dict(((a, b), lf) for a, b, _c, _na, _nb, lf in rows)
    def get(a, b):
        return lift.get((a, b), lift.get((b, a)))
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

    print("\n" + "=" * 50)
    if FAIL:
        print("실패 %d건: %s" % (len(FAIL), ", ".join(FAIL)))
        sys.exit(1)
    print("전부 통과")


if __name__ == "__main__":
    main()
