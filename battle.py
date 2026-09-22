# -*- coding: utf-8 -*-
"""
4-B — 턴을 실제로 넘겨 보는 곳.

    python battle.py 메가보만다 하마돈
    python battle.py 메가보만다 하마돈 --계획 용의춤,이판사판태클

`best.py` 는 한 턴만 본다. 그래서 데미지가 0인 기술(용의춤·날개쉬기·칼춤)에는
점수를 못 매긴다. 여기서는 턴을 끝까지 돌려 보고 답을 낸다.

**내놓는 답은 승패가 아니라 '끝났을 때의 상태' 다.**

    나쁜 설계  ->  "이겼다"
    맞는 설계  ->  "이겼다. 끝났을 때 HP 62%, 공격+1, 스피드+1, 자뭉열매 씀"

쌓아 놓은 랭크는 상대가 쓰러져도 남아서 후속 포켓몬까지 따라간다.
승패만 보면 용의춤의 값어치가 통째로 안 보인다.
이렇게 해 두면 나중에 후속 포켓몬을 붙일 때 이 파일을 다시 짤 필요가 없다.

또 하나. **판단의 근거를 남긴다.** 나중에 실전에서 이 도구가 고른 수를 두고 졌을 때
'규칙이 틀렸나 / 판단이 나빴나 / 그냥 운이 나빴나' 를 갈라내야 하기 때문이다.
결과만 출력하고 근거를 안 남기면 그 분석이 불가능하다.
"""

import math
import paths
import random
import re
import sys

import best
import calc
import scout

# ---------------------------------------------------------------------------
# 능력치 이름 — 게임 설명문의 표기를 우리 키로 옮긴다
# ---------------------------------------------------------------------------
STAT_WORD = {
    "공격": "attack", "방어": "defense", "특수공격": "spAtk",
    "특수방어": "spDef", "스피드": "speed",
}

# 날씨가 어느 타입을 올리고 어느 타입을 깎는가.
# **게임 데이터에 숫자가 없다.** 본편 값을 쓰고 경고를 띄운다 — 압정과 같다.
WEATHER_BOOST = {"비": "물", "쾌청": "불꽃"}
WEATHER_WEAKEN = {"비": "불꽃", "쾌청": "물"}

# 같은 편 필드에 까는 것들. 기술 설명문에서 이름과 턴수를 읽는다.
# 물리만 깎는 것 / 특수만 깎는 것 / 둘 다 깎는 것으로 갈린다.
# 값이 "물리"/"특수" 면 그 분류만 깎고, None 이면 둘 다 깎는다.
# "-" 는 **데미지를 안 깎는 것**이다 — 순풍은 같은 자리에 깔리지만
# 스피드를 두 배로 만드는 것이라 데미지와 상관이 없다. 이걸 안 갈라 두면
# 순풍이 조용히 스크린 노릇을 한다.
SCREEN_KIND = {"리플렉터": "물리", "빛의장막": "특수", "오로라베일": None,
               "순풍": "-"}
SCREEN_SPEED = {"순풍": 2.0}

# 날씨를 등장만으로 까는 특성
WEATHER_ABILITY = {
    "모래날림": "모래바람", "가뭄": "쾌청", "잔비": "비", "눈퍼뜨리기": "눈",
    "그래스메이커": "그래스필드", "일렉트릭메이커": "일렉트릭필드",
    "사이코메이커": "사이코필드", "미스트메이커": "미스트필드",
}
TERRAIN = {"그래스필드", "일렉트릭필드", "사이코필드", "미스트필드"}
# 필드가 어느 타입에 영향을 주는가.
# **게임 데이터에는 이 규칙이 없다.** 본편 값을 가져다 쓴 것이고 전부 미확인이다.
# 배율은 calc.CONFIG["terrain_boost"] 한 곳에 모여 있다.
TERRAIN_TYPE = {"그래스필드": "풀", "일렉트릭필드": "전기", "사이코필드": "에스퍼"}
TERRAIN_WEAKEN = {"미스트필드": "드래곤"}      # 미스트필드는 드래곤을 반감시킨다
# 모래바람 데미지를 안 받는 타입
SAND_IMMUNE = {"땅", "바위", "강철"}

# 계산에 넣은 상태 이상. 나머지는 이름만 붙고 효과가 없다 (경고를 띄운다).
STATUS_DONE = {"화상", "마비", "독", "맹독", "잠듦", "졸음", "얼음", "혼란"}
# 한 번에 하나만 걸리는 것들 (혼란·졸음은 여기 끼지 않고 따로 붙는다)
MAJOR_STATUS = {"화상", "마비", "독", "맹독", "잠듦", "얼음"}

# 기술 설명문에 적힌 타입 면역. '풀타입 포켓몬에게는 효과가 없다' 같은 문장.
_MOVE_TYPE_IMMUNE = re.compile(r"([가-힣]+)타입 포켓몬에게는 효과가 없다")
# 특성 설명문에 적힌 상태이상 면역. '마비 상태가 되지 않는다' 같은 문장.
_ABILITY_IMMUNE = re.compile(r"([가-힣,\s]+?) 상태가 되지 않는다")

# 맞을 때마다 뭔가 일어나는 특성.
# 배율이 아니라 '턴마다 벌어지는 일' 이라 calc.py 로는 못 다뤘던 것들이다.
# 설계 문서 2장에서 '메타 상위권인데 못 한다' 고 꼽은 것이 바로 이 표다.
ON_HIT_ABILITY = {
    # 브리두라스(8위) — 맞을 때마다 방어가 오른다. 2타 이상이 계산보다 덜 들어간다.
    "지구력":     {"kind": "rank", "stat": "defense", "step": 1},
    # 드닐레이브(7위) — 불꽃을 맞으면 공격이 오른다.
    "열교환":     {"kind": "rank_on_type", "type": "불꽃",
                   "stat": "attack", "step": 1},
    # 한카리아스(2위) 99.1% — 접촉기로 때린 쪽이 최대 HP의 1/8 을 받는다.
    "까칠한피부": {"kind": "contact_recoil", "frac": 1 / 8.0},
    # 킬라플로르(16위) 92.7% — 물리 기술을 맞으면 상대 쪽에 독압정을 깐다
    "독치장":     {"kind": "hazard_on_hit", "hazard": "독압정"},
}
# 한 번은 통째로 버티는 특성. 데미지 배율이 아니라 별도 규칙이라 여기 둔다.
DISGUISE = "탈"          # 따라큐(11위) 100% — 첫 공격을 무효로 하고 최대 HP의 1/8 소모
ENDURE_FULL = "옹골참"   # HP가 꽉 차 있으면 한 방에 안 죽고 1 남는다

# --- 5단계: 교체 -----------------------------------------------------------
# 나올 때 한 번 터지는 특성. 날씨 까는 것들은 WEATHER_ABILITY 에 따로 있다.
ENTRY_ABILITY = {
    # 보만다(1위) 99.3%, 갸라도스(14위) 99.4% — 나올 때마다 상대 공격을 깎는다
    "위협": {"kind": "foe_rank", "stat": "attack", "step": -1},
    "파수견": {"kind": "self_rank", "stat": "attack", "step": 1},
}
# 위협을 무시하는 특성
INTIMIDATE_PROOF = {"파수견", "둔감", "마이페이스", "정신력"}
# 강제 교체를 안 당하는 특성 (설명문에 '교체시키는 기술 ... 효과를 받지 않는다')
PHAZE_PROOF = {"흡반", "파수견"}
# 상대를 못 빠지게 하는 특성
TRAP_ABILITY = {"그림자밟기", "개미지옥", "자력"}
# 상대의 변화 기술이 아예 안 통하는 특성. 타부자고(9위) 100% 다.
STATUS_MOVE_PROOF = {"황금몸"}
# 능력이 깎이지 않는 특성. 미러아머는 깎은 쪽에게 되돌려준다.
STAT_DROP_PROOF = {"하얀연기", "클리어바디", "메탈프로텍트", "꽃무늬장식"}
MIRROR_ARMOR = "미러아머"
# HP 가 반 이하가 되면 스스로 물러나는 특성.
# 갑주무사(5위)의 기본 폼 특성이다. 다만 98.6% 가 메가로 가고 메가는
# 단단한발톱이라, 실제로 이 특성으로 싸우는 것은 나머지 1.4% 다.
# (사용률의 '특성 100%' 는 기본 폼 기준 집계라는 것을 여기서 또 확인했다.)
EMERGENCY_EXIT = {"위기회피", "허둥지둥"}
# 물리 기술을 맞으면 상대 쪽에 압정을 깐다. 킬라플로르(16위) 92.7% 다.
HAZARD_ON_HIT = {"독치장": "독압정"}

# 압정. 나올 때 한 번 맞는다.
# 수치는 게임 데이터에 없어서 calc.CONFIG 에 본편 값을 모아 뒀다.
HAZARDS = ("스텔스록", "압정뿌리기", "독압정", "끈적끈적네트")
# 땅에 안 닿아 있으면 압정을 안 밟는다 (스텔스록은 예외 — 공중에도 맞는다)
GROUNDED_IMMUNE_TYPES = {"비행"}
GROUNDED_IMMUNE_ABILITY = {"부유", "천정부지"}


# ---------------------------------------------------------------------------
# 변화기가 무슨 일을 하는가 — 게임 설명문에서 읽어낸다
# ---------------------------------------------------------------------------
# 도구·특성과 같은 방식이다. 규칙을 손으로 적지 않으므로 새 기술이 나와도 따라온다.
# 받침이 있으면 '공격을', 없으면 '방어를' 이라 조사가 갈린다. 둘 다 받는다.
_RANK = re.compile(
    r"((?:자신|상대)의 )?([가-힣]+(?:, ?[가-힣]+)*)[를을] (\d)단계 "
    r"(올린|떨어뜨린|올리고|떨어뜨리고)")
_HEAL = re.compile(r"자신의 최대 HP의 1/(\d+)만큼 회복")
_HEAL_FULL = re.compile(r"자신의 HP와 상태 이상을 모두 회복")
_STATUS = re.compile(r"상대를 ([가-힣]+) 상태로 만든다")
_PROTECT = re.compile(r"사용한 턴 동안 상대의 (?:공격|기술)으?로부터 몸을 보호")
_PHAZE = re.compile(r"랜덤한 포켓몬으로 교체시킨다")
_HAZARD = re.compile(r"상대 필드를 ([가-힣]+) 상태로 만든다")
_WEATHER = re.compile(r"5턴 동안 (?:전체 필드를 )?([가-힣]+) 상태로 만든다")
_RECOIL = re.compile(r"준 데미지의 1/(\d+)만큼 자신도")


# "5턴 동안 같은 편 필드를 빛의장막 상태로 만든다" — 순풍도 같은 꼴이다
_SCREEN = re.compile(r"(\d+)턴 동안 같은 편 필드를 (.+?) 상태로 만든다")
_SUBSTITUTE = re.compile(r"HP를 소비하여 대타를 내보낸다")
_DESTINY = re.compile(r"자신은 길동무 상태가 된다")
_REVIVE = re.compile(r"기절한 지닌 포켓몬을 최대 HP의 1/(\d+) 상태로 부활")
_TRICK = re.compile(r"상대와 자신의 지니고 있는 도구를 바꾼다")
_BATON = re.compile(r"다른 지닌 포켓몬과 교체한다\. 능력 변화")
_PERISH = re.compile(r"필드의 전원을 멸망 상태로 만든다")
_HEAL_WISH = re.compile(r"자신은 기절하게 되지만 다음에 내보내는 포켓몬의 HP를 모두 회복")
_DEFOG = re.compile(r"리플렉터, 압정뿌리기.*등을 해제한다")
_FOCUS_ENERGY = re.compile(r"자신은 급소업 상태가 된다\. \(\+(\d+)\)")
_TYPE_CHANGE = re.compile(r"상대의 타입을 (.+?)타입으로 바꾼다")
_BELLY = re.compile(r"HP를 소비하여 공격을 (\d+)단계까지 올린다")
_WISH = re.compile(r"자신이 위치한 자리를 희망사항 상태로 만든다")
_PAIN_SPLIT = re.compile(r"남은 HP를 더한 다음 1/2씩 나눠 갖는다")
_HAZE = re.compile(r"전체 필드의 능력 변화를 없앤다")
_ENDURE_MOVE = re.compile(r"사용한 턴 동안 기절할 듯한 기술로 데미지를 입으면 "
                          r"HP를 1 남기고 버틴다")


def move_effects(move):
    """이 기술이 하는 일을 목록으로. 못 읽은 것은 'unknown' 으로 남긴다."""
    d = move.get("description") or ""
    out = []

    # 랭크 변화. '자신의 스피드를 1단계 떨어뜨리고 공격, 방어를 1단계 올린다' 처럼
    # 뒷 문장에는 '자신의' 가 생략되므로 앞에서 본 대상을 이어 쓴다.
    who = None
    for prefix, names, step, verb in _RANK.findall(d):
        if prefix:
            who = "self" if prefix.startswith("자신") else "foe"
        if who is None:
            continue
        # '올린' 은 '올리'로 시작하지 않는다 — 한글은 '린'과 '리'가 서로 다른 한 글자다.
        # 여기서 부호가 뒤집히면 용의춤이 공격 -1 이 되어 버린다. 첫 글자만 본다.
        sign = 1 if verb[0] == "올" else -1
        for name in names.split(","):
            key = STAT_WORD.get(name.strip())
            if key:
                out.append({"kind": "rank", "who": who, "stat": key,
                            "step": sign * int(step)})

    m = _HEAL.search(d)
    if m:
        out.append({"kind": "heal", "frac": 1.0 / int(m.group(1))})
    elif _HEAL_FULL.search(d):
        # 잠자기 — HP와 상태 이상을 전부 되돌리는 대신 자기가 잠든다
        out.append({"kind": "heal", "frac": 1.0, "cure": True})
        out.append({"kind": "self_status", "status": "잠듦"})
    m = _STATUS.search(d)
    if m:
        out.append({"kind": "status", "status": m.group(1)})
    if _PROTECT.search(d):
        out.append({"kind": "protect"})
    if _PHAZE.search(d):
        out.append({"kind": "phaze"})
    if _DESTINY.search(d):
        out.append({"kind": "destiny"})
    m = _REVIVE.search(d)
    if m:
        out.append({"kind": "revive", "frac": 1.0 / int(m.group(1))})
    if _TRICK.search(d):
        out.append({"kind": "trick"})
    if _BATON.search(d):
        out.append({"kind": "baton"})
    if _PERISH.search(d):
        out.append({"kind": "perish", "turns": 3})
    if _HEAL_WISH.search(d):
        out.append({"kind": "heal_wish"})
    if _DEFOG.search(d):
        out.append({"kind": "defog"})
    m = _FOCUS_ENERGY.search(d)
    if m:
        out.append({"kind": "crit_up", "step": int(m.group(1))})
    m = _TYPE_CHANGE.search(d)
    if m:
        out.append({"kind": "retype", "type": m.group(1)})
    m = _BELLY.search(d)
    if m:
        out.append({"kind": "belly", "step": int(m.group(1)), "cost": 0.5})
    if _SUBSTITUTE.search(d):
        out.append({"kind": "substitute", "frac": 0.25})
    if _WISH.search(d):
        out.append({"kind": "wish", "frac": 0.5})
    if _PAIN_SPLIT.search(d):
        out.append({"kind": "pain_split"})
    if _HAZE.search(d):
        out.append({"kind": "haze"})
    if _ENDURE_MOVE.search(d):
        out.append({"kind": "endure_turn"})
    m = _SCREEN.search(d)
    if m:
        out.append({"kind": "screen", "name": m.group(2),
                    "turns": int(m.group(1))})
    m = _WEATHER.search(d)
    if m:
        out.append({"kind": "weather", "weather": m.group(1)})
    else:
        m = _HAZARD.search(d)
        if m:
            out.append({"kind": "hazard", "hazard": m.group(1)})

    if move["category"] == "변화" and not out:
        out.append({"kind": "unknown"})
    return out


# ---------------------------------------------------------------------------
# 도구가 대전 중에 하는 일
# ---------------------------------------------------------------------------
#
# `calc.Dex.item_effects` 는 **데미지 배율**만 읽는다. 여기서 읽는 것은
# 턴이 있어야 뜻이 생기는 것들이다 — 버티기, 회복, 접촉 반동, 타입 무효.
#
# **왜 만들었나.** 아머까오의 도구 1·2·3위(울퉁불퉁멧 66% · 먹다남은음식
# 24% · 자뭉열매 9%, 합쳐서 99%)가 전부 미구현이라 400판을 **맨몸으로**
# 싸워 놓고 "아머까오가 진다" 고 보고한 적이 있다. 접촉기를 네 번 맞고도
# 울퉁불퉁멧 반동이 한 번도 안 들어갔다. 상위 20종에서 **효과가 아예
# 없는 도구의 채용률 합이 중앙값 45%** 였다.
#
# 설명문에서 읽는다. 데미지 도구와 같은 방식이라 새 도구가 나와도 따라온다.
# 못 읽은 도구는 버리지 않고 이름을 남겨서 `_warn_dead_items` 가 세도록 한다.
_ITEM_RULES = [
    (r"HP가 꽉 찼을 때 .*기절할 듯한 기술로 데미지를 입으면 HP를 1 남기고",
     lambda m: {"kind": "endure", "chance": 1.0, "full_hp": True}),
    (r"기절할 듯한 기술로 데미지를 입으면 (\d+)% 확률로 HP를 1 남기고",
     lambda m: {"kind": "endure", "chance": int(m.group(1)) / 100.0,
                "full_hp": False}),
    (r"턴 종료 시 최대 HP의 1/(\d+)만큼 회복",
     lambda m: {"kind": "heal_turn", "frac": 1.0 / int(m.group(1))}),
    (r"남은 HP가 최대 HP의 1/(\d+) 이하가 되었을 때 최대 HP의 1/(\d+)만큼 회복",
     lambda m: {"kind": "heal_pinch", "at": 1.0 / int(m.group(1)),
                "frac": 1.0 / int(m.group(2))}),
    (r"남은 HP가 최대 HP의 1/(\d+) 이하가 되었을 때 HP를 (\d+) 회복",
     lambda m: {"kind": "heal_pinch", "at": 1.0 / int(m.group(1)),
                "flat": int(m.group(2))}),
    (r"접촉 기술을 받으면 상대 최대 HP의 1/(\d+)만큼 데미지",
     lambda m: {"kind": "contact_chip", "frac": 1.0 / int(m.group(1))}),
    (r"땅 위에 있지 않게 되어",
     lambda m: {"kind": "float"}),
    (r"모든 상태 이상과 혼란 상태를 회복",
     lambda m: {"kind": "cure", "statuses": None}),
    (r"능력이 떨어지면 원래대로 되돌린다",
     lambda m: {"kind": "restore_ranks"}),
    (r"(?:빛의장막|리플렉터|오로라베일).*지속 시간이 (\d+)턴 증가",
     lambda m: {"kind": "extend", "what": "screen", "turns": int(m.group(1))}),
    (r"필드를 전개했을 때 지속 시간이 (\d+)턴 증가",
     lambda m: {"kind": "extend", "what": "terrain", "turns": int(m.group(1))}),
    (r"(비|모래바람|눈|쾌청|쨍쨍한 햇살) 상태로 만들었을 때 지속 시간이 (\d+)턴 증가",
     lambda m: {"kind": "extend", "what": "weather",
                "weather": m.group(1), "turns": int(m.group(2))}),
    (r"^(.+?필드) 상태일 때 (.+?)가 (\d+)단계 올라간다",
     lambda m: {"kind": "seed", "terrain": m.group(1),
                "stat": m.group(2), "step": int(m.group(3))}),
    (r"^(.+?)타입 기술의 위력이 (\d+\.\d+)배가 된다\. 한 번 사용하면",
     lambda m: {"kind": "jewel", "type": m.group(1),
                "mult": float(m.group(2))}),
    (r"^기술의 명중률이 (\d+\.\d+)배",
     lambda m: {"kind": "accuracy", "mult": float(m.group(1))}),
    (r"자신에게 상대가 사용하는 기술의 명중률이 (\d+\.\d+)배",
     lambda m: {"kind": "evasion", "mult": float(m.group(1))}),
    (r"상대보다 행동 순서가 늦으면 기술의 명중률이 (\d+\.\d+)배",
     lambda m: {"kind": "accuracy_slow", "mult": float(m.group(1))}),
    (r"^급소업\+(\d+)이 된다",
     lambda m: {"kind": "crit_stage", "step": int(m.group(1))}),
    (r"^(.+?)가 급소업\+(\d+)[이가] 된다",
     lambda m: {"kind": "crit_stage", "step": int(m.group(2)),
                "who": [x.strip() for x in m.group(1).split(",")]}),
    (r"자신에게 기술로 데미지를 준 상대를 교체시킨다",
     lambda m: {"kind": "force_switch_foe"}),
    (r"기술로 데미지를 입으면 지닌 포켓몬으로 돌아간다",
     lambda m: {"kind": "self_switch"}),
    (r"(\d+)% 확률로 우선도가 같은 기술 중에서 가장 먼저 행동",
     lambda m: {"kind": "quick", "chance": int(m.group(1)) / 100.0}),
    (r"기술로 데미지를 주었을 때 (\d+)% 확률로 상대를 풀죽게",
     lambda m: {"kind": "flinch", "chance": int(m.group(1)) / 100.0}),
    (r"기술로 데미지를 주었을 때 그 데미지의 1/(\d+)만큼 자신의 HP를 회복",
     lambda m: {"kind": "drain_hit", "frac": 1.0 / int(m.group(1))}),
    (r"HP를 흡수하는 기술의 회복량이 (\d+\.\d+)배",
     lambda m: {"kind": "drain_boost", "mult": float(m.group(1))}),
    (r"^(.+?)의 공격, 특수공격이 (\d+)배가 된다",
     lambda m: {"kind": "only_for", "who": [m.group(1)],
                "mult": int(m.group(2))}),
    (r"교체를 방해하는 효과를 무시하고",
     lambda m: {"kind": "free_switch"}),
    (r"바인드 상태로 주는 데미지가 .*1/\d+이 아니라 1/(\d+)",
     lambda m: {"kind": "bind_chip", "frac": 1.0 / int(m.group(1))}),
    (r"같은 기술을 연속해서 사용하면 위력이 올라간다.*?최대 (\d+)배",
     lambda m: {"kind": "metronome", "step": 0.2, "cap": float(m.group(1))}),
    (r"PP가 0이 된 기술의 PP를 (\d+) 회복",
     lambda m: {"kind": "pp", "amount": int(m.group(1))}),
    # 상태 회복 열매 — **제일 마지막에 둔다.** '^(.+?) 상태를 회복한다' 는
    # 너무 넓어서 앞에 두면 다른 규칙을 잡아먹는다.
    (r"^(.+?) 상태를 회복한다\.",
     lambda m: {"kind": "cure",
                "statuses": [x.strip() for x in m.group(1).split(",")]}),
]

# **여기가 정직함을 지키는 자리다.** 설명문을 읽어냈다는 것과 턴 루프가
# 그걸 실제로 쓴다는 것은 다르다. 전에 `dex.item_effects`(데미지 표) 만
# 보고 "먹다남은음식·자뭉열매가 미구현" 이라고 보고했는데, 사실 둘 다
# 턴 루프에 손으로 박혀 있었다. 표 하나만 보고 세면 또 틀린다.
# **아래 집합에 넣기 전에 반드시 코드를 붙인다.**
APPLIED_ITEM_KINDS = {
    "endure", "heal_turn", "heal_pinch", "contact_chip", "float",
    "cure", "restore_ranks", "jewel", "crit_stage",
    "accuracy", "evasion", "accuracy_slow",
    "drain_hit", "flinch", "force_switch_foe", "self_switch",
    "extend", "seed",
    # 큰뿌리 — 2026-09-22 흡수 기술(드레인펀치 등)을 붙이면서 같이 붙었다 (_secondaries)
    "drain_boost",
}

# ★ **반만 붙은 것.** 위 집합에 들어 있어서 경고가 안 뜨는데,
#   실제로는 효과의 일부만 돈다. **이게 제일 고약하다** — "안 붙었다" 는
#   경고라도 뜨지만, 반만 붙은 것은 붙었다고 말하면서 틀린 답을 준다.
#
#   {종류: (도는 것, 안 도는 것)}
# 지금은 비어 있다. **비워 두더라도 장치는 남겨 둔다** — 다음에 또
# 반만 붙일 것이기 때문이다.
#
# 여기 있던 것: `float`(풍선). 압정을 안 밟는 것과 맞으면 터지는 것은
# 돌았는데 **땅 기술 무효가 없었다.** `_grounded()` 가 `_apply_hazards`
# 에서만 쓰여 데미지 계산에 안 닿았다. 타부자고(사용률 9위)가 풍선을
# 66.2% 로 드는데, 한카리아스(지진) vs 타부자고가 **풍선이 있든 없든
# 100%** 였다. 2026-09-20 에 `calc.floating_items` 로 고쳤고
# 재 보니 **100% -> 0%** 로 뒤집혔다. 그래서 여기서 뺐다.
PARTIAL_ITEM_KINDS = {}
# 아직 못 붙인 것 — 모델에 그 개념 자체가 없다. 붙이면 위로 옮긴다.
#   quick      : 우선도가 같을 때 끼어드는 것 (best.turn_order 를 고쳐야 한다)
#   pp         : PP 를 안 세고 있다
#   bind_chip  : 바인드(조르기) 상태가 없다
#   metronome  : 같은 기술 연속 횟수를 안 세고 있다
#   only_for   : 피카츄 전용 (챔피언스 상위권에 없다)
#   free_switch: 교체를 막는 효과가 아직 없다

_ITEM_CACHE = {}


def item_behaviors(dex):
    """도구 이름 -> 대전 중 효과 목록. dex 하나당 한 번만 읽는다.

    ! 전에는 `id(dex)` 를 열쇠로 썼다. 파이썬은 객체가 사라지면 그 id 를
      **다시 내준다.** 새 Dex 가 옛 Dex 의 id 를 물려받으면 남의 표를
      돌려주게 된다. 조용히 틀어지는 종류라 dex 에 직접 붙인다.
    """
    got = getattr(dex, "_item_behaviors", None)
    if got is not None:
        return got
    out = {}
    for it in dex.items:
        d = it["description"] or ""
        got = []
        for pattern, make in _ITEM_RULES:
            m = re.search(pattern, d)
            if m:
                got.append(make(m))
                break            # 도구 하나에 규칙 하나면 충분하다
        if got:
            out[it["name"]] = got
    try:
        dex._item_behaviors = out
    except AttributeError:
        pass
    return out


def item_effect(dex, item, kind):
    """그 도구에 그 효과가 있으면 돌려준다. 없으면 None."""
    if not item:
        return None
    for ef in item_behaviors(dex).get(item) or ():
        if ef["kind"] == kind:
            return ef
    return None


def status_immune_abilities(dex):
    """특성 설명문에서 '무슨 상태가 안 걸리는지' 를 읽어낸다.

    게임 데이터에 그대로 적혀 있다 — 유연(마비), 불면·의기양양(잠듦·졸음),
    면역(독·맹독), 마그마의무장(얼음), 수포·열교환(화상) 등.
    """
    out = {}
    for a in dex.abilities:
        for chunk in _ABILITY_IMMUNE.findall(a["description"]):
            # '자신과 같은 편은 잠듦, 졸음' 처럼 앞에 말이 붙는 경우가 있으므로
            # 쉼표뿐 아니라 공백으로도 쪼갠 뒤 아는 이름만 고른다.
            names = re.split(r"[,\s]+", chunk.strip())
            got = {n for n in names if n in STATUS_DONE or n == "헤롱헤롱"}
            if got:
                out.setdefault(a["name"], set()).update(got)
    return out


def move_type_immunity(move):
    """이 기술이 안 통하는 타입. 설명문에 적혀 있는 것만."""
    return _MOVE_TYPE_IMMUNE.findall(move.get("description") or "")


def move_recoil(move):
    """반동으로 자신이 받는 비율. 없으면 0."""
    m = _RECOIL.search(move.get("description") or "")
    return 1.0 / int(m.group(1)) if m else 0.0


# ---------------------------------------------------------------------------
# 설명문에 적힌 '실패한다' 조건과 그 짝 (2026-09-22)
#
# ! 전에는 이 조건들을 **하나도** 안 읽었다. 폴터가이스트가 도구 없는 상대에게
#   맞고(사용자 영상에서 잡힘), 만나자마자(갑주무사 71.8%)가 매 턴 위력 100
#   선제기로, 기습(대도각참 99%)이 상대가 변화기를 써도 들어갔다. 터지지 않고
#   그 기술을 든 쪽이 조용히 세졌다.
# 규칙마다 **걸리는 기술을 전부 세어서** 딱 그 기술만 잡는 것을 확인했다
# (tests.py [48] 이 못 박는다). 이름을 박지 않고 설명문을 읽는다.
# ---------------------------------------------------------------------------
_FIRST_ONLY = re.compile(r"등장하고 가장 먼저 사용하지 않으면 실패")       # 속이기·만나자마자
# 기습. 설명문은 "상대가 공격 기술을 선택하였고 ... 이미 공격하였다면 실패" 로
# 옮겨져 있는데, 본편 규칙은 '상대가 공격기를 안 골랐거나 이미 움직였으면 실패' 다.
_SUCKER = re.compile(r"상대가 공격 기술을 선택하였고 이 기술을 사용한 턴 동안 이미 공격하였다면 실패")
_UPPER_HAND = re.compile(r"상대가 선제 공격 기술을 사용하지 않은 경우 실패")  # 기선제압
_FOCUS = re.compile(r"상대로부터 먼저 기술로 데미지를 입으면 실패")         # 힘껏펀치
_LAST_RESORT = re.compile(r"다른 배운 기술을 모두 사용하지 않은 경우 실패")  # 비장의무기
_BELCH = re.compile(r"나무열매를 먹지 않은 경우 이 기술은 실패")            # 트림
_NEED_STOCKPILE = re.compile(r"비축하기 상태가 아닌 경우 이 기술은 실패")    # 토해내기·꿀꺽
_STOCKPILE = re.compile(r"비축하기 상태를 1회 추가")                        # 비축하기
_NEED_TERRAIN = re.compile(r"필드가 전개되어 있지 않은 경우 실패")          # 아이언롤러
_CLEAR_TERRAIN = re.compile(r"필드를 해제한다")                            # 아이언롤러·아이스스피너
_CRASH = re.compile(r"빗나가거나 실패하면 자신의 최대 HP의 1/(\d+)만큼 데미지")  # 무릎차기 등
_AFTER_FAIL = re.compile(r"직전 턴에 자신이 행동하지 못했거나 기술이 빗나가거나 "
                         r"실패한 경우 위력이 (\d+)배")                     # 분함의발구르기·열불내기
_LOSE_TYPE = re.compile(r"자신의 (\S+?)타입이 없어진다")                   # 불사르기·전광쌍격
# 속이기·기선제압의 풀죽음은 확률이 아니라 기술 그 자체다 ('30% 확률로 ...' 와 다르다).
_FLINCH_ALWAYS = re.compile(r"(?:^|[.]\s*)상대를 풀죽게 한다")
_THAW_SELF = re.compile(r"자신의 얼음 상태를 회복")                        # 불꽃 기술 5개


def _abilities_saying(dex, attr, phrase):
    """설명문에 phrase 가 있는 특성들. dex 에 붙여 외운다 (§7 — id 열쇠 금지)."""
    got = getattr(dex, attr, None)
    if got is None:
        got = {a["name"] for a in dex.abilities
               if phrase in (a.get("description") or "")}
        setattr(dex, attr, got)
    return got


def flinch_proof_abilities(dex):
    """'풀죽지 않는다' 고 적힌 특성 (정신력)."""
    return _abilities_saying(dex, "_flinch_proof", "풀죽지 않")


def shield_dust_abilities(dex):
    """'공격의 추가 효과를 받지 않는다' (인분)."""
    return _abilities_saying(dex, "_shield_dust", "공격의 추가 효과를 받지 않는다")


def skill_link_abilities(dex):
    """'연속 기술을 사용하면 최고 횟수로' (스킬링크)."""
    return _abilities_saying(dex, "_skill_link", "연속 기술을 사용하면 최고 횟수로")


# 거대해머 — "이 기술은 2회 연속으로 사용할 수 없다." (설명문에 '실패' 가 없어서 따로 둔다)
_NO_REPEAT = re.compile(r"이 기술은 2회 연속으로 사용할 수 없다")


# ---------------------------------------------------------------------------
# 대전 중 한 마리의 상태
# ---------------------------------------------------------------------------
class Side(object):
    """`calc.Build` 는 그대로 두고, 대전 중 변하는 것만 여기 담는다.

    끝났을 때 이 객체가 그대로 '다음 포켓몬 상대의 시작 상태' 가 된다.
    """

    def __init__(self, dex, build, hp_pct=None):
        """hp_pct 를 주면 **그 비율에서 시작한다** (0~100).

        ! 이게 없어서 실전 도구가 반쪽이었다. 대전은 늘 만피에서
          시작하는 게 아니다. 3턴만 지나도 양쪽 다 깎여 있는데, 그걸
          못 넣으면 "지금 이 상황" 이 아니라 "처음이었다면" 을 재게 된다.
        """
        self.dex = dex
        # ★ **메가진화는 수(手)다.** 한 게임에 한 번이고, **언제 누구를**
        #   할지 고르는 것 자체가 판단이다 (사용자: "무조건 B야. 이건
        #   선택이 아니라 필수", 2026-09-21).
        #   그래서 메가 폼으로 받은 것은 **기본 폼으로 되돌려 시작**하고,
        #   메가 폼은 따로 들고 있다가 '메가' 를 두면 그때 바꾼다.
        #   되돌리기 전에는 특성도 기본 폼 것이다 — 갑주무사는 메가 전에
        #   단단한발톱이 아니라 위기회피다. 그게 실제 게임과 맞다.
        self.mega_form = None
        self.is_mega = False
        origin = build
        if build.poke.get("isMega"):
            base_poke = calc.base_form(dex, build.poke)
            if base_poke is not build.poke:
                self.mega_form = build
                build = calc.Build(
                    dex, base_poke, sp=build.sp, nature=build.nature,
                    ranks=build.ranks, item=build.item,
                    ability=calc.base_ability(dex, base_poke),
                    status=build.status, hp_ratio=build.hp_ratio)
        self.base = build
        # ! **넘겨받은 그대로의 Build 도 들고 있는다.** 위에서 메가 폼을
        #   기본 폼으로 갈아 끼우면 `self.base` 가 **새 객체**가 되는데,
        #   `Policy` 는 계획의 주인을 `is` 로 확인한다. 그래서 이걸 안 두면
        #   메가스톤 든 놈은 계획이 통째로 버려진다 — 전에 똑같은 자리에서
        #   크게 당했다 (CLAUDE.md §8-4). 검사 [22] 가 이걸 잡았다.
        self.origin = origin
        # ★ **이 놈이 될 수 있는 Build 를 전부 들고 있는다.**
        #   폼이 바뀌어도 '같은 놈' 인 것을 알아봐야 한다. 이게 없으면
        #   메가진화한 순간 `Policy` 가 계획의 주인을 못 알아보고,
        #   **내 기술 목록 밖의 기술을 꺼내 쓴다** (CLAUDE.md §8-1 의 재발).
        #   실제로 그랬다 — 땅 기술만 줬는데 메가한 뒤 화염방사를 써서
        #   아머까오(땅 무효)를 100% 로 이겼다. 검사 [41] 이 잡았다.
        self.forms = [b for b in (origin, build, self.mega_form)
                      if b is not None]
        self.max_hp = build.stat("hp")
        if hp_pct is None:
            self.hp = self.max_hp
        else:
            pct = max(0.0, min(100.0, float(hp_pct)))
            # 1 이상은 남긴다 — 0 으로 시작하면 이미 쓰러진 것이다
            self.hp = max(1, int(round(self.max_hp * pct / 100.0)))
        self.ranks = dict(build.ranks)
        self.status = build.status
        self.item = build.item
        self.item_used = False
        self.protecting = False
        # 이 턴에 풀죽었는가 (왕의징표석 등). 턴이 끝나면 지워진다.
        self.flinched = False
        # 대타출동으로 세운 인형의 남은 HP. 0 이면 없다.
        self.substitute = 0
        # 희망사항을 자기가 걸었는지 (표시용). 실제 회복은 Party.wish 가 한다.
        self.wish = 0
        # 버티기 — 이 턴만 HP 1 을 남긴다
        self.enduring = False
        # 길동무를 건 턴 번호. **턴 끝에 지우면 안 된다** — 길동무는
        # '내가 다음에 행동할 때까지' 가고, 쓴 턴에 이미 맞은 뒤라면
        # 정작 죽는 것은 다음 턴이기 때문이다. 한 번 그렇게 짰다가
        # 길동무가 한 번도 안 터졌다.
        self.destiny_turn = None
        # 멸망의노래 남은 턴. 0 이 되면 쓰러진다.
        self.perish = 0
        # 기충전 등으로 올라간 급소업 단계
        self.crit_stage = 0
        # 물붓기 등으로 바뀐 타입. None 이면 원래 타입.
        self.types_override = None
        # 따라큐의 탈. 첫 공격을 한 번 통째로 막는다.
        self.disguise = (build.ability == DISGUISE)
        # 상태 이상 부속 — 잠듦/얼음 남은 턴, 맹독 누적, 혼란, 졸음
        self.status_turns = 0
        self.toxic_n = 0
        self.confused = 0
        self.drowsy = 0
        # 배운 기술 이름 목록. 아는 경우에만 (Policy 가 내 기술을 알 때 채운다).
        # 비장의무기가 본다 — 모르면 '기술 4개' 로 보고 경고한다.
        self.moveset = None
        # 이 턴의 기록 — 기습·기선제압·힘껏펀치가 본다. Battle.step 이 매 턴 지운다.
        self.chosen = None           # 이 턴에 고른 기술 (교체했으면 None)
        self.moved = False           # 이 턴에 이미 행동했나
        self.hit_this_turn = False   # 이 턴에 기술로 데미지를 입었나
        self.move_failed = False     # 방금 쓴 기술이 빗나가거나 실패했나
        self.reset_entry()

    def reset_entry(self):
        """나온 뒤의 기록. 들어올 때마다 새로 시작한다 (switch_in 이 부른다).

        ! 교체해서 다시 나오면 속이기·만나자마자가 또 된다 — 그게 게임 규칙이다.
          그래서 Party 가 아니라 **나올 때마다** 지운다.
        """
        self.acted = False           # 나온 뒤 기술을 한 번이라도 썼나 (속이기·만나자마자)
        self.used_moves = set()      # 나온 뒤 쓴 기술 이름 (비장의무기)
        self.stockpile = 0           # 비축하기 횟수 (토해내기)
        self.last_failed = False     # 직전 행동이 실패했나 (분함의발구르기·열불내기)
        self.last_move = None        # 직전에 쓴 기술 (Policy._just_failed — 상대가 본다)
        # 판 중간에서 시작해 '막 나왔는지' 를 몰라서 막 나왔다고 **가정한** 몸인가.
        # Battle.__init__ 이 켜고, 실제로 교체해 들어오면 여기서 꺼진다.
        self.fresh_guessed = False

    @property
    def ate_berry(self):
        """이 배틀에서 나무열매를 먹었나 (트림). 먹은 열매는 item 에 이름이 남는다."""
        return bool(self.item_used and self.item and self.item.endswith("열매"))

    @property
    def name(self):
        return self.base.name

    def is_same(self, build):
        """이 놈이 그 Build 로 만들어졌나. **폼이 바뀌어도 같은 놈이다.**"""
        return any(build is f for f in self.forms)

    @property
    def can_mega(self):
        """지금 메가진화할 수 있는 몸인가 (파티가 아직 안 썼는지는 Party 가 본다)."""
        return self.mega_form is not None and not self.is_mega and self.alive

    def mega(self):
        """메가진화. 폼을 바꾸고 능력치를 다시 잡는다.

        **남은 HP 비율을 지킨다.** 메가는 보통 HP 종족값이 안 바뀌지만,
        바뀌는 폼이 생겨도 '반피였는데 만피가 되는' 일이 없게 한다.
        """
        if self.mega_form is None or self.is_mega:
            return False
        ratio = self.hp_ratio
        self.base = self.mega_form
        self.is_mega = True
        self.max_hp = self.base.stat("hp")
        self.hp = max(1, int(round(self.max_hp * ratio)))
        # 특성이 바뀐다 — 탈(따라큐)처럼 특성에 딸린 상태도 다시 잡는다
        self.disguise = (self.base.ability == DISGUISE)
        return True

    @property
    def alive(self):
        return self.hp > 0

    @property
    def hp_ratio(self):
        return self.hp / float(self.max_hp)

    def as_build(self):
        """지금 상태를 반영한 Build. 데미지 계산기에 그대로 넣을 수 있다.

        ! **타입이 바뀌어 있으면 바뀐 타입으로 넘겨야 한다.** 물붓기를
          넣고 나서 `types_override` 만 만들어 두고 여기서 안 넘겼더니,
          로그에는 "물타입이 됐다" 고 찍히는데 데미지는 원래 타입으로
          계산되고 있었다. 딱 이 프로젝트가 고장나는 방식이다.
        """
        poke = self.base.poke
        # ! `is not None` 이어야 한다. 불사르기로 순수 불꽃이 타입을 잃으면 [] 가
        #   되는데, 참/거짓으로 물으면 [] 가 '안 바뀜' 으로 읽혀 원래 타입으로 돌아간다.
        if self.types_override is not None:
            poke = dict(poke)
            poke["types"] = list(self.types_override)
        return calc.Build(
            self.dex, poke, sp=self.base.sp, nature=self.base.nature,
            ranks=self.ranks, item=None if self.item_used else self.item,
            ability=self.base.ability, status=self.status,
            hp_ratio=self.hp_ratio)

    def bump(self, stat, step):
        """랭크 변화. 위아래로 6이 한계다."""
        before = self.ranks.get(stat, 0)
        after = max(-6, min(6, before + step))
        self.ranks[stat] = after
        return after - before        # 실제로 움직인 칸수

    def herb(self):
        """하양허브 — 깎인 랭크를 통째로 되돌린다. 되돌렸으면 True."""
        if self.item_used or not item_effect(self.dex, self.item,
                                             "restore_ranks"):
            return False
        if not any(v < 0 for v in self.ranks.values()):
            return False
        for k, v in list(self.ranks.items()):
            if v < 0:
                self.ranks[k] = 0
        self.item_used = True
        return True

    def blocks_drop(self):
        """상대가 내 능력을 깎는 것을 막는가."""
        return (self.base.ability in STAT_DROP_PROOF
                or self.base.ability == MIRROR_ARMOR)

    def damage(self, amount, direct=True, rng=None):
        """데미지를 넣는다. 기합의띠·옹골참이 있으면 여기서 버틴다.

        direct=False 는 반동·칩 데미지처럼 '기술로 맞은 것' 이 아닌 경우다.
        기합의띠와 옹골참은 그때는 안 버틴다.
        """
        note = None
        if direct and amount >= self.hp and self.enduring:
            self.hp = 1
            return "버티기로 HP 1 남김"
        if direct and amount >= self.hp and self.hp == self.max_hp:
            if self.base.ability == ENDURE_FULL:
                amount = self.hp - 1
                note = "옹골참으로 HP 1 남기고 버팀"
            else:
                # **손으로 박아 두지 않는다.** 전에는 여기에 "기합의띠" 라는
                # 이름이 직접 적혀 있었다. 그러면 기합의머리띠(10% 버팀)
                # 같은 것이 조용히 빠진다. 설명문에서 읽은 규칙을 쓴다.
                ef = item_effect(self.dex, self.item, "endure")
                if ef and not self.item_used and (
                        not ef["full_hp"] or self.hp == self.max_hp):
                    if ef["chance"] >= 1.0 or (
                            rng is not None
                            and rng.random() < ef["chance"]):
                        amount = self.hp - 1
                        self.item_used = True
                        note = "%s 로 HP 1 남기고 버팀" % self.item
        self.hp = max(0, self.hp - amount)
        return note

    def heal(self, amount):
        amount = int(amount)
        before = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        return self.hp - before

    @property
    def types(self):
        """지금 이 몸의 타입. 물붓기 같은 것으로 바뀌어 있을 수 있다."""
        if self.types_override is not None:      # [] (타입 없음) 도 바뀐 것이다
            return self.types_override
        return self.base.types

    def rank_text(self):
        got = ["%s%+d" % (calc.STAT_KO[k], v)
               for k, v in self.ranks.items() if v]
        return " ".join(got) if got else "없음"

    def snapshot(self):
        """'끝났을 때의 상태'. 이게 이 파일이 내놓는 진짜 답이다."""
        return {
            "name": self.name, "hp": self.hp, "maxHp": self.max_hp,
            "hpPct": self.hp_ratio * 100.0,
            # 0인 랭크는 빼고 넘긴다. 안 그러면 '남는 것이 없다' 와
            # '0이 여섯 개 남았다' 를 구분할 수 없다.
            "ranks": {k: v for k, v in self.ranks.items() if v},
            "status": self.status, "itemUsed": self.item_used,
            "confused": self.confused > 0, "alive": self.alive,
        }


# **메가진화는 한 게임에 한 번뿐이다** (사용자가 알려 준 규칙, 2026-09-19).
#
# ! 처음엔 이걸 아예 안 지키고 있었다. `calc.popular_build` 이 "1위 도구가
#   메가스톤이면 메가로 본다" 며 **만들 때** 폼을 바꿔 버려서, 파티에 스톤
#   든 놈이 셋이면 **셋 다 메가로** 싸웠다. 경고도 없었다.
#   메가보만다·한카리아스·갑주무사 vs 하마돈·브리두라스·누리레느 에서
#   **메가 3마리 34.2% / 메가 1마리 0.0%** — 아예 다른 판이었다.
#
# ! 그 다음엔 "먼저 나오는 놈만 메가" 로 굳혀 놨는데, 그것도 틀렸다.
#   진짜 규칙은 "한 게임에 한 번" 이지 "선봉만" 이 아니다. 갑주무사를
#   기본 폼으로 버티다가 **나중에 나온 보만다를 메가로 쓰는** 수가 있는데
#   그걸 표현조차 못 했다. 사용자가 못 박았다 —
#   *"무조건 B야. 이건 선택이 아니라 필수"* (2026-09-21).
#
# 그래서 지금은 **메가가 수(手)다.** 모두 기본 폼으로 시작하고
# (`Side.__init__`), 턴에 `("메가", 기술)` 을 두면 그때 메가가 된다.
# 한 편이 한 번 쓰면 `Party.mega_used` 가 잠긴다.
MEGA_PER_GAME = 1


class Party(object):
    """한 쪽이 데리고 나온 포켓몬들. 지금 나와 있는 것과 벤치.

    기본 룰이 6마리 파티 -> 3마리 선출이므로, 여기 들어오는 건 보통 3마리다.
    1마리만 넣으면 4-B 와 똑같이 1대1 이 된다.
    """

    def __init__(self, dex, builds, hp_pcts=None):
        """hp_pcts 를 주면 각자 그 비율에서 시작한다. [100, 55, None] 처럼."""
        if not isinstance(builds, (list, tuple)):
            builds = [builds]
        self.dex = dex
        hp_pcts = list(hp_pcts or [])
        # 이 편이 메가를 이미 썼는가. 한 게임에 한 번뿐이다.
        self.mega_used = False
        self.members = [Side(dex, b,
                             hp_pcts[i] if i < len(hp_pcts) else None)
                        for i, b in enumerate(builds)]
        self.active_idx = 0
        # 이 편이 '맞는' 압정. 상대가 깔아 둔 것이다.
        self.hazards = {}
        # 이 편이 '깐' 스크린. {이름: 남은 턴}
        self.screens = {}
        # 치유소원 — 다음에 나오는 놈이 다 낫는다
        self.heal_wish = False
        # 희망사항 — (남은 턴, 회복량). **자리에 걸리는 것**이라 건 놈이
        # 빠져도 다음에 나온 놈이 받는다. 그래서 Side 가 아니라 Party 다.
        self.wish = None

    @property
    def active(self):
        return self.members[self.active_idx]

    def can_mega(self, side=None):
        """지금 나와 있는 놈이 메가진화할 수 있나.

        **한 게임에 한 번**이라 이미 썼으면 아무도 못 한다.
        """
        if self.mega_used:
            return False
        side = side or self.active
        return side.can_mega

    def do_mega(self, side=None):
        """메가진화시킨다. 됐으면 True."""
        side = side or self.active
        if not self.can_mega(side):
            return False
        if side.mega():
            self.mega_used = True
            return True
        return False

    def mega_candidates(self):
        """아직 메가를 안 썼다면, 메가할 수 있는 놈들의 번호."""
        if self.mega_used:
            return []
        return [i for i, m in enumerate(self.members) if m.can_mega]

    @property
    def alive(self):
        return any(m.alive for m in self.members)

    def bench(self):
        """지금 바꿔 나갈 수 있는 것들. (번호, Side) 목록."""
        return [(i, m) for i, m in enumerate(self.members)
                if i != self.active_idx and m.alive]

    def add_hazard(self, kind):
        """압정을 한 겹 쌓는다. 쌓을 수 있으면 True."""
        cap = 1
        if kind == "압정뿌리기":
            cap = calc.CONFIG["max_spike_layers"]
        elif kind == "독압정":
            cap = calc.CONFIG["max_toxic_layers"]
        now = self.hazards.get(kind, 0)
        if now >= cap:
            return False
        self.hazards[kind] = now + 1
        return True

    def screen_text(self):
        if not self.screens:
            return "없음"
        return " ".join("%s(%d턴)" % (k, v) for k, v in self.screens.items())

    def screen_mult(self, category):
        """이 편이 받는 데미지 배율. 스크린이 깔려 있으면 깎인다."""
        mult = 1.0
        for name in self.screens:
            kind = SCREEN_KIND.get(name, "-")   # 모르는 것은 안 깎는다
            if kind == "-":
                continue
            if kind is None or kind == category:
                mult *= calc.CONFIG["screen_reduce"]
        return mult

    def speed_mult(self):
        """순풍처럼 이 편 전체의 스피드를 바꾸는 것."""
        mult = 1.0
        for name in self.screens:
            mult *= SCREEN_SPEED.get(name, 1.0)
        return mult

    def tick_screens(self):
        out = []
        for name in list(self.screens):
            self.screens[name] -= 1
            if self.screens[name] <= 0:
                del self.screens[name]
                out.append("%s 가 사라졌다" % name)
        return out

    def hazard_text(self):
        if not self.hazards:
            return "없음"
        return " ".join("%s%s" % (k, "x%d" % v if v > 1 else "")
                        for k, v in self.hazards.items())


class Field(object):
    """날씨·필드. 전역 상태라 처음부터 자리를 만들어 둔다."""

    def __init__(self):
        self.weather = None
        self.weather_turns = 0
        self.terrain = None
        self.terrain_turns = 0

    def set(self, kind, turns=5):
        if kind in TERRAIN:
            self.terrain, self.terrain_turns = kind, turns
        else:
            self.weather, self.weather_turns = kind, turns

    def tick(self):
        out = []
        if self.weather:
            self.weather_turns -= 1
            if self.weather_turns <= 0:
                out.append("%s 가 그쳤다" % self.weather)
                self.weather = None
        if self.terrain:
            self.terrain_turns -= 1
            if self.terrain_turns <= 0:
                out.append("%s 가 사라졌다" % self.terrain)
                self.terrain = None
        return out


# ---------------------------------------------------------------------------
# 대전
# ---------------------------------------------------------------------------
class Battle(object):
    """1대1. 교체·파티는 아직 없다 (5단계).

    log 에 매 턴 무슨 일이 있었는지 남긴다. 나중에 실전에서 지고 나서
    '왜 졌나' 를 되짚으려면 이 기록이 있어야 한다.
    """

    def __init__(self, dex, me_build, opp_build, rng=None, log=False,
                 matchup=None, my_hp=None, opp_hp=None, my_active=0,
                 opp_hazards=None, my_hazards=None, opp_active=0,
                 my_fresh=None, opp_fresh=None):
        """my_fresh / opp_fresh — 지금 나와 있는 놈이 **이번 턴에 막 나왔나.**

        속이기·만나자마자는 나온 뒤 첫 기술일 때만 된다. 판 처음부터 돌리면
        당연히 True 지만(run_once 가 그렇게 준다), 실전 중간 상태에서 부르면
        알 수가 없다. None(모름)이면 막 나온 것으로 보되, 그 가정 때문에
        그 기술이 먹혔으면 **경고를 남긴다** — 조용히 넘어가지 않게.
        """
        self.dex = dex
        # 한 마리만 넣으면 1대1, 목록을 넣으면 교체가 있는 대전이 된다
        self.me_party = Party(dex, me_build, my_hp)
        self.opp_party = Party(dex, opp_build, opp_hp)
        if my_active:
            self.me_party.active_idx = my_active
        # 상대도 1번이 나와 있으란 법이 없다. 실전은 1턴부터 시작하지 않는다.
        if opp_active:
            self.opp_party.active_idx = opp_active
        # 이미 깔려 있는 압정도 받는다 (실전은 1턴부터 시작하지 않는다)
        if my_hazards:
            self.me_party.hazards = dict(my_hazards)
        if opp_hazards:
            self.opp_party.hazards = dict(opp_hazards)
        self.field = Field()
        self.rng = rng or random.Random()
        self.turn = 0
        self.log = [] if log else None
        self.warnings = []
        # 막 나왔는지 몰라서 '막 나왔다' 고 가정한 몸에는 표시를 단다 (Side.fresh_guessed).
        for party, fresh in ((self.me_party, my_fresh),
                             (self.opp_party, opp_fresh)):
            if fresh is None:
                party.active.fresh_guessed = True
            elif not fresh:
                party.active.acted = True
        self._immune_abilities = status_immune_abilities(dex)
        self._warn_dead_items()
        # 이름쌍 -> 1대1 승률. 교체 판단에 쓴다 (matchup_table 로 미리 재 둔다).
        self.matchup = matchup
        self._entry_weather()

    # 지금 나와 있는 놈. 교체가 들어와도 나머지 코드는 그대로 돌아간다.
    @property
    def me(self):
        return self.me_party.active

    @property
    def opp(self):
        return self.opp_party.active

    def _party_of(self, side):
        return (self.me_party if side in self.me_party.members
                else self.opp_party)

    def _say(self, text):
        if self.log is not None:
            self.log.append("%2d턴  %s" % (self.turn, text))

    def _warn(self, text):
        if text not in self.warnings:
            self.warnings.append(text)

    def _warn_dead_items(self):
        """**계산에 아무 일도 안 하는 도구를 들고 싸우면 큰 소리로 말한다.**

        한 번 크게 당했다. 아머까오(울퉁불퉁멧 66% · 먹다남은음식 24% ·
        자뭉열매 9%)로 한카리아스를 상대하는 판을 400판 돌려 놓고
        "아머까오가 진다" 고 보고했는데, 사실은 **도구 셋이 다 미구현**
        이라 맨몸으로 싸우고 있었다. 접촉기를 네 번 맞고도 울퉁불퉁멧
        반동이 한 번도 안 들어갔다.
        조용히 틀어진 것이라 결과만 봐서는 알 수가 없었다. 그래서 이제
        대전이 시작될 때 세어서 경고에 넣는다 — 승률 옆에 같이 찍힌다.
        """
        spd = best.speed_item_effects(self.dex)
        behave = item_behaviors(self.dex)
        for party, who in ((self.me_party, "나"), (self.opp_party, "상대")):
            for side in party.members:
                it = side.base.item
                if not it:
                    continue
                if (self.dex.item_effects.get(it)
                        or self.dex.mega_by_item.get(it)
                        or it in spd):
                    continue
                kinds = [e["kind"] for e in behave.get(it) or ()]
                left = [k for k in kinds if k not in APPLIED_ITEM_KINDS]
                # ★ **반만 붙은 것도 말한다.** 전에는 APPLIED 에 들어 있기만
                #   하면 조용히 넘어갔다. 풍선이 그래서 경고 한 줄 없이
                #   땅 기술을 그냥 맞고 있었다 — 도구가 미구현일 때보다
                #   나쁘다. 붙었다고 말하면서 틀린 답을 주기 때문이다.
                half = [k for k in kinds if k in PARTIAL_ITEM_KINDS]
                for k in half:
                    works, missing = PARTIAL_ITEM_KINDS[k]
                    self._warn("%s %s 의 %s 는 **반만 들어간다** — %s 는 "
                               "되지만 **%s 는 안 된다.** 이 승률은 그만큼 "
                               "틀려 있다." % (who, side.name, it,
                                            works, missing))
                if kinds and not left:
                    continue
                why = ("아직 구현 안 된 도구다" if not kinds
                       else "%s 는 아직 모델에 없다" % ", ".join(left))
                self._warn("%s %s 의 %s 는 **계산에 안 들어간다** (%s). "
                           "이 승률은 그 도구가 없다고 치고 나온 값이다."
                           % (who, side.name, it, why))

    # -- 교체 ---------------------------------------------------------------
    def _grounded(self, side):
        """땅에 닿아 있는가. 압정은 떠 있으면 안 밟는다 (스텔스록은 예외)."""
        if side.base.ability in GROUNDED_IMMUNE_ABILITY:
            return False
        if set(side.base.types) & GROUNDED_IMMUNE_TYPES:
            return False
        # 풍선 — 터지기 전까지는 떠 있다
        if item_effect(self.dex, side.item, "float") and not side.item_used:
            return False
        return True

    def _seed_item(self, side):
        """그래스시드·사이코시드 — 필드가 맞으면 한 번 랭크를 올린다."""
        if side.item_used or not side.alive:
            return
        ef = item_effect(self.dex, side.item, "seed")
        if not ef or self.field.terrain != ef["terrain"]:
            return
        key = STAT_WORD.get(ef["stat"])
        if not key:
            return
        if side.bump(key, ef["step"]):
            side.item_used = True
            self._say("%s 의 %s — %s %s%+d (지금 %s)"
                      % (side.name, side.item, side.name,
                         calc.STAT_KO[key], ef["step"], side.rank_text()))

    def _apply_hazards(self, party, side):
        """나올 때 압정을 밟는다. 수치는 게임 데이터에 없어서 본편 값 가정."""
        if not party.hazards:
            return
        self._warn("압정 수치는 게임 데이터에 없어 본편 값을 가정했습니다 "
                   "(스텔스록 1/8 x 바위 상성, 압정 1/8~1/4)")

        if party.hazards.get("스텔스록"):
            # 스텔스록만 떠 있어도 맞고, 바위 상성을 그대로 탄다
            eff = self.dex.effectiveness("바위", side.base.types)
            hurt = max(1, int(side.max_hp * eff / calc.CONFIG["rock_hazard"]))
            side.damage(hurt, direct=False)
            self._say("%s 가 스텔스록을 밟았다 — %d (상성 x%g, HP %d/%d)"
                      % (side.name, hurt, eff, side.hp, side.max_hp))
            self._pinch_berry(side)
        if not side.alive or not self._grounded(side):
            return

        n = party.hazards.get("압정뿌리기", 0)
        if n:
            frac = calc.CONFIG["spike_layers"][min(n, 3) - 1]
            hurt = max(1, side.max_hp // frac)
            side.damage(hurt, direct=False)
            self._say("%s 가 압정을 밟았다 — %d (%d겹, HP %d/%d)"
                      % (side.name, hurt, n, side.hp, side.max_hp))
            self._pinch_berry(side)
        if not side.alive:
            return

        n = party.hazards.get("독압정", 0)
        if n:
            if "독" in side.base.types:
                # 독타입이 나오면 독압정을 걷어 간다
                party.hazards.pop("독압정", None)
                self._say("%s 가 독압정을 걷어 갔다" % side.name)
            else:
                self._inflict(side, "맹독" if n >= 2 else "독")
        if party.hazards.get("끈적끈적네트"):
            if side.bump("speed", -1):
                self._say("%s 가 끈적끈적네트에 걸렸다 — 스피드-1" % side.name)

    def _entry_abilities(self, side):
        """나올 때 한 번 터지는 특성. 위협이 제일 흔하다 (보만다 99.3%)."""
        ab = ENTRY_ABILITY.get(side.base.ability)
        if not ab:
            return
        if ab["kind"] == "foe_rank":
            foe = self.opp if side is self.me else self.me
            if foe.base.ability in INTIMIDATE_PROOF or foe.blocks_drop():
                if foe.base.ability == MIRROR_ARMOR:
                    if side.bump(ab["stat"], ab["step"]):
                        self._say("%s 의 미러아머 — %s 의 위협을 되돌렸다"
                                  % (foe.name, side.name))
                else:
                    self._say("%s 의 %s — %s 에게는 안 통한다"
                              % (side.name, side.base.ability, foe.name))
                return
            if foe.bump(ab["stat"], ab["step"]):
                self._say("%s 의 %s — %s %s%+d"
                          % (side.name, side.base.ability, foe.name,
                             calc.STAT_KO[ab["stat"]], ab["step"]))
        elif ab["kind"] == "self_rank":
            if side.bump(ab["stat"], ab["step"]):
                self._say("%s 의 %s — 공격%+d" % (side.name, side.base.ability,
                                                 ab["step"]))

    def switch_in(self, party, idx, reason=""):
        """교체. 나가는 쪽의 랭크는 사라지고, 들어오는 쪽은 압정을 밟는다."""
        old = party.active
        if old.alive:
            # **랭크는 물러나면 사라진다.** 쌓아 둔 것을 지키려면 안 빠져야 한다.
            old.ranks = {k: 0 for k in old.ranks}
            old.substitute = 0
            old.enduring = False
            old.crit_stage = 0
            old.types_override = None
            old.destiny_turn = None
            old.confused = 0
            old.drowsy = 0
            old.protecting = False
        party.active_idx = idx
        side = party.active
        side.reset_entry()                       # 방금 나온 것을 이제 안다
        # 턴 중간에 들어온 놈은 이 턴에 고른 것이 없고 움직이지도 않는다.
        # (예전 턴의 기록이 남아 있으면 기습이 그걸 보고 틀린다)
        side.chosen, side.moved, side.hit_this_turn = None, True, False
        self._say("%s 로 교체%s" % (side.name, (" (%s)" % reason) if reason else ""))
        self._apply_hazards(party, side)
        if party.heal_wish and side.alive:
            party.heal_wish = False
            got = side.heal(side.max_hp)
            side.status = None
            side.status_turns = 0
            side.toxic_n = 0
            if got:
                self._say("%s — 치유소원으로 %d 회복하고 상태도 나았다"
                          % (side.name, got))
        if side.alive:
            self._entry_weather_for(side)
            self._entry_abilities(side)
            self._seed_item(side)

    def _entry_weather_for(self, side):
        w = WEATHER_ABILITY.get(side.base.ability)
        if w:
            self.field.set(w, turns=self._field_turns(side, w))
            self._say("%s(%s) — %s" % (side.name, side.base.ability, w))

    def _force_switch(self, party, by_name):
        """날려버리기·울부짖기·드래곤테일. 랭크를 통째로 날린다."""
        side = party.active
        if side.base.ability in PHAZE_PROOF:
            self._say("%s 의 %s 로 %s 를 버텼다"
                      % (side.name, side.base.ability, by_name))
            return False
        bench = party.bench()
        if not bench:
            self._say("%s — 바꿀 포켓몬이 없어 실패" % by_name)
            return False
        idx = self.rng.choice([i for i, _ in bench])
        self.switch_in(party, idx, "%s 에 밀려서" % by_name)
        return True

    def _entry_weather(self):
        """등장만으로 날씨를 까는 특성. 상위권에 99.8% 로 깔려 있다.

        둘 다 갖고 있으면 **느린 쪽이 나중에 발동해서 이긴다** (본편 규칙).
        빠른 순서대로 깔면 느린 쪽 것이 남는다.
        """
        order = sorted(
            ((self.me, "나"), (self.opp, "상대")),
            key=lambda x: -best.effective_speed(self.dex, x[0].as_build())[0])
        for side, who in order:
            w = WEATHER_ABILITY.get(side.base.ability)
            if w:
                self.field.set(w)
                self._say("%s(%s) 등장 — %s" % (side.name, side.base.ability, w))
        for side, who in order:
            self._entry_abilities(side)
        for side, who in order:
            self._seed_item(side)

    # -- 데미지 -------------------------------------------------------------
    def _field_turns(self, user, kind):
        """날씨·필드가 몇 턴 가나. 연장 도구가 있으면 3턴 늘어난다.

        축축한바위(비) · 뜨거운바위(쾌청) · 보송보송바위(모래) ·
        차가운바위(눈) · 그라운드코트(필드) — 전부 설명문에 '3턴 증가
        (총 8턴)' 라고 적혀 있다.
        """
        base = 5
        ef = item_effect(self.dex, user.item, "extend")
        if not ef:
            return base
        if ef["what"] == "terrain" and kind in TERRAIN:
            return base + ef["turns"]
        if ef["what"] == "weather" and ef.get("weather") == kind:
            return base + ef["turns"]
        return base

    def _power_scale(self, move, attacker):
        """날씨·필드가 위력에 주는 배율. 데이터에 적혀 있는 것만 본다."""
        mult = 1.0
        d = move.get("description") or ""
        if self.field.terrain == "그래스필드" and "그래스필드 상태일 때 위력이 1/2" in d:
            mult *= 0.5
        # 필드의 타입 강화·반감은 게임 데이터에 없다. 본편 값을 쓰고 경고를 띄운다.
        if TERRAIN_TYPE.get(self.field.terrain) == move["type"]:
            mult *= calc.CONFIG["terrain_boost"]
            self._warn("%s 의 %s 타입 강화 %.2f배는 게임 데이터에 없는 미확인 값입니다"
                       % (self.field.terrain, move["type"],
                          calc.CONFIG["terrain_boost"]))
        if TERRAIN_WEAKEN.get(self.field.terrain) == move["type"]:
            mult *= 0.5
            self._warn("%s 가 %s 를 반감시킨다고 본 것은 미확인 값입니다"
                       % (self.field.terrain, move["type"]))
        # 날씨도 게임 데이터에 숫자가 없다. 본편 값을 쓰고 경고를 띄운다.
        if WEATHER_BOOST.get(self.field.weather) == move["type"]:
            mult *= calc.CONFIG["weather_boost"]
            self._warn("%s 의 %s 타입 강화 %.2f배는 게임 데이터에 없는 "
                       "미확인 값입니다" % (self.field.weather, move["type"],
                                       calc.CONFIG["weather_boost"]))
        if WEATHER_WEAKEN.get(self.field.weather) == move["type"]:
            mult *= calc.CONFIG["weather_weaken"]
            self._warn("%s 가 %s 를 %.2f배로 깎는다고 본 것은 미확인 값입니다"
                       % (self.field.weather, move["type"],
                          calc.CONFIG["weather_weaken"]))
        return mult

    def move_blocked(self, user, target, move, foresee=False):
        """이 기술이 지금 실패하면 그 까닭을, 아니면 None. 설명문의 조건을 본다.

        foresee=True 는 **턴 전에 고를 때** (Policy) 다. 상대가 무엇을 골랐는지·
        이 턴에 맞았는지에 달린 것(기습·기선제압·힘껏펀치)은 그때 알 수 없으므로
        안 본다. 나머지는 턴 전에도 확실히 알 수 있다.
        """
        d = move.get("description") or ""
        # ! 막혀서 실패한 시도는 '쓴' 것이 아니다. 안 그러면 한 번 막힌 뒤로 영영
        #   못 쓴다 (실패한 시도도 last_move 에 남아서 — [49] 가 잡았다).
        if (_NO_REPEAT.search(d) and user.last_move is not None
                and user.last_move["name"] == move["name"] and not user.last_failed):
            return "실패 — 두 번 연달아 쓸 수 없다"
        if "실패" not in d:
            return None
        if _FIRST_ONLY.search(d) and user.acted:
            return "실패 — 나온 뒤 첫 기술이 아니다"
        if _LAST_RESORT.search(d):
            others = ([n for n in user.moveset if n != move["name"]]
                      if user.moveset else None)
            if others is None:
                # 기술 목록을 모른다 — 기술 4개로 보고 나머지 3개를 다 썼나 본다.
                used = [n for n in user.used_moves if n != move["name"]]
                if len(used) < 3:
                    return "실패 — 다른 기술을 다 안 썼다 (기술 목록을 몰라 4개로 봄)"
            elif not all(n in user.used_moves for n in others):
                return "실패 — 다른 기술을 다 안 썼다"
        if _BELCH.search(d) and not user.ate_berry:
            return "실패 — 이 배틀에서 나무열매를 안 먹었다"
        if _NEED_STOCKPILE.search(d) and not user.stockpile:
            return "실패 — 비축하기 상태가 아니다"
        if _NEED_TERRAIN.search(d) and not self.field.terrain:
            return "실패 — 필드가 없다"
        if not foresee:
            if _SUCKER.search(d) and (target.moved or target.chosen is None
                                      or target.chosen["category"] == "변화"):
                return ("실패 — 상대가 이미 움직였다" if target.moved else
                        "실패 — 상대가 공격 기술을 고르지 않았다")
            if _UPPER_HAND.search(d) and (
                    target.moved or target.chosen is None
                    or target.chosen.get("priority", 0) <= 0):
                return "실패 — 상대가 선제 공격 기술을 쓰지 않는다"
            if _FOCUS.search(d) and user.hit_this_turn:
                return "실패 — 이 턴에 먼저 맞았다"
        # 몸(Build)만 보고 되는 것 — 폴터가이스트·불사르기·전광쌍격·죽기살기
        return calc.move_fails(move, user.as_build(), target.as_build())

    def _crash(self, atk, move):
        """무릎차기처럼 빗나가거나 실패하면 자신이 다치는 기술."""
        atk.move_failed = True
        m = _CRASH.search(move.get("description") or "")
        if m and atk.alive:
            lost = max(1, atk.max_hp // int(m.group(1)))
            atk.damage(lost, direct=False)
            self._say("%s 는 기세가 넘쳐 스스로 다쳤다 — %d (HP %d/%d)"
                      % (atk.name, lost, atk.hp, atk.max_hp))
            self._pinch_berry(atk)

    def _hit(self, atk, dfn, move, who):
        """공격기 한 방. 실제로 들어간 데미지를 돌려준다."""
        if dfn.protecting:
            self._say("%s 의 %s — 막혔다" % (atk.name, move["name"]))
            self._crash(atk, move)
            return 0

        # 설명문의 실패 조건 — 명중 판정보다 먼저. calc_damage 도 몸으로 되는 것은
        # 보지만, 여기서 먼저 걸러야 로그가 '빗나감' 이 안 된다 (열 판에 한 판꼴로
        # 그랬다 — tests.py [47]).
        why = self.move_blocked(atk, dfn, move)
        if why:
            self._say("%s 의 %s — %s" % (atk.name, move["name"], why))
            self._crash(atk, move)
            return 0
        d_text = move.get("description") or ""
        if _NEED_STOCKPILE.search(d_text):
            # 토해내기 — 비축한 만큼 위력이 오른다 (설명문: 100~300)
            move = dict(move, power=100 * atk.stockpile)
        if atk.fresh_guessed and _FIRST_ONLY.search(d_text):
            self._warn("%s 가 이번 턴에 막 나왔는지 몰라서, 막 나온 것으로 보고 %s 를 "
                       "통하게 했습니다 (나온 첫 턴만 되는 기술)"
                       % (atk.name, move["name"]))

        if not self._accuracy_roll(atk, dfn, move, who):
            self._crash(atk, move)
            return 0

        # 기술마다 급소 확률이 다르다. '반드시 급소' 도 있다 (트릭플라워 등).
        stage = atk.crit_stage
        ef = item_effect(self.dex, atk.item, "crit_stage")
        if ef and (not ef.get("who") or atk.base.poke["name"] in ef["who"]):
            stage += ef["step"]
        crit = self.rng.random() < calc.crit_chance(move, stage)
        extra = self._power_scale(move, atk)
        m2 = _AFTER_FAIL.search(d_text)
        if m2 and atk.last_failed:
            extra *= int(m2.group(1))
            self._say("%s 의 %s — 직전에 실패해서 위력 %s배"
                      % (atk.name, move["name"], m2.group(1)))
        jw = item_effect(self.dex, atk.item, "jewel")
        if jw and not atk.item_used and move["type"] == jw["type"] \
                and move["category"] != "변화":
            extra *= jw["mult"]
            atk.item_used = True
            self._say("%s 의 %s — %s 기술 위력 %.1f배 (한 번뿐)"
                      % (atk.name, atk.item, jw["type"], jw["mult"]))
        fx = calc.attack_effects(move)
        first = (dict(move, power=fx["powers"][0]) if fx["powers"] else move)
        res = calc.calc_damage(self.dex, atk.as_build(), dfn.as_build(), first,
                               critical=crit, extra=extra)
        if "error" in res:
            self._say("%s 의 %s — %s" % (atk.name, move["name"], res["error"]))
            self._crash(atk, move)        # 고스트에게 무릎차기 — 안 통해도 다친다
            return 0

        # 연속기 — 한 방씩 따로 맞힌다. 기합의띠·옹골참은 **한 방만** 버티고,
        # 울퉁불퉁멧·까칠한피부는 **매 방** 반응한다. 합쳐서 한 번에 넣으면 둘 다 틀린다.
        # ! 전에는 스케일샷(한카리아스 17%)·록블라스트가 **한 번만** 때렸다.
        n_hits = self._hit_count(atk, move, fx)
        my_party, foe_party = self._party_of(atk), self._party_of(dfn)
        total, landed, connected = 0, 0, False
        for i in range(n_hits):
            if i > 0:
                # 레드카드·탈출버튼으로 누가 빠졌거나 쓰러졌으면 멈춘다
                if not (atk.alive and dfn.alive) or foe_party.active is not dfn \
                        or my_party.active is not atk:
                    break
                if (fx["stop_on_miss"]
                        and atk.base.ability not in skill_link_abilities(self.dex)
                        and not self._accuracy_roll(atk, dfn, move, who, quiet=True)):
                    self._say("%s 의 %s — %d번째가 빗나가 끝났다"
                              % (atk.name, move["name"], i + 1))
                    break
                crit = self.rng.random() < calc.crit_chance(move, stage)
                mv_i = (dict(move, power=fx["powers"][i])
                        if fx["powers"] and i < len(fx["powers"]) else move)
                res = calc.calc_damage(self.dex, atk.as_build(), dfn.as_build(),
                                       mv_i, critical=crit, extra=extra)
                if "error" in res:
                    break
            got, touched = self._land(atk, dfn, move, res, crit)
            total += got
            landed += 1
            connected = connected or touched
        if n_hits > 1:
            self._say("%s 의 %s — %d번 맞았다 (합계 %d)"
                      % (atk.name, move["name"], landed, total))
        dmg = total

        # 우격다짐 — 추가 효과가 없어지는 대신 1.3배 (calc 가 올렸다).
        # 본편처럼 **생명의구슬 반동도 없다** — 추가 효과가 있는 기술일 때만.
        sheer = calc.sheer_force_on(self.dex, atk.as_build(), move)

        # 반동
        rec = move_recoil(move)
        if rec and dmg:
            back = max(1, int(dmg * rec))
            atk.damage(back, direct=False)
            self._say("%s 반동 %d (HP %d/%d)" % (atk.name, back, atk.hp, atk.max_hp))
        # 생명의구슬
        # 죽기살기 같은 고정 데미지는 생명의구슬이 세게 하지도, 반동을 주지도 않는다
        if (dmg and atk.item == "생명의구슬" and not atk.item_used
                and not res.get("fixed") and not sheer):
            atk.damage(max(1, atk.max_hp // 10), direct=False)
            self._say("생명의구슬 반동 %d" % max(1, atk.max_hp // 10))

        # 데미지 계산기가 '이 특성은 못 넣었다' 고 한 것들을 올린다.
        # 다만 여기서 이미 다루는 것(탈·지구력·까칠한피부·열교환·옹골참)은 뺀다.
        handled = set(ON_HIT_ABILITY) | {DISGUISE, ENDURE_FULL}
        for w in res.get("warnings") or []:
            if any(("'%s'" % h) in w for h in handled):
                continue
            self._warn(w)

        # 기술에 붙은 특수 규칙은 경고로만.
        # 날씨·필드는 여기서 실제로 계산하므로 그 경고는 뺀다.
        for c in best.move_caveats(move):
            if "날씨·필드" in c or c.startswith(best.CONDITIONAL):
                continue          # 여기서 실제로 판정하는 것들이다
            if "위력이" in c and _NEED_STOCKPILE.search(d_text):
                continue          # 토해내기 — 비축한 만큼 위력을 위에서 실제로 넣었다
            if "회 연속" in c:
                continue          # 연속기 — 위에서 실제로 여러 번 때렸다
            self._warn("%s: %s" % (move["name"], c))

        self._secondaries(atk, dfn, move, fx, dmg, connected, sheer)
        self._pinch_berry(dfn)
        return dmg

    def _accuracy_roll(self, atk, dfn, move, who, quiet=False):
        """명중 판정. 맞으면 True. (연속기의 두 번째부터도 이걸 쓴다)"""
        acc = move.get("accuracy")
        if acc is None or acc > 100:
            return True
        hit_p = acc / 100.0
        for src, kind in ((atk, "accuracy"), (dfn, "evasion")):
            ef = item_effect(self.dex, src.item, kind)
            if ef:
                hit_p *= ef["mult"]
        ef = item_effect(self.dex, atk.item, "accuracy_slow")
        if ef and who == "후공":
            hit_p *= ef["mult"]
        if self.rng.random() > min(1.0, hit_p):
            if not quiet:
                self._say("%s 의 %s — 빗나감 (명중 %.0f%%)"
                          % (atk.name, move["name"], min(1.0, hit_p) * 100))
            return False
        return True

    def _hit_count(self, atk, move, fx):
        """이번에 몇 번 때리나. 설명문의 'N~M회 연속' 을 읽는다."""
        if not fx["hits"]:
            return 1
        lo, hi = fx["hits"]
        if lo == hi:
            return lo
        if atk.base.ability in skill_link_abilities(self.dex):
            return hi                     # 스킬링크 — "최고 횟수로 사용한다"
        if fx["stop_on_miss"]:
            return hi                     # 찍찍베기 — 매번 명중을 따로 굴려서 멈춘다
        if (lo, hi) == (2, 5):
            # 설명문엔 '2~5회' 까지만 있다. 횟수 확률은 사용자가 확인해 준 값
            # (37.5/37.5/12.5/12.5 — calc.CONFIG). 확인된 값이라 경고하지 않는다.
            r, acc = self.rng.random(), 0.0
            for n, p in zip(range(2, 6), calc.CONFIG["multi_hit_2to5"]):
                acc += p
                if r < acc:
                    return n
            return 5
        return self.rng.randint(lo, hi)

    def _land(self, atk, dfn, move, res, crit):
        """한 방. (몸에 들어간 데미지, 닿았나) — 대타·탈에 막혀도 '닿은' 것이다."""
        dmg = self.rng.choice(res["rolls"])
        # 스크린 — 급소에는 안 통한다 (본편 규칙). 죽기살기 같은 고정 데미지도 안 깎인다.
        if not crit and not res.get("fixed"):
            shield = self._party_of(dfn).screen_mult(move["category"])
            if shield < 1.0:
                dmg = max(1, int(dmg * shield))

        # 따라큐의 탈 — 데미지를 통째로 막고 최대 HP의 1/8 만 잃는다
        if dfn.disguise and dmg > 0:
            dfn.disguise = False
            lost = max(1, dfn.max_hp // 8)
            dfn.damage(lost, direct=False)
            self._say("%s 의 탈이 벗겨졌다 — 데미지 무효, %d 만 잃음 (HP %d/%d)"
                      % (dfn.name, lost, dfn.hp, dfn.max_hp))
            self._pinch_berry(dfn)
            return 0, True

        if dfn.substitute > 0:
            took = min(dfn.substitute, dmg)
            dfn.substitute -= took
            gone = dfn.substitute <= 0
            self._say("%s 의 %s → %s 의 대타에게 %d%s"
                      % (atk.name, move["name"], dfn.name, took,
                         " — 대타가 부서졌다" if gone else
                         " (대타 %d 남음)" % dfn.substitute))
            if gone:
                dfn.substitute = 0
            return 0, True

        note = dfn.damage(dmg)
        self._say("%s 의 %s → %s 에게 %d (HP %d/%d)%s%s"
                  % (atk.name, move["name"], dfn.name, dmg, dfn.hp, dfn.max_hp,
                     "  급소!" if crit else "",
                     "  · " + note if note else ""))
        if dmg:
            dfn.hit_this_turn = True           # 힘껏펀치가 본다

        # 맞은 쪽 특성이 반응한다
        ab = ON_HIT_ABILITY.get(dfn.base.ability)
        if ab and dmg and dfn.alive:
            if ab["kind"] == "rank" or (ab["kind"] == "rank_on_type"
                                        and res["moveType"] == ab["type"]):
                if dfn.bump(ab["stat"], ab["step"]):
                    self._say("%s 의 %s — %s %s%+d (지금 %s)"
                              % (dfn.name, dfn.base.ability,
                                 dfn.name, calc.STAT_KO[ab["stat"]],
                                 ab["step"], dfn.rank_text()))
            elif ab["kind"] == "hazard_on_hit" and move["category"] == "물리":
                foe_party = self._party_of(atk)
                if foe_party.add_hazard(ab["hazard"]):
                    self._say("%s 의 %s — %s 쪽에 %s (지금 %s)"
                              % (dfn.name, dfn.base.ability, atk.name,
                                 ab["hazard"], foe_party.hazard_text()))
            elif ab["kind"] == "contact_recoil" and move["isContact"]:
                back = max(1, int(atk.max_hp * ab["frac"]))
                atk.damage(back, direct=False)
                self._say("%s 의 %s — %s 가 %d (HP %d/%d)"
                          % (dfn.name, dfn.base.ability, atk.name, back,
                             atk.hp, atk.max_hp))

        # 길동무 — 이 기술로 쓰러졌다면 때린 쪽도 데려간다
        if (dmg and not dfn.alive and atk.alive
                and dfn.destiny_turn is not None
                and self.turn <= dfn.destiny_turn + 1):
            atk.hp = 0
            self._say("%s 의 길동무 — %s 도 같이 쓰러졌다"
                      % (dfn.name, atk.name))

        # 도구가 반응한다 (맞은 쪽)
        if dmg and dfn.alive:
            ef = item_effect(self.dex, dfn.item, "contact_chip")
            if ef and move["isContact"]:
                back = max(1, int(atk.max_hp * ef["frac"]))
                atk.damage(back, direct=False)
                self._say("%s 의 %s — %s 가 %d (HP %d/%d)"
                          % (dfn.name, dfn.item, atk.name, back,
                             atk.hp, atk.max_hp))
        if dmg and item_effect(self.dex, dfn.item, "float") \
                and not dfn.item_used:
            dfn.item_used = True
            self._say("%s 의 %s 이 터졌다 — 이제 땅에 닿는다"
                      % (dfn.name, dfn.item))
        # 때린 쪽 도구
        if dmg:
            ef = item_effect(self.dex, atk.item, "drain_hit")
            if ef and atk.alive:
                got = atk.heal(max(1, int(dmg * ef["frac"])))
                if got:
                    self._say("%s 의 %s — %d 회복" % (atk.name, atk.item, got))
            ef = item_effect(self.dex, atk.item, "flinch")
            if ef and dfn.alive and self.rng.random() < ef["chance"]:
                dfn.flinched = True
                self._say("%s 의 %s — %s 가 풀죽었다"
                          % (atk.name, atk.item, dfn.name))

        # 맞으면 누군가를 바꾸는 도구
        if dmg and dfn.alive and not dfn.item_used:
            if item_effect(self.dex, dfn.item, "force_switch_foe"):
                dfn.item_used = True
                self._say("%s 의 %s — %s 를 밀어낸다"
                          % (dfn.name, dfn.item, atk.name))
                self._force_switch(self._party_of(atk), dfn.item)
            elif item_effect(self.dex, dfn.item, "self_switch"):
                bench = self._party_of(dfn).bench()
                if bench:
                    dfn.item_used = True
                    self._say("%s 의 %s — 스스로 물러난다"
                              % (dfn.name, dfn.item))
                    self._force_switch(self._party_of(dfn), dfn.item)
        return dmg, True

    def _secondaries(self, atk, dfn, move, fx, dealt, connected, sheer):
        """공격기의 추가 효과·뒤처리 (calc.attack_effects 가 설명문에서 읽은 것).

        상대에게 거는 것은 **몸에 데미지가 들어갔을 때만** (대타에 막히면 안 걸린다),
        자기에게 거는 것(인파이트·용성군·니트로차지)은 닿기만 하면 된다.
        """
        if not connected:
            return
        shield = dfn.base.ability in shield_dust_abilities(self.dex)
        for g in fx["groups"]:
            if g["cond"]:
                self._warn("%s: '...한 경우' 에만 걸리는 추가 효과는 아직 계산에 "
                           "없습니다" % move["name"])
                continue
            if sheer and g["secondary"]:
                continue                  # 우격다짐 — 추가 효과가 없어진다
            on_foe = any(e.get("who") == "foe" or e["kind"] != "rank"
                         for e in g["effects"])
            if on_foe and (not dealt or not dfn.alive):
                continue
            if g["chance"] < 1.0 and self.rng.random() >= g["chance"]:
                continue
            if on_foe and shield and g["secondary"]:
                self._say("%s 의 %s — 추가 효과를 받지 않는다"
                          % (dfn.name, dfn.base.ability))
                continue
            for e in g["effects"]:
                k = e["kind"]
                if k == "rank":
                    side = atk if e["who"] == "self" else dfn
                    if not side.alive:
                        continue
                    if side is dfn and e["step"] < 0 and dfn.blocks_drop():
                        self._say("%s 의 %s — 능력이 안 깎인다"
                                  % (dfn.name, dfn.base.ability))
                        continue
                    moved = side.bump(e["stat"], e["step"])
                    if moved:
                        self._say("%s 의 %s — %s %s%+d (지금 %s)"
                                  % (atk.name, move["name"], side.name,
                                     calc.STAT_KO[e["stat"]], moved,
                                     side.rank_text()))
                elif k == "status":
                    opts = e["options"]
                    self._inflict(dfn, opts[0] if len(opts) == 1
                                  else self.rng.choice(opts))
                elif k == "flinch":
                    if dfn.moved:
                        continue          # 이미 움직였으면 풀죽어도 소용없다
                    if dfn.base.ability in flinch_proof_abilities(self.dex):
                        self._say("%s 의 %s — 풀죽지 않는다"
                                  % (dfn.name, dfn.base.ability))
                    else:
                        dfn.flinched = True
                        self._say("%s 는 풀죽었다" % dfn.name)
                else:
                    self._warn("%s 의 '%s' 효과는 아직 계산에 없습니다"
                               % (move["name"], e["name"]))
        # 흡수 — 큰뿌리를 들면 더 회복한다 (설명문 배율)
        if fx["drain"] and dealt and atk.alive:
            mult = 1.0
            ef = item_effect(self.dex, atk.item, "drain_boost")
            if ef:
                mult = ef["mult"]
            got = atk.heal(max(1, int(dealt * fx["drain"] * mult)))
            if got:
                self._say("%s 의 %s — %d 흡수 (HP %d/%d)%s"
                          % (atk.name, move["name"], got, atk.hp, atk.max_hp,
                             " · %s" % atk.item if ef else ""))
        # 열탕·열사의대지 — 맞은 쪽의 얼음을 녹인다
        if fx["thaw_foe"] and dealt and dfn.alive and dfn.status == "얼음":
            dfn.status = None
            self._say("%s 의 얼음이 녹았다" % dfn.name)
        # 탁쳐서떨구기 — 도구를 없앤다 (메가스톤은 못 떨어뜨린다)
        if (fx["knock_off"] and dealt and dfn.item and not dfn.item_used
                and dfn.item not in self.dex.mega_by_item):
            self._say("%s 의 %s — %s 의 %s 를 떨어뜨렸다"
                      % (atk.name, move["name"], dfn.name, dfn.item))
            dfn.item = None
        # 유턴·볼트체인지·퀵턴 — 때리고 나서 교체한다
        if fx["self_switch"] and atk.alive:
            party = self._party_of(atk)
            if party.bench():
                idx = self.choose_replacement(party)
                self.switch_in(party, idx, "%s 로" % move["name"])

    def _pinch_berry(self, side):
        """자뭉열매처럼 반피에서 터지는 열매. 상위권 1위 도구가 이거다."""
        if side.item_used or not side.item or not side.alive:
            return
        ef = item_effect(self.dex, side.item, "heal_pinch")
        if not ef or side.hp > side.max_hp * ef["at"]:
            return
        # 자뭉열매는 비율, 오랭열매는 고정값이다. 전에는 비율만 읽어서
        # 고정값 열매가 조용히 안 터졌다.
        amount = (side.max_hp * ef["frac"]) if "frac" in ef else ef["flat"]
        got = side.heal(amount)
        side.item_used = True
        self._say("%s 의 %s 발동 — %d 회복 (HP %d/%d)"
                  % (side.name, side.item, got, side.hp, side.max_hp))

    def _cure_berry(self, side):
        """리샘열매·유루열매처럼 상태를 풀어 주는 열매."""
        if side.item_used or not side.alive:
            return
        ef = item_effect(self.dex, side.item, "cure")
        if not ef:
            return
        want = ef["statuses"]
        hit = None
        if side.status and (want is None or side.status in want):
            hit = side.status
            side.status = None
            side.status_turns = 0
            side.toxic_n = 0
        elif side.confused and (want is None or "혼란" in want):
            hit = "혼란"
            side.confused = 0
        if hit:
            side.item_used = True
            self._say("%s 의 %s — %s 가 풀렸다" % (side.name, side.item, hit))

    # -- 변화기 -------------------------------------------------------------
    def _use_status(self, user, target, move):
        # 설명문의 실패 조건 (꿀꺽 — 비축하기 상태가 아니면 실패)
        why = self.move_blocked(user, target, move)
        if why:
            self._say("%s 의 %s — %s" % (user.name, move["name"], why))
            user.move_failed = True
            return
        d_text = move.get("description") or ""
        if _STOCKPILE.search(d_text) and user.stockpile >= 3:
            # "비축하기 상태는 최대 3회까지" — 넘치면 방어·특방도 안 오른다
            self._say("%s 의 %s — 더 비축할 수 없다 (3회)" % (user.name, move["name"]))
            user.move_failed = True
            return
        # 황금몸 — 상대가 쓰는 변화 기술이 아예 안 통한다
        if (target is not user and move["category"] == "변화"
                and target.base.ability in STATUS_MOVE_PROOF):
            self._say("%s 의 %s — %s 의 %s 로 막혔다"
                      % (user.name, move["name"], target.name,
                         target.base.ability))
            user.move_failed = True
            return
        if _STOCKPILE.search(d_text):
            user.stockpile += 1
            self._say("%s 의 %s — 비축 %d회" % (user.name, move["name"],
                                                user.stockpile))

        for ef in move_effects(move):
            k = ef["kind"]
            if k == "rank":
                side = user if ef["who"] == "self" else target
                if side is target and target.protecting:
                    continue
                # 남이 내 능력을 깎으려 할 때만 막힌다 (내가 스스로 깎는 건 통과)
                if side is target and ef["step"] < 0 and target.blocks_drop():
                    if target.base.ability == MIRROR_ARMOR:
                        if user.bump(ef["stat"], ef["step"]):
                            self._say("%s 의 미러아머 — %s 에게 %s%+d 로 되돌렸다"
                                      % (target.name, user.name,
                                         calc.STAT_KO[ef["stat"]], ef["step"]))
                    else:
                        self._say("%s 의 %s — 능력이 안 깎인다"
                                  % (target.name, target.base.ability))
                    continue
                moved = side.bump(ef["stat"], ef["step"])
                if moved:
                    self._say("%s 의 %s — %s %s%+d (지금 %s)"
                              % (user.name, move["name"], side.name,
                                 calc.STAT_KO[ef["stat"]], moved,
                                 side.rank_text()))
                else:
                    self._say("%s 의 %s — %s 는 더 이상 안 변한다"
                              % (user.name, move["name"],
                                 calc.STAT_KO[ef["stat"]]))
            elif k == "heal":
                if user.hp >= user.max_hp:
                    self._say("%s 의 %s — HP가 꽉 차서 실패" % (user.name, move["name"]))
                    user.move_failed = True
                    continue
                got = user.heal(user.max_hp * ef["frac"])
                if ef.get("cure"):
                    user.status = None
                self._say("%s 의 %s — %d 회복 (HP %d/%d)"
                          % (user.name, move["name"], got, user.hp, user.max_hp))
            elif k == "self_status":
                # 잠자기 — 스스로 잠든다. 면역 판정을 거치지 않는다.
                user.status = ef["status"]
                # 게임 설명문이 '2턴 동안' 이라고 못박고 있다 (본편은 3턴).
                user.status_turns = 2
                self._say("%s 는 %s 상태가 됐다 (2턴)" % (user.name, ef["status"]))
            elif k == "status":
                if target.protecting:
                    continue
                self._inflict(target, ef["status"], move)
            elif k == "protect":
                user.protecting = True
                self._say("%s 의 %s — 이 턴은 막는다" % (user.name, move["name"]))
            elif k == "destiny":
                user.destiny_turn = self.turn
                self._say("%s 의 %s — 쓰러지면 같이 데려간다"
                          % (user.name, move["name"]))
            elif k == "crit_up":
                user.crit_stage += ef["step"]
                self._say("%s 의 %s — 급소업+%d (지금 +%d)"
                          % (user.name, move["name"], ef["step"],
                             user.crit_stage))
            elif k == "retype":
                target.types_override = [ef["type"]]
                self._say("%s 의 %s — %s 가 %s타입이 됐다"
                          % (user.name, move["name"], target.name,
                             ef["type"]))
            elif k == "belly":
                cost = max(1, int(user.max_hp * ef["cost"]))
                if user.hp <= cost:
                    self._say("%s 의 %s — HP가 모자라 실패" % (user.name, move["name"]))
                    user.move_failed = True
                else:
                    user.damage(cost, direct=False)
                    user.ranks["attack"] = ef["step"]
                    self._say("%s 의 %s — HP %d 를 쓰고 공격 +%d (HP %d/%d)"
                              % (user.name, move["name"], cost, ef["step"],
                                 user.hp, user.max_hp))
            elif k == "perish":
                for side in (self.me, self.opp):
                    if not side.perish:
                        side.perish = ef["turns"]
                self._say("%s 의 %s — 양쪽 모두 %d턴 뒤에 쓰러진다"
                          % (user.name, move["name"], ef["turns"]))
            elif k == "defog":
                party = self._party_of(target)
                mine = self._party_of(user)
                cleared = []
                for p in (party, mine):
                    if p.hazards:
                        cleared.append("%s 쪽 압정" % ("상대" if p is party else "내"))
                        p.hazards = {}
                    if p.screens:
                        cleared.append("%s 쪽 스크린" % ("상대" if p is party else "내"))
                        p.screens = {}
                if self.field.terrain:
                    cleared.append(self.field.terrain)
                    self.field.terrain, self.field.terrain_turns = None, 0
                if target.bump("evasion", -1) if "evasion" in target.ranks else 0:
                    pass
                self._say("%s 의 %s — %s 해제"
                          % (user.name, move["name"],
                             ", ".join(cleared) if cleared else "해제할 것 없음"))
            elif k == "trick":
                a, b = user.item, target.item
                if user.item_used or target.item_used:
                    self._say("%s 의 %s — 실패 (이미 쓴 도구)" % (user.name, move["name"]))
                    user.move_failed = True
                else:
                    user.item, target.item = b, a
                    self._say("%s 의 %s — 도구를 바꿨다 (%s <-> %s)"
                              % (user.name, move["name"], a or "없음", b or "없음"))
            elif k == "revive":
                party = self._party_of(user)
                dead = [i for i, m in enumerate(party.members) if not m.alive]
                if not dead:
                    self._say("%s 의 %s — 쓰러진 포켓몬이 없어 실패"
                              % (user.name, move["name"]))
                    user.move_failed = True
                else:
                    user.hp = 0
                    back = party.members[dead[0]]
                    back.hp = max(1, int(back.max_hp * ef["frac"]))
                    back.status = None
                    self._say("%s 의 %s — 자신은 쓰러지고 %s 가 HP %d 로 돌아왔다"
                              % (user.name, move["name"], back.name, back.hp))
            elif k == "heal_wish":
                party = self._party_of(user)
                user.hp = 0
                party.heal_wish = True
                self._say("%s 의 %s — 자신은 쓰러지고 다음에 나오는 놈이 다 낫는다"
                          % (user.name, move["name"]))
            elif k == "baton":
                party = self._party_of(user)
                bench = party.bench()
                if not bench:
                    self._say("%s 의 %s — 바꿀 포켓몬이 없어 실패"
                              % (user.name, move["name"]))
                    user.move_failed = True
                else:
                    keep = dict(user.ranks)
                    sub = user.substitute
                    idx = max(bench, key=lambda t: self.replacement_score(
                        party, t[1], target))[0]
                    self.switch_in(party, idx, "%s 로" % move["name"])
                    # **배턴터치의 요점은 랭크를 넘기는 것이다.**
                    # switch_in 이 랭크를 지우므로 그 뒤에 다시 얹는다.
                    party.active.ranks = keep
                    party.active.substitute = sub
                    self._say("%s — 능력 변화를 이어받았다 (지금 %s)"
                              % (party.active.name, party.active.rank_text()))
            elif k == "substitute":
                cost = max(1, int(user.max_hp * ef["frac"]))
                if user.substitute:
                    self._say("%s 의 %s — 이미 대타가 있다" % (user.name, move["name"]))
                    user.move_failed = True
                elif user.hp <= cost:
                    self._say("%s 의 %s — HP가 모자라 실패" % (user.name, move["name"]))
                    user.move_failed = True
                else:
                    user.damage(cost, direct=False)
                    user.substitute = cost
                    self._say("%s 의 %s — 대타 %d (HP %d/%d)"
                              % (user.name, move["name"], cost,
                                 user.hp, user.max_hp))
            elif k == "wish":
                if user.wish:
                    self._say("%s 의 %s — 이미 걸려 있다" % (user.name, move["name"]))
                    user.move_failed = True
                else:
                    # 희망사항은 **다음 턴 끝에** 자리로 회복이 온다.
                    # 그래서 빠지고 나서 들어온 놈이 받는다 — 그게 이 기술의 핵심이다.
                    user.wish = max(1, int(user.max_hp * ef["frac"]))
                    self._party_of(user).wish = (2, user.wish)
                    self._say("%s 의 %s — 다음 턴에 %d 회복이 온다"
                              % (user.name, move["name"], user.wish))
            elif k == "pain_split":
                total = user.hp + target.hp
                half = total // 2
                user.hp = min(user.max_hp, half)
                target.hp = min(target.max_hp, total - half)
                self._say("%s 의 %s — %d/%d 와 %d/%d 로 나눴다"
                          % (user.name, move["name"], user.hp, user.max_hp,
                             target.hp, target.max_hp))
            elif k == "haze":
                for side in (self.me, self.opp):
                    side.ranks = {kk: 0 for kk in side.ranks}
                self._say("%s 의 %s — 양쪽 능력 변화가 전부 사라졌다"
                          % (user.name, move["name"]))
            elif k == "endure_turn":
                user.enduring = True
                self._say("%s 의 %s — 이 턴은 버틴다" % (user.name, move["name"]))
            elif k == "screen":
                party = self._party_of(user)
                turns = ef["turns"]
                ext = item_effect(self.dex, user.item, "extend")
                if ext and ext["what"] == "screen":
                    turns += ext["turns"]
                party.screens[ef["name"]] = turns
                self._say("%s 의 %s — %d턴 (지금 %s)"
                          % (user.name, move["name"], turns,
                             party.screen_text()))
                self._warn("스크린이 데미지를 %.0f%% 깎는다고 본 것은 게임 "
                           "데이터에 없는 미확인 값입니다"
                           % ((1 - calc.CONFIG["screen_reduce"]) * 100))
            elif k == "weather":
                self.field.set(ef["weather"], turns=self._field_turns(
                    user, ef["weather"]))
                self._say("%s 의 %s — %s" % (user.name, move["name"], ef["weather"]))
            elif k == "phaze":
                if target.protecting:
                    continue
                self._force_switch(self._party_of(target), move["name"])
            elif k == "hazard":
                foe_party = self._party_of(target)
                if foe_party.add_hazard(ef["hazard"]):
                    self._say("%s 의 %s — 상대 쪽에 깔았다 (지금 %s)"
                              % (user.name, move["name"],
                                 foe_party.hazard_text()))
                    if len(foe_party.members) == 1:
                        self._warn("'%s' 는 상대가 교체할 때 값어치가 납니다. "
                                   "지금은 1대1 이라 효과가 없습니다."
                                   % move["name"])
                else:
                    self._say("%s 의 %s — 더 못 쌓는다" % (user.name, move["name"]))
                    user.move_failed = True
            else:
                self._say("%s 의 %s — 효과를 아직 모른다" % (user.name, move["name"]))
                self._warn("'%s' 의 효과를 설명문에서 못 읽었습니다" % move["name"])

    # -- 상태 이상 ----------------------------------------------------------
    def _inflict(self, side, status, move=None):
        """상태 이상을 건다. 막히면 왜 막혔는지 로그에 남긴다."""
        # 1) 기술 설명문에 적힌 타입 면역 (전기자석파 -> 땅, 수면가루 -> 풀)
        if move is not None:
            for t in move_type_immunity(move):
                if t in side.base.types:
                    self._say("%s 는 %s타입이라 %s 가 안 통한다"
                              % (side.name, t, move["name"]))
                    return False
        # 2) 특성 면역 — 설명문에 적혀 있다
        if status in self._immune_abilities.get(side.base.ability, ()):
            self._say("%s 의 특성 '%s' 로 %s 를 막았다"
                      % (side.name, side.base.ability, status))
            return False
        # 3) 타입 면역 — 게임 데이터에 없어서 본편 규칙을 가정한 부분
        for t in calc.STATUS_TYPE_IMMUNE.get(status, ()):
            if t in side.base.types:
                self._say("%s 는 %s타입이라 %s 에 안 걸린다" % (side.name, t, status))
                self._warn("'%s타입은 %s 에 안 걸린다' 는 게임 데이터에 없는 "
                           "본편 규칙 가정입니다" % (t, status))
                return False

        if status == "혼란":
            if side.confused:
                self._say("%s 는 이미 혼란" % side.name)
                return False
            side.confused = self.rng.randint(calc.CONFIG["confuse_min"],
                                             calc.CONFIG["confuse_max"])
            self._say("%s 는 혼란에 빠졌다 (%d턴)" % (side.name, side.confused))
            return True
        if status == "졸음":
            if side.status or side.drowsy:
                self._say("%s 에게는 안 통했다" % side.name)
                return False
            side.drowsy = 2          # 이번 턴 끝 + 다음 턴 끝 -> 잠든다
            self._say("%s 는 졸음 상태 (다음 턴에 잠든다)" % side.name)
            return True

        if side.status:
            self._say("%s 는 이미 %s 상태" % (side.name, side.status))
            return False
        side.status = status
        if status == "잠듦":
            side.status_turns = self.rng.randint(calc.CONFIG["sleep_min"],
                                                 calc.CONFIG["sleep_max"])
            self._say("%s 는 잠들었다 (%d턴)" % (side.name, side.status_turns))
        elif status == "맹독":
            side.toxic_n = 1
            self._say("%s 는 맹독 상태가 됐다" % side.name)
        else:
            self._say("%s 를 %s 상태로" % (side.name, status))
        if status not in STATUS_DONE:
            self._warn("'%s' 상태의 효과는 아직 계산에 없습니다 (이름만 붙습니다)"
                       % status)
        return True

    def _can_move(self, side, move=None):
        """행동할 수 있는가. 잠듦·얼음·마비·혼란을 여기서 본다."""
        if side.status == "잠듦":
            if side.status_turns > 0:
                side.status_turns -= 1
                self._say("%s 는 자고 있다 (남은 %d턴)" % (side.name, side.status_turns))
                return False
            side.status = None
            self._say("%s 가 깨어났다" % side.name)
        elif side.status == "얼음":
            if move and _THAW_SELF.search(move.get("description") or ""):
                # 플레어드라이브·열탕·불사르기 등 — "사용하면 자신의 얼음 상태를 회복한다"
                side.status = None
                self._say("%s 의 %s — 얼음이 녹았다" % (side.name, move["name"]))
            elif self.rng.random() >= calc.CONFIG["freeze_thaw"]:
                self._say("%s 는 얼어붙어 움직이지 못했다" % side.name)
                return False
            else:
                side.status = None
                self._say("%s 의 얼음이 풀렸다" % side.name)

        if (side.status == "마비"
                and self.rng.random() < calc.CONFIG["paralysis_skip"]):
            self._say("%s 는 몸이 저려 움직이지 못했다" % side.name)
            return False

        if side.confused:
            side.confused -= 1
            if self.rng.random() < calc.CONFIG["confuse_self"]:
                self._confusion_hit(side)
                return False
            self._say("%s 는 혼란스럽다 (남은 %d턴)" % (side.name, side.confused))
        return True

    def _confusion_hit(self, side):
        """혼란 자해. 무속성 물리라 상성·자속을 타지 않는다."""
        b = side.as_build()
        a, d_ = b.stat("attack"), b.stat("defense")
        lvl = calc.CONFIG["level"]
        base = (int(int(int(2 * lvl / 5 + 2) * calc.CONFIG["confuse_power"]
                        * a / d_) / 50) + 2)
        roll = self.rng.randint(calc.CONFIG["random_min"],
                                calc.CONFIG["random_max"])
        dmg = max(1, int(base * roll / 100))
        side.damage(dmg, direct=False)
        self._say("%s 는 혼란해서 자신을 공격했다 — %d (HP %d/%d)"
                  % (side.name, dmg, side.hp, side.max_hp))
        self._pinch_berry(side)

    # -- 한 턴 --------------------------------------------------------------
    def _act(self, actor, target, move):
        if not actor.alive:
            return
        actor.move_failed = False
        if not self._can_move(actor, move):
            actor.last_failed = True          # '행동하지 못했다' 도 실패로 친다 (설명문)
            return
        if move["category"] == "변화":
            self._use_status(actor, target, move)
        else:
            self._hit(actor, target, move, None)
            # 자폭·대폭발·미스트버스트 — 막히거나 빗나가도 쓴 쪽은 쓰러진다 (본편 규칙)
            if calc.attack_effects(move)["self_faint"] and actor.alive:
                actor.hp = 0
                self._say("%s 는 %s 로 쓰러졌다" % (actor.name, move["name"]))
        # 나온 뒤의 기록 — **쓰고 난 뒤에** 남긴다. 먼저 남기면 속이기가 자기 자신
        # 때문에 '첫 기술이 아니다' 로 실패한다.
        actor.acted = True
        actor.fresh_guessed = False
        actor.used_moves.add(move["name"])
        actor.last_move = move
        if not actor.move_failed:
            self._after_use(actor, move)
        actor.last_failed = actor.move_failed

    def _after_use(self, user, move):
        """기술이 제대로 나갔을 때만 일어나는 뒤처리 (설명문에 적힌 것)."""
        d = move.get("description") or ""
        m = _LOSE_TYPE.search(d)
        if m and m.group(1) in user.types:
            # 불사르기·전광쌍격. 순수 불꽃이면 타입이 **없어진다** ([] — None 과 다르다)
            user.types_override = [t for t in user.types if t != m.group(1)]
            self._say("%s 의 %s타입이 없어졌다 (지금 %s)"
                      % (user.name, m.group(1),
                         "/".join(user.types_override) or "타입 없음"))
        if _CLEAR_TERRAIN.search(d) and self.field.terrain:
            self._say("%s 의 %s — %s 가 사라졌다"
                      % (user.name, move["name"], self.field.terrain))
            self.field.terrain, self.field.terrain_turns = None, 0
        if _NEED_STOCKPILE.search(d) and user.stockpile:
            # 토해내기·꿀꺽 — 비축을 다 쓰고, 비축하며 올린 방어·특방도 돌려놓는다
            n, user.stockpile = user.stockpile, 0
            user.bump("defense", -n)
            user.bump("spDef", -n)
            self._say("%s 의 비축이 풀렸다 (방어·특방 -%d, 지금 %s)"
                      % (user.name, n, user.rank_text()))

    def step(self, my_action, opp_action):
        """한 턴 진행.

        수는 셋 중 하나다.
          · 기술 (moves.json 의 항목)
          · ("교체", 번호)
          · ("메가", 기술)   메가진화하고 그 기술을 쓴다
        교체는 기술보다 먼저 처리된다.

        ! **메가는 순서를 정하기 전에 처리한다.** 메가하면 스피드가
          바뀌는데, 순서를 먼저 정해 버리면 기본 폼 스피드로 겨루게 된다.
          실제 게임도 메가가 먼저 일어나고 그 다음에 선공을 가린다.
          조용히 틀어지는 자리라 여기 적어 둔다.
        """
        self.turn += 1
        self.me.protecting = False
        self.opp.protecting = False

        # 0) 메가진화 — 순서를 가리기 **전에**
        unwrapped = []
        for action, party, who in ((my_action, self.me_party, "나"),
                                   (opp_action, self.opp_party, "상대")):
            if isinstance(action, tuple) and action[0] == "메가":
                before = party.active.name
                if party.do_mega():
                    self._say("%s %s 가 메가진화했다 — %s"
                              % (who, before, party.active.name))
                else:
                    # 이미 썼거나 스톤이 없다. 기술만 쓴다.
                    self._say("%s %s 는 메가진화할 수 없다 (한 게임에 한 번)"
                              % (who, before))
                unwrapped.append(action[1])
            else:
                unwrapped.append(action)
        my_action, opp_action = unwrapped

        # 1) 교체가 먼저다
        pending = []
        for action, party, who in ((my_action, self.me_party, "나"),
                                   (opp_action, self.opp_party, "상대")):
            if isinstance(action, tuple) and action[0] == "교체":
                foe = self.opp if party is self.me_party else self.me
                if foe.base.ability in TRAP_ABILITY:
                    self._say("%s 의 %s 때문에 못 빠진다"
                              % (foe.name, foe.base.ability))
                    pending.append((party, None))
                    continue
                self.switch_in(party, action[1])
                pending.append((party, None))
            else:
                pending.append((party, action))

        my_move = pending[0][1]
        opp_move = pending[1][1]
        # 이 턴의 기록 — 교체가 끝난 뒤 **지금 나와 있는 놈** 에게 단다.
        # 기습은 '상대가 공격기를 골랐고 아직 안 움직였나' 를 본다.
        for side, mv in ((self.me, my_move), (self.opp, opp_move)):
            side.chosen = mv
            side.moved = False
            side.hit_this_turn = False
        if my_move is None and opp_move is None:
            self._end_of_turn()
            self._replace_fainted()
            return

        # 2) 남은 기술을 순서대로
        probe = my_move or best.NEUTRAL_MOVE
        probe2 = opp_move or best.NEUTRAL_MOVE
        order = best.turn_order(self.dex, self.me.as_build(), probe,
                                self.opp.as_build(), probe2)
        first = order["first"]
        if first == "동시":
            first = "나" if self.rng.random() < 0.5 else "상대"
        seq = [(self.me, self.opp, my_move), (self.opp, self.me, opp_move)]
        if first == "상대":
            seq.reverse()

        for actor, target, move in seq:
            if move is None:
                continue          # 이 턴에 교체한 쪽이다
            if not (self.me.alive and self.opp.alive):
                break
            if actor.flinched:
                self._say("%s 는 풀죽어서 움직이지 못했다" % actor.name)
                actor.last_failed = True      # 행동하지 못했다 (분함의발구르기가 본다)
                actor.moved = True
                continue
            self._act(actor, target, move)
            actor.moved = True

        if self.me.alive and self.opp.alive:
            self._end_of_turn()
        self._replace_fainted()
        self._emergency_exit()

    def replacement_score(self, party, side, foe, taking_hit=False):
        """이놈을 지금 내보내면 이 상대에게 무엇을 할 수 있는가.

        **'HP 비율이 제일 높은 놈' 은 틀린 기준이다.** 필요한 HP 는 상대마다 다르다.
        물어야 할 것은 "이 상대를 상대하려면 몇 대를 버텨야 하고,
        지금 HP 로 그게 되는가" 다.

          · 따라큐는 탈이 살아 있으면 한 대를 통째로 막고, 야습(우선도 +1, 95.3%)
            으로 스피드와 상관없이 때린다. HP 가 적어도 확실히 두 대는 넣는다.
          · 느리고 한 방에 죽는 놈은 HP 가 꽉 차 있어도 한 대도 못 넣는다.

        그래서 양쪽 타수를 재고, 선공 여부와 묶어 **죽기 전에 몇 대나 넣는지**를 센다.
        best.race 와 같은 셈법이다.
        """
        # 1) 나오면서 압정을 밟는다. 밟고 죽으면 최악.
        hp = side.hp
        if party.hazards.get("스텔스록"):
            eff = self.dex.effectiveness("바위", side.base.types)
            hp -= max(1, int(side.max_hp * eff / calc.CONFIG["rock_hazard"]))
        if hp <= 0:
            return -1.0

        me_build = side.as_build()
        foe_build = foe.as_build()

        # taking_hit — 스스로 빼서 들어오는 경우다. 그 턴에 한 대를 그냥 맞는다.
        # 쓰러진 자리로 나오는 것(공짜)과 값이 다르므로 여기서 갈라 준다.
        if taking_hit:
            entry_rows = best.rate_moves(
                self.dex, foe_build, me_build,
                realistic_moveset(self.dex, foe.base.poke))
            entry = best.best_threat(entry_rows)
            if entry:
                if side.disguise:
                    hp -= max(1, side.max_hp // 8)      # 탈이 대신 맞는다
                else:
                    hp -= int(entry["expected"])
            if hp <= 0:
                return -1.0

        # 2) 내가 이 상대를 잡는 데 몇 대가 드는가
        my_rows = best.rate_moves(
            self.dex, me_build, foe_build,
            best.candidate_moves(self.dex, side.base.poke))
        mine = best.best_threat(my_rows)
        if mine is None:
            return 0.0                      # 때릴 수단이 없다
        my_move = mine["move"]
        per_hit = mine["expected"] / float(foe.hp or 1)
        my_hits = max(1, int(math.ceil(1.0 / per_hit))) if per_hit > 0 else best.NEVER

        # 3) 상대가 나를 잡는 데 몇 대가 드는가 — **지금 내 HP 기준**이다
        foe_rows = best.rate_moves(
            self.dex, foe_build, me_build,
            realistic_moveset(self.dex, foe.base.poke))
        threat = best.best_threat(foe_rows)
        if threat is None:
            foe_hits = best.NEVER
            first = "나"
        else:
            hurt = threat["expected"]
            foe_hits = (max(1, int(math.ceil(hp / hurt))) if hurt > 0 else best.NEVER)
            # 탈·옹골참·기합의띠는 한 대를 통째로 벌어 준다
            if side.disguise:
                foe_hits += 1
            elif (hp == side.max_hp
                    and (side.base.ability == ENDURE_FULL
                         or (side.item == "기합의띠" and not side.item_used))):
                foe_hits += 1
            order = best.turn_order(self.dex, me_build, my_move,
                                    foe_build, threat["move"])
            first = order["first"]

        # 4) 이 대면을 이기는가. best.race 와 같은 판정이다.
        #    선공이면 같은 타수라도 이기고, 후공이면 한 대 더 빨라야 한다.
        wins = best._i_win(my_hits, foe_hits, first == "나")
        if first == "동시":
            wins = best._i_win(my_hits, foe_hits, True) and \
                best._i_win(my_hits, foe_hits, False)

        # 죽기 전에 몇 대나 넣는가 (못 이길 때 얼마나 깎아 놓는지)
        if first == "나":
            chances = foe_hits
        elif first == "동시":
            chances = foe_hits - 0.5
        else:
            chances = foe_hits - 1
        chances = max(0.0, min(chances, my_hits))
        dealt = min(1.0, chances * per_hit)

        # **이기는 것과 비기는 것을 확실히 갈라야 한다.**
        # 전에는 '깎은 양' 과 '잡았음' 을 그냥 더해서, 사이좋게 비기는 놈이
        # 확실히 이기는 놈과 같은 점수가 나왔다. 그러면 카운터를 안 꺼낸다.
        if wins:
            left = max(0.0, 1.0 - (my_hits - 1) / float(max(1, foe_hits)))
            return 1.0 + 0.5 * left        # 1.0 ~ 1.5 — 여유가 많을수록 높다
        return 0.6 * dealt                 # 0 ~ 0.6 — 못 이기면 무조건 아래

    def should_switch(self, party):
        """지금 빼는 게 나은가. 나으면 바꿀 번호를, 아니면 None.

        **되도록 추측하지 않고 실제로 잰 1대1 승률을 쓴다.**
        한 번의 교환만 보는 어림셈으로는 카운터를 못 알아본다 —
        '한 대 맞고 들어가면 손해' 로만 보여서, 확실히 이기는 놈도 안 꺼내게 된다.

        표가 없으면 어림셈(replacement_score)으로 돌아간다.
        """
        bench = party.bench()
        if not bench:
            return None
        foe = self.opp if party is self.me_party else self.me
        if not foe.alive or not party.active.alive:
            return None

        if self.matchup is not None:
            stay = self.matchup.get((party.active.name, foe.name))
            if stay is not None:
                best_idx, best_val = None, stay + SWITCH_MARGIN
                for i, side in bench:
                    v = self.matchup.get((side.name, foe.name))
                    if v is None:
                        continue
                    # 들어오면서 한 대 맞고, 압정도 밟는다. 그만큼 깎아 본다.
                    v *= (1.0 - SWITCH_COST)
                    if party.hazards:
                        v *= (1.0 - HAZARD_COST)
                    if v > best_val:
                        best_idx, best_val = i, v
                return best_idx

        stay = self.replacement_score(party, party.active, foe)
        best_idx, best_val = None, stay + SWITCH_MARGIN
        for i, side in bench:
            v = self.replacement_score(party, side, foe, taking_hit=True)
            if v > best_val:
                best_idx, best_val = i, v
        return best_idx

    def choose_replacement(self, party, explain=False):
        """쓰러진 자리에 누구를 낼지 고른다.

        explain 을 켜면 왜 그렇게 골랐는지 같이 돌려준다.
        (이 프로젝트는 판단 근거를 남긴다 — 나중에 지고 나서 되짚어야 하므로.)
        """
        bench = party.bench()
        if not bench:
            return (None, []) if explain else None
        foe = self.opp if party is self.me_party else self.me
        if not foe.alive:
            idx = max(bench, key=lambda x: x[1].hp_ratio)[0]
            return (idx, []) if explain else idx
        scored = [(self.replacement_score(party, side, foe), -i, i, side)
                  for i, side in bench]
        best_one = max(scored)
        if explain:
            rows = sorted(((sc, sd) for sc, _, _, sd in scored),
                          key=lambda x: -x[0])
            return best_one[2], rows
        return best_one[2]

    def _replace_fainted(self):
        """쓰러진 자리에 다음 놈을 내보낸다. 나오면서 압정을 밟는다."""
        for party in (self.me_party, self.opp_party):
            if party.active.alive or not party.alive:
                continue
            idx, rows = self.choose_replacement(party, explain=True)
            if idx is None:
                continue
            if rows and self.log is not None:
                self._say("누구를 낼까 — " + " / ".join(
                    "%s(HP %d%%) %.2f" % (sd.name, sd.hp_ratio * 100, sc)
                    for sc, sd in rows))
            self.switch_in(party, idx, "쓰러진 자리")

    @property
    def over(self):
        return not (self.me_party.alive and self.opp_party.alive)

    def _emergency_exit(self):
        """위기회피·허둥지둥 — HP 가 반 이하로 떨어지면 스스로 물러난다.

        이게 없으면 반피까지 깎아 놓고 그대로 잡을 수 있다고 계산하게 된다.
        """
        for party in (self.me_party, self.opp_party):
            side = party.active
            if (side.base.ability not in EMERGENCY_EXIT or not side.alive
                    or side.hp > side.max_hp // 2):
                continue
            if not party.bench():
                continue
            idx = self.choose_replacement(party)
            if idx is None:
                continue
            self._say("%s 의 %s — HP 가 반 이하라 물러난다"
                      % (side.name, side.base.ability))
            self.switch_in(party, idx, "위기회피")

    def _end_of_turn(self):
        """턴 끝 — 상태이상 · 날씨 칩댐 · 먹다남은음식."""
        for side in (self.me, self.opp):
            if not side.alive:
                continue
            if side.status == "화상":
                side.damage(max(1, side.max_hp // calc.CONFIG["burn_chip"]),
                            direct=False)
                self._say("%s 화상 데미지 (HP %d/%d)" % (side.name, side.hp, side.max_hp))
            elif side.status == "독":
                side.damage(max(1, side.max_hp // calc.CONFIG["poison_chip"]),
                            direct=False)
                self._say("%s 독 데미지 (HP %d/%d)" % (side.name, side.hp, side.max_hp))
            elif side.status == "맹독":
                # 맹독은 턴마다 세진다 — 1/16, 2/16, 3/16 ...
                hurt = max(1, side.max_hp * side.toxic_n
                           // calc.CONFIG["toxic_chip"])
                side.damage(hurt, direct=False)
                self._say("%s 맹독 데미지 %d (%d턴째, HP %d/%d)"
                          % (side.name, hurt, side.toxic_n, side.hp, side.max_hp))
                side.toxic_n += 1

            # 하품 -> 졸음 -> 다음 턴 끝에 잠든다
            if side.drowsy:
                side.drowsy -= 1
                if side.drowsy == 0 and side.alive:
                    self._inflict(side, "잠듦")

            if (self.field.weather == "모래바람"
                    and not (set(side.base.types) & SAND_IMMUNE)):
                side.damage(max(1, side.max_hp // calc.CONFIG["sand_chip"]))
                self._say("%s 모래바람 데미지 (HP %d/%d)"
                          % (side.name, side.hp, side.max_hp))
                self._warn("모래바람 칩 데미지 1/%d 은 미확인 값입니다"
                           % calc.CONFIG["sand_chip"])

            if side.item == "먹다남은음식" and side.alive:
                got = side.heal(side.max_hp / 16.0)
                if got:
                    self._say("%s 먹다남은음식 %d 회복" % (side.name, got))
            self._pinch_berry(side)
            self._cure_berry(side)
            if side.herb():
                self._say("%s 의 하양허브 — 깎인 능력이 돌아왔다 (지금 %s)"
                          % (side.name, side.rank_text()))
            side.flinched = False
            side.enduring = False
            if (side.destiny_turn is not None
                    and self.turn > side.destiny_turn + 1):
                side.destiny_turn = None
            if side.perish and side.alive:
                side.perish -= 1
                if side.perish <= 0:
                    side.hp = 0
                    self._say("%s — 멸망의노래로 쓰러졌다" % side.name)
                else:
                    self._say("%s — 멸망까지 %d턴" % (side.name, side.perish))

        for party in (self.me_party, self.opp_party):
            if not party.wish:
                continue
            turns, amount = party.wish
            turns -= 1
            if turns <= 0:
                party.wish = None
                got = party.active.heal(amount) if party.active.alive else 0
                if got:
                    self._say("%s — 희망사항으로 %d 회복 (HP %d/%d)"
                              % (party.active.name, got,
                                 party.active.hp, party.active.max_hp))
            else:
                party.wish = (turns, amount)

        for party in (self.me_party, self.opp_party):
            for text in party.tick_screens():
                self._say(text)
        for text in self.field.tick():
            self._say(text)


# ---------------------------------------------------------------------------
# 계획을 돌려 본다
# ---------------------------------------------------------------------------
MAX_TURNS = 30           # 서로 못 죽이면 여기서 끊는다

# 얼마나 나아야 빼는가.
#
# 빼면 들어오는 놈이 그 턴에 한 대 맞는다. 조금 나은 정도로는 빼면 손해다.
# 이 값이 0이면 매 턴 들락날락하고, 너무 크면 영영 안 뺀다.
# 사람이 감으로 박은 값이다 (RANK_VALUE 와 같이 5장 B 에서 맞출 자리).
SWITCH_MARGIN = 0.15
# 빼서 들어오면 그 턴에 한 대 맞는다. 1대1 승률을 그만큼 깎아서 본다.
SWITCH_COST = 0.25
# 압정이 깔려 있으면 더 깎는다.
HAZARD_COST = 0.10

# 랭크 1단계를 'HP 몇 %' 로 칠 것인가.
#
# 이 숫자가 "용의춤 두 번 쌓고 HP 38% 로 이기기" 와 "그냥 때려서 HP 89% 로 이기기"
# 중 무엇을 고를지를 정한다. 지금은 사람이 감으로 박은 값이다.
# 설계 문서 5장 B('평가 기준 자동 조정')가 바로 이 숫자를 자동으로 맞추는 단계다.
# 여기가 그 첫 손잡이다.
RANK_VALUE = 15.0



def _pick(plan, turn_index):
    """계획의 turn_index 번째 수. 모자라면 마지막 수를 계속 쓴다."""
    return plan[min(turn_index, len(plan) - 1)]


class Policy(object):
    """누가 나와 있든 무엇을 할지 정한다.

    계획(plan)은 **처음 나온 놈의 수순**이다. 그놈이 빠지거나 쓰러져서
    다른 놈이 나와 있으면, 그놈이 쓸 수 있는 제일 아픈 수를 쓴다.

    이게 없으면 고릴타가 보만다의 이판사판태클을 쓰려 드는 일이 생긴다.
    (배우지도 않은 기술이라 조용히 이상한 계산이 된다.)
    """

    def __init__(self, dex, party, foe_build, plan, allow_switch=True,
                 moves=None, lead=None, auto_mega=True):
        """moves 를 주면 **계획이 끝난 뒤에도 그 기술들만 쓴다.**

        ! 이게 없어서 7단계가 조용히 거짓말을 했다. 계획(plan)은 첫 턴
          한 수뿐인데, 그 뒤부터는 `_best_move` 가 **사용률 상위 기술**을
          꺼내 썼다. 그래서 땅 기술만 든 한카리아스로 아머까오(비행,
          땅 무효)를 상대하는 판이 96.7% 승률로 나왔다 — 2턴째부터
          화염방사를 쓰고 있었던 것이다.
          숫자가 그럴듯해서 눈으로는 절대 못 잡는 종류다.

        lead 는 **계획이 누구 것이냐** 다. 안 주면 파티의 1번으로 본다.

        ! 여기서도 똑같이 조용히 틀어졌다. 실전은 1번이 나와 있는
          상태에서만 시작하지 않는데, lead 를 1번으로 굳혀 놓으니
          2번을 내보낸 채로 물으면 `act` 의 첫 줄
          (`party.active.base is self.lead`) 이 False 가 되어
          **계획을 통째로 건너뛰었다.** 그러면 "이 수를 두면
          어떻게 되나" 를 묻는데 그 수를 아예 안 두고 답한 것이다.
          재 보니 철벽·브레이브버드·날개쉬기 세 계획이 같은 씨앗에서
          결과까지 완전히 똑같이 나왔다 (이김 / 파티HP 81.04% / 6턴).
          점수는 91.9~93.1 로 그럴듯하게 벌어져 있어서 눈으로는 못 잡는다.
        """
        self.dex = dex
        self.plan = plan
        # moves 를 주면 **계획이 끝난 뒤에는 첫 수를 반복하지 않고**
        # 그 기술들 중 제일 나은 것을 매번 고른다 (7단계가 쓰는 방식).
        # 이름으로 줘도 받는다 — 안 그러면 `_best_move` 안에서 터진다.
        self.moves = ([m if isinstance(m, dict) else dex.find_move(m)
                       for m in moves] if moves else None)
        if lead is not None:
            self.lead = lead
        else:
            self.lead = party[0] if isinstance(party, (list, tuple)) else party
        self._fallback = {}
        self._foe = _first(foe_build)
        # **계획(plan) 턴에도 메가를 할 것인가.**
        #
        # ! 기본은 True 다. 계획을 돌려 보는 쪽(`battle.evaluate` · 선출)은
        #   "메가를 할지 말지" 를 따로 정하지 않으므로, 안 해 주면 메가
        #   보유자가 **실제보다 약하게** 나온다. 재 보니 메가보만다의
        #   이판사판태클 승률이 0.85 -> 0.69 로 떨어졌다 (스카이스킨이
        #   기본 폼엔 없다). 선출 추천이 통째로 흔들리는 크기다.
        # ! 7단계(`search.py`)만 False 로 준다. 거기서는 '메가하고 쓴다'
        #   와 '그냥 쓴다' 가 **서로 다른 후보**라, 여기서 덮으면 탐색이
        #   고른 답을 몰래 바꿔 버린다.
        self.auto_mega = auto_mega
        # 계획이 끝난 뒤에는 스스로 뺄지도 판단한다.
        # 이게 없으면 상대가 죽을 때까지 절대 안 빠지고, 그러면 내 승률이
        # 실제보다 한참 높게 나온다 (재 보니 최대 89%p 차이가 났다).
        self.allow_switch = allow_switch

    def _best_move(self, side, battle=None):
        # 내 기술을 아는 경우에는 **그 안에서만** 고른다.
        restricted = bool(self.moves) and self._is_lead(side)
        if restricted:
            side.moveset = [m["name"] for m in self.moves]   # 비장의무기가 본다
        key = (side.name, restricted)
        rows = self._fallback.get(key)
        if rows is None:
            if restricted:
                cand = [(m, None) for m in self.moves]
            else:
                cand = best.candidate_moves(self.dex, side.base.poke)
            rows = best.rate_moves(
                self.dex, side.as_build(), self._foe, cand)
            self._fallback[key] = rows
        # ! 표는 한 번만 재지만 **고르는 것은 매 턴** 한다. 전에는 고른 기술 하나를
        #   외워 두고 끝까지 썼는데, 만나자마자처럼 '나온 첫 턴만' 되는 기술이 1등이면
        #   둘째 턴부터 매번 실패하게 된다. 지금 확실히 실패할 기술은 빼고 고른다.
        #   (기습처럼 상대 선택에 달린 것은 턴 전에 알 수 없으므로 안 뺀다)
        if battle is not None:
            foe = battle.opp if side is battle.me else battle.me
            rows = [r for r in rows if battle.move_blocked(
                side, foe, r["move"], foresee=True) is None
                and not self._just_failed(side, r["move"], foe)]
        threat = best.best_threat(rows)
        if threat:
            return threat["move"]
        dmg = [r for r in rows if r["kind"] != "status"]
        return (dmg[0]["move"] if dmg else
                (rows[0]["move"] if rows else self.dex.find_move("막치기")))

    @staticmethod
    def _just_failed(side, move, foe=None):
        """상대 선택에 달린 기술(기습·기선제압·힘껏펀치)을 **지금 안 고를 까닭**.

        ! **이건 정한 규칙이지 잰 것이 아니다** (2026-09-22). 이게 없으면 철벽만
          쓰는 하마돈을 상대로 대도각참이 30턴 내내 기습을 골라 200판에 6000번
          실패했고 판이 안 끝났다. '방금 실패했으면 한 턴 쉰다' 로는 기습과
          아이언헤드를 번갈아 써서 여전히 2512번 실패했다.
          그래서 **사람이 보는 것** 으로 고른다 —
            기습     상대가 직전에 변화기를 썼으면 안 고른다
            기선제압 상대가 직전에 선제기가 아닌 기술을 썼으면 안 고른다
            힘껏펀치 방금 이 기술이 실패했으면 한 턴 쉰다
        """
        d = move.get("description") or ""
        seen = foe.last_move if foe is not None else None
        if _SUCKER.search(d) and seen is not None:
            return seen["category"] == "변화"
        if _UPPER_HAND.search(d) and seen is not None:
            return seen.get("priority", 0) <= 0
        return bool(_FOCUS.search(d) and side.last_failed and side.last_move
                    and side.last_move["name"] == move["name"])

    def _wrap_mega(self, party, action):
        """메가를 아직 안 썼고 지금 나와 있는 놈이 할 수 있으면 같이 한다.

        ! **이건 정한 규칙이지 잰 것이 아니다.** '기회가 오면 바로' 로 둔다 —
          실제로도 대개 그렇게 두고, 안 그러면 메가를 영영 안 써서 그 편이
          실제보다 약하게 나온다.
        ! **계획(plan)은 여기서 안 건드린다.** 계획은 부른 쪽이 정한 수라,
          "이번 턴에 메가를 안 한다" 도 하나의 수다. 그걸 여기서 덮으면
          탐색이 고른 답을 몰래 바꿔 버린다 — 전에 `Policy` 가 기술을
          몰래 바꿔 써서 크게 틀린 적이 있다 (CLAUDE.md §8).
        """
        if isinstance(action, tuple) or action is None:
            return action
        if party.can_mega():
            return ("메가", action)
        return action

    def _is_lead(self, side):
        """이 놈이 계획의 주인인가.

        **넘겨받은 Build 와 실제로 싸우는 Build 가 다를 수 있다** —
        메가스톤을 들면 `Side` 가 기본 폼으로 갈아 끼우기 때문이다.
        둘 다 본다.
        """
        return side.is_same(self.lead)

    def act(self, party, turn_index, battle=None):
        # 계획은 처음 나온 놈의 수순이다. 그놈이 나와 있는 동안은 계획대로.
        if self._is_lead(party.active) and turn_index < len(self.plan):
            want = self.plan[turn_index]
            return self._wrap_mega(party, want) if self.auto_mega else want

        # 계획이 끝났거나 다른 놈이 나와 있다 — 빼는 게 나은지 본다
        if self.allow_switch and battle is not None:
            idx = battle.should_switch(party)
            if idx is not None:
                return ("교체", idx)
        if self._is_lead(party.active):
            # ! **계획이 끝난 뒤 첫 수를 계속 반복하면 안 된다.**
            #   7단계는 "이번 턴에 이 수를 두면 어떻게 되나" 를 묻는데,
            #   반복해 버리면 "매 턴 이 수만 둔다면" 을 재게 된다.
            #   칼춤을 한 번 쓰는 것과 여섯 턴 내리 쓰는 것은 완전히
            #   다른 이야기다. 내 기술을 알 때는 매 턴 다시 고른다.
            if self.moves:
                return self._wrap_mega(party, self._best_move(party.active, battle))
            again = _pick(self.plan, turn_index)
            # 되풀이하려는 수가 **확실히 실패하면** (만나자마자를 둘째 턴에 등)
            # 되풀이하지 않고 쓸 수 있는 기술 중에서 고른다.
            if (battle is not None and isinstance(again, dict)
                    and (battle.move_blocked(
                        party.active,
                        battle.opp if party is battle.me_party else battle.me,
                        again, foresee=True)
                         or self._just_failed(
                             party.active, again,
                             battle.opp if party is battle.me_party else battle.me))):
                again = self._best_move(party.active, battle)
            return self._wrap_mega(party, again)
        return self._wrap_mega(party, self._best_move(party.active, battle))


def action_name(action, party=None):
    """수 하나를 사람이 읽을 이름으로. 교체는 누구로 바꾸는지까지 적는다."""
    if isinstance(action, tuple) and action[0] == "교체":
        if party is not None and action[1] < len(party):
            return "%s 로 교체" % party[action[1]].name
        return "교체"
    return action["name"]


def _first(builds):
    """파티를 줬으면 지금 나와 있는 놈, 한 마리를 줬으면 그놈."""
    return builds[0] if isinstance(builds, (list, tuple)) else builds


def _as_party(builds):
    return list(builds) if isinstance(builds, (list, tuple)) else [builds]


_MATCHUP_CACHE = {}


def matchup_table(dex, my_builds, opp_builds, trials=25, seed=11):
    """양쪽 파티의 1대1 승률을 미리 재 둔다. 이름쌍으로 찾는다.

    교체를 판단할 때 쓴다. 대전 한 판마다 다시 재면 너무 비싸므로
    시작 전에 한 번만 재고 돌려 쓴다.
    (여기서 돌리는 1대1 에는 교체가 없다 — 있으면 서로를 불러 무한히 돈다.)
    """
    mine = _as_party(my_builds)
    theirs = _as_party(opp_builds)
    if len(mine) == 1 and len(theirs) == 1:
        return {}                       # 1대1 이면 교체가 없으니 필요 없다
    key = (tuple(b.name for b in mine), tuple(b.name for b in theirs), trials)
    if key in _MATCHUP_CACHE:
        return _MATCHUP_CACHE[key]
    out = {}
    for i, a in enumerate(mine):
        for j, b in enumerate(theirs):
            opp_plan, _, _ = opponent_plan(dex, b, a)
            plans, _ = build_plans(dex, a, b)
            plan = plans[0] if plans else [dex.find_move("막치기")]
            rng = random.Random(seed + i * 13 + j)
            win = 0
            for _ in range(trials):
                r = run_once(dex, a, b, plan, opp_plan, rng, opp_switch=False)
                if r["result"] == "이김":
                    win += 1
            p = win / float(trials)
            out[(a.name, b.name)] = p
            out[(b.name, a.name)] = 1.0 - p
    _MATCHUP_CACHE[key] = out
    return out


def run_once(dex, me_build, opp_build, my_plan, opp_plan, rng, log=False,
             opp_switch=True, matchup=None, my_moves=None, state=None,
             auto_mega=True):
    """한 판. 끝났을 때의 상태를 통째로 돌려준다.

    my_moves 를 주면 계획이 끝난 뒤에도 **내 기술 안에서만** 고른다.
    """
    kw = dict(state or {})
    if state is None:
        # 판 처음부터 — 둘 다 **확실히** 막 나왔다 (경고할 일이 아니다).
        # 실전 중간 상태(state)를 주면 모른다 — Battle 이 가정하고 경고한다.
        kw["my_fresh"] = kw["opp_fresh"] = True
    b = Battle(dex, me_build, opp_build, rng=rng, log=log,
               matchup=matchup, **kw)
    # 내 쪽은 '이 계획이 좋은가' 를 재는 중이므로 계획을 그대로 밀고,
    # 계획이 끝난 뒤부터는 양쪽 다 빼는 것을 판단한다.
    # ! lead 를 **Battle 에게 물어서** 넘긴다. 손으로 me_build[0] 이라고
    #   적으면 state 로 '2번이 나와 있다' 를 줬을 때 조용히 어긋난다.
    mine = Policy(dex, me_build, opp_build, my_plan, moves=my_moves,
                  lead=b.me_party.active.base, auto_mega=auto_mega)
    theirs = Policy(dex, opp_build, me_build, opp_plan,
                    allow_switch=opp_switch, lead=b.opp_party.active.base)
    for i in range(MAX_TURNS):
        if b.over:
            break
        b.step(mine.act(b.me_party, i, b), theirs.act(b.opp_party, i, b))
    if b.me_party.alive and not b.opp_party.alive:
        result = "이김"
    elif b.opp_party.alive and not b.me_party.alive:
        result = "짐"
    elif not b.me_party.alive and not b.opp_party.alive:
        result = "동시에 쓰러짐"
    else:
        result = "안 끝남"
    # 파티 단위 결과. '한 마리 내주고 이겼는가' 를 보려면 이게 있어야 한다.
    my_alive = sum(1 for m in b.me_party.members if m.alive)
    my_hp = (sum(m.hp for m in b.me_party.members)
             / float(sum(m.max_hp for m in b.me_party.members)))
    return {"result": result, "turns": b.turn,
            "me": b.me.snapshot(), "opp": b.opp.snapshot(),
            "myAlive": my_alive, "myCount": len(b.me_party.members),
            "myPartyHpPct": my_hp * 100.0,
            "myLost": len(b.me_party.members) - my_alive,
            "log": b.log, "warnings": b.warnings,
            "weather": b.field.weather, "terrain": b.field.terrain}


def evaluate(dex, me_build, opp_build, my_plan, opp_plan, trials=400,
             seed=7, my_party=None, matchup=None):
    """같은 계획을 여러 번 돌려 승률과 '평균적으로 어떤 상태로 끝나는지' 를 낸다.

    난수(데미지 16단계 · 명중 · 급소 · 마비)가 있으므로 한 판만 봐서는 안 된다.

    matchup 을 주면 1대1 상성표를 **다시 재지 않는다.**

    ! 이걸 안 주면 여기서 매번 표를 새로 잰다. 표 하나가 3x3 x 25판
      = 225판이라, 400조합을 훑는 6단계(선출)에서는 **조합당 225판이
      덤으로** 붙었다. 실제 평가가 조합당 29판이었으니 덤이 본전의
      8배였던 것이다. 45초로 잡은 예산이 199초가 나왔다.
      표는 이름으로 캐시되는데 3마리 조합마다 이름쌍이 달라서
      400개가 전부 따로 만들어졌다. 6x6 표를 이미 재 놓고도 그랬다.
    """
    rng = random.Random(seed)
    wins = 0
    turns = hp = 0.0
    lost = party_hp = 0.0
    ranks = {}
    counts = {}
    warnings = []
    table = matchup if matchup is not None else matchup_table(
        dex, me_build, opp_build)
    for _ in range(trials):
        r = run_once(dex, me_build, opp_build, my_plan, opp_plan, rng,
                     matchup=table)
        counts[r["result"]] = counts.get(r["result"], 0) + 1
        if r["result"] == "이김":
            wins += 1
            hp += r["me"]["hpPct"]
            # 이기긴 했는데 몇 마리를 내줬나. 빼는 것과 내주는 것을 견주려면 필요하다.
            lost += r["myLost"]
            party_hp += r["myPartyHpPct"]
            for k, v in r["me"]["ranks"].items():
                ranks[k] = ranks.get(k, 0.0) + v
        turns += r["turns"]
        for w in r["warnings"]:
            if w not in warnings:
                warnings.append(w)
    avg_hp = (hp / wins) if wins else 0.0
    avg_lost = (lost / wins) if wins else 0.0
    avg_party_hp = (party_hp / wins) if wins else 0.0
    avg_ranks = {k: v / wins for k, v in ranks.items()} if wins else {}
    # 이기고 나서 남는 몸을 한 숫자로. 후속 포켓몬에게 이어지는 값어치다.
    carry = avg_hp + sum(avg_ranks.values()) * RANK_VALUE
    return {
        "plan": [action_name(a, my_party) for a in my_plan],
        "winRate": wins / float(trials),
        "avgTurns": turns / float(trials),
        # 이겼을 때 평균적으로 어떤 몸으로 남는가 — 후속 포켓몬에게 그대로 이어진다
        "avgHpPctWhenWin": avg_hp,
        "avgRanksWhenWin": avg_ranks,
        "carry": carry,
        "lostWhenWin": avg_lost,        # 이길 때 평균 몇 마리를 내줬나
        "partyHpWhenWin": avg_party_hp,  # 이길 때 파티 전체 HP 가 얼마나 남나
        "counts": counts, "trials": trials, "warnings": warnings,
    }


def evaluate_vs_distribution(dex, me_build, opp_poke, my_plan, trials=400,
                             seed=7, evidence=None, my_party=None):
    """4-C — 상대를 하나로 고정하지 않고, 매 판 새로 뽑아서 싸운다.

    '사용률 1위 배분에 제일 아픈 기술' 하나를 상대로 삼으면
    채용률 4% 짜리 기술을 100% 확정으로 놓는 셈이 된다.
    여기서는 채용률대로 상대를 뽑으므로, 나오는 승률이
    **실제로 만날 상대들을 평균한 값**이 된다.

    덤으로 '졌을 때 상대가 뭘 들고 있었나' 를 센다. 이게 착취 전략의 재료다.
    """
    rng = random.Random(seed)
    speed_of = lambda b: best.effective_speed(dex, b)[0]
    wins = 0
    carry_sum = 0.0
    lost_sum = party_hp_sum = 0.0
    turns = 0.0
    warnings = []
    # 무엇이 나를 이겼나 / 전체에서는 얼마나 나왔나
    seen = {"기술": {}, "도구": {}, "특성": {}}
    lost = {"기술": {}, "도구": {}, "특성": {}}

    for _ in range(trials):
        opp_build, opp_moves = scout.sample_opponent(
            dex, opp_poke, rng, evidence, speed_of)
        rows = best.rate_moves(dex, opp_build, _first(me_build),
                               [(m, None) for m in opp_moves])
        threat = best.best_threat(rows)
        if threat:
            opp_plan = [threat["move"]]
        else:
            opp_plan = [opp_moves[0]] if opp_moves else [dex.find_move("막치기")]

        r = run_once(dex, me_build, opp_build, my_plan, opp_plan, rng)
        won = r["result"] == "이김"
        if won:
            wins += 1
            carry_sum += (r["me"]["hpPct"]
                          + sum(r["me"]["ranks"].values()) * RANK_VALUE)
            lost_sum += r["myLost"]
            party_hp_sum += r["myPartyHpPct"]
        turns += r["turns"]
        for w in r["warnings"]:
            if w not in warnings:
                warnings.append(w)

        tags = [("기술", m["name"]) for m in opp_moves]
        if opp_build.item:
            tags.append(("도구", opp_build.item))
        if opp_build.ability:
            tags.append(("특성", opp_build.ability))
        for kind, name in tags:
            seen[kind][name] = seen[kind].get(name, 0) + 1
            if not won:
                lost[kind][name] = lost[kind].get(name, 0) + 1

    losses = trials - wins
    blame = []
    for kind in ("기술", "도구", "특성"):
        for name, n_lost in lost[kind].items():
            n_seen = seen[kind][name]
            # 졌을 때 이게 있었을 비율 vs 평소 있을 비율
            share_lost = n_lost / float(losses) if losses else 0.0
            share_all = n_seen / float(trials)
            if share_all <= 0 or n_lost < 3:
                continue
            blame.append({"kind": kind, "name": name,
                          "inLosses": share_lost, "overall": share_all,
                          "lift": share_lost / share_all})
    blame.sort(key=lambda x: -(x["lift"] * x["inLosses"]))

    return {
        "plan": [action_name(a, my_party) for a in my_plan],
        "winRate": wins / float(trials),
        "avgTurns": turns / float(trials),
        "carry": (carry_sum / wins) if wins else 0.0,
        "lostWhenWin": (lost_sum / wins) if wins else 0.0,
        "partyHpWhenWin": (party_hp_sum / wins) if wins else 0.0,
        "blame": blame, "trials": trials, "warnings": warnings,
        "distribution": True,
    }


def build_plans(dex, me_build, opp_build, my_moves=None):
    """비교해 볼 계획들을 만든다.

    ① 공격기 하나만 계속  ② 변화기 한 번 쓰고 그 공격기  ③ 변화기 두 번
    ④ **빠지고 나서 때린다** — 파티가 있을 때만 (5단계)
    """
    party = _as_party(me_build)
    me_build = _first(me_build)
    opp_build = _first(opp_build)
    rows = best.rate_moves(dex, me_build, opp_build,
                           best.candidate_moves(dex, me_build.poke, my_moves))
    dmg = sorted(best.damage_rows(rows), key=lambda r: -r["expected"])
    setups = [r["move"] for r in rows if r["kind"] == "status"
              and any(e["kind"] in ("rank", "heal") for e in move_effects(r["move"]))]
    if not dmg:
        return [], rows

    main = dmg[0]["move"]
    plans = [[main]]
    for s in setups[:3]:
        plans.append([s, main])
        plans.append([s, s, main])
    # 두 번째로 센 공격기도 한 번 본다
    if len(dmg) > 1:
        plans.append([dmg[1]["move"]])

    # 빠지는 것도 하나의 수다. 벤치마다 '바꿔서 그놈의 주력으로 때린다' 를 만든다.
    for i in range(1, len(party)):
        sub_rows = best.rate_moves(
            dex, party[i], opp_build,
            best.candidate_moves(dex, party[i].poke))
        sub = best.best_threat(sub_rows)
        if sub:
            plans.append([("교체", i), sub["move"]])
    return plans, rows


def realistic_moveset(dex, poke, slots=4):
    """상대가 실제로 들고 있을 법한 기술 4개 = 채용률 상위 4개.

    **이건 '같이 쓰이는 4개' 가 아니라 '각각 많이 쓰이는 4개' 다.**
    사용률에는 기술끼리의 조합 정보가 없다. 실제로는 배분에 따라 구성이 갈린다
    (한카리아스 AS형은 드래곤테일을 잘 안 들고, HB형은 스텔스록과 같이 든다).
    그래도 '채용률 1위 기술 하나' 만 보는 것보다는 훨씬 실제에 가깝다.
    제대로 하려면 형태별 샘플이 필요하다 — docs/ai-design.md 참고.
    """
    cand = best.candidate_moves(dex, poke)
    with_pct = [(m, p) for m, p in cand if p is not None]
    if not with_pct:
        return cand[:slots]
    with_pct.sort(key=lambda x: -x[1])
    return with_pct[:slots]


def opponent_plan(dex, opp_build, me_build, worst_case=False):
    """상대가 쓸 수를 정한다.

    기본 — 채용률 상위 4개(실제로 들고 다닐 법한 구성)만 놓고 그 중 제일 아픈 수.
    --최악 — 사용률 목록 전체에서 제일 아픈 수. 채용률 4%짜리도 들고 있다고 본다.

    4-C 에서 이 자리가 '분포' 로 바뀐다.
    """
    opp_build = _first(opp_build)
    me_build = _first(me_build)
    pool = (best.candidate_moves(dex, opp_build.poke) if worst_case
            else realistic_moveset(dex, opp_build.poke))
    rows = best.rate_moves(dex, opp_build, me_build, pool)
    threat = best.best_threat(rows)
    if threat:
        return [threat["move"]], rows, pool
    # 때릴 수단이 하나도 없으면 변화기라도 쓴다
    for r in rows:
        if r["kind"] == "status":
            return [r["move"]], rows, pool
    return [dex.find_move("막치기")], rows, pool


# ---------------------------------------------------------------------------
# 보고서
# ---------------------------------------------------------------------------
def _rank_text(ranks):
    got = ["%s%+.1f" % (calc.STAT_KO[k], v) for k, v in ranks.items()
           if abs(v) >= 0.05]
    return " ".join(got) if got else "없음"


def report(dex, me_build, opp_build, results, opp_plan_moves, opp_pool, trials,
           me_party=None, opp_party=None):
    L = []
    line = "=" * 78
    L.append(line)
    L.append("  4-B  턴을 끝까지 돌려 본 결과   ·   각 계획 %d판" % trials)
    L.append(line)
    L.append("  나   " + _first(me_build).describe())
    if me_party and len(me_party) > 1:
        L.append("       벤치 " + ", ".join(b.name for b in me_party[1:]))
    L.append("  상대 " + _first(opp_build).describe())
    if opp_party and len(opp_party) > 1:
        L.append("       벤치 " + ", ".join(b.name for b in opp_party[1:]))
    L.append("")
    L.append("  [판단의 근거]  나중에 지고 나서 되짚을 수 있도록 남긴다")
    L.append("    · 상대 기술 4개를 이렇게 가정했다 — %s"
             % ", ".join("%s(%.0f%%)" % (m["name"], p) if p is not None
                         else m["name"] for m, p in opp_pool))
    L.append("    · 그 중 '%s' 를 계속 쓴다고 봤다 (넷 중 제일 아픈 수)"
             % " → ".join(m["name"] for m in opp_plan_moves))
    L.append("    · 상대 배분은 사용률 1위로 가정했다")
    L.append("    · 난수·명중·급소·마비는 매 판 굴렸다")
    L.append("    ! 채용률 상위 4개일 뿐, '실제로 같이 쓰이는 4개' 는 아니다.")
    L.append("-" * 78)

    party_mode = bool(me_party and len(me_party) > 1)
    if party_mode:
        head = [("계획", 34), ("승률", 8), ("평균턴", 8),
                ("이길 때 잃는 마릿수", 20), ("남는 파티 HP", 16),
                ("남는 랭크", 20)]
    else:
        head = [("계획", 34), ("승률", 8), ("평균턴", 8),
                ("이겼을 때 남는 HP", 20), ("남는 랭크", 20), ("남는 몸", 8)]
    L.append("  " + "".join(best._pad(h, w) for h, w in head).rstrip())
    for r in results:
        if party_mode:
            cells = [
                " → ".join(r["plan"]),
                "%.1f%%" % (r["winRate"] * 100),
                "%.1f" % r["avgTurns"],
                "%.2f마리" % r["lostWhenWin"] if r["winRate"] else "-",
                "%.0f%%" % r["partyHpWhenWin"] if r["winRate"] else "-",
                _rank_text(r["avgRanksWhenWin"]) if r["winRate"] else "-",
            ]
        else:
            cells = [
                " → ".join(r["plan"]),
                "%.1f%%" % (r["winRate"] * 100),
                "%.1f" % r["avgTurns"],
                "%.0f%%" % r["avgHpPctWhenWin"] if r["winRate"] else "-",
                _rank_text(r["avgRanksWhenWin"]) if r["winRate"] else "-",
                "%.0f" % r["carry"] if r["winRate"] else "-",
            ]
        L.append("  " + "".join(best._pad(c, w)
                                for c, (h, w) in zip(cells, head)).rstrip())

    L.append("-" * 78)
    top = results[0]
    L.append("  추천   %s" % " → ".join(top["plan"]))
    L.append("         승률 %.1f%%" % (top["winRate"] * 100))
    if top["winRate"] and top["avgRanksWhenWin"]:
        L.append("         이기고 나서 %s 를 들고 다음 포켓몬을 맞는다"
                 % _rank_text(top["avgRanksWhenWin"]))
        L.append("         ↑ 이 값어치는 후속 포켓몬까지 이어진다. "
                 "승패만 보면 안 보이는 부분이다.")
    if len(results) > 1:
        second = results[1]
        gap = (top["winRate"] - second["winRate"]) * 100
        if abs(gap) < 2:
            L.append("         ! 승률은 2위(%s)와 %.1f%%p 차이뿐이다."
                     % (" → ".join(second["plan"]), abs(gap)))
            L.append("           '남는 몸' = HP%% + 랭크합 x %.0f 으로 갈랐다. "
                     "랭크 1단계를 HP %.0f%% 로 친 값이고," % (RANK_VALUE, RANK_VALUE))
            L.append("           사람이 감으로 박은 숫자다 (5장 B 에서 자동으로 맞출 자리).")

    if party_mode:
        L.append("")
        L.append("  [빼는 것 vs 내주는 것]  ← 불리하다고 늘 빼는 것이 답은 아니다")
        L.append("    · 빼면   — 들어오는 놈이 그 턴에 한 대 맞고 압정도 밟는다.")
        L.append("              대신 뺀 놈은 살아 남는다 (쌓아 둔 랭크는 사라진다).")
        L.append("    · 내주면 — 한 마리를 잃지만 다음 놈이 공짜로 나온다.")
        L.append("              쓰러진 자리로 나오는 턴에는 안 맞고, 압정만 밟는다.")
        L.append("    위 표의 '이길 때 잃는 마릿수' 와 '남는 파티 HP' 로 둘을 견준다.")

    warns = []
    for r in results:
        for w in r["warnings"]:
            if w not in warns:
                warns.append(w)
    if warns:
        L.append("")
        L.append("  [아직 계산에 안 들어간 것]")
        for w in warns:
            L.append("    ! %s" % w)
    L.append(line)
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 명령줄
# ---------------------------------------------------------------------------
def report_distribution(dex, me_build, opp_poke, results, evidence, trials):
    """4-C 보고서 — 상대를 분포로 봤을 때."""
    L = []
    line = "=" * 78
    L.append(line)
    L.append("  4-C  상대를 하나가 아니라 분포로   ·   각 계획 %d판" % trials)
    L.append(line)
    L.append("  나   " + me_build.describe())
    L.append("  상대 %s — 매 판 사용률대로 새로 뽑는다"
             % (opp_poke["formName"] or opp_poke["name"]))
    L.append("       본 것: %s" % evidence.describe())
    L.append("")
    L.append("  [상대가 들고 있을 확률]")
    # 본 것이 있으면 형태가 좁혀지고, **안 본 기술의 확률까지 같이 움직인다** (1-A)
    probs = scout.narrowed_probabilities(dex, opp_poke, evidence)
    L.append("    " + "  ·  ".join("%s %.0f%%" % (mv["name"], pr * 100)
                                   for mv, pr in probs[:8]))
    L.append("-" * 78)

    head = [("계획", 36), ("승률", 10), ("평균턴", 8), ("이겼을 때 남는 몸", 18)]
    L.append("  " + "".join(best._pad(h, w) for h, w in head).rstrip())
    for r in results:
        cells = [" → ".join(r["plan"]), "%.1f%%" % (r["winRate"] * 100),
                 "%.1f" % r["avgTurns"],
                 "%.0f" % r["carry"] if r["winRate"] else "-"]
        L.append("  " + "".join(best._pad(c, w)
                                for c, (h, w) in zip(cells, head)).rstrip())

    L.append("-" * 78)
    top = results[0]
    L.append("  추천   %s   (승률 %.1f%%)"
             % (" → ".join(top["plan"]), top["winRate"] * 100))

    hits = [b for b in top["blame"][:6] if b["lift"] >= 1.3]
    if hits:
        L.append("")
        L.append("  [졌을 때 상대는 이랬다]  ← 여기가 이 프로젝트의 무기다")
        for b in hits:
            L.append("    · %s '%s' — 졌을 때 %.0f%% 에 있었다 (평소 %.0f%%, %.1f배)"
                     % (b["kind"], b["name"], b["inLosses"] * 100,
                        b["overall"] * 100, b["lift"]))
        L.append("    평소 잘 안 나오는 것이 위에 있으면 '운 나쁘면 지는' 경우이고,")
        L.append("    자주 나오는 것이 위에 있으면 진짜로 불리한 대면이다.")

    warns = []
    for r in results:
        for w in r["warnings"]:
            if w not in warns:
                warns.append(w)
    if warns:
        L.append("")
        L.append("  [아직 계산에 안 들어간 것]")
        for w in warns[:6]:
            L.append("    ! %s" % w)
    L.append("")
    L.append("  ! 성격·노력치·도구·기술을 서로 독립이라고 보고 뽑은 근사다.")
    L.append("    실제로는 형태별로 몰려 다닌다 (한카리아스 AS형은 드래곤테일을 잘 안 듦).")
    L.append(line)
    return "\n".join(L)


USAGE = """사용법: python battle.py <내 포켓몬> <상대 포켓몬> [옵션]

  포켓몬을 쉼표로 여러 마리 적으면 교체가 있는 대전이 된다 (5단계)
    python battle.py 메가보만다,한카리아스 하마돈,브리두라스

  --분포                       상대를 사용률대로 매 판 새로 뽑는다 (4-C)
  --봤다 지진,하품             상대가 쓰는 걸 본 기술 — 확률 100%로 확정된다
  --계획 용의춤,이판사판태클   이 순서대로 쓰는 계획 하나만 돌려본다
  --판수 1000                  기본 400
  --기록                       한 판을 턴별로 찍어서 보여준다
  --최악                       상대가 채용률 낮은 기술까지 다 들고 있다고 본다

  예 : python battle.py 메가보만다 하마돈
       python battle.py 메가보만다 하마돈 --분포
       python battle.py 메가보만다 하마돈 --분포 --봤다 얼음엄니
"""


def main():
    paths.fix_console()   # 윈도우에서 한글을 찍다 죽지 않게
    args = sys.argv[1:]
    trials, plan_arg, show_log, worst = 400, None, False, False
    use_dist, seen = False, []
    rest = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--판수" and i + 1 < len(args):
            trials = int(args[i + 1]); i += 2
        elif a == "--계획" and i + 1 < len(args):
            plan_arg = args[i + 1]; i += 2
        elif a == "--기록":
            show_log = True; i += 1
        elif a == "--최악":
            worst = True; i += 1
        elif a == "--분포":
            use_dist = True; i += 1
        elif a == "--봤다" and i + 1 < len(args):
            seen = [x.strip() for x in args[i + 1].split(",") if x.strip()]
            use_dist = True; i += 2
        else:
            rest.append(a); i += 1

    if len(rest) < 2:
        print(USAGE)
        return

    dex = calc.Dex()
    try:
        # 쉼표로 여러 마리를 적으면 교체가 있는 대전이 된다 (5단계)
        me_party = [calc.popular_build(dex, dex.find_pokemon(n))[0]
                    for n in rest[0].split(",") if n.strip()]
        opp_party = [calc.popular_build(dex, dex.find_pokemon(n))[0]
                     for n in rest[1].split(",") if n.strip()]
        me = me_party if len(me_party) > 1 else me_party[0]
        opp = opp_party if len(opp_party) > 1 else opp_party[0]
        opp_plan, _, opp_pool = opponent_plan(dex, opp, me, worst_case=worst)
        if plan_arg:
            plans = [[dex.find_move(n) for n in plan_arg.split(",")]]
        else:
            plans, _ = build_plans(dex, me, opp)
    except LookupError as e:
        print("! %s" % e)
        return

    if not plans:
        print("  데미지가 들어가는 기술이 없습니다. 교체를 봐야 합니다 (5단계).")
        return

    # 승률이 먼저. 파티가 있으면 '몇 마리를 잃었나' 로, 아니면 '남는 몸' 으로 가른다.
    def rank_key(r):
        if len(me_party) > 1:
            return (-r["winRate"], r.get("lostWhenWin", 0),
                    -r.get("partyHpWhenWin", 0))
        return (-r["winRate"], -r["carry"])

    if use_dist:
        ev = scout.Evidence(seen_moves=seen)
        results = [evaluate_vs_distribution(dex, me, _first(opp).poke, p,
                                            trials=trials, evidence=ev,
                                            my_party=me_party)
                   for p in plans]
        results.sort(key=rank_key)
        print(report_distribution(dex, _first(me), _first(opp).poke, results,
                                  ev, trials))
    else:
        results = [evaluate(dex, me, opp, p, opp_plan, trials=trials,
                            my_party=me_party)
                   for p in plans]
        results.sort(key=rank_key)
        print(report(dex, me, opp, results, opp_plan, opp_pool, trials,
                     me_party=me_party, opp_party=opp_party))

    if show_log:
        r = run_once(dex, me, opp, plans[0], opp_plan, random.Random(1), log=True)
        print("\n  [한 판 기록 — %s]" % " → ".join(m["name"] for m in plans[0]))
        for row in r["log"]:
            print("    " + row)
        print("    결과: %s (%d턴)" % (r["result"], r["turns"]))


if __name__ == "__main__":
    main()
