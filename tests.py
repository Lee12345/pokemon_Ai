# -*- coding: utf-8 -*-
"""
계산기 검증 스크립트.

계산기를 고쳤으면 이걸 먼저 돌려서 깨진 데 없는지 확인한다.

    python tests.py
"""

import itertools
import math
import sys

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
    best = 0
    for used in range(1, 7):
        for total in range(1, 6 * 32 + 1):
            if total > 32 * used:
                break
            if 8 * total - 4 * used <= 510:
                best = max(best, total)
    check("구 노력치 510 제약에서 최대 66점", best == 66, "계산값 %d" % best)


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

    print("\n" + "=" * 50)
    if FAIL:
        print("실패 %d건: %s" % (len(FAIL), ", ".join(FAIL)))
        sys.exit(1)
    print("전부 통과")


if __name__ == "__main__":
    main()
