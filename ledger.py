# -*- coding: utf-8 -*-
"""판 장부 — **지금 판에 대해 아는 것 전부를 메모리에 들고 있는 물건.**

    python ledger.py        (장부가 어떻게 생겼나 보여 준다)

## 왜 만들었나 (2026-09-24, 사용자가 정한 방향)

> *"현재까지 확인된 데이터를 정확하게 유지하고, 계산을 검산하고, **사실과 추론을 분리**하고,
>  상대의 선택지를 체계적으로 좁혀서 게임을 이기는 것이다. **모르는 것은 모른다고 표시한다.**
>  확정되지 않은 것은 확정하지 않는다. … **전투 데이터를 물리적으로 메모리에 올려놓고** 해야 한다."*

그때까지 판 상태는 **창의 칸(tkinter 변수)에만** 있었다. 장마다 `gui.board()` 가 칸을 훑어
새 `Board` 를 만들고, 고치고, 다시 칸에 써 넣었다. 그래서 **칸에 못 담는 것은 전부 사라졌다** —

- **어떻게 알았나.** 「상대 HP 55%」 가 막대를 재서 나온 값(±1~2%p)인지 게임이 띄운 글자인지
  기록 줄에만 남고, `row["hp"] = 55.0` 이 되는 순간 없어졌다. 그 뒤로는 둘이 똑같아 보인다.
- **모른다는 것.** 「모른다」 를 담을 수 있는 칸은 `opp_active_known` 하나뿐이었다. HP 는 100,
  상태는 없음, 랭크는 0 으로 **조용히 채워졌다.** 한 번도 안 읽은 값과 100% 라고 읽은 값이
  구별되지 않는다.
- **어떻게 여기까지 왔나.** 턴 기록은 파일에만 있고 프로그램은 그 파일을 안 읽는다.
  그래서 "아까 그 값이 어디서 왔지" 를 프로그램이 되짚을 수가 없다.

★ 그리고 **칸이 없는 값은 장마다 되살아난다.** `Board` 가 `opp_active_known=True` 로 시작하는
  바람에 선출 화면이 꺼 놓은 「모른다」 가 다음 장에서 켜졌고, 실전에서 패리퍼가 나왔는데
  대도각참으로 계산했다 (docs/이어받기.md §5-55). 장부는 **판이 끝날 때까지 안 새로 만든다.**

## 무엇을 들고 있나

`Fact` 하나 = **값 + 어떻게 알았나 + 몇 장째에 + 확정인가.**
`Match` = 그 사실들의 모음 + 판이 흘러온 기록. 둘 다 그냥 메모리 객체다 (파일 아님).

**장부는 계산의 주인이 아니다.** 창의 칸이 여전히 사람이 고치는 자리이고, 계산은 그 칸에서
간다. 장부는 **그 값이 얼마나 믿을 만한지**를 따로 들고 있다가 답 옆에 같이 내놓는다.
(사람이 직접 고친 값이 제일 세다 — 사람은 화면을 눈으로 보고 있다.)
"""

import sys
import time


# ── 어떻게 알았나 ──────────────────────────────────────────────────────
#
# 이름은 **사용자에게 그대로 보여 줄 말**로 짓는다. 창에 「막대로 잼」 이라고 찍힌다.
#
# `확정` 은 "이 값을 그대로 믿고 둬도 되나" 다. 막대를 잰 55% 는 53~57 일 수 있으므로
# 확정이 아니고, 게임이 글자로 띄운 55% 는 확정이다.
# `오차` 는 그 값이 얼마나 움직일 수 있나 (%p). 모르면 None.
HOW = {
    "사람":     {"확정": True,  "오차": 0.0,  "말": "사람이 직접 적음"},
    "화면글자": {"확정": True,  "오차": 0.0,  "말": "화면 글자로 읽음"},
    "문구":     {"확정": True,  "오차": 0.0,  "말": "문구로 알아냄"},
    "이름표":   {"확정": True,  "오차": 0.0,  "말": "이름 칸으로 알아냄"},
    "그림":     {"확정": False, "오차": None, "말": "그림으로 알아봄"},
    "막대":     {"확정": False, "오차": 2.0,  "말": "HP 막대를 재서 (±1~2%p)"},
    "사용률":   {"확정": False, "오차": None, "말": "사용률로 짐작"},
    "미뤄짐":   {"확정": False, "오차": None, "말": "다른 것으로 미루어 봄"},
    "기본값":   {"확정": False, "오차": None, "말": "아무도 안 알려 줘서 기본값"},
}

# 장부가 자리마다 들고 있는 것들. 이 목록에 없는 이름으로 넣으면 **바로 멈춘다** —
# 오타로 만든 새 칸은 아무도 안 읽어서 조용히 사라진다 (이 저장소의 단골 고장 방식).
FIELDS = ("poke", "hp", "status", "brought", "active", "item", "ability",
          "moves", "ranks", "weather", "terrain", "hazards", "fresh")

SIDES = ("me", "opp", "field")


class Fact(object):
    """값 하나와 **그 값을 어떻게 알았는지.**

    ★ 값만 들고 다니면 안 된다. 「55%」 가 막대를 잰 것인지 글자를 읽은 것인지에 따라
      "한 방에 죽나" 의 답이 갈린다. 그래서 값과 출처를 **한 덩어리로** 묶어 둔다.
    """

    __slots__ = ("value", "how", "frame", "at")

    def __init__(self, value, how, frame=0):
        if how not in HOW:
            raise ValueError("모르는 출처: %r (HOW 에 넣고 쓰세요)" % (how,))
        self.value = value
        self.how = how
        self.frame = frame
        self.at = time.time()

    @property
    def sure(self):
        """이 값을 그대로 믿고 둬도 되나."""
        return HOW[self.how]["확정"]

    @property
    def error(self):
        """얼마나 틀릴 수 있나 (%p). 모르면 None."""
        return HOW[self.how]["오차"]

    def describe(self):
        return "%s (%s)" % (_short(self.value), HOW[self.how]["말"])

    def __repr__(self):
        return "Fact(%r, %r, %d장)" % (self.value, self.how, self.frame)


def _short(v):
    if isinstance(v, float):
        return "%g" % v
    if isinstance(v, dict):
        return ", ".join("%s %s" % (k, _short(x)) for k, x in sorted(v.items())) or "없음"
    if isinstance(v, (list, tuple)):
        return ", ".join(_short(x) for x in v) or "없음"
    return "%s" % (v,)


class Match(object):
    """**한 판.** 판이 끝날 때까지 이 객체 하나가 산다 — 장마다 새로 만들지 않는다.

    `put` 으로 넣고 `get`/`how`/`unknown` 으로 꺼낸다. 넣을 때마다 **기록에 한 줄** 남는다.
    """

    KEEP = 400          # 기록을 이만큼까지 들고 있는다 (판 하나면 넉넉하다)

    def __init__(self):
        self.facts = {}         # (쪽, 자리, 무엇) -> Fact
        self.log = []           # [(몇 장째, 시각, 한 줄)]
        self.frame = 0          # 지금 몇 장째를 보고 있나 (창이 알려 준다)
        self.started = time.time()

    # -- 넣고 꺼내기 ------------------------------------------------------
    def key(self, side, i, field):
        if side not in SIDES:
            raise ValueError("모르는 쪽: %r" % (side,))
        if field not in FIELDS:
            raise ValueError("모르는 칸 이름: %r (FIELDS 에 넣고 쓰세요)" % (field,))
        return (side, i, field)

    def put(self, side, i, field, value, how):
        """값 하나를 적는다. **덮어쓴 것도 기록에 남는다** — 되짚을 수 있어야 한다.

        ★ **같은 장 안에서는** 더 흐린 출처가 확정된 값을 못 덮는다. 한 장에서 글자로
          「62%」 를 읽고 막대로 「58%」 를 쟀으면 글자가 맞다.
        ★ 그러나 **다음 장에서는 흐린 값이라도 이긴다.** HP 는 턴마다 바뀐다 —
          3장째의 확정값이 30장째의 측정값을 막으면 판이 통째로 멈춘 것으로 보인다.
          사용자가 정한 것: *"새로운 정보가 기존 판단을 틀렸다고 보여주면 기존 판단을 수정한다."*
        """
        k = self.key(side, i, field)
        old = self.facts.get(k)
        if (old is not None and old.sure and not HOW[how]["확정"]
                and old.frame == self.frame):
            if old.value != value:
                self.note("%s 를 %s 로 바꾸려다 안 바꿈 — 같은 장에서 이미 %s"
                          % (_where(side, i, field), _short(value), old.describe()))
            return old
        fact = Fact(value, how, self.frame)
        self.facts[k] = fact
        if old is None:
            self.note("%s = %s" % (_where(side, i, field), fact.describe()))
        elif old.value != value:
            self.note("%s : %s -> %s" % (_where(side, i, field),
                                         _short(old.value), fact.describe()))
        return fact

    def get(self, side, i, field, default=None):
        f = self.facts.get(self.key(side, i, field))
        return default if f is None else f.value

    def fact(self, side, i, field):
        return self.facts.get(self.key(side, i, field))

    def how(self, side, i, field):
        """그 값을 어떻게 알았나. **한 번도 안 넣었으면 '기본값'** — 즉 모른다는 뜻이다."""
        f = self.facts.get(self.key(side, i, field))
        return "기본값" if f is None else f.how

    def unknown(self, side, i, field):
        """한 번도 안 넣은 칸인가. ★ 조용히 채워진 값과 진짜로 읽은 값을 가른다."""
        return self.key(side, i, field) not in self.facts

    def sure(self, side, i, field):
        f = self.facts.get(self.key(side, i, field))
        return bool(f and f.sure)

    # -- 기록 -------------------------------------------------------------
    def note(self, text):
        self.log.append((self.frame, time.strftime("%H:%M:%S"), text))
        if len(self.log) > self.KEEP:
            del self.log[:len(self.log) - self.KEEP]

    # -- 무엇을 모르나 ----------------------------------------------------
    def soft(self):
        """**확정이 아닌 값 전부** → [(어디, Fact)]. 답 옆에 같이 내놓는다.

        ★ 이게 이 장부의 핵심이다. 「이 답은 이 값들 위에 세워졌고, 그중 이것들은
          확실하지 않다」 를 말할 수 있어야 사용자가 스스로 판단한다.
        """
        out = []
        for k, f in self.facts.items():
            if not f.sure:
                out.append((_where(*k), f))
        out.sort(key=lambda r: r[0])
        return out

    def lines(self, most=40):
        """장부 전체를 글로 — 디버그 파일과 「이거 틀렸어」 가 쓴다."""
        L = ["── 장부 (아는 것 %d가지 · %d장째 · %.0f초째)"
             % (len(self.facts), self.frame, time.time() - self.started)]
        # ! 자리 이름으로만 정렬한다. 튜플째 정렬하면 이름이 같을 때 파이썬이 `Fact` 끼리
        #   크기를 견주려 해서 **디버그 파일을 쓰다가 터진다** (TypeError).
        rows = sorted(((_where(*k), f) for k, f in self.facts.items()),
                      key=lambda r: r[0])
        for where, f in rows:
            L.append("   %-22s %s%s" % (where, f.describe(),
                                        "" if f.sure else "   ← 확정 아님"))
        soft = self.soft()
        L.append("── 확정이 아닌 값 %d개" % len(soft))
        L.append("── 기록 (마지막 %d줄)" % min(most, len(self.log)))
        for frame, at, text in self.log[-most:]:
            L.append("   %s %4d장  %s" % (at, frame, text))
        return L

    def text(self, most=40):
        return "\n".join(self.lines(most))


def _where(side, i, field):
    """(쪽, 자리, 무엇) → 사람이 읽을 자리 이름."""
    who = {"me": "내", "opp": "상대", "field": "판"}[side]
    what = {"poke": "누구", "hp": "HP", "status": "상태", "brought": "냈다",
            "active": "나와 있음", "item": "도구", "ability": "특성",
            "moves": "본 기술", "ranks": "랭크", "weather": "날씨",
            "terrain": "필드", "hazards": "압정", "fresh": "막 나옴"}[field]
    if side == "field":
        return "판 %s" % what
    # ★ **'나와 있음' 은 쪽마다 하나다** (자리마다가 아니다). 자리마다 True 로 적으면
    #   바뀐 뒤에도 앞엣놈의 True 가 남아서 **둘이 동시에 나와 있는** 장부가 된다.
    #   그래서 값은 '몇 번이 나와 있나' 이고 자리는 안 붙인다.
    if field == "active":
        return "%s 나와 있음" % who
    return "%s %d번 %s" % (who, i + 1, what)


def main():
    import paths
    paths.fix_console()
    m = Match()
    m.frame = 12
    m.put("opp", 2, "poke", "한카리아스", "그림")
    m.put("opp", 2, "hp", 99.0, "막대")
    m.put("opp", 2, "active", True, "이름표")
    m.frame = 31
    m.put("opp", 2, "hp", 62.0, "화면글자")
    m.put("opp", 2, "hp", 58.0, "막대")          # 같은 장 — 글자가 이긴다
    m.frame = 44
    m.put("opp", 2, "hp", 41.0, "막대")          # 다음 장 — 바뀐 것이므로 이긴다
    m.put("me", 0, "hp", 100.0, "사람")
    print(m.text())
    print("\n모르는 것: 상대 3번 도구 → %s / 한 번도 안 넣었나 %s"
          % (m.how("opp", 2, "item"), m.unknown("opp", 2, "item")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
