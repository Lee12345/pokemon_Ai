# -*- coding: utf-8 -*-
"""
포켓몬 챔피언스 데미지 계산기.

사용법 (둘 다 됨):

  1) 바로 물어보기
     python calc.py 메가보만다 이판사판태클 하마돈

  2) 대화식
     python calc.py

먼저 build_data.py 와 build_usage.py 를 실행해 둬야 한다.
"""

import json
import math
import os
import re
import sys

import paths

HERE = paths.read_root()
DATA = paths.data()

# ---------------------------------------------------------------------------
# 아직 게임에서 직접 확인하지 못한 값들.
# 실제 대전 결과와 어긋나면 여기 숫자만 고치면 된다.
# ---------------------------------------------------------------------------
CONFIG = {
    "level": 50,                # 랭크배틀은 50 고정
    # 자속·급소는 **사용자가 확실하다고 확인해 준 값**이다 (2026-09-17).
    # 감도 측정 결과 이 둘이 미확인 값 중 유일하게 답을 흔드는 것이었는데,
    # 확정되면서 그 구멍이 닫혔다 — sensitivity.py 참고.
    "stab": 1.5,                # 자속 보정 — 확정
    "critical": 1.5,            # 급소 배율 — 확정
    # 화상·마비도 **사용자가 확실하다고 확인해 준 값**이다 (2026-09-18).
    # 이걸로 감도 측정에서 답을 흔들던 값이 전부 닫혔다.
    "burn_physical": 0.5,       # 화상일 때 물리 데미지 — 확정
    "paralysis_speed": 0.5,     # 마비일 때 스피드 — 확정
    "random_min": 85,           # 데미지 난수 하한 (85~100, 16단계)
    "random_max": 100,
    # --- 아래는 턴을 넘겨야 의미가 생기는 값들 (battle.py 가 쓴다) ---
    # 전부 본편 값을 가져다 쓴 것이고 챔피언스에서 확인한 적이 없다.
    # 실전에서 어긋나면 여기부터 의심할 것.
    "crit_rate": 1 / 24.0,      # 급소가 뜰 확률 — 미확인
    # 급소업 단계별 확률. 0단계가 위의 crit_rate 다. 전부 미확인 (본편 7세대 이후 값).
    # '반드시 급소' 기술은 단계와 상관없이 무조건 뜬다.
    "crit_stage_rates": [1 / 24.0, 1 / 8.0, 0.5, 1.0],
    "paralysis_skip": 0.25,     # 마비로 그 턴 행동을 못 할 확률 — 미확인
    "burn_chip": 16,            # 화상: 턴 끝에 최대 HP의 1/N — 미확인
    "poison_chip": 8,           # 독: 턴 끝에 최대 HP의 1/N — 미확인
    "sand_chip": 16,            # 모래바람: 턴 끝에 최대 HP의 1/N — 미확인
    "sand_rock_spdef": 1.5,     # 모래바람일 때 바위 타입 특방 배율 — 미확인
    "terrain_boost": 1.3,       # 필드가 같은 타입 기술을 올려 주는 배율 — 미확인
    # 날씨가 타입에 주는 배율. 게임 데이터의 기술·특성 설명문 어디에도
    # 숫자가 없어서 본편 값을 가져다 쓴다 — 전부 미확인이다.
    #   비: 물 1.5 / 불꽃 0.5     쾌청: 불꽃 1.5 / 물 0.5
    "weather_boost": 1.5,       # 날씨가 맞는 타입을 올려 주는 배율 — 미확인
    "weather_weaken": 0.5,      # 날씨가 반대 타입을 깎는 배율 — 미확인
    # 빛의장막·리플렉터·오로라베일이 데미지를 얼마나 깎는가. 기술 설명문은
    # "같은 편 필드를 OO 상태로 만든다" 뿐이고 **수치가 없다.** 본편 싱글
    # 값(1/2)을 쓴다 — 미확인.
    "screen_reduce": 0.5,       # 스크린이 깎는 비율 — 미확인
    "toxic_chip": 16,           # 맹독: 1턴째 1/N, 매 턴 1/N 씩 늘어남 — 미확인
    "sleep_min": 2,             # 잠듦 지속 턴 (본편 5세대 이후 2~4) — 미확인
    "sleep_max": 4,
    "freeze_thaw": 0.20,        # 얼음이 풀릴 확률 — 미확인
    "confuse_self": 1 / 3.0,    # 혼란일 때 자기를 때릴 확률 — 미확인
    "confuse_power": 40,        # 혼란 자해의 위력 (무속성 물리) — 미확인
    "confuse_min": 1,           # 혼란 지속 턴 — 미확인
    "confuse_max": 4,
    "infatuation_skip": 0.5,    # 헤롱헤롱으로 행동 못 할 확률 — 미확인
    # --- 압정 (5단계) ---
    # 기술 설명문은 '상대 필드를 스텔스록 상태로 만든다' 뿐이고 **수치가 없다.**
    # 전부 본편 값을 가져다 쓴 것이라 미확인이다.
    "rock_hazard": 8,           # 스텔스록: 최대 HP의 1/N x 바위 상성
    "spike_layers": [8, 6, 4],  # 압정뿌리기: 1겹 1/8, 2겹 1/6, 3겹 1/4
    "max_spike_layers": 3,
    "max_toxic_layers": 2,      # 독압정: 1겹 독, 2겹 맹독
    # --- 형태 추론 (1-A) / 세기는 구축기사 표본으로 맞춤 (1-B) ---
    #
    # 처음에는 넷 다 내가 감으로 잡았다. 그 뒤 구축기사 **개체 1,326마리**로
    # 최대가능도로 맞췄더니 **내가 잡은 값이 전부 너무 약했다** (2026-09-17).
    #   form   0.15 -> 0.05     nature 0.05 -> 0.01
    #   item   1.0  -> 4.5      mega   1.5  -> 1.5 (이건 맞았다)
    # 927마리에서 잰 값과 1,326마리에서 잰 값이 같아서 수렴한 것으로 본다.
    # 다시 재는 방법: python samples.py --맞추기
    #
    # ! 표본은 **랭커가 쓴 것**이다. 랭커는 형태와 기술을 더 딱 맞춰 짜므로
    #   이 세기는 래더 평균보다 셀 수 있다. 그래도 '아예 안 가른다(독립)'
    #   보다는 실제에 가깝다 — 그건 감도로 따로 쟀다 (sensitivity.py --형태).

    # 노력치 배분과 안 어울리는 기술을 들고 있을 **승산 배율**.
    # 특수형 한카리아스가 지진을 들고 있을 승산을 얼마나 깎을 것인가.
    "form_mismatch": 0.05,          # 표본으로 맞춤 (원래 0.15)

    # 도구가 어느 형태에 쏠리는지는 **데이터에서 잰다** (forms.item_tendency).
    # 여기 있는 건 그 상관을 승산으로 바꿀 때의 세기.
    #   승산 배율 = exp(세기 x 상관).  상관 0.69 에 세기 4.5 면 약 22배.
    # 0 으로 두면 도구를 형태 추론에 안 쓰는 것과 같다.
    "item_tendency_strength": 4.5,  # 표본으로 맞춤 (원래 1.0)

    # 성격은 기술보다 규칙이 딱딱하다. CS형이 지진을 커버로 드는 일은 실제로
    # 있지만, CS형이 특수공격을 깎는 성격을 드는 일은 **사실상 없다.**
    # 표본 1,350마리에서 맞춰 보니 격자 **바닥**이 뽑혔다 — 반례가 없다는 뜻이다.
    # 그래도 0 으로는 안 둔다. 확률이 0 이면 관찰이 어긋났을 때 사후확률이
    # 통째로 무너져서 빠져나갈 길이 없어진다. 안전분으로 0.01 을 남긴다.
    # 표본 3,047마리에서 **0.003** 이 최댓값이다. 0.001 과는 0.15 차이로
    # 구별이 안 되고(고원), 0.01 은 4.2 · 0.05(내 감)는 28.4 만큼 나쁘다.
    # 즉 반례가 아주 없는 것이 아니라 **0.3% 쯤은 있다.** 그럴 만하다 —
    # 바디프레스는 방어로 때리니 공격 깎는 성격이 정상이고, 트릭룸은
    # 스피드를 깎는다. (처음에 '격자 끝' 으로 보인 것은 내 격자의 제일
    # 낮은 값이 우연히 그 근처였기 때문이다.)
    "nature_mismatch": 0.003,       # 표본으로 맞춤 (내 감 0.05)

    # 메가스톤은 상관이 아니라 **메가 폼의 종족값**이 형태를 정한다.
    # (메가스톤은 한 포켓몬만 쓰므로 포켓몬끼리의 상관을 잴 수가 없다.)
    #   승산 배율 = exp(세기 x (공격-특공)/100).  차이 85 에 세기 1.5 면 약 3.6배.
    # 임계값을 두지 않는다 — 차이가 작으면 저절로 거의 안 움직인다.
    # **한 번 잘못 내렸다가 되돌린 값이다. 기록으로 남긴다.**
    #
    # 표본 1,291마리에서 재니 0.75 가 나와서 그리로 내렸다. 그때 곡선이
    # 평평하다는 것을 **측정해서 알고 있었는데도**(0.75 와 1.125 가 0.054
    # 차이) 최댓값을 따라갔다. 표본을 2,896마리로 늘리고 다시 재니:
    #
    #     0.375  차이 12.3     1.500  차이  0.000  <- 최고
    #     0.750  차이  6.2     2.000  차이  0.043
    #     1.125  차이  2.1     3.000  차이  8.7
    #
    # 0.75 는 이제 6.2 만큼 나쁘다. **평평한 구간의 최댓값은 잡음이었다.**
    # 교훈: 고원에서는 값을 옮기지 말고 표본을 더 모은다. 그래서 --맞추기 가
    # 이제 고원 범위를 같이 찍어 주고, 지금 값이 그 안에 있으면 '구별 안 됨'
    # 이라고 알린다 (samples.report_fit).
    "mega_stat_strength": 1.5,      # 표본이 확인해 줌 (내 감이 맞았다)
}

# 타입 자체가 갖는 상태이상 면역.
# **게임 설명문 어디에도 안 적혀 있다.** 본편 규칙을 가져다 쓴 것이라 전부 미확인이다.
# (특성으로 인한 면역은 설명문에 적혀 있어서 battle.py 가 직접 읽는다.)
STATUS_TYPE_IMMUNE = {
    "화상": ["불꽃"],
    "마비": ["전기"],
    "독":   ["독", "강철"],
    "맹독": ["독", "강철"],
    "얼음": ["얼음"],
}

# 실능 계산식은 실제 게임 화면으로 확인 완료 (2026-09-17).
#   한카리아스 / 성격 장난꾸러기 / 노력치 H32 B32 S2 (합 66)
#   -> 215 / 150 / 161 / 90 / 105 / 124  ... 6개 전부 일치
# 이때 입력한 값이 노력치뿐인데 전부 맞았으므로,
# 개체값은 없거나 전부 최대로 고정돼 있다는 것도 함께 확인됐다.
# 방어 (95+20+32)x1.1 = 161.7 -> 161 이므로 반올림이 아니라 '버림'인 것도 확정.

STAT_KO = {
    "hp": "HP", "attack": "공격", "defense": "방어",
    "spAtk": "특공", "spDef": "특방", "speed": "스피드",
}

# ---------------------------------------------------------------------------
# 데미지에 관여하는 특성.
# 게임 안의 설명문을 그대로 옮긴 것이고, 여기 없는 특성은 계산에 반영되지 않는다.
# (반영 안 되는 특성이 걸려 있으면 계산 결과에 경고를 띄운다.)
# ---------------------------------------------------------------------------
ATTACKER_ABILITY = {
    "천하장사":   {"kind": "physical_power", "mult": 2.0},
    "순수한힘":   {"kind": "physical_power", "mult": 2.0},
    "의욕":       {"kind": "attack_stat", "mult": 1.5},
    "근성":       {"kind": "status_attack", "mult": 1.5},
    "적응력":     {"kind": "stab", "value": 2.0},
    "테크니션":   {"kind": "weak_move", "max_power": 60, "mult": 1.5},
    "단단한발톱": {"kind": "contact", "mult": 1.3},
    "스나이퍼":   {"kind": "crit", "value": 2.25},
    "심록":       {"kind": "pinch", "type": "풀", "mult": 1.5},
    "맹화":       {"kind": "pinch", "type": "불꽃", "mult": 1.5},
    "급류":       {"kind": "pinch", "type": "물", "mult": 1.5},
    "벌레의알림": {"kind": "pinch", "type": "벌레", "mult": 1.5},
    "스카이스킨": {"kind": "skin", "type": "비행", "mult": 1.2},
    "프리즈스킨": {"kind": "skin", "type": "얼음", "mult": 1.2},
    "페어리스킨": {"kind": "skin", "type": "페어리", "mult": 1.2},
    "드래곤스킨": {"kind": "skin", "type": "드래곤", "mult": 1.2},
    # 기술 분류를 쓰는 것들 (moves.json 의 tags)
    "철주먹":     {"kind": "tag_power", "tag": "펀치", "mult": 1.2},
    "예리함":     {"kind": "tag_power", "tag": "베기", "mult": 1.5},
    "메가런처":   {"kind": "tag_power", "tag": "파동", "mult": 1.5},
    "옹골찬턱":   {"kind": "tag_power", "tag": "무는", "mult": 1.5},
    "펑크록":     {"kind": "tag_power", "tag": "소리", "mult": 1.3},
    # 특정 타입을 강화하는 것들
    "불꽃의갈기": {"kind": "type_power", "type": "불꽃", "mult": 1.5},
    "강철정신":   {"kind": "type_power", "type": "강철", "mult": 1.5},
    "페어리오라": {"kind": "type_power", "type": "페어리", "mult": 1.33},
    "수포":       {"kind": "type_power", "type": "물", "mult": 2.0},
    # 쓰는 기술의 타입으로 자기가 변한다 -> 무슨 기술을 써도 자속이 붙는다.
    # 마스카나(12위) 87.4%, 에이스번(20위) 98.5% 라 그냥 넘길 수 없다.
    "변환자재":   {"kind": "always_stab"},
    "리베로":     {"kind": "always_stab"},
}
# 방어측은 효과가 두 개인 특성이 있어서 목록으로 둔다 (예: 복슬복슬)
DEFENDER_ABILITY = {
    "두꺼운지방": [{"kind": "resist_types", "types": ["불꽃", "얼음"], "mult": 0.5}],
    "내열":       [{"kind": "resist_types", "types": ["불꽃"], "mult": 0.5}],
    "건조피부":   [{"kind": "resist_types", "types": ["불꽃"], "mult": 1.25}],
    "수포":       [{"kind": "resist_types", "types": ["불꽃"], "mult": 0.5}],
    "정화의소금": [{"kind": "resist_types", "types": ["고스트"], "mult": 0.5}],
    "필터":       [{"kind": "resist_super", "mult": 0.75}],
    "하드록":     [{"kind": "resist_super", "mult": 0.75}],
    "파동의방호": [{"kind": "resist_contact", "mult": 0.5}],
    "복슬복슬":   [{"kind": "resist_contact", "mult": 0.5},
                   {"kind": "resist_types", "types": ["불꽃"], "mult": 2.0}],
    "퍼코트":     [{"kind": "resist_category", "category": "물리", "mult": 0.5}],
    "펑크록":     [{"kind": "resist_tag", "tag": "소리", "mult": 0.5}],
    "멀티스케일": [{"kind": "resist_full_hp", "mult": 0.5}],
}
# 특성만으로 아예 안 맞는 경우. 이건 배율이 아니라 '무효'라서 따로 둔다.
# 빠뜨리면 결과가 조금 틀리는 게 아니라 완전히 틀리므로 반드시 챙길 것.
DEFENDER_IMMUNE = {
    "부유":       ["땅"],
    "천정부지":   ["땅"],
    "축전":       ["전기"],
    "피뢰침":     ["전기"],
    "저수":       ["물"],
    "건조피부":   ["물"],
    "초식":       ["풀"],
}
# 도구 때문에 아예 안 맞는 경우. **설명문에서 읽는다** — 새 도구가 나와도 따라온다.
#
# ! 이게 없어서 **풍선이 반만 돌았다** (2026-09-20에 고침).
#   `battle._grounded()` 가 압정 계산에서만 쓰이고 데미지 계산에는
#   안 닿아서, 풍선을 든 타부자고가 지진을 그대로 맞고 있었다.
#   타부자고는 사용률 9위이고 그중 66.2% 가 풍선이다. 재 보니
#   한카리아스(지진) vs 타부자고가 **풍선이 있든 없든 100%** 였다.
#   배율이 조금 틀리는 것이 아니라 **답이 통째로 뒤집히는** 종류였고,
#   `float` 이 `APPLIED_ITEM_KINDS` 에 있어서 경고조차 안 떴다.
_FLOAT_DESC = "땅 위에 있지 않게"


def floating_items(dex):
    """땅 기술이 안 통하게 만드는 도구 이름들. dex 하나당 한 번만 읽는다.

    ! `id(dex)` 를 열쇠로 쓰지 않는다 — 파이썬은 객체가 사라지면 그 id 를
      다시 내주므로 새 Dex 가 옛 Dex 의 표를 물려받는다. dex 에 직접 붙인다.
    """
    got = getattr(dex, "_floating_items", None)
    if got is None:
        got = set(it["name"] for it in dex.items
                  if _FLOAT_DESC in (it.get("description") or ""))
        dex._floating_items = got
    return got


# 기술 분류째로 안 맞는 특성
DEFENDER_IMMUNE_TAG = {
    "방음": "소리",
    "방탄": "구슬폭탄",
}
# 반대로 무효를 뚫는 특성
IGNORE_IMMUNE = {
    "배짱": {"move_types": ["노말", "격투"], "target_type": "고스트"},
}
# 계산에 반영 못 하는데 데미지에 영향은 주는 것들 (경고만 띄운다)
# 어느 쪽에 붙어 있을 때 의미가 있는지 표시해 둔다 ('공격' / '방어' / '양쪽')
UNSUPPORTED_SIDE = {
    "배틀스위치": "양쪽", "프레셔": "방어",
    "모래의힘": "공격", "선파워": "공격", "애널라이즈": "공격", "잠복": "공격",
    "이판사판": "공격", "투쟁심": "공격", "플러스": "공격", "마이너스": "공격",
    "까칠한피부": "방어", "탈": "방어", "옹골참": "방어", "지구력": "방어",
    "열교환": "방어", "이상한비늘": "방어", "풀모피": "방어",
    "곡예": "양쪽", "단순": "양쪽",
}
UNSUPPORTED_ABILITY = {
    "배틀스위치": "공격하면 블레이드폼, 킹실드를 쓰면 실드폼 — 폼에 따라 종족값이 바뀜",
    "프레셔": "상대 기술의 PP를 더 깎음 — PP 가 모델에 없음",
    "모래의힘": "모래바람일 때만 적용 — 날씨가 아직 계산에 없음",
    "이상한비늘": "상태 이상일 때 방어 1.5배 — 상대 상태이상 입력이 아직 없음",
    "풀모피": "그래스필드일 때 방어 1.5배 — 필드가 아직 계산에 없음",
    "선파워": "쾌청일 때 특공 1.5배 — 날씨가 아직 계산에 없음",
    "애널라이즈": "후공이면 위력 1.3배 — 선공/후공 판정이 아직 없음",
    "잠복": "교체로 나온 상대에게 위력 2배 — 대전 상황 정보가 없음",
    "이판사판": "반동 기술 위력 1.2배 — 반동 여부가 분류에 없음",
    "투쟁심": "성별에 따라 위력이 달라짐 — 성별 정보가 없음",
    "플러스": "같은 편이 있어야 발동 — 더블 전용",
    "마이너스": "같은 편이 있어야 발동 — 더블 전용",
    # 아래는 배율이 아니라 '한 번 막는' 종류라 데미지 숫자와 따로 봐야 한다
    "탈": "둔갑한 모습이면 첫 공격 데미지를 통째로 무효 — 아래 숫자는 탈이 벗겨진 뒤 기준",
    "옹골참": "HP가 꽉 차 있으면 한 방에 안 죽고 HP 1 남김",
    "지구력": "맞을 때마다 방어가 1단계 올라감 — 2타 이상은 계산보다 덜 들어감",
    "열교환": "불꽃 기술을 맞으면 공격이 1단계 올라감",
    "까칠한피부": "접촉 기술을 쓰면 공격한 쪽이 최대 HP의 1/8을 받음",
    "곡예": "도구가 없어지면 스피드 2배 — 스피드 판정에만 영향",
    "단순": "랭크 변화가 2배로 적용됨",
}
# 급소 관련 규칙은 기술 설명문에 그대로 적혀 있다.
#   "반드시 급소에 맞는다"  -> 무조건 급소
#   "급소업+1로 공격한다"   -> 급소 확률 한 단계 위
_ALWAYS_CRIT = re.compile(r"반드시 급소에 맞는다")
_CRIT_STAGE = re.compile(r"급소업\+?(\d)")


def move_crit(move):
    """이 기술의 급소 규칙. (항상 급소인가, 급소업 단계)."""
    d = move.get("description") or ""
    if _ALWAYS_CRIT.search(d):
        return True, 0
    m = _CRIT_STAGE.search(d)
    return False, int(m.group(1)) if m else 0


def crit_chance(move, extra_stage=0):
    """이 기술로 급소가 뜰 확률.

    extra_stage 는 도구·기술로 올라간 급소업 단계다 (초점렌즈 +1, 기충전 +2).
    """
    always, stage = move_crit(move)
    if always:
        return 1.0
    rates = CONFIG["crit_stage_rates"]
    return rates[min(stage + max(0, extra_stage), len(rates) - 1)]


# 노력치 배분 표기(A/B/C/D/S/H) -> 능력치 이름
SPREAD_KEY = {"H": "hp", "A": "attack", "B": "defense",
              "C": "spAtk", "D": "spDef", "S": "speed"}


# ---------------------------------------------------------------------------
# 데이터 읽기
# ---------------------------------------------------------------------------
def _load(name, required=True):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        if required:
            sys.exit("%s 가 없습니다. 먼저 build_data.py 를 실행하세요." % name)
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Dex(object):
    """데이터 묶음. 이름으로 찾는 기능까지 들고 있다."""

    def __init__(self):
        self.pokemon = _load("pokemon.json")
        self.moves = _load("moves.json")
        self.abilities = _load("abilities.json")
        self.items = _load("items.json")
        self.natures = _load("natures.json")
        self.learnsets = _load("learnsets.json")
        chart = _load("type_chart.json")
        self.types = chart["types"]
        self.chart = chart["chart"]

        usage = _load("usage_single.json", required=False)
        self.usage = {p["key"]: p for p in usage["pokemon"]} if usage else {}
        self.usage_season = usage.get("season") if usage else None

        self._by_key = {p["key"]: p for p in self.pokemon}
        self._move_by_name = {m["name"]: m for m in self.moves}
        self._move_by_id = {m["id"]: m for m in self.moves}
        self._nature_by_name = {n["name"]: n for n in self.natures}
        self.item_effects = self._parse_items()
        self.mega_by_item = self._parse_mega_stones()

    def _parse_mega_stones(self):
        """메가스톤 -> 그 도구로 바뀌는 폼.

        사용률은 기본 폼 기준으로 집계되고 메가는 '도구 채용률'로만 나타난다.
        그래서 '1위 도구가 메가스톤' 이면 그건 사실 메가로 싸운다는 뜻이다.
        이 표가 없으면 메가스톤을 든 기본 폼이라는, 실제로는 없는 몸으로 계산하게 된다.
        """
        import re
        by_name = {}
        for p in self.pokemon:
            by_name.setdefault(p["name"], []).append(p)
        megas = {}
        for p in self.pokemon:
            if p.get("isMega"):
                megas.setdefault(p["dexNo"], []).append(p)

        out = {}
        for it in self.items:
            d = it["description"]
            m = re.match(r"^(.+?)(?:이|가) 메가진화할 수 있게 되는 도구", d)
            if not m:
                continue
            # 메가가 둘인 포켓몬은 설명문 끝에 '(메가리자몽X)' 처럼 적혀 있다
            paren = re.search(r"\((메가[^)]+)\)", d)
            if paren:
                hit = [p for p in self.pokemon
                       if paren.group(1) in (p["formName"], p["name"])]
                if len(hit) == 1:
                    out[it["name"]] = hit[0]
                continue
            owner = m.group(1).split("(")[0].strip()
            cand = by_name.get(owner)
            if not cand:
                continue
            forms = megas.get(cand[0]["dexNo"], [])
            if len(forms) == 1:
                out[it["name"]] = forms[0]
        return out

    def _parse_items(self):
        """도구 설명문에서 데미지 배율을 읽어낸다.

        설명문이 규칙적이라 글에서 바로 뽑아낼 수 있다. 이렇게 해두면
        게임에 새 도구가 추가돼도 자동으로 따라온다.
        """
        import re
        fixed = {
            "생명의구슬": {"kind": "all", "mult": 1.3},
            "힘의머리띠": {"kind": "physical", "mult": 1.1},
            "박식안경":   {"kind": "special", "mult": 1.1},
            "달인의띠":   {"kind": "super_effective", "mult": 1.2},
        }
        out = dict(fixed)
        for it in self.items:
            if it["name"] in out:
                continue
            d = it["description"]
            m = re.match(r"^(.+?)타입 기술의 위력이 1\.2배", d)
            if m:
                out[it["name"]] = {"kind": "type_boost", "type": m.group(1),
                                   "mult": 1.2}
                continue
            m = re.match(r"^효과가 굉장한 (.+?)타입 기술을 받으면 데미지가 반감", d)
            if m:
                out[it["name"]] = {"kind": "resist_berry", "type": m.group(1),
                                   "mult": 0.5}
                continue
            if d.startswith("노말타입 기술을 받으면 데미지가 반감"):
                out[it["name"]] = {"kind": "resist_berry_always",
                                   "type": "노말", "mult": 0.5}
        return out

    # -- 찾기 ---------------------------------------------------------------
    def find_pokemon(self, text):
        """'보만다', '메가보만다', '0373-01' 다 받는다."""
        text = text.strip()
        if text in self._by_key:
            return self._by_key[text]
        exact_form = [p for p in self.pokemon if p["formName"] == text]
        if len(exact_form) == 1:
            return exact_form[0]
        base = [p for p in self.pokemon if p["name"] == text and p["formNo"] == 0]
        if base:
            return base[0]
        loose = [p for p in self.pokemon
                 if text in (p["name"], p["formName"]) or text in p["formName"]]
        if len(loose) == 1:
            return loose[0]
        if loose:
            raise LookupError("'%s' 은(는) 여러 개입니다: %s" % (
                text, ", ".join((p["formName"] or p["name"]) for p in loose[:8])))
        raise LookupError("'%s' 이라는 포켓몬을 못 찾았습니다." % text)

    def find_move(self, text):
        text = text.strip()
        if text in self._move_by_name:
            return self._move_by_name[text]
        loose = [m for m in self.moves if text in m["name"]]
        if len(loose) == 1:
            return loose[0]
        if loose:
            raise LookupError("'%s' 은(는) 여러 개입니다: %s" % (
                text, ", ".join(m["name"] for m in loose[:8])))
        raise LookupError("'%s' 이라는 기술을 못 찾았습니다." % text)

    def move_by_id(self, move_id):
        """사용률 데이터는 기술을 번호로 들고 있다. 이름보다 번호가 안전하다."""
        return self._move_by_id.get(move_id)

    def find_nature(self, text):
        if not text:
            return self._nature_by_name["노력"]      # 무보정
        if text in self._nature_by_name:
            return self._nature_by_name[text]
        raise LookupError("'%s' 이라는 성격을 못 찾았습니다." % text)

    def effectiveness(self, move_type, def_types):
        """기술 타입이 방어 타입들에게 갖는 최종 배율."""
        mult = 1.0
        for dt in def_types:
            mult *= self.chart.get(move_type, {}).get(dt, 1.0)
        return mult


# ---------------------------------------------------------------------------
# 실능 계산
# ---------------------------------------------------------------------------
def real_stat(base, sp, stat, nature=None):
    """레벨 50 기준 실제 능력치.

    HP   = 종족값 + 75 + 노력치
    그 외 = (종족값 + 20 + 노력치) x 성격보정   (소수점 버림)
    """
    if stat == "hp":
        return base + 75 + sp
    value = base + 20 + sp
    mod = 1.0
    if nature:
        mod = nature["modifiers"].get(stat, 1.0)
    return int(value * mod)        # 버림


RANK_TABLE = {}
for _n in range(-6, 7):
    RANK_TABLE[_n] = (2 + _n) / 2.0 if _n >= 0 else 2.0 / (2 - _n)


def base_form(dex, poke):
    """메가 폼을 원래(기본) 폼으로 되돌린다. 메가가 아니면 그대로.

    **메가진화는 한 게임에 한 번뿐이라** 파티에 메가스톤이 둘 이상 있어도
    실제로 메가가 되는 것은 하나다. 나머지는 스톤만 든 기본 폼으로 싸운다.
    그걸 되돌릴 때 쓴다 (`battle.Party` 가 부른다).
    """
    if not poke.get("isMega"):
        return poke
    same = [q for q in dex.pokemon
            if q["dexNo"] == poke["dexNo"] and not q.get("isMega")]
    return same[0] if same else poke


class Build(object):
    """실제로 싸우는 한 마리. 포켓몬 + 노력치 + 성격 + 상태."""

    def __init__(self, dex, poke, sp=None, nature=None, ranks=None,
                 item=None, ability=None, status=None, hp_ratio=1.0):
        self.dex = dex
        self.poke = poke
        self.sp = {k: 0 for k in STAT_KO}
        if sp:
            self.sp.update(sp)
        self.nature = nature
        self.ranks = {k: 0 for k in STAT_KO}
        if ranks:
            self.ranks.update(ranks)
        self.item = item
        self.ability = ability or (poke["abilities"][0]["name"]
                                   if poke["abilities"] else None)
        self.status = status          # '화상' 등
        self.hp_ratio = hp_ratio      # 남은 HP 비율 (심록·맹화 같은 특성용)

    @property
    def name(self):
        base = self.poke["name"]
        form = self.poke["formName"]
        if not form:
            return base
        if base in form:          # '메가보만다' 처럼 이름이 이미 들어있으면 그대로
            return form
        return "%s(%s)" % (base, form)

    @property
    def types(self):
        return self.poke["types"]

    def stat(self, key, with_rank=True):
        v = real_stat(self.poke["baseStats"][key], self.sp.get(key, 0),
                      key, self.nature)
        if with_rank and key != "hp":
            v = int(v * RANK_TABLE[self.ranks.get(key, 0)])
        return v

    def sp_total(self):
        return sum(self.sp.values())

    def describe(self):
        inv = ["%s%d" % (STAT_KO[k], v) for k, v in self.sp.items() if v]
        return "%s | %s | 성격 %s | 노력치 %s(합%d)%s" % (
            self.name, "/".join(self.types),
            self.nature["name"] if self.nature else "무보정",
            " ".join(inv) if inv else "없음", self.sp_total(),
            " | 도구 %s" % self.item if self.item else "")


# ---------------------------------------------------------------------------
# 데미지 계산
# ---------------------------------------------------------------------------
def calc_damage(dex, attacker, defender, move, critical=False,
                stab=None, extra=1.0):
    """한 번 때렸을 때의 데미지를 계산한다.

    돌려주는 값에 최소/최대 데미지, HP 대비 비율, 확정 몇 타인지가 들어있다.
    """
    if move["category"] == "변화":
        return {"error": "'%s' 은(는) 변화기라서 데미지가 없습니다." % move["name"]}

    power = move["power"]
    if power <= 0:
        return {"error": "'%s' 은(는) 위력이 정해져 있지 않습니다." % move["name"]}

    notes = []
    warnings = []
    move_type = move["type"]
    power = float(power)

    a_ab = ATTACKER_ABILITY.get(attacker.ability)
    d_ab = DEFENDER_ABILITY.get(defender.ability)
    for who, ab_name in (("공격", attacker.ability), ("방어", defender.ability)):
        if ab_name not in UNSUPPORTED_ABILITY:
            continue
        side = UNSUPPORTED_SIDE.get(ab_name, "양쪽")
        if side not in (who, "양쪽"):
            continue          # 그쪽에 붙어 있어도 의미 없는 특성이면 조용히 넘어간다
        warnings.append("%s측 특성 '%s' 는 계산에 안 들어갔습니다 (%s)"
                        % (who, ab_name, UNSUPPORTED_ABILITY[ab_name]))

    # 노말 기술의 타입을 바꾸는 특성 (스카이스킨 등) — 타입 판정 전에 처리
    if a_ab and a_ab["kind"] == "skin" and move_type == "노말":
        move_type = a_ab["type"]
        power *= a_ab["mult"]
        notes.append("%s: 노말 → %s, 위력 1.2배"
                     % (attacker.ability, a_ab["type"]))

    if move["category"] == "물리":
        atk_key, def_key = "attack", "defense"
    else:
        atk_key, def_key = "spAtk", "spDef"

    # 급소는 자신에게 불리한 랭크를 무시한다 (본편 규칙, 챔피언스 미확인)
    a_rank = attacker.ranks.get(atk_key, 0)
    d_rank = defender.ranks.get(def_key, 0)
    a = attacker.stat(atk_key, with_rank=not (critical and a_rank < 0))
    if a_ab and a_ab["kind"] == "attack_stat" and move["category"] == "물리":
        a = int(a * a_ab["mult"])
        notes.append("%s: 공격 %.1f배 (명중률은 0.8배)"
                     % (attacker.ability, a_ab["mult"]))
    if (a_ab and a_ab["kind"] == "status_attack" and move["category"] == "물리"
            and attacker.status):
        a = int(a * a_ab["mult"])
        notes.append("%s: 상태 이상이라 공격 %.1f배"
                     % (attacker.ability, a_ab["mult"]))
    d = defender.stat(def_key, with_rank=not (critical and d_rank > 0))
    hp = defender.stat("hp")

    # --- 위력에 붙는 보정들 ---
    if a_ab:
        k = a_ab["kind"]
        if k == "physical_power" and move["category"] == "물리":
            power *= a_ab["mult"]
            notes.append("%s: 물리 위력 %.1f배" % (attacker.ability, a_ab["mult"]))
        elif k == "weak_move" and move["power"] <= a_ab["max_power"]:
            power *= a_ab["mult"]
            notes.append("%s: 위력 60 이하라 %.1f배"
                         % (attacker.ability, a_ab["mult"]))
        elif k == "contact" and move["isContact"]:
            power *= a_ab["mult"]
            notes.append("%s: 접촉 기술이라 %.1f배"
                         % (attacker.ability, a_ab["mult"]))
        elif k == "pinch" and move_type == a_ab["type"] and attacker.hp_ratio <= 1 / 3.0:
            power *= a_ab["mult"]
            notes.append("%s: HP 1/3 이하라 %s 기술 %.1f배"
                         % (attacker.ability, a_ab["type"], a_ab["mult"]))
        elif k == "tag_power" and a_ab["tag"] in (move.get("tags") or []):
            power *= a_ab["mult"]
            notes.append("%s: %s 기술이라 %.2f배"
                         % (attacker.ability, a_ab["tag"], a_ab["mult"]))
        elif k == "type_power" and move_type == a_ab["type"]:
            power *= a_ab["mult"]
            notes.append("%s: %s 기술 %.2f배"
                         % (attacker.ability, a_ab["type"], a_ab["mult"]))

    # 특성으로 아예 안 맞는 경우
    immune = DEFENDER_IMMUNE.get(defender.ability)
    if immune and move_type in immune:
        return {"error": "%s 의 특성 '%s' 때문에 %s 타입 기술은 통하지 않습니다." % (
            defender.name, defender.ability, move_type)}
    tag_immune = DEFENDER_IMMUNE_TAG.get(defender.ability)
    if tag_immune and tag_immune in (move.get("tags") or []):
        return {"error": "%s 의 특성 '%s' 때문에 %s 기술은 통하지 않습니다." % (
            defender.name, defender.ability, tag_immune)}

    # 도구로 떠 있는 경우 (풍선). 터지면 `Side.as_build` 가 item 을 None 으로
    # 넘기므로 여기까지 안 온다.
    if move_type == "땅" and defender.item in floating_items(dex):
        return {"error": "%s 이(가) %s 으로 떠 있어 땅 타입 기술은 통하지 "
                         "않습니다." % (defender.name, defender.item)}

    eff = dex.effectiveness(move_type, defender.types)
    if eff == 0:
        bypass = IGNORE_IMMUNE.get(attacker.ability)
        if (bypass and move_type in bypass["move_types"]
                and bypass["target_type"] in defender.types):
            # 배짱: 고스트에게도 노말·격투가 통한다. 남은 타입으로만 다시 계산.
            rest = [t for t in defender.types if t != bypass["target_type"]]
            eff = dex.effectiveness(move_type, rest) if rest else 1.0
            notes.append("%s: 고스트 무효를 무시" % attacker.ability)
        if eff == 0:
            return {"error": "%s 에게 %s 타입은 효과가 없습니다." % (
                defender.name, move_type)}

    # 공격측 도구
    ai = dex.item_effects.get(attacker.item) if attacker.item else None
    if ai:
        k = ai["kind"]
        if (k == "all"
                or (k == "physical" and move["category"] == "물리")
                or (k == "special" and move["category"] == "특수")
                or (k == "type_boost" and ai.get("type") == move_type)
                or (k == "super_effective" and eff > 1)):
            power *= ai["mult"]
            notes.append("%s: 위력 %.1f배" % (attacker.item, ai["mult"]))

    level = CONFIG["level"]
    base = math.floor(math.floor(math.floor(2 * level / 5 + 2)
                                 * math.floor(power) * a / d) / 50) + 2

    if stab is None:
        stab = CONFIG["stab"] if move_type in attacker.types else 1.0
        # 변환자재·리베로 — 쓰는 기술의 타입이 되므로 무슨 기술이든 자속이 붙는다
        if a_ab and a_ab["kind"] == "always_stab" and stab == 1.0:
            stab = CONFIG["stab"]
            notes.append("%s: %s 타입이 되어 자속 %.1f배"
                         % (attacker.ability, move_type, stab))
        if a_ab and a_ab["kind"] == "stab" and stab > 1:
            stab = a_ab["value"]
            notes.append("%s: 자속이 2배" % attacker.ability)

    burn = 1.0
    if attacker.status == "화상" and move["category"] == "물리":
        burn = CONFIG["burn_physical"]

    crit = CONFIG["critical"] if critical else 1.0
    if critical and a_ab and a_ab["kind"] == "crit":
        crit = a_ab["value"]
        notes.append("%s: 급소 배율 %.2f배" % (attacker.ability, crit))

    # 방어측 특성·도구
    guard = 1.0
    for ef in (d_ab or []):
        k = ef["kind"]
        hit = False
        if k == "resist_types" and move_type in ef["types"]:
            hit = True
            label = "%s 기술" % move_type
        elif k == "resist_super" and eff > 1:
            hit = True
            label = "효과 굉장한 기술"
        elif k == "resist_contact" and move["isContact"]:
            hit = True
            label = "접촉 기술"
        elif k == "resist_category" and move["category"] == ef["category"]:
            hit = True
            label = "%s 기술" % ef["category"]
        elif k == "resist_tag" and ef["tag"] in (move.get("tags") or []):
            hit = True
            label = "%s 기술" % ef["tag"]
        elif k == "resist_full_hp" and defender.hp_ratio >= 1.0:
            hit = True
            label = "HP가 꽉 차 있어서"
        if hit:
            guard *= ef["mult"]
            notes.append("%s: %s %s" % (
                defender.ability, label,
                "%.2f배" % ef["mult"] if ef["mult"] != 0.5 else "반감"))
    di = dex.item_effects.get(defender.item) if defender.item else None
    if di:
        if (di["kind"] == "resist_berry" and di["type"] == move_type and eff > 1) or            (di["kind"] == "resist_berry_always" and di["type"] == move_type):
            guard *= di["mult"]
            notes.append("%s: 데미지 반감 (1회용)" % defender.item)

    # 난수 16단계. **본편처럼 단계마다 버림한다** — 곱을 한 번에 하면
    # 값이 달라진다.
    #
    # ! 여기가 제일 뜨거운 자리다. 3대3 한 판에 calc_damage 가 698번
    #   불리고, 이 고리가 한 번에 16 x 7 = 112번 돈다. 그래서 두 가지만
    #   손봤다 — 둘 다 **결과를 바꾸지 않는다.**
    #     · math.floor 를 지역 이름으로 묶는다 (속성 찾기를 없앤다)
    #     · 배율이 정확히 1.0 인 단계는 건너뛴다.
    #       dmg 는 이미 정수라 floor(정수 x 1.0) == 정수 다.
    #   무작위 6만 경우로 옛 코드와 대조해서 **전부 같음**을 확인했다.
    floor = math.floor
    chain = [m for m in (crit, stab, eff, burn, guard, extra) if m != 1.0]
    rolls = []
    for r in range(CONFIG["random_min"], CONFIG["random_max"] + 1):
        dmg = floor(base * r / 100)
        for m in chain:
            dmg = floor(dmg * m)
        rolls.append(1 if dmg < 1 else dmg)

    lo, hi = min(rolls), max(rolls)
    ko1 = sum(1 for x in rolls if x >= hp) / len(rolls)

    # 몇 번 때려야 쓰러지는지
    need_min = math.ceil(hp / hi) if hi else 999      # 가장 운 좋을 때
    need_max = math.ceil(hp / lo) if lo else 999      # 가장 운 나쁠 때

    return {
        "move": move, "moveType": move_type, "power": math.floor(power),
        "notes": notes, "warnings": warnings, "attack": a, "defense": d, "hp": hp,
        "effectiveness": eff, "stab": stab, "critical": crit, "burn": burn,
        "rolls": rolls, "min": lo, "max": hi,
        "minPct": lo * 100.0 / hp, "maxPct": hi * 100.0 / hp,
        "ohkoChance": ko1, "hitsMin": need_min, "hitsMax": need_max,
    }


def verdict(res):
    """'확정 2타' 처럼 사람이 읽을 결론."""
    if res["ohkoChance"] >= 1.0:
        return "확정 1타"
    if res["ohkoChance"] > 0:
        return "난수 1타 (%.1f%%)" % (res["ohkoChance"] * 100)
    if res["hitsMin"] == res["hitsMax"]:
        return "확정 %d타" % res["hitsMax"]
    return "난수 %d타 (최악이면 %d타)" % (res["hitsMin"], res["hitsMax"])


EFF_KO = {0.25: "효과가 별로 (4배 반감)", 0.5: "효과가 별로 (반감)",
          1.0: "보통", 2.0: "효과가 굉장함 (2배)", 4.0: "효과가 굉장함 (4배)"}


def report(dex, attacker, defender, res):
    if "error" in res:
        return "  " + res["error"]
    m = res["move"]
    lines = [
        "  %s  →  %s" % (attacker.name, defender.name),
        "  기술: %s (%s %s 위력%d)" % (
            m["name"],
            m["type"] if res["moveType"] == m["type"]
            else "%s→%s" % (m["type"], res["moveType"]),
            m["category"], res["power"]),
        "  상성: %s  /  자속 %s" % (
            EFF_KO.get(res["effectiveness"], "x%g" % res["effectiveness"]),
            "있음" if res["stab"] > 1 else "없음"),
        "  공격 %d  vs  방어 %d   상대 HP %d" % (res["attack"], res["defense"], res["hp"]),
        "",
        "  데미지  %d ~ %d   (HP의 %.1f%% ~ %.1f%%)" % (
            res["min"], res["max"], res["minPct"], res["maxPct"]),
        "  결론    %s" % verdict(res),
    ]
    for n in res.get("notes") or []:
        lines.append("  · %s" % n)
    for w in res.get("warnings") or []:
        lines.append("  ! %s" % w)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 실전 기본값 — 사용률 1위 성격/노력치/도구를 그대로 쓴다
# ---------------------------------------------------------------------------
def popular_build(dex, poke, verbose=False):
    """그 포켓몬을 실제로 사람들이 쓰는 모습으로 만든다."""
    u = dex.usage.get(poke["key"])
    if not u:
        # 메가는 사용률이 기본 폼에 잡힌다
        u = dex.usage.get("%04d-00" % poke["dexNo"])
    if not u:
        return Build(dex, poke), "사용률 데이터 없음 — 노력치 0, 무보정으로 계산"

    nature = None
    if u.get("natures"):
        try:
            nature = dex.find_nature(u["natures"][0]["name"])
        except LookupError:
            pass
    sp = {}
    if u.get("evs"):
        for k, v in u["evs"][0]["spread"].items():
            if k in SPREAD_KEY:
                sp[SPREAD_KEY[k]] = v
    item = u["items"][0]["name"] if u.get("items") else None
    item_pct = u["items"][0]["pct"] if u.get("items") else None

    # 1위 도구가 이 포켓몬의 메가스톤이면, 실제로는 메가로 싸운다는 뜻이다.
    # (사용률은 기본 폼 기준으로 집계되므로 메가는 도구 채용률로만 드러난다.)
    mega_note = None
    mega = dex.mega_by_item.get(item)
    if mega and not poke.get("isMega") and mega["dexNo"] == poke["dexNo"]:
        mega_note = "%s 채용률 %.1f%% — 메가로 보고 계산한다 (나머지 %.1f%% 는 기본 폼)" % (
            item, item_pct, 100.0 - item_pct)
        poke = mega

    # 사용률은 기본 폼 기준이라 특성도 기본 폼 것이 들어있다.
    # 메가처럼 특성이 하나로 고정된 폼은 그 폼의 특성을 써야 한다.
    own = [a["name"] for a in poke["abilities"]]
    if len(own) == 1:
        ability = own[0]
    else:
        ability = None
        for cand in (u.get("abilities") or []):
            if cand["name"] in own:
                ability = cand["name"]
                break
        if ability is None:
            ability = own[0] if own else None

    note = "실전 1위 배분: 성격 %s / %s / 도구 %s" % (
        nature["name"] if nature else "?",
        u["evs"][0]["name"] if u.get("evs") else "?",
        item or "?")
    if mega_note:
        note += "\n        ! " + mega_note
    return Build(dex, poke, sp=sp, nature=nature, item=item,
                 ability=ability), note


# ---------------------------------------------------------------------------
# 명령줄 / 대화식
# ---------------------------------------------------------------------------
def quick(dex, atk_name, move_name, def_name):
    atk_poke = dex.find_pokemon(atk_name)
    def_poke = dex.find_pokemon(def_name)
    move = dex.find_move(move_name)

    atk, atk_note = popular_build(dex, atk_poke)
    dfn, def_note = popular_build(dex, def_poke)

    print("=" * 62)
    print("  공격: " + atk.describe())
    print("        " + atk_note)
    print("  방어: " + dfn.describe())
    print("        " + def_note)
    print("-" * 62)
    res = calc_damage(dex, atk, dfn, move)
    print(report(dex, atk, dfn, res))
    if "error" not in res:
        crit = calc_damage(dex, atk, dfn, move, critical=True)
        print("  급소면  %d ~ %d   (%.1f%% ~ %.1f%%)  →  %s" % (
            crit["min"], crit["max"], crit["minPct"], crit["maxPct"], verdict(crit)))
    print("=" * 62)

    # 배울 수 있는 기술인지 확인
    learn = dex.learnsets.get(atk_poke["key"], [])
    if move["id"] not in learn:
        print("  ! 참고: %s 는 '%s' 를 배우지 못합니다." % (atk.name, move["name"]))


def interactive(dex):
    print("=" * 62)
    print("  포켓몬 챔피언스 데미지 계산기")
    print("  포켓몬 %d / 기술 %d / 사용률 시즌 %s"
          % (len(dex.pokemon), len(dex.moves), dex.usage_season or "없음"))
    print("  그냥 엔터를 누르면 종료합니다.")
    print("=" * 62)
    while True:
        try:
            a = input("\n공격하는 포켓몬: ").strip()
            if not a:
                return
            m = input("사용할 기술    : ").strip()
            if not m:
                return
            d = input("맞는 포켓몬    : ").strip()
            if not d:
                return
            print()
            quick(dex, a, m, d)
        except LookupError as e:
            print("  ! %s" % e)
        except (EOFError, KeyboardInterrupt):
            return


def main():
    paths.fix_console()   # 윈도우에서 한글을 찍다 죽지 않게
    dex = Dex()
    args = sys.argv[1:]
    if len(args) == 3:
        try:
            quick(dex, args[0], args[1], args[2])
        except LookupError as e:
            print("! %s" % e)
    elif args:
        print("사용법: python calc.py <공격 포켓몬> <기술> <방어 포켓몬>")
        print("   예 : python calc.py 메가보만다 이판사판태클 하마돈")
    else:
        interactive(dex)


if __name__ == "__main__":
    main()
