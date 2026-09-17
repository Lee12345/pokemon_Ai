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

import random
import re
import sys

import best
import calc

# ---------------------------------------------------------------------------
# 능력치 이름 — 게임 설명문의 표기를 우리 키로 옮긴다
# ---------------------------------------------------------------------------
STAT_WORD = {
    "공격": "attack", "방어": "defense", "특수공격": "spAtk",
    "특수방어": "spDef", "스피드": "speed",
}

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
STATUS_DONE = {"화상", "마비", "독"}

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
}
# 한 번은 통째로 버티는 특성. 데미지 배율이 아니라 별도 규칙이라 여기 둔다.
DISGUISE = "탈"          # 따라큐(11위) 100% — 첫 공격을 무효로 하고 최대 HP의 1/8 소모
ENDURE_FULL = "옹골참"   # HP가 꽉 차 있으면 한 방에 안 죽고 1 남는다


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


def move_recoil(move):
    """반동으로 자신이 받는 비율. 없으면 0."""
    m = _RECOIL.search(move.get("description") or "")
    return 1.0 / int(m.group(1)) if m else 0.0


# ---------------------------------------------------------------------------
# 대전 중 한 마리의 상태
# ---------------------------------------------------------------------------
class Side(object):
    """`calc.Build` 는 그대로 두고, 대전 중 변하는 것만 여기 담는다.

    끝났을 때 이 객체가 그대로 '다음 포켓몬 상대의 시작 상태' 가 된다.
    """

    def __init__(self, dex, build):
        self.dex = dex
        self.base = build
        self.max_hp = build.stat("hp")
        self.hp = self.max_hp
        self.ranks = dict(build.ranks)
        self.status = build.status
        self.item = build.item
        self.item_used = False
        self.protecting = False
        # 따라큐의 탈. 첫 공격을 한 번 통째로 막는다.
        self.disguise = (build.ability == DISGUISE)

    @property
    def name(self):
        return self.base.name

    @property
    def alive(self):
        return self.hp > 0

    @property
    def hp_ratio(self):
        return self.hp / float(self.max_hp)

    def as_build(self):
        """지금 상태를 반영한 Build. 데미지 계산기에 그대로 넣을 수 있다."""
        return calc.Build(
            self.dex, self.base.poke, sp=self.base.sp, nature=self.base.nature,
            ranks=self.ranks, item=None if self.item_used else self.item,
            ability=self.base.ability, status=self.status,
            hp_ratio=self.hp_ratio)

    def bump(self, stat, step):
        """랭크 변화. 위아래로 6이 한계다."""
        before = self.ranks.get(stat, 0)
        after = max(-6, min(6, before + step))
        self.ranks[stat] = after
        return after - before        # 실제로 움직인 칸수

    def damage(self, amount, direct=True):
        """데미지를 넣는다. 기합의띠·옹골참이 있으면 여기서 버틴다.

        direct=False 는 반동·칩 데미지처럼 '기술로 맞은 것' 이 아닌 경우다.
        기합의띠와 옹골참은 그때는 안 버틴다.
        """
        note = None
        if direct and amount >= self.hp and self.hp == self.max_hp:
            if self.base.ability == ENDURE_FULL:
                amount = self.hp - 1
                note = "옹골참으로 HP 1 남기고 버팀"
            elif self.item == "기합의띠" and not self.item_used:
                amount = self.hp - 1
                self.item_used = True
                note = "기합의띠로 HP 1 남기고 버팀"
        self.hp = max(0, self.hp - amount)
        return note

    def heal(self, amount):
        amount = int(amount)
        before = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        return self.hp - before

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
            "alive": self.alive,
        }


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

    def __init__(self, dex, me_build, opp_build, rng=None, log=False):
        self.dex = dex
        self.me = Side(dex, me_build)
        self.opp = Side(dex, opp_build)
        self.field = Field()
        self.rng = rng or random.Random()
        self.turn = 0
        self.log = [] if log else None
        self.warnings = []
        self._entry_weather()

    def _say(self, text):
        if self.log is not None:
            self.log.append("%2d턴  %s" % (self.turn, text))

    def _warn(self, text):
        if text not in self.warnings:
            self.warnings.append(text)

    def _entry_weather(self):
        """등장만으로 날씨를 까는 특성. 상위권에 99.8% 로 깔려 있다."""
        for side, who in ((self.me, "나"), (self.opp, "상대")):
            w = WEATHER_ABILITY.get(side.base.ability)
            if w:
                self.field.set(w)
                self._say("%s(%s) 등장 — %s" % (side.name, side.base.ability, w))

    # -- 데미지 -------------------------------------------------------------
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
        return mult

    def _hit(self, atk, dfn, move, who):
        """공격기 한 방. 실제로 들어간 데미지를 돌려준다."""
        if dfn.protecting:
            self._say("%s 의 %s — 막혔다" % (atk.name, move["name"]))
            return 0

        acc = move.get("accuracy")
        if acc is not None and acc <= 100 and self.rng.random() > acc / 100.0:
            self._say("%s 의 %s — 빗나감 (명중 %d%%)" % (atk.name, move["name"], acc))
            return 0

        crit = self.rng.random() < calc.CONFIG["crit_rate"]
        extra = self._power_scale(move, atk)
        res = calc.calc_damage(self.dex, atk.as_build(), dfn.as_build(), move,
                               critical=crit, extra=extra)
        if "error" in res:
            self._say("%s 의 %s — %s" % (atk.name, move["name"], res["error"]))
            return 0

        dmg = self.rng.choice(res["rolls"])

        # 따라큐의 탈 — 데미지를 통째로 막고 최대 HP의 1/8 만 잃는다
        if dfn.disguise and dmg > 0:
            dfn.disguise = False
            lost = max(1, dfn.max_hp // 8)
            dfn.damage(lost, direct=False)
            self._say("%s 의 탈이 벗겨졌다 — 데미지 무효, %d 만 잃음 (HP %d/%d)"
                      % (dfn.name, lost, dfn.hp, dfn.max_hp))
            self._pinch_berry(dfn)
            return 0

        note = dfn.damage(dmg)
        self._say("%s 의 %s → %s 에게 %d (HP %d/%d)%s%s"
                  % (atk.name, move["name"], dfn.name, dmg, dfn.hp, dfn.max_hp,
                     "  급소!" if crit else "",
                     "  · " + note if note else ""))

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
            elif ab["kind"] == "contact_recoil" and move["isContact"]:
                back = max(1, int(atk.max_hp * ab["frac"]))
                atk.damage(back, direct=False)
                self._say("%s 의 %s — %s 가 %d (HP %d/%d)"
                          % (dfn.name, dfn.base.ability, atk.name, back,
                             atk.hp, atk.max_hp))

        # 반동
        rec = move_recoil(move)
        if rec and dmg:
            back = max(1, int(dmg * rec))
            atk.damage(back, direct=False)
            self._say("%s 반동 %d (HP %d/%d)" % (atk.name, back, atk.hp, atk.max_hp))
        # 생명의구슬
        if atk.item == "생명의구슬" and not atk.item_used:
            atk.damage(max(1, atk.max_hp // 10), direct=False)
            self._say("생명의구슬 반동 %d" % max(1, atk.max_hp // 10))

        # 데미지 계산기가 '이 특성은 못 넣었다' 고 한 것들을 그대로 올린다
        for w in res.get("warnings") or []:
            self._warn(w)

        # 기술에 붙은 특수 규칙은 경고로만.
        # 날씨·필드는 여기서 실제로 계산하므로 그 경고는 뺀다.
        for c in best.move_caveats(move):
            if "날씨·필드" in c:
                continue
            self._warn("%s: %s" % (move["name"], c))
        self._pinch_berry(dfn)
        return dmg

    def _pinch_berry(self, side):
        """자뭉열매처럼 반피에서 터지는 열매. 상위권 1위 도구가 이거다."""
        if side.item_used or not side.item or not side.alive:
            return
        it = [i for i in self.dex.items if i["name"] == side.item]
        if not it:
            return
        m = re.search(r"최대 HP의 1/2 이하가 되었을 때 최대 HP의 1/(\d+)만큼 회복",
                      it[0]["description"])
        if m and side.hp <= side.max_hp // 2:
            got = side.heal(side.max_hp / float(int(m.group(1))))
            side.item_used = True
            self._say("%s 의 %s 발동 — %d 회복 (HP %d/%d)"
                      % (side.name, side.item, got, side.hp, side.max_hp))

    # -- 변화기 -------------------------------------------------------------
    def _use_status(self, user, target, move):
        for ef in move_effects(move):
            k = ef["kind"]
            if k == "rank":
                side = user if ef["who"] == "self" else target
                if side is target and target.protecting:
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
                    continue
                got = user.heal(user.max_hp * ef["frac"])
                if ef.get("cure"):
                    user.status = None
                self._say("%s 의 %s — %d 회복 (HP %d/%d)"
                          % (user.name, move["name"], got, user.hp, user.max_hp))
            elif k == "self_status":
                user.status = ef["status"]
                self._say("%s 는 %s 상태가 됐다" % (user.name, ef["status"]))
                if ef["status"] not in STATUS_DONE:
                    self._warn("'%s' 상태의 효과는 아직 계산에 없습니다 (이름만 붙습니다)"
                               % ef["status"])
            elif k == "status":
                if target.protecting:
                    continue
                if target.status:
                    self._say("%s 는 이미 %s 상태" % (target.name, target.status))
                    continue
                target.status = ef["status"]
                self._say("%s 를 %s 상태로" % (target.name, ef["status"]))
                if ef["status"] not in STATUS_DONE:
                    self._warn("'%s' 상태의 효과는 아직 계산에 없습니다 (이름만 붙습니다)"
                               % ef["status"])
            elif k == "protect":
                user.protecting = True
                self._say("%s 의 %s — 이 턴은 막는다" % (user.name, move["name"]))
            elif k == "weather":
                self.field.set(ef["weather"])
                self._say("%s 의 %s — %s" % (user.name, move["name"], ef["weather"]))
            elif k == "phaze":
                self._say("%s 의 %s — 바꿀 포켓몬이 없어 실패 (파티는 5단계)"
                          % (user.name, move["name"]))
                self._warn("'%s' 는 상대를 강제로 교체시키는 기술입니다. "
                           "1대1 에서는 실패 처리되지만 실전에서는 "
                           "쌓아 놓은 랭크가 전부 날아갑니다." % move["name"])
            elif k == "hazard":
                self._say("%s 의 %s — 1대1 에서는 효과가 없다 (교체가 없음)"
                          % (user.name, move["name"]))
                self._warn("'%s' 는 교체가 있어야 값어치가 나옵니다 (5단계)"
                           % move["name"])
            else:
                self._say("%s 의 %s — 효과를 아직 모른다" % (user.name, move["name"]))
                self._warn("'%s' 의 효과를 설명문에서 못 읽었습니다" % move["name"])

    # -- 한 턴 --------------------------------------------------------------
    def _act(self, actor, target, move):
        if not actor.alive:
            return
        if actor.status == "마비" and self.rng.random() < calc.CONFIG["paralysis_skip"]:
            self._say("%s 는 몸이 저려 움직이지 못했다" % actor.name)
            return
        if move["category"] == "변화":
            self._use_status(actor, target, move)
        else:
            self._hit(actor, target, move, None)

    def step(self, my_move, opp_move):
        """한 턴 진행."""
        self.turn += 1
        self.me.protecting = False
        self.opp.protecting = False

        order = best.turn_order(self.dex, self.me.as_build(), my_move,
                                self.opp.as_build(), opp_move)
        first = order["first"]
        if first == "동시":
            first = "나" if self.rng.random() < 0.5 else "상대"
        seq = [(self.me, self.opp, my_move), (self.opp, self.me, opp_move)]
        if first == "상대":
            seq.reverse()

        for actor, target, move in seq:
            if not (self.me.alive and self.opp.alive):
                break
            self._act(actor, target, move)

        if self.me.alive and self.opp.alive:
            self._end_of_turn()

    def _end_of_turn(self):
        """턴 끝 — 상태이상 · 날씨 칩댐 · 먹다남은음식."""
        for side in (self.me, self.opp):
            if not side.alive:
                continue
            if side.status == "화상":
                side.damage(max(1, side.max_hp // calc.CONFIG["burn_chip"]))
                self._say("%s 화상 데미지 (HP %d/%d)" % (side.name, side.hp, side.max_hp))
            elif side.status == "독":
                side.damage(max(1, side.max_hp // calc.CONFIG["poison_chip"]))
                self._say("%s 독 데미지 (HP %d/%d)" % (side.name, side.hp, side.max_hp))

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

        for text in self.field.tick():
            self._say(text)


# ---------------------------------------------------------------------------
# 계획을 돌려 본다
# ---------------------------------------------------------------------------
MAX_TURNS = 30           # 서로 못 죽이면 여기서 끊는다

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


def run_once(dex, me_build, opp_build, my_plan, opp_plan, rng, log=False):
    """한 판. 끝났을 때의 상태를 통째로 돌려준다."""
    b = Battle(dex, me_build, opp_build, rng=rng, log=log)
    for i in range(MAX_TURNS):
        if not (b.me.alive and b.opp.alive):
            break
        b.step(_pick(my_plan, i), _pick(opp_plan, i))
    if b.me.alive and not b.opp.alive:
        result = "이김"
    elif b.opp.alive and not b.me.alive:
        result = "짐"
    elif not b.me.alive and not b.opp.alive:
        result = "동시에 쓰러짐"
    else:
        result = "안 끝남"
    return {"result": result, "turns": b.turn,
            "me": b.me.snapshot(), "opp": b.opp.snapshot(),
            "log": b.log, "warnings": b.warnings,
            "weather": b.field.weather, "terrain": b.field.terrain}


def evaluate(dex, me_build, opp_build, my_plan, opp_plan, trials=400, seed=7):
    """같은 계획을 여러 번 돌려 승률과 '평균적으로 어떤 상태로 끝나는지' 를 낸다.

    난수(데미지 16단계 · 명중 · 급소 · 마비)가 있으므로 한 판만 봐서는 안 된다.
    """
    rng = random.Random(seed)
    wins = 0
    turns = hp = 0.0
    ranks = {}
    counts = {}
    warnings = []
    for _ in range(trials):
        r = run_once(dex, me_build, opp_build, my_plan, opp_plan, rng)
        counts[r["result"]] = counts.get(r["result"], 0) + 1
        if r["result"] == "이김":
            wins += 1
            hp += r["me"]["hpPct"]
            for k, v in r["me"]["ranks"].items():
                ranks[k] = ranks.get(k, 0.0) + v
        turns += r["turns"]
        for w in r["warnings"]:
            if w not in warnings:
                warnings.append(w)
    avg_hp = (hp / wins) if wins else 0.0
    avg_ranks = {k: v / wins for k, v in ranks.items()} if wins else {}
    # 이기고 나서 남는 몸을 한 숫자로. 후속 포켓몬에게 이어지는 값어치다.
    carry = avg_hp + sum(avg_ranks.values()) * RANK_VALUE
    return {
        "plan": [m["name"] for m in my_plan],
        "winRate": wins / float(trials),
        "avgTurns": turns / float(trials),
        # 이겼을 때 평균적으로 어떤 몸으로 남는가 — 후속 포켓몬에게 그대로 이어진다
        "avgHpPctWhenWin": avg_hp,
        "avgRanksWhenWin": avg_ranks,
        "carry": carry,
        "counts": counts, "trials": trials, "warnings": warnings,
    }


def build_plans(dex, me_build, opp_build, my_moves=None):
    """비교해 볼 계획들을 만든다.

    ① 공격기 하나만 계속  ② 변화기 한 번 쓰고 그 공격기  ③ 변화기 두 번
    """
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


def report(dex, me_build, opp_build, results, opp_plan_moves, opp_pool, trials):
    L = []
    line = "=" * 78
    L.append(line)
    L.append("  4-B  턴을 끝까지 돌려 본 결과   ·   각 계획 %d판" % trials)
    L.append(line)
    L.append("  나   " + me_build.describe())
    L.append("  상대 " + opp_build.describe())
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

    head = [("계획", 34), ("승률", 8), ("평균턴", 8),
            ("이겼을 때 남는 HP", 20), ("남는 랭크", 20), ("남는 몸", 8)]
    L.append("  " + "".join(best._pad(h, w) for h, w in head).rstrip())
    for r in results:
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
USAGE = """사용법: python battle.py <내 포켓몬> <상대 포켓몬> [옵션]

  --계획 용의춤,이판사판태클   이 순서대로 쓰는 계획 하나만 돌려본다
  --판수 1000                  기본 400
  --기록                       한 판을 턴별로 찍어서 보여준다
  --최악                       상대가 채용률 낮은 기술까지 다 들고 있다고 본다

  예 : python battle.py 메가보만다 하마돈
       python battle.py 메가보만다 하마돈 --기록
"""


def main():
    args = sys.argv[1:]
    trials, plan_arg, show_log, worst = 400, None, False, False
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
        else:
            rest.append(a); i += 1

    if len(rest) < 2:
        print(USAGE)
        return

    dex = calc.Dex()
    try:
        me, _ = calc.popular_build(dex, dex.find_pokemon(rest[0]))
        opp, _ = calc.popular_build(dex, dex.find_pokemon(rest[1]))
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

    results = [evaluate(dex, me, opp, p, opp_plan, trials=trials) for p in plans]
    # 승률이 먼저, 같으면 '이기고 나서 남는 몸' 으로 가른다
    results.sort(key=lambda r: (-r["winRate"], -r["carry"]))
    print(report(dex, me, opp, results, opp_plan, opp_pool, trials))

    if show_log:
        r = run_once(dex, me, opp, plans[0], opp_plan, random.Random(1), log=True)
        print("\n  [한 판 기록 — %s]" % " → ".join(m["name"] for m in plans[0]))
        for row in r["log"]:
            print("    " + row)
        print("    결과: %s (%d턴)" % (r["result"], r["turns"]))


if __name__ == "__main__":
    main()
