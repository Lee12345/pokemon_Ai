# -*- coding: utf-8 -*-
"""
4-A — 한 턴 최선수.

    python best.py 메가보만다 하마돈
    python best.py 메가보만다 하마돈 이판사판태클 지진 용의춤
    python best.py 한카리아스 하마돈 --트릭룸

기술을 직접 적으면 그것만 비교하고, 안 적으면 사용률 상위 기술을 대신 쓴다.

하는 일은 세 가지다.

  1. 스피드 비교 — 내가 먼저 때리는가
  2. 기술 일괄 비교 — 어느 기술이 제일 좋은가
  3. 대면 결론   — 이 대면을 이기는가

설계 문서(docs/ai-design.md) 3-5 의 4-A 에 해당한다.
변화기는 아직 점수를 못 매긴다(4-B). 목록에는 보여주되 추천에서는 뺀다.
"""

import re
import paths
import sys
import unicodedata

import calc

# ---------------------------------------------------------------------------
# 스피드에 관여하는 특성
# ---------------------------------------------------------------------------
# 지금 계산에 넣을 수 있는 것
SPEED_ABILITY = {
    # 상태 이상일 때 1.5배. 마비로 느려지는 것도 무시한다.
    "속보": {"kind": "status", "mult": 1.5, "ignores_paralysis": True},
}
# 조건이 아직 모델에 없어서 못 넣는 것 (경고만 띄운다)
SPEED_ABILITY_UNSUPPORTED = {
    "쓱쓱":       "비일 때 스피드 2배 — 날씨가 아직 없음",
    "엽록소":     "쾌청일 때 스피드 2배 — 날씨가 아직 없음",
    "모래헤치기": "모래바람일 때 스피드 2배 — 날씨가 아직 없음",
    "눈치우기":   "눈일 때 스피드 2배 — 날씨가 아직 없음",
    "서핑테일":   "일렉트릭필드일 때 스피드 2배 — 필드가 아직 없음",
    "곡예":       "도구가 없어지면 스피드 2배 — 도구 소실이 아직 없음",
    "가속":       "턴이 끝날 때마다 스피드 1단계 상승 — 턴 진행이 아직 없음",
    "깨어진갑옷": "물리 기술을 맞으면 스피드 2단계 상승 — 턴 진행이 아직 없음",
}
# 우선도를 바꾸는 특성
PRIORITY_ABILITY = {
    "짓궂은마음": {"kind": "category", "category": "변화", "bonus": 1,
                   "note": "변화기 우선도 +1 (악타입에게는 안 통함)"},
    "질풍날개":   {"kind": "type_full_hp", "type": "비행", "bonus": 1,
                   "note": "HP가 꽉 차 있어서 비행 기술 우선도 +1"},
}
# 같은 우선도 안에서 무조건 마지막
ALWAYS_LAST = {"시간벌기": "시간벌기: 같은 우선도면 항상 나중에"}
# 확률로 선공을 가져가는 것들. 확정이 아니라서 경고로만 알린다.
RANDOM_FIRST_ABILITY = {"퀵드로": 0.30}
RANDOM_FIRST_ITEM = {"선제공격손톱": 0.20}

WIN, LUCK, LOSE = "win", "luck", "lose"
OUTCOME_KO = {WIN: "확실히 이김", LUCK: "난수 싸움", LOSE: "확실히 짐"}
OUTCOME_RANK = {WIN: 0, LUCK: 1, LOSE: 2}

NEVER = 999          # 영원히 못 쓰러뜨린다는 뜻

# 우선도를 빼고 스피드만 견줄 때 쓰는 가짜 기술
NEUTRAL_MOVE = {"name": "(우선도 0 기준)", "priority": 0,
                "category": "물리", "type": "노말"}


# ---------------------------------------------------------------------------
# 글자 폭 맞추기 (한글은 두 칸을 먹는다)
# ---------------------------------------------------------------------------
def _w(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _pad(s, width):
    return s + " " * max(0, width - _w(s))


# ---------------------------------------------------------------------------
# 스피드
# ---------------------------------------------------------------------------
def speed_item_effects(dex):
    """도구 설명문에서 스피드 배율을 읽어낸다.

    데미지 도구와 같은 방식이다. 설명문을 읽으므로 새 도구가 나와도 따라온다.

    ! **결과를 dex 에 붙여 둔다.** 이건 dex 만 있으면 정해지는 값인데
      전에는 부를 때마다 도구 166개를 전부 다시 훑었다. 3대3 한 판을
      도는 동안 7,235번 불렸고, 그 안에서 정규식이 **240만 번** 돌았다
      (한 판 전체 re.search 306만 번의 대부분). 재 보니 그것만으로
      전체 시간의 44% 였다. 7단계(여러 턴 내다보기)는 이 함수를
      수십만 번 부르게 되므로 여기서 막아야 한다.
    """
    got = getattr(dex, "_speed_items", None)
    if got is not None:
        return got
    out = {}
    for it in dex.items:
        d = it["description"]
        # 문장 끝('된다' / '되지만')은 보지 않는다.
        # 한글은 '되'와 '된'이 서로 다른 한 글자라, 어미까지 넣으면 조용히 안 걸린다.
        m = re.search(r"스피드가 (\d+(?:\.\d+)?)배", d)
        if m:
            out[it["name"]] = float(m.group(1))
            continue
        m = re.search(r"스피드가 1/(\d+)", d)
        if m:
            out[it["name"]] = 1.0 / int(m.group(1))
    try:
        dex._speed_items = out
    except AttributeError:
        pass
    return out


def effective_speed(dex, build):
    """실제로 행동 순서를 정할 때 쓰는 스피드.

    랭크 -> 특성 -> 도구 -> 마비 순서로 곱한다.
    본편은 단계마다 소수점을 버리는데, 챔피언스도 같은지는 확인 못 했다.
    """
    v = build.stat("speed")           # 랭크까지 들어간 값
    notes, warnings = [], []

    para_ignored = False
    ab = SPEED_ABILITY.get(build.ability)
    if ab and ab["kind"] == "status" and build.status:
        v = int(v * ab["mult"])
        notes.append("%s: 상태 이상이라 스피드 %.1f배" % (build.ability, ab["mult"]))
        para_ignored = ab.get("ignores_paralysis", False)
    if build.ability in SPEED_ABILITY_UNSUPPORTED:
        warnings.append("%s 의 특성 '%s' 는 스피드 계산에 안 들어갔습니다 (%s)"
                        % (build.name, build.ability,
                           SPEED_ABILITY_UNSUPPORTED[build.ability]))

    mult = speed_item_effects(dex).get(build.item) if build.item else None
    if mult:
        v = int(v * mult)
        notes.append("%s: 스피드 %.2f배" % (build.item, mult))

    if build.status == "마비" and not para_ignored:
        v = int(v * calc.CONFIG["paralysis_speed"])
        notes.append("마비: 스피드 %.2f배 (미확인 값)"
                     % calc.CONFIG["paralysis_speed"])

    return v, notes, warnings


def move_priority(build, move):
    """기술의 우선도. 특성으로 올라가는 경우까지 본다."""
    p = move["priority"]
    notes = []
    ab = PRIORITY_ABILITY.get(build.ability)
    if ab:
        hit = False
        if ab["kind"] == "category" and move["category"] == ab["category"]:
            hit = True
        elif (ab["kind"] == "type_full_hp" and move["type"] == ab["type"]
                and build.hp_ratio >= 1.0):
            hit = True
        if hit:
            p += ab["bonus"]
            notes.append("%s: %s" % (build.ability, ab["note"]))
    return p, notes


def turn_order(dex, me, my_move, opp, opp_move, trick_room=False):
    """누가 먼저 때리는가.

    돌려주는 first 는 '나' / '상대' / '동시' 셋 중 하나다.
    '동시' 는 스피드가 완전히 같아서 50:50 인 경우를 뜻한다.
    """
    my_speed, my_notes, warn = effective_speed(dex, me)
    op_speed, op_notes, w2 = effective_speed(dex, opp)
    warnings = list(warn) + list(w2)

    my_pri, pn1 = move_priority(me, my_move)
    op_pri, pn2 = move_priority(opp, opp_move)
    notes = my_notes + pn1 + op_notes + pn2

    for who, b in (("나", me), ("상대", opp)):
        if b.ability in RANDOM_FIRST_ABILITY:
            warnings.append("%s측 특성 '%s' — %d%% 확률로 선공을 가져갑니다"
                            % (who, b.ability,
                               RANDOM_FIRST_ABILITY[b.ability] * 100))
        if b.item in RANDOM_FIRST_ITEM:
            warnings.append("%s측 도구 '%s' — %d%% 확률로 선공을 가져갑니다"
                            % (who, b.item, RANDOM_FIRST_ITEM[b.item] * 100))

    if my_pri != op_pri:
        first = "나" if my_pri > op_pri else "상대"
        reason = "우선도 %+d vs %+d" % (my_pri, op_pri)
    else:
        my_last = me.ability in ALWAYS_LAST
        op_last = opp.ability in ALWAYS_LAST
        if my_last != op_last:
            first = "상대" if my_last else "나"
            reason = ALWAYS_LAST["시간벌기"]
        elif my_speed == op_speed:
            first = "동시"
            reason = "둘 다 스피드 %d" % my_speed
        else:
            faster = "나" if my_speed > op_speed else "상대"
            if trick_room:
                faster = "상대" if faster == "나" else "나"
            first = faster
            reason = "스피드 %d vs %d%s" % (
                my_speed, op_speed, " · 트릭룸이라 느린 쪽이 먼저" if trick_room else "")

    return {"first": first, "reason": reason,
            "mySpeed": my_speed, "oppSpeed": op_speed,
            "myPriority": my_pri, "oppPriority": op_pri,
            "notes": notes, "warnings": warnings}


# ---------------------------------------------------------------------------
# 상대 스피드가 얼마일 수 있는가 — 사용률로 본 분포
# ---------------------------------------------------------------------------
def _usage_of(dex, poke):
    return (dex.usage.get(poke["key"])
            or dex.usage.get("%04d-00" % poke["dexNo"]))


def speed_scenarios(dex, poke):
    """상대 배분을 모를 때 나올 수 있는 스피드와 그 확률.

    사용률에는 성격·노력치·도구가 따로따로 들어있고
    '어떤 성격이 어떤 배분과 같이 쓰였는지' 는 없다.
    그래서 셋을 서로 독립이라고 보고 곱한다. 어디까지나 근사다.
    """
    u = _usage_of(dex, poke)
    if not u or not u.get("natures") or not u.get("evs"):
        return []

    natures = []
    tot = sum(n["pct"] for n in u["natures"]) or 1.0
    for n in u["natures"]:
        try:
            natures.append((dex.find_nature(n["name"]), n["pct"] / tot))
        except LookupError:
            pass
    if not natures:
        return []

    spreads = []
    tot = sum(e["pct"] for e in u["evs"]) or 1.0
    for e in u["evs"]:
        spreads.append((e["spread"].get("S", 0), e["pct"] / tot, e["name"]))

    # 도구는 스피드를 바꾸는 것만 따로 본다. 메가는 도구가 메가스톤으로 고정이다.
    items = []
    if not poke.get("isMega"):
        speed_items = speed_item_effects(dex)
        used = 0.0
        for i in (u.get("items") or []):
            if i["name"] in speed_items:
                items.append((i["name"], speed_items[i["name"]], i["pct"] / 100.0))
                used += i["pct"] / 100.0
        items.append((None, 1.0, max(0.0, 1.0 - used)))
    else:
        items.append((None, 1.0, 1.0))

    base = poke["baseStats"]["speed"]
    out = []
    for nature, pn in natures:
        for ev_s, pe, ev_name in spreads:
            raw = calc.real_stat(base, ev_s, "speed", nature)
            for item_name, imult, pi in items:
                if pi <= 0:
                    continue
                out.append({"speed": int(raw * imult), "prob": pn * pe * pi,
                            "nature": nature["name"], "ev": ev_name,
                            "item": item_name})
    return out


def faster_chance(my_speed, scenarios):
    """내 스피드가 상대보다 빠를 확률. 동속은 반씩 나눈다."""
    if not scenarios:
        return None
    total = sum(s["prob"] for s in scenarios) or 1.0
    win = sum(s["prob"] for s in scenarios if s["speed"] < my_speed)
    tie = sum(s["prob"] for s in scenarios if s["speed"] == my_speed)
    return (win + tie / 2.0) / total


def scenario_summary(scenarios):
    """도구별로 묶어서 '이 도구면 스피드 몇~몇' 을 정리한다."""
    groups = {}
    for s in scenarios:
        g = groups.setdefault(s["item"], {"prob": 0.0, "speeds": []})
        g["prob"] += s["prob"]
        g["speeds"].append(s["speed"])
    out = []
    for name, g in groups.items():
        out.append({"item": name, "prob": g["prob"],
                    "min": min(g["speeds"]), "max": max(g["speeds"])})
    out.sort(key=lambda x: -x["prob"])
    return out


# ---------------------------------------------------------------------------
# 기술에 붙은 특수 규칙 — 계산에 안 들어간 것들
# ---------------------------------------------------------------------------
# 설계 문서 2장에서 센 '위력 그대로가 아닌 공격기 79개' 가 여기 걸린다.
# 배율을 고쳐 넣는 게 아니라, 숫자를 그대로 믿으면 안 된다고 알려주기만 한다.
# (아는 척해서 틀린 값을 넣느니, 모른다고 말하는 편이 낫다.)
# 대전(battle.py)이 실제로 판정하는 조건 — 이 말로 시작하는 주의는 대전 경고에서 뺀다.
CONDITIONAL = "조건부 — "

MOVE_CAVEAT_RULES = [
    (r"차지 상태가 되어 다음 턴에 공격",
     "2턴 기술 — 첫 턴에는 데미지가 0이다"),
    (r"다음 턴에 자신은 반동 상태",
     "쓰고 나면 다음 턴을 통째로 쉰다"),
    (r"준 데미지의 1/(\d+)만큼 자신도",
     "준 데미지의 1/{0} 를 자신도 받는다"),
    (r"(\d)~(\d)회 연속으로 공격",
     "{0}~{1}회 연속 — 아래 데미지는 1회분이다"),
    # (2026-09-22 전에는 계산기가 위력 1 로 계산해서 '아래 숫자는 무시할 것' 이라고
    #  적었다. 이제 calc 가 정해진 양으로 넣으므로 숫자가 맞다 — 문구를 고쳤다)
    (r"상대 HP에 (\d+)데미지",
     "위력과 상관없이 {0} 고정 데미지 (상성·자속·스크린을 안 탄다)"),
    (r"위력은 (\d+)~(\d+)",
     "상황에 따라 위력이 {0}~{1} 로 변한다 — 아래는 표기 위력 기준"),
    (r"난동 상태가 된다",
     "2~3턴 같은 기술만 쓰게 되고, 끝나면 자신이 혼란에 빠진다"),
    (r"(?:쾌청|비|눈|모래바람|[가-힣]*필드) 상태[^.]*위력",
     "날씨·필드에 따라 위력이 달라진다 — 아직 계산에 없음"),
    (r"([가-힣]+) 상태인 경우 상대에게 반드시 명중",
     "{0} 상태면 반드시 명중한다 — 옆의 명중률은 날씨가 없을 때 기준"),
    (r"명중률은 (\d+)%가 된다",
     "날씨에 따라 명중률이 {0}% 로 바뀐다"),
    # 설명문의 '실패한다' 조건 (2026-09-22). 한 턴 표는 판의 흐름(나온 첫 턴인가·
    # 상대가 무엇을 골랐나)을 모르므로 **적어서 보여 준다.** 대전(battle.py)은
    # 이것들을 실제로 판정하므로 '조건부' 로 시작하는 줄은 경고로 안 올린다.
    # ! 패턴은 battle.py 의 _FIRST_ONLY 등과 같아야 한다 — tests.py [48] 이 대조한다.
    (r"등장하고 가장 먼저 사용하지 않으면 실패",
     CONDITIONAL + "나온 뒤 첫 기술일 때만 된다 (그 뒤로는 실패)"),
    (r"상대가 공격 기술을 선택하였고 이 기술을 사용한 턴 동안 이미 공격하였다면 실패",
     CONDITIONAL + "상대가 공격기를 골랐고 아직 안 움직였을 때만 된다"),
    (r"상대가 선제 공격 기술을 사용하지 않은 경우 실패",
     CONDITIONAL + "상대가 선제기를 쓰는 턴에만 된다"),
    (r"상대로부터 먼저 기술로 데미지를 입으면 실패",
     CONDITIONAL + "그 턴에 먼저 맞으면 실패한다"),
    (r"다른 배운 기술을 모두 사용하지 않은 경우 실패",
     CONDITIONAL + "다른 기술을 다 써 본 뒤에만 된다"),
    (r"나무열매를 먹지 않은 경우 이 기술은 실패",
     CONDITIONAL + "이 배틀에서 나무열매를 먹은 뒤에만 된다"),
    (r"비축하기 상태가 아닌 경우 이 기술은 실패",
     CONDITIONAL + "비축하기를 해 둔 만큼만 된다 (없으면 실패)"),
    (r"필드가 전개되어 있지 않은 경우 실패",
     CONDITIONAL + "필드가 깔려 있을 때만 된다"),
    (r"자신이 (\S+?)타입이 아닌 경우 실패",
     CONDITIONAL + "자신이 {0}타입일 때만 된다 (쓰면 {0}타입을 잃는다)"),
    (r"빗나가거나 실패하면 자신의 최대 HP의 1/(\d+)만큼 데미지",
     CONDITIONAL + "빗나가거나 실패하면 자신이 최대 HP의 1/{0} 를 잃는다"),
    (r"직전 턴에 자신이 행동하지 못했거나 기술이 빗나가거나 실패한 경우 위력이 (\d+)배",
     CONDITIONAL + "직전 턴에 실패·행동 불능이었으면 위력 {0}배"),
    (r"이 기술은 2회 연속으로 사용할 수 없다",
     CONDITIONAL + "두 번 연달아 쓸 수 없다"),
]


_CAVEAT_CACHE = {}


def move_caveats(move):
    """이 기술이 '위력 그대로' 가 아닌 이유들. 없으면 빈 목록.

    기술 하나당 답이 하나뿐이라 외워 둔다. 한 판에 66,763번 불린다.
    """
    key = move.get("id") or move.get("name")
    got = _CAVEAT_CACHE.get(key)
    if got is not None:
        return got
    d = move.get("description") or ""
    out = []
    for pattern, text in MOVE_CAVEAT_RULES:
        m = re.search(pattern, d)
        if m:
            out.append(text.format(*m.groups()) if m.groups() else text)
    if key is not None:
        _CAVEAT_CACHE[key] = out
    return out


# ---------------------------------------------------------------------------
# 기술 고르기 / 점수 매기기
# ---------------------------------------------------------------------------
def candidate_moves(dex, poke, names=None):
    """비교할 기술 목록. (기술, 채용률) 의 목록으로 준다.

    채용률이 None 이면 '사용자가 직접 적은 기술' 이라는 뜻이다.
    """
    if names:
        return [(dex.find_move(n), None) for n in names]

    u = _usage_of(dex, poke)
    if u and u.get("moves"):
        out = []
        for entry in u["moves"]:
            mv = dex.move_by_id(entry["id"])
            if mv is None:
                try:
                    mv = dex.find_move(entry["name"])
                except LookupError:
                    continue
            out.append((mv, entry["pct"]))
        if out:
            return out

    # 사용률이 없으면 배울 수 있는 공격기 중 위력 높은 순으로
    learn = dex.learnsets.get(poke["key"], [])
    pool = [dex.move_by_id(i) for i in learn]
    pool = [m for m in pool if m and m["category"] != "변화" and m["power"] > 0]
    pool.sort(key=lambda m: -m["power"])
    return [(m, None) for m in pool[:8]]


def hit_rate(move):
    """명중률. 101 은 '반드시 맞는다' 는 표시다."""
    acc = move.get("accuracy")
    if acc is None or acc > 100:
        return 1.0
    return acc / 100.0


# ---------------------------------------------------------------------------
# rate_moves 외워 두기
# ---------------------------------------------------------------------------
#
# 3대3 한 판을 도는 동안 `rate_moves` 가 175번 불리고, 그 안에서
# `calc_damage` 가 698번 돈다. 재 보니 **교체를 판단하는 휴리스틱
# (should_switch -> replacement_score -> rate_moves) 이 전투 시뮬레이션
# 자체보다 8배 비쌌다** — 4.84초 중 3.95초. 벤치에 앉아 있는 놈들은
# 턴이 지나도 상태가 안 변하는데 매 턴 다시 재고 있었다.
# 실제로 세어 보니 호출의 **73%가 이미 잰 것과 똑같은 조건**이었다.
#
# ! 열쇠는 `calc_damage` 가 **읽는 것 전부**여야 한다. 하나라도 빠지면
#   남의 답을 돌려주는, 이 프로젝트에서 제일 무서운 종류의 고장이 된다.
#   그래서 실제로 읽는 필드를 세어서 맞췄다 —
#     ability · hp_ratio · item · ranks · stat(종족값·노력치·성격) ·
#     status · types
#   그리고 `CHECK_CACHE = True` 로 켜면 **캐시를 쓰지 않고 매번 다시
#   계산해서 저장된 답과 대조한다.** 테스트가 그 모드로 한 번 돌린다.
_RATE_CACHE = {}
CHECK_CACHE = False         # True 면 캐시를 믿지 않고 매번 대조한다


def _build_key(b):
    """이 몸이 데미지 계산에 주는 영향을 남김없이 담은 열쇠."""
    return (b.poke["key"], b.poke.get("formNo"),
            tuple(sorted(b.sp.items())),
            b.nature["name"] if b.nature else None,
            tuple(sorted(b.ranks.items())),
            b.item, b.ability, b.status,
            round(b.hp_ratio, 6), tuple(b.poke["types"]))


def _rate_signature(rows):
    """대조용 — 캐시가 돌려준 답이 정말 같은지 비교할 거리."""
    return [(r["move"]["id"], r["kind"], round(r.get("expected", 0.0), 9),
             round(r.get("koNow", 0.0), 9)) for r in rows]


def rate_moves(dex, attacker, defender, moves):
    """기술 하나하나에 데미지와 점수를 붙인다.

    kind 는 셋 중 하나다.
      damage — 데미지가 나온다
      status — 변화기라 아직 점수를 못 매긴다 (4-B)
      none   — 안 통하거나 위력이 정해져 있지 않다
    """
    key = (_build_key(attacker), _build_key(defender),
           tuple(m["id"] for m, _ in moves),
           tuple(p for _, p in moves))
    got = _RATE_CACHE.get(key)
    if got is not None and not CHECK_CACHE:
        return got
    rows = _rate_moves_raw(dex, attacker, defender, moves)
    if got is not None:
        # 대조 모드 — 열쇠가 모자라면 여기서 걸린다
        if _rate_signature(got) != _rate_signature(rows):
            raise AssertionError(
                "rate_moves 캐시가 다른 답을 돌려준다. 열쇠에 빠진 것이 "
                "있다: %s vs %s" % (_rate_signature(got)[:2],
                                   _rate_signature(rows)[:2]))
    if len(_RATE_CACHE) > 200000:
        _RATE_CACHE.clear()
    _RATE_CACHE[key] = rows
    return rows


def expected_hits(move, hit=1.0):
    """연속기가 평균 몇 방 분량인가 (1회분 데미지에 곱할 값). 연속기가 아니면 1.

    2~5회는 calc.CONFIG 의 확률(사용자가 확인해 줌 — 평균 3.0회), 찍찍베기처럼 '도중에 빗나가면 끝' 은
    두 번째부터 매번 명중을 곱한다. 트리플악셀은 방마다 위력이 달라서 위력 비로 센다.
    """
    fx = calc.attack_effects(move)
    if not fx["hits"]:
        return 1.0
    lo, hi = fx["hits"]
    if fx["powers"]:
        base = float(fx["powers"][0])
        return sum(p / base * (hit ** i if fx["stop_on_miss"] else 1.0)
                   for i, p in enumerate(fx["powers"]))
    if lo == hi:
        return float(lo)
    if fx["stop_on_miss"]:
        return sum(hit ** i for i in range(hi))
    if (lo, hi) == (2, 5):
        return sum(n * p for n, p in zip(range(2, 6), calc.CONFIG["multi_hit_2to5"]))
    return (lo + hi) / 2.0


def _rate_moves_raw(dex, attacker, defender, moves):
    rows = []
    for move, pct in moves:
        row = {"move": move, "pct": pct, "hit": hit_rate(move),
               "caveats": move_caveats(move)}
        if move["category"] == "변화":
            row["kind"] = "status"
            rows.append(row)
            continue
        res = calc.calc_damage(dex, attacker, defender, move)
        if "error" in res:
            row["kind"] = "none"
            row["reason"] = res["error"]
            rows.append(row)
            continue
        # '반드시 급소' 기술은 급소 기준으로 재야 한다 (트릭플라워 등).
        always_crit, _ = calc.move_crit(move)
        if always_crit:
            res = calc.calc_damage(dex, attacker, defender, move, critical=True)
            if "error" in res:
                row["kind"] = "none"
                row["reason"] = res["error"]
                rows.append(row)
                continue
            row["alwaysCrit"] = True
        hp = res["hp"]
        rolls = res["rolls"]
        row["kind"] = "damage"
        row["res"] = res
        # 연속기는 평균 몇 번 때리는 만큼 곱한다 (대전은 실제로 여러 번 때린다).
        # ! 전에는 1회분이라 AI 가 스케일샷·록블라스트를 실제보다 약하게 봤다.
        times = expected_hits(move, row["hit"])
        if times != 1.0:
            row["timesHit"] = times
        # 넘치는 데미지는 값어치가 없으므로 HP 에서 자른다
        row["expected"] = (sum(min(r * times, hp) for r in rolls)
                           / float(len(rolls)) * row["hit"])
        row["koNow"] = (sum(1 for r in rolls if r * times >= hp)
                        / float(len(rolls)) * row["hit"]
                        if times != 1.0 else res["ohkoChance"] * row["hit"])
        rows.append(row)
    return rows


def damage_rows(rows):
    return [r for r in rows if r["kind"] == "damage"]


def best_threat(rows):
    """상대가 나를 때릴 때 제일 아픈 수. 대면 결론의 '최악' 쪽을 맡는다."""
    cand = damage_rows(rows)
    if not cand:
        return None
    return max(cand, key=lambda r: (r["expected"], r["koNow"]))


def most_used(rows):
    """상대가 제일 자주 들고 오는 공격기."""
    cand = [r for r in damage_rows(rows) if r["pct"] is not None]
    if not cand:
        return None
    return max(cand, key=lambda r: r["pct"])


# ---------------------------------------------------------------------------
# 대면 결론
# ---------------------------------------------------------------------------
def _i_win(my_hits, opp_hits, i_first):
    """내가 my_hits 번, 상대가 opp_hits 번 때려야 할 때 내가 이기는가.

    내가 선공이면 상대는 내 마지막 공격 전까지 my_hits-1 번밖에 못 때린다.
    후공이면 상대가 먼저 다 때리므로 한 번 더 빨라야 한다.
    """
    return my_hits <= opp_hits if i_first else my_hits < opp_hits


def race(my_res, opp_res, first):
    """이 대면을 이기는가. WIN / LUCK / LOSE."""
    mine = (my_res["hitsMin"], my_res["hitsMax"]) if my_res else (NEVER, NEVER)
    theirs = (opp_res["hitsMin"], opp_res["hitsMax"]) if opp_res else (NEVER, NEVER)
    if first == "동시":
        orders = [True, False]        # 선공/후공 둘 다 일어날 수 있다
    else:
        orders = [first == "나"]

    # 제일 운 좋을 때: 내가 최소 타수, 상대가 최대 타수
    best = any(_i_win(mine[0], theirs[1], o) for o in orders)
    # 제일 운 나쁠 때: 내가 최대 타수, 상대가 최소 타수
    worst = all(_i_win(mine[1], theirs[0], o) for o in orders)
    if worst:
        return WIN
    if not best:
        return LOSE
    return LUCK


def analyze(dex, me, opp, my_move_names=None, trick_room=False):
    """4-A 전체. 스피드 비교 + 기술 비교 + 대면 결론."""
    my_rows = rate_moves(dex, me, opp, candidate_moves(dex, me.poke, my_move_names))
    opp_rows = rate_moves(dex, opp, me, candidate_moves(dex, opp.poke))

    threat = best_threat(opp_rows)
    common = most_used(opp_rows)
    opp_move = threat["move"] if threat else None
    opp_res = threat["res"] if threat else None

    # 상대가 뭘 쓸지는 모르니, 선공 판정에는 상대의 제일 아픈 수를 쓴다.
    threat_move = opp_move or NEUTRAL_MOVE

    for r in damage_rows(my_rows):
        order = turn_order(dex, me, r["move"], opp, threat_move,
                           trick_room=trick_room)
        r["order"] = order
        r["outcome"] = race(r["res"], opp_res, order["first"])

    ranked = sorted(damage_rows(my_rows),
                    key=lambda r: (OUTCOME_RANK[r["outcome"]],
                                   r["res"]["hitsMax"], -r["expected"]))
    pick = ranked[0] if ranked else None

    # 머리말의 스피드 비교는 우선도를 빼고 '순수한 스피드' 만 본다.
    # 우선도는 기술마다 다르므로 기술별 판정에서 따로 처리한다.
    speed_note = turn_order(dex, me, NEUTRAL_MOVE, opp, NEUTRAL_MOVE,
                            trick_room=trick_room)
    scenarios = speed_scenarios(dex, opp.poke)

    return {
        "me": me, "opp": opp,
        "myRows": my_rows, "oppRows": opp_rows,
        "threat": threat, "common": common,
        "pick": pick, "ranked": ranked,
        "speed": speed_note,
        "threatMove": threat_move,
        "scenarios": scenarios,
        "fasterChance": faster_chance(speed_note["mySpeed"], scenarios),
        "trickRoom": trick_room,
    }


# ---------------------------------------------------------------------------
# 보고서
# ---------------------------------------------------------------------------
def _eff_ko(res):
    return {0.25: "4배반감", 0.5: "반감", 1.0: "보통",
            2.0: "2배", 4.0: "4배"}.get(res["effectiveness"],
                                        "x%g" % res["effectiveness"])


def _move_table(rows, show_pct):
    """기술 목록을 표로. show_pct 면 채용률 순, 아니면 센 기술 순으로 늘어놓는다."""
    head = [("기술", 18), ("타입", 8), ("위력", 6), ("명중", 6),
            ("상성", 8), ("데미지", 12), ("HP비율", 16), ("결론", 26),
            ("이번턴KO", 8)]
    if show_pct:
        head.insert(1, ("채용률", 8))
    out = ["    " + "".join(_pad(h, w) for h, w in head).rstrip()]

    if show_pct:
        # 상대 기술은 '얼마나 자주 들고 오는가' 순으로 보는 게 읽기 편하다
        order = sorted(rows, key=lambda r: -(r["pct"] if r["pct"] is not None
                                             else -1))
    else:
        order = sorted(damage_rows(rows), key=lambda r: -r["expected"])
        order += [r for r in rows if r["kind"] != "damage"]
    for r in order:
        m = r["move"]
        cells = [m["name"] + (" !" if r.get("caveats") else "")]
        if show_pct:
            cells.append("%.1f%%" % r["pct"] if r["pct"] is not None else "-")
        if r["kind"] == "damage":
            res = r["res"]
            cells += [
                res["moveType"],
                "%d" % res["power"],
                "필중" if r["hit"] >= 1.0 else "%d%%" % round(r["hit"] * 100),
                _eff_ko(res),
                "%d ~ %d" % (res["min"], res["max"]),
                "%.1f ~ %.1f%%" % (res["minPct"], res["maxPct"]),
                calc.verdict(res),
                "%.0f%%" % (r["koNow"] * 100),
            ]
        elif r["kind"] == "status":
            cells += [m["type"], "-", "-", "-", "-", "-",
                      "변화기 — 4-B에서 다룸", "-"]
        else:
            cells += [m["type"], "%d" % m["power"], "-", "무효", "-", "-",
                      "안 통함", "0%"]
        out.append("    "
                   + "".join(_pad(c, w) for c, (h, w) in zip(cells, head)).rstrip())

    flagged = [r for r in order if r.get("caveats")]
    if flagged:
        out.append("    ! 표시 — 위력 숫자만으로는 안 되는 기술")
        for r in flagged:
            out.append("      %s: %s" % (r["move"]["name"],
                                         " / ".join(r["caveats"])))
    return out


def report(dex, a, notes=None):
    me, opp = a["me"], a["opp"]
    sp = a["speed"]
    L = []
    line = "=" * 78
    L.append(line)
    L.append("  4-A  한 턴 최선수   ·   사용률 시즌 %s 기준" % (dex.usage_season or "없음"))
    L.append(line)
    notes = notes or {}
    L.append("  나   " + me.describe())
    if notes.get("me"):
        L.append("       " + notes["me"])
    L.append("  상대 " + opp.describe())
    if notes.get("opp"):
        L.append("       " + notes["opp"])
    L.append("-" * 78)

    # --- 스피드 ---
    first_ko = {"나": "내가 먼저 때린다", "상대": "상대가 먼저 때린다",
                "동시": "동속 — 50:50"}[sp["first"]]
    L.append("[스피드]  나 %d  vs  상대 %d   →  %s  (%s)"
             % (sp["mySpeed"], sp["oppSpeed"], first_ko, sp["reason"]))
    if a["scenarios"]:
        groups = scenario_summary(a["scenarios"])
        lo = min(s["speed"] for s in a["scenarios"])
        hi = max(s["speed"] for s in a["scenarios"])
        L.append("  상대 배분은 사실 모른다. 사용률로 보면 상대 스피드는 %d ~ %d 사이다."
                 % (lo, hi))
        fc = a["fasterChance"]
        if fc is not None:
            if fc >= 0.9995:
                L.append("    어떤 배분이라도 내가 빠르다")
            elif fc <= 0.0005:
                L.append("    어떤 배분이라도 상대가 빠르다")
            else:
                L.append("    내가 더 빠를 확률  약 %.1f%%" % (fc * 100))
        for g in groups:
            if g["prob"] < 0.005:
                continue
            L.append("    · %s %.1f%% → 스피드 %d ~ %d%s" % (
                g["item"] or "스피드 도구 없음", g["prob"] * 100,
                g["min"], g["max"],
                "  (이 경우 내가 후공)" if g["min"] > sp["mySpeed"] else ""))
        L.append("  ! 성격·노력치·도구를 서로 독립이라고 본 근사다. "
                 "실제로는 같이 몰려 다닌다.")
    tm = a["threatMove"]
    if tm.get("priority"):
        L.append("  ! 상대의 제일 아픈 수 '%s' 는 우선도 %+d 다 — "
                 "스피드와 상관없이 순서가 뒤집힌다."
                 % (tm["name"], tm["priority"]))
    my_pri = [r for r in damage_rows(a["myRows"]) if r["move"]["priority"]]
    if my_pri:
        L.append("  · 우선도가 0이 아닌 내 기술 — %s   (+면 선공, -면 후공)"
                 % ", ".join("%s %+d" % (r["move"]["name"],
                                         r["move"]["priority"])
                             for r in my_pri))
    for n in sp["notes"]:
        L.append("  · %s" % n)
    for w in sp["warnings"]:
        L.append("  ! %s" % w)

    # --- 내 기술 ---
    L.append("-" * 78)
    L.append("[내 기술]   이번턴KO = 명중률까지 곱한, 이번 턴에 쓰러뜨릴 확률")
    L += _move_table(a["myRows"], show_pct=False)

    # --- 상대 기술 ---
    L.append("-" * 78)
    L.append("[상대가 나를 때리는 수]   사용률 상위 기술로 추정한 것")
    L += _move_table(a["oppRows"], show_pct=True)

    # --- 결론 ---
    L.append("-" * 78)
    L.append("[대면 결론]")
    pick = a["pick"]
    if pick is None:
        L.append("  데미지가 들어가는 기술이 하나도 없다. 교체를 봐야 한다.")
        L.append(line)
        return "\n".join(L)

    res = pick["res"]
    order = pick["order"]
    L.append("  추천 기술   %s   (%s)" % (pick["move"]["name"],
                                          OUTCOME_KO[pick["outcome"]]))
    L.append("    · %s  (%s)" % ({"나": "내가 먼저 때린다",
                                  "상대": "상대가 먼저 때린다",
                                  "동시": "동속이라 반반이다"}[order["first"]],
                                 order["reason"]))
    L.append("    · 내가 상대를 쓰러뜨리는 데 %s" % _hits_ko(res))
    threat = a["threat"]
    if threat is None:
        L.append("    · 상대는 나에게 데미지를 줄 수단이 없다")
    else:
        L.append("    · 상대의 제일 아픈 수 '%s' 로는 나를 쓰러뜨리는 데 %s"
                 % (threat["move"]["name"], _hits_ko(threat["res"])))
        common = a["common"]
        if common and common is not threat:
            L.append("    · 상대가 제일 자주 드는 공격기는 '%s' (%.1f%%) — %s"
                     % (common["move"]["name"], common["pct"],
                        _hits_ko(common["res"])))
    blocked = [r for r in a["oppRows"]
               if r["kind"] == "none" and r["pct"] is not None]
    if blocked:
        blocked.sort(key=lambda r: -r["pct"])
        L.append("    · 상대 기술 중 나에게 아예 안 통하는 것 — %s"
                 % ", ".join("%s(%.1f%%)" % (r["move"]["name"], r["pct"])
                             for r in blocked[:4]))
    for c in pick.get("caveats") or []:
        L.append("    ! %s: %s" % (pick["move"]["name"], c))
    if pick["hit"] < 1.0:
        L.append("    ! 명중률 %d%% 다. 위 결론은 빗나가지 않는다고 보고 낸 것이다."
                 % round(pick["hit"] * 100))

    if len(a["ranked"]) > 1:
        L.append("")
        L.append("  다른 기술로 바꾸면")
        for r in a["ranked"][1:4]:
            L.append("    %s %s → %s"
                     % (_pad(r["move"]["name"], 16), _hits_ko(r["res"]),
                        OUTCOME_KO[r["outcome"]]))

    L.append("")
    L.append("  ! 아직 안 보는 것 — 급소 · 변화기의 값어치(4-B) · 교체 · 날씨/필드 ·")
    L.append("    기술에 붙은 조건 (만나자마자는 나온 첫 턴만, 기습은 상대가 공격기일 때만 —")
    L.append("    이 표는 판의 흐름을 모른다. 해당 기술에는 '조건부' 주의가 붙는다)")
    L.append("  ! 상대 기술·배분은 사용률로 찍은 것이다. 실제로 뭘 들었는지는 모른다.")
    L.append(line)
    return "\n".join(L)


def _hits_ko(res):
    if res["hitsMin"] == res["hitsMax"]:
        return "%d번 (확정)" % res["hitsMax"]
    return "%d ~ %d번" % (res["hitsMin"], res["hitsMax"])


# ---------------------------------------------------------------------------
# 명령줄
# ---------------------------------------------------------------------------
USAGE = """사용법: python best.py <내 포켓몬> <상대 포켓몬> [기술...] [--트릭룸]

  예 : python best.py 메가보만다 하마돈
       python best.py 메가보만다 하마돈 이판사판태클 지진 용의춤
"""


def main():
    paths.fix_console()   # 윈도우에서 한글을 찍다 죽지 않게
    args = [a for a in sys.argv[1:]]
    trick_room = False
    for flag in ("--트릭룸", "--trickroom", "--tr"):
        if flag in args:
            args.remove(flag)
            trick_room = True
    if len(args) < 2:
        print(USAGE)
        return

    dex = calc.Dex()
    try:
        my_poke = dex.find_pokemon(args[0])
        opp_poke = dex.find_pokemon(args[1])
        move_names = args[2:] or None
        me, my_note = calc.popular_build(dex, my_poke)
        opp, opp_note = calc.popular_build(dex, opp_poke)
        a = analyze(dex, me, opp, move_names, trick_room=trick_room)
    except LookupError as e:
        print("! %s" % e)
        return

    print(report(dex, a, notes={"me": my_note, "opp": opp_note}))


if __name__ == "__main__":
    main()
